# Strategy-Bot Roadmap

Build roadmap for Cadence's strategy-bot subsystem, derived from a feasibility
review of the ~47 numbered course algos in `/Users/nilsschwinning/workspaces/quant/course`
(there is no Algo 44).

**Porting contract.** A Cadence strategy is a *pure signal* over one symbol's
OHLCV bars → `ENTER_LONG` / `EXIT` / `HOLD`. It is **long-only** (any short leg
in the course script is dropped). The engine already owns TP/SL/drawdown
guardrails, ATR/all-in sizing, and the multi-asset shared-capital pool. No order
book, no news feed, no multi-symbol/pairs inside one `evaluate`. Adding a bot is
additive: implement the `Strategy` + register one entry in `registry.py` with a
new `StrategyKey`.

**Key insight — consolidation.** Once periods, thresholds, MA-type, and optional
filters become *config*, many course folders collapse into the same bot. The ~35
feasible/caveat folders reduce to **16 distinct bots** (2 shipped); a 17th
(Trend-Confirmation, #13) is derived from the AI-portfolio technical gate rather
than a course algo. Each item below is one shippable bot; "Absorbs" lists the
course folders it subsumes so we never build the same signal twice.

---

## ✅ Shipped

- **MA Crossover** (`ma_crossover`) — Algo 6.
- **RSI Mean Reversion** (`rsi_mean_reversion`) — Algo 16 (Tier 1 #1). Absorbs 16, 22, 24. Close-only, long-only (course RSI>70 short leg dropped); entry RSI<`oversold` (default 30), exit RSI>`exit_level` (default 50), + engine TP/SL/drawdown.

## Tier 1 — Core signals, each unlocks a whole family (highest leverage)

| # | Bot | Key params | Absorbs | Notes |
|---|-----|-----------|---------|-------|
| 1 | ✅ **RSI Mean Reversion** | period, oversold, exit-level | 16, 22, 24 | **Shipped** (`rsi_mean_reversion`, Algo 16). Close-only, long-only (overbought/short leg dropped). Entry RSI<30, exit RSI>50 (+ engine TP/SL/drawdown). 22/24 "news" is illusory; 24's ATR is only sizing. |
| 2 | **Donchian / Range Breakout** | lookback | 7, 25, 8 | **Next up.** Breakout of N-bar high. |
| 3 | **Rolling-Average Reversion** | average_type (SMA/VWAP/typical), distance (band/z-score), exit filter (none/ADX/volume) | 5, 14, 39, 35, 15, 4 | Biggest consolidation — 6 folders in one bot. "VWAP" in the course is a rolling mean, not volume-weighted. |
| 4 | **ATR-Band Trend** | midline (SuperTrend/Keltner), atr_mult | 9, 21 | "midline ± k·ATR" trend. |

*Tier 1 = 4 bots covering ~15 course folders (1 shipped, 3 remaining; Donchian next).*

## Tier 2 — Distinct standalone signals (breadth)

| # | Bot | Absorbs | Notes |
|---|-----|---------|-------|
| 5 | **MACD Momentum** | 10 | EMA-difference cross. |
| 6 | **ADX Trend Strength** | 12 | DI cross gated by ADX. |
| 7 | **Heikin-Ashi Trend** (optional volume filter) | 11, 37 | 37 = 11 + volume-confirmation toggle. |
| 8 | **HMA Trend** (cross + slope + reversal exit) | 19, 26 | 26 is a plain HMA crossover, a subset of 19. |
| 9 | **MA Ribbon** | 18 | 3-MA alignment (fast>mid>slow). |
| 10 | **VAMA** | 30 | Volatility-adaptive EMA cross. |
| 11 | **Price Velocity Reversal** | 48 | Velocity/acceleration reversal (file mislabeled `algo 49.py`). |
| 12 | **Gradient Convergence** | 3 | Short-window mean reversion. |
| 13 | **Trend-Confirmation (multi-indicator AND)** | — (new; derived from the AI-portfolio technical gate) | Intraday, re-tuned. See note below. |

## Tier 3 — Volume-dependent (data-quality caveat)

| # | Bot | Absorbs | Caveat |
|---|-----|---------|--------|
| 14 | **Volume Breakout** (indicator: spike/VROC/Chaikin) | 34, 46, 45 | Needs reliable bar volume; 45 (Chaikin) fakes H/L with random in the course script — verify real bars fix it. |

## Tier 4 — Composites (build only after their primitives exist)

| # | Bot | Absorbs | Depends on |
|---|-----|---------|-----------|
| 15 | **Volatility Regime Switcher** | 20 | a trend bot + a reversion bot (Tier 1) |
| 16 | **Multi-Signal Consensus** | 43 | several Tier 1/2 signals to vote |
| 17 | **Bayesian Trend Predictor** | 33 | stateful posterior — its own thing |

## ⛔ Excluded

- **Sizing overlays, not strategies:** 13 GARCH, 23 "News Flow" ATR — pure
  position-sizing with no entry/exit; the engine already owns sizing.
- **Infra the strategy layer lacks:** 1, 2 (time-based accumulation / martingale,
  no signal) · 27/28/29/31 (TWAP/POV execution + surveillance) · 32/40/41/42
  (two-symbol pairs/spread) · 38 ARIMA (per-tick model fit) · 47 VPI (order-flow
  buy/sell split).

---

## Note — Trend-Confirmation bot (#13) and the AI-portfolio "filter"

This bot is **not** a port of a course algo; it comes from asking whether
Cadence's AI-portfolio **technical gate** could become a bot.

- The AI portfolio screens candidates with four opt-in signals. Only the
  **technical trend gate** (`technical_indicators/compute.py` → `compute_snapshot`
  → `_derive_gate`: `close>SMA200 ∧ SMA50>SMA200 ∧ SMA200-slope ∧ MACD_hist ∧
  RSI14 ∧ ROC120 ∧ OBV-rising`) is a pure single-symbol OHLCV computation. The
  other three are **not convertible**: fundamentals = SEC EDGAR statements,
  news-sentiment = news-text NLP, price-ML = TA features but scored by a pooled
  trained model (shared state). None is a per-symbol OHLCV signal.
- **Resolution is the catch.** The AI gate runs on **daily** bars; strategy bots
  tick on **5-min** bars (`settings.BOT_SIGNAL_BAR_TIMEFRAME = "5Min"`, one global
  knob). On 5-min, SMA200 ≈ 2.5 trading days, not a 10-month regime — so the same
  code is a different indicator. **Code reuse ≠ behavior reuse.** A faithful daily
  port would need per-bot timeframe support AND would largely duplicate the AI
  portfolio's daily job — rejected.
- **Decision (option B):** build a NEW *intraday* bot that borrows only the
  indicator *toolkit* (factor `compute_snapshot`'s pure math), **re-tuned** for
  5-min, with no SMA200/daily semantics. Its distinct identity is a strict
  **conjunction (AND)** of a small fixed trend set — default legs **SMA-fast >
  SMA-slow (regime) ∧ MACD_hist > 0 (momentum) ∧ RSI > threshold (not exhausted)**,
  with OBV/ROC as optional toggles. `ENTER_LONG` when all legs agree, `EXIT` when
  the conjunction breaks (+ engine TP/SL/drawdown). This is deliberately AND, which
  keeps it distinct from #16 Multi-Signal Consensus (a vote) and from single-
  indicator bots (#0 MA Crossover, #5 MACD).
- Independent of this bot, two reusable wins were identified: (a) **per-bot
  timeframe** as a general engine capability (several long-window bots would want
  `1Day`), and (b) factoring the indicator math so bots and the AI gate can't
  drift. Both are optional, not prerequisites for #13.

## Notable findings

- The "News Flow Price Reactor" trio (22, 23, 24) and "News Flow + HMA" (26) are
  **misnomers at the code level**: their `News.py` only perturbs the *simulated*
  price feed; the trading loops read price only. They need no news feed.
- Range 13–24 contains **zero** algos that truly require news, order book, pairs,
  or external models.

**Scorecard:** 17 distinct bots (2 shipped) — 16 replace all ~35 feasible course
folders, plus the Trend-Confirmation bot (#13) derived from the AI-portfolio
technical gate. Tier 1's 4 bots alone cover ~15 course folders.
