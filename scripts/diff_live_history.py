"""Compare captured live IEX minute bars with next-morning IEX REST bars."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from nflx_indicator.config import load_settings  # noqa: E402
from nflx_indicator.history import fetch_bars  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data" / "live.sqlite")
    parser.add_argument("--start", required=True, help="first captured session date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="last captured session date (YYYY-MM-DD)")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs" / "live_vs_history.md")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error(f"live database not found: {args.database}")
    settings = load_settings()
    try:
        key_id, secret_key = settings.require_alpaca_credentials()
    except ValueError as exc:
        parser.error(str(exc))
    start = pd.Timestamp(args.start, tz="America/New_York").tz_convert("UTC")
    end = (pd.Timestamp(args.end, tz="America/New_York") + pd.Timedelta(days=1)).tz_convert("UTC")
    if end <= start:
        parser.error("--end must be on or after --start")
    from alpaca.data.historical import StockHistoricalDataClient

    client = StockHistoricalDataClient(key_id, secret_key)
    rest = fetch_bars(
        client,
        settings.symbol,
        start.to_pydatetime(),
        end.to_pydatetime(),
        settings.adjustment,
        feed="iex",
    )
    with sqlite3.connect(args.database) as connection:
        live = pd.read_sql_query(
            "SELECT timestamp, open, high, low, close, volume FROM bars_1m "
            "WHERE symbol = ? AND source = 'live_iex' AND timestamp >= ? AND timestamp < ? "
            "ORDER BY timestamp",
            connection,
            params=(settings.symbol, start.isoformat(), end.isoformat()),
        )
    if live.empty or rest.empty:
        parser.error("the selected interval has no captured live bars or no REST bars")
    live["timestamp"] = pd.to_datetime(live["timestamp"], utc=True)
    rest["timestamp"] = pd.to_datetime(rest["timestamp"], utc=True)
    columns = ["open", "high", "low", "close", "volume"]
    live = live.set_index("timestamp").sort_index()
    rest = rest.set_index("timestamp").sort_index()
    common = live.index.intersection(rest.index)
    compared = live.loc[common, columns].astype(float)
    reference = rest.loc[common, columns].astype(float)
    exact = compared.eq(reference)
    mismatched_rows = ~exact.all(axis=1)
    only_live = live.index.difference(rest.index)
    only_rest = rest.index.difference(live.index)
    retrieved = datetime.now(UTC).isoformat()
    examples = []
    for timestamp in common[mismatched_rows][:10]:
        examples.append(
            f"| {timestamp.isoformat()} | {compared.loc[timestamp, 'close']:.6f} | "
            f"{reference.loc[timestamp, 'close']:.6f} |"
        )
    report = [
        "# Live IEX versus next-morning REST parity",
        "",
        f"- Retrieved REST comparison: `{retrieved}`",
        f"- Symbol/feed: `{settings.symbol}` / `iex`",
        f"- Requested session interval: `{args.start}` through `{args.end}`",
        f"- Captured live rows: {len(live)}; REST rows: {len(rest)}; "
        f"common timestamps: {len(common)}",
        f"- Timestamps only in live capture: {len(only_live)}; only in REST: {len(only_rest)}",
        f"- Common timestamp rows with any OHLCV difference: {int(mismatched_rows.sum())}",
        "",
        "This compares provider records only. REST rows are fetched for this diagnostic and "
        "are not saved, trained on, or sent to the UI.",
        "",
        "## Close-difference examples",
        "",
        "| Timestamp (UTC) | Live close | REST close |",
        "|---|---:|---:|",
        *(examples or ["| none | — | — |"]),
        "",
        "## Mismatch counts by field",
        "",
        "| Field | Different common rows |",
        "|---|---:|",
        *(f"| {column} | {int((~exact[column]).sum())} |" for column in columns),
        "",
    ]
    output = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(report))
    print(
        f"Compared {len(common)} common bars; {int(mismatched_rows.sum())} rows differ; "
        f"wrote {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
