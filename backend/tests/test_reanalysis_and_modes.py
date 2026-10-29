import io
import unittest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.services.core_client import CoreWork, CoreConfigurationError, CoreRequestError


class TestReanalysisAndModes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.sample_text = (
            "Clinical diagnosis and healthcare monitoring are essential for hospitalized patients. "
            "Medical staff assess patient vital signs and heart rate to detect early signs of disease. "
            "Continuous clinical monitoring improves treatment outcomes in modern hospitals."
        )

    def test_offline_mode_sources_and_reanalysis(self):
        """Verify Offline mode uses local corpus and calculates re-analysis delta accurately."""
        # Initial analysis in offline mode
        file_obj = io.BytesIO(self.sample_text.encode("utf-8"))
        res = self.client.post(
            "/api/analyze",
            files={"file": ("report.txt", file_obj, "text/plain")},
            data={"online": "false", "student_name": "Test Student", "usn": "1VT20CS001"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["analysis_mode"], "offline")
        self.assertEqual(data["online_sources_compared"], 0)
        self.assertGreater(data["local_sources_compared"], 0)
        self.assertGreater(data["total_sources_compared"], 0)
        initial_score = data["plagiarism_score"]

        # Now test re-analysis of a revised document passing previous_score
        revised_text = (
            "Healthcare teams monitor clinical vital signs to support timely medical interventions. "
            "Hospitalized individuals receive ongoing assessment to track their overall disease progress. "
            "Routine health evaluation remains a cornerstone of inpatient patient care."
        )
        revised_file = io.BytesIO(revised_text.encode("utf-8"))
        re_res = self.client.post(
            "/api/analyze",
            files={"file": ("corrected_report.txt", revised_file, "text/plain")},
            data={
                "online": "false",
                "previous_score": str(initial_score),
                "is_reanalysis": "true",
            },
        )
        self.assertEqual(re_res.status_code, 200)
        re_data = re_res.json()
        self.assertTrue(re_data["is_reanalysis"])
        self.assertEqual(re_data["previous_score"], initial_score)
        self.assertIsNotNone(re_data["score_delta"])
        expected_delta = round(re_data["plagiarism_score"] - initial_score, 2)
        self.assertEqual(re_data["score_delta"], expected_delta)

    @patch("app.main.search_works")
    @patch("app.main.core_configured", return_value=True)
    def test_online_mode_merges_sources(self, mock_configured, mock_search):
        """Verify Online mode combines local reference corpus with CORE papers up to CORE_MAX_PAPERS."""
        mock_works = [
            CoreWork(
                title=f"Clinical Monitoring and Patient Health Study {i}",
                text=(
                    f"Patient health and clinical monitoring diagnosis treatment evaluation {i}. "
                    "This clinical healthcare study investigates hospital patient diagnosis and treatment in depth "
                    "with comprehensive clinical monitoring and essential medical evaluation protocols across diverse healthcare cohorts."
                ),
                doi=f"10.1234/test.paper.{i}",
            )
            for i in range(15)
        ]
        mock_search.return_value = (mock_works, 100)

        file_obj = io.BytesIO(self.sample_text.encode("utf-8"))
        res = self.client.post(
            "/api/analyze",
            files={"file": ("report.txt", file_obj, "text/plain")},
            data={"online": "true"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["analysis_mode"], "online")
        self.assertGreater(data["online_sources_compared"], 0)
        self.assertEqual(
            data["total_sources_compared"],
            data["local_sources_compared"] + data["online_sources_compared"],
        )

    @patch("app.main.search_works")
    def test_online_mode_does_not_silently_fallback_on_unconfigured(self, mock_search):
        """Verify Online mode fails clearly if CORE is unconfigured rather than silently falling back."""
        mock_search.side_effect = CoreConfigurationError("CORE_API_KEY is not configured")

        file_obj = io.BytesIO(self.sample_text.encode("utf-8"))
        res = self.client.post(
            "/api/analyze",
            files={"file": ("report.txt", file_obj, "text/plain")},
            data={"online": "true"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("CORE_API_KEY", res.json()["detail"])

    @patch("app.main.search_works")
    def test_online_mode_does_not_silently_fallback_on_request_failure(self, mock_search):
        """Verify Online mode reports HTTP 502 with error message if CORE request fails."""
        mock_search.side_effect = CoreRequestError("CORE connection timed out")

        file_obj = io.BytesIO(self.sample_text.encode("utf-8"))
        res = self.client.post(
            "/api/analyze",
            files={"file": ("report.txt", file_obj, "text/plain")},
            data={"online": "true"},
        )
        self.assertEqual(res.status_code, 502)
        self.assertIn("Online academic search failed", res.json()["detail"])

    @patch("app.main.search_works")
    @patch("app.main.core_configured", return_value=True)
    def test_online_mode_does_not_silently_fallback_when_zero_papers_found(self, mock_configured, mock_search):
        """Verify Online mode returns HTTP 502 instead of silently returning offline mode when 0 papers are found."""
        mock_search.return_value = ([], 0)

        file_obj = io.BytesIO(self.sample_text.encode("utf-8"))
        res = self.client.post(
            "/api/analyze",
            files={"file": ("report.txt", file_obj, "text/plain")},
            data={"online": "true"},
        )
        self.assertEqual(res.status_code, 502)
        self.assertIn("could not retrieve matching academic papers", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
