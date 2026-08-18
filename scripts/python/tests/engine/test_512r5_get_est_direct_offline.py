"""#512-r5 -- CLIQUET : `DSLFormulas$$Get(int)` et `$$Direct(int)` sont LE MEME corps.

Le port ecrit `Get(x) == Direct(x)` (`engine/entities/formulas.py::Get(Const)`, consomme par
`runner/abilities/necrons.py` pour le 9e argument de `ChainLeftOverHitsAttackDamage` de
`1006 MultiThreatEliminator`, et par `.../worldeaters.py` pour `1129 BloodyFury`). La fiche du
residu affirmait l'inverse ; la mesure la REFUTE.

CE QUE CE FICHIER GARDE, ET CE QU'IL NE PEUT PAS GARDER
--------------------------------------------------------
Il compare les EMPREINTES STRUCTURELLES des quatre methodes (`data/symbols/<build>/fingerprints/
functions.tsv`, VERSIONNE, donc jouable depuis n'importe quel worktree sans le jeu installe).
Un ecart de corps entre les deux le fait rougir.

Il ne TRANCHE PAS la question de fond, et c'est ecrit noir sur blanc par le generateur lui-meme
(`fingerprint_functions.py`, section << CE QUE L'EMPREINTE NE VOIT PAS >>) : une reference vers
une DONNEE -- le `mov rcx, [rip + X]` qui charge l'`Il2CppClass*` -- est reduite au jeton unique
`<X>`. DEUX CLASSES DIFFERENTES RENDRAIENT DONC LA MEME EMPREINTE, ce qui est exactement le faux
negatif que ce residu redoutait. La mesure qui tranche desassemble le PE et resout les cibles :
`probe_512r5_get_vs_direct.py --volet cibles` (le PE vit HORS du checkout, ce probe est donc
tri-etat et ne peut pas etre un test). Elle rend, sur `t6dpr4k06g` : memes 5 adresses decisives
(meme `Il2CppClass*`, meme allocateur, meme ctor), seuls les booleens
`s_Il2CppMethodInitialized` -- un octet d'amorcage, ni classe ni valeur -- different.

LE PIEGE DE RESOLUTION, ET IL A MORDU LA FICHE : `$$Get` porte TROIS surcharges que
`ghidra/functions.tsv` nomme identiquement (regime des noms multi-VA du build). Elles ne se
distinguent que par leur SIGNATURE. Ce fichier resout donc par signature -- et l'etage 1
assertionne qu'aucune signature n'est ambigue, sans quoi tout le reste porterait sur un corps
arbitraire.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                  # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_512r5_get_vs_direct as P                                        # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/probe_512r5_get_vs_direct.py",),
    "build": True,
    "toujours": False,
    "raison": "Le fichier lit `data/symbols/<build>/frida/methods.tsv` et "
              "`.../fingerprints/functions.tsv` : un changement de build doit le rejouer. Le "
              "port lui-meme (`engine/entities/formulas.py::Get`) n'est pas dans le "
              "declencheur -- ce fichier ne mesure PAS le port, il mesure le NATIF dont le port "
              "depend.",
}

BUILD = P.build_des_tables()


@pytest.fixture(scope="module")
def rvas():
    assert BUILD, "aucun dump `fingerprints/functions.tsv` sous `data/symbols/` -- rien a mesurer"
    return P.resoudre_rva(BUILD)


@pytest.fixture(scope="module")
def emp(rvas):
    return P.lire_empreintes(BUILD, rvas)


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- la RESOLUTION. Sans elle, tout le reste porte sur un corps arbitraire.
# --------------------------------------------------------------------------------------------
def test_etage1_les_quatre_signatures_resolvent_et_sont_distinctes(rvas):
    attendus = {c for c, _n, _p, _r in P.VISEES}
    assert set(rvas) == attendus, (
        "signatures introuvables dans `frida/methods.tsv` : %s" % sorted(attendus - set(rvas)))
    assert len(set(rvas.values())) == 4, (
        "deux signatures resolvent sur la MEME RVA : %s -- la resolution par signature ne "
        "discrimine plus" % rvas)


def test_etage1bis_les_trois_surcharges_de_Get_portent_bien_le_meme_nom(rvas):
    """Le piege que ce residu documente : `$$Get` est un nom multi-VA. Si le build cessait
    d'avoir trois surcharges homonymes, la mise en garde de la fiche deviendrait sans objet et
    il faudrait la relire -- pas la laisser se perimer en silence."""
    noms = {c: n for c, n, _p, _r in P.VISEES}
    gets = [c for c, n in noms.items() if n.endswith(".Get")]
    assert len(gets) == 3, "le build ne porte plus trois surcharges `$$Get` : %s" % gets
    assert len({rvas[c] for c in gets}) == 3


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- LE VERDICT : meme corps, sur les CINQ couches d'empreinte.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("colonne", ["taille", "n_ins", "h_local", "h_body", "h_mnem",
                                     "h_calls", "h_imm"])
def test_etage2_get_int_et_direct_int_ont_la_meme_empreinte(emp, colonne):
    a, b = emp["get_int"], emp["direct_int"]
    assert a is not None and b is not None, "empreinte absente pour l'une des deux methodes"
    assert a[colonne] == b[colonne], (
        "`DSLFormulas$$Get(amount:System.Int32)` et `$$Direct(amount:System.Int32)` divergent "
        "sur `%s` (%s != %s) -- le port qui les traite comme egaux devient FAUX. Rejouer "
        "`probe_512r5_get_vs_direct.py --volet cibles` avant toute conclusion."
        % (colonne, a[colonne], b[colonne]))


# --------------------------------------------------------------------------------------------
# ETAGE 3 -- TEMOINS NEGATIFS. Une colonne constante rendrait l'etage 2 vide.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("temoin", ["get_string", "get_edge"])
def test_etage3_les_deux_autres_surcharges_divergent(emp, temoin):
    a, t = emp["get_int"], emp[temoin]
    assert t["h_local"] != a["h_local"], (
        "le temoin negatif `%s` a le MEME `h_local` que `Get(int)` : la colonne ne discrimine "
        "rien et l'etage 2 ne prouve pas." % temoin)
    assert t["h_body"] != a["h_body"]


def test_etage3bis_les_temoins_ne_sont_pas_degeneres(emp):
    """Un `h_local` a `-` signale un corps ILLISIBLE (`_illisible`), pas un corps different :
    comparer deux `-` rendrait l'etage 3 vert sans rien mesurer."""
    for cle in ("get_int", "direct_int", "get_string", "get_edge"):
        assert emp[cle]["h_local"] != "-", (
            "corps illisible pour `%s` : les comparaisons d'empreinte sont vacantes" % cle)
        assert int(emp[cle]["n_ins"]) > 0
