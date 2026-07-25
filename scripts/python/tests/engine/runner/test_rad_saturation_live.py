"""AdMech S4b GAP : RadSaturation (passif du Skitarii Vanguard admecSmnVanguard) confronte au port.

RadSaturation = **passiveAbility** du Skitarii Vanguard -> ability-trigger (registre `ABILITY_TRIGGERS`).
RE (decompile ghidra gqfc5mff6c) :
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RadSaturationAbility$$CreateTrigger` = `On(4=UnitAfterMove)&OwnerIsActor | On(0x23=UnitDisplaced)&OwnerIsTarget |
    On(0x17=TurnEnd)&OwnerIsActor&NOT(moved)` ;
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RadSaturationAbility$$CreateBehaviour` = `AddEffect(Contaminated=1244, Tiles(Caster()))` -> pose l'effet de TUILE
    Contaminated sur SA PROPRE tuile (« its hex »).
== i2 : « After the Skitarii Vanguard moves, it adds Contamination to its hex. If it does not move, then this
ability triggers at the end of its turn. »

RadSaturation est le **1er poseur** de l'effet de TUILE Contaminated (1244) du port (OnToxicDamage 1203 non
porte). La machinerie AVAL (`ContaminatedTileEffect`) etait donc DORMANTE ; ce port l'ARME. Une fois la tuile
contaminee, l'occupant NON-immune (pas Mechanical/ContagionsOfNurgle) subit `Contaminated_Unit` (1245, -30%
FixedArmor) a l'entree/au tick (aval deja valide #132).

CE FICHIER (port-agreement offline, board natif evenq + kit gameconfig ; positions DRIVE'es) :
  1. branche 1 : apres que le Skitarii bouge (`after_move_triggers`) -> SA tuile porte Contaminated (1244) ;
  2. branche 3 : en fin de tour SANS avoir bouge (`end_turn_summon_triggers`) -> SA tuile porte Contaminated ;
  3. gate branche 3 : s'il a bouge ce tour (flag natif `UnitFlag.Moved`) -> la fin de tour NE re-contamine PAS ;
  4. aval arme : la tuile contaminee expose un `ContaminatedTileEffect` (machinerie #132 desormais alimentee).

ASCII only. NON committe (tests confront live, hors depot)."""
from __future__ import annotations

import pytest

import gameconfig as GC

SUMMON_VIS = "admecSmnVanguard"        # Skitarii Vanguard (cle config/kit ; passiveAbilities=['RadSaturation'])
TAN_VIS = "admecMarshall"              # present dans le build -> fournit le niveau de scaling du summon
SUMMON_ABILITY = "ControlEdict"        # le Skitarii est summoned par ControlEdict -> source du scaling
CONTAMINATED_TILE = 1244               # EffectType.Contaminated (effet de TUILE pose par RadSaturation)
CONTAMINATED_UNIT = 1245               # EffectType.Contaminated_Unit (-30% FixedArmor sur l'occupant, aval)
BUILD = ["--roster", "1", "--p-units", f"{TAN_VIS},admecRuststalker",
         "--a-units", "necroWarden,necroWarden"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _load(rpc, build_runner, seed="777"):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    rid = build_runner(seed, extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec, ob, snap, board=board)
    if _ok(s0) and s0.get("mt"):
        rng = IntBasedMersenneTwister(); rng.mt = list(s0["mt"]); rng.mti = s0["mti"]; state.rng = rng
    return state, board


def _tan(state):
    """(tan_id, lvl, mult, team, player) depuis l'etat offline -> scaling du summon (niveau du caster)."""
    from engine.runner.components import StatsComponent, OwnerComponent, UnitComponent
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is None or uc.visual_id != TAN_VIS:
            continue
        sc = e.get_component(StatsComponent); oc = e.get_component(OwnerComponent)
        if sc is None or oc is None:
            return None
        ctx = sc.ctx
        return eid, getattr(ctx, "active_ability_level", None), \
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100), oc.team, oc.player
    return None


def _occupied(state):
    from engine.runner.operations.spawn import _occupied_tiles
    return _occupied_tiles(state)


def _free_neighbour_of(state, board, unit_id):
    """1re tuile LIBRE walkable voisine du `unit_id` (cote joueur, loin des ennemis -> pas d'overwatch)."""
    from engine.runner.components import PositionComponent
    pc = state.get_entity(unit_id).get_component(PositionComponent)
    if pc is None:
        return None
    tile = board.id_at(pc.col, pc.row)
    occ = _occupied(state)
    for n in sorted(board.neighbours(tile)):
        if n not in occ and board.walkable(n):
            return n
    return None


def _spawn_skitarii(state, board, tile, lvl, mult, team, player):
    from engine.runner.operations.spawn import _spawn_config_grot
    c, r = board.coord(tile)
    return _spawn_config_grot(state, SUMMON_VIS, board.id_at(c, r), SUMMON_ABILITY, lvl, mult, team, player)


def _prep(rpc, build_runner):
    state, board = _load(rpc, build_runner)
    tan = _tan(state)
    if tan is None:
        pytest.skip("Tan Gi'da absent offline / sans StatsComponent")
    tan_id, lvl, mult, team, player = tan
    if lvl is None:
        pytest.skip("niveau du caster indisponible (scaling summon non resoluble)")
    if state.effects is None:
        pytest.skip("EffectsState absent (snapshot sans combatSnapshot) -> AddEffect impossible")
    spot = _free_neighbour_of(state, board, tan_id)
    if spot is None:
        pytest.skip("aucune tuile libre adjacente a Tan pour poser le Skitarii")
    sid = _spawn_skitarii(state, board, spot, lvl, mult, team, player)
    if sid is None:
        pytest.skip("spawn Skitarii KO")
    return state, board, sid, spot, player


def _set_moved(state, uid, moved: bool):
    """Pose/retire le flag natif `UnitFlag.Moved` (`UnitFlagsComponent`) — LE store du fait « a bouge ce
    tour » cote natif comme cote port (`components.unit_has_moved`)."""
    from engine.runner.components import UnitFlagsComponent, set_moved_flag
    if moved:
        set_moved_flag(state, uid)
        return
    fl = state.get_entity(uid).get_component(UnitFlagsComponent)
    if fl is not None:
        fl.remove(UnitFlagsComponent.MOVED)


def _skit_tile(state, board, sid):
    from engine.runner.components import PositionComponent
    pc = state.get_entity(sid).get_component(PositionComponent)
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _find_open_push_triple(board, occupied):
    """(pusher C, pousse T, atterrissage B) en CHAMP OUVERT : C adjacent a T ; B = tuile derriere T (oppose de
    C) via la MEME geometrie que `DisplaceUnitOperation` (`_dir_index`/`_step`) ; les 3 walkable, distinctes,
    libres (hors `occupied`, un set d'ids de tuiles). None si aucun triplet. Sert a DRIVE un push deterministe
    du Skitarii pour valider la branche 2 (contamination a l'atterrissage)."""
    from engine.runner.operations.displace import _dir_index, _step
    for t in board.by_id:
        tc = board.coord(t)
        if not board.walkable(t) or t in occupied:
            continue
        for c in board.neighbours(t):
            cc = board.coord(c)
            if not board.walkable(c) or c in occupied or c == t:
                continue
            di = _dir_index(cc[0], cc[1], tc[0], tc[1])
            if di is None:
                continue
            b = board.id_at(*_step(tc[0], tc[1], di))
            if b is None or b in (t, c) or not board.walkable(b) or b in occupied:
                continue
            return c, t, b
    return None


def test_rad_saturation_after_move_contaminates_own_tile(live_session, rpc, build_runner):
    """Branche 1 (`On(4)&OwnerIsActor`) : quand le Skitarii bouge, `after_move_triggers(sid)` pose Contaminated
    (1244) sur SA tuile courante (== `Tiles(Caster())`)."""
    from engine.runner.operations.triggers.dispatch import after_move_triggers
    state, board, sid, tile, _player = _prep(rpc, build_runner)
    assert not state.effects.has_effect(tile, effect_type=CONTAMINATED_TILE), "tuile deja contaminee (pre-cond KO)"

    out = after_move_triggers(state, sid)                 # le Skitarii vient de bouger sur `tile`
    rad = [r for r in out if isinstance(r, dict) and r.get("passive") == "RadSaturation"]
    print(f"[radsat move] rad={rad} tile={tile} has_1244={state.effects.has_effect(tile, effect_type=CONTAMINATED_TILE)}")

    assert state.effects.has_effect(tile, effect_type=CONTAMINATED_TILE), \
        "apres move : la tuile du Skitarii NE porte PAS Contaminated (1244)"
    assert rad and rad[0].get("contaminated_tile") == tile, \
        f"RadSaturation n'a pas rapporte la contamination de sa tuile : {rad}"


def test_rad_saturation_turn_end_no_move_contaminates(live_session, rpc, build_runner):
    """Branche 3 (`On(0x17=TurnEnd)&NOT moved`) : sans avoir bouge, `end_turn_summon_triggers(player)` pose
    Contaminated (1244) sur la tuile du Skitarii."""
    from engine.runner.operations.triggers.dispatch import end_turn_summon_triggers
    state, board, sid, tile, player = _prep(rpc, build_runner)
    _set_moved(state, sid, False)                         # n'a PAS bouge ce tour (flag natif absent)
    assert not state.effects.has_effect(tile, effect_type=CONTAMINATED_TILE), "tuile deja contaminee (pre-cond KO)"

    out = end_turn_summon_triggers(state, player)
    rad = [r for r in out if isinstance(r, dict) and r.get("passive") == "RadSaturation"]
    print(f"[radsat turnend] rad={rad} tile={tile} has_1244={state.effects.has_effect(tile, effect_type=CONTAMINATED_TILE)}")

    assert state.effects.has_effect(tile, effect_type=CONTAMINATED_TILE), \
        "fin de tour sans move : la tuile du Skitarii NE porte PAS Contaminated (1244)"
    assert rad and rad[0].get("contaminated_tile") == tile, f"RadSaturation turn-end absent : {rad}"


def test_rad_saturation_turn_end_gate_skips_if_moved(live_session, rpc, build_runner):
    """Gate branche 3 : s'il a BOUGE ce tour (flag natif `UnitFlag.Moved` pose sur lui), la fin de tour NE
    re-contamine PAS (la branche 1 l'a deja fait a la destination) -> `NOT(HasFlag moved)` refute."""
    from engine.runner.operations.triggers.dispatch import end_turn_summon_triggers
    state, board, sid, tile, player = _prep(rpc, build_runner)
    _set_moved(state, sid, True)                          # a BOUGE ce tour -> branche 3 gatee
    assert not state.effects.has_effect(tile, effect_type=CONTAMINATED_TILE), "tuile deja contaminee (pre-cond KO)"

    out = end_turn_summon_triggers(state, player)
    rad = [r for r in out if isinstance(r, dict) and r.get("passive") == "RadSaturation"]
    print(f"[radsat gate] rad={rad} has_1244={state.effects.has_effect(tile, effect_type=CONTAMINATED_TILE)}")

    assert not rad, f"gate KO : RadSaturation a fire en fin de tour alors qu'il a bouge : {rad}"
    assert not state.effects.has_effect(tile, effect_type=CONTAMINATED_TILE), \
        "gate KO : la tuile a ete contaminee en fin de tour malgre le flag 'a bouge'"


def test_rad_saturation_arms_contaminated_tile_effect(live_session, rpc, build_runner):
    """Aval arme : apres que RadSaturation contamine la tuile, `collect_effect_triggers` expose desormais un
    `ContaminatedTileEffect` (owner = la tuile) -> la machinerie #132 (Contaminated_Unit -30% armure) est
    alimentee (elle etait DORMANTE, aucun poseur de 1244 avant ce port)."""
    from engine.runner.operations.triggers.dispatch import after_move_triggers, collect_effect_triggers
    from engine.runner.operations.triggers.effect_triggers import ContaminatedTileEffect
    state, board, sid, tile, _player = _prep(rpc, build_runner)

    before = [e for e in collect_effect_triggers(state)
              if isinstance(e, ContaminatedTileEffect)]
    after_move_triggers(state, sid)                       # contamine la tuile du Skitarii
    after = [e for e in collect_effect_triggers(state)
             if isinstance(e, ContaminatedTileEffect) and e.owner_id == tile]
    print(f"[radsat arm] contaminated-tile-effects before={len(before)} after(on tile {tile})={len(after)}")

    assert state.effects.has_effect(tile, effect_type=CONTAMINATED_TILE), "tuile non contaminee (pre-cond)"
    assert after, "aucun ContaminatedTileEffect arme sur la tuile contaminee (machinerie aval non alimentee)"


def test_rad_saturation_on_displace_contaminates_landing_tile(live_session, rpc, build_runner):
    """Branche 2 (`On(0x23=UnitDisplaced) & OwnerIsTarget`) : quand le Skitarii est FORCE-MOVE (push), il
    contamine sa tuile d'ATTERRISSAGE. `DisplaceUnitOperation.execute` (apres le MoveUnit du push) dispatche
    On(UnitDisplaced) {actor=pusher, target=Skitarii} via `displace_triggers` -> RadSaturation OwnerIsTarget ->
    Contaminated (1244) sur la NOUVELLE tuile. Geometrie DRIVE'e (pousseur/pousse/atterrissage places en champ
    ouvert, meme geometrie que DisplaceUnitOperation) -> deterministe, robuste au placement live."""
    from engine.runner.events import EventBus
    from engine.runner.operations.displace import DisplaceUnitOperation
    from engine.runner.components import PositionComponent
    state, board = _load(rpc, build_runner)
    tan = _tan(state)
    if tan is None:
        pytest.skip("Tan Gi'da absent offline / sans StatsComponent")
    tan_id, lvl, mult, team, player = tan
    if lvl is None:
        pytest.skip("niveau du caster indisponible (scaling summon non resoluble)")
    if state.effects is None:
        pytest.skip("EffectsState absent (snapshot sans combatSnapshot) -> AddEffect impossible")
    triple = _find_open_push_triple(board, _occupied(state))
    if triple is None:
        pytest.skip("aucun triplet (pousseur, pousse, atterrissage) ouvert sur ce board")
    c_tile, t_tile, b_tile = triple
    # DRIVE : place Tan (pousseur) en C ; spawn le Skitarii (pousse) en T ; atterrissage attendu = B (derriere).
    tpc = state.get_entity(tan_id).get_component(PositionComponent)
    cc, cr = board.coord(c_tile)
    tpc.col, tpc.row = cc, cr
    sid = _spawn_skitarii(state, board, t_tile, lvl, mult, team, player)
    if sid is None:
        pytest.skip("spawn Skitarii KO")
    assert not state.effects.has_effect(b_tile, effect_type=CONTAMINATED_TILE), "atterrissage deja contamine (pre-cond KO)"

    res = DisplaceUnitOperation(tan_id, sid).execute(state, EventBus())
    spc = state.get_entity(sid).get_component(PositionComponent)
    new_tile = board.id_at(spc.col, spc.row)
    print(f"[radsat displace] pusher@{c_tile} pushed@{t_tile} -> landing@{new_tile} (want {b_tile}) "
          f"res={res} has_1244={state.effects.has_effect(b_tile, effect_type=CONTAMINATED_TILE)}")

    assert new_tile == b_tile, \
        f"le Skitarii n'a PAS ete pousse sur la tuile d'atterrissage attendue (got {new_tile}, want {b_tile})"
    assert state.effects.has_effect(b_tile, effect_type=CONTAMINATED_TILE), \
        "apres push : la tuile d'atterrissage du Skitarii NE porte PAS Contaminated (1244) (branche 2 non firee)"
