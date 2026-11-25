"""Bar-by-bar driver for the reference strategies, plus a CSV fixture loader.

WHY THIS LIVES IN tests/ AND NOT IN engine/core/engine.py
---------------------------------------------------------
Spec §3 reserves `core/engine.py` for THE orchestrator, the one used by
backtest and live alike, and §9 does not schedule it in phase 2. The loop
below is deliberately not that file, for one concrete reason: the fill
path is not yet decided.

In a backtest a queued order fills when the next bar arrives, which is why
`SimBroker.fill_pending(bar)` exists. Live fills are not discovered that
way at all -- Appendix A.4 and A.7 describe polling MT5 deal history over
a time range and matching it against a durable intent log. A loop written
today around `fill_pending(bar)` would work for the simulated broker and
no other, and a loop that works for only one wiring is precisely the
separate backtester P1 forbids. It would look harmless now and diverge
later.

So this is a test harness: the smallest thing that can stream bars through
a real `Strategy`, a real `SimBroker`, a real `CostModel` and the real
`Portfolio`, so that phase 2's exit criterion can be measured. It contains
no strategy logic and no accounting of its own -- every number it reports
comes out of `Portfolio`. When the real orchestrator arrives and the live
fill path is settled, this should be deleted rather than extended.

WHAT ONE BAR DOES, in order
---------------------------
  1. charge rollovers in (previous bar's close, this bar's open], against
     the position as it stood BEFORE this bar's fills
  2. fill any order queued by the previous bar's decision, at this bar's open
  3. charge rollovers in (this bar's open, this bar's close], against the
     position as it stands AFTER those fills
  4. update the feature pipeline with this bar
  5. mark the portfolio to this bar's close, asking the cost model what a
     long and a short could each exit at
  6. ask the strategy for its target positions
  7. ask the position book whether the target is held -- a weight target
     identical to the one that sized the position, while lots are held or
     ordered (PC.2) -- and if not, pass it through the sizer, with the
     deciding bar, the committed quantity (held plus ordered) and the
     instrument spec
  8. ask the position book (PC.1, spec §2.10) for the orders that move
     held-plus-pending lots to the sized target, under the run's position
     mode, and queue them for the next bar. Netting: one order for the
     difference. Hedging: a new ticket for an increase; closes naming
     tickets, oldest first, for a reduction; closes then an opening order
     for a flip

THE DECIDING BAR IS PER SYMBOL (phase 3c.3, operator 2026-11-23). A target
is sized from the latest bar of ITS OWN symbol, whichever symbol's bar is
being processed -- that bar may be hours old if its market is closed. A
target for a symbol with no bar yet waits (no order, a `no_bar_yet` note);
a symbol targeted but never given a bar in the whole run raises
`NoBarForTargetError` at the end.

STOPS ARE NOT EXECUTED (phase 3c.3, decision D). After step 2, if a held
position's stop -- the stop_price of the target that sized it -- lies
within this bar's range, the run stops with `StopNotExecutedError` rather
than carrying on as if the stop were not there. A long's stop is checked
against the bar's low as a sell could exit it; a short's against its high
as a buy could exit it, i.e. at the ask.

Step 2 happening before step 6 is the entire point of the fill rule: a
decision made at bar N's close cannot be acted on until bar N+1 exists.

STEPS 1 AND 3 ARE SPLIT AROUND THE FILL, and that is what makes the size
at each rollover exact rather than approximate. Rollovers land on bar
boundaries and fills land on bar opens, so a single charge per bar would
have to guess which side of the fill a boundary rollover belonged to. Two
windows do not guess. The consequences are the two cases worth stating
plainly:

- A position OPENED at exactly a rollover instant is NOT charged for it.
  The instant falls in window 1, which is evaluated before the fill, when
  the book was still flat.
- A position CLOSED at exactly a rollover instant IS charged for it. The
  same window 1 is evaluated before the closing fill, while the position
  is still held.

Which is the right way round: you owe for the night you held, and you do
not owe for one that ended before you were in.

Step 5 asks the cost model rather than using `bar.close` directly, because
what a position is worth is what it could be closed at, and that differs
by direction once there is a spread. The same cost model answers for the
fill in step 2, so the two cannot drift apart.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from engine.brokers.sim import SimBroker
from engine.core.instruments import InstrumentSpec
from engine.core.portfolio import ExitPrices, Portfolio, PortfolioView
from engine.core.positions import PositionBook
from engine.core.types import Bar, Fill, Order, PositionMode
from engine.costs.base import CostModel
from engine.costs.zero import ZeroCostModel
from engine.features.technical import TechnicalFeatureSet
from engine.sizing.base import Sizer, SizingContext
from engine.sizing.equity import SizingNote
from engine.sizing.fixed import FixedQuantitySizer
from engine.strategies.base import Strategy

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTRUMENTS_CONFIG = REPO_ROOT / "config" / "instruments.yaml"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

CSV_COLUMNS = ("ts_open", "ts_close", "open", "high", "low", "close", "volume", "spread")


class StopNotExecutedError(RuntimeError):
    """A price reached the stop of a held position, and stop execution is
    not built yet (phase 3c.3, decision D). Raised rather than ignored: a
    backtest that runs straight through its stops reports losses no real
    account with those stops could have had."""


class NoBarForTargetError(RuntimeError):
    """A strategy targeted a symbol that received no bar in the whole run
    (operator, 2026-11-23). Waiting for a first bar is right bar by bar; a
    whole run of waiting means the feed and the strategy disagree about the
    instruments, and the result would silently omit one of them."""


@dataclass(frozen=True)
class BacktestResult:
    """Everything the run produced, so a failure can be read rather than
    debugged."""

    total_pnl: Decimal
    final_equity: Decimal
    realised_pnl: Decimal
    unrealised_pnl: Decimal
    # Financing sitting on still-open positions. Separate from realised
    # because that is where the venue keeps it until a position closes.
    financing_accrued: Decimal
    orders: tuple[Order, ...]
    fills: tuple[Fill, ...]
    unfilled_orders: tuple[Order, ...]
    bars_processed: int
    first_bar: Bar
    last_bar: Bar
    # What the sizer capped or declined (3c.3), so it is visible. Into the
    # decision log at orchestrator design.
    sizing_notes: tuple = ()
    # Each traded symbol's share of total_pnl (3c.4): its realised P&L
    # (closed lots, released financing, fees) plus its open position at the
    # last mark. Sums to total_pnl exactly; a symbol never filled is absent.
    pnl_by_symbol: Mapping[str, Decimal] = field(default_factory=dict)

    def describe(self) -> str:
        """A plain-text account of the run, used as the message on a failed
        assertion. Values are printed in full and are NOT rounded: rounding
        here would hide a mismatch in the last decimal place, which is
        exactly the kind this phase is looking for."""
        lines = [
            "",
            f"bars processed:   {self.bars_processed}",
            f"first bar:        {self.first_bar.ts_open.isoformat()} "
            f"open={self.first_bar.open} close={self.first_bar.close}",
            f"last bar:         {self.last_bar.ts_open.isoformat()} "
            f"open={self.last_bar.open} close={self.last_bar.close}",
            f"orders placed:    {len(self.orders)}",
        ]
        lines += [
            f"  order  {order.side} {order.quantity} {order.symbol} "
            f"(client_order_id={order.client_order_id})"
            for order in self.orders
        ]
        lines.append(f"fills:            {len(self.fills)}")
        lines += [
            f"  fill   {fill.quantity} {fill.symbol} @ {fill.price} "
            f"at {fill.ts.isoformat()} fees={fill.fees}"
            for fill in self.fills
        ]
        if self.unfilled_orders:
            lines.append(f"NEVER FILLED:     {len(self.unfilled_orders)} order(s) left queued")
        lines += [
            f"realised P&L:     {self.realised_pnl}",
            f"unrealised P&L:   {self.unrealised_pnl}",
            f"total P&L:        {self.total_pnl}",
            f"final equity:     {self.final_equity}",
            "",
        ]
        return "\n".join(lines)


def run_backtest(  # noqa: PLR0912, PLR0913, PLR0915 -- one argument per component; one loop, deleted at orchestrator design
    bars: Sequence[Bar],
    strategy: Strategy,
    *,
    position_mode: PositionMode,
    contract_sizes: Mapping[str, Decimal],
    starting_balance: Decimal = Decimal(0),
    cost_model: CostModel | None = None,
    sizer: Sizer | None = None,
    instruments: Mapping[str, InstrumentSpec] | None = None,
) -> BacktestResult:
    """Stream `bars` through `strategy` and report what came out.

    `starting_balance` defaults to zero so that `total_pnl` and
    `final_equity` are the same number in a test that only cares about
    P&L. Nothing in the accounting depends on the starting balance --
    it is added to both sides.
    """
    if not bars:
        raise ValueError("run_backtest needs at least one bar")
    specs = dict(instruments or {})
    for symbol, spec in specs.items():
        if symbol in contract_sizes and contract_sizes[symbol] != spec.contract_size:
            raise ValueError(
                f"{symbol}: contract size {contract_sizes[symbol]} disagrees with the "
                f"instrument spec's {spec.contract_size}"
            )

    costs = cost_model or ZeroCostModel()
    portfolio = Portfolio(
        starting_balance=starting_balance,
        contract_sizes=contract_sizes,
        position_mode=position_mode,
    )
    broker = SimBroker(cost_model=costs, portfolio=portfolio, position_mode=position_mode)
    book = PositionBook(portfolio, position_mode)
    features = TechnicalFeatureSet([])
    sizing = sizer or FixedQuantitySizer()
    strategy_name = type(strategy).__name__
    orders: list[Order] = []
    fills: list[Fill] = []

    last_close: dict[str, datetime] = {}
    stops: dict[str, Decimal] = {}  # symbol -> stop of the target that sized it
    # Each symbol's latest bar: the DECIDING bar for a target in that symbol,
    # whichever symbol's bar is being processed (3c.3, operator 2026-11-23).
    latest_bar: dict[str, Bar] = {}
    waits: list[SizingNote] = []  # targets that waited for their symbol's first bar
    for bar_index, bar in enumerate(bars):
        # 1. rollovers up to this bar's open, on the pre-fill position.
        previous_close = last_close.get(bar.symbol)
        if previous_close is not None:
            _accrue_financing(portfolio, costs, bar.symbol, previous_close, bar.ts_open)
        # 2. fills at this bar's open.
        fills.extend(broker.fill_pending(bar))
        _refuse_a_reached_stop(bar, stops.get(bar.symbol), portfolio, costs)
        # 3. rollovers inside this bar, on the post-fill position.
        _accrue_financing(portfolio, costs, bar.symbol, bar.ts_open, bar.ts_close)
        last_close[bar.symbol] = bar.ts_close
        latest_bar[bar.symbol] = bar
        features.update(bar)
        snapshot = features.snapshot()
        portfolio.mark(
            bar.symbol,
            ExitPrices(
                long_exit=costs.executable_price("sell", bar, bar.close),
                short_exit=costs.executable_price("buy", bar, bar.close),
            ),
        )
        if bar_index < strategy.warmup_bars:
            continue
        targets = strategy.on_bar(bar, snapshot, portfolio)
        for intent_index, target in enumerate(targets):
            if target.symbol not in latest_bar:
                # No close to size from yet. The target waits: targets are
                # restated every bar, so it is sized on its symbol's first bar.
                waits.append(
                    SizingNote(bar.ts_close, target.symbol, "no_bar_yet", Decimal(0), Decimal(0))
                )
                stops.pop(target.symbol, None)
                continue
            committed = _committed(portfolio, broker.pending_orders(), target.symbol)
            if book.holds(target, committed):
                continue  # identical to the target that sized it (PC.2, decision 2)
            context = SizingContext(
                bar=latest_bar[target.symbol],
                committed=committed,
                spec=specs.get(target.symbol),
            )
            sized = sizing.size(target, portfolio, snapshot, context)
            book.record_sizing(target)
            if target.stop_price is not None and sized != 0:
                stops[target.symbol] = target.stop_price
            else:
                stops.pop(target.symbol, None)
            # The sized quantity, not the target's own, is what the engine aims
            # for: the sizer alone decides how big a position is. Pending
            # orders count as held (see `_committed`).
            for order in book.plan(
                target.symbol,
                sized,
                pending_orders=broker.pending_orders(),
                intent_id=_client_order_id(strategy_name, target.symbol, bar, intent_index),
            ):
                broker.submit(order)
                orders.append(order)

    never_seen = sorted({note.symbol for note in waits} - set(latest_bar))
    if never_seen:
        raise NoBarForTargetError(
            f"the strategy targeted {never_seen} but no bar for "
            f"{'it' if len(never_seen) == 1 else 'them'} arrived in the whole run, so "
            "those targets were never sized; the feed and the strategy disagree about "
            "the instruments"
        )
    return BacktestResult(
        total_pnl=portfolio.equity - starting_balance,
        final_equity=portfolio.equity,
        realised_pnl=portfolio.realised_pnl,
        unrealised_pnl=portfolio.unrealised_pnl,
        financing_accrued=sum(
            (position.financing_accrued for position in portfolio.positions().values()),
            Decimal(0),
        ),
        orders=tuple(orders),
        fills=tuple(fills),
        unfilled_orders=tuple(broker.pending_orders()),
        bars_processed=len(bars),
        first_bar=bars[0],
        last_bar=bars[-1],
        sizing_notes=tuple(
            sorted([*waits, *getattr(sizing, "notes", ())], key=lambda note: note.ts)
        ),
        pnl_by_symbol={
            symbol: portfolio.realised_pnl_for(symbol) + portfolio.unrealised_pnl_for(symbol)
            for symbol in dict.fromkeys(fill.symbol for fill in fills)
        },
    )


def _committed(portfolio: PortfolioView, pending_orders: Sequence[Order], symbol: str) -> Decimal:
    """Held plus ordered-but-not-filled, signed.

    LOTS ORDERED AND NOT FILLED ARE AS COMMITTED AS LOTS HELD. Counting only
    filled lots looks correct with one instrument -- each bar fills the
    previous bar's order before the strategy is asked again -- and breaks
    the moment two instruments interleave: a bar for one symbol cannot fill
    the other's pending order, the book looks flat while the order is in
    flight, and the whole position is ordered a second time under a new
    `client_order_id`, which §5.2 idempotency does not stop. The position
    book (`PositionBook.plan`) counts pending orders the same way.
    """
    return portfolio.position_quantity(symbol) + _net_pending_quantity(pending_orders, symbol)


def _refuse_a_reached_stop(
    bar: Bar, stop: Decimal | None, portfolio: PortfolioView, costs: CostModel
) -> None:
    """Stop the run if this bar reached the stop of a held position."""
    held = portfolio.position_quantity(bar.symbol)
    if stop is None or held == 0:
        return
    if held > 0:
        reached = costs.executable_price("sell", bar, bar.low) <= stop
    else:
        reached = costs.executable_price("buy", bar, bar.high) >= stop
    if reached:
        raise StopNotExecutedError(
            f"{bar.symbol} reached the stop {stop} of the position held ({held} lots) in "
            f"the bar opening {bar.ts_open.isoformat()}, and stop execution is not built "
            "yet (phase 3c.3, decision D). Running on would report a result no account "
            "with this stop could have had."
        )


def _accrue_financing(
    portfolio: Portfolio,
    costs: CostModel,
    symbol: str,
    window_start: datetime,
    window_end: datetime,
) -> None:
    """Ask the cost model what the rollovers in this window cost, and put
    it on the position.

    The loop contributes a window and a position and nothing else. It does
    no date arithmetic, counts no nights, and knows nothing about weekends
    or triple days -- all of that is behind the `CostModel` seam, where a
    bug in it cannot reach a run using `ZeroCostModel`.
    """
    # One charge per position (ticket), as MT5 charges swap: under hedging a
    # symbol can hold several, each with its own open time and lots.
    for position in portfolio.tickets(symbol):
        amount = costs.financing(position, window_start, window_end)
        if amount != 0:
            portfolio.accrue_financing(position.ticket, amount)


def _client_order_id(strategy_name: str, symbol: str, bar: Bar, intent_index: int) -> str:
    """Compose the deterministic order id required by §5.2.

    Derived from strategy name, symbol, the deciding bar's close and the
    index of the intent within that bar, so an identical run produces
    identical ids and a retry after a crash carries the id the broker
    already knows.

    It is composed as text rather than run through Python's `hash()`,
    which §5.2 names literally: `hash()` on strings is salted per process
    (PYTHONHASHSEED), so identical runs would produce different ids and
    determinism -- the property that makes a result reproducible at all --
    would be lost.
    """
    return f"{strategy_name}:{symbol}:{bar.ts_close.isoformat()}:{intent_index}"


def _net_pending_quantity(orders: Sequence[Order], symbol: str) -> Decimal:
    """Signed lots ordered for `symbol` and not yet filled. Positive is
    buying, negative is selling, and a buy and a sell of the same size
    cancel -- they leave the position where it is."""
    total = Decimal(0)
    for order in orders:
        if order.symbol == symbol:
            total += order.quantity if order.side == "buy" else -order.quantity
    return total


def merge_bars(series: Mapping[str, Sequence[Bar]], order: Sequence[str]) -> list[Bar]:
    """Several instruments' bars as one stream: by bar open, and at a shared
    open by `order` -- the SAME-TIMESTAMP PROCESSING ORDER, stated by the
    caller, never left to file or dictionary order (3c.4, operator
    2026-11-23). It matters: a bar processed first at an instant is marked
    before the others decide at that instant.

    `order` must name each symbol exactly once. A series must hold only its
    own symbol's bars, and no instant twice.
    """
    if len(set(order)) != len(order) or set(order) != set(series):
        raise ValueError(
            f"the processing order {list(order)} must name each of {sorted(series)} exactly once"
        )
    for symbol, bars in series.items():
        strangers = {bar.symbol for bar in bars} - {symbol}
        if strangers:
            raise ValueError(f"bars of {sorted(strangers)} filed under {symbol}")
        opens = [bar.ts_open for bar in bars]
        if len(set(opens)) != len(opens):
            raise ValueError(f"{symbol} has a bar opening at the same instant twice")
    rank = {symbol: index for index, symbol in enumerate(order)}
    return sorted(
        (bar for bars in series.values() for bar in bars),
        key=lambda bar: (bar.ts_open, rank[bar.symbol]),
    )


def load_bars_from_csv(path: Path, symbol: str) -> list[Bar]:
    """Read a fixture CSV into `Bar` objects, in file order.

    Expected header -- exactly these names, in any order:

        ts_open,ts_close,open,high,low,close,volume,spread

    `spread` is in PRICE units, not points: the conversion happened at the
    feed, when the fixture was exported. A fixture without the column is
    rejected rather than defaulted to zero, because a spread-less bar
    would price a backtest as though crossing were free.

    Timestamps are ISO-8601 and must carry an offset:
    "2026-01-05 13:45:00+00:00" or "2026-01-05T13:45:00Z". An offset other
    than UTC is converted; a timestamp with no offset at all is rejected
    rather than assumed to be UTC. Four clocks are in play on this project
    -- operator UTC+4, MT5 server UTC+2/+3, the firm's accounting day, and
    internal UTC -- so "it's probably UTC" is wrong more often than right.

    Prices are read as text straight into `Decimal`, never through
    `float()`. 1.1005 is not exactly representable as a float, and one
    float anywhere in the accounting path is enough to make a
    to-the-cent comparison fail for reasons that have nothing to do with
    the engine.

    Rows are used in file order. They are not sorted, deduplicated or
    gap-filled: a fixture spanning a weekend simply has Friday's last bar
    followed by Monday's first, which is what stored data looks like
    (Appendix B.6).
    """
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"fixture {path} has a header but no data rows")
    missing = [column for column in CSV_COLUMNS if column not in rows[0]]
    if missing:
        raise ValueError(
            f"fixture {path} is missing column(s): {', '.join(missing)}. "
            f"Expected header: {','.join(CSV_COLUMNS)}"
        )
    return [
        Bar(
            symbol=symbol,
            ts_open=_parse_utc(row["ts_open"]),
            ts_close=_parse_utc(row["ts_close"]),
            open=Decimal(row["open"].strip()),
            high=Decimal(row["high"].strip()),
            low=Decimal(row["low"].strip()),
            close=Decimal(row["close"].strip()),
            volume=Decimal(row["volume"].strip()),
            is_final=True,
            spread=Decimal(row["spread"].strip()),
        )
        for row in rows
    ]


def _parse_utc(text: str) -> datetime:
    parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(
            f"timestamp {text!r} has no UTC offset. Write it as "
            "'2026-01-05 13:45:00+00:00' or '2026-01-05T13:45:00Z' -- a bare "
            "timestamp is ambiguous between four clocks on this project"
        )
    return parsed.astimezone(UTC)
