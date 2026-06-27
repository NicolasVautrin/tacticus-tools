"""Matérialisation OFFLINE des effets actifs — **seed one-shot + évolution** (directive user 2026-06-27).

Pour rester 100% offline, l'engine ne lit PAS `decisionView.effects` à chaque décision : il capte
l'ensemble des effets actifs **une seule fois** (snapshot one-shot au chargement) puis l'**ÉVOLUE
offline** via le cycle de vie de chaque effet. Le cycle de vie est porté en **méthodes sur les classes
d'effet** (`engine.entities.effects` : BaseEffect + sous-classes + factory), pas en table de données :
chaque effet capté devient une instance `BaseEffect` (via `EffectFactory`), et l'évolution interroge
ses méthodes (`is_active`/`removed_after_attack`/`one_shot`/`expired`). cf. playbook-engine.md §17.13.

⚠ La capture one-shot des effets (côté hook) reste à brancher dans `combatSnapshot` (extension à venir) ;
en attendant, le harnais peut seeder depuis un `decisionView` (oracle). L'API ici est indépendante de
la source de seed.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .effects import BaseEffect, EffectFactory


@dataclass
class EffectsState:
    """État matérialisé des effets actifs (par unité) = instances `BaseEffect`, seedées une fois puis
    évoluées offline. Source de seed = capture one-shot `{unit_id: [{name, effectType, level, remaining,
    source}]}`. `active_effects(uid, state)` = ce que l'engine consomme à chaque décision (au lieu d'une
    relecture live)."""
    by_unit: dict[int, list[BaseEffect]] = field(default_factory=dict)

    @classmethod
    def seed(cls, effects_by_unit: Mapping | None, mult_by_unit: Mapping | None = None,
             ability_level_by_unit: Mapping | None = None) -> "EffectsState":
        """`mult_by_unit` = {unit_id: AbilityVariablesMultiplierPercentage} (BC, défaut 100) ;
        `ability_level_by_unit` = {unit_id: niveau d'ability source} (indexe les `variables[level]`,
        ≠ stack level capté) — tous deux propagés aux effets matérialisés (§17.21)."""
        bu: dict[int, list[BaseEffect]] = {}
        for uid, effs in (effects_by_unit or {}).items():
            mult = int((mult_by_unit or {}).get(int(uid), 100) or 100)
            albl = (ability_level_by_unit or {}).get(int(uid))
            bu[int(uid)] = EffectFactory.create_many(
                effs, ability_variables_multiplier=mult, ability_level=albl)
        return cls(by_unit=bu)

    def active_effects(self, unit_id: int, unit_state: Mapping | None = None) -> list[BaseEffect]:
        """Effets ACTIFS de l'unité = non consommés, non expirés, `is_active(state)` vrai. Renvoie des
        instances `BaseEffect` (consommées par `build_attacker_modifiers_from_effects` / `hits_bonus_from_effects`)."""
        return [e for e in self.by_unit.get(int(unit_id), [])
                if not e.consumed and not e.expired and e.is_active(unit_state)]

    def on_attack(self, unit_id: int) -> None:
        """L'unité attaque → consomme les effets one-shot stricts."""
        for e in self.by_unit.get(int(unit_id), []):
            if e.one_shot:
                e.consumed = True

    def on_turn_end(self, unit_id: int, attacked: bool) -> None:
        """Fin de tour de l'unité : retrait des effets « removed-after-attack » si elle a attaqué, puis
        décrément des timers (expiration quand `remaining_turns` atteint 0)."""
        for e in self.by_unit.get(int(unit_id), []):
            if e.removed_after_attack and attacked:
                e.consumed = True
            if e.remaining_turns is not None:
                e.remaining_turns -= 1
