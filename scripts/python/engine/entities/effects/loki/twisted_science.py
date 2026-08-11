"""`TwistedScience_ExtraHp` (1355 = 0x54b) -- le stat-mod HEALTH du passif `TwistedScience` (1278)
de `genesBiophagus` "Hollan". #931

ARTEFACT NATIF : **aucune classe d'effet dediee** (ni `frida/classes.tsv` ni `ghidra/functions.tsv`
ne portent de `TwistedScience_ExtraHpEffect` -- contraste avec son voisin `TwistedScience_ExtraDmg`
1356, qui en a une). C'est une instance GENERIQUE
`IdunBattle.Entities.Effects.DynamicStatModifierEffect`, construite par la base d'effets
(`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`, un lambda par `EffectType`) puis
POSEE par la feuille `IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffect` de
`IdunBattleLogic.Entities.Abilities.Active.Loki.TwistedScience_HealAbility$$ExecuteBehaviour` :

    AddDynamicStatModifierEffect(targets = Target@DSLSelectors+0x60, source = Owner@+0x30,
                                 effectType = 0x54b, statType = **5 = Health**,
                                 abilityStateSelector = AActiveAbility.AbilityStateReference,
                                 turns = null  -> PERMANENT, isHidden = false)

Les DEUX moities de la magnitude sont donc lues a DEUX endroits differents, et c'est structurel :
le **StatType** est le litteral de la FEUILLE de pose (5 = Health), la **valeur** est celle du
ctor generique. `IdunBattle.Entities.Effects.DynamicStatModifierEffect$$.ctor(abilityType,
variableType, isNegative, canBeImmuneTo)` range `+0x490/+0x498 = abilityType`,
`+0x4a0 = variableType`, `+0x4a4 = isNegative`, et
`...DynamicStatModifierEffect$$GetDynamicStatModificationAmount` rend :

    v = DSLFormulas.ConfigVar(<abilityType>, DSLSelectors.EffectSource(Get(effect)), <variableType>)
    return isNegative ? -v : v

-- soit `ConfigVar(TwistedScience, <la SOURCE de l'effet, c.-a-d. Hollan>, hp)`, indexe sur le
niveau du PASSIF du poseur et non du buffe. C'est exactement ce que
`runner/abilities/behaviours/effects.py::AddDynamicStatModifierEffect` propage
(`_source_scaling(source)` -> `ability_level = passive_ability_level`), d'ou le `self.ability_level`
ci-dessous.

## CE QUI EST LU, ET CE QUI EST MESURE (aucune des deux n'est devinee)

* LU : `variableType = 0x1d = hp` et `isNegative = 0` sur le lambda de la base d'effets qui
  construit un `DynamicStatModifierEffect` a ces deux valeurs ; `statType = 5 = Health` au
  call-site de la feuille.
* MESURE (`probe_931_twisted_science.py --phase blesse`, MC1_67/777) : une cible a **1000** PV
  (max 6023) passe a **7606** cote natif apres le cast. Or `7606 = 1000 + 2992 (ChangeStat) + 3614
  (Heal)`, et `3614` ne peut passer ENTIEREMENT que si le plafond a ete releve d'au moins 1583 --
  le natif a donc bien releve `CurrentMaximumValue()` de `+2992`, la valeur meme de
  `TwistedScience.hp[50] x 180 %`. Le signe POSITIF et l'appariement a la config `TwistedScience`
  sont ainsi confirmes par un observable INDEPENDANT du gameconfig.

## POURQUOI CETTE CLASSE EXISTE ALORS QUE LE NATIF N'EN A PAS

Cote port, `EFFECT_CLASSES` est la SEULE voie par laquelle un stat-mod est applique : un effet
absent du registre est materialise en `BaseEffect` nu, donc POSE mais INERTE
(`AddEffectOperation._apply_stat_mods` ne trouve ni stat ni magnitude). Sans cette classe, le
plafond de PV ne bouge pas et le `Heal` final se clampe sur l'ANCIEN maximum : mesure du
2026-08-11, **6023 au lieu de 7606** (ecart 1583, soit 21 % du resultat natif). La classe est donc
le mirror du COUPLE (base d'effets + ctor generique), pas l'invention d'une classe native qui
n'existe pas -- meme arbitrage que `unbreakable_duty.py`, dont les deux self-buffs sont eux aussi
des instances generiques (`StaticStatModifierEffect`) sans classe native.

Le second effet du meme cast, `1356 TwistedScience_ExtraDmg`, a lui une classe native et vit dans
`extra_damage.py` (rangement par FAMILLE de ce paquet : tous les
`CreateEffectDamageBonusForAttack` directs y sont).
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
from ....entities.ability_variable_type import AbilityVariableType
from ....entities.stats import StatType

#: Cle gameconfig du PASSIF -- `TriggeredAbilityType.TwistedScience` (0x4fe = 1278). L'active
#: substituee `1167 Heal_TwistedScience` n'a AUCUNE entree `units.abilities` : `hp` et `extraDmg`
#: vivent tous deux ici.
_ABILITY_ID = "TwistedScience"


class TwistedScienceExtraHpEffect(BaseEffect):
    """`EffectType.TwistedScience_ExtraHp` (0x54b = 1355) -- +`hp[level]` sur `StatType.Health`,
    PERMANENT (`turns = null`), pose sur toute unite soignee par Hollan qui ne le portait pas deja.

    i2 (`UnitEffects/TwistedScience_ExtraHp_Description`) : "Maximum Health increased by +{[hp]}".

    NIVEAU : `self.ability_level` d'abord -- c'est la voie par laquelle
    `AddDynamicStatModifierEffect` a propage le `passive_ability_level` de la SOURCE, seule fidele
    au `ConfigVar(..., EffectSource(effect), ...)` natif. Replis explicites ensuite
    (`active_ability_level`, puis le niveau de stack) pour une instance arrivee par `load_state`,
    ou le canal ne distingue pas les deux."""

    def get_stat_modification_stat(self) -> "int | None":
        return int(StatType.HEALTH)                 # litteral 5 de la feuille de pose

    def get_stat_modification_amount(self) -> "int | None":
        lvl = (self.ability_level if self.ability_level is not None
               else (self.active_ability_level if self.active_ability_level is not None
                     else self.level))
        return ability_var(_ABILITY_ID, AbilityVariableType.hp.name, lvl,
                           multiplier_pct=self.ability_variables_multiplier)

    def applied_stat_mods(self, stats_ctx) -> "list":
        """DATA du `ChangeStat` (part 5) pose A L'APPLICATION : HEALTH += `hp[level]`.

        ⚠ CETTE DECLARATION N'EST PAS REDONDANTE AVEC LE COUPLE CI-DESSUS -- elle choisit le CHEMIN,
        et sur HEALTH les deux chemins ne mutent pas le meme objet :

          * `AddEffectOperation._apply_stat_mods` (le chemin de la POSE) ne lit QUE
            `applied_stat_mods`, et il execute par `operations/stat_ops.py::apply_change_stat`, qui
            ROUTE `StatType.Health` vers `HealthComponent.modify_max` -- donc vers
            `get_CurrentMaximumValue()`, le plafond que lit le `Heal` qui SUIT dans le meme arbre ;
          * `refresh_stat_modifier_effects` (le chemin du REFRESH, qui lit la forme de BASE via
            `effect_stat_modifications`) ecrit dans `UnitStats`, que RIEN ne relit pour les PV.

        Sans cette methode, l'effet est POSE mais le plafond ne bouge pas, et le `Heal` final se
        clampe sur l'ANCIEN maximum. MESURE (`probe_931 --phase blesse`) : **6023 au lieu de 7606**
        sur une cible a 1000 PV. C'est le MEME arbitrage, pour la MEME raison, que
        `AnvilShieldFrozenAttackerAdvantageEffect` (`hits.py`) : effet pose A L'EXECUTION, sans
        `ActiveCondition`, donc c'est `_apply_stat_mods` qui doit l'appliquer.

        Pas de double-compte : `effect_stat_modifications` fait PRIMER la forme OVERRIDE sur la
        forme de BASE (mirror du natif, ou un `ApplyModification` surcharge remplace celui de la
        base), et les deux chemins partagent la MEME cle de source (`effect_stat_mod_key` rend
        `eff.stat_mod_source`, pose par `_apply_stat_mods`) -- une `ValueModification.Modify` sur une
        source deja connue REMPLACE, elle n'additionne pas."""
        amt = self.get_stat_modification_amount()
        return [(int(StatType.HEALTH), int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        return [int(StatType.HEALTH)]
