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
        """Effets ACTIFS de l'unité = non consommés, non expirés, flag `EffectComponent.IsActive @+0x5c`
        (`e.active`) posé, ET `is_active(state)` (la `CreateActiveCondition`) vraie. Renvoie des
        instances `BaseEffect` (consommées par `build_attacker_modifiers_from_effects` / `hits_bonus_from_effects`).

        Les DEUX conjoints sont natifs et distincts : le FLAG est ce qu'ecrivent les feuilles DSL
        `ActivateEffect`/`DeactivateEffect` (et ce que lit `EntityExtensions$$IsOwnerOfEffect` en mode
        `activeOnly`) ; la CONDITION est reevaluee a la lecture (mirror de `CreateActiveCondition`, cf.
        `runner/operations/refresh_effects.py`). Un effet desactive par une feuille ne contribue plus —
        exactement comme il disparait de `decisionView.units[].effects` cote live."""
        return [e for e in self.by_unit.get(int(unit_id), [])
                if not e.consumed and not e.expired and e.active and e.is_active(unit_state)]

    def has_effect(self, unit_id: int, effect_type: int | None = None,
                   name: str | None = None) -> bool:
        """L'unité porte-t-elle DÉJÀ un effet (non consommé) de ce type/nom ? Gate « déjà-présent »
        de la matérialisation (cf. `AddEffectOperation` : query 0x28 sur la def vs cible, + base de
        `UpdateExistingEffect`). Match par `effect_type` si fourni, sinon par `name`."""
        for e in self.by_unit.get(int(unit_id), []):
            if e.consumed:
                continue
            if effect_type is not None and e.effect_type == effect_type:
                return True
            if name is not None and e.name == name:
                return True
        return False

    def add_effect(self, unit_id: int, effect: BaseEffect) -> BaseEffect:
        """Enregistre un effet matérialisé sur l'unité (`AddNewEffect` : ajout à la liste portée de la
        cible). `effect.target` doit être l'unité porteuse. Mirror de l'ajout à
        `EffectsOwnedComponent` côté entité-effet (la liste structurée ici)."""
        self.by_unit.setdefault(int(unit_id), []).append(effect)
        return effect

    def on_attack(self, unit_id: int) -> None:
        """L'unité attaque → consomme les effets one-shot stricts."""
        for e in self.by_unit.get(int(unit_id), []):
            if e.one_shot:
                e.consumed = True

    def on_turn_end(self, unit_id: int, attacked: bool) -> None:
        """Fin de tour de l'unité : retrait des effets « removed-after-attack » si elle a attaqué, puis
        décrément des timers (expiration quand `remaining_turns` atteint 0), puis CASCADE composite :
        un effet PARENT disparu (expiré/consommé) retire ses ENFANTS (lien `parent_type`).

        Mirror du cycle de vie natif d'un effet composite (ex. Stunned 1162) : à l'expiration du parent,
        `<Effect>.RevertInternal` (IdunBattle.Entities.Effects.Loki.StunnedEffect$$RevertInternal) fait `RemoveEffect` de ses enfants permanents (1166/1167)
        et l'enfant same-turns (1165) expire sur son propre timer synchronisé — NET : toute la famille
        part ensemble. La cascade `parent_type` reproduit ce NET (et couvre le retrait anticipé du parent)."""
        lst = self.by_unit.get(int(unit_id), [])
        for e in lst:
            if e.removed_after_attack and attacked:
                e.consumed = True
            if e.remaining_turns is not None:
                e.remaining_turns -= 1
        # cascade : tant qu'un parent vient de disparaître, consommer ses enfants (point fixe — gère un
        # éventuel chaînage parent->enfant->petit-enfant ; aujourd'hui 1 niveau pour Stunned).
        while True:
            gone = {e.effect_type for e in lst
                    if (e.consumed or e.expired) and e.effect_type is not None}
            changed = False
            for e in lst:
                if not e.consumed and e.parent_type in gone:
                    e.consumed = True
                    changed = True
            if not changed:
                break
