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
#
# ⚠ RE-MESURES le 2026-08-07 (211 -> 224, 136 -> 139), et il faut dire POURQUOI, sinon relever un
# seuil a chaque rouge le vide de son sens. La montee court sur ~30 tranches de portage livrees
# depuis #485-r1-r1 -- environ 0,45 differe par tranche. Ce n'est PAS la reprise de MASSE que ce
# seuil surveille ; c'est de la derive unitaire, que seul un seuil jamais re-mesure transforme en
# rouge permanent. Mesure a l'appui (`probe_270r4r2r2_tri_differes.py --mesurer`), partition
# EXHAUSTIVE des 224 : 54 TYPE_CHECKING, 95 brise-cycle, 31 conditionnel, 16 placement -- et
# 28 HISSABLES.
#
# ⚠ RE-MESURES le 2026-08-10 (224 -> 290, 139 -> 193, #547-r2), MEME critere et meme obligation de
# motif. Ce qui a ete VERIFIE avant de relever, plutot que suppose :
#   * la DISPERSION. Diff site-a-site contre l'arbre de `22014f1c` (le commit qui a pose 224) :
#     +44 instructions reparties sur 23 modules, la plus grosse contribution etant les +9 d'un
#     module NEUF (`engine.runner.abilities.loki.attempted_possession`, #590). Aucun module ne
#     remonte le plafond a lui seul -> ce n'est pas la reprise de MASSE que ce seuil surveille.
#   * le DEBIT. 193 commits entre `22014f1c` et la mesure, soit ~0,23 differe par commit --
#     MOITIE du debit qui avait justifie le passage de 211 a 224. La derive ne s'accelere pas.
#   * la PARTITION EXHAUSTIVE des 265 (meme commande) : 57 TYPE_CHECKING, 105 brise-cycle,
#     38 conditionnel, 19 placement -- et 46 HISSABLES.
# Trois GRATUITS ont ete hisses dans la meme tranche (etage 1 remis a zero), en FORME B : le total
# passe de 268 a 265 AVANT la re-mesure du plafond, jamais l'inverse.
#
# ⚠⚠ ET LE PLAFOND PORTE DESORMAIS UNE MARGE DE 20, QUI EST ELLE AUSSI MESUREE. Un seuil pose A LA
# VALEUR COURANTE rougit au merge SUIVANT -- ce n'est pas une crainte, c'est ce qui vient de se
# passer trois fois : 211, puis 224, puis les 265 de cette tranche, devenus 270 en UN SEUL rebase
# (6 merges, quelques heures). Un cliquet qui accuse l'auteur suivant d'un gisement qu'il n'a pas
# creuse ne fait plus mesurer, il fait relever. La marge est donc bornee des DEUX cotes :
#   * assez GRANDE pour absorber la derive : 20 / 0,23 par commit = ~87 commits, l'ordre d'une
#     journee de cadence ;
#   * assez PETITE pour que le seuil garde son objet : les deux reprises de MASSE au dossier valent
#     625 (971 -> 346) et 122 (346 -> 224) instructions. 20 n'en masque aucune.
# Le nombre MESURE reste ecrit ci-dessus (270/173) : c'est lui qu'une tranche future doit
# re-mesurer et DESCENDRE, pas le plafond qu'elle doit remonter.
#
# ⚠⚠ CE SONT CES 46 QUI SONT LE GISEMENT, PAS LE TOTAL, et l'etage 1 ne peut pas les voir : son
# critere `gratuits()` est SYNTAXIQUE (« la cible est deja au preambule du MEME fichier ») et n'en
# retient AUCUN une fois la tranche passee. Le critere doctrinal, lui, est une MESURE (charger la
# cible seule en process frais). Le sweep des 46 (28 a l'epoque) est ouvert en RESIDU
# #270-r4-r2-r2-r4 : il touche autant de fichiers partages, et chaque site doit passer par
# `migrate_485r1_barils_reexport.py morsure` puis etre hisse en FORME B -- ce n'est pas un geste a
# glisser dans une tranche de reparation de cliquets.
#: MESURE le 2026-08-10 : 270 instructions, dont 173 inconditionnelles. Les plafonds portent la
#: marge de 20 justifiee ci-dessus -- ils ne SONT pas la mesure, ils la bornent.
MESURE_DIFFERES, MESURE_INCONDITIONNELS = 270, 173
PLAFOND_DIFFERES = MESURE_DIFFERES + 20
PLAFOND_INCONDITIONNELS = MESURE_INCONDITIONNELS + 20


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
    # `essayer_tous` (#486-r5) : MEME mesure, meme parallelisme, mais elle ne re-lance PAS un
    # interpreteur pour un module deja essaye sur le MEME etat de l'arbre -- et les 201 modules
    # de `test_270r4r2_cycles_imports_offline.py` sont un SOUS-ENSEMBLE de ces 437.
    echecs = ["  %s\n     %s" % (mod, err)
              for mod, rc, err in IP.essayer_tous(mods) if rc != 0]
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
