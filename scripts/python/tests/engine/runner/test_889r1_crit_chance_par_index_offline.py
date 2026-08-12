"""#889-r1 -- LE CANAL CRIT-CHANCE SE RELIT A CHAQUE COUP, PAS A DEUX POINTS.

`IdunBattle.Core.Services.DamagePrediction$$RollCritical(this, attaquant, defenseur,
abilityOrEffect, **hitIndex**)` passe l'index a
`IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects`, qui le pose dans
l'`IdunBattle.Entities.Abilities.AbilityEntities` qu'il construit lui-meme -- le noeud
`IdunBattleLogic.Entities.DSLFormulas$$CurrentHitIndex` le relit donc a CHAQUE coup.

Le port ne mesurait que DEUX points (`crit_chance` = index 0, `crit_chance_after` = index 1) : exact
pour toute serie de 1 ou 2 coups, faux au-dela des qu'un `EffectBonus` discrimine un index >= 2.

BORNE LUE, gardee ici : `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage` appelle
`GetCritDamageBonusFromEffects(this, attaquant, defenseur, abilityOrEffect)` -- QUATRE arguments,
**sans** `hitIndex`. Le canal crit-DEGAT n'est donc PAS index-dependant, et la reparation ne doit pas
le toucher.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.damage_hits import HitDamage
from engine.runner.prng import IntBasedMersenneTwister


_OPS = pathlib.Path(__file__).resolve().parents[3] / "engine" / "runner" / "operations"


def _run(hits, *, crit_chance_at=None, hit_index0=0, crit_chance=100,
         crit_chance_after=100, seed=777):
    """Une salve de `hits` coups, cellules DEGENEREES (min == max) pour que seul le CRIT bouge."""
    return AttackDamageOperation._run_hits(
        IntBasedMersenneTwister(seed), HitDamage(100, 100), HitDamage(200, 200),
        crit_chance, True, hits, None,
        crit_chance_after=crit_chance_after, crit_enabled_after=True,
        crit_chance_at=crit_chance_at, hit_index0=hit_index0)


def _tracer(discrimine_index=None):
    """Closure de mesure : enregistre les index rappeles. `discrimine_index` = l'index auquel elle
    rend une chance NULLE (le porteur synthetique de l'axe INDEX)."""
    vus = []

    def _at(idx):
        vus.append(idx)
        return (0, True) if idx == discrimine_index else (100, True)

    return _at, vus


# --------------------------------------------------------------- etage 1 : le no-op est TOTAL

@pytest.mark.parametrize("hits", [1, 2])
def test_une_ou_deux_coups_ne_rappellent_JAMAIS_le_canal(hits):
    """A 1 ou 2 coups, les deux points de mesure COUVRENT tous les index joues (0 et 1) : aucun
    rappel ne doit avoir lieu. C'est ce qui rend la reparation bit-identique -- et sans surcout --
    sur tout ce que le corpus mesure aujourd'hui."""
    at, vus = _tracer()
    _run(hits, crit_chance_at=at)
    assert vus == [], "un rappel a eu lieu la ou les deux points suffisent : %r" % (vus,)


@pytest.mark.parametrize("hits", [1, 2, 3, 5])
def test_une_closure_qui_ne_discrimine_pas_est_un_NO_OP_exact(hits):
    """Contre-epreuve de neutralite : quand le canal rend la MEME valeur a tous les index (le cas de
    toutes les attaques sans porteur index-dependant), le resultat est identique AU COUP PRES a
    celui d'avant la reparation."""
    avant = _run(hits)
    at, _ = _tracer()
    apres = _run(hits, crit_chance_at=at)
    assert avant["per_hit"] == apres["per_hit"]
    assert avant["crits"] == apres["crits"]


# ------------------------------------------------- etage 2 : au-dela, l'index exact est demande

def test_trois_coups_rappellent_l_index_2_et_PAS_l_index_de_reference():
    """L'index 1 est deja mesure (`crit_chance_after`) : le rappeler serait un surcout pur. L'index 2
    ne l'est PAS -- c'est exactement le trou de #889-r1."""
    at, vus = _tracer()
    _run(3, crit_chance_at=at)
    assert vus == [2], "attendu un rappel du seul index 2, vu %r" % (vus,)


def test_le_groupe_ADDITIONNEL_reference_hit_index0_plus_1():
    """`hit_index0 > 0` (groupe de coups additionnels, #179) : l'index de reference N'EST PAS 1, mais
    `hit_index0 + 1` -- c'est l'index auquel le vecteur appelle `_crit_params`. Un gate ecrit
    `idx >= 2` serait faux ici : il rappellerait l'index deja mesure et sauterait le premier coup du
    groupe."""
    at, vus = _tracer()
    _run(3, crit_chance_at=at, hit_index0=5)
    assert 6 not in vus, "l'index de reference (hit_index0 + 1 = 6) a ete rappele : %r" % (vus,)
    assert 5 in vus, "le premier coup du groupe (index 5) n'a pas ete rappele : %r" % (vus,)


# ------------------------------------------------------------- etage 3 : le comportement CHANGE

def test_un_porteur_qui_discrimine_l_index_2_MORD():
    """LE cliquet. Un `EffectBonus` dont le trigger porte `AmountIsEqual(CurrentHitIndex(), 2)` doit
    changer le resultat observable. Sans la reparation, l'index 2 lisait la valeur de l'index 1."""
    at_plat, _ = _tracer()
    at_discr, _ = _tracer(discrimine_index=2)
    plat = _run(5, crit_chance_at=at_plat)
    discr = _run(5, crit_chance_at=at_discr)
    assert plat["crits"] != discr["crits"], \
        "le canal index-dependant n'a rien change : la reparation est DESARMEE"
    assert plat["crits"][2] is True and discr["crits"][2] is False, \
        "c'est bien le coup d'index 2 qui doit basculer : %r vs %r" % (plat["crits"], discr["crits"])


def test_sans_la_closure_l_index_2_lit_la_valeur_de_l_index_1():
    """La MESURE du defaut, gardee en negatif : en l'absence de canal par index, le coup 2 prend la
    valeur mesuree a l'index 1 -- ce qui etait le comportement AVANT #889-r1."""
    at_discr, _ = _tracer(discrimine_index=2)
    sans = _run(5)                                   # deux points de mesure seulement
    avec = _run(5, crit_chance_at=at_discr)
    assert sans["crits"][2] is True
    assert avec["crits"][2] is False


# ---------------------------------------- etage 4 : la BORNE lue -- la crit-DEGAT n'est pas touchee

def test_la_closure_ne_rend_que_chance_et_gate_jamais_la_crit_damage():
    """`GetCritDamageBonusFromEffects` ne recoit PAS de `hitIndex` (4 arguments, LU sur `rnca9r7q6c`).
    Les trois closures des vecteurs doivent donc rendre un COUPLE (chance, enabled) -- jamais un
    triplet qui embarquerait la crit-DEGAT."""
    for vecteur in ("normal.py", "ability.py", "normal_like.py"):
        src = (_OPS / "damage_ops" / vecteur).read_text(encoding="utf-8")
        arbre = ast.parse(src)
        fns = [n for n in ast.walk(arbre)
               if isinstance(n, ast.FunctionDef) and n.name == "_crit_chance_at"]
        assert len(fns) == 1, "%s : %d definition(s) de `_crit_chance_at`" % (vecteur, len(fns))
        retours = [n for n in ast.walk(fns[0])
                   if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple)]
        assert retours, "%s : `_crit_chance_at` ne rend aucun tuple" % vecteur
        for r in retours:
            assert len(r.value.elts) == 2, \
                "%s : `_crit_chance_at` rend %d valeurs -- la crit-DEGAT n'est pas index-dependante" \
                % (vecteur, len(r.value.elts))


# -------------------------------------- etage 5 : le CABLAGE des trois vecteurs (garde par AST)

def test_les_trois_vecteurs_CABLENT_le_canal_par_index():
    """Garde de CABLAGE. Un `_crit_chance_at` defini mais jamais passe a `_run_hits` serait du code
    mort et le residu se rouvrirait en silence -- exactement la forme de faux vert que #963 a
    rencontree avec un garde par chaine de caracteres. On confronte donc l'AST : l'appel a
    `_run_hits` doit porter le mot-cle `crit_chance_at`, et sa valeur doit etre le NOM de la closure
    locale (pas une constante, pas `None`)."""
    for vecteur in ("normal.py", "ability.py", "normal_like.py"):
        arbre = ast.parse((_OPS / "damage_ops" / vecteur).read_text(encoding="utf-8"))
        appels = [n for n in ast.walk(arbre)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "_run_hits"]
        assert appels, "%s : aucun appel a `_run_hits`" % vecteur
        for appel in appels:
            kw = {k.arg: k.value for k in appel.keywords if k.arg}
            assert "crit_chance_at" in kw, \
                "%s : `_run_hits` appele SANS `crit_chance_at` -- #889-r1 rouvert" % vecteur
            assert isinstance(kw["crit_chance_at"], ast.Name), \
                "%s : `crit_chance_at` n'est pas la closure locale" % vecteur
            assert kw["crit_chance_at"].id == "_crit_chance_at", \
                "%s : `crit_chance_at` cable sur %r" % (vecteur, kw["crit_chance_at"].id)
