#!/usr/bin/env python
"""probe #406 -- CONFRONTATION LIVE du DEPLACEMENT de `HarlequinsPanoply`.

QUESTION BINAIRE, posee avant la methode : **apres une attaque A DISTANCE dont un coup est bloque,
le NATIF rapproche-t-il le porteur d'EXACTEMENT un hex de l'attaquant ?**

C'est le pendant observable de la RE de #406 : le `TriggerAbilityDelayed(Owner, 0x4a3, 3)` de la
branche `On(0x3c = UnitBlocked)` de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
HarlequinsPanoplyAbility$$CreateBehaviour` ENFILE (`IdunBattle.Core.MatchState$$
AddPendingTriggeredAbility`), et le drain -- `IdunBattle.Messages.InputMessageProcessor$$
ProcessPendingTriggeredAbilities`, appele par `RunPhase` APRES le retour de `action()` -- rejoue
l'ability avec `triggerType = 0x20 = Custom`, dont l'arbre est
`Inform(0xb6) + If(NOT IsAdjacent(Owner, Caster, 3), MoveUnit(Owner, First(SortByDistance(
MovableTilesInRange(Owner, MainTileOfUnits(Owner), Const(1)), Caster))))`.

MONTAGE. Meme greffe que `probe_366r1_harlequins_panoply.py` (le passif n'a que deux porteurs,
`eldarSmnHarlequin` (SUMMON sans summoner de catalogue) et `eldarNpc3Harlequin` (npc)) -- mais
l'attaque doit etre A DISTANCE, sinon le gate `NOT IsAdjacent` est FAUX et rien ne bouge. C'est le
trou du probe #366-r1, qui attaquait au contact.

`necroDestroyer` porte DEUX profils (`unit_map` : `6hmp60` melee ET `6hR2p60` ranged portee 2) : on
le place a distance 2 du greffon, l'attaque part en RANGED, le gate est VRAI, et la tuile d'approche
est libre par construction (il y a au moins un hex entre les deux).

DEUX runners STRICTEMENT identiques (meme seed, meme board, memes rosters, meme `--block-target`),
un seul bit de difference : la greffe. Le chiffre lu est la DISTANCE HEX attaquant-defenseur apres
l'attaque.

Usage (depuis scripts/python, session warmee) :
    python probe_406_harlequins_panoply_move.py --state-file <ABSOLU> [--board MC1_67] [--seed 31337]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
GRAFT = "astraBullgryn"          # defenseur greffe (a-units)
ATTACKER = "necroDestroyer"      # attaquant (p-units) : 6hR2p60 -> attaque RANGED portee 2
ABILITY = "HarlequinsPanoply"
BLOCK = "100,300"                # BlockChance,BlockDamage : block DETERMINISTE, rogne sans annuler
DIST = 2                         # distance de tir : >= 2 pour que `NOT IsAdjacent` soit VRAI


def sid() -> int:
    return int(requests.get(HOST + "/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, s),
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def _run(argv: list, cwd: Path) -> str:
    p = subprocess.run([sys.executable] + argv, cwd=str(cwd), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def _units(s: int, rid: int) -> dict:
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    return {int(u["id"]): u for u in (dv.get("units") or [])}


def _find(units: dict, visual_id: str):
    for uid, u in units.items():
        if u.get("visualId") == visual_id:
            return int(uid), u
    raise RuntimeError("unite %r absente du runner" % (visual_id,))


def _normal_ability_id(units: dict, uid: int) -> int:
    """Id de l'ATTAQUE NORMALE CONCRETE de `uid` (`decisionView.units[].abilities[]`,
    `kind == "normal"`) -- mirror de `rl_duel._normal_ability_map` (TF18).

    #411-r2 : `act ability` SANS `--ability` auto-resolvait depuis `attackPlans`, qui porte une
    entree PAR ABILITY castable sur la cible, et retenait la DERNIERE -- donc l'ACTIVE du
    caster. On la NOMME toujours, et on LEVE si le kind normal manque."""
    u = units.get(int(uid)) or {}
    for ab in (u.get("abilities") or []):
        if ab.get("kind") == "normal" and ab.get("id") is not None:
            return int(ab["id"])
    raise RuntimeError("pas d'ability kind='normal' sur u%s -- ne pas deviner" % (uid,))


def _xy(u):
    p = u.get("pos") or {}
    return (int(p["col"]), int(p["row"]))


def _tile_at_distance(s: int, rid: int, units: dict, target_pos, mover: int, want: int):
    """Tuile LIBRE et marchable a distance hex EXACTE `want` de la cible (jamais « bloque par la
    geometrie de spawn » : on BALAYE tout le plateau)."""
    import hexgeo
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    occupied = {_xy(u) for uid, u in units.items() if u.get("pos") and int(uid) != mover}
    for t in (bg.get("tiles") or []):
        if t.get("walkable") is False:
            continue
        p = (int(t["col"]), int(t["row"]))
        if p in occupied or hexgeo.distance(p, target_pos) != int(want):
            continue
        return p
    raise RuntimeError("aucune tuile libre a distance %d de la cible" % want)


def _port_replay(s: int, rid: int, att: int, dfd: int) -> dict:
    """CONFRONTATION PAR ETAGE : rejoue le MEME etat pre-attaque dans le PORT (chokepoint
    `AttackDamageOperation.execute` + drain `process_pending_triggered_abilities`) et rend la tuile
    finale du porteur. « Le porteur a bouge » ne suffit pas -- ce qu'on compare, c'est la TUILE."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state, bind_live_rpc
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import PositionComponent, StatsComponent
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.triggers.dispatch.pending import (
        process_pending_triggered_abilities)
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    dec = rpc(s, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc(s, "tileMeta", {"runnerId": rid}, 90)
    # TRANSPORT AMBIANT (#363) : sans lui `_auto_ability_states` rend `no-transport`, donc
    # `UnitContext.passive_abilities` reste None et le port RETOMBE sur la derivation gameconfig
    # par `visualId` -- ou la GREFFE n'existe pas. Le passif serait INERTE, sans erreur : le probe
    # rendrait « le port ne bouge pas » pour une raison de HARNAIS, pas de port.
    prev = bind_live_rpc(lambda method, args=None, timeout=60: rpc(s, method, args, timeout))
    try:
        st = load_state(dec, ob, snap, board=Board(bg["tiles"], adjacency="evenq"), tiles=tm)
    finally:
        bind_live_rpc(prev)
    st.rng = IntBasedMersenneTwister(777)
    _sc = st.get_entity(int(dfd)).get_component(StatsComponent)
    carried = list(getattr(_sc.ctx, "passive_abilities", None) or [])
    assert ABILITY in carried, ("le port ne voit PAS la greffe (canal ability_states=%r, "
                                "passives=%r) -- montage casse, pas un verdict"
                                % (getattr(st, "ability_states_seed", None), carried))
    r = AttackDamageOperation.execute(st, int(att), int(dfd), 20)
    out = process_pending_triggered_abilities(st)
    pc = st.get_entity(int(dfd)).get_component(PositionComponent)
    return {"pos": (pc.col, pc.row), "per_hit": list(r.get("per_hit") or []),
            "queued_drained": len(out), "moved": bool(out and out[0].get("moved"))}


def one_run(pydir: Path, state_file: Path, seed_bc, seed: str, board: str, label: str,
            replay_port: bool = False) -> dict:
    import hexgeo
    extra = ["--rank", "17", "--p-units", ATTACKER, "--a-units", GRAFT,
             "--block-target", BLOCK, "--board", board]
    if seed_bc:
        extra = ["--seed-bc", str(seed_bc)] + extra
    _run(["rl_duel.py", "build", "--seed", seed, "--state-file", str(state_file)] + extra, pydir)
    st = json.loads(state_file.read_text(encoding="utf-8"))
    rid = int(st["runnerId"])
    s = sid()
    units = _units(s, rid)
    att, au = _find(units, ATTACKER)
    dfd, du = _find(units, GRAFT)
    dpos0 = _xy(du)
    to = _tile_at_distance(s, rid, units, dpos0, att, DIST)
    _run(["rl_duel.py", "act", "move", "--unit", str(att), "--to", "%d,%d" % to,
          "--state-file", str(state_file)], pydir)
    units1 = _units(s, rid)
    apos = _xy(units1[att])
    dpos1 = _xy(units1[dfd])
    d_before = hexgeo.distance(apos, dpos1)
    port = _port_replay(s, rid, att, dfd) if replay_port else None
    _run(["rl_duel.py", "act", "ability", "--caster", str(att), "--target", str(dfd),
          "--ability", str(_normal_ability_id(units1, att)),          # #411-r2 : jamais implicite
          "--state-file", str(state_file)], pydir)
    units2 = _units(s, rid)
    dpos2 = _xy(units2[dfd])
    d_after = hexgeo.distance(_xy(units2[att]), dpos2)
    rpc(s, "disposeRunner", {"runnerId": rid}, 20)
    return {"label": label, "runner": rid, "attacker": att, "defender": dfd,
            "att_pos": apos, "def_before": dpos1, "def_after": dpos2,
            "dist_before": d_before, "dist_after": d_after,
            "hp_before": int(units1[dfd].get("hp") or 0),
            "hp_after": int(units2[dfd].get("hp") or 0), "port": port}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="31337")
    a = ap.parse_args()
    pydir = Path(__file__).resolve().parent
    sf = Path(a.state_file).resolve()
    sys.path.insert(0, str(pydir))
    import catalog_inject as CI
    import host_inputs                                         # noqa: F401 (garde data/)
    grafted = sf.parent / "panoply406-grafted-bc.json"
    p, reports = CI.write_grafted_seed_bc(str(grafted), ["%s:%s" % (GRAFT, ABILITY)])
    assert reports[0]["abilityId"] == 1187, reports
    assert reports[0]["passiveAbilitiesAfter"] == [1187], reports
    print("[montage] greffe %s:%s -> %s" % (GRAFT, ABILITY, reports[0]))

    ctrl = one_run(pydir, sf, None, a.seed, a.board, "TEMOIN (sans greffe)")
    graf = one_run(pydir, sf, p, a.seed, a.board, "GREFFE (HarlequinsPanoply)", replay_port=True)
    for r in (ctrl, graf):
        print("[%-28s] def u%d  pos %s -> %s   dist %d -> %d   hp %d -> %d"
              % (r["label"], r["defender"], r["def_before"], r["def_after"],
                 r["dist_before"], r["dist_after"], r["hp_before"], r["hp_after"]))
    if ctrl["dist_before"] != DIST or graf["dist_before"] != DIST:
        print("[VERDICT] INDECIS -- le montage n'a pas place l'attaquant a distance %d." % DIST)
        return 2
    if ctrl["def_before"] != ctrl["def_after"]:
        print("[VERDICT] INDECIS -- le TEMOIN a bouge : la position n'isole pas le passif.")
        return 2
    moved = graf["def_before"] != graf["def_after"]
    step = graf["dist_before"] - graf["dist_after"]
    print("[mesure] greffe : deplacement=%s  rapprochement=%d hex" % (moved, step))
    natif_ok = bool(moved and step == 1)
    print("[VERDICT natif] %s" % ("MOVE CONFIRME cote NATIF (1 hex)" if natif_ok
                                  else "PAS de move d'1 hex observe -- le port serait FAUX"))
    port = graf.get("port") or {}
    same = port.get("pos") == graf["def_after"]
    print("[port] tuile finale=%s  natif=%s  per_hit=%s  drained=%s"
          % (port.get("pos"), graf["def_after"], port.get("per_hit"), port.get("queued_drained")))
    print("[VERDICT port] %s" % ("ACCORD PORT/NATIF sur la TUILE" if same
                                 else "DESACCORD sur la tuile -- le port choisit une autre case"))
    return 0 if (natif_ok and same) else 1


if __name__ == "__main__":
    raise SystemExit(main())
