"""#350 -- les formes de moyenne LUES par #350, confrontees au LIVE.

#344 avait mesure UNE ability par forme (FlailSwing / PlasmaCannon), toutes deux atteignant leur
moyenne par le MEME corps deduplique. #350 a lu trois AUTRES voies vers la meme moyenne, et cette
garde en confronte les deux qui ont un porteur au pool :

  a2 -- `<X>Ability$$GetDamage(state, isPrediction)` (corps deduplique etiquete
        `IdunBattleLogic.Entities.Abilities.Active.Loki.StaffOfStarsAbility$$GetDamage`), dont les
        ONZE call-sites de playbook posent `isPrediction = 1` -> branche `Half(Sum(...), 0)`.
        Montages : `LightOfSanguinius` (1177, bloodDante) et `LeadingTheCharge` (1204, astraDreir).
  a3 -- corps PROPRE de l'ability : `SpiritLeechAbility$$GetAttackDamage` -> `MinMaxDamage(true)`.
        Montage : `SpiritLeech` (1104, tyranNeurothrope).

Ces trois abilities etaient NON LUES avant #350 : le port leur rendait la TRONCATURE. La garde
verrouille que le natif les fait MONTER, donc que l'inscription au registre (a) est load-bearing --
et pas un alignement decoratif. Le montage, les deux leviers de pilotage (parite via
`--unit-stat ActiveAbilityLevel`, survie de l'ecart via `--armor-target 0`) et le refus de verdir
sur un bras muet sont ceux de `probe_344_ability_damage_average.py` (en-tete).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_344_ability_damage_average as P                 # noqa: E402
from engine.entities.abilities.active_ability import (       # noqa: E402
    _PREDICTION_MINMAX_AVERAGE, _A_VIA_STAFF_OF_STARS_GET_DAMAGE, _A_VIA_OWN_ABILITY_BODY)

# Un montage par VOIE lue en #350, restreint aux porteurs presents dans `rl_duel build --list-pool`.
# `armor_target = 0` : sans ca la reduction d'armure absorbe l'ecart d'une unite et le bras devient
# muet (piege #339 sec.4, re-observe par #344 sur BringerOfDespair).
MONTAGES = {
    "a2_light_of_sanguinius": dict(caster="bloodDante", ability=1177,
                                   ability_name="LightOfSanguinius", board="MC1_67", center=(3, 4),
                                   lvl_a=7, lvl_b=1, armor_target=0, seed=35001),
    "a2_leading_the_charge": dict(caster="astraDreir", ability=1204,
                                  ability_name="LeadingTheCharge", board="MC1_67", center=(3, 4),
                                  lvl_a=2, lvl_b=4, armor_target=0, seed=35011),
    "a3_spirit_leech": dict(caster="tyranNeurothrope", ability=1104, ability_name="SpiritLeech",
                            board="MC1_67", center=(3, 4), lvl_a=4, lvl_b=3, armor_target=0,
                            seed=35021),
}

SUBCHAIN = {"a2_light_of_sanguinius": _A_VIA_STAFF_OF_STARS_GET_DAMAGE,
            "a2_leading_the_charge": _A_VIA_STAFF_OF_STARS_GET_DAMAGE,
            "a3_spirit_leech": _A_VIA_OWN_ABILITY_BODY}


@pytest.fixture(scope="module")
def measured():
    out = {}
    for key, m in MONTAGES.items():
        sf = PYDIR.parents[1] / "logs" / ("t350_%s.json" % key)
        r = P.run(state_file=str(sf), verbose=False, **m)
        for k, arm in (r.get("arms") or {}).items():
            assert not arm.get("error"), "%s bras %s KO : %s" % (key, k, arm["error"])
        out[key] = r
    return out


def test_each_montage_covers_the_sub_chain_it_claims():
    """Pre-condition : chaque montage porte bien l'id de la voie qu'il pretend confronter, et cet
    id est dans le registre (a). Sans ca la mesure ne dirait rien de la lecture #350."""
    for key, m in MONTAGES.items():
        aid = m["ability"]
        assert aid in SUBCHAIN[key], "%s : %d n'est plus dans sa sous-chaine" % (key, aid)
        assert aid in _PREDICTION_MINMAX_AVERAGE


def test_both_parities_are_driven(measured):
    """Les deux bras sont dans le regime ANNONCE et le niveau EFFECTIF est celui demande."""
    for key, out in measured.items():
        assert out["regimes_ok"], "%s : parites non pilotees (a=%s mod 4, b=%s mod 4)" % (
            key, out["arms"]["a"].get("sum_mod4"), out["arms"]["b"].get("sum_mod4"))
        for k in ("a", "b"):
            arm = out["arms"][k]
            assert arm["level_eff"] == arm["level_asked"], (
                "%s bras %s : niveau demande %d, effectif %d -- la mesure porterait sur un autre "
                "couple" % (key, k, arm["level_asked"], arm["level_eff"]))


def test_every_arm_discriminates(measured):
    """Un bras ou les quatre variantes coincident ne prouve RIEN : il fait echouer, pas verdir."""
    for key, out in measured.items():
        for k in ("a", "b"):
            assert out["arms"][k]["discriminates"], (
                "%s bras %s : les quatre variantes rendent la MEME prediction -- ecart absorbe en "
                "aval, ce bras est muet" % (key, k))


def test_shipped_code_matches_native_on_both_arms(measured):
    """Le code LIVRE (aucun patch) egale le natif bras par bras."""
    for key, out in measured.items():
        for k in ("a", "b"):
            arm = out["arms"][k]
            assert arm["shipped_ok"], (
                "%s bras %s : le port LIVRE rend %s la ou le natif rend %s (minDmg=%d maxDmg=%d, "
                "somme %d = %d mod 4)" % (key, k, arm["shipped"], arm["native"], arm["minDmg"],
                                          arm["maxDmg"], arm["sum"], arm["sum_mod4"]))


def test_truncation_is_refused_by_the_native_on_all_three(measured):
    """Le coeur de #350 : sur le bras `3 mod 4`, la TRONCATURE -- ce que le port rendait AVANT
    d'avoir lu ces trois voies -- s'ecarte du natif. Retirer l'un de ces ids du registre re-creerait
    exactement cet ecart."""
    for key, out in measured.items():
        a = out["arms"]["a"]
        assert out["nul_on_both_arms"] == ["to_even"], (
            "%s : variantes nulles sur les deux bras = %s, attendu ['to_even']"
            % (key, out["nul_on_both_arms"]))
        assert not a["match"]["trunc"], (
            "%s bras a : la troncature %s egale le natif %s -- ce montage ne demontre plus que "
            "l'inscription au registre (a) est load-bearing" % (key, a["ports"]["trunc"], a["native"]))
