"""Les DEUX effets du passif `EnmityForTheUnworthy` (`TriggeredAbilityType 0x522 = 1314`) de
`darkaCompanion` << Forcas >> (Dark Angels / Imperial) -- #948.

i2 `Abilities/EnmityForTheUnworthy_CurrentLevelDescription` :
    << Forcas deals +{[extraDmgPct]}% Damage for each adjacent unit and additionally
    +{[extraDmg]} Damage for each adjacent friendly Dark Angel. >>

===================================================================================================
RECENSEMENT PAR LE BLOC `methodPointers` (jamais par grep de nom) -- 3 classes, 12 methodes
===================================================================================================

  `IdunBattle.Entities.Effects.Loki.EnmityForTheUnworthy_ExtraDamageEffect`  (`EffectType 0x578 = 1400`)
      AdjacentFriendlyDarkaUnitsAmount · CreateActiveCondition · CreateEffectDamageBonusForAttack
      · CurrentDamage · GetLocalizationDataInternal
  `IdunBattle.Entities.Effects.Loki.EnmityForTheUnworthy_ExtraDamagePctEffect` (`EffectType 0x577 = 1399`)
      .ctor · AdjacentUnitsAmount · CreateActiveCondition · CreateEffectDamageBonusForAttack
      · CurrentDamagePct · GetLocalizationDataInternal
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnmityForTheUnworthyAbility`
      CreateBehaviour

CE QUI N'EXISTE PAS, et c'est un RESULTAT :
  * **`EnmityForTheUnworthyAbility` n'a PAS de `CreateTrigger` propre** -- elle prend celui de sa
    base, `On(AbilityInit) & get_OwnerIsActor` : les deux effets sont poses A L'INIT du porteur,
    d'un bloc, et y restent (aucune duree). D'ou l'inscription en `ABILITY_INIT_OWNER_EFFECTS`
    et NON en `ABILITY_TRIGGERS` (contraste `HeadClaimer`, dont la pose est un trigger de kill) ;
  * **aucune `CreateTargetSelector`** -> deux SELF-effects, jamais des auras ;
  * **aucun `.ctor` propre a `_ExtraDamageEffect`** : DEDUPLIQUE par IL2CPP avec celui de
    `_ExtraDamagePctEffect` (corps byte-identiques, `mov edx, 0x522` puis
    `AbilityOrEffect$$op_Implicit` @`set_TriggeredAbility` puis `BaseEffect..ctor(this, ao, 1)`) --
    lu dans les OCTETS, la table n'ayant qu'une ligne pour les deux.

===================================================================================================
LES ARBRES (mirror 1:1 du decompile)
===================================================================================================

`..._ExtraDamageEffect$$AdjacentFriendlyDarkaUnitsAmount` :

    Count( NonSteppableOrObjectUnits(
               UnitsFromFaction( AdjacentFriends(Owner@DSLSelectors+0x30, unique: true,
                                                 UnitSelectionType.OnlyAliveAndTargetable = 3),
                                 UnitFaction.DarkAngels = 0xa, 3 ),
               3 ) )

`..._ExtraDamageEffect$$CurrentDamage` :

    Multiply( ConfigVar(AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@this+0x60),
              Count(<le MEME sous-arbre, recompose inline par le natif>) )

`..._ExtraDamageEffect$$CreateActiveCondition`         : AmountIsGreaterThanZero(<le compteur>)
`..._ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :
    EffectBonus.ForAddition( get_OwnerIsCaster, CurrentDamage(), AbilityOrEffect(<source>) )

`..._ExtraDamagePctEffect$$AdjacentUnitsAmount` :

    Count( NonSteppableOrObjectUnits( AdjacentUnits(Owner@DSLSelectors+0x30, unique: true, 3), 3 ) )

`..._ExtraDamagePctEffect$$CurrentDamagePct` :

    Multiply( ConfigVar(AbilityVariableType.extraDmgPct = 0xa = 10, GetAbilityState(this),
                        config@this+0x60),
              Count(<le MEME sous-arbre, recompose inline>) )

`..._ExtraDamagePctEffect$$CreateActiveCondition`         : AmountIsGreaterThanZero(<le compteur>)
`..._ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack` :
    EffectBonus.ForPercentIncrease( get_OwnerIsCaster, CurrentDamagePct(), AbilityOrEffect(<source>) )

## LES DEUX EFFETS SE RESSEMBLENT ET DIFFERENT SUR **QUATRE** AXES -- une recopie les effacerait

    | axe                | 1400 `_ExtraDamage`                | 1399 `_ExtraDamagePct`          |
    |--------------------|------------------------------------|---------------------------------|
    | population comptee | `AdjacentFriends` **+ faction**    | `AdjacentUnits` NU (amis ET     |
    |                    | `UnitsFromFaction(DarkAngels)`     | ennemis, aucun filtre d'equipe) |
    | variable lue       | `ConfigVar(8 = extraDmg)`          | `ConfigVar(10 = extraDmgPct)`   |
    | canal `EffectBonus`| `+0x10` Addition -> `ForAddition`  | `+0x08` -> `ForPercentIncrease` |
    | scaling de rarete  | `extraDmg` **EST** dans            | `extraDmgPct` n'y est **PAS**   |
    |                    | `variablesAffectedByRarityBonus`   | -> multiplier NO-OP             |

Le 1er axe est celui que l'i2 rend explicite (<< for each adjacent unit >> vs << for each adjacent
friendly Dark Angel >>) ; le 4e ne se lit QUE dans le gameconfig
(`abilities.EnmityForTheUnworthy.variablesAffectedByRarityBonus == ["extraDmg"]`).

## CE QUI EST COMMUN, ET LU

  * `NonSteppableOrObjectUnits(entities, 3)` = `entities & UnitsWithoutTrait(entities,
    UnitTrait.Steppable = 0x1b, 3) & UnitsWithoutTrait(entities, UnitTrait.Object = 0xd, 3)`
    (decompile de `IdunBattleLogic.Entities.DSLSelectors$$NonSteppableOrObjectUnits`) -- present
    sur LES DEUX compteurs. C'est l'ecart avec le compteur DEATHWING deja porte
    (`adjacent_dark_angels_friends`, #932), qui s'arrete a `UnitsFromFaction` : les deux arbres ne
    sont donc PAS interchangeables, d'ou deux cles de contexte distinctes.
  * `AdjacentUnits(origin, unique, selType)` =
    `op_Subtraction(Units(AdjacentTiles(origin), unique, selType), origin)` -> le PORTEUR ne se
    compte JAMAIS lui-meme, sur les deux axes (`AdjacentFriends` fait la meme soustraction).
  * `get_OwnerIsCaster` est le SEUL noeud des deux conjonctions de degat : ni `IsMeleeAttack`, ni
    `IsRangedAttack`, ni `IsNormalAttack` -> le bonus vaut pour TOUTE attaque du porteur (i2 :
    << deals ... Damage >>, sans restriction de nature).

## LES SURCHARGES SONT TRANCHEES PAR L'ADRESSE REELLE DE LA CIBLE DU `call` (decodage `E8 rel32`)

Depuis `...$$AdjacentFriendlyDarkaUnitsAmount` :
  * `+0x48` -> `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(this, unit, unique,
    selectionType)` -- la variante **A**, PAS la variante B `(this, unit, unitTile, unique)` ;
  * `+0x68` -> `IdunBattleLogic.Entities.DSLSelectors$$UnitsFromFaction(this, entities, faction,
    unitSelectionType)` -- l'overload **ENUM**, pas celui qui recoit un `factionId` string ;
  * `+0x7c` -> `IdunBattleLogic.Entities.DSLSelectors$$NonSteppableOrObjectUnits`.
Le pseudo-C affiche la MEME signature pour les deux variantes d'`AdjacentFriends` : seule l'adresse
tranche. Meme methode que `deathwing.py`.

## LA CONDITION D'ACTIVITE EST PORTEE, ET ELLE EST REDONDANTE AVEC LA MAGNITUDE

`AmountIsGreaterThanZero(<compteur>)` : l'effet est INACTIF tant qu'aucun voisin ne compte. Cote
port la magnitude RE-COMPTE au coup (`n == 0` -> `None`), donc le gate ne peut pas diverger de la
contribution -- meme regime que `LordOfTempests_ExtraDamage`. En revanche `active_condition_ported`
est pose : le flag `active` CAPTE decrit la position REELLE et ne predit rien d'une tuile SIMULEE
(le natif, lui, reecrit `EffectComponent.IsActive` a chaque `RefreshEffects`, `Simulation`
comprise) -- exactement l'argument de `ModifiedExoarmour_ExtraDmg` (case-322).

## SUBSTRAT DES DEUX COMPTEURS (tri-etat STRICT, MEMES cles des DEUX cotes)

    face COMBAT     : `runner/damage_model.py` -> `runner/components.py`
    face PREDICTION : `playbook/prediction/` -> `playbook/scene.py`

    `adjacent_units_no_steppable`                  <- `AdjacentUnitsAmount`
    `adjacent_dark_angels_friends_no_steppable`    <- `AdjacentFriendlyDarkaUnitsAmount`

CLE ABSENTE ou `None` => << non mesure >> => aucune contribution (degradation RESTRICTIVE), JAMAIS
un 0 rabattu : un 0 invente ferait passer un bonus reel pour son absence.

⚠ RESIDU NOMME (#948-r1, meme contraste assume que `adjacent_dark_angels_friends` de #932) : la
face PREDICTION evalue les deux compteurs A LA POSITION COURANTE du porteur, pas a la TUILE
CANDIDATE. Un plan qui rapproche Forcas de ses freres n'en voit donc pas le gain en prediction ; la
face COMBAT, elle, mesure la position REELLE au moment du coup.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition, for_percent_increase
from ..base import BaseEffect
from ..magnitude import ability_var
from ....dsl.base import Const
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentFriends, AdjacentUnits, And, UnitsFromFaction, UnitsWithoutTrait
from ...traits.unit_trait import UnitTrait
from ...unit_faction import UnitFaction
from ...unit_selection_type import UnitSelectionType

#: cle gameconfig de l'ability -- l'`AbilityOrEffect` que le `.ctor` des DEUX effets passe a
#: `BaseEffect` (`mov edx, 0x522` = `TriggeredAbilityType.EnmityForTheUnworthy = 1314`, lu dans les
#: octets), donc la config que `ConfigVar` indexe.
ABILITY_ID = "EnmityForTheUnworthy"
#: `AbilityVariableType 8` et `0xa = 10` (`frida/enums.tsv`), resolus par leur NOM.
VAR_EXTRA_DMG = "extraDmg"
VAR_EXTRA_DMG_PCT = "extraDmgPct"
#: `UnitSelectionType 3` -- le litteral que le natif propage a TOUS les etages des deux compteurs.
_SEL = int(UnitSelectionType.OnlyAliveAndTargetable)
#: cles du contexte per-coup. MEME nom, MEME semantique des DEUX cotes (cf. l'en-tete).
CTX_ADJACENT_UNITS = "adjacent_units_no_steppable"
CTX_ADJACENT_DA = "adjacent_dark_angels_friends_no_steppable"


def non_steppable_or_object_units(entities, selection_type=_SEL):
    """`IdunBattleLogic.Entities.DSLSelectors$$NonSteppableOrObjectUnits(entities, selectionType)`,
    noeud par noeud (decompile) :

        op_BitwiseAnd( op_BitwiseAnd(entities, UnitsWithoutTrait(entities, 0x1b, selectionType)),
                       UnitsWithoutTrait(entities, 0xd, selectionType) )

    C'est une INTERSECTION des deux filtres avec l'ensemble d'origine, pas deux filtres CHAINES --
    meme forme que le `UnitsWithoutTraits` (pluriel) mirroire par `runner/abilities/admec.py`.
    Le nom << NonSteppableOrObject >> designe ce qui est RETIRE (Steppable **ou** Object), donc ce
    qui reste est bien l'intersection des deux complementaires."""
    return And(And(entities, UnitsWithoutTrait(entities, int(UnitTrait.Steppable),
                                               selection_type=selection_type)),
               UnitsWithoutTrait(entities, int(UnitTrait.Object), selection_type=selection_type))


def adjacent_units_selector():
    """L'ARBRE de `..._ExtraDamagePctEffect$$AdjacentUnitsAmount` (doctrine #149 : l'artefact natif
    est un SELECTEUR, donc le port est un arbre) :

        Count( NonSteppableOrObjectUnits( AdjacentUnits(Owner@+0x30, unique: true, 3), 3 ) )

    AUCUN filtre d'equipe ni de faction : `AdjacentUnits` compte les AMIS **et** les ENNEMIS
    (`Units(AdjacentTiles(origin)) - origin`). Import PARESSEUX de `Count` : `entities/formulas` est
    assemble APRES le package `entities/effects` (meme garde anti-cycle que `deathwing`)."""
    from ...formulas import Count

    return Count(non_steppable_or_object_units(
        AdjacentUnits(Owner(), Const(1), selection_type=_SEL)))


def adjacent_dark_angels_friends_selector():
    """L'ARBRE de `..._ExtraDamageEffect$$AdjacentFriendlyDarkaUnitsAmount` :

        Count( NonSteppableOrObjectUnits(
                   UnitsFromFaction( AdjacentFriends(Owner@+0x30, unique: true, 3),
                                     UnitFaction.DarkAngels = 0xa, 3 ), 3 ) )

    `reference=Owner()` est passe EXPLICITEMENT a `AdjacentFriends` : la reference d'equipe du
    `Friends` natif EST le centre, et le defaut du port (`ctx.caster`) ne coinciderait que tant que
    le contexte est bati sur le porteur (meme precaution que `deathwing`).

    `UnitsFromFaction` compare le `FactionId` gameconfig au NOM de la valeur d'enum -- c'est ce que
    le natif fait (`System.Enum.ToString(UnitFaction)` puis `String.Equals` sur
    `FactionComponent+0x30`), et c'est pourquoi la constante est `UnitFaction.DarkAngels.name` et
    non l'ordinal `10`.

    ⚠ CE N'EST PAS le selecteur de `DeathwingEffect$$GetDoubleEffectCondition` (#932), qui s'arrete
    a `UnitsFromFaction` : l'etage `NonSteppableOrObjectUnits` est PROPRE a Enmity."""
    from ...formulas import Count

    return Count(non_steppable_or_object_units(
        UnitsFromFaction(AdjacentFriends(Owner(), Const(1), Owner(), _SEL),
                         UnitFaction.DarkAngels.name, _SEL)))


class _EnmityForTheUnworthyEffect(BaseEffect):
    """Socle des DEUX effets : meme `.ctor` (deduplique), meme gate `get_OwnerIsCaster` seul, meme
    forme `Multiply(ConfigVar(<var>), Count(<compteur>))`, meme `CreateActiveCondition`
    `AmountIsGreaterThanZero(<le MEME compteur>)`. Tout le reste DIFFERE (cf. l'en-tete)."""

    #: cle du contexte per-coup qui porte `Count(<compteur>)` pour CETTE face.
    _CTX_KEY = ""
    #: variable gameconfig lue par le `ConfigVar` de CETTE face.
    _VAR = ""
    #: `EffectComponent.IsActive` capte est PERIME : la `CreateActiveCondition` est PORTEE ici (la
    #: magnitude rend `None` des que le compteur vaut 0, ce qui EST `AmountIsGreaterThanZero`).
    active_condition_ported = True

    def _count(self, ctx: "Mapping | None") -> "int | None":
        """Le `Count(<selecteur>)` de CETTE face, lu au contexte per-coup. TRI-ETAT : cle absente ou
        `None` => `None` = << non mesure >>, JAMAIS 0 (un 0 invente ferait passer un bonus reel pour
        son absence)."""
        n = (ctx or {}).get(self._CTX_KEY)
        return None if n is None else int(n)

    def _amount(self, ctx: "Mapping | None") -> "int | None":
        """`Multiply( ConfigVar(<var>, GetAbilityState(this), config@+0x60), Count(<compteur>) )`.

        `MultiplyAmount$$Calculate` est un produit d'ENTIERS : `ability_var` arrondit AVANT.
        `GetAbilityState(this)` sur un `AbilityOrEffect` TRIGGERED resout le niveau du PASSIF du
        porteur -> `self.ability_level` (jamais `active_ability_level`)."""
        n = self._count(ctx)
        if not n or n <= 0:                             # AmountIsGreaterThanZero -> inerte
            return None
        if self.ability_level is None:                  # ConfigVar sans AbilityState -> inerte
            return None
        per = ability_var(ABILITY_ID, self._VAR, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        return int(per) * int(n)

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` = `AmountIsGreaterThanZero(<compteur>)`.

        Le `unit_state` ne porte PAS ces compteurs (ils vivent dans le contexte PER-COUP, comme la
        position d'attaque) : sans substrat, on rend `True` -- la magnitude, elle, re-compte au coup
        et rend `None` quand le compteur est nul, donc la contribution reste EXACTE. Ce qui serait
        FAUX, c'est de rendre `False` par defaut : l'instance disparaitrait de `active_effects` et
        avec elle toute chance de contribuer."""
        n = self._count(unit_state)
        return True if n is None else n > 0


class EnmityForTheUnworthyExtraDamageEffect(_EnmityForTheUnworthyEffect):
    """`IdunBattle.Entities.Effects.Loki.EnmityForTheUnworthy_ExtraDamageEffect`
    (`EffectType 0x578 = 1400`, nom capte `EnmityForTheUnworthy_ExtraDamage`).

    i2 `UnitEffects/EnmityForTheUnworthy_ExtraDamage_Description` :
    << Deals +{[extraDmgCurrent]} Damage >>.

    Compteur = les amis DARK ANGELS adjacents (hors Steppable/Object) ; variable `extraDmg`, DANS
    `variablesAffectedByRarityBonus` -> scale par le multiplicateur du porteur ; canal `+0x10`
    Addition (`for_addition`), applique PAR COUP."""

    _CTX_KEY = CTX_ADJACENT_DA
    _VAR = VAR_EXTRA_DMG

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """`ForAddition( get_OwnerIsCaster, CurrentDamage() )` -- UN SEUL noeud trigger, satisfait
        STRUCTURELLEMENT sur ce canal (l'agregateur n'itere que les effets de l'ATTAQUANT). Aucun
        re-gate de nature de coup : le decompile n'en porte AUCUN."""
        amt = self._amount(att_ctx)
        return for_addition(True, amt) if amt else None


class EnmityForTheUnworthyExtraDamagePctEffect(_EnmityForTheUnworthyEffect):
    """`IdunBattle.Entities.Effects.Loki.EnmityForTheUnworthy_ExtraDamagePctEffect`
    (`EffectType 0x577 = 1399`, nom capte `EnmityForTheUnworthy_ExtraDamagePct`).

    i2 `UnitEffects/EnmityForTheUnworthy_ExtraDamagePct_Description` :
    << Deals +{[extraDmgPctCurrent]}% Damage >>.

    Compteur = TOUTES les unites adjacentes (amies ET ennemies, hors Steppable/Object) ; variable
    `extraDmgPct`, **HORS** `variablesAffectedByRarityBonus` -> le multiplier est un NO-OP ; canal
    `+0x08` (`for_percent_increase`) = la %-list du `DamageModifiers` attaquant, consommee par
    `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers` APRES percage/armure."""

    _CTX_KEY = CTX_ADJACENT_UNITS
    _VAR = VAR_EXTRA_DMG_PCT

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """`ForPercentIncrease( get_OwnerIsCaster, CurrentDamagePct() )` -- MEME conjonction a un
        noeud que la face additive, mais canal `EffectBonus` DIFFERENT (`+0x08`, lu a l'offset
        ECRIT, pas au nom de la fabrique)."""
        amt = self._amount(att_ctx)
        return for_percent_increase(True, amt) if amt else None
