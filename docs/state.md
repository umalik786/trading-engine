# Current State

**Last session:** 2026-11-19 (proposal (c) applied); before that 2026-11-17
**Phase:** 3 in progress. 3a (spread, commission) complete 2026-10-01; 3b (financing)
complete 2026-10-02. **3c is next** (slippage, the C.1 spread model, a real sizer).
Phase 2 complete 2026-09-30.

## Session 2026-11-17 in brief

No phase work. The day went on recovering the environment and the data, and on what the
data turned out to contain. Details in the sections below.

- **Laptop replaced.** Repositories recovered from GitHub; nothing committed was lost.
  Market data in `C:\trading\data` was lost (it lives outside the repo by design).
- **Data re-extracted** on a fresh FTMO trial, by the trial-session plan below: M15, H1
  and H4 bars for all five instruments, **M1 added** (never extracted before), and a
  **tick sample** for 2026-10-19 to 2026-11-14. Bid basis confirmed (`chart_mode` 0
  on all five); triple-swap weekday read (indices Friday, the rest Wednesday).
- **Fix (a):** the extractor no longer stores the bar still forming at extraction time.
  2026 re-extracted.
- **Fix (b):** FTMO index history before 2021-09-15 (M1, M15) and 2021-01-22 (H1, H4)
  is daily, then hourly, bars filed under the wrong timeframe. Raw files untouched;
  `bars_genuine_from` in `config/instruments.yaml` now tells ReplayFeed not to read it,
  and `check_bar_spacing.py` checks every series month by month.
- **Backups**, Google Drive, each compared at both ends:
  `G:\My Drive\trading-data-backup\2026-11-17`, `…\2026-11-17b` (after fix a),
  `…\2026-11-17c` (after M1).

## Blocked

Nothing blocks the next step. Waiting on the operator or on a live terminal:

- **Needs a held position on a live terminal:** whether "Wednesday" triple swap means the
  rollover ending Wednesday or the one beginning it.
- **Needs a live order:** whether the broker keeps the order `comment` field (§10 item 2).
- FTMO trial logins expire, so the next extraction needs a new trial.

## Next, in order

1. **Phase 3c:** slippage, the statistical spread model of Appendix C.1, and a real sizer.
   Plan and decisions approved 2026-11-19 ("Phase 3c plan and decisions"); starts with
   3c.0, the spread-semantics analysis.
2. **Position conventions:** netting and hedging, before phase 4.
3. **Orchestrator design** (`core/engine.py`), before phase 4. Includes making
   `bars_genuine_from` required.

Proposal (c), the FTMO swap config, was applied 2026-11-19 — see "Proposals from the
session".

Detail on each is under "Next" further down.

## Machine replaced, 2026-11-17

- Laptop replaced. Repositories recovered from GitHub; nothing committed was lost,
  including the golden-test fixtures under `tests/golden/fixtures/`.
- **Market data in `C:\trading\data` was lost** — it sits outside the repo by design,
  so GitHub held no copy. It must be re-extracted before any backtest beyond the
  committed fixtures. Re-extraction needs a live FTMO trial and a new login (see
  "FTMO trial accounts expire" under phase 2).
- **Until then, the two future-shuffle property tests fail** (292 passed, 2 failed on
  2026-11-17): `tests/properties/test_future_shuffle.py` reads 1000 bars from 2026-01-01
  out of `C:\trading\data`, and gets none. Expected, not a regression.
- **New rule: back up `C:\trading\data` off-machine after every extraction.** Keeping
  data outside the repo protects it from `git clean`, not from losing the machine.

## Settled, 2026-11-17

- **Extraction keeps the per-bar spread column.** `extract_mt5_data.py:237` stores
  MT5's `spread` field as an integer point count on every bar, and the 3a fixtures carry
  it. Still open, and relevant to C.1: MT5 does not clearly document whether that figure
  is the spread at one instant of the bar or the bar's minimum. If it is the minimum, a
  distribution built from it understates the pessimistic tail C.1 asks for. The tick
  sample (trial-session plan, step 4) can answer this by comparing each bar's stored
  spread with the ask - bid of the ticks inside it.

## Phase 3b — financing, COMPLETE 2026-10-02

Overnight swap behind the `CostModel` interface. Values, formula shapes, the
server clock and the triple weekday are all configuration.

- **The rollover is midnight on the server's clock**, derived from the verified
  server-timezone rule rather than any constant. In February that is 22:00 UTC; in
  July it is 21:00. A hardcoded hour would be right for about four months a year.
- **The clock is promoted into the engine.** `ftmo_server_utc_offset` lived in
  `extract_mt5_data.py`, a root-level script. The arithmetic now lives in
  `engine/core/clock.py` and the script imports it, so there is one definition.
  The server-timezone market-fact tests still pass unchanged, which is what
  confirms the move changed no behaviour.
- **Two clock shapes**, because a server clock is venue configuration: `iana` (a
  real, nameable zone — a retail broker) and `dst_switched_offsets` (fixed winter
  and summer offsets switching on another region's DST calendar — FTMO is +2/+3 on
  `America/New_York`, which matches no IANA zone). **Kept separate from the §6.5
  accounting-day clock, deliberately**: FTMO's accounting day runs in Prague on the
  European calendar, and the two differ by two hours for a few weeks each spring and
  autumn. Merging them would be right most of the year and wrong exactly when it
  mattered.
- **Order of operations per bar, which is what makes the size at each rollover exact
  rather than approximate.** Rollovers land on bar boundaries and fills land on bar
  opens, so one charge per bar would have to guess which side of the fill a boundary
  rollover fell on. Two windows do not guess:
  1. charge rollovers in `(previous bar's close, this bar's open]` on the position as
     held BEFORE this bar's fills
  2. apply fills at the bar's open
  3. charge rollovers in `(this bar's open, this bar's close]` on the position AFTER
     the fills

  Consequences, both now unit-tested: a position **opened** at exactly a rollover
  instant is **not** charged for it; a position **closed** at exactly a rollover
  instant **is**. You owe for the night you held and not for one that ended as you
  came in.
- **Signed rates, and the credit path is real.** EURUSD and XAGUSD shorts currently
  earn +0.35 and +0.5 points on this venue. A mechanism that treated financing as
  always a cost would be wrong today, not hypothetically.
- **Financing accrues on the open position, so it moves equity but not balance**, and
  lands on balance only when the position closes — which is what MT5 does. This is
  why `realised_pnl` in the golden tests is still only the commission. The
  distinction is load-bearing: §6.5.3 records whether each firm's daily loss limit
  watches equity or closed balance, so it decides whether financing counts against
  the limit yet.
- **Shapes implemented:** `points` (MT5 mode 1, what FTMO uses on all five),
  `currency_per_lot` (mode 4, the common retail shape) and `disabled` (mode 0).
  Modes 2, 3, 5, 6, 7 and 8 raise by name: the interest modes need a day-count
  convention that is another unverified external fact, and the reopen modes alter the
  position's open price rather than charging money.
- **The points conversion is confirmed twice over.** Money per lot per night is
  `rate x point x contract_size`, and the 2026-09-11 run shows that
  `point x contract_size` equals the broker's own `tick_value` for all five
  instruments. Two independent routes to the same figure.
- **Provenance is now per section.** The swap rates *are* verified (2026-09-11, from
  `symbol_info()`); `price_basis`, commission and the triple weekday are not. One
  `rules_verified` per file would have forced one of those to be mislabelled.
  Financing also carries a **30-day** staleness threshold rather than 90, because
  brokers revise swap rates far more often than rulebooks change.
- **`quote_currency` and `account_currency` added.** All five instruments are
  USD-quoted against a USD account, and `ConfiguredCostModel` now raises at
  construction on any mismatch rather than converting at an unverified FX rate — the
  assumption made checkable instead of written in a docstring.
- **Spec v3.9:** `CostModel.financing` takes an explicit half-open window instead of
  a `Bar`. A bar cannot express the question, because whether a rollover happened
  depends on where time was before it.
- **`Position` gains `opened_at` and `financing_accrued`.** The first is what makes
  "was it open at that instant" answerable; the position-conventions step will need
  it too, for closing the oldest ticket first.

### Exit criterion — MET 2026-10-02

`AlwaysLong` and `AlwaysShort` matched operator-computed figures to the cent with
spread, commission and financing all applied: **2580.50** and **-3060.50**. Both
computed by hand before the engine was run, and the engine's own figures were withheld
from the failure message so they could not be transcribed instead of derived.

The move from the 3a figures is exactly the financing: 3078.50 - 498.00 = 2580.50 for
the long, and -3135.50 + 75.00 = -3060.50 for the short. Six nights at -83.00 and
+12.50 respectively. The short's figure is the one that exercises the credit path,
since its rate is positive -- a mechanism that treated financing as always a cost
would have been wrong on that case alone while the long still passed.

The test profile uses a **Thursday** triple day, because the fixture's only
Wednesday-ending rollover falls before the fill and a Wednesday triple would therefore
never be charged. Rollovers crossed and nights charged are listed in that test's
docstring.

### Breaks run, 2026-10-02 — every move predicted before running, every one exact

Per night on one lot: long -83.00, short +12.50. Six nights charged at baseline.

| Break | Nights | Long | Short | Caught by |
|---|---|---|---|---|
| Wednesday rollover charged though position not open | +1 | **0.00** | **0.00** | unit tests only -- see below |
| Weekends charged | +2 | **-166.00** | **+25.00** | golden, both cases |
| Triple day ignored | -2 | **+166.00** | **-25.00** | golden, both cases |
| Long and short rates swapped | — | **+573.00** | **-573.00** | golden, both cases |
| Sign dropped (credit charged as a cost) | — | **0.00** | **-150.00** | golden, short only |
| "Day beginning" labelling | -2 | **+166.00** | **-25.00** | golden, both cases |

Three findings that matter more than the arithmetic:

- **The golden test cannot catch the first break at all.** Disabling the cost model's
  `opened_at` guard moved neither figure, because the engine loop's two-window ordering
  independently prevents the charge: the pre-fill window is evaluated while the book is
  still flat, so `financing()` is never even called for that rollover. Two mechanisms
  protect the same rule and the loop's fires first. Only two unit tests in
  `test_financing.py` failed. That is the argument for having both -- and a warning
  that an end-to-end figure can be silent about a rule it happens to satisfy twice.
- **Sign dropped is invisible on the long**, whose rate is already negative. Only the
  short catches it. The same single-strategy blindness as 3a's breaks 1 and 3, now on
  a third mechanism: one reference strategy is never enough to cover a cost model.
- **"Triple day ignored" and "day beginning labelling" are indistinguishable by the
  figure.** Both net to -2 nights and produce identical totals, by different routes:
  the labelling break turns Thursday's triple into a Friday single (-2), Friday's
  single into a Saturday zero (-1), and Sunday's zero into a Monday single (+1). The
  unit tests do separate them -- 4 failures for the triple-day break, all in
  `TestWeekendsAndTripleDay`, against 7 for the labelling break including both
  `TestDayEndingLabel` clock tests. So the failure signature identifies the bug where
  the number cannot.

Absence of break residue verified by SHA-256 of all 39 files under `src/` against a
snapshot taken before the first break -- identical. Every one of the six breaks was in
`src/`, unlike 3a's break 5 which had to live in the harness.

## Phase 3a exit criterion — MET 2026-10-01

Scope was spread and commission mechanics only. Financing, slippage, the statistical
spread model of Appendix C.1 and a real sizer are 3b/3c; the position conventions are
the step after. Slippage is zero but wired and exercised, not absent.

- `AlwaysLong` and `AlwaysShort` matched operator-computed figures to the cent on a new
  XAUUSD M15 window: **3078.50** and **-3135.50**. Both computed by hand before the
  engine was run. The failure message deliberately withholds the engine's own figure,
  so a future figure cannot be transcribed instead of derived.
- Cost profile for the test: bid basis, commission 3.50 per lot per side, slippage zero.
  The bid basis is an assumption OF THE TEST, not a claim about FTMO.
- **New fixture, `xauusd_m15_2025-02-05T2145_2025-02-12.csv`.** The phase 2 fixtures
  could not be reused: in both of them the deciding bar and the fill bar happen to carry
  the same spread, so a spread taken from the wrong bar changes nothing. That is the
  phase 2 lesson one layer down — the fixture that caught the fill-PRICE bug cannot
  catch the fill-SPREAD bug. The new window carries 0.64 / 0.27 / 0.23 on the deciding,
  fill and last bars, all distinct. A test guards that property so a future re-export
  cannot quietly lose it.
- The fill bar is 23:00, not 22:00: the 21:45 bar is the last before gold's daily
  session break, so the order fills at the next bar that EXISTS, an hour and a quarter
  later. The window exercises the session gap as well as the spread.
- **Design: one side-aware rule, used twice.** `CostModel.executable_price(side, bar,
  reference_price)` answers "if I traded this direction now, at what price?"
  `fill_price` wraps it with `bar.open`; valuation calls it with `bar.close` once per
  direction. Fills and valuation therefore cannot drift apart. Recorded as spec v3.8,
  along with `Bar.spread` in price units.
- `Portfolio.mark()` now takes `ExitPrices(long_exit, short_exit)` and picks by the sign
  of the position it holds. The ledger stays ignorant of spread, basis and venue; the
  caller asks the cost model for both candidates.

### Breaks run, 2026-10-01 — every move predicted before running, every one exact

| Break | Long | Short | Note |
|---|---|---|---|
| Spread from the deciding bar, not the fill bar | **-37.00** | **0.00** | 1 x 100 x (0.64 - 0.27) |
| Sell also pays the spread (double count) | **-23.00** | **-27.00** | long's extra lands on the last bar, short's on the fill bar |
| Short valued at close, not close + spread | **0.00** | **+23.00** | flattering: the short looks better |
| Commission dropped | **+3.50** | **+3.50** | caught by the `fees` assertion before the P&L one |
| Spread charged every bar held (additive) | **-8074.00** | **-8074.00** | 372 bars held, spreads summing to 80.74 |

Three findings from the breaks that matter more than the arithmetic:

- **Break 1 is invisible on the short.** On a bid basis a sell pays no spread at the
  fill, so which bar's spread is read changes nothing for `AlwaysShort`. Only the long
  can catch a wrong-bar spread. Under a mid basis both would. One reference strategy
  would not have been enough.
- **Break 3 is invisible on the long**, and it is the flattering direction — it makes a
  short look better than it is. Breaks 1 and 3 are each caught by exactly one of the two
  strategies, in opposite directions. Neither alone is sufficient coverage.
- **Break 5 took the phase 2 tests down too**, because the per-bar charge sat in the
  shared harness loop rather than in the cost model, so it charged runs using
  `ZeroCostModel`. A cost bug placed in the loop contaminates every wiring; placed in
  the cost model it stays where it belongs. An argument for the orchestrator keeping
  costs strictly behind the `CostModel` seam.

`git diff src/` is NOT empty after the breaks, and cannot be: the six modified files are
the phase 3a implementation itself, still uncommitted. Absence of break residue was
verified instead by SHA-256 of all 38 files under `src/` against a snapshot taken before
the first break — identical.

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
- **Addendum 2026-10-01: AlwaysShort added** (missing from spec §7.1). Matched
  operator-computed figure -4740.00 on the 02:45 fixture; the look-ahead figure
  -4749.00 turned it red with difference +9.00 — opposite sign to the long case, as
  expected. First end-to-end proof of the sell path: sell order, negative fill and cost,
  valuation against a rising price.

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
  Ltd. Both candidate venues are therefore hedging; netting is still built, for venue
  independence and for the cross-convention property test.
- **Position mode is venue configuration, never an engine assumption.** Both
  conventions get built together, as a step between phase 3 and phase 4: netting
  (average cost, one net position per symbol) and hedging (per-ticket, each fill its own
  position). Built together because the cross-convention property test (identical equity
  and total P&L for any fill sequence) is what proves the accounting, and it needs both
  to exist. The earlier reason given — that persisted state differs in shape, so adding
  one later means a migration — was overstated: under §5.1 the broker is authoritative for
  positions, so on restart much of the per-ticket record can be rebuilt from
  `positions_get()`. What the engine must persist itself (intent-to-ticket links, close
  order, realised P&L history for balance-anchored limits) is the first design question
  of that step, to be settled before any code. The engine never deliberately hedges: one
  direction per symbol under either convention. Close order under hedging is oldest
  ticket first. The adapter asserts the configured mode against `account_info()` at
  startup and halts on mismatch.
- **Partial-close cost split: decided.** Per-ticket accounting, in the step before
  phase 4, removes the division for hedging venues, which both candidate venues are.
  Average cost stays for netting, where the division remains and is bounded as described
  under "Fixed after review" — the rounding cancels in equity and can only move the
  realised/unrealised split.
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

## Trial-session plan — re-extraction

One session on a fresh FTMO trial, in this order. Every script is read only and places
no orders. Run each from `C:\trading\engine`. Each step needs a reading, not an opinion:
paste or summarise the output into this file before closing the session.

0. **Before the session:** confirm a US non-farm payrolls release falls inside the tick
   window (default 2026-10-19 to 2026-11-14 UTC) on the BLS release calendar. If not,
   pick a window that contains one and pass it in step 4.
1. **Depth per instrument** — `uv run --extra mt5 python verify_mt5.py`. Record earliest
   date per instrument. Two cautions: a single request caps near 100,000 bars, so its
   M5/M15/H1 counts can understate depth — trust D1 here, and step 3's per-year counts
   for M15; and its report labels server time as UTC without converting, so its dates
   are off by 2-3 hours (immaterial for depth).
2. **Bid basis** — `uv run --extra mt5 python check_chart_mode.py`. Record `chart_mode`
   per symbol (0 = bid, 1 = last). Also prints `swap_rollover3days`, the triple-swap
   weekday, never captured before. Do not edit `config/cost_ftmo_demo.yaml` in the
   session; record the reading, change config after.
3. **Bars** — `uv run --extra mt5 python extract_mt5_data.py`. Check the per-year counts
   for any year that looks truncated.
4. **Ticks** — `uv run --extra mt5 python extract_mt5_ticks.py` (or with
   `--start`/`--end`). Weekends show zero; a weekday showing zero means the server did
   not serve that day.
5. **DST check** — `uv run python check_dst_boundaries.py`. Must print `All 3 passed.`
   Any FAIL: stop, do not use the data, do not back it up over a good copy.
   Then `uv run pytest`: the two future-shuffle tests, red since the data was lost,
   should be green again. Then `uv run --extra mt5 pytest -m requires_mt5`: the
   MT5-marked tests, deselected from the default run, must also pass. Then
   `uv run python check_bar_spacing.py`: must print
   `No violations.` Any VIOLATION means the venue has filed bars of another width under
   a timeframe after the config's `bars_genuine_from`: stop, as for the DST check.
6. **Back up** — copy all of `C:\trading\data` off the machine, e.g.
   `robocopy C:\trading\data <backup location> /E`, then compare file count and total
   size at both ends.

### Session readings, 2026-11-17 — FTMO-Demo, login 1515313288, terminal build 6320

- **Step 0 (operator):** BLS Employment Situation released Fri 6 Nov 2026, 8:30 ET
  (13:30 UTC) — inside the default tick window.
- **Step 1, `verify_mt5.py`, ~06:30 UTC.** Report saved to
  `C:\trading\data\mt5-verification-2026-11-17.json`. Symbols resolve as before
  (US100.cash, US500.cash, EURUSD, XAUUSD, XAGUSD); contract sizes 1, 1, 100000, 100,
  5000; digits 2, 2, 5, 2, 3. History depth (earliest bar, dates in server time):

  | Instrument | Earliest | M15 bars | D1 bars |
  |---|---|---|---|
  | NAS100 | 2017-12-29 | 126,789 | 2,297 |
  | US500 | 2017-12-29 | 126,798 | 2,297 |
  | EURUSD | 2005-01-03 | 542,111 | 5,680 |
  | XAUUSD | 2005-01-03 | 506,659 | 5,633 |
  | XAGUSD | 2008-11-07 | 421,850 | 4,654 |

  Swap long/short (points): NAS100 -684.39 / 20.6, US500 -175.75 / -4.04, EURUSD
  -8.8 / 0.38, XAUUSD -57.69 / -4.2, XAGUSD -12.58 / -0.93.

  **Unexpected, session stopped here pending operator review:**
  1. "Spread now" was **0 points on all five**, on a Tuesday with markets open — the
     current tick's ask equalled its bid on every symbol. **Resolved by operator:**
     Market Watch showed live non-zero spreads; treated as a stale first quote after
     `symbol_select`. Operator observation, ~06:30 UTC (Asian session): EURUSD steady at
     5 points and XAUUSD steady at 44 over a few minutes, while GBPUSD and others
     varied. **Open question for the tick sample:** are EURUSD and XAUUSD spreads fixed
     during the Asian session? If so, C.1's hour-of-day distribution for those hours
     collapses to one value, and the widening it targets is elsewhere.
  2. Single requests returned up to 1,621,016 bars (EURUSD M5). The ~100,000-bar cap
     recorded in `extract_mt5_data.py`, and step 1's caution above, did not apply.
     Possibly the "Max bars in chart: Unlimited" setting.
  3. EURUSD and XAUUSD history now starts 2005-01-03, not the 2017-12-29 recorded in
     `extract_mt5_data.py` as the earliest verified start.
  4. XAGUSD short swap is **-0.93**; on 2026-09-11 it was +0.5, a credit. The sign has
     flipped. Expected in kind — swaps change, hence the 30-day staleness threshold —
     but worth noting, since it was the credit path's real-world example.

- **Step 2, `check_chart_mode.py`.** `chart_mode` = **0 (bid) on all five** —
  `price_basis: bid` in `config/cost_ftmo_demo.yaml` is now a reading, not an
  assumption (config not edited in session; update it and its provenance after).
  `swap_rollover3days`: **NAS100 and US500 = 5 (Friday)**; EURUSD, XAUUSD, XAGUSD = 3
  (Wednesday). The config has `triple_weekday: Wednesday` for all five, so it is
  **wrong for both indices**. The day-labelling question (does "Wednesday" mean the
  rollover ending Wednesday) is still open — needs a held position.
  The config's placeholder swap rates are also stale against step 1's readings,
  including **NAS100 short now +20.6 against -102.6 in config** — a sign change that
  turns a cost into a credit.

- **Step 3, `extract_mt5_data.py`, ~06:35 UTC. Exit 0.** Totals (earliest bar, true UTC):

  | Instrument | M15 | H1 | H4 | Earliest M15 |
  |---|---|---|---|---|
  | NAS100 | 126,798 | 35,185 | 9,783 | 2017-12-28 22:00 |
  | US500 | 126,807 | 35,185 | 9,782 | 2017-12-28 22:00 |
  | EURUSD | 542,120 | 135,678 | 34,026 | 2005-01-02 22:00 |
  | XAUUSD | 506,668 | 129,787 | 33,578 | 2005-01-02 23:00 |
  | XAGUSD | 421,859 | 107,888 | 27,792 | 2008-11-07 21:00 |

  EURUSD, XAUUSD and XAGUSD M15 per-year counts are full (about 21,000-25,000) every year
  from their first full year; partial first years (XAGUSD 2008: 3,260) and 2026
  year-to-date as expected.
  **Unexpected, session stopped here pending operator review:**
  1. **NAS100 and US500 "M15" for 2018-2020 hold about 258 bars a year: one per day,
     stamped 22:00 UTC, with open and close spanning the whole day** (NAS100
     2019-01-01: open 6334.86, close 6245.86). These are daily bars filed under M15. In
     the NAS100 2021 file, 15-minute spacing first appears at **2021-09-14 06:30 UTC**.
     ReplayFeed gives every bar ts_close = ts_open + 15 minutes, so a backtest over
     these years would read a day's move as a 15-minute bar. **Real intraday index
     history starts September 2021, not December 2017.** Step 1's "8.88 years" for
     the indices overstates it the same way. H1/H4 index files not yet inspected.
  2. **The last stored bar of each 2026 file was still forming.** Extraction ran at
     ~06:35 UTC; the latest M15 bar opens 06:30 and H1/H4 open 06:00, so their
     high/low/close are partial. The extractor stores whatever MT5 returns, including
     the open bar. Affects only the newest bar, but it is a price that never finished.

- **Step 4, `extract_mt5_ticks.py`, default window 2026-10-19 to 2026-11-14. Exit 0.**
  Totals: NAS100 10,074,538; US500 2,819,491; EURUSD 1,938,422; XAUUSD 5,201,108;
  XAGUSD 4,965,341 ticks. Every weekday non-zero, every Saturday zero, Sundays small
  (Sunday-evening open). Read-only checks on the stored ticks:
  - EURUSD's first Sunday tick is **21:05 UTC on 25 Oct and 22:05 UTC on 1 and 8 Nov** —
    the US clock change on 1 Nov, seen in the ticks themselves, so the tick
    timestamps follow the US calendar.
  - On 6 Nov (payrolls day), no tick on any instrument has ask below bid.
  - **37,322 of 123,126 EURUSD ticks on 6 Nov (30%) have ask = bid**, a zero spread.
    None on the other four. Bears on C.1 and on the config's rule that every stored
    zero spread is missing data: for EURUSD ticks, zero may be a real quote. Not
    investigated further in session.

- **Step 5, `check_dst_boundaries.py`. All 3 passed, exit 0:** Fri 17 Jan 2025 last bar
  closes 22:00 UTC; Fri 14 Mar 2025 21:00 UTC; Fri 31 Oct 2025 21:00 UTC.
  `uv run pytest`: **294 passed, 4 deselected, 0 failed** — the two future-shuffle
  tests are green again. 11 warnings, unchanged from before the session.
- **Step 6, backup, 2026-11-17 ~10:52 local.** `robocopy C:\trading\data
  "G:\My Drive\trading-data-backup\2026-11-17" /E` — 385 files, 27 directories,
  0 failed (robocopy exit 1 = files copied). Both ends compared independently:
  **385 files and 313,532,723 bytes at each.** Location: Google Drive,
  `G:\My Drive\trading-data-backup\2026-11-17`.

### Proposals from the session — options for review, NOT implemented

**(a) Extractor stores a bar that is still forming.**

- *Fix:* `extract_mt5_data.py` captures one `extraction_cutoff = datetime.now(UTC)`
  at the start of the run and drops any bar whose close time (open + the timeframe's
  width) is after it. A bar closing exactly at the cutoff is kept. The cutoff is written
  to each manifest as `complete_through_utc`, so a reader knows where the data is
  guaranteed final. The widths would come from ReplayFeed's existing
  `TIMEFRAME_DURATIONS` by import, not a second table.
- *Re-extract only 2026:* delete the fifteen `2026.parquet` files and rerun without
  `--force`. The extractor already re-fetches any year whose file is missing and skips
  the rest, so no new flag is needed. Needs a live terminal; the current trial will do.
- *Showing it catches a forming bar:* a `requires_mt5` test feeding the bar-to-table
  step fake rates against a fixed cutoff of 06:35 UTC: an M15 bar opening 06:15
  (closes 06:30) is kept, one opening 06:30 (closes 06:45) is dropped, and one opening
  06:20 (closes exactly 06:35) is kept. Run it against today's code first: it must fail
  on the 06:30 bar, which today's code stores. After re-extraction, a live check: for
  every instrument and timeframe, the last stored bar's close is at or before
  `complete_through_utc`.
- **IMPLEMENTED 2026-11-17.** One change from the proposal: the cutoff is taken at the
  start of each instrument/timeframe job, not once per run. It is still taken before
  that job fetches anything, which is the property that matters. Each manifest then
  records the cutoff that applies to its own files, and the extractor's function
  signatures are unchanged, so the test could run against the old code. Test:
  `tests/unit/test_extract_drops_forming_bar.py` (`requires_mt5`), clock frozen at
  06:30:00 UTC; bars closing 06:15 and exactly 06:30 kept, the one opening 06:30
  dropped. **Against the old code both tests failed for the right reason**: "the bar
  still forming at the cutoff was stored", and no `complete_through_utc` in the
  manifest. Both pass after the fix.
  Re-extraction ~06:54 UTC: the fifteen `2026.parquet` files deleted and re-fetched
  (all other years skipped from disk). Live check: on all 15 series, the last stored
  bar closes at or before the manifest's `complete_through_utc`. On H1, the bar
  opening 06:00 was still forming at 06:54 and was dropped. DST check: all 3 passed.
  pytest: 294 passed, 6 deselected; with `-m requires_mt5`: 6 passed.
  **Second backup:** `G:\My Drive\trading-data-backup\2026-11-17b`, 385 files and
  313,533,297 bytes at both ends.

**(b) Index history before September 2021 is not what its folder says.**

Findings from a read-only spacing scan of every file (share of consecutive bars exactly
one bar-width apart, per year, plus a gap histogram for index M15 2021):

| Series | Daily bars | Hourly bars | Genuine from (first nominal spacing, UTC) |
|---|---|---|---|
| NAS100 M15 | 2017-12-28 to 2021-01-21 | 2021-01-21 to 2021-09-14 | 2021-09-14 06:30 |
| US500 M15 | 2017-12-28 to 2021-01-21 | 2021-01-21 to 2021-09-14 | 2021-09-14 02:30 |
| NAS100 H1, H4 | 2017-12-28 to 2021-01-21 | — | 2021-01-21 (H1 22:00, H4 18:00) |
| US500 H1, H4 | 2017-12-28 to 2021-01-21 | — | 2021-01-21 (H1 19:00, H4 18:00) |

So the index M15 files hold **three tiers**: daily bars, then about eight months of
hourly bars, then genuine 15-minute bars, all filed as M15. A check asking only "when
does 15-minute spacing first appear" would have missed the hourly tier. **EURUSD,
XAUUSD and XAGUSD are clean on all three timeframes back to their first year**: nominal
spacing share 94.8% (XAUUSD M15 2005) to 99.8% (EURUSD M15), against 0% for the index
daily years. The config's own note that index spreads are zero from 2017 to 2020 is
the same history seen from another side.

- *Raw files stay untouched*, per B.6: they are what the venue returned.
- *Config:* a per-instrument, per-timeframe `bars_genuine_from` in
  `config/instruments.yaml`, which already holds each instrument's verified contract
  size. Proposed values, rounded forward to the next UTC midnight so a partial day
  never counts: NAS100 and US500 M15 `2021-09-15T00:00Z`, H1 and H4
  `2021-01-22T00:00Z`. Others absent, meaning no restriction. Each value carries a
  verified date and source, like contract sizes.
- *Engine:* ReplayFeed takes `bars_genuine_from` with the instrument's other config
  and **raises** if `range_start`, or `warmup()`'s backward reach, falls before it. It
  does not quietly clip, for the same reason `warmup()` raises instead of returning a
  short list: a backtest that silently starts later than asked looks like a result.
- *Check script:* `check_bar_spacing.py`, read only, run after every extraction as a
  new step in the trial-session plan. For every instrument, timeframe and **month**, it
  reports the commonest gap and the share of nominal gaps. Month, not year, because
  index M15 2021 scores 64% for the year and only a monthly view separates the hourly
  tier from the genuine one. It exits non-zero if any month at or after an
  instrument's `bars_genuine_from` (or the whole file, where there is none) has a
  commonest gap other than the nominal width. Shown failing first by running it with
  `bars_genuine_from` removed for NAS100, which must flag 2018-2021.
- *Effect on depth:* genuine intraday index history is about 5.2 years at M15 and 5.8
  at H1, not the 8.88 `verify_mt5.py` reports.
- **IMPLEMENTED 2026-11-17.** Raw files untouched: 385 files, 313,533,297 bytes, newest
  write still the 06:54 re-extraction.
  - `config/instruments.yaml`: `bars_genuine_from` for NAS100 and US500 (M15
    2021-09-15, H1/H4 2021-01-22, UTC), with provenance. `InstrumentSpec` rejects a
    date that is not UTC; `load_bars_genuine_from()` returns the mapping.
  - `ReplayFeed(..., bars_genuine_from=...)` raises if `range_start` is before it, and
    `warmup()` raises rather than reach back past it. **Optional, default None (no
    restriction), unlike `point`.** Making it required would break the operator-written
    `tests/properties/test_future_shuffle.py`, which constructs a ReplayFeed and is not
    Claude Code's to edit. The guard therefore holds only where the caller passes the
    date. The real orchestrator, when it builds feeds from config, must pass it.
    Consider making it required then, with the operator updating that test.
  - `check_bar_spacing.py`: commonest gap per instrument, timeframe and **month**,
    judged on the bars the engine may read. Exit 1 on any VIOLATION. Added to step 5
    of the trial-session plan.
  - *Tests first.* The config test failed for the right reason before the config was
    edited (shipped config returned `{}` for the indices). The ReplayFeed and
    spacing-check tests could only fail at the interface against the old code
    (unexpected keyword; no such module), so four deliberate breaks were run after
    implementing, each restored and SHA-256 verified: constructor guard disabled (1 red),
    warmup floor removed (1 red), spacing judged per **year** (6 red, including the
    command passing three-tier data), spacing judged ignoring `bars_genuine_from`
    (3 red). pytest: 310 passed, 6 deselected.
  - *On real data:* shipped config → exit 0, no violations; 238 months excluded.
    NAS100 and US500 M15 January-August 2021 show commonest gap **1:00:00**, 0% at
    15 minutes. September 2021 is "mixed" (commonest gap 15 min, 84% share), because
    it straddles the date; its allowed part is clean. With NAS100's dates removed from
    a config copy → exit 1, 119 violations: M15 December 2017 to August 2021 (45),
    H1 and H4 December 2017 to January 2021 (37 each).
  - *Unrelated finding:* six metal months are genuinely 15-minute but only 70-83% of
    their gaps are 15 minutes — recorded as known data holes, see "Carried-forward
    gaps".

**(c) FTMO cost config: triple-swap day and swap rates.** Readings from steps 1 and 2.
**APPLIED 2026-11-19**, tests first: the two tests asserting the old values were changed
to assert the 2026-11-17 readings, and a third added for the swap rates; all three
failed against the old config, each showing exactly the old values, and pass after.
`price_basis: bid` marked verified in a comment citing `chart_mode` (the schema has no
provenance field for it). The source citation names `mt5-verification-2026-11-17.json`
and its Google Drive backup folder, because the 2026-09-11 file the config used to cite
was lost with the old laptop. The swap rates are in that JSON; `chart_mode` and the
triple weekday are not (they came from `check_chart_mode.py`'s printed output), so those
cite this file instead. The triple-swap **labelling** stays marked unverified. Golden
tests unaffected (they load `tests/golden/fixtures/cost_test_profile.yaml`). pytest
313 passed; `-m requires_mt5` 8 passed. Default-run warnings fell from 11 to 4, because
the old 2026-09-11 swap verification had passed its 30-day staleness limit. Applied as
proposed, with two additions: the backup location in the citation, and the
labelling-unverified note on each triple day.
The diff as proposed on 2026-11-17 (applied 2026-11-19, with the two additions above):

```diff
     provenance:
-      verified: "2026-09-11"
-      source: "C:\\trading\\data\\mt5-verification-2026-09-11.json"
+      verified: "2026-11-17"
+      source: "C:\\trading\\data\\mt5-verification-2026-11-17.json"
       stale_after_days: 30
     #
-    # triple_weekday is NOT verified. symbol_info().swap_rollover3days was
-    # never captured, so Wednesday below is the common convention rather
-    # than a reading from this account. Confirm by holding a position over
-    # a Wednesday night on the trial and reading the swap off the deal
-    # record. Note also that "Wednesday" means the rollover from Wednesday
-    # into Thursday -- see docs/state.md on the labelling convention.
+    # triple_weekday read from symbol_info().swap_rollover3days on
+    # 2026-11-17 (check_chart_mode.py): Friday for the indices, Wednesday
+    # for the rest. Which ROLLOVER that names -- the one ending that day or
+    # the one beginning it -- is still unverified; confirm by holding a
+    # position across the night and reading the swap off the deal record.
     instruments:
       NAS100:
         shape: points
-        long_rate: "-514.2"
-        short_rate: "-102.6"
-        triple_weekday: Wednesday   # UNVERIFIED
+        long_rate: "-684.39"
+        short_rate: "20.6"          # positive: a credit to a short
+        triple_weekday: Friday
       US500:
         shape: points
-        long_rate: "-130.92"
-        short_rate: "-29.24"
-        triple_weekday: Wednesday   # UNVERIFIED
+        long_rate: "-175.75"
+        short_rate: "-4.04"
+        triple_weekday: Friday
       EURUSD:
         shape: points
-        long_rate: "-9.47"
-        short_rate: "0.35"          # positive: a credit to a short
-        triple_weekday: Wednesday   # UNVERIFIED
+        long_rate: "-8.8"
+        short_rate: "0.38"          # positive: a credit to a short
+        triple_weekday: Wednesday
       XAUUSD:
         shape: points
-        long_rate: "-83.0"
-        short_rate: "-8.3"
-        triple_weekday: Wednesday   # UNVERIFIED
+        long_rate: "-57.69"
+        short_rate: "-4.2"
+        triple_weekday: Wednesday
       XAGUSD:
         shape: points
-        long_rate: "-15.2"
-        short_rate: "0.5"           # positive: a credit to a short
-        triple_weekday: Wednesday   # UNVERIFIED
+        long_rate: "-12.58"
+        short_rate: "-0.93"
+        triple_weekday: Wednesday
```

Two sign changes: NAS100 short becomes a credit, XAGUSD short becomes a cost.
**Applying this turns two unit tests red, by design**, and they would need updating
with it: `test_the_ftmo_financing_section_is_verified_unlike_the_rest` asserts the date
2026-09-11, and `test_the_ftmo_triple_weekday_is_set_but_unverified` asserts Wednesday
for all five. The golden cost tests use their own test profile and are unaffected.
Out of scope of (c) but due on the same evidence: `price_basis: bid` can now cite
`chart_mode` = 0 on all five (step 2), and its "UNVERIFIED" comments can go.

### M1 survey, 2026-11-17 — read only, nothing extracted

- **M1 has never been fetched.** Every version of `extract_mt5_data.py` in git history,
  from the first commit `e16a181` to `cd09da9`, listed only M15, H1 and H4. M1 appears
  nowhere in history or docs.
- **Depth on the FTMO server**, measured year by year through the extractor's own
  `fetch_year` (true-UTC conversion), each month's commonest gap checked with
  `check_bar_spacing.monthly_reports`:

  | Instrument | Earliest M1 bar (UTC) | Genuine M1 from | Bars | Est. size |
  |---|---|---|---|---|
  | NAS100 | 2017-12-28 22:00 | ~September 2021 | 1,817,107 | 38.6 MB |
  | US500 | 2017-12-28 22:00 | ~September 2021 | 1,794,563 | 31.1 MB |
  | EURUSD | 2005-01-02 22:02 | first bar | 7,986,115 | 124.4 MB |
  | XAUUSD | 2005-01-02 23:07 | first bar | 7,020,963 | 157.3 MB |
  | XAGUSD | 2008-11-07 21:11 | first bar | 6,025,785 | 103.4 MB |
  | **Total** | | | **24,644,533** | **~455 MB** |

- **Index M1 has the same tiers as index M15:** about 258 bars a year (one a day) in
  2018-2020, and January-August 2021 not M1 either. Genuine M1 from some point in
  September 2021. Needs `M1` entries in `bars_genuine_from`.
- **Early gold M1 is sparse:** 140,695 bars in 2005 and 166,260 in 2006, against about
  350,000 a year from 2013. The bars present are 1-minute bars; many minutes simply
  have none, presumably no trades. Backtests over those years see the sparseness.
- **Size estimate ~455 MB (±20%)**: each instrument's 2025 bytes per bar, measured by
  serialising that year to parquet in memory, times its total bars. About 1.5x the
  whole of `C:\trading\data` today (313 MB); each backup grows by the same.
- Side effect: requesting M1 makes the MT5 terminal download and cache it in its own
  data folder, outside the repo.
- **M1 EXTRACTED 2026-11-17** (~07:30 UTC), after adding M1 to the extractor and to
  `TIMEFRAME_DURATIONS`, tests first. Totals: NAS100 1,817,122; US500 1,794,578; EURUSD
  7,986,129; XAUUSD 7,020,978; XAGUSD 6,025,801. The spacing check flagged index M1
  exactly as surveyed: daily bars to 2020-12, then 2021-01 to 2021-08 with commonest gap
  1:00:00. First genuine 1-minute gap NAS100 2021-09-14 06:31, US500 02:41 UTC. Operator
  approved `bars_genuine_from` M1 = 2021-09-15T00:00:00Z for both. After adding it:
  spacing check **0 violations on all 20 series**; DST check 3/3; pytest 312 passed;
  `-m requires_mt5` 8 passed. **Actual size added about 417 MB**, against the ~455 MB
  estimate.
- **Backup 2026-11-17c:** `G:\My Drive\trading-data-backup\2026-11-17c`, **473 files and
  730,529,268 bytes at both ends**, 0 failed.

Other items that need a live terminal, not part of the extraction:

- **Hold a position across a Wednesday night and read the swap off the deal record.**
  Step 2 settles which weekday is triple; only a real charge settles whether "Wednesday"
  means the rollover from Wednesday into Thursday — the day-ending convention the
  engine uses, currently recorded as unverified. Getting the labelling wrong moves
  every triple charge by a day.
- **Place one order and check whether the `comment` field survives** (§10 item 2).

## Phase 3c plan and decisions — approved 2026-11-19

Five steps, each with its own exit criterion, in the 3a/3b standard: figures the operator
computes by hand before the engine runs, for both `AlwaysLong` and `AlwaysShort`, on a
fixture checked for whether it can tell the correct behaviour from the bug, plus
deliberate breaks with predicted moves.

| Step | What | Operator hand calculations | Sessions |
|---|---|---|---|
| 3c.0 | What the stored bar spread means; EURUSD zeros; fixed Asian-session spreads — from the tick sample, analysis only | Spot-check 3 bars from a tick excerpt | ~1 |
| 3c.1 | Slippage proportional to the fill bar's spread, always adverse (3c.1a) | Yes, both strategies | ~1 |
| 3c.2 | Statistical spread model: per instrument, per hour, pessimistic percentile | Yes, both strategies, on a fixture that includes a DST-divergence week | ~2-3 |
| 3c.3 | Real sizer: weight-based, and risk-based when a stop is given | Yes: lot sizes, then both strategies | ~2 |
| 3c.4 | Phase 3 exit: everything on together (spec §9) | Yes, both strategies | ~1 |

3c.0's exit criterion: a written finding on what the bar spread is (match rates counted
only over bars where the candidate statistics differ, so a match is evidence), the
EURUSD zero-spread evidence, and the operator's decision on how the model treats both.

**Decisions:**

- **Slippage applies to fills only, never to the valuation of open positions. Spread
  stays in valuation.** Reason: FTMO measures equity at quoted prices without slippage,
  and phase 4's loss limits must be computed on the same equity the firm uses. A limit
  computed on a different equity fires at a different moment from the firm's. **This
  changes current behaviour:** `ConfiguredCostModel.executable_price` today adds
  slippage in both fills and valuation. No golden figure moves yet, because slippage is
  zero in every profile, including the golden test profile. The change lands in 3c.1,
  and the 3c.1 hand figures must be computed under the new rule. Every golden figure is
  re-checked then.
- **The volatility term of slippage (C.1) is deferred until after the orchestrator
  design.** Reason: it needs recent price history inside the cost model, and where a
  cost model gets bars from without being able to see ahead is a causality question
  (P2) that belongs to the orchestrator's design, not to the cost model. 3c.1 builds the
  spread-proportional term only.
- **Spread-model choices are decided after 3c.0.** Operator's leaning, not yet decided:
  hours by the server clock (keeps the rollover in one bucket across DST), a fixed
  percentile (deterministic, hand-checkable), charged spread = max(bar spread, table
  value), and the table fitted only on data before each backtest's start, rather than
  accepting the look-ahead leak of a whole-history fit.
- **Sizer:** weight-based (fraction of equity → lots), and risk-based when the strategy
  gives a stop price. Always round **down** to the volume step. Size from the
  **deciding** bar's close, never the fill bar's open (unknown at decision time). Volume
  minimum, step and maximum move into `config/instruments.yaml` with provenance (read
  2026-11-17).

### 3c.0 finding — the stored bar spread is the bar's MINIMUM (2026-11-19)

`analyse_spread_semantics.py` (read only) rebuilt, from the tick sample (2026-10-19 to
2026-11-13), the minimum, maximum, first, last and average tick spread inside every M1
and M15 bar, and compared each with the stored `spread`. Counted only over
**discriminating bars** — bars whose ticks did not all share one spread, where the
candidates disagree and a match is evidence:

| | Discriminating bars M1 / M15 | min | first | last | mean | max |
|---|---|---|---|---|---|---|
| NAS100 | 5,828 / 1,025 | 99.98 / 99.90% | 47 / 38% | 51 / 41% | 6 / 10% | 0% |
| US500 | 155 / 85 | 100 / 100% | 51 / 52% | 55 / 68% | 16 / 25% | 0% |
| EURUSD | 26,595 / 1,889 | 99.55 / 99.89% | 37 / 33% | 33 / 28% | 6 / 1% | ~0% |
| XAUUSD | 15,608 / 1,733 | 99.94 / 100% | 51 / 56% | 56 / 56% | 33 / 33% | 0% |
| XAGUSD | 23,095 / 1,819 | 99.69 / 98.96% | 22 / 28% | 30 / 31% | 7 / 2% | 0% |

**Operator spot-check:** three bars exported as raw ticks (EURUSD 2026-11-04 22:26,
XAGUSD 2026-10-26 22:24, XAUUSD 2026-10-27 22:38 UTC, each chosen so min, first and last
all differ), worked by hand: the stored figure equals the minimum in all three (63, 45,
47 points), and not the first or last. **Accepted 2026-11-19: bar spread = minimum.**
Residue, unexplained: a few bars store a spread below every tick spread in them
(XAGUSD 34 M1 / 16 M15, EURUSD 2, NAS100 1) — possibly quotes absent from the served
tick history; not investigated.

- **Consequence: the 3a/3b cost model charges the fill bar's MINIMUM spread, so it is
  optimistic** — about a point on EURUSD and a few on gold in normal hours, far more
  around the rollover. The 3a golden figures are correct for the rule they test; the
  rule understates cost. **3c.2 corrects it.** A spread table built from stored bars
  would be a table of minimums.
- **EURUSD zeros are genuine.** 30.5% of EURUSD ticks quote ask = bid, evenly across
  server hours 02-22 (none in 23-01, the rollover); no other instrument has any. Stored
  EURUSD bars with spread 0: ~0% before 2017, 13.7% (M1) in 2017, 0% 2018-2024, 24.4% in
  2025, 62.0% in 2026 — genuine minimums of zero, not missing data. **Decision: deferred
  to 3c.2.** Meanwhile the config's rule (every stored zero = missing → 7-point fallback,
  against a typical EURUSD tick spread of ~1 point) **overcharges EURUSD, the safe
  direction**.
- **Asian-session spreads are not fixed.** XAUUSD server hours 01-08: 10th-90th
  percentile about 37-47 points, the commonest value only 41-51% of ticks. EURUSD 0-4.
  The real structure is the rollover: EURUSD at server hour 00 has median 37 points and
  90th percentile 89, against ~1 the rest of the day — the widening C.1 names, kept in
  one bucket by server-clock hours.
- **Spread-table source: decision deferred until FTMO's tick-history depth is surveyed.**
  Then choose between (a) historical tables from bar minimums with an hour-by-hour
  correction measured from ticks, and a tick-fitted table.
- **Tick-history depth, surveyed 2026-11-19** (read only, same trial, login 1515313288).
  One hour of ticks (14:00-15:00 UTC) requested on the second Wednesday of every quarter
  from 2005, then of each of the three months before the first quarter with ticks; an
  empty answer retried once:

  | Instrument | Ticks served from | Last empty probe | Ticks in the probe hour, first probe → latest |
  |---|---|---|---|
  | NAS100 | between 2021-09-08 and 2021-10-13 | 2021-09-08 | 10,590 → 31,146 |
  | US500 | between 2021-09-08 and 2021-10-13 | 2021-09-08 | 4,277 → 8,837 |
  | EURUSD | between 2019-12-11 and 2020-01-08 | 2019-12-11 | 1,833 → 11,238 |
  | XAUUSD | between 2021-09-08 and 2021-10-13 | 2021-09-08 | 11,341 → 20,155 |
  | XAGUSD | between 2021-09-08 and 2021-10-13 | 2021-09-08 | 5,316 → 20,229 |

  No empty quarter after each start. So ticks reach back about **five years** (EURUSD
  about seven): from late 2021, the same switchover that made the index bars genuine.
  Before that, metals and EURUSD have 15+ years of bars but no ticks. A tick-fitted
  table fitted only on data before a backtest's start therefore exists for backtests
  starting 2022 or later; earlier backtests would need option (a). Starts are bounded by
  monthly probes, not pinned to a day. Decision between (a) and a tick-fitted table:
  **operator's, pending.**
- **Live quotes versus served history — no markup. Question closed 2026-11-19.** For
  3 minutes (07:20:11-07:23:11 UTC) this account's live quote (`symbol_info_tick`) was
  sampled about four times a second for all five instruments, then matched by
  millisecond timestamp against `copy_ticks_range` for the same minutes. **Every live
  quote was found in the history, with an identical spread, on all five**: NAS100
  590/590 (spread 195), US500 225/225 (60), EURUSD 229/229 (median 1, range 0-3), XAUUSD
  412/412 (median 36, 35-39), XAGUSD 279/279 (median 36, 33-39). **Operator reading,
  Market Watch, ~07:07 UTC the same day:** EURUSD mostly 1 point, range 0-3 over two
  minutes, bid/ask 1.09717/1.09718 — consistent with the history. The "steady 5 points"
  seen on 2026-11-17 is therefore not evidence of a markup; its cause is not known.

## Next

- ~~**Bid-basis check: read `symbol_info().chart_mode` per symbol.**~~ **Done
  2026-11-17:** `chart_mode` = 0 (bid) on all five (trial-session step 2). Recorded in
  the config 2026-11-19 with proposal (c).
- ~~**Proposal (c): FTMO swap config.**~~ **Applied 2026-11-19.**
- **Phase 3c: slippage, the statistical spread model of Appendix C.1, and a real
  sizer.** 3a (spread, commission) and 3b (financing) are complete — see above.
  Slippage is already wired at zero; 3c gives it a real model. Same standard as 3a/3b:
  operator-computed figures before the engine runs, for both `AlwaysLong` and
  `AlwaysShort`, on a fixture checked for whether it can tell the correct behaviour from
  the bug it exists to catch, and deliberate breaks with predicted moves.
  **Plan approved 2026-11-19** — see "Phase 3c plan and decisions" below.
  **Input for the C.1 spread model: EURUSD shows genuine zero-spread ticks on this
  venue** — 30% of ticks on 2026-11-06 had ask = bid (trial-session step 4). The
  config's rule that every stored zero spread is missing data therefore does not hold
  for EURUSD here. It may still hold for the index bars of 2017-2020, where the zeros
  coincide with the daily-bar history of proposal (b).
- **Then position conventions — netting and hedging — as a step after phase 3 and before
  phase 4**, per the position-mode decision above, including the persistence question:
  what the engine must record itself when the broker is authoritative for positions.
  Exit: the cross-convention property test, operator-written.
  Why between the two rather than inside phase 3: costs apply per fill identically under
  both conventions, and `AlwaysLong` never partially closes, so phase 3's exit criterion
  does not depend on which convention is in force. Phase 4's does — firm loss limits
  anchor to balance, and the convention decides how realised P&L feeds it.
- **Then design the real orchestrator (`core/engine.py`), before phase 4.** The risk
  gate lives inside the bar loop, so phase 4 cannot start until that loop exists. See
  the orchestrator entry under "Carried-forward gaps".
  - **Make `ReplayFeed`'s `bars_genuine_from` required** (today optional, default no
    restriction), and have the orchestrator pass it from `config/instruments.yaml`
    when it builds a feed. **Update `tests/properties/test_future_shuffle.py` at the
    same time — operator edit**: it constructs a ReplayFeed, and a required argument
    breaks it. Until then the guard holds only for callers that pass the date.

## Carried-forward gaps (not blocking)

- **Known limitation of `check_bar_spacing.py`: a wrong-width stretch inside a month
  passes when correct-width bars outnumber it.** It judges each month by its
  commonest gap, so a minority tier is invisible. Seen on real data: index M1
  2021-09 reads "ok" with no `bars_genuine_from` at all, because its 1-minute bars
  (from 14 Sep) outnumber the hourly ones before them (98.7% of gaps are 1 minute for
  NAS100). The boundary had to be found directly. A tier shorter than about half a
  month, anywhere in the history, could pass the same way. Possible fixes later: a
  per-day check, or flagging any long run of consecutive gaps at a single wrong width.

- **Known data holes, XAUUSD and XAGUSD M15: 2010-12, 2011-01, 2012-03.** The bars
  present are genuinely 15-minute (commonest gap 15 min), but only 70-83% of the gaps
  in those months are 15 minutes, against 95%+ elsewhere. 2012-03 holds about half a
  normal month's bars (XAUUSD 974, XAGUSD 1,021). Found by `check_bar_spacing.py` on
  2026-11-17. **Not gap-filled, per B.6**: a missing bar is left missing, never
  invented. A backtest spanning these months sees fewer bars, and any feature that
  assumes even spacing must handle the jumps, as B.6 already requires.

- **Answered 2026-11-17: `chart_mode` = 0 (bid) on all five symbols** (trial-session
  step 2). Recorded in `config/cost_ftmo_demo.yaml` 2026-11-19 with proposal (c).
  Original entry kept below.
  **The FTMO cost profile's `price_basis` must be verified before any FTMO backtest is
  believed.** MT5 records which price a symbol's bars are built from as
  `symbol_info().chart_mode` (0 = bid, 1 = last), and the 2026-09-11 verification run
  did not capture it. `config/cost_ftmo_demo.yaml` says `bid`, which is an assumption,
  not a finding — the file warns at load because `rules_verified` is unset. The basis
  decides which side of a trade pays the spread, so getting it wrong charges the short
  instead of the long: plausible on every chart, wrong on every trade. The phase 3a
  test profile also uses a bid basis, but there it is an assumption *of the test*,
  chosen so a figure can be computed by hand, and makes no claim about FTMO.
- **Holiday rollovers are charged one night.** There is no holiday calendar in the
  project, so a rollover falling inside a holiday gap is treated as an ordinary night.
  Real brokers vary. A known approximation, recorded rather than guessed at.
- **Partial closes pro-rate accrued financing**, which is a division — the same
  bounded one as the cost basis, where the remainder is defined by subtraction so the
  rounding cancels in equity and can only move the realised/unrealised split. Resolve
  with the position-conventions step, where per-ticket accounting removes it for
  hedging venues.
- **`per_lot_round_turn` commission over-charges a closing fill.** Per the phase 3a
  decision it charges the full round turn at entry — pessimistic, and common broker
  practice. But `fees()` cannot tell an entry from an exit, so it charges the full round
  turn on *every* fill, and a strategy that closes a position pays twice. That is
  correct for the reference strategies, which only ever enter, and wrong for anything
  else. Telling the two apart needs position state, and §2.8 hands `fees()` only the
  order and the fill price, so this cannot be fixed without either widening that
  signature or moving commission out of the cost model. Resolve it with the
  position-conventions step, where open-versus-close becomes explicit per ticket. Until
  then, do not evaluate any strategy that closes positions on a `per_lot_round_turn`
  profile. The shipped FTMO placeholder uses `per_lot_per_side`, which is unaffected.
- **The real orchestrator (`core/engine.py`) must be designed before phase 4.** The
  risk gate sits inside the bar loop — it vets each order between sizing and
  submission — so phase 4 cannot be built without deciding where that loop lives. The
  harness in `tests/golden/harness.py` must not be grown into it: a loop that only
  works against `SimBroker.fill_pending(bar)` is a second backtester, which is what P1
  forbids. Design the orchestrator and the live fill path together, then delete the
  harness.
  **Costs must sit strictly behind the `CostModel` interface, never in the bar loop.**
  Break 5 showed why: a per-bar spread charge placed in the shared loop also charged
  `ZeroCostModel` runs and turned three phase 2 tests red. A cost bug in the loop
  contaminates every wiring; behind the seam it stays contained.
  **The per-bar order of operations has no test of its own, and needs one when the
  orchestrator is built.** The ordering is: charge financing for the pre-fill window
  against the position as held BEFORE this bar's fills, apply the fills at the bar's
  open, then charge the post-fill window against the position as it stands after them.
  Nothing currently tests that sequence directly. Phase 3b break 1 showed why it cannot
  be left to the golden test: the cost model's `opened_at` guard and the loop's ordering
  enforce the same rule independently, so each masks a break in the other. Disabling the
  guard moved neither golden figure, and a loop that charged financing on the wrong side
  of the fill would be hidden by the guard in exactly the same way. The orchestrator
  needs a direct test of the ordering — a position opened at a rollover instant and one
  closed at a rollover instant, driven through the loop rather than through
  `financing()` alone.
- **Content-perturbation property test not written — before phase 5, operator-written.**
  The future-shuffle test catches order-sensitive leaks only (see "Found in phase 1").
  Perturbing the *contents* of the post-boundary bars, rather than their order, would
  also catch order-invariant leaks — `max`, `min`, `sum` over a whole dataset return
  the same value under a shuffle and pass today. Scale open/high/low/close together or
  `Bar` validation rejects the perturbed bars.
- Licence decision — before any public posting (LinkedIn etc.). Options: restrictive
  source-available (e.g. PolyForm Noncommercial / BSL) vs private repo. Check no LICENSE
  file exists meanwhile; default is all rights reserved. Take IP advice if productising.
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
