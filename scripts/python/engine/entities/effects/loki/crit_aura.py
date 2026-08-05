"""Effets `Effects.Triggered.Loki` — famille AURA a stat-mod **CRIT** : l'effet-entite vit sur le
PORTEUR et ECRIT une `ValueModification` de CRIT sur chaque unite de son `CreateTargetSelector`.

Meme famille structurelle que `loki/dark_angels_passives.py` (LionHelm, axes BLOCK) et que
`loki/extra_damage_aura.py` (axe ATTACK) -- ce qui change est le `StatType` ecrit chez la cible.
L'interface consommee est celle de `runner/operations/aura_stat_mods.py` :
`aura_stat_modification_stat` / `_amount` / `_targets`.

## Pourquoi un canal STAT et pas un canal `create_aura_*` de lecture

Sur l'axe ATTACK, le port a un canal de LECTURE (`create_aura_attack_bonus`) parce que la chaine
de PREDICTION re-positionne l'attaquant sur une tuile CANDIDATE et doit donc recalculer la base
par tuile (#153). L'axe CRIT n'a pas cet usage : la seule lecture numerique du port est
`GetStat(9)` dans `_crit_params` (`runner/operations/damage.py`), evaluee a la position REELLE.
Un canal de lecture y serait un gate MORT ; le canal FIDELE est celui que le natif emprunte --
la `ValueModification` sur la cible, posee/retiree par `RefreshEffectsOperation`.

GROUND TRUTH LIVE de la pose (runner MC1_67, seed 31337, `eldarAutarch` ablvl 50, event stream de
l'atterrissage deep-strike) :

    [Effect_Refresh e=101 <<PathOfCommand_ExtraCrit>>]
      ActivateEffect e=83                                       # l'effet vit sur l'AUTARCH
      ReceiveEffect  e=85  Effect_SourceId=83  Effect_SourceTriggeredAbility=1112
      ChangeStats    e=85  UnitStats_CritChance_Modification_Change=20
                           UnitStats_CritChance_Modification_Entity=101

    -> u85 `eldarRanger` (CritChance de base 20) recoit +20 ;
    -> u87 `eldarFarseer` (CritChance de base 0), pourtant a portee (il recoit bien le +699 Attack
       de `PathOfCommand_ExtraDmg` 1112 au MEME instant), ne recoit RIEN : le noeud
       `UnitsWithStatBiggerThan(CRIT_CHANCE > 0)` du selecteur MORD.
"""
from __future__ import annotations

from ..aura_selectors import surrounding_friends
from ..base import BaseEffect
from ..magnitude import ability_var
from ....entities.effect_type import EffectType   # #270-r1-r1-r3
from ....entities.stats import StatType   # #270-r1-r1-r3
from ...stats import StatPart

_PATH_OF_COMMAND = "PathOfCommand"    # TriggeredAbilityType 0x458 = 1112 (eldarAutarch « Aethana »)

# Qualification des enums (le meme id nomme autre chose ailleurs) :
#   EffectType 1107 PathOfCommand_ExtraCrit != TriggeredAbilityType 1107 RighteousRepugnance
#   EffectType 1112 PathOfCommand_ExtraDmg  == TriggeredAbilityType 1112 PathOfCommand (collision
#     de VALEUR entre deux enums DISTINCTS : c'est bien 1112 que le `ConfigVar` ci-dessous passe en
#     `abilityType`, et 1112 que `AddDynamicStatModifierEffectToOwner` passe en `effectType` pour
#     l'AUTRE effet du meme behaviour -- ne pas confondre les deux roles).
EFFECT_PATH_OF_COMMAND_EXTRA_CRIT = EffectType.PathOfCommand_ExtraCrit   # 0x453
EFFECT_PATH_OF_COMMAND_EXTRA_DMG = EffectType.PathOfCommand_ExtraDmg    # 0x458

_STAT_CRIT_CHANCE = StatType.CRIT_CHANCE                      # `IdunBattle.Entities.Enum.StatType` 9 = CritChance


def _path_of_command_range() -> int:
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(cfg, 0x16 = range)` =
    `PathOfCommand.constants.range` (= 2). MEME lecture que le jumeau ATTACK
    (`loki/extra_damage_aura.py::PathOfCommandExtraDmgEffect`)."""
    r = ability_var(_PATH_OF_COMMAND, "range", is_constant=True)
    return int(r) if r else 2


class PathOfCommandExtraCritEffect(BaseEffect):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandExtraCritEffect`
    (EffectType 0x453 = 1107) -- volet CRIT de l'aura de `eldarAutarch`.

    POSE. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandAbility$$CreateBehaviour`
    pose DEUX `ADynamicStatModifierEffect` sur le porteur, via
    `IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffectToOwner(effectType, statType,
    turns, isHidden)` :

        AddDynamicStatModifierEffectToOwner( 0x453 = 1107, statType = 0x9 = CritChance, null, false )
      & AddDynamicStatModifierEffectToOwner( 0x458 = 1112, statType = 0x0 = Attack,     null, false )

    -> le `StatType` ecrit chez la cible est lu VERBATIM du behaviour : **CritChance (9)**, et RIEN
    d'autre. Pas de `CritDamage` (10) : l'axe DEGAT-de-crit n'est PAS porte par cette ability.

    SELECTEUR.
    `...PathOfCommandExtraCritEffect$$CreateTargetSelector` =

        UnitsWithStatBiggerThan(
            entities        = SurroundingFriends( Owner@0x148,
                                                  GetNumberConstant(0x16 = range),
                                                  unique = true,
                                                  unitSelectionType = 3 = OnlyAliveAndTargetable ),
            statType        = 0x9 = CritChance,
            statPart        = 0x0 = Current,
            amount          = <DSLFormulas+0x18> = Constant(0),
            excludingEffect = true )

    Le second noeud est le DISCRIMINANT de cet effet (le jumeau ATTACK ne l'a pas) :
    `IdunBattle.Entities.Selectors.UnitsWithStatBiggerThanSelector$$Select` calcule, pour chaque
    unite retenue par `SurroundingFriends`,

        v = GetStat(unit, CritChance, Current)
        si excludingEffect : v -= GetStat(unit, CritChance, part 5 = Modification, source = CET effet)
        garde l'unite si   threshold < v      (threshold = Calculate(Constant(0)) = 0)

    c.-a-d. **strictement > 0**, la propre contribution de l'effet DEFALQUEE (sans quoi le gate
    s'auto-entretiendrait). Un allie a portee dont la chance de crit est nulle n'est donc PAS cible
    -- mesure live en tete de module (`eldarFarseer` a 0 : rien, alors qu'il prend bien le +699
    Attack du jumeau 1112 au meme instant).

    MAGNITUDE.
    `...PathOfCommandExtraCritEffect$$GetDynamicStatModificationAmount` =
    `ConfigVar( abilityType = TriggeredAbilityType.PathOfCommand = 0x458,
                unit        = EffectSource(Get(effect)),
                variableType = AbilityVariableType.extraCritChance = 0x41 )`
    (surcharge `IdunBattleLogic.Entities.DSLFormulas$$ConfigVar(this, abilityType, unit,
    variableType)` -> `IdunBattle.Entities.Formulas.ConfigAmount$$.ctor`, dont le `Calculate` finit
    sur `AbilityConfiguration$$GetVariableForLevel(variableType, abilityState)`). La magnitude
    s'indexe donc sur l'`AbilityState` de la **SOURCE** (l'Autarch), jamais sur celui du buffe --
    c'est pourquoi cet effet est modelise cote SOURCE, comme LionHelm.
    Aucun gate de faction / grande-alliance ici : le `If(IsSameFaction(...))` est propre au jumeau
    ATTACK (`extraDmg` + `extraDmg_2`), il n'existe pas dans ce corps.
    `extraCritChance` n'est **PAS** dans `variablesAffectedByRarityBonus` de `PathOfCommand`
    (seuls `extraDmg`/`extraDmg_2` y sont) -> aucun scaling de rarete ; `ability_var` le gate deja
    sur cette liste, on lui passe le multiplier pour que la regle reste config-driven.
    Mesure live : `extraCritChance[L50]` = 20, modification observee = +20 (mult 180 sans effet).

    CONDITION ACTIVE.
    `...PathOfCommandEffect$$CreateActiveCondition` = `IsTargetable(Owner@0x148)` -- porte par la
    base commune aux DEUX effets ; le port le laisse au regime commun (`BaseEffect.is_active`), qui
    est le MEME residu que pour le jumeau 1112 deja livre.
    """

    def aura_stat_modification_stat(self) -> int:
        return _STAT_CRIT_CHANCE                       # statType litteral du `CreateBehaviour`

    def aura_stat_modification_amount(self) -> "int | None":
        if self.ability_level is None:
            return None                                # niveau SOURCE inconnu -> aucune magnitude devinee
        return ability_var(_PATH_OF_COMMAND, "extraCritChance", self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)

    def aura_stat_modification_targets(self, state, owner_id: int) -> list:
        """`UnitsWithStatBiggerThan( SurroundingFriends(...), CritChance, Current, 0, excluding )`.

        La cle de source utilisee pour la defalque `excludingEffect` est CELLE DU DRIVER
        (`runner/operations/aura_stat_mods.aura_stat_mod_key`) : c'est sous cette cle exacte que la
        contribution de CET effet est ecrite chez la cible, donc c'est elle que le natif retire
        (le natif passe l'ENTITE-EFFET, dont la cle est l'homologue offline)."""
        from ....runner.components import StatsComponent
        from ....runner.operations.aura_stat_mods import aura_stat_mod_key
        key = aura_stat_mod_key(owner_id, self)
        out: list = []
        for uid in surrounding_friends(state, owner_id, _path_of_command_range()):
            ent = state.get_entity(uid)
            sc = ent.get_component(StatsComponent) if ent is not None else None
            us = getattr(sc.ctx, "stats", None) if (sc is not None and sc.ctx is not None) else None
            if us is None:
                continue
            cur = int(us.get_stat(_STAT_CRIT_CHANCE, int(StatPart.CURRENT)))
            own = int(us.get_stat(_STAT_CRIT_CHANCE, int(StatPart.MODIFICATION), key))
            if cur - own > 0:                          # `threshold < v`, threshold = Constant(0)
                out.append(uid)
        return out
