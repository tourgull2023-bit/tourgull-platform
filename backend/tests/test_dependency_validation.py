"""Tests for dependency direction and isolation."""
import pytest

from app.dependency_validation import (
    Dependency,
    FOUNDATION_DEPENDENCIES,
    validate_dependencies,
)
from app.module_registry import MODULES
from app.shared_services import SHARED_SERVICES


def test_foundation_dependencies_are_valid():
    validate_dependencies(FOUNDATION_DEPENDENCIES)
    assert len(FOUNDATION_DEPENDENCIES) == len(MODULES) * len(SHARED_SERVICES)


@pytest.mark.parametrize("dependencies", [
    [Dependency("brain", "module:staying")],
    [Dependency("service:identity", "module:staying")],
    [Dependency("module:staying", "module:event")],
    [Dependency("module:unknown", "service:identity")],
    [Dependency("module:staying", "module:staying")],
    [Dependency("service:identity", "service:booking"),
     Dependency("service:booking", "service:identity")],
])
def test_forbidden_dependencies_are_rejected(dependencies):
    with pytest.raises(ValueError):
        validate_dependencies(dependencies)


def test_shared_service_to_brain_direction_allowed():
    validate_dependencies([Dependency("service:identity", "brain")])


def test_empty_dependency_graph_is_valid():
    validate_dependencies([])
