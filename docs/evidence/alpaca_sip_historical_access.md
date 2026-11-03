# Historical SIP access diagnostic

- Source URLs: https://docs.alpaca.markets/us/docs/market-data-faq ; https://docs.alpaca.markets/us/docs/about-market-data-api ; https://docs.alpaca.markets/us/reference/stockbars
- Retrieval date: 2026-11-03.
- Library version: `alpaca-py` 0.44.0.
- Official FAQ says historical SIP requests are available without a subscription when `end` is at least 15 minutes old; latest SIP endpoints require a subscription. The plan page's “latest 15 minutes” wording is clarified by this historical-end rule.
- An authenticated historical query on this account succeeded for five sessions, 2026-10-26 through 2026-10-30, returning 4,205 one-minute SIP bars. On the 390 regular-session 5-minute candles with real bars in both feeds, IEX and SIP closes differed on 255 (65.38%); mean absolute close difference was 0.935 bp, median 0.794 bp, maximum 7.287 bp.
- This was a diagnostic comparison only. SIP rows were held in memory, not written to disk or committed, and are never used for training or the live path. Full aggregate diagnostics are in `docs/data_quality.md`.
