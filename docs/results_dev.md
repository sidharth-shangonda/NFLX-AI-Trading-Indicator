# Development walk-forward results

These are development-only results. The final 30 NYSE sessions are locked and were not loaded.

- Frozen snapshot: `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9`
- Code commit: `164a36c30ee76ba18a04d1410953d2c85b6f793d`
- Final holdout sessions: `2026-09-22` through `2026-11-02`
- Holdout access-log entries: **0** (must be zero in Phase 3)
- Walk-forward: expanding train; 60 initial NYSE sessions; 1-session gap; 20-session test blocks; seed `20261107`.
- The date universe includes excluded event sessions, so the one-session embargo remains a trading-day embargo even when an event day supplies no supervised rows.

## Pooled out-of-fold results

| Window | Feature set | Method | OOF rows | Log loss | Brier | Accuracy | Signal coverage | Signal accuracy |
|---|---|---|---:|---:|---:|---:|---:|---:|
| full_history | all_features | neutral_50_50 | 22,193 | 0.69315 | 0.25000 | 50.03% | 100.00% | 50.03% |
| full_history | all_features | logistic_regression | 22,193 | 0.69400 | 0.25042 | 50.43% | 100.00% | 50.43% |
| full_history | all_features | random_forest | 22,193 | 0.69403 | 0.25044 | 50.60% | 100.00% | 50.60% |
| full_history | all_features | hist_gradient_boosting | 22,193 | 0.70152 | 0.25400 | 49.74% | 100.00% | 49.74% |
| full_history | all_features | rsi_rule | 22,193 | 2.42769 | 0.31962 | 50.41% | 27.99% | 50.13% |
| full_history | all_features | always_up | 22,193 | 6.90309 | 0.49966 | 50.03% | 100.00% | 50.03% |
| full_history | all_features | majority_class | 22,193 | 6.90309 | 0.49966 | 50.03% | 100.00% | 50.03% |
| full_history | all_features | always_down | 22,193 | 6.91242 | 0.50034 | 49.97% | 100.00% | 49.97% |
| full_history | all_features | previous_candle_direction | 22,193 | 6.98588 | 0.50565 | 49.43% | 100.00% | 49.43% |
| post_split | all_features | neutral_50_50 | 11,136 | 0.69315 | 0.25000 | 50.18% | 100.00% | 50.18% |
| post_split | all_features | logistic_regression | 11,136 | 0.69568 | 0.25123 | 49.52% | 100.00% | 49.52% |
| post_split | all_features | random_forest | 11,136 | 0.69570 | 0.25126 | 49.82% | 100.00% | 49.82% |
| post_split | all_features | hist_gradient_boosting | 11,136 | 0.70197 | 0.25422 | 50.03% | 100.00% | 50.03% |
| post_split | all_features | rsi_rule | 11,136 | 2.39866 | 0.31935 | 50.41% | 27.07% | 49.39% |
| post_split | all_features | always_up | 11,136 | 6.88294 | 0.49820 | 50.18% | 100.00% | 50.18% |
| post_split | all_features | always_down | 11,136 | 6.93257 | 0.50180 | 49.82% | 100.00% | 49.82% |
| post_split | all_features | majority_class | 11,136 | 6.93257 | 0.50180 | 49.82% | 100.00% | 49.82% |
| post_split | all_features | previous_candle_direction | 11,136 | 7.00576 | 0.50709 | 49.29% | 100.00% | 49.29% |

`neutral_50_50`, `always_up`, `always_down`, `majority_class`, and `previous_candle_direction` signal on every row. The RSI rule uses neutral P(UP)=0.5 outside RSI<30 / RSI>70, so its signal coverage is intentionally lower.

## Selection-rule evidence

A classifier is eligible only when its pooled OOF log loss is lower than every specified baseline and it beats the best baseline in a strict majority of folds. If no classifier qualifies, the protocol's logistic-regression fallback is named without claiming an edge.

| Window | Recommendation | Basis |
|---|---|---|
| full_history | logistic_regression | lr_fallback |
| post_split | logistic_regression | lr_fallback |

The provisional full-history recommendation has lower pooled log loss by `0.00169` than the post-split recommendation. This small development-only difference does not itself adopt a training window; the coverage discontinuity remains an owner decision before Phase 4.

| Window | Classifier | Beats every baseline pooled? | Fold wins / folds | Eligible? |
|---|---|---:|---:|---:|
| full_history | logistic_regression | False | 8/22 | False |
| full_history | random_forest | False | 9/22 | False |
| full_history | hist_gradient_boosting | False | 1/22 | False |
| post_split | logistic_regression | False | 0/8 | False |
| post_split | random_forest | False | 1/8 | False |
| post_split | hist_gradient_boosting | False | 0/8 | False |

## Feature-family ablations

Ablations rerun the window's provisional recommendation after removing one causal feature family. They are diagnostics only, not a license to change the approved feature schema after model freeze.

| Window | Feature set | Method | OOF rows | Log loss | Brier | Accuracy | Signal coverage | Signal accuracy |
|---|---|---|---:|---:|---:|---:|---:|---:|
| full_history | without_trend_and_momentum | logistic_regression | 22,193 | 0.69378 | 0.25031 | 50.44% | 100.00% | 50.44% |
| full_history | without_return_and_risk | logistic_regression | 22,193 | 0.69380 | 0.25032 | 50.16% | 100.00% | 50.16% |
| full_history | without_activity_and_time | logistic_regression | 22,193 | 0.69380 | 0.25032 | 50.56% | 100.00% | 50.56% |
| post_split | without_trend_and_momentum | logistic_regression | 11,136 | 0.69462 | 0.25071 | 49.66% | 100.00% | 49.66% |
| post_split | without_return_and_risk | logistic_regression | 11,136 | 0.69487 | 0.25085 | 49.56% | 100.00% | 49.56% |
| post_split | without_activity_and_time | logistic_regression | 11,136 | 0.69555 | 0.25116 | 49.93% | 100.00% | 49.93% |

## Protocol notes

- HistGradientBoostingClassifier runs with `early_stopping=False`; it therefore does not create sklearn's internal random validation split.
- Logistic regression scales within each fold only. All labels, model fitting, thresholds, and selection remain chronological; no random split was used.
- The optional two-candle-horizon ablation was not run. It is not a candidate for the shipped next-candle target.
- These figures do not use calibration, threshold tuning, or the final holdout. Phase 4 performs those locked steps once a training window is approved.
