"""Static dependency validation for the modular-monolith foundation.

Metadata only: this is not an authorization or runtime enforcement layer.
"""
from dataclasses import dataclass
from typing import Iterable

from app.module_registry import MODULES
from app.shared_services import SHARED_SERVICES


@dataclass(frozen=True)
class Dependency:
    source: str
    target: str


BRAIN = "brain"
SERVICE_KEYS = frozenset(service.key for service in SHARED_SERVICES)
MODULE_KEYS = frozenset(f"module:{module.slug}" for module in MODULES)
NODES = frozenset({BRAIN}) | frozenset(f"service:{key}" for key in SERVICE_KEYS) | MODULE_KEYS


def validate_dependencies(dependencies: Iterable[Dependency]) -> None:
    """Reject unknown nodes, reverse ownership, direct module coupling and cycles."""
    edges: dict[str, set[str]] = {node: set() for node in NODES}
    for dependency in dependencies:
        source, target = dependency.source, dependency.target
        if source not in NODES or target not in NODES:
            raise ValueError(f"Unknown dependency node: {source} -> {target}")
        if source == target:
            raise ValueError(f"Self dependency: {source}")
        if source == BRAIN and target.startswith("module:"):
            raise ValueError("Global Brain cannot depend on commercial modules")
        if source.startswith("service:") and target.startswith("module:"):
            raise ValueError("Shared services cannot depend on commercial modules")
        if source.startswith("module:") and target.startswith("module:"):
            raise ValueError("Direct commercial module coupling is forbidden")
        edges[source].add(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f"Circular dependency involving {node}")
        if node in visited:
            return
        visiting.add(node)
        for target in edges[node]:
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in NODES:
        visit(node)


# Baseline: modules may depend on declared shared-service boundaries.
# No commercial module is activated by declaring these edges.
FOUNDATION_DEPENDENCIES: tuple[Dependency, ...] = tuple(
    Dependency(f"module:{module.slug}", f"service:{service.key}")
    for module in MODULES
    for service in SHARED_SERVICES
)
