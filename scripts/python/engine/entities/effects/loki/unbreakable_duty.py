"""`UnbreakableDuty_Health` (1251 = 0x4e3) et `UnbreakableDuty_Damage` (1256 = 0x4e8) — les deux
self-buffs PERMANENTS de l'active `UnbreakableDuty` de `templAncient` (« Thoread »).

ARTEFACT NATIF : aucune classe d'effet dediee — deux instances GENERIQUES
`IdunBattle.Entities.Effects.StaticStatModifierEffect`, posees par la feuille
`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffectToOwner`
(signature `(effectType, statType, amount, turns, isHidden)`) de
`IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$ExecuteBehaviour` :

    AddStaticStatModifierEffectToOwner(0x4e3 = 1251, stat = 5    HEALTH,
                                       ConfigVar(0x1e = extraHp,  abilityState), turns = NULL)
    + ChangeStat(Owner, Position(HEALTH, part 0), Modify, <le MEME ConfigVar>, ..., OnlyAlive)
    AddStaticStatModifierEffectToOwner(0x4e8 = 1256, stat = 0    ATTACK,
                                       ConfigVar(8    = extraDmg, abilityState), turns = NULL)

le tout sous `If(AmountIsEqualOrGreater(Count(UnitsWithTraits(Friends(AllDeadOrResurrectedUnits),
[0x1a, 0x10])), Direct(2)), <les buffs + l'attaque libre>, null)` — il faut >= 2 allies morts. Le
`ChangeStat` qui accompagne 1251 monte la sante COURANTE du meme montant (c'est le patron « +max HP
ET +HP courants ») ; il n'appartient pas a l'entite-effet et n'est donc pas porte ici.

`turns = NULL` => **PERMANENTS**. Le bug de DUREE que ferme le lot G1 (case-371) ne les concerne
donc PAS : rien ne les fait expirer. Ce que leur inscription ferme est l'**ATTRIBUTION** — sans elle,
les deux contributions tombent dans le RESIDU OPAQUE (`CAPTURED_SOURCE`) de `seed_unit_stats`, ou
elles ne sont ni verifiables (aucune confrontation « somme des magnitudes config == statDelta natif »)
ni retirables si un chemin de retrait apparait. Avec elle, `residu == 0` sur les deux stats devient
une validation NON CIRCULAIRE : le montant vient de gameconfig, le delta vient du natif.

⚠ CONTRE-EPREUVE OBLIGATOIRE (garde `test_static_statmod_g1_expiry.py`) : declares, ils ne doivent
RIEN perdre au tick de duree. `EffectComponent$$RemoveOneTurn` a pour gate `!Removed && HasTurns`,
et `remaining <= 0` est materialise `None` (PERMANENT) par `EffectFactory` — meme regime que
`ProtectorImperative`.

MAGNITUDES : `ConfigVar(0x1e)` et `ConfigVar(8)` == `UnbreakableDuty.variables.extraHp[level]` /
`.extraDmg[level]`. L'index 0x1e est tranche par ELIMINATION STRICTE sur les TROIS variables de
l'ability : `extraDmg` = 8 (index etabli par une dizaine de ports), `dmgReductionPct` = 0x46 (lu
sur `IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDuty_DamageReductionEffect$$CreateEffectDamageMalusForDefense`,
meme index que `SereneUnifierSenseOfStoneEffect`), donc 0x1e = `extraHp` — la seule restante, et la
seule dont la semantique va sur le stat HEALTH. Les DEUX sont dans `variablesAffectedByRarityBonus`
-> scalees par l'`AbilityVariablesMultiplierPercentage`.

`UnbreakableDuty` est une ability ACTIVE -> le niveau est `active_ability_level` (patron
`StandVigilExtraArmorEffect`), avec repli passif puis stack level.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var

_ABILITY_ID = "UnbreakableDuty"


def _active_level(eff: BaseEffect) -> int | None:
    """Niveau indexant les `variables[level]` d'une ability ACTIVE (mirror `StandVigil`)."""
    if eff.active_ability_level is not None:
        return eff.active_ability_level
    return eff.ability_level if eff.ability_level is not None else eff.level


class UnbreakableDutyHealthEffect(BaseEffect):
    """`UnbreakableDuty_Health` (0x4e3 = 1251) — +`extraHp` sur HEALTH, PERMANENT (turns = NULL)."""

    def get_stat_modification_stat(self) -> int | None:
        return 5                                     # StatType.HEALTH

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "extraHp", _active_level(self),
                           multiplier_pct=self.ability_variables_multiplier)


class UnbreakableDutyDamageEffect(BaseEffect):
    """`UnbreakableDuty_Damage` (0x4e8 = 1256) — +`extraDmg` sur ATTACK, PERMANENT (turns = NULL)."""

    def get_stat_modification_stat(self) -> int | None:
        return 0                                     # StatType.ATTACK

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "extraDmg", _active_level(self),
                           multiplier_pct=self.ability_variables_multiplier)
