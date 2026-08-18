"""#477-r24 -- GARDE offline : une phase native est NOMMEE, et attribuee au drain qu'elle opere.

Le probe `probe_477r24_phase_attribution.py` MESURE ; ce fichier GARDE. Il rejoue les trois etages
et la contre-epreuve, plus deux crans que le probe ne porte pas :

  * l'ordinal ECRIT au site est fige ICI AUSSI, en dur, independamment du mirror. `probe_313`
    redevient vert des qu'on regenere `phase_type.py` apres un renumerotage du build ; ce test-la
    ne le peut pas ;
  * **`ReviveUnit` n'est le drain d'AUCUNE phase** -- c'est le resultat de la tranche, et il est
    assertionne comme tel, pas seulement documente.

⚠ Le test ASSERTIONNE SON PROPRE NON-VIDE (corpus non vide, mutants non vides) : un balayage a
perimetre casse rendrait un ensemble vide, et un ensemble vide passe pour vert.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PY = Path(__file__).resolve().parents[2]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import probe_477r24_phase_attribution as P  # noqa: E402
from engine.streams.phase_type import PhaseType  # noqa: E402
from symbols_layout import current_build  # noqa: E402


@pytest.fixture(scope="module")
def ref():
    return P.enum_natif(current_build())


@pytest.fixture(scope="module")
def ops():
    o = P.noms_operations(current_build())
    assert len(o) > 100, "methods.tsv n'a rendu que %d methode(s) : perimetre casse" % len(o)
    return o


@pytest.fixture(scope="module")
def corpus():
    c = P.charger()
    assert len(c) > 500, "corpus a %d fichier(s) : perimetre casse" % len(c)
    sites = sum(1 for ch, li in c.items() for _ in P.sites(li, ch))
    assert sites > 20, "seulement %d site(s) de phase : le detecteur ne voit plus rien" % sites
    return c


def test_etape1_mirror_et_ordinaux_ecrits(ref):
    """Le mirror est bijectif ET les ordinaux ecrits aux sites sont ceux du build."""
    assert P.etape1(ref) == []


def test_ordinaux_figes_en_dur():
    """Cliquet independant du mirror : les valeurs que le depot ECRIT dans ses docstrings.

    Si le build renumerote, ce test tombe meme apres regeneration du mirror -- c'est tout
    l'interet (CLAUDE.md, « FIGER l'ordinal ECRIT AU SITE »)."""
    assert int(PhaseType.ProcessDeaths) == 12
    assert int(PhaseType.ProcessRemovals) == 13
    assert int(PhaseType.StartBattle) == 0
    assert int(PhaseType.ProcessDamageEvents) == 14
    assert int(PhaseType.ProcessPendingTriggeredAbilities) == 15
    assert P.ORDINAUX_ECRITS[13] == "ProcessRemovals"
    #: #10028 -- l'ordinal du drain des damage-events est ECRIT au depot depuis que ses deux
    #: citations sont NOMMEES (`dispatch/damage_events.py`, `test_443r2b2_post_damage_taken`).
    #: Il entre donc ICI, au meme titre que les six autres : c'est le cran que `probe_313` ne
    #: peut pas rendre (il redevient vert des qu'on regenere le mirror).
    assert P.ORDINAUX_ECRITS[14] == "ProcessDamageEvents"


def test_aucune_phase_ne_nomme_un_revive(ref):
    """LE RESULTAT DE LA TRANCHE, assertionne : aucun `PhaseType` ne nomme un revive, et
    `ReviveUnit` n'est le drain d'AUCUNE phase mesuree.

    Le contre-controle (`revive` present dans les noms d'operations) evite le test VIDE : si le
    mot n'existait nulle part, l'assertion du dessus serait vraie pour une mauvaise raison."""
    assert not [n for n in ref.values() if "revive" in n.lower()]
    for operations in P.DRAIN_MESURE.values():
        assert "ReviveUnit" not in operations
    ops = P.noms_operations(current_build())
    assert "ReviveUnit" in ops, "le jeton cherche par l'etape 3 n'existe plus : garde inerte"


def test_etape2_aucun_ordinal_de_phase_nu(ref, corpus):
    """Invariant 0 : sous `scripts/python/**`, un ordinal de phase porte toujours son membre."""
    ecarts = P.etape2(ref, corpus)
    assert ecarts == [], "ordinaux de phase NUS :\n  " + "\n  ".join(ecarts)


def test_etape3_attribution_conforme_au_drain_mesure(ref, corpus, ops):
    """Invariant 0 : aucune ligne n'attribue a une phase une operation qu'elle ne draine pas."""
    ecarts, exemptions, non_couvertes = P.etape3(ref, corpus, ops)
    assert ecarts == [], "attributions FAUSSES :\n  " + "\n  ".join(ecarts)
    # l'echappatoire reste VISIBLE et BORNEE : elle ne doit pas devenir la norme.
    assert len(exemptions) <= 5, "trop d'exemptions declarees : %d" % len(exemptions)
    assert non_couvertes, "aucune phase NON COUVERTE : le probe se declarerait vert partout"


def test_contre_epreuve_chaque_mutant_mord(ref, ops, corpus):
    """`a_mordu` par mutant, SEPARE du verdict -- trois tranches de suite ont eu une
    contre-epreuve inerte qui passait pour mordante."""
    assert P.MUTANTS, "aucun mutant : contre-epreuve vide"
    cible = P.PY / "engine" / "streams" / "phase_type.py"
    assert cible in corpus, "la cible d'injection n'est pas dans le corpus"
    inertes = []
    for nom, ligne, etage in P.MUTANTS:
        mute = dict(corpus)
        mute[cible] = list(corpus[cible]) + [ligne]
        if etage == 2:
            trouve, temoin = P.etape2(ref, mute), P.etape2(ref, corpus)
        else:
            trouve = P.etape3(ref, mute, ops)[0]
            temoin = P.etape3(ref, corpus, ops)[0]
        if len(trouve) <= len(temoin):
            inertes.append("%s (etage %d)" % (nom, etage))
    assert inertes == [], "mutant(s) INERTE(s) :\n  " + "\n  ".join(inertes)
