"""engine.entities.damage_trait — enum natif `DamageTrait` (traits de PROFIL DE DEGAT).

Mirror 1:1 de l'enum natif `DamageTrait` (dump.cs `gqfc5mff6c`, TypeDefIndex 24353) : les traits portes
par un `DamageProfile` (arme / attaque), DISTINCTS des `UnitTrait` (traits d'unite, TypeDefIndex 24364,
cf. entities/traits/unit_trait.py). Teste via `DamageProfile.HasTrait(DamageTrait)`.

Le port referencait ces traits en ints bruts (`profile_has_trait3`, `PROFILE_TRAIT_HITS_MULTIPLE_MEMBERS
= 2`, `"OnFire" in Traits`...) -> #156 : cet enum est desormais la source unique id<->nom (meme demarche
que `UnitTrait` #146 / `EventTriggerType` #155). Les `DamageProfile.Traits` gameconfig sont des NOMS de
chaine -> les checks se font name-based (`DamageTrait.X.name in Traits`), pas via des int bruts.

Usages dans le port (post-#156) :
  - NoBlocking (0)          : le profil BYPASSE le block. COMBAT (#65) : `AttackDamageOperation._block_sources`
                              gate sur ce trait (profil Psychic -> aucune source, 0 tirage), mirror du flag
                              `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (`DamageProfile.HasTrait(0)` -> skip block/evade de
                              `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`). PREDICTION (`PredictAttackRaw`) : reste
                              non-gate (residu documente case-65-noblocking-block-bypass, scenario WillBeKill).
  - OnFire (1)              : `OnFireDamageAbility` pose du feu on-hit (`DamageTrait.OnFire.name in Traits`, triggers.py).
  - HitsMultipleMembers (2) : "Blast" -> `ApplyGroupUnitDamageLimit` SKIP le member-cap (bool
                              `profile_has_hits_multiple_members`, trait_damage_limits ; moot tant que member_count=1).
  - LasCannon (3)           : bonus de percage si l'attaquant a `UnitTrait.HeavyWeapon` (1001) /
                              `UnitTrait.Emplacement` (1016) — bool `profile_has_lascannon` dans
                              get_piercing_ratio / static_battle_rules (non wire, defaut False).
  - OnToxic (4)             : attaque Toxic -> pose Contaminated (OnToxicDamageAbility, #137).
  - OnMelta (5)             : attaque Melta. i2 `Keywords/DMG_Melta` = "75% pierce ratio. Deals +50%
                              damage against Vehicle units". Le +50% vs Vehicle est DEAD CODE dans le
                              build gqfc5mff6c -> NON porte (le porter DIVERGERAIT du live). Racine :
                              `OnMeltaDamageAbility` (TriggeredAbilityType 1211) a un `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnMeltaDamageAbility$$CreateBehaviour (`AddEffect(Melta_ExtraDmg=1297, First(+0x78))`) mais AUCUN
                              `CreateTrigger` -- contrairement a OnFire (1016, trigger IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateTrigger) et
                              OnToxic (1203, trigger IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateTrigger). Sans trigger l'ability ne fire jamais
                              -> l'effet `Melta_ExtraDmgEffect` (IdunBattle.Entities.Effects.Loki.Melta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack `ForPercentIncrease(
                              DamageProfileHasTrait(OnMelta) & HasTrait(target, Vehicle=1029),
                              ConfigConst 0xf=meltaDamageExtraDmgPct=50)`) n'est JAMAIS pose -> le +50%
                              n'est applique NI en prediction NI en combat. CONFIRME LIVE (case-72) :
                              tauShadowsun Melta ranged vs admecDestroyer (Vehicle) predit [6008-9014]
                              == vs cible non-Vehicle (aucun +50%), aucun effet pose post-coup ; A/B :
                              OnFire pose bien `Fire` on-hit dans le meme runner. Verdict = DEAD-CODE
                              documente (cf. docs/rl/case-72-onmelta-dead-code.md), pas un gap de port.
"""
from __future__ import annotations

from enum import IntEnum


class DamageTrait(IntEnum):
    """`DamageTrait` @dump.cs TypeDefIndex 24353. Valeur == id natif (arg de `DamageProfile.HasTrait`)."""
    Unknown = -1
    NoBlocking = 0
    OnFire = 1
    HitsMultipleMembers = 2   # "Blast"
    LasCannon = 3
    OnToxic = 4
    OnMelta = 5
