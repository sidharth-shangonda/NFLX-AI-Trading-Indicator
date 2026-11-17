# Recorded indicator score

- Feed: LIVE DB (verify health log)
- Database: `live.sqlite`
- Model: `model-v1`
- Artifact SHA-256: `87043fbb25384ac6f8e890e2e1ca6ae90074292a2ba8d79cf71a4535ad786773`
- Snapshot hash: `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9`
- Sessions: 2026-11-10 through 2026-11-16 (2)
- Matched on-time outcomes: 54
- Excluded rows: 570
- Zero-return share (reported separately): 5.5556%
- Recorded ERROR/CRITICAL events: 2
- Feed state transition severities: `{"INFO": 7}`

This is a descriptive score of the selected local database. It does not retrain,
calibrate, tune, or modify `model-v1`. Simulated P&L is separate from accuracy and
uses the stated 0/1/2/3 bp per-side cost assumptions (two sides per completed horizon).
Zero-return outcomes are excluded from binary metrics, as in training, but remain in
the P&L calculation. Baselines use the same matched candle outcomes.

## Metrics

### All

| Method | Rows | Signals | Coverage | Signal accuracy | Log loss | Brier | P&L bp @ 0 / 1 / 2 / 3 bp per side |
|---|---:|---:|---:|---:|---:|---:|---|
| model-v1 | 54 | 45 | 0.8333 | 0.5111 | 0.6907 | 0.2488 | -39.9 / -129.9 / -219.9 / -309.9 |
| always_up | 54 | 54 | 1.0000 | 0.3889 | 8.1268 | 0.5882 | -163.6 / -271.6 / -379.6 / -487.6 |
| always_down | 54 | 54 | 1.0000 | 0.5556 | 5.6887 | 0.4118 | 163.6 / 55.6 / -52.4 / -160.4 |
| majority_class_expanding | 54 | 53 | 0.9815 | 0.4906 | 6.5150 | 0.4755 | 74.8 / -31.2 / -137.2 / -243.2 |
| previous_candle_direction | 54 | 51 | 0.9444 | 0.4314 | 7.0840 | 0.5245 | -8.5 / -110.5 / -212.5 / -314.5 |
| rsi14_rule | 54 | 16 | 0.2963 | 0.3750 | 3.1846 | 0.3676 | -63.5 / -95.5 / -127.5 / -159.5 |

### Non Event

| Method | Rows | Signals | Coverage | Signal accuracy | Log loss | Brier | P&L bp @ 0 / 1 / 2 / 3 bp per side |
|---|---:|---:|---:|---:|---:|---:|---|
| model-v1 | 54 | 45 | 0.8333 | 0.5111 | 0.6907 | 0.2488 | -39.9 / -129.9 / -219.9 / -309.9 |
| always_up | 54 | 54 | 1.0000 | 0.3889 | 8.1268 | 0.5882 | -163.6 / -271.6 / -379.6 / -487.6 |
| always_down | 54 | 54 | 1.0000 | 0.5556 | 5.6887 | 0.4118 | 163.6 / 55.6 / -52.4 / -160.4 |
| majority_class_expanding | 54 | 53 | 0.9815 | 0.4906 | 6.5150 | 0.4755 | 74.8 / -31.2 / -137.2 / -243.2 |
| previous_candle_direction | 54 | 51 | 0.9444 | 0.4314 | 7.0840 | 0.5245 | -8.5 / -110.5 / -212.5 / -314.5 |
| rsi14_rule | 54 | 16 | 0.2963 | 0.3750 | 3.1846 | 0.3676 | -63.5 / -95.5 / -127.5 / -159.5 |

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
| all | 4 (0.4-0.5) | 21 | 0.4865 | 0.3810 |
| all | 5 (0.5-0.6) | 23 | 0.5177 | 0.4348 |
| non_event | 4 (0.4-0.5) | 21 | 0.4865 | 0.3810 |
| non_event | 5 (0.5-0.6) | 23 | 0.5177 | 0.4348 |

## Notes

- Event sessions present: none.
- Prediction reasons in matched rows: `{"feature_warmup": 7, "signal": 42, "uncertain_model_probability": 5}`.
- Live outage duration is not inferred from error-event counts; use the health and host logs for the soak report.
- A REPLAY database is historical plumbing evidence, not a live evaluation.
