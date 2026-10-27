"""Controlled service contract declarations for the Global Brain.

These are metadata-only contracts. They do not authorize or implement calls,
module activation, data access, payments, or network transport.
"""
from dataclasses import dataclass
from typing import Literal

from app.module_registry import get_module
from app.shared_services import get_shared_service

ContractVersion = Literal["v1"]


@dataclass(frozen=True)
class ServiceContract:
    service_key: str
    version: ContractVersion
    operation: str


CONTRACTS: tuple[ServiceContract, ...] = (
    ServiceContract("identity", "v1", "resolve_identity"),
    ServiceContract("organizations", "v1", "resolve_organization"),
    ServiceContract("geography", "v1", "resolve_destination_selection"),
    ServiceContract("catalog", "v1", "lookup_product"),
    ServiceContract("booking", "v1", "lookup_booking"),
    ServiceContract("payments", "v1", "lookup_payment_status"),
    ServiceContract("notifications", "v1", "lookup_notification_status"),
    ServiceContract("maps", "v1", "lookup_location"),
    ServiceContract("audit", "v1", "lookup_audit_record"),
)


def validate_contracts() -> None:
    """Reject undeclared service dependencies and duplicate contract identities."""
    identities: set[tuple[str, str, str]] = set()
    for contract in CONTRACTS:
        get_shared_service(contract.service_key)
        if not contract.operation or not contract.operation.isidentifier():
            raise ValueError("Invalid service operation")
        identity = (contract.service_key, contract.version, contract.operation)
        if identity in identities:
            raise ValueError(f"Duplicate service contract: {identity}")
        identities.add(identity)


def resolve_module_contract(module_number: int, service_key: str, operation: str) -> ServiceContract:
    """Validate a proposed module-to-Brain dependency without granting access."""
    get_module(module_number)
    get_shared_service(service_key)
    for contract in CONTRACTS:
        if contract.service_key == service_key and contract.operation == operation:
            return contract
    raise KeyError(f"Undeclared service operation: {service_key}.{operation}")
