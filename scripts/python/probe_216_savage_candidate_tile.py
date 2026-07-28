"""probe #216 volet D -- le `Count(CanAddUnit(AdjacentTiles(Owner@0x148)))` de
`IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage` est-il evalue a la
POSITION REELLE du caster, ou a la TUILE CANDIDATE du balayage IA (`casterPosition`) ?

RE : `Owner@0x148` est un selecteur d'ENTITE ; le natif en prend la MainTile reelle
(`EntityExtensions$$GetTiles`). La tuile candidate vit dans d'AUTRES slots (`CasterTile@0x168` /
`CasterTiles@0x170`), que cet arbre n'utilise pas -- la struct de contexte que
`ComparablePlaybook$$GenerateMultiHitAttackPredictions` construit porte bien les deux (caster ENTITE
d'un cote, `casterPosition` + `UnitPosition.get_MainTile(casterPosition)` de l'autre).

MESURE : le caster NE BOUGE PAS (son movable set doit rester plein -- `pairUtility(col,row)` exige que
la tuile candidate y figure, sinon il retombe sur la tuile courante). On deplace la CIBLE pour la coller
a une tuile candidate B du movable set dont le nombre de voisins LIBRES differe nettement de celui de la
position REELLE du caster, puis on compare `pairUtility(col=B)` natif a l'utilite OFFLINE depuis B.
Le port compte les tuiles libres a la position REELLE (il lit `_pos(caster)`, jamais `ctx.caster_pos`) :
  - accord natif<->offline  -> le natif fait de meme (Owner = ENTITE), port FIDELE ;
  - desaccord de l'ordre de `extraDmg x (freeB - freeA) x hits` -> le natif suit la tuile CANDIDATE.
Les mods positionnels (elevation, adjacence) sont evalues depuis B des DEUX cotes : ils ne sont donc pas
le discriminant, seul le compte l'est.

Usage : python probe_216_savage_candidate_tile.py [--keep]
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_savage.json"
STATE = LOGS / "rs_216_candidate.json"
BOARD = "MC1_67"
SEED = 909
CASTER, TARGET = 81, 77
ALLY, FOE = 83, 79
ABILITY = 1230


def _run(args):
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _move(rid, uid, col, row):
    _run(["act", "move", "--unit", str(uid), "--to", "%d,%d" % (col, row),
          "--state-file", str(STATE), "--runner", str(rid)])


def _pair(rid, col, row):
    r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": CASTER, "targetId": TARGET,
                               "abilityType": ABILITY, "col": col, "row": row}])
    return r.get("utility")


def _offline_pair(rid, tile):
    """Utilite de paire OFFLINE depuis la tuile candidate `tile` (le port lit la position REELLE)."""
    import engine_validate as EV
    from engine import weights as W
    from engine.playbook import scene as _scene, get_playbook_or_default
    from engine.ai import context as AICTX
    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, CASTER, W.load(), _scene.build_predictor(rpc, rid))
    c = get_playbook_or_default(ABILITY).calculate_action_utility(ctx, tile, TARGET, ABILITY)
    return None if c is None else c["u"]


def main() -> int:
    if not SEED_BC.exists():
        print("seed BC augmentee absente : python catalog_inject.py --units bloodTerminator --out %s"
              % SEED_BC)
        return 2
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--seed-bc", str(SEED_BC),
          "--p-units", "bloodTerminator,ultraCalgar", "--a-units", "tauCrisis,blackTerminator",
          "--hp-player", "100000", "--hp-target", "60000", "--state-file", str(STATE)])
    rid = int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])
    print("runner=%d board=%s" % (rid, BOARD))

    import engine_validate as EV
    from engine.entities.pathfinding.board import Board
    sid = L.INV._session_id()
    bg = EV._r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = EV._r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    upos = {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
            for u in (dv.get("units") or [])}
    # bouchons gares loin AVANT tout (ils ne doivent fausser aucun des deux comptes)
    far = sorted(board.by_id, key=lambda t: -t)
    for uid in (ALLY, FOE):
        for t in far:
            c = board.coord(t)
            if board.walkable(t) and c not in upos.values():
                _move(rid, uid, c[0], c[1])
                break
    dv = EV._r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    occ = {((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
           for u in (dv.get("units") or []) if u.get("alive")}
    here = next(((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                for u in (dv.get("units") or []) if u.get("id") == CASTER)

    def free_at(pos, extra_occ=frozenset()):
        t = board.id_at(pos[0], pos[1])
        taken = (occ | set(extra_occ)) - {pos}
        return len([n for n in board.neighbours_native(t)
                    if board.walkable(n) and board.coord(n) not in taken])

    mov = EV._r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    cand = [(t.get("col"), t.get("row"))
            for u in (mov.get("units") or []) if u.get("unitId") == CASTER
            for t in (u.get("tiles") or [])]
    free_here = free_at(here)
    # tuile candidate B : dans le movable set, avec un voisin LIBRE ou poser la cible, et un compte
    # de tuiles libres qui DIFFERE nettement de celui de la position reelle du caster.
    pickB = None
    for b in cand:
        if b == here or b in occ:
            continue
        nb = [board.coord(n) for n in board.neighbours_native(board.id_at(b[0], b[1]))
              if board.walkable(n) and board.coord(n) not in occ]
        if not nb:
            continue
        tgt_tile = nb[0]
        if abs(free_at(b, {tgt_tile}) - free_here) >= 2:
            pickB = (b, tgt_tile)
            break
    if pickB is None:
        print("aucune tuile candidate discriminante dans le movable set du caster")
        return 1
    B, tgt_tile = pickB
    _move(rid, TARGET, tgt_tile[0], tgt_tile[1])
    free_B = free_at(B, {tgt_tile})
    print("caster REEL en %s (free=%d) ; tuile CANDIDATE B=%s (free=%d) ; cible posee en %s"
          % (here, free_here, B, free_B, (tgt_tile,)))
    nat = _pair(rid, B[0], B[1])
    off = _offline_pair(rid, B)
    print("pairUtility depuis B : natif=%r  offline=%r" % (nat, off))
    if nat is None:
        print("VERDICT : INDETERMINE (le natif n'a pas rendu d'utilite pour cette tuile)")
    elif abs((off or 0) - nat) < 1e-6:
        print("VERDICT : accord -> le compte suit la POSITION REELLE du caster (port FIDELE)")
    else:
        print("VERDICT : DESACCORD %r -> le natif compterait depuis la TUILE CANDIDATE"
              % ((off or 0) - nat,))
    if "--keep" not in sys.argv[1:]:
        L._rpc("disposeRunner", [{"runnerId": rid}])
        print("runner %d dispose" % rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
