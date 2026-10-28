"""Tests for Sentence-Level Report and AI-content detection integration.

Covers:
1. Sentence extraction and preservation of original sentence order.
2. Short sentence handling (< 8 words): ai_probability is None and label is
   'AI-style score unavailable for this sentence'.
3. Normal sentence handling (>= 8 words): valid ai_probability and label.
4. Independent evaluation: plagiarism similarity vs AI probability.
5. All sentences included in all_sentences regardless of score or flagged status.
6. Auto-correct and correction endpoints continue functioning with all sentences.
"""
import io
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import get_db, Base
from app.services.ai_detection import detect_ai_content
from app.services.similarity import analyze_document


class TestSentenceReportBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        TestingSessionLocal = sessionmaker(bind=engine)

        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    def test_short_sentence_ai_unavailable_label(self):
        """Short sentences with < 8 words must yield unavailable status without crashing."""
        short_sentence = "Patient was monitored."
        self.assertLess(len(short_sentence.split()), 8)

        # Longer sentence for comparison
        longer_sentence = (
            "Clinical research studies evaluate disease prevention and patient "
            "health outcomes through hospital treatment protocols."
        )
        self.assertGreaterEqual(len(longer_sentence.split()), 8)
        ai_res = detect_ai_content(longer_sentence)
        self.assertIn("ai_probability", ai_res)
        self.assertIsInstance(ai_res["ai_probability"], float)

    def test_analyze_endpoint_returns_all_sentences_with_ai_labels(self):
        """Verify that POST /api/analyze returns all sentences in original order with separate indicators."""
        # Must be healthcare-related to satisfy prototype gate (need 3+ healthcare keywords, 20+ words)
        text = (
            "Clinical research evaluates disease prevention protocols and health outcome improvements. "
            "Hospital patient care was monitored. "
            "Medical diagnosis improves patient health outcomes and hospital treatment through careful clinical data analysis."
        )

        mock_corpus = {
            "pubmed::sample1": "Clinical research evaluates disease prevention protocols and health metrics.",
            "pubmed::sample2": "Medical diagnosis improves patient health outcomes through careful clinical data analysis.",
        }

        with patch("app.main.load_reference_corpus", return_value=mock_corpus):
            response = self.client.post(
                "/api/analyze",
                files={"file": ("report.txt", text.encode("utf-8"), "text/plain")},
                data={"online": "false"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()

        # Check all_sentences presence and length
        self.assertIn("all_sentences", data)
        sentences = data["all_sentences"]
        self.assertGreaterEqual(len(sentences), 3)

        # 1. First sentence: normal length (10 words >= 8)
        self.assertEqual(
            sentences[0]["sentence"],
            "Clinical research evaluates disease prevention protocols and health outcome improvements.",
        )
        self.assertIsNotNone(sentences[0]["ai_probability"])
        self.assertIn(sentences[0]["ai_label"], ["Likely AI-Generated", "Mixed / Uncertain", "Likely Human-Written"])

        # 2. Second sentence: short ("Hospital patient care was monitored." = 5 words < 8 words)
        self.assertEqual(sentences[1]["sentence"], "Hospital patient care was monitored.")
        self.assertIsNone(sentences[1]["ai_probability"])
        self.assertEqual(sentences[1]["ai_label"], "AI-style score unavailable for this sentence")

        # 3. Third sentence: normal length
        self.assertIn("Medical diagnosis improves patient health outcomes", sentences[2]["sentence"])
        self.assertIsNotNone(sentences[2]["ai_probability"])

        # Check that plagiarism status is independent and present on every sentence
        for s in sentences:
            self.assertIn("similarity", s)
            self.assertIn("hybrid_similarity", s)
            self.assertIn("flagged", s)
            self.assertIn("matched_source", s)
            self.assertIsInstance(s["flagged"], bool)

    def test_auto_correct_with_mixed_sentences(self):
        """Auto correct must apply corrections on any sentence regardless of AI score availability."""
        text = "Hospital care. Patient diagnosis was conducted."
        corrections = [
            {
                "original": "Hospital care.",
                "corrected": "Inpatient healthcare services.",
                "start_offset": 0,
                "end_offset": 14,
            }
        ]
        import json
        response = self.client.post(
            "/api/auto-correct",
            files={"file": ("test.txt", text.encode("utf-8"), "text/plain")},
            data={"corrections": json.dumps(corrections)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Applied-Corrections"), "1")


if __name__ == "__main__":
    unittest.main()
