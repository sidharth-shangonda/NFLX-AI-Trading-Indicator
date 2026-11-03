# Alpaca historical stock bars

- Source URLs: https://docs.alpaca.markets/us/reference/stockbars ; https://docs.alpaca.markets/us/docs/market-data-faq
- Retrieval date: 2026-11-03.
- Documentation version: current API reference, version not stated.
- Note: The stock-bars reference supports 1-minute requests, `feed=iex`, split adjustment, and up to 10,000 rows per page with continuation tokens. Alpaca's FAQ defines a minute timestamp as the interval's left edge and says a bar is omitted when no eligible trade updates prices; this documents aggregation behavior but cannot identify the cause of a particular historical gap.
