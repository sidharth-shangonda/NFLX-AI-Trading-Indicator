"""Load the frozen snapshot and build reproducible supervised training rows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd

from data.candles import build_regular_session_candles
from features import add_causal_features
from labels import attach_next_candle_labels
from nflx_indicator.events import configured_event_session_dates
from nflx_indicator.history import sha256_file, snapshot_hash

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT_DIR: Final = PROJECT_ROOT / "data" / "snapshot"
DEFAULT_MANIFEST_PATH: Final = PROJECT_ROOT / "data" / "manifest.json"
POST_SPLIT_START: Final = "2025-11-17"
TRAINING_WINDOWS: Final = ("full_history", "post_split")


class TrainingDataError(RuntimeError):
    """Raised when a frozen snapshot cannot safely become supervised data."""


@dataclass(frozen=True)
class FrozenSnapshot:
    """Verified local source data and its content-derived identity."""

    bars: pd.DataFrame
    manifest: dict[str, Any]
    snapshot_hash: str


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingDataError(f"cannot read frozen snapshot manifest: {path}") from exc
    if not isinstance(manifest, dict):
        raise TrainingDataError("frozen snapshot manifest must be a JSON object")
    required = {"files", "snapshot_hash", "row_count", "request_start_utc", "request_end_utc"}
    missing = required.difference(manifest)
    if missing:
        raise TrainingDataError(f"frozen snapshot manifest is missing: {sorted(missing)}")
    if not isinstance(manifest["files"], list) or not manifest["files"]:
        raise TrainingDataError("frozen snapshot manifest has no parquet files")
    return manifest


def _safe_snapshot_file(snapshot_dir: Path, relative_path: str) -> Path:
    candidate = snapshot_dir / relative_path
    try:
        candidate.resolve().relative_to(snapshot_dir.resolve())
    except ValueError as exc:
        message = f"snapshot file path escapes snapshot directory: {relative_path}"
        raise TrainingDataError(message) from exc
    return candidate


def load_frozen_snapshot(
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> FrozenSnapshot:
    """Read only a hash-verified, per-month frozen snapshot.

    This intentionally trusts neither a stale manifest nor changed parquet files:
    every expected file's content hash is checked before rows are loaded.  The
    retrieval metadata remains outside the returned content identity.
    """
    manifest = _read_manifest(manifest_path)
    actual_files: list[dict[str, Any]] = []
    parquet_paths: list[Path] = []
    for entry in sorted(manifest["files"], key=lambda item: str(item.get("path", ""))):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise TrainingDataError("each snapshot file entry needs a relative path")
        if not isinstance(entry.get("sha256"), str):
            raise TrainingDataError(f"snapshot file {entry['path']} has no sha256")
        target = _safe_snapshot_file(snapshot_dir, entry["path"])
        if not target.is_file():
            raise TrainingDataError(f"frozen snapshot file is missing: {target}")
        actual_hash = sha256_file(target)
        if actual_hash != entry["sha256"]:
            raise TrainingDataError(
                f"frozen snapshot file hash differs from manifest: {entry['path']}"
            )
        actual_files.append({"path": entry["path"], "sha256": actual_hash})
        parquet_paths.append(target)

    actual_snapshot_hash = snapshot_hash(actual_files)
    if actual_snapshot_hash != manifest["snapshot_hash"]:
        raise TrainingDataError("frozen snapshot content hash differs from manifest")

    bars = pd.concat([pd.read_parquet(path) for path in parquet_paths], ignore_index=True)
    if len(bars) != int(manifest["row_count"]):
        raise TrainingDataError("frozen snapshot row count differs from manifest")
    return FrozenSnapshot(
        bars=bars,
        manifest=manifest,
        snapshot_hash=actual_snapshot_hash,
    )


def build_labeled_feature_frame(snapshot: FrozenSnapshot) -> pd.DataFrame:
    """Build the single causal candle/label/feature view for all experiments."""
    candles = build_regular_session_candles(
        snapshot.bars,
        start=pd.Timestamp(snapshot.manifest["request_start_utc"]),
        end=pd.Timestamp(snapshot.manifest["request_end_utc"]),
    )
    labeled = attach_next_candle_labels(
        candles,
        event_session_dates=configured_event_session_dates(),
    )
    result = add_causal_features(labeled)
    if result.empty:
        raise TrainingDataError("frozen snapshot produced no regular-session candles")
    return result


def supervised_rows(frame: pd.DataFrame, *, window: str) -> pd.DataFrame:
    """Return chronological, eligible rows for one candidate training window.

    Both windows are deliberately supported so Phase 3 can compare them without
    silently making the pre/post-split policy decision.
    """
    if window not in TRAINING_WINDOWS:
        raise TrainingDataError(f"unknown training window: {window}")
    required = {"session_date", "training_eligible", "features_ready", "target_up"}
    missing = required.difference(frame.columns)
    if missing:
        raise TrainingDataError(f"feature frame is missing: {sorted(missing)}")
    rows = frame.loc[
        frame["training_eligible"].astype(bool)
        & frame["features_ready"].astype(bool)
        & frame["target_up"].notna()
    ].copy()
    rows["session_date"] = rows["session_date"].astype(str)
    if window == "post_split":
        rows = rows.loc[rows["session_date"] >= POST_SPLIT_START].copy()
    return rows.sort_values("candle_start", kind="mergesort").reset_index(drop=True)
