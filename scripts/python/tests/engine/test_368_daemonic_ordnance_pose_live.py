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

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15). Ajoute
#: par #368-r2, qui lui donne une seconde famille de crans (le FLAG d'activite).
#: `build: True` : la mesure est LIVE (elevations et marchabilite du `TileComponent`, `tileMeta`).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_368_daemonic_ordnance_pose.py",
        # L'ability confrontee et sa zone.
        "scripts/python/engine/runner/abilities/blacklegion.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/battle_query.py",
        # #368-r2 : le predicat de tuile, son domaine, et le site qui ecrit le flag a la pose.
        "scripts/python/engine/entities/effects/loki/status.py",
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effect_type.py",
        # Le harnais.
        "scripts/python/rl_duel.py", "scripts/python/tests/conftest.py",
    ),
    "build": True,
    "toujours": False,
    "raison": ("Confrontation LIVE de la POSE de 1148 ET du flag d'activite des effets de tuile : "
               "la zone (elevation), le domaine des quatre types a condition, le predicat "
               "walkable/temporaire et le site qui l'ecrit peuvent tous retourner le verdict."),
}


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


# ------------------------------------------------------------------ #368-r2 : le FLAG D'ACTIVITE

def test_le_natif_POSE_puis_DESACTIVE_sur_la_tuile_non_marchable_live(measured):
    """LE REGIME QUI REND CE FICHIER DISCRIMINANT. Sans ce cran, << la tuile ne brule pas >> ne
    distingue pas << jamais soumis >> (un selecteur l'exclurait) de << pose puis desactive >> (une
    `CreateActiveCondition`) -- et le port aurait ete << repare >> au mauvais etage, en ajoutant
    un filtre `Walkable` au selecteur qu'aucun artefact natif ne porte."""
    r = measured["D"]
    if r.get("fire_inactif") is None:
        pytest.fail("`includeInactive` NON MESURE (bundle charge sans le drapeau) -- ce n'est pas "
                    "un accord, c'est une absence de mesure", pytrace=False)
    assert str(r.get("verdict_368r1", "")).startswith("POSE-PUIS-DESACTIVE"), \
        f"verdict #368-r1 inattendu : {r.get('verdict_368r1')}"
    for q in r["unwalkable_in_zone"]:
        rows = (r["fire_inactif"] or {}).get(str(tuple(q))) or []
        assert rows, f"la tuile non marchable {q} ne porte AUCUN Fire, meme inactif"
        assert all(e.get("active") is False for e in rows), \
            f"le natif garde un Fire ACTIF sur la tuile non marchable {q} : {rows}"


def test_le_port_pose_PARTOUT_et_n_active_QUE_ce_que_le_natif_active_live(measured):
    """#368-r2 -- LA CONFRONTATION QUI COMPTE, etage par etage :

      * POSE   : le port pose sur les MEMES tuiles que le natif (les trois de la zone) ;
      * ACTIVE : et il n'en laisse ACTIVES que celles que `tileMeta` (actif-only) rend.

    Comparer directement `burned_tiles` a `native` confondait les deux etages -- c'est ce que
    faisait la garde ci-dessus, et c'est pourquoi elle constatait un << residu >> la ou le port
    etait en fait juste sur la POSE et faux sur le FLAG."""
    r = measured["D"]
    s = r["stages"]
    assert sorted(map(tuple, s["zone"])) == r["port"], \
        f"le port ne pose pas sur toute la zone : zone={sorted(s['zone'])} poses={r['port']}"
    assert r["gap_actifs"] == [], \
        (f"le port garde ACTIF ce que le natif desactive : {r['gap_actifs']} "
         f"(actifs port={r['port_actifs']}, natif={r['native']})")
    assert r["agree_actifs"], \
        f"actifs port {r['port_actifs']} != natif {r['native']}"
    # Le bras EXERCE bien la condition : sans tuile desactivee, l'accord serait vacant.
    assert set(map(tuple, r["port"])) - set(map(tuple, r["port_actifs"])), \
        "aucune tuile n'a ete DESACTIVEE par le port -- le bras ne prouve rien"


def test_la_condition_de_tuile_MORD_quand_on_la_neutralise():
    """CONTRE-EPREUVE, sur le PREDICAT (offline, aucun runner) : c'est lui qui decide, et il doit
    rendre FAUX exactement sur << non marchable ET non temporaire >>.

    ⚠ Le tri-etat est teste dans les DEUX sens : un canal NON MESURE (`None`) ne doit JAMAIS
    produire un `False` -- sinon le port desactiverait un effet sur une non-mesure, ce qui est
    pire que le laisser actif."""
    from engine.entities.effects.loki.status import (tile_status_effect_is_active as cond,
                                                     TILE_ACTIVE_CONDITION_EFFECT_TYPES)
    from engine.entities.effect_type import EffectType
    assert cond(True, False) is True and cond(True, None) is True     # marchable -> actif
    assert cond(False, True) is True and cond(None, True) is True     # temporaire -> actif
    assert cond(False, False) is False                                # LE seul FAUX
    assert cond(False, None) is None and cond(None, None) is None     # NON MESURE, pas False
    assert cond(None, False) is None
    # Le DOMAINE est de QUATRE types : `Darkness` est dans `IsTileStatusEffect` mais n'a AUCUNE
    # `CreateActiveCondition` propre (elle herite le trigger CONSTANT partage par 114 classes).
    assert {int(x) for x in TILE_ACTIVE_CONDITION_EFFECT_TYPES} == {
        int(EffectType.Fire), int(EffectType.Ice),
        int(EffectType.Contaminated), int(EffectType.DespoiledGround)}
    assert int(EffectType.Darkness) not in TILE_ACTIVE_CONDITION_EFFECT_TYPES
