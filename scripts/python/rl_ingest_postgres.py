"""
rl_ingest_postgres.py — ingere un batch RL (summary JSON + trace JSONL)
dans la base Postgres `tacticus_rl`.

Usage:
    python scripts/python/rl_ingest_postgres.py                   # ingere le plus recent
    python scripts/python/rl_ingest_postgres.py --summary <path>  # ingere un specifique
    python scripts/python/rl_ingest_postgres.py --all             # ingere tous les non-ingerges

Strategie de join :
  - summary.battles[*].runnerId  ←joint→  jsonl events.runnerId
  - 1 batch  → N battles
  - 1 battle → 1 battle_winner event, K move_options events

Idempotence :
  - On vise pas l'idempotence ici. Ré-ingerer creerait des doublons.
  - Pour purger un batch : `DELETE FROM tacticus.batch WHERE batch_id=X`
    (cascade fait le reste).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    print("ERREUR : pip install 'psycopg[binary]'", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
TRACES_DIR = ROOT / "frida" / "data" / "ai-traces"
SUMMARIES_DIR = ROOT / "frida" / "data" / "rl-batches"
ENV_PATH = ROOT / ".env"


# ---- .env loader stdlib ------------------------------------------------- #

def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


# ---- JSONL trace reader ------------------------------------------------- #

# `stream_event.step_name` — dérivé de la table VERSIONNÉE `data/symbols/<CURRENT>/frida/
# enums.tsv`, jamais recopié (#254b-b). La copie littérale qui vivait ici datait de
# `gqfc5mff6c` ; depuis que `rnca9r7q6c` a retiré `StepType.RestoreArmorInfo` (7), elle
# décalait de +1 le nom de TOUT pas >= 7 — l'ingest écrivait `AddUnit` pour un `AddMachine`,
# `RemoveUnit` pour un `ChangeStats`, sans erreur ni trace.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stream_events as _SE  # noqa: E402


class _StepNames:
    """`.get(ordinal)` -> NOM, ou None si l'ordinal n'existe pas sur le build courant."""

    @staticmethod
    def get(i, defaut=None):
        try:
            n = _SE.step_name(i)
        except (TypeError, ValueError):
            return defaut
        return defaut if n.startswith("Step#") else n


STEP_NAMES = _StepNames()


def _read_trace_events(trace_paths: list[Path]) -> dict[int, dict[str, list]]:
    """Lit les fichiers JSONL et regroupe par `runnerId`.
    Capture : move_options, battle_winner, message, message_events.
    Les `message_events` sont indexes par msgIdx (pas runnerId) pour pouvoir
    les joindre avec les `message` events apres."""
    by_runner: dict[int, dict[str, list]] = {}
    msg_events_by_idx: dict[int, list] = {}
    for tp in trace_paths:
        if not tp.exists():
            print(f"  ! trace file absent: {tp}", file=sys.stderr)
            continue
        with open(tp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                evt = rec.get("evt")
                if evt == "message_events":
                    midx = rec.get("msgIdx")
                    if isinstance(midx, int):
                        msg_events_by_idx[midx] = rec.get("events") or []
                    continue
                if evt not in ("move_options", "battle_winner", "message"):
                    continue
                rid = rec.get("runnerId")
                if not isinstance(rid, int):
                    continue
                bucket = by_runner.setdefault(
                    rid, {"move_options": [], "battle_winner": [],
                          "message": []})
                bucket[evt].append(rec)
    # Attach message_events to each message by msgIdx
    for rid, bucket in by_runner.items():
        for msg in bucket.get("message", []):
            mi = msg.get("msgIdx")
            msg["_events"] = msg_events_by_idx.get(mi, []) if mi else []
    return by_runner


# ---- Insertion ---------------------------------------------------------- #

def _ingest_summary(conn: psycopg.Connection, summary_path: Path,
                    game_hash: str | None) -> int:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    trace_files = [TRACES_DIR / name for name in summary.get("trace_files") or []]
    events_by_runner = _read_trace_events(trace_files)

    with conn.cursor() as cur:
        # batch row
        cur.execute("""
            INSERT INTO tacticus.batch (seed, n_battles, game_hash, config, hooks_sha)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING batch_id
        """, (
            summary.get("seed"),
            summary.get("n_battles"),
            game_hash,
            Jsonb(summary.get("args") or {}),
            None,  # hooks_sha — TODO: read .git/HEAD if useful
        ))
        batch_id = cur.fetchone()[0]
        print(f"  batch_id = {batch_id}")

        battles = summary.get("battles") or []
        n_battle_rows = 0
        n_winner_updates = 0
        n_move_events = 0
        n_messages = 0
        n_stream_events = 0
        n_unit_states = 0
        n_mow_states = 0
        for b in battles:
            runner_id = b.get("runnerId")
            cur.execute("""
                INSERT INTO tacticus.battle (
                    batch_id, idx, runner_id,
                    roster_p, roster_a, mow_p, mow_a, board_id,
                    engine_seed, ok, final_stage,
                    reached_finished, hit_max_turns,
                    turns_count, elapsed_ms, err
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING battle_id
            """, (
                batch_id,
                b.get("i"),
                runner_id,
                b.get("rosterP"),
                b.get("rosterA"),
                b.get("mowPlayer"),
                b.get("mowAi"),
                b.get("boardId"),
                b.get("engineSeed"),
                bool(b.get("ok")),
                b.get("finalStage"),
                bool(b.get("reachedFinished")),
                bool(b.get("hitMaxTurns")),
                _safe_int(b.get("turns")),
                _safe_ms(b.get("elapsed")),
                b.get("err"),
            ))
            battle_id = cur.fetchone()[0]
            n_battle_rows += 1

            # Update winner from battle_winner event if any
            if runner_id is not None and runner_id in events_by_runner:
                win_events = events_by_runner[runner_id]["battle_winner"]
                if win_events:
                    win = win_events[-1]  # dernier (cas où plusieurs)
                    cur.execute("""
                        UPDATE tacticus.battle
                           SET winner_player_id = %s,
                               winner_team_id   = %s,
                               winner_entity_id = %s,
                               outcome          = %s,
                               reason_code      = %s,
                               reason_name      = %s
                         WHERE battle_id = %s
                    """, (
                        win.get("winnerPlayerId"),
                        win.get("winnerTeamId"),
                        win.get("winnerEntityId"),
                        win.get("outcome"),
                        win.get("reasonCode"),
                        win.get("reasonName"),
                        battle_id,
                    ))
                    n_winner_updates += 1

            # Insert move_options events for this runner
            if runner_id is not None and runner_id in events_by_runner:
                mo_events = events_by_runner[runner_id]["move_options"]
                # Bulk-friendly : on construit la liste de tuples puis
                # executemany.
                rows = []
                for ev in mo_events:
                    opts = ev.get("options") or {}
                    rows.append((
                        battle_id,
                        ev.get("applySeq"),
                        ev.get("unitEntityId"),
                        ev.get("turn"),
                        ev.get("turnPlayer"),
                        bool(ev.get("ignoreFlags")),
                        bool(opts.get("ignSpecial")),
                        bool(opts.get("ignUnits")),
                        bool(opts.get("isDanger")),
                        opts.get("overrideRange"),
                        bool(opts.get("hasRangeBonus")),
                        ev.get("fireNo"),
                        Jsonb(ev.get("candidates") or []),
                    ))
                if rows:
                    cur.executemany("""
                        INSERT INTO tacticus.move_options_event (
                            battle_id, apply_seq, unit_entity_id,
                            turn, turn_player, ignore_flags,
                            opt_ign_special, opt_ign_units, opt_is_danger,
                            opt_override_range, opt_has_range_bonus,
                            fire_no, candidates
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s
                        )
                    """, rows)
                    n_move_events += len(rows)

            # Insert messages + stream events for this runner
            if runner_id is not None and runner_id in events_by_runner:
                msg_records = events_by_runner[runner_id]["message"]
                for msg in msg_records:
                    ms = msg.get("matchState") or {}
                    cur.execute("""
                        INSERT INTO tacticus.message (
                            battle_id, msg_idx, apply_seq, src,
                            msg_class, unit_id_raw, runner_id,
                            turn, stage, stage_name, player_on_turn
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s,
                                  %s, %s, %s, %s)
                        RETURNING message_id
                    """, (
                        battle_id,
                        msg.get("msgIdx"),
                        msg.get("applySeq"),
                        msg.get("src"),
                        msg.get("msgClass"),
                        _safe_int(msg.get("unitId")),
                        runner_id,
                        _safe_int(ms.get("turn")),
                        _safe_int(ms.get("stage")),
                        ms.get("stageName"),
                        _safe_int(ms.get("playerOnTurn")),
                    ))
                    message_id = cur.fetchone()[0]
                    n_messages += 1

                    # Insert unit_state rows (1 per UnitFoot of the snapshot)
                    units_in_state = ms.get("units") or []
                    if units_in_state:
                        us_rows = []
                        for u in units_in_state:
                            pos = u.get("pos") or {}
                            us_rows.append((
                                message_id,
                                _safe_int(u.get("id")),
                                _safe_int(u.get("squadId")),
                                _safe_int(pos.get("col")),
                                _safe_int(pos.get("row")),
                                _safe_int(u.get("hp")),
                                _safe_int(u.get("maxHp")),
                                _safe_int(u.get("ownerId")),
                                _safe_int(u.get("teamId")),
                                u.get("visualId"),
                                _safe_int(u.get("rank")),
                                bool(u.get("isDead")),
                            ))
                        cur.executemany("""
                            INSERT INTO tacticus.unit_state (
                                message_id, unit_id, squad_id,
                                col, row, hp, hp_max, owner_id,
                                team_id, visual_id, rank, is_dead
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s
                            )
                        """, us_rows)
                        n_unit_states += len(us_rows)

                    # Insert mow_state rows (1 per Machine of War in the
                    # snapshot — analogous to unit_state for UnitFoot).
                    # matchState.mows is populated by projectMatchState since
                    # the MoW work; prior batches had none, hence mow_state=0.
                    mows_in_state = ms.get("mows") or []
                    if mows_in_state:
                        mow_rows = []
                        for w in mows_in_state:
                            pos = w.get("pos") or {}
                            mow_rows.append((
                                message_id,
                                _safe_int(w.get("id")),
                                _safe_int(w.get("machineId")),
                                _safe_int(pos.get("col")),
                                _safe_int(pos.get("row")),
                                _safe_int(w.get("hp")),
                                _safe_int(w.get("maxHp")),
                                _safe_int(w.get("ownerId")),
                                _safe_int(w.get("teamId")),
                                w.get("visualId"),
                                _safe_int(w.get("rank")),
                                _safe_int(w.get("initialSlot")) or 0,
                                bool(w.get("isDead")),
                            ))
                        cur.executemany("""
                            INSERT INTO tacticus.mow_state (
                                message_id, platform_id, machine_id,
                                col, row, hp, hp_max, owner_id,
                                team_id, visual_id, rank, initial_slot, is_dead
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s
                            )
                        """, mow_rows)
                        n_mow_states += len(mow_rows)

                    events = msg.get("_events") or []
                    if not events:
                        continue
                    se_rows = []
                    for ord_idx, ev in enumerate(events):
                        kind = ev.get("kind")
                        step = ev.get("step") if kind == "action" else None
                        group = ev.get("group") if kind == "group" else None
                        step_name = STEP_NAMES.get(step) if step is not None else None
                        # `tags` est deja une string JSON cote Frida ;
                        # on la re-parse pour la stocker en JSONB.
                        tags_raw = ev.get("tags")
                        tags_json = None
                        if isinstance(tags_raw, str):
                            try:
                                tags_json = Jsonb(json.loads(tags_raw))
                            except json.JSONDecodeError:
                                tags_json = None
                        elif isinstance(tags_raw, dict):
                            tags_json = Jsonb(tags_raw)
                        se_rows.append((
                            message_id, ord_idx, kind,
                            step, step_name, group,
                            _safe_int(ev.get("entity")),
                            tags_json,
                        ))
                    cur.executemany("""
                        INSERT INTO tacticus.stream_event (
                            message_id, ordinal, kind,
                            step_code, step_name, group_code,
                            entity_id, tags
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, se_rows)
                    n_stream_events += len(se_rows)

        conn.commit()
        print(f"  battles       : {n_battle_rows}")
        print(f"  winners       : {n_winner_updates}")
        print(f"  move_options  : {n_move_events}")
        print(f"  messages      : {n_messages}")
        print(f"  unit_states   : {n_unit_states}")
        print(f"  mow_states    : {n_mow_states}")
        print(f"  stream_events : {n_stream_events}")
        return batch_id


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_ms(v: Any) -> int | None:
    """Convertit elapsed (secondes float) en ms int."""
    if v is None:
        return None
    try:
        return int(float(v) * 1000)
    except (TypeError, ValueError):
        return None


# ---- Main --------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", type=Path,
                    help="Chemin d'un summary specifique a ingerer")
    ap.add_argument("--all", action="store_true",
                    help="Ingere tous les summaries de rl-batches/")
    ap.add_argument("--game-hash", type=str, default=None,
                    help="Hash du build Tacticus (ex. rmvdp0v56c)")
    args = ap.parse_args(argv[1:])

    env = _load_env(ENV_PATH)
    host = env.get("PG_HOST", "localhost")
    port = env.get("PG_PORT", "5433")
    db = env.get("PG_DATABASE", "tacticus_rl")
    user = env.get("PG_USER", "postgres")
    pwd = env.get("PG_PASSWORD", "")
    if not pwd:
        print("ERREUR : PG_PASSWORD vide dans .env", file=sys.stderr)
        return 1

    # Default game_hash : lit depuis le dossier des dumps actif
    game_hash = args.game_hash
    if game_hash is None:
        for p in (ROOT / "data" / "dumps").iterdir():
            if p.is_dir() and (p / "HASH").exists():
                h = (p / "HASH").read_text().strip()
                # Auto-detect : le hash du Tacticus actif est dans
                # ~/AppData/Local/tacticus/games/<HASH>/ — on prend le
                # premier match.
                games_dir = Path(os.path.expandvars(
                    r"%LOCALAPPDATA%\tacticus\games"))
                if games_dir.exists() and (games_dir / h).exists():
                    game_hash = h
                    break
        if game_hash is None:
            print("  ! game_hash non auto-detecte ; passe --game-hash X "
                  "pour le forcer", file=sys.stderr)

    # Selection des summaries a ingerer
    if args.summary:
        targets = [args.summary]
    elif args.all:
        targets = sorted(SUMMARIES_DIR.glob("batch-*.json"))
    else:
        # Dernier en date
        cand = sorted(SUMMARIES_DIR.glob("batch-*.json"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        if not cand:
            print(f"Aucun summary trouve dans {SUMMARIES_DIR}",
                  file=sys.stderr)
            return 1
        targets = [cand[0]]

    if not targets:
        print("Rien a ingerer", file=sys.stderr)
        return 1

    print(f"Connexion Postgres {user}@{host}:{port}/{db}")
    print(f"game_hash = {game_hash}")
    print(f"{len(targets)} summary(s) a ingerer")

    with psycopg.connect(
            host=host, port=int(port), dbname=db,
            user=user, password=pwd) as conn:
        for path in targets:
            print(f"--- {path.name} ---")
            t0 = time.monotonic()
            try:
                _ingest_summary(conn, path, game_hash)
            except Exception as e:
                print(f"  ERREUR : {e}", file=sys.stderr)
                conn.rollback()
                continue
            print(f"  elapsed: {time.monotonic()-t0:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
