"""Vecteur `On(0x2c = 44 UnitHealedWithRemoveEffects)` -- le troisieme et dernier evenement du soin,
et il n'etait pas emis.

`IdunBattle.Operations.HealUnitOperation$$Execute` finit par TROIS appels au slot 0x51 de
l'`OperationProcessor` (`Core.Services.OperationProcessor$$EvaluateAbilities(actor, caster, target,
trigger, ability)`, surcharge a 5 arguments -- signature LUE dans `frida/methods.tsv`, slot 81 lu
dans `metadata/ioperationprocessor_slots.tsv`). Verbatim sur `rnca9r7q6c` :

    processor.<slot 0x51>(healed, healed, healed, 0x1e, <null>)
    processor.<slot 0x51>(caster, caster, healed, 0x2b UnitHealed,                   abilityOrEffect)
    if (removeEffects) processor.<slot 0x51>(caster, caster, healed, 0x2c, abilityOrEffect)

⚠ **Le nommage de Ghidra est DECALE d'un cran sur cette fonction** (retour de struct
`OperationResult` par pointeur cache) : ce que le pseudo-C appelle `abilityOrEffect` est en realite
`removeEffects:System.Boolean`, et le vrai `abilityOrEffect` arrive sur la PILE
(`in_stack_00000040`). Le decalage est deja documente en tete de `runner/operations/heal.py`. C'est
donc bien `removeEffects` qui GATE le troisieme appel -- ce que confirme le NOM de l'evenement.

Consequence de ce gate, et elle DISCRIMINE : `IdunBattle.Entities.Behaviours.HealBehaviourOptions$$
ForHeal` pose `removeEffects = 1` (le soin ordinaire emet donc `On(0x2c)`) tandis que
`$$ForRegenerate` pose `removeEffects = 0` (une REGENERATION ne l'emet pas). Ce sont les deux seules
fabriques du build.

## POURQUOI CE MODULE EXISTE (#1037)

`runner/operations/heal.py` NOMMAIT ces trois vecteurs dans ses non-portes et justifiait l'omission
ainsi : « Le SEUL consommateur porte est le stat-mod EXTRA_HITS du trait `Swarm` [...] deja cable
par l'appel direct a `on_group_unit_hp_changed` ». C'etait vrai a l'ecriture, et c'est devenu FAUX :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WyrdmakersHelmAbility$$CreateTrigger` ouvre sur
`On(0x2c, ownerNeedsToBeAlive: true)`, qu'aucun raccourci ne couvre. MEME forme que #964-r1 cote
reparation (`dispatch/repair.py`).

⚠ Le raccourci `Swarm` RESTE en place et n'est pas double : `on_group_unit_hp_changed` est un appel
DIRECT au recalcul du stat-mod, il ne passe pas par le registre de triggers, et le trait `Swarm` n'a
aucune entree `event_id == 44` dans `TRAIT_TRIGGERS`.

## CE QUI N'EST PAS PORTE, ET LE RESTE

Les DEUX premiers appels restent non emis, faute de consommateur porte -- les ajouter serait un
vecteur mort :
  * `On(0x1e)` sur le triplet `(healed, healed, healed)` ;
  * `On(0x2b = 43 UnitHealed)` sur `(caster, caster, healed)`, dont le seul consommateur porte est le
    bras `On(UnitHealed=43)` du trait `Swarm`, deja servi par le raccourci ci-dessus.
Ils restent NOMMES dans `operations/heal.py`.
"""
from __future__ import annotations

from .....dsl.event_trigger_type import EventTriggerType
from ....state import State
from ..base import TriggerEvent
from .core import evaluate_trigger_operation


def unit_healed_with_remove_effects_triggers(state: State, caster_id, target_id: int,
                                             ability_or_effect=None) -> list[dict]:
    """`processor.<slot 0x51>(caster, caster, healed, 0x2c UnitHealedWithRemoveEffects, ability)`.

    `actor_id = caster_id` : le natif passe le SOIGNEUR dans les deux premiers slots (actor ET
    caster) et l'unite SOIGNEE en `target` -- exactement comme son voisin `On(0x30 UnitRepaired)`.
    C'est ce triplet qui donne son sens au `get_OwnerIsTarget` du consommateur : le porteur du
    trigger doit etre l'unite QUI RECOIT le soin, jamais celle qui le donne.

    ⚠ **PLACE DANS LA SEQUENCE** : le natif l'emet APRES la mutation (`FillUp`), APRES le gate de
    sortie anticipee et APRES l'increment `stats[0xd4] += 1`. Un consommateur qui lit
    `TimesHealedThisTurn(Target)` voit donc **1** au premier soin du tour, pas 0 -- c'est ce qui rend
    le gate `AmountIsEqual(..., Const(1))` de `WyrdmakersHelmAbility` satisfaisable. L'ordre n'est
    pas cosmetique.

    `caster_id` nul (soin sans soigneur : effet de tuile, regeneration) -> le natif passe quand meme
    l'event avec un owner nul ; le port emet de meme, avec `actor_id = None`."""
    ev = TriggerEvent(EventTriggerType.UnitHealedWithRemoveEffects,
                      None if caster_id is None else int(caster_id), int(target_id),
                      ranged=False, profile=None, ability_type=ability_or_effect)
    return evaluate_trigger_operation(state, ev)
