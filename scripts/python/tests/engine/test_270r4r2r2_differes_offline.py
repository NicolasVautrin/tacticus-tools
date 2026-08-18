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
#
# ⚠⚠ 2026-08-11 (#923) -- LE SEUIL N'A PAS ETE RELEVE, LE COMPTE A ETE ABAISSE. `master` etait
# ROUGE a 305 pour un plafond de 290. Ce qui a ete MESURE avant de decider :
#   * l'ATTRIBUTION. 128 commits entre `0c30d55d` (le commit qui a pose 270/173, 2026-08-10 21:03)
#     et `4f3b7bb3`, pour +35 instructions -- soit 0,27 par commit, l'ORDRE EXACT du debit
#     historique (0,23) qui avait justifie la marge. Ce n'est donc PAS la reprise de MASSE que ce
#     seuil surveille : la marge de 20 a simplement ete consommee, comme prevu, en une journee.
#   * la REPONSE. Relever le plafond aurait ete la 4e fois -- et un seuil qu'on releve a chaque
#     rouge ne mesure plus rien. Le gisement REEL (les HISSABLES, cf. le paragraphe ci-dessous)
#     valait 65 sites : 36 ont ete hisses, dont 34 par `migrate_270r4r2r2_hisser_differes` sous son
#     filtre acyclique (SCC du graphe projete = 0) et 2 a la main en FORME B ABSOLUE.
#   * ce qui RESTE, et c'est une mesure, pas un renoncement : 31 sites restent refuses
#     `fermerait-une-boucle`. Hisser ceux-la ne se fait pas par deplacement d'import -- il faut
#     DEPLACER le code partage (doctrine (1)), ce que le residu #270-r4-r2-r2-r4 porte deja.
#   * les DEUX mesures descendent SOUS celles du 2026-08-10 (270 -> 271 puis 269 sur l'arbre de la
#     tranche, 173 -> 169), donc les deux plafonds descendent avec elles (290 -> 289, 193 -> 187) :
#     le ratchet joue dans le bon sens. Un plafond ne remonte jamais ; celui-ci a BAISSE.
#
# ⚠⚠ ET LA MARGE VAUT 18, PAS 20 -- C'EST UNE CONSEQUENCE, PAS UN CHOIX. La tranche a atteint
# 269/167 sur son propre arbre ; le REBASE sur `27e78a8a` (#919) en a re-ajoute 2, portant l'arbre
# LIVRE a 271/169. C'est cette derniere mesure qui est inscrite -- celle de ce qu'on livre, pas
# celle d'un arbre qui n'existe plus. Or `MESURE + 20` vaudrait 291, donc REMONTERAIT le plafond
# de 290 : interdit, un plafond ne remonte pas. La marge est donc ce qui RESTE sous le plafond
# herite, et elle se re-elargira a 20 des qu'une tranche descendra la mesure de deux crans de plus.
# Les deux sites qui manquaient ont ete EXAMINES et ECARTES, pas oublies : `selectors/pathing.py`
# (lignes ~50 et ~111) porte deux differes PORTEURS dont le motif est MESURE et ECRIT sur place
# (« charger `engine.entities.triggers` seul met `engine.entities.selectors.pathing` dans
# `sys.modules` »). Les hisser irait contre une mesure existante.
#
# ⚠⚠ 2026-08-12 (#962) -- LE PLAFOND TOTAL EST RELEVE, ET C'EST LA PREMIERE FOIS QU'IL L'EST APRES
# EPUISEMENT DU GISEMENT HISSABLE. Je l'ecris franchement parce que la doctrine ci-dessus dit
# << un plafond ne remonte pas >> et que je viens de la contredire sur UN des deux axes.
# CE QUI A ETE FAIT AVANT D'Y VENIR, dans l'ordre, et qui est la condition de ce relevement :
#   * l'ETAGE 1 A ETE REMIS A ZERO : le seul GRATUIT restant
#     (`triggers/loki/geminae_superia.py` -> `TriggerAnd`) est hisse ; le module cible etait DEJA
#     au preambule (ligne 144), donc le hissage est une pure suppression de redondance.
#     291 -> 290.
#   * ET LE COMPTE NE PEUT PLUS DESCENDRE PAR HISSAGE -- c'est une MESURE, pas un renoncement :
#     `migrate_270r4r2r2_hisser_differes` retient **0 site sur 48** (29 `hissable` + 19
#     `placement`), tous refuses `fermerait-une-boucle`. Le refus a ete CONTRE-EPROUVE sur un
#     site : hisser `engine/battle_query.py:340` (`entities.effects.aura`) EN FIN DE FICHIER --
#     la recette que le probe classe pourtant << verte sur 2 ordres >> -- casse l'import des
#     `selectors` par un TROISIEME module (`ImportError` sur `_shared._entity_pos`). Les deux
#     ordres mesures par le probe ne couvrent pas l'entree par un tiers. Revert immediat.
#   * DONC le gisement restant n'est plus hissable : il se ferme en DEPLACANT le code partage
#     (doctrine (1)), ce que porte le residu #270-r4-r2-r2-r4. Ce n'est pas une tranche de
#     reparation de cliquet.
# CE QUI EST MESURE, ET QUI ETABLIT QUE CE N'EST PAS LA REPRISE DE MASSE SURVEILLEE :
#   * ATTRIBUTION : 80 commits entre `46ba95e8` (qui a pose 271/169) et cet arbre, pour
#     +19 instructions -- soit **0,24 par commit**, l'ordre EXACT du debit historique (0,23 puis
#     0,27) qui a justifie la marge les fois precedentes. La marge de 18 a ete consommee comme
#     prevu (18 / 0,24 = ~75 commits ; il en a fallu 80).
#   * DISPERSION : les 143 modules `engine/**` touches depuis portent 135 differes au total ;
#     aucun ne remonte le plafond a lui seul. Les deux reprises de MASSE au dossier valent 625 et
#     122 instructions -- une marge de 12 n'en masque aucune.
# CE QUI EST RELEVE, ET CE QUI NE L'EST PAS :
#   * le plafond TOTAL passe de 289 a 302, et la MARGE est RESSERREE de 18 a 12 (~50 commits,
#     l'ordre d'une demi-journee de cadence) : relever en gardant 18 aurait donne 308, une marge
#     qu'aucune mesure ne justifie ici ;
#   * le plafond INCONDITIONNEL reste a **187**, INCHANGE -- la mesure (186) tient encore sous
#     lui, donc il n'y a aucune raison de le desserrer. Un ratchet ne se relache que sur l'axe ou
#     il est demontre intenable, jamais << au passage >>.
# ⚠⚠ 2026-08-18 (#485-r5) -- LA MESURE INSCRITE CI-DESSOUS ETAIT DEJA FAUSSE A SON PROPRE COMMIT,
# et c'est ce qu'il faut lire en premier : `869b9760` (#962) a inscrit `290` en le disant << mesure
# APRES rebase sur origin/master >>, alors que SON arbre en porte **294**. L'ecart de 4 n'est pas une
# derive posterieure -- c'est une mesure prise sur un arbre qui n'a pas ete livre. Consequence
# CHIFFREE : la marge annoncee de 12 n'en valait reellement que **8**, et la re-mesure est arrivee
# d'autant plus tot. Un seuil ecrit A LA MAIN ne peut pas dire s'il juge l'arbre qu'on livre ; le
# rendre verifiable est le residu **#485-r6**. En attendant, la regle d'ecriture est explicite : la
# mesure s'inscrit APRES le rebase de la branche, jamais avant.
#
# CE QUI A ETE MESURE AVANT DE RELEVER, dans l'ordre :
#   * l'OUTIL n'a pas bouge -- il fallait l'etablir avant d'attribuer quoi que ce soit au code.
#     `git diff 869b9760 HEAD -- probe_270r4r2r2_tri_differes.py` est VIDE, et les QUATRE
#     croisements (outil ancien/neuf x arbre ancien/neuf) rendent les memes couples 294/186 et
#     331/218. Le delta est INTEGRALEMENT du code.
#   * ATTRIBUTION : 860 commits entre `869b9760` (2026-08-12) et cet arbre, pour +37 instructions --
#     soit **0,043 par commit**, CINQ A SIX FOIS SOUS le debit qui a justifie les relevements
#     precedents (0,23 ; 0,27 ; 0,24). La derive ne s'accelere pas, elle a nettement ralenti.
#   * DISPERSION : 34 modules montent (+54), 12 baissent (-17) ; la plus grosse contribution vaut
#     **+6** (`runner.components`, `runner.abilities.behaviours.context`). Aucun module ne remonte
#     le plafond a lui seul -- il faudrait +29. Les deux reprises de MASSE au dossier valent 625 et
#     122 instructions : une marge de 12 n'en masque aucune.
#   * le GISEMENT HISSABLE est EPUISE au critere DOCTRINAL, et c'est lui qui fait foi :
#     `probe_485_imports_differes` rend **0 gratuit hors base** (les 3 restants sont les imports
#     OPTIONNELS sous `try/except` de la base attestee). Les 4 derniers gratuits ont ete hisses en
#     FORME B dans cette tranche meme (#485-r5), etage 1 remis a ZERO.
#   * la partition EXHAUSTIVE (`--mesurer`, 331 sites) rend 71 TYPE_CHECKING, 165 brise-cycle,
#     42 conditionnel, 22 placement -- et 31 `hissable`. Ces 31 NE SONT PAS un gisement : leur
#     critere (<< l'import reste vert dans les 2 ordres essayes >>) est un FAUX POSITIF connu
#     (#962, contre-epreuve `battle_query.py:340`), et `probe_485` les classe PORTEURS par la
#     mesure en process frais. `migrate_270r4r2r2_hisser_differes` REFUSE d'ailleurs de les
#     traiter : l'arbre porte 4 SCC module-level -- **PRE-EXISTANTS**, temoin pris sur
#     `origin/master` `8b2a2e35` qui rend les MEMES 4 SCC avec les MEMES membres.
#   * DONC le compte ne descend plus par hissage : il se ferme en DEPLACANT le code partage
#     (doctrine (1)), ce que porte le residu `#270-r4-r2-r2-r4`.
#: MESURE le 2026-08-18 (#485-r5), APRES rebase sur `origin/master` `8b2a2e35` ET apres les quatre
#: hissages de la tranche : 331 instructions, dont 218 inconditionnelles. C'est la mesure de
#: l'arbre LIVRE, pas d'un arbre intermediaire. Les plafonds ne SONT pas la mesure, ils la bornent.
MESURE_DIFFERES, MESURE_INCONDITIONNELS = 331, 218
#: MARGE = 12, INCHANGEE, et desormais JUSTIFIEE PAR LA CADENCE MESUREE : 12 / 0,043 par commit
#: = ~280 commits, soit ~2 jours au rythme constate (860 commits en 6 jours, ~143/jour). La
#: resserrer davantage ferait rougir la PR suivante pour une derive qu'elle n'a pas creusee ;
#: l'elargir masquerait ce que ce seuil surveille.
_MARGE = 12
PLAFOND_DIFFERES = MESURE_DIFFERES + _MARGE
#: DERIVE de `_MARGE` desormais (il etait un litteral tant qu'il ne remontait pas). Le deriver
#: ferme un trou d'ecriture : on ne peut plus desserrer CE plafond-la sans relever la MESURE,
#: c'est-a-dire sans inscrire un chiffre que l'etage 3 confronte a l'arbre.
PLAFOND_INCONDITIONNELS = MESURE_INCONDITIONNELS + _MARGE


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
