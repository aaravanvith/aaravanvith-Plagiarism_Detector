"""
Correction Agent (Slides 13-14)
================================
"Detect -> Explain -> Correct" writing assistant.

- Detect:  handled upstream by similarity.py
- Explain: templated, transparent explanation of *why* a sentence was flagged
- Correct: rule-based rewrite using a bundled synonym table (kept offline;
           no external paraphrasing API), plus a citation suggestion in
           APA or IEEE format.

This is intentionally rule-based rather than calling a hosted LLM: the
project brief (Slide 6) states GenAI is used only as a *development*
aid, never to assess or alter student submissions live, and the whole
system must remain internet-independent (Slide 7). A rule-based rewriter
keeps that guarantee while still demonstrating the "Correct" stage end to end.
"""
import random
import re

SYNONYMS = {
    "important": ["significant", "essential", "crucial"],
    "use": ["utilize", "employ", "apply"],
    "used": ["utilized", "employed", "applied"],
    "show": ["demonstrate", "illustrate", "reveal"],
    "shows": ["demonstrates", "illustrates", "reveals"],
    "big": ["substantial", "considerable", "large-scale"],
    "good": ["effective", "favorable", "sound"],
    "bad": ["ineffective", "unfavorable", "problematic"],
    "help": ["assist", "support", "facilitate"],
    "helps": ["assists", "supports", "facilitates"],
    "make": ["create", "develop", "construct"],
    "makes": ["creates", "develops", "constructs"],
    "focus": ["concentrate", "center", "emphasis"],
    "learning": ["acquisition of knowledge", "training process", "skill development"],
    "system": ["framework", "mechanism", "platform"],
    "method": ["approach", "technique", "procedure"],
    "problem": ["issue", "challenge", "difficulty"],
    "increase": ["rise", "growth", "escalation"],
    "reduce": ["decrease", "lower", "minimize"],
    "part": ["component", "element", "segment"],
    "subset": ["branch", "division", "category"],
    "focuses": ["concentrates", "centers", "specializes"],
    "data": ["information", "datasets", "records"],
    "patterns": ["trends", "regularities", "structures"],
    "detect": ["identify", "recognize", "flag"],
    "detects": ["identifies", "recognizes", "flags"],
    "analyze": ["examine", "evaluate", "assess"],
    "analyzes": ["examines", "evaluates", "assesses"],
}

_WORD_RE = re.compile(r"[A-Za-z']+")


def _rewrite_sentence(sentence: str, seed: int = 0) -> str:
    rng = random.Random(seed)

    def replace(match: re.Match) -> str:
        word = match.group(0)
        lower = word.lower()
        if lower in SYNONYMS:
            choice = rng.choice(SYNONYMS[lower])
            if word[0].isupper():
                choice = choice[0].upper() + choice[1:]
            return choice
        return word

    rewritten = _WORD_RE.sub(replace, sentence)
    if rewritten.strip() == sentence.strip():
        # No swappable vocabulary found — restructure with a generic academic frame.
        # Only lowercase the opening letter if the first word isn't an acronym (e.g. "TF-IDF").
        first_word = sentence.split(" ", 1)[0] if sentence else ""
        if first_word[:2].isupper() and len(first_word) > 1:
            lead = sentence
        else:
            lead = sentence[0].lower() + sentence[1:]
        rewritten = f"In other words, {lead}"
    return rewritten


def explain_flag(sentence: str, best_source: str, score: float) -> str:
    if score >= 75:
        strength = "very high textual and structural overlap"
    elif score >= 55:
        strength = "notable wording and phrase-level overlap"
    else:
        strength = "some overlap in key terms"
    return (
        f"This sentence matches content from \"{best_source}\" with {strength} "
        f"({score}% similarity, measured via TF-IDF cosine similarity). "
        "Consider paraphrasing in your own words or adding a citation to "
        "properly attribute the source."
    )


def suggest_citation(source_name: str, style: str = "APA") -> str:
    style = style.upper()
    year_guess = "n.d."
    if style == "IEEE":
        return f'[X] Author(s), "{source_name}," source document, {year_guess}.'
    # default APA
    return f"Author, A. A. ({year_guess}). {source_name}. Source document."

def correct_sentence(sentence: str, source_name: str, score: float, seed: int = 0) -> dict:
    rewritten = _rewrite_sentence(sentence, seed=seed)
    return {
        "original": sentence,
        "rewritten": rewritten,
        "explanation": explain_flag(sentence, source_name, score),
        "citation_apa": suggest_citation(source_name, "APA"),
        "citation_ieee": suggest_citation(source_name, "IEEE"),
    }


CHAT_TEMPLATES = [
    (re.compile(r"why.*flag", re.I),
     lambda ctx: explain_flag(ctx["sentence"], ctx["source"], ctx["score"])),
    (re.compile(r"(rewrite|improve|fix|correct)", re.I),
     lambda ctx: f"Here's a possible rewrite: \"{_rewrite_sentence(ctx['sentence'])}\""),
    (re.compile(r"citat|reference|cite", re.I),
     lambda ctx: f"Suggested citation (APA): {suggest_citation(ctx['source'])}"),
    (re.compile(r"ai.?generated|ai.?content", re.I),
     lambda ctx: "AI-content likelihood is scored separately using sentence-length "
                 "uniformity, lexical diversity, and punctuation variety — check the "
                 "\"AI Detection\" tab for this document's score."),
]


def chat_reply(message: str, context: dict) -> str:
    for pattern, handler in CHAT_TEMPLATES:
        if pattern.search(message):
            return handler(context)
    return (
        "I can help explain why a sentence was flagged, suggest a rewrite, "
        "or recommend a citation format. Try asking: \"Why is this flagged?\" "
        "or \"Can you rewrite this?\""
    )
