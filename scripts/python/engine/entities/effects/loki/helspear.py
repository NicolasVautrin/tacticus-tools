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
`#1008-r2` -- LE LECTEUR DEFENSEUR EXISTE : IL EST *DANS* LE SLOT `0x1a`, PAS A COTE
===================================================================================================

La fiche du residu cherchait un QUATRIEME slot d'interface et concluait : << le slot `0x19` rend un
`Nullable`, `IgnoreArmor` rend un `IAmountFormula`, donc ce n'est aucun des trois >>. Le
raisonnement est EXACT et ne conclut pas -- `IgnoreArmor()` rend une formule NON EVALUEE, que le
slot `0x1a` evalue.

CE QUI EST LU (`IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense`, le corps du slot
`0x1a`, relu VERBATIM sur `t6dpr4k06g`) :

    InitializeBonusCacheIfNeeded(this)
    bonus = <Nullable<EffectBonus>> cache a this+0x1d8        # = CreateEffectDamageMalusForDefense()
    si !bonus.HasValue                        -> Nullable<DamageBonus> VIDE
    si !bonus.Value.trigger.<slot 0>(entities) -> Nullable<DamageBonus> VIDE      # <<< LA GATE
    sinon:
        DamageBonus+0x20 = eval(bonus+0x08)
        DamageBonus+0x28 = eval(bonus+0x10)
        DamageBonus+0x30 = eval(bonus+0x18)
        DamageBonus+0x38 = eval( this.<vtable +0x718>() )     # <<< APPEL VIRTUEL = `IgnoreArmor()`
        DamageBonus+0x40 = eval(bonus+0x28)

puis `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`
accumule `DamageBonus+0x38` dans **`DamageModifiers+0x28`** -- le MEME axe armure que la face
attaquant, celui que le port nomme `DamageModifiers.armor_penetration` et que
`IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor` consomme par
`armor_eff = max(armor - ignoreArmor, 0)`, DEJA porte (`services/damage_prediction.py`).

⚠ **L'`EffectBonus` << condition-seule >> N'EST PAS UN NO-OP -- C'EST LA GATE.**
`Helspear_IgnoreArmorEffect$$CreateEffectDamageMalusForDefense` rend un `EffectBonus` dont TOUTES
les formules valent 0 et dont le trigger est `get_OwnerIsTarget & IsUnit(Caster)`. La fiche y voyait
la preuve que la penetration ne passe pas par ce slot ; c'est l'inverse. Le natif SEPARE
volontairement la CONDITION (portee par l'`EffectBonus`) et la MAGNITUDE (portee par
`IgnoreArmor()`), et `DamageMalusForDefense` les RECOMBINE. Un `EffectBonus` sans formule y est
exactement ce qu'il faut.

C'est pourquoi le port lit `get_armor_penetration` **a l'interieur** du bloc ou le malus est rendu
(`entities/effects/__init__.py::build_defender_modifiers_from_effects`) : la gate n'est pas
dupliquee, elle est celle du malus, comme dans le natif.

⚠ **DEUX effets vivent sur ce canal**, pas un : `Helspear_IgnoreArmor` (1583) et
`StrikeFromTheShadows` (1549) -- les deux seules classes qui surchargent
`CreateEffectDamageMalusForDefense` parmi les cinq porteuses d'`armorIgnored` au gameconfig
(les trois autres -- `KanOpener`, `PowerTrip`, `WayOfTheShortBlade` -- surchargent
`CreateEffectDamageBonusForAttack`, donc face ATTAQUANT). `1549` n'a AUCUNE classe portee : residu
distinct, ce module ne le couvre pas.
"""
from __future__ import annotations

from typing import Mapping, Optional

from ....services.effect_bonus import for_addition
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
      * le CHEMIN par lequel cette magnitude entre dans le calcul (#1008-r2, cf. l'en-tete) :
        `create_effect_damage_malus_for_defense` porte la GATE et `get_armor_penetration` la
        MAGNITUDE, comme le natif les separe -- la boucle defenseur les recombine."""

    def create_effect_damage_malus_for_defense(self, is_melee=None, damage_profile=None,
                                               attacker_ctx=None):
        """`Helspear_IgnoreArmorEffect$$CreateEffectDamageMalusForDefense` -- mirror 1:1.

        Le natif rend un `EffectBonus` dont TOUTES les formules valent 0 et dont le trigger est
        `get_OwnerIsTarget & IsUnit(Caster@<DSLSelectors+0x48>)`. Il ne modifie donc AUCUN
        multiplicateur de degat : son unique role est de faire passer -- ou pas -- le bloc de
        `BaseEffect$$DamageMalusForDefense` dans lequel `IgnoreArmor()` est evalue.

        ⚠ RENDRE `None` ICI DESARMERAIT LA PENETRATION, sans rien changer d'autre : c'est ce
        `EffectBonus` a magnitude nulle qui PORTE la gate. Le supprimer comme << inutile, il vaut
        zero >> serait la faute exacte que la fiche d'origine a commise en le lisant."""
        attacker_id = (attacker_ctx or {}).get("id") if attacker_ctx else None
        if not self.applies_to_incoming_attack(attacker_id):
            return None
        return for_addition(False, 0)          # `EffectBonus` a formules NULLES -- la gate seule

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        """`IgnoreArmor()` -- le slot virtuel `+0x718`, evalue par `BaseEffect$$DamageMalusForDefense`
        et range dans `DamageBonus+0x38`, que le natif accumule dans `DamageModifiers+0x28`.

        ⚠ AUCUN gate `is_normal_attack` ICI, et c'est LU, pas omis : le corps natif evalue la
        formule sans consulter la nature du coup. Le parametre existe pour les penetrations de la
        face ATTAQUANT qui, elles, sont gatees (`PowerTrip` : << NORMAL attacks ignore X Armour >>).
        La gate de CET effet est ailleurs -- dans le trigger du malus ci-dessus."""
        return self.ignore_armor()

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
