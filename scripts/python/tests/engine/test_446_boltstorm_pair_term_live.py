"""#446 -- la sortie de `Boltstorm` (1090) dans le `pairUtility`, confrontee au NATIF.

`IdunBattle.AI.Playbook.Loki.BoltstormPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
rend `GetUtilityValue("BOLTSTORM_AdjacentEnemies") * Count(BoltstormAbility.GetAllTargets(dsl,
Direct(FindRangedWeapon(caster).Range)))` -- un PRODUIT poids x CARDINAL, ou le cardinal compte la
CIBLE elle-meme plus ses voisins ennemis a portee du caster et non obscurcis. Il entre dans la face
ATTACK du dispatcher `TriggeredAbilitiesUtility(2)`, donc DANS le terme de paire.

CE QUE CE TEST GARDE -- cinq choses :

  1. **NON-DEGENERESCENCE** -- deux cardinaux distincts (3 sur la cible entouree, 1 sur la cible
     isolee) ET au moins un voisin de la cible EXCLU PAR LA PORTEE. Sans ce dernier, la porte
     `SurroundingEnemies(Owner, range)` ne serait pas exercee et un port qui l'oublierait passerait.
     ⚠ MESURE #446 : ce montage a d'abord ete construit avec `hexgeo.neighbors` NU, et la porte
     d'ELEVATION d'`AdjacentUnits` (`|delta| < 2`) excluait deja le temoin -- le gate de portee
     n'etait PAS teste, et rien ne le signalait. Le montage exige donc l'adjacence NATIVE.
  2. **CONFORMITE AU NATIF, PAR CRAN** -- le balayage bouge UNE seule chose (la distance au caster
     d'un voisin qui reste voisin) et exige que le natif ET le port bougent d'EXACTEMENT le poids,
     et que l'ecart natif-port reste INVARIANT. C'est la confrontation directe : tout le mouvement
     de l'oracle est capte par le terme porte.
  3. **DISCRIMINANCE** -- playbook 1090 RETIRE du registre, le port perd EXACTEMENT `poids x
     cardinal` sur chaque cible. Un port qui verserait un terme plat passerait (2) et tomberait ici.
  4. **LES CONTRE-EPREUVES MORDENT** -- trois mutants (porte de portee retiree, volet `Target`
     retire, gate d'adjacence retire) doivent DEPLACER le port. Le critere est le deplacement par
     rapport au port NON MUTE, jamais l'ecart au natif : cette paire porte un residu constant
     hors-perimetre, et un critere « ecart au natif > EPS » serait VRAI meme pour un mutant inerte
     (le piege mesure par #441).
  5. **LA FEUILLE** rend `poids x cardinal` SANS `prediction` : ce corps ne lit que `case@+0x10`
     (Caster) et `case@+0x20` (Target), jamais `case.DamagePrediction` (`UtilityAttackCase+0x28`).

⚠ CE QUE CE TEST N'ASSERTE PAS, ET POURQUOI : la conformite en NIVEAU (`natif == port`). Cette
paire porte un ecart CONSTANT (mesure : -4.159792 sur la cible entouree, -5.639718 sur l'isolee)
qui ne bouge PAS quand le cardinal varie, et qui differe par cible -- il vient du composite de
DEGAT, pas de ce terme. L'asserter ici ferait rougir cette garde pour une cause etrangere ; la
garder muette le cacherait. Elle asserte donc l'INVARIANCE de cet ecart a travers le balayage, ce
qui est strictement plus fort sur l'axe teste. Residu nomme dans `docs/rl/case-446-boltstorm-playbook.md`.

Porteur : `templAggressor` (HERO au pool ; 4 npc `templBossAggressor*` portent 1090 aussi).
ASCII only. Probe jumeau : `scripts/python/probe_446_boltstorm_pair_term.py`.
"""
from __future__ import annotations

import pytest

import probe_446_boltstorm_pair_term as P446

EPS = P446.EPS


@pytest.fixture(scope="module")
def bs_case(live_session, rpc, build_runner):
    """Un runner : geometrie CONSTRUITE (adjacence NATIVE, deux voisins a portee, deux hors
    portee), drive, attestation complete. Un `MontageError` devient un ECHEC, jamais un skip."""
    try:
        rid = build_runner(P446.SEED, P446.BUILD_ARGS)["rid"]
        return P446.build_case(live_session, rpc, rid)
    except P446.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def bs_rows(bs_case, rpc):
    try:
        return P446.measure(rpc, bs_case)
    except P446.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def bs_mutants(bs_rows, bs_case, rpc):
    """Les trois contre-epreuves, jouees AVANT le balayage : elles s'appuient sur le layout de
    montage, ou `F` est voisin NATIF de la cible mais HORS portee."""
    try:
        return {m: P446.measure_mutant(rpc, bs_case, m)
                for m in ("no_range", "no_target", "not_adjacent")}
    except P446.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def bs_sweep(bs_mutants, bs_case, live_session, rpc):
    """Le balayage, EN DERNIER : il DEPLACE les unites et laisse la geometrie ailleurs."""
    try:
        return P446.sweep_count(live_session, rpc, bs_case)
    except P446.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_boltstorm_covers_two_cardinals(bs_rows):
    """(1) NON-DEGENERESCENCE : deux cardinaux distincts sont installes, et le poids du BC servi
    n'est pas nul (sinon le terme serait inerte et l'accord ne prouverait rien -- piege #271)."""
    assert bs_rows, "aucune mesure produite -- le montage n'a rien confronte"
    counts = {r["count"] for r in bs_rows}
    assert counts == {P446.EXPECTED_COUNT_CROWD, P446.EXPECTED_COUNT_ALONE}, (
        f"un seul cardinal couvert -- un terme PLAT passerait : {counts}")
    for r in bs_rows:
        assert r["weight"] > 0, (
            f"le poids {P446.WEIGHT_KEY} vaut {r['weight']} dans le BC servi : le terme serait nul "
            f"et cette garde ne trancherait rien")


def test_boltstorm_term_is_load_bearing(bs_rows):
    """(3) DISCRIMINANCE : playbook 1090 RETIRE -> le port perd EXACTEMENT `poids x cardinal`."""
    for r in bs_rows:
        got = r["port"] - r["port_muted"]
        assert abs(got - r["expected"]) < EPS, (
            f"sans le playbook {P446.ABILITY}, le port devrait perdre exactement "
            f"{r['expected']} sur la cible {r['target']} (cardinal {r['count']}, poids "
            f"{r['weight']}) : port={r['port']} port_mute={r['port_muted']} perdu={got}")


def test_boltstorm_leaf_returns_weight_times_count(bs_case, bs_rows):
    """(5) LA FEUILLE `TriggeredAbilities(2)` FACE ATTACK rend `poids x cardinal`, SANS
    `prediction`. Elle vise le FOYER (`engine.utilities.tile.triggered_abilities_attack_utility`),
    donc elle garde le CABLAGE autant que le calcul -- c'est la moitie du patron #419.

    ⚠ `templAggressor` porte AUSSI `SuppressiveFire` (1044, par le trait 1010), dont le playbook est
    au registre : son terme vaut 0 ici (le montage ATTESTE qu'aucune cible ne porte l'overwatch
    1009), donc la feuille ne renvoie que le terme de 1090."""
    from engine.utilities.tile import triggered_abilities_attack_utility
    ctx, cid, tile, ab = bs_case["ctx"], bs_case["cid"], bs_case["tile"], bs_case["ab"]
    for r in bs_rows:
        got = triggered_abilities_attack_utility(ctx, cid, ab, r["uid"], tile)
        assert abs(got - r["expected"]) < EPS, (
            f"la feuille rend {got} sur la cible {r['target']} alors que le cardinal {r['count']} "
            f"et le poids {r['weight']} imposent {r['expected']}, SANS prediction")


def test_boltstorm_counter_probes_bite(bs_mutants):
    """(4) LES CONTRE-EPREUVES MORDENT -- chacune doit DEPLACER le port par rapport au port NON
    MUTE. Un mutant inerte signifierait que l'axe qu'il coupe n'est pas exerce par le montage."""
    for name, rows in bs_mutants.items():
        moved = max(abs(r["port"] - r["port_ref"]) for r in rows)
        assert moved > EPS, (
            f"la contre-epreuve `{name}` NE MORD PAS (deplacement max {moved}) : l'axe qu'elle "
            f"coupe n'est pas exerce par ce montage, la garde ne prouve rien dessus -- "
            f"{[(r['target'], r['port'], r['port_ref']) for r in rows]}")


def test_boltstorm_sweep_tracks_native_exactly(bs_sweep, bs_rows):
    """(2) CONFORMITE AU NATIF, PAR CRAN. Le balayage ne bouge QUE la distance au caster de voisins
    qui restent voisins de la cible : le natif et le port doivent bouger d'EXACTEMENT le poids par
    cran, et l'ecart natif-port doit rester INVARIANT (tout le mouvement de l'oracle est capte par
    le terme porte).

    C'est aussi la garde du gate de PORTEE : au moins un cran doit avoir un voisin de la cible
    EXCLU par `SurroundingEnemies(Owner, range)` -- sinon la porte n'est pas exercee."""
    assert len(bs_sweep) >= 3, f"balayage trop court : {len(bs_sweep)} crans"
    weight = bs_rows[0]["weight"]
    assert any(r["gated_by_range"] for r in bs_sweep), (
        "aucun cran n'a de voisin de la cible exclu PAR LA PORTEE -- la porte "
        "`SurroundingEnemies(Owner, range)` n'est pas exercee")
    base = bs_sweep[0]["native"] - bs_sweep[0]["port"]
    for prev, cur in zip(bs_sweep, bs_sweep[1:]):
        dn = cur["native"] - prev["native"]
        dp = cur["port"] - prev["port"]
        dcount = cur["count"] - prev["count"]
        assert abs(dn - weight * dcount) < EPS, (
            f"entre {prev['step']} (cardinal {prev['count']}) et {cur['step']} (cardinal "
            f"{cur['count']}), le NATIF bouge de {dn} au lieu de {weight * dcount} -- le terme "
            f"n'est pas `poids x cardinal`")
        assert abs(dp - dn) < EPS, (
            f"entre {prev['step']} et {cur['step']}, le port bouge de {dp} et le natif de {dn}")
    for r in bs_sweep:
        gap = r["native"] - r["port"]
        assert abs(gap - base) < EPS, (
            f"l'ecart natif-port varie avec le cardinal ({r['step']} : {gap} contre {base} au "
            f"premier cran) -- une partie du mouvement de l'oracle n'est pas captee par le terme")
