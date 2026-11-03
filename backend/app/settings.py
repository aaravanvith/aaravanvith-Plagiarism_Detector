
"""Runtime configuration for the plagiarism detection system."""

import os
from pathlib import Path


def load_local_env() -> None:
    """Load KEY=VALUE entries from the project .env file."""
    env_path = Path(__file__).resolve().parent.parent / ".env"

    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)

        os.environ.setdefault(
            key.strip(),
            value.strip().strip('"').strip("'")
        )


load_local_env()


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


# EXISTING SIMILARITY SETTINGS

ENABLE_SEMANTIC_SIMILARITY = env_flag(
    "ENABLE_SEMANTIC_SIMILARITY", False
)

SEMANTIC_MODEL_NAME = os.getenv(
    "SEMANTIC_MODEL_NAME", "all-MiniLM-L6-v2"
)


# CORE API SETTINGS

CORE_API_KEY = os.getenv("CORE_API_KEY", "").strip()

CORE_API_URL = os.getenv(
    "CORE_API_URL",
    "https://api.core.ac.uk/v3/search/works/"
)

CORE_MAX_PAGES = int(os.getenv("CORE_MAX_PAGES", "3"))
CORE_MAX_PAPERS = int(os.getenv("CORE_MAX_PAPERS", "15"))


# OPENALEX SETTINGS

OPENALEX_API_URL = "https://api.openalex.org/works"

OPENALEX_API_KEY = os.getenv(
    "OPENALEX_API_KEY", ""
).strip()


# SEMANTIC SCHOLAR SETTINGS

SEMANTIC_SCHOLAR_API_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)

SEMANTIC_SCHOLAR_API_KEY = os.getenv(
    "SEMANTIC_SCHOLAR_API_KEY", ""
).strip()


# ONLINE SEARCH SETTINGS

ONLINE_PROVIDER_TIMEOUT = float(
    os.getenv("ONLINE_PROVIDER_TIMEOUT", "15")
)

ONLINE_MIN_PAPERS = int(
    os.getenv("ONLINE_MIN_PAPERS", "5")
)

ONLINE_MAX_PAPERS_PER_PROVIDER = int(
    os.getenv("ONLINE_MAX_PAPERS_PER_PROVIDER", "15")
)


# GEMINI / CORRECTION AGENT SETTINGS

GEMINI_REWRITE_MODEL = os.getenv(
    "GEMINI_REWRITE_MODEL", "gemini-3.5-flash"
)

GEMINI_TIMEOUT = float(
    os.getenv("GEMINI_TIMEOUT", "30")
)


# API KEY GETTERS

def get_gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def get_core_api_key() -> str:
    load_local_env()
    return os.getenv("CORE_API_KEY", "").strip()


def get_openalex_api_key() -> str:
    return os.getenv("OPENALEX_API_KEY", "").strip()


def get_semantic_scholar_api_key() -> str:
    return os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
