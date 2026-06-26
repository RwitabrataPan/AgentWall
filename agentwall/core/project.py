from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def detect_project_root() -> Path:
    """Return git root if inside a repo, else CWD. Resolved and OS-agnostic."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    except Exception:
        pass
    return Path.cwd().resolve()


def project_id_for(root: Path) -> str:
    """Deterministic 16-char hex ID from resolved root path."""
    return hashlib.sha256(str(root).encode()).hexdigest()[:16]


def project_name_for(root: Path) -> str:
    return root.name
