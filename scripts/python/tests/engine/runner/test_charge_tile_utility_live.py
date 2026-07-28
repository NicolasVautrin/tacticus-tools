"""#165 : `SortTilesByUtility` -- la tuile de charge/spawn suit l'UTILITE `Tile(7)`, PAS la distance.

Trois ports freres (`SkyStrikeAbility$$ExecuteBehaviour`, `HeroicFusilladeAbility$$ExecuteBehaviour`,
`ForwardSpotterAbility$$PickTiles`) collapsaient
`IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` en « la tuile la plus PROCHE du
caster ». Ce test est le CLIQUET : il monte une geometrie ou les deux regles DIVERGENT et confronte
la tuile choisie par le port au NATIF (position finale du caster / tuile de spawn du summon).

Un test qui passerait sur une geometrie NON discriminante ne prouverait rien : chaque cas
`assert`-e d'abord que `collapse != utilite` sur le pool retenu (sinon il ECHOUE, il ne skippe pas --
le board `MC1_67` porte du relief, cf. `probe_165_charge_tile_utility.py --plan MC1_67`).

ASCII only (console cp1252).
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import hexgeo

PYDIR = Path(__file__).resolve().parents[3]        # scripts/python
ROOT = PYDIR.parents[1]

BOARD = "MC1_67"
HF_BUILD = ["--p-units", "genesKelermorph", "--a-units", "necroWarden", "--no-ai"]
HF_ABILITY = 1180
HF_MOVE_RANGE = 2


# ------------------------------------------------------------------ helpers

def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dv, ob, snap, board=board), board, dv


def _uid_by_vis(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return int(u["id"])
    return None


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


def _nearest(board, cpos, pool):
    """L'ANCIEN collapse : la tuile du pool la plus PROCHE du caster (tie-break id de tuile)."""
    return sorted(pool, key=lambda t: (hexgeo.distance(cpos, board.coord(t)), t))[0]


def _live_pos(rpc, rid, uid):
    """(col,row) LIVE d'une unite -- `decisionView.units[].pos` (PAS de `col`/`row` a plat)."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90) or {}
    for u in (dv.get("units") or []):
        if int(u.get("id")) == int(uid):
            p = u.get("pos") or {}
            return (p.get("col"), p.get("row"))
    return None


def _move(rpc, rid, uid, col, row):
    """`applyAction{kind:"move"}` — la destination est un OBJET `to` (`{col,row}`), pas deux champs
    a plat : un `col`/`row` a plat est accepte et rend un NO-OP SILENCIEUX."""
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _endturn(rpc, rid):
    return rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _drive_to(rpc, rid, wanted: dict, max_turns: int = 12) -> bool:
    """Amene chaque `uid -> (col,row)` de `wanted` a destination, PAS-A-PAS.

    `applyAction move` refuse une destination hors de la portee du tour : on avance donc de tour en
    tour, en choisissant a chaque fois la tuile LEGALE (`aiMovableTiles`, joueur COURANT seulement)
    qui minimise la distance hex a la destination. `endturn` fait tourner les camps -- on pilote les
    deux (`applyAction` ne verifie pas la propriete du `unitId`, cf. runner.md §4)."""
    for _ in range(max_turns):
        if all(_live_pos(rpc, rid, u) == p for u, p in wanted.items()):
            return True
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
        for mu in (mov.get("units") or []):
            uid = int(mu.get("unitId") or -1)
            if uid not in wanted:
                continue
            dest = tuple(wanted[uid])
            cur = (mu.get("pos") or {}).get("col"), (mu.get("pos") or {}).get("row")
            if cur == dest:
                continue        # NE PAS re-bouger : la tuile occupee est HORS de `tiles`, donc un
                                # `min` aveugle repartirait ailleurs et re-consommerait l'activation
                                # (le camp ne basculerait jamais a l'`endturn`).
            reach = [(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                     if t.get("col") is not None]
            if not reach:
                continue
            step = min(reach, key=lambda p: (hexgeo.distance(p, dest), p))
            if step != cur:
                _move(rpc, rid, uid, *step)
        _endturn(rpc, rid)
    return all(_live_pos(rpc, rid, u) == p for u, p in wanted.items())


# ------------------------------------------------------------------ HeroicFusillade (charge)

def _hf_pick_geometry(state, board, caster, target):
    """Cherche (cpos, tpos, pool, collapse_tile, port_tile) tel que l'ancien collapse et le tri
    `Tile(7)` DIVERGENT, avec une divergence tranchee par l'UTILITE (elevations distinctes) et des
    positions atteignables (dist caster<->cible dans [2,3])."""
    from engine.runner.abilities.genestealer import (_charge_candidate_tiles, _hf_move_dest_tile,
                                                     SURROUND_RADIUS)
    keep_c, keep_t = _pos(state, caster), _pos(state, target)
    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    found = []
    try:
        for ttile in walk:
            _set_pos(state, target, *board.coord(ttile))
            for ctile in walk:
                if ctile == ttile:
                    continue
                cpos = board.coord(ctile)
                if not 2 <= hexgeo.distance(cpos, board.coord(ttile)) <= 3:
                    continue
                _set_pos(state, caster, *cpos)
                pool = _charge_candidate_tiles(state, caster, target, SURROUND_RADIUS,
                                               HF_MOVE_RANGE)
                if len(pool) < 2:
                    continue
                near = _nearest(board, cpos, pool)
                best = _hf_move_dest_tile(state, caster, target, SURROUND_RADIUS, HF_MOVE_RANGE)
                if best is None or board.coord(near) == best:
                    continue
                if board.elevation(near) == board.elevation(board.id_at(*best)):
                    continue                       # egalite d'utilite : ne testerait que l'ordre source
                found.append((cpos, board.coord(ttile), pool, board.coord(near), best))
    finally:
        _set_pos(state, caster, *keep_c)
        _set_pos(state, target, *keep_t)
    if not found:
        return None
    # la geometrie la MOINS chere a atteindre depuis les spawns (chaque saut = un tour de jeu)
    found.sort(key=lambda g: hexgeo.distance(keep_c, g[0]) + hexgeo.distance(keep_t, g[1]))
    return found[0]


def test_heroic_fusillade_charge_tile_follows_tile_utility(rpc, build_runner):
    """`HeroicFusilladeAbility$$ExecuteBehaviour` : `First(SortTilesByUtility(<pool>, self, 7), 1)`.
    La charge atterrit sur la MEILLEURE tuile au sens `Tile(7)`, pas sur la plus proche."""
    rid = build_runner("165165", extra=HF_BUILD, board=BOARD)["rid"]
    state, board, dv = _load(rpc, rid)
    caster = _uid_by_vis(dv, "genesKelermorph")
    target = _uid_by_vis(dv, "necroWarden")
    assert caster is not None and target is not None, "roster attendu absent du runner"

    geo = _hf_pick_geometry(state, board, caster, target)
    assert geo is not None, f"aucune geometrie discriminante sur {BOARD} -- le test ne prouverait rien"
    cpos, tpos, pool, collapse_tile, port_tile = geo
    assert collapse_tile != port_tile                       # le cas EST discriminant

    # DRIVE des positions live (le runner ne fait pas jouer l'IA : `--no-ai`).
    if not _drive_to(rpc, rid, {caster: cpos, target: tpos}):
        pytest.skip(f"geometrie non atteignable (caster={_live_pos(rpc, rid, caster)} "
                    f"cible={_live_pos(rpc, rid, target)}, vise {cpos}/{tpos})")

    # re-calcule le port sur l'etat LIVE effectif (les positions ont bouge pour de vrai)
    state2, board2, _dv2 = _load(rpc, rid)
    from engine.runner.abilities.genestealer import (_charge_candidate_tiles, _hf_move_dest_tile,
                                                     SURROUND_RADIUS)
    pool2 = _charge_candidate_tiles(state2, caster, target, SURROUND_RADIUS, HF_MOVE_RANGE)
    port2 = _hf_move_dest_tile(state2, caster, target, SURROUND_RADIUS, HF_MOVE_RANGE)
    near2 = board2.coord(_nearest(board2, cpos, pool2)) if pool2 else None
    assert port2 is not None and near2 is not None and port2 != near2, \
        f"geometrie live non discriminante (pool={pool2} port={port2} collapse={near2})"

    # ⚠ un cast REFUSE (pas mon tour, cooldown) rend `ok=true, error=null, mutated=false` — un NO-OP
    # SILENCIEUX : c'est `mutated` qui dit si le cast a eu lieu, pas `error`.
    act0 = {}
    for _ in range(8):
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": HF_ABILITY}}, 120)
        act0 = ((res or {}).get("actions") or [{}])[0]
        if not act0.get("error") and act0.get("mutated"):
            break
        _endturn(rpc, rid)
    assert not act0.get("error") and act0.get("mutated"), \
        f"cast 1180 sans effet: err={act0.get('error')} mutated={act0.get('mutated')}"

    live_after = _live_pos(rpc, rid, caster)
    print(f"\n[165 HF] pool={[(board2.coord(t), board2.elevation(t)) for t in pool2]} "
          f"collapse={near2} port={port2} live={live_after}")
    assert live_after == port2, (f"charge live {live_after} != port {port2} "
                                 f"(l'ancien collapse aurait donne {near2})")
    assert live_after != near2, "le natif suivrait la distance -- collapse NON refute"


# ------------------------------------------------------------------ ForwardSpotter (spawn)

FS_BUILD = ["--p-units", "genesKelermorph", "--p-mow", "astraOrdnanceBattery",
            "--a-units", "necroWarden", "--no-ai"]
FS_BOARD = "C3_01"
FS_ABILITY = 1143


def _mow_caster_id(dv):
    for m in (dv.get("mows") or []):
        if m.get("visualId") == "astraOrdnanceBattery" and m.get("casterId") is not None:
            return int(m["casterId"])
    return None


def _fs_pick_geometry(state, board, target):
    """Position de la CIBLE ou l'ancien collapse (1re tuile libre, ids TRIES) et le port #165
    (`neighbours_native` + tri `Tile(7)`) divergent, la divergence etant tranchee par l'utilite."""
    from engine.runner.abilities.astramilitarum import forward_spotter_pick_tiles
    from engine.runner.components import PositionComponent, UnitComponent
    keep = _pos(state, target)
    occ0 = set()
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if pc is None or uid == target or (uc is not None and not uc.alive):
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ0.add(t)
    found = []
    try:
        for ttile in sorted(board.by_id):
            if not board.walkable(ttile) or ttile in occ0:
                continue
            _set_pos(state, target, *board.coord(ttile))
            occ = occ0 | {ttile}
            old = [t for t in board.neighbours(ttile) if t not in occ and board.walkable(t)]
            new = forward_spotter_pick_tiles(state, target, 1)
            if not old or not new or old[0] == new[0]:
                continue
            if board.elevation(old[0]) == board.elevation(new[0]):
                continue
            found.append((board.coord(ttile), board.coord(old[0]), board.coord(new[0])))
    finally:
        _set_pos(state, target, *keep)
    if not found:
        return None
    found.sort(key=lambda g: hexgeo.distance(keep, g[0]))     # la plus proche du spawn de la cible
    return found[0]


def test_forward_spotter_spawn_tile_follows_tile_utility(rpc, build_runner):
    """`ForwardSpotterAbility$$PickTiles` : `First(SortTilesByUtilityForSummon(<ring-1 libre>, 7,
    owner), nrOfSummons)`. Le Cadian apparait sur la MEILLEURE tuile au sens `Tile(7)`."""
    rid = build_runner("165777", extra=FS_BUILD, board=FS_BOARD)["rid"]
    state, board, dv = _load(rpc, rid)
    caster = _mow_caster_id(dv)
    target = _uid_by_vis(dv, "genesKelermorph")
    if caster is None:
        pytest.skip("MoW astraOrdnanceBattery non deployee dans ce runner")
    assert target is not None, "genesKelermorph absent du runner"

    geo = _fs_pick_geometry(state, board, target)
    assert geo is not None, f"aucune geometrie discriminante sur {FS_BOARD}"
    tpos, collapse_tile, port_tile = geo
    assert collapse_tile != port_tile

    if not _drive_to(rpc, rid, {target: tpos}):
        pytest.skip(f"cible non deplacable en {tpos} (live={_live_pos(rpc, rid, target)})")

    state2, board2, _dv2 = _load(rpc, rid)
    from engine.runner.abilities.astramilitarum import forward_spotter_pick_tiles
    port2 = forward_spotter_pick_tiles(state2, target, 1)
    ttile2 = board2.id_at(*tpos)
    occ2 = set()
    from engine.runner.components import PositionComponent, UnitComponent
    for uid, e in state2.entities.items():
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        t = board2.id_at(pc.col, pc.row)
        if t is not None:
            occ2.add(t)
    old2 = [t for t in board2.neighbours(ttile2) if t not in occ2 and board2.walkable(t)]
    assert port2 and old2 and board2.coord(port2[0]) != board2.coord(old2[0]), \
        "geometrie live non discriminante"

    # ⚠ un cast REFUSE rend `ok=true, error=null, mutated=false` — un NO-OP SILENCIEUX.
    act0 = {}
    for _ in range(8):                                     # cooldown initial du MoW
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": FS_ABILITY}}, 120)
        act0 = ((res or {}).get("actions") or [{}])[0]
        if not act0.get("error") and act0.get("mutated"):
            break
        _endturn(rpc, rid)
    assert not act0.get("error") and act0.get("mutated"), \
        f"cast 1143 sans effet: err={act0.get('error')} mutated={act0.get('mutated')}"

    # ⚠ Le Cadian JOUE son tour A L'APPARITION (`PerformAIAttack`) : `changes[].appeared.to` est sa
    # position FINALE (mesure : spawn (2,3) -> `to` (3,6) apres qu'il a marche sur l'ennemi), PAS la
    # tuile de spawn. Celle-ci vient du tag `Unit_Foot_Tile_Id_1` du step d'APPARITION (`step == 10`,
    # celui qui porte `Unit_IsSummoned`) ; `tags` est une CHAINE JSON, pas un dict.
    appeared = [c for c in (act0.get("changes") or []) if c.get("appeared")]
    assert appeared, f"aucun summon apparu apres le cast 1143 (changes={act0.get('changes')})"
    spawn_tile = None
    for ev in (act0.get("events") or []):
        if ev.get("kind") != "action" or int(ev.get("step") or -1) != 10:
            continue
        try:
            tags = json.loads(ev.get("tags") or "{}")
        except ValueError:
            continue
        if tags.get("Unit_IsSummoned") and tags.get("Unit_Foot_Tile_Id_1") is not None:
            spawn_tile = int(tags["Unit_Foot_Tile_Id_1"])
            break
    assert spawn_tile is not None, "tuile de spawn introuvable dans les events du cast 1143"
    print(f"\n[165 FS] ring1_libre={[(board2.coord(t), board2.elevation(t)) for t in old2]} "
          f"collapse={board2.coord(old2[0])} port={board2.coord(port2[0])} "
          f"live_spawn={board2.coord(spawn_tile)}")
    assert spawn_tile == port2[0], (f"spawn live {board2.coord(spawn_tile)} != port "
                                    f"{board2.coord(port2[0])} (l'ancien collapse aurait donne "
                                    f"{board2.coord(old2[0])})")


# ------------------------------------------------------------------ SkyStrike (charge, sans reach)

SKY_VIS = "adeptCelestine"
SKY_ABILITY = 1025


def _sky_pool(state, board, target):
    """Le pool `CanAddUnit(AdjacentTiles(target))` DANS L'ORDRE DU SELECTEUR — meme construction que
    `_sky_strike_dest_tile` (c'est lui qu'on veut re-trier de deux facons)."""
    from engine.runner.abilities.sisterhood import _sk_occupied_positions, _sk_pos_of
    tpos = _sk_pos_of(state, target)
    ttile = board.id_at(*tpos) if tpos else None
    if ttile is None:
        return []
    occ = _sk_occupied_positions(state)
    return [t for t in board.neighbours_native(ttile)
            if board.coord(t) not in occ and board.walkable(t)]


def _sky_pick_geometry_geminae(state, board, caster, target):
    """(cpos, tpos, sans_unite, avec_unite) — geometrie ou le terme de la feuille
    `TriggeredAbilities(2)` du composite RENVERSE le classement (case-165b).

    `sans_unite` = `first_tile_by_utility(..., unit_id=None)` : le tri REDUIT (Elevation +
    TileEffects seulement), c'est-a-dire EXACTEMENT le port d'avant case-165b. `avec_unite` =
    `_sky_strike_dest_tile`, qui passe `caster@0x160` comme `dc.units` et reveille le
    `GeminaeSuperiaPlaybook` (10 x |CanAddUnit(AdjacentTiles(tuile))|). Le terme etant CONSTANT en
    plein plateau, on ne trouve de divergence qu'au voisinage TRONQUE (bord / tuiles occupees) —
    c'est le sens meme du cas."""
    from engine.runner.abilities.sisterhood import _sky_strike_dest_tile
    from engine.utilities.tile import first_tile_by_utility
    keep_c, keep_t = _pos(state, caster), _pos(state, target)
    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    found = []
    try:
        for ttile in walk:
            tpos = board.coord(ttile)
            _set_pos(state, target, *tpos)
            for ctile in walk:
                cpos = board.coord(ctile)
                if ctile == ttile or not 2 <= hexgeo.distance(cpos, tpos) <= 4:
                    continue
                _set_pos(state, caster, *cpos)
                pool = _sky_pool(state, board, target)
                if len(pool) < 2:
                    continue
                before = first_tile_by_utility(state, pool)          # dc.units ABSENT (port d'avant)
                after = _sky_strike_dest_tile(state, caster, target)  # dc.units = le caster
                if before is None or after is None or board.coord(before) == after:
                    continue
                found.append((cpos, tpos, board.coord(before), after))
    finally:
        _set_pos(state, caster, *keep_c)
        _set_pos(state, target, *keep_t)
    if not found:
        return None
    found.sort(key=lambda g: hexgeo.distance(keep_c, g[0]) + hexgeo.distance(keep_t, g[1]))
    return found[0]


def test_sky_strike_landing_tile_follows_unit_gated_leaf(rpc, build_runner, sky_bc):
    """case-165b — le composite `Tile(7)` du tri VOIT `dc.units` (`caster@0x160`).

    `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` construit
    `UtilityMovementCase(dc.units, tile, null, null, dc.owner)` : les feuilles gatees sur l'unite
    recoivent donc le caster. Pour `adeptCelestine` (passif `GeminaeSuperia` 1048) la feuille
    `TriggeredAbilities(2)` dispatche vers
    `IdunBattle.AI.Playbook.Loki.GeminaeSuperiaPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__3$$MoveNext`
    = `10 x |CanAddUnit(AdjacentTiles(tuile))|` (+10 si `OwnerInAdjacentTile`, +30 par Geminae
    adjacente). Ce test monte une geometrie ou ce terme RENVERSE le classement d'`ElevationUtility`
    et confronte au natif."""
    extra = ["--seed-bc", str(sky_bc), "--p-units", SKY_VIS, "--a-units", "necroWarden", "--no-ai"]
    rid = build_runner("1651652", extra=extra, board=BOARD)["rid"]
    state, board, dv = _load(rpc, rid)
    caster = _uid_by_vis(dv, SKY_VIS)
    target = _uid_by_vis(dv, "necroWarden")
    if caster is None:
        pytest.skip("adeptCelestine absente du build (injection KO)")
    assert target is not None

    geo = _sky_pick_geometry_geminae(state, board, caster, target)
    assert geo is not None, (f"aucune geometrie ou la feuille gatee sur l'unite departage sur {BOARD}"
                             " -- le test ne prouverait rien")
    cpos, tpos, before_tile, after_tile = geo
    assert before_tile != after_tile

    if not _drive_to(rpc, rid, {caster: cpos, target: tpos}):
        pytest.skip(f"geometrie non atteignable (caster={_live_pos(rpc, rid, caster)} "
                    f"cible={_live_pos(rpc, rid, target)}, vise {cpos}/{tpos})")

    state2, board2, _dv2 = _load(rpc, rid)
    from engine.runner.abilities.sisterhood import _sky_strike_dest_tile
    from engine.utilities.tile import first_tile_by_utility
    pool2 = _sky_pool(state2, board2, target)
    port2 = _sky_strike_dest_tile(state2, caster, target)
    before2 = first_tile_by_utility(state2, pool2)
    assert port2 is not None and before2 is not None and board2.coord(before2) != port2, \
        f"geometrie live NON discriminante (pool={pool2} avec={port2} sans={before2})"

    act0 = {}
    for _ in range(8):
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": SKY_ABILITY}}, 120)
        act0 = ((res or {}).get("actions") or [{}])[0]
        if not act0.get("error") and act0.get("mutated"):
            break
        _endturn(rpc, rid)
    assert not act0.get("error") and act0.get("mutated"), \
        f"cast 1025 sans effet: err={act0.get('error')} mutated={act0.get('mutated')}"

    live_after = _live_pos(rpc, rid, caster)
    print(f"\n[165b SKY] pool={[(board2.coord(t), board2.elevation(t)) for t in pool2]} "
          f"sans_dc_units={board2.coord(before2)} avec={port2} live={live_after}")
    assert live_after == port2, (f"atterrissage live {live_after} != port {port2} "
                                 f"(sans le terme gate sur l'unite : {board2.coord(before2)})")


def _sky_pick_geometry(state, board, caster, target):
    """(cpos, tpos, collapse, port) ou l'ancien collapse (ring-1 `hexgeo.disk`, trie par distance au
    caster) et le port #165 (`neighbours_native` + tri `Tile(7)`) divergent, divergence tranchee par
    l'utilite. Contraintes : caster NON adjacent (sinon le gate `Not(IsAdjacent)` supprime le move) et
    AUCUNE contrainte de portee (Celestine vole).

    ⚠ On EXIGE une cible a 6 voisins et un caster PROCHE (dist <= 3) : c'est le patron ELEVATION/COVER
    etabli par #165, que ce test garde tel quel. La cible au BORD avec caster lointain est l'objet du
    test `..._follows_unit_gated_leaf` ci-dessus (case-165b), qui exerce l'AUTRE terme."""
    from engine.runner.abilities.sisterhood import _sky_strike_dest_tile
    keep_c, keep_t = _pos(state, caster), _pos(state, target)
    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    found = []
    try:
        for ttile in walk:
            tpos = board.coord(ttile)
            if len([n for n in board.neighbours_native(ttile) if board.walkable(n)]) < 6:
                continue                              # pas de cible au BORD (voisinage tronque)
            _set_pos(state, target, *tpos)
            for ctile in walk:
                cpos = board.coord(ctile)
                if ctile == ttile or not 2 <= hexgeo.distance(cpos, tpos) <= 3:
                    continue
                _set_pos(state, caster, *cpos)
                occ = {cpos, tpos}
                old = [t for (c, r) in hexgeo.disk(tpos[0], tpos[1], 1)
                       for t in [board.id_at(c, r)]
                       if (c, r) not in occ and t is not None and board.walkable(t)]
                if len(old) < 2:
                    continue
                old.sort(key=lambda t: (hexgeo.distance(cpos, board.coord(t)), t))
                new = _sky_strike_dest_tile(state, caster, target)
                if new is None or board.coord(old[0]) == new:
                    continue
                if board.elevation(old[0]) == board.elevation(board.id_at(*new)):
                    continue
                found.append((cpos, tpos, board.coord(old[0]), new))
    finally:
        _set_pos(state, caster, *keep_c)
        _set_pos(state, target, *keep_t)
    if not found:
        return None
    found.sort(key=lambda g: hexgeo.distance(keep_c, g[0]) + hexgeo.distance(keep_t, g[1]))
    return found[0]


@pytest.fixture(scope="module")
def sky_bc():
    """Seed BC augmente d'`adeptCelestine` via `catalog_inject.py` — il pose `BC.Units` ET
    `BC.Abilities`, ce sans quoi le cast live de 1025 leve « system error »
    (`AbilityConfiguration$$GetVariableForLevel` sur une config vide). cf. runner.md §1bis."""
    out = ROOT / "logs" / "runners" / f"sky165-{uuid.uuid4().hex[:8]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", SKY_VIS, "--out", str(out)],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not out.exists():
        pytest.skip(f"catalog_inject KO: {(p.stderr or p.stdout or '')[-300:]}")
    yield out
    out.unlink(missing_ok=True)


def test_sky_strike_landing_tile_follows_tile_utility(rpc, build_runner, sky_bc):
    """`SkyStrikeAbility$$ExecuteBehaviour` : `First(SortTilesByUtility(CanAddUnit(AdjacentTiles(
    target)), caster, UtilityDefinition(7)), 1)` — Celestine atterrit sur la MEILLEURE tuile."""
    extra = ["--seed-bc", str(sky_bc), "--p-units", SKY_VIS, "--a-units", "necroWarden", "--no-ai"]
    rid = build_runner("1650252", extra=extra, board=BOARD)["rid"]
    state, board, dv = _load(rpc, rid)
    caster = _uid_by_vis(dv, SKY_VIS)
    target = _uid_by_vis(dv, "necroWarden")
    if caster is None:
        pytest.skip("adeptCelestine absente du build (injection KO)")
    assert target is not None

    geo = _sky_pick_geometry(state, board, caster, target)
    assert geo is not None, f"aucune geometrie discriminante sur {BOARD}"
    cpos, tpos, collapse_tile, port_tile = geo
    assert collapse_tile != port_tile

    if not _drive_to(rpc, rid, {caster: cpos, target: tpos}):
        pytest.skip(f"geometrie non atteignable (caster={_live_pos(rpc, rid, caster)} "
                    f"cible={_live_pos(rpc, rid, target)}, vise {cpos}/{tpos})")

    state2, board2, _dv2 = _load(rpc, rid)
    from engine.runner.abilities.sisterhood import _sky_strike_dest_tile
    port2 = _sky_strike_dest_tile(state2, caster, target)
    occ = {cpos, tpos}
    old2 = [t for (c, r) in hexgeo.disk(tpos[0], tpos[1], 1)
            for t in [board2.id_at(c, r)]
            if (c, r) not in occ and t is not None and board2.walkable(t)]
    old2.sort(key=lambda t: (hexgeo.distance(cpos, board2.coord(t)), t))
    assert port2 is not None and old2 and board2.coord(old2[0]) != port2, \
        "geometrie live non discriminante"

    # ⚠ un cast REFUSE (cooldown initial, pas mon tour) rend `ok=true, error=null, mutated=false` —
    # un NO-OP SILENCIEUX. C'est `mutated` qui dit si le cast a eu lieu, pas `error`.
    act0 = {}
    for _ in range(8):                                     # cooldown initial 1 tour
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": SKY_ABILITY}}, 120)
        act0 = ((res or {}).get("actions") or [{}])[0]
        if not act0.get("error") and act0.get("mutated"):
            break
        _endturn(rpc, rid)
    assert not act0.get("error") and act0.get("mutated"), \
        f"cast 1025 sans effet: err={act0.get('error')} mutated={act0.get('mutated')}"

    live_after = _live_pos(rpc, rid, caster)
    print(f"\n[165 SKY] ring1_libre={[(board2.coord(t), board2.elevation(t)) for t in old2]} "
          f"collapse={board2.coord(old2[0])} port={port2} live={live_after}")
    assert live_after == port2, (f"atterrissage live {live_after} != port {port2} "
                                 f"(l'ancien collapse aurait donne {board2.coord(old2[0])})")


# ------------------------------------------------------------- #206 : le litteral 0x20 (BlackRage)
#
# `BlackRageAbility$$ExecuteBehaviour` et `WaaaghAbility$$ExecuteBehaviour` appellent
# `First(SortTilesByUtility(<Ability>.GetPossibleMovementTiles(), caster@0x160, 0x20), 1)` : le
# composite est `MovementSuggestion(32) = [Tile(7), TileDistance(33)]` (#201), PAS le `7 = Tile` des
# trois ports ci-dessus. Ces DEUX call-sites gardaient leur collapse « la plus proche du caster »
# apres #201 ; ces tests sont leur CLIQUET, sur le MEME principe que les trois precedents : une
# geometrie ou collapse et utilite DIVERGENT, confrontee au NATIF.
BR_BUILD = ["--p-units", "bloodDeathCompany", "--a-units", "necroWarden", "--no-ai"]
BR_ABILITY = 1163
WA_BUILD = ["--p-units", "orksWarboss", "--a-units", "necroWarden", "--no-ai"]
WA_ABILITY = 1058


def _ms_legacy_nearest(board, pool, cpos):
    """L'ANCIEN collapse des deux call-sites : la tuile du pool la plus PROCHE du caster."""
    return board.coord(_nearest(board, cpos, pool)) if pool else None


def _ms_port(state, pool, caster):
    """Le port #206 : `First(SortTilesByUtility(pool, caster, 0x20), 1)`."""
    from engine.utilities.tile import first_tile_by_utility
    from engine.utilities.utility_type import UtilityType
    best = first_tile_by_utility(state, pool, unit_id=caster,
                                 utility_type=int(UtilityType.MovementSuggestion))
    return state.board.coord(best) if best is not None else None


def _ms_pick_geometry(state, board, caster, target, pool_fn, range_fn):
    """(cpos, tpos) ou l'ancien collapse et le tri `MovementSuggestion(32)` divergent AVEC des
    `Tile(7)` DISTINCTS -- c'est-a-dire ou un terme ENTIER (elevation, effet de tuile) renverse
    l'ordre, et pas seulement le tie-break. Un cas a `Tile(7)` egal ne testerait que l'ordre du
    selecteur source et laisserait passer le collapse sur toute carte plate."""
    from engine.utilities.tile import TILE_UTILITY, runner_tile_leaf_ctx, terrain_tile_effects
    from engine.weights import load as load_weights
    wt = load_weights()
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)

    def tile7(st, t, ctx):
        info = board.by_id.get(t) or {}
        effs = list(terrain_tile_effects(board.tile_def_id(t), []))
        return TILE_UTILITY.evaluate(board.coord(t), {"elevation": info.get("elevation"),
                                                      "elevation_max": emax, "elevation_min": emin,
                                                      "effects": effs}, ctx, wt)

    keep_c, keep_t = _pos(state, caster), _pos(state, target)
    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    found = []
    try:
        for ttile in walk:
            tpos = board.coord(ttile)
            _set_pos(state, target, *tpos)
            for ctile in walk:
                if ctile == ttile:
                    continue
                cpos = board.coord(ctile)
                mr = range_fn(state, caster)
                # `TargetIsNotAdjacent` -> dist >= 2 ; pool non vide -> dist <= portee + 1
                if not 2 <= hexgeo.distance(cpos, tpos) <= mr + 1:
                    continue
                _set_pos(state, caster, *cpos)
                pool = pool_fn(state, caster, target, mr)
                if len(pool) < 2:
                    continue
                near = _ms_legacy_nearest(board, pool, cpos)
                port = _ms_port(state, pool, caster)
                if port is None or near is None or near == port:
                    continue
                ctx = runner_tile_leaf_ctx(state, caster)
                if abs(tile7(state, board.id_at(*near), ctx)
                       - tile7(state, board.id_at(*port), ctx)) < 1e-9:
                    continue                    # egalite de Tile(7) : ne testerait que l'ordre source
                found.append((cpos, tpos))
    finally:
        _set_pos(state, caster, *keep_c)
        _set_pos(state, target, *keep_t)
    if not found:
        return None
    found.sort(key=lambda g: hexgeo.distance(keep_c, g[0]) + hexgeo.distance(keep_t, g[1]))
    return found[0]


def _br_pool(state, caster, target, mr):
    from engine.runner.abilities.loki.strike import black_rage_possible_movement_tiles_selector
    from engine.runner.abilities.behaviours import entities_from_state
    return black_rage_possible_movement_tiles_selector(mr).evaluate(
        entities_from_state(state, caster, target))


def _br_range(state, caster):
    from engine.runner.abilities.loki.strike import _black_rage_move_range
    return _black_rage_move_range(state, caster)


def _wa_pool(state, caster, target, mr):
    from engine.runner.abilities.orks import waaagh_possible_movement_tiles_selector
    from engine.runner.abilities.behaviours import entities_from_state
    return waaagh_possible_movement_tiles_selector(mr).evaluate(
        entities_from_state(state, caster, target))


def _wa_range(state, caster):
    import gameconfig as GC
    from engine.runner.abilities.orks import waaagh_move_range
    extra = int(((GC.ability("Waaagh") or {}).get("constants") or {}).get("extraMovement") or 0)
    return waaagh_move_range(state, caster, extra)


def _cast(rpc, rid, caster, target, ability, tries=8):
    """Caste et rend (action, position du caster APRES) lue dans le retour d'`applyAction`
    (`units[].squadId/pos`) : quand l'action termine la bataille, `decisionView` ne liste plus
    l'unite et `_live_pos` rendrait `None` -- un faux negatif. `mutated == False` sans `error` =
    ce n'est pas le tour du camp du caster -> `endturn` et on retente."""
    act0, res = {}, {}
    for _ in range(tries):
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": int(ability)}}, 120) or {}
        act0 = (res.get("actions") or [{}])[0]
        if not act0.get("error") and act0.get("mutated"):
            break
        _endturn(rpc, rid)
    after = None
    for u in (res.get("units") or []):
        if int(u.get("squadId", -1)) == int(caster):
            p = u.get("pos") or {}
            after = (p.get("col"), p.get("row"))
            break
    return act0, after


def _summon_tiles(act0):
    """Tuiles ou les summons du cast ont ATTERRI (`Unit_IsSummoned` + `Unit_Foot_Tile_Id_*` dans les
    events). Waaagh SPAWNE avant de bouger : le pool que le natif trie est le pool POST-SPAWN."""
    out = set()
    for ev in (act0.get("events") or []):
        tags = ev.get("tags")
        if not tags:
            continue
        try:
            d = json.loads(tags) if isinstance(tags, str) else dict(tags)
        except Exception:
            continue
        if not d.get("Unit_IsSummoned"):
            continue
        for k, v in d.items():
            if k.startswith("Unit_Foot_Tile_Id"):
                out.add(int(v))
    return out


def test_black_rage_charge_tile_follows_movement_suggestion(rpc, build_runner):
    """`BlackRageAbility$$ExecuteBehaviour` : la charge atterrit sur la meilleure tuile au sens
    `MovementSuggestion(32)`, PAS sur la plus proche du caster."""
    rid = build_runner("206206", extra=BR_BUILD, board=BOARD)["rid"]
    state, board, dv = _load(rpc, rid)
    caster, target = _uid_by_vis(dv, "bloodDeathCompany"), _uid_by_vis(dv, "necroWarden")
    assert caster is not None and target is not None, "roster attendu absent du runner"

    geo = _ms_pick_geometry(state, board, caster, target, _br_pool, _br_range)
    assert geo is not None, f"aucune geometrie discriminante sur {BOARD} -- le test ne prouverait rien"
    cpos, tpos = geo
    if not _drive_to(rpc, rid, {caster: cpos, target: tpos}):
        pytest.skip(f"geometrie non atteignable (caster={_live_pos(rpc, rid, caster)} "
                    f"cible={_live_pos(rpc, rid, target)}, vise {cpos}/{tpos})")

    state2, board2, _dv2 = _load(rpc, rid)
    mr = _br_range(state2, caster)
    pool2 = _br_pool(state2, caster, target, mr)
    near2, port2 = _ms_legacy_nearest(board2, pool2, cpos), _ms_port(state2, pool2, caster)
    assert port2 is not None and near2 is not None and port2 != near2, \
        f"geometrie live non discriminante (pool={pool2} port={port2} collapse={near2})"

    act0, live_after = _cast(rpc, rid, caster, target, BR_ABILITY)
    assert not act0.get("error") and act0.get("mutated"), \
        f"cast 1163 sans effet: err={act0.get('error')} mutated={act0.get('mutated')}"
    print(f"\n[206 BR] pool={[(board2.coord(t), board2.elevation(t)) for t in pool2]} "
          f"collapse={near2} port={port2} live={live_after}")
    assert live_after == port2, (f"charge live {live_after} != port {port2} "
                                 f"(l'ancien collapse aurait donne {near2})")
    assert live_after != near2, "le natif suivrait la distance -- collapse NON refute"


def test_waaagh_charge_tile_follows_movement_suggestion(rpc, build_runner):
    """`WaaaghAbility$$ExecuteBehaviour` : idem BlackRage, MAIS l'etage MOVE (`Group(moveB,0x23)`)
    s'execute APRES l'etage SPAWN (`Group(spawnB,0x22)`) -- les 2 Ork Boyz atterrissent sur des
    tuiles adjacentes au CASTER, qui recouvrent souvent le pool de charge. Le pool que le natif
    TRIE est donc le pool POST-SPAWN : on l'ampute des tuiles de spawn (lues dans les events) avant
    de confronter, sinon on mesurerait le TIRAGE et non le TRI."""
    rid = build_runner("206207", extra=WA_BUILD, board=BOARD)["rid"]
    state, board, dv = _load(rpc, rid)
    caster, target = _uid_by_vis(dv, "orksWarboss"), _uid_by_vis(dv, "necroWarden")
    assert caster is not None and target is not None, "roster attendu absent du runner"

    geo = _ms_pick_geometry(state, board, caster, target, _wa_pool, _wa_range)
    assert geo is not None, f"aucune geometrie discriminante sur {BOARD} -- le test ne prouverait rien"
    cpos, tpos = geo
    if not _drive_to(rpc, rid, {caster: cpos, target: tpos}):
        pytest.skip(f"geometrie non atteignable (caster={_live_pos(rpc, rid, caster)} "
                    f"cible={_live_pos(rpc, rid, target)}, vise {cpos}/{tpos})")

    state2, board2, _dv2 = _load(rpc, rid)
    mr = _wa_range(state2, caster)
    pool2 = _wa_pool(state2, caster, target, mr)
    assert len(pool2) >= 2, f"pool live trop petit ({pool2})"

    act0, live_after = _cast(rpc, rid, caster, target, WA_ABILITY)
    assert not act0.get("error") and act0.get("mutated"), \
        f"cast 1058 sans effet: err={act0.get('error')} mutated={act0.get('mutated')}"
    pool3 = [t for t in pool2 if t not in _summon_tiles(act0)]
    if not pool3:
        pytest.skip("les Ork Boyz ont occupe TOUT le pool de charge -- rien a departager")
    near3, port3 = _ms_legacy_nearest(board2, pool3, cpos), _ms_port(state2, pool3, caster)
    print(f"\n[206 WA] pool_post_spawn={[(board2.coord(t), board2.elevation(t)) for t in pool3]} "
          f"collapse={near3} port={port3} live={live_after}")
    assert live_after == port3, (f"charge live {live_after} != port {port3} "
                                 f"(l'ancien collapse aurait donne {near3})")
    if near3 == port3:
        pytest.skip("spawns Ork Boyz : le pool restant ne discrimine plus collapse vs utilite")
    assert live_after != near3, "le natif suivrait la distance -- collapse NON refute"

