# Current State

**Last session:** 2026-11-23 (3c.2 exit criterion met); before that 2026-11-20 (3c.2:
tick sample, correction fitted and validated, wiring built)
**Phase:** 3 in progress. 3a complete 2026-10-01; 3b complete 2026-10-02; 3c.0 and
3c.1 complete 2026-11-19. **3c.2 (the spread correction) exit criterion met
2026-11-23. 3c.3 (the sizer) complete 2026-11-23.**
Phase 2 complete 2026-09-30.

## RESUME HERE (session 2026-11-23)

1. ~~Operator hand figures~~ — **done 2026-11-23: long 9108.50, short -9624.50; the
   engine matches both to the cent.**
2. ~~Held breaks~~ — **done 2026-11-23: all six moved exactly as predicted.** 3c.2's
   exit criterion is met. Record under 3c.2, "Exit criterion — MET 2026-11-23".
3. ~~XAGUSD read-only check~~ — **done 2026-11-23. Decision (operator): option (a).**
   The data check at fitting time is confirmed as it stands, so XAGUSD's earliest table
   and earliest backtest is about mid-2024. Finding under 3c.2, "XAGUSD bar/tick
   disagreement".
4. **EURUSD's 12-week minimum is reached around January 2023** (its data starts in
   2022); the others' around October 2022.

5. ~~3c.3 (the sizer)~~ — **COMPLETE 2026-11-23.** Hand figures matched (L1-L8 and four
   runs); break 8 exposed a harness defect (deciding bar not per symbol), fixed with
   operator decisions; all eleven breaks exact on the re-run. Record under 3c.3.

6. ~~FTMO commission~~ — **verified from the venue and applied, committed 2026-11-24**
   (7825340). Record under 3c.4.

**The 3c.4 build** (decisions below under "3c.4"; build record there, 2026-11-25):
1. ~~Real table, cutoff 2025-01-01, checked against the validated fit~~ — **done
   2026-11-25: identical** in every value of all five instruments.
2. ~~Guard test and week search; basket strategy and per-instrument breakdown~~ —
   **done 2026-11-25** (tests first). Week: 2026-08-25 21:00 to 2026-08-31 01:00 UTC.
3. Operator's inputs — **handed over 2026-11-25. NEXT: the operator's 14 figures**
   (6 lot sizes, 6 leg P&Ls, 2 totals) into `CASES` in
   `tests/golden/test_phase3_exit_vs_hand_figures.py`; then the six held breaks,
   predictions written first.
Then the rest of Next below.

## Data recovery (checked 2026-11-24)

- **Restore market data from `G:\My Drive\trading-data-backup\2026-11-20`.** It matches
  `C:\trading\data\raw` exactly -- all five instruments, every folder (M1, M15, H1, H4,
  ticks, ticks_monthly), same file count and total bytes, and every file the same name
  and size -- checked 2026-11-24 **by names and sizes, not contents.** It also holds
  `mt5-verification-2026-11-17.json`, compared byte for byte: identical.
- **Earlier folders are superseded:** `2026-11-17` predates fix (a) (its M15/H1/H4 files
  differ by a few dozen bytes per folder) and has no M1 or ticks_monthly;
  `2026-11-17b` has no M1 or ticks_monthly; `2026-11-17c` has no ticks_monthly.
- **`C:\trading\data\derived\` is not backed up**, deliberately: it is regenerable from
  the raw data with `fit_spread_correction.py --fit-until <date>`. Tables used by tests
  are committed as fixtures with their provenance.
- **Before any laptop handover: run a full content check** of the latest backup against
  local (read every file on both sides and compare, about 2.8 GB from Drive), not only
  names and sizes.

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
   Plan and decisions approved 2026-11-19 ("Phase 3c plan and decisions"). **3c.0
   complete 2026-11-19** (bar spread = minimum; spread-table method decided). **3c.1
   complete 2026-11-19** (slippage; see "3c.1 slippage — COMPLETE"). **3c.2, the
   statistical spread model, is in progress**: see "RESUME HERE" above.
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
  monthly probes, not pinned to a day.
- **Spread-table source DECIDED 2026-11-19: option (a) for all periods, one consistent
  method.** Historical spread from stored bar minimums plus a correction (pessimistic
  tick spread versus bar minimum, per instrument per server hour). No tick-fitted table
  for recent years alongside it: a change of method in late 2021 would put a seam in
  the walk-forward results that could be mistaken for a change in the market.
  - **The correction is fitted only on ticks before each backtest's start**, where such
    ticks exist.
  - **Validated out of sample before 3c.2 relies on it:** fit on ticks to the end of
    2024, test against actual 2025-2026 tick spreads, and report how well it predicts,
    per instrument and server hour.
  - **Open question for 3c.2, to be proposed with evidence:** whether the correction is
    added in points or as a percentage. Spreads were wider in earlier years, so the two
    diverge most for early backtests.
  - **Prerequisite for 3c.2, needs an operator decision:** the fit and the validation
    need tick history from late 2021 (EURUSD 2020) to 2026; only the four-week sample
    is extracted. That sample takes 240 MB, so the full span at today's density is about
    15 GB (perhaps 8-12 GB, since early ticks are about half as dense), carried by every
    backup. A sampled subset, such as one week per month, would be about a quarter of
    that. **Proposed approach (operator's leaning, 2026-11-19; to be decided when 3c.2
    starts):** sample one week per month, the week containing the 15th, rather than the
    full history.
  - **DECIDED 2026-11-20, with one change to the rule.** One sampled week per month,
    each a Sunday 00:00 UTC to Sunday 00:00 UTC window (exactly one trading week: the
    Sunday open, five daily rollovers, the Friday close). **The anchor day rotates
    through the 4th, 11th, 18th and 25th: anchor index = (month − 1 + year) mod 4**, and
    the sampled week is the Sunday-to-Sunday week containing that day. **Reasons:**
    - A fixed 15th systematically excluded US non-farm payrolls (always on or before
      the 7th) and over-sampled CPI (usually the 10th-15th). C.1 singles out spread
      behaviour around scheduled releases, so which releases are sampled matters.
    - A rotation by month alone, (month − 1) mod 4, was tried first and rejected:
      twelve is a multiple of four, so it repeats every year and each calendar month
      always got the same anchor. December was always Christmas week, late-month Fed
      meetings were always missed, and the CPI share stayed high. Adding the year
      moves the cycle on by one each year, so every calendar month passes through all
      four anchors over any four consecutive years.
    - Approximate release coverage, EURUSD 83 weeks / others 62: payrolls 18.1% /
      19.4%, CPI 22.9% / 19.4%, Fed decisions 16.9% / 16.1%, against ~23%, ~23% and
      ~15% for a random week. The month-only rule gave 16.9% / 26.5% / 16.9% for
      EURUSD. Payrolls stay slightly low under any 4/11/18/25 rule, because only the
      4th-anchored week can contain a first Friday, and it misses when that Friday is
      the 1st or 2nd. **These coverage figures are approximate and were used only to
      compare rules**: payrolls taken as the first Friday, CPI as about the 12th (moved
      to Monday if on a weekend), Fed decision dates from recall, not checked against
      federalreserve.gov.
    Range: EURUSD from 2019-12, the others
    from 2021-09 (the months of the last empty depth probes, so each true start is
    captured), to the October 2026 week.
  - **INCIDENT 2026-11-20, during the first sample extraction: eight-day weeks.**
    - **What happened.** A deliberate break (`_WEEK = timedelta(days=7)` → `8`) was
      restored byte for byte, with the SHA-256 confirmed. But the extraction, started
      8 seconds later, ran an eight-day rule. The edit kept the file the same length,
      and it was restored within the same second. Python's bytecode cache counts a file
      as unchanged when its size and its modification second both match, so it kept
      using the compiled broken version. Every week gained its following Sunday.
    - **Found by** the operator asking for the log: a date the rule could not produce
      (2026-04-12) appeared in it.
    - **Cleanup.** Stopped mid-XAUUSD. Every in-rule day was correctly extracted, since
      the time conversion was unaffected. The 199 extra Sunday files (EURUSD 68, NAS100
      49, US500 49, XAUUSD 33; about 12 MB) were listed, checked to be Sundays outside
      every sampled week, and deleted. `__pycache__` cleared. The run is resumed, with
      days on disk skipped and all five manifests rewritten with seven-day weeks.
    - **Lesson: a hash of the source is not proof that the code that runs is
      restored.** The earlier break runs (3a/3b, (b), 3c.1) were checked: in each, the
      last break on any file changed its length, so the cache was rebuilt, and both
      suites pass from a clean cache.
    - **Safeguards, decided 2026-11-20:**
      1. Break harnesses run with `PYTHONDONTWRITEBYTECODE=1`, clear `__pycache__`
         after every restore, and both test suites are run from a clean cache after
         any break run and before any real extraction.
      2. **Defence in depth:** `extract_mt5_ticks.py --monthly-sample` checks, before
         connecting to MT5, that every sample week is exactly Sunday 00:00 UTC + 7
         days, and refuses to run otherwise. Tested (six tests, which failed first;
         today's code "connected to MT5 despite an invalid sample rule"). Two breaks
         of the guard were each caught. **The incident reproduced on the real command
         line — the rule's source edited to eight days — was refused before
         connecting**, and nothing was written.
  - **EXTRACTED 2026-11-20** (resumed run 06:41-06:53 UTC, exit 0, after the
    cleanup). Every manifest equals the rule: each week is exactly Sunday + 7 days, and
    no file falls outside the rule.

    | Instrument | Weeks | Day files | Size | Ticks | First day with ticks |
    |---|---|---|---|---|---|
    | NAS100 | 62 | 364 | 670 MB | 65,720,358 | 2021-10-17 |
    | US500 | 62 | 364 | 193 MB | 18,806,193 | 2021-10-17 |
    | EURUSD | 83 | 488 | 347 MB | 33,147,143 | 2020-01-01 |
    | XAUUSD | 62 | 364 | 522 MB | 47,730,241 | 2021-10-17 |
    | XAGUSD | 62 | 364 | 309 MB | 29,507,386 | 2021-10-17 |

    About 2.04 GB in all, against the ~2.3 GB estimate. No Saturday has any ticks. The
    only empty weekday after each start is **2022-04-15, Good Friday**, for the four
    non-FX instruments; EURUSD traded.
  - **Tick DST check** (`check_tick_dst.py`, EURUSD Sunday open, 17:00-17:30 New York):
    - **European-calendar version: 7 failures**, six of them exactly the weeks where
      the calendars disagree at the open (2020-03-15, 2021-03-21, 2022-10-30,
      2024-03-17, 2025-03-23, 2026-10-25), each an hour late at 18:0x New York.
    - **As stored: 79 passed, 1 failed, 3 with no Sunday ticks.** All six disagreeing
      weeks pass at 17:05-17:08. The weeks with no Sunday ticks are 2019-12-15 and
      2019-12-29 (before EURUSD's history begins on 2020-01-01) and 2023-12-31 (New
      Year's Eve).
    - **The one failure, 2020-06-07, is a late venue open, not a timezone fault.** The
      first tick is at 21:48:38 UTC = 17:48 New York, 43 minutes late rather than a
      whole hour. The separately extracted M1 bars also begin at 21:48 that Sunday,
      and the previous Friday's last bar (20:54 UTC = 16:54 New York) sits exactly at
      the 17:00 close, which a wrong offset would also have moved.
    - **Window widened to [17:00, 18:00) New York, operator decision 2026-11-20.**
      2020-06-07 prompted the review. **The change is justified by an argument
      independent of the data, not by making that week pass:** a calendar error shifts
      the open by exactly one hour, and a half-open window exactly one hour wide cannot
      contain any time shifted by one hour. So every calendar error still fails,
      however late inside the hour the open falls. Any wider window would lose that
      guarantee.
    - **Rerun both ways:** European calendar → exit 1, **6 failures, exactly the 6
      disagree weeks and no others**. As stored → exit 0, **80 passed**, 0 failed, 3
      with no Sunday ticks (2020-06-07 passes at 17:48).
  - Both suites from a clean cache: 350 passed, 15 MT5 passed. Bar DST check 3/3.
  - **Backup:** `G:\My Drive\trading-data-backup\2026-11-20`, **2,422 files and
    2,770,428,750 bytes at both ends**, 0 failed.
    Stored in
    `C:\trading\data\raw\<instrument>\ticks_monthly\`, separate from the 3c.0 sample in
    `ticks\`, which `analyse_spread_semantics.py` reads in full.
  - **Known limitation**, recorded under carried-forward gaps.
  - **Fit and out-of-sample validation of the correction — APPROVED 2026-11-20, criteria
    fixed before any result was seen.** Not adjusted after results.
    - **Target:** the spread in force at a bar boundary, the moment a trade faces it.
      That's the last tick at or before the boundary. **Operator change:** at a
      boundary following a gap in quotes (no tick in the 5 minutes before it: session
      opens, the indices' daily break, the Sunday open), use the **first tick at or
      after** the boundary instead. The count of boundaries using this rule is
      reported per cell.
    - **Each M15 bar gives two observations, both against its stored minimum**,
      because the engine charges that bar's spread at both
      (`src/engine/costs/configured.py`): its **open** (a fill) and its **close**
      (valuation). The cell is the instrument and the server hour of the bar's start
      (+2/+3, US calendar).
    - **Correction** = the 90th percentile, nearest rank (sort, take the value at rank
      ⌈0.9·N⌉; no interpolation), of the boundary-minus-minimum differences
      (**points**) or the boundary-over-minimum excesses (**percentage**). Charged
      spread = max(bar minimum, bar minimum with the correction applied), so a
      negative correction never charges below the minimum. A zero minimum gives no
      percentage observation, and charges zero under the percentage form.
    - **M15 only.** Fit: sampled weeks with bars before 2025-01-01 00:00 UTC. Test:
      bars from 2025-01-01 to the October 2026 week. A cell with fewer than 200 fit
      bars uses the instrument-wide correction and is reported as a fallback.
    - **Pass/fail:**
      - A cell fails if its test coverage (the share of observations at or below the
        charge) is below 85%.
      - An instrument passes if at least 90% of its fitted (non-fallback) cells pass
        and its overall test coverage is at least 88%.
      - Cells above 97% are flagged as over-pessimistic, with their mean over-charge
        in points; they are not failed.
    - **Baselines:** no correction (bar minimum alone), and one constant correction per
      instrument. Unless the per-hour table has fewer failing cells than the constant
      correction, the simpler model is preferred.
    - **Points against percentage:** decided on the criteria, and on stability: a table
      fitted on each calendar year alone, scored against the same test period.
    - **Recorded with the approval:**
      1. **Bars within a week are correlated** (one volatile session widens many
         consecutive bars), so 22 test weeks carry less evidence than about 440 bars
         per cell suggests. Read per-cell failures with that in mind: a cell failing
         narrowly may be one bad week.
      2. **This run validates the method; it doesn't produce the tables backtests
         use.** Tables used in backtests are re-fitted on data before each backtest's
         start only.
    - **Definitions fixed to write the code, set before any result. 1-5 APPROVED
      2026-11-20:**
      1. The 5-minute gap test is half-open: no tick in [boundary − 5 min, boundary).
         If the gap rule finds no later tick in the sampled week, the observation is
         dropped and counted.
      2. Thresholds are inclusive: exactly 85% passes a cell; exactly 88% and exactly
         90% of cells pass an instrument.
      3. Year stability = the range (highest minus lowest) of the instrument's overall
         test coverage across the single-year fits. Only full sampled years count:
         EURUSD 2020-2024, the others 2022-2024. The others' 2021 (three weeks) is
         reported but not counted. **The drift evidence is thin:** four of the five
         instruments have only three full years (2022-2024), so their range is taken
         over three fits.
      4. Form chosen per instrument: if only one form passes, that one. If both pass,
         the smaller year range wins, and points if they're equal. If neither passes,
         the instrument fails and no form is chosen.
      5. Data integrity check before trusting anything: each bar's stored spread is
         compared with the minimum tick spread in [open, open + 15 min). If more than
         1% of an instrument's bars disagree, that instrument stops and is reported.
         **Amended after the first hand-check run, APPROVED 2026-11-20:** bars with
         no ticks inside them are excluded and counted, and the 1% applies to bars that
         have ticks. That first run counted XAUUSD 664 of 28,057 bars (2.37%) as
         disagreeing, but 553 of those have no ticks at all:
         - 444 are in the 2021-09-05 week, before the tick history begins (that month
           was sampled on purpose, to catch the true start);
         - 89 are a hole in FTMO's served ticks: the week of 2021-11-28 has bars all
           week, but ticks only from Wednesday 2021-12-01 23:29:39 UTC (the manifest's
           per-day counts agree);
         - 20 are scattered (2021-11, 2022-07, 2022-09, 2025-12).

         Bars with ticks that genuinely disagree: **111 of 27,504 (0.40%)**. In 86 of
         them the stored value is higher than the tick minimum, usually by a point or
         two, with a few larger (2022-01-16 23:00 UTC, stored 15, ticks 7). Cause not
         investigated. The extracted history may hold ticks the bar was not built
         from.
         Bars with no ticks are unmeasurable, not mismatches. They are still counted
         and reported per instrument.
      6. **DECIDED 2026-11-20, before results:** a cell with fewer than 100 test bars
         is reported but not judged, neither passing nor failing. Any instrument with
         more than two unjudged cells is flagged.
      7. **DECIDED 2026-11-20, before results: every cell with at least 100 test bars
         is judged, whether it was fitted or fell back.** This replaces "fitted cells"
         in the instrument criterion. A fallback cell's charge is what a backtest would
         use, and thin hours (session opens, the rollover) are where an undercharge
         matters most. Fallback cells are reported separately. The instrument criterion
         is therefore: at least 90% of judged cells pass.
      8. **Confirmed: the overall 88% is computed over every test observation**, in
         every cell, including unjudged ones.
    - **Hand check, XAUUSD server hour 14, fit period (operator, 2026-11-20):** N =
      1,528, rank ⌈0.9 × 1,528⌉ = 1,376, correction **V = 14 points**. With it, **12
      of the 12** test boundaries are covered. The export's rank 1,376 reads 14.
    - **RESULTS, 2026-11-20** (`fit_spread_correction.py`, run on 857bc7d plus the
      uncommitted 3c.2 files; report and JSON in `C:\trading\runtime\spread_correction\`).
      **The script agrees with the hand check:** V = +14, 12 of 12. Every cell had at
      least 100 test bars, so none was unjudged and none fell back. Server hour 0 has no
      bars on any instrument.

      | | No correction | Points: verdict, overall | Percentage | Hour structure earns its place? | Form chosen (def. 4) |
      |---|---|---|---|---|---|
      | NAS100 | 63.7%, FAIL | PASS, 97.88%, 0 failed; drift 0.20 pts | PASS, 97.66%; drift 1.29 | yes | points |
      | US500 | 78.6%, FAIL | PASS, 97.93%; drift 4.74 | PASS, 97.11%; drift 5.34 | no: constant +20 pts preferred | points |
      | EURUSD | — | **STOPPED by the data check**: 19.79% of measured bars disagree | — | — | none |
      | XAUUSD | 23.5%, FAIL | PASS, 97.69%, 1 failed (hour 23, 83.70%); drift 4.69 | PASS, 99.35%; drift 0.51 | no: constant +15 pts preferred | **percentage** |
      | XAGUSD | 22.7%, FAIL | **FAIL**, 69.40%, all 23 cells fail | PASS, 95.53%; drift 1.16 | no: constant 70% preferred | percentage |

      Drift is in percentage points. The bar minimum alone fails everywhere, by a wide
      margin, which confirms that today's model understates the spread. The results are
      recorded as produced. **Not yet reviewed by the operator; nothing here has been
      acted on.**
      - **EURUSD stop, cause found (read-only diagnostic):** in every disagreement the
        stored spread is above the tick minimum. 7,602 of the 7,676 are in 2020-2021,
        and 6,270 of them store 50 points where the ticks reach 0. From 2022 on, 74
        disagree. EURUSD's 2020-2021 bar spreads do not match FTMO's own ticks.
      - **XAUUSD's percentage form is chosen by the drift rule but is heavily
        over-pessimistic:** 99.35% coverage, 21 of 23 cells above 97%, and a mean
        over-charge of about 50-70 points per observation. The bar minimum rose from
        about 7 points (2022-2023) to about 21-39 (2025-2026), while the excess stayed
        about the same in points. So a 200% correction fitted on small minimums
        roughly triples the large ones. **Weakness in definition 3, visible only now:**
        a coverage range saturates near 100%, so a form that overcharges everything
        looks perfectly steady.
      - **The two metals behave oppositely:** gold's excess held steady in points,
        while silver's grew with the minimum (points fails at 69%, percentage passes at
        95.5% with few over-pessimistic cells). Points against percentage is genuinely
        instrument-specific.
      - **XAUUSD hour 23** (the hour before the daily break) fails broadly. Only 10 of
        its 132 uncovered test observations used the gap rule.
      - **NAS100 is over-pessimistic in most hours** (99%+, about 30-60 points of
        over-charge). Its corrections all come out as multiples of 10 points, so the
        90th percentile lands on a step.
      - **"Mean over-charge"** is the mean of (charge − actual spread) over the cell's
        observations, with undercharges counted as negatives.
      - **Dropped observations, about 58 per instrument, one per week:** the last bar
        before the weekend (Friday, or Thursday before Good Friday) closes after its
        last tick, and nothing follows within the week.
      - **Index 2021 single-year fits equal the no-correction baseline exactly** (NAS100
        63.67%, US500 78.55%). Those three weeks are below 200 bars in every hour, so
        they use the 2021 instrument-wide value, which is evidently 0. Not checked
        further.
      - Committed exactly as produced in b4c35a5, with the verbatim report at
        `docs/results/3c2_validation_preregistered_2026-11-20.txt`.
    - **DECISIONS MADE AFTER SEEING THE RESULTS, 2026-11-20 (operator).** Recorded as
      such: the test period informed them.
      1. **EURUSD is fitted from 2022**, like the other four, under the same criteria,
         including the data check (applied to bars from 2022-01-01 only). Its counted
         drift years become 2022-2024. Data-quality finding below.
      2. **Definition 4 amended: when both forms pass, the one with the lower mean
         over-charge on the test period is chosen** (points on a tie). Mean
         over-charge is the mean of (charged − actual spread) over every test
         observation, using the per-hour table, with undercharges counted negative.
         Applied to every instrument. **Why:** the criteria guarded only against
         undercharging, and drift measured by coverage saturates near 100%, so a
         heavily overcharging form looked stable (XAUUSD percentage, 99.35%).
         **Overcharging is not safe: it hides real edges.** Drift is still reported.
         **Amended rerun, 2026-11-20** (`validation_fit_to_2024_amended.txt`). The
         figures for NAS100, US500, XAUUSD and XAGUSD are identical to the
         pre-registered run; only the choice of form moved, for XAUUSD. The hand check
         still agrees.

         | | No correction | Points: verdict, coverage, failed cells, mean over-charge | Percentage | Per-hour table beats constant? | Chosen |
         |---|---|---|---|---|---|
         | NAS100 | 63.67% | PASS, 97.88%, 0, 35.80 pts | PASS, 97.66%, 0, 47.83 | yes | points |
         | US500 | 78.55% | PASS, 97.93%, 0, 14.58 | PASS, 97.11%, 0, 20.63 | no | points |
         | EURUSD (from 2022) | 43.79% | PASS, 93.38%, 0 of 24, 2.73 | **FAIL**, 67.24%, 22 of 24, 4.98 | yes | points |
         | XAUUSD | 23.49% | PASS, 97.69%, 1 (hour 23), 9.40 | PASS, 99.35%, 0, 59.27 | no | **points** (was percentage) |
         | XAGUSD | 22.71% | **FAIL**, 69.40%, 23, −2.09 | PASS, 95.53%, 0, 15.33 | no | percentage |

         EURUSD from 2022: 74 of 27,629 measured bars disagree (0.27%), so it passes
         the data check; 7 bars are unmeasurable. Its percentage form fails on the
         zero minimums, the structural weakness predicted in the proposal: any
         percentage of zero is zero.
         **Known weak cell: XAUUSD server hour 23, points form, 83.70% test coverage**
         (the hour before the daily break). It is the only failing cell among the
         chosen forms. Its instrument passes overall, so the cell is recorded, not
         acted on. It is the first place to look if XAUUSD costs prove too low.
      3. **These choices need confirming on fresh data**: the monthly sample weeks from
         November 2026 onward, which no decision has seen. Until then, the 2025-2026
         test period has informed the method and is no longer a clean out-of-sample
         test of it.
    - **DATA-QUALITY FINDING: EURUSD's stored bar spreads, 2005-2021, are not
      trustworthy as a measured history** (read-only examination, 2026-11-20, M15).
      Only 2020-2021 can be checked against ticks, and there they are wrong. Before
      2020 there is nothing to check them against. (Corrected 2026-11-20: 2009-2019 is
      *unverifiable*, not *wrong*. See below the table.)

      | Years | What the stored spread looks like |
      |---|---|
      | 2005-2008 | One value for the whole year: 30 (2005), then 20 (2006-2008). 100% of bars. |
      | 2009 | 71% at 20, the rest 10-15: a transition. |
      | 2010-2012 | Varied, median 10-12, p10-p90 about 6-15. Plausible, but unverifiable. |
      | 2013-2014 | Median 2, many 1s; 4.7% zeros in 2014. Plausible, but unverifiable. |
      | 2015-2017 | Mostly 7 (93% of 2016 bars); 23.8% zeros in 2017. Looks fixed. |
      | 2018-2019 | Two values, 1 and 8. In 2019, 8 is the commonest value in every server hour but one. |
      | May 2020-Sep 2021 | **50 points on 56-90% of each month's bars, in every hour.** FTMO's own ticks show minimums of 0 in the same bars. Demonstrably wrong. |
      | Oct 2021-2024 | 2 on 93-96% of bars. Agrees with the ticks (data check passes from 2022). |
      | 2025-2026 | Zeros rising: 26% (2025), 68% (2026). Genuine, per the 3c.0 tick evidence. |

      **DECIDED 2026-11-20 (operator), CORRECTED the same day.** EURUSD's stored
      spreads before 2022 are not trusted:
      - 2005-2008: one fixed value per year.
      - **2009-2019: unverifiable, not wrong.** A dominant value can be a genuine broker
        floor, as 2022-2024 shows: EURUSD 2 points on 93-96% of bars, passing the data
        check against ticks. Before 2020 there are no ticks to tell a floor from a
        placeholder.
      - **May 2020 to September 2021: demonstrably wrong.** These are the only years
        contradicted by FTMO's own ticks.

      The 3c.2 correction, fitted from 2022, can't repair the bar minimum it is added
      to.

    - **Stored-spread profile, the other four instruments** (read-only, 2026-11-20,
      M15):

      | Instrument and period | Stored spread | Verdict |
      |---|---|---|
      | XAUUSD 2005 (XAGUSD 2008) to Sep 2010 | Zero on 100% of bars; both begin recording in October 2010 | Missing |
      | Metals, late 2010-2011 | Coarse steps (XAUUSD 50/60/70/80; XAGUSD 40/50/60) | Measurement-like at coarser precision; unverifiable |
      | Metals 2012-2020 | 27-182 distinct values a year; distributions move year to year. Some dominant values (XAUUSD 24 on 64% of 2017 bars) | Looks like measurement; unverifiable |
      | Metals Jan-Sep 2021 | Irregular zeros: XAUUSD 9-86% a month; XAGUSD exactly 25% every month from February to August | Untrustworthy |
      | Indices before 2021-09-15 | 100% zero, and the bars aren't genuinely M15 | Already refused (`bars_genuine_from`) |
      | Indices about 15-30 Sep 2021 | Zero | Missing |
      | Indices 1-17 Oct 2021 | One value on every bar: 60 (NAS100), 39 (US500) | Setting or floor; unverifiable |
      | All four from Oct 2021 | Data check against ticks: 0.07-0.62% disagree | Verified |

      **The XAGUSD 25% zeros are not investigated** (operator): they fall inside the
      excluded period.

    - **DECIDED 2026-11-20 (operator): verified cost history starts 2022-01-01 for
      all five instruments.** Stored per instrument in config as
      `cost_history_verified_from`, because another broker's dates will differ. The
      guard is in Next.
      **Consequence for phase 5: about five years of trustworthy cost history,
      growing monthly.**
    - **Wiring the correction into the cost model: APPROVED 2026-11-20, all seven
      points as proposed.**
      1. **The correction values are a fitted file**, produced by a fitting command
         for a stated cutoff ("fit until"), with provenance. It lives outside the repo,
         and its hash goes in the run manifest. **The engine refuses to cost any bar
         that opens before the table's cutoff.**
      2. **The method is fixed in the cost profile per instrument:** NAS100 and EURUSD
         points per hour; US500 and XAUUSD points constant; XAGUSD percentage
         constant. All at the 90th percentile, nearest rank. The table must agree
         with the profile's method, or the engine refuses it.
      3. **Minimum fit sample: 12 sampled weeks per instrument**, enforced by refusal.
         The earliest backtest start is therefore about October 2022 for the
         non-FX instruments, and the window is about four years, growing monthly.
      4. **Percentage charges are rounded up to a whole point**, against the trader.
      5. **No correction on fallback spreads.**
      6. **EURUSD zeros are genuine from 2022-01-01** (`zero_spread_genuine`,
         open-ended), so they get the hour's correction instead of the 7-point
         fallback.
      7. **Golden test:** both reference strategies, hand figures first, on a March
         US/EU DST-divergence week, with a hand-made test table. Breaks are held
         until the operator's figures are in.
      **Also decided:** the table used for **live trading** carries provenance and
      **warns when its data is more than 60 days old**, like the swap staleness
      check. Built in this step (small). Calling it from the live wiring is in Next.
    - **Wiring built, 2026-11-20 (committed as work in progress, 1e09dbf).**
      - The pure rules moved into `src/engine/costs/spread_correction.py` (git mv).
      - New: `engine.costs.correction_table` (the table file, exact values, all 24
        hours, UTC cutoff, the 60-day staleness warning) and `SpreadCorrectionMethod`
        in the profile. `ConfiguredCostModel` takes the table and applies it inside
        `resolved_spread`, so fills, valuation and slippage all see it. `DateRange`
        may now be open-ended. The FTMO profile carries the five methods and EURUSD's
        genuine zeros from 2022-01-01.
      - `fit_spread_correction.py --fit-until YYYY-MM-DD` writes a table to
        `C:\trading\data\derived\spread_correction\ftmo-demo\`, using whole sampled
        weeks ending at or before the cutoff.
      - **Tests:** 36 new tests failed first for the intended reason; 11 others first
        failed on a mistake in my test helpers (a missing `Bar.is_final` and missing
        `Order` fields), fixed before any code was written. Four passed before any
        code existed, because a stub that ignores the table already gets them right:
        negative floor, fallback not corrected, no method, unknown keys. The first two
        are held breaks. `test_the_ftmo_profile_declares_no_zero_spread_as_genuine`
        was replaced, because the decision it recorded changed.
      - **Golden inputs:** fixture `xauusd_m15_2025-03-12T2045_2025-03-19.csv` (its
        generator reproduces the 3c.1 fixture byte for byte), test profile
        `cost_test_profile_correction.yaml`, hand-made `spread_correction_test_table.json`.
        **Incident:** the fixture guard first found that, with hour 1 at +12, buy
        rounding against the trader equalled rounding to nearest. Its assertion
        message printed the raw buy price for that version of the table. Hour 1 was
        changed to +11, so the printed number is not the answer, and the guard now
        fails with a message only (shown failing on +12 without printing an amount).
      - **Real-data fits:** a table fitted until 2026-11-01 is accepted by the cost
        model (58-61 weeks per instrument; NAS100 hour 0 falls back, a closed hour).
      - **FINDING, for the operator: XAGUSD fails the data check (more than 1% of
        bars disagree) at every cutoff before the week of 2024-06-09.** Its weekly
        disagreements run at about 1-2% through 2022-2023, so the cumulative share
        first falls to 1% in mid-2024. Under the current rules, the earliest XAGUSD
        table, and so the earliest XAGUSD backtest, is about mid-2024. Applying the
        data check when fitting a table was my addition, as a safeguard; the operator
        approved it for the validation runs, not explicitly for fitting. **Confirmed
        for fitting by the operator 2026-11-23 (option (a), below).**
      - **EURUSD reaches 12 weeks (from 2022) only around January 2023**, so its
        earliest backtest is about then; the others' is about October 2022.
    - **XAGUSD bar/tick disagreement — read-only check, 2026-11-23. Decision:
      option (a).** A bar "disagrees" when its stored spread differs from the
      narrowest tick spread inside it. XAGUSD, from 2022:

      | | 2022 | 2023 | 2024 | 2025 | 2026 |
      |---|---|---|---|---|---|
      | Disagreeing share | 1.19% | 1.12% | 0.19% | 0.29% | 0.04% |
      | Stored ABOVE the narrowest tick | 64 | 62 | 10 | 11 | 2 |
      | Stored BELOW every tick | 0 | 0 | 0 | 5 (the 2 Dec zeros) | 0 |

      - **One-sided:** every 2022-2024 disagreement has the stored spread HIGHER than
        the ticks' minimum. Neither hypothesis in the old resume note holds: missing
        ticks would show the stored value below every tick (never, 2022-2024), and the
        bars are not grossly wrong.
      - **Small:** mostly 1 point (max 3 in 2022, 5 in 2023).
      - **Usually one narrow tick:** the ticks' minimum is reached by a single tick in
        39 of 64 bars (2022) and 46 of 62 (2023).
      - **M1 agrees with the stored M15 spread in 126 of 126** disagreeing 2022-2023
        bars. Same broker, so this shows the two bar series are consistent with each
        other, not that either is right.
      - **The same pattern on XAUUSD**, less often (0.63% in 2022, 0.83% in 2023),
        with shared worst weeks (weeks of 2022-01-16 and 2023-06-04, and 2024-11-17).
        So it looks venue-wide, not corrupt silver data. Cause unknown.
      - **Absorbed by the fit:** the correction is fitted on (tick spread minus
        stored spread) and applied on top of the same stored spread, so a stored value
        1 point high is taken into account by the fit, not carried into the charge.
      - **Decision (operator, 2026-11-23): option (a).** The data check at fitting
        time stands unchanged; XAGUSD's earliest table and backtest is about mid-2024.
        The check exists to catch bars matched to the wrong ticks (large, two-sided
        disagreements); this is not that, but changing a threshold after seeing
        results was rejected.
      - **Option (b), available if a strategy later needs silver's longer window:**
        make the check look at the direction and size of a disagreement, so this
        pattern (1 point, stored side higher, M1 agreeing) would not stop a fit.
        XAGUSD would then start about October 2022 with the others. It would be a
        new rule written after seeing the data, and must be recorded as one.
    - **Zero-spread bars inside the test period (found 2026-11-23).**
      - **2 December 2025, XAGUSD: 5 M15 bars stored with spread 0** (08:15, 08:30,
        08:45, 14:15, 15:00 UTC) while their ticks show 27-32 points. XAUUSD has no
        zero that day; its 09:45 bar disagrees (stored 21, ticks 28) but is not zero.
      - **8 December 2025: XAGUSD 9 zero bars (09:45-12:00 UTC), NAS100 1 (10:15).**
        That week is not in the tick sample, so there are no ticks to compare.
      - The engine treats these zeros as missing data (neither profile declares them
        genuine) and charges the uncorrected fallback. For XAGUSD that is the
        placeholder 0.019 (19 points), BELOW the 27-32 the 2 December ticks show, so
        those bars are under-charged by 8-13 points. Correct behaviour under the
        current rules; recorded because fallbacks are placeholders, not measurements.
    - **Exit criterion — MET 2026-11-23.** Operator's hand figures, computed before
      the engine's were seen: **long 9108.50, short -9624.50**. Engine: identical.
      **Breaks, 2026-11-23 — every move predicted before running, every one exact.**
      Hardened harness: each anchor replaced exactly once, no bytecode, `__pycache__`
      cleared after each restore, SHA-256 identical after every restore, full suite
      run per break; both suites green from a clean cache afterwards (445 passed;
      15 MT5 passed).

      | Break | Long | Short | Unit failures |
      |---|---|---|---|
      | 1 European calendar for the hour | 9116.50 (+8.00) | -9633.50 (-9.00) | US-calendar test (0.42 for 0.43) |
      | 2 close hour instead of open hour | no move | -9631.50 (-7.00) | none |
      | 3 negative floor removed | no move | -9620.50 (+4.00) | 5 floor tests (e.g. 0.26 for 0.30) |
      | 4 percentage rounds toward trader | no move | no move | 2 (41 for 42; 0.41 for 0.42) |
      | 5 correction applied to a fallback | no move | no move | 1 (0.63 for 0.50) |
      | 6 late-cutoff table not refused | no move | no move | 1 (did not raise) |

      Breaks 4-6 cannot move the golden figures by construction (points form, no zero
      spreads, cutoff before every bar); the unit tests carry them. Break 2 leaves the
      long unmoved because the fill bar closes in the hour it opens.

**3c.0 COMPLETE 2026-11-19.** Exit criterion met: the bar spread is the minimum
(operator-checked); the EURUSD zero-spread evidence is recorded and its treatment
deferred to 3c.2; the spread-table method is decided.
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

### 3c.4 phase 3 exit — decisions 2026-11-23; built 2026-11-25, awaiting hand figures

**Build, 2026-11-25** (operator's start instruction of the same day):
- **Table:** `fit_spread_correction.py --fit-until 2025-01-01` (commit af2a154).
  Checked against the validated fit to end-2024
  (`runtime/spread_correction/validation_fit_to_2024_amended.json`, whose report is
  byte-identical to `docs/results/3c2_validation_amended_2026-11-20.txt`): **every
  correction identical** for all five instruments in the profile's form and
  structure (NAS100's fallback hour 0 = the validated constant 40); same input
  digests; the same fit observations bar by bar. Copied byte for byte to
  `tests/golden/fixtures/spread_correction_ftmo_fit_until_2025-01-01.json`.
- **Week search** (prints dates and pass/fail only). No daily window has NAS100
  closed while XAGUSD trades (same daily break, same Sunday open), so the run starts
  at the daily break, when only EURUSD trades: EURUSD decides alone, and XAGUSD and
  NAS100 decide together an hour later, sized from equity including EURUSD's open
  position. **Requiring XAGUSD's lots to differ between balance and equity was
  dropped** (4 of 181 starts: a 0.01-lot silver step is ~1,800 USD of equity); the
  proposal required it of NAS100 only. Two weeks passed every requirement; the first
  taken: **2026-08-25 21:00 to 2026-08-31 01:00 UTC** (first valid end, by rule).
  XAGUSD's lots do not move under balance-for-equity in this week (recorded).
- **Break 6 can move only the short basket:** EURUSD's fill falls in the rollover
  hour, where its ticks show no zeros, so the long never pays a zero spread.
- **Same-timestamp processing order: by time, then EURUSD, NAS100, XAGUSD**
  (alphabetical), via a new harness `merge_bars(series, order)` that refuses an
  order not naming each symbol exactly once.
- **Built, tests first:** `ConstantWeights` (signed weight per symbol);
  `Portfolio.realised_pnl_for` / `unrealised_pnl_for` (a small core addition: the
  per-symbol marks are private, so the breakdown could not be computed in the
  harness without duplicating the accounting); `BacktestResult.pnl_by_symbol`;
  `export_fixture.py` gains a per-window instrument (earlier fixtures re-export
  byte-identical). Golden test pins the profile, instruments file and table by
  SHA-256, so fresh swap readings stop it with that message, not a P&L mismatch.
- **Tests:** 21 new failed first, each for the intended reason, against do-nothing
  stubs. Six passed before code, each because a stub already gives the expected
  answer (never-traded symbol zero; targets independent of holdings; no features or
  warmup; legs sum to total and no-trade run has no legs, both trivially with no
  trades; the config pin). **Test mistake, fixed:** a wait-note bound of 22:00
  should be 22:15 (EURUSD's 22:00 bar, closing 22:15, is processed first).
- **Guard shown failing** (message only, files restored to identical SHA-256): EURUSD
  last spread non-zero; XAGUSD last spread 0.054 and 0.050 (up = nearest); EURUSD's
  first four bars removed; `instruments.yaml` touched (pin).

**Decisions (operator, 2026-11-23), on the proposal of the same day:**
1. **Commission, option (a): verify from the venue before 3c.4.** Third-party sources
   contradict each other. FTMO's own pages (read 2026-11-23: /en/symbols/, /en/faq/ and
   its fee, account-specification and account-comparison answers, /en/trading-platforms/,
   the trading-updates archive and its 2026-11-19 post) state **no commission rate**; the
   symbols page's spec table renders client-side and was not readable by fetch. So the
   evidence is the trial account's own deal history, read back with
   `read_deal_commissions.py` (read only). Profile updated with provenance;
   `pct_notional` if the rate turns out percentage-based.
2. **Table:** a real fitted table, cutoff 2025-01-01, checked against the validated fit
   to end-2024 before use, copied into the golden fixtures with provenance.
3. **Instruments:** XAGUSD (percentage correction), EURUSD (genuine zeros), NAS100
   (Friday triple, contract 1, daily close), merged into one run.
4. **Weights only** (no stops); the 3c.3 sizing file reused (its risk fraction is unused
   by weight targets). `config/sizing.yaml` left for phase 4.
5. **A basket reference strategy and a per-instrument P&L breakdown** in the run result.
6. **Six breaks:** wrong-symbol correction row; wrong-instrument swap settings; wrong
   contract size in sizing; balance instead of equity; percentage not rounded up;
   genuine zero treated as missing.
- **The same-timestamp processing order is stated explicitly in the operator's inputs.**

**Commission evidence so far** (deal history, FTMO-Demo trial, 2026-11-23 07:47-07:48
UTC, 0.01 lots, one long round trip each, placed by the operator before the trade list
was given): XAUUSD -0.03 on the opening deal and -0.03 on the closing deal; EURUSD -0.03
/ -0.03; XAGUSD -0.01 / -0.01; US100.cash 0 / 0; US500.cash not traded. Commission is
charged **on both deals (per side)**. At 0.01 lots MT5 reports cents, so these resolve a
per-lot rate only to about 1.00 (-0.03 per 0.01 lots is anywhere from 2.50 to 3.49 per
lot). Not enough to set the profile.

**Venue source (operator, read in a browser 2026-11-23; screenshots in the session):**
FTMO's symbols page, https://ftmo.com/en/symbols/ (its specification table renders
client-side, so it could not be fetched by script). It states commission:
**Forex $5.000; Commodities XAGUSD and XAUUSD 0.0014%; Indices, including US100.cash
and US500.cash, 0.000%.** The page does **not** say whether these are per side or per
round trip, nor (for Forex) per what unit -- read as per lot.

**Deal evidence against it** (the 0.01-lot round trips above): every rate fits
**half the stated rate charged on each side**, and the full rate per side does not:
| 0.01 lots | half per side | full per side | observed, each side |
|---|---|---|---|
| EURUSD | 2.50 x 0.01 = 0.025 | 0.05 | -0.03 |
| XAUUSD | 0.0007% x 0.01 x 100 x 3625.96 = 0.0254 | 0.0508 | -0.03 |
| XAGUSD | 0.0007% x 0.01 x 5000 x 42.727 = 0.01495 | 0.0299 | -0.01 |
| US100.cash | 0 | 0 | 0 |

**"Half per side" -- CONFIRMED 2026-11-24 for forex and metals** (record below); it was
an inference until then, pending the 1.00-lot trades. At 0.01 lots MT5's cents rounding cannot
separate it from nearby rates (e.g. gold at a flat 2.50 per lot per side would also
show -0.03). The deals also show MT5 rounding each deal's commission to the cent:
EURUSD 0.025 -> 0.03 and XAGUSD 0.01495 -> 0.01. **Correction (operator, 2026-11-23):**
an earlier line here gave XAGUSD's figure as 0.0150; it is 0.01495
(42.727 x 5000 x 0.01 x 0.000007), which is why it showed -0.01 -- evidence for
rounding to the NEAREST cent rather than against the trader (against the trader would
have shown -0.02).

**Proposed profile values (NOT applied; awaiting confirmation):** EURUSD
`per_lot_per_side` 2.50; XAUUSD and XAGUSD `pct_notional` 0.0007 (percent, per fill);
NAS100 and US500 0, now a stated venue value rather than a placeholder.

**Decisions (operator, 2026-11-23), for when the values are applied:**
1. **Each commission entry gets its own provenance** (date and source) **with a
   staleness warning, like financing.** Built test-first when the values are applied.
2. **Commission stays exact in the engine** (no rounding). Recorded: MT5 rounds each
   deal's commission to the **nearest cent, half up** (0.025 -> 0.03; 0.01495 -> 0.01).
   The engine therefore differs from the venue by under a cent per fill; see the
   phase 7 note.

**Confirmation trades, 2026-11-24 16:00-16:02 UTC (FTMO-Demo trial), read with
`read_deal_commissions.py --day 2026-11-24`. Every deal matched its written prediction
at its own price:**
| deal | price | predicted per side | observed |
|---|---|---|---|
| EURUSD 1.00 buy, open / close | 1.09699 / 1.09691 | -2.50 / -2.50 | -2.5 / -2.5 |
| EURUSD 1.00 sell, open / close | 1.09701 / 1.09697 | -2.50 / -2.50 | -2.5 / -2.5 |
| XAUUSD 1.00 buy, open / close | 3567.85 / 3569.08 | 2.4975 -> -2.50 / 2.4984 -> -2.50 | -2.5 / -2.5 |
| XAGUSD 1.00 buy, open / close | 40.985 / 40.949 | 1.4345 -> -1.43 / 1.4332 -> -1.43 | -1.43 / -1.43 |
| US100.cash 0.01 buy, open / close | 25973.68 / 25989.13 | 0 / 0 | 0 / 0 |
- **Half per side confirmed for forex** ($5.000 -> 2.50 on each deal, buy and sell, at
  1 lot) **and metals** (silver 1.43 per deal = 0.0007% of its 204,925 notional; the
  full 0.0014% would be 2.87).
- **Gold did not discriminate today:** at 3567 (below ~3593) a flat 2.50 per lot and
  0.0007% of notional give the same cents. Silver settles the percentage form for
  metals, with the venue page stating a percentage for both.
- **US500.cash was not traded:** the planned 0.01-lot index round trip was placed on
  US100.cash. US500's zero rests on the venue page alone, and its provenance says so.

**Applied 2026-11-24 (operator: apply if every deal matches), test-first:**
- `config/cost_ftmo_demo.yaml`: EURUSD `per_lot_per_side` 2.50; XAUUSD and XAGUSD
  `pct_notional` 0.0007; NAS100 and US500 0. Each entry carries `provenance`
  (verified 2026-11-24; source: the symbols page plus the deal history).
- `Commission` gains `provenance` (default staleness **90 days** -- Claude's choice,
  the project default; financing uses 30 -- flagged to the operator) and refuses
  unknown keys (a misspelt `provenance` was previously ignored silently). The loader
  warns per instrument ("<profile> <symbol> commission: ...").
- Tests: 13 new; 12 failed first for the intended reason, after a helper mistake
  (the test profile's name contained "commission", so the profile-wide warning
  matched the filter) was fixed before any code. Two passed before code: "a recently
  verified commission does not warn" (nothing warned yet -- shown failing by break i)
  and NAS100's zero fee (zero before and after; it pins the venue's zero).
  `test_ftmo_commission_on_one_lot_matches_the_deal_history_exactly` asserts the
  engine's EXACT figures at the deal prices (2.497495 and 1.434475, where MT5 showed
  -2.50 and -1.43), per decision 2.
- Breaks, predicted first, all exact: (i) commission always warns -> 2 failures;
  (ii) loader skips commission -> 2; (iii) unknown keys accepted -> 1.

**Held (from 2026-11-23, now released by the confirmation):** the rest of 3c.4 waited
for the 1.00-lot confirmation trades (planned for the evening of 2026-11-23: 1.00 lot buy-and-close on
EURUSD, XAUUSD, XAGUSD; 1.00 lot sell-and-close on EURUSD; 0.01 lot buy-and-close on
US500.cash). Predicted per side: EURUSD -2.50 on all four deals; XAUUSD 0.0007 x price
(-2.54 at 3625.96); XAGUSD 0.035 x price (-1.50 at 42.727); US500.cash 0.

### 3c.3 sizer — COMPLETE 2026-11-23

**Decisions (operator, 2026-11-23), on the proposal of the same day:**
- **Rules (section 3 of the proposal), approved.** "close" = the deciding bar's close;
  "equity" = equity marked at that close.
  - weight w, no stop: |w| x equity / (contract size x close)
  - a stop: risk fraction x equity / (contract size x |close - stop|); the weight
    then gives only the DIRECTION and **must be exactly +1 or -1** -- any other weight
    is refused as a second answer to "how big" (operator, 2026-11-23, decision C;
    replaces Claude's first reading, which ignored the weight's size)
  - quantity q: |q|
  - then: round toward zero to the step; below the minimum -> 0; above the maximum
    -> the maximum; apply the sign. Exact arithmetic (fractions) until the rounding.
  - Refusals: a stop on the wrong side of the close or at it; a stop with a quantity;
    a stop with a weight other than +1 or -1;
    a stop on a flat target; neither or both of quantity and weight; no instrument
    spec. Equity at or below zero sizes to 0.
  - Risk fraction is sizer config, no default; not a firm rule, not the strategy's.
- **A. Hold rule, for weight- and stop-sized targets ONLY.** If the committed
  position is non-zero and in the target's direction, it is kept. Quantity targets
  order the difference exactly as before. **Limit, recorded: changing a weight in the
  same direction has no effect until the position-conventions step.**
- **B. Spec §2.5 amended:** the sizer also receives a `SizingContext` (deciding bar,
  committed quantity = held plus ordered, instrument spec).
- **C. Spec §2.1 amended:** a `TargetPosition` gives exactly one of quantity or weight.
- **D. Stops are not executed yet, and that is enforced:** if a price reaches the stop
  of a held position during a backtest, the run stops with `StopNotExecutedError`
  (long: bid low <= stop; short: ask high >= stop, via the cost model). The golden
  stops are guard-tested as never reached.
- **Known understatement, recorded:** the risk distance is the raw price distance; a
  real stop-out also pays spread, slippage and commission, so the loss at the stop
  exceeds the risk budget. Revisit when stops are executed.
- **Caps are made visible:** a cap, a size below the minimum and a non-positive equity
  each add a `SizingNote`; the run result carries them (`sizing_notes`). Into the
  decision log at orchestrator design (Next).
- **Figures:** L1-L8 plus all four runs (weight and stop, long and short).

**Built:**
- `InstrumentSpec` gains `volume_min`, `volume_step`, `volume_max` (required, no
  default, floats refused, minimum and maximum whole multiples of the step).
  `config/instruments.yaml` carries the 2026-11-17 readings (all five 0.01/0.01;
  maximum 1000 indices, 50 EURUSD, 100 metals), with provenance and the reading
  file's SHA-256.
- `engine.sizing.equity`: `EquitySizer`, `SizingConfig` (`risk_fraction`),
  `load_sizing_config`, `SizingNote`. `FixedQuantitySizer` is unchanged in behaviour
  (no rounding, no limits) and refuses a weight; every earlier golden figure stands.
- `AlwaysLong` / `AlwaysShort` take `weight=` and `stop_price=` (positive weight;
  the strategy applies the sign).
- The harness (`tests/golden/harness.py`): passes the context, enforces D, refuses
  specs whose contract size disagrees with the run's, carries `sizing_notes`. The
  instrument specs are OPTIONAL in the harness so the earlier golden tests stay
  untouched; `EquitySizer` refuses to run without one.
- **Tests:** written first against stubs (a sizer returning 0 for everything). 85
  failed, each on its assertion, a refusal not raised, or the new contract not yet
  existing. **Seven passed before any code:** zero weight is flat; a flat weight
  closes a position; below the minimum is zero (weight and quantity) -- all because
  the stub returns 0 (held breaks 5 and 10 cover them); and three `TargetPosition`
  tests of behaviour that already existed (weight alone valid, quantity alone valid,
  float weight refused), there to stop the new rule being written too strictly.
- **Golden inputs:** the 3c.2 fixture, profile and table, unchanged; new
  `instruments_sizer_test.yaml` (minimum 0.20, step 0.05, maximum 3.00 -- the real
  0.01/0.01 cannot tell a step from a minimum) and `sizing_test.yaml` (risk fraction
  0.04, test data). Weight 2.3; long stop 2918; short stop 3066 (the week's highest
  ask after the decision is 3038.51; its lowest bid, 2932.85, is above the deciding
  close). **No single weight can catch both "open instead of close" and "round to
  nearest"** (the open-to-close gap is 0.02% of the price, so it flips a size only
  just above a step boundary, where both roundings agree); the stop runs catch the
  first, the weight runs the second.
- **Fixture guard** shown failing, message only, file restored to an identical SHA-256:
  short stop 3030 (fails a rounding check first), weight 1.2, L8 off its step, and
  short stop 2990 (reached: both the guard and `StopNotExecutedError` fire).
- **Incident, disclosed:** a `ruff check --fix` over all of `tests/` reordered two
  imports in `tests/properties/test_future_shuffle.py`. Reverted with `git checkout`
  before anything else ran; the file is unchanged from HEAD.

**Held breaks (predictions written before each, after the operator's figures):**
1. round to nearest instead of down; 2. the deciding bar's open instead of its close;
3. balance instead of equity; 4. round to the minimum instead of the step;
5. minimum ignored; 6. maximum cap removed; 7. sign dropped (a short sized as a long);
8. hold rule removed (re-size every bar); 9. wrong-side stop accepted;
10. a flat weight held instead of closed (covers two tests that passed before code);
11. a stop target with a weight other than +1 or -1 accepted (its test failed first,
    DID NOT RAISE, before the rule existed; the "1.00 is +1" test passed before code,
    as a guard against comparing the written form rather than the value).

**Operator's hand figures (2026-11-23), entered; the engine matches every one:**
L1 0.75, L2 -0.75, L3 2.70, L4 -0.25, L5 0, L6 3.00, L7 0.85, L8 1.15; runs
long-weight 6831.375, short-weight -7218.375, long-stop 24592.95, short-stop -2406.125.

**First break run (2026-11-23): 9 of 11 as predicted; 7 and 8 not. Not committed.**
- **Break 7 (sign dropped) -- prediction error, not an engine fault.** The 11 tests
  that failed are exactly those listed, but the prediction said "10" (its own list
  sums to 11) and said the short-weight run would fail on its side. It failed with 16
  orders: with the sign dropped the sized position always opposes the target, so the
  hold rule never applies and every bar re-sizes; the one-order check runs first.
- **Break 8 (hold rule removed) -- exposed a DEFECT in the harness wiring.** Predicted:
  the two-symbol in-flight test passes (equity is constant there). It failed. Cause:
  the harness passed the bar BEING PROCESSED as the sizer's deciding bar, whatever the
  target's symbol, so gold was sized from silver's close (30) -> 16.67 lots, capped at
  5.00, and silver from gold's close (2000) -> 0, sold. The hold rule masked it in
  every test: a held position is returned before any price is used. The golden runs
  (one symbol) were never affected. A multi-instrument strategy ENTERING one symbol on
  another's bar would have been sized from the wrong price.
- **Fix (operator decisions, 2026-11-23):**
  - the deciding bar is **the latest bar of the target's own symbol**;
  - **(a)** a target for a symbol with no bar yet **waits**: no order, a `no_bar_yet`
    `SizingNote`, sized on that symbol's first bar;
  - **safeguard:** a symbol targeted but given no bar in the whole run raises
    `NoBarForTargetError` at the end.
  Tests, each shown failing first: gold entered on a silver bar is sized from gold's
  last close (failed: 5.00 for 0.20 -- independent of the hold rule, flat when
  decided); a target with no bar yet waits (failed: KeyError, before waiting existed);
  a never-seen symbol stops the run (failed: DID NOT RAISE).
- **The deciding bar may be hours old** when its market is closed: a target for an
  index restated on a gold bar overnight is sized from the index's last close. That
  close is in the past, so causality holds; it is simply stale, and a strategy that
  cares must not target a closed market.

**Corrected predictions for breaks 7 and 8** (the originals above stand as written):
- 7: the same 11 failures; the short-weight run fails "expected exactly one order"
  (16 orders), not on its side; the short-stop run still raises StopNotExecutedError.
- 8: with the per-symbol fix, the in-flight test PASSES under this break (equity
  constant, the re-size equals the order); 7 failures, as first written.

**Exit criterion — MET 2026-11-23.** Re-run of all eleven breaks after the fix, fresh
predictions written first (including the corrected 7 and 8): **every one exact** --
failures 14, 7, 4, 15, 4, 6, 11, 7, 4, 1, 4, the same tests and the same wrong sizes
as written (e.g. break 2 moves L8 to 1.10; break 7's short-weight run places 16 orders;
under break 8 the four runs place 16, 2, 128 and 103 orders). Hardened harness, SHA-256
identical after every restore. All eleven breaks are in `src/engine/sizing/equity.py`;
the three new harness tests (own-symbol, waiting, never-seen) are exact multiples of
step and minimum, flat when decided, so none of the eleven moves them -- predicted
and observed.

### 3c.1 slippage — COMPLETE 2026-11-19

**Built, tests first:**
- Slippage is paid on fills only, never in the valuation of an open position.
  `executable_price` is the quoted price adjusted for spread; `fill_price` adds slippage
  (spec v3.11, §2.8).
- Fills are put on the instrument's price grid, rounded against the trader: up for a
  buy, down for a sell.
- Each instrument's costs have a `slippage` block with shape `fixed` or
  `spread_multiple`. `spread_multiple` scales the spread the fill is charged (the fill
  bar's resolved spread now, the modelled spread after 3c.2).
- Each instrument's cost block rejects unknown keys. Before that change, the new
  `slippage` block was silently ignored and every new test showed slippage at zero, the
  exact danger the guard now prevents.
- FTMO profile: `spread_multiple 0.5` on all five, PLACEHOLDER (cannot be measured on a
  simulated venue, C.4).
- The 3a/3b test profile keeps `fixed 0`, and its figures are unchanged.

The volatility term of C.1 is deferred until after the orchestrator design.

**Exit criterion MET:** a new golden test, `tests/golden/test_slippage_vs_hand_figures.py`,
with its own profile (`cost_test_profile_slippage.yaml`, identical to the 3a/3b profile
except slippage `spread_multiple 0.3`), on the 2145 fixture. The operator's hand
figures, computed before the engine's were seen, are **long 2571.50 and short −3069.50**.
Both match. The fixture is guarded in code: the deciding, fill and last bars give three
different slippage amounts, and rounding against the trader differs from rounding to
nearest on both sides.

**Breaks — every move predicted in writing before running (08:24 UTC), every one exact.**
Move = engine minus hand figure; each restored and SHA-256 verified.

| Break | Long | Short |
|---|---|---|
| 1. Slippage from the deciding bar (a stale-bar bug) | **−11.00** | **−11.00** |
| 2. Slippage from the last bar (injected, not causally reachable) | **+2.00** | **+2.00** |
| 3. Slippage in the trader's favour | **+17.00** | **+17.00** |
| 4. Slippage back in valuation (the old code shape) | **−6.90** | **−6.90** |
| 5. Rounding to nearest instead of against the trader | **+1.00** | **+1.00** |
| 6. Slippage scaled by the spread component, not the bar's spread | **0.00** | **+9.00** |

- **Break 6 is invisible on the long.** On a bid basis the long's spread component is
  the whole spread, so scaling by it changes nothing. Only the short catches it. That is
  the same one-sided blindness as 3a's breaks 1 and 3 and 3b's sign break, on a fourth
  mechanism.
- **Break 2 cannot arise in a causal loop**, since the last bar is in the future at fill
  time. It was injected only to show the figure separates the three amounts.

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

- **FTMO commission is still a zero placeholder. Verify it from FTMO's own terms
  before any FTMO backtest is believed** (added 2026-11-20). A zero commission
  understates costs on every fill, in the same invisible way as the minimum spread
  did.
- **Orchestrator design: refuse to run when the data's source server doesn't match the
  venue the cost profile was built for** (added 2026-11-20). Every extraction manifest
  records `source_server` (e.g. FTMO-Demo). A cost profile measured on one venue,
  applied to bars from another, gives plausible numbers that are wrong. The guard
  compares the two at startup and stops on a mismatch.

- **The engine refuses backtests starting before each instrument's
  `cost_history_verified_from` date** (decided 2026-11-20; replaces the EURUSD-only
  item). The date is per instrument in config: 2022-01-01 for all five on FTMO. An
  explicit override allows earlier starts **for exploratory runs only, and stamps
  their results "costs unverified"**. It works the way `bars_genuine_from` refuses
  non-genuine bars. See the 3c.2 decision on verified cost history.

- **Live wiring must call the spread-correction table's staleness check** (60 days;
  added 2026-11-20). The check exists from 3c.2. Nothing live exists yet to call it.

- **Orchestrator design: mark every bar sharing a close time before any strategy
  decision** (operator, added 2026-11-23, 3c.4). Today the harness processes bars with
  the same timestamp one symbol at a time, so a decision on the first symbol's bar sees
  the other symbols' previous marks; results then depend on symbol order. The
  orchestrator must mark all bars of a timestamp first, then decide.
- **Orchestrator design: the deciding bar is per symbol** (added 2026-11-23, 3c.3).
  The real orchestrator must size each target from the latest bar of the TARGET's
  symbol, not the bar being processed; a target for a symbol with no bar yet waits
  with a note; a symbol targeted but never given a bar stops the run. The test
  harness does this today (`tests/golden/harness.py`), found by break 8.
- **Orchestrator design: write `SizingNote`s into the decision log** (added
  2026-11-23, 3c.3). Caps and sizes below the minimum are in the run result today;
  `DecisionRecord` has no field for them yet.
- **Position conventions: decide rebalancing.** Under the 3c.3 hold rule a weight
  change in the same direction does nothing (added 2026-11-23).
- **Stop execution** (position conventions / orchestrator). Until then a backtest
  stops when a held position's stop is reached. When built: revisit the risk-distance
  understatement (costs at the stop) (added 2026-11-23).

## Phase 5 notes

- **Rolling refit of the spread correction** (operator, 2026-11-20). A table frozen
  for a multi-year backtest grows stale: gold's spreads roughly tripled from 2022 to
  2026. Refitting, for example quarterly, with each table fitted only on data before
  its quarter, is equally causal and more faithful. Design it in phase 5, not now. The
  3c.2 cutoff refusal already allows it: each quarter's bars are costed by a table
  whose cutoff is at or before that quarter's start.

## Phase 7 notes

- **Commission reconciliation against the venue** (operator, 2026-11-23). The engine
  charges commission exactly; MT5 rounds each deal's commission to the nearest cent,
  half up. Reconciling engine fills against the broker's deal history must therefore
  allow up to half a cent per deal on commission (and say so in the report), rather
  than treating it as a mismatch -- or round the engine's figure the same way before
  comparing. Decide which in phase 7.

## Carried-forward gaps (not blocking)

- **Known limitation — backtests before the tick history use a spread correction
  measured from later data. Untested assumption.** FTMO serves ticks from about January
  2020 (EURUSD) and September/October 2021 (NAS100, US500, XAUUSD, XAGUSD). The 3c.2
  spread model corrects bar minimums with a tick-measured correction fitted only on
  ticks before each backtest's start, but a backtest starting before the ticks begin has
  no such ticks. It must borrow a correction measured later. That assumes the
  relationship between the bar minimum and the pessimistic spread held in 2005-2021 as
  it does since. Nothing in this project tests that, and nothing currently can. Recorded
  in the same way as the simulated-venue caveat (spec C.4, §6.5.9): stated where results
  are read, not quietly treated as settled. Decided 2026-11-19.

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
