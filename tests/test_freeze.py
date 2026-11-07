from __future__ import annotations

import pytest

from eval.freeze import FreezeError, freeze_model_once


def test_freeze_requires_explicit_owner_holdout_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ALLOW_HOLDOUT", raising=False)

    with pytest.raises(FreezeError, match="ALLOW_HOLDOUT=1"):
        freeze_model_once()
