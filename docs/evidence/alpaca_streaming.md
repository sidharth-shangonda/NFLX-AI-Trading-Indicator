# Alpaca streaming behavior

- Source URLs: https://docs.alpaca.markets/us/docs/streaming-market-data ; https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data
- Retrieval date: 2026-11-03.
- Documentation version: current online documentation, version not stated.
- Note: The stock stream sends `bars` after minute marks and `updatedBars` after half-minute marks for late trades; bars include pre/post-market trades. The test endpoint `/v2/test` with `FAKEPACA` is available outside market hours and synthetic. Alpaca says most subscriptions have a one-connection limit; stream errors include 402 authentication, 405 symbol limit, and 406 connection limit.
