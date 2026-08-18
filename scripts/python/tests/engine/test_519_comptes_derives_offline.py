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

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    # PERIMETRE LARGE, et DERIVE du role des trois probes, pas prudentiel : l'axe TEMOIN balaie
    # TOUT site executable de `scripts/python/**` qui affirme un camp (« pas encore portee »), et
    # l'axe COMPTES lit le texte de `engine/runner/abilities/targeting.py` marqueur par marqueur.
    # N'importe quel fichier qui se met a citer une ability change donc le verdict, sans toucher
    # ni au moteur ni a ce test. Une liste choisie serait un FAUX VERT -- c'est exactement la
    # faute que cette tranche outille.
    # Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    "build": True,
    "toujours": False,
    "raison": "L'axe ORDINAUX compare les ordinaux CITES aux valeurs du build PRECEDENT : c'est "
              "une propriete du build, pas du code. Un renumerotage d'`ActiveAbilityType` a la "
              "mise a jour suivante peut donc faire changer ce fichier d'avis sans qu'une ligne "
              "de `scripts/python` bouge -- et c'est precisement le glissement SILENCIEUX que la "
              "tranche existe pour rendre visible.",
}

comptes = importlib.import_module("probe_519_comptes_de_table")
temoins = importlib.import_module("probe_519_temoins_de_camp")
ordinaux = importlib.import_module("probe_519_ordinaux_decales")


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
    passerait pour un vert.

    ⚠ **LE NON-VIDE PORTE SUR LE TOTAL ET SUR LA PARTITION, PAS SUR CHAQUE COTE (#889-r6).** La
    redaction precedente exigeait `hors_bloc` NON VIDE, et cette exigence est tombee le jour ou la
    derniere entree hors-bloc a migre sur sa classe (`1215 InstrumentsOfVengeance`, contrat de
    DISJONCTION de la table). Ce n'etait pas une regression : la table DRAINE par construction --
    notre cadence va de « non portee » vers « portee », jamais l'inverse, et le dernier port de
    chaque cote videra son cote. Exiger les deux cotes non vides revenait donc a garder une
    PROPRIETE DU CORPUS, qui se perime toute seule, la ou l'invariant a garder est celui de la
    DERIVATION : elle mesure quelque chose, et sa partition est EXHAUSTIVE.

    Ce que ce test garde donc, et qui ne se perime pas : `hors_bloc + bloc == total` (le decoupage
    ne perd aucune entree -- une entree tombee entre les deux serait comptee nulle part, exactement
    le vice que le volet COMPTES existe pour interdire) et l'EGALITE ENSEMBLISTE avec la table (la
    derivation voit exactement ce que la table porte, ni plus ni moins).

    ⚠ **LE JOUR ANNONCE EST ARRIVE, ET LA PRESCRIPTION D'AU-DESSUS NE TENAIT PAS (#996-r1-r3).**
    La redaction precedente exigeait `total > 0` et annoncait « le jour ou la table entiere sera
    vide, il faudra supprimer le volet, pas le desarmer ». La table est passee a **0** le
    2026-08-14, par deux migrations LEGITIMES et independantes (`1215 InstrumentsOfVengeance`
    #889-r6, puis `1015 PrecisionShot` #996-r1-r3) -- et ce test etait ROUGE sur `origin/master`
    AVANT toute autre tranche (mesure au stash : `len(TARGETING_OPTIONS_UNPORTED) = 0`, 2 echecs
    dans ce fichier).

    Supprimer le VOLET serait excessif : le bloc genere et sa garde de fraicheur
    (`test_le_bloc_genere_est_a_jour`) restent PLEINEMENT utiles -- ils gardent la SYNCHRONIE entre
    la table et son commentaire, ce qui est vrai pour toute taille, zero compris. Ce qui n'avait
    plus d'objet, c'est le seul PLANCHER DE POPULATION -- la forme meme que `probe_1021` decrit en
    majuscules (« aucun cran d'ici ne compare un compte a un nombre ») et qui a fait rougir CINQ
    cliquets le 2026-08-13 en prenant le PROGRES pour une panne. Il est remplace par une assertion
    qui MORD a taille nulle : l'egalite ensembliste derivation <-> table.

    ⚠ La table peut REMONTER (une ability non portee dont on relit le masque y entre), donc zero
    n'est pas un etat terminal : une garde qui n'aurait su vivre qu'a zero aurait le defaut
    SYMETRIQUE de celle qu'elle remplace."""
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    mes = comptes.deriver()
    assert len(mes["hors_bloc"]) + len(mes["bloc"]) == mes["total"], (
        "le decoupage PERD des entrees : %d hors-bloc + %d bloc != %d au total"
        % (len(mes["hors_bloc"]), len(mes["bloc"]), mes["total"]))
    assert mes["total"] == len(TARGETING_OPTIONS_UNPORTED), (
        "la derivation ne voit PAS la table : %d derive != %d dans la table"
        % (mes["total"], len(TARGETING_OPTIONS_UNPORTED)))


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


# ---------------------------- 3. aucun ORDINAL d'enum cite n'est celui du build PRECEDENT

def test_aucun_ordinal_cite_ne_vient_du_build_precedent():
    """L'autre forme du motif : celle qu'alimente le JEU, pas notre cadence. Une insertion dans un
    enum natif decale tous les membres suivants, et chaque ordinal recopie en commentaire devient
    faux -- en silence, puisqu'aucun code ne le lit.

    MESURE (`gqfc5mff6c` -> `rnca9r7q6c`, insertion d'`AttackTile` en 8, 73 membres decales) :
    **37** citations perimees dans `engine/**`, dont le `Damage(34)` que `#504-r1` n'avait vu que
    sur un fichier. Corriger : `python scripts/python/probe_519_ordinaux_decales.py --ecrire`.

    ⚠ LA REFERENCE N'EST PLUS << LE BUILD PRECEDENT >> (#10028) -- le NOM de ce test est garde tel
    quel a dessein (un test renomme DISPARAIT du corpus, cf. #455-r3), mais sa source est desormais
    la MEMOIRE ARCHIVEE : l'UNION des ordinaux portes sur AU MOINS UNE archive. Une citation
    perimee depuis DEUX builds redevient donc visible, ce que la version << build precedent >>
    disait explicitement ne pas voir."""
    trouves, vieux, neuf, blds = ordinaux.balayer()
    assert vieux and neuf, (
        "enum introuvable pour les builds %r -- MESURE IMPOSSIBLE, ce n'est pas un vert" % (blds,))
    perimes = ["%s:%d %s(%d) -> %d" % (f.name, i, n, o, v) for f, i, n, o, v in trouves]
    assert perimes == [], "ordinaux cites PERIMES :\n  " + "\n  ".join(perimes)


def test_le_detecteur_d_ordinaux_a_de_quoi_trouver():
    """Ce probe ne peut rien voir si la memoire archivee porte le MEME enum que le build courant :
    son zero serait alors vide de sens. On exige donc qu'il existe des membres DECALES -- sinon le
    vert ci-dessus ne prouve rien et il faut le dire.

    ⚠ CE TEST ETAIT ROUGE SUR `master`, ET LE DEFAUT ETAIT DANS LE PROBE (#10028). L'ancien
    `builds()` elisait un build de reference par une heuristique BIAISEE -- « celui qui partage le
    plus de NOMS avec le courant » --, or plus deux tables se ressemblent, plus ce score est haut :
    elle convergeait donc vers le build sur lequel il n'y a RIEN a voir. Mesure : `rnca9r7q6c`
    porte **0** membre decale contre `t6dpr4k06g`, `gqfc5mff6c` en porte **73** -- et l'heuristique
    elisait `rnca9r7q6c`. Le detecteur etait VACANT et son voisin ci-dessus etait un VERT VIDE.

    ⚠ LE CALCUL EST DELEGUE AU PROBE, il n'est plus recopie ici -- et ce n'est pas du style : ecrite
    a la main, la comparaison `vieux[n] != neuf[n]` serait TOUJOURS vraie depuis que `vieux` rend un
    `frozenset` (un ensemble n'est jamais egal a un entier), donc ce test serait VERT ET VACANT,
    l'etat exact qu'il existe pour interdire. C'est la lecon d'`_olds()` (#10023) : un cliquet qui
    reconstruit ce qu'il garde ne garde pas ce qui tourne."""
    _t, vieux, neuf, blds = ordinaux.balayer()
    assert vieux and neuf, "MESURE IMPOSSIBLE pour les builds %r" % (blds,)
    decales = ordinaux.membres_decales(vieux, neuf)
    assert decales, (
        "aucun membre decale sur les archives %r : le detecteur ne peut RIEN trouver, son zero ne "
        "dit rien de la fraicheur des citations" % (blds,))
    # ... et le critere DISCRIMINE : un critere vacant (celui du `frozenset != int` decrit
    # ci-dessus) rendrait TOUS les membres. Sans cette borne haute, le non-vide ci-dessus serait
    # satisfait par la panne meme qu'il est cense exclure.
    assert len(decales) < len(neuf), (
        "le detecteur rend TOUS les %d membres comme decales : le critere ne discrimine plus "
        "(compare-t-il un ensemble a un entier ?)" % len(neuf))


@pytest.mark.parametrize("verdict", [temoins.PERIME, temoins.PERISSABLE, temoins.STABLE])
def test_les_trois_verdicts_sont_exhaustifs(verdict):
    """La partition doit etre TOTALE : aucun site ne doit sortir sans verdict. Un `None` qui passe
    a travers serait invisible du filtre `PERIME` ci-dessus."""
    sites = temoins.balayer()
    assert all(s.verdict in (temoins.PERIME, temoins.PERISSABLE, temoins.STABLE) for s in sites)
    assert verdict in (temoins.PERIME, temoins.PERISSABLE, temoins.STABLE)
