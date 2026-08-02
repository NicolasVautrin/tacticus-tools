"""#419 tranche 6 -- la sortie de `CosmicHorror` (1277) dans le `pairUtility`, confrontee au NATIF.

`IdunBattle.AI.Playbook.Loki.CosmicHorrorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
rend `GetUtilityValue("COSMICHORROR_StepOnDecoyToAttack")` quand l'unite qui OCCUPE la TUILE
D'ATTAQUE (`case.CasterPosition.MainTile`, `UtilityAttackCase@+0x18`) porte `UnitTrait.Decoy`
(0x41d) et est AMIE du caster (`case.Caster`, `@+0x10`) -- 0 sinon. Il entre dans la face ATTACK du
dispatcher `TriggeredAbilitiesUtility(2)`, donc DANS le terme de paire.

CE QUE CE TEST GARDE -- six choses :

  1. **NON-DEGENERESCENCE** -- trois tuiles d'attaque, toutes adjacentes a la MEME cible, a trois
     occupants DIFFERENTS : `D` un leurre, `F` rien, `C` le caster lui-meme (ami, NON leurre). Un
     montage a deux tuiles laisserait passer un port qui oublie le gate `HasTrait`.
  2. **CONFORMITE AU NATIF, EN NIVEAU** -- `port == natif` sur les trois tuiles. Contrairement a
     #446, cette paire ne porte AUCUN residu (mesure : |port - natif| < 1e-7 partout), donc le
     niveau est assertable et c'est la garde la plus forte.
  3. **DISCRIMINANCE** -- playbook 1277 RETIRE du registre, le port perd EXACTEMENT le poids sur
     `D` (regime `friend`) et RIEN ailleurs. Un port qui verserait un terme plat passerait (2)
     sur `D` et tomberait ici.
  4. **LE GATE `IsFriend` A LE BON SENS** -- comparaison INTER-REGIMES sur la MEME tuile `D`, meme
     geometrie, meme cible : le NATIF LUI-MEME rend le poids de plus quand le leurre est AMI. Sans
     ce couple, un port qui accepterait n'importe quel leurre passerait tous les autres tests --
     c'est la seule mesure qui distingue `IsFriend(u, case.Caster)` de « il y a un leurre ».
  5. **LES CONTRE-EPREUVES MORDENT** -- gate de trait retire, gate d'amitie inverse, tuile de la
     CIBLE lue au lieu de celle du caster. Le critere est le DEPLACEMENT par rapport au port NON
     MUTE, jamais l'ecart au natif (piege #441 : un ecart au natif est vrai meme pour un mutant
     inerte des qu'un residu preexiste).
     ⚠ `target_tile` n'est discriminant qu'en regime `friend` : en `enemy` le port rend deja 0
     partout, donc le mutant ne PEUT pas deplacer -- ce n'est pas un defaut du mutant, c'est le
     regime qui ne l'exerce pas. `P419T6.MUST_BITE` porte cette table.
  6. **LA FEUILLE** rend le terme sans `prediction` : ce corps ne lit que `case@+0x10` (Caster) et
     `case@+0x18` (CasterPosition), jamais `case.DamagePrediction` (`UtilityAttackCase@+0x28`).

Le montage n'exige NI injection catalogue NI greffe : `genesPatriarch` (HERO) est au pool et son
PROPRE kit fabrique le leurre (face COMBAT de 1277 : « places a decoy on the hex of that enemy »).
Le regime `enemy` le refait avec un SECOND Patermine, adverse, qui tue une de NOS unites.

Porteur : `genesPatriarch` (HERO au pool) ; 3 npc `genes*Patriarch*` portent 1277 aussi.
ASCII only. Probe jumeau : `scripts/python/probe_419_t6_cosmic_horror_pair_term.py`.
"""
from __future__ import annotations

import pytest

import probe_419_t6_cosmic_horror_pair_term as P419T6

EPS = P419T6.EPS


def _case(live_session, rpc, build_runner, regime: str):
    try:
        rid = build_runner(P419T6.SEED, P419T6.BUILD_ARGS[regime])["rid"]
        return P419T6.build_case(live_session, rpc, rid, regime)
    except P419T6.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def ch_friend(live_session, rpc, build_runner):
    """Regime AMI : le caster tue la proie adverse, le leurre est a lui."""
    return _case(live_session, rpc, build_runner, "friend")


@pytest.fixture(scope="module")
def ch_enemy(live_session, rpc, build_runner):
    """Regime ENNEMI : un SECOND Patermine, adverse, tue NOTRE proie -- le leurre est a lui."""
    return _case(live_session, rpc, build_runner, "enemy")


@pytest.fixture(scope="module")
def ch_rows_friend(ch_friend, rpc):
    try:
        return P419T6.measure(rpc, ch_friend)
    except P419T6.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def ch_rows_enemy(ch_enemy, rpc):
    try:
        return P419T6.measure(rpc, ch_enemy)
    except P419T6.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def ch_mutants(ch_rows_friend, ch_rows_enemy, ch_friend, ch_enemy, rpc):
    try:
        return {r: {m: P419T6.measure_mutant(rpc, c, m)
                    for m in ("no_trait", "invert_friend", "target_tile")}
                for r, c in (("friend", ch_friend), ("enemy", ch_enemy))}
    except P419T6.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_cosmic_horror_montage_is_not_degenerate(ch_friend, ch_enemy, ch_rows_friend):
    """(1) NON-DEGENERESCENCE : trois tuiles d'attaque a occupants DISTINCTS, un leurre ATTESTE
    (trait lu au canal ECS `combatSnapshot`, pas au port), et un poids BC non nul -- sinon le
    terme serait inerte et l'accord ne prouverait rien (piege #271)."""
    for case, want_friend in ((ch_friend, True), (ch_enemy, False)):
        dec = case["decoy"]
        assert dec["is_decoy"], (
            f"l'occupant de la tuile D ne porte pas `UnitTrait.Decoy` ({dec['trait_ids']}) -- "
            f"le regime teste n'est pas installe")
        assert dec["is_friend"] is want_friend, (
            f"regime {case['regime']} : leurre ami={dec['is_friend']}, attendu {want_friend}")
        tiles = [t for _k, t in P419T6._tiles(case)]
        assert len(set(tiles)) == 3, f"les trois tuiles ne sont pas distinctes : {tiles}"
    for r in ch_rows_friend:
        assert r["weight"] > 0, (
            f"le poids {P419T6.WEIGHT_KEY} vaut {r['weight']} dans le BC servi : le terme serait "
            f"nul et cette garde ne trancherait rien")


@pytest.mark.parametrize("which", ["friend", "enemy"])
def test_cosmic_horror_matches_native(which, ch_rows_friend, ch_rows_enemy):
    """(2) CONFORMITE AU NATIF, EN NIVEAU, sur les trois tuiles et dans les deux regimes."""
    rows = ch_rows_friend if which == "friend" else ch_rows_enemy
    assert rows, "aucune mesure produite -- le montage n'a rien confronte"
    for r in rows:
        assert abs(r["port"] - r["native"]) < EPS, (
            f"regime {which}, tuile {r['tile_key']}={r['tile']} : le port rend {r['port']} et le "
            f"natif {r['native']} (ecart {r['port'] - r['native']})")


@pytest.mark.parametrize("which", ["friend", "enemy"])
def test_cosmic_horror_term_is_load_bearing(which, ch_rows_friend, ch_rows_enemy):
    """(3) DISCRIMINANCE : playbook 1277 RETIRE -> le port perd EXACTEMENT le poids sur la tuile
    au leurre AMI, et RIEN sur les autres."""
    rows = ch_rows_friend if which == "friend" else ch_rows_enemy
    for r in rows:
        got = r["port"] - r["port_muted"]
        assert abs(got - r["expected"]) < EPS, (
            f"regime {which}, tuile {r['tile_key']}={r['tile']} : sans le playbook "
            f"{P419T6.ABILITY} le port devrait perdre exactement {r['expected']} (poids "
            f"{r['weight']}) : port={r['port']} port_mute={r['port_muted']} perdu={got}")


def test_cosmic_horror_friend_gate_has_the_right_sign(ch_rows_friend, ch_rows_enemy,
                                                      ch_friend, ch_enemy):
    """(4) LE GATE `IsFriend` A LE BON SENS -- la mesure INTER-REGIMES, la seule qui le tranche.

    Meme tuile `D`, meme geometrie, meme cible : seul le CAMP du leurre change. Le NATIF doit
    rendre exactement le poids DE PLUS quand le leurre est AMI. Un port qui accepterait n'importe
    quel leurre (ou qui ignorerait le gate) passerait tous les autres tests de ce fichier."""
    d_friend = next(r for r in ch_rows_friend if r["tile_key"] == "D")
    d_enemy = next(r for r in ch_rows_enemy if r["tile_key"] == "D")
    assert d_friend["tile"] == d_enemy["tile"], (
        f"les deux regimes n'ont pas monte la MEME tuile D ({d_friend['tile']} contre "
        f"{d_enemy['tile']}) -- la comparaison inter-regimes ne dirait rien")
    weight = d_friend["weight"]
    gap_native = d_friend["native"] - d_enemy["native"]
    assert abs(gap_native - weight) < EPS, (
        f"le NATIF ne distingue pas les deux camps du leurre comme attendu : {d_friend['native']} "
        f"(ami) contre {d_enemy['native']} (ennemi), ecart {gap_native} au lieu de {weight}")
    gap_port = d_friend["port"] - d_enemy["port"]
    assert abs(gap_port - gap_native) < EPS, (
        f"le port bouge de {gap_port} entre les deux camps du leurre la ou le natif bouge de "
        f"{gap_native} -- le gate `IsFriend` du port n'a pas le meme sens que le natif")


def test_cosmic_horror_counter_probes_bite(ch_mutants):
    """(5) LES CONTRE-EPREUVES MORDENT -- chacune doit DEPLACER le port par rapport au port NON
    MUTE, dans les regimes ou l'axe qu'elle coupe est EXERCE (`MUST_BITE`)."""
    for regime, muts in ch_mutants.items():
        for name, rows in muts.items():
            moved = max(abs(r["port"] - r["port_ref"]) for r in rows)
            if name in P419T6.MUST_BITE[regime]:
                assert moved > EPS, (
                    f"regime {regime} : la contre-epreuve `{name}` NE MORD PAS (deplacement max "
                    f"{moved}) : l'axe qu'elle coupe n'est pas exerce, la garde ne prouve rien "
                    f"dessus -- {[(r['tile_key'], r['port'], r['port_ref']) for r in rows]}")
            else:
                assert moved < EPS, (
                    f"regime {regime} : la contre-epreuve `{name}` DEPLACE le port de {moved} "
                    f"alors que ce regime ne l'exerce pas -- la table `MUST_BITE` est fausse, ou "
                    f"le mutant touche autre chose que l'axe annonce")


@pytest.mark.parametrize("which", ["friend", "enemy"])
def test_cosmic_horror_leaf_returns_the_weight(which, ch_friend, ch_enemy,
                                               ch_rows_friend, ch_rows_enemy):
    """(6) LA FEUILLE `TriggeredAbilities(2)` FACE ATTACK rend le terme, SANS `prediction`. Elle
    vise le FOYER (`engine.utilities.tile.triggered_abilities_attack_utility`), donc elle garde le
    CABLAGE autant que le calcul -- c'est la moitie du patron #419.

    `genesPatriarch` n'a QU'UN triggered (`kit_triggered_ability_ids` = {1277}), la feuille ne
    renvoie donc que ce terme-la."""
    from engine.utilities.tile import triggered_abilities_attack_utility
    case = ch_friend if which == "friend" else ch_enemy
    rows = ch_rows_friend if which == "friend" else ch_rows_enemy
    ctx, cid, tgt = case["ctx"], case["cid"], case["ids"]["T"]
    for r in rows:
        got = triggered_abilities_attack_utility(ctx, cid, r["ability"], tgt, r["tile"])
        assert abs(got - r["expected"]) < EPS, (
            f"regime {which}, tuile {r['tile_key']}={r['tile']} : la feuille rend {got} alors que "
            f"le regime impose {r['expected']}, SANS prediction")
