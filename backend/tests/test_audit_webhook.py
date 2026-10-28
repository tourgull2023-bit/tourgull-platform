"""Tests for opt-in HTTPS alert notification adapter."""
import httpx
import pytest
from app.audit_delivery import AlertEnvelope
from app.audit_webhook import (
    SecureWebhookAlertAdapter, WebhookConfigurationError, WebhookDeliveryError,
)

URL = "https://alerts.example.test/security"
TOKEN = "unit-test-token-with-at-least-32-characters"
ENVELOPE = AlertEnvelope(
    code="integrity_mismatch", severity="critical", examined=4, invalid=1,
    window_start="2026-10-27T12:00:00+00:00",
    dedup_key="audit-integrity:integrity_mismatch:123",
)

def test_webhook_sends_minimal_payload_and_idempotency_key():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(202)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        sender = SecureWebhookAlertAdapter(endpoint=URL, token=TOKEN, client=client)
        sender.send(ENVELOPE)
    assert len(seen) == 1
    assert seen[0].headers["idempotency-key"] == ENVELOPE.dedup_key
    assert seen[0].headers["authorization"] == "Bearer " + TOKEN
    assert b"integrity_mismatch" in seen[0].content
    assert b"subject" not in seen[0].content

@pytest.mark.parametrize("endpoint", [
    "http://alerts.example.test/security", "https://user:pass@alerts.example.test/",
    "https://alerts.example.test:8080/", "https://alerts.example.test/#fragment",
    "not-a-url", "",
])
def test_unapproved_endpoint_rejected(endpoint):
    with pytest.raises(WebhookConfigurationError):
        SecureWebhookAlertAdapter(endpoint=endpoint, token=TOKEN)

def test_missing_credentials_rejected(monkeypatch):
    monkeypatch.delenv("TOURGULL_AUDIT_ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TOURGULL_AUDIT_ALERT_WEBHOOK_TOKEN", raising=False)
    with pytest.raises(WebhookConfigurationError):
        SecureWebhookAlertAdapter.from_environment()

def test_rejected_response_does_not_expose_provider_content():
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(503, text="private-provider-details")
    )) as client:
        sender = SecureWebhookAlertAdapter(endpoint=URL, token=TOKEN, client=client)
        with pytest.raises(WebhookDeliveryError) as error:
            sender.send(ENVELOPE)
    assert "private-provider-details" not in str(error.value)
    assert TOKEN not in str(error.value)

def test_network_error_is_sanitized():
    def handler(request):
        raise httpx.ConnectError("private-network-details")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        sender = SecureWebhookAlertAdapter(endpoint=URL, token=TOKEN, client=client)
        with pytest.raises(WebhookDeliveryError) as error:
            sender.send(ENVELOPE)
    assert "private-network-details" not in str(error.value)
