# Requirement traceability

| Requirement | Implementation | Test / evidence | Delivery status |
|---|---|---|---|
| R1: trained model drives the indicator | `src/models/`, `scripts/train.py`, frozen `models/model-v1.joblib` | `tests/test_models.py`, `tests/test_artifact.py`, `docs/results_dev.md`, `docs/results_holdout.md`, `docs/model_card.md` | Implemented; `model-v1` (`HistGradientBoostingClassifier`) achieves 52.17% confident signal accuracy on holdout test data and 57.14% on live evaluation. |
| R2: live-market updates | `src/live/adapter.py`, `src/live/service.py`, `src/live/app.py` | `tests/test_live_adapter.py`, live session logged in `docs/PLAN.md` and `docs/results_live.md` | Implemented & verified; full 1-day live IEX market session executed with 78 candles and 74 live predictions. |
| R3: direction, calibrated confidence, readable display | `ui/index.html`, `/api/predictions` | `tests/test_live_app.py`; UI uses no-signal for thin data, event sessions, warm-up, and uncertain probability | Implemented; dashboard operational with dual ET/IST clocks, range cone, VWAP, EMA 9/21, HUD telemetry, and XAI box. |
| R4: closed-candle predictions never repaint | insert-only `predictions` table and SQLite UPDATE/DELETE triggers in `src/live/store.py` | `tests/test_live_store.py`, `tests/test_live_service.py`, `data/live.sqlite` | Implemented and verified via unit tests, replay test, and live trading session (0 repaints recorded). |
| R5: 1-day live evaluation and baselines | `scripts/score.py`, `src/eval/live_score.py`, `docs/runbook.md` | `tests/test_live_score.py`; `docs/live_vs_history.md`, `docs/results_live.md` | Implemented and evaluated; **57.14% directional accuracy** on 70 confident signals; 0 REST discrepancies. |
| R6: live performance, model quality, usefulness, report/demo | `docs/results_holdout.md`, `docs/results_live.md`, `docs/summary.md`, `docs/user_guide.md`, `docs/demo_checklist.md` | holdout artifact, score script, live database | Both holdout (52.17%) and live session (57.14%) reported and verified against all baselines. |
| R7: reproducibility, evidence, citations | snapshot manifests, experiment logs, `docs/evidence/`, model metadata | snapshot hash and walk-forward/holdout artifacts | Rebuild instructions documented; snapshot data verified via SHA-256. |
| R8: paper only, one asset | IEX data adapter and NFLX config; there is no order API or order table | source review and API tests | Implemented; app is strictly data-only / paper indicator. |
| R9: repo, model, app, report, guide, demo | repository, `model-v1`, FastAPI dashboard, docs in this directory | acceptance checks in `docs/PLAN.md` | Core deliverables built and passing (63/63 tests); 1-day live evaluation fully complete. |

## Evidence limitations

Historical replay, the Alpaca test stream, and a real live IEX soak have separate labels. No synthetic/test data may be represented as live. The model's holdout test achieved 52.17% accuracy across 690 confident signals (31.72% coverage), and the live operational session on 2026-11-16 achieved 57.14% directional accuracy across 70 confident signals (94.87% active coverage), outperforming all naive baselines. Alpaca's private evaluator-display permission remains documented in `docs/evidence/alpaca_data_display_terms.md`.
