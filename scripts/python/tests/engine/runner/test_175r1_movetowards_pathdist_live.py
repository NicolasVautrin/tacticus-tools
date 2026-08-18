"""#175-r1 -- CLIQUET LIVE de l'etage NEUF de la tranche : la DISTANCE DE CHEMIN par POSITION.

Le probe `probe_175r1_movetowards_pathdist_live.py` MESURE ; ce fichier GARDE.

CE QUI EST GARDE, ET POURQUOI C'EST CET ETAGE-LA
-------------------------------------------------
Les deux feuilles `MoveTowardsUnitUtility` (`BioMinefield_MoveTowardsTarget` = 62 et
`MasterOfTheTutelaries_MoveTowardsTarget` = 63 sur `t6dpr4k06g` -- **pas** 61/62, ordinaux d'un
build anterieur) valent `poids x GetMinDistanceToTarget(tuile, cible)`. Leur SCORE natif n'est
lisible par aucun canal : `LEAF_HOOKS` de `frida/hooks/features/scorer-damage-trace.ts` ne porte
que `TileEffects` et `CapturePointTile`, et y ajouter
`IdunBattle.AI.Utilities.MoveTowardsUnitUtility.u003CEvaluateMovementInStepsu003Ed__15$$MoveNext`
serait une edition `frida/hooks/*`, donc une FENETRE DE REINJECT.

Mais leur ETAGE NEUF, lui, EST confrontable : `#175-r1` a livre
`ignore_terrain_pathfinder.get_path_node_counts_by_pos`, le jumeau en domaine POSITION du moteur
`Board`. Le canal natif est `pathDistToEnemies`, qui invoque `IPathfinders.GetPath` avec le
litteral `PathfinderType = 1` (`IgnoreTerrain`) -- **le pathfinder meme** que
`IdunBattle.AI.Utilities.MoveTowardsUnitUtility$$GetMinDistanceToTarget` appelle. C'est donc une
confrontation de l'etage, pas un proxy.

TROIS ASSERTIONS, ET LA TROISIEME EXISTE POUR NE PAS SE MENTIR
---------------------------------------------------------------
1. le canal natif publie des tuiles (sinon tout ce qui suit serait vacant) ;
2. accord EXACT sur toutes les tuiles communes ;
3. les deux conventions DECALEES (`+1`, `-1`) doivent ECHOUER. Un accord `n/n` sur une carte de
   distances quasi constantes ne prouverait rien ; exiger que le decalage casse est ce qui
   etablit que le temoin DISCRIMINE. C'est aussi ce qui garde le `Count = aretes + 1`
   (extremites INCLUSES, `route+0x18` = `List._size`) -- un off-by-one y coute une tuile
   entiere de poids, soit -100 pour la feuille 62.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine import weights as W                                              # noqa: E402
from engine.ai import context as _ai_ctx                                     # noqa: E402
from engine.entities.pathfinding import ignore_terrain_pathfinder as ITP     # noqa: E402
from engine.playbook import scene as _scene                                  # noqa: E402
from engine.utilities import tile as T                                       # noqa: E402
from engine.utilities.utility_type import UtilityType                        # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # l'etage CONFRONTE : le jumeau en domaine POSITION du pathfinder IgnoreTerrain
        "scripts/python/engine/entities/pathfinding/ignore_terrain_pathfinder.py",
        # le producteur `_movetowards_pathdist_by_pos`, les deux feuilles, et les leaf_ctx qui
        # publient `neigh_by_pos` / `walkable_by_pos` / `elev_by_pos`
        "scripts/python/engine/utilities/tile.py",
        # le mirror dont le test fige les ordinaux 62/63
        "scripts/python/engine/utilities/utility_type.py",
        # le ctx live : c'est lui qui alimente `tile_leaf_ctx`
        "scripts/python/engine/ai/context.py",
        "scripts/python/engine/playbook/scene.py",
        # le montage
        "scripts/python/probe_175r1_movetowards_pathdist_live.py",
        "scripts/python/tests/engine/_move_tile_sweep_order.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Il confronte la distance de CHEMIN par position au canal natif "
              "`pathDistToEnemies` (PathfinderType=IgnoreTerrain) : le pathfinder porte, le "
              "producteur qui l'appelle, les cartes du leaf_ctx qui le nourrissent, et le "
              "mirror d'ordinaux que le 4e test fige.",
}

#: roster Chaos : le porteur de l'ACTIVE 1096 et un mover qui porte le trait `Chaos` (la gate
#: `OnlyUnitsWithAny = [Chaos, Daemon]` de la feuille 63 est ainsi REELLEMENT franchie).
PORTEUR = "thousInfernalMaster"
MOVER = "worldKharn"


def _mesure(rpc, rid: int, max_steps: int = 6) -> dict:
    sys.path.insert(0, str(PYDIR / "tests" / "engine"))
    from _move_tile_sweep_order import _apply_native                          # noqa: E402
    wt = W.load()
    for _ in range(max_steps):
        dry = rpc("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            return {"ok": False, "raison": "trajectoire finie (%s)" % dry.get("error")}
        uid = dry.get("activatedUnitId")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
        if me is None:
            _apply_native(rpc, rid, dry)
            continue
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        predictor = _scene.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
        ctx = _ai_ctx.build(lambda m, b, t: rpc(m, b, t), rid, dv, mov_by_unit, uid, wt, predictor)
        lc = T.tile_leaf_ctx(ctx)
        pde = rpc("pathDistToEnemies", {"runnerId": rid, "unitId": uid}, 120) or {}
        if not pde.get("ok"):
            _apply_native(rpc, rid, dry)
            continue
        nat = {(t["col"], t["row"]): t.get("pathDist")
               for t in (pde.get("tiles") or []) if t.get("pathDist") is not None}
        enn = [tuple(u["pos"]) for u in (lc.get("enemy_units") or []) if u.get("pos")]
        if not nat or not enn:
            _apply_native(rpc, rid, dry)
            continue
        occ = tuple([u["pos"] for u in (lc.get("friend_units") or []) if u.get("pos")]
                    + [u["pos"] for u in (lc.get("enemy_units") or []) if u.get("pos")])
        port: dict = {}
        for e in enn:
            for p, n in ITP.get_path_node_counts_by_pos(
                    e, neigh_by_pos=lc.get("neigh_by_pos"),
                    walkable_by_pos=lc.get("walkable_by_pos"),
                    elev_by_pos=lc.get("elev_by_pos"), occupied_positions=occ).items():
                if n is not None and (p not in port or n < port[p]):
                    port[p] = n
        communs = sorted(set(nat) & set(port))
        if communs:
            return {"ok": True, "uid": uid, "vis": me.get("visualId"), "nat": nat, "port": port,
                    "communs": communs, "lc": lc, "ctx": ctx, "wt": wt,
                    "neigh": bool(lc.get("neigh_by_pos"))}
        _apply_native(rpc, rid, dry)
    return {"ok": False, "raison": "aucun pas avec un canal `pathDistToEnemies` exploitable"}


@pytest.fixture(scope="module")
def mesure(rpc, build_runner):
    rid = build_runner("777", extra=["--p-units", "%s,%s" % (PORTEUR, MOVER),
                                     "--a-units", "orksNob"], board="MC1_67")["rid"]
    return _mesure(rpc, rid)


def test_le_canal_natif_publie_des_tuiles(mesure):
    """Sans lui, les deux assertions suivantes seraient VACANTES (un `0/0` passe pour un accord)."""
    assert mesure.get("ok"), "montage non obtenu : %s" % mesure.get("raison")
    assert len(mesure["communs"]) >= 5, (
        "canal natif trop pauvre (%d tuile(s) communes) : un accord ne prouverait rien"
        % len(mesure["communs"]))
    assert mesure["neigh"], (
        "`neigh_by_pos` absent : le port retomberait sur le voisinage `hexgeo` approxime, et la "
        "confrontation ne porterait plus sur le meme graphe que le natif")


def test_la_distance_de_chemin_par_POSITION_accorde_avec_le_natif(mesure):
    """`get_path_node_counts_by_pos` (etage NEUF de #175-r1) contre `IPathfinders.GetPath(1, ...)`."""
    assert mesure.get("ok")
    nat, port, communs = mesure["nat"], mesure["port"], mesure["communs"]
    ecarts = [(p, port[p], nat[p]) for p in communs if port[p] != nat[p]]
    assert not ecarts, (
        "%d ecart(s) sur %d tuiles entre le pathfinder porte et le natif (PathfinderType="
        "IgnoreTerrain) : %r" % (len(ecarts), len(communs), ecarts[:10]))


def test_les_conventions_DECALEES_echouent_le_temoin_DISCRIMINE(mesure):
    """`Count` = NOEUDS, extremites INCLUSES (`route+0x18` = `List._size`), donc `aretes + 1`.

    Si un decalage de +/-1 accordait AUSSI, la carte serait trop plate pour rien etablir -- et un
    off-by-one passerait inapercu alors qu'il coute une tuile entiere de poids (-100 pour la
    feuille 62)."""
    assert mesure.get("ok")
    nat, port, communs = mesure["nat"], mesure["port"], mesure["communs"]
    for delta in (-1, 1):
        ok = sum(1 for p in communs if port[p] + delta == nat[p])
        assert ok < len(communs), (
            "la convention decalee de %+d accorde AUSSI sur les %d tuiles : le temoin ne "
            "discrimine pas, l'accord exact ne prouve rien" % (delta, len(communs)))


def test_les_deux_feuilles_portent_les_ordinaux_du_BUILD_COURANT(mesure):
    """62 / 63, pas 61 / 62 -- la fiche `#175-r1` du backlog cite des ordinaux PERIMES.

    Le mirror, lui, est juste ; ce test fige l'appariement NOM -> ordinal cote port pour que le
    prochain lecteur ne recopie pas la fiche."""
    assert int(UtilityType.BioMinefield_MoveTowardsTarget) == 62
    assert int(UtilityType.MasterOfTheTutelaries_MoveTowardsTarget) == 63
    #: Forme CONFRONTEE (#1031) : le littéral ET le membre dans la MEME chaine de comparaison.
    #: Ecrit `== 62` seul, l'ordinal serait fige sans que rien ne le confronte au mirror -- c'est
    #: exactement ce que l'etape 2 de `probe_283` refuse, et elle rougissait ici (#10023).
    assert T.BioMinefield_MoveTowardsTargetUtility().UTILITY_TYPE == 62 \
        == int(UtilityType.BioMinefield_MoveTowardsTarget)
    assert T.MasterOfTheTutelaries_MoveTowardsTargetUtility().UTILITY_TYPE == 63 \
        == int(UtilityType.MasterOfTheTutelaries_MoveTowardsTarget)
