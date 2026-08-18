"""`StrikeFromTheShadowsEffect` -- `EffectType` 0x60d = 1549, pose par
`IdunBattleLogic.Entities.Abilities.Active.Loki.StrikeFromTheShadowsAbility$$ExecuteBehaviour`
sur la CIBLE de l'active 1225 d'`astarCyrus` (<< Cyrus >>, Adeptus Astartes). #1008-r4.

===================================================================================================
RE (decompile ghidra, build `t6dpr4k06g`, lu VERBATIM)
===================================================================================================

## Le bloc `methodPointers` porte CINQ entrees, pas DEUX

C'est le fait qui rouvre ce port, et il est l'exemple type du piege documente par le CLAUDE.md
(<< l'ABSENCE d'une methode dans les tables ne prouve RIEN >>) : `frida/methods.tsv` est indexe
par ADRESSE et IL2CPP DEDUPLIQUE (ICF) les corps identiques, donc il ne nomme que DEUX methodes
pour cette classe. Le bloc du PE, borne par `list_xrefs` sur les deux corps nommes puis lu par
`read_bytes`, en porte CINQ -- et l'entree suivante bascule sur `StructuralAnalyserAdjacentEffect$$.ctor`,
ce qui BORNE le bloc :

    +0x00  `StrikeFromTheShadowsEffect$$.ctor`
    +0x08  corps ICF `WisdomOfTheAncients_DamageReductionEffect$$CreateActiveCondition`
    +0x10  corps ICF `WhisperingWebEffect$$CreateTargetSelector`
    +0x18  `StrikeFromTheShadowsEffect$$CreateEffectDamageMalusForDefense`
    +0x20  corps ICF `WayOfTheShortBladeEffect$$IgnoreArmor`      <<< LA MAGNITUDE
    +0x28  `StructuralAnalyserAdjacentEffect$$.ctor`              <<< bloc SUIVANT

## `...StrikeFromTheShadowsEffect$$.ctor`

    BaseEffect( AbilityOrEffect(<litteral>), hasAutomaticActivation = 1 )

## `...StrikeFromTheShadowsEffect$$CreateEffectDamageMalusForDefense`  (slot DEFENSEUR 0x1a)

    return Nullable<EffectBonus>{
        condition = op_BitwiseAnd( DSLTriggers$$IsRangedAttack, DSLTriggers$$get_OwnerIsTarget ),
        <les six slots de magnitude + le Nullable<AbilityOrEffect> = ZERO> }

`EffectBonus` CONDITION-SEULE, valeur nulle -- exactement le patron de `Helspear_IgnoreArmorEffect`
(`entities/effects/loki/helspear.py`), qui porte la lecture complete du mecanisme : le natif SEPARE
la CONDITION (portee par l'`EffectBonus`) et la MAGNITUDE (portee par `IgnoreArmor()`), et
`IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense` -- le corps du slot -- les
RECOMBINE en evaluant `this.<vtable +0x718>()` DANS le bloc gate par le trigger, puis en rangeant
le resultat dans `DamageBonus+0x38`, que
`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` accumule
dans `DamageModifiers+0x28`.

⚠ **LA GATE N'EST PAS CELLE DE `Helspear`, ET C'EST MESURE, PAS SUPPOSE.** Les deux effets vivent
sur le meme canal mais leurs conditions DIFFERENT terme a terme :

    Helspear_IgnoreArmor (1583)  :  get_OwnerIsTarget & IsUnit(Caster@<DSLSelectors+0x48>)
    StrikeFromTheShadows (1549)  :  IsRangedAttack()  & get_OwnerIsTarget

`1549` n'a **AUCUN** `IsUnit(Caster)` -- donc aucune degradation sur l'identite de l'attaquant -- et
`1583` n'a **AUCUN** `IsRangedAttack`. Recopier l'un sur l'autre serait le piege du voisin de forme,
ici a un caractere pres dans le nom du canal.

## `...StrikeFromTheShadowsEffect$$IgnoreArmor`  -- corps FONDU (ICF)

    return ConfigVar( AbilityVariableType.armorIgnored = 0x40,
                      BaseEffect$$GetAbilityState(this), <config>@this+0x60 )

Corps LU a `18105a610`, attribue a `WayOfTheShortBladeEffect$$IgnoreArmor` dans les tables ; son
appartenance a CETTE classe est etablie par le bloc `methodPointers` ci-dessus, pas par contiguite.
Le gameconfig porte bien la variable :
`StrikeFromTheShadows.armorIgnored = [6, 7, 8, 10, 11, 12]`, et -- contrairement a `Helspear`, dont
la config n'a AUCUNE liste -- `armorIgnored` y est **dans `variablesAffectedByRarityBonus`**
(avec `minDmg` / `maxDmg`), donc le multiplicateur de rarete s'y applique. `ability_var` le fait
seul, config-driven : ne pas cabler ce scaling a la main.

## Les DEUX autres surcharges du bloc -- LUES, et sans effet portable

  * `CreateActiveCondition` = `<DSLTriggers+0x70>` = **YesTrigger** (condition d'ACTIVITE
    inconditionnelle : rien a gater, c'est deja le regime par defaut du port) ;
  * `CreateTargetSelector` = `<DSLSelectors+0x30>` = **Owner** (le porteur lui-meme).

Elles sont citees pour que la prochaine relecture du bloc ne les prenne pas pour un oubli.

===================================================================================================
CE QUE CE MODULE CORRIGE -- un enonce ECRIT qui etait FAUX
===================================================================================================

`engine/runner/abilities/astartes.py` affirmait, en toutes lettres, que << l'effet 0x60d est
NUMERIQUEMENT INERTE >> et que la classe << n'a que DEUX methodes (`frida/methods.tsv`) >>, puis en
concluait << le port n'inscrit AUCUNE classe d'effet >>. La lecture de l'`EffectBonus` etait
JUSTE (ses six slots de magnitude valent bien zero) ; c'est la CONCLUSION qui ne suivait pas -- un
`EffectBonus` a magnitude nulle est precisement ce que ce canal attend, la magnitude vivant dans
le slot virtuel voisin. La phrase est corrigee au site.
"""
from __future__ import annotations

from typing import Mapping, Optional

from ....services.effect_bonus import for_addition
from ..base import BaseEffect
from ..magnitude import ability_var

#: `EffectType` 0x60d = 1549 -- nom capte (`frida/enums.tsv`), identique au nom de l'ability.
STRIKE_FROM_THE_SHADOWS = "StrikeFromTheShadows"
#: L'ability dont l'`AbilityState` indexe le `ConfigVar` (`GetAbilityState(this)` = l'etat d'ability
#: du POSEUR, ici l'active 1225 du caster).
ABILITY_ID = "StrikeFromTheShadows"
ARMOR_IGNORED_KEY = "armorIgnored"      # `AbilityVariableType` 0x40 = 64


class StrikeFromTheShadowsEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.StrikeFromTheShadowsEffect` -- le marqueur pose sur la
    cible de Cyrus, qui la rend PLUS VULNERABLE aux tirs.

    Ce que le port porte, terme a terme :
      * la CONDITION native, LUE (`IsRangedAttack() & get_OwnerIsTarget`) -- `create_effect_damage_
        malus_for_defense`, qui rend un `EffectBonus` a magnitude NULLE : c'est la gate, pas un
        no-op ;
      * la MAGNITUDE native, LUE (`ConfigVar(armorIgnored)`) -- `get_armor_penetration` ;
      * le CHEMIN (#1008-r2) : la boucle defenseur
        (`entities/effects/__init__.py::build_defender_modifiers_from_effects`) lit la penetration
        DANS le bloc ou le malus est rendu, donc sous la meme gate que le natif."""

    def create_effect_damage_malus_for_defense(self, is_melee=None, damage_profile=None,
                                               attacker_ctx=None):
        """`StrikeFromTheShadowsEffect$$CreateEffectDamageMalusForDefense` -- mirror 1:1.

        Le natif rend un `EffectBonus` dont les six slots de magnitude valent 0 et dont le trigger
        est `IsRangedAttack() & get_OwnerIsTarget`. Il ne modifie donc AUCUN multiplicateur : son
        unique role est de faire passer -- ou pas -- le bloc de `BaseEffect$$DamageMalusForDefense`
        dans lequel `IgnoreArmor()` est evalue.

        ⚠ RENDRE `None` ICI DESARMERAIT LA PENETRATION, sans rien changer d'autre. Et rendre
        `for_addition(False, 0)` INCONDITIONNELLEMENT l'armerait sur les coups de MELEE, que le
        natif exclut."""
        # `IsRangedAttack()` -- `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` ne rend VRAI
        # que si la nature du coup est PROUVEE distance (#106). La nature INCONNUE (`None`) ferme
        # donc le gate : degradation RESTRICTIVE, alignee sur `is_ranged_attack` de `..base`.
        if is_melee is not False:
            return None
        # `get_OwnerIsTarget` : structurel ici -- l'appelant est, par construction, en train de
        # resoudre une attaque CONTRE le porteur de cet effet (c'est la liste qu'il balaie).
        return for_addition(False, 0)          # `EffectBonus` a formules NULLES -- la gate seule

    def get_armor_penetration(self, is_normal_attack: bool = True,
                              is_ranged: bool | None = None) -> int | None:
        """`IgnoreArmor()` -- le slot virtuel `+0x718`, evalue par `BaseEffect$$DamageMalusForDefense`
        et range dans `DamageBonus+0x38`, que le natif accumule dans `DamageModifiers+0x28`.

        ⚠ AUCUN gate `is_normal_attack` NI `is_ranged` ICI, et c'est LU : le corps natif evalue la
        formule sans consulter la nature du coup. Les deux parametres existent pour les penetrations
        dont le trigger porte un tel noeud -- `PowerTrip` (`IsNormalAttack`) et `KanOpener`
        (`IsMeleeAttack`, #1008-r5). La gate de CET effet est ailleurs -- dans le trigger du malus
        ci-dessus, comme pour `Helspear`."""
        return self.ignore_armor()

    def ignore_armor(self, unit_state: Mapping | None = None) -> Optional[int]:
        """`ConfigVar(AbilityVariableType.armorIgnored = 0x40, GetAbilityState(this), config)`.

        `ability_level` est seede depuis l'`AbilityState` sous lequel l'effet a ete pose (le
        `scale_from_source` du call-site d'`astartes.py`, mirror du 2e argument natif
        `get_AbilityStateReference(this)`). Repli sur le `level` du stack s'il n'a pas ete seede.

        ⚠ **LE NIVEAU MORD, ET LARGEMENT** -- la table a 65 paliers pleins (`[6, 7, 8, 10, 11, 12,
        ... , 333, 336, ... , 437]`), pas la poignee que suggere sa tete : un effet pose SANS son
        `abilityState` retomberait sur `ability_level = None` -> index 0 -> **6** de penetration, la
        ou un runner normalise (`level 50`, mult 180) en donne **599**. C'est exactement l'ecart que
        `scale_from_source` ferme, et il est SILENCIEUX si on l'oublie."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var(ABILITY_ID, ARMOR_IGNORED_KEY, lvl,
                           multiplier_pct=self.ability_variables_multiplier)
