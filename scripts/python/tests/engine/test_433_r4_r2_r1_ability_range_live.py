"""LIVE #433-r4-r2-r1 -- la BRANCHE A d'`EarlyWarningOverridePlaybook`, confrontee TUILE PAR TUILE.

L'ORACLE EST LE NATIF CONTRE LUI-MEME. On ne compare pas deux utilites : on lit la PARTITION que
`IdunBattle.Core.Services.BattleQuery$$IsTileInRangeOfAnyAbility` induit sur le sweep, en isolant
son terme (`bonus = util + 10*Sum_E d(P,E)`, qui vaut `0` en portee et `50` hors portee), puis on la
compare au mirror `engine.services.ability_range.is_tile_in_range_of_any_ability`.

VERROU DE MONTAGE : la partition n'est attribuable qu'a UN ennemi vivant -- chaque ennemi verse son
propre `+50/0` ET son propre `-10*d`. Le probe REFUSE un montage impur, et c'est ce refus qui a
invalide une premiere mesure (`genesMagus` amene DEUX summons au spawn, `genesSmnDecoy` et
`genesSmnNeophyte` : la partition lue etait un melange de trois kits).

DEUX KITS, deux proprietes DIFFERENTES :
  * `tauMarksman` -- le cas que cette tranche corrige. Sa zone porte a 5 (l'ability
    `SeekerMissileFrequencyLock`, `RANGE_FROM_CONFIG`, `constants.range = 5`) alors que son arme a
    distance ne porte qu'a 3 : le port d'AVANT, qui prenait la portee d'ARME, se trompait sur
    l'anneau `4 <= d <= 5`. Attendu : accord EXACT, dans les deux sens.
  * `bloodDante` -- le RESIDU, mesure plutot qu'affirme. Son ability `LightOfSanguinius` porte le
    preset `RANGE_WHOLE_BOARD` (le MEME que `LeadingTheCharge` d'`astraDreir`), et pourtant les
    deux kits rendent des zones DIFFERENTES : le discriminant est donc EN AVAL du `TargetingRange`.
    Le port ne l'elargit pas -> ce qu'on garantit ici est la BORNE INFERIEURE (zero faux positif),
    pas l'exactitude.

Detail : `docs/rl/case-433-r4-r2-r1-r2-portees.md`. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_433_r4_r2_r1_ability_range as PROBE


def _measure(enemy: str) -> dict:
    res = PROBE.step_kit(verbose=True, enemy=enemy)
    if "error" in res:
        pytest.fail("montage %s non installe : %s" % (enemy, res["error"]), pytrace=False)
    return res


@pytest.fixture(scope="module")
def marksman(live_session) -> dict:
    return _measure("tauMarksman")


@pytest.fixture(scope="module")
def dante(live_session) -> dict:
    return _measure("bloodDante")


def test_marksman_sweep_is_large_enough_to_be_discriminant(marksman):
    """Sans un sweep qui DEPASSE la portee, l'accord serait vide de sens : le montage historique de
    `#433-r4-r2 --step partition` restait a `d <= 4`, donc entierement DANS la zone."""
    assert marksman["n_sweep"] >= 30, "sweep trop court : %r" % (marksman["n_sweep"],)
    assert marksman["reach"] == 5


def test_marksman_zone_is_exact_in_both_directions(marksman):
    """Le mirror doit rendre la MEME partition que le natif -- ni faux positif, ni faux negatif."""
    assert marksman["faux_positifs"] == []
    assert marksman["faux_negatifs"] == []
    assert marksman["exact"] is True


def test_marksman_ability_range_beats_the_weapon_range(marksman):
    """La regression que cette tranche ferme : la zone porte a 5 alors que l'arme a distance ne
    porte qu'a 3. Un port qui reprendrait la portee d'ARME rendrait 2 anneaux de faux negatifs."""
    from engine.playbook.noncomparable.early_warning_override import _ranged_weapon_threshold
    assert _ranged_weapon_threshold("tauMarksman") == 3
    assert marksman["reach"] > _ranged_weapon_threshold("tauMarksman")


def test_dante_residual_is_a_lower_bound_not_an_error(dante):
    """RESIDU MESURE, pas suppose : `LightOfSanguinius` est whole-board et le port ne l'elargit pas.
    Ce qui doit tenir, c'est le SENS de l'ecart -- le port ne declare JAMAIS « en portee » une tuile
    que le natif exclut (zero faux positif). L'inverse (faux negatifs) est l'ecart assume."""
    assert dante["faux_positifs"] == [], \
        "le port a ELARGI la zone : la borne inferieure est rompue (%r)" % (dante["faux_positifs"],)
    assert dante["faux_negatifs"], \
        "l'ecart a DISPARU : si la zone whole-board est devenue derivable, re-lire le residu"
