"""Fail-closed, pure access-policy foundation for Tourgull.

This is a policy evaluation primitive, NOT authentication, token validation,
tenant provisioning, or a production authorization integration.
Callers must authenticate principals and obtain trusted context separately.
"""
from dataclasses import dataclass
from enum import Enum

from app.module_registry import get_module
from app.service_contracts import resolve_module_contract


class Role(str, Enum):
    GLOBAL_ADMIN = "global_admin"
    COUNTRY_ADMIN = "country_admin"
    SUPPLIER_ADMIN = "supplier_admin"
    GUEST = "guest"


@dataclass(frozen=True)
class Principal:
    subject_id: str
    role: Role
    organization_id: str
    country_code: str


@dataclass(frozen=True)
class AccessRequest:
    module_number: int
    service_key: str
    operation: str
    organization_id: str
    country_code: str


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str


# Deliberately narrow demonstration permissions. These are not a
# final Tourgull permissions matrix or an approval of business rules.
ROLE_OPERATIONS: dict[Role, frozenset[tuple[str, str]]] = {
    Role.GLOBAL_ADMIN: frozenset({
        ("identity", "resolve_identity"),
        ("organizations", "resolve_organization"),
        ("audit", "lookup_audit_record"),
    }),
    Role.COUNTRY_ADMIN: frozenset({
        ("organizations", "resolve_organization"),
        ("geography", "resolve_destination_selection"),
    }),
    Role.SUPPLIER_ADMIN: frozenset({
        ("catalog", "lookup_product"),
    }),
    Role.GUEST: frozenset({
        ("geography", "resolve_destination_selection"),
        ("catalog", "lookup_product"),
    }),
}


def evaluate_access(principal: Principal, request: AccessRequest) -> AccessDecision:
    """Deny unknown, incomplete, out-of-scope or undeclared access."""
    if not isinstance(principal, Principal) or not isinstance(request, AccessRequest):
        return AccessDecision(False, "invalid_context")
    if not all((
        isinstance(principal.subject_id, str) and principal.subject_id.strip(),
        isinstance(principal.organization_id, str) and principal.organization_id.strip(),
        isinstance(principal.country_code, str) and len(principal.country_code) == 2
        and principal.country_code.isalpha() and principal.country_code.isupper(),
        isinstance(request.organization_id, str) and request.organization_id.strip(),
        isinstance(request.country_code, str) and len(request.country_code) == 2
        and request.country_code.isalpha() and request.country_code.isupper(),
    )):
        return AccessDecision(False, "invalid_context")
    if not isinstance(principal.role, Role):
        return AccessDecision(False, "unknown_role")
    if type(request.module_number) is not int:
        return AccessDecision(False, "unknown_module")
    try:
        get_module(request.module_number)
        resolve_module_contract(
            request.module_number, request.service_key, request.operation
        )
    except (KeyError, TypeError, ValueError):
        return AccessDecision(False, "undeclared_contract")
    if (request.service_key, request.operation) not in ROLE_OPERATIONS[principal.role]:
        return AccessDecision(False, "operation_not_permitted")
    if principal.organization_id != request.organization_id:
        return AccessDecision(False, "organization_mismatch")
    if principal.country_code != request.country_code:
        return AccessDecision(False, "country_mismatch")
    return AccessDecision(True, "policy_match")
