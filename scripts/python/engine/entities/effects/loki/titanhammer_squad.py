"""`TitanhammerSquad_ExtraBlockDamage` (`EffectType` 0x624 = 1572) -- le stat-mod BLOCK DAMAGE du
3e volet de l'active `TitanhammerSquad` (`ActiveAbilityType` 0x4cf = 1231) de `astarLysander`
<< Lysander >> (Adeptus Astartes / Imperial Fists, HERO).

Le VECTEUR de pose vit ailleurs (cite pour le contexte) :
`IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$ExecuteBehaviour` volet 3 =
`AddDynamicStatModifierEffect(targets = Filter(<groupe>, AmountIsGreaterThanZero(StatAmount(
ActiveTarget, 7 = BlockChance, 0 = Current, null, 0 = Any))), source = Caster@<Sel+0x48>,
effectType = 0x624, statType = 8 = BlockDamage, abilityStateSelector = AbilityStateReference,
turns = Sum(TurnsUntilUnitOwnerTurn(ActiveTarget), TurnsFromRounds(1)), isHidden = 0)` -- cf.
`engine/runner/abilities/astartes.py`.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- OU LA MAGNITUDE EST LUE
================================================================================================

Il n'existe AUCUNE classe d'effet native `TitanhammerSquad_ExtraBlockDamageEffect` : la recherche de
symboles `Titanhammer` du build ne rend, cote effets, que
`IdunBattle.Entities.Effects.Loki.TitanhammerSquad_TeleportingInEffect` (l'effet 0x625, une
`APsychicStalkEffect`). 1572 est donc une instance GENERIQUE, exactement comme
`MyWillBeDoneOverlord_ExtraDamage` (cf. le module voisin, meme mold) :

1. **L'instance** est construite par une lambda de la base d'effets :

       IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_565
         -> new IdunBattle.Entities.Effects.DynamicStatModifierEffect(
                abilityType   = AbilityType.op_Implicit(0x4cf = 1231 TitanhammerSquad),
                variableType  = 0x14 (`IdunBattle.Configuration.AbilityVariableType` 20 = blockDmg),
                isNegative    = 0,
                canBeImmuneTo = 0 )

   L'`AbilityType` est LU AU DESASSEMBLEUR (`mov edx, 0x4cf` a l'entree de la lambda), ghidra perdant
   l'immediat dans le decompile ; `variableType = 0x14` et `isNegative = 0`, eux, sont dans le
   decompile. `DynamicStatModifierEffect$$.ctor` range `variableType` en `this+0x4a0`, `isNegative`
   en `this+0x4a4` et l'`AbilityOrEffect` en `this+0x490`.

2. **Le consommateur de la magnitude** est le corps generique
   `IdunBattle.Entities.Effects.DynamicStatModifierEffect$$GetDynamicStatModificationAmount` :

       amount = ConfigVar( <this+0x490 = AbilityOrEffect(1231)>,
                           EffectSource(Get(effect)),
                           <this+0x4a0 = 20 blockDmg> ).Invoke(entities)
       return Nullable( this+0x4a4 /*isNegative*/ ? -amount : amount )

   -> le NIVEAU vient de l'`AbilityState` de la **SOURCE** de l'effet (`EffectSource`) = Lysander,
   et le signe est `+` (`isNegative = 0`).

3. **La STAT** ne vient PAS de l'effet mais de l'entite-effet :
   `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` lit le composant de
   l'effet (`+0x10`), rempli par le behaviour avec son argument `statType` -- ici `8 = BlockDamage`.
   Les deux sources coincident : la variable de config s'appelle `blockDmg`.

4. **La POSE / LE RETRAIT** : `AStatModifierEffect$$ApplyModification` emet
   `ChangeStat(Entity(target), Stat(8, part 5 = Modification), Modify, Direct(amount), Entity(effect))`
   et `…$$RevertModification` rejoue le MEME appel en `part = 6 ResetModification` -> couple EAGER
   `applied_stat_mods` / `reverted_stats`.

Magnitude (gameconfig `TitanhammerSquad`, RE-LU, jamais fitte) : `blockDmg` = tableau 65 niveaux
(10 @L1 ... 554 @L50 ... 728 @L65) et il est dans `variablesAffectedByRarityBonus`
(`["hpToHeal", "blockDmg"]`) -> le multiplier de rarete s'y applique. `ability_var` gate deja
l'application sur cette liste.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
from ...stats import StatType

#: `AbilityType.op_Implicit(0x4cf = 1231)` de la lambda -- l'ability dont la config est lue.
TITANHAMMER_SQUAD = "TitanhammerSquad"
#: `IdunBattle.Configuration.AbilityVariableType` 20 = `blockDmg` (argument `variableType`).
BLOCK_DMG_KEY = "blockDmg"


def _source_level_mult(effect: BaseEffect, stats_ctx) -> "tuple[int, int]":
    """(niveau d'ability, multiplier de rarete %) qui indexent le `ConfigVar` de l'effet.

    Mirror de `ConfigVar(AbilityOrEffect(1231), EffectSource(Get(effect)), 20)` : le natif resout la
    config contre l'`AbilityState` de la **SOURCE** de l'effet. 1231 etant un `ActiveAbilityType`,
    le niveau est l'`activeAbilityLevel` -- celui que
    `runner/abilities/behaviours/effects.py::_source_scaling` seede a la pose. Repli sur le
    `stats_ctx` du PORTEUR : la source (Lysander) et le porteur different des que l'effet est pose
    sur un Terminator allie, donc ce repli est une APPROXIMATION nommee, jamais le chemin nominal
    (`AddDynamicStatModifierEffect` propage bien le scaling de la source, cf. `_source_scaling`).
    Niveau introuvable -> 0 (premiere entree de la courbe), jamais un niveau invente."""
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


class TitanhammerSquadExtraBlockDamageEffect(BaseEffect):
    """`TitanhammerSquad_ExtraBlockDamage` (0x624 = 1572) -- stat-mod **BlockDamage(8) POSITIF** pose
    par Lysander sur chaque membre du groupe (lui-meme + les allies `TerminatorArmour` a portee)
    dont la `BlockChance` COURANTE est > 0, pour `Sum(TurnsUntilUnitOwnerTurn(cible),
    TurnsFromRounds(1))` tours.

    Magnitude = `blockDmg[activeAbilityLevel de la source] x multiplier de rarete` -- le `ConfigVar`
    du corps generique `DynamicStatModifierEffect$$GetDynamicStatModificationAmount` (cf. l'en-tete
    du module) ; le signe est `+` parce que la lambda d'enregistrement passe `isNegative = 0`."""
    stat_mod_source = None   # cle de source ChangeStat (revert par-source via `RemoveEffect`)

    def applied_stat_mods(self, stats_ctx) -> "list":
        """DATA du `ChangeStat` (`StatPart` 5 = Modification) emis par
        `AStatModifierEffect$$ApplyModification` : BlockDamage += `blockDmg[level source] x mult`.
        Execute par `AddEffectOperation._apply_stat_mods`. Montant nul/absent -> aucun stat-mod
        (degradation fidele << present != applique >>)."""
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(TITANHAMMER_SQUAD, BLOCK_DMG_KEY, lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.BLOCK_DAMAGE), int(amt))]   # isNegative = 0 -> +amount

    def reverted_stats(self) -> "list":
        """Stats annulees par `AStatModifierEffect$$RevertModification`
        (`Stat(8 = BlockDamage, 6 = ResetModification)`), lu par la feuille `RemoveEffect` et par
        l'expiration du timer (`revert_stat_mods_of_removed_effects`)."""
        return [StatType.BLOCK_DAMAGE]
