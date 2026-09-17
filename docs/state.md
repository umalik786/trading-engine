# Current State

**Phase:** 1 — in progress. `ReplayFeed` built and unit-tested. **Blocked on
re-extraction: all stored data is mislabelled — see the CRITICAL section below.**
**Last session:** 17 September 2026

## Decided recently

- Week one setup complete: Python 3.11, `uv`, pytest, Git 2.55, VS Code, public repo
  `trading-engine` and a private repo, both pushed. No engine code yet.
- Venue is a proprietary firm on MT5, not a retail broker account. This adds externally
  imposed loss limits to the risk layer and means fills are simulated throughout.
- External limits are configuration, never code. Spec gained §6.5.
- Both floor modes — `static` and `trailing_eod` — are built together even though the
  default only needs static. The high-water mark lives in persisted `RiskState`, and
  adding a field to persisted state later would mean a migration on a running system.
- **Which firm is deliberately undecided**, and stays undecided until phase 7.
- Do not buy an evaluation before phase 6. Phases 0–6 touch no broker, and knowing where
  a strategy sits against the random-entry baseline is cheaper than paying to find out.
- Spec now at version 3.2.
- **Current lean is FTMO**, on the strength of no size ceiling, no add-on fee, and a
  published position on automation that is explicitly mechanism-agnostic. Recorded as
  a lean, not a decision: §10 defers the choice to phase 7, and both profiles are built
  regardless. Settling it early would create a pull toward not building the second
  profile, which is how a general abstraction quietly stops being general.

## Venue rules verified from primary sources (2026-09-10)

- **FundedNext bars automation on accounts of $50,000 and above.** EAs, bots and any
  automated tool are permitted only below $50k, on MT4/MT5 only, with a non-refundable
  add-on fee. Extends to tools that only modify SL, TP or lot size. Not permitted at any
  size on cTrader or Match-Trader.
  Source: `help.fundednext.com/en/articles/8020763`, checked 2026-09-10.
- **FundedNext treats a Python script executing trades as automated trading**, under the
  same rules as EAs. Confirmed by support and by the article above.
- **FundedNext prohibits EAs incorporating Telegram, WhatsApp or similar.** Kills the
  earlier idea of a Telegram-driven kill switch. Local control file stands.
- **FundedNext measures both limits on equity** — support confirmed that open and closed
  positions both count toward the daily and maximum loss limits.
- **FundedNext Stellar 2-Step, $100k**: Phase 1 target 8%, Phase 2 5%, daily loss 5%,
  max loss 10%, drawdown static, minimum 5 trading days, news trading allowed.
  *Note: the $100k size cannot be automated. Figures retained for the profile; the
  usable size on this venue is below $50k.*
- **FundedNext caps allocation at $300k per strategy** and bans EAs built to pass
  prop-firm challenges.
- **UAE eligibility**: fine. Accounts held with both firms.
- **FTMO permits algorithmic trading and EAs with no account-size ceiling and no
  add-on fee.** Trading style is the trader's own provided it is legitimate, conforms
  to real market conditions and avoids forbidden practices. No stop-loss required
  (the risk layer imposes one anyway).
  Source: `ftmo.com/en/faq/which-instruments-can-i-trade-and-what-strategies-am-i-allowed-to-use/`,
  checked 2026-09-10.
- **FTMO server limits**: 200 orders at a time, 2,000 maximum positions per day, plus
  limited acceptance of server messages (orders and TP/SL or limit-order modifications).
  Hyperactivity may be flagged. A bar-close system on five instruments is far below all
  three. This corrects an earlier, wrongly stated figure in spec §10 item 10.
- **FTMO states on its own site that it provides simulated trading only**, does not act
  as a broker and accepts no deposits. Primary-source confirmation for §6.5.9.
- **FTMO offers unlimited free trials with no time limit.** The MT5 verification script
  should run against a free trial, not a paid evaluation.

## Blocked on

- Nothing blocking phase 0.

## Open, not blocking

- Accounting-day reset time and timezone, and what the daily limit anchors to
  (initial balance, or each day's opening balance). Needed to complete the §6.5.3
  profiles. Ask FundedNext support; read FTMO's trading objectives page.
- FTMO's position on third-party messaging integrations — still unverified; their
  strategies FAQ is silent on it. §6.4's local-control-file constraint stands regardless,
  since it is the safer design at either venue.
- **FTMO's Forbidden Trading Practices page is unread** (`ftmo.com/en/forbidden-trading-practices/`).
  This is where the specific prohibitions live — the strategies FAQ only links to it.
  Read before phase 7.
- Whether FTMO prohibits mixing manual and automated execution on one account.
  FundedNext does prohibit it; FTMO is silent. Affects whether every intervention must
  route through the engine (§6.4).
- Whether the FundedNext EA add-on can be purchased after checkout or only at checkout.
- §10 item 2 — whether the broker preserves the order `comment` field. Needs an order
  actually placed and read back, so it is a separate script on the demo account and a
  separate decision. Appendix A.5 has a fallback either way, so this is not blocking.

## MT5 verification — COMPLETE (2026-09-11)

Ran `verify_mt5.py` against a fresh FTMO free trial. Server `FTMO-Demo`, company
FTMO Global Markets Ltd, terminal build 6182. Full output saved at
`C:\trading\data\mt5-verification-2026-09-11.json`.

**§10 item 1 — history depth. ANSWERED.**

| Internal | Broker symbol | M15 span | M15 bars |
|---|---|---|---|
| NAS100 | `US100.cash` | 8.7 yrs (from 2017-12-29) | 122,501 |
| US500 | `US500.cash` | 8.7 yrs (from 2017-12-29) | 122,510 |
| EURUSD | `EURUSD` | 4.05 yrs (from 2022-08-25) | 100,725 |
| XAUUSD | `XAUUSD` | 4.22 yrs (from 2022-06-21) | 99,989 |
| XAGUSD | `XAGUSD` | 4.25 yrs (from 2022-06-10) | 100,585 |

Depth is sufficient at every timeframe. Accepted as answered; not pursued further.

*Caveat:* FX and metals returned ~100,000 bars at M5, M15 and H1 alike — suspiciously
uniform, and almost certainly the terminal's download chunking rather than FTMO's limit.
Their D1 reaches 2005, so more intraday history very likely exists. Indices were not
capped (354,465 M5 bars), so this is not a global ceiling. If a strategy later needs a
longer intraday window, scroll those three charts fully back and re-run.

**§10 item 4 — symbol specifications. ANSWERED.**

- **Broker naming differs from the spec's instrument list.** FTMO uses `US100.cash` and
  `US500.cash`, not `NAS100`/`SPX500_USD`. Internal names stay as they are; the adapter
  maps them (Appendix A.6).
- All five support **both FOK and IOC** filling modes (`filling_mode_raw: 3`). No
  constraint on `order_send` fill type.
- Volume min and step are 0.01 on all five. Max: 1000 on indices, 50 on EURUSD,
  100 on metals.
- Contract sizes: 1.0 indices, 100,000 EURUSD, 100 XAUUSD, 5000 XAGUSD.
- Digits: 2 for indices and gold, 3 for silver, 5 for EURUSD.
- Swaps are material and asymmetric — NAS100 -514.2 long vs -102.6 short; EURUSD and
  XAGUSD are positive short. Confirms Appendix C.1: implement `CostModel.financing()`
  properly rather than returning zero.
- **`margin_initial` is 0.0 on every symbol.** Margin derives from account leverage, not
  a per-symbol figure. The sizer needs leverage from `account_info()`, which this script
  did not capture. Small gap — pick up when the sizer is built (phase 3).

**§10 item 3 — bar interval. Still open, now for the right reason.** Depth no longer
constrains the choice; all four timeframes are viable. The trade-off is spread as a
share of each trade (favours longer bars) against trade count for the §7.1 random-entry
percentile (favours shorter). Defer until there is a strategy candidate.

**Not measured: spread.** The script's `spread_now_points` is a single snapshot and
EURUSD returned 0 with bid == ask, which is a stale tick rather than a reading.
Appendix C.1 wants a fitted distribution per instrument per hour-of-day. Separate job.

## Phase 0 — COMPLETE (2026-09-14)

Run as four tasks, each ending in something checkable without reading Python.
Claude Code wrote; chat-side reviewed between tasks.

**Exit criterion — all three demonstrated:**

| Criterion | Evidence |
|---|---|
| Config round-trips | Parametrized test over both YAML profiles; load → dump → reload equal |
| Manifest records commit + config hash | Built live against the repo; `git rev-parse HEAD` plus SHA-256 of the config file |
| Decision log captures full context | Sample JSONL line written — a REJECT carrying features, strategy output, reason, order and account snapshot |

**What exists now:**

- `src/engine/core/types.py` — `Bar`, `TargetPosition`, `Order`, `Fill` per §2.1.
  Frozen dataclasses. Runtime guards beyond the spec: `require_utc` rejects naive and
  non-UTC datetimes; `require_decimal` rejects floats in monetary fields, forcing
  callers through `Decimal(str(x))`. `Bar` validates OHLC inequalities and bar ordering.
- `src/engine/core/config.py` — pydantic v2 schema for §6.5.3 `account_constraints`,
  plus `load_account_constraints()`. IANA timezone validated via `zoneinfo`;
  `internal_pct < external_pct` enforced; §6.5.6 staleness and never-verified warnings.
- `config/ftmo_2step.yaml` and `config/fundednext_stellar_2step.yaml` — the two profiles
  genuinely differ (`trailing_eod` / `day_open_balance` vs `static` / `initial_balance`),
  so §6.5.1's "switching firm is a config edit" is exercised rather than asserted.
- `src/engine/core/decisions.py` — `DecisionRecord` per §2.9, `RiskDecision` enum.
  The "rejections logged as fully as executions" property is enforced in
  `__post_init__` rather than left to convention: the non-empty guards on `features`,
  `strategy_reason`, `risk_reason` and `account_snapshot` do not branch on
  `risk_decision`, so a REJECT has no path to omit context.
- `src/engine/observability/decision_log.py` — append-only JSONL. `Decimal` serialises
  as a string, never a float. Datetimes ISO-8601 with offset. Every write flushed **and
  fsynced** — `flush()` alone survives a Python exception but not a power cut, and
  §2.9's reason for the log calls for the stronger guarantee.
  Default path `C:/trading/runtime/logs/decisions.jsonl`, outside the repo.
- `src/engine/core/manifest.py` — P5 run manifest. Commit hash, **dirty-tree flag**,
  config hash, data range, seed, UTC start time.

**Dependencies added:** `pydantic`, `pyyaml`, `tzdata`, and `ruff` (dev).

`tzdata` was an unplanned find. Windows ships no system IANA database, so
`zoneinfo.ZoneInfo` fails on every valid timezone name without it. Without this the
accounting-day boundary work in phase 4 would have been silently broken on this machine
and on the production host.

**Test count: 56, all passing. `ruff check .` clean.**

## Data extraction — COMPLETE (2026-09-15)

`extract_mt5_data.py` (repo root, throwaway tooling, not imported from `src/`) pulls M15,
H1 and H4 for all five instruments from FTMO-Demo into
`C:/trading/data/raw/<internal_name>/<timeframe>/<year>.parquet`, with a manifest per
instrument/timeframe. Outside the repo, per the folder layout. Re-runnable; `--force`
re-fetches.

**M15 — the chosen interval (§10 item 3, now settled):**

| Instrument | Bars | From |
|---|---|---|
| NAS100 | 122,663 | 2017-12-29 |
| US500 | 122,672 | 2017-12-29 |
| EURUSD | 100,026 | 2022-09-07 |
| XAUUSD | 100,026 | 2022-06-22 |
| XAGUSD | 100,026 | 2022-06-21 |

H1 and H4 also extracted. H4 on EURUSD and XAUUSD reaches back to 2005.

**Decision: M15 downloaded directly, not aggregated from M1.** Aggregating would have
introduced the partial-bar leak class — a 15-minute bar that updates before minute 15
completes is showing the future — in the very phase whose job is to prove leaks
impossible. Re-downloading a different interval is cheap and reversible; a subtle
aggregation leak is neither. If a venue-unavailable interval is ever needed, build
aggregation then, with the phase 1 harness already in place to check it.

**Decision: store exactly what MT5 returns. No gap filling.** Weekends, holidays and
index session breaks are absent rows. Now recorded in the spec at Appendix B.6.

### A real bug the live run caught

`mt5.copy_rates_range()` does **not** return an empty array for a window containing no
data. It returns the single nearest bar from *outside* the window. Querying NAS100 M15
for all of 2005 returned one bar dated 2017-12-29 — the series' true start.

Unfiltered, this would have written a duplicate of each instrument's first bar into
every preceding empty year, misdated by up to twelve years. It would not have crashed.
`Bar` validation would not have caught it, because the bar is internally valid — it is
simply in the wrong year. It would have surfaced as a backtest quietly running over
fabricated history.

Fixed by filtering every result to bars actually inside the requested window. A
second-order bug followed: after the fix, `--force` correctly found zero bars for empty
years but left the stale file on disk, so a "fixed" re-run still produced bad data.
Fixed by deleting the file when a forced re-fetch legitimately finds nothing.

**Lesson worth keeping: a broker API returning something plausible is not the same as it
returning something true.** The suspicious signal was "1 bar" appearing in every empty
year — a pattern too regular to be real. Treat uniform-looking output as a prompt to
check, as with the earlier ~100,000-bar reading.

**Stored types verified on a real file:** `time` is `timestamp[us, tz=UTC]`,
OHLC are `decimal128(precision = 10 + digits, scale = digits)`, values read back as
Python `Decimal`. No float exists anywhere in the stored path.

## CRITICAL — stored data is mislabelled. Re-extraction required (2026-09-17)

**Every timestamp in `C:/trading/data/raw/` is wrong.** 1,027,342 bars across 5
instruments x 3 timeframes. Do not use any of it until re-extracted.

### What happened

`mt5.copy_rates_range()` returns times in the **broker server's own clock**, not UTC.
`extract_mt5_data.py` labelled them UTC via `datetime.fromtimestamp(t, tz=UTC)` without
converting, so every stored timestamp is shifted by the server's offset — and that
offset is not constant, because the server observes DST.

Caught by `ReplayFeed`'s own future-bar assertion, which refused to yield a bar whose
`ts_close` was ahead of the wall clock. The first explanation offered was a sandbox
clock artifact. It was not. **A cheap explanation for a guardrail firing is exactly the
thing to distrust.**

### The second, worse half of the bug

`extract_mt5_data.py`'s `year_bounds()` also passes `datetime(year, 1, 1, tzinfo=UTC)`
*into* `copy_rates_range` — and MT5 interprets input in server-local terms too. So the
year files are bucketed by server-local calendar year, not UTC.

Fixing only the output labelling would leave bars near each Dec 31 / Jan 1 boundary
filed under the wrong year. `ReplayFeed._bars_in_range` picks files by
`range(start.year, end.year + 1)`, so those bars would become **invisible** to a query
for the year they actually belong to. Missing, not wrong — a harder failure to notice.

Both sides of every call need converting.

### Server timezone — VERIFIED 2026-09-17, from FTMO's own trading updates

**GMT+2 in winter, GMT+3 in summer, transitioning on the UNITED STATES DST calendar.**

FTMO states this explicitly: the platform moves to GMT+3 on the US spring-forward date
and back to GMT+2 on the US fall-back date, not the European ones. In 2022 Europe's DST
ended on 30 October but FTMO's platform time did not change until 6 November.
Source: `ftmo.com/en/blog/trading-updates/`

EET-magnitude offsets on a US transition calendar corresponds to **no IANA timezone** —
no region observes it. It is a broker configuration choice, common among MT4/MT5
brokers, made to keep the weekly candle boundary stable against the New York session.

Implement it by asking `zoneinfo` whether `America/New_York` is in daylight time at the
instant in question, then applying +3 or +2. The DST calendar still comes from the
library — just the US one. A hand-written table of transition dates would need
maintaining forever and would be wrong the first time legislation changed.

### Accounting day — VERIFIED 2026-09-17, same source

**Midnight Prague time, European calendar.** FTMO monitors the Max Daily Loss in Prague
time and the daily drawdown resets at midnight there. Closes two `UNVERIFIED` markers in
`config/ftmo_2step.yaml`.

**These are two different clocks and must stay separate.** For two to three weeks each
spring and autumn the US and EU calendars diverge and the offset between the server
clock and Prague is two hours rather than one. A single combined offset is correct most
of the year and silently wrong exactly when it matters.

### Still to do

1. Fix `extract_mt5_data.py` — both the output labelling and the request windows.
2. Delete and re-extract from scratch. Not a surgical fix: relabelling would still leave
   the year-bucketing wrong, and re-extraction took only minutes.
3. Add `server_timezone` and its verification date to each extraction manifest (6.5.6).
4. Re-run the `ReplayFeed` unit tests against corrected data.
5. Sanity-check the corrected timestamps against a known market fact — FX closes Friday
   17:00 New York, so the weekly gap should start at 21:00 or 22:00 UTC depending on US
   DST. That is the check that proves the conversion, not that it runs.

Spec corrected to 3.6: A.3 no longer claims MT5 returns UTC; A.6 records the verified
server convention.

## Carried forward — known gaps, not blocking

- **Provenance hole (§6.5.6).** A profile with `rules_verified` set but `rules_source`
  null loads without warning. FundedNext's profile is currently in exactly that state.
  Fix when the constraint code is written in phase 4.
- **`realised_fill` backfill is documented, not enforced.** Nothing prevents
  constructing a record with it already set, or replacing other fields alongside it.
  Matters at phase 7, when there is a real write path.
- **`test_inverted_high_low_rejected_by_ohlc_checks_collectively`** — renamed after
  discovering it passed with the `high >= low` guard removed, because an earlier OHLC
  check always fires first. The guard is mathematically redundant given the other four.
  Kept as insurance; the test name now tells the truth about what it exercises.

## Next

1. **Phase 1.** Feed protocol, `ReplayFeed`, streaming feature pipeline.
   Exit criterion: the §7.3 future-shuffle property test passes — shuffling the future
   portion of a dataset never changes decisions already made.

   Note: that exit criterion is a **property test**, and §7.3 requires those to be
   hand-written by the operator rather than generated from the same specification as
   the implementation. This is the first phase where the known gap in §5 of
   `operator-context.md` becomes load-bearing rather than theoretical.

2. Bar interval: **M15, settled 2026-09-15**. §10 item 3 closed.

## Running alongside

Learning enough Python to review generated code. Spec §7.3 requires the property tests
to be hand-written rather than generated from the same specification as the
implementation — that part cannot be delegated. Phases 0–3 are slow and simple by
design and are a good place to learn on.

The standing question at every phase gate, which needs no code reading:
*"Show me this test failing when the thing it checks is broken."*
