## ADDED Requirements

### Requirement: Build completion communicates deferred allocation

Because a build no longer places opening trades, the AI portfolio build form SHALL
NOT imply that trades were placed when a build completes. On a successful build the
UI SHALL communicate that the portfolio was created and enrolled in daily
rebalancing and that it will be allocated on its next daily rebalance, so the user
understands the new portfolio starts empty (holding cash) rather than already
invested. The UI SHALL NOT present an "added N assets" or "opening trades placed"
style summary for the build result.

#### Scenario: Successful build communicates deferred allocation

- **WHEN** a user submits the build form and the build completes successfully
- **THEN** the UI SHALL communicate that the portfolio was created and enrolled and will be allocated on its next daily rebalance, and SHALL NOT state or imply that opening trades were placed

#### Scenario: No opening-trades summary on build completion

- **WHEN** a build completes successfully
- **THEN** the UI SHALL NOT render an "added N assets" or "opening trades placed" style summary for the build, because the build placed no trades
