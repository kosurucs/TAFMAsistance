"""
Step 3 – Build the instruction-tuning dataset.

Reads raw chunks from book_chunks.jsonl and investopedia_chunks.jsonl,
generates diverse Q&A / instruction pairs, and saves them as a JSONL dataset
ready for fine-tuning.

Usage:
    python llm_training/scripts/3_prepare_dataset.py

Output:  llm_training/data/dataset/train.jsonl
         llm_training/data/dataset/eval.jsonl
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parents[2]
PROCESSED_DIR = ROOT / "llm_training" / "data" / "processed"
DATASET_DIR   = ROOT / "llm_training" / "data" / "dataset"

BOOK_CHUNKS   = PROCESSED_DIR / "book_chunks.jsonl"
INVESTO_CHUNKS = PROCESSED_DIR / "investopedia_chunks.jsonl"
HISTORICAL_TRAIN = PROCESSED_DIR / "historical_train.jsonl"
STRATEGY_RULES = PROCESSED_DIR / "strategy_rules.jsonl"

EVAL_SPLIT = 0.30   # 30% held out for evaluation (Phase 5: 70/30 split)
RANDOM_SEED = 42

SOURCE_FILES = [
    BOOK_CHUNKS,
    INVESTO_CHUNKS,
    HISTORICAL_TRAIN,
    STRATEGY_RULES,
]

# ── Instruction templates ─────────────────────────────────────────────────────
# The fine-tune uses Alpaca-style chat:
#   <s>[INST] <<SYS>>\n{system}\n<</SYS>>\n\n{user} [/INST] {assistant} </s>
#
# We generate several instruction types from each text chunk.

SYSTEM_PROMPT = (
    "You are a professional trading and finance assistant. "
    "Answer questions clearly and accurately based on sound financial principles. "
    "Always remind users that nothing constitutes financial advice."
)

# (template_fn, weight)  — weight controls how often that type is sampled
INSTRUCTION_TEMPLATES: list[tuple] = [
    # ── Explain / define ──────────────────────────────────────────────────────
    (lambda chunk: {
        "instruction": f"Explain the following trading concept in simple terms:\n\n{_first_sentence(chunk)}",
        "response": chunk,
    }, 3),

    # ── Summarise ─────────────────────────────────────────────────────────────
    (lambda chunk: {
        "instruction": "Summarise the key points from the following finance passage:",
        "response": _summary_response(chunk),
        "context": chunk,
    }, 2),

    # ── What is … ─────────────────────────────────────────────────────────────
    (lambda chunk: {
        "instruction": f"What is {_extract_key_term(chunk)}? Give a thorough explanation.",
        "response": chunk,
    }, 3),

    # ── How does … work ───────────────────────────────────────────────────────
    (lambda chunk: {
        "instruction": f"How does {_extract_key_term(chunk)} work in financial markets?",
        "response": chunk,
    }, 2),

    # ── Practical application ─────────────────────────────────────────────────
    (lambda chunk: {
        "instruction": (
            "A trader asks: 'How can I use this in my trading strategy?'\n"
            f"Context:\n{chunk}\n\nProvide a practical answer."
        ),
        "response": _practical_response(chunk),
    }, 1),

    # ── Raw passage → Q&A ─────────────────────────────────────────────────────
    (lambda chunk: {
        "instruction": f"Based on the passage below, what are the most important takeaways?\n\n{chunk}",
        "response": _bullet_summary(chunk),
    }, 2),
]


# ── Text helpers ──────────────────────────────────────────────────────────────

def _first_sentence(text: str) -> str:
    """Return the first sentence of the chunk."""
    m = re.search(r"^(.{30,200}?[.!?])", text, re.S)
    return m.group(1).strip() if m else text[:120].strip()


def _extract_key_term(text: str) -> str:
    """Heuristically extract a likely key term from the chunk."""
    # Try bold / uppercase phrases first
    bold = re.search(r"\*\*(.+?)\*\*", text)
    if bold:
        return bold.group(1)
    caps = re.search(r"\b([A-Z][A-Z &]{3,30})\b", text)
    if caps:
        return caps.group(1).title()
    # Fall back: first few words
    words = text.split()[:5]
    return " ".join(words).rstrip(".,;:")


def _summary_response(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    # Take first + last sentences as a naive summary
    if len(sentences) <= 2:
        return text
    return f"{sentences[0]} {sentences[-1]}"


def _practical_response(text: str) -> str:
    return (
        f"Here's how to apply this concept practically:\n\n"
        f"{text}\n\n"
        "⚠ This is educational content. Always apply proper risk management and "
        "consult a registered financial advisor before trading."
    )


def _bullet_summary(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    bullets = [f"• {s.strip()}" for s in sentences if len(s.strip()) > 40][:6]
    return "\n".join(bullets) if bullets else text


# ── Format conversion ─────────────────────────────────────────────────────────

def to_chat_format(instruction: str, response: str, context: str = "") -> dict:
    """Convert an instruction+response pair to Llama-2/Mistral chat format."""
    user_msg = f"{instruction}\n\n{context}".strip() if context else instruction
    return {
        "text": (
            f"<s>[INST] <<SYS>>\n{SYSTEM_PROMPT}\n<</SYS>>\n\n"
            f"{user_msg} [/INST] {response} </s>"
        )
    }


# ── Weighted sampler ──────────────────────────────────────────────────────────

def _pick_template(rng: random.Random):
    templates, weights = zip(*[(fn, w) for fn, w in INSTRUCTION_TEMPLATES])
    return rng.choices(templates, weights=weights, k=1)[0]


# ── Main ──────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(RANDOM_SEED)

    # Load all available sources (only if they exist)
    book_records = load_jsonl(BOOK_CHUNKS)
    investo_records = load_jsonl(INVESTO_CHUNKS)
    historical_records = load_jsonl(HISTORICAL_TRAIN)
    strategy_records = load_jsonl(STRATEGY_RULES)

    # Print per-source counts
    print("Source data loaded:")
    print(f"  Book chunks:           {len(book_records)}")
    print(f"  Investopedia chunks:   {len(investo_records)}")
    print(f"  Historical training:   {len(historical_records)}")
    print(f"  Strategy rules:        {len(strategy_records)}")

    # For book/investopedia, generate Q&A pairs
    # For historical/strategy, they already are in Alpaca format
    all_records = book_records + investo_records
    if not all_records and not historical_records and not strategy_records:
        print("[!] No source data found. Run generation scripts first.")
        return

    examples: list[dict] = []
    for rec in all_records:
        chunk = rec.get("text", "").strip()
        if len(chunk) < 100:
            continue

        # Generate 1-3 examples per chunk
        n = rng.randint(1, 3)
        seen_types: set[int] = set()
        attempts = 0
        while len(seen_types) < n and attempts < 20:
            attempts += 1
            template_fn = _pick_template(rng)
            try:
                pair = template_fn(chunk)
            except Exception:
                continue

            instruction = pair.get("instruction", "")
            response = pair.get("response", "")
            context = pair.get("context", "")

            if not instruction or not response or len(response) < 60:
                continue

            idx = id(template_fn)
            if idx in seen_types:
                continue
            seen_types.add(idx)

            examples.append(to_chat_format(instruction, response, context))

    # Add historical + strategy examples (already in correct format)
    # These have "instruction", "input", "output" — convert to chat format
    for rec in historical_records + strategy_records:
        instruction = rec.get("instruction", "")
        input_text = rec.get("input", "")
        output_text = rec.get("output", "")
        
        if not instruction or not output_text:
            continue
        
        # Build user message with instruction + input
        user_msg = f"{instruction}\n\n{input_text}".strip() if input_text else instruction
        
        examples.append({
            "text": (
                f"<s>[INST] <<SYS>>\n{SYSTEM_PROMPT}\n<</SYS>>\n\n"
                f"{user_msg} [/INST] {output_text} </s>"
            )
        })

    rng.shuffle(examples)

    # Train / eval split
    n_eval = max(1, int(len(examples) * EVAL_SPLIT))
    eval_examples = examples[:n_eval]
    train_examples = examples[n_eval:]

    def _write(path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    _write(DATASET_DIR / "train.jsonl", train_examples)
    _write(DATASET_DIR / "eval.jsonl", eval_examples)

    print(f"\nDataset built:")
    print(f"  Total examples: {len(examples)}")
    print(f"  Train: {len(train_examples)} ({100*(1-EVAL_SPLIT):.0f}%)")
    print(f"  Eval:  {len(eval_examples)} ({100*EVAL_SPLIT:.0f}%)")
    print(f"Saved to: {DATASET_DIR}")

    print(f"Dataset built:  {len(train_examples)} train  |  {len(eval_examples)} eval")
    print(f"Saved to: {DATASET_DIR}")


if __name__ == "__main__":
    main()
