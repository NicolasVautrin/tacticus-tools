"""`ReinforcedHiveNode` (passif du SUMMON `tyranSmnWarrior` << Tyranid Warrior >>, invoque par
`tyranWingedPrime` via l'active `AlphaWarrior` (1112) -- TriggeredAbilityType 0x459 = 1113) --
volet **ARMURE** (`1108 ReinforcedHiveNode_ExtraArmor`, 0x454) ET volet **BLOCAGE**
(`1109 ReinforcedHiveNode_ExtraBlock`, 0x455).

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

## Les DEUX classes sont DISTINCTES (et sont TOUTES DEUX portees ici)

`classes.tsv` : `ReinforcedHiveNode_ExtraArmorEffect` derive de
`IdunBattle.Entities.Effects.StaticStatModifierEffect`, `ReinforcedHiveNode_ExtraBlockEffect` de
`IdunBattle.Entities.Effects.StatOverrideEffect` -- DEUX slots `Il2CppClass*`, DEUX `.ctor`
distincts, DEUX entrees dans `EffectsDatabase.<>c$$<InitializeEffects>b__14_135` / `..._136`. Ce
n'est PAS une classe unique parametree : DEUX classes portees, et le volet BLOCAGE passe par un
canal DIFFERENT (override part 7, cf. ci-dessous).

## `.ctor`s (octets relus)

`IdunBattle.Entities.Effects.Loki.ReinforcedHiveNode_ExtraArmorEffect$$.ctor` :
`StaticStatModifierEffect..ctor(this, sourceAbility = Nullable<AbilityOrEffect>(op_Implicit(0x459 =
TriggeredAbilityType.ReinforcedHiveNode)), unitEffectType = 0, canBeImmuneTo = 0, keepOnRevive = 1,
isMultiply = 0)`. `canBeImmuneTo = 0` -> le defaut `BaseEffect.can_be_immune_to = False` est exact.

`IdunBattle.Entities.Effects.Loki.ReinforcedHiveNode_ExtraBlockEffect$$.ctor` = trois `mov` et un
`jmp` : `xor r9d,r9d ; xor r8d,r8d ; mov edx,0x459 ; jmp <StatOverrideEffect..ctor>` ->
`StatOverrideEffect..ctor(this, sourceAbility = 0x459, isModifiable = 0)`. Cette surcharge de
`IdunBattle.Entities.Effects.StatOverrideEffect$$.ctor` fait litteralement
`movzx edi, r8b ; ... ; mov [rbx+0x480], dil` -> **`isModifiable = FALSE`** est le champ `+0x480`
que `ApplyInternal` repasse a `ChangeStat`. Consequence LUE, pas deduite
(`IdunBattle.Entities.Components.ValueOverride$$GetOverrideValueWithModification` =
`override + (isModifiable ? modTotal : 0)`) : tant que 1109 est ACTIF, `BlockChance` vaut EXACTEMENT
100 -- aucune modification par-source ne s'y ajoute.

## Le volet BLOCAGE est un OVERRIDE, pas un additif -- et c'est le MEME driver qui le pilote

`IdunBattle.Entities.Effects.StatOverrideEffect$$ApplyInternal` (relu) :

    comp = <effectEntity>.GetComponent<StatOverrideComponent>()   # +0x10 statType, +0x14 amount,
                                                                  # +0x18 isHidden
    ChangeStat( Entity(target), Position(comp+0x10, part 7 = OVERRIDE), mode 4,
                Direct(comp+0x14), Entity(effect), 3, <this+0x480 = isModifiable>, comp+0x18 )

et `...$$RevertInternal` rejoue le MEME appel avec `Position(comp+0x10, part 8 = REMOVE_OVERRIDE)`.
`comp+0x14` est ecrit a la POSE par `IdunBattle.Entities.Behaviours.
AddStatOverrideEffectBehaviour$$StatOverrideBuilder(id, statType, amount, isHidden)` -- `amount` =
le noeud `Direct(GetNumberConstant(0x2d = blockChance))` DEJA EVALUE.

⚠ Ce qui rend le port possible SANS canal special : `IdunBattle.Operations.RefreshEffectsOperation`
ne connait PAS la famille de l'effet. `...$$ApplyEffectsForTargets` appelle le slot d'interface
`IEffect+0xe` (= `IdunBattle.Entities.Effects.BaseEffect$$Apply`, qui delegue au virtuel
`<Effect>.ApplyInternal` via `*(vtable+0x548)`) et `...$$RevertEffectsForTargets` le slot `+0xf`
(= `...$$Revert` -> `*(vtable+0x578)` = `RevertInternal`). Le couple
`ActivateEffect`/`DeactivateEffect` pilote donc l'override EXACTEMENT comme il pilote l'additif, sous
le MEME verdict `ShouldBeActive` -- d'ou l'elargissement de `refresh_stat_modifier_effects` aux parts
7/8 (canal `applied_stat_overrides` / `effect_stat_overrides`), et pas un chemin parallele.

================================================================================================
FORME DU PORT
================================================================================================
### 1109 -- canal OVERRIDE

`applied_stat_overrides()` rend `[(7 BlockChance, blockChance = 100, isModifiable = False)]`. Le
triplet est ENTIEREMENT declaratif (aucune dependance au `UnitContext`) parce que ses trois membres
sont des donnees natives : `statType` et `amount` viennent du `StatOverrideComponent` de
l'entite-effet, `isModifiable` du DEF (`+0x480`). Consommateurs, tous deux nouveaux ici :
`entities/stats.py::seed_unit_stats(overrides=...)` (le SEED pose l'override, au lieu de verser le
delta capte dans le residu opaque `CAPTURED_SOURCE` -- une modification FANTOME qui reapparaitrait
au `RemoveOverride`) et `runner/operations/refresh_effects.py` (le DRIVER, parts 7/8).

⚠ La valeur est RE-DERIVEE de gameconfig : le `StatOverrideComponent` n'est PAS publie par la
capture (`frida/hooks/game/effects.ts` ne lit que le `StatModifierComponent`, canal `statMod`). Le
regime est donc celui de toute magnitude sans canal a la source -- exact ici (une CONSTANTE
gameconfig, ni indexee par niveau ni scalee par la rarete), et le test live l'asserte contre la
valeur natif.

### 1108 -- canal stat-mod ADDITIF

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
SEEDEE (`stat_mod_source is None`, le seul regime de ces DEUX effets -- aucun vecteur de pose
OFFLINE ne les materialise, `ReinforcedHiveNodeAbility` n'etant pas portee) reste donc bien pilotee
par le driver.
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


class ReinforcedHiveNodeExtraBlockEffect(BaseEffect):
    """`ReinforcedHiveNode_ExtraBlock` (EffectType 0x455 = 1109) --
    `IdunBattle.Entities.Effects.StatOverrideEffect` PERMANENT pose sur le porteur par
    `ReinforcedHiveNodeAbility$$CreateBehaviour`
    (`AddStatOverrideEffectToOwner(1109, statType = 7 BlockChance,
    Direct(GetNumberConstant(0x2d = blockChance)), turns = null)`), ACTIF un round sur deux
    (`turnsStarted` du porteur PAIR) -- MEME corps de `CreateActiveCondition` que 1108, cf. en-tete.

    JUMEAU de `ReinforcedHiveNodeExtraArmorEffect`, mais canal NATIF DIFFERENT : un OVERRIDE
    (part 7 `SetOverride`), pas une modification additive (part 5|9). `BlockChance` est donc FORCEE
    a 100 -- elle ne s'ajoute pas a la valeur de base du porteur, et `isModifiable = 0` interdit
    meme aux modifications par-source de s'y ajouter."""

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """MIRROR du corps natif FONDU `CreateActiveCondition` -- STRICTEMENT le meme que 1108 :
        `IdunBattle.Entities.Effects.Loki.ReinforcedHiveNode_ExtraBlockEffect$$CreateActiveCondition`
        est litteralement
        `return ReinforcedHiveNodeAbility.GetEffectActiveCondition(<this+0x48>)` (le corps que les
        deux tables de symboles, dedupliquees par ADRESSE, attribuent a CETTE classe -- c'est celui
        de 1108 qui n'y apparait pas, cf. l'en-tete du module), et le corps appele est
        `AmountIsOdd(Sum(RoundsStarted(Owner), <DSLFormulas+0x20 = Direct(1)>))`.

        Donc actif ssi `turnsStarted(porteur)` est PAIR. Cle ABSENTE -> True (<< present == actif >>,
        meme degradation que 1108)."""
        if unit_state is None or "turns_started" not in unit_state:
            return True
        return ((int(unit_state.get("turns_started") or 0) + 1) & 1) == 1

    def applied_stat_overrides(self) -> "list":
        """`IdunBattle.Entities.Effects.StatOverrideEffect$$ApplyInternal` :

            ChangeStat( Entity(target), Position(<comp+0x10> = 7 BlockChance, part 7 = OVERRIDE),
                        mode 4, Direct(<comp+0x14>), Entity(effect), 3,
                        <this+0x480 = isModifiable>, <comp+0x18 = isHidden> )

        * `statType = 7 BlockChance` : le 3e argument litteral d'`AddStatOverrideEffectToOwner`
          dans `ReinforcedHiveNodeAbility$$CreateBehaviour` (que `StatOverrideBuilder` recopie
          dans `StatOverrideComponent+0x10`).
        * `valeur = blockChance` : le noeud `Direct(GetNumberConstant(0x2d))` de la meme feuille,
          EVALUE a la pose et range dans `StatOverrideComponent+0x14`. CONSTANTE gameconfig -- ni
          indexee par niveau, ni listee dans `variablesAffectedByRarityBonus` (la table est absente
          de `gameconfig.ability('ReinforcedHiveNode')`) -> aucun scaling.
        * `isModifiable = False` : `ReinforcedHiveNode_ExtraBlockEffect$$.ctor` passe `r8 = 0` a
          `StatOverrideEffect..ctor`, qui l'ecrit en `+0x480`. `IdunBattle.Entities.Components.
          ValueOverride$$GetOverrideValueWithModification` rend alors `override` SEUL.

        Constante illisible -> `[]` (rien n'est devine ; l'effet est alors INERTE, jamais approche
        par une valeur inventee)."""
        from ...stats import StatType
        from ..magnitude import ability_var
        val = ability_var(REINFORCED_HIVE_NODE, "blockChance", is_constant=True)
        if val is None:
            return []
        return [(int(StatType.BLOCK_CHANCE), int(val), False)]
