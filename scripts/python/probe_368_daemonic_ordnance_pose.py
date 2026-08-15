"""probe #368 -- la POSE de `1148 DaemonicOrdnance` : le port allume-t-il les MEMES tuiles ?

LA QUESTION BINAIRE, ENONCEE AVANT LA METHODE
---------------------------------------------
"L'ensemble des tuiles que le NATIF embrase apres un cast de 1148 est-il EGAL a l'ensemble que
rend la face COMBAT du port (`DaemonicOrdnanceAbility.execute_behaviour` -> `burned_tiles`) ?"

Et il faut le mesurer sur une geometrie ou la zone NOMINALE (le triangle geometrique brut) et la
zone REELLE different -- sinon la mesure ne tranche rien.

CE QUE LE DECOMPILE DIT (et qu'aucune mesure n'a besoin de redecouvrir)
-----------------------------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$ExecuteBehaviour` etage [5] :

    AddEffect( 5 = Fire, AbilityStateReference, source = DSLSelectors@+0x30 (Owner),
               targets = GetTargetAreaTiles(), options ZERO )

`...DaemonicOrdnanceAbility$$GetTargetAreaTiles` :

    dir  = If( IsPositionMachineForCurrentPlayer(2), Direct(1), Direct(4) )
    zone = TilesOnSameElevation( Target@+0x60, TilesInTriangleShape(Target@+0x60, dir), maxDiff = 1 )

Les SEULS filtres de la chaine de POSE, lus etage par etage -- AUCUN ne teste la marchabilite :

| etage natif | filtre |
|---|---|
| `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape` | n'ajoute au HashSet que les `IdunBattle.Entities.StateExtensions$$GetTileAt` NON NULS ; `GetTileAt` rend null si `IdunBattle.Entities.Components.BoardComponent$$IsPositionInside` est faux OU si l'id de tuile du tableau `BoardComponent+0x18` vaut 0 |
| `IdunBattle.Entities.Selectors.TilesOnSameElevationSelector$$Select` | garde si `IdunBattle.Entities.TileExtensions$$GetElevationDifference(tile, ancre) <= maxDiff` -- et ce corps est `abs(TileComponent+0x18 - TileComponent+0x18)`, rien d'autre |
| `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` | saute l'entite cible si `IdunBattle.Entities.UnitExtensions$$HasFlag(entity, 6 = UnitFlag.Dead)` -- INERTE sur une TUILE (`HasFlag` rend false des que `EntityType` n'est ni `1 = Unit` ni `6 = Machine`) |
| `IdunBattle.Operations.AddEffectOperation$$Execute` | trois refus : `owner == null` ; `<effet>.EntityIsImmuneToEffect(owner)` (== le corps de `IdunBattle.Core.Services.BattleQuery$$IsUnitImmuneTo`, et `IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` = `HasTrait(entity, 0x19)`) ; `IsUnit(owner) && HasFlag(owner, 6)` |

=> **le filtre qui ampute le triangle est l'ELEVATION**, pas la marchabilite. La covariable
`walkable = False` relevee par #359-r4 n'est PAS le mecanisme : elle n'est meme pas lue.

CE QUE CE PROBE MESURE
----------------------
Par board, il DECOMPOSE PAR ETAGE au lieu de comparer un compte :

    E1 triangle geometrique brut   (`TilesInTriangleShape`, port)   -- avec l'elevation LIVE de chaque tuile
    E2 zone apres elevation        (`daemonic_ordnance_target_area_tiles`, port)
    E3 tuiles reellement embrasees (natif, `tileMeta` apres un cast REEL)
    E4 `burned_tiles` de la face COMBAT du port sur l'etat charge AVANT le cast

et il REFUSE de mesurer si l'ancre n'est pas DISCRIMINANTE en live (|E1| == |E2|) : un board ou les
deux coincident ne conclut rien. Meme refus si le cast est illegal ou si le montage rate.

Usage (depuis scripts/python, ASCII only) :
    python probe_368_daemonic_ordnance_pose.py --scan                 # inventaire OFFLINE, sans live
    python probe_368_daemonic_ordnance_pose.py --pose                 # les 2 couples (board, seed)
    python probe_368_daemonic_ordnance_pose.py --pose --only A        # un seul bras
    python probe_368_daemonic_ordnance_pose.py --pose --mutate elev   # VUE ROUGE (maxDiff neutralise)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.entities.selectors.geometry import _TRIANGLE_SHAPE_DIRECTIONS, neighbour_at

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"

DAEMONIC = 1148
FIRE = int(EffectType.Fire)                 # 5
MOW_CARRIER = "blackForgefiend"             # porteur REEL de 1148 (Machine of War)
GRAFT_ON = "deathTyphus"                    # porteur greffe (bras sans MoW)

# QUATRE BRAS = deux branches du `If` x DEUX REGIMES de tuile, et le second regime est celui qui
# TRANCHE le residu #359-r4 ("le natif n'allume pas une tuile NON MARCHABLE") :
#
#   dir=1 -- board MoW-capable : les 227 boards MoW-capables du depot declarent TOUS
#            `MachineOfWarPosition = (team1: 2, team2: 1)` (mesure `--scan`), donc `dir = 1` avec la
#            MoW du joueur courant deployee. Le porteur est la VRAIE MoW.
#   dir=4 -- board NON MoW-capable (`MachineOfWarPosition = 0` des deux cotes, 552 boards) : le
#            predicat est FAUX cote natif ET cote port (aucune MoW deployee -> proxy `None`). Le
#            porteur est une greffe (une MoW ne se deploie pas sur un tel board).
#
#   regime `elev`   -- ancre dont le triangle compte 3 tuiles et la zone 2 : c'est l'ELEVATION qui
#                      ampute. Sans lui, nominal == reel et la mesure ne tranche rien.
#   regime `unwalk` -- ancre dont la zone compte 3 tuiles DONT au moins une NON MARCHABLE. Si le
#                      natif l'allume, la marchabilite n'est PAS un filtre de la pose -- ce que le
#                      decompile dit deja, et que ce bras CONFRONTE.
ARMS = {
    "A": {"board": "MC1_67", "seed": "4242", "mow": True, "regime": "elev"},
    "B": {"board": "C1_15", "seed": "909", "mow": False, "regime": "elev"},
    "C": {"board": "C1_15", "seed": "909", "mow": False, "regime": "unwalk"},
    "D": {"board": "MC1_67", "seed": "4242", "mow": True, "regime": "unwalk"},
    "E": {"board": "C1_15", "seed": "909", "mow": False, "regime": "terrain:Block"},
}


# ------------------------------------------------------------------ etage 0 : inventaire OFFLINE

def scan(limit: int = 8) -> int:
    """Inventaire des boards qui PORTENT le regime discriminant (|triangle| = 3, |zone| = 2).

    Lu dans la BC (`Tiles[col].Tile[row].{TileId, Elevation}`) : c'est un cadrage, pas la mesure --
    l'elevation qui compte est celle du `TileComponent` LIVE, que `--pose` relit."""
    from rl_duel import _board_mow_ok
    from engine.services.machine_of_war_position import (machine_of_war_position_for_player,
                                                         spawn_groups_from_battle_config)
    bd = HERE.parents[1] / "data" / "boards"
    rows, pos_counts = [], {}
    for kind in ("global", "pvp", "syncPvp"):
        d = bd / kind
        for p in sorted(d.glob("*.json")) if d.exists() else []:
            dump = json.loads(p.read_text(encoding="utf-8"))
            bc = {"Board": dump["board"], "SpawnPointSetIndex": dump.get("spawnPointsSet", 0)}
            groups = spawn_groups_from_battle_config(bc)
            try:
                mp1 = int(machine_of_war_position_for_player(groups, 1))
                mp2 = int(machine_of_war_position_for_player(groups, 2))
            except Exception:
                continue
            key = (mp1, mp2, bool(_board_mow_ok(bc)))
            pos_counts[key] = pos_counts.get(key, 0) + 1
            n = len(_discriminating_anchors_bc(dump["board"], 1 if mp1 == 2 else 4))
            if n:
                rows.append((dump["id"], kind, 1 if mp1 == 2 else 4, n))
    print("=== MachineOfWarPosition (team1, team2, mow_ok) -> nb de boards ===")
    for k, v in sorted(pos_counts.items()):
        print("  %s -> %d" % (k, v))
    rows.sort(key=lambda r: -r[3])
    print("=== boards portant une ancre DISCRIMINANTE (|triangle|=3, |zone|=2) : %d ===" % len(rows))
    for r in rows[:limit]:
        print("  id=%-26s kind=%-8s dir=%d ancres=%d" % r)
    return 0


def _discriminating_anchors_bc(board_dump: dict, direction: int) -> list:
    tiles, w, h = board_dump["Tiles"], board_dump["Width"], board_dump["Height"]

    def cell(c, r):
        return tiles[c]["Tile"][r] if 0 <= c < w and 0 <= r < h else None

    dirs = _TRIANGLE_SHAPE_DIRECTIONS[int(direction)]
    out = []
    for c in range(w):
        for r in range(h):
            a = cell(c, r)
            if a is None or a.get("TileId") == "Block":
                continue
            nom = [(c, r)] + [tuple(neighbour_at(c, r, k)) for k in dirs]
            nom = [q for q in nom if cell(q[0], q[1]) is not None]
            zone = [q for q in nom if abs(cell(q[0], q[1])["Elevation"] - a["Elevation"]) <= 1]
            if len(nom) == 3 and len(zone) == 2:
                out.append(((c, r), nom, zone))
    return out


# ------------------------------------------------------------------------------ montage (live)

def _rpc_fn():
    import engine_validate as EV
    import probe_27_3_live as L
    sid = L.INV._session_id()
    return lambda m, b, t=60: EV._r(sid, m, b, t)


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)


def _board(rpc, rid) -> Board:
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise SystemExit("boardGraph indisponible sur le runner %d -- mesure REFUSEE" % rid)
    return Board(bg["tiles"], adjacency="evenq")


def _burning(rpc, rid) -> set:
    tm = rpc("tileMeta", {"runnerId": rid}, 90) or {}
    return {(t["col"], t["row"]) for t in (tm.get("tiles") or [])
            if any(e.get("effectType") == FIRE for e in (t.get("effects") or []))}


def _fire_par_tuile(rpc, rid) -> dict:
    """#368-r1 -- LE DISCRIMINANT. `tileMeta(includeInactive=True)` publie `active` par effet :
    une tuile qui porte un `Fire` **INACTIF** a bien recu la pose (le refus est alors une
    `ActiveCondition`, `RefreshEffectsOperation$$ShouldBeActive`) ; une tuile qui ne porte RIEN
    n'a jamais ete soumise (le refus est au selecteur, `StateExtensions$$GetTileAt`, et c'est le
    substrat `board.id_at` du port qu'il faudrait corriger, pas `1148`).

    Rend `{(col,row): [{"active": bool, "removed": bool, ...}]}` pour les seuls effets `Fire`,
    et `None` si le bundle injecte ne connait pas `includeInactive` (tri-etat : l'absence du
    drapeau `active` sur TOUS les effets publies signe un bundle anterieur -- on ne la rabat
    surtout pas sur « aucun effet inactif »)."""
    tm = rpc("tileMeta", {"runnerId": rid, "includeInactive": True}, 90) or {}
    tuiles = tm.get("tiles") or []
    vu_active = any("active" in e
                    for t in tuiles for e in (t.get("effects") or []))
    porte_des_effets = any(t.get("effects") for t in tuiles)
    if porte_des_effets and not vu_active:
        return None                     # bundle sans `includeInactive` -> PAS MESURE
    return {(t["col"], t["row"]): [e for e in (t.get("effects") or [])
                                   if e.get("effectType") == FIRE]
            for t in tuiles
            if any(e.get("effectType") == FIRE for e in (t.get("effects") or []))}


def _write_graft_seed_bc(out: Path) -> None:
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    seen = False
    for u in bc.get("Units") or []:
        if u.get("Id") == GRAFT_ON:
            u["ActiveAbilities"] = [DAEMONIC]
            seen = True
    if not seen:
        raise SystemExit("greffe impossible : %s absent de BC.Units" % GRAFT_ON)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")


def _build(arm: str, state: Path) -> int:
    """Build du bras `arm`. Deux montages, et le choix n'est PAS cosmetique : le predicat
    `IsPositionMachineForCurrentPlayer(2)` est resolu cote COMBAT par le slot d'une MoW DEPLOYEE
    (`engine/runner/abilities/behaviours/context.py`). Sur un board MoW-capable, il FAUT donc la MoW
    reelle -- une greffe sans MoW ferait rendre `dir = 4` au port et `dir = 1` au natif, et le
    desaccord n'accuserait que le harnais."""
    import subprocess
    cfg = ARMS[arm]
    args = ["build", "--seed", cfg["seed"], "--board", cfg["board"], "--rank", "17",
            "--state-file", str(state)]
    if cfg["mow"]:
        args += ["--p-mow", MOW_CARRIER,
                 "--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden"]
    else:
        seed_bc = LOGS / ("bc_368_%s.json" % arm)
        _write_graft_seed_bc(seed_bc)
        args += ["--seed-bc", str(seed_bc),
                 "--p-units", GRAFT_ON + ",deathPutrifier", "--a-units", "necroWarden,necroDestroyer"]
    r = subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                       capture_output=True, text=True)
    if not state.exists():
        raise SystemExit("build KO (%s) : %s" % (arm, (r.stderr or r.stdout or "")[-600:]))
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])


def _spawn_groups(state: Path):
    from engine.services.machine_of_war_position import spawn_groups_from_battle_config
    return spawn_groups_from_battle_config(
        json.loads(state.read_text(encoding="utf-8")).get("bc") or {})


def _direction(rpc, rid, state: Path) -> int:
    """`dir` REEL = `If(IsPositionMachineForCurrentPlayer(2), 1, 4)`, calcule sur les
    `SpawnPointGroups` de la BC que le runner EXECUTE.

    ⚠ « aucun RPC ne les expose » etait FAUX (corrige #302 tranche 5) : `boardGraph.mowPositions`
    publie depuis #311 le retour de `GetPositionMachineForPlayer(player)` INVOQUE. Ce calcul par la
    BC reste un mirror valide -- il concorde 6/6 avec le natif sur les deux regimes mesures."""
    from engine.ai.context import _current_player_team
    from engine.services.machine_of_war_position import machine_of_war_position_for_player
    team = _current_player_team(_dv(rpc, rid))
    if team is None:
        raise SystemExit("team courante indeterminee -- mesure REFUSEE")
    return 1 if int(machine_of_war_position_for_player(_spawn_groups(state), int(team))) == 2 else 4


def _caster(rpc, rid, arm: str):
    """`(casterId, kind)` du porteur de 1148, cooldown PURGE (`initialCooldownTurns = 1`)."""
    dec = _dv(rpc, rid)
    if ARMS[arm]["mow"]:
        m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == MOW_CARRIER), None)
        if m is None:
            raise SystemExit("MoW %s non deployee -- montage REFUSE" % MOW_CARRIER)
        return int(m["casterId"]), "mow"
    u = next((x for x in (dec.get("units") or []) if x.get("visualId") == GRAFT_ON), None)
    if u is None:
        raise SystemExit("porteur greffe %s absent -- montage REFUSE" % GRAFT_ON)
    return int(u["id"]), "unit"


def _legal_tile_targets(rpc, rid, caster) -> set:
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster,
                                "abilityType": DAEMONIC, "allAbilities": True}, 120) or {}
    out = set()
    for u in (at.get("units") or []):
        if u.get("unitId") != caster:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") not in (DAEMONIC, None) and a.get("abilityType") != DAEMONIC:
                continue
            for t in (a.get("targets") or []):
                tl = t.get("tile") or {}
                if t.get("kind") == "tile" and tl.get("col") is not None:
                    out.add((tl["col"], tl["row"]))
    return out


# ------------------------------------------------------------------------- etages, cote PORT

def _zone_port(board: Board, anchor: tuple, direction: int) -> dict:
    """E1/E2 par le MEME code que la face COMBAT (`daemonic_ordnance_target_area_tiles`), evalue sur
    un contexte DSL MINIMAL -- board + direction forcee. Le but n'est pas de re-implementer le
    selecteur mais de LIRE ses deux etages separement."""
    from engine.dsl.base import DslContext
    from engine.entities.selectors.accessors import FixedTileIds
    from engine.entities.selectors.geometry import TilesInTriangleShape, TilesOnSameElevation
    tid = board.id_at(anchor[0], anchor[1])
    if tid is None:
        raise SystemExit("ancre %s absente du boardGraph -- mesure REFUSEE" % (anchor,))
    ctx = DslContext(units=[], board=board,
                     current_player_machine_position=(2 if direction == 1 else 0))
    sel = FixedTileIds([int(tid)])
    tri = TilesInTriangleShape(sel, direction).select(ctx)
    from engine.runner.abilities.blacklegion import daemonic_ordnance_target_area_tiles
    zone = daemonic_ordnance_target_area_tiles(sel).select(ctx)
    return {"tile_id": int(tid),
            "triangle": [board.coord(t) for t in tri],
            "zone": [board.coord(t) for t in zone],
            "elev": {board.coord(t): board.elevation(t) for t in tri},
            "walkable": {board.coord(t): board.walkable(t) for t in tri},
            "terrain": {board.coord(t): board.tile_def_id(t) for t in tri},
            "is_wall": {board.coord(t): bool((board.by_id.get(t) or {}).get("isWall"))
                        for t in tri}}


def _load_state(rpc, rid, board: Board):
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    dec = _dv(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 90)
    st = load_state(dec, ob, snap, board=board, tiles=tm)
    s0 = rpc("dumpRng", {"runnerId": rid}, 40)
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
    return st


def _port_burn(state, caster: int, tile_id: int, board: Board) -> list:
    """E4 -- la face COMBAT du port : `DaemonicOrdnanceAbility.execute_behaviour` rend
    `burned_tiles` = les entites-tuiles sur lesquelles l'etage [5] a REELLEMENT pose `Fire`."""
    from engine.runner.abilities.blacklegion import DaemonicOrdnanceAbility
    out = DaemonicOrdnanceAbility().execute_behaviour(state, int(caster), int(tile_id))
    if out is None:
        raise SystemExit("execute_behaviour a rendu None (caster %s, tuile %s)" % (caster, tile_id))
    return sorted(board.coord(int(t)) for t in (out.get("burned_tiles") or [])
                  if int(t) in board.by_id)


def _port_burn_with_flag(state, caster: int, tile_id: int, board: Board) -> tuple:
    """E4bis (#368-r2) -- **LA POSE ET LE FLAG, SEPAREMENT**.

    `burned_tiles` repond a << ou l'etage [5] a-t-il POSE ? >>, ce qui n'est PAS la question que
    `E3` mesure cote natif : `tileMeta` SANS `includeInactive` ne rend que les effets **ACTIFS**.
    Comparer l'un a l'autre confond donc deux etages, et c'est exactement ce que ce probe avait
    conclu au bras D -- << ecart port \\ natif = [(0,8)] >> alors que le natif POSE aussi sur (0,8),
    en `active: False`. La mesure qui tranche lit `EffectComponent.IsActive @+0x5c` (le champ
    `BaseEffect.active`) sur l'etat du port, apres la pose.

    Rend `(poses, actifs)` : les deux ensembles de coordonnees."""
    poses = _port_burn(state, caster, tile_id, board)
    actifs = []
    for q in poses:
        tid = board.id_at(q[0], q[1])
        if tid is None:
            continue
        for e in (state.effects.by_unit.get(int(tid), []) if state.effects else []):
            if int(getattr(e, "effect_type", 0) or 0) == FIRE and not e.consumed:
                if bool(getattr(e, "active", True)):
                    actifs.append(q)
                break
    return poses, sorted(set(actifs))


# ---------------------------------------------------------------------------------- la mesure

def pose(arm: str, mutate: str = "") -> dict:
    import subprocess
    rpc = _rpc_fn()
    state = LOGS / ("rs_368_%s.json" % arm)
    LOGS.mkdir(parents=True, exist_ok=True)
    rid = _build(arm, state)
    try:
        board = _board(rpc, rid)
        direction = _direction(rpc, rid, state)
        caster, kind = _caster(rpc, rid, arm)
        # Purge du `initialCooldownTurns = 1` : tant qu'il court, le natif ne PEUT pas caster et la
        # mesure ne dirait rien de la pose. Les tours se terminent A VIDE.
        regime = ARMS[arm]["regime"]
        for _ in range(4):
            anchor = _pick_anchor(rpc, rid, board, direction, caster, regime)
            if anchor is not None:
                break
            subprocess.run([sys.executable, "rl_duel.py", "act", "endturn",
                            "--state-file", str(state), "--runner", str(rid)],
                           cwd=str(HERE), capture_output=True, text=True)
        if anchor is None:
            raise SystemExit("aucune ancre du regime %r LEGALE sur %s (dir=%d) -- "
                             "mesure REFUSEE (board sans le regime, pas resultat degrade)"
                             % (regime, ARMS[arm]["board"], direction))
        stages = _zone_port(board, anchor, direction)
        before = _burning(rpc, rid)
        # Les DEUX ports sont calcules sur le MEME etat, AVANT le cast natif : la vue verte et la
        # VUE ROUGE partagent donc exactement le meme montage (un seul build), et un ecart entre
        # elles ne peut pas venir d'un etat different.
        port, port_actifs = _port_burn_with_flag(_load_state(rpc, rid, board), caster,
                                                 stages["tile_id"], board)
        port_wide = _mutated_port_burn(_load_state(rpc, rid, board), caster, stages["tile_id"],
                                       board, "elev")
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "abilityType": DAEMONIC,
            "to": {"col": anchor[0], "row": anchor[1]}}}, 120) or {}
        act = (r.get("actions") or [{}])[0]
        if act.get("error"):
            raise SystemExit("cast natif refuse (%s) -- mesure REFUSEE" % act.get("error"))
        native = sorted(_burning(rpc, rid) - before)
        # EVENTS du cast : ils disent si l'effet a ete SOUMIS puis retire, ou JAMAIS soumis. Sans
        # eux, "la tuile ne brule pas" ne distingue pas un selecteur qui l'exclut d'une operation
        # qui la refuse -- exactement la decomposition par etage qu'un compte ne donne pas.
        ev = _effect_events(act)
        unwalk = sorted(q for q in stages["zone"] if not stages["walkable"][q])
        # #368-r1 -- APRES le cast, relire avec `includeInactive` : c'est la seule mesure qui
        # separe « jamais soumis » de « pose puis desactive » sur les tuiles de l'ecart.
        fire_inactif = _fire_par_tuile(rpc, rid)
        gap = sorted(set(map(tuple, port)) - set(map(tuple, native)))
        if fire_inactif is None:
            verdict_368r1 = "NON MESURE -- le bundle injecte ignore `includeInactive`"
        elif not gap:
            verdict_368r1 = "SANS OBJET -- aucun ecart port/natif sur ce bras"
        else:
            portees = [q for q in gap if fire_inactif.get(q)]
            verdict_368r1 = ("POSE-PUIS-DESACTIVE (ActiveCondition) : %s" % portees
                             if portees else
                             "JAMAIS SOUMIS (selecteur / GetTileAt) : aucune des tuiles de "
                             "l'ecart %s ne porte de `Fire`, meme INACTIF" % gap)
        return {"arm": arm, "rid": rid, "board": ARMS[arm]["board"], "dir": direction,
                "fire_inactif": (None if fire_inactif is None
                                 else {str(k): v for k, v in fire_inactif.items()}),
                "verdict_368r1": verdict_368r1,
                "regime": regime, "caster": caster, "caster_kind": kind, "anchor": anchor,
                "stages": stages, "native": native, "port": sorted(port),
                # #368-r2 -- l'ensemble COMPARABLE a `native` : les tuiles ou le port a pose un
                # `Fire` **ACTIF**. `native` vient de `tileMeta` sans `includeInactive`, donc
                # actif-only ; `port` (les poses) ne l'est pas.
                "port_actifs": sorted(port_actifs),
                "gap_actifs": sorted(set(map(tuple, port_actifs)) - set(map(tuple, native))),
                "agree_actifs": sorted(port_actifs) == native,
                "port_wide": sorted(port_wide), "events": ev[:12],
                # `zone_port \ natif` -- l'ecart RESIDUEL, et l'ensemble des tuiles NON MARCHABLES
                # de la zone, pour que la garde teste l'EGALITE des deux au lieu d'un compte.
                "gap": sorted(set(map(tuple, port)) - set(map(tuple, native))),
                "unwalkable_in_zone": unwalk,
                "agree": native == sorted(port), "mutate": mutate}
    finally:
        _dispose(rpc, rid)


def _mutated_port_burn(state, caster, tile_id, board, mutate: str):
    """VUE ROUGE. `--mutate elev` neutralise le `maxDiff = 1` de `TilesOnSameElevationSelector`
    (le SEUL filtre qui ampute le triangle) : le port doit alors allumer une tuile de PLUS que le
    natif, et la comparaison DOIT rougir. Restauration par sauvegarde, jamais par `del`."""
    from engine.entities.selectors.geometry import TilesOnSameElevation
    if mutate != "elev":
        return _port_burn(state, caster, tile_id, board)
    saved = TilesOnSameElevation.select

    def wide(self, ctx):
        d, self.max_diff = self.max_diff, 99
        try:
            return saved(self, ctx)
        finally:
            self.max_diff = d
    TilesOnSameElevation.select = wide
    try:
        return _port_burn(state, caster, tile_id, board)
    finally:
        TilesOnSameElevation.select = saved


def _pick_anchor(rpc, rid, board: Board, direction: int, caster: int, regime: str):
    """Ancre qui PORTE le regime demande ET qui est cible LEGALE de 1148. `None` si aucune --
    l'appelant REFUSE alors de mesurer (jamais un montage degrade)."""
    legal = _legal_tile_targets(rpc, rid, caster)
    if not legal:
        return None
    occupied = {(u["pos"]["col"], u["pos"]["row"])
                for u in (_dv(rpc, rid).get("units") or []) if u.get("pos")}
    for pos in sorted(legal):
        if pos in occupied:
            continue
        s = _zone_port(board, pos, direction)
        if regime == "elev" and len(s["triangle"]) == 3 and len(s["zone"]) == 2:
            return pos
        if regime == "unwalk" and len(s["zone"]) == 3 \
                and any(not s["walkable"][q] for q in s["zone"]):
            return pos
        # Regimes de TERRAIN : ils separent "non marchable" de "ce terrain-la". Deux tuiles
        # non marchables de terrains DIFFERENTS (Water vs Block) qui se comportent pareil disent
        # que la covariable est la marchabilite ; un ecart dit que c'est le terrain.
        if regime.startswith("terrain:") and len(s["zone"]) == 3 \
                and any(s["terrain"].get(q) == regime.split(":", 1)[1] for q in s["zone"]):
            return pos
    return None


def _effect_events(act: dict) -> list:
    """Events `ReceiveEffect` de la cascade StreamDispatcher du cast (`ActionResult.events`).

    C'est L'ETAGE qui separe "l'effet n'a jamais ete soumis" de "il a ete pose puis desactive" :
    `tileMeta` FILTRE les effets inactifs (`readEffectsByTile` : `!info.active && !includeInactive
    -> continue`) et n'expose pas le drapeau, donc son silence est AMBIGU. La cascade, elle, est
    emise a la POSE."""
    out = []
    for e in (act.get("events") or []):
        nm = str(e.get("name") or e.get("kind") or "")
        if "Effect" in nm:
            out.append({"name": nm, "tags": e.get("tags"), "target": e.get("targetId"),
                        "entity": e.get("entityId")})
    return out


def _dispose(rpc, rid) -> None:
    try:
        rpc("disposeRunner", {"runnerId": int(rid)}, 60)
    except Exception:
        pass


def _print(r: dict) -> None:
    s = r["stages"]
    print("\n=== POSE bras %s regime=%s (runner %d, board %s, dir=%d, caster u%d %s) ==="
          % (r["arm"], r["regime"], r["rid"], r["board"], r["dir"], r["caster"],
             r["caster_kind"]))
    print("  ancre du cast          = %s (tuile %d)" % (r["anchor"], s["tile_id"]))
    print("  E1 triangle brut       = %s" % (sorted(s["triangle"]),))
    print("     elevation LIVE      = %s" % (s["elev"],))
    print("     walkable LIVE       = %s" % (s["walkable"],))
    print("     terrain LIVE        = %s" % (s["terrain"],))
    print("     isWall LIVE         = %s" % (s["is_wall"],))
    print("  E2 zone (port)         = %s" % (sorted(s["zone"]),))
    print("  E3 embrasees (NATIF)   = %s" % (r["native"],))
    print("  E4 burned_tiles (PORT) = %s" % (r["port"],))
    print("  E4bis PORT, Fire ACTIF = %s   <- l'ensemble COMPARABLE a E3 (#368-r2)" % (r["port_actifs"],))
    print("  E4' PORT, maxDiff NEUTRALISE (vue ROUGE) = %s" % (r["port_wide"],))
    for e in (r.get("events") or []):
        print("     event: %s" % (e,))
    print("  ecart port \\ natif     = %s   (non marchables de la zone = %s)"
          % (r["gap"], r["unwalkable_in_zone"]))
    print("  ecart ACTIFS port \\ natif = %s" % (r["gap_actifs"],))
    print("  ACCORD natif/port      = %s%s   |   ACCORD sur les ACTIFS = %s"
          % (r["agree"], ("   [mutation %s]" % r["mutate"]) if r["mutate"] else "",
             r["agree_actifs"]))
    print("  #368-r1 (includeInactive) = %s" % r.get("verdict_368r1"))
    if r.get("fire_inactif") is not None:
        for q, effs in sorted((r.get("fire_inactif") or {}).items()):
            print("     Fire sur %s : %s" % (q, effs))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--pose", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--mutate", default="", choices=["", "elev"])
    a = ap.parse_args()
    if a.scan:
        return scan()
    if not a.pose:
        ap.print_help()
        return 2
    arms = [a.only] if a.only else sorted(ARMS)
    ok = True
    ok_actifs = True
    for arm in arms:
        r = pose(arm, a.mutate)
        _print(r)
        ok = ok and r["agree"]
        ok_actifs = ok_actifs and r["agree_actifs"]
    # DEUX verdicts, et il FAUT les deux. Le premier compare les POSES du port aux tuiles que
    # `tileMeta` rend (donc ACTIVES) : il est FAUX par construction des qu'une tuile est posee puis
    # desactivee -- c'est l'observation de #368-r1, pas un desaccord. Le second (#368-r2) compare
    # ce qui est COMPARABLE : effets ACTIFS des deux cotes.
    print("\n=== VERDICT === accord POSES(port) vs ACTIFS(natif) = %s "
          "[FAUX attendu des qu'une tuile est posee-puis-desactivee]" % ok)
    print("=== VERDICT === accord ACTIFS/ACTIFS (#368-r2) = %s" % ok_actifs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
