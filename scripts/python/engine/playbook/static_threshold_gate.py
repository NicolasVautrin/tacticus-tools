"""Les playbooks Comparable dont `ShouldExecute` compare l'utilite d'action a un SEUIL STATIQUE de la
classe (`#419-r1-tr14-r5-r2-r1-r1-r1-r2`, seuil corrige par `-r4`).

DOUZE classes natives, UN SEUL corps en forme, lu verbatim au decompile (les douze sont IDENTIQUES a
l'adresse du `Il2CppClass*` pres, chacune ayant son propre corps parce qu'elle lit SON static) :

    // <X>Playbook$$ShouldExecute
    y = *(*(Il2CppClass*<X>Playbook + 0xb8));       // `+0xb8` = Il2CppClass.static_fields
    return Fix64.op_GreaterThan(attackHealUtility, y);

La double indirection lit le champ statique d'offset **0** de la classe -- son PREMIER static.

## Le seuil vaut `Fix64(10)`, pour les DOUZE -- et il a DEUX ecrivains

Ce champ est ecrit par `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.cctor` :

    value = FixMath.NET.Fix64$$op_Implicit(0xa);          // Fix64(10)
    klass  = <rgctx du .cctor>[22];                        // Il2CppClass* resolu par RGCTX
    if (!klass.initialized) Class::Init(klass);
    **(klass + 0xb8) = value;                              // le PREMIER static de CETTE classe

C'est le SEUL `Fix64(10)` de la couche playbook, et il ecrit exactement le slot que
`<X>Playbook$$ShouldExecute` lit. QUATRE des douze classes declarent en plus leur propre `.cctor`
qui y ecrit `Fix64(1)` -- mais ce `1` est ECRASE : le `.cctor` derive est declenche par le
`class_init` de la classe derivee (a l'allocation), tandis que celui de la base generique l'est plus
tard, par `ComparablePlaybook<T>..ctor` que le `.ctor` derive appelle ENSUITE. Le dernier ecrivain
gagne, et c'est la base.

**Ce n'est pas une deduction : c'est MESURE, sur DEUX identites aux seuils DECLARES OPPOSES**
(montage `Movement=0` de la tranche precedente, `u` pilote par les PV de la cible, bissection sur
`aiDryRunAllUnits`, `u` lu au canal NATIF `pairUtility`) :

| ability                              | `.cctor` derive | seuil DECLARE | bascule NATIVE mesuree      |
|--------------------------------------|-----------------|---------------|------------------------------|
| `1150 PlasmaCannon`                  | oui, `Fix64(1)` | 1             | `(9.9997062, 10.0000000093]` |
| `1069 SeekerMissileFrequencyLock`    | AUCUN           | 0             | `(9.8438, 10.0781]`          |

Deux seuils declares differents, UN seul seuil effectif. L'encadrement de `1150` est serre a 3e-5 :
il CONTIENT `Fix64(10)` (raw `42949672960`) et EXCLUT tout ce qui est en dessous de `9.99971`.

La comparaison est STRICTE (`Fix64$$op_GreaterThan`) : une utilite EGALE au seuil est REFUSEE.

Les douze `ability_id` sont lus dans le `.ctor` de leur classe
(`ComparablePlaybook<T>..ctor(this, <id>, klass)`), jamais devines du nom.

## Le rang du gate, et ce que ce module ne change PAS

Le gate vit au slot de vtable `+0x328`, appele par
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
avec `attackHealUtility = CalculateCustomUtility + CalculateUtilityFromPredictions`, donc AVANT les
trois termes positionnels (`CalculateCasterPositionUtility`, la cle `0x37`, `Tile(7)`). `false` ==>
`Nullable` VIDE, c.-a-d. AUCUNE action poussee dans le `Bucket` pour ce couple (tuile, cible).
Les deux termes de l'argument sont ceux du DEFAUT pour ces douze
(`ComparablePlaybook<T>$$CalculateCustomUtility` rend `Fix64(0)` et aucune des douze ne la
surcharge -- mesure `resolveMethodPtr`), donc l'argument EST l'utilite de prediction.

Les dix ids enregistres ici retombaient jusqu'ici sur `DefaultActiveAbilityPlaybook` ; les classes
d'ici en HERITENT, donc `make_damage_predictions`, `calculate_custom_utility` et
`make_effect_predictions` restent EXACTEMENT ce qu'ils etaient. Le seul delta est `should_execute`.

## DEUX des douze ne sont PAS enregistrees ici, et c'est delibere

* **1184 MomentShackle** : sa route est le generateur BESPOKE `playbook/bespoke.py`
  (`MomentShacklePlaybook`, self-heal + `CalculateCasterPositionUtility` position-swept), pas
  `_best_attack`. Son gate y vit sous le nom `MIN_UTILITY`, et il porte le MEME seuil.
* **1197 ExcruciatingFrequencies** : route bespoke elle aussi
  (`playbook/excruciating_frequencies.py`, ligne-AoE a cible TUILE, generateur propre). Meme seuil.

Les inscrire au registre serait un port MORT (leur `calculate_action_utility` n'est jamais appele) et
masquerait ou vit reellement leur gate. `NOT_REGISTERED` porte ce fait, et le probe le garde.
"""
from __future__ import annotations

from .base import register
from .common import DefaultActiveAbilityPlaybook
from ..entities.active_ability_type import ActiveAbilityType

#: `Fix64(10)`, ecrit par `ComparablePlaybook<T>$$.cctor` dans le PREMIER static de la classe que
#: `<X>Playbook$$ShouldExecute` lit. Foyer UNIQUE du seuil : les deux routes bespoke le consomment
#: aussi (`bespoke.MomentShacklePlaybook`, `excruciating_frequencies`), pour qu'il n'existe qu'UN
#: endroit ou le corriger.
STATIC_UTILITY_THRESHOLD: float = 10.0


class StaticUtilityThresholdPlaybook(DefaultActiveAbilityPlaybook):
    """`<X>Playbook$$ShouldExecute` de la famille « seuil statique », lu verbatim :

        return attackHealUtility > <premier champ statique de la classe>;

    UNE clause, et elle n'utilise NI le caster, NI la cible, NI la tuile de cast -- seule l'utilite
    d'action deja sommee (custom + predictions) entre dans la comparaison. C'est ce qui permet a une
    unique classe Python de porter les douze identites natives : elles ne different que par leur
    `ability_id`, et leur seuil est le MEME (cf. l'en-tete du module).

    La comparaison est STRICTE (`Fix64$$op_GreaterThan`) : une utilite EGALE au seuil est REFUSEE."""

    def __init__(self, ability_id: int, utility_threshold: float = STATIC_UTILITY_THRESHOLD):
        self.ability_id = int(ability_id)
        self.utility_threshold = float(utility_threshold)

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        return utility > self.utility_threshold


#: Les QUATRE classes qui declarent en plus leur propre `.cctor` (`Fix64(1)`). Le fait est CONSERVE
#: -- il explique pourquoi la tranche precedente lisait `1` -- mais il n'a AUCUN effet : le `.cctor`
#: de la base generique ecrit `Fix64(10)` dans le meme slot, et il ecrit en DERNIER.
DERIVED_CCTOR_IDS: tuple[int, ...] = (
    int(ActiveAbilityType.FlailSwing),        # 1042 = 0x412
    int(ActiveAbilityType.PlasmaCannon),      # 1150 = 0x47e -- MESUREE : bascule a 10
    int(ActiveAbilityType.BlightGrenades),    # 1176 = 0x498
    int(ActiveAbilityType.MomentShackle),     # 1184 = 0x4a0  -- route BESPOKE, cf. NOT_REGISTERED
)

#: Les HUIT classes qui ne declarent AUCUN `.cctor` : leur premier static n'a qu'UN ecrivain, celui
#: de la base generique. (Mesure `class_get_methods`, deux sources -- cf. le probe.)
NO_DERIVED_CCTOR_IDS: tuple[int, ...] = (
    int(ActiveAbilityType.PlagueWind),                  # 1035 = 0x40b
    int(ActiveAbilityType.ScythingTalons),              # 1065 = 0x429
    int(ActiveAbilityType.SeekerMissileFrequencyLock),  # 1069 = 0x42d -- MESUREE : bascule a 10
    int(ActiveAbilityType.StaffOfStars),                # 1073 = 0x431
    int(ActiveAbilityType.ScytheOfDust),                # 1074 = 0x432
    int(ActiveAbilityType.Supercharge),                 # 1103 = 0x44f
    int(ActiveAbilityType.ExcruciatingFrequencies),     # 1197 = 0x4ad  -- route BESPOKE
    int(ActiveAbilityType.AncestralFortune),            # 1207 = 0x4b7
)

#: Les deux identites dont le gate vit AILLEURS (generateur bespoke) -- cf. l'en-tete du module.
NOT_REGISTERED: frozenset[int] = frozenset({
    int(ActiveAbilityType.MomentShackle),             # 1184 -> playbook/bespoke.py
    int(ActiveAbilityType.ExcruciatingFrequencies),   # 1197 -> playbook/excruciating_frequencies.py
})

#: Un seul seuil pour les douze -- c'est le RESULTAT de la mesure, pas une simplification.
THRESHOLD_BY_ID: dict[int, float] = {
    aid: STATIC_UTILITY_THRESHOLD
    for aid in (DERIVED_CCTOR_IDS + NO_DERIVED_CCTOR_IDS)
}


def _register_all() -> None:
    for aid, thr in THRESHOLD_BY_ID.items():
        if aid in NOT_REGISTERED:
            continue
        register(StaticUtilityThresholdPlaybook(aid, thr))


_register_all()
