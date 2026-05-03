# Historical market data

Place CSV or Parquet files here.

Expected naming convention (generated automatically by `DataPipeline`):
```
RELIANCE_minute_20240101.csv
INFY_minute_20240101.csv
```

Columns: `date, open, high, low, close, volume`

Training data for LLM fine-tuning:
```
training_data.jsonl
```
