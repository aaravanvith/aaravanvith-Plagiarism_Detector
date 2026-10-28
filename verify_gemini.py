"""Stand-alone verification script for Gemini integration and fallback capabilities."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, "backend")

from app.services import gemini_client
from app.services import correction_agent as ca
from app.main import app
from fastapi.testclient import TestClient

print("=" * 60)
print("VERIFYING GEMINI API INTEGRATION & FALLBACK")
print("=" * 60)

# 1. Verify unconfigured state
gemini_client.invalidate_client()
os.environ.pop("GEMINI_API_KEY", None)
assert not gemini_client.configured(), "Expected configured to be False when GEMINI_API_KEY is unset"
assert gemini_client._default_model() == "gemini-3.8-flash", f"Expected gemini-3.8-flash, got {gemini_client._default_model()}"
print("[PASS] Unconfigured state and default model (gemini-3.8-flash)")

# 2. Verify legacy model sanitization
os.environ["GEMINI_REWRITE_MODEL"] = "gemini-3.5-flash"
assert gemini_client._default_model() == "gemini-3.8-flash", "Legacy gemini-3.5-flash was not sanitized"
os.environ.pop("GEMINI_REWRITE_MODEL", None)
print("[PASS] Legacy gemini-3.5-flash sanitization")

# 3. Verify security: key is not leaked in exception string
os.environ["GEMINI_API_KEY"] = "super-secret-key-12345"
try:
    with patch("google.genai.Client", side_effect=Exception("401 Invalid API key")):
        gemini_client.get_client()
except Exception as exc:
    assert "super-secret-key-12345" not in str(exc)
    print("[PASS] Security: GEMINI_API_KEY is not leaked in exception")

# 4. Verify timeout & retry parsing
os.environ["GEMINI_TIMEOUT"] = "25"
os.environ["GEMINI_MAX_RETRIES"] = "3"
assert gemini_client._timeout() == 25.0
assert gemini_client._max_retries() == 3
print("[PASS] Timeout and max retries configuration")

# 5. Verify graceful fallback when Gemini is unavailable
gemini_client.invalidate_client()
os.environ.pop("GEMINI_API_KEY", None)
sample_sentence = "The system detects anomalies using machine learning."
fallback_rewrites = ca.rewrite_suggestions(sample_sentence)
assert "academic" in fallback_rewrites and len(fallback_rewrites["academic"]) > 5
assert "human" in fallback_rewrites and len(fallback_rewrites["human"]) > 5
assert "simple" in fallback_rewrites and len(fallback_rewrites["simple"]) > 5
print("[PASS] Graceful fallback rewrite generation when Gemini is unavailable")

# 6. Verify Gemini generation when available
os.environ["GEMINI_API_KEY"] = "mock-key"
mock_response = MagicMock()
mock_response.text = "Through machine learning, anomalies are detected by the system."
mock_client = MagicMock()
mock_client.models.generate_content.return_value = mock_response

with patch("app.services.gemini_client.get_client", return_value=mock_client):
    gemini_out = gemini_client.generate_text("Rewrite sentence")
    assert gemini_out == "Through machine learning, anomalies are detected by the system."
    print("[PASS] Gemini text generation via google-genai SDK mock")

# 7. Verify API endpoints with TestClient
with TestClient(app) as client:
    res = client.get("/api/correction/provider/status")
    assert res.status_code == 200, res.text
    data = res.json()
    assert "gemini_configured" in data
    assert data["gemini_model"] == "gemini-3.8-flash"
    print("[PASS] /api/correction/provider/status endpoint")

    res = client.post(
        "/api/correct",
        json={
            "sentence": sample_sentence,
            "matched_source": "test-source",
            "similarity": 75.0,
            "rewrite_strength": "moderate",
            "start_offset": 0,
            "end_offset": len(sample_sentence),
        },
    )
    assert res.status_code == 200, res.text
    corr = res.json()
    assert "rewrites" in corr and "academic" in corr["rewrites"]
    print("[PASS] /api/correct endpoint with rewrites dictionary")

    res = client.post(
        "/api/chat",
        json={
            "message": "Why was this flagged?",
            "sentence": sample_sentence,
            "matched_source": "test-source",
            "similarity": 75.0,
        },
    )
    assert res.status_code == 200, res.text
    chat_data = res.json()
    assert "reply" in chat_data and len(chat_data["reply"]) > 0
    print("[PASS] /api/chat endpoint with assistant reply")

print("=" * 60)
print("ALL GEMINI INTEGRATION & FALLBACK VERIFICATIONS PASSED!")
print("=" * 60)

