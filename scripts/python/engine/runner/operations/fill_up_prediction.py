"""Les DEUX etages de SUBSTRAT que `IdunBattle.Core.Services.DamagePrediction$$PredictHeal` et
`IdunBattle.Core.Services.DamagePrediction$$PredictRepair` partagent MOT POUR MOT (#520).

Ce ne sont pas des mirrors de fonctions natives : ce sont les ADAPTATEURS qui disent, pour chacun
des deux caps de ces prediction, ce que le substrat runner sait lire. Ils vivaient dans
`operations/repair.py` (#299) ; #520 a porte le pipeline de SOIN, et le natif y ecrit les deux
MEMES lignes :

    health = UnitExtensions.GetStat(target, 5 Health, 0 Current)
    if (scope == 1) predicted = Min(predicted, GetGroupUnitHealLimit(target, health))
    if (UnitExtensions.IsBoss(target))
        predicted = Min(predicted, GetStat(target, 5 Health, 3 Initial) - health)

Les DUPLIQUER aurait cree deux lectures d'une meme limite de substrat, exactement ce que la
doctrine « une seule lecture du natif, deux substrats -- surtout pas deux tables » interdit.

ASCII only (console cp1252).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..components import StatsComponent

if TYPE_CHECKING:
    from ..state import State


def group_unit_members(state: "State", unit_id) -> int:
    """`GetComponent<NumberOfMembersComponent>(target)+0x10` = `nrOfMembers`, le champ que
    `IdunBattle.Core.Services.DamagePrediction$$GetGroupUnitHealLimit` lit en TOUT PREMIER
    (`if (nrOfMembers < 2) return int.MaxValue`).

    Substrat runner : `StatsComponent.ctx.number_of_members` (seede depuis `nrOfMembers` du
    gameconfig / de la capture, cf. `entities/unit_context.py` et `operations/spawn.py`) -- MEME
    source que le `n` que le trigger `LivingMetal` lisait avant #310. Defaut 1 = unite simple, donc
    branche `int.MaxValue` = pas de cap, exactement comme le natif sur un heros."""
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or getattr(sc, "ctx", None) is None:
        return 1
    return max(1, int(getattr(sc.ctx, "number_of_members", 1) or 1))


def is_boss(state: "State", unit_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsBoss` -- NON PORTE, et le decompile dit POURQUOI :

        TryGetComponent<UnitComponent>(unit, out c) && *(byte*)(c + 0x88)

    Ce n'est PAS `HasTrait(Boss)` (l'erreur naturelle : `UnitTrait.Boss` existe et vaut 2023) mais un
    CHAMP du `UnitComponent`, qu'aucun canal de seed du runner n'expose (`components.UnitComponent`
    n'a pas d'attribut boss -- et tous les appelants de `predict.repair_utility` passent deja
    `is_boss=False`). Rendu `False` = le cap boss ne s'applique jamais.

    CONSEQUENCE CHIFFREE, et elle est nulle sur le substrat runner : le cap boss vaut
    `GetStat(Health, Initial) - current`, tandis que l'etage SUIVANT (`MaxFillUp`) cape a
    `CurrentMaximumValue - current`. Le canal offline n'expose qu'UN SEUL plafond (`hp_max`), donc
    les deux bornes s'y confondent -- meme argument, mot pour mot, que la branche BOSS d'
    `attack_query.is_damaged_unit`. Un port qui INVENTERAIT `Initial != hp_max` fabriquerait un cap
    la ou le natif n'en met pas."""
    return False
