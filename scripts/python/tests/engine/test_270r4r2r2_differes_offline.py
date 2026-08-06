"""#270-r4-r2-r2 -- CLIQUET : le gisement des imports DIFFERES d'`engine/` ne se rouvre pas.

Un import differe ne casse pas un cycle, il le DEPLACE : l'echec du chargement part vers le
premier appel, et l'ordre d'initialisation devient dependant du chemin d'execution. #270-r4-r2
a coupe les deux SCC ; cette tranche a trie les differes restants et hisse ce qui etait hissable.
Ce qui suit empeche la remontee.

DEUX CRITERES, ET ILS NE SE VALENT PAS -- c'est le point de ce fichier :

  * etage 1, INVARIANT a ZERO (le differe GRATUIT). Sa cible est deja chargee par le PREAMBULE
    du meme fichier : ni cycle possible (l'arete existe deja), ni cout (le module est deja la).
    Un tel differe n'a AUCUNE raison d'etre. Un invariant ne se degrade pas en silence, lui.
  * etage 3, SEUIL (le compte total). Il est ecrit ici en sachant ce qu'il vaut : une garde en
    seuil cesse de mordre des qu'un contributeur ne remonte pas a lui seul le plafond. Il est
    la pour attraper une REPRISE DE MASSE, pas un site isole -- et l'etage 1, lui, mord sur un
    seul site.

  * etage 5, IMPORT REEL sur TOUT `engine/`. Il ne duplique PAS le cliquet #270-r4-r2 : celui-ci
    ne balaye que `services`/`playbook`/`entities`/`dsl`, quand cette tranche a hisse 98 fichiers
    sous `engine/runner`, hors de sa portee. Et il est INDISPENSABLE -- CONTRE-EPREUVE mesuree :
    en retirant du filtre l'arete `module -> paquet parent`
    (`migrate_270r4r2r2_hisser_differes.py --sans-ancetres`), le lot obtenu laisse le graphe
    declare a **0 SCC** et casse pourtant l'import de **405 des 409** modules. Un cliquet qui ne
    regarde que le graphe serait reste VERT sur cette regression-la.

Le graphe module-level (0 SCC) et sa contre-epreuve restent gardes par
`test_270r4r2_cycles_imports_offline.py` : on ne duplique pas, on s'appuie dessus.

100 % OFFLINE : aucun runner, aucune session Frida.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_270r4r2_import_en_premier as IP    # noqa: E402
import probe_270r4r2r2_tri_differes as TR       # noqa: E402

# Plafonds MESURES a la livraison de #270-r4-r2-r2 : 971 -> 346 instructions differees, dont
# 928 -> 219 inconditionnelles. C'est un SEUIL, pas un invariant : il attrape une reprise de
# MASSE. Le BAISSER quand une tranche descend -- un plafond qu'on ne descend pas cesse de mordre.
# #485-r1-r1 : le sweep des barils a fait tomber les GRATUITS (47 -> 3, les 3 restants etant des
# imports OPTIONNELS sous `try/except` que hisser denaturerait). Plafonds re-MESURES apres coup.
PLAFOND_DIFFERES = 211
PLAFOND_INCONDITIONNELS = 136


@pytest.fixture(scope="module")
def sites():
    lot, _ = TR.collecter(PYDIR / "engine", "")
    return lot


def test_etage0_temoin_le_balayage_voit_quelque_chose(sites):
    """TEMOIN d'abord : sans lui, les etages suivants seraient verts SUR RIEN."""
    fichiers = {s.module for s in sites}
    assert len(sites) >= 100, "portee derisoire : %d instruction(s) differee(s) vues" % len(sites)
    assert len(fichiers) >= 40, "portee derisoire : %d fichier(s)" % len(fichiers)
    # le visiteur distingue-t-il encore les causes ? Un visiteur casse rendrait une seule.
    causes = {s.cause_syn for s in sites}
    assert causes == {"fonction", "TYPE_CHECKING"}, (
        "le visiteur ne distingue plus les causes syntaxiques : %r" % sorted(causes))


def test_etage1_invariant_aucun_differe_gratuit():
    """INVARIANT a ZERO. Cible deja chargee par le preambule -> ni cycle, ni cout."""
    lot = TR.gratuits(PYDIR / "engine")
    assert lot == [], "\n".join(
        ["%d import(s) differe(s) GRATUIT(s) : leur cible est DEJA importee au niveau module "
         "dans le preambule du meme fichier." % len(lot),
         "Ni cycle possible (l'arete existe deja au niveau module), ni cout (le module est deja "
         "charge) : hisser l'instruction est sans effet de bord.",
         ""]
        + ["  %s:%d  %s" % t for t in lot[:40]])


def test_etage2_contre_epreuve_le_detecteur_discrimine(tmp_path):
    """Le detecteur de l'etage 1 ROUGIT-il encore ? Un `gratuits` casse rendrait `[]` toujours."""
    pkg = tmp_path / "p"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text("X = 1\nY = 2\n", encoding="utf-8")

    # (a) GRATUIT : `p.a` est deja au preambule, et la fonction le re-importe.
    (pkg / "b.py").write_text(
        "from .a import X\n\n\ndef f():\n    from .a import Y\n    return X, Y\n",
        encoding="utf-8")
    trouves = TR.gratuits(pkg, racine=tmp_path)
    assert [t for t in trouves if t[0] == "p.b"], (
        "le detecteur NE VOIT PAS un differe gratuit evident : %r" % (trouves,))

    # (b) PAS gratuit : aucun import module-level de `p.a` -> le differe peut avoir une raison.
    (pkg / "b.py").write_text("def f():\n    from .a import Y\n    return Y\n", encoding="utf-8")
    trouves = TR.gratuits(pkg, racine=tmp_path)
    assert not [t for t in trouves if t[0] == "p.b"], (
        "FAUX POSITIF : un differe sans import module-level de la cible est declare gratuit : %r"
        % (trouves,))

    # (c) PAS gratuit : l'import module-level est place APRES une definition (recette du
    # PLACEMENT). Il ne garantit rien pour le corps -> il ne doit pas compter comme preambule.
    (pkg / "b.py").write_text(
        "def f():\n    from .a import Y\n    return Y\n\n\nfrom .a import X  # noqa: E402\n",
        encoding="utf-8")
    trouves = TR.gratuits(pkg, racine=tmp_path)
    assert not [t for t in trouves if t[0] == "p.b"], (
        "un import de PLACEMENT (apres une definition) est compte comme preambule : %r"
        % (trouves,))

    # (d) PAS gratuit : sous un `if` dans la fonction -> hisser changerait la SEMANTIQUE.
    (pkg / "b.py").write_text(
        "from .a import X\n\n\ndef f(c):\n    if c:\n        from .a import Y\n"
        "        return Y\n    return X\n", encoding="utf-8")
    trouves = TR.gratuits(pkg, racine=tmp_path)
    assert not [t for t in trouves if t[0] == "p.b"], (
        "un import CONDITIONNEL est declare gratuit alors que le hisser changerait la "
        "semantique : %r" % (trouves,))


def test_etage3_seuil_le_compte_ne_remonte_pas(sites):
    """SEUIL, et il est nomme comme tel : il attrape une reprise de MASSE, pas un site isole."""
    inconditionnels = [s for s in sites if s.cause_syn == "fonction" and not s.conteneur]
    assert len(sites) <= PLAFOND_DIFFERES, (
        "le gisement des imports differes REMONTE : %d instruction(s) pour un plafond de %d.\n"
        "Casser le cycle d'abord ; un differe se justifie par le COUT, et le motif s'ecrit."
        % (len(sites), PLAFOND_DIFFERES))
    assert len(inconditionnels) <= PLAFOND_INCONDITIONNELS, (
        "les differes INCONDITIONNELS remontent : %d pour un plafond de %d"
        % (len(inconditionnels), PLAFOND_INCONDITIONNELS))


def test_etage5_tout_engine_s_importe_en_premier():
    """MESURE MATERIELLE, sur les 409 modules -- ce que le graphe ne peut PAS donner.

    CONTRE-EPREUVE (mesuree) : un lot de hissages filtre SANS l'arete `module -> paquet
    parent` laisse le graphe declare a 0 SCC et casse 405 des 409 imports. C'est cet etage,
    et lui seul, qui rougit dans ce regime.
    """
    mods = IP._modules_sous(("engine",))
    assert len(mods) >= 300, "portee derisoire : %d module(s)" % len(mods)
    echecs = []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        for mod, rc, err in ex.map(IP._essayer, mods):
            if rc != 0:
                echecs.append("  %s\n     %s" % (mod, err))
    assert not echecs, "\n".join(
        ["%d/%d module(s) d'engine/ ne s'importent pas EN PREMIER." % (len(echecs), len(mods)),
         "Un import HISSE a referme une boucle. Le graphe des sources declarees ne la voit "
         "pas forcement : Python execute les `__init__.py` ANCETRES quoi qu'on ecrive."]
        + echecs[:30])


def test_etage4_partition_exhaustive(sites):
    """La ventilation est une PARTITION : aucune forme ne peut se faire absorber en silence.

    Un recenseur qui n'enumere qu'une liste blanche de causes ne peut pas montrer celle qu'il a
    oubliee. La somme des categories syntaxiques DOIT valoir le total.
    """
    tc = [s for s in sites if s.cause_syn == "TYPE_CHECKING"]
    cond = [s for s in sites if s.cause_syn == "fonction" and s.conteneur]
    incond = [s for s in sites if s.cause_syn == "fonction" and not s.conteneur]
    assert len(tc) + len(cond) + len(incond) == len(sites), (
        "la ventilation n'est plus une partition : %d + %d + %d != %d"
        % (len(tc), len(cond), len(incond), len(sites)))
    # chaque categorie doit etre NON VIDE : une categorie vide ferait passer pour vert un
    # visiteur qui aurait cesse de la produire.
    assert tc and cond and incond, (
        "une categorie est VIDE (TYPE_CHECKING=%d, conditionnel=%d, inconditionnel=%d) : le "
        "visiteur a cesse d'en produire une, et le test serait vert a vide"
        % (len(tc), len(cond), len(incond)))
