"""#362 -- `1132 KillMaimBurn` : le playbook NonComparable est PORTE, gate compris.

CE QUE CETTE GARDE VERROUILLE

A. **L'oracle NC ne rend pas « la prediction de l'ability ».** `ncPlaybookPredict` pose son
   trampoline sur `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor` : il capture TOUT ce que
   l'evaluation construit. Or `IdunBattle.AI.Playbook.Loki.KillMaimBurnPlaybook$$Evaluate
   NonComparable` ouvre son corps de boucle par `IdunBattle.AI.Playbook.BasePlaybook$$WillNormal
   AttackKill`, qui construit lui-meme un `ProbableDamageEvent` (prediction de l'attaque NORMALE)
   avec le MEME `targetId`. Le `(8536, 8536, 4)` du residu `#356-r1`, lu a l'epoque comme « la
   prediction de 1132, bornee aux PV MAX », est cet event-la : `4` = `worldKharn.weapons[0].hits`,
   quand `nrOfHits` de l'ability vaut `1`.

B. **Le gate est un `continue`, et il se voit.** Aux PV du seed la normale de Kharn sur-tue :
   toutes les cibles sont sautees, le Bucket reste VIDE et le natif ne construit AUCUNE prediction
   d'ability. C'est la reponse JUSTE du natif -- et c'est aussi pourquoi `probe_344` doit rendre
   NON CONFRONTE (rc 2) sur ce montage-la plutot que d'accuser l'arrondi.

C. **Le gate CHANGE la cible emise.** Avec un survivant et un mourant sur l'anneau, le
   contrefactuel « port sans gate » designe le mourant (utilite du kill sur), le natif designe le
   survivant, et le port avec gate aussi -- verifie sur `bucketUtil`, pas sur un scalaire choisi
   apres coup.

D. **La forme d'arrondi de `1132` est enfin confrontable** : `probe_344 --oracle auto` commute sur
   l'oracle NC, compare la SEQUENCE construite, et doit elire `to_even` -- ce que le registre
   `_PREDICTION_MINMAX_AVERAGE` prevoit pour la famille (a)
   (`AActiveAbility$$MinMaxDamage(state, isPrediction: TRUE)` = `Half(Sum(Direct, Direct))` ->
   `DivideAmount$$Calculate` -> `Fix64.Round(., 0)` demi-vers-le-pair).

Mesure : `probe_362_kill_maim_burn_nc.py`. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_344_ability_damage_average as P344             # noqa: E402
import probe_362_kill_maim_burn_nc as P362                  # noqa: E402
from engine.entities.abilities.active_ability import _PREDICTION_MINMAX_AVERAGE  # noqa: E402
from engine.playbook import noncomparable as NCPB           # noqa: E402

ABILITY = 1132
CASTER = "worldKharn"

# Le montage #344 de 1132 : anneau (precondition satisfaite par construction), armure retiree,
# niveaux poses pour `3 mod 4` (bras a, niveau 3 : 70+101=171) et `1 mod 4` (bras b, niveau 12 :
# 171+246=417), et PV de la cible FORCES -- sans quoi le gate mord et il n'y a rien a mesurer.
MONTAGE_344 = dict(caster=CASTER, victim="necroWarden", ability=ABILITY,
                   ability_name="KillMaimBurn", board="MC1_67", center=(3, 4),
                   lvl_a=3, lvl_b=12, armor_target=0, victim_hp=400000, seed=36240)


@pytest.fixture(scope="module")
def p362():
    sf = PYDIR.parents[1] / "logs" / "t362_p362.json"
    return P362.run(state_file=str(sf), verbose=False)


@pytest.fixture(scope="module")
def p344():
    sf = PYDIR.parents[1] / "logs" / "t362_p344.json"
    return P344.run(state_file=str(sf), verbose=False, **MONTAGE_344)


# --- pre-conditions offline ---------------------------------------------------------------------

def test_1132_is_ported_and_belongs_to_the_average_family():
    """Sans playbook NC porte, `probe_344 --oracle auto` refuserait (rc 2) et rien de ce qui suit
    ne serait mesure ; sans appartenance au registre (a), la variante attendue changerait sans que
    rien ne le dise."""
    assert NCPB.is_noncomp(ABILITY) and P344._is_nc(ABILITY)
    assert ABILITY in _PREDICTION_MINMAX_AVERAGE


def test_the_playbook_carries_the_native_constants():
    """`.cctor` = `Fix64(1)` -> `MIN_UTILITY` ; `get_Priority` non surcharge -> tier 0 (mesure
    exhaustive #170, 1132 hors `NATIVE_PRIORITY`)."""
    pb = NCPB.playbook_for(ABILITY)
    assert pb.MIN_UTILITY == 1.0 and pb.PRIORITY == 0


# --- A/B : ce que l'oracle capture VRAIMENT ------------------------------------------------------

def test_the_gate_event_is_the_normal_attack(p362):
    """A : l'event capte quand le gate mord egale EXACTEMENT la prediction d'attaque NORMALE du
    port -- ce n'est pas 1132."""
    assert p362["gate_event_is_normal_attack"], p362["gate_on"]
    on = p362["gate_on"]
    assert on["port_normal_attack_will_be_kill"] is True
    # Le discriminant OBSERVABLE : les coups de l'ARME, pas `nrOfHits` de l'ability.
    hits = [e["appliedHits"] for e in on["captured"] if e["targetId"] == on["targetId"]]
    assert hits and hits[0] == on["port_normal_attack"][2] != on["port_ability"][2], (
        "les coups captes ne separent plus l'attaque normale de l'ability : %s" % on["captured"])


def test_the_gate_skips_the_target_and_empties_the_bucket(p362):
    """B : sure-kill -> `continue` natif -> aucune prediction d'ability, Bucket VIDE."""
    assert p362["gate_on_skips"], p362["gate_on"]
    assert p362["gate_on"]["bucket"] == "empty"


def test_out_of_the_gate_the_port_reproduces_the_whole_sequence(p362):
    """B (revers) : PV forces -> le natif construit `[normale, ability]` dans cet ordre, et le port
    rend les MEMES deux tuples."""
    assert p362["gate_off_builds_both"], p362["gate_off"]
    off = p362["gate_off"]
    mains = [e for e in off["captured"] if e["targetId"] == off["targetId"]]
    assert len(mains) == 2, mains
    assert (mains[1]["healthDmgMin"], mains[1]["healthDmgMax"],
            mains[1]["appliedHits"]) == off["port_ability"]


# --- C : le gate change le RESULTAT OBSERVABLE ---------------------------------------------------

def test_the_gate_changes_the_target_the_native_picks(p362):
    """C : le contrefactuel « sans gate » designe le mourant ; le natif et le port avec gate
    designent le survivant. Sans cette difference, le port du gate serait invalidable."""
    arg = p362["argmax"]
    assert not arg.get("error"), arg.get("error")
    assert p362["gate_changes_target"], (arg["argmax_with_gate"], arg["argmax_without_gate"])
    assert p362["argmax_agrees"], (
        "bucketUtil natif %s : ni l'utilite AVEC gate %s, ni le montage n'expliquent l'ecart"
        % (arg.get("bucketUtil"), arg.get("port_with_gate")))


# --- D : la forme d'arrondi de 1132 --------------------------------------------------------------

def test_p344_uses_the_nc_oracle_and_reaches_the_regime(p344):
    assert p344.get("oracle") == "nc"
    assert not p344.get("not_confronted"), p344.get("reason")
    for k in ("a", "b"):
        arm = p344["arms"][k]
        assert not arm.get("error"), "bras %s KO : %s" % (k, arm["error"])
        assert (arm.get("regime") or {}).get("reached"), arm.get("regime")
        assert arm["discriminates"], (
            "bras %s : les quatre variantes coincident, il ne prouve rien" % k)


def test_p344_shipped_code_matches_native_and_selects_to_even(p344):
    for k in ("a", "b"):
        arm = p344["arms"][k]
        assert arm["shipped_ok"], (
            "bras %s : port LIVRE %s vs natif %s (minDmg=%d maxDmg=%d somme=%d)"
            % (k, arm["shipped"], arm["native"], arm["minDmg"], arm["maxDmg"], arm["sum"]))
    assert p344["nul_on_both_arms"] == ["to_even"], p344["nul_on_both_arms"]
    assert p344.get("ok") is True


def test_the_compared_sequence_carries_the_gate_event(p344):
    """La comparaison porte sur la SEQUENCE : deux events par bras (gate + ability). Retomber a un
    seul signifierait qu'on a recommence a opposer l'event du gate a la prediction d'ability."""
    for k in ("a", "b"):
        arm = p344["arms"][k]
        assert len(arm["native"]) == 2 and len(arm["shipped"]) == 2, (
            "bras %s : natif=%s port=%s" % (k, arm["native"], arm["shipped"]))
        assert arm["native"][0][2] == 4 and arm["native"][1][2] == 1, (
            "bras %s : les coups ne separent plus gate (4) et ability (1) : %s"
            % (k, arm["native"]))


def test_a_montage_where_the_gate_bites_says_not_confronted_instead_of_failing():
    """TROIS ISSUES. Le MEME montage, PV de la cible non pilotes : le gate mord, aucune prediction
    d'ability n'est construite, et `probe_344` doit rendre NON CONFRONTE -- il n'accuse ni le port
    ni ne verdit. C'est le pendant exact du separateur de #356 sec.6."""
    sf = PYDIR.parents[1] / "logs" / "t362_p344_gate.json"
    m = dict(MONTAGE_344)
    m["victim_hp"] = None
    m["seed"] = 36260
    out = P344.run(state_file=str(sf), verbose=False, **m)
    assert out.get("not_confronted") is True, out.get("arms")
    assert out.get("ok") is None
    assert "gate predictif" in (out.get("reason") or "")
