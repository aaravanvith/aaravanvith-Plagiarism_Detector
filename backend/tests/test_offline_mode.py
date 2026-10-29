"""Tests for Offline Analysis mode, dataset loading, and local repository integrity."""
import io
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import (
    app,
    load_reference_corpus,
    get_reference_corpus_dir,
    get_healthcare_corpus_dir,
)
from app.database import get_db, Base


class TestOfflineMode(unittest.TestCase):
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
        cls.db = TestingSessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_directory_resolvers(self):
        """Directory resolvers must find existing folders containing text files."""
        ref_dir = get_reference_corpus_dir()
        healthcare_dir = get_healthcare_corpus_dir()

        self.assertTrue(ref_dir.exists(), f"Reference corpus dir not found: {ref_dir}")
        self.assertTrue(healthcare_dir.exists(), f"Healthcare dataset dir not found: {healthcare_dir}")

        ref_txts = list(ref_dir.glob("*.txt"))
        healthcare_txts = list(healthcare_dir.glob("*.txt"))

        self.assertGreaterEqual(len(ref_txts), 4, "Expected at least 4 reference files")
        self.assertGreaterEqual(len(healthcare_txts), 469, "Expected at least 469 PubMed files")

    def test_load_reference_corpus_loads_473_sources(self):
        """load_reference_corpus must load the 473 expected academic sources."""
        corpus = load_reference_corpus(self.db)
        self.assertGreaterEqual(len(corpus), 473, f"Expected >= 473 sources, got {len(corpus)}")

        # Check key sample sources
        self.assertIn("academic_integrity", corpus)
        self.assertIn("ml_intro", corpus)
        pubmed_keys = [k for k in corpus.keys() if k.startswith("pubmed::")]
        self.assertGreaterEqual(len(pubmed_keys), 469, f"Expected >= 469 PubMed sources, got {len(pubmed_keys)}")

    def test_offline_mode_does_not_call_core_api(self):
        """Offline analysis must NOT invoke CORE academic search API."""
        sample_text = (
            "This study investigates clinical patient treatment protocols in hospital healthcare systems. "
            "Medical data analysis was performed to evaluate clinical disease outcomes and patient health."
        )

        with patch("app.main.build_online_corpus") as mock_online:
            response = self.client.post(
                "/api/analyze",
                files={"file": ("test_report.txt", io.BytesIO(sample_text.encode("utf-8")), "text/plain")},
                data={"online": "false"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            mock_online.assert_not_called()

            data = response.json()
            self.assertEqual(data["analysis_mode"], "offline")
            self.assertEqual(data["online_sources_compared"], 0)
            self.assertGreaterEqual(data["total_sources_compared"], 473)
            self.assertGreaterEqual(data["local_sources_compared"], 473)

    def test_offline_mode_without_api_keys(self):
        """Offline analysis must succeed completely without CORE_API_KEY or GEMINI_API_KEY."""
        sample_text = (
            "Clinical research evaluates healthcare patient monitoring and diagnosis methods in hospitals. "
            "The study evaluates patient care protocols and medical treatment efficacy for disease management."
        )

        with patch.dict(os.environ, {"CORE_API_KEY": "", "GEMINI_API_KEY": ""}, clear=False):
            response = self.client.post(
                "/api/analyze",
                files={"file": ("no_key_report.txt", io.BytesIO(sample_text.encode("utf-8")), "text/plain")},
                data={"online": "false"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["analysis_mode"], "offline")
            self.assertIn("plagiarism_score", data)
            self.assertGreaterEqual(data["total_sources_compared"], 473)

    def test_offline_mode_error_when_dataset_missing_or_empty(self):
        """Missing or empty local dataset must raise a clear 503 error instead of silent online fallback."""
        sample_text = (
            "Clinical research evaluates healthcare patient monitoring and diagnosis methods in hospitals. "
            "The study evaluates patient care protocols and medical treatment efficacy for disease management."
        )

        with patch("app.main.load_reference_corpus", return_value={}):
            response = self.client.post(
                "/api/analyze",
                files={"file": ("missing_corpus.txt", io.BytesIO(sample_text.encode("utf-8")), "text/plain")},
                data={"online": "false"},
            )
            self.assertEqual(response.status_code, 503)
            self.assertIn("Local reference dataset is unavailable or empty", response.json()["detail"])

    def test_repository_stats_includes_bundled_corpus(self):
        """GET /api/repository/stats must report bundled corpus sources (473)."""
        response = self.client.get("/api/repository/stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(data["total_documents"], 473)
        self.assertGreaterEqual(data["bundled_sources"], 473)

    def test_repository_documents_surfaces_bundled_sources(self):
        """GET /api/repository/documents must surface bundled local sources."""
        response = self.client.get("/api/repository/documents?limit=10")
        self.assertEqual(response.status_code, 200)
        items = response.json()
        self.assertGreater(len(items), 0)
        self.assertTrue(any("bundled" in str(item.get("id", "")) for item in items))

    def test_online_mode_successful_retrieval_and_metadata(self):
        """Online mode with successful CORE retrieval must record online sources and mode."""
        sample_text = (
            "Clinical research evaluates healthcare patient monitoring and diagnosis methods in hospitals. "
            "The study evaluates patient care protocols and medical treatment efficacy for disease management."
        )
        mock_online_corpus = {
            "online::CORE::10.1234/test.paper": (
                "Clinical research evaluates healthcare patient monitoring and diagnosis methods in hospitals. "
                "Retrospective analysis of hospital patient care and medical diagnosis."
            )
        }

        with patch("app.main.build_online_corpus", return_value=mock_online_corpus) as mock_builder:
            response = self.client.post(
                "/api/analyze",
                files={"file": ("online_report.txt", io.BytesIO(sample_text.encode("utf-8")), "text/plain")},
                data={"online": "true"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            mock_builder.assert_called_once()

            data = response.json()
            self.assertEqual(data["analysis_mode"], "online")
            self.assertEqual(data["online_sources_compared"], 1)
            self.assertGreaterEqual(data["local_sources_compared"], 473)
            self.assertEqual(data["total_sources_compared"], data["local_sources_compared"] + 1)
            # Online paper should be prioritized in preview sources list
            self.assertTrue(any(s.startswith("online::CORE") for s in data["sources_compared"]))

    def test_online_mode_fails_explicitly_when_core_fails(self):
        """Online mode must NOT silently fall back to local analysis when CORE retrieval fails."""
        sample_text = (
            "Clinical research evaluates healthcare patient monitoring and diagnosis methods in hospitals. "
            "The study evaluates patient care protocols and medical treatment efficacy for disease management."
        )

        from app.services.core_client import CoreRequestError
        with patch("app.main.search_works", side_effect=CoreRequestError("CORE connection timed out")):
            response = self.client.post(
                "/api/analyze",
                files={"file": ("failing_online.txt", io.BytesIO(sample_text.encode("utf-8")), "text/plain")},
                data={"online": "true"},
            )
            # Must return HTTP 502 with clear error, NOT silent local success
            self.assertEqual(response.status_code, 502)
            self.assertIn("Online academic search failed", response.json()["detail"])

    def test_online_mode_fails_explicitly_when_core_unconfigured(self):
        """Online mode must return HTTP 400 when CORE_API_KEY is not configured."""
        sample_text = (
            "Clinical research evaluates healthcare patient monitoring and diagnosis methods in hospitals. "
            "The study evaluates patient care protocols and medical treatment efficacy for disease management."
        )

        with patch.dict(os.environ, {"CORE_API_KEY": ""}, clear=False):
            with patch("app.services.core_client.configured", return_value=False):
                response = self.client.post(
                    "/api/analyze",
                    files={"file": ("unconfigured_online.txt", io.BytesIO(sample_text.encode("utf-8")), "text/plain")},
                    data={"online": "true"},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("requires a valid CORE_API_KEY", response.json()["detail"])

    def test_online_mode_fails_when_no_online_papers_found(self):
        """Online mode must return HTTP 502 when CORE returns 0 usable academic papers."""
        sample_text = (
            "Clinical research evaluates healthcare patient monitoring and diagnosis methods in hospitals. "
            "The study evaluates patient care protocols and medical treatment efficacy for disease management."
        )

        with patch("app.main.search_works", return_value=([], 0)):
            response = self.client.post(
                "/api/analyze",
                files={"file": ("empty_online.txt", io.BytesIO(sample_text.encode("utf-8")), "text/plain")},
                data={"online": "true"},
            )
            self.assertEqual(response.status_code, 502)
            self.assertIn("could not retrieve matching academic papers from CORE", response.json()["detail"])

    def test_online_mode_enforces_max_pages_ceiling(self):
        """build_online_corpus must stop at max_pages (e.g. 3) and not paginate indefinitely."""
        from app.services.core_client import CoreWork
        from app.main import build_online_corpus

        sample_text = (
            "Clinical research evaluates healthcare patient monitoring and diagnosis methods in hospitals. "
            "The study evaluates patient care protocols and medical treatment efficacy for disease management."
        )

        call_count = 0

        def mock_search(query, limit=10, offset=0):
            nonlocal call_count
            call_count += 1
            # Return 2 relevant works on every call, total_hits = 100,000 (would go on forever without page cap)
            # Need >= 20 words so length check in build_online_corpus passes.
            sample_body = (
                "Clinical patient monitoring in hospital care evaluates treatment and disease management. "
                "Medical data analysis supports clinical diagnosis and patient healthcare outcomes across hospital facilities."
            )
            # Return 10 works (2 relevant, 8 irrelevant) on every call, total_hits = 100,000
            # Without page limit, this would continue through thousands of pages because
            # consecutive_empty_pages resets on every page!
            works = [
                CoreWork(
                    title=f"Hospital Patient Study {offset + 1}",
                    text=sample_body,
                    doi=f"10.1000/test.{offset + 1}",
                ),
                CoreWork(
                    title=f"Clinical Diagnosis Protocol {offset + 2}",
                    text=sample_body,
                    doi=f"10.1000/test.{offset + 2}",
                ),
            ] + [
                CoreWork(
                    title=f"Unrelated Topic {offset + i}",
                    text="Astronomical astrophysics galactic observation physics mathematics quantum mechanics relativity telescope.",
                    doi=f"10.1000/astro.{offset + i}",
                )
                for i in range(3, 11)
            ]
            return works, 100000

        with patch("app.main.search_works", side_effect=mock_search):
            corpus = build_online_corpus(sample_text)

        # Must execute exactly 3 pages (the configured max_pages ceiling), NOT 74 or infinite
        self.assertEqual(call_count, 3)
        self.assertEqual(len(corpus), 6)

    def test_online_mode_stops_early_when_max_papers_reached(self):
        """build_online_corpus must stop immediately when max_online_papers is reached."""
        from app.services.core_client import CoreWork
        from app.main import build_online_corpus

        sample_text = (
            "Clinical research evaluates healthcare patient monitoring and diagnosis methods in hospitals. "
            "The study evaluates patient care protocols and medical treatment efficacy for disease management."
        )

        call_count = 0

        def mock_search(query, limit=10, offset=0):
            nonlocal call_count
            call_count += 1
            sample_body = (
                "Clinical patient monitoring in hospital care evaluates treatment and disease management. "
                "Medical data analysis supports clinical diagnosis and patient healthcare outcomes across hospital facilities."
            )
            works = [
                CoreWork(
                    title=f"Patient Health {offset + i}",
                    text=sample_body,
                    doi=f"10.2000/paper.{offset + i}",
                )
                for i in range(10)
            ]
            return works, 50000

        with patch("app.main.CORE_MAX_PAPERS", 10):
            with patch("app.main.search_works", side_effect=mock_search):
                corpus = build_online_corpus(sample_text)

        # Since page 1 returns 10 relevant works and target limit is 10, it should stop on page 1!
        self.assertEqual(call_count, 1)
        self.assertEqual(len(corpus), 10)


if __name__ == "__main__":
    unittest.main()

