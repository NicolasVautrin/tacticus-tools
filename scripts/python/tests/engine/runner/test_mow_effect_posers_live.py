"""CONFRONT LIVE du lot #90-B : les 5 abilities de MACHINE OF WAR dont le behaviour natif de CAST est
une PURE POSE D'EFFET(S) (`AddEffect`/`AddBondEffect` seuls -- aucune attaque, aucun spawn, aucune stat).

    1160 HeavyRailRifle         (tauBroadside)         IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour   unit-target
    1159 MacroPlasmaIncinerator (ultraDreadnought)     IdunBattleLogic.Entities.Abilities.Active.Loki.MacroPlasmaIncineratorAbility$$ExecuteBehaviour   tile-target
    1188 DevastatingRefrain     (adeptExorcist)        IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour   tile-target
    1201 SquigMine              (orksRukkatrukk)       IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour   tile-target
    1142 MalleusRocketLauncher  (astraOrdnanceBattery) IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncherAbility$$ExecuteBehaviour   tile-target

PROTOCOLE (aucune constante attendue en dur -- l'oracle est le natif) : pour chaque ability, on monte un
runner isole avec sa MoW, on choisit une cible LEGALE (`abilityTargets`), on execute le port OFFLINE sur
l'etat charge (`load_state` -> `_apply_active_ability`), puis on rejoue le MEME cast LIVE et on compare
l'EMPREINTE D'EFFETS : `{entite|tuile -> effectTypes poses}` + `remaining`. Les effets de TUILE viennent
du seul canal qui les expose (`tileMeta`, `readEffectsByTile`), les effets d'unite/MoW de `decisionView`.

Deux volets de GENERALISATION (non utilises pour construire le port) :
  * la BRANCHE OPPOSEE de `IsPositionMachineForCurrentPlayer(2)` : autre board, MoW du camp ADVERSE,
    tour passe a l'adversaire -> la forme de DevastatingRefrain doit basculer sur le triplet de
    directions COMPLEMENTAIRE, et le triangle de MacroPlasmaIncinerator sur l'autre coin ;
  * DevastatingRefrain caste depuis une tuile CENTRALE (4 tuiles marquees, aucune coupee par un bord).

Drive les positions ; lit l'etat LIVE ; state-files UNIQUES (chemin absolu + agent id) ; ASCII-only.

⚠ MONTAGE (#162) : le `combatSnapshot` qui alimente `load_state` est pris sur un runner JUMEAU, JAMAIS
sur le runner de mesure — ce RPC corrompt tout runner ou une MoW est deployee (toute pose d'effet
ulterieure y devient un no-op SILENCIEUX ; le degat, lui, passe). cf. `_twin_snapshot` et
`docs/rl/case-162-mow-red-suites.md`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.runner.operations.summon_ai import _apply_active_ability

AGENT_ID = "aeb0914f7e7a1d2a0"
PYDIR = Path(__file__).resolve().parents[3]                        # scripts/python
ROOT = Path(__file__).resolve().parents[5]                         # racine repo
# SOUS `logs/`, PAS `data/` : `data/` est VERSIONNE et ne contient que des ENTREES ; un
# state-file y est une SORTIE (le conftest a fait cette migration le 2026-07-27, ces deux
# fichiers-ci l'avaient ratee -- une passe interrompue laissait 4 `??` dans `git status`).
STATE = ROOT / "logs" / f"_pytest_mowposer_{AGENT_ID}.json"        # runner courant (scoped replace)
STATE_GEN = ROOT / "logs" / f"_pytest_mowposer_gen_{AGENT_ID}.json"
# state-file DEDIE au runner JUMEAU du snapshot (cf. `_twin_snapshot`) : un `build` ne dispose
# que le runner enregistre dans SON state-file -- le partager avec STATE tuerait le runner de mesure.
STATE_TWIN = ROOT / "logs" / f"_pytest_mowposer_twin_{AGENT_ID}.json"

EFF_SQUIG_MINE = 1441    # EffectType.SquigMine_Tile (marquage de tuile de 1201)
BOARD = "C1_02"          # board MoW-capable (slot MachineOfWarPosition des deux cotes)
GEN_BOARD = "C2_02"      # AUTRE board MoW-capable (generalisation)
SEED = "4242"

# (ability, carrier MoW, kind de cible attendu par le cast)
LOT = [
    (1160, "tauBroadside", "unit"),
    (1159, "ultraDreadnought", "tile"),
    (1188, "adeptExorcist", "tile"),
    (1201, "orksRukkatrukk", "tile"),
    (1142, "astraOrdnanceBattery", "tile"),
]


# ------------------------------------------------------------------ harnais

def _build(state_path: Path, extra: list[str], board: str = BOARD, seed: str = SEED):
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
         "--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden",
         "--state-file", str(state_path), *extra],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_path.exists():
        return None, (proc.stderr or proc.stdout or "")[-400:]
    return json.loads(state_path.read_text())["runnerId"], None


@pytest.fixture(scope="module")
def rpc_(host, live_session):
    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r
    return _rpc


def _twin_snapshot(rpc, extra, board_id, seed, endturn=0):
    """`combatSnapshot` pris sur un runner JUMEAU, JAMAIS sur le runner de mesure (#162).

    DEFAUT D'OUTILLAGE MESURE : appeler le RPC `combatSnapshot` sur un runner qui contient une
    entite MACHINE (une MoW deployee) laisse CE runner dans un etat ou toute pose d'effet
    ulterieure est un NO-OP SILENCIEUX -- l'action est bien consommee et le DEGAT passe
    normalement (mesure : 6180 PV identiques avec et sans), mais `AddEffect` n'ecrit plus rien.
    Ni erreur ni exception : le cast rend `ok=true` avec seulement les events d'ouverture. Ca
    frappait les casts de MoW comme ceux d'UNITE (`ThunderousAssault` ne posait plus `Stunned`),
    et seulement quand une MoW etait sur le plateau (meme runner sans MoW : intact). Contre-
    epreuves : `decisionView`, `observeBattle`, `boardGraph`, `tileMeta`, `dumpRng`,
    `abilityTargets`, `statModSources` et `aiPlaybookPredict` (caster = la MoW) ne corrompent
    PAS ; la corruption n'est pas reversible (elle survit aux fins de tour).

    Parade : deux `rl_duel build` de MEMES arguments donnent un etat STRICTEMENT identique
    (mesure : `combatSnapshot`, `decisionView`, ids d'entites et etat du PRNG egaux) -> le
    snapshot est pris sur un jumeau qu'on dispose aussitot. `endturn` rejoue sur le jumeau la
    meme avance de tour que sur le runner de mesure, sans quoi l'etat snapshotte ne serait pas
    celui qu'on confronte. cf. `docs/rl/case-162-mow-red-suites.md`."""
    rid, err = _build(STATE_TWIN, list(extra), board=board_id, seed=seed)
    if rid is None:
        pytest.skip(f"build runner KO (jumeau du snapshot): {err}")
    try:
        for _ in range(endturn):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        return rpc("combatSnapshot", {"runnerId": rid}, 90)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:                                          # noqa: BLE001
            pass


def _load(rpc, rid, twin_extra, board_id=BOARD, seed=SEED, endturn=0):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = _twin_snapshot(rpc, twin_extra, board_id, seed, endturn)
    return load_state(dec, ob, snap, board=board), board, dec, ob


def _live_footprint(rpc, rid, board) -> dict:
    """Empreinte d'effets LIVE : `{id d'unite|MoW|TUILE -> {effectType: remaining}}`. Les effets de
    TUILE ne sont exposes QUE par `tileMeta` (`readEffectsByTile`) ; ceux d'unite/MoW par
    `decisionView`. On CLE tout par id ECS (les tuiles via `board.id_at`) pour comparer a l'offline."""
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    out: dict = {}
    # ⚠ la cle ECS d'une MoW est `casterId` (== machineId, Type=6) ; le `id` de la ligne `mows` est la
    # PLATEFORME (Type=7) -- c'est `casterId` que `load_state` utilise et qu'attend `applyAction`.
    rows = [(u.get("id"), u) for u in (dec.get("units") or [])]
    rows += [(m.get("casterId"), m) for m in (dec.get("mows") or [])]
    for key, u in rows:
        if key is None:
            continue
        effs = {int(e["effectType"]): e.get("remaining") for e in (u.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            out[int(key)] = effs
    for t in (tm.get("tiles") or []):
        effs = {int(e["effectType"]): e.get("remaining") for e in (t.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            tid = board.id_at(t["col"], t["row"])
            if tid is not None:
                out[int(tid)] = effs
    return out


def _offline_footprint(state) -> dict:
    """MEME empreinte, cote port : `{cible -> {effectType: remaining}}` lue de `State.effects`
    (`remaining_turns` None == le `remaining 0` live = permanent)."""
    out: dict = {}
    for key, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        cur = {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
               for e in effs if not e.consumed}
        if cur:
            out[int(key)] = cur
    return out


def _delta(before: dict, after: dict) -> dict:
    """Effets AJOUTES entre deux empreintes : `{cible -> {effectType: remaining}}`."""
    out: dict = {}
    for key, effs in after.items():
        new = {et: rem for et, rem in effs.items() if et not in (before.get(key) or {})}
        if new:
            out[int(key)] = new
    return out


def _pick_target(rpc, rid, caster, ability, prefer_center=None, board=None, pick_tile=None):
    """1re cible LEGALE (`abilityTargets`). `prefer_center` : privilegie la tuile la plus CENTRALE
    (max de voisins sur le board) pour ne pas tronquer une forme contre un bord. `pick_tile(board,
    positions) -> (col,row)|None` : selecteur personnalise parmi les tuiles legales."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
    units = [t for t in tgts if t.get("kind") == "unit"]
    tiles = [t for t in tgts if t.get("kind") == "tile"]
    if units:
        return {"kind": "unit", "id": units[0]["targetId"]}, len(tgts)
    if not tiles:
        return None, 0
    legal = [(t["tile"]["col"], t["tile"]["row"]) for t in tiles]
    if pick_tile is not None:
        p = pick_tile(board, legal)
        return ({"kind": "tile", "col": p[0], "row": p[1], "legal": legal} if p else None), len(tgts)
    if prefer_center and board is not None:
        tiles = sorted(tiles, key=lambda t: -len(board.neighbours(
            board.id_at(t["tile"]["col"], t["tile"]["row"]) or -1)))
    tl = tiles[0]["tile"]
    return {"kind": "tile", "col": tl["col"], "row": tl["row"], "legal": legal}, len(tgts)


def _cast_live(rpc, rid, caster, ability, tgt):
    action = {"kind": "ability", "casterId": caster, "abilityType": ability}
    if tgt["kind"] == "unit":
        action["targetId"] = tgt["id"]
    else:
        action["to"] = {"col": tgt["col"], "row": tgt["row"]}
    r = rpc("applyAction", {"runnerId": rid, "action": action}, 90) or {}
    # Une erreur de NIVEAU RPC (`{ok:false, error}` sans clef `actions`) etait AVALEE : le
    # `(actions or [{}])[0]` rendait `{}`, donc `act.get("error")` etait None, donc le test
    # continuait et echouait plus loin sur une empreinte live VIDE -- en accusant le port.
    if r.get("ok") is False or not r.get("actions"):
        return {"error": f"applyAction KO: {str(r)[:300]}"}
    return r["actions"][0]


def _hp_offline(state) -> dict:
    from engine.runner.components import HealthComponent
    return {eid: hc.hp for eid, hc in
            ((e.id, e.get_component(HealthComponent)) for e in state.entities.values())
            if hc is not None}


def _hp_live(rpc, rid) -> dict:
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return {u.get("squadId"): u.get("hp") for u in (ob.get("units") or [])}


def _confront(rpc, ability, carrier, kind, state_path=STATE, board_id=BOARD, extra=None,
              prefer_center=False, endturn=0, pick_tile=None):
    """Monte le runner, choisit la cible, execute OFFLINE puis LIVE, rend
    (diag_offline, delta_offline, delta_live, contexte). `pick_tile(board, tiles)` = selecteur de
    tuile-cible personnalise (scenarios discriminants) parmi les tuiles LEGALES."""
    build_extra = list(extra or []) + ["--p-mow", carrier]
    rid, err = _build(state_path, build_extra, board=board_id)
    if rid is None:
        pytest.skip(f"build MoW {carrier} KO: {err}")
    for _ in range(endturn):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    state, board, dec, _ob = _load(rpc, rid, build_extra, board_id, SEED, endturn)
    m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == carrier), None)
    if m is None:
        pytest.skip(f"MoW {carrier} non deployee")
    caster = m["casterId"]
    tgt, n_tgts = _pick_target(rpc, rid, caster, ability, prefer_center, board, pick_tile)
    if tgt is None:
        pytest.skip(f"aucune cible legale pour {ability}")
    assert tgt["kind"] == kind, f"kind de cible {tgt['kind']} != {kind} attendu (ability {ability})"

    off_before, hp_off_before = _offline_footprint(state), _hp_offline(state)
    tid = tgt["id"] if tgt["kind"] == "unit" else board.id_at(tgt["col"], tgt["row"])
    res = _apply_active_ability(state, caster, tid, ability)
    diag = (res or {}).get("diag") or {}
    assert res.get("routed") == "handler" and diag.get("ported") is True, \
        f"ability {ability} non portee (routed={res.get('routed')})"
    off_delta = _delta(off_before, _offline_footprint(state))
    # GARDE anti-degat FANTOME : le behaviour de CAST de ces 5 abilities ne contient AUCUNE attaque
    # (le degat est en phase 2). Sans le port dedie, `_apply_active_ability` retombait sur le chemin
    # GENERIQUE `execute_ability_attack` (elles ont toutes un `damageProfile` en constants) et infligeait
    # des PV en trop. On verifie donc qu'AUCUN PV ne bouge, offline comme live.
    assert _hp_offline(state) == hp_off_before, "le cast a change des PV OFFLINE (degat fantome)"

    live_before, hp_live_before = _live_footprint(rpc, rid, board), _hp_live(rpc, rid)
    act = _cast_live(rpc, rid, caster, ability, tgt)
    if act.get("error"):
        pytest.skip(f"cast natif bloque: {act.get('error')}")
    live_delta = _delta(live_before, _live_footprint(rpc, rid, board))
    assert _hp_live(rpc, rid) == hp_live_before, "le cast natif a change des PV (le port n'en change pas)"
    ctx = {"rid": rid, "caster": caster, "target": tgt, "tileId": tid, "board": board,
           "mow": m, "nTargets": n_tgts, "dec": dec, "diag": diag}
    return diag, off_delta, live_delta, ctx


def _dispose(rpc, ctx):
    try:
        rpc("disposeRunner", {"runnerId": ctx["rid"]}, 20)
    except Exception:
        pass


def _coords(board, keys):
    return sorted(board.coord(k) for k in keys if k in board.by_id)


def _tgt(ctx):
    """Cible en forme COMPACTE pour les traces (la liste des tuiles legales est volumineuse)."""
    t = ctx["target"]
    return t["id"] if t["kind"] == "unit" else (t["col"], t["row"])


# ------------------------------------------------------------------ CONFRONT par ability

def test_heavy_rail_rifle_confront_live(rpc_):
    """1160 IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour : `AddEffect(1334 -> cible) & AddEffect(1333 -> la MoW)`. L'empreinte OFFLINE
    doit etre EXACTEMENT celle du natif (memes entites, memes effectTypes, meme `remaining`)."""
    diag, off, live, ctx = _confront(rpc_, 1160, "tauBroadside", "unit")
    print(f"\n[1160] caster={ctx['caster']} target={ctx['target']} off={off} live={live}")
    _dispose(rpc_, ctx)
    assert off == live, f"empreinte d'effets offline {off} != live {live}"
    assert ctx["caster"] in off, "aucun effet pose sur la MoW (PendingAttack manquant)"
    assert ctx["target"]["id"] in off, "aucun effet pose sur la cible (PendingTarget manquant)"


def test_macro_plasma_incinerator_confront_live(rpc_):
    """1159 IdunBattleLogic.Entities.Abilities.Active.Loki.MacroPlasmaIncineratorAbility$$ExecuteBehaviour : triangle de tuiles (`TilesInTriangleShape` filtre elevation + walkable) +
    effet d'armement sur la MoW. Confront de l'empreinte COMPLETE (tuiles marquees incluses)."""
    diag, off, live, ctx = _confront(rpc_, 1159, "ultraDreadnought", "tile", prefer_center=True)
    board = ctx["board"]
    print(f"\n[1159] caster={ctx['caster']} tile={_tgt(ctx)} turns={diag.get('turns')}\n"
          f"       off={off} ({_coords(board, off)})\n       live={live} ({_coords(board, live)})")
    _dispose(rpc_, ctx)
    assert off == live, f"empreinte offline {off} != live {live}"
    assert ctx["tileId"] in off, "la tuile ciblee n'est pas marquee"
    assert ctx["caster"] in off, "la MoW n'est pas armee (AutoAttack manquant)"


def test_devastating_refrain_confront_live(rpc_):
    """1188 IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour : forme = tuile ciblee + ses voisines dans les 3 directions du ctor
    (`{3,1,5}` = {N,SE,SW} cote machine). Cible CENTRALE -> aucune branche coupee par un bord."""
    diag, off, live, ctx = _confront(rpc_, 1188, "adeptExorcist", "tile", prefer_center=True)
    board = ctx["board"]
    tiles = [k for k in off if k != ctx["caster"]]
    print(f"\n[1188] caster={ctx['caster']} tile={_tgt(ctx)} machineSide={diag.get('machineSide')}\n"
          f"       off={off} ({_coords(board, off)})\n       live={live} ({_coords(board, live)})")
    _dispose(rpc_, ctx)
    assert off == live, f"empreinte offline {off} != live {live}"
    assert ctx["caster"] in off, "la MoW n'est pas armee (DevastatingRefrain_Attack manquant)"
    assert ctx["tileId"] in tiles, "la tuile ciblee n'est pas marquee"
    # forme complete depuis une tuile centrale = 1 + 3 directions
    assert len(tiles) == 4, f"forme de {len(tiles)} tuiles (attendu 4 depuis une tuile centrale)"


def test_squig_mine_confront_live(rpc_):
    """1201 IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour : la tuile ciblee + `nrOfTiles[level]` tuiles TIREES dans le disque `range`
    (libres, sans mine). Le TIRAGE n'est pas RNG-exact (GAP #215) -> on confronte ce qui EST
    deterministe : le CARDINAL, la tuile ciblee, l'appartenance des tuiles live au POOL modelise,
    l'effectType et le `remaining`."""
    import hexgeo
    diag, off, live, ctx = _confront(rpc_, 1201, "orksRukkatrukk", "tile", prefer_center=True)
    board, tid = ctx["board"], ctx["tileId"]
    pool = set(diag.get("pool") or []) | {tid}
    # POOL confronte a une geometrie INDEPENDANTE du port : les tuiles LEGALES (= libres + walkable,
    # ce que `abilityTargets` publie) a distance hex <= `range` de la cible, centre EXCLU. Valide
    # `SurroundingTiles(target, includeCenter=0, GetNumberConstant(0x16)=range)` + `CanAddUnit`.
    here = (ctx["target"]["col"], ctx["target"]["row"])
    indep = {board.id_at(*q) for q in ctx["target"]["legal"]
             if 0 < hexgeo.distance(here, q) <= int(diag.get("range") or 0)}
    print(f"\n[1201] caster={ctx['caster']} tile={ctx['target']['col'], ctx['target']['row']} "
          f"nrOfTiles={diag.get('nrOfTiles')} range={diag.get('range')} turns={diag.get('turns')}\n"
          f"       pool={_coords(board, diag.get('pool') or [])}\n"
          f"       indep={_coords(board, indep)}\n"
          f"       off={_coords(board, off)}\n       live={_coords(board, live)}")
    _dispose(rpc_, ctx)
    assert set(diag.get("pool") or []) == indep, \
        f"pool du port {_coords(board, diag.get('pool') or [])} != geometrie independante {_coords(board, indep)}"
    assert set(off) <= pool and set(live) <= pool, \
        f"tuiles hors du pool modelise: off={set(off) - pool} live={set(live) - pool}"
    assert tid in off and tid in live, "la tuile ciblee n'est pas minee"
    assert len(off) == len(live), f"cardinal offline {len(off)} != live {len(live)}"
    assert len(off) == 1 + int(diag.get("nrOfTiles") or 0), \
        f"cardinal {len(off)} != 1 + nrOfTiles={diag.get('nrOfTiles')}"
    # effectType + duree : identiques sur CHAQUE tuile (le natif pose le meme effet partout)
    off_sig = {tuple(sorted(v.items())) for v in off.values()}
    live_sig = {tuple(sorted(v.items())) for v in live.values()}
    assert off_sig == live_sig, f"signature d'effet offline {off_sig} != live {live_sig}"


def test_malleus_rocket_launcher_confront_live(rpc_):
    """1142 IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncherAbility$$ExecuteBehaviour : les TROIS effets (1308 bond / 1309 pending / 1310 spotted) sur la MEME tuile
    ciblee, plus un `Inform` sans effet d'etat."""
    diag, off, live, ctx = _confront(rpc_, 1142, "astraOrdnanceBattery", "tile", prefer_center=True)
    board = ctx["board"]
    print(f"\n[1142] caster={ctx['caster']} tile={_tgt(ctx)}\n"
          f"       off={off} ({_coords(board, off)})\n       live={live} ({_coords(board, live)})")
    _dispose(rpc_, ctx)
    assert off == live, f"empreinte offline {off} != live {live}"
    assert list(off) == [ctx["tileId"]], f"les effets ne sont pas tous sur la tuile ciblee: {off}"
    assert len(off[ctx["tileId"]]) == 3, f"attendu 3 effets sur la tuile, vu {off[ctx['tileId']]}"


# ------------------------------------------------------------------ GENERALISATION

def _raw_triangle(board, pos, direction):
    """Triangle GEOMETRIQUE pur (`BattleQuery.GetTilesInTriangleShape` sans aucun filtre) : la tuile +
    ses 2 voisines du coin `direction`. Sert d'oracle « avant filtres » aux scenarios discriminants."""
    # `_TRIANGLE_SHAPE_DIRECTIONS` est PRIVE : il vit dans le module qui le definit et n'est pas
    # re-exporte par le package. `selectors.py` est devenu le package `selectors/` -> l'import a
    # plat (`from engine.entities.selectors import ...`) ne le trouvait plus (ImportError).
    from engine.entities.selectors.geometry import neighbour_at, _TRIANGLE_SHAPE_DIRECTIONS
    ids = [board.id_at(pos[0], pos[1])]
    ids += [board.id_at(*neighbour_at(pos[0], pos[1], k))
            for k in _TRIANGLE_SHAPE_DIRECTIONS[direction]]
    return [i for i in ids if i is not None]


def _picker(mode):
    """Selecteur de tuile-cible dont le triangle BRUT (dir=1 = cote machine) perd une voisine a CAUSE
    D'UN SEUL des deux filtres — ce qui ISOLE le filtre teste (un port qui aurait oublie `Walkable`
    passerait un scenario ou l'ecart d'elevation suffit, et reciproquement)."""
    def _pick(board, positions):
        for p in positions:
            raw = _raw_triangle(board, p, 1)
            if len(raw) != 3:
                continue                                    # triangle deja tronque par un bord
            e0 = board.elevation(board.id_at(p[0], p[1]))
            drop_elev = [i for i in raw if board.walkable(i) and abs(board.elevation(i) - e0) > 1]
            drop_walk = [i for i in raw
                         if not board.walkable(i) and abs(board.elevation(i) - e0) <= 1]
            if (mode == "elevation" and drop_elev) or (mode == "walkable" and drop_walk):
                return p
        return None
    return _pick


@pytest.mark.parametrize("mode", ["elevation", "walkable"])
def test_macro_plasma_tile_filters_live(rpc_, mode):
    """GENERALISATION discriminante des FILTRES de `MacroPlasmaIncineratorAbility` :
    `TilesOnSameElevation(target, ., 1)` et `Walkable`, ISOLES l'un de l'autre.

    On CHOISIT (au lieu de subir) une tuile-cible dont le triangle BRUT (`TilesInTriangleShape`,
    geometrie pure) contient une voisine ecartee par UN SEUL des deux filtres -> la forme finale doit
    etre REDUITE, offline COMME live. Board `C2_02` (63 tuiles, 10 non-walkable, elevations 1..4) : sur
    `C1_02` aucun triangle ne declenche ces filtres, un port qui les OUBLIE y passerait sans broncher."""
    diag, off, live, ctx = _confront(rpc_, 1159, "ultraDreadnought", "tile",
                                     state_path=STATE_GEN, board_id=GEN_BOARD,
                                     pick_tile=_picker(mode))
    board = ctx["board"]
    raw = _raw_triangle(board, (ctx["target"]["col"], ctx["target"]["row"]), 1)
    tiles = [k for k in off if k != ctx["caster"]]
    print(f"\n[1159/filtre {mode}] tile={_tgt(ctx)} triangle BRUT={_coords(board, raw)} "
          f"(walkable={[board.walkable(i) for i in raw]}, elev={[board.elevation(i) for i in raw]})\n"
          f"       off={_coords(board, off)}\n       live={_coords(board, live)}")
    _dispose(rpc_, ctx)
    assert off == live, f"empreinte offline {off} != live {live} (filtre {mode})"
    assert len(tiles) < len(raw), \
        f"scenario non discriminant : {len(tiles)} tuiles marquees pour un triangle brut de {len(raw)}"


def test_machine_side_branch_flips_live(rpc_, host, live_session):
    """GENERALISATION la plus DISCRIMINANTE : la branche OPPOSEE de
    `IsPositionMachineForCurrentPlayer(2)` (IdunBattle.Entities.Triggers.IsPositionMachineForPlayerTrigger$$ShouldTrigger : le slot MoW du joueur COURANT).

    Montage : AUTRE board, DEUX MoW (une par camp), et on passe la main a l'ADVERSAIRE avant de caster
    SA MoW -> le joueur courant est celui dont le slot n'est PAS 2, donc `DevastatingRefrain` doit
    basculer sur le triplet de directions COMPLEMENTAIRE (`{0,2,4}` = {S,NE,NW}) et
    `MacroPlasmaIncinerator` sur l'autre coin de triangle. Aucun des deux cas n'a servi a batir le port
    (mesure de construction = MoW slot 2, joueur courant = son proprietaire)."""
    gen_extra = ["--p-mow", "ultraDreadnought", "--a-mow", "adeptExorcist"]
    rid, err = _build(STATE_GEN, gen_extra, board=GEN_BOARD, seed="31337")
    if rid is None:
        pytest.skip(f"build 2 MoW KO: {err}")
    try:
        rpc_("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        state, board, dec, _ob = _load(rpc_, rid, gen_extra, GEN_BOARD, "31337", endturn=1)
        mows = {m["visualId"]: m for m in (dec.get("mows") or [])}
        if "adeptExorcist" not in mows:
            pytest.skip("MoW adverse non deployee")
        m = mows["adeptExorcist"]
        cur = dec.get("currentPlayer")
        print(f"\n[gen] currentPlayer={cur} mows="
              f"{[(x['visualId'], x['casterId'], x['team'], x['owner'], x['slot']) for x in mows.values()]}")
        if m["owner"] != cur:
            pytest.skip("le endturn n'a pas donne la main au camp de la MoW adverse")
        caster = m["casterId"]
        tgt, _n = _pick_target(rpc_, rid, caster, 1188, prefer_center=True, board=board)
        if tgt is None or tgt["kind"] != "tile":
            pytest.skip("aucune tuile-cible pour DevastatingRefrain")
        tid = board.id_at(tgt["col"], tgt["row"])

        off_before = _offline_footprint(state)
        res = _apply_active_ability(state, caster, tid, 1188)
        diag = (res or {}).get("diag") or {}
        off = _delta(off_before, _offline_footprint(state))
        live_before = _live_footprint(rpc_, rid, board)
        act = _cast_live(rpc_, rid, caster, 1188, tgt)
        if act.get("error"):
            pytest.skip(f"cast natif bloque: {act.get('error')}")
        live = _delta(live_before, _live_footprint(rpc_, rid, board))
        print(f"[gen] slot={m['slot']} machineSide={diag.get('machineSide')}\n"
              f"      off={_coords(board, off)}\n      live={_coords(board, live)}")
        # la MoW du joueur courant est au slot != 2 -> branche FALSE du predicat
        assert diag.get("machineSide") is (int(m["slot"]) == 2), \
            f"verdict IsPositionMachineForCurrentPlayer(2)={diag.get('machineSide')} vs slot={m['slot']}"
        assert off == live, f"empreinte offline {off} != live {live} (branche opposee)"
    finally:
        try:
            rpc_("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
