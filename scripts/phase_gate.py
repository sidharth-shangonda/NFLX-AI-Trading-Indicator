"""Make targets reserved for later phases fail clearly until implemented."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, type=int)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    parser.exit(
        2,
        f"make {args.target}: implementation is scheduled for Phase {args.phase}; "
        "this target is not available yet.\n",
    )


if __name__ == "__main__":
    raise SystemExit(main())
