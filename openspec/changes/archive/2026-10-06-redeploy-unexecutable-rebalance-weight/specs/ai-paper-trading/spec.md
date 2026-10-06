## ADDED Requirements

### Requirement: Redeploy unexecutable target weight across executable targets

During an automated rebalance, when one or more of the AI's target positions cannot be
executed, the system SHALL redistribute the unexecuted targets' weight across the targets
that **can** be executed, rather than leaving that weight uninvested as cash. A target is
**unexecutable** for the run when the broker returns no usable price for it, or when its
share of the sizing base cannot fund the minimum tradable amount for its asset class (at
least one whole share for an equity, or the minimum crypto notional for a crypto asset).

The redeployment SHALL remain bounded by the reserved cash buffer (see "Reserve a cash
buffer when sizing orders"): the system SHALL NOT deploy capital below the reserved buffer,
so the session still retains its cash reserve for fees and slippage. When a session has
risk guardrails enabled, the redeployed weight vector SHALL still satisfy the configured
guardrail caps (per-asset, per-asset-class, and maximum invested fraction); weight that
cannot be placed without breaching a guardrail SHALL remain as cash, consistent with the
guardrail requirements. The redeployment SHALL preserve the existing delta model: the
system still trades only the delta between each resulting target position and the current
position, still uses whole-share sizing for equities and fractional sizing for crypto, and
still submits sells before buys.

When every target is unexecutable, or no executable target can absorb additional weight
without breaching the cash buffer or a guardrail, the system SHALL leave the residual as
cash rather than failing the run.

#### Scenario: An unpriceable target's weight is redeployed

- **WHEN** a rebalance has several target positions and one target cannot be priced by the
  broker
- **THEN** the system SHALL redistribute that target's weight across the targets that can
  be priced and executed, so the session's invested fraction reflects the executable
  targets rather than stranding the unpriceable target's weight as cash

#### Scenario: A target too small for one share is redeployed

- **WHEN** a target position's share of the sizing base cannot fund even one whole share of
  that equity (or the minimum crypto notional for a crypto target)
- **THEN** the system SHALL redistribute that target's weight across the targets that can be
  funded, rather than silently leaving that slice of capital uninvested

#### Scenario: Redeployment respects the reserved cash buffer

- **WHEN** unexecutable target weight is redeployed across the executable targets
- **THEN** the system SHALL NOT deploy capital below the reserved cash buffer, so the
  session still retains its cash reserve for fees and slippage

#### Scenario: Redeployment respects risk guardrails when enabled

- **WHEN** a session with risk guardrails enabled has unexecutable target weight to redeploy
- **THEN** the resulting target weights SHALL still satisfy the per-asset, per-asset-class,
  and maximum-invested guardrail caps, and any weight that cannot be placed without
  breaching a cap SHALL remain as cash

#### Scenario: All targets unexecutable leaves cash without failing

- **WHEN** no target in a rebalance can be executed (for example, none can be priced)
- **THEN** the system SHALL leave the capital as cash and complete the run without error,
  recording each target as not executed

### Requirement: Record a rebalance target that cannot be executed

When a rebalance cannot execute a target position, the system SHALL record that target as a
non-executed outcome with a clear reason (for example, that no price was available, or that
the target was too small to fund the minimum tradable amount), so that a `partial`-status
run is explainable from the recorded run statistics. The system SHALL NOT drop an
unexecutable target silently.

#### Scenario: A target too small for one share is recorded

- **WHEN** a target position cannot fund even one whole share (or the minimum crypto
  notional) and is therefore not traded
- **THEN** the system SHALL record that target as not executed with a reason indicating it
  was too small to fund the minimum tradable amount, rather than omitting it from the run's
  recorded outcomes

#### Scenario: An unpriceable target is recorded

- **WHEN** a target position cannot be priced by the broker
- **THEN** the system SHALL record that target as not executed with a reason indicating no
  price was available

### Requirement: Exclude known-unexecutable tickers from rebalance candidates

When assembling the candidate universe offered to the agent for a rebalance, the system
SHALL exclude tickers that are known to be unexecutable on the configured brokerage — for
example a listing the broker cannot price or trade — so that such a ticker is not
repeatedly re-selected as a target on every run. This exclusion applies to rebalance
candidate assembly and SHALL NOT change which already-held positions a rebalance may sell
or exit.

#### Scenario: A known-unexecutable ticker is not offered as a candidate

- **WHEN** a rebalance assembles the candidate universe for the agent and a ticker is known
  to be unexecutable on the configured brokerage
- **THEN** the system SHALL omit that ticker from the candidates offered to the agent, so it
  is not re-targeted every run

#### Scenario: Held positions are still actionable

- **WHEN** a ticker excluded from the rebalance candidates is already held by the session
- **THEN** the exclusion SHALL NOT prevent the rebalance from selling or exiting that held
  position
