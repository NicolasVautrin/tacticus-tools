"""Matérialisation OFFLINE des TRAITS par unité — symétrique de `EffectsState`, mais SANS évolution :
les traits sont **innés/statiques** (`gameconfig.unit(id).traits`, présents tout le combat). On matérialise
chaque unité en instances `BaseTrait` (via `TraitFactory`) que le raw prediction interroge (contrat §17.17).

Source de seed = `{unit_id: [trait_names]}` (offline, depuis gameconfig). 100% offline, pas de capture live.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .traits.base import BaseTrait
from .traits.factory import TraitFactory


@dataclass
class TraitsState:
    """Traits matérialisés par unité (instances `BaseTrait`). Statique (pas d'`on_attack`/`on_turn_end`)."""
    by_unit: dict[int, list[BaseTrait]] = field(default_factory=dict)

    @classmethod
    def seed(cls, traits_by_unit: Mapping | None) -> "TraitsState":
        return cls(by_unit={int(uid): TraitFactory.create_many(names)
                            for uid, names in (traits_by_unit or {}).items()})

    def traits(self, unit_id: int) -> list[BaseTrait]:
        return self.by_unit.get(int(unit_id), [])
