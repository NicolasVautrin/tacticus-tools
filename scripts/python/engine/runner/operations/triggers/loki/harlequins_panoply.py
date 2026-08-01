"""`1227 HarlequinsPanoply_IgnoreHits` -- le MARQUEUR qui fait JETER les coups restants d'une attaque,
et le cluster natif qui le pose, le lit et le retire (#366-r1).

i2 (`HarlequinsPanoply`, passif de `eldarSmnHarlequin` / `eldarNpc3Harlequin`) : « The first time each
turn this unit blocks a hit, all further hits of the attack are discarded and the Harlequin Player
moves 1 hex closer to the origin of the attack, if possible. »

## Ce qu'EST l'effet 1227 (et ce qu'il n'est PAS)

`IdunBattle.Entities.Effects.Loki.HarlequinsPanoply_IgnoreHitsEffect$$.ctor` n'appelle QUE
`IdunBattle.Entities.Effects.BaseEffect$$.ctor` : **aucun canal** (ni stat-mod, ni damage-bonus, ni
`ApplyInternal`). La classe ne surcharge qu'UNE chose, `$$CreateTargetTrigger` -- et pour un
`BaseEffect` ce virtuel est le **trigger de RETRAIT** : `IdunBattle.Entities.Effects.BaseEffect$$
CreateHandleTriggerAbilities` bâtit `Triggered(<ce trigger>, GetRemoveEffectBehaviour())` avec
`GetRemoveEffectBehaviour() = DSLBehaviors$$RemoveEffect(Effect@0x38)` (même mécanique que
`UntilOfEndTurnEffect`, cf. `triggers/loki/until_of_end_turn.py`).

    HarlequinsPanoply_IgnoreHitsEffect$$CreateTargetTrigger
        = DSLTriggers$$On(EventTriggerType.Attack = 9, ownerNeedsToBeAlive: true)
          & DSLTriggers$$get_OwnerIsTarget

=> 1227 est un marqueur qui vit **le temps d'UNE attaque** : posé au coup bloqué, retiré à la clôture
de l'attaque (`IdunBattle.Operations.FinishAttackOperation$$Execute` émet `On(9)` INCONDITIONNELLEMENT).

## Les trois artefacts natifs du cluster (décompilé LU, build `rnca9r7q6c`)

### 1. POSE -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HarlequinsPanoplyAbility$$CreateTrigger`
```
On(0x3c = UnitBlocked, true)
  & get_OwnerIsTarget
  & NOT HasTrait(Caster@DSLSelectors+0x48, 0xd = UnitTrait.Object)
  & NOT HasBlockedThisTurn(Target@DSLSelectors+0x60)
  & NOT HasEffect(Owner@DSLSelectors+0x30, 0x4cb = 1227, onlyActive: false, targetType: 6)
```
Le mapping des slots `DSLSelectors` est celui déjà établi par le port
(`entities/selectors/accessors.py` : `+0x30 Owner`, `+0x40 Actor`, `+0x48 Caster`, `+0x60 Target`,
dérivé de `DSLSelectors+0x30 == factory+0x148` et de `get_OwnerIsActor = AreEqual(+0x30, +0x40)`).
Sur le vecteur `On(UnitBlocked)`, l'`AbilityEntities` que bâtit `IdunBattle.Operations.
ADamageOperation$$EvaluateAfterHitTriggers` porte **caster = l'ATTAQUANT** et
**owner = actor = target = le DÉFENSEUR** (cf. `triggers/loki/anvil_shield.py`, même vecteur) : les
trois gates se lisent donc « l'attaquant n'est pas un Object », « le porteur n'a pas déjà bloqué ce
tour » et « le porteur ne porte pas déjà 1227 ».

### 2. POSE -- `...HarlequinsPanoplyAbility$$CreateBehaviour(abilityState, triggerType)`
La fonction FOURCHE sur `triggerType`, et seules DEUX branches existent :
```
if (triggerType == 0x3c = UnitBlocked)
    AddEffect(0x4cb = 1227, AbilityStateReference, targets = Owner@+0x30, options = null)
  + TriggerAbilityDelayed(Owner@+0x30, 0x4a3 = 1187 HarlequinsPanoply, unitSelectionType = 3)
else if (triggerType == 0x20 = Custom)
    Inform(0xb6, EntityId(Actor@+0x40))
  + If( NOT IsAdjacent(Owner@+0x30, Caster@+0x48, 3),
        MoveUnit(Owner@+0x30, First(SortByDistance(MovableTilesInRange(Owner, MainTileOfUnits(Owner),
                                                   <DSLFormulas+0x20>), Caster@+0x48), 1)) )
else
    Nothing()
```
La branche `Custom` est le DÉPLACEMENT de 1 hex : elle n'est atteinte que par le
`TriggerAbilityDelayed` posé par la branche `UnitBlocked`. **NON PORTÉE** -- résidu nommé, cf. §Résidus.

### 3. LECTURE -- `...HarlequinsPanoplyAbility_DiscardHits$$CreateTrigger` / `$$CreateBehaviour`
```
CreateTrigger   = get_OwnerIsTarget & On(6 = PreAttackHit, true)
                  & HasEffect(Owner@+0x30, 0x4cb = 1227, onlyActive: false, targetType: 6)
CreateBehaviour = DSLBehaviors$$DiscardHit(Owner@+0x30)
```
`DSLBehaviors$$DiscardHit` -> `IdunBattle.Entities.Behaviours.DiscardHitBehaviour$$Execute` -> slot
`IOperationProcessor` 0x46 -> `IdunBattle.Operations.DiscardHitOperation$$Execute`, qui RÉÉCRIT le
`Nullable<AttackHit>` du coup courant (`OngoingAttack+0x98`) en
`AttackHit(damage, damageProfile, discard: 1)` (`IdunBattle.Core.AttackHit$$.ctor` : `+0x00 damage`,
`+0x04 damageProfile`, **`+0x08 discard`**).

## OÙ le discard MORD, et CE QU'IL CONSOMME (le point qui décide de la fidélité RNG)

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, dans l'ordre LU :

1. `IdunBattle.Core.HitDamage$$GetDamage(<bornes>, ...)`  -- 1 tirage SSI min != max ;
2. `RollCritical` (slot 0xa)                              -- 1 tirage SSI `couldCrit` et cc >= 1 ;
3. `OngoingAttack+0x98 = Nullable<AttackHit>(damage, profile, discard: 0)` (posé AVANT les events) ;
4. émission de `On(6 = PreAttackHit)` **puis** `On(7 = PreAttackDamageHit)` ;
5. **RELECTURE** de `OngoingAttack+0x98` : `if (attackHit.discard != 0) return this;`
   -- `this` est l'`OperationResult` **memset à 0** en tête de fonction : ni dégât, ni block, ni
   `EvaluateAfterHitTriggers` ;
6. sinon : `CalculateDamageOperation` (slot 4), `RandomlyResolveMinMaxDamage` (slot 8), sub-op 0x42
   (block rolls), puis `ADamageOperation$$EvaluateAfterHitTriggers`.

⚠ Conséquence portée ici : un coup DISCARDÉ consomme **quand même** les tirages (1) et (2), et
**aucun** des tirages en aval. C'est l'inverse d'un « coup qui n'a pas eu lieu ».

Et côté boucle, `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` appelle
`IdunBattle.Operations.ADamageOperation$$RegisterBlocks(result, hitGroup)` **APRÈS** le retour
d'`ExecuteHit` -- donc APRÈS `EvaluateAfterHitTriggers`, donc APRÈS `On(UnitBlocked)`. C'est ce qui
rend le gate `NOT HasBlockedThisTurn` VRAI au coup qui bloque le premier : le compteur n'est
incrémenté qu'ensuite. `RegisterBlocks` appelle le slot 0x4c ->
`IdunBattle.Operations.RegisterBlockOperation$$Execute` ->
`IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterBlockMade` (`+0x8c += 1`), et
`HasBlockedThisTurn` est exactement `TimesBlockedThisTurn(unit) > 0` avec
`IdunBattle.Entities.Triggers.TimesBlockedThisTurnFormula$$Calculate` = ce même `+0x8c`.
Reset : `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetBlocksMadeThisTurn`, appelé par
`IdunBattle.Operations.StartTurnOperation$$ResetUnit` -- dans la MÊME séquence que
`ResetAttacksReceivedThisTurn` / `ResetReceivedDamageThisTurn`, déjà portée par
`operations/turnflow.py` (portée = les unités du joueur ENTRANT).

## POURQUOI un INTERCEPTEUR per-coup et pas le bus de triggers

Le bus du port émet `On(PreAttackHit)` et `On(UnitBlocked)` **UNE FOIS PAR ATTAQUE**
(`dispatch/attack.py`, résidu de granularité déjà documenté là-bas), et `On(PreAttackHit)` est émis
**avant** le calcul du crit-chance parce que son seul consommateur historique (ThrillSeekers) y pose
un stat-mod que ce calcul doit voir. Les deux triggers de ce cluster, eux, sont **per-COUP** et n'ont
aucun gate `IsFirstHitInSeries` : les router sur le bus per-attaque les rendrait soit muets (le
discard n'aurait aucun coup à jeter), soit faux.

Le port instancie donc les DEUX classes ci-dessous depuis un intercepteur appelé PAR COUP, aux DEUX
places natives exactes (juste après l'étape 2 pour le discard, juste après la sub-op 0x42 pour le
block). Les classes restent des mirrors 1:1 de `CreateTrigger`/`CreateBehaviour` -- ce qui change,
c'est QUI les appelle, pas ce qu'elles évaluent. Elles ne sont donc **pas** inscrites dans
`ABILITY_TRIGGERS` (une inscription les ferait firer une 2e fois, per-attaque et au mauvais moment).
Seul le trigger de RETRAIT, qui est bien per-attaque (`On(9)` = clôture), passe par `EFFECT_TRIGGERS`.

## Résidus NOMMÉS (non portés)

* `HarlequinsPanoplyAbility$$CreateBehaviour` branche `Custom` = le **déplacement de 1 hex vers
  l'attaquant** (`MoveUnit` + `Inform(0xb6)`), armé par `TriggerAbilityDelayed(..., unitSelectionType
  = 3)`. Le port ne modélise pas la file différée du natif (slot `IOperationProcessor` 6) et exécuter
  le mouvement inline, au milieu de la résolution d'une attaque, ferait entrer les vecteurs
  `On(PreUnitMove)` / `On(UnitAfterMove)` (overwatch) dans un ordre qui n'est PAS celui du natif.
  Non porté, et donc NON couvert : la position finale du porteur après une attaque bloquée.
* `HarlequinsPanoplyAbility_MoveVisual` (`On(0x1f = PreUnitMove) & get_OwnerIsActor &
  NOT TriggeringAbilityIs(HarlequinsPanoply)` -> `Inform({0x82: 1})`) : purement VISUEL.
* `HarlequinsPanoplyAbility$$CannotBeGuaranteedKilled` / `$$SurvivesByDiscardingHits` : face
  PRÉDICTION du même passif (le gate `DamagePredictionResult@0x89`, cf.
  `services/damage_prediction.py`). Non porté ici -- c'est le résidu déjà nommé par #372.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, Inform, Seq
from .....entities.effect_type import EffectType
from .....entities.selectors import (Actor, Caster, First, MovableTilesInRange, SortByDistance,
                                     Tiles)
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.triggers import IsAdjacent, Not
from ....components import PositionComponent, UnitComponent
from ....abilities.behaviours import (AddEffect, MoveUnit, RemoveEffect, TriggerAbilityDelayed,
                                      entities_from_state)
from ....state import State
from ..base import EffectTrigger, TriggerEvent, TriggeredAbility, _unit_trait_names

HARLEQUINS_PANOPLY_IGNORE_HITS = int(EffectType.HarlequinsPanoply_IgnoreHits)   # 0x4cb = 1227
_ON_BLOCKED = int(EventTriggerType.UnitBlocked)          # 0x3c = 60
_ON_PRE_ATTACK_HIT = int(EventTriggerType.PreAttackHit)  # 6
_ON_ATTACK = int(EventTriggerType.Attack)                # 9
# `IdunBattle.Entities.Enum.TriggeredAbilityType.HarlequinsPanoply` = 0x4a3, l'`AbilityOrEffect` que
# `BaseTriggeredAbility$$Execute` pose dans `CurrentAbility` avant d'exécuter le behaviour.
HARLEQUINS_PANOPLY_ABILITY = 1187


def _has_ignore_hits(state: State, unit_id: int) -> bool:
    """`HasEffect(Owner@+0x30, 0x4cb, onlyActive: FALSE, targetType: 6)`.

    ⚠ `onlyActive` est le 4e argument de `IdunBattleLogic.Entities.DSLTriggers$$HasEffect` (cf.
    l'en-tête d'`anvil_shield.py` pour la chaîne `HasEffectTrigger` -> `HasOneOfEffects` ->
    `IsOwnerOfEffect`, où `param_4 != 0` exige `EffectComponent+0x5c`). Les DEUX call-sites du cluster
    passent **0** : un 1227 inactif compterait tout autant. Le port ne teste donc PAS `is_active` --
    et 1227 n'a de toute façon aucune `CreateActiveCondition` (le ctor n'appelle que `BaseEffect`).
    `targetType = 6 = 2|4` = les deux branches owned|incoming, comme partout ailleurs."""
    eff = getattr(state, "effects", None)
    if eff is None or unit_id is None:
        return False
    return any((not e.consumed) and (not e.expired) and e.effect_type == HARLEQUINS_PANOPLY_IGNORE_HITS
               for e in eff.by_unit.get(int(unit_id), []))


def _blocks_made_this_turn(state: State, unit_id: int) -> int:
    """`IdunBattle.Entities.Triggers.TimesBlockedThisTurnFormula$$Calculate` = `ActorStatisticsComponent
    + 0x8c`. Logé sur le `UnitComponent` du port -- MÊME résidu structurel que
    `received_damage_this_turn` / `times_attacked_this_turn` (case-202 §6)."""
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    uc = e.get_component(UnitComponent) if e is not None else None
    return int(getattr(uc, "blocks_made_this_turn", 0) or 0) if uc is not None else 0


def register_block_made(state: State, unit_id: int) -> None:
    """`IdunBattle.Operations.RegisterBlockOperation$$Execute` ->
    `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterBlockMade`, qui pousse **DEUX**
    compteurs : `+0x8c += 1` (ce tour) ET `+0x88 += 1` (la bataille). #393-r1.

    Appelé PAR COUP BLOQUÉ, comme le natif : `IdunBattle.Operations.ADamageOperation$$RegisterBlocks`
    est invoquée par `AttackDamageOperation$$ExecuteHits` à chaque tour de boucle, et pousse le slot
    0x4c dès que le résultat du coup porte `didBlock` (`result+0x22`).

    `+0x88` n'a AUCUN lecteur porté (seul `BattleStatisticQuery$$GetTotalBlocksMadeByUnit` le lit,
    côté statistiques de fin de bataille) : il est écrit pour rester le mirror exact du `+=` double,
    comme `tiles_moved_this_battle` l'est de `RecordTilesMoved`. Il n'est PAS remis à zéro au
    turn-start -- `ActorStatisticsComponent$$ResetBlocksMadeThisTurn` n'écrit que `+0x8c`."""
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None:
        return
    uc.blocks_made_this_turn = int(getattr(uc, "blocks_made_this_turn", 0) or 0) + 1
    uc.blocks_made_this_battle = int(getattr(uc, "blocks_made_this_battle", 0) or 0) + 1


class HarlequinsPanoplyAbility(TriggeredAbility):
    """`HarlequinsPanoplyAbility` volet POSE -- `$$CreateTrigger` + la branche `UnitBlocked` de
    `$$CreateBehaviour` (cf. l'en-tête de module pour les deux corps LUS).

    Le behaviour natif est `AddEffect(1227, targets = Owner) + TriggerAbilityDelayed(Owner, 1187, 3)` ;
    depuis #406 les DEUX termes sont portés -- le second ENFILE la branche `Custom` (le déplacement)
    dans `state.pending_triggered_abilities`, drainée à la clôture du message par `Runner.apply`.
    `options = null` au call-site natif -> durée par DÉFAUT (`duration_rounds=None`), ce qui laisse
    `remaining` à la valeur que `StaticBattleRules.Effect$$DefaultAmountOfRounds` rend pour 1227 : le
    retrait effectif vient du trigger `On(9)` de la classe d'effet, pas d'un timer."""
    event_id = _ON_BLOCKED
    TRIGGERED_ABILITY_ID = HARLEQUINS_PANOPLY_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # get_OwnerIsTarget : le porteur est la CIBLE de l'attaque -- c'est lui qui vient de bloquer.
        if ev.target_id != self.owner_id:
            return False
        # NOT HasTrait(Caster@+0x48, Object) : sur ce vecteur `Caster` = l'ATTAQUANT.
        if ev.actor_id is not None and has_trait(_unit_trait_names(state, ev.actor_id),
                                                 UnitTrait.Object):
            return False
        # NOT HasBlockedThisTurn(Target@+0x60) : « the FIRST time each turn this unit blocks a hit ».
        if _blocks_made_this_turn(state, self.owner_id) > 0:
            return False
        # NOT HasEffect(Owner@+0x30, 1227, onlyActive: false, 6) : anti re-pose dans la MEME attaque.
        return not _has_ignore_hits(state, self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `AddEffect(1227, AbilityStateReference, targets = Owner@+0x30)` : source ET cible sont le
        # PORTEUR (`AbilityStateReference` = le caster de la triggered = son owner). La feuille
        # `AddEffect` du port lit la source dans `ctx.caster` et la cible via son selecteur -> les
        # deux pointent l'owner.
        entities = entities_from_state(state, self.owner_id, self.owner_id, actor_id=ev.actor_id)
        AddEffect(HARLEQUINS_PANOPLY_IGNORE_HITS, "HarlequinsPanoply_IgnoreHits", Caster(),
                  duration_rounds=None).execute(entities, ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        if not placed:
            return None
        # 2e terme de l'`op_Addition` natif : `TriggerAbilityDelayed(Owner@+0x30, 0x4a3 = 1187,
        # unitSelectionType = 3)`. Il ENFILE (il n'execute pas) : cf. `dispatch/pending.py`. C'est
        # ce qui fait sortir le deplacement de la resolution de l'attaque -- le natif ne draine sa
        # file qu'apres le retour de `action()` dans
        # `IdunBattle.Messages.InputMessageProcessor$$RunPhase`.
        # ⚠ Le natif l'arme MEME quand l'`AddEffect` n'a rien pose (les deux termes sont des effets
        # PURS -> `CombinedBehaviour` ne court-circuite pas). Le port le place APRES le gate `placed`
        # parce que ce gate est aussi celui du re-arme : `matches` refuse deja toute 2e pose tant que
        # 1227 est la (`NOT HasEffect`) et tout 2e blocage du tour (`NOT HasBlockedThisTurn`), donc
        # `placed == False` n'est atteignable que sur un `state.effects` absent -- ou enfiler serait
        # un mouvement sans marqueur. ECART NOMME, inerte sur tout scenario porte.
        TriggerAbilityDelayed(Caster(), HARLEQUINS_PANOPLY_ABILITY,
                              unit_selection_type=3).execute(entities, ectx)
        return {"ability": "HarlequinsPanoply", "unit": int(self.owner_id),
                "effect": HARLEQUINS_PANOPLY_IGNORE_HITS,
                "queued": any(p.get("queued") for n, p in ectx.emitted
                              if n == "TriggerAbilityDelayed"),
                "attacker": (int(ev.actor_id) if ev.actor_id is not None else None)}


class HarlequinsPanoplyDiscardHitsAbility(TriggeredAbility):
    """`HarlequinsPanoplyAbility_DiscardHits` -- `get_OwnerIsTarget & On(6 = PreAttackHit) &
    HasEffect(Owner, 1227)` -> `DiscardHit(Owner)`.

    `execute_behaviour` ne mute rien du `State` : le natif écrit le flag `discard` du
    `Nullable<AttackHit>` de l'attaque COURANTE (`OngoingAttack+0x98`), que `ExecuteHit` relit deux
    instructions plus loin pour sortir sans dégât. Le port n'a pas d'`OngoingAttack` matérialisée ; le
    flag est rendu à l'intercepteur, qui EST la relecture (cf. `HarlequinsPanoplyHitInterceptor`)."""
    event_id = _ON_PRE_ATTACK_HIT
    TRIGGERED_ABILITY_ID = HARLEQUINS_PANOPLY_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.target_id != self.owner_id:                      # get_OwnerIsTarget
            return False
        return _has_ignore_hits(state, self.owner_id)          # HasEffect(Owner, 1227, false, 6)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return {"ability": "HarlequinsPanoply_DiscardHits", "unit": int(self.owner_id),
                "discard": True}


class HarlequinsPanoplyCustomAbility(TriggeredAbility):
    """`HarlequinsPanoplyAbility$$CreateBehaviour`, branche **`triggerType == 0x20 = Custom`** -- le
    DEPLACEMENT d'un hex vers l'attaquant (#406). MIRROR de l'arbre LU :

        Inform(0xb6, EntityId(Actor@sel+0x40))
      + If( NOT IsAdjacent(Owner@sel+0x30, Caster@sel+0x48, 3),
            MoveUnit(Owner@sel+0x30,
                     First(SortByDistance(MovableTilesInRange(Owner@sel+0x30,
                                                              MainTileOfUnits(Owner@sel+0x30),
                                                              <DSLFormulas+0x20>,
                                                              ignoreFlags: 1,
                                                              ignoreUnitsOnTiles: 0),
                                          Caster@sel+0x48),
                           amount: 1, ignoreForcedTargets: 0),
                     options) )

    (l'ordre de l'`op_Addition` est bien `Inform` PUIS le `If` : `LAB_181193fde` compose
    `op_Addition(<Inform>, <If>)`. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    HarlequinsPanoplyAbility$$GetMoveTile` est le MEME arbre de selecteurs, extrait en helper.)

    CE QUI EST LU, ET COMMENT IL SE TRADUIT
    ---------------------------------------
    * **`<DSLFormulas+0x20>` = la constante 1.** `IdunBattleLogic.Entities.DSLFormulas$$.ctor` remplit
      cinq formules constantes -- `+0x18` = 0, **`+0x20` = 1**, `+0x28` = 2, `+0x30` = 100,
      `+0x38` = -1. La portee du deplacement est donc `Const(1)` : UN hex, pas la stat Movement.
    * **`options` du `MoveUnit` = TOUTES au DEFAUT.** La struct de 0x40 octets construite au
      call-site est a ZERO sauf `+0x10`, qui recoit `DSLTriggers+0x40`. Or
      `IdunBattleLogic.Entities.DSLTriggers$$.ctor` pose en `+0x40` un trigger CONSTANT (et en
      `+0x48` sa negation, `op_LogicalNot` du meme). Dans
      `IdunBattle.Entities.Behaviours.MoveUnitBehaviour$$Execute`, le champ correspondant
      (`behaviour+0x70`) a pour DEFAUT `1` et son bit part inverse (`^ 0x101`) : poser le trigger
      TOUJOURS-VRAI y reproduit exactement le defaut. Le `MoveUnit` porte -- qui ne modelise aucune
      option -- est donc fidele a CE call-site.
    * **`ignoreFlags = 1`** (contraste avec Waaagh/RammingSpeed, qui passent 0) : la garde d'entree
      de `IdunBattle.Core.Services.MovementQuery$$FindAnyOrAllMoveableTiles` est levee, donc un
      porteur qui a DEJA bouge ce tour se replace quand meme. Le port ne modelise pas cette garde
      (`MovableTilesInRange.ignore_flags` est accepte et non lu) -> le comportement coincide sur
      `ignoreFlags = 1`, et l'argument est passe pour la tracabilite.
    * **`MainTileOfUnits(units)`** = le selecteur concret `IdunBattle.Entities.Selectors.
      UnitsMainTilesSelector`, deja porte sous le nom `Tiles` (`entities/selectors/units.py`).
    * **`IsAdjacent(a, b, 3)`** : le 3e argument est le mode de selection, inerte pour le predicat
      par-paire (meme lecture que VigilanceEternal / SkyStrike).

    LE MAPPING DES ROLES (le point ou l'on se trompe)
    ------------------------------------------------
    Sur le vecteur `On(0x3c = UnitBlocked)`, l'`AbilityEntities` natif porte `caster = l'ATTAQUANT`
    et `owner = actor = target = le DEFENSEUR`. Le port construit son contexte par
    `entities_from_state(state, caster_id = owner, target_id = owner, actor_id = <attaquant>)` --
    convention deja en place pour la face POSE de ce meme cluster. Donc, cote port :
    `Caster()` = `Owner@+0x30` natif (le porteur) et `Actor()` = `Caster@+0x48` natif (l'attaquant).
    `Actor@+0x40` natif vaut le DEFENSEUR sur ce vecteur, mais il n'est lu que par la charge utile
    de l'`Inform`, que le port DROPPE (pas de bus de messages) -> sans consequence.

    OU CETTE CLASSE EST APPELEE : jamais par le bus d'events -- elle n'a pas de `CreateTrigger`.
    Elle est inscrite dans `CUSTOM_TRIGGERED_ABILITIES[1187]` et n'est atteinte que par le drain
    (`operations/triggers/dispatch/pending.py`), lui-meme arme par le `TriggerAbilityDelayed` de la
    face POSE. `matches` rend donc `True` : le natif ne re-evalue AUCUN trigger sur ce chemin
    (le declenchement est imperatif) -- la seule condition restante, `NOT IsAdjacent`, est DANS
    l'arbre, evaluee a l'etat COURANT au moment du drain."""
    event_id = int(EventTriggerType.Custom)          # 0x20 -- jamais emis par le bus du port
    TRIGGERED_ABILITY_ID = HARLEQUINS_PANOPLY_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, self.owner_id, actor_id=ev.actor_id)
        e = state.get_entity(int(self.owner_id))
        pc = e.get_component(PositionComponent) if e is not None else None
        before = (pc.col, pc.row) if pc is not None else None
        Seq(
            Inform(0xb6),
            If(Not(IsAdjacent(Caster(), Actor())),
               MoveUnit(Caster(),
                        First(SortByDistance(
                            MovableTilesInRange(Caster(), Tiles(Caster()), Const(1),
                                                ignore_flags=True, ignore_units_on_tiles=False),
                            Actor()))))
        ).execute(entities, ectx)
        pc = e.get_component(PositionComponent) if e is not None else None
        after = (pc.col, pc.row) if pc is not None else None
        return {"ability": "HarlequinsPanoply_Move", "unit": int(self.owner_id),
                "attacker": (int(ev.actor_id) if ev.actor_id is not None else None),
                "from": before, "to": after, "moved": bool(before != after)}


class HarlequinsPanoplyIgnoreHitsRemove(EffectTrigger):
    """`HarlequinsPanoply_IgnoreHitsEffect$$CreateTargetTrigger` = `On(9 = Attack) & get_OwnerIsTarget`,
    monté par `BaseEffect$$CreateHandleTriggerAbilities` avec `GetRemoveEffectBehaviour()` =
    `RemoveEffect(Effect@0x38)` -- exactement le patron d'`UntilOfEndTurnRemove`.

    `On(9)` est émis par `IdunBattle.Operations.FinishAttackOperation$$Execute` à la clôture de CHAQUE
    attaque (normale ET ability) ; le port l'émet aux deux endroits (`after_hit_normal_attack` /
    `after_hit_ability_attack`). Le marqueur ne survit donc PAS à l'attaque qui l'a posé.

    COLLAPSE ASSUMÉ, identique à `UntilOfEndTurnRemove` : le natif retire L'INSTANCE, le port retire
    les stacks non consommés du type sur le porteur -- `AddEffectOperation` garantit au plus une
    instance par unité."""
    event_id = _ON_ATTACK
    effect_type = HARLEQUINS_PANOPLY_IGNORE_HITS

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`get_OwnerIsTarget` : sur le vecteur de clôture `On(9)`, `target` = le DÉFENSEUR. Le
        marqueur ne part donc qu'à la fin de l'attaque qui VISAIT son porteur -- pas à la clôture
        d'une attaque de son porteur contre quelqu'un d'autre."""
        return ev.target_id == self.owner_id

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(self.effect_type, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": int(self.effect_type), "owner": int(self.owner_id), "removed": removed}


class HarlequinsPanoplyHitInterceptor:
    """Les DEUX points d'accrochage PER-COUP d'`IdunBattle.Operations.AttackDamageOperation$$
    ExecuteHit(s)`, matérialisés pour la boucle `_run_hits` du port.

      * `should_discard(idx)` = l'étape 5 d'`ExecuteHit` (relecture de `OngoingAttack+0x98` juste après
        l'émission de `On(6)`/`On(7)`). Évalue `HarlequinsPanoplyDiscardHitsAbility` ;
      * `on_blocked(idx)`     = la branche `param_6 != 0` d'`ADamageOperation$$EvaluateAfterHitTriggers`
        (`On(0x3c)`), PUIS `RegisterBlocks` -- dans CET ordre, qui est ce qui rend le gate
        `NOT HasBlockedThisTurn` vrai au premier blocage du tour.

    L'objet est construit pour TOUT couple (attaquant, défenseur) : `register_block_made` doit tourner
    même sans porteur, sinon le compteur `+0x8c` ne refléterait plus le natif. Quand le défenseur ne
    porte pas le passif, `should_discard` retourne False sans rien allouer."""
    __slots__ = ("state", "attacker_id", "defender_id", "_pose", "_discard", "_transfer", "events")

    def __init__(self, state: State, attacker_id: Optional[int], defender_id: Optional[int],
                 carries_panoply: bool):
        self.state = state
        self.attacker_id = attacker_id
        self.defender_id = defender_id
        self.events: list[dict] = []
        self._pose = HarlequinsPanoplyAbility(int(defender_id)) if carries_panoply else None
        self._discard = HarlequinsPanoplyDiscardHitsAbility(int(defender_id)) if carries_panoply else None
        # #411 : la TROISIEME accroche du meme point d'`ExecuteHit`. Elle ne depend PAS du passif
        # du defenseur (le porteur de `DrawFire` est un ALLIE ADJACENT du defenseur, pas le
        # defenseur), donc elle est montee inconditionnellement -- sa detection est interne.
        from .draw_fire import DrawFireTransfer
        self._transfer = DrawFireTransfer(state, attacker_id, defender_id)

    def _event(self, event_id: int) -> TriggerEvent:
        """L'`AbilityEntities` des deux vecteurs natifs : `caster = actor = l'ATTAQUANT`,
        `owner = target = le DÉFENSEUR` (`ExecuteHit` pour `On(6)`,
        `EvaluateAfterHitTriggers` pour `On(0x3c)` -- les deux passent le même couple)."""
        return TriggerEvent(event_id, self.attacker_id, self.defender_id,
                            ranged=False, profile=None,
                            triggering_ability=HARLEQUINS_PANOPLY_ABILITY)

    def should_discard(self, hit_index: int) -> bool:
        if self._discard is None:
            return False
        ev = self._event(_ON_PRE_ATTACK_HIT)
        if not self._discard.matches(self.state, ev):
            return False
        out = self._discard.execute_behaviour(self.state, ev)
        if out:
            self.events.append({**out, "hit": int(hit_index)})
        return True

    def should_transfer(self, hit_index: int) -> bool:
        """#411 -- la branche `!HasValue` de l'etape 5 d'`ExecuteHit`, JUMELLE de `should_discard`.

        `should_discard` demande « le `PendingHit` est-il marque `discard` ? » ; celle-ci demande
        « le `PendingHit` a-t-il ete EFFACE ? », ce qui n'arrive que par
        `IdunBattle.Operations.TransferHitOperation$$Execute`. Les deux relisent le MEME
        `UnitComponent+0x98`, au MEME instant (juste apres `On(6)` puis `On(7)`), et le natif les
        teste dans cet ordre : `HasValue` d'abord (discard), `!HasValue` ensuite (transfert).

        L'appel LANCE l'attaque de transfert sur le porteur -- le natif l'execute DANS le dispatch
        d'`On(7)`, donc AVANT le resolve du coup courant. Cf. `draw_fire.py`."""
        return self._transfer.transfer(hit_index)

    def finish(self) -> None:
        """Le RETRAIT du marqueur a la CLOTURE de l'attaque, mirror LOCAL du
        `Triggered(On(9) & OwnerIsTarget, RemoveEffect)` de la classe d'effet -- et parade a un
        RESIDU STRUCTUREL du port, pas une invention.

        Le natif emet `On(9)` depuis `IdunBattle.Operations.FinishAttackOperation$$Execute`, appelee
        par `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` (slot 0x3b) apres CHAQUE cible
        -- donc pour TOUTE attaque, y compris celles qu'un trigger declenche. Le port, lui, emet
        `On(9)` au niveau MESSAGE (`DamageHandler.visit_AttackUnitMessage`), et les attaques
        declenchees par un trigger -- **le TIR D'OVERWATCH en tete** -- appellent
        `AttackDamageOperation.execute` DIRECTEMENT : c'est le residu deja decrit par
        `dispatch/attack.py::attack_damage_attack_triggers`, qui a fait DEPLACER `On(10)` a la sortie
        de l'operation pour exactement cette raison. Sans cette parade, un marqueur 1227 pose par un
        block d'overwatch ne serait JAMAIS retire -> le porteur annulerait TOUTES les attaques
        suivantes. C'est la degradation la plus permissive possible, et elle serait SILENCIEUSE.

        IDEMPOTENT, donc cumulable avec l'entree `EFFECT_TRIGGERS[1227]` : `RemoveEffect` sur un
        marqueur deja parti ne rend rien. Meme place que `On(10)` = 2e event de `FinishAttackOperation`."""
        if self._pose is None:
            return
        if not _has_ignore_hits(self.state, self.defender_id):
            return
        out = HarlequinsPanoplyIgnoreHitsRemove(int(self.defender_id)).execute_behaviour(
            self.state, self._event(_ON_ATTACK))
        if out:
            self.events.append(out)

    def on_blocked(self, hit_index: int) -> None:
        if self._pose is not None:
            ev = self._event(_ON_BLOCKED)
            if self._pose.matches(self.state, ev):
                out = self._pose.execute_behaviour(self.state, ev)
                if out:
                    self.events.append({**out, "hit": int(hit_index)})
        # `RegisterBlocks` : APRES l'evenement, comme `ExecuteHits` (qui l'appelle au retour
        # d'`ExecuteHit`, donc apres `EvaluateAfterHitTriggers`).
        register_block_made(self.state, self.defender_id)


def make_hit_interceptor(state: State, attacker_id: Optional[int],
                         defender_id: Optional[int]) -> Optional[HarlequinsPanoplyHitInterceptor]:
    """Fabrique l'intercepteur per-coup pour une attaque. `None` quand il n'y a rien à intercepter
    (pas de `State`, pas de défenseur) -- `_run_hits` retombe alors exactement sur son chemin d'avant.

    Le porteur est reconnu par la MÊME source que `collect_triggered_abilities` : les passives
    MESURÉES (`UnitContext.passive_abilities`, hiérarchie 2) quand le canal a parlé, sinon la
    dérivation gameconfig par `visualId`. C'est ce qui rend une GREFFE (`catalog_inject.
    graft_passive_ability`) visible ici, exactement comme pour le bus."""
    if state is None or defender_id is None:
        return None
    from ....components import StatsComponent
    import gameconfig as GC
    e = state.get_entity(int(defender_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    measured = getattr(sc.ctx, "passive_abilities", None)
    if measured is None:
        vid = getattr(sc.ctx, "visual_id", None)
        measured = list(((GC.unit(vid) or {}) if vid else {}).get("passiveAbilities") or [])
    carries = "HarlequinsPanoply" in (measured or [])
    return HarlequinsPanoplyHitInterceptor(state, attacker_id, defender_id, carries)
