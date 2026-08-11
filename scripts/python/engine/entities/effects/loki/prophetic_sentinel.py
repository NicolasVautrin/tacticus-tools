"""Les TROIS owner-effects du passif de kit `PropheticSentinel` (`thousSekhetar` << Sekhetar Robot >>,
`TriggeredAbilityType` 0x607 = 1543) -- 1558 / 1559 / 1560.

ARTEFACT NATIF : aucune classe d'effet dediee cote jeu pour ces trois ids -- ce sont des
`IdunBattle.Entities.Effects.StaticStatModifierEffect` GENERIQUES, instancies par la feuille
`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffectToOwner` du `CreateBehaviour` de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PropheticSentinel_AddBuffAbility` (MIRROR 1:1 du
decompile, build `rnca9r7q6c`) :

    AddStaticStatModifierEffectToOwner( 0x616 = 1558 PropheticSentinel_ExtraArmor,
                                        stat = 0x10 = FixedArmor,
                                        Direct( GetVariableForLevel(0x1b = extraArmor) ),
                                        turns = NULL, isHidden = false )
  & AddStaticStatModifierEffectToOwner( 0x617 = 1559 PropheticSentinel_ExtraBlockChance,
                                        stat = 0x7  = BlockChance,
                                        Direct( GetVariableForLevel(0x15 = blockChance) ),
                                        turns = NULL, isHidden = false )
  & AddStaticStatModifierEffectToOwner( 0x618 = 1560 PropheticSentinel_ExtraBlockDamage,
                                        stat = 0x8  = BlockDamage,
                                        Direct( GetVariableForLevel(0x14 = blockDmg) ),
                                        turns = NULL, isHidden = false )

Les trois `op_BitwiseAnd` d'`IdunBattle.DSL.AbilityBehaviour` en font UN seul behaviour.
`turns = NULL` => PERMANENTS (meme regime que `UnbreakableDuty_Health` / `_Damage`).

## Le TRIGGER de ce behaviour est `On(AbilityInit)`, PAS le compte de Psykers -- et c'est mesure

`PropheticSentinel_AddBuffAbility$$CreateTrigger` n'apparait PAS dans `frida/methods.tsv` : son corps
est DEDUPLIQUE (identical code folding) avec
`IdunBattleLogic.Entities.Abilities.Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`,
dont le corps ENTIER est `return <DSLTriggers+0x30>`. Le depart a ete lu dans la TABLE DES POINTEURS
DE METHODES (le metadata declare bien `CreateTrigger` slot 26 ET `CreateBehaviour` slot 28 pour les
DEUX classes du kit ; les entrees consecutives de la table donnent les corps), pas suppose.
`<DSLTriggers+0x30>` est le trigger pre-cache d'`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`
= `On(0x21 = AbilityInit) & <conjoint @+0x70> & get_OwnerIsActor` -- la MEME constante que
`LifewardsAddEffectAbility` / `ListenUpMaggotsAbility` / `LionHelmAbility` (cf.
`triggers/loki/stormboyz_strike.py`, `effects/loki/dark_angels_passives.py`).

=> canal de port = `ABILITY_INIT_OWNER_EFFECTS` (pose au spawn) + `EFFECT_CLASSES` (comportement).
JAMAIS `ABILITY_TRIGGERS` pour CE volet : le compte de Psykers adjacents appartient a l'AUTRE
ability du meme kit (`PropheticSentinel_OverwatchAbility`, cf.
`runner/operations/triggers/loki/prophetic_sentinel.py`), qui ne pose AUCUN de ces trois effets.
L'hypothese inverse (<< un seul trigger partage par les deux classes >>) etait la lecture naturelle
et elle est REFUTEE par la table des pointeurs.

## Les DEUX classes `Effects.Idun.PropheticSentinel_{Chaos,Psyker}Effect` ne sont PAS ces effets

Le build porte `IdunBattle.Entities.Effects.Idun.PropheticSentinel_PsykerEffect` et
`..._ChaosEffect` (toutes deux `StaticStatModifierEffect`, une seule methode propre chacune :
`CreateTargetSelector` = `UnitsWithTrait(AdjacentFriends(Owner@+0x30, 1, 3), 0x3ea = Psyker | 0x7ea
= Chaos, 3)`). Elles ne sont PAS portees ici, pour une raison MESUREE et non par omission :
  * `EffectType` ne contient AUCUN `PropheticSentinel_Psyker` ni `PropheticSentinel_Chaos` -- seuls
    1558/1559/1560 existent, et leurs noms ne collent a aucune des deux classes ;
  * une recherche LITTERALE de `0x616` dans tout le pseudo-C du build ne rend que DEUX fonctions,
    dont une seule pose l'effet : le `CreateBehaviour` ci-dessus. Aucun autre poseur, donc aucune
    projection d'aura par ce kit.
Verdict : classes SANS EffectType => non instanciables par la factory native. Residu #915-r1 (le
mapping EffectType -> classe n'est pas lisible offline dans le port ; la confrontation live est ce
qui tranche, cf. plus bas).

## MAGNITUDES

`GetVariableForLevel` => VARIABLES per-niveau du gameconfig `PropheticSentinel.variables` :
`extraArmor` (9..655), `blockChance` (15/20/25, plateau), `blockDmg` (9..655).
`variablesAffectedByRarityBonus = ['extraArmor', 'blockDmg']` => ces DEUX-LA sont scalees par
l'`AbilityVariablesMultiplierPercentage` ; `blockChance` ne l'est PAS (multiplier passe pour la
forme, comme `VexillaMagnifica` / `SereneUnifier`).

`PropheticSentinel` est un PASSIF (`units.abilities` du kit, voie `passiveAbilities`) => le niveau
qui indexe `variables[level]` est `ability_level` (le niveau de l'ability PASSIVE porte par
l'instance d'effet), pas `active_ability_level`.

## Qualification des enums (le meme id nomme autre chose ailleurs)

    EffectType 1558/1559/1560 PropheticSentinel_ExtraArmor/_ExtraBlockChance/_ExtraBlockDamage
        != TriggeredAbilityType 1558 Helspear (1559/1560 : aucun homonyme)
    TriggeredAbilityType 1543 PropheticSentinel != EffectType 1543 ModifiedExoarmour_PierceReduction
    StatType 0x10 = FixedArmor · 0x7 = BlockChance · 0x8 = BlockDamage
    AbilityVariableType 0x1b = extraArmor · 0x15 = blockChance · 0x14 = blockDmg
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
from ....entities.stats import StatType

_ABILITY_ID = "PropheticSentinel"                 # TriggeredAbilityType 0x607 = 1543


class PropheticSentinelExtraArmorEffect(BaseEffect):
    """`PropheticSentinel_ExtraArmor` (0x616 = 1558) -- +`extraArmor` sur `FixedArmor`, PERMANENT.

    `AddStaticStatModifierEffectToOwner(0x616, 0x10, Direct(ConfigVar(0x1b)), turns = NULL)`.
    `extraArmor` est dans `variablesAffectedByRarityBonus` -> scalee par le multiplicateur."""

    def get_stat_modification_stat(self) -> int | None:
        return StatType.FIXED_ARMOR                                # StatType 0x10

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "extraArmor", self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)


class PropheticSentinelExtraBlockChanceEffect(BaseEffect):
    """`PropheticSentinel_ExtraBlockChance` (0x617 = 1559) -- +`blockChance` sur `BlockChance`,
    PERMANENT.

    `AddStaticStatModifierEffectToOwner(0x617, 0x7, Direct(ConfigVar(0x15)), turns = NULL)`.
    `blockChance` est HORS `variablesAffectedByRarityBonus` -> le multiplicateur est INERTE ici ; il
    est passe pour la forme (meme convention que `VexillaMagnifica`/`SereneUnifier`), pas par
    inadvertance."""

    def get_stat_modification_stat(self) -> int | None:
        return StatType.BLOCK_CHANCE                               # StatType 0x7

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "blockChance", self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)


class PropheticSentinelExtraBlockDamageEffect(BaseEffect):
    """`PropheticSentinel_ExtraBlockDamage` (0x618 = 1560) -- +`blockDmg` sur `BlockDamage`,
    PERMANENT.

    `AddStaticStatModifierEffectToOwner(0x618, 0x8, Direct(ConfigVar(0x14)), turns = NULL)`.
    `blockDmg` est dans `variablesAffectedByRarityBonus` -> scalee par le multiplicateur.

    ⚠ `blockDmg` (0x14) et `blockChance` (0x15) sont ADJACENTS dans `AbilityVariableType` et les
    deux tableaux du gameconfig ont la MEME longueur : les intervertir ne leverait AUCUNE erreur et
    donnerait un +15 d'armure de blocage la ou le natif met +655. Les deux index sont LUS au
    decompile (`GetVariableForLevel(.., 0x15, ..)` precede `0x14` dans le corps), pas deduits du
    nom."""

    def get_stat_modification_stat(self) -> int | None:
        return StatType.BLOCK_DAMAGE                               # StatType 0x8

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "blockDmg", self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)
