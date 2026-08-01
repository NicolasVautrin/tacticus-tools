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

## Ce qui n'est PAS porte ici, nommement

* les effets 1140 / 1573 (deux des trois soeurs) : tranches filles #448-r2b/d. Les classes de
  BASE ci-dessous sont ecrites pour elles (un `effect_type`, un `MOVING_EFFECT_TYPE`, et pour
  TitanhammerSquad une surcharge de `_custom_moving_condition`) -- mais AUCUNE n'est inscrite au
  registre tant qu'elle n'est pas CONFRONTEE ;
* `UntargetableEffect$$ApplyInternal` pour 1238 : `ai/state_bridge.py::_is_untargetable` ne lit que
  `1035`, alors que la non-ciblabilite vient de la BASE `UntargetableEffect` et vaut donc pour les
  QUATRE (chaine `FearOfTheUnseen_TeleportingInEffect <- ATeleportingEffect <- UntargetableEffect
  <- BaseEffect`, `classes.tsv`). RESIDU NOMME, canal DECISION, hors de cette tranche (qui ne touche
  que les triggers) ;
* les DEUX autres jambes du `FinishUnitTurn(unit, false)` que `IdunBattle.Operations.
  EndTurnOperation$$Execute` appelle par unite possedee (`On(0x1c ArrivedAtFinalTile)` et
  `On(0x29 UnitFinishedTurnNormally)`) : le port n'emet, depuis ce site-la, que la jambe `On(0x28 = UnitFinishedTurn)`
  -- residu NOMME, cf. `operations/turnflow.py::EndTurnOperation` ;
* `UntargetableEffect$$ApplyInternal/RevertInternal` (le flag `UnitFlag 0x11`) : le port lit la
  non-ciblabilite depuis la PRESENCE de l'effet (`ai/state_bridge.py::_is_untargetable`,
  `entities/effects/aura_selectors.py`), pas depuis un flag -- equivalent observable, canal
  different, inchange par cette tranche.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors import Caster
from ....abilities.behaviours import AddEffect, RemoveEffect, entities_from_state
from ....components import get_unit_feet
from ....state import State
from ..base import EffectTrigger, TriggerEvent

TELEPORT_STRIKE_TELEPORTING_IN = int(EffectType.TeleportStrike_TeleportingIn)   # 0x40b = 1035
TELEPORT_STRIKE_MOVING = int(EffectType.TeleportStrike_Moving)                 # 0x40c = 1036


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
        from ...spawn import initialize_deferred_actor_abilities
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
