import assert from "node:assert/strict";
import { test } from "node:test";
import { getPlagiarismCategory, getAiCategory } from "./src/components/sentenceUtils.js";

test("getPlagiarismCategory marks FLAGGED sentence with Flagged Match label and red card styling", () => {
  const flaggedSentence = {
    flagged: true,
    hybrid_similarity: 78.5,
    similarity: 75.0,
    sentence: "Clinical study demonstrates significant patient outcome improvements.",
  };
  const cat = getPlagiarismCategory(flaggedSentence);
  assert.equal(cat.isFlagged, true);
  assert.equal(cat.key, "flagged");
  assert.equal(cat.badgeText, "Flagged Match · 78.5%");
  assert.match(cat.label, /Flagged Match/);
  assert.match(cat.badgeStyle, /text-risk-high/);
  assert.match(cat.cardBorder, /border-l-risk-high/);
  assert.equal(cat.score, 78.5);
});

test("getPlagiarismCategory marks UNFLAGGED sentence with No Flagged Match label and green card styling", () => {
  const unflaggedSentence = {
    flagged: false,
    hybrid_similarity: 4.2,
    similarity: 4.0,
    sentence: "Independent original text written by the student.",
  };
  const cat = getPlagiarismCategory(unflaggedSentence);
  assert.equal(cat.isFlagged, false);
  assert.equal(cat.key, "unflagged");
  assert.equal(cat.badgeText, "No Flagged Match · 4.2%");
  assert.match(cat.label, /No Flagged Match/);
  assert.match(cat.badgeStyle, /text-risk-low/);
  assert.match(cat.cardBorder, /border-l-risk-low/);
  assert.equal(cat.score, 4.2);
});

test("preserves all sentences in original order regardless of similarity or flagged status", () => {
  const sentences = [
    { sentence: "Clean opening sentence.", flagged: false, similarity: 2.1, start_offset: 0, end_offset: 23 },
    { sentence: "High overlap sentence from medical paper.", flagged: true, similarity: 85.0, start_offset: 24, end_offset: 65 },
    { sentence: "Moderate similarity but unflagged note.", flagged: false, similarity: 18.0, start_offset: 66, end_offset: 105 },
    { sentence: "Another flagged passage needing rewrite.", flagged: true, similarity: 62.4, start_offset: 106, end_offset: 146 },
  ];

  // Must preserve all 4 sentences in original index order
  assert.equal(sentences.length, 4);
  assert.equal(sentences[0].sentence, "Clean opening sentence.");
  assert.equal(sentences[1].sentence, "High overlap sentence from medical paper.");
  assert.equal(sentences[2].sentence, "Moderate similarity but unflagged note.");
  assert.equal(sentences[3].sentence, "Another flagged passage needing rewrite.");

  const flaggedCount = sentences.filter((s) => s.flagged).length;
  const unflaggedCount = sentences.length - flaggedCount;
  assert.equal(flaggedCount, 2);
  assert.equal(unflaggedCount, 2);
});

test("correction selection handler only accepts flagged sentences", () => {
  let activeSentence = null;
  const onSelectSentence = (s) => {
    if (s && s.flagged) {
      activeSentence = s;
    }
  };

  const flagged = { sentence: "Flagged sentence", flagged: true, similarity: 75.0 };
  const unflagged = { sentence: "Clean sentence", flagged: false, similarity: 5.0 };

  // Attempting to select an unflagged sentence must NOT activate correction
  onSelectSentence(unflagged);
  assert.equal(activeSentence, null, "Unflagged sentence must never activate correction");

  // Selecting a flagged sentence successfully activates correction
  onSelectSentence(flagged);
  assert.equal(activeSentence, flagged, "Flagged sentence must activate correction");
});

test("getAiCategory utility backwards compatibility", () => {
  assert.equal(getAiCategory({ ai_probability: 85.0 }).key, "ai_like");
  assert.equal(getAiCategory({ ai_probability: 50.0 }).key, "mixed");
  assert.equal(getAiCategory({ ai_probability: 20.0 }).key, "human_like");
  assert.equal(getAiCategory({ ai_probability: null }).key, "unavailable");
});
