"""Probe #118 — un stat-mod d'effet SEEDE sort-il du `UnitStats` quand l'effet expire ?

MESURE, pas garde : 100 % offline (aucun runner, aucune session Frida). Construit un `State`
minimal ou l'effet `ThrillSeekers` (1434, +15 CritChance, TIMER) est DEJA porte au chargement
-- exactement l'etat que produit `load_state` quand la capture est prise APRES la pose -- puis
tique jusqu'a expiration et lit la crit chance.

Question tranchee (RE, build gqfc5mff6c) : le natif applique la stat-modification d'un effet en
`ValueModification` PAR-SOURCE keyee par l'ENTITE-EFFET
(`IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification` passe
`IdunBattleLogic.Entities.DSLSelectors$$Entity(<effectEntity>)` en 6e argument de
`IdunBattleLogic.Entities.DSLBehaviors$$ChangeStat`) et la RETIRE au retrait de l'effet
(`IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification`, meme entite, `Position(stat,
part 6)` -> `IdunBattle.Entities.Components.ValueModification$$ReverseModification`). Le port devait
donc, lui aussi, attribuer la contribution du SEED a une source retirable.

Sortie attendue APRES le fix   : per_source = {('statmod', 1434, ...): 15} et cc 55 -> 40.
Sortie mesuree AVANT le fix    : per_source = {'captured': 15} (residu opaque) et cc 55 -> 55
                                 (le +15 seede restait applique A VIE).

Usage : depuis `scripts/python`, `python probe_118_seeded_statmod_revert.py`.
"""
from __future__ import annotations

from engine.entities.effects.factory import EffectFactory
from engine.entities.effects_state import EffectsState
from engine.entities.unit_context import UnitContext
from engine.runner.components import StatsComponent
from engine.runner.operations.effects import revert_stat_mods_of_removed_effects
from engine.runner.state import State

# Effet CAPTE tel que `decisionView.units[].effects[]` le rend (le capteur n'expose NI le stat NI
# le montant -- cf. frida/hooks/game/effects.ts : EffectType/remaining/level/source seulement).
CAPTURED = {"name": "ThrillSeekers", "effectType": 1434, "level": 1, "remaining": 2, "source": 7}
STAT_IDS = {"critChance": 9, "attack": 0, "health": 5}
# `combatSnapshot` d'une unite qui porte DEJA le buff : Current 55, statDelta +15 (le +15 est donc
# DEJA CUIT dans les stats captees -- c'est tout le probleme du cas SEEDE).
SNAP_UNIT = {"entityId": 11, "visualId": "emperNoiseMarine",
             "stats": {"critChance": 55, "attack": 100, "health": 8000},
             "statDelta": {"critChance": 15}}
EXTRA_CC = 15


def build_seeded_state():
    """`State` minimal reproduisant la voie SEEDE de `snapshot._load_stats_and_effects` :
    `UnitContext.from_snapshot` (attribution) + `EffectsState.seed` (instances evoluees)."""
    effs = EffectFactory.create_many([CAPTURED])
    ctx = UnitContext.from_snapshot(SNAP_UNIT, None, STAT_IDS, effs)
    st = State()
    st.add_entity(SNAP_UNIT["entityId"]).add_component(StatsComponent(ctx=ctx))
    st.effects = EffectsState.seed({SNAP_UNIT["entityId"]: [CAPTURED]})
    return st, ctx, effs[0]


def main() -> int:
    st, ctx, eff = build_seeded_state()
    uid = SNAP_UNIT["entityId"]
    cc0 = ctx.stat(9)
    print("classe d'effet   : %s" % type(eff).__name__)
    print("stat/montant     : %s / %s" % (eff.get_stat_modification_stat(),
                                          eff.get_stat_modification_amount()))
    print("per_source(cc)   : %s" % (ctx.stats.components[9].modification.per_source,))
    print("cc au chargement : %s" % cc0)
    for i in range(3):
        st.effects.on_turn_end(uid, attacked=False)
        out = revert_stat_mods_of_removed_effects(st)
        print("tick %d -> rem=%s reverts=%s cc=%s"
              % (i + 1, st.effects.by_unit[uid][0].remaining_turns, out, ctx.stat(9)))
    cc1 = ctx.stat(9)
    ok = (cc1 == cc0 - EXTRA_CC)
    print("VERDICT          : %s (cc %s -> %s, attendu %s)"
          % ("REVERTE" if ok else "NON REVERTE", cc0, cc1, cc0 - EXTRA_CC))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
