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

    <X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour(abilityState):     # vslot 0x4e8
        return IdunBattleLogic.Entities.DSLBehaviors$$If(
                   <cond>, GetAdditionalDamageBehaviour(abilityState, Target@0x60), null)

⚠ #1050-r1 -- LE VSLOT ECRIT ICI ETAIT FAUX, ET CE N'EST PAS UNE COQUILLE INERTE. `0x4a8` est
`$$GetTarget`, le SELECTEUR DE CIBLES que `ALoki_NormalAttackAbility$$ExecuteNormalAttack` appelle
en tete et passe en 5e argument a `$$GetAttackDamageBehaviour` ; le FOLD est `0x4e8`, appele DANS
`$$GetAttackDamageBehaviour` (les deux sont LUS au decompile de ces deux fonctions, et
`AncientFury_NormalAttackAbility$$GetTargets` -- qui n'est qu'un `return this.vslot(0x4a8)()` --
apparie le slot a son unique surcharge nommee). La confusion masquait le fait que le 5e argument
n'est PAS la cible du message mais un SELECTEUR : c'est ce slot-la qu'`AncientFury` surcharge pour
elargir son attaque normale (cf. `ancient_fury.py`). La meme phrase fausse vivait dans
`operations/damage.py` ; elle y est corrigee.

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

from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.behaviours import AtomicGroup, Foreach
from ....entities.selectors.accessors import CasterTile, Owner, Subject, Target, TargetTile
from ....entities.selectors.tiles import Caster
from ....entities.selectors.units import (
    AdjacentEnemies, AdjacentFriends, AdjacentUnits, And, Enemies, Sub, SurroundingEnemies,
    Unobscured
)
from ..behaviours.combat import AttackWithAttackDamage
from ..behaviours.context import entities_from_state
from ....services.battle_query import are_tiles_adjacent
from ....services.custom_normal_attack import substitutes_normal_attack
from ...components import PositionComponent
from ...damage_model import select_weapon
from ..attack_type import NORMAL_ATTACK_KIND
from ....entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve
#: #585-r1, build `rnca9r7q6c`, littéral par littéral (JAMAIS par symetrie : deux call-sites
#: du releve passent `Any` parce que leur source est un ensemble de MORTS).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


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
    # #585-r1 -- ⚠ LES DEUX LITTERAUX SONT IMPLICITES : `$$GetAdditionalTargets` emprunte la
    # VARIANTE B des DEUX primitives -- `AdjacentEnemies(gs, gs@0x48, gs@0x58, unique: 1)` et
    # `AdjacentFriends(gs, gs@0x60, gs@0x78, unique: 1)` -- et c'est cette variante-la qui code `3`
    # EN DUR. Aucun `3` n'apparait dans le corps ; il se lit a la XREF ENTRANTE. Lire le 4e argument
    # comme un selectionType donnerait `1` = `OnlyAlive`, qui n'ecarte PAS `Untargetable`.
    return Sub(And(AdjacentEnemies(CasterTile(), Const(1), selection_type=SELECTION),
                   AdjacentFriends(TargetTile(), Const(1), reference=Target(),
                                   selection_type=SELECTION)),
               Target())


def talon_of_horus_additional_targets():
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TalonOfHorusAbility$$GetAdditionalTargets`
    -- MIRROR 1:1 :

        AdjacentEnemies(Caster@0x48, CasterTile@0x50, unique)
      & AdjacentFriends(Target@0x60,  TargetTiles@0x78, unique)

    AUCUN `op_Subtraction` final -- et le texte i2 dit la meme chose : « he also deals [...] to all
    enemies adjacent to both the target of the attack and to Abaddon », sans clause sur la cible."""
    # #585-r1 -- ⚠ LES DEUX LITTERAUX SONT IMPLICITES, comme pour `Fealty` : VARIANTE B des deux
    # primitives (`AdjacentEnemies(gs, gs@0x48, gs@0x50, unique: 1)`,
    # `AdjacentFriends(gs, gs@0x60, gs@0x78, unique: 1)`), donc `3` code EN DUR, lisible seulement
    # a la XREF ENTRANTE.
    return And(AdjacentEnemies(CasterTile(), Const(1), selection_type=SELECTION),
               AdjacentFriends(TargetTile(), Const(1), reference=Target(),
                               selection_type=SELECTION))


def righteous_repugnance_additional_targets():
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RighteousRepugnanceAbility$$GetAdditionalTargets`
    -- MIRROR 1:1, et c'est l'AUTRE surcharge des primitives (ancre = l'UNITE, pas une tuile) :

        AdjacentEnemies(Caster@0x48, unique, selType 3)
      & AdjacentUnits (Target@0x60,  unique, selType 3)

    MEME arbre que celui deja porte cote DECISION par
    `engine/playbook/righteous_repugnance.py::count_additional_targets` -- un seul artefact natif,
    deux faces, et c'est ce qui rend le terme d'utilite exactement egal a ce que le combat frappe."""
    # #585-r1 : ici les DEUX litteraux sont EXPLICITES (`AdjacentEnemies(gs, gs@0x48, unique: 1, 3)`
    # = VARIANTE A, `AdjacentUnits(gs, gs@0x60, unique: 1, 3)`) -- c'est le contraste exact avec
    # `Fealty`/`TalonOfHorus` ci-dessus, qui empruntent la variante a `3` implicite. Deux fonctions
    # voisines, deux surcharges differentes : c'est pourquoi le tri se fait call-site par call-site.
    return And(AdjacentEnemies(Caster(), Const(1), selection_type=SELECTION),
               AdjacentUnits(Target(), Const(1), selection_type=SELECTION))


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
    d'equipe.

    ## `Owner` VAUT LE CASTER SUR CETTE VOIE -- LU, plus suppose (#478-r4)

    Le premier port de cette tranche ancrait sur un noeud `OwnerSlot` qui rendait `None`, sur
    l'hypothese « l'`AbilityEntities` d'une attaque normale ne renseigne pas `Owner` ». Cette
    hypothese est **REFUTEE par le decompile**, et la chaine se lit d'un bout a l'autre :

      * `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` construit son
        `AbilityEntities` par `IdunBattle.Operations.ActiveAbilityOperation$$GetAbilityEntities`,
        puis passe CETTE struct aux slots virtuels de l'ability (dont `ExecuteBehaviour`) ;
      * `$$GetAbilityEntities` `memset` la struct (0x128 octets) puis ecrit l'ENTITE CASTER dans
        **TROIS** slots : `+0x00`, `+0x08` et `+0x18` ;
      * les trois lecteurs nomment ces slots sans ambiguite --
        `IdunBattle.Entities.Selectors.ActorSelector$$Select` lit `+0x00`,
        `IdunBattle.Entities.Selectors.CasterSelector$$Select` lit `+0x08`,
        `IdunBattle.Entities.Selectors.OwnerSelector$$Select` lit `+0x18` (et rend une `List` VIDE
        quand il est nul -- c'est ce chemin-la, jamais pris ici, qui aurait justifie `None`).

    ⇒ pour toute ability **ACTIVE** -- et l'attaque normale en est une (`ActiveAbilityComponent.
    NormalAttackType@0x28`, cf. `damage.py`) -- `Owner == Caster == Actor`. Le noeud partage
    `entities/selectors/accessors.py::Owner` (`ctx.owner or ctx.caster`) est donc EXACT ici, pour
    la meme raison qu'il l'est sur une TRIGGERED : ce n'est pas un repli de confort, c'est ce que
    le natif ECRIT.

    ⚠ L'ORDRE DES ARGUMENTS DU PORT EST L'INVERSE DE CELUI DU NATIF : `DSLSelectors$$Unobscured(from,
    source)` mais `Unobscured(source, from_ref=...)` cote port. Ecrit dans l'ordre natif, le noeud
    rend le CASTER au lieu des cibles -- donc une intersection VIDE, donc « zero cible
    additionnelle ». Cet accord-la avec un natif qu'on croyait a zero ne prouvait RIEN : c'est le
    regime degenere par excellence, et c'est exactement ce qui avait fige le residu."""
    # #585-r1 : `AdjacentUnits(gs, gs@0x60, unique: 1, 3)`, `Enemies(gs, gs@0x48, ., 3)` puis
    # `SurroundingEnemies(gs, gs@0x30, range, unique: 1, 3)` -- les TROIS explicites, LUS dans
    # `...BoltstormAbility$$GetAdditionalTargets`.
    return And(SurroundingEnemies(Owner(), Const(int(weapon_range)), reference=Owner(),
                                  selection_type=SELECTION),
               Unobscured(Enemies(AdjacentUnits(Target(), Const(1), selection_type=SELECTION),
                                  selection_type=SELECTION), Owner()))


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
    for name, entry in NORMAL_ATTACK_CLEAVES.items():
        if substitutes_normal_attack(name, passive_abilities=passive_abilities,
                                     visual_id=visual_id, active_abilities=active_abilities,
                                     traits=traits,
                                     config_active_abilities=config_active_abilities):
            return entry
    return None


# ---------------------------------------------------------------- l'execution

def fold_inherits_attack_state() -> bool:
    """#419-r3 -- le FOLD primaire herite-t-il de l'`OngoingAttack` de l'attaque primaire ?

    Fonction de MODULE, et pas une expression inline, pour une seule raison : c'est le point de
    MUTATION des probes/cliquets : `probe_419r3_fold_attack_state.py` SUBSTITUE cet attribut de
    module (`AT.fold_inherits_attack_state = lambda: False`) et joue les DEUX regimes en une seule
    passe -- il n'y a pas de drapeau de ligne de commande a passer. La rendre
    fausse restaure exactement le port d'AVANT #419-r3 (fold sur une attaque NEUVE) -- une
    contre-epreuve qui DOIT diverger du live. Meme pattern que `crit_gate_open` pour #366-r1 et
    qu'`apply_all_modifiers` pour #131.

    VRAI est le natif : `<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour` rend un
    `If(<cond>, <AttackDamage NU>)` -- aucun `IdunBattleLogic.Entities.DSLBehaviors$$Attack` --, et
    `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` le compose dans le `Attack(...)` de
    l'attaque primaire. Le call-site pose `isOutsideAttack = false`, donc
    `IdunBattle.Operations.ADamageOperation$$GetCurrentAttackOrDefault` route sur le slot **200**
    `GetCurrentAttackOrDefault` (arite 0) et rend l'attaque EN COURS."""
    return True


def fold_emits_pre_attack() -> bool:
    """#925 -- le FOLD primaire pousse-t-il `StartAttack`, donc `On(PreAttack = 5)` ?

    FAUX est le natif, et c'est LU dans
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`,
    dont la queue est un `Attack(...)` UNIQUE qui englobe les TROIS volets :

        b1 = DSLBehaviors$$AttackDamage(caster@0x48, Target@0x60, <vslot 0x4d8>, Direct(weapon+0x10),
                                        <vslot 0x4c8>, source, options)      # les coups d'ARME
        b2 = <vslot 0x4e8>(abilityState)             # = $$GetCustomNormalAttackBehaviour = le FOLD
        b  = AbilityBehaviour$$op_BitwiseAnd(b1, b2)
        b3 = DSLBehaviors$$ExecuteAdditionalHitsWithDamageProfileType(...)
        b  = AbilityBehaviour$$op_BitwiseAnd(b, b3)
        return IdunBattleLogic.Entities.DSLBehaviors$$Attack(caster@0x48, target, b, source)

    Le FOLD est donc une feuille **NUE** -- `<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour`
    rend un `DSLBehaviors$$If(<cond>, <AttackDamage>, null)`, AUCUN `DSLBehaviors$$Attack` -- composee
    DANS l'`AttackBehaviour` que l'attaque primaire a deja ouvert. Or `StartAttack` (slot 58, LU dans
    `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`) est pousse par
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`, et c'est le SEUL emetteur sur cette
    voie : UN `Attack(...)` = UN `StartAttack` = UN `On(5)`, pour la cible primaire.

    CONTRASTE avec le CLEAVE, qui appelle la MEME feuille (`$$GetAdditionalDamageBehaviour`) mais
    l'enveloppe dans son PROPRE `IdunBattleLogic.Entities.DSLBehaviors$$Attack`
    (`<X>_NormalAttackAbility$$GetAdditionalTargetsAttackBehavior`) : lui pousse bien un `StartAttack`
    par cible additionnelle. Les DEUX volets partagent la feuille et DIFFERENT sur ce point -- c'est
    pourquoi le drapeau est un ARGUMENT de `_attack_damage_leaf` et non une constante, et c'est ce
    que le port n'exprimait pas (le defaut `is_outside_attack=True` d'`AttackWithAttackDamage` etait
    pris par les DEUX).

    CE QUE `On(5)` DECLENCHE, cote port : `SuppressiveFireAddEffectAbility` (pose `Pinned`, aucun
    tirage) et `LetTheGalaxyBurnArmAbility`, dont le `Maybe(ConfigConst(0x2a))` de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger`
    CONSOMME un `state.rng` -- un `On(5)` de trop y decale tout le flux de tirages, donc tous les
    coups qui suivent.

    Fonction de MODULE, et pas une expression inline, pour la MEME raison que
    `fold_inherits_attack_state` : c'est le point de MUTATION des probes/cliquets
    (`probe_925_fold_pre_attack.py` SUBSTITUE cet attribut de module et joue les DEUX regimes en une
    seule passe -- il n'y a pas de drapeau de ligne de commande a passer). La rendre VRAIE restaure
    exactement le port d'AVANT #925."""
    return False


def _attack_damage_leaf(entry: "_Cleave", target_sel, is_melee: bool, attack_state0=None,
                        is_outside_attack: bool = True):
    """La feuille commune aux DEUX volets : `<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour`
    -> `DSLBehaviors$$AttackDamage(caster, target, RandomAmount(var 0xc, var 0xd),
    Direct(GetDamageProfile()), Direct(GetNumberConstant(0x2f)), source, options)`.

    Un SEUL artefact natif, un SEUL port : le cleave l'appelle avec la cible courante du `Foreach`
    (`Subject()`), le fold primaire avec `Target@0x60` (`Target()`).

    ⚠ #419-r1-tr9-r4-r3 -- **ENONCE REFUTE** (RE re-conduite au build `t6dpr4k06g`). Le residu
    annoncait « la face COMBAT du fold additional-damage n'est pas portee ; aucun mirror de
    `Boltstorm_NormalAttackAbility$$GetAdditionalDamageBehaviour` / `$$ExecuteBoltstorm` ». Cette
    fonction EST ce mirror, `primary_fold_tree` celui de `$$GetCustomNormalAttackBehaviour`, et
    `execute_additional_targets_attacks` celui de `$$ExecuteBoltstorm`. Le foyer que la fiche
    nommait (`operations/additional_hits.py`) est celui du canal #179
    (`DSLBehaviors$$ExecuteAdditionalHitsWithDamageProfileType`), qui est le **`b3`** du
    `Attack(...)` -- un TROISIEME volet, FRERE du fold, jamais son foyer.
    Ce que la RE ajoute, et qui est desormais garde par
    `tests/engine/runner/test_419r1tr9r4r3_boltstorm_fold_combat_offline.py` :
      * le fold part **DEUX** fois par cast (cible PRIMAIRE sous `If(IsRangedPosition)`, puis UNE
        fois par cible ADDITIONNELLE, **sans gate de position**) ;
      * `hits = Direct(GetNumberConstant(0x2f = nrOfHits))` = **3** pour `Boltstorm`, et ces 3 coups
        **REPASSENT** par `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` -> slot 182
        d'`IBattleQuery`, parce que l'octet +3 des options (`BypassHitModifiers`) est FAUX. C'est la
        regression silencieuse la plus probable d'un port naif : `skip_hits_modifiers` doit rester
        a son defaut.

    `is_melee` = la nature de l'arme CHOISIE (`FindAttackWeapon(...).IsMelee`), threadee telle
    quelle : c'est elle qui pilote `ExtraPierceMelee` vs `ExtraPierceRanged` dans `profile_pierce`.
    On ne la re-derive pas d'une adjacence.

    `attack_state0` (#419-r3) = l'etat de l'`OngoingAttack` HERITEE, `None` si l'appelant en ouvre
    une neuve. Les DEUX volets sont ici, et ils N'ONT PAS la meme reponse -- c'est ce qui interdit
    de la poser dans cette fonction :

      * **CLEAVE** -> `<X>$$GetAdditionalTargetsAttackBehavior` enveloppe la feuille dans son PROPRE
        `IdunBattleLogic.Entities.DSLBehaviors$$Attack(caster, target, behaviour, source)`, donc
        `StartAttackOperation$$Execute` pousse un `OngoingAttack` NEUF par cible -> `None` ;
      * **FOLD** -> `<X>$$GetCustomNormalAttackBehaviour` rend `If(<cond>, <la feuille>)` SANS aucun
        `Attack(...)`, et `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` le compose entre
        l'`AttackDamage` d'ARME et `ExecuteAdditionalHitsWithDamageProfileType`, le tout DANS un seul
        `Attack(...)`. La feuille lit donc l'`OngoingAttack` de l'attaque PRIMAIRE, deja mutee par
        les coups d'arme -> l'appelant lui passe l'etat.

    Les options du call-site du fold sont un `Nullable<AttackDamageBehaviourOptions>` **NUL**
    (`hasValue = 0`), donc `GetValueOrDefault()` rend la struct zeroee : ni `alwaysOverkilled` (+4),
    ni `alwaysCrit` (+5), et surtout `isOutsideAttack` (+0) = **false**. Balayage exhaustif des 18
    call-sites : `docs/rl/case-419-r3-is-outside-attack-inexprimable.md`.

    `is_outside_attack` (#925) = la feuille est-elle emballee dans son PROPRE
    `IdunBattleLogic.Entities.DSLBehaviors$$Attack`, donc pousse-t-elle `StartAttack` -> `On(5)` ?
    CLEAVE oui (`$$GetAdditionalTargetsAttackBehavior` l'emballe), FOLD non (feuille nue composee
    dans l'`Attack(...)` de la primaire). Detail et decompile : `fold_emits_pre_attack`."""
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
        multi=False,
        attack_state0=attack_state0,     # #419-r3 : cf. docstring (None pour le CLEAVE)
        is_outside_attack=bool(is_outside_attack))   # #925 : cf. `fold_emits_pre_attack`


def primary_fold_tree(entry: "_Cleave", is_melee: bool, attack_state0=None):
    """`<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour` = `If(<cond>,
    GetAdditionalDamageBehaviour(abilityState, Target@0x60))`.

    Le port n'enveloppe PAS la feuille dans un noeud `If` : la condition
    (`IsMeleePosition` / `IsRangedPosition`) est evaluee IMPERATIVEMENT par l'appelant, parce que
    son substrat natif est un slot d'`IBattleQuery` (`AreUnitsInMelee`) et non un predicat du DSL
    porte. Meme frontiere que partout ailleurs : le sous-arbre reste declaratif, le predicat
    runner-couple est impératif.

    `attack_state0` (#419-r3) = l'etat de l'`OngoingAttack` de l'attaque PRIMAIRE en sortie de ses
    coups d'arme (`{"attack_state": ...}` du retour d'`AttackDamageOperation.execute`). Ce volet-ci
    tourne DANS le `Attack(...)` de la primaire ; le passer est ce qui rend `isOutsideAttack = false`
    exprimable cote port.

    #925 -- et le MEME fait a une SECONDE consequence, que #419-r3 n'avait pas tiree : tourner DANS
    l'`Attack(...)` de la primaire veut dire ne PAS ouvrir le sien, donc ne PAS pousser `StartAttack`,
    donc ne PAS emettre `On(PreAttack = 5)`. Le port le faisait (defaut `is_outside_attack=True`) :
    un `On(5)` de trop par cast, sur la CIBLE PRIMAIRE. Lecture : `fold_emits_pre_attack`."""
    return _attack_damage_leaf(entry, Target(), is_melee, attack_state0=attack_state0,
                               is_outside_attack=fold_emits_pre_attack())


def cleave_tree(entry: "_Cleave", is_melee: bool, weapon_range: Optional[int] = None):
    """`ExecuteAtomic( Foreach(sel, t => Attack(caster, t, AttackDamage(...))), 0x2a )` -- MIRROR de
    la queue de `<X>_NormalAttackAbility$$Execute<X>`.

    `AtomicGroup` = `AActiveAbility$$ExecuteAtomic` (pass-through d'execution cote port, RE #201).
    `Foreach` = `DSLBehaviors$$Foreach` : ordre du SELECTEUR, aucun tri (cf. en-tete).
    La feuille est `AttackWithAttackDamage(Subject(), <passif>, <profil>, ...)` en mode BORNES --
    c'est le couple `AttackBehaviour` + `AttackDamageBehaviour` que le natif construit.

    `is_melee` : cf. `_attack_damage_leaf`.

    #925 -- `is_outside_attack=True` (le defaut) est EXACT ici et ne se derive PAS du volet FOLD :
    `<X>_NormalAttackAbility$$GetAdditionalTargetsAttackBehavior` emballe la feuille dans son PROPRE
    `IdunBattleLogic.Entities.DSLBehaviors$$Attack`, donc `AttackBehaviour$$Execute` pousse
    `StartAttack` -> `On(PreAttack = 5)` par cible additionnelle."""
    sel = entry.build(int(weapon_range or 0)) if entry.needs_weapon_range else entry.build()
    return AtomicGroup(Foreach(sel, _attack_damage_leaf(entry, Subject(), is_melee,
                                                        is_outside_attack=True)))


def _normal_attack_kind() -> int:
    """`AbilityOrEffect(0x3f5)` -- import PARESSEUX, meme raison de cycle que
    `operations/damage_ops/_channel.py`."""
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
                                       weapon_range: Optional[int] = None,
                                       attack_state0=None,
                                       after_primary=None) -> dict:
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

    `after_primary` (#521-r7) = un callable JOUE ENTRE 2 et 3, sans argument. Un seul appelant :
    l'emission d'`EvaluateAbilities(0x4a = AttackInAtomicGroup)` que
    `ALoki_NormalAttackAbility$$ExecuteNormalAttack` compose par `op_BitwiseAnd` APRES
    `GetAttackDamageBehaviour` (donc apres les coups d'arme ET le fold) et AVANT que `Execute<X>`
    n'enchaine sur son `ExecuteAtomic(0x2a)`. Ce rang n'est pas decoratif : chaque coup consomme
    `state.rng`, donc jouer le vecteur du mauvais cote du cleave decalerait le flux. `None` (defaut)
    = rien entre les deux volets.

    Les deux volets ont des gates DISTINCTES et l'un peut partir sans l'autre : c'est pourquoi ils
    sont testes separement et non par un seul `if`. Aucun des deux ne part sans cible primaire.

    `attack_state0` (#419-r3) = l'etat de l'`OngoingAttack` de l'attaque primaire, transmis au SEUL
    volet FOLD : lui tourne dans le `Attack(...)` de la primaire, le CLEAVE ouvre le sien. Voir
    `_attack_damage_leaf`.

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
            primary_fold_tree(entry, is_melee,
                              attack_state0=attack_state0).execute(entities, ectx)
            hit = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
            if hit is not None:
                out["primary_fold"] = {"target": hit.get("target"), "attack": hit.get("attack")}
    if after_primary is not None:
        after_primary()                  # #521-r7 : `EvaluateAbilities(0x4a)`, cf. la docstring
    seen = len(ectx.emitted)
    if bool(is_melee) == entry.cleaves_when_melee:
        cleave_tree(entry, is_melee, weapon_range).execute(entities, ectx)
        out["additional_targets"] = [{"target": p.get("target"), "attack": p.get("attack")}
                                     for n, p in ectx.emitted[seen:]
                                     if n == "AttackWithAttackDamage"]
    return out


__all__ = ["NORMAL_ATTACK_CLEAVES", "cleave_for", "cleave_tree", "primary_fold_tree",
           "selected_weapon_range", "is_melee_position",
           "execute_additional_targets_attacks", "fold_inherits_attack_state",
           "fold_emits_pre_attack",
           "fealty_additional_targets",
           "talon_of_horus_additional_targets", "righteous_repugnance_additional_targets",
           "boltstorm_additional_targets"]
