"""DarkTalonStrike (actif 1092, `darkaAzrael` Azrael) face COMBAT -> arbre DSL, confronte au LIVE (#117).

`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$ExecuteBehaviour` (mirror 1:1 --
cf. `engine/runner/abilities/darkangels.py`) :
    Foreach( Enemies(Units(GetTilesInBestLine())),
             AddEffect(0x429 = 1065 Pinned, <cible>)  +  DamageUnit(Cache(Units(target@0x178)), <cible>) )
avec `DamageUnit` = UN `AttackWithAbilityDamage` dont degat / profil / coups sont trois noeuds
conditionnes par `AreEqual(<cible>, Cache(Units(target)))` : cible principale -> `minDmg`/`maxDmg` +
`damageProfile` + `nrOfHits` ; toute autre -> `minDmg_2`/`maxDmg_2` + `damageProfile_2` + `nrOfHits_2`.

CE QUE CE TEST GARDE — la GEOMETRIE de ligne, qui est le coeur du port et le seul endroit ou il pouvait
etre faux en silence :

  (A) LIGNE LONGUE (colonne SANS marche d'elevation >= 2) : le SET frappe, le NB DE COUPS par cible, le
      PROFIL par cible et le SET de `Pinned` sont identiques offline / live. DISCRIMINANT : >= 2 ennemis
      de LIGNE touches (un port qui s'arreterait au 1er hexe passerait le test A avec 1 seul).

  (B) MARCHE D'ELEVATION (le quirk `TileUtil$$IsTileValidForList` : `|elev(ref) - elev(tile)| < 2`, active
      par `settings+0x10 = 1` et re-ancre pas-a-pas par `settings+0x11 = 1`) : sur une colonne dont la
      ligne franchit une marche de 2 niveaux, le natif COUPE le beam a la marche. On confronte le SET live
      au port, ET on montre que le gate est PORTANT : le meme arbre construit SANS le gate
      (`check_walkable=False`) frapperait STRICTEMENT PLUS de cibles. Sans cette 2e assertion, le test (B)
      serait incapable d'echouer si le port ignorait l'elevation ET que la geometrie tronquait ailleurs.

CIBLE = une TUILE (`abilityTargets` live : `kind=tile`) -> le `targetId` du message est l'entite-TUILE.
On prend la cible dans `fromHere` (JAMAIS `targets`, superset move-inclus, cf. case-111).

MAGNITUDE NON CONFRONTEE (confond documente, PARTAGE avec test_plasma_cannon_live) : `execute_ability_attack`
ne passe pas `is_ranged` aux modificateurs d'attaquant -> les buffs ranged du caster (LionHelm, high-ground)
manquent offline. On valide STRUCTURE + CIBLAGE + COUPS + PROFIL + EFFET, pas l'egalite de degat brute.

Board `C4_02` (pvp 7x9) : ZERO DryBush/Trench/Swamp/Water/Block (aucun effet de tuile parasite sur une
attaque ranged multi-coups) mais une ELEVATION variee — exactement ce qu'il faut pour (A) et (B). Le test
DERIVE les colonnes (A)/(B) de l'elevation LIVE (`boardGraph`), il n'en hardcode aucune.

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only. Skip si build/darkaAzrael/geometrie indispo.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import gameconfig as GC
from engine.entities.damage_profile_type import DamageProfileType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.darkangels import (DarkTalonStrikeAbility, dark_talon_strike_tree,
                                                dark_talon_get_tiles_in_best_line)
from engine.runner.abilities.behaviours import entities_from_state
from engine.runner.snapshot import load_state
from engine.entities.selectors import Enemies, FixedTileIds, TilesBehindInLine, Units

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "darkaAzrael"
ABILITY = 1092
BOARD = "C4_02"
A_UNITS = "eldarRanger,eldarRanger,eldarRanger,eldarRanger,eldarRanger"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"])
    r.mti = s["mti"]
    return r


def _const(key: str) -> str:
    """Oracle CONFIG (valeur BRUTE lue telle quelle par le natif) — LEVE si la cle manque."""
    consts = ((GC.ability("DarkTalonStrike") or {}).get("constants") or {})
    assert key in consts, (f"oracle introuvable : gameconfig.ability('DarkTalonStrike').constants.{key} "
                           f"absent -- le natif le lit par GetNumberConstant, il DOIT exister")
    return str(consts[key])


def _caster(dv):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER_VIS and u.get("alive")),
                None)


def _straight_run(board, elev, col, rows, max_step: int):
    """Les `rows` consecutives de `col` forment-elles une ligne walkable dont CHAQUE marche d'elevation
    est <= `max_step` ? (mirror de la marche pas-a-pas de `GetTilesBehind` + `IsTileValidForList`)."""
    prev = None
    for r in rows:
        t = board.id_at(col, r)
        if t is None or not board.walkable(t) or elev.get((col, r)) is None:
            return False
        if prev is not None and abs(elev[(col, r)] - prev) > max_step:
            return False
        prev = elev[(col, r)]
    return True


def _find_columns(board, elev, n_line: int):
    """Rend `(colA, rowsA, colB, rowsB, breakIdxB)` :
      - A = une colonne dont `1 + 1 + n_line` rangees consecutives (caster, cible, ligne) ne franchissent
        AUCUNE marche >= 2 -> le beam va au bout ;
      - B = une colonne dont la ligne franchit une marche >= 2 APRES au moins 1 hexe de ligne -> le beam
        casse a `breakIdxB` (index dans la ligne, 1-based).
    None si le board n'offre pas la configuration."""
    need = 2 + n_line
    a = b = None
    for col in sorted({c for (c, _r) in board.by_coord}):
        rows_all = sorted({r for (c, r) in board.by_coord if c == col})
        for i in range(len(rows_all) - need + 1):
            win = rows_all[i:i + need]
            if win != list(range(win[0], win[0] + need)):
                continue
            if any(board.id_at(col, r) is None or not board.walkable(board.id_at(col, r))
                   or elev.get((col, r)) is None for r in win):
                continue
            steps = [abs(elev[(col, win[k + 1])] - elev[(col, win[k])]) for k in range(need - 1)]
            # steps[0] = caster->cible (hors ligne) ; steps[1:] = les marches DE LA LIGNE.
            line_steps = steps[1:]
            if a is None and all(s < 2 for s in line_steps):
                a = (col, win)
            if b is None and any(s >= 2 for s in line_steps[1:]):   # casse APRES >= 1 hexe de ligne
                brk = next(k for k, s in enumerate(line_steps[1:], start=1) if s >= 2)
                b = (col, win, brk)
    if a is None or b is None:
        return None
    return (a[0], a[1], b[0], b[1], b[2])


def _live_hits(cast, ability_id: int):
    """`{target_id: [(amount, profileIndex), ...]}` extrait des tags d'evenement de la cascade."""
    out: dict = {}
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ability_id:
                out.setdefault(td.get("Target_Id"), []).append(
                    (td.get("Amount"), td.get("DamageProfileType")))
    return out


def _positions(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    return dv, {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")}


def _drive_to(rpc, rid, board, wanted: dict, rounds: int = 8):
    """DOCTRINE « drive positions, don't blame geometry » : amene chaque unite de `wanted`
    (`{unitId: (col,row)}`) sur sa tuile, en PLUSIEURS tours si necessaire — `applyAction move` respecte
    la portee de deplacement, donc un placement arbitraire exige des sauts successifs (avec `endturn`
    pour re-armer le mouvement). Approche par la LIGNE HEX (le plus loin d'abord). Rend True si TOUTES
    les unites sont arrivees."""
    import hexgeo as _hx
    for _ in range(rounds):
        _dv, pos = _positions(rpc, rid)
        if all(pos.get(u) == dest for u, dest in wanted.items()):
            return True
        occupied = {p for p in pos.values()}
        for uid, dest in wanted.items():
            cur = pos.get(uid)
            if cur is None or cur == dest:
                continue
            for p in reversed(_hx.line(cur, dest)[1:]):
                t = board.id_at(p[0], p[1])
                if t is None or not board.walkable(t) or (p in occupied and p != dest):
                    continue
                r = rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 60)
                if _ok(r) and (r.get("actions") or [{}])[0].get("mutated"):
                    occupied.discard(cur)
                    occupied.add(p)
                    break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    _dv, pos = _positions(rpc, rid)
    return all(pos.get(u) == dest for u, dest in wanted.items())


def _run_scenario(rpc, rid, board, elev, col, rows, n_line):
    """Place Azrael + les ennemis sur `col`, verifie la legalite du cast (`fromHere`), capture l'etat,
    caste LIVE et rend `(state_snapshot_args, caster_id, tile_id, live_hits, live_pinned)`."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv) or _caster(dv) is None:
        pytest.skip("darkaAzrael absent (pool/spawn)")
    myplayer = _caster(dv).get("owner")
    cid = _caster(dv)["id"]
    enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
    if len(enemies) < n_line + 1:
        pytest.skip(f"moins de {n_line + 1} ennemis vivants")

    # caster sur rows[0], cible sur rows[1], ligne sur rows[2:] ; les ennemis EXCEDENTAIRES sont
    # parques hors de la colonne (l'anneau de la cible ne doit porter aucun autre ennemi).
    wanted = {cid: (col, rows[0])}
    placed = []
    for k in range(1, 2 + n_line):
        wanted[enemies[k - 1]["id"]] = (col, rows[k])
        placed.append(enemies[k - 1]["id"])
    spare = [t for t in sorted(board.by_id)
             if board.walkable(t) and abs(board.coord(t)[0] - col) > 1]
    for j, u in enumerate(enemies[1 + n_line:]):
        if j < len(spare):
            wanted[u["id"]] = board.coord(spare[j])
    if not _drive_to(rpc, rid, board, wanted):
        _dv, pos = _positions(rpc, rid)
        pytest.skip(f"placement incomplet (col {col}, rows {rows}) : "
                    f"{ {u: pos.get(u) for u in wanted} } != { wanted }")
    # rendre la main a mon camp si l'`endturn` du driver a bascule
    for _ in range(2):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        if dv.get("currentPlayer") == myplayer:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == ABILITY), {})
    # RECETTE case-111 : la cible vient de `fromHere` (cast LEGAL depuis la position courante), jamais
    # de `targets` (superset move-inclus) -- sinon un refus de ciblage passerait pour « ability inerte ».
    tgt_tile = board.id_at(col, rows[1])
    legal = [x for x in (ab.get("fromHere") or [])
             if (x.get("tile") or {}).get("col") == col and (x.get("tile") or {}).get("row") == rows[1]]
    if not legal:
        pytest.skip(f"cast 1092 illegal sur la tuile ({col},{rows[1]}) depuis ({col},{rows[0]})")
    tid = legal[0].get("targetId")
    if not isinstance(tid, int):                 # cible TILE : `applyAction` la veut en `to` (hex)
        tid = tgt_tile
        action = {"kind": "ability", "casterId": cid, "abilityType": ABILITY,
                  "to": {"col": col, "row": rows[1]}}
    else:
        action = {"kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY}

    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(rng0):
        pytest.skip("dumpRng KO")
    cast = rpc("applyAction", {"runnerId": rid, "action": action, "captureEvents": True}, 120)
    acts = cast.get("actions") or [{}]
    assert _ok(cast) and acts[0].get("mutated"), (
        f"cast DarkTalonStrike non applique / sans mutation: ok={cast.get('ok')} "
        f"action={acts[0]} -- verifier la LEGALITE de la cible (case-111 : ok/mutated=False + "
        f"2 evenements groupe 12 == REFUS DE CIBLAGE, pas une ability inerte)")
    live = _live_hits(cast, ABILITY)
    dv3 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    pinned = {u["id"] for u in (dv3.get("units") or [])
              if any((e.get("name") or "") == EffectType.Pinned.name for e in (u.get("effects") or []))}
    return (dv2, ob2, snap2), cid, tgt_tile, tid, live, pinned, placed, rng0


def _offline(state_args, board, cid, tile_id, tgt_entity, rng0):
    st = load_state(*state_args, board=board)
    st.rng = _seed_rng(rng0)
    res = DarkTalonStrikeAbility().execute_behaviour(st, cid, tgt_entity)
    assert res is not None and res.get("dsl") is True, f"port 1092 non execute: {res}"
    by_target: dict = {}
    for h in (res.get("hits") or []):
        by_target.setdefault(h["target"], []).append(h["attack"])
    return st, res, by_target


def _build(seed, extra):
    state_file = ROOT / "data" / "rl-state" / f"dts-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
         "--board", BOARD, *extra],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    return state_file, json.loads(state_file.read_text())["runnerId"]


def _board_of(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    tiles = bg["tiles"]
    return Board(tiles, adjacency="native_sym"), {(t["col"], t["row"]): t.get("elevation") for t in tiles}


@pytest.mark.parametrize("scenario", ["long", "elevation_break"])
def test_dark_talon_strike_line_live(live_session, rpc, scenario):
    """(A) ligne longue : SET/COUPS/PROFIL/Pinned offline == live, avec >= 2 ennemis de LIGNE touches.
    (B) marche d'elevation : le beam CASSE a la marche live == offline, et le gate est PORTANT (le meme
    arbre sans gate frapperait strictement plus)."""
    n_line = 3
    state_file, rid = _build("41171", ["--p-units", CASTER_VIS, "--a-units", A_UNITS,
                                       "--hp-target", "90000", "--hp-player", "90000"])
    try:
        board, elev = _board_of(rpc, rid)
        cols = _find_columns(board, elev, n_line)
        if cols is None:
            pytest.skip(f"board {BOARD} n'offre pas les deux colonnes (plate + marche >= 2)")
        colA, rowsA, colB, rowsB, brkB = cols
        col, rows = (colA, rowsA) if scenario == "long" else (colB, rowsB)

        st_args, cid, tile_id, tgt_entity, live, pinned, placed, rng0 = _run_scenario(
            rpc, rid, board, elev, col, rows, n_line)
        st, res, off = _offline(st_args, board, cid, tile_id, tgt_entity, rng0)

        main_unit = next((p for p in placed), None)          # rows[1] = la cible principale
        want_main_prof = int(DamageProfileType[_const("damageProfile")])
        want_line_prof = int(DamageProfileType[_const("damageProfile_2")])
        want_main_hits = int(_const("nrOfHits"))
        want_line_hits = int(_const("nrOfHits_2"))

        # --- 1. SET frappe : offline == live -------------------------------------------------------
        assert set(off) == set(live), (
            f"[{scenario}] SET frappe offline {sorted(off)} != live {sorted(live)} "
            f"(colonne {col}, rangees {rows}, elevations "
            f"{[elev.get((col, r)) for r in rows]})")
        # --- 2. coups + profil par cible ------------------------------------------------------------
        for tid_u, phs in live.items():
            is_main = (tid_u == main_unit)
            want_hits = want_main_hits if is_main else want_line_hits
            want_prof = want_main_prof if is_main else want_line_prof
            assert len(phs) == want_hits, (
                f"[{scenario}] cible {tid_u} ({'main' if is_main else 'ligne'}) : {len(phs)} coups LIVE "
                f"!= oracle config {want_hits}")
            assert {p for _a, p in phs} == {want_prof}, (
                f"[{scenario}] cible {tid_u} : profils live {[p for _a, p in phs]} != oracle config "
                f"{want_prof} ({'damageProfile' if is_main else 'damageProfile_2'})")
            assert len(off[tid_u][0]["per_hit"]) == want_hits, (
                f"[{scenario}] cible {tid_u} : {len(off[tid_u][0]['per_hit'])} coups OFFLINE "
                f"!= oracle config {want_hits}")
        # --- 3. Pinned pose sur TOUS les frappes (live) ET offline ----------------------------------
        assert set(live).issubset(pinned), (
            f"[{scenario}] Pinned live {sorted(pinned)} ne couvre pas toutes les cibles frappees "
            f"{sorted(live)}")
        assert set(res.get("pinned") or []) == set(off), (
            f"[{scenario}] Pinned offline {sorted(res.get('pinned') or [])} != cibles frappees "
            f"{sorted(off)}")

        if scenario == "long":
            # DISCRIMINANT : sans >= 2 cibles de LIGNE, un port qui s'arreterait au 1er hexe passerait.
            assert len(live) >= 3, (
                f"[long] seulement {len(live)} cibles frappees (main + {len(live) - 1} de ligne) : le "
                f"scenario NE DISCRIMINE PAS une ligne tronquee -- geometrie a re-crafter")
        else:
            # (B) le beam CASSE a la marche : main + exactement `brkB` hexes de ligne.
            assert len(live) == 1 + brkB, (
                f"[elevation_break] {len(live)} cibles frappees, attendu 1 + {brkB} (la marche "
                f"d'elevation coupe le beam). elevations {[elev.get((col, r)) for r in rows]}")
            # ... et le gate est PORTANT : sans lui la ligne serait STRICTEMENT plus longue.
            ent = entities_from_state(st, cid, None)
            tgt_ref = FixedTileIds([int(tile_id)])
            gated = dark_talon_get_tiles_in_best_line(tgt_ref)
            no_gate_line = TilesBehindInLine(
                tgt_ref,
                # meme direction que le beam retenu : la 2e tuile de la best-line gatee.
                FixedTileIds([int(gated.evaluate(ent)[1])]),
                check_walkable=False, update_reference=False)
            n_gated = len(Enemies(Units(gated)).evaluate(ent))
            n_free = len(Enemies(Units(no_gate_line)).evaluate(ent)) + 1     # + la cible principale
            assert n_free > n_gated, (
                f"[elevation_break] le gate d'elevation n'est PAS portant dans ce scenario "
                f"(gate={n_gated}, sans-gate={n_free}) -- le test serait incapable d'echouer si le "
                f"port ignorait `IsTileValidForList`")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass
