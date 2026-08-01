"""GARDE LIVE #366-r1 tranche 3/3 -- `1141 StormboyzStrike` CONFRONTE au natif, sur DEUX fronts.

LES DEUX CRITERES, en questions binaires :

  1. **A l'init de ses abilities, le porteur quitte-t-il le plateau avec l'effet 1140 pour 2 TOURS,
     et l'etat resultant est-il terme a terme celui du natif ?** -- pose au NATIF (runner GREFFE) et
     au PORT (meme etat de depart, pris sur le runner TEMOIN).
  2. **Le pool de teleport du pathfinder `StormboyzStrike` est-il bien TOUTES les tuiles libres et
     walkable, sans le gate « pas d'ennemi adjacent » de son cousin `TeleportStrike` ?** -- le
     predicat `StormboyzStrikePathfinder$$IsValidTeleportTile` (vslot 11) etait porte en HYPOTHESE
     `True` faute de porteur confrontable (`#381-r5`).

Le montage vit dans `scripts/python/probe_366_r1_stormboyz_strike.py` (`run()`) ; ce fichier n'est
que sa PORTE pytest. Ce que `run()` fait, par cas :

  * DEUX runners, meme seed / meme board / memes unites : l'un avec le passif GREFFE sur une unite du
    pool (`catalog_inject.graft_passive_ability` -- le porteur reel `orksNpc6Stormboy` est **npc** et
    n'a AUCUN summoner, recours 3 de `docs/rl/case-92-catalog-injection.md` §5bis), l'autre sans ;
  * l'etat du TEMOIN est l'ENTREE du trigger, celui du GREFFE sa SORTIE NATIVE. Le port est applique
    a l'entree, les deux sorties sont comparees terme a terme ;
  * puis le pool `aiMovableTiles` de l'unite hors plateau, compare au pool du port sous trois
    predicats (l'hypothese, le cousin `TeleportStrike`, et « aucun pool »).

⚠ Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268). Seule l'indisponibilite du
HARNAIS (pas de session Frida) skippe, et c'est `live_session` qui la porte.

RE : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` §6. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import pytest

import probe_366_r1_stormboyz_strike as P

TELEPORTING_IN = 1140


@pytest.fixture(scope="module")
def stormboyz_cases(live_session):
    """Le montage, UNE fois pour tout le fichier : un cas par entree de `P.TEST_PLAN`.
    Chaque paire de runners est DISPOSEE par `run()` en sortie -- rien a liberer au teardown."""
    return [P.run(board, seed, graft, foes) for board, seed, graft, foes, _note in P.TEST_PLAN]


def _tag(c):
    return "%s/%s/%s" % (c.get("graft"), c.get("board"), len(c.get("foes") or []))


def test_the_montage_actually_mounted_the_grafted_passive(stormboyz_cases):
    """ANTI-TAUTOLOGIE #1 -- sans ce test, un montage qui n'aurait RIEN greffe rendrait deux etats
    identiques et tous les autres tests seraient VERTS. On exige : le canal MESURE des passives
    (`unitAbilityStates` -> `UnitContext.passive_abilities`) porte `StormboyzStrike` du cote GREFFE
    et pas du cote TEMOIN, et le registre du port INSCRIT bien l'ability sur cette entite."""
    for c in stormboyz_cases:
        assert c.get("passivesGraft") == ["StormboyzStrike"], (
            "%s passives mesurees cote GREFFE = %r" % (_tag(c), c.get("passivesGraft")))
        assert "StormboyzStrike" not in (c.get("passivesControl") or []), (
            "%s le TEMOIN porte deja le passif : montage degenere" % _tag(c))
        assert c.get("registered") == ["StormboyzStrikeTeleportAbility"], (
            "%s `collect_triggered_abilities` n'inscrit pas l'ability : %r"
            % (_tag(c), c.get("registered")))
        assert c.get("sameEntityId") is True, (
            "%s ids d'entite differents entre les deux runners -- la comparaison ne porte pas "
            "sur la meme unite" % _tag(c))


def test_the_carrier_leaves_the_board_natively_at_ability_init(stormboyz_cases):
    """LA question binaire #1, cote NATIF. Le TEMOIN est sur le plateau, le GREFFE n'y est plus --
    et il est VIVANT : `RemoveUnitFromTilesOperation` retire des TUILES, il ne tue pas."""
    for c in stormboyz_cases:
        assert c["liveControl"]["pos"] is not None, (
            "%s montage : le TEMOIN est deja hors plateau" % _tag(c))
        assert c["liveGraft"]["pos"] is None and c["liveGraft"]["feet"] == [], (
            "%s le porteur NATIF garde une position : %r" % (_tag(c), c["liveGraft"]))
        assert c["liveGraft"]["alive"] is True


def test_the_teleporting_in_effect_lasts_exactly_two_turns(stormboyz_cases):
    """LE DISCRIMINANT du `turns`. `AddEffect(0x474, ..., turns: Nullable<int>(2))` passe une duree
    DEJA EN TOURS ; un `TurnsFromRounds(2)` vaudrait `2 * nbJoueurs` = 4 sur ces montages. Le natif
    rend `remaining = 2` -- c'est ce qui separe `duration_turns=2` de `duration_rounds=2`."""
    for c in stormboyz_cases:
        rows = [tuple(r) for r in c["liveGraft"]["effects"] if r[0] == TELEPORTING_IN]
        assert rows == [(TELEPORTING_IN, 2)], (
            "%s effet 1140 cote natif = %r (attendu remaining 2)" % (_tag(c), rows))
        assert not [r for r in c["liveControl"]["effects"] if r[0] == TELEPORTING_IN], (
            "%s le TEMOIN porte deja 1140" % _tag(c))


def test_port_and_native_states_agree_term_by_term(stormboyz_cases):
    """La confrontation complete du front 1 : position, empreinte, vie et la LISTE ENTIERE des
    effets (avec leur `remaining`), pas seulement 1140."""
    for c in stormboyz_cases:
        assert c.get("confrontAgree") is True, (
            "%s port=%r natif=%r" % (_tag(c), c.get("portAfter"), c.get("liveGraft")))


def test_the_port_actually_executed_the_behaviour(stormboyz_cases):
    """ANTI-TAUTOLOGIE #2 -- le test precedent serait vert si le port n'avait rien execute ET que le
    natif n'avait rien fait. On exige que le gate ait laisse passer sur l'entree rejouee."""
    for c in stormboyz_cases:
        assert c["portAfter"]["pos"] is None and c["portAfter"]["feet"] == [], (
            "%s le port n'a pas retire l'unite de ses tuiles : %r" % (_tag(c), c["portAfter"]))
        assert [r for r in c["portAfter"]["effects"] if r[0] == TELEPORTING_IN], (
            "%s le port n'a pose aucun 1140 : %r" % (_tag(c), c["portAfter"]))


def test_the_three_gates_refuse_when_they_must(stormboyz_cases):
    """Les TROIS predicats de `...StormboyzStrike_TeleportAbility$$CreateTrigger`, chacun exerce
    NEGATIVEMENT sur un etat ou il est le SEUL a changer :
      * `get_OwnerIsActor` -- evenement porte par une autre entite ;
      * `AmountIsEqual(UnitTurnsStarted(Owner), Direct(0))` -- l'etat CAPTURE a deja
        `turnsStarted == 1` (le tour du joueur a commence), et c'est une MESURE live ;
      * `NOT HasFlag(Owner, Moved)` -- flag pose a la main sur l'etat rejoue."""
    for c in stormboyz_cases:
        assert c.get("turnsStartedLive") == 1, (
            "%s turnsStarted mesure = %r (le montage suppose 1)" % (_tag(c),
                                                                    c.get("turnsStartedLive")))
        assert c.get("gateOnCapturedState") is False, (
            "%s le gate laisse passer alors que turnsStarted != 0" % _tag(c))
        assert c.get("gateWrongActor") is False, (
            "%s `get_OwnerIsActor` ne gate pas" % _tag(c))
        assert c.get("gateMoved") is False, (
            "%s `NOT HasFlag(Owner, Moved)` ne gate pas" % _tag(c))


def test_the_stormboyz_teleport_predicate_is_the_permissive_one(stormboyz_cases):
    """FRONT 2 -- l'hypothese `IsValidTeleportTile == true` devient une MESURE.

    Sur les montages dont le pathfinder effectif EST bien de la famille `StormboyzStrike`, le pool
    natif de l'unite hors plateau doit coincider EXACTEMENT avec le pool du port sous le predicat
    permissif, et le predicat concurrent (`TeleportStrike`, « aucun ennemi non-Steppable adjacent »)
    doit rendre STRICTEMENT MOINS -- sans quoi le montage ne discrimine rien."""
    valid = [c for c in stormboyz_cases if c.get("front2Valid")]
    assert valid, "aucun montage n'exerce le pathfinder StormboyzStrike"
    for c in valid:
        p = c["pools"]
        assert p["stormboyz_true"]["equal"] is True, (
            "%s pool natif=%s port(true)=%s extra=%s missing=%s"
            % (_tag(c), c["nativePool"], p["stormboyz_true"]["n"],
               p["stormboyz_true"]["extra"], p["stormboyz_true"]["missing"]))
        assert p["teleport_strike"]["n"] < c["nativePool"], (
            "%s le predicat concurrent rend %s pour un pool natif de %s : ce montage ne "
            "DISCRIMINE pas" % (_tag(c), p["teleport_strike"]["n"], c["nativePool"]))
        assert p["base_only"]["n"] == 0 and c["nativePool"] > 0, (
            "%s sans pool de teleport le port rendrait %s, le natif rend %s"
            % (_tag(c), p["base_only"]["n"], c["nativePool"]))


def test_a_higher_ranked_movement_effect_wins_the_dispatch(stormboyz_cases):
    """CONTRE-EPREUVE de la LECTURE du front 2. Le montage `bloodIntercessor` porte le trait
    `TeleportStrike`, donc l'effet `0x40b = 1035`, que
    `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit` teste AVANT `0x474` : son
    pathfinder n'est PAS celui de Stormboyz, et son pool natif suit le predicat de `TeleportStrike`.
    Sans ce garde-fou, ce montage se lirait comme une REFUTATION de l'hypothese (mesure du
    2026-08-01 : natif 28, port(true) 31, port(teleportStrike) 28)."""
    confounded = [c for c in stormboyz_cases if not c.get("front2Valid")]
    assert confounded, "le plan de test ne contient plus le montage CONFOND -- il garde la lecture"
    for c in confounded:
        assert c.get("family") == "TeleportStrike", (
            "%s famille de pathfinder = %r" % (_tag(c), c.get("family")))
        assert c["pools"]["teleport_strike"]["equal"] is True, (
            "%s le pool natif ne suit pas le predicat du rang gagnant : natif=%s port=%r"
            % (_tag(c), c["nativePool"], c["pools"]["teleport_strike"]))
