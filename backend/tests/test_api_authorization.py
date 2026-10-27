"""API authentication and trusted database authorization tests."""
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.main import app
from app.api.v1 import router as api
from app.authentication import AuthenticatedIdentity, AuthenticationError
from app.db import Base
from app.trusted_membership_model import TrustedMembership

PAYLOAD = {
    "module_number": 1, "service_key": "catalog", "operation": "lookup_product",
    "organization_id": "org-a", "country_code": "BD",
}

def test_missing_or_invalid_token_denied_before_database(monkeypatch):
    def reject(header):
        raise AuthenticationError("unauthenticated")
    monkeypatch.setattr(api, "verify_bearer_token", reject)
    def no_db():
        raise AssertionError("unauthenticated must not touch database")
    monkeypatch.setattr(api, "create_db_engine", no_db)
    response = TestClient(app).post("/api/v1/access/check", json=PAYLOAD)
    assert response.status_code == 401

def test_verified_identity_authorized_only_for_its_database_scope(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(TrustedMembership(
            id=str(uuid4()), issuer="https://id.example", subject_id="user-1",
            organization_id="org-a", country_code="BD",
            role="supplier_admin", status="active"))
        session.commit()
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr(api, "create_db_engine", lambda: engine)
    monkeypatch.setattr(api, "verify_bearer_token",
                        lambda header: AuthenticatedIdentity("user-1", "https://id.example"))
    client = TestClient(app)
    assert client.post("/api/v1/access/check", json=PAYLOAD).status_code == 200
    assert client.post("/api/v1/access/check", json={**PAYLOAD, "country_code": "US"}).status_code == 403
    assert client.post("/api/v1/access/check", json={**PAYLOAD, "organization_id": "org-b"}).status_code == 403
    monkeypatch.setattr(api, "verify_bearer_token",
                        lambda header: AuthenticatedIdentity("user-1", "https://other.example"))
    assert client.post("/api/v1/access/check", json=PAYLOAD).status_code == 403
    engine.dispose()
