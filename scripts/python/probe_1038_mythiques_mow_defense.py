"""#1038 -- PROBE de mesure (pas un test) : les deux mythiques de MoW dont la face DEGAT est un
MALUS DEFENSEUR -- `MastersOfManoeuvre` (1508 / effet 1510) et `ContemptuousDisregard`
(1450 / effet 1443).

Il DECOMPOSE PAR ETAGE, dans l'ordre ou le port les traverse :
  0. la MoW est-elle une entite ECS, porte-t-elle la TERTIAIRE, et avec quel couple
     (`tertiary_ability_level`, `tertiary_ability_variables_multiplier`) ?
  1. l'effet est-il CAPTE (`decisionView.effects` -> `state.effects`), sur QUI, et avec quel
     `(ability_level, ability_variables_multiplier)` -- c'est-a-dire l'`AbilityState` BAKEE que
     `ConfigVar(0x46)` va indexer ;
  2. que rend `create_effect_damage_malus_for_defense` sur les TROIS natures de coup
     (ranged prouve / melee prouvee / inconnue) ;
  3. rejeu PORT d'une attaque ranged sur le porteur, avec et sans l'effet : le RATIO mesure la
     reduction REELLEMENT appliquee par le pipeline, pas seulement celle que la classe annonce.

Usage :
    python probe_1038_mythiques_mow_defense.py --state-file <ABSOLU> --effect MastersOfManoeuvre
                                               [--attacker <id>] [--carrier <id>]

Le state-file est celui d'un `rl_duel build ... --p-mow <MoW> --equip-mythic "<MoW>:<Ability>:<lvl>"`
sur lequel l'effet a DEJA ete pose par le natif (pour 1510 : deplacer une unite MYTHIQUE amie
d'au moins `tilesTraversed` = 2 tuiles).
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import rl_collect_batch as R                                               # noqa: E402

#: `EffectType` (`frida/enums.tsv`) -> l'ability TERTIAIRE qui le pose (`TriggeredAbilityType`).
CIBLES = {
    "MastersOfManoeuvre": (1510, 1508),
    "ContemptuousDisregard_DamageReduction": (1443, 1450),
}


def _unwrap(res):
    if isinstance(res, dict) and "result" in res and isinstance(res["result"], dict):
        return res["result"]
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--effect", default="MastersOfManoeuvre",
                    help="nom d'EffectType : %s" % " | ".join(sorted(CIBLES)))
    ap.add_argument("--attacker", type=int, default=None, help="id du tireur (defaut : 1er ennemi)")
    ap.add_argument("--carrier", type=int, default=None, help="id du porteur (defaut : deduit)")
    args = ap.parse_args()
    if args.effect not in CIBLES:
        print("[1038] effet inconnu : %s" % args.effect)
        return 2
    etype, ability_id = CIBLES[args.effect]

    rid = int(json.loads(Path(args.state_file).read_text())["runnerId"])
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        b = {**(body or {}), "runnerId": rid}
        return _unwrap(R._rpc(sid, method, [b], timeout=timeout))

    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state, bind_live_rpc
    from engine.runner.components import HealthComponent, StatsComponent

    bind_live_rpc(lambda m, b, t=90: _unwrap(R._rpc(sid, m, [b], timeout=t)))
    bg = rpc("boardGraph", {}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"allAbilities": True}, 120)
    ob = rpc("observeBattle", {}, 60)
    snap = rpc("combatSnapshot", {}, 90)
    st = load_state(dv, ob, snap, board=board)

    # ---- ETAGE 0 : la MoW et son couple TERTIAIRE -------------------------------------------
    print("=== ETAGE 0 : la MoW porteuse de la mythique ===")
    mows = [m for m in (dv.get("mows") or []) if m.get("casterId") is not None]
    for m in mows:
        ent = st.get_entity(int(m["casterId"]))
        sc = ent.get_component(StatsComponent) if ent is not None else None
        ctx = getattr(sc, "ctx", None)
        print("  mow %s [%s] entite=%s tertiary=%s lvl=%s mult=%s | passif lvl=%s mult=%s"
              % (m.get("casterId"), m.get("visualId"), ent is not None,
                 getattr(ctx, "tertiary_ability", None),
                 getattr(ctx, "tertiary_ability_level", None),
                 getattr(ctx, "tertiary_ability_variables_multiplier", None),
                 getattr(ctx, "ability_level", None),
                 getattr(ctx, "ability_variables_multiplier", None)))

    # ---- ETAGE 1 : l'instance CAPTEE et son AbilityState bakee -------------------------------
    print("=== ETAGE 1 : l'instance d'effet %d (%s) captee ===" % (etype, args.effect))
    porteurs = []
    for uid, effs in ((st.effects.by_unit if st.effects else {}) or {}).items():
        for e in effs:
            if int(getattr(e, "effect_type", -1) or -1) == etype:
                porteurs.append((int(uid), e))
                print("  porteur=%s source=%s ability_level=%s mult=%s remaining=%s active=%s"
                      % (uid, e.source, e.ability_level, e.ability_variables_multiplier,
                         e.remaining_turns, e.active))
    if not porteurs:
        print("  AUCUNE instance captee -- le natif ne l'a pas posee (regime non atteint) : "
              "rien a mesurer plus bas.")
        return 1
    carrier_id, eff = (next((p for p in porteurs if p[0] == args.carrier), porteurs[0])
                       if args.carrier is not None else porteurs[0])

    # ---- ETAGE 2 : les trois natures de coup -------------------------------------------------
    print("=== ETAGE 2 : create_effect_damage_malus_for_defense, par nature de coup ===")
    for lib, is_melee in (("ranged prouve (is_melee=False)", False),
                          ("melee prouvee (is_melee=True)", True),
                          ("nature inconnue (is_melee=None)", None)):
        print("  %-32s -> %s" % (lib, eff.create_effect_damage_malus_for_defense(is_melee=is_melee)))

    # ---- ETAGE 3 : rejeu PORT, avec et sans l'effet -------------------------------------------
    print("=== ETAGE 3 : rejeu PORT d'une attaque RANGED sur le porteur ===")
    units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("alive")}
    porteur_u = units.get(carrier_id)
    if porteur_u is None:
        print("  le porteur %s n'est pas une unite du plateau -- rejeu impossible" % carrier_id)
        return 0
    equipe = porteur_u.get("team")
    tireur = (args.attacker if args.attacker is not None
              else next((i for i, u in units.items()
                         if u.get("team") != equipe and (u.get("pos") or {}).get("col") is not None),
                        None))
    if tireur is None:
        print("  aucun tireur adverse -- rejeu impossible")
        return 0

    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage

    def _rejoue(avec_effet: bool):
        s = load_state(dv, ob, snap, board=board)
        d = rpc("dumpRng", {}, 30)
        if isinstance(d, dict) and d.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(d["mt"]); rng.mti = d["mti"]
            s.rng = rng
        if not avec_effet and s.effects is not None:
            s.effects.by_unit[carrier_id] = [
                e for e in (s.effects.by_unit.get(carrier_id) or [])
                if int(getattr(e, "effect_type", -1) or -1) != etype]
        hc = s.get_entity(carrier_id).get_component(HealthComponent)
        hp0 = hc.hp if hc else None
        Runner(s).install_default_handlers(20).apply(AttackUnitMessage(tireur, carrier_id))
        hp1 = hc.hp if hc else None
        return hp0, hp1

    a0, a1 = _rejoue(True)
    b0, b1 = _rejoue(False)
    d_avec, d_sans = (a0 - a1 if None not in (a0, a1) else None,
                      b0 - b1 if None not in (b0, b1) else None)
    print("  tireur=%s porteur=%s" % (tireur, carrier_id))
    print("  AVEC effet : hp %s -> %s  (degat %s)" % (a0, a1, d_avec))
    print("  SANS effet : hp %s -> %s  (degat %s)" % (b0, b1, d_sans))
    print("  /!\\ CES DEUX NOMBRES NE SE COMPARENT PAS -- mesure #1038 : le tirage de degat consomme")
    print("    le RNG DIFFEREMMENT selon les modificateurs (balayage pct 0..20 : 2008, 2162, 2421,")
    print("    2102, ... NON MONOTONE). Le bras A/B se fait sur `aiPredict`, etage 4.")

    # ---- ETAGE 4 : `aiPredict` NATIF, la seule mesure DETERMINISTE -----------------------------
    print("=== ETAGE 4 : aiPredict NATIF (preview, sans RNG) ===")
    pr = rpc("aiPredict", {"unitId": int(tireur), "targetId": int(carrier_id), "fresh": True}, 90)
    print("  natif %s -> %s : %s" % (tireur, carrier_id, json.dumps(pr)[:400]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
