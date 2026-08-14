"""`MawClawsOfThyrax_ExtraCritDmg` (`EffectType` 0x5b5 = **1461**) -- le second `ForAddition` de
l'axe crit-DEGAT porte par une RELIQUE : le porteur frappe plus fort en CRIT pour chaque unite
a trait `Summon` ADJACENTE, **de n'importe quel camp**.

## IDENTITE -- DEUX collisions d'ordinal, et chacune designe une AUTRE relique

    EffectType            0x5b5 = 1461 = MawClawsOfThyrax_ExtraCritDmg   <- CET effet
    TriggeredAbilityType  0x5bd = 1469 = MawClawsOfThyrax                <- sa CONFIG
    TriggeredAbilityType  0x5b5 = 1461 = BookOfFate                      <- une AUTRE relique
    EffectType            0x5bd = 1469 = MischiefMakers                  <- autre chose encore

Les deux lectures sont TRANCHEES par l'ADRESSE de la cible du `call`, pas par le nom :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.MawClawsOfThyraxAbility$$GetEffectType
        b8 b5 05 00 00 c3      ; corps ENTIER : `return 0x5b5` = 1461 -> l'appariement
                               ;   ability -> effet est LU, pas deduit

    IdunBattle.Entities.Effects.Loki.MawClawsOfThyrax_ExtraCritDmgEffect$$.ctor
        ba bd 05 00 00         ; mov  edx, 0x5bd = 1469
        e8 <rel32> -> 0x181669f80 = `IdunBattle.Core.AbilityOrEffect$$op_Implicit(
                                     triggeredAbility: TriggeredAbilityType)`
                               ;   surcharge resolue par son RVA (les QUATRE sont homonymes)
        41 b0 01               ; mov  r8b, 1  = hasAutomaticActivation
        e8 <rel32> -> 0x18100c390 = `IdunBattle.Entities.Effects.BaseEffect$$.ctor(
                                     abilityOrEffect, hasAutomaticActivation)`

Lire `0x5bd` comme un `EffectType` nommerait `MischiefMakers` ; lire `0x5b5` comme une
`TriggeredAbilityType` ferait chercher la config de `BookOfFate` -- qui EXISTE au gameconfig (autre
relique), donc l'erreur ne leverait pas : elle lirait la mauvaise variable, en silence.

## L'ARTEFACT, LU EN ENTIER (build `rnca9r7q6c`)

`IdunBattle.Entities.Effects.Loki.MawClawsOfThyrax_ExtraCritDmgEffect` (: `BaseEffect`, cf.
`classes.tsv`). SEPT methodes, dont deux DEDUPLIQUEES (absentes des tables -- « l'absence ne prouve
rien », CLAUDE.md) :

    $$.ctor                       = BaseEffect..ctor(this, AbilityOrEffect(0x5bd), hasAutomatic: 1)
    $$CreateTargetSelector        = <DSLSelectors+0x30> = Owner   <- DEDUPLIQUE (defaut)
    $$CreateActiveCondition       = DSLTriggers.AmountIsGreaterThanZero( <vslot +0x5f8> )
    $$GetCalculateLevel           = <vslot +0x5f8>, cf. plus bas
    $$CreateCritDamageBonus       = EffectBonus.ForAddition( get_OwnerIsCaster,
                                                             GetExtraCritAmount() )
    $$GetExtraCritAmount          = DSLFormulas.Multiply(
                                        ConfigVar(0x42 = extraCritDmg, GetAbilityState(effet),
                                                  config@+0x60),
                                        DSLFormulas.EffectLevel(Effect@DSLSelectors+0x38) )
    $$GetLocalizationDataInternal = { AbilityParam(0x23) : <GetExtraCritAmount> }  -- affichage seul

`GetExtraCritAmount` (RVA `0x105ef40`) porte le corps PARTAGE avec
`KardiocoreGalvanus_ExtraCritDmgEffect` : meme formule, et le `config@+0x60` etant un champ
d'INSTANCE, chaque effet y lit SA propre `AbilityConfiguration`. `AbilityVariableType 0x42 = 66 =
extraCritDmg` (`enums.tsv`, jamais recopie du decompile) ; `UnitSelectionType 3 =
OnlyAliveAndTargetable`.

## LE COMPTEUR -- `AdjacentUnits`, PAS `AdjacentFriends`, et c'est LA difference

`$$GetCalculateLevel`, relu A L'ASSEMBLEUR (les QUATRE cibles de `call` resolues par leur RVA,
jamais par le nom affiche) :

    Count( Unique( UnitsWithTrait( AdjacentUnits(Owner@DSLSelectors+0x30, unique: 1,
                                                 selectionType: 3),
                                   trait: 0x2 = UnitTrait.Summon,
                                   selectionType: 3 ) ) )

    e8 -> 0x180eac4a0  DSLSelectors$$AdjacentUnits(origin, unique, selectionType)
    e8 -> 0x180eb5070  DSLSelectors$$UnitsWithTrait(entities, trait, selectionType)
    e8 -> 0x180eb35a0  DSLSelectors$$Unique(entities)
    e9 -> 0x180ea85e0  DSLFormulas$$Count(selector)

⚠ **`AdjacentUnits` NE FILTRE PAS L'EQUIPE.** Son corps est
`op_Subtraction( Units(AdjacentTiles(origin), unique, selectionType), origin )` -- aucun `Friends`,
aucun `Enemies`. Un summon ENNEMI adjacent compte donc AUTANT qu'un summon allie. C'est l'exacte
difference avec les deux voisins de forme, dont le port a deja ete ecrit :

  * `AmuletOfTheVoidwyrm` -> `AdjacentFriends(...)` filtre `Summon` **et** `Decoy`, AMIS seuls ;
  * `KardiocoreGalvanus`  -> `MechanicalUnits(AdjacentFriends(...))`, AMIS seuls.

Recopier l'un des deux ferait manquer tous les summons adverses -- silencieusement, et sur un
axe (Tyranides / Genestealer) ou les deux camps en produisent.

⚠ Le `Unique` est un noeud SUPPLEMENTAIRE que ni 1450 ni 1460 ne portent, bien qu'`AdjacentUnits`
recoive deja `unique: 1`. On le mirrore quand meme : on porte le corps, pas l'economie qu'on
pourrait en faire.

## LA CONDITION D'ACTIVITE -- le MEME compteur, compare a zero

`$$CreateActiveCondition`, relu octet a octet :

    48 8b 41 48              ; rax = this->dsl (+0x48)
    48 8b 98 88 00 00 00     ; rbx = dsl.Triggers (+0x88)
    48 8b 82 f8 05 00 00     ; rax = vtable[+0x5f8]         <- LE SLOT
    ff d0                    ; call  -> `GetCalculateLevel()`
    e9 <rel32> -> 0x180ed52d0 = `DSLTriggers$$AmountIsGreaterThanZero(amount: IAmountFormula)`
                             ;   surcharge tranchee par l'ADRESSE (l'autre, 0x180ed5360, prend un
                             ;   ITargetsSelector)

Le slot `+0x5f8` EST `GetCalculateLevel` : `IdunBattle.Entities.Effects.BaseEffect$$
IsCalculatingLevel` et `$$NeedsRefreshing` l'appellent tous deux et CACHENT le resultat dans
`this+0x88`, que `BaseEffect$$CalculateLevel` evalue ensuite. (Le slot `+0x518`, lui, est
`CreateActiveCondition`, cache en `this+0x90`.)

CONSEQUENCE DE HARNAIS, et c'est l'INVERSE de `KardiocoreGalvanus` (dont la condition est
`<DSLTriggers+0x70>` = `YesTrigger`, constante VRAIE) : cet effet est **INACTIF** tant qu'aucun
summon n'est adjacent, donc **ABSENT du canal `decisionView.effects`** (ACTIF-ONLY, GROUND TRUTH
#100) -- meme motif exact qu'`AmuletOfTheVoidwyrm`, `NetherRealmCasket`, `AnvilShield_
BlockChanceBelowHealthCap` et `VisionsOfHeresy_*`. D'ou `active_condition_ported = True` et la cle
`adjacent_summons` du `unit_state`.

## POSE -- owner-effect PERMANENT, a l'init de l'ability

`classes.tsv` : `MawClawsOfThyraxAbility` derive d'`IdunBattle.Entities.Abilities.
AOwnerEffectTriggeredAbility` (elle n'override QUE `GetEffectType`), dont le `CreateBehaviour` de
BASE est

    If( CreateTrigger() = OnOwnerSpecificAbilityInit(<this+0x10> = 1469),
        AddEffect( GetEffectType() = 0x5b5,
                   AbilityState(Owner@DSLSelectors+0x30, AbilityType(abilityState)),
                   source  = Owner@DSLSelectors+0x30,
                   targets = Owner@DSLSelectors+0x30,
                   turns   = <zeroe>  ->  PERMANENT ) )

donc **source == porteur == Owner**, une fois a l'initialisation, jamais expire -- ce qui l'eteint
est sa `CreateActiveCondition`, pas une duree. C'est ce qui rend le niveau EXACT : l'`AbilityState`
bake dans l'`EffectComponent+0x18` est celui de la relique SUR SON PORTEUR, c'est-a-dire l'etat
TERTIAIRE (`TertiaryAbilityLevel` / `TertiaryAbilityVariablesMultiplierPercentage`), relu par le
foyer UNIQUE `runner/operations/triggers/base.py::triggered_ability_state` (#357).

## PAS d'entree `ABILITY_INIT_OWNER_EFFECTS`, et c'est MESURE

`runner/operations/spawn.py::_seed_ability_owner_effects` lit
`GC.unit(vid).activeAbilities + passiveAbilities` -- le KIT gameconfig. Or `MawClawsOfThyrax` est
une RELIQUE (`items/R_Crit_MawClawsOfThyrax`, `allowedUnits = [tyranTyrantGuard, tyranWingedPrime,
tyranParasite, genesPatriarch]`) : elle n'est au kit d'AUCUN des quatre porteurs, elle arrive par
`BC.Units[].TertiaryAbility`. Une entree serait donc INERTE sur ce chemin. Meme arbitrage explicite
que `kardiocore_galvanus.py`, `martial_superiority.py` et `structural_analyser.py` -- a rouvrir SI
un porteur SPAWNE de cette relique apparait (aucun aujourd'hui : les quatre sont des HEROES du
pool).

## LE CANAL -- `ForAddition`, et le trigger porte sur le CASTER

`$$CreateCritDamageBonus`, cibles de `call` resolues par leur RVA :

    e8 -> 0x18105ef40  GetExtraCritAmount()
    e8 -> 0x180edbaa0  DSLTriggers$$get_OwnerIsCaster
    e8 -> 0x181047dc0  EffectBonus$$ForAddition(trigger, addition, abilityOrEffect)
                       (et NON 0x181048090 = `$$ForSubtraction` : c'est l'ADRESSE qui tranche)

`get_OwnerIsCaster` = `AreEqual(Owner@DSLSelectors+0x30, Caster@DSLSelectors+0x48)` : « le PORTEUR
de cet effet est-il l'ATTAQUANT du coup ? ». Trigger NU, aucun `op_BitwiseAnd`.

CONSOMMATION, relue : `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects`
accumule litteralement `addition - subtraction`, et `$$CalculateCriticalDamage` fait
`Math.Max(0, GetStat(10) + somme)`. Le port rend donc un entier **POSITIF** ; le clamp bas ne peut
pas mordre sur un terme additif.

## LA MAGNITUDE -- un PRODUIT, et son second facteur est une LECTURE du niveau STOCKE

    Multiply( ConfigVar(0x42 = extraCritDmg, GetAbilityState(effet), config@+0x60),
              EffectLevel(Effect@DSLSelectors+0x38) )

`DSLFormulas.EffectLevel` lit `EffectComponent+0x68`, champ que
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel` tient EGAL a `GetCalculateLevel` (il
appelle le slot `CalculateLevel` = `BaseEffect$$CalculateLevel`, formule `this+0x88`, compare et
ECRIT si ca differe). Le niveau stocke EST donc, a tout instant ou le refresh a tourne, le nombre
de summons adjacents. Le port privilegie le compteur RECALCULE (il suit l'etat courant du board) et
retombe sur le niveau CAPTE quand aucun `state` n'est threade -- les garder tous les deux est ce
qui rend l'etage FALSIFIABLE.

`MawClawsOfThyrax` n'a AUCUN `variablesAffectedByRarityBonus` ni `constants` au gameconfig
(`variables.extraCritDmg` seule, 10 paliers `[295, 311, ..., 438]` -- les MEMES valeurs que
`KardiocoreGalvanus`, coincidence de config, pas de partage) -> le multiplicateur de rarete ne mord
pas ; on le passe quand meme, parce que c'est `ability_var` (donc la config) qui decide.

ASCII only.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ....dsl.base import Const
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentUnits, Unique, UnitsWithTrait
from ...traits.unit_trait import UnitTrait
from ...unit_selection_type import UnitSelectionType
from .. import ctx_keys as _ctx_keys      # #1042-r5 : foyer UNIQUE des chaines de cle de ctx

#: `TriggeredAbilityType 0x5bd = 1469` -- le litteral du `.ctor`, relu a l'assembleur, et dont la
#: SURCHARGE d'`op_Implicit` (resolue par son RVA `0x1669f80`) etablit qu'il s'agit bien de l'enum
#: des TRIGGERED (l'`EffectType` 1469 est `MischiefMakers`, autre chose).
_ABILITY_ID = "MawClawsOfThyrax"
#: `AbilityVariableType 0x42 = 66` (`enums.tsv`, jamais recopie du decompile).
_VAR_KEY = "extraCritDmg"
#: `UnitSelectionType 3` -- le litteral que le natif propage aux DEUX etages du compteur.
_SEL = int(UnitSelectionType.OnlyAliveAndTargetable)
#: cle du compteur, posee par le foyer `runner/components.py::adjacent_summons_count`
CARRIER_COUNT_KEY = "adjacent_summons"
#: callable `(owner_id) -> int | None` pose dans le contexte du canal CRIT par `_crit_board`
CTX_COUNT_OF = "adjacent_summons_of"
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(effet)`
CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF


def adjacent_summons_selector():
    """L'ARBRE DSL de `...MawClawsOfThyrax_ExtraCritDmgEffect$$GetCalculateLevel`, noeud par noeud
    (doctrine #149 : l'artefact natif est un SELECTEUR, donc le port est un arbre, pas une boucle
    recablee) :

        Count( Unique( UnitsWithTrait( AdjacentUnits(Owner@+0x30, unique: 1, selectionType: 3),
                                       0x2 = Summon, selectionType: 3 ) ) )

    ⚠ `AdjacentUnits` et NON `AdjacentFriends` : le natif ne filtre AUCUN camp ici (son corps est
    `Units(AdjacentTiles(origin), unique, sel) op_Subtraction origin`). Le porteur s'exclut
    lui-meme par ce `op_Subtraction`, mais un summon ADVERSE compte.

    Import PARESSEUX de `Count` : `entities/formulas` est assemble APRES le package
    `entities/effects` (meme garde anti-cycle et meme convention que `kardiocore_galvanus`,
    `supa_cybork_body` et `amulet_of_the_voidwyrm`)."""
    from ...formulas import Count

    return Count(Unique(UnitsWithTrait(AdjacentUnits(Owner(), Const(1), _SEL),
                                       int(UnitTrait.Summon), _SEL)))


class MawClawsOfThyraxExtraCritDmgEffect(BaseEffect):
    """`MawClawsOfThyrax_ExtraCritDmg` (0x5b5 = 1461) -- owner-effect PERMANENT de la relique
    `MawClawsOfThyrax` : quand son porteur est l'ATTAQUANT d'un coup CRITIQUE, le degat de crit est
    AUGMENTE de `extraCritDmg[niveau de relique] x <nombre d'unites a trait Summon adjacentes au
    porteur, TOUS CAMPS CONFONDUS>`.

    Quatrieme implementeur porte du canal crit-DEGAT cote RELIQUE, et le second de l'axe ADDITION
    (`KardiocoreGalvanus` est l'autre) ; `AmuletOfTheVoidwyrm`, `SupaCyborkBody` et
    `NetherRealmCasket` sont des `ForSubtraction` sur la CIBLE."""

    # La `CreateActiveCondition` est GEOMETRIQUE (`AmountIsGreaterThanZero(GetCalculateLevel())`) :
    # elle rebascule des qu'une unite bouge, et le natif la reevalue
    # (`RefreshEffectsOperation$$RefreshEffect` -> `Activate`/`DeactivateEffect`). La condition
    # PORTEE fait donc foi sur le flag `IsActive` capte -- meme arbitrage qu'`AmuletOfTheVoidwyrm`
    # et `NetherRealmCasket`, dont la condition est de la meme famille.
    active_condition_ported = True

    @staticmethod
    def _adjacent_summons(ctx: "Mapping | None") -> "int | None":
        """`GetCalculateLevel()` EVALUE pour le PORTEUR de CETTE instance.

        Le canal pose `owner_id` par porteur (mirror de l'ecriture `AbilityEntities+0x18` que la
        boucle native fait a chaque iteration), et `_crit_board` pose le callable
        `adjacent_summons_of` -- paresseux, donc rien n'est calcule tant qu'aucune instance ne le
        demande.

        TRI-ETAT : callable ou `owner_id` ABSENT => `None` = « non mesure », JAMAIS 0. Un 0 invente
        annulerait le produit et ferait passer un bonus reel pour une absence de bonus."""
        c = ctx or {}
        fn = c.get(CTX_COUNT_OF)
        oid = c.get("owner_id")
        if fn is None or oid is None:
            return None
        n = fn(oid)
        return None if n is None else int(n)

    def _effect_level(self, ctx: "Mapping | None") -> "int | None":
        """`DSLFormulas.EffectLevel(Effect@DSLSelectors+0x38)` = `EffectComponent+0x68`.

        Ce champ est tenu EGAL a `GetCalculateLevel` par
        `IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel`. Le port privilegie donc le
        compteur RECALCULE, qui suit l'etat courant du board, et retombe sur le niveau CAPTE quand
        aucun `state` n'est threade (probe/test offline).

        ⚠ Ce niveau n'est PAS le niveau d'ability : `self.level` est le niveau de l'EFFET
        (`decisionView.effects[].level`), `_ability_state` rend l'autre. Les confondre lirait
        `extraCritDmg[1] = 295` au lieu du palier reel."""
        n = self._adjacent_summons(ctx)
        if n is not None:
            return n
        return None if self.level is None else int(self.level)

    def _ability_state(self, ctx: "Mapping | None") -> tuple:
        """`GetAbilityState(effet)` -> `(level, multiplier)` de l'`AbilityState` bake a la pose.

        `AOwnerEffectTriggeredAbility$$CreateBehaviour` bake `AbilityState(Owner, <cette ability>)`
        et pose l'effet SUR l'Owner : source == porteur, donc le couple se relit sur le porteur
        (`owner_id`) par le foyer UNIQUE `runner/operations/triggers/base.py::
        triggered_ability_state` (#357), qui rend l'etat TERTIAIRE si la relique y est montee et
        l'etat PASSIF sinon.

        Callable absent (contexte sans `state`) -> repli sur les niveaux que l'effet porte deja,
        comme toutes les autres classes d'effet."""
        c = ctx or {}
        fn, oid = c.get(CTX_ABILITY_STATE_OF), c.get("owner_id")
        if fn is not None and oid is not None:
            lvl, mult = fn(oid, _ABILITY_ID)
            if lvl is not None:
                return int(lvl), int(mult if mult is not None else 100)
        lvl = self.ability_level if self.ability_level is not None else self.level
        return lvl, int(self.ability_variables_multiplier or 100)

    def _owner_is_caster(self, att_ctx: "Mapping | None" = None) -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster` = `AreEqual(Owner@+0x30,
        Caster@+0x48)`. Identite NON PROUVEE (une des deux cles absente) => noeud FAUX, jamais
        permissif -- meme foyer de raisonnement que `KardiocoreGalvanusExtraCritDmgEffect.
        _owner_is_caster`."""
        c = att_ctx or {}
        oid, aid = c.get("owner_id"), c.get("att_id")
        return oid is not None and aid is not None and oid == aid

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` = `AmountIsGreaterThanZero(GetCalculateLevel())`, ou le
        `minAmount` natif est `<DSLFormulas+0x18>` = `Direct(0)`.

        Cle ABSENTE = **non mesure** -> on NE FERME PAS (degradation fidele, meme regime
        qu'`AmuletOfTheVoidwyrmCritDamageReductionEffect.is_active` et
        `NetherRealmCasketCritDamageReductionEffect.is_active`). Cote COMBAT la cle EST posee :
        `UnitEffectStateView` la calcule paresseusement des que le porteur est SUR le plateau."""
        n = (unit_state or {}).get(CARRIER_COUNT_KEY)
        return True if n is None else int(n) > 0

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `...MawClawsOfThyrax_ExtraCritDmgEffect$$CreateCritDamageBonus` :

            EffectBonus.ForAddition( get_OwnerIsCaster,
                                     Multiply( ConfigVar(0x42 = extraCritDmg,
                                                         GetAbilityState(effet), config@+0x60),
                                               EffectLevel(Effect@+0x38) ) )

        Retour ENTIER POSITIF : `IdunBattle.Core.Services.DamagePrediction$$
        GetCritDamageBonusFromEffects` accumule litteralement `addition - subtraction`, et son
        consommateur est `Math.Max(0, GetStat(10) + somme)` dans `$$CalculateCriticalDamage`.

        Les etages sont SEPARES et chacun peut se taire independamment (aucun scalaire fitte) :
          1. `get_OwnerIsCaster`  -- le porteur est-il l'ATTAQUANT ?
          2. `EffectLevel`        -- tri-etat, `None` = non mesure ;
          3. l'`AbilityState`     -- niveau/multiplicateur de la relique sur le porteur ;
          4. `ConfigVar`          -- `extraCritDmg[niveau]`, relu du gameconfig ;
          5. `Multiply`           -- le produit, puis le signe de `ForAddition`."""
        if not self._owner_is_caster(att_ctx):                 # 1
            return None
        n = self._effect_level(att_ctx)                        # 2
        if n is None:
            return None
        lvl, mult = self._ability_state(att_ctx)               # 3
        v = ability_var(_ABILITY_ID, _VAR_KEY, lvl, multiplier_pct=mult)   # 4  ConfigVar(0x42)
        if v is None:
            return None
        amount = int(v) * int(n)                               # 5  Multiply
        return amount or None                                  #    ForAddition
