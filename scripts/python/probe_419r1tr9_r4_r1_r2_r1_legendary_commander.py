#!/usr/bin/env python
"""#419-r1-tr9-r4-r1-r2-r1 -- `LegendaryCommander_ExtraHits` (1395) : +nrOfHits coups, gate en
NEGATION (`!IsNormalAttack`), etat persistant (<< first attack >>) et `IsFirstHitGroupInAttack`.

CE QUE CE PROBE MESURE, ET DANS QUEL ORDRE (chaque cran est NATIF SEUL ; le port n'entre pas dans
la definition du verdict) :

  [1] MONTAGE INSTALLE. L'effet 1395 est-il present sur `custoTrajann` (`decisionView`) et l'aura
      couvre-t-elle la victime ? Sans ce cran rien d'autre n'est lisible.
  [2] LE BONUS MORD. Nb de coups NATIFS appliques par une attaque d'ABILITY (famille ATTACK) d'un
      allie de Trajann sur un ennemi ADJACENT A TRAJANN :
        * bras `armed` : Trajann a caste une active ce tour -> `HasUsedActiveAbilityThisTurn` VRAI
          -> l'aura couvre l'ennemi -> `nrOfHits` coups EN PLUS ;
        * bras `idle`  : Trajann n'a rien caste -> le `Filter` du selecteur ne retient personne ->
          aucun bonus.
      Meme board, meme seed, meme geometrie, meme cast : la SEULE variable est le cast de Trajann.
  [3] << FIRST ATTACK >>. Dans le bras `armed`, la DEUXIEME attaque du MEME attaquant sur la MEME
      victime (tour suivant) doit retomber a la valeur de base : `!IsInPersistentDataList` a ferme.
  [4] TEMOIN DE NEGATION. L'attaque NORMALE du meme attaquant sur la meme victime ne doit RIEN
      gagner, dans AUCUN bras -- c'est `!IsNormalAttack`, le noeud qui distingue cet effet des cinq
      autres consommateurs du canal.

MONTAGE (RE : `docs/rl/case-419-r1-tr9-r4-r1-r2-r1-legendary-commander.md`)
  `IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraHitsEffect$$CreateTargetSelector` =
      Filter( AdjacentEnemies( Filter( Friends(Owner, AllUnits, 3),
                                       HasUsedActiveAbilityThisTurn(Subject) ), 1, 3 ),
              IsAdjacent(Owner, Subject, 3) )
  `Friends(Owner, AllUnits)` n'a AUCUN `- Owner` : TRAJANN LUI-MEME compte parmi les allies dont le
  cast arme l'aura. Un seul cast (le sien, `MomentShackle`) suffit donc a installer le montage, et
  la victime n'a qu'a etre ADJACENTE A TRAJANN (le 4e noeud, propre a 1395, exige cette adjacence
  de toute facon).

  Attaquant : `deathBlightlord` / `FlailSwing` -- ability de la famille ATTACK
  (`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`), donc le SEUL vecteur qui
  traverse `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` -> la formule de coups.
  Une attaque de la famille ABILITY ne la traverse PAS (cf. l'entete de
  `engine/services/attack_hits_formula.py`), et la PREDICTION non plus : le seul regime ou 1395
  mord est le COMBAT famille ATTACK.

Usage :  python probe_419r1tr9_r4_r1_r2_r1_legendary_commander.py [--seed 41395] [--board MC1_67]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import gameconfig as GC                                       # noqa: E402
from rl_collect_batch import _resolve_session                 # noqa: E402
from probe_353_ramming_speed_prediction import _r             # noqa: E402

BOARD = "MC1_67"
SEED = 41395
TRAJANN = "custoTrajann"          # porteur du passif `LegendaryCommander` (pool, rank courant)
ATTACKER = "deathBlightlord"      # porteur de `FlailSwing` (famille ATTACK, melee, nrOfHits=3)
VICTIM = "astraBullgryn"
HP = 3000000                      # la victime doit survivre a MomentShackle + 2 FlailSwing


class MontageError(RuntimeError):
    """Le montage n'est pas installe -> on ne conclut RIEN (jamais un verdict sur un bras vide)."""


def _ability_id(name: str) -> int:
    a = GC.ability(name) or {}
    v = a.get("id")
    if v is None:
        raise MontageError(f"gameconfig.ability({name!r}).id introuvable")
    return int(v)


def _cfg_hits(name: str) -> int:
    v = ((GC.ability(name) or {}).get("constants") or {}).get("nrOfHits")
    if v is None:
        raise MontageError(f"gameconfig.ability({name!r}).constants.nrOfHits introuvable")
    return int(v)


def _nr_of_hits_bonus(level: int) -> int:
    """L'ORACLE de la magnitude = `ConfigVar(0x2f = nrOfHits)` de `LegendaryCommander` au niveau
    d'ability effectif -- jamais un litteral (`ability_var` est le MEME foyer que le port)."""
    from engine.entities.effects.magnitude import ability_var
    v = ability_var("LegendaryCommander", "nrOfHits", level)
    if v is None:
        raise MontageError("ability_var(LegendaryCommander, nrOfHits) introuvable")
    return int(v)


def _build(state_file: Path, seed: int, board: str) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board,
           "--p-units", f"{TRAJANN},{ATTACKER}", "--a-units", VICTIM,
           "--unit-stat", f"{VICTIM}:Health={HP},RemainingHealth={HP},Armor=0,FixedArmor=0"]
    p = subprocess.run(cmd, cwd=str(_HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build rc={p.returncode} : {(p.stderr or p.stdout)[-900:]}")
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def _view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _endturn(sid, rid):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _cast(sid, rid, cid, tid, ability):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": int(ability)}, "captureEvents": True}, 180)


def _normal_attack(sid, rid, cid, tid):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "attack", "unitId": int(cid), "targetId": int(tid)}, "captureEvents": True}, 180)


def _hits_of(cast: dict, ability: int, tid: int) -> int:
    """Nb de coups NATIFS portes sur `tid` par `ability` -- meme lecture que
    `tests/engine/runner/test_flail_swing_live.py::_cast_live_perhit` (un event `Amount` par coup)."""
    n = 0
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" not in td:
                continue
            if ability is not None and td.get("Active_Ability_Type") != ability:
                continue
            if int(td.get("Target_Id") or -1) != int(tid):
                continue
            n += 1
    return n


def _place(sid, rid, ids: dict) -> dict:
    """GEOMETRIE DRIVEE ET VERIFIEE (runner.md sec.4) : la VICTIME sur une tuile a 6 voisins
    marchables, TRAJANN et l'ATTAQUANT sur deux de ces voisins. `FlailSwing` etant melee et le 4e
    noeud du selecteur exigeant `IsAdjacent(Trajann, victime)`, les deux adjacences sont requises
    -- on les DRIVE, on ne les subit pas."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    six = sorted(t.get("id") for t in bg["tiles"]
                 if len(board.neighbours(t.get("id"))) == 6 and board.walkable(t.get("id"))
                 and all(board.walkable(n) for n in board.neighbours(t.get("id"))))
    if not six:
        raise MontageError("aucune tuile a 6 voisins marchables sur ce board")
    centre = six[len(six) // 2]
    ring = sorted(board.neighbours(centre))
    coords = {VICTIM: board.coord(centre), TRAJANN: board.coord(ring[0]),
              ATTACKER: board.coord(ring[3])}
    for vis, (col, row) in coords.items():
        _move(sid, rid, ids[vis], col, row)
    dv = _view(sid, rid)
    got = {}
    for u in (dv.get("units") or []):
        if int(u["id"]) in set(ids.values()):
            got[int(u["id"])] = (u.get("col"), u.get("row"))
    for vis, want in coords.items():
        have = got.get(ids[vis])
        if have is None or tuple(have) != tuple(want):
            raise MontageError(f"placement REFUSE pour {vis} : voulu {want}, lu {have}")
    return coords


def _ids(dv: dict) -> tuple[dict, int]:
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("aucune unite controlee")
    me = mine[0]["owner"]
    out = {}
    for vis, own in ((TRAJANN, True), (ATTACKER, True), (VICTIM, False)):
        u = next((x for x in units if x.get("visualId") == vis
                  and ((x.get("owner") == me) == own)), None)
        if u is None:
            raise MontageError(f"{vis} absent du roster ({'joueur' if own else 'adverse'})")
        out[vis] = int(u["id"])
    return out, me


def _effects_of(dv: dict, uid: int) -> list:
    u = next((x for x in (dv.get("units") or []) if int(x["id"]) == int(uid)), {})
    return [e.get("name") for e in (u.get("effects") or [])]


def _ability_level(dv: dict, uid: int) -> int:
    """Niveau d'ability effectif du porteur -- l'index de `ConfigVar(0x2f)`."""
    u = next((x for x in (dv.get("units") or []) if int(x["id"]) == int(uid)), {})
    for key in ("abilityLevel", "activeAbilityLevel", "level"):
        v = u.get(key)
        if v is not None:
            return int(v)
    return 50


def arm(sid, rid: int, cast_trajann: bool) -> dict:
    """UN bras. `cast_trajann` = la SEULE variable entre les deux bras."""
    dv = _view(sid, rid)
    ids, _me = _ids(dv)
    coords = _place(sid, rid, ids)
    out: dict = {"coords": {k: list(v) for k, v in coords.items()},
                 "cast_trajann": bool(cast_trajann)}
    dv = _view(sid, rid)
    out["trajann_effects"] = _effects_of(dv, ids[TRAJANN])
    out["ability_level"] = _ability_level(dv, ids[TRAJANN])
    shackle, flail = _ability_id("MomentShackle"), _ability_id("FlailSwing")
    if cast_trajann:
        c = _cast(sid, rid, ids[TRAJANN], ids[VICTIM], shackle)
        out["shackle_ok"] = bool(c.get("ok", True)) and not c.get("error")
        out["shackle_err"] = c.get("error")
    dv = _view(sid, rid)
    out["victim_effects_before"] = _effects_of(dv, ids[VICTIM])
    cast1 = _cast(sid, rid, ids[ATTACKER], ids[VICTIM], flail)
    out["flail_err"] = cast1.get("error")
    out["hits_1"] = _hits_of(cast1, flail, ids[VICTIM])
    # [3] << first attack >> : 2e FlailSwing du MEME attaquant sur la MEME victime, tour suivant.
    for _ in range(6):
        _endturn(sid, rid)
        dv = _view(sid, rid)
        u = next((x for x in (dv.get("units") or []) if int(x["id"]) == ids[ATTACKER]), {})
        if u.get("ctrl") and not u.get("hasActed"):
            break
    cast2 = _cast(sid, rid, ids[ATTACKER], ids[VICTIM], flail)
    out["flail2_err"] = cast2.get("error")
    out["hits_2"] = _hits_of(cast2, flail, ids[VICTIM])
    out["ids"] = ids
    return out


def run(seed: int = SEED, board: str = BOARD, verbose: bool = True) -> dict:
    sid = _resolve_session()
    logs = _HERE.parents[1] / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    res: dict = {"seed": seed, "board": board}
    for name, cast_trajann in (("armed", True), ("idle", False)):
        sf = logs / f"probe419r1tr9r4r1r2r1-{name}.json"
        rid = None
        try:
            rid = _build(sf, seed, board)
            res[name] = arm(sid, rid, cast_trajann)
            res[name]["runner"] = rid
        except MontageError as exc:
            res[name] = {"error": str(exc)}
        finally:
            if rid is not None:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    base = _cfg_hits("FlailSwing")
    lvl = (res.get("armed") or {}).get("ability_level") or 50
    bonus = _nr_of_hits_bonus(int(lvl))
    res["oracle"] = {"flail_nrOfHits": base, "legendary_nrOfHits": bonus, "level": int(lvl)}
    a, i = res.get("armed") or {}, res.get("idle") or {}
    res["verdict"] = {
        "montage": ("LegendaryCommander_ExtraHits" in (a.get("trajann_effects") or [])),
        "d_hits_1": (None if a.get("hits_1") is None or i.get("hits_1") is None
                     else int(a["hits_1"]) - int(i["hits_1"])),
        "expected_d_hits_1": bonus,
        "d_hits_2": (None if a.get("hits_2") is None or i.get("hits_2") is None
                     else int(a["hits_2"]) - int(i["hits_2"])),
        "expected_d_hits_2": 0}
    if verbose:
        print(json.dumps(res, indent=2, sort_keys=True))
    return res


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    a = ap.parse_args()
    r = run(a.seed, a.board)
    v = r.get("verdict") or {}
    ok = bool(v.get("montage")) and v.get("d_hits_1") == v.get("expected_d_hits_1") \
        and v.get("d_hits_2") == v.get("expected_d_hits_2")
    print("VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
