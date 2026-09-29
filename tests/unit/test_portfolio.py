"""Tests for portfolio accounting. See docs/trading-engine-architecture.md
§2.4 and §3.

Every expected figure below is written out as arithmetic in a comment so
it can be checked with a calculator, independently of what portfolio.py
does. XAUUSD's contract size is 100, so one lot moving 1.00 in price is
100.00 of P&L.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from engine.core.portfolio import Portfolio, Position
from engine.core.types import Fill

XAUUSD_CONTRACT_SIZE = Decimal(100)
EURUSD_CONTRACT_SIZE = Decimal(100000)
CONTRACT_SIZES = {"XAUUSD": XAUUSD_CONTRACT_SIZE, "EURUSD": EURUSD_CONTRACT_SIZE}
_TS = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def _portfolio(starting_balance: str = "0") -> Portfolio:
    return Portfolio(starting_balance=Decimal(starting_balance), contract_sizes=CONTRACT_SIZES)


def _fill(quantity: str, price: str, symbol: str = "XAUUSD", fees: str = "0") -> Fill:
    """A fill with SIGNED quantity: positive bought, negative sold."""
    return Fill(
        order_id="o1",
        client_order_id="c1",
        symbol=symbol,
        quantity=Decimal(quantity),
        price=Decimal(price),
        fees=Decimal(fees),
        ts=_TS,
    )


class TestOpeningAndAdding:
    def test_first_fill_opens_position_at_its_own_price(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("2", "2000.00"))

        assert portfolio.position_quantity("XAUUSD") == Decimal(2)
        assert portfolio.positions()["XAUUSD"].avg_price == Decimal("2000.00")
        assert portfolio.realised_pnl == Decimal(0)

    def test_adding_weights_the_average_price_by_size(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("2", "2000.00"))
        portfolio.apply_fill(_fill("1", "2030.00"))

        # (2 x 2000.00 + 1 x 2030.00) / 3 = 6030.00 / 3 = 2010.00
        assert portfolio.position_quantity("XAUUSD") == Decimal(3)
        assert portfolio.positions()["XAUUSD"].avg_price == Decimal("2010.00")
        assert portfolio.realised_pnl == Decimal(0)

    def test_adding_to_a_short_weights_the_average_the_same_way(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("-2", "2000.00"))
        portfolio.apply_fill(_fill("-1", "2030.00"))

        # (-2 x 2000.00 + -1 x 2030.00) / -3 = -6030.00 / -3 = 2010.00
        assert portfolio.position_quantity("XAUUSD") == Decimal(-3)
        assert portfolio.positions()["XAUUSD"].avg_price == Decimal("2010.00")


class TestClosing:
    def test_partial_close_realises_only_the_closed_lots(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("3", "2010.00"))
        portfolio.apply_fill(_fill("-1", "2050.00"))

        # 1 lot x 100 x (2050.00 - 2010.00) = 4000.00
        assert portfolio.realised_pnl == Decimal("4000.00")
        assert portfolio.position_quantity("XAUUSD") == Decimal(2)
        # the lots still open were opened at the same average as before
        assert portfolio.positions()["XAUUSD"].avg_price == Decimal("2010.00")

    def test_full_close_removes_the_position(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("2", "2000.00"))
        portfolio.apply_fill(_fill("-2", "1990.00"))

        # 2 lots x 100 x (1990.00 - 2000.00) = -2000.00
        assert portfolio.realised_pnl == Decimal("-2000.00")
        assert portfolio.position_quantity("XAUUSD") == Decimal(0)
        assert portfolio.positions() == {}
        assert portfolio.unrealised_pnl == Decimal(0)

    def test_closing_a_short_profits_when_price_falls(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("-2", "2000.00"))
        portfolio.apply_fill(_fill("2", "1950.00"))

        # short: 2 lots x 100 x (2000.00 - 1950.00) = +10000.00
        assert portfolio.realised_pnl == Decimal("10000.00")
        assert portfolio.position_quantity("XAUUSD") == Decimal(0)

    def test_flip_realises_the_old_position_and_opens_the_rest_at_this_price(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("1", "2000.00"))
        portfolio.apply_fill(_fill("-3", "2100.00"))

        # closes 1 lot: 1 x 100 x (2100.00 - 2000.00) = +10000.00
        assert portfolio.realised_pnl == Decimal("10000.00")
        # the other 2 lots are a new short, opened at the price they traded at
        assert portfolio.position_quantity("XAUUSD") == Decimal(-2)
        assert portfolio.positions()["XAUUSD"].avg_price == Decimal("2100.00")


class TestMarkingAndEquity:
    def test_unrealised_pnl_follows_the_mark_price(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("2", "2000.00"))
        portfolio.mark("XAUUSD", Decimal("2010.00"))

        # 2 lots x 100 x (2010.00 - 2000.00) = 2000.00
        assert portfolio.unrealised_pnl == Decimal("2000.00")

    def test_a_short_gains_when_the_mark_falls(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("-2", "2000.00"))
        portfolio.mark("XAUUSD", Decimal("1950.00"))

        # -2 lots x 100 x (1950.00 - 2000.00) = +10000.00
        assert portfolio.unrealised_pnl == Decimal("10000.00")

    def test_an_unmarked_position_is_valued_at_the_price_it_filled_at(self) -> None:
        """A fill records its own price as the mark, so there is never an
        open position with no price to value it at."""
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("2", "2000.00"))

        assert portfolio.unrealised_pnl == Decimal(0)

    def test_equity_is_balance_plus_open_positions(self) -> None:
        portfolio = _portfolio("100000.00")
        portfolio.apply_fill(_fill("1", "2000.00"))
        portfolio.apply_fill(_fill("-1", "2010.00"))  # realises 1 x 100 x 10.00 = 1000.00
        portfolio.apply_fill(_fill("1", "2010.00"))  # opens again
        portfolio.mark("XAUUSD", Decimal("2015.00"))  # 1 x 100 x 5.00 = 500.00 unrealised

        assert portfolio.realised_pnl == Decimal("1000.00")
        assert portfolio.balance == Decimal("101000.00")
        assert portfolio.unrealised_pnl == Decimal("500.00")
        assert portfolio.equity == Decimal("101500.00")

    def test_marking_a_symbol_does_not_move_another_symbols_position(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("1", "2000.00", symbol="XAUUSD"))
        portfolio.apply_fill(_fill("1", "1.1000", symbol="EURUSD"))
        portfolio.mark("EURUSD", Decimal("1.1050"))

        # EURUSD only: 1 lot x 100000 x 0.0050 = 500.00
        assert portfolio.unrealised_pnl == Decimal("500.00")


class TestFees:
    def test_fees_come_straight_off_realised_pnl(self) -> None:
        portfolio = _portfolio("100000.00")
        portfolio.apply_fill(_fill("1", "2000.00", fees="7.50"))

        assert portfolio.realised_pnl == Decimal("-7.50")
        assert portfolio.balance == Decimal("99992.50")
        assert portfolio.equity == Decimal("99992.50")


class TestDecimalDiscipline:
    def test_pnl_is_exact_where_a_float_would_not_be(self) -> None:
        """0.0005 has no exact float representation, so this same
        calculation in floats gives 50.000000000000114. Every value in the
        accounting path is Decimal precisely so that a to-the-cent
        comparison means what it says."""
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("1", "1.1000", symbol="EURUSD"))
        portfolio.mark("EURUSD", Decimal("1.1005"))

        # 1 lot x 100000 x 0.0005 = 50.00, exactly
        assert portfolio.unrealised_pnl == Decimal("50.00")

    def test_a_position_whose_average_price_does_not_divide_evenly_stays_exact(self) -> None:
        """1 lot at 2000.00 and 2 at 2001.00 average 6002/3, which has no
        finite decimal expansion. An average price is therefore a rounded
        number, and P&L computed through one inherits the rounding. The
        ledger holds total cost instead, so this arithmetic is exact."""
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("1", "2000.00"))
        portfolio.apply_fill(_fill("2", "2001.00"))
        portfolio.mark("XAUUSD", Decimal("2005.00"))

        # 3 x 100 x 2005.00 - 100 x (1 x 2000.00 + 2 x 2001.00)
        #   = 601500.00 - 600200.00 = 1300.00
        assert portfolio.unrealised_pnl == Decimal("1300.00")

    def test_float_starting_balance_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="Decimal"):
            Portfolio(starting_balance=100000.0, contract_sizes=CONTRACT_SIZES)  # type: ignore[arg-type]

    def test_float_contract_size_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="Decimal"):
            Portfolio(starting_balance=Decimal(0), contract_sizes={"XAUUSD": 100.0})  # type: ignore[dict-item]

    def test_float_mark_price_is_rejected(self) -> None:
        portfolio = _portfolio()
        with pytest.raises(TypeError, match="Decimal"):
            portfolio.mark("XAUUSD", 2000.0)  # type: ignore[arg-type]


class TestContractSizeConfiguration:
    def test_a_symbol_with_no_configured_contract_size_raises(self) -> None:
        """There is deliberately no default multiplier: a wrong one scales
        every P&L figure and nothing else would notice."""
        portfolio = _portfolio()
        with pytest.raises(KeyError, match="no contract size configured"):
            portfolio.apply_fill(_fill("1", "5000.00", symbol="NAS100"))


class TestPositionType:
    def test_position_is_immutable(self) -> None:
        position = Position(symbol="XAUUSD", quantity=Decimal(1), cost=Decimal("2000.00"))
        with pytest.raises(FrozenInstanceError):
            position.quantity = Decimal(2)

    def test_avg_price_is_derived_from_cost_for_reporting(self) -> None:
        """Reading only -- this divides, and nothing in the accounting
        path goes through it."""
        position = Position(symbol="XAUUSD", quantity=Decimal(3), cost=Decimal("6030.00"))
        assert position.avg_price == Decimal("2010.00")

    def test_a_shorts_quantity_and_cost_are_both_negative(self) -> None:
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("-2", "2000.00"))
        position = portfolio.positions()["XAUUSD"]

        assert position.quantity == Decimal(-2)
        assert position.cost == Decimal("-4000.00")
        assert position.avg_price == Decimal("2000.00")

    def test_positions_mapping_is_a_copy(self) -> None:
        """Handing out the live dict would let a strategy edit the book it
        was only meant to read."""
        portfolio = _portfolio()
        portfolio.apply_fill(_fill("1", "2000.00"))
        snapshot = portfolio.positions()
        del snapshot["XAUUSD"]

        assert portfolio.position_quantity("XAUUSD") == Decimal(1)
