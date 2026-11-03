# NFLX AI Trading Indicator

Paper-only university ML project for a trained NFLX indicator. The application is planned for local laptop use and Alpaca's IEX market-data feed.

## Setup

```sh
make setup
```

Put your Alpaca **paper** credentials in the local, gitignored `.env` file using the names in `.env.example`. Never commit or share those values.

## Historical data snapshot

The first historical download is explicit and writes a frozen local snapshot under `data/snapshot/`:

```sh
make data-freeze
```

This fetches NFLX 1-minute bars from Alpaca using `feed=iex` and `adjustment=split`, and writes monthly parquet files, `data/manifest.json`, and a non-row manifest/hash record at `docs/data_manifest.json`. The `data/` directory is gitignored; no parquet data is committed. The snapshot content hash covers sorted relative file paths and file-content SHA-256 values, not retrieval time or provider metadata.

To check provider drift, `make data` downloads the same recorded interval to a temporary directory and reports row-count and file-hash differences. It does not replace the frozen snapshot. If the project has no local snapshot, create one with `make data-freeze`.

To rebuild after cloning, run `make setup`, add your paper keys to `.env`, then run `make data-freeze`. Historical data may change at the provider; record the resulting manifest and snapshot hash with any experiment. Ask before committing any parquet or other market-data files.

The current Alpaca data display/redistribution terms do not clearly settle a private university evaluator demo; see `docs/evidence/alpaca_data_display_terms.md`. Until clarified, keep the data local and expose no raw bars to third parties.

## Project status

See `docs/SPEC.md` and `docs/PLAN.md` for requirements, phase gates, and progress.
