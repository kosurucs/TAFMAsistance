"""Test script to diagnose main.py hanging issue."""
import sys
sys.path.insert(0, 'c:/Source/TAFMAsistance/TAFMAsistance/trading_bot')

print("1. Starting imports...")
from dotenv import load_dotenv
load_dotenv()

print("2. Loading environment...")
import os
print(f"   PAPER_TRADING={os.environ.get('PAPER_TRADING', 'true')}")
print(f"   WATCHLIST={os.environ.get('WATCHLIST', 'RELIANCE')}")

print("3. Importing Redis...")
try:
    import redis as redis_lib
    print("   Redis module imported")
except Exception as e:
    print(f"   Redis import failed: {e}")

print("4. Importing trading_agent...")
from src.agents.trading_agent import TradingState, build_trading_graph
print("   trading_agent imported")

print("5. Importing kite_tools...")
from src.tools.kite_tools import KiteAuthManager, KiteDataFetcher, KiteOrderManager, KitePortfolio
print("   kite_tools imported")

print("6. Importing data_pipeline...")
from src.tools.data_pipeline import DataPipeline
print("   data_pipeline imported")

print("7. Importing risk_manager...")
from src.utils.risk_manager import RiskManager
print("   risk_manager imported")

print("\n✓ All imports successful!")
print("\n8. Testing asyncio...")
import asyncio

async def test_async():
    print("   Async function running...")
    await asyncio.sleep(0.1)
    print("   Async complete!")

asyncio.run(test_async())
print("\n✓ All tests passed!")
