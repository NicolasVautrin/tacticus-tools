"""#951 -- `TrophyTaker` (`TriggeredAbilityType.TrophyTaker` = 1229), passif de `worldExecutions`
(« Tarvakh »). Face EFFET : `TrophyTaker_ExtraCritDamage` (`EffectType` 0x509 = 1289).

i2 : le porteur frappe plus fort les cibles deja entamees, et sa chance de critique monte a chaque
unite normale qu'il a vaincue. Les deux moities vivent dans des ARTEFACTS NATIFS DIFFERENTS, et
c'est ce qui decide du canal de port :

* le +DEGAT et le +DEGAT DE CRIT sont deux `EffectBonus` de la classe d'effet 1289, evalues
  CALC-TIME a chaque coup -- ils n'existent nulle part dans l'etat ;
* la +CHANCE DE CRIT est un STAT-MODIFIER (`EffectType` 0x508 = 1288, `StatType.CriticalChance`)
  re-ecrit sur `On(UnitDefeated)`. Il vit dans `runner/operations/triggers/loki/trophy_taker.py`.

## Le decompile (build `rnca9r7q6c`, surcharges tranchees a l'ENCODAGE -- `probe_951_call_targets`)

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.TrophyTakerAbility$$CreateBehaviour
        if (triggerType == EventTriggerType.UnitDefeated)   -> face STAT-MOD (cf. le trigger)
        else                                                -> AddEffect(0x509, AbilityStateReference,
                                                                        targets: Owner@+0x30,
                                                                        turns: Nullable<int> VIDE)

    IdunBattle.Entities.Effects.Loki.TrophyTaker_ExtraCritDamageEffect$$.ctor
        BaseEffect..ctor(AbilityOrEffect(TriggeredAbilityType.TrophyTaker = 0x4cd),
                         hasAutomaticActivation: true)

    ...$$HealthLowerThanPct
        NOT AmountIsEqualOrGreater(
                StatAmount(Target@+0x60, StatType.Health = 5, StatPart.CurrentPct = 1,
                           modificationEntity: null, UnitSelectionType.Any = 0),
                Direct(GetNumberConstant(AbilityConstantType.hpPct = 0x12)) )

    ...$$CreateEffectDamageBonusForAttack
        ForAddition( get_OwnerIsCaster & HealthLowerThanPct(),
                     ConfigVar(AbilityVariableType.extraDmg = 0x8, GetAbilityState(this), config),
                     abilityOrEffect: AbilityOrEffect(TriggeredAbilityType.TrophyTaker) )

    ...$$CreateCritDamageBonus
        ForAddition( get_OwnerIsCaster & HealthLowerThanPct(),
                     ConfigVar(AbilityVariableType.extraCritDmg = 0x42, GetAbilityState(this), config),
                     abilityOrEffect: AbilityOrEffect(TriggeredAbilityType.TrophyTaker) )

## Ce que la lecture DES OCTETS a tranche, et que le pseudo-C ne disait pas

1. **`AmountIsEqualOrGreater`, pas `AmountIsGreater`** -- deux classes distinctes, deux corps. Le
   gate est donc `NOT (pct >= hpPct)`, soit **`pct < hpPct`** strict. Avec `hpPct = 50`, une cible
   a EXACTEMENT 50 % ne donne AUCUN bonus. Un `<=` aurait double le bonus sur ce cas-la.
2. **La surcharge d'`AmountIsEqualOrGreater` est `(amount, minAmount)`**, pas `(selector,
   minAmount)` : le premier operande est la FORMULE `StatAmount`, pas un selecteur d'unites.
3. **`StatPart.CurrentPct` (1)** -- ce n'est ni `Current` (0) ni `Missing` (4). Sa formule est lue
   dans `IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart` case 1 :

       Fix64.op_Explicit( Fix64.Round( Max(Fix64(0), Fix64(current) / Fix64(CurrentMaximumValue))
                                       * Fix64(100), mode 0 ) )

   soit un pourcentage ARRONDI demi-vers-le-PAIR (`AAmountFormula$$RoundFix64Result` mode 0), pas
   une troncature. `StatComponent$$GetStatPart` n'a PAS de `case 1` (il leverait
   `ArgumentOutOfRangeException`) : ce chemin-la est propre au `FillUpStatComponent`, celui de
   Health/Shield. Le port reutilise le foyer d'arrondi PARTAGE `dsl.base._round_fix64`.
4. **La cible du gate est `Target@+0x60`**, la victime du coup -- jamais le porteur. C'est ce qui
   fait de TrophyTaker un passif d'EXECUTION et non un passif de baroud d'honneur.
5. **`ConfigVar` y prend la surcharge `abilityState: IAbilityStateSelector`** (celle de
   `BaseEffect$$GetAbilityState`), la ou la face STAT-MOD prend la surcharge `AbilityState`
   (struct). Meme nom, deux corps -- l'un lit l'etat de l'EFFET, l'autre celui de l'ABILITY.

## Rarete

`variablesAffectedByRarityBonus == ["extraDmg", "extraCritDmg"]` -- les deux magnitudes de ce
fichier sont rarity-scalees, et `extraCritChance` (l'autre face) ne l'est PAS. Ce fait ne se lit
que dans le gameconfig ; `ability_var(multiplier_pct=...)` le porte.

## PAS d'entree `ABILITY_INIT_OWNER_EFFECTS`, et c'est MESURE

L'effet n'a NI `CreateActiveCondition` NI `ApplyInternal` (le bloc `methodPointers` de la classe
tient en quatre corps : `.ctor`, `HealthLowerThanPct`, `CreateCritDamageBonus`,
`CreateEffectDamageBonusForAttack`). Il est donc ACTIF des sa pose et apparait dans
`decisionView.effects`, que le seed lit deja -- l'inscrire au registre de seed le materialiserait
une seconde fois. Le motif inverse (`AnvilShield`/`CamoCloak`) ne s'applique qu'aux effets qu'une
`CreateActiveCondition` eteint au moment de la capture.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect, owner_is_caster
from ..magnitude import ability_var
from ...ability_constant_type import AbilityConstantType
from ....dsl.base import _round_fix64
from ....services.effect_bonus import EffectBonus, for_addition

ABILITY_ID = "TrophyTaker"

VAR_EXTRA_DMG = "extraDmg"                        # `AbilityVariableType` 0x08 = 8
VAR_EXTRA_CRIT_DMG = "extraCritDmg"               # `AbilityVariableType` 0x42 = 66
CONST_HP_PCT = AbilityConstantType.hpPct          # 0x12 = 18


def health_current_pct(hp, hp_max) -> "int | None":
    """`StatAmount(unit, StatType.Health, StatPart.CurrentPct)` -- mirror de
    `IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart` case 1 :
    `Round(Max(0, current / maximum) * 100, mode 0)`, arrondi demi-vers-le-PAIR.

    Tri-etat : `None` = PAS MESURE (PV ou maximum absents du contexte du coup) -- le gate se TAIT
    alors, il ne devine pas un pourcentage. `hp_max <= 0` rend `None` de meme : le natif y
    diviserait par zero, donc aucun arbre valide ne l'atteint et le port refuse d'inventer."""
    if hp is None or hp_max is None:
        return None
    try:
        hp, hp_max = int(hp), int(hp_max)
    except (TypeError, ValueError):
        return None
    if hp_max <= 0:
        return None
    from fractions import Fraction
    q = Fraction(hp, hp_max)
    if q < 0:                                      # `Fix64.Max(0, .)`
        q = Fraction(0)
    return _round_fix64(q * 100, 0)                # `AAmountFormula$$RoundFix64Result` mode 0


def health_lower_than_pct(att_ctx: "Mapping | None") -> bool:
    """`...TrophyTaker_ExtraCritDamageEffect$$HealthLowerThanPct` = `NOT AmountIsEqualOrGreater(
    StatAmount(Target, Health, CurrentPct), Direct(hpPct))`, donc **`pct < hpPct` STRICT**.

    `False` quand la mesure manque (`tgt_hp`/`tgt_hp_max` non threades, ou constante absente) :
    « present != applique ». Foyer UNIQUE des deux canaux (`CreateEffectDamageBonusForAttack` et
    `CreateCritDamageBonus` appellent le MEME corps natif) -- les deux ne peuvent donc pas
    diverger, exactement comme cote natif."""
    c = att_ctx or {}
    pct = health_current_pct(c.get("tgt_hp"), c.get("tgt_hp_max"))
    if pct is None:
        return False
    seuil = ability_var(ABILITY_ID, CONST_HP_PCT.name, is_constant=True)
    if seuil is None:
        return False
    return int(pct) < int(seuil)


class TrophyTakerExtraCritDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.TrophyTaker_ExtraCritDamageEffect` (`EffectType` 0x509).
    UN effet, DEUX canaux de bonus -- c'est le natif qui les porte tous deux sur la meme classe
    (`CreateEffectDamageBonusForAttack` et `CreateCritDamageBonus`), avec le MEME trigger."""

    def _magnitude(self, cle: str) -> "int | None":
        """`ConfigVar(<var>, GetAbilityState(this), config)`. `ability_level is None` = l'effet n'a
        pas d'`AbilityState` -> le noeud natif est INERTE (pas de magnitude), jamais 0."""
        if self.ability_level is None:
            return None
        v = ability_var(ABILITY_ID, cle, self.ability_level,
                        multiplier_pct=self.ability_variables_multiplier)
        return int(v) if v else None

    def _gate(self, att_ctx: "Mapping | None", balayage_board: bool) -> bool:
        """`get_OwnerIsCaster & HealthLowerThanPct()` -- les deux conjoints natifs, dans l'ordre.

        ⚠ `balayage_board` n'est PAS une option de confort : les deux canaux du port n'ont pas le
        MEME univers de porteurs, et le natif oui.
          * canal CRIT (`crit_damage_bonus_from_effects`) : balayage BOARD-WIDE aligne sur
            `EffectsQuery$$GetActiveEffectsWithBonuses` (#589-r1-r1) -- le porteur peut etre
            n'importe qui, donc `get_OwnerIsCaster` DOIT etre evalue, et l'agregateur pose
            `owner_id` par porteur pour cela.
          * canal DEGAT (`_attacker_effect_bonuses`) : la boucle ne recoit QUE les effets de
            l'ATTAQUANT, et son `att_ctx` NE POSE PAS `owner_id` (mesure : `damage_model.py` y
            thread `tgt_hp`/`tgt_hp_max`/`tgt_id`, jamais `owner_id`). Y appeler `owner_is_caster`
            rendrait donc `False` PARTOUT et effacerait le bonus en silence -- la degradation
            permissive a l'envers. Le conjoint est satisfait par CONSTRUCTION de la boucle, comme
            pour `HeadClaimer_ExtraDmg` et les ~50 autres effets de ce canal."""
        if balayage_board and not owner_is_caster(att_ctx):
            return False
        return health_lower_than_pct(att_ctx)

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits=None, is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> "EffectBonus | None":
        """`$$CreateEffectDamageBonusForAttack` = `ForAddition(<gate>, ConfigVar(extraDmg))`.
        AUCUN gate de nature de coup : ni `IsRangedAttack` ni `IsNormalAttack` dans le corps natif
        -- le bonus vaut sur la melee comme sur le tir, attaque normale comme ability."""
        if not self._gate(att_ctx, balayage_board=False):
            return None
        amt = self._magnitude(VAR_EXTRA_DMG)
        return for_addition(True, amt) if amt else None

    def create_effect_crit_damage_bonus_for_attack(self,
                                                   att_ctx: "Mapping | None" = None) -> "int | None":
        """`$$CreateCritDamageBonus` = `ForAddition(<le MEME gate>, ConfigVar(extraCritDmg))`.
        Retour ENTIER (pas un `EffectBonus`) : `GetCritDamageBonusFromEffects` accumule
        `addition - subtraction`, et ce canal-ci n'a que de l'addition."""
        if not self._gate(att_ctx, balayage_board=True):
            return None
        return self._magnitude(VAR_EXTRA_CRIT_DMG)
