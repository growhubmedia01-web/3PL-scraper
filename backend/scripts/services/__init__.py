"""Registry of data-defined services (007+).

Each module exposes SLUG, NAME, DESCRIPTION, CONFIG, SIGNALS, KEYWORDS,
ROLES and build_library(). The legacy 3PL service predates this registry and
is still defined by scripts/seed.py + scripts/query_library.py and the
003/004/005 migrations; it is retained (inactive), never deleted.
"""
from __future__ import annotations

from types import ModuleType

from scripts.services import (pet_specialty_food_treats_supplements,
                             powersports_aftermarket_sourcing)

SERVICE_MODULES: dict[str, ModuleType] = {
    powersports_aftermarket_sourcing.SLUG: powersports_aftermarket_sourcing,
    pet_specialty_food_treats_supplements.SLUG: pet_specialty_food_treats_supplements,
}

# Migration file generated for each registered service.
MIGRATION_FILES: dict[str, str] = {
    powersports_aftermarket_sourcing.SLUG: "007_powersports_aftermarket_sourcing.sql",
    pet_specialty_food_treats_supplements.SLUG:
        "010_pet_specialty_food_treats_supplements.sql",
}


def get(slug: str) -> ModuleType | None:
    return SERVICE_MODULES.get(slug)
