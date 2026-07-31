#!/usr/bin/env python
"""Probe #383 -- les batchs 3/4 (EXPLOSION) de `RammingSpeed` (1059) : le PORT confronte au NATIF.

CE QU'IL MESURE
---------------
`probe_361_ramming_speed_explosion_batches.py` a etabli que le natif EMET bien ces deux batchs (5
events == 5 attendus, cibles exactes) et que le verrou de `#353-r1` etait un ARTEFACT DE MONTAGE.
Il ne comparait que le COMPTE et les CIBLES. Ce probe-ci compare la LISTE COMPLETE, event pour
event -- `(targetId, healthDmgMin, healthDmgMax, appliedHits)` -- entre :

  * le NATIF (`aiPlaybookPredict`, qui charge `RammingSpeedPlaybook` par ability) ;
  * le PORT LIVRE (`playbook.prediction.make_damage_predictions`) ;
  * le port MUTE (`--mutate`), qui doit DIVERGER -- sans quoi le bras ne discrimine rien.

MONTAGE (herite de `probe_361`, aux trois conditions pres qui ont coute quatre hypotheses fausses)
--------------------------------------------------------------------------------------------------
  1. la GATE `self.Any(p => p.Prediction.WillBeKill)` doit etre OUVERTE -> `--hp-player` bas ; le
     probe RELIT `willBeKill` sur l'event du caster et refuse de conclure si elle est fermee ;
  2. le caster doit AVOIR LA MAIN (`ensure_turn`) -- sinon
     `MovementQuery$$FindAnyOrAllMoveableTiles` repart sur un `OrderedSet` VIDE (garde FLAG) et les
     deux batchs manquent POUR UNE RAISON DE MONTAGE ;
  3. le voisinage de la tuile d'arrivee doit porter un AMI **et** un ENNEMI -- sinon les deux batchs
     ne se distinguent pas l'un de l'autre.

Le probe REFUSE (verdict `BRAS NON DISCRIMINANT`) plutot que de mesurer degrade.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_383_ramming_speed_explosion_port.py
    python probe_383_ramming_speed_explosion_port.py --board C1_03 --seed 38301
    python probe_383_ramming_speed_explosion_port.py --mutate hp-current      # DOIT rougir
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from probe_353_ramming_speed_prediction import build_grafted_seed_bc         # noqa: E402
from probe_353r1_ramming_speed_charge_tile import (                          # noqa: E402
    ENEMY2, FILLER_P, GRAFT, VICTIM, _cast, _ids, _pos, _view,
    controlled_by_current_player, drive_to, ensure_turn)
from probe_361_ramming_speed_explosion_batches import _load, _scan_geometry  # noqa: E402

ABILITY = 1059
ABILITY_NAME = "RammingSpeed"
BOARD = "MC1_67"
HP_PLAYER = 60          # le recul (`nrOfHits_2` coups) doit TUER le caster -> gate OUVERTE

MUTATIONS = ("none", "no-explosion", "hp-current", "friends-only", "enemies-only",
             "tile-utility-only")


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed_bc: Path, seed: int, board: str, level: int, mult: int,
           hp_player: int, hp_current=None) -> int:
    """`--crit/--block-*` a 0 : degat DETERMINISTE et `BlockScenarios` vide cote caster (mesure #372
    : `blockScenarioCount = 0`), donc `get_WillBeKill` retombe sur le scalaire `rawMin@0x1c`.

    `hp_current` DESSOUDE les PV COURANTS du maxPV : `--hp-player` pose `Health` ET
    `RemainingHealth` (donc courant == max, et l'axe `StatPart` de
    `StatAmount(Owner, Health, part = 2)` reste INOBSERVABLE) ; un `--unit-stat
    <graft>:RemainingHealth=<n>` applique APRES (l'ordre est celui de `rl_duel.build`) ne touche que
    le courant. C'est ce qui rend le bras `--mutate hp-current` DISCRIMINANT."""
    state_file.unlink(missing_ok=True)
    stat = "%s:ActiveAbilityLevel=%d,AbilityVariablesMultiplierPercentage=%d" % (GRAFT, level, mult)
    if hp_current is not None:
        stat += ",RemainingHealth=%d" % int(hp_current)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17",
           "--seed-bc", str(seed_bc),
           "--p-units", "%s,%s" % (GRAFT, FILLER_P),
           "--a-units", "%s,%s" % (VICTIM, ENEMY2),
           "--unit-stat", stat,
           "--hp-player", str(int(hp_player)),
           "--crit", "0,0", "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _sig(events) -> list:
    """Signature COMPARABLE cote NATIF : (cible, min, max, coups), triee."""
    return sorted((e.get("targetId"), e.get("healthDmgMin"), e.get("healthDmgMax"),
                   e.get("appliedHits")) for e in events)


def _sig_port(events) -> list:
    """MEME contrat que `probe_353._sig_port` : le natif borne le degat SANTE par les PV courants."""
    return sorted((e.target,
                   min(e.prediction.accurate_health_damage.min, e.prediction.current_health),
                   min(e.prediction.accurate_health_damage.max, e.prediction.current_health),
                   e.prediction.applied_hits) for e in events)


def _ring(board, dv, tile_pos, caster_id) -> dict:
    """Les DEUX ensembles que les batchs 3/4 selectionnent autour de `tile_pos`, derives de la
    composition native `AdjacentUnits(origin) = Units(AdjacentTiles(origin), 1, 3) - origin` :
    unites VIVANTES posees sur une tuile hex-adjacente, ventilees par camp RELATIVEMENT au caster
    (`UnitsByTeamSelector$$CountOrAdd` -> `UnitExtensions$$IsFriend(referent, other)`)."""
    units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("alive")}
    cteam = (units.get(int(caster_id)) or {}).get("team")
    tid = board.id_at(tile_pos[0], tile_pos[1])
    ring = {board.coord(n) for n in board.neighbours(tid)} if tid is not None else set()
    friends, enemies = [], []
    for uid, u in sorted(units.items()):
        p = u.get("pos") or {}
        if (p.get("col"), p.get("row")) not in ring:
            continue
        (friends if u.get("team") == cteam else enemies).append(uid)
    return {"friends": friends, "enemies": enemies}


def _pool(scene, cid, tid, here, board):
    """Le POOL candidat de `RammingSpeedAbility$$GetTileToMoveTo`, cote PORT et depuis la `Scene` :
    `MovableTilesInRange(caster, casterTile, Direct(range), 0, 0) op_BitwiseAnd
    CanAddUnit(AdjacentTiles(target))`, AVANT tri d'utilite. Rend une liste de `(col,row)`."""
    import gameconfig as GC
    from engine.playbook.prediction import ramming_speed as RS
    from engine.runner.abilities.orks import ramming_speed_charge_tiles_selector
    dctx = RS.dsl_context(scene, cid, tid, here)
    if dctx is None or board is None:
        return None
    consts = (GC.ability(RS.RAMMING_SPEED_ABILITY) or {}).get("constants") or {}
    rng = int(consts.get(RS.RAMMING_SPEED_RANGE_KEY) or 0)
    return [list(board.coord(t)) for t in ramming_speed_charge_tiles_selector(rng).evaluate(dctx)]


def _native_movable(sid, rid, unit_id, override_range):
    """Le pool de MOUVEMENT du natif pour `unit_id`, a la portee du selecteur.

    Le RPC `aiMovableTiles` appelle la MEME `MovementQuery$$GetMovableTilesFor(unit,
    ignoreUnitFlags: false, options)` que `MovableTilesInRangeSelector$$Select` (#381), avec
    `side="all"` (il couvre les unites que le joueur courant ne controle pas) et `overrideRange`
    (= le `Direct(GetNumberConstant(0x16))` du selecteur). C'est LE capteur qui separe « pool natif
    plus petit » (residu `#381-r1`) de « meme pool, tri different ».

    Rend une liste de `[col,row]`, ou `None` si l'unite n'est pas listee (= NON MESURE)."""
    res = _r(sid, "aiMovableTiles",
             {"runnerId": rid, "side": "all", "overrideRange": int(override_range)}, 90)
    if not res or res.get("ok") is False:
        return None
    for u in (res.get("units") or []):
        if int(u.get("unitId") or -1) == int(unit_id):
            return sorted([int(t["col"]), int(t["row"])] for t in (u.get("tiles") or [])
                          if t.get("col") is not None)
    return None


def _decompose(scene, board, pool_pos, cid) -> dict:
    """Terme par terme sur le pool, substrat `Scene` : `Tile(7)` d'un cote, la feuille 54
    (`RammingSpeed_MostAdjacentEnemies`) de l'autre. Jumeau de `probe_353r1._decompose`, qui part
    d'un `State` de runner. C'est ce qui rend un ecart de TUILE ATTRIBUABLE au lieu d'etre constate.

    ⚠ Le `meta` par tuile est reconstruit EXACTEMENT comme dans `sort_tiles_by_utility` -- un `meta`
    vide afficherait un `Tile(7)` PLAT qui n'existe pas."""
    from engine import weights as W
    from engine.utilities.ramming_speed import RAMMING_SPEED_MOST_ADJACENT_ENEMIES as U54
    from engine.utilities.tile import (SceneTileState, TILE_UTILITY, scene_tile_leaf_ctx,
                                       terrain_tile_effects)
    wt = W.load()
    ctx = scene_tile_leaf_ctx(scene, cid)
    st = SceneTileState(scene)
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    out = {}
    for p in (pool_pos or []):
        p = (int(p[0]), int(p[1]))
        t = board.id_at(p[0], p[1])
        info = board.by_id.get(t) or {}
        effs = [e.name for e in st.effects.by_unit.get(int(t), []) if not e.consumed and e.name]
        effs += terrain_tile_effects(board.tile_def_id(t), effs)
        meta = {"elevation": info.get("elevation"), "elevation_max": emax, "elevation_min": emin,
                "effects": effs}
        t7, u54 = TILE_UTILITY.evaluate(p, meta, ctx, wt), U54.evaluate(p, meta, ctx, wt)
        out[str(list(p))] = {"tile7": t7, "u54": u54, "total": t7 + u54,
                             "elev": info.get("elevation"), "terrain": board.tile_def_id(t)}
    return out


def _ctx(sid, rid, cid):
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    rpc = lambda m, b, t=60: _r(sid, m, b, t)                       # noqa: E731
    dv = _view(sid, rid)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
    return AICTX.build(rpc, rid, dv, mov_by_unit, int(cid), W.load(),
                       _scene.build_predictor(rpc, rid))


class _Empty:
    """Selecteur MUTE : rend l'ensemble VIDE. Sert aux bras `friends-only`/`enemies-only`, qui
    AMPUTENT un des deux batchs -- si le compte natif ne bouge pas, c'est que la geometrie ne
    peuplait pas ce batch-la et le bras ne prouve rien."""
    def __init__(self, inner):
        self.inner = inner

    def evaluate(self, ctx):
        return []


def _apply_mutation(mutate: str):
    """Pose la mutation sur le MODULE `prediction.ramming_speed` et rend le restaurateur.

    Toutes portent sur des symboles resolus AU NIVEAU MODULE a l'appel (`explosion_events` importe
    `explosion_amount`/`tile_to_move_to`/`Friends`/`Enemies` du module), donc un patch d'attribut
    suffit -- aucune copie de code moteur dans le probe."""
    from engine.playbook.prediction import ramming_speed as RS
    saved = {k: getattr(RS, k) for k in ("explosion_events", "explodes_damage_tree",
                                         "Friends", "Enemies", "tile_to_move_to")}

    def _restore():
        for k, v in saved.items():
            setattr(RS, k, v)

    if mutate == "none":
        return _restore
    if mutate == "no-explosion":
        # L'ETAT D'AVANT #383 : les deux batchs absents (le residu (b) de `#353-r1`).
        RS.explosion_events = lambda *a, **k: []
    elif mutate == "hp-current":
        # `StatAmount(Owner, Health, part = 2 -> MAX)` remplace par la partie COURANTE. Discriminant
        # des que le caster est blesse -- `--hp-player` le force a 60 pour ouvrir la gate.
        from engine.entities.stats import StatPart
        _orig = saved["explodes_damage_tree"]

        def _mutated(explodes_pct, ramming_extra_pct):
            tree = _orig(explodes_pct, ramming_extra_pct)
            tree.base.variant = int(StatPart.CURRENT)
            return tree
        RS.explodes_damage_tree = _mutated
    elif mutate == "friends-only":
        RS.Enemies = _Empty
    elif mutate == "enemies-only":
        RS.Friends = _Empty
    elif mutate == "tile-utility-only":
        # `UtilityBucket([Tile(7), RammingSpeed_MostAdjacentEnemies(54)])` reduit a `Tile(7)` seul --
        # la lecture que `#353-r1` a REFUTEE (elle rend (3,7) la ou le natif pose le caster en (5,7)).
        _orig_tile = saved["tile_to_move_to"]

        def _tile_plain(scene, caster_id, target_id, attack_pos=None, move_range=None):
            import gameconfig as GC
            from engine.runner.abilities.orks import ramming_speed_charge_tiles_selector
            from engine.utilities.tile import (SceneTileState, first_tile_by_utility,
                                               scene_tile_leaf_ctx)
            board = getattr(scene, "board", None)
            dctx = RS.dsl_context(scene, caster_id, target_id, attack_pos)
            if board is None or dctx is None or dctx.target is None:
                return None
            if move_range is None:
                consts = (GC.ability(RS.RAMMING_SPEED_ABILITY) or {}).get("constants") or {}
                move_range = int(consts.get(RS.RAMMING_SPEED_RANGE_KEY) or 0)
            cands = ramming_speed_charge_tiles_selector(int(move_range)).evaluate(dctx)
            if not cands:
                return None
            best = first_tile_by_utility(SceneTileState(scene), cands, unit_id=caster_id,
                                         leaf_ctx=scene_tile_leaf_ctx(scene, caster_id))
            return board.coord(best) if best is not None else None
        RS.tile_to_move_to = _tile_plain
    else:
        raise SystemExit("mutation inconnue : %r" % mutate)
    return _restore


def _predict_port(scene, cid, tid, here, mutate: str) -> list:
    from engine.playbook.prediction import abilities as PA
    restore = _apply_mutation(mutate)
    try:
        return PA.make_damage_predictions(scene, int(cid), int(tid), ABILITY, ABILITY_NAME,
                                          attack_pos=here) or []
    finally:
        restore()


def run(seed: int = 38300, level: int = 8, mult: int = 100, board: str = BOARD,
        hp_player: int = HP_PLAYER, hp_current=None, mutate: str = "none",
        verbose: bool = True) -> dict:
    sid = _resolve_session()
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    sf = logs / ("p383-%s.json" % tag)
    bcf = logs / ("p383-seed-bc-%s.json" % tag)
    out: dict = {"seed": seed, "level": level, "mult": mult, "board": board,
                 "hp_player": hp_player, "hp_current": hp_current, "mutation": mutate}
    out["graft"] = build_grafted_seed_bc(bcf)
    rid = None
    try:
        rid = _build(sf, bcf, seed, board, level, mult, hp_player, hp_current)
        out["runner"] = rid
        state, brd, dv = _load(sid, rid)
        ids = _ids(dv)
        geo = _scan_geometry(state, brd, ids)
        if geo is None:
            out["error"] = ("aucune geometrie ou le voisinage de la tuile d'arrivee porte un AMI et "
                            "un ENNEMI sur %s -- rien n'est joue" % board)
            return out
        tp, e2, cp, ap, tile0 = geo
        out["geometry"] = {"target": list(tp), "enemy2": list(e2), "caster": list(cp),
                           "ally": list(ap), "tile_predite": list(tile0)}
        wanted = {ids[VICTIM]: tp, ids[ENEMY2]: e2, ids[GRAFT]: cp, ids[FILLER_P]: ap}
        if not drive_to(sid, rid, wanted):
            dv = _view(sid, rid)
            out["error"] = "drive KO : voulu %s obtenu %s" % (
                {k: list(v) for k, v in wanted.items()}, {u: _pos(dv, u) for u in wanted})
            return out
        out["turn_given"] = ensure_turn(sid, rid, ids[GRAFT])
        dv = _view(sid, rid)          # RELIRE : `dv` datait d'AVANT le drive (positions perimees)

        cid, tid = ids[GRAFT], ids[VICTIM]
        out["caster_id"], out["target_id"] = cid, tid
        ctrl = controlled_by_current_player(sid, rid)
        out["caster_has_turn"] = (int(cid) in ctrl) if ctrl else None

        ctx = _ctx(sid, rid, cid)
        scene = ctx.scene
        mp = ctx.me.get("pos") or {}
        here = (mp.get("col"), mp.get("row"))
        out["caster_pos"] = list(here)
        out["caster_hp"], out["caster_hpmax"] = scene.hp(cid), scene.hpmax(cid)

        # --- entrees EFFECTIVES du batch EXPLOSION, re-derivees (jamais supposees)
        from engine.playbook.prediction import ramming_speed as RS
        out["explosion_amount"] = RS.explosion_amount(scene, cid, tid, here)
        port_tile = RS.tile_to_move_to(scene, cid, tid, here)
        out["port_tile"] = list(port_tile) if port_tile else None

        nat = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tid,
                                            "abilityType": ABILITY}, 150)
        out["native_playbook"] = nat.get("playbookClass")
        out["native_error"] = nat.get("error")
        nev = nat.get("events") or []
        out["native_events"] = [{"targetId": e.get("targetId"),
                                 "healthDmgMin": e.get("healthDmgMin"),
                                 "healthDmgMax": e.get("healthDmgMax"),
                                 "appliedHits": e.get("appliedHits"),
                                 "willBeKill": e.get("willBeKill")} for e in nev]
        out["native_sig"] = _sig(nev)
        out["n_native"] = len(nev)
        # TRI-ETAT (#372) : `willBeKill` n'est publie que par le decodeur du capteur ; `None` = NON
        # MESURE, jamais « la gate est fermee ». Le discriminant de MONTAGE reste le COMPTE natif
        # (`n_native > 2` = les batchs 3/4 ont ete emis) -- lire un champ absent comme un refus est
        # exactement le faux vert de `#361`.
        self_ev = next((e for e in nev if e.get("targetId") == cid), None)
        out["self_will_be_kill"] = (self_ev or {}).get("willBeKill")

        port = _predict_port(scene, cid, tid, here, mutate)
        out["port_sig"] = _sig_port(port)
        out["n_port"] = len(port)
        out["port_events"] = [{"target": e.target, "friendly": bool(e.friendly)} for e in port]
        out["match"] = (out["port_sig"] == out["native_sig"])

        # --- POOL NATIF de mouvement, LU AVANT le cast (qui deplace le caster).
        import gameconfig as _GC
        _rng = int(((_GC.ability(ABILITY_NAME) or {}).get("constants") or {}).get("range") or 0)
        out["native_movable"] = _native_movable(sid, rid, cid, _rng)
        out["port_movable_n"] = None

        # --- DECOMPOSITION PAR ETAGE : la TUILE. Le cast REEL pose le caster sur la tuile que
        # `GetTileToMoveTo` a designee (`ExecuteBehaviour` = `If(!IsAdjacent(caster, target),
        # MoveUnit(caster, GetTileToMoveTo()))`) -- c'est le SEUL canal qui l'expose, et il est deja
        # confronte 2/2 par `#353-r1`. Il vient APRES la prediction (il consomme le tour).
        # Sans lui, un ecart d'events ne dit pas s'il vient de la TUILE ou du SELECTEUR.
        _, landed = _cast(sid, rid, cid, tid)
        out["native_tile"] = list(landed) if landed else None
        out["tile_match"] = (bool(landed) and port_tile is not None
                             and tuple(landed) == tuple(port_tile))
        if landed:
            out["ring_native"] = _ring(brd, dv, tuple(landed), cid)
        if port_tile:
            out["ring_port"] = _ring(brd, dv, tuple(port_tile), cid)
        # UN CRAN DE PLUS quand la tuile diverge : la tuile NATIVE est-elle seulement DANS le pool
        # candidat du port ? Absente -> l'ecart est le POOL (`MovableTilesInRange` : le port rend le
        # `visited` d'un BFS qui TRAVERSE, le natif un PATHFINDING, cf. `#381-r1`). Presente mais
        # perdante -> l'ecart est le TRI (utilite / ordre source).
        out["pool"], out["native_tile_in_pool"] = _pool(scene, cid, tid, here, brd), None
        if out["pool"] is not None and landed:
            out["native_tile_in_pool"] = (list(landed) in out["pool"])
        if not out.get("tile_match"):
            out["utilities"] = _decompose(scene, brd, out.get("pool"), cid)
            # Le pool du PORT prive du pool de mouvement NATIF = les candidates que le port croit
            # atteignables et que le natif n'atteint pas. Non vide => residu `#381-r1` (POOL).
            nm = out.get("native_movable")
            out["pool_not_native_movable"] = (
                None if nm is None else [p for p in (out.get("pool") or []) if p not in nm])
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sf.unlink(missing_ok=True)
        bcf.unlink(missing_ok=True)

    # --- VERDICT DERIVE DES CHAMPS (jamais un texte ecrit d'avance)
    if out.get("error"):
        out["ok"] = False
        out["verdict"] = "MONTAGE KO : %s" % out["error"]
    elif out.get("native_error"):
        out["ok"] = False
        out["verdict"] = "NATIF EN ERREUR : %s -- rien n'est mesure" % out["native_error"]
    elif out.get("caster_has_turn") is not True:
        out["ok"] = False
        out["verdict"] = (
            "BRAS NON DISCRIMINANT : le caster n'a pas la main (caster_has_turn=%s). "
            "`MovableTilesInRange(Caster, ...)` repart d'un `OrderedSet` VIDE (garde FLAG de "
            "`MovementQuery$$FindAnyOrAllMoveableTiles`) -- on mesurerait le MONTAGE, pas l'arbre."
            % out.get("caster_has_turn"))
    elif out.get("n_native", 0) <= 2:
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : le natif rend %d events (<= 2) -- les batchs 3/4 "
                          "sont VIDES cote natif, il n'y a rien a confronter (gate "
                          "`Any(selfPreds, WillBeKill)` : willBeKill=%s sur l'event du caster ; "
                          "baisser --hp-player si elle est fermee)."
                          % (out.get("n_native", 0), out.get("self_will_be_kill")))
    elif mutate != "none":
        out["ok"] = not out["match"]
        out["verdict"] = (
            "MUTATION %r : le port MUTE %s le natif (port=%s natif=%s) -- le bras %s ce terme."
            % (mutate, "DIVERGE de" if not out["match"] else "s'accorde AVEC",
               out["port_sig"], out["native_sig"],
               "DISCRIMINE" if not out["match"] else "NE DISCRIMINE PAS"))
    elif out["match"]:
        out["ok"] = True
        out["verdict"] = ("PORT == NATIF sur %d events (dont %d d'EXPLOSION) : %s"
                          % (out["n_native"], max(0, out["n_native"] - 2), out["native_sig"]))
    elif out.get("tile_match") is False and out.get("native_tile"):
        out["ok"] = False
        # L'anneau NATIF est-il exactement ce que le natif a emis ? Si oui, les SELECTEURS des
        # batchs 3/4 sont hors de cause et l'ecart est ENTIEREMENT a l'etage TUILE.
        nat_expl = sorted(t for t, *_ in out["native_sig"] if t != cid)
        rn = out.get("ring_native") or {}
        ring_ids = sorted((rn.get("friends") or []) + (rn.get("enemies") or []))
        out["selectors_exonerated"] = (sorted(set(nat_expl)) == sorted(set(ring_ids + [tid])))
        extra = out.get("pool_not_native_movable")
        if extra is None:
            cause = ("pool de mouvement natif NON LU (`aiMovableTiles` muet) -- l'etage TUILE n'est "
                     "pas decompose plus loin")
        elif extra:
            cause = ("le POOL : %s sont dans le pool du port mais HORS du pool de mouvement NATIF "
                     "(%d tuiles). `MovableTilesInRange` rend cote port le `visited` d'un BFS qui "
                     "TRAVERSE, cote natif un PATHFINDING -- RESIDU `#381-r1`, non traite ici"
                     % (extra, len(out.get("native_movable") or [])))
        else:
            cause = ("le TRI d'utilite / l'ordre source : la tuile native est %s le pool du port et "
                     "tout le pool du port est atteignable par le natif"
                     % ("DANS" if out.get("native_tile_in_pool") else "HORS DE"))
        out["verdict"] = (
            "PORT != NATIF, et l'ECART EST ENTIEREMENT SUR LA TUILE : le port designe %s, le natif "
            "POSE le caster en %s (cast reel). Anneaux : port=%s natif=%s -- et les events "
            "d'EXPLOSION du natif sont EXACTEMENT l'anneau de SA tuile (%s), donc les selecteurs "
            "`Friends`/`Enemies(AdjacentUnits(...))` des batchs 3/4 sont HORS DE CAUSE. Cause : %s."
            % (out.get("port_tile"), out.get("native_tile"), out.get("ring_port"),
               out.get("ring_native"), out.get("selectors_exonerated"), cause))
    else:
        out["ok"] = False
        out["verdict"] = ("PORT != NATIF a TUILE EGALE (%s) : port=%s natif=%s (amount=%s, "
                          "voisinage=%s) -- l'ecart est dans les SELECTEURS ou le degat."
                          % (out.get("port_tile"), out["port_sig"], out["native_sig"],
                             out.get("explosion_amount"), out.get("ring_port")))

    if verbose:
        print("[383] runner=%s board=%s seed=%s niveau=%s hp_player=%s mutation=%s"
              % (out.get("runner"), board, seed, level, hp_player, mutate))
        print("[383] geo=%s" % json.dumps(out.get("geometry")))
        print("[383] caster=%s pos=%s hp=%s/%s | main=%s willBeKill=%s | tuile_port=%s amount=%s"
              % (out.get("caster_id"), out.get("caster_pos"), out.get("caster_hp"),
                 out.get("caster_hpmax"), out.get("caster_has_turn"),
                 out.get("self_will_be_kill"), out.get("port_tile"),
                 out.get("explosion_amount")))
        print("[383] playbook natif = %s | erreur = %s"
              % (out.get("native_playbook"), out.get("native_error")))
        for e in out.get("native_events") or []:
            print("        natif %s" % json.dumps(e, sort_keys=True))
        for e in out.get("port_events") or []:
            print("        port  %s" % json.dumps(e, sort_keys=True))
        print("  natif = %s" % (out.get("native_sig"),))
        print("  port  = %s" % (out.get("port_sig"),))
        print("[383] tuile : port=%s natif(cast)=%s match=%s | anneau port=%s natif=%s"
              % (out.get("port_tile"), out.get("native_tile"), out.get("tile_match"),
                 json.dumps(out.get("ring_port")), json.dumps(out.get("ring_native"))))
        if out.get("utilities"):
            print("[383] pool=%s | natif_dans_pool=%s | pool_hors_mouvement_natif=%s "
                  "| |mouvement natif|=%s"
                  % (out.get("pool"), out.get("native_tile_in_pool"),
                     out.get("pool_not_native_movable"),
                     None if out.get("native_movable") is None else len(out["native_movable"])))
            for k, v in sorted(out["utilities"].items()):
                print("        util %s %s" % (k, json.dumps(v, sort_keys=True)))
        print("[383] %s" % out.get("verdict"))
        print("[383] -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=38300)
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--mult", type=int, default=100)
    ap.add_argument("--board", default=BOARD, help="board CHOISI (runner.md sec.2), jamais subi")
    ap.add_argument("--hp-player", type=int, default=HP_PLAYER)
    ap.add_argument("--hp-current", type=int, default=None,
                    help="PV COURANTS du greffon (`RemainingHealth`), pose APRES --hp-player : "
                         "dessoude courant et MAX, seul regime ou l'axe `StatPart` de "
                         "`StatAmount(Owner, Health, 2)` est observable")
    ap.add_argument("--mutate", choices=MUTATIONS, default="none",
                    help="GARDE ADVERSARIALE : le port est volontairement FAUX, le probe DOIT rougir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, level=a.level, mult=a.mult, board=a.board, hp_player=a.hp_player,
              hp_current=a.hp_current, mutate=a.mutate, verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
