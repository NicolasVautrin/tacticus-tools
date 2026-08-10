"""#603 -- GARDE : les champs `FOYER:`/`BLOCAGE:` du backlog DESIGNENT quelque chose de REEL.

CE QUE CE FICHIER GARDE, ET POURQUOI CHAQUE CRAN EXISTE
--------------------------------------------------------
Le champ `FOYER:` sert a prouver la DISJONCTION de deux tranches avant de les dispatcher
ensemble. Il n'a donc de valeur que s'il designe des fichiers qui EXISTENT : un foyer qui
pourrit en silence rend une disjonction que personne ne peut plus verifier.

⚠ **Ce n'est pas une crainte, c'est une MESURE.** En ecrivant les 173 champs de cette tranche,
le garde de l'etage 3 a attrape `frida/hooks/probes/try-to-campaign.ts`, cite par `#390-r1` --
un fichier **SUPPRIME du depot** par `0a61b0c6` (<< retirer le code mort de `frida/hooks` >>).
La fiche demandait << la faire passer par le foyer, OU LA RETIRER >> : elle a ete retiree, donc
le residu est PERIME et personne ne l'avait vu. Le meme etage a attrape deux autres chemins que
la lecture avait mal transcrits (`probe_283_enums_dumpes` pour `probe_283_enum_ordinal_sweep`,
`probe_440_ecritures_concurrentes` pour `probe_440_repo_root_scan_guard`).

LES CINQ ETAGES
----------------
  1. PARTITION EXHAUSTIVE  -- fermees + annotees + non annotees == lignes visitees.
  2. BIJECTION du TSV      -- toute fiche non annotee a une decision, toute decision une fiche.
  3. AUCUN FOYER MORT      -- chaque chemin ecrit existe (`git ls-files`), globs compris.
  4. VOCABULAIRE de BLOCAGE-- chaque mot est l'un des cinq, aucun autre.
  5. INDEX RE-DERIVABLE    -- `--index` regenere le fichier A L'IDENTIQUE (doctrine des
                              documents generes : un `git status` propre apres regeneration est
                              la seule preuve qu'ils le sont).
  6. LE GARDE MORD         -- contre-epreuve : un chemin bidon et un blocage bidon sont REFUSES.
     Sans ce cran, les etages 3 et 4 pourraient etre verts en ne verifiant RIEN.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
RACINE = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import backlog_entries as B          # noqa: E402
import index_foyers as IF            # noqa: E402

BACKLOG = RACINE / "docs" / "rl" / "backlog.md"
INDEX = RACINE / "docs" / "rl" / "index-foyers.md"

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/backlog_entries.py",
        "scripts/python/index_foyers.py",
        "scripts/python/probe_603_index_foyers.py",
        "scripts/python/migration_603_foyers.py",
        "docs/rl/backlog.md",
        "docs/rl/index-foyers.md",
    ),
    "build": False,
    "toujours": True,
    "raison": "Les `chemins` nomment ce que ce fichier LIT (le backlog, l'index, le TSV de "
              "decisions) et IMPORTE (`backlog_entries`, `index_foyers`). Mais ils ne "
              "SUFFISENT PAS, d'ou `toujours: True` -- et c'est une MESURE, pas un aveu. "
              "L'etage 3 confronte chaque chemin "
              "de foyer a `git ls-files` : la SUPPRESSION ou le RENOMMAGE de n'importe quel "
              "fichier du depot peut donc faire basculer ce verdict, sans qu'aucun des fichiers "
              "que ce test LIT ne bouge. C'est exactement ce qui s'est produit -- "
              "`frida/hooks/probes/try-to-campaign.ts`, cite par `#390-r1`, a ete supprime par "
              "`0a61b0c6` et le foyer est reste ecrit. Un perimetre borne (backlog.md, le TSV, "
              "les trois modules) serait donc un FAUX VERT sur le seul gisement qui compte. Le "
              "fichier est offline, sans runner, et court (6 tests, ~4 s dont un `git ls-files`).",
}


@pytest.fixture(scope="module")
def entrees():
    return B.lire(BACKLOG)


def test_etage1_la_partition_du_backlog_est_exhaustive(entrees):
    fermees = [e for e in entrees if e.ferme]
    ouvertes = [e for e in entrees if e.ouverte]
    annotees = [e for e in ouvertes if e.annotee]
    non = [e for e in ouvertes if not e.annotee]
    assert entrees, "aucune ligne de tableau lue -- le parseur ou le fichier a change de forme"
    assert len(fermees) + len(annotees) + len(non) == len(entrees), (
        "PARTITION CASSEE : %d fermees + %d annotees + %d non annotees != %d visitees"
        % (len(fermees), len(annotees), len(non), len(entrees)))


def test_etage2_chaque_fiche_non_annotee_a_une_decision_et_reciproquement(entrees):
    non = {IF.cle(e.ident) for e in entrees if e.ouverte and not e.annotee}
    decisions = set(IF.lire_decisions())
    assert decisions, "le TSV de migration est VIDE -- ce test se noterait sur rien"
    manquants = sorted(non - decisions)
    assert not manquants, (
        "%d fiche(s) non annotee(s) SANS decision : %s" % (len(manquants), manquants[:10]))


def test_etage3_aucun_foyer_ne_designe_un_fichier_disparu(entrees):
    fichiers = IF._fichiers_versionnes()
    reps = set()
    for f in fichiers:
        p = f
        while "/" in p:
            p = p.rsplit("/", 1)[0]
            reps.add(p + "/")

    annotees = [e for e in entrees if e.ouverte and e.annotee]
    assert annotees, "aucune fiche annotee -- ce test se noterait sur un ensemble VIDE"

    absents: dict[str, list[str]] = {}
    controles = 0
    for e in annotees:
        for p in e.foyer_chemins:
            controles += 1
            if not IF._valide_chemin(p, fichiers, reps):
                absents.setdefault(p, []).append(IF.cle(e.ident))
    assert controles > 0, "aucun chemin controle -- l'extraction du champ FOYER est cassee"

    # << absent de l'arbre >> ne vaut PAS << mort >> : un foyer nomme legitimement un fichier
    # que la tranche va CREER. Le discriminant est l'HISTORIQUE.
    #
    # ⚠ TEMOIN POSITIF OBLIGATOIRE. `chemins_supprimes` interroge `git log` : si git devenait
    # muet (binaire absent, depot inaccessible, option retiree), il rendrait une liste VIDE et
    # ce cliquet serait VERT POUR TOUJOURS, sans rien garder. On lui donne donc un chemin dont
    # on SAIT qu'il a ete supprime -- `frida/hooks/probes/try-to-campaign.ts`, retire par
    # `0a61b0c6` -- et on exige qu'il le voie AVANT de croire son silence sur les autres.
    TEMOIN_SUPPRIME = "frida/hooks/probes/try-to-campaign.ts"
    assert IF.chemins_supprimes([TEMOIN_SUPPRIME]) == [TEMOIN_SUPPRIME], (
        "le detecteur de foyer POURRI ne voit pas un fichier dont la suppression est certaine "
        "(%s, retire par 0a61b0c6) : il rend un vide qui ne prouve RIEN" % TEMOIN_SUPPRIME)
    assert IF.chemins_supprimes(["scripts/python/rl_duel.py"]) == [], (
        "le detecteur accuse un fichier VIVANT -- il accuserait a tort et se ferait desactiver")

    morts = IF.chemins_supprimes(sorted(absents))
    assert not morts, (
        "%d foyer(s) POURRI(s) : le fichier a EXISTE puis a ete supprime/renomme, et la ligne "
        "de residu le cite encore -- elle est a requalifier. %s"
        % (len(morts), [(p, absents[p]) for p in morts]))


def test_etage4_le_vocabulaire_de_blocage_est_tenu(entrees):
    annotees = [e for e in entrees if e.ouverte and e.annotee]
    assert annotees
    hors = sorted({e.blocage for e in annotees if e.blocage not in B.BLOCAGES})
    assert not hors, (
        "mot(s) de BLOCAGE hors des cinq (%s) : %s" % (", ".join(B.BLOCAGES), hors))


def test_etage5_l_index_se_re_derive_a_l_identique(tmp_path):
    avant = INDEX.read_bytes()
    temoin = tmp_path / "index-foyers.md"
    IF.ecrire_index(BACKLOG, temoin)
    apres = temoin.read_bytes()
    assert apres == avant, (
        "`docs/rl/index-foyers.md` n'est pas re-derivable a l'identique -- il a ete edite a la "
        "main, ou le backlog a bouge sans qu'on le regenere "
        "(`python scripts/python/probe_603_index_foyers.py --index`)")


def test_etage6_le_garde_MORD_sur_un_chemin_et_un_blocage_bidons(tmp_path, monkeypatch):
    """Contre-epreuve : sans elle, les etages 3 et 4 pourraient etre verts en ne verifiant rien."""
    fichiers = IF._fichiers_versionnes()
    reps = {"scripts/python/"}
    assert IF._valide_chemin("scripts/python/rl_duel.py", fichiers, reps), (
        "temoin POSITIF absent : le validateur refuse un chemin qui EXISTE, il est casse")
    assert not IF._valide_chemin(
        "scripts/python/ce_fichier_n_existe_pas_603.py", fichiers, reps), (
        "le validateur ACCEPTE un chemin inexistant -- l'etage 3 ne garde rien")

    # FORME B (`import X` puis `X.foo()`) : on substitue l'ATTRIBUT du module, pas un nom
    # importe -- une liaison `from ... import lire_decisions` ne mordrait pas (cf. CLAUDE.md,
    # << HISSER, OUI -- MAIS EN FORME B >>). `ecrire_backlog` appelle bien `lire_decisions()`
    # depuis son propre module, donc la substitution est effective.
    faux_decisions = {
        "#zzz-1": ("scripts/python/ce_fichier_n_existe_pas_603.py", "aucun", "fiche"),
        "#zzz-2": ("scripts/python/rl_duel.py", "pas_un_mot", "fiche"),
    }
    monkeypatch.setattr(IF, "lire_decisions", lambda: faux_decisions)
    copie = tmp_path / "backlog.md"
    copie.write_bytes(BACKLOG.read_bytes())
    rc = IF.ecrire_backlog(copie, verifier_seulement=True)
    assert rc == IF.EX_ROUGE, "l'ecrivain a ACCEPTE un chemin bidon ET un blocage bidon"
    assert copie.read_bytes() == BACKLOG.read_bytes(), (
        "l'ecrivain a MODIFIE le fichier alors qu'il refusait -- l'ecriture n'est pas atomique")
