"""`SummaryExecution` (passif d'`astraYarrick` << Yarrick >>, `TriggeredAbilityType` 1033) -- #955.

i2 : « Friendly units with Battle Fatigue gain +291 Damage. The first time a friendly unit would flee
due to Battle Fatigue, it is executed instead and all other friendly units with the trait ignore it
and gain an additional +146 Damage. »

Les DEUX effets de ce kit sont des `IdunBattle.Entities.Effects.ADynamicStatModifierEffect` PROJETES
(`base` lue dans `frida/classes.tsv`, pas dans le nom du `.ctor`) : ils vivent sur YARRICK et ecrivent
une `ValueModification` du stat **Attack** sur CHAQUE unite de leur `CreateTargetSelector`. Ils
relevent donc du driver `runner/operations/aura_stat_mods.py` (interface `aura_stat_modification_*`),
comme `PathOfCommandExtraCritEffect` -- surtout pas des canaux de DEGAT (`create_effect_damage_*`),
qui sont un autre etage.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- recensement par le bloc `methodPointers`
================================================================================================
| classe | slots | corps PROPRES |
|---|---|---|
| `IdunBattle.Entities.Effects.Loki.SummaryExecutionEffect` | 4 | **3** |
| `IdunBattle.Entities.Effects.Loki.SummaryExecution_AlwaysEffectEffect` | 3 | **3** |

⚠ **LA FACE CACHEE EST LE SELECTEUR DE 1031.** `SummaryExecutionEffect` n'a **pas** de
`CreateTargetSelector` propre : son slot pointe sur le corps de son voisin
(`SummaryExecution_AlwaysEffectEffect$$CreateTargetSelector` @ le meme pointeur, fondu par l'ICF).
Les DEUX effets ont donc **le meme sélecteur d'aura** -- le lire << Owner >> (le piege mesure de
#952) ou l'omettre aurait rendu 1031 inerte.

## Le selecteur PARTAGE

    Friends( Owner@<DSLSelectors+0x30>,
             UnitsWithTrait( AllAliveUnits@<DSLSelectors+0x20>,
                             0x3f7 = UnitTrait.BattleFatigue,
                             3 = UnitSelectionType.OnlyAliveAndTargetable ),
             3 )

`IdunBattleLogic.Entities.DSLSelectors$$Friends(of, entities, selectionType)` alloue un
`UnitsFromFactionSelector(state, of, entities, sameTeam = 1, selectionType)` : **rien n'y ecarte
`of` lui-meme**. Le porteur est donc INCLUS s'il porte le trait -- ce n'est pas le cas de Yarrick
(`Hero`, `Resilient`), mais le port ne pose aucune exclusion que le natif n'a pas (leçon #952).

## Les deux magnitudes

    SummaryExecution_AlwaysEffectEffect$$GetDynamicStatModificationAmount
        ConfigVar( 0x409 = TriggeredAbilityType.SummaryExecution,
                   EffectSource( Get(effect) ),
                   8 = AbilityVariableType.extraDmg )          # +291 @L65
    SummaryExecutionEffect$$GetDynamicStatModificationAmount
        ConfigVar( SummaryExecution, EffectSource(Get(effect)),
                   9 = AbilityVariableType.extraDmg_2 )        # +146 @L65

Surcharge tranchee par l'ADRESSE REELLE de la cible du `call` : `DSLFormulas$$ConfigVar` en a
**cinq**, et les deux corps visent celle a `(abilityType, unit, variableType)`. Le PREMIER argument
est donc un `TriggeredAbilityType`, pas un `AbilityVariableType` -- le lire comme dans #952
(`ConfigVar(8 = extraDmg, ...)`) aurait interverti les deux et indexe une variable inexistante.
`EffectSource(Get(effect))` = l'unite SOURCE de l'effet (Yarrick) : la magnitude s'indexe sur SON
`AbilityState`, jamais sur celui du buffe -- d'ou `self.ability_level` (meme regime que
`PathOfCommandExtraCritEffect` / `LordOfTheHost`).

Les deux variables sont dans `variablesAffectedByRarityBonus` -> `ability_var` applique le
multiplier ; on le lui passe et c'est LUI qui decide (regle config-driven).

## Le `statType` ne vient PAS de l'effet, mais du BEHAVIOUR qui le pose

`IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` lit un CHAMP de
l'entite-effet ; aucun des deux effets ne l'override. Le litteral est donc celui des deux
`IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffectToOwner(effectType, statType,
turns, isHidden)` :

    SummaryExecutionAddBaseEffectAbility$$CreateBehaviour : (0x413 = 1043, statType = 0, null, false)
    SummaryExecutionAbility$$CreateBehaviour              : (0x407 = 1031, statType = 0, null, false)

soit **`StatType.Attack` (0)** pour les deux, `turns = null` = PERMANENT, `isHidden = false`.

## Le sous-effet de 1031

`SummaryExecutionEffect$$ApplyInternal` = `AStatModifierEffect.ApplyInternal(owner, target, effect)`
puis `BaseEffect$$AddSubEffect(effect, target, 0x437 = EffectType.IgnoreBattleFatigue, turns = null)`
-- surcharge SANS `EffectBuilder`, tranchee a l'adresse du `call`. `target` y est la CIBLE
SELECTIONNEE, pas le porteur : c'est le « all other friendly units with the trait **ignore it** »
de l'i2. Le port le pose depuis le behaviour du trigger (cf. `runner/operations/triggers/loki/
summary_execution.py`), parce que le driver d'aura du port n'a pas d'etage `ApplyInternal`
par-cible -- residu #955-r3.
"""
from __future__ import annotations

from ...effect_type import EffectType
from ...traits.unit_trait import UnitTrait
from ...triggered_ability_type import TriggeredAbilityType
from ...unit_selection_type import UnitSelectionType
from ...selectors.accessors import Owner
from ...selectors.tiles import AllAliveUnits
from ...selectors.units import Friends, UnitsWithTrait
from ...stats import StatType
from ..base import BaseEffect, SubEffectSpec
from ..magnitude import ability_var

#: L'ability dont les DEUX effets lisent la config (`ConfigVar(0x409, EffectSource, <var>)`).
SUMMARY_EXECUTION = TriggeredAbilityType.SummaryExecution.name        # 0x409 = 1033
#: `AddDynamicStatModifierEffectToOwner(<type>, statType = 0, null, false)` -- LU aux deux behaviours.
_STAT_ATTACK = int(StatType.ATTACK)                                   # 0
#: 3e argument des DEUX noeuds du selecteur partage.
_SEL_ALIVE_TARGETABLE = UnitSelectionType.OnlyAliveAndTargetable      # 3
#: Le sous-effet que `SummaryExecutionEffect$$ApplyInternal` pose sur chaque cible.
IGNORE_BATTLE_FATIGUE = int(EffectType.IgnoreBattleFatigue)          # 0x437 = 1079


def summary_execution_target_selector() -> Friends:
    """Le `CreateTargetSelector` PARTAGE par 1043 et 1031 (un seul corps, fondu par l'ICF) :

        Friends( Owner@+0x30,
                 UnitsWithTrait( AllAliveUnits@+0x20, BattleFatigue, OnlyAliveAndTargetable ),
                 OnlyAliveAndTargetable )

    Le porteur n'est PAS exclu (cf. l'en-tete) ; l'arbre est monte une fois et partage par les deux
    classes, exactement comme le natif partage le corps."""
    return Friends(UnitsWithTrait(AllAliveUnits(), UnitTrait.BattleFatigue,
                                  selection_type=_SEL_ALIVE_TARGETABLE),
                   reference=Owner(), selection_type=_SEL_ALIVE_TARGETABLE)


class _ASummaryExecutionAuraEffect(BaseEffect):
    """Tronc commun des DEUX `ADynamicStatModifierEffect` du kit : meme selecteur (un seul corps
    natif), meme `StatType`, meme unite d'indexation (`EffectSource` = Yarrick) -- seule la VARIABLE
    de config change. Cette base n'est PAS inscrite au registre : elle n'a pas d'homologue natif."""

    _VAR = ""                      # `AbilityVariableType` du `ConfigVar` (8 = extraDmg | 9 = extraDmg_2)

    def aura_stat_modification_stat(self) -> int:
        """Le `statType` litteral du `AddDynamicStatModifierEffectToOwner` qui pose CET effet."""
        return _STAT_ATTACK

    def aura_stat_modification_amount(self) -> "int | None":
        """`ConfigVar(SummaryExecution, EffectSource(Get(effect)), <var>)` -- indexe sur
        l'`AbilityState` de la SOURCE. Niveau inconnu -> None (aucune magnitude devinee)."""
        if self.ability_level is None:
            return None
        return ability_var(SUMMARY_EXECUTION, self._VAR, self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)

    def aura_stat_modification_targets(self, state, owner_id: int) -> list:
        """Le selecteur partage, evalue contre l'etat courant. L'import est DIFFERE et il est
        PORTEUR : `runner.abilities.behaviours.context` tire `runner.state`, qui re-entre dans
        `entities.*` -- meme classement et meme forme que `loki/prophetic_sentinel.py`."""
        from ....runner.abilities.behaviours.context import entities_from_state
        entities = entities_from_state(state, int(owner_id))
        out: list = []
        for u in (summary_execution_target_selector().evaluate(entities) or []):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is not None:
                out.append(int(uid))
        return out


class SummaryExecutionBaseEffect(_ASummaryExecutionAuraEffect):
    """`SummaryExecution_AlwaysEffectEffect` (EffectType 0x413 = 1043 `SummaryExecution_BaseEffect`)
    -- l'aura PERMANENTE : `+extraDmg` au stat **Attack** de tous les allies de Yarrick porteurs du
    trait `BattleFatigue`. Posee au chargement par `SummaryExecutionAddBaseEffectAbility`, dont le
    `CreateTrigger` est le corps ICF partage `<DSLTriggers+0x30>` = `On(0x21 = AbilityInit) &
    <YesTrigger> & get_OwnerIsActor` -- d'ou l'inscription a `ABILITY_INIT_OWNER_EFFECTS` et NON a
    `ABILITY_TRIGGERS` (meme arbitrage que `HuntersBeyondDeath` #952 et `EnmityForTheUnworthy` #948 ;
    s'y tromper donne un passif qui ne se pose JAMAIS)."""

    _VAR = "extraDmg"              # `AbilityVariableType` 8


class SummaryExecutionEffect(_ASummaryExecutionAuraEffect):
    """`SummaryExecutionEffect` (EffectType 0x407 = 1031 `SummaryExecution_Effect`) -- l'aura
    ADDITIONNELLE, posee sur Yarrick par `SummaryExecutionAbility$$CreateBehaviour` la PREMIERE fois
    qu'un allie allait fuir sur Battle Fatigue (le gate `NOT HasEffect(Owner, 1031, false, 6)` du
    trigger fait de sa PRESENCE le verrou one-shot). Elle ajoute `+extraDmg_2` au stat **Attack** des
    MEMES cibles (selecteur partage), et son `ApplyInternal` pose `IgnoreBattleFatigue` (1079) sur
    chacune."""

    _VAR = "extraDmg_2"            # `AbilityVariableType` 9

    def aura_sub_effects_on_apply(self) -> tuple:
        """`IdunBattle.Entities.Effects.Loki.SummaryExecutionEffect$$ApplyInternal`, MIRROR du
        decompile -- corps ENTIER, deux instructions :

            AStatModifierEffect.ApplyInternal(this, owner, target, effect)
            BaseEffect.AddSubEffect(this, effect, target, 0x437 = IgnoreBattleFatigue, turns = null)

        Le `target` est la CIBLE SELECTIONNEE (3e argument du slot 0x548, que
        `RefreshEffectsOperation$$ApplyEffectsForTargets` alimente une cible a la fois), donc le
        natif pose l'immunite sur CHACUNE -- et la RE-pose des qu'une nouvelle entre dans le
        selecteur. C'est ce que le driver d'aura joue desormais (#955-r3) ; jusque-la le port ne la
        posait qu'UNE FOIS, depuis le behaviour du trigger, au moment de la materialisation de 1031.

        `turns = null` -> `SubEffectSpec.turns = None` = `DefaultAmountOfRounds`, mirror du
        `Nullable<int>` VIDE.

        ⚠ PAS de pendant au RETRAIT, et c'est LU : le bloc de `SummaryExecutionEffect` porte `.ctor`,
        `ApplyInternal` et `GetDynamicStatModificationAmount` -- aucun `RevertInternal`. Une cible
        qui sort du selecteur GARDE donc son immunite cote natif ; elle ne part qu'avec le parent,
        par `IdunBattle.Operations.RemoveEffectOperation$$RemoveSubEffects`."""
        return (SubEffectSpec(IGNORE_BATTLE_FATIGUE, EffectType.IgnoreBattleFatigue.name,
                              turns=None),)
