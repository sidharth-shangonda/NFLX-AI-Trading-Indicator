# PLAN - phases (living document: tick boxes, log surprises and decisions at the bottom)

Rule: do ONE phase, run its acceptance checks, report, then STOP for my "go".

## Phase 0 - setup
Tasks: repo skeleton per AGENTS.md; pinned dependencies and lock; Makefile targets for setup/test/lint/data/train/serve/replay/score; .gitignore (.env, data/, models/*.bin as appropriate); .env.example (placeholders only); config module and `MIN_MINUTES=3` default; JSON logging; `docs/evidence/` notes and `docs/evidence/versions.md` with installed versions; scripts/check_alpaca.py (auth + fetch 10 NFLX bars feed=iex, print counts only). Tell me exactly how to create the Alpaca PAPER account and keys; I do that myself.
Accept (offline): `make test` and `make lint` green; config and JSON logging checks pass; `git grep -inE '^(APCA_API_KEY_ID|APCA_API_SECRET_KEY)='` shows only placeholder values in `.env.example` and no committed real credentials. The owner runs `python scripts/check_alpaca.py` after creating keys and adding them to `.env`; it must print `OK` and a bar count. Do not mark Phase 0 complete until the owner reports that run's printed counts.
- [ ] done

## Phase 1 - data + resolve UNVERIFIED items
Tasks: `src/data/pull_history.py` (1-min NFLX, feed=iex, adjustment=split, SDK pagination, >= 2 years or earliest available) -> temporary download and an explicitly frozen local snapshot of per-month parquet files plus a local manifest (params, retrieval time, provider metadata, per-file content SHA-256, deterministic snapshot hash). `make data-freeze` explicitly creates the initial snapshot; `make data` re-downloads the exact recorded interval to a temp directory, reports row-count/hash drift, and never overwrites the snapshot. Keep `data/` ignored and do not commit parquet files. Check official Alpaca data display/redistribution terms and record the result in `docs/evidence/`; if evaluator-display permission remains unclear, commit only a non-row manifest/hash record under `docs/` and include exact rebuild instructions in `README.md`. Ask before committing any data files. QC report `docs/data_quality.md` (date range, row/candle counts, missing minutes, duplicates, invalid OHLC, split handling, n_minutes distribution, below-3 share by month/split/time/weekday, non-filled zero-return rate, filled share, mean absolute return and volume by n_minutes, limitations); `docs/unverified_results.md` answers Phase 1 items a-d and f-h from SPEC section 2. Item e stays UNVERIFIED until Phase 7 has a live capture. Re-check every changeable claim in SPEC section 2 and update its evidence note. Optionally query five old SIP sessions for an IEX-close comparison; keep this diagnostic only and never save/use SIP rows for training or live.
Accept: snapshot hashes depend only on sorted file paths and file contents, not retrieval metadata; drift is reported without modifying the frozen snapshot; no ~10x price jump around 2025-11-14 to 2025-11-17; first regular bar timestamp check passes; requested historical missing-minute and candle diagnostics are written. If access fails: report a blocker and the setup fix, do NOT invent data. If more than 5% of regular-session 5-minute candles have fewer than 3 real minute bars, stop and ask before changing `MIN_MINUTES`.
- [x] done

## Phase 2 - candles, labels, features, leakage tests
Tasks: src/data/candles.py (shared 5-min builder), session filter via pandas_market_calendars NYSE, src/labels, src/features/features.py, config/events.yaml (verify earnings dates from ir.netflix.net).
Accept: `make test` includes no-look-ahead test, determinism test, DST (1 Nov 2026) + early-close tests, prior-session-close fills and leading-empty-drop tests, zero-return-rate report.
- [ ] done

## Phase 3 - baselines, models, walk-forward (dev data only)
Tasks: src/eval/walkforward.py (by trading day, 1-day gap, holdout guard + access log), baselines, LR, HGB (early_stopping=False), RF, feature-family ablations, optional h=2 ablation (validation only, not shipped), experiments/experiments.csv, plots, docs/results_dev.md.
Accept: `make train` runs end to end; holdout_access.log has ZERO entries; every trial in experiments.csv; selection rule applied as written.
- [ ] done

## Phase 4 - calibrate, set delta, ONE holdout run, freeze
Tasks: calibration on OOF; delta on OOF; single holdout evaluation (ALLOW_HOLDOUT=1) -> docs/results_holdout.md (never edited afterwards); model artifact + metadata (version, data hash, git hash, feature list, delta, calibrator) + docs/model_card.md; tag model-v1.
Accept: holdout_access.log has exactly one entry; artifact reproduces from a clean clone; results written honestly even if no model beats baselines.
- [ ] done

## Phase 5 - live backend
Tasks: ingestor (alpaca-py, handle event loop issue), 1-min store, candle builder, finalizer (35 s grace), inference, insert-only predictions + triggers, outcome evaluator, websocket + REST, REPLAY mode, test-stream mode, structured logs, clock-offset check.
Accept: all section-6 tests for these parts pass; run against the TEST stream and a REPLAY of recorded real data (each labeled); kill/restart and reconnect scenarios produce no duplicate predictions.
- [ ] done

## Phase 6 - frontend
Tasks: per SPEC section 5, including dual ET/IST times, all banner states demonstrable, attribution.
Accept: screenshots of each banner state; signal readable at a glance; export CSV works.
- [ ] done

## Phase 7 - soak and freeze
Tasks: run live paper mode >= 3 market days on the laptop (keep it awake; one stream connection only); diff live-recorded bars vs next-morning REST bars (this resolves UNVERIFIED item e only after a live capture exists); fix BUGS only, no model tuning; write host runbook (start, restart, rotate keys, what to do on outage); tag release-v1. Start the five-day live evaluation only after the soak and release freeze; schedule it to fit the submission window where possible.
Accept: diff report in docs/live_vs_history.md; zero repaint incidents; runbook tested by a cold restart; item e evidence recorded or remains explicitly UNVERIFIED if a valid live capture could not be obtained.
- [ ] done

## Phase 8 - docs and scoring
Tasks: README with reproduce-from-clean-clone steps; docs/traceability.md mapping R1-R9 to code/test/deliverable; report skeleton with citations and a "what did not work" section; user guide ("when NOT to trust it", IEX-vs-TradingView difference, no-signal meaning); demo checklist; `make score` script (baselines on same candles, calibration, outages, event-session split, simulated P&L reported separately).
Accept: fresh clone + `make setup && make test` works; `make score` runs on recorded data.
- [ ] done

## Optional (needs my approval): Phase 9 - scenarios (q20/q50/q80) and/or Finnhub emergency fallback adapter.

## Log (surprises, decisions, blockers)
(append as you go)

- 2026-11-03: User set the submission window to about two weeks (target around 2026-11-17; exact deadline not specified), chose the laptop for now, and will create the Alpaca Paper account and store keys in `.env`. Recommend starting the five-day no-change live evaluation only after Phase 7 soak and `release-v1` freeze; exact start date remains TBD until the implementation and soak pass.
- 2026-11-03: Reproducibility uses a frozen local per-month parquet snapshot; its deterministic hash excludes retrieval/provider metadata. `make data` compares a temp re-download and cannot silently overwrite the snapshot. Initial snapshot creation must be explicit.
- 2026-11-03: Candle gap rules use the regular-session grid, real-bar-only OHLCV, `n_minutes`, zero-minute filled candles, and `MIN_MINUTES=3`; report below-threshold frequency in Phase 1 and ask before changing the rule if it is frequent.
- 2026-11-03: Phase 0 offline checks can pass before credentials are available, but the phase checkbox stays open until the owner reports the authenticated check's printed counts.
- 2026-11-03: Evidence notes are short, link to sources, and record retrieval date plus source/library version (or say unversioned); Phase 1 rechecks changeable section 2 claims. Item e moved to Phase 7 and remains UNVERIFIED until live-vs-REST comparison.
- Open question before Phase 8: `data/` is ignored by Git per the project rules, so a frozen local parquet snapshot and manifest will not be available from a clean clone unless a sharing/archival policy is selected. Keep experiment snapshot hashes, but resolve how the actual snapshot is delivered before claiming clean-clone reproducibility.
- 2026-11-03: Phase 0 implementation created the initial Git repository because the project folder had no `.git`; offline test/lint acceptance is recorded at handoff. The authenticated Alpaca check remains owner-run and Phase 0 remains unchecked until its printed bar count is reported.
- 2026-11-03: User decided that zero-minute candles carry forward the prior session's last close; only leading empty candles at the beginning of the dataset are dropped. Phase 1 must measure the share of regular-session 5-minute candles with fewer than 3 real minutes and stop if it exceeds 5%.
- 2026-11-03: User directed that parquet remains local/ignored pending official data-use review. Official Alpaca terms and support material do not clearly answer whether this private university evaluator display is permitted; keep the status UNVERIFIED, record only manifest/hashes, document rebuild steps, and ask before any data-file commit.
- 2026-11-03: Short-path planning for the 2026-11-17 target is required after Phase 1; do not skip leakage or non-repainting tests, and identify when Phase 5 can start to leave at least three market days for soak.
- 2026-11-03: GitHub origin was configured as `https://github.com/sidharth-shangonda/NFLX-AI-Trading-Indicator.git`. Parquet files remain ignored; no push has been made.
- 2026-11-03: Phase 1 source re-check updated `docs/evidence/` and corrected stale price/IEX-share/provider claims in SPEC. Alpaca's evaluator-display terms remain UNVERIFIED: the current Terms require advance notice before making content available through a user application, and linked exchange agreements could not be fetched (403); no parquet will be committed.
- 2026-11-03: First `make data-freeze` attempt stopped before sending an API request because both Alpaca credentials were not available through local `.env`. No snapshot, data manifest, split check, timestamp observation, missing-minute count, or MIN_MINUTES rate was produced. Phase 1 remains unchecked until credentials are configured and the historical checks run; never paste keys into chat.
- 2026-11-03: Phase 1 snapshot hashing, drift comparison, and historical QC code now have unit coverage. `make test` passes 15 tests and `make lint` passes; these checks do not substitute for the blocked API/data acceptance checks.
- 2026-11-03: Tightened the ignore rule to `/data/` after checking that the broad `data/` pattern also hid the source package `src/data/`. Root data snapshots remain ignored while downloader code is tracked.
- 2026-11-03: `make data-freeze` succeeded: 147,124 rows, returned range 2024-10-01 13:30 UTC through 2026-11-02 20:59 UTC, 26 monthly files, snapshot hash `b9895df89c65acbf77493fbc8abb4a6afaa24688b497c427c0511cd81a1e80a9`. `make data` re-fetch returned the same row count and snapshot hash; the frozen snapshot was not modified.
- 2026-11-03: Historical QC covered 524 complete NYSE sessions: 57,502/203,460 regular-session minutes missing (28.2621%); 12,014/40,692 5-minute candles had fewer than 3 real bars (29.5242%), exceeding the owner's 5% stop threshold. There were 2,857 zero-minute candles, 0 duplicate timestamps, 0 invalid OHLCV rows, and 0 off-grid regular timestamps. First bar on 2026-11-02 was 09:30 ET. Split check passed: pre-split adjusted/raw close factor 0.09999955, post-split factor 1.0, and adjusted Nov 17/Nov 14 close ratio 0.9919072. No MIN_MINUTES or other rule was changed; pause for owner decision.
- 2026-11-03: Because the below-3-minute share exceeds 5%, Phase 1 stops here pending the owner's instruction on whether to retain `MIN_MINUTES=3` and proceed with those candles excluded or to revisit the eligibility rule. No raw parquet was committed; display permission remains UNVERIFIED.
- 2026-11-03: Owner directed that `MIN_MINUTES` remain 3. The prediction gate uses only candle t (`n_minutes(t) >= MIN_MINUTES`); a label additionally requires only a real close in t+1 (`n_minutes(t+1) >= 1`). Gated-out candles remain stored, display `NO CLEAR SIGNAL (thin data)`, and log a reason. This clarification is recorded in SPEC section 3; the threshold itself is unchanged.
- 2026-11-03: Phase 1 diagnostics show below-3 share is concentrated before the 2025-11-17 split cutoff. Recommendation is post-cutoff-only primary training with a full-history comparison experiment, pending owner approval; this is not an adopted training decision. SIP historical access and the diagnostic-only close comparison are recorded in the Phase 1 report/evidence; no SIP rows are retained.
- 2026-11-03: Schedule proposal for a 2026-11-17 live-test start: Phase 2 Nov 4-5, Phase 3 Nov 6-8, Phase 4 Nov 9-10; begin Phase 5 implementation as soon as the candle/features interface stabilizes (target Nov 6), using labeled test/replay paths while model selection and calibration proceed. Finish Phase 4 freeze and Phase 5 acceptance by Nov 11; soak Nov 12, 13, and 16; run the five-day no-change evaluation Nov 17, 18, 19, 20, and 23. This requires overlapping Phase 5 implementation with Phases 3-4, so it is a proposal only; preserve each phase's checks, including leakage and non-repainting tests. If Nov 17 is the final submission deadline, a complete soak plus live evaluation cannot finish by then; the proposed evaluation ends Nov 23.
