"""`Vitarus` -- relique `TriggeredAbilityType` 0x5be = **1470**, porteur `bloodMephiston`
(Blood Angels, HERO du pool). Comme `ChaliceOfBaal` et `DawnBlade`, la cle porte DEUX classes
natives, et les DEUX comptent :

  * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Vitarus_InitAbility` -- parent
    `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` (`frida/classes.tsv`), n'override
    QUE `$$GetEffectType`, dont le corps ENTIER est `return 0x5ba` (= 1466 `EffectType.Vitarus`).
    Le reste vient de la base (`CreateTrigger = OnOwnerSpecificAbilityInit(this.AbilityType)`,
    `CreateBehaviour = AddEffect(GetEffectType(), AbilityState(Owner), source = Owner,
    targets = Owner, turns = <zeroe>)`) -- owner-effect PERMANENT pose a l'init, exactement le
    patron `ToughToKill` / `Skullsmasher` / `Ramshackle`. Porte par
    `entities/effects/factory.py::ABILITY_INIT_OWNER_EFFECTS["Vitarus"]`.
  * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.VitarusAbility` -- le volet FEU, porte ici.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================
`...VitarusAbility$$CreateTrigger` :

      IdunBattleLogic.Entities.DSLTriggers$$On(EventTriggerType.Attack = 9, ownerNeedsToBeAlive = true)
    & IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster
    & IdunBattleLogic.Entities.DSLTriggers$$IsMeleeAttack
    & (   IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack
        | IdunBattleLogic.Entities.DSLTriggers$$AreEqual(
              <DSLSelectors+0x88>,                                     # TriggeringAbility
              AbilityOrEffect(TriggeredAbilityType.FuryOfTheAncients = 0x4df = 1247) ) )

Le `0x4df` est LU AUX OCTETS (`mov edx, 0x4df` puis `call` dont le rel32 resout sur
`IdunBattle.Core.AbilityOrEffect$$op_Implicit(triggeredAbility:TriggeredAbilityType)`, PAS sur les
surcharges `ActiveAbilityType` / `EffectType`) -- l'ordinal seul n'aurait rien tranche, les trois
enums partageant des centaines de valeurs. Il concorde avec l'i2 :
« The hexes of each enemy hit by Mephiston's normal melee attack **or by Fury of the Ancients** are
set on Fire. If these attacks hit enemies on hexes with Fire, they deal +{[extraDmg]} Damage and
extinguish the Fire. »

`...VitarusAbility$$CreateBehaviour` :

    tiles = IdunBattleLogic.Entities.DSLSelectors$$Tiles(Target@DSLSelectors+0x60)
    cond  = IdunBattleLogic.Entities.DSLTriggers$$Any(
                list    = tiles,
                trigger = IdunBattleLogic.Entities.DSLTriggers$$HasEffect(
                              entity = <DSLSelectors+0x68>,            # l'ELEMENT courant du Any
                              effectType = EffectType.Fire = 5,
                              onlyActive = false,
                              targetType = EffectTargetType.Both = 6 ) )
    return IdunBattleLogic.Entities.DSLBehaviors$$If(
               cond,
               ifBehaviour   = IdunBattleLogic.Entities.DSLBehaviors$$Inform(
                                   tag = IdunBattle.Streams.TagKey.Is_Modified = 0xe9, value = 1)
                             + IdunBattleLogic.Entities.DSLBehaviors$$RemoveEffect(
                                   selector = tiles,
                                   effectType = Nullable(EffectType.Fire = 5),
                                   replaceableEffectType = null),
               elseBehaviour = IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(
                                   effectType = EffectType.Fire = 5,
                                   abilityState = BaseTriggeredAbility$$get_AbilityStateReference,
                                   targets = tiles,
                                   turns = Nullable<int>(null) ) )

`IdunBattle.Entities.Effects.Loki.VitarusEffect$$CreateEffectDamageBonusForAttack` (l'effet 1466
que `Vitarus_InitAbility` pose sur le porteur) porte la MEME condition, plus le bonus :

    EffectBonus.ForAddition(
        cond & get_OwnerIsCaster & IsMeleeAttack & (IsNormalAttack | TriggeringAbilityIs(1247)),
        DSLFormulas$$ConfigVar(AbilityVariableType.extraDmg = 8, GetAbilityState(this), <effet+0x60>) )

et `IdunBattle.Entities.Effects.Loki.VitarusEffect$$.ctor` = `BaseEffect(AbilityOrEffect(
TriggeredAbilityType.Vitarus = 0x5be), true)` (`mov edx, 0x5be` LU aux octets), donc le `ConfigVar`
lit l'entree gameconfig **`Vitarus`** (`variables.extraDmg`, 10 paliers de RELIQUE).

================================================================================================
LE COUPLE EST UN VA-ET-VIENT, ET L'ORDRE COMPTE
================================================================================================
L'effet 1466 LIT le feu, l'ability l'ETEINT ou le POSE. Le vecteur `On(9 = Attack)` est
POST-ATTAQUE (`dispatch/attack.py`, fin de l'attaque), tandis que le bonus de degat est evalue
PENDANT le calcul du coup (`damage_model.attacker_modifiers`) : le natif lit donc le feu AVANT que
`CreateBehaviour` ne l'eteigne, et le port le fait pareil BY CONSTRUCTION -- les deux etages sont
sur deux vecteurs distincts, dans cet ordre. C'est ce qui rend le comportement cyclique lisible :
1er coup sur une tuile SANS feu -> pas de bonus, feu POSE ; coup suivant sur la MEME tuile ->
bonus applique, feu ETEINT.

RESIDUS NOMMES
  * `Inform(TagKey.Is_Modified, 1)` -- le bus de messages natif n'est pas modelise (meme choix que
    `FireOfAbsolution` / `HeavyWarpFlamer`) ; le noeud est present pour le MIRROR STRUCTUREL.
  * `onlyActive = false` sur le `HasEffect` -- l'accesseur tuile du port (`ctx.tile_has_effect`)
    n'expose aucune notion d'effet de tuile actif/inactif ; sans consequence tant qu'aucun effet de
    TUILE ne porte d'`ActiveCondition` (aucun a ce jour), cf. la docstring d'`entities/triggers.py::
    HasEffect`.
  * NIVEAU de la variable -- `extraDmg` a 10 entrees (niveaux de RELIQUE), indexees nativement par
    `BC.Units[].TertiaryAbilityLevel` ; l'effet, lui, est materialise sur le porteur et lit son
    couple `(ability_level, ability_variables_multiplier)`. Sur un runner normalise le niveau vaut
    50 et `ability_var` clampe au dernier palier -- les deux lectures coincident. Meme residu que
    `DawnBlade` avant #357.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, Inform, op_add
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Target
from .....entities.selectors.units import Tiles
from .....entities.triggers import HasEffect
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....streams.tag_key import TagKey
from ....components import UnitComponent
from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, RemoveEffect
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "Vitarus"
VITARUS = int(TriggeredAbilityType.Vitarus)                        # 0x5be = 1470
FURY_OF_THE_ANCIENTS = int(TriggeredAbilityType.FuryOfTheAncients)  # 0x4df = 1247
FIRE_TILE = int(EffectType.Fire)                                    # 5
FIRE_TILE_NAME = EffectType.Fire.name

_ON_ATTACK = int(EventTriggerType.Attack)                           # `On(9, alive = true)`


def target_tile_is_on_fire() -> HasEffect:
    """`Any( Tiles(Target@DSLSelectors+0x60),
             HasEffect(<element>, EffectType.Fire = 5, onlyActive: false,
                       EffectTargetType.Both = 6) )`.

    Le port n'a pas de noeud `Any` : `entities/triggers.py::HasEffect` ITERE deja son selecteur et
    rend VRAI des qu'UN element porte l'effet -- c'est litteralement `Any(sel, HasEffect(element))`.
    `as_ids=True` est OBLIGATOIRE : `Tiles` rend par defaut des POSITIONS `(col,row)`, que
    `HasEffect` ne sait pas router (il n'a que les branches unite-dict et tuile-ID) -- le gate
    serait FAUX en silence."""
    return HasEffect(Tiles(Target(), as_ids=True), FIRE_TILE, active_only=False)


def vitarus_behaviour_tree() -> If:
    """`If(cond, Inform(Is_Modified, 1) + RemoveEffect(tiles, Fire), AddEffect(Fire, tiles))`
    -- ARBRE 1:1.

    `duration_rounds=None` : la surcharge natif est `AddEffect(effectType, abilityState, targets,
    turns:Nullable<int>)` avec `turns = null` -> duree PAR DEFAUT de l'effet
    (`DefaultAmountOfRounds`), la MEME que celle de `OnFireDamageAbility` (`fire.py`). Passer le
    defaut positionnel `1` ECRASERAIT cette duree (le vice deja corrige sur `on_fire_damage_tree`).

    `source_from_target=True` : le selecteur SOURCE de cette surcharge est NUL, et
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` retombe alors sur la CIBLE -- la
    source du FEU est donc la TUILE, jamais le caster. GROUND TRUTH live du jumeau
    (`FleshMetalGuns_TileEffectAbility`, #85) ; MEME choix que `on_fire_damage_tree`."""
    tiles = Tiles(Target(), as_ids=True)
    eteint = op_add(Inform(int(TagKey.Is_Modified)), RemoveEffect(FIRE_TILE, tiles))
    allume = AddEffect(FIRE_TILE, FIRE_TILE_NAME, Tiles(Target(), as_ids=True),
                       duration_rounds=None, source_from_target=True)
    return If(target_tile_is_on_fire(), eteint, allume)


class VitarusAbility(TriggeredAbility):
    """`VitarusAbility` -- a la FIN de chaque attaque de MELEE du porteur qui est soit son attaque
    NORMALE, soit `FuryOfTheAncients` (1247), la tuile de la cible passe de « pas de feu » a
    « en feu », ou l'inverse (le feu est ETEINT quand il etait deja la, et c'est ce meme regime qui
    a donne le `+extraDmg` via l'effet 1466)."""
    event_id = _ON_ATTACK
    TRIGGERED_ABILITY_ID = VITARUS                                  # 0x5be = 1470

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` -- le vecteur `On(9)` publie l'attaquant en `actor`/`caster`.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        if ev.target_id is None:
            return False
        # `On(9, ownerNeedsToBeAlive = true)` -- `<DSLTriggers+0x20>`.
        owner = state.get_entity(int(self.owner_id))
        ouc = owner.get_component(UnitComponent) if owner is not None else None
        if owner is None or (ouc is not None and not ouc.alive):
            return False
        # `IsMeleeAttack` -- `BattleQuery$$IsMeleeAttack` : VRAI seulement si la nature du coup est
        # PROUVEE melee (tri-etat, foyer `effects/base.py::is_melee_attack`, cf. #106).
        if getattr(ev, "ranged", None) is not False:
            return False
        # `IsNormalAttack(CurrentAbility@<DSLSelectors+0x88>)
        #  | AreEqual(CurrentAbility@<+0x88>, AbilityOrEffect(FuryOfTheAncients = 1247))`
        # -- les DEUX disjoints lisent LE MEME selecteur, donc un SEUL canal cote port :
        # `ev.ability_type`, le mirror de `CurrentAbility` (`dispatch/attack.py` le laisse a `None`
        # sur la voie NORMALE et pose l'id de l'ability sur la voie ABILITY).
        return self._current_ability_is_accepted(getattr(ev, "ability_type", None))

    @staticmethod
    def _current_ability_is_accepted(ability_type) -> bool:
        """`IsNormalAttack(CurrentAbility) | AreEqual(CurrentAbility, AbilityOrEffect(1247))`.

        `IsNormalAttack` -> `IdunBattle.Entities.Triggers.AbilityIsNormalAttackTrigger$$ShouldTrigger`
        -> `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$
        IsRegularAttack(<ability courante>)`, FAUX s'il n'y a AUCUNE ability dans le contexte. Cote
        port, `ability_type = None` EST la voie normale (`finish_attack_triggers` :
        « `ability_type` reste None sur la voie NORMALE »).

        ⚠ #1005-r3 -- FERME. `FuryOfTheAncientsAbility` (#927) construisait son `ChainAttackDamage`
        **sans passer `ability_type`** : son attaque arrivait ici avec `None` et entrait par le
        PREMIER disjoint au lieu du SECOND, ce qui rendait `AreEqual(CurrentAbility, 1247)`
        INATTEIGNABLE et `IsNormalAttack` PERMISSIF. L'observable etait identique SUR CE PORTEUR
        (les trois seules sources de melee de `bloodMephiston` -- attaque normale, l'attaque normale
        GRATUITE de `TheQuickening` 1151, et `FuryOfTheAncients` -- sont toutes acceptees par la
        disjonction NATIVE) ; ce qui manquait, c'etait une QUATRIEME attaque de melee d'ability qui
        n'annonce pas son kind, que le port aurait acceptee et le natif refusee.
        L'id est desormais threade (`fury_of_the_ancients.py`, `abilityType = AbilityOrEffect(this)`
        du natif). RAYON DE SOUFFLE MESURE AVANT (`probe_1005r3_fury_ability_type.py`) : sur les
        lecteurs portes d'`ev.ability_type`, **0 divergence de verdict** ; le SEUL changement est
        `AttackDamageOperation._damage_source_ability(1247, None)` = `1247` au lieu de `None` --
        c'est-a-dire l'attribution que le natif publie deja (`StaticBattleRules$$
        GetDamageSourceAbility` rend `currentAbility` des lors qu'elle n'est pas une attaque
        REGULIERE)."""
        if ability_type is None:
            return True
        return int(ability_type) == FURY_OF_THE_ANCIENTS

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), int(ev.target_id),
                                       actor_id=ev.actor_id)
        vitarus_behaviour_tree().execute(entities, ectx)
        placed = [p["target"] for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        removed = [p["target"] for n, p in ectx.emitted
                   if n == "RemoveEffect" and p.get("removed")]
        if not placed and not removed:
            return None
        return {"relic": ABILITY_ID, "owner": int(self.owner_id), "on": int(ev.target_id),
                "ignited_tiles": placed, "extinguished_tiles": removed, "dsl": True}
