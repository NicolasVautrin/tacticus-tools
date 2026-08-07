"""GARDES #519 -- LE CLIQUET DU MOTIF « nos livraisons periment nos citations et nos temoins ».

Le 2026-08-07, vingt ports d'ability ont ete mergees. Chacun fait ENTRER une ability dans
`ABILITY_CLASSES` et SORTIR son entree de `TARGETING_OPTIONS_UNPORTED`. Toute citation ou tout
temoin qui pointait vers une de ces abilities devient FAUX -- et rien ne le voyait. Quatre
occurrences mesurees dans la journee, dont DEUX ont rendu `master` rouge.

CE FICHIER GARDE LES DEUX AXES, par les deux probes de la tranche :

  1. `probe_519_comptes_de_table.py`  -- les COMPTES de `TARGETING_OPTIONS_UNPORTED` sont DERIVES
     du code (marqueurs `@FORME`) et confrontes au BLOC GENERE de l'en-tete. Un compte ecrit a la
     main se perime a la tranche suivante : quatre valeurs fausses en un jour, dont la correction
     FINALE elle-meme (`10 / 4 / 0 / 13` annonce pour un code qui porte `12 / 6 / 0 / 9` -- trois
     nombres faux sur quatre, et une SOMME juste qui masquait le tout).

  2. `probe_519_temoins_de_camp.py`   -- aucun site EXECUTABLE ne doit affirmer un camp FAUX.
     L'asymetrie fait le tri : notre cadence va de « non portee » vers « portee », jamais
     l'inverse, donc seules les affirmations du cote « pas encore portee » perissent.

Ces deux gardes sont OFFLINE (aucun runner, aucun RPC). ASCII only.
"""
from __future__ import annotations

import importlib
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0].rstrip("\\/"))

comptes = importlib.import_module("probe_519_comptes_de_table")
temoins = importlib.import_module("probe_519_temoins_de_camp")


# ------------------------------------------------------- 1. les COMPTES sont DERIVES, pas ecrits

def test_le_bloc_genere_est_a_jour():
    """LA garde du volet COMPTEURS. Elle tombe des qu'une tranche retire une entree de la table
    sans re-generer le bloc -- c'est-a-dire exactement au moment ou le compte devient faux, et non
    plusieurs tranches plus tard quand quelqu'un le relit par hasard.

    Reparer : `python scripts/python/probe_519_comptes_de_table.py --ecrire`."""
    mes = comptes.deriver()
    attendu = comptes.bloc_attendu(mes)
    lignes = comptes.CIBLE.read_text(encoding="utf-8").splitlines()
    bornes = comptes._bornes(lignes)
    assert bornes is not None, (
        "le BLOC GENERE a disparu de %s : les comptes seraient de nouveau ecrits a la main"
        % comptes.CIBLE.name)
    d, f = bornes
    assert lignes[d:f + 1] == attendu, (
        "BLOC GENERE PERIME. Re-generer :\n"
        "  python scripts/python/probe_519_comptes_de_table.py --ecrire")


def test_chaque_entree_porte_sa_forme():
    """Sans marqueur `@FORME`, une entree n'est comptee dans AUCUNE forme et la ventilation cesse
    de sommer au total -- une derivation qui ne voit pas tout est pire qu'un compte ecrit, parce
    qu'elle a l'air derivee. Le probe rend rc 2 dans ce cas ; ici on le rend explicite."""
    mes = comptes.deriver()
    assert mes["sans_forme"] == [], (
        "entrees sans marqueur `@FORME` : %s -- ajouter le marqueur au-dessus, ou au-dessus de "
        "leur section" % (mes["sans_forme"],))
    somme = sum(len(v) for v in mes["par_forme"].values())
    assert somme == mes["total"], (
        "la ventilation somme a %d pour un dict de %d" % (somme, mes["total"]))


def test_la_derivation_mesure_quelque_chose():
    """Un derivateur qui ne trouve RIEN rendrait tous les comptes a zero et le bloc genere serait
    « a jour » sur du vide. Le test assertionne son propre non-vide -- sans ca, vider la table
    passerait pour un vert."""
    mes = comptes.deriver()
    assert mes["total"] > 0, "la table est VIDE : la garde ci-dessus ne mesurerait plus rien"
    assert mes["hors_bloc"], "aucune entree hors-bloc : le decoupage ne separe plus rien"
    assert mes["bloc"], "aucune entree dans le bloc du pool"


# ------------------------------------------------------- 2. aucun TEMOIN de camp n'est PERIME

def test_aucun_temoin_de_camp_perime():
    """LA garde du volet TEMOINS, et la cause exacte des DEUX rouges de `master` du 2026-08-07 :
    `targeting_options_for(1091) is None` fige dans deux fichiers, faux des le port de `#507`.

    Un site PERIME est une affirmation qui est FAUSSE aujourd'hui -- soit elle rougit deja quelque
    part (test), soit elle ment en silence (probe)."""
    sites = temoins.balayer()
    perimes = [str(s) for s in sites if s.verdict == temoins.PERIME]
    assert perimes == [], "temoins de camp PERIMES :\n  " + "\n  ".join(perimes)


def test_le_balayage_voit_un_corpus_non_vide():
    """Meme raison que ci-dessus : un balayage qui ne trouve aucun site rendrait `0 PERIME` et se
    lirait comme un vert. Le corpus est DERIVE (AST de `scripts/python/**`), donc il doit contenir
    au moins les affirmations STABLE que le port normal produit."""
    sites = temoins.balayer()
    assert sites, "le balayage ne trouve AUCUN site : defaut d'outil, pas un vert"
    assert any(s.verdict == temoins.STABLE for s in sites), (
        "aucun site STABLE : le detecteur ne reconnait plus les formes du corpus")


@pytest.mark.parametrize("verdict", [temoins.PERIME, temoins.PERISSABLE, temoins.STABLE])
def test_les_trois_verdicts_sont_exhaustifs(verdict):
    """La partition doit etre TOTALE : aucun site ne doit sortir sans verdict. Un `None` qui passe
    a travers serait invisible du filtre `PERIME` ci-dessus."""
    sites = temoins.balayer()
    assert all(s.verdict in (temoins.PERIME, temoins.PERISSABLE, temoins.STABLE) for s in sites)
    assert verdict in (temoins.PERIME, temoins.PERISSABLE, temoins.STABLE)
