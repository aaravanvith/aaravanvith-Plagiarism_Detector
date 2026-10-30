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
import io
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

    @patch("app.services.correction_agent.ollama_rewrite", return_value=None)
    @patch("app.services.gemini_client.configured", return_value=False)
    def test_offline_fallback_produces_structured_contrastive_clauses(self, mock_gemini_cfg, mock_ollama):
        """When Gemini is not configured, offline structural rules restructure contrastive clauses."""

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

    @patch("app.services.correction_agent.ollama_rewrite", return_value=None)
    @patch("app.services.gemini_client.configured", return_value=False)
    def test_biomedical_sentences_with_numbers_and_acronyms_offline_fallback(self, mock_gemini_cfg, mock_ollama):
        """Flagged clinical sentences with numbers, units, and acronyms must succeed in offline fallback."""
        clinical_sentences = [
            (
                "Diagnosis of diabetes mellitus type 2 requires fasting plasma glucose >= 126 mg/dL.",
                ["126", "diabetes", "fasting plasma glucose"],
            ),
            (
                "The ECG revealed ST-segment elevation in leads V1-V4, consistent with an anterior STEMI.",
                ["ecg", "stemi", "v1-v4"],
            ),
            (
                "Patients aged 65 and older exhibited a 42% reduction in systolic blood pressure following 50 mg daily losartan therapy.",
                ["65", "42%", "50 mg", "losartan"],
            ),
            (
                "HbA1c levels decreased by 1.5% after 12 weeks of metformin (1000 mg/day) intervention.",
                ["hba1c", "1.5%", "metformin", "1000"],
            ),
        ]

        for sentence, expected_terms in clinical_sentences:
            for mode in ["academic", "human", "simple"]:
                res = ca.correct_sentence(sentence, "Medical Journal", 82.0, mode=mode)
                self.assertIsNone(res["error"], f"Sentence failed with error: {res['error']} for mode {mode}")
                self.assertTrue(res["is_fallback"])
                self.assertEqual(res["provider"], "offline")
                self.assertTrue(bool(res["rewritten"]))
                self.assertNotEqual(res["rewritten"].lower(), sentence.lower())

                # Check all 3 mode variants exist and are non-empty
                self.assertEqual(len(res["rewrites"]), 3)
                for m, rewrite in res["rewrites"].items():
                    self.assertTrue(bool(rewrite), f"Mode '{m}' produced empty rewrite for '{sentence}'")
                    self.assertNotEqual(rewrite.lower(), sentence.lower())

    def test_llm_cleaning_strips_preambles_and_markdown_headers(self):
        """LLM responses with conversational introductions or markdown headers must be cleanly extracted."""
        sample_responses = [
            (
                'Here is the academic rewrite:\n"Acute myocardial infarction is indicated by elevated cardiac troponin levels."',
                "Acute myocardial infarction is indicated by elevated cardiac troponin levels.",
            ),
            (
                '**Academic:**\nAcute myocardial infarction is indicated by elevated cardiac troponin levels.',
                "Acute myocardial infarction is indicated by elevated cardiac troponin levels.",
            ),
            (
                'Here are a few ways to rewrite the sentence, depending on the desired tone:\n\n**Professional & Academic**\n* "Accurate clinical diagnosis is paramount to patient well-being."',
                "Accurate clinical diagnosis is paramount to patient well-being.",
            ),
        ]
        for raw, expected in sample_responses:
            cleaned = ca._clean_llm_output(raw)
            self.assertEqual(cleaned, expected)

    @patch("app.services.correction_agent.ollama_rewrite", return_value=None)
    @patch("app.services.gemini_client.configured", return_value=False)
    def test_offline_mode_rejects_awkward_phrasings_and_preserves_clinical_grammar(self, mock_gemini_cfg, mock_ollama):
        """Offline rewrites must be grammatically fluent and never contain awkward machine templates."""
        banned_phrases = [
            "form part of the work",
            "is used to require",
            "works to require",
            "helps require",
            "works to exhibit",
            "is used to exhibit",
            "works to decrease",
            "is used to decrease",
            "required by diagnosis",
            "in clinical evaluation,",
            "from a practical perspective,",
        ]

        clinical_cases = [
            "Diagnosis of diabetes mellitus type 2 requires fasting plasma glucose >= 126 mg/dL.",
            "The ECG revealed ST-segment elevation in leads V1-V4, consistent with an anterior STEMI.",
            "Patients aged 65 and older exhibited a 42% reduction in systolic blood pressure following 50 mg daily losartan therapy.",
            "HbA1c levels decreased by 1.5% after 12 weeks of metformin (1000 mg/day) intervention.",
            "The control cohort did not demonstrate significant renal functional recovery without renal replacement therapy.",
        ]

        for sentence in clinical_cases:
            res = ca.correct_sentence(sentence, "Medical Journal", 85.0, mode="academic")
            self.assertIsNone(res["error"])
            rewrites = res["rewrites"]

            # Confirm all 3 modes generated distinct rewrites
            self.assertNotEqual(rewrites["academic"].lower(), rewrites["human"].lower())
            self.assertNotEqual(rewrites["academic"].lower(), rewrites["simple"].lower())
            self.assertNotEqual(rewrites["human"].lower(), rewrites["simple"].lower())

            for mode_name, text in rewrites.items():
                text_low = text.lower()
                for banned in banned_phrases:
                    self.assertNotIn(
                        banned,
                        text_low,
                        f"Mode '{mode_name}' produced banned awkward phrasing '{banned}': {text}",
                    )

    @patch("app.services.correction_agent.ollama_rewrite", return_value=None)
    @patch("app.services.gemini_client.configured", return_value=False)
    def test_clinical_numerical_thresholds_units_and_negations_preserved(self, mock_gemini_cfg, mock_ollama):
        """Preserves numbers, comparison operators, medical units, and polarities in all 3 offline modes."""
        test_cases = [
            (
                "Diagnosis of diabetes mellitus type 2 requires fasting plasma glucose >= 126 mg/dL.",
                {
                    "must_have": [">= 126", "mg/dl", "diabetes mellitus type 2"],
                    "has_negation": False,
                },
            ),
            (
                "The control cohort did not demonstrate significant renal functional recovery without renal replacement therapy.",
                {
                    "must_have": ["renal replacement therapy", "renal functional recovery"],
                    "has_negation": True,
                },
            ),
            (
                "Patients with serum ferritin >= 500 ng/mL had higher mortality rates (p < 0.01).",
                {
                    "must_have": [">= 500", "ng/ml", "0.01", "ferritin"],
                    "has_negation": False,
                },
            ),
        ]

        for sentence, rules in test_cases:
            res = ca.correct_sentence(sentence, "Clinical Study", 80.0, mode="academic")
            self.assertIsNone(res["error"], f"Failed for '{sentence}': {res['error']}")
            rewrites = res["rewrites"]

            for mode_name, rewrite in rewrites.items():
                rewrite_low = rewrite.lower()
                for term in rules["must_have"]:
                    self.assertIn(
                        term.lower(),
                        rewrite_low,
                        f"Term '{term}' missing from '{mode_name}' rewrite: '{rewrite}'",
                    )
                if rules["has_negation"]:
                    self.assertTrue(
                        ca._has_negation(rewrite),
                        f"Negation missing from '{mode_name}' rewrite: '{rewrite}'",
                    )

    @patch("app.services.correction_agent.ollama_rewrite", return_value=None)
    @patch("app.services.gemini_client.configured", return_value=False)
    def test_unparseable_sentence_returns_safe_error_instead_of_awkward_text(self, mock_gemini_cfg, mock_ollama):
        """When an unparseable sentence cannot be safely restructured, return clear error without broken text."""
        res = ca.correct_sentence("123456 completely unparseable fragment xyz.", "Source", 70.0, mode="academic")
        self.assertIsNotNone(res["error"])
        self.assertIn("Could not generate an independent academic rewrite", res["error"])
        self.assertEqual(res["rewrites"]["academic"], "")
        self.assertEqual(res["rewrites"]["human"], "")
        self.assertEqual(res["rewrites"]["simple"], "")

    @patch("app.services.correction_agent.ollama_rewrite", return_value=None)
    @patch("app.services.gemini_client.configured", return_value=False)
    def test_definitional_pediatric_nephrotic_syndrome_offline_fallback(self, mock_gemini_cfg, mock_ollama):
        """Exact sentence from project review screenshot must generate valid, distinct rewrites across all 3 modes."""
        sentence = (
            "Pediatric nephrotic syndrome (NS) is a complex renal disorder characterized by "
            "proteinuria, hypoalbuminemia, edema, hyperlipidemia, and risk of chronic kidney disease."
        )
        res = ca.correct_sentence(sentence, "PubMed Article 42541462", 88.0, mode="academic")
        self.assertIsNone(res["error"], f"Expected no error, got: {res['error']}")
        self.assertTrue(res["is_fallback"])
        self.assertEqual(res["provider"], "offline")

        rewrites = res["rewrites"]
        self.assertIn("academic", rewrites)
        self.assertIn("human", rewrites)
        self.assertIn("simple", rewrites)

        acad, hum, simp = rewrites["academic"], rewrites["human"], rewrites["simple"]
        self.assertTrue(bool(acad), "Academic rewrite must not be empty")
        self.assertTrue(bool(hum), "Human rewrite must not be empty")
        self.assertTrue(bool(simp), "Simple rewrite must not be empty")

        # Distinctness across all 3 modes
        self.assertNotEqual(acad.lower(), sentence.lower())
        self.assertNotEqual(hum.lower(), sentence.lower())
        self.assertNotEqual(simp.lower(), sentence.lower())
        self.assertNotEqual(acad.lower(), hum.lower())
        self.assertNotEqual(acad.lower(), simp.lower())
        self.assertNotEqual(hum.lower(), simp.lower())

        # Preservation of all core medical terms
        required_terms = [
            "pediatric nephrotic syndrome",
            "complex renal disorder",
            "proteinuria",
            "hypoalbuminemia",
            "edema",
            "hyperlipidemia",
            "chronic kidney disease",
        ]
        for term in required_terms:
            for m, rew in rewrites.items():
                self.assertIn(term.lower(), rew.lower(), f"Term '{term}' missing from {m} rewrite: '{rew}'")

    @patch("app.services.correction_agent.ollama_rewrite", return_value=None)
    @patch("app.services.gemini_client.configured", return_value=False)
    def test_all_four_biomedical_sentence_categories_offline_fallback(self, mock_gemini_cfg, mock_ollama):
        """Comprehensive verification across: (a) Definitional, (b) Numerical/Units, (c) Diagnostic, (d) Observational."""
        categories = {
            "definitional": (
                "Pediatric nephrotic syndrome (NS) is a complex renal disorder characterized by proteinuria, hypoalbuminemia, edema, hyperlipidemia, and risk of chronic kidney disease.",
                [">= 0", "proteinuria", "hypoalbuminemia", "edema", "hyperlipidemia", "chronic kidney disease"],
            ),
            "numerical_thresholds": (
                "Patients with serum ferritin >= 500 ng/mL had higher mortality rates (p < 0.01).",
                [">= 500", "ng/ml", "0.01", "ferritin"],
            ),
            "diagnostic_criteria": (
                "The diagnosis of acute myocardial infarction requires elevated cardiac troponin.",
                ["acute myocardial infarction", "elevated cardiac troponin"],
            ),
            "observational_clinical": (
                "The cohort study evaluated 450 pediatric participants over a 12-month period.",
                ["450", "pediatric participants", "12-month period"],
            ),
            "pharmacological_reduction": (
                "Treatment with metformin reduced HbA1c levels by 1.5% in patients with type 2 diabetes.",
                ["metformin", "hba1c", "1.5%", "type 2 diabetes"],
            ),
            "biomarker_correlation": (
                "Analysis demonstrated significant correlation between biomarker expression and disease severity.",
                ["significant correlation", "biomarker expression", "disease severity"],
            ),
        }

        for cat_name, (sentence, check_items) in categories.items():
            res = ca.correct_sentence(sentence, f"Journal-{cat_name}", 80.0, mode="academic")
            self.assertIsNone(res["error"], f"Category '{cat_name}' failed with error: {res['error']}")
            self.assertEqual(res["provider"], "offline")

            rewrites = res["rewrites"]
            acad, hum, simp = rewrites["academic"], rewrites["human"], rewrites["simple"]

            # Must all be valid non-empty strings
            self.assertTrue(bool(acad), f"Empty academic rewrite for '{cat_name}'")
            self.assertTrue(bool(hum), f"Empty human rewrite for '{cat_name}'")
            self.assertTrue(bool(simp), f"Empty simple rewrite for '{cat_name}'")

            # Must all be distinct
            self.assertNotEqual(acad.lower(), sentence.lower())
            self.assertNotEqual(hum.lower(), sentence.lower())
            self.assertNotEqual(simp.lower(), sentence.lower())
            self.assertNotEqual(acad.lower(), hum.lower(), f"Academic and human identical for '{cat_name}'")
            self.assertNotEqual(acad.lower(), simp.lower(), f"Academic and simple identical for '{cat_name}'")
            self.assertNotEqual(hum.lower(), simp.lower(), f"Human and simple identical for '{cat_name}'")

            # Verify factual terms and numbers
            for item in check_items:
                if item == ">= 0":
                    continue
                for m, rew in rewrites.items():
                    self.assertIn(item.lower(), rew.lower(), f"Item '{item}' missing from {m} in '{cat_name}': '{rew}'")


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

    def test_auto_correct_endpoint_applies_correction_cleanly(self):
        doc_text = f"Introduction. {SAMPLE_NEPHRITIC_SENTENCE} Conclusion."
        start = doc_text.find(SAMPLE_NEPHRITIC_SENTENCE)
        end = start + len(SAMPLE_NEPHRITIC_SENTENCE)

        corrections_payload = [
            {
                "original": SAMPLE_NEPHRITIC_SENTENCE,
                "corrected": SAMPLE_ACADEMIC_REWRITE,
                "start_offset": start,
                "end_offset": end,
                "mode": "academic",
            }
        ]
        import json
        res = self.client.post(
            "/api/auto-correct",
            files={"file": ("report.txt", io.BytesIO(doc_text.encode("utf-8")), "text/plain")},
            data={"corrections": json.dumps(corrections_payload)},
        )
        self.assertEqual(res.status_code, 200)
        corrected_content = res.content.decode("utf-8")
        self.assertIn(SAMPLE_ACADEMIC_REWRITE, corrected_content)
        self.assertNotIn(SAMPLE_NEPHRITIC_SENTENCE, corrected_content)
        self.assertTrue(corrected_content.startswith("Introduction. "))
        self.assertTrue(corrected_content.endswith(" Conclusion."))

    @patch("app.main.load_reference_corpus", return_value={"ref_1": "Nephritic syndrome is characterized by hematuria, hypertension, and red blood cell casts."})
    def test_reanalysis_flow_after_applying_correction(self, mock_corpus):
        """Full re-analysis flow: original document analyzed -> corrected via auto-correct -> re-analyzed."""
        original_doc = (
            "Medical report on renal disease diagnosis and clinical patient treatment. "
            f"{SAMPLE_NEPHRITIC_SENTENCE} "
            "Conclusion of the hospital clinical investigation on patient kidney healthcare."
        )

        # 1. Initial analysis
        analyze_res = self.client.post(
            "/api/analyze",
            files={"file": ("report.txt", io.BytesIO(original_doc.encode("utf-8")), "text/plain")},
            data={"mode": "offline"},
        )
        self.assertEqual(analyze_res.status_code, 200)
        initial_data = analyze_res.json()
        self.assertEqual(initial_data["analysis_mode"], "offline")
        self.assertIn("plagiarism_score", initial_data)

        # 2. Generate and apply correction
        target_sentence = SAMPLE_NEPHRITIC_SENTENCE
        start = original_doc.find(target_sentence)
        end = start + len(target_sentence)
        self.assertGreater(start, -1)

        corrections_payload = [
            {
                "original": target_sentence,
                "corrected": SAMPLE_ACADEMIC_REWRITE,
                "start_offset": start,
                "end_offset": end,
                "mode": "academic",
            }
        ]
        import json
        apply_res = self.client.post(
            "/api/auto-correct",
            files={"file": ("report.txt", io.BytesIO(original_doc.encode("utf-8")), "text/plain")},
            data={"corrections": json.dumps(corrections_payload)},
        )
        self.assertEqual(apply_res.status_code, 200)
        corrected_content = apply_res.content

        # 3. Re-analysis on corrected document
        reanalyze_res = self.client.post(
            "/api/analyze",
            files={"file": ("report.txt", io.BytesIO(corrected_content), "text/plain")},
            data={"mode": "offline"},
        )
        self.assertEqual(reanalyze_res.status_code, 200)
        reanalyze_data = reanalyze_res.json()
        self.assertEqual(reanalyze_data["analysis_mode"], "offline")
        self.assertIn("plagiarism_score", reanalyze_data)
        # Verify valid updated report generated from actual text
        self.assertIsInstance(reanalyze_data["plagiarism_score"], (int, float))
        self.assertGreater(reanalyze_data["local_sources_compared"], 0)


if __name__ == "__main__":
    unittest.main()
