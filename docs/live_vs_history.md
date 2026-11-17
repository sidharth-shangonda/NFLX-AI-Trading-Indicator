# Live IEX versus next-morning REST parity

- Retrieved REST comparison: `2026-11-16T21:33:46.818314+00:00`
- Symbol/feed: `NFLX` / `iex`
- Requested session interval: `2026-11-16` through `2026-11-16`
- Captured live rows: 221; REST rows: 391; common timestamps: 221
- Timestamps only in live capture: 0; only in REST: 170
- Common timestamp rows with any OHLCV difference: 0

This compares provider records only. REST rows are fetched for this diagnostic and are not saved, trained on, or sent to the UI.

## Close-difference examples

| Timestamp (UTC) | Live close | REST close |
|---|---:|---:|
| none | — | — |

## Mismatch counts by field

| Field | Different common rows |
|---|---:|
| open | 0 |
| high | 0 |
| low | 0 |
| close | 0 |
| volume | 0 |
