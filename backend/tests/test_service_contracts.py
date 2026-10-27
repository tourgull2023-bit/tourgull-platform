"""Global Brain dependency boundary contract checks."""
import pytest

from app.service_contracts import (
    CONTRACTS,
    ServiceContract,
    resolve_module_contract,
    validate_contracts,
)
from app.shared_services import SHARED_SERVICES


def test_all_declared_contracts_are_valid():
    validate_contracts()
    assert {c.service_key for c in CONTRACTS} == {s.key for s in SHARED_SERVICES}


def test_commercial_module_can_resolve_declared_contract_metadata():
    contract = resolve_module_contract(1, "identity", "resolve_identity")
    assert contract == ServiceContract("identity", "v1", "resolve_identity")


def test_undeclared_operation_is_rejected():
    with pytest.raises(KeyError):
        resolve_module_contract(1, "payments", "charge_card")


def test_unknown_module_is_rejected():
    with pytest.raises(KeyError):
        resolve_module_contract(15, "identity", "resolve_identity")


def test_unknown_service_is_rejected():
    with pytest.raises(KeyError):
        resolve_module_contract(1, "staying", "lookup_product")
