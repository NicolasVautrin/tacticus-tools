"""`AmuletOfTheVoidwyrm_CritDamageReduction` (0x5b4 = **1460**) -- l'axe REDUCTION du canal
crit-DEGAT : la relique qui retranche du degat critique RECU, proportionnellement aux summons et
decoys allies adjacents au porteur. #589-r1-r1-r2-r1.

## IDENTITE -- TROIS enums, et deux d'entre eux valent 1460 sans etre le meme objet

    EffectType            0x5b4 = 1460 = AmuletOfTheVoidwyrm_CritDamageReduction  <- CET effet
    TriggeredAbilityType  0x5b8 = 1464 = AmuletOfTheVoidwyrm                      <- sa CONFIG
    TriggeredAbilityType  0x5b4 = 1460 = TalismanOfRage                           <- une AUTRE relique

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AmuletOfTheVoidwyrmAbility$$GetEffectType` rend
litteralement `0x5b4`, et le `.ctor` de l'effet, RELU OCTET A OCTET, porte `mov edx, 0x5b8` :

    ba b8 05 00 00                    ; mov  edx, 0x5b8 = 1464
    e8 <rel32>                        ; call IdunBattle.Core.AbilityOrEffect$$op_Implicit
                                      ;   surcharge tranchee par son ADRESSE : son corps appelle
                                      ;   `AbilityOrEffect$$set_TriggeredAbility` (les surcharges
                                      ;   sont homonymes, elles ne se distinguent pas au nom)
    41 b0 01                          ; mov  r8b, 1  = hasAutomaticActivation
    e8 <rel32>                        ; call IdunBattle.Entities.Effects.BaseEffect$$.ctor

=> la config lue est celle de la TRIGGERED `AmuletOfTheVoidwyrm`, et sa seule variable est
`critDmgReduction` (10 paliers, `[390, 411, ..., 579]` au gameconfig). Confondre les deux 1460
ferait lire la config de `TalismanOfRage` -- c'est le piege « qualifier les enums » a l'etat pur.

## POSE -- owner-effect PERMANENT, a l'init de l'ability

`classes.tsv` : `AmuletOfTheVoidwyrmAbility` derive d'`IdunBattle.Entities.Abilities.
AOwnerEffectTriggeredAbility`, dont le `CreateBehaviour` (corps de BASE) est

    If( <trigger de la sous-classe>,
        AddEffect( GetEffectType() = 0x5b4,
                   AbilityState(entities, Owner@DSLSelectors+0x30, <l'ability elle-meme>),
                   source  = Owner@DSLSelectors+0x30,
                   targets = Owner@DSLSelectors+0x30,
                   turns   = <zeroe>  ->  PERMANENT ) )

et son `CreateTrigger` = `OnOwnerSpecificAbilityInit(<this+0x10>)`. Donc : **source == porteur ==
Owner**, pose une fois a l'initialisation, jamais expiree -- ce qui l'eteint est sa
`CreateActiveCondition`, pas une duree.

C'est ce qui rend le port du niveau EXACT : l'`AbilityState` bake dans l'`EffectComponent+0x18` est
celui de la relique SUR SON PORTEUR, c'est-a-dire l'etat TERTIAIRE
(`TertiaryAbilityLevel` / `TertiaryAbilityVariablesMultiplierPercentage`, cf. `UnitFactory$$Build`
et `case-237`). Le port le relit par le foyer UNIQUE
`runner/operations/triggers/base.py::triggered_ability_state`, celui-la meme que #357 a pose pour
`DawnBlade` -- et il est exact ICI parce que la source EST le porteur.

## LE CANAL -- `ForSubtraction`, et c'est la seule difference de forme avec 1578

`IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$
CreateCritDamageBonus` (mirror du decompile ; `ForSubtraction` y est INLINE par ghidra, il se
reconnait a l'OFFSET ECRIT dans la struct `EffectBonus` -- `+0x00` = trigger, `+0x10` = addition,
`+0x18` = subtraction ; ici c'est `+0x18` qui recoit le montant, `+0x10` reste a 0) :

    EffectBonus.ForSubtraction( get_OwnerIsTarget,
                               GetCritDmgReductionAmount(),
                               AbilityOrEffect.op_Implicit(...) )

Le trigger est `get_OwnerIsTarget` **SEUL** -- aucun `op_BitwiseAnd`, contrairement a
`EmpyricAmbushEffect$$CreateCritDamageBonus` qui le combine avec `IsValidAttackForBuff()`.

`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(Owner@DSLSelectors+0x30,
Target@DSLSelectors+0x60)` : « le PORTEUR de cet effet est-il le DEFENSEUR du coup ? ». Les deux
canaux crit natifs construisent leur `AbilityEntities` en `(attacker, attacker, defender)` puis
ECRASENT `AbilityEntities+0x18` (`Owner`) par le porteur de l'effet courant a chaque iteration --
c'est ce fait qui a impose l'elargissement du balayage a `board_effect_carriers` (#589-r1-r1), et
c'est lui qui rend CET effet atteignable.

CONSOMMATION, relue : `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects`
accumule litteralement `addition - subtraction` (`uVar14 += (int)v - (int)(v >> 32)`), et
`$$CalculateCriticalDamage` fait `Math.Max(0, GetStat(10) + somme)`. Le port rend donc un entier
**NEGATIF** : c'est le mirror exact du terme soustractif, pas une convention locale.

## LA MAGNITUDE -- un PRODUIT, pas un scalaire

`...$$GetCritDmgReductionAmount` (mirror) :

    DSLFormulas.Multiply( ConfigVar(0x97 = critDmgReduction, GetAbilityState(effect), config@+0x60),
                          GetAdjacentFriendlySummonsAndDecoysCount() )

`AbilityVariableType 0x97 = 151 = critDmgReduction` (`enums.tsv`, jamais recopie du decompile).
`AmuletOfTheVoidwyrm` n'a PAS de `variablesAffectedByRarityBonus` au gameconfig -> le multiplicateur
ne mord pas ; on le passe quand meme, parce que c'est `ability_var` (donc la config) qui decide.

## LE COMPTEUR -- un ARBRE DSL, et son union NE DEDOUBLONNE PAS

`...$$GetAdjacentFriendlySummonsAndDecoysCount` (mirror, dans l'ordre du decompile) :

    Count( UnitsWithTrait( AdjacentFriends(Owner@+0x30, unique: 1, selectionType: 3), 0x2   = Summon )
           op_Addition
           UnitsWithTrait( AdjacentFriends(Owner@+0x30, unique: 1, selectionType: 3), 0x41d = Decoy ) )

Resolutions (`enums.tsv`) : `UnitTrait 0x2 = 2 = Summon`, `UnitTrait 0x41d = 1053 = Decoy`.

⚠ La surcharge d'`AdjacentFriends` est tranchee par la POSITION de ses arguments : l'appel passe
`(this, <Owner@+0x30>, 1, 3)`, or les deux surcharges natives sont `(this, unit, unique,
selectionType)` et `(this, unit, unitTile, unique)` -- un `1` litteral ne peut pas etre un
SELECTEUR de tuile, donc c'est la premiere. Son corps :

    Friends( reference = unit,
             Units(AdjacentTiles(unit), unique, selectionType) op_Subtraction unit,
             selectionType )

La reference d'equipe EST le centre : le port passe donc `reference=Owner()` EXPLICITEMENT. Le
defaut (`ctx.caster`) serait exact tant que le contexte est bati sur le porteur, mais l'ecrire
evite de dependre du montage.

⚠ **`op_Addition` CONCATENE, il ne fusionne pas.** `IdunBattle.DSL.TargetsSelector$$op_Addition`
construit un `CombinedSelector` de mode **1**, et `IdunBattle.DSL.CombinedSelector$$SelectUnion` est
litteralement `new List(n1 + n2); AddRange(left); AddRange(right)` -- AUCUN dedoublonnage. Une unite
qui porterait A LA FOIS `Summon` et `Decoy` compterait donc **DEUX FOIS**. Le port mirrore ce quirk
(`Union` = concatenation, `entities/selectors/units.py`). Il n'est pas OBSERVABLE sur ce build : les
deux seuls porteurs de `Decoy` du gameconfig (`genesDecoy`, `genesSmnDecoy`) ont `['Steppable',
'Decoy']` et AUCUNE unite ne porte les deux traits -- residu documente, pas comble.

## LA CONDITION D'ACTIVITE -- le MEME compteur, compare a zero

`...$$CreateActiveCondition` = `DSLTriggers.AmountIsGreaterThanZero(
GetAdjacentFriendlySummonsAndDecoysCount() )`, ou `AmountIsGreaterThanZero(amount)` =
`AmountIsGreaterAbilityTrigger(amount, minAmount = <DSLFormulas+0x18> = Direct(0))`.

Consequence de HARNAIS, et elle compte : l'effet est **INACTIF** tant qu'aucun summon/decoy allie
n'est adjacent, donc **ABSENT du canal `decisionView.effects`** (ACTIF-ONLY, GROUND TRUTH #100) --
meme motif exact qu'`AnvilShield_BlockChanceBelowHealthCap`, `HammerOfWrath_ConditionalDamage`,
`ModifiedExoarmour_ExtraDmg` et `VisionsOfHeresy_*`.

(`...$$GetCalculateLevel` rend le MEME compteur : c'est le « niveau » d'affichage de l'effet, lu par
`AmuletOfTheVoidwyrm_CritDamageReductionEffectVisuals$$OnEffectLevelIncreased`. Aucun observable de
combat -- non porte, et c'est dit plutot que suppose.)
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ....dsl.base import Const
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentFriends, Union, UnitsWithTrait
from ...traits.unit_trait import UnitTrait
import engine.entities.effects.ctx_keys as _ctx_keys      # #1042-r5 : foyer UNIQUE des chaines de cle de ctx

_ABILITY_ID = "AmuletOfTheVoidwyrm"      # TriggeredAbilityType 0x5b8 = 1464 (la CONFIG de la relique)
_VAR_KEY = "critDmgReduction"            # AbilityVariableType 0x97 = 151
#: cle du compteur, posee par le foyer `runner/components.py::adjacent_friendly_summons_and_decoys_count`
CARRIER_COUNT_KEY = "adjacent_friendly_summons_and_decoys"
#: callable `(owner_id) -> int | None` pose dans le contexte du canal CRIT par `_crit_board`
CTX_COUNT_OF = "adjacent_friendly_summons_and_decoys_of"
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(effect)`
CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF


def adjacent_friendly_summons_and_decoys_selector():
    """L'ARBRE DSL de `IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$
    GetAdjacentFriendlySummonsAndDecoysCount`, noeud par noeud (doctrine #149 : l'artefact natif est un
    SELECTEUR, donc le port est un arbre, pas une boucle recablee).

        Count( UnitsWithTrait(AdjacentFriends(Owner, 1, 3), Summon)
               + UnitsWithTrait(AdjacentFriends(Owner, 1, 3), Decoy) )

    Le natif construit DEUX `AdjacentFriends` distincts (deux appels, deux allocations) : on fait
    pareil plutot que de partager le noeud -- l'evaluation est identique, mais la structure citee
    l'est aussi. Import PARESSEUX : `entities/selectors` et `entities/formulas` sont assembles APRES
    le package `entities/effects` (garde anti-cycle, meme convention que les autres modules d'effet).
    """
    from ...formulas import Count

    def _adjacent_friends():
        # `DSLSelectors$$AdjacentFriends(this, unit = Owner@+0x30, unique = 1, selectionType = 3)`
        # = `Friends(reference = Owner, Units(AdjacentTiles(Owner), 1, 3) - Owner, 3)`.
        return AdjacentFriends(Owner(), Const(1), Owner())

    return Count(Union(UnitsWithTrait(_adjacent_friends(), int(UnitTrait.Summon)),
                       UnitsWithTrait(_adjacent_friends(), int(UnitTrait.Decoy))))


class AmuletOfTheVoidwyrmCritDamageReductionEffect(BaseEffect):
    """`AmuletOfTheVoidwyrm_CritDamageReduction` (0x5b4 = 1460) -- owner-effect PERMANENT de la
    relique `AmuletOfTheVoidwyrm` : quand son porteur est la CIBLE d'un coup CRITIQUE, le degat de
    crit de l'attaquant est reduit de `critDmgReduction[niveau de relique] x <nombre de summons et
    decoys allies adjacents au porteur>`.

    C'est le premier implementeur porte de l'axe REDUCTION du canal crit-DEGAT (`ForSubtraction`) --
    les quatre autres (`InescapableAccuracy_extraCritDmg`, `WarHowl_ExtraDamage_Unstoppable`,
    `SmashaEad`, `EmpyricAmbush`) sont tous des `ForAddition`."""

    # La `CreateActiveCondition` est GEOMETRIQUE : elle rebascule des qu'une unite bouge, et le natif
    # la reevalue (`RefreshEffectsOperation$$RefreshEffect` -> `Activate`/`DeactivateEffect`). La
    # condition PORTEE fait donc foi sur le flag `IsActive` capte -- meme arbitrage que
    # `StructuralAnalyser_Visual`, dont la condition est de la meme famille.
    active_condition_ported = True

    @staticmethod
    def _adjacent_count(ctx: "Mapping | None") -> "int | None":
        """`GetAdjacentFriendlySummonsAndDecoysCount()` EVALUE pour le PORTEUR de CETTE instance.

        Le canal pose `owner_id` par porteur (mirror de l'ecriture `AbilityEntities+0x18`), et
        `_crit_board` pose le callable `adjacent_friendly_summons_and_decoys_of` -- paresseux, donc
        rien n'est calcule tant qu'aucune instance ne le demande.

        TRI-ETAT : callable ou `owner_id` ABSENT => `None` = « non mesure », JAMAIS 0. Un 0 invente
        annulerait le produit et ferait passer une reduction reelle pour une absence de reduction."""
        c = ctx or {}
        fn = c.get(CTX_COUNT_OF)
        oid = c.get("owner_id")
        if fn is None or oid is None:
            return None
        n = fn(oid)
        return None if n is None else int(n)

    def _ability_state(self, ctx: "Mapping | None") -> tuple:
        """`GetAbilityState(effect)` -> `(level, multiplier)` de l'`AbilityState` bake a la pose.

        `AOwnerEffectTriggeredAbility$$CreateBehaviour` bake `AbilityState(entities, Owner, <cette
        ability>)`, et l'effet est pose SUR l'Owner : source == porteur, donc le couple se relit sur
        le porteur (`owner_id`). C'est l'etat TERTIAIRE quand la relique est EQUIPEE
        (`BC.Units[].TertiaryAbilityLevel`), l'etat PASSIF quand elle est cablee en dur au kit d'un
        npc -- exactement l'arbitrage de `triggered_ability_state` (#357).

        Callable absent (contexte sans `state` : probe, test offline) -> repli sur les niveaux que
        l'effet porte deja (`ability_level`, sinon le stack `level`), c'est-a-dire le comportement
        de toutes les autres classes d'effet."""
        c = ctx or {}
        fn, oid = c.get(CTX_ABILITY_STATE_OF), c.get("owner_id")
        if fn is not None and oid is not None:
            lvl, mult = fn(oid, _ABILITY_ID)
            if lvl is not None:
                return int(lvl), int(mult if mult is not None else 100)
        lvl = self.ability_level if self.ability_level is not None else self.level
        return lvl, int(self.ability_variables_multiplier or 100)

    def _owner_is_target(self, att_ctx: "Mapping | None" = None) -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(Owner@+0x30,
        Target@+0x60)`. Identite NON PROUVEE (une des deux cles absente) => noeud FAUX, jamais
        permissif -- meme foyer de raisonnement qu'`EmpyricAmbushEffect._owner_is_target`."""
        c = att_ctx or {}
        oid, tid = c.get("owner_id"), c.get("tgt_id")
        return oid is not None and tid is not None and oid == tid

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` = `AmountIsGreaterThanZero(GetAdjacentFriendlySummonsAndDecoys
        Count())`, ou le `minAmount` natif est `<DSLFormulas+0x18>` = `Direct(0)`.

        Cle ABSENTE = **non mesure** -> on NE FERME PAS (degradation fidele, meme regime que
        `StructuralAnalyserVisualEffect.is_active` et `ModifiedExoarmour_ExtraDmg`). Cote COMBAT la
        cle EST posee : `UnitEffectStateView` la calcule paresseusement des que le porteur a une
        equipe et une tuile."""
        n = (unit_state or {}).get(CARRIER_COUNT_KEY)
        return True if n is None else int(n) > 0

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `...AmuletOfTheVoidwyrm_CritDamageReductionEffect$$CreateCritDamageBonus` :

            EffectBonus.ForSubtraction( get_OwnerIsTarget,
                                        Multiply( ConfigVar(0x97 = critDmgReduction,
                                                            GetAbilityState(effect), config@+0x60),
                                                  GetAdjacentFriendlySummonsAndDecoysCount() ) )

        Retour ENTIER NEGATIF : `GetCritDamageBonusFromEffects` accumule `addition - subtraction`,
        et son consommateur est `Math.Max(0, GetStat(10) + somme)` dans `CalculateCriticalDamage`.

        Les etages sont SEPARES et chacun peut se taire independamment (aucun scalaire fitte) :
          1. `get_OwnerIsTarget`  -- le porteur est-il le defenseur ?
          2. le COMPTEUR          -- tri-etat, `None` = non mesure ;
          3. l'`AbilityState`     -- niveau/multiplicateur de la relique sur le porteur ;
          4. `ConfigVar`          -- `critDmgReduction[niveau]`, relu du gameconfig ;
          5. `Multiply`           -- le produit, puis le signe de `ForSubtraction`."""
        if not self._owner_is_target(att_ctx):                 # 1
            return None
        n = self._adjacent_count(att_ctx)                      # 2
        if n is None:
            return None
        lvl, mult = self._ability_state(att_ctx)               # 3
        v = ability_var(_ABILITY_ID, _VAR_KEY, lvl, multiplier_pct=mult)   # 4  ConfigVar(0x97)
        if v is None:
            return None
        amount = int(v) * int(n)                               # 5  Multiply
        return -amount if amount else None                     #    ForSubtraction
