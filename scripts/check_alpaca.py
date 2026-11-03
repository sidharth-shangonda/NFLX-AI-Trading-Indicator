"""Check paper credentials and fetch up to ten recent NFLX IEX minute bars."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alpaca.data.enums import Adjustment, DataFeed  # noqa: E402
from alpaca.data.historical import StockHistoricalDataClient  # noqa: E402
from alpaca.data.requests import StockBarsRequest  # noqa: E402
from alpaca.data.timeframe import TimeFrame  # noqa: E402

from nflx_indicator.config import ConfigurationError, load_settings  # noqa: E402


def main() -> int:
    try:
        settings = load_settings()
        key_id, secret_key = settings.require_alpaca_credentials()
    except ConfigurationError:
        print("ERROR missing_credentials: add paper keys to .env", file=sys.stderr)
        return 2

    try:
        client = StockHistoricalDataClient(key_id, secret_key)
        request = StockBarsRequest(
            symbol_or_symbols=settings.symbol,
            timeframe=TimeFrame.Minute,
            limit=10,
            feed=DataFeed.IEX,
            adjustment=Adjustment.SPLIT,
        )
        response = client.get_stock_bars(request)
        bar_count = len(response.df)
    except Exception:
        print("ERROR request_failed: check paper credentials and network", file=sys.stderr)
        return 1

    if bar_count == 0:
        print("ERROR bar_count=0: no bars returned", file=sys.stderr)
        return 1
    print(f"OK bar_count={bar_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
