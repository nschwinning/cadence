## Context

The AI portfolio's gate (`technical_indicators/compute.py` → `compute_snapshot` → `_derive_gate`)
computes, with pandas on daily adjusted closes: rolling SMAs, MACD via `ewm(span, adjust=False,
min_periods)`, a Wilder-smoothed RSI (`_wilder` / `_rsi`), ROC, and OBV change. Strategy bots tick on
5-minute bars, so the gate's daily windows (SMA200, ROC120) don't transfer; the roadmap chose a
re-tuned intraday AND of a smaller set (option B). The user approved the defaults and asked for
shared indicator maths.

## Goals / Non-Goals

**Goals:** the Trend Confirmation strategy with approved defaults and churn-resistant exits; one
implementation of the indicator series used by both the gate and the bot; preset; form; guide.

**Non-Goals:** changing the AI gate's behaviour or windows; per-bot timeframes; a vote/consensus mode.

## Decisions

1. **`technical_indicators/series.py`** — pure functions on `pd.Series`: `sma(p, n)`,
   `macd_histogram(p, fast, slow, signal)` (returns line, signal, hist with the gate's `ewm`
   settings), `wilder(series, n)` and `rsi(p, n)` (moved verbatim), `roc(p, n)`,
   `obv(close, volume)` and `obv_change(obv, n)`. `compute_snapshot` calls them with its constants.
   A parity test computes snapshots on fixed fixtures before/after (golden values) to prove no
   drift; existing technical-indicator tests must pass unchanged.
2. **`TrendConfirmationParams`** (`extra='forbid'`, unique param names so presets and the form don't
   collide with other strategies): `sma_fast` 20 < `sma_slow` 50; `macd_fast` 12 < `macd_slow` 26,
   `macd_signal` 9; `rsi_period` 14; `rsi_exit` 45 ≤ `rsi_entry` 50 < `rsi_max` 70 ≤ 100;
   `use_roc` False, `roc_period` 12; `use_obv` False, `obv_window` 20.
3. **Required history** = `max(sma_slow, 3 × macd_slow + macd_signal, 3 × rsi_period,
   roc_period + 1, obv_window + 1)` — 87 for the defaults, so the EMA- and Wilder-based series have
   converged over a fixed span (they start at the first bar provided).
4. **Signals** on the latest values (bars' closes; OBV uses volumes): flat → ENTER_LONG iff every
   active leg agrees (strict); holding → EXIT iff any active leg breaks (strict, RSI vs `rsi_exit`,
   never on RSI > cap); otherwise HOLD. Any undefined active value → HOLD.
5. **Preset** `trend_confirmation_cadence` (default; `course_ref` "Cadence — no course algorithm"):
   defaults above, TP 0.01, SL 0.01, DD 0.05.
6. **Frontend**: grouped fields — Trend (SMA fast/slow), Momentum (MACD fast/slow/signal),
   Strength (RSI period, entry, cap, exit), optional ROC (toggle + period) and OBV (toggle + window);
   validation mirrors the params. `trendConfirmationChart.ts` plots a synthetic close with the two
   SMAs and shades/marks where all legs agree (entry) and where one breaks (exit), with a small TS
   mirror of the leg logic.

## Risks / Trade-offs

- Three required legs make entries rare on choppy days — intended.
- MACD here uses the gate's pandas `ewm` (starts from the first bar) rather than the MACD bot's
  course seeding; both converge — the bot shares the gate's maths by request.

## Migration Plan

None (additive; the AI gate's behaviour is unchanged).

## Open Questions

None.
