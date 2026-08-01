"""#419-r1 -- la sortie de `FireOfAbsolution` (**TriggeredAbilityType 1017**) dans le `pairUtility`,
confrontee au NATIF.

`IdunBattle.AI.Playbook.Loki.FireOfAbsolutionPlaybook.u003CCalculateAttackUtilityInStepsInternalu003E
d__4$$MoveNext` rend `wFriend * |GetAdjacentFriends(case.Target, playerId)| + wEnemy *
|GetAdjacentEnemies(case.Target, playerId, false)|` -- DEUX produits poids x cardinal, de SIGNES
OPPOSES (-20 / +20 sur ce BC), ancres sur la CIBLE. Il entre dans la face ATTACK du dispatcher
`TriggeredAbilitiesUtility(2)`, donc DANS le terme de paire.

CE QUE CE TEST GARDE -- six choses :

  1. **NON-DEGENERESCENCE** -- le balayage installe des couples `(amis, ennemis)` DISTINCTS, dont au
     moins un ou `amis != ennemis`. Sans lui, les deux poids etant opposes, un port qui les
     ECHANGERAIT rendrait exactement la meme valeur : la contre-epreuve `swap_keys` serait inerte et
     l'appariement cle <-> slot ne serait prouve par rien. ⚠ MESURE #419-r1 : la premiere version de
     ce montage jouait les mutants sur le SEUL dernier cran, ou `(2, 2)` -- `swap_keys` y etait vert
     sans que rien ne cloche. Les mutants sont donc joues a CHAQUE cran.
  2. **CONFORMITE AU NATIF, PAR CRAN** -- entre deux crans consecutifs, une seule unite bouge : le
     delta de `natif - port_mute` doit valoir EXACTEMENT le delta du terme attendu (+-20). C'est la
     mesure isolante : tout le reste est identique d'un cran a l'autre.
  3. **DISCRIMINANCE** -- playbook 1017 RETIRE du registre, le port perd EXACTEMENT
     `wFriend * nFriends + wEnemy * nEnemies`. Un port qui verserait un terme plat, ou qui
     n'utiliserait qu'un des deux poids, passerait (2) et tomberait ici.
  4. **LES CONTRE-EPREUVES MORDENT** -- cinq mutants (cles echangees, terme ami retire, terme ennemi
     retire, caster exclu des amis, porte d'elevation retiree) doivent DEPLACER le port sur AU MOINS
     un cran. Le critere est le deplacement par rapport au port NON MUTE, jamais l'ecart au natif
     (piege mesure par #441 : un mutant inerte serait vert sur ce critere-la).
  5. **LA FEUILLE** rend le terme SANS `prediction` ni tuile d'attaque : ce corps ne lit que
     `case@+0x10` (Caster) et `case@+0x20` (Target), jamais `case.DamagePrediction`
     (`UtilityAttackCase+0x28`) ni `case.CasterPosition` (`+0x18`).
  6. **LE CASTER COMPTE PARMI LES AMIS** (double delta) -- le natif n'oppose AUCUN retrait au
     resultat de `GetAdjacentFriends`, la ou la famille MOVE en a un explicite. Un caster adjacent a
     sa propre cible doit donc s'infliger `wFriend`. Le confronter en NIVEAU est impossible (changer
     la tuile de tir change tout le reste du score) : on prend le double delta
     `(nat_adj - mute_adj) - (nat_far - mute_far)`, qui annule et le residu constant et la variation
     due au changement de tuile.

⚠ CE QUE CE TEST ASSERTE EN NIVEAU, ET POURQUOI IL PEUT : contrairement a #446 (ecart constant de
-4.16 / -5.64 sur sa paire), cette paire porte un residu **NUL** -- `natif == port` a 1e-9 sur les
six crans mesures. La garde asserte donc l'INVARIANCE de l'ecart natif-port (robuste a l'apparition
d'un residu etranger) ET l'egalite `manque == attendu` (le critere isolant). Si un residu etranger
apparait un jour, c'est l'assertion d'invariance qui doit tenir et celle de niveau qui doit ceder --
elles sont separees expres.

Porteur : `adeptRetributor` (HERO au pool ; 3 npc `adept*Retributor*` portent 1017 aussi).
`FireOfAbsolution` est son SEUL passif, et le montage ATTESTE qu'aucun autre playbook attack n'est
dans son `AbilitiesComponent` -- aucun terme etranger ne se mele.
ASCII only. Probe jumeau : `scripts/python/probe_419_r1_fire_of_absolution_pair_term.py`.
"""
from __future__ import annotations

import pytest

import probe_419_r1_fire_of_absolution_pair_term as P419

EPS = P419.EPS


@pytest.fixture(scope="module")
def foa_case(live_session, rpc, build_runner):
    """Un runner : geometrie CONSTRUITE (adjacence NATIVE, >= 5 voisins libres autour de la cible,
    quatre garages, et si le board l'offre une marche `|delta elev| >= 2`), attestation complete.
    Un `MontageError` devient un ECHEC, jamais un skip."""
    try:
        rid = build_runner(P419.SEED, P419.BUILD_ARGS)["rid"]
        return P419.build_case(live_session, rpc, rid)
    except P419.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def foa_rows(foa_case, live_session, rpc):
    """Le balayage, mutants compris (ils sont offline sur le `ctx` de chaque cran)."""
    try:
        return P419.sweep(live_session, rpc, foa_case, with_mutants=True)
    except P419.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def foa_quirk(foa_rows, foa_case, live_session, rpc):
    """L'etape B, EN DERNIER : elle re-drive les unites et laisse la geometrie ailleurs."""
    try:
        return P419.caster_quirk(live_session, rpc, foa_case)
    except P419.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_foa_montage_is_not_degenerate(foa_rows, foa_case):
    """(1) NON-DEGENERESCENCE : plusieurs couples `(amis, ennemis)`, dont un ASYMETRIQUE, et deux
    poids NON NULS de signes OPPOSES dans le BC servi.

    Le couple asymetrique est la condition sans laquelle `swap_keys` ne peut rien prouver ; les
    poids non nuls sont la condition sans laquelle le terme entier serait inerte et l'accord ne
    dirait rien (piege #271, ou une cle valait 0 dans la capture et 10 au gameconfig vivant)."""
    assert foa_rows, "aucune mesure produite -- le montage n'a rien confronte"
    couples = {(r["nf"], r["ne"]) for r in foa_rows}
    assert len(couples) >= 3, f"balayage trop pauvre, un terme plat passerait : {couples}"
    assert any(nf != ne for nf, ne in couples), (
        f"aucun cran ou amis != ennemis : les deux poids etant opposes, un port qui les ECHANGERAIT "
        f"rendrait la meme valeur partout et rien ne le verrait -- couples {couples}")
    wt = foa_case["ctx"].wt
    wf, we = float(wt.triggered(P419.KEY_FRIEND)), float(wt.triggered(P419.KEY_ENEMY))
    assert wf < 0 < we, (
        f"les poids du BC servi ne sont pas de signes opposes ({P419.KEY_FRIEND}={wf}, "
        f"{P419.KEY_ENEMY}={we}) : le montage ne teste plus ce que le decompile decrit")


def test_foa_sweep_tracks_native_exactly(foa_rows):
    """(2) CONFORMITE AU NATIF, PAR CRAN. Entre deux crans consecutifs une seule unite bouge, donc
    le delta de `natif - port_mute` EST le terme du playbook, isole : il doit valoir exactement le
    delta attendu (+-20). L'ecart natif-port doit rester INVARIANT (tout le mouvement de l'oracle
    est capte par le terme porte)."""
    assert len(foa_rows) >= 4, f"balayage trop court : {len(foa_rows)} crans"
    base = foa_rows[0]["native"] - foa_rows[0]["port"]
    for prev, cur in zip(foa_rows, foa_rows[1:]):
        dm = cur["missing"] - prev["missing"]
        de = cur["expected"] - prev["expected"]
        assert abs(dm - de) < EPS, (
            f"entre {prev['step']} ({prev['nf']}a/{prev['ne']}e) et {cur['step']} "
            f"({cur['nf']}a/{cur['ne']}e), ce qui MANQUE au port prive de {P419.ABILITY} bouge de "
            f"{dm} au lieu de {de} -- le terme n'est pas `wAmi x nAmis + wEnnemi x nEnnemis`")
    for r in foa_rows:
        gap = r["native"] - r["port"]
        assert abs(gap - base) < EPS, (
            f"l'ecart natif-port varie avec les cardinaux ({r['step']} : {gap} contre {base} au "
            f"premier cran) -- une partie du mouvement de l'oracle n'est pas captee par le terme")


def test_foa_level_matches_native(foa_rows):
    """(2bis) NIVEAU : sur cette paire le residu est NUL, donc `natif - port_mute` doit valoir le
    terme attendu en ABSOLU, pas seulement en delta.

    Assertion SEPAREE de l'invariance ci-dessus : si un residu etranger apparait un jour, c'est
    celle-ci qui doit ceder (et nommer sa cause), pas la conformite par cran."""
    for r in foa_rows:
        assert abs(r["missing"] - r["expected"]) < EPS, (
            f"cran {r['step']} ({r['nf']} amis, {r['ne']} ennemis) : le port prive de "
            f"{P419.ABILITY} manque de {r['missing']} au natif, alors que le terme vaut "
            f"{r['expected']} -- natif={r['native']} port={r['port']} mute={r['muted']}")


def test_foa_term_is_load_bearing(foa_rows):
    """(3) DISCRIMINANCE : playbook 1017 RETIRE -> le port perd EXACTEMENT le terme des deux
    produits. Un port qui n'utiliserait qu'un des deux poids passerait (2) et tomberait ici."""
    for r in foa_rows:
        assert abs(r["carried"] - r["expected"]) < EPS, (
            f"sans le playbook {P419.ABILITY}, le port devrait perdre exactement {r['expected']} au "
            f"cran {r['step']} ({r['nf']} amis, {r['ne']} ennemis) : port={r['port']} "
            f"mute={r['muted']} perdu={r['carried']}")


def test_foa_counter_probes_bite(foa_rows, foa_quirk):
    """(4) LES CONTRE-EPREUVES MORDENT -- chaque mutant doit DEPLACER le port sur AU MOINS un cran.

    `exclude_caster` est le seul qui ne peut PAS mordre pendant le balayage (le caster y est
    toujours sur sa tuile de tir, non adjacente a la cible) : son gisement est le regime `adj` de
    l'etape B, et c'est la qu'on l'exige. `no_elev_gate` n'a de gisement que sur un board offrant
    une marche `|delta elev| >= 2` voisine de la cible -- si le cran `zz` n'a pas ete installe, le
    montage le dit et le test le refuse plutot que de rendre un vert qui ne prouve rien."""
    for m in P419.MUTANTS:
        if m == "exclude_caster":
            continue
        worst = max(abs(r["mutants"][m]) for r in foa_rows)
        assert worst > EPS, (
            f"la contre-epreuve `{m}` NE MORD sur AUCUN cran (deplacement max {worst}) : l'axe "
            f"qu'elle coupe n'est pas exerce par ce montage, la garde ne prouve rien dessus -- "
            f"crans { {r['step']: r['mutants'][m] for r in foa_rows} }")
    assert any(r["step"] == "zz" for r in foa_rows), (
        "le cran `zz` (marche `|delta elev| >= 2` voisine de la cible) n'a PAS ete installe : la "
        "porte d'elevation d'`IterateAdjacentTiles` n'est pas exercee, et `no_elev_gate` ne prouve "
        "rien -- il faut un board qui l'offre")


def test_foa_caster_counts_as_friend(foa_quirk):
    """(6) LE CASTER COMPTE PARMI LES AMIS. Double delta : `(nat_adj - mute_adj) - (nat_far -
    mute_far)` doit valoir `wFriend`. Il vaudrait 0 si le natif retirait le caster.

    Et la contre-epreuve qui le coupe (`exclude_caster`) doit MORDRE dans ce regime -- c'est son
    unique gisement."""
    assert abs(foa_quirk["double_delta_native"] - foa_quirk["expected"]) < EPS, (
        f"le double delta NATIF vaut {foa_quirk['double_delta_native']} au lieu de "
        f"{foa_quirk['expected']} : le caster adjacent a sa cible ne se compte PAS comme le port le "
        f"croit -- far={foa_quirk['far']} adj={foa_quirk['adj']}")
    assert abs(foa_quirk["double_delta_port"] - foa_quirk["expected"]) < EPS, (
        f"le double delta du PORT vaut {foa_quirk['double_delta_port']} au lieu de "
        f"{foa_quirk['expected']}")
    assert foa_quirk["adj"]["nf"] == 1 and foa_quirk["far"]["nf"] == 0, (
        f"le regime du quirk n'est pas installe : le caster doit etre le SEUL ami adjacent en "
        f"`adj` et aucun en `far` -- {foa_quirk['far']['nf']} / {foa_quirk['adj']['nf']}")


def test_foa_leaf_returns_the_two_products(foa_case, foa_quirk):
    """(5) LA FEUILLE `TriggeredAbilities(2)` FACE ATTACK rend le terme SANS `prediction`. Elle vise
    le FOYER (`engine.utilities.tile.triggered_abilities_attack_utility`), donc elle garde le
    CABLAGE autant que le calcul -- c'est la moitie du patron #419.

    Jouee sur le regime `adj` de l'etape B (le dernier installe) : un seul ami adjacent, le CASTER
    lui-meme, donc la feuille doit rendre `wFriend` exactement -- une valeur NEGATIVE, ce qu'aucun
    autre playbook du registre ne produit."""
    from engine.utilities.tile import triggered_abilities_attack_utility
    ctx, cid, ab = foa_case["ctx"], foa_case["cid"], foa_case["ab"]
    tgt, tile = foa_case["ids"]["T"], foa_quirk["adj"]["tile"]
    got = triggered_abilities_attack_utility(ctx, cid, ab, tgt, tile)
    assert abs(got - foa_quirk["expected"]) < EPS, (
        f"la feuille rend {got} alors que le caster est le seul ami adjacent a la cible et que "
        f"{P419.KEY_FRIEND} vaut {foa_quirk['expected']}, SANS prediction")
