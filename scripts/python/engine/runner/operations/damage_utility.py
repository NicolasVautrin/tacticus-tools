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
call-site prend l'**argmax du composite Damage(34)** = DamageDealt(35) + KillUnit(36) + OverkillUnit(38)
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
from ..components import HealthComponent, StatsComponent
from ...utilities import damage_composite
from ...services.damage_prediction import attacker_could_crit
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


def owner_might_crit(state: State, owner_id: int) -> bool:
    """`MightCrit` de la prediction que le selecteur natif construit pour l'OWNER (`this+0x18`).

    `SortUnitsByDamageUtilitySelector$$Select` n'invente pas de prediction : il appelle le service
    (`this+0x50`) avec `owner` et recopie la `DamagePredictionResult` COMPLETE dans son etat de
    boucle (les 0x9c octets `+0x10..+0xac` du decompile), flags compris. Le champ `MightCrit` y vaut
    donc ce que `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` y ecrit :
    `IdunBattle.Core.Services.DamageCalculations$$CouldCrit(owner)`.

    FOYER UNIQUE reutilise, pas de second mirror : `services.damage_prediction.attacker_could_crit`,
    le meme producteur que la chaine PLAYBOOK (#R34). `UnitContext.crit_chance`/`.crit_damage` sont
    des proprietes adossees a `get_stat(Current)` = `IdunBattle.Entities.UnitExtensions$$GetStat`
    NU — exactement le niveau de lecture de `CouldCrit`, qui ignore la couche calc-time
    `GetCritChanceBonusFromEffects` / `GetCritDamageBonusFromEffects`.

    Owner sans `StatsComponent` (montage sans stats) -> `False`, comme `attacker_could_crit(None)`."""
    e = state.get_entity(owner_id) if owner_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    return bool(attacker_could_crit(sc.ctx if sc is not None else None))


def _target_utility(state: State, target_id: int, dmin: int, dmax: int, wt,
                    might_crit: bool = False) -> float:
    """`UtilityDecider.CalculateUtility(UtilityDefinition(0x22 = Damage), cible, prediction)` pour UNE
    cible — mirror des champs que `UtilityAttackCase$$ForDamagePrediction` lit du `DamagePredictionResult`
    (bornes santé capées/brutes, PV avant, kill = `MightBeKill`, killSure = `WillBeKill`). Bouclier non
    modelise (`shieldBefore = 0`, meme residu que le reste du moteur).

    `might_crit` = `MightCrit` de l'OWNER (identique pour toutes les cibles d'un meme `Select` : le
    natif l'evalue sur l'ATTAQUANT). Il est calcule UNE FOIS par l'appelant (`owner_might_crit`) et
    non par cible, ce qui est exact et evite N lectures de stats."""
    e = state.get_entity(target_id)
    hc = e.get_component(HealthComponent) if e is not None else None
    hp = int(hc.hp) if (hc is not None and hc.hp is not None) else 0
    max_hp = int(hc.hp_max) if (hc is not None and hc.hp_max) else hp
    pred = {"healthDmgMin": max(0, dmin), "healthDmgMax": max(0, dmax),
            # rawHealthDmg* = plage NON capee (mirror @0x24/@0x28) : `OverkillUnit` fidele via l'over-shoot
            # (dmg >= 2*PV) — la prediction pre-armure EST deja brute.
            "rawHealthDmgMin": max(0, dmin), "rawHealthDmgMax": max(0, dmax),
            "hpBefore": hp, "shieldBefore": 0,
            # #419-r6-r1 : `MightCrit` etait ABSENT de ce dict -> `might_be_overkill` lisait 0 en dur,
            # la ou le natif passe le flag de la prediction. Sans effet TANT QUE le canal crit etait
            # muet (`CouldCrit` faux sur 106/106 unites normalisees) ; la bascule du defaut a
            # « equiper » (#419-r6) l'ouvre sur 98/106, donc l'ecart devient REEL. Effet : toute cible
            # dont les PV tombent dans `(dmax/2, dmax]` (letale mais SOUS `overkillDmgPctOfHealth`)
            # vaut `PossibleOverkill` pour le natif et 0 pour le port -> classement different.
            "mightCrit": bool(might_crit),
            "killSure": hp > 0 and dmin >= hp,          # WillBeKill  (dmg min >= PV)
            "kill": hp > 0 and dmax >= hp}              # MightBeKill (dmg max >= PV)
    return damage_composite(pred, max_hp, wt)


def sort_units_by_damage_utility(state: State, candidates, dmin: int, dmax: int,
                                 owner_id: int) -> list:
    """`SortUnitsByDamageUtilitySelector$$Select` — les candidats TRIES par utilite Damage DECROISSANTE
    (`OrderBy(−utilite)`). Tie-break : `OrderBy` natif STABLE sur l'ordre source ; approxime ici par `id`
    croissant (les call-sites portes alimentent le selecteur avec un ensemble non ordonne).

    `owner_id` = l'OWNER du selecteur (`this+0x18`, `SelectSingle(entities)`), OBLIGATOIRE : c'est lui
    qui porte `MightCrit`. Un defaut `None` re-creerait le canal muet que #419-r6-r1 ferme."""
    wt = damage_utility_weights()
    mc = owner_might_crit(state, owner_id)
    ordered = sorted(int(c) for c in candidates)
    return sorted(ordered, key=lambda eid: -_target_utility(state, eid, dmin, dmax, wt, mc))


def first_by_damage_utility(state: State, candidates, dmin: int, dmax: int,
                            owner_id: int) -> Optional[int]:
    """`First(SortUnitsByDamageUtility(…), 1)` — l'argmax du composite Damage(34), ou None si aucun
    candidat. Argmax STRICT sur l'ordre `id` croissant = 1er id en cas d'egalite parfaite (== la stabilite
    de l'`OrderBy` natif sur l'ordre source). `owner_id` : cf. `sort_units_by_damage_utility`."""
    best, best_util = None, None
    wt = damage_utility_weights()
    mc = owner_might_crit(state, owner_id)
    for eid in sorted(int(c) for c in candidates):
        util = _target_utility(state, eid, dmin, dmax, wt, mc)
        if best_util is None or util > best_util:
            best_util, best = util, eid
    return best
