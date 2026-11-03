# Phase 1 UNVERIFIED items

Checked 2026-11-03 against the current official source notes and pinned local library source. No historical API request was sent because Alpaca credentials were unavailable in local `.env`; the historical checks below remain pending.

| Item | Status | Evidence / next check |
|---|---|---|
| a. Free IEX 1-minute NFLX history reaches at least 2 years | UNVERIFIED | `make data-freeze` stopped before the API request; test the account's returned range. |
| b. Split adjustment is applied | UNVERIFIED | No raw or split-adjusted bars were queried; compare 2025-11-14 and 2025-11-17 after credentials are configured. |
| c. Bar timestamp is interval start and the first regular bar is 09:30 ET | UNVERIFIED empirically | Alpaca's official FAQ describes the minute timestamp as the interval's left edge; inspect returned regular-session timestamps after the snapshot exists. |
| d. Minutes with no eligible IEX trades produce no bar | VERIFIED as documented behavior; historical gap cause UNVERIFIED | Alpaca's aggregation FAQ says bars are omitted when no eligible trade updates prices. A missing historical minute could also have another cause. |
| e. Live-recorded bars equal next-day REST bars | UNVERIFIED — Phase 7 | Requires an eligible live capture and next-day REST comparison. |
| f. Display/redistribution permission for a private evaluator demo or derived signals | UNVERIFIED | See `docs/evidence/alpaca_data_display_terms.md`; keep parquet local and ignored. |
| g. `StockDataStream` event-loop behavior | VERIFIED for alpaca-py 0.44.0 | Installed source calls `asyncio.run()` in `.run()`; Phase 5 should use a dedicated thread/process. |
| h. HGB automatic early stopping uses a random internal split | VERIFIED for scikit-learn 1.9.1 | Installed source enables `train_test_split` with `early_stopping='auto'` above 10,000 samples. Always set `early_stopping=False`. |

The data request and resulting quality statistics are recorded in `docs/data_quality.md`; that report currently contains the credential blocker and no invented data values.
