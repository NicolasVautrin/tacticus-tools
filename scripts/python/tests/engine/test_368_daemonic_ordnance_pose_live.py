"""#368 -- la POSE de `1148 DaemonicOrdnance` : le port allume-t-il les MEMES tuiles ?

QUESTION BINAIRE : l'ensemble des tuiles que le NATIF embrase apres un cast est-il EGAL a
`burned_tiles` de la face COMBAT du port (`DaemonicOrdnanceAbility.execute_behaviour`) ?

Ce fichier verrouille TROIS choses, et la troisieme est un RESIDU, pas un acquis :

A/B. **Le regime `elev`** -- l'ancre dont le triangle geometrique compte 3 tuiles et la zone 2,
     l'amputation venant de `TilesOnSameElevation(..., maxDiff = 1)`
     (`IdunBattle.Entities.Selectors.TilesOnSameElevationSelector$$Select` =
     `abs(TileComponent+0x18 - TileComponent+0x18) <= maxDiff`, rien d'autre). Sur ce regime le port
     est EXACT, sur les DEUX branches du `If` de
     `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetTargetAreaTiles` :
       * `dir = 1` -- board MoW-capable, porteur = la VRAIE MoW `blackForgefiend` ;
       * `dir = 4` -- board non MoW-capable, porteur greffe.
     C'est ce regime que #359-r4 avait lu comme "le natif n'allume pas une tuile NON MARCHABLE" :
     sur `MC1_67`, l'ancre `(4,1)` a pour voisine `(4,2)` a l'elevation **4** contre **2** -- la
     marchabilite n'y est qu'une COVARIABLE, et le bras A l'exhibe a l'envers (la tuile amputee y est
     MARCHABLE).

     **VUE ROUGE, sur le MEME montage** : le port dont le `maxDiff` est neutralise allume une tuile
     de PLUS que le natif. Sans elle, un accord ne dirait pas que c'est ce filtre-la qui le produit.

C.  **Le regime `unwalk`** -- ancre dont les 3 tuiles de la zone passent l'elevation, mais dont l'une
    est NON MARCHABLE. Le natif ne l'embrase PAS ; le port si. La garde n'affirme donc PAS l'accord :
    elle EXIGE que l'ecart soit EXACTEMENT l'ensemble des tuiles non marchables de la zone. Elle
    rougit si le natif change, et elle rougit aussi si le port diverge AILLEURS.
    Residu, cause native non tranchee et capteur manquant : `docs/rl/case-368-pose-daemonic-ordnance.md`.

Montage, decomposition par etage et refus hors regime : `probe_368_daemonic_ordnance_pose.py`
(il REFUSE de mesurer si l'ancre n'est pas du regime demande, au lieu de rendre un montage degrade).
ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_368_daemonic_ordnance_pose as P                 # noqa: E402


@pytest.fixture(scope="module")
def measured():
    """Un build par bras -- chacun rend la vue VERTE et la VUE ROUGE (port `maxDiff` neutralise) sur
    le MEME etat, et dispose son runner dans un `finally`."""
    return {arm: P.pose(arm) for arm in ("A", "B", "D")}


@pytest.mark.parametrize("arm", ["A", "B"])
def test_pose_matches_native_on_elevation_regime_live(measured, arm):
    """A/B -- regime `elev`, une branche du `If` chacun : natif == port == zone apres elevation."""
    r = measured[arm]
    s = r["stages"]
    assert r["regime"] == "elev"
    # Le regime est EXERCE : sans amputation, l'accord ne dirait rien.
    assert len(s["triangle"]) == 3 and len(s["zone"]) == 2, \
        f"[{arm}] regime non exerce: triangle={s['triangle']} zone={s['zone']}"
    assert r["native"] == r["port"], \
        f"[{arm}] natif {r['native']} != port {r['port']} (zone={sorted(s['zone'])})"
    assert sorted(map(tuple, s["zone"])) == r["native"], \
        f"[{arm}] la zone du port {sorted(s['zone'])} n'est pas ce que le natif embrase {r['native']}"


@pytest.mark.parametrize("arm", ["A", "B"])
def test_neutralising_max_diff_over_burns_live(measured, arm):
    """VUE ROUGE -- `TilesOnSameElevation` sans son `maxDiff` allume une tuile de PLUS que le natif.

    C'est la mutation adversariale du filtre EXACT que A/B attribuent l'accord : si elle passait
    inapercue, l'accord pourrait venir de n'importe quoi d'autre."""
    r = measured[arm]
    assert r["port_wide"] != r["native"], \
        f"[{arm}] la mutation maxDiff ne change RIEN ({r['port_wide']}) -- le bras ne prouve rien"
    assert set(r["native"]).issubset(set(map(tuple, r["port_wide"]))), \
        f"[{arm}] port mute {r['port_wide']} ne contient pas le natif {r['native']}"


def test_unwalkable_tile_of_the_zone_is_the_whole_residual_live(measured):
    """C -- RESIDU BORNE : l'ecart `port \\ natif` est EXACTEMENT les tuiles NON MARCHABLES de la zone.

    Le natif n'embrase pas une tuile non marchable ; aucun etage de la chaine de pose lu au
    decompile ne teste la marchabilite (cf. la doc de cas). La garde ne suppose donc pas un
    mecanisme : elle FIGE l'ecart mesure, borne par la marchabilite, et rougit des qu'il bouge."""
    r = measured["D"]
    s = r["stages"]
    assert r["regime"] == "unwalk"
    assert len(s["zone"]) == 3, f"regime non exerce: zone={s['zone']}"
    assert r["unwalkable_in_zone"], "aucune tuile non marchable dans la zone -- bras vide"
    assert r["gap"] == r["unwalkable_in_zone"], \
        (f"ecart port\\natif {r['gap']} != tuiles non marchables de la zone "
         f"{r['unwalkable_in_zone']} -- le residu a BOUGE (natif ou port)")
    # Et l'ecart ne touche QUE des tuiles non marchables : les marchables de la zone brulent toutes.
    walk = [q for q in map(tuple, s["zone"]) if s["walkable"][q]]
    assert sorted(walk) == r["native"], \
        f"les tuiles MARCHABLES de la zone {sorted(walk)} != natif {r['native']}"
