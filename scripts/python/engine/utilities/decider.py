"""`IdunBattleLogic.AI.Utilities` — le triplet `WeightedUtility` / `UtilityBucket` /
`UtilityDefinition` et le sommateur `UtilityDecider.CalculateUtility`, mirror 1:1.

POURQUOI ce module existe (#353-r1) : jusqu'ici le port collapsait toute la chaine en UN scalaire
`utility_type: int`, parce que TOUS les call-sites deja portes passent la surcharge INT de
`IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility` (qui construit
`UtilityDefinition(utilityType)` = UN bucket, UNE `WeightedUtility`, poids 1).
`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo` est le PREMIER
call-site porte qui construit la definition A LA MAIN, avec **DEUX** `WeightedUtility` dans le meme
bucket -- le collapse n'y suffit plus.

CE QUE LE DECOMPILE DIT (`rnca9r7q6c`, lu VERBATIM ; jamais deduit du nom des types)
------------------------------------------------------------------------------------
`IdunBattleLogic.AI.Utilities.WeightedUtility$$.ctor(this, utilityType|utility, weight)` --
DEUX surcharges (l'une ecrit `this+0x10 = (int)utilityType`, l'autre `this+0x18 = utility`), MEME
queue : `this+0x20 = weight.HasValue ? weight.Value : Fix64.op_Implicit(1)`.
=> **un poids ABSENT vaut 1**, ce n'est pas une convention du port.

`IdunBattleLogic.AI.Utilities.UtilityBucket$$.ctor(this, utilities, minUtilityDifference)` --
TROIS surcharges (tableau / un `utilityType` / une `utility`), MEME queue :
`this+0x10 = utilities` et `this+0x20 = minUtilityDifference.HasValue ? value : Fix64.op_Implicit(0)`.
=> **une difference minimale ABSENTE vaut 0**.

`IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor` -- TROIS surcharges, toutes
`this+0x10 = new[]{ <bucket> }` (un tableau d'UN element).

`IdunBattleLogic.AI.Utilities.UtilityDecider$$CalculateUtility<T>` epuise
`UtilityDecider.<CalculateUtilityInSteps>d__9<T>.MoveNext` et rend son DERNIER `Current`. Le corps de
l'iterateur, remis en C# :

    total = Fix64.FromInt(0)
    arr   = bucket.Utilities                       // <bucket>+0x10
    for (i = 0; i < arr.Length; i++) {
        wu = arr[i]
        u  = wu.Utility ?? utilitiesDatabase.GetUtility(wu.UtilityType)
        r  = evaluate(case, u)                     // Func<...> du call-site (SortTilesByUtilitySelector)
        if (r == null)                    { yield return Fix64.FromInt(0); yield break; }
        if (r == <BaseUtility.statics+0x20>) { yield return <idem>; yield break; }   // 4 SENTINELLES
        if (r == <BaseUtility.statics+0x28>) { yield return <idem>; yield break; }
        if (r == <BaseUtility.statics+0x18>) { yield return <idem>; yield break; }
        if (r == <BaseUtility.statics+0x10>) { yield return <idem>; yield break; }
        total = total + r * wu.Weight              // Fix64.op_Multiply puis Fix64.op_Addition
    }
    yield return total

DEUX lectures a ne pas presumer, et c'est pour elles que ce module est ecrit :

1. **la composition est une SOMME PONDEREE**, `Sigma weight_i * u_i` -- pas une moyenne, pas un
   lexicographique, pas un max. Les deux `WeightedUtility` de `GetTileToMoveTo` sont construites
   avec un `Nullable<Fix64>` VIDE, donc **poids 1 chacune** : la somme y est nue.
2. **quatre SENTINELLES court-circuitent** la boucle (VETO / MUST-DO de `BaseUtility`). Aucune des
   utilites portees n'en rend une (`Tile(7)` comme `RammingSpeed_MostAdjacentEnemies(54)` ne
   somment que des poids BC), donc `calculate_utility` ne les modelise PAS -- RESIDU NOMME : le jour
   ou une feuille sentinelle entre au registre, c'est ICI qu'il faut la brancher, pas dans la
   feuille.

LES SENTINELLES, DESORMAIS **LUES** (#1013-r3) -- et ce qu'un `customUtility` PEUT faire
------------------------------------------------------------------------------------------
`IdunBattle.AI.Utilities.BaseUtility$$.cctor` ecrit sept champs statiques ; `FixMath.NET.Fix64$$.cctor`
donne les deux valeurs auxquelles ils renvoient (`Fix64.statics+0x10 = 0x7fffffffffffffff` =
**MaxValue**, `+0x18 = 0x8000000000000000` = **MinValue**) :

    BaseUtility.statics+0x00 = Fix64(0)                             # NEUTRE -- PAS une sentinelle
    BaseUtility.statics+0x08 = Fix64(100000)
    BaseUtility.statics+0x10 = Fix64.MaxValue                       # MUST-DO
    BaseUtility.statics+0x18 = Fix64.MinValue / (1000001/1000000)   # VETO
    BaseUtility.statics+0x20 = Fix64.MinValue                       # VETO
    BaseUtility.statics+0x28 = Fix64.MinValue / (1000002/1000000)
    BaseUtility.statics+0x30 = Fix64(-12345)

⚠ **UN `customUtility` DE CALL-SITE N'EST JAMAIS SOMME AU SCORE -- IL N'A QUE TROIS ISSUES.**
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
recoit la `UtilityDefinition` du call-site (chaine : `IdunBattle.AI.ActionGenerators.
ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` -> slot 7 du playbook ->
`ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal` -> ce corps), et,
LU verbatim :

    if (customUtility == null || customUtility.Buckets.Length == 0)  -> chemin NORMAL
    r = UtilityDecider.CalculateUtility(db, UtilityAttackCase.Base(unit, position, target, ab),
                                        customUtility.Buckets[0], evaluate)
    if (r == statics+0x18 || r == statics+0x20)  -> **Nullable VIDE** (aucune action pour ce couple)
    if (r == statics+0x10)                       -> utilite = MaxValue (MUST-DO)
    sinon                                        -> **chemin NORMAL** (la valeur est JETEE)

Consequence, et elle est STRUCTURELLE : une utilite custom qui rend un NOMBRE (et non l'une des
trois sentinelles TESTEES) **ne change RIEN** au choix de l'IA. Deux call-sites l'illustrent, en
sens inverse :
  * `IdunBattle.AI.Utilities.OnlyCertainTargetUtility` (`1101 AttemptedPossession`) yield
    `statics+0x20` = **MinValue** quand la cible n'est pas dans sa liste, `statics+0x00` = **0**
    quand elle y est -> ELIMINATION de la cible interdite, scoring NORMAL de l'autorisee. C'est
    exactement ce que le port exprime par `allowed_targets` : le residu `#590-r5` (qui declarait
    la polarite << non lisible offline >>, `BLOCAGE: capteur`) est TRANCHE HORS LIGNE, et le port
    avait RAISON ;
  * `IdunBattle.AI.Utilities.TheArdentBlade_GeminaeUtility` (`1468 TheArdentBlade`) yield `0` ou
    `+30` (`GetUtilityValue("LikesAdjacentCelestine")`) -- **jamais une sentinelle** -> son
    `customUtility` est IGNORE par le NATIF lui-meme. La premisse de `#1013-r3` (<< la Geminae
    rejouee choisit sa cible par l'utilite par DEFAUT >>, sous-entendu : contrairement au natif)
    est donc REFUTEE : le natif choisit AUSSI par l'utilite par defaut.

`min_utility_difference` n'est PAS lu par ce chemin : il sert a
`IdunBattleLogic.AI.Utilities.UtilityDecider$$Decide` (arbitrage entre ACTIONS). Il est porte quand
meme, parce qu'il fait partie de l'objet que le call-site construit et que le taire ferait croire
qu'il n'existe pas.
"""
from __future__ import annotations

from .base import BaseUtility


class WeightedUtility:
    """`IdunBattleLogic.AI.Utilities.WeightedUtility` — une utilite + son poids.

    `utility_type` (surcharge `int`) OU `utility` (surcharge objet) ; `weight=None` = le
    `Nullable<Fix64>` VIDE du natif -> **1** (`WeightedUtility$$.ctor`, queue commune aux DEUX
    surcharges)."""

    def __init__(self, utility_type: int | None = None,
                 weight: float | None = None, utility: BaseUtility | None = None):
        if (utility_type is None) == (utility is None):
            raise ValueError("WeightedUtility: exactement UN de utility_type / utility "
                             "(le natif a DEUX surcharges, jamais les deux champs a la fois)")
        self.utility_type = None if utility_type is None else int(utility_type)
        self.utility = utility
        self.weight = 1.0 if weight is None else float(weight)   # `weight ?? Fix64.FromInt(1)`


class UtilityBucket:
    """`IdunBattleLogic.AI.Utilities.UtilityBucket` — un TABLEAU de `WeightedUtility` + une
    difference minimale. `min_utility_difference=None` -> **0** (`UtilityBucket$$.ctor`).

    Les surcharges `.ctor(utilityType, ...)` / `.ctor(utility, ...)` du natif ne sont que du sucre :
    elles allouent `new[]{ new WeightedUtility(<arg>, null) }`. `from_utility_type` / `from_utility`
    les mirrorent."""

    def __init__(self, utilities: "list[WeightedUtility]",
                 min_utility_difference: float | None = None):
        self.utilities = list(utilities)
        self.min_utility_difference = (0.0 if min_utility_difference is None
                                       else float(min_utility_difference))

    @classmethod
    def from_utility_type(cls, utility_type: int,
                          min_utility_difference: float | None = None) -> "UtilityBucket":
        return cls([WeightedUtility(utility_type=utility_type)], min_utility_difference)

    @classmethod
    def from_utility(cls, utility: BaseUtility,
                     min_utility_difference: float | None = None) -> "UtilityBucket":
        return cls([WeightedUtility(utility=utility)], min_utility_difference)


class UtilityDefinition:
    """`IdunBattleLogic.AI.Utilities.UtilityDefinition` — `Buckets` = un tableau d'UN bucket dans les
    TROIS surcharges du `.ctor` natif. `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select`
    ne lit d'ailleurs que `Buckets[0]` (`definition+0x10` puis element `+0x20`, apres un
    `Length == 0 -> throw`)."""

    def __init__(self, bucket: UtilityBucket):
        self.buckets = [bucket]

    @classmethod
    def from_utility_type(cls, utility_type: int) -> "UtilityDefinition":
        """Surcharge `UtilityDefinition..ctor(UtilityType)` = `[ UtilityBucket(utilityType, null) ]`
        = `[ [ WeightedUtility(utilityType, null) ] ]` -> UNE utilite, poids 1. C'est ce que
        construit la surcharge INT de `DSLSelectors$$SortTilesByUtility`, donc TOUS les call-sites
        portes avant #353-r1."""
        return cls(UtilityBucket.from_utility_type(utility_type))

    @property
    def bucket(self) -> UtilityBucket:
        return self.buckets[0]


def calculate_utility(utilities_database, case, bucket: UtilityBucket, evaluate) -> float:
    """`IdunBattleLogic.AI.Utilities.UtilityDecider$$CalculateUtility<T>(db, case, bucket, evaluate)`
    = le dernier `Current` de `<CalculateUtilityInSteps>d__9<T>` (cf. l'en-tete du module) :

        Sigma_i  weight_i * evaluate(case, utility_i)

    `utilities_database(utility_type) -> BaseUtility | None` mirrore
    `IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility` (le `wu.Utility ?? db.GetUtility(...)`
    natif). Un type absent de la base LEVE ici, la ou le natif rendrait null puis deref -- le port
    prefere l'erreur nette au 0 silencieux (meme parti que `sort_tiles_by_utility` avant #353-r1).

    `evaluate(case, utility) -> float` = la `Func<>` que le call-site fournit ; pour
    `SortTilesByUtilitySelector` c'est
    `<>c__DisplayClass8_0.<Select>b__1(tile, u) = Sigma u.EvaluateMovementInSteps(
        new UtilityMovementCase(dc.unit, tile, null, null, dc.parent))`."""
    total = 0.0
    for wu in bucket.utilities:
        u = wu.utility
        if u is None:
            u = utilities_database(wu.utility_type)
            if u is None:
                raise KeyError("UtilityDecider.CalculateUtility: UtilityType %r hors "
                               "UtilitiesDatabase" % (wu.utility_type,))
        total += wu.weight * float(evaluate(case, u))
    return total
