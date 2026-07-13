"""Playbooks Comparable COMMUNS — Normal / Default / Heal / Repair (namespace `IdunBattle.AI.Playbook`).

Sous-classes MINCES de `ComparablePlaybook<T>` (base.py) : elles n'overrident QUE le fournisseur de
prédiction (`MakeDamagePredictions`, vtable +0x358) et éventuellement le gate/custom. Le calcul
prédiction->utilité (Σ damage_composite + Tile(7)) est mutualisé dans la base.

- `NormalAttackPlaybook` (ALoki_NormalAttackPlaybook & co, un par unité côté natif) : prédiction =
  `prediction.make_normal_attack_predictions` (sélection d'arme + hits + perçage + armure + modifiers effets).
- `DefaultActiveAbilityPlaybook` : fallback pour toute ability spéciale sans playbook bespoke ->
  `prediction.make_damage_predictions` (cible principale + AoE ; None/[] pour summon/buff/heal = NON-attaque).
- `HealPlaybook` (tag 18) : soin = `HealUtility @1810e16f0` (heal_utility) + CustomUtility (TwistedScience).
  Gate `ShouldExecute @181184b30` : pred > 0.
- `RepairPlaybook` (tag 28) : DORMANT (prédiction repair non-dégât, pas de repair dans les batailles testées).

PRÉDICTEUR = `engine.playbook.prediction` (modèle objet : Scene + ability + services + ProbableDamageEvent).
"""
from __future__ import annotations

from . import prediction
from .base import ComparablePlaybook, register
from ..predict import heal_utility
from ..entities.active_ability_type import ActiveAbilityType


class NormalAttackPlaybook(ComparablePlaybook):
    """Attaque normale (par-unité côté natif ; ici une classe, PV gère la sélection d'arme). Tie-break :
    à utilité TOTALE égale, la normale gagne (`InitAbilityTypeLists` : [normal, spéciales…])."""
    is_normal_attack = True

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        if ctx.scene is None:
            return None
        ev = prediction.make_normal_attack_predictions(ctx.scene, ctx.uid, target, caster_tile)
        return None if ev is None else [ev]


class DefaultActiveAbilityPlaybook(ComparablePlaybook):
    """Fallback générique pour toute ability spéciale d'attaque (non enregistrée sous un id bespoke).
    Prédiction = `PV.make_damage_predictions` : liste cible principale + AoE. None/[] = NON-attaque
    (summon/buff/heal) -> aucune action émise (gate). ability_id -1 (non enregistré ; défaut)."""
    ability_id = -1
    is_normal_attack = False

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        if ctx.scene is None:
            return None
        return prediction.make_damage_predictions(ctx.scene, ctx.uid, target, ability_id,
                                                  ctx.ab_name_by_id.get(ability_id), attack_pos=caster_tile)


class HealPlaybook(ComparablePlaybook):
    """Soin (tag 18). Utilité = CustomUtility (TwistedScience : +100, +100 si cible Genestealers) +
    `HealUtility` (heal_utility = (missing/(maxHP+1))×100×friendSign×bossMod). Gate `ShouldExecute
    @181184b30` : pred > 0 (self-heal permis). L'énumération cibles/tuiles reste au générateur ;
    `score` = le terme d'utilité par cible."""
    ability_id = int(ActiveAbilityType.Heal)  # 18 (#158)

    def score(self, effective_heal, hp_max, is_friend, is_twisted, target_faction):
        """Utilité de soin d'une cible, ou None si `pred <= 0` (gate `ShouldExecute`). `effective_heal` =
        soin EFFECTIF `min(HealAmount, missing)` (le générateur le cape via `predict_heal_effective`, #79 ;
        auparavant saturé à `missing`). Le skip « cible déjà buffée TwistedScience » est un gate
        d'ÉNUMÉRATION (fait par le générateur, inconditionnel), pas ce CustomUtility."""
        heal_term = heal_utility(effective_heal, hp_max, is_friend=is_friend, is_boss=False)
        custom = (100 + (100 if target_faction == "Genestealers" else 0)) if is_twisted else 0
        pred = custom + heal_term
        return pred if pred > 0 else None


class RepairPlaybook(ComparablePlaybook):
    """Repair (tag 28) — DORMANT : la prédiction repair est non-dégât (idx 0x29), pas encore portée ;
    aucune ability repair dans les batailles testées. `make_damage_predictions` -> None (pas d'attaque)."""
    ability_id = int(ActiveAbilityType.Repair)  # 28 (#158)

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        return None


# Instance unique du fallback (spéciales sans bespoke) + du soin (dispatch par le générateur).
DEFAULT_PLAYBOOK = DefaultActiveAbilityPlaybook()
NORMAL_ATTACK_PLAYBOOK = NormalAttackPlaybook()
HEAL_PLAYBOOK = HealPlaybook()

register(RepairPlaybook())
