# Operator Context

**Companion to:** `project-alignment.md`, `trading-engine-architecture.md`
**Purpose:** who is building this, with what background, and how to pitch explanations. Read alongside the other two at the start of every session.

The other two documents describe the system. This one describes the person building it, because the right answer to "how should this be explained" is different from the right answer to "what should be built."

---

## 1. Experience level

**The operator has no coding experience. None.** Not "rusty", not "knows a bit of Python". This is the starting point.

That is a deliberate premise of the project, not a problem to be worked around: Claude Code is the engineer, and the operator is the reviewer and decision-maker. But it means explanations must be pitched accordingly.

### What this means in practice

**Assume no vocabulary.** Terms like repository, virtual environment, dependency, lockfile, CI, linter, protocol, package manager, commit, branch, and terminal all need defining the first time they appear in a session. A one-line definition inline is enough; a lecture is not wanted.

**Never say "just" or "simply".** If a step were simple it would not need explaining.

**Give the click path, not the concept.** "Open the Extensions panel on the left sidebar, search for Ruff, click Install" beats "install the Ruff extension". Say which menu, which button, what the screen will look like afterwards.

**Say what success looks like.** Every instruction should end with what appears on screen when it worked. Without that there is no way to tell a completed step from a silently failed one.

**Anticipate the failure.** The common Windows traps — PATH not set, Microsoft Store Python stub, Git opening Vim, OneDrive redirecting folders — should be flagged before they happen, not diagnosed afterwards.

**Do not skip the "why" entirely.** The operator makes good architectural decisions and pushes back usefully when reasoning is exposed. Explain the reason briefly, then the steps. Reason first, then mechanics.

### What does *not* need dumbing down

The architecture, the reasoning, the trade-offs, the risk thinking. `project-alignment.md` and `trading-engine-architecture.md` were produced through discussion with this operator, and the judgement in them is sound. The gap is vocabulary and mechanics, not thinking. Condescension is the wrong correction.

---

## 2. Environment as it stands

| Thing | Status |
|---|---|
| OS | Windows, working machine (not a VPS) |
| Python | 3.11 64-bit, installed |
| Editor | VS Code, installed |
| MT5 | Terminal installed, account exists |
| TradingView | Account exists |
| Git | 2.55.0, installed and configured |
| `uv` | 0.12.12, installed. PATH entry added manually to user variables |
| GitHub | Public repo `trading-engine` and a private repo, both pushed |
| Prop firm accounts | FundedNext and FTMO, both held |
| VPS | Not needed until phase 7 |

**Week one is complete.** Project folder at `C:\trading\engine` with its own `.venv`, `uv.lock`, pytest running, `docs/` populated, `CLAUDE.md` in the root. Line endings normalised to LF via `.gitattributes`. No engine code written yet — phase 0 has not started.

**On Python 3.11.** Keep it. `Self` is available in 3.11; only `typing.override` requires 3.12, and `typing_extensions` supplies it. The `MetaTrader5` package supports 3.11. Do not ask the operator to reinstall Python.

**Development is native Windows, not WSL.** The `MetaTrader5` package talks to `terminal64.exe` over a Windows named pipe and cannot reach it from WSL. One environment, no exceptions.

---

## 3. Decisions made in conversation, not yet in the other documents

Recorded here so they are not re-litigated or forgotten.

**Three environments, not one.** Research (TradingView, browser), development (this Windows machine, phases 0–6, no broker needed), production (a rented always-on Windows server, phase 7 onward). The only early exception is a one-off data extraction from MT5, which happens on the development machine.

**Folder layout.** Everything under `C:\trading\`, with `data\` and `runtime\` as siblings of the repository rather than ignored folders inside it. Reason: `git clean -xdf` deletes ignored files, and one careless invocation should not be able to destroy historical data or persisted risk state.

**Not under `Documents`, `Desktop` or anything OneDrive syncs.** OneDrive holds file locks and syncs partially-written files.

**Private strategies as an installed package**, not a nested clone inside the public repository. The engine loads a strategy by an import string from configuration. Secondary benefit: it is a real test of P3 — if the engine can load a strategy from a separately versioned package with no path manipulation, the plugin contract is genuine.

**VS Code as the primary surface.** Most of the toolchain has VS Code extensions, so the command line reduces to a handful of commands. The Testing panel in particular gives phase exit criteria a visible green/red interface.

**MetaQuotes' free "MT5 VPS" is not usable.** It runs MQL5 Expert Advisors only, not Python. When the broker offers a free VPS, it is not the thing needed.

**The venue is a proprietary firm, not a retail broker account.** The operator holds accounts with both FundedNext and FTMO. This adds externally imposed loss limits to the risk layer — specification §6.5 — and means realised fills come from a simulated environment throughout, so the cost-model validation loop in Appendix C.4 cannot close on this venue.

**External limits are configuration, never code.** Both `fundednext_stellar_2step` and `ftmo_2step` profiles are built; which one is used is deferred to phase 7. Both floor modes — static and end-of-day trailing — are implemented together even though the default only needs static, because the trailing high-water mark lives in persisted `RiskState` and adding a field to persisted state later would mean a migration on a running system. Two profiles is also the test that the constraint model is genuinely general, in the same sense that a second broker adapter tests the `Broker` protocol.

**FTMO permits automation at every account size, free, with no add-on.** Verified 2026-09-10 from their strategies FAQ. Their published position is that mechanism is irrelevant provided behaviour complies. This is the main engineering argument for FTMO over FundedNext and the reason the current lean is FTMO.

**FundedNext bars automation at $50,000 and above.** Verified 2026-09-10 from their help centre. On FundedNext this engine may only run on an account below $50,000, with a non-refundable EA add-on fee. FTMO has no size ceiling and charges nothing extra. Neither support agent volunteered the threshold when asked whether Python automation was permitted — both answered the question asked, correctly and incompletely.

**The control plane must not use Telegram or WhatsApp.** FundedNext prohibits EAs incorporating third-party messaging applications. An earlier suggestion in this project to drive the §6.4 kill switch from a Telegram bot is withdrawn; the local control file stands, but whatever writes it must be local.

**Firm rules come from the firms' own rulebooks, dated and linked.** Comparison sites were checked during this work and contradicted each other, and the firms' own pages, on profit targets and on whether daily limits are measured on equity or balance. Any figure in a config file carries its source and verification date.

---

## 4. Proposed but not confirmed

**Scoping the project to phases 0–5 as the finish line**, with 6–10 as a decision made later from a published position. Rationale: phases 0–5 produce the credibility artifact described in `project-alignment.md` §9, have pass/fail exit criteria verifiable without deep code review, and take roughly six weeks rather than four months. The realistic failure mode for this project is stalling at phase 4 or 5 with nothing published, not choosing wrong tools.

**Status: proposed. The operator has not agreed to this.** Do not assume it in future sessions; ask.

---

## 5. The known gap

`trading-engine-architecture.md` §7.3 requires property tests *"written by you, not generated from the same spec that generated the implementation"*, and `project-alignment.md` §8 identifies the failure mode as accepting a phase because the tests are green when the tests came from the same misunderstanding as the code.

That reasoning is correct, and it means the validation layer — the part that makes this project worth building — is specifically the part that cannot be delegated to the same assistant writing the implementation.

Two things make this tractable rather than fatal. The exit criteria were designed well: *"`AlwaysLong` matches buy-and-hold to the cent"* is a number to compare, not code to audit. And reading Python well enough to review it is a far smaller skill than writing it.

**Therefore: learning enough Python to review generated code is a real workstream**, running alongside phases 0–3, not something picked up incidentally. Phases 0–3 are slow and simple by design, which makes them a good place to learn.

---

## 6. Session hygiene

Context does not survive reliably between chats. The files do.

At the **start** of a session: this file plus the other two.

At the **end** of a session: ask for the session's decisions to be written into `docs/state.md` — current phase, what was decided and why, what is blocked, what is next. Ten lines. This is the difference between resuming and re-deciding.

`CLAUDE.md` in the repository root serves the same purpose for Claude Code, which reads it automatically at the start of every session and otherwise has no memory of the codebase it built last week.
