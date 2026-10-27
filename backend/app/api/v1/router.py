
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/meta", tags=["system"])
def platform_metadata():
    return {
        "platform": "tourgull",
        "api_version": "v1"
    }

# Explicitly protected authorization probe; never accepts role from the client.
from fastapi import Header, HTTPException
import logging
from app.security_audit import record_access_decision
from app import security_audit_model  # noqa: F401 - register audit schema
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.authentication import AuthenticationError, verify_bearer_token
from app.db import create_db_engine
from app.access_policy import AccessRequest
from app.trusted_membership import evaluate_trusted_membership


class AuthorizationProbe(BaseModel):
    module_number: int
    service_key: str = Field(min_length=1, max_length=100)
    operation: str = Field(min_length=1, max_length=100)
    organization_id: str = Field(min_length=1, max_length=255)
    country_code: str = Field(min_length=2, max_length=2)


@router.post("/access/check", tags=["security"])
def check_access(probe: AuthorizationProbe, authorization: str | None = Header(default=None)):
    """Demonstrate token + stored membership + declared contract enforcement."""
    try:
        identity = verify_bearer_token(authorization)
    except AuthenticationError:
        logging.getLogger("tourgull.security").warning("authentication_denied")
        raise HTTPException(status_code=401, detail="Unauthenticated")
    request = AccessRequest(
        probe.module_number, probe.service_key, probe.operation,
        probe.organization_id, probe.country_code,
    )
    try:
        engine = create_db_engine()
        try:
            with Session(engine) as session:
                decision = evaluate_trusted_membership(session, identity, request)
                record_access_decision(session, identity, decision)
                session.commit()
        finally:
            engine.dispose()
    except Exception:
        raise HTTPException(status_code=503, detail="Authorization unavailable")
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"allowed": True}
