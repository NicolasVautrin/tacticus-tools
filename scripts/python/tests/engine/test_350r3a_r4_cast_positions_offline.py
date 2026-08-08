"""#350-r3a-r4 -- CLIQUET : aucun gate de POSITION ne lit `ranked` brut.

CE QUE LA TRONCATURE COUTE, MESURE (`case-350r3-oracle-noncomparable.md` §9) :
`computeAttackPlans` plafonne (`for (let r = 0; r < maxRank; r++)`), plafond ABSENT du natif. A
`maxRank = 6` -- le defaut du RPC `decisionView`, donc le regime de PRODUCTION -- **21 positions
sur 33** disparaissent du plan, et l'argmax se DEPLACE (natif `(1,3)`, port `(0,3)`).

POURQUOI LE CLIQUET PORTE SUR LA STRUCTURE ET PAS SEULEMENT SUR UNE VALEUR. Le residu recensait
<< 6 sites lisent `ranked` >>, ce qui est le mauvais axe : ce n'est pas le SITE qui decide mais la
SOURCE du plan (face DECISION = tronquee, face COMBAT = complete). Un septieme lecteur naitrait
expose sans qu'aucun test de valeur ne bouge. L'etage 3 balaie donc les gates de position par AST.

100 % OFFLINE : aucun runner, aucune session Frida.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.ai import cast_positions as CP                              # noqa: E402


def _ev(positions, complete=None):
    ev = {"abilityId": 69, "targetId": 77,
          "ranked": [{"col": c, "row": r} for (c, r) in positions],
          "rankCount": len(positions)}
    if complete is not None:
        ev[CP.RANK_COMPLETE] = complete
    return ev


def _cft(tiles, current_valid=False):
    def f(_uid, _tid, _ab):
        return {"currentValid": current_valid,
                "moveTiles": [{"col": c, "row": r} for (c, r) in tiles]}
    return f


# ────────────────────────────────────── etage 1 : le TRI-ETAT du foyer

def test_plan_declare_COMPLET_ne_coute_aucun_rpc():
    """Face COMBAT (`state_bridge`) : l'enumeration est exhaustive, donc `ranked` EST la reponse.
    Un `castFromTiles` y serait un RPC pur perte -- et le montage le prouve en rendant un ensemble
    DIFFERENT : s'il etait consulte, le resultat le montrerait."""
    appels = []

    def piege(*a):
        appels.append(a)
        return {"currentValid": True, "moveTiles": [{"col": 9, "row": 9}]}

    out = CP.positions_castables(_ev([(1, 3), (2, 4)], complete=True), piege, 5, 77, 69, (0, 0))
    assert out == {(1, 3), (2, 4)}
    assert appels == [], "un plan declare COMPLET ne doit consulter aucune seam"


def test_plan_declare_TRONQUE_va_chercher_les_positions_manquantes():
    """LE CRAN. `ranked` porte 2 positions, le predicat natif en a 4 : sans le foyer, les deux
    autres sont refusees par `tile not in legal[tgt]` alors que le natif y autorise l'attaque."""
    out = CP.positions_castables(_ev([(1, 3), (2, 4)], complete=False),
                                 _cft([(1, 3), (2, 4), (5, 5), (6, 6)]), 5, 77, 69, (0, 0))
    assert out == {(1, 3), (2, 4), (5, 5), (6, 6)}


def test_drapeau_ABSENT_vaut_PAS_MESURE_et_JAMAIS_complet():
    """Le bundle courant ne publie pas encore `rankComplete`. Rabattre l'absence sur << complet >>
    serait exactement la degradation permissive que la tranche ferme : ni erreur, ni crash, et le
    gate refuse des attaques que le natif autorise."""
    out = CP.positions_castables(_ev([(1, 3)]), _cft([(1, 3), (7, 7)]), 5, 77, 69, None)
    assert out == {(1, 3), (7, 7)}, "un drapeau absent doit declencher la mesure, pas la supposer"


def test_l_origine_entre_seulement_si_currentValid():
    out_sans = CP.positions_castables(_ev([(1, 3)]), _cft([(4, 4)], current_valid=False),
                                      5, 77, 69, (0, 0))
    out_avec = CP.positions_castables(_ev([(1, 3)]), _cft([(4, 4)], current_valid=True),
                                      5, 77, 69, (0, 0))
    assert out_sans == {(4, 4)}
    assert out_avec == {(4, 4), (0, 0)}


# ────────────────────────────────────── etage 2 : les TROIS replis sont NOMMES

@pytest.mark.parametrize("seam,libelle", [
    (None, "seam absente"),
    ("boum", "seam qui leve"),
    ("vide", "seam qui rend un ensemble VIDE"),
])
def test_les_replis_rendent_ranked_jamais_un_ensemble_vide(seam, libelle):
    """Rendre `set()` ferait DISPARAITRE la cible -- pire que la troncature, parce que la
    troncature laisse au moins les positions qu'elle a vues."""
    if seam == "boum":
        def fn(*_a):
            raise RuntimeError("rpc casse")
    elif seam == "vide":
        def fn(*_a):
            return {"currentValid": False, "moveTiles": []}
    else:
        fn = None
    avant = dict(CP.COMPTEURS)
    out = CP.positions_castables(_ev([(1, 3), (2, 4)]), fn, 5, 77, 69, (0, 0))
    assert out == {(1, 3), (2, 4)}, libelle
    assert CP.COMPTEURS["repli"] == avant["repli"] + 1, (
        "le repli doit etre COMPTE, sinon il est silencieux (%s)" % libelle)


def test_plan_est_complet_prend_le_membre_le_plus_faible():
    """Un SEUL eval tronque suffit a deplacer un argmax : l'agregat ne peut pas etre plus
    optimiste que son membre le plus faible."""
    assert CP.plan_est_complet({"evals": [_ev([(1, 1)], True), _ev([(2, 2)], True)]}) is True
    assert CP.plan_est_complet({"evals": [_ev([(1, 1)], True), _ev([(2, 2)], False)]}) is False
    assert CP.plan_est_complet({"evals": [_ev([(1, 1)], True), _ev([(2, 2)])]}) is None
    assert CP.plan_est_complet({"evals": []}) is None


# ────────────────────── etage 3 : AUCUN gate de position ne lit `ranked` brut

#: Les gates de POSITION, c.-a-d. les sites qui decident << cette attaque est-elle legale DEPUIS
#: cette tuile ? >>. Ils doivent tous passer par le foyer. Les deux gates de DEGAT
#: (`hammer_of_wrath`, `holy_duel`) n'y sont PAS : ils lisent `dmgMin` / `kill`, que
#: `castFromTiles` ne porte pas -- ils sont declares exposes et documentes, pas gardes ici.
GATES_DE_POSITION = [
    ("engine/ai/action_generators.py", "_best_attack"),
    ("engine/playbook/noncomparable/_base.py", "_get_num_attack_targets_in_position"),
    ("engine/playbook/loki_custom.py", "_get_target"),
]


def _fonction(chemin: Path, nom: str):
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    return None


@pytest.mark.parametrize("rel,fn_nom", GATES_DE_POSITION)
def test_un_gate_de_position_passe_par_le_foyer(rel, fn_nom):
    """GARDE STRUCTURELLE. Un septieme lecteur de `ranked` naitrait expose sans qu'aucun test de
    VALEUR ne bouge -- c'est ainsi que six sites ont survecu au fix de `#350-r3a-r3`."""
    chemin = PYDIR / rel
    fn = _fonction(chemin, fn_nom)
    assert fn is not None, "%s::%s introuvable (renomme ?)" % (rel, fn_nom)
    appels = {n.func.attr for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "positions_castables" in appels, (
        "%s::%s doit passer par `engine.ai.cast_positions.positions_castables` "
        "(gate de POSITION lisant `ranked` brut = expose au plafond `maxRank`)" % (rel, fn_nom))


def test_le_bridge_OFFLINE_declare_ses_plans_complets():
    """Sans ce drapeau, la face COMBAT paierait un `castFromTiles` par paire -- ou, pire, on
    serait tente de rabattre l'absence sur << complet >> pour l'eviter."""
    import engine.ai.state_bridge as SB
    src = (PYDIR / "engine/ai/state_bridge.py").read_text(encoding="utf-8")
    assert '"rankComplete": True' in src, (
        "`_plans_for_unit` doit DECLARER ses evals complets")
    assert hasattr(SB, "_plans_for_unit")


def test_le_harnais_publie_le_drapeau():
    """Le correctif `projection.ts` est LIVRE mais exige une REINJECTION pour etre actif. Ce test
    garde qu'il n'est pas perdu au prochain rebase -- et le port, lui, tient sans lui (le drapeau
    absent = regime PAS MESURE, cf. etage 1)."""
    ts = PYDIR.parents[1] / "frida/hooks/features/ai-step/projection.ts"
    src = ts.read_text(encoding="utf-8")
    assert "rankComplete" in src, "`projection.ts` ne publie plus le drapeau"
    assert "let rankComplete = false" in src, (
        "le drapeau doit etre FAUX par defaut : un defaut a `true` ferait taire le plafond")
