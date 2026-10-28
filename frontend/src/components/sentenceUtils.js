/**
 * Pure utilities for Sentence Report categorization and metrics.
 * Separated from JSX components so they can be unit-tested directly in standard JS.
 */

/**
 * Plagiarism status is determined using existing plagiarism detection thresholds and logic.
 * - FLAGGED sentence: Flagged Match with score % and red styling.
 * - UNFLAGGED sentence: No Flagged Match with score % and green styling.
 */
export function getPlagiarismCategory(sentence) {
  const score = sentence.hybrid_similarity ?? sentence.similarity ?? 0;
  const isFlagged = Boolean(sentence.flagged);

  if (isFlagged) {
    return {
      key: "flagged",
      isFlagged: true,
      label: `Flagged Match · ${score.toFixed(1)}%`,
      badgeText: `Flagged Match · ${score.toFixed(1)}%`,
      badgeStyle: "bg-risk-highBg text-risk-high border border-risk-high/30 font-medium",
      cardBorder: "border-l-4 border-l-risk-high border-risk-high/30 bg-risk-highBg/20",
      score,
    };
  }
  return {
    key: "unflagged",
    isFlagged: false,
    label: `No Flagged Match · ${score.toFixed(1)}%`,
    badgeText: `No Flagged Match · ${score.toFixed(1)}%`,
    badgeStyle: "bg-risk-lowBg text-risk-low border border-risk-low/30 font-medium",
    cardBorder: "border-l-4 border-l-risk-low border-risk-low/30 bg-risk-lowBg/15",
    score,
  };
}

/**
 * Kept for backend API parity and tests.
 */
export function getAiCategory(sentence) {
  const prob = sentence.ai_probability;
  if (prob === null || prob === undefined || !Number.isFinite(prob)) {
    return {
      key: "unavailable",
      label: "AI-style score unavailable for this sentence",
      badgeText: "AI-style score unavailable for this sentence",
      shortLabel: "AI Unavailable",
      badgeStyle: "bg-ink-100 text-ink-600 border border-ink-200",
      score: null,
    };
  }
  if (prob >= 70) {
    return {
      key: "ai_like",
      label: `AI-like writing (${prob.toFixed(1)}%)`,
      badgeText: `AI-like · ${prob.toFixed(1)}%`,
      shortLabel: "AI-like",
      badgeStyle: "bg-risk-highBg text-risk-high border border-risk-high/30",
      score: prob,
    };
  }
  if (prob >= 40) {
    return {
      key: "mixed",
      label: `Mixed / uncertain (${prob.toFixed(1)}%)`,
      badgeText: `Mixed / uncertain · ${prob.toFixed(1)}%`,
      shortLabel: "Mixed / uncertain",
      badgeStyle: "bg-risk-mediumBg text-risk-medium border border-risk-medium/30",
      score: prob,
    };
  }
  return {
    key: "human_like",
    label: `Human-like writing (${prob.toFixed(1)}%)`,
    badgeText: `Human-like · ${prob.toFixed(1)}%`,
    shortLabel: "Human-like",
    badgeStyle: "bg-risk-lowBg text-risk-low border border-risk-low/30",
    score: prob,
  };
}
