"""`TraitFactory` — instancie la bonne sous-classe `BaseTrait` depuis un nom de trait gameconfig (registre
nom→classe). Trait non porté → `BaseTrait` (no-op) = dégradation fidèle (présent mais sans effet sur le
calcul tant qu'il n'est pas porté). Registre extensible au fil du portage du roster.
"""
from __future__ import annotations

from .base import BaseTrait
from .combat import GetStuckInTrait, ImperviousTrait, ResilientTrait

# Registre nom de trait gameconfig (`gameconfig.unit(id).traits`) → classe. À ÉTENDRE (HeavyWeapon,
# TerminatorArmour, Parry, BigTarget, hit-twice, lasCannon-pierce, ignore-armure…) en RE'ant chaque
# point du contrat §17.17.
TRAIT_CLASSES: dict[str, type[BaseTrait]] = {
    "GetStuckIn": GetStuckInTrait,
    "Resilient": ResilientTrait,
    "Impervious": ImperviousTrait,
}


class TraitFactory:
    registry: dict[str, type[BaseTrait]] = TRAIT_CLASSES

    @classmethod
    def create(cls, name: str) -> BaseTrait:
        klass = cls.registry.get(name, BaseTrait)
        return klass(name=name)

    @classmethod
    def create_many(cls, names) -> list[BaseTrait]:
        return [cls.create(n) for n in (names or []) if n]

    @classmethod
    def register(cls, name: str, klass: type[BaseTrait]) -> None:
        cls.registry[name] = klass
