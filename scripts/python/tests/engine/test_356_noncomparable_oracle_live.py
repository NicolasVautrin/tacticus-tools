"""#356 -- l'ORACLE de la face NonComparable est OUVERT, et une capture nulle est QUALIFIEE.

CE QUE CETTE GARDE VERROUILLE, et pourquoi elle ne peut pas passer par accident :

A. **L'oracle NC rend des events.** `ncPlaybookPredict(via="evaluate")` capture le
   `ProbableDamageEvent` que `<X>Playbook$$EvaluateNonComparable` CONSTRUIT avant de le passer a
   `CalculateUtilityFromDamageEvent` -- il le consomme au lieu de le rendre, d'ou le capteur. Un
   `capturedCount == 0` ici signerait la fermeture de la seule voie d'observation des **134**
   classes de playbook NonComparable.
B. **Le REGIME est atteint et PROUVE, pas suppose.** `1202 VigilanceEternal` n'a de cible eligible
   que si elle est adjacente OU chargeable a portee 2
   (`VigilanceEternalAbility$$GetDynamicInvalidTargetReason`, flag `0x8000000` sinon). Aux tuiles de
   spawn de `MC1_67` c'est FAUX : le montage PILOTE les positions et exige que `abilityTargets`
   devienne non vide. C'est ce qui distingue « le natif a raison de ne rien rendre » de « l'oracle
   est casse » -- la confusion qui avait fait classer #350-r3a-r1 en bug de port.
C. **Le SEPARATEUR est exerce dans les DEUX sens.** Le meme probe, borne a 1 round, doit rendre
   `NON CONFRONTE` (et rc 2), jamais un echec. Un probe qui rougirait la aurait accuse le port pour
   un defaut de montage ; un probe qui verdirait aurait rendu un zero muet.
D. **Le VERROU d'auto-validation du capteur tient.** Sur une ability COMPARABLE
   (`deathBlightlord`/`1042`), la capture par trampoline doit EGALER la liste rendue par
   `MakeDamagePredictions` : sans ca, les nombres de la face NC seraient non verifiables.
E. **`probe_344` branche sur cet oracle tranche la forme d'arrondi de `1202`**, qui etait
   INVALIDABLE live tant qu'on ne disposait que d'`aiPlaybookPredict` (structurellement muet sur un
   NonComparable). Les deux bras doivent discriminer et le code LIVRE egaler le natif.
F. **Une capture nulle a une TROISIEME lecture** : un playbook NC dont l'utilite n'est pas un degat
   n'en construit aucun (`DarkTalonStrikePlaybook` score un COMPTE de cibles). `probe_344` doit
   REFUSER (rc 2 / `out_of_scope`) toute ability hors des deux registres d'arrondi, ou son
   `expected` serait fabrique.

Lecture du decompile : en-tete de `probe_350r3_noncomparable_oracle.py` et
`docs/rl/case-350r3-oracle-noncomparable.md` sec.6-7.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_344_ability_damage_average as P344             # noqa: E402
import probe_350r3_noncomparable_oracle as P350             # noqa: E402
from engine.entities.abilities.active_ability import (_PREDICTION_MINMAX_AVERAGE,   # noqa: E402
                                                      _PREDICTION_MINMAX_RANDOM_READ)
from engine.playbook import noncomparable as NCPB           # noqa: E402

ABILITY = 1202
CASTER = "custoKyrus"

# Montage `probe_344` de la face NC : l'anneau satisfait la precondition PAR CONSTRUCTION (toutes
# les cibles a distance 1) ; niveaux choisis pour poser `3 mod 4` (bras a) et `1 mod 4` (bras b).
MONTAGE_344 = dict(caster=CASTER, ability=ABILITY, ability_name="VigilanceEternal",
                   board="MC1_67", center=(3, 4), lvl_a=4, lvl_b=3, armor_target=0, seed=34650)


@pytest.fixture(scope="module")
def reached():
    """Le probe #350-r3 joue EN ENTIER, montage pilote jusqu'au regime."""
    return P350.run(verbose=False)


@pytest.fixture(scope="module")
def not_reached():
    """Le MEME probe, pilotage borne a 1 round : le regime n'est PAS atteint."""
    return P350.run(verbose=False, max_rounds=1)


@pytest.fixture(scope="module")
def p344_nc():
    sf = PYDIR.parents[1] / "logs" / "t356_p344_nc.json"
    return P344.run(state_file=str(sf), verbose=False, **MONTAGE_344)


# --- pre-conditions offline ---------------------------------------------------------------------

def test_1202_is_noncomparable_and_ported():
    """Sans playbook NC porte cote Python, `--oracle auto` ne commuterait pas et le test
    mesurerait la face Comparable -- qui est structurellement muette ici."""
    assert NCPB.is_noncomp(ABILITY)
    assert P344._is_nc(ABILITY)


def test_1202_belongs_to_the_random_read_family():
    """E (pre-condition) : la variante ATTENDUE par le registre est `trunc`. Si `1202` migrait dans
    l'autre registre, le verdict ci-dessous changerait de cible sans que rien ne le dise."""
    assert ABILITY in _PREDICTION_MINMAX_RANDOM_READ
    assert ABILITY not in _PREDICTION_MINMAX_AVERAGE


def test_probe_344_refuses_an_ability_outside_both_rounding_registries():
    """F : `1092 DarkTalonStrike` a un playbook NC porte mais son utilite est
    `Fix64(GetAttackTargets(GetTilesInBestLine()).Count)` -- aucun `ProbableDamageEvent`. Le probe
    doit le DIRE (`out_of_scope`), pas fabriquer un `expected` puis rougir sur une capture nulle.
    Le refus est PRE-live : aucune session n'est requise."""
    out = P344.run(verbose=False, caster="darkaAzrael", ability=1092,
                   ability_name="DarkTalonStrike")
    assert out.get("out_of_scope") is True
    assert out.get("ok") is None
    assert 1092 not in (set(_PREDICTION_MINMAX_AVERAGE) | set(_PREDICTION_MINMAX_RANDOM_READ))


def test_probe_344_refuses_an_nc_ability_without_a_ported_playbook():
    """F (second volet) : `1132 KillMaimBurn` EST dans un registre d'arrondi et son playbook natif
    EST NonComparable, mais aucun playbook NC n'est porte cote Python -- l'offline mesurerait
    `generate_multi_hit_attack_prediction`, qui n'est pas sa chaine. Mesure : natif
    `(8536, 8536, 4)` (borne aux PV MAX, 4 coups, trois profils) contre `(86, 129, 1)` pour le
    chemin generique. Sans ce refus, le probe rougirait comme un ecart d'ARRONDI ce qui est un
    PORT MANQUANT. Refus PRE-live."""
    assert 1132 in _PREDICTION_MINMAX_AVERAGE and not NCPB.is_noncomp(1132)
    out = P344.run(verbose=False, caster="worldKharn", ability=1132,
                   ability_name="KillMaimBurn", oracle="nc")
    assert out.get("out_of_scope") is True
    assert "playbook NonComparable porte" in (out.get("reason") or "")


# --- A/B/D : l'oracle NC lui-meme ---------------------------------------------------------------

def test_capteur_lock_holds_on_a_comparable_ability(reached):
    """D : capture par trampoline == liste rendue par `MakeDamagePredictions`."""
    lock = reached["step3a"]
    assert not lock.get("skipped"), (
        "capteur absent du bundle : %s -- il FAUT une reinjection avant de conclure quoi que ce "
        "soit sur la face NC" % lock.get("skipped"))
    assert lock["identical"] and lock["nonEmpty"], (
        "verrou du capteur ROMPU : capture=%s rendue=%s -- les nombres de la face NC deviennent "
        "non verifiables" % (lock.get("capturedCount"), lock.get("returnedCount")))


def test_the_regime_is_reached_and_proven(reached):
    """B : la precondition geometrique est SATISFAITE, et prouvee par les deux voies."""
    appr = reached["approach"]
    assert appr.get("reached"), (
        "montage non atteint en %s rounds -- rien de ce qui suit ne pourrait accuser le port"
        % appr.get("rounds"))
    pre = reached["step2"]["precondition"]
    assert pre["fromHereCount"] or pre["targetsCount"], (
        "abilityTargets vide alors que l'approche se dit atteinte : %s" % pre)
    eligible = [r for r in pre["reasons"] if r["eligible"]]
    assert eligible, (
        "aucune cible avec targetReason == 0x0 : %s -- le flag 0x8000000 est exactement ce que "
        "VigilanceEternalAbility$$GetDynamicInvalidTargetReason rend quand la charge est impossible"
        % pre["reasons"])


def test_nc_oracle_returns_damage_events(reached):
    """A : le coeur de #356. `ncPlaybookPredict` capture au moins un event, et il est CHIFFRE."""
    s3 = reached["step3b"]
    assert s3.get("ok"), (
        "capture NULLE alors que le regime est PROUVE -> lecture (b) : le triplet serait consomme "
        "sans passer par ProbableDamageEvent$$.ctor (%s)" % s3.get("error"))
    ev = s3["first"]
    assert ev["healthDmgMin"] > 0 and ev["healthDmgMax"] >= ev["healthDmgMin"], ev
    assert ev["appliedHits"] >= 1, ev
    assert isinstance(s3.get("bucketUtil"), (int, float)) and s3["bucketUtil"] > 0, (
        "bucketUtil absent : l'utilite du Bucket est le second cadran de l'oracle NC")


def test_nc_face_is_not_vacuous(reached):
    """A (complement) : `ncEvaluate` score des positions -- « 0 event » ne se lit pas « rien ne se
    passe »."""
    s2 = reached["step2"]
    assert s2.get("ok") and s2["nScored"] > 0, s2


def test_hvt_is_not_a_proof_of_regime(reached):
    """Garde CONTRE le faux critere. `HasValidTargets` (slot 0x3f) valait `true` 13/13 sur un
    montage a eligibilite VIDE : il ne traverse pas `GetDynamicInvalidTargetReason`. Le probe ne
    doit donc jamais s'en servir comme preuve -- ici il vaut `true` PARTOUT, y compris sur la
    position qui ne score rien."""
    s2 = reached["step2"]
    assert s2["nHvtTrue"] == s2["nPositions"], (
        "hvt n'est plus constant sur ce montage (%d/%d) : re-lire la garde, pas la relacher"
        % (s2["nHvtTrue"], s2["nPositions"]))
    assert s2["nScored"] < s2["nPositions"], (
        "toutes les positions scorent : ce montage ne montre plus que hvt sur-approxime "
        "l'eligibilite")


# --- C : le separateur, exerce dans l'autre sens -------------------------------------------------

def test_a_montage_that_misses_the_regime_says_so_instead_of_failing(not_reached):
    """C : borne a 1 round, le probe rend NON CONFRONTE -- il n'accuse NI le port NI ne verdit."""
    assert not_reached["step2"].get("ok") is None
    assert not_reached["step3b"].get("ok") is None
    assert "MONTAGE NON ATTEINT" in (not_reached["step2"].get("skipped") or "")
    assert not_reached["not_confronted"], (
        "le verdict ne signale AUCUNE etape non confrontee alors que le regime n'est pas atteint")
    # `ok` reste vrai (rien n'a echoue) mais la liste `not_confronted` porte rc 2 cote CLI.
    assert not_reached.get("ok") is True


# --- E : la forme d'arrondi de 1202, enfin confrontable ------------------------------------------

def test_p344_uses_the_nc_oracle_for_1202(p344_nc):
    assert p344_nc.get("oracle") == "nc", (
        "probe_344 n'a pas commute sur ncPlaybookPredict : il mesurerait aiPlaybookPredict, "
        "structurellement muet sur un NonComparable")
    for k in ("a", "b"):
        arm = p344_nc["arms"][k]
        assert not arm.get("error"), "bras %s KO : %s" % (k, arm["error"])
        assert (arm.get("regime") or {}).get("reached"), (
            "bras %s : l'anneau n'a pas mis la cible a distance 1 (%s)" % (k, arm.get("regime")))


def test_p344_both_arms_are_driven_and_discriminate(p344_nc):
    a, b = p344_nc["arms"]["a"], p344_nc["arms"]["b"]
    assert a["sum_mod4"] == 3 and b["sum_mod4"] == 1, (a["sum"], b["sum"])
    for k in ("a", "b"):
        assert p344_nc["arms"][k]["discriminates"], (
            "bras %s : les quatre variantes coincident, il ne prouve rien" % k)


def test_p344_shipped_code_matches_native_and_selects_trunc(p344_nc):
    """Le verdict de fond : le port LIVRE egale le natif sur les deux bras, et la seule variante
    nulle sur les deux est `trunc` -- ce que le registre prevoit pour la famille (b)."""
    for k in ("a", "b"):
        arm = p344_nc["arms"][k]
        assert arm["shipped_ok"], (
            "bras %s : port LIVRE %s vs natif %s (minDmg=%d maxDmg=%d somme=%d)"
            % (k, arm["shipped"], arm["native"], arm["minDmg"], arm["maxDmg"], arm["sum"]))
    assert p344_nc["nul_on_both_arms"] == ["trunc"], p344_nc["nul_on_both_arms"]
    assert p344_nc["expected_variant"] == "trunc"
    assert p344_nc.get("ok") is True


def test_to_even_is_wrong_for_1202(p344_nc):
    """Mutation ciblee : sur le bras `3 mod 4`, le demi-vers-le-pair s'ecarte du natif. Aligner
    `1202` sur l'autre famille serait une REGRESSION -- et elle est desormais VISIBLE."""
    a = p344_nc["arms"]["a"]
    assert a["match"]["trunc"] and not a["match"]["to_even"], (
        "to_even=%s trunc=%s natif=%s" % (a["ports"]["to_even"], a["ports"]["trunc"], a["native"]))
