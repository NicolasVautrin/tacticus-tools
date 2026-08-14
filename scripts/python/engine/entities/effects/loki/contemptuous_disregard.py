"""`ContemptuousDisregard` -- ability **MYTHIQUE** de Machine of War (`TriggeredAbilityType`
0x5aa = **1450**), porteurs `blackForgefiend` (MoW `lineup`) et `blackNpcMowForgefiend` (MoW `npc`).
Voie TERTIAIRE (`BC.Units[].TertiaryAbility`), montage ECRIT `rl_duel build --equip-mythic
"blackForgefiend:ContemptuousDisregard:<lvl>"` (#999).

===================================================================================================
LES ARTEFACTS NATIFS (decompile ghidra, build `rnca9r7q6c`)
===================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ContemptuousDisregardAbility` -- parent
`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` (`frida/classes.tsv`), et la classe
n'override QUE `$$GetEffectType`, dont le corps ENTIER est `return 0x5a3` (= 1443
`EffectType.ContemptuousDisregard_DamageReduction`) : l'appariement ability -> effet est LU, pas
devine. Le reste vient de la base :

    AOwnerEffectTriggeredAbility$$CreateTrigger   = OnOwnerSpecificAbilityInit(this.AbilityType)
    AOwnerEffectTriggeredAbility$$CreateBehaviour = If( CreateCondition(abilityState),
        AddEffect( GetEffectType(), AbilityState(Owner@<DSLSelectors+0x30>, AbilityType(this)),
                   source = Owner, targets = Owner, options = <Nullable ZERO> ) )

-> owner-effect PERMANENT pose a l'init, exactement le patron `Vitarus` (#1005) / `NornCrown`
(#1011) / `MoreGitzOverEre` (#1025). C'est ce qui range l'ability dans
`factory.ABILITY_INIT_OWNER_EFFECTS`, JAMAIS dans `ABILITY_CLASSES` (elle est TRIGGERED : ni
`TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne la concernent).

`IdunBattle.Entities.Effects.Loki.ContemptuousDisregard_DamageReductionEffect` (`EffectType`
0x5a3 = **1443**), parent `IdunBattle.Entities.Effects.BaseEffect` (`frida/classes.tsv`).
DEUX faces propres dans `frida/methods.tsv` :

    $$CreateEffectDamageMalusForDefense (corps INLINE) :
        trigger = DSLTriggers.get_OwnerIsTarget                     <- SEUL noeud
        montant = DSLFormulas.ConfigVar( AbilityVariableType.dmgReductionPct = 0x46,
                                         BaseEffect.GetAbilityState(this), config@this+0x60 )
        -> EffectBonus.ForPercentDecrease( trigger, montant )

    $$CreateTargetSelector :
        DSLSelectors.Filter(
            DSLSelectors.UnitsWithRarity(
                DSLSelectors.Friends( Owner@<DSLSelectors+0x30>, AllUnits(), 3 ),
                idun.meta.Rarity.Mythic = 5, 3 ),
            DSLTriggers.HasTileStatusEffect( DSLSelectors.Tiles( <DSLSelectors+0x68> ) ) )

⚠ **LE `ForPercentDecrease` EST LU, PAS DEDUIT D'UN NOM.** Le corps est inline, donc il n'y a
aucun `call` a apparier. Ce qui tranche est la CONSTRUCTION, identique bit pour bit a celle de
`IdunBattle.Entities.Effects.EffectBonus$$ForPercentDecrease` : les MEMES deux classes globales
(`DAT_183395500` puis `DAT_1833fe9f0`), le premier ctor recevant le litteral `0xffffffff` (= -1),
le second composant `(<ce -1>, <le montant>)`, et le resultat ecrit au champ **+0x08** de la
struct `EffectBonus`. Or `...$$ForPercentIncrease` ecrit le montant BRUT en +0x08 sans construire
quoi que ce soit : le slot est PARTAGE, et c'est la negation `Multiply(-1, pct)` qui separe les
deux fabriques. Lire << +0x08 => PercentIncrease >> aurait donc INVERSE le signe.

===================================================================================================
CE QUI EST PORTE ICI, ET CE QUI NE L'EST PAS
===================================================================================================

PORTE -- la face DEGAT de l'effet (`create_effect_damage_malus_for_defense`), sans aucun gate,
parce que le trigger natif n'a QUE `get_OwnerIsTarget` (satisfait structurellement : la boucle
defenseur n'itere que les effets de la CIBLE du coup).

NON PORTE -- le SELECTEUR d'aura, et c'est un BLOCAGE de capteur, pas un choix :
`UnitsWithRarity(..., 5)` lit `GetBaseUnitComponent(entity)+0x74`
(`IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select`, meme champ que
`IdunBattle.Entities.UnitExtensions$$HasRarity` et
`IdunBattle.Entities.Triggers.HasRarityTrigger$$ShouldTrigger`), et **aucun canal de rarete
n'existe cote port** -- ni `decisionView`, ni `combatSnapshot`, ni `unitAbilityStates`. Meme
verrou que `#1025-r1`. La consequence est BORNEE et RESTRICTIVE : le port ne DECIDE pas qui
beneficie de l'aura, il CONSOMME les instances que le natif a materialisees et que
`decisionView.effects` publie -- exactement le regime de `GuardianOrganism_DamageReduction` (#89)
et de `VexillaMagnifica_DmgReduction`. Sur un chemin purement OFFLINE (aucune capture), seule
l'instance de l'OWNER est seedee (`ABILITY_INIT_OWNER_EFFECTS`), et les beneficiaires d'aura
manquent : c'est un MANQUE, jamais un sur-compte.

⚠ `HasTileStatusEffect(Tiles(<+0x68>))` -- second conjoint du `Filter`, non porte pour la meme
raison (il ne se pose qu'au sein du selecteur). i2 concorde : l'aura ne protege que les allies
Mythiques qui se tiennent sur une tuile portant un effet de statut.

===================================================================================================
MAGNITUDE -- le niveau est celui de la TERTIAIRE, jamais celui des passifs
===================================================================================================

`ConfigVar(0x46)` est resolu contre `GetAbilityState(this)` = l'`AbilityStateReference` **BAKEE**
dans `EffectComponent+0x18` a la pose (#382), c.-a-d. celle de la MoW porteuse. Pour une ability
TERTIAIRE, `IdunBattle.Entities.Factories.UnitFactory$$Build` la fabrique depuis
`config+0xc0 TertiaryAbilityLevel` -- mesure `level 1..4 / mult 100`, la ou les passifs du MEME
porteur portent `50 / 180` en runner normalise (#1005/#1009). Le port lit donc
`self.ability_level` / `self.ability_variables_multiplier`.

Gameconfig `ContemptuousDisregard` : `dmgReductionPct = [10, 13, 16, 20]` (4 paliers), et
`variablesAffectedByRarityBonus = ['dmgReductionPct']` -> le multiplicateur MORD.

⚠ AUCUN repli sur `self.level` : `level` est le niveau de STACK capte
(`decisionView.effects[].level`), pas un `AbilityState`. Les confondre donnerait un palier
plausible et FAUX. `AbilityState` absent -> inerte (degradation restrictive, fidele au
`ConfigAmount$$Calculate` qui ne trouve aucun tableau).
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_percent_decrease
from ..base import BaseEffect
from ..magnitude import ability_var

#: Cle gameconfig de l'ability -- la config qu'indexe `ConfigVar`.
ABILITY_ID = "ContemptuousDisregard"

#: `AbilityVariableType` 0x46 = 70 (`frida/enums.tsv`), resolu par son NOM. L'ordinal seul ne
#: discrimine PAS : `AbilityConstantType` 69/70 nomment `nrOfRounds`/`summonId`, rien a voir.
VAR_DMG_REDUCTION_PCT = "dmgReductionPct"


class ContemptuousDisregardDamageReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ContemptuousDisregard_DamageReductionEffect$$CreateEffectDamageMalusForDefense`
    (`EffectType` 0x5a3 = 1443, nom capte `ContemptuousDisregard_DamageReduction`).

    MIRROR 1:1 : `EffectBonus.ForPercentDecrease( get_OwnerIsTarget, ConfigVar(0x46) )`.
    Cf. l'en-tete du module pour l'arbre natif complet et pour la lecture du `ForPercentDecrease`
    inline (le slot +0x08 est PARTAGE avec `ForPercentIncrease` -- c'est le `Multiply(-1, pct)`
    qui separe les deux).

    OBSERVABLE : le porteur de l'effet encaisse `-dmgReductionPct %` sur TOUT degat recu -- aucun
    gate de nature de coup (ni `IsMeleeAttack`, ni `IsRangedAttack`, ni `IsNormalAttack`), aucun
    gate de profil, aucun gate sur l'attaquant. Le contraste avec son jumeau `MastersOfManoeuvre`
    (meme fabrique, meme variable, meme famille de mythique de MoW) est ENTIER : celui-la porte un
    `IsRangedAttack` et celui-ci n'en a pas. Recopier le voisin de forme aurait eteint la
    reduction sur toute la melee."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        # `get_OwnerIsTarget` SEUL : satisfait structurellement sur ce canal (`CalculateDefender
        # ModifiersForPrediction` / `damage_model.defender_modifiers` n'iterent que les effets de
        # la CIBLE du coup). Aucun autre noeud a evaluer -- c'est un RESULTAT de lecture.
        lvl = self.ability_level
        if lvl is None:
            return None                       # `ConfigVar` sans `AbilityState` -> inerte
        red = ability_var(ABILITY_ID, VAR_DMG_REDUCTION_PCT, lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not red:
            return None
        return for_percent_decrease(False, abs(int(red)))   # owner=defenseur (l'effet est sur la cible)
