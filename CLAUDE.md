# Trading Engine

A strategy-agnostic execution framework. It takes an arbitrary strategy, runs it identically over historical and live data, sizes it, gates it against risk limits, executes it, and reports honestly how it performed.

**Success is defined as: the system executes a strategy correctly and reports honestly whether that strategy has an edge.** Success is not defined as making money. Profitability is a property of the strategy, not the framework.

---

## Read these first, in this order

| File | What it is | When to read |
|---|---|---|
| `docs/state.md` | Current phase, recent decisions, what is blocked | Every session, first |
| `docs/trading-engine-architecture.md` | Full specification. The source of truth for what to build | Before writing any code |
| `docs/project-alignment.md` | Rationale and decision record. What was decided, what was rejected, and why | Before proposing a change to the design |
| `docs/operator-context.md` | Who is building this and how to pitch explanations | Every session |
| `docs/week-one-setup.md` | Historical record of environment setup. Not needed for ongoing work | Only if the environment breaks |

If a proposal conflicts with the architecture spec, the spec wins unless the operator explicitly changes it. Do not quietly relax a documented decision.

---

## Non-negotiables

These are design principles from the spec, restated here because they are the ones most easily violated by accident.

- **One engine, two wirings.** Backtest and live share the same orchestrator, differing only in feed, broker and clock. There is no separate backtester and no duplicated signal logic. If a change to the middle of the wiring is needed for live trading, the architecture has been violated.
- **Causality by construction.** Features are computed incrementally as bars arrive, from a bounded rolling window. Never vectorise over a complete dataframe. A component must be physically unable to see future data.
- **Strategy is a plugin behind a contract.** The engine imports no strategy module. It has no knowledge of indicators, regimes, levels or setups.
- **Risk has veto, not advice.** The risk gate can reduce or reject an order. It can never originate one. Its limits are configuration, not model outputs.
- **Determinism.** Same data, config and seed produces bit-identical output. Every run writes a manifest with commit hash, config hash, data range and seed.
- **Costs are a model, not a constant.** Spread, slippage, commission and financing come from a pluggable `CostModel`.
- **No LLM anywhere in the signal path.** Ever. Non-determinism destroys backtestability, reproducibility and falsifiability. The advisory layer in spec §13 observes and reports; it never sizes, enters, exits or changes a parameter.
- **TradingView never emits a live signal.** Research tool only. No webhooks in the trade path.
- **All datetimes are timezone-aware and UTC internally.** Never construct a naive datetime. The operator is UTC+4, the broker server is UTC+2/+3 with DST, and internal storage is UTC — three time bases, two of which shift twice a year.
- **External account constraints are configuration, never code.** The venue is a proprietary firm with externally imposed loss limits. No firm's rules — percentages, reset times, floor modes — may appear in a Python file. See spec §6.5. Changing firm must be a config edit.
- **The engine's own limits fire before the firm's.** A limit that never fires because someone else's fires first is not a limit. See §6.5.4 and Appendix C.3.
- **Never commit credentials.** This repository is public. Credentials live in `.env`, which is gitignored.

---

## Current state

**Phase: 0 — repo skeleton, core types, config loading, decision log schema.**

Exit criterion: config round-trips; the manifest records commit and config hash; a decision log entry captures full context.

See `docs/state.md` for anything more recent than this line.

---

## Working agreement

**One phase at a time.** Do not begin the next phase until the current exit criterion passes. Phases and criteria are in spec §9. Phases 2 and 3 look trivial and matter most — if `AlwaysLong` does not reproduce buy-and-hold exactly, the accounting is wrong and every later result is wrong in the same invisible way.

**Do not write the property tests in `tests/properties/`.** They are hand-written by the operator by design — see spec §7.3. Tests generated from the same specification as the implementation confirm internal consistency, not correctness. If you misunderstood the spec, you would write both the bug and the test that passes it.

**The operator has no coding experience** and is reviewing your output. This is a deliberate premise, not a problem to work around.

- Define vocabulary the first time it appears. One line inline, not a lecture.
- Explain what each change does and why, in plain language, before the mechanics.
- Never say "just" or "simply".
- State what success looks like on screen after each step.
- Do not condescend about the architecture, reasoning or trade-offs — the judgement in these documents is the operator's and it is sound. The gap is vocabulary and mechanics, not thinking.

**When claiming a test passes, be prepared to show it failing.** A test that has never failed may be testing nothing. "Show me this test failing when the thing it checks is broken" is a standing question.

**At the end of a session,** write the session's decisions into `docs/state.md`: current phase, what was decided and why, what is blocked, what is next. Ten lines.

---

## Environment

| Thing | Value |
|---|---|
| OS | Windows, native (not WSL — `MetaTrader5` needs a Windows named pipe) |
| Python | 3.11 |
| Dependencies | `uv`. Run commands as `uv run <command>` |
| Repo root | `C:\trading\engine` |
| Market data | `C:\trading\data` — outside the repo, deliberately |
| Logs and state | `C:\trading\runtime` — outside the repo, deliberately |
| Private strategies | `C:\trading\private`, installed as a package, loaded by import string from config |
| Venue | Proprietary firm evaluation on MT5. Both FundedNext and FTMO profiles built; firm choice deferred to phase 7. FundedNext bars automation at $50k and above |

`data\` and `runtime\` sit outside the repository so that `git clean -xdf` cannot destroy historical data or persisted risk state.

`MetaTrader5` is an optional dependency with a `sys_platform == 'win32'` marker so that CI on Linux is unaffected. Tests touching it are marked `requires_mt5` and skipped by default.

---

## Conventions

- Line endings are LF, enforced by `.gitattributes`. CI runs on Linux.
- Prices and quantities are `Decimal`, not float.
- Structured logging, one JSON object per event, append-only JSONL.
- Rejections are logged as fully as executions. The trades the system declined are as informative as the ones it took.
- Expected fill price is recorded alongside realised fill price, always.
- Time zones in play: operator UTC+4, broker server UTC+2/+3 with DST, internal UTC, and the firm's accounting-day boundary in its own timezone with DST. Four bases. Store timezones as IANA names and let the library handle DST — never by arithmetic.
