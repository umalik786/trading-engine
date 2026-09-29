# Current State

**Phase:** 1 — complete
**Last session:** 2026-09-28

## Decided recently

- Phase 1.3 (future-shuffle property test) complete and committed at
  `tests/properties/test_future_shuffle.py`. Hand-typed by the operator from a
  reviewed draft; Claude Code wrote the draft to a scratchpad outside the repo
  rather than into `tests/properties/`, preserving the CLAUDE.md rule. Claude Code
  raised the tension itself rather than silently resolving it.
- The clean indicator under test is the real `SimpleMovingAverage` from
  `engine.features.technical`, reached through a thin adapter with no logic of its
  own. An earlier draft used a fresh standalone moving average written inside the
  test file — rejected, because proving a 10-line class written in the test doesn't
  peek proves nothing about the shipped pipeline.
- `ReplayFeed` is deliberately not used to feed the indicators here. It reads from
  disk and cannot be handed a shuffled list, so bars are loaded once into a list and
  that list is what gets shuffled and fed. `ReplayFeed` has its own tests; the thing
  under test in this file is the feature pipeline.
- Constants split: `SHUFFLE_FROM` (where the shuffle starts), `RECORD_THROUGH`
  (how many snapshots are compared), `PERIOD` (indicator window). They were one
  constant, `SPLIT`, doing all three jobs.

## Found this session

- **`SPLIT` was overloaded and hid a failed break test.** With one constant serving
  as shuffle start, record count and boundary position, changing it to 900 moved all
  three together — so the first attempt to break the test deliberately passed when it
  should have failed. Neither Claude Code (which wrote the draft) nor the chat
  reviewer caught this; it surfaced only by trying to break the test. Splitting the
  constant fixed it.
- **The test catches order-sensitive leaks only.** The shuffle changes the order of
  future bars, not their contents. A leak reaching for something order-invariant —
  `max`, `min`, `sum` over a whole dataset — returns the same value either way and
  passes. This is a real limit on what phase 1 proves, recorded in the test's
  docstring.

## Verified, not assumed

The harness was proven able to fail, two independent ways:

1. Probe's slice reversed to look backward → leaky test red, clean stayed green.
   Proves it detects forward-looking specifically.
2. `SHUFFLE_FROM` moved to 900, past the recorded range → leaky test red, clean
   stayed green. Proves the boundary is what drives it.

Both reverted. Boundary values under normal settings: leaky bar 450 identical in both
runs (4468.3494), bar 451 first to differ (4468.8124 vs 4471.1652), no coincidental
matches among the 50 differing snapshots.

## Blocked on

- Nothing

## Next

- Phase 2: strategy protocol, `AlwaysLong` / `AlwaysFlat`, portfolio accounting,
  `SimBroker` with `ZeroCostModel`.
- Exit criterion: `AlwaysLong` matches buy-and-hold to the cent.
- Use Opus for this phase — `project-alignment.md` §8 flags phases 2 and 3 as the
  ones where being subtly wrong is most expensive.

## Carried-forward gaps (not blocking)

- `warmup()` reads a whole year file to return `n` bars (~2s, ~25MB at n=200).
- Full-history streaming ~52s wall time; phase 5 runs hundreds of backtests.
- Decimal context is process-global and mutable, not recorded in the run manifest —
  a determinism surface P5 doesn't currently cover.
- FTMO loss percentages still unverified placeholders; `rules_verified` deliberately
  unset so the profile keeps warning.
- FundedNext `rules_source` null.
- FTMO Forbidden Trading Practices page unread — before phase 7.
- §10 item 2 (does the broker preserve the order `comment` field) — needs a live order.
- Whether FTMO prohibits mixing manual and automated execution.
