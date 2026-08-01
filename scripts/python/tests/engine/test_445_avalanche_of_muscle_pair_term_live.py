"""#445 -- `AvalancheOfMuscle` (1028) dans le `pairUtility`, confronte au NATIF.

`IdunBattle.AI.Playbook.Loki.AvalancheOfMusclePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`
a SEPT sorties. Quatre sont atteignables par un montage live, et elles se distinguent par la TUILE
et la POSITION du caster, jamais par un poids constant :

  R_CHARGE   caster loin, tuile au contact           -> etat 7, terme > 0
  R_KILL     idem, cible a 1 PV                      -> etat 7, terme AUTRE (KillUnit/Overkill)
  R_ALREADY  caster DEJA au contact, change de tuile -> etat 6, terme 0
  R_STAY     tuile d'attaque == tuile courante       -> etat 3, terme 0

CE QUE CE TEST GARDE :

  1. **CONFORMITE** -- pour chaque regime, l'utilite de paire du port
     (`ComparablePlaybook.calculate_action_utility(...)["u"]`) egale celle du NATIF (`pairUtility`).
  2. **DISCRIMINANCE** -- playbook 1028 RETIRE du registre, le port perd EXACTEMENT le terme sur
     les deux regimes de charge et RIEN sur les deux regimes gates.
  3. **NON-DEGENERESCENCE** -- R_CHARGE et R_KILL versent des termes DIFFERENTS. Ce sont deux
     points de la MEME chaine (`extraDmg` -> prediction slot 0x23 -> composite Damage) : un seul
     point se fitterait, deux ne se fittent pas.
  4. **L'ETAGE `CameIntoContactWithEnemy`, ISOLE** -- les quatre combinaisons (avant/apres) hors
     runner. Les etats 2 / 4 / 5 du natif sont MUTUELLEMENT REDONDANTS sur la VALEUR (ils rendent
     tous `0` sur les memes entrees, seul le numero d'etat du yield les distingue, et il est
     invisible de l'exterieur) : une assertion prise sur la feuille ne peut pas rougir en n'en
     cassant qu'un -- MESURE, y compris en en cassant DEUX. Elle est donc remplacee par cette
     garde d'etage, qui mord.
  5. **L'ETAGE `extraDmg`** -- la magnitude portee est LUE au meme foyer que la face COMBAT
     (`ability_var("AvalancheOfMuscle", "extraDmg", ...)`, var index 8), jamais un litteral.

Porteur : `astraBullgryn` (HERO au pool ; 4 npc `astra*Bullgryn*` portent 1028 aussi).
Le montage EXIGE ses quatre regimes ; s'il ne les obtient pas il ECHOUE, il ne skippe pas (#268).
ASCII only. Probe jumeau : `scripts/python/probe_445_avalanche_of_muscle_pair_term.py`.
"""
from __future__ import annotations

import pytest

import probe_445_avalanche_of_muscle_pair_term as P445

EPS = P445.EPS


@pytest.fixture(scope="module")
def am_case(live_session, rpc, build_runner):
    """Un runner : le montage entier (drive vers l'etoile, verification de l'AbilitiesComponent,
    attestation geometrique ET par l'oracle) vit dans le probe -- cette fixture n'en est que la
    porte pytest. Un `MontageError` devient un ECHEC, jamais un skip."""
    try:
        rid = build_runner(P445.SEED, P445.build_args(P445.BOARD, P445.FOES))["rid"]
        return P445._stage(live_session, rpc, rid, P445.FOES)
    except P445.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def am_rows(am_case, rpc):
    return P445.measure(rpc, am_case)


def test_avalanche_of_muscle_pair_term_matches_native(am_rows):
    """(1) CONFORMITE : port == natif sur les quatre regimes, tuile par tuile."""
    assert am_rows, "aucune mesure produite -- le montage n'a rien confronte"
    for r in am_rows:
        assert abs(r["native"] - r["port"]) < EPS, (
            f"pairUtility != natif sur {r['target']} (regime={r['regime']}) depuis {r['tile']} : "
            f"natif={r['native']} port={r['port']} ecart={r['port'] - r['native']}")


def test_avalanche_of_muscle_term_is_load_bearing(am_rows):
    """(2) DISCRIMINANCE : playbook 1028 RETIRE -> le port perd le terme sur les deux regimes de
    CHARGE et rien sur les deux regimes gates. C'est la moitie CABLAGE : un playbook porte mais
    absent du registre serait INERTE, sans erreur ni test rouge (patron #419)."""
    for r in am_rows:
        term = r["port"] - r["port_muted"]
        missing = r["native"] - r["port_muted"]
        if r["nonzero"]:
            assert abs(term) > EPS, (
                f"{r['regime']} : le playbook ne verse RIEN ({term}) -- regime degenere, "
                f"l'accord de la garde precedente ne prouverait rien")
        else:
            assert abs(term) < EPS, (
                f"{r['regime']} : le playbook verse {term} alors que le gate natif "
                f"(`CameIntoContactWithEnemy` / << le caster bouge >>) doit rendre 0")
        assert abs(missing - term) < EPS, (
            f"{r['regime']} : sans le playbook, l'ecart au natif vaut {missing} alors que le "
            f"terme verse par le port vaut {term} -- les deux doivent coincider")


def test_avalanche_of_muscle_two_points_of_the_same_chain(am_rows):
    """(3) NON-DEGENERESCENCE : R_CHARGE et R_KILL versent des termes DIFFERENTS et non nuls."""
    by = {r["regime"]: r["port"] - r["port_muted"] for r in am_rows}
    assert {"R_CHARGE", "R_KILL", "R_ALREADY", "R_STAY"} <= set(by), (
        f"les quatre regimes ne sont pas tous installes : {sorted(by)}")
    assert abs(by["R_CHARGE"]) > EPS and abs(by["R_KILL"]) > EPS, (
        f"un regime de charge verse 0 : R_CHARGE={by['R_CHARGE']} R_KILL={by['R_KILL']}")
    assert abs(by["R_CHARGE"] - by["R_KILL"]) > EPS, (
        f"R_CHARGE et R_KILL versent le MEME terme ({by['R_CHARGE']}) : la chaine "
        f"extraDmg -> prediction -> composite n'est mesuree qu'en UN point, donc fittable")


def test_came_into_contact_is_the_native_conjunction():
    """(4) L'ETAGE `CameIntoContactWithEnemy`, ISOLE (offline).

    `AvalancheOfMusclePlaybook$$CameIntoContactWithEnemy` =
    `AreTilesAdjacent([casterTile], targetTiles) && !AreTilesAdjacent(casterTiles, targetTiles)`.
    Les QUATRE combinaisons sont exigees ici, hors runner.

    POURQUOI ISOLER : dans le corps natif comme dans le port, ce conjonct `after` est REDONDANT
    avec l'etat 4 (`<slot 0x60>(casterTile, target)`) -- et l'etat 5 (aucune arme melee a
    distance) rend `0` sur les memes entrees. MESURE : desactiver l'etat 4, forcer `after=True`,
    ou meme les DEUX, laisse la garde live entierement VERTE. Une assertion << hors contact -> 0 >>
    prise sur la feuille ne garde donc RIEN d'isolable ; celle-ci, si."""
    from engine.playbook.avalanche_of_muscle import AvalancheOfMusclePlaybook

    class _Scene:                       # `elev_by_pos` absent -> adjacence hex pure
        elev_by_pos = None

    f = AvalancheOfMusclePlaybook._came_into_contact_with_enemy
    sc, tgt = _Scene(), (5, 5)
    adj, far = (5, 4), (5, 2)           # (5,4) touche (5,5) ; (5,2) est a distance 2
    assert f(sc, far, adj, tgt) is True, "loin AVANT, au contact APRES : c'est LA charge"
    assert f(sc, adj, (6, 5), tgt) is False, "deja au contact AVANT -> le conjonct nie"
    assert f(sc, far, far, tgt) is False, "hors contact APRES -> pas de charge"
    assert f(sc, adj, adj, tgt) is False, "au contact AVANT et APRES -> pas de charge"


def test_avalanche_of_muscle_extra_damage_reads_the_config(am_case):
    """(5) L'ETAGE `extraDmg` : la magnitude est LUE dans la config d'ability au meme foyer que la
    face COMBAT (`AvalancheOfMuscleExtraDamageEffect`), var index 8, avec le multiplicateur de
    rarete -- jamais un litteral. On recoupe la valeur du port contre une relecture INDEPENDANTE
    de `gameconfig`, au niveau et au multiplicateur LUS du runner."""
    from engine.entities.effects.magnitude import ability_var
    from engine.playbook.avalanche_of_muscle import AvalancheOfMusclePlaybook

    sc, cid = am_case["ctx"].scene, am_case["cid"]
    got = AvalancheOfMusclePlaybook()._extra_damage(sc, cid)
    assert got, f"la magnitude portee est vide ({got}) -- l'etat 7 ne verserait jamais rien"
    st = sc.ability_state(cid, int(P445.ABILITY)) or {}
    lvl = st.get("level") if st.get("level") is not None else (sc.ablvl_by_id or {}).get(cid)
    mult = st.get("multiplier") if st.get("multiplier") is not None else (sc.mult_by_id or {}).get(cid)
    want = ability_var("AvalancheOfMuscle", "extraDmg", lvl, multiplier_pct=int(mult or 100))
    assert got == want, (
        f"la magnitude portee ({got}) ne provient pas de la config d'ability "
        f"(extraDmg[level={lvl}] x mult={mult} = {want})")
