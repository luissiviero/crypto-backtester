<!-- Output of `python scripts/measure_storage.py` (build run, 2026-10-28; polars 2.1.0,
Python 3.12.3). Synthetic data, not real Binance candles: the owner's real-data check is
`python -m app.data download BTCUSDT 1m 2023-01-01 2023-12-31` then
`python scripts/measure_storage.py --from-cache BTCUSDT 1m`. -->
# Storage measurement (synthetic)

Source: synthetic 1m candles for 2023, random seed 20261028; 365 days, 525600 rows, the schema of `app.data.schema`.

| layout | zstd 3 | zstd 9 |
| --- | --- | --- |
| 365 daily files | 26.56 MiB | 26.17 MiB |
| one yearly file | 23.02 MiB | 21.81 MiB |
| daily vs yearly | +15.4% | +20.0% |

Reopen rule (spec § Storage measurement): daily files at zstd 3 are +15.4% against one yearly file, which is within the 20 % threshold.
