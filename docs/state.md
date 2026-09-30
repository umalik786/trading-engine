# Current State

**Phase:** 2 — COMPLETE (2026-09-30)
**Last session:** 2026-09-30

## Phase 2 exit criterion — MET 2026-09-30

- `AlwaysLong` matched operator-computed buy-and-hold to the cent on two real XAUUSD
  M15 weeks: **5718.00** and **4740.00**. Both figures were computed independently in a
  spreadsheet before the engine was run, not read off it afterwards.
- **The 00:00-start fixture cannot distinguish the correct behaviour from the bug it
  exists to catch.** In `xauusd_m15_2025-02-05_2025-02-12.csv`, bar 2's open equals
  bar 1's close, so filling at the next bar's open and filling at the deciding bar's
  close give the identical entry price and the identical P&L. That fixture passes under
  either rule.
- **The 02:45-start fixture can.** There bar 1's close is 2851.10 and bar 2's open is
  2851.19, so the two rules diverge. Proven by registering the look-ahead figure
  4749.00: the test went red with difference exactly -9.00, which is
  1 lot x 100 x 0.09 — the gap between the two candidate entry prices, and nothing else.
- **Lesson: a fixture has to be checked for whether it can tell correct behaviour from
  the bug it exists to catch, not only for whether it passes.** Both fixtures pass.
  Only one of them is evidence. The green from the 00:00 fixture was indistinguishable
  from the green a look-ahead engine would have produced, and on its own it would have
  certified the accounting on a test that could not fail for the right reason.

## Decided this session (phase 2)

- Built: `Strategy` protocol, `AlwaysLong`, `AlwaysFlat`, `Portfolio`/`PortfolioView`,
  `Broker` protocol, `SimBroker`, `CostModel` protocol, `ZeroCostModel`, and
  `config/instruments.yaml` with its loader.
- **No `core/engine.py` was written, deliberately.** The bar loop lives in
  `tests/golden/harness.py` instead. Reason: a backtest fills a queued order when the
  next bar arrives (`SimBroker.fill_pending`), whereas live fills are discovered by
  polling deal history against a durable intent log (Appendix A.4/A.5/A.7). An
  orchestrator written today around `fill_pending(bar)` would work for one wiring
  only, which is the separate backtester P1 forbids. Delete the harness rather than
  extend it when the real orchestrator arrives.
- **`Fill.quantity` is signed** — positive bought, negative sold. §2.1's `Fill` has no
  `side` field, so the sign is the only place direction can live. `SimBroker` writes
  it from the order's side; a live adapter must do the same.
- **`client_order_id` is composed as text, not `hash()`.** §5.2 says
  `hash(strategy_name, symbol, bar.ts_close, intent_index)`, but Python's `hash()` on
  strings is salted per process, so it would give different ids on identical runs and
  break determinism outright. Same four inputs, joined with colons.
- **SimBroker and the engine share one `Portfolio`.** In a backtest there is no second
  system that could disagree, so separate copies would invent a drift that cannot
  occur here while hiding the one that can. §5.3 reconciliation is the live answer.
- Contract sizes are config (`config/instruments.yaml`), with no default: an unknown
  symbol raises at the first fill rather than guessing a multiplier that would scale
  every P&L figure silently. Verified 2026-09-11 from `symbol_info()`, source recorded
  in the file.
- **FTMO position mode: HEDGING** (`margin_mode` 2). Verified 2026-09-29 via
  `check_margin_mode.py` reading `account_info()` on FTMO-Demo, FTMO Global Markets
  Ltd. Support chat said the same; recorded as supporting evidence only — the
  account's own report is the source.
- **FundedNext position mode: HEDGING** (`margin_mode` 2). Verified 2026-09-29 via
  `check_margin_mode.py` reading `account_info()` on FundedNext-Server 3, FundedNext
  Ltd. Both candidate venues are therefore hedging; netting is still built in phase 3
  for venue independence and for the cross-convention property test.
- **Position mode is venue configuration, never an engine assumption.** Both
  conventions get built at the start of phase 3, together: netting (average cost, one
  net position per symbol) and hedging (per-ticket, each fill its own position). Built
  together because persisted state differs in shape between them, and adding a field to
  persisted state later means migrating a running system — the same reasoning that put
  both risk floor modes in at once. The engine never deliberately hedges: one direction
  per symbol under either convention. Close order under hedging is oldest ticket first.
  The adapter asserts the configured mode against `account_info()` at startup and halts
  on mismatch. Property test: both conventions produce identical equity and total P&L
  for any fill sequence.
- **Partial-close cost split: decided.** Per-ticket accounting in phase 3 removes the
  division for hedging venues, which both candidate venues are. Average cost stays for
  netting, where the division remains and is bounded as described under "Fixed after
  review" — the rounding cancels in equity and can only move the realised/unrealised
  split.
- **FTMO trial accounts expire.** "Unlimited free trials" means unlimited *new* trials,
  not an account that lasts indefinitely. Data re-extraction therefore needs a live
  trial at the time it runs and expects a new login each time; extraction credentials
  are not stable between runs.

## Fixed after review (phase 2)

- **Order sizing counts pending orders, not just filled lots.** Found in chat-side review.
  With one instrument the fault is invisible — each bar fills the previous bar's order
  before the strategy is asked again. With two instruments interleaved, a bar for one
  symbol cannot fill the other's pending order, so the book looked flat and the whole
  position was ordered again under a new `client_order_id` — a new intent, not a retry,
  so §5.2 idempotency did not catch it. Observed before the fix: 2 orders, 2 fills,
  then the oversized position provoked corrective sells and invented 2000.00 of
  realised P&L from a strategy that never sells.
- **The ledger stores total cost, not average price.** Found in chat-side review. A
  weighted average divides, and `Decimal` rounds a non-terminating quotient at context
  precision: 1 lot at 2000.00 plus 2 at 2001.00, marked 2005.00, reported
  1299.999999999999999999999900 instead of 1300.00. `Position` now holds signed
  `cost` (sum of lots x price) and P&L is add/subtract/multiply only.
  `Position.avg_price` survives as a derived property for reporting, explicitly out of
  the accounting path.
- One division remains, on partial closes only: allocating cost basis between lots
  closed and lots kept is proportional. Its rounding cancels in equity, because the
  position keeps `cost` minus exactly the share that was removed, so only the
  realised/unrealised split can differ in the last digits. FIFO tranches would remove
  even that, at the cost of changing what average price means — not taken, since it
  changes an accounting convention rather than fixing an error.
  Superseded for hedging venues: per-ticket accounting in phase 3 removes this
  division — see the position-mode decision above.

## Verified, not assumed (phase 2)

Three deliberate breaks, each reverted:

1. `ZeroCostModel.fill_price` returning `bar.close` instead of `bar.open` → 4 broker
   tests red, including both next-bar-open tests.
2. Dropping `contract_size` from the realised-P&L line → 5 portfolio tests red.
3. `AlwaysFlat` targeting 1 lot instead of 0 → all 3 AlwaysFlat tests red.

Harness run over a four-bar XAUUSD series spanning a weekend: one order, decided at
bar 1's close, filled at bar 2's open (2002.00), held across the gap, marked at bar 4's
close (2015.50). 1 x 100 x 13.50 = 1350.00, which is what it reported.

## Blocked on (phase 2)

- Nothing. The exit criterion was the last item and is met — see the section at the top
  of this file. Two cases are registered in
  `tests/golden/test_always_long_vs_buy_and_hold.py`. Nothing in this repository
  computes buy-and-hold; both expected figures came from outside it, by design.

## Decided previously (phase 1)

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

## Found in phase 1

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

## Verified, not assumed (phase 1)

The harness was proven able to fail, two independent ways:

1. Probe's slice reversed to look backward → leaky test red, clean stayed green.
   Proves it detects forward-looking specifically.
2. `SHUFFLE_FROM` moved to 900, past the recorded range → leaky test red, clean
   stayed green. Proves the boundary is what drives it.

Both reverted. Boundary values under normal settings: leaky bar 450 identical in both
runs (4468.3494), bar 451 first to differ (4468.8124 vs 4471.1652), no coincidental
matches among the 50 differing snapshots.

## Open items

- Nothing open.

## Next

- Phase 3, starting with both position conventions — netting and hedging — per the
  position-mode decision above. They go in together because persisted state differs in
  shape between them.
- Then the cost model and sizer. The exit criterion is the same comparison minus a cost
  figure derivable by hand; the harness already takes a `cost_model` argument. Check it
  against the 02:45-start fixture, which is the one that can fail for the right reason.
  Watch for spread double-counting: charged at entry and again when marking the open
  position. A single round-number cost figure passes either way. The phase 3
  exit-criterion fixtures must be designed to separate the two, e.g. two fixtures with
  different bar counts, with the operator's hand-computed cost figure for each.

## Carried-forward gaps (not blocking)

- **The real orchestrator (`core/engine.py`) must be designed before phase 4.** The
  risk gate sits inside the bar loop — it vets each order between sizing and
  submission — so phase 4 cannot be built without deciding where that loop lives. The
  harness in `tests/golden/harness.py` must not be grown into it: a loop that only
  works against `SimBroker.fill_pending(bar)` is a second backtester, which is what P1
  forbids. Design the orchestrator and the live fill path together, then delete the
  harness.
- **Content-perturbation property test not written — before phase 5, operator-written.**
  The future-shuffle test catches order-sensitive leaks only (see "Found in phase 1").
  Perturbing the *contents* of the post-boundary bars, rather than their order, would
  also catch order-invariant leaks — `max`, `min`, `sum` over a whole dataset return
  the same value under a shuffle and pass today. Scale open/high/low/close together or
  `Bar` validation rejects the perturbed bars.
- No decision log is written during a run. `DecisionRecord` exists from phase 0 but
  nothing populates it; the harness does not, since it is not the orchestrator. It
  needs wiring wherever the real bar loop ends up.
- `financing()` is defined on `CostModel` and returns zero, but nothing calls it —
  there is no per-bar financing step in the loop yet. Phase 3.
- Nothing validates `strategy.required_features` against what the feature pipeline
  actually provides. §2.4 says the engine should check this at startup; there is no
  engine to do it in yet, and both reference strategies declare no features.
- Multi-symbol runs are untested end to end. The accounting is per-symbol throughout
  and the harness loop handles a list of targets, but every test uses one instrument.
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
