"""Residu O3 — EVOLUTION des effets portes par une TUILE (le SEED etait deja fidele, cf. case-102).

Deux faces, deux gardes :

A. EXPIRATION. `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` n'itere PAS les unites : il
   enumere TOUTES les entites-EFFET du state (meme collection generique que consomme
   `IdunBattle.Entities.EntityExtensions$$GetEffectsBySourceUnit`) et applique
   `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` = `if (0 < Duration@+0x64) Duration--`
   (decrement CLAMPE a 0), sous le gate `!Removed@+0x5f && HasTurns@+0x5d`. Puis
   `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` teste
   `IdunBattle.Entities.Components.EffectComponent$$ShouldBeRemoved` = `HasTurns && Duration == 0` et
   prend la branche `DeactivateEffect` + RETRAIT : a 0, l'entite-effet N'EXISTE PLUS.
   Le port decrementait bien (le tick balaye toutes les cles de `by_unit`, tuiles comprises) mais ne
   RETIRAIT rien : `has_effect` et `collect_effect_triggers` ne filtrent que `consumed`, jamais
   `expired`. Pour une TUILE, dont c'est le SEUL chemin de lecture, le feu brulait pour toujours.

B. TRANSITION D'ENTREE. `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$CreateTrigger`
   = `(On(0x19=MatchInit) | On(0x33=UnitAdded) | On(0x24=UnitPositionChanged_1) | On(0x2e=UnitRevived)
   | On(0x2f=UnitResurrected)) & NOT AmountIsZero(UnitsThatNeedEffect)` ;
   `$$CreateBehaviour` = `AddEffect(0x3f5 = 1013 LightCover, AbilityStateReference, UnitsThatNeedEffect)`.
   `On(0x24)` est le PREMIER des trois events d'`IdunBattle.Operations.MoveUnitOperation$$
   EvaluateAfterMoveTriggers` : une unite qui ENTRE sur une tuile de cover recoit l'effet. Le port ne
   posait rien (seul le seed connaissait les unites deja a couvert). La SORTIE, elle, est deja fidele :
   le natif CONSERVE l'effet et le neutralise par le gate compute-time `AreEqual(coverPatch, target)`
   de `IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack` (porte, A3).

ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
import gameconfig as GC
from engine.runner.state import State
from engine.runner.runner import Runner
from engine.runner.messages import MoveUnitMessage
from engine.runner.snapshot import load_state
from engine.entities.effects_state import EffectsState
from engine.entities.effects import EffectFactory
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.operations.turnflow import EndTurnOperation
from engine.runner.operations.triggers.loki import FIRE_TILE, FIRE_DMG_PCT_KEY

W, H, MV_VIN = 7, 9, 3
P_UNITS = "adeptRetributor"          # arme hits=4 DamageProfile=Flame Range=2 -> pose le feu
HP_TARGET = 500000                   # la cible survit largement aux ticks de DoT
COVER_BOARD = "MC1_67"               # arene par defaut : 3 tuiles DryBush (cf. runner.md 2bis)


# ============================================================ A. offline (aucune session requise)

def test_tile_effect_timer_expires_and_is_removed_offline():
    """MESURE du residu O3, cote port pur. Un effet de TUILE a timer (`FireEffect` 5, remaining=2)
    doit disparaitre APRES 2 ticks de fin de tour -- et le compteur ne doit JAMAIS passer sous 0
    (`RemoveOneTurn` clampe). AVANT le fix : `has_effect` restait True indefiniment et le compteur
    descendait a -4 en 6 tours. Un effet PERMANENT (remaining capte = 0 -> `HasTurns` faux) n'est
    jamais touche."""
    st = State()
    st.current_player_id = 1
    st.effects = EffectsState()
    tile_id, unit_id = 9001, 7
    fire = EffectFactory.create({"name": "Fire", "effectType": int(FIRE_TILE), "level": 1,
                                 "remaining": 2, "source": None})
    perm = EffectFactory.create({"name": "LightCover", "effectType": int(EffectType.LightCover),
                                 "level": 1, "remaining": 0, "source": None})
    st.effects.add_effect(tile_id, fire)
    st.effects.add_effect(unit_id, perm)
    assert fire.remaining_turns == 2 and perm.remaining_turns is None

    seen = []
    for _ in range(6):
        EndTurnOperation.execute(st, advance=False)
        seen.append((fire.remaining_turns,
                     st.effects.has_effect(tile_id, effect_type=int(FIRE_TILE))))
    print(f"\n[O3/A offline] (remaining, has_effect) par tick = {seen}")
    assert seen[0] == (1, True), f"tick 1 : {seen[0]} (le feu doit encore bruler)"
    assert seen[1] == (0, False), f"tick 2 : {seen[1]} (le feu doit etre RETIRE, ShouldBeRemoved)"
    assert all(s == (0, False) for s in seen[2:]), \
        f"apres retrait, l'etat doit etre STABLE a (0, False) : {seen[2:]}"
    assert min(r for r, _ in seen) == 0, \
        "le compteur est passe sous 0 : `RemoveOneTurn` clampe (`if (0 < Duration) Duration--`)"
    assert not perm.consumed and st.effects.has_effect(unit_id,
                                                       effect_type=int(EffectType.LightCover)), \
        "un effet PERMANENT (HasTurns faux) ne doit jamais etre retire par le tick"


# ============================================================ helpers live

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _alive(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _endturn(rpc, rid):
    try:
        rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    except Exception:
        pass


def _skip_enemy(rpc, rid, me):
    for _ in range(6):
        if rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60).get("currentPlayer") == me:
            return
        _endturn(rpc, rid)


def _tile_rows(rpc, rid):
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    return (tm.get("tiles") if isinstance(tm, dict) else tm) or [], tm


def _fire_remaining_live(rows, pos):
    """`remaining` du `FireEffect` porte par la tuile `pos` cote LIVE, ou None si elle ne brule pas."""
    for t in rows:
        if (t.get("col"), t.get("row")) == pos:
            for e in (t.get("effects") or []):
                if int(e.get("effectType") or -1) == int(FIRE_TILE):
                    return int(e.get("remaining") or 0)
    return None


def _setup_vindicta(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    vin = next((u["id"] for u in _alive(dv) if u.get("visualId") == P_UNITS), None)
    tgt = next((u["id"] for u in _alive(dv) if u.get("visualId") != P_UNITS), None)
    norm = None
    for u in (dv.get("units") or []):
        if u.get("id") == vin:
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    norm = ab.get("id") if ab.get("id") is not None else ab.get("abilityId")
    if vin is None or tgt is None or norm is None:
        pytest.skip("roster/attaque normale introuvables")
    return vin, tgt, norm, dv.get("currentPlayer")


def _drive_until_burning(rpc, rid, vin, tgt, norm, me, max_rounds=8):
    """Approche Vindicta a distance 2 EXACTEMENT (au contact son arme est Physical, pas Flame) et
    attaque jusqu'a ce que la tuile de la cible brule. Recette identique a
    `test_env_fire_tile_migration_live.py` (deja verte)."""
    for _ in range(max_rounds):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        tu = next((u for u in (dec.get("units") or []) if u.get("id") == tgt), None)
        vu = next((u for u in _alive(dec) if u.get("id") == vin), None)
        if tu is None or not tu.get("alive") or vu is None:
            return False
        vp, tp = _pos(vu), _pos(tu)
        rows, _ = _tile_rows(rpc, rid)
        if _fire_remaining_live(rows, tp) is not None:
            return True
        occ = {_pos(u) for u in _alive(dec)} - {vp}
        if hexgeo.distance(vp, tp) != 2:
            ring2 = [t for t in hexgeo.ring(tp[0], tp[1], 2)
                     if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ
                     and hexgeo.distance(vp, t) <= MV_VIN]
            ring2.sort(key=lambda t: hexgeo.distance(vp, t))
            cands = ring2 or sorted(
                [t for t in hexgeo.disk(vp[0], vp[1], MV_VIN)
                 if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ and t != vp],
                key=lambda t: hexgeo.distance(t, tp))[:6]
            for t in cands:
                r = rpc("applyAction", {"runnerId": rid, "actions": [
                    {"kind": "move", "unitId": vin, "to": {"col": t[0], "row": t[1]}}]}, 60)
                if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
                    vp = t
                    break
        if hexgeo.distance(vp, tp) == 2:
            rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "ability", "casterId": vin, "targetId": tgt, "abilityType": norm}]}, 90)
        _endturn(rpc, rid)
        _skip_enemy(rpc, rid, me)
    return False


# ============================================================ A. live : le feu s'ETEINT au bon tour

def test_tile_fire_expires_at_the_same_turn_as_live(rpc, build_runner):
    """CONFRONTATION du volet A. On allume la tuile de la cible LIVE, on charge l'etat offline avec
    ses effets de tuile (`load_state(tiles=tileMeta)`, #102), puis on avance les DEUX cotes du MEME
    nombre de tours en ne faisant plus RIEN (aucune re-ignition). Le tour ou le feu disparait doit
    etre le MEME. AVANT le fix, l'offline ne s'eteignait jamais -> le test est binaire."""
    rid = build_runner("90311", extra=["--p-units", P_UNITS, "--a-units", "darkaTerminator",
                                       "--hp-target", str(HP_TARGET)])["rid"]
    vin, tgt, norm, me = _setup_vindicta(rpc, rid)
    if not GC.global_value(FIRE_DMG_PCT_KEY):
        pytest.skip("fireDmgPct absent du gameconfig")
    assert _drive_until_burning(rpc, rid, vin, tgt, norm, me), \
        "la tuile de la cible n'a pas pris feu -> montage non exerce"

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rows, tm = _tile_rows(rpc, rid)
    tp = _pos(next(u for u in _alive(dec) if u.get("id") == tgt))
    rem0 = _fire_remaining_live(rows, tp)
    assert rem0 and rem0 > 0, f"le feu live n'a pas de duree exploitable (remaining={rem0})"

    st = load_state(dec, ob, snap, board=board, tiles=tm)
    tile_id = board.id_at(*tp)
    off0 = next((e for e in (st.effects.by_unit.get(tile_id) or [])
                 if e.effect_type == int(FIRE_TILE)), None)
    assert off0 is not None, "le seed n'a pas charge le feu de la tuile (regression #102)"
    assert off0.remaining_turns == rem0, \
        f"seed : offline remaining={off0.remaining_turns} != live {rem0}"

    # Avance PARALLELE : 1 endturn live = 1 EndTurnOperation offline. On ne fait plus rien d'autre,
    # donc la seule mutation attendue est le tick de duree.
    live_off_turn, off_off_turn, trace = None, None, []
    for k in range(1, 2 * rem0 + 3):
        _endturn(rpc, rid)
        EndTurnOperation.execute(st, advance=True)
        rows_k, _ = _tile_rows(rpc, rid)
        live_rem = _fire_remaining_live(rows_k, tp)
        off_present = st.effects.has_effect(tile_id, effect_type=int(FIRE_TILE))
        trace.append((k, live_rem, off_present))
        if live_rem is None and live_off_turn is None:
            live_off_turn = k
        if not off_present and off_off_turn is None:
            off_off_turn = k
        if live_off_turn is not None and off_off_turn is not None:
            break
    print(f"\n[O3/A live] rem0={rem0} trace(k, live_remaining, offline_present)={trace}")
    assert live_off_turn is not None, \
        f"le feu NATIF n'a pas expire en {2 * rem0 + 2} tours -> montage non exerce ({trace})"
    assert off_off_turn is not None, \
        f"le feu OFFLINE n'expire jamais -- c'est le residu O3 ({trace})"
    assert off_off_turn == live_off_turn, \
        f"extinction offline au tour {off_off_turn}, natif au tour {live_off_turn} ({trace})"


# ============================================================ B. live : LightCover pose a l'ENTREE

def _drybush_targets(board, dv, uid):
    """Tuiles DryBush LIBRES atteignables (portee de mouvement large : on prend les plus proches et
    on laisse le runner refuser celles qui ne le sont pas)."""
    occ = {_pos(u) for u in _alive(dv)}
    me = next(u for u in _alive(dv) if u.get("id") == uid)
    here = _pos(me)
    out = [c for c in board.coords_with_terrain("DryBush") if c not in occ]
    out.sort(key=lambda c: hexgeo.distance(here, c))
    return here, out


def test_light_cover_is_placed_when_entering_cover_live(rpc, build_runner):
    """CONFRONTATION du volet B. Une unite qui n'est PAS a couvert se DEPLACE sur une tuile DryBush.
    Le natif lui pose l'effet `LightCover` (1013) via `LightCoverAbility` (`On(0x24)`). Le port doit
    faire de meme en rejouant LE MEME move offline. AVANT le fix, l'offline ne posait rien."""
    rid = build_runner("90312", extra=["--board", COVER_BOARD, "--roster", "2"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    if not board.coords_with_terrain("DryBush"):
        pytest.skip(f"board {COVER_BOARD} sans DryBush")

    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dv0):
        pytest.skip("decisionView KO")
    me = dv0.get("currentPlayer")
    mine = [u for u in _alive(dv0) if u.get("player") == me or u.get("playerId") == me]
    if not mine:
        mine = _alive(dv0)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm0 = rpc("tileMeta", {"runnerId": rid}, 60)

    moved = None
    for u in mine:
        uid = u["id"]
        here, cands = _drybush_targets(board, dv0, uid)
        if board.terrain_at(*here) == "DryBush":
            continue                                   # deja a couvert -> pas une TRANSITION
        for c in cands[:6]:
            r = rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}]}, 60)
            if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
                dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
                u1 = next((x for x in (dv1.get("units") or []) if x.get("id") == uid), None)
                if u1 is not None and _pos(u1) == c:
                    moved = (uid, c, dv1)
                    break
        if moved:
            break
    if moved is None:
        pytest.skip("aucune unite n'a pu entrer sur une tuile DryBush (geometrie du build)")
    uid, dest, dv1 = moved

    live_names = {e.get("name") for e in
                  ((next(x for x in (dv1.get("units") or []) if x.get("id") == uid)
                    .get("effects")) or [])}
    # REJEU offline du MEME move depuis l'etat d'AVANT
    runner = Runner(load_state(dv0, ob0, snap0, board=board, tiles=tm0)).install_default_handlers()
    runner.apply(MoveUnitMessage(uid, dest))
    off = [e for e in (runner.state.effects.by_unit.get(uid) or [])
           if not e.consumed and e.effect_type == int(EffectType.LightCover)]
    print(f"\n[O3/B live] u{uid} -> {dest} (DryBush) : live effects={sorted(n for n in live_names if n)} "
          f"| offline LightCover={[e.name for e in off]}")
    assert "LightCover" in live_names, \
        "le NATIF n'a pas pose LightCover a l'entree -> montage non exerce (terrain/trait ?)"
    assert off, "le port n'a pas pose LightCover a l'entree sur la tuile de cover -- residu O3"
    assert off[0].remaining_turns is None, \
        (f"LightCover doit etre PERMANENT (AddEffect 4 args, DefaultAmountOfRounds(1013) NULL) ; "
         f"lu remaining_turns={off[0].remaining_turns}")


# ================================== B'. GENERALISATION : le gate de TRAITS du cctor (anti-sur-ajustement)

BIG_TARGET_UNIT = "orksWarboss"       # trait `BigTarget` (1017) — porteur HERO, present au pool


def test_light_cover_is_not_placed_on_excluded_trait_live(rpc, build_runner):
    """GENERALISATION du volet B : `UnitsThatNeedEffect` filtre par
    `UnitsWithoutTraits(<liste du cctor>)`, et `LightCoverAbility$$.cctor` remplit cette liste avec
    `Add(0x3f9)` `Add(0x405)` `Add(0)` = **BigTarget(1017) / Vehicle(1029) / Mounted(0)**. Une unite
    BigTarget qui ENTRE sur une tuile DryBush ne doit donc RIEN recevoir -- ni live, ni offline.
    Ce scenario discrimine la LECTURE du cctor : un port qui poserait l'effet inconditionnellement
    (le fix naif) passe le test B et ECHOUE ici."""
    rid = build_runner("90313", extra=["--board", COVER_BOARD,
                                       "--p-units", BIG_TARGET_UNIT,
                                       "--a-units", BIG_TARGET_UNIT])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    if not board.coords_with_terrain("DryBush"):
        pytest.skip(f"board {COVER_BOARD} sans DryBush")
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dv0):
        pytest.skip("decisionView KO")
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm0 = rpc("tileMeta", {"runnerId": rid}, 60)
    big = next((u for u in _alive(dv0) if u.get("visualId") == BIG_TARGET_UNIT), None)
    if big is None:
        pytest.skip(f"{BIG_TARGET_UNIT} absent du build")
    if "BigTarget" not in set((GC.unit(BIG_TARGET_UNIT) or {}).get("traits") or []):
        pytest.skip(f"{BIG_TARGET_UNIT} ne porte plus BigTarget dans le gameconfig")

    uid = big["id"]
    here, cands = _drybush_targets(board, dv0, uid)
    if board.terrain_at(*here) == "DryBush":
        pytest.skip("l'unite BigTarget spawn deja sur DryBush -> pas une TRANSITION")
    dest = None
    for c in cands[:6]:
        r = rpc("applyAction", {"runnerId": rid, "actions": [
            {"kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}]}, 60)
        if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
            dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            u1 = next((x for x in (dv1.get("units") or []) if x.get("id") == uid), None)
            if u1 is not None and _pos(u1) == c:
                dest = c
                break
    if dest is None:
        pytest.skip("l'unite BigTarget n'a pas pu entrer sur une tuile DryBush (geometrie)")

    live_names = {e.get("name") for e in
                  ((next(x for x in (dv1.get("units") or []) if x.get("id") == uid)
                    .get("effects")) or [])}
    runner = Runner(load_state(dv0, ob0, snap0, board=board, tiles=tm0)).install_default_handlers()
    runner.apply(MoveUnitMessage(uid, dest))
    off = [e for e in (runner.state.effects.by_unit.get(uid) or [])
           if not e.consumed and e.effect_type == int(EffectType.LightCover)]
    print(f"\n[O3/B' live] u{uid} {BIG_TARGET_UNIT} (BigTarget) -> {dest} (DryBush) : "
          f"live effects={sorted(n for n in live_names if n)} | offline LightCover={[e.name for e in off]}")
    assert "LightCover" not in live_names, \
        "le NATIF a pose LightCover sur un BigTarget -> la liste du cctor est mal lue"
    assert not off, \
        "le port a pose LightCover sur un BigTarget -- gate `UnitsWithoutTraits(<cctor>)` non applique"


# ================== B''. COMPOSITION : entrer a couvert CHANGE le nombre de coups recus (offline)

def test_entering_cover_reduces_incoming_ranged_hits_offline(rpc, build_runner):
    """COMPOSITION des deux faces portees : la POSE a l'entree (ce commit) + le GATE compute-time
    `AreEqual(coverPatch, target)` (A3) doivent, ensemble, faire CHUTER les coups ranged encaisses
    par une unite qui vient de se mettre a couvert. Sans la pose, l'effet n'existe pas et le nombre
    de coups ne bouge pas : le scenario est le CONSOMMATEUR REEL du volet B.

    Roster `necroDestroyer` (6 coups ranged Gauss) : le plancher natif `min=Direct(1)` ne sature pas,
    donc la MAGNITUDE est observable (meme garde-fou que `test_lightcover_gate_live`). Les positions
    sont FORCEES offline (doctrine drive-positions) : defenseur sur Grass a distance 2, puis MEME
    defenseur deplace sur DryBush par un `MoveUnitMessage`. Oracle de magnitude =
    `globalValues.lightCoverHitReduction` (le `GetNumberConstant(0x2c)` du natif), jamais une mesure figee."""
    from engine.runner.components import PositionComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    red = GC.global_value("lightCoverHitReduction")
    if not red:
        pytest.skip("globalValues.lightCoverHitReduction absent")
    red = int(red)
    rid = build_runner("90314", extra=["--board", "SyncPvp_Arctic_06",
                                       "--p-units", "necroDestroyer",
                                       "--a-units", "necroDestroyer"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live incomplete")
    units = _alive(dv)
    if len(units) < 2:
        pytest.skip("roster insuffisant")

    def place(state, uid, col, row):
        pc = state.get_entity(uid).get_component(PositionComponent)
        pc.col, pc.row = col, row

    def hits(state, att, tid):
        state.rng = IntBasedMersenneTwister()      # le NB de coups ne depend pas du seed
        r = Runner(state).install_default_handlers(20)
        r.apply(AttackUnitMessage(att, tid))
        return len((r.damage_handler.last or {}).get("per_hit") or [])

    # une tuile DryBush LIBRE et une Grass a distance 2 l'une de l'autre (l'attaquant tire de la Grass)
    bushes = [c for c in board.coords_with_terrain("DryBush")]
    pair = None
    for b in bushes:
        for a in board.coords_with_terrain("Grass"):
            if hexgeo.distance(a, b) == 2:
                pair = (a, b)
                break
        if pair:
            break
    if pair is None:
        pytest.skip("pas de couple (Grass, DryBush) a distance 2 sur le board")
    apos, bpos = pair
    # depart du defenseur : une Grass a distance 2 de l'attaquant, DIFFERENTE de sa tuile de cover
    start = next((c for c in board.coords_with_terrain("Grass")
                  if c != apos and hexgeo.distance(apos, c) == 2), None)
    if start is None:
        pytest.skip("pas de tuile Grass de depart a distance 2")
    att, tid = units[0]["id"], units[1]["id"]

    st0 = load_state(dv, ob, snap, board=board, tiles=tm)
    place(st0, att, *apos)
    place(st0, tid, *start)
    base_hits = hits(st0, att, tid)

    st1 = load_state(dv, ob, snap, board=board, tiles=tm)
    place(st1, att, *apos)
    place(st1, tid, *start)
    runner = Runner(st1).install_default_handlers(20)
    runner.apply(MoveUnitMessage(tid, bpos))       # ENTREE a couvert -> LightCoverAbility On(0x24)
    cover_hits = hits(runner.state, att, tid)
    names = [e.name for e in (runner.state.effects.by_unit.get(tid) or []) if not e.consumed]
    print(f"\n[O3/B'' offline] red={red} base_hits={base_hits} (Grass {start}) -> "
          f"cover_hits={cover_hits} (DryBush {bpos}) effets={sorted(n for n in names if n)}")
    assert base_hits - red > 1, \
        (f"setup NON discriminant : base_hits={base_hits}, red={red} -> le plancher min=Direct(1) "
         f"sature. Il faut un attaquant a plus de coups ranged.")
    assert "LightCover" in names, "l'entree a couvert n'a pose aucun LightCover (residu O3)"
    assert cover_hits == max(1, base_hits - red), \
        (f"apres l'entree a couvert : {cover_hits} coups, attendu max(1, {base_hits} - {red}) "
         f"(oracle globalValues.lightCoverHitReduction)")
