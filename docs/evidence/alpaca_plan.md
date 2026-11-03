# Alpaca market-data plan

- Source URLs: https://docs.alpaca.markets/us/docs/about-market-data-api ; https://alpaca.markets/data
- Retrieval date: 2026-11-03.
- Documentation version: current online documentation, version not stated.
- Note: Alpaca's current page lists Basic as free with real-time IEX equities and historical coverage since 2016; its “latest 15 minutes” wording is clarified by the official Market Data FAQ: an historical SIP query whose `end` is at least 15 minutes old is allowed without a subscription, while latest SIP endpoints require one. A five-session historical SIP query also succeeded on this account on 2026-11-03; see `alpaca_sip_historical_access.md`. Algo Trader Plus is listed at $99/month with all-US-exchange coverage on the retrieval date. Plan details can change.
