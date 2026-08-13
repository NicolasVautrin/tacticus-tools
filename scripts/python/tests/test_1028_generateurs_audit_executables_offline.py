"""#1028 -- la garde : TOUT generateur d'audit reste EXECUTABLE, et la population est DERIVEE.

CONTRE QUOI. `audit_npc_registry.py` est reste INEXECUTABLE une journee entiere sur `master`
(`ImportError: cannot import name 'TRAIT_COMMON_MAX'`, cause : #1015 a retire le symbole de
`audit_kit_coverage.py`, a raison). Personne ne l'a vu, parce qu'un generateur mort n'emet aucun
signal -- son fichier de sortie cesse simplement de CHANGER.

POURQUOI AUCUNE GARDE EXISTANTE NE POUVAIT L'ATTRAPER. Mesure : `audit_kit_coverage` est cite par
NEUF fichiers de `scripts/python/tests`, `audit_combat_ability_coverage` par TROIS,
`audit_npc_registry` par ZERO. Les gardes existantes gardent le SUJET de leur tranche et importent
un auditeur comme MOYEN ; aucune ne pose la question « tous les generateurs tournent-ils ? ». Une
garde qui cite ses auditeurs un par un ne peut pas voir celui que personne n'a cite -- le vice
repete du depot (un recenseur ne rend jamais zero sur ce qu'il ne visite pas), transpose des
DONNEES aux OUTILS.

CINQ ETAGES. Le [4] est load-bearing : sans lui, un `verifier()` qui retomberait sur « vert »
rendrait les etages [2] et [3] vrais par VACUITE -- la faute exacte que #1015 volet 1 a reparee
trois fois.

Usage : depuis `scripts/python/`
    python -m pytest tests/test_1028_generateurs_audit_executables_offline.py -q

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

_PYROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

#: Ce qui doit faire REJOUER ce fichier.
#:
#: `scripts/python/**/*.py` SEUL, et la forme est MESUREE, pas supposee : j'avais d'abord ecrit la
#: double forme (`*.py` + `**/*.py`), en croyant qu'un `**/` exige un segment et raterait donc
#: `scripts/python/audit_kit_coverage.py` -- soit precisement le fichier dont la modification a
#: cause le defaut. `declencheur_cliquet.couvre` tranche l'inverse : le glob unique couvre la
#: racine ET les sous-dossiers, et la double forme sort en `redondants()`.
#:
#: Le perimetre est large A DESSEIN, et ce n'est pas une paresse : la cause racine mesuree n'est
#: PAS dans le generateur casse, elle est dans un foyer PARTAGE qu'il importe. Une declaration
#: reduite aux `audit_*.py` ne se serait rejouee sur #1015 -- qui ne touche QUE
#: `audit_kit_coverage.py` -- que par chance, et raterait un renommage dans `engine/**`.
#:
#: `docs/rl/*.md` + `*.tsv` : la source B DERIVE la population depuis les artefacts versionnes
#: (« Genere par `scripts/python/<X>` »). Un artefact ajoute ou retire change donc la population
#: gardee, sans qu'aucun `.py` ne bouge.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/**/*.py",
        "docs/rl/*.md",
        "docs/rl/*.tsv",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Offline : garde que TOUT generateur d'audit reste EXECUTABLE. La population est DERIVEE "
        "par deux sources independantes (prefixe `audit_*.py` ; artefact versionne de `docs/rl` "
        "qui NOMME son generateur), donc elle bouge quand un `.py` de `scripts/python/**` bouge "
        "ET quand un artefact de `docs/rl` apparait ou disparait. `build: True` parce que l'import "
        "d'un generateur traverse `unit_map`/`gameconfig`, qui lisent les entrees du build."
    ),
}

import probe_1028_generateurs_audit_executables as P      # noqa: E402


# ================================================================================================
# 1. LA DERIVATION -- non vide, et CHAQUE SOURCE APPORTE
# ================================================================================================

def test_la_population_est_derivee_et_non_vide():
    """Un recenseur vide serait VERT sur tout. On assertionne son propre non-vide (le controle qui
    a sauve #270-r1-r1-r3 : un test dont l'ensemble mesure est vide passe pour un succes)."""
    par_module = P.generateurs()
    assert par_module, (
        "AUCUN generateur derive : les deux sources sont muettes. Ce n'est pas un vert -- c'est un "
        "recenseur qui ne visite rien, donc incapable de rougir sur quoi que ce soit.")
    for mod, sources in par_module.items():
        assert (P.PY / (mod + ".py")).is_file(), (
            "%s est derive mais son fichier n'existe pas (%r)" % (mod, sorted(sources)))
        assert sources <= {"prefixe", "artefact"}, (
            "%s porte une source inconnue %r" % (mod, sorted(sources)))


def test_la_source_ARTEFACT_apporte_ce_que_le_PREFIXE_raterait():
    """L'ETAGE QUI JUSTIFIE LA SECONDE SOURCE, exerce au lieu d'etre affirme.

    Mesure au 2026-08-13 : le prefixe rend 4 modules, l'artefact 5, et le cinquieme
    (`probe_251_citation_resolution`) N'A PAS le prefixe -- une liste par convention de nom aurait
    donc rate un generateur reel des le premier jour. Sans cet etage, la source B pourrait etre
    supprimee sans qu'aucune assertion ne tombe."""
    par_module = P.generateurs()
    par_artefact_seule = {m for m, s in par_module.items() if s == {"artefact"}}
    assert par_artefact_seule, (
        "la source ARTEFACT n'apporte AUCUN generateur que le prefixe ne voit deja. Deux lectures, "
        "et il faut trancher AVANT de faire taire ce test : (a) tous les generateurs ont acquis le "
        "prefixe `audit_*` -- alors la source B est devenue redondante, ENTERINE-le explicitement ; "
        "(b) la source B s'est CASSEE (motif 'Genere par' disparu des artefacts, `git ls-files` "
        "muet) -- alors le recenseur a perdu un oeil et le prochain generateur hors convention "
        "sera invisible. Modules vus par le prefixe : %r" % sorted(par_module))


def test_chaque_generateur_derive_porte_un_point_d_entree():
    """Un module importable mais sans garde `__main__` ne produit plus rien -- et l'import seul ne
    le dirait pas."""
    sans = [m for m in sorted(P.generateurs()) if m not in P.EXCEPTIONS and not P.lancable(m)]
    assert sans == [], (
        "generateur(s) sans garde `__main__`, donc non lancable(s) : %r" % sans)


# ================================================================================================
# 2. LE CRAN -- tous EXECUTABLES
# ================================================================================================

def test_tous_les_generateurs_derives_s_importent_en_process_frais():
    """LE CRAN. Process FRAIS obligatoire : dans le process courant, un module deja importe par un
    autre test de la passe rendrait VERT un module qui ne s'importe plus seul.

    Vu ROUGE le 2026-08-13 sur `af2e590c`, message verbatim :
        ROUGE  audit_npc_registry   IMPORT_ROUGE
               ImportError: cannot import name 'TRAIT_COMMON_MAX' from 'audit_kit_coverage'
    """
    m = P.mesurer()
    rouges = m["rouges"]
    assert not rouges, (
        "generateur(s) d'audit INEXECUTABLE(S) -- leur fichier de sortie a cesse d'etre "
        "regenerable, et rien d'autre ne le signale :\n%s\n"
        "Si l'un d'eux est inexecutable pour une raison LEGITIME (dependance live, entree "
        "gitignoree), declare-le dans `probe_1028.EXCEPTIONS` avec sa raison et sa source -- "
        "jamais en le retirant de la derivation."
        % "\n".join("  %-42s %s : %s" % (mod, v[1], v[2]) for mod, v in sorted(rouges.items())))


# ================================================================================================
# 3. LA CONTRE-EPREUVE -- le verificateur SAIT rougir (sinon tout ce qui precede est vacuite)
# ================================================================================================

def test_le_verificateur_VOIT_un_import_casse(tmp_path):
    """L'ETAGE LOAD-BEARING. Si `verifier()` retombait sur « vert » (chemin faux, cwd errone, `rc`
    ignore), les etages precedents seraient vrais par VACUITE et ce fichier serait un faux vert --
    exactement la faute que #1015 volet 1 a du reparer trois fois."""
    (tmp_path / "temoin_1028_casse.py").write_text(
        "from module_qui_n_existe_pas_1028 import CONSTANTE_ABSENTE\n", encoding="utf-8")
    ok, panne, detail = P.verifier("temoin_1028_casse", racine=tmp_path)
    assert not ok, (
        "le verificateur declare EXECUTABLE un module dont l'import leve : il ne peut rougir sur "
        "rien, et tout le fichier est un faux vert.")
    assert panne == "IMPORT_ROUGE", "panne mal NOMMEE : %r (un `rc` ne nomme rien)" % panne
    assert "module_qui_n_existe_pas_1028" in detail or "ModuleNotFound" in detail, (
        "le detail ne porte pas la cause : %r -- un message qui ne nomme pas la cause fait "
        "corriger la mauvaise chose (lecon #467-r6)." % detail)


def test_le_verificateur_SAIT_AUSSI_dire_OK(tmp_path):
    """Le pendant : un verificateur qui rendrait ROUGE sur tout serait inutilisable, et l'etage
    precedent passerait quand meme."""
    (tmp_path / "temoin_1028_sain.py").write_text("VALEUR = 1\n", encoding="utf-8")
    ok, panne, detail = P.verifier("temoin_1028_sain", racine=tmp_path)
    assert ok, "le verificateur rougit sur un module SAIN (%s : %s)" % (panne, detail)


# ================================================================================================
# 4. LES EXCEPTIONS -- declarees, motivees, et REELLEMENT rouges
# ================================================================================================

def test_les_exceptions_declarees_sont_bien_formees_et_encore_rouges():
    """Une exception RETIRE un generateur du cran : elle porte donc sa raison, et elle doit encore
    correspondre a un generateur REELLEMENT rouge. Une exception posee sur un generateur qui
    remarche est une scorie -- elle masquerait sa PROCHAINE panne, en silence."""
    par_module = P.generateurs()
    for mod, e in sorted(P.EXCEPTIONS.items()):
        assert mod in par_module, (
            "exception sur `%s`, qui n'est meme pas derive comme generateur : elle ne protege "
            "rien et donne l'illusion d'un perimetre couvert." % mod)
        for champ in ("raison", "source", "date"):
            assert e.get(champ), "exception `%s` : champ `%s` vide ou absent" % (mod, champ)
        assert e["raison"].isascii() and len(e["raison"]) > 20, (
            "exception `%s` : raison trop courte ou non ASCII -- une exception sans motif lisible "
            "est une mise sous silence." % mod)
        ok, _panne, _d = P.verifier(mod)
        assert not ok, (
            "`%s` est declare inexecutable, mais il S'IMPORTE tres bien : l'exception est une "
            "scorie qui masquera sa prochaine panne. La retirer fait partie de la tranche qui "
            "l'a reparee." % mod)


def test_une_mesure_incomplete_LEVE_au_lieu_de_rendre_un_vert(monkeypatch):
    """Doctrine : un echec RENDU se lit comme une mesure. Si la population ne peut pas etre etablie
    (git muet), le probe doit LEVER -- une liste vide ou tronquee se lirait « tous verts »."""
    monkeypatch.setattr(P, "generateurs", lambda: {})
    with pytest.raises(P.MesureIncomplete):
        P.mesurer()
