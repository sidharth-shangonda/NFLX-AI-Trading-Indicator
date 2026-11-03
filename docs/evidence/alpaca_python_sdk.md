# Alpaca Python SDK

- Source URL: https://alpaca.markets/sdks/python/
- Retrieval date: 2026-11-03.
- Library version: alpaca-py 0.44.0 (see `versions.md`).
- Note: The installed 0.44.0 source auto-paginates `get_stock_bars` through `next_page_token` with a 10,000-row page size when no total `limit` is supplied. `StockDataStream.run()` calls `asyncio.run`; run it in a dedicated thread/process rather than inside FastAPI's running event loop. The request and stream classes used by the project are present in this pinned SDK.
