"""Le CLEAVE des `<X>_NormalAttackAbility` de la famille `GetAdditionalTargetsAttackBehavior`
(#478) : `Boltstorm`, `RighteousRepugnance`, `Fealty`, `TalonOfHorus`.

Quatre attaques normales CONCRETES (substituees par un passif, cf.
`engine.services.custom_normal_attack`) frappent, EN PLUS de la cible primaire, un ensemble de
cibles ADDITIONNELLES. Face DECISION deja portee (le fold `GetAdditionalDamagePrediction` de
`Boltstorm`/`RighteousRepugnance`, `playbook/prediction/normal_attack.py`) ; face COMBAT portee ICI.

## L'artefact natif, relu sur `rnca9r7q6c`

    <X>_NormalAttackAbility$$ExecuteBehaviour(abilityState, entities):
        weapon = ALoki_NormalAttackAbility$$FindAttackWeapon(entities)
        if (weapon == null) return 0
        <GATE>  ->  Execute<X>(abilityState, entities, weapon)
        sinon   ->  la voie SANS cleave

    <X>_NormalAttackAbility$$Execute<X>(abilityState, entities, weapon):
        sel = <X>Ability$$GetAdditionalTargets(dsl [, Direct(weapon.Range)])
        ALoki_NormalAttackAbility$$ExecuteInformWeapon(weapon, entities, null)
        ALoki_NormalAttackAbility$$ExecuteNormalAttack(abilityState, entities, weapon)   # PRIMAIRE
        b = IdunBattleLogic.Entities.DSLBehaviors$$Foreach(sel, t => GetAdditionalTargetsAttackBehavior(t, abilityState))
        IdunBattle.Entities.Abilities.AActiveAbility$$ExecuteAtomic(b, entities, 0x2a)
        return ALoki_NormalAttackAbility$$ExecuteTriggerAbilities(entities, weapon)

    <X>_NormalAttackAbility$$GetAdditionalTargetsAttackBehavior(target, abilityState):
        return IdunBattleLogic.Entities.DSLBehaviors$$Attack(
                   caster = <DSLSelectors+0x48>, target,
                   GetAdditionalDamageBehaviour(abilityState, target), source)

    <X>_NormalAttackAbility$$GetAdditionalDamageBehaviour(abilityState, target):
        return IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage(
                   caster = <DSLSelectors+0x48>, target,
                   amount  = DSLFormulas$$RandomAmount(GetVariableForLevel(0xc), GetVariableForLevel(0xd)),
                   profile = DSLSelectors$$Direct(AbilityConfiguration$$GetDamageProfile()),
                   hits    = DSLFormulas$$Direct(AbilityConfiguration$$GetNumberConstant(0x2f)),
                   source, options = <struct ZEROEE, HasValue = 0>)

## LE SECOND VOLET -- `$$GetCustomNormalAttackBehaviour`, le fold sur la cible PRIMAIRE

`GetAdditionalDamageBehaviour` a **DEUX** consommateurs, pas un, et c'est la MESURE qui l'a impose :
un premier port n'ayant cable que le cleave laissait `adeptMorvenn` a **1565 PV** de moins que le
natif sur la cible PRIMAIRE, dans une geometrie ou son cleave n'avait AUCUNE cible (cardinal 0).
La ventilation par COUP (events natifs) montrait `787, 969` (les 2 coups d'ARME) **puis** `502, 506,
557` -- trois coups de plus sur la cible primaire, aux bornes de `RighteousRepugnance`.

    <X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour(abilityState):     # vslot 0x4a8
        return IdunBattleLogic.Entities.DSLBehaviors$$If(
                   <cond>, GetAdditionalDamageBehaviour(abilityState, Target@0x60), null)

`ALoki_NormalAttackAbility$$ExecuteNormalAttack` appelle ce vslot et passe son resultat en 5e
argument a `$$GetAttackDamageBehaviour` : le fold est donc compose DANS l'attaque primaire, et
s'execute APRES ses coups d'arme, dans le MEME `ExecuteAtomic(0x3d)`.

| ability | `$$GetCustomNormalAttackBehaviour` | condition |
|---|---|---|
| `RighteousRepugnance` | **oui** | `<DSLTriggers+0x18>` = **IsMeleePosition** |
| `Boltstorm` | **oui** | `DSLTriggers$$IsRangedPosition` = `op_LogicalNot(<+0x18>)` |
| `Fealty`, `TalonOfHorus` | **ABSENT** (le symbole n'existe pas) | -- |

`<DSLTriggers+0x18>` est nomme par le corps TRIVIAL de `IdunBattleLogic.Entities.DSLTriggers$$
IsRangedPosition`, litteralement `IdunBattle.DSL.AbilityTrigger$$op_LogicalNot(this+0x18)` : le
slot est donc `IsMeleePosition`, et son `ShouldTrigger` invoque le slot 9 d'`IBattleQuery`
(`IdunBattle.Core.Services.BattleQuery$$AreUnitsInMelee`) -- le foyer `services.battle_query.
are_tiles_adjacent` cote port. Identification deja etablie et documentee par #389
(`entities/triggers.py`, appariement FORCE des deux classes que `DSLTriggers$$InitializeShared`
alloue sans allocateur nomme).

⇒ **L'asymetrie de #446-r3b est CONFIRMEE, et sa cause est NOMMEE** : ce n'est pas « la prediction
attribue ce que le combat ne fait pas », c'est que `Boltstorm` et `RighteousRepugnance` ont un
SECOND artefact que `Fealty` et `TalonOfHorus` n'ont pas -- et la prediction
(`$$GetAdditionalDamagePrediction`, portee par `playbook/prediction/normal_attack.py`) est le
mirror DE CE SECOND ARTEFACT, pas du cleave. Le texte i2 dit exactement la meme chose :
`RighteousRepugnance` porte la clause « **to the target** and to all enemy units adjacent to both »
(les DEUX volets), `TalonOfHorus` ne porte que le second.

⚠ Les DEUX gates sont DISTINCTES et il ne faut pas les confondre : le CLEAVE est gate par
`attackWeapon.IsMelee` (l'ARME choisie, dans `$$ExecuteBehaviour`), le FOLD PRIMAIRE par
`IsMeleePosition` (la GEOMETRIE, dans le `If` du behaviour). Elles coincident dans le regime
nominal, mais le fold primaire vit au rang de `ExecuteNormalAttack` -- donc il s'applique AUSSI
dans la branche SANS cleave (un `Boltstorm` en melee ne cleave pas ET ne folde pas ; un
`RighteousRepugnance` a distance non plus).

## LA GATE N'EST PAS LA MEME POUR LES QUATRE -- lue, ability par ability

| ability | branche qui CLEAVE | l'autre branche |
|---|---|---|
| `Fealty` | `IsMelee != 0` | `ALoki_NormalAttackAbility$$ExecuteBehaviour` |
| `RighteousRepugnance` | `IsMelee != 0` | `ALoki_NormalAttackAbility$$ExecuteBehaviour` |
| `TalonOfHorus` | `IsMelee != 0` | `ALoki_NormalAttackAbility$$ExecuteBehaviour` |
| **`Boltstorm`** | **`IsMelee == 0`** | InformWeapon + ExecuteNormalAttack + ExecuteTriggerAbilities INLINE |

C'est la MEME asymetrie que celle deja portee cote DECISION (`Boltstorm_NormalAttackAbility$$
PredictAttack` gate `!IsMelee`, `RighteousRepugnance_NormalAttackAbility$$PredictAttack` gate
`IsMelee`), et elle interdit de porter les quatre « par analogie » : un `Boltstorm` gate MELEE ne
cleaverait JAMAIS (son porteur `templAggressor` tire) et un `Fealty` gate RANGED non plus.

## LES QUATRE SELECTEURS SONT DISTINCTS -- lus un par un, jamais generalises

Carte `DSLSelectors` (etablie par le port, deux voies independantes -- cf.
`runner/abilities/admec.py` et `entities/selectors/accessors.py`) :
`+0x30 Owner · +0x40 Actor · +0x48 Caster · +0x50 CasterTile · +0x58 CasterTiles · +0x60 Target ·
+0x78 TargetTiles`.

    FealtyAbility$$GetAdditionalTargets(dsl) =
          AdjacentEnemies(Caster@0x48, CasterTiles@0x58, unique)
        & AdjacentFriends(Target@0x60,  TargetTiles@0x78, unique)
        - Target@0x60                                            <-- le `op_Subtraction` EXPLICITE

    TalonOfHorusAbility$$GetAdditionalTargets(dsl) =
          AdjacentEnemies(Caster@0x48, CasterTile@0x50, unique)
        & AdjacentFriends(Target@0x60,  TargetTiles@0x78, unique)
                                                                 <-- AUCUN `- Target`

    RighteousRepugnanceAbility$$GetAdditionalTargets(dsl) =       <-- l'AUTRE surcharge (unite, pas tuile)
          AdjacentEnemies(Caster@0x48, unique, sel 3)
        & AdjacentUnits (Target@0x60,  unique, sel 3)

    BoltstormAbility$$GetAdditionalTargets(dsl, range) =
          SurroundingEnemies(Owner@0x30, range, unique, sel 3)
        & Unobscured(Owner@0x30, Enemies(Caster@0x48, AdjacentUnits(Target@0x60, unique, sel 3)))

Les deux surcharges d'`IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies` sont DISTINCTES et
les xrefs tranchent laquelle chaque ability appelle (mesure, pas lecture a l'oeil) :

    AdjacentEnemies(this, unit, unitTile, unique) = Enemies(unit, Units(AdjacentTiles(unitTile)) - unitTile)
    AdjacentEnemies(this, unit, unique, selType)  = Enemies(unit, Units(AdjacentTiles(unit))     - unit)

`Fealty`/`TalonOfHorus` appellent la PREMIERE (ancre = une tuile), `RighteousRepugnance` la SECONDE
(ancre = l'unite, resolue par `GetMainTile`). Idem pour `AdjacentFriends`, dont la REFERENCE
d'equipe est le 2e argument (`Target@0x60`), PAS le caster : les « amis de la CIBLE » sont les
ennemis du caster tant que deux camps s'opposent, mais le port passe `reference=Target()`
EXPLICITEMENT -- on ne laisse pas un collapse implicite porter un argument LU.

⚠ RESIDU `#478-r1` : le port collapse `CasterTile@0x50` et `CasterTiles@0x58` sur le MEME noeud
`CasterTile()` (= l'EMPREINTE, `_feet`). Les deux slots sont bien deux instances DISTINCTES du meme
type dans `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`, et le natif choisit `+0x58`
pour `Fealty`, `+0x50` pour `TalonOfHorus`. Inerte pour toute unite MONO-hex (les deux rendent la
meme unique tuile) ; sur une unite MULTI-hex, `TalonOfHorus` serait ancre plus etroitement que ce
que le port evalue. Aucun des porteurs confrontes n'est multi-hex.

## Ce que la feuille d'attaque consomme -- et pourquoi c'est le mode BORNES

`DSLBehaviors$$AttackDamage(caster, target, amount, damageProfile, hits, source, options)` construit
un `IdunBattle.Entities.Behaviours.AttackDamageBehaviour`, que `DSLBehaviors$$Attack` enveloppe dans
un `IdunBattle.Entities.Behaviours.AttackBehaviour` -- exactement le couple que la feuille portee
`AttackWithAttackDamage` (`runner/abilities/behaviours/combat.py`) mirrore, `native_factory="attack"`.

* `amount = RandomAmount(var 0xc, var 0xd)` = les BORNES `minDmg`/`maxDmg` -> mode BORNES
  (`ability_attack_params` -> `AttackDamageOperation.execute_ability_attack`), PAS le mode `amount` ;
* `hits = Direct(GetNumberConstant(0x2f))` = `nrOfHits` (= 3 pour les quatre au gameconfig courant) ;
* `profile = GetDamageProfile()` = `constants.damageProfile` de la config ;
* `options` est une struct ZEROEE (`local_88..local_68 = 0`) -> `HasValue = 0` : ni `alwaysOverkilled`
  (octet +4), ni `alwaysCrit` (+5), ni le drapeau d'attaque NORMALE (+6). Le port laisse donc
  `force_overkill=False`, `force_crit=False` et reste en mode bornes -- aucun `amount_spread_pct`.

**La CONFIG lue est celle du PASSIF, au niveau du PASSIF.** `this@+0x60` est l'`AbilityConfiguration`
de l'instance, et `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` monte
l'attaque normale substituee avec le `triggeredAbilityState` (`if (fromPassive.HasValue) { type =
fromPassive.Value; state = triggeredAbilityState; }`) -- d'ou `ability_id = <le passif>` et
`level_slot="passive"`, exactement comme le fait deja le mold de PREDICTION
(`get_additional_damage_prediction`, qui lit `ability_var(<passif>, "minDmg", ...)`).

## Ordre d'execution, et ou le port l'insere

`Execute<X>` place le cleave APRES `ExecuteNormalAttack` (donc apres le `FinishAttack`/`On(9)` de
l'attaque primaire) et AVANT `ExecuteTriggerAbilities` (`On(0x26)`). Le port l'insere au meme rang
dans `DamageHandler.visit_AttackUnitMessage` : entre `AttackDamageOperation.execute` et
`after_hit_normal_attack`.

Le sélecteur est un ARBRE PARESSEUX cote natif : `GetAdditionalTargets` ne fait que le CONSTRUIRE,
et c'est le `Foreach` (sous `ExecuteAtomic`) qui l'EVALUE -- donc APRES l'attaque primaire, sur
l'etat DEJA mute (une cible additionnelle tuee par la primaire n'est plus la). Le port evalue de
meme, au moment du `Foreach`.

⚠ L'ordre de frappe est celui du SELECTEUR, pas un tri : le natif enveloppe chaque cible dans son
PROPRE `AttackBehaviour` via `Foreach`, donc l'`OrderBy(b__5_0)` d'`AttackBehaviour$$Execute` (qui
ne trie que quand UN SEUL behaviour porte N cibles) ne s'applique PAS ici. Le port utilise donc
`Foreach(sel, AttackWithAttackDamage(Subject(), ...))` et surtout PAS `multi=True`, qui trierait
par id et deplacerait la consommation RNG des que le cleave touche 2 cibles ou plus.

## Degradations, toutes nommees

* `weapon == null` : le natif rend `0` sans rien executer. Cote port, `AttackDamageOperation.execute`
  rend `None` dans ce regime et l'appelant ne demande pas le cleave -- meme resultat observable.
* Le porteur ne substitue pas son attaque normale (`substitutes_normal_attack` faux) -> aucun cleave.
* Cible primaire absente -> aucun cleave (le selecteur ancre sur `Target@0x60`).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ....dsl.base import Const, TargetsSelector
from ....dsl.effects import ExecutionContext
from ....entities.behaviours import AtomicGroup, Foreach
from ....entities.selectors import (AdjacentEnemies, AdjacentFriends, AdjacentUnits, And, Caster,
                                    CasterTile, Enemies, Sub, Subject, SurroundingEnemies,
                                    Target, TargetTile, Unobscured)
from ..behaviours import AttackWithAttackDamage, entities_from_state

if TYPE_CHECKING:
    from ...state import State


# ---------------------------------------------------------------- les quatre arbres de ciblage

def fealty_additional_targets():
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FealtyAbility$$GetAdditionalTargets`
    -- MIRROR 1:1 :

        ( AdjacentEnemies(Caster@0x48, CasterTiles@0x58, unique)
        & AdjacentFriends(Target@0x60,  TargetTiles@0x78, unique) )  op_Subtraction  Target@0x60

    Le `- Target` final est un no-op geometrique tant que la cible est MONO-hex (`AdjacentFriends`
    ancre sur l'empreinte de la cible et `_within` exclut deja son centre) ; il ne mord que si la
    cible occupe une tuile ADJACENTE a sa propre main tile. On le porte quand meme : c'est ce que le
    natif ECRIT, et c'est la SEULE difference d'arbre avec `TalonOfHorus`."""
    return Sub(And(AdjacentEnemies(CasterTile(), Const(1)),
                   AdjacentFriends(TargetTile(), Const(1), reference=Target())),
               Target())


def talon_of_horus_additional_targets():
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TalonOfHorusAbility$$GetAdditionalTargets`
    -- MIRROR 1:1 :

        AdjacentEnemies(Caster@0x48, CasterTile@0x50, unique)
      & AdjacentFriends(Target@0x60,  TargetTiles@0x78, unique)

    AUCUN `op_Subtraction` final -- et le texte i2 dit la meme chose : « he also deals [...] to all
    enemies adjacent to both the target of the attack and to Abaddon », sans clause sur la cible."""
    return And(AdjacentEnemies(CasterTile(), Const(1)),
               AdjacentFriends(TargetTile(), Const(1), reference=Target()))


def righteous_repugnance_additional_targets():
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RighteousRepugnanceAbility$$GetAdditionalTargets`
    -- MIRROR 1:1, et c'est l'AUTRE surcharge des primitives (ancre = l'UNITE, pas une tuile) :

        AdjacentEnemies(Caster@0x48, unique, selType 3)
      & AdjacentUnits (Target@0x60,  unique, selType 3)

    MEME arbre que celui deja porte cote DECISION par
    `engine/playbook/righteous_repugnance.py::count_additional_targets` -- un seul artefact natif,
    deux faces, et c'est ce qui rend le terme d'utilite exactement egal a ce que le combat frappe."""
    return And(AdjacentEnemies(Caster(), Const(1)), AdjacentUnits(Target(), Const(1)))


class OwnerSlot(TargetsSelector):
    """`<DSLSelectors+0x30>` = **Owner**, LITTERALEMENT -- sans le repli sur le caster.

    Le noeud partage `entities/selectors/accessors.py::Owner` rend `ctx.owner or ctx.caster`, et ce
    repli est documente comme EXACT pour une TRIGGERED-ability (`Owner == Caster == le porteur`,
    `BaseTriggeredAbility$$Execute`). Il ne l'est PAS ici : `Boltstorm_NormalAttackAbility` est une
    ability ACTIVE, et l'`AbilityEntities` que le port construit pour une attaque normale
    (`entities_from_state`) ne renseigne PAS `owner`.

    MESURE qui l'impose (`probe_478 --regime boltstorm`, `templAggressor` a distance 2 de la cible,
    DEUX ennemis adjacents a la cible, dans la portee et non obscurcis -- donc les trois gates du
    selecteur satisfaites) : le natif ne frappe **AUCUNE** cible additionnelle, la ou le MEME
    montage fait cleaver `Fealty` et `TalonOfHorus` (qui, eux, ancrent sur `Caster@0x48`). Avec le
    repli, le port en frappait DEUX -- une regression de `+2380 PV` qu'aucun test n'aurait vue.

    ⚠ Ce noeud DIT ce qu'il ne sait pas : il mirroir le slot, il n'explique pas pourquoi le natif le
    laisse vide sur cette voie. Le volet CLEAVE de `Boltstorm` reste donc **NON CONFRONTE**
    (residu `#478-r4`) : il est cable, mais son selecteur ne rend rien tant que `owner` n'est pas
    threade, exactement comme le natif observe. Le jour ou une voie d'appel renseignera `owner`,
    il partira -- et il faudra le re-confronter AVANT de s'en rejouir."""
    def select(self, ctx):
        return getattr(ctx, "owner", None)


def boltstorm_additional_targets(weapon_range: int):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BoltstormAbility$$GetAdditionalTargets(dsl, range)`
    -- MIRROR 1:1 :

        SurroundingEnemies(Owner@0x30, range, unique, selType 3)
      & Unobscured(Owner@0x30, Enemies(Caster@0x48, AdjacentUnits(Target@0x60, unique, selType 3)))

    `range` = `Direct(attackWeapon.Range.Value)` -- la portee de l'ARME CHOISIE par
    `ALoki_NormalAttackAbility$$FindAttackWeapon`, capturee au moment du cast (pas une variable
    d'ability). C'est le MEME arbre, au volet `+ Target@0x60` pres, que le `$$GetAllTargets` porte
    cote DECISION (`engine/playbook/boltstorm.py::count_all_targets`) : le playbook compte la cible
    primaire, le combat ne la re-frappe pas.

    `SurroundingEnemies` est ici la surcharge 4-args : `Owner@0x30` sert de centre ET de reference
    d'equipe. L'ancre est `OwnerSlot()` -- le slot LITTERAL, **sans** le repli sur le caster du
    noeud partage `Owner()` : cf. sa docstring, c'est une mesure qui l'impose, pas un scrupule.

    ⚠ L'ORDRE DES ARGUMENTS DU PORT EST L'INVERSE DE CELUI DU NATIF : `DSLFactory$$Unobscured(from,
    source)` mais `Unobscured(source, from_ref=...)` cote port. Ecrit dans l'ordre natif, le noeud
    rend le CASTER au lieu des cibles -- mesure : `Unobscured(Owner(), Enemies(...))` rendait
    `['templAggressor']`, donc une intersection VIDE, donc « zero cible additionnelle ». Et cet
    accord-la avec le natif (qui rend zero pour une AUTRE raison dans ce montage) ne prouvait
    RIEN : c'est le regime degenere par excellence."""
    return And(SurroundingEnemies(OwnerSlot(), Const(int(weapon_range)), reference=OwnerSlot()),
               Unobscured(Enemies(AdjacentUnits(Target(), Const(1))), OwnerSlot()))


# ---------------------------------------------------------------- la table de dispatch

class _Cleave:
    """Une entree de la famille : le passif qui SUBSTITUE l'attaque normale, les DEUX gates lues au
    decompile, et le constructeur de l'arbre de cibles additionnelles.

    `cleaves_when_melee` est la gate `IdunShared.Battle.WeaponProfile$$get_IsMelee` de
    `<X>_NormalAttackAbility$$ExecuteBehaviour`, LUE ability par ability (cf. l'en-tete : elle est
    INVERSEE pour `Boltstorm`). `needs_weapon_range` dit si l'arbre consomme la portee de l'arme
    choisie -- seul `Boltstorm` le fait.

    `primary_fold_when_melee_position` est la condition du `If` de
    `<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour` : `True` = `<DSLTriggers+0x18>`
    (`IsMeleePosition`), `False` = `DSLTriggers$$IsRangedPosition`, **`None` = le symbole n'existe
    pas pour cette ability** (donc AUCUN fold sur la cible primaire -- `Fealty`, `TalonOfHorus`).
    `None` et `False` sont deux etats DISTINCTS : le second folde a distance."""
    __slots__ = ("passive", "cleaves_when_melee", "build", "needs_weapon_range",
                 "primary_fold_when_melee_position")

    def __init__(self, passive: str, cleaves_when_melee: bool, build,
                 needs_weapon_range: bool = False,
                 primary_fold_when_melee_position: "Optional[bool]" = None):
        self.passive = passive
        self.cleaves_when_melee = bool(cleaves_when_melee)
        self.build = build
        self.needs_weapon_range = bool(needs_weapon_range)
        self.primary_fold_when_melee_position = primary_fold_when_melee_position


#: Les QUATRE `<X>_NormalAttackAbility` qui portent `$$GetAdditionalTargetsAttackBehavior`. La cle
#: est le PASSIF (`TriggeredAbilityType`), c'est-a-dire la cle de la cascade
#: `UnitFactory$$AddNormalAttackAbility` -- la MEME que celle de
#: `engine.services.custom_normal_attack.CUSTOM_NORMAL_ATTACK_BY_PASSIVE`, et le MEME substrat
#: d'ENTITE (`BC.Units[].PassiveAbilities`), sans quoi la face COMBAT et la face DECISION
#: decideraient de deux cascades differentes (#419-r1-tr14-r5).
#:
#: La liste est CLOSE, et ce n'est pas une lecture par affinite de nom : `<X>_NormalAttackAbility$$
#: GetAdditionalTargetsAttackBehavior` n'existe que pour ces quatre-la dans la table de symboles du
#: build, plus `CalibaniteGreatsword_NormalAttackAdditionalDamageAbility$$GetAdditionalTargets
#: AttackBehavior` -- qui est une TRIGGERED (`Abilities.Triggered.Loki`), pas une attaque normale
#: substituee, et n'entre donc pas dans cette cascade (residu `#478-r2`).
NORMAL_ATTACK_CLEAVES: dict = {
    # `$$GetCustomNormalAttackBehaviour` N'EXISTE PAS pour ces deux-la -> aucun fold sur la cible
    # primaire (`primary_fold_when_melee_position=None`). C'est l'asymetrie attestee par #446-r3b,
    # et sa CAUSE : un symbole absent, pas un oubli.
    "Fealty": _Cleave("Fealty", True, fealty_additional_targets),
    "TalonOfHorus": _Cleave("TalonOfHorus", True, talon_of_horus_additional_targets),
    "RighteousRepugnance": _Cleave("RighteousRepugnance", True,
                                   righteous_repugnance_additional_targets,
                                   primary_fold_when_melee_position=True),
    # ⚠ gate INVERSEE des DEUX cotes, lue au decompile : `Boltstorm_NormalAttackAbility$$
    # ExecuteBehaviour` route vers `$$ExecuteBoltstorm` sur `IsMelee == 0` (sa branche MELEE inline
    # l'attaque normale SANS cleave), et son `$$GetCustomNormalAttackBehaviour` gate sur
    # `DSLTriggers$$IsRangedPosition`.
    "Boltstorm": _Cleave("Boltstorm", False, boltstorm_additional_targets,
                         needs_weapon_range=True, primary_fold_when_melee_position=False),
}


def cleave_for(passive_abilities, active_abilities=None, visual_id=None, traits=None,
               config_active_abilities=None) -> "Optional[_Cleave]":
    """L'entree de `NORMAL_ATTACK_CLEAVES` que la CASCADE native attribue a cette unite, ou `None`.

    Delegue a `engine.services.custom_normal_attack.substitutes_normal_attack` -- le FOYER de la
    cascade `UnitFactory$$AddNormalAttackAbility` (voie PASSIVE, puis voie ACTIVE, puis branche
    trait `Boss`, puis garde du repli generique). Passer par lui, plutot que par un
    `passive in passives`, est ce qui garantit que le cleave part exactement quand l'attaque normale
    CONCRETE est montee : une unite qui porte `Fealty` DERRIERE un autre passif substituant recoit
    l'attaque normale de l'AUTRE, et ne doit donc pas cleaver."""
    from ....services.custom_normal_attack import substitutes_normal_attack
    for name, entry in NORMAL_ATTACK_CLEAVES.items():
        if substitutes_normal_attack(name, passive_abilities=passive_abilities,
                                     visual_id=visual_id, active_abilities=active_abilities,
                                     traits=traits,
                                     config_active_abilities=config_active_abilities):
            return entry
    return None


# ---------------------------------------------------------------- l'execution

def _attack_damage_leaf(entry: "_Cleave", target_sel, is_melee: bool):
    """La feuille commune aux DEUX volets : `<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour`
    -> `DSLBehaviors$$AttackDamage(caster, target, RandomAmount(var 0xc, var 0xd),
    Direct(GetDamageProfile()), Direct(GetNumberConstant(0x2f)), source, options = ZEROEE)`.

    Un SEUL artefact natif, un SEUL port : le cleave l'appelle avec la cible courante du `Foreach`
    (`Subject()`), le fold primaire avec `Target@0x60` (`Target()`).

    `is_melee` = la nature de l'arme CHOISIE (`FindAttackWeapon(...).IsMelee`), threadee telle
    quelle : c'est elle qui pilote `ExtraPierceMelee` vs `ExtraPierceRanged` dans `profile_pierce`.
    On ne la re-derive pas d'une adjacence."""
    profile = ((GC.ability(entry.passive) or {}).get("constants") or {}).get("damageProfile") or ""
    return AttackWithAttackDamage(
        target_sel, entry.passive, profile, is_melee=bool(is_melee),
        # `GetVariableForLevel(0xc/0xd)` + `GetNumberConstant(0x2f)` = les cles par defaut de
        # `ability_attack_params` ; le NIVEAU vient du slot PASSIF (l'attaque normale substituee est
        # montee avec le `triggeredAbilityState`, cf. l'en-tete).
        level_slot="passive",
        # `AbilityOrEffect.op_Implicit(this)` -- le natif thread la MEME source sur l'attaque
        # PRIMAIRE (`GetAttackDamageBehaviour`) et sur ces deux volets. La voie normale du port
        # thread le marqueur de kind `0x3f5` sur la primaire (`_normal_attack_kind`) : on thread le
        # MEME ici, pour que tous les volets d'un meme cast portent le meme contexte, comme au natif.
        ability_type=_normal_attack_kind(),
        # `options` = struct ZEROEE au call-site -> ni `alwaysOverkilled` (+4) ni `alwaysCrit` (+5).
        force_overkill=False, force_crit=False,
        # UNE cible resolue par appel (le `Foreach` pour le cleave, `Target` pour le fold) : surtout
        # PAS `multi=True`, qui trierait par id (l'`OrderBy` d'`AttackBehaviour$$Execute` ne
        # s'applique que quand UN behaviour porte N cibles -- ce n'est pas la forme d'ici).
        multi=False)


def primary_fold_tree(entry: "_Cleave", is_melee: bool):
    """`<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour` = `If(<cond>,
    GetAdditionalDamageBehaviour(abilityState, Target@0x60))`.

    Le port n'enveloppe PAS la feuille dans un noeud `If` : la condition
    (`IsMeleePosition` / `IsRangedPosition`) est evaluee IMPERATIVEMENT par l'appelant, parce que
    son substrat natif est un slot d'`IBattleQuery` (`AreUnitsInMelee`) et non un predicat du DSL
    porte. Meme frontiere que partout ailleurs : le sous-arbre reste declaratif, le predicat
    runner-couple est impératif."""
    return _attack_damage_leaf(entry, Target(), is_melee)


def cleave_tree(entry: "_Cleave", is_melee: bool, weapon_range: Optional[int] = None):
    """`ExecuteAtomic( Foreach(sel, t => Attack(caster, t, AttackDamage(...))), 0x2a )` -- MIRROR de
    la queue de `<X>_NormalAttackAbility$$Execute<X>`.

    `AtomicGroup` = `AActiveAbility$$ExecuteAtomic` (pass-through d'execution cote port, RE #201).
    `Foreach` = `DSLBehaviors$$Foreach` : ordre du SELECTEUR, aucun tri (cf. en-tete).
    La feuille est `AttackWithAttackDamage(Subject(), <passif>, <profil>, ...)` en mode BORNES --
    c'est le couple `AttackBehaviour` + `AttackDamageBehaviour` que le natif construit.

    `is_melee` : cf. `_attack_damage_leaf`."""
    sel = entry.build(int(weapon_range or 0)) if entry.needs_weapon_range else entry.build()
    return AtomicGroup(Foreach(sel, _attack_damage_leaf(entry, Subject(), is_melee)))


def _normal_attack_kind() -> int:
    """`AbilityOrEffect(0x3f5)` -- import PARESSEUX, meme raison de cycle que
    `operations/damage_ops/_channel.py`."""
    from ..attack_type import NORMAL_ATTACK_KIND
    return NORMAL_ATTACK_KIND


def selected_weapon_range(state: "State", caster_id: int, target_id: Optional[int],
                          ctx) -> Optional[int]:
    """`attackWeapon.Range.Value` -- la portee de l'arme que
    `ALoki_NormalAttackAbility$$FindAttackWeapon` a choisie pour CE cast, seule consommee par
    `BoltstormAbility$$GetAdditionalTargets`.

    On la relit par le MEME service et avec le MEME argument `dist` que la selection d'arme de
    l'attaque primaire (`damage_ops/normal.py` : `are_tiles_adjacent(...) ? 1 : 2`), pour qu'il n'y
    ait qu'UNE regle de selection d'arme par cast -- le natif, lui, appelle `FindAttackWeapon` une
    seule fois et passe l'arme.

    `None` si la position d'un des deux manque ou si aucune arme n'est resolue (le natif serait
    sorti sur `weapon == null` bien avant)."""
    from ...components import PositionComponent
    from ...damage_model import select_weapon
    from ....services.battle_query import are_tiles_adjacent
    if target_id is None or ctx is None:
        return None
    ae = state.get_entity(int(caster_id))
    te = state.get_entity(int(target_id))
    ap = ae.get_component(PositionComponent) if ae is not None else None
    tp = te.get_component(PositionComponent) if te is not None else None
    dist = None
    if ap is not None and tp is not None:
        dist = 1 if are_tiles_adjacent((ap.col, ap.row), (tp.col, tp.row), state.board) else 2
    w = select_weapon(ctx, dist)
    if not w:
        return None
    return int(w.get("Range") or 0)


def is_melee_position(state: "State", caster_id: int, target_id: Optional[int]) -> bool:
    """`<DSLTriggers+0x18>` = `IdunBattle.Entities.Triggers.IsMeleePositionAbilityTrigger`, dont le
    `ShouldTrigger` invoque le slot 9 d'`IBattleQuery` -- `IdunBattle.Core.Services.BattleQuery$$
    AreUnitsInMelee`, dont le foyer porte est `services.battle_query.are_tiles_adjacent` (adjacence
    HEX + porte d'elevation, PAS Chebyshev).

    Position d'un des deux inconnue -> `False` : le natif deref sans garde, on ne mirroir pas une
    levee et l'absence de position ne peut pas valoir « au contact »."""
    from ...components import PositionComponent
    from ....services.battle_query import are_tiles_adjacent
    if target_id is None:
        return False
    ae = state.get_entity(int(caster_id))
    te = state.get_entity(int(target_id))
    ap = ae.get_component(PositionComponent) if ae is not None else None
    tp = te.get_component(PositionComponent) if te is not None else None
    if ap is None or tp is None:
        return False
    return bool(are_tiles_adjacent((ap.col, ap.row), (tp.col, tp.row), state.board))


def execute_additional_targets_attacks(state: "State", caster_id: int, target_id: Optional[int],
                                       entry: "_Cleave", is_melee: bool,
                                       weapon_range: Optional[int] = None) -> dict:
    """Joue les DEUX volets, DANS L'ORDRE NATIF, et rend
    `{"primary_fold": {...}|None, "additional_targets": [{"target": id, "attack": {...}}, ...]}`.

    ORDRE, mesure a l'appui (events natifs d'`adeptMorvenn`, `787, 969 | 502, 506, 557 | 614, 572,
    634`) :

      1. les coups d'ARME de l'attaque primaire -- deja joues par l'appelant
         (`AttackDamageOperation.execute`) ;
      2. le FOLD sur la cible PRIMAIRE (`$$GetCustomNormalAttackBehaviour`, compose DANS
         `ExecuteNormalAttack` donc dans le meme `ExecuteAtomic(0x3d)`), gate par
         `IsMeleePosition` / `IsRangedPosition` ;
      3. le CLEAVE (`Execute<X>` -> `Foreach` sous `ExecuteAtomic(0x2a)`), gate par
         `attackWeapon.IsMelee`.

    Les deux volets ont des gates DISTINCTES et l'un peut partir sans l'autre : c'est pourquoi ils
    sont testes separement et non par un seul `if`. Aucun des deux ne part sans cible primaire.

    ⚠ L'ORDRE compte au-dela de l'affichage : chaque coup consomme le `state.rng`. Inverser les
    deux volets donnerait les BONS montants sur les MAUVAISES cibles -- exactement ce qu'un premier
    port a produit (le cleave d'`adeptMorvenn` recevait `502, 506, 557`, les rolls que le natif
    applique a la cible PRIMAIRE)."""
    out = {"primary_fold": None, "additional_targets": []}
    if target_id is None:
        return out
    ectx = ExecutionContext(state=state, rng=state.rng)
    entities = entities_from_state(state, caster_id, target_id)
    if entry.primary_fold_when_melee_position is not None:
        if is_melee_position(state, caster_id, target_id) == entry.primary_fold_when_melee_position:
            primary_fold_tree(entry, is_melee).execute(entities, ectx)
            hit = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
            if hit is not None:
                out["primary_fold"] = {"target": hit.get("target"), "attack": hit.get("attack")}
    seen = len(ectx.emitted)
    if bool(is_melee) == entry.cleaves_when_melee:
        cleave_tree(entry, is_melee, weapon_range).execute(entities, ectx)
        out["additional_targets"] = [{"target": p.get("target"), "attack": p.get("attack")}
                                     for n, p in ectx.emitted[seen:]
                                     if n == "AttackWithAttackDamage"]
    return out


__all__ = ["NORMAL_ATTACK_CLEAVES", "cleave_for", "cleave_tree", "primary_fold_tree",
           "selected_weapon_range", "is_melee_position",
           "execute_additional_targets_attacks", "fealty_additional_targets",
           "talon_of_horus_additional_targets", "righteous_repugnance_additional_targets",
           "boltstorm_additional_targets"]
