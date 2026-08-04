"""LIVE #433-r4-r2-r1-r1-c -- les TROIS gates CASTER, confrontes SUR DEUX BRAS, sur DEUX kits.

LE DISCRIMINANT, ENONCE AVANT LA MESURE. `IdunBattle.Core.Services.AttackQuery$$
GetAllTilesInAbilityRange` (surcharge a 4 arguments) rend un ensemble VIDE quand l'un de ses trois
gates mord : slot 0x14 `AActiveAbility$$CanStillBeUsed`, slot 0x13 `AActiveAbility$$IsDisabled`,
puis `AttackQuery$$GetInvalidCasterReason`. Pour prouver qu'un port GATE -- et non qu'il REFUSE --
il faut les DEUX bras ; pour prouver qu'il gate au bon ENDROIT, il faut deux gates DIFFERENTS.

    `darkaTerminator` : arme de MELEE (1) + `PlasmaCannon` (1150) de zone 3.
        Gate arme par `constants.initialCooldownTurns = 1` -> c'est la marche (d) de
        `GetInvalidCasterReason` (`get_CanCurrentlyBeUsed`, terme `RemainingCooldownTurns`) ;
        il s'eteint tout seul, sans qu'on touche a l'unite.        1  ->  3

    `tauMarksman` : arme A DISTANCE (3) + `SeekerMissileFrequencyLock` (1069) de zone 5.
        Gate arme en faisant CASTER l'ability : sans `constants.cooldownTurns`, le tail de
        `CanStillBeUsed` se reduit a `amountOfTimesAlreadyUsed == 0` -> c'est le SLOT 0x14, et le
        champ `cooldown` reste `null` (la mesure separe donc bien les deux gates).  5  ->  3

Les trois ports imaginables se separent sur CHAQUE kit :
    correct         -> bloque != temoin, aux deux valeurs attendues
    ne gate jamais  -> temoin dans les deux bras   (echoue sur le bras BLOQUE)
    gate tout       -> portee d'ARME dans les deux (echoue sur le TEMOIN)

⚠ Le regime n'est DEGENERE sur aucun des deux : « zone = portee d'arme » est FAUX sur les deux
temoins (3 != 1 et 5 != 3). Et la CONTRE-EPREUVE est jouee ici meme, sur la mesure DEJA PRISE : on
rejoue le bras bloque avec le port PRIVE de son canal -- le port d'AVANT cette tranche -- et on
exige qu'il sur-couvre.

L'oracle est le NATIF CONTRE LUI-MEME : la partition qu'induit
`BattleQuery$$IsTileInRangeOfAnyAbility` sur le sweep d'`EarlyWarningOverridePlaybook`
(`bonus = util + 10*d(P,E)` vaut `0` en portee, `50` hors portee), avec le verrou « exactement UN
ennemi vivant » sans lequel elle n'est attribuable a aucun kit.

BORNE ASSUMEE, mesuree et NON introduite par cette tranche : quelques faux POSITIFS subsistent dans
les deux bras (residu `#433-r4-r2-r1-r2`, le 2e predicat de `GetPossibleTargetsForOptions` qui
retire les tuiles obscurcies par le terrain). Ce n'est PAS le gate dynamique : ni `PlasmaCannon` ni
`SeekerMissileFrequencyLock` ne surchargent `klass+0x478` (egalite du pointeur de slot avec
`AActiveAbility`, lue au runtime). Le test garde qu'ils ne s'AGGRAVENT pas et que le bras bloque
n'en cree AUCUN nouveau.

Detail : `docs/rl/case-433-r4-r2-r1-r2-portees.md` §8. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_433_r4_r2_r1_r1_c_caster_gates as PROBE

KITS = sorted(PROBE.KITS)


def _measure(enemy: str) -> dict:
    res = PROBE.step_arms(verbose=True, enemy=enemy)
    if "error" in res:
        pytest.fail("montage %s non installe : %s" % (enemy, res["error"]), pytrace=False)
    return res


@pytest.fixture(scope="module")
def measures(live_session) -> dict:
    return {k: _measure(k) for k in KITS}


@pytest.mark.parametrize("kit", KITS)
def test_the_two_arms_are_two_states_of_the_same_unit(measures, kit):
    """Sans cette garde, les deux bras pourraient etre deux MONTAGES differents -- et la
    comparaison ne dirait plus rien. Meme runner, meme tuile ennemie, meme sweep ; seul l'etat de
    l'ability gatee change."""
    res = measures[kit]
    b, t = res["arms"]["bloque"], res["arms"]["temoin"]
    aid = res["ability"]
    assert b["sweep"] == t["sweep"], "le sweep a change entre les deux bras"
    assert len(b["sweep"]) >= 30, "sweep trop court pour separer les deux rayons"
    from engine.services import ability_caster_gates as acg
    assert acg.can_currently_be_used(b["state"][aid]) is False
    assert acg.can_currently_be_used(t["state"][aid]) is True


@pytest.mark.parametrize("kit", KITS)
def test_blocked_arm_falls_to_the_expected_reach(measures, kit):
    """LE LIVRABLE. Gate arme -> le natif ne garde que ce qui n'est pas gate, et le port aussi.
    Avant cette tranche il rendait la zone du TEMOIN dans les deux bras."""
    res = measures[kit]
    b = res["arms"]["bloque"]
    assert b["reach"] == PROBE.KITS[kit]["bloque"]
    assert b["natif_dmax"] == PROBE.KITS[kit]["bloque"], \
        "le natif lui-meme doit s'arreter la : %r" % (b["natif_dmax"],)
    assert b["fn"] == [], "le port ne doit RIEN rater : un gate ne peut que RETRECIR"


@pytest.mark.parametrize("kit", KITS)
def test_witness_arm_still_reaches_the_ability_zone(measures, kit):
    """LE TEMOIN. Sans lui, un port qui REFUSE tout passerait le test precedent."""
    res = measures[kit]
    t = res["arms"]["temoin"]
    assert t["reach"] == PROBE.KITS[kit]["temoin"]
    assert t["natif_dmax"] == PROBE.KITS[kit]["temoin"]
    assert t["fn"] == [], "le port ne doit RIEN rater quand l'ability est prete"


@pytest.mark.parametrize("kit", KITS)
def test_the_slice_creates_no_new_false_positive(measures, kit):
    """La PROPRIETE de la tranche, et non un chiffre : un gate ne peut que RETIRER de la zone.
    Les faux positifs du bras bloque doivent donc etre INCLUS dans ceux du temoin -- si le bras
    bloque en creait un, c'est que le port aurait ELARGI en gatant, ce qui n'a aucun sens."""
    res = measures[kit]
    b, t = res["arms"]["bloque"], res["arms"]["temoin"]
    new = {tuple(P) for P in b["fp"]} - {tuple(P) for P in t["fp"]}
    assert new == set(), "faux positifs CREES par le gate : %r" % (sorted(new),)
    assert len(t["fp"]) <= 2, "residu -r1-r2 aggrave sur %s : %r" % (kit, t["fp"])


@pytest.mark.parametrize("kit", KITS)
def test_the_regime_is_not_degenerate(measures, kit):
    """ANTI-COINCIDENCE. Les deux bras doivent RENDRE DES VALEURS DIFFERENTES, et la valeur du
    TEMOIN doit differer de la portee d'ARME -- sinon « zone = portee d'arme » expliquerait tout."""
    from engine.runner.abilities.targeting import unit_weapon_range
    res = measures[kit]
    b, t = res["arms"]["bloque"], res["arms"]["temoin"]
    assert b["reach"] != t["reach"], "les deux bras ne separent rien"
    assert t["reach"] != unit_weapon_range(kit, None), \
        "sur ce kit, zone == portee d'arme : l'accord ne prouverait rien"


@pytest.mark.parametrize("kit", KITS)
def test_counter_proof_the_ungated_port_fails_the_blocked_arm(measures, kit):
    """CONTRE-EPREUVE, sur la mesure DEJA PRISE (aucun runner supplementaire) : on rejoue le bras
    bloque avec le port PRIVE de son canal d'etat -- c'est-a-dire le port d'AVANT cette tranche --
    et on exige qu'il produise des faux positifs. Un test qui ne verifie pas cela ne distingue pas
    « mon gate marche » de « le montage ne gate rien »."""
    from engine.services import ability_range as ar
    res = measures[kit]
    b = res["arms"]["bloque"]
    Y = tuple(res["Y"])
    elev = res["elev"] or None
    inr = {tuple(P) for P in b["in_range"]}
    naive = {tuple(P) for P in b["sweep"]
             if ar.is_tile_in_range_of_any_ability(Y, tuple(P), kit, elev_by_pos=elev)}
    excess = naive - inr
    assert len(excess) >= 6, \
        "le port SANS canal devrait sur-couvrir nettement ; il n'a que %d tuiles de trop -- le " \
        "montage ne gate peut-etre rien" % len(excess)


def test_the_two_kits_arm_two_DIFFERENT_gates(measures):
    """Ce que la parametrisation seule ne dirait pas : les deux kits n'exercent PAS le meme gate.
    `darkaTerminator` passe par le champ `RemainingCooldownTurns` (marche d de
    `GetInvalidCasterReason`) ; `tauMarksman` par `CanStillBeUsed` (slot 0x14), son `cooldown`
    restant `null`. Un port qui ne lirait qu'UN des deux champs passerait la moitie du fichier."""
    from engine.services import ability_caster_gates as acg
    term = measures["darkaTerminator"]
    mark = measures["tauMarksman"]
    st_term = term["arms"]["bloque"]["state"][term["ability"]]
    st_mark = mark["arms"]["bloque"]["state"][mark["ability"]]
    assert st_term.get("usable") is True and (st_term.get("cooldown") or 0) >= 1, \
        "darkaTerminator doit etre gate par le COOLDOWN seul : %r" % (st_term,)
    assert st_mark.get("usable") is False and st_mark.get("cooldown") is None, \
        "tauMarksman doit etre gate par CanStillBeUsed seul : %r" % (st_mark,)
    assert acg.caster_gate_reason(term["ability"], st_term) == acg.REASON_CAN_CURRENTLY_BE_USED
    assert acg.caster_gate_reason(mark["ability"], st_mark) == acg.REASON_CAN_STILL_BE_USED
