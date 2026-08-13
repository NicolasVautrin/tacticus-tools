"""Les DEUX stat-modifiers du passif `HealingBalms` (`TriggeredAbilityType` 0x5de = **1502**,
`spaceWolfPriest` << Baldr >>, HERO Space Wolves) -- #966.

i2 (autoritatif) : << When Baldr uses his action to heal a friendly unit, the healed unit has
**+{[extraCritChance]}% Crit Chance** and deals **+{[extraCritDmg]} Crit Damage** for
{[nrOfRounds]} rounds. At the start of its next turn, the affected unit is also healed for
{[hpToHeal]} Health. Baldr can heal friendly units even if they are at full Health. >>

Les deux effets sont posés par l'ACTIVE substituée `1212 HealingBalms_Heal`
(`IdunBattleLogic.Entities.Abilities.Active.Loki.HealingBalms_HealAbility$$ExecuteBehaviour`), pas
par le passif lui-même -- le passif se contente du SWAP d'active
(`...Triggered.Loki.HealingBalmsAbility$$CreateBehaviour`, cf. `runner/abilities/loki/healing_balms.py`).

## Ce que le décompilé DIT, et que le tooltip ne dirait pas

`...HealingBalms_HealAbility$$ExecuteBehaviour` (MIRROR, dans SON ordre) :

    nrOfRounds = DSLFormulas.ConfigConst(0x5de = TriggeredAbilityType.HealingBalms,
                                         Owner@DSLSelectors+0x30,
                                         0x45 = AbilityConstantType.nrOfRounds)
    RemoveEffect(Target@+0x60, Nullable(0x5df = HealingBalms_ExtraCritDamage), null)
      op_Addition RemoveEffect(Target@+0x60, Nullable(0x5e0 = HealingBalms_ExtraCritChance), null)
    AddDynamicStatModifierEffect(targets = Target@+0x60, source = Owner@+0x30,
        effectType = 0x5df, statType = 10 = CriticalDamage,
        abilityStateSelector = AActiveAbility.AbilityStateReference,
        turns = TurnsFromRounds(nrOfRounds), isHidden = false)
      op_Addition AddDynamicStatModifierEffect(..., 0x5e0, statType = 9 = CriticalChance, ...)
    ...

⚠ **Le `RemoveEffect` PRÉCÈDE le ré-ajout, et il porte sur la CIBLE, pas sur le caster** : re-soigner
la même unité ne CUMULE pas les deux buffs, il les RÉ-ARME (durée remise à `nrOfRounds`). Un port qui
n'émettrait que l'`Add` empilerait deux instances -- écart SILENCIEUX de magnitude.

⚠ **L'APPARIEMENT effectType <-> statType est INVERSE de ce que le nom laisse croire à la lecture
rapide** : `0x5df` est `ExtraCritDAMAGE` et porte `statType = 10 = CriticalDamage` ; `0x5e0` est
`ExtraCritCHANCE` et porte `statType = 9 = CriticalChance`. Les deux ordinaux se suivent, les deux
noms aussi -- les intervertir ne lèverait AUCUNE erreur (mesure : les deux stats existent sur toute
unité). Ordinaux LUS dans `data/symbols/<build>/frida/enums.tsv`, jamais devinés.

⚠ **La rarity-scale n'est PAS symétrique** (gameconfig `abilities.HealingBalms`) :
`variablesAffectedByRarityBonus = [extraCritDmg, hpToHeal]` -- `extraCritChance` en est ABSENT.
`ability_var` n'applique le multiplicateur qu'aux variables listées, donc passer `multiplier_pct`
dans les deux cas reste correct PAR CONSTRUCTION (même arbitrage qu'`AncestralFortune` #votann).

**SIGNE -- LU AU DÉCOMPILÉ : POSITIF pour les DEUX** (#966-r1 FERMÉ). Le signe n'est ni dans
l'ability ni dans le behaviour : il est figé à l'ENREGISTREMENT, par le 3ᵉ argument `isNegative` d'
`IdunBattle.Entities.Effects.DynamicStatModifierEffect$$.ctor`
(`.ctor(AbilityType, AbilityVariableType, bool isNegative, bool canBeImmuneTo)`). Les deux fabriques
sont `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_498`
(EffectType 1503) et `...b__14_497` (1504) ; toutes deux, verbatim :

    mov edx, 0x5de ; call AbilityType$$op_Implicit   -> set_TriggeredAbility (HealingBalms 1502)
    xor r9d, r9d                        ; isNegative = FALSE
    mov r8d, 0x42 (= 66 extraCritDmg) | 0x41 (= 65 extraCritChance)
    mov byte ptr [rsp+0x20], 0          ; canBeImmuneTo = false
    call DynamicStatModifierEffect$$.ctor

⚠ **POURQUOI LA RECHERCHE DE `1503`/`0x5df` NE POUVAIT RIEN RENDRE, et l'énoncé du résidu se
trompait de cause** : `_effectsBuilder` est un `Dictionary<EffectType, Func<IEffect>>` -- la CLÉ vit
chez l'appelant, **la lambda ne porte JAMAIS l'EffectType**. C'est `0x5de` (l'ABILITY) qu'il fallait
chercher. Et `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` fait **20 205
instructions**, donc le pseudo-C ne la rend pas -- d'où le faux constat « l'inscription passe par
une table de données ». L'appariement effectType <-> fabrique se lit dans cette fonction, par
l'offset du cache de délégué `u003Cu003E9__14_N` (= `8 + 8*N`) : clé `0x5df` -> `+0xf98` -> `N=498`
(`extraCritDmg`) ; clé `0x5e0` -> `+0xf90` -> `N=497` (`extraCritChance`). Chaque clé n'apparaît
qu'UNE fois dans les 607 entrées, et l'auto-cohérence nom <-> variable valide la formule d'index.

**TÉMOIN NÉGATIF -- le flag n'est pas inerte** : sur les **14** fabriques `DynamicStatModifierEffect`
du build, **13 posent `xor r9d, r9d` (false) et UNE SEULE `mov r9b, 1` (true)** --
`...u003CInitializeEffectsu003Eb__14_533` -> clé `0x605` = 1541 `AugmentedAssault_ReduceArmor`
(`variableType = 48 armorReduction`). Les deux enregistrements sont structurellement IDENTIQUES :
seul `r9` change. Un accord sans ce témoin ne prouverait rien.

**APPLICATION -- foyer UNIQUE** `IdunBattle.Entities.Effects.DynamicStatModifierEffect$$GetDynamicStatModificationAmount` :
`neg eax` puis `cmp byte ptr [rbx+0x4a4], 0` / `cmove eax, esi` -> `_isNegative == 0` garde le
POSITIF. L'ORDRE des arguments est figé par le ctor lui-même (`_abilityType` `+0x490`,
`_variableType` `+0x4a0`, `_isNegative` `+0x4a4` écrit depuis `r9b`) : `canBeImmuneTo`, lui, transite
par la pile -- toute confusion entre les deux booléens est exclue.

Lus au même endroit et CONFORMES au port : `abilityType` = `TriggeredAbilityType` (les variables
sont donc bien lues dans la config du PASSIF `HealingBalms`, cf. `HEALING_BALMS` plus bas, qui
cesse d'être une inférence) ; `isMultiply = false` (stat-mod ADDITIF) ; `keepOnRevive = true` ;
`canBeImmuneTo = false`.

ASCII only.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
from ...stats import StatType

#: Nom gameconfig du PASSIF -- c'est SA config que `ConfigVar` indexe (le `1212` n'a AUCUNE entrée
#: `abilities.*` : il est substitué au `18 Heal`, exactement comme `1167 Heal_TwistedScience`).
HEALING_BALMS = "HealingBalms"

#: `AbilityVariableType` -- ordinaux LUS (`frida/enums.tsv`), pas devinés.
EXTRA_CRIT_CHANCE_KEY = "extraCritChance"      # PAS dans `variablesAffectedByRarityBonus`
EXTRA_CRIT_DMG_KEY = "extraCritDmg"            # DANS `variablesAffectedByRarityBonus`


def _source_level_mult(effect, stats_ctx) -> tuple:
    """`(level, multiplier)` de l'`AbilityState` sous lequel l'effet a été posé.

    `AActiveAbility$$get_AbilityStateReference` : les `ConfigVar` de l'effet se résolvent contre
    l'état d'ability de sa SOURCE (Baldr), jamais contre celui du porteur (l'allié soigné).
    `AddEffectOperation` seede ces champs sur l'instance (`scale_from_source`) -> on les lit sur
    l'EFFET en priorité ; le `stats_ctx` (ctx du PORTEUR) n'est le repli que pour les instances
    captées one-shot. Même helper que `entities/effects/loki/votann.py::_source_level_mult`."""
    lvl = effect.active_ability_level
    if lvl is None:
        lvl = effect.ability_level
    if lvl is None and stats_ctx is not None:
        lvl = getattr(stats_ctx, "active_ability_level", None)
    lvl = int(lvl) if lvl is not None else 0
    mult = effect.ability_variables_multiplier
    if (mult is None or int(mult) == 100) and stats_ctx is not None:
        mult = getattr(stats_ctx, "ability_variables_multiplier", 100)
    return lvl, int(mult or 100)


class HealingBalmsExtraCritDamageEffect(BaseEffect):
    """`HealingBalms_ExtraCritDamage` (`EffectType` 0x5df = **1503**) -- stat-mod
    **CriticalDamage (10)** posé sur la CIBLE du soin, source = Baldr.

    Call-site (`...HealingBalms_HealAbility$$ExecuteBehaviour`, décompilé) :

        AddDynamicStatModifierEffect( targets = Target@DSLSelectors+0x60,
                                      source  = Owner@DSLSelectors+0x30,
                                      effectType = 0x5df, statType = 10 = CriticalDamage,
                                      AbilityStateReference,
                                      turns = TurnsFromRounds(ConfigConst(HealingBalms, Owner,
                                                                          nrOfRounds)),
                                      isHidden = false )

    C'est le couple `+0x58 source` / `+0x60 targets` d'`AddStatModifierEffectBehaviour$$.ctor` qui
    tranche « self-buff vs buff sur la cible », pas le nom : ici `targets = Target` -> l'ALLIÉ SOIGNÉ
    porte le buff. Magnitude = `extraCritDmg[niveau ACTIF de Baldr] x multiplicateur de rareté`
    (`extraCritDmg` EST dans `variablesAffectedByRarityBonus`).

    ⚠ Le gate de décision `HealingBalms_HealPlaybook$$CalculateCustomUtility` interroge CET
    effet-ci (`HasEffect(target, 0x5df)`), pas son jumeau `_ExtraCritChance` -- cf.
    `engine/playbook/common.py::HealingBalms_HealPlaybook` (#27-4d). Les deux sont posés ensemble,
    donc les deux gates coïncident ; la citation, elle, se lit au décompilé."""
    stat_mod_source = None      # clé de source `ChangeStat` (revert par-source via `RemoveEffect`)

    def applied_stat_mods(self, stats_ctx) -> "list":
        """DATA du `ChangeStat` (StatPart 5 = MODIFICATION) appliqué par
        `AddEffectOperation._apply_stat_mods` (= `AStatModifierEffect$$ApplyModification` natif)."""
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(HEALING_BALMS, EXTRA_CRIT_DMG_KEY, lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.CRIT_DAMAGE), int(amt))]       # POSITIF LU : isNegative = false au ctor (cf. en-tete)

    def reverted_stats(self) -> "list":
        return [StatType.CRIT_DAMAGE]


class HealingBalmsExtraCritChanceEffect(BaseEffect):
    """`HealingBalms_ExtraCritChance` (`EffectType` 0x5e0 = **1504**) -- stat-mod
    **CriticalChance (9)** posé sur la CIBLE du soin, source = Baldr. Jumeau exact de
    `HealingBalmsExtraCritDamageEffect` ci-dessus, au couple (effectType, statType) près.

    ⚠ Magnitude NON rarity-scale : `extraCritChance` est ABSENT de
    `variablesAffectedByRarityBonus` (gameconfig `abilities.HealingBalms`), à la différence de son
    jumeau. `ability_var` ne multiplie que les variables listées, donc l'appel avec
    `multiplier_pct` reste correct par construction -- il ne mordra simplement pas."""
    stat_mod_source = None

    def applied_stat_mods(self, stats_ctx) -> "list":
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(HEALING_BALMS, EXTRA_CRIT_CHANCE_KEY, lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.CRIT_CHANCE), int(amt))]       # POSITIF LU : isNegative = false au ctor (cf. en-tete)

    def reverted_stats(self) -> "list":
        return [StatType.CRIT_CHANCE]
