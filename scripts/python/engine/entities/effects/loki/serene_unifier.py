"""`SereneUnifierStormOfFire` (1171 = 0x493) — phase ATTAQUE du cycle a 3 temps du passif
`SereneUnifier` (`TriggeredAbilityType` 0x479 = 1145) de `tauAunShi`.

ARTEFACT NATIF : aucune classe d'effet dediee — l'entite-effet est un
`IdunBattle.Entities.Effects.StaticStatModifierEffect` GENERIQUE, instancie par la feuille
`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`
(signature `(targets, effectType, statType, amount, turns, isHidden)`) de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour`.

LE CYCLE, lu au decompile (`Modulo(PlayerTurnsStarted, Direct(3), Direct(k))` -> `If(..., ..., Nothing)`) :

    k = 0 -> AddStaticStatModifierEffect(units, 0x493 = 1171, stat = 0 ATTACK,
                                         ConfigVar(8 = extraDmg, abilityState), TurnsFromRounds(1))
    k = 1 -> AddEffect(0x491 = 1169 SenseOfStone, ...,                          TurnsFromRounds(1))
    k = 2 -> AddStaticStatModifierEffect(units, 0x492 = 1170 ZephyrsGrace, stat = 1 MOVEMENT,
                                         ConfigConst(0xe = extraMovement),      TurnsFromRounds(1))
    (+ les trois `*_Visual` 0x49a/0x498/0x499, `NoneEffect` inertes — case-366 3.2)

`units` = `(AdjacentFriends(1) + Self) + UnitsFromFaction(SurroundingFriends(ConfigConst(0x16 = range))
- AdjacentFriends, T'au = 9)` — self + amis adjacents + amis T'au a <= 2. Le porteur EST dans la cible :
Aun'Shi se buffe lui-meme, et c'est le seul cas ou source == porteur (cf. MAGNITUDE ci-dessous).

POURQUOI CETTE CLASSE EXISTE COTE PORT (#118, meme motif que `ThrillSeekersEffect` /
`RealityUnbound*`) : `decisionView.effects` n'expose NI le stat NI le montant d'un effet CAPTE. Un
`SereneUnifierStormOfFire` DEJA ACTIF au chargement d'un `State` arrivait donc sans stat-modification
declaree -> sa contribution restait dans le RESIDU OPAQUE (`CAPTURED_SOURCE`) de `seed_unit_stats`,
attribuee a AUCUNE source retirable. Or cet effet porte un VRAI TIMER (`TurnsFromRounds(1)`) : a
l'echeance le natif sort la `ValueModification`
(`IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification`, ChangeStat part 6) alors que
le port gardait le +extraDmg d'ATTACK **A VIE**. C'est un bug de DUREE, invisible tant qu'on mesure
juste apres la pose. Garde : `tests/engine/runner/test_static_statmod_g1_expiry.py`.

MAGNITUDE : `ConfigVar(8 = extraDmg, <AbilityState du POSEUR>)` == gameconfig
`SereneUnifier.variables.extraDmg[level]`, et `extraDmg` figure dans `variablesAffectedByRarityBonus`
-> scalee par l'`AbilityVariablesMultiplierPercentage`. `SereneUnifier` est un PASSIF -> le niveau est
`ability_level` (slot passif), jamais `active_ability_level`.

LIMITE ASSUMEE (identique a `RitesOfBattle`, buff cross-unite) : au SEED, l'instance porte le niveau
du PORTEUR, pas celui du POSEUR. Sur AUN'SHI LUI-MEME (source == porteur) la magnitude est donc
EXACTE et le residu opaque tombe a 0 — c'est le regime que la garde mesure. Sur un ALLIE buffe, le
niveau lu peut differer de celui d'Aun'Shi : la contribution reste alors partiellement dans le residu
(sous-attribution), jamais une sur-attribution — `seed_unit_stats` reproduit toujours le `Current`
capte exactement.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var

_ABILITY_ID = "SereneUnifier"


class SereneUnifierStormOfFireEffect(BaseEffect):
    """`SereneUnifierStormOfFire` (0x493 = 1171) — +`extraDmg` ATTACK pour 1 round, phase `k = 0` du
    cycle `Modulo(PlayerTurnsStarted, 3)` de `SereneUnifierAbility$$CreateBehaviour`.

    Jumeau structurel de `ThrillSeekersEffect` (meme feuille generique, meme canal de revert) ; le
    frere de la phase `k = 1`, `1169 SereneUnifierSenseOfStone`, est deja porte
    (`effects/loki/damage_reduction.py`) mais par un canal DIFFERENT (classe native bespoke a
    `CreateEffectDamageMalusForDefense`) : lui n'a aucune stat-modification."""

    def get_stat_modification_stat(self) -> int | None:
        return 0                                     # StatType.ATTACK (statType du CreateBehaviour)

    def get_stat_modification_amount(self) -> int | None:
        # `SereneUnifier` = passif -> `ability_level` (slot passif) ; fallback sur le stack `level`.
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var(_ABILITY_ID, "extraDmg", lvl,
                           multiplier_pct=self.ability_variables_multiplier)
