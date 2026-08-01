"""GARDE #366-r1 tranche 2 (OFFLINE PURE) -- `GrapnelLauncher` (active 1090), face COMBAT.

CE QU'ELLE PROTEGE, et pourquoi chaque bloc peut regresser SILENCIEUSEMENT :

  1. **LA GEOMETRIE DU PULL** -- `IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180Front`,
     l'arc AVANT (vers le tireur) a UN hex de la cible. C'est l'exact SYMETRIQUE de l'arc ARRIERE du
     push (`GetMinimumTiles180Behind`), et se tromper de signe donnerait un PUSH deguise en pull --
     un port qui « bouge la cible d'un hex » a tous les coups, sans qu'aucun test de mouvement ne
     rougisse.
  2. **L'ORDRE `pull` PUIS `attaque`**, lu verbatim dans l'`op_Addition` du decompile. **L'i2 dit
     l'INVERSE** (« deals damage to it. ... it is then pulled ») : c'est le seul endroit ou le port
     et le texte du jeu divergent, donc le seul endroit ou une « correction » de bonne foi peut
     casser la fidelite.
  3. **LE QUIRK « CIBLE DEJA ADJACENTE »** : l'arc AVANT se reduit alors a la tuile du CASTER, et
     `FindTileToPullOnce` n'applique son filtre `IsEmptyOrSteppable` que si la liste a PLUS d'une
     tuile -- il rend donc une tuile OCCUPEE, ce qui envoie la queue commune sur
     `ApplyKnockbackTo(caster, target, doIt = 1)`. L'i2 est muet la-dessus.
  4. **LES DEUX LITTERAUX DU REGISTRE** : `rules = 0x8004000` (forme FLAGS DIRECTS, 6 arguments) et
     `AbilityAttackType` = 0 = `DirectTargetAttack`.
  5. **LA CLE `"knockbackRange "`** du gameconfig -- avec un ESPACE FINAL. Le natif ne la voit pas
     (son dictionnaire est indexe par l'ENUM `AbilityConstantType`, et `Enum.Parse` TRIM) ; le port,
     qui lit le JSON par nom, rendait `None` -> aucun knockback de denivele. Repli TRIMME pose dans
     `engine/entities/effects/magnitude.py::_lookup_config_key`.

Mesure live : `python scripts/python/probe_366_r1_grapnel_launcher.py`.
RE : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` section 6. ASCII only, aucune VA.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.battle_query import get_minimum_tiles_180_front              # noqa: E402
from engine.entities import EffectsState                                 # noqa: E402
from engine.entities.effects.magnitude import _lookup_config_key, ability_var  # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.spacewolves import GrapnelLauncherAbility    # noqa: E402
from engine.runner.abilities.targeting import (RANGE_FROM_CONFIG, RANGED_BOOL_FALSE,  # noqa: E402
                                               TargetingOptions)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.components import PositionComponent                   # noqa: E402
from engine.runner.operations.displace import PullUnitOneTileOperation   # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

GRAPNEL = 1090                   # ActiveAbilityType.GrapnelLauncher
# `GrapnelLauncherAbility$$.ctor` : forme FLAGS DIRECTS a 6 arguments -> le litteral EST le masque.
NATIVE_MASK = 0x8004000
COLS, ROWS = 9, 9
CASTER, FOE, ALLY = 10, 20, 30


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles(walls=()) -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": (col, row) not in walls,
                        "isWall": (col, row) in walls, "neighbours": nb})
    return out


def _state(caster_pos, foe_pos, ally_pos=None, walls=()):
    board = Board(_tiles(walls), adjacency="evenq")
    units = [
        {"id": CASTER, "visualId": "spaceHound", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": caster_pos[0], "row": caster_pos[1]}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": foe_pos[0], "row": foe_pos[1]}, "effects": []},
    ]
    if ally_pos is not None:
        units.append({"id": ALLY, "visualId": "spaceRockfist", "alive": True, "team": 1, "owner": 1,
                      "pos": {"col": ally_pos[0], "row": ally_pos[1]}, "effects": []})
    observe = {"units": [{"squadId": u["id"], "hp": 100000, "hpMax": 100000} for u in units]}
    st = load_state({"currentPlayer": 1, "units": units}, observe, board=board)
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _pos(st, uid):
    e = st.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return None if pc is None else (pc.col, pc.row)


# ------------------------------------------------------- 1. LA GEOMETRIE DE L'ARC AVANT

def test_front_arc_is_one_hex_toward_the_puller_not_away():
    """L'invariant qui separe un PULL d'un PUSH : chaque candidate est a UN hex de la cible ET
    STRICTEMENT plus proche du tireur. Un signe inverse (l'arc ARRIERE du push) donnerait
    `d(cand, tireur) == d + 1`."""
    for caster, foe in (((5, 3), (3, 3)), ((3, 1), (3, 4)), ((2, 2), (5, 4)), ((0, 0), (3, 1))):
        cands = get_minimum_tiles_180_front(caster, foe)
        d = hexgeo.distance(caster, foe)
        assert cands, "arc AVANT vide pour %r -> %r" % (caster, foe)
        for c in cands:
            assert hexgeo.distance(c, foe) == 1
            assert hexgeo.distance(c, caster) == d - 1


def test_front_arc_of_an_adjacent_target_is_the_caster_tile_itself():
    """LE QUIRK, a la racine : cible au contact -> l'unique candidate EST la tuile du tireur."""
    assert get_minimum_tiles_180_front((4, 3), (3, 3)) == [(4, 3)]


def test_front_arc_yields_two_candidates_off_axis():
    """Cas NON aligne (aucune composante cube nulle, un ex-aequo au min/max) : le natif ajoute DEUX
    vecteurs et TIRE ensuite -- c'est la seule source de RNG de cette ability."""
    assert len(get_minimum_tiles_180_front((5, 3), (3, 3))) == 2


def test_front_arc_omits_a_wall_but_ignores_elevation():
    """`AddNewTileToList(..., checkWalkability = 1, checkElevation = isReachable = 0)` : l'i2 « can be
    pulled over any elevation but not through impassable terrain », lu au litteral."""
    blocked = get_minimum_tiles_180_front(
        (3, 1), (3, 4), walkable_at=lambda p: p != (3, 3), tile_exists=lambda p: True)
    assert blocked == []
    high = get_minimum_tiles_180_front(
        (3, 1), (3, 4), walkable_at=lambda p: True,
        elevation_at=lambda p: 0 if p == (3, 4) else 9, tile_exists=lambda p: True)
    assert high == [(3, 3)], "le gate d'elevation ne doit PAS s'armer (checkElevation = 0)"


# ------------------------------------------------------- 2. L'OPERATION DE PULL

def test_pull_moves_the_target_one_hex_toward_the_puller():
    st = _state((3, 1), (3, 4))
    res = PullUnitOneTileOperation(CASTER, FOE).execute(st, None)
    assert res["moved"] is True and res["to"] == (3, 3)
    assert _pos(st, FOE) == (3, 3)


def test_pull_of_an_adjacent_target_does_not_move_it_and_knocks_it_back():
    """LE QUIRK, cote operation : la seule candidate est la tuile du tireur -> `IsFilled` -> aucun
    deplacement, mais `ApplyKnockbackTo(caster, target)`. L'occupant etant le tireur LUI-MEME,
    `IsEnemy(caster, caster)` est faux -> un SEUL knockback, sur la cible."""
    st = _state((4, 3), (3, 3))
    hp0 = st.get_entity(FOE).get_component(
        __import__("engine.runner.components", fromlist=["HealthComponent"]).HealthComponent).hp
    res = PullUnitOneTileOperation(CASTER, FOE).execute(st, None)
    assert res["moved"] is False and res["reason"] == "occupied"
    assert _pos(st, FOE) == (3, 3)
    kb = res.get("knockback") or []
    assert len(kb) == 1 and kb[0]["unit"] == FOE
    assert kb[0]["amount"] == -(-100000 * 20 // 100)      # ceil(maxHealth x KnockbackPercentage/100)
    hp1 = st.get_entity(FOE).get_component(
        __import__("engine.runner.components", fromlist=["HealthComponent"]).HealthComponent).hp
    assert hp1 < hp0


def test_pull_blocked_by_a_wall_knocks_back_without_moving():
    """Arc AVANT VIDE (`FindTileToPullOnce` rend null) -> `ApplyKnockbackTo` seul, aucun move."""
    st = _state((3, 1), (3, 4), walls=((3, 3),))
    res = PullUnitOneTileOperation(CASTER, FOE).execute(st, None)
    assert res["moved"] is False and res["reason"] == "blocked"
    assert _pos(st, FOE) == (3, 4)
    assert len(res.get("knockback") or []) == 1


def test_pull_over_a_two_level_drop_pays_the_elevation_knockback():
    """`if (elevationDifferenceForKnockback.HasValue && value <= |elev(dest) - elev(origine)|)
    ApplyKnockbackTo(...)` -- et le deplacement a QUAND MEME lieu."""
    tiles = _tiles()
    for t in tiles:
        if (t["col"], t["row"]) == (3, 4):
            t["elevation"] = 3
    board = Board(tiles, adjacency="evenq")
    units = [{"id": CASTER, "visualId": "spaceHound", "alive": True, "team": 1, "owner": 1,
              "pos": {"col": 3, "row": 1}, "effects": []},
             {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
              "pos": {"col": 3, "row": 4}, "effects": []}]
    observe = {"units": [{"squadId": u["id"], "hp": 100000, "hpMax": 100000} for u in units]}
    st = load_state({"currentPlayer": 1, "units": units}, observe, board=board)
    res = PullUnitOneTileOperation(CASTER, FOE, elevation_knockback=2).execute(st, None)
    assert res["moved"] is True and res["to"] == (3, 3)
    assert len(res.get("knockback") or []) == 1, "denivele 3 >= seuil 2 -> knockback du"
    res2 = PullUnitOneTileOperation(CASTER, FOE, elevation_knockback=9).execute(
        _state((3, 1), (3, 4)), None)
    assert res2["moved"] is True and not res2.get("knockback"), "seuil 9 -> aucun knockback"


# ------------------------------------------------------- 3. L'ARBRE COMPLET

def test_cast_pulls_then_attacks_then_flies_into_the_freed_tile():
    """LE CAS NOMINAL, et l'ORDRE des trois etages : la cible recule d'un hex, l'attaque part, puis
    le caster occupe la tuile d'ORIGINE de la cible (`First(cache)` = le cache PRE-pull)."""
    st = _state((3, 1), (3, 4))
    out = GrapnelLauncherAbility().execute_behaviour(st, CASTER, FOE)
    assert out["pull"]["moved"] is True and out["pull"]["to"] == (3, 3)
    assert _pos(st, FOE) == (3, 3)
    # `attacked` = le noeud d'attaque a ete TRAVERSE, donc le gate `NOT IsDead(Target)` etait vrai.
    # (Le PAYLOAD `main_attack` reste None hors runner : l'Operation saute le degat quand `state.rng`
    # n'est pas cale -- c'est le mode replay effet-seul, commun a tous les tests offline.)
    assert out["attacked"] is True, "l'attaque doit partir (cible vivante apres le pull)"
    assert out["fly"]["moved"] is True and out["fly"]["to"] == (3, 4)
    assert _pos(st, CASTER) == (3, 4), "le caster occupe la tuile d'ORIGINE de la cible"


def test_the_cache_freezes_the_pre_pull_tile_not_the_live_one():
    """CONTRE-EPREUVE du `Cache` (meme piege que #27 sur ThunderousAssault) : sans memoisation, le
    `First(Tiles(Target))` relu APRES le pull donnerait la tuile d'ARRIVEE (occupee) et le caster ne
    volerait jamais. On exige donc que la destination du vol soit la tuile PRE-pull, DIFFERENTE de la
    position finale de la cible."""
    st = _state((3, 1), (3, 4))
    out = GrapnelLauncherAbility().execute_behaviour(st, CASTER, FOE)
    assert out["fly"]["to"] == (3, 4) and _pos(st, FOE) == (3, 3)
    assert out["fly"]["to"] != _pos(st, FOE)


def test_cast_on_an_adjacent_target_knocks_back_and_flies_to_an_adjacent_free_tile():
    """LE QUIRK, cote arbre. La cible ne bouge pas et prend le knockback ; la tuile d'origine reste
    OCCUPEE -> `IsCanAddUnit(First(cache))` est FAUX -> branche `else` : le caster vole sur une tuile
    LIBRE adjacente a cette tuile d'origine (`PickRandomly(CanAddUnit(AdjacentTiles(cache)))`)."""
    st = _state((4, 3), (3, 3))
    out = GrapnelLauncherAbility().execute_behaviour(st, CASTER, FOE)
    assert out["pull"]["moved"] is False and out["pull"]["reason"] == "occupied"
    assert (out["pull"]["knockback"] or [])[0]["unit"] == FOE
    assert _pos(st, FOE) == (3, 3)
    assert out["fly"]["moved"] is True
    assert hexgeo.distance(out["fly"]["to"], (3, 3)) == 1


def test_the_dead_branch_frees_the_origin_tile_only_when_the_pull_failed():
    """`If(IsDead(Target) & AreEqual(TargetTiles, cache), KillDeadUnits + If(IsDead,
    RemoveUnitFromItsTiles))`. `AreEqual` = « la cible est TOUJOURS sur sa tuile d'origine », donc la
    branche ne s'arme QUE si le pull a echoue -- si le pull a reussi, la tuile est deja libre.
    Ici le pull REUSSIT : la cible bouge, le `AreEqual` est FAUX, et le caster vole quand meme."""
    st = _state((3, 1), (3, 4))
    out = GrapnelLauncherAbility().execute_behaviour(st, CASTER, FOE)
    assert _pos(st, FOE) == (3, 3)
    assert out["fly"]["to"] == (3, 4)


def test_the_fly_never_lands_on_an_occupied_tile():
    """Garde-fou de la branche `else` : un allie plante sur toutes les voisines libres de la tuile
    d'origine ne doit jamais etre ecrase. Ici la cible est adjacente (pull impossible) et un allie
    occupe une voisine -- le caster ne peut pas s'y poser."""
    st = _state((4, 3), (3, 3), ally_pos=(3, 2))
    GrapnelLauncherAbility().execute_behaviour(st, CASTER, FOE)
    assert _pos(st, CASTER) != (3, 2) and _pos(st, CASTER) != (3, 3)
    assert _pos(st, ALLY) == (3, 2)


# ------------------------------------------------------- 4. LE REGISTRE ET LA CONFIG

def test_registry_carries_both_native_literals():
    """Une ability qui entre dans `ABILITY_CLASSES` pose son masque ET son `AbilityAttackType` DANS
    LE MEME COMMIT. Les deux sont RELUS au `$$.ctor` (forme flags directs, 6 arguments)."""
    assert ABILITY_CLASSES[GRAPNEL] is GrapnelLauncherAbility
    opts = GrapnelLauncherAbility.TARGETING_OPTIONS
    assert int(opts.rules) == NATIVE_MASK
    assert int(opts.rules) == int(TR.TargetIsEnemy | TR.TargetIsInRange), (
        "0x8004000 se decompose EXACTEMENT en ces deux bits, sans residu")
    assert opts.self_cast is False and opts.range == RANGE_FROM_CONFIG
    assert opts.force_melee_target == RANGED_BOOL_FALSE
    assert isinstance(opts, TargetingOptions)
    assert ABILITY_ATTACK_TYPE[GRAPNEL] == AbilityAttackType.DirectTargetAttack


def test_the_knockback_range_constant_survives_its_trailing_space():
    """La cle du gameconfig est `"knockbackRange "`. Le natif la lit par l'ENUM (`Enum.Parse` TRIM) ;
    le port doit rendre 2, pas None -- sinon le knockback de denivele est ETEINT en silence."""
    assert ability_var("GrapnelLauncher", "knockbackRange", is_constant=True) == 2
    assert ability_var("GrapnelLauncher", "range", is_constant=True) == 3
    assert ability_var("GrapnelLauncher", "nrOfHits", is_constant=True) == 1


def test_the_trimmed_lookup_refuses_an_ambiguous_match():
    """Le repli n'est tente QUE si la cle exacte manque, et il exige une correspondance UNIQUE : deux
    variantes qui trimment pareil rendent None plutot qu'un choix arbitraire."""
    assert _lookup_config_key({"a ": 1}, "a") == 1
    assert _lookup_config_key({"a": 1, "a ": 2}, "a") == 1        # exacte d'abord
    assert _lookup_config_key({"a ": 1, " a": 2}, "a") is None    # ambigu -> None
    assert _lookup_config_key({}, "a") is None


@pytest.mark.parametrize("caster,foe", [((3, 1), (3, 4)), ((5, 3), (3, 3)), ((4, 3), (3, 3))])
def test_the_cast_never_leaves_two_units_on_the_same_tile(caster, foe):
    """Invariant transverse : quel que soit le regime (pull droit, pull a deux candidates, quirk
    adjacent), aucune paire d'unites vivantes ne partage une tuile a la fin du cast."""
    st = _state(caster, foe)
    GrapnelLauncherAbility().execute_behaviour(st, CASTER, FOE)
    seen = {}
    for uid in (CASTER, FOE):
        p = _pos(st, uid)
        if p is not None:
            assert p not in seen, "collision sur %r entre %r et %r" % (p, seen.get(p), uid)
            seen[p] = uid
