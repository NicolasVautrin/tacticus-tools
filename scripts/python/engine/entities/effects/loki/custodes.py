"""Effets de la faction ADEPTUS CUSTODES (case-231) — namespace natif `IdunBattle.Entities.Effects`
/ base de donnees `IdunBattle.Core.Services.EffectsDatabase`.

Les DEUX stat-mods de `MomentShackle` (1184, `custoTrajann` « Trajann ») n'ont **aucune classe
d'effet dediee** cote natif : ils sont instancies par des lambdas de
`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` sur la classe GENERIQUE
`IdunBattle.Entities.Effects.DynamicStatModifierEffect`, exactement comme le lot Votann (#113) :

    lambda(): new DynamicStatModifierEffect( AbilityType.op_Implicit(<abilityId>), <varKey>,
                                             <isNegative>, <flag> )

et leur magnitude sort du corps GENERIQUE
`IdunBattle.Entities.Effects.DynamicStatModifierEffect$$GetDynamicStatModificationAmount` :

    amount = ConfigVar( <abilityId>, EffectSource(Get(entities)), <varKey> ).Invoke(entities)
    return Nullable( this+0x4a4 /*isNegative*/ ? -amount : amount )

LAMBDAS LUES (build gqfc5mff6c ; localisees par les XREFS de
`IdunBattle.Entities.Effects.DynamicStatModifierEffect$$.ctor` — 12 lambdas seulement, donc
enumerables) :
  * `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_400`
    -> `DynamicStatModifierEffect(AbilityType(0x4a0 = 1184 MomentShackle), 0x15 = 21 blockChance,
        isNegative = 0, 0)`   ==> **MomentShackle_ExtraBlockChance (0x56f = 1391)**, BONUS.
  * `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_401`
    -> `DynamicStatModifierEffect(AbilityType(0x4a0 = 1184), 0x14 = 20 blockDmg,
        isNegative = 0, 0)`   ==> **MomentShackle_ExtraBlockDamage (0x570 = 1392)**, BONUS.

(Cles `IdunBattle.Configuration.AbilityVariableType` : 20 = blockDmg, 21 = blockChance — dump enums
du build.) L'APPARIEMENT lambda -> effectType est fixe par le call-site :
`IdunBattleLogic.Entities.Abilities.Active.Loki.MomentShackleAbility$$ExecuteBehaviour` passe
`statType = 7 BlockChance` avec `0x56f` et `statType = 8 BlockDamage` avec `0x570` — le `varKey` de
chaque lambda tombe donc sur le statType de son propre effectType, sans ambiguite.

Le TROISIEME effet du cast (`MomentShackle_Attack`, 0x571 = 1393) est un MARQUEUR sans stat-mod :
c'est lui que lit le trigger de la triggered-ability
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MomentShackle_AttackAbility$$CreateTrigger`
(`On(0x1f) & HasEffect(owner@0x148, 0x571, 0, 6) & (AreEnemies & IsAdjacent) & !AreEqual(...)`).
Aucune classe portee ne lui est necessaire : `BaseEffect` nu = « effet PRESENT, sans modification »,
ce dont le marqueur a exactement besoin. La face TRIGGERED (la contre-attaque sur mouvement) n'est
PAS portee — residu nomme, cf. `MomentShackleAbility`.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
from .votann import _source_level_mult
from ...stats import StatType

_MOMENT_SHACKLE = "MomentShackle"       # ActiveAbilityType 0x4a0 = 1184 (custoTrajann / Trajann)


class MomentShackleExtraBlockChanceEffect(BaseEffect):
    """`MomentShackle_ExtraBlockChance` (0x56f = 1391) — stat-mod **BlockChance(7)** POSITIF,
    self-buff du caster, `TurnsFromRounds(nrOfRounds = 1)`. Pose par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.MomentShackleAbility$$ExecuteBehaviour` :

        AddDynamicStatModifierEffect( owner@0x148, 0x56f, stat = 7 BlockChance,
                                      TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)) )

    (le call-site passe `owner@0x148` en SOURCE comme en CIBLE -> le porteur EST le caster, meme
    forme que le helper `...$$AddDynamicStatModifierEffectToOwner` du lot Votann).

    Magnitude = `blockChance[activeAbilityLevel de la SOURCE]` (lambda `...b__14_400`, varKey
    0x15 = 21, `isNegative = 0`). NON rarity-scale : `variablesAffectedByRarityBonus` de 1184 =
    [hpToHeal, blockDmg, minDmg, maxDmg] — `blockChance` n'y est PAS, et `ability_var` n'applique le
    multiplier qu'aux variables listees, donc l'appel avec `multiplier_pct` reste correct par
    construction (meme invariant que `AncestralFortuneExtraCritChanceEffect`)."""
    stat_mod_source = None   # cle de source ChangeStat (revert par-source via la feuille RemoveEffect)

    def applied_stat_mods(self, stats_ctx) -> "list":
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(_MOMENT_SHACKLE, "blockChance", lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.BLOCK_CHANCE), int(amt))]      # isNegative = 0 -> +amount

    def reverted_stats(self) -> "list":
        return [StatType.BLOCK_CHANCE]


class MomentShackleExtraBlockDamageEffect(BaseEffect):
    """`MomentShackle_ExtraBlockDamage` (0x570 = 1392) — stat-mod **BlockDamage(8)** POSITIF,
    self-buff du caster, meme duree. Jumeau exact du precedent :

        AddDynamicStatModifierEffect( owner@0x148, 0x570, stat = 8 BlockDamage, TurnsFromRounds(1) )

    Magnitude = `blockDmg[activeAbilityLevel de la SOURCE]` x multiplier de rarete (lambda
    `...b__14_401`, varKey 0x14 = 20, `isNegative = 0`). `blockDmg` EST dans
    `variablesAffectedByRarityBonus` de 1184 -> le multiplier s'applique bien ici (contraste
    `blockChance` ci-dessus : c'est la config qui tranche, pas une convention)."""
    stat_mod_source = None

    def applied_stat_mods(self, stats_ctx) -> "list":
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(_MOMENT_SHACKLE, "blockDmg", lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.BLOCK_DAMAGE), int(amt))]

    def reverted_stats(self) -> "list":
        return [StatType.BLOCK_DAMAGE]
