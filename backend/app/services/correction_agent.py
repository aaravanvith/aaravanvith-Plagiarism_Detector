"""Contextual academic rewriting used by the Correction Agent.

A configured LLM is preferred for semantic rewriting.  The local fallback is
structural: it rearranges clauses and changes voice; it never does word-by-word
synonym replacement.  The public API remains compatible with /api/correct.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import json
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from .ollama_client import ollama_rewrite

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.-]*")
_FILLER_RE = re.compile(r"^(put differently|in other words|simply put|to rephrase)\b", re.I)
_MODES = ("academic", "human", "simple")
_GEMINI_CLIENT = None


class RewriteProviderConfigurationError(RuntimeError):
    """Raised when the selected rewrite provider cannot be used."""

# Grammatical forms for passive-voice conversion, not synonym replacement.
_PARTICIPLES = {
    "detect": "detected", "detects": "detected", "identify": "identified", "identifies": "identified",
    "store": "stored", "stores": "stored", "use": "used", "uses": "used",
    "combine": "combined", "combines": "combined", "integrate": "integrated", "integrates": "integrated",
    "monitor": "monitored", "monitors": "monitored", "analyze": "analyzed", "analyzes": "analyzed",
    "generate": "generated", "generates": "generated", "process": "processed", "processes": "processed",
    "manage": "managed", "manages": "managed", "record": "recorded", "records": "recorded",
    "propose": "proposed", "proposes": "proposed", "provide": "provided", "provides": "provided",
    "support": "supported", "supports": "supported", "improve": "improved", "improves": "improved",
    "collect": "collected", "collects": "collected",
}
_BASE_VERBS = {
    "detects": "detect", "identifies": "identify", "stores": "store", "uses": "use",
    "combines": "combine", "integrates": "integrate", "monitors": "monitor",
    "analyzes": "analyze", "generates": "generate", "processes": "process",
    "manages": "manage", "records": "record", "proposes": "propose", "provides": "provide",
    "supports": "support", "improves": "improve",
    "collects": "collect",
}


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _WORD_RE.findall(text)]


def _ending(sentence: str) -> str:
    text = sentence.rstrip()
    return text[-1:] if text.endswith((".", "!", "?")) else "."


def _core(sentence: str) -> str:
    return sentence.strip().rstrip(".!?")


def _sentence(text: str, ending: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".!?") + ending


def _base_verb(verb: str) -> str:
    return _BASE_VERBS.get(verb.lower(), verb.lower())


def _gerund(verb: str) -> str:
    base = _base_verb(verb)
    return f"{base[:-1]}ing" if base.endswith("e") else f"{base}ing"


def _technical_terms(sentence: str) -> set[str]:
    """Acronyms and named technologies must remain unchanged."""
    return {
        term.lower() for term in _WORD_RE.findall(sentence)
        if len(term) > 1 and (
            term.isupper() or any(char.isdigit() for char in term) or re.search(r"[a-z][A-Z]", term)
        )
    }


def _split_clause(sentence: str) -> tuple[str, str, str] | None:
    """Parse common technical declarative sentences for voice conversion."""
    verbs = (
        "detects|detect|identifies|identify|stores|store|uses|use|combines|combine|"
        "integrates|integrate|monitors|monitor|analyzes|analyze|generates|generate|"
        "processes|process|manages|manage|records|record|proposes|propose|provides|provide|"
        "supports|support|improves|improve|collects|collect"
    )
    match = re.match(
        rf"^(?P<subject>(?:the|this|that|an|a)\s+[^,]+?)\s+(?P<verb>{verbs})\s+(?P<object>.+)$",
        _core(sentence), re.I,
    )
    return (match.group("subject"), match.group("verb"), match.group("object")) if match else None


def _offline_candidates(sentence: str, mode: str) -> list[str]:
    """Generate 3–5 full-sentence structural candidates, never token swaps."""
    ending, core = _ending(sentence), _core(sentence)
    candidates: list[str] = []
    parsed = _split_clause(sentence)
    if parsed:
        subject, verb, obj = parsed
        participle = _PARTICIPLES.get(verb.lower())
        tail = re.match(r"(?P<object>.+?)\s+(?P<link>using|through|with|to)\s+(?P<detail>.+)$", obj, re.I)
        if participle:
            candidates.append(_sentence(f"{obj} are {participle} by {subject}", ending))
            if tail and tail.group("link").lower() in {"using", "through", "with"}:
                candidates.append(_sentence(
                    f"Through {tail.group('detail')}, {tail.group('object')} are {participle} by {subject}", ending
                ))
        if tail:
            candidates.append(_sentence(
                f"{subject} relies on {tail.group('detail')} to {verb.lower()} {tail.group('object')}", ending
            ))
            candidates.append(_sentence(
                f"{tail.group('object').capitalize()} are handled by {subject} {tail.group('link').lower()} {tail.group('detail')}",
                ending,
            ))

    relative = re.match(r"^(?P<intro>.+?)\s+that\s+(?P<detail>.+)$", core, re.I)
    if relative:
        candidates.extend([
            _sentence(f"{relative.group('detail').capitalize()}, forming {relative.group('intro').lower()}", ending),
            _sentence(f"{relative.group('intro')} is designed around {relative.group('detail')}", ending),
        ])

    # For unparseable sentences, reorganize at the sentence level rather than
    # pretending a few changed words are a paraphrase.
    fallback_prefix = {
        "academic": "The subject addressed in this report is",
        "human": "This report covers",
        "simple": "Report topic",
    }[mode]
    candidates.append(_sentence(f"{fallback_prefix}: {core}", ending))

    if mode == "human" and parsed:
        subject, verb, obj = parsed
        tail = re.match(r"(?P<object>.+?)\s+(?P<link>using|through|with|to)\s+(?P<detail>.+)$", obj, re.I)
        if tail:
            return [
                _sentence(f"With {tail.group('detail')}, {subject} can {_base_verb(verb)} {tail.group('object')}", ending),
                _sentence(f"{subject} uses {tail.group('detail')} to {_base_verb(verb)} {tail.group('object')}", ending),
                _sentence(f"{tail.group('object').capitalize()} are handled through {tail.group('detail')} by {subject}", ending),
            ]
        return [
            _sentence(f"{subject} is responsible for {_gerund(verb)} {obj}", ending),
            _sentence(f"Within {subject}, {obj} are { _PARTICIPLES.get(verb.lower(), verb.lower()) } as part of the process", ending),
            _sentence(f"{obj.capitalize()} form part of the work carried out by {subject}", ending),
        ]
    if mode == "simple" and parsed:
        subject, verb, obj = parsed
        return [
            _sentence(f"{subject} can {_base_verb(verb)} {obj}", ending),
            _sentence(f"{obj.capitalize()} can be {_PARTICIPLES.get(verb.lower(), verb.lower())} by {subject}", ending),
            _sentence(f"{subject} is used to {_base_verb(verb)} {obj}", ending),
        ]
    return candidates


def _candidate_score(original: str, candidate: str) -> float:
    original_tokens, candidate_tokens = _tokens(original), _tokens(candidate)
    if not candidate_tokens or _FILLER_RE.search(candidate):
        return -100.0
    overlap = len(set(original_tokens) & set(candidate_tokens)) / max(1, len(set(candidate_tokens)))
    order = SequenceMatcher(None, original_tokens, candidate_tokens).ratio()
    terms = _technical_terms(original)
    preserved = sum(term in set(candidate_tokens) for term in terms) / max(1, len(terms))
    return (1 - overlap) * 45 + (1 - order) * 35 + preserved * 20


def _valid_candidate(original: str, candidate: str) -> bool:
    if not candidate or candidate.strip().lower() == original.strip().lower() or _FILLER_RE.search(candidate):
        return False
    return _technical_terms(original).issubset(set(_tokens(candidate)))


def _too_similar(first: str, second: str) -> bool:
    sequence = SequenceMatcher(None, first.lower(), second.lower()).ratio()
    first_words, second_words = set(_tokens(first)), set(_tokens(second))
    lexical = len(first_words & second_words) / max(1, len(first_words | second_words))
    return sequence > 0.70 or lexical > 0.70


def _textual_similarity(first: str, second: str) -> float:
    """Token-set similarity used for the stricter Human/Simple guard."""
    first_words, second_words = set(_tokens(first)), set(_tokens(second))
    return len(first_words & second_words) / max(1, len(first_words | second_words))


def _best_offline_rewrite(sentence: str, mode: str, strength: str, avoid: list[str] | None = None) -> str:
    candidates = [item for item in _offline_candidates(sentence, mode) if _valid_candidate(sentence, item)]
    avoid = avoid or []
    distinct = [item for item in candidates if not any(_too_similar(item, prior) for prior in avoid)]
    choices = distinct or candidates
    if choices:
        if strength in {"strong", "maximum"}:
            return min(choices, key=lambda item: SequenceMatcher(None, _tokens(sentence), _tokens(item)).ratio())
        return max(choices, key=lambda item: _candidate_score(sentence, item))
    core = _core(sentence)
    prefix = {"academic": "The subject addressed in this report is", "human": "This report covers", "simple": "Report topic"}[mode]
    return _sentence(f"{prefix}: {core}", _ending(sentence))


_MODE_INSTRUCTIONS = {
    "academic": (
        "You are an IEEE research-paper editor. Write one formal, professional sentence using advanced "
        "academic vocabulary. Restructure the sentence completely; passive voice is encouraged where natural."
    ),
    "human": (
        "You are a university student writing naturally. Use conversational but professional active voice, "
        "reorder the ideas, and make the sentence sound independently written. Avoid overly formal wording."
    ),
    "simple": (
        "You write for school-level readers. Use very easy English, common vocabulary, and the shortest "
        "clear sentence possible. Prefer a different subject and clause order from a normal conversational rewrite."
    ),
}


def _gemini_client():
    """Create the official Google GenAI client once, using the loaded env key."""
    global _GEMINI_CLIENT
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None
    if genai is None:
        raise RewriteProviderConfigurationError(
            "GEMINI_API_KEY is configured but the google-genai package is not installed. "
            "Install backend requirements before starting the API."
        )
    if _GEMINI_CLIENT is None:
        try:
            _GEMINI_CLIENT = genai.Client(api_key=api_key)
        except Exception as exc:
            raise RewriteProviderConfigurationError(
                f"Gemini client initialization failed: {exc}"
            ) from exc
    return _GEMINI_CLIENT


def _rewrite_prompt(sentence: str, mode: str, strength: str, avoid: str = "") -> str:
    prompt = (
        f"{_MODE_INSTRUCTIONS[mode]} Rewrite strength: {strength}. Preserve meaning and technical terms exactly. "
        "Return only the rewritten sentence. Do not use filler such as 'In other words'. Do not add facts.\n"
        f"Sentence: {sentence}"
    )
    if avoid:
        prompt += (
            f"\nDo not copy the wording, subject order, or sentence pattern of this Human rewrite: {avoid} "
            "Your wording must share fewer than 60% of its content words with it."
        )
    return prompt


def _gemini_rewrite(sentence: str, mode: str, strength: str, avoid: str = "") -> str | None:
    """One independent Gemini request per mode; responses are never shared."""
    client = _gemini_client()
    if client is None:
        return None
    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_REWRITE_MODEL", "gemini-3.5-flash"),
            contents=_rewrite_prompt(sentence, mode, strength, avoid),
        )
        rewrite = (response.text or "").strip()
    except Exception as exc:
        raise RewriteProviderConfigurationError(f"Gemini rewrite request failed: {exc}") from exc
    return rewrite if _valid_candidate(sentence, rewrite) else None


def _openai_rewrite(sentence: str, mode: str, strength: str, avoid: str = "") -> str | None:
    """Preserved OpenAI-compatible implementation, used when Gemini is absent."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None
    payload = json.dumps({
        "model": os.getenv("OPENAI_REWRITE_MODEL", "gpt-4o-mini"), "temperature": 0.75,
        "messages": [{"role": "user", "content": _rewrite_prompt(sentence, mode, strength, avoid)}],
    }).encode("utf-8")
    request = Request(
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions", data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            rewrite = json.loads(response.read().decode("utf-8"))["choices"][0]["message"]["content"].strip()
    except (URLError, OSError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    return rewrite if _valid_candidate(sentence, rewrite) else None


def rewrite_suggestions(sentence: str, strength: str = "moderate") -> dict[str, str]:
    """Create independent, validated mode outputs for instant client-side tabs."""
    strength = strength if strength in {"light", "moderate", "strong", "maximum"} else "moderate"
    
    generator = ollama_rewrite
    provider = "Ollama"

    rewrites: dict[str, str] = {}
    for mode in _MODES:
        avoid = rewrites.get("human", "") if mode == "simple" else ""
        candidate = generator(sentence, mode, strength, avoid) if generator else None
        if (
            generator
            and mode == "simple"
            and candidate
            and _textual_similarity(candidate, rewrites["human"]) > 0.60
        ):
            # A second, dedicated Simple request keeps the same meaning while
            # explicitly rejecting the too-similar Human wording.
            candidate = generator(
                sentence,
                mode,
                strength,
                f"{rewrites['human']} Previous Simple attempt was too similar; use a new sentence pattern.",
            )
        # Ollama is optional. A stopped server, unavailable model, or weak
        # response must not turn the Correction Agent into an HTTP 503.
        if candidate and mode == "simple" and _textual_similarity(candidate, rewrites["human"]) > 0.60:
            candidate = None
        if candidate and any(_too_similar(candidate, prior) for prior in rewrites.values()):
            candidate = None
        if not candidate:
            candidate = _best_offline_rewrite(sentence, mode, strength, list(rewrites.values()))
        rewrites[mode] = candidate
    return rewrites


def explain_flag(sentence: str, best_source: str, score: float) -> str:
    strength = "very high textual and structural overlap" if score >= 75 else (
        "notable wording and phrase-level overlap" if score >= 55 else "some overlap in key terms"
    )
    return (
        f'This sentence matches content from "{best_source}" with {strength} '
        f"({score}% similarity). Consider writing it independently or adding a citation to attribute the source."
    )


def suggest_citation(source_name: str, style: str = "APA") -> str:
    if style.upper() == "IEEE":
        return f'[X] Author(s), "{source_name}," source document, n.d.'
    return f"Author, A. A. (n.d.). {source_name}. Source document."


def correct_sentence(sentence: str, source_name: str, score: float, seed: int = 0, strength: str = "moderate") -> dict:
    rewrites = rewrite_suggestions(sentence, strength=strength)
    return {
        "original": sentence,
        "rewritten": rewrites["academic"],  # Existing consumers retain this default.
        "rewrites": rewrites,
        "explanation": explain_flag(sentence, source_name, score),
        "citation_apa": suggest_citation(source_name, "APA"),
        "citation_ieee": suggest_citation(source_name, "IEEE"),
    }


def _chat_rewrite(context: dict) -> str:
    return f'Academic rewrite: "{rewrite_suggestions(context["sentence"])["academic"]}"'


CHAT_TEMPLATES = [
    (re.compile(r"why.*flag", re.I), lambda ctx: explain_flag(ctx["sentence"], ctx["source"], ctx["score"])),
    (re.compile(r"(rewrite|improve|fix|correct)", re.I), _chat_rewrite),
    (re.compile(r"citat|reference|cite", re.I), lambda ctx: f"Suggested citation (APA): {suggest_citation(ctx['source'])}"),
]


def chat_reply(message: str, context: dict) -> str:
    for pattern, handler in CHAT_TEMPLATES:
        if pattern.search(message):
            return handler(context)
    return "I can explain the match, provide an academic rewrite, or suggest a citation."
