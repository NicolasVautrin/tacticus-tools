"""probe #302 tranche 3 -- `1148 DaemonicOrdnance` sur la route de decision a cibles TUILE.

CE QUE CE PROBE MESURE (et qu'aucune lecture du decompile ne donne)
-------------------------------------------------------------------
La RE est faite (`engine/playbook/daemonic_ordnance.py` porte le mirror 1:1 de
`IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$CalculateCustomUtility`). Restent QUATRE
choses qui ne se lisent que LIVE :

1. **Le cooldown.** 1148 arrive avec `initialCooldownTurns = 1` : au tour du build elle est
   INDISPONIBLE, et une mesure faite la se lit comme « le natif refuse la cible tuile » -- c'est
   exactement l'artefact qui avait produit une conclusion architecturale FAUSSE sur 1169
   (`case-302` §5). `build_ready` PURGE le cooldown et l'assert.
2. **La DIRECTION du triangle.** `DaemonicOrdnanceAbility$$GetTargetAreaTiles` vaut
   `TilesOnSameElevation(target, TilesInTriangleShape(target, If(IsPositionMachineForCurrentPlayer(2),
   1, 4)), 1)`. Le predicat interroge le slot MoW du joueur COURANT -- une donnee d'ETAT. Le probe
   imprime `decisionView.mows` et le slot retenu : si le port et le natif divergent la-dessus, ils
   visent deux triangles DIFFERENTS, et le desaccord de cible le montre.
3. **L'accord natif/moteur sur (ability, cible TUILE)**, par `aiDryRunAllUnits` -- il n'existe
   aucun oracle PAR ETAGE pour une cible tuile (`rpc-predict.ts::pairUtility` ne resout `targetId`
   que sur `EntityType.Unit`, cf. `case-302` §7 tranche 5).
4. **Les bras de NECESSITE** : custom force a 0, registre non-attaque vide, domaine force a UNITE,
   `_best_attack`. Sans eux, un accord ne prouve pas que ce port-ci l'a produit.

MONTAGE. 1148 est portee par `blackForgefiend` (MACHINE OF WAR, hors `decisionView.units`) : on la
GREFFE sur une unite du pool -- le natif charge le playbook PAR ABILITY, jamais par unite
(`case-92` §5bis), et le custom de 1148 ne lit NI stat NI trait du caster (seulement `caster.team`,
pour `IsEnemy`), donc la greffe est legitime ici.

Les trois ennemis sont poses en TRIANGLE HEX SERRE (A, A+S, A+SE). Ce cluster donne du CONTRASTE
quelle que soit la direction retenue par le natif -- c'est voulu : le montage ne presuppose pas la
direction, il la laisse trancher le choix de tuile.

  * direction 1 (coin {S, SE}) : la tuile A capte les TROIS (custom 30) ;
  * direction 4 (coin {NW, N}) : la tuile A+S en capte DEUX (custom 20).

DEUX BRAS, et le second est le TEMOIN :
  * `--hp-target 400000` : cibles quasi increvables -> l'utilite d'attaque s'effondre, 1148 domine ;
  * `--hp-target 1`      : cibles one-shot -> le composite `KillUnit` domine, le natif ATTAQUE.
Sans le temoin, un port qui casterait 1148 SYSTEMATIQUEMENT passerait toutes les autres gardes.

Usage (depuis scripts/python, ASCII only) :
    python probe_302_3_daemonic_ordnance.py --decision
    python probe_302_3_daemonic_ordnance.py --stage        # etage kit/cooldown/domaine seul
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.selectors.geometry import neighbour_at

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_do_graft.json"

DAEMONIC = int(ActiveAbilityType.DaemonicOrdnance)          # 0x47c = 1148
NORMAL = 69

BOARD = "MC1_67"
# Plateau du SECOND CAS DISCRIMINANT (`--flip`) : son SpawnPointSet actif declare
# `MachineOfWarPosition = 0` pour les DEUX camps, la ou celui de `MC1_67` declare (2, 1). Le
# predicat `IsPositionMachineForCurrentPlayer(2)` bascule donc de VRAI a FAUX, et avec lui la
# direction du triangle (`{S, SE}` -> `{NW, N}`). Meme geometrie (7x9), memes tuiles jouables.
BOARD_FLAT = "C1_03"
SEED = 909
RANK = "17"

GRAFT_ON = "deathTyphus"                  # dans `rl_duel build --list-pool` au rank 17
P_UNITS = "deathTyphus,deathPutrifier"
A_UNITS = "orksWarboss,necroWarden,astraCreed"

CASTER_VID = GRAFT_ON
A_VID, B_VID, C_VID = "orksWarboss", "necroWarden", "astraCreed"

CASTER_TILE = (2, 4)
CLUSTER_ANCHOR = (4, 4)
# Cluster TRIANGLE HEX SERRE : l'ancre + ses voisins S (dir 0) et SE (dir 1). Cf. l'en-tete --
# `_TRIANGLE_SHAPE_DIRECTIONS` de `engine.entities.selectors.geometry` : coin 1 = {S, SE},
# coin 4 = {NW, N}. Ce cluster porte du contraste dans les DEUX cas.
CLUSTER = (CLUSTER_ANCHOR,
           neighbour_at(CLUSTER_ANCHOR[0], CLUSTER_ANCHOR[1], 0),
           neighbour_at(CLUSTER_ANCHOR[0], CLUSTER_ANCHOR[1], 1))

HP_FAVOURABLE = 400000
HP_WITNESS = 1

# `FixMath_NET_Fix64__op_Implicit(0xa)` du corps natif -- le pas du custom, par ennemi de la zone.
# Re-expose ici pour que la garde n'ait pas a le re-ecrire (source unique = le playbook).
ENEMY_STEP = 10.0


# ------------------------------------------------------------------------------ montage (live)

def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _duel(args, state: Path, rid: int) -> None:
    _run(args + ["--state-file", str(state), "--runner", str(rid)])


def write_graft_seed_bc() -> None:
    """Greffe `ActiveAbilities = [1148]` sur `GRAFT_ON` dans une COPIE de la seed BC."""
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == GRAFT_ON:
            u["ActiveAbilities"] = [DAEMONIC]
            n += 1
    if n != 1:
        raise SystemExit("greffe impossible : %d entree(s) %r dans BC.Units" % (n, GRAFT_ON))
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")


def _dv(rid: int) -> dict:
    import probe_27_3_live as L
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    out = {}
    for u in (_dv(rid).get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")))
    return out


def build(hp_target: int, state: Path, board: str = BOARD) -> int:
    write_graft_seed_bc()
    extra = ["--hp-target", str(hp_target)] if hp_target else []
    _run(["build", "--seed", str(SEED), "--board", board, "--rank", RANK,
          "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
          "--state-file", str(state)] + extra)
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    placement = ((ids[A_VID], CLUSTER[0]), (ids[B_VID], CLUSTER[1]), (ids[C_VID], CLUSTER[2]),
                 (ids[CASTER_VID], CASTER_TILE))
    for unit, to in placement:
        _duel(["act", "move", "--unit", str(unit), "--to", "%d,%d" % to], state, rid)
    return rid


def spawn_groups(state_name: str):
    """Les `SpawnPointGroups` du SpawnPointSet ACTIF, lus dans la BC que le runner EXECUTE.

    `rl_duel build` ecrit la BC normalisee dans son state-file : c'est litteralement l'objet que
    `buildRunner` a consomme, donc la MEME structure que `BattleQuery+0x78`
    (`Board.SpawnPointSets[SpawnPointSetIndex].SpawnPointGroups`). Aucun RPC ne l'expose par runner
    -- c'est le residu d'outillage nomme par `case-302`."""
    from engine.services.machine_of_war_position import spawn_groups_from_battle_config
    p = LOGS / state_name
    if not p.exists():
        return None
    return spawn_groups_from_battle_config(json.loads(p.read_text(encoding="utf-8")).get("bc") or {})


def _caster_state(rid: int):
    c = next((u for u in (_dv(rid).get("units") or []) if u.get("visualId") == CASTER_VID), None)
    if c is None:
        return None, None, None
    ab = next((a for a in (c.get("abilities") or []) if a.get("id") == DAEMONIC), None)
    return c.get("id"), (ab or {}).get("cooldown"), _dv(rid).get("toActivate")


def build_ready(hp_target: int, state_name: str, board: str = BOARD) -> int:
    """Monte le montage PUIS purge le cooldown initial de 1148 (`initialCooldownTurns = 1`).

    Les fins de tour ne sont PAS cosmetiques : tant que `RemainingCooldownTurns > 0`, le natif ne
    PEUT PAS proposer l'ability, et la mesure ne dirait rien du ciblage tuile. Les positions
    crafttees survivent (on termine les tours a vide)."""
    state = LOGS / state_name
    rid = build(hp_target, state, board)
    for _ in range(4):
        cid, cd, to_act = _caster_state(rid)
        if cid is not None and cd in (None, 0) and cid in (to_act or []):
            return rid
        _duel(["act", "endturn"], state, rid)
    raise SystemExit("cooldown de 1148 jamais purge sur le runner %d" % rid)


# ----------------------------------------------------------------------------- etages mesures

def stage(rid: int, caster: int) -> dict:
    """Kit REEL vu par `unitAbilityTypes` + domaine de cibles + slot MoW du joueur courant."""
    import probe_27_3_live as L
    from engine.ai import context as C

    dv = _dv(rid)
    me = next((u for u in (dv.get("units") or []) if u.get("id") == caster), None)
    ab = next((a for a in ((me or {}).get("abilities") or []) if a.get("id") == DAEMONIC), None)
    at = L._rpc("abilityTargets", [{"runnerId": rid, "unitId": caster, "allAbilities": True}])
    kinds, count = {}, 0
    for u in (at.get("units") or []):
        if u.get("unitId") != caster:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != DAEMONIC:
                continue
            count += int(a.get("targetCount") or 0)
            for t in (a.get("targets") or []):
                kinds[t.get("kind")] = kinds.get(t.get("kind"), 0) + 1
    tid_by_pos = C._board_tile_ids(lambda m, b, to=40: L._rpc(m, [dict(b)]), rid)
    mows = dv.get("mows") or []
    slot_by_player = C._mow_slot_by_player(dv)
    return {"in_kit": ab is not None, "usable": (ab or {}).get("usable"),
            "cooldown": (ab or {}).get("cooldown"), "kind": (ab or {}).get("kind"),
            "target_count": count, "target_kinds": kinds,
            "current_player": dv.get("currentPlayer"), "mow_rows": len(mows),
            "mow_slot_by_player": slot_by_player,
            "mow_slot_current": slot_by_player.get(dv.get("currentPlayer")),
            "tile_ids": len(tid_by_pos)}


def native(rid: int, caster: int) -> tuple:
    """Le choix du natif : `(abilityType, targetId)` de l'`ActiveAbilityMessage` propose."""
    import probe_27_3_live as L
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    for u in (dr.get("units") or []):
        if u.get("unitId") != caster:
            continue
        for m in (u.get("proposed") or []):
            if m.get("cls") == "ActiveAbilityMessage":
                return (m.get("abilityType"), m.get("targetId"))
    return (None, None)


def engine(rid: int, caster: int, groups=None) -> dict:
    """Decision MOTEUR sur le MEME etat + bras de necessite + decomposition par etage.

    `groups` = `SpawnPointGroups` du set actif (cf. `spawn_groups`) -- l'entree du predicat
    `IsPositionMachineForCurrentPlayer`. Le bras `nogroups` rejoue la MEME decision SANS elle :
    c'est la mesure de ce que vaut le port quand le canal manque (l'etat d'avant cette tranche)."""
    import engine_validate as EV
    import probe_27_3_live as L
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook import nonattack as NA
    from engine.ai import context as AICTX

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)              # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, wt, predictor, spawn_groups=groups)
    pb = PB.REGISTRY[DAEMONIC]

    targets = pb.eligible_targets(ctx, DAEMONIC)
    per_target = [(t, pb.calculate_custom_utility(ctx, ctx.origin, t, DAEMONIC)) for t in targets]
    preds = {t: len(pb.make_damage_predictions(ctx, ctx.origin, t, DAEMONIC)) for t in targets}
    # VUE ROUGE : ce que `eligible_targets` rend avec le domaine force a UNITE (l'etat d'AVANT la
    # route tuile). Mesure, pas hypothese.
    orig_dom = type(pb).targets_tiles
    type(pb).targets_tiles = lambda self, aid: False
    try:
        targets_unit_domain = pb.eligible_targets(ctx, DAEMONIC)
    finally:
        type(pb).targets_tiles = orig_dom

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor, spawn_groups=groups)
    # BRAS `nogroups` : le MEME moteur prive du canal `SpawnPointGroups`. Il mesure l'ecart que
    # produit le predicat `IsPositionMachineForCurrentPlayer` quand il retombe sur son repli --
    # c'est-a-dire l'ETAT D'AVANT cette tranche, pas une hypothese sur lui.
    nogroups = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = lambda self, c, tile, target, aid: 0.0
    try:
        zero = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor,
                                spawn_groups=groups)
    finally:
        type(pb).calculate_custom_utility = orig
    saved = dict(NA.NONATTACK_PLAYBOOKS)
    NA.NONATTACK_PLAYBOOKS.clear()
    try:
        noroute = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor,
                                   spawn_groups=groups)
    finally:
        NA.NONATTACK_PLAYBOOKS.update(saved)
    from engine.ai.action_generators import ComparableAbilityGenerator
    best = ComparableAbilityGenerator()._best_attack(ctx)
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "nogroups": (nogroups.get("ability"), nogroups.get("target")),
            "zero": (zero.get("ability"), zero.get("target")),
            "noroute": (noroute.get("ability"), noroute.get("target")),
            "targets": targets, "per_target": per_target, "pred_counts": preds,
            "targets_unit_domain": targets_unit_domain,
            "best_attack_ability": (best[3] if best else None),
            "mow_position": ctx.machine_of_war_position(),
            "current_player_team": ctx.current_player_team}


def measure(hp_target: int, state_name: str, board: str = BOARD) -> dict:
    rid = build_ready(hp_target, state_name, board)
    caster, cd, _ = _caster_state(rid)
    pos = {v: p for v, (_i, p) in _units(rid).items()}
    groups = spawn_groups(state_name)
    return {"rid": rid, "caster": caster, "cooldown": cd, "positions": pos, "board": board,
            "spawn_groups": groups, "stage": stage(rid, caster),
            "native": native(rid, caster), "engine": engine(rid, caster, groups)}


def dispose(rid: int) -> None:
    import probe_27_3_live as L
    try:
        L._rpc("disposeRunner", [{"runnerId": rid}])
    except Exception:                                       # noqa: BLE001
        pass


# ------------------------------------------------------------------------------------- sorties

def _print_arm(name: str, r: dict) -> None:
    e, s = r["engine"], r["stage"]
    print("\n=== bras %s (runner %d, caster u%s, board %s) ==="
          % (name, r["rid"], r["caster"], r.get("board")))
    print("  positions        = %s" % {k: v for k, v in r["positions"].items()})
    print("  cooldown 1148    = %s (doit etre None/0)" % r["cooldown"])
    print("  kit REEL         : in_kit=%s usable=%s kind=%s" % (s["in_kit"], s["usable"], s["kind"]))
    print("  domaine 1148     : %d cibles, kinds=%s" % (s["target_count"], s["target_kinds"]))
    print("  currentPlayer=%s  mows=%d  slot_by_player=%s  team courante=%s"
          % (s["current_player"], s["mow_rows"], s["mow_slot_by_player"], e["current_player_team"]))
    print("  SpawnPointGroups = %s" % ([(g.get("TeamWithPlayerIndex"),
                                         g.get("MachineOfWarPosition"))
                                        for g in (r["spawn_groups"] or [])] or "NON LUS"))
    print("  MachineOfWarPosition(joueur courant) = %s (2 = Bottom -> triangle {S,SE})"
          % e["mow_position"])
    print("  natif            = %s" % (r["native"],))
    print("  moteur           = %s (to=%s)" % (e["on"], e["to"]))
    print("  nogroups         = %s   (canal SpawnPointGroups coupe)" % (e["nogroups"],))
    print("  zero  (custom=0) = %s" % (e["zero"],))
    print("  noroute          = %s" % (e["noroute"],))
    print("  best_attack rend = %s" % e["best_attack_ability"])
    print("  eligibles        = %d tuiles | domaine UNITE force = %s"
          % (len(e["targets"]), e["targets_unit_domain"]))
    vals = sorted({c for _t, c in e["per_target"]})
    print("  custom distinct  = %s" % vals)
    print("  predictions !=0  = %d cible(s) (attendu 0 : la zone ne brule pas)"
          % sum(1 for n in e["pred_counts"].values() if n))
    print("  ACCORD           = %s" % ("OUI" if e["on"] == r["native"] else "NON"))


def decision(hp_fav: int, hp_wit: int) -> int:
    rids = []
    try:
        a = measure(hp_fav, "rs_302_3_a.json")
        rids.append(a["rid"])
        _print_arm("favorable", a)
        b = measure(hp_wit, "rs_302_3_b.json")
        rids.append(b["rid"])
        _print_arm("TEMOIN", b)
        print("\n=== VERDICT ===")
        print("  natif caste 1148 au bras favorable : %s" % (a["native"][0] == DAEMONIC))
        print("  natif caste 1148 au bras TEMOIN    : %s (doit etre False)"
              % (b["native"][0] == DAEMONIC))
        print("  accord des deux bras               : %s"
              % (a["engine"]["on"] == a["native"] and b["engine"]["on"] == b["native"]))
    finally:
        for rid in rids:
            dispose(rid)
    return 0


def flip(hp_target: int) -> int:
    """SECOND CAS DISCRIMINANT : le MEME montage sur un plateau dont le groupe de spawn declare
    `MachineOfWarPosition = 0`.

    `MC1_67` (SpawnPointSetIndex 1) declare `(TWPI 0 -> 2)`, donc le predicat est VRAI et le
    triangle vaut `{S, SE}`. `C1_03` declare `(0, 0)` pour les DEUX camps : le predicat devient
    FAUX et le triangle bascule sur `{NW, N}`. Le natif ET le port doivent changer de cible
    ENSEMBLE. Sans ce bras, l'accord de `--decision` ne distinguerait pas « le port lit le groupe »
    de « le port repond VRAI par hasard ».

    Le cluster est le meme (A, A+S, A+SE) : sous `{S, SE}` la tuile A capte les TROIS ennemis
    (custom 30), sous `{NW, N}` aucune tuile n'en capte plus de DEUX (custom 20)."""
    r = measure(hp_target, "rs_302_3_f.json", BOARD_FLAT)
    try:
        _print_arm("FLIP (" + BOARD_FLAT + ", groupe a MoWPos 0)", r)
        e = r["engine"]
        vals = sorted({c for _t, c in e["per_target"]})
        print("\n=== VERDICT FLIP ===")
        print("  MachineOfWarPosition attendue 0, mesuree %s" % e["mow_position"])
        print("  custom max = %s (30 = triangle {S,SE} ; 20 = triangle {NW,N})"
              % (vals[-1] if vals else None))
        print("  ACCORD = %s" % (e["on"] == r["native"]))
    finally:
        dispose(r["rid"])
    return 0


def stage_only(hp_target: int) -> int:
    rid = build_ready(hp_target, "rs_302_3_s.json")
    try:
        caster, _cd, _ = _caster_state(rid)
        st = stage(rid, caster)
        print("runner=%d caster=u%s" % (rid, caster))
        for k, v in st.items():
            print("  %-20s = %s" % (k, v))
        print("  cluster vise    = %s" % (CLUSTER,))
        print("  voisins ancre   = %s" % (hexgeo.neighbors(*CLUSTER_ANCHOR),))
    finally:
        dispose(rid)
    return 0


def diag(hp_target: int) -> int:
    """DECOMPOSITION PAR ETAGE d'un desaccord de CIBLE : pour chaque tuile candidate, sa position,
    la ZONE que le port calcule (`GetTargetAreaTiles`), le custom, et l'utilite d'action complete.

    C'est l'outil a sortir AVANT toute retouche : « le natif vise 52, le port 53 » ne dit pas si
    c'est la DIRECTION du triangle, l'ORDRE d'enumeration (tie-break keep-first) ou le terme
    positionnel qui differe -- et les trois se corrigent a des endroits opposes."""
    import engine_validate as EV
    import probe_27_3_live as L
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook.base import tile_utility
    from engine.playbook.tile_targets import dsl_context_for_tile_target
    from engine.entities.selectors.accessors import FixedTileIds
    from engine.runner.abilities.blacklegion import daemonic_ordnance_target_area_tiles
    from engine.ai import context as AICTX

    rid = build_ready(hp_target, "rs_302_3_d.json")
    try:
        caster, _cd, _ = _caster_state(rid)
        nat = native(rid, caster)
        sid = L.INV._session_id()
        rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, W.load(),
                          _scene.build_predictor(rpc, rid),
                          spawn_groups=spawn_groups("rs_302_3_d.json"))
        pb = PB.REGISTRY[DAEMONIC]
        print("MachineOfWarPosition(courant) = %s (team %s)"
              % (ctx.machine_of_war_position(), ctx.current_player_team))
        dctx = dsl_context_for_tile_target(ctx)
        pos_by_tid = {t: p for p, t in (ctx.tile_id_by_pos or {}).items()}
        targets = pb.eligible_targets(ctx, DAEMONIC)
        rows = []
        for i, t in enumerate(targets):
            u = pb.calculate_custom_utility(ctx, ctx.origin, t, DAEMONIC)
            zone = daemonic_ordnance_target_area_tiles(FixedTileIds([int(t)])).select(dctx)
            rows.append((i, t, pos_by_tid.get(t), u, [pos_by_tid.get(z) for z in zone]))
        print("runner=%d caster=u%s natif=%s" % (rid, caster, (nat,)))
        print("occupants = %s" % {v: p for v, (_i, p) in _units(rid).items()})
        print("\nordre  tile  pos      custom  zone (positions)")
        for i, t, p, u, zone in rows:
            if u > 0 or t in (nat[1],):
                print("  %-4d %-5s %-8s %-6s %s%s"
                      % (i, t, p, u, zone, "   <== NATIF" if t == nat[1] else ""))
        # Terme positionnel : `full = custom + tile_utility(T)` sur la MEILLEURE tuile d'action.
        best_by_tile = {}
        for T in (ctx.reach_nc or []):
            best_by_tile[T] = tile_utility(ctx, T)
        print("\ntile_utility par tuile d'action (les 6 premieres) = %s"
              % list(best_by_tile.items())[:6])
        top = sorted(rows, key=lambda r: -r[3])[:6]
        print("top custom = %s" % [(r[1], r[2], r[3]) for r in top])
    finally:
        dispose(rid)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decision", action="store_true")
    ap.add_argument("--flip", action="store_true")
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--stage", action="store_true")
    ap.add_argument("--hp-target", type=int, default=HP_FAVOURABLE)
    ap.add_argument("--hp-witness", type=int, default=HP_WITNESS)
    a = ap.parse_args()
    if a.decision:
        return decision(a.hp_target, a.hp_witness)
    if a.flip:
        return flip(a.hp_target)
    if a.diag:
        return diag(a.hp_target)
    if a.stage:
        return stage_only(a.hp_target)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
