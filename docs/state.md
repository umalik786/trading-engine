# Current State

**Phase:** 0 — not started
**Last session:** 10 September 2026

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

## Verified this session, from primary sources

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

## Superseded — earlier chart-scroll estimate

Measured by scrolling charts in the terminal, not by script. Indicative only.

- **Max bars in chart** is already set to unlimited on the terminal (Tools → Options →
  Charts). This setting silently caps history depth and is the most common false
  negative when checking a broker's data.
- EURUSD and XAUUSD both scroll back past 2023 and were still loading when stopped.
  Two-plus years of M15 is enough for the phase 5 and 6 comparisons to say something,
  though not generously.
- An earlier reading of **February 2024 was wrong** — that was the download still in
  progress, not the server's limit. Taken at face value it would have led to a bar
  interval and walk-forward window sized for a fraction of the real dataset.
- **Chart scrolling is not a measurement.** Use `copy_rates_range` from 2005 and read
  the earliest bar actually returned. Do not record a depth figure obtained any other
  way.
- Not yet checked: NAS100, US500, XAGUSD. Exact symbol names on FTMO's server also
  still unrecorded (§10 item 4).

## Next

1. **Phase 0.** Repo skeleton (§3), core types (§2.1), config loading, decision log
   schema (§2.9). Exit criterion: config round-trips; manifest records commit and config
   hash; a decision log entry captures full context. Being run as four smaller tasks
   rather than one, each ending in something checkable without reading Python.
2. Phase 0: repo skeleton, core types, config loading, decision log schema.
   Exit criterion: config round-trips; manifest records commit and config hash;
   a decision log entry captures full context.

## Running alongside

Learning enough Python to review generated code. Spec §7.3 requires the property tests
to be hand-written rather than generated from the same specification as the
implementation — that part cannot be delegated. Phases 0–3 are slow and simple by
design and are a good place to learn on.

The standing question at every phase gate, which needs no code reading:
*"Show me this test failing when the thing it checks is broken."*
