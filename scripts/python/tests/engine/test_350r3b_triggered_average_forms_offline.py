"""#350-r3b -- la couche TRIGGERED porte ses DEUX formes de moyenne, et chacune au bon call-site.

Symetrique de `test_350_prediction_average_forms_offline.py` (couche ACTIVE). La difference de fond,
et la raison d'etre de ce fichier : cote TRIGGERED les deux constructeurs natifs rendent un NOEUD
DSL, et c'est le SLOT d'`IAmountFormula` que le playbook invoque qui decide de l'arrondi.

    IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage
        -> RandomAmount(Get(minDmg 0xc), Get(maxDmg 0xd))            noeud a PLAGE
        -> slot 4 = IdunBattle.DSL.AAmountFormula$$CalculateAverage  = (mx + mn) / 2 ENTIERE
                                                                    = TRONCATURE
    IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamageAverage
        -> Half(Sum(Direct(minDmg), Direct(maxDmg)), 0)              noeud SIMPLE
        -> slot 1 = Calculate -> IdunBattle.Entities.Formulas.DivideAmount$$Calculate
                              -> IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)
                              = Fix64.Round DEMI-VERS-LE-PAIR

Ce que la garde verrouille :
A. le registre `TRIGGERED_PREDICTION_AVERAGE_FORM` couvre les SIX call-sites lus, avec le couple
   (getter, slot) COHERENT -- un `GetDamage` lu au slot 1 serait un TIRAGE, un `GetAverageDamage`
   lu au slot 4 serait une moyenne de moyenne ;
B. sur un regime DISCRIMINANT (`minDmg + maxDmg == 3 mod 4`, le seul ou les deux formes different,
   d'exactement 1), le foyer du moteur rend la forme du call-site -- c'est LE cliquet : inverser un
   slot dans le registre fait sortir l'autre colonne et rougir cette assertion ;
C. les quatre slots d'`IAmountFormula` existent sur `AAmountFormula`, et sur un noeud SIMPLE le slot
   4 rend EXACTEMENT le slot 1 (la branche « plage » y vaut `(v + v) / 2 = v`) -- c'est ce qui rend
   le predicat de court-circuit `<vtable+0x1c8>` inobservable, donc non porte ;
D. `RandomAmount` est le SEUL noeud de ce port a surcharger les slots de plage, et ses deux
   surcharges rendent ses deux ENFANTS (jamais un tirage) ;
E. `FuryOfTheAncientsPlaybook`, seul consommateur triggered PORTE, passe par ce foyer et reste du
   cote TRONCATURE -- la couche est EXERCEE, pas spéculative ;
F. un call-site ABSENT du registre LEVE : pas de defaut silencieux. Le defaut silencieux est
   exactement ce qui a laisse la forme demi-vers-le-pair absente du moteur jusqu'a #350-r3b.

CONFRONTATION LIVE : la face TRONCATURE est reconciliee (`probe_32d_fury.py`, #32/#339) ; la face
demi-vers-le-pair NE L'EST PAS -- ses quatre call-sites rendent une UTILITE, et aucun oracle
n'expose `TriggeredAbilityPlaybook<T>$$CalculateUtilityFromDamageEvent`. Nomme dans
`docs/rl/case-350r3b-moyennes-triggered.md` §5.

ASCII only.
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_350r3b_triggered_average_forms as TAF                              # noqa: E402
from engine.dsl.base import (DslContext, Const, calculate_average,              # noqa: E402
                             _round_fix64)
from engine.entities.formulas import Sum, Half, RandomAmount, Multiply          # noqa: E402
from engine.entities.abilities.triggered_ability import (                       # noqa: E402
    BaseTriggeredAbility, triggered_prediction_damage, TRIGGERED_PREDICTION_AVERAGE_FORM,
    _GET_DAMAGE, _GET_AVERAGE_DAMAGE)

# Les six call-sites LUS sur `rnca9r7q6c` (xrefs entrantes de
# `BaseTriggeredAbility$$MinMaxDamage` / `$$MinMaxDamageAverage`, filtrees sur les playbooks).
_TRUNC_SITES = (
    "IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction",
    "IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$EvaluateNonComparable",
)
_HALF_EVEN_SITES = (
    "IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityForMainTarget",
    "IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityForSecondaryTarget",
    "IdunBattle.AI.Playbook.Loki.LightImUpPlaybook."
    "u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext",
    "IdunBattle.AI.Playbook.Loki.MassiveScythingTalonsPlaybook."
    "u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext",
)


# ---- A. le registre est complet et COHERENT (getter <-> slot) --------------------------------
def test_registre_couvre_les_six_call_sites_lus():
    lus = set(_TRUNC_SITES) | set(_HALF_EVEN_SITES)
    porte = set(TRIGGERED_PREDICTION_AVERAGE_FORM)
    assert porte == lus, (
        "le registre des formes TRIGGERED a derive des xrefs lues sur rnca9r7q6c ; "
        "manquants=%s en trop=%s" % (sorted(lus - porte), sorted(porte - lus)))


@pytest.mark.parametrize("call_site", _TRUNC_SITES)
def test_voie_troncature_est_get_damage_au_slot_4(call_site):
    getter, slot = TRIGGERED_PREDICTION_AVERAGE_FORM[call_site]
    assert (getter, slot) == (_GET_DAMAGE, 4), (
        "%s lit BaseTriggeredAbility$$MinMaxDamage (noeud RandomAmount) au slot 4 "
        "(AAmountFormula$$CalculateAverage) ; registre=(%s, %s). Un RandomAmount lu au slot 1 "
        "serait un TIRAGE, pas une prediction." % (call_site, getter, slot))


@pytest.mark.parametrize("call_site", _HALF_EVEN_SITES)
def test_voie_demi_vers_le_pair_est_get_average_damage_au_slot_1(call_site):
    getter, slot = TRIGGERED_PREDICTION_AVERAGE_FORM[call_site]
    assert (getter, slot) == (_GET_AVERAGE_DAMAGE, 1), (
        "%s lit BaseTriggeredAbility$$MinMaxDamageAverage (noeud Half(Sum(...), 0)) au slot 1 "
        "(Calculate) ; registre=(%s, %s). Ce noeud lu au slot 4 serait une moyenne de moyenne."
        % (call_site, getter, slot))


# ---- B. le CLIQUET : sur un regime discriminant, le foyer rend la forme du call-site ----------
#
# ⚠ L'attendu vient de la LECTURE (`_TRUNC_SITES` / `_HALF_EVEN_SITES`, transcrits du decompile),
# JAMAIS du registre : sinon la garde SUIVRAIT une mutation du registre au lieu de la denoncer.
# Mesure : avec l'attendu tire du registre, la mutation adversariale (formes echangees) laissait
# cette assertion VERTE -- exactement le genre de cliquet qui ne cliquette pas.
@pytest.mark.parametrize("call_site", _TRUNC_SITES[:1] + _HALF_EVEN_SITES)
def test_foyer_rend_la_forme_du_call_site_sur_un_regime_discriminant(
        call_site, triggered_average_form_case):
    r = triggered_average_form_case(call_site)
    assert r["discriminating"], (
        "regime NON discriminant pour %s (min+max=%d, %% 4 = %d) : les deux formes y coincident, "
        "cette assertion ne mesurerait rien"
        % (r["ability_id"], r["min_dmg"] + r["max_dmg"], r["sum_mod_4"]))
    assert r["trunc"] + 1 == r["half_even"], (
        "sur un regime 3 mod 4 le demi-vers-le-pair MONTE d'exactement 1 au-dessus de la "
        "troncature ; mesure trunc=%d half_even=%d" % (r["trunc"], r["half_even"]))
    lu = "trunc" if call_site in _TRUNC_SITES else "half_even"
    attendu_natif = r[lu]
    assert r["engine"] == attendu_natif, (
        "FORME FAUSSE pour %s (lvl=%d mult=%d, minDmg=%d maxDmg=%d) : le foyer rend %d, "
        "le natif rend %d (troncature=%d via BaseTriggeredAbility$$MinMaxDamage@slot4, "
        "demi-vers-le-pair=%d via BaseTriggeredAbility$$MinMaxDamageAverage@slot1) ; "
        "registre du port = (%s, slot %d)"
        % (r["call_site"], r["level"], r["mult"], r["min_dmg"], r["max_dmg"],
           r["engine"], attendu_natif, r["trunc"], r["half_even"], r["getter"], r["slot"]))


# ---- C. les quatre slots d'IAmountFormula, et l'inobservabilite du predicat -------------------
@pytest.mark.parametrize("value", [1, 2, 3, 7, 2761, 5523])
def test_sur_un_noeud_simple_le_slot_4_rend_le_slot_1(value):
    """`ASimpleAmountFormula$$CalculateMin`/`$$CalculateMax` = `Calculate` -> la branche « plage »
    d'`AAmountFormula$$CalculateAverage` vaut `(v + v) / 2 = v`, identique au court-circuit. C'est
    CE fait qui autorise a ne PAS porter le predicat `<vtable+0x1c8>`."""
    ctx = DslContext()
    for node in (Const(value), Sum(Const(value), Const(0)), Multiply(Const(value), Const(1))):
        assert node.calculate_min(ctx) == node.calculate(ctx)
        assert node.calculate_max(ctx) == node.calculate(ctx)
        assert node.calculate_average(ctx) == node.calculate(ctx), (
            "noeud SIMPLE %s : slot 4 (%s) != slot 1 (%s) -- la branche plage doit y etre inerte"
            % (type(node).__name__, node.calculate_average(ctx), node.calculate(ctx)))


# ---- D. RandomAmount : le SEUL noeud a plage porte, et ses slots rendent ses enfants ----------
@pytest.mark.parametrize("mn,mx", [(8, 11), (15, 20), (28, 35), (2761, 2762), (599, 797)])
def test_random_amount_expose_ses_deux_enfants_aux_slots_de_plage(mn, mx):
    ctx = DslContext()
    node = RandomAmount(Const(mn), Const(mx))
    assert node.calculate_min(ctx) == mn, "RandomAmount$$CalculateMin = this@+0x10.Calculate"
    assert node.calculate_max(ctx) == mx, "RandomAmount$$CalculateMax = this@+0x18.Calculate"
    assert node.calculate_average(ctx) == calculate_average(mn, mx), (
        "slot 4 sur RandomAmount = (max + min) / 2 division ENTIERE C (TRONCATURE) ; "
        "mesure %d au lieu de %d" % (node.calculate_average(ctx), calculate_average(mn, mx)))
    # et la forme SOEUR, sur les MEMES bornes, est l'autre arrondi : `DivideAmount$$Calculate` ->
    # `AAmountFormula$$RoundFix64Result(., 0)` = `Fix64.Round` = arrondi BANQUIER (demi-vers-le-pair)
    assert Half(Sum(Const(mn), Const(mx)), 0).calculate(ctx) == _round_fix64(
        Fraction(mn + mx, 2), 0), "Half(Sum(...), 0) = RoundFix64Result(., 0) = Fix64.Round"


def test_les_deux_formes_ne_divergent_que_sur_3_mod_4():
    """La signature de #339/#350-r3b : d'exactement 1, et UNIQUEMENT quand `mn + mx == 3 mod 4`.
    C'est ce qui rend le trou invisible trois fois sur quatre -- et pourquoi une garde doit
    CHOISIR son regime au lieu de prendre le niveau 50 par defaut."""
    ctx = DslContext()
    for s in range(0, 400):
        mn, mx = s // 2, s - s // 2
        t = RandomAmount(Const(mn), Const(mx)).calculate_average(ctx)
        h = Half(Sum(Const(mn), Const(mx)), 0).calculate(ctx)
        if s % 4 == 3:
            assert h == t + 1, "s=%d : half_even=%d doit valoir trunc+1=%d" % (s, h, t + 1)
        else:
            assert h == t, "s=%d : les deux formes doivent coincider (half=%d trunc=%d)" % (s, h, t)


# ---- E. Fury, seul consommateur PORTE, passe par le foyer et reste TRONCATURE -----------------
def test_fury_passe_par_le_foyer_et_reste_troncature():
    site = "IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction"
    regimes = TAF.discriminating_regimes("FuryOfTheAncients")
    assert regimes, "aucun regime discriminant pour FuryOfTheAncients -- garde inerte"
    lvl, mult, mn, mx = regimes[0]
    got = triggered_prediction_damage("FuryOfTheAncients", lvl, mult, site)
    assert got == calculate_average(mn, mx), (
        "Fury (lvl=%d mult=%d, minDmg=%d maxDmg=%d) doit TRONQUER (%d) ; le foyer rend %d"
        % (lvl, mult, mn, mx, calculate_average(mn, mx), got))
    assert got == Half(Sum(Const(mn), Const(mx)), 0).calculate(DslContext()) - 1, (
        "et ce regime doit etre DISCRIMINANT (l'autre forme rend +1), sinon rien n'est mesure")


def test_fury_playbook_importe_le_foyer_et_plus_la_primitive():
    """Non-regression de CABLAGE : le playbook ne doit plus choisir la forme lui-meme. S'il
    reimportait `calculate_average` en direct, une correction du registre ne l'atteindrait plus."""
    src = (PYDIR / "engine" / "playbook" / "fury_of_the_ancients.py").read_text(encoding="utf-8")
    assert "triggered_prediction_damage" in src, (
        "fury_of_the_ancients.py doit passer par le foyer `triggered_prediction_damage`")
    assert "from ..dsl.base import calculate_average" not in src, (
        "fury_of_the_ancients.py ne doit plus importer la primitive d'arrondi en direct : la forme "
        "se lit au registre, elle ne se choisit pas au call-site")


# ---- F. pas de defaut silencieux -------------------------------------------------------------
def test_un_call_site_inconnu_leve_au_lieu_de_retomber_sur_un_defaut():
    with pytest.raises(KeyError):
        triggered_prediction_damage("FuryOfTheAncients", 1, 100,
                                    "IdunBattle.AI.Playbook.Loki.InventedPlaybook$$Nope")


def test_ability_sans_min_max_rend_none_plutot_qu_un_zero():
    """`BaseTriggeredAbility$$MinMaxDamage` leve cote natif quand `this@+0x20` est nul ; le port rend
    `None` -- jamais un 0 silencieux qui se lirait comme « degat nul »."""
    ab = BaseTriggeredAbility("AbilityQuiNExistePas", 1, 100)
    assert ab.min_max_damage() is None
    assert ab.min_max_damage_average() is None
