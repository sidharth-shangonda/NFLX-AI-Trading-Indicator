# Final holdout results — evaluated on out-of-sample testing data

This file records the verified `ALLOW_HOLDOUT=1` evaluation on the chronological test holdout.

- Frozen snapshot: `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9`
- Artifact SHA-256: `87043fbb25384ac6f8e890e2e1ca6ae90074292a2ba8d79cf71a4535ad786773`
- Training code commit: `f92581db9ec5ef87c1f179cc92e01720a4f8ea59`
- Holdout: `2026-09-22` through `2026-11-02`
- Model: `hist_gradient_boosting` on `full_history`; calibration `identity`; delta `0.020`

## Calibration chronology

- Base model trained through `2026-09-21`.
- Calibration fit sessions: `2026-02-19` through `2026-06-04`.
- Threshold selection sessions: `2026-06-08` through `2026-09-21`.
- Calibration-period log loss `0.69485`, Brier `0.25084`; later threshold-period log loss `0.69423`, Brier `0.25053`.

## Model metrics

- Log loss: **0.69257**
- Brier: **0.24971**
- Confident signals: **690/2,175** (31.72%)
- Confident-signal accuracy: **52.17%**; Wilson lower bound: **48.44%**
- Balanced accuracy: 52.07%; MCC: 0.0414
- Confusion matrix: `{"true_down_pred_down": 196, "true_down_pred_up": 165, "true_up_pred_down": 165, "true_up_pred_up": 164}`
- Simulated P&L assumes a complete long/short entry and exit on every confident signal; results are not trading results:
  - 0 bp per side: total 1029.98 bp; mean 1.4927 bp/signal
  - 1 bp per side: total -350.02 bp; mean -0.5073 bp/signal
  - 2 bp per side: total -1730.02 bp; mean -2.5073 bp/signal
  - 3 bp per side: total -3110.02 bp; mean -4.5073 bp/signal

## Same-candle baseline probability metrics

| Baseline | Log loss | Brier | Signal coverage | Signal accuracy |
|---|---:|---:|---:|---:|
| neutral_50_50 | 0.69315 | 0.25000 | 0.00% | n/a |
| always_up | 7.16501 | 0.51862 | 100.00% | 48.14% |
| always_down | 6.65050 | 0.48138 | 100.00% | 51.86% |
| majority_class | 7.16501 | 0.51862 | 100.00% | 48.14% |
| previous_candle_direction | 7.00621 | 0.50713 | 100.00% | 49.29% |
| rsi_rule | 2.28752 | 0.31414 | 25.66% | 50.00% |

## Breakdowns

The JSON metadata records time-of-day and holdout-volatility-tercile breakdowns.

---

## Subsequent Operational Evaluation

Following holdout verification, the frozen model was evaluated in real-time on live market data during the full regular NYSE session of Monday, November 16, 2026. The live operational hit rate reached **57.14%** (40/70 correct) across 78 candles. Complete live results, baseline comparisons, and REST parity checks are documented in [docs/results_live.md](results_live.md).
