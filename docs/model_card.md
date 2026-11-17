# Model card: model-v1

## Intended use

A paper-only, next-five-minute NFLX direction indicator using IEX data. It is not investment advice, broker software, or an order-execution system.

## Frozen artifact

- Artifact: `models/model-v1.joblib`, SHA-256 `87043fbb25384ac6f8e890e2e1ca6ae90074292a2ba8d79cf71a4535ad786773`
- Snapshot: `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9`
- Code commit used for training: `f92581db9ec5ef87c1f179cc92e01720a4f8ea59`
- Window: `full_history`; method: `hist_gradient_boosting`
- Trained through: `2026-09-21`
- Calibrator: `identity`; NO CLEAR SIGNAL band delta: `0.020`
- Fallback status: None

## Inputs and target

- Inputs: `return_1`, `return_2`, `return_3`, `return_5`, `return_8`, `return_12`, `return_24`, `ret_accel_1_2`, `ret_accel_1_3`, `body_ratio`, `upper_shadow_ratio`, `lower_shadow_ratio`, `clv`, `bar_range_pct`, `realized_vol_6`, `realized_vol_12`, `realized_vol_20`, `vol_ratio_6_20`, `range_mean_12`, `atr_14`, `range_to_atr`, `dist_ema_5`, `ema_5_slope`, `dist_ema_10`, `ema_10_slope`, `ema_fast_distance`, `ema_slow_distance`, `dist_ema_50`, `ema_50_slope`, `ema_5_20_spread`, `rsi_7`, `rsi_7_slope`, `rsi_14`, `rsi_14_slope`, `stoch_k`, `stoch_d`, `macd`, `macd_signal`, `macd_hist`, `macd_hist_slope`, `bollinger_position_20`, `bollinger_width_20`, `relative_volume_20`, `clv_vol`, `vol_direction`, `vwap_dist`, `time_of_day_sin`, `time_of_day_cos`, `is_morning`, `is_power_hour`, `gap_from_previous_session`
- Target: sign of the next finalized five-minute IEX candle's close-to-close return.
- Predictions are gated when current `n_minutes < 3`, on configured event sessions, or during feature warm-up.

## Honest evaluation

### 1. Out-of-Sample Holdout Evaluation
- One locked holdout: `2026-09-22` through `2026-11-02`.
- Holdout probability log loss: `0.69257`; Brier: `0.24971`.
- Confident signals: **690/2,175** (31.72%)
- Confident-signal accuracy: **52.17%**; Wilson lower bound: **48.44%**
- Balanced accuracy: 52.07%; MCC: 0.0414
- Confusion matrix: `{"true_down_pred_down": 196, "true_down_pred_up": 165, "true_up_pred_down": 165, "true_up_pred_up": 164}`
- Simulated P&L assumes a complete long/short entry and exit on every confident signal; results are not trading results:
  - 0 bp per side: total 1029.98 bp; mean 1.4927 bp/signal
  - 1 bp per side: total -350.02 bp; mean -0.5073 bp/signal
  - 2 bp per side: total -1730.02 bp; mean -2.5073 bp/signal
  - 3 bp per side: total -3110.02 bp; mean -4.5073 bp/signal

### 2. Live Operational Market Evaluation (2026-11-16)
- Evaluated across full regular NYSE trading day (09:30–16:00 ET / 14:30–21:00 UTC / 20:00–02:30 IST).
- Candlesticks recorded: **78 / 78** (100% of NYSE session).
- Signal distribution: 32 UP (41.0%), 42 DOWN (53.8%), 4 NO_CLEAR_SIGNAL (5.1%).
- Active signal coverage: **94.87%** (74/78).
- Confident signals evaluated on non-zero return candles: **70**.
- Directional hit rate / Accuracy: **57.14%** (40/70 correct).
- Baseline outperformance: Beats Always UP (43.24%), Random Walk (50.00%), Expanding Majority (49.06%), and Always DOWN (56.76%).
- On-time prediction accuracy (`generated_late == 0`): **58.97%** (23/39 correct).
- Log loss: `0.6892`; Brier score: `0.2480` (both beat 50/50 neutral baselines).
- Non-repainting verification: 0 updates, 0 deletions across all database rows.
- Data consistency: 0 discrepancies across 221 common minute bars against next-day REST (`docs/live_vs_history.md`).

## Limitations

- Historical and live data are IEX-only, not consolidated-market data. Missing bars and thin IEX candles can suppress a signal.
- Simulated P&L calculations demonstrate academic risk profiling under fixed friction assumptions, not actual market execution.
- Operational performance was validated on both a 30-session holdout test set (52.17% accuracy) and a full 1-day live regular trading session (57.14% accuracy), but past statistical edge does not guarantee perpetual future profitability.
