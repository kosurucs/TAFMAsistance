"""
Ollama setup helper — run this once after installing Ollama.

Downloads mistral:7b and creates the custom trading-assistant model.

Prerequisites:
  1. Install Ollama from https://ollama.com/download (Windows installer)
  2. Run:  python llm_training/scripts/setup_ollama.py

Usage after setup:
  - Interactive chat:  ollama run trading-assistant
  - API server (auto-starts with Ollama): http://localhost:11434
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA_API = "http://localhost:11434"
MODELFILE  = Path(__file__).parents[1] / "Modelfile"


def _ollama_running() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_API}/api/tags", timeout=3)
        return True
    except Exception:
        return False


def _check_ollama_installed() -> bool:
    try:
        result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Ollama found: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    return False


def _pull_model(model: str) -> None:
    print(f"\nDownloading base model '{model}' (this may take a few minutes)...")
    result = subprocess.run(["ollama", "pull", model], check=False)
    if result.returncode != 0:
        print(f"[!] Failed to pull {model}. Check your internet connection.")
        sys.exit(1)
    print(f"'{model}' downloaded.")


def _create_trading_model() -> None:
    print(f"\nCreating 'trading-assistant' model from {MODELFILE} ...")
    result = subprocess.run(
        ["ollama", "create", "trading-assistant", "-f", str(MODELFILE)],
        check=False,
    )
    if result.returncode != 0:
        print("[!] Failed to create trading-assistant model.")
        sys.exit(1)
    print("'trading-assistant' model created.")


def _test_model() -> None:
    print("\nTesting model with a sample question...")
    import json

    data = json.dumps({
        "model": "trading-assistant",
        "prompt": "What does RSI above 70 indicate in technical analysis?",
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_API}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode())
            print("\nModel response:")
            print(body.get("response", "")[:500])
    except Exception as exc:
        print(f"[!] Test failed: {exc}")


def main() -> None:
    # 1. Check Ollama is installed
    if not _check_ollama_installed():
        print("\n[!] Ollama is not installed.")
        print("    Download and install from: https://ollama.com/download")
        print("    Then re-run this script.")
        sys.exit(1)

    # 2. Check Ollama service is running
    if not _ollama_running():
        print("\nStarting Ollama service...")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        if not _ollama_running():
            print("[!] Could not start Ollama. Try running 'ollama serve' manually in a terminal.")
            sys.exit(1)
    print("Ollama service is running.")

    # 3. Pull base model
    _pull_model("mistral")

    # 4. Create custom trading model
    _create_trading_model()

    # 5. Quick test
    _test_model()

    print("\n=== Setup complete ===")
    print("Model:  trading-assistant")
    print("API:    http://localhost:11434")
    print("\nThe trading bot and chat API will automatically use this model.")
    print("Make sure Ollama is running ('ollama serve') before starting the app.")


if __name__ == "__main__":
    main()
