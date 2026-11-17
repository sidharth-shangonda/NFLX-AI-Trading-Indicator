# NFLX AI Trading Indicator - report

## Objective and system

Describe the one-candle, five-minute next-direction task, paper-only scope, laptop setup, Alpaca IEX feed, and frozen model version/hash.

## Data and reproducibility

Record the frozen snapshot hash, coverage dates/rows, retrieval metadata, candle construction, missing-bar rates, split handling, timestamp convention, and provider-use limitations. Link to `docs/data_quality.md` and `docs/evidence/`.

## Methods and leakage controls

Describe the causal feature list, model, calibration, fixed threshold, walk-forward day blocks, one-day gap, holdout guard, and insert-only prediction storage. Cite the repository files and relevant official sources.

## Development and holdout results

Summarize `docs/results_dev.md` and `docs/results_holdout.md`; report log loss (0.69257 vs neutral 0.69315), Brier score (0.24971 vs neutral 0.25000), coverage (31.72%), confident-call accuracy (52.17%), Wilson lower bound (48.44%), and comparison against traditional rules and baselines. Do not retune based on the holdout.

## Live evaluation

State the exact 1-day market date (regular NYSE trading session: 09:30–16:00 ET = 78 candles per TA instruction), feed state, model/artifact hash, on-time prediction count, outcomes, confidence interval, event-session split, outage duration, parity check, and no-repaint audit. Link to the generated score and live-vs-history report. If no live period completed, say so plainly.

## Simulated P&L

Report separately from accuracy. State the assumed per-side cost (0/1/2/3 bp), entry/exit convention, sample size, and limitations. It is a simulation, not executed trading.

## What did not work

Record candidates that failed to beat the baseline, no-signal counts, data/coverage limitations, unresolved feed/display questions, and any unavailable live evidence.

## User guide and demo

Link to `docs/user_guide.md` and `docs/demo_checklist.md`; include only genuine screenshots with their true feed-state labels.
