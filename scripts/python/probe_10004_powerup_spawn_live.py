"""#10004 -- CONFRONTATION live des `PowerUp_*Spawn*` (natif vs port).

Montage de #1083-r1/r3 (le BOARD n'y est pour rien) : `catalog_inject` + `rl_duel build
--explicit-stats --a-units`, power-up pose A COTE du ramasseur.

⚠ **DEUX PIEGES DE CANAL, tous deux MESURES sur ce montage** :

 1. `decisionView` rend **ZERO unite** apres le crush (le stage passe a 2), alors qu'`observeBattle`
    en rend quatre. Lire le premier ferait conclure « rien n'a spawne » sur un spawn REUSSI. Toutes
    les mesures d'existence passent donc par `observeBattle`.
 2. On injecte au catalogue le power-up **ET l'unite qu'il spawne** : sans son entree, la fabrique
    ne construit rien, **sans la moindre erreur** (piege deja paye en #1083-r1).

⚠ **TEMOIN NON DEGENERE, monte AVANT toute comparaison** : `GetSpawnTile` peut ne rendre aucune
tuile et le gate `IsInTeam(Actor, 1)` peut etre faux -- deux regimes ou RIEN ne spawne et ou les
deux cotes « accordent » sur du vide. Le probe exige donc qu'une entite soit REELLEMENT apparue
cote natif avant de valider quoi que ce soit.

CONTRE-EPREUVE (`--regime hors-tuile`) : le ramasseur va sur une tuile VOISINE. Natif et port
doivent etre INERTES (aucun spawn, aucun kill) et le power-up SURVIVRE.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PYDIR))

from rl_collect_batch import _rpc, _resolve_session                      # noqa: E402
from engine.runner.components import UnitComponent                       # noqa: E402
from engine.runner.messages import MoveUnitMessage                       # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                   # noqa: E402
from engine.runner.runner import Runner                                  # noqa: E402
from engine.runner.snapshot import bind_live_rpc, load_state             # noqa: E402

#: cas -> (unite power-up, unite SPAWNEE a injecter aussi, nom gameconfig du passif)
CAS = {
    "uthar": ("powupHeroSpawn_Uthar", "votanUthar", "PowerUp_HeroSpawn_Uthar"),
    "inceptor": ("powupSummonSpawn_ultraSmnInceptor", "ultraSmnInceptor",
                 "PowerUp_SummonSpawn_ultraSmnInceptor"),
}
BOARD, SEED, RAMASSEUR = "MC1_67", "777", "ultraCalgar"
TUILE_POWUP, TUILE_HERO, TUILE_VOISINE = (2, 1), (1, 1), (0, 1)


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def preparer(sf: Path, sbc: Path, cas: str) -> int:
    powup, spawne, _ = CAS[cas]
    if not sbc.exists():
        r = subprocess.run([sys.executable, "catalog_inject.py", "--units",
                            "%s,%s" % (powup, spawne), "--out", str(sbc)],
                           cwd=str(_PYDIR), capture_output=True, text=True)
        if r.returncode:
            print("INJECT KO rc=%d %s" % (r.returncode, (r.stderr or "")[-400:]))
            return r.returncode
    r = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
                        "--no-ai", "--seed-bc", str(sbc), "--state-file", str(sf),
                        "--explicit-stats", powup, "--p-units", RAMASSEUR,
                        "--a-units", "%s,orksNob" % powup,
                        "--a-place", "%s:%d,%d" % (powup, *TUILE_POWUP),
                        "--place", "%s:%d,%d" % (RAMASSEUR, *TUILE_HERO)],
                       cwd=str(_PYDIR), capture_output=True, text=True)
    if r.returncode:
        print("BUILD KO rc=%d %s" % (r.returncode, (r.stderr or r.stdout or "")[-600:]))
    return r.returncode


def _obs(rpc, rid):
    """`observeBattle` -- LE canal d'existence. `decisionView` se vide apres le crush."""
    ob = rpc("observeBattle", {"runnerId": rid}, 60) or {}
    return {int(u.get("entityId", u.get("id"))): {"vis": u.get("visualId"),
                                                  "dead": bool(u.get("isDead"))}
            for u in (ob.get("units") or [])}


def _vivants_port(state):
    out = {}
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        if uc is None:
            continue
        out[int(e.id)] = {"vis": getattr(uc, "visual_id", None), "dead": not bool(uc.alive)}
    return out


def mesurer(rid: int, rpc, cas: str, regime: str) -> dict:
    powup_id, spawne_id, passif = CAS[cas]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                              "includeInactive": True}, 90)
    units = dv.get("units") or []
    pw = next((u for u in units if (u.get("visualId") or "") == powup_id), None)
    he = next((u for u in units if (u.get("visualId") or "") == RAMASSEUR), None)
    if pw is None or he is None:
        return {"erreur": "montage: powup=%s hero=%s" % (pw is not None, he is not None)}
    if he.get("team") is None:
        return {"erreur": "team du ramasseur illisible -- le gate IsInTeam serait indecidable"}

    ppos = pw.get("pos") or {}
    cible = ((ppos.get("col"), ppos.get("row")) if regime == "nominal" else TUILE_VOISINE)

    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    from engine.entities.pathfinding.board import Board                   # noqa: PLC0415
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return {"erreur": "boardGraph indisponible -- AUCUNE mesure n'a eu lieu"}
    state = load_state(dv, ob0, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    avant_nat = _obs(rpc, rid)
    avant_port = _vivants_port(state)

    # --- PORT : rejoue le MEME deplacement depuis la MEME capture -------------------------------
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if isinstance(s0, dict) and s0.get("ok"):
        rng = IntBasedMersenneTwister()
        rng.mt, rng.mti = list(s0["mt"]), s0["mti"]
        state.rng = rng
    Runner(state).install_default_handlers(20).apply(
        MoveUnitMessage(he["id"], (int(cible[0]), int(cible[1]))))
    apres_port = _vivants_port(state)

    # --- NATIF ----------------------------------------------------------------------------------
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": he["id"], "to": {"col": int(cible[0]), "row": int(cible[1])}}}, 120)
    if not (isinstance(res, dict) and res.get("ok")):
        return {"erreur": "move live KO: %s" % str(res)[:200]}
    apres_nat = _obs(rpc, rid)

    def neuves(av, ap):
        return sorted((ap[i]["vis"] or "?") for i in ap if i not in av)

    def morts(av, ap):
        """Les unites MORTES A LA FIN, power-up EXCLU.

        ⚠ ON COMPARE L'ETAT FINAL, PAS LE DELTA -- et c'est une correction de MESURE, pas une
        indulgence : `observeBattle` marque le power-up (HP 0) `dead = True` des le snapshot
        INITIAL, alors que le port le voit vivant jusqu'au crush. Un comparateur en delta rendait
        donc le power-up « tue par le port et pas par le natif » sur un port PARFAITEMENT juste.
        Il est exclu des deux cotes parce que sa mort EST le vecteur du trigger, pas un effet du
        behaviour qu'on confronte.

        ⚠ L'exclusion se fait par VISUAL-ID, pas par id d'entite : `decisionView` et
        `observeBattle` ne numerotent PAS les memes entites de la meme facon (mesure : le power-up
        y porte `81` d'un cote et `82` de l'autre). Exclure par id laissait donc passer le power-up
        cote natif."""
        del av
        return sorted((ap[i]["vis"] or "?") for i in ap
                      if ap[i]["dead"] and ap[i]["vis"] != powup_id)

    return {"cas": cas, "regime": regime, "passif": passif, "hero": he["id"],
            "team_hero": he.get("team"), "powup": pw["id"], "tuile_visee": list(cible),
            "spawnee_attendue": spawne_id,
            "spawns_natif": neuves(avant_nat, apres_nat),
            "spawns_port": neuves(avant_port, apres_port),
            "tues_natif": morts(avant_nat, apres_nat),
            "tues_port": morts(avant_port, apres_port),
            "powup_vivant_natif": (not apres_nat.get(pw["id"], {}).get("dead", True))
            if pw["id"] in apres_nat else None}


def _verdict(out, regime) -> int:
    sn, sp = out["spawns_natif"], out["spawns_port"]
    tn, tp = out["tues_natif"], out["tues_port"]
    print("  SPAWNS  natif=%s port=%s" % (sn, sp))
    print("  TUES    natif=%s port=%s" % (tn, tp))
    if regime == "hors-tuile":
        if sn or sp or tn or tp:
            print("  VERDICT: DIVERGENCE hors tuile -- il ne devait RIEN se passer")
            return 1
        print("  VERDICT: ACCORD (les deux INERTES hors tuile)")
        return 0
    if not sn:
        print("  VERDICT: TEMOIN DEGENERE -- le natif n'a RIEN spawne, la comparaison est vide")
        return 4
    if out["spawnee_attendue"] not in sn:
        print("  VERDICT: TEMOIN SUSPECT -- le natif a spawne %s, pas %s"
              % (sn, out["spawnee_attendue"]))
        return 4
    if sn == sp and tn == tp:
        print("  VERDICT: ACCORD")
        return 0
    print("  VERDICT: DIVERGENCE")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cas", required=True, choices=sorted(CAS))
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed-bc", required=True)
    ap.add_argument("--regime", default="nominal", choices=("nominal", "hors-tuile"))
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()
    sf, sbc = Path(a.state_file), Path(a.seed_bc)
    if not a.no_build and preparer(sf, sbc, a.cas):
        return 2
    if not sf.exists():
        print("ABSENT: %s" % sf)
        return 2
    rid = int(json.loads(sf.read_text(encoding="utf-8"))["runnerId"])
    sess = _resolve_session()

    def rpc(name, params, to=90):
        return _unwrap(_rpc(sess, name, params, to))

    bind_live_rpc(lambda m, b=None, t=60: rpc(m, b if b is not None else {}, int(t)))
    print("runner=%d session=%s cas=%s regime=%s" % (rid, sess, a.cas, a.regime))
    out = mesurer(rid, rpc, a.cas, a.regime)
    for k in sorted(out):
        print("  %-20s %s" % (k, out[k]))
    rc = 3 if "erreur" in out else _verdict(out, a.regime)
    try:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        print("  runner %d dispose" % rid)
    except Exception as e:                       # noqa: BLE001 -- on DIT l'echec
        print("  dispose KO: %s" % str(e)[:160])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
