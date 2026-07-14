const RISK_STYLES = {
  high: "bg-risk-highBg text-risk-high border-risk-high/30",
  medium: "bg-risk-mediumBg text-risk-medium border-risk-medium/30",
  low: "bg-transparent text-ink-600 border-transparent",
};

export default function SentenceReport({ sentences, onSelect, activeSentence }) {
  return (
    <div className="bg-white rounded-xl border border-ink-100 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-display text-lg text-ink-900">Sentence-Level Evidence</h3>
        <p className="text-xs text-ink-400">Click a highlighted line to inspect the hybrid score</p>
      </div>
      <div className="space-y-1 leading-relaxed">
        {sentences.map((s, i) => (
          <p
            key={i}
            onClick={() => s.flagged && onSelect(s)}
            className={`rounded-md px-2 py-1.5 border text-[15px] ${RISK_STYLES[s.risk]} ${
              s.flagged ? "cursor-pointer hover:brightness-95" : ""
            } ${activeSentence?.sentence === s.sentence ? "ring-2 ring-seal-500" : ""}`}
          >
            {s.sentence}
            {s.flagged && (
              <>
                <span className="ml-2 font-mono text-xs opacity-70">{s.hybrid_similarity ?? s.similarity}%</span>
                <span className="ml-2 text-[11px] opacity-65">
                  TF-IDF {s.tfidf_similarity ?? "–"}% · Cosine {s.cosine_similarity ?? "–"}%
                  {s.semantic_similarity ? ` · Semantic ${s.semantic_similarity}%` : ""}
                </span>
              </>
            )}
          </p>
        ))}
      </div>
    </div>
  );
}
