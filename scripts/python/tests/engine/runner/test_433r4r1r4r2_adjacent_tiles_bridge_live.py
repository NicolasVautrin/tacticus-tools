"""#433-r4-r1-r4-r2 -- CONFRONTATION du substrat d'adjacence a un oracle natif INDEPENDANT.

POURQUOI CE TEST EXISTE (le trou que la mesure de substrat ne peut pas fermer)
-----------------------------------------------------------------------------
Le canal `neigh_by_pos` du port est DERIVE de `boardGraph.neighbours`. Confronter le port a ce
meme champ ne prouve donc que le CABLAGE, jamais la FIDELITE : les deux cotes liraient la meme
entree, et l'accord serait degenere. Il faut un oracle natif qui n'y touche pas.

C'EST LE SPLASH DE `FragBomb` (1017, `astraBullgryn`). Decompile :

    splash = AdjacentUnits(Target@0x178, 0, 3) - Caster@0x160

`IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits` = `AdjacentTiles` puis `Units`, donc
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` -- exactement
l'iterateur que `battle_query.is_adjacent` mirroir. L'oracle est alors un fait de BATAILLE (les
events de degat), pas une lecture de capteur.

LE MONTAGE, et son unique point delicat -- on a besoin d'une arete que la COURONNE HEX porte et
que la LISTE STOCKEE ne porte pas, a `|dElev| < 2` (sinon la porte d'elevation, deja portee depuis
#433-r4-r1-r4, expliquerait tout et le cran serait vert pour la mauvaise raison) :

    T (cible)   sur `a`
    F (fantome) sur `b`  -- voisin GEOMETRIQUE de `a`, ABSENT de la liste stockee
    W (temoin)  sur `c`  -- voisin REEL de `a` (dans la liste stockee)
    caster      sur `d`  -- voisin reel de `a`, exclu du splash par le natif

ORACLE, a 1 bit : le natif frappe `W` et **jamais** `F`. Le port SANS canal les compte tous les
deux (c'est l'etat d'avant), AVEC canal il rend l'ensemble natif. Le temoin `W` est ce qui
interdit de lire un « F epargne » comme un splash simplement inerte.

L'arete est DERIVEE du board (jamais hardcodee) ; le board porte des `Bridge`, le terrain que
`IdunBattle.Operations.InitializeConnectivityOperation$$Execute` ne relie pas a son voisin de
niveau (`TileComponent$$HasEdge` exige des DEUX cotes).
"""
from __future__ import annotations

import json
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

FRAGBOMB = 1017
# `C3_14` porte 15 `Bridge` (le gisement le plus riche mesure) ; `C1_74` en porte 2. Les deux sont
# essayes : le montage exige 4 tuiles libres autour de `a`, ce qu'un board ne garantit pas.
BOARDS = ("C3_14", "C1_74")


def _tags(ev):
    td = ev.get("tags")
    return json.loads(td) if isinstance(td, str) else (td or {})


def t_ok(tiles, p) -> bool:
    """La tuile `p` existe-t-elle et est-elle marchable ? (tuile d'evacuation)"""
    for t in tiles:
        if (t["col"], t["row"]) == p:
            return bool(t.get("walkable"))
    return False


def _choisir_arete(tiles):
    """`(a, b, c)` : `b` voisin GEOMETRIQUE de `a` hors liste stockee (a `|dElev| < 2`), `c`
    voisin REEL. DERIVE du board -- rien n'est hardcode. `None` si le board n'en porte pas."""
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
        if fantomes and len(reels) >= 2:
            return a, fantomes[0], reels
    return None


@pytest.fixture(scope="module")
def scene_pont(build_runner, rpc):
    """Monte la geometrie decrite en tete et rend tout ce que les crans lisent."""
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
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        caster = next(u for u in units if u.get("visualId") == "astraBullgryn")
        ens = [u for u in units if u.get("owner") != caster.get("owner")]
        assert len(ens) >= 3, "il faut cible + fantome + temoin"
        cible, fantome, temoin = ens[0], ens[1], ens[2]
        # Les tuiles visees doivent etre LIBRES : une unite non deplacee qui stationne sur `a` ou
        # sur un voisin fait echouer un `move` en silence, et le splash mesure ne serait plus
        # celui du montage. On evacue donc TOUT LE MONDE loin de la zone d'abord.
        zone = {a, b, *reels[:2]}
        loin = [p for p in ((t["col"], t["row"]) for t in tiles)
                if t_ok(tiles, p) and p not in zone and hexgeo.distance(p, a) > 2]
        for u in units:
            if u["id"] in (cible["id"], fantome["id"], temoin["id"], caster["id"]):
                continue
            if loin:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": u["id"],
                    "to": {"col": loin[0][0], "row": loin[0][1]}}}, 60)
                loin.pop(0)
        for uid, p in ((cible["id"], a), (fantome["id"], b), (temoin["id"], reels[0]),
                       (caster["id"], reels[1])):
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 60)
        # On RELIT les positions : un `move` refuse en silence rendrait le cran vert a vide.
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
               for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")}
        voulu = {cible["id"]: a, fantome["id"]: b, temoin["id"]: reels[0],
                 caster["id"]: reels[1]}
        rate = {uid: (pos.get(uid), p) for uid, p in voulu.items() if pos.get(uid) != p}
        if rate:
            continue          # ce board ne se laisse pas monter -> on essaie le suivant
        # Personne d'AUTRE ne doit etre adjacent a la cible, sinon un tiers entrerait au splash.
        intrus = [uid for uid, p in pos.items()
                  if uid not in voulu and hexgeo.distance(p, a) <= 1]
        if intrus:
            continue
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster["id"], "targetId": cible["id"],
            "abilityType": FRAGBOMB}}, 120)
        frappes = set()
        for act in (res.get("actions") or []):
            for ev in (act.get("events") or []):
                td = _tags(ev)
                if td.get("Active_Ability_Type") == FRAGBOMB and "Amount" in td:
                    frappes.add(int(td["Target_Id"]))
        return {"board": board, "a": a, "b": b, "c": reels[0], "tiles": tiles,
                "cible": cible["id"], "fantome": fantome["id"], "temoin": temoin["id"],
                "frappes": frappes, "cast_ok": bool(res.get("ok"))}
    pytest.fail("aucun board de %s ne porte le montage (arete fantome + 2 voisins reels)"
                % (BOARDS,))


def test_le_montage_est_DISCRIMINANT(scene_pont):
    """Sans ce cran, tout le reste pourrait etre vert pour la mauvaise raison : il faut que `b`
    soit VRAIMENT dans la couronne de `a` (donc que l'ancien port l'ait compte voisin) et que la
    porte d'elevation, elle, ne l'explique PAS."""
    s = scene_pont
    bd = Board(s["tiles"])
    elev = bd.elev_by_pos()
    assert hexgeo.distance(s["a"], s["b"]) == 1, "b n'est pas dans la couronne de a"
    assert abs(elev[s["a"]] - elev[s["b"]]) < 2, "la porte d'elevation expliquerait l'ecart"
    assert bq.is_adjacent(s["a"], s["b"], elev, None) is True, "l'ancien port ne mordait pas ici"


def test_le_natif_EPARGNE_le_voisin_geometrique_hors_liste_stockee(scene_pont):
    """L'ORACLE, et il ne lit aucun capteur de board : `AdjacentUnits(Target)` en bataille."""
    s = scene_pont
    assert s["cast_ok"], "le cast n'a pas abouti -- rien a conclure"
    assert s["temoin"] in s["frappes"], \
        "le TEMOIN (voisin reel) n'est pas frappe : le splash est inerte, cran sans valeur"
    assert s["fantome"] not in s["frappes"], \
        "le natif a frappe le voisin GEOMETRIQUE hors liste stockee (%s)" % (s["frappes"],)


def test_le_port_AVEC_canal_accorde_avec_le_natif(scene_pont):
    s = scene_pont
    bd = Board(s["tiles"])
    canal = adjacent_neigh_by_pos(bd)
    assert bq.is_adjacent(s["a"], s["b"], bd.elev_by_pos(), canal) is False    # comme le natif
    assert bq.is_adjacent(s["a"], s["c"], bd.elev_by_pos(), canal) is True     # comme le natif


def test_le_port_SANS_canal_DIVERGE_du_natif(scene_pont):
    """Le CONTRE-BRAS : sans lui, l'accord ci-dessus ne prouverait pas que le canal MORD."""
    s = scene_pont
    bd = Board(s["tiles"])
    assert bq.is_adjacent(s["a"], s["b"], bd.elev_by_pos(), None) is True      # != natif
