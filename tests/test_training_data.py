from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nflx_indicator.history import sha256_file, snapshot_hash
from nflx_indicator.training_data import (
    TrainingDataError,
    load_frozen_snapshot,
    supervised_rows,
)


def _write_snapshot(tmp_path: Path) -> tuple[Path, Path]:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    parquet = snapshot_dir / "2026-01.parquet"
    pd.DataFrame(
        {
            "symbol": ["NFLX"],
            "timestamp": [pd.Timestamp("2026-01-05T14:30:00Z")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10.0],
            "trade_count": [1],
            "vwap": [100.2],
        }
    ).to_parquet(parquet, index=False)
    entry = {"path": "2026-01.parquet", "sha256": sha256_file(parquet)}
    manifest = {
        "files": [entry],
        "snapshot_hash": snapshot_hash([entry]),
        "row_count": 1,
        "request_start_utc": "2026-01-05T00:00:00+00:00",
        "request_end_utc": "2026-01-06T00:00:00+00:00",
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return snapshot_dir, manifest_path


def test_load_frozen_snapshot_requires_hash_verified_files(tmp_path: Path) -> None:
    snapshot_dir, manifest_path = _write_snapshot(tmp_path)

    snapshot = load_frozen_snapshot(snapshot_dir, manifest_path)

    assert len(snapshot.bars) == 1
    assert snapshot.snapshot_hash == snapshot.manifest["snapshot_hash"]

    (snapshot_dir / "2026-01.parquet").write_bytes(b"changed")
    with pytest.raises(TrainingDataError, match="hash differs"):
        load_frozen_snapshot(snapshot_dir, manifest_path)


def test_supervised_rows_filters_eligibility_and_compares_windows() -> None:
    frame = pd.DataFrame(
        {
            "candle_start": pd.to_datetime(
                ["2025-11-14T15:00:00Z", "2025-11-17T15:00:00Z", "2025-11-18T15:00:00Z"]
            ),
            "session_date": ["2025-11-14", "2025-11-17", "2025-11-18"],
            "training_eligible": [True, True, False],
            "features_ready": [True, True, True],
            "target_up": pd.Series([0, 1, pd.NA], dtype="Int64"),
        }
    )

    full = supervised_rows(frame, window="full_history")
    post_split = supervised_rows(frame, window="post_split")

    assert full["session_date"].tolist() == ["2025-11-14", "2025-11-17"]
    assert post_split["session_date"].tolist() == ["2025-11-17"]
