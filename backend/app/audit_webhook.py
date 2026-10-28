"""Opt-in HTTPS webhook adapter for security alerts.

No URL or credential is bundled. The operator must explicitly configure
an approved endpoint and secret through trusted deployment configuration.
"""
import json
import os
from urllib.parse import urlsplit
import httpx
from app.audit_delivery import AlertEnvelope

class WebhookConfigurationError(RuntimeError):
    pass

class WebhookDeliveryError(RuntimeError):
    pass

class SecureWebhookAlertAdapter:
    def __init__(self, *, endpoint: str, token: str, client: httpx.Client | None = None):
        parts = urlsplit(endpoint) if isinstance(endpoint, str) else None
        if (parts is None or parts.scheme != "https" or not parts.hostname
                or parts.username or parts.password or parts.fragment
                or parts.port not in (None, 443)):
            raise WebhookConfigurationError("approved HTTPS endpoint required")
        if not isinstance(token, str) or len(token) < 32 or "\n" in token or "\r" in token:
            raise WebhookConfigurationError("alert credential not configured")
        self._endpoint = endpoint
        self._token = token
        self._client = client

    @classmethod
    def from_environment(cls, *, client: httpx.Client | None = None):
        endpoint = os.getenv("TOURGULL_AUDIT_ALERT_WEBHOOK_URL", "")
        token = os.getenv("TOURGULL_AUDIT_ALERT_WEBHOOK_TOKEN", "")
        return cls(endpoint=endpoint, token=token, client=client)

    def send(self, envelope: AlertEnvelope) -> None:
        if not isinstance(envelope, AlertEnvelope):
            raise WebhookDeliveryError("invalid alert")
        # Only predefined fields; no raw audit events or identity information.
        payload = {
            "code": envelope.code,
            "severity": envelope.severity,
            "examined": envelope.examined,
            "invalid": envelope.invalid,
            "window_start": envelope.window_start,
            "dedup_key": envelope.dedup_key,
        }
        try:
            if self._client is None:
                with httpx.Client(timeout=3.0, follow_redirects=False, trust_env=False) as client:
                    response = client.post(self._endpoint, json=payload, headers={
                        "Authorization": "Bearer " + self._token,
                        "Idempotency-Key": envelope.dedup_key,
                    })
            else:
                response = self._client.post(self._endpoint, json=payload, headers={
                    "Authorization": "Bearer " + self._token,
                    "Idempotency-Key": envelope.dedup_key,
                })
            if response.status_code < 200 or response.status_code >= 300:
                raise WebhookDeliveryError("alert delivery rejected")
        except (httpx.HTTPError, ValueError) as exc:
            raise WebhookDeliveryError("alert delivery unavailable") from None
