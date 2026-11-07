# NFLX AI Trading Indicator

Paper-only university ML project for a trained NFLX indicator. The application is planned for local laptop use and Alpaca's IEX market-data feed.

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
make serve
```

Open `http://127.0.0.1:8000`. `make serve` uses the local paper credentials and the IEX market-data stream. It has no order-entry path. Run only one instance at a time for this Alpaca key. On a market day, confirm the banner says `LIVE-IEX`; after hours it should say `MARKET CLOSED`. An `AUTH ERROR` or `DISCONNECTED` banner means the feed is not live.

To demonstrate outside market hours, run `make replay`, open the same local URL, and press **Run replay**. The banner remains `REPLAY`; these are recorded historical IEX bars, not live prices. `FEED_MODE=test make serve` is only for testing the stream connection and displays `TEST STREAM` on synthetic `FAKEPACA` data.

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
