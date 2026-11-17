"""Score an existing local live/replay database; this script never trains a model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval.live_score import LiveScoreError, score_database  # noqa: E402

PROJECT_ROOT = ROOT


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Recorded indicator score",
        "",
        f"- Feed: {report['feed_label']}",
        f"- Database: `{report['database']}`",
        f"- Model: `{report.get('model', {}).get('model_version', 'unknown')}`",
        f"- Artifact SHA-256: `{report.get('model', {}).get('artifact_sha256', 'unknown')}`",
        f"- Snapshot hash: `{report.get('model', {}).get('snapshot_hash', 'unknown')}`",
        f"- Sessions: {report['start_session']} through {report['end_session']} "
        f"({report['sessions']})",
        f"- Matched on-time outcomes: {report['prediction_outcomes']}",
        f"- Excluded rows: {report['late_or_ineligible_rows_excluded']}",
        f"- Zero-return share (reported separately): {report['zero_return_share']:.4%}",
        f"- Recorded ERROR/CRITICAL events: {report['recorded_error_events']}",
        f"- Feed state transition severities: "
        f"`{json.dumps(report['recorded_feed_state_transitions'], sort_keys=True)}`",
        "",
        "This is a descriptive score of the selected local database. It does not retrain,",
        "calibrate, tune, or modify `model-v1`. Simulated P&L is separate from accuracy and",
        "uses the stated 0/1/2/3 bp per-side cost assumptions (two sides per completed horizon).",
        "Zero-return outcomes are excluded from binary metrics, as in training, but remain in",
        "the P&L calculation. Baselines use the same matched candle outcomes.",
        "",
        "## Metrics",
        "",
    ]
    for split, methods in report["metrics"].items():
        lines.extend([f"### {split.replace('_', ' ').title()}", ""])
        lines.append(
            "| Method | Rows | Signals | Coverage | Signal accuracy | Log loss | Brier | "
            "P&L bp @ 0 / 1 / 2 / 3 bp per side |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|")

        def fmt(value: float | None) -> str:
            return "—" if value is None else f"{value:.4f}"

        for name, metric in methods.items():
            pnl = metric.get("simulated_pnl_bp", {})
            pnl_text = " / ".join(
                "—"
                if pnl.get(str(cost), {}).get("total") is None
                else f"{pnl[str(cost)]['total']:.1f}"
                for cost in (0, 1, 2, 3)
            )
            lines.append(
                f"| {name} | {metric.get('observations', 0)} | {metric.get('signals', 0)} | "
                f"{fmt(metric.get('coverage'))} | {fmt(metric.get('signal_accuracy'))} | "
                f"{fmt(metric.get('log_loss'))} | {fmt(metric.get('brier'))} | {pnl_text} |"
            )
        lines.append("")
    lines.extend(["## Model calibration bins", ""])
    lines.append("| Slice | P(UP) bin | Rows | Mean predicted | Observed up rate |")
    lines.append("|---|---:|---:|---:|---:|")
    for split, bins in report["calibration_bins"].items():
        for row in bins:
            lines.append(
                f"| {split} | {row['bin']} ({row['lower']:.1f}-{row['upper']:.1f}) | "
                f"{row['count']} | {row['mean_predicted_probability']:.4f} | "
                f"{row['observed_up_rate']:.4f} |"
            )
    if not any(report["calibration_bins"].values()):
        lines.append("| no eligible calibrated rows | — | 0 | — | — |")
    lines.append("")
    lines.extend(
        [
            "## Notes",
            "",
            f"- Event sessions present: {', '.join(report['event_sessions_in_sample']) or 'none'}.",
            f"- Prediction reasons in matched rows: "
            f"`{json.dumps(report['prediction_reasons'], sort_keys=True)}`.",
            "- Live outage duration is not inferred from error-event counts; use the health "
            "and host logs for the soak report.",
            "- A REPLAY database is historical plumbing evidence, not a live evaluation.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data" / "replay.sqlite")
    parser.add_argument("--symbol", default="NFLX")
    parser.add_argument("--min-minutes", type=int, default=3)
    parser.add_argument("--delta", type=float, default=0.05)
    parser.add_argument("--output", type=Path, help="optional Markdown output path")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()
    try:
        report = score_database(
            args.database,
            symbol=args.symbol,
            min_minutes=args.min_minutes,
            delta=args.delta,
        )
    except (LiveScoreError, OSError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        markdown = _markdown(report)
        print(markdown, end="")
        if args.output:
            output_path = args.output
            if not output_path.is_absolute():
                output_path = PROJECT_ROOT / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown)
            print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
