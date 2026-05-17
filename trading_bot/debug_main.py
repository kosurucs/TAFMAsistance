"""Debug script to find where main.py hangs."""
print("DEBUG: Starting script...", flush=True)

import sys
sys.path.insert(0, 'c:/Source/TAFMAsistance/TAFMAsistance/trading_bot')

print("DEBUG: About to import load_dotenv...", flush=True)
from dotenv import load_dotenv
print("DEBUG: About to load .env...", flush=True)
load_dotenv()
print("DEBUG: .env loaded", flush=True)

print("DEBUG: About to import os...", flush=True)
import os
print("DEBUG: os imported", flush=True)

print("DEBUG: About to import loguru...", flush=True)
from loguru import logger
print("DEBUG: loguru imported", flush=True)

print("DEBUG: About to try Redis connection...", flush=True)
try:
    import redis as redis_lib
    print("DEBUG: Redis module imported", flush=True)
    _redis_client = redis_lib.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        db=int(os.environ.get("REDIS_DB", 0)),
        decode_responses=True,
        socket_connect_timeout=2,
    )
    print("DEBUG: Redis client created", flush=True)
    _redis_client.ping()
    print("DEBUG: Redis ping successful", flush=True)
except Exception as e:
    print(f"DEBUG: Redis failed: {e}", flush=True)
    _redis_client = None

print("DEBUG: About to import trading_agent...", flush=True)
from src.agents.trading_agent import TradingState, build_trading_graph
print("DEBUG: trading_agent imported", flush=True)

print("DEBUG: About to import kite_tools...", flush=True)
from src.tools.kite_tools import KiteAuthManager, KiteDataFetcher, KiteOrderManager, KitePortfolio
print("DEBUG: kite_tools imported", flush=True)

print("DEBUG: About to import data_pipeline...", flush=True)
from src.tools.data_pipeline import DataPipeline
print("DEBUG: data_pipeline imported", flush=True)

print("DEBUG: About to import risk_manager...", flush=True)
from src.utils.risk_manager import RiskManager
print("DEBUG: risk_manager imported", flush=True)

print("DEBUG: Reading PAPER_TRADING setting...", flush=True)
PAPER_TRADING = os.environ.get("PAPER_TRADING", "true").lower() == "true"
print(f"DEBUG: PAPER_TRADING = {PAPER_TRADING}", flush=True)

print("\n✓ All imports and initialization successful!", flush=True)
print("DEBUG: Script completed successfully", flush=True)
