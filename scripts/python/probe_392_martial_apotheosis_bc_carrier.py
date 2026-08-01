"""Probe #392 -- `MartialApotheosis` (1045) EST-ELLE MONTEE en bataille, oui ou non ?

CONTEXTE. Le tripwire d'inertie `test_ma_inertia_tripwire_no_carrier` rougit sur `master` :
`dispatch=['MartialApotheosis']` alors que le gameconfig ne l'accorde plus a `necroOverlord`.
Le probe #354 avait conclu « 0 porteur » en balayant le GAMECONFIG et le `decisionView` -- deux
canaux qui ne disent RIEN du montage reel. Le natif ne lit pas le gameconfig :
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` enumere
`UnitConfiguration.PassiveAbilities` (`config+0xa8`) et appelle
`IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, passiveAbilityState, 2)`.
La source du montage est donc `BattleConfiguration.Units[].PassiveAbilities`, pas le kit.

CE QUE CE PROBE MESURE, sans rien supposer :

  ETAGE 1 (offline, seed BC) -- `data/seed-bc.json` : quelles unites portent `PassiveAbilities`
      contenant 1045 ? C'est la SOURCE que `rl_duel build` donne au jeu.
  ETAGE 2 (offline, gameconfig) -- les 4 voies d'attribution du kit, pour memoire : c'est ce que
      #354 mesurait, et ce que le port ne lit PLUS depuis #366-r1.
  ETAGE 3 (live) -- monte un runner et lit le `TriggeredAbilityComponent` REEL du porteur via le
      RPC `unitAbilityStates` (entrees `raw[10] == 2` = hierarchie Passive). C'est la MESURE du
      montage natif : ni une derivation, ni un kit expose, le composant ECS lui-meme.
  ETAGE 4 (live) -- CONFRONTATION : un ennemi drive en anneau-1, `endturn` vers le turn-start du
      porteur, et on lit le HP delta. Le NATIF tire-t-il l'ability ? C'est la seule question qui
      tranche « port sur-permissif » contre « tripwire perime ».
  ETAGE 5 (live) -- ATTRIBUTION du degat de l'etage 4, par CONTRASTE GEOMETRIQUE. `case-354` §3
      objectait, a juste titre, qu'un `delta > 0` n'attribue rien : n'importe quelle source de
      degat le satisfait. On rejoue donc le MEME montage avec l'ennemi drive a distance **2** --
      hors de l'anneau-1 de `DestroyerHiveAbility$$GetValidTargets`, et de lui seul. Un delta nul
      a d=2 et non nul a d=1 ATTRIBUE le degat a une source dont la portee est l'anneau-1.

Usage : python probe_392_martial_apotheosis_bc_carrier.py [--no-live]
ASCII only (console cp1252).
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8765"
ABILITY = "MartialApotheosis"
ABILITY_ID = 1045
CARRIER = "necroOverlord"
ENEMIES = "necroWarden,eldarRanger,eldarAutarch"
PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_probe392_ma_bc_carrier.json"     # SORTIE -> logs/ (#349)
SEED_BC = ROOT / "data" / "seed-bc.json"                              # ENTREE versionnee

VOIES = ("passiveAbilities", "activeAbilities", "relicAbilities", "mythicAbilities")
PASSIVE_HIERARCHY = 2


def etage1() -> list:
    """Porteurs de 1045 dans `BC.Units[].PassiveAbilities` -- la SOURCE du montage natif."""
    print("=== ETAGE 1 -- seed BC (`data/seed-bc.json`), la source que le natif MONTE ===")
    bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
    units = bc.get("Units") or []
    porteurs = [u for u in units
                if ABILITY_ID in (u.get("PassiveAbilities") or [])]
    print("  BC.Units : %d" % len(units))
    print("  porteurs de PassiveAbilities contenant %d : %d" % (ABILITY_ID, len(porteurs)))
    for u in porteurs:
        print("     %-20s PassiveAbilities=%s" % (u.get("VisualId"), u.get("PassiveAbilities")))
    if not porteurs:
        print("     (AUCUN -- le BC ne monte pas l'ability)")
    return porteurs


def etage2() -> dict:
    """Les 4 voies du GAMECONFIG -- ce que #354 mesurait, et ce que le port ne lit plus (#366-r1)."""
    print("=== ETAGE 2 -- gameconfig (kit), pour memoire ===")
    import gameconfig as GC
    gu = GC.unit(CARRIER) or {}
    hits = {v: (gu.get(v) or []) for v in VOIES if ABILITY in (gu.get(v) or [])}
    print("  gameconfig.unit(%s).passiveAbilities = %s" % (CARRIER, gu.get("passiveAbilities")))
    print("  voies nommant %s : %s" % (ABILITY, hits or "AUCUNE"))
    print("  -> le gameconfig NE MONTE RIEN : le natif enumere BC.Units[].PassiveAbilities")
    print("     (`UnitFactory$$AddConfiguredAbilities` -> `TriggeredAbilityComponent$$TryAdd(id, _, 2)`)")
    return hits


def _sid() -> int:
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=10) as r:
        return json.loads(r.read())["session"]["id"]


def _rpc(sid: int, method: str, body: dict, timeout: int = 90):
    payload = json.dumps({"method": method, "args": [body]}).encode()
    req = urllib.request.Request(HOST + "/api/scripts/%d/rpc" % sid, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return out.get("result", out)


def _build(sid: int) -> str | None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "4321", "--state-file", str(STATE),
         "--board", "MC1_67", "--p-units", ENEMIES, "--a-units", CARRIER, "--hp-player", "500000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("  build runner KO : %s" % ((proc.stderr or proc.stdout or "")[-400:]))
        return None
    return json.loads(STATE.read_text())["runnerId"]


def _confront(sid: int, want_dist: int, with_etage3: bool) -> int | None:
    """Monte un runner, drive UN ennemi a distance `want_dist` du porteur, `endturn` vers son
    turn-start, et rend le DELTA HP TOTAL sur les ennemis (None si le montage n'a pas pu etre
    obtenu). `with_etage3` ajoute la lecture du `TriggeredAbilityComponent` reel."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state, live_rpc
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    from engine.entities.triggered_ability_type import TriggeredAbilityType

    rid = _build(sid)
    if rid is None:
        return None
    print("  runner %s (cible driven a d=%d)" % (rid, want_dist))
    rpc = lambda m, b=None, t=90: _rpc(sid, m, dict(b or {}, runnerId=rid), t)   # noqa: E731
    try:
        dv = rpc("decisionView", {"allAbilities": True}, 150)
        ov = next((u for u in (dv.get("units") or []) if u.get("visualId") == CARRIER), None)
        if ov is None:
            print("  %s absent du build -- non mesure" % CARRIER)
            return None
        oid = ov["id"]
        bg = rpc("boardGraph", {}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        ob = rpc("observeBattle", {}, 60)

        if with_etage3:
            print("=== ETAGE 3 -- TriggeredAbilityComponent REEL (RPC `unitAbilityStates`) ===")
            uas = rpc("unitAbilityStates", {}, 60)
            su = next((u for u in (uas.get("units") or [])
                       if oid in (u.get("entityId"), u.get("squadId"), u.get("unitId"), u.get("id"))),
                      None)
            if su is None:
                print("  capteur MUET pour e%s (cles vues : %s)"
                      % (oid, sorted((uas.get("units") or [{}])[0].keys())))
            else:
                passives = []
                for t in (su.get("triggered") or []):
                    raw = t.get("raw") or []
                    if len(raw) > 10 and raw[10] == PASSIVE_HIERARCHY:
                        try:
                            passives.append("%d=%s" % (int(raw[0]),
                                                       TriggeredAbilityType(int(raw[0])).name))
                        except ValueError:
                            passives.append("%d=<hors enum>" % int(raw[0]))
                print("  hierarchie 2 (Passive) montee sur %s : %s" % (CARRIER, passives or "AUCUNE"))
                print("  -> %d monte : %s"
                      % (ABILITY_ID,
                         "OUI" if any(p.startswith("%d=" % ABILITY_ID) for p in passives) else "NON"))
            snap = rpc("combatSnapshot", {}, 90)
            with live_rpc(rpc):
                state = load_state(dv, ob, snap, board=board)
            print("  ability_states_seed = %s" % (state.ability_states_seed,))
            ported = [type(x).__name__ for x in collect_triggered_abilities(state)
                      if getattr(x, "owner_id", None) == oid]
            print("  ability-triggers instancies par le PORT pour %s : %s"
                  % (CARRIER, ported or "AUCUN"))

        ov_player, cur = ov.get("owner"), dv.get("currentPlayer")
        if cur == ov_player:
            print("  build demarre au tour du porteur -- endturn INTO son turn-start impossible")
            return None
        om = {u.get("squadId"): u for u in (ob.get("units") or [])}
        ovp = om.get(oid)
        if ovp is None:
            print("  porteur absent d'observeBattle -- non mesure")
            return None
        opos = (ovp.get("col"), ovp.get("row"))
        foes = [u for u in (ob.get("units") or [])
                if u.get("teamId") != ovp.get("teamId") and not u.get("isDead")
                and u.get("col") is not None]
        if not foes:
            print("  aucun ennemi vivant -- non mesure")
            return None
        occupied = {board.id_at(u.get("col"), u.get("row")) for u in om.values()
                    if u.get("col") is not None and not u.get("isDead")}
        otile = board.id_at(*opos)
        cands = [t for t in board.by_id
                 if board.walkable(t) and t not in occupied
                 and hexgeo.distance(opos, board.coord(t)) == want_dist]
        if not cands:
            print("  aucune tuile libre a d=%d du porteur -- non mesure" % want_dist)
            return None
        fid = foes[0].get("squadId")
        dcol, drow = board.coord(sorted(cands)[0])
        rpc("applyAction", {"action": {"kind": "move", "unitId": fid,
                                       "to": {"col": dcol, "row": drow}}}, 90)
        ob1 = rpc("observeBattle", {}, 60)
        alive1 = [u for u in (ob1.get("units") or [])
                  if u.get("teamId") != ovp.get("teamId") and not u.get("isDead")
                  and u.get("col") is not None]
        dists = {u.get("squadId"): hexgeo.distance(opos, (u.get("col"), u.get("row")))
                 for u in alive1}
        print("  distances ennemis -> porteur apres move : %s" % dists)
        if min(dists.values()) != want_dist:
            print("  montage NON obtenu (min dist %s != %d) -- non mesure"
                  % (min(dists.values()), want_dist))
            return None
        hp0 = {u.get("squadId"): u.get("hp") for u in alive1}
        rpc("applyAction", {"action": {"kind": "endturn"}, "captureEvents": True}, 90)
        ob2 = rpc("observeBattle", {}, 60)
        hp1 = {u.get("squadId"): u.get("hp") for u in (ob2.get("units") or [])}
        delta = sum((hp0[k] - hp1.get(k, hp0[k])) for k in hp0
                    if hp0[k] is not None and hp1.get(k) is not None)
        print("  hp ennemis %s -> %s | DELTA TOTAL = %s"
              % (hp0, {k: hp1.get(k) for k in hp0}, delta))
        return int(delta)
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
            print("  runner dispose")
        except Exception as exc:
            print("  disposeRunner KO : %s" % exc)


def etage345(sid: int) -> int:
    print("=== ETAGE 3+4 -- montage ANNEAU-1 (d=1) ===")
    d1 = _confront(sid, 1, with_etage3=True)
    print("  -> le NATIF a tire au turn-start du porteur : %s"
          % ("OUI" if (d1 or 0) > 0 else "NON" if d1 is not None else "NON MESURE"))
    print("")
    print("=== ETAGE 5 -- CONTRE-EPREUVE d'ATTRIBUTION : meme montage a d=2 ===")
    d2 = _confront(sid, 2, with_etage3=False)
    print("")
    print("  d=1 delta=%s | d=2 delta=%s" % (d1, d2))
    if d1 is not None and d2 is not None:
        print("  -> source de portee ANNEAU-1 : %s"
              % ("OUI (degat a d=1, AUCUN a d=2)" if d1 > 0 and d2 == 0
                 else "NON -- le degat n'est pas attribuable a l'anneau-1"))
    return 0


def main() -> int:
    etage1()
    print("")
    etage2()
    print("")
    rc = 0
    if "--no-live" not in sys.argv:
        rc = etage345(_sid())
    print("")
    print("=== VERDICT ===")
    print("  Le montage natif se lit dans le BC + le TriggeredAbilityComponent, JAMAIS dans le kit")
    print("  gameconfig ni dans `decisionView.units[].abilities` (qui n'expose pas les passifs).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
