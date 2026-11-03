"""Download, freeze, or compare historical 1-minute NFLX IEX bars."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nflx_indicator.config import ConfigurationError, load_settings  # noqa: E402
from nflx_indicator.data_quality import (  # noqa: E402
    candle_diagnostics,
    compare_feed_candle_closes,
    regular_session_quality,
    split_adjustment_summary,
)
from nflx_indicator.history import (  # noqa: E402
    build_manifest,
    compare_manifests,
    fetch_bars,
    write_monthly_parquet,
)

DATA_DIR = ROOT / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshot"
LOCAL_MANIFEST = DATA_DIR / "manifest.json"
TRACKED_MANIFEST = ROOT / "docs" / "data_manifest.json"
QUALITY_REPORT = ROOT / "docs" / "data_quality.md"
UNVERIFIED_REPORT = ROOT / "docs" / "unverified_results.md"
DEFAULT_START = datetime(2024, 10, 1, tzinfo=UTC)
MIN_MINUTES = 3


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _client(settings: Any) -> Any:
    from alpaca.data.historical import StockHistoricalDataClient

    key_id, secret_key = settings.require_alpaca_credentials()
    return StockHistoricalDataClient(key_id, secret_key)


def _now_utc() -> datetime:
    return datetime.now(UTC).replace(second=0, microsecond=0)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _request(start: datetime, end: datetime, adjustment: str = "split") -> dict[str, str]:
    return {
        "symbol": "NFLX",
        "start": start.astimezone(UTC).isoformat(),
        "end": end.astimezone(UTC).isoformat(),
        "feed": "iex",
        "adjustment": adjustment,
        "timeframe": "1Min",
        "sort": "asc",
    }


def _manifest_from_frame(
    frame: pd.DataFrame, files: list[dict[str, Any]], request: dict[str, str]
) -> dict[str, Any]:
    return build_manifest(files, frame, request)


def _append_summary_table(
    lines: list[str], heading: str, label: str, summaries: dict[str, Any]
) -> None:
    lines.extend(
        [
            f"### {heading}",
            "",
            f"| {label} | Candles | Below 3 | Below-3 share |",
            "|---|---:|---:|---:|",
        ]
    )
    for key, summary in summaries.items():
        share = summary["below_min_minutes_share"]
        share_text = "n/a" if share is None else f"{share:.2%}"
        lines.append(
            f"| {key} | {summary['candles']:,} | "
            f"{summary['below_min_minutes']:,} | {share_text} |"
        )
    lines.append("")


def _append_candle_diagnostics(lines: list[str], diagnostics: dict[str, Any]) -> None:
    lines.extend(
        [
            "## Five-minute candle diagnostics",
            "",
            (
                f"Total grid candles: {diagnostics['candle_count']:,}; filled "
                f"(n=0): {diagnostics['filled_candles']:,} "
                f"({diagnostics['filled_share']:.2%})."
            ),
            "",
            "### n_minutes distribution",
            "",
            "| n_minutes | Candles | Share |",
            "|---:|---:|---:|",
        ]
    )
    for n_minutes, summary in diagnostics["n_minutes_distribution"].items():
        lines.append(
            f"| {n_minutes} | {summary['candles']:,} | {summary['share']:.2%} |"
        )
    lines.extend(
        [
            "",
            (
                "Zero-return rate: "
                f"{diagnostics['zero_return_pairs']:,}/"
                f"{diagnostics['nonfilled_close_to_close_pairs']:,} "
                f"same-session close-to-close observations ending at a non-filled candle "
                f"({diagnostics['zero_return_rate']:.2%})."
            ),
            "Returns are close-to-close, computed only within a session. The first "
            "candle of each session has no return observation.",
            "",
        ]
    )
    _append_summary_table(
        lines,
        "Below-3 share by month",
        "Session month",
        diagnostics["below_min_minutes_by_month"],
    )
    _append_summary_table(
        lines,
        "Before and after split cutoff",
        "Session period",
        diagnostics["below_min_minutes_by_split_period"],
    )
    _append_summary_table(
        lines,
        "Below-3 share by time of day",
        "ET candle-start bucket",
        diagnostics["below_min_minutes_by_time_bucket"],
    )
    _append_summary_table(
        lines,
        "Below-3 share by weekday",
        "Weekday",
        diagnostics["below_min_minutes_by_weekday"],
    )
    lines.extend(
        [
            "### Mean absolute close-to-close return and volume by n_minutes",
            "",
            (
                "| n_minutes | Candles | Return observations | Mean absolute "
                "return (%) | Mean IEX volume |"
            ),
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for n_minutes, summary in diagnostics["return_and_volume_by_n_minutes"].items():
        mean_return = summary["mean_absolute_return_pct"]
        return_text = "n/a" if mean_return is None else f"{mean_return:.5f}"
        mean_volume = summary["mean_volume"]
        volume_text = "n/a" if mean_volume is None else f"{mean_volume:,.2f}"
        lines.append(
            f"| {n_minutes} | {summary['candles']:,} | "
            f"{summary['return_observations']:,} | {return_text} | {volume_text} |"
        )
    lines.extend(
        [
            "",
            "Returns are assigned to the current candle's n_minutes and compare its "
            "close with the prior five-minute grid close. No overnight return is used; "
            "n=0 closes carry forward and have zero volume by construction.",
            "",
            "### Training-window observation (not adopted)",
            "",
            (
                "Below-3 sparsity was 12,014/21,966 candles (54.69%) before "
                "2025-11-17 and 0/18,726 (0.00%) on/after it. The post-cutoff "
                "sample contains 18,726 candles. This large coverage discontinuity "
                "supports considering post-cutoff-only training, with full-history "
                "training as a comparison experiment; it does not establish why "
                "IEX coverage changed. This is a recommendation only and requires "
                "owner approval before adopting a training window."
            ),
            "",
        ]
    )


def _append_sip_diagnostic(lines: list[str], diagnostic: dict[str, Any]) -> None:
    lines.extend(["## SIP feed comparison (diagnostic only)", ""])
    if diagnostic["status"] != "ACCESSIBLE":
        lines.append(
            f"Status: **{diagnostic['status']}**; "
            f"error type `{diagnostic.get('error_type')}`, "
            f"HTTP status `{diagnostic.get('http_status')}`, "
            f"API code `{diagnostic.get('api_code')}`. No SIP data used."
        )
        lines.append("")
        return

    lines.extend(
        [
            (
                f"Historical `feed=sip` access succeeded for "
                f"{diagnostic['start_utc']} through {diagnostic['end_utc']} "
                "(five complete sessions; older than 15 minutes)."
            ),
            (
                f"The sample returned {diagnostic['sip_rows']:,} 1-minute SIP rows. "
                "On shared regular-session grid candles with real bars in both feeds, "
                f"IEX and SIP closes differed in {diagnostic['different_close_count']:,}/"
                f"{diagnostic['both_real_candles']:,} candles "
                f"({diagnostic['different_close_share']:.2%})."
            ),
            (
                "Absolute close differences: mean "
                f"{diagnostic['mean_absolute_close_difference_bps']:.3f} bp, "
                f"median {diagnostic['median_absolute_close_difference_bps']:.3f} bp, "
                f"max {diagnostic['max_absolute_close_difference_bps']:.3f} bp."
            ),
            "This was an isolated diagnostic. SIP rows were not saved, committed, or "
            "used for training or the live path.",
            "",
        ]
    )


def _write_quality_report(
    manifest: dict[str, Any],
    quality: dict[str, Any],
    timestamp_status: str,
    split_summary: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
    sip_diagnostic: dict[str, Any] | None = None,
) -> None:
    percent_missing = quality["missing_minute_share"]
    percent_low = quality["candles_below_min_minutes_share"]
    missing_text = "UNAVAILABLE" if percent_missing is None else f"{percent_missing:.4%}"
    low_text = "UNAVAILABLE" if percent_low is None else f"{percent_low:.4%}"
    latest = quality["latest_complete_session"] or {}
    lines = [
        "# Historical data quality",
        "",
        f"Snapshot hash: `{manifest['snapshot_hash']}`",
        (
            f"Requested range (UTC): `{manifest['request_start_utc']}` "
            f"to `{manifest['request_end_utc']}`"
        ),
        (
            f"Returned timestamp range (UTC): `{manifest['first_timestamp_utc']}` "
            f"to `{manifest['last_timestamp_utc']}`"
        ),
        f"Total 1-minute rows: **{manifest['row_count']:,}**",
        (
            f"Files: **{len(manifest['files'])}** UTC calendar-month parquet files "
            "(local, ignored by Git)"
        ),
        "",
        "## Quality counts",
        "",
        f"- Complete NYSE sessions checked: {len(quality['complete_sessions']):,}",
        f"- Regular-session rows: {quality['regular_session_rows']:,}",
        f"- Pre/post-market or outside-session rows: {quality['extended_or_outside_rows']:,}",
        f"- Expected regular-session minute slots: {quality['expected_regular_minutes']:,}",
        (
            f"- Missing regular-session minute slots: "
            f"{quality['missing_regular_minutes']:,} ({missing_text})"
        ),
        f"- Duplicate timestamp rows: {quality['duplicate_timestamp_rows']:,}",
        f"- Invalid OHLCV rows: {quality['invalid_ohlc_rows']:,}",
        f"- Invalid timestamp rows: {quality['invalid_timestamp_rows']:,}",
        f"- Off-grid regular-session timestamps: {quality['off_grid_regular_timestamps']:,}",
        f"- Regular-session 5-minute grid candles: {quality['regular_session_5m_candles']:,}",
        (
            f"- Candles with fewer than {MIN_MINUTES} real minute bars: "
            f"{quality['candles_below_min_minutes']:,} ({low_text})"
        ),
        f"- MIN_MINUTES configured: {MIN_MINUTES} (unchanged)",
        f"- Zero-minute filled candles: {quality['candles_with_zero_minutes']:,}",
        "",
        "## Timestamp check",
        "",
        f"- Latest complete session first bar (ET): `{latest.get('first_bar_et')}`",
        f"- First bar equals that session's 09:30 ET open: `{latest.get('first_bar_at_open')}`",
        (
            f"- Convention assessment: **{timestamp_status}**. Alpaca documents "
            "minute timestamps as the interval's left edge; see "
            "`docs/evidence/alpaca_historical_bars.md`."
        ),
        "",
        "## Split-adjustment check",
        "",
    ]
    if split_summary is None:
        lines.append("Not yet checked; run `make verify-data` after the snapshot is frozen.")
    else:
        lines.extend(
            [
                f"- Status: **{split_summary.get('status', 'UNVERIFIED')}**",
                (
                    "- Pre-split adjusted/raw close factor: "
                    f"{split_summary.get('pre_split_adjusted_to_raw_close_factor')}"
                ),
                (
                    "- Post-split adjusted/raw close factor: "
                    f"{split_summary.get('post_split_adjusted_to_raw_close_factor')}"
                ),
                (
                    "- Adjusted Nov 17 / Nov 14 close ratio: "
                    f"{split_summary.get('split_adjusted_nov17_to_nov14_close_ratio')}"
                ),
                (f"- No approximately 10x jump: {split_summary.get('no_approximately_10x_jump')}"),
            ]
        )
    lines.extend(
        [
            "",
            (
                "Counts use complete NYSE regular sessions only. A missing minute means no "
                "returned bar occupied that slot."
            ),
            "This does not establish whether the cause was no eligible IEX trade or a data gap.",
            "",
            (
                "No parquet rows are committed. Rebuild steps are in `README.md`; the "
                "manifest and content hashes are in `docs/data_manifest.json`."
            ),
        ]
    )
    if diagnostics is not None:
        lines.extend([""])
        _append_candle_diagnostics(lines, diagnostics)
    if sip_diagnostic is not None:
        _append_sip_diagnostic(lines, sip_diagnostic)
    QUALITY_REPORT.write_text("\n".join(lines).rstrip() + "\n")


def _write_unverified_report(
    manifest: dict[str, Any],
    quality: dict[str, Any],
    split: dict[str, Any],
    timestamp_status: str,
    history_status: str,
) -> None:
    low_share = quality["candles_below_min_minutes_share"]
    low_share_text = "UNAVAILABLE" if low_share is None else f"{low_share:.4%}"
    split_status = split.get("status", "UNVERIFIED")
    split_detail = split.get("reason", "see split summary in data quality report and log")
    lines = [
        "# Phase 1 UNVERIFIED items",
        "",
        (
            "Checked on 2026-11-03 against the frozen snapshot "
            f"`{manifest['snapshot_hash']}` and official sources in `docs/evidence/`."
        ),
        "",
        "| Item | Status | Phase 1 evidence |",
        "|---|---|---|",
        (
            f"| a. Free IEX 1-minute history >= 2 years | {history_status} | "
            f"{manifest['row_count']:,} rows; `{manifest['first_timestamp_utc']}` "
            f"to `{manifest['last_timestamp_utc']}`. |"
        ),
        f"| b. Split adjustment applied | {split_status} | {split_detail}. |",
        (
            f"| c. Bar timestamp is interval start | {timestamp_status} | "
            "First regular bar: "
            f"`{(quality['latest_complete_session'] or {}).get('first_bar_et')}` ET; "
            "official docs describe the left-edge convention. |"
        ),
        (
            "| d. No eligible IEX trade may yield no bar | VERIFIED in docs; "
            f"historical gap share measured | {quality['missing_regular_minutes']:,} "
            f"missing minutes; below-3-minute candle share {low_share_text}. |"
        ),
        (
            "| e. Live-recorded bars equal next-day REST bars | UNVERIFIED — Phase 7 | "
            "No eligible live capture has been compared with next-day REST yet. |"
        ),
        (
            "| f. Evaluator display/redistribution permission | UNVERIFIED | "
            "The terms do not settle a private demo or derived signals. |"
        ),
        (
            "| g. StockDataStream inside FastAPI loop | VERIFIED: thread/process | "
            "Pinned `.run()` calls `asyncio.run`. |"
        ),
        (
            "| h. HGB early-stopping split | VERIFIED with condition | "
            "In sklearn 1.9.1, auto enables a random split above 10,000 samples; "
            "set `early_stopping=False`. |"
        ),
        "",
        "The 5% pause condition uses `candles_below_min_minutes_share`.",
        "The measured share exceeds 5%; the owner directed that MIN_MINUTES remain 3.",
        "The candle-t gate and t+1 label rule are recorded in SPEC section 3.",
    ]
    UNVERIFIED_REPORT.write_text("\n".join(lines) + "\n")


def freeze_initial(start: datetime, end: datetime) -> int:
    if SNAPSHOT_DIR.exists() or LOCAL_MANIFEST.exists() or TRACKED_MANIFEST.exists():
        print("BLOCKER snapshot_exists: refusing to overwrite an existing frozen snapshot")
        return 2
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    try:
        client = _client(settings)
    except ConfigurationError:
        print("BLOCKER missing_credentials: add paper keys to .env")
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix=".history-stage-", dir=DATA_DIR) as temp_name:
            stage_root = Path(temp_name)
            stage_snapshot = stage_root / "snapshot"
            frame = fetch_bars(client, settings.symbol, start, end, "split")
            files = write_monthly_parquet(frame, stage_snapshot)
            request = _request(start, end, "split")
            manifest = _manifest_from_frame(frame, files, request)
            quality = regular_session_quality(
                frame, pd.Timestamp(start), pd.Timestamp(end), MIN_MINUTES
            )
            _write_json(stage_root / "manifest.json", manifest)
            if SNAPSHOT_DIR.exists() or LOCAL_MANIFEST.exists() or TRACKED_MANIFEST.exists():
                print("BLOCKER snapshot_exists: refusing to overwrite an existing frozen snapshot")
                return 2
            os.replace(stage_snapshot, SNAPSHOT_DIR)
            _write_json(LOCAL_MANIFEST, manifest)
            _write_json(TRACKED_MANIFEST, manifest)
            timestamp_status = (
                "VERIFIED"
                if (quality["latest_complete_session"] or {}).get("first_bar_at_open")
                else "UNVERIFIED"
            )
            _write_quality_report(manifest, quality, timestamp_status)
            print(
                "SNAPSHOT_CREATED "
                f"rows={manifest['row_count']} files={len(files)} "
                f"first={manifest['first_timestamp_utc']} last={manifest['last_timestamp_utc']} "
                f"snapshot_hash={manifest['snapshot_hash']}"
            )
            print(
                "MIN_MINUTES "
                f"below_3={quality['candles_below_min_minutes']} "
                f"grid_candles={quality['regular_session_5m_candles']} "
                f"share={quality['candles_below_min_minutes_share']}"
            )
            return 0
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        suffix = f" status={status}" if status is not None else f" error_type={type(exc).__name__}"
        print(
            f"BLOCKER history_download_failed{suffix}; inspect account/feed entitlement and network"
        )
        return 1


def check_drift() -> int:
    if not LOCAL_MANIFEST.exists() or not SNAPSHOT_DIR.is_dir():
        print("BLOCKER no_frozen_snapshot: create one explicitly with make data-freeze")
        return 2
    expected = _read_json(LOCAL_MANIFEST)
    start = _parse_utc(expected["request_start_utc"])
    end = _parse_utc(expected["request_end_utc"])
    settings = load_settings()
    try:
        client = _client(settings)
    except ConfigurationError:
        print("BLOCKER missing_credentials: add paper keys to .env")
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix="nflx-history-drift-") as temp_name:
            temp_snapshot = Path(temp_name) / "snapshot"
            frame = fetch_bars(client, settings.symbol, start, end, "split")
            files = write_monthly_parquet(frame, temp_snapshot)
            actual = _manifest_from_frame(
                frame,
                files,
                _request(start, end, "split"),
            )
        comparison = compare_manifests(expected, actual)
        status = "UNCHANGED" if not comparison["snapshot_hash_changed"] else "DRIFT"
        print(
            f"{status} rows_expected={comparison['expected_row_count']} "
            f"rows_actual={comparison['actual_row_count']} "
            f"hash_expected={comparison['expected_snapshot_hash']} "
            f"hash_actual={comparison['actual_snapshot_hash']} "
            f"changed_files={len(comparison['changed_files'])}"
        )
        for item in comparison["changed_files"]:
            print(
                f"FILE_DRIFT path={item['path']} rows_expected={item['expected_rows']} "
                f"rows_actual={item['actual_rows']} sha_expected={item['expected_sha256']} "
                f"sha_actual={item['actual_sha256']}"
            )
        print("SNAPSHOT_UNMODIFIED")
        return 0
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        suffix = f" status={status}" if status is not None else f" error_type={type(exc).__name__}"
        print(f"BLOCKER drift_download_failed{suffix}; frozen snapshot was not modified")
        return 1


def verify_phase1() -> int:
    if not LOCAL_MANIFEST.exists() or not SNAPSHOT_DIR.is_dir():
        print("BLOCKER no_frozen_snapshot: create one explicitly with make data-freeze")
        return 2
    manifest = _read_json(LOCAL_MANIFEST)
    frame = pd.concat(
        [pd.read_parquet(path) for path in sorted(SNAPSHOT_DIR.glob("*.parquet"))],
        ignore_index=True,
    )
    start = _parse_utc(manifest["request_start_utc"])
    end = _parse_utc(manifest["request_end_utc"])
    quality = regular_session_quality(frame, pd.Timestamp(start), pd.Timestamp(end), MIN_MINUTES)
    latest = quality["latest_complete_session"] or {}
    timestamp_status = (
        "VERIFIED"
        if latest.get("first_bar_at_open")
        else "UNVERIFIED: first observed bar did not equal 09:30 ET"
    )
    duration = pd.Timestamp(manifest["last_timestamp_utc"]) - pd.Timestamp(
        manifest["first_timestamp_utc"]
    )
    history_status = (
        "PASS >= 2 years"
        if duration >= pd.Timedelta(days=730)
        else "UNVERIFIED: less than 2 years returned"
    )

    settings = load_settings()
    try:
        client = _client(settings)
    except ConfigurationError:
        print("BLOCKER missing_credentials: add paper keys to .env")
        return 2
    split_start = datetime(2025, 11, 14, tzinfo=UTC)
    split_end = datetime(2025, 11, 19, tzinfo=UTC)
    try:
        raw = fetch_bars(client, settings.symbol, split_start, split_end, "raw")
        adjusted = fetch_bars(client, settings.symbol, split_start, split_end, "split")
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        suffix = f" status={status}" if status is not None else f" error_type={type(exc).__name__}"
        print(f"BLOCKER split_check_failed{suffix}; snapshot is preserved")
        return 1

    split = split_adjustment_summary(raw, adjusted)
    diagnostics = candle_diagnostics(
        frame, pd.Timestamp(start), pd.Timestamp(end), MIN_MINUTES
    )

    # SIP is an isolated five-session diagnostic. Never persist its rows or feed it
    # into the frozen IEX snapshot, training, or live path.
    sip_start = datetime(2026, 10, 26, tzinfo=UTC)
    sip_end = datetime(2026, 10, 31, tzinfo=UTC)
    try:
        sip_frame = fetch_bars(
            client, settings.symbol, sip_start, sip_end, "split", feed="sip"
        )
        comparison = compare_feed_candle_closes(
            frame,
            sip_frame,
            pd.Timestamp(sip_start),
            pd.Timestamp(sip_end),
        )
        sip_diagnostic = {
            "status": "ACCESSIBLE" if len(sip_frame) else "EMPTY",
            "start_utc": sip_start.isoformat(),
            "end_utc": sip_end.isoformat(),
            "sip_rows": len(sip_frame),
            **comparison,
        }
    except Exception as exc:
        response = getattr(exc, "response", None)
        http_status = getattr(exc, "status_code", None) or getattr(
            response, "status_code", None
        )
        api_code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
        denied = http_status in (401, 403) or str(api_code).startswith("403")
        sip_diagnostic = {
            "status": "DENIED" if denied else "ERROR",
            "error_type": type(exc).__name__,
            "http_status": http_status,
            "api_code": api_code,
        }

    _write_quality_report(
        manifest, quality, timestamp_status, split, diagnostics, sip_diagnostic
    )
    _write_unverified_report(manifest, quality, split, timestamp_status, history_status)
    share = quality["candles_below_min_minutes_share"]
    print(
        "PHASE1_QC "
        f"rows={manifest['row_count']} "
        f"range={manifest['first_timestamp_utc']}..{manifest['last_timestamp_utc']} "
        f"missing={quality['missing_regular_minutes']}/{quality['expected_regular_minutes']} "
        f"below3={quality['candles_below_min_minutes']}/{quality['regular_session_5m_candles']} "
        f"share={share} time={timestamp_status} split={split['status']} "
        f"history={history_status} sip={sip_diagnostic['status']}"
    )
    if share is not None and share > 0.05:
        print("PAUSE threshold_share_over_5_percent: ask owner before changing any rule")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-initial", action="store_true")
    parser.add_argument("--verify-phase1", action="store_true")
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    if args.verify_phase1:
        return verify_phase1()
    if args.freeze_initial:
        start = _parse_utc(args.start)
        end = _parse_utc(args.end) if args.end else _now_utc()
        return freeze_initial(start, end)
    return check_drift()


if __name__ == "__main__":
    raise SystemExit(main())
