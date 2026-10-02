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
  7. pass each target through the sizer
  8. turn any difference between the sized target and actual into one
     market order, queued for the next bar

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
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from engine.brokers.sim import SimBroker
from engine.core.portfolio import ExitPrices, Portfolio, PortfolioView
from engine.core.types import Bar, Fill, Order, TargetPosition
from engine.costs.base import CostModel
from engine.costs.zero import ZeroCostModel
from engine.features.technical import TechnicalFeatureSet
from engine.sizing.base import Sizer
from engine.sizing.fixed import FixedQuantitySizer
from engine.strategies.base import Strategy

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTRUMENTS_CONFIG = REPO_ROOT / "config" / "instruments.yaml"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

CSV_COLUMNS = ("ts_open", "ts_close", "open", "high", "low", "close", "volume", "spread")


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


def run_backtest(  # noqa: PLR0913 -- one wiring argument per component, by design
    bars: Sequence[Bar],
    strategy: Strategy,
    *,
    contract_sizes: Mapping[str, Decimal],
    starting_balance: Decimal = Decimal(0),
    cost_model: CostModel | None = None,
    sizer: Sizer | None = None,
) -> BacktestResult:
    """Stream `bars` through `strategy` and report what came out.

    `starting_balance` defaults to zero so that `total_pnl` and
    `final_equity` are the same number in a test that only cares about
    P&L. Nothing in the accounting depends on the starting balance --
    it is added to both sides.
    """
    if not bars:
        raise ValueError("run_backtest needs at least one bar")

    costs = cost_model or ZeroCostModel()
    portfolio = Portfolio(starting_balance=starting_balance, contract_sizes=contract_sizes)
    broker = SimBroker(cost_model=costs, portfolio=portfolio)
    features = TechnicalFeatureSet([])
    sizing = sizer or FixedQuantitySizer()
    strategy_name = type(strategy).__name__
    orders: list[Order] = []
    fills: list[Fill] = []

    last_close: dict[str, datetime] = {}
    for bar_index, bar in enumerate(bars):
        # 1. rollovers up to this bar's open, on the pre-fill position.
        previous_close = last_close.get(bar.symbol)
        if previous_close is not None:
            _accrue_financing(portfolio, costs, bar.symbol, previous_close, bar.ts_open)
        # 2. fills at this bar's open.
        fills.extend(broker.fill_pending(bar))
        # 3. rollovers inside this bar, on the post-fill position.
        _accrue_financing(portfolio, costs, bar.symbol, bar.ts_open, bar.ts_close)
        last_close[bar.symbol] = bar.ts_close
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
            order = _order_for_target(
                target,
                portfolio,
                sized_quantity=sizing.size(target, portfolio, snapshot),
                pending_orders=broker.pending_orders(),
                identifier=_client_order_id(strategy_name, target.symbol, bar, intent_index),
            )
            if order is None:
                continue
            broker.submit(order)
            orders.append(order)

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
    )


def _order_for_target(
    target: TargetPosition,
    portfolio: PortfolioView,
    *,
    sized_quantity: Decimal,
    pending_orders: Sequence[Order],
    identifier: str,
) -> Order | None:
    """Turn a target position into the one market order that closes the gap
    between target and actual -- or into nothing at all.

    This is what makes target-position semantics work. `AlwaysLong` returns
    the same target on every bar of a run; on the first it differs from a
    flat book by the full size, and on all the others the difference is
    zero and no order exists. One order for the whole run, with no
    "am I already in?" test inside the strategy.

    "WHERE THE ENGINE ALREADY IS" INCLUDES ORDERS NOT YET FILLED. Lots
    that have been ordered and not filled are as committed as lots that
    have, so they count against the target exactly the same. Counting only
    filled lots looks correct with one instrument -- each bar fills the
    previous bar's order before the strategy is asked again -- and breaks
    the moment two instruments interleave, because a bar for one symbol
    cannot fill the other's pending order. The strategy is then asked
    while the order is in flight, the book looks flat, and the whole
    position is ordered a second time under a new `client_order_id`, which
    is a new intent rather than a retry, so §5.2 idempotency does not stop
    it. Both fill, and the position is double the size anyone asked for.

    `intent_id` carries the same text as `client_order_id` here because
    one intent produces at most one order. They separate in phase 3, when
    a sizer can turn a single intent into several.
    """
    committed = portfolio.position_quantity(target.symbol) + _net_pending_quantity(
        pending_orders, target.symbol
    )
    # The sized quantity, not the target's own, is what the engine aims
    # for -- the sizer is the only thing entitled to decide how big a
    # position is. `FixedQuantitySizer` returns the target unchanged,
    # which is why the reference strategies behave identically either way.
    delta = sized_quantity - committed
    if delta == 0:
        return None
    return Order(
        client_order_id=identifier,
        symbol=target.symbol,
        side="buy" if delta > 0 else "sell",
        quantity=abs(delta),
        order_type="market",
        limit_price=None,
        stop_price=None,
        intent_id=identifier,
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
    position = portfolio.positions().get(symbol)
    if position is None:
        return
    amount = costs.financing(position, window_start, window_end)
    if amount != 0:
        portfolio.accrue_financing(symbol, amount)


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
