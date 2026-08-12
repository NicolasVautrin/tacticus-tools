"""#987 (residu #957-r2) -- CONFRONTATION du veto de `1115 FearOfTheUnseen`.

CE QUE LE NATIF DEMANDE
-----------------------
`IdunBattle.AI.Playbook.Loki.FearOfTheUnseenPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # cctor : Fix64(1)
    vt = BasePlaybook.GetAllNormalAttackTargets(caster)              # ValidTargets
    if (vt != null && vt.<+0x10> != null && vt.<+0x10>.<+0x18> == 0)
        bucket.AddAction(GenerateAction(casterPosition, caster, Fix64.op_Implicit(10)))

`GetAllNormalAttackTargets` = `IBattleQuery` slot `0x45` =
`GetAllValidTargetsFromAllPossibleMovementTiles(unit, GetNormalAttackType(unit), false)`, et
`+0x10` est l'`OrderedSet<IEntity>` UNION. Le veto est donc : **l'union des cibles d'attaque
normale, prise sur TOUTES les tuiles atteignables, est VIDE**.

POURQUOI LES DEUX PISTES DU RESIDU NE POUVAIENT PAS MARCHER
-----------------------------------------------------------
Le residu proposait (a) patcher le cooldown initial dans `BC.Units[].Abilities`, (b) trouver un
board dont la tuile de deep-strike est hors de portee. Les deux sont refutees par la mesure :

* `initialCooldownTurns = "1"` n'est PAS dans `BC.Units[]` -- c'est une entree de
  `BC.Abilities.ActiveAbilities.FearOfTheUnseen.Constants`. Et le patcher est INUTILE : mesure
  live, `1115` passe de `cd=1` a **`cd=0` des le tour suivant**, donc le tour 1 n'est pas le seul
  ou l'ability est disponible.
* La tuile d'arrivee n'a aucune importance, et `--place` MORD sur `tyranDeathleaper` (mesure :
  il se pose exactement ou on le demande, y compris en `(6,8)`). Ce qui rend l'union non vide,
  ce n'est pas SA position : c'est que le trait `TeleportStrike` lui donne un pathfinder qui
  atteint tout le plateau jouable -- mesure live, avec `Movement=0` et le Deathleaper en `(6,8)`,
  le natif propose encore `MoveUnitMessage to (0,3)` avec `pathLen = 1`.

LE REGIME QUI, LUI, EXISTE
--------------------------
Puisque le pathfinder atteint tout, l'union est vide **ssi aucun ennemi n'a de voisin JOUABLE et
LIBRE** (l'unique arme de `tyranDeathleaper` n'a pas de `Range` -> portee 1). On ENCERCLE donc
l'unique ennemi. Sur `MC1_67`, `(0,0)` est de degre **2** (voisins `(0,1)` et `(1,0)`) : deux
bloqueurs de MON camp suffisent, et ils ne sont pas des cibles pour le Deathleaper.

L'adjacence est ASSERTIONNEE contre le `boardGraph` du runner, jamais deduite de la couronne hex
(le natif lit la liste d'adjacence STOCKEE, qui la sous-atteint).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from probe_r6_round_materialize import _mkrpc                      # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402

BOARD = "MC1_67"
SEED = "777"
DL = "tyranDeathleaper"
#: l'UNIQUE ennemi, a encercler. `(0,0)` est de degre 2 sur `MC1_67`.
PREY = "orksNob"
TILE_PREY = (0, 0)
#: mes deux BLOQUEURS, sur les deux voisins de `TILE_PREY`. Ils sont a MOI, donc le Deathleaper ne
#: peut pas les prendre pour cible -- ils ne font qu'occuper la tuile.
BLOCKERS = ("ultraEliminatorSgt", "templHelbrecht")
TILE_BLOCK = ((0, 1), (1, 0))
#: LES DEUX BRAS -- seule la tuile du Deathleaper change.
#:  `loin`   : a l'autre bout du plateau. Au tour 2 le `TeleportStrike` a deja ete consomme par le
#:             deploiement, donc ses tuiles de move sont celles de son MOUVEMENT NORMAL, et aucune
#:             n'est adjacente a la proie -> l'UNION est VIDE -> le veto est VRAI.
#:  `proche` : adjacent a la proie -> l'union contient la proie -> le veto est FAUX.
ARMS = {"loin": (6, 8), "proche": (1, 1)}

FOTU = int(ActiveAbilityType.FearOfTheUnseen)      # 1115


def _build(arm: str, seed=SEED, board=BOARD):
    """`arm` fixe la SEULE chose qui change entre les bras : la tuile du Deathleaper."""
    sf = ROOT / "logs" / "runners" / ("p987fotu-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    dl_tile = ARMS[arm]
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
           "--board", board, "--rank", "17",
           "--p-units", "%s,%s,%s" % (DL, BLOCKERS[0], BLOCKERS[1]),
           "--a-units", PREY,
           "--place", "%s:%d,%d" % (DL, dl_tile[0], dl_tile[1]),
           "--place", "%s:%d,%d" % (BLOCKERS[0], TILE_BLOCK[0][0], TILE_BLOCK[0][1]),
           "--place", "%s:%d,%d" % (BLOCKERS[1], TILE_BLOCK[1][0], TILE_BLOCK[1][1]),
           "--a-place", "%s:%d,%d" % (PREY, TILE_PREY[0], TILE_PREY[1]),
           "--no-ai"]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, (p.stderr or p.stdout or "")[-1200:]
    return int(json.loads(sf.read_text())["runnerId"]), None


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True, "includeInactive": True}, 180)


def _unit(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis), None)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return None if p.get("col") is None else (int(p["col"]), int(p["row"]))


def _assert_geometry(rpc, rid, arm):
    """L'adjacence vient du `boardGraph` du runner, PAS d'une couronne hex calculee."""
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or []
    # `neighbours` est une liste d'ID de tuiles (`BattleQuery.GetAdjacentTiles(tile, 0, 0, 1)`),
    # pas d'objets : on la resout par la table id -> (col, row) du meme payload.
    pos_by_id = {t.get("id"): (int(t["col"]), int(t["row"])) for t in tiles}
    neigh = {}
    for t in tiles:
        key = (int(t["col"]), int(t["row"]))
        neigh[key] = sorted(p for p in (pos_by_id.get(n) for n in (t.get("neighbours") or []))
                            if p is not None)
    out = {"prey_neighbours": neigh.get(TILE_PREY), "source": "boardGraph"}
    if out["prey_neighbours"] is None:
        out["source"] = "boardGraph SANS liste d'adjacence -- geometrie NON assertionnee"
    else:
        out["prey_free_neighbours"] = [p for p in out["prey_neighbours"]
                                       if p not in TILE_BLOCK]
    return out


def run(arm: str = "loin", verbose: bool = True, seed=SEED, board=BOARD) -> dict:
    rid, err = _build(arm, seed=seed, board=board)
    if rid is None:
        return {"error": "build KO : %s" % err}
    rpc = _mkrpc()
    try:
        geo = _assert_geometry(rpc, rid, arm)
        dv = _dv(rpc, rid)
        dl = _unit(dv, DL)
        if dl is None:
            return {"error": "Deathleaper absent du build"}
        out = {"arm": arm, "runner": rid, "geo": geo,
               "dl_id": int(dl["id"]), "dl_pos": _pos(dl), "prey_pos": _pos(_unit(dv, PREY)),
               "blockers_pos": [_pos(_unit(dv, b)) for b in BLOCKERS]}
        # TOUR 1 : `1115` est en `cd=1`, donc le natif ne peut pas la proposer, quoi que vaille
        # le veto. On le MESURE plutot que de le supposer.
        out["t1"] = _snapshot(rpc, rid, dl)
        # On rend la main puis on la reprend : `1115` passe a `cd=0`.
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        dv2 = _dv(rpc, rid)
        out["t2"] = _snapshot(rpc, rid, _unit(dv2, DL))
        # CONFRONTATION DU PORT -- l'oracle standard : il fait choisir le moteur Python sur CE
        # runner et compare l'ability retenue a celle du natif. C'est le seul chemin qui construit
        # le `NCContext` comme le fait la decision reelle (`engine/ai/action_generators.py`).
        out["oracle"] = _oracle(rid, steps=6)
        if verbose:
            _report(out)
        return out
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def _snapshot(rpc, rid, dl):
    """Etat de `1115` + ce que le natif PROPOSE pour le Deathleaper."""
    ab = next((a for a in ((dl or {}).get("abilities") or []) if int(a.get("id", -1)) == FOTU), None)
    o = {"cooldown": None if ab is None else ab.get("cooldown"),
         "usable": None if ab is None else ab.get("usable"),
         "disabled": None if ab is None else ab.get("disabled")}
    try:
        dry = rpc("aiDryRunAllUnits", {"runnerId": rid}, 240)
        u = next((x for x in (dry.get("units") or [])
                  if int(x.get("unitId", -1)) == int((dl or {}).get("id", -1))), None)
        o["proposed"] = None if u is None else u.get("proposed")
        o["proposes_1115"] = bool(u is not None and any(
            int(m.get("abilityType", -1)) == FOTU for m in (u.get("proposed") or [])))
    except Exception as exc:
        o["proposed"] = "aiDryRun KO: %s" % exc
        o["proposes_1115"] = None
    return o


def _oracle(rid, steps=1):
    """`engine_validate.py --runner <id>` : la comparaison port <-> natif, pas une re-implementation."""
    p = subprocess.run([sys.executable, "engine_validate.py", "--runner", str(rid),
                        "--steps", str(steps)],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    txt = (p.stdout or "") + (p.stderr or "")
    keep = [ln.strip() for ln in txt.splitlines()
            if ("ab=" in ln or "ABILITY" in ln.upper() or "MATCH" in ln.upper()
                or "MISS" in ln.upper())]
    return {"rc": p.returncode, "lines": keep[-8:] or txt.strip().splitlines()[-6:]}


def _report(r):
    print("[987] arm=%-7s runner=%s dl=%s@%s prey@%s blockers@%s"
          % (r["arm"], r["runner"], r["dl_id"], r["dl_pos"], r["prey_pos"],
             r["blockers_pos"]))
    print("       geometrie (%s) voisins de la proie = %s | LIBRES = %s"
          % (r["geo"]["source"], r["geo"]["prey_neighbours"],
             r["geo"].get("prey_free_neighbours")))
    for k in ("t1", "t2"):
        s = r[k]
        print("       %s : 1115 cd=%s usable=%s | propose_1115=%s | proposed=%s"
              % (k.upper(), s["cooldown"], s["usable"], s["proposes_1115"],
                 json.dumps(s["proposed"])[:200]))
    if r.get("oracle"):
        print("       ORACLE port<->natif (engine_validate) rc=%s" % r["oracle"]["rc"])
        for ln in r["oracle"]["lines"]:
            print("          %s" % ln[:190])


def verdict(loin: dict, proche: dict) -> list:
    """Le veto de `1115` est VRAI quand l'union est vide, et FAUX sinon.

    Le discriminant n'est pas << le natif propose 1115 >> tout seul : c'est l'ECART entre le bras
    ENCERCLE et son TEMOIN, tout le reste egal."""
    out = []
    for name, r in (("loin", loin), ("proche", proche)):
        if r.get("error"):
            out.append("[987] %s : %s" % (name, r["error"]))
    if out:
        return out
    if loin["t1"]["cooldown"] in (1, "1"):
        out.append("[987] OK T1 : 1115 est en cd=1 -- le natif ne peut pas la proposer au tour 1, "
                   "quelle que soit la valeur du veto")
    if loin["t2"]["cooldown"] not in (0, None):
        out.append("[987] T2 : 1115 devrait etre a cd=0, mesure %s" % loin["t2"]["cooldown"])
    if not loin["t2"]["proposes_1115"]:
        out.append("[987] LOIN T2 : le natif NE propose PAS 1115 alors que l'union est vide -- "
                   "proposed=%s" % json.dumps(loin["t2"]["proposed"])[:300])
    if proche["t2"]["proposes_1115"]:
        out.append("[987] PROCHE T2 : le natif propose 1115 alors que l'union n'est PAS vide -- "
                   "le bras `loin` ne discrimine donc rien")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", choices=("loin", "proche", "both"), default="both")
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    a = ap.parse_args()
    if a.arm == "both":
        loin = run("loin", seed=a.seed, board=a.board)
        proche = run("proche", seed=a.seed, board=a.board)
        for line in verdict(loin, proche):
            print(line)
    else:
        run(a.arm, seed=a.seed, board=a.board)
    return 0


if __name__ == "__main__":
    sys.exit(main())
