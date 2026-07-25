"""Effet-triggers du namespace natif `IdunBattleLogic.Entities.Effects.*` — effets porteurs de leur
propre trigger (`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTrigger). 1 classe par effet (VA citée) :
- `Overwatch_AutoAttackEffect` — auto-attaque after-move.
- `ContaminatedEffect` — tile-effet posant le sous-effet -X% armure sur l'occupant.
(Le DISPATCH itère ces classes via `EFFECT_TRIGGERS` dans `dispatch.py`.)"""
from __future__ import annotations

from typing import Optional

from ...state import State
from ...components import OwnerComponent, StatsComponent, UnitComponent
from ....entities.stats import StatType
from ....entities.traits import UnitTrait, has_any_trait
from ....entities.effect_type import EffectType
from ....dsl.event_trigger_type import EventTriggerType
from ..damage import AttackDamageOperation
from .base import EffectTrigger, TileEffectTrigger, _unit_trait_names, _in_attack_range

# --- Contaminated (tile-effect, RE #132/#128) : enter-tile + tick posent le sous-effet -X% armure --------
CONTAMINATED_TILE = int(EffectType.Contaminated)        # 1244 — effet de TUILE (posé par attaque Toxic, OnToxicDamage).
CONTAMINATED_UNIT = int(EffectType.Contaminated_Unit)   # 1245 — sous-effet -X% FixedArmor posé sur l'unité.
# #158 : ex-`CONTAMINATED_IMMUNE_TRAIT = 2027` (mort depuis #154 : l'immunité gate via
# `has_any_trait(names, (UnitTrait.ContagionsOfNurgle, UnitTrait.Mechanical))`) retiré. 2027 = UnitTrait.ContagionsOfNurgle.
# Magnitude Contaminated_Unit (#132, RE re-expert 2026-07-14) : `ContaminatedStatModifierEffect.GetDynamicStat
# ModificationAmount IdunBattle.Entities.Effects.Loki.ContaminatedStatModifierEffect$$GetDynamicStatModificationAmount` = `-BattleQuery.GetEffectConfig(EffectType=6)` ; `BattleQuery.GetEffectConfig
# IdunBattle.Core.Services.BattleQuery$$GetEffectConfig` lit `BattleConfiguration.Effect[+0x28]` = **`ContaminatedArmorReductionPct`** (=30). => le sous-effet
# reduit le FixedArmor cible de -30 %. Source = section `Effect` de la BC (seed-bc.json), lue ICI (PAS un hardcode ;
# defaut 30 = miroir de la valeur BC connue, comme `_DMG_CFG.get('TrenchReductionPercentage', -50)` en prediction).
import json as _json_cfg
from .... import weights as _weights_cfg
_EFF_CFG: dict = (_json_cfg.loads(_weights_cfg.DEFAULT_BC.read_text(encoding="utf-8")).get("Effect", {})
                  if _weights_cfg.DEFAULT_BC.exists() else {})
CONTAMINATED_ARMOR_REDUCTION_PCT: int = int(_EFF_CFG.get("ContaminatedArmorReductionPct", 30))

# --- Overwatch (effet-trigger after-move) ---------------------------------------------------------
OVERWATCH_AUTO_ATTACK = int(EffectType.Overwatch_AutoAttack)   # 1009 — effectType de l'effet porteur du trigger
#   (ATTENTION #158 : 1009 = EffectType.Overwatch_AutoAttack ICI, PAS UnitTrait.Resilient=1009 — contexte = effet)
OVERWATCH_TARGET_IMMUNE = int(EffectType.Infiltrate)  # 1048 — mover immunisé (Overwatch_AutoAttackEffect.AdditionalTriggers : NOT)
OVERWATCH_SOURCE_DISABLE = int(EffectType.Pinned)     # 1065 — overwatch désactivé sur l'overwatcher (AdditionalActivateTrigger : NOT)


def _is_immune_to_contaminated(state: State, unit_id: int) -> bool:
    """`IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$EntityIsImmuneToEffect` (décompilé) = `HasTrait(0x7eb=2027=
    ContagionsOfNurgle) OR IsMechanical(unit) OR BaseEffect.EntityIsImmuneToEffect(...)`. #154 : porte les
    DEUX premières branches — `ContagionsOfNurgle` (trait, `UnitTrait` #146) ajouté au gate, + `Mechanical`
    (APPROXIMATION trait de la propriété native `UnitExtensions.IsMechanical` — best-effort pré-existant, la
    propriété peut couvrir plus que le seul trait Mechanical). Non porté (sous-gate résiduel documenté) : la
    3e branche `BaseEffect.EntityIsImmuneToEffect` (immunité générique d'effet, input offline non capté)."""
    return has_any_trait(_unit_trait_names(state, unit_id),
                         (UnitTrait.ContagionsOfNurgle, UnitTrait.Mechanical))


class OverwatchAutoAttack(EffectTrigger):
    """`Overwatch_AutoAttackEffect` (base `RangedAutoAttackEffect`) — auto-attaque after-move.
    Trigger `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateTargetTrigger = `On(4) & NOT AreFriends(overwatcher,mover) &
    IsInAttackRange(overwatcher,mover,3) & AdditionalTriggers` (Overwatch : `NOT mover a 0x418` ;
    AdditionalActivateTrigger : `NOT overwatcher a 0x429`). Behaviour `IdunBattle.Entities.Effects.Loki.Overwatch_AutoAttackEffect$$GetAttackBehaviour =
    `UseActiveAbility(NormalAttack)` sur le mover ⇒ **attaque NORMALE** de l'overwatcher (chemin
    `AttackDamageOperation.execute`, déjà bit-exact)."""
    event_id = EventTriggerType.UnitAfterMove
    effect_type = OVERWATCH_AUTO_ATTACK

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        mover = ev.actor_id                                   # l'unité qui vient de bouger
        ow = state.get_entity(self.owner_id)
        mv = state.get_entity(mover)
        if ow is None or mv is None:
            return False
        # TARGET-VALIDITY = leg de re-validation du PUMP FIFO (#201). Le mover (cible de l'overwatch)
        # doit etre VIVANT. Natif : les pending triggered-abilities after-move (les 2 overwatch) sont
        # draines UN PAR UN par `IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities` (snapshot+Clear de la file
        # #5) ; chaque item = un `IdunBattle.Messages.InputMessageProcessor$$RunPhase(0xf)` qui appelle `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` juste
        # apres son callback, AVANT l'item suivant. Donc si le 1er overwatch TUE le mover, VerifyDeaths le
        # retire et le 2e overwatch ne trouve plus de cible : `IdunBattle.Entities.Effects.Loki.Overwatch_AutoAttackEffect$$GetAttackBehaviour` =
        # `UseActiveAbility(NormalAttack)` sur une unite morte = fizzle (les selecteurs DSL de cible operent
        # sur AllAliveMachines, #202). Le port COLLAPSE ce pump dans `evaluate_trigger_operation` (registre
        # snapshot + drain par-item re-evaluant `matches` contre l'etat courant + morts appliquees INLINE via
        # `_fire_death_if_killed` = alive=False) : ce gate est la re-validation de cible du drain. Sans lui,
        # le 2e overwatch tirait sur le CADAVRE (double-fire = divergence #201 prouvee deterministe + live).
        mvu = mv.get_component(UnitComponent)
        if mvu is not None and not mvu.alive:
            return False
        owc = ow.get_component(OwnerComponent)
        mvc = mv.get_component(OwnerComponent)
        if owc is None or mvc is None or owc.team == mvc.team:   # NOT AreFriends ⇒ ennemi
            return False
        if not _in_attack_range(state, self.owner_id, mover):    # IsInAttackRange(...,3)
            return False
        if state.effects is not None and (                       # additional : NOT 0x418 / NOT 0x429
                state.effects.has_effect(mover, effect_type=OVERWATCH_TARGET_IMMUNE)
                or state.effects.has_effect(self.owner_id, effect_type=OVERWATCH_SOURCE_DISABLE)):
            return False
        return True

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        if state.rng is None:                                    # l'attaque consomme le RNG (spread/rolls)
            return None
        res = AttackDamageOperation.execute(state, self.owner_id, ev.actor_id, 20)  # attaque NORMALE
        return {"effect": "Overwatch_AutoAttack", "attacker": self.owner_id,
                "target": ev.actor_id, "result": res}


class ContaminatedTileEffect(TileEffectTrigger):
    """`IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateHandleTriggerAbilitiesInternal (effet de tuile 0x4dc) — pose le
    sous-effet `Contaminated_Unit` (0x4dd, -X% FixedArmor, 1 round) sur l'unité qui ENTRE (`On(4)` &
    `AreEqual(triggeringTile, effectTile)`) ou qui OCCUPE au tick de tour (`On(0x12)`) la tuile contaminée,
    sauf si déjà présent (`!HasEffect(0x4dd)`) ou immune (trait 2027 / Mechanical IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$EntityIsImmuneToEffect). Enter+tick
    partagent le behaviour (appliquer à la cible) → `event_ids=(4, 0x12)`.
    ⚠ MAGNITUDE (X%) NON RÉSOLUE (#132) → l'effet est posé avec `value=None` (PRÉSENT mais inerte-stat)."""
    effect_type = CONTAMINATED_TILE
    event_ids = (EventTriggerType.UnitAfterMove, EventTriggerType.TurnStart_EffectActivation)

    def _target_unit(self, state: State, ev: "TriggerEvent") -> Optional[int]:
        occ = self._unit_on_tile(state)
        if occ is None:
            return None
        if ev.event_id == EventTriggerType.UnitAfterMove:
            # ENTER : gate `AreEqual(triggeringTile, effectTile)` = le MOVER doit être sur MA tuile (pas un
            # occupant d'une autre tuile contaminée qui se déclencherait à chaque move ailleurs).
            return occ if occ == ev.actor_id else None
        return occ                                        # TICK : occupant courant

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        return self._target_unit(state, ev) is not None

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        uid = self._target_unit(state, ev)
        if uid is None or state.effects is None:
            return None
        if state.effects.has_effect(uid, effect_type=CONTAMINATED_UNIT):
            return None                                   # !HasEffect(0x4dd) : pas de re-pose
        if _is_immune_to_contaminated(state, uid):        # trait 2027 / Mechanical
            return None
        # MAGNITUDE #132 (RE IdunBattle.Entities.Effects.Loki.ContaminatedStatModifierEffect$$GetDynamicStatModificationAmount = -GetEffectConfig(6) = -ContaminatedArmorReductionPct%, cf. constante) :
        # le sous-effet reduit le FixedArmor de -30 %. Le stat-layer applique `get_stat_modification_amount` en
        # ADDITIF -> on materialise le -X% en DELTA PLAT pre-calcule = -round(FixedArmor * pct/100). Lu AVANT la
        # pose (gate has_effect -> pas de recursion). `value=None` si stats absentes = present mais stat-inerte.
        val: Optional[int] = None
        te = state.get_entity(uid)
        tsc = te.get_component(StatsComponent) if te is not None else None
        if tsc is not None and CONTAMINATED_ARMOR_REDUCTION_PCT > 0:
            armor = int(tsc.ctx.stat(StatType.FIXED_ARMOR))
            if armor > 0:
                val = -round(armor * CONTAMINATED_ARMOR_REDUCTION_PCT / 100)
        from ..effects import AddEffectOperation            # lazy : évite le cycle triggers<->effects
        from ...abilities.base import convert_rounds_to_turns
        # #98 : `IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$AddEffectBehavior` = `AddDynamicStatModifierEffect(sel,
        # 0x4dd, 0x10, **TurnsFromRounds(1)**)` -> la duree passe par `BattleQuery.ConvertRoundsToTurns`
        # IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns (le port envoyait 1 TOUR en dur, soit la moitie dans un duel a 2 joueurs).
        eff = AddEffectOperation.execute(
            state, source=self.owner_id, target=uid, effect_type=CONTAMINATED_UNIT,
            name="Contaminated_Unit", duration_override=convert_rounds_to_turns(state, 1),
            value=val)                                       # #132 : -pct% FixedArmor (BC Effect config)
        if eff is None:
            return None
        return {"tile_effect": "Contaminated", "tile": self.owner_id, "unit": uid,
                "applied": "Contaminated_Unit", "armor_delta": val, "on_event": ev.event_id}
