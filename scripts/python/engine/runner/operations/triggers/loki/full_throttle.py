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

    On(0x24)                                         # EventTriggerType, litteral LU
  & get_OwnerIsActor
  & AmountIsEqualOrGreater( MovementSteps(),
                            Direct(GetNumberConstant(0x51 = 'movement')) )

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

**NON PORTE : le `CreateTrigger`** (le passif autonome, « bouger de >= 3 hexes »). RESIDU NOMME,
avec sa cause exacte : la formule `IdunBattleLogic.Entities.DSLFormulas$$MovementSteps()` alloue une
classe dont le `.ctor` ne prend QU'UN argument (un champ mis a `0`) et dont **aucun nom n'apparait
dans les tables de symboles** -- ce n'est ni `TilesMovedThisTurnFormula` ni
`TilesMovedLastTurnFormula` (leurs deux `DSLFormulas$$TilesMoved*Turn` allouent des classes
DIFFERENTES, avec un ctor a DEUX arguments dont un selecteur d'unite). La seule xref de son cache de
classe est `MovementSteps` elle-meme, donc rien ne la discrimine offline : il faudrait lire son slot
`Calculate` au RUNTIME (`resolveMethodPtr`, cf. `reference_il2cpp_methodptr_uninit_class`). Porter
le gate en SUPPOSANT que c'est « les tuiles parcourues ce tour » serait exactement l'invention que
la doctrine proscrit -- et le supposer FAUX (gate toujours vrai) tuerait 30 % des Stormboyz a chaque
pas. On ne l'inscrit donc PAS dans `ABILITY_TRIGGERS` : le passif autonome reste inerte, et le port
le DIT au lieu de le deviner.
⇒ Consequence, chiffree : `orksNpc6Stormboy` est le SEUL porteur de `FullThrottle`
(`unit_map.py find --ability FullThrottle` -> 1 unite, bucket npc, voie `passive`) -- le residu n'a
donc AUCUN rayon de souffle sur une unite du pool.

CONFRONTABILITE : celle, deja acquise, du kit `StormboyzStrike` -- greffe du passif sur une unite du
pool (`catalog_inject.graft_passive_ability`, `docs/rl/case-92-catalog-injection.md` §5bis).
Condition verifiee : ni le trigger ni le behaviour ne lisent stat, trait ou arme du caster.

NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : `BaseTriggeredAbility`, hors `ABILITY_CLASSES`.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours import (Kill, TRIGGERED_ABILITY_BEHAVIOURS, entities_from_state)
from .....entities.behaviours import If
from .....entities.selectors import Caster
from .....entities.triggers import MaybeTrigger
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext

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


def execute_full_throttle(state: State, owner_id: int) -> Optional[dict]:
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[1134]` -- le callable que le noeud DSL
    `TriggerAbility` invoque, unite par unite, pour un declenchement DIRECT.

    `chance` vient du gameconfig (`FullThrottle.constants.chance` = 30) ; absente -> `0`, et
    `next_bool(0)` est toujours faux : le port ne tue alors personne plutot que d'inventer un taux.
    C'est la MEME doctrine que le refus de dispatcher `BattleFatigue` (dont la config, elle,
    n'existe PAS du tout -- ici elle existe, d'ou l'entree)."""
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


# Inscription au registre du noeud `TriggerAbility` (import-time, comme les autres modules
# d'abilities). Le SEUL declencheur porte est `...StormboyzStrike_MissAbility$$CreateBehaviour`.
TRIGGERED_ABILITY_BEHAVIOURS[FULL_THROTTLE] = execute_full_throttle
