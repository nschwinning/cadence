## 1. Verify the spec against the shipped code

- [x] 1.1 Confirm each scenario is covered by an existing test: `test_kill_switch_sends_one_push` (one push naming the positions and P&L), `test_kill_switch_message_handles_no_open_positions` (no positions), `test_no_kill_switch_sends_no_push` (no trip, no push), `test_kill_switch_raising_notifier_still_stops` (failure still stops). Verify: those tests pass against the 5435 test DB (tear the container down afterwards).
- [x] 1.2 `openspec validate document-bot-kill-switch-notification --strict`. Verify: passes.
