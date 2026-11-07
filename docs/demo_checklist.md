# Demo checklist

## Before the demo

- [ ] Run `make test` and `make lint`.
- [ ] Confirm `.env` has paper credentials locally and is not staged by Git.
- [ ] Confirm no other stream instance is running for this key.
- [ ] Start `make serve` during market hours and verify `/api/health` reports `LIVE-IEX` before presenting live mode.
- [ ] If market is closed, use `make replay` and keep the `REPLAY` banner visible. Do not call it live.
- [ ] Show `/api/model` metadata and explain the post-split training window and frozen artifact hash.
- [ ] Show a signal and its later outcome only if those rows exist; otherwise explain why the app says `NO CLEAR SIGNAL`.
- [ ] Download the prediction CSV and show `generated_late`, reason, and outcome columns.
- [ ] Explain that the model did not beat the neutral development benchmark and produced no confident signals on the holdout.
- [ ] Explain IEX-versus-consolidated-feed differences and the limitations in the user guide.
- [ ] Stop the app cleanly after the presentation.

## Evidence captures

Store genuine screenshots under `docs/evidence/screenshots/` with a note of the capture date and actual feed state. Capture TEST STREAM and REPLAY only from those modes. Capture LIVE-IEX, STALE, DISCONNECTED, AUTH ERROR, RATE LIMIT, and MARKET CLOSED only when each state is actually observed; never fabricate a live-looking banner for a screenshot. Screenshot acceptance is complete only when the relevant state captures exist and are labeled honestly.
