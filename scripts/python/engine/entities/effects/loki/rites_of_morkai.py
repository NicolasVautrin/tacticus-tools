"""`RitesOfMorkai_ExtraDamage` (EffectType 0x5f9 = 1529) -- le SECOND effet que l'active
`1211 RitesOfMorkai` de `spaceWolfPriest` << Baldr >> (Space Wolves) pose, sur le sous-ensemble
de sa zone qui porte DEJA une forme de Final Vengeance. #906.

i2 `Abilities/RitesOfMorkai_CurrentLevelDescription` : « Baldr and all surrounding friendly
non-mechanical units become <i>Inspired</i> for {[nrOfRounds]} round or until they are revived.
The first time each inspired unit would be defeated, it is instead revived with a maximum of
{[hp]} Health, unless Overkilled. **Inspired units with <i>Final Vengeance</i> deal +{[extraDmg]}
Damage with all attacks.** After using this ability, Baldr immediately performs a normal melee
attack against an adjacent enemy. »

Le volet REVIVE (effet 1502 `RitesOfMorkai`) vit ailleurs et etait deja porte :
`engine/runner/operations/triggers/loki/rites_of_morkai.py` (#79/#229). Ce module-ci porte le
volet DEGAT, et `engine/runner/abilities/spacewolves.py` la POSE des deux.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite, live = confirmation
================================================================================================

## `IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect$$.ctor`

    BaseEffect..ctor(this, AbilityOrEffect(<op_Implicit>), hasAutomaticActivation = 1)

Classe de base `IdunBattle.Entities.Effects.BaseEffect` (LU dans `frida/classes.tsv` : parent
`IdunBattle.Entities.Effects.BaseEffect`, taille 1152) -- a la difference de son frere 1502, qui
derive de `IdunBattle.Entities.Effects.ReviveEffect`.

## `IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`

MIRROR 1:1, terme a terme (slots `DSLFactory` : `+0x80 Formulas`, `+0x88 Triggers`,
`+0x90 Selectors`) :

    trigger = DSLTriggers.get_OwnerIsCaster
    amount  = DSLFormulas.ConfigVar( 0x8 = extraDmg, BaseEffect.GetAbilityState(this),
                                     config@this+0x60 )
    return Nullable( EffectBonus.ForAddition(trigger, amount) )

**UN SEUL noeud de trigger** -- pas d'`IsMeleeAttack`, pas d'`IsNormalAttack`, aucun
`op_BitwiseAnd` (lu a l'assembleur : un seul `call` de trigger avant le `ForAddition`). C'est le
contraste exact avec `WarHowl_ExtraDamage_Unstoppable` (1222), qui en porte TROIS, et c'est ce que
dit l'i2 : « deal +{[extraDmg]} Damage **with all attacks** » -- toutes, melee comme ranged,
normales comme abilities.

## `IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect$$CreateActiveCondition`

Le corps est **DEDUPLIQUE par IL2CPP avec `$$HasAnyKindOfFinalVengeance`** : le bloc
`methodPointers` de la classe porte la MEME adresse a DEUX slots (0x18 d'ecart), et le build
`gqfc5mff6c` nommait ce corps `CreateActiveCondition` la ou `rnca9r7q6c` le nomme
`HasAnyKindOfFinalVengeance`. Les deux noms designent donc la meme fonction :

    HasTrait ( Owner@DSLSelectors+0x30, 0x3f6 = 1014 UnitTrait.FinalJustice )
    op_BitwiseOr
    HasEffect( Owner@DSLSelectors+0x30, 0x5ae = 1454 EffectType.FinalVengeance_UnitEffect,
               onlyActive = 0, effectTargetType = 6 = Both )

⚠ `0x3f6 = 1014` est QUALIFIE : c'est un `UnitTrait` (`FinalJustice` -- le << Final Vengeance >> de
l'i2, le style i2 et le nom d'enum divergent), et 1014 nomme `EffectType.ArmoriumCherub` et
`ActiveAbilityType.ArmoriumCherub` dans d'AUTRES enums. Meme travail pour `0x5ae = 1454` :
`EffectType.FinalVengeance_UnitEffect`, la ou `UnitTrait` n'a pas de 1454.

Le MEME predicat est reconstruit INLINE dans
`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$ExecuteBehaviour` pour
FILTRER les cibles de la pose (noeud pour noeud, au slot `ActiveTarget@+0x68` puisqu'il y est sous
un `Filter`), et expose a part sous
`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$HasAnyKindOfFinalVengeance`.
Il est donc evalue DEUX fois : a la POSE (par l'ability) et a la LECTURE (par cet effet).

================================================================================================
ETAGE ET RESIDUS (nommes, jamais lisses)
================================================================================================
 * **ETAGE** : `EffectBonus.ForAddition` ecrit la liste ADDITIVE du `DamageModifiers` ATTAQUANT --
   un terme FLAT par coup, exactement au meme etage que `WarHowl_ExtraDamage_Unstoppable` (dont
   ce port reprend la mecanique de lecture) et que `PrioritisedEfficiency_ExtraDmg`.
 * `get_OwnerIsCaster` : ce canal (`build_attacker_modifiers_from_effects`) n'itere QUE les effets
   de l'ATTAQUANT -> le predicat est VRAI par construction, meme note et meme foyer que
   `MartialInspirationExtraDamageEffect` et `HeavyGravCannonEffect`.
 * **`active_condition_ported` reste FALSE, et c'est DELIBERE.** `is_active` ci-dessous MIRRORE la
   `CreateActiveCondition`, mais les DEUX membres du `op_BitwiseOr` ne sont pas mesurables avec la
   meme surete : `traits` l'est toujours, `has_effect_on` ne l'est que si le `State` porte une
   `EffectsState`. Passer le flag a True ferait contribuer une instance que le canal a captee
   INERTE des que l'un des deux membres n'est pas mesure. Le port exige donc les DEUX (`e.active`
   ET `is_active`), ce qui est la degradation RESTRICTIVE.
 * **NIVEAU / MULTIPLICATEUR** : `ConfigVar(0x8, GetAbilityState(this), config)` lit l'`AbilityState`
   BAKE A LA POSE, et l'ability passe `AActiveAbility$$get_AbilityStateReference` =
   `DSLSelectors$$AbilityState(Caster@+0x48, <l'active courante>)` -- donc celui du **CASTER**
   (Baldr), pas du porteur. `extraDmg` EST dans `variablesAffectedByRarityBonus` de la config
   `RitesOfMorkai` (avec `hp`), donc l'ecart de multiplicateur entre deux unites MORD. La POSE
   passe ce scaling explicitement (`AddEffect(..., scale_from_source=True)`, cf.
   `runner/abilities/spacewolves.py`) ; une instance SEEDEE, elle, retombe sur le porteur --
   residu #382, partage par les 135 entrees d'`EFFECT_CLASSES`, pas un choix de cette classe.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
from ...ability_variable_type import AbilityVariableType
from ...effect_type import EffectType
from ...traits.unit_trait import UnitTrait, has_trait
from ..base import BaseEffect
from ..magnitude import ability_var

#: cle gameconfig de l'ability 1211 -- la config que `ConfigVar` resout (`this+0x60`).
_ABILITY_ID = "RitesOfMorkai"
#: `ConfigVar(0x8)` -> `AbilityVariableType.extraDmg` (rarity-affected, cf. l'en-tete).
VAR_EXTRA_DMG = AbilityVariableType.extraDmg                          # 0x8 = 8
#: `HasTrait(Owner, 0x3f6)` -- le << Final Vengeance >> de l'i2 s'ecrit `FinalJustice` a l'enum.
FINAL_VENGEANCE_TRAIT = UnitTrait.FinalJustice                        # 0x3f6 = 1014
#: `HasEffect(Owner, 0x5ae, onlyActive: 0, effectTargetType: 6 = Both)`.
FINAL_VENGEANCE_EFFECT = EffectType.FinalVengeance_UnitEffect         # 0x5ae = 1454


class RitesOfMorkaiExtraDamageEffect(BaseEffect):
    """`RitesOfMorkai_ExtraDamage` (0x5f9 = 1529) -- +extraDmg FLAT sur TOUTES les attaques du
    porteur, tant qu'il a une forme de Final Vengeance. Cf. l'en-tete de module pour la RE."""

    # `IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect$$get_KeepOnRevive`
    # (`IEffect` slot 2) SURCHARGE le defaut `True` de `IdunBattle.Entities.Effects.BaseEffect` :
    # corps `xor al,al ; ret` (`32 c0 c3`), DERIVE par `probe_547r13_keep_on_revive.py`, entree
    # versionnee `data/symbols/<build>/metadata/keep_on_revive.tsv`. L'UNE des trois seules classes
    # du binaire a le renverser -- et le sens colle a la mecanique : le bonus de degat que Baldr
    # accorde a l'unite << Inspired >> ne survit PAS a la resurrection de cette unite (#547-r14).
    # ⚠ Lu UNIQUEMENT au revive (`keep_on_revive_gate`) : sur le chemin de MORT ce flag est inerte,
    # donc ceci ne change RIEN a la sequence de mort -- 1529 y part comme avant.
    keep_on_revive = False

    def _level(self) -> "int | None":
        """`Level$$ToZeroBasedIndex(abilityState)` : `RitesOfMorkai` est une ability ACTIVE, donc la
        variable s'indexe par le niveau d'ability ACTIVE (meme idiome que les 18 autres classes qui
        lisent une active, cf. `war_howl.py`). Repli sur `ability_level` : `EffectsState.seed` ne
        propage a ce jour que celui-la (residu #382), et sous `buildNormalizedBC` les deux valent 50."""
        if self.active_ability_level is not None:
            return self.active_ability_level
        return self.ability_level if self.ability_level is not None else self.level

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """MIRROR de `IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect$$
        CreateActiveCondition` (= `$$HasAnyKindOfFinalVengeance`, corps FONDU par IL2CPP) :

            HasTrait(Owner, 0x3f6 = FinalJustice)
            op_BitwiseOr
            HasEffect(Owner, 0x5ae = FinalVengeance_UnitEffect, onlyActive: 0, targetType: 6)

        `onlyActive = 0` est LU et il MORD : le natif accepte une instance 1454 INERTE -- le port
        passe donc `active_only` a `False` par le callable `has_effect_on`, dont le contrat est
        precisement `HasEffect(..., onlyActive: null, effectTargetType: 6)`.

        TRI-ETAT sur chaque membre, et la disjonction se lit dans le bon ordre : un membre VRAI
        suffit (aucune mesure du second n'est alors requise) ; les deux membres FAUX ferment ; un
        membre faux et l'autre NON MESURE **ne ferme pas** (degradation fidele, meme regime que
        `AmuletOfTheVoidwyrmCritDamageReductionEffect.is_active` et `StructuralAnalyser`)."""
        us = unit_state or {}
        traits = us.get("traits")
        trait_hit = None if traits is None else has_trait(traits, FINAL_VENGEANCE_TRAIT)
        if trait_hit:
            return True                                    # 1er membre VRAI -> le OR est satisfait
        fn = us.get("has_effect_on")
        oid = us.get("owner_id")
        eff_hit = None if (fn is None or oid is None) else bool(fn(oid, int(FINAL_VENGEANCE_EFFECT)))
        if eff_hit:
            return True                                    # 2e membre VRAI
        if trait_hit is False and eff_hit is False:
            return False                                   # les DEUX mesures, les DEUX fausses
        return True                                        # au moins un membre NON MESURE

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits=None,
                                              is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> "EffectBonus | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect$$
        CreateEffectDamageBonusForAttack` :

            EffectBonus.ForAddition( get_OwnerIsCaster,
                                     ConfigVar(0x8 = extraDmg, GetAbilityState(effect),
                                               config@+0x60) )

        **AUCUN autre gate.** Ni `IsMeleeAttack` ni `IsNormalAttack` : les deux existent dans le
        vocabulaire natif et cette classe ne les appelle PAS -- lu a l'assembleur (un seul `call`
        de trigger). Le porteur gagne donc le flat sur TOUTE attaque, ce que l'i2 dit mot pour mot
        (« with all attacks »). Recopier les trois gates de `WarHowl` par analogie de forme aurait
        eteint le bonus sur les attaques d'ability et sur les tirs -- silencieusement."""
        n = ability_var(_ABILITY_ID, VAR_EXTRA_DMG.name, self._level(),      # ConfigVar 0x8
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, int(n)) if n else None
