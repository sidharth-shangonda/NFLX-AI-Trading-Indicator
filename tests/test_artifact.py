from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from models.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactError,
    ModelArtifact,
    ProbabilityCalibrator,
    load_model_artifact,
    save_model_artifact,
)
from models.prediction import fit_classifier


def _artifact() -> ModelArtifact:
    features = pd.DataFrame({"a": [0.0, 1.0, 2.0, 3.0], "b": [1.0, 0.0, 1.0, 0.0]})
    estimator = fit_classifier(
        "logistic_regression", train_features=features, train_target=[0, 1, 1, 0], seed=1
    )
    calibrator = ProbabilityCalibrator.fit(
        estimator.predict_proba(features)[:, 1], np.array([0, 1, 1, 0])
    )
    return ModelArtifact(
        schema_version=ARTIFACT_SCHEMA_VERSION,
        model_version="model-v1",
        method="logistic_regression",
        estimator=estimator,
        calibrator=calibrator,
        feature_columns=("a", "b"),
        delta=0.05,
        snapshot_hash="snapshot",
        git_hash="git",
        trained_through_session="2026-01-01",
        calibration_sessions=("2026-01-02",),
        threshold_sessions=("2026-01-03",),
        production_window="post_split",
        fallback_reason="test",
    )


def test_artifact_round_trip_keeps_schema_and_predictions(tmp_path: Path) -> None:
    artifact = _artifact()
    path = tmp_path / "model.joblib"
    digest = save_model_artifact(artifact, path)
    restored = load_model_artifact(path)

    probability, direction = restored.predict_direction(pd.DataFrame({"a": [1.0], "b": [0.0]}))
    assert len(digest) == 64
    assert path.with_suffix(".joblib.sha256").read_text().strip() == digest
    assert 0.0 <= probability[0] <= 1.0
    assert direction[0] in {"UP", "DOWN", "NO_CLEAR_SIGNAL"}


def test_artifact_rejects_reordered_or_missing_features() -> None:
    with pytest.raises(ArtifactError, match="schema differs"):
        _artifact().predict_calibrated(pd.DataFrame({"b": [0.0], "a": [1.0]}))
