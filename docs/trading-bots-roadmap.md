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
feasible/caveat folders reduce to **16 distinct bots** (13 shipped); a 17th
(Trend-Confirmation, #13) is derived from the AI-portfolio technical gate rather
than a course algo. Each item below is one shippable bot; "Absorbs" lists the
course folders it subsumes so we never build the same signal twice.

---

## ✅ Shipped

- **MA Crossover** (`ma_crossover`) — Algo 6.
- **RSI Mean Reversion** (`rsi_mean_reversion`) — Algo 16 (Tier 1 #1). Absorbs 16, 22, 24. Close-only, long-only (course RSI>70 short leg dropped); entry RSI<`oversold` (default 30), exit RSI>`exit_level` (default 50), + engine TP/SL/drawdown.
- **Donchian / Range Breakout** (`donchian_breakout`) — Tier 1 #2. Versions Turtle (Algo 25) and Locked (Algos 7 + 8). Presets: Turtle Breakout (Algo 25, default), Smart Range Breakout (Algo 8).
- **Rolling-Average Reversion** (`rolling_average_reversion`) — Tier 1 #3. Presets for Algos 5 (default), 4, 14, 39, 3 (Gradient Convergence: SMA 5, entry/exit 0 — the course "gradient" read long-only) and 15 (VWAP + ADX, using the optional ADX danger exit; ADX lookback 20 bars where the course measures every candle since start). Algo 35 is trend-following (separate bot).
- **ATR-Band Trend** (`atr_band_trend`) — Tier 1 #4. Versions SuperTrend (Algo 9) and Keltner (Algo 21), close-based course ATR. Presets: SuperTrend (Algo 9, default), Keltner Breakout (Algo 21; course has no drawdown stop, 5% catalog convention).

- **ADX Trend Strength** (`adx_trend`) — Tier 2 #6, Algo 12. Course plain-sum ADX (not Wilder); enter ADX > 20 with +DI > −DI, exit ADX < 20. Preset: ADX Trend Strength (Algo 12, default). Its directional-movement helpers also power the reversion bot's ADX danger exit.
- **MACD Momentum** (`macd_momentum`) — Tier 2 #5, Algo 10. EMA 12/26, signal 9, seeded from simple means as in the course; enter on a bullish MACD cross while MACD > 0, exits via the engine bracket (course has no signal exit). Preset: MACD Momentum (Algo 10, default).
- **Heikin-Ashi Trend** (`heikin_ashi_trend`) — Tier 2 #7, Algos 11 and 37. Green Heikin-Ashi candle in, red out; optional volume filter (bar volume above its N-bar mean to enter, fading volume exits — the course compares tick volumes). Presets: Heikin-Ashi Trend (Algo 11, default), Heikin-Ashi + Volume (Algo 37, no TP/SL as in the course).
- **HMA Trend** (`hma_trend`) — Tier 2 #8, Algos 19 and 26 (26's trading code is identical to 19; its news module only perturbs the simulated feed). Proper Hull MA (WMA over √n of 2·WMA(n/2) − WMA(n)); the course `hull_ma` skips that final smoothing (bug) — user chose the proper HMA. Enter on a rising fast HMA above the slow one, exit on a falling cross below. Preset: HMA Trend (Algos 19 / 26, default).
- **MA Ribbon** (`ma_ribbon`) — Tier 2 #9, Algo 18. SMA 5/10/20; enter when fast > mid > slow, exits via the engine bracket (course has no ribbon exit). Preset: MA Ribbon (Algo 18, default).
- **VAMA** (`vama`) — Tier 2 #10, Algo 30. The course's "adaptive" α divides the current volatility by itself, so it is always α_max (0.20) — a fixed EMA. Shipped with both: fixed smoothing (course, used by the preset) and a real adaptive mode (α = α_max × current ÷ average volatility, clamped). Close above the VAMA in, at/below out; no TP/SL. Preset: VAMA (Algo 30, default, fixed smoothing).
- **Price Velocity Reversal** (`price_velocity_reversal`) — Tier 2 #11, Algo 48 (file `algo 49.py`). Velocity = latest bar's % change; enter when velocity < −threshold and acceleration > 0 (a slowing sell-off), exit when velocity turns positive. The course's absolute ₹2 threshold (on a ₹1,000 simulated price) is expressed as 0.2% so it works at any share price (user decision). Preset: Price Velocity Reversal (Algo 48, default).

Every shipped strategy also has its course presets in the preset catalog (`strategy_bots/presets.py`), which is all the AI orchestrator may deploy.

## Tier 1 — Core signals, each unlocks a whole family (highest leverage)

| # | Bot | Key params | Absorbs | Notes |
|---|-----|-----------|---------|-------|
| 1 | ✅ **RSI Mean Reversion** | period, oversold, exit-level | 16, 22, 24 | **Shipped** (`rsi_mean_reversion`, Algo 16). Close-only, long-only (overbought/short leg dropped). Entry RSI<30, exit RSI>50 (+ engine TP/SL/drawdown). 22/24 "news" is illusory; 24's ATR is only sizing. |
| 2 | ✅ **Donchian / Range Breakout** | lookback | 7, 25, 8 | **Shipped** (`donchian_breakout`). Breakout of N-bar high; Turtle and Locked versions. |
| 3 | ✅ **Rolling-Average Reversion** | average_type (SMA/VWAP/typical), distance (band/z-score), exit filter (none/ADX/volume) | 5, 14, 39, 35, 15, 4 | **Shipped** (`rolling_average_reversion`) with presets 5/4/14/39/15 (15 via the ADX danger exit); 35 is trend-following. |
| 4 | ✅ **ATR-Band Trend** | midline (SuperTrend/Keltner), atr_mult | 9, 21 | **Shipped** (`atr_band_trend`). "midline ± k·ATR" trend; SuperTrend and Keltner versions. |

*Tier 1 = 4 bots covering ~15 course folders — **complete**.*

## Tier 2 — Distinct standalone signals (breadth)

| # | Bot | Absorbs | Notes |
|---|-----|---------|-------|
| 5 | ✅ **MACD Momentum** | 10 | **Shipped** (`macd_momentum`). EMA-difference cross above zero. |
| 6 | ✅ **ADX Trend Strength** | 12 | **Shipped** (`adx_trend`). DI lead gated by ADX; also powers the Algo 15 reversion preset. |
| 7 | ✅ **Heikin-Ashi Trend** (optional volume filter) | 11, 37 | **Shipped** (`heikin_ashi_trend`). 37 = 11 + volume-confirmation toggle. |
| 8 | ✅ **HMA Trend** (cross + slope + reversal exit) | 19, 26 | **Shipped** (`hma_trend`). 26 trades identically to 19; proper HMA (course skips the √n smoothing). |
| 9 | ✅ **MA Ribbon** | 18 | **Shipped** (`ma_ribbon`). 3-MA alignment (fast>mid>slow). |
| 10 | ✅ **VAMA** | 30 | **Shipped** (`vama`). Fixed (course) and adaptive smoothing. |
| 11 | ✅ **Price Velocity Reversal** | 48 | **Shipped** (`price_velocity_reversal`). Velocity/acceleration reversal, percent threshold (file mislabeled `algo 49.py`). |
| 12 | ✅ **Gradient Convergence** | 3 | **Shipped as a Rolling-Average Reversion preset** (`rolling_reversion_gradient_algo3`): long while close < SMA(5), flat once back at/above — the same signal, so no separate strategy. |
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

**Scorecard:** 17 distinct bots (13 shipped) — 16 replace all ~35 feasible course
folders, plus the Trend-Confirmation bot (#13) derived from the AI-portfolio
technical gate. Tier 1's 4 bots alone cover ~15 course folders.
