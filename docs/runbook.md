# Laptop runbook: live IEX soak

This is a data-only paper-account workflow. It does not place, modify, or cancel orders.

## Start

1. On the laptop, run `make test` and `make lint` before the soak.
2. Put only the Alpaca paper key ID and secret in the gitignored `.env`; do not paste or print them.
3. Confirm no other app instance is using the same Alpaca key. Keep the laptop awake and connected to the network for the full regular session.
4. Run `make serve`. Keep this one process open. Open `http://127.0.0.1:8000` and confirm `/api/health` says `LIVE-IEX` during market hours.
5. Record date, start/stop time, feed transitions, app git hash, model hash, and any outage in the soak log below. Do not run REPLAY or TEST STREAM against the live database.

## Restart and key rotation

- For a controlled restart, stop the running process with Ctrl+C, wait for shutdown, then start `make serve` once. Startup backfills recent missing bars from IEX REST.
- If credentials fail, stop the app, rotate/regenerate the paper keys in the Alpaca dashboard, replace values in `.env`, then restart. Never put the values in a command line, log, screenshot, or Git commit.
- If the banner is `DISCONNECTED`, `STALE`, `RATE LIMIT`, or `AUTH ERROR`, record the time and displayed reason. Do not call that interval live data. Let the app reconnect; its reconnect path requests REST backfill.
- Stop before using `make replay` or `FEED_MODE=test make serve`; only one stream per key should be active.

## After each session

1. Stop only after the market session and confirm the local DB is present at `data/live.sqlite`.
2. The next morning, compare captured live bars with REST without feeding REST data into training:

   ```sh
   make diff-live ARGS="--start YYYY-MM-DD --end YYYY-MM-DD"
   ```

3. Review `docs/live_vs_history.md`, the CSV export, event log counts, and the insert-only prediction ledger. Keep every prediction row intact.
4. Complete the 1-day live market evaluation (78 candles, 09:30–16:00 ET) per TA instruction. Fix bugs only. Do not tune the model or threshold.

## Soak log

| Session date | Start/end (local time) | Git hash | Model hash | Feed transitions / outage | Notes |
|---|---|---|---|---|---|
| pending | pending | pending | pending | no soak run yet | |

Do not create `release-v1` until the live bar comparison, runbook restart, and no-repaint checks pass. The 1-day live evaluation starts once live paper mode is launched.
