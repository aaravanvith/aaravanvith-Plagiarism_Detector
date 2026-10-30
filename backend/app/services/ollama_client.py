import os
import time
import requests

_LAST_OLLAMA_CHECK = 0.0
_OLLAMA_AVAILABLE = True


def _is_ollama_reachable() -> bool:
    global _LAST_OLLAMA_CHECK, _OLLAMA_AVAILABLE
    now = time.time()
    if now - _LAST_OLLAMA_CHECK < 60.0:
        return _OLLAMA_AVAILABLE
    _LAST_OLLAMA_CHECK = now
    try:
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=0.2)
        _OLLAMA_AVAILABLE = (r.status_code == 200)
    except Exception:
        _OLLAMA_AVAILABLE = False
    return _OLLAMA_AVAILABLE


def ollama_rewrite(sentence: str, mode: str, strength: str, avoid: str = "") -> str | None:
    if not _is_ollama_reachable():
        return None
    model = os.getenv("OLLAMA_MODEL", "gemma2:2b")

    prompts = {
        "academic": (
            "Rewrite this as a professional IEEE research paper sentence. "
            "Use formal academic English. Preserve the meaning exactly."
        ),
        "human": (
            "Rewrite this naturally like a university student. "
            "Keep the meaning exactly. Avoid sounding AI-generated."
        ),
        "simple": (
            "Rewrite this in very simple English. "
            "Use short sentences while preserving meaning."
        ),
    }

    prompt = prompts.get(mode, prompts["academic"])

    if avoid:
        prompt += (
            f"\nAvoid wording similar to this rewrite:\n{avoid}"
        )

    prompt += f"""

    Sentence:
    {sentence}

    Return ONLY the rewritten sentence.

    Do NOT explain.
    Do NOT use bullet points.
    Do NOT add notes.
    Do NOT add citation guidance.
    Do NOT say 'Here is the rewrite'.
    Output only one rewritten sentence.
   """

    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=(3.0, 120.0),
        )

        if response.status_code != 200:
            return None

        data = response.json()

        return data.get("response", "").strip()

    except Exception:
        return None