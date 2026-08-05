"""Port `IdunBattle.Entities.Abilities.BaseTriggeredAbility` — la base des abilities DECLENCHEES,
et le foyer UNIQUE des DEUX formes de moyenne que la couche TRIGGERED emprunte (#350-r3b).

Symetrique de la couche ACTIVE (`active_ability.py`, #344/#350). La difference de fond :

  * cote ACTIF, `AActiveAbility$$MinMaxDamage{,Average}` sont selectionnees par le corps DEDUPLIQUE
    que le playbook appelle (`GetDamageAmountMain` vs `GetDamage`), et l'arithmetique finale est
    ecrite en dur dans `AActiveAbility.get_damage` ;
  * cote TRIGGERED, les deux constructeurs natifs rendent un **NOEUD DSL**, et c'est le **SLOT
    d'`IAmountFormula`** que le playbook invoque qui decide de l'arrondi. Deux etages, pas un.

Les deux constructeurs, mirror 1:1 du decompile `rnca9r7q6c` :

    IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage(this, abilityState)
        mn = AbilityConfiguration$$GetVariableForLevel(this@+0x20, 0xc /* minDmg */, state, 0)
        mx = AbilityConfiguration$$GetVariableForLevel(this@+0x20, 0xd /* maxDmg */, state, 0)
        return IdunBattleLogic.Entities.DSLFormulas$$RandomAmount(mn, mx)          # noeud a PLAGE

    IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamageAverage(this, abilityState)
        mn, mx = les MEMES variables 0xc / 0xd
        a = IdunBattleLogic.Entities.DSLFormulas$$Direct(mn)
        b = IdunBattleLogic.Entities.DSLFormulas$$Direct(mx)
        return IdunBattleLogic.Entities.DSLFormulas$$Half(
                   IdunBattleLogic.Entities.DSLFormulas$$Sum(a, b), 0)             # noeud SIMPLE

et les deux lectures, mesurees call-site par call-site (`FUN_180025fb0(<slot>, ...)`) :

    slot 4 = `IdunBattle.DSL.AAmountFormula$$CalculateAverage`
             sur `RandomAmount` -> `(max + min) / 2` division ENTIERE C = **TRONCATURE**
    slot 1 = `Calculate`
             sur `Half` -> `IdunBattle.Entities.Formulas.DivideAmount$$Calculate`
             -> `IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` = `Fix64.Round`
             = **DEMI-VERS-LE-PAIR**

Les deux ne divergent QUE lorsque `minDmg + maxDmg` vaut 3 mod 4, d'exactement 1 (ex. 2761 + 2762 :
2761 contre 2762) -- invisible trois fois sur quatre, ce qui est exactement pourquoi le trou a tenu.

RE complet, tableau des 6 call-sites et residus : `docs/rl/case-350r3b-moyennes-triggered.md`.
"""
from __future__ import annotations

from ...dsl.base import DslContext, Const
from ..formulas import Sum, Half, RandomAmount
from ..effects.magnitude import ability_var
from ...entities.ability_variable_type import AbilityVariableType   # #270-r1-r1-r3


# ─── #350-r3b : quel PLAYBOOK lit quelle forme — table LUE par `triggered_prediction_damage` ───────
#
# Clef = le symbole ghidra du CALL-SITE (pas de l'ability : les corps `<X>Ability$$GetDamage` et
# `$$GetAverageDamage` sont DEDUPLIQUES, leur nom ne dit rien de l'ability reellement evaluee).
# Valeur = (getter natif appele, slot d'`IAmountFormula` invoque).
#
# EXHAUSTIF pour `rnca9r7q6c` : la moyenne min/max d'une ability TRIGGERED ne peut naitre que de
# `BaseTriggeredAbility$$MinMaxDamage{,Average}`, dont les xrefs entrantes sont enumerees ici. Les
# 63 AUTRES appelants de `$$MinMaxDamage` sont des `<X>Ability$$CreateBehaviour` : c'est
# l'EXECUTION (un vrai tirage `RandomAmount`), pas la decision -- hors de cette table.
_GET_DAMAGE = "GetDamage"                   # -> BaseTriggeredAbility$$MinMaxDamage
_GET_AVERAGE_DAMAGE = "GetAverageDamage"    # -> BaseTriggeredAbility$$MinMaxDamageAverage

TRIGGERED_PREDICTION_AVERAGE_FORM = {
    # --- voie TRONCATURE : noeud a PLAGE `RandomAmount`, lu au slot 4 ---------------------------
    "IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction":
        (_GET_DAMAGE, 4),
    "IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$EvaluateNonComparable":
        (_GET_DAMAGE, 4),
    # --- voie DEMI-VERS-LE-PAIR : noeud SIMPLE `Half(Sum(...))`, lu au slot 1 -------------------
    "IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityForMainTarget":
        (_GET_AVERAGE_DAMAGE, 1),
    "IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityForSecondaryTarget":
        (_GET_AVERAGE_DAMAGE, 1),
    "IdunBattle.AI.Playbook.Loki.LightImUpPlaybook."
    "u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext":
        (_GET_AVERAGE_DAMAGE, 1),
    "IdunBattle.AI.Playbook.Loki.MassiveScythingTalonsPlaybook."
    "u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext":
        (_GET_AVERAGE_DAMAGE, 1),
}


class BaseTriggeredAbility:
    """Base des abilities DECLENCHEES — mirror `IdunBattle.Entities.Abilities.BaseTriggeredAbility`.

    `ability_id` = id gameconfig de l'ability (str) ; `level` = niveau PASSIF du porteur
    (`UnitExtensions$$GetAbilityState` / `TriggeredAbilityPlaybook<T>$$GetAbilityState`) ;
    `multiplier_pct` = `AbilityVariablesMultiplierPercentage` de l'unite. Les deux indexent
    `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel`, porte par `ability_var`."""

    # Index natifs des variables lues par les deux constructeurs (litteraux du decompile).
    VAR_MIN_DMG = AbilityVariableType.minDmg     # `minDmg`
    VAR_MAX_DMG = AbilityVariableType.maxDmg     # `maxDmg`

    def __init__(self, ability_id: str, level: int | None = None, multiplier_pct: int = 100):
        self.ability_id = ability_id
        self.level = level
        self.multiplier_pct = int(multiplier_pct or 100)

    def _min_max(self) -> tuple[int, int] | None:
        """Les deux variables `0xc`/`0xd` au niveau + multiplicateur du porteur. `None` si l'une des
        deux manque : le natif leverait sur `this@+0x20 == 0` (`FUN_1801f51f0`), le port rend `None`
        plutot que de fabriquer un zero silencieux."""
        mn = ability_var(self.ability_id, "minDmg", self.level, multiplier_pct=self.multiplier_pct)
        mx = ability_var(self.ability_id, "maxDmg", self.level, multiplier_pct=self.multiplier_pct)
        if mn is None or mx is None:
            return None
        return int(mn), int(mx)

    def min_max_damage(self):
        """`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage` — rend le NOEUD
        `RandomAmount(Get(minDmg), Get(maxDmg))` (a PLAGE), PAS un scalaire. `rng=None` : ce noeud
        n'est construit ici que pour la DECISION, qui le lit par `calculate_average` (slot 4) ;
        l'EXECUTION (un vrai tirage) passe par les arbres de `CreateBehaviour`, pas par ce foyer."""
        mm = self._min_max()
        if mm is None:
            return None
        return RandomAmount(Const(mm[0]), Const(mm[1]))

    def min_max_damage_average(self):
        """`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamageAverage` — rend le NOEUD
        `Half(Sum(Direct(minDmg), Direct(maxDmg)), 0)` (SIMPLE). Le `0` est le 3ᵉ argument LU du
        `DSLFormulas$$Half` natif = `roundingRule`, stocke a `DivideAmount@+0x20` et relu par
        `AAmountFormula$$RoundFix64Result` -> `Fix64.Round` demi-vers-le-PAIR."""
        mm = self._min_max()
        if mm is None:
            return None
        return Half(Sum(Const(mm[0]), Const(mm[1])), 0)


def triggered_prediction_damage(ability_id: str, level: int | None, multiplier_pct: int,
                                playbook_call_site: str, ctx: DslContext | None = None) -> int | None:
    """FOYER UNIQUE des deux formes : construit le noeud que le call-site natif construit, et
    l'evalue par le SLOT que ce call-site invoque. `playbook_call_site` = clef de
    `TRIGGERED_PREDICTION_AVERAGE_FORM` (symbole ghidra VERBATIM).

    Un call-site absent de la table leve `KeyError` — DELIBERE : le defaut silencieux est
    exactement la degradation qui a laisse la forme demi-vers-le-pair absente du moteur (le seul
    consommateur triggered porte, Fury, est du cote troncature ; rien ne signalait le trou).
    Entrer un playbook dans le moteur = poser sa ligne ici, dans le meme commit."""
    getter, slot = TRIGGERED_PREDICTION_AVERAGE_FORM[playbook_call_site]
    ability = BaseTriggeredAbility(ability_id, level, multiplier_pct)
    node = (ability.min_max_damage() if getter == _GET_DAMAGE
            else ability.min_max_damage_average())
    if node is None:
        return None
    if ctx is None:
        ctx = DslContext()
    # slot 4 = `AAmountFormula$$CalculateAverage` ; slot 1 = `Calculate`. Aucun autre slot n'est
    # invoque par les 6 call-sites lus -> on ne fabrique pas de branche non observee.
    return int(node.calculate_average(ctx) if slot == 4 else node.calculate(ctx))
