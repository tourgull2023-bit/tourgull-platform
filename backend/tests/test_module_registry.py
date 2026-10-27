"""The controlled module inventory must remain stable across refactors."""
import pytest

from app.module_registry import MODULES, get_module


def test_exactly_fourteen_unique_module_ids_and_slugs():
    assert len(MODULES) == 14
    assert [module.number for module in MODULES] == list(range(1, 15))
    assert len({module.slug for module in MODULES}) == 14


def test_approved_module_numbering():
    assert get_module(1).slug == "staying"
    assert get_module(6).slug == "event"
    assert get_module(8).slug == "tour-package"
    assert get_module(9).slug == "visa-service"
    assert get_module(11).slug == "travel-guide"
    assert get_module(14).slug == "travel-guideline"


def test_unknown_module_is_rejected():
    with pytest.raises(KeyError):
        get_module(15)
