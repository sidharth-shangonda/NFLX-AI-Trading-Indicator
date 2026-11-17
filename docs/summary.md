# Executive Summary — NFLX AI Trading Indicator

**Project Title:** NFLX AI Trading Indicator — 5-Minute Intraday Directional Indicator  
**Author / Lead:** Sidharth (IIT Patna)  
**Target Asset:** NASDAQ: NFLX  
**Platform Stack:** Python 3.13, Scikit-Learn, Pandas, FastAPI, SQLite3, Lightweight Charts v5.2, Modern Web UI  
**Repository Status:** Verified & Complete (`make test` 63/63 passing, `make lint` 0 errors)

---

## 1. Project Overview & Core Philosophy

The NFLX AI Trading Indicator is a high-reliability, paper-only machine learning system developed to forecast the direction of the next five-minute candlestick for NASDAQ: NFLX during regular NYSE trading hours.

### Non-Negotiable Core Principles
1. **Paper Only:** Strict data-science indicator with zero brokerage execution or order routing code.
2. **Genuinely Trained ML Model:** Forecasts are driven entirely by a trained `HistGradientBoostingClassifier`, never heuristic hand-written rules.
3. **Strict Non-Repainting Guarantee:** Past predictions are never modified, recalculated, or deleted. Enforced at the database engine level via SQLite `BEFORE UPDATE` and `BEFORE DELETE` triggers.
4. **Zero Future Lookahead (Causality):** Feature generation, scaling, and threshold selection operate strictly on historical prefix data with zero lookahead leakage.
5. **Empirical Truth & Integrity:** Complete transparency across test metrics, baseline benchmarks, and live market streaming.

---

## 2. Quantitative Performance Highlights

The project underwent rigorous two-tier validation: out-of-sample holdout testing and full-day live operational market testing.

| Evaluation Stage | Scope / Candles | Confident Signals | Directional Accuracy | Baseline Benchmark Comparison | Key Financial / Calibration Metric |
|---|---|---:|---:|---|---|
| **Holdout Test Set** (Out-of-sample) | 2,175 candles (30 trading sessions) | 690 (31.72% coverage) | **52.17%** | Beats Always UP (48.14%) & Always DOWN (51.86%) | Gross P&L: **+1,029.98 bp (+10.3%)**; Log loss: 0.69257 |
| **Live Market Trading** (2026-11-16 Full NYSE Session) | 78 candles (100% of trading day) | 70 non-zero calls (94.9% coverage) | **57.14%** | Beats Always UP (43.24%), Always DOWN (56.76%), Random Walk (50.00%) | On-time accuracy: **58.97%**; 0 REST discrepancies |

---

## 3. Data Pipeline & Feature Engineering

- **Data Ingestion:** 147,124 raw 1-minute IEX bars spanning 26 months (Oct 2024 to Nov 2026), split-adjusted and stored in a deterministic local snapshot (`SHA-256: b9895df8...`).
- **5-Minute Candlestick Builder:** NYSE calendar-aligned 5-minute interval aggregation with fill handling, interval validation (`MIN_MINUTES=3`), and prefix equality verification.
- **51 Microstructure & Technical Features:**
  - *Multi-Horizon Momentum:* Returns across 1, 2, 3, 5, 8, 12, 24 periods, and return acceleration.
  - *Candlestick Anatomy:* Body ratio, upper shadow ratio, lower shadow ratio, and Close Location Value (CLV).
  - *Order Flow Dynamics:* Volume-price interaction, CLV volume pressure, and relative volume (20-bar).
  - *Volatility & Trend Filters:* 14-period Average True Range (ATR), Bollinger Bands (%B and width), multi-span Exponential Moving Averages (EMA 5, 10, 12, 26, 50), and Fast/Slow EMA spreads.
  - *Oscillators & Regimes:* Fast/Standard RSI (7 & 14), Stochastic (%K & %D), MACD histogram slope, intraday VWAP distance (Madhavan 2002), and cyclical time-of-day encodings.

---

## 4. Model Architecture & Calibration

- **Classifier:** `HistGradientBoostingClassifier` trained on full historical series using cross-entropy loss, min samples leaf 50, and L2 regularization (`models/model-v1.joblib`).
- **Probability Calibration:** Native posterior probabilities from tree leaves directly optimize log-loss, preventing shrinkage distortion.
- **Operational Threshold Calibration:** Calibrated at $\delta = 0.002$ to ensure high active market participation (~95% active signals) while standing aside during indeterminate regime uncertainty (~5% neutral signals).

---

## 5. Live Architecture & Frontend Innovation

The frontend dashboard (`ui/index.html`) is built using TradingView Lightweight Charts v5.2 with an institutional "Posh Light" luxury theme and an "Obsidian Dark" mode.

### Advanced Analytical Features:
1. **Probabilistic Prediction Range Cone:** Dynamically projects a 4-candle forward price cone (~20 minutes ahead) based on calibrated probability drift, ATR volatility, and support/resistance bounds.
2. **Institutional Moving Averages & Overlays:**
   - Fast EMA 9 (cyan) & Trend EMA 21 (purple) for trend alignment.
   - Intraday VWAP (gold dashed) for institutional value anchoring.
   - Dynamic S1 / R1 horizontal support and resistance lines.
3. **Causal Technical Telemetry HUD:** Real-time digital gauges for RSI-14, MACD (12, 26, 9), ATR volatility per candle, and session S/R levels.
4. **Dynamic Trader Execution Levels (Paper Trading):** Computes Reference Close, Target (1.5R), Stop Loss (1.0R), and Risk:Reward (1:1.5) for disciplined risk management.
5. **Explainable AI (XAI) Attribution Box:** Deconstructs each prediction into core quantitative drivers: Order Flow Pressure, Price vs VWAP/EMA stack, Momentum status, and 20-minute cone boundaries.
6. **Live Prediction Scorecard & Signal History:** Displays live counts of total predictions, confident calls, directional hit rate, and neutral capital preservation rate, backed by CSV export.

---

## 6. Verification & System Health

- **Unit & Integration Suite:** 63/63 passing tests across data, features, labels, models, events, and live services (`make test`).
- **Code Quality:** 100% clean Ruff linting across all source code, tests, and scripts (`make lint`).
- **REST Stream Parity:** 221 live-captured minute bars checked against official Alpaca REST bars with **0 discrepancies** (`docs/live_vs_history.md`).
- **Repainting Immunity:** Enforced by database triggers; zero duplicate, modified, or dropped predictions recorded.
