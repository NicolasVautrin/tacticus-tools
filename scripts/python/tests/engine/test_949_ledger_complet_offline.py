"""#949 -- GARDES du LEDGER COMPLET et de l'ORDRE PAR FACE.

Deux vices distincts, tous deux mesures par #949, et tous deux INVISIBLES a un test de valeur seul :

  1. **LE LECTEUR.** `damage_ops/normal.py::execute` publie la phase d'ARME dans `per_hit` et les
     coups du canal #179 A COTE, dans `additional_hits` -- deux sous-operations natives distinctes,
     donc deux cles. Un lecteur qui compare le ledger NATIF (un flux d'events UNIQUE) au seul
     `per_hit` fabrique un ecart de coups des que l'attaquant porte un descripteur #179 ACTIF.
     C'est exactement ce qui a fait ecrire << 8 coups natif contre 6 port >> au Sec.6 de
     `docs/rl/case-947-948-passifs-extra-damage.md` : le port etait bit-exact
     (`hp_delta` == somme des coups natifs), l'ecart n'existait QUE dans le lecteur.

  2. **L'ORDRE PAR FACE.** `apply_pierce_and_modifiers` doit consommer ses quatre conteneurs de
     modificateurs GROUPES PAR FACE (attaquant puis defenseur), parce que le natif CLOT la face
     attaquant (`CalculateBaseDamageWithModifiers`, etape 3, INCONDITIONNELLE) avant d'ouvrir la
     face defenseur (etape 4). La valeur est gardee par
     `test_446_r2_inter_face_rounding_offline.py::test_effet_defenseur_reel_materialise_la_face_attaquant`
     (temoin natif 443) ; ce fichier-ci garde la FORME, qui rougit meme si un futur regime rendait
     le temoin de valeur non discriminant.

ASCII only.
"""
from __future__ import annotations

import ast
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(os.path.dirname(_HERE))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

_NORMAL = os.path.join(_PY, "engine", "runner", "operations", "damage_ops", "normal.py")
_PIERCE = os.path.join(_PY, "engine", "services", "damage_prediction.py")

#: Les lecteurs de la famille qui CONFRONTENT un ledger natif a un rejeu offline. Perimetre
#: VOLONTAIREMENT etroit et NOMME : c'est un cliquet sur les deux probes que #949 a corriges, pas un
#: balayage du corpus. Le balayage des ~100 sites `damage_handler.last` est le residu **#949-r1**.
_LECTEURS = ("probe_947_948_extra_damage_passives.py", "probe_949_ltgb_coup_manquant.py")


def _src(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_le_retour_de_execute_separe_les_deux_canaux():
    """ETAGE 1a -- LE CONTRAT. `normal.py::execute` doit publier `additional_hits` comme cle PROPRE,
    et `per_hit` doit rester la phase d'ARME (`r["per_hit"]`). Si un jour les deux fusionnent, ce
    test rougit -- et c'est voulu : les lecteurs ci-dessous recollent, donc ils compteraient double.
    """
    tree = ast.parse(_src(_NORMAL))
    dicts = [n for n in ast.walk(tree) if isinstance(n, ast.Dict)]
    cibles = [d for d in dicts
              if any(isinstance(k, ast.Constant) and k.value == "additional_hits" for k in d.keys)]
    assert cibles, ("aucun dict de `normal.py` ne publie la cle `additional_hits` -- le canal #179 "
                    "n'est plus observable separement, tout lecteur de ledger est aveugle")
    d = cibles[0]
    cles = {k.value for k in d.keys if isinstance(k, ast.Constant)}
    assert "per_hit" in cles, "le meme dict doit publier `per_hit` (la phase d'ARME)"
    idx = [i for i, k in enumerate(d.keys)
           if isinstance(k, ast.Constant) and k.value == "per_hit"][0]
    val = d.values[idx]
    # `per_hit` = `r["per_hit"]` : la phase d'arme SEULE, pas une concatenation
    assert isinstance(val, ast.Subscript), (
        "`per_hit` n'est plus un simple `r[...]` : si la valeur agrege desormais les coups "
        "additionnels, les lecteurs qui recollent compteraient DEUX FOIS le canal #179")


def test_les_lecteurs_recollent_les_deux_canaux():
    """ETAGE 1b -- LES LECTEURS. Chacun des deux probes de la famille doit LIRE `additional_hits`.
    Cliquet de FORME assume : il ne verifie pas la valeur recollee (aucune capture n'est versionnee),
    il verifie qu'on n'est pas REVENU a ne lire que la phase d'arme -- la regression exacte qui a
    produit le faux ecart de #949."""
    manquants = []
    for nom in _LECTEURS:
        chemin = os.path.join(_PY, nom)
        assert os.path.exists(chemin), "lecteur introuvable : %s" % nom
        if "additional_hits" not in _src(chemin):
            manquants.append(nom)
    assert not manquants, (
        "ces lecteurs comparent un ledger natif sans lire le canal #179 (`additional_hits`) : %s "
        "-- ils sous-comptent les coups des que l'attaquant porte un descripteur #179 actif"
        % (manquants,))


def test_les_quatre_conteneurs_sont_groupes_par_face():
    """ETAGE 2 -- L'ORDRE. Dans la branche `attacker_additive_pre` d'`apply_pierce_and_modifiers`,
    les quatre consommations doivent apparaitre dans l'ordre FACE ATTAQUANTE (`pct_list` puis
    `multiplicative`) PUIS FACE DEFENSEUR (`pct_list_defender` puis `multiplicative_defender`).

    L'ordre `(pct, pct_defender, mult, mult_defender)` -- celui d'avant #949 -- applique le
    multiplicateur de la face ATTAQUANTE APRES le %-effet de la face DEFENSEUR, donc la face
    defenseur travaille sur la sortie FRACTIONNAIRE du percage au lieu de la valeur materialisee.
    Mesure : percage 884.8 x 0.50 -> 442 au lieu de 443 (natif). Cf.
    `test_446_r2_inter_face_rounding_offline.py` pour le temoin de VALEUR."""
    tree = ast.parse(_src(_PIERCE))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "apply_pierce_and_modifiers")
    attendus = ["pct_list", "multiplicative", "pct_list_defender", "multiplicative_defender"]
    vus = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and node.attr in attendus:
            vus.append((node.lineno, node.col_offset, node.attr))
    # `pct_list` est un PREFIXE de `pct_list_defender` cote texte, mais pas cote AST : l'attribut
    # est distinct, donc l'ordre se lit sans ambiguite.
    ordre = [a for _l, _c, a in sorted(vus)]
    premiers = []
    for a in ordre:
        if a not in premiers:
            premiers.append(a)
    assert premiers == attendus, (
        "les quatre conteneurs de modificateurs ne sont plus groupes PAR FACE dans "
        "`apply_pierce_and_modifiers` : ordre lu %s, attendu %s. L'ordre historique "
        "(pct, pct_defender, mult, mult_defender) fait travailler la face DEFENSEUR sur la sortie "
        "fractionnaire du percage -> -1 par coup (mesure #949 : 442 au lieu de 443)"
        % (premiers, attendus))
