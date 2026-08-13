"""`Helspear_IgnoreArmorEffect` -- `EffectType` 0x62f = 1583, pose par
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Helspear_BuffActiveAbility` sur la CIBLE de
l'active `HeraldOfTheApocalypse` de `blackHaarken`. Relique `R_Crit_Helspear`. #1008.

===================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
===================================================================================================

## `IdunBattle.Entities.Effects.Loki.Helspear_IgnoreArmorEffect$$.ctor`

    BaseEffect( AbilityOrEffect(<litteral>), hasAutomaticActivation = 1 )

## `...Helspear_IgnoreArmorEffect$$CreateEffectDamageMalusForDefense`  (slot DEFENSEUR 0x1a)

    return Nullable<EffectBonus>{ condition = get_OwnerIsTarget & IsUnit(Caster@DSLSelectors+0x48),
                                  <tout le reste = ZERO> }

C'est un `EffectBonus` **CONDITION-SEULE, valeur nulle** -- exactement le patron deja lu sur
`PowerTrip_IgnoreArmorEffect` (`entities/effects/loki/hits.py`), dont la docstring dit : « le natif
CreateEffectDamageBonusForAttack = NO-OP (EffectBonus condition-seule, valeur 0) ». Ce n'est donc
PAS par ce slot que passe la penetration.

## `...Helspear_IgnoreArmorEffect$$IgnoreArmor`  -- corps FONDU (ICF)

    return ConfigVar( AbilityVariableType.armorIgnored = 0x40,
                      BaseEffect.GetAbilityState(this), <config>@this+0x60 )

⚠ **CE CORPS EST ATTRIBUE A `WayOfTheShortBladeEffect$$IgnoreArmor` DANS LES TABLES** (RVA
`1059b60`). L'appartenance a `Helspear_IgnoreArmorEffect` est etablie par TROIS faits :
  1. **contiguite d'emission** -- IL2CPP emet les methodes d'une classe en bloc, et `1059b60` tombe
     ENTRE `Helspear_IgnoreArmorEffect$$CreateEffectDamageMalusForDefense` (`1059960`) et
     `Helspear_IgnoreArmorEffect$$.ctor` (`1059bc0`) ;
  2. **6 xrefs DATA et 0 xref CODE** sur ce corps -> ce sont SIX slots de vtable, donc SIX classes
     partagent le meme corps : la table n'en nomme qu'un proprietaire (piege documente par le
     CLAUDE.md, « l'ABSENCE d'une methode dans les tables ne prouve RIEN ») ;
  3. **la variable existe** -- le gameconfig de `Helspear` porte `armorIgnored` =
     [685, 722, 759, 796, 833, 870, 907, 944, 981, 1018], et c'est la SEULE de ses deux variables
     que ce corps peut lire (`0x40`).

===================================================================================================
RESIDU `#1008-r2` -- LA MAGNITUDE N'ATTEINT PAS LE CALCUL, ET C'EST UN ETAGE, PAS UN OUBLI
===================================================================================================

Cote port, `BaseEffect.get_armor_penetration` (le canal de `IgnoreArmor`) n'est appele QUE par
`_attacker_effect_bonuses` -- la boucle des effets de l'**ATTAQUANT**
(`entities/effects/__init__.py`). Or CET effet-ci vit sur le **DEFENSEUR** : son porteur est la
cible de l'active, et sa propre condition le dit (`get_OwnerIsTarget`).

Cote natif, `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`
appelle sur chaque effet du defenseur TROIS slots virtuels -- `0x19` (un `Nullable<int>` accumule
dans `DamageModifiers+0x20`), `0x1a` et `0x1b` (deux `Nullable<EffectBonus>`). Le port les mirroire
deja (`create_piercing_bonus_for_attack` / `create_effect_damage_malus_for_defense`). **Aucun des
trois n'est `IgnoreArmor`** : le slot `0x19` rend un `Nullable`, la `IgnoreArmor` rend un
`IAmountFormula`. Le lecteur natif de `IgnoreArmor` pour un effet DEFENSEUR n'a donc pas ete
localise dans cette tranche.

Le port EXPOSE la magnitude (`ignore_armor()` ci-dessous) sans la brancher, et NE surcharge PAS
`get_armor_penetration` : la brancher sur le canal attaquant serait un no-op silencieux -- l'effet
n'est jamais dans la liste de l'attaquant --, c'est-a-dire exactement le genre de cablage qui se
lit comme « porte » sans rien changer. Le trou est ainsi VISIBLE et testable.

BLOCAGE `etage`. Point d'ancrage pour la suite : le slot virtuel qui invoque `IgnoreArmor`, a
chercher dans `DamageCalculations$$GetBaseDamageWithFixedPiercedArmor` et ses appelants.
"""
from __future__ import annotations

from typing import Mapping, Optional

from ..base import BaseEffect
from ..magnitude import ability_var

#: `EffectType` 0x62f = 1583 -- nom capte (`effect-type-names.ts` / `frida/enums.tsv`).
HELSPEAR_IGNORE_ARMOR = "Helspear_IgnoreArmor"
#: L'ability qui porte la variable lue par `IgnoreArmor` (le `GetAbilityState(this)` natif designe
#: l'`AbilityState` de la relique qui a POSE l'effet, donc `Helspear`).
ABILITY_ID = "Helspear"
ARMOR_IGNORED_KEY = "armorIgnored"      # `AbilityVariableType` 0x40 = 64


class HelspearIgnoreArmorEffect(BaseEffect):
    """`Helspear_IgnoreArmorEffect` -- marqueur pose sur la cible de `HeraldOfTheApocalypse`.

    Ce que le port porte VRAIMENT :
      * l'existence de l'effet (nom capte, instance reelle, duree par la regle par defaut) ;
      * sa CONDITION native, LUE (`get_OwnerIsTarget & IsUnit(Caster)`) -- exposee par
        `applies_to_incoming_attack` ;
      * sa MAGNITUDE native, LUE (`ConfigVar(armorIgnored)`) -- exposee par `ignore_armor`.
    Ce qu'il ne porte PAS : le CHEMIN par lequel cette magnitude entre dans le calcul de degat
    (residu `#1008-r2`, cf. l'en-tete). `get_armor_penetration` n'est deliberement PAS surcharge."""

    def applies_to_incoming_attack(self, attacker_id: Optional[int] = None) -> bool:
        """`get_OwnerIsTarget & IsUnit(Caster@DSLSelectors+0x48)` -- la condition de l'`EffectBonus`
        rendu par `CreateEffectDamageMalusForDefense`.

        Le port n'evalue QUE le second conjoint : le premier (`get_OwnerIsTarget`) est structurel
        ici -- l'appelant est, par construction, en train de resoudre une attaque CONTRE le porteur
        de cet effet. `IsUnit(Caster)` = l'attaquant est une UNITE (pas une tuile / un objet
        d'environnement) ; `attacker_id is None` -> on ne sait pas, donc **False** (degradation
        RESTRICTIVE : on n'active pas une vulnerabilite qu'on ne peut pas qualifier)."""
        return attacker_id is not None

    def ignore_armor(self, unit_state: Mapping | None = None) -> Optional[int]:
        """`ConfigVar(AbilityVariableType.armorIgnored = 0x40, GetAbilityState(this), config)`.

        `ability_level` est seede depuis l'`AbilityState` sous lequel l'effet a ete pose -- pour une
        relique c'est le palier TERTIAIRE, jamais le palier passif (faute mesuree par #1007). Repli
        sur le `level` du stack si l'`ability_level` n'a pas ete seede."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var(ABILITY_ID, ARMOR_IGNORED_KEY, lvl,
                           multiplier_pct=self.ability_variables_multiplier)
