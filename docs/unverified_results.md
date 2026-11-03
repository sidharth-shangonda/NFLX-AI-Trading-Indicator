# Phase 1 UNVERIFIED items

Checked on 2026-11-03 against the frozen snapshot `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9` and official sources in `docs/evidence/`.

| Item | Status | Phase 1 evidence |
|---|---|---|
| a. Free IEX 1-minute history >= 2 years | PASS >= 2 years | 147,124 rows; `2024-10-01T13:30:00+00:00` to `2026-11-02T20:59:00+00:00`. |
| b. Split adjustment applied | PASS | see split summary in data quality report and log. |
| c. Bar timestamp is interval start | VERIFIED | First regular bar: `2026-11-02T09:30:00-05:00` ET; official docs describe the left-edge convention. |
| d. No eligible IEX trade may yield no bar | VERIFIED in docs; historical gap share measured | 57,502 missing minutes; below-3-minute candle share 29.5242%. |
| e. Live-recorded bars equal next-day REST bars | UNVERIFIED — Phase 7 | No eligible live capture has been compared with next-day REST yet. |
| f. Evaluator display/redistribution permission | UNVERIFIED | The terms do not settle a private demo or derived signals. |
| g. StockDataStream inside FastAPI loop | VERIFIED: thread/process | Pinned `.run()` calls `asyncio.run`. |
| h. HGB early-stopping split | VERIFIED with condition | In sklearn 1.9.1, auto enables a random split above 10,000 samples; set `early_stopping=False`. |

The 5% pause condition uses `candles_below_min_minutes_share`.
The measured share exceeds 5%; the owner directed that MIN_MINUTES remain 3.
The candle-t gate and t+1 label rule are recorded in SPEC section 3.
