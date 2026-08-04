"""Les playbooks Comparable dont `ShouldExecute` compare l'utilite d'action a un SEUIL STATIQUE de la
classe (`#419-r1-tr14-r5-r2-r1-r1-r1-r2`).

DOUZE classes natives, UN SEUL corps en forme, lu verbatim au decompile (les douze sont IDENTIQUES a
l'adresse du `Il2CppClass*` pres, chacune ayant son propre corps parce qu'elle lit SON static) :

    // <X>Playbook$$ShouldExecute
    y = *(*(Il2CppClass*<X>Playbook + 0xb8));       // `+0xb8` = Il2CppClass.static_fields
    return Fix64.op_GreaterThan(attackHealUtility, y);

La double indirection lit le champ statique d'offset **0** de la classe -- son PREMIER static. La
valeur ne se DEDUIT pas du nom de l'ability ni d'une voisine : elle s'ecrit dans le `.cctor`, et
**quatre** des douze classes seulement en declarent un.

## Le seuil, classe par classe (JAMAIS generalise depuis la premiere lue)

`Fix64(1)` -- ecrit par `<X>Playbook$$.cctor` : `FixMath.NET.Fix64$$op_Implicit(1)` stocke a
l'offset 0 des statics. Les QUATRE `.cctor` ont ete lus un par un :

* `IdunBattle.AI.Playbook.BlightGrenadesPlaybook$$.cctor`            -> 1176 BlightGrenades
* `IdunBattle.AI.Playbook.Loki.FlailSwingPlaybook$$.cctor`           -> 1042 FlailSwing
* `IdunBattle.AI.Playbook.Loki.MomentShacklePlaybook$$.cctor`        -> 1184 MomentShackle
* `IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$.cctor`         -> 1150 PlasmaCannon

`Fix64(0)` -- les HUIT classes SANS `.cctor` : `Class::Init` alloue `static_fields` zero-initialise
et rien ne l'ecrit jamais, donc le seuil vaut zero et le gate se lit `utility > 0`.

* `Loki.AncestralFortunePlaybook` 1207 | `Loki.ExcruciatingFrequenciesPlaybook` 1197
* `Loki.PlagueWindPlaybook` 1035      | `Loki.ScytheOfDustPlaybook` 1074
* `Loki.ScythingTalonsPlaybook` 1065  | `Loki.SeekerMissileFrequencyLockPlaybook` 1069
* `Loki.StaffOfStarsPlaybook` 1073    | `Loki.SuperchargePlaybook` 1103

⚠ **L'absence d'un `.cctor` est MESUREE, pas grep-ee.** Les tables de symboles sont indexees par
ADRESSE et IL2CPP deduplique les corps triviaux : « pas dans la table » n'y prouve rien. Le verdict
vient de DEUX enumerations `class_get_methods` independantes -- le dump Frida
(`data/symbols/<build>/frida/methods.tsv`) et le RPC `resolveMethodPtr` REJOUE dans le processus,
avec `ShouldExecute` en TEMOIN a `depth 0` (sans lui, « aucun `.cctor` » ne mesurerait que la panne
du RPC). Probe : `scripts/python/probe_419r1tr14r5r2r1r1r1r2_static_threshold_gate.py`.

Les douze `ability_id` sont lus dans le `.ctor` de leur classe
(`ComparablePlaybook<T>..ctor(this, <id>, klass)`), jamais devines du nom.

## Le rang du gate, et ce que ce module ne change PAS

Le gate vit au slot de vtable `+0x328`, appele par
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
avec `attackHealUtility = CalculateCustomUtility + CalculateUtilityFromPredictions`, donc AVANT les
trois termes positionnels (`CalculateCasterPositionUtility`, la cle `0x37`, `Tile(7)`). `false` ==>
`Nullable` VIDE, c.-a-d. AUCUNE action poussee dans le `Bucket` pour ce couple (tuile, cible). La
degradation qu'il ferme est PERMISSIVE : sans lui, le port propose des casts que le natif ecarte.

Les dix ids enregistres ici retombaient sur `DefaultActiveAbilityPlaybook` (aucune entree au
registre) ; les classes d'ici en HERITENT, donc `make_damage_predictions`, `calculate_custom_utility`
et `make_effect_predictions` restent EXACTEMENT ce qu'ils etaient. Le seul delta est
`should_execute`. Une instance par identite -- c'est le mirror des classes natives, toutes concretes.

## DEUX des douze ne sont PAS enregistrees ici, et c'est deliberé

* **1184 MomentShackle** : sa route est le generateur BESPOKE `playbook/bespoke.py`
  (`MomentShacklePlaybook`, self-heal + `CalculateCasterPositionUtility` position-swept), pas
  `_best_attack`. Son gate y vit deja sous le nom `MIN_UTILITY` -- cette tranche n'y corrige que la
  BORNE (`>` strict, pas `>=`).
* **1197 ExcruciatingFrequencies** : route bespoke elle aussi
  (`playbook/excruciating_frequencies.py`, ligne-AoE a cible TUILE, generateur propre). Son gate y
  est deja pose et conforme au seuil LU (`if u <= 0: return None`, soit `u > 0`) ; l'enregistrer ici
  creerait une seconde voie sans effet sur la premiere.

Les inscrire au registre serait un port MORT (leur `calculate_action_utility` n'est jamais appele) et
masquerait ou vit reellement leur gate. `NOT_REGISTERED` porte ce fait, et le probe le garde.
"""
from __future__ import annotations

from .base import register
from .common import DefaultActiveAbilityPlaybook
from ..entities.active_ability_type import ActiveAbilityType


class StaticUtilityThresholdPlaybook(DefaultActiveAbilityPlaybook):
    """`<X>Playbook$$ShouldExecute` de la famille « seuil statique », lu verbatim :

        return attackHealUtility > <premier champ statique de la classe>;

    UNE clause, et elle n'utilise NI le caster, NI la cible, NI la tuile de cast -- seule l'utilite
    d'action deja sommee (custom + predictions) entre dans la comparaison. C'est ce qui permet a une
    unique classe Python de porter les douze identites natives : elles ne different que par leur
    `ability_id` et par la VALEUR de leur static.

    La comparaison est STRICTE (`Fix64$$op_GreaterThan`) : une utilite EGALE au seuil est REFUSEE.
    Le point mord reellement au seuil `1` -- `u == 1.0` exactement est atteignable (une utilite de
    degat vaut `100 * dmg / (maxHP + 2)` sur une cible a PV pleins sans bouclier), et c'est
    exactement l'ecart que la borne `>=` du bespoke `MomentShacklePlaybook` portait."""

    def __init__(self, ability_id: int, utility_threshold: float):
        self.ability_id = int(ability_id)
        self.utility_threshold = float(utility_threshold)

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        return utility > self.utility_threshold


#: Seuil `Fix64(1)` -- LU dans le `.cctor` de CHAQUE classe, un par un.
THRESHOLD_ONE_IDS: tuple[int, ...] = (
    int(ActiveAbilityType.FlailSwing),        # 1042 = 0x412
    int(ActiveAbilityType.PlasmaCannon),      # 1150 = 0x47e
    int(ActiveAbilityType.BlightGrenades),    # 1176 = 0x498
    int(ActiveAbilityType.MomentShackle),     # 1184 = 0x4a0  -- route BESPOKE, cf. NOT_REGISTERED
)

#: Seuil `Fix64(0)` -- ces classes ne declarent AUCUN `.cctor` (mesure `class_get_methods`, deux
#: sources), donc leur premier static reste a la valeur zero-initialisee de `Class::Init`.
THRESHOLD_ZERO_IDS: tuple[int, ...] = (
    int(ActiveAbilityType.PlagueWind),                  # 1035 = 0x40b
    int(ActiveAbilityType.ScythingTalons),              # 1065 = 0x429
    int(ActiveAbilityType.SeekerMissileFrequencyLock),  # 1069 = 0x42d
    int(ActiveAbilityType.StaffOfStars),                # 1073 = 0x431
    int(ActiveAbilityType.ScytheOfDust),                # 1074 = 0x432
    int(ActiveAbilityType.Supercharge),                 # 1103 = 0x44f
    int(ActiveAbilityType.ExcruciatingFrequencies),     # 1197 = 0x4ad  -- route BESPOKE
    int(ActiveAbilityType.AncestralFortune),            # 1207 = 0x4b7
)

#: Les deux identites dont le gate vit AILLEURS (generateur bespoke) -- cf. l'en-tete du module.
#: Elles restent listees ci-dessus parce que leur SEUIL est un fait de cette tranche ; elles ne sont
#: simplement pas poussees au registre, ou elles seraient inertes.
NOT_REGISTERED: frozenset[int] = frozenset({
    int(ActiveAbilityType.MomentShackle),             # 1184 -> playbook/bespoke.py
    int(ActiveAbilityType.ExcruciatingFrequencies),   # 1197 -> playbook/excruciating_frequencies.py
})

THRESHOLD_BY_ID: dict[int, float] = {
    **{aid: 1.0 for aid in THRESHOLD_ONE_IDS},
    **{aid: 0.0 for aid in THRESHOLD_ZERO_IDS},
}


def _register_all() -> None:
    for aid, thr in THRESHOLD_BY_ID.items():
        if aid in NOT_REGISTERED:
            continue
        register(StaticUtilityThresholdPlaybook(aid, thr))


_register_all()
