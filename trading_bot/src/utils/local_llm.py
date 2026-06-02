"""
Local LLM inference using GPT-2 (124M) weights loaded via the
LLMs-from-scratch architecture (rasbt/LLMs-from-scratch on GitHub).

Architecture:  llms_from_scratch.ch04.GPTModel  (pure PyTorch, no TF)
Tokeniser:     tiktoken  (gpt2 encoding)
Weights src:   https://huggingface.co/rasbt/gpt2-from-scratch-pytorch
               (pre-converted .pth – no TensorFlow required)

Output contract (matches existing Ollama / Mistral contract):
  {
    "action":       "BUY | SELL | WAIT",
    "reason":       "<one sentence>",
    "confidence":   0-100,
    "suggested_sl": <float>,
    "suggested_tp": <float>
  }
Any failure → WAIT response so the rest of the system is never blocked.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import requests
import torch
import tiktoken

from llms_from_scratch.ch04 import GPTModel
from llms_from_scratch.ch05 import generate, text_to_token_ids, token_ids_to_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPT-2 small (124M) config – matches rasbt/gpt2-from-scratch-pytorch weights
# ---------------------------------------------------------------------------
_GPT2_SMALL_CONFIG: dict = {
    "vocab_size":       50257,
    "context_length":   1024,
    "emb_dim":          768,
    "n_heads":          12,
    "n_layers":         12,
    "drop_rate":        0.0,   # inference only
    "qkv_bias":         True,
}

_MODEL_FILENAME = "gpt2-small-124M.pth"
_MODEL_URL = (
    "https://huggingface.co/rasbt/gpt2-from-scratch-pytorch"
    f"/resolve/main/{_MODEL_FILENAME}"
)

# All local LLM assets live under llm_training/ so the training pipeline
# and inference engine share a single folder.
# __file__ = .../trading_bot/src/utils/local_llm.py → parents[3] = workspace root
_LLM_TRAINING_DIR = Path(__file__).resolve().parents[3] / "llm_training"
_MODELS_DIR  = _LLM_TRAINING_DIR / "models"
_WEIGHT_PATH = _MODELS_DIR / _MODEL_FILENAME
# Training dataset (grown by every analysis run)
_TRAIN_FILE = _LLM_TRAINING_DIR / "data" / "dataset" / "train.jsonl"

# ---------------------------------------------------------------------------
# Module-level singletons (loaded once per process)
# ---------------------------------------------------------------------------
_model: Optional[GPTModel] = None
_tokenizer = None
_device: Optional[torch.device] = None


# ---------------------------------------------------------------------------
# Dynamic few-shot loader
# Instead of hard-coded examples, load the most recent real analyses from
# llm_training/data/dataset/train.jsonl.  Falls back to built-in examples
# when the file is empty or unavailable.
# ---------------------------------------------------------------------------
_FALLBACK_SHOTS = (
    'RSI=28,price=2450.00,trend=BULLISH,macd=BUY,bb=NEUTRAL,atr=12.50,rr=2.5 '
    '→ {{"action":"BUY","reason":"RSI oversold bullish trend","confidence":72,"suggested_sl":2431.25,"suggested_tp":2487.50}}\n'
    'RSI=78,price=3100.00,trend=BEARISH,macd=SELL,bb=OVERBOUGHT,atr=15.00,rr=1.2 '
    '→ {{"action":"SELL","reason":"RSI overbought bearish divergence","confidence":65,"suggested_sl":3122.50,"suggested_tp":3055.00}}\n'
    'RSI=52,price=1800.00,trend=NEUTRAL,macd=NEUTRAL,bb=NEUTRAL,atr=8.00,rr=1.0 '
    '→ {{"action":"WAIT","reason":"No dominant signal above threshold","confidence":40,"suggested_sl":0.0,"suggested_tp":0.0}}\n'
)

_PROMPT_HEADER = (
    "Trading signal JSON. Format: context → {{\"action\":\"BUY|SELL|WAIT\","
    "\"reason\":\"...\",\"confidence\":0-100,"
    "\"suggested_sl\":0.0,\"suggested_tp\":0.0}}\n"
)


def _load_local_examples(n: int = 3) -> str:
    """
    Read the most recent *n* valid training examples from train.jsonl and
    format them as few-shot shots string.  Returns empty string if the
    file is unavailable or has fewer than 2 usable entries.

    Handles two storage formats:
      1. Alpaca  {"instruction", "input", "output"} – added by research pipeline
      2. Llama   {"text": "<s>[INST]...[/INST]...<\\s>"} – pre-existing dataset
    """
    if not _TRAIN_FILE.exists():
        return ""
    try:
        lines = [ln.strip() for ln in _TRAIN_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:
        return ""

    _llama_re   = re.compile(r"\[/INST\]\s*(\{.*?\})\s*(?:</s>|$)", re.DOTALL)
    _inst_rsi   = re.compile(r"RSI[:\s=]+(\d+\.?\d*)")
    _inst_price = re.compile(r"(?:EMA9|price)[:\s=]+(\d+\.?\d*)")
    _inst_sym   = re.compile(r"Symbol[:\s=]+([A-Z0-9]+)")

    shots: list[str] = []
    for line in reversed(lines):
        try:
            ex = json.loads(line)

            # ── Alpaca format ─────────────────────────────────────────────
            if "input" in ex and "output" in ex:
                ctx    = ex["input"].strip()
                output = ex["output"].strip()
                out_d  = json.loads(output)
                if out_d.get("action") not in ("BUY", "SELL", "WAIT"):
                    continue
                shots.append(f"{ctx} → {output}\n")

            # ── Llama chat format ─────────────────────────────────────────
            elif "text" in ex:
                text = ex["text"]
                m = _llama_re.search(text)
                if not m:
                    continue
                out_json = m.group(1).strip()
                out_d    = json.loads(out_json)
                if out_d.get("action") not in ("BUY", "SELL", "WAIT"):
                    continue

                # Build a compact context from the [INST] section
                inst_part = text[:text.find("[/INST]")]
                sym_m   = _inst_sym.search(inst_part)
                rsi_m   = _inst_rsi.search(inst_part)
                price_m = _inst_price.search(inst_part)
                parts: list[str] = []
                if sym_m:   parts.append(sym_m.group(1))
                if rsi_m:   parts.append(f"RSI={rsi_m.group(1)}")
                if price_m: parts.append(f"price={price_m.group(1)}")
                ctx = ",".join(parts) if parts else "market"
                shots.append(f"{ctx} → {out_json}\n")

            if len(shots) >= n:
                break
        except Exception:
            continue

    if len(shots) < 2:
        return ""
    return "".join(reversed(shots))  # chronological order


_SYSTEM_PROMPT = (
    "Trading signal JSON. Format: context → {{\"action\":\"BUY|SELL|WAIT\","
    "\"reason\":\"...\",\"confidence\":0-100,"
    "\"suggested_sl\":0.0,\"suggested_tp\":0.0}}\n"
    '{shots}'
    '{compact_context} →'
)


def _wait_response(reason: str = "local llm unavailable") -> dict:
    return {
        "action": "WAIT",
        "reason": reason,
        "confidence": 0,
        "suggested_sl": 0.0,
        "suggested_tp": 0.0,
    }


# ---------------------------------------------------------------------------
# Weight download
# ---------------------------------------------------------------------------
def _download_weights() -> None:
    """Download pre-converted GPT-2 PyTorch weights (≈500 MB) on first use."""
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if _WEIGHT_PATH.exists():
        return

    logger.info("Downloading GPT-2 weights from HuggingFace (~500 MB) …")
    try:
        with requests.get(_MODEL_URL, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(_WEIGHT_PATH, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        if pct % 10 == 0:
                            logger.info("  … %d%%", pct)
        logger.info("GPT-2 weights saved to %s", _WEIGHT_PATH)
    except Exception as exc:
        if _WEIGHT_PATH.exists():
            _WEIGHT_PATH.unlink()
        raise RuntimeError(f"Failed to download GPT-2 weights: {exc}") from exc


# ---------------------------------------------------------------------------
# Model initialisation
# ---------------------------------------------------------------------------
def _load_model() -> tuple[GPTModel, any, torch.device]:
    """Load GPT-2 model with pretrained weights. Called once, result cached."""
    global _model, _tokenizer, _device

    if _model is not None:
        return _model, _tokenizer, _device

    _download_weights()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Loading local GPT-2 model on %s …", device)

    model = GPTModel(_GPT2_SMALL_CONFIG)
    model.load_state_dict(
        torch.load(_WEIGHT_PATH, map_location=device, weights_only=True)
    )
    model.to(device)
    model.eval()

    tokenizer = tiktoken.get_encoding("gpt2")

    _model, _tokenizer, _device = model, tokenizer, device
    logger.info("Local GPT-2 model ready.")
    return model, tokenizer, device


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------
_JSON_RE = re.compile(r'\{[^{}]*"action"\s*:[^{}]*\}', re.DOTALL)


def _extract_trading_json(raw_text: str) -> Optional[dict]:
    """
    Find the first JSON object containing "action" in the generated text.
    Returns a validated dict or None.
    """
    match = _JSON_RE.search(raw_text)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    action = str(data.get("action", "")).upper().strip()
    if action not in {"BUY", "SELL", "WAIT"}:
        return None

    return {
        "action":       action,
        "reason":       str(data.get("reason", "local llm analysis"))[:200],
        "confidence":   int(data.get("confidence", 0)),
        "suggested_sl": float(data.get("suggested_sl", 0.0)),
        "suggested_tp": float(data.get("suggested_tp", 0.0)),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def query_local_llm(
    market_context: str,
    max_new_tokens: int = 120,
    temperature: float = 0.1,
    top_k: int = 5,
) -> dict:
    """
    Run local GPT-2 inference and return a trading decision dict.

    Parameters
    ----------
    market_context : str
        Compact description of current market conditions, e.g.
        "RSI=42, price below 200-SMA, doji pattern, R:R=2.1"
    max_new_tokens : int
        Maximum tokens to generate (default 120 is sufficient for one JSON line).
    temperature : float
        Sampling temperature; lower = more deterministic (default 0.1).
    top_k : int
        Top-k sampling; keep low for structured output (default 5).

    Returns
    -------
    dict matching the LLM output contract:
        {"action", "reason", "confidence", "suggested_sl", "suggested_tp"}
    """
    try:
        model, tokenizer, device = _load_model()
    except Exception as exc:
        logger.error("local_llm: model load failed – %s", exc)
        return _wait_response(f"model load error: {exc}")

    # Use real past analyses as few-shot examples when available.
    # Falls back to built-in examples on the first few runs.
    local_shots = _load_local_examples(3)
    shots = local_shots if local_shots else _FALLBACK_SHOTS
    prompt = _SYSTEM_PROMPT.format(
        shots=shots,
        compact_context=market_context.strip(),
    )

    try:
        with torch.no_grad():
            token_ids = generate(
                model=model,
                idx=text_to_token_ids(prompt, tokenizer).to(device),
                max_new_tokens=max_new_tokens,
                context_size=_GPT2_SMALL_CONFIG["context_length"],
                temperature=temperature,
                top_k=top_k,
                eos_id=50256,  # GPT-2 <|endoftext|>
            )
        full_text = token_ids_to_text(token_ids, tokenizer)
        # Only parse the newly generated part (after the prompt)
        generated = full_text[len(prompt):]
    except Exception as exc:
        logger.error("local_llm: inference failed – %s", exc)
        return _wait_response(f"inference error: {exc}")

    result = _extract_trading_json(generated)
    if result is None:
        logger.warning("local_llm: could not parse JSON from: %r", generated[:200])
        return _wait_response("could not parse json from model output")

    return result


def is_model_cached() -> bool:
    """Return True if the GPT-2 weights are already downloaded locally."""
    return _WEIGHT_PATH.exists()


def build_compact_context(
    symbol: str,
    indicators: dict[str, Any],
    rr_result=None,
) -> str:
    """
    Build a compact single-line market context string suitable for GPT-2.
    Keeps the token count low so the model has room to generate the JSON.

    Example output:
      "RELIANCE RSI=42.1,price=2500.50,trend=BULLISH,macd=BUY,bb=NEUTRAL,atr=12.50,rr=2.1"
    """
    rsi   = indicators.get("rsi", 0.0)
    close = indicators.get("close", 0.0)
    trend = indicators.get("trend", "NEUTRAL")
    macd  = indicators.get("macd_label", "NEUTRAL")
    bb    = indicators.get("bb_signal", "NEUTRAL")
    atr   = indicators.get("atr", 0.0)

    rr_str = ""
    if rr_result is not None:
        rr_str = f",rr={rr_result.rr_ratio:.1f}"

    return (
        f"{symbol} "
        f"RSI={rsi:.1f},"
        f"price={close:.2f},"
        f"trend={trend},"
        f"macd={macd},"
        f"bb={bb},"
        f"atr={atr:.2f}"
        f"{rr_str}"
    )


def model_info() -> dict:
    """Return metadata about the local model."""
    local_examples = 0
    try:
        if _TRAIN_FILE.exists():
            local_examples = sum(1 for ln in _TRAIN_FILE.read_text(encoding="utf-8").splitlines() if ln.strip())
    except Exception:
        pass

    return {
        "model":            "GPT-2 small (124M)",
        "architecture":     "llms_from_scratch GPTModel (rasbt/LLMs-from-scratch)",
        "weights_src":      _MODEL_URL,
        "weights_dir":      str(_MODELS_DIR),
        "cached":           is_model_cached(),
        "weight_path":      str(_WEIGHT_PATH),
        "device":           str(_device) if _device else "not loaded",
        "training_file":    str(_TRAIN_FILE),
        "local_examples":   local_examples,
    }
