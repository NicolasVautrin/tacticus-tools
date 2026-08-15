"""#605-r1 -- le DISCRIMINANT : un porteur pose par `--place` emet-il moins de coups que le meme
porteur laisse a son SpawnPoint, et si oui, POURQUOI ?

CE QUE LA FICHE A MESURE. A montage par ailleurs IDENTIQUE (meme `HellfireShells.Constants`, meme
`--seed`, meme distance porteur-cible, cible sans `BigTarget`, armure et block a zero),
`rl_duel build --place ultraNpc4HeavyIntercessor:33:3,4` rend **1** event `UnitDamaged` la ou le
meme build SANS `--place` en rend **2** -- soit `nrOfHits`, la valeur du decompile. Deux lectures
restaient ouvertes :

  (a) ARTEFACT DE HARNAIS -- le placement force laisse l'unite dans un etat que le pipeline
      d'attaque lit differemment, et alors c'est `rl_duel` qui doit le dire ;
  (b) CANAL NATIF -- un `hitsReduction` positionnel, et alors c'est le PORT qui diverge.

LE DISCRIMINANT, ecrit dans la fiche : rejouer le meme cast en faisant BOUGER le porteur d'une
tuile depuis sa position `--place`. Ce probe joue les TROIS bras a geometrie et graine identiques :

  A  SPAWN   -- porteur au SpawnPoint, rapproche jusqu'a portee (il a donc BOUGE) ;
  B  PLACE   -- porteur pose par `--place` a la meme distance, cast SANS avoir bouge ;
  C  PLACE+  -- porteur pose par `--place`, DEPLACE d'une tuile, puis cast.

`hasMoved` est LU sur l'etat live juste avant chaque cast (`decisionView`), jamais deduit de la
sequence d'actions -- c'est la variable que les trois bras separent.

Usage (depuis `scripts/python`) :

    python probe_605r1_place_vs_spawn.py --state-file <ABSOLU>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import hexgeo
import rl_duel as R
from probe_605_hellfire_hits import (
    ABILITY, BOARD, CIBLE_SANS, PORTEUR, PORTEUR_VIS, PORTEE, _coups, _pos, _rapproche, _vue,
)


def _unite(dv: dict, uid: int) -> dict:
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), {})


def _a_bouge(dv: dict, uid: int) -> bool | None:
    """`hasMoved` LU, tri-etat : `None` = le champ n'existe pas, jamais rabattu sur False."""
    u = _unite(dv, uid)
    for cle in ("hasMoved", "moved"):
        if u.get(cle) is not None:
            return bool(u[cle])
    return None


def _ids(dv: dict, cible: str) -> tuple:
    vivants = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u["id"] for u in vivants if (u.get("visualId") or "") == PORTEUR_VIS), None)
    tg = next((u["id"] for u in vivants if (u.get("visualId") or "") == cible), None)
    return me, tg


def _build(state_file: str, place: tuple | None, a_place: tuple | None = None) -> int:
    argv = ["build", "--board", BOARD, "--seed", "777", "--no-ai",
            "--explicit-stats", PORTEUR, "--p-units", PORTEUR, "--a-units", CIBLE_SANS,
            "--armor-target", "0", "--block-target", "0,0", "--hp-target", "400000",
            "--state-file", state_file]
    if place is not None:
        argv += ["--place", "%s:%d,%d" % (PORTEUR, place[0], place[1])]
    if a_place is not None:
        argv += ["--a-place", "%s:%d,%d" % (CIBLE_SANS, a_place[0], a_place[1])]
    rc = R.main(argv)
    if rc != 0:
        raise SystemExit("[605-r1] build rc=%d (place=%r)" % (rc, place))
    return json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"]


def _cast(rpc, rid: int, me: int, tg: int) -> dict:
    res = rpc("applyAction", {"runnerId": rid,
                              "action": {"kind": "ability", "casterId": me, "targetId": tg,
                                         "abilityType": ABILITY}}, 240)
    a0 = ((res or {}).get("actions") or [{}])[0]
    if not a0.get("ok"):
        raise SystemExit("[605-r1] le natif REFUSE le cast : %r" % (a0,))
    return res


def _deplace_d_une_tuile(rpc, rid: int, me: int, tg: int) -> tuple:
    """DEPLACE le porteur d'une tuile en RESTANT a portee de la cible. Rend `(avant, apres)`.

    On ne se plaint jamais de la geometrie : si aucune tuile accessible ne garde la portee, on le
    DIT (la mesure est alors NON CONCLUANTE, pas un resultat).
    """
    dv = _vue(rpc, rid)
    avant = _pos(_unite(dv, me))
    tp = _pos(_unite(dv, tg))
    mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
    tiles = set()
    for mu in (mov.get("units") or []):
        if mu.get("unitId") == me:
            tiles = {(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                     if t.get("col") is not None}
    cands = [t for t in tiles
             if t != avant and 1 <= hexgeo.distance(t, tp) <= PORTEE]
    if not cands:
        return avant, None
    cible_tuile = min(cands, key=lambda p: (hexgeo.distance(p, avant), hexgeo.distance(p, tp)))
    rpc("applyAction", {"runnerId": rid,
                        "action": {"kind": "move", "unitId": me,
                                   "to": {"col": cible_tuile[0], "row": cible_tuile[1]}}}, 60)
    return avant, _pos(_unite(_vue(rpc, rid), me))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    a = ap.parse_args(argv)
    sid = R._resolve_session()

    def rpc(m, p, t=60):
        return R._rpc(sid, m, [p], timeout=t)["result"]

    lignes = []

    # ---------------------------------------------------------------- A : SPAWN (porteur mobile)
    rid = _build(a.state_file, None)
    try:
        dv = _vue(rpc, rid)
        me, tg = _ids(dv, CIBLE_SANS)
        if me is None or tg is None:
            raise SystemExit("[605-r1] bras A : montage non installe")
        pos_spawn = _pos(_unite(dv, me))
        if not _rapproche(rpc, rid, me, tg):
            raise SystemExit("[605-r1] bras A : cible jamais amenee a portee")
        dv2 = _vue(rpc, rid)
        pa = _pos(_unite(dv2, me))
        pt = _pos(_unite(dv2, tg))
        res = _cast(rpc, rid, me, tg)
        lignes.append(("A SPAWN", pos_spawn, pa, hexgeo.distance(pa, pt),
                       _a_bouge(dv2, me), _coups(res, tg)))
        tuile_a = pa
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)

    # -------------------------------------- B : PLACE sur la tuile EXACTE d'ou le bras A a caste
    rid = _build(a.state_file, tuile_a)
    try:
        dv = _vue(rpc, rid)
        me, tg = _ids(dv, CIBLE_SANS)
        if me is None or tg is None:
            raise SystemExit("[605-r1] bras B : montage non installe")
        pa = _pos(_unite(dv, me))
        pt = _pos(_unite(dv, tg))
        d = hexgeo.distance(pa, pt)
        if not (1 <= d <= PORTEE):
            raise SystemExit("[605-r1] bras B : cible hors portee (d=%s) -- geometrie a revoir"
                             % d)
        res = _cast(rpc, rid, me, tg)
        lignes.append(("B PLACE", tuile_a, pa, d, _a_bouge(dv, me), _coups(res, tg)))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)

    # --------------------------- C : PLACE puis DEPLACEMENT d'une tuile -- LE discriminant ecrit
    rid = _build(a.state_file, tuile_a)
    try:
        dv = _vue(rpc, rid)
        me, tg = _ids(dv, CIBLE_SANS)
        if me is None or tg is None:
            raise SystemExit("[605-r1] bras C : montage non installe")
        avant, apres = _deplace_d_une_tuile(rpc, rid, me, tg)
        if apres is None:
            lignes.append(("C PLACE+", avant, None, None, None, None))
        else:
            dv2 = _vue(rpc, rid)
            pt = _pos(_unite(dv2, tg))
            res = _cast(rpc, rid, me, tg)
            lignes.append(("C PLACE+", avant, apres, hexgeo.distance(apres, pt),
                           _a_bouge(dv2, me), _coups(res, tg)))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)

    # ------------------- D : la GEOMETRIE EXACTE de la fiche -- `--place <porteur>:3,4`, cible
    # amenee par `--a-place` a la meme distance. C'est le seul bras qui reproduit son montage
    # LITTERALEMENT ; les trois precedents changent la tuile, et un phenomene positionnel pourrait
    # ne vivre que sur celle-la.
    tuile_fiche = (3, 4)
    cible_fiche = None
    for c in range(0, 8):
        for r in range(0, 10):
            if hexgeo.distance((c, r), tuile_fiche) == PORTEE:
                cible_fiche = (c, r)
                break
        if cible_fiche:
            break
    rid = _build(a.state_file, tuile_fiche, a_place=cible_fiche)
    try:
        dv = _vue(rpc, rid)
        me, tg = _ids(dv, CIBLE_SANS)
        if me is None or tg is None:
            lignes.append(("D FICHE", tuile_fiche, None, None, None, None))
        else:
            pa, pt = _pos(_unite(dv, me)), _pos(_unite(dv, tg))
            d = hexgeo.distance(pa, pt)
            if not (1 <= d <= PORTEE):
                lignes.append(("D FICHE", tuile_fiche, pa, d, None, None))
            else:
                res = _cast(rpc, rid, me, tg)
                lignes.append(("D FICHE", tuile_fiche, pa, d, _a_bouge(dv, me), _coups(res, tg)))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)

    # ------------- E/F : le montage LITTERAL de `test_605_hellfire_shells_live.py` -- DEUX porteurs
    # du meme unitId, DEUX cibles posees par `--a-place`. C'est celui-la, et pas le mien, qui a
    # produit la mesure de la fiche ; les bras A-D n'en partagent ni le roster ni la geometrie, donc
    # ils ne pouvaient pas la refuter a eux seuls. F ajoute `--place` sur le porteur, E ne l'a pas.
    for nom, place_porteur in (("E TEST", None), ("F TEST+PLACE", (3, 4))):
        argv = ["build", "--board", BOARD, "--seed", "777", "--no-ai",
                "--explicit-stats", PORTEUR,
                "--p-units", "%s,%s" % (PORTEUR, PORTEUR),
                "--a-units", "%s,%s" % (CIBLE_SANS, "astraBullgryn"),
                "--armor-target", "0", "--block-target", "0,0", "--hp-target", "200000",
                "--a-place", "%s:1,2" % CIBLE_SANS, "--a-place", "astraBullgryn:3,2",
                "--state-file", a.state_file]
        if place_porteur is not None:
            argv += ["--place", "%s:%d,%d" % (PORTEUR, place_porteur[0], place_porteur[1])]
        if R.main(argv) != 0:
            lignes.append((nom, place_porteur, None, None, None, None))
            continue
        rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
        try:
            dv = _vue(rpc, rid)
            vivants = [u for u in (dv.get("units") or []) if u.get("alive")]
            porteurs = [u["id"] for u in vivants if (u.get("visualId") or "") == PORTEUR_VIS]
            tg = next((u["id"] for u in vivants if (u.get("visualId") or "") == CIBLE_SANS), None)
            if len(porteurs) < 1 or tg is None:
                lignes.append((nom, place_porteur, None, None, None, None))
                continue
            me = porteurs[0]
            pa, pt = _pos(_unite(dv, me)), _pos(_unite(dv, tg))
            if not (1 <= hexgeo.distance(pa, pt) <= PORTEE) and not _rapproche(rpc, rid, me, tg):
                lignes.append((nom, place_porteur, pa, hexgeo.distance(pa, pt), None, None))
                continue
            dv2 = _vue(rpc, rid)
            pa, pt = _pos(_unite(dv2, me)), _pos(_unite(dv2, tg))
            res = _cast(rpc, rid, me, tg)
            lignes.append((nom, place_porteur, pa, hexgeo.distance(pa, pt),
                           _a_bouge(dv2, me), _coups(res, tg)))
        finally:
            rpc("disposeRunner", {"runnerId": rid}, 60)

    print("[605-r1] SIX BRAS, meme graine / meme board / meme cible (sans BigTarget)")
    for nom, depart, tuile, d, bouge, coups in lignes:
        if coups is None:
            print("  %-9s depart=%s -- NON CONCLUANT : aucune tuile accessible ne garde la portee"
                  % (nom, depart))
            continue
        print("  %-9s depart=%s cast_depuis=%s distance=%s hasMoved=%s -> %d coup(s) %r"
              % (nom, depart, tuile, d, bouge, len(coups), coups))
    print("[605-r1] LECTURE : si B rend moins de coups que A et que C REMONTE au compte de A, la "
          "variable est `a bouge ce tour` et non le placement -- lecture (a), artefact de "
          "harnais. Si B et C rendent le meme compte reduit, la variable est la POSITION ou le "
          "mode de pose -- lecture (b), canal natif a porter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
