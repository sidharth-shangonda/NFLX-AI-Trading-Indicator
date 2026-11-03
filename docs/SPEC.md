# SPEC - NFLX AI Trading Indicator

## 0. Goal
A live candlestick web app for NFLX. On every candle it shows a direction (UP / DOWN / NO CLEAR SIGNAL) and a calibrated confidence from a trained model, readable in one second, never repainting. Evaluated by running live for 5 US trading days and checking each signal against what price did next, versus simple baselines.

## 1. Instructor requirements (every one must be traceable to code, a test and a deliverable)
R1 Indicator is driven by a model trained on historical market data.
R2 Works on the live market; chart updates with every new candle.
R3 On every candle: direction (UP/DOWN/NO CLEAR SIGNAL), confidence (e.g. "UP, 54%"), clear visual.
R4 NO REPAINTING: a signal on a closed candle never changes. Repainting, no signals, or inability to run live = ZERO on the live test.
R5 Live test: 5 trading days, no changes during the test; signals checked against actual price over the stated horizon; compared with baselines (always UP, basic RSI rule).
R6 Marking: live performance 40 (accuracy of confident signals, simulated profit after costs), model quality + honest validation 20, usefulness to a trader 20, report + demo 20.
R7 Every result reproducible from the repo; every choice justified with evidence; sources cited; our own trained model (a copied public indicator scores zero).
R8 Paper trading only. One asset only (NFLX).
R9 Deliverables: repo, trained model, running app + code, report (choices, results, what did NOT work), short user guide (how to read it and when NOT to trust it), live demo + questions.

## 2. Data-provider facts and UNVERIFIED items

The facts below were marked verified from documentation checked 28 Oct 2026 in the original project notes. Short evidence notes are maintained in `docs/evidence/`; unless otherwise stated, those inherited notes have not yet been rechecked. Phase 1 must re-check every changeable claim in this section against current official sources and update the notes. Any claim that cannot be confirmed remains UNVERIFIED.

Data provider: Alpaca Markets free "Basic" market-data plan, feed = IEX.
VERIFIED from docs:
- Anyone globally can create a free Paper Only account with email. Paper includes free IEX real-time data; Market Data API works the same on paper. API secret is shown once at key generation.
- Basic plan: free, real-time coverage IEX only, history since 2016. Paid Algo Trader Plus ($99/mo, all US exchanges) is only an upgrade path.
- Stream: wss://stream.data.alpaca.markets/v2/iex. "bars" = minute bars, emitted right after each minute mark, include pre/post-market trades. "updatedBars" = corrections emitted after each half-minute mark when a late trade arrived. Most plans allow ONE concurrent stream connection (second gets error 406). Other stream errors: 405 symbol limit, 402 auth failed.
- Test stream wss://stream.data.alpaca.markets/v2/test, symbol FAKEPACA, runs 24/7 (synthetic: plumbing tests only, always labeled).
- Historical REST bars: timeframe 1Min/5Min, up to 10000 rows per page via next_page_token, adjustment (raw/split/dividend/all), feed (iex/sip).
- alpaca-py: StockHistoricalDataClient, StockBarsRequest(adjustment=..., feed=...), StockDataStream(feed=DataFeed.IEX default) with subscribe_bars(handler, *symbols) and subscribe_updated_bars(handler, *symbols). StockDataStream.run() starts its own event loop.
- NFLX did a 10-for-1 split, trading split-adjusted from 17 Nov 2025 (SEC 8-K). Price now ~$68-70 (secondary sources), so one cent is ~1.4 bp.
- IEX is only ~3-4% of US volume (IEX site: 2.8% overall Q3 2025; Rosenblatt: record 3.89% Feb 2026). Our candles/volume will NOT match TradingView's consolidated NFLX chart. UI and user guide must say "IEX feed"; outcomes are scored on the same IEX candles.
- Delayed sources (yfinance, Twelve Data free, Alpha Vantage free, Massive/Polygon below its real-time tier) FAIL the live requirement. Massive real-time starts at ~$199/mo (secondary source). Finnhub free candles for US stocks reportedly denied (github issue); do not rely on Finnhub history.
- Finnhub official docs: its real-time US data is provided by IEX; 1 key = 1 connection. Possible EMERGENCY live fallback by building bars from its trades stream (optional Phase 9, needs approval; free-tier access for NFLX trades is UNVERIFIED).
- Calendar: pandas_market_calendars NYSE calendar includes full closes, early closes and late opens.
- Lightweight Charts (Apache-2.0) requires a TradingView attribution notice + link; the attributionLogo chart option satisfies it. Use v5 API (createSeriesMarkers; series.update for the live candle). Chart time is UTC seconds.
UNVERIFIED (resolve in the listed phase and record in `docs/unverified_results.md`):
a) free 1-min NFLX history with feed=iex reaches >= 2 years (Phase 1); b) split adjustment actually applied (Phase 1); c) bar timestamp = start of interval (first regular bar is 09:30 ET; Phase 1); d) minutes with no IEX trades produce no bar (Phase 1); e) live-recorded bars equal next-day REST bars (Phase 7, after a live capture exists); f) Alpaca data display terms for showing the app to an evaluator (Phase 1); g) how to run StockDataStream inside FastAPI's event loop (check SDK source) or run it in a thread/process (Phase 1); h) HistGradientBoosting early_stopping default uses a random internal split (set early_stopping=False regardless; verify in Phase 1).

Phase 0 records the installed versions of `alpaca-py`, `scikit-learn`, `pandas`, and `pandas-market-calendars` in `docs/evidence/versions.md`.

## 3. Data and model decisions
- Data snapshot: the frozen local snapshot under `data/snapshot/`, consisting of per-month parquet files, is the source of truth. Record SHA-256 for each file's contents and a deterministic snapshot hash derived from the sorted relative paths and file-content hashes. Retrieval time and provider metadata are recorded separately and excluded from the content/snapshot hash. `make data` downloads into a temporary directory, reports drift against the frozen snapshot (row counts and hash differences), and never overwrites it silently. Every experiment references the snapshot hash.
- Bars: pull 1-min history (feed=iex, adjustment=split); build 5-min candles on the regular-session grid with ONE shared function (`src/data/candles.py`) used in training AND live. `n_minutes` is the number of distinct real minute bars in a grid candle (0-5). OHLCV comes only from real minute bars: open=first available minute open, high=max, low=min, close=last available minute close, volume=sum. Do not forward-fill inside a candle. A candle with `n_minutes == 0` is filled: O=H=L=C=previous close, volume=0, `is_filled=true`. Filled candles never get a label or prediction. A prediction for candle t requires t to be non-filled and `n_minutes >= MIN_MINUTES`; a label for t additionally requires t+1 to be non-filled and both candles to meet `MIN_MINUTES`. `MIN_MINUTES` defaults to 3 in config. Feature windows run over the session grid including filled candles, and features must tolerate them. Phase 1 reports how often candles fall below `MIN_MINUTES`; if this is frequent, stop and ask before changing the rule.
- Session: regular hours only (09:30-16:00 America/New_York) using the NYSE calendar (early closes handled). tz-aware timestamps everywhere. US clocks change 1 Nov 2026. Pre/post-market excluded in v1.
- Target: direction of the NEXT 5-minute candle. Prediction for candle t is issued after t finalizes. label = sign(close(t+1)/close(t) - 1). Last candle of the day gets no prediction; labels never cross overnight. Exact-zero returns are dropped from training; report their rate (tick size matters at ~$70).
- NO CLEAR SIGNAL is NOT a label. Model outputs calibrated P(up). UP if p >= 0.5+delta, DOWN if p <= 0.5-delta, else NO CLEAR SIGNAL. delta is chosen on dev out-of-fold predictions only, maximizing the Wilson lower bound of confident-signal accuracy subject to min coverage ~10%. Accuracy at the chosen delta on those same predictions is IN-SAMPLE for delta and must be reported as such; honest numbers = holdout + live.
- Event days: earnings release dates in config/events.yaml (verify from ir.netflix.net; secondary sources say 2026-07-16 and 2026-10-20 after the close; next one ~mid-Jan 2027, UNVERIFIED). The first session after a release is an "event session": excluded from training and from headline metrics (report with and without), and the live app shows NO CLEAR SIGNAL on it. This rule is fixed now, before seeing any results.
- Models: baselines (always UP, always DOWN, majority class, previous-candle direction, RSI rule: RSI14<30 UP, >70 DOWN, else none), then logistic regression, sklearn HistGradientBoostingClassifier, random forest. LightGBM only if needed. NO LSTM/Transformer/RL (literature gives no clear winner; deep nets not justified on this data). Select by experiment.
- Features (causal, one features.py shared by training and live): lagged/rolling returns, realized vol, ATR, rolling range, EMA distances, RSI, MACD, Bollinger position/width, relative volume, time of day, gap vs previous close. Indicators are INPUT FEATURES only. SPY/QQQ context = one ablation, dropped unless it clearly helps (extra live dependency).
- Validation: chronological only. Expanding-window walk-forward by trading day (own splitter; sklearn TimeSeriesSplit assumes equally spaced samples), ~1-month test blocks, 1-trading-day gap between train and test. Final holdout = last ~6 weeks, enforced in code: the holdout loader refuses to run unless ALLOW_HOLDOUT=1 and logs every access to experiments/holdout_access.log (must contain exactly one entry at freeze). Scalers, calibrators, thresholds, hyperparameters fit on training/validation data only. Small grids; log every trial in experiments/experiments.csv with git hash + data hash.
- Selection: lowest pooled walk-forward log loss; keep a model only if it beats baselines on pooled out-of-fold log loss AND in most folds. If nothing beats baselines, ship logistic regression with a wide NO CLEAR SIGNAL band and say so honestly.
- Calibration: sigmoid (Platt) fit on walk-forward OOF predictions, checked on later folds (reliability diagram, Brier, log loss). Isotonic only with plenty of samples. Calibration data disjoint from fitting data.
- Shipping rule: deploy EXACTLY the model that was evaluated on the holdout (no retraining afterwards). Tag it model-v1 with artifact hash.
- Metrics: primary = accuracy of confident signals with coverage and confidence intervals, plus log loss/Brier vs baselines. Secondary = balanced accuracy, MCC, confusion matrix, simulated long/short P&L at several per-side costs (0/1/2/3 bp; costs are assumptions, not facts), breakdowns by time of day and volatility tercile.
- Honest expectations (for the report): 5 days x ~77 predictions = ~385. Standard error at 50% is ~2.5 points (about +/-5 at 95%); with ~115 confident signals about +/-9. A 1-2 point edge cannot be proven live. Calibrated confidences will likely be ~52-56%, not 68%. Display what is true.
- Scenarios (bull/base/bear via vol-scaled empirical q20/q50/q80): STRETCH, build last, only if validation coverage checks out, labeled "model-derived range, not a causal explanation".

## 4. Live system
Single async FastAPI process: Alpaca ingestor -> 1-min store (SQLite) -> candle builder -> features + inference -> prediction store -> websocket push. No extra infrastructure.
- Finalization: a 5-min candle is FINAL when its available minute bars have been captured and wall clock >= candle end + 35 s (configurable; lets updatedBars arrive); record `n_minutes` for the frozen interval. Predictions use that frozen snapshot; later revisions are logged, never applied to existing predictions. States: provisional candle (no signal) / final candle / final prediction.
- NON-REPAINTING: predictions table insert-only, UNIQUE(symbol, candle_start, model_version), DB triggers reject UPDATE and DELETE. Outcomes in a separate table.
- Tables: bars_1m, candles_5m(status), predictions(id, symbol, candle_start, reference_price, horizon, direction, raw_output, calibrated_p, model_version, source_ts, generated_ts, generated_late), outcomes(prediction_id, realized_return, realized_direction, evaluated_ts, status), events (JSON logs), model_registry.
- Outcome: inserted when candle t+1 finalizes. Missing/invalid outcomes recorded with a status.
- Restart/outage: backfill missing 1-min bars via REST (feed=iex), rebuild candles. A candle that finalized while down gets no on-time prediction; a late one is flagged generated_late and excluded from live scoring. Duplicate/out-of-order bars never create two predictions. Reconnect backfills.
- Clock: log offset vs the HTTP Date header of REST responses; warn if > 2 s.
- Banner states: LIVE-IEX, STALE (no bar for 3 min in market hours), DISCONNECTED (reconnecting), AUTH ERROR, RATE LIMIT, MARKET CLOSED, TEST STREAM (synthetic), REPLAY (recorded real data). Never silently fall back to delayed data.
- Only ONE stream connection per key: no dev instance may run while the live instance runs.
- Endpoints: GET /api/health, /api/candles, /api/predictions, /api/predictions/export.csv, /api/model. WebSocket messages: snapshot, candle_update (provisional), candle_final, prediction_final, outcome, health.
- Structured JSON logs (timestamp, component, severity, event, symbol, candle ts, prediction id, model version, latency, error). Never log keys.
- Config: .env (real), .env.example (placeholders), config module, market-data adapter. Document key rotation (regenerate in Alpaca dashboard, edit .env, restart).

## 5. UI
Plain HTML/JS + Lightweight Charts v5 with attributionLogo enabled. Candles + arrow markers (blue up / orange down; shape plus color for accessibility); big "UP 54%" panel with horizon, last prediction time, model version; prediction history with realized outcomes; collapsible diagnostics drawer (feed status, last update, finalization, inference latency, errors, reconnects, data-quality warnings). Show times in BOTH New York and IST. US regular hours are 09:30-16:00 ET = 20:00-02:30 IST after 1 Nov 2026 (19:00-01:30 IST before). Market-closed state shows next open in both zones. A one-click REPLAY mode (recorded real IEX data, clearly labeled) supports demos outside market hours. Understandable in one second; not a broker terminal.

## 6. Tests (all required)
Parsing; timestamp/timezone normalization incl. the 1 Nov 2026 DST change and an early-close day; session-grid candle counts and gap/fill behavior (including `n_minutes`, `is_filled`, and `MIN_MINUTES`); missing/duplicate/out-of-order candles; feature correctness; no-look-ahead (altering future rows must not change feature at t); historical-vs-live feature equality; model input schema and inference; calibration; persistence; finalization; ATTEMPTS TO UPDATE/DELETE A FINAL PREDICTION MUST FAIL; restart creates no duplicates; reconnect + backfill; API error/auth/rate-limit handling; stale-feed banner; outcome scoring vs a hand-computed example; holdout single-touch guard. Synthetic data only in unit tests, never shown in the UI as live.

## 7. Live evaluation protocol
Freeze git tag release-v1 + model hash before the test. No edits during the 5 days. Score only on-time predictions; baselines computed on the same candles; report outages; simulated P&L reported separately from accuracy; report accuracy with and without event sessions.

## 8. Sources to re-verify against
docs.alpaca.markets/docs/paper-trading ; docs.alpaca.markets/us/docs/streaming-market-data ; alpaca.markets/docs/real-time-stock-pricing-data ; docs.alpaca.markets/us/reference/stockbars ; alpaca.markets/sdks/python ; finnhub.io/docs/api ; sec.gov 8-K ex99.1 (NFLX 10-for-1 split, 30 Oct 2025) ; scikit-learn TimeSeriesSplit and CalibratedClassifierCV docs ; tradingview.github.io/lightweight-charts ; pandas-market-calendars docs. Papers: Nabipour et al. 2020 IEEE Access 8:150199 (cautionary: random 30% test split); Fischer & Krauss 2018 EJOR 270(2):654-669 (LSTM edge fades after 2010, ~zero after costs); Lopez de Prado, Advances in Financial Machine Learning, ch. 7 (purging/embargo).
