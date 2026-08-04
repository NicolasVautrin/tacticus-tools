"""#433-r4-r1-r4-r2-r1 -- CONFRONTATION d'`UpdateCharging` a un oracle natif INDEPENDANT du canal.

POURQUOI CET ORACLE-LA
----------------------
Le canal `neigh_by_pos` du port est DERIVE de `boardGraph.neighbours`. S'y confronter ne prouve
que le CABLAGE. #433-r4-r1-r4-r2 avait resolu ce probleme pour `is_adjacent` par le splash de
`FragBomb` ; ici il faut un oracle du natif **`IdunBattle.Operations.MoveUnitOperation$$
UpdateCharging`** lui-meme, et il existe : la liste `UnitComponent.ChargedUnitIds@+0x190`, que le
capteur `combatSnapshot` publie (`units[].chargedUnitIds`). C'est un ETAT ECS ecrit par le natif
au moment du pas -- il ne lit aucun champ de `boardGraph`.

C'est aussi le SEUL point d'observation direct de ce natif. Son unique lecteur natif
(`IdunBattle.Core.Services.BattleQuery$$IsCharging`) re-teste l'adjacence par
`MovementUtil$$AreTilesAdjacent`, sur le MEME substrat : sur une arete que la liste stockee ne
porte pas, il rendrait FAUX par son PREMIER terme, quel que soit le contenu de la liste. Le
contenu de `ChargedUnitIds` est donc inobservable via le degat -- il faut le lire.

LE MONTAGE (la geometrie est DERIVEE du board, jamais hardcodee)

    a  = tuile d'ARRIVEE du mover
    b  = FANTOME : voisin GEOMETRIQUE de `a`, ABSENT de sa liste stockee, a `|dElev| < 2`
    c  = TEMOIN  : voisin REEL de `a` (present dans la liste stockee)
    s  = DEPART du mover, a distance >= 2 de `b` ET de `c` (sinon le pas ne cree rien de neuf)

ORACLE, a 1 bit : apres le pas `s -> a`, le natif met le TEMOIN dans `ChargedUnitIds` et **jamais**
le FANTOME. Le temoin est ce qui interdit de lire un « fantome absent » comme une liste
simplement vide. Le port SANS canal les met tous les deux (l'etat d'avant), AVEC canal il rend
l'ensemble natif.

⚠ La liste n'est videe que par `IdunBattle.Operations.FinishUnitTurnOperation$$Execute`. Le
montage exploite cela au lieu de le subir : le mover est d'abord place sur `s`, ou personne n'est
a portee, donc ce premier pas n'ajoute RIEN ; ce que la liste contient a la fin est donc
exactement ce que le pas `s -> a` a produit. Un cran le verifie.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from engine import battle_query as bq                                            # noqa: E402
from engine.entities.pathfinding.board import (Board,                            # noqa: E402
                                               adjacent_neigh_by_pos)

BOARDS = ("C3_14", "C1_74")


def _walkable(tiles):
    return {(t["col"], t["row"]): bool(t.get("walkable")) for t in tiles}


def _choisir_arete(tiles):
    """`(a, fantome, reels)` : `fantome` voisin GEOMETRIQUE de `a` hors liste stockee (a
    `|dElev| < 2`), `reels` les voisins presents dans la liste. DERIVE du board."""
    bd = Board(tiles)
    by_pos = {(t["col"], t["row"]): t for t in tiles}
    elev = {(t["col"], t["row"]): int(t.get("elevation") or 0) for t in tiles}
    neigh = adjacent_neigh_by_pos(bd) or {}
    for a, stockes in sorted(neigh.items()):
        if not by_pos.get(a, {}).get("walkable"):
            continue
        vus = {(q[0], q[1]) for q in stockes}
        geo = [p for p in hexgeo.neighbors(a[0], a[1]) if p in by_pos]
        fantomes = [p for p in geo if p not in vus and by_pos[p].get("walkable")
                    and abs(elev[a] - elev[p]) < 2]
        reels = [p for p in geo if p in vus and by_pos[p].get("walkable")]
        if fantomes and reels:
            return a, fantomes[0], reels
    return None


def _pos_by_id(dv):
    return {u["id"]: (u["pos"]["col"], u["pos"]["row"])
            for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")}


@pytest.fixture(scope="module")
def scene_charge(build_runner, rpc):
    """Monte la geometrie decrite en tete, JOUE le pas, et rend ce que les crans lisent."""
    for board in BOARDS:
        r = build_runner(seed="777", board=board, extra=[
            "--p-units", "astraBullgryn,astraCreed",
            "--a-units", "necroOverlord,necroWarden,necroDestroyer,necroSpyder",
            "--hp-target", "90000", "--hp-player", "90000", "--no-ai"])
        rid = r["rid"]
        tiles = (rpc("boardGraph", {"runnerId": rid}, 90) or {}).get("tiles") or []
        choix = _choisir_arete(tiles)
        if choix is None:
            continue
        a, b, reels = choix
        c = reels[0]
        walk = _walkable(tiles)
        # `s` : un depart marchable a distance >= 2 de `b` ET de `c`, mais atteignable depuis `a`.
        cands = [p for p, ok in walk.items() if ok and hexgeo.distance(p, b) >= 2
                 and hexgeo.distance(p, c) >= 2 and 1 <= hexgeo.distance(p, a) <= 3
                 and p not in (a, b, c)]
        if not cands:
            continue
        s = sorted(cands, key=lambda p: (hexgeo.distance(p, a), p))[0]
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        mover = next(u for u in units if u.get("visualId") == "astraBullgryn")
        ens = [u for u in units if u.get("owner") != mover.get("owner")]
        if len(ens) < 2:
            continue
        fantome, temoin = ens[0], ens[1]
        # Evacuation : une unite qui stationne dans la zone fausserait la mesure (elle entrerait
        # dans `ChargedUnitIds` sans etre au montage) ou bloquerait un placement en silence.
        zone = {a, b, c, s}
        loin = [p for p, ok in walk.items() if ok and p not in zone
                and hexgeo.distance(p, a) > 3]
        for u in units:
            if u["id"] in (mover["id"], fantome["id"], temoin["id"]) or not loin:
                continue
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": u["id"],
                "to": {"col": loin[0][0], "row": loin[0][1]}}}, 60)
            loin.pop(0)
        for uid, p in ((fantome["id"], b), (temoin["id"], c), (mover["id"], s)):
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 60)
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        pos = _pos_by_id(dv)
        voulu = {fantome["id"]: b, temoin["id"]: c, mover["id"]: s}
        if any(pos.get(uid) != p for uid, p in voulu.items()):
            continue          # ce board ne se laisse pas monter -> on essaie le suivant
        if any(hexgeo.distance(p, a) <= 1 for uid, p in pos.items() if uid not in voulu):
            continue          # un tiers adjacent a `a` polluerait la liste
        avant = rpc("combatSnapshot", {"runnerId": rid}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mover["id"], "to": {"col": a[0], "row": a[1]}}}, 60)
        apres = rpc("combatSnapshot", {"runnerId": rid}, 60)
        dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

        def _charged(snap):
            for u in (snap.get("units") or []):
                if int(u.get("entityId") or u.get("id") or -1) == int(mover["id"]):
                    ch = u.get("chargedUnitIds")
                    return None if ch is None else {int(i) for i in ch}
            return None

        return {"board": board, "a": a, "b": b, "c": c, "s": s, "tiles": tiles,
                "mover": mover["id"], "fantome": fantome["id"], "temoin": temoin["id"],
                "charged_avant": _charged(avant), "charged_apres": _charged(apres),
                "arrive": _pos_by_id(dv2).get(mover["id"])}
    pytest.fail("aucun board de %s ne porte le montage (arete fantome + depart eloigne)"
                % (BOARDS,))


def test_le_montage_est_DISCRIMINANT(scene_charge):
    """Sans ce cran, tout le reste serait vert pour la mauvaise raison : il faut que le FANTOME
    soit VRAIMENT dans la couronne de `a` (donc que l'ancien port l'ait charge), que la porte
    d'elevation ne l'explique PAS, et que le pas ait bien eu lieu."""
    s = scene_charge
    bd = Board(s["tiles"])
    elev = bd.elev_by_pos()
    assert s["arrive"] == s["a"], "le mover n'est pas arrive sur `a` : rien a conclure"
    assert hexgeo.distance(s["a"], s["b"]) == 1, "le fantome n'est pas dans la couronne de `a`"
    assert abs(elev[s["a"]] - elev[s["b"]]) < 2, "la porte d'elevation expliquerait l'ecart"
    assert hexgeo.distance(s["s"], s["b"]) >= 2 and hexgeo.distance(s["s"], s["c"]) >= 2, \
        "le depart etait deja au contact : le pas ne cree aucune adjacence NOUVELLE"


def test_la_liste_etait_VIDE_avant_le_pas(scene_charge):
    """Le premier placement (loin de tout) ne doit RIEN avoir charge, sinon ce que la liste
    contient a la fin ne serait pas imputable au pas mesure. `None` = capteur muet -> on le DIT."""
    s = scene_charge
    assert s["charged_avant"] is not None, \
        "combatSnapshot ne publie pas `chargedUnitIds` : oracle indisponible, pas un verdict"
    assert s["charged_avant"] == set(), \
        "la liste n'etait pas vide avant le pas (%s)" % (s["charged_avant"],)


def test_le_natif_NE_CHARGE_PAS_le_voisin_geometrique_hors_liste_stockee(scene_charge):
    """L'ORACLE. `GetAdjacentUnits` -> `IterateAdjacentTiles` -> la liste STOCKEE."""
    s = scene_charge
    assert s["charged_apres"] is not None, "oracle indisponible"
    assert s["temoin"] in s["charged_apres"], \
        "le TEMOIN (voisin reel) n'a pas ete charge : la mesure est inerte, cran sans valeur"
    assert s["fantome"] not in s["charged_apres"], \
        "le natif a charge le voisin GEOMETRIQUE hors liste stockee (%s)" % (s["charged_apres"],)


def test_le_port_AVEC_canal_accorde_avec_le_natif(scene_charge):
    s = scene_charge
    bd = Board(s["tiles"])
    others = {s["fantome"]: s["b"], s["temoin"]: s["c"]}
    got = bq.newly_adjacent_ids(s["s"], s["a"], others, bd.elev_by_pos(),
                                adjacent_neigh_by_pos(bd))
    assert got == {s["temoin"]}, "port avec canal = %s, natif = %s" % (got, s["charged_apres"])
    assert got == (s["charged_apres"] & set(others)), "desaccord avec l'oracle natif"


def test_le_port_SANS_canal_DIVERGE_du_natif(scene_charge):
    """Le CONTRE-BRAS : sans lui, l'accord ci-dessus ne prouverait pas que le canal MORD."""
    s = scene_charge
    others = {s["fantome"]: s["b"], s["temoin"]: s["c"]}
    got = bq.newly_adjacent_ids(s["s"], s["a"], others)
    assert got == {s["temoin"], s["fantome"]}, \
        "l'etat d'avant ne divergeait pas ici : le montage ne discrimine rien"


def test_is_charging_suit_le_meme_substrat(scene_charge):
    """`BattleQuery$$IsCharging` re-teste l'adjacence : sur l'arete fantome il rend FAUX par son
    PREMIER terme, MEME si la liste contenait la cible. C'est ce qui rend le contenu de
    `ChargedUnitIds` inobservable par le degat -- et ce qui exige l'oracle de ce fichier."""
    s = scene_charge
    bd = Board(s["tiles"])
    elev, canal = bd.elev_by_pos(), adjacent_neigh_by_pos(bd)
    force = [s["fantome"], s["temoin"]]         # liste FORCEE : on isole le 1er terme
    assert bq.is_charging(s["a"], s["b"], s["fantome"], force, elev, canal) is False
    assert bq.is_charging(s["a"], s["c"], s["temoin"], force, elev, canal) is True
    assert bq.is_charging(s["a"], s["b"], s["fantome"], force, elev, None) is True   # avant
