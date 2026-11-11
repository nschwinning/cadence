## ADDED Requirements

### Requirement: AI build form hints when many signals are enabled

The AI build form SHALL show a **soft, non-blocking hint** when three or more of its opt-in
signal toggles (for example the technical-indicator trend, company-fundamentals,
news-sentiment, and price-ML toggles — whichever exist) are turned on at once, advising that
a focused set of complementary signals usually serves a strategy better than enabling every
signal (for example "Using many signals can dilute focus — 2–3 complementary signals usually
work best").

The hint SHALL be **advisory only**: it SHALL NOT disable the build action, SHALL NOT cap,
uncheck, or disable any toggle, and SHALL NOT change the request submitted to the backend.
When fewer than three opt-in signals are enabled, the hint SHALL NOT be shown. Toggling a
signal on or off SHALL update the hint's visibility live.

#### Scenario: Hint appears when three or more signals are enabled

- **WHEN** the operator has three or more of the AI build form's opt-in signal toggles turned
  on
- **THEN** the form SHALL display a soft advisory hint about focusing on a smaller set of
  complementary signals
- **AND** the build action SHALL remain enabled and the toggles SHALL remain exactly as the
  operator set them

#### Scenario: Hint is hidden below the threshold

- **WHEN** the operator has fewer than three opt-in signal toggles turned on
- **THEN** the form SHALL not display the hint

#### Scenario: Hint does not alter the submitted request

- **WHEN** the operator submits the build with three or more opt-in signals enabled despite
  the hint
- **THEN** the submitted request SHALL carry exactly the signals the operator enabled,
  unaffected by the hint
