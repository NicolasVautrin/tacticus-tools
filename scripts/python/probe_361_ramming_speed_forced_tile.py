"""probe #365 -- l'arbre `GetTileToMoveTo()` rend-il VIDE, ou une tuile ISOLEE ? (residu #361-r1)

L'AMBIGUITE QUE CE PROBE LEVE
-----------------------------
`probe_361_adjacent_units_selector.py` a MESURE (3/3 bras exacts) que la composition
`AdjacentUnits(origin, 1, 3)`, la `op_Subtraction`, `TargetsSelector$$SelectUniqueUnits(ctx, 3)` et
le contexte de `ComparablePlaybook<T>$$GenerateAttackPredictions` sont TOUS operants : avec un
`origin` SIMPLE (`Target@0x60`), `ExplosivePresentsPlaybook` emet la cible ET ses deux voisins, et
retire le caster quand il est lui-meme adjacent.

Reste alors DEUX causes possibles au vide des batchs 3/4 de `RammingSpeed`, et elles donnent le
MEME compte d'events -- donc l'une ne se conclut pas de l'autre :

  (B1) l'arbre `RammingSpeedAbility$$GetTileToMoveTo()` rend un ensemble VIDE dans le contexte du
       playbook (un maillon -- `MovableTilesInRange`, `CanAddUnit`, `SortTilesByUtility`, `First` --
       ne rend rien) ;
  (B2) il rend UNE tuile, mais PAS celle que le combat choisit, et cette tuile-la n'a aucun voisin.

MONTAGE QUI LES SEPARE : SATURER LE RING
----------------------------------------
On entoure la cible de QUATRE unites (2 amies du caster, 2 ennemies), sur quatre des six voisins.
Le pool de charge de `GetTileToMoveTo` est alors reduit aux DEUX voisins libres restants -- et,
dans un hexagone, deux voisins consecutifs du ring se touchent : CHAQUE tuile encore candidate
porte donc au moins un voisin OCCUPE. Le probe le VERIFIE tuile par tuile au lieu de le supposer.

=> sous ce montage, (B2) devient IMPOSSIBLE : quelle que soit la tuile que l'arbre designe, son
   voisinage est peuple, donc les batchs 3/4 DEVRAIENT emettre. S'ils n'emettent toujours pas,
   c'est (B1) : l'arbre rend VIDE.

Le probe REFUSE de conclure si le montage ne tient pas (gate fermee, ring non sature, une candidate
sans voisin occupe) -- il l'ECRIT au lieu de compter un accord sans valeur.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_361_ramming_speed_forced_tile.py
    python probe_361_ramming_speed_forced_tile.py --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402
from probe_353_ramming_speed_prediction import build_grafted_seed_bc     # noqa: E402
from probe_353r1_ramming_speed_charge_tile import (                      # noqa: E402
    MOVE_RANGE, _pos, _view, drive_to)
from probe_361_ramming_speed_explosion_batches import _gate_verdict      # noqa: E402

ABILITY = 1059
BOARD = "MC1_67"
GRAFT = "orksKillaKan"                       # le caster greffe (#353, case-92 sec.5bis)
ALLIES = ["astraBullgryn", "adeptCanoness"]  # amis du caster, POSES sur le ring de la cible
VICTIM = "necroWarden"                       # la cible
ENEMIES = ["ultraTitus", "admecDestroyer"]   # ennemis, POSES sur le ring de la cible
# PV du camp JOUEUR : le 2e batch est un recul qui frappe le caster ; la gate
# `Any(selfPreds, p => p.WillBeKill)` doit OUVRIR, sinon le probe ne teste rien (il le dit).
HP_PLAYER = 60


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed_bc: Path, seed: int, level: int) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", BOARD, "--rank", "17",
           "--seed-bc", str(seed_bc),
           "--p-units", ",".join([GRAFT] + ALLIES),
           "--a-units", ",".join([VICTIM] + ENEMIES),
           "--unit-stat", "%s:ActiveAbilityLevel=%d" % (GRAFT, level),
           "--hp-player", str(HP_PLAYER),
           "--crit", "0,0", "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1400:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _view(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dv, ob, snap, board=board), board, dv


def _ids(dv) -> dict:
    out = {}
    for v in [GRAFT, VICTIM] + ALLIES + ENEMIES:
        u = next((x for x in (dv.get("units") or []) if x.get("visualId") == v and x.get("alive")),
                 None)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        out[v] = int(u["id"])
    return out


def scan_saturated(board, caster_pos, max_targets: int = 60):
    """Cible a 6 voisins marchables ; QUATRE d'entre eux recoivent une unite, DEUX restent libres.
    Caster hors du ring, a portee de charge (`MOVE_RANGE`), et LE PLUS PRES POSSIBLE de son spawn :
    une destination lointaine ne se drive pas en un nombre de tours borne (mesure du 1er jet -- le
    caster restait a (6,2) pour un voulu (6,7), les quatre unites du ring etant, elles, en place)."""
    walk = sorted(board.coord(t) for t in board.by_id if board.walkable(t))
    if not walk:
        return None
    cc = (sum(p[0] for p in walk) / float(len(walk)), sum(p[1] for p in walk) / float(len(walk)))
    six = [t for t in board.by_id
           if board.walkable(t) and len(board.neighbours(t)) == 6
           and all(board.walkable(n) for n in board.neighbours(t))]
    six.sort(key=lambda t: (abs(board.coord(t)[0] - cc[0]) + abs(board.coord(t)[1] - cc[1]), t))
    for tt in six[:max_targets]:
        tp = board.coord(tt)
        ring = sorted(board.coord(n) for n in board.neighbours(tt))
        occupied, free = ring[:4], ring[4:]
        cands = sorted((p for p in walk
                        if p != tp and p not in ring and 2 <= hexgeo.distance(p, tp) <= MOVE_RANGE),
                       key=lambda p: (hexgeo.distance(p, tuple(caster_pos)), p))
        caster = cands[0] if cands else None
        if caster is None:
            continue
        return {"target": tp, "occupied": occupied, "free": free, "caster": caster}
    return None


def _team_of(dv, uid):
    for u in (dv.get("units") or []):
        if int(u.get("id")) == int(uid):
            return u.get("team")
    return None


def movable_count(sid, rid, uid) -> int:
    """Nombre de tuiles que `aiMovableTiles` donne a `uid` -- le pendant RPC de la query que
    `MovableTilesInRangeSelector$$Select` delegue a
    `IBattleQuery.GetMovableTilesInRange(unit, fromTile, ignoreFlags, options)`. Zero = l'arbre
    `GetTileToMoveTo` ne peut structurellement rien rendre."""
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60) or {}
    for mu in (mov.get("units") or []):
        if int(mu.get("unitId") or -1) == int(uid):
            return len(mu.get("tiles") or [])
    return -1          # l'unite n'est meme pas listee : elle n'a pas la main


def hand_back_to(sid, rid, uid, max_turns: int = 8) -> dict:
    """Rend la main jusqu'a ce que `uid` figure dans `aiMovableTiles` (= c'est son tour).

    POURQUOI ce bras existe : `drive_to` termine par un `endturn`, donc la mesure qui suit tombe
    pendant le tour ADVERSE. Or `IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select`
    delegue a `IBattleQuery.GetMovableTilesInRange(unit, fromTile, ignoreFlags, options)` avec
    `ignoreFlags = 0` -- le litteral que `RammingSpeedAbility$$GetTileToMoveTo` passe -- donc la
    query RESPECTE les flags de l'unite. Un caster qui n'a pas la main n'aurait aucune tuile de
    mouvement, et l'arbre rendrait vide POUR UNE RAISON DE MONTAGE, pas de mecanique."""
    from probe_353r1_ramming_speed_charge_tile import _endturn
    for _ in range(max_turns):
        if movable_count(sid, rid, uid) >= 0:
            return _view(sid, rid)
        _endturn(sid, rid)
    return _view(sid, rid)


def _ring_population(board, dv, tile_pos, caster_id):
    """Amis / ennemis VIVANTS sur une tuile hex-adjacente a `tile_pos`, camps RELATIFS au caster.
    C'est exactement ce que `Friends`/`Enemies(Caster, AdjacentUnits(tile, 1, 3), 3)` selectionnent
    (`UnitsFromFactionSelector` PARTITIONNE son entree par `UnitExtensions$$HasFaction`)."""
    units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("alive")}
    cteam = (units.get(int(caster_id)) or {}).get("team")
    tid = board.id_at(tile_pos[0], tile_pos[1])
    ring = {board.coord(n) for n in board.neighbours(tid)} if tid is not None else set()
    fr, en = [], []
    for uid, u in sorted(units.items()):
        p = u.get("pos") or {}
        if (p.get("col"), p.get("row")) not in ring:
            continue
        (fr if u.get("team") == cteam else en).append(
            {"id": uid, "visualId": u.get("visualId"), "pos": [p.get("col"), p.get("row")]})
    return fr, en


def run(seed: int = 36510, level: int = 8, verbose: bool = True) -> dict:
    sid = _resolve_session()
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    sf = logs / ("p365f-%s.json" % tag)
    bcf = logs / ("p365f-seed-bc-%s.json" % tag)
    out: dict = {"seed": seed, "level": level, "board": BOARD}
    out["graft"] = build_grafted_seed_bc(bcf, graft=GRAFT, ability_id=ABILITY,
                                         ability_name="RammingSpeed")
    rid = None
    try:
        rid = _build(sf, bcf, seed, level)
        out["runner"] = rid
        state, board, dv = _load(sid, rid)
        ids = _ids(dv)
        geo = scan_saturated(board, _pos(dv, ids[GRAFT]))
        if geo is None:
            out["error"] = "aucune cible a 6 voisins marchables sur %s" % BOARD
            return out
        out["geometry"] = {"target": list(geo["target"]), "caster": list(geo["caster"]),
                           "occupied": [list(p) for p in geo["occupied"]],
                           "free": [list(p) for p in geo["free"]]}
        ring_w = {ids[VICTIM]: geo["target"]}
        for v, p in zip(ALLIES + ENEMIES, geo["occupied"]):
            ring_w[ids[v]] = p
        wanted = dict(ring_w)
        wanted[ids[GRAFT]] = geo["caster"]
        drive_to(sid, rid, ring_w)
        if not drive_to(sid, rid, wanted):
            dv = _view(sid, rid)
            out["error"] = ("drive KO : voulu %s obtenu %s"
                            % ({k: list(v) for k, v in wanted.items()},
                               {u: _pos(dv, u) for u in wanted}))
            return out
        state, board, dv = _load(sid, rid)
        caster, target = ids[GRAFT], ids[VICTIM]

        # --- le POOL reel, derive de l'etat mesure : voisins de la cible encore LIBRES
        taken = {((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                 for u in (dv.get("units") or []) if u.get("alive")}
        tp = _pos(dv, target)
        tid = board.id_at(tp[0], tp[1])
        ring = sorted(board.coord(n) for n in board.neighbours(tid))
        pool = [p for p in ring if p not in taken and board.walkable(board.id_at(*p))]
        out["pool"] = [list(p) for p in pool]
        pop = {}
        for p in pool:
            fr, en = _ring_population(board, dv, p, caster)
            pop[str(list(p))] = {"friends": [x["visualId"] for x in fr],
                                 "enemies": [x["visualId"] for x in en],
                                 "n": len(fr) + len(en)}
        out["pool_population"] = pop
        out["min_pool_population"] = min([v["n"] for v in pop.values()], default=0)

        # --- la tuile que le PORT designe (confronte 2/2 au natif par cast reel, #353-r1 volet a)
        from engine.runner.abilities.orks import ramming_speed_tile_to_move_to
        t_port = ramming_speed_tile_to_move_to(state, caster, target, MOVE_RANGE)
        out["tile_port"] = list(t_port) if t_port else None

        def _shot(tag):
            nat = _r(sid, "aiPlaybookPredict",
                     {"runnerId": rid, "unitId": caster, "targetId": target,
                      "abilityType": ABILITY, "gateProbe": True}, 120)
            rows = [{"targetId": e.get("targetId"), "hpBefore": e.get("hpBefore"),
                     "healthDmgMin": e.get("healthDmgMin"), "appliedHits": e.get("appliedHits"),
                     "willBeKill": e.get("willBeKill"), "willKillDmg": e.get("willKillDmg")}
                    for e in (nat.get("events") or [])]
            self_ev = next((r for r in rows if r["targetId"] == caster), None)
            gk, gp = _gate_verdict(nat.get("gateProbe"))
            return {"tag": tag, "events": rows, "n_events": len(rows),
                    "playbook": nat.get("playbookClass"), "native_error": nat.get("error"),
                    "gate_kind": gk, "gate_phrase": gp,
                    "gate_open": ((self_ev or {}).get("willBeKill") is True)}

        # (a) TEL QUEL : `drive_to` a fini par un `endturn`, on est donc dans le tour ADVERSE.
        out["team_caster"] = _team_of(dv, caster)
        out["movable_a"] = movable_count(sid, rid, caster)
        shot_a = _shot("tour-adverse")
        shot_a["movable"] = out["movable_a"]
        # (b) MAIN RENDUE AU CASTER : seul facteur qui change entre (a) et (b).
        hand_back_to(sid, rid, caster)
        out["movable_b"] = movable_count(sid, rid, caster)
        shot_b = _shot("tour-caster")
        shot_b["movable"] = out["movable_b"]
        out["shots"] = [shot_a, shot_b]
        # Le verdict porte sur le bras ou le caster a EFFECTIVEMENT des tuiles de mouvement : c'est
        # le seul ou la query ne peut pas etre neutralisee par le montage.
        chosen = shot_b if out["movable_b"] > 0 else shot_a
        out["chosen_shot"] = chosen["tag"]
        out.update({k: chosen[k] for k in ("events", "n_events", "playbook", "native_error",
                                           "gate_kind", "gate_phrase", "gate_open")})
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sf.unlink(missing_ok=True)
        bcf.unlink(missing_ok=True)

    # --- VERDICT DERIVE DES CHAMPS
    if out.get("error"):
        out["ok"] = False
        out["verdict"] = "MONTAGE KO : %s" % out["error"]
    elif out.get("native_error"):
        out["ok"] = False
        out["verdict"] = "NATIF EN ERREUR : %s" % out["native_error"]
    elif not out.get("gate_open"):
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : la gate n'est pas ouverte -- baisser "
                          "`HP_PLAYER`. %s" % out.get("gate_phrase"))
    elif not out.get("pool"):
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : le ring est SATURE a 6/6, il ne reste aucune "
                          "tuile de charge -- le natif n'aurait rien a designer.")
    elif max(out.get("movable_a", -1), out.get("movable_b", -1)) <= 0:
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : le caster n'a AUCUNE tuile de mouvement "
                          "(aiMovableTiles a=%s b=%s), donc `MovableTilesInRange` rendrait vide "
                          "quel que soit le contexte -- le montage, pas la mecanique."
                          % (out.get("movable_a"), out.get("movable_b")))
    elif out.get("min_pool_population", 0) < 1:
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : une tuile du pool %s n'a AUCUN voisin occupe "
                          "-- (B2) « l'arbre designe une tuile isolee » reste possible, donc un "
                          "compte de 2 ne conclurait rien." % out.get("pool_population"))
    elif out.get("n_events", 0) > 2:
        out["ok"] = True
        out["verdict"] = ("BATCHS 3/4 EMIS (%d events) : l'arbre `GetTileToMoveTo()` rend bien une "
                          "tuile dans le contexte du playbook. Le vide mesure ailleurs venait donc "
                          "de la TUILE DESIGNEE (voisinage vide), pas de l'arbre."
                          % out["n_events"])
    else:
        out["ok"] = True
        out["verdict"] = (
            "ARBRE VIDE : %d events alors que CHAQUE tuile encore candidate (%s) porte au moins "
            "%d unite(s) adjacente(s) (%s) et que la gate est OUVERTE. Aucune tuile du pool ne "
            "pouvait donner un voisinage vide => "
            "`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo` "
            "rend un ensemble VIDE quand il est evalue dans le contexte de "
            "`IdunBattle.AI.Playbook.ComparablePlaybook<T>$$GenerateAttackPredictions`, alors que "
            "le MEME arbre rend une tuile dans celui de "
            "`RammingSpeedAbility$$GetDynamicInvalidTargetReason` (cast reel : MATCH 2/2, #353-r1)."
            % (out.get("n_events"), out.get("pool"), out.get("min_pool_population"),
               out.get("pool_population")))

    if verbose:
        print("[365f] runner=%s playbook=%s geo=%s"
              % (out.get("runner"), out.get("playbook"), json.dumps(out.get("geometry"))))
        for s in out.get("shots") or []:
            print("       tir[%s] movable=%s events=%s gate_ouverte=%s erreur=%s"
                  % (s.get("tag"), s.get("movable"), s.get("n_events"), s.get("gate_open"),
                     s.get("native_error")))
        print("       team_caster=%s retenu=%s" % (out.get("team_caster"), out.get("chosen_shot")))
        print("       pool=%s population=%s min=%s tuile_port=%s"
              % (out.get("pool"), json.dumps(out.get("pool_population")),
                 out.get("min_pool_population"), out.get("tile_port")))
        print("       events natifs=%s gate_ouverte=%s erreur=%s"
              % (out.get("n_events"), out.get("gate_open"), out.get("native_error")))
        for r in out.get("events") or []:
            print("       %s" % json.dumps(r, sort_keys=True))
        print("       capteur gate [%s] : %s" % (out.get("gate_kind"), out.get("gate_phrase")))
        print("[365f] %s" % out.get("verdict"))
        print("[365f] -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=36510)
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, level=a.level, verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
