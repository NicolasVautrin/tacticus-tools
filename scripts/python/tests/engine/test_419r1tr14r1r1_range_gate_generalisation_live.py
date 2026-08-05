"""#419-r1-tr14-r1-r1 -- la porte de PORTEE d'arme, GENERALISEE a un porteur MIXTE.

Le residu s'est ouvert sur `templNpc1Initiate`, un porteur MELEE SEUL : la porte s'y reduit a
« adjacent ou rien », et un accord y laisserait ouverte la question du BOUNDARY. Cette garde la
confronte sur `adeptCanoness` (HERO du pool, `Chain` melee 3 coups + `Bolter` portee 2, 2 coups),
ou les TROIS issues de
`IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack(attacker,
attackerTiles, target)` sont exercees ET distinguables :

    d = 1        -> `FindMeleeWeapon`  -> `Chain`  -> non nulle, 3 coups
    d = Range    -> `FindRangedWeapon` -> `Bolter` -> non nulle, 2 coups   (BOUNDARY `dist <= Range`)
    d = Range+1  -> `FindRangedWeapon` -> ENSEMBLE VIDE -> `null` -> `0..0` en 1 coup

Le cran du milieu est ce qui garde le SENS de l'inegalite : avec `dist < Range`, il tomberait a
`0..0` et cette garde rougirait. Le dernier cran est ce que le residu a ferme.

NON-DEGENERESCENCE : la garde exige que les trois issues NATIVES different entre elles -- sinon
l'accord viendrait du regime et non du port. Le montage DEPLACE les unites (`P124._drive_to`), il ne
subit pas la geometrie de spawn.

ASCII only. Probe jumeau : `scripts/python/probe_419r1tr14r1r1_range_gate_generalisation.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r1r1_range_gate_generalisation as G


@pytest.fixture(scope="module")
def gen_case(live_session, rpc, build_runner, tmp_path_factory):
    logs = str(tmp_path_factory.mktemp("rgate_gen"))
    try:
        rid = build_runner(G.SEED_DEFAULT, G.build_extra())
        if isinstance(rid, dict):
            rid = rid["rid"]
        return G.run(live_session, rpc, int(rid))
    except G.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_rgate_carrier_kit_is_mixed_and_discriminant(gen_case):
    """Le montage EXIGE le regime a trois issues : un porteur mixte dont melee et distance ne
    portent PAS le meme nombre de coups. Sans cette attestation, les deux premiers crans
    deviendraient indiscernables par les coups et l'accord perdrait la moitie de son pouvoir."""
    kit = gen_case["kit"]
    assert kit["range_max"] >= 2, f"portee maximale mesuree {kit['range_max']} : pas d'arme distance"
    assert kit["hits_melee"] != kit["hits_ranged"], (
        f"melee {kit['hits_melee']} et distance {kit['hits_ranged']} portent le MEME nombre de "
        f"coups -- les crans d=1 et d=Range ne se distinguent plus")


def test_rgate_three_native_regimes_are_distinct(gen_case):
    """NON-DEGENERESCENCE, cote NATIF : les trois issues doivent DIFFERER. Un montage ou elles
    coincideraient (p. ex. prediction nulle partout) rendrait l'accord vide."""
    seen = {(r["native"]["dmin"], r["native"]["dmax"], r["native"]["hits"]) for r in gen_case["rows"]}
    assert len(seen) == 3, (
        f"les trois crans natifs rendent {sorted(seen)} : le lot ne separe plus les trois issues")
    rows = {r["d"]: r["native"] for r in gen_case["rows"]}
    rmax = gen_case["range_max"]
    assert (rows[1]["dmin"], rows[1]["dmax"]) != (0, 0), (
        f"cran d=1 (MELEE) : le natif rend {rows[1]['dmin']}..{rows[1]['dmax']}")
    assert (rows[rmax]["dmin"], rows[rmax]["dmax"]) != (0, 0), (
        f"cran d={rmax} (BOUNDARY, arme a distance EXACTEMENT en portee) : le natif rend "
        f"{rows[rmax]['dmin']}..{rows[rmax]['dmax']} -- l'inegalite de `FindRangedWeapon` ne serait "
        f"plus `dist <= Range` mais `dist < Range`")
    assert (rows[rmax + 1]["dmin"], rows[rmax + 1]["dmax"], rows[rmax + 1]["hits"]) == (0, 0, 1), (
        f"cran d={rmax + 1} (HORS PORTEE) : le natif rend {rows[rmax + 1]['dmin']}.."
        f"{rows[rmax + 1]['dmax']} en {rows[rmax + 1]['hits']} coups au lieu de 0..0 en 1")


def test_rgate_port_agrees_on_the_three_regimes(gen_case):
    """L'ACCORD, aux trois crans -- bornes ET nombre de coups."""
    for r in gen_case["rows"]:
        n, p = r["native"], r["port"]
        assert (n["dmin"], n["dmax"], n["hits"]) == (p["dmin"], p["dmax"], p["hits"]), (
            f"cran d={r['d']} (tuile {r['tile']}) : natif {n['dmin']}..{n['dmax']} "
            f"({n['hits']} coups) contre port {p['dmin']}..{p['dmax']} ({p['hits']})")


# --------------------------------------------------------------------------- la face COMBAT

@pytest.fixture(scope="module")
def combat_case(live_session, rpc, build_runner):
    """Runner SEPARE : le volet combat DEPLACE reellement le caster, il ne peut pas partager le
    montage de prediction (qui, lui, garde le caster fixe et fait varier la TUILE d'attaque)."""
    try:
        rid = build_runner(G.SEED_DEFAULT, G.build_extra())
        if isinstance(rid, dict):
            rid = rid["rid"]
        return G.run_combat(live_session, rpc, int(rid))
    except G.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_rgate_combat_is_inert_when_a_weapon_exists(combat_case):
    """CONTREFACTUEL de la face COMBAT : au contact, le gate n'immunise RIEN -- l'attaque s'execute
    et le rejeu OFFLINE de l'etat pre-attaque rend le MEME degat que le live. Sans ce cran, un port
    qui no-operait TOUJOURS passerait la garde suivante."""
    c = combat_case["crans"][1]
    assert (c["live_dmg"] or 0) > 0, (
        f"au contact (spot {c['spot']}), le natif inflige {c['live_dmg']} : le montage n'exerce "
        f"plus le regime AVEC arme")
    assert c["live_dmg"] == c["off_dmg"] and c["live_nd"] == c["off_nd"], (
        f"au contact : live {c['live_dmg']} degats / {c['live_nd']} tirages contre offline "
        f"{c['off_dmg']} / {c['off_nd']}")


def test_rgate_combat_noops_out_of_weapon_range(combat_case):
    """LA FACE COMBAT DU MEME FOYER.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteBehaviour` est
    `weapon = FindAttackWeapon(entities); if (weapon == null) return;` -- ni coup, ni trigger. Avec
    le caster REELLEMENT hors de portee de toutes ses armes, le natif ne tire RIEN (0 degat,
    0 tirage RNG) et le port doit en faire autant.

    ⚠ Ce cran a exhibe un SECOND defaut, invisible cote prediction : le runner rabattait la distance
    sur un binaire `1 if adjacent else 2`, donc la porte `dist <= Range` ne pouvait jamais mordre
    au-dela de 2. Mesure d'alors : natif `0 degat / 0 tirage`, port `1311 degats / 2 tirages`."""
    rmax = combat_case["range_max"]
    c = combat_case["crans"][rmax + 1]
    assert c["live_dmg"] == 0 and c["live_nd"] == 0, (
        f"hors portee (spot {c['spot']}, cible {combat_case['target']}) : le NATIF inflige "
        f"{c['live_dmg']} degats en {c['live_nd']} tirages -- le regime a change")
    assert c["off_dmg"] == 0 and c["off_nd"] == 0, (
        f"hors portee : le PORT inflige {c['off_dmg']} degats en {c['off_nd']} tirages alors que le "
        f"natif no-ope -- `ExecuteBehaviour` n'est pas mirrore (arme selectionnee hors portee, ou "
        f"gate `weapon is None` absent)")
    assert c["last_none"] is True, (
        "hors portee : le port a produit une operation de degat alors que `ExecuteBehaviour` sort "
        "avant `ExecuteNormalAttack`")
