import sys
from pathlib import Path

# Make the app/ directory importable as the root, so `ingest.*` and `api.*` resolve.
sys.path.insert(0, str(Path(__file__).parent))
