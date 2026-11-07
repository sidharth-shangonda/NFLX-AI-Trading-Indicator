# Model card: model-v1

## Intended use

A paper-only, next-five-minute NFLX direction indicator using IEX data. It is not investment advice, broker software, or an order-execution system.

## Frozen artifact

- Artifact: `models/model-v1.joblib`, SHA-256 `8c10985bb689c3a3b6cbdb0597b117610d91659323d358a3036628f3be00c146`
- Snapshot: `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9`
- Code commit used for training: `b7808d2b97aa2af319c24a6eb759fb8ab61fb19b`
- Window: `post_split`; method: `logistic_regression`
- Trained through: `2026-06-09`
- Calibrator: `platt`; NO CLEAR SIGNAL band delta: `0.050`
- Fallback status: No Phase 3 candidate beat neutral_50_50 on pooled development log loss; logistic-regression fallback uses a 0.05 minimum no-signal band.

## Inputs and target

- Inputs: `return_1`, `return_3`, `return_12`, `realized_vol_12`, `range_mean_12`, `atr_14`, `ema_fast_distance`, `ema_slow_distance`, `rsi_14`, `macd`, `macd_signal`, `bollinger_position_20`, `bollinger_width_20`, `relative_volume_20`, `time_of_day_sin`, `time_of_day_cos`, `gap_from_previous_session`
- Target: sign of the next finalized five-minute IEX candle's close-to-close return.
- Predictions are gated when current `n_minutes < 3`, on configured event sessions, or during feature warm-up.

## Honest evaluation

- One locked holdout: `2026-09-22` through `2026-11-02`.
- Holdout probability log loss: `0.69325`; Brier: `0.25005`.
- Confident signals: **0/2,175** (0.00%)
- Confident-signal accuracy: **n/a**; Wilson lower bound: **0.00%**
- Balanced accuracy: n/a; MCC: n/a
- Confusion matrix: `{"true_down_pred_down": 0, "true_down_pred_up": 0, "true_up_pred_down": 0, "true_up_pred_up": 0}`
- Simulated P&L assumes a complete long/short entry and exit on every confident signal; results are not trading results:

## Limitations

- Phase 3 found no model that beat the neutral 50/50 probability benchmark in development. This artifact is a logistic-regression fallback with a wide no-signal band, not evidence of a profitable edge.
- Historical and live data are IEX-only, not consolidated-market data. Missing bars and thin IEX candles can suppress a signal.
- The holdout is one period only; the future live evaluation is required before claims about operational performance.
