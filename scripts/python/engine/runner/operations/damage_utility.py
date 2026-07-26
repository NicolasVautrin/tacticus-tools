"""Port de `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector` (noeud DSL
`IdunBattleLogic.Entities.DSLFactory$$SortUnitsByDamageUtility`) — tri de cibles par l'UTILITE IA de degat.

DECOMPILE (`…SortUnitsByDamageUtilitySelector$$Select`, lecture integrale) :

    units   = (+0x20).Select(entities)                       # la source de candidats
    owner   = (+0x18).SelectSingle(entities)                 # l'attaquant
    dmgMin  = (+0x40).Calculate(entities)                    # noeud de degat (min)
    dmgMax  = (+0x48) ? (+0x48).Calculate(entities) : dmgMin # (optionnel ; sinon min == max)
    ability = (+0x28) ? (+0x28).Calculate(...) : GetNormalAttackType(owner)
    foreach u in units :
        pred = <DamagePrediction scenario 0x25>(owner, u, ability, dmgMin, dmgMax, …)
        dict[u] = UtilityDecider.CalculateUtility(+0x38 = UtilityDefinition(0x22 = 34 = Damage), u, pred)
    return units.OrderBy( u => Fix64.op_UnaryNegation(dict[u]) ).ToList()

Le lambda de tri (`…SortUnitsByDamageUtilitySelector.u003Cu003Ec__DisplayClass9_0$$u003CSelectu003Eb__0`)
rend **−utilite** ⇒ `OrderBy` croissant sur −u = tri **DECROISSANT** par utilite ⇒ le `First(…)` d'un
call-site prend l'**argmax du composite Damage(34)** = DamageDealt(35) + KillUnit(36) + OverkillUnit(37)
(`engine.utilities.damage_composite`, poids BC `Utilities`).

La prediction IA est PRE-ARMURE (`armor = 0`, cf. en-tete de `services/damage_prediction`) ⇒ la PLAGE de
degat est la MEME pour toutes les cibles ; le classement ne depend que des PV courants/max et des flags
kill/overkill PAR cible. Ce module ne porte donc que l'etage TRI (la plage vient de l'appelant, qui sait
quel noeud de degat le call-site branche sur +0x40/+0x48).

Deux call-sites portes :
  * `IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$CreateBehaviour` — plage =
    l'attaque NORMALE melee de l'owner (`_normal_attack_health_range`).
  * `IdunBattleLogic.Entities.Abilities.Active.Loki.AncestralFortuneAbility$$ExecuteBehaviour` — plage =
    `MinMaxDamage(entities, 1)` = `Half(Sum(Direct(minDmg[lvl]), Direct(maxDmg[lvl])))`
    (`IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` branche `useAverage != 0`), donc
    min == max == moyenne des bornes de l'ability.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import HealthComponent
from ...utilities import damage_composite
from ...weights import load as _load_weights

# Cache des poids d'utilite (BC `Utilities` — statiques par bataille, cf.
# project_ai_weights_in_battle_config) : seules KillUnit/OverkillUnit sont lues ici, les poids
# DamageDealt 80/20 etant des Fix64 codes en dur dans `DamageUtility$$.cctor`.
_DAMAGE_UTILITY_WEIGHTS = None


def damage_utility_weights():
    global _DAMAGE_UTILITY_WEIGHTS
    if _DAMAGE_UTILITY_WEIGHTS is None:
        _DAMAGE_UTILITY_WEIGHTS = _load_weights()
    return _DAMAGE_UTILITY_WEIGHTS


def _target_utility(state: State, target_id: int, dmin: int, dmax: int, wt) -> float:
    """`UtilityDecider.CalculateUtility(UtilityDefinition(0x22 = Damage), cible, prediction)` pour UNE
    cible — mirror des champs que `UtilityAttackCase$$ForDamagePrediction` lit du `DamagePredictionResult`
    (bornes santé capées/brutes, PV avant, kill = `MightBeKill`, killSure = `WillBeKill`). Bouclier non
    modelise (`shieldBefore = 0`, meme residu que le reste du moteur)."""
    e = state.get_entity(target_id)
    hc = e.get_component(HealthComponent) if e is not None else None
    hp = int(hc.hp) if (hc is not None and hc.hp is not None) else 0
    max_hp = int(hc.hp_max) if (hc is not None and hc.hp_max) else hp
    pred = {"healthDmgMin": max(0, dmin), "healthDmgMax": max(0, dmax),
            # rawHealthDmg* = plage NON capee (mirror @0x24/@0x28) : `OverkillUnit` fidele via l'over-shoot
            # (dmg >= 2*PV) — la prediction pre-armure EST deja brute.
            "rawHealthDmgMin": max(0, dmin), "rawHealthDmgMax": max(0, dmax),
            "hpBefore": hp, "shieldBefore": 0,
            "killSure": hp > 0 and dmin >= hp,          # WillBeKill  (dmg min >= PV)
            "kill": hp > 0 and dmax >= hp}              # MightBeKill (dmg max >= PV)
    return damage_composite(pred, max_hp, wt)


def sort_units_by_damage_utility(state: State, candidates, dmin: int, dmax: int) -> list:
    """`SortUnitsByDamageUtilitySelector$$Select` — les candidats TRIES par utilite Damage DECROISSANTE
    (`OrderBy(−utilite)`). Tie-break : `OrderBy` natif STABLE sur l'ordre source ; approxime ici par `id`
    croissant (les call-sites portes alimentent le selecteur avec un ensemble non ordonne)."""
    wt = damage_utility_weights()
    ordered = sorted(int(c) for c in candidates)
    return sorted(ordered, key=lambda eid: -_target_utility(state, eid, dmin, dmax, wt))


def first_by_damage_utility(state: State, candidates, dmin: int, dmax: int) -> Optional[int]:
    """`First(SortUnitsByDamageUtility(…), 1)` — l'argmax du composite Damage(34), ou None si aucun
    candidat. Argmax STRICT sur l'ordre `id` croissant = 1er id en cas d'egalite parfaite (== la stabilite
    de l'`OrderBy` natif sur l'ordre source)."""
    best, best_util = None, None
    wt = damage_utility_weights()
    for eid in sorted(int(c) for c in candidates):
        util = _target_utility(state, eid, dmin, dmax, wt)
        if best_util is None or util > best_util:
            best_util, best = util, eid
    return best
