"""Dedicated Gemini client for the Vidya Chaya Audit backend.

Responsibilities
----------------
* Lazily initialise the official `google-genai` SDK client on first use.
* Validate credentials and raise `GeminiConfigurationError` with a clear,
  actionable message when the key is absent or invalid.
* Provide synchronous generation helper that calls `generate_content` with a
  configurable timeout so the FastAPI event loop is not blocked indefinitely.
* Never log, print, or expose the raw API key.
* Ensure the application does not hard-depend on Gemini: callers handle
  `GeminiConfigurationError` and `GeminiRequestError` gracefully, falling back
  to local Ollama or the built-in structural rewriter.

Environment variables (read from process environment; loaded from backend/.env)
-------------------------------------------------------------------------------
`GEMINI_API_KEY`        -- Required for any Gemini request. Never hardcoded.
`GEMINI_REWRITE_MODEL`  -- Model identifier (default: `gemini-2.5-flash`).
`GEMINI_TIMEOUT`        -- Per-request timeout in seconds (default: 30).
`GEMINI_MAX_RETRIES`    -- Number of transient-error retries (default: 2).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional SDK import -- application continues to start even if package is absent.
# ---------------------------------------------------------------------------
try:
    from google import genai as _genai_module          # type: ignore
    from google.genai import errors as _genai_errors   # type: ignore
    from google.genai import types as _genai_types     # type: ignore
    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    _genai_module = None     # type: ignore
    _genai_errors = None     # type: ignore
    _genai_types = None      # type: ignore
    _SDK_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public exception hierarchy
# ---------------------------------------------------------------------------

class GeminiConfigurationError(RuntimeError):
    """Raised when the Gemini API key is absent, empty, invalid, or SDK is missing."""


class GeminiRequestError(RuntimeError):
    """Raised for transient or permanent API errors (rate limit, quota, network)."""


# ---------------------------------------------------------------------------
# Internal state -- one client instance shared across requests
# ---------------------------------------------------------------------------
_client: Optional[object] = None


def _key() -> str:
    """Return the configured API key without logging it."""
    return os.getenv("GEMINI_API_KEY", "").strip()


def configured() -> bool:
    """Return True when `GEMINI_API_KEY` is set to a non-empty value."""
    return bool(_key())


def is_available() -> bool:
    """Return True if both the google-genai SDK is installed and an API key is set."""
    return _SDK_AVAILABLE and configured()


def _default_model() -> str:
    """Return the currently supported Gemini model identifier."""
    model = os.getenv("GEMINI_REWRITE_MODEL", "gemini-3.5-flash").strip()
    # Guard against retired models or models with known severe capacity bottlenecks
    if not model or model in ("gemini-2.5-flash", "gemini-3.8-flash"):
        return "gemini-3.5-flash"
    return model


def _timeout() -> float:
    """Request timeout in seconds (default: 30.0)."""
    try:
        return max(1.0, float(os.getenv("GEMINI_TIMEOUT", "30")))
    except ValueError:
        return 30.0


def _max_retries() -> int:
    """Number of transient retries (default: 2, bounded 0..5)."""
    try:
        return max(0, min(int(os.getenv("GEMINI_MAX_RETRIES", "2")), 5))
    except ValueError:
        return 2


def get_client():
    """Return (or lazily create) the shared google.genai.Client.

    Raises
    ------
    GeminiConfigurationError
        If the API key is absent or the SDK package is not installed.
    """
    global _client
    api_key = _key()
    if not api_key:
        raise GeminiConfigurationError(
            "GEMINI_API_KEY is not set. Add it to backend/.env (locally) or to "
            "the server environment variables."
        )
    if not _SDK_AVAILABLE or _genai_module is None:  # pragma: no cover
        raise GeminiConfigurationError(
            "GEMINI_API_KEY is configured but the google-genai package is not "
            "installed. Run: pip install -r backend/requirements.txt"
        )
    if _client is None:
        try:
            timeout_ms = int(_timeout() * 1000)
            http_options = _genai_types.HttpOptions(timeout=timeout_ms) if _genai_types else None
            _client = _genai_module.Client(api_key=api_key, http_options=http_options)
            logger.info("Gemini client initialised (default_model=%s)", _default_model())
        except Exception as exc:
            raise GeminiConfigurationError(
                f"Gemini client initialisation failed: {exc}"
            ) from exc
    return _client


def generate_text(
    prompt: str,
    model: str | None = None,
    system_instruction: str | None = None,
    temperature: float = 0.7,
    timeout: float | None = None,
) -> str:
    """Send `prompt` to Gemini using the google-genai SDK and return the response text.

    Parameters
    ----------
    prompt:
        The text prompt.
    model:
        Optional model override (default: GEMINI_REWRITE_MODEL or 'gemini-2.5-flash').
    system_instruction:
        Optional steering instruction for the model.
    temperature:
        Sampling temperature (default: 0.7).
    timeout:
        Per-call timeout in seconds override.

    Returns
    -------
    str
        The response text with leading/trailing whitespace stripped.

    Raises
    ------
    GeminiConfigurationError
        API key absent, invalid, or model not found.
    GeminiRequestError
        Quota exhausted, rate limited, or all retries failed.
    """
    client = get_client()
    chosen_model = model or _default_model()
    if chosen_model == "gemini-2.5-flash":
        chosen_model = "gemini-3.5-flash"

    max_retries = _max_retries()
    last_exc: Exception | None = None

    timeout_sec = timeout if timeout is not None else _timeout()
    timeout_ms = int(timeout_sec * 1000)

    for attempt in range(max_retries + 1):
        try:
            config = None
            if _genai_types:
                config_kwargs = {
                    "temperature": temperature,
                    "candidate_count": 1,
                    "http_options": _genai_types.HttpOptions(timeout=timeout_ms),
                }
                if system_instruction:
                    config_kwargs["system_instruction"] = system_instruction
                config = _genai_types.GenerateContentConfig(**config_kwargs)

            response = client.models.generate_content(
                model=chosen_model,
                contents=prompt,
                config=config,
            )
            text = (response.text or "").strip()
            if not text:
                raise GeminiRequestError(
                    "Gemini returned an empty response. "
                    "The prompt may have been blocked or the model produced no output."
                )
            return text

        except GeminiConfigurationError:
            raise

        except GeminiRequestError:
            raise

        except Exception as exc:
            exc_str = str(exc)
            # Detect credential / key errors -- never retry these.
            if any(kw in exc_str.lower() for kw in ("api key", "invalid", "unauthorized", "permission", "403", "401")):
                raise GeminiConfigurationError(
                    f"Gemini rejected the configured API key: {exc}"
                ) from exc
            # Quota exhaustion / rate limit -- do not retry immediately.
            if any(kw in exc_str.lower() for kw in ("quota", "resource_exhausted", "429")):
                raise GeminiRequestError(
                    f"Gemini quota exhausted or rate-limited: {exc}"
                ) from exc
            # Non-existent model error:
            if "404" in exc_str or "not found" in exc_str.lower():
                raise GeminiConfigurationError(
                    f"Gemini model '{chosen_model}' was not found: {exc}"
                ) from exc

            # Transient capacity spikes (503 UNAVAILABLE or 504 DEADLINE_EXCEEDED):
            # Attempt failover to gemini-3.5-flash-lite on subsequent attempt
            if ("503" in exc_str or "unavailable" in exc_str.lower() or "504" in exc_str or "deadline" in exc_str.lower()) and chosen_model != "gemini-3.5-flash-lite":
                logger.info("Failing over Gemini request to gemini-3.5-flash-lite due to transient capacity: %s", exc)
                chosen_model = "gemini-3.5-flash-lite"

            # Transient errors: retry with exponential back-off.
            last_exc = exc
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(
                    "Gemini request attempt %d/%d failed (%s). Retrying in %ds.",
                    attempt + 1, max_retries + 1, exc, wait,
                )
                time.sleep(wait)
            else:
                raise GeminiRequestError(
                    f"Gemini request failed after {max_retries + 1} attempt(s): {exc}"
                ) from exc

    raise GeminiRequestError(f"Gemini request failed: {last_exc}")


def invalidate_client() -> None:
    """Reset the cached client instance (used in tests and config updates)."""
    global _client
    _client = None
