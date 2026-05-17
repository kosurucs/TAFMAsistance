---
description: "Add a new LLM training data source to the pipeline: scaffold a new data collection script, integrate it into the dataset merge, and regenerate training data."
---

Add a new LLM training data source: `${input:sourceName}`.

## Steps

### 1. Create the Data Collection Script

Create `llm_training/scripts/${input:scriptNumber}_${input:sourceName|snake}.py`:

The script should:
- Collect raw text data from the source
- Chunk text into 600–1000 character segments
- Save to `llm_training/data/processed/${input:sourceName}_chunks.jsonl`
- Format: one JSON per line with keys `"text"`, `"source"`, `"url"` (optional)
- Add rate limiting if scraping (minimum 1.5s between requests)
- Skip already-downloaded content (idempotent — safe to re-run)

### 2. Update the Dataset Merge

Open `llm_training/scripts/3_prepare_dataset.py`:

- Add the new source file path to the `SOURCE_FILES` list:
  ```python
  SOURCE_FILES = [
      "data/processed/book_chunks.jsonl",
      "data/processed/investopedia_chunks.jsonl",
      "data/processed/historical_train.jsonl",   # Phase 5
      "data/processed/strategy_rules.jsonl",      # Phase 5
      "data/processed/${input:sourceName}_chunks.jsonl",  # new
  ]
  ```
- Ensure the new source's chunks match the expected format (`{"text": "..."}` minimum).

### 3. Regenerate the Dataset

```bash
cd llm_training
python scripts/${input:scriptNumber}_${input:sourceName|snake}.py
python scripts/3_prepare_dataset.py
```

Verify the output:
- `data/dataset/train.jsonl` line count has increased
- `data/dataset/eval.jsonl` line count has increased
- Run: `python -c "import json; [json.loads(l) for l in open('data/dataset/train.jsonl')]"` — no JSON errors

### 4. Update Training

If the new source adds > 5,000 examples, consider increasing `--steps` in `4_finetune.py` by 200 per additional 5,000 examples (up to a max of 3,000 steps).

### 5. Sync Docs

After completing, run the `doc-sync` agent to update `llm-training.instructions.md`:
- Add the new script to the Script Pipeline Order table
- Update the Dataset Size Targets section

## Validation

- New script runs without errors: `python scripts/${input:scriptNumber}_${input:sourceName|snake}.py`
- New source file is non-empty: check line count
- Merged dataset includes examples from the new source (grep for source identifier)
- All `train.jsonl` examples validate as proper Alpaca format JSON
