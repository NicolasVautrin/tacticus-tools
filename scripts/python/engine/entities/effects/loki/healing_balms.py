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

⚠ **SIGNE -- NON LU AU DÉCOMPILÉ, et c'est dit** : `isNegative` vit dans la lambda
`EffectsDatabase.<InitializeEffects>b__14_*` qui enregistre 1503/1504 ; ni la recherche littérale
`0x5df`/`1503` dans le pseudo-C (2 résultats, aucun n'est une lambda d'enregistrement) ni les xrefs
n'en exposent le corps sur ce build. Le signe POSITIF retenu ici s'appuie sur trois indices
concordants et AUCUN décompilé : (a) l'i2 écrit `+` pour les deux ; (b) les variables gameconfig
s'appellent `extraCritChance` / `extraCritDmg` ; (c) le jumeau structurel
`AncestralFortune_ExtraCritChance` (0x5cd = 1485, `entities/effects/loki/votann.py`) est POSITIF.
Résidu #966-r1 -- fermer = lire la lambda d'enregistrement, jamais inférer d'une mesure de dégât
(un crit-damage négatif de même magnitude produirait un écart, pas une erreur).

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
        return [(int(StatType.CRIT_DAMAGE), int(amt))]       # signe : cf. en-tête, résidu #966-r1

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
        return [(int(StatType.CRIT_CHANCE), int(amt))]       # signe : cf. en-tête, résidu #966-r1

    def reverted_stats(self) -> "list":
        return [StatType.CRIT_CHANCE]
