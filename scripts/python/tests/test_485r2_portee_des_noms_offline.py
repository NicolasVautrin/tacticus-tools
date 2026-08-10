"""#485-r2 -- la resolution d'un `<nom>.<attr>` se fait DANS SA PORTEE, pas a plat sur le fichier.

LE DEFAUT REPARE, MESURE SUR `master` LE 2026-08-10
---------------------------------------------------
`probe_485r1r1_acces_attributaires` rendait `rc=1` en accusant
`engine.utilities.sworn_protector.evaluate` -- 5 acces, tous dans
`tests/engine/runner/test_120bis_spawn_tile_offline.py`. FAUX : ce fichier lie le nom `F` DEUX
fois, dans deux fonctions differentes --

    ligne 108 : import engine.utilities.sworn_protector as F                      (un MODULE)
    ligne 182 : from engine.utilities.sworn_protector import SWORN_..._ENEMIES as F  (un OBJET)

-- et `migrate_485r1_barils_reexport._table_modules` construit une table PLATE du fichier : la
liaison de module de la ligne 108 etait attribuee aux sites des lignes 182-208, ou `F` designe
une FEUILLE de scoring, qui expose bien `.evaluate`. Le cliquet accusait donc un
`AttributeError` qui ne peut pas se produire.

⚠ POURQUOI CA COMPTE PLUS QUE LES 5 ACCES : un cliquet qui accuse a tort se fait desarmer, et il
masque alors les VRAIS. C'est le seul mode de defaillance qui coute plus cher que l'absence de
cliquet.

CE QUE CE FICHIER GARDE
-----------------------
Le resolveur `migrate_485r1_barils_reexport.ResolveurDeModules`, dans les DEUX sens :

  * il ne doit plus attribuer un module a un nom qu'une portee plus proche lie a un OBJET ;
  * il doit continuer de MORDRE sur le gisement d'origine (#485-r1-r1) -- un acces attributaire
    vers un symbole que le module n'expose pas ;
  * il doit rester TRANSPARENT sur ce que le langage ne tranche pas (un nom recu en PARAMETRE),
    sans quoi la reparation retirerait 7 acces VRAIS du recensement (mesure du 2026-08-10).

Chaque cas porte son TEMOIN NON NUL : la table PLATE est confrontee au resolveur, et le test
exige que les deux DIVERGENT la ou la reparation porte. Sans ce temoin, un resolveur qui rendrait
`None` partout passerait tous les cas negatifs.

100 % offline, aucune ecriture. ASCII only (cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: DECLARE LARGE, et par MESURE : les deux etages qui portent sur l'arbre REEL lisent le fichier
#: de test accuse, et toute la resolution passe par `existe_module`, qui interroge le DISQUE sous
#: `scripts/python/engine/**` (un module renomme change le verdict). Les deux formes de glob sont
#: necessaires -- `**/` exige un segment, donc `engine/**/*.py` seul raterait `engine/*.py`.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/migrate_485r1_barils_reexport.py",
        "scripts/python/probe_485r1r1_acces_attributaires.py",
        "scripts/python/tests/engine/runner/test_120bis_spawn_tile_offline.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le foyer du resolveur, le cliquet qui le consomme, le fichier de test dont le "
              "faux positif a ete mesure, et l'arbre `engine/**` que `existe_module` interroge "
              "pour decider si un nom importe designe un module.",
    # LE BYPASS (#486-r24), a la place d'un `scripts/python/**/*.py` qui retiendrait ce fichier a
    # CHAQUE PR Python. Ce qu'il LIT n'est pas ce dont son verdict DEPEND : l'etage de bout en
    # bout appelle `P.recenser()`, qui visite TOUT `.py` de `scripts/python/**` -- c'est
    # l'ANTI-VACUITE de ce cas (un recensement maigre rendrait le vert creux), donc aucune
    # enumeration ne peut le borner. Mesure du 2026-08-10 : 17 chemins hors perimetre declare,
    # tous ouverts par ce balayage.
    "hors_confrontation":
        "Son etage de bout en bout BALAIE scripts/python/** : `probe_485r1r1.recenser()` "
        "`ast.parse` chaque `.py` de l'arbre, et l'anti-vacuite du cas EXIGE le perimetre reel "
        "(un recensement maigre rendrait le vert creux). La confrontation voit donc 17 chemins "
        "hors perimetre declare -- des probes, `data/seed-bc.json` et des helpers -- qu'aucune "
        "enumeration ne peut borner sans desarmer le cas.",
}

import ast
import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import migrate_485r1_barils_reexport as MIG          # noqa: E402
import probe_485r1r1_acces_attributaires as P        # noqa: E402


def _resoudre(source: str, attr: str, nom: str):
    """`(par la table PLATE, par le RESOLVEUR)` pour le site `<nom>.<attr>` du temoin.

    Le site est designe par son ATTRIBUT et non par un NUMERO DE LIGNE : un temoin dont on
    ajoute une ligne ferait alors echouer le test sur une cause qui n'est pas la sienne (vecu a
    l'ecriture de ce fichier). Les attributs des temoins sont uniques par construction.

    Rendre les DEUX est le point : un test qui n'observerait que le resolveur ne pourrait pas
    montrer que la reparation MORD -- il passerait aussi bien avec l'ancien code s'il se trouvait
    que le cas soit deja correct."""
    arbre = ast.parse(source)
    plat = MIG._table_modules(arbre, "scripts_temoin", _PYDIR)
    resolveur = MIG.ResolveurDeModules(arbre, "scripts_temoin", _PYDIR)
    for n in ast.walk(arbre):
        if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id == nom and n.attr == attr):
            return plat.get(nom), resolveur.resoudre(nom, n.value)
    raise AssertionError("aucun acces `%s.%s` dans le temoin" % (nom, attr))


# ---------------------------------------------------------------------------------------------
# 1. LE FAUX POSITIF, SUR UN TEMOIN SYNTHETIQUE QUI REPRODUIT LE PATRON MESURE
# ---------------------------------------------------------------------------------------------

#: Le patron EXACT du fichier accuse : deux fonctions, deux liaisons du meme nom local `F`.
#: Les modules cites existent reellement -- `existe_module` interroge le disque, donc un temoin
#: a modules imaginaires ne prouverait rien du chemin qui compte.
_TEMOIN_DEUX_LIAISONS = """
def un():
    import engine.utilities.sworn_protector as F
    return F.SWORN_PROTECTOR_AVOID_ADJACENT_ENEMIES


def deux():
    from engine.utilities.sworn_protector import SWORN_PROTECTOR_AVOID_ADJACENT_ENEMIES as F
    return F.evaluate(None, {}, {}, None)
"""


def test_un_nom_relie_a_un_OBJET_dans_SA_portee_ne_designe_plus_le_module():
    plat, resolu = _resoudre(_TEMOIN_DEUX_LIAISONS, "evaluate", "F")
    assert plat == "engine.utilities.sworn_protector", \
        "TEMOIN NON NUL : sans lui ce cas ne prouverait rien -- la table PLATE DOIT se tromper ici"
    assert resolu is None, \
        "`F` est lie a une FEUILLE dans cette portee : le resolveur ne doit y voir aucun module"


def test_le_MEME_nom_designe_bien_le_module_dans_la_portee_qui_l_importe():
    """Contre-epreuve du precedent : la reparation ne doit pas eteindre le cas legitime."""
    _plat, resolu = _resoudre(_TEMOIN_DEUX_LIAISONS, "SWORN_PROTECTOR_AVOID_ADJACENT_ENEMIES", "F")
    assert resolu == "engine.utilities.sworn_protector", \
        "dans la portee qui fait `import ... as F`, `F` EST le module"


def test_sur_le_FICHIER_REEL_les_cinq_acces_accuses_ne_sont_plus_recenses():
    """L'etage qui porte sur l'arbre : le rouge mesure de `master`, sur son fichier reel.

    Il ANCRE sa mesure sur le contenu present et non sur des numeros de ligne : ce qui est
    exige, c'est qu'aucun acces `F.evaluate` de ce fichier ne soit attribue au MODULE."""
    cible = _PYDIR / "tests" / "engine" / "runner" / "test_120bis_spawn_tile_offline.py"
    arbre = ast.parse(cible.read_text(encoding="utf-8"))
    mod = MIG.nom_module(cible, _PYDIR)
    plat = MIG._table_modules(arbre, mod, _PYDIR)
    resolveur = MIG.ResolveurDeModules(arbre, mod, _PYDIR)
    sites = [n for n in ast.walk(arbre)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
             and n.value.id == "F" and n.attr == "evaluate"]
    assert len(sites) >= 5, \
        ("TEMOIN NON NUL : le fichier accuse doit encore porter ses acces `F.evaluate` -- s'ils "
         "ont disparu, ce test ne garde plus rien (vu %d)" % len(sites))
    assert plat.get("F") == "engine.utilities.sworn_protector", \
        "TEMOIN NON NUL : c'est bien la table PLATE qui produisait l'accusation"
    for n in sites:
        assert resolveur.resoudre("F", n.value) is None, \
            ("ligne %d : `F` y designe la FEUILLE importee, pas le module" % n.lineno)


# ---------------------------------------------------------------------------------------------
# 2. LE CLIQUET MORD TOUJOURS -- la reparation ne doit rien eteindre
# ---------------------------------------------------------------------------------------------

#: Le gisement d'ORIGINE de #485-r1-r1 : un baril lie comme MODULE, puis un attribut qu'il
#: n'expose pas. C'est ce que le cliquet existe pour voir.
_TEMOIN_ACCES_MANQUANT = """
from engine.playbook import noncomparable as NC


def lire():
    return NC.CE_SYMBOLE_N_EXISTE_PAS
"""


def test_le_gisement_d_ORIGINE_reste_recense():
    _plat, resolu = _resoudre(_TEMOIN_ACCES_MANQUANT, "CE_SYMBOLE_N_EXISTE_PAS", "NC")
    assert resolu == "engine.playbook.noncomparable", \
        "un baril importe comme MODULE doit rester resolu -- sinon le cliquet ne voit plus rien"
    manquants, _sous, muets = P.confronter([(resolu, "CE_SYMBOLE_N_EXISTE_PAS", "temoin:6")])
    assert not muets, "le module temoin doit etre importable : %s" % muets
    assert manquants, "le cliquet DOIT signaler un attribut que le module n'expose pas"


@pytest.mark.parametrize("masque,attendu", [
    ("from engine.playbook.noncomparable import NATIVE_PRIORITY as NC", None),
    ("def NC():\n        pass", None),
    ("", "engine.playbook.noncomparable"),
])
def test_seules_les_liaisons_CONNUES_non_module_masquent(masque, attendu):
    """Le tri-etat, exerce : `objet importe` et `def` MASQUENT ; rien du tout ne masque pas."""
    src = ("from engine.playbook import noncomparable as NC\n\n\n"
           "def lire():\n    %s\n    return NC.NATIVE_PRIORITY\n"
           % (masque or "pass"))
    _plat, resolu = _resoudre(src, "NATIVE_PRIORITY", "NC")
    assert resolu == attendu


def test_un_nom_recu_en_PARAMETRE_reste_TRANSPARENT():
    """Ce que le langage ne tranche pas, le resolveur ne le tranche pas non plus.

    Mesure du 2026-08-10 : rendre le parametre OPAQUE retirait 7 acces VRAIS du recensement --
    `EF` dans `probe_124_line_elevation_decision`, `ar` dans
    `probe_433_r4_r2_r1_r1_dynamic_target_gate`, `adj` dans `probe_419r1tr10r2_multi_tuiles_canal`
    -- tous du meme patron : un module importe ailleurs, passe en argument sous le meme nom."""
    src = ("from engine.playbook import noncomparable as NC\n\n\n"
           "def diag(x, NC):\n    return NC.NATIVE_PRIORITY\n")
    _plat, resolu = _resoudre(src, "NATIVE_PRIORITY", "NC")
    assert resolu == "engine.playbook.noncomparable", \
        "un parametre homonyme n'est pas une preuve que ce n'est pas le module"


def test_un_import_dans_une_AUTRE_fonction_reste_atteignable_en_dernier_recours():
    """Le RECOURS a la table plate : `EF` n'est lie nulle part dans la portee du site, et le seul
    endroit qui le lie est une AUTRE fonction. Sans recours, l'acces disparaitrait du
    recensement."""
    src = ("def a():\n"
           "    import engine.playbook.noncomparable as EF\n"
           "    return EF\n\n\n"
           "def b(EF):\n"
           "    return EF.NATIVE_PRIORITY\n")
    _plat, resolu = _resoudre(src, "NATIVE_PRIORITY", "EF")
    assert resolu == "engine.playbook.noncomparable"


# ---------------------------------------------------------------------------------------------
# 3. LE CLIQUET LUI-MEME
# ---------------------------------------------------------------------------------------------

def test_le_probe_est_VERT_sur_l_arbre_et_son_recensement_est_NON_VIDE():
    """Le verdict de bout en bout. L'ANTI-VACUITE est ce qui l'empeche d'etre un vert creux :
    un recensement vide rendrait deja `PAS MESURE`, mais un recensement MAIGRE passerait."""
    lectures, ecritures = P.recenser()
    assert len(lectures) > 1000, \
        "recensement anormalement maigre (%d lectures) -- le vert ne prouverait rien" % len(lectures)
    manquants, _sous, muets = P.confronter(lectures)
    assert not muets, "modules non importables -- la confrontation n'a pas eu lieu : %s" % muets
    assert not manquants, (
        "acces attributaires manquants : %s"
        % sorted({"%s.%s" % (c, a) for c, a, _s in manquants})[:5])
    assert ecritures, "TEMOIN NON NUL : le recensement des ECRITURES ne doit pas etre vide"
