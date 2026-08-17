"""`Abilities.Triggered.Loki.LordOfTempests_AddIceAbility` (passif triggered 1194 de Njal
`spaceStormcaller.passiveAbilities=['LordOfTempests']`) — face RUNNER « pose de glace » du passif (#35).
RE (decompile ghidra, build gqfc5mff6c) :

  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateTrigger` = `OnNormalAttackOrSmite() & get_OwnerIsCaster` :
      * `IdunBattleLogic.Entities.DSLTriggers$$OnNormalAttackOrSmite` = `On(0x26=38 NormalAttack) | (On(9=Attack) &
        <trigger DAT_18322f680>(DirectAbilitySelector(AbilityOrEffect 0x3f5=1013)))`. Le 2e terme
        est LE MÊME nœud que la 2e branche d'`IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack` (même classe DAT_18322f680,
        même ctor gshared MISLABELÉ `HasUsedActiveAbilityThisTurnTrigger`, même sélecteur 1013 —
        verdict `dsl-wave3-specs.md` « IsNormalAttack [PROUVE] ») : « l'ability COURANTE de l'event
        est du KIND attaque-normale (marqueur 0x3f5=1013) ». Le splash « Smite » du trait Psyker
        porte `AbilityOrEffect(1013)` (case-34 §chaîne Njal) → la branche 2 = le coup de SMITE.
      * i2 : « The hex of each enemy that is hit by Njal's normal attacks is covered in Ice at the
        end of the attack. » = cible principale (branche `On(38)`) + victime du splash Psyker
        (branche `On(9) & kind==1013`).
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateBehaviour` = feuille UNIQUE
        `AddEffect(0x11=Ice, AbilityStateReference, source=Self@0x148, cible=Tiles(Target@0x178),
                   <Nullable ZÉROÉ 16 octets>, 0)`
    → pose l'effet **Ice (17)** sur la TUILE de la cible touchée. 5e arg zéroé = PAS de
    `TurnsFromRounds` → `DefaultAmountOfRounds(0x11)=2` (switch natif idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds, transcrit
    `effects.py _DEFAULT_ROUNDS[0x11]=2`). `source=Self@0x148` == le caster (triggered
    Owner==Caster, cf. behaviours.py `entities_from_state`) → la feuille portée `AddEffect`
    (source = `entities.caster`) est le mirror exact — pas besoin de l'overload source explicite.

DISPATCH : branche 1 = vecteur `after_hit_normal_attack` (`On(38)`, actor=Njal, target=cible
principale) ; branche 2 = vecteur `after_hit_ability_attack` (`On(9)`) gaté `ev.ability_type ==
0x3f5` — le kind est threadé par la feuille `AttackWithAttackDamage` (param `ability_type`,
`psyker_smite_tree` passe `0x3f5` ; les AUTRES attaques d'ability laissent None → branche 2
muette, fidèle : leur AbilityOrEffect != 1013). Le `On(9)` de la voie NORMALE ne porte PAS le
kind : non requis (la branche 1 a déjà glacé la tuile de la cible principale — la re-pose de la
branche 2 serait un no-op `already-present` d'AddEffect), et on n'encode pas la claim non-RE'd
« l'event finish de la normale porte 1013 ».

AVAL : la glace posée nourrit la face DECISION déjà portée `LordOfTempests_ExtraDamageEffect`
(`extra_damage.py` : +extraDmg × Count(Ice ring-1 de la position d'attaque)) — côté COMBAT runner
via l'`att_ctx` positionnel threadé par `attacker_modifiers` (damage_model.py, même lecture
`state.effects.by_unit[tile_id]` que le PickTile MV71). Le blocage de mouvement Ice
(`NotBlockingMovementOfTraits(0x11)`, mécanique 1 de terrain-effects.md) reste NON porté (#131,
déféré faute de board jouable) ; le crit-bonus Ice (mécanique 2, `IceEffect.
IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack`) reste NON porté (gate ICE, terrain-effects.md §2).

DOCTRINE #149 : prédicats du trigger COLLAPSÉS impérativement (`matches` : OwnerIsCaster +
event/kind) ; la feuille E (`AddEffect` tile-domain) délègue à `AddEffectOperation`."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from .....entities.selectors.accessors import Target
from .....entities.selectors.units import Tiles
from .....entities.effect_type import EffectType
# Feuille pure (`enum` seul) -- 2 modules `engine.*` charges, aucune arete ajoutee.
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

ICE_TILE = int(EffectType.Ice)          # 17 (0x11) — effet de TUILE Ice (durée défaut 2 rounds)
# ⚠ L'ENUM EST TRANCHE (#270-r1-r1-r3-r1, build `rnca9r7q6c`) : `1013` est un membre valide de
# QUATRE enums, donc l'ordinal ne discrimine rien. Le discriminant est la SURCHARGE
# d'`IdunBattle.Core.AbilityOrEffect$$op_Implicit` empruntee par
# `IdunBattleLogic.Entities.DSLTriggers$$OnNormalAttackOrSmite+0x4d` -- celle dont le parametre se
# nomme `triggeredAbility` et qui appelle `IdunBattle.Core.AbilityOrEffect$$set_TriggeredAbility`.
# Le nom natif le corrobore : c'est la branche « OrSmite ». Detail : `abilities/attack_type.py`.
SMITE_KIND = int(TriggeredAbilityType.PsykerExtraAttack)   # 0x3f5 = 1013 — le splash Smite Psyker

_ON_NORMAL = int(EventTriggerType.NormalAttack)   # 38 (0x26) — branche 1
_ON_ATTACK = int(EventTriggerType.Attack)         # 9 — branche 2 (gate kind==1013)


def lord_of_tempests_add_ice_tree():
    """Feuille de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateBehaviour` (MIRROR 1:1 du DÉCOMPILÉ) :
        AddEffect( effectType = 0x11=Ice (TILE),
                   source     = Self@0x148 (== caster, triggered Owner==Caster),
                   cible      = Tiles(Target@0x178) = la MainTile de la cible touchée )
    `duration_rounds=None` = pas de TurnsFromRounds (mirror du Nullable zéroé natif) →
    `DefaultAmountOfRounds(0x11)=2`. RNG-free. La feuille tile-domain convertit la position en id
    de tuile (`_add_effect_target_id`) et route vers `AddEffectOperation.execute(target=tile_id,
    17, "Ice")` — no-op si la tuile est déjà glacée (gate `already-present`)."""
    return AddEffect(ICE_TILE, "Ice", Tiles(Target()), duration_rounds=None)


class LordOfTempestsAddIceAbility(TriggeredAbility):
    """`LordOfTempests_AddIceAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateBehaviour) —
    passif de Njal (`spaceStormcaller.passiveAbilities=['LordOfTempests']`, triggered id 1194).
    Glace la tuile de CHAQUE ennemi touché par une attaque normale de Njal : cible principale
    (`On(38)`) + victime du splash Smite Psyker (`On(9) & kind==0x3f5`), toujours `OwnerIsCaster`.
    L'autre moitié du passif (+extraDmg × hex d'Ice ring-1) = `LordOfTempestsExtraDamageEffect`
    (extra_damage.py, face DECISION/COMBAT déjà portée — lit la glace posée ici via att_ctx).

    ⚠ **`fire_on_death` = VRAI (#10015).**
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility` surcharge
    `IdunBattle.Entities.Abilities.ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` et son corps
    rend VRAI (`b0 01 c3`, LU -- `metadata/allow_for_dead_owner.tsv`), contre le FAUX de
    `IdunBattle.Entities.Abilities.BaseTriggeredAbility`. Njal tue par la riposte de sa propre
    attaque normale continue donc de glacer la tuile de sa cible, et le port ne le faisait pas :
    `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` coupait avant `matches`.
    Symetrique DELIBERE du fait deja ecrit plus bas -- << sa tuile reçoit Ice même si le coup l'a
    tuée >> vaut pour la CIBLE morte ; ceci le rend vrai pour le PORTEUR mort."""
    event_id = _ON_NORMAL                              # primaire (branche 1) ; `event_ids` = les deux
    event_ids = (_ON_NORMAL, _ON_ATTACK)
    #: `ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` -> VRAI (cf. la docstring).
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:               # get_OwnerIsCaster (l'attaquant EST le porteur)
            return False
        if ev.event_id == _ON_NORMAL:                  # branche 1 : On(0x26=38 NormalAttack)
            return True
        # branche 2 : On(9=Attack) & <kind attaque-normale 0x3f5> — seul le smite Psyker le porte.
        return ev.event_id == _ON_ATTACK and ev.ability_type == SMITE_KIND

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """Behaviour = arbre DSL `lord_of_tempests_add_ice_tree()` (mirror 1:1 IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateBehaviour) :
        `AddEffect(Ice=17, Tiles(Target()))`. Target() = la cible de l'événement (l'ennemi touché) ;
        sa tuile reçoit Ice même si le coup l'a tuée (le natif pompe le trigger APRÈS le dégât —
        l'entité-cadavre garde sa position, `Tiles` résout sa MainTile)."""
        if state.effects is None or getattr(state, "board", None) is None:
            return None                                # pas d'EffectsState/board -> pose impossible
        if ev.target_id is None or state.get_entity(ev.target_id) is None:
            return None                                # cible absente de l'ECS -> pas de tuile résolvable
        ectx = ExecutionContext(state=state, rng=state.rng)
        lord_of_tempests_add_ice_tree().execute(
            entities_from_state(state, self.owner_id, ev.target_id), ectx)
        placed = [p["target"] for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        if not placed:                                 # tuile déjà glacée -> no-op (anti-repose)
            return None
        return {"passive": "LordOfTempests", "unit": self.owner_id,
                "iced_tile": placed[0], "on_event": ev.event_id}
