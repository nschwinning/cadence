## ADDED Requirements

### Requirement: Rebalance sizes against the session's current value

An automated rebalance SHALL size its target weights against the session's **current
marked-to-market value** — the allocated capital adjusted by cumulative realised
profit/loss and transaction fees plus the live unrealised profit/loss of open positions,
equivalently the current market value of all open positions plus the session's
unallocated cash — rather than against the session's original frozen allocated capital.
The normalised target weights (which sum to approximately one, after any guardrail
enforcement) SHALL therefore be applied to the session's current equity, so that each
target position value is a fraction of what the session is worth now. Realised and
unrealised gains SHALL thereby be redeployed into the target allocation on the next
rebalance, and after losses the targets SHALL be sized to the session's reduced equity
rather than its original capital.

The target-weight delta model SHALL be otherwise unchanged: the system SHALL still trade
only the delta between each target position and the current position (a buy when the
target exceeds the current holding, a sell or full exit when it falls short), SHALL still
apply fractional sizing for crypto and whole-share sizing for equities, and SHALL still
enforce any configured risk guardrails on the weight vector before sizing.

The **initial build** SHALL continue to size positions against the session's allocated
capital. Because at build time the session holds no positions and has no profit/loss, its
current value equals its allocated capital, so build sizing is unaffected; only the
rebalance seam uses the current-value base.

#### Scenario: Gains are redeployed on rebalance

- **WHEN** a session whose current value has grown above its allocated capital is
  rebalanced
- **THEN** the system SHALL size the target positions against the current (grown) value,
  so the gains are deployed into the target allocation rather than left idle as cash

#### Scenario: Targets sized down after losses

- **WHEN** a session whose current value has fallen below its allocated capital is
  rebalanced
- **THEN** the system SHALL size the target positions against the current (reduced)
  value rather than the original allocated capital

#### Scenario: Build still sizes against allocated capital

- **WHEN** a portfolio is first built (no positions, no profit/loss yet)
- **THEN** the system SHALL size the initial positions against the allocated capital,
  which equals the session's current value at that moment

#### Scenario: Delta model and guardrails unchanged

- **WHEN** a rebalance sizes positions against the current value
- **THEN** the system SHALL still trade only the delta between target and current
  positions and SHALL still enforce any configured risk guardrails on the target weights
  before sizing
