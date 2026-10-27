"""Approved Tourgull module identities; not an implementation or activation list.

The shared Global Brain remains separate from commercial modules.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDefinition:
    number: int
    slug: str
    name: str


MODULES: tuple[ModuleDefinition, ...] = (
    ModuleDefinition(1, "staying", "Staying"),
    ModuleDefinition(2, "air-ticket", "Air ticket"),
    ModuleDefinition(3, "transportation", "Transportation"),
    ModuleDefinition(4, "ticketing-passes", "Ticketing & Passes"),
    ModuleDefinition(5, "things-to-do", "Things to do"),
    ModuleDefinition(6, "event", "Event"),
    ModuleDefinition(7, "food", "Food"),
    ModuleDefinition(8, "tour-package", "Tour package"),
    ModuleDefinition(9, "visa-service", "Visa service"),
    ModuleDefinition(10, "travel-gear", "Travel gear"),
    ModuleDefinition(11, "travel-guide", "Travel guide"),
    ModuleDefinition(12, "travel-planner", "Travel planner"),
    ModuleDefinition(13, "travel-document", "Travel document"),
    ModuleDefinition(14, "travel-guideline", "Travel guideline"),
)


def get_module(number: int) -> ModuleDefinition:
    """Look up a controlled module identity without enabling it."""
    for module in MODULES:
        if module.number == number:
            return module
    raise KeyError(f"Unknown Tourgull module: {number}")
