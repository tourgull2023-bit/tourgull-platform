"""Validate architectural boundaries without claiming implementations exist."""
import pytest

from app.module_registry import MODULES
from app.shared_services import SHARED_SERVICES, get_shared_service


def test_shared_service_keys_are_unique():
    keys = [service.key for service in SHARED_SERVICES]
    assert len(keys) == len(set(keys))
    assert all(keys)


def test_global_brain_is_distinct_from_commercial_modules():
    module_slugs = {module.slug for module in MODULES}
    assert not module_slugs.intersection(service.key for service in SHARED_SERVICES)


def test_required_boundaries_are_declared():
    assert {"identity", "geography", "booking", "payments", "audit"}.issubset(
        {service.key for service in SHARED_SERVICES}
    )


def test_unknown_shared_service_rejected():
    with pytest.raises(KeyError):
        get_shared_service("unknown")
