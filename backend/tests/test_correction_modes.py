"""Unit tests for Correction Agent modes (Academic, Human, Simple).

Tests verify:
1. Academic mode returns formal academic rewrite.
2. Human mode returns natural active rewrite.
3. Simple mode returns plain-language rewrite.
4. The outputs are not merely copies of the original with different labels.
5. Modes do not reuse the same cached output incorrectly.
6. Selected mode sets primary rewrite and applies correct version.
7. Medical meaning, diagnoses, findings, and terms remain accurate.
8. Failed generation is reported clearly rather than presenting unchanged original.
"""
import os
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app import settings
from app.services import gemini_client
from app.services import correction_agent as ca
from app.main import app


SAMPLE_NEPHRITIC_SENTENCE = (
    "Nephritic syndrome is characterized by hematuria, hypertension, and red blood cell casts, "
    "whereas nephrotic syndrome presents with heavy proteinuria, hypoalbuminemia, and severe edema."
)

SAMPLE_ACADEMIC_REWRITE = (
    "While nephritic syndrome typically manifests with hypertension, hematuria, and red blood cell casts, "
    "nephrotic syndrome is clinically defined by severe edema, hypoalbuminemia, and massive proteinuria."
)

SAMPLE_HUMAN_REWRITE = (
    "Nephritic syndrome is marked by hematuria, hypertension, and red blood cell casts, "
    "whereas patients with nephrotic syndrome experience heavy proteinuria, hypoalbuminemia, and severe edema."
)

SAMPLE_SIMPLE_REWRITE = (
    "Nephritic syndrome causes hematuria, hypertension, and red blood cell casts. "
    "In contrast, nephrotic syndrome presents with heavy proteinuria, hypoalbuminemia, and severe edema."
)

REQUIRED_MEDICAL_TERMS = [
    "hematuria",
    "hypertension",
    "red blood cell",
    "proteinuria",
    "hypoalbuminemia",
    "edema",
]


class TestCorrectionModesWithMockedGemini(unittest.TestCase):
    def setUp(self):
        gemini_client.invalidate_client()
        self._orig_env = os.environ.copy()
        os.environ["GEMINI_API_KEY"] = "mock-gemini-key"

    def tearDown(self):
        gemini_client.invalidate_client()
        os.environ.clear()
        os.environ.update(self._orig_env)

    def _mock_gemini_generator(self, prompt, **kwargs):
        p_lower = prompt.lower()
        if "target mode: human" in p_lower:
            return SAMPLE_HUMAN_REWRITE
        elif "target mode: simple" in p_lower:
            return SAMPLE_SIMPLE_REWRITE
        elif "target mode: academic" in p_lower:
            return SAMPLE_ACADEMIC_REWRITE
        elif "human" in p_lower or "university student" in p_lower:
            return SAMPLE_HUMAN_REWRITE
        elif "simple" in p_lower or "school-level" in p_lower or "educational guide" in p_lower:
            return SAMPLE_SIMPLE_REWRITE
        return SAMPLE_ACADEMIC_REWRITE

    def test_all_three_modes_produce_independent_different_rewrites(self):
        with patch("app.services.gemini_client.generate_text", side_effect=self._mock_gemini_generator):
            rewrites = ca.rewrite_suggestions(SAMPLE_NEPHRITIC_SENTENCE, strength="moderate")

            self.assertIn("academic", rewrites)
            self.assertIn("human", rewrites)
            self.assertIn("simple", rewrites)

            # 1. Academic mode returns formal rewrite
            self.assertEqual(rewrites["academic"], SAMPLE_ACADEMIC_REWRITE)
            # 2. Human mode returns natural rewrite
            self.assertEqual(rewrites["human"], SAMPLE_HUMAN_REWRITE)
            # 3. Simple mode returns plain-language rewrite
            self.assertEqual(rewrites["simple"], SAMPLE_SIMPLE_REWRITE)

            # 4. Outputs are not copies of original
            self.assertNotEqual(rewrites["academic"].lower(), SAMPLE_NEPHRITIC_SENTENCE.lower())
            self.assertNotEqual(rewrites["human"].lower(), SAMPLE_NEPHRITIC_SENTENCE.lower())
            self.assertNotEqual(rewrites["simple"].lower(), SAMPLE_NEPHRITIC_SENTENCE.lower())

            # 5. Modes do not reuse the same cached output incorrectly
            self.assertNotEqual(rewrites["academic"], rewrites["human"])
            self.assertNotEqual(rewrites["human"], rewrites["simple"])
            self.assertNotEqual(rewrites["academic"], rewrites["simple"])

    def test_medical_terminology_and_facts_preserved(self):
        with patch("app.services.gemini_client.generate_text", side_effect=self._mock_gemini_generator):
            rewrites = ca.rewrite_suggestions(SAMPLE_NEPHRITIC_SENTENCE, strength="moderate")
            for mode, text in rewrites.items():
                for term in REQUIRED_MEDICAL_TERMS:
                    self.assertIn(
                        term.lower(),
                        text.lower(),
                        f"Mode '{mode}' omitted required medical term '{term}'",
                    )

    def test_correct_sentence_honors_requested_mode(self):
        with patch("app.services.gemini_client.generate_text", side_effect=self._mock_gemini_generator):
            # Academic mode request
            res_acad = ca.correct_sentence(
                SAMPLE_NEPHRITIC_SENTENCE,
                "Nephrology Journal",
                75.0,
                mode="academic",
            )
            self.assertEqual(res_acad["mode"], "academic")
            self.assertEqual(res_acad["rewritten"], SAMPLE_ACADEMIC_REWRITE)
            self.assertIsNone(res_acad["error"])

            # Human mode request
            res_human = ca.correct_sentence(
                SAMPLE_NEPHRITIC_SENTENCE,
                "Nephrology Journal",
                75.0,
                mode="human",
            )
            self.assertEqual(res_human["mode"], "human")
            self.assertEqual(res_human["rewritten"], SAMPLE_HUMAN_REWRITE)
            self.assertIsNone(res_human["error"])

            # Simple mode request
            res_simple = ca.correct_sentence(
                SAMPLE_NEPHRITIC_SENTENCE,
                "Nephrology Journal",
                75.0,
                mode="simple",
            )
            self.assertEqual(res_simple["mode"], "simple")
            self.assertEqual(res_simple["rewritten"], SAMPLE_SIMPLE_REWRITE)
            self.assertIsNone(res_simple["error"])

    def test_offline_fallback_produces_structured_contrastive_clauses(self):
        """When Gemini is not configured, offline structural rules restructure contrastive clauses."""
        os.environ.pop("GEMINI_API_KEY", None)
        gemini_client.invalidate_client()

        rewrites, provider = ca.rewrite_suggestions(
            SAMPLE_NEPHRITIC_SENTENCE,
            strength="moderate",
            return_provider=True,
        )
        self.assertEqual(provider, "offline")

        # Must not be copies of original
        self.assertNotEqual(rewrites["academic"].lower(), SAMPLE_NEPHRITIC_SENTENCE.lower())
        self.assertNotEqual(rewrites["human"].lower(), SAMPLE_NEPHRITIC_SENTENCE.lower())
        self.assertNotEqual(rewrites["simple"].lower(), SAMPLE_NEPHRITIC_SENTENCE.lower())

        # Must not contain broken prepositional phrases like "By with"
        for mode, text in rewrites.items():
            self.assertNotIn("by with", text.lower())
            self.assertNotIn("in practical terms", text.lower())
            self.assertNotIn("overall,", text.lower())

        # Must preserve essential medical terms
        for term in REQUIRED_MEDICAL_TERMS:
            self.assertIn(term.lower(), rewrites["academic"].lower())
            self.assertIn(term.lower(), rewrites["human"].lower())
            self.assertIn(term.lower(), rewrites["simple"].lower())

    def test_failed_generation_reported_clearly_never_presents_unchanged_original(self):
        """When generation fails or returns empty, clear error is returned."""
        os.environ["GEMINI_API_KEY"] = "mock-gemini-key"

        # Mock Gemini returning empty or identical string
        with patch("app.services.gemini_client.generate_text", return_value=""):
            with patch("app.services.correction_agent._best_offline_rewrite", return_value=None):
                res = ca.correct_sentence(
                    "Some irregular sentence that cannot be rewritten offline.",
                    "SourceDoc",
                    60.0,
                    mode="human",
                )
                self.assertIsNotNone(res["error"])
                self.assertNotEqual(res["rewritten"], res["original"])


class TestCorrectionApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self._orig_env = os.environ.copy()
        os.environ["GEMINI_API_KEY"] = "mock-key"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_api_correct_supports_mode_parameter(self):
        def mock_generate(prompt, **kwargs):
            p_lower = prompt.lower()
            if "target mode: human" in p_lower:
                return SAMPLE_HUMAN_REWRITE
            elif "target mode: simple" in p_lower:
                return SAMPLE_SIMPLE_REWRITE
            return SAMPLE_ACADEMIC_REWRITE

        with patch("app.services.gemini_client.generate_text", side_effect=mock_generate):
            payload = {
                "sentence": SAMPLE_NEPHRITIC_SENTENCE,
                "matched_source": "Source X",
                "similarity": 80.0,
                "mode": "human",
                "start_offset": 10,
                "end_offset": 180,
            }
            res = self.client.post("/api/correct", json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["mode"], "human")
            self.assertEqual(data["rewritten"], SAMPLE_HUMAN_REWRITE)
            self.assertEqual(data["start_offset"], 10)
            self.assertEqual(data["end_offset"], 180)
            self.assertIn("academic", data["rewrites"])
            self.assertIn("human", data["rewrites"])
            self.assertIn("simple", data["rewrites"])


if __name__ == "__main__":
    unittest.main()
