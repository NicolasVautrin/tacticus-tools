"""`#510-r2` -- `battle_query.get_tiles_behind` doit avancer d'un PAS UNITAIRE.

CRITERE BINAIRE : quand `to` n'est PAS adjacent a `from`, la ligne rendue avance-t-elle d'UNE tuile
par iteration (le natif) ou par bonds de `d(from, to)` (le mirror d'avant) ?

Le natif, LU :

    // IdunBattle.Core.Services.BattleQuery$$GetTilesBehind(from, to, checkWalkable, updateRef, max)
    dir = CubeCoordinate$$DirectionTo(cube(from), cube(to))   // = clamp(from - to, -1, +1)
    cur = cube(from)
    loop: next = cur - dir ; tile = GetTileEntityAt(next) ; if (tile == null) return list
          if (!TileUtil.IsTileValidForList(tile, ref, checkWalkable, 1)) return list
          list.Add(tile) ; if (updateReference) ref = tile ; cur = next

et `IdunBattle.Utils.Hex.CubeCoordinate$$DirectionTo` est `Max(Min(delta, 1), -1)` **par
composante** -- le mirror `battle_query.direction_to` etait deja exact ; c'est
`get_tiles_behind` qui ne l'appelait pas.

Les quatre etages ci-dessous ont tous ete vus ROUGES sur l'arbre d'avant le correctif (le message
verbatim est en tete de chacun). ASCII only (console cp1252)."""
from __future__ import annotations

import os
import sys

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

from engine import battle_query as bq          # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
#: Le foyer mesure est `battle_query` ; `hexgeo` porte la conversion cube/odd-q dont depend
#: chaque coordonnee assertionnee ici, et l'etage 5 lit le SOURCE de `get_tiles_behind`.
DECLENCHEUR = {
    "chemins": (
        # `--proposer` dit que la fermeture d'imports tient ENTIEREMENT dans la cascade derivee
        # par le foyer (473 chemins) : une liste vide serait donc juste. On declare quand meme
        # les DEUX foyers que ce fichier juge, parce qu'un lecteur doit les voir sans relancer
        # l'outil -- c'est du sur-declaratif, et le garde dit que trop LARGE est sain.
        "scripts/python/engine/battle_query.py",
        "scripts/python/hexgeo.py",
    ),
    "build": False,   # aucune lecture de `data/symbols/**` ni du binaire : tout est calcule
    "toujours": False,
    "raison": "le foyer mesure est `battle_query.get_tiles_behind` (et `direction_to`, dont "
              "l'etage 5 verifie qu'il est bien APPELE et pas re-transcrit) ; `hexgeo` porte la "
              "conversion cube/odd-q dont depend CHAQUE coordonnee assertionnee ici. Rien "
              "d'autre : le fichier n'ouvre aucun dump et ne monte aucun runner.",
}


# `from` et `to` sur la MEME colonne, a TROIS hex d'ecart : le regime que trois des quatre
# call-sites natifs n'atteignent jamais, et que `UnstoppableMomentumReworked` atteint.
FRM = (2, 2)
TO_LOIN = (2, 5)
TO_ADJ = (2, 3)


def test_etage1_pas_unitaire_sur_cible_distante():
    """ROUGE avant : `[(2, 5), (2, 8), (2, 11), (2, 14)]` -- des bonds de 3."""
    ligne = bq.get_tiles_behind(FRM, TO_LOIN, max_count=4)
    assert ligne == [(2, 3), (2, 4), (2, 5), (2, 6)], ligne
    # Le pas est unitaire : chaque tuile est a distance hex 1 de la precedente.
    import hexgeo
    prev = FRM
    for p in ligne:
        d = hexgeo.distance(prev, p)
        assert d == 1, "pas non unitaire %s -> %s : d=%s" % (prev, p, d)
        prev = p


def test_etage2_les_gates_voient_les_tuiles_intermediaires():
    """La consequence MORDANTE du bug, et la seule qui soit PERMISSIVE.

    ROUGE avant : la ligne rendait `[(2, 5), (2, 8), ...]` -- le mur pose en `(2, 3)` n'etait
    JAMAIS evalue, donc la ligne le TRAVERSAIT. Le natif, lui, s'arrete au 1er echec
    (`return list`)."""
    mur = {(2, 3)}
    ligne = bq.get_tiles_behind(FRM, TO_LOIN, max_count=4,
                               tile_exists=lambda p: p not in mur)
    assert ligne == [], ligne
    # Et un mur plus loin ne coupe QUE la queue : c'est un prefixe, pas un filtre.
    ligne2 = bq.get_tiles_behind(FRM, TO_LOIN, max_count=4,
                                 tile_exists=lambda p: p != (2, 5))
    assert ligne2 == [(2, 3), (2, 4)], ligne2


def test_etage3_value_preserving_sur_cible_adjacente():
    """Le regime des trois autres call-sites natifs et de TOUS les montages joues jusqu'ici : le
    correctif ne doit RIEN y changer. `clamp(delta) == delta` des que chaque composante est dans
    [-1, +1].

    Cet etage est le garde-fou de non-regression ; il etait VERT avant comme apres, et c'est
    exactement ce qu'on lui demande de montrer."""
    assert bq.get_tiles_behind(FRM, TO_ADJ, max_count=4) == [(2, 3), (2, 4), (2, 5), (2, 6)]
    # Balayage des SIX voisins : sur chacun, la 1re tuile rendue EST la cible.
    import hexgeo
    for n in hexgeo.neighbors(FRM[0], FRM[1]):
        ligne = bq.get_tiles_behind(FRM, n, max_count=1)
        assert ligne == [(n[0], n[1])], "voisin %s -> %s" % (n, ligne)


def test_etage4_le_contournement_de_unstoppable_momentum_devient_un_noop():
    """`unstoppable_momentum._first_step` passait le PAS UNITAIRE comme `to` pour ne pas forker la
    geometrie. Une fois le clamp pose, donner le pas ou donner la cible distante rend la MEME
    ligne -- le contournement est donc inerte, et le retirer ne changerait rien.

    ROUGE avant : les deux lignes divergeaient (`[(2,3),(2,4),...]` contre
    `[(2,5),(2,8),...]`), ce qui EST la raison d'etre du contournement."""
    dx, _dy, dz = bq.direction_to(FRM, TO_LOIN)
    import hexgeo
    fx, _fy, fz = hexgeo.to_cube(FRM[0], FRM[1])
    pas = hexgeo.from_cube(fx - dx, fz - dz)
    assert bq.get_tiles_behind(FRM, pas, max_count=5) \
        == bq.get_tiles_behind(FRM, TO_LOIN, max_count=5)


def test_etage5_le_foyer_est_direction_to_et_pas_une_seconde_transcription():
    """Un site qui re-transcrit `Max(Min(v,1),-1)` au lieu d'appeler le mirror deja pose est un
    second endroit ou le natif peut devenir faux -- c'est exactement ce qui a produit ce residu.

    Prémisse ASSERTIONNEE (sinon l'etage serait vide, donc vert pour rien) : le corps de
    `get_tiles_behind` cite `direction_to`."""
    import inspect
    src = inspect.getsource(bq.get_tiles_behind)
    corps = src.split('"""')[-1]          # apres la docstring
    assert "direction_to(" in corps, corps[:400]
