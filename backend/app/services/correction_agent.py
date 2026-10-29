"""Contextual academic rewriting used by the Correction Agent.

A configured LLM is preferred for semantic rewriting.  The local fallback is
structural: it rearranges clauses and changes voice; it never does word-by-word
synonym replacement.  The public API remains compatible with /api/correct.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import json
import logging
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from . import gemini_client
from .ollama_client import ollama_rewrite
from ..settings import load_local_env

load_local_env()

logger = logging.getLogger(__name__)

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
    "evaluate": "evaluated", "evaluates": "evaluated",
    "examine": "examined", "examines": "examined",
    "investigate": "investigated", "investigates": "investigated",
    "measure": "measured", "measures": "measured",
    "assess": "assessed", "assesses": "assessed",
    "demonstrate": "demonstrated", "demonstrates": "demonstrated",
    "observe": "observed", "observes": "observed",
    "track": "tracked", "tracks": "tracked",
    "present": "presented", "presents": "presented",
    "predict": "predicted", "predicts": "predicted",
}
_BASE_VERBS = {
    "detects": "detect", "identifies": "identify", "stores": "store", "uses": "use",
    "combines": "combine", "integrates": "integrate", "monitors": "monitor",
    "analyzes": "analyze", "generates": "generate", "processes": "process",
    "manages": "manage", "records": "record", "proposes": "propose", "provides": "provide",
    "supports": "support", "improves": "improve",
    "collects": "collect",
    "evaluates": "evaluate", "examines": "examine", "investigates": "investigate",
    "measures": "measure", "assesses": "assess", "demonstrates": "demonstrate",
    "observes": "observe", "tracks": "track", "presents": "present", "predicts": "predict",
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
        "supports|support|improves|improve|collects|collect|evaluates|evaluate|"
        "examines|examine|investigates|investigate|measures|measure|assesses|assess|"
        "demonstrates|demonstrate|observes|observe|tracks|track|presents|present|predicts|predict"
    )
    match = re.match(
        rf"^(?P<subject>(?:the|this|that|an|a|[A-Z][a-zA-Z0-9_\-]*)\s+[^,]+?)\s+(?P<verb>{verbs})\s+(?P<object>.+)$",
        _core(sentence), re.I,
    )
    return (match.group("subject"), match.group("verb"), match.group("object")) if match else None


def _offline_candidates(sentence: str, mode: str) -> list[str]:
    """Generate 3–5 full-sentence structural candidates, never token swaps."""
    ending, core = _ending(sentence), _core(sentence)
    candidates: list[str] = []

    # 1. Contrastive clauses: e.g. "Clause1, whereas/while/although Clause2"
    contrastive = re.match(
        r"^(?P<c1>.+?),\s*(?P<conj>whereas|while|whilst|although|in contrast to which)\s+(?P<c2>.+)$",
        core,
        re.I,
    )
    if contrastive:
        c1 = contrastive.group("c1").strip()
        c2 = contrastive.group("c2").strip()
        c1_low = c1[0].lower() + c1[1:] if not c1[:2].isupper() else c1
        c2_low = c2[0].lower() + c2[1:] if not c2[:2].isupper() else c2
        c1_cap = c1[0].upper() + c1[1:]
        c2_cap = c2[0].upper() + c2[1:]

        if mode == "academic":
            candidates.append(_sentence(f"While {c2_low}, {c1_low}", ending))
            candidates.append(_sentence(f"{c1_cap}; in contrast, {c2_low}", ending))
            candidates.append(_sentence(f"Whereas {c2_low}, {c1_low}", ending))
            return candidates
        elif mode == "human":
            candidates.append(_sentence(f"Although {c2_low}, {c1_low}", ending))
            candidates.append(_sentence(f"{c1_cap}, though {c2_low}", ending))
            candidates.append(_sentence(f"While {c1_low}, {c2_low}", ending))
            return candidates
        else:  # simple
            candidates.append(_sentence(f"{c2_cap}. In comparison, {c1_low}", ending))
            candidates.append(_sentence(f"{c1_cap}. In contrast, {c2_low}", ending))
            candidates.append(_sentence(f"{c1_cap}, but {c2_low}", ending))
            return candidates

    # 2. Coordinate clauses: e.g. "Clause1, and Clause2"
    coord = re.match(
        r"^(?P<c1>.+?),\s*and\s+(?P<c2>.+)$",
        core,
        re.I,
    )
    if coord:
        c1 = coord.group("c1").strip()
        c2 = coord.group("c2").strip()
        c1_low = c1[0].lower() + c1[1:] if not c1[:2].isupper() else c1
        c2_low = c2[0].lower() + c2[1:] if not c2[:2].isupper() else c2
        c1_cap = c1[0].upper() + c1[1:]
        c2_cap = c2[0].upper() + c2[1:]

        if mode == "academic":
            candidates.append(_sentence(f"In conjunction with {c1_low}, {c2_low}", ending))
            candidates.append(_sentence(f"{c1_cap}; additionally, {c2_low}", ending))
            return candidates
        elif mode == "human":
            candidates.append(_sentence(f"Along with {c1_low}, {c2_low}", ending))
            candidates.append(_sentence(f"{c2_cap}, and {c1_low}", ending))
            return candidates
        else:  # simple
            candidates.append(_sentence(f"{c1_cap}. Also, {c2_low}", ending))
            candidates.append(_sentence(f"Both {c1_low} and {c2_low}", ending))
            return candidates

    parsed = _split_clause(sentence)
    if parsed:
        subject, verb, obj = parsed
        subject_lower = subject[0].lower() + subject[1:] if not subject.isupper() else subject
        participle = _PARTICIPLES.get(verb.lower(), verb.lower())
        base_v = _base_verb(verb)
        tail = re.match(r"(?P<object>.+?)\s+(?P<link>using|through|with|to|via)\s+(?P<detail>.+)$", obj, re.I)

        if mode == "academic":
            if tail and tail.group("link").lower() in {"using", "through", "with", "via"}:
                candidates.append(_sentence(
                    f"Through {tail.group('detail')}, {tail.group('object')} are {participle} by {subject_lower}", ending
                ))
                candidates.append(_sentence(
                    f"{tail.group('object').capitalize()} are systematically {participle} by {subject_lower} via {tail.group('detail')}", ending
                ))
                candidates.append(_sentence(
                    f"Utilization of {tail.group('detail')} enables {subject_lower} to {base_v} {tail.group('object')}", ending
                ))
            else:
                candidates.append(_sentence(f"{obj.capitalize()} are {participle} by {subject_lower}", ending))
                candidates.append(_sentence(f"Systematic evaluation of {obj} is conducted by {subject_lower}", ending))
            candidates.append(_sentence(
                f"{subject} relies on {tail.group('detail') if tail else obj} to {base_v} {tail.group('object') if tail else 'the primary objectives'}", ending
            ))
            return candidates

        if mode == "human":
            if tail:
                return [
                    _sentence(f"With {tail.group('detail')}, {subject_lower} can {base_v} {tail.group('object')}", ending),
                    _sentence(f"{subject} uses {tail.group('detail')} to {base_v} {tail.group('object')}", ending),
                    _sentence(f"{tail.group('object').capitalize()} are handled through {tail.group('detail')} by {subject_lower}", ending),
                ]
            return [
                _sentence(f"{subject} is responsible for {_gerund(verb)} {obj}", ending),
                _sentence(f"In practice, {subject} helps {base_v} {obj}", ending),
                _sentence(f"{obj.capitalize()} form part of the work carried out by {subject_lower}", ending),
            ]

        if mode == "simple":
            if tail:
                return [
                    _sentence(f"{subject} uses {tail.group('detail')} to {base_v} {tail.group('object')}", ending),
                    _sentence(f"{tail.group('object').capitalize()} can be {participle} using {tail.group('detail')}", ending),
                    _sentence(f"The {tail.group('detail')} help {subject_lower} {base_v} {tail.group('object')}", ending),
                ]
            return [
                _sentence(f"{subject} can {base_v} {obj}", ending),
                _sentence(f"{obj.capitalize()} can be {participle} by {subject_lower}", ending),
                _sentence(f"{subject} is used to {base_v} {obj}", ending),
            ]

    relative = re.match(r"^(?P<intro>.+?)\s+that\s+(?P<detail>.+)$", core, re.I)
    if relative:
        candidates.extend([
            _sentence(f"{relative.group('detail').capitalize()}, forming {relative.group('intro').lower()}", ending),
            _sentence(f"{relative.group('intro')} is designed around {relative.group('detail')}", ending),
        ])

    prep = re.match(r"^(?P<main>.+?)\s+(?P<prep>using|through|via)\s+(?P<detail>[^.!?]+)$", core, re.I)
    if prep:
        main, link, detail = prep.group("main"), prep.group("prep").lower(), prep.group("detail")
        main_lower = main[0].lower() + main[1:]
        if mode == "academic":
            candidates.append(_sentence(f"Through {detail}, {main_lower} is systematically conducted", ending))
            candidates.append(_sentence(f"In the context of {detail}, {main_lower}", ending))
        elif mode == "human":
            candidates.append(_sentence(f"By {link} {detail}, {main_lower}", ending))
            candidates.append(_sentence(f"With {detail}, {main_lower}", ending))
        else:
            candidates.append(_sentence(f"{link.capitalize()} {detail}, {main_lower}", ending))
            candidates.append(_sentence(f"Using {detail}, {main_lower}", ending))

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
    if not first or not second:
        return False
    if first.strip().lower() == second.strip().lower():
        return True
    return SequenceMatcher(None, first.lower(), second.lower()).ratio() > 0.88


def _best_offline_rewrite(sentence: str, mode: str, strength: str, avoid: list[str] | None = None) -> str | None:
    candidates = [item for item in _offline_candidates(sentence, mode) if _valid_candidate(sentence, item)]
    avoid = avoid or []
    distinct = [item for item in candidates if not any(_too_similar(item, prior) for prior in avoid)]
    choices = distinct or candidates
    if choices:
        if strength in {"strong", "maximum"}:
            return min(choices, key=lambda item: SequenceMatcher(None, _tokens(sentence), _tokens(item)).ratio())
        return max(choices, key=lambda item: _candidate_score(sentence, item))
    return None


_MODE_INSTRUCTIONS = {
    "academic": (
        "You are an IEEE and biomedical research-paper editor. Rewrite this single sentence in formal, publication-ready academic English. "
        "You MUST syntactically restructure the sentence (for example, by inverting clauses, using formal contrastive markers, "
        "or converting voice). Do NOT return the sentence unchanged or identical to the original. "
        "Do NOT prepend filler phrases like 'The subject addressed in this report', 'In this context', or 'In this investigation'. "
        "Preserve all scientific facts, medical terminology, acronyms, diagnoses, and numbers accurately. "
        "Return ONLY the single rewritten sentence without preamble, explanations, numbering, or quotation marks."
    ),
    "human": (
        "You are a university student writing a research paper in your own authentic, fluent voice. "
        "Rewrite this single sentence in natural, conversational active voice appropriate for an academic report. "
        "You MUST reorder or restructure the clauses so it sounds independently composed in your own words. "
        "Do NOT return the sentence unchanged, and do NOT use generic prefixes like 'In practical terms' or 'From our observations'. "
        "Preserve all scientific facts, medical terminology, acronyms, diagnoses, and numbers accurately. "
        "Return ONLY the single rewritten sentence without preamble, explanations, numbering, or quotation marks."
    ),
    "simple": (
        "You are writing an educational guide for students and general readers. "
        "Rewrite this single sentence in plain, clear, everyday English with direct and simple sentence structure. "
        "You may break complex compound ideas into two short sentences if helpful. "
        "Do NOT return the sentence unchanged, and do NOT use robotic prefixes like 'Overall' or 'In short'. "
        "Preserve all essential scientific facts, medical terminology, acronyms, diagnoses, and numbers accurately. "
        "Return ONLY the single rewritten sentence (or two short sentences) without preamble, explanations, numbering, or quotation marks."
    ),
}


def _clean_llm_output(text: str) -> str:
    """Clean markdown fences, surrounding quotes, or prefix labels from LLM output."""
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]).strip()
    # If the model output multiple lines, pick the first non-empty line that isn't a header/bullet
    for line in cleaned.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^(?:\d+[\.)]|\*|-)\s*", "", line).strip()
        line = re.sub(
            r"^(?:(?:rewritten\s+)?sentence|rewrite|academic(?:\s+version)?|human(?:\s+version)?|simple(?:\s+version)?):\s*",
            "",
            line,
            flags=re.I,
        ).strip()
        if (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
            line = line[1:-1].strip()
        if line:
            return line
    return cleaned


def _gemini_client():
    """Return the initialized Gemini client via the dedicated gemini_client service."""
    if not gemini_client.configured():
        return None
    try:
        return gemini_client.get_client()
    except Exception as exc:
        logger.warning("Gemini client configuration failed: %s", exc)
        return None


def _rewrite_prompt(sentence: str, mode: str, strength: str, avoid: str = "") -> str:
    prompt = (
        f"{_MODE_INSTRUCTIONS[mode]}\n\n"
        f"Target Mode: {mode.upper()}\n"
        f"Rewrite strength: {strength}. Maintain precision: preserve all medical terms, acronyms, and scientific conclusions. "
        "Do not use conversational filler (such as 'In other words'). Return ONLY the single rewritten sentence.\n"
        f"Original sentence: {sentence}"
    )
    if avoid:
        prompt += (
            f"\nDo not copy the structure or wording of this rewrite: {avoid} "
            "Use a distinct sentence pattern."
        )
    return prompt


def _gemini_rewrite(sentence: str, mode: str, strength: str, avoid: str = "") -> str | None:
    """One independent Gemini request per mode; responses are never shared."""
    if not gemini_client.configured():
        return None
    try:
        prompt = _rewrite_prompt(sentence, mode, strength, avoid)
        text = gemini_client.generate_text(prompt)
        text = _clean_llm_output(text)
        return text if _valid_candidate(sentence, text) else None
    except gemini_client.GeminiConfigurationError as exc:
        logger.warning("Gemini configuration issue, falling back: %s", exc)
        return None
    except gemini_client.GeminiRequestError as exc:
        logger.warning("Gemini request issue, falling back: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Gemini rewrite unexpected error, falling back: %s", exc)
        return None


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
            rewrite = _clean_llm_output(rewrite)
    except (URLError, OSError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    return rewrite if _valid_candidate(sentence, rewrite) else None


def rewrite_suggestions(
    sentence: str,
    strength: str = "moderate",
    return_provider: bool = False,
    return_error: bool = False,
    mode: str | None = None,
) -> dict[str, str] | tuple[dict[str, str], str] | tuple[dict[str, str], str, str | None]:
    """Create independent, validated mode outputs for instant client-side tabs.

    Provider hierarchy:
    1. Gemini API via official google-genai SDK
    2. OpenAI (preserved secondary provider)
    3. Ollama (local model fallback)
    4. Deterministic offline structural rule-based generator
    """
    strength = strength if strength in {"light", "moderate", "strong", "maximum"} else "moderate"

    rewrites: dict[str, str] = {}
    provider_used = "offline"
    error_message: str | None = None

    for m in _MODES:
        avoid = rewrites.get("human", "") if m == "simple" else (rewrites.get("academic", "") if m == "human" else "")
        candidate = None
        mode_provider = "offline"

        # 1. Primary provider: Gemini API
        if gemini_client.configured():
            try:
                candidate = _gemini_rewrite(sentence, m, strength, avoid)
                if candidate:
                    mode_provider = "gemini"
            except Exception as exc:
                error_message = f"Gemini error: {exc}"

        # 2. Secondary provider: OpenAI if configured
        if not candidate and os.getenv("OPENAI_API_KEY"):
            candidate = _openai_rewrite(sentence, m, strength, avoid)
            if candidate:
                mode_provider = "openai"

        # 3. Tertiary provider: Local Ollama
        if not candidate:
            candidate = ollama_rewrite(sentence, m, strength, avoid)
            if candidate:
                mode_provider = "ollama"

        # If LLM candidate is too similar to another mode, attempt once with explicit avoidance
        if candidate and any(_too_similar(candidate, prior) for prior in rewrites.values()):
            if gemini_client.configured():
                alt_cand = _gemini_rewrite(sentence, m, strength, avoid=f"{avoid} Use a completely different clause order or syntax.")
                if alt_cand and not any(_too_similar(alt_cand, prior) for prior in rewrites.values()):
                    candidate = alt_cand

        # 4. Final deterministic structural fallback
        if not candidate:
            candidate = _best_offline_rewrite(sentence, m, strength, list(rewrites.values()))
            if candidate:
                mode_provider = "offline"

        if candidate:
            rewrites[m] = candidate
            if mode_provider != "offline":
                provider_used = mode_provider
        else:
            rewrites[m] = ""
            if not error_message:
                error_message = f"Could not generate an independent {m} rewrite without altering scientific meaning."

    if return_provider and return_error:
        return rewrites, provider_used, error_message
    if return_provider:
        return rewrites, provider_used
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


def correct_sentence(
    sentence: str,
    source_name: str,
    score: float,
    seed: int = 0,
    strength: str = "moderate",
    mode: str = "academic",
) -> dict:
    selected_mode = mode.lower().strip() if mode and mode.lower().strip() in _MODES else "academic"
    rewrites, provider, error = rewrite_suggestions(
        sentence,
        strength=strength,
        return_provider=True,
        return_error=True,
        mode=selected_mode,
    )
    primary_rewrite = rewrites.get(selected_mode) or rewrites.get("academic") or ""

    if not primary_rewrite or primary_rewrite.strip().lower() == sentence.strip().lower():
        error = error or f"Failed to generate an independent {selected_mode} rewrite."

    return {
        "original": sentence,
        "rewritten": primary_rewrite,
        "mode": selected_mode,
        "rewrites": rewrites,
        "provider": provider,
        "is_fallback": provider == "offline",
        "error": error if not primary_rewrite else None,
        "explanation": explain_flag(sentence, source_name, score),
        "citation_apa": suggest_citation(source_name, "APA"),
        "citation_ieee": suggest_citation(source_name, "IEEE"),
    }


def _chat_rewrite(context: dict) -> str:
    res = rewrite_suggestions(context["sentence"])
    rewrite = res.get("academic") or res.get("human") or context["sentence"]
    return f'Academic rewrite: "{rewrite}"'


CHAT_TEMPLATES = [
    (re.compile(r"why.*flag", re.I), lambda ctx: explain_flag(ctx["sentence"], ctx["source"], ctx["score"])),
    (re.compile(r"(rewrite|improve|fix|correct)", re.I), _chat_rewrite),
    (re.compile(r"citat|reference|cite", re.I), lambda ctx: f"Suggested citation (APA): {suggest_citation(ctx['source'])}"),
]


def _gemini_chat_reply(message: str, context: dict) -> str | None:
    """Use Gemini for contextual academic assistance in the correction chatbot."""
    if not gemini_client.configured():
        return None
    prompt = (
        "You are an academic integrity and writing assistant in the Vidya Chaya Audit tool. "
        "A student is reviewing a flagged sentence in their academic paper.\n"
        f"Flagged Sentence: \"{context.get('sentence', '')}\"\n"
        f"Matched Source: \"{context.get('source', '')}\"\n"
        f"Similarity Score: {context.get('score', 0)}%\n\n"
        f"Student question: {message}\n\n"
        "Provide a concise, helpful, and professional response (1-3 sentences). "
        "If they ask to rewrite, provide a high-quality academic rewrite. "
        "If they ask for citation, provide APA or IEEE citation guidance. "
        "Do not use markdown headers or long bulleted lists."
    )
    try:
        reply = gemini_client.generate_text(prompt)
        return reply.strip() if reply else None
    except Exception as exc:
        logger.warning("Gemini chat error, falling back to templates: %s", exc)
        return None


def chat_reply(message: str, context: dict) -> str:
    # If Gemini is configured, use it for contextual assistant replies
    gemini_answer = _gemini_chat_reply(message, context)
    if gemini_answer:
        return gemini_answer

    # Fallback to existing deterministic templates
    for pattern, handler in CHAT_TEMPLATES:
        if pattern.search(message):
            return handler(context)
    return "I can explain the match, provide an academic rewrite, or suggest a citation."
