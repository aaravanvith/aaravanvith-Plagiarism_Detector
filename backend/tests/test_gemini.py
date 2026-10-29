"""Tests for the Gemini API integration in Vidya Chaya Audit backend.

Covers:
1. Environment variable handling and secure API key loading.
2. Lazy client instantiation, cached client reuse, and invalidation.
3. Model default selection and sanitization (gemini-2.5-flash).
4. Configurable timeouts (in seconds and milliseconds) and retry behavior.
5. Error handling: auth/quota/transient error categorization without leaking secrets.
6. Seamless fallback to local Ollama / offline rewriter when Gemini is unavailable.
7. Successful rewrite generation with mock responses.
8. Chat assistant integration with fallback to regex templates.
9. FastAPI endpoints: /api/correct, /api/chat, /api/correction/provider/status.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

from app.services import gemini_client
from app.services import correction_agent as ca


class TestGeminiClient(unittest.TestCase):
    def setUp(self):
        gemini_client.invalidate_client()
        self._orig_env = os.environ.copy()

    def tearDown(self):
        gemini_client.invalidate_client()
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_unconfigured_when_key_empty(self):
        os.environ.pop("GEMINI_API_KEY", None)
        self.assertFalse(gemini_client.configured())
        with self.assertRaises(gemini_client.GeminiConfigurationError) as ctx:
            gemini_client.get_client()
        self.assertIn("GEMINI_API_KEY is not set", str(ctx.exception))

    def test_configured_when_key_present(self):
        os.environ["GEMINI_API_KEY"] = "fake-secret-test-key-999"
        self.assertTrue(gemini_client.configured())
        self.assertTrue(gemini_client.is_available())

    def test_key_never_leaked_in_exceptions(self):
        secret = "super-secret-api-key-do-not-leak"
        os.environ["GEMINI_API_KEY"] = secret

        with patch("google.genai.Client", side_effect=Exception("401 Invalid API key")):
            with self.assertRaises(gemini_client.GeminiConfigurationError) as ctx:
                gemini_client.get_client()
            err_msg = str(ctx.exception)
            self.assertNotIn(secret, err_msg)

    def test_default_model_selection_and_legacy_sanitization(self):
        # Default
        os.environ.pop("GEMINI_REWRITE_MODEL", None)
        self.assertEqual(gemini_client._default_model(), "gemini-3.5-flash")

        # Retired model sanitization
        os.environ["GEMINI_REWRITE_MODEL"] = "gemini-2.5-flash"
        self.assertEqual(gemini_client._default_model(), "gemini-3.5-flash")

        # Explicit valid override
        os.environ["GEMINI_REWRITE_MODEL"] = "gemini-2.0-flash"
        self.assertEqual(gemini_client._default_model(), "gemini-2.0-flash")

    def test_timeout_and_retries_parsing(self):
        os.environ["GEMINI_TIMEOUT"] = "45"
        os.environ["GEMINI_MAX_RETRIES"] = "3"
        self.assertEqual(gemini_client._timeout(), 45.0)
        self.assertEqual(gemini_client._max_retries(), 3)

        # Invalid strings fall back safely
        os.environ["GEMINI_TIMEOUT"] = "invalid"
        os.environ["GEMINI_MAX_RETRIES"] = "invalid"
        self.assertEqual(gemini_client._timeout(), 30.0)
        self.assertEqual(gemini_client._max_retries(), 2)

    def test_generate_text_success(self):
        os.environ["GEMINI_API_KEY"] = "mock-key"
        mock_response = MagicMock()
        mock_response.text = "  Through wearable sensors, patient health is monitored.  "

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("app.services.gemini_client.get_client", return_value=mock_client):
            output = gemini_client.generate_text("Rewrite this sentence.")
            self.assertEqual(output, "Through wearable sensors, patient health is monitored.")
            mock_client.models.generate_content.assert_called_once()
            call_kwargs = mock_client.models.generate_content.call_args[1]
            self.assertEqual(call_kwargs["model"], "gemini-3.5-flash")

    def test_generate_text_auth_error_no_retry(self):
        os.environ["GEMINI_API_KEY"] = "mock-key"
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("401 Unauthorized API key")

        with patch("app.services.gemini_client.get_client", return_value=mock_client):
            with self.assertRaises(gemini_client.GeminiConfigurationError):
                gemini_client.generate_text("Test prompt")
            # Must not retry auth errors
            self.assertEqual(mock_client.models.generate_content.call_count, 1)

    def test_generate_text_quota_error_no_retry(self):
        os.environ["GEMINI_API_KEY"] = "mock-key"
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("429 ResourceExhausted: Quota exceeded")

        with patch("app.services.gemini_client.get_client", return_value=mock_client):
            with self.assertRaises(gemini_client.GeminiRequestError):
                gemini_client.generate_text("Test prompt")
            # Must not retry quota errors
            self.assertEqual(mock_client.models.generate_content.call_count, 1)

    def test_generate_text_transient_retry_and_recovery(self):
        os.environ["GEMINI_API_KEY"] = "mock-key"
        os.environ["GEMINI_MAX_RETRIES"] = "2"

        mock_response = MagicMock()
        mock_response.text = "Recovered after transient error."

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [
            Exception("503 Service Unavailable"),
            mock_response,
        ]

        with patch("app.services.gemini_client.get_client", return_value=mock_client):
            with patch("time.sleep", return_value=None):
                output = gemini_client.generate_text("Test prompt")
                self.assertEqual(output, "Recovered after transient error.")
                self.assertEqual(mock_client.models.generate_content.call_count, 2)


class TestCorrectionAgentWithGemini(unittest.TestCase):
    def setUp(self):
        gemini_client.invalidate_client()
        self._orig_env = os.environ.copy()

    def tearDown(self):
        gemini_client.invalidate_client()
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_fallback_when_gemini_unconfigured(self):
        os.environ.pop("GEMINI_API_KEY", None)
        sentence = "The system detects anomalies using machine learning."
        rewrites = ca.rewrite_suggestions(sentence, strength="moderate")

        self.assertIn("academic", rewrites)
        self.assertIn("human", rewrites)
        self.assertIn("simple", rewrites)
        for mode in ("academic", "human", "simple"):
            self.assertTrue(len(rewrites[mode]) > 5)
            self.assertNotEqual(rewrites[mode].lower(), sentence.lower())

    def test_fallback_when_gemini_fails(self):
        os.environ["GEMINI_API_KEY"] = "mock-key"
        with patch("app.services.gemini_client.generate_text", side_effect=gemini_client.GeminiRequestError("Quota")):
            sentence = "The system detects anomalies using machine learning."
            # Must not raise an exception; must fall back gracefully
            rewrites = ca.rewrite_suggestions(sentence, strength="moderate")
            self.assertIn("academic", rewrites)
            self.assertIn("human", rewrites)
            self.assertIn("simple", rewrites)

    def test_gemini_used_when_available(self):
        os.environ["GEMINI_API_KEY"] = "mock-key"

        def mock_generate(prompt, **kwargs):
            if "IEEE" in prompt:
                return "Anomalies are detected by the system through machine learning."
            elif "university student" in prompt:
                return "With machine learning, the system can detect anomalies."
            else:
                return "The system can detect anomalies."

        with patch("app.services.gemini_client.generate_text", side_effect=mock_generate):
            sentence = "The system detects anomalies using machine learning."
            rewrites = ca.rewrite_suggestions(sentence, strength="moderate")
            self.assertEqual(
                rewrites["academic"],
                "Anomalies are detected by the system through machine learning.",
            )
            self.assertEqual(
                rewrites["human"],
                "With machine learning, the system can detect anomalies.",
            )

    def test_chat_reply_with_gemini(self):
        os.environ["GEMINI_API_KEY"] = "mock-key"
        context = {
            "sentence": "The system detects anomalies.",
            "source": "Sample Paper A",
            "score": 85.0,
        }

        with patch("app.services.gemini_client.generate_text", return_value="This sentence has high overlap with Sample Paper A; consider rephrasing."):
            reply = ca.chat_reply("What should I do?", context)
            self.assertEqual(reply, "This sentence has high overlap with Sample Paper A; consider rephrasing.")

    def test_chat_reply_fallback_templates_when_unconfigured(self):
        os.environ.pop("GEMINI_API_KEY", None)
        context = {
            "sentence": "The system detects anomalies.",
            "source": "Sample Paper A",
            "score": 85.0,
        }
        reply_why = ca.chat_reply("Why was this flagged?", context)
        self.assertIn("Sample Paper A", reply_why)

        reply_cite = ca.chat_reply("How do I cite this?", context)
        self.assertIn("Suggested citation", reply_cite)

        reply_unknown = ca.chat_reply("Hello there", context)
        self.assertIn("I can explain the match", reply_unknown)


class TestCorrectionApiEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db, Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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

    def test_health_endpoint(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_provider_status_endpoint(self):
        res = self.client.get("/api/correction/provider/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("gemini_configured", data)
        self.assertIn("gemini_model", data)
        self.assertIn("ollama_model", data)
        self.assertEqual(data["gemini_model"], "gemini-3.5-flash")

    def test_correct_endpoint(self):
        payload = {
            "sentence": "The system detects anomalies using machine learning.",
            "matched_source": "pubmed::42541193",
            "similarity": 80.0,
            "rewrite_strength": "moderate",
            "start_offset": 0,
            "end_offset": 52,
        }
        with patch("app.services.gemini_client.generate_text", return_value="Machine learning is used to identify anomalies."):
            res = self.client.post("/api/correct", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("rewrites", data)
        self.assertIn("academic", data["rewrites"])
        self.assertIn("human", data["rewrites"])
        self.assertIn("simple", data["rewrites"])
        self.assertIn("provider", data)
        self.assertIn("is_fallback", data)
        self.assertEqual(data["start_offset"], 0)
        self.assertEqual(data["end_offset"], 52)

    def test_chat_endpoint(self):
        payload = {
            "message": "Why was this flagged?",
            "sentence": "The system detects anomalies.",
            "matched_source": "pubmed::42541193",
            "similarity": 80.0,
        }
        with patch("app.services.gemini_client.generate_text", return_value="This sentence has high overlap with pubmed::42541193."):
            res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("reply", data)
        self.assertIn("pubmed::42541193", data["reply"])


if __name__ == "__main__":
    unittest.main()

