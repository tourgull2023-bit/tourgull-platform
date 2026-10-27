"""Global Brain service boundaries (foundation contracts only).

These names describe architecture, not completed service implementations.
No module activation, persistence, or public API exposure occurs here.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SharedService:
    key: str
    description: str


SHARED_SERVICES: tuple[SharedService, ...] = (
    SharedService("identity", "Guest, staff, and supplier identity boundary"),
    SharedService("organizations", "Global-to-local office and supplier organization boundary"),
    SharedService("geography", "Physical, home, and manually selected destination boundaries"),
    SharedService("catalog", "Cross-module product discovery and publishing boundary"),
    SharedService("booking", "Cross-module booking lifecycle boundary"),
    SharedService("payments", "Global, country, and provider payment boundary"),
    SharedService("notifications", "Messaging and notification boundary"),
    SharedService("maps", "Universal mapping and routing boundary"),
    SharedService("audit", "Auditable decisions and operations boundary"),
)


def get_shared_service(key: str) -> SharedService:
    """Resolve a declared service; reject unknown boundaries."""
    for service in SHARED_SERVICES:
        if service.key == key:
            return service
    raise KeyError(f"Unknown shared service: {key}")
