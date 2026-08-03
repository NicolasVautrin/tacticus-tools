"""LIVE #433-r4-r2-r1 -- la BRANCHE A d'`EarlyWarningOverridePlaybook`, confrontee TUILE PAR TUILE.

L'ORACLE EST LE NATIF CONTRE LUI-MEME. On ne compare pas deux utilites : on lit la PARTITION que
`IdunBattle.Core.Services.BattleQuery$$IsTileInRangeOfAnyAbility` induit sur le sweep, en isolant
son terme (`bonus = util + 10*Sum_E d(P,E)`, qui vaut `0` en portee et `50` hors portee), puis on la
compare au mirror `engine.services.ability_range.is_tile_in_range_of_any_ability`.

VERROU DE MONTAGE : la partition n'est attribuable qu'a UN ennemi vivant -- chaque ennemi verse son
propre `+50/0` ET son propre `-10*d`. Le probe REFUSE un montage impur, et c'est ce refus qui a
invalide une premiere mesure (`genesMagus` amene DEUX summons au spawn, `genesSmnDecoy` et
`genesSmnNeophyte` : la partition lue etait un melange de trois kits).

TROIS KITS, trois proprietes DIFFERENTES :
  * `tauMarksman` -- le cas que la tranche `-r1` corrigeait. Sa zone porte a 5 (l'ability
    `SeekerMissileFrequencyLock`, `RANGE_FROM_CONFIG`, `constants.range = 5`) alors que son arme a
    distance ne porte qu'a 3 : le port d'AVANT, qui prenait la portee d'ARME, se trompait sur
    l'anneau `4 <= d <= 5`. Attendu : accord EXACT, dans les deux sens.
  * `bloodDante` -- le residu `-r1-r1`, FERME depuis. `LightOfSanguinius` porte le preset
    `RANGE_WHOLE_BOARD` (le MEME que `LeadingTheCharge` d'`astraDreir`) et les deux kits rendent
    pourtant des zones DIFFERENTES : le discriminant est le slot de vtable `klass+0x478`
    (`GetDynamicInvalidTargetReason`), invoque par le 3e predicat de
    `TargetingQuery$$GetPossibleTargetsForOptions` en `RemoveAll`. Celui de `LightOfSanguinius` est
    `GetFreeAdjacentTiles(targetTiles).Any(t => GetDistance(t, casterTiles) <= config.range)`, d'ou
    un rayon `config.range + 1 = 6`. Le port passe de **18 faux negatifs** a **0**, au prix de deux
    faux POSITIFS residuels a `d = 6` -- attribues, mesures, et gardes ici comme tels.
  * `darkaAsmodai` -- l'autre moitie du meme residu. `ExemplarOfHate` est whole-board et ne
    surcharge PAS le gate : sa zone est le plateau ENTIER (`GetAllTiles()`). Le port rendait `None`,
    soit **40 faux negatifs sur 40** ; il est desormais EXACT.

⚠ Ce fichier ne peut PAS coincider par hasard : les trois kits ont une arme de MELEE ou une portee
d'arme STRICTEMENT inferieure a leur zone d'ability, donc « zone = portee d'arme » y est faux.

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


@pytest.fixture(scope="module")
def asmodai(live_session) -> dict:
    return _measure("darkaAsmodai")


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


def test_dante_whole_board_zone_is_bounded_by_its_dynamic_gate(dante):
    """`#433-r4-r2-r1-r1`, FERME. `LightOfSanguinius` est whole-board, donc sa zone de BASE est le
    plateau entier ; ce qui la borne est son gate `GetDynamicInvalidTargetReason` --
    `GetFreeAdjacentTiles(targetTiles).Any(t => GetDistance(t, casterTiles) <= config.range)`.

    D'ou un rayon `config.range + 1 = 6`, ET la porte d'elevation d'`IterateAdjacentTiles`. Le port
    rendait 18 faux negatifs ; il est desormais EXACT dans les deux sens."""
    assert dante["reach"] == 6, "config.range = 5, +1 pour le voisinage de la cible"
    assert dante["faux_positifs"] == []
    assert dante["faux_negatifs"] == []
    assert dante["exact"] is True


def test_dante_zone_is_not_its_weapon_range(dante):
    """ANTI-COINCIDENCE. `bloodDante` n'a qu'une arme de MELEE : « zone = portee d'arme » y donnerait
    1. Sans cette garde, l'accord des autres kits pourrait venir d'un modele degenere."""
    from engine.playbook.noncomparable.early_warning_override import _ranged_weapon_threshold
    assert _ranged_weapon_threshold("bloodDante") == 1
    assert dante["reach"] == 6


def test_asmodai_whole_board_without_gate_covers_the_board(asmodai):
    """L'autre moitie du residu. `ExemplarOfHate` est whole-board et ne SURCHARGE PAS le gate (fait
    runtime : egalite du pointeur de slot `klass+0x478` avec celui d'`AActiveAbility`), donc sa zone
    est `GetAllTiles()`. Le natif rend « en portee » sur TOUT le sweep -- le port rendait `None`,
    soit 40 faux negatifs sur 40."""
    assert asmodai["faux_positifs"] == []
    assert asmodai["faux_negatifs"] == []
    assert asmodai["exact"] is True
    from engine.services import ability_range as ar
    assert ar.unit_threat_reach("darkaAsmodai") == ar.WHOLE_BOARD_REACH
