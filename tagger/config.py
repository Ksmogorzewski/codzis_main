"""Shared project paths, env helpers, and small data utilities."""

import hashlib
import html
import re
from pathlib import Path

# Project root is two levels up from this file (tagger/config.py -> <root>/).
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data_real"
ENV_FILE = ROOT / ".env"


def load_env_value(name: str) -> str | None:
    """Read a KEY=VALUE entry from the project .env file, or None."""
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


def event_id(url: str) -> str:
    """Stable id derived from the event url (reproducible across re-fetches)."""
    return hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:12]


def strip_html(raw: str) -> str:
    """Remove HTML tags, unescape entities, collapse whitespace."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()
