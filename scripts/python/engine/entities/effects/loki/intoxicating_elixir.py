"""`IntoxicatingElixir` (`EffectType` 0x5b3 = **1459**) -- la relique dont le bonus de degat
CRITIQUE compte les unites DEBUFFEES autour du porteur, plafonne le compte, et le DOUBLE quand le
porteur est bas en vie.

## IDENTITE -- le piege d'ordinal est REEL, et c'est la SURCHARGE qui le tranche

    EffectType            0x5b3 = 1459 = IntoxicatingElixir              <- CET effet
    TriggeredAbilityType  0x5b7 = 1463 = IntoxicatingElixir              <- sa CONFIG
    EffectType            0x5b7 = 1463 = OrbsOfDecay_AdditionalHits      <- une AUTRE ability

`1463` nomme donc DEUX choses. Ce qui tranche n'est ni l'ordinal ni le nom du module, c'est
l'ADRESSE de la surcharge appelee par le `.ctor`, relue OCTET A OCTET :

    ba b7 05 00 00      ; mov  edx, 0x5b7 = 1463
    e8 <rel32>          ; -> `IdunBattle.Core.AbilityOrEffect$$op_Implicit(triggeredAbility:
                        ;    TriggeredAbilityType)` -- la cible du `call` resolue par son RVA
                        ;    (`next_ip + rel32`), et cette surcharge-la appelle
                        ;    `AbilityOrEffect$$set_TriggeredAbility` ; les QUATRE surcharges sont
                        ;    HOMONYMES dans les tables, seule l'adresse les separe
    41 b0 01            ; mov  r8b, 1  = hasAutomaticActivation
    e8 <rel32>          ; call IdunBattle.Entities.Effects.BaseEffect$$.ctor

Lire `1463` comme un `EffectType` ferait chercher la config d'`OrbsOfDecay_AdditionalHits` : elle
n'existe pas au gameconfig, donc ici l'erreur serait BRUYANTE -- mais c'est un hasard de ce cas, pas
une garantie ; le voisin `KardiocoreGalvanus` (#913) tombait, lui, sur une config EXISTANTE.
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.IntoxicatingElixirAbility$$GetEffectType` a pour
corps ENTIER `return 0x5b3`, donc l'appariement ability -> effet est LU.

## L'ARTEFACT, LU EN ENTIER (build `rnca9r7q6c`)

`IdunBattle.Entities.Effects.Loki.IntoxicatingElixir_ExtraCritDmgEffect` (: `BaseEffect`,
`classes.tsv`). SEPT methodes nommees dans `ghidra/functions.tsv`, `CreateTargetSelector` etant la
seule DEDUPLIQUEE (corps partage avec le defaut `Owner`, cf. #913) :

    $$.ctor                 = BaseEffect..ctor(this, AbilityOrEffect(0x5b7), hasAutomatic: 1)
    $$GetLevelFormula(dsl, config, tileSelector) =
          Min( Count( EntitiesWithAnyEffect(
                          SurroundingUnits( origin  = tileSelector,
                                            range   = GetNumberConstant(0x16 = range),
                                            unique  = 1,
                                            includeCenter = 1,           <- LE CENTRE COMPTE
                                            selectionType = 3 ),
                          EffectType[4] { Pinned, Stunned,
                                          Taunted_OnlySpecificTargets, ThrillSeekers } ) ),
               Get( GetNumberConstant(0x78 = nrOfUnits) ) )
    $$GetCalculateLevel     = GetLevelFormula(dsl, config, Tiles(Owner@DSLSelectors+0x30))
    $$CreateActiveCondition = AmountIsGreaterThanZero( <le MEME GetLevelFormula> )
    $$CreateCritDamageBonus = EffectBonus.ForAddition( get_OwnerIsCaster, GetCritAmount() )
    $$GetCritAmount         = Multiply(
                                  Multiply( ConfigVar(0x42 = extraCritDmg, GetAbilityState(effet),
                                                      config@+0x60),
                                            EffectLevel(Effect@DSLSelectors+0x38) ),
                                  ConditionalAmount(
                                      HealthPctIsBelowOrEqual(Owner@DSLSelectors+0x30,
                                                              Get(GetNumberConstant(0x4f
                                                                  = healthPct))),
                                      formulaTrue  = <DSLFormulas+0x28> = Direct(2),
                                      formulaFalse = <DSLFormulas+0x20> = Direct(1) ) )
    $$GetLocalizationDataInternal                                        -- affichage seul

Resolutions, toutes LUES dans `data/symbols/<build>/frida/enums.tsv` et jamais recopiees du
decompile : `AbilityVariableType 0x42 = 66 = extraCritDmg` ; `AbilityConstantType 0x16 = 22 = range`,
`0x78 = 120 = nrOfUnits`, `0x4f = 79 = healthPct` ; `UnitSelectionType 3 = OnlyAliveAndTargetable`.
⚠ `0x42` dans l'AUTRE enum (`AbilityConstantType`) vaut `armorReduction2` : c'est la SIGNATURE de
`DSLFormulas$$ConfigVar(variableType: AbilityVariableType, abilityState, config)`, lue dans
`frida/methods.tsv`, qui fixe l'enum -- pas l'ordinal.

Gameconfig (`IntoxicatingElixir`) : `constants = {range: 2, nrOfUnits: 6, healthPct: 50}`,
`variables.extraCritDmg = [295, 311, 327, 343, 359, 375, 391, 406, 422, 438]` (memes paliers que
`KardiocoreGalvanus`, autre relique du meme lot -- coincidence de valeurs, pas de partage).

## LE BLOC DE QUATRE `EffectType` -- LU, et son blob est UNIQUE dans le metadata

Le tableau est construit par `RuntimeHelpers.InitializeArray(new EffectType[4], <FieldInfo>)`, donc
AUCUN immediat n'apparait au decompile : le `DAT_` du site porte l'index de metadata encode
(`kind = 4 = FieldInfo`), qui n'est resolu qu'au runtime. Le blob a donc ete LU dans
`global-metadata.dat` : l'UNIQUE fenetre de 4 `int32` alignes du fichier (21,6 Mo) qui contienne a la
fois `1065` et `1162` vaut

    [1065, 1162, 27, 1434]
    = Pinned, Stunned, Taunted_OnlySpecificTargets, ThrillSeekers

et cet ordre est EXACTEMENT celui de l'i2 (`Abilities/IntoxicatingElixir_CurrentLevelDescription` :
« each unit within range {[range]} that is Suppressed, Stunned, Taunted, or Thrilled, up to a maximum
of {[nrOfUnits]} times »). ⚠ `Taunted` est le composite **27** (`Taunted_OnlySpecificTargets`), PAS
ses trois sous-effets `25 / 26 / 1237` : les prendre pour equivalents compterait une cible tauntee
JUSQU'A QUATRE FOIS.

## CE QUI SEPARE CET EFFET DE SES TROIS VOISINS DE FORME -- quatre differences, toutes LUES

`KardiocoreGalvanus_ExtraCritDmg` (#913), `AmuletOfTheVoidwyrm_CritDamageReduction`,
`SupaCyborkBody_CritDmgReduction` et `NetherRealmCasket_CritDamageReduction` partagent la forme
`ForXxx(<trigger>, Multiply(ConfigVar, <compteur>))`. Recopier l'un d'eux serait FAUX ici :

| | les voisins | `IntoxicatingElixir` |
|---|---|---|
| geometrie | `AdjacentFriends` (ring-1 STOCKE, porteur EXCLU) | **`SurroundingUnits(Tiles(Owner), 2)` -- disque CUBE, `includeCenter = 1`, donc le PORTEUR SE COMPTE LUI-MEME s'il est debuffe** |
| equipe | `Friends(reference = Owner)` | **AUCUN filtre d'equipe -- amis ET ennemis comptent** |
| plafond | aucun | **`Min(..., nrOfUnits = 6)`** |
| magnitude | `ConfigVar x compteur` | **`x2` de plus si `HealthPct(Owner) <= 50`** |

Et la condition d'activite est GEOMETRIQUE (`AmountIsGreaterThanZero`), pas le `YesTrigger` de
`KardiocoreGalvanus` : l'effet est ABSENT du canal `decisionView.effects` (ACTIF-ONLY, #100) tant
qu'aucune unite debuffee n'est a portee -- meme regime qu'`AmuletOfTheVoidwyrm`, l'inverse de
`KardiocoreGalvanus`.

## POSE -- owner-effect PERMANENT, a l'init de l'ability

`classes.tsv` : `IntoxicatingElixirAbility` derive d'`IdunBattle.Entities.Abilities.
AOwnerEffectTriggeredAbility`, dont le `CreateBehaviour` (corps de BASE, deja relu par #913 et
#589-r1-r1-r2-r1) est

    If( CreateTrigger() = OnOwnerSpecificAbilityInit(<this+0x10> = 1463),
        AddEffect( GetEffectType() = 0x5b3,
                   AbilityState(Owner@DSLSelectors+0x30, <cette ability>),
                   source  = Owner@DSLSelectors+0x30,
                   targets = Owner@DSLSelectors+0x30,
                   turns   = <zeroe>  ->  PERMANENT ) )

donc **source == porteur == Owner**, une fois a l'initialisation, jamais expire. L'`AbilityState`
bake dans l'`EffectComponent+0x18` est celui de la relique SUR SON PORTEUR, c'est-a-dire l'etat
TERTIAIRE (`TertiaryAbilityLevel` / `TertiaryAbilityVariablesMultiplierPercentage`), relu par le
foyer UNIQUE `runner/operations/triggers/base.py::triggered_ability_state` (#357).

`IntoxicatingElixirAbility` ne nomme QU'UNE methode dans les tables (`$$GetEffectType`) : tout le
reste est le corps de la base.

## PAS d'entree `ABILITY_INIT_OWNER_EFFECTS`, et c'est MESURE

`runner/operations/spawn.py::_seed_ability_owner_effects` lit `GC.unit(vid).activeAbilities +
passiveAbilities` -- le KIT gameconfig. Or `IntoxicatingElixir` est une RELIQUE : elle n'y figure
pas (elle arrive par `BC.Units[].TertiaryAbility`). Une entree serait donc INERTE sur ce chemin --
meme arbitrage EXPLICITE que `kardiocore_galvanus.py` et `martial_superiority.py`. A rouvrir SI un
porteur SPAWNE apparait ; les quatre `allowedUnits` (`emperExultant`, `emperFlawlessBlade`,
`emperKakophonist`, `emperNoiseMarine`) sont des HEROES, jamais invoques.

ASCII only.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ....dsl.base import Const
from ...effect_type import EffectType
from ...selectors.accessors import Owner
from ...selectors.geometry import EntitiesWithAnyEffect
from ...selectors.units import SurroundingUnits, Tiles
from ...unit_selection_type import UnitSelectionType
import engine.entities.effects.ctx_keys as _ctx_keys      # #1042-r5 : foyer UNIQUE des chaines de cle de ctx

#: `TriggeredAbilityType 0x5b7 = 1463` -- le litteral du `.ctor`, relu a l'assembleur, et dont la
#: SURCHARGE d'`op_Implicit` etablit qu'il s'agit bien de l'enum des TRIGGERED.
_ABILITY_ID = "IntoxicatingElixir"
#: `AbilityVariableType 0x42 = 66` (`enums.tsv`, jamais recopie du decompile).
_VAR_KEY = "extraCritDmg"
#: `AbilityConstantType 0x16 = 22` -- le 2e argument de `SurroundingUnits` (`range = 2`).
_CONST_RANGE = "range"
#: `AbilityConstantType 0x78 = 120` -- la borne haute du `Min` (`nrOfUnits = 6`).
_CONST_NR_OF_UNITS = "nrOfUnits"
#: `AbilityConstantType 0x4f = 79` -- le seuil du `HealthPctIsBelowOrEqual` (`healthPct = 50`).
_CONST_HEALTH_PCT = "healthPct"
#: `UnitSelectionType 3` -- le litteral que le natif passe a `SurroundingUnits`.
_SEL = int(UnitSelectionType.OnlyAliveAndTargetable)
#: `<DSLFormulas+0x28>` = `Direct(2)`, LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor` (qui
#: alloue `+0x18 = 0`, `+0x20 = 1`, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`).
_DOUBLE = 2
#: `<DSLFormulas+0x20>` = `Direct(1)` -- la branche NON doublee du meme `ConditionalAmount`.
_SINGLE = 1
#: le blob `EffectType[4]` de `$$GetLevelFormula`, LU dans `global-metadata.dat` (cf. l'en-tete).
DEBUFFS = (EffectType.Pinned,                          # 0x429 = 1065  -- UI « Suppressed »
           EffectType.Stunned,                         # 0x48a = 1162  -- composite
           EffectType.Taunted_OnlySpecificTargets,     # 0x1b  = 27    -- composite, PAS 25/26/1237
           EffectType.ThrillSeekers)                   # 0x59a = 1434  -- UI « Thrilled »

#: cle du compteur dans le `unit_state`, posee par `runner/components.py::
#: debuffed_units_in_range_count` et lue par la `CreateActiveCondition`.
CARRIER_COUNT_KEY = "debuffed_units_in_range"
#: callable `(owner_id) -> int | None` pose dans le contexte du canal CRIT par `_crit_board`
CTX_COUNT_OF = "debuffed_units_in_range_of"
#: callable `(owner_id) -> (hp, hp_max)` -- substrat du `HealthPctIsBelowOrEqual(Owner, ...)`
CTX_HEALTH_OF = "unit_health_of"
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(effet)`
CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF


def _const(key: str) -> "int | None":
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config, <key>)` -- lecture
    du gameconfig, jamais un litteral en dur. `None` = constante absente (le noeud se tait)."""
    return ability_var(_ABILITY_ID, key, is_constant=True)


def debuffed_units_in_range_selector():
    """L'ARBRE DSL de `...IntoxicatingElixir_ExtraCritDmgEffect$$GetLevelFormula` ancre sur
    `Tiles(Owner)` -- c'est-a-dire `$$GetCalculateLevel` (doctrine #149 : l'artefact natif est un
    ARBRE, donc le port est un arbre, pas une boucle recablee) :

        Min( Count( EntitiesWithAnyEffect(
                        SurroundingUnits(Tiles(Owner@+0x30), range, unique: 1,
                                         includeCenter: 1, selectionType: 3),
                        [Pinned, Stunned, Taunted_OnlySpecificTargets, ThrillSeekers] ) ),
             Get(nrOfUnits) )

    `Tiles(Owner)` (`UnitsMainTilesSelector$$Select` = `GetMainTile` PAR ENTITE) et non `Owner` nu :
    sur une unite MULTI-HEX le natif ancre le disque sur la SEULE main tile, la ou passer l'entite
    unionnerait le voisinage de tous ses pieds (`_origin_tiles`). Aucun des quatre porteurs n'est
    multi-hex aujourd'hui -- on ecrit quand meme ce que le natif ecrit.

    `include_center=True` est le litteral `1` du 4e argument (`includeCenter`), relu au
    DESASSEMBLAGE (`mov byte [rsp+0x20], 1`) : le PORTEUR compte pour lui-meme s'il est debuffe.
    C'est l'inverse d'`AdjacentFriends`, qui EXCLUT son centre (`op_Subtraction unit`).

    Import PARESSEUX de `Count`/`Min` : `entities/formulas` est assemble APRES le package
    `entities/effects` (meme garde anti-cycle et meme convention que `kardiocore_galvanus`,
    `amulet_of_the_voidwyrm` et `supa_cybork_body`)."""
    from ...formulas import Count, Min

    rng = _const(_CONST_RANGE)
    cap = _const(_CONST_NR_OF_UNITS)
    disc = SurroundingUnits(Tiles(Owner()), Const(int(rng or 0)),
                            include_center=True, selection_type=_SEL)
    count = Count(EntitiesWithAnyEffect(disc, [int(e) for e in DEBUFFS]))
    return Min(count, Const(int(cap))) if cap is not None else count


class IntoxicatingElixirEffect(BaseEffect):
    """`IntoxicatingElixir` (0x5b3 = 1459) -- owner-effect PERMANENT de la relique
    `IntoxicatingElixir` : quand son porteur est l'ATTAQUANT d'un coup CRITIQUE, le degat de crit est
    AUGMENTE de `extraCritDmg[niveau de relique] x min(<unites DEBUFFEES a portee 2 du porteur,
    porteur COMPRIS>, 6)`, le tout DOUBLE si le porteur est a `healthPct` % de vie ou moins.

    Second `ForAddition` porte de l'axe crit-DEGAT cote RELIQUE (apres `KardiocoreGalvanus`), et le
    PREMIER dont la magnitude porte un facteur CONDITIONNEL."""

    # La `CreateActiveCondition` est GEOMETRIQUE (`AmountIsGreaterThanZero(GetLevelFormula(...))`) :
    # elle rebascule des qu'une unite bouge OU qu'un debuff est pose/retire, et le natif la reevalue
    # (`RefreshEffectsOperation$$RefreshEffect` -> `Activate`/`DeactivateEffect`). La condition
    # PORTEE fait donc foi sur le flag `IsActive` capte -- meme arbitrage qu'`AmuletOfTheVoidwyrm`
    # et `SupaCyborkBody`, l'inverse de `KardiocoreGalvanus` (dont la condition est constante VRAIE).
    active_condition_ported = True

    @staticmethod
    def _debuffed_in_range(ctx: "Mapping | None") -> "int | None":
        """`GetCalculateLevel()` EVALUE pour le PORTEUR de CETTE instance.

        Le canal pose `owner_id` par porteur (mirror de l'ecriture `AbilityEntities+0x18` que la
        boucle native fait a chaque iteration), et `_crit_board` pose le callable
        `debuffed_units_in_range_of` -- paresseux, donc rien n'est calcule tant qu'aucune instance ne
        le demande.

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
        `IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel` (il appelle le slot
        `CalculateLevel`, compare, et ECRIT si ca differe). Le port privilegie donc le compteur
        RECALCULE, qui suit l'etat courant du board, et retombe sur le niveau CAPTE quand aucun
        `state` n'est threade (probe/test offline).

        ⚠ Ce niveau n'est PAS le niveau d'ability : `self.level` est le niveau de l'EFFET
        (`decisionView.effects[].level`), `_ability_state` rend l'autre. Les confondre lirait
        `extraCritDmg[1] = 295` au lieu du palier reel."""
        n = self._debuffed_in_range(ctx)
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

        Callable absent (contexte sans `state`) -> repli sur les niveaux que l'effet porte deja."""
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
        permissif -- meme foyer de raisonnement que `KardiocoreGalvanusExtraCritDmgEffect`."""
        c = att_ctx or {}
        oid, aid = c.get("owner_id"), c.get("att_id")
        return oid is not None and aid is not None and oid == aid

    def _health_multiplier(self, ctx: "Mapping | None") -> int:
        """`ConditionalAmount( HealthPctIsBelowOrEqual(Owner@+0x30, Get(healthPct)),
        <DSLFormulas+0x28> = Direct(2), <DSLFormulas+0x20> = Direct(1) )`.

        C'est une MAGNITUDE, pas un gate : sans la condition le bonus vaut `x1`, il ne disparait pas
        (meme forme que le `If(HasTrait(...))` de `RelicBoltPistol`).

        `IdunBattleLogic.Entities.DSLTriggers$$HealthPctIsBelowOrEqual(unit, percentage)` alloue un
        `IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger` sur la stat
        **5 = Health** ; son `$$ShouldTrigger` compare `GetStat(5, CURRENT) / GetStat(5, MAXIMUM)` a
        `pct/100` en Fix64 (`op_LessThanOrEqual`) -- comparaison INCLUSIVE. Le port l'ecrit en
        ENTIERS (`100*hp <= pct*max`), exactement comme `VisionsOfHeresyExtraPierceEffect.is_active`
        et `HammerOfWrath_ConditionalDamageEffect` : pour des PV entiers la division Fix64 ne
        bascule jamais autrement.

        TRI-ETAT : PV NON MESURES (callable ou `owner_id` absent, PV nuls) => branche NON DOUBLEE.
        C'est la borne BASSE, celle qui ne peut pas SUR-estimer le bonus -- meme arbitrage que
        `RelicBoltPistol._amount` sur son `If(HasTrait(Target))`."""
        c = ctx or {}
        fn, oid = c.get(CTX_HEALTH_OF), c.get("owner_id")
        pct = _const(_CONST_HEALTH_PCT)
        if fn is None or oid is None or pct is None:
            return _SINGLE
        hp, mx = fn(oid)
        if hp is None or not mx:
            return _SINGLE
        return _DOUBLE if 100 * int(hp) <= int(pct) * int(mx) else _SINGLE

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` = `AmountIsGreaterThanZero(GetLevelFormula(Tiles(Owner)))`, ou
        `AmountIsGreaterThanZero(amount)` = `AmountIsGreaterAbilityTrigger(amount, minAmount =
        <DSLFormulas+0x18> = Direct(0))` -- surcharge `IAmountFormula` tranchee par l'ADRESSE du
        tail-call (sa voisine prend un `ITargetsSelector`).

        Cle ABSENTE = **non mesure** -> on NE FERME PAS (degradation fidele, meme regime
        qu'`AmuletOfTheVoidwyrm` / `SupaCyborkBody`). Cote COMBAT la cle EST posee :
        `UnitEffectStateView` la calcule paresseusement des que le porteur est SUR le plateau."""
        n = (unit_state or {}).get(CARRIER_COUNT_KEY)
        return True if n is None else int(n) > 0

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `...IntoxicatingElixir_ExtraCritDmgEffect$$CreateCritDamageBonus` :

            EffectBonus.ForAddition( get_OwnerIsCaster,
                                     Multiply( Multiply( ConfigVar(0x42 = extraCritDmg,
                                                                   GetAbilityState(effet),
                                                                   config@+0x60),
                                                         EffectLevel(Effect@+0x38) ),
                                               ConditionalAmount(HealthPctIsBelowOrEqual(Owner,
                                                                     Get(healthPct)),
                                                                 Direct(2), Direct(1)) ) )

        Retour ENTIER POSITIF : `IdunBattle.Core.Services.DamagePrediction$$
        GetCritDamageBonusFromEffects` accumule litteralement `addition - subtraction`, et son
        consommateur est `Math.Max(0, GetStat(10) + somme)` dans `$$CalculateCriticalDamage` -- le
        clamp bas ne peut donc pas mordre sur un terme positif (contrairement aux `ForSubtraction`,
        qui exigent une garde de saturation).

        Les etages sont SEPARES et chacun peut se taire independamment (aucun scalaire fitte) :
          1. `get_OwnerIsCaster`  -- le porteur est-il l'ATTAQUANT ?
          2. `EffectLevel`        -- le compteur PLAFONNE, tri-etat `None` = non mesure ;
          3. l'`AbilityState`     -- niveau/multiplicateur de la relique sur le porteur ;
          4. `ConfigVar`          -- `extraCritDmg[niveau]`, relu du gameconfig ;
          5. `ConditionalAmount`  -- `x2` si `HealthPct(Owner) <= healthPct`, sinon `x1` ;
          6. les deux `Multiply`  -- le produit, puis le signe de `ForAddition`."""
        if not self._owner_is_caster(att_ctx):                 # 1
            return None
        n = self._effect_level(att_ctx)                        # 2
        if n is None:
            return None
        lvl, mult = self._ability_state(att_ctx)               # 3
        v = ability_var(_ABILITY_ID, _VAR_KEY, lvl, multiplier_pct=mult)   # 4  ConfigVar(0x42)
        if v is None:
            return None
        amount = int(v) * int(n) * self._health_multiplier(att_ctx)       # 5-6  Multiply x2
        return amount or None                                  #      ForAddition
