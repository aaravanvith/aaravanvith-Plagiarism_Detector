"""Runtime switches for optional enhancements.

Set ENABLE_SEMANTIC_SIMILARITY=false to keep the original TF-IDF-only
comparison workflow. The default keeps the enhancement available while the
similarity service safely falls back if its optional model is unavailable.
"""
import os
from pathlib import Path


def load_local_env() -> None:
    """Load simple KEY=VALUE entries from backend/.env without dependencies.

    Existing process environment variables always win, which keeps production
    secret management compatible with the local-development configuration.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


ENABLE_SEMANTIC_SIMILARITY = env_flag("ENABLE_SEMANTIC_SIMILARITY", False)
SEMANTIC_MODEL_NAME = os.getenv("SEMANTIC_MODEL_NAME", "all-MiniLM-L6-v2")
CORE_API_KEY = os.getenv("CORE_API_KEY", "")
CORE_API_URL = os.getenv("CORE_API_URL", "https://api.core.ac.uk/v3/search/works/")
CORE_MAX_PAGES = int(os.getenv("CORE_MAX_PAGES", "3"))
CORE_MAX_PAPERS = int(os.getenv("CORE_MAX_PAPERS", "15"))
GEMINI_REWRITE_MODEL = os.getenv("GEMINI_REWRITE_MODEL", "gemini-3.8-flash")
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "30"))


def get_gemini_api_key() -> str:
    """Return configured GEMINI_API_KEY securely from environment without logging."""
    return os.getenv("GEMINI_API_KEY", "").strip()
