# Historical data quality

Snapshot hash: `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9`
Requested range (UTC): `2024-10-01T00:00:00+00:00` to `2026-11-03T09:13:00+00:00`
Returned timestamp range (UTC): `2024-10-01T13:30:00+00:00` to `2026-11-02T20:59:00+00:00`
Total 1-minute rows: **147,124**
Files: **26** UTC calendar-month parquet files (local, ignored by Git)

## Quality counts

- Complete NYSE sessions checked: 524
- Regular-session rows: 145,958
- Pre/post-market or outside-session rows: 1,166
- Expected regular-session minute slots: 203,460
- Missing regular-session minute slots: 57,502 (28.2621%)
- Duplicate timestamp rows: 0
- Invalid OHLCV rows: 0
- Invalid timestamp rows: 0
- Off-grid regular-session timestamps: 0
- Regular-session 5-minute grid candles: 40,692
- Candles with fewer than 3 real minute bars: 12,014 (29.5242%)
- Zero-minute filled candles: 2,857

## Timestamp check

- Latest complete session first bar (ET): `2026-11-02T09:30:00-05:00`
- First bar equals that session's 09:30 ET open: `True`
- Convention assessment: **VERIFIED**. Alpaca documents minute timestamps as the interval's left edge; see `docs/evidence/alpaca_historical_bars.md`.

## Split-adjustment check

- Status: **PASS**
- Pre-split adjusted/raw close factor: 0.09999955040216525
- Post-split adjusted/raw close factor: 1.0
- Adjusted Nov 17 / Nov 14 close ratio: 0.9919072025896952
- No approximately 10x jump: True

Counts use complete NYSE regular sessions only. A missing minute means no returned bar occupied that slot.
This does not establish whether the cause was no eligible IEX trade or a data gap.

No parquet rows are committed. Rebuild steps are in `README.md`; the manifest and content hashes are in `docs/data_manifest.json`.
