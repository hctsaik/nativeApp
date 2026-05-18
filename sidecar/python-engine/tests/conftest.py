from __future__ import annotations

import sys
from pathlib import Path

# Make the engine module importable from the tests directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
