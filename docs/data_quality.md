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
- MIN_MINUTES configured: 3 (unchanged)
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

## Five-minute candle diagnostics

Total grid candles: 40,692; filled (n=0): 2,857 (7.02%).

### n_minutes distribution

| n_minutes | Candles | Share |
|---:|---:|---:|
| 0 | 2,857 | 7.02% |
| 1 | 4,412 | 10.84% |
| 2 | 4,745 | 11.66% |
| 3 | 4,086 | 10.04% |
| 4 | 3,162 | 7.77% |
| 5 | 21,430 | 52.66% |

Zero-return rate: 1,076/37,313 same-session close-to-close observations ending at a non-filled candle (2.88%).
Returns are close-to-close, computed only within a session. The first candle of each session has no return observation.

### Below-3 share by month

| Session month | Candles | Below 3 | Below-3 share |
|---|---:|---:|---:|
| 2024-10 | 1,794 | 795 | 44.31% |
| 2024-11 | 1,524 | 659 | 43.24% |
| 2024-12 | 1,602 | 1,011 | 63.11% |
| 2025-01 | 1,560 | 682 | 43.72% |
| 2025-02 | 1,482 | 747 | 50.40% |
| 2025-03 | 1,638 | 745 | 45.48% |
| 2025-04 | 1,638 | 701 | 42.80% |
| 2025-05 | 1,638 | 1,154 | 70.45% |
| 2025-06 | 1,560 | 1,228 | 78.72% |
| 2025-07 | 1,680 | 1,039 | 61.85% |
| 2025-08 | 1,638 | 1,234 | 75.34% |
| 2025-09 | 1,638 | 1,108 | 67.64% |
| 2025-10 | 1,794 | 910 | 50.72% |
| 2025-11 | 1,446 | 1 | 0.07% |
| 2025-12 | 1,680 | 0 | 0.00% |
| 2026-01 | 1,560 | 0 | 0.00% |
| 2026-02 | 1,482 | 0 | 0.00% |
| 2026-03 | 1,716 | 0 | 0.00% |
| 2026-04 | 1,638 | 0 | 0.00% |
| 2026-05 | 1,560 | 0 | 0.00% |
| 2026-06 | 1,638 | 0 | 0.00% |
| 2026-07 | 1,716 | 0 | 0.00% |
| 2026-08 | 1,638 | 0 | 0.00% |
| 2026-09 | 1,638 | 0 | 0.00% |
| 2026-10 | 1,716 | 0 | 0.00% |
| 2026-11 | 78 | 0 | 0.00% |

### Before and after split cutoff

| Session period | Candles | Below 3 | Below-3 share |
|---|---:|---:|---:|
| before_2025-11-17 | 21,966 | 12,014 | 54.69% |
| on_or_after_2025-11-17 | 18,726 | 0 | 0.00% |

### Below-3 share by time of day

| ET candle-start bucket | Candles | Below 3 | Below-3 share |
|---|---:|---:|---:|
| close_15:30-16:00 | 3,114 | 507 | 16.28% |
| midday | 34,434 | 11,054 | 32.10% |
| open_09:30-10:00 | 3,144 | 453 | 14.41% |

### Below-3 share by weekday

| Weekday | Candles | Below 3 | Below-3 share |
|---|---:|---:|---:|
| Friday | 8,040 | 2,362 | 29.38% |
| Monday | 7,878 | 2,447 | 31.06% |
| Thursday | 7,998 | 2,239 | 27.99% |
| Tuesday | 8,466 | 2,371 | 28.01% |
| Wednesday | 8,310 | 2,595 | 31.23% |

### Mean absolute close-to-close return and volume by n_minutes

| n_minutes | Candles | Return observations | Mean absolute return (%) | Mean IEX volume |
|---:|---:|---:|---:|---:|
| 0 | 2,857 | 2,855 | 0.00000 | 0.00 |
| 1 | 4,412 | 4,408 | 0.09108 | 3,004.15 |
| 2 | 4,745 | 4,728 | 0.11435 | 6,928.23 |
| 3 | 4,086 | 4,046 | 0.13375 | 11,971.01 |
| 4 | 3,162 | 3,076 | 0.15932 | 19,748.96 |
| 5 | 21,430 | 21,055 | 0.12899 | 30,728.19 |

Returns are assigned to the current candle's n_minutes and compare its close with the prior five-minute grid close. No overnight return is used; n=0 closes carry forward and have zero volume by construction.

### Training-window observation (not adopted)

Below-3 sparsity was 12,014/21,966 candles (54.69%) before 2025-11-17 and 0/18,726 (0.00%) on/after it. The post-cutoff sample contains 18,726 candles. This large coverage discontinuity supports considering post-cutoff-only training, with full-history training as a comparison experiment; it does not establish why IEX coverage changed. This is a recommendation only and requires owner approval before adopting a training window.

## SIP feed comparison (diagnostic only)

Historical `feed=sip` access succeeded for 2026-10-26T00:00:00+00:00 through 2026-10-31T00:00:00+00:00 (five complete sessions; older than 15 minutes).
The sample returned 4,205 1-minute SIP rows. On shared regular-session grid candles with real bars in both feeds, IEX and SIP closes differed in 255/390 candles (65.38%).
Absolute close differences: mean 0.935 bp, median 0.794 bp, max 7.287 bp.
This was an isolated diagnostic. SIP rows were not saved, committed, or used for training or the live path.
