from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SIDECAR_ENGINE = REPO_ROOT / "sidecar" / "python-engine"
if str(SIDECAR_ENGINE) not in sys.path:
    sys.path.insert(0, str(SIDECAR_ENGINE))

WORKSPACE_ROOT = Path(
    os.environ.get("ANNOTATION_WORKSPACE", str(REPO_ROOT / "tmp" / "annotation-workspace"))
)
