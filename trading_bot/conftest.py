"""pytest configuration – adds the trading_bot directory to sys.path."""
import sys
from pathlib import Path

# Make `src` importable as a top-level package when running pytest from the
# trading_bot directory.
sys.path.insert(0, str(Path(__file__).parent))
