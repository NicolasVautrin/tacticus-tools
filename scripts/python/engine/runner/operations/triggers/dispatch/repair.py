"""Vecteur `On(0x30 = 48 UnitRepaired)` -- le SEUL evenement de la reparation, et il n'etait pas emis.

`IdunBattle.Operations.RepairUnitOperation$$Execute` finit par DEUX appels au slot 0x51 de
l'`OperationProcessor` (le dispatch de triggers), lus verbatim sur `rnca9r7q6c` :

    if (repaired < 1 && cleansed < 1 && !HasFlag(target, 0x18)) return {};
    result.repaired += repaired ; <statistiques> ; <event UnitRepaired> ;
    processor.<slot 0x51>(caster, caster, target, 0x30 UnitRepaired, ...)
    if (repaired > 0) processor.<slot 0x51>(target, target, target, 0x1e, ...)

Le PREMIER est celui-ci : `owner = actor = le REPARATEUR`, `target = la cible reparee`. C'est ce
triplet qui fait de `get_OwnerIsCaster` un gate discriminant -- le passif ne fire que pour le
mecanicien, jamais pour un spectateur.

## POURQUOI CE MODULE EXISTE (#964-r1)

`runner/operations/repair.py` NOMMAIT ce vecteur dans ses non-portes (« les vecteurs de trigger
`processor.<slot 0x51>` `On(0x30 = 48 UnitRepaired)` et `On(0x1e)` ») et justifiait l'omission
ainsi : « Le SEUL consommateur porte de `On(48 = UnitRepaired)` est le stat-mod EXTRA_HITS du trait
`Swarm`, deja cable par l'appel direct a `on_group_unit_hp_changed` ». C'etait vrai a l'ecriture, et
c'est devenu FAUX : `ECogSupportAbility$$CreateTrigger` = `On(0x30, ownerNeedsToBeAlive: 1) &
get_OwnerIsCaster` est un second consommateur, qu'aucun raccourci ne couvre.

⚠ Le raccourci `Swarm` RESTE en place et n'est pas double : `on_group_unit_hp_changed` est un appel
DIRECT au recalcul du stat-mod, il ne passe pas par le registre de triggers. Le trait `Swarm` n'a
d'ailleurs pas d'entree `event_id == 48` dans `TRAIT_TRIGGERS` -- verifiable d'un grep, et c'est
exactement ce qui garantit qu'ajouter le vecteur ne le fait pas fire deux fois.

## CE QUI N'EST PAS PORTE, ET LE RESTE

Le SECOND appel (`On(0x1e)`, sur le triplet `(target, target, target)`, sous le gate
`repaired > 0`) n'a aucun consommateur porte -- l'ajouter serait un vecteur mort. Il reste NOMME
dans `operations/repair.py`.
"""
from __future__ import annotations

from .....dsl.event_trigger_type import EventTriggerType
from ....state import State
from ..base import TriggerEvent
from .core import evaluate_trigger_operation


def unit_repaired_triggers(state: State, caster_id, target_id: int) -> list[dict]:
    """`processor.<slot 0x51>(caster, caster, target, 0x30 UnitRepaired, ...)`.

    `actor_id = caster_id` : le natif passe le REPARATEUR dans les deux premiers slots (owner ET
    actor), donc `get_OwnerIsCaster` cote consommateur se lit sur cet acteur.

    ⚠ **PLACE DANS LA SEQUENCE** : le natif l'emet APRES la mutation (`FillUp`) et APRES le gate de
    sortie anticipee, donc le consommateur voit les PV DEJA remontes. Un `ECogSupport` qui compterait
    ses E-Cogs avant la reparation lirait le meme compte, mais un consommateur qui lirait les PV
    verrait le mauvais etat -- l'ordre n'est pas cosmetique.

    `caster_id` nul (reparation sans reparateur : effet de tuile, regeneration) -> le natif passe
    quand meme l'event avec un owner nul et aucun `get_OwnerIsCaster` ne peut alors matcher ; le port
    emet de meme, avec `actor_id = None`."""
    ev = TriggerEvent(EventTriggerType.UnitRepaired,
                      None if caster_id is None else int(caster_id), int(target_id),
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)
