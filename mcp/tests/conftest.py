from __future__ import annotations

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]

# Allow MCP packages and the sidecar annotation package without installation.
sys.path.insert(0, str(repo_root / "mcp"))
sys.path.insert(0, str(repo_root / "sidecar" / "python-engine"))
