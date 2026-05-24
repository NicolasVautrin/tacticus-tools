"""
rl_collect_batch.py — Pilote N battles AI-vs-AI sur runner isole.

Pipeline (v4 — pool dynamique 106 normalises, pattern PvP) :
  - Setup une fois :
      1. charger arena BC seed
      2. buildNormalizedBC offline -> recupere les 106 unitIds normalises
         (ceux qui passent IStatsFormula). On exclut les `:pvp` variants
         et les `*Smn*` summons (= les 61 skipped).
      3. lire les vraies spawn points du Board (TWPI=0 player, TWPI=1 AI)

  - Par battle :
      4. clone du template normalise
      5. PredefinedUnits = [{Id: 12 (AI), Units: rosterAI_random}]
      6. initRunner(configJson) -> ctor+Initialize spawn auto les AI
      7. applyAddUnit player_random × N aux spawn points TWPI=0 (PlayerId=11)
      8. startBattle -> Setup -> Running
      9. autoPlayRunner({maxTurns}) -> Finished ou maxTurns
     10. disposeRunner

Pendant tout ce temps, les hooks ai-trace (L1+L2) ecrivent dans
`frida/data/ai-traces/<sessionId>-<iso>.jsonl`. Aucune live BC touchee.

Pre-requis :
  - host tourne (http://127.0.0.1:8765)
  - session Frida active
  - warmupGameSingletons fait UNE fois apres reinject
  - ai-trace L1+L2 enabled (auto-enable)

Usage:
    python scripts/python/rl_collect_batch.py             # defaut: 5 battles
    python scripts/python/rl_collect_batch.py -n 50 --seed 42
    python scripts/python/rl_collect_batch.py --no-normalize  # garde stats seed

Stdlib only.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TypedDict

HOST = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[2]
TRACES_DIR = ROOT / "frida" / "data" / "ai-traces"
ARENA_SEED_BC = ROOT / "data" / "arena-battle-config-newtonsoft.json"
BOARDS_DIR = ROOT / "data" / "boards"

# PlayerIds lus de Player.Players du seed
PLAYER_ID_HUMAN = 11   # PlayerType=0, TeamId=1
PLAYER_ID_AI = 12      # PlayerType=1, TeamId=2


# ---- HTTP helpers ------------------------------------------------------- #

def _http(path: str, method: str = "GET",
          body: dict | None = None, timeout: float = 10.0) -> dict:
    url = HOST + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"_httpError": e.code, "_body": str(e)}
    except urllib.error.URLError as e:
        return {"_urlError": str(e)}


def _rpc(sid: int, method: str, args: list | None = None,
         timeout: float = 60.0) -> dict:
    body = {"method": method, "args": args or [], "timeout": int(timeout * 1000)}
    return _http(f"/api/scripts/{sid}/rpc", "POST", body, timeout=timeout + 5)


# ---- Pre-flight --------------------------------------------------------- #

def _resolve_session() -> int:
    st = _http("/api/admin/status")
    sess = st.get("session") or {}
    sid = sess.get("id")
    if not isinstance(sid, int):
        raise RuntimeError(
            f"no active Frida session — host status: {json.dumps(st)[:200]}")
    if sess.get("status") != "running":
        raise RuntimeError(
            f"session {sid} not running (status={sess.get('status')})")
    return sid


def _ensure_ai_trace(sid: int) -> dict:
    status = _rpc(sid, "aiTraceStatus", [], timeout=5).get("result") or {}
    for lvl in ("L1", "L2"):
        if not (status.get("enabled") or {}).get(lvl):
            _rpc(sid, "aiTraceEnable", [lvl], timeout=5)
    return _rpc(sid, "aiTraceStatus", [], timeout=5).get("result") or {}


def _dir_size_bytes(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.glob("*.jsonl") if f.is_file())


# ---- BC + pool setup ---------------------------------------------------- #

def _load_seed_bc() -> dict:
    if not ARENA_SEED_BC.exists():
        raise RuntimeError(f"seed BC not found: {ARENA_SEED_BC}")
    return json.loads(ARENA_SEED_BC.read_text(encoding="utf-8"))


def _load_board_dump(board_id: str) -> dict:
    """Load a board JSON dump (from dumpPvpAndSyncBoards). Searches across
    `pvp/`, `syncPvp/`, `global/` subfolders. Returns the full dump record
    (dict with keys: id, kind, spawnPointsSet, board) so the caller has
    both the BoardConfiguration and the paired SPS index.

    Why paired SPS matters: a board's SpawnPointSets array contains layouts
    for ALL game modes (campaign, PvP, sync PvP, MoW, etc.). PvP uses a
    specific 5v5 SPS picked by PvpGameModeSource.GetSpawnPointSetIndex →
    `_currentEncounter.SpawnPointsSet` (decompiled: reads field at offset
    0x70 on PvpEncounter). For our offline swap, the dumpPvpAndSyncBoards
    RPC saved that index alongside each PvP board → `spawnPointsSet`.
    """
    for kind in ("pvp", "syncPvp", "global"):
        p = BOARDS_DIR / kind / f"{board_id}.json"
        if p.exists():
            with p.open(encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(
        f"Board {board_id!r} not found under {BOARDS_DIR} "
        f"(searched pvp/, syncPvp/, global/)")


def _load_board_pool(kind: str, roster_size: int) -> list[dict]:
    """Load every dumped board of the given kind. Filters out boards
    whose paired SPS doesn't provide enough TWPI=0 + TWPI=1 spawn points
    (we need `roster_size` per side). PvP boards have the right paired
    SPS for 5v5 by definition, so this is mostly defensive."""
    pool_dir = BOARDS_DIR / kind
    if not pool_dir.exists():
        raise FileNotFoundError(f"No board dump dir {pool_dir}")
    out: list[dict] = []
    for p in sorted(pool_dir.glob("*.json")):
        try:
            with p.open(encoding="utf-8") as f:
                dump = json.load(f)
        except Exception:
            continue
        inner = dump.get("board")
        sps_idx = dump.get("spawnPointsSet")
        if not inner or not isinstance(sps_idx, int):
            continue
        sps_list = inner.get("SpawnPointSets") or []
        if not (0 <= sps_idx < len(sps_list)):
            continue
        groups = sps_list[sps_idx].get("SpawnPointGroups") or []
        twpi_counts = {g.get("TeamWithPlayerIndex"):
                       len(g.get("SpawnPoints") or []) for g in groups}
        if (twpi_counts.get(0, 0) >= roster_size
                and twpi_counts.get(1, 0) >= roster_size):
            out.append(dump)
    return out


def _normalize_and_extract_pool(
    sid: int, base_bc: dict, target_rank: int,
    board_dump: dict | None = None,
) -> tuple[dict, list[str], list[str]]:
    """Calls buildNormalizedBC. Returns
    (template_bc_normalized, pool_regular, pool_mow).

    Both pools are subsets of `result.normalized` (i.e. units that
    passed IStatsFormula.StatsUsingProgressionIndexFor at target rank).
    `pool_mow` are those flagged by IsMachineOfWar — they spawn via
    BC.PredefinedMachines, not PredefinedUnits, and obey the mode's
    SupportsMachinesOfWar. `pool_regular` = pool_normalized − pool_mow.

    If `board_dump` is given, the seed BC's Board is replaced by the
    dump's BoardConfiguration and SpawnPointSetIndex is set to the
    dump's paired sps. The buildNormalizedBC RPC supports `boardJson` +
    `spawnPointSetIndex` natively.
    """
    base_json = json.dumps(base_bc)
    args: dict = {
        "baseBcJson": base_json,
        "targetRank": target_rank,
        "targetProgressionIndex": target_rank,
        "targetRarity": 5,
        "targetLevel": 50,
        "targetStarLevel": 5,
        "targetAbilityLevel": 50,
    }
    if board_dump is not None:
        inner = board_dump.get("board")
        if not inner:
            raise RuntimeError(
                f"Board dump for {board_dump.get('id')!r} has no .board")
        args["boardJson"] = json.dumps(inner)
        sps = board_dump.get("spawnPointsSet")
        if isinstance(sps, int):
            args["spawnPointSetIndex"] = sps
    out = _rpc(sid, "buildNormalizedBC", [args], timeout=60).get("result") or {}
    if not out.get("ok"):
        raise RuntimeError(f"buildNormalizedBC failed: {out.get('err', '?')}")
    template = json.loads(out["configJson"])
    normalized = set(out.get("normalized") or [])
    mow_set = set(out.get("mow") or [])
    pool_regular = sorted(normalized - mow_set)
    pool_mow = sorted(mow_set)
    return template, pool_regular, pool_mow


def _spawn_points_by_twpi(bc: dict) -> dict[int, list[tuple[int, int]]]:
    """Lit les SpawnPointGroups du board pour le SpawnPointSetIndex actif."""
    sps_idx = bc.get("SpawnPointSetIndex") or 0
    sets = (bc.get("Board") or {}).get("SpawnPointSets") or []
    if sps_idx >= len(sets):
        return {}
    groups = sets[sps_idx].get("SpawnPointGroups") or []
    out: dict[int, list[tuple[int, int]]] = {}
    for g in groups:
        twpi = g.get("TeamWithPlayerIndex")
        pts = [(int(p["Column"]), int(p["Row"]))
               for p in (g.get("SpawnPoints") or [])
               if p.get("Column") is not None and p.get("Row") is not None]
        out[twpi] = pts
    return out


# ---- One battle --------------------------------------------------------- #

def _patch_predefined_units(bc: dict, ai_roster: list[str]) -> None:
    """1 group AI (PlayerId=12, sans suffix). Player via AddUnit."""
    bc["PredefinedUnits"] = [{
        "Id": PLAYER_ID_AI,
        "Units": [
            {"UnitId": u, "RemainingHealth": None, "MaxHealth": None}
            for u in ai_roster
        ],
    }]


def _patch_predefined_machines(
    bc: dict,
    player_mow: str | None,
    ai_mow: str | None,
) -> None:
    """Set BC.PredefinedMachines = MoW lineup. Pass None to omit a side
    (no MoW for that team). Replaces any existing entries from the seed
    BC (which may contain `:pvp` variants that fail normalization)."""
    machines: list[dict] = []
    if ai_mow:
        machines.append({
            "Id": PLAYER_ID_AI,
            "MachineOfWar": {"UnitId": ai_mow},
        })
    if player_mow:
        machines.append({
            "Id": PLAYER_ID_HUMAN,
            "MachineOfWar": {"UnitId": player_mow},
        })
    bc["PredefinedMachines"] = machines


def _attempt_battle(sid: int, idx: int, bc: dict, roster_p: list[str],
                    roster_a: list[str], engine_seed: int,
                    player_pts: list[tuple[int, int]], max_turns: int,
                    roster_size: int, attempt_tag: str = "") -> dict:
    """Execute one battle with already-frozen (bc, rosters, seed). Used
    by both the main loop and the retry path so the retry replays the
    EXACT same config without consuming the rng state again."""
    t0 = time.monotonic()
    # One consolidated RPC: deserializes BC, builds runner, applies
    # each player AddUnit at its spawn point, then StartMatch.
    # Atomic cleanup on fail (configPtr + runner unpinned, recorder
    # detached) — see initAndStart in launch.ts.
    player_units = [
        {"unitId": roster_p[i], "playerId": PLAYER_ID_HUMAN,
         "col": int(player_pts[i][0]), "row": int(player_pts[i][1])}
        for i in range(min(len(roster_p), len(player_pts)))
    ]
    init_resp = _rpc(sid, "initAndStart",
                     [{"configJson": json.dumps(bc),
                       "seed": engine_seed,
                       "playerUnits": player_units}], timeout=30)
    init = init_resp.get("result") or {}
    runner_id = init.get("runnerId")
    if runner_id is None:
        rpc_err = (init.get("err") or init_resp.get("error")
                   or (f"HTTP {init_resp.get('_httpError')}"
                       if init_resp.get("_httpError") else None)
                   or init_resp.get("_urlError")
                   or "no runnerId")
        return {"i": idx, "ok": False, "phase": "init",
                "rosterP": roster_p, "rosterA": roster_a,
                "engineSeed": engine_seed,
                "attemptTag": attempt_tag,
                "err": rpc_err,
                "elapsed": time.monotonic() - t0}
    spawn_p_ok = len(init.get("addUnits") or [])

    # autoPlay
    play = _rpc(sid, "autoPlayRunner",
                [{"runnerId": runner_id, "maxTurns": max_turns}],
                timeout=180).get("result") or {}

    # dispose
    _rpc(sid, "disposeRunner", [{"runnerId": runner_id}], timeout=5)

    # Extract frame delta stats from history (added in cheat.ts: each
    # turn's per-frame queueOnMainThread emits its frameNo; deltas tell
    # us empirically how many Unity frames elapsed between turns).
    hist = play.get("history") or []
    frames = [h.get("frameNo") for h in hist if h.get("frameNo") is not None]
    frame_deltas = [frames[i+1]-frames[i] for i in range(len(frames)-1)]
    frame_summary = None
    if frame_deltas:
        frame_summary = {
            "min": min(frame_deltas), "max": max(frame_deltas),
            "avg": round(sum(frame_deltas)/len(frame_deltas), 1),
        }

    elapsed = time.monotonic() - t0
    return {
        "i": idx, "ok": bool(play.get("ok")),
        "runnerId": runner_id, "rosterP": roster_p, "rosterA": roster_a,
        "engineSeed": engine_seed,
        "attemptTag": attempt_tag,
        "spawnP": spawn_p_ok, "spawnErrs": [],
        "turns": play.get("turns"),
        "reachedFinished": play.get("reachedFinished"),
        "finalStage": play.get("finalStage"),
        "hitMaxTurns": play.get("hitMaxTurns"),
        "elapsed": elapsed,
        "phase": "play" if not play.get("ok") else None,
        "err": play.get("reason") if not play.get("ok") else None,
        "frameDeltas": frame_summary,
    }


class BattleConfig(TypedDict, total=False):
    """Per-battle resolved content : regular units (5 per side), optional
    MoW per side, optional board dump (= board JSON + paired SPS index).
    Built once by `_pick_battle_config`, consumed by `_one_battle`.

    `board=None` means "keep the template BC's board" (= seed BC's
    PVP_desert_08 by default, or the --board override applied at
    template build time)."""
    p_units: list[str]
    a_units: list[str]
    p_mow: str | None
    a_mow: str | None
    board: dict | None  # board dump record (id, kind, spawnPointsSet, board)


def _pick_battle_config(
    rng: random.Random,
    pool: list[str], pool_mow: list[str], roster_size: int,
    fixed_p_mow: str | None, fixed_a_mow: str | None, no_mow: bool,
    board_pool: list[dict] | None,
) -> BattleConfig:
    """Sample a BattleConfig from rng so `--seed` keeps the whole batch
    deterministic. Order of consumption matters for apples-to-apples
    comparisons across runs:
      1. player units, 2. AI units, 3. MoW (player then AI),
      4. board (only if board_pool given).
    Putting the optional ones LAST means a no-MoW or no-board run
    produces identical unit rosters."""
    p_units = rng.sample(pool, k=min(roster_size, len(pool)))
    a_units = rng.sample(pool, k=min(roster_size, len(pool)))
    if no_mow or not pool_mow:
        p_mow, a_mow = None, None
    else:
        p_mow = fixed_p_mow if fixed_p_mow else rng.choice(pool_mow)
        a_mow = fixed_a_mow if fixed_a_mow else rng.choice(pool_mow)
    board = rng.choice(board_pool) if board_pool else None
    return {"p_units": p_units, "a_units": a_units,
            "p_mow": p_mow, "a_mow": a_mow, "board": board}


def _one_battle(sid: int, idx: int, template_bc: dict, cfg: BattleConfig,
                default_player_pts: list[tuple[int, int]], max_turns: int,
                roster_size: int, batch_seed: int,
                retry_on_fail: int = 0) -> dict:
    """Run a battle for a pre-sampled BattleConfig. If --retry-on-fail
    > 0, replays the EXACT same config (same bc, same seed, same
    rosters, same MoW, same board) up to N times so we can tell whether
    the engine is wedged or the config itself is the problem."""
    t0_outer = time.monotonic()

    bc = copy.deepcopy(template_bc)
    _patch_predefined_units(bc, cfg["a_units"])
    _patch_predefined_machines(bc, cfg.get("p_mow"), cfg.get("a_mow"))
    # Optional per-battle board swap. Without a board dump in cfg, the
    # template's board stays in place. With one, both Board and
    # SpawnPointSetIndex (paired with the board) are replaced — and
    # the player spawn points are re-derived from the new board.
    if cfg.get("board") is not None:
        board_dump = cfg["board"]
        bc["Board"] = board_dump["board"]
        bc["SpawnPointSetIndex"] = board_dump["spawnPointsSet"]
        spawns = _spawn_points_by_twpi(bc)
        player_pts = spawns.get(0) or []
    else:
        player_pts = default_player_pts
    if len(player_pts) < roster_size:
        return {"i": idx, "ok": False, "phase": "spawn-pts",
                "err": f"only {len(player_pts)} player spawn points "
                       f"(need {roster_size})",
                "elapsed": time.monotonic() - t0_outer}

    # Deterministic engine RNG seed (does NOT consume `rng` so rosters
    # stay apples-to-apples with a run without engine seeding).
    engine_seed = ((batch_seed * 1009 + idx * 2654435761) & 0x7fffffff) or 1

    first = _attempt_battle(sid, idx, bc, cfg["p_units"],
                            cfg["a_units"], engine_seed, player_pts,
                            max_turns, roster_size, attempt_tag="primary")
    first["mowPlayer"] = cfg.get("p_mow")
    first["mowAi"] = cfg.get("a_mow")
    board_dump = cfg.get("board")
    first["boardId"] = board_dump["id"] if board_dump else None
    if first.get("ok") or retry_on_fail <= 0:
        return first

    # Replay the same config to test whether the engine is wedged
    # (retry also fails) vs transient (retry succeeds → state-dependent).
    retries: list[dict] = []
    for k in range(retry_on_fail):
        time.sleep(0.2)
        again = _attempt_battle(
            sid, idx, copy.deepcopy(bc), cfg["p_units"],
            cfg["a_units"], engine_seed, player_pts,
            max_turns, roster_size, attempt_tag=f"retry#{k+1}")
        retries.append(again)
        if again.get("ok"):
            break

    first["retries"] = retries
    first["retrySucceeded"] = any(r.get("ok") for r in retries)
    return first


# ---- Main --------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--num-battles", type=int, default=5)
    ap.add_argument("--max-turns", type=int, default=200)
    ap.add_argument("--target-rank", type=int, default=17)
    ap.add_argument("--roster-size", type=int, default=5)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--retry-on-fail", type=int, default=0,
                    help="On a battle fail, replay the EXACT same "
                         "config (same bc, same engine seed, same "
                         "rosters) up to N times. Tells us whether the "
                         "engine is wedged or the failure is transient.")
    ap.add_argument("--probe-unit", type=str, default=None,
                    help="After a fail (and after the canary), probe "
                         "the canary's rosterA with each slot replaced "
                         "by this UnitId one at a time. Tells us if a "
                         "single unit triggers the crash in this state.")
    ap.add_argument("--board", type=str, default=None,
                    help="Swap the seed BC's board for this dumped "
                         "board id (e.g. C1_02). Searches data/boards/"
                         "<pvp|syncPvp|global>/<id>.json. Paired SPS is "
                         "auto-applied (PvpGameModeSource uses one "
                         "specific SPS per board, stored alongside).")
    ap.add_argument("--board-pool", type=str, default=None,
                    choices=["pvp", "syncPvp", "global"],
                    help="Random board per battle from this dump pool "
                         "(filtered to boards whose paired SPS has "
                         "enough player+AI spawn points). Mutually "
                         "exclusive with --board.")
    ap.add_argument("--mow-player", type=str, default=None,
                    help="Add a Machine of War on the player side "
                         "(PlayerId=11). UnitId must come from the "
                         "normalized MoW pool (use --list-mow to see). "
                         "Some game modes refuse MoW — the BC's mode "
                         "(arena/PvP) does support it.")
    ap.add_argument("--mow-ai", type=str, default=None,
                    help="Replace the seed BC's AI Machine of War "
                         "(default astraOrdnanceBattery:pvp).")
    ap.add_argument("--no-mow", action="store_true",
                    help="Clear BC.PredefinedMachines entirely "
                         "(no MoW on either side).")
    ap.add_argument("--list-mow", action="store_true",
                    help="Print the normalized MoW pool and exit.")
    args_ns = ap.parse_args(argv[1:])

    try:
        sid = _resolve_session()
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    print(f"[ok] session id = {sid}")

    trace_status = _ensure_ai_trace(sid)
    print(f"[ok] ai-trace enabled = {trace_status.get('enabled')}")

    try:
        seed_bc = _load_seed_bc()
        print(f"[ok] seed BC ({len(seed_bc.get('Units') or [])} unit templates)")
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    # Board options: --board (fixed for the whole batch, swapped at
    # setup time) vs --board-pool (random per battle, applied in
    # _one_battle). Mutually exclusive.
    if args_ns.board and args_ns.board_pool:
        print("[error] --board and --board-pool are mutually exclusive",
              file=sys.stderr)
        return 2
    board_dump: dict | None = None
    board_pool: list[dict] = []
    if args_ns.board:
        try:
            board_dump = _load_board_dump(args_ns.board)
            inner = board_dump.get("board") or {}
            print(f"[ok] board swap (fixed): id={board_dump.get('id')} "
                  f"kind={board_dump.get('kind')} "
                  f"{inner.get('Width')}x{inner.get('Height')} "
                  f"sps={board_dump.get('spawnPointsSet')}")
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[error] {e}", file=sys.stderr)
            return 2
    elif args_ns.board_pool:
        try:
            board_pool = _load_board_pool(
                args_ns.board_pool, args_ns.roster_size)
            print(f"[ok] board pool ({args_ns.board_pool}): "
                  f"{len(board_pool)} boards eligible "
                  f"(>={args_ns.roster_size} pts per side)")
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[error] {e}", file=sys.stderr)
            return 2
        if not board_pool:
            print(f"[error] empty board pool for kind="
                  f"{args_ns.board_pool!r}", file=sys.stderr)
            return 2

    # Setup : normalize + extract pool (with optional board swap)
    try:
        t0 = time.monotonic()
        template_bc, pool, pool_mow = _normalize_and_extract_pool(
            sid, seed_bc, args_ns.target_rank, board_dump=board_dump)
        print(f"[ok] BC normalized to rank {args_ns.target_rank} "
              f"({(time.monotonic()-t0)*1000:.0f} ms) — pool: "
              f"{len(pool)} regular + {len(pool_mow)} MoW")
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    if args_ns.list_mow:
        print(f"[ok] MoW pool ({len(pool_mow)} units):")
        for u in pool_mow:
            print(f"  {u}")
        return 0

    # MoW config summary (per-battle picks happen in _one_battle so the
    # rng can drive diversity across the batch).
    if args_ns.no_mow:
        print("[ok] MoW: disabled on both sides (--no-mow)")
    else:
        player_mow_desc = (args_ns.mow_player if args_ns.mow_player
                           else f"random from {len(pool_mow)}")
        ai_mow_desc = (args_ns.mow_ai if args_ns.mow_ai
                       else f"random from {len(pool_mow)}")
        print(f"[ok] MoW: player={player_mow_desc} ai={ai_mow_desc}")
        if not pool_mow and not args_ns.mow_player and not args_ns.mow_ai:
            print("[error] pool_mow is empty — can't pick random MoW",
                  file=sys.stderr)
            return 2
        for explicit in (args_ns.mow_player, args_ns.mow_ai):
            if explicit and explicit not in pool_mow:
                print(f"[warn] {explicit!r} not in normalized MoW pool "
                      f"— using anyway")

    # Spawn points TWPI=0 (player)
    spawns = _spawn_points_by_twpi(template_bc)
    player_pts = spawns.get(0) or []
    ai_pts = spawns.get(1) or []
    print(f"[ok] spawn points: TWPI=0 (player)={len(player_pts)}, "
          f"TWPI=1 (AI)={len(ai_pts)}")

    if len(pool) < args_ns.roster_size:
        print(f"[error] pool ({len(pool)}) < roster size ({args_ns.roster_size})",
              file=sys.stderr)
        return 2

    seed = args_ns.seed if args_ns.seed is not None else int(time.time())
    rng = random.Random(seed)
    print(f"[ok] seed = {seed}")

    bytes_before = _dir_size_bytes(TRACES_DIR)
    print(f"[ok] ai-traces dir : {TRACES_DIR}")
    print(f"[ok] bytes before  : {bytes_before:,}")
    print(f"[ok] launching {args_ns.num_battles} battles "
          f"(maxTurns={args_ns.max_turns}, roster={args_ns.roster_size}/team)")
    print("-" * 60)

    results = []
    t_global = time.monotonic()
    for i in range(args_ns.num_battles):
        cfg = _pick_battle_config(
            rng, pool, pool_mow, args_ns.roster_size,
            fixed_p_mow=args_ns.mow_player,
            fixed_a_mow=args_ns.mow_ai,
            no_mow=args_ns.no_mow,
            board_pool=board_pool or None)
        r = _one_battle(sid, i + 1, template_bc, cfg, player_pts,
                        args_ns.max_turns, args_ns.roster_size,
                        seed, retry_on_fail=args_ns.retry_on_fail)
        # Canary test: if the primary attempt + all its same-config
        # retries failed, replay the LAST successful battle to tell
        # apart "engine wedged" vs "config #N poisoned in this state".
        if (not r.get("ok")
                and args_ns.retry_on_fail > 0
                and not r.get("retrySucceeded", False)):
            last_ok = next((p for p in reversed(results) if p.get("ok")),
                           None)
            if last_ok is not None:
                bc_canary = copy.deepcopy(template_bc)
                _patch_predefined_units(bc_canary, last_ok["rosterA"])
                _patch_predefined_machines(
                    bc_canary, last_ok.get("mowPlayer"),
                    last_ok.get("mowAi"))
                time.sleep(0.2)
                canary = _attempt_battle(
                    sid, last_ok["i"], bc_canary,
                    list(last_ok["rosterP"]),
                    list(last_ok["rosterA"]),
                    int(last_ok["engineSeed"]),
                    player_pts, args_ns.max_turns,
                    args_ns.roster_size, attempt_tag="canary")
                r["canary"] = canary
                # Probe: take the canary roster and replace each slot
                # one at a time with --probe-unit, see which slot (if
                # any) triggers the crash. Skip if canary itself failed
                # (would just confirm engine-wedged, no signal).
                if (args_ns.probe_unit
                        and canary.get("ok")
                        and last_ok.get("rosterA")):
                    probes: list[dict] = []
                    base_a = list(last_ok["rosterA"])
                    for slot in range(len(base_a)):
                        rosterA_probe = list(base_a)
                        rosterA_probe[slot] = args_ns.probe_unit
                        bc_probe = copy.deepcopy(template_bc)
                        _patch_predefined_units(bc_probe, rosterA_probe)
                        _patch_predefined_machines(
                            bc_probe, last_ok.get("mowPlayer"),
                            last_ok.get("mowAi"))
                        time.sleep(0.2)
                        pr = _attempt_battle(
                            sid, last_ok["i"], bc_probe,
                            list(last_ok["rosterP"]),
                            rosterA_probe,
                            int(last_ok["engineSeed"]),
                            player_pts, args_ns.max_turns,
                            args_ns.roster_size,
                            attempt_tag=f"probe[slot={slot}]")
                        probes.append({"slot": slot,
                                       "rosterA": rosterA_probe,
                                       "result": pr})
                        if not pr.get("ok"):
                            # Found the trigger — no need to keep
                            # poking the wedged engine. Stop here.
                            break
                    r["probes"] = probes
        results.append(r)
        # Petit sleep entre battles : pas indispensable (autoPlayRunner
        # lui-meme yield la frame entre turns maintenant), mais laisse
        # un peu de breath pour l'ai-trace flush et le dispose async.
        time.sleep(0.05)
        if r.get("ok"):
            mow_tag = ""
            if r.get("mowPlayer") or r.get("mowAi"):
                mow_tag = (f" mowP={r.get('mowPlayer')} "
                           f"mowA={r.get('mowAi')}")
            board_tag = (f" board={r.get('boardId')}"
                         if r.get("boardId") else "")
            print(f"  [{i+1:>3}/{args_ns.num_battles}] "
                  f"ok turns={r['turns']:>3} fin={r['reachedFinished']} "
                  f"spawnP={r.get('spawnP', '?')}/{args_ns.roster_size} "
                  f"({r['elapsed']:.1f}s) frameDeltas={r.get('frameDeltas')}"
                  f"{mow_tag}{board_tag}")
            print(f"           rosterP={r.get('rosterP')}")
            print(f"           rosterA={r.get('rosterA')}")
        else:
            print(f"  [{i+1:>3}/{args_ns.num_battles}] "
                  f"FAIL phase={r.get('phase')} err={r.get('err')!r} "
                  f"({r['elapsed']:.1f}s)")
            print(f"           rosterP={r.get('rosterP')}")
            print(f"           rosterA={r.get('rosterA')}")
            print(f"           engineSeed={r.get('engineSeed')}")
            for rk, ret in enumerate(r.get("retries") or []):
                tag = "OK" if ret.get("ok") else "FAIL"
                turns = ret.get("turns")
                print(f"           [retry#{rk+1}] {tag} "
                      f"turns={turns} elapsed={ret.get('elapsed', 0):.1f}s "
                      f"err={ret.get('err')!r}")
            canary = r.get("canary")
            if canary is not None:
                tag = "OK" if canary.get("ok") else "FAIL"
                print(f"           [canary i={canary.get('i')}] {tag} "
                      f"turns={canary.get('turns')} "
                      f"elapsed={canary.get('elapsed', 0):.1f}s "
                      f"err={canary.get('err')!r}")
            for pr in r.get("probes") or []:
                res = pr["result"]
                tag = "OK" if res.get("ok") else "FAIL"
                print(f"           [probe slot={pr['slot']}] {tag} "
                      f"rosterA={pr['rosterA']} "
                      f"elapsed={res.get('elapsed', 0):.1f}s "
                      f"err={res.get('err')!r}")

    total_elapsed = time.monotonic() - t_global
    bytes_after = _dir_size_bytes(TRACES_DIR)
    delta = bytes_after - bytes_before

    print("-" * 60)
    ok_count = sum(1 for r in results if r.get("ok"))
    finished = sum(1 for r in results
                   if r.get("ok") and r.get("reachedFinished"))
    total_turns = sum(r.get("turns") or 0 for r in results)
    print("== resume ==")
    print(f"  battles ok          : {ok_count}/{len(results)}")
    if ok_count:
        print(f"  reached Finished    : {finished}/{ok_count}")
    print(f"  total turns         : {total_turns}")
    print(f"  ai-traces           : {bytes_before:,} -> {bytes_after:,} "
          f"(+{delta:,} bytes)")
    print(f"  total elapsed       : {total_elapsed:.1f}s")
    if ok_count and total_turns:
        print(f"  avg time / turn     : "
              f"{(total_elapsed/total_turns)*1000:.0f} ms")

    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
