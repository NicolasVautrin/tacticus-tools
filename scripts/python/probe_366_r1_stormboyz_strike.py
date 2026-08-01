#!/usr/bin/env python
"""#366-r1 tranche 3/3 -- `1141 StormboyzStrike` (triggered, passif d'`orksNpc6Stormboy`).

CE QUE CE PROBE TRANCHE, en deux fronts INDEPENDANTS :

  FRONT 1 -- le port de `...StormboyzStrike_TeleportAbility$$CreateBehaviour` :
      RemoveUnitFromItsTiles(Owner, true) & AddEffect(0x474, stateRef, Owner, turns: Nullable(2))
    CONFRONT terme a terme : deux runners MEME seed / MEME board / MEMES unites, l'un avec le
    passif GREFFE sur une unite du pool, l'autre sans. Le natif applique l'ability a l'init du
    runner GREFFE ; le port l'applique OFFLINE a l'etat du runner TEMOIN. Les deux etats finaux
    doivent coincider sur (pos, feet, alive, effet 1140 + son `remaining`).
    `remaining` est le DISCRIMINANT du `turns` : `Nullable<int>(2)` est deja en TOURS (2), un
    `TurnsFromRounds(2)` vaudrait 4 a deux joueurs.

  FRONT 2 -- l'HYPOTHESE `IsValidTeleportTile == true` de
    `IdunBattle.Entities.Pathfinding.StormboyzStrikePathfinder` (vslot 11), portee par `#381-r5`
    faute de porteur confrontable. L'unite greffee est hors plateau sous 1140 -> son pathfinder
    est `StormboyzStrikeWalk/Fly` (8/9) et son pool de destination est BOARD-WIDE. On compare le
    pool NATIF (`aiMovableTiles`) au pool du port sous TROIS predicats :
        (a) `True`                 -- l'hypothese portee
        (b) `TeleportStrike`       -- « pas d'ennemi adjacent », le voisin le plus plausible
        (c) base seule (pas de pool de teleport)
    Si (a) == natif et (b) != natif, l'hypothese est CONFRONTEE, pas seulement compatible.

  ⚠ `MovementQuery$$AnyOrFillMoveableTiles` (decompile) : quand `tiles.Count == 0` -- exactement le
  cas d'une unite hors plateau -- le natif appelle `GetReachableTiles(start = NULL, type, range,
  unit)`. Le port, lui, exige un `from_tile` : `services/movement_query.get_movable_tiles_for` n'a
  pas cette branche. Le probe calcule donc le pool du port en appelant DIRECTEMENT
  `entities.pathfinding.teleport_pathfinder.find_tiles_reachable_by_teleport` (= la moitie
  board-wide du decorateur, la seule que `start = NULL` laisse produire).

MONTAGE. Porteur unique `orksNpc6Stormboy`, bucket **npc** -> ni pool ni summoner -> GREFFE du
passif sur une unite du pool (`catalog_inject.graft_passive_ability`, `case-92` §5bis). Legitime :
ni le trigger ni le behaviour ne lisent stat, trait ou arme du caster. Deux greffons pour couvrir
les deux BASES du decorateur : un non-volant (`StormboyzStrikeWalk` 8) et un volant
(`StormboyzStrikeFly` 9, comme le vrai porteur qui a le trait `Flying`).

ASCII only. Usage (depuis scripts/python) :
    python probe_366_r1_stormboyz_strike.py
    python probe_366_r1_stormboyz_strike.py --board C3_26 --seed 31337 --graft orksNob
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                   # noqa: E402
import catalog_inject as CI                                              # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

ABILITY = "StormboyzStrike"
TELEPORTING_IN = 0x474            # 1140 EffectType.StormboyzStrike_TeleportingIn
ALREADY_USED_TILE = 0x49b         # 1179 EffectType.StormboyzStrike_AlreadyUsedTile (pose par _Fallback)
LOGS = ROOT / "logs"

#: `(board, seed, greffon, adversaires, note)`. QUATRE montages, chacun pour une raison :
#:   1. `orksNob`      -- greffon NON volant -> base `StormboyzStrikeWalk` (8) ;
#:   2. `thousTzaangor`-- greffon VOLANT sans autre effet de mouvement special -> base
#:      `StormboyzStrikeFly` (9), comme le VRAI porteur (`orksNpc6Stormboy` a le trait `Flying`) ;
#:      autre board, autre seed ;
#:   3. TROIS adversaires -- le predicat concurrent `TeleportStrike` (« pas d'ennemi adjacent »)
#:      retire d'autant plus de tuiles qu'il y a d'ennemis : c'est le montage qui donne au front 2
#:      son POUVOIR DISCRIMINANT (un ecart de 2 tuiles se plaide mal, un ecart large non) ;
#:   4. `bloodIntercessor` -- CONFOND VOLONTAIRE : ce greffon porte le trait `TeleportStrike`, donc
#:      l'effet `0x40b = 1035 TeleportStrike_TeleportingIn`, que `MovementQuery$$
#:      GetPathfinderTypeForUnit` teste AVANT `0x474`. Son pathfinder n'est donc PAS Stormboyz :
#:      le montage mesure l'ORDRE des tests, pas le predicat de Stormboyz. Garde-fou : le probe
#:      IMPRIME le type de pathfinder effectif et refuse de compter ce montage comme une
#:      confrontation du front 2.
PLAN = [
    ("MC1_67", 777, "orksNob", ["ultraTitus"], "base WALK"),
    ("C3_26", 31337, "thousTzaangor", ["ultraTitus"], "base FLY"),
    ("MC1_67", 777, "orksNob", ["ultraTitus", "orksWarboss", "necroOverlord"], "discriminant"),
    ("C3_26", 31337, "bloodIntercessor", ["ultraTitus"], "CONFOND: trait TeleportStrike -> 1035"),
]


def rpc(sid, m, args, t=120):
    r = _rpc(sid, m, [args], timeout=t)
    return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}


# ============================================================ VOLET A -- offline, re-derive tout

def volet_a() -> dict:
    idx = GC._index()
    carriers = []
    for bucket in ("lineup", "npc", "summons"):
        for uid, u in (idx.get(bucket) or {}).items():
            names = list(u.get("passiveAbilities") or []) + list(u.get("activeAbilities") or [])
            if any(ABILITY == n for n in names):
                carriers.append({"id": uid, "bucket": bucket,
                                 "faction": u.get("FactionId") or "", "traits": u.get("traits")})
    print("== A1. porteurs gameconfig de %s ==" % ABILITY)
    for c in carriers:
        print("   %-22s bucket=%-8s faction=%-10s traits=%s"
              % (c["id"], c["bucket"], c["faction"], c["traits"]))
    print("== A2. graphe summon (qui peut faire APPARAITRE ces porteurs ?) ==")
    for c in carriers:
        s = [aid for aid, a in idx["abilities"].items() if c["id"] in json.dumps(a)]
        print("   %-22s summoners=%s" % (c["id"], s if s else "AUCUN -> porte SUMMON FERMEE"))
    cfg = idx["abilities"].get(ABILITY) or {}
    print("== A3. config gameconfig ==")
    print("   variables=%s constants=%s" % (list((cfg.get("variables") or {}).keys()),
                                            list((cfg.get("constants") or {}).keys())))
    print("   -> la constante 'chance' n'est lue que par `StormboyzStrike_MissAbility` "
          "(GetNumberConstant(0x2a)), pas par la tranche portee ici")
    # Fermeture du domaine, lue dans la table VERSIONNEE du build courant.
    subs, tel = [], []
    for p in (ROOT / "data" / "symbols").glob("*/frida/classes.tsv"):
        for line in p.read_text(encoding="utf-8").splitlines():
            f = line.split("\t")
            if len(f) < 3:
                continue
            if f[2].endswith(".ATeleportingEffect"):
                tel.append(f[0].rsplit(".", 1)[-1])
            if f[2].endswith(".ATeleportPathfinder"):
                subs.append(f[0].rsplit(".", 1)[-1])
    print("== A4. fermeture du domaine (classes.tsv) ==")
    print("   sous-classes d'ATeleportingEffect  : %s" % sorted(set(tel)))
    print("   sous-classes d'ATeleportPathfinder : %s" % sorted(set(subs)))
    return {"carriers": carriers}


# ============================================================ montage LIVE

def build(seed: int, board: str, graft: str, foes, seed_bc: str, state_file: Path) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board, "--p-units", graft, "--a-units", ",".join(foes), "--no-ai",
           "--seed-bc", seed_bc, "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        sys.stdout.write((p.stdout or "")[-1500:])
        sys.stdout.write((p.stderr or "")[-1500:])
        raise SystemExit("build KO (board=%s graft=%s bc=%s)" % (board, graft, seed_bc))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def capture(sid, rid):
    """Les quatre canaux + l'etat ECS charge."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    ast = rpc(sid, "unitAbilityStates", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    state = load_state(dv, ob, snap, board=board, ability_states=ast)
    return {"bg": bg, "dv": dv, "ob": ob, "snap": snap, "ast": ast,
            "board": board, "state": state}


def carrier_id(state, foes):
    """L'id du GREFFON dans l'etat charge.

    ⚠ ON NE PEUT PAS le retrouver par `visualId` cote GREFFE : mesure du 2026-08-01 -- une unite
    SANS TUILE sort de `observeBattle` et arrive dans `decisionView` avec
    `visualId = pos = hp = owner = team = null` (seuls `id`, `alive`, `hasAction`, `abilities` et
    `effects` survivent). On l'identifie donc en NEGATIF : l'unite qui n'est pas l'adversaire.
    Les ids d'entite sont par ailleurs IDENTIQUES entre les deux runners (meme seed, meme board,
    memes unites) -- verifie a chaque run par le probe."""
    from engine.runner.components import StatsComponent
    out = []
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        vid = getattr(getattr(sc, "ctx", None), "visual_id", None)
        if vid not in set(foes):
            out.append(int(eid))
    return out[0] if len(out) == 1 else None


def team_of(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(int(uid))
    oc = e.get_component(OwnerComponent) if e is not None else None
    return None if oc is None else oc.team


def terms(state, uid):
    """Les TERMES compares de part et d'autre : position, empreinte, vie, effets (type, remaining)."""
    from engine.runner.components import PositionComponent, UnitComponent, get_unit_feet
    e = state.get_entity(int(uid))
    pc = e.get_component(PositionComponent) if e is not None else None
    uc = e.get_component(UnitComponent) if e is not None else None
    eff = getattr(state, "effects", None)
    rows = [] if eff is None else [(int(x.effect_type), getattr(x, "remaining_turns", None))
                                   for x in eff.by_unit.get(int(uid), []) if not x.consumed]
    return {"pos": None if pc is None else (pc.col, pc.row),
            "feet": sorted(get_unit_feet(state, int(uid)) or []),
            "alive": None if uc is None else bool(uc.alive),
            "effects": sorted(rows, key=lambda r: (r[0], -1 if r[1] is None else r[1]))}


def native_movable(sid, rid, uid):
    r = rpc(sid, "aiMovableTiles", {"runnerId": rid, "unitId": uid}, 120)
    for u in (r.get("units") or []):
        if int(u.get("unitId")) == int(uid):
            return [(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])
                    if t.get("col") is not None]
    return [(int(t["col"]), int(t["row"])) for t in (r.get("unionTiles") or [])
            if t.get("col") is not None]


def port_teleport_pools(state, board, uid, team):
    """Les TROIS pools du port pour l'unite HORS PLATEAU.

    Branche `tiles.Count == 0` d'`IdunBattle.Core.Services.MovementQuery$$AnyOrFillMoveableTiles`
    (decompile) : le natif appelle `GetReachableTiles(start = NULL, type, range, unit)` -- seule la
    moitie `ATeleportPathfinder$$FindTilesReachableByTeleport` du decorateur peut alors produire
    quelque chose. C'est donc elle qu'on compare, sous les trois predicats.

    `team` est passe par l'appelant (mesure prise sur le runner TEMOIN) : une unite sans tuile
    arrive dans `decisionView` avec `team = null`, ce qui rendrait le predicat `TeleportStrike`
    TOUJOURS vrai et lui oterait tout pouvoir discriminant."""
    from engine.ai.state_bridge import _occupants
    from engine.entities.pathfinding import teleport_pathfinder as TP
    from engine.entities.pathfinding.pathfinders import TELEPORT_DECORATORS
    from engine.runner.components import StatsComponent
    from engine.services.movement_query import get_pathfinder_type_for_unit, unit_has_effect_fn
    occ = _occupants(state)
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    traits = getattr(getattr(sc, "ctx", None), "traits", None) or []
    ptype = get_pathfinder_type_for_unit(unit_has_effect_fn(state, uid), traits)
    family = TELEPORT_DECORATORS.get(int(ptype), (int(ptype), ""))[1]
    pools = {}
    pools["stormboyz_true"] = TP.find_tiles_reachable_by_teleport(
        board, occ, is_valid_teleport_tile=lambda t: TP.is_valid_teleport_tile_stormboyz(
            t, board, occ, team))
    pools["teleport_strike"] = TP.find_tiles_reachable_by_teleport(
        board, occ, is_valid_teleport_tile=lambda t: TP.is_valid_teleport_tile_teleport_strike(
            t, board, occ, team))
    pools["base_only"] = set()
    return pools, occ, int(ptype), family


def run_pair(sid, seed, board_id, graft, foes, tag):
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    from engine.runner.operations.triggers.loki.stormboyz_strike import (
        StormboyzStrikeTeleportAbility)
    from engine.runner.snapshot import clear_ability_states_cache

    LOGS.mkdir(parents=True, exist_ok=True)
    bc_ctrl = LOGS / ("bc_stormboyz_control_%s.json" % tag)
    bc_graft = LOGS / ("bc_stormboyz_graft_%s.json" % tag)
    CI.write_grafted_seed_bc(str(bc_ctrl), [])                       # meme pipeline, sans greffe
    _p, reports = CI.write_grafted_seed_bc(str(bc_graft), ["%s:%s" % (graft, ABILITY)])
    print("[graft] %s" % json.dumps(reports[0]))

    sf_c = LOGS / ("probe_366r1_sbz_ctrl_%s.json" % tag)
    sf_g = LOGS / ("probe_366r1_sbz_graft_%s.json" % tag)
    rid_c = build(seed, board_id, graft, foes, str(bc_ctrl), sf_c)
    rid_g = build(seed, board_id, graft, foes, str(bc_graft), sf_g)
    out = {"board": board_id, "seed": seed, "graft": graft, "foes": list(foes),
           "ridControl": rid_c, "ridGraft": rid_g}
    try:
        clear_ability_states_cache()
        cap_c = capture(sid, rid_c)
        cap_g = capture(sid, rid_g)
        uid_c = carrier_id(cap_c["state"], foes)
        uid_g = carrier_id(cap_g["state"], foes)
        team = team_of(cap_c["state"], uid_c) if uid_c is not None else None
        print("[%s] board=%s seed=%s rid ctrl=%s graft=%s | uid ctrl=%s graft=%s team=%s"
              % (tag, board_id, seed, rid_c, rid_g, uid_c, uid_g, team))
        if uid_c is None or uid_g is None:
            print("[%s] ABANDON : greffon introuvable dans un des deux runners" % tag)
            return out
        if uid_c != uid_g:
            print("[%s] ATTENTION : ids d'entite DIFFERENTS entre les deux runners (%s vs %s)"
                  % (tag, uid_c, uid_g))
        out["sameEntityId"] = (uid_c == uid_g)

        # --- le passif est-il REELLEMENT monte cote GRAFT (canal mesure) ? ---------------------
        from engine.runner.components import StatsComponent
        e = cap_g["state"].get_entity(uid_g)
        sc = e.get_component(StatsComponent) if e is not None else None
        pas_g = getattr(getattr(sc, "ctx", None), "passive_abilities", None)
        e = cap_c["state"].get_entity(uid_c)
        sc = e.get_component(StatsComponent) if e is not None else None
        pas_c = getattr(getattr(sc, "ctx", None), "passive_abilities", None)
        insts = [type(a).__name__ for a in collect_triggered_abilities(cap_g["state"])
                 if isinstance(a, StormboyzStrikeTeleportAbility)]
        print("[%s] passives MESUREES ctrl=%s graft=%s | registre du port -> %s"
              % (tag, pas_c, pas_g, insts or "AUCUNE INSCRIPTION"))
        out["passivesControl"], out["passivesGraft"] = pas_c, pas_g
        out["registered"] = insts

        # --- E1 : l'etat LIVE des deux cotes ---------------------------------------------------
        t_ctrl = terms(cap_c["state"], uid_c)
        t_graft = terms(cap_g["state"], uid_g)
        print("[%s] E1 live TEMOIN %s" % (tag, json.dumps(t_ctrl)))
        print("[%s] E1 live GREFFE %s" % (tag, json.dumps(t_graft)))
        out["liveControl"], out["liveGraft"] = t_ctrl, t_graft

        # --- CONFRONT : le PORT applique a l'etat TEMOIN --------------------------------------
        # ⚠ RECONSTITUTION DE L'ENTREE. Le natif tire son trigger a l'INIT des abilities, AVANT le
        # premier `StartTurnOperation`. Le premier etat LISIBLE d'un runner est posterieur : mesure
        # 2026-08-01, le porteur y a deja `GetStat(0xc = TURNS_STARTED) == 1` (l'adversaire, dont le
        # tour n'a pas commence, est a 0). Le gate `AmountIsEqual(UnitTurnsStarted, Direct(0))`
        # refuse donc sur l'etat capture -- et ce REFUS est lui-meme une mesure (c'est ce qui empeche
        # l'ability de re-tirer). On remet le compteur a 0 pour rejouer l'entree du trigger.
        from engine.runner.operations.triggers.base import TriggerEvent
        from engine.dsl.event_trigger_type import EventTriggerType
        from engine.entities.stats import StatType
        from engine.runner.components import StatsComponent as _SC
        ab = StormboyzStrikeTeleportAbility(uid_c)
        ev = TriggerEvent(int(EventTriggerType.AbilityInit), uid_c, uid_c,
                          ranged=False, profile=None)
        ts_live = int(((cap_c["state"].get_entity(uid_c).get_component(_SC)).ctx
                       .stat(StatType.TURNS_STARTED)) or 0)
        out["turnsStartedLive"] = ts_live
        out["gateOnCapturedState"] = bool(ab.matches(cap_c["state"], ev))
        print("[%s] CONFRONT etat capture : turnsStarted=%d -> matches=%s (gate natif "
              "UnitTurnsStarted==0)" % (tag, ts_live, out["gateOnCapturedState"]))
        cap_c["state"].get_entity(uid_c).get_component(_SC).ctx.stats.increment_base(
            int(StatType.TURNS_STARTED), -ts_live)
        matched = ab.matches(cap_c["state"], ev)
        res = ab.execute_behaviour(cap_c["state"], ev) if matched else None
        t_port = terms(cap_c["state"], uid_c)
        print("[%s] CONFRONT entree rejouee : matches=%s res=%s" % (tag, matched, json.dumps(res)))
        print("[%s] CONFRONT port   %s" % (tag, json.dumps(t_port)))
        agree = (t_port["pos"] == t_graft["pos"] and t_port["feet"] == t_graft["feet"]
                 and t_port["alive"] == t_graft["alive"]
                 and t_port["effects"] == t_graft["effects"])
        print("[%s] CONFRONT => %s" % (tag, "ACCORD" if agree else "DESACCORD"))
        out["portAfter"], out["confrontAgree"] = t_port, bool(agree)

        # --- E3 : contre-epreuves du GATE (offline, sur l'etat temoin deja mute) ---------------
        from engine.runner.components import set_moved_flag
        ab2 = StormboyzStrikeTeleportAbility(uid_c)
        out["gateWrongActor"] = bool(ab2.matches(
            cap_c["state"], TriggerEvent(int(EventTriggerType.AbilityInit), uid_c + 1, uid_c + 1,
                                         ranged=False, profile=None)))
        set_moved_flag(cap_c["state"], uid_c)
        out["gateMoved"] = bool(ab2.matches(cap_c["state"], ev))
        print("[%s] E3 gate : autre acteur -> %s | HasFlag(Moved) -> %s | turnsStarted!=0 -> %s"
              % (tag, out["gateWrongActor"], out["gateMoved"], out["gateOnCapturedState"]))

        # --- E2 : le pool de teleport ----------------------------------------------------------
        nat = native_movable(sid, rid_g, uid_g)
        board_g = cap_g["board"]
        nat_ids = {board_g.id_at(c, r) for (c, r) in nat}
        nat_ids.discard(None)
        pools, occ, ptype, family = port_teleport_pools(cap_g["state"], board_g, uid_g, team)
        walk = {int(t) for t in board_g.by_id if board_g.walkable(int(t))}
        stormboyz = family == "StormboyzStrike"
        print("[%s] E2 pathfinder du port = type %d (famille %s) -> %s"
              % (tag, ptype, family or "(aucune)",
                 "montage VALIDE pour le front 2" if stormboyz
                 else "MONTAGE CONFONDU : un effet de rang superieur gagne l'ordre des tests"))
        print("[%s] E2 natif=%d tuiles | board=%d | walkable=%d | occupees=%d"
              % (tag, len(nat_ids), len(board_g.by_id), len(walk),
                 sum(1 for v in occ.values() if v is not None)))
        for name, pool in pools.items():
            print("[%s] E2 port[%-16s]=%-4d  extra=%-4d  missing=%-4d  %s"
                  % (tag, name, len(pool), len(pool - nat_ids), len(nat_ids - pool),
                     "== NATIF" if pool == nat_ids else ""))
        for name in ("stormboyz_true", "teleport_strike"):
            d = pools[name]
            if d != nat_ids:
                print("[%s] E2 diff(%s) extra=%s missing=%s"
                      % (tag, name, sorted(board_g.coord(t) for t in (d - nat_ids)),
                         sorted(board_g.coord(t) for t in (nat_ids - d))))
        out["nativePool"] = len(nat_ids)
        out["pathfinderType"], out["family"], out["front2Valid"] = ptype, family, stormboyz
        out["pools"] = {k: {"n": len(v), "extra": len(v - nat_ids), "missing": len(nat_ids - v),
                            "equal": v == nat_ids} for k, v in pools.items()}
    finally:
        for rid, sf in ((rid_c, sf_c), (rid_g, sf_g)):
            rpc(sid, "disposeRunner", {"runnerId": rid}, 45)
            sf.unlink(missing_ok=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=None, help="un seul board (defaut : les deux du plan)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--graft", default=None, help="un seul greffon (defaut : les deux)")
    ap.add_argument("--offline", action="store_true", help="volet A seul")
    a = ap.parse_args()

    volet_a()
    if a.offline:
        return 0
    plan = list(PLAN)
    if a.graft or a.board or a.seed:
        plan = [(a.board or "MC1_67", a.seed or 777, a.graft or "orksNob", ["ultraTitus"], "ad hoc")]
    sid = _resolve_session()
    results = []
    for i, (b, s, g, foes, note) in enumerate(plan):
        print("\n=== montage %d/%d : board=%s seed=%s greffon=%s adverses=%s [%s] ==="
              % (i + 1, len(plan), b, s, g, ",".join(foes), note))
        r = run_pair(sid, s, b, g, foes, "%s_%s_%d" % (g, b, len(foes)))
        r["note"] = note
        results.append(r)
    print("\n== SYNTHESE ==")
    print("   %-18s %-8s %-6s %-8s %-8s %-7s %-7s %-7s %s"
          % ("greffon", "board", "nFoes", "confront", "pfType", "natif", "true", "==", "teleStrike"))
    for r in results:
        p = r.get("pools") or {}
        print("   %-18s %-8s %-6d %-8s %-8s %-7s %-7s %-7s %s"
              % (r.get("graft"), r.get("board"), len(r.get("foes") or []),
                 r.get("confrontAgree"),
                 "%s/%s" % (r.get("pathfinderType"), r.get("family") or "-"),
                 r.get("nativePool"),
                 (p.get("stormboyz_true") or {}).get("n"),
                 (p.get("stormboyz_true") or {}).get("equal"),
                 (p.get("teleport_strike") or {}).get("n")))
    print("   (les montages dont la famille n'est pas StormboyzStrike ne confrontent PAS le "
          "predicat -- ils mesurent l'ORDRE des tests de GetPathfinderTypeForUnit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
