"""Fail-closed trusted membership database tests."""
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.trusted_membership_model import TrustedMembership
from app.trusted_membership import evaluate_trusted_membership
from app.access_policy import AccessRequest

def req(org="org-a", country="BD"):
    return AccessRequest(1, "catalog", "lookup_product", org, country)

def test_active_membership_and_scope_enforced():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(TrustedMembership(id=str(uuid4()), subject_id="subject-a", organization_id="org-a", country_code="BD", role="supplier_admin", status="active"))
        session.add(TrustedMembership(id=str(uuid4()), subject_id="subject-b", organization_id="org-b", country_code="US", role="supplier_admin", status="suspended"))
        session.commit()
        assert evaluate_trusted_membership(session, "subject-a", req()).allowed
        assert not evaluate_trusted_membership(session, "subject-a", req("org-b")).allowed
        assert not evaluate_trusted_membership(session, "subject-a", req("org-a", "US")).allowed
        assert not evaluate_trusted_membership(session, "subject-b", req("org-b", "US")).allowed
        assert not evaluate_trusted_membership(session, "", req()).allowed
        assert not evaluate_trusted_membership(session, "missing", req()).allowed
    engine.dispose()

def test_database_failure_denies():
    class BrokenSession:
        def execute(self, statement):
            raise RuntimeError("database offline")
    decision = evaluate_trusted_membership(BrokenSession(), "subject-a", req())
    assert not decision.allowed
    assert decision.reason == "membership_unavailable"

def test_invalid_context_denies_without_query():
    class ForbiddenSession:
        def execute(self, statement):
            raise AssertionError("must not query")
    assert not evaluate_trusted_membership(ForbiddenSession(), "subject-a", req(country="bd")).allowed
