"""#515 (residu `#497-r1`) -- CONFRONT LIVE de la porte d'elevation sur l'adjacence du RUNNER.

LE MONTAGE EST LE TEMOIN DE #497 LUI-MEME, retourne. La variante `elevation` de
`probe_497_silent_death.py` aligne quatre orks sur la colonne 2 de `MC1_67`, en TRAVERSANT la
marche 2 -> 4 des rangees 2 -> 3. C'est le seul des cinq scenarios de #497 qui DIVERGEAIT :

    port  = [81, 83, 85, 87]      natif = [81]        9 706 PV de degat fantome

parce que `engine/dsl/base.py::_within` decidait l'appartenance par `hexgeo.distance <= r`, quand
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` enumere la liste
STOCKEE (`tile.ConnectivityComponent.Neighbours`) puis applique une porte `|dElev| < 2`
INCONDITIONNELLE. #497 n'a rien asserte dessus, et c'etait juste : un test ecrit A CE MOMENT-LA
aurait FIGE LE BUG.

CE QUE CE FICHIER GARDE, et qu'aucun autre ne peut garder :

  * la CHAINE S'ARRETE A LA MARCHE, port == natif == un seul maillon. C'est le retournement du
    verdict de #497, contre l'oracle NATIF -- pas contre une constante ecrite ici.
  * le REGIME N'EST PAS DEGENERE : le montage a bien quatre ennemis alignes a distance hex 1 les
    uns des autres, donc l'ANCIENNE primitive en frappait quatre. Un `[81] == [81]` obtenu sur un
    montage ou il n'y a qu'un ennemi ne prouverait rien -- le temoin `from_here` et le nombre
    d'unites places l'interdisent.
  * la MARCHE EST REELLE : la porte doit refuser au moins une arete SUR CE BOARD, mesuree sur le
    `boardGraph` capte (etage `adjacence` du probe). Sur un plateau plat, tout ce fichier serait un
    accord en regime degenere.

Le montage et TOUTES les lectures vivent dans `probe_497_silent_death.py` : le probe MESURE, ce
test GARDE, une seule implementation.

Lit l'etat LIVE, aucune RVA ni tuile hardcodee hors du montage, ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
import probe_497_silent_death as P

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # Meme perimetre LARGE que `test_silent_death_live.py`, et pour la meme raison mesuree : ce
    # fichier importe le PROBE, dont la fermeture d'import atteint la quasi-totalite de
    # `scripts/python`. Declarer etroit produirait un FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE de la porte d'elevation `|dElev| < 2` sur l'adjacence du runner "
              "(`_within` / `_adjacent_tiles_native`). Le verdict depend du foyer d'adjacence, du "
              "substrat `boardGraph.neighbours`, du port de 1068 qui sert de revelateur, du "
              "MONTAGE (le probe), des entrees versionnees du runner et du BUILD charge -- "
              "l'oracle etant le jeu lui-meme.",
}

#: L'index de la variante `elevation` dans `P.VARIANTES`, verifie par son NOM (jamais par sa
#: position seule : reordonner le tuple ferait silencieusement mesurer un autre scenario).
_NOM_ELEVATION = "elevation"


@pytest.fixture(scope="module")
def elevation(live_session):
    """UN runner, la variante `elevation` du probe. Le cast n'est pas rejouable (il consomme
    l'actif) : toutes les gardes relisent la MEME mesure."""
    v = next((x for x in P.VARIANTES if x[0] == _NOM_ELEVATION), None)
    assert v is not None, ("la variante `%s` a disparu de `probe_497_silent_death.VARIANTES` -- ce "
                           "fichier n'a plus de montage" % _NOM_ELEVATION)
    _, ctile, places, hp = v
    m, dispose = P.measure_montage(live_session, ctile, places, hp,
                                   state_name="test_515_elevation")
    m["_places"] = places
    m["_caster_tile"] = ctile
    try:
        yield m
    finally:
        dispose()


def test_515_le_montage_traverse_une_vraie_marche(elevation):
    """TEMOIN DE NON-DEGENERESCENCE, cran 1 : la porte doit refuser des aretes SUR CE BOARD.

    Mesure prise sur le `boardGraph` CAPTE (etage `adjacence` du probe), donc sur le substrat que
    le port consomme reellement -- pas sur les elevations du BC re-derivees."""
    a = elevation["adjacence"]
    assert a["sur_atteintes"] > 0, \
        "la couronne hex ne sur-atteint RIEN sur ce board : plateau plat, accord degenere"
    assert a["tuiles_touchees"] > 0


def test_515_le_montage_alignait_quatre_ennemis(elevation):
    """TEMOIN DE NON-DEGENERESCENCE, cran 2 : l'ANCIENNE primitive frappait bien quatre unites.

    Les quatre orks sont consecutifs a distance hex 1 -- c'est ce qui rend l'arret a UN maillon
    informatif. Sans ce cran, un montage a un seul ennemi rendrait le meme `[81]`."""
    places = elevation["_places"]
    assert len(places) >= 4, "le montage ne pose que %d ennemis" % len(places)
    tuiles = [t for _, t in places]
    for a, b in zip(tuiles, tuiles[1:]):
        assert hexgeo.distance(a, b) == 1, \
            "la chaine geometrique est rompue entre %s et %s -- l'ancienne primitive n'aurait pas " \
            "frappe quatre unites, et l'arret a un maillon ne prouverait rien" % (a, b)
    assert hexgeo.distance(elevation["_caster_tile"], tuiles[0]) == 1


def test_515_la_chaine_s_arrete_a_la_marche(elevation):
    """LA garde : port == natif, et le natif s'arrete au premier maillon.

    L'oracle est la cascade du cast NATIF (`GroupType.Damage` par coup), pas une constante ecrite
    ici. Avant la reparation, le port rendait quatre maillons contre un -- 9 706 PV fantomes."""
    assert not elevation["cast_error"], "cast natif bloque: %s" % elevation["cast_error"]
    assert elevation["mutated"] is True, "le cast natif n'a rien mute -- scenario non exerce"
    assert len(elevation["live_chain"]) == 1, \
        "le NATIF ne s'arrete plus a la marche (%s) -- le montage ou le board a change" \
        % elevation["live_chain"]
    assert elevation["off_chain"] == elevation["live_chain"], \
        "chaine PORT %s != chaine NATIF %s" % (elevation["off_chain"], elevation["live_chain"])


def test_515_degat_coup_par_coup_bit_exact(elevation):
    """Le degat du SEUL maillon reste bit-exact : la reparation retire des CIBLES, elle ne touche
    a aucun etage de degat. Un accord sur la topologie qui deplacerait les degats serait pire que
    la divergence d'origine."""
    uid = elevation["live_chain"][0]
    natif = elevation["live_per_hit"].get(uid)
    port = elevation["off_per_hit"].get(uid)
    assert natif and all(x is not None and x > 0 for x in natif), \
        "regime DEGENERE : le natif n'a inflige aucun degat (%s)" % natif
    assert port == natif, "coup par coup sur %d : port=%s natif=%s" % (uid, port, natif)
    assert elevation["off_delta"] == elevation["live_delta"], \
        "totaux port=%s natif=%s" % (elevation["off_delta"], elevation["live_delta"])
