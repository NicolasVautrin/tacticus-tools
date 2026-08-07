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
                              damage against Vehicle units". Le +50% vs Vehicle est VIVANT sur
                              `rnca9r7q6c` et PORTE (#488-r1) : `MeltaExtraDmgEffect`
                              (`effects/loki/extra_damage.py`), inscrit dans `MATCH_WIDE_EFFECTS`.
                              L'effet `Melta_ExtraDmgEffect` (IdunBattle.Entities.Effects.Loki.Melta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack
                              = `ForPercentIncrease(DamageProfileHasTrait(OnMelta) &
                              HasTrait(target, Vehicle=1029), ConfigConst 0xf =
                              meltaDamageExtraDmgPct = 50)`) est pose au `MatchInit` par l'ability
                              GLOBALE 1211 sur UNE TUILE arbitraire (IdunBattleLogic.Entities.Abilities.Damage.Loki.OnMeltaDamageAbility$$CreateBehaviour
                              = `AddEffect(1297, AbilityStateReference, First(AllTiles(), 1))`).
                              ⚠ CE PARAGRAPHE A DEJA ETE FAUX, ET C'EST LE PIEGE A CONNAITRE.
                              `case-72` concluait DEAD-CODE au motif que 1211 n'override pas
                              `CreateTrigger` : vrai sur `gqfc5mff6c`, FAUX ici. Le corps de
                              IdunBattleLogic.Entities.Abilities.Damage.Loki.OnMeltaDamageAbility$$CreateTrigger
                              (`On(0x19 = MatchInit, true)`) est DEDUPLIQUE -- seul le slot de
                              vtable de l'INSTANCE le prouve (profondeur 0, RPC `resolveMethodPtr`).
                              Et l'ABSENCE d'observation ne prouvait rien non plus : l'effet est sur
                              une TUILE, donc invisible de `decisionView.effects`, vue PAR UNITE.
                              MESURE (#488-r1, armure egalisee, geometrie identique) : natif
                              [9014-13520] vs `Vehicle` contre [6008-9014] vs DEUX temoins
                              non-Vehicle -- rapport 1,5000 exact, et nul en melee (profil
                              non-Melta). Cf. docs/rl/case-488-r1-onmelta-vivant-ou-mort.md ; le
                              verdict de docs/rl/case-72-onmelta-dead-code.md ne vaut QUE pour
                              `gqfc5mff6c`.
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
