from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from nflx_indicator.history import (
    build_manifest,
    compare_manifests,
    fetch_bars,
    normalize_bars,
    snapshot_hash,
    write_monthly_parquet,
)


def _bars() -> pd.DataFrame:
    return normalize_bars(
        [
            {
                "symbol": "NFLX",
                "timestamp": datetime(2025, 1, 31, 20, 59, tzinfo=UTC),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10,
                "trade_count": 3,
                "vwap": 100.2,
            },
            {
                "symbol": "NFLX",
                "timestamp": datetime(2025, 2, 3, 14, 30, tzinfo=UTC),
                "open": 100.5,
                "high": 102.0,
                "low": 100.0,
                "close": 101.5,
                "volume": 20,
                "trade_count": 5,
                "vwap": 101.2,
            },
        ]
    )


def test_snapshot_hash_uses_only_sorted_paths_and_content_hashes() -> None:
    first = [
        {"path": "2025-02.parquet", "rows": 2, "sha256": "b"},
        {"path": "2025-01.parquet", "rows": 1, "sha256": "a"},
    ]
    second = list(reversed(first))

    assert snapshot_hash(first) == snapshot_hash(second)


def test_manifest_metadata_is_excluded_from_snapshot_hash() -> None:
    frame = _bars()
    files = [
        {"path": "2025-01.parquet", "rows": 1, "sha256": "a"},
        {"path": "2025-02.parquet", "rows": 1, "sha256": "b"},
    ]
    request = {
        "symbol": "NFLX",
        "start": "2025-01-01T00:00:00+00:00",
        "end": "2025-03-01T00:00:00+00:00",
        "adjustment": "split",
    }
    first_time = datetime(2026, 11, 3, tzinfo=UTC)
    later_time = datetime(2026, 11, 4, tzinfo=UTC)

    first = build_manifest(files, frame, request, retrieved_at=first_time)
    later = build_manifest(files, frame, request, retrieved_at=later_time)

    assert first["snapshot_hash"] == later["snapshot_hash"]
    assert first["retrieved_at_utc"] != later["retrieved_at_utc"]


def test_monthly_parquet_is_byte_deterministic(tmp_path: Path) -> None:
    first_entries = write_monthly_parquet(_bars(), tmp_path / "first")
    second_entries = write_monthly_parquet(_bars(), tmp_path / "second")

    assert [entry["path"] for entry in first_entries] == [
        "2025-01.parquet",
        "2025-02.parquet",
    ]
    assert first_entries == second_entries


def test_compare_manifests_reports_drift_without_mutating_inputs() -> None:
    expected = {
        "row_count": 2,
        "snapshot_hash": "before",
        "files": [{"path": "2025-01.parquet", "rows": 2, "sha256": "old"}],
    }
    actual = {
        "row_count": 3,
        "snapshot_hash": "after",
        "files": [{"path": "2025-01.parquet", "rows": 3, "sha256": "new"}],
    }

    result = compare_manifests(expected, actual)

    assert result["row_count_changed"]
    assert result["snapshot_hash_changed"]
    assert result["changed_files"][0]["expected_rows"] == 2
    assert expected["files"][0]["sha256"] == "old"


def test_fetch_bars_attaches_requested_symbol_to_sdk_bars() -> None:
    from alpaca.data.enums import DataFeed

    class Bar:
        def model_dump(self) -> dict[str, object]:
            return {
                "timestamp": datetime(2025, 1, 2, 14, 30, tzinfo=UTC),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10,
                "trade_count": 3,
                "vwap": 100.2,
            }

    class Result:
        data = {"NFLX": [Bar()]}

    class Client:
        request = None

        def get_stock_bars(self, request_params: object) -> Result:
            self.request = request_params
            return Result()

    client = Client()
    bars = fetch_bars(
        client,
        "NFLX",
        datetime(2025, 1, 2, tzinfo=UTC),
        datetime(2025, 1, 3, tzinfo=UTC),
    )

    assert bars.loc[0, "symbol"] == "NFLX"
    assert bars.loc[0, "timestamp"] == pd.Timestamp("2025-01-02T14:30:00Z")
    assert client.request.feed == DataFeed.IEX

    fetch_bars(
        client,
        "NFLX",
        datetime(2025, 1, 2, tzinfo=UTC),
        datetime(2025, 1, 3, tzinfo=UTC),
        feed="sip",
    )
    assert client.request.feed == DataFeed.SIP
