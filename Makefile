VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(PYTHON) -m pip
RUFF := $(VENV)/bin/ruff
PYTEST := $(PYTHON) -m pytest

.PHONY: setup test lint check-alpaca data data-freeze verify-data train serve replay score

setup:
	python3 -m venv $(VENV)
	$(PIP) install --disable-pip-version-check --requirement requirements.lock

test:
	$(PYTEST)

lint:
	$(RUFF) check src tests scripts

check-alpaca:
	$(PYTHON) scripts/check_alpaca.py

data:
	$(PYTHON) src/data/pull_history.py

data-freeze:
	$(PYTHON) src/data/pull_history.py --freeze-initial

verify-data:
	$(PYTHON) src/data/pull_history.py --verify-phase1

train:
	$(PYTHON) scripts/phase_gate.py --phase 3 --target train

serve:
	$(PYTHON) scripts/phase_gate.py --phase 5 --target serve

replay:
	$(PYTHON) scripts/phase_gate.py --phase 5 --target replay

score:
	$(PYTHON) scripts/phase_gate.py --phase 8 --target score
