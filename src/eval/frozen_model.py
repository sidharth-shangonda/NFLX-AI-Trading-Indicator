"""Read-only verification for the already-trained production model.

The project keeps a single final evaluation separate from model development.
After that evaluation, the useful meaning of ``make train`` is not to refit a
different model: it is to prove that the saved model still matches its frozen
data snapshot and can accept the shared live feature schema.  This module does
exactly that, without loading labels or writing experiment results.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

from data.candles import build_regular_session_candles
from features import FEATURE_COLUMNS, add_causal_features
from models import ModelArtifact, load_model_artifact
from nflx_indicator.training_data import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SNAPSHOT_DIR,
    FrozenSnapshot,
    load_frozen_snapshot,
)

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH: Final = PROJECT_ROOT / "models" / "model-v1.joblib"
_SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


class FrozenModelVerificationError(RuntimeError):
    """Raised when a frozen model cannot be used safely with its source data."""


@dataclass(frozen=True)
class FrozenModelVerification:
    """Read-only evidence that the saved model is internally deployable."""

    model_version: str
    method: str
    artifact_hash: str
    snapshot_hash: str
    feature_count: int
    candle_count: int
    feature_ready_count: int
    up_count: int
    down_count: int
    no_clear_signal_count: int


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise FrozenModelVerificationError(f"cannot read model artifact: {path}") from exc


def verify_artifact_provenance(
    artifact_path: Path,
    *,
    expected_snapshot_hash: str,
    expected_feature_columns: tuple[str, ...] = FEATURE_COLUMNS,
) -> tuple[ModelArtifact, str]:
    """Check the artifact bytes, snapshot identity, and exact feature contract."""
    artifact_path = Path(artifact_path)
    sidecar_path = artifact_path.with_suffix(artifact_path.suffix + ".sha256")
    try:
        recorded_hash = sidecar_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise FrozenModelVerificationError(
            f"model checksum sidecar is unavailable: {sidecar_path}"
        ) from exc
    if not _SHA256_PATTERN.fullmatch(recorded_hash):
        raise FrozenModelVerificationError("model checksum sidecar is not a SHA-256 digest")

    actual_hash = _sha256(artifact_path)
    if actual_hash != recorded_hash:
        raise FrozenModelVerificationError("model artifact hash differs from its checksum sidecar")

    try:
        artifact = load_model_artifact(artifact_path)
    except Exception as exc:  # The artifact loader provides the specific unsafe-payload error.
        raise FrozenModelVerificationError(f"cannot load model artifact: {exc}") from exc
    if artifact.snapshot_hash != expected_snapshot_hash:
        raise FrozenModelVerificationError("model artifact snapshot hash differs from frozen data")
    if artifact.feature_columns != expected_feature_columns:
        raise FrozenModelVerificationError("model artifact feature schema differs from live schema")
    return artifact, actual_hash


def _feature_frame(snapshot: FrozenSnapshot):
    """Build inference inputs only; deliberately do not attach labels or outcomes."""
    candles = build_regular_session_candles(
        snapshot.bars,
        start=snapshot.manifest["request_start_utc"],
        end=snapshot.manifest["request_end_utc"],
    )
    return candles, add_causal_features(candles)


def verify_frozen_model(
    *,
    model_path: Path = DEFAULT_MODEL_PATH,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> FrozenModelVerification:
    """Verify production inference without retraining or inspecting test outcomes."""
    snapshot = load_frozen_snapshot(snapshot_dir=snapshot_dir, manifest_path=manifest_path)
    artifact, artifact_hash = verify_artifact_provenance(
        model_path,
        expected_snapshot_hash=snapshot.snapshot_hash,
    )
    candles, features = _feature_frame(snapshot)
    ready = features.loc[features["features_ready"].astype(bool), list(FEATURE_COLUMNS)]
    if ready.empty:
        raise FrozenModelVerificationError("frozen data produced no feature-ready inference rows")
    if not np.isfinite(ready.to_numpy(dtype=float)).all():
        raise FrozenModelVerificationError("feature-ready inference rows contain non-finite values")

    probabilities, directions = artifact.predict_direction(ready)
    invalid_probability = (
        not np.isfinite(probabilities).all()
        or ((probabilities < 0.0) | (probabilities > 1.0)).any()
    )
    if invalid_probability:
        raise FrozenModelVerificationError("model produced an invalid calibrated probability")
    counts = {name: int((directions == name).sum()) for name in ("UP", "DOWN", "NO_CLEAR_SIGNAL")}
    if sum(counts.values()) != len(ready):
        raise FrozenModelVerificationError("model produced an unknown direction label")

    return FrozenModelVerification(
        model_version=artifact.model_version,
        method=artifact.method,
        artifact_hash=artifact_hash,
        snapshot_hash=snapshot.snapshot_hash,
        feature_count=len(artifact.feature_columns),
        candle_count=len(candles),
        feature_ready_count=len(ready),
        up_count=counts["UP"],
        down_count=counts["DOWN"],
        no_clear_signal_count=counts["NO_CLEAR_SIGNAL"],
    )
