# Historical data quality

**Status: BLOCKED — no historical request was sent.**

On 2026-11-03, `make data-freeze` stopped because the local `.env` did not provide both Alpaca credentials. It exited before calling the historical endpoint. No parquet files, local manifest, or tracked data manifest were created.

The planned initial request is NFLX 1-minute bars, `feed=iex`, `adjustment=split`, from 2024-10-01 UTC through the UTC minute when the owner runs `make data-freeze`. The actual returned date range and row count are unavailable.

| Check | Result |
|---|---|
| Regular-session rows and missing-minute share | UNAVAILABLE — no snapshot |
| 5-minute candle counts and share with fewer than 3 minute bars | UNAVAILABLE — no snapshot; the 5% stop condition has not been evaluated |
| Duplicate rows, invalid OHLCV, off-grid timestamps | UNAVAILABLE — no snapshot |
| Timestamp convention / first 09:30 ET observation | UNVERIFIED empirically — no snapshot |
| Split adjustment around 2025-11-14 to 2025-11-17 | UNVERIFIED empirically — no API query |

Setup fix: add the paper credentials to the local, gitignored `.env` using the variable names in `.env.example`, then rerun `make data-freeze`. Do not send credentials in chat. After a successful freeze, run `make data` to report drift and `make verify-data` for historical checks. All parquet files remain in ignored `data/` pending clarification of display and redistribution terms.
