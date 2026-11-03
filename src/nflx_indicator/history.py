"""Historical bars, deterministic snapshot metadata, and drift comparisons."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

BAR_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
)


class DataUnavailableError(RuntimeError):
    """Raised when the provider returns no usable bars."""


def normalize_bars(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Return bars in a stable column and timestamp order without dropping duplicates."""
    rows = list(records)
    if not rows:
        raise DataUnavailableError("Alpaca returned no bars for the requested interval")

    frame = pd.DataFrame.from_records(rows)
    for column in BAR_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame.loc[:, BAR_COLUMNS].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    for column in ("open", "high", "low", "close", "volume", "trade_count", "vwap"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["symbol"] = frame["symbol"].astype("string")
    return frame.sort_values(["timestamp", "symbol"], kind="mergesort").reset_index(drop=True)


def fetch_bars(
    client: Any,
    symbol: str,
    start: datetime,
    end: datetime,
    adjustment: str = "split",
    feed: str = "iex",
) -> pd.DataFrame:
    """Fetch minute bars; SIP is reserved for the Phase 1 diagnostic only."""
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    feeds = {"iex": DataFeed.IEX, "sip": DataFeed.SIP}
    try:
        selected_feed = feeds[feed.lower()]
    except KeyError as exc:
        raise ValueError("feed must be iex or sip") from exc

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed=selected_feed,
        adjustment=Adjustment(adjustment),
        sort="asc",
    )
    result = client.get_stock_bars(request_params=request)
    records = [{**bar.model_dump(), "symbol": symbol} for bar in result.data.get(symbol, [])]
    return normalize_bars(records)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_monthly_parquet(frame: pd.DataFrame, directory: Path) -> list[dict[str, Any]]:
    """Write one parquet file per UTC calendar month and return content hashes."""
    if frame.empty:
        raise DataUnavailableError("cannot write an empty snapshot")
    directory.mkdir(parents=True, exist_ok=True)
    normalized = normalize_bars(frame.to_dict(orient="records"))
    normalized["_month"] = normalized["timestamp"].dt.strftime("%Y-%m")
    entries: list[dict[str, Any]] = []
    for month, month_frame in normalized.groupby("_month", sort=True):
        relative_path = f"{month}.parquet"
        target = directory / relative_path
        month_frame.drop(columns="_month").to_parquet(
            target,
            engine="pyarrow",
            compression="zstd",
            index=False,
            version="2.6",
        )
        entries.append(
            {
                "path": relative_path,
                "rows": len(month_frame),
                "sha256": sha256_file(target),
            }
        )
    return entries


def snapshot_hash(files: Iterable[dict[str, Any]]) -> str:
    """Hash only sorted relative paths and file-content hashes, never manifest metadata."""
    content_map = [
        {"path": str(item["path"]), "sha256": str(item["sha256"])}
        for item in sorted(files, key=lambda item: str(item["path"]))
    ]
    canonical = json.dumps(content_map, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def build_manifest(
    files: list[dict[str, Any]],
    frame: pd.DataFrame,
    request: dict[str, str],
    retrieved_at: datetime | None = None,
) -> dict[str, Any]:
    retrieval_time = retrieved_at or datetime.now(UTC)
    ordered_files = sorted(files, key=lambda item: str(item["path"]))
    return {
        "schema_version": 1,
        "symbol": request["symbol"],
        "timeframe": "1Min",
        "feed": "iex",
        "adjustment": request["adjustment"],
        "sort": "asc",
        "request_start_utc": request["start"],
        "request_end_utc": request["end"],
        "retrieved_at_utc": retrieval_time.astimezone(UTC).isoformat(),
        "provider": "Alpaca Markets StockHistoricalDataClient",
        "alpaca_py_version": _alpaca_py_version(),
        "row_count": int(len(frame)),
        "first_timestamp_utc": frame["timestamp"].min().isoformat(),
        "last_timestamp_utc": frame["timestamp"].max().isoformat(),
        "files": ordered_files,
        "snapshot_hash": snapshot_hash(ordered_files),
    }


def _alpaca_py_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("alpaca-py")
    except PackageNotFoundError:
        return "UNVERIFIED"


def compare_manifests(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected_files = {item["path"]: item for item in expected["files"]}
    actual_files = {item["path"]: item for item in actual["files"]}
    changed = []
    for path in sorted(expected_files.keys() | actual_files.keys()):
        old = expected_files.get(path)
        new = actual_files.get(path)
        if (
            old is None
            or new is None
            or old["sha256"] != new["sha256"]
            or old["rows"] != new["rows"]
        ):
            changed.append(
                {
                    "path": path,
                    "expected_rows": old["rows"] if old else None,
                    "actual_rows": new["rows"] if new else None,
                    "expected_sha256": old["sha256"] if old else None,
                    "actual_sha256": new["sha256"] if new else None,
                }
            )
    return {
        "row_count_changed": expected["row_count"] != actual["row_count"],
        "snapshot_hash_changed": expected["snapshot_hash"] != actual["snapshot_hash"],
        "expected_row_count": expected["row_count"],
        "actual_row_count": actual["row_count"],
        "expected_snapshot_hash": expected["snapshot_hash"],
        "actual_snapshot_hash": actual["snapshot_hash"],
        "changed_files": changed,
    }
