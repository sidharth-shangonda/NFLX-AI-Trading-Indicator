# NFLX AI Trading Indicator 

Paper-only university ML project for a trained NFLX indicator. The application is planned for local laptop use and Alpaca's IEX market-data feed.

## Key Results & Model Performance

- **Model Architecture:** `HistGradientBoostingClassifier` (Scikit-Learn histogram gradient boosted trees, trained & frozen in `models/model-v1.joblib`)
- **Feature Set:** 51 strictly causal market microstructure and technical features (zero future lookahead leakage)
- **Live Market Trading Accuracy (Nov 16, 2026):** **57.14%** directional hit rate (40/70 correct on full regular NYSE session of 78 candles)
- **Live Baseline Outperformance:** Outperformed Always `UP` (**+13.90%**), Random Walk (**+7.14%**), Expanding Majority (**+8.08%**), and Always `DOWN` (**+0.38%**)
- **Live Operational Coverage:** **94.87%** active predictions (74/78), with **5.13%** neutral stand-aside during high ambiguity
- **Out-of-Sample Holdout Accuracy:** **52.17%** on confident signals (360/690 correct, $\delta = 0.020$, 2,175 candles)
- **Log Loss / Brier Score:** **0.6892 / 0.2480** (live), **0.69257 / 0.24971** (holdout) — both beat 50/50 neutral baselines
- **Non-Repainting Guarantee:** SQLite `BEFORE UPDATE` and `BEFORE DELETE` triggers abort any retroactive modification
- **Live vs REST Stream Parity:** 221 common minute bars verified with **0 discrepancies** across Open, High, Low, Close, and Volume (`docs/live_vs_history.md`)
- **Frontend Dashboard:** Interactive TradingView Lightweight Charts v5.2, dual ET/IST clocks, Probabilistic Range Cone, institutional VWAP, EMA 9/21, Causal HUD Telemetry (RSI, MACD, ATR, S1/R1), Dynamic Trader Execution Levels (1:1.5 RR), Explainable AI (XAI) Attribution Box, and Live Scorecard
- **Test Suite:** **63/63 passing unit tests** (`make test`), 100% clean Ruff linting (`make lint`)

## Live Operational Evaluation Scorecard (Nov 16, 2026)

Full regular NYSE trading session (09:30–16:00 ET / 14:30–21:00 UTC / 20:00–02:30 IST):

| Metric / Benchmark | Value / Hit Rate | Notes |
|---|---|---|
| **Candles Captured** | **78 / 78 (100%)** | Full NYSE regular trading session |
| **Active Predictions** | **74 (94.87%)** | 32 UP (41.0%), 42 DOWN (53.8%) |
| **Neutral Stand-Aside** | **4 (5.13%)** | Deliberate risk mitigation during high ambiguity |
| **`model-v1` Accuracy** | **57.14% (40 / 70)** | Evaluated on non-zero return candles |
| **On-Time Signal Accuracy** | **58.97% (23 / 39)** | Evaluated on strictly on-time candles (`generated_late == 0`) |
| Always `DOWN` Baseline | 56.76% (42 / 74) | Model beat by +0.38% |
| Random Walk (Expected) | 50.00% (37 / 74) | Model beat by +7.14% |
| Expanding Majority Class | 49.06% (26 / 53) | Model beat by +8.08% |
| Always `UP` Baseline | 43.24% (32 / 74) | Model beat by **+13.90%** |
| Previous-Candle Direction | 43.14% (22 / 51) | Model beat by +14.00% |
| RSI-14 Rule | 37.50% (6 / 16) | Model beat by +19.64% |
| Repainting Incidents | **0 (Zero)** | Verified via SQLite engine triggers |
| REST Feed Discrepancies | **0 (Zero)** | Verified across 221 common minute bars |

Detailed documentation: [Executive Summary](docs/summary.md) | [Live Market Evaluation](docs/results_live.md) | [Holdout Evaluation](docs/results_holdout.md) | [Model Card](docs/model_card.md)

## Setup

```sh
make setup
make test
make lint
```

Put your Alpaca **paper** credentials in the local, gitignored `.env` file using the names in `.env.example`. Never commit or share those values.

## Historical data snapshot

The first historical download is explicit and writes a frozen local snapshot under `data/snapshot/`:

```sh
make data-freeze
```

This fetches NFLX 1-minute bars from Alpaca using `feed=iex` and `adjustment=split`, and writes monthly parquet files, `data/manifest.json`, and a non-row manifest/hash record at `docs/data_manifest.json`. The `data/` directory is gitignored; no parquet data is committed. The snapshot content hash covers sorted relative file paths and file-content SHA-256 values, not retrieval time or provider metadata.

To check provider drift, `make data` downloads the same recorded interval to a temporary directory and reports row-count and file-hash differences. It does not replace the frozen snapshot. If the project has no local snapshot, create one with `make data-freeze`.

To rebuild after cloning, run `make setup`, add your paper keys to `.env`, then run `make data-freeze`. Historical data may change at the provider; record the resulting manifest and snapshot hash with any experiment. Ask before committing any parquet or other market-data files.

The current Alpaca data display/redistribution terms do not clearly settle a private university evaluator demo; see `docs/evidence/alpaca_data_display_terms.md`. Until clarified, keep the data local and expose no raw bars to third parties.

## Train, serve, and replay

The frozen `model-v1` artifact is used exactly as evaluated; normal app startup does not retrain it.

```sh
make train
```

After a model has been frozen, `make train` is a read-only verification: it checks the model checksum, frozen-snapshot hash, exact feature schema, and a complete inference pass without reading labels or changing the model. This keeps the recorded test result intact. `make train-dev` is only for a fresh, pre-freeze development run; it intentionally refuses to rerun once the final holdout has been accessed.

```sh
make serve
```

Open `http://127.0.0.1:8000`. `make serve` uses the local paper credentials and the IEX market-data stream. It has no order-entry path. Run only one instance at a time for this Alpaca key. On a market day, confirm the banner says `LIVE-IEX`; after hours it should say `MARKET CLOSED`. An `AUTH ERROR` or `DISCONNECTED` banner means the feed is not live.

To demonstrate outside market hours, run `make replay` and open the same local URL. If the replay database is empty, the dashboard automatically loads the latest five recorded sessions; **Run replay** reruns them. The banner remains `REPLAY`; these are recorded historical IEX bars, not live prices. The chart footer identifies Lightweight Charts or the built-in fallback view. If the chart area is empty, check the feed banner and the diagnostics drawer; the dashboard will say whether it is waiting for live candles, loading replay data, or cannot reach the local API. `FEED_MODE=test make serve` is only for testing the stream connection and displays `TEST STREAM` on synthetic `FAKEPACA` data.

Download the prediction log with **Export CSV** or visit `/api/predictions/export.csv`. Health and model metadata are available at `/api/health` and `/api/model`.

## Score recorded runs

`make score` reads `data/replay.sqlite` and reports model-v1 alongside always-UP, always-DOWN, expanding majority, previous-candle direction, and RSI14 baselines on the same recorded outcomes. It separates event-session results, reports probability metrics and confident-signal coverage/accuracy, lists recorded errors, and keeps cost-assumption P&L separate. It never fits or changes the model. To score a live database or another file, use:

```sh
.venv/bin/python scripts/score.py --database data/live.sqlite --output docs/score_report.md
```

Replay and live databases are local artifacts and are intentionally not committed. A clean clone needs the frozen local snapshot rebuilt with `make data-freeze`; run a replay to create `data/replay.sqlite` before using the default `make score` target.

## Live soak operations

See [the host runbook](docs/runbook.md), [the user guide](docs/user_guide.md), and [the demo checklist](docs/demo_checklist.md). Phase status, acceptance checks, and known blockers remain in `docs/PLAN.md`. A test-stream connection or historical replay does not count as live soak evidence.

## Project status

See `docs/SPEC.md` and `docs/PLAN.md` for requirements, phase gates, and progress.
