"""`Abilities.Active.Loki.PsykerExtraAttackAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateBehaviour..) — splash « Smite » du trait Psyker.

1 classe = 1 ability native (VA citée). Cf. `loki/__init__.py` pour le regroupement « Loki »."""
from __future__ import annotations

from typing import Optional

import gameconfig as GC

from ....state import State
from ....components import is_effect_target
from ....abilities.behaviours import AttackWithAttackDamage, entities_from_state
from .....entities.effect_type import EffectType
from .....entities.stats import StatType
from .....entities.formulas import StatAmount, PercentageOf
from .....entities.selectors import Caster, Target
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import (TriggeredAbility, TriggerEvent, _adjacent_damageable_enemies, _pick_randomly)

PSYKER_OWNER_SUPPRESS = int(EffectType.HuntersBeyondDeathPsykerSuppression)   # 1191 — effet owner qui supprime le splash psyker
PSYKER_TARGET_SUPPRESS = int(EffectType.WatchedOver_PsykerSuppression)        # 1533 — effet cible qui supprime le splash psyker
PSYCHIC_PROFILE = "Psychic"


def psyker_smite_tree(pct: int, profile: str):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateBehaviour` (MIRROR 1:1 du DECOMPILE) :
        AttackWithAttackDamage(
            caster     = @0x160,
            targets    = PickRandomly(Damageable(Enemies(caster, AdjacentUnits(target@0x178, 1, 3))), 1),
            damageNode = PercentageOf(StatAmount(Self@0x148, statType=0=Attack, variant=0=Current),
                                      Direct(GetNumberConstant(0xf=psykerExtraDmg))),
            profile    = Psychic (0xd) )
    Port : `AttackWithAttackDamage(Target(), amount=PercentageOf(Direct(pct), StatAmount(Caster(), Attack)),
    Psychic, ranged, hits=1)`. Le SELECTEUR natif `PickRandomly(Damageable(Enemies(AdjacentUnits)))` est
    resolu EN AMONT dans `execute_behaviour` (`_adjacent_damageable_enemies` = pool + `_pick_randomly` =
    tirage RNG id-trie ; DSL-ification du selecteur = #216) et la cible RESOLUE passee via `Target()` — ==
    le collapse `Units(Cache(First(Nearest(...))))` documente sur la feuille (mono-cible). Le degat-node
    `PercentageOf(StatAmount(Caster(), Attack), Direct(pct))` (feuilles formule EXISTANTES) fait calculer a la
    feuille `base = round_fix64(pct * Attack / 100)` (Fix64 = mirror natif `PercentageOf.Calculate` ; l'ancien
    imperatif `round(float)` etait moins fidele -> ici aligne sur l'oracle) puis router via
    `execute_normal_like(base, pierce, hits=1, spread_pct=0, Psychic, ranged)` = MEME Operation/pipeline que
    l'ancien corps. Le `spread_pct=0` est LU, pas suppose (#449-r2) : le 8e argument
    `Nullable<AttackDamageBehaviourOptions>` est passe VIDE (`local_78..local_58 = 0`, les 0x28 octets mis a
    zero juste avant l'appel a `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`), donc
    `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor` (`GetValueOrDefault`) pose `+0x9e = 0`, qui
    transite `$$ExecuteTarget` (options+0x2f) -> `AttackDamageOperation$$ExecuteHit` (request+0x6a) ->
    `DamagePrediction$$PredictAttackRaw` branche PLATE `MinMaxDamageFix64(d, d)`. ⚠ La conclusion de #449
    (cote PREDICTION le byte vaut 1 EN DUR, donc spread TOUJOURS) NE SE TRANSPORTE PAS ici : c'est le MEME
    byte, mais cote COMBAT c'est l'ability qui l'ecrit -- `SkyStrikeAbility$$ExecuteBehaviour` le pose a 1.
    Bit-exact BY CONSTRUCTION (meme base, meme
    pierce via `profile_pierce`, meme rng). `pct`/`profile` passes par l'appelant (`GC.trait("Psyker").
    variables.psykerExtraDmg` / `PSYCHIC_PROFILE`) pour eviter tout couplage d'import."""
    amount = PercentageOf(Const(pct), StatAmount(Caster(), int(StatType.ATTACK)))   # Direct(pct) x StatAmount(Attack)
    # `ability_type=0x3f5` (1013) : le smite porte l'AbilityOrEffect « kind attaque-normale » (case-34
    # ProbableDamageEvent AbilityOrEffect(1013)) -> threade au payload d'event On(9) after-hit — c'est le
    # gate de la branche 2 d'`IdunBattleLogic.Entities.DSLFactory$$OnNormalAttackOrSmite` (LordOfTempests AddIce #35).
    return AttackWithAttackDamage(Target(), "Psyker", profile, is_melee=False, amount=amount, hits=1,
                                  ability_type=0x3f5)


class PsykerExtraAttackAbility(TriggeredAbility):
    """Splash « Smite » du trait Psyker (`PsykerExtraAttackAbility`, IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateBehaviour..).
    Trigger `On(0x26)=NormalAttack` (IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateTrigger) → fire UNIQUEMENT sur le vecteur attaque-NORMALE
    (`after_hit_normal_attack`), JAMAIS sur le splash/ability (chemin `AbilityDamageOperation`, events {6,8,0x3d}
    sans 0x26) → pas de chain (verdict RE #147/#150)."""
    event_id = EventTriggerType.NormalAttack

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateTrigger : OwnerIsActor & IsRangedAttack & DamageProfileIs(Psychic) & NON suppressé.
        if self.owner_id != ev.actor_id:                       # OwnerIsActor
            return False
        if not ev.ranged or ev.profile != PSYCHIC_PROFILE:     # IsRangedAttack & DamageProfileIs(0xd)
            return False
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$
        # IsPsykerAttackSuppressed` = `IsEffectTarget(Caster@DSLSelectors+0x48, 0x4a7 = 1191)
        # op_BitwiseOr IsEffectTarget(Target@+0x60, 0x5fd = 1533)`, pris en `op_LogicalNot`.
        #
        # ⚠ `IsEffectTarget` != `HasEffect` : l'instance `1191` est POSEE SUR SON PORTEUR
        # (`HuntersBeyondDeathAbility$$CreateBehaviour` = `AddEffect(0x4a7, ref, Owner, Owner, ...)`),
        # et c'est le PSYKER ENNEMI qui figure dans sa liste `EffectComponent.Targets @+0x48`. Le
        # gate lisait `has_effect(psyker, 1191)`, structurellement TOUJOURS faux -> le splash
        # n'etait JAMAIS supprime (mesure case-418-r1 : `spaceHound` a d = 2, live 0 splash, port
        # 1506 de degat Psychic fantome).
        if is_effect_target(state, self.owner_id, PSYKER_OWNER_SUPPRESS):
            return False
        # `1533` : le `WatchedOver_PsykerSuppressionEffect$$CreateTargetSelector` n'a AUCUN symbole
        # (corps deduplique) -> geometrie NON LUE, donc NON INSCRITE (pas de port speculatif). Le
        # foyer rend `None` ; on ne ferme pas sur un inconnu -- comportement strictement anterieur,
        # et residu NOMME (case-418-r1 §residus).
        if is_effect_target(state, ev.target_id, PSYKER_TARGET_SUPPRESS) is True:
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # CIBLE : selecteur natif `PickRandomly(Damageable(Enemies(caster, AdjacentUnits(target,1,3))), 1)`
        # resolu IMPERATIVEMENT (pool `_adjacent_damageable_enemies` + tirage RNG `_pick_randomly` id-trie ;
        # DSL-ification du selecteur = #216). La cible RESOLUE est passee a l'arbre via `Target()`.
        cands = _adjacent_damageable_enemies(state, self.owner_id, ev.target_id)
        if not cands:
            return None
        picked = _pick_randomly(state, cands)
        if picked is None:
            return None
        # behaviour = arbre DSL `psyker_smite_tree()` (mirror 1:1 de IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateBehaviour) :
        # AttackWithAttackDamage(target, PercentageOf(StatAmount(Attack), psykerExtraDmg%), Psychic). La feuille
        # (mode `amount`) calcule base Fix64 + route `execute_normal_like` -> MEME Operation/args que l'ancien
        # corps (bit-exact BY CONSTRUCTION). pct source = trait config (== `GetNumberConstant(0xf)` natif, validee).
        pct = int((GC.trait("Psyker") or {}).get("variables", {}).get("psykerExtraDmg") or 0)
        ectx = ExecutionContext(state=state, rng=state.rng)
        psyker_smite_tree(pct, PSYCHIC_PROFILE).execute(
            entities_from_state(state, self.owner_id, picked), ectx)
        hit = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        if hit is None:
            return None
        atk = hit.get("attack") or {}
        return {"trait": "Psyker", "target": picked, "base": atk.get("base"),
                "pierce": atk.get("pierce"), "result": atk}
