"""CLIQUET #457-r6 -- aucune entree de la banque ne rejoue un fichier que `probe_457` joue deja.

CE QUE CETTE GARDE TIENT, ET POURQUOI ELLE EXISTE
--------------------------------------------------
Jusqu'a #457-r5, trois entrees de `scripts/ratchets.ps1` etaient des invocations `pytest`
NOMMANT leurs fichiers a la main (`pytest_signatures`, `pytest_attestations`,
`pytest_adjacency`). C'etaient des ALLOWLISTS -- et c'est precisement ce que `probe_457`
generalise : son perimetre se DERIVE (`git ls-files scripts/python/tests`, tout ce qui n'est
pas `_live.py`), donc il joue DEJA ces memes fichiers.

Depuis #457-r5, la banque faisait donc DEUX FOIS le meme travail. Mesure du 2026-08-03,
durees ISOLEES (`ratchets.ps1 -Serial`, machine calme) : 29,0 + 7,5 + 3,9 = **40,4 s** de
travail strictement redondant, sur 739,6 s de somme isolee.

L'INVARIANT : une entree `pytest` de la banque ne doit nommer aucun fichier du perimetre
derive de `probe_457`. Le violer ne casse rien -- c'est du temps, pas un faux vert -- mais ce
temps est celui du mur que #457-r6 cherche a baisser, et un doublon reintroduit serait aussi
invisible que celui-ci l'a ete.

CE QUE CETTE GARDE NE DIT PAS
-----------------------------
Elle ne dit pas qu'une entree `pytest` est TOUJOURS illegitime : un fichier de test HORS du
perimetre derive (par exemple un `_live.py`, que `probe_457` exclut a dessein) aurait toute sa
place dans la banque sous cette forme. Le critere est l'APPARTENANCE AU PERIMETRE, pas la
forme de la commande.

Elle ne garde pas non plus que `probe_457` joue INTEGRALEMENT ces fichiers : son filet
deselectionne les items dont la cloture de fixtures touche le monde live. C'est verifie ici,
mais STATIQUEMENT et sur le seul axe qui soit derivable -- le suffixe `_offline`, declaratif et
tenu par le depot. Un fichier du perimetre qui deviendrait mixte serait rapporte par le shard
(`N item(s) DESELECTIONNE(S)`), non bloquant.

ASCII only (cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_439_cliquet_peut_rougir as B439                            # noqa: E402
import probe_457_offline_tests_green as P457                            # noqa: E402

#: Les trois entrees retirees par #457-r6, avec les fichiers qu'elles nommaient. Elles sont
#: citees ICI pour que le test PROUVE la redondance au lieu de la supposer -- si l'une d'elles
#: sortait du perimetre derive, le test rougirait et la retirer aurait ete une PERTE.
RETIREES = (
    "tests/test_additional_hits_variant_signatures_offline.py",
    "tests/test_337_dsl_triggers_attestation_offline.py",
    "tests/engine/runner/test_433_r1_identity_shortcircuit_offline.py",
    "tests/engine/runner/test_433_r3_isadjacent_node_offline.py",
    "tests/engine/runner/test_433_r3_r1_dsl_footprint_offline.py",
)


def _perimetre() -> set:
    fichiers = set(P457.candidate_files())
    assert fichiers, "perimetre de probe_457 VIDE -- ce test ne mesurerait rien"
    return fichiers


def test_les_fichiers_des_entrees_retirees_sont_bien_dans_le_perimetre_derive():
    """LA preuve que la deduplication n'a rien perdu.

    Sans elle, retirer les trois entrees serait un retrecissement de perimetre deguise en
    optimisation -- exactement la faute que #457-r5 a reparee.
    """
    perimetre = _perimetre()
    hors = [rel for rel in RETIREES if rel not in perimetre]
    assert hors == [], (
        "fichier(s) retire(s) de la banque et ABSENT(S) du perimetre de probe_457 -- ils ne "
        "sont donc plus joues par personne : %s" % hors)


def test_aucune_entree_pytest_de_la_banque_ne_double_le_perimetre_derive():
    """L'invariant, sur la banque REELLE (derivee du texte de `ratchets.ps1`, jamais saisie)."""
    perimetre = _perimetre()
    banque = B439.banque_par_texte()
    assert banque, "banque VIDE -- la derivation a echoue, ce test ne mesurerait rien"

    doublons = []
    for ident, argv in sorted(banque.items()):
        if "pytest" not in argv:
            continue
        for arg in argv:
            rel = arg.replace("\\", "/")
            if rel in perimetre:
                doublons.append((ident, rel))
    assert doublons == [], (
        "entree(s) de la banque qui rejoue(nt) un fichier deja joue par probe_457 (perimetre "
        "DERIVE) -- travail fait deux fois :\n"
        + "\n".join("  %s -> %s" % d for d in doublons)
        + "\n  Retirer l'entree : probe_457 couvre deja ce fichier, sans allowlist.")


def test_les_fichiers_retires_sont_declares_OFFLINE_par_leur_nom():
    """Le seul axe DERIVABLE de la couverture integrale par `probe_457`.

    Son filet deselectionne les items a fixture live. Le suffixe `_offline` ne le PROUVE pas
    formellement, mais il est declaratif et tenu par le depot ; l'exiger ici empeche qu'un
    fichier mixte se retrouve, demain, couvert seulement pour moitie.
    """
    pas_offline = [rel for rel in RETIREES if not rel.endswith("_offline.py")]
    assert pas_offline == [], pas_offline


def test_le_temoin_ce_fichier_est_LUI_MEME_dans_le_perimetre():
    """Anti-vacuite : si `candidate_files` cessait de voir ce repertoire, les tests ci-dessus
    passeraient au vert sur un ensemble vide."""
    moi = Path(__file__).resolve().relative_to(PYDIR).as_posix()
    assert moi in _perimetre(), moi
