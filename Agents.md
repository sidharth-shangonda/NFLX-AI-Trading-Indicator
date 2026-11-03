# AGENTS.md - NFLX AI Trading Indicator (university ML lab project)

Build a live web-app indicator for NASDAQ: NFLX, driven by a genuinely TRAINED ML model.
Owner: Sidharth (IIT Patna). Submission window: about two weeks from 3 Nov 2026 (target around 17 Nov; exact deadline TBD). Live test (5 US trading days, no changes allowed): schedule after Phase 7 soak and `release-v1` freeze; exact start TBD. App runs on: laptop.

Read first, in order: docs/SPEC.md (what and why), docs/PLAN.md (phases, acceptance checks, progress log). Keep both updated.

## Non-negotiable rules
1. Paper only. Never write order-execution or brokerage trading code.
2. A trained model must drive the indicator. A hand-written rule is never "the model".
3. No repainting: a final prediction row is never updated or deleted (DB trigger + tests).
4. No random train/test split, ever. Chronological walk-forward only. No future information in features, scaling, thresholds, tuning, calibration or model selection.
5. Never fabricate results, API behavior, sources or data. Unknown = mark UNVERIFIED and check official docs. If data access fails, report a blocker; do not invent data.
6. Never label delayed, synthetic or replayed data as live. The UI banner always shows the true feed state.
7. Secrets only in .env (gitignored). Never print, log or commit keys. Never ask me to paste keys in chat.
8. Small stack: Python, pandas, scikit-learn, FastAPI, SQLite, plain HTML/JS + Lightweight Charts. No Docker/Redis/Kafka/microservices without my approval.
9. Every experiment is reproducible: seeded, logged with git hash + data hash.
10. After the model-freeze tag, no model or threshold changes.
11. Ask before changing: prediction target, data provider, architecture, anything with cost.

## Workflow
- One phase at a time from docs/PLAN.md. Begin with a short plan (use Plan mode if available).
- End each phase with: what changed, commands run and their output, acceptance checks passed/failed, open questions. Then STOP and wait for my "go".
- Small commits. Tick the checklist in docs/PLAN.md. Record surprises and decisions in its log.
- If you make the same mistake twice, propose an AGENTS.md addition.

## Commands (create in Phase 0, keep them working)
make setup | make test | make lint | make data | make train | make serve | make replay | make score
Run `make test` and `make lint` before every handoff.

## Definition of done (any phase)
Code + tests pass + acceptance checks in PLAN.md met + docs updated + no secrets in the diff.
