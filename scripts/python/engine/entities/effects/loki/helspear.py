"""`Helspear_IgnoreArmorEffect` -- `EffectType` 0x62f = 1583, pose par
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Helspear_BuffActiveAbility` sur la CIBLE de
l'active `HeraldOfTheApocalypse` de `blackHaarken`. Relique `R_Crit_Helspear`. #1008.

===================================================================================================
RE (decompile ghidra, RE-LUE INTEGRALEMENT sur le build `t6dpr4k06g` -- #1008-r2, 2026-08-15)
===================================================================================================

## `IdunBattle.Entities.Effects.Loki.Helspear_IgnoreArmorEffect$$.ctor`

    BaseEffect( AbilityOrEffect(<litteral>), hasAutomaticActivation = 1 )

## `...Helspear_IgnoreArmorEffect$$CreateEffectDamageMalusForDefense`  (slot DEFENSEUR 0x1a)

    return Nullable<EffectBonus>{ condition = get_OwnerIsTarget & IsUnit(Caster@DSLSelectors+0x48),
                                  <tout le reste = ZERO> }

C'est un `EffectBonus` **CONDITION-SEULE, valeur nulle** -- exactement le patron deja lu sur
`PowerTrip_IgnoreArmorEffect` (`entities/effects/loki/hits.py`).

&#9888; **CE N'EST PAS UN NO-OP, ET LE CROIRE ETAIT LE CONTRESENS DE `#1008-r2`.** Un `EffectBonus`
sans aucune formule est le **PORTEUR DE LA GATE** : `BaseEffect$$DamageMalusForDefense` evalue ce
trigger AVANT de lire la magnitude, et ne lit rien s'il est faux. Le design SEPARE la condition
(l'`EffectBonus`) de la magnitude (`IgnoreArmor()`), et le slot `0x1a` les RECOMBINE. La penetration
passe donc bien par ce slot -- pas par son `EffectBonus`, mais par son CORPS.

## `...Helspear_IgnoreArmorEffect$$IgnoreArmor`  -- corps FONDU (ICF)

    return ConfigVar( AbilityVariableType.armorIgnored = 0x40,
                      BaseEffect.GetAbilityState(this), <config>@this+0x60 )

⚠ **CE CORPS EST ATTRIBUE A `WayOfTheShortBladeEffect$$IgnoreArmor` DANS LES TABLES** -- IL2CPP
DEDUPLIQUE les corps identiques et n'en nomme qu'UN proprietaire (« l'ABSENCE d'une methode dans
les tables ne prouve RIEN », CLAUDE.md). Le SLOT, lui, est identifie sans ambiguite : c'est
`vtable +0x718`, soit `(0x718 - 0x138) / 0x10` = **slot 94** de la classe, invoque explicitement
par `IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense` (face DEFENSEUR) **et** par
`IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack` (face ATTAQUANT), avec
`*(this + 0x720)` comme `MethodInfo*`. Son nom est etabli par QUATRE sources independantes :
  1. **signature unique compatible** -- `frida/methods.tsv` ne porte qu'une methode d'effet rendant
     `IdunBattle.DSL.IAmountFormula` a **0 parametre** : `...WayOfTheShortBladeEffect.IgnoreArmor` ;
  2. **corps lu** -- `ConfigVar(0x40, GetAbilityState(this), cfg)` avec
     `IdunBattle.Configuration.AbilityVariableType.64 = armorIgnored` (`frida/enums.tsv`) ;
  3. **le port le nommait deja** -- `engine/runner/operations/triggers/revive_effect.py` ecrit
     `+0x718 IgnoreArmor`, et que le corps de BASE est `33 c0 c3` (`xor eax,eax ; ret` = `null`),
     ce qui EXPLIQUE la deduplication ;
  4. **comptage croise 5/5** -- le corps porte **5 xrefs DATA** (5 slots de vtable) et le gameconfig
     porte **exactement 5** abilities a variable `armorIgnored` : `KanOpener`, `PowerTrip`,
     `Helspear`, `WayOfTheShortBlade`, `StrikeFromTheShadows`. Aucune en trop, aucune manquante.
Et la variable existe bien ici : le gameconfig de `Helspear` porte `armorIgnored` =
[685, 722, 759, 796, 833, 870, 907, 944, 981, 1018] -- la SEULE de ses deux variables que ce corps
peut lire (`0x40` ; l'autre est `nrOfUnits`).

===================================================================================================
`#1008-r2` RESOLU -- LE LECTEUR EST DANS LE SLOT `0x1a`, PAS A COTE DE LUI
===================================================================================================

L'enonce du residu cherchait un QUATRIEME slot d'interface, frere des `0x19`/`0x1a`/`0x1b`, et
concluait « aucun des trois n'est `IgnoreArmor` » -- exact, mais **ne conclut pas**. `IgnoreArmor`
n'est pas un slot d'`IEffect` (ses 47 slots sont nommes dans
`data/symbols/<build>/metadata/interface_slots.tsv`, aucun ne porte ce nom) : c'est un slot de
**vtable de CLASSE**, appele DEPUIS le corps du `0x1a`. La chaine, LUE de bout en bout :

    <Effect>$$Create<Face>                       -> Nullable<EffectBonus> : la CONDITION SEULE
    <Effect>$$IgnoreArmor       (vtable +0x718)  -> IAmountFormula        : la MAGNITUDE
    BaseEffect$$DamageBonusForAttack  (slot 0x16) ] combinent SOUS LA GATE, et rangent
    BaseEffect$$DamageMalusForDefense (slot 0x1a) ] la formule evaluee dans DamageBonus+0x38
    DamageCalculations$$Calculate{Attacker,Defender}ModifiersForPrediction
        -> accumulent DamageBonus+0x38 dans DamageModifiers+0x28   (les DEUX faces)
    DamagePrediction$$CalculateBaseDamageWithAllModifiers
        -> ignoreArmor = Fix64.op_Addition(attackModifiers.@0x28, defenseModifiers.@0x28)
    DamagePrediction$$GetBaseDamageWithFixedPiercedArmor
        -> armor_eff = Math.Max(defender.GetStat(0x10 = Armor) - (int)ignoreArmor, 0)

Deux precisions qui manquaient a l'enonce : les slots `0x1a`/`0x1b` rendent
`Nullable<Core.Services.DamageBonus>` (la structure EVALUEE), pas `Nullable<EffectBonus>` ; et le
slot `0x19` est `PiercingMalusForDefense`, qui alimente `DamageModifiers+0x20` -- un axe DISTINCT
de l'armure. Le point d'ancrage suggere (`$$GetBaseDamageWithFixedPiercedArmor`) etait JUSTE : son
dixieme parametre s'appelle litteralement `ignoreArmor`.

⚠ **Le nombre de PASSES n'est pas toujours 1** : `GetDamageWithPiercing` est applique 2 fois si la
cible a `UnitTrait.MkXGravis` (1013) hors crit, 3 fois sous `TriggeredAbilityType.AblativePlating`
(1206) hors crit et sous condition de `pierceRatio`. Une penetration juste avec un mauvais nombre
de passes donne un faux vert sur les cibles ordinaires.

Le port branche desormais le canal (`build_defender_modifiers_from_effects` appelle
`get_armor_penetration`, cf. le commentaire de ce site pour l'ECART D'UN ETAGE assume sur la gate).
Detail complet : `docs/rl/case-1008r2-ignorearmor-canal-defenseur.md`.
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
      * le CHEMIN par lequel cette magnitude entre dans le calcul de degat -- `#1008-r2` RESOLU :
        `get_armor_penetration` est surcharge ci-dessous, et `build_defender_modifiers_from_effects`
        l'appelle, ce qui alimente `DamageModifiers+0x28` puis l'argument `ignoreArmor` de
        `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor`."""

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

    def get_armor_penetration(self, is_normal_attack: bool = True, attacker_ctx=None) -> Optional[int]:
        """`Helspear_IgnoreArmorEffect$$IgnoreArmor` (`vtable +0x718`), LU par
        `IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense` (slot `0x1a`) APRES la gate
        que porte `...$$CreateEffectDamageMalusForDefense` -- `#1008-r2`.

        **Aucune gate `is_normal_attack`** : le trigger natif de cet effet est
        `get_OwnerIsTarget & IsUnit(Caster)`, il ne regarde PAS la nature de l'attaque (contraste
        avec `PowerTrip_IgnoreArmorEffect`, dont le trigger porte `IsNormalAttack`). Le parametre
        est accepte pour la signature partagee et deliberement ignore.

        La gate PORTEE est `IsUnit(Caster)`, via `applies_to_incoming_attack` : l'attaquant doit
        etre une UNITE. `attacker_ctx` absent ou sans `id` -> on ne sait pas qualifier l'attaquant
        -> **None** (degradation RESTRICTIVE : on n'active pas une vulnerabilite qu'on ne peut pas
        justifier). `get_OwnerIsTarget`, lui, est structurel ici -- ce canal n'est appele que par
        `build_defender_modifiers_from_effects`, donc le porteur EST la cible par construction."""
        if not self.applies_to_incoming_attack((attacker_ctx or {}).get("id")):
            return None
        return self.ignore_armor()
