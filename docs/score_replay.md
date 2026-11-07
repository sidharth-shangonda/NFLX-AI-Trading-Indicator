# Recorded indicator score

- Feed: REPLAY (recorded IEX bars)
- Database: `replay.sqlite`
- Model: `model-v1`
- Artifact SHA-256: `8c10985bb689c3a3b6cbdb0597b117610d91659323d358a3036628f3be00c146`
- Snapshot hash: `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9`
- Sessions: 2026-10-27 through 2026-11-02 (5)
- Matched on-time outcomes: 385
- Excluded rows: 5
- Zero-return share (reported separately): 3.6364%
- Recorded ERROR/CRITICAL events: 0
- Feed state transition severities: `{}`

This is a descriptive score of the selected local database. It does not retrain,
calibrate, tune, or modify `model-v1`. Simulated P&L is separate from accuracy and
uses the stated 0/1/2/3 bp per-side cost assumptions (two sides per completed horizon).
Zero-return outcomes are excluded from binary metrics, as in training, but remain in
the P&L calculation. Baselines use the same matched candle outcomes.

## Metrics

### All

| Method | Rows | Signals | Coverage | Signal accuracy | Log loss | Brier | P&L bp @ 0 / 1 / 2 / 3 bp per side |
|---|---:|---:|---:|---:|---:|---:|---|
| model-v1 | 385 | 0 | 0.0000 | — | 0.6923 | 0.2496 | 0.0 / 0.0 / 0.0 / 0.0 |
| always_up | 385 | 385 | 1.0000 | 0.4571 | 7.2615 | 0.5256 | -140.8 / -910.8 / -1680.8 / -2450.8 |
| always_down | 385 | 385 | 1.0000 | 0.5065 | 6.5540 | 0.4744 | 140.8 / -629.2 / -1399.2 / -2169.2 |
| majority_class_expanding | 385 | 384 | 0.9974 | 0.4974 | 6.6676 | 0.4832 | -23.0 / -791.0 / -1559.0 / -2327.0 |
| previous_candle_direction | 385 | 371 | 0.9636 | 0.5013 | 6.4293 | 0.4724 | 124.6 / -617.4 / -1359.4 / -2101.4 |
| rsi14_rule | 385 | 81 | 0.2104 | 0.5185 | 1.8526 | 0.2925 | 284.9 / 122.9 / -39.1 / -201.1 |

### Non Event

| Method | Rows | Signals | Coverage | Signal accuracy | Log loss | Brier | P&L bp @ 0 / 1 / 2 / 3 bp per side |
|---|---:|---:|---:|---:|---:|---:|---|
| model-v1 | 385 | 0 | 0.0000 | — | 0.6923 | 0.2496 | 0.0 / 0.0 / 0.0 / 0.0 |
| always_up | 385 | 385 | 1.0000 | 0.4571 | 7.2615 | 0.5256 | -140.8 / -910.8 / -1680.8 / -2450.8 |
| always_down | 385 | 385 | 1.0000 | 0.5065 | 6.5540 | 0.4744 | 140.8 / -629.2 / -1399.2 / -2169.2 |
| majority_class_expanding | 385 | 384 | 0.9974 | 0.4974 | 6.6676 | 0.4832 | -23.0 / -791.0 / -1559.0 / -2327.0 |
| previous_candle_direction | 385 | 371 | 0.9636 | 0.5013 | 6.4293 | 0.4724 | 124.6 / -617.4 / -1359.4 / -2101.4 |
| rsi14_rule | 385 | 81 | 0.2104 | 0.5185 | 1.8526 | 0.2925 | 284.9 / 122.9 / -39.1 / -201.1 |

### Event

| Method | Rows | Signals | Coverage | Signal accuracy | Log loss | Brier | P&L bp @ 0 / 1 / 2 / 3 bp per side |
|---|---:|---:|---:|---:|---:|---:|---|
| model-v1 | 0 | 0 | — | — | — | — | — / — / — / — |
| always_up | 0 | 0 | — | — | — | — | — / — / — / — |
| always_down | 0 | 0 | — | — | — | — | — / — / — / — |
| majority_class_expanding | 0 | 0 | — | — | — | — | — / — / — / — |
| previous_candle_direction | 0 | 0 | — | — | — | — | — / — / — / — |
| rsi14_rule | 0 | 0 | — | — | — | — | — / — / — / — |

## Model calibration bins

| Slice | P(UP) bin | Rows | Mean predicted | Observed up rate |
|---|---:|---:|---:|---:|
| all | 4 (0.4-0.5) | 220 | 0.4914 | 0.4682 |
| all | 5 (0.5-0.6) | 76 | 0.5039 | 0.5526 |
| non_event | 4 (0.4-0.5) | 220 | 0.4914 | 0.4682 |
| non_event | 5 (0.5-0.6) | 76 | 0.5039 | 0.5526 |

## Notes

- Event sessions present: none.
- Prediction reasons in matched rows: `{"feature_warmup": 77, "uncertain_model_probability": 308}`.
- Live outage duration is not inferred from error-event counts; use the health and host logs for the soak report.
- A REPLAY database is historical plumbing evidence, not a live evaluation.
