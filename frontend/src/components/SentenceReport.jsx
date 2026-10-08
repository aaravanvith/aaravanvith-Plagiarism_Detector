export default function SentenceReport({ sentences = [], onSelect, activeSentence }) {
  const flaggedCount = sentences.filter((sentence) => sentence.flagged).length;
  return (
    <div className="bg-white rounded-xl border border-ink-100 p-6">
      <div className="flex items-center justify-between mb-4">
        <div><p className="text-xs font-semibold uppercase tracking-[.14em] text-seal-600">Explainable evidence</p><h3 className="font-display text-lg text-ink-900">Sentence-Level Report</h3></div>
        <p className="text-xs text-ink-400">{flaggedCount} potential matches · Click any sentence box for a correction</p>
      </div>
      <div className="space-y-1 leading-relaxed">
        {sentences.map((s, i) => (
          <button type="button"
            key={`${s.start_offset}-${s.end_offset}-${i}`}
            aria-label={s.flagged ? `Review flagged sentence ${i + 1}` : `Rewrite sentence ${i + 1}`}
            aria-haspopup="dialog"
            aria-expanded={activeSentence?.start_offset === s.start_offset && activeSentence?.end_offset === s.end_offset}
            onClick={() => onSelect(s)}
            className={`block w-full rounded-lg px-4 py-3 border text-left text-[15px] transition ${
              "bg-risk-mediumBg text-risk-medium border-risk-medium/30 cursor-pointer hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-seal-500"
            } ${activeSentence?.start_offset === s.start_offset && activeSentence?.end_offset === s.end_offset ? "ring-2 ring-seal-500" : ""}`}
          >
            <span className="mr-2 font-mono text-xs text-ink-400">{String(i + 1).padStart(2, "0")}</span>{s.sentence}
            {!s.flagged && <span className="mt-2 block text-right text-xs text-ink-500">Below flag threshold · Click to rewrite →</span>}
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
    </div>
  );
}
