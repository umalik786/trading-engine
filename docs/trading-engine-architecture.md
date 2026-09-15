# Strategy-Agnostic Trading Engine — Architecture Specification

**Status:** design document, pre-implementation
**Version:** 3.4 — records the no-gap-fill rule for stored data (B.6)
**Previous:** 3.3 — `strategies/user/` clarified as a placeholder; real strategies load from a separately installed private package (§3)
**Previous:** 3.2 — FTMO automation position, server limits and simulated-venue status verified from primary sources (§10, §6.5.9)
**Previous:** 3.1 — records the FundedNext $50,000 automation ceiling (§10), reopens the venue choice, and constrains the §6.4 control plane against third-party messaging integrations
**Previous:** 3 — external account constraints (§6.5); prop-firm verification items in §10; simulated-venue caveat in Appendix C.4
**Previous:** 2 — MT5 primary adapter, intervention rules, decision log, TradingView boundary
**Purpose:** hand to Claude Code as the source of truth for a phased build

---

## 0. Scope and non-goals

**This document specifies an execution framework, not a strategy.** The framework's job is to take an arbitrary strategy, run it identically over historical and live data, size it, gate it against risk limits, execute it, and tell you honestly how it performed. Whether any particular strategy makes money is out of scope by design.

**Non-goals:**
- Predicting prices. No component of this system forecasts anything.
- Being fast. This is a bar-close system, not a latency-sensitive one. Correctness beats microseconds everywhere.
- Supporting every asset class on day one. The broker adapter is pluggable; ship one.
- **Multi-tenancy.** This is a single-user system running the operator's own strategies against the operator's own account. Running other people's strategies introduces untrusted code execution, credential custody, two-tier risk limits and likely regulatory obligations — a separate design problem, deliberately deferred. Nothing here forecloses it: the strategy contract and pluggable adapters are the right foundation for a platform. But no compromises are made for it now.

**A note on financial risk.** This document describes software architecture. It is not advice to trade, and no architecture makes a losing strategy profitable. The risk layer specified in section 6 limits how fast you can lose money; it does not prevent losing money.

---

## 1. Design principles

These are non-negotiable. Every downstream decision defers to them.

### P1 — One engine, two wirings

Backtest and live are **the same orchestrator** driven by different adapters. There is no `backtester.py` and no separate `live.py` containing duplicated signal logic. There is one `Engine` class, instantiated with either `(ReplayFeed, SimBroker)` or `(LiveFeed, LiveBroker)`.

*Why:* the single most expensive bug class in retail trading systems is silent divergence between the strategy you validated and the strategy that trades. Structural identity eliminates it rather than testing for it.

### P2 — Causality by construction

Features are computed **incrementally as bars arrive**, from a bounded rolling window, never by vectorising over a complete dataframe. A component physically cannot see future data because future data is not in memory when it runs.

*Why:* look-ahead bias is not one bug, it is a category. Fixing individual instances (e.g. swapping Viterbi for a forward pass in an HMM) closes one door in a house with many. Streaming computation closes the category.

### P3 — Strategy is a plugin behind a contract

The engine imports no strategy module. It receives a strategy object satisfying an interface. The engine has no knowledge of indicators, regimes, levels, or setups.

*Why:* this is the stated requirement, and it also forces the risk layer, sizer and executor to be genuinely general rather than accidentally coupled to one idea.

### P4 — Risk has veto, not advice

The risk gate sits between sizing and execution. It can reduce or reject an order. It cannot originate one. It knows nothing about why a trade was proposed. Its limits are hardcoded configuration, not model outputs.

*Why:* a risk layer that can be reasoned with by the strategy is not a risk layer.

### P5 — Determinism and reproducibility

Given the same input data, config, and seed, the engine produces bit-identical output. Every run writes a manifest recording code commit hash, config hash, data range and seed. Any result you cannot reproduce is not a result.

### P6 — Costs are a first-class model, not a constant

Spread, slippage, commission and financing are produced by a pluggable `CostModel` that sees the order and current market state. The same model runs in backtest and is used live to score realised fill quality against expectation.

*Why:* the gap between backtest and reality is mostly costs. A flat "0.05% slippage" assumption hides exactly the conditions — wide spreads, thin books, news — where strategies actually fail.

---

## 2. Component contracts

These interfaces are the architecture. Implementations are replaceable; contracts are not.

### 2.1 Core data types

```python
@dataclass(frozen=True)
class Bar:
    symbol: str
    ts_open: datetime      # timezone-aware, always UTC internally
    ts_close: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_final: bool         # False for in-progress bars; strategies see finals only

@dataclass(frozen=True)
class TargetPosition:
    symbol: str
    quantity: Decimal          # signed; negative = short; 0 = flat
    # OR, for allocation-style strategies:
    weight: Optional[Decimal]  # fraction of equity; engine converts to quantity
    stop_price: Optional[Decimal]
    take_profit: Optional[Decimal]
    reason: str                # human-readable; logged with every decision
    confidence: Optional[Decimal]  # 0-1, used by sizer if strategy provides it

@dataclass(frozen=True)
class Order:
    client_order_id: str   # deterministic; see §5.2
    symbol: str
    side: Literal["buy", "sell"]
    quantity: Decimal
    order_type: Literal["market", "limit", "stop"]
    limit_price: Optional[Decimal]
    stop_price: Optional[Decimal]
    intent_id: str         # links back to the TargetPosition that produced it

@dataclass(frozen=True)
class Fill:
    order_id: str
    client_order_id: str
    symbol: str
    quantity: Decimal
    price: Decimal
    fees: Decimal
    ts: datetime
```

### 2.2 Feed adapter

```python
class Feed(Protocol):
    def stream(self) -> Iterator[Bar]:
        """Yield final bars in strictly ascending ts_close order.

        ReplayFeed: reads historical data from disk/API.
        LiveFeed:   blocks until each bar closes, then yields.

        Both MUST yield identical Bar objects for the same market period.
        Neither may yield a bar whose ts_close is in the future.
        """

    def warmup(self, n: int) -> list[Bar]:
        """Bars before the run start, for feature initialisation only.
        These are never passed to the strategy."""
```

### 2.3 Feature pipeline

```python
class FeatureSet(Protocol):
    def update(self, bar: Bar) -> None:
        """Ingest one bar. MUST be O(1) or O(window), never O(history)."""

    def snapshot(self) -> Mapping[str, Any]:
        """Current feature values. Contains NO forward-looking information."""

    @property
    def is_ready(self) -> bool:
        """False until enough bars have been ingested for all features to be valid."""
```

Regime detection — an HMM, a volatility classifier, anything — is **a feature provider, not a core component**. It implements `FeatureSet` and appears in `snapshot()` alongside moving averages. This is a deliberate demotion from the reference framework, where the regime model sits at the centre and everything else hangs off it. A strategy that wants regime awareness reads it from features; a strategy that doesn't, ignores it.

### 2.4 Strategy plugin

```python
class Strategy(Protocol):
    def on_bar(
        self,
        bar: Bar,
        features: Mapping[str, Any],
        portfolio: PortfolioView,   # read-only current positions and equity
    ) -> list[TargetPosition]:
        """Return desired positions. Empty list = no change from current.

        MUST be a pure function of its arguments.
        MUST NOT: read the clock, perform I/O, call a broker, mutate global state,
                  or use randomness without an injected seeded generator.
        """

    @property
    def required_features(self) -> set[str]:
        """Declared upfront so the engine can validate wiring at startup."""

    @property
    def warmup_bars(self) -> int:
        """How many bars before the strategy should be allowed to trade."""
```

The purity constraint is what makes everything else possible: it's testable in isolation, identical in backtest and live, and trivially replayable.

### 2.5 Position sizer

```python
class Sizer(Protocol):
    def size(
        self,
        target: TargetPosition,
        portfolio: PortfolioView,
        features: Mapping[str, Any],
    ) -> Decimal:
        """Convert an intent into a concrete quantity."""
```

Separated from the strategy so you can vary sizing (fixed fractional, volatility-scaled, Kelly-capped, confidence-weighted) without touching signal logic — and A/B one against another on the same signals.

### 2.6 Risk gate

```python
class RiskGate(Protocol):
    def evaluate(self, order: Order, portfolio: PortfolioView, state: RiskState) -> RiskDecision:
        """Returns APPROVE, REDUCE(new_quantity), or REJECT(reason).
        Every decision is logged regardless of outcome."""

    def check_circuit_breakers(self, portfolio: PortfolioView, state: RiskState) -> BreakerAction:
        """Called every bar, independent of whether an order exists."""
```

### 2.7 Broker adapter

```python
class Broker(Protocol):
    def submit(self, order: Order) -> BrokerOrderRef:
        """MUST be idempotent on client_order_id. Resubmitting the same
        client_order_id MUST NOT create a second order."""

    def cancel(self, order_ref: BrokerOrderRef) -> None: ...

    def positions(self) -> list[Position]:
        """Ground truth. The engine trusts this over its own memory."""

    def account(self) -> AccountState: ...

    def is_market_open(self, symbol: str) -> bool: ...
```

`SimBroker` implements this against the `CostModel`; `LiveBroker` implements it against a real API. The engine cannot tell them apart.

### 2.8 Cost model

```python
class CostModel(Protocol):
    def fill_price(self, order: Order, bar: Bar, book: Optional[BookSnapshot]) -> Decimal:
        """Model the realistic fill, including spread and market impact."""

    def fees(self, order: Order, fill_price: Decimal) -> Decimal: ...

    def financing(self, position: Position, bar: Bar) -> Decimal:
        """Overnight/swap costs. Zero for cash equities intraday."""
```

Implement at minimum: `ZeroCostModel` (for engine testing only, never for evaluation), and `SpreadAwareCostModel` with spread as a function of time-of-day and volatility rather than a constant.

### 2.9 Decision log

**This must be built in phase 0. It cannot be retrofitted.** Decision context that was not captured at the time is unrecoverable, and everything in §13 depends on it.

One record per bar in which the engine made or declined to make a decision:

```python
@dataclass(frozen=True)
class DecisionRecord:
    ts: datetime
    symbol: str
    bar: Bar
    features: Mapping[str, Any]        # full snapshot at decision time
    strategy_output: Optional[TargetPosition]
    strategy_reason: str               # the strategy's stated rationale
    sized_quantity: Optional[Decimal]
    risk_decision: RiskDecision        # APPROVE / REDUCE / REJECT
    risk_reason: str                   # why, in every case including approval
    order: Optional[Order]
    expected_fill: Optional[Decimal]   # from the cost model
    realised_fill: Optional[Decimal]   # backfilled when the fill arrives
    account_snapshot: Mapping[str, Any]
```

Two properties matter. **Rejections are logged as fully as executions** — the trades the system declined are as informative as the ones it took, and they are invisible in a P&L curve. And **expected fill is recorded alongside realised fill**, which is what makes §C.4 cost-model validation possible.

The difference between a log that says `sell 0.5 XAUUSD @ 2043.20` and one carrying the above is the difference between a system you can interrogate and one you can only watch.

---

## 3. Repository structure

```
engine/
  core/
    types.py            # Bar, Order, Fill, TargetPosition, ...
    engine.py           # THE orchestrator. Used by backtest and live alike.
    portfolio.py        # PortfolioView, position accounting
    clock.py            # ReplayClock | WallClock
  feeds/
    base.py             # Feed protocol
    replay.py
    live_<provider>.py
  features/
    base.py             # FeatureSet protocol
    technical.py        # rolling indicators, streaming
    regime.py           # optional HMM / classifier, as a FeatureSet
  strategies/
    base.py             # Strategy protocol
    reference/          # See §7 — engine validation strategies
      always_long.py
      always_flat.py
      random_entry.py
      perfect_foresight.py
    user/               # placeholder only — see note below
  sizing/
  risk/
    gate.py
    breakers.py
    state.py            # persisted; survives restarts
  brokers/
    base.py
    sim.py
    <provider>.py
  costs/
  persistence/
    state_store.py      # append-only event log + snapshot
    reconcile.py        # §5.3
  validation/
    walkforward.py      # §8
    metrics.py
    parity.py           # §7.2
  observability/
    logging.py          # structured, one event per decision
    dashboard.py
config/
  base.yaml
  strategies/<name>.yaml
tests/
  unit/
  properties/           # hand-written, adversarial — see §7.3
  golden/               # recorded replays with expected outputs
```

**On `strategies/user/`.** This directory is a placeholder in the public repository, holding only a `.gitkeep` and a README. Real strategies live in a separately versioned private package, installed with `uv add --editable`, and loaded by import string from configuration — e.g. `my_strategies.some_strategy:Strategy`.

Two reasons. The public repository then has no private-shaped gap in it, so there is nothing to commit by accident. And loading a strategy from a separately installed package with no `sys.path` manipulation is a real test of P3: if the engine can do that, the plugin contract is genuine rather than a convention that happens to hold because everything sits in one tree.

---

## 4. The two wirings

```python
# Backtest
engine = Engine(
    feed=ReplayFeed(path="data/2023-2025.parquet"),
    features=FeatureSet(...),
    strategy=MyStrategy(config),
    sizer=VolatilityScaledSizer(config),
    risk=RiskGate(config),
    broker=SimBroker(cost_model=SpreadAwareCostModel(config)),
    clock=ReplayClock(),
)
result = engine.run()

# Live — the only lines that change are feed, broker, clock
engine = Engine(
    feed=LiveFeed(provider_config),
    features=FeatureSet(...),        # identical
    strategy=MyStrategy(config),     # identical
    sizer=VolatilityScaledSizer(config),  # identical
    risk=RiskGate(config),           # identical
    broker=LiveBroker(credentials),
    clock=WallClock(),
)
engine.run()
```

If a change ever needs to be made to the middle four arguments for live trading, the architecture has been violated.

---

## 5. State, restart and reconciliation

### 5.1 What is authoritative

The **broker** is authoritative for positions and account equity. The **local state store** is authoritative for risk state (daily P&L accumulator, breaker status, lock files) and for the audit log. In-memory state is authoritative for nothing.

### 5.2 Order idempotency

`client_order_id` is deterministic: `hash(strategy_name, symbol, bar.ts_close, intent_index)`. If the process dies after submitting but before recording the response, the retry on restart carries the same ID, and the broker rejects the duplicate. This turns the worst failure mode in automated trading — the accidental double position — into a no-op.

### 5.3 Startup reconciliation

Before the first bar is processed, in order:

1. Load persisted risk state. If a breaker lock file exists, halt and exit.
2. Fetch actual positions and account state from the broker.
3. Fetch recent order history and match against the local order log.
4. Log any discrepancy loudly. If positions exist that the log doesn't explain, **halt** — do not trade around an unknown position.
5. Warm up the feature pipeline from historical bars.
6. Only then enter the main loop.

This routine is absent from the reference framework and is the most likely cause of a real-money incident.

---

## 6. Risk layer specification

### 6.1 Structure

Two independent tiers:

**Per-order checks** (in `RiskGate.evaluate`): max position size, max notional exposure, max leverage, per-trade risk cap, correlation with existing positions, spread ceiling, market-hours check, sanity bounds on stop distance.

**Circuit breakers** (in `check_circuit_breakers`, run every bar regardless of orders): intraday loss threshold → halve sizing; larger intraday loss → flatten and stand down for the session; rolling-period loss → reduce sizing; peak-to-trough drawdown threshold → **halt and write a lock file requiring manual deletion**.

The lock file is deliberate friction, borrowed directly from the reference framework and worth keeping. It converts "just restart it" into "understand what happened first."

### 6.2 On threshold values

**Do not copy anyone's numbers, including the ones in the video.** Thresholds calibrated for a daily-rebalanced equity portfolio are wrong for an intraday system taking several trades a session, where a "-3% day" may be entirely ordinary.

Derive them: run your strategy over the full backtest, extract the distribution of daily P&L, and set breakers where a day is genuinely anomalous rather than merely bad — roughly the 99th percentile of historical daily losses for the hard stop, and the 95th for the sizing reduction. Re-derive whenever the strategy changes materially. Record the derivation in the config file as a comment so future-you knows the numbers weren't arbitrary.

### 6.3 Risk state persistence

`RiskState` is written to disk on every mutation, not on shutdown. A process killed mid-session must not wake up with its daily loss counter reset to zero.

### 6.4 Intervention rules

Automation removes execution error. It does not remove the human — it relocates the human's decisions one level up, to: should I pause during this news week, was that breaker firing signal or noise, has the strategy stopped working or is this a normal losing stretch, should I redeploy after this drawdown. These are the decisions that determine whether an automated system survives, and they are made under the same emotional pressure as discretionary trading, but are harder to notice because they don't feel like trading.

This section specifies controls over those decisions. It is part of the risk layer, not the dashboard.

**The governing principle is asymmetric friction: the system can always be made safer instantly; making it riskier costs something.**

**Category 1 — operational controls. Free, immediate, no confirmation.**
Kill switch, flatten all, pause new entries, disable an instrument, reduce size, tighten any limit. One action, available from a phone, no dialogs. There is never a case where the operator should be slowed down while trying to reduce exposure.

*Implementation constraint.* The authoritative control is a local file that the engine polls every bar, so that reducing exposure never depends on a third-party service being reachable. **Whatever writes that file must not be a third-party messaging integration:** FundedNext prohibits EAs incorporating applications such as Telegram or WhatsApp (§10 item 5b), and a control channel that breaches the venue's rules is not a control. A local dashboard on the production host, or a remote desktop session, satisfies the requirement without the exposure.

*Venue interaction.* Some firms prohibit mixing automated and manual execution on one account. Where that applies, closing a position through the terminal interface is a manual trade and may constitute a breach — so every intervention, including flattening, must go through the engine. The control plane therefore stops being a convenience and becomes the only permitted route to intervene, which is why the file mechanism above belongs in phase 7 rather than waiting for the dashboard in phase 9.

**Category 2 — loosening changes. Deliberately expensive.**
Raising a drawdown limit, increasing position size or leverage, widening a spread ceiling, disabling a filter, shortening a cooldown. Four mechanisms apply:

1. **Deferred effect.** The change is proposed, not applied. It takes effect at the next session boundary or after a configured delay, whichever is later. The moment that produced the urge has passed by the time it lands.
2. **Mandatory written reason.** Free text, minimum length, stored with the change. Written for the operator reading it back in three months, not for anyone else.
3. **Blocked while triggered.** Risk parameters are frozen while a breaker is active. A drawdown limit cannot be raised while the drawdown breaker is firing. If the lock file exists, parameters stay frozen until it is deleted and the system has run clean for a configured period.
4. **Append-only history.** Every change is a versioned record: parameter, old value, new value, timestamp, written reason, and a snapshot of system state at the time — equity, open drawdown, recent trade count, active breakers. Committed to the repository, not only to a database.

**Schema:**

```python
@dataclass(frozen=True)
class ParameterChange:
    change_id: str
    parameter: str
    old_value: Any
    new_value: Any
    direction: Literal["tighten", "loosen"]
    proposed_at: datetime
    effective_at: datetime          # == proposed_at for tightening
    reason: str                     # required for loosening
    state_snapshot: Mapping[str, Any]
    applied: bool
```

**Why the log matters.** After six months this is queryable data about the operator: how often limits were loosened, what the drawdown was at each point, and what happened in the thirty days following. Most discretionary traders have no record of their own override patterns. This produces one, with stated reasons attached.

The interface does not create discipline. Someone can build all of this and override daily. What it does is make the absence of discipline visible and undeniable, which is a precondition for addressing it rather than a substitute.

**Draft the rules during phase 8, not phase 10** — while the practice account is running, nothing is at stake, and it is still possible to think clearly. A month of watching the system under those rules with simulated money is how impractical rules get found cheaply.

### 6.5 External account constraints

Some venues impose loss limits from outside the system. Proprietary trading firms are the clearest case: an account has a daily loss limit and a maximum loss limit, both enforced by the firm, and breaching either terminates the account. A personal live account has no such limits, only the broker's margin close-out (Appendix C.3).

This section specifies how those constraints are represented. It is a generalisation of the argument already made in C.3: **a limit that never fires because someone else's fires first is not a limit.**

#### 6.5.1 Principle

**External constraints are configuration, never code.** No firm's rules appear in a Python file. The engine implements a general capability — "an external party imposes loss limits on this account" — and each venue is a named profile.

Three consequences follow, and all three are requirements rather than side effects:

- Changing firm is a config edit.
- Moving to a personal account means removing the external limits and keeping only the operator's own.
- Supporting a second firm without touching engine code is the test that the abstraction is real, in the same sense that Appendix B treats a second broker adapter as the test of the `Broker` protocol.

#### 6.5.2 Required capabilities

Three things the risk layer does not currently do.

**Equity evaluated every bar.** External daily limits are typically measured on equity — balance plus unrealised P&L on open positions, adjusted for swaps and commissions — not on closed results. The limit can therefore be breached with no order placed, by an open position drifting. `check_circuit_breakers` already runs every bar (§6.1); it must now receive live equity including floating P&L, and must be able to flatten pre-emptively rather than only decline new entries.

**A configurable accounting-day boundary.** These limits reset at a specific hour in a specific timezone — commonly midnight in the firm's local time, which is subject to daylight saving. This is a fourth time base alongside operator-local, broker-server and internal UTC. It is configuration, not a constant, and is stored as an IANA timezone name so DST is handled by the library rather than by arithmetic.

**Two floor modes.** `static` anchors the maximum loss to the initial balance and never moves. `trailing_eod` recalculates against the highest balance recorded at the accounting-day boundary, and only ever rises. Static is the simpler case and is the default; trailing is implemented at the same time because it requires a persisted field, and adding a field to persisted `RiskState` (§6.3) later means a state migration on a running system.

#### 6.5.3 Configuration

```yaml
account_constraints:
  profile: fundednext_stellar_2step
  rules_verified: "2026-09-10"       # see 6.5.6
  rules_source: "<url of the firm's own rulebook>"

  accounting_day:
    reset_time: "00:00"
    timezone: "Europe/Prague"        # IANA name, DST handled by library

  daily_loss:
    external_pct: 5.0                # the firm's limit
    internal_pct: 3.0                # ours, fires first — see 6.5.4
    measured_on: equity              # equity | closed_balance
    anchor: initial_balance          # initial_balance | day_open_balance

  max_loss:
    external_pct: 10.0
    internal_pct: 7.0
    mode: static                     # static | trailing_eod
```

A personal live account omits every `external_pct`. The engine then enforces only the internal values, and the rest of the machinery is inert rather than absent.

#### 6.5.4 Deriving the internal margin

The internal limit is not a round number chosen for comfort. Two distinct effects require the gap, and both are measurable.

**Bar-close latency.** The engine acts at bar close; price moves between closes. The relevant quantity is the distribution of adverse intra-bar excursion at the chosen interval, per instrument — available from historical data once §10 item 1 is answered.

**Exit slippage.** A breaker firing produces a market order under conditions that are, by construction, unfavourable. The `CostModel` (§2.8) already estimates this.

Set the internal limit such that the sum of a pessimistic-tail intra-bar excursion and modelled exit slippage still lands inside the external limit. Record the derivation as a comment in the config, per the practice established in §6.2.

Until historical data exists to derive it, use a placeholder of 60% of the external limit and mark it explicitly as underived.

#### 6.5.5 Persisted state

Added to `RiskState` (§6.3), written on every mutation:

| Field | Purpose |
|---|---|
| `accounting_day_start_ts` | Boundary of the current accounting day, in UTC |
| `balance_at_day_start` | Anchor for the daily limit |
| `highest_eod_balance` | High-water mark for `trailing_eod`. Maintained even when mode is `static` |
| `external_limits_breached` | Latch. Once set, only manual clearing resets it |

`highest_eod_balance` is deliberately maintained in both modes. It costs one update per day and removes the need for a state migration if the profile later changes to a trailing venue.

#### 6.5.6 Rule provenance

Firm rules change without notice, and third-party summaries of them disagree with each other and with the firms' own pages. Two requirements:

- Every profile records the date its numbers were verified and the URL of the **firm's own rulebook**. Comparison sites are not acceptable sources.
- A profile whose `rules_verified` date is older than a configured threshold produces a startup warning.

#### 6.5.7 Interaction with §6.4

External constraints are not parameters the operator may loosen. `external_pct` values are facts about the account, not preferences: raising one does not raise the firm's limit, it only removes the engine's knowledge of it.

`internal_pct` values are operator parameters and fall under §6.4 in full — loosening one is a Category 2 change requiring deferred effect, written reason, and append-only history. Narrowing the gap to an external limit after a losing session is precisely the decision §6.4 exists to slow down.

#### 6.5.8 Exit criteria

Property tests, hand-written per §7.3:

- Under any randomised sequence of bars and fills, equity never crosses an external limit without the internal breaker having fired first.
- The accounting-day boundary is computed correctly across a DST transition in the configured timezone, in both directions.
- `highest_eod_balance` never decreases.
- A process killed mid-session and restarted resumes with the same accounting-day anchor and high-water mark.
- Switching profile from `static` to `trailing_eod` requires no code change and no state migration.

#### 6.5.9 Note on simulated venues

Prop-firm accounts are simulated environments, including after funding. FTMO's own site states that it provides services of simulated trading and educational tools only, does not act as a broker, and accepts no deposits (verified 2026-09-10). Realised fills therefore reflect the firm's simulator rather than a market. This does not affect anything in this section, but it does mean the cost-model validation loop in Appendix C.4 cannot close on such a venue: comparing expected against realised fill measures the simulator's behaviour, not the market's. Record cost-model validation as unresolved for as long as the only venue is simulated.

---

## 7. Validation strategy

This section is the largest addition to the reference framework, which relies on a suite of agent-written tests that verify the code does what the same agent thought it should do.

### 7.1 Reference strategies — validating the engine

Because any strategy can be plugged in, plug in strategies whose correct behaviour is known *a priori*. These test the engine, not the strategy:

| Strategy | Expected result | Catches |
|---|---|---|
| `AlwaysLong` | Matches buy-and-hold minus modelled costs, within tolerance | Accounting errors, cost double-counting, missed bars |
| `AlwaysFlat` | Exactly zero P&L, zero orders | Phantom trades, state leakage |
| `PerfectForesight` (peeks at next bar — test only) | Enormous, near-monotonic returns | If it *doesn't* win big, the engine is broken |
| `RandomEntry` (seeded) | Distribution centred slightly below zero after costs | Gives you the null distribution |

`RandomEntry` under identical risk rules is the benchmark that actually matters. Run it a few hundred times with different seeds to build a distribution, then ask where your real strategy's result falls in it. A strategy that doesn't clear the random baseline convincingly has no demonstrated edge — its apparent performance is coming from the sizing and risk rules, not the signal.

### 7.2 Parity harness

An automated test that runs a fixed historical window through **both** wirings — replay feed with sim broker, and live wiring pointed at a recorded/mocked feed — and asserts the resulting trade lists are identical. Run in CI. This is the test that guards P1, and its absence is what allows systems to drift.

### 7.3 Property tests, hand-written

Written by you, not generated from the same spec that generated the implementation. Assert invariants rather than specific outputs:

- Feeding bars in order produces the same result as feeding the same bars after a mid-stream restart.
- No order is ever submitted with a client_order_id already in the log.
- Realised position never exceeds the risk gate's stated maximum, for any random input sequence.
- Shuffling the *future* portion of a dataset never changes decisions already made (the strongest look-ahead test available).
- The engine never submits an order when `is_market_open` is False.

### 7.4 Golden replays

Record a handful of interesting historical windows — a crash, a quiet range, a gap, a news spike — with the exact expected output. Any change to engine code that alters these outputs must be an intentional, reviewed decision.

---

## 8. Walk-forward validation

Rolling windows: train on an in-sample period, evaluate on the subsequent out-of-sample period, roll forward, never re-using out-of-sample data for fitting.

**Nested selection is mandatory.** Any hyperparameter — indicator lookbacks, thresholds, or the number of regimes in a state model — must be selected *inside each training window*, using only that window's data. Selecting once globally and then running the walk-forward with that choice leaks out-of-sample information into a hyperparameter, and produces optimistic results that will not repeat. This is the subtlest flaw in the reference framework: it fixes look-ahead at inference time while leaving it open at model-selection time.

**Report per-regime and per-confidence-bucket**, so you can see whether performance is broad or concentrated in a handful of periods.

**Benchmarks:** buy-and-hold, a simple trend-following rule, and the random-entry distribution from §7.1. Report your result's percentile against the random distribution, not just whether it beat the mean.

**Stress overlays:** inject synthetic gaps, spread blowouts and liquidity holes into out-of-sample windows and confirm the risk layer responds as specified.

---

## 9. Build phases

Each phase has an exit criterion. Do not start the next phase until the current one passes. Give Claude Code one phase at a time — the reference framework's approach of scaffolding everything first is right, but the temptation to accept a phase because the tests are green is the thing to resist.

| Phase | Deliverable | Exit criterion |
|---|---|---|
| 0 | Repo skeleton, types, config loading, **decision log schema (§2.9)** | Config round-trips; manifest records commit + config hash; a decision log entry captures full context |
| 1 | Feed protocol, ReplayFeed, streaming feature pipeline | Property test §7.3 (future-shuffle) passes |
| 2 | Strategy protocol, `AlwaysLong` / `AlwaysFlat`, portfolio accounting, SimBroker with ZeroCostModel | `AlwaysLong` matches buy-and-hold to the cent |
| 3 | Cost model, sizer | `AlwaysLong` matches buy-and-hold minus a cost figure you can derive by hand |
| 4 | Risk gate, circuit breakers, **external account constraints (§6.5)** | Property tests: limits never breached under randomised adversarial input; §6.5.8 exit criteria pass |
| 5 | Walk-forward engine and metrics, `RandomEntry` baseline | Random-entry distribution generated and plotted |
| 6 | Your first real strategy | Clears the random baseline at a percentile you specify *before* looking |
| 7 | LiveBroker, idempotency, reconciliation | Parity harness §7.2 green; kill the process mid-position and confirm clean recovery |
| 8 | Practice-account trading; **draft intervention rules (§6.4)** | Minimum one month. Validates *mechanics* — see caveat below. Rules written and tested against a live-running system |
| 9 | Dashboard and alerting | — |
| 10 | Live capital, minimum position size | Runs for a defined period as cost measurement, not profit-seeking |

Phases 2 and 3 look trivial and are the most valuable in the whole build. If `AlwaysLong` doesn't reproduce buy-and-hold exactly, your accounting is wrong, and every result the system ever produces afterwards will be wrong in the same invisible way.

**Caveat on phase 8.** A broker practice account fills at quoted prices with none of the widening, rejection or slippage of live execution. Phase 8 therefore validates mechanics — session refresh, reconciliation, breaker firing, weekend-gap survival, no crashes over a month — and tells you nothing about costs. Cost validation begins at phase 10 with minimum size. Enter that phase expecting to gather data, not returns, and size accordingly.

---

## 10. Decisions

### Settled

| Decision | Choice | Consequence |
|---|---|---|
| Broker / venue | **MT5 first**, OANDA second | See Appendices A and B |
| Account type | **Proprietary firm evaluation**, MT5 platform | Externally imposed loss limits — see §6.5. Operator holds accounts with FundedNext and FTMO |
| Constraint profile | **Both `fundednext_stellar_2step` and `ftmo_2step` implemented.** Which is used at phase 7 is deliberately deferred | See "On the venue choice" below. Static and trailing floor modes are both built regardless (§6.5.2) |
| Research tooling | TradingView / Pine, research only | See §12 |
| Instruments | `NAS100_USD`, `SPX500_USD`, `EUR_USD`, `XAU_USD`, `XAG_USD` | Multi-instrument from day one — sizer needs correlation checks |
| Language | Python | Assumed throughout; architecture does not require it |
| Tenancy | Single user | §0 non-goals |
| Regime model | Deferred | It's a `FeatureSet`; don't build one before a strategy needs it |

**On multi-instrument.** Indices, FX and metals in one portfolio means correlated exposure is real, not theoretical — gold and silver move together, and both trade against the dollar alongside EUR/USD. The `RiskGate` correlation check (§6.1) is therefore load-bearing rather than nice-to-have. Compute rolling correlation from the feature pipeline and cap aggregate exposure across correlated groups, not just per instrument.

**On the venue choice.** The venue is a proprietary firm on MT5, but *which* firm is deliberately open until phase 7. FundedNext permits this engine only below $50,000 and charges a non-refundable add-on fee; FTMO permits automation at every size up to $200,000 at no additional cost, and its published position on mechanism is explicitly agnostic. Against that, FundedNext's static maximum-loss floor is marginally simpler to model than FTMO's end-of-day trailing floor — but both floor modes are implemented regardless (§6.5.2), so this is not a differentiator in engineering terms.

Deferring the choice costs nothing: phases 0 through 6 touch no broker. Firm rules also change on a shorter cycle than this build, so a decision made now would need re-verifying anyway. Re-read both rulebooks at phase 7 and choose then.

**On broker ordering.** MT5 comes first for two reasons. It is the retail standard, so a framework built on it is usable by others without modification — which matters given the intent to help other people build their own version. And it is already familiar, which matters more than API elegance when momentum is the scarce resource. OANDA follows as the second adapter, where its value is as much architectural as practical: see Appendix B.

### Still to verify before phase 0

1. **Historical data depth available from the chosen MT5 broker** for each instrument, at the chosen bar interval. MT5 serves history from the broker's own server and depth varies widely. This determines whether meaningful walk-forward validation is possible at all.
2. **Whether the broker preserves the order `comment` field.** Some overwrite it. Determines whether §5.2 idempotency can key on it or must rely wholly on the durable-intent-log fallback.
3. **Bar interval.** Drives feed design, warmup length, and how much intraday cost modelling matters. Not yet chosen.
4. **Symbol specifications** from `symbol_info()`: contract size, minimum and step volume, digits, margin requirement and swap rates per instrument. These feed the sizer and cost model directly. Symbol naming is broker-specific (`XAUUSD`, `XAUUSD.m`, `GOLD`) and must live in adapter configuration.

Items 1, 2 and 4 are answered from a free-trial or existing evaluation account on the chosen firm's MT5 server, not from a generic broker. Depth in particular cannot be shopped for once a firm is chosen, so verify before paying for an evaluation.

### Also to verify, from the firm's own rulebook

Third-party comparison sites disagree with each other and with the firms' own pages on nearly every figure. Use primary sources only, and record the date and URL per §6.5.6.

5. **~~Does the firm permit external algorithmic execution~~ — ANSWERED, both firms. VERIFIED 2026-09-10.** FTMO's published position is that trading style is the trader's own — discretionary, algorithmic or EA-driven alike — provided it is legitimate, conforms to real market conditions and does not resemble forbidden practices. **No account-size ceiling and no add-on fee appear anywhere in that statement.** Source: `ftmo.com/en/faq/which-instruments-can-i-trade-and-what-strategies-am-i-allowed-to-use/`. FTMO also does not require a stop-loss, though the risk layer imposes one regardless. FundedNext's help centre states that a Python script executing trades is treated as automated trading and falls under its EA rules — *subject to the account-size ceiling in item 5a*.
5a. **FundedNext imposes a $50,000 automation ceiling — VERIFIED 2026-09-10.** EAs, bots and automated tools are permitted on MT4/MT5 only for accounts **below $50,000**. Accounts of $50,000 and above must be traded fully manually, in both Challenge and funded stages. The restriction extends to tools that place no trades and only modify stop loss, take profit or lot size. It also applies to cTrader and Match-Trader at any size. Source: `help.fundednext.com/en/articles/8020763`. **Consequence: on FundedNext this engine may only run on an account below $50,000, and the EA add-on fee is required and non-refundable.** FTMO has no equivalent size ceiling.
5b. **FundedNext prohibits EAs incorporating third-party applications such as Telegram or WhatsApp — VERIFIED 2026-09-10.** Constrains the §6.4 control plane; see the note there. FTMO's position on this is unverified.
5c. **FundedNext caps allocation at $300,000 per strategy** across accounts, and bans EAs designed specifically to pass prop-firm challenges, with a published named list.
6. **~~Does the firm offer MT5~~ — ANSWERED.** Both firms offer MT5.
7. **Exact rule figures for the specific plan held**: daily loss percentage, whether measured on equity or closed balance, its anchor, maximum loss percentage, floor mode, and the accounting-day reset time and timezone. These populate the §6.5.3 profile.
8. **Profit targets per phase.** Reported inconsistently across sources for both firms; confirm before selecting a venue on that basis.
9. **Prohibited practices and any news-trading restriction**, and whether a time-based filter is therefore required in strategy code. FTMO maintains a separate Forbidden Trading Practices page (`ftmo.com/en/forbidden-trading-practices/`) which is where the specific prohibitions live; the strategies FAQ only links to it. **Unread — read before phase 7.** FundedNext confirmed news trading allowed on the Stellar 2-Step, so no time-based filter is required on that venue.
10. **~~Request-rate ceiling~~ — ANSWERED for FTMO, VERIFIED 2026-09-10.** FTMO's platform servers impose **200 orders at a time** and **2,000 maximum positions per day**, alongside limited acceptance of server messages — orders and order modifications such as TP/SL updates and limit-order updates. An EA causing hyperactivity may be flagged and asked to adjust its logic or parameters. Source: `ftmo.com/en/faq/which-instruments-can-i-trade-and-what-strategies-am-i-allowed-to-use/`. A bar-close system on five instruments is orders of magnitude below all three, but Appendix A.7's poll loop should still be designed against these stated figures rather than assumed safe. FundedNext's equivalent limits are unverified.
11. **~~Eligibility from the operator's jurisdiction (UAE)~~ — ANSWERED.** The operator holds live accounts with both firms.

---

## 11. Summary of changes from the reference framework

| Reference framework | This specification |
|---|---|
| Separate backtester and live loop | One engine, swappable adapters (P1) |
| Look-ahead fixed at HMM inference | Causality enforced structurally; nested hyperparameter selection (P2, §8) |
| HMM regime model at the centre | Regime model demoted to an optional feature provider (§2.3) |
| Strategy written into the system | Strategy is a plugin behind a contract (P3, §2.4) |
| Agent-written test suite | Reference strategies, parity harness, hand-written property tests, golden replays (§7) |
| Position tracker only | Full startup reconciliation, order idempotency, persisted risk state (§5) |
| Slippage as a constant | Cost model as a first-class pluggable component (P6, §2.8) |
| Fixed breaker thresholds | Thresholds derived from your own P&L distribution (§6.2) |
| Circuit breakers, lock file | Kept as-is — these were right |
| No concept of externally imposed limits | External account constraints as configurable profiles (§6.5) |
| Random-entry benchmark | Kept and promoted to primary significance test (§7.1) |

---

## 12. Research workflow and the TradingView boundary

TradingView and Pine are retained for research. They are fast, visual, and good at the thing they are good at: forming intuition about whether an idea has any merit before it justifies a Python implementation.

**The boundary is absolute: TradingView never emits a live signal.**

The common retail pattern — Pine strategy fires an alert, webhook hits a bot, bot places a trade — is incompatible with this specification. Alert delivery is best-effort and unlogged. The Pine strategy tester and the live path are different programs, reintroducing exactly the divergence P1 exists to eliminate. And no honest end-to-end backtest is possible when half the system is not in it.

**Research phase (TradingView).** Prototype in Pine. Eyeball behaviour on charts. Discard what obviously fails. No constraints, no rigour required — this stage is for generating candidates cheaply.

**Promotion.** An idea that survives is ported to a `Strategy` plugin in Python. Before it enters the validation pipeline, run a **Pine-to-Python parity check**: export the Pine indicator's signal values over a fixed historical window, run the Python engine over the same bars, and assert the signals agree bar-for-bar.

This step is a feature, not overhead. It surfaces ambiguities hidden behind Pine built-ins — how `ta.atr` seeds its first value, how session functions handle DST transitions, what `barstate` means at a boundary — which are exactly the places where "the same strategy" quietly means two different things in two languages.

**Production (Python only).** Everything from promotion onward runs in the engine. No webhooks in the trade path, ever.

---

## 13. Deferred: LLM advisory layer

Documented now so that the phase 0 logging decision (§2.9) is made correctly. Nothing here is built until the engine is live and stable.

**Never in the signal path.** A non-deterministic component in the decision chain destroys the properties this architecture exists to protect: backtesting becomes meaningless (§7, §8 stop working), runs stop being reproducible (P5), and failures become unfalsifiable — when it loses, there is no way to distinguish a bad strategy from an inconsistent model, so the failure never gets fixed. There is also a domain problem: language models are trained overwhelmingly on market *narrative*, so asking one to judge a setup returns plausible commentary rather than a probability estimate, delivered with confidence uncorrelated to accuracy.

**The judgment layer is the legitimate application.** The decisions identified in §6.4 as irreducibly human are precisely where a model is well suited: reading logs, change history and context, and reporting what it sees.

Three uses, in build order:

1. **Intervention review.** When a loosening change is proposed (§6.4), the model reads the written reason alongside actual state — current drawdown, recent trades, the operator's own override history — and reflects it back. It does not block. Example output: *"This limit has been raised three times, each within two days of a drawdown exceeding 4%, and the thirty days following each change were worse than the thirty preceding."* A mirror at the moment self-perception is weakest.
2. **Post-hoc analysis.** Weekly review of executed trades, rejected signals and risk-gate vetoes, reporting patterns that an equity curve conceals.
3. **Regime commentary.** Advisory only, beside any numeric filter, never replacing it.

**The invariant:** the model observes and advises; it never has authority. It cannot size, enter, exit, or change a parameter. This mirrors the risk gate's constraint from the opposite direction — the gate vetoes but never originates; the model advises but never acts.

**Prerequisite:** §2.9. The value of every use above is bounded by log richness, and unrecorded decision context cannot be reconstructed later.

---

## Appendix A — MT5 broker adapter (primary)

### A.1 Shape

`MT5Broker` and `MT5Feed` implement the `Broker` and `Feed` protocols. Nothing above the adapter layer is aware of MT5. The engine, strategies, sizer, risk gate and backtester are unchanged.

MT5 is used as an execution and data adapter only. **MQL5 Expert Advisors and the MT5 Strategy Tester are not used.** MQL5 lacks the unit testing, property testing and CI infrastructure that §7 depends on, and the Strategy Tester's fill simulation is a black box that cannot be inspected or replaced — whereas `SimBroker` plus a pluggable `CostModel` exists specifically so its assumptions can be examined and argued with.

### A.2 Runtime requirements

The official `MetaTrader5` Python package communicates with a running `terminal64.exe` over Windows named-pipe IPC. This means:

- Windows host, realistically a Windows VPS for 24/5 operation.
- The terminal must be running, logged in, with Algo Trading enabled.
- A macOS wrapper exists that runs the official package inside MT5's bundled Wine environment. Acceptable for development; not for live capital.

**The terminal dependency is the primary operational liability of this venue.** A GUI desktop application must survive auto-updates, modal dialogs and reconnects. Treat terminal health as a monitored condition: if `initialize()` fails or the connection drops, the engine halts and alerts rather than continuing blind.

### A.3 Capabilities used

| Purpose | Call |
|---|---|
| Symbol metadata | `symbol_info()` |
| Historical bars | `copy_rates_range()` |
| Historical bid/ask ticks | `copy_ticks_range(..., COPY_TICKS_ALL)` |
| Current quote | `symbol_info_tick()` |
| Submit order | `order_send()` |
| Open positions | `positions_get()` |
| Deal history | `history_deals_get()` |
| Account state | `account_info()` |

Tick data returns named `time`, `bid`, `ask`, `last` and `flags` columns at millisecond precision, which is better raw material for the cost model than bid/ask candles: the spread distribution in §C.1 can be fitted from observed ticks rather than inferred from aggregates.

**Time zones.** MT5 returns UTC, but Python's `datetime` applies a local shift on construction and printing. Construct all datetimes explicitly in UTC. This is a documented and frequently-hit trap.

### A.4 Reconciliation

MT5 offers no "everything since transaction ID N" primitive. `history_deals_get()` queries by time range, position or ticket. The §5.3 startup routine therefore uses the time-range form:

1. Load persisted state including `last_reconciled_ts`.
2. If a breaker lock file exists, halt.
3. `history_deals_get(from=last_reconciled_ts - overlap, to=now)` with a deliberate overlap window, deduplicating by deal ticket.
4. Replay into local state.
5. `positions_get()` and assert agreement with reconstructed state. **Disagreement is a halt, not a warning.**
6. Warm up features, then enter the main loop.

This is weaker than Appendix B.4 and is the main cost of choosing this venue.

### A.5 Idempotency

MT5 provides `magic` (an EA-level identifier, not per-order unique) and `comment` (which some brokers overwrite). Neither is a reliable caller-supplied order ID.

Use the durable-intent-log fallback from §5.2: write the intent with a unique `intent_id` **before** submitting; on restart, for any intent in submitted-unconfirmed state, query deals within a bounded time window and match on symbol, volume, direction and timestamp before retrying. Set `magic` to a constant identifying this engine, and write `intent_id` into `comment` opportunistically — useful when preserved, never relied upon.

Note the mitigating property from §5.2: because the architecture is target-position based, a duplicate fill self-corrects on the next bar. It costs the spread twice; it does not leave silent double-size.

### A.6 Broker-specific configuration

Symbol names vary by broker (`XAUUSD`, `XAUUSD.m`, `GOLD`). Contract size, volume step, minimum volume, digits, margin requirement and swap rates all come from `symbol_info()` at startup, and every order is validated against them before submission. All of this lives in adapter configuration and never leaks into strategy code.

**Historical depth is a per-broker unknown.** MT5 serves history from the broker's server, and depth varies from months to years. Verify before committing (§10).

### A.7 No push streaming

There is no callback or socket push; the adapter polls. Acceptable for a bar-close system, but `MT5Feed.stream()` is implemented as a poll loop that waits for bar close, whereas an OANDA-style feed blocks on a stream. Both satisfy the `Feed` protocol — a good early demonstration that the abstraction holds.

---

## Appendix B — OANDA v20 broker adapter (second implementation)

Built after phase 8, for two reasons. Practically, it provides venue independence and a cleaner reconciliation path. Architecturally, **implementing a second broker adapter is the strongest available test that the `Broker` protocol is not leaking venue-specific assumptions.** If `OandaBroker` slots in without touching the engine, sizer, risk gate or any strategy, the abstraction is real. Any `if broker == ...` appearing above the adapter layer means it is not — and that is far better discovered from a second implementation than from a production bug.

Once both exist, realised fill quality can be compared across venues on the same strategy.

### B.1 Why this venue

Selected on four criteria that map directly to this specification:

- **Reconciliation.** Transaction history supports ID-range queries, and account state can be polled for changes since a given transaction ID. §5.3 becomes exact rather than heuristic: resume from a transaction ID instead of matching on timestamp and size.
- **Cost modelling.** Separate bid and ask price objects on both REST and streaming. Spread is observed, not inferred from mid.
- **Backtest data.** Candles from 2005, up to 5,000 records per page, granularities from 5-second to monthly. Enough history for meaningful walk-forward on all five instruments.
- **Practice environment** mirrors production endpoints, so phases 0–8 need no live account.

### B.2 Environments

Practice and live are separate hosts with separate tokens. The adapter takes the host as configuration. **A live token must never be resolvable from practice configuration** — separate credential files, and a startup assertion that the environment flag and the token source agree.

### B.3 Endpoints the adapter needs

| Purpose | Endpoint |
|---|---|
| Instrument metadata | `GET /accounts/{id}/instruments` |
| Historical candles | `GET /instruments/{inst}/candles` (`price=BA` for bid+ask) |
| Live pricing stream | `GET /accounts/{id}/pricing/stream` |
| Submit order | `POST /accounts/{id}/orders` |
| Open positions | `GET /accounts/{id}/openPositions` |
| Account state | `GET /accounts/{id}/summary` |
| Reconciliation | `GET /accounts/{id}/transactions/sinceid` |
| Transaction stream | `GET /accounts/{id}/transactions/stream` |

Always request `price=BA` on candles. Mid-price candles discard the spread, which is the dominant cost on these instruments.

### B.4 Reconciliation using transaction IDs

Persist `last_transaction_id` alongside risk state on every mutation. The §5.3 startup routine becomes:

1. Load persisted state including `last_transaction_id`.
2. If a breaker lock file exists, halt.
3. `GET /transactions/sinceid?id={last_transaction_id}` — every account event since shutdown.
4. Replay those transactions into local state. Fills that occurred while the process was dead are now accounted for.
5. `GET /openPositions` and assert agreement with reconstructed state. Disagreement is a **halt**, not a warning.
6. Warm up features, then enter the main loop.

This is the strongest recovery guarantee available at this venue and the main reason to prefer it.

### B.5 Instrument mapping

The engine's internal symbols map to OANDA names in adapter configuration, never in strategy code:

```
NAS100  -> NAS100_USD
US500   -> SPX500_USD
EURUSD  -> EUR_USD
XAUUSD  -> XAU_USD
XAGUSD  -> XAG_USD
```

Units are instrument-specific and not lots. Pull precision and minimum size from `GET /instruments` at startup and validate every order against them before submission — an order rejected for precision is an avoidable failure.

### B.6 Trading hours

The five instruments do not share a calendar. FX and metals trade nearly continuously Sunday evening to Friday evening; index CFDs have daily breaks and different holiday schedules. Encode per-instrument sessions in configuration, and have the feed emit an explicit market-closed signal rather than silently producing no bars — a strategy needs to distinguish "no data" from "market shut".

Weekend gaps are a first-class scenario, not an edge case. Include at least one in the golden replays (§7.4).

**Stored historical data is never gap-filled.** Extraction writes exactly what the venue returns. Weekends, holidays and session breaks appear as absent rows, and no synthetic bar, forward fill or zero-volume placeholder is inserted. A missing bar means the market was shut; inventing one invents a price that was never traded, and a strategy that trades it is trading fiction. Features must therefore tolerate irregular time spacing — a rolling window is a window over *bars*, not over clock time, and any feature whose meaning depends on even spacing must say so and handle the jump explicitly.

---

## Appendix C — Cost model for leveraged instruments

On a CFD or margin FX venue the broker is both counterparty and price source. There is no independent tape to check fills against, and reported volume is not exchange volume. Any strategy requiring true traded volume is unavailable here. Treat the cost model as the most consequential component in the system.

### C.1 Components

**Spread** is the entire commission structure on these instruments and is variable. Model it as a function of instrument, time of day and prevailing volatility — not a constant. Minimum viable version: fit an empirical spread distribution per instrument per hour-of-day from recorded bid/ask candles, and sample the pessimistic tail rather than the median.

Overnight and rollover periods deserve explicit treatment. Spread widening at the daily rollover and around scheduled data releases is predictable, large, and exactly when a naive backtest assumes normal conditions.

**Financing** applies to any position held through the daily financing time. Rates differ per instrument and by direction, and are material for anything held over days. Implement `CostModel.financing()` properly rather than returning zero; a strategy that looks profitable without it may not be.

**Slippage** on market orders. Model as a function of spread and recent volatility, applied adversely.

### C.2 Spread ceiling in the risk gate

A veto rule, not a cost input: reject entries when the current spread exceeds a per-instrument threshold. Without it, a strategy filtering on a minimum reward-to-risk ratio silently accepts trades whose real ratio has collapsed — the setup looks identical, the economics do not. This is the single most likely place for a backtested edge to disappear in production.

### C.3 Margin close-out as a risk input

The broker can liquidate positions when margin utilisation breaches their threshold, independently of your circuit breakers. If your drawdown breaker sits below their close-out level, it never fires — theirs does first. Add `margin_used` and `margin_close_out_level` to `AccountState`, and have the risk gate stand down at a utilisation level well clear of the broker's.

### C.4 Validating the model

From phase 10 onward, log expected fill price alongside realised fill price for every order. Review the distribution weekly. Persistent bias means the cost model is optimistic and every backtest result to date is overstated by roughly that margin — recalibrate before increasing size.

**This loop cannot close on a simulated venue.** Proprietary firm accounts are simulated environments, including after funding. Comparing expected against realised fill there measures the firm's simulator, not the market. The logging must still be built and reviewed — a systematic bias against the simulator is worth knowing — but cost-model validation against real market conditions remains **unresolved** for as long as the only venue is simulated, and must be recorded as such rather than quietly treated as passed. See §6.5.9.

The practical consequence: §6.2 threshold derivation and §6.5.4 margin derivation both rest on a cost model that has not been validated against a real tape. Size accordingly, and treat the first live-capital venue — whenever it arrives — as the point at which this becomes answerable.
