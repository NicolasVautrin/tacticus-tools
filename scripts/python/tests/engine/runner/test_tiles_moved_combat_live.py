"""CLIQUET de la FACE COMBAT de `ModifiedExoarmour_ExtraDmg` (1544) -- residu #322-r1.

CE QUE CE FICHIER GARDE, et pourquoi il n'existait pas avant : la face PREDICTION du passif de Kimm
(`votanChampion`) est bit-exacte sur 85 paires depuis #322, mais la face COMBAT rendait
SILENCIEUSEMENT `None` -- `att_ctx["tiles_moved_this_turn"]` n'y etait pas threade, et le port
n'avait AUCUN compteur de tuiles. Aucun test ne rougissait : l'effet rendait deja `None` avant le
port. Le degat REEL d'une charge de Kimm etait simplement sous-evalue.

LA CHAINE NATIVE, relue au decompile (`rnca9r7q6c`) :

    IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, tiles, state):
        if ((int)tiles < 1) return;
        comp[0xec] += tiles;   comp[0xf0] += tiles;      // ActorStatisticsComponent

    IdunBattle.Operations.MoveUnitOperation$$Execute, branche REELLE (options+0x16 == 0) :
        n = IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(connectedPath)   // Count - 1
        RecordTilesMoved(unit, n, state)

    IdunBattle.Operations.EndTurnOperation$$Execute, sur GetAllUnits :
        IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn(comp, wasOwnTurn)
            -> comp[0xf0] = 0    (INCONDITIONNEL)

Cote port : `runner/components.py::record_tiles_moved` (appele par `MoveUnitOperation`),
`reset_tiles_moved_this_turn` (appele par `EndTurnOperation`), et le threading dans
`runner/damage_model.py::attacker_modifiers`.

MESURE (le montage vit dans `probe_335_tiles_moved_combat.py`, qui monte un runner isole, DEPLACE
les unites pour imposer la longueur du pas, snapshote AVANT le pas et rejoue le pas offline) :

    MC1_67 / 909   pas=1  n=1  live == off == [3980, 4303]   (n=0 -> [3357, 3680])
                   pas=2  n=2  live == off == [5500, 5073]   (n=1 -> [4876, 4449])
    C1_25  / 31337 pas=1  n=1  live == off == [5233, 4301]
                   pas=3  n=4  live == off == [7049, 6124]   (n=1 -> [5177, 4252])

⚠ Le bras `C1_25` pas=3 rend **n = 4** pour une distance HEX de 3 : le chemin de marche fait un
detour. Le natif facture 4, le port aussi -- c'est la preuve que le compte vient du PATHFINDER
(`walk_pathfinder`, meme foyer que la face DECISION et que la face MOUVEMENT #304), pas d'une
distance hexagonale.

ASCII only.
"""
from __future__ import annotations

import pytest

import probe_335_tiles_moved_combat as TMC
from engine.entities.effects.base import tiles_moved_this_turn as att_ctx_tiles
from engine.runner.components import UnitComponent
from engine.runner.operations.turnflow import EndTurnOperation


@pytest.fixture(scope="module")
def tiles_moved_case(live_session):
    """Fabrique : `tiles_moved_case()` -> le dict de mesure du probe #335.

    Chaque appel monte UN runner isole (build + geometrie drivee + un bras par valeur de pas) et le
    DISPOSE en sortie. Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un skip
    sur un regime non atteint est un VERT qui ment."""
    cache: dict = {}

    def _case(steps=(1, 2), board: str = TMC.BOARD, seed: int = TMC.SEED) -> dict:
        key = (tuple(steps), board, seed)
        if key not in cache:
            res = None
            try:
                res = TMC.scenario(steps=tuple(steps), board=board, seed=seed, verbose=True)
            except RuntimeError as exc:
                pytest.fail(f"montage tiles-moved NON INSTALLE (board={board}, seed={seed}, "
                            f"pas={tuple(steps)}) : {exc}", pytrace=False)
            finally:
                if res is not None:
                    TMC.dispose(res)
            cache[key] = res
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def nominal(tiles_moved_case):
    """Bras nominal : MC1_67 / 909, un pas d'UNE tuile et un pas de DEUX."""
    return tiles_moved_case()


def _arms(res):
    return [res["arms"][k] for k in sorted(res["arms"])]


def test_combat_damage_matches_live_for_each_step(nominal):
    """CONTROLE PRINCIPAL -- pour CHAQUE longueur de pas, le degat de COMBAT rejoue offline est
    bit-exact avec le live.

    C'est ce qui etait faux avant #322-r1 : le port n'avait aucun compteur, donc il rendait le
    degat SANS le `V x n` que le natif applique -- silencieusement, sans qu'aucun test ne rougisse."""
    for arm in _arms(nominal):
        assert arm["n"] > 0, (
            "pas de %d tuile(s) : le port n'a enregistre AUCUNE tuile (n=%s) -- "
            "`MoveUnitOperation` n'appelle pas `record_tiles_moved`, ou le chemin n'est pas trouve"
            % (arm["steps"], arm["n"]))
        assert arm["off_per_hit"] == arm["live_per_hit"], (
            "pas de %d tuile(s) (n=%d) : le degat de COMBAT diverge -- live=%s offline=%s "
            "(delta/coup=%s)"
            % (arm["steps"], arm["n"], arm["live_per_hit"], arm["off_per_hit"],
               [o - l for l, o in zip(arm["live_per_hit"], arm["off_per_hit"])]))


def test_bonus_is_not_vacuous(nominal):
    """GARDE DE NON-VACUITE -- si le bonus valait ZERO, le controle principal comparerait live et
    offline A VIDE et ne prouverait plus rien du canal.

    Contrefactuel : le MEME etat, le MEME flux de PRNG, avec le compteur FORCE a 0 (= l'etat du port
    AVANT ce residu). Il doit DIVERGER du live, et vers le BAS (l'additif est positif)."""
    for arm in _arms(nominal):
        assert arm["off_per_hit_zero"] != arm["live_per_hit"], (
            "pas de %d tuile(s) : rejouer avec un compteur a ZERO rend EXACTEMENT les coups du live "
            "(%s) -- le montage n'active pas le passif, la garde principale ne mesure rien"
            % (arm["steps"], arm["live_per_hit"]))
        assert len(arm["off_per_hit_zero"]) == len(arm["live_per_hit"]), (
            "l'additif ne doit PAS changer la CARDINALITE des coups -- avec=%s sans=%s"
            % (arm["live_per_hit"], arm["off_per_hit_zero"]))
        assert sum(arm["live_per_hit"]) > sum(arm["off_per_hit_zero"]), (
            "l'additif `V x n` doit AUGMENTER le degat : live=%s sans compteur=%s"
            % (arm["live_per_hit"], arm["off_per_hit_zero"]))


def test_count_is_threaded_not_a_constant(nominal):
    """LE DISCRIMINANT -- le compte de tuiles est-il THREADE, ou est-ce une constante heureuse ?

    Un port qui facturerait `V x 1` quel que soit le pas passerait le controle principal sur un
    scenario a une seule valeur de `n`. On exige donc :
      (a) les deux bras ont des `n` DIFFERENTS (le montage varie bien la longueur du pas) ;
      (b) sur le bras a `n > 1`, rejouer avec le compteur FORCE a 1 DIVERGE du live.
    """
    arms = _arms(nominal)
    ns = sorted({a["n"] for a in arms})
    assert len(ns) >= 2, (
        "les bras rendent tous le meme compte %s -- le montage ne fait pas varier la longueur du "
        "pas, donc il ne peut pas distinguer `V x n` de `V x constante`" % (ns,))
    multi = [a for a in arms if a["n"] > 1]
    assert multi, "aucun bras avec n > 1 : le discriminant ne peut pas etre evalue"
    for arm in multi:
        assert arm["off_per_hit_n1"] != arm["live_per_hit"], (
            "pas de %d tuile(s) (n=%d) : rejouer avec le compteur FIGE a 1 rend EXACTEMENT les coups "
            "du live (%s) -- le degat ne depend donc PAS du nombre de tuiles, le port pourrait "
            "facturer une constante" % (arm["steps"], arm["n"], arm["live_per_hit"]))


def test_effect_magnitude_scales_with_the_count(nominal):
    """L'effet MATERIALISE cote runner, sa magnitude, et le gate `IsMeleeAttack`, lus sur l'objet.

    `ModifiedExoarmour_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` =
    `ForAddition(get_OwnerIsCaster & IsMeleeAttack, Multiply(ConfigVar(8=extraDmg),
    TilesMovedThisTurn(Self)))`. On verifie les DEUX faces du produit et le gate, sur l'instance
    reellement presente dans l'etat rejoue."""
    arm = _arms(nominal)[0]
    caster = arm["rec"]["caster"]
    st = arm["state"]
    eff = next((e for e in (st.effects.by_unit.get(caster) or [])
                if e.effect_type == TMC.EXOARMOUR_EFFECT_TYPE), None)
    assert eff is not None, (
        "l'effet %d ModifiedExoarmour_ExtraDmg n'est pas materialise sur Kimm (u%s) -- le scenario "
        "ne peut RIEN prouver du canal" % (TMC.EXOARMOUR_EFFECT_TYPE, caster))
    b1 = eff.create_effect_damage_bonus_for_attack(is_ranged=False,
                                                   att_ctx={"tiles_moved_this_turn": 1})
    b2 = eff.create_effect_damage_bonus_for_attack(is_ranged=False,
                                                   att_ctx={"tiles_moved_this_turn": 2})
    b0 = eff.create_effect_damage_bonus_for_attack(is_ranged=False,
                                                   att_ctx={"tiles_moved_this_turn": 0})
    rng = eff.create_effect_damage_bonus_for_attack(is_ranged=True,
                                                    att_ctx={"tiles_moved_this_turn": 2})
    assert b0 is None, "n = 0 -> aucune contribution (ActiveCondition), obtenu %s" % (b0,)
    assert rng is None, "gate IsMeleeAttack : aucune contribution a distance, obtenu %s" % (rng,)
    assert b1 is not None and b1.value and b1.value > 0, (
        "magnitude ConfigVar(8) non resolue (%s) -- niveau=%s mult=%s"
        % (b1, eff.ability_level, eff.ability_variables_multiplier))
    assert b2.value == 2 * b1.value, (
        "`Multiply(ConfigVar, TilesMovedThisTurn)` : le bonus doit etre PROPORTIONNEL au compte "
        "-- n=1 -> %s, n=2 -> %s" % (b1.value, b2.value))


def test_turn_end_resets_the_counter_live(nominal):
    """RESET DE FIN DE TOUR, confronte au LIVE par sa CONSEQUENCE.

    Aucun capteur ne publie `ActorStatisticsComponent+0xf0` (residu #322-r2), donc on ne LIT pas le
    reset : on lit son effet sur le degat. La MEME attaque, depuis la MEME tuile, un tour plus tard
    et SANS bouger, ne doit plus porter aucun `V x n` -- c'est
    `ActorStatisticsComponent$$ResetThisTurn` (`+0xf0 = 0` inconditionnel) que
    `EndTurnOperation$$Execute` applique a `GetAllUnits`.

    Contrefactuel : rejouer cette seconde attaque avec le compteur CONSERVE (la valeur du tour
    precedent) doit DIVERGER -- sinon la garde passerait meme si le natif ne remettait rien a zero."""
    sec = next((a["second"] for a in _arms(nominal) if "second" in a), None)
    assert sec is not None, "aucun bras ne porte la seconde attaque -- le reset n'est pas confronte"
    assert sec["n"] == 0, (
        "l'etat rejoue de la seconde attaque porte un compteur non nul (%s) : le montage ne mesure "
        "pas le regime « compteur remis a zero »" % sec["n"])
    assert sec["off_per_hit"] == sec["live_per_hit"], (
        "seconde attaque (tour suivant, sans bouger) : live=%s offline=%s"
        % (sec["live_per_hit"], sec["off_per_hit"]))
    assert sec["off_per_hit_kept"] != sec["live_per_hit"], (
        "rejouer la seconde attaque en CONSERVANT le compteur du tour precedent rend EXACTEMENT les "
        "coups du live (%s) -- ce montage ne peut donc pas voir un reset manquant"
        % (sec["live_per_hit"],))


def test_end_turn_operation_zeroes_the_counter_offline(nominal):
    """Le PORT du reset, sur l'etat rejoue : `EndTurnOperation.execute` doit remettre
    `tiles_moved_this_turn` a ZERO pour TOUTES les unites et rouler `tiles_moved_last_turn` pour
    celles du joueur qui FINIT (mirror de `ResetThisTurn(comp, wasOwnTurn)`).

    Pendant OFFLINE de la garde live ci-dessus : celle-la mesure que le NATIF remet a zero, celle-ci
    que le PORT le fait -- deux morceaux differents.

    ⚠ Etat NEUF (`offline_state` re-joue le pas depuis la capture) et non `arm["state"]` : ce test
    MUTE l'etat (c'est son objet), et `arm["state"]` est partage par tout le module."""
    arm = _arms(nominal)[-1]
    st = nominal["harness"].offline_state(arm["rec"])
    caster = arm["rec"]["caster"]
    e = st.get_entity(caster)
    uc = e.get_component(UnitComponent)
    assert uc.tiles_moved_this_turn == arm["n"] > 0, (
        "pre-condition : le compteur du caster doit valoir %s avant la fin de tour, obtenu %s"
        % (arm["n"], uc.tiles_moved_this_turn))
    before_battle = uc.tiles_moved_this_battle
    EndTurnOperation.execute(st, advance=False)
    assert uc.tiles_moved_this_turn == 0, (
        "`ActorStatisticsComponent$$ResetThisTurn` : `+0xf0` doit retomber a 0, obtenu %s"
        % uc.tiles_moved_this_turn)
    assert uc.tiles_moved_last_turn == arm["n"], (
        "`+0xf4 = +0xf0` pour une unite du joueur qui FINIT : attendu %s, obtenu %s"
        % (arm["n"], uc.tiles_moved_last_turn))
    assert uc.tiles_moved_this_battle == before_battle, (
        "`+0xec` est le cumul BATAILLE : `ResetThisTurn` n'y touche PAS (attendu %s, obtenu %s)"
        % (before_battle, uc.tiles_moved_this_battle))


def test_att_ctx_channel_is_threaded_by_the_runner(nominal):
    """Le CANAL lui-meme, au foyer partage : `attacker_modifiers` doit POSER la cle
    `tiles_moved_this_turn` dans l'`att_ctx` -- c'est exactement ce qui manquait (#322-r1).

    Sans cette cle, `effects.base.tiles_moved_this_turn` rend `None` (« non threade ») et l'effet
    ne contribue RIEN : la degradation est SILENCIEUSE, aucun test ne rougit. On la constate ici
    directement, pour que la regression se voie meme si les deltas de degat devenaient nuls."""
    from engine.runner.damage_model import attacker_modifiers
    arm = _arms(nominal)[-1]
    rec = arm["rec"]
    st = nominal["harness"].offline_state(rec)     # etat NEUF (cf. la garde du reset ci-dessus)
    captured = {}
    import engine.entities.effects.base as base_mod
    real = base_mod.tiles_moved_this_turn

    def _spy(att_ctx):
        captured["ctx"] = att_ctx
        return real(att_ctx)

    import engine.entities.effects.loki.extra_damage as ed
    ed.tiles_moved_this_turn = _spy
    try:
        attacker_modifiers(st, rec["caster"], None, is_ranged=False, target_id=rec["target"])
    finally:
        ed.tiles_moved_this_turn = real
    ctx = captured.get("ctx")
    assert ctx is not None, (
        "l'effet 1544 n'a pas ete interroge par `attacker_modifiers` -- il n'est pas dans les "
        "effets ACTIFS du caster (gate `is_active` ferme ?)")
    assert "tiles_moved_this_turn" in ctx, (
        "`attacker_modifiers` ne threade PAS la cle `tiles_moved_this_turn` dans l'att_ctx "
        "(cles=%s) -- l'effet rendrait `None` en silence" % sorted(ctx))
    assert att_ctx_tiles(ctx) == arm["n"] > 0, (
        "la cle threadee vaut %s, le compteur du port %s" % (att_ctx_tiles(ctx), arm["n"]))


@pytest.fixture(scope="module")
def other_board(tiles_moved_case):
    """GENERALISATION : autre plateau, autre seed, autre longueur de pas.

    `C1_25` porte du relief -- le pas de distance HEX 3 y coute **4 tuiles de chemin**. Si le port
    comptait en distance hexagonale au lieu de passer par le pathfinder, ce bras le dirait."""
    return tiles_moved_case(steps=(1, 3), board="C1_25", seed=31337)


def test_count_comes_from_the_pathfinder_not_hex_distance(other_board):
    """DISCRIMINANT GEOMETRIQUE -- sur `C1_25`, un pas de distance hex 3 rend un chemin de 4 tuiles.

    Le natif facture `GetNumTilesMoved(connectedPath) = Count - 1` sur le chemin du
    `WalkPathfinder`, jamais une distance hexagonale. Ce bras est celui qui separe les deux."""
    arms = _arms(other_board)
    detour = [a for a in arms if a["n"] != a["steps"]]
    assert detour, (
        "aucun bras de ce montage ne fait de DETOUR (n == distance hex partout : %s) -- il ne "
        "distingue donc pas le chemin du pathfinder d'une distance hexagonale"
        % [(a["steps"], a["n"]) for a in arms])
    for arm in arms:
        assert arm["off_per_hit"] == arm["live_per_hit"], (
            "C1_25/31337, pas de %d tuile(s) (n=%d) : live=%s offline=%s"
            % (arm["steps"], arm["n"], arm["live_per_hit"], arm["off_per_hit"]))
    for arm in detour:
        assert arm["off_per_hit_n1"] != arm["live_per_hit"], (
            "C1_25/31337, bras a detour (hex=%d, n=%d) : le compteur fige a 1 rend les coups du "
            "live -- le compte n'est pas threade" % (arm["steps"], arm["n"]))
