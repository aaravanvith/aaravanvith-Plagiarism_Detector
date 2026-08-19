import { Bot, User } from "lucide-react";

export default function AIDetectionCard({ aiDetection }) {
  if (!aiDetection) return null;
  const { ai_probability = 0, label = "Not available", features = {} } = aiDetection;
  const isAI = ai_probability >= 70;
  const isMixed = ai_probability >= 40 && ai_probability < 70;

  const color = isAI ? "#B23A48" : isMixed ? "#B8862F" : "#2F7A5C";
  const Icon = isAI ? Bot : User;

  return (
    <div className="bg-white rounded-xl border border-ink-100 p-6">
      <div className="flex items-center justify-between mb-4"><div><p className="text-xs font-semibold uppercase tracking-[.14em] text-seal-600">Content authenticity</p>
        <h3 className="font-display text-lg text-ink-900">AI Content Detection</h3></div>
        <Icon className="h-5 w-5" style={{ color }} />
      </div>

      <div className="flex items-baseline gap-2 mb-1">
        <span className="font-mono text-3xl font-semibold" style={{ color }}>
          {ai_probability}%
        </span>
        <span className="text-sm text-ink-400">AI-likelihood</span>
      </div>
      <p className="text-sm font-medium mb-4" style={{ color }}>{label}</p>

      <div className="h-2 rounded-full bg-ink-50 overflow-hidden mb-5">
        <div
          className="h-full rounded-full"
          style={{ width: `${ai_probability}%`, backgroundColor: color }}
        />
      </div>

      <p className="text-xs text-ink-400 uppercase tracking-wide mb-2">Stylometric signals</p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <Feature label="Avg. sentence length" value={features.avg_sentence_length ?? "—"} />
        <Feature label="Sentence-length variance" value={features.sentence_length_variation ?? "—"} />
        <Feature label="Lexical diversity (TTR)" value={features.lexical_diversity_ttr ?? "—"} />
        <Feature label="Stopword ratio" value={features.stopword_ratio ?? "—"} />
      </dl>
    </div>
  );
}

function Feature({ label, value }) {
  return (
    <div className="flex justify-between border-b border-dashed border-ink-100 pb-1">
      <dt className="text-ink-400">{label}</dt>
      <dd className="font-mono text-ink-800">{value}</dd>
    </div>
  );
}
