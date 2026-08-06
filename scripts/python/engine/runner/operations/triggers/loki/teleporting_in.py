"""`IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` -- les
QUATRE triggers PROPRES de la famille « je descends du ciel », et le trigger UNIQUE de son effet
compagnon `IdunBattleLogic.Effects.TeleportMovingEffect`.

Tache #448-r2, tranche 1/4 : l'item CONFRONTABLE SANS RIEN MONTER = `1035
TeleportStrike_TeleportingIn` (trait `TeleportStrike`, **7 porteurs du pool rank 17**).

## La famille (classes.tsv, build `rnca9r7q6c`) -- QUATRE derivees, une seule base

    IdunBattle.Entities.Effects.Loki.ATeleportingEffect        <- IdunBattle.Entities.Effects.Common.UntargetableEffect
      TeleportStrike_TeleportingInEffect      EffectType 1035 (0x40b)   source 0x40d TriggeredAbilityType.TeleportStrike
      StormboyzStrike_TeleportingInEffect     EffectType 1140 (0x474)   source 0x475 TriggeredAbilityType.StormboyzStrike
      FearOfTheUnseen_TeleportingInEffect     EffectType 1238 (0x4d6)   source 0x45b ActiveAbilityType.FearOfTheUnseen
      TitanhammerSquad_TeleportingInEffect    EffectType 1573 (0x625)   source 0x4cf ActiveAbilityType.TitanhammerSquad

⚠ QUALIFIER L'ENUM : les quatre `$$.ctor` partagent le MEME corps deduplique (que Ghidra attribue a
`APsychicStalkEffect$$.ctor`) ; seuls le `mov edx, imm32` ET la surcharge d'
`IdunBattle.Core.AbilityOrEffect$$op_Implicit` appelee les separent -- DEUX surcharges distinctes,
lues a l'octet : celle de `TeleportStrike`/`StormboyzStrike` appelle `$$set_TriggeredAbility`, celle
de `FearOfTheUnseen`/`TitanhammerSquad` appelle `$$set_ActiveAbility`.

`UntargetableEffect$$ApplyInternal` pose `UnitFlag 0x11` (Untargetable) sur la cible et
`$$RevertInternal` le retire : c'est de la BASE que vient la non-ciblabilite, pas de ces triggers.

## L'`ArraySet` natif : QUATRE `Triggered(cond, behaviour)` (decompile lu en entier)

    T1  On(0x04 UnitAfterMove)    & OwnerIsActor                    & <vslot 0x738>
            -> BaseEffect$$GetRemoveEffectBehaviour = RemoveEffect(EffectSelf)
    T2  On(0x2a PreUnitAbility)   & OwnerIsActor                    & <vslot 0x738>
            -> RemoveEffect(EffectSelf)
    T3  On(0x28 UnitFinishedTurn) & OwnerIsActor & HasTile(Owner)   & <vslot 0x738>
            -> RemoveEffect(EffectSelf)
    T4  On(0x1f PreUnitMove)      & OwnerIsActor & <vslot 0x738> & <vslot 0x748>
            -> GetMovingEffectType().HasValue
                 ? AddEffect(<ce type>, GetAbilityState(), targets: Owner, turns: Nullable<int>(1))
                 : Nothing()

Les trois vslots, RESOLUS AU RUNTIME (`resolveMethodPtr`, lecture pure -- les corps de base sont
TRIVIAUX donc dedupliques, aucune table de symboles ne les nomme ; 2026-08-01) :

| vslot | methode | corps de BASE (`ATeleportingEffect`) | surcharges du build |
|---|---|---|---|
| 0x738 | `GetAdditionalRemoveTriggers`   | `<DSLTriggers+0x40>` = conjonct NEUTRE | `FearOfTheUnseen_TeleportingInEffect` seul |
| 0x748 | `GetCustomMovingEffectCondition`| `<DSLTriggers+0x40>` = conjonct NEUTRE | `TitanhammerSquad_TeleportingInEffect` seul |
| 0x758 | `GetMovingEffectType`          | ABSTRAIT (entree nulle)                | les QUATRE derivees |

`<DSLTriggers+0x40>` est une instance de la classe que `IdunBattleLogic.Entities.DSLTriggers$$.ctor`
alloue TROIS fois (`+0x40`, `+0x70`, et `+0x48 = op_LogicalNot(<la meme>)`) : le meme conjonct neutre
que `<+0x70>`, celui qu'`$$InitializeShared` insere dans `On(0x21) & <+0x70> & OwnerIsActor`. Que ce
soit le trigger TOUJOURS-VRAI est confirme par `IdunBattle.Entities.Effects.BaseEffect$$
NeedsRefreshing`, qui traite « la condition active EST une instance de cette classe » comme
« pas de condition ». Le port le COLLAPSE (`_additional_remove_triggers` / `_custom_moving_condition`
rendent `True`), exactement comme il collapse `<+0x70>` depuis #95.

⚠ L'assignation vslot -> methode n'est PAS une hypothese : `FearOfTheUnseen_TeleportingInEffect`
surcharge UNIQUEMENT `GetAdditionalRemoveTriggers` et `TitanhammerSquad_TeleportingInEffect`
UNIQUEMENT `GetCustomMovingEffectCondition`. Le 0x738 apparait dans T1/T2/T3 (des RETRAITS -- et la
surcharge de FearOfTheUnseen est `AmountIsEqual(EffectRemainingTurns(EffectSelf), Direct(1))`, une
condition de retrait) ; le 0x748 n'apparait QUE dans T4 (la branche MOUVEMENT -- et la surcharge de
TitanhammerSquad parle de `TitanhammerSquad_TargetTile` et d'adjacence a la destination). Les deux
attributions inverses sont donc exclues.

## `IdunBattleLogic.Effects.TeleportMovingEffect` -- l'effet que T4 pose

`$$CreateHandleTriggerAbilitiesInternal` (decompile lu) = UN SEUL `Triggered` :

    On(0x04 UnitAfterMove) & OwnerIsActor -> BaseEffect$$GetRemoveEffectBehaviour

Son `$$.ctor` est appele par TROIS lambdas d'`EffectsDatabase$$InitializeEffects` -- une par
`GetMovingEffectType` non nulle : `1036 TeleportStrike_Moving` (0x40c), `1241 FearOfTheUnseen_Moving`
(0x4d9), `1574 TitanhammerSquad_Moving` (0x626). `StormboyzStrike_TeleportingInEffect`, lui,
surcharge bien `GetMovingEffectType` mais avec un corps TRIVIAL (`return 0`, deduplique avec
`Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`) : `Nullable` VIDE -> branche
`Nothing()` de T4, et aucun `StormboyzStrike_Moving` dans l'`EffectType` du build. (La case-366-r1
§7.5 ecrivait « ne surcharge PAS `GetMovingEffectType` » : la surcharge EXISTE, c'est son corps qui
est vide -- meme conclusion observable, lecture corrigee.)

## GROUND TRUTH LIVE (2026-08-01, board MC1_67 seed 777, `--no-ai`)

Cascade d'un `act move` sur `bloodIntercessor` (puis `eldarAutarch`), verbatim :

    [User_MoveUnit e=83]
      [Effect_Refresh e=115 <<TeleportStrike_Moving>>]                      # T4 (On PreUnitMove)
        ActivateEffect e=83 / ReceiveEffect e=83 Effect_SourceTriggeredAbility=1037
                                                 Effect_RemainingTurns=1
      ChangePosition e=83  Is_Last_Tile=1
      [Effect_Refresh e=106 <<TeleportStrike_TeleportingIn>>]               # T1 (On UnitAfterMove)
        LoseEffect e=83 / DeactivateEffect e=83
      [Effect_Refresh e=105 <<PathOfCommand_ExtraDmg>>]                     # InitializeActorAbilities
        ActivateEffect e=83 / ReceiveEffect e=87 / ChangeStats e=87 Attack_Modification=400
      [Effect_Refresh e=115 <<TeleportStrike_Moving>>]                      # TeleportMovingEffect
        LoseEffect e=83 / DeactivateEffect e=83

Cascade d'un `act ability` (Foehammer) sur `spaceRockfist` SANS bouger : le `LoseEffect
TeleportStrike_TeleportingIn` arrive AVANT `[Ability_Power]` -- exactement le rang ou
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` publie `On(0x2a = PreUnitAbility)` = T2.
Cascade d'un `act finish` sans rien faire d'autre : `LoseEffect` seul = T3.

CE QUE CA REFUTE : le port faisait atterrir TOUTES les unites deep-strike du joueur finissant dans
`EndTurnOperation` (boucle bespoke `land_deep_strike`). Le natif retire l'effet DES LE MOUVEMENT ou
DES LE CAST -- donc, sur toute la fin du tour, le port gardait l'unite NON-CIBLABLE, sur le
pathfinder de teleport, et surtout SANS ses passives deferrees : `eldarAutarch` n'accordait pas ses
+400 Attack a son allie pendant le reste du tour. Divergence PERMISSIVE et silencieuse.

## Tranche 2 (#448-r2c) : `1238 FearOfTheUnseen_TeleportingIn` -- le REGIME NUMERIQUE

`tyranDeathleaper`, HERO du pool rank 17, aucun montage : son ACTIVE 1115 (deja portee,
`runner/abilities/tyranids.py`) pose 1238 sur lui-meme. C'est la SEULE des quatre a surcharger le
vslot 0x738, et la surcharge n'est PAS neutre :

    FearOfTheUnseen_TeleportingInEffect$$GetAdditionalRemoveTriggers
        = AmountIsEqual( EffectRemainingTurns(EffectSelf), Direct(1) )

Comme 0x738 conditionne les QUATRE `Triggered()` (T4 compris), les quatre ne firent que lorsqu'il
reste EXACTEMENT 1 tour a l'effet -- pose a 3 (`Sum(TurnsFromRounds(1), Direct(1))`, 2 joueurs), il
traverse donc le tour du cast ET le tour adverse avant de pouvoir partir. Detail et lecture des
feuilles : docstring de `_FearOfTheUnseenRemainingIsOne`.

## Tranche 4 (#448-r2d) : `1573 TitanhammerSquad_TeleportingIn` -- le REGIME GEOMETRIQUE

`astarLysander`, HERO **hors pool** (injection catalogue + assainissement d'un trait hors-enum,
#270-d). SEULE des quatre a surcharger le vslot 0x748, et la surcharge n'est pas neutre :

    TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition
        = Contains(<Sel+0x78>, tgt) op_BitwiseOr IsAdjacentTiles(<Sel+0x78>, tgt)
          tgt = EffectTarget( EffectsFromUnitSource( EffectSource(EffectSelf@<Sel+0x38>),
                                                     0x623 = 1571 TitanhammerSquad_TargetTile ) )

Ce vslot ne conditionne QUE T4 : le marqueur `1574` n'est pose que si la DESTINATION du pas EST une
tuile marquee `1571`, ou lui est adjacente -- les trois retraits, eux, sont inchanges. Detail des
deux bras (et de leur ASYMETRIE de resolution de selecteur) : docstring de
`_TitanhammerSquadTargetTileCondition`.

## Ce qui n'est PAS porte ici, nommement

* RIEN de la famille : les QUATRE derivees sont desormais portees -- `1035` (#448-r2, bas de ce
  module), `1140` (#448-r2b), `1238` (#448-r2c) et `1573` (#448-r2d, SEULE a surcharger le vslot
  0x748) ;
* RIEN des DEUX abilities triggered qui ENTOURENT 1140 : `StormboyzStrike_MissAbility` (retire 1140
  au `On(0x1f)`, 20 % de deviation de destination, `TriggerAbility(FullThrottle)`) et
  `StormboyzStrike_FallbackAbility` (repose l'unite hors plateau au `On(0x28)`, pose
  `1179 _AlreadyUsedTile`) sont PORTEES depuis #448-r1
  (`triggers/loki/stormboyz_strike.py`). ⚠ Elles ne changent pas la lecture des triggers PROPRES de
  1140, mais elles les rendent OBSERVATIONNELLEMENT INERTES sur le geste nominal (mesure
  #448-r3-r1) -- c'est dit sur chaque classe. Seul `FullThrottle$$CreateTrigger` reste non porte ;
* `1231 TitanhammerSquad` (l'ACTIVE qui POSE 1571/1572/1573 et soigne) : son
  `IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$ExecuteBehaviour` est un
  `op_BitwiseAnd` de QUATRE behaviours, hors tranche. **Consequence NOMMEE** : cote port, PERSONNE
  ne pose `1571 TitanhammerSquad_TargetTile`, donc le vslot 0x748 rend `False` partout tant que son
  substrat n'est pas monte -- il l'est par la voie live (cast natif de 1231 par `astarLysander`
  injecte, puis re-seed du port depuis `tileMeta`), cf. `probe_448_r2d_titanhammer_squad.py` ;
* les DEUX autres jambes du `FinishUnitTurn(unit, false)` que `IdunBattle.Operations.
  EndTurnOperation$$Execute` appelle par unite possedee (`On(0x1c ArrivedAtFinalTile)` et
  `On(0x29 UnitFinishedTurnNormally)`) : le port n'emet, depuis ce site-la, que la jambe `On(0x28 = UnitFinishedTurn)`
  -- residu NOMME, cf. `operations/turnflow.py::EndTurnOperation` ;
* `UntargetableEffect$$ApplyInternal/RevertInternal` (le flag `UnitFlag 0x11`) **pour 1238 et 1573**.
  Le port ne lit pas un flag mais la PRESENCE de l'effet -- canal different, equivalent observable --
  et depuis #448-r2b c'est un DOMAINE et non une constante
  (`entities/effects/aura_selectors.py::UNTARGETABLE_EFFECT_TYPES`), parce que le flag vient de la
  BASE et vaut donc pour les QUATRE (chaine `<X>_TeleportingInEffect <- ATeleportingEffect <-
  UntargetableEffect <- BaseEffect`, `classes.tsv`). Le port n'y inscrit que ce qu'il a CONFRONTE
  SUR CE CANAL : `1035` et `1140`. **`1238` en reste DEHORS** -- residu NOMME de #448-r2c, canal
  DECISION -- et `1573` arrivera avec #448-r2d.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.tiles import Caster
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, RemoveEffect
from ....abilities.targeting import are_tiles_adjacent
from ....components import get_unit_feet
from ....state import State
from ..base import EffectTrigger, TriggerEvent
from ...spawn import initialize_deferred_actor_abilities

TELEPORT_STRIKE_TELEPORTING_IN = int(EffectType.TeleportStrike_TeleportingIn)   # 0x40b = 1035
TELEPORT_STRIKE_MOVING = int(EffectType.TeleportStrike_Moving)                 # 0x40c = 1036
STORMBOYZ_STRIKE_TELEPORTING_IN = int(EffectType.StormboyzStrike_TeleportingIn)  # 0x474 = 1140


# --- ATeleportingEffect : les TROIS triggers de RETRAIT (T1/T2/T3) --------------------------------
class ATeleportingRemoveTrigger(EffectTrigger):
    """Base COMMUNE des trois `Triggered(<cond>, RemoveEffect(EffectSelf))` d'
    `ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal`. Le port les eclate en une classe par
    `event_id` (le registre `EFFECT_TRIGGERS` indexe par event), le natif en met trois dans le meme
    `ArraySet` -- meme cardinalite, meme conditions.

    `matches` = `OwnerIsActor` & le vslot 0x738, plus le gate propre a l'evenement (`HasTile` pour
    T3). Une sous-classe d'EFFET qui surcharge `GetAdditionalRemoveTriggers` (aujourd'hui
    `FearOfTheUnseen_TeleportingInEffect` seul) redefinit `_additional_remove_triggers`."""
    effect_type = -1                                  # pose par la sous-classe d'EFFET
    event_id = -1                                     # pose par la sous-classe d'EVENEMENT

    def _additional_remove_triggers(self, state: State, ev: TriggerEvent) -> bool:
        """vslot 0x738 = `GetAdditionalRemoveTriggers`. Corps de BASE = `<DSLTriggers+0x40>`, le
        conjonct NEUTRE -> `True`."""
        return True

    def _event_gate(self, state: State, ev: TriggerEvent) -> bool:
        """Le conjonct SUPPLEMENTAIRE propre a l'evenement (seul T3 en a un : `HasTile(Owner)`)."""
        return True

    def _remove(self, state: State) -> int:
        """`BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(EffectSelf)`.

        COLLAPSE ASSUME, identique a `ChronometronExtraDamageRemove` / `UntilOfEndTurnRemove` : le
        natif retire L'INSTANCE, le port retire tous les stacks non consommes du type sur le
        porteur -- le gate << deja present >> d'`AddEffectOperation` garantit au plus UNE instance
        par unite."""
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(self.effect_type, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        return sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")

    def _after_remove(self, state: State) -> list:
        """Ce que le natif enchaine DERRIERE le retrait, cote IMPERATIF. Rien par defaut."""
        return []

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False                                   # get_OwnerIsActor
        if not self._event_gate(state, ev):
            return False
        return self._additional_remove_triggers(state, ev)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        removed = self._remove(state)
        if not removed:
            return None
        return {"effect": int(self.effect_type), "owner": int(self.owner_id), "removed": removed,
                "event": int(ev.event_id), "after": self._after_remove(state)}


class ATeleportingRemoveOnAfterMove(ATeleportingRemoveTrigger):
    """T1 -- `On(0x04 = UnitAfterMove) & OwnerIsActor & GetAdditionalRemoveTriggers()`. L'unite qui
    vient de se poser N'EST PLUS en descente : c'est CE trigger, et pas une borne de duree, qui
    termine le deep-strike dans le cas de loin le plus frequent."""
    event_id = int(EventTriggerType.UnitAfterMove)          # 4


class ATeleportingRemoveOnPreUnitAbility(ATeleportingRemoveTrigger):
    """T2 -- `On(0x2a = PreUnitAbility) & OwnerIsActor & GetAdditionalRemoveTriggers()`. Le vecteur
    est publie EN TETE d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`, donc
    AVANT l'execution : l'unite est deja posee quand son ability resout (mesure live, le
    `LoseEffect` precede `[Ability_Power]`). L'attaque NORMALE emprunte la meme operation."""
    event_id = int(EventTriggerType.PreUnitAbility)         # 0x2a = 42


class ATeleportingRemoveOnUnitFinishedTurn(ATeleportingRemoveTrigger):
    """T3 -- `On(0x28 = UnitFinishedTurn) & OwnerIsActor & HasTile(Owner) &
    GetAdditionalRemoveTriggers()`.

    `HasTile(Owner)` est LOAD-BEARING pour la famille, meme s'il est toujours vrai pour 1035 :
    `TeleportStrikeAbility$$CreateBehaviour` n'appelle PAS `RemoveUnitFromItsTiles` (l'unite
    deep-strike reste SUR le plateau, juste non-ciblable), alors que
    `StormboyzStrike_TeleportAbility$$CreateBehaviour` le fait. C'est ce gate qui permet a une
    unite HORS PLATEAU de garder son effet a travers la fin de son tour."""
    event_id = int(EventTriggerType.UnitFinishedTurn)       # 0x28 = 40

    def _event_gate(self, state: State, ev: TriggerEvent) -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$HasTile(Owner)`. Canal du port : l'empreinte
        (`get_unit_feet`, qui retombe sur la `PositionComponent` quand `feet is None`) -- la MEME
        que `RemoveUnitFromTilesOperation` vide (#438)."""
        return bool(get_unit_feet(state, int(self.owner_id)))


# --- ATeleportingEffect : le QUATRIEME trigger (T4, la pose de l'effet `*_Moving`) ----------------
class ATeleportingAddMovingOnPreMove(EffectTrigger):
    """T4 -- `On(0x1f = PreUnitMove) & OwnerIsActor & GetAdditionalRemoveTriggers() &
    GetCustomMovingEffectCondition()` -> `GetMovingEffectType().HasValue ? AddEffect(<ce type>,
    GetAbilityState(), targets: Owner, turns: Nullable<int>(1)) : Nothing()`.

    `duration_turns=1` et NON `duration_rounds=1` : la surcharge a 5 arguments d'
    `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect` range le `Nullable<int>` tel quel dans les
    options (duree DEJA en tours). MESURE LIVE : `Effect_RemainingTurns=1` -- a deux joueurs un
    `TurnsFromRounds(1)` vaudrait 2.
    `source_from_target=True` : cette surcharge passe litteralement `0` en selecteur SOURCE d'
    `AddEffectBehaviour$$.ctor` -> fallback natif « la source EST la cible ». Ici cible == owner,
    donc le resultat coincide avec le defaut ; on transcrit la FORME native (meme lecture que
    `stormboyz_strike_teleport_tree` et `burrowers_hidden_tree`)."""
    effect_type = -1                                        # pose par la sous-classe d'EFFET
    event_id = int(EventTriggerType.PreUnitMove)            # 0x1f = 31
    #: `GetMovingEffectType()` (vslot 0x758). `None` = `Nullable` VIDE -> branche `Nothing()`.
    MOVING_EFFECT_TYPE: Optional[int] = None
    MOVING_EFFECT_NAME: str = ""

    def _additional_remove_triggers(self, state: State, ev: TriggerEvent) -> bool:
        return True                                         # vslot 0x738, corps de base = neutre

    def _custom_moving_condition(self, state: State, ev: TriggerEvent) -> bool:
        """vslot 0x748 = `GetCustomMovingEffectCondition`. Corps de BASE = `<DSLTriggers+0x40>`, le
        conjonct NEUTRE -> `True`. Surcharge du build : `TitanhammerSquad_TeleportingInEffect`
        seule."""
        return True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False                                   # get_OwnerIsActor
        return (self._additional_remove_triggers(state, ev)
                and self._custom_moving_condition(state, ev))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None or self.MOVING_EFFECT_TYPE is None:
            return None                                    # branche `Nothing()`
        ectx = ExecutionContext(state=state, rng=state.rng)
        AddEffect(int(self.MOVING_EFFECT_TYPE), self.MOVING_EFFECT_NAME, Caster(),
                  duration_rounds=None, duration_turns=1,
                  source_from_target=True).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        if not placed:
            return None
        return {"effect": int(self.MOVING_EFFECT_TYPE), "owner": int(self.owner_id), "placed": True}


# --- TeleportMovingEffect : son trigger UNIQUE ----------------------------------------------------
class TeleportMovingRemoveOnAfterMove(EffectTrigger):
    """`IdunBattleLogic.Effects.TeleportMovingEffect$$CreateHandleTriggerAbilitiesInternal` = UN
    SEUL `Triggered( On(0x04 UnitAfterMove) & OwnerIsActor, RemoveEffect(EffectSelf) )`.

    Le marqueur `*_Moving` ne vit donc QUE l'espace d'un deplacement : pose par T4 avant la mutation
    de position, retire ici juste apres (mesure live : les deux `Effect_Refresh` encadrent le
    `ChangePosition` dans la MEME cascade). SANS cette entree, la pose de T4 serait PERMANENTE
    (`turns = 1` ne tombe qu'au tick de fin de tour) et `set_moved_flag` poserait `UnitFlag.
    Teleported` sur des deplacements ordinaires du tour suivant -- regression PERMISSIVE."""
    effect_type = -1                                        # pose par la sous-classe
    event_id = int(EventTriggerType.UnitAfterMove)          # 4

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)   # OwnerIsActor

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


# --- 1035 TeleportStrike_TeleportingIn : la specialisation CONFRONTEE ------------------------------
class _TeleportStrikeLandingMixin:
    """Le volet IMPERATIF que le port enchaine derriere le retrait de 1035 : les passives DEFEREES.

    Le natif ne les initialise pas a la creation de l'unite deep-strike -- `snapshot._load_*` les
    capte deja absentes -- et les pose au moment ou l'effet part (mesure live : `ActivateEffect
    PathOfCommand_ExtraDmg` suit immediatement `LoseEffect TeleportStrike_TeleportingIn` dans la
    MEME cascade de move). Le port modelise cette re-initialisation par
    `spawn.initialize_deferred_actor_abilities` -- meme foyer qu'avant #448-r2, seul le DECLENCHEUR
    change (les trois triggers natifs, au lieu d'une boucle bespoke d'`EndTurnOperation`)."""

    def _after_remove(self, state: State) -> list:
        return initialize_deferred_actor_abilities(state, int(self.owner_id))


class TeleportStrikeTeleportingInRemoveOnAfterMove(_TeleportStrikeLandingMixin,
                                                   ATeleportingRemoveOnAfterMove):
    effect_type = TELEPORT_STRIKE_TELEPORTING_IN


class TeleportStrikeTeleportingInRemoveOnPreUnitAbility(_TeleportStrikeLandingMixin,
                                                        ATeleportingRemoveOnPreUnitAbility):
    effect_type = TELEPORT_STRIKE_TELEPORTING_IN


class TeleportStrikeTeleportingInRemoveOnUnitFinishedTurn(_TeleportStrikeLandingMixin,
                                                          ATeleportingRemoveOnUnitFinishedTurn):
    effect_type = TELEPORT_STRIKE_TELEPORTING_IN


class TeleportStrikeTeleportingInAddMovingOnPreMove(ATeleportingAddMovingOnPreMove):
    """`TeleportStrike_TeleportingInEffect$$GetMovingEffectType` = `Nullable<EffectType>(0x40c)` (lu
    a l'octet : `local_res18[0] = 0x40c` puis le ctor du `Nullable`)."""
    effect_type = TELEPORT_STRIKE_TELEPORTING_IN
    MOVING_EFFECT_TYPE = TELEPORT_STRIKE_MOVING             # 0x40c = 1036
    MOVING_EFFECT_NAME = EffectType.TeleportStrike_Moving.name


class TeleportStrikeMovingRemoveOnAfterMove(TeleportMovingRemoveOnAfterMove):
    """`1036 TeleportStrike_Moving` -- la premiere des TROIS `EffectType` que la fabrique native
    construit par `TeleportMovingEffect` (la derniere, `1574 TitanhammerSquad_Moving`, arrive avec
    la tranche fille #448-r2d)."""
    effect_type = TELEPORT_STRIKE_MOVING


# --- 1238 FearOfTheUnseen_TeleportingIn : la SEULE des quatre a surcharger le vslot 0x738 ---------
FEAR_OF_THE_UNSEEN_TELEPORTING_IN = int(EffectType.FearOfTheUnseen_TeleportingIn)   # 0x4d6 = 1238
FEAR_OF_THE_UNSEEN_MOVING = int(EffectType.FearOfTheUnseen_Moving)                  # 0x4d9 = 1241


def effect_remaining_turns(state: State, owner_id: int, effect_type: int) -> int:
    """`IdunBattleLogic.Entities.DSLFormulas$$EffectRemainingTurns(selector)`, dont la formule
    construite est `IdunBattle.Entities.Formulas.EffectRemainingTurnsFormula` : son `$$Calculate`
    resout le selecteur puis SOMME `EffectComponent.Duration @+0x64` sur chaque entite-effet
    obtenue (`uVar13 = uVar13 + *(int *)(lVar6 + 100)` dans la boucle de l'enumerateur).

    `+0x64` est EXACTEMENT le champ que `IdunBattle.Entities.Components.EffectComponent$$
    RemoveOneTurn` decremente (`if (0 < Duration@+0x64) Duration -= 1`), soit le `remaining_turns`
    du port (cf. `EffectsState.on_turn_end`).

    COLLAPSE ASSUME, le meme que `ATeleportingRemoveTrigger._remove` : le selecteur natif est
    `EffectSelf` (`<DSLSelectors+0x38>`), donc UNE instance ; le port somme les instances NON
    CONSOMMEES du type sur le porteur. Le gate << deja present >> d'`AddEffectOperation` garantit au
    plus une instance par unite, donc somme == valeur unique.

    `remaining_turns is None` = effet PERMANENT (`EffectComponent.HasTurns @+0x5d` faux) : sa
    `Duration` n'est jamais posee, elle vaut 0 -- le port contribue 0, pas None."""
    if state.effects is None:
        return 0
    total = 0
    for e in state.effects.by_unit.get(int(owner_id), []):
        if e.consumed or e.effect_type != int(effect_type):
            continue
        total += 0 if e.remaining_turns is None else int(e.remaining_turns)
    return total


class _FearOfTheUnseenRemainingIsOne:
    """`IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_TeleportingInEffect$$
    GetAdditionalRemoveTriggers` -- la SEULE surcharge du vslot 0x738 dans ce build, et elle N'EST
    PAS le conjonct neutre. Decompile lu en entier :

        AmountIsEqual( EffectRemainingTurns(<DSLSelectors+0x38> = EffectSelf),
                       <DSLFormulas+0x20> = Direct(1) )

    Les deux feuilles sont lues, pas deduites :
      * `<DSLFormulas+0x20>` : `IdunBattleLogic.Entities.DSLFormulas$$.ctor` alloue ses constantes en
        file -- `+0x18` = 0, **`+0x20` = 1**, `+0x28` = 2, `+0x30` = 100, `+0x38` = -1 ;
      * `<DSLSelectors+0x38>` = `EffectSelf`, deja etabli par trois lectures independantes du depot
        (`case-366-r1-turnof-all.md`, `case-366-r1-hateful-assault-marker.md`, `wireweave_net.py`) ;
      * la SURCHARGE d'`AmountIsEqual` : le tail-call vise
        `IdunBattleLogic.Entities.DSLTriggers$$AmountIsEqual(this, amount1, amount2)` qui instancie
        `IdunBattle.Entities.Conditions.AmountIsEqualAbilityTrigger`. ⚠ Sa VOISINE IMMEDIATE porte
        le MEME nom Ghidra, la MEME signature -- et instancie `AmountIsGreaterAbilityTrigger`. La
        surcharge est tranchee par l'adresse exacte du tail-call, pas au nom.
        `AmountIsEqualAbilityTrigger$$ShouldTrigger` = `GetAmount(a1) == GetAmount(a2)`, egalite
        STRICTE d'entiers.

    ⚠ LE VSLOT 0x738 EST DANS LES **QUATRE** `Triggered()`, pas seulement dans les trois retraits :
    `ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` appelle `(**(code **)(*in_RDX +
    0x738))()` une fois par trigger, T4 compris. La condition gouverne donc AUSSI la pose du
    marqueur `1241 FearOfTheUnseen_Moving`. D'ou l'application de ce mixin aux QUATRE classes.

    CE QUE LE REGIME DONNE, mesurable : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    FearOfTheUnseenAbility$$ExecuteBehaviour` pose 1238 avec
    `Sum(TurnsFromRounds(1), Direct(1))` = **3 tours a deux joueurs** (le port folde deja ce noeud,
    `runner/abilities/tyranids.py`). L'effet ne peut donc PAS partir au tour du cast :

        tour du cast   remaining 3  -> 3 != 1 : le `FinishUnitTurn` qui suit le cast NE RETIRE RIEN
        fin de ce tour           -> 2         (`EffectsState.on_turn_end`)
        fin du tour adverse      -> 1
        tour SUIVANT du porteur  remaining 1  -> 1 == 1 : le pas / le cast / le finish RETIRE

    Un port qui collapserait ce vslot a `True` (le corps de BASE) retirerait 1238 des le
    `On(0x28 UnitFinishedTurn)` qui suit immediatement le cast : le Deathleaper ne disparaitrait
    JAMAIS, ni pour le tour adverse ni pour son propre tour suivant. Divergence PERMISSIVE et
    silencieuse -- exactement la meme signature que celle que #448-r2 a fermee sur 1035."""

    def _additional_remove_triggers(self, state: State, ev: TriggerEvent) -> bool:
        return effect_remaining_turns(
            state, int(self.owner_id), FEAR_OF_THE_UNSEEN_TELEPORTING_IN) == 1


class FearOfTheUnseenTeleportingInRemoveOnAfterMove(_FearOfTheUnseenRemainingIsOne,
                                                    ATeleportingRemoveOnAfterMove):
    effect_type = FEAR_OF_THE_UNSEEN_TELEPORTING_IN


class FearOfTheUnseenTeleportingInRemoveOnPreUnitAbility(_FearOfTheUnseenRemainingIsOne,
                                                         ATeleportingRemoveOnPreUnitAbility):
    effect_type = FEAR_OF_THE_UNSEEN_TELEPORTING_IN


class FearOfTheUnseenTeleportingInRemoveOnUnitFinishedTurn(_FearOfTheUnseenRemainingIsOne,
                                                           ATeleportingRemoveOnUnitFinishedTurn):
    effect_type = FEAR_OF_THE_UNSEEN_TELEPORTING_IN


class FearOfTheUnseenTeleportingInAddMovingOnPreMove(_FearOfTheUnseenRemainingIsOne,
                                                     ATeleportingAddMovingOnPreMove):
    """`FearOfTheUnseen_TeleportingInEffect$$GetMovingEffectType` = `Nullable<EffectType>(0x4d9)`
    (lu a l'octet : `local_res18[0] = 0x4d9` puis le ctor du `Nullable`) = `1241
    FearOfTheUnseen_Moving`. Le vslot 0x748 (`GetCustomMovingEffectCondition`) N'EST PAS surcharge
    par cette classe -- son corps de BASE `<DSLTriggers+0x40>` (conjonct neutre) s'applique, d'ou
    l'heritage tel quel de `_custom_moving_condition`."""
    effect_type = FEAR_OF_THE_UNSEEN_TELEPORTING_IN
    MOVING_EFFECT_TYPE = FEAR_OF_THE_UNSEEN_MOVING          # 0x4d9 = 1241
    MOVING_EFFECT_NAME = EffectType.FearOfTheUnseen_Moving.name


class FearOfTheUnseenMovingRemoveOnAfterMove(TeleportMovingRemoveOnAfterMove):
    """`1241 FearOfTheUnseen_Moving` -- la DEUXIEME des trois `EffectType` que
    `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` construit par
    `IdunBattleLogic.Effects.TeleportMovingEffect`. Meme trigger unique que 1036."""
    effect_type = FEAR_OF_THE_UNSEEN_MOVING


# --- 1140 StormboyzStrike_TeleportingIn : la specialisation SANS `*_Moving` (#448-r2b) -------------
# LES QUATRE MESURES QUI FONDENT CETTE TRANCHE -- aucune n'est une symetrie avec les trois soeurs :
#
#  1. `StormboyzStrike_TeleportingInEffect` SURCHARGE bien `GetMovingEffectType` (vslot 0x758,
#     ABSTRAIT dans la base) : `resolveMethodPtr` la trouve a la profondeur 0 de la chaine de
#     parents. Son corps est TRIVIAL donc DEDUPLIQUE -- il n'a aucun nom de symbole, et son entree
#     est partagee avec `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`. Les octets a
#     cette entree sont `33 c0 c3` = `xor eax, eax ; ret`. `Nullable<EffectType>` (int32 + bool,
#     8 octets) revient dans RAX sur x64 Windows -> `hasValue = 0` = **Nullable VIDE** -> T4 prend
#     la branche `Nothing()`. Les trois soeurs, elles, ont un corps NOMME qui construit le
#     `Nullable` par son ctor (0x40c / 0x4d9 / 0x626).
#  2. `IdunBattle.Entities.Enum.EffectType` du build ne contient QUE TROIS `*_Moving` (1036, 1241,
#     1574) -- aucun `StormboyzStrike_Moving` (table VERSIONNEE `frida/enums.tsv`, 629 valeurs).
#  3. `IdunBattleLogic.Effects.TeleportMovingEffect$$.ctor` a EXACTEMENT TROIS appelants, tous des
#     lambdas d'`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` -- une par `*_Moving`.
#  4. Les DEUX autres vslots ne sont PAS surcharges (`resolveMethodPtr` : `GetAdditionalRemoveTriggers`
#     et `GetCustomMovingEffectCondition` ne resolvent qu'a la profondeur 1, sur le corps de BASE
#     partage avec `WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateActiveCondition`, qui
#     rend `<DSLTriggers+0x40>` = le conjonct NEUTRE). Les deux collapses de la base valent donc.
#     ⚠ Ce point PORTE, depuis #448-r2c : le vslot 0x738 est appele dans les **QUATRE** `Triggered()`,
#     T4 COMPRIS (`ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` fait
#     `(**(code **)(*in_RDX + 0x738))()` une fois par trigger). Chez `FearOfTheUnseen`, qui le
#     surcharge, il gouverne donc AUSSI la pose du marqueur `*_Moving`. Pour 1140, non surcharge, il
#     rend `True` partout -- la condition de T4 se reduit a `OwnerIsActor`, et la branche prise
#     depend du SEUL `GetMovingEffectType`, donc `Nothing()`. La rectification ne change RIEN ici,
#     et c'est verifie plutot que suppose (garde `test_T4_declares_no_moving_effect_and_poses_nothing` :
#     T4 MATCHE et ne pose rien -- la distinction entre << condition fausse >> et << condition vraie,
#     behaviour `Nothing()` >>).
#
# PAS DE `_TeleportStrikeLandingMixin` ICI, et c'est une lecture, pas un oubli : le volet
# « passives DEFERREES » est une couche IMPERATIVE que le port accroche au retrait de 1035 parce que
# la cascade live de l'atterrissage TeleportStrike les montre dans le meme bloc (residu NOMME de la
# tranche 1 -- `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` n'a que des xrefs
# DATA). Le regime de 1140 est l'inverse : c'est `On(0x21 = AbilityInit)` LUI-MEME qui pose l'effet
# (`StormboyzStrike_TeleportAbility$$CreateTrigger`), donc les owner-effects du porteur sont DEJA
# initialises quand 1140 arrive -- `snapshot.load_state` ne les diffère que sous 1035. MESURE :
# volet E1 de `probe_448_r2b_stormboyz_teleporting_in.py` (le porteur greffe arrive sous 1140 AVEC
# ses owner-effects passifs).
class StormboyzStrikeTeleportingInRemoveOnAfterMove(ATeleportingRemoveOnAfterMove):
    """T1 pour 1140. ⚠ REGIME : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    StormboyzStrike_MissAbility` (PORTEE depuis #448-r1) ecoute le MEME pas en amont
    (`On(0x1f = PreUnitMove)`) et fait `RemoveEffect(Caster, 0x474)` INCONDITIONNELLEMENT (le
    `RemoveEffect` est HORS du `If(Maybe(chance))`) -- c'est donc ELLE qui retire 1140 des le
    pre-move, DES DEUX COTES, et T1 n'a plus rien a retirer quand le vecteur `On(0x04)` s'ouvre.

    ⚠ T1 EST DONC OBSERVATIONNELLEMENT INERTE SUR CE REGIME, et c'est mesure : vider
    `EFFECT_TRIGGERS[1140]` laissait la garde live ENTIEREMENT VERTE (#448-r3-r1). Il reste porte
    parce qu'il est dans l'`ArraySet` natif de la base -- pas parce qu'un geste l'exerce."""
    effect_type = STORMBOYZ_STRIKE_TELEPORTING_IN


class StormboyzStrikeTeleportingInRemoveOnPreUnitAbility(ATeleportingRemoveOnPreUnitAbility):
    """T2 pour 1140. NON CONFRONTE LIVE : sous 1140 l'unite est HORS PLATEAU
    (`StormboyzStrike_TeleportAbility$$CreateBehaviour` appelle `RemoveUnitFromItsTiles`), donc elle
    n'a ni portee ni ligne de vue et aucun cast n'est legal -- `abilityTargets` rend un `fromHere`
    VIDE (mesure : volet T2-VIDE du probe). Le trigger est porte parce qu'il est DANS l'`ArraySet`
    natif de la classe de base, pas parce qu'un geste l'exerce."""
    effect_type = STORMBOYZ_STRIKE_TELEPORTING_IN


class StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn(ATeleportingRemoveOnUnitFinishedTurn):
    """T3 pour 1140 -- LE contre-bras vivant du gate `HasTile(Owner)`, qu'aucune autre tranche de la
    famille ne peut exercer : 1140 est le SEUL des quatre dont le poseur retire l'unite du plateau.

    Sous 1140 `HasTile(Owner)` est FAUX et T3 NE FIRE PAS. Ce qui le fait finalement mordre est un
    TIERS : `IdunBattleLogic.Abilities.Triggered.Loki.StormboyzStrike_FallbackAbility` (PORTEE
    depuis #448-r1), qui ecoute le MEME `On(0x28)` sous `HasEffect(Owner, 0x474)` et REPOSE l'unite
    par un `MoveUnitBehaviour` -- apres quoi `HasTile` devient vrai et T3 retire.

    L'ORDRE vient du dispatch : `evaluate_trigger_operation` concatene `collect_triggered_abilities`
    PUIS `collect_effect_triggers`, donc le Fallback (ABILITY) est evalue AVANT T3 (EFFET) et le
    gate est deja VRAI quand T3 passe. ⚠ Il decide QUI retire, pas SI l'effet part : le
    `MoveUnitBehaviour` du Fallback re-emet `On(0x1f)`, donc le `_MissAbility` retirerait 1140 de
    toute facon. L'etat final est le meme dans les deux ordres -- ne pas lire cet enchainement
    comme une garde de l'observable.

    ⚠ ET LE BRAS FAUX N'EST PLUS ATTEIGNABLE PAR UN GESTE : le Fallback repose toujours l'unite
    avant que T3 soit evalue, et son `MoveUnitBehaviour` re-emet `On(0x1f)`, donc le `_MissAbility`
    retire 1140 par un canal REDONDANT. Les deux bras du gate restent gardes par les volets
    T3-GATE et T3-POSITIF de `probe_448_r2b_stormboyz_teleporting_in.py`, qui RETIRENT le Fallback
    du registre pour l'isoler (#448-r3-r1)."""
    effect_type = STORMBOYZ_STRIKE_TELEPORTING_IN


class StormboyzStrikeTeleportingInAddMovingOnPreMove(ATeleportingAddMovingOnPreMove):
    """T4 pour 1140 : `MOVING_EFFECT_TYPE` reste `None` (herite de la base) = `Nullable` VIDE =
    branche `Nothing()`. C'est le SEUL des quatre dans ce cas, et c'est MESURE (les quatre points
    ci-dessus), pas deduit d'une absence de symbole."""
    effect_type = STORMBOYZ_STRIKE_TELEPORTING_IN


# --- 1573 TitanhammerSquad_TeleportingIn : la SEULE des quatre a surcharger le vslot 0x748 --------
TITANHAMMER_SQUAD_TARGET_TILE = int(EffectType.TitanhammerSquad_TargetTile)      # 0x623 = 1571
TITANHAMMER_SQUAD_TELEPORTING_IN = int(EffectType.TitanhammerSquad_TeleportingIn)  # 0x625 = 1573
TITANHAMMER_SQUAD_MOVING = int(EffectType.TitanhammerSquad_Moving)              # 0x626 = 1574


def _effect_source(state: State, carrier_id: int, effect_type: int) -> Optional[int]:
    """`IdunBattleLogic.Entities.DSLSelectors$$EffectSource(<selecteur d'effets>)` ->
    `IdunBattle.Entities.Selectors.EffectSourceSelector$$Select`, applique a l'instance PORTEE.

    Le natif resout son selecteur source (ici `EffectSelf` = `<DSLSelectors+0x38>`), prend l'
    `EffectComponent` de chaque entite-effet rendue et garde `SourceUnit @+0x10` quand il est non nul
    (`if (*(int *)(lVar8 + 0x10) != 0)`). Cote port, `BaseEffect.source` EST ce champ.

    COLLAPSE ASSUME (le meme que `_remove`) : le port n'a pas de handle d'INSTANCE dans un
    `EffectTrigger` -- il retrouve l'instance par (porteur, type) et rend la premiere non consommee.
    Le gate << deja present >> d'`AddEffectOperation` garantit au plus une instance par unite.
    Jumeau exact dans `triggers/loki/ghost_revive.py::_effect_source` (meme noeud natif, autre
    porteur : une TUILE) -- deux lecteurs, un seul champ."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in (eff.by_unit.get(int(carrier_id)) or []):
        if e.effect_type == int(effect_type) and not e.consumed:
            return None if e.source is None else int(e.source)
    return None


class _TitanhammerSquadTargetTileCondition:
    """vslot 0x748 = `IdunBattle.Entities.Effects.Loki.TitanhammerSquad_TeleportingInEffect$$
    GetCustomMovingEffectCondition` -- **la SEULE surcharge du build** (les trois soeurs gardent le
    conjonct NEUTRE `<DSLTriggers+0x40>`). Arbre natif lu en entier :

        tgt = EffectTarget( EffectsFromUnitSource( EffectSource(EffectSelf@<Sel+0x38>),
                                                   0x623 = 1571 TitanhammerSquad_TargetTile ) )
        Contains(<Sel+0x78>, tgt)  op_BitwiseOr  IsAdjacentTiles(<Sel+0x78>, tgt)

    Autrement dit : le marqueur `1574 *_Moving` n'est pose que si la DESTINATION du pas EST une tuile
    marquee `1571`, ou lui est ADJACENTE.

    `<DSLSelectors+0x78>` = **TargetTiles** (`AbilityEntities+0x190`) -- lecture etablie deux fois
    independamment : `runner/abilities/admec.py` (<< `factory+0x178 Target` = `+0x60`,
    `factory+0x190 TargetTiles` = `+0x78` >>) et le port live-confirme d'`HatefulAssaultAbility$$
    CreateTrigger` (case-366-r1). Sur `On(0x1f = PreUnitMove)`,
    `IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers` remplit `casterTiles` (7e arg)
    ET `targetTiles` (10e) avec la MEME liste `position` : ce slot porte donc la tuile d'ARRIVEE,
    que le port threade dans `TriggerEvent.dest_tile`.

    LES DEUX BRAS n'invoquent PAS leurs selecteurs de la meme facon (decompile lu) :

    * `IdunBattle.Entities.Triggers.XContainsYTrigger$$ShouldTrigger` resout X (`+0x10` = les tuiles
      de destination) par le slot d'interface **0** (liste d'entites) et Y (`+0x18` = `tgt`) par le
      slot **1**, qui rend **UNE SEULE** entite (meme slot que celui par lequel
      `EffectsFromUnitSourceSelector$$Select` reduit sa source a un `entity` unique) ; il compare
      ensuite les `Id`. Le bras `Contains` ne teste donc QUE LA PREMIERE tuile marquee.
    * `IdunBattle.Entities.Triggers.IsAdjacentTilesTrigger$$ShouldTrigger` resout SES DEUX selecteurs
      (`+0x18`, `+0x20`) par le slot **10** (liste de TUILES) et fait une double boucle : vrai des
      qu'UNE paire est adjacente (`<query>` slot 0x60). Ce bras-la balaye TOUTES les tuiles marquees.

    `<query>` slot 0x60 = `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` ->
    `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`, dont la surcharge scalaire vaut
    `(|dElev| < 2) & (tile1 == tile2 || ConnectivityComponent$$IsNeighbour(tile1, tile2))`. Ce bras
    passe donc par le foyer mirror `abilities/targeting.py::are_tiles_adjacent` (#433-r1) : le
    voisinage nu de `board.neighbours` qu'il utilisait avant ratait les DEUX termes foldes -- le
    court-circuit d'IDENTITE (une destination QUI EST une marque satisfait aussi ce bras, pas
    seulement `Contains`) et la porte d'ELEVATION (une voisine a `|dElev| >= 2` n'est PAS adjacente).

    LE RESIDU D'ORDRE de #448-r2d TOMBE AVEC #433-r1, et c'est une CONSEQUENCE du court-circuit, pas
    une coincidence : puisque `AreTilesAdjacent(t, t)` est VRAI, tout `dest` egal a une marque -- la
    premiere ou une autre -- satisfait deja le bras `IsAdjacentTiles`. Le bras `Contains` est donc
    SUBSUME par lui **cote natif aussi** (`Contains(X, marked[0])` implique
    `IsAdjacentTiles(X, marked)`), et la disjonction entiere se reduit a
    `EXISTE j : AreTilesAdjacent(dest, marked[j])`. Le port garde le bras `Contains` en tete par
    fidelite structurelle (mirror 1:1 de l'`op_BitwiseOr`), mais il ne peut plus rien decider seul :
    l'ordre de `EffectsState.by_unit` (qui n'est PAS l'ordre de creation des entites-effet du natif)
    est devenu sans effet sur le verdict, a toute cardinalite de `marked`. Ce que
    `TitanhammerSquadAbility$$ExecuteBehaviour` ne pose qu'UNE marque
    (`AddEffect(0x623, ..., targets: <Sel+0x60> = Target)`, mesure `marked_tiles` du probe) n'est donc
    plus ce qui protege le port -- c'est desormais vrai independamment."""

    def _target_tiles(self, state: State) -> list:
        """`EffectTarget( EffectsFromUnitSource( EffectSource(EffectSelf), 1571 ) )`.

        `IdunBattle.Entities.EntityExtensions$$GetEffectsBySourceUnit(entity, state, effectType)`
        balaye les entites-effet de l'etat et garde celles dont l'`EffectComponent` a
        `SourceUnit @+0x10 == entity.Id` ET `Type @+0x58 == effectType` ;
        `IdunBattle.Entities.Selectors.EffectTargetSelector$$Select` en rend ensuite les CIBLES
        (la liste `EffectComponent+0x48`).

        Cote port ces deux etages se collapsent en un seul balayage de `EffectsState.by_unit`, dont
        la CLE **EST** la cible de l'effet (`_load_tile_effects` : << cle = l'ENTITE-TUILE >>) --
        meme collapse que `abilities/behaviours/context.py::_effects_from_source`. Que `1571` vive
        bien sur des TUILES est lu au decompile :
        `IdunBattle.Entities.Pathfinding.TitanhammerSquadPathfinder$$IsValidTitanhammerSquadTargetTile`
        fait `GetOwnedEffect(tile, state, 0x623)` puis `GetEffectSourceUnit(...)`."""
        eff = getattr(state, "effects", None)
        src = _effect_source(state, int(self.owner_id), int(self.effect_type))
        if eff is None or src is None:
            return []
        out: list = []
        for carrier, effs in eff.by_unit.items():
            for e in (effs or []):
                if e.consumed or e.effect_type != TITANHAMMER_SQUAD_TARGET_TILE:
                    continue
                if e.source is not None and int(e.source) == int(src):
                    out.append(int(carrier))
                    break
        return out

    def _custom_moving_condition(self, state: State, ev: TriggerEvent) -> bool:
        board = getattr(state, "board", None)
        if state.effects is None or board is None:
            return False
        dest = getattr(ev, "dest_tile", None)
        if dest is None:
            # `<Sel+0x78>` NON THREADE sur cet evenement -> le natif evaluerait `Contains`/
            # `IsAdjacentTiles` sur une liste VIDE, donc FAUX des deux cotes. Seul
            # `MoveUnitOperation.execute` renseigne ce canal, et T4 n'ecoute que `On(0x1f)`.
            return False
        dest_id = board.id_at(int(dest[0]), int(dest[1]))
        if dest_id is None:
            return False
        marked = self._target_tiles(state)
        if not marked:
            return False
        if int(marked[0]) == int(dest_id):            # Contains(X, Y) -- Y reduite a UNE entite
            return True
        # `IsAdjacentTiles` : double boucle sur les DEUX listes, chaque paire tranchee par le slot
        # 0x60 du query = `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` ->
        # `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`. C'est le foyer mirror
        # `abilities/targeting.py::are_tiles_adjacent` qu'il faut appeler, PAS `board.neighbours` :
        # la primitive native folde DEUX termes que le voisinage nu n'a pas -- le COURT-CIRCUIT
        # D'IDENTITE (`tile1 == tile2` -> vrai sans consulter la connectivite) et la porte
        # d'ELEVATION (`|dElev| < 2`). Cf. `docs/rl/case-433-r1-identite-adjacence.md`.
        return any(are_tiles_adjacent(board, int(dest_id), int(t)) for t in marked)


class TitanhammerSquadTeleportingInRemoveOnAfterMove(ATeleportingRemoveOnAfterMove):
    effect_type = TITANHAMMER_SQUAD_TELEPORTING_IN


class TitanhammerSquadTeleportingInRemoveOnPreUnitAbility(ATeleportingRemoveOnPreUnitAbility):
    effect_type = TITANHAMMER_SQUAD_TELEPORTING_IN


class TitanhammerSquadTeleportingInRemoveOnUnitFinishedTurn(ATeleportingRemoveOnUnitFinishedTurn):
    effect_type = TITANHAMMER_SQUAD_TELEPORTING_IN


class TitanhammerSquadTeleportingInAddMovingOnPreMove(_TitanhammerSquadTargetTileCondition,
                                                      ATeleportingAddMovingOnPreMove):
    """`TitanhammerSquad_TeleportingInEffect$$GetMovingEffectType` = `Nullable<EffectType>(0x626)`
    (lu a l'octet : `local_res18[0] = 0x626` puis le ctor du `Nullable`), et vslot 0x748 surcharge
    (cf. `_TitanhammerSquadTargetTileCondition`)."""
    effect_type = TITANHAMMER_SQUAD_TELEPORTING_IN
    MOVING_EFFECT_TYPE = TITANHAMMER_SQUAD_MOVING                 # 0x626 = 1574
    MOVING_EFFECT_NAME = EffectType.TitanhammerSquad_Moving.name


class TitanhammerSquadMovingRemoveOnAfterMove(TeleportMovingRemoveOnAfterMove):
    """`1574 TitanhammerSquad_Moving` -- la TROISIEME et derniere `EffectType` que les lambdas d'
    `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` construisent par
    `IdunBattleLogic.Effects.TeleportMovingEffect`."""
    effect_type = TITANHAMMER_SQUAD_MOVING
