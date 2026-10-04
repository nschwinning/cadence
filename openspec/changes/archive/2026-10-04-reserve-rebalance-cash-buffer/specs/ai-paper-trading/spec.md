## ADDED Requirements

### Requirement: Reserve a cash buffer when sizing orders

The AI executor SHALL reserve a **cash buffer** before sizing build or rebalance
orders, so that executed buys cannot claim the full value available and the
session's **unallocated cash is not driven negative** by fully deploying value
plus per-trade transaction fees and market-order fill slippage.

The reserved buffer SHALL be the **greater of**:

1. a **configurable percentage** of the sizing base (the allocated capital at
   build, the session's current marked-to-market value at rebalance), and
2. the **estimated total transaction fees** for the run — the number of
   candidate orders for the run multiplied by the per-trade transaction cost.

The sizing base SHALL be reduced by the reserved buffer **before** any target
weight is applied, so every per-ticker allocation is sized against the net
(post-buffer) base. The reserve SHALL be applied consistently at both the
initial build and every rebalance, and SHALL apply to a crypto-only rebalance's
crypto-scoped base as well. When the per-trade transaction cost is zero and the
buffer percentage is zero, the reserve SHALL be zero and sizing SHALL be
unchanged.

The buffer SHALL only shrink the base the executor sizes against; it SHALL NOT
change the target-weight delta model, guardrail enforcement, crypto-only
scoping, the `market_open` equity-skip, or the sells-before-buys phasing.

#### Scenario: Fully invested target leaves cash non-negative

- **WHEN** a session is rebalanced toward target weights that sum to
  approximately one
- **THEN** the executor SHALL size the target positions against the current
  value reduced by the reserved cash buffer, so that after the fees for the
  executed trades the session's unallocated cash is not negative

#### Scenario: Buffer is the greater of the percentage and the fee estimate

- **WHEN** the estimated total fees for a run exceed the configured percentage of
  the sizing base
- **THEN** the executor SHALL reserve the fee estimate rather than the smaller
  percentage, and conversely SHALL reserve the percentage when it is the larger
  of the two

#### Scenario: Build reserves the buffer too

- **WHEN** a portfolio is first built
- **THEN** the executor SHALL size the initial positions against the allocated
  capital reduced by the reserved cash buffer, leaving a cash reserve rather than
  deploying the full allocated capital

#### Scenario: Zero cost and zero percentage disable the reserve

- **WHEN** the per-trade transaction cost and the buffer percentage are both zero
- **THEN** the reserved buffer SHALL be zero and sizing SHALL match the behavior
  with no buffer

## MODIFIED Requirements

### Requirement: Rebalance sizes against the session's current value

An automated rebalance SHALL size its target weights against the session's **current
marked-to-market value** — the allocated capital adjusted by cumulative realised
profit/loss and transaction fees plus the live unrealised profit/loss of open positions,
equivalently the current market value of all open positions plus the session's
unallocated cash — rather than against the session's original frozen allocated capital,
**reduced by the reserved cash buffer** (see "Reserve a cash buffer when sizing orders").
The normalised target weights (which sum to approximately one, after any guardrail
enforcement) SHALL therefore be applied to the session's current equity net of the
reserved buffer, so that each target position value is a fraction of what the session is
worth now less the reserve. Realised and unrealised gains SHALL thereby be redeployed into
the target allocation on the next rebalance, and after losses the targets SHALL be sized to
the session's reduced equity rather than its original capital.

The target-weight delta model SHALL be otherwise unchanged: the system SHALL still trade
only the delta between each target position and the current position (a buy when the
target exceeds the current holding, a sell or full exit when it falls short), SHALL still
apply fractional sizing for crypto and whole-share sizing for equities, and SHALL still
enforce any configured risk guardrails on the weight vector before sizing.

The **initial build** SHALL continue to size positions against the session's allocated
capital (likewise reduced by the reserved cash buffer). Because at build time the session
holds no positions and has no profit/loss, its current value equals its allocated capital,
so build sizing is unaffected apart from the reserve; only the rebalance seam uses the
current-value base.

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

#### Scenario: Sizing base is net of the reserved buffer

- **WHEN** a rebalance sizes positions against the current value
- **THEN** the system SHALL first reduce that value by the reserved cash buffer and apply
  the target weights to the net base, so the session retains a cash reserve for fees and
  slippage

#### Scenario: Delta model and guardrails unchanged

- **WHEN** a rebalance sizes positions against the current value
- **THEN** the system SHALL still trade only the delta between target and current
  positions and SHALL still enforce any configured risk guardrails on the target weights
  before sizing
