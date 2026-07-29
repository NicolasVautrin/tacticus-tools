#!/usr/bin/env python
"""Probe #224 item 1 -- `CursedPlagueBellMovementAbility` (volet MOUVEMENT du passif
`CursedPlagueBell` 1071 de `deathBlightbringer`/Corrodius). Confrontation LIVE-vs-PORT de la POSE
de l'effet `CursedPlagueBell_ExtraMove` (1073) au debut du tour du porteur.

MECANIQUE PORTEE (RE : cf. l'en-tete de
`engine/runner/operations/triggers/loki/cursed_plague_bell.py`) :
    On(TurnStart_Other=0x13) & OwnerIsActor
      -> AddEffect(1073, turns=1) sur
         UnitsWithoutTrait( UnitsWithTrait( SurroundingFriends(Owner, ContagionsOfNurgleRange(Owner)),
                                            Chaos ), Stationary )

MONTAGE (board MC1_67) -- CINQ cas discriminants sur UN seul plateau, obtenus en DRIVANT les
positions (aucune dependance aux spawns) :
  * `deathPutrifier`  (allie CHAOS)      a distance 1 de Corrodius -> DOIT recevoir 1073
  * `worldJakhal`     (allie CHAOS)      a distance 2                -> ne recoit RIEN tant que le
                                                                        rayon d'aura vaut 1, PUIS
                                                                        recoit des qu'il vaut 2
                                                                        (discriminant de RAYON)
  * `necroWarden`     (allie XENOS)      a distance 1 -> gate `UnitsWithTrait(Chaos)` -> RIEN
  * `astraBullgryn`   (allie IMPERIAL)   a distance 1 -> gate `UnitsWithTrait(Chaos)` -> RIEN
  * `blackTerminator` (ENNEMI Chaos)     a distance 1 -> gate `SurroundingFriends`     -> RIEN
  * Corrodius LUI-MEME                                 -> centre EXCLU (`- Tiles(unit)`) -> RIEN

Le rayon suit `ContagionsOfNurgle_ArmorReduction_Effect$$GetRangeOnOwnerTurn(TurnsStarted)` =
1 (tours 1-2) / 2 (3-4) / 3 (5+). On boucle donc plusieurs cycles d'`endturn` purs (personne ne
bouge) : la geometrie est FIGEE et c'est le RAYON qui change -> `worldJakhal` bascule de RIEN a
1073 au tour ou `TurnsStarted` depasse 2. Un port qui figerait le rayon a 1 (ou a 3) se trahit.

PROTOCOLE par tour de P :
  1. au tour ADVERSE : capture S (`decisionView allAbilities` + `observeBattle` + `combatSnapshot`
     + `boardGraph`) ;
  2. LIVE : `endturn` (A -> P) => `StartTurnOperation` natif => `On(0x13)` => pose ;
     relecture `decisionView` -> ENSEMBLE des porteurs de 1073 ;
  3. PORT : `load_state(S)` + `_bump_turns_started(P)` (mirror de l'incrementation que
     `StartTurnOperation` fait AVANT d'emettre les 5 events) + `turn_start_other_triggers(P)` ->
     ENSEMBLE des porteurs de 1073 dans `state.effects` ;
  4. comparaison d'ENSEMBLES + du rayon.

CONTREFACTUELS (option `--mutate`) : chaque gate est retire a tour de role et la mesure rejouee sur
les MEMES captures -- si un gate ne mord pas, le montage ne le teste pas.

ASCII only (cp1252). Usage :
    python probe_224_cursed_plague_bell.py [--seed 777] [--board MC1_67] [--turns 4] [--mutate]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402
from engine.runner.operations.triggers import turn_start_other_triggers    # noqa: E402
from engine.runner.operations.turnflow import _bump_turns_started          # noqa: E402

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_224_cursed_plague_bell.json"

CARRIER = "deathBlightbringer"          # Corrodius : Chaos + trait ContagionsOfNurgle (l'aura)
FRIEND_CHAOS_NEAR = "deathPutrifier"    # allie Chaos, place a distance 1
FRIEND_CHAOS_FAR = "worldJakhal"        # allie Chaos, place a distance 2 (1er seuil de rayon)
FRIEND_CHAOS_FAR3 = "thousTzaangor"     # allie Chaos, place a distance 3 (2e seuil de rayon)
FRIEND_XENOS = "necroWarden"            # allie NON-Chaos (Xenos), distance 1
FRIEND_IMPERIAL = "astraBullgryn"       # allie NON-Chaos (Imperial), distance 1
ENEMY_CHAOS = "blackTerminator"         # ENNEMI Chaos, distance 1 (gate SurroundingFriends)

EXTRA_MOVE = int(EffectType.CursedPlagueBell_ExtraMove)      # 1073
P_UNITS = [CARRIER, FRIEND_CHAOS_NEAR, FRIEND_CHAOS_FAR, FRIEND_CHAOS_FAR3,
           FRIEND_XENOS, FRIEND_IMPERIAL]
A_UNITS = [ENEMY_CHAOS]
# `visualId de l'allie Chaos` -> distance hex a laquelle on le PLACE (les deux seuils de
# `GetRangeOnOwnerTurn` : rayon 1 tours 1-2, 2 tours 3-4, 3 a partir du tour 5).
FAR_PLACEMENT = {FRIEND_CHAOS_FAR: 2, FRIEND_CHAOS_FAR3: 3}


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(seed, board):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", board,
         "--p-units", ",".join(P_UNITS), "--a-units", ",".join(A_UNITS),
         "--hp-player", "90000", "--hp-target", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[224] build KO:", (proc.stderr or proc.stdout or "")[-600:], file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def dispose(sid, rid):
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception as exc:                                   # pragma: no cover (nettoyage)
        print("[224] dispose KO:", exc, file=sys.stderr)


def dv(sid, rid, all_ab=False, mr=1):
    b = {"runnerId": rid, "maxRank": mr}
    if all_ab:
        b["allAbilities"] = True
    return _r(sid, "decisionView", b, 150 if all_ab else 60)


EXTRA_MOVE_NAME = "CursedPlagueBell_ExtraMove"


def carriers_live(view) -> dict:
    """{id d'unite: `remaining`} des porteurs de 1073 dans `decisionView` (canal `units[].effects`).
    Le `remaining` est le DISCRIMINANT du `turns = Nullable<int>(1)` de l'`AddEffect` natif : un port
    qui aurait lu un `TurnsFromRounds` (ou pas de duree du tout) rendrait une autre valeur."""
    out = {}
    for u in (view.get("units") or []):
        for e in (u.get("effects") or []):
            if e.get("active") is False:
                continue
            if int(e.get("effectType") or -1) == EXTRA_MOVE or e.get("name") == EXTRA_MOVE_NAME:
                out[int(u["id"])] = e.get("remaining")
    return out


def carriers_offline(state) -> dict:
    """{id: `remaining`} des instances ACTIVES de 1073 dans `State.effects` (cote PORT)."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return {}
    return {int(uid): e.remaining_turns          # == `remaining` de decisionView (None = permanent)
            for uid, lst in eff.by_unit.items()
            for e in lst if (not e.consumed) and int(e.effect_type) == EXTRA_MOVE}


def move(sid, rid, uid, col, row):
    _r(sid, "applyAction",
       {"runnerId": rid, "actions": [{"kind": "move", "unitId": uid, "to": {"col": col, "row": row}}]}, 60)


def endturn(sid, rid):
    _r(sid, "applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 90)


def _hub_tile(bg):
    """Une tuile jouable a SIX voisins jouables -- le spawn de Corrodius est en COIN (3 voisins) sur
    MC1_67, ce qui SOUS-EXERCERAIT le voisinage (cf. runner.md : « si ta mecanique compte des
    voisins, exige explicitement une tuile a 6 voisins »). On prend celle du milieu de la liste
    (loin des bords)."""
    by_id = {t["id"]: t for t in bg["tiles"]}
    cands = []
    for t in bg["tiles"]:
        if not t.get("walkable") or t.get("isWall"):
            continue
        good = [n for n in (t.get("neighbours") or [])
                if n in by_id and by_id[n].get("walkable") and not by_id[n].get("isWall")]
        if len(good) >= 6:
            cands.append(t)
    return cands[len(cands) // 2] if cands else None


def setup_positions(sid, rid, ids):
    """DRIVE les positions (doctrine « drive positions ») : Corrodius sur une tuile a 6 voisins, 4
    unites sur son ring-1, l'allie Chaos LOINTAIN a distance hex 2. `applyAction move` teleporte
    (aucune contrainte de portee) -> la geometrie est CHOISIE, pas subie. Renvoie le boardGraph
    final."""
    import hexgeo
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    hub = _hub_tile(bg)
    if hub is None:
        return None
    # 1) degager le hub et son ring-1 : on deplace d'abord Corrodius, puis chaque unite a sa place.
    move(sid, rid, ids[CARRIER], hub["col"], hub["row"])
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    by_id = {t["id"]: t for t in bg["tiles"]}
    ctile = next((t for t in bg["tiles"] if t.get("occupantUnitId") == ids[CARRIER]), None)
    if ctile is None:
        return None
    near = [FRIEND_CHAOS_NEAR, FRIEND_XENOS, FRIEND_IMPERIAL, ENEMY_CHAOS]
    for vis in near:
        # relecture ENTRE CHAQUE move : `applyAction move` refuse une tuile OCCUPEE, et l'echec est
        # silencieux (l'unite reste ou elle est) -> on choisit la 1re tuile REELLEMENT libre a chaque
        # fois, et le controle de distance en sortie de `main` refuse un montage degrade.
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        by_id = {t["id"]: t for t in bg["tiles"]}
        ctile = next((t for t in bg["tiles"] if t.get("occupantUnitId") == ids[CARRIER]), None)
        if ctile is None:
            return None
        free = [by_id[n] for n in (ctile.get("neighbours") or [])
                if n in by_id and by_id[n].get("walkable") and not by_id[n].get("isWall")
                and by_id[n].get("occupantUnitId") in (None, ids[vis])]
        if not free:
            return None
        move(sid, rid, ids[vis], free[0]["col"], free[0]["row"])
    # 2) les allies Chaos LOINTAINS : distance hex EXACTEMENT 2 puis 3 -- ils entrent dans l'aura
    #    l'un apres l'autre quand le rayon franchit ses DEUX seuils.
    for vis, want in FAR_PLACEMENT.items():
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        ctile = next((t for t in bg["tiles"] if t.get("occupantUnitId") == ids[CARRIER]), None)
        occupied = {t["id"] for t in bg["tiles"] if t.get("occupantUnitId") is not None}
        cpos = (ctile["col"], ctile["row"])
        far = next((t for t in bg["tiles"]
                    if t.get("walkable") and not t.get("isWall") and t["id"] not in occupied
                    and hexgeo.distance((t["col"], t["row"]), cpos) == want), None)
        if far is None:
            return None
        move(sid, rid, ids[vis], far["col"], far["row"])
    return _r(sid, "boardGraph", {"runnerId": rid}, 90)


def offline_fire(cap, player, mutate=None):
    """Rejoue le turn-start de `player` cote PORT depuis la capture `cap`.

    `_bump_turns_started` AVANT le vecteur = mirror de l'ORDRE natif (`StartTurnOperation$$Execute`
    incremente `turnsStarted@+0x58` puis emet la sequence 0x12..0x16) -- sans lui le rayon d'aura
    serait lu avec un tour de retard.

    `mutate` = nom d'un gate a NEUTRALISER (contrefactuel) : 'chaos' | 'stationary' | 'friends' |
    'radius1' | 'trait'."""
    state = load_state(cap["dec"], cap["ob"], cap["snap"], board=cap["board"])
    _bump_turns_started(state, player)
    import engine.runner.operations.triggers.loki.cursed_plague_bell as M
    saved = M.cursed_plague_bell_targets_selector
    if mutate is not None:
        from engine.dsl.base import Const
        from engine.entities.selectors import (Caster, SurroundingFriends, SurroundingEnemies,
                                               UnitsWithoutTrait, UnitsWithTrait)

        def patched(is_danger_zone=False):
            owner = Caster()
            rng = (Const(1) if mutate == "radius1"
                   else M.ContagionsOfNurgleRange(owner, 0, is_danger_zone))
            if mutate == "friends":                       # gate de CAMP retire (ennemis inclus)
                base = SurroundingEnemies(owner, rng)
            else:
                base = SurroundingFriends(owner, rng)
            sel = base if mutate == "chaos" else UnitsWithTrait(base, M.CHAOS)
            return sel if mutate == "stationary" else UnitsWithoutTrait(sel, M.STATIONARY)

        M.cursed_plague_bell_targets_selector = patched
    try:
        turn_start_other_triggers(state, player)
    finally:
        M.cursed_plague_bell_targets_selector = saved
    return state


def measure(sid, seed, board_id, turns, verbose=True, keep=False):
    """Monte le montage, joue `turns` tours de P et rend la mesure BRUTE (aucune assertion).

    Renvoie `None` si le montage n'a pas pu etre etabli (unite absente, placement impossible,
    distance non atteinte) -- JAMAIS un resultat degrade : un move refuse ferait simplement
    disparaitre le cas discriminant que l'unite portait, et le vert ne prouverait plus rien.
    Sinon : `{rows, p_team, ids, vis_by_id, rid}` (le runner est dispose sauf `keep`)."""
    import hexgeo
    rid = build(seed, board_id)
    if verbose:
        print("[224] runner=%s seed=%s board=%s" % (rid, seed, board_id))
    try:
        view = dv(sid, rid)
        ids, teams = {}, {}
        for u in (view.get("units") or []):
            if u.get("alive"):
                ids[u.get("visualId")] = int(u["id"])
                teams[int(u["id"])] = u.get("team")
        missing = [v for v in (P_UNITS + A_UNITS) if v not in ids]
        if missing:
            print("[224] ABORT unites absentes du build: %s" % missing)
            return None
        vis_by_id = {v: k for k, v in ids.items()}
        p_team = view.get("currentPlayer")
        if setup_positions(sid, rid, ids) is None:
            print("[224] ABORT placement impossible (pas assez de tuiles libres)")
            return None
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        pos = {t.get("occupantUnitId"): (t["col"], t["row"])
               for t in bg["tiles"] if t.get("occupantUnitId") is not None}
        cpos = pos[ids[CARRIER]]
        want = {FRIEND_CHAOS_NEAR: 1, FRIEND_XENOS: 1, FRIEND_IMPERIAL: 1, ENEMY_CHAOS: 1,
                **FAR_PLACEMENT}
        degraded = []
        for vis in P_UNITS + A_UNITS:
            if vis == CARRIER:
                continue
            d = hexgeo.distance(pos[ids[vis]], cpos)
            if verbose:
                print("  place %-20s pos=%s dist=%d (voulu %d) team=%s"
                      % (vis, pos[ids[vis]], d, want[vis], teams[ids[vis]]))
            if d != want[vis]:
                degraded.append((vis, d, want[vis]))
        if degraded:
            print("[224] ABORT montage degrade (distances non atteintes): %s" % degraded)
            return None

        from engine.runner.abilities.deathguard import contagions_of_nurgle_range_for_turns
        from engine.entities.stats import StatType
        from engine.runner.components import StatsComponent
        rows = []
        for k in range(turns):
            if dv(sid, rid).get("currentPlayer") == p_team:      # se placer au tour ADVERSE
                endturn(sid, rid)
            cap = {"dec": dv(sid, rid, all_ab=True),
                   "ob": _r(sid, "observeBattle", {"runnerId": rid}, 60),
                   "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 120), "board": board}
            before = carriers_live(cap["dec"])
            endturn(sid, rid)                                    # A -> P : turn-start natif
            after = carriers_live(dv(sid, rid, all_ab=True))
            st = offline_fire(cap, p_team)
            off = carriers_offline(st)
            sc = st.get_entity(ids[CARRIER]).get_component(StatsComponent)
            ts = int(sc.ctx.stats.get_stat(int(StatType.TURNS_STARTED), 0))
            rad = contagions_of_nurgle_range_for_turns(ts)
            ok = set(after) == set(off) and all(after.get(i) == off.get(i) for i in after)
            if verbose:
                print("[224] tour P #%d  TurnsStarted=%d rayon=%d  live=%s port=%s  "
                      "duree live=%s port=%s  %s"
                      % (k + 1, ts, rad,
                         sorted(vis_by_id[i] for i in after), sorted(vis_by_id[i] for i in off),
                         sorted(set(after.values())), sorted(set(off.values())),
                         "OK" if ok else "DESACCORD"))
            rows.append({"k": k + 1, "ts": ts, "radius": rad, "live": after,
                         "port": off, "before": before, "cap": cap, "ok": ok})
        return {"rows": rows, "p_team": p_team, "ids": ids, "vis_by_id": vis_by_id, "rid": rid}
    finally:
        if not keep:
            dispose(sid, rid)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="C1_75",
                    help="board a >= 6 spawns joueur (MC1_67 n'en a que 5)")
    ap.add_argument("--turns", type=int, default=6, help="nb de tours de P mesures")
    ap.add_argument("--mutate", action="store_true", help="rejoue les contrefactuels par gate")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en sortie")
    args = ap.parse_args(argv)

    sid = _resolve_session()
    out = measure(sid, args.seed, args.board, args.turns, keep=args.keep)
    if out is None:
        return 2
    rows, p_team, vis_by_id = out["rows"], out["p_team"], out["vis_by_id"]
    bad = sum(0 if r["ok"] else 1 for r in rows)
    if args.mutate and rows:
        print("\n[224] contrefactuels (memes captures, un gate neutralise a la fois)")
        for gate in ("chaos", "stationary", "friends", "radius1"):
            bites = 0
            for row in rows:
                mo = set(carriers_offline(offline_fire(row["cap"], p_team, mutate=gate)))
                if mo != set(row["live"]):
                    bites += 1
                print("   %-11s tour #%d -> %s  %s"
                      % (gate, row["k"], sorted(vis_by_id[i] for i in mo),
                         "MORD" if mo != set(row["live"]) else "inerte sur ce montage"))
            print("   => %-11s mord sur %d/%d tours" % (gate, bites, len(rows)))
    print("\n[224] %d tours confrontes, %d desaccords" % (len(rows), bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
