---
description: "Use when writing or modifying LLM training scripts, the Modelfile, dataset generation, fine-tuning configuration, or inference testing. Covers Alpaca format, LoRA params, dataset pipeline, and output contract."
applyTo: "llm_training/**"
---

# LLM Training Conventions

## Dataset Format — Alpaca Chat

All training examples must use the Alpaca instruction-following format:

```
<s>[INST] <<SYS>>
{system_prompt}
<</SYS>>

{user_message} [/INST] {assistant_response} </s>
```

- `system_prompt`: The trading system prompt from `Modelfile`.
- `user_message`: Indicator table or question.
- `assistant_response`: Valid JSON matching the output contract.
- Files: `llm_training/data/dataset/train.jsonl` (training), `llm_training/data/dataset/eval.jsonl` (evaluation).
- JSONL format: one JSON object per line with keys `"instruction"`, `"input"`, `"output"`.

## LLM Output Contract

Every training example's `"output"` must be valid JSON:

```json
{
  "action": "BUY|SELL|WAIT",
  "reason": "one sentence explanation",
  "confidence": 0,
  "suggested_sl": 0.0,
  "suggested_tp": 0.0
}
```

Never add extra fields to the output. Never format as prose. Confidence: 0–100 integer.

## Base Model & Fine-Tuning

- Base model: `unsloth/mistral-7b-v0.3-bnb-4bit` (~5 GB VRAM)
- Method: QLoRA 4-bit + LoRA adapters
- LoRA rank: 16 (`r=16`)
- LoRA alpha: 16
- Target modules: `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`
- Sequence length: 2048
- Batch size: 2, gradient accumulation: 4 (effective batch = 8)
- Learning rate: 2e-4, scheduler: cosine
- Steps: 2000 (up from 500 for larger datasets)
- Output: `llm_training/models/trading_llm/final/`

## Script Pipeline Order (Phase 5 Updated)

| Script | Input | Output | Examples Generated |
|--------|-------|--------|--------------------|
| `1_extract_pdfs.py` | `data/raw/books/*.pdf` | `data/processed/book_chunks.jsonl` | ~5,000 |
| `2_scrape_investopedia.py` | Web | `data/processed/investopedia_chunks.jsonl` | ~10,000 |
| `6_generate_historical_training.py` | TimescaleDB / yfinance | `data/processed/historical_train.jsonl` | ~76,000 |
| `7_generate_strategy_rules.py` | Strategy definitions | `data/processed/strategy_rules.jsonl` | ~10,250 |
| `3_prepare_dataset.py` | All processed chunks | `data/dataset/train.jsonl`, `eval.jsonl` | ~101,000 total |
| `4_finetune.py` | `data/dataset/train.jsonl` | `models/trading_llm/final/` | n/a |
| `5_inference_test.py` | Trained model | Interactive test or REST server | n/a |

Run scripts from `llm_training/` directory.

**Phase 5 additions:**
- Script 6 generates labeled market states from 20-year historical data across Nifty 50 symbols.
- Script 7 generates Q&A pairs from 4 strategy family definitions (TREND_FOLLOWING, MEAN_REVERSION, MOMENTUM, PRICE_ACTION).
- Script 4 now accepts `--steps` CLI argument (default 2000, up from 500).

## Dataset Size Targets (Phase 5 Final)

- Book chunks: ~5,000 examples
- Investopedia: ~10,000 examples
- Historical training (Phase 5): ~76,000 labeled market states (Nifty 50 symbols, 4 timeframes, 20 years)
- Strategy rules (Phase 5): ~10,250 Q&A pairs (4 strategies × multi-condition permutations)
- **Total: ~101,000 examples** (89.1% train, 10.9% eval)

## Ollama Modelfile (Phase 5 Enhanced)

Located at `llm_training/Modelfile`. System prompt includes:
- R:R rules: MIN_RR_RATIO = 2.0, standard SL/TP calculation (1.5×ATR / 3.0×ATR)
- Scenario confidence gate: Only trade when dominant scenario ≥ 60%
- 4 strategy families: TREND_FOLLOWING, MEAN_REVERSION, MOMENTUM, PRICE_ACTION
- 5 scenario types: BULLISH_BREAKOUT, BEARISH_BREAKDOWN, SIDEWAYS_CONSOLIDATION, REVERSAL_UP, REVERSAL_DOWN
- Multi-timeframe confluence: 1m, 15m, 1h, 1D
- Indian market hours: 09:15–15:30 IST
- Output JSON format (strict contract)
- Template: Mistral chat format `<s>[INST]...[/INST]...<s>`

After fine-tuning: `ollama create trading-llm -f llm_training/Modelfile`

## GPU Requirements

- Local fine-tuning: NVIDIA GPU with ≥ 6 GB VRAM + CUDA 11.8+
- No GPU available: Use Google Colab Free (T4, 16 GB VRAM) — upload `train.jsonl`, run `4_finetune.py`
- Inference only (Ollama): No GPU required — CPU inference supported
