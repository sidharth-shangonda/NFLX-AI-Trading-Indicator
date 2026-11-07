# Phase 2 candle, label, and feature contract

Frozen snapshot: `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9`.

`data.candles.build_regular_session_candles` is the one shared five-minute builder. It uses the NYSE regular-session grid, aggregates OHLCV from real one-minute bars only, records `n_minutes`, and creates an `is_filled` candle only where no real minute bar exists. A fill carries the prior grid close with zero volume. It drops empty candles only before the first available close in the whole dataset. The builder emits a gate reason when `n_minutes < 3`.

`labels.attach_next_candle_labels` creates an UP or DOWN target only where candle t meets the minute gate, the immediate next candle remains in the same NYSE session, that next candle has at least one real minute, and its return is nonzero. It records why a row cannot receive a target. Earnings event sessions come from the verified release facts in `config/events.yaml`, then use the first following NYSE trading session; they are excluded from predictions and training rows.

`features.add_causal_features` supplies the same feature schema to historical training and live finalization. Every feature uses data through the current finalized candle only. Leading rolling-window values remain missing instead of being filled from future rows.

## Snapshot validation on 2026-11-07

- Five-minute candles: 40,692.
- Filled candles: 2,857.
- Candles below `MIN_MINUTES=3`: 12,014.
- Exact-zero, same-session close-to-close returns ending at a non-filled candle: 1,076 / 37,313 (2.883713%).
- Technically label-eligible rows: 27,060; training-eligible rows after earnings-session exclusion: 26,448; rows with a complete feature vector: 40,487.

The full missing-minute, `n_minutes`, and zero-return breakdown remains in `docs/data_quality.md`.
