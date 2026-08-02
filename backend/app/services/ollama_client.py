import os
import requests


def ollama_rewrite(sentence: str, mode: str, strength: str, avoid: str = "") -> str | None:
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
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=120,
        )

        if response.status_code != 200:
            return None

        data = response.json()

        return data.get("response", "").strip()

    except Exception:
        return None