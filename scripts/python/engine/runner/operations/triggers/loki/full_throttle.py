"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FullThrottleAbility`
(`TriggeredAbilityType` 0x46e = 1134 `FullThrottle`, passif d'`orksNpc6Stormboy` << Stormboy >>)
-- QUATRIEME et derniere piece nommee par `#448-r1` §6.

i2 (`StormboyzStrike`) : « This fly-in counts as a movement for <i>Full Throttle</i>. »
Le kit Ork : le jetpack peut lacher quand on pousse les gaz.

⚠ QUALIFIER L'ENUM : **1134 = `TriggeredAbilityType.FullThrottle`**. Un id voisin porte d'autres
noms dans d'autres tables -- ne jamais resoudre 1134 ailleurs que dans `TriggeredAbilityType`.

RE (decompile ghidra, build `rnca9r7q6c`)
-----------------------------------------
`...FullThrottleAbility$$CreateTrigger` :

    On(0x24 = UnitPositionChanged_1)                 # EventTriggerType, litteral LU
  & get_OwnerIsActor
  & AmountIsEqualOrGreater( MovementSteps(),
                            Direct(GetNumberConstant(0x51 = 'movement')) )

⚠ **LE SEUIL EFFECTIF EST 2 PAS, PAS 3** -- et l'ecart d'UN est structurel, lu au site d'appel de
`IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` dans
`IdunBattle.Operations.MoveUnitOperation$$Execute` :

    movementSteps = IsLikeFlying ? <distance(path.First(), path.Last())> : **path.Count**

`path[0]` est la tuile de DEPART (la boucle `IdunBattle.Operations.MoveUnitOperation$$AddMoveEvent`
demarre a `i = 1`), et le helper que le jeu utilise ailleurs pour compter les tuiles PARCOURUES,
`IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(path)`, rend explicitement `path.Count - 1`.
Un marcheur qui franchit 2 hexes porte donc `movementSteps = 3` et PASSE le gate `>= 3`.
Cf. `runner/operations/movement.py::_movement_steps` (les deux branches y sont mirrorees).

`...FullThrottleAbility$$CreateBehaviour` :

    If( Maybe( GetNumberConstant(0x2a = 'chance') ),
        Kill( Caster@DSLSelectors+0x48, Caster@DSLSelectors+0x48, ForDirectKill ),
        null )

Les DEUX constantes sont dans le gameconfig et resolvent sans ambiguite :
`FullThrottle.constants = {movement: 3, chance: 30}` -- donc `0x51 = 'movement'` et
`0x2a = 'chance'` (ce dernier deja etabli par tout le reste du port).
`KillUnitBehaviourOptions$$ForDirectKill` a pour corps entier `return 0x10001;`.

CE QUI EST PORTE, ET CE QUI NE L'EST PAS
-----------------------------------------
**PORTE : le `CreateBehaviour`**, sous la forme d'une entree de `TRIGGERED_ABILITY_BEHAVIOURS`
(le registre du noeud `TriggerAbility`). C'est EXACTEMENT la face que
`...StormboyzStrike_MissAbility$$CreateBehaviour` exerce : son dernier terme est
`TriggerAbility(Caster, 0x46e, ...)`, et `IdunBattle.Operations.
TriggerTriggeredAbilityOperation$$TriggerAbility` -- lu au decompile -- va DIRECTEMENT au slot
`Execute` de l'ability declenchee (avec `triggerType = 0x20 = Custom`) **sans jamais evaluer son
`ShouldTrigger`**. Le `CreateTrigger` n'est donc pas sur ce chemin, et le declenchement par le
fly-in est INCONDITIONNEL cote gate de mouvement.

**PORTE AUSSI, depuis #448-r1-r1 : le `CreateTrigger`** (le passif autonome). Le verrou qui l'avait
fait classer RESIDU -- « la formule `IdunBattleLogic.Entities.DSLFormulas$$MovementSteps()` alloue
une classe dont aucun nom n'apparait dans les tables, il faudrait lire son slot `Calculate` au
RUNTIME » -- **n'existait pas** : la recherche avait porte sur le mauvais namespace. La classe est
`IdunBattle.DSL.MovementStepFormula` (namespace `IdunBattle.DSL`, et non
`IdunBattle.Entities.Formulas` ou vivent les deux `TilesMoved*TurnFormula` de comparaison), elle est
dans `classes.tsv`, et son `Calculate` est nomme dans les DEUX tables. Detail et contre-epreuves :
`docs/rl/case-448-r1-r1-full-throttle-gate.md`.

    IdunBattle.DSL.MovementStepFormula$$Calculate = Nullable<int>.GetValueOrDefault(entities+0x11c)

et `AbilityEntities+0x11c` se nomme **`movementSteps`** -- verbatim dans la signature du ctor a 33
parametres d'`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`. Ce n'est donc PAS « les tuiles
parcourues ce tour » (l'invention que la doctrine proscrivait, et qui se serait revelee FAUSSE) :
c'est une donnee de l'EVENEMENT, renseignee par le seul
`IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers`.

⇒ Rayon de souffle, chiffre : `orksNpc6Stormboy` est le SEUL porteur de `FullThrottle`
(`unit_map.py find --ability FullThrottle` -> 1 unite, bucket npc, voie `passive`) -- le port n'a
donc aucun effet sur une unite du pool tant qu'on ne greffe pas.

CONFRONTABILITE : celle, deja acquise, du kit `StormboyzStrike` -- greffe du passif sur une unite du
pool (`catalog_inject.graft_passive_ability`, `docs/rl/case-92-catalog-injection.md` §5bis).
Condition verifiee : ni le trigger ni le behaviour ne lisent stat, trait ou arme du caster.

NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : `BaseTriggeredAbility`, hors `ABILITY_CLASSES`.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.lifecycle import Kill, TRIGGERED_ABILITY_BEHAVIOURS
from .....entities.behaviours import If
from .....entities.selectors.tiles import Caster
from .....entities.triggers import MaybeTrigger
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

FULL_THROTTLE_ID = "FullThrottle"
FULL_THROTTLE = int(TriggeredAbilityType.FullThrottle)                   # 0x46e = 1134


def full_throttle_tree(chance: int, rng) -> If:
    """`...FullThrottleAbility$$CreateBehaviour`, MIRROR 1:1 :

        If( Maybe(GetNumberConstant(0x2a = 'chance')), Kill(Caster, Caster, ForDirectKill), null )

    `Maybe` a UN argument = le PREDICAT `IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger`
    (`NextBool(chance)`, UN tirage), pas le noeud EFFET homonyme. Son PRNG est un CHAMP de
    l'instance cote natif -> passe au constructeur ici aussi.

    `Kill(Caster, Caster, ForDirectKill)` : le tueur EST la victime (les deux selecteurs sont le
    MEME slot `DSLSelectors+0x48`). Branche FAUSSE nulle -> resultat vide, aucune mutation."""
    return If(MaybeTrigger(rng, Const(int(chance))), Kill(Caster(), Caster()), None)


def execute_full_throttle(state: State, owner_id: int,
                          entities=None, ectx_appelant=None) -> Optional[dict]:
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[1134]` -- le callable que le noeud DSL
    `TriggerAbility` invoque, unite par unite, pour un declenchement DIRECT.

    `chance` vient du gameconfig (`FullThrottle.constants.chance` = 30) ; absente -> `0`, et
    `next_bool(0)` est toujours faux : le port ne tue alors personne plutot que d'inventer un taux.
    C'est la MEME doctrine que le refus de dispatcher `BattleFatigue` (dont la config, elle,
    n'existe PAS du tout -- ici elle existe, d'ou l'entree).

    ⚠ `entities` / `ectx_appelant` sont les DEUX parametres que #513 a ajoutes au contrat du
    registre (le noeud natif reconstitue un `AbilityEntities` depuis ses quatre selecteurs et le
    passe a l'operation). CE call-site les IGNORE, et c'est le comportement STRICTEMENT d'avant :
    il rebatit `entities_from_state(state, owner_id)` (donc `Caster` = l'unite DECLENCHEE) et son
    propre `ExecutionContext`. Sur `...StormboyzStrike_MissAbility`, seul call-site porte, le
    selecteur `caster` du noeud est le caster du Miss, qui n'est pas forcement l'unite declenchee :
    le port choisirait donc une AUTRE unite s'il consommait `entities`. Basculer sur les entities du
    noeud changerait la semantique de FullThrottle -- residu NOMME **#513-r5**, hors de la tranche
    qui l'a rendu visible. Les nommer ici plutot que d'avaler un `*args` muet est ce qui rend le
    residu greppable."""
    if state is None or owner_id is None:
        return None
    import gameconfig as GC
    chance = int((GC.ability(FULL_THROTTLE_ID) or {}).get("constants", {}).get("chance") or 0)
    ectx = ExecutionContext(state=state, rng=state.rng)
    full_throttle_tree(chance, state.rng).execute(
        entities_from_state(state, int(owner_id)), ectx)
    killed = [i for n, p in ectx.emitted if n == "Kill" for i in (p.get("killed") or [])]
    return {"ability": FULL_THROTTLE_ID, "unit": int(owner_id), "chance": chance,
            "killed": killed}


class FullThrottlePassiveAbility(TriggeredAbility):
    """`...FullThrottleAbility$$CreateTrigger` + `$$CreateBehaviour` -- le PASSIF AUTONOME.

        On(0x24 = UnitPositionChanged_1, true)
          & get_OwnerIsActor
          & AmountIsEqualOrGreater( MovementSteps(), Direct(GetNumberConstant(0x51='movement')) )
        -> If( Maybe(chance), Kill(Caster, Caster, ForDirectKill), null )

    C'est la SECONDE face de 1134, distincte du declenchement DIRECT par
    `...StormboyzStrike_MissAbility` (nœud `TriggerAbility`, qui va au slot `Execute` sans jamais
    evaluer ce `ShouldTrigger` -- cf. l'en-tete). Les deux partagent le MEME behaviour, et c'est
    voulu : `execute_full_throttle` est le foyer unique.

    ⚠ **LE TIRAGE PRNG N'A LIEU QUE SI LE GATE PASSE.** `Maybe` est evalue DANS le behaviour, apres
    `ShouldTrigger` -- inscrire ce trigger CHANGE donc le nombre de `NextBool` consommes sur une
    bataille, exactement comme le gate manquant de #448-r1 DECALAIT la sequence. Un gate trop
    permissif ne se verrait pas seulement sur les morts : il decalerait tout l'aleatoire aval.

    `matches` ne teste PAS `alive` : le gate « owner vivant » est applique en amont par le
    collecteur (`CanGetAbilityTrigger`), et `fire_on_death` reste a False -- une unite morte
    pendant son propre mouvement (crush, overwatch) ne pousse plus les gaz."""
    event_id = int(EventTriggerType.UnitPositionChanged_1)     # On(0x24), litteral LU
    TRIGGERED_ABILITY_ID = FULL_THROTTLE

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` = `AreEqual(<Sel+0x30 = Owner>, <Sel+0x40 = Actor>)`. Sur ce vecteur le
        # natif met le MOVER en actor/caster/target (`AbilityEntities(unit, unit, unit, ...)`).
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        # `AmountIsEqualOrGreater(MovementSteps(), Direct(movement))`. `movement_steps is None` = le
        # `Nullable` VIDE du natif -> `GetValueOrDefault()` rend **0**, et le gate echoue. On ne se
        # tait donc PAS (pas de tri-etat ici) : rendre False EST la reponse native.
        steps = 0 if ev.movement_steps is None else int(ev.movement_steps)
        import gameconfig as GC
        movement = (GC.ability(FULL_THROTTLE_ID) or {}).get("constants", {}).get("movement")
        if movement is None:
            return False        # constante absente -> aucun seuil connu : on ne tue personne
        return steps >= int(movement)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return execute_full_throttle(state, self.owner_id)


# Inscription au registre du noeud `TriggerAbility` (import-time, comme les autres modules
# d'abilities). Declencheurs portes : `...StormboyzStrike_MissAbility$$CreateBehaviour` (direct) et
# `FullThrottlePassiveAbility` ci-dessus (autonome, via `ABILITY_TRIGGERS["FullThrottle"]`).
TRIGGERED_ABILITY_BEHAVIOURS[FULL_THROTTLE] = execute_full_throttle
