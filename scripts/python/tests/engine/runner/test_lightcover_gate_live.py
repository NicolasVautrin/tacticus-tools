"""A3 (#113) — gate compute-time LightCover (`AreEqual(coverPatch, target)` IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack) : le runner-sim
ne doit PAS sur-appliquer le -2 coups d'un LightCover PERIME (cible ayant quitte sa tuile de cover).

Board `SyncPvp_Arctic_06` (contient DryBush). On trouve (ou drive) un defenseur portant l'effet live
'LightCover' SUR une tuile DryBush, puis :
  - ON-COVER : combat offline -> coups ranged REDUITS (LightCover -2).
  - OFF-COVER : on DEPLACE le defenseur sur une tuile Grass (offline, effet LightCover CONSERVE = simule
    l'absence de retrait B1) -> coups = BASE. LightCover TOUJOURS present -> c'est le GATE (terrain != cover),
    pas un retrait d'effet, qui annule le -2.
Ancrage LIVE : la presence de 'LightCover' est IsActive-gate (present sur-DryBush, DROP hors-DryBush,
confirme live) -> off-cover = base est ce que fait le jeu. ASCII only. (Modele : test_getstuckin_combat_live.)
"""
from __future__ import annotations

from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, PositionComponent
from engine.entities.pathfinding.board import Board

COVER_TILE = "DryBush"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _bfs(board, src):
    d = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in d:
                d[n] = d[x] + 1; q.append(n)
    return d


def _eff_names(state, uid):
    e = state.get_entity(uid)
    if e is None or state.effects is None:
        return []
    hc = e.get_component(HealthComponent)
    return [getattr(x, "name", None)
            for x in state.effects.active_effects(uid, {"hp": hc.hp if hc else None})]


def _hits(state, att, tid):
    state.rng = IntBasedMersenneTwister()   # le NB de coups ne depend pas du seed (GetStuckIn off ici)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(att, tid))
    rr = runner.damage_handler.last
    return len((rr or {}).get("per_hit") or []), rr


@pytest.fixture(scope="session")
def lc_gate(live_session, rpc, build_runner):
    # Roster choisi pour que la MAGNITUDE soit observable, pas seulement le gate : le natif borne la
    # reduction par `min=Direct(1)`, donc un attaquant a peu de coups SATURE le plancher et rend
    # l'assertion de magnitude inoperante (mesure : templHelbrecht = 3 coups ranged -> on_hits=1 aussi
    # bien avec -2 qu'avec -3). `necroDestroyer` porte 6 coups ranged (Gauss, Range 2) et aucun trait
    # touchant le canal de coups -- le test garde ainsi du pouvoir discriminant tant que
    # `lightCoverHitReduction` reste < 5. Le garde-fou `off_hits - red > 1` ci-dessous le CONSTATE.
    b = build_runner("4242", extra=["--board", "SyncPvp_Arctic_06",
                                    "--p-units", "necroDestroyer", "--a-units", "necroDestroyer"])
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    if not any(t.get("tileDefId") == COVER_TILE for t in bg["tiles"]):
        pytest.skip("board sans DryBush (capteur tileDefId absent ?)")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live incomplete")
    units = dv.get("units") or []

    def has_lc(u):
        return any(e.get("name") == "LightCover" for e in (u.get("effects") or []))
    defender = next((u for u in units if has_lc(u) and u.get("alive")), None)
    if defender is None:
        pytest.skip("aucune unite avec LightCover (aucun spawn sur DryBush)")
    tid = defender["id"]
    dp = defender.get("pos") or {}
    if board.terrain_at(dp.get("col"), dp.get("row")) != COVER_TILE:
        pytest.skip("porteur LightCover pas sur DryBush (etat live incoherent)")
    attacker = next((u for u in units if u.get("id") != tid and u.get("alive")), None)
    if attacker is None:
        pytest.skip("pas d'attaquant")
    att = attacker["id"]
    dtile = board.id_at(dp["col"], dp["row"])

    # attaquant a hex-dist 2 (ranged), hors-cover (isole le defenseur)
    dist = _bfs(board, dtile)
    ranged = [t for t, dd in dist.items() if dd == 2 and board.walkable(t)
              and board.tile_def_id(t) != COVER_TILE]
    if not ranged:
        pytest.skip("pas de tuile ranged libre a dist 2")
    apos = board.coord(ranged[0])

    def place(state, uid, col, row):
        state.get_entity(uid).get_component(PositionComponent).col = col
        state.get_entity(uid).get_component(PositionComponent).row = row

    # (a) ON-COVER
    st = load_state(dv, ob, snap, board=board)
    place(st, att, *apos)
    on_eff = _eff_names(st, tid)
    on_hits, _ = _hits(st, att, tid)

    # (b) OFF-COVER : defenseur DEPLACE sur Grass a dist 2 de l'attaquant, LightCover CONSERVE
    dist_a = _bfs(board, ranged[0])
    grass = [t for t, dd in dist_a.items() if dd == 2 and board.walkable(t)
             and board.tile_def_id(t) == "Grass"]
    if not grass:
        pytest.skip("pas de tuile Grass a dist 2 de l'attaquant")
    st2 = load_state(dv, ob, snap, board=board)
    place(st2, att, *apos)
    place(st2, tid, *board.coord(grass[0]))
    off_eff = _eff_names(st2, tid)
    off_terr = board.terrain_at(*board.coord(grass[0]))
    off_hits, _ = _hits(st2, att, tid)
    return {"on_hits": on_hits, "off_hits": off_hits, "on_eff": on_eff, "off_eff": off_eff,
            "off_terr": off_terr, "tid": tid, "att": att}


def test_lightcover_gate_drops_offcover(lc_gate):
    """La reduction LightCover CHUTE quand le defenseur quitte sa tuile de cover, MEME si l'effet
    persiste : on_hits == max(1, off_hits - hitsReduction), off_hits > on_hits, et 'LightCover' present
    les DEUX fois (=> c'est le gate `AreEqual(coverPatch,target)`, pas un retrait d'effet).
    Anti-regression du runner-sim stale.

    ORACLE DE MAGNITUDE (rien de fige ici) : le decompile de
    `IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack` donne
    `ForAdditionWithMinimum(AreEqual(Tiles(coverPatch), Tiles(target)) & !IsMeleeAttack,
    Direct(-AbilityConfiguration.GetNumberConstant(0x2c)), min=Direct(1))`. LightCoverAbility etant une
    ability de TUILE (absente de `units.abilities`), sa config vit dans les valeurs globales :
    ConfigConst 0x2c = `globalValues.lightCoverHitReduction`. Le test lit cet oracle et derive
    l'attendu (plancher `Direct(1)` compris) au lieu de figer la mesure du jour."""
    import gameconfig as GC
    red = GC.global_value("lightCoverHitReduction")
    assert red is not None, ("oracle introuvable : globalValues.lightCoverHitReduction absent de "
                             "gameconfig (GetNumberConstant(0x2c) non resolvable offline)")
    red = int(red)
    assert red > 0, (f"oracle incoherent : lightCoverHitReduction={red}, or le natif construit "
                     f"Direct(-GetNumberConstant(0x2c)) -- une constante positive est attendue")
    c = lc_gate
    print("\n[LC-GATE] oracle lightCoverHitReduction=%d on_hits=%d off_hits=%d on_eff=%s off_terr=%s "
          "off_eff=%s" % (red, c["on_hits"], c["off_hits"], c["on_eff"], c["off_terr"], c["off_eff"]))
    assert "LightCover" in c["on_eff"], "LightCover absent on-cover (setup KO)"
    assert "LightCover" in c["off_eff"], (
        "LightCover retire off-cover -> le test ne prouve PAS le gate (il faudrait l'effet PRESENT)")
    # Le plancher natif `min=Direct(1)` peut ABSORBER la magnitude : si off_hits - red <= 1, toute
    # magnitude >= off_hits - 1 rend le meme on_hits=1 et l'egalite ci-dessous ne prouve plus rien.
    # On le dit fort plutot que de laisser un vert non discriminant (mesure : 3 coups + red=2 -> le
    # test passait avec un port fige a 3).
    assert c["off_hits"] - red > 1, (
        f"setup NON discriminant : off_hits={c['off_hits']} et lightCoverHitReduction={red} -> le "
        f"plancher min=Direct(1) sature, l'assertion de magnitude ne peut plus rougir. Il faut un "
        f"attaquant a plus de coups ranged (cf. choix du roster dans la fixture).")
    assert c["off_hits"] > c["on_hits"], (
        f"off_hits {c['off_hits']} <= on_hits {c['on_hits']} : le -{red} LightCover ne chute pas "
        f"hors-cover")
    assert c["on_hits"] == max(1, c["off_hits"] - red), (
        f"on_hits {c['on_hits']} != max(1, off {c['off_hits']} - {red}) (oracle "
        f"globalValues.lightCoverHitReduction) : gate LightCover mal applique")
