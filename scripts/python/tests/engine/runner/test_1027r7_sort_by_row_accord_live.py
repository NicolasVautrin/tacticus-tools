"""#1027-r7 -- l'accord **TUILE A TUILE** de `SortByRow(sameColumnIsRandom: 1)`, flux PRNG ALIGNE.

CE QUE CE FICHIER GARDE, ET CE QUE L'ETAGE OFFLINE NE POUVAIT PAS GARDER
------------------------------------------------------------------------
L'etage 9 de `test_1027_belisarius_actives_offline.py` garde deja la FORME du tirage : un par
element, dans l'ordre source, borne au `Width`. Il le fait avec un `pseudo_rng_next` FACTICE --
il ne peut donc rien dire de l'accord avec le natif.

#1027-r1 avait mesure que les deux MELANGENT (quatre graines, quatre jeux de tuiles distincts de
chaque cote) sans jamais les COMPARER : son etage port repart d'un twister FRAIS alors que le
natif a deja consomme au montage. Deux flux desalignes ne peuvent pas rendre les memes tuiles,
meme si le port est exact.

Ce fichier ferme l'ecart : il CAPTURE l'etat du runner juste avant le cast (`decisionView` +
`observeBattle` + `combatSnapshot` + **`dumpRng`**), joue `InvocationOfMachineVengeance` (1172)
EN LIVE, rejoue le MEME cast dans le Runner du port avec le twister remis dans l'etat capture, et
compare les tuiles de spawn UNE A UNE.

MESURE DU 2026-08-15 (build `t6dpr4k06g`, board MC1_67, Belisarius) -- 3 graines, 3 jeux de tuiles
natifs DISTINCTS, accord 3/3 :

    777    natif = port = [(0,0), (2,0), (4,0), (5,0)]
    31337  natif = port = [(2,0), (3,0), (5,0), (6,0)]
    4242   natif = port = [(0,0), (2,0), (5,0), (6,0)]

CE QUE CET ACCORD ETABLIT, ET QUE RIEN D'AUTRE N'ATTEIGNAIT : le **COMPTE** de tirages. A flux
aligne, un tirage de trop ou de moins decale tout l'aval et change les tuiles. Le mutant
`tirageEnTrop` le montre en rendant un jeu DIFFERENT sur les trois graines -- c'est la
contre-epreuve qui transforme << plausible >> en << exact >>.

DISCIPLINE : ce fichier monte UN runner par graine et les dispose. Deux graines suffisent au
cliquet (la troisieme vit dans le probe) ; la non-degenerescence est ASSERTIONNEE, pas supposee --
si les deux graines rendaient les memes tuiles natives, il n'y aurait eu aucun ex aequo a
departager et l'accord ne prouverait rien.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LES QUATRE ETAGES QU'IL TRAVERSE.
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/runner/abilities/admec.py",
        "scripts/python/engine/runner/prng.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/probe_1027r7_sort_by_row_accord_tuiles.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Confrontation LIVE : il monte un runner, joue le cast natif et le rejoue dans le "
              "port sur le MEME flux PRNG. Depend de la session Frida, donc rejoue toujours.",
}

import uuid                                                                     # noqa: E402
from pathlib import Path                                                        # noqa: E402

import pytest                                                                   # noqa: E402

import probe_1027r7_sort_by_row_accord_tuiles as P                              # noqa: E402

SEEDS = (777, 31337)


@pytest.fixture(scope="module")
def mesures(tmp_path_factory):
    """Une mesure par graine. `state-file` ABSOLU et UNIQUE (jamais sous `data/`)."""
    rpc = P._mkrpc()
    sf = str(tmp_path_factory.mktemp("r1027r7") / ("st_%s.json" % uuid.uuid4().hex[:8]))
    out = []
    for s in SEEDS:
        r = P.une_graine(rpc, sf, s, mutants=True)
        if "erreur" in r:
            pytest.skip("graine %d NON MESUREE (harnais) : %s" % (s, r["erreur"]))
        out.append(r)
    return out


def test_le_temoin_n_est_PAS_degenere(mesures):
    """SI les deux graines rendaient les MEMES tuiles natives, il n'y aurait eu aucun ex aequo a
    departager -- et l'accord de tous les tests suivants ne dirait rien du melange. Ce cran doit
    passer AVANT qu'on lise le moindre accord."""
    jeux = {tuple(m["natif"]) for m in mesures}
    assert len(jeux) == len(SEEDS), (
        "regime DEGENERE : %d graines pour %d jeu(x) de tuiles natif(s) %s"
        % (len(SEEDS), len(jeux), sorted(jeux)))
    for m in mesures:
        assert len(m["natif"]) >= 2, (
            "graine %d : %d tuile(s) de spawn -- il en faut au moins deux pour qu'un ordre "
            "compte" % (m["seed"], len(m["natif"])))


@pytest.mark.parametrize("i", range(len(SEEDS)))
def test_accord_TUILE_A_TUILE_a_flux_PRNG_aligne(mesures, i):
    """LE CRAN CENTRAL, et le seul que #1027-r1 ne pouvait pas poser."""
    m = mesures[i]
    assert m["port"] == m["natif"], (
        "graine %d : natif=%s port=%s -- l'accord tuile a tuile est ROMPU"
        % (m["seed"], m["natif"], m["port"]))


@pytest.mark.parametrize("mutant", ("sansTirage", "tirageEnTrop", "borneHauteur"))
def test_les_contre_epreuves_DIVERGENT(mesures, mutant):
    """UN ACCORD NE VAUT QUE CE QUE VAUT SA CONTRE-EPREUVE. Trois desarmements du seul etage en
    cause, joues sur la MEME capture :
      * `sansTirage`   -- le port garderait l'ordre source (c'est l'etat d'AVANT #1027-r1) ;
      * `tirageEnTrop` -- un tirage de plus AVANT le tri : c'est LUI qui fait du COMPTE de tirages
        une propriete MESUREE et non plausible ;
      * `borneHauteur` -- borne `height` (`BoardComponent+0x10`) au lieu de `width` (`+0x14`) ;
        `NextInternal` faisant du REJET sur les bornes non-puissances-de-2, une borne fausse ne
        change pas que la valeur, elle change le NOMBRE de `genrand_int32` consommes.
    Un mutant qui rendrait EGAL prouverait que ce montage ne sait pas distinguer un port juste
    d'un port faux."""
    for m in mesures:
        d = m["mutants"][mutant]
        assert d["appels"] > 0, (
            "MUTANT NON TRAVERSE (graine %d) : le binding patche n'est pas celui que le port lit"
            % m["seed"])
        assert d["verdict"] == "DIVERGE", (
            "graine %d : le mutant %s rend les MEMES tuiles que le natif (%s) -- temoin degenere"
            % (m["seed"], mutant, d["tuiles"]))


def test_sans_tirage_le_port_rendrait_le_MEME_ordre_sur_toutes_les_graines(mesures):
    """La signature de l'etat d'AVANT : sans le 3e `ThenBy`, l'ordre ne depend plus de la graine.
    Ce cran nomme ce que la reparation a apporte, au lieu de le laisser en prose."""
    sans = {tuple(m["mutants"]["sansTirage"]["tuiles"]) for m in mesures}
    assert len(sans) == 1, (
        "sans tirage, l'ordre source est INVARIANT par graine -- or on en voit %d : %s"
        % (len(sans), sorted(sans)))
    assert sorted(sans)[0] not in {tuple(m["natif"]) for m in mesures}, (
        "l'ordre source coincide avec un jeu natif : ce montage ne separerait pas les deux")
