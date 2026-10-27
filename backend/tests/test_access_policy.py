"""Policy-only tests; no authentication or production permission claims."""
import pytest

from app.access_policy import (
    AccessRequest, Principal, Role, evaluate_access,
)


def principal(role=Role.GUEST, organization_id="org-1", country_code="BD"):
    return Principal("subject-1", role, organization_id, country_code)


def request(service="catalog", operation="lookup_product", module=1,
            organization_id="org-1", country_code="BD"):
    return AccessRequest(module, service, operation, organization_id, country_code)


def test_declared_in_scope_operation_allowed():
    assert evaluate_access(principal(), request()).allowed


@pytest.mark.parametrize("changes,reason", [
    ({"organization_id": "org-2"}, "organization_mismatch"),
    ({"country_code": "US"}, "country_mismatch"),
    ({"module": 99}, "undeclared_contract"),
    ({"service": "payments", "operation": "charge_card"}, "undeclared_contract"),
    ({"service": "payments", "operation": "lookup_payment_status"}, "operation_not_permitted"),
    ({"module": True}, "unknown_module"),
    ({"country_code": "bd"}, "invalid_context"),
    ({"organization_id": ""}, "invalid_context"),
])
def test_fail_closed_requests(changes, reason):
    values = {"service": "catalog", "operation": "lookup_product",
              "module": 1, "organization_id": "org-1", "country_code": "BD"}
    values.update(changes)
    result = evaluate_access(principal(), request(**values))
    assert not result.allowed
    assert result.reason == reason


def test_unknown_role_denied():
    result = evaluate_access(principal(role="global_admin"), request())
    assert not result.allowed
    assert result.reason == "unknown_role"


def test_role_permissions_do_not_imply_cross_tenant_access():
    result = evaluate_access(
        principal(Role.GLOBAL_ADMIN),
        request("audit", "lookup_audit_record", organization_id="org-2"),
    )
    assert not result.allowed


def test_missing_identity_denied():
    result = evaluate_access(
        Principal("", Role.GUEST, "org-1", "BD"), request()
    )
    assert not result.allowed
