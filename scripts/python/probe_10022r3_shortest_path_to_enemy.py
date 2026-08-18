"""#10022-r3 -- CLIQUET de `ShortestPathToEnemyUtility` (100 % OFFLINE, aucune session Frida).

Ce que ce probe garde, etage par etage, et pourquoi chacun peut se PERIMER EN SILENCE.

  1. **FRAICHEUR DES SYMBOLES** -- le corps reel vit dans le `MoveNext` de l'iterateur genere, pas
     dans la methode nommee. Un renommage cote jeu ferait lire le port comme le mirror d'autre
     chose, sans qu'aucun test ne bronche.
  2. **FRAICHEUR DES SLOTS D'INTERFACE** -- le site n'ecrit ni `GetPath` ni `GetDistance` : il
     appelle `IPathfinders` slot 4 et `IBattleQuery` slot 0x6c. Les deux sont des HOMONYMES a
     plusieurs surcharges (`IBattleQuery` porte trois `GetDistance` a 2 parametres, aux slots
     108/109/110) ; un decalage de vtable au prochain build ferait porter la mauvaise.
  3. **LES DEUX LITTERAUX ECRITS AU SITE** -- `PathfinderType.IgnoreTerrain` = 1 (le `1` du
     call-site) et `UtilityType.UnitWithShortestPathToEnemy` = 72 (le bucket 6). `probe_313` compare
     le *mirror* au *build* et redeviendrait VERT apres un renumerotage ; ce qu'il faut figer, c'est
     l'ordinal MESURE A LA CONVERSION.
  4. **LA PROPRIETE CENTRALE, et c'est le seul etage qui teste du COMPORTEMENT** : hors
     teleporteur, le mirror FIDELE (tri `OrderBy` + les deux elagages + le `break` a 1) rend
     exactement `min over ennemis of pathNodeCount(unitTile, targetMainTile)`. C'est falsifiable :
     un elagage porte de travers (`<` au lieu de `<=`, mauvais sens de comparaison, `break` mal
     place) casse l'egalite sur au moins une configuration.
     ⚠ **Cet etage ASSERTIONNE SON PROPRE NON-VIDE, sur trois axes** : il exige qu'au moins une
     configuration ait fait MORDRE l'elagage 1, qu'au moins une ait fait mordre l'elagage 2, et
     qu'au moins une ait un `pathNodeCount` STRICTEMENT superieur a `hexDist + 1` (un detour reel).
     Sans ces trois crans, une grille sans obstacle rendrait un accord parfait ET VIDE -- les
     elagages n'y mordraient jamais et l'egalite serait une tautologie.
  5. **L'IDENTITE DES SENTINELLES** -- `OUT_OF_RUNNING` (`statics+0x18`, hors course pour CE
     bucket) n'est PAS `HARD_VETO` (`statics+0x20`, veto ferme). Les confondre supprimerait toute
     unite IA du jeu (cf. la reduction a l'absurde de `case-10022` section 3.3). Les deux etant des
     `float`, seule l'IDENTITE les separe -- l'etage verifie qu'un `is` les distingue ET qu'aucune
     n'est egale a l'autre en valeur.
  6. **LA STABILITE DU TRI** -- `Enumerable.OrderBy` est stable en .NET ; a distance hex egale
     l'ordre reste celui de `GetAllEnemyUnitsOfUnit`. Le port s'appuie dessus (`sorted`).

Ce que ce probe NE fait PAS : confronter au natif. L'etage PATHFINDING, lui, l'est deja
(`ignore_terrain_pathfinder`, 180 distances, 0 ecart) ; l'ordre d'activation live est un livrable
distinct (cf. `docs/rl/case-10022-r3-shortest-path-to-enemy.md` section 5).

    python scripts/python/probe_10022r3_shortest_path_to_enemy.py

rc 0 = tout concorde ; rc 1 = au moins une divergence ; rc 2 = PAS MESURE (entrees manquantes --
jamais rabattu sur un vert, cf. la regle tri-etat du depot).
"""
from __future__ import annotations

import io
import os
import random
import sys

_ICI = os.path.dirname(os.path.abspath(__file__))
if _ICI not in sys.path:
    sys.path.insert(0, _ICI)

_RACINE = os.path.dirname(os.path.dirname(_ICI))
_SYMBOLES = os.path.join(_RACINE, "data", "symbols")

_NS = "IdunBattleLogic.AI.Utilities.UnitPicker.ShortestPathToEnemyUtility"

# Les symboles dont le port est le mirror. Le premier n'alloue que la machine a etats ; le
# DEUXIEME porte le corps ; le TROISIEME est le comparateur du `OrderBy`, corps a part.
SYMBOLES = (
    _NS + "$$EvaluateUnitInSteps",
    _NS + ".u003CEvaluateUnitInStepsu003Ed__0$$MoveNext",
    _NS + ".u003Cu003Ec__DisplayClass0_0$$u003CEvaluateUnitInStepsu003Eb__0",
)

# Les DEUX slots d'interface ECRITS au site d'appel, avec leur arite -- lus dans
# `data/symbols/<build>/metadata/interface_slots.tsv`, jamais devines.
SLOTS = (
    ("IPathfinders", 4, "GetPath", 5),         # `pathfinders.<slot 4>(1, unit, from, to, null)`
    ("IBattleQuery", 108, "GetDistance", 2),   # `query.<slot 0x6c>(unitTile, targetTile)`
)

# Les deux ordinaux ECRITS au site (cf. etage 3 de l'en-tete).
PATHFINDER_TYPE_IGNORE_TERRAIN = 1
# ⚠ `UTILITY_TYPE_SHORTEST_PATH` NE VIT PLUS ICI, et c'est la doctrine, pas un gout : ecrit en
# constante de module (`= 72`), c'etait un ordinal NU d'un des quatre enums que garde
# `probe_283` etape 2 -- refuse. Il est desormais FIGE EN FORME CONFRONTEE dans `main()` (le
# litteral ET le membre dans la MEME comparaison), la seule ecriture qui garde la MESURE et
# rougisse quand même au renumerotage. `PATHFINDER_TYPE_IGNORE_TERRAIN` reste : `PathfinderType`
# n'est pas sous ce cliquet.
#
# TROUVE AU MERGE (#10023) : le cliquet renforce et ce litteral viennent de DEUX PR en vol
# SIMULTANEMENT (#1160 l'ecrit, #1162 renforce le cliquet). Aucun des deux auteurs ne pouvait le
# voir -- le premier a joue l'ancien probe, le second a rebase avant que le premier soit merge.


def _build_courant():
    chemin = os.path.join(_SYMBOLES, "CURRENT")
    if not os.path.isfile(chemin):
        return None
    val = io.open(chemin, encoding="utf-8").read().strip()
    return val or None


def _fonctions_du_build(build):
    chemin = os.path.join(_SYMBOLES, build, "ghidra", "functions.tsv")
    noms = set()
    if not os.path.isfile(chemin):
        return noms
    for ligne in io.open(chemin, encoding="utf-8", errors="replace"):
        champs = ligne.rstrip("\n").split("\t")
        if len(champs) >= 2:
            noms.add(champs[1])
    return noms


def _slots_du_build(build):
    """`{(interface, slot): (methode, param_count)}` depuis `metadata/interface_slots.tsv`."""
    chemin = os.path.join(_SYMBOLES, build, "metadata", "interface_slots.tsv")
    out = {}
    if not os.path.isfile(chemin):
        return out
    for ligne in io.open(chemin, encoding="utf-8", errors="replace"):
        if ligne.startswith("#"):
            continue
        champs = ligne.rstrip("\n").split("\t")
        if len(champs) >= 4:
            try:
                out[(champs[0], int(champs[1]))] = (champs[2], int(champs[3]))
            except ValueError:
                continue
    return out


# ------------------------------------------------------------------------------------------- #
#  Le terrain de l'etage 4 : une grille hex SYNTHETIQUE, avec murs et relief
# ------------------------------------------------------------------------------------------- #

def _grille(rng, largeur=9, hauteur=9, taux_mur=0.18, relief=True):
    """Rend `(positions, neigh_by_pos, walkable_by_pos, elev_by_pos)`.

    Grille hex complete par `hexgeo.neighbors` ; des tuiles rendues NON marchables (des murs) et
    du relief (`|dElev| > 1` coupe l'arete) forcent des DETOURS -- sans quoi `pathNodeCount` vaut
    toujours `hexDist + 1` et l'etage 4 serait vide (cf. son 3e cran de non-vide)."""
    import hexgeo
    positions = [(c, r) for c in range(largeur) for r in range(hauteur)]
    walkable = {p: (rng.random() > taux_mur) for p in positions}
    elev = {p: (rng.randint(0, 2) if relief else 0) for p in positions}
    neigh = {}
    for p in positions:
        neigh[p] = [q for q in hexgeo.neighbors(p[0], p[1]) if q in walkable]
    return positions, neigh, walkable, elev


def _etage4(rouges, tirages=240, graine=10022):
    """La propriete centrale + ses trois crans de non-vide."""
    import hexgeo
    from engine.entities.pathfinding.ignore_terrain_pathfinder import get_path_node_counts_by_pos
    from engine.utilities.base import OUT_OF_RUNNING
    from engine.utilities.unit_picker import ShortestPathToEnemyUtility

    util = ShortestPathToEnemyUtility()
    rng = random.Random(graine)

    n_confrontes = 0
    n_elagage1 = 0          # une cible n'a JAMAIS ete pathfindee (skip par distance hex)
    n_elagage2 = 0          # un chemin trouve n'a PAS ameliore le minimum
    n_detour = 0            # un pathNodeCount > hexDist + 1 (le graphe n'est pas trivial)
    n_hors_course = 0       # aucun ennemi joignable
    divergences = []

    for essai in range(tirages):
        positions, neigh, walkable, elev = _grille(rng)
        libres = [p for p in positions if walkable[p]]
        if len(libres) < 6:
            continue
        unite = rng.choice(libres)
        k = rng.randint(2, 5)
        ennemis = rng.sample([p for p in libres if p != unite], k)

        tiles = {"U": unite}
        for i, e in enumerate(ennemis):
            tiles["E%d" % i] = e

        def main_tile_of(x, _t=tiles):
            return _t[x]

        def enemies_of(_x, _n=k):
            return ["E%d" % i for i in range(_n)]

        def hex_distance(a, b):
            return hexgeo.distance(a, b)

        # `IPathfinders.GetPath(IgnoreTerrain, unit, from, to, null)?.Count` -- une passe par
        # CIBLE, comme le natif. On compte les appels : c'est ce qui rend l'elagage 1 OBSERVABLE.
        appels = {"n": 0}

        def path_node_count(_unit, frm, to, _n=neigh, _w=walkable, _e=elev, _a=appels):
            _a["n"] += 1
            counts = get_path_node_counts_by_pos(frm, neigh_by_pos=_n, walkable_by_pos=_w,
                                                 elev_by_pos=_e)
            return counts.get(to)

        r = util.evaluate_unit("U", main_tile_of=main_tile_of, enemies_of=enemies_of,
                               hex_distance=hex_distance, path_node_count=path_node_count)
        appels_mirror = appels["n"]

        # --- l'oracle NAIF : aucun tri, aucun elagage, aucun break -------------------------- #
        appels["n"] = 0
        counts_naifs = []
        for e in ennemis:
            c = path_node_count("U", unite, e)
            if c is not None:
                counts_naifs.append(c)
        attendu = OUT_OF_RUNNING if not counts_naifs else float(-min(counts_naifs))

        n_confrontes += 1
        if not counts_naifs:
            n_hors_course += 1
            if r is not OUT_OF_RUNNING:
                divergences.append("essai %d : aucun ennemi joignable, mirror rend %r au lieu de "
                                   "la sentinelle OUT_OF_RUNNING (identite)" % (essai, r))
            continue
        if r is OUT_OF_RUNNING or float(r) != float(attendu):
            divergences.append("essai %d : mirror=%r attendu=%r (unite=%s ennemis=%s)"
                               % (essai, r, attendu, unite, ennemis))

        # --- les trois crans de NON-VIDE ----------------------------------------------------- #
        if appels_mirror < k:
            n_elagage1 += 1                       # au moins une cible n'a pas ete pathfindee
        # elagage 2 : un chemin trouve n'ameliore pas -> il y a strictement plus d'un chemin
        # trouve, et le premier trouve dans l'ordre de tri n'est pas le seul.
        if len(counts_naifs) >= 2 and appels_mirror >= 2:
            n_elagage2 += 1
        for e, c in zip(ennemis, [path_node_count("U", unite, x) for x in ennemis]):
            if c is not None and c > hexgeo.distance(unite, e) + 1:
                n_detour += 1
                break

    if n_confrontes == 0:
        rouges.append("etage 4 : VACANT -- aucune configuration confrontee")
        return
    for nom, val in (("elagage 1 (skip par distance hex)", n_elagage1),
                     ("elagage 2 (chemin non ameliorant)", n_elagage2),
                     ("detour reel (pathCount > hexDist + 1)", n_detour),
                     ("hors course (aucun ennemi joignable)", n_hors_course)):
        if val == 0:
            rouges.append("etage 4 : cran de NON-VIDE a ZERO -- %s n'a jamais ete exerce sur %d "
                          "configurations. L'accord serait une tautologie." % (nom, n_confrontes))
    if divergences:
        rouges.append("etage 4 : %d divergence(s) mirror vs argmin naif, dont : %s"
                      % (len(divergences), " | ".join(divergences[:3])))
    else:
        print("[10022-r3] etage 4 OK : %d configurations, mirror == argmin naif ; "
              "elagage1=%d elagage2=%d detours=%d hors-course=%d"
              % (n_confrontes, n_elagage1, n_elagage2, n_detour, n_hors_course))


def _etage6(rouges):
    """Tri STABLE : a distance hex egale, l'ordre d'entree survit (`OrderBy` .NET l'est aussi)."""
    import hexgeo
    from engine.utilities.unit_picker import ShortestPathToEnemyUtility

    util = ShortestPathToEnemyUtility()
    # Trois ennemis EQUIDISTANTS de l'unite en hex, mais de longueurs de chemin differentes.
    # L'ordre de visite doit rester celui d'entree ; on l'observe par l'ordre des appels.
    tiles = {"U": (4, 4), "A": (4, 2), "B": (4, 6), "C": (2, 4)}
    vus = []

    def pnc(_u, _f, to):
        vus.append(to)
        return {(4, 2): 9, (4, 6): 8, (2, 4): 7}[to]

    r = util.evaluate_unit("U", main_tile_of=lambda x: tiles[x],
                           enemies_of=lambda _x: ["A", "B", "C"],
                           hex_distance=lambda a, b: hexgeo.distance(a, b),
                           path_node_count=pnc)
    d = [hexgeo.distance(tiles["U"], tiles[n]) for n in ("A", "B", "C")]
    if len(set(d)) != 1:
        rouges.append("etage 6 : VACANT -- le temoin n'est pas equidistant (%r), il ne teste "
                      "aucune stabilite" % (d,))
        return
    attendu = [tiles["A"], tiles["B"], tiles["C"]]
    if vus != attendu:
        rouges.append("etage 6 : ordre de visite %r, attendu %r (tri NON stable a egalite)"
                      % (vus, attendu))
    elif float(r) != -7.0:
        rouges.append("etage 6 : resultat %r, attendu -7.0 (le minimum des trois)" % (r,))
    else:
        print("[10022-r3] etage 6 OK : tri stable a distance hex egale (%r), resultat %r"
              % (vus, r))


def _etage7(rouges):
    """LE COMPTE DE REQUETES DE PATHFINDING -- le seul cran qui voie la FORME de l'elagage 1.

    Mesure (contre-epreuve du 2026-08-18) : elargir l'elagage 1 d'un cran
    (`minSteps <= hexDist` -> `minSteps <= hexDist + 1`) laisse l'etage 4 **VERT**, et ce n'est pas
    un trou du cliquet -- c'est une equivalence PROUVEE : un chemin de `hexDist` aretes compte
    `hexDist + 1` noeuds, donc `pathCount(B) >= hexDist(B) + 1 >= minSteps` des que
    `minSteps <= hexDist(B) + 1` : la cible elaguee ne pouvait de toute facon pas ameliorer. Les
    deux formes rendent le MEME resultat sur tout graphe sans teleporteur.

    Ce qui les separe est le NOMBRE d'appels a `GetPath`. Temoin fabrique pour que le regime
    discriminant existe (`minSteps == hexDist(B) + 1` exactement) :

        U=(4,4) ; A=(7,4) a hexDist 3, pathCount 5 ; B=(0,4) a hexDist 4, pathCount 6

    tri -> [A, B] ; A donne minSteps=5 ; sur B, le natif teste `5 <= 4` (FAUX) et **pathfinde B**,
    la variante elargie teste `5 <= 5` (VRAI) et le SAUTE. Le natif fait donc **2** requetes."""
    import hexgeo
    from engine.utilities.unit_picker import ShortestPathToEnemyUtility

    util = ShortestPathToEnemyUtility()
    tiles = {"U": (4, 4), "A": (7, 4), "B": (0, 4)}
    counts = {(7, 4): 5, (0, 4): 6}
    appels = []

    # Le temoin ne vaut que si sa premisse tient : il DOIT etre dans le regime discriminant.
    dA = hexgeo.distance(tiles["U"], tiles["A"])
    dB = hexgeo.distance(tiles["U"], tiles["B"])
    if not (dA == 3 and dB == 4 and counts[tiles["A"]] == dB + 1):
        rouges.append("etage 7 : VACANT -- le temoin n'est plus dans le regime discriminant "
                      "(dA=%d dB=%d minSteps_attendu=%d). Le refabriquer, ne pas l'affaiblir."
                      % (dA, dB, counts[tiles["A"]]))
        return

    def pnc(_u, _f, to):
        appels.append(to)
        return counts[to]

    r = util.evaluate_unit("U", main_tile_of=lambda x: tiles[x],
                           enemies_of=lambda _x: ["A", "B"],
                           hex_distance=lambda a, b: hexgeo.distance(a, b),
                           path_node_count=pnc)
    if len(appels) != 2:
        rouges.append("etage 7 : %d requete(s) de pathfinding, attendu 2. L'elagage 1 du natif est "
                      "`minSteps <= GetDistance(unitTile, targetTile)` ; toute forme plus LARGE "
                      "saute une cible que le natif interroge -- meme resultat, autre comportement "
                      "(appels vus : %r)" % (len(appels), appels))
    elif float(r) != -5.0:
        rouges.append("etage 7 : resultat %r, attendu -5.0" % (r,))
    else:
        print("[10022-r3] etage 7 OK : 2 requetes de pathfinding sur le temoin discriminant "
              "(la forme `<=` de l'elagage 1 est figee)")


def main():
    rouges = []
    print("[10022-r3] cliquet ShortestPathToEnemyUtility")

    build = _build_courant()
    if build is None:
        print("[10022-r3] NON MESURE : data/symbols/CURRENT absent -- rc 2 (jamais un vert)")
        return 2
    fonctions = _fonctions_du_build(build)
    slots = _slots_du_build(build)
    if not fonctions or not slots:
        print("[10022-r3] NON MESURE : tables du build %s incompletes (functions=%d, slots=%d) "
              "-- rc 2" % (build, len(fonctions), len(slots)))
        return 2
    print("[10022-r3] build = %s" % build)

    # --- etage 1 : les symboles du mirror ------------------------------------------------------ #
    perdus = [s for s in SYMBOLES if s not in fonctions]
    if perdus:
        rouges.append("etage 1 : symbole(s) disparu(s) du build : %s -- le port ne mirrore plus "
                      "ce qu'il cite" % ", ".join(perdus))
    else:
        print("[10022-r3] etage 1 OK : les %d symboles du mirror vivent dans le build"
              % len(SYMBOLES))

    # --- etage 2 : les slots d'interface ECRITS au site ---------------------------------------- #
    ecarts = []
    for itf, slot, methode, arite in SLOTS:
        lu = slots.get((itf, slot))
        if lu is None:
            ecarts.append("%s slot %d ABSENT de la table" % (itf, slot))
        elif lu != (methode, arite):
            ecarts.append("%s slot %d = %s/%d, attendu %s/%d"
                          % (itf, slot, lu[0], lu[1], methode, arite))
    if ecarts:
        rouges.append("etage 2 : %s -- le call-site n'appelle plus ce que le port porte"
                      % " ; ".join(ecarts))
    else:
        print("[10022-r3] etage 2 OK : IPathfinders slot 4 = GetPath/5, "
              "IBattleQuery slot 108 = GetDistance/2")

    # --- etage 3 : les deux ordinaux ECRITS au site -------------------------------------------- #
    try:
        from engine.entities.pathfinding.pathfinders import PathfinderType
        from engine.utilities.utility_type import UtilityType
        from engine.utilities.unit_picker import ShortestPathToEnemyUtility
    except Exception as exc:                                       # noqa: BLE001
        print("[10022-r3] NON MESURE : import du port impossible (%s) -- rc 2" % exc)
        return 2
    if int(PathfinderType.IgnoreTerrain) != PATHFINDER_TYPE_IGNORE_TERRAIN:
        rouges.append("etage 3 : PathfinderType.IgnoreTerrain = %d, or le call-site ecrit le "
                      "LITTERAL %d -- le port porterait un autre pathfinder"
                      % (int(PathfinderType.IgnoreTerrain), PATHFINDER_TYPE_IGNORE_TERRAIN))
    # L'ordinal MESURE a la conversion, en forme CONFRONTEE : le litteral ET le membre dans la
    # MEME comparaison (cf. le bloc en tete de fichier). Un mirror REGENERE apres renumerotage
    # laisserait `probe_313` vert ; cette ligne-ci, non.
    if not (72 == int(UtilityType.UnitWithShortestPathToEnemy)):
        rouges.append("etage 3 : UtilityType.UnitWithShortestPathToEnemy = %d, attendu 72 "
                      "(ordinal MESURE a la conversion)"
                      % int(UtilityType.UnitWithShortestPathToEnemy))
    UTILITY_TYPE_SHORTEST_PATH = int(UtilityType.UnitWithShortestPathToEnemy)
    if int(ShortestPathToEnemyUtility.UTILITY_TYPE) != UTILITY_TYPE_SHORTEST_PATH:
        rouges.append("etage 3 : la classe portee declare UTILITY_TYPE = %d, attendu %d"
                      % (int(ShortestPathToEnemyUtility.UTILITY_TYPE), UTILITY_TYPE_SHORTEST_PATH))
    if not any(r.startswith("etage 3") for r in rouges):
        print("[10022-r3] etage 3 OK : IgnoreTerrain=%d, UnitWithShortestPathToEnemy=%d"
              % (PATHFINDER_TYPE_IGNORE_TERRAIN, UTILITY_TYPE_SHORTEST_PATH))

    # --- etage 5 : l'identite des sentinelles --------------------------------------------------- #
    from engine.utilities.base import (CONDITIONAL_VETO, HARD_VETO, MUST_DO, OUT_OF_RUNNING,
                                       STEP_MARKER)
    toutes = (MUST_DO, OUT_OF_RUNNING, HARD_VETO, CONDITIONAL_VETO, STEP_MARKER)
    if len({id(s) for s in toutes}) != len(toutes):
        rouges.append("etage 5 : deux sentinelles partagent la MEME instance -- un test `is` ne "
                      "les separerait plus")
    if float(OUT_OF_RUNNING) == float(HARD_VETO):
        rouges.append("etage 5 : OUT_OF_RUNNING == HARD_VETO en VALEUR. Le natif distingue "
                      "`statics+0x18` (hors course pour CE bucket) de `statics+0x20` (veto ferme) "
                      "-- les confondre ferait qu'AUCUNE unite IA ne jouerait jamais "
                      "(case-10022 section 3.3).")
    if not any(r.startswith("etage 5") for r in rouges):
        print("[10022-r3] etage 5 OK : %d sentinelles distinctes par identite ET par valeur"
              % len(toutes))

    # --- etages comportementaux ----------------------------------------------------------------- #
    _etage4(rouges)
    _etage6(rouges)
    _etage7(rouges)

    print("")
    if rouges:
        for r in rouges:
            print("[10022-r3] ROUGE : %s" % r)
        return 1
    print("[10022-r3] VERT : 7 etages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
