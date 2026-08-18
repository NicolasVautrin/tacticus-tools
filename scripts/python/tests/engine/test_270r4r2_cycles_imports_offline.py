"""#270-r4-r2 -- CLIQUET : `engine/` n'a AUCUN cycle d'import module-level, et chaque module
s'importe EN PREMIER.

POURQUOI DEUX CRITERES, ET PAS UN. Ils ne voient pas la meme chose, et c'est mesure :

  * le GRAPHE (etage 1) modelise la SOURCE DECLAREE d'un import -- `from . import x` declare le
    PAQUET (il lit son attribut), `from .x import y` declare le MODULE. C'est actionnable : on
    peut le rendre acyclique, et c'est ce que la coupe a fait. Mais il est AVEUGLE aux cycles qui
    passent par un paquet ANCETRE, que Python execute quoi qu'on ecrive : `engine.dsl.base` ->
    `engine.entities` (init) -> ... -> `engine.dsl.base` n'y apparait PAS, et pourtant il casse.
  * l'IMPORT REEL (etage 3) les voit tous, mais ne dit pas OU est le cycle.

Un seul des deux laisserait passer une regression. Les deux se gardent mutuellement.

ETAGES
  1. 0 SCC > 1 dans le graphe module-level. Critere DERIVE (Tarjan sur le graphe reel), jamais
     une liste de noms : un cycle qui reapparait ailleurs rougit pareil.
  2. CONTRE-EPREUVE du detecteur : sur un graphe artificiellement cyclique il DOIT rougir. Sans
     elle, un Tarjan casse rendrait `0` pour toujours et l'etage 1 serait vert a vide.
  3. Chaque module des paquets touches s'importe EN PREMIER (interpreteur frais).
  4. TEMOIN : le balayage voit bien quelque chose (un zero de portee ne prouve rien).

100 % OFFLINE : aucun runner, aucune session Frida.
"""
from __future__ import annotations

#: CE QUI DOIT CHANGER POUR QUE CE FICHIER PUISSE CHANGER DE VERDICT -- et son ABSENCE etait la
#: CAUSE MESUREE de la decroissance silencieuse de l'etage 1 (#270-r4-r2, 2026-08-18).
#:
#: Ce cliquet lit `engine/**` PAR BALAYAGE DU DISQUE (`rglob`), pas par import : ni lui ni ses
#: deux probes n'importent quoi que ce soit d'`engine`. Sans declaration, `probe_457.
#: impacted_files` le selectionnait donc par le GRAPHE D'IMPORTS -- ou aucune arete ne le relie a
#: `engine/`. Resultat : AUCUN diff d'`engine/**` ne l'a jamais rejoue, et le
#: `probe_270r4r2_cycles_imports.py` n'est PAS non plus une entree de `scripts/ratchets.ps1`.
#: Le cliquet etait VERT a `1370d930` (SCC=0, 409 modules) et rendait 4 SCC / 721 modules quand
#: on l'a rejoue -- personne ne pouvait le voir entre les deux.
#:
#: Les cinq chemins hors `engine/` sont la fermeture d'imports DERIVEE
#: (`probe_486r15 --proposer`) ; la cascade de harnais, elle, est derivee par le foyer (#531),
#: donc absente d'ici a dessein.
DECLENCHEUR = {
    "chemins": (
        # LE GISEMENT : tout module d'`engine/` peut ajouter ou retirer une arete du graphe.
        # UNE SEULE forme, et c'est MESURE, pas suppose : `probe_486r15 --proposer` conseille
        # d'ecrire AUSSI `engine/*.py` (<< dans ce matcher, `**/` exige un segment >>), mais le
        # matcher reellement en jeu est `declencheur_cliquet.couvre`, que `probe_457` appelle
        # LUI AUSSI (l. 2383) -- et `**/` y vaut ZERO segment ou plus. Verifie : le glob
        # ci-dessous couvre `engine/battle_query.py` et `engine/__init__.py`. La seconde forme
        # ne serait donc qu'un `redondants` de plus.
        "scripts/python/engine/**/*.py",
        # LES DEUX PROBES et ce dont ils dependent.
        "scripts/python/probe_270r4r2_cycles_imports.py",
        "scripts/python/probe_270r4r2_import_en_premier.py",
        "scripts/python/import_closure.py",
        "scripts/python/verdict_cache.py",
        "scripts/cliquets-cache/probe_270r4r2_import_en_premier.tsv",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le critere est DERIVE du graphe d'imports de `engine/**` (SCC de Tarjan) et de "
              "l'import reel de chaque module ; il ne lit rien d'autre. Le balayage se fait par "
              "`rglob`, donc AUCUNE arete d'import ne relie ce fichier a `engine/` -- c'est "
              "precisement pourquoi le perimetre doit etre DECLARE ici et pas laisse au graphe. "
              "`build: False` : ni binaire ni `data/symbols/**`.",
}

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_270r4r2_cycles_imports as CY          # noqa: E402
import probe_270r4r2_import_en_premier as IP       # noqa: E402


@pytest.fixture(scope="module")
def graphe():
    return CY.construire(PYDIR / "engine")


def test_etage4_temoin_le_balayage_voit_quelque_chose(graphe):
    """TEMOIN d'abord : sans lui, les etages suivants pourraient etre verts SUR RIEN."""
    ml, tous, differes = graphe
    assert len(ml) >= 300, "portee derisoire : %d modules visites sous engine/" % len(ml)
    aretes = sum(len(v) for v in ml.values())
    assert aretes >= 1500, "graphe module-level derisoire : %d aretes" % aretes
    # le graphe TOUS IMPORTS doit etre strictement plus riche, sinon le visiteur ne distingue
    # plus module-level et differe -- et l'etage 1 mesurerait le mauvais graphe.
    assert sum(len(v) for v in tous.values()) > aretes, (
        "le graphe TOUS IMPORTS n'est pas plus dense que le module-level : le visiteur ne "
        "distingue plus les imports differes, l'etage 1 ne mesure plus ce qu'il annonce")
    assert sum(len(v) for v in differes.values()) > 0, "aucun import differe vu : visiteur casse"


def test_etage1_aucun_cycle_module_level(graphe):
    """CLIQUET. Critere DERIVE : composantes fortement connexes du graphe reel."""
    ml, _, _ = graphe
    cycles = CY._cycles(ml)
    assert cycles == [], "\n".join(
        ["%d cycle(s) d'import NIVEAU MODULE dans engine/ :" % len(cycles)]
        + ["  SCC de %d : %s" % (len(c), ", ".join(c)) for c in cycles]
        + ["Un enfant ne doit pas importer A TRAVERS son propre paquet "
           "(`from .frere import X`, jamais `from . import X` / `from engine.pkg import X`)."])


def test_etage2_contre_epreuve_le_detecteur_discrimine():
    """Le detecteur ROUGIT-il encore ? Un `_cycles` casse rendrait `[]` pour toujours."""
    acyclique = {"a": {"b"}, "b": {"c"}, "c": set()}
    assert CY._cycles(acyclique) == [], "faux positif sur un graphe acyclique"

    cyclique = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
    trouves = CY._cycles(cyclique)
    assert len(trouves) == 1 and set(trouves[0]) == {"a", "b", "c"}, (
        "le detecteur NE VOIT PAS un cycle de 3 : %r" % trouves)

    # forme exacte des deux SCC coupes par #270-r4-r2 : un paquet et ses enfants
    paquet = {"p": {"p.a", "p.b"}, "p.a": {"p"}, "p.b": {"p.a"}}
    trouves = CY._cycles(paquet)
    assert len(trouves) == 1 and set(trouves[0]) == {"p", "p.a", "p.b"}, (
        "le detecteur NE VOIT PAS la forme paquet<->enfants qui a ete coupee : %r" % trouves)

    boucle_sur_soi = {"a": {"a"}}
    assert CY._cycles(boucle_sur_soi), "le detecteur ne voit pas une boucle sur soi"


def test_etage3_chaque_module_s_importe_en_premier():
    """MESURE MATERIELLE, que l'etage 1 ne peut pas donner (cycles par paquet ancetre).

    Un cycle ne se voit que dans UN SENS : importer chaque module EN PREMIER, dans un
    interpreteur frais, est ce qui balaye tous les sens d'entree.
    """
    mods = IP._modules_sous(IP.PAQUETS_DEFAUT)
    assert len(mods) >= 100, "portee derisoire : %d modules" % len(mods)
    # `essayer_tous` (#486-r5) : MEME mesure, meme parallelisme, mais elle ne re-lance PAS un
    # interpreteur pour un module deja essaye sur le MEME etat de l'arbre. Les 201 modules d'ici
    # sont un SOUS-ENSEMBLE des 437 de `test_270r4r2r2_differes_offline.py` : dans une passe
    # complete, ces 44,1 s etaient payes deux fois.
    echecs = ["  %s\n     %s" % (mod, err)
              for mod, rc, err in IP.essayer_tous(mods) if rc != 0]
    assert not echecs, "\n".join(
        ["%d/%d module(s) ne s'importent pas EN PREMIER :" % (len(echecs), len(mods))] + echecs)
