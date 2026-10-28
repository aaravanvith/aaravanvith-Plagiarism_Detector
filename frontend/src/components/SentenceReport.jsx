import { useState } from "react";
import { Sparkles, AlertTriangle, CheckCircle2, FileText, ArrowRight } from "lucide-react";
import { getPlagiarismCategory } from "./sentenceUtils.js";

export default function SentenceReport({
  sentences = [],
  onSelect,
  activeSentence,
  plagiarismScore,
  sourcesCompared,
}) {
  const [filter, setFilter] = useState("all");

  const flaggedCount = sentences.filter((s) => s.flagged).length;
  const unflaggedCount = sentences.length - flaggedCount;

  // Preserve the original sentence order and indices
  const sentencesWithIndex = sentences.map((s, index) => ({
    ...s,
    originalIndex: index,
  }));

  const filteredSentences = sentencesWithIndex.filter((s) => {
    if (filter === "all") return true;
    if (filter === "flagged") return Boolean(s.flagged);
    if (filter === "unflagged") return !s.flagged;
    return true;
  });

  const handleSelectSentence = (sentence) => {
    // Critical: only flagged sentences may open the Correction Agent
    if (sentence && sentence.flagged && onSelect) {
      onSelect(sentence);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-ink-100 p-6 shadow-sm">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[.14em] text-seal-600">
            Explainable Evidence
          </p>
          <h3 className="font-display text-xl text-ink-900">
            Sentence-Level Report
          </h3>
        </div>
        <p className="text-xs text-ink-500 bg-ink-50 px-3 py-1.5 rounded-lg border border-ink-100">
          <span className="font-semibold text-ink-700">{sentences.length}</span> sentences extracted ·{" "}
          <span className="font-semibold text-risk-high">{flaggedCount}</span> flagged matches ·{" "}
          <span className="font-semibold text-risk-low">{unflaggedCount}</span> clean
        </p>
      </div>

      {/* Plagiarism Status Legend */}
      <div className="mb-4 rounded-lg bg-ink-50 p-3.5 border border-ink-100 space-y-1.5 text-xs">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="font-semibold text-ink-700 flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5 text-seal-500" /> Plagiarism Match Status:
          </span>
          <span className="inline-flex items-center gap-1 rounded bg-risk-highBg px-2 py-0.5 text-risk-high border border-risk-high/30 font-medium">
            <AlertTriangle className="h-3 w-3" /> Flagged Match (≥ 20% similarity)
          </span>
          <span className="inline-flex items-center gap-1 rounded bg-risk-lowBg px-2 py-0.5 text-risk-low border border-risk-low/30 font-medium">
            <CheckCircle2 className="h-3 w-3" /> No Flagged Match (&lt; 20% similarity)
          </span>
        </div>
        <p className="text-[11px] text-ink-400">
          Click any flagged sentence to open the Correction Agent for rewrites and citation assistance. Unflagged sentences have low overlap with the reference corpus and require no correction.
        </p>
      </div>

      {/* Filter Tabs */}
      <div className="mb-4 flex flex-wrap gap-1.5 border-b border-ink-100 pb-3" role="tablist" aria-label="Sentence filter">
        {[
          { id: "all", label: `All Sentences (${sentences.length})` },
          { id: "flagged", label: `Flagged Plagiarism (${flaggedCount})` },
          { id: "unflagged", label: `Unflagged (${unflaggedCount})` },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={filter === tab.id}
            onClick={() => setFilter(tab.id)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
              filter === tab.id
                ? "bg-ink-800 text-white shadow-xs"
                : "bg-ink-50 text-ink-600 hover:bg-ink-100 hover:text-ink-900"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Sentence Cards List */}
      <div className="space-y-3">
        {filteredSentences.length === 0 ? (
          <div className="rounded-lg border border-dashed border-ink-200 p-8 text-center text-sm text-ink-500">
            No sentences match the selected filter.
          </div>
        ) : (
          filteredSentences.map((s) => {
            const plagCat = getPlagiarismCategory(s);
            const isSelected =
              s.flagged &&
              activeSentence?.start_offset === s.start_offset &&
              activeSentence?.end_offset === s.end_offset;

            if (s.flagged) {
              // FLAGGED SENTENCE CARD: Red styling, clickable to open Correction Agent
              return (
                <button
                  type="button"
                  key={`${s.start_offset}-${s.end_offset}-${s.originalIndex}`}
                  aria-label={`Review flagged sentence ${s.originalIndex + 1}: ${plagCat.score.toFixed(1)}% similarity`}
                  aria-haspopup="dialog"
                  aria-expanded={isSelected}
                  onClick={() => handleSelectSentence(s)}
                  className={`group relative block w-full rounded-xl border bg-risk-highBg/20 p-4 text-left transition-all duration-150 border-l-4 border-l-risk-high border-risk-high/30 cursor-pointer ${
                    isSelected
                      ? "ring-2 ring-risk-high border-risk-high shadow-md bg-risk-highBg/40"
                      : "hover:border-risk-high hover:shadow-sm hover:bg-risk-highBg/30"
                  }`}
                >
                  {/* Card Top Row */}
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-ink-100 text-ink-700">
                        #{String(s.originalIndex + 1).padStart(2, "0")}
                      </span>
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-risk-high uppercase tracking-wider">
                        <AlertTriangle className="h-3 w-3" /> Flagged Match
                      </span>
                    </div>

                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs ${plagCat.badgeStyle}`}
                      title={`Plagiarism similarity: ${plagCat.score.toFixed(1)}%`}
                    >
                      <AlertTriangle className="h-3 w-3" /> {plagCat.badgeText}
                    </span>
                  </div>

                  {/* Sentence Text */}
                  <p className="text-[15px] text-ink-900 leading-relaxed font-body my-2">
                    {s.sentence}
                  </p>

                  {/* Card Bottom Row: Source evidence and Correct Sentence prompt */}
                  <div className="flex flex-wrap items-center justify-between gap-2 mt-3 pt-2.5 border-t border-risk-high/20 text-xs text-ink-500">
                    <div className="flex flex-wrap items-center gap-2">
                      {s.matched_source && s.matched_source !== "-" ? (
                        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-seal-700 bg-white px-2 py-0.5 rounded border border-seal-200">
                          Source: {s.matched_source}
                        </span>
                      ) : (
                        <span className="text-ink-400 text-[11px]">No reference source match</span>
                      )}

                      <span className="text-ink-500 text-[11px] font-mono">
                        TF-IDF {s.tfidf_similarity ?? 0}% · Cosine {s.cosine_similarity ?? 0}%
                        {s.semantic_similarity ? ` · Semantic ${s.semantic_similarity}%` : ""}
                      </span>
                    </div>

                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-risk-high group-hover:translate-x-0.5 transition-transform">
                      <Sparkles className="h-3.5 w-3.5 text-risk-high" /> Correct Sentence <ArrowRight className="h-3 w-3" />
                    </span>
                  </div>
                </button>
              );
            }

            // UNFLAGGED SENTENCE CARD: Green styling, non-clickable, NO correction action
            return (
              <div
                key={`${s.start_offset}-${s.end_offset}-${s.originalIndex}`}
                aria-label={`Sentence ${s.originalIndex + 1}: No flagged match, no correction needed`}
                className="relative block w-full rounded-xl border bg-risk-lowBg/15 p-4 text-left border-l-4 border-l-risk-low border-risk-low/30"
              >
                {/* Card Top Row */}
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-ink-100 text-ink-700">
                      #{String(s.originalIndex + 1).padStart(2, "0")}
                    </span>
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-risk-low">
                      <CheckCircle2 className="h-3 w-3" /> Clean
                    </span>
                  </div>

                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs ${plagCat.badgeStyle}`}
                    title={`Similarity: ${plagCat.score.toFixed(1)}%`}
                  >
                    <CheckCircle2 className="h-3 w-3" /> {plagCat.badgeText}
                  </span>
                </div>

                {/* Sentence Text */}
                <p className="text-[15px] text-ink-900 leading-relaxed font-body my-2">
                  {s.sentence}
                </p>

                {/* Card Bottom Row: Source evidence and 'No correction needed' */}
                <div className="flex flex-wrap items-center justify-between gap-2 mt-3 pt-2.5 border-t border-risk-low/20 text-xs text-ink-500">
                  <div className="flex flex-wrap items-center gap-2">
                    {s.matched_source && s.matched_source !== "-" ? (
                      <span className="inline-flex items-center gap-1 font-mono text-[11px] text-ink-600 bg-white px-2 py-0.5 rounded border border-ink-200">
                        Source: {s.matched_source}
                      </span>
                    ) : (
                      <span className="text-ink-400 text-[11px]">No reference source match</span>
                    )}
                  </div>

                  <span className="inline-flex items-center gap-1.5 text-xs font-medium text-risk-low bg-white px-2.5 py-1 rounded-md border border-risk-low/30">
                    <CheckCircle2 className="h-3.5 w-3.5 text-risk-low" /> No correction needed
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Summary section */}
      <section
        aria-label="Plagiarism evidence summary"
        className="mt-6 rounded-xl border border-ink-100 bg-ink-50 p-5"
      >
        <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-2 border-b border-ink-200/60 pb-3">
          <div>
            <h4 className="font-display text-lg text-ink-900">
              Plagiarism Evidence Summary
            </h4>
            <p className="mt-0.5 text-xs text-ink-500">
              Overall similarity calculated against {sourcesCompared ?? "all available"} reference sources.
            </p>
          </div>
          <div className="text-right">
            <span className="text-xs uppercase tracking-wider text-ink-400 font-semibold block">
              Overall Plagiarism
            </span>
            <span className="text-2xl font-semibold text-seal-600 font-mono">
              {Number.isFinite(plagiarismScore) ? `${plagiarismScore.toFixed(1)}%` : "Unavailable"}
            </span>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="rounded-lg bg-white p-3.5 border border-ink-100">
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-400 mb-1.5 flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 text-risk-high" /> Flagged Matches
            </p>
            <p className="text-sm text-ink-800">
              <strong className="text-risk-high font-semibold">{flaggedCount}</strong> of {sentences.length} sentences reached the similarity threshold (≥ 20%).
            </p>
            <p className="text-xs text-ink-500 mt-1">
              Flagged sentences can be opened for sentence-level rewriting and citations.
            </p>
          </div>

          <div className="rounded-lg bg-white p-3.5 border border-ink-100">
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-400 mb-1.5 flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-risk-low" /> Unflagged Sentences
            </p>
            <p className="text-sm text-ink-800">
              <strong className="text-risk-low font-semibold">{unflaggedCount}</strong> of {sentences.length} sentences are below the similarity threshold.
            </p>
            <p className="text-xs text-ink-500 mt-1">
              These sentences are within acceptable originality standards; no correction needed.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
