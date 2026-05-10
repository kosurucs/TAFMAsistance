"""
Step 4 – Fine-tune Mistral-7B with QLoRA using Unsloth.

Works on a single NVIDIA GPU with 8 GB+ VRAM (e.g. RTX 3070/3080/4080).
Training ~1 000 examples takes roughly 15-30 min on an RTX 3080.

Usage:
    python llm_training/scripts/4_finetune.py

Output model saved to:  llm_training/models/trading_llm/

After training you can run inference via:
    python llm_training/scripts/5_inference_test.py

Requirements:
    pip install -r llm_training/requirements.txt
    (Must have CUDA toolkit installed; NVIDIA GPU required)
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parents[2]
DATASET_DIR = ROOT / "llm_training" / "data" / "dataset"
OUTPUT_DIR  = ROOT / "llm_training" / "models" / "trading_llm"

TRAIN_FILE = DATASET_DIR / "train.jsonl"
EVAL_FILE  = DATASET_DIR / "eval.jsonl"

# ── Hyperparameters ───────────────────────────────────────────────────────────
BASE_MODEL    = "unsloth/mistral-7b-v0.3-bnb-4bit"  # 4-bit quantised, ~5 GB VRAM
MAX_SEQ_LEN   = 2048
LORA_RANK     = 16       # higher = more capacity; 16 is a good balance
LORA_ALPHA    = 32
LORA_DROPOUT  = 0.05
BATCH_SIZE    = 2        # per-device; increase if you have > 12 GB VRAM
GRAD_ACCUM    = 4        # effective batch = BATCH_SIZE * GRAD_ACCUM = 8
LEARNING_RATE = 2e-4
MAX_STEPS     = 500      # ~500 steps is enough for a good domain adaptation
WARMUP_STEPS  = 50
SAVE_STEPS    = 100
LOG_STEPS     = 20
FP16          = True     # use True for Ampere/Turing GPUs (RTX 20xx/30xx)
BF16          = False    # set True and FP16=False for RTX 40xx / A100

# ── Verify dataset exists ─────────────────────────────────────────────────────
def _check_dataset() -> None:
    if not TRAIN_FILE.exists():
        raise FileNotFoundError(
            f"Training data not found at {TRAIN_FILE}\n"
            "Run script 3_prepare_dataset.py first."
        )
    with TRAIN_FILE.open(encoding="utf-8") as f:
        n = sum(1 for _ in f)
    print(f"Training examples: {n}")
    if n < 50:
        print("[!] Very few training examples. Consider adding more books/data.")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    _check_dataset()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Load base model with Unsloth ──────────────────────────────────────
    print("Loading base model (this downloads ~4 GB on first run)...")
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,        # auto-detect from GPU
        load_in_4bit=True, # 4-bit QLoRA — must for 8 GB GPU
    )

    # ── 2. Attach LoRA adapters ───────────────────────────────────────────────
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        use_gradient_checkpointing="unsloth",  # reduces VRAM by ~30 %
        random_state=42,
    )

    # ── 3. Load dataset ───────────────────────────────────────────────────────
    from datasets import load_dataset

    raw = load_dataset(
        "json",
        data_files={"train": str(TRAIN_FILE), "eval": str(EVAL_FILE)},
        split={"train": "train", "eval": "eval"},
    )
    print(f"Dataset loaded: {len(raw['train'])} train, {len(raw['eval'])} eval")

    # ── 4. Training arguments ─────────────────────────────────────────────────
    from transformers import TrainingArguments
    from trl import SFTTrainer

    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR / "checkpoints"),
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        warmup_steps=WARMUP_STEPS,
        max_steps=MAX_STEPS,
        learning_rate=LEARNING_RATE,
        fp16=FP16,
        bf16=BF16,
        logging_steps=LOG_STEPS,
        save_steps=SAVE_STEPS,
        evaluation_strategy="steps",
        eval_steps=SAVE_STEPS,
        save_total_limit=2,
        optim="adamw_8bit",       # 8-bit Adam — saves VRAM
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=42,
        report_to="none",         # set "wandb" if you use Weights & Biases
    )

    # ── 5. Trainer ────────────────────────────────────────────────────────────
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=raw["train"],
        eval_dataset=raw["eval"],
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        dataset_num_proc=2,
        packing=True,             # pack short examples — speeds up training
        args=training_args,
    )

    # ── 6. Train ──────────────────────────────────────────────────────────────
    print("\nStarting training...")
    trainer.train()

    # ── 7. Save final model + tokenizer ──────────────────────────────────────
    final_dir = OUTPUT_DIR / "final"
    model.save_pretrained(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    print(f"\nModel saved to {final_dir}")

    # Also save as a merged 16-bit model for inference without Unsloth
    print("Merging LoRA weights and saving 16-bit model (for easy deployment)...")
    merged_dir = OUTPUT_DIR / "merged_16bit"
    model.save_pretrained_merged(
        str(merged_dir),
        tokenizer,
        save_method="merged_16bit",
    )
    print(f"Merged model saved to {merged_dir}")

    # Optional: save as GGUF for llama.cpp / Ollama
    gguf_dir = OUTPUT_DIR / "gguf_q4"
    model.save_pretrained_gguf(
        str(gguf_dir),
        tokenizer,
        quantization_method="q4_k_m",  # ~4 GB, fast inference
    )
    print(f"GGUF model saved to {gguf_dir}")
    print("\nTraining complete!")


if __name__ == "__main__":
    main()
