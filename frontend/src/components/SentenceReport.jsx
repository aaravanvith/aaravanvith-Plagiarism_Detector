const RISK_STYLES = {
  high: "bg-risk-highBg text-risk-high border-risk-high/40",
  medium: "bg-risk-mediumBg text-risk-medium border-risk-medium/40",
  low: "bg-risk-lowBg text-risk-low border-risk-low/40",
  unknown: "bg-ink-50 text-ink-600 border-ink-100",
};
const riskFor = (sentence) => {
  if (!Number.isFinite(sentence.ai_probability)) return "unknown";
  const score = sentence.ai_probability;
  return score >= 70 ? "high" : score >= 40 ? "medium" : "low";
};
const RISK_LABELS = { high: "AI-like writing (estimate)", medium: "Mixed human-like / AI-like writing (estimate)", low: "Human-like writing (estimate)", unknown: "Insufficient evidence for an AI-style estimate" };

export default function SentenceReport({ sentences = [], onSelect, activeSentence, plagiarismScore, sourcesCompared }) {
  const flaggedCount = sentences.filter((sentence) => sentence.flagged).length;
  const counts = sentences.reduce((result, sentence) => {
    result[riskFor(sentence)] += 1;
    return result;
  }, {high: 0, medium: 0, low: 0, unknown: 0});
  return (
    <div className="bg-white rounded-xl border border-ink-100 p-6">
      <div className="flex items-center justify-between mb-4">
        <div><p className="text-xs font-semibold uppercase tracking-[.14em] text-seal-600">Explainable evidence</p><h3 className="font-display text-lg text-ink-900">Sentence-Level Report</h3></div>
        <p className="text-xs text-ink-400">{flaggedCount} potential matches · Click any sentence box for a correction</p>
      </div>
      <div className="mb-4 flex flex-wrap gap-2 text-xs">
        <span className="rounded border border-risk-high/40 bg-risk-highBg px-3 py-2 text-risk-high">Red: AI-like · AI score 70–100%</span>
        <span className="rounded border border-risk-medium/40 bg-risk-mediumBg px-3 py-2 text-risk-medium">Yellow: mixed · AI score 40–&lt;70%</span>
        <span className="rounded border border-risk-low/40 bg-risk-lowBg px-3 py-2 text-risk-low">Green: human-like · AI score below 40%</span>
      </div>
      <p className="mb-4 text-xs text-ink-500">Colors reflect experimental AI-style scores, not proven authorship. Yellow means uncertain or mixed signals, not a measured 50/50 split. Short fragments are gray. The detector uses synthetic training data and may misclassify AI-written or human-written text.</p>
      <div className="space-y-2 leading-relaxed">
        {sentences.map((s, i) => (
          <button type="button"
            key={`${s.start_offset}-${s.end_offset}-${i}`}
            aria-label={s.flagged ? `Review flagged sentence ${i + 1}` : `Rewrite sentence ${i + 1}`}
            aria-haspopup="dialog"
            aria-expanded={activeSentence?.start_offset === s.start_offset && activeSentence?.end_offset === s.end_offset}
            onClick={() => onSelect(s)}
            className={`block w-full rounded-lg px-4 py-3 border text-left text-[15px] transition ${
              `${RISK_STYLES[riskFor(s)]} cursor-pointer hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-seal-500`
            } ${activeSentence?.start_offset === s.start_offset && activeSentence?.end_offset === s.end_offset ? "ring-2 ring-seal-500" : ""}`}
          >
            <span className="mb-1 block text-xs font-semibold">{RISK_LABELS[riskFor(s)]}{Number.isFinite(s.ai_probability) ? ` · AI-style score ${s.ai_probability}%` : ""}</span><span className="mr-2 font-mono text-xs text-ink-400">{String(i + 1).padStart(2, "0")}</span>{s.sentence}
            {!s.flagged && <span className="mt-2 block text-right text-xs text-ink-500">Low similarity · {s.hybrid_similarity ?? s.similarity ?? 0}% · Click to rewrite →</span>}
            {s.flagged && (
              <>
                <span className="ml-2 font-mono text-xs opacity-80">{s.hybrid_similarity ?? s.similarity}% similarity · Review correction →</span>
                <span className="mt-2 block text-right text-xs opacity-80">
                  TF-IDF {s.tfidf_similarity ?? "–"}% · Cosine {s.cosine_similarity ?? "–"}%
                  {s.semantic_similarity ? ` · Semantic ${s.semantic_similarity}%` : ""}
                </span>
              </>
            )}
          </button>
        ))}
      </div>
      <section aria-label="Plagiarism summary" className="mt-6 rounded-xl border border-ink-100 bg-ink-50 p-5">
        <h4 className="font-display text-xl text-ink-900">Plagiarism summary</h4>
        <p className="mt-2 text-3xl font-semibold text-seal-600">{Number.isFinite(plagiarismScore) ? `${plagiarismScore.toFixed(1)}%` : "Unavailable"}</p>
        <p className="mt-1 text-sm text-ink-600">Overall similarity against {sourcesCompared ?? "the available"} reference sources.</p>
        <p className="mt-3 text-sm font-semibold text-ink-600">Sentence AI-style estimates (separate from plagiarism)</p>
        <div className="mt-3 flex flex-wrap gap-4 text-sm">
          <span className="text-risk-high">AI-like: {counts.high}</span>
          <span className="text-risk-medium">Mixed: {counts.medium}</span>
          <span className="text-risk-low">Human-like: {counts.low}</span>
          <span className="text-ink-500">Unassessed: {counts.unknown}</span>
        </div>
        <p className="mt-2 text-xs text-ink-500">{flaggedCount} of {sentences.length} sentences reached the flag threshold. The overall score comes from the analysis engine; it is not the percentage of colored boxes.</p>
      </section>
    </div>
  );
}
