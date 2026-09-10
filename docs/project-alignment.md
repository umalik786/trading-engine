# Project Alignment and Decision Record

**Companion to:** `trading-engine-architecture.md`
**Purpose:** the *why*. The spec says what to build; this says what it is for, what was decided and rejected, and how the work is run.

Read this first in any new session.

---

## 1. What this is

A personal, single-user trading engine that runs the operator's own strategies against the operator's own account, with automated sizing, risk management and execution inside architecturally enforced guardrails.

**Success is defined as: the system autonomously executes a strategy correctly, and honestly reports whether that strategy has an edge.** Success is explicitly *not* defined as making money. Profitability is a property of the strategy, not of the framework, and the framework's job is to avoid lying about it.

## 2. Why it exists

**Validation.** A place to test strategies where the backtest can be trusted. Most retail backtests are optimistic through look-ahead, understated costs and unmeasured overfitting. The framework's value is that its results survive scrutiny.

**Discipline.** Removing discretionary intervention from individual trade decisions — entry, sizing, stop placement, exit. This is the operator's primary motivation and the more important of the two.

**Portfolio and credibility.** Built during a period of unemployment, published as evidence of engineering capability, and used as the basis for offering 1:1 help to others building their own systems around their own strategies.

## 3. Non-negotiable premises

These were established through discussion and should not be quietly relaxed later.

**Edge comes from the strategy, not the automation.** Automation removes execution error. If a strategy has no edge, disciplined execution loses more consistently. The phase 6 gate — clearing the random-entry baseline at a percentile nominated *before* looking — is the test of this, and must not be softened when reached.

**Automation is not hands-free; it relocates the human.** The remaining decisions (pause during news, override a signal, widen a limit after a breaker, redeploy after a drawdown) carry the same psychological pressure as discretionary trading, and are harder to see because they don't feel like trading. Addressed by §6.4 of the spec rather than by willpower.

**No LLM in the signal path, ever.** Non-determinism destroys backtestability, reproducibility and falsifiability. See spec §13.

**TradingView never emits a live signal.** Research tool only. See spec §12.

**Correctness is the differentiator.** In a field where the standard currency is unverifiable returns screenshots, a system that can demonstrate it isn't lying to itself is the rarer and more defensible artifact.

## 4. Origin and what changed

The architecture began from a YouTube tutorial (AI Pathways, "How To Actually Build a Trading Bot With Claude Code"), which is more rigorous than most of its genre. Three things it got right and which were kept:

- **Causal inference in the regime model** — using the forward algorithm rather than full-sequence Viterbi, which would let bar *N*'s classification depend on bars after it. A real bug most tutorials never mention.
- **Random-entry benchmark** — comparing against random entries under identical risk rules. Promoted here to the primary significance test.
- **The lock file** — a drawdown halt requiring manual deletion. Good friction design: converts "just restart it" into "understand it first."

What was changed, and why:

| Reference framework | This project | Reason |
|---|---|---|
| Separate backtester and live loop | One engine, swappable adapters | Silent divergence between validated and trading code is the most expensive bug class in retail systems |
| Look-ahead fixed at inference only | Causality enforced structurally; nested hyperparameter selection | Look-ahead is a category, not an instance. Global model selection before a walk-forward leaks out-of-sample data into a hyperparameter |
| Regime model at the centre | Demoted to an optional feature provider | Required for strategy-agnosticism; also means it needn't be built until something needs it |
| Strategy embedded in the system | Plugin behind a contract | Forces the risk layer, sizer and executor to be genuinely general |
| Agent-written test suite ("134 tests pass") | Reference strategies, parity harness, hand-written property tests, golden replays | Tests generated from the same spec as the implementation confirm internal consistency, not correctness. If the agent misunderstood, it wrote both the bug and the test that passes it |
| Position tracker only | Full startup reconciliation, order idempotency, persisted risk state | Process death mid-position is the most likely real-money incident |
| Slippage as a constant | Pluggable cost model | The backtest-to-reality gap is mostly costs, and constants hide exactly the conditions where strategies fail |
| Fixed breaker thresholds | Derived from own P&L distribution | Thresholds calibrated for daily equity rebalancing are wrong for intraday multi-trade systems |

## 5. Decisions made

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Single user | Multi-tenancy deferred entirely — see §7 |
| Primary venue | MT5 | Retail standard, so others can use the result; already familiar |
| Second venue | OANDA v20 | Venue independence, and a test of whether the `Broker` abstraction is real |
| Account type | Proprietary firm evaluation, on MT5 | Externally imposed loss limits become a first-class part of the risk layer — spec §6.5 |
| Firms | Both profiles built; choice deferred to phase 7 | FundedNext bars automation at $50k and above; FTMO permits it at every size. Two profiles is also the test that the constraint model is general |
| Instruments | NAS100, US500, EURUSD, XAUUSD, XAGUSD | Correlated exposure is real here, making the correlation check load-bearing |
| Research tooling | TradingView / Pine, research only | Fast for prototyping; hard boundary before production |
| Language | Python | Ecosystem for testing and analysis, which MQL5 lacks |
| Repo | Framework public, `strategies/user/` private | Framework is the credential; edge stays private |
| LLM | Advisory layer only, deferred | Judgment layer, never the signal path |

**Rejected: MQL5 Expert Advisor.** Its one real advantage is that the Strategy Tester runs the same code as live, giving parity for free. But it costs the entire validation layer — no unit testing, no property testing, no CI, no dependency management — and its parity is shallower than it appears, because the Tester's fill simulation is a black box that can't be inspected or replaced.

**Rejected: TradingView webhook → bot → broker.** The common retail pattern. Alert delivery is best-effort and unlogged, the Pine tester and live path are different programs, and end-to-end backtesting becomes impossible.

**Rejected: Capital.com.** Viable, but ranks last on every criterion that matters here, and issues no read-only API keys — every key can trade, which can't be engineered around.

## 6. Open items

1. Historical data depth from the chosen MT5 broker, per instrument.
2. Whether the broker preserves the order `comment` field.
3. Bar interval — not yet chosen.
4. Symbol specifications and naming from `symbol_info()`.
5. If OANDA is pursued later: entity confirmation (UAE routes to OANDA Global Markets, BVI) and whether v20 is exposed on live accounts of that entity.
6. ~~Whether FundedNext offers MT5 and permits a Python process driving the terminal.~~ **Answered 2026-09-10.** Both firms offer MT5. Both treat a Python script as automated trading. But FundedNext permits it only on accounts **below $50,000**, requires a non-refundable add-on fee, and prohibits EAs incorporating third-party messaging applications. FTMO permits automation at every size to $200,000 at no extra cost. This reopened the venue choice rather than closing it — see spec §10, "On the venue choice".
7. Reset time and timezone of the accounting day, and what the daily limit anchors to, for both firms. FundedNext confirmed by support that both open and closed positions count toward both limits — the limits are therefore measured on equity. The anchor and reset boundary remain unconfirmed.
8. Exact rule figures for both firms, from their own rulebooks rather than comparison sites — which were found to contradict each other and the firms' own pages on nearly every number, including profit targets and whether the daily limit is measured on equity or balance.
9. ~~Eligibility from the UAE for both firms.~~ **Answered** — the operator holds accounts with both.

## 7. Deliberately deferred

Documented so they are recognised as decisions rather than oversights, and so nothing forecloses them.

**Multi-tenancy / productisation.** Running other people's strategies introduces untrusted code execution, credential custody, two-tier risk limits and likely regulatory obligations. In most jurisdictions, holding client credentials and executing orders on their behalf can constitute a regulated financial service regardless of who chose the strategy, and disclaimers don't reliably change that classification. To be taken up separately, with qualified legal advice, if ever. *(Not legal advice — a flag to get some.)*

**The safer adjacent version** — distributing software people run themselves with their own keys — carries a fraction of the exposure and is a better first product regardless. This is the shape the 1:1 offer takes.

**LLM advisory layer.** Spec §13. Its only prerequisite is the phase 0 logging schema, which is why that is not deferred.

**OANDA adapter.** After phase 8.

## 8. How the work runs

**Claude Code is the engineer; Claude in chat is the reviewer.** The two documents are the shared source of truth — start sessions by pointing at them. Neither assistant retains context reliably across sessions; the files do.

**One phase at a time, with exit criteria enforced.** The failure mode is accepting a phase because the tests are green when the tests were written from the same misunderstanding as the code. The spec's exit criteria are deliberately things an agent cannot satisfy by writing an agreeable test — `AlwaysLong` matching buy-and-hold to the cent is either true or it isn't.

**Phases 2 and 3 look trivial and matter most.** If `AlwaysLong` doesn't reproduce buy-and-hold exactly, the accounting is wrong, and every subsequent result is wrong in the same invisible way.

**Division of labour.** Chat-side is useful for reviewing output, arguing design, and asking whether a passing test proves anything. It cannot see the repo, run the code, or verify a backtest is honest. That part is the operator's.

## 9. Publication and positioning

**Publishing can begin at phase 5, not phase 10.** Nothing about the credibility case requires live results. "How I test that my backtester isn't lying to me" is a better artifact than a P&L curve, is honest, and exists in weeks rather than months. Write up each phase as it clears.

**Frame the 1:1 offer as engineering, not trading.** Helping someone build and test software is a service that can plainly be delivered. Advising on what to trade drifts toward regulated activity in most jurisdictions including the UAE. The engineering framing is also the more defensible pitch, being what is actually demonstrable.

**Indicative sequencing** (weeks, not commitments):

| Weeks | Work | Output |
|---|---|---|
| 1–3 | Phases 0–3, MT5 adapter | Public repo; `AlwaysLong` matches buy-and-hold |
| 4–6 | Phases 4–5 | Risk gate, walk-forward, random-entry baseline — first publishable artifact |
| 7–9 | Port a strategy from Pine, parity check, phase 6 | First honest answer on edge — second artifact |
| 10+ | Phases 7–8, practice account, one month | Mechanics validated; intervention rules drafted |
| After | Phase 10, minimum size | Cost measurement, not profit-seeking |

## 10. Standing caution

Phase 10 is designed as data-gathering at a size where the outcome doesn't matter. That design assumption is load-bearing given the current income situation, and shouldn't be relaxed because the practice month went well — practice fills are fiction, and a good month there says nothing about costs.

**The prop-firm route changes the shape of the risk, not its size.** An evaluation fee is a smaller and more bounded amount than funding a live account, and the firm's loss limits are externally enforced discipline that does not depend on the operator supplying it. Both are genuine advantages given the current situation.

The cost is a pass/fail deadline attached to money already spent. That is precisely the pressure §6.4 of the specification exists to manage, and it arrives from a direction the section did not anticipate: not "should I widen a limit after a drawdown" but "should I take a trade to reach a target before the fee is wasted". The intervention rules drafted in phase 8 should name this case explicitly.

**Do not buy an evaluation before phase 6.** The framework does not need one to be built — phases 0 through 6 touch no broker. Knowing where a strategy falls against the random-entry baseline before paying to prove it has an edge is the cheaper order, and reverses nothing if the answer is good.

Nothing in either document is financial advice. Leveraged trading carries substantial risk of loss, and no architecture makes a losing strategy profitable.
