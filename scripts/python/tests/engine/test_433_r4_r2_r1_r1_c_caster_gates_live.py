"""LIVE #433-r4-r2-r1-r1-c -- les TROIS gates CASTER, confrontes SUR DEUX BRAS.

LE DISCRIMINANT, ENONCE AVANT LA MESURE. `IdunBattle.Core.Services.AttackQuery$$
GetAllTilesInAbilityRange` (surcharge a 4 arguments) rend un ensemble VIDE quand l'un de ses trois
gates mord : slot 0x14 `AActiveAbility$$CanStillBeUsed`, slot 0x13 `AActiveAbility$$IsDisabled`,
puis `AttackQuery$$GetInvalidCasterReason`. Pour prouver qu'un port GATE -- et non qu'il REFUSE --
il faut les deux bras :

    `darkaTerminator` : arme de MELEE (Range 1) + `PlasmaCannon` (1150) de zone 3,
                        `initialCooldownTurns = 1`

  * bras BLOQUE  (`cooldown = 1`, les deux premiers tours) : le natif ne laisse que l'attaque
    normale -> « en portee » pour `d <= 1` SEULEMENT ;
  * bras TEMOIN  (`cooldown = null`, meme unite, MEME tuile, MEME sweep)                -> `d <= 3`.

Les trois ports imaginables se separent tous :
    correct         -> 1 puis 3
    ne gate jamais  -> 3 puis 3   (echoue sur le bras bloque)
    gate tout       -> 1 puis 1   (echoue sur le TEMOIN)

⚠ Le regime n'est pas DEGENERE : sur ce kit « zone = portee d'arme » est FAUX quand l'ability est
prete (3 != 1), donc l'accord du temoin ne peut pas venir d'une coincidence de modeles. Et la
CONTRE-EPREUVE est jouee ici meme : on rejoue le bras bloque SANS le canal d'etat, et on exige que
le port d'avant cette tranche y produise des faux positifs.

L'oracle est le NATIF CONTRE LUI-MEME : la partition qu'induit
`BattleQuery$$IsTileInRangeOfAnyAbility` sur le sweep d'`EarlyWarningOverridePlaybook`
(`bonus = util + 10*d(P,E)` vaut `0` en portee, `50` hors portee), avec le verrou « exactement UN
ennemi vivant » sans lequel elle n'est attribuable a aucun kit.

Detail : `docs/rl/case-433-r4-r2-r1-r2-portees.md` §8. ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
import probe_433_r4_r2_r1_r1_c_caster_gates as PROBE


@pytest.fixture(scope="module")
def arms(live_session) -> dict:
    res = PROBE.step_arms(verbose=True)
    if "error" in res:
        pytest.fail("montage non installe : %s" % res["error"], pytrace=False)
    return res


def test_the_two_arms_are_really_two_states_of_the_same_unit(arms):
    """Sans cette garde, les deux bras pourraient etre deux MONTAGES differents -- et la
    comparaison ne dirait plus rien. Meme runner, meme tuile ennemie, meme sweep ; seul l'etat de
    `PlasmaCannon` change."""
    b, t = arms["arms"]["bloque"], arms["arms"]["temoin"]
    assert b["sweep"] == t["sweep"], "le sweep a change entre les deux bras"
    assert len(b["sweep"]) >= 30, "sweep trop court pour separer un rayon 1 d'un rayon 3"
    assert (b["state"][PROBE.GATED_ABILITY]["cooldown"] or 0) >= 1
    assert (t["state"][PROBE.GATED_ABILITY]["cooldown"] or 0) == 0


def test_blocked_arm_is_exact_in_both_directions(arms):
    """LE LIVRABLE. Gate arme -> le natif ne garde que l'attaque normale (`d <= 1`), et le port
    aussi. Avant cette tranche il rendait le disque de rayon 3 : 12 faux positifs sur 38."""
    b = arms["arms"]["bloque"]
    assert b["reach"] == 1, "seule l'attaque normale (arme de MELEE) doit subsister"
    assert b["natif_dmax"] == 1, "le natif lui-meme ne porte plus au-dela de d=1"
    assert b["fp"] == []
    assert b["fn"] == []


def test_witness_arm_still_reaches_the_ability_zone(arms):
    """LE TEMOIN. Sans lui, un port qui REFUSE tout passerait le test precedent. Gate eteint, la
    zone remonte a 3 (`PlasmaCannon`, `constants.range = 3`) -- cote natif COMME cote port."""
    t = arms["arms"]["temoin"]
    assert t["reach"] == 3
    assert t["natif_dmax"] == 3
    assert t["fn"] == [], "le port ne doit RIEN rater quand l'ability est prete"


def test_witness_arm_residual_false_positives_are_bounded_and_on_the_outer_ring(arms):
    """BORNE, pas un accord. Il reste des faux positifs sur l'anneau EXTERIEUR du temoin : ce n'est
    PAS le gate dynamique (`PlasmaCannonAbility` ne surcharge pas `klass+0x478` -- egalite du
    pointeur de slot avec `AActiveAbility`, lue au runtime), c'est le 2e predicat de
    `TargetingQuery$$GetPossibleTargetsForOptions` (`b__1`, tuiles obscurcies par le terrain),
    residu `#433-r4-r2-r1-r2`. Cette tranche ne le touche pas : le bras temoin est mot pour mot
    celui d'avant elle."""
    t = arms["arms"]["temoin"]
    Y = tuple(arms["Y"])
    assert len(t["fp"]) <= 2, "residu -r1-r2 aggrave : %r" % (t["fp"],)
    off = [P for P in t["fp"] if hexgeo.distance(tuple(P), Y) != t["reach"]]
    assert off == [], "faux positifs HORS de l'anneau exterieur -> autre cause : %r" % (off,)


def test_the_regime_is_not_degenerate(arms):
    """ANTI-COINCIDENCE. Les deux bras doivent RENDRE DES VALEURS DIFFERENTES, et la valeur du
    temoin doit differer de la portee d'ARME -- sinon « zone = portee d'arme » expliquerait tout."""
    from engine.runner.abilities.targeting import unit_weapon_range
    b, t = arms["arms"]["bloque"], arms["arms"]["temoin"]
    assert b["reach"] != t["reach"], "les deux bras ne separent rien"
    assert unit_weapon_range(PROBE.ENEMY, None) == 1
    assert t["reach"] != unit_weapon_range(PROBE.ENEMY, None)


def test_counter_proof_the_ungated_port_fails_the_blocked_arm(arms):
    """CONTRE-EPREUVE, sur la mesure DEJA PRISE (aucun runner supplementaire) : on rejoue le bras
    bloque avec le port PRIVE de son canal d'etat -- c'est-a-dire le port d'AVANT cette tranche --
    et on exige qu'il produise des faux positifs. Un test qui ne verifie pas cela ne distingue pas
    « mon gate marche » de « le montage ne gate rien »."""
    from engine.services import ability_range as ar
    b = arms["arms"]["bloque"]
    Y = tuple(arms["Y"])
    inr = {tuple(P) for P in b["in_range"]}
    elev = {tuple(k) if isinstance(k, list) else k: v for k, v in (arms["elev"] or {}).items()}
    naive = {tuple(P) for P in b["sweep"]
             if ar.is_tile_in_range_of_any_ability(Y, tuple(P), PROBE.ENEMY, elev_by_pos=elev)}
    assert naive - inr, "le port SANS canal devrait sur-couvrir : le montage ne gate rien"
    assert len(naive - inr) >= 6, "sur-couverture trop faible pour etre discriminante : %d" \
                                  % len(naive - inr)
