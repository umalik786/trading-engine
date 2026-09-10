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
- Spec now at version 3.1.

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

## Blocked on

- Nothing blocking phase 0.

## Open, not blocking

- Accounting-day reset time and timezone, and what the daily limit anchors to
  (initial balance, or each day's opening balance). Needed to complete the §6.5.3
  profiles. Ask FundedNext support; read FTMO's trading objectives page.
- FTMO's position on third-party messaging integrations — unverified.
- Whether the FundedNext EA add-on can be purchased after checkout or only at checkout.
- MT5 verification session (spec §10 items 1–4): historical depth per instrument,
  `symbol_info` values, whether the order `comment` field survives, bar interval.
  Needs a running terminal and a throwaway script. Depth is the one that matters —
  it decides whether meaningful walk-forward validation is possible at all.

## Next

1. MT5 verification session — the four §10 items above.
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
