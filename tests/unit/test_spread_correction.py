"""The 3c.2 spread-correction rules, approved 2026-11-20 (docs/state.md, 3c.2
"Fit and out-of-sample validation").

Every expected value here is worked by hand in the comment beside it. Times are
whole microseconds since the epoch, spreads whole points -- the units the
analysis script feeds in.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
S = 1_000_000  # one second in microseconds
MIN = 60 * S
B = 1_000_000 * S  # an arbitrary boundary instant


@pytest.fixture
def sc(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO))
    import spread_correction  # noqa: PLC0415 -- needs REPO on sys.path first

    return spread_correction


# --- nearest rank: sort, take the value at rank ceil(pct/100 * N) ------------


def test_nearest_rank_ten_values(sc):
    # N = 10: rank ceil(0.9 * 10) = 9 -> the 9th smallest.
    assert sc.nearest_rank(list(range(1, 11)), 90) == 9


def test_nearest_rank_rounds_the_rank_up(sc):
    # N = 11: 0.9 * 11 = 9.9 -> rank 10.
    assert sc.nearest_rank(list(range(1, 12)), 90) == 10


def test_nearest_rank_never_interpolates(sc):
    # N = 2: rank ceil(1.8) = 2 -> 10. Interpolation would give 9, a value
    # never observed.
    assert sc.nearest_rank([0, 10], 90) == 10


def test_nearest_rank_sorts_and_keeps_ties(sc):
    # Sorted 1,5,5,5; rank ceil(3.6) = 4 -> 5.
    assert sc.nearest_rank([5, 1, 5, 5], 90) == 5


def test_nearest_rank_does_not_reorder_its_input(sc):
    values = [3, 1, 2]
    sc.nearest_rank(values, 90)
    assert values == [3, 1, 2]


def test_nearest_rank_works_on_fractions(sc):
    # Sorted -1/5, 1/3, 1/2; rank ceil(2.7) = 3 -> 1/2.
    assert sc.nearest_rank([Fraction(1, 2), Fraction(-1, 5), Fraction(1, 3)], 90) == Fraction(1, 2)


def test_nearest_rank_single_value_and_hundredth(sc):
    assert sc.nearest_rank([7], 90) == 7
    assert sc.nearest_rank([4, 9, 2], 100) == 9


@pytest.mark.parametrize("pct", [0, 101])
def test_nearest_rank_rejects_percentile_out_of_range(sc, pct):
    with pytest.raises(ValueError, match="percentile"):
        sc.nearest_rank([1, 2], pct)


def test_nearest_rank_rejects_no_values(sc):
    with pytest.raises(ValueError, match="no values"):
        sc.nearest_rank([], 90)


# --- the spread in force at a boundary ---------------------------------------


def test_boundary_uses_last_tick_before(sc):
    times = [B - 60 * S, B - 10 * S, B + 5 * S]
    assert sc.boundary_spread(times, [3, 5, 9], B, sc.GAP_US) == (5, False)


def test_a_tick_exactly_at_the_boundary_is_in_force(sc):
    times = [B - 10 * S, B]
    assert sc.boundary_spread(times, [5, 7], B, sc.GAP_US) == (7, False)


def test_after_a_gap_the_first_tick_at_or_after_is_used(sc):
    # Nothing in the 5 minutes before B: the 6-minutes-old quote is stale.
    times = [B - 6 * MIN, B + 30 * S]
    assert sc.boundary_spread(times, [4, 12], B, sc.GAP_US) == (12, True)


def test_a_tick_exactly_five_minutes_before_is_not_a_gap(sc):
    # The window [B - 5 min, B) includes its start.
    times = [B - 5 * MIN, B + 30 * S]
    assert sc.boundary_spread(times, [4, 12], B, sc.GAP_US) == (4, False)


def test_a_tick_one_microsecond_older_is_a_gap(sc):
    times = [B - 5 * MIN - 1, B + 30 * S]
    assert sc.boundary_spread(times, [4, 12], B, sc.GAP_US) == (12, True)


def test_no_tick_before_at_all_is_a_gap(sc):
    # The Sunday open: the week's file starts after the boundary.
    times = [B + 2 * S, B + 3 * S]
    assert sc.boundary_spread(times, [20, 15], B, sc.GAP_US) == (20, True)


def test_a_gap_with_nothing_after_gives_no_observation(sc):
    times = [B - 10 * MIN]
    assert sc.boundary_spread(times, [4], B, sc.GAP_US) is None
    assert sc.boundary_spread([], [], B, sc.GAP_US) is None


# --- the bar minimum, over [open, open + 15 min) -----------------------------


def test_bar_minimum_includes_open_excludes_end(sc):
    end = B + 15 * MIN
    times = [B - S, B, B + MIN, end - 1, end]
    spreads = [1, 6, 4, 5, 2]
    # In range: 6, 4, 5 -> 4. The 1 before and the 2 at `end` are outside.
    assert sc.bar_minimum(times, spreads, B, end) == 4


def test_bar_minimum_of_an_empty_bar_is_none(sc):
    assert sc.bar_minimum([B - S], [3], B, B + 15 * MIN) is None


# --- excesses -----------------------------------------------------------------


def test_excess_points_can_be_negative(sc):
    # The open boundary's tick lies before the bar, so can be below its minimum.
    assert sc.excess_points(8, 5) == 3
    assert sc.excess_points(4, 5) == -1


def test_excess_ratio_is_exact(sc):
    assert sc.excess_ratio(8, 5) == Fraction(3, 5)
    assert sc.excess_ratio(4, 5) == Fraction(-1, 5)


def test_excess_ratio_of_a_zero_minimum_is_none(sc):
    assert sc.excess_ratio(3, 0) is None


# --- coverage: charged = max(minimum, minimum with correction) ---------------


def test_points_coverage(sc):
    # Charge 5 + 2 = 7.
    assert sc.covered(7, 5, 2, "points")
    assert not sc.covered(8, 5, 2, "points")


def test_negative_points_correction_never_charges_below_minimum(sc):
    # Charge max(5, 5 - 3) = 5.
    assert sc.covered(5, 5, -3, "points")
    assert not sc.covered(6, 5, -3, "points")


def test_percentage_coverage(sc):
    # Charge 10 * (1 + 1/5) = 12, exactly -- no floating point.
    assert sc.covered(12, 10, Fraction(1, 5), "percentage")
    assert not sc.covered(13, 10, Fraction(1, 5), "percentage")


def test_negative_percentage_correction_never_charges_below_minimum(sc):
    assert sc.covered(10, 10, Fraction(-1, 2), "percentage")
    assert not sc.covered(11, 10, Fraction(-1, 2), "percentage")


def test_percentage_of_a_zero_minimum_charges_zero(sc):
    # The structural weakness for EURUSD: any correction times zero is zero.
    assert sc.covered(0, 0, Fraction(5), "percentage")
    assert not sc.covered(1, 0, Fraction(5), "percentage")


def test_points_correction_on_a_zero_minimum_still_charges(sc):
    assert sc.covered(2, 0, 2, "points")


def test_unknown_form_is_refused(sc):
    with pytest.raises(ValueError, match="form"):
        sc.covered(1, 1, 0, "pips")


# --- fitting a table, with the thin-cell fallback ----------------------------


def _obs(n, minimum, excess):
    return [(minimum + excess, minimum)] * n


def test_fit_table_points_per_hour_and_fallback(sc):
    # Hour 3: 200 bars, 400 observations: 360 at +1 and 40 at +9.
    #   rank ceil(0.9 * 400) = 360 -> +1.
    # Hour 4: 199 bars -> thin, falls back to the instrument-wide value.
    #   Pooled: 360 at +1, 40 at +9, 398 at +2 = 798; rank ceil(718.2) = 719.
    #   Sorted: 360 ones (ranks 1-360), 398 twos (361-758) -> +2.
    cells = {
        3: _obs(360, 5, 1) + _obs(40, 5, 9),
        4: _obs(398, 5, 2),
    }
    table, fallbacks = sc.fit_table(cells, {3: 200, 4: 199}, "points")
    assert table == {3: 1, 4: 2}
    assert fallbacks == {4}


def test_fit_table_percentage_skips_zero_minimums(sc):
    # Hour 0: 200 bars; 300 observations at minimum 10, excess 2 -> 1/5, and
    # 100 at minimum 0, which give no ratio. Only the 300 count: -> 1/5.
    cells = {0: _obs(300, 10, 2) + _obs(100, 0, 3)}
    table, fallbacks = sc.fit_table(cells, {0: 200}, "percentage")
    assert table == {0: Fraction(1, 5)}
    assert fallbacks == set()


def test_fit_table_percentage_cell_of_only_zero_minimums_falls_back(sc):
    cells = {0: _obs(400, 0, 1), 1: _obs(400, 4, 1)}
    table, fallbacks = sc.fit_table(cells, {0: 200, 1: 200}, "percentage")
    assert table == {0: Fraction(1, 4), 1: Fraction(1, 4)}
    assert fallbacks == {0}


# --- pass / fail, inclusive thresholds ---------------------------------------


def test_cell_at_exactly_85_percent_passes(sc):
    assert not sc.cell_fails(85, 100)
    assert not sc.cell_fails(17, 20)
    assert sc.cell_fails(84, 100)


def test_over_pessimistic_above_97_only(sc):
    assert not sc.over_pessimistic(97, 100)
    assert sc.over_pessimistic(98, 100)


def test_instrument_needs_both_conditions(sc):
    assert sc.instrument_passes(9, 10, 88, 100)  # exactly 90% of cells, 88%
    assert not sc.instrument_passes(8, 10, 95, 100)  # too few cells pass
    assert not sc.instrument_passes(10, 10, 87, 100)  # overall too low
    assert sc.instrument_passes(18, 20, 880, 1000)


@pytest.mark.parametrize("call", ["cell_fails", "over_pessimistic"])
def test_no_observations_cannot_be_judged(sc, call):
    with pytest.raises(ValueError, match="no observations"):
        getattr(sc, call)(0, 0)


def test_instrument_with_no_judged_cells_cannot_be_judged(sc):
    with pytest.raises(ValueError, match="no judged cells"):
        sc.instrument_passes(0, 0, 90, 100)


# --- choosing the form --------------------------------------------------------


def test_choose_form(sc):
    f = Fraction
    assert sc.choose_form(True, False, f(9), f(1)) == "points"
    assert sc.choose_form(False, True, f(1), f(9)) == "percentage"
    assert sc.choose_form(True, True, f(2), f(3)) == "points"
    assert sc.choose_form(True, True, f(3), f(2)) == "percentage"
    assert sc.choose_form(True, True, f(2), f(2)) == "points"
    assert sc.choose_form(False, False, f(1), f(2)) is None


# --- the charge itself --------------------------------------------------------


def test_charge_points_and_percentage(sc):
    assert sc.charge(5, 2, "points") == 7
    assert sc.charge(5, -3, "points") == 5
    # 7 * (1 + 1/2) = 21/2 points: kept exact, not rounded.
    assert sc.charge(7, Fraction(1, 2), "percentage") == Fraction(21, 2)
    assert sc.charge(0, Fraction(5), "percentage") == 0


# --- scoring a table against observations ------------------------------------


def test_score_counts_covered_per_hour(sc):
    # Hour 1, correction +2: charges 7; boundaries 7, 8, 6 -> 2 of 3.
    # Hour 2, correction 0: charge 4; boundaries 4, 4 -> 2 of 2.
    obs = {1: [(7, 5), (8, 5), (6, 5)], 2: [(4, 4), (4, 4)]}
    assert sc.score(obs, {1: 2, 2: 0}, "points") == {1: (2, 3), 2: (2, 2)}


def test_score_refuses_an_hour_missing_from_the_table(sc):
    # A test hour the fit never saw must have been given a fallback by
    # fit_table; reaching score without one is a bug, not a zero charge.
    with pytest.raises(KeyError):
        sc.score({9: [(1, 1)]}, {1: 0}, "points")


def test_fit_table_gives_a_test_only_hour_the_fallback(sc):
    # Hour 7 has no fit bars at all (it appears only in the test period).
    cells = {3: _obs(400, 5, 1), 7: []}
    table, fallbacks = sc.fit_table(cells, {3: 200, 7: 0}, "points")
    assert table == {3: 1, 7: 1}
    assert fallbacks == {7}


# --- judging an instrument (operator decisions 6-8) ---------------------------


def test_judge_counts_fallback_cells_and_leaves_thin_cells_unjudged(sc):
    scores = {
        0: (90, 100),  # judged, passes
        1: (84, 100),  # judged, fails (below 85%)
        2: (99, 100),  # judged, passes, over-pessimistic (above 97%)
        3: (90, 100),  # judged, passes -- a FALLBACK cell, still judged
        4: (0, 99),  # 99 test bars -> unjudged, however bad
    }
    bars = {0: 100, 1: 100, 2: 100, 3: 100, 4: 99}
    v = sc.judge(scores, bars, fallbacks={3})
    assert v.judged == [0, 1, 2, 3]
    assert v.failed == [1]
    assert v.unjudged == [4]
    assert v.over_pessimistic == [2]
    assert v.fallback_judged == [3]
    # Overall over EVERY observation, unjudged cell included:
    # (90 + 84 + 99 + 90 + 0) / 499 = 363/499 = 72.7% -> below 88%.
    assert v.overall == (363, 499)
    assert not v.passes
    assert not v.too_many_unjudged


def test_judge_passes_with_exactly_90_percent_of_judged_cells(sc):
    scores = dict.fromkeys(range(9), (90, 100)) | {9: (80, 100)}
    v = sc.judge(scores, dict.fromkeys(range(10), 100), fallbacks=set())
    # 9 of 10 judged cells pass; overall (810 + 80) / 1000 = 89%.
    assert v.failed == [9]
    assert v.passes


def test_judge_flags_more_than_two_unjudged_cells(sc):
    scores = {0: (90, 100), 1: (5, 5), 2: (5, 5), 3: (5, 5)}
    bars = {0: 100, 1: 5, 2: 5, 3: 5}
    assert sc.judge(scores, bars, set()).too_many_unjudged
    del scores[3], bars[3]
    assert not sc.judge(scores, bars, set()).too_many_unjudged


# --- data integrity (definition 5) --------------------------------------------


def test_integrity_stops_above_one_percent_of_measured_bars(sc):
    assert sc.integrity_ok(100, 10_000)  # exactly 1%
    assert not sc.integrity_ok(101, 10_000)


# --- the hour structure must earn its place ------------------------------------


def test_hourly_preferred_only_with_strictly_fewer_failing_cells(sc):
    assert sc.prefer_hourly(hourly_failed=1, constant_failed=2)
    assert not sc.prefer_hourly(hourly_failed=2, constant_failed=2)
    assert not sc.prefer_hourly(hourly_failed=3, constant_failed=2)


# --- drift across single-year fits (definition 3) ------------------------------


def test_coverage_range_is_best_minus_worst(sc):
    # 90/100, 85/100, 93/100 -> 93% - 85% = 8 percentage points = 2/25.
    assert sc.coverage_range([(90, 100), (85, 100), (93, 100)]) == Fraction(2, 25)


def test_coverage_range_needs_two_years(sc):
    with pytest.raises(ValueError, match="at least two"):
        sc.coverage_range([(90, 100)])
