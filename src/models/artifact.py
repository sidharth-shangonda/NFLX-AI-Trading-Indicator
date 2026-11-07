"""Versioned trained-model artifact with a strict shared feature schema."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

ARTIFACT_SCHEMA_VERSION: Final = 1


class ArtifactError(ValueError):
    """Raised when a saved artifact or inference frame is unsafe to use."""


@dataclass
class ProbabilityCalibrator:
    """Platt scaling learned only from the reserved calibration period."""

    estimator: LogisticRegression | None
    constant_probability: float | None = None

    @staticmethod
    def _logit(probabilities: np.ndarray) -> np.ndarray:
        clipped = np.clip(probabilities.astype(float), 1e-6, 1.0 - 1e-6)
        return np.log(clipped / (1.0 - clipped)).reshape(-1, 1)

    @classmethod
    def fit(cls, raw_probabilities: np.ndarray, target_up: np.ndarray) -> ProbabilityCalibrator:
        probabilities = np.asarray(raw_probabilities, dtype=float)
        target = np.asarray(target_up, dtype=int)
        if len(probabilities) != len(target) or not len(target):
            raise ArtifactError("calibrator inputs must be non-empty and aligned")
        if not np.isfinite(probabilities).all() or not np.isin(target, (0, 1)).all():
            raise ArtifactError("calibrator inputs are invalid")
        if np.unique(target).size < 2:
            return cls(estimator=None, constant_probability=float(target[0]))
        estimator = LogisticRegression(C=1.0, max_iter=1_000, random_state=20_261_107)
        estimator.fit(cls._logit(probabilities), target)
        return cls(estimator=estimator)

    def predict(self, raw_probabilities: np.ndarray) -> np.ndarray:
        probabilities = np.asarray(raw_probabilities, dtype=float)
        if probabilities.ndim != 1 or not np.isfinite(probabilities).all():
            raise ArtifactError("raw probabilities must be a finite vector")
        if self.estimator is None:
            if self.constant_probability is None:
                raise ArtifactError("calibrator has neither estimator nor constant")
            return np.full(len(probabilities), self.constant_probability, dtype=float)
        return self.estimator.predict_proba(self._logit(probabilities))[:, 1]


@dataclass
class ModelArtifact:
    """The exact trained model, calibrator, threshold, and provenance to deploy."""

    schema_version: int
    model_version: str
    method: str
    estimator: Any
    calibrator: ProbabilityCalibrator
    feature_columns: tuple[str, ...]
    delta: float
    snapshot_hash: str
    git_hash: str
    trained_through_session: str
    calibration_sessions: tuple[str, ...]
    threshold_sessions: tuple[str, ...]
    production_window: str
    fallback_reason: str | None

    def _features(self, frame: pd.DataFrame) -> pd.DataFrame:
        received = tuple(frame.columns)
        if received != self.feature_columns:
            raise ArtifactError(
                "model input schema differs; expected exactly "
                f"{self.feature_columns}, received {received}"
            )
        try:
            numeric = frame.astype(float)
        except (TypeError, ValueError) as exc:
            raise ArtifactError("model inputs must be numeric") from exc
        if not np.isfinite(numeric.to_numpy()).all():
            raise ArtifactError("model inputs contain missing or non-finite values")
        return numeric

    def predict_raw(self, frame: pd.DataFrame) -> np.ndarray:
        values = self._features(frame)
        return np.asarray(self.estimator.predict_proba(values)[:, 1], dtype=float)

    def predict_calibrated(self, frame: pd.DataFrame) -> np.ndarray:
        return self.calibrator.predict(self.predict_raw(frame))

    def predict_direction(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        probability = self.predict_calibrated(frame)
        direction = np.full(len(probability), "NO_CLEAR_SIGNAL", dtype=object)
        direction[probability >= 0.5 + self.delta] = "UP"
        direction[probability <= 0.5 - self.delta] = "DOWN"
        return probability, direction


def save_model_artifact(artifact: ModelArtifact, path: Path) -> str:
    """Persist a model deterministically enough to checksum its actual bytes."""
    if artifact.schema_version != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactError("unexpected artifact schema version")
    if not 0.0 <= artifact.delta < 0.5:
        raise ArtifactError("artifact delta must be between zero and 0.5")
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n")
    return digest


def load_model_artifact(path: Path) -> ModelArtifact:
    """Load a model artifact and reject malformed/non-project payloads."""
    try:
        artifact = joblib.load(path)
    except (OSError, ValueError, TypeError) as exc:
        raise ArtifactError(f"cannot load model artifact: {path}") from exc
    if not isinstance(artifact, ModelArtifact):
        raise ArtifactError("artifact has unexpected type")
    if artifact.schema_version != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactError("artifact schema version is unsupported")
    return artifact


def artifact_metadata(artifact: ModelArtifact, artifact_hash: str) -> dict[str, object]:
    """Return a JSON-safe, non-secret model card payload."""
    return {
        "artifact_schema_version": artifact.schema_version,
        "artifact_sha256": artifact_hash,
        "calibrator": "platt" if artifact.calibrator.estimator is not None else "constant",
        "delta": artifact.delta,
        "fallback_reason": artifact.fallback_reason,
        "feature_columns": list(artifact.feature_columns),
        "git_hash": artifact.git_hash,
        "method": artifact.method,
        "model_version": artifact.model_version,
        "production_window": artifact.production_window,
        "snapshot_hash": artifact.snapshot_hash,
        "threshold_sessions": list(artifact.threshold_sessions),
        "trained_through_session": artifact.trained_through_session,
        "calibration_sessions": list(artifact.calibration_sessions),
    }


def write_artifact_metadata(artifact: ModelArtifact, artifact_hash: str, path: Path) -> None:
    """Write the sidecar metadata used by API and human documentation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(artifact_metadata(artifact, artifact_hash), indent=2, sort_keys=True)
    path.write_text(payload + "\n")
