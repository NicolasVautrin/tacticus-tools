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

LE REGIME CROSS-UNITE ETAIT FAUX, ET IL EST DESORMAIS LU (case-366-r1-statmod). La feuille
`AddStaticStatModifierEffect` construit `AddStatModifierEffectBehaviour..ctor` avec **source = NULL**
(4e argument) ; `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute` retombe alors
sur l'ENTITE-CIBLE (`lVar9 = <target>; if (sourceSelectionne != 0) lVar9 = <source>;`). Donc
`EffectComponent.SourceUnit` -- le canal que consulte `effects_state.baked_ability_state` -- designe
le PORTEUR, jamais Aun'Shi : sur un ALLIE, la re-derivation lisait son niveau et son multiplier a lui.
MESURE live du 2026-08-01 (MC1_67 / 3711, `--unit-stat "tauCrisis:PassiveAbilityLevel=20"`) :
`SourceUnit` = **l'allie lui-meme** (u83, pas Aun'Shi u81), `StatModifierComponent.Amount` = **797**
sur les DEUX porteurs, re-derivation depuis l'allie = **76** (`extraDmg[20] x 180 %`) -> residu opaque
721, et a l'expiration l'ATTACK de l'allie restait a 1425 la ou le natif la ramene a 704.

D'ou la lecture du canal CAPTE en priorite ci-dessous. Le repli (canal absent : pose OFFLINE, ou
capture anterieure au capteur) reste la re-derivation, EXACTE sur Aun'Shi lui-meme (source == porteur)
et APPROCHEE sur un allie -- sous-attribution absorbee par le residu opaque, jamais une
sur-attribution.
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
        """`AStatModifierEffect$$GetStatModificationStat` = `StatModifierComponent+0x10`.

        On lit le champ tel que la capture le publie (MESURE : `StatType = 0`), avec repli sur le
        litteral `0 = ATTACK` du `CreateBehaviour` quand le canal est absent -- les deux valent 0,
        le natif n'ayant qu'UNE feuille de pose pour 1171."""
        native = self.captured_stat_mod_stat()
        return native if native is not None else 0

    def get_stat_modification_amount(self) -> int | None:
        """`StaticStatModifierEffect$$GetStatModificationAmount` = `StatModifierComponent+0x14`.

        Canal CAPTE en priorite : c'est litteralement ce que le natif relit, et la SEULE lecture
        exacte hors d'Aun'Shi -- la feuille de pose passe `source = null`, donc
        `EffectComponent.SourceUnit` (la cle de `baked_ability_state`) designe le PORTEUR.
        MESURE 2026-08-01 : natif `Amount = 797` sur l'allie, re-derivation depuis lui `76`.

        REPLI, canal absent (pose OFFLINE, capture anterieure au capteur) : `ConfigVar(8 = extraDmg)`
        indexe par `ability_level` -- `SereneUnifier` est un PASSIF, donc le slot passif, JAMAIS
        `active_ability_level`. EXACT sur Aun'Shi (source == porteur), APPROCHE sur un allie dont le
        niveau/multiplier differe (sous-attribution : le residu opaque absorbe l'ecart, jamais une
        sur-attribution)."""
        native = self.captured_stat_mod_amount()
        if native is not None:
            return native
        # `SereneUnifier` = passif -> `ability_level` (slot passif) ; fallback sur le stack `level`.
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var(_ABILITY_ID, "extraDmg", lvl,
                           multiplier_pct=self.ability_variables_multiplier)
