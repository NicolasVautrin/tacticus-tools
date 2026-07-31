"""#350-r3 (b) -- le porteur MACHINE OF WAR, confronte au LIVE.

#350 avait laisse `1147 HadesAutocannons` et `1148 DaemonicOrdnance` (porteur `blackForgefiend`,
MoW) NON CONFRONTEES : le gabarit #344 passe son caster par `--p-units`, qui REFUSE une MoW. La
levee est ecrite dans `probe_350r3_mow_caster.py` (en-tete) ; cette garde en verrouille le resultat.

Ce que la garde tient :

1. la garde `--p-units` est EXPLICITE et STRUCTURELLE -- `pool_regular = normalized - mow`, donc
   `blackForgefiend` est dans `pool_mow` et JAMAIS dans le pool regulier -- et le chemin MoW EST
   cable (`--a-mow` la deploie, board MoW-capable, entree `BC.Units` patchable) ;
2. le mur RESTANT n'est PAS le deploiement : avec la MoW comme caster, l'oracle natif rend une liste
   VIDE sans summon puis `null` avec, et le port n'a AUCUN contexte AI pour une MoW. C'est ce
   constat qui justifie la voie GREFFE (`case-92` §5bis) ;
3. `1147` CONFRONTEE : deux bras de parite, quatre variantes, `to_even` SEULE nulle sur les deux --
   ce que prevoit son inscription (a2) -- et le code LIVRE egal au natif sur les deux bras ;
4. `1148` CONFRONTEE dans ses DEUX regimes : zone froide (natif 0 == port 0) et zone EN FEU
   (natif == port). Le regime froid est celui ou le port INVENTAIT un event avant #350-r3.

Trois runners au total, disposes par le probe. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_350r3_mow_caster as P                          # noqa: E402
from engine.entities.abilities.active_ability import (      # noqa: E402
    _PREDICTION_MINMAX_AVERAGE, _A_VIA_STAFF_OF_STARS_GET_DAMAGE)


@pytest.fixture(scope="module")
def scan():
    return P.scan(verbose=False)


@pytest.fixture(scope="module")
def mow_caster():
    return P.step1_mow_caster(seed=35130, verbose=False)


@pytest.fixture(scope="module")
def confronted_1147():
    return P.step2_confront_1147(seed=35140, verbose=False)


@pytest.fixture(scope="module")
def daemonic():
    return P.step3_daemonic_ordnance(seed=35160, verbose=False)


def test_p_units_refuses_a_mow_by_construction_and_the_mow_path_is_wired(scan):
    """1 : la limite etait NOTRE outil, et elle est structurelle -- pas un oubli de cablage."""
    assert scan["in_pool_mow"] is True, "blackForgefiend n'est plus au pool MoW"
    assert scan["in_pool_regular"] is False, (
        "blackForgefiend serait desormais dans le pool REGULIER : `--p-units` l'accepterait, et le "
        "diagnostic de #350-r3 (garde explicite, pools disjoints) ne tiendrait plus")
    assert scan["in_bc_units_catalog"] is True, (
        "sans entree `BC.Units`, `--unit-stat <mow>:ActiveAbilityLevel` n'aurait aucune prise")
    assert scan["board_mow_ok"] is True, "MC1_67 n'est plus MoW-capable : la MoW serait DROP en silence"
    assert scan["ok"] is True


def test_the_remaining_wall_is_the_oracle_not_the_deployment(mow_caster):
    """2 : la MoW se deploie et son playbook se resout -- et pourtant ni l'oracle ni le port ne
    savent la prendre pour CASTER. C'est ce constat qui rend la greffe necessaire, et c'est lui
    qu'il faudra re-mesurer si `rpc-predict.ts` ou `ai/context.py` changent."""
    assert mow_caster["deployed"] is True
    assert dict(mow_caster["abilities"]).get(1147) == P.A1147_LVL_A, (
        "`--unit-stat` ne pilote plus le niveau d'ability de la MoW : la parite ne serait plus "
        "choisie mais subie")
    assert mow_caster["cold"]["count"] == 0 and mow_caster["cold"]["listNull"] is False
    assert mow_caster["summons"], "le montage summon n'a rien pose"
    assert mow_caster["hot"]["listNull"] is True, (
        "l'oracle rend desormais une liste avec un caster MoW : la voie DIRECTE serait ouverte, "
        "et la greffe ne serait plus la seule voie -- a re-lire avant de garder le montage actuel")
    assert mow_caster["port_ctx_me"] is None, (
        "le port construit desormais un contexte AI pour une MoW : re-evaluer la voie directe")


def test_1147_is_confronted_and_rounds_half_to_even(confronted_1147):
    """3 : le verdict d'arrondi de 1147, mesure sur les deux bras."""
    assert 1147 in _A_VIA_STAFF_OF_STARS_GET_DAMAGE and 1147 in _PREDICTION_MINMAX_AVERAGE
    r = confronted_1147
    for k in ("a", "b"):
        arm = r["arms"][k]
        assert not arm.get("error"), "bras %s KO : %s" % (k, arm["error"])
        assert arm["discriminates"], (
            "bras %s NON DISCRIMINANT (les quatre variantes coincident) : il ne prouve rien" % k)
        assert arm["shipped_ok"], (
            "bras %s : le code LIVRE %s != natif %s" % (k, arm["shipped"], arm["native"]))
    assert r["regimes_ok"], "la parite pilotee n'est pas celle annoncee (3 mod 4 puis 1 mod 4)"
    assert r["nul_on_both_arms"] == ["to_even"], (
        "variantes nulles sur les DEUX bras : %s -- attendu ['to_even'] (voie a2, "
        "`StaffOfStarsAbility$$GetDamage` avec isPrediction = 1)" % r["nul_on_both_arms"])


def test_1148_agrees_with_the_native_in_both_fire_regimes(daemonic):
    """4 : le cliquet du gate de selecteur. Le regime FROID est celui ou le port inventait un
    event ; le regime EN FEU verifie que le gate ne l'a pas simplement eteint."""
    cold, hot = daemonic["cold"], daemonic["hot"]
    assert cold["n_native"] == 0, "le natif emet desormais sur une zone froide : relire le selecteur"
    assert cold["n_port"] == 0, (
        "le port emet %s sur une zone FROIDE la ou le natif n'emet rien -- c'est exactement la "
        "sur-prediction que `_MAKE_DMG_TARGET_GATE` ferme" % (cold["port"],))
    assert daemonic["cast_ok"], "le cast intermediaire a echoue : %s" % daemonic.get("cast_error")
    assert "Fire" in (hot["tile_effects_on_target"] or []), (
        "la tuile de la cible ne brule pas apres le cast : le second regime n'a pas ete atteint")
    assert hot["n_native"] > 0, "zone en feu et natif muet : le montage ne discrimine plus"
    assert hot["port"] == hot["native"], (
        "zone EN FEU : port %s != natif %s -- le gate ne doit pas eteindre les events LEGITIMES"
        % (hot["port"], hot["native"]))
