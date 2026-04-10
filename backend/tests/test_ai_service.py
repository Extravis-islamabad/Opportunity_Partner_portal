"""
Unit tests for ai_service pure helpers. Network calls are NOT made — we
verify PII scrubbing and graceful degradation.
"""
import pytest

from app.services.ai_service import _scrub_pii, AIUnavailableError


class TestScrubPII:
    def test_scrubs_email(self):
        assert _scrub_pii("Contact jane.doe@example.com for details") == (
            "Contact [EMAIL] for details"
        )

    def test_scrubs_phone(self):
        assert "[PHONE]" in _scrub_pii("Call +1 (555) 123-4567 today")

    def test_scrubs_multiple(self):
        text = "Email a@b.com or b@c.com and call 555-987-6543"
        scrubbed = _scrub_pii(text)
        assert "@" not in scrubbed
        assert "555-987-6543" not in scrubbed

    def test_handles_empty(self):
        assert _scrub_pii("") == ""
        assert _scrub_pii(None) == ""

    def test_preserves_non_pii(self):
        text = "The deal is worth 10000 USD and closes in Q3"
        assert _scrub_pii(text) == text


class TestAIUnavailableError:
    def test_is_exception(self):
        assert issubclass(AIUnavailableError, Exception)

    def test_carries_message(self):
        err = AIUnavailableError("API key missing")
        assert str(err) == "API key missing"
