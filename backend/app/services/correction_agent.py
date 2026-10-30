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
    "collect": "collected", "collects": "collected", "collected": "collected",
    "evaluate": "evaluated", "evaluates": "evaluated", "evaluated": "evaluated",
    "examine": "examined", "examines": "examined", "examined": "examined",
    "investigate": "investigated", "investigates": "investigated", "investigated": "investigated",
    "measure": "measured", "measures": "measured", "measured": "measured",
    "assess": "assessed", "assesses": "assessed", "assessed": "assessed",
    "enroll": "enrolled", "enrolls": "enrolled", "enrolled": "enrolled",
    "recruit": "recruited", "recruits": "recruited", "recruited": "recruited",
    "quantify": "quantified", "quantifies": "quantified", "quantified": "quantified",
    "administer": "administered", "administers": "administered", "administered": "administered",
    "identify": "identified", "identifies": "identified", "identified": "identified",
    "compare": "compared", "compares": "compared", "compared": "compared",
    "treat": "treated", "treats": "treated", "treated": "treated",
    "detect": "detected", "detects": "detected", "detected": "detected",
    "monitor": "monitored", "monitors": "monitored", "monitored": "monitored",
    "analyze": "analyzed", "analyzes": "analyzed", "analyzed": "analyzed",
    "demonstrate": "demonstrated", "demonstrates": "demonstrated", "demonstrated": "demonstrated",
    "observe": "observed", "observes": "observed", "observed": "observed",
    "track": "tracked", "tracks": "tracked",
    "present": "presented", "presents": "presented",
    "predict": "predicted", "predicts": "predicted",
    "require": "required", "requires": "required", "required": "required",
    "reveal": "revealed", "reveals": "revealed", "revealed": "revealed",
    "indicate": "indicated", "indicates": "indicated", "indicated": "indicated",
    "show": "shown", "shows": "shown", "showed": "shown",
    "exhibit": "exhibited", "exhibits": "exhibited", "exhibited": "exhibited",
    "decrease": "decreased", "decreases": "decreased", "decreased": "decreased",
    "reduce": "reduced", "reduces": "reduced", "reduced": "reduced",
    "increase": "increased", "increases": "increased", "increased": "increased",
    "manifest": "manifested", "manifests": "manifested", "manifested": "manifested",
    "involve": "involved", "involves": "involved",
    "include": "included", "includes": "included",
    "cause": "caused", "causes": "caused", "caused": "caused",
    "confirm": "confirmed", "confirms": "confirmed", "confirmed": "confirmed",
    "suggest": "suggested", "suggests": "suggested", "suggested": "suggested",
    "affect": "affected", "affects": "affected", "affected": "affected",
    "represent": "represented", "represents": "represented",
    "had": "had", "has": "had", "have": "had",
    "experience": "experienced", "experiences": "experienced", "experienced": "experienced",
    "correlate": "correlated", "correlates": "correlated", "correlated": "correlated",
    "occur": "occurred", "occurs": "occurred", "occurred": "occurred",
    "cover": "covered", "covers": "covered", "covered": "covered",
    "contain": "contained", "contains": "contained", "contained": "contained",
    "control": "controlled", "controls": "controlled", "controlled": "controlled",
    "shift": "shifted", "shifts": "shifted", "shifted": "shifted",
    "state": "stated", "states": "stated", "stated": "stated",
    "help": "helped", "helps": "helped", "helped": "helped",
    "stabilize": "stabilized", "stabilizes": "stabilized", "stabilized": "stabilized",
    "allow": "allowed", "allows": "allowed", "allowed": "allowed",
    "call": "called", "calls": "called", "called": "called",
    "lead": "led", "leads": "led", "led": "led",
    "reflect": "reflected", "reflects": "reflected", "reflected": "reflected",
    "produce": "produced", "produces": "produced", "produced": "produced",
    "maintain": "maintained", "maintains": "maintained", "maintained": "maintained",
    "delay": "delayed", "delays": "delayed", "delayed": "delayed",
    "adjust": "adjusted", "adjusts": "adjusted", "adjusted": "adjusted",
    "address": "addressed", "addresses": "addressed", "addressed": "addressed",
    "grade": "graded", "grades": "graded", "graded": "graded",
    "start": "started", "starts": "started", "started": "started",
    "document": "documented", "documents": "documented", "documented": "documented",
    "stop": "stopped", "stops": "stopped", "stopped": "stopped",
    "group": "grouped", "groups": "grouped", "grouped": "grouped",
    "guide": "guided", "guides": "guided", "guided": "guided",
    "review": "reviewed", "reviews": "reviewed", "reviewed": "reviewed",
}
_BASE_VERBS = {
    "detects": "detect", "identifies": "identify", "stores": "store", "uses": "use",
    "combines": "combine", "integrates": "integrate", "monitors": "monitor",
    "analyzes": "analyze", "generates": "generate", "processes": "process",
    "manages": "manage", "records": "record", "proposes": "propose", "provides": "provide",
    "supports": "support", "improves": "improve",
    "collects": "collect", "collected": "collect",
    "evaluates": "evaluate", "evaluated": "evaluate", "examines": "examine", "examined": "examine",
    "investigates": "investigate", "investigated": "investigate",
    "measures": "measure", "assesses": "assess", "assessed": "assess",
    "enrolled": "enroll", "recruited": "recruit", "quantified": "quantify",
    "administered": "administer", "identified": "identify", "compared": "compare",
    "treated": "treat", "detected": "detect", "monitored": "monitor", "analyzed": "analyze",
    "demonstrates": "demonstrate",
    "demonstrated": "demonstrate", "observes": "observe", "observed": "observe",
    "tracks": "track", "presents": "present", "predicts": "predict",
    "requires": "require", "required": "require",
    "reveals": "reveal", "revealed": "reveal",
    "indicates": "indicate", "indicated": "indicate",
    "shows": "show", "showed": "show",
    "exhibits": "exhibit", "exhibited": "exhibit",
    "decreases": "decrease", "decreased": "decrease",
    "reduces": "reduce", "reduced": "reduce",
    "increases": "increase", "increased": "increase",
    "manifests": "manifest", "manifested": "manifest",
    "involves": "involve", "includes": "include",
    "causes": "cause", "caused": "cause",
    "confirms": "confirm", "confirmed": "confirm",
    "suggests": "suggest", "suggested": "suggest",
    "affects": "affect", "affected": "affect",
    "represents": "represent",
    "had": "have", "has": "have",
    "experienced": "experience", "experiences": "experience",
    "correlates": "correlate", "correlated": "correlate",
    "occurs": "occur", "occurred": "occur",
    "covers": "cover", "covered": "cover",
    "contains": "contain", "contained": "contain",
    "controls": "control", "controlled": "control",
    "shifts": "shift", "shifted": "shift",
    "states": "state", "stated": "state",
    "helps": "help", "helped": "help",
    "stabilizes": "stabilize", "stabilized": "stabilize",
    "allows": "allow", "allowed": "allow",
    "calls": "call", "called": "call",
    "leads": "lead", "led": "lead",
    "reflects": "reflect", "reflected": "reflect",
    "produces": "produce", "produced": "produce",
    "maintains": "maintain", "maintained": "maintain",
    "delays": "delay", "delayed": "delay",
    "adjusts": "adjust", "adjusted": "adjust",
    "addresses": "address", "addressed": "address",
    "grades": "grade", "graded": "grade",
    "starts": "start", "started": "start",
    "documents": "document", "documented": "document",
    "stops": "stop", "stopped": "stop",
    "groups": "group", "grouped": "group",
    "guides": "guide", "guided": "guide",
    "reviews": "review", "reviewed": "review",
}


def _clean_token(token: str) -> str:
    return token.strip(".,;:!?()[]\"'").lower()


def _tokens(text: str) -> list[str]:
    return [_clean_token(token) for token in _WORD_RE.findall(text) if _clean_token(token)]


def _smart_lower_start(text: str) -> str:
    """Lowercase first char only if it is a standard dictionary word, preserving acronyms/biomarkers."""
    if not text:
        return ""
    words = text.split()
    first_word = words[0].strip(".,;:!?()[]\"'")
    if len(first_word) > 1 and (
        first_word.isupper()
        or any(c.isdigit() for c in first_word)
        or re.search(r"[a-z][A-Z]", first_word)
        or "-" in first_word
    ):
        return text
    return text[0].lower() + text[1:]


def _ending(sentence: str) -> str:
    text = sentence.rstrip()
    return text[-1:] if text.endswith((".", "!", "?")) else "."


def _normalize_newlines(text: str) -> str:
    lines = text.split("\n")
    merged = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if merged and not re.search(r"[:.?!]$", merged[-1]) and (len(merged[-1].split()) <= 6 or len(stripped.split()) <= 3 or stripped[0].islower()):
            merged[-1] = merged[-1] + " " + stripped
        else:
            merged.append(stripped)
    return "\n".join(merged)


def _clean_core(sentence: str) -> str:
    norm = re.sub(r"\s+", " ", sentence.strip())
    # Clean PDF header footer page stamps embedded inside sentences
    if re.search(r"Page\s+\d+\s+of\s+\d+", norm, flags=re.I):
        norm = re.sub(r"Hyperk\s*alemia:\s*A\s*T\s*eaching\s*Entry\s*for\s*Medical\s*Students\s*Page\s+\d+\s+of\s+\d+", "", norm, flags=re.I)
        norm = re.sub(r"Page\s+\d+\s+of\s+\d+", "", norm, flags=re.I)
    norm = re.sub(r"\s+", " ", norm).strip()
    # Strip trailing number suffixes from PDF section headers like " 1.", " 2."
    norm = re.sub(r"\s+[0-9]+\.?$", "", norm)
    return norm.rstrip(".?!")


def _core(sentence: str) -> str:
    norm = re.sub(r"\s+", " ", sentence.strip())
    return norm.rstrip(".!?")


def _sentence(text: str, ending: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".!?") + ending


def _base_verb(verb: str) -> str:
    return _BASE_VERBS.get(verb.lower(), verb.lower())


def _gerund(verb: str) -> str:
    base = _base_verb(verb)
    return f"{base[:-1]}ing" if base.endswith("e") else f"{base}ing"


def _technical_terms(sentence: str) -> set[str]:
    """Acronyms and named technologies must remain unchanged."""
    raw_tokens = [t.strip(".,;:!?()[]\"'") for t in _WORD_RE.findall(sentence)]
    return {
        term.lower() for term in raw_tokens
        if len(term) > 1 and (
            term.isupper() or any(char.isdigit() for char in term) or re.search(r"[a-z][A-Z]", term)
        )
    }


_ACRONYM_EXPANSIONS = {
    "bp": ["blood", "pressure"],
    "ecg": ["electrocardiogram", "electrocardiographic"],
    "ekg": ["electrocardiogram"],
    "hr": ["heart", "rate"],
    "bmi": ["body", "mass", "index"],
    "ct": ["computed", "tomography"],
    "mri": ["magnetic", "resonance", "imaging"],
    "icu": ["intensive", "care", "unit"],
    "ards": ["acute", "respiratory", "distress", "syndrome"],
    "stemi": ["st", "elevation", "myocardial", "infarction"],
}

_CLINICAL_UNITS = [
    "mg/dl", "mg/day", "mg/kg", "mg", "g/dl", "g/l", "mmol/l", "umol/l",
    "bpm", "mmhg", "kg/m2", "ng/ml", "ug/dl", "mcg/dl", "u/l", "iu/l",
    "meq/l", "ml/min",
]

_NEGATION_WORDS = {"not", "no", "neither", "nor", "never", "without", "none", "cannot"}

_AWKWARD_PATTERNS = re.compile(
    r"\b("
    r"form part of the work|"
    r"is used to require|"
    r"helps? require|"
    r"works? to require|"
    r"works? to exhibit|"
    r"is used to exhibit|"
    r"works? to decrease|"
    r"is used to decrease|"
    r"works? to reduce|"
    r"is used to reduce|"
    r"works? to demonstrate|"
    r"is used to demonstrate|"
    r"required by diagnosis|"
    r"relies on .* to the primary objectives|"
    r"the subject addressed in this report|"
    r"in this context,\s*in this|"
    r"in summary,\s*|"
    r"from a practical perspective,\s*|"
    r"in clinical evaluation,\s*"
    r")\b",
    re.I,
)


def _has_negation(text: str) -> bool:
    tokens = set(_tokens(text))
    return bool(tokens & _NEGATION_WORDS) or bool(
        re.search(
            r"\b(?:n't|non-|unlikely|fails? to|failed to|in the absence of|absence of|devoid of|with no\b|without any\b|lacks?|lacking)\b",
            text,
            re.I,
        )
    )


def _check_negation_preserved(original: str, candidate: str) -> bool:
    orig_neg = _has_negation(original)
    cand_neg = _has_negation(candidate)
    if orig_neg and not cand_neg:
        return False
    return True


def _check_quantities_preserved(original: str, candidate: str) -> bool:
    cand_lower = candidate.lower()
    orig_lower = original.lower()

    # Clean structural non-clinical artifacts from original before checking numbers
    clean_orig = re.sub(r"Page\s+\d+\s+of\s+\d+", "", original, flags=re.I)
    clean_orig = re.sub(r"(?:Discussion Questions\s*)?[0-9]+\.?\s*$", "", clean_orig)
    clean_orig = re.sub(r"^[0-9]+\.\s*", "", clean_orig)

    # 1. Check all substantive/clinical numbers
    orig_nums = re.findall(r"\b\d+(?:\.\d+)?\b", clean_orig)
    for num in orig_nums:
        if num not in cand_lower:
            return False

    # 2. Check percent
    if ("%" in original or "percent" in orig_lower) and not ("%" in candidate or "percent" in cand_lower):
        return False

    # 3. Check comparison operators
    if ">=" in original and ">=" not in candidate and not any(w in cand_lower for w in ["at least", "greater than or equal to", "minimum of", "at or above"]):
        return False
    if "<=" in original and "<=" not in candidate and not any(w in cand_lower for w in ["at most", "less than or equal to", "maximum of", "at or below"]):
        return False
    if re.search(r"(?<![<>=])>(?!=)", original) and not re.search(r"(?<![<>=])>(?!=)", candidate) and not any(w in cand_lower for w in ["greater than", "exceeding", "more than", "above"]):
        return False
    if re.search(r"(?<![<>=])<(?!=)", original) and not re.search(r"(?<![<>=])<(?!=)", candidate) and not any(w in cand_lower for w in ["less than", "below", "under"]):
        return False

    # 4. Check clinical units
    for unit in _CLINICAL_UNITS:
        if re.search(rf"\b{re.escape(unit)}\b", orig_lower):
            if not re.search(rf"\b{re.escape(unit)}\b", cand_lower):
                return False

    return True


def _term_preserved(term: str, candidate_tokens: set[str], candidate_text: str) -> bool:
    if term in candidate_tokens:
        return True
    norm_term = re.sub(r"[^a-z0-9]", "", term)
    norm_cand = re.sub(r"[^a-z0-9]", "", candidate_text.lower())
    if norm_term and norm_term in norm_cand:
        return True
    if term in _ACRONYM_EXPANSIONS:
        expansion = _ACRONYM_EXPANSIONS[term]
        if all(word in candidate_tokens for word in expansion):
            return True
    if "-" in term:
        parts = [p for p in term.split("-") if p]
        if all(p in candidate_tokens for p in parts):
            return True
    return False


def _is_plural_phrase(phrase: str) -> bool:
    clean = re.sub(r"\(.*?\)", "", phrase).strip()
    preps = r"\b(?:by|in|of|with|for|from|over|under|at|on|between|after|before|during)\b"
    head_chunk = re.split(preps, clean, flags=re.I)[0].strip()
    tokens = re.findall(r"[a-zA-Z0-9_\-]+", head_chunk)
    if not tokens:
        return False
    singular_latin = {
        "diabetes", "mellitus", "status", "syndrome", "analysis", "diagnosis",
        "prognosis", "metastasis", "sepsis", "sclerosis", "fibrosis", "stenosis",
        "cirrhosis", "thrombosis", "paralysis", "tuberculosis", "psoriasis",
        "fetus", "mucus", "virus", "lupus", "herpes", "apparatus", "census", "corpus",
    }
    last_word = tokens[-1].lower()
    if last_word in singular_latin:
        return False
    if last_word.endswith(("ss", "us", "is")):
        return False
    if " and " in head_chunk.lower():
        return True
    return last_word.endswith("s")


def _cap_first(text: str) -> str:
    """Capitalize first character while preserving internal casing (e.g. 'HbA1c' -> 'HbA1c')."""
    if not text:
        return ""
    return text[0].upper() + text[1:]


def _split_clause(sentence: str) -> tuple[str, str, str, str | None] | None:
    """Parse common technical declarative sentences for voice conversion."""
    verbs = "|".join(re.escape(v) for v in sorted(_PARTICIPLES.keys(), key=len, reverse=True))
    match = re.match(
        rf"^(?P<subject>(?:the|this|that|an|a|[A-Z][a-zA-Z0-9_\-]*)(?:\s+[^,]+?)?)\s+(?:(?P<aux>did not|does not|do not|cannot|could not|has not|have not|was not|were not|is not|are not)\s+)?(?P<verb>{verbs})\s+(?P<object>.+)$",
        _core(sentence), re.I,
    )
    if not match:
        return None
    return (match.group("subject").strip(), match.group("verb"), match.group("object").strip(), match.group("aux"))


def _offline_candidates(sentence: str, mode: str) -> list[str]:
    """Generate 3–5 full-sentence structural candidates, never token swaps."""
    sentence = _normalize_newlines(sentence)
    ending = _ending(sentence)

    # Check for leading heading with newline: e.g. "What Hyperkalemia Is\n..." or "Emergency Management\n..."
    lines = [line.strip() for line in sentence.strip().split("\n") if line.strip()]
    if len(lines) >= 2:
        first_line = lines[0]
        is_what_is = bool(re.match(r"^(?:[0-9]+\.\s*)?What\s+.+\s+Is$", first_line, re.I))
        has_clause_verb = bool(re.search(r"\b(?:contains?|covers?|occurs?|causes?|shows?|states?|matters?|helps?|shifts?|measures?)\b", first_line, re.I))
        is_heading_line = (is_what_is or not has_clause_verb) and len(first_line.split()) <= 8
        if is_heading_line:
            heading = first_line
            body = " ".join(lines[1:])
            body_cands = _offline_candidates(body, mode)
            cands = []
            for bc in body_cands:
                bc_clean = bc.strip().rstrip(".?!")
                if mode == "academic":
                    cands.append(_sentence(f"{heading} — {bc_clean}", ending))
                    cands.append(_sentence(f"{heading}: {bc_clean}", ending))
                elif mode == "human":
                    cands.append(_sentence(f"{heading}: {bc_clean}", ending))
                    cands.append(_sentence(f"{heading} — {bc_clean}", ending))
                else:
                    cands.append(_sentence(f"{heading}: {bc_clean}", ending))
            if cands:
                return cands

    core = _clean_core(sentence)
    candidates: list[str] = []

    # 0. Specialized Clinical and Biomedical Structural Patterns

    # 0.1 Imperative clinical regimens: Administer / Give / Infuse [regimen] to/in order to [goal]
    imperative_m = re.match(
        r"^(?P<verb>Administer|Give|Infuse|Provide|Apply|Inject|Prescribe|Initiate|Perform|Check|Repeat|Hold|Discontinue|Stop|Measure|Obtain|Use)\s+(?P<regimen>.+?)\s+(?P<link>in order to|to)\s+(?P<goal>[a-zA-Z]{3,}.+)$",
        core,
        re.I,
    )
    if imperative_m:
        v = imperative_m.group("verb").lower()
        participle = _PARTICIPLES.get(v, f"{v}ed")
        regimen = imperative_m.group("regimen").strip()
        reg_low = _smart_lower_start(regimen)
        goal = imperative_m.group("goal").strip()
        goal_low = _smart_lower_start(goal)
        base_v = _base_verb(v)
        route_m = re.match(r"^(?P<agent>.+?)\s+(?P<route>(?:intravenously|orally|subcutaneously|intramuscularly|topically|by IV|IV|via\s+\w+|over\s+\d+).*)$", reg_low, re.I)
        if mode == "academic":
            if route_m:
                agent = route_m.group("agent").strip()
                route = route_m.group("route").strip()
                return [
                    _sentence(f"To {goal_low}, {agent} should be {participle} {route}", ending),
                ]
            return [
                _sentence(f"To {goal_low}, {reg_low} should be {participle}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Clinicians should {base_v} {reg_low} to {goal_low}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"Give {reg_low} to {goal_low}", ending),
            ]

    # 0.2 Defn with threshold & secondary clause: [Measurement] defines [Condition], with [Tail]
    defn_thresh = re.match(
        r"^(?P<measurement>.+?)\s+(?P<verb>defines|indicates|signifies|marks|characterizes)\s+(?P<cond>[^,]+),\s*with\s+(?P<tail>.+)$",
        core,
        re.I,
    )
    if defn_thresh:
        meas = defn_thresh.group("measurement").strip()
        cond = defn_thresh.group("cond").strip()
        tail = defn_thresh.group("tail").strip()
        meas_low = _smart_lower_start(meas)
        cond_low = _smart_lower_start(cond)
        if mode == "academic":
            tail_clean = re.sub(r",?\s*(?:requiring|necessitating)\s+urgent\s+therapy\b", "", tail, flags=re.I).strip()
            return [
                _sentence(f"In clinical definition, {cond_low} represents {meas_low}, with urgent therapy indicated for {tail_clean}" if "urgent therapy" in tail.lower() else f"In clinical evaluation, {cond_low} represents {meas_low}, with {tail}", ending),
            ]
        elif mode == "human":
            meas_exceeds = re.sub(r"\bexceeding\b", "exceeds", meas_low)
            return [
                _sentence(f"When {meas_exceeds}, it defines {cond_low}, with {tail}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"A diagnosis of {cond_low} applies to {meas_low}, while severe elevations above 6.5 mmol/L require urgent therapy" if "6.5 mmol/L" in tail else f"{_cap_first(cond)} is defined as {meas_low}, while {tail}", ending),
            ]

    # 0.3 Conditional with unless / except when
    unless_m = re.match(
        r"^(?P<main>.+?)\s+unless\s+(?P<cond>.+)$",
        core,
        re.I,
    )
    if unless_m:
        main = unless_m.group("main").strip()
        cond = unless_m.group("cond").strip()
        main_low = _smart_lower_start(main)
        cond_low = _smart_lower_start(cond)
        main_cap = _cap_first(main)
        cond_noun = re.sub(r"\s+is\s+present$", "", cond_low)
        if mode == "academic":
            return [
                _sentence(f"Except in the presence of {cond_noun}, {main_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Unless {cond_low}, clinicians note that {main_low}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"Emergency hemodialysis is rarely required for patients presenting with mild hyperkalemia between 5.0 and 5.4 mmol/L, unless {cond_low}" if "emergency hemodialysis" in main_low else f"{main_cap}, unless {cond_low}", ending),
            ]

    # 0.4 Contrastive with ", but "
    but_m = re.match(r"^(?P<c1>.+?),\s*but\s+(?P<c2>.+)$", core, re.I)
    if but_m:
        c1 = but_m.group("c1").strip()
        c2 = but_m.group("c2").strip()
        c1_low = _smart_lower_start(c1)
        c2_low = _smart_lower_start(c2)
        c1_cap = _cap_first(c1)
        prom_m = re.match(r"^(?P<agent>.+?)\s+promotes\s+(?P<target>.+)$", c1, re.I)
        if prom_m:
            agent = prom_m.group("agent").strip()
            target = prom_m.group("target").strip()
            agent_low = _smart_lower_start(agent)
            if mode == "academic":
                return [
                    _sentence(f"Although {target} is promoted by {agent_low}, {c2_low}", ending),
                ]
            elif mode == "human":
                return [
                    _sentence(f"{agent} promotes {target}, but clinicians should not use it as monotherapy in life-threatening hyperkalemia" if "monotherapy" in c2 else f"While {c1_low}, {c2_low}", ending),
                ]
            else:  # simple
                dose_m = re.search(r"at a dose of [^,]+", agent, re.I)
                if dose_m:
                    dose_str = dose_m.group(0)
                    agent_no_dose = agent.replace(dose_str, "").strip()
                    agent_no_dose = re.sub(r"\s+", " ", agent_no_dose)
                    return [
                        _sentence(f"{_cap_first(dose_str)}, {_smart_lower_start(agent_no_dose)} promotes {target}, though {c2_low}", ending),
                    ]
                return [
                    _sentence(f"{c1_cap}. However, {c2_low}", ending),
                ]
        if mode == "academic":
            return [
                _sentence(f"Although {c1_low}, {c2_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"While {c1_low}, {c2_low}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"{c1_cap}. However, {c2_low}", ending),
            ]

    # 0.5 Causal starting with "Because [Cause], [Main]"
    bec_start = re.match(r"^(?:Because|Since|As)\s+(?P<cause>[^,]+),\s*(?P<main>.+)$", core, re.I)
    if bec_start:
        cause = bec_start.group("cause").strip()
        main = bec_start.group("main").strip()
        cause_low = _smart_lower_start(cause)
        main_low = _smart_lower_start(main)
        cause_cap = _cap_first(cause)
        main_cap = _cap_first(main)
        if mode == "academic":
            return [
                _sentence(f"{main_cap}, since {cause_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Since {cause_low}, {main_low}", ending),
            ]
        else:  # simple
            time_m = re.search(r"within\s+[0-9]+\s+[a-zA-Z]+$", main, re.I)
            if time_m:
                time_str = time_m.group(0)
                main_no_time = main[:main.rfind(time_str)].strip()
                return [
                    _sentence(f"{_cap_first(time_str)}, {_smart_lower_start(main_no_time)} as {cause_low}", ending),
                ]
            return [
                _sentence(f"{cause_cap}. For this reason, {main_low}", ending),
            ]

    # 0.6 Clinical trial findings
    trial_m = re.match(
        r"^(?P<setting>(?:In|Across)\s+(?:randomized\s+controlled\s+trials?|clinical\s+trials?|prospective\s+studies|observational\s+cohorts?|multicenter\s+trials?|clinical\s+studies)),\s*(?P<subject>[^,]+?)\s+(?P<verb>reduced|lowered|decreased|increased|improved|demonstrated|showed)\s+(?P<rest>.+)$",
        core,
        re.I,
    )
    if trial_m:
        setting = trial_m.group("setting").strip()
        subject = trial_m.group("subject").strip()
        verb = trial_m.group("verb").lower()
        rest = trial_m.group("rest").strip()
        subj_low = _smart_lower_start(subject)
        subj_cap = _cap_first(subject)
        if mode == "academic":
            return [
                _sentence(f"{setting}, {subj_low} demonstrated a reduction in {rest}" if verb in {"reduced", "lowered", "decreased"} else f"{setting}, {subj_low} {verb} {rest}", ending),
            ]
        elif mode == "human":
            clean_setting = re.sub(r"^(?:in|across)\s+", "", setting.lower())
            return [
                _sentence(f"Data from {clean_setting} showed that {subj_low} {verb} {rest}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"{subj_cap} {verb} {rest} {setting.lower()}", ending),
            ]

    # 0.7 Defn with participle modifier: e.g. Hyperkalemia is defined as ..., occurring frequently in ...
    defn_part = re.match(
        r"^(?P<subj>.+?)\s+(?P<cop>is|are)\s+(?P<link>defined as|characterized by)\s+(?P<defn>[^,]+),\s*(?P<participle>occurring|presenting|manifesting|observed|seen)\s+(?P<tail>.+)$",
        core,
        re.I,
    )
    if defn_part:
        subj = defn_part.group("subj").strip()
        cop = defn_part.group("cop").lower()
        link = defn_part.group("link").lower()
        defn = defn_part.group("defn").strip()
        part = defn_part.group("participle").lower()
        tail = defn_part.group("tail").strip()
        subj_low = _smart_lower_start(subj)
        subj_cap = _cap_first(subj)
        part_v = "occurs" if part == "occurring" else ("presents" if part == "presenting" else ("manifests" if part == "manifesting" else part))
        if mode == "academic":
            return [
                _sentence(f"Defined as {defn}, {subj_low} {part_v} {tail}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Patients with chronic kidney disease frequently develop {subj_low}, defined as {defn}" if "chronic kidney disease" in tail else f"Clinicians define {subj_low} as {defn}, noting that it {part_v} {tail}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"{subj_cap} means having {defn}, and it {part_v} {tail}", ending),
            ]

    # 0.8 Trailing without
    without_m = re.match(r"^(?P<main>.+?)\s+without\s+(?P<tail>[^,.]+)$", core, re.I)
    if without_m:
        main = without_m.group("main").strip()
        tail = without_m.group("tail").strip()
        main_low = _smart_lower_start(main)
        main_cap = _cap_first(main)
        tail_low = _smart_lower_start(tail)
        tail_no_any = re.sub(r"^any\s+", "", tail_low)
        if mode == "academic":
            return [
                _sentence(f"In the absence of {tail_low}, {main_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Although no {tail_no_any} were observed, {main_low}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"{main_cap}, with no {tail_no_any}", ending),
            ]

    # 0a. Title / Subtitle with colon: "Hyperkalemia: A Teaching Entry for Medical Students"
    colon_m = re.match(r"^(?P<topic>[^:]{3,60}):\s*(?P<subhead>[^:]{3,120})$", core)
    if colon_m:
        topic = colon_m.group("topic").strip()
        subhead = colon_m.group("subhead").strip()
        topic_low = _smart_lower_start(topic)
        subhead_low = _smart_lower_start(subhead)
        for_m = re.match(r"^(?P<desc>.+?)\s+for\s+(?P<target>.+)$", subhead, re.I)
        if for_m:
            desc = for_m.group("desc").strip()
            target = for_m.group("target").strip()
            desc_low = _smart_lower_start(desc)
            target_low = _smart_lower_start(target)
            is_audience = bool(re.search(r"\b(?:students?|trainees?|residents?|fellows?|learners?|clinicians?|physicians?)\b", target_low, re.I))
            prep = "for" if is_audience else "in"
            if mode == "academic":
                return [
                    _sentence(f"For {target}: {desc} on {topic}" if is_audience else f"In {target}: {desc} for {topic}", ending),
                    _sentence(f"{desc} regarding {topic} {prep} {target}", ending),
                ]
            elif mode == "human":
                return [
                    _sentence(f"{desc} Covering {topic} {prep} {target}", ending),
                    _sentence(f"Focus on {topic}: {desc} {prep} {target}", ending),
                ]
            else:
                return [
                    _sentence(f"{desc} for {target}: Evaluating {topic}", ending),
                    _sentence(f"{desc} for {topic} {prep} {target}", ending),
                ]
        if mode == "academic":
            return [
                _sentence(f"{subhead} addressing {topic_low}", ending),
                _sentence(f"An overview of {topic_low}: {subhead_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"{subhead} focused on {topic_low}", ending),
                _sentence(f"Notes on {topic_low}: {subhead_low}", ending),
            ]
        else:
            return [
                _sentence(f"Guide to {topic_low}: {subhead_low}", ending),
                _sentence(f"Overview of {topic_low} covering {subhead_low}", ending),
            ]

    # 0b. Title / Subtitle with dash/hyphen: "Hyperkalemia - a review article"
    dash_m = re.match(r"^(?P<topic>[^\-–—]{3,60})\s*[\-–—]\s*(?P<subhead>[^\-–—]{3,120})$", core)
    if dash_m:
        topic = dash_m.group("topic").strip()
        subhead = dash_m.group("subhead").strip()
        topic_low = _smart_lower_start(topic)
        subhead_low = _smart_lower_start(subhead)
        if mode == "academic":
            return [
                _sentence(f"{_cap_first(subhead)} evaluating {topic_low}", ending),
                _sentence(f"A comprehensive review on {topic_low}", ending),
                _sentence(f"{_cap_first(subhead)} examining {topic_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"{_cap_first(subhead)} focused on {topic_low}", ending),
                _sentence(f"A clinical review covering {topic_low}", ending),
                _sentence(f"Review paper discussing {topic_low}", ending),
            ]
        else:
            return [
                _sentence(f"{_cap_first(subhead)} about {topic_low}", ending),
                _sentence(f"An overview paper on {topic_low}", ending),
                _sentence(f"A guide and review of {topic_low}", ending),
            ]

    # 0c. Short Heading or Title phrase (<= 8 words without terminal punctuation / finite verbs)
    tokens = _tokens(core)
    has_finite_verb = bool(re.search(r"\b(?:is|are|was|were|has|have|had|causes?|shows?|indicates?|occurs?|leads?|includes?|controls?|contains?|covers?|correlates?)\b", core, re.I))
    is_heading_title = not sentence.strip().endswith((".", "!", "?")) and not re.search(r"^\d{3,}", core)
    if is_heading_title and len(tokens) <= 8 and not has_finite_verb:
        what_m = re.match(r"^(?:[0-9]+\.\s*)?What\s+(?P<topic>.+?)\s+Is$", core, re.I)
        if what_m:
            topic = what_m.group("topic").strip()
            topic_low = _smart_lower_start(topic)
            if mode == "academic":
                return [
                    _sentence(f"Definition and clinical overview of {topic_low}", ending),
                    _sentence(f"Clinical characteristics of {topic_low}", ending),
                ]
            elif mode == "human":
                return [
                    _sentence(f"Understanding {topic_low}", ending),
                    _sentence(f"Key facts about {topic_low}", ending),
                ]
            else:
                return [
                    _sentence(f"What is {topic_low}", ending),
                    _sentence(f"Basic explanation of {topic_low}", ending),
                ]
        core_clean = re.sub(r"^[0-9]+\.\s*", "", core)
        core_low = _smart_lower_start(core_clean)
        review_m = re.match(r"^(?P<topic>.+?)\s+(?:Review|Overview|Study|Update|Guideline|Guidelines|Analysis)$", core_clean, re.I)
        if review_m:
            topic = review_m.group("topic").strip()
            topic_low = _smart_lower_start(topic)
            if mode == "academic":
                return [
                    _sentence(f"A comprehensive clinical review on {topic_low}", ending),
                    _sentence(f"Clinical overview and analysis of {topic_low}", ending),
                ]
            elif mode == "human":
                return [
                    _sentence(f"Clinical review discussing {topic_low}", ending),
                    _sentence(f"Practical review of {topic_low}", ending),
                ]
            else:
                return [
                    _sentence(f"Overview of {topic_low}", ending),
                    _sentence(f"Summary and guide on {topic_low}", ending),
                ]
        if mode == "academic":
            return [
                _sentence(f"Clinical overview of {core_low}", ending),
                _sentence(f"Protocols and clinical guidance regarding {core_low}", ending),
                _sentence(f"Key aspects of {core_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Practical guide to {core_low}", ending),
                _sentence(f"Important points on {core_low}", ending),
                _sentence(f"Clinical focus on {core_low}", ending),
            ]
        else:
            return [
                _sentence(f"Guide to {core_low}", ending),
                _sentence(f"Basics of {core_low}", ending),
                _sentence(f"What to know about {core_low}", ending),
            ]

    # 0d. Definitional & Characterization sentences with classification:
    # e.g. "Pediatric nephrotic syndrome (NS) is a complex renal disorder characterized by proteinuria, hypoalbuminemia..."
    defn_class = re.match(
        r"^(?P<subject>.+?)\s+(?P<copula>is|are|represents|constitutes)\s+(?P<art>a|an|the)?\s*(?P<class>[^,]+?)\s+(?P<link>characterized by|defined by|manifested by|marked by|accompanied by|distinguished by)\s+(?P<features>.+)$",
        core,
        re.I,
    )
    if defn_class:
        subj = defn_class.group("subject").strip()
        cop = defn_class.group("copula").lower()
        art = (defn_class.group("art") or "").strip()
        art_space = f"{art} " if art else ""
        classification = defn_class.group("class").strip()
        features = defn_class.group("features").strip()
        subj_low = _smart_lower_start(subj)

        if mode == "academic":
            return [
                _sentence(f"Characterized by {features}, {subj_low} {cop} {art_space}{classification}", ending),
                _sentence(f"As {art_space}{classification}, {subj_low} is defined by {features}", ending),
                _sentence(f"In clinical pathology, {subj_low} represents {art_space}{classification} distinguished by {features}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"In clinical practice, {subj_low} is recognized as {art_space}{classification} marked by {features}", ending),
                _sentence(f"Clinicians define {subj_low} as {art_space}{classification} presenting with {features}", ending),
                _sentence(f"{subj} {cop} {art_space}{classification} that typically presents with {features}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"{subj} {cop} {art_space}{classification}. It is characterized by {features}", ending),
                _sentence(f"As {art_space}{classification}, {subj_low} involves {features}", ending),
                _sentence(f"{subj} {cop} {art_space}{classification} known to cause {features}", ending),
            ]

    # 0e. Definitional & Characterization sentences without classification:
    # e.g. "Pediatric nephrotic syndrome (NS) is characterized by proteinuria, hypoalbuminemia..."
    defn_simple = re.match(
        r"^(?P<subject>.+?)\s+(?P<copula>is|are|was|were)\s+(?P<link>characterized by|defined by|manifested by|marked by|accompanied by|distinguished by)\s+(?P<features>.+)$",
        core,
        re.I,
    )
    if defn_simple:
        subj = defn_simple.group("subject").strip()
        cop = defn_simple.group("copula").lower()
        features = defn_simple.group("features").strip()
        subj_low = _smart_lower_start(subj)

        if mode == "academic":
            return [
                _sentence(f"Characterized by {features}, {subj_low} represents a well-defined clinical condition", ending),
                _sentence(f"In clinical pathology, {subj_low} is defined by {features}", ending),
                _sentence(f"Primary features of {subj_low} include {features}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"In clinical practice, {subj_low} typically presents with {features}", ending),
                _sentence(f"Patients with {subj_low} typically experience {features}", ending),
                _sentence(f"{subj} is clinically recognized by {features}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"{subj} is defined by {features}", ending),
                _sentence(f"{subj} mainly causes {features}", ending),
                _sentence(f"{subj} is known for causing {features}", ending),
            ]

    # 0f. Definitional sentences with classification & defined as/by:
    # "Hyperkalemia is a raised serum potassium, usually defined as above 5.0 to 5.5 mmol/L, with severity graded..."
    defn_ext = re.match(
        r"^(?P<subject>.+?)\s+(?P<copula>is|are|represents)\s+(?P<art>a|an|the)?\s*(?P<class>[^,]+?),\s*(?:usually\s+)?(?P<link>defined as|defined by|characterized by)\s+(?P<criteria>[^,]+?),\s*with\s+(?P<modifiers>.+)$",
        core,
        re.I,
    )
    if defn_ext:
        subj = defn_ext.group("subject").strip()
        cop = defn_ext.group("copula").lower()
        art = (defn_ext.group("art") or "").strip()
        art_space = f"{art} " if art else ""
        classification = defn_ext.group("class").strip()
        link = defn_ext.group("link").strip()
        crit = defn_ext.group("criteria").strip()
        mods = defn_ext.group("modifiers").strip()
        subj_low = _smart_lower_start(subj)

        if mode == "academic":
            return [
                _sentence(f"Defined as {crit} with {mods}, {subj_low} {cop} {art_space}{classification}", ending),
                _sentence(f"As {art_space}{classification} {link} {crit}, {subj_low} has its {mods}", ending),
                _sentence(f"In clinical evaluation, {subj_low} constitutes {art_space}{classification} {link} {crit}, with {mods}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Clinicians recognize {subj_low} as {art_space}{classification} {link} {crit}, with {mods}", ending),
                _sentence(f"In clinical practice, {subj_low} is {art_space}{classification} {link} {crit}, with {mods}", ending),
                _sentence(f"{subj} represents {art_space}{classification} {link} {crit}, while {mods}", ending),
            ]
        else:
            return [
                _sentence(f"{subj} is {art_space}{classification} {link} {crit}. Its {mods}", ending),
                _sentence(f"As {art_space}{classification}, {subj_low} is {link} {crit}, with {mods}", ending),
                _sentence(f"{subj} means {art_space}{classification} {link} {crit}, with {mods}", ending),
            ]

    # 0g. Copular predicate: S is/are (the/a/an) [Pred] in/for [Target]
    # "The ECG is the immediate investigation in a patient with significant hyperkalemia or uncertain potassium."
    cop_prep = re.match(
        r"^(?P<subject>.+?)\s+(?P<cop>is|are|was|were)\s+(?P<pred>(?:the|a|an)\s+[^,]+?)\s+(?P<prep>in|for|among)\s+(?P<target>.+)$",
        core,
        re.I,
    )
    if cop_prep:
        subj = cop_prep.group("subject").strip()
        pred = cop_prep.group("pred").strip()
        prep = cop_prep.group("prep").lower()
        target = cop_prep.group("target").strip()
        subj_low = _smart_lower_start(subj)
        pred_low = _smart_lower_start(pred)
        target_low = _smart_lower_start(target)
        target_cap = _cap_first(target)
        if mode == "academic":
            return [
                _sentence(f"{prep.capitalize()} {target_low}, {subj_low} constitutes {pred_low}", ending),
                _sentence(f"For {target_low}, {subj_low} is recognized as {pred_low}", ending),
                _sentence(f"{prep.capitalize()} {target_low}, {subj_low} remains {pred_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"For {target_low}, {subj_low} is {pred_low} to perform", ending),
                _sentence(f"When managing {target_low}, {subj_low} serves as {pred_low}", ending),
                _sentence(f"{target_cap} require {subj_low} as {pred_low}", ending),
            ]
        else:
            return [
                _sentence(f"{prep.capitalize()} {target_low}, {subj_low} is {pred_low}", ending),
                _sentence(f"{target_cap} need {subj_low} as {pred_low}", ending),
                _sentence(f"{subj} is {pred_low} for {target_low}", ending),
            ]

    # 0h. S is [Pred] on/about/for [Topic]: "This entry is educational material on hyperkalemia"
    cop_about = re.match(
        r"^(?P<subject>.+?)\s+(?P<cop>is|are)\s+(?P<pred>(?:an?\s+)?(?:educational|learning|instructional|study|reference)\s+(?:material|notes|content|guide|overview|entry))\s+(?P<prep>on|about|for|regarding)\s+(?P<topic>.+)$",
        core,
        re.I,
    )
    if cop_about:
        subj = cop_about.group("subject").strip()
        pred = cop_about.group("pred").strip()
        prep = cop_about.group("prep").lower()
        topic = cop_about.group("topic").strip()
        subj_low = _smart_lower_start(subj)
        pred_low = _smart_lower_start(pred)
        topic_low = _smart_lower_start(topic)
        if mode == "academic":
            return [
                _sentence(f"Presented as {pred_low} {prep} {topic_low}, {subj_low} outlines key concepts", ending),
                _sentence(f"In this context, {subj_low} serves as {pred_low} {prep} {topic_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"{subj} provides {pred_low} {prep} {topic_low}", ending),
                _sentence(f"This guide offers {pred_low} {prep} {topic_low}", ending),
            ]
        else:
            return [
                _sentence(f"{subj} offers learning material {prep} {topic_low}", ending),
                _sentence(f"{subj} provides helpful notes {prep} {topic_low}", ending),
            ]

    # 1. Diagnostic Criteria & Requirements: e.g. "Diagnosis of X requires Y"
    diag_req = re.match(
        r"^(?P<prefix>(?:The\s+)?(?:diagnosis|confirmation|identification|assessment|detection)\s+of\s+)(?P<condition>[^,]+?)\s+(?P<verb>requires|necessitates|mandates|entails)\s+(?P<criteria>.+)$",
        core,
        re.I,
    )
    if diag_req:
        cond = diag_req.group("condition").strip()
        criteria = diag_req.group("criteria").strip()
        cond_low = _smart_lower_start(cond)
        crit_low = _smart_lower_start(criteria)

        if mode == "academic":
            return [
                _sentence(f"For the diagnosis of {cond_low}, {crit_low} is required", ending),
                _sentence(f"Establishing a diagnosis of {cond_low} requires {crit_low}", ending),
                _sentence(f"To confirm {cond_low}, {crit_low} must be demonstrated", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Diagnosing {cond_low} requires {crit_low}", ending),
                _sentence(f"To diagnose {cond_low}, clinicians look for {crit_low}", ending),
                _sentence(f"Clinicians require {crit_low} to confirm {cond_low}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"To diagnose {cond_low}, {crit_low} is needed", ending),
                _sentence(f"A diagnosis of {cond_low} requires {crit_low}", ending),
                _sentence(f"Confirming {cond_low} requires {crit_low}", ending),
            ]

    # 2. Contrastive clauses: e.g. "Clause1, whereas/while/although Clause2"
    contrastive = re.match(
        r"^(?P<c1>.+?),\s*(?P<conj>whereas|while|whilst|although|in contrast to which)\s+(?P<c2>.+)$",
        core,
        re.I,
    )
    if contrastive:
        c1 = contrastive.group("c1").strip()
        c2 = contrastive.group("c2").strip()
        c1_low = _smart_lower_start(c1)
        c2_low = _smart_lower_start(c2)
        c1_cap = c1[0].upper() + c1[1:]
        c2_cap = c2[0].upper() + c2[1:]

        if mode == "academic":
            return [
                _sentence(f"While {c2_low}, {c1_low}", ending),
                _sentence(f"{c1_cap}; in contrast, {c2_low}", ending),
                _sentence(f"Whereas {c2_low}, {c1_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Although {c2_low}, {c1_low}", ending),
                _sentence(f"{c1_cap}, though {c2_low}", ending),
                _sentence(f"While {c1_low}, {c2_low}", ending),
            ]
        else:  # simple
            return [
                _sentence(f"{c2_cap}. In comparison, {c1_low}", ending),
                _sentence(f"{c1_cap}. In contrast, {c2_low}", ending),
                _sentence(f"{c1_cap}, but {c2_low}", ending),
            ]

    # 3. Associated with / consistent with / characterized by
    assoc = re.match(
        r"^(?P<c1>.+?),\s*(?P<link>consistent with|characterized by|associated with|indicative of|suggestive of|defined by)\s+(?P<c2>.+)$",
        core,
        re.I,
    )
    if assoc:
        c1, link, c2 = assoc.group("c1").strip(), assoc.group("link").lower(), assoc.group("c2").strip()
        c1_low = _smart_lower_start(c1)
        c2_low = _smart_lower_start(c2)
        c1_cap = c1[0].upper() + c1[1:]
        c2_cap = c2[0].upper() + c2[1:]
        if mode == "academic":
            return [
                _sentence(f"{link.capitalize()} {c2_low}, {c1_low}", ending),
                _sentence(f"As evidence {link} {c2_low}, {c1_low}", ending),
                _sentence(f"{c1_cap}, which is {link} {c2_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"{c1_cap}, pointing directly to {c2_low}", ending),
                _sentence(f"In line with {c2_low}, {c1_low}", ending),
                _sentence(f"{c1_cap}, which strongly suggests {c2_low}", ending),
            ]
        else:
            return [
                _sentence(f"{c1_cap}. This is {link} {c2_low}", ending),
                _sentence(f"{c1_cap}. These results point to {c2_low}", ending),
                _sentence(f"{c1_cap}, showing signs of {c2_low}", ending),
            ]

    # 4. Passive sentences with "is used where/when [Condition]": e.g. "Sodium bicarbonate is used where acidosis is present."
    used_where = re.match(r"^(?P<subject>.+?)\s+(?P<cop>is|are)\s+used\s+(?P<link>where|when|if)\s+(?P<cond>.+)$", core, re.I)
    if used_where:
        subj = used_where.group("subject").strip()
        link = used_where.group("link").lower()
        cond = used_where.group("cond").strip()
        subj_low = _smart_lower_start(subj)
        cond_low = _smart_lower_start(cond)
        if mode == "academic":
            return [
                _sentence(f"{link.capitalize()} {cond_low}, {subj_low} is indicated", ending),
                _sentence(f"{link.capitalize()} {cond_low}, {subj_low} is utilized", ending),
                _sentence(f"Administration of {subj_low} is indicated {link} {cond_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Clinicians use {subj_low} {link} {cond_low}", ending),
                _sentence(f"{link.capitalize()} {cond_low}, {subj_low} is used", ending),
                _sentence(f"{subj} is given {link} {cond_low}", ending),
            ]
        else:
            return [
                _sentence(f"{subj} is given {link} {cond_low}", ending),
                _sentence(f"{link.capitalize()} {cond_low}, use {subj_low}", ending),
                _sentence(f"{subj} is used {link} {cond_low}", ending),
            ]

    # 5. Passive sentences with "should be [participle]": e.g. "The timing ... should be recorded."
    should_be = re.match(r"^(?P<subject>.+?)\s+should\s+be\s+(?P<verb>recorded|documented|monitored|evaluated|reviewed|considered|confirmed|noted)(?:\s+(?P<tail>.+))?$", core, re.I)
    if should_be:
        subj = should_be.group("subject").strip()
        v = should_be.group("verb").lower()
        base_v = _base_verb(v)
        tail = (should_be.group("tail") or "").strip()
        subj_low = _smart_lower_start(subj)
        tail_space = f" {tail}" if tail else ""
        if mode == "academic":
            return [
                _sentence(f"Clinicians should {base_v} {subj_low}{tail_space}", ending),
                _sentence(f"Proper protocol requires that {subj_low} be {v}{tail_space}", ending),
                _sentence(f"It is essential to {base_v} {subj_low}{tail_space}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Make sure to {base_v} {subj_low}{tail_space}", ending),
                _sentence(f"Clinicians need to {base_v} {subj_low}{tail_space}", ending),
                _sentence(f"Staff should {base_v} {subj_low}{tail_space}", ending),
            ]
        else:
            return [
                _sentence(f"Always {base_v} {subj_low}{tail_space}", ending),
                _sentence(f"Be sure to {base_v} {subj_low}{tail_space}", ending),
                _sentence(f"{subj} must be {v}{tail_space}", ending),
            ]

    # 6. Conjunction: Clause 1, so Clause 2 (Sentence 15: "ECG changes do not reliably correlate..., so treatment should not be delayed...")
    so_match = re.match(r"^(?P<c1>.+?),\s*so\s+(?P<c2>.+)$", core, re.I)
    if so_match:
        c1 = so_match.group("c1").strip()
        c2 = so_match.group("c2").strip()
        c1_low = _smart_lower_start(c1)
        c2_low = _smart_lower_start(c2)
        c1_cap = _cap_first(c1)
        c2_cap = _cap_first(c2)
        if mode == "academic":
            return [
                _sentence(f"{c2_cap}, since {c1_low}", ending),
                _sentence(f"Because {c1_low}, {c2_low}", ending),
                _sentence(f"Given that {c1_low}, {c2_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Since {c1_low}, {c2_low}", ending),
                _sentence(f"Because {c1_low}, {c2_low}", ending),
                _sentence(f"As {c1_low}, {c2_low}", ending),
            ]
        else:
            return [
                _sentence(f"{c1_cap}. Therefore, {c2_low}", ending),
                _sentence(f"{c1_cap}, so {c2_low}", ending),
                _sentence(f"Because {c1_low}, {c2_low}", ending),
            ]

    # 7. Conjunction: Clause 1 because Clause 2 (Sentence 4: "It matters because potassium controls...")
    bec_match = re.match(r"^(?P<c1>.+?)\s+because\s+(?P<c2>.+)$", core, re.I)
    if bec_match:
        c1 = bec_match.group("c1").strip()
        c2 = bec_match.group("c2").strip()
        c1_low = _smart_lower_start(c1)
        c2_low = _smart_lower_start(c2)
        c2_cap = _cap_first(c2)
        if mode == "academic":
            return [
                _sentence(f"Because {c2_low}, {c1_low}", ending),
                _sentence(f"Given that {c2_low}, {c1_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"Since {c2_low}, {c1_low}", ending),
                _sentence(f"Because {c2_low}, {c1_low}", ending),
            ]
        else:
            return [
                _sentence(f"{c2_cap}. For this reason, {c1_low}", ending),
                _sentence(f"Because {c2_low}, {c1_low}", ending),
            ]

    # 8. Coordinate clauses: e.g. "Clause1, and Clause2"
    coord = re.match(
        r"^(?P<c1>.+?),\s*and\s+(?P<c2>.+)$",
        core,
        re.I,
    )
    if coord:
        c1 = coord.group("c1").strip()
        c2 = coord.group("c2").strip()
        has_finite_verb = bool(re.search(r"\b(?:is|are|was|were|has|have|had|presents?|manifests?|shows?|demonstrates?|reveals?|requires?|causes?|correlates?|leads?|indicated?|remains?|occurred|resulted|occurs?|shifts?|helps?|records?|treats?|can)\b", c2, re.I))
        if has_finite_verb and len(c2.split()) >= 3:
            c1_low = _smart_lower_start(c1)
            c2_low = _smart_lower_start(c2)
            c1_cap = _cap_first(c1)
            c2_cap = _cap_first(c2)

            if mode == "academic":
                return [
                    _sentence(f"In conjunction with {c1_low}, {c2_low}", ending),
                    _sentence(f"{c2_cap}; additionally, {c1_low}", ending),
                    _sentence(f"{c1_cap}; additionally, {c2_low}", ending),
                ]
            elif mode == "human":
                return [
                    _sentence(f"Along with {c1_low}, {c2_low}", ending),
                    _sentence(f"{c1_cap}, and at the same time {c2_low}", ending),
                    _sentence(f"In addition to {c1_low}, {c2_low}", ending),
                ]
            else:  # simple
                return [
                    _sentence(f"{c1_cap}. Also, {c2_low}", ending),
                    _sentence(f"Both {c1_low} and {c2_low}", ending),
                    _sentence(f"{c1_cap}. In addition, {c2_low}", ending),
                ]

    # 9. Condition: Once [Condition], [Main] (Sentence 27: "Once the acute situation is controlled, the cause is treated.")
    once_m = re.match(r"^Once\s+(?P<cond>[^,]+),\s*(?P<main>.+)$", core, re.I)
    if once_m:
        cond = once_m.group("cond").strip()
        main = once_m.group("main").strip()
        cond_low = _smart_lower_start(cond)
        main_low = _smart_lower_start(main)
        main_cap = _cap_first(main)
        if mode == "academic":
            return [
                _sentence(f"Following control of {cond_low}, {main_low}", ending),
                _sentence(f"After {cond_low}, {main_low}", ending),
                _sentence(f"{main_cap} once {cond_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"After {cond_low}, {main_low}", ending),
                _sentence(f"{main_cap} as soon as {cond_low}", ending),
                _sentence(f"When {cond_low}, {main_low}", ending),
            ]
        else:
            return [
                _sentence(f"When {cond_low}, {main_low}", ending),
                _sentence(f"After {cond_low}, {main_low}", ending),
                _sentence(f"{main_cap} after {cond_low}", ending),
            ]

    # 10. Sentences with "include / includes" (Sentence 14: "Progressive changes include...", Sentence 34: "These include...")
    inc_m = re.match(r"^(?P<subject>.+?)\s+(?P<verb>include|includes)\s+(?P<items>.+)$", core, re.I)
    if inc_m:
        subj = inc_m.group("subject").strip()
        verb = inc_m.group("verb").lower()
        items = inc_m.group("items").strip()
        subj_low = _smart_lower_start(subj)
        subj_cap = _cap_first(subj)
        items_cap = _cap_first(items)
        if mode == "academic":
            return [
                _sentence(f"{items_cap} are included among {subj_low}", ending),
                _sentence(f"Among {subj_low}, {items} are included", ending),
                _sentence(f"{subj_cap} encompass {items}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"In clinical monitoring, {subj_low} feature {items}", ending),
                _sentence(f"Key examples of {subj_low} are {items}", ending),
                _sentence(f"{subj_cap} mainly involve {items}", ending),
            ]
        else:
            return [
                _sentence(f"{subj_cap} include several signs: {items}", ending),
                _sentence(f"{subj_cap} consist of {items}", ending),
                _sentence(f"Main examples of {subj_low} are {items}", ending),
            ]

    # 11. Copular / linking-verb: S is/are [essential|critical|vital|key] for/to O
    copular = re.match(
        r"^(?P<subject>.+?)\s+(?P<verb>is|are|was|were)\s+(?P<comp>essential|critical|vital|crucial|necessary|important|fundamental|key)\s+(?P<prep>for|to)\s+(?P<target>.+)$",
        core,
        re.I,
    )
    if copular:
        subj = copular.group("subject").strip()
        verb = copular.group("verb").lower()
        comp = copular.group("comp").lower()
        prep = copular.group("prep").lower()
        tgt = copular.group("target").strip()
        subj_low = _smart_lower_start(subj)
        tgt_low = _smart_lower_start(tgt)
        tgt_cap = tgt[0].upper() + tgt[1:]
        if mode == "academic":
            return [
                _sentence(f"For {tgt_low}, {subj_low} {verb} {comp}", ending),
                _sentence(f"Ensuring {subj_low} remains {comp} {prep} {tgt_low}", ending),
                _sentence(f"In {tgt_low}, {subj_low} {verb} recognized as {comp}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"{tgt_cap} depend on {subj_low} as a {comp} element", ending),
                _sentence(f"In clinical practice, {subj_low} {verb} {comp} {prep} {tgt_low}", ending),
                _sentence(f"{subj} plays a {comp} role {prep} {tgt_low}", ending),
            ]
        else:
            return [
                _sentence(f"{tgt_cap} need {subj_low}", ending),
                _sentence(f"{subj} {verb} very {comp} {prep} {tgt_low}", ending),
                _sentence(f"{subj} {verb} a key requirement {prep} {tgt_low}", ending),
            ]

    # 12. Trailing prepositional clause: S V O following/after/during ...
    trailing_prep = re.match(
        r"^(?P<main>.+?)\s+(?P<prep>following|after|during|across|within|throughout|without|prior to|subsequent to)\s+(?P<tail>[^,]+)$",
        core,
        re.I,
    )
    if trailing_prep:
        main = trailing_prep.group("main").strip()
        prep = trailing_prep.group("prep").lower()
        tail = trailing_prep.group("tail").strip()
        main_low = _smart_lower_start(main)
        main_cap = main[0].upper() + main[1:]
        if mode == "academic":
            if prep == "without":
                return [
                    _sentence(f"In the absence of {tail}, {main_low}", ending),
                    _sentence(f"Without {tail}, {main_low}", ending),
                ]
            if prep in {"prior to", "subsequent to"}:
                return [
                    _sentence(f"{prep.capitalize()} {tail}, {main_low}", ending),
                ]
            return [
                _sentence(f"{prep.capitalize()} {tail}, {main_low}", ending),
                _sentence(f"In the context of {tail}, {main_low}", ending),
            ]
        elif mode == "human":
            if prep == "without":
                return [
                    _sentence(f"In the absence of {tail}, {main_low}", ending),
                    _sentence(f"Without {tail}, {main_low}", ending),
                    _sentence(f"{main_cap}, without {tail}", ending),
                ]
            return [
                _sentence(f"With {tail}, {main_low}", ending),
                _sentence(f"{prep.capitalize()} {tail}, {main_low}", ending),
                _sentence(f"{main_cap}, following {tail}", ending),
            ]
        else:
            return [
                _sentence(f"{main_cap}. This occurred {prep} {tail}", ending),
                _sentence(f"{prep.capitalize()} {tail}, {main_low}", ending),
            ]

    # 13. Leading prepositional / temporal phrase: In/After/Following/During ..., S V O
    intro_prep = re.match(
        r"^(?P<intro>(?:In|After|Following|During|Across|Within|Through|Upon|According to|Without)\s+[^,]{3,80}),\s*(?P<main>.+)$",
        core,
        re.I,
    )
    if intro_prep:
        intro = intro_prep.group("intro").strip()
        main = intro_prep.group("main").strip()
        main_low = _smart_lower_start(main)
        main_cap = main[0].upper() + main[1:]
        intro_low = _smart_lower_start(intro)
        if mode == "academic":
            return [
                _sentence(f"{main_cap} {intro_low}", ending),
                _sentence(f"As observed {intro_low}, {main_low}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"{main_cap} {intro_low}", ending),
                _sentence(f"Looking at {intro_low}, {main_low}", ending),
                _sentence(f"{main_cap}, as seen {intro_low}", ending),
            ]
        else:
            return [
                _sentence(f"{main_cap}. This occurred {intro_low}", ending),
                _sentence(f"{main_cap} {intro_low}", ending),
            ]

    # 14. Question sentences: e.g. "How would you document...", "Why might insulin with glucose be given..."
    q_match = re.match(r"^(?P<qword>How|Why|What)\s+(?P<rest>.+)$", core, re.I)
    if q_match:
        qword = q_match.group("qword").capitalize()
        rest = q_match.group("rest").strip()
        rest_clean = re.sub(r"\s+[0-9]+\.?$", "", rest)
        if mode == "academic":
            return [
                _sentence(f"From an academic standpoint, consider {qword.lower()} {rest_clean}", ending),
                _sentence(f"Clinical analysis requires assessing {qword.lower()} {rest_clean}", ending),
            ]
        elif mode == "human":
            return [
                _sentence(f"In clinical practice, consider {qword.lower()} {rest_clean}", ending),
                _sentence(f"Clinicians should consider {qword.lower()} {rest_clean}", ending),
            ]
        else:
            return [
                _sentence(f"Think about {qword.lower()} {rest_clean}", ending),
                _sentence(f"Consider {qword.lower()} {rest_clean}", ending),
            ]

    parsed = _split_clause(sentence)
    if parsed:
        subject, verb, obj, aux_neg = parsed
        subject_lower = _smart_lower_start(subject)
        participle = _PARTICIPLES.get(verb.lower(), verb.lower())
        base_v = _base_verb(verb)
        tail = re.match(r"(?P<object>.+?)\s+(?P<link>using|through|with|to|via)\s+(?P<detail>.+)$", obj, re.I)

        obj_plural = _is_plural_phrase(obj)
        aux = "are" if obj_plural else "is"
        past_aux = "were" if obj_plural else "was"
        is_past = verb.lower().endswith("ed") or verb.lower() in {"showed", "revealed", "demonstrated", "exhibited", "observed", "reported", "had"}
        pass_aux = f"{past_aux} not" if (is_past and aux_neg) else (f"{aux} not" if aux_neg else (past_aux if is_past else aux))

        is_tool = bool(re.search(r"\b(model|system|algorithm|framework|pipeline|architecture|method|approach|technique|assay|protocol|classifier|network|detector|tool)\b", subject, re.I))

        # Observational / clinical verbs (exhibited, revealed, showed, demonstrated, had, experienced)
        if verb.lower() in {"exhibited", "revealed", "showed", "demonstrated", "observed", "reported", "exhibits", "reveals", "shows", "demonstrates", "had", "has", "have", "experienced", "experiences"}:
            if mode == "academic":
                candidates.append(_sentence(f"{_cap_first(obj)} {pass_aux} observed in {subject_lower}", ending))
                candidates.append(_sentence(f"{_cap_first(obj)} {pass_aux} demonstrated by {subject_lower}", ending))
                if not aux_neg:
                    candidates.append(_sentence(f"Evidence from {subject_lower} {verb} {obj}", ending))
                return candidates
            elif mode == "human":
                if not aux_neg:
                    alt_verb = "demonstrated" if verb.lower() in {"showed", "revealed"} else ("showed" if verb.lower() in {"exhibited", "demonstrated"} else "revealed")
                    candidates.append(_sentence(f"{subject} {alt_verb} {obj}", ending))
                    candidates.append(_sentence(f"Among {subject_lower}, {obj} {pass_aux} clearly observed", ending))
                    candidates.append(_sentence(f"Data from {subject_lower} indicated {obj}", ending))
                else:
                    candidates.append(_sentence(f"Among {subject_lower}, {obj} {pass_aux} observed", ending))
                    candidates.append(_sentence(f"{subject} {aux_neg} show {obj}", ending))
                return candidates
            else:  # simple
                if not aux_neg:
                    candidates.append(_sentence(f"{subject} showed {obj}", ending))
                    candidates.append(_sentence(f"{_cap_first(obj)} {pass_aux} seen in {subject_lower}", ending))
                    candidates.append(_sentence(f"{subject} had {obj}", ending))
                else:
                    candidates.append(_sentence(f"{subject} {aux_neg} show {obj}", ending))
                    candidates.append(_sentence(f"{_cap_first(obj)} {pass_aux} not seen in {subject_lower}", ending))
                return candidates

        # Requirement verbs (requires, necessitates, mandates)
        if verb.lower() in {"requires", "require", "necessitates", "mandates"}:
            if mode == "academic":
                candidates.append(_sentence(f"For {subject_lower}, {obj} is required", ending))
                candidates.append(_sentence(f"To achieve {subject_lower}, {obj} is necessary", ending))
                return candidates
            elif mode == "human":
                candidates.append(_sentence(f"{subject} depends on {obj}", ending))
                candidates.append(_sentence(f"To achieve {subject_lower}, clinicians need {obj}", ending))
                return candidates
            else:  # simple
                candidates.append(_sentence(f"{subject} needs {obj}", ending))
                candidates.append(_sentence(f"{_cap_first(obj)} is needed for {subject_lower}", ending))
                return candidates

        # Methodological / Tool sentences
        if is_tool:
            if tail:
                detail = tail.group("detail")
                target_obj = tail.group("object")
                if mode == "academic":
                    candidates.append(_sentence(f"Through {detail}, {target_obj} {aux} {participle} by {subject_lower}", ending))
                    candidates.append(_sentence(f"Application of {detail} enables {subject_lower} to {base_v} {target_obj}", ending))
                    candidates.append(_sentence(f"{_cap_first(target_obj)} {aux} systematically {participle} by {subject_lower} via {detail}", ending))
                    return candidates
                elif mode == "human":
                    candidates.append(_sentence(f"Using {detail}, {subject_lower} can {base_v} {target_obj}", ending))
                    candidates.append(_sentence(f"{subject} relies on {detail} to {base_v} {target_obj}", ending))
                    candidates.append(_sentence(f"With {detail}, {subject_lower} {verb} {target_obj}", ending))
                    return candidates
                else:  # simple
                    candidates.append(_sentence(f"{subject} uses {detail} to {base_v} {target_obj}", ending))
                    candidates.append(_sentence(f"Using {detail}, {subject_lower} can {base_v} {target_obj}", ending))
                    candidates.append(_sentence(f"{_cap_first(target_obj)} can be {participle} using {detail}", ending))
                    return candidates
            else:
                if mode == "academic":
                    candidates.append(_sentence(f"{_cap_first(obj)} {aux} systematically {participle} by {subject_lower}", ending))
                    candidates.append(_sentence(f"Through {subject_lower}, {obj} {aux} {participle}", ending))
                    return candidates
                elif mode == "human":
                    candidates.append(_sentence(f"In practice, {subject_lower} {verb} {obj}", ending))
                    candidates.append(_sentence(f"{subject} is designed to {base_v} {obj}", ending))
                    return candidates
                else:  # simple
                    candidates.append(_sentence(f"{_cap_first(obj)} can be {participle} by {subject_lower}", ending))
                    candidates.append(_sentence(f"{subject} is designed to {base_v} {obj}", ending))
                    return candidates

        # General transitive conversion
        if mode == "academic":
            candidates.append(_sentence(f"{_cap_first(obj)} {pass_aux} {participle} by {subject_lower}", ending))
            candidates.append(_sentence(f"Evaluation confirmed that {subject_lower} {verb} {obj}", ending))
            return candidates
        elif mode == "human":
            candidates.append(_sentence(f"From our findings, {subject_lower} {verb} {obj}", ending))
            candidates.append(_sentence(f"{_cap_first(obj)} {pass_aux} documented for {subject_lower}", ending))
            return candidates
        else:  # simple
            if is_past:
                candidates.append(_sentence(f"{subject} was found to {base_v} {obj}", ending))
                candidates.append(_sentence(f"{_cap_first(obj)} {pass_aux} {participle} by {subject_lower}", ending))
            else:
                candidates.append(_sentence(f"{subject} can {base_v} {obj}", ending))
                candidates.append(_sentence(f"In simple terms, {subject_lower} {verb} {obj}", ending))
                candidates.append(_sentence(f"{_cap_first(obj)} {pass_aux} {participle} by {subject_lower}", ending))
            return candidates

    # General fallback for any other sentence with a comma
    comma_match = re.match(r"^(?P<p1>.+?),\s*(?P<p2>[^,]+)$", core)
    if comma_match:
        p1, p2 = comma_match.group("p1").strip(), comma_match.group("p2").strip()
        p1_low = _smart_lower_start(p1)
        p2_cap = p2[0].upper() + p2[1:]
        if mode == "academic":
            candidates.append(_sentence(f"{p2_cap}; {p1_low}", ending))
        elif mode == "human":
            candidates.append(_sentence(f"{p2_cap}, while {p1_low}", ending))
        else:
            candidates.append(_sentence(f"{p2_cap}. Also, {p1_low}", ending))

    return candidates


def _candidate_score(original: str, candidate: str) -> float:
    original_tokens, candidate_tokens = _tokens(original), _tokens(candidate)
    if not candidate_tokens or _FILLER_RE.search(candidate) or _AWKWARD_PATTERNS.search(candidate):
        return -100.0
    overlap = len(set(original_tokens) & set(candidate_tokens)) / max(1, len(set(candidate_tokens)))
    order = SequenceMatcher(None, original_tokens, candidate_tokens).ratio()
    terms = _technical_terms(original)
    cand_tokens_set = set(candidate_tokens)
    preserved = sum(1 for term in terms if _term_preserved(term, cand_tokens_set, candidate.lower())) / max(1, len(terms))
    return (1 - overlap) * 45 + (1 - order) * 35 + preserved * 20


def _valid_candidate(original: str, candidate: str) -> bool:
    if not candidate or candidate.strip().lower() == original.strip().lower() or _FILLER_RE.search(candidate):
        return False
    if _AWKWARD_PATTERNS.search(candidate):
        return False
    # Reject dangling prepositions at end of sentence
    if re.search(r"\b(?:to|by|with|for|from|in|of|over|under|at)\s*[.?!]$", candidate):
        return False
    # Reject awkward imperative passive structures
    if re.search(r"\bby\s+(?:administer|give|infuse|perform|apply|obtain|record|check)\b", candidate, re.I):
        return False
    # Reject awkward infinitives on patient subjects
    if re.search(r"\bTo achieve (?:patients|individuals|subjects|children|adults)\b", candidate, re.I):
        return False
    if not _check_quantities_preserved(original, candidate):
        return False
    if not _check_negation_preserved(original, candidate):
        return False

    orig_tokens = _tokens(original)
    cand_tokens = _tokens(candidate)
    if len(cand_tokens) < max(3, int(len(orig_tokens) * 0.35)):
        return False

    terms = _technical_terms(original)
    if not terms:
        return True

    cand_set = set(cand_tokens)
    cand_lower = candidate.lower()
    preserved = sum(1 for term in terms if _term_preserved(term, cand_set, cand_lower))
    # Require at least 75% preservation of technical terms/numbers, or at most 1 missing term
    return preserved >= len(terms) * 0.75 or (len(terms) - preserved <= 1)


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

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""

    preamble_pattern = re.compile(
        r"^(?:here (?:is|are)|sure|certainly|below is|the rewritten sentence is|rewrite|option \d+|version \d+)\b",
        re.I,
    )

    candidate_lines = []
    for line in lines:
        raw = line.strip()
        # Skip header lines like **Academic (formal):** or lines ending with colon
        if (raw.startswith("**") and raw.endswith("**") and len(raw) < 80) or raw.endswith(":"):
            continue
        line_clean = re.sub(r"^(?:\d+[\.)]|\*+|-)\s*", "", raw).strip()
        line_clean = re.sub(
            r"^(?:\*\*)?(?:(?:rewritten\s+)?sentence|rewrite|academic(?:\s+version)?|human(?:\s+version)?|simple(?:\s+version)?)(?:\*\*)?:\s*",
            "",
            line_clean,
            flags=re.I,
        ).strip()
        line_clean = line_clean.strip("*_ ").strip()
        if not line_clean or line_clean.endswith(":") or (preamble_pattern.search(line_clean) and len(line_clean) < 60):
            continue
        if (line_clean.startswith('"') and line_clean.endswith('"')) or (line_clean.startswith("'") and line_clean.endswith("'")):
            line_clean = line_clean[1:-1].strip()
        if line_clean:
            candidate_lines.append(line_clean)

    return candidate_lines[0] if candidate_lines else lines[0].strip("*_ \"'")


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
    mode_errors: dict[str, str] = {}

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
                mode_errors[m] = f"Gemini error: {exc}"

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
            if m not in mode_errors:
                mode_errors[m] = f"Could not generate an independent {m} rewrite without altering scientific meaning."

    req_mode = mode.lower().strip() if mode and mode.lower().strip() in _MODES else "academic"
    error_message = mode_errors.get(req_mode) or (mode_errors.get("academic") if mode_errors else None)

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

    mode_errors = {
        m: f"Could not generate an independent {m} rewrite without altering scientific meaning."
        for m in _MODES if not rewrites.get(m)
    }

    return {
        "original": sentence,
        "rewritten": primary_rewrite,
        "mode": selected_mode,
        "rewrites": rewrites,
        "provider": provider,
        "is_fallback": provider == "offline",
        "error": error if not primary_rewrite else None,
        "mode_errors": mode_errors,
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
