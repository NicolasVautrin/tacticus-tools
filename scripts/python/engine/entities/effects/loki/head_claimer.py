"""Les DEUX effets du passif `HeadClaimer` (`TriggeredAbilityType 0x407 = 1031`) de `blackHaarken`
<< Haarken Worldclaimer >> (Black Legion / Chaos) -- #947.

i2 `Abilities/HeadClaimer_CurrentLevelDescription` :
    << For each enemy unit that Haarken has defeated, his attacks deal +{[extraDmg]} Damage for the
    rest of the battle. For each enemy Character that he has defeated, his attacks also score
    +{[extraHit]} hit for the rest of the battle. >>

===================================================================================================
RECENSEMENT PAR LE BLOC `methodPointers` (jamais par grep de nom) -- 4 classes, ce que CHACUNE porte
===================================================================================================

  `IdunBattle.Entities.Effects.Loki.HeadClaimer_ExtraDamageEffect`   (`EffectType 0x404 = 1028`)
      CreateEffectDamageBonusForAttack · GetLocalizationDataInternal
  `IdunBattle.Entities.Effects.Loki.HeadClaimer_ExtraHitsEffect`     (`EffectType 0x405 = 1029`)
      .ctor · CreateEffectHitsBonusForAttack · GetHits · GetLocalizationDataInternal
  `IdunBattleLogic.Entities.Abilities.Active.Loki.HeadClaimerAbility`
      CreateBehaviour · CreateTrigger   (face TRIGGER -> `runner/operations/triggers/loki/head_claimer.py`)
  `IdunBattle.View.AbilityConfigs.Loki.HeadClaimerVisuals`
      ExecuteInternal (+ son itérateur) -- couche VUE, aucune logique de combat.

CE QUI N'EXISTE PAS, et c'est un RESULTAT, pas un oubli :
  * **aucune `CreateActiveCondition`** sur l'un ou l'autre effet -> l'effet est actif des qu'il est
    pose (pas de gate d'activite, donc pas d'`active_condition_ported`) ;
  * **aucune `CreateTargetSelector`** -> ce sont des SELF-effects, jamais des auras ;
  * **aucun `.ctor` propre a `_ExtraDamageEffect`** : IL2CPP l'a DEDUPLIQUE avec celui de
    `_ExtraHitsEffect` -- les deux corps sont byte-identiques (`mov edx, 0x407` puis
    `AbilityOrEffect$$op_Implicit` @`set_TriggeredAbility` puis `BaseEffect..ctor(this, ao, 1)`),
    ce qui se LIT dans les octets, pas dans la table (qui n'a qu'une ligne pour les deux) ;
  * **aucun `GetCurrentBonus` propre** : le corps qu'appelle `CreateEffectDamageBonusForAttack` est
    celui que ghidra etiquette `IdunBattle.Entities.Effects.Loki.
    TerrifyingCrescendo_ExtraDmgEffect$$GetCurrentBonus` -- MEME corps, deux noms (dedup ICF).

===================================================================================================
LES ARBRES (mirror 1:1 du decompile)
===================================================================================================

`IdunBattle.Entities.Effects.Loki.HeadClaimer_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :

    EffectBonus.ForAddition( get_OwnerIsCaster,
                             Multiply( ConfigVar(AbilityVariableType.extraDmg = 8,
                                                 GetAbilityState(this), config@this+0x60),
                                       EffectLevel(Effect@DSLSelectors+0x38) ) )

`IdunBattle.Entities.Effects.Loki.HeadClaimer_ExtraHitsEffect$$GetHits` :

    Multiply( Get( AbilityConfiguration.GetNumberConstant(config@this+0x60,
                                                          AbilityConstantType.extraHit = 0x2b) ),
              EffectLevel(Effect@DSLSelectors+0x38) )

`IdunBattle.Entities.Effects.Loki.HeadClaimer_ExtraHitsEffect$$CreateEffectHitsBonusForAttack` :

    EffectBonus.ForAddition( get_OwnerIsCaster, GetHits() )

## LE GATE EST `get_OwnerIsCaster` SEUL -- DES DEUX COTES, ET C'EST L'ECART AVEC LES JUMEAUX

`HeadClaimer_ExtraDamage` est le QUATRIEME membre de la fratrie `Multiply(ConfigVar(extraDmg),
EffectLevel)` -- apres `BeaconOfRage_ExtraDamage` (1298), `TerrifyingCrescendo_ExtraDmg` (1424) et
`FuelledByFury_ExtraDamage` (1323). Il PARTAGE le corps de magnitude de TerrifyingCrescendo, mais
**PAS son gate** : `TerrifyingCrescendo` porte en plus un `IsRangedAttack` (d'ou son
`if not is_ranged_attack(...)`) ; ici la conjonction n'a QU'UN noeud. Recopier le jumeau aurait
supprime le bonus sur toutes les attaques MELEE de Haarken -- or son attaque normale principale
(`WorldclaimersRefrain`) est melee. Aucun `IsNormalAttack` non plus : le bonus vaut aussi pour les
attaques d'ABILITY (i2 << his attacks >>, sans restriction).

## LE NIVEAU DE L'EFFET EST LE COMPTEUR DE TETES

`EffectLevel` = le nombre d'ennemis vaincus (resp. de Characters vaincus pour l'axe COUPS),
accumule par la face TRIGGER (`runner/operations/triggers/loki/head_claimer.py`, mirror de
`...HeadClaimerAbility$$CreateTrigger` + `$$CreateBehaviour`). **AUCUN cap** : le `max` passe a
`DSLBehaviors$$AddEffectOrIncreaseLevel` est NULL (contraste TerrifyingCrescendo, qui passe
`Direct(GetNumberConstant(0x62 = buffMaxLevel))` = 6) -- d'ou l'i2 << for the rest of the battle >>
sans borne. Le niveau abouti arrive TEL QUEL dans `decisionView.effects[].level` : on lit
`self.level`, sans recalcul offline (meme regime que ses trois jumeaux de fratrie).

## MAGNITUDES

  * `extraDmg` -- `abilities.HeadClaimer.variables.extraDmg` ([L1]=3 .. [L65]=218), **DANS**
    `variablesAffectedByRarityBonus` -> scale par le multiplicateur de rarete du porteur ;
  * `extraHit` -- `abilities.HeadClaimer.constants.extraHit` = **"1"**. Une CONSTANTE
    (`GetNumberConstant`, pas `GetVariableForLevel`) : ni indexee par niveau, ni scalee par le
    multiplier (meme forme que `UnstoppableFerocity`/`PowerTrip`, cle `0x2b` elles aussi).

`GetAbilityState(this)` sur un `AbilityOrEffect` TRIGGERED resout le niveau du PASSIF du porteur ->
`self.ability_level` (jamais `active_ability_level`), meme cascade que `Deathwing`/`FuelledByFury`.
Niveau d'ability ou niveau d'effet inconnu -> INERTE (degradation fidele, regle de la fratrie).
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
from ..base import BaseEffect
from ..magnitude import ability_var

#: cle gameconfig de l'ability -- l'`AbilityOrEffect` que le `.ctor` des DEUX effets passe a
#: `BaseEffect` (`mov edx, 0x407` = `TriggeredAbilityType.HeadClaimer = 1031`, lu dans les octets),
#: donc la config que `ConfigVar` / `GetNumberConstant` indexent.
ABILITY_ID = "HeadClaimer"
#: `AbilityVariableType 8` et `AbilityConstantType 0x2b = 43` (`frida/enums.tsv`, jamais recopies
#: du decompile) -- resolus par leur NOM, pas par leur ordinal.
VAR_EXTRA_DMG = "extraDmg"
CONST_EXTRA_HIT = "extraHit"


class HeadClaimerExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HeadClaimer_ExtraDamageEffect` (`EffectType 0x404 = 1028`,
    nom capte `HeadClaimer_ExtraDmg`). Cf. l'en-tete du module pour l'arbre natif et le recensement.

    PAS d'`active_condition_ported` : la classe ne DECLARE aucune `CreateActiveCondition` -- poser le
    flag inventerait un gate que le decompile ne porte pas."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """`ForAddition( get_OwnerIsCaster, Multiply(ConfigVar(extraDmg), EffectLevel) )`.

        `get_OwnerIsCaster` est satisfait STRUCTURELLEMENT sur ce canal : l'agregateur n'itere que
        les effets de l'ATTAQUANT. AUCUN autre noeud dans la conjonction -> aucun re-gate
        `is_ranged` / `is_normal_attack` / `is_prediction` ici (cf. l'en-tete : c'est l'ecart
        MESURE avec `TerrifyingCrescendo`, qui porte un `IsRangedAttack`)."""
        heads = self.level                              # EffectLevel(Effect@DSLSelectors+0x38)
        if not heads or int(heads) <= 0:
            return None
        if self.ability_level is None:                  # ConfigVar sans AbilityState -> inerte
            return None
        per = ability_var(ABILITY_ID, VAR_EXTRA_DMG, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        # `MultiplyAmount$$Calculate` est un produit d'ENTIERS : `ability_var` arrondit AVANT.
        return for_addition(True, int(per) * int(heads))


class HeadClaimerExtraHitEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HeadClaimer_ExtraHitsEffect` (`EffectType 0x405 = 1029`,
    nom capte `HeadClaimer_ExtraHit`). Cf. l'en-tete du module.

    `.ctor` = `BaseEffect(AbilityOrEffect(TriggeredAbilityType.HeadClaimer = 1031),
    hasAutomaticActivation: true)`. PAS d'`active_condition_ported` (aucune `CreateActiveCondition`
    declaree)."""

    def get_hits(self) -> "int | None":
        """`...HeadClaimer_ExtraHitsEffect$$GetHits` =
        `Multiply( Get(GetNumberConstant(config, 0x2b = extraHit)), EffectLevel(Effect) )`.

        `GetNumberConstant` -> `abilities.HeadClaimer.constants.extraHit` = 1 : une CONSTANTE, donc
        jamais indexee par niveau ni scalee par le multiplier de rarete. Niveau d'effet nul/inconnu
        -> `None` (degradation fidele : le produit natif vaudrait 0, on ne contribue pas)."""
        heads = self.level                              # EffectLevel(Effect@DSLSelectors+0x38)
        if not heads or int(heads) <= 0:
            return None
        n = ability_var(ABILITY_ID, CONST_EXTRA_HIT, is_constant=True)
        if not n:
            return None
        return int(n) * int(heads)

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        """`ForAddition( get_OwnerIsCaster, GetHits() )` -- UN SEUL noeud trigger, comme la face
        DEGAT : ni `IsNormalAttack`, ni `IsMeleeAttack`, ni `IsCharging` (contraste
        `UnstoppableFerocity_Owner` / `SagaOfTheWarriorBorn_Owner`, qui portent `IsCharging`).
        `get_OwnerIsCaster` est deja porte par le canal (`hits_bonus_from_effects` n'interroge que
        les effets de l'ATTAQUANT)."""
        hits = self.get_hits()
        return for_addition(True, int(hits)) if hits else None
