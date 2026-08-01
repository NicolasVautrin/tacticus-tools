"""`ReinforcedHiveNode` (passif du SUMMON `tyranSmnWarrior` << Tyranid Warrior >>, invoque par
`tyranWingedPrime` via l'active `AlphaWarrior` (1112) -- TriggeredAbilityType 0x459 = 1113) --
volet **ARMURE** (`1108 ReinforcedHiveNode_ExtraArmor`, 0x454).

i2 (`Abilities/ReinforcedHiveNode_CurrentLevelDescription`) : << Every second round - starting from
the first the Tyranid Warrior is in play - the Tyranid Warrior has +100% Armour and - if it has
Block - 100% Block chance. >>

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite
================================================================================================

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ReinforcedHiveNodeAbility$$CreateBehaviour`

    AddStaticStatModifierEffectToOwner(
        0x454 = 1108 ReinforcedHiveNode_ExtraArmor,
        statType = 0x10 = 16 FixedArmor,
        amount   = PercentageOf( StatAmount( Owner@DSLSelectors+0x30,
                                             statType = 0x10 = 16 FixedArmor,
                                             statPart = 3 = Initial,
                                             modificationEntity = null, selectionType = 0 ),
                                 Direct( GetNumberConstant(0x4a = extraArmorPct) ),
                                 roundingRule = 0 ),
        turns = null (PERMANENT), isHidden = false )
  & AddStatOverrideEffectToOwner(
        0x455 = 1109 ReinforcedHiveNode_ExtraBlock,
        statType = 7 = BlockChance,
        amount   = Direct( GetNumberConstant(0x2d = blockChance) ),
        turns = null )

(`AbilityBehaviour.op_BitwiseAnd` des deux feuilles ; slots `DSLFactory` : `+0x78 Behaviors ·
+0x80 Formulas · +0x88 Triggers · +0x90 Selectors`, et `DSLSelectors+0x30 = Owner`.)

`gameconfig.ability('ReinforcedHiveNode')` : AUCUNE `variables`, deux `constants` --
`extraArmorPct = 100` et `blockChance = 100`. Les constantes ne sont NI indexees par niveau NI
scalees par `variablesAffectedByRarityBonus` (la table est absente). Le volet ARMURE vaut donc
**+100 % de la part Initial de FixedArmor du PORTEUR** = un DOUBLEMENT exact de son armure.

## `CreateActiveCondition` -- UN SEUL CORPS NATIF POUR LES DEUX EFFETS (folding IL2CPP)

`IdunBattle.Entities.Effects.Loki.ReinforcedHiveNode_ExtraBlockEffect$$CreateActiveCondition` =
`return ReinforcedHiveNodeAbility.GetEffectActiveCondition(this+0x48)`, et
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ReinforcedHiveNodeAbility$$GetEffectActiveCondition` :

    AmountIsOdd( Sum( RoundsStarted(Owner@DSLSelectors+0x30), <DSLFormulas+0x20 = Direct(1)> ) )

=> ACTIF ssi `turnsStarted(porteur) + 1` est IMPAIR, c'est-a-dire ssi **`turnsStarted(porteur)` est
PAIR** (0, 2, 4, ...). `RoundsStarted` = `IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate`
= SOMME de `UnitComponent.turnsStarted@+0x58` sur les unites du selecteur (ici mono-unite = le
porteur), meme grandeur que `GetStat(unit, 0xc = TURNS_STARTED)`.

⚠ PIEGE DE TABLE, RESOLU PAR LA TABLE DE POINTEURS DE METHODES (pas par les noms) -- `functions.tsv`
et `methods.tsv` sont DEDUPLIQUEES PAR ADRESSE, donc un corps FONDU n'a qu'UN proprietaire nomme, et
ici c'est `ExtraBlockEffect`. Lire la table serait donc conclure a tort que `ExtraArmorEffect` n'a
PAS de condition active. Le discriminant utilise est la table `g_MethodPointers`, ordonnee PAR
CLASSE : le bloc de `ReinforcedHiveNode_ExtraArmorEffect` (`.ctor` @ son entree, puis
`CreateActiveCondition`, puis `CreateTargetSelector`) et celui de `ReinforcedHiveNode_ExtraBlockEffect`
sont CONSECUTIFS et portent, pour leurs 2e et 3e slots, les MEMES adresses -- le corps de
`CreateActiveCondition` (celui nomme `ExtraBlockEffect$$CreateActiveCondition`) et celui de
`CreateTargetSelector` (nomme `IdunBattle.Entities.Effects.Loki.WhisperingWebEffect$$CreateTargetSelector`,
`return <this+0x48>->Selectors+0x30` = **Owner**). Les DEUX classes declarent donc les DEUX methodes.
C'est le patron exact de `DestroyTheWitch_*` (cf. `loki/destroy_the_witch.py`).

## Les DEUX classes sont DISTINCTES (perimetre de ce port)

`classes.tsv` : `ReinforcedHiveNode_ExtraArmorEffect` derive de
`IdunBattle.Entities.Effects.StaticStatModifierEffect`, `ReinforcedHiveNode_ExtraBlockEffect` de
`IdunBattle.Entities.Effects.StatOverrideEffect` -- DEUX slots `Il2CppClass*`, DEUX `.ctor`
distincts, DEUX entrees dans `EffectsDatabase.<>c$$<InitializeEffects>b__14_135` / `..._136`. Ce
n'est PAS une classe unique parametree : seul **1108** est porte ici.

RESIDU NOMME -- **1109 `ReinforcedHiveNode_ExtraBlock`** :
`IdunBattle.Entities.Effects.Loki.ReinforcedHiveNode_ExtraBlockEffect$$.ctor` =
`StatOverrideEffect..ctor(this, 0x459 = TriggeredAbilityType.ReinforcedHiveNode, unitEffectType = 0)`.
C'est un **StatOverride** (part 7 `ChangeStat` mode 4 -> `ValueOverride.SetOverride`), PAS un
stat-modifier additif : `BlockChance` est FORCEE a `blockChance = 100`, et le port n'a pas encore de
canal declaratif `overridden_stats` conditionne par une `CreateActiveCondition` (`overridden_stats()`
n'est lu que par `AddEffectOperation._apply_stat_overrides`, chemin de POSE, jamais par
`refresh_stat_modifier_effects`). Le porter exige d'elargir ce driver -- hors perimetre de ce cas.

## `.ctor` du volet ARMURE

`IdunBattle.Entities.Effects.Loki.ReinforcedHiveNode_ExtraArmorEffect$$.ctor` (octets relus) :
`StaticStatModifierEffect..ctor(this, sourceAbility = Nullable<AbilityOrEffect>(op_Implicit(0x459 =
TriggeredAbilityType.ReinforcedHiveNode)), unitEffectType = 0, canBeImmuneTo = 0, keepOnRevive = 1,
isMultiply = 0)`. `canBeImmuneTo = 0` -> le defaut `BaseEffect.can_be_immune_to = False` est exact.

================================================================================================
FORME DU PORT
================================================================================================
Canal **stat-mod a magnitude CONTEXTUELLE** (`applied_stat_mods(stats_ctx)`), et non le couple
`get_stat_modification_amount()` de la base : la magnitude native lit une STAT DU PORTEUR
(`StatAmount(Owner, FixedArmor, Initial)`), qui n'est pas lisible sans le `UnitContext`. C'est la
forme OVERRIDE d'`ApplyModification` que `effect_stat_modifications(eff, stats_ctx)` privilegie
(point de verite unique R16) ; `get_stat_modification_stat()` reste declare -- c'est lui que
`refresh_stat_modifier_effects` lit pour savoir QUEL stat reverter quand la condition tombe.

Cette classe est la PREMIERE du registre a declarer `applied_stat_mods` ET a surcharger
`is_active` : c'est exactement ce que le discriminant `_active_condition_is_ported` de
`runner/operations/refresh_effects.py` (#417) autorise -- une classe qui SAIT lire sa
`CreateActiveCondition` re-evalue et ECRIT le flag `EffectComponent.IsActive @+0x5c`. Le skip du
driver porte sur la CLE de pose (`stat_mod_source`), pas sur la methode declaree : une instance
SEEDEE (`stat_mod_source is None`, le seul regime de cet effet -- aucun vecteur de pose OFFLINE ne
materialise 1108) reste donc bien pilotee par le driver.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect

REINFORCED_HIVE_NODE = "ReinforcedHiveNode"


class ReinforcedHiveNodeExtraArmorEffect(BaseEffect):
    """`ReinforcedHiveNode_ExtraArmor` (EffectType 0x454 = 1108) -- `StaticStatModifierEffect`
    PERMANENT pose sur le porteur par `ReinforcedHiveNodeAbility$$CreateBehaviour`
    (`AddStaticStatModifierEffectToOwner(1108, stat = 16 FixedArmor,
    PercentageOf(StatAmount(Owner, FixedArmor, Initial), Direct(extraArmorPct)))`), ACTIF un round
    sur deux (`turnsStarted` du porteur PAIR)."""

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """MIRROR du corps natif FONDU `CreateActiveCondition` (cf. en-tete) :
        `AmountIsOdd( Sum( RoundsStarted(Owner), Direct(1) ) )`.

        `AmountIsOdd(a)` = `NOT AmountIsEven(a)` = `(a & 1) == 1` (cf.
        `engine/entities/triggers.py::AmountIsOdd`), donc actif ssi `turnsStarted` est PAIR.

        Lit `unit_state["turns_started"]` (= `GetStat(porteur, 0xc = TURNS_STARTED)`, renseigne par
        `runner/components.py::UnitEffectStateView`). Cle ABSENTE = contexte non fourni -> True
        (<< present == actif >>, meme degradation que `DestroyTheWitch_*` : le seed live ne capte
        QUE les effets actifs par le canal par defaut)."""
        if unit_state is None or "turns_started" not in unit_state:
            return True
        return ((int(unit_state.get("turns_started") or 0) + 1) & 1) == 1

    def get_stat_modification_stat(self) -> "int | None":
        from ...stats import StatType
        return int(StatType.FIXED_ARMOR)          # statType 0x10 de la feuille native

    def applied_stat_mods(self, stats_ctx) -> "list":
        """Forme OVERRIDE d'`ApplyModification` -- la magnitude se lit SUR LE PORTEUR :

            PercentageOf( StatAmount(Owner, 0x10 FixedArmor, 3 Initial),
                          Direct(GetNumberConstant(0x4a = extraArmorPct)), roundingRule = 0 )

        `IdunBattle.Entities.Formulas.PercentageOf$$CalculateInternal` (Fix64) :
        `p = Round(pct/100 x 100, 0) / 100 ; r = Round(amount x p x 100, 0) / 100 ;
        return RoundFix64Result(r, roundingRule)` -- `roundingRule = 0` = `Fix64.Round` demi-vers-le-
        PAIR (`engine/dsl/base.py::_round_fix64` mode 0). Modelise en `Fraction` EXACTE : les deux
        arrondis intermediaires sont exacts des que `pct` est entier (le cas ici, `extraArmorPct` est
        une CONSTANTE gameconfig), il ne reste que l'arrondi final.

        `stats_ctx` absent ou constante illisible -> `[]` : la magnitude contextuelle n'est PAS
        devinee (degradation fidele, cf. `effect_stat_modifications`)."""
        from fractions import Fraction

        from ....dsl.base import _round_fix64
        from ...stats import StatPart, StatType
        from ..magnitude import ability_var
        if stats_ctx is None:
            return []
        pct = ability_var(REINFORCED_HIVE_NODE, "extraArmorPct", is_constant=True)
        if not pct:
            return []
        # `StatAmount(Owner, 0x10, 3 = Initial)` -> `UnitExtensions.GetStat(owner, FixedArmor, Initial)`
        base = int(stats_ctx.get_stat(int(StatType.FIXED_ARMOR), int(StatPart.INITIAL)) or 0)
        if base <= 0:
            return []
        amt = _round_fix64(Fraction(base * int(pct), 100), 0)
        return [(int(StatType.FIXED_ARMOR), int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        """`AStatModifierEffect$$RevertModification` -- meme stat que l'apply (part 6)."""
        from ...stats import StatType
        return [StatType.FIXED_ARMOR]
