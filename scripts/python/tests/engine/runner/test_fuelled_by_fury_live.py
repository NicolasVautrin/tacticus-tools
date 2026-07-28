"""#1323 -- GARDE des DEUX etages de `FuelledByFury_ExtraDamage` (0x52b), le passif d'`ultraTitus`.

i2 : << Deals +153 Damage with all attacks **for each time a friendly Character has used an active
ability this battle**. >> Deux etages distincts, deux facons INDEPENDANTES de casser en silence :

  * ETAGE 1 -- le COMPTEUR (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    FuelledByFury_ExtraDamageAbility$$CreateTrigger` / `$$CreateBehaviour`) : `On(0xe=UnitPostAbility)
    & AreFriends(Owner, caster) & HasTrait(caster, Hero) & !HasTrait(caster, MachineOfWar) &
    IsActiveAbilityCountedAsUsed(false)` -> `If(HasEffect, IncreaseEffectLevel(+1), AddEffect(1323))`.
    Non porte : le niveau reste celui du seed (0 sur un runner frais) -> effet INERTE.
  * ETAGE 2 -- la MAGNITUDE (`IdunBattle.Entities.Effects.Loki.FuelledByFury_ExtraDamageEffect$$
    CreateEffectDamageBonusForAttack` = `ForAddition(get_OwnerIsCaster, GetCurrentExtraDamage())`,
    `GetCurrentExtraDamage` = `Multiply(ConfigVar(8=extraDmg), EffectLevel)`). Non portee : le niveau
    monte mais le degat ne bouge pas.

La PAIRE DE REGIMES `fury=0` / `fury=2` est ce qui separe les deux : `fury=0` n'exerce PAS l'etage 2
(l'effet est absent de Titus au deploiement), `fury=2` ne prouve PAS a lui seul que le compteur bouge.
Montage : `tests/engine/runner/_fuelled_by_fury_regime.py`. Sonde jumelle :
`scripts/python/probe_1323_fuelled_by_fury.py`.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from _fuelled_by_fury_regime import build_stage      # noqa: E402


@pytest.fixture(scope="module")
def fury_regime(build_runner, rpc):
    """Le montage complet joue UNE fois par module (build + geometrie drivee + les deux regimes)."""
    return build_stage(build_runner, rpc)


def test_fury_counter_accumulates_on_allied_active(fury_regime):
    """ETAGE 1 -- chaque active d'un HERO ALLIE incremente le stack de Titus, et le port produit le
    MEME niveau que le jeu sur le MEME vecteur `On(UnitPostAbility)`. Deux casts => 0 -> 1 -> 2 :
    un seul cast ne distinguerait pas << +1 par cast >> de << pose a 1 puis fige >>."""
    steps = fury_regime["steps"]
    assert len(steps) >= 2, "montage insuffisant : il faut >= 2 casts allies (%s)" % steps
    for s in steps:
        assert s["ok"], "cast allie refuse (%s / %s) : %s" % (s["caster"], s["ability"], s["raw"])
        assert s["n_events"] > 0, (
            "cast rendu ok=True mais SANS evenement = no-op silencieux (%s)" % s)
    assert [s["after_live"] for s in steps] == [1, 2], (
        "le jeu n'a pas accumule 0 -> 1 -> 2 : %s" % [(s["before"], s["after_live"]) for s in steps])
    for s in steps:
        assert s["after_off"] == s["after_live"], (
            "DESACCORD compteur port/live apres le cast %s de %s : port=%s live=%s"
            % (s["ability"], s["caster"], s["after_off"], s["after_live"]))


def test_fury_counter_ignores_the_carrier_own_normal_attack(fury_regime):
    """ETAGE 1, gate `IsActiveAbilityCountedAsUsed` -- l'attaque NORMALE emet elle aussi `On(0xe)`
    (`ability_type = 1013`, cf. `dispatch/attack.py`). Sans le gate, TOUTE attaque de TOUT hero allie
    ferait monter le compteur : c'est le faux-positif que ce test verrouille, des DEUX cotes."""
    a = fury_regime["a"]
    assert a["ok"], a.get("reason")
    assert a["fury_after_live"] == 0, (
        "le jeu a incremente FuelledByFury sur une attaque NORMALE (live=%s)" % a["fury_after_live"])
    assert a["fury_after_off"] == 0, (
        "le port a incremente FuelledByFury sur une attaque NORMALE (port=%s) -- le gate "
        "`!IsNormalAttack` a saute" % a["fury_after_off"])


def test_fury_counter_ignores_an_enemy_caster(fury_regime):
    """ETAGE 1, gate `AreFriends(Owner@0x148, caster@0x160)` -- le MEME vecteur `On(0xe)` emis avec un
    caster ENNEMI ne doit RIEN incrementer.

    PORTEE DE CE TEST, dite explicitement : c'est une garde du PORT, PAS une confrontation live -- le
    harnais ne sait pas faire caster une unite adverse (`applyAction` rend `ok=True, events=2, 0
    degat` = le no-op silencieux ; le controle positif de la meme passe, cast ALLIE a 21 evenements,
    montre que le harnais lui-meme fonctionne). Elle verrouille malgre tout le gate contre un retrait
    accidentel, qui serait sinon PERMISSIF et invisible."""
    if fury_regime["foe"] is None or fury_regime["foe_ability"] is None:
        pytest.skip("aucun ennemi porteur d'une active dans le montage")
    assert fury_regime["foe_level_after_off"] == fury_regime["foe_level_before"], (
        "le port a incremente FuelledByFury sur le cast d'un ENNEMI (%s, ability %s) : %s -> %s "
        "-- le gate `AreFriends` a saute"
        % (fury_regime["foe"], fury_regime["foe_ability"],
           fury_regime["foe_level_before"], fury_regime["foe_level_after_off"]))


def test_fury_damage_is_bit_exact_in_both_regimes(fury_regime):
    """ETAGE 2 -- MEME attaque normale rejouee offline sur le MEME MT, dans les DEUX regimes.
    `fury=0` est le TEMOIN (l'effet est absent : un port sans la classe d'effet le passe aussi) ;
    `fury=2` est la mesure (il ne passe QUE si la magnitude `extraDmg x level` est portee)."""
    a, b = fury_regime["a"], fury_regime["b"]
    assert a["ok"] and b["ok"], (a.get("reason"), b.get("reason"))
    assert a["fury"] == 0 and b["fury"] >= 2, (
        "la paire n'est plus discriminante (fury A=%s B=%s)" % (a["fury"], b["fury"]))
    assert len(a["live_ph"]) > 0 and len(b["live_ph"]) > 0, "aucun coup live capte"
    assert a["off_ph"] == a["live_ph"], (
        "TEMOIN fury=0 en desaccord (port %s vs live %s) : le montage lui-meme est casse, "
        "l'echec de `fury=2` ne serait pas imputable a FuelledByFury" % (a["off_ph"], a["live_ph"]))
    assert b["off_ph"] == b["live_ph"], (
        "DESACCORD a fury=%s : port %s vs live %s -- la magnitude `Multiply(ConfigVar(8=extraDmg), "
        "EffectLevel)` n'est pas (ou mal) portee" % (b["fury"], b["off_ph"], b["live_ph"]))


def test_fury_magnitude_matches_the_native_prediction_delta(fury_regime):
    """ETAGE 2, DECOMPOSE -- le delta de prediction NATIVE entre les deux regimes doit valoir
    exactement `nrHits x fury x round(extraDmg[ablvl] x multiplier/100)`. C'est la lecture par ETAGE
    de la magnitude (pas un scalaire fitte) : elle tombe si `extraDmg`, le niveau d'ability, le
    multiplier de rarete ou le facteur `EffectLevel` derapent. Le montage impose une ELEVATION EGALE
    entre le centre et le ring, sans quoi le +50 % d'elevation multiplierait le bonus additif."""
    p0, pN, b = fury_regime["pred0"], fury_regime["predN"], fury_regime["b"]
    if p0 is None or pN is None:
        pytest.skip("aiPredict indisponible sur ce runner")
    params = b.get("params")
    assert params, "l'effet 1323 n'est pas materialise offline au regime B : %s" % b
    level, ablvl, mult, base, per_stack = params
    assert base and per_stack, "magnitude non resolue (extraDmg base=%s per=%s)" % (base, per_stack)
    n_hits = len(b["live_ph"])
    expected = n_hits * level * per_stack
    assert (pN[0] - p0[0]) == expected and (pN[1] - p0[1]) == expected, (
        "delta de prediction live %s/%s != nrHits(%d) x fury(%d) x par-stack(%d) = %d "
        "[extraDmg[%s]=%s x multiplier %s%%]"
        % (pN[0] - p0[0], pN[1] - p0[1], n_hits, level, per_stack, expected, ablvl, base, mult))
