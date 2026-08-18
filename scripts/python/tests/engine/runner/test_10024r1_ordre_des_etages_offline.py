"""#10024-r1 -- CLIQUET : le slot 2 BRANCHE d'abord, il ne lit une position que dans `Normal(3)`.

Ce que ce fichier garde, et qu'aucun autre ne gardait : l'ORDRE DES ETAGES d'`is_melee_attack`.
`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` (build `t6dpr4k06g`), LU :

    if (!ability.HasValue) return false;
    switch (GetAbilityAttackRangeType(ability)) {
      case 0 (None):   return false;                      // AUCUNE position lue
      case 1 (Melee):  return true;                       // AUCUNE position lue
      case 2 (Ranged): return false;                      // AUCUNE position lue
      case 3 (Normal): return !UnitExtensions$$HasFlag(caster, 0x15)   // UnitFlag.ForceRangedAttack
                              && AreEntitiesAdjacent(casterPosition, target);
      default: throw new NotImplementedException();
    }

Le port ouvrait son corps par `if caster_position is None or target_position is None: return False`,
donc les TROIS cases sans position etaient rabattues sur `false`. Sur `Melee(1)` c'est une
divergence FRANCHE (`true` natif contre `false` porte), et elle est RESTRICTIVE-EN-MOINS : ni
erreur, ni trace. Ses DEUX freres -- `is_ranged_attack` (slot 3) et `get_attack_range_type`
(slot 4) -- portaient deja le bon ordre : l'asymetrie etait dans le port SEUL.

REGIME re-derive du gameconfig du build (etage 0, assertionne NON VIDE) : 572 abilities indexees,
dont 71 `Melee`, 85 `Ranged`, 10 `Normal` et 406 sans entree `attackRangeType` (ces dernieres
retombent sur la branche `Normal(3)`, cf. la docstring d'`attack_range_type`). AUCUNE ability ne
porte la CHAINE `"None"` : la case 0 est inatteignable par le gameconfig courant, elle n'est donc
exercee ici que par substitution -- et cette substitution porte son propre controle de morsure.

CONTRE-EPREUVE : l'etage 5 rejoue le regime d'AVANT (garde de position en tete) et doit DIVERGER
sur `Melee`. Sans ce cran, un montage ou les deux ecritures coincident rendrait le fichier vert
sans rien prouver. L'etage 4 lit l'AST du module et refuse que la garde remonte au-dessus du
switch -- c'est lui qui mord sur une regression de reordonnancement, qu'aucune valeur ne montre.

ASCII only.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]                  # scripts/python
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                      # noqa: E402
from engine.services import battle_query as SBQ                              # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/services/battle_query.py",),
    "build": True,
    "toujours": False,
    "raison": "Le seul foyer garde est le switch du slot 2 et de ses deux freres, tous dans "
              "`engine/services/battle_query.py`. `build: True` parce que l'etage 0 re-derive la "
              "distribution `attackRangeType` du gameconfig du build et que les etages 1 a 3 "
              "nomment de VRAIES abilities (`BloodyFury`, `AnnihilatorBeam`, `CrusadeOfWrath`) : "
              "un renommage ou une bascule de `attackRangeType` doit faire rougir ce fichier, pas "
              "le rendre vacant.",
}

#: Une position ARBITRAIRE mais VALIDE, pour l'etage de non-regression : les deux ecritures
#: doivent coincider des que les positions sont fournies.
TUILE_A = (2, 3)
TUILE_ADJACENTE = (2, 4)
TUILE_LOIN = (9, 9)


def _abilities_par_range_type() -> dict:
    """Re-derive du gameconfig du build : `{attackRangeType: [nom, ...]}`. Jamais recopie."""
    par = {}
    for nom, cfg in GC._index()["abilities"].items():
        par.setdefault((cfg or {}).get("attackRangeType"), []).append(nom)
    return {k: sorted(v) for k, v in par.items()}


PAR_RT = _abilities_par_range_type()


def _un(rt: str) -> str:
    """Le premier nom d'ability du build qui porte ce `attackRangeType`."""
    noms = PAR_RT.get(rt) or []
    assert noms, "TEMOIN VIDE pour attackRangeType=%s : le gameconfig du build n'en porte aucune" % rt
    return noms[0]


# --------------------------------------------------------------------------------------------
# ETAGE 0 -- les temoins EXISTENT. Un test qui n'exerce rien passe pour vert.
# --------------------------------------------------------------------------------------------
def test_etage0_les_trois_temoins_sont_non_vides():
    for rt in ("Melee", "Ranged", "Normal"):
        assert PAR_RT.get(rt), (
            "aucune ability `attackRangeType=%s` au gameconfig du build : les etages 1 a 3 "
            "n'exerceraient RIEN et passeraient pour verts" % rt)
    assert len(PAR_RT.get("Melee") or []) >= 10, (
        "le gisement `Melee` s'est effondre -- re-deriver avant de conclure")
    # La case 0 du switch n'a AUCUN porteur au gameconfig : mesure, pas hypothese.
    assert not PAR_RT.get("None"), (
        "une ability porte desormais la CHAINE 'None' : l'etage 3 doit cesser de la substituer "
        "et la nommer")


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- `Melee(1)` rend VRAI sans qu'aucune position soit lue. C'EST LE FIX.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cpos,tpos", [(None, None), (None, TUILE_A), (TUILE_A, None)])
def test_etage1_melee_sans_position_rend_vrai(cpos, tpos):
    assert SBQ.is_melee_attack(_un("Melee"), cpos, tpos) is True, (
        "`case 1 (Melee): return true;` ne consulte AUCUNE position dans le decompile -- une "
        "garde de position en tete du corps la rabat a tort sur `false`")


def test_etage1bis_melee_ignore_aussi_le_flag_force_ranged():
    """`if (iVar1 == 1) return 1;` sort AVANT le `HasFlag(caster, 0x15)`, qui n'appartient qu'a
    la branche `Normal(3)`. Le port doit donc rendre VRAI meme flag arme."""
    assert SBQ.is_melee_attack(_un("Melee"), None, None, force_ranged_attack=True) is True
    assert SBQ.is_melee_attack(_un("Melee"), TUILE_A, TUILE_LOIN, force_ranged_attack=True) is True


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- `Ranged(2)` et la branche `Normal(3)` sans position restent FAUX.
# Le fix ne doit pas avoir ouvert une passoire : il DEPLACE une garde, il ne la supprime pas.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cpos,tpos", [(None, None), (None, TUILE_A), (TUILE_A, None)])
def test_etage2_ranged_sans_position_reste_faux(cpos, tpos):
    assert SBQ.is_melee_attack(_un("Ranged"), cpos, tpos) is False


@pytest.mark.parametrize("nom", [None, "AbilityQuiNExistePas", "CrusadeOfWrath"])
@pytest.mark.parametrize("cpos,tpos", [(None, None), (None, TUILE_A), (TUILE_A, None)])
def test_etage2bis_branche_normal_sans_position_reste_faux(nom, cpos, tpos):
    """`case 3 (Normal)` est la SEULE qui deref une position. Le port ne mirroir pas la levee
    native : positions absentes -> `False`, la place de la garde ayant seulement change."""
    assert SBQ.is_melee_attack(nom, cpos, tpos) is False


# --------------------------------------------------------------------------------------------
# ETAGE 3 -- la case 0 (`AttackRangeType.None`), inatteignable au gameconfig, par substitution
# QUI PORTE SON CONTROLE DE MORSURE.
# --------------------------------------------------------------------------------------------
def test_etage3_case_none_rend_faux_et_la_substitution_mord(monkeypatch):
    monkeypatch.setattr(SBQ, "attack_range_type", lambda _n: "Melee")
    assert SBQ.is_melee_attack("PeuImporte", None, None) is True, (
        "la substitution d'`attack_range_type` NE MORD PAS : l'assertion suivante ne prouverait "
        "rien")
    monkeypatch.setattr(SBQ, "attack_range_type", lambda _n: "None")
    assert SBQ.is_melee_attack("PeuImporte", None, None) is False
    assert SBQ.is_melee_attack("PeuImporte", TUILE_A, TUILE_ADJACENTE) is False, (
        "`case 0` rend faux MEME au contact -- il ne consulte aucune position")


# --------------------------------------------------------------------------------------------
# ETAGE 4 -- INVARIANT STRUCTUREL, lu a l'AST : la garde de position vit SOUS le switch, dans
# les TROIS freres. C'est le seul etage qui morde sur un reordonnancement, qu'aucune valeur ne
# montre des lors que les positions sont fournies.
# --------------------------------------------------------------------------------------------
_FRERES = ("is_melee_attack", "is_ranged_attack", "get_attack_range_type")


def _corps(nom_fn: str) -> ast.FunctionDef:
    arbre = ast.parse(inspect.getsource(SBQ))
    for n in ast.walk(arbre):
        if isinstance(n, ast.FunctionDef) and n.name == nom_fn:
            return n
    raise AssertionError("fonction introuvable dans le module : %s" % nom_fn)


def _ligne_garde_position(fn: ast.FunctionDef):
    """La 1re ligne qui teste `caster_position is None` / `target_position is None`."""
    for n in ast.walk(fn):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) \
                and n.left.id in ("caster_position", "target_position"):
            return n.lineno
    return None


def _ligne_premier_switch(fn: ast.FunctionDef):
    """La 1re ligne qui compare le resultat d'`attack_range_type` a un membre du switch."""
    for n in ast.walk(fn):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and n.left.id == "rt":
            return n.lineno
    return None


@pytest.mark.parametrize("nom_fn", _FRERES)
def test_etage4_la_garde_de_position_vit_sous_le_switch(nom_fn):
    fn = _corps(nom_fn)
    l_switch = _ligne_premier_switch(fn)
    l_garde = _ligne_garde_position(fn)
    assert l_switch is not None, (
        "%s ne branche plus sur `rt` : le mirror du switch natif a disparu" % nom_fn)
    assert l_garde is not None, (
        "%s ne garde plus les positions absentes : le port mirroirerait une levee native" % nom_fn)
    assert l_garde > l_switch, (
        "%s teste les positions AVANT de brancher (garde ligne %s, switch ligne %s) -- le natif "
        "`BattleQuery$$%s` branche d'abord et ne lit une position que dans `Normal(3)`"
        % (nom_fn, l_garde, l_switch, nom_fn))


def test_etage4bis_le_detecteur_de_garde_mord_sur_le_regime_dAVANT():
    """CONTRE-EPREUVE DU DETECTEUR : sur une fonction ecrite comme AVANT le fix, il doit rendre
    une garde ANTERIEURE au switch. Un detecteur qui rendrait toujours `garde > switch` serait
    vert quoi qu'il arrive."""
    avant = ast.parse(
        "def f(ability_name, caster_position, target_position):\n"
        "    if caster_position is None or target_position is None:\n"
        "        return False\n"
        "    rt = attack_range_type(ability_name)\n"
        "    if rt == 'Melee':\n"
        "        return True\n"
        "    return False\n").body[0]
    assert _ligne_garde_position(avant) < _ligne_premier_switch(avant), (
        "le detecteur ne voit pas le regime d'AVANT : l'etage 4 ne prouverait rien")


# --------------------------------------------------------------------------------------------
# ETAGE 5 -- NON-REGRESSION + CONTRE-EPREUVE DE VALEUR. Le fix est un STRICT no-op des que les
# DEUX positions sont fournies ; et le regime d'AVANT, rejoue tel quel, DIVERGE sur `Melee`.
# --------------------------------------------------------------------------------------------
def _avant_le_fix(ability_name, caster_position, target_position, **kw):
    """L'ecriture d'AVANT #10024-r1, rejouee TELLE QUELLE : garde de position en TETE."""
    if caster_position is None or target_position is None:
        return False
    return SBQ.is_melee_attack(ability_name, caster_position, target_position, **kw)


@pytest.mark.parametrize("nom", [None, "CrusadeOfWrath"])
@pytest.mark.parametrize("cpos,tpos", [(TUILE_A, TUILE_ADJACENTE), (TUILE_A, TUILE_LOIN)])
def test_etage5_no_op_quand_les_deux_positions_sont_fournies(nom, cpos, tpos):
    assert SBQ.is_melee_attack(nom, cpos, tpos) is _avant_le_fix(nom, cpos, tpos)


@pytest.mark.parametrize("rt,attendu_apres", [("Melee", True), ("Ranged", False)])
def test_etage5bis_la_divergence_est_exactement_melee_sans_position(rt, attendu_apres):
    apres = SBQ.is_melee_attack(_un(rt), None, None)
    avant = _avant_le_fix(_un(rt), None, None)
    assert apres is attendu_apres
    assert avant is False
    assert (apres != avant) is (rt == "Melee"), (
        "la divergence attendue est EXACTEMENT `Melee` sans position : ni plus (une passoire), "
        "ni moins (un fix inerte)")
