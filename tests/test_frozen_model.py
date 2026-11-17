from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from eval.frozen_model import FrozenModelVerificationError, verify_artifact_provenance
from models.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    ModelArtifact,
    ProbabilityCalibrator,
    save_model_artifact,
)
from models.prediction import fit_classifier


def _artifact() -> ModelArtifact:
    features = pd.DataFrame({"a": [0.0, 1.0, 2.0, 3.0], "b": [1.0, 0.0, 1.0, 0.0]})
    estimator = fit_classifier(
        "logistic_regression", train_features=features, train_target=[0, 1, 1, 0], seed=1
    )
    return ModelArtifact(
        schema_version=ARTIFACT_SCHEMA_VERSION,
        model_version="test-v1",
        method="logistic_regression",
        estimator=estimator,
        calibrator=ProbabilityCalibrator.fit(
            estimator.predict_proba(features)[:, 1], np.array([0, 1, 1, 0])
        ),
        feature_columns=("a", "b"),
        delta=0.05,
        snapshot_hash="snapshot-hash",
        git_hash="git-hash",
        trained_through_session="2026-01-01",
        calibration_sessions=("2026-01-02",),
        threshold_sessions=("2026-01-03",),
        production_window="test",
        fallback_reason=None,
    )


def test_verification_checks_checksum_snapshot_and_feature_contract(tmp_path: Path) -> None:
    path = tmp_path / "model.joblib"
    digest = save_model_artifact(_artifact(), path)

    artifact, actual_hash = verify_artifact_provenance(
        path,
        expected_snapshot_hash="snapshot-hash",
        expected_feature_columns=("a", "b"),
    )

    assert artifact.model_version == "test-v1"
    assert actual_hash == digest


def test_verification_rejects_modified_artifact(tmp_path: Path) -> None:
    path = tmp_path / "model.joblib"
    save_model_artifact(_artifact(), path)
    path.write_bytes(b"modified")

    with pytest.raises(FrozenModelVerificationError, match="hash differs"):
        verify_artifact_provenance(
            path,
            expected_snapshot_hash="snapshot-hash",
            expected_feature_columns=("a", "b"),
        )


def test_verification_rejects_mismatched_snapshot_or_feature_contract(tmp_path: Path) -> None:
    path = tmp_path / "model.joblib"
    save_model_artifact(_artifact(), path)

    with pytest.raises(FrozenModelVerificationError, match="snapshot hash differs"):
        verify_artifact_provenance(
            path,
            expected_snapshot_hash="other-snapshot",
            expected_feature_columns=("a", "b"),
        )
    with pytest.raises(FrozenModelVerificationError, match="feature schema differs"):
        verify_artifact_provenance(
            path,
            expected_snapshot_hash="snapshot-hash",
            expected_feature_columns=("b", "a"),
        )
