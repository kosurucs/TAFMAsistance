"""
Step 5 – Test your trained model and optionally serve it via a local API.

Usage:
    # Interactive chat in terminal
    python llm_training/scripts/5_inference_test.py

    # Serve as local REST API (then point trading_bot/src/api.py at it)
    python llm_training/scripts/5_inference_test.py --serve

API endpoint (when --serve):
    POST http://localhost:8001/chat
    Body: {"message": "What is RSI?", "max_tokens": 512}
    Returns: {"reply": "..."}
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
MODEL_DIR = ROOT / "llm_training" / "models" / "trading_llm" / "final"

SYSTEM_PROMPT = (
    "You are a professional trading and finance assistant. "
    "Answer questions clearly and accurately based on sound financial principles. "
    "Always remind users that nothing constitutes financial advice."
)

# ── Model loading ─────────────────────────────────────────────────────────────

def load_model():
    if not MODEL_DIR.exists():
        print(f"[!] Model not found at {MODEL_DIR}")
        print("    Run 4_finetune.py first.")
        sys.exit(1)

    print(f"Loading model from {MODEL_DIR} ...")
    try:
        from unsloth import FastLanguageModel
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(MODEL_DIR),
            max_seq_length=2048,
            dtype=None,
            load_in_4bit=True,
        )
        FastLanguageModel.for_inference(model)
    except ImportError:
        # Fall back to plain transformers if unsloth not available
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
        model = AutoModelForCausalLM.from_pretrained(
            str(MODEL_DIR),
            torch_dtype=torch.float16,
            device_map="auto",
        )
    return model, tokenizer


def generate_reply(model, tokenizer, message: str, max_new_tokens: int = 512) -> str:
    prompt = (
        f"<s>[INST] <<SYS>>\n{SYSTEM_PROMPT}\n<</SYS>>\n\n"
        f"{message} [/INST]"
    )
    import torch
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.1,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    # Decode only newly generated tokens
    new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
    reply = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    return reply


# ── Interactive CLI ───────────────────────────────────────────────────────────

def interactive_chat(model, tokenizer) -> None:
    print("\nTrading Assistant (fine-tuned). Type 'exit' to quit.\n")
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not user_input or user_input.lower() in {"exit", "quit"}:
            break
        print("Assistant: ", end="", flush=True)
        reply = generate_reply(model, tokenizer, user_input)
        print(reply)
        print()


# ── REST API server ───────────────────────────────────────────────────────────

def serve_api(model, tokenizer, port: int = 8001) -> None:
    """Serve the fine-tuned model as a local HTTP API on port 8001."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn

    api = FastAPI(title="Trading LLM API")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class ChatRequest(BaseModel):
        message: str
        max_tokens: int = 512

    @api.post("/chat")
    def chat(req: ChatRequest) -> dict:
        reply = generate_reply(model, tokenizer, req.message, req.max_tokens)
        return {"reply": reply}

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": str(MODEL_DIR)}

    print(f"\nServing fine-tuned model at http://localhost:{port}")
    print("Point the trading assistant to http://localhost:8001/chat")
    uvicorn.run(api, host="0.0.0.0", port=port)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="Run as HTTP API server on port 8001")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    model, tokenizer = load_model()

    if args.serve:
        serve_api(model, tokenizer, port=args.port)
    else:
        interactive_chat(model, tokenizer)


if __name__ == "__main__":
    main()
