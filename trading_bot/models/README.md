# Model Weights

Place fine-tuned LoRA adapter weights in this directory.

Expected path (configurable via `LLM_MODEL_PATH` in `.env`):

```
models/trading-lora-adapter/
├── adapter_config.json
├── adapter_model.safetensors
└── tokenizer_config.json   # (optional – copy from base model)
```

---

## QLoRA Fine-Tuning Guide

### 1. Prerequisites

```bash
pip install transformers peft trl datasets accelerate bitsandbytes
```

### 2. Dataset Format

Each training sample should follow the Instruction → Output format:

```json
{
  "instruction": "Analyse the current market state for NSE:RELIANCE.\nMarket State:\n  - Close Price  : 2450.35\n  - RSI (14)      : 72.4\n  - EMA Fast (9)  : 2440.10\n  - EMA Slow (21)  : 2415.80\n  - Trend        : BULLISH\n  - BB Signal    : ABOVE_UPPER",
  "output": "{\"action\": \"SELL\", \"reason\": \"RSI overbought above 70 and price above upper Bollinger Band – potential reversal.\"}"
}
```

Place the JSONL file at `data/training_data.jsonl`.

### 3. Fine-tuning Script

```python
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
import torch

MODEL_ID = "meta-llama/Meta-Llama-3-8B"
DATA_PATH = "data/training_data.jsonl"
OUTPUT_DIR = "models/trading-lora-adapter"

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    load_in_4bit=True,          # QLoRA: 4-bit quantisation
    device_map="auto",
    torch_dtype=torch.float16,
)
model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)

dataset = load_dataset("json", data_files=DATA_PATH, split="train")

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    fp16=True,
    logging_steps=10,
    save_strategy="epoch",
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    args=training_args,
    dataset_text_field="instruction",
    max_seq_length=512,
)

trainer.train()
trainer.save_model(OUTPUT_DIR)
print(f"Saved LoRA adapter to {OUTPUT_DIR}")
```

### 4. Model Objectives

- Recognise chart patterns (breakout, mean-reversion, RSI divergence).
- **Output ONLY valid JSON** – never free-form text.
- Be conservative: prefer WAIT when signals are ambiguous.

### 5. Security Note

Never commit model weights to Git.  
Add `models/trading-lora-adapter/` to `.gitignore` (already done).
