# User guide

## Start the dashboard

1. Add Alpaca **paper** credentials to the local `.env` file. Never share them in chat or commit them.
2. Run `make serve` and open `http://127.0.0.1:8000` on this laptop.
3. Check the feed banner before reading any price or indicator. Only `LIVE-IEX` is the real-time IEX data path.

## Read the signal

- **UP** or **DOWN** is the frozen model's next-five-minute direction, with its calibrated probability shown as a percentage.
- **NO CLEAR SIGNAL** means the app deliberately withheld a direction. The row's reason may be thin data, an event session, feature warm-up, or a probability inside the model's frozen no-signal band. It is not a neutral prediction and should not be counted as a directional call.
- A prediction appears only after its five-minute candle is finalized. Its row is immutable. The outcome is attached later after the next same-session candle closes.
- A zero-minute filled candle has no prediction. Thin candles remain visible in the stored candle grid; a candle with fewer than three real minutes is gated out.
- A late prediction after an outage is labeled late in the export and excluded from on-time live scoring.

## Feed banners

| Banner | Meaning |
|---|---|
| `LIVE-IEX` | Connected to Alpaca's IEX stream. IEX is one exchange feed, not the consolidated market. |
| `STALE` | No recent bar arrived while regular market hours are open. Do not rely on the displayed signal until data resumes. |
| `DISCONNECTED` | Stream is reconnecting or unavailable. |
| `AUTH ERROR` | Local credentials or provider authorization failed. |
| `RATE LIMIT` | Provider rate-limited the connection/request. |
| `MARKET CLOSED` | Regular trading is closed; the last bar is historical. The dashboard shows the next open in ET and IST. |
| `TEST STREAM` | Synthetic Alpaca `FAKEPACA` plumbing data; never a real NFLX quote. |
| `REPLAY` | Historical recorded IEX bars; useful for a demo, not live data. |

The chart shows New York and India Standard Time. After the US daylight-saving transition on 1 Nov 2026, regular hours are 09:30-16:00 ET / 20:00-02:30 IST. TradingView can differ because its displayed source may be consolidated or use a different venue, adjustment, timestamp, or bar-finalization rule.

## When not to trust it

Do not treat the output as financial advice or an order instruction. Do not rely on it when the banner is not `LIVE-IEX`, when data-quality warnings appear, during outages, on event sessions, or when it says `NO CLEAR SIGNAL`. The current model did not beat a neutral probability benchmark in development and produced no confident calls in its final holdout; no live edge has been established. IEX-only bars may differ from consolidated prices.

The app is paper/data-only. It has no order submission function. `make replay` and `FEED_MODE=test` are demonstrations and must keep their explicit banners visible.
