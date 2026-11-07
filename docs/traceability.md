# Requirement traceability

| Requirement | Implementation | Test / evidence | Delivery status |
|---|---|---|---|
| R1: trained model drives the indicator | `src/models/`, `scripts/train.py`, frozen `models/model-v1.joblib` | `tests/test_models.py`, `tests/test_artifact.py`, `docs/results_dev.md`, `docs/results_holdout.md`, `docs/model_card.md` | Implemented; model-v1 has no demonstrated edge over neutral 50/50. |
| R2: live-market updates | `src/live/adapter.py`, `src/live/service.py`, `src/live/app.py` | `tests/test_live_adapter.py`, test-stream connection logged in `docs/PLAN.md` | Plumbing implemented; three-market-day IEX soak is pending. |
| R3: direction, calibrated confidence, readable display | `ui/index.html`, `/api/predictions` | `tests/test_live_app.py`; UI uses no-signal for thin data, event sessions, warm-up, and uncertain probability | Implemented; screenshot acceptance remains pending. |
| R4: closed-candle predictions never repaint | insert-only `predictions` table and SQLite UPDATE/DELETE triggers in `src/live/store.py` | `tests/test_live_store.py`, `tests/test_live_service.py` | Implemented and locally tested. |
| R5: five-day evaluation and baselines | `scripts/score.py`, `src/eval/live_score.py`, `docs/runbook.md` | `tests/test_live_score.py`; `docs/live_vs_history.md` is generated after live capture | Evaluation protocol prepared; five-day test not started. |
| R6: live performance, model quality, usefulness, report/demo | `docs/results_holdout.md`, scoring report, `docs/user_guide.md`, `docs/demo_checklist.md` | holdout artifact and score script | Holdout reported; live score and demo still pending. |
| R7: reproducibility, evidence, citations | snapshot manifests, experiment logs, `docs/evidence/`, model metadata | snapshot hash and walk-forward/holdout artifacts | Rebuild instructions are documented; snapshot data stays local under current terms uncertainty. |
| R8: paper only, one asset | IEX data adapter and NFLX config; there is no order API or order table | source review and API tests | Implemented; app is data-only. |
| R9: repo, model, app, report, guide, demo | repository, `model-v1`, FastAPI dashboard, docs in this directory | acceptance checks in `docs/PLAN.md` | Core deliverables exist; live soak and visual demo evidence remain pending. |

## Evidence limitations

Historical replay, the Alpaca test stream, and a real live IEX soak have separate labels. No synthetic/test data may be represented as live. The model's holdout result produced zero confident signals, so the score and guide must not claim predictive skill. Alpaca's private evaluator-display permission remains UNVERIFIED in `docs/evidence/alpaca_data_display_terms.md`.
