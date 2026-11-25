"""Tests for the per-ticket ledger (spec v3.12, §2.10; phase PC.1).

Under HEDGING every opening fill is its own position -- a ticket -- with its
own open price and its own accrued swap, and a closing fill names the
ticket it reduces. Under NETTING there is one position per symbol, its
ticket is the symbol, and the phase 2 arithmetic (average cost, flips
through zero) is unchanged; tests/unit/test_portfolio.py covers that.

Every expected figure is written out as arithmetic. XAUUSD's contract size
is 100, so one lot moving 1.00 is 100.00.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from engine.core.portfolio import BothDirectionsError, ExitPrices, Portfolio
from engine.core.types import Fill, PositionMode

SYMBOL = "XAUUSD"
CONTRACT_SIZES = {SYMBOL: Decimal(100), "EURUSD": Decimal(100000)}
_TS = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def _ledger(mode: PositionMode = "hedging") -> Portfolio:
    return Portfolio(starting_balance=Decimal(0), contract_sizes=CONTRACT_SIZES, position_mode=mode)


def _fill(  # noqa: PLR0913 -- one keyword per Fill field a test varies
    quantity: str,
    price: str,
    ticket: str,
    *,
    ts: datetime = _TS,
    symbol: str = SYMBOL,
    fees: str = "0",
) -> Fill:
    """Signed quantity: positive bought, negative sold."""
    return Fill(
        order_id="o",
        client_order_id="c",
        symbol=symbol,
        quantity=Decimal(quantity),
        price=Decimal(price),
        fees=Decimal(fees),
        ts=ts,
        ticket=ticket,
    )


class TestHedgingTickets:
    def test_each_opening_fill_is_its_own_ticket_at_its_own_price(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("1", "2000.00", "1"))
        ledger.apply_fill(_fill("1", "2010.00", "2"))

        tickets = ledger.tickets(SYMBOL)
        assert [t.ticket for t in tickets] == ["1", "2"]
        assert [t.quantity for t in tickets] == [Decimal(1), Decimal(1)]
        assert [t.avg_price for t in tickets] == [Decimal("2000.00"), Decimal("2010.00")]
        assert ledger.position_quantity(SYMBOL) == Decimal(2)

    def test_positions_are_keyed_by_ticket(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("1", "2000.00", "1"))
        ledger.apply_fill(_fill("1", "2010.00", "2"))

        assert set(ledger.positions()) == {"1", "2"}

    def test_closing_a_ticket_realises_against_its_own_open_price(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("1", "2000.00", "1"))
        ledger.apply_fill(_fill("1", "2010.00", "2"))
        ledger.apply_fill(_fill("-1", "2020.00", "2"))

        # ticket 2 only: (2020.00 - 2010.00) x 1 x 100 = 1000.00
        assert ledger.realised_pnl == Decimal("1000.00")
        assert [t.ticket for t in ledger.tickets(SYMBOL)] == ["1"]

    def test_netting_realises_the_same_fills_against_the_average(self) -> None:
        """The contrast that makes the test above mean something. Same
        fills, netting: average cost (2000 + 2010) / 2 = 2005.00, so
        (2020.00 - 2005.00) x 1 x 100 = 1500.00 realised. Equity is equal
        under both modes; only the realised/unrealised split differs."""
        netting = _ledger("netting")
        for quantity, price in (("1", "2000.00"), ("1", "2010.00"), ("-1", "2020.00")):
            netting.apply_fill(_fill(quantity, price, SYMBOL))
        hedging = _ledger()
        hedging.apply_fill(_fill("1", "2000.00", "1"))
        hedging.apply_fill(_fill("1", "2010.00", "2"))
        hedging.apply_fill(_fill("-1", "2020.00", "2"))
        for ledger in (netting, hedging):
            ledger.mark(SYMBOL, ExitPrices.unadjusted(Decimal("2020.00")))

        assert netting.realised_pnl == Decimal("1500.00")
        # hedging 1000.00 realised + ticket 1 (2020 - 2000) x 100 = 2000.00 open;
        # netting 1500.00 + (2020 - 2005) x 100 = 1500.00 open. Both 3000.00.
        assert hedging.equity == netting.equity == Decimal("3000.00")

    def test_a_partial_close_realises_only_the_closed_lots(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("0.30", "2000.00", "1"))
        ledger.apply_fill(_fill("-0.10", "2010.00", "1"))

        # (2010.00 - 2000.00) x 0.10 x 100 = 100.00
        assert ledger.realised_pnl == Decimal("100.00")
        (ticket,) = ledger.tickets(SYMBOL)
        assert ticket.quantity == Decimal("0.20")
        assert ticket.cost == Decimal("400.0000")  # 0.20 x 2000.00

    def test_a_partial_close_releases_swap_in_proportion(self) -> None:
        """Until the venue check in docs/state.md says otherwise (Blocked):
        a third of the lots closed releases a third of the accrued swap."""
        ledger = _ledger()
        ledger.apply_fill(_fill("0.30", "2000.00", "1"))
        ledger.accrue_financing("1", Decimal("-3.00"))
        ledger.apply_fill(_fill("-0.10", "2000.00", "1"))

        # -3.00 x 0.10 / 0.30 = -1.00 to realised; -2.00 stays on the ticket
        assert ledger.realised_pnl == Decimal("-1.00")
        (ticket,) = ledger.tickets(SYMBOL)
        assert ticket.financing_accrued == Decimal("-2.00")

    def test_financing_lands_on_the_named_ticket_only(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("1", "2000.00", "1"))
        ledger.apply_fill(_fill("1", "2000.00", "2"))
        ledger.accrue_financing("2", Decimal("-5.00"))

        accrued = {t.ticket: t.financing_accrued for t in ledger.tickets(SYMBOL)}
        assert accrued == {"1": Decimal(0), "2": Decimal("-5.00")}

    def test_fees_are_realised_on_the_fill_that_paid_them(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("1", "2000.00", "1", fees="2.50"))
        ledger.apply_fill(_fill("-1", "2000.00", "1", fees="2.50"))

        assert ledger.realised_pnl == Decimal("-5.00")

    def test_per_symbol_pnl_sums_that_symbols_tickets(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("1", "2000.00", "1"))
        ledger.apply_fill(_fill("1", "2010.00", "2"))
        ledger.apply_fill(_fill("-1", "2020.00", "1"))
        ledger.apply_fill(_fill("1", "1.1000", "3", symbol="EURUSD"))
        ledger.mark(SYMBOL, ExitPrices.unadjusted(Decimal("2030.00")))

        # realised: ticket 1, (2020 - 2000) x 100 = 2000.00
        # open: ticket 2, (2030 - 2010) x 100 = 2000.00
        assert ledger.realised_pnl_for(SYMBOL) == Decimal("2000.00")
        assert ledger.unrealised_pnl_for(SYMBOL) == Decimal("2000.00")
        assert ledger.position_quantity("EURUSD") == Decimal(1)


class TestHedgingCloseOrder:
    def test_tickets_are_oldest_first_with_the_ticket_number_breaking_ties(self) -> None:
        """Ticket 11 opened an hour earlier than 9 and 10, so it is first.
        9 and 10 opened at the same instant: 9 before 10 by NUMBER -- as
        text "10" would sort before "9"."""
        ledger = _ledger()
        ledger.apply_fill(_fill("1", "2000.00", "10"))
        ledger.apply_fill(_fill("1", "2000.00", "9"))
        ledger.apply_fill(_fill("1", "2000.00", "11", ts=_TS - timedelta(hours=1)))

        assert [t.ticket for t in ledger.tickets(SYMBOL)] == ["11", "9", "10"]

    def test_a_flat_symbol_has_no_tickets(self) -> None:
        assert _ledger().tickets(SYMBOL) == []


class TestHedgingRefusals:
    def test_an_opposite_opening_fill_halts_and_leaves_the_book_alone(self) -> None:
        """The invariant (§2.10): never both directions in one symbol. On a
        hedging account an opposite order that names no ticket opens a
        second position; the ledger halts instead of holding it."""
        ledger = _ledger()
        ledger.apply_fill(_fill("1", "2000.00", "1"))

        with pytest.raises(BothDirectionsError, match=SYMBOL):
            ledger.apply_fill(_fill("-1", "2000.00", "2"))
        assert ledger.position_quantity(SYMBOL) == Decimal(1)
        assert [t.ticket for t in ledger.tickets(SYMBOL)] == ["1"]
        assert ledger.realised_pnl == Decimal(0)

    def test_closing_more_than_a_ticket_holds_is_refused(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("0.10", "2000.00", "1"))

        with pytest.raises(ValueError, match="holds"):
            ledger.apply_fill(_fill("-0.20", "2000.00", "1"))
        assert ledger.position_quantity(SYMBOL) == Decimal("0.10")

    def test_adding_to_an_open_ticket_is_refused(self) -> None:
        """Under hedging an add is a new ticket; a fill in the same
        direction naming an open ticket means the broker and the ledger
        disagree about what a ticket is."""
        ledger = _ledger()
        ledger.apply_fill(_fill("0.10", "2000.00", "1"))

        with pytest.raises(ValueError, match="new ticket"):
            ledger.apply_fill(_fill("0.10", "2000.00", "1"))
        assert ledger.position_quantity(SYMBOL) == Decimal("0.10")

    def test_financing_on_a_ticket_that_is_not_open_is_refused(self) -> None:
        ledger = _ledger()
        with pytest.raises(KeyError, match="no open position"):
            ledger.accrue_financing("1", Decimal("-1"))


class TestNettingTicket:
    def test_a_netting_fill_names_its_symbol_as_its_ticket(self) -> None:
        ledger = _ledger("netting")
        with pytest.raises(ValueError, match="netting"):
            ledger.apply_fill(_fill("1", "2000.00", "1"))

    def test_netting_has_one_ticket_per_symbol_named_after_it(self) -> None:
        ledger = _ledger("netting")
        ledger.apply_fill(_fill("1", "2000.00", SYMBOL))
        ledger.apply_fill(_fill("1", "2010.00", SYMBOL))

        (position,) = ledger.tickets(SYMBOL)
        assert position.ticket == SYMBOL
        assert position.quantity == Decimal(2)


class TestMode:
    def test_the_ledger_reports_its_mode(self) -> None:
        assert _ledger("hedging").position_mode == "hedging"
        assert _ledger("netting").position_mode == "netting"

    def test_an_unknown_mode_is_refused(self) -> None:
        with pytest.raises(ValueError, match="position_mode"):
            _ledger("fifo")  # type: ignore[arg-type]
