## Why

When a bot's drawdown kill-switch liquidates it, Cadence sends a push notification. That
behaviour was built by `add-strategy-bot-notifications`, which was archived without
syncing its specs (its other requirement blocks were outdated copies). The daily
summary push has since been specified, but the kill-switch push is still described
nowhere in the main `strategy-bots` spec. This change closes that gap so the spec matches
the shipped code.

## What Changes

- Add a **"Bot kill-switch notification"** requirement to `strategy-bots` describing the
  existing behaviour:
  - when the drawdown kill-switch stops a bot, one best-effort push is sent, titled with
    the bot's label;
  - it names the positions liquidated (or that there were none), the realised P&L booked
    on the liquidation, and that the bot is now stopped;
  - it is sent for **every** bot, including bots deployed by an orchestrator (unlike the
    daily summary, it is not rolled up);
  - it is a silent no-op without a notification channel, and a failure never stops the
    tick from stopping the bot.
- **No code change**: the behaviour and its tests already exist.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `strategy-bots`: adds the "Bot kill-switch notification" requirement.

## Impact

Spec only. The implementation (`strategy_bots/notifications._kill_switch_message`, the
kill-switch block of `service._tick_session`) and its tests are unchanged.
