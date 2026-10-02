# Current State

**Phase:** 3b — COMPLETE (2026-10-02). Phase 3a complete 2026-10-01,
phase 2 complete 2026-09-30.
**Last session:** 2026-10-02

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

## Trial-session checklist

Things that can only be settled on a live terminal or a live account, collected so a
trial session is not wasted. Each needs a reading, not an opinion.

- **Hold a position across a Wednesday night and read the swap off the deal record.**
  Settles two things at once: whether the triple-swap day really is Wednesday
  (`symbol_info().swap_rollover3days` was never captured), and whether "Wednesday"
  means the rollover from Wednesday into Thursday — the day-ending convention the
  engine uses, currently recorded as unverified. Getting the labelling wrong moves
  every triple charge by a day.
- **Read `symbol_info().chart_mode`** for each instrument, to settle whether bars are
  bid-built or last-built. `check_margin_mode.py` is the model for the script; see the
  `price_basis` gap below.
- **Place one order and check whether the `comment` field survives** (§10 item 2).

## Next

- **Phase 3 — the spec's phase 3 (§9): cost model (spread, commission, slippage) and
  sizer.** Exit criterion: `AlwaysLong` matches buy-and-hold minus a cost figure the
  operator derives by hand. The harness already takes a `cost_model` argument. Check it
  against the 02:45-start fixture, which is the one that can fail for the right reason.
  Watch for spread double-counting: charged at entry and again when marking the open
  position. A single round-number cost figure passes either way. The phase 3
  exit-criterion fixtures must be designed to separate the two, e.g. two fixtures with
  different bar counts, with the operator's hand-computed cost figure for each.
  Phase 3 exit includes AlwaysShort with spread, not just AlwaysLong. MT5 bars are
  normally bid-based, so a long pays spread on entry and a short pays it in its
  valuation while open; a cost model that only adds spread to buys passes AlwaysLong and
  overstates every short. Verify FTMO bars are bid-based, and check whether extraction
  kept copy_rates' per-bar spread column.
- **Then position conventions — netting and hedging — as a step after phase 3 and before
  phase 4**, per the position-mode decision above, including the persistence question:
  what the engine must record itself when the broker is authoritative for positions.
  Exit: the cross-convention property test, operator-written.
  Why between the two rather than inside phase 3: costs apply per fill identically under
  both conventions, and `AlwaysLong` never partially closes, so phase 3's exit criterion
  does not depend on which convention is in force. Phase 4's does — firm loss limits
  anchor to balance, and the convention decides how realised P&L feeds it.

## Carried-forward gaps (not blocking)

- **The FTMO cost profile's `price_basis` must be verified before any FTMO backtest is
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
