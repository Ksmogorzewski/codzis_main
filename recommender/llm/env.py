"""Environment / .env helpers (copied from ModelTagowania/tagger/config.py).

Verbatim copy of `load_env_value` so the recommender is self-contained. The original
in ModelTagowania/ is left untouched.
"""

from __future__ import annotations

import os
from pathlib import Path

# Resolve the .env file. Priority:
#   1) DEEPSEEK_ENV_FILE env var (explicit path)
#   2) ./.env  (a local .env next to where you run)
#   3) <repo-root>/.env  (this file lives at <repo-root>/recommender/llm/env.py,
#      so repo root is two levels up)
_HERE = Path(__file__).resolve().parent          # <repo>/recommender/llm
_REPO_ROOT = _HERE.parents[1]                    # <repo>
_CANDIDATES = [
    Path(os.environ.get("DEEPSEEK_ENV_FILE", "")) if os.environ.get("DEEPSEEK_ENV_FILE") else None,
    Path.cwd() / ".env",
    _REPO_ROOT / ".env",
]
ENV_FILE = next((p for p in _CANDIDATES if p and p.exists()), _REPO_ROOT / ".env")


def load_env_value(name: str) -> str | None:
    """Read a KEY=VALUE entry from the resolved .env file, or None."""
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return None
