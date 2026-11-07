# Final holdout results — immutable after Phase 4

This file records the one owner-authorized `ALLOW_HOLDOUT=1` evaluation. Do not edit, rerun, tune, or retrain from it.

- Frozen snapshot: `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9`
- Artifact SHA-256: `8c10985bb689c3a3b6cbdb0597b117610d91659323d358a3036628f3be00c146`
- Training code commit: `b7808d2b97aa2af319c24a6eb759fb8ab61fb19b`
- Holdout: `2026-09-22` through `2026-11-02`
- Model: `logistic_regression` on `post_split`; calibration `platt`; delta `0.050`

## Calibration chronology

- Base model trained through `2026-06-09` only.
- Calibration fit sessions: `2026-06-11` through `2026-07-24`.
- Threshold selection sessions: `2026-07-28` through `2026-09-21`.
- Calibration-period log loss `0.69290`, Brier `0.24988`; later threshold-period log loss `0.69329`, Brier `0.25007`.

## Model metrics

- Log loss: **0.69325**
- Brier: **0.25005**
- Confident signals: **0/2,175** (0.00%)
- Confident-signal accuracy: **n/a**; Wilson lower bound: **0.00%**
- Balanced accuracy: n/a; MCC: n/a
- Confusion matrix: `{"true_down_pred_down": 0, "true_down_pred_up": 0, "true_up_pred_down": 0, "true_up_pred_up": 0}`
- Simulated P&L assumes a complete long/short entry and exit on every confident signal; results are not trading results:

## Same-candle baseline probability metrics

| Baseline | Log loss | Brier | Signal coverage | Signal accuracy |
|---|---:|---:|---:|---:|
| neutral_50_50 | 0.69315 | 0.25000 | 0.00% | n/a |
| always_up | 7.16501 | 0.51862 | 100.00% | 48.14% |
| always_down | 6.65050 | 0.48138 | 100.00% | 51.86% |
| majority_class | 6.65050 | 0.48138 | 100.00% | 51.86% |
| previous_candle_direction | 7.06338 | 0.51126 | 100.00% | 48.87% |
| rsi_rule | 2.29323 | 0.31437 | 25.75% | 50.00% |

## Breakdowns

The JSON metadata records time-of-day and holdout-volatility-tercile breakdowns. They are descriptive, not tuning inputs.
