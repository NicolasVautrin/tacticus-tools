#!/usr/bin/env python
"""Probe #10019-r2 -- la face PREDICTION du canal #179 gagne-t-elle le COUP, ou seulement sa VALEUR ?

CE QUE #10019 A MESURE, ET CE QU'IL RESTAIT. #10019 a etabli, sur `MasterAnnihilator`, que le natif
PREDIT un coup de plus (rapports entiers `(h+1)/h` sur les DEUX bornes). La fiche de `#10019-r2`
interdisait de generaliser aux DEUX autres porteurs du meme noeud. La lecture du corps PARTAGE
`IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(entities, isPrediction)` rend la
generalisation inutile -- `trigger` et `hitsFormula` y sont evalues A L'IDENTIQUE sur les deux
faces, `isPrediction` ne choisissant qu'entre `predictionDamageFormula` et `damageFormula` -- mais
elle ne remplace pas une MESURE.

LE CRITERE, ET POURQUOI IL EST BINAIRE. `aiPlaybookPredict` rend `appliedHits` : le nombre de coups
que le PLAYBOOK NATIF compte pour cette paire. On fait varier UN SEUL axe -- la POSITION du porteur
d'`AstartesBanner` autour de son rayon 2 -- et on relit. Si `appliedHits` monte de `h` a `h+1`
quand le porteur entre dans le rayon, la face PREDICTION compte bien le coup. Sinon, le port de
`#10019-r2` sur-applique et doit etre retire.

C'est le MEME deplacement que `probe_204_ah_channel.py --case astartes`, lu sur la PREDICTION au
lieu des evenements de degat -- donc un bras DISCRIMINANT par construction : #204 a mesure la face
COMBAT sur ce montage-la meme.

⚠ TEMOIN DE NON-DEGENERESCENCE : on imprime aussi la prediction de l'attaquant quand le porteur est
LOIN. Si les deux phases rendent le meme `appliedHits` ET les memes bornes, le montage n'a rien
fait varier (porteur non deplace, attaquant hors melee) -- le probe le DIT au lieu de conclure.

ASCII only. Usage (depuis `scripts/python`) :
    python probe_10019r2_prediction_hits_live.py --runner <id>
    python probe_10019r2_prediction_hits_live.py --build            # monte son propre runner
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                   # noqa: E402
from rl_collect_batch import _resolve_session, _rpc             # noqa: E402

PYDIR = Path(__file__).resolve().parent
PORTEUR = "templAncient"          # porteur d'`AstartesBanner`
ATTAQUANT = "ultraApothecary"     # temoin : 1 coup melee, aucune mecanique parasite
CIBLE = "bloodSanguinary"
RAYON = 2                         # `ConfigConst(0x16 = range)` du `SurroundingFriends`
SID = None


def rpc(method, body, timeout=90):
    r = _rpc(SID, method, body, timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def build(seed: int, state: Path) -> int | None:
    out = subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "build",
                          "--seed", str(seed), "--state-file", str(state),
                          "--p-units", f"{PORTEUR},{ATTAQUANT}", "--a-units", CIBLE,
                          "--board", "MC1_67", "--hp-target", "900000", "--hp-player", "900000",
                          "--crit", "0,0", "--block-target", "0,0"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    for ln in (out.stdout or "").splitlines():
        if "runnerId=" in ln:
            return int(ln.split("runnerId=")[1].split()[0])
    print("[build KO]", (out.stdout or "")[-400:], (out.stderr or "")[-400:])
    return None


def _bornes(pred) -> tuple:
    """(appliedHits, healthDmgMin, healthDmgMax) agreges sur les `ProbableDamageEvent`.

    Les noms de champ sont ceux que le RPC rend VERBATIM (`appliedHits`, `healthDmgMin`,
    `healthDmgMax`) -- pas de repli sur une forme imbriquee : un champ renomme doit se voir en
    rendant `0`, pas se faire deviner."""
    evs = (pred or {}).get("events") or []
    hits = sum(int(e.get("appliedHits") or 0) for e in evs)
    mn = sum(int(e.get("healthDmgMin") or 0) for e in evs)
    mx = sum(int(e.get("healthDmgMax") or 0) for e in evs)
    return hits, mn, mx


def main(argv=None) -> int:
    global SID
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args(argv)

    SID = _resolve_session()
    rid = a.runner
    if rid is None:
        if not a.build:
            print("[10019-r2] donner --runner <id> ou --build")
            return 2
        sf = Path(a.state_file) if a.state_file else (PYDIR.parent.parent / "logs"
                                                     / "st_10019r2_astartes.json")
        rid = build(a.seed, sf)
        if rid is None:
            return 1
    print("[10019-r2] runner %s" % rid)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    att = next((u for u in units if u.get("visualId") == ATTAQUANT), None)
    car = next((u for u in units if u.get("visualId") == PORTEUR), None)
    en = next((u for u in units if u.get("visualId") == CIBLE), None)
    if att is None or car is None or en is None:
        print("[10019-r2] unites introuvables :", [u.get("visualId") for u in units])
        return 1
    aid, cid, tid = att["id"], car["id"], en["id"]
    a_norm = next((x for x in (att.get("abilities") or []) if x.get("kind") == "normal"), None)
    if a_norm is None:
        print("[10019-r2] pas d'attaque normale sur l'attaquant")
        return 1

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    walk = [(t.get("col"), t.get("row")) for t in (bg.get("tiles") or []) if t.get("walkable")]

    def etat():
        d = rpc("decisionView", {"runnerId": rid, "maxRank": 1})
        return {u["id"]: u for u in (d.get("units") or []) if u.get("alive")}

    # --- (1) l'ATTAQUANT au contact de la cible (le trigger porte `IsMeleeAttack`) -------------
    u = etat()
    T = upos(u[tid])
    occ = {upos(x) for x in u.values() if upos(x) is not None}
    adj = [c for c in walk if hexgeo.distance(c, T) == 1 and (c not in occ or c == upos(u[aid]))]
    if not adj:
        print("[10019-r2] aucune tuile libre adjacente a la cible")
        return 1
    A = upos(u[aid]) if upos(u[aid]) in adj else adj[0]
    if upos(u[aid]) != A:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": aid, "to": {"col": A[0], "row": A[1]}}}, 40)

    lignes = []
    for phase, dans in (("LOIN", False), ("PRES", True)):
        u = etat()
        occ = {upos(x) for x in u.values() if upos(x) is not None} - {upos(u[cid])}
        cand = [c for c in walk if c not in occ and c != A
                and ((hexgeo.distance(c, A) <= RAYON) if dans else (hexgeo.distance(c, A) > RAYON))]
        cand.sort(key=lambda c: hexgeo.distance(c, upos(u[cid])))
        if not cand:
            print("[10019-r2] phase %s : aucune tuile candidate" % phase)
            return 1
        if upos(u[cid]) != cand[0]:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": cid, "to": {"col": cand[0][0], "row": cand[0][1]}}}, 40)
        u = etat()
        d = hexgeo.distance(upos(u[cid]), upos(u[aid]))
        pred = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": aid, "targetId": tid,
                                         "abilityType": a_norm["id"]}, 60)
        hits, mn, mx = _bornes(pred)
        lignes.append((phase, d, hits, mn, mx))
        print("[10019-r2] %-5s porteur a %d hex de l'attaquant -> appliedHits=%s  healthDmg=[%s, %s]"
              % (phase, d, hits, mn, mx))

    (_p0, d0, h0, mn0, mx0), (_p1, d1, h1, mn1, mx1) = lignes
    if not (d0 > RAYON >= d1):
        print("[10019-r2] MONTAGE INVALIDE -- le porteur n'a pas traverse le rayon (%d puis %d)"
              % (d0, d1))
        return 1
    if (h0, mn0, mx0) == (h1, mn1, mx1):
        print("[10019-r2] AUCUNE VARIATION -- soit la face PREDICTION ne compte pas le coup, soit "
              "le montage n'a rien fait varier. NE PAS conclure sans lever l'ambiguite.")
        return 1
    print("[10019-r2] VERDICT : appliedHits %d -> %d (delta %+d) ; bornes [%d, %d] -> [%d, %d]"
          % (h0, h1, h1 - h0, mn0, mx0, mn1, mx1))
    if h0:
        print("[10019-r2] rapport des bornes : min x%.4f  max x%.4f  (attendu (h+1)/h = %.4f)"
              % ((mn1 / mn0 if mn0 else 0.0), (mx1 / mx0 if mx0 else 0.0), (h0 + 1) / h0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
