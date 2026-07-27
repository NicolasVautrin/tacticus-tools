"""#241 -- MESURE du volet PORTEE du gate de cible, et surtout de son etage le plus RISQUE :
le CLAMP MELEE de `IdunBattle.Core.Services.TargetingQuery$$GetRange`.

CE QUI EST DISCRIMINE ICI (et que les probes de masque ne pouvaient pas voir) : `GetRange` ne rend
pas seulement `constants.range`. Quand `options.ForceMeleeTarget` est vrai pour le caster, il
appelle `IdunBattle.Core.Services.AttackQuery$$ShouldApplyRangedInMelee(caster, casterTiles,
ignoreTrait = 1)` et, s'il existe un ENNEMI MELEE-ABLE ADJACENT, rabat la portee a
`Math.Min(1, range)` **et** pose `Range.OnlyAdjacent`. Autrement dit : une ability ranged de portee
2-3 ne porte plus qu'a l'adjacence des que son caster est engage au contact.

Le scenario compare donc DEUX etats qui ne different QUE par la presence d'un ennemi adjacent :

    S1 : aucun ennemi adjacent au caster, un ennemi a distance 2   -> doit etre CIBLABLE
    S2 : un ennemi adjacent au caster,  un ennemi a distance 2     -> le distant doit etre REFUSE
                                                                      (`TargetIsInRange`)

Si le clamp n'etait pas porte, S1 et S2 rendraient le MEME verdict cote port (cible acceptee), et
la divergence serait PERMISSIVE -- donc invisible en self-play. C'est exactement le trou que ce
probe existe pour rendre visible.

ORACLE = le RPC `abilityReason` (natif). CONFRONTE = `engine.runner.abilities.targeting`.

PORTEUR : `necroDestroyer` / `MultiThreatEliminator` (1006) -- HERO present dans `--list-pool`,
`constants.range = 2`, preset `TargetingOptions` statique `+0x140` (`useRangeFromConfig` +
`forceMeleeTarget = True`). C'est le seul couple du registre a la fois spawnable, de portee > 1 et
`forceMeleeTarget` arme.

Usage :
    python probe_range_gate_melee_clamp.py [--board MC1_67] [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent

CASTER_VIS = "necroDestroyer"
ABILITY = 1006                      # MultiThreatEliminator
P_UNITS = ["necroDestroyer", "necroOverlord"]
A_UNITS = ["darkaCompanion", "astraBullgryn", "eldarRanger"]
RULE_TARGET_IS_IN_RANGE = 0x8000000


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _hexv(h):
    try:
        return int(str(h), 16)
    except (TypeError, ValueError):
        return 0


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _capture(rpc, rid, board_obj):
    """Etat OFFLINE + vue live au meme instant (dec/ob/snap), comme tout le harnais du moteur."""
    from engine.runner.snapshot import load_state
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    return dec, load_state(dec, ob, snap, board=board_obj)


def _classify(rpc, rid, dec, state, caster_id):
    """Rend (adjacents, distance2) = ids d'ennemis VIVANTS a distance hex 1 et 2 du caster."""
    import hexgeo
    caster = next((u for u in (dec.get("units") or []) if int(u["id"]) == int(caster_id)), None)
    if caster is None:
        return [], []
    cp = _pos(caster)
    adj, far = [], []
    for u in (dec.get("units") or []):
        if not u.get("alive") or int(u["id"]) == int(caster_id):
            continue
        if u.get("owner") == caster.get("owner"):
            continue
        d = hexgeo.distance(cp, _pos(u))
        if d == 1:
            adj.append(int(u["id"]))
        elif d == 2:
            far.append(int(u["id"]))
    return adj, far


def _confront(rpc, rid, state, caster_id, target_id, ability):
    from engine.runner.abilities.targeting import get_invalid_target_reason
    nat = rpc("abilityReason", {"runnerId": rid, "casterId": int(caster_id),
                                "abilityType": ABILITY, "targetId": int(target_id)}, 60)
    nt = _hexv(((nat or {}).get("targetReason") or {}).get("hex"))
    names = ",".join(((nat or {}).get("targetReason") or {}).get("reasons") or []) or "-"
    pt = int(get_invalid_target_reason(state, int(caster_id), int(target_id), ability) or 0)
    return nt, pt, names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--max-turns", type=int, default=16)
    args = ap.parse_args()

    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.handler import ABILITY_CLASSES

    sid = R._resolve_session()
    ability = ABILITY_CLASSES[ABILITY]()
    failures = []
    s1_seen = s2_seen = False

    with tempfile.TemporaryDirectory(prefix="rngclamp_") as tmpdir:
        state_file = Path(tmpdir) / "state_range_clamp.json"
        argv = [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed),
                "--board", args.board, "--p-units", ",".join(P_UNITS),
                "--a-units", ",".join(A_UNITS), "--no-ai", "--state-file", str(state_file)]
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if not state_file.exists():
            print("[build] KO:", (p.stderr or p.stdout or "")[-400:])
            return 1
        rid = json.loads(state_file.read_text())["runnerId"]

        def rpc(m, b, t=90):
            return _unwrap(R._rpc(sid, m, [b], timeout=t))

        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board_obj = Board(bg["tiles"], adjacency="evenq")
            caster_id = None
            for turn in range(args.max_turns):
                dec, state = _capture(rpc, rid, board_obj)
                caster = next((u for u in (dec.get("units") or [])
                               if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
                if caster is None:
                    print("caster absent/mort -- arret")
                    break
                caster_id = int(caster["id"])
                adj, far = _classify(rpc, rid, dec, state, caster_id)
                print("  tour %-2d caster u%d %s  player=%s  adj=%s dist2=%s"
                      % (turn, caster_id, _pos(caster), dec.get("currentPlayer"), adj, far))

                # --- S1 : PAS d'ennemi adjacent, un ennemi a distance 2 -> pas de clamp.
                if far and not adj and not s1_seen:
                    s1_seen = True
                    tid = far[0]
                    nt, pt, names = _confront(rpc, rid, state, caster_id, tid, ability)
                    print("S1 (aucun ennemi adjacent, cible a dist 2) u%d : natif=0x%x port=0x%x [%s]"
                          % (tid, nt, pt, names))
                    if nt != 0:
                        print("  ATTENDU natif=0 (portee 2 = constants.range, pas de clamp) -- KO")
                        failures.append("S1 natif refuse 0x%x" % nt)
                    if pt != 0:
                        print("  FAUX-REFUS du port (le natif accepte) -- KO")
                        failures.append("S1 port refuse 0x%x" % pt)
                    if nt == 0 and pt == 0:
                        print("  OK : cible a dist 2 ACCEPTEE des deux cotes")

                # --- S2 : un ennemi adjacent ET un ennemi a distance 2 -> clamp actif.
                if far and adj and not s2_seen:
                    s2_seen = True
                    tid_far, tid_adj = far[0], adj[0]
                    nt, pt, names = _confront(rpc, rid, state, caster_id, tid_far, ability)
                    print("S2 (ennemi u%d ADJACENT, cible a dist 2) u%d : natif=0x%x port=0x%x [%s]"
                          % (tid_adj, tid_far, nt, pt, names))
                    if nt != RULE_TARGET_IS_IN_RANGE:
                        print("  ATTENDU natif=TargetIsInRange (clamp melee) -- KO")
                        failures.append("S2 natif=0x%x != TargetIsInRange" % nt)
                    if pt != nt:
                        print("  le port ne reproduit PAS le clamp -- KO")
                        failures.append("S2 port=0x%x != natif=0x%x" % (pt, nt))
                    if nt == RULE_TARGET_IS_IN_RANGE and pt == nt:
                        print("  OK : clamp melee reproduit (portee 2 -> adjacence)")
                    nt2, pt2, names2 = _confront(rpc, rid, state, caster_id, tid_adj, ability)
                    print("S2 (meme etat, cible ADJACENTE) u%d : natif=0x%x port=0x%x [%s]"
                          % (tid_adj, nt2, pt2, names2))
                    if nt2 == 0 and pt2 != 0:
                        print("  FAUX-REFUS du port sur la cible adjacente -- KO")
                        failures.append("S2 adjacent port refuse 0x%x" % pt2)
                    elif nt2 == 0 and pt2 == 0:
                        print("  OK : la cible ADJACENTE reste legale des deux cotes")

                if s1_seen and s2_seen:
                    break

                # --- rapprochement : chaque camp avance vers le caster (le caster, lui, NE BOUGE
                #     PAS -- son masque ne pose pas CasterHasNotMoved mais on veut une tuile fixe).
                import hexgeo
                # `side` de `aiMovableTiles` est RELATIF au joueur COURANT (pas a notre caster) :
                # "friendly" = les unites de `currentPlayer`. On avance donc toujours "friendly",
                # ce qui rapproche alternativement l'escorte puis les ennemis.
                side = "friendly"
                mov = rpc("aiMovableTiles", {"runnerId": rid, "side": side}, 60)
                cp = _pos(caster)
                for m in (mov.get("units") or []):
                    uid = int(m.get("unitId"))
                    if uid == caster_id:
                        continue                      # le caster garde sa tuile (mesure stable)
                    tiles = [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                             if t.get("col") is not None]
                    if not tiles:
                        continue
                    best = min(tiles, key=lambda t: (hexgeo.distance(t, cp), t))
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": uid,
                        "to": {"col": best[0], "row": best[1]}}}, 60)
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        finally:
            try:
                R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:
                pass

    if not s1_seen or not s2_seen:
        print("ECHEC : geometrie non atteinte (S1 vu=%s, S2 vu=%s) -- le probe n'a rien prouve"
              % (s1_seen, s2_seen))
        return 1
    if failures:
        print("ECHEC :", "; ".join(failures))
        return 1
    print("OK -- clamp melee de GetRange confronte au natif dans les DEUX regimes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
