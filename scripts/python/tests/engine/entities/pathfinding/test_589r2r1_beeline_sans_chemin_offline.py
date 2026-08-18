"""#589-r2-r1 -- LA BEELINE SANS CHEMIN : le port LEVE, et le corpus dit que ca n'arrive pas.

## L'ecart de fidelite, et pourquoi il etait mesure sur DEUX boards seulement

`IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo` recoud les sauts d'un chemin de VOL
par la beeline, sans aucun test :

    var sub = pathfinders.GetPath(PathfinderType.Beeline, unit, last, next, null);
    for (int i = 1; i < sub.Count - 1; i++) res.Add(sub[i]);       // sub NUL -> DEREFERENCEMENT

Le port ecrivait `for mid in (sub or [])[1:-1]` : il AVALAIT l'absence et comptait le saut pour
**1** arete -- le SEUL regime ou `n_C < n_G`, donc le seul ou un seuil `K = 2`
(`MastersOfManoeuvre`, `SmashaEad`) pouvait basculer. `#589-r2` l'avait mesure NON ATTEINT sur
`C1_74` et `C3_14`, et le disait : **285 des 287 boards a `Bridge` n'etaient pas mesures**, parce
que chaque mesure exigeait une CAPTURE LIVE (le champ `connectivity` n'existe que sur une bataille
montee).

## Ce que ce fichier garde, sur trois etages

  1. **LA LEVEE** -- le port ne compte plus 1 quand la beeline ne rend rien. C'est le seul cran qui
     vise la faute ; sa contre-epreuve est le retour a `(sub or [])`, qui rend `1` la ou le natif
     jette. Il ne depend d'AUCUNE entree versionnee et tourne partout.
  2. **L'INERTIE, MESUREE** -- sur le seul board du corpus qui porte une poche isolee, aucun
     MOUVEMENT LEGAL ne fait naitre le saut en cause. C'est ce qui rend la levee sure, et c'est
     rejoue ici, pas recopie.
  3. **LE BALAYAGE** -- les 779 boards de `data/boards/**` sont MESURES (aucune cle de tuile hors
     table), et l'ensemble des boards a connectivite morcelee est exactement celui que la mesure a
     nomme. Un board neuf, ou un masque qui bouge, fait rougir ici.

Les etages 2 et 3 lisent l'entree versionnee `data/symbols/<build>/metadata/tile_edges.tsv` et
skippent en le disant si elle manque ; l'etage 1 tourne toujours, donc ce fichier ne peut jamais
rendre `passed == 0 and skipped > 0` (le regime que #455 fait rougir).

ASCII only (console cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[4]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
import engine.services.movement_query as MQ                                # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LE PROBE : les etages 2 et 3 rejouent SES fonctions (jamais une copie du resultat).
        "scripts/python/probe_589r2r1_beeline_sans_chemin.py",
        "scripts/python/build_pin.py",
        # L'ENTREE VERSIONNEE : elle change au changement de JEU, sans qu'aucun code ne bouge --
        # aucune cascade d'imports ne peut la reveler.
        "data/symbols/*/metadata/tile_edges.tsv",
        # LE CORPUS : un board ajoute ou retire change l'ensemble des morceles de l'etage 3.
        "data/boards/**",
    ),
    "build": True,
    "toujours": False,
    "raison": ("le probe dont les etages 2 et 3 rejouent les fonctions, son epinglage de build, "
               "l'entree versionnee qui porte les masques d'aretes, et le corpus de boards dont "
               "l'etage 3 derive son ensemble. Les foyers de production (`movement_query.py`, "
               "`beeline_pathfinder.py`, `base_pathfinder.py`, `board.py`) ne sont PAS declares : "
               "ils sont deja dans la cascade DERIVEE par les imports."),
}

#: Le SEUL board du corpus dont la connectivite est morcelee -- MESURE (779 boards balayes), pas
#: choisi. L'etage 3 le RE-DERIVE et compare : cette constante n'est pas une entree du calcul.
MORCELES_ATTENDUS = ("global/Waves_Xenos_13",)


# ------------------------------------------------------------------ etage 1 : LA LEVEE

def _board_en_deux_morceaux():
    """Deux rangees de tuiles SANS aucune arete entre elles : le graphe de connectivite a deux
    composantes, la geometrie une seule. C'est la forme exacte de la poche de `Waves_Xenos_13`,
    reduite au minimum."""
    tiles = []
    for col in range(4):
        for row in range(2):
            tid = col * 2 + row + 1
            # arete UNIQUEMENT vers le voisin de la meme rangee : les deux rangees sont disjointes.
            nb = [c * 2 + row + 1 for c in (col - 1, col + 1) if 0 <= c < 4]
            tiles.append({"id": tid, "col": col, "row": row, "elevation": 0, "walkable": True,
                          "isWall": False, "neighbours": nb, "connectivity": nb})
    return Board(tiles, adjacency="evenq")


def test_le_port_LEVE_quand_la_beeline_ne_rend_aucun_chemin():
    """`sub == null` -> le natif dereference. Le port doit lever, PAS compter le saut pour 1.

    ⚠ TEMOIN NON DEGENERE : le meme montage, avec un saut que la beeline SAIT recoudre, doit
    rendre un chemin -- sinon << ca leve >> serait compatible avec un port casse."""
    bd = _board_en_deux_morceaux()
    a = bd.id_at(0, 0)
    z = bd.id_at(3, 1)                       # AUTRE rangee : aucune arete de connectivite
    assert a is not None and z is not None
    assert hexgeo.distance(bd.coord(a), bd.coord(z)) > 1
    with pytest.raises(MQ.BeelineSansChemin):
        MQ.get_connected_path_to(bd, a, z, [a, z])

    # TEMOIN : dans la MEME rangee, la beeline recoud, et le compte est celui du chemin recousu.
    b = bd.id_at(3, 0)
    chemin = MQ.get_connected_path_to(bd, a, b, [a, b])
    assert MQ.get_num_tiles_moved(chemin) == 3, chemin


def test_la_branche_path_None_reste_une_DEGRADATION_et_non_une_levee():
    """Les DEUX absences ne sont pas la meme. Celle du `path` a une branche NATIVE
    (`if (path == null) return new List { from, to };`) ; celle du `sub` n'en a aucune.

    Sans ce test, << faire lever le port >> pourrait deraper sur l'autre absence et casser un
    regime que le natif traite gracieusement."""
    bd = _board_en_deux_morceaux()
    a, z = bd.id_at(0, 0), bd.id_at(3, 1)
    assert MQ.get_connected_path_to(bd, a, z, None) == [a, z]
    assert MQ.get_num_tiles_moved(MQ.get_connected_path_to(bd, a, z, None)) == 1


# ------------------------------------------------------------------ etages 2 et 3 : LE CORPUS

def _probe():
    sys.path.insert(0, str(PYDIR))
    import probe_589r2r1_beeline_sans_chemin as P                          # noqa: E402
    try:
        P.lire_tsv()
    except SystemExit as exc:
        pytest.skip("entree versionnee absente pour le build courant : %s" % exc)
    except Exception as exc:                                               # noqa: BLE001
        pytest.skip("build courant non epingle (jeu absent) : %s" % exc)
    return P


def test_le_balayage_des_779_boards_ne_laisse_AUCUN_board_non_mesure():
    """Etage 3, premiere moitie : le masque couvre-t-il TOUT le corpus ?

    Un board dont une cle de tuile manque a la table n'est PAS mesure -- et un balayage qui le
    compterait comme connexe rendrait un vert qui ment. On exige donc zero non-mesure, et on
    ASSERTE le non-vide du corpus (un `data/boards/` vide passerait sinon pour un succes)."""
    P = _probe()
    masques = P.lire_tsv()
    bds = P.charger_boards()
    assert len(bds) > 500, "corpus de boards suspect : %d" % len(bds)
    non_mesures = [k for k, b in bds.items() if P.connectivite_derivee(b, masques)[1]]
    assert not non_mesures, ("%d board(s) NON MESURE(S) : %s"
                             % (len(non_mesures), non_mesures[:6]))


def test_un_seul_board_du_corpus_porte_une_poche_isolee():
    """Etage 3, seconde moitie : QUELS boards ont un graphe de connectivite morcele ?

    ⚠ LE SENS DE LA BORNE EST CE QUI REND CE TEST UTILE. Le masque est une BORNE INFERIEURE, donc
    un board rendu CONNEXE l'est vraiment -- c'est la conclusion qui porte (le regime y est
    impossible). Un board rendu MORCELE n'est qu'un CANDIDAT ; celui qui reste a ete confirme par
    une capture, et l'autre candidat du premier tour (`Waves_Imperial_13`) a ete REFUTE par la
    sienne puis absorbe dans l'ajustement."""
    P = _probe()
    masques = P.lire_tsv()
    morceles = []
    for k, b in sorted(P.charger_boards().items()):
        adj, inconnues = P.connectivite_derivee(b, masques)
        if inconnues:
            continue
        comps = P._composantes(adj)
        if len(comps) > 1:
            morceles.append(k)
    assert tuple(morceles) == MORCELES_ATTENDUS, morceles


def test_sur_le_seul_board_a_poche_aucun_MOUVEMENT_LEGAL_n_atteint_la_levee():
    """Etage 2 -- ce qui rend la levee SURE, rejoue et non recopie.

    Le regime est GEOMETRIQUEMENT REEL sur ce board (la beeline echoue sur des centaines de
    couples, et des dizaines de sauts de vol ne sont pas recousus), mais
    `MovementQuery$$GetConnectedPathTo` n'est appele que par
    `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved`, donc APRES un deplacement : ses deux
    extremites sont MARCHABLES par construction. Sous cette contrainte, le compte tombe a zero.

    ⚠ TEMOIN NON DEGENERE, et il est indispensable : sans lui, << 0 mouvement legal >> serait
    indistinguable de << la mesure ne sait rien voir sur ce board >>. On exige donc que les etages
    [1] et [2] soient NON NULS -- la beeline echoue bien, et des sauts de vol le rencontrent."""
    P = _probe()
    bd, why = P.board_derive("Waves_Xenos_13")
    assert bd is not None, why
    r = P.mesurer_regime(bd)
    assert r["sans_chemin"] > 0, "TEMOIN VIDE : la beeline ne rate aucun couple sur ce board"
    assert r["sauts_sans"] > 0, "TEMOIN VIDE : aucun saut de vol ne rencontre la poche"
    assert r["sauts_sans_legaux"] == 0, (
        "%d saut(s) SANS chemin naissent d'un mouvement legal -- la levee de "
        "`get_connected_path_to` est ATTEIGNABLE en jeu, ce que la tranche a mesure faux : %s"
        % (r["sauts_sans_legaux"], r["legaux"][:3]))
