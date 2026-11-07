VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(PYTHON) -m pip
RUFF := $(VENV)/bin/ruff
PYTEST := $(PYTHON) -m pytest

.PHONY: setup test lint check-alpaca data data-freeze verify-data train freeze-model serve replay score diff-live

setup:
	python3 -m venv $(VENV)
	$(PIP) install --disable-pip-version-check --requirement requirements.lock

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTEST) -p no:cacheprovider

lint:
	$(RUFF) check --no-cache src tests scripts

check-alpaca:
	$(PYTHON) scripts/check_alpaca.py

data:
	$(PYTHON) src/data/pull_history.py

data-freeze:
	$(PYTHON) src/data/pull_history.py --freeze-initial

verify-data:
	$(PYTHON) src/data/pull_history.py --verify-phase1

train:
	$(PYTHON) scripts/train.py

freeze-model:
	$(PYTHON) scripts/freeze_model.py

serve:
	$(VENV)/bin/uvicorn live.app:app --app-dir src --host 127.0.0.1 --port 8000

replay:
	FEED_MODE=replay $(VENV)/bin/uvicorn live.app:app --app-dir src --host 127.0.0.1 --port 8000

score:
	$(PYTHON) scripts/score.py

diff-live:
	$(PYTHON) scripts/diff_live_history.py $(ARGS)
