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
  - autoBootExtraire fait UNE fois apres reinject
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
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, TypedDict

# enum_maps : dicts id->nom générés depuis le dump du build courant
# (rl_gen_enum_columns.py). Remplit les colonnes *_name à l'ingest (013).
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from enum_maps import BY_COLUMN as _ENUM_MAPS
except ImportError:
    _ENUM_MAPS = {}

# StepType/GroupType : PAS depuis `enum_maps` (#254b-b). `enum_maps.py` est généré depuis un
# `dump.cs` (artefact gitignoré) et sa table `GROUP_TYPE` est PÉRIMÉE — 102 membres au lieu de
# 104, décalée à partir de 36 (`Ability_Displace` et `EndTurn` y manquent). Elle donnait
# `59 = NormalAttack_AtomicDamage` là où le build courant dit `ZingerAbility` (le vrai
# `NormalAttack_AtomicDamage` est 61) : c'est ce mensonge qui a fixé le `59` de `_ATTACK`
# ci-dessous. `stream_events` lit `data/symbols/<CURRENT>/frida/enums.tsv`, VERSIONNÉE et
# estampillée, et LÈVE sur un membre disparu.
import stream_events as _SE  # noqa: E402
import host_inputs  # noqa: E402  (#273 : entrees gitignorees, resolution tri-etat)
# `gameconfig` au niveau MODULE, et c'est MESURE : il n'importe que la stdlib (aucun cycle avec
# ce fichier) et son import coute 0,09 s -- ses tables sont chargees paresseusement. Un import
# differe sans raison ecrite CACHE la question du cycle au lieu d'y repondre. Le `catalog_inject`
# tardif du corps, lui, garde sa raison propre (il charge le gameconfig a l'import).
import gameconfig as _gc  # noqa: E402


def _enum_name(v: int | None, col: str) -> str | None:
    """Libellé dénormalisé d'une valeur enum (None si inconnue/absente)."""
    if v is None:
        return None
    return _ENUM_MAPS.get(col, {}).get(v)


def _group_name(code: int | None) -> str | None:
    """Libellé GroupType (stream_group.group_name)."""
    if code is None:
        return None
    n = _SE.group_name(code)
    return None if n.startswith("Group#") else n


HOST = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[2]
# #273 : ENTREES gitignorees ecrites HORS de ce checkout -- `ai-traces` par le
# HOST Node (cwd = `frida/` de SON arbre), `rl-batches` par un batch anterieur.
# Resolues par `host_inputs` (env > arbre local > arbre principal git), qui
# LEVE au lieu de rendre une liste vide quand aucun candidat n'existe.
# `rl-batches` reste, lui, une SORTIE de ce script : ecrite dans l'arbre du
# host quand il existe, sinon cree localement (cf. `_summaries_out_dir`).
_TRACES = "frida/data/ai-traces"
_SUMMARIES = "frida/data/rl-batches"
# Seed BC template (skeleton Players/Utilities/mode) + board dumps. TOUS DEUX
# sous data/ (gitignore) = artefacts LOCAUX per-hash, PURGES par tout menage de
# data/ (git clean -fdx, ...). Regeneres en une commande : `python dump_boards.py`
# (cf. #159). NE PAS hardcoder un fallback : absent => erreur actionnable.
SEED_BC = ROOT / "data" / "seed-bc.json"
BOARDS_DIR = ROOT / "data" / "boards"

# PlayerIds lus de Player.Players du seed
PLAYER_ID_HUMAN = 11   # PlayerType=0, TeamId=1
PLAYER_ID_AI = 12      # PlayerType=1, TeamId=2

# Units/MoW that pass buildNormalizedBC's stats filter but throw a managed
# exception when spawned (Initialize / AddUnit) — confirmed via exhaustive
# spawn-probe. The probe caches a per-rank list in
# data/unspawnable_rank{N}.json (see `_load_unspawnable`); this set is the
# fallback when no cache exists. As of rank 17, only necroPlasmancer fails
# (97/98 units + 8/8 MoW spawn fine — no class/faction pattern).
UNSPAWNABLE_FALLBACK = {"necroPlasmancer"}


# ---- Postgres progressive ingest --------------------------------------- #
# Une connection PG ouverte au demarrage du batch ; apres chaque battle on
# lit les nouveaux events du JSONL et on insert immediatement dans la DB.
# Permet de voir les data en temps reel pendant un long run.

try:
    import psycopg  # type: ignore
    from psycopg.types.json import Jsonb  # type: ignore
    _PSYCOPG_OK = True
except ImportError:
    _PSYCOPG_OK = False


# `stream_event.step_name` (migration 013) — dérivé de la table VERSIONNÉE, jamais recopié.
# La copie littérale qui vivait ici datait de `gqfc5mff6c` : depuis que `rnca9r7q6c` a retiré
# `StepType.RestoreArmorInfo` (7), elle décalait de +1 le nom de TOUT pas >= 7. Chaque batch
# ingéré depuis la MAJ a donc écrit en base `AddUnit` pour un `AddMachine`, `RemoveUnit` pour
# un `ChangeStats`, etc. — sans erreur ni trace (#254b-b).
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


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try: return int(v)
    except (TypeError, ValueError): return None


class _IngestCtx(TypedDict, total=False):
    """État partagé pour l'ingestion progressive."""
    conn: Any              # psycopg.Connection
    batch_id: int
    trace_path: Path
    trace_offset: int      # byte position to start next read
    pending_events: dict[int, dict[str, list]]  # runnerId → buckets
    next_gid: int          # compteur global group_id (stream_group, 014)


def _open_progressive_ingest(
    args_ns: argparse.Namespace, seed: int, sid: int,
    trace_path: Path | None,
) -> _IngestCtx | None:
    if not _PSYCOPG_OK:
        print("[ingest] psycopg pas installe — ingestion progressive desactivee",
              file=sys.stderr)
        return None
    # #273 : `.env` est gitignore (secret) -> ABSENT d'un worktree frais. Le
    # message d'avant (« PG_PASSWORD vide ») accusait le CONTENU du fichier ;
    # dans un worktree, le fichier n'existait tout simplement pas et le batch
    # tournait en collectant tout, sans rien ingerer. Les deux causes portent
    # desormais deux messages, et le chemin retenu est NOMME.
    env_res = host_inputs.resolve(".env")
    env = _load_env(env_res.path) if env_res.path else {}
    pwd = env.get("PG_PASSWORD")
    if not pwd:
        if env_res.path is None:
            print("[ingest] PAS MESURE -- aucun .env trouve, ingestion "
                  "desactivee :\n"
                  + "\n".join(f"    [{o}] {p.as_posix()}"
                              for o, p in env_res.candidates),
                  file=sys.stderr)
        else:
            print(f"[ingest] PG_PASSWORD vide dans "
                  f"{env_res.path.as_posix()} -- ingestion desactivee",
                  file=sys.stderr)
        return None
    conn = psycopg.connect(
        host=env.get("PG_HOST", "localhost"),
        port=int(env.get("PG_PORT", "5433")),
        dbname=env.get("PG_DATABASE", "TACTICUS"),
        user=env.get("PG_USER", "postgres"),
        password=pwd,
    )
    # `batch.game_hash` = LE BUILD QUI A EMIS LES ORDINAUX. C'est le seul discriminant qui rend
    # l'historique relisible : `stream_event.step_code` / `stream_group.group_code` sont des
    # ordinaux IMPLICITES, et leur nom depend du build. Sans ce champ, decoder un batch ancien
    # avec la table du build courant rend des noms FAUX -- et rien ne le signale.
    #
    # Ce que le code faisait (#275) : `ents[0].name`, c'est-a-dire le PREMIER repertoire de
    # `games/` par ordre de listage. Sur cette machine c'est `.temp`, un repertoire de travail --
    # l'unique ligne de `tacticus.batch` porte donc `game_hash = '.temp'`, valeur qui ne designe
    # aucun build. Il a fallu inferer le build emetteur par le CONTENU des groupes (aucun
    # `GroupType` 61/48 emis => table a 102 membres, donc un build anterieur aux deux versionnes)
    # pour etablir que ses colonnes `*_name` etaient justes et NE DEVAIENT PAS etre corrigees.
    # Voir `docs/rl/case-275-enum-maps-drift.md` section 4.
    #
    # On retient le repertoire qui porte reellement l'executable, et on ignore `.temp` / tout
    # nom commencant par un point. Aucun repli sur « le premier venu » : une valeur fausse est
    # pire que NULL, qui dit au moins « inconnu ».
    game_hash = None
    games_dir = Path(os.path.expandvars(r"%LOCALAPPDATA%\tacticus\games"))
    if games_dir.exists():
        builds = sorted(d for d in games_dir.iterdir()
                        if d.is_dir() and not d.name.startswith(".")
                        and (d / "Tacticus.exe").is_file())
        if len(builds) == 1:
            game_hash = builds[0].name
        elif builds:
            print("[ingest] %d builds installes (%s) : game_hash laisse NULL -- on ne devine pas"
                  % (len(builds), ", ".join(d.name for d in builds)), file=sys.stderr)
    # Insert batch row
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO tacticus.batch (seed, n_battles, game_hash, config, hooks_sha)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING batch_id
        """, (seed, args_ns.num_battles, game_hash,
              Jsonb(vars(args_ns)), None))
        batch_id = cur.fetchone()[0]
    # Load ability name dicts pour denormalisation a l'ingest.
    with conn.cursor() as cur:
        cur.execute("SELECT ability_id, name FROM tacticus.ref_active_ability")
        for aid, n in cur.fetchall():
            ACTIVE_ABILITY_NAMES[aid] = n
        cur.execute("SELECT ability_id, name FROM tacticus.ref_triggered_ability")
        for aid, n in cur.fetchall():
            TRIGGERED_ABILITY_NAMES[aid] = n
        # Seed du compteur group_id (stream_group, 014) — continue après l'existant.
        cur.execute("SELECT coalesce(max(group_id), 0) + 1 FROM tacticus.stream_group")
        next_gid = cur.fetchone()[0]
    conn.commit()
    print(f"[ingest] connected PG, batch_id={batch_id}, "
          f"game_hash={game_hash}, trace={trace_path}")
    return {
        "conn": conn,
        "batch_id": batch_id,
        "trace_path": trace_path or host_inputs.require(_TRACES) / "_unknown.jsonl",
        "trace_offset": 0,
        "pending_events": {},
        "next_gid": next_gid,
    }


# Ability name dicts (chargees au 1er ingest connection).
ACTIVE_ABILITY_NAMES: dict[int, str] = {}
TRIGGERED_ABILITY_NAMES: dict[int, str] = {}


def _slurp_new_events(ctx: _IngestCtx) -> None:
    """Lit le JSONL depuis trace_offset → end et accumule events_by_runner.
    Met a jour trace_offset. Tolerant aux lignes incomplètes (file en cours
    d'ecriture)."""
    path = ctx["trace_path"]
    if not path.exists():
        return
    size = path.stat().st_size
    offset = ctx["trace_offset"]
    if size <= offset:
        return
    msg_events_by_idx: dict[int, list] = {}
    # Garde l'index existant (nécessaire si message_events arrive APRES
    # message dans le stream — rare mais possible).
    pending = ctx["pending_events"]
    with open(path, "rb") as f:
        f.seek(offset)
        buf = f.read(size - offset)
    # Si la dernière ligne est incomplète, on la garde pour la prochaine fois.
    last_nl = buf.rfind(b"\n")
    if last_nl < 0:
        return  # rien de complet à parser
    chunk = buf[:last_nl + 1].decode("utf-8", errors="replace")
    new_offset = offset + last_nl + 1
    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        evt = rec.get("evt")
        if evt == "message_events":
            mi = rec.get("msgIdx")
            if isinstance(mi, int):
                msg_events_by_idx[mi] = rec.get("events") or []
            continue
        if evt not in ("move_options", "battle_winner", "message"):
            continue
        rid = rec.get("runnerId")
        if not isinstance(rid, int):
            continue
        bucket = pending.setdefault(
            rid, {"move_options": [], "battle_winner": [], "message": []})
        bucket[evt].append(rec)
    # Attach message_events to messages in pending (by msgIdx).
    for rid, bucket in pending.items():
        for m in bucket.get("message", []):
            mi = m.get("msgIdx")
            if isinstance(mi, int) and mi in msg_events_by_idx:
                m.setdefault("_events", [])
                m["_events"].extend(msg_events_by_idx[mi])
                # On consomme — évite la double-affectation au prochain
                # slurp si le même msgIdx réapparaît (it ne peut pas, mais
                # safer).
                msg_events_by_idx[mi] = []
    ctx["trace_offset"] = new_offset


def _ingest_one_battle(ctx: _IngestCtx, battle_rec: dict) -> None:
    """Insere battle + winner + move_options + messages + unit_states +
    stream_events pour ce battle. Drain les events accumules pour son
    runner_id."""
    _slurp_new_events(ctx)
    conn = ctx["conn"]
    runner_id = battle_rec.get("runnerId")
    bucket = ctx["pending_events"].get(runner_id) if runner_id else None

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO tacticus.battle (
                batch_id, idx, runner_id, roster_p, roster_a,
                mow_p, mow_a, board_id, engine_seed, ok,
                final_stage, reached_finished, hit_max_turns,
                turns_count, elapsed_ms, err
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            ) RETURNING battle_id
        """, (
            ctx["batch_id"], battle_rec.get("i"), runner_id,
            battle_rec.get("rosterP"), battle_rec.get("rosterA"),
            battle_rec.get("mowPlayer"), battle_rec.get("mowAi"),
            battle_rec.get("boardId"), battle_rec.get("engineSeed"),
            bool(battle_rec.get("ok")), battle_rec.get("finalStage"),
            bool(battle_rec.get("reachedFinished")),
            bool(battle_rec.get("hitMaxTurns")),
            _safe_int(battle_rec.get("turns")),
            int(float(battle_rec.get("elapsed", 0)) * 1000)
            if battle_rec.get("elapsed") is not None else None,
            battle_rec.get("err"),
        ))
        battle_id = cur.fetchone()[0]
        n_moves = n_msgs = n_units = n_streams = 0

        if bucket:
            # Winner
            wins = bucket["battle_winner"]
            if wins:
                w = wins[-1]
                cur.execute("""
                    UPDATE tacticus.battle
                       SET winner_player_id=%s, winner_team_id=%s,
                           winner_entity_id=%s, outcome=%s,
                           reason_code=%s, reason_name=%s
                     WHERE battle_id=%s
                """, (w.get("winnerPlayerId"), w.get("winnerTeamId"),
                      w.get("winnerEntityId"), w.get("outcome"),
                      w.get("reasonCode"), w.get("reasonName"), battle_id))
            # Move options
            mo_rows = []
            for ev in bucket["move_options"]:
                opts = ev.get("options") or {}
                mo_rows.append((
                    battle_id, ev.get("applySeq"),
                    ev.get("unitEntityId"), ev.get("turn"),
                    ev.get("turnPlayer"), bool(ev.get("ignoreFlags")),
                    bool(opts.get("ignSpecial")), bool(opts.get("ignUnits")),
                    bool(opts.get("isDanger")), opts.get("overrideRange"),
                    bool(opts.get("hasRangeBonus")), ev.get("fireNo"),
                    Jsonb(ev.get("candidates") or []),
                ))
            if mo_rows:
                cur.executemany("""
                    INSERT INTO tacticus.move_options_event (
                        battle_id, apply_seq, unit_entity_id,
                        turn, turn_player, ignore_flags,
                        opt_ign_special, opt_ign_units, opt_is_danger,
                        opt_override_range, opt_has_range_bonus,
                        fire_no, candidates
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s)
                """, mo_rows)
                n_moves = len(mo_rows)
            # Pre-pass : collecter squad_ids + machine_ids vus dans le battle
            # pour classer target_kind sur stream_events. 'unit' si squad,
            # 'machine' si machine, 'tile' sinon.
            battle_squads: set[int] = set()
            battle_machines: set[int] = set()
            for _msg in bucket["message"]:
                _ms = _msg.get("matchState") or {}
                for _u in (_ms.get("units") or []):
                    _sq = _safe_int(_u.get("squadId"))
                    if _sq is not None:
                        battle_squads.add(_sq)
                for _m in (_ms.get("mows") or []):
                    _mid = _safe_int(_m.get("machineId"))
                    if _mid is not None:
                        battle_machines.add(_mid)
            # Messages + unit_states + stream_events
            for msg in bucket["message"]:
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
                    battle_id, msg.get("msgIdx"), msg.get("applySeq"),
                    msg.get("src"), msg.get("msgClass"),
                    _safe_int(msg.get("unitId")), runner_id,
                    _safe_int(ms.get("turn")), _safe_int(ms.get("stage")),
                    ms.get("stageName"), _safe_int(ms.get("playerOnTurn")),
                ))
                message_id = cur.fetchone()[0]
                n_msgs += 1
                # Tiles : present uniquement au 1er message de chaque battle
                # (snapshot statique). Insert idempotent via PK (battle_id, tile_id).
                for t in (ms.get("tiles") or []):
                    cur.execute("""
                        INSERT INTO tacticus.tile_ref (
                            battle_id, tile_id, col, row, tile_def_id,
                            elevation, is_wall, is_temporary,
                            is_boss_platform, is_territory, is_in_fog,
                            room_tile_type
                        ) VALUES (%s, %s, %s, %s, %s,
                                  %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (battle_id, tile_id) DO NOTHING
                    """, (
                        battle_id, _safe_int(t.get("id")),
                        _safe_int(t.get("col")), _safe_int(t.get("row")),
                        t.get("tileDefId"),
                        _safe_int(t.get("elevation")) or 0,
                        bool(t.get("isWall")),
                        bool(t.get("isTemporary")),
                        bool(t.get("isBossPlatform")),
                        bool(t.get("isTerritory")),
                        bool(t.get("isInFog")),
                        _safe_int(t.get("roomTileType")) or 0,
                    ))
                # Unit states from snapshot
                for u in (ms.get("units") or []):
                    pos = u.get("pos") or {}
                    cur.execute("""
                        INSERT INTO tacticus.unit_state (
                            message_id, unit_id, squad_id, col, row,
                            hp, hp_max, owner_id, team_id, visual_id,
                            rank, is_dead
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                                  %s, %s, %s)
                    """, (
                        message_id, _safe_int(u.get("id")),
                        _safe_int(u.get("squadId")),
                        _safe_int(pos.get("col")), _safe_int(pos.get("row")),
                        _safe_int(u.get("hp")), _safe_int(u.get("maxHp")),
                        _safe_int(u.get("ownerId")),
                        _safe_int(u.get("teamId")),
                        u.get("visualId"), _safe_int(u.get("rank")),
                        bool(u.get("isDead")),
                    ))
                    n_units += 1
                # MoW state — 1 row par MachinePlatform (analog unit_state).
                # ms.mows est present si la battle contient des MoW.
                for w in (ms.get("mows") or []):
                    wpos = w.get("pos") or {}
                    cur.execute("""
                        INSERT INTO tacticus.mow_state (
                            message_id, platform_id, machine_id, col, row,
                            hp, hp_max, owner_id, team_id, visual_id,
                            rank, initial_slot, is_dead
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                                  %s, %s, %s, %s)
                    """, (
                        message_id, _safe_int(w.get("id")),
                        _safe_int(w.get("machineId")),
                        _safe_int(wpos.get("col")), _safe_int(wpos.get("row")),
                        _safe_int(w.get("hp")), _safe_int(w.get("maxHp")),
                        _safe_int(w.get("ownerId")),
                        _safe_int(w.get("teamId")),
                        w.get("visualId"), _safe_int(w.get("rank")),
                        _safe_int(w.get("initialSlot")) or 0,
                        bool(w.get("isDead")),
                    ))
                # Stream events (action-only) + arbre des groupes (stream_group,
                # 014). On empile/dépile : group → noeud (push), finish → ferme
                # (pop + ordinal_close), action → reliée au groupe englobant
                # (group_id) ; caster_entity = ancêtre attaque/ability ;
                # weapon_is_melee = Info(arme) du scope d'attaque.
                # Codes GroupType résolus PAR NOM (#254b-b). Le `59` qui était écrit ici
                # portait le commentaire « NormalAttack » : il venait de `enum_maps.GROUP_TYPE`,
                # table périmée où 59 = `NormalAttack_AtomicDamage`. Sur le build courant 59 =
                # `ZingerAbility` et le vrai `NormalAttack_AtomicDamage` vaut 61 — le fallback
                # « 015 » ci-dessous ne s'est donc JAMAIS armé sur une attaque normale ; il
                # s'armait sur les scopes d'une ability sans rapport.
                _g = _SE.group_id
                _ATTACK = (_g("User_UseAbility"), _g("Ability_Attack"),
                           _g("NormalAttack_AtomicDamage"))
                _ACTOR = _ATTACK + (_g("User_MoveUnit"), _g("User_PlaceUnit"))
                _USER = (_g("User_MoveUnit"), _g("User_UseAbility"),
                         _g("User_PlaceUnit"))   # actions user (bornent le fallback Info, 015)
                _NORMAL_ATTACK = _g("NormalAttack_AtomicDamage")
                se_rows = []
                sg_rows: list[list[Any]] = []
                gstack: list[dict[str, Any]] = []
                last_info_melee = None         # 015: dernier Info(arme) de l'action user courante
                for ord_idx, ev in enumerate(msg.get("_events") or []):
                    kind = ev.get("kind")
                    if kind == "group":
                        gcode = _safe_int(ev.get("group"))
                        gent = _safe_int(ev.get("entity"))
                        if gcode in _USER:
                            last_info_melee = None  # nouvelle action user → reset
                        # NB: groupe poussé ci-dessous
                        gid = ctx["next_gid"]
                        ctx["next_gid"] += 1
                        sg_rows.append([
                            gid, message_id, ord_idx, None, len(gstack),
                            gcode, _group_name(gcode), gent,
                            gstack[-1]["gid"] if gstack else None,
                        ])
                        gstack.append({"gid": gid, "code": gcode,
                                       "entity": gent, "melee": None,
                                       "ridx": len(sg_rows) - 1})
                        continue
                    if kind == "finish":
                        if gstack:
                            sg_rows[gstack.pop()["ridx"]][3] = ord_idx
                        continue
                    # kind == "action"
                    step = ev.get("step")
                    step_name = STEP_NAMES.get(step) if step is not None else None
                    tags_raw = ev.get("tags")
                    tags_dict: dict[str, Any] = {}
                    if isinstance(tags_raw, str):
                        try: tags_dict = json.loads(tags_raw) or {}
                        except json.JSONDecodeError: tags_dict = {}
                    elif isinstance(tags_raw, dict):
                        tags_dict = tags_raw

                    def _t(k: str) -> int | None:
                        v = tags_dict.get(k)
                        if v is None:
                            return None
                        try: return int(v)
                        except (TypeError, ValueError): return None

                    # 014 — scope englobant depuis la pile de groupes.
                    group_id = gstack[-1]["gid"] if gstack else None
                    caster_entity = None
                    for fr in reversed(gstack):
                        if fr["code"] in _ACTOR and fr["entity"]:
                            caster_entity = fr["entity"]
                            break
                    if step == _SE.step_id("Info") and "Attack_Weapon_IsMelee" in tags_dict:
                        _mv = _t("Attack_Weapon_IsMelee")
                        last_info_melee = _mv  # 015: fallback message-level (borné action user)
                        for fr in reversed(gstack):
                            if fr["code"] in _ATTACK:
                                fr["melee"] = _mv
                                break
                    melee_val = None
                    for fr in reversed(gstack):
                        if fr["melee"] is not None:
                            melee_val = fr["melee"]
                            break
                    # 015: fallback pour les ~3% (NormalAttack dont le Info est dans
                    # un scope frère/fermé, non-ancêtre) — gardé aux hits sous un
                    # scope `NormalAttack_AtomicDamage` pour ne pas toucher ability/MoW.
                    if melee_val is None and any(fr["code"] == _NORMAL_ATTACK for fr in gstack):
                        melee_val = last_info_melee

                    # 015: classification du degat (UnitDamaged). MoW avant ability
                    # (les MoW ont aussi un active_ability mais c'est de l'artillerie).
                    dmg_kind = None
                    if step == _SE.step_id("UnitDamaged"):
                        _atk = _t("Attacker_Id")
                        if _t("Effect_Type") is not None:
                            dmg_kind = "effect"
                        elif melee_val == 1:
                            dmg_kind = "normal_melee"
                        elif melee_val == 0:
                            dmg_kind = "normal_ranged"
                        elif _atk is not None and _atk in battle_machines:
                            dmg_kind = "mow_artillery"
                        elif _t("Active_Ability_Type") is not None:
                            dmg_kind = "ability"
                        else:
                            dmg_kind = "unknown"

                    entity_id = _safe_int(ev.get("entity"))
                    target_kind = None
                    if entity_id is not None:
                        if entity_id in battle_squads:
                            target_kind = "unit"
                        elif entity_id in battle_machines:
                            target_kind = "machine"
                        else:
                            target_kind = "tile"
                    se_rows.append((
                        message_id, ord_idx, kind, step, step_name, None,
                        entity_id, target_kind,
                        Jsonb(tags_dict) if tags_dict else None,
                        # Hot columns extraites
                        _t("UnitStats_RemainingHealth"),
                        _t("UnitStats_MaxHealth"),
                        _t("UnitStats_RemainingArmor"),
                        _t("UnitStats_MaxArmor"),
                        _t("UnitStats_NumberOfMembers"),
                        _t("UnitStats_MaxMembers"),
                        _t("UnitStats_Attack"),
                        _t("UnitStats_Range"),
                        _t("UnitStats_Movement"),
                        _t("UnitStats_ActiveAbility_Id"),
                        _t("UnitStats_ActiveAbility_RemainingCooldownTurns"),
                        _t("UnitStats_TriggeredAbility_Id"),
                        _t("Effect_Id"),
                        _t("Effect_Type"),
                        _t("Effect_SourceId"),
                        _t("Effect_CurrentLevel"),
                        _t("Effect_RemainingTurns"),
                        _t("Effect_SourceActiveAbility"),
                        _t("Effect_SourceTriggeredAbility"),
                        _t("Unit_Owner_Id"),
                        # 012 — attribution
                        _t("Attacker_Id"),
                        _t("Amount"),
                        _t("Attack_WasMemberKilled"),
                        _t("Target_Id"),
                        _t("Caster_Id"),
                        _t("Active_Ability_Type"),
                        _t("Killed_Unit_Id"),
                        # 012 — combat quality
                        _t("Attack_DidCrit"),
                        _t("Attack_DidBlock"),
                        _t("Attack_DidEvade"),
                        _t("Attack_WasOverkill"),
                        _t("Attack_Is_First_Hit"),
                        _t("DamageProfileType"),
                        melee_val,  # 014 : Info(arme) du scope d'attaque (au lieu du tag absent)
                        # 012 — ability / state
                        _t("Passive_Ability_Type"),
                        _t("UnitStats_Transformed"),
                        # 012 — lifecycle
                        _t("Unit_WasOverkilled"),
                        _t("Unit_IsDying"),
                        _t("Unit_IsSummoned"),
                        _t("Unit_SpawnSource"),
                        _t("Unit_Parent_Id"),
                        # 013 — libellés enum dénormalisés (depuis enum_maps)
                        _enum_name(_t("Effect_Type"), "effect_type"),
                        _enum_name(_t("Active_Ability_Type"), "active_ability_type"),
                        _enum_name(_t("Passive_Ability_Type"), "passive_ability_type"),
                        _enum_name(_t("DamageProfileType"), "damage_profile_type"),
                        _enum_name(_t("Unit_SpawnSource"), "unit_spawn_source"),
                        # 014 — arbre des groupes
                        group_id, caster_entity,
                        # 015 — classification du dégât
                        dmg_kind,
                    ))
                # stream_group AVANT stream_event (FK group_id → stream_group ;
                # parents insérés avant enfants car gid monotone en ordre d'ouverture).
                if sg_rows:
                    cur.executemany("""
                        INSERT INTO tacticus.stream_group (
                            group_id, message_id, ordinal_open, ordinal_close,
                            depth, group_code, group_name, entity, parent_group_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, sg_rows)
                if se_rows:
                    cur.executemany("""
                        INSERT INTO tacticus.stream_event (
                            message_id, ordinal, kind,
                            step_code, step_name, group_code,
                            entity_id, target_kind, tags,
                            hp_remaining, hp_max, armor_remaining, armor_max,
                            members_current, members_max, attack, attack_range,
                            movement, active_ability_id, active_ability_cooldown,
                            triggered_ability_id, effect_id, effect_type,
                            effect_source_id, effect_level, effect_turns_remaining,
                            effect_source_active_ability,
                            effect_source_triggered_ability, unit_owner_id,
                            attacker_id, amount, member_killed, target_id,
                            caster_id, active_ability_type, killed_unit_id,
                            did_crit, did_block, did_evade, was_overkill,
                            is_first_hit, damage_profile_type, weapon_is_melee,
                            passive_ability_type, transformed,
                            unit_was_overkilled, unit_is_dying, unit_is_summoned,
                            unit_spawn_source, unit_parent_id,
                            effect_type_name, active_ability_type_name,
                            passive_ability_type_name, damage_profile_type_name,
                            unit_spawn_source_name,
                            group_id, caster_entity, damage_kind
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s
                        )
                    """, se_rows)
                    n_streams += len(se_rows)
                # Ability state changes — log par event qui mentionne une
                # active OR triggered ability (signal RL : "puis-je
                # utiliser cette ability ?" via CanStillBeUsed +
                # cooldown_remaining + is_disabled + blocked).
                as_rows = []
                for ord_idx, ev in enumerate(msg.get("_events") or []):
                    entity_id = _safe_int(ev.get("entity"))
                    if entity_id is None or (
                        entity_id not in battle_squads
                        and entity_id not in battle_machines
                    ):
                        continue  # only track for units (squads) or machines
                    tags_raw = ev.get("tags")
                    if isinstance(tags_raw, str):
                        try: t = json.loads(tags_raw) or {}
                        except json.JSONDecodeError: t = {}
                    elif isinstance(tags_raw, dict):
                        t = tags_raw
                    else:
                        continue
                    def _ti(k: str) -> int | None:
                        v = t.get(k)
                        if v is None: return None
                        try: return int(v)
                        except (TypeError, ValueError): return None
                    def _tb(k: str) -> bool | None:
                        v = t.get(k)
                        if v is None: return None
                        return bool(int(v)) if str(v).isdigit() else bool(v)
                    # Active ability change
                    aaid = _ti("UnitStats_ActiveAbility_Id")
                    if aaid is not None:
                        as_rows.append((
                            message_id, battle_id,
                            _safe_int(msg.get("applySeq")), ord_idx,
                            entity_id, "active", aaid,
                            ACTIVE_ABILITY_NAMES.get(aaid),
                            _ti("UnitStats_ActiveAbility_RemainingCooldownTurns"),
                            _tb("UnitStats_ActiveAbility_CanStillBeUsed"),
                            _tb("UnitStats_ActiveAbility_IsDisabled"),
                            _tb("UnitStats_ActiveAbility_Blocked"),
                            _ti("UnitStats_ActiveAbility_Blocked_ReasonEffectType"),
                            _ti("UnitStats_ActiveAbility_Level"),
                            _ti("UnitStats_ActiveAbility_VariableMultiplierPercentage"),
                            None,  # has_enough_ammo (triggered-only)
                        ))
                    # Triggered ability change
                    taid = _ti("UnitStats_TriggeredAbility_Id")
                    if taid is not None:
                        as_rows.append((
                            message_id, battle_id,
                            _safe_int(msg.get("applySeq")), ord_idx,
                            entity_id, "triggered", taid,
                            TRIGGERED_ABILITY_NAMES.get(taid),
                            None, None, None, None, None,  # active-only fields
                            _ti("UnitStats_TriggeredAbility_Level"),
                            _ti("UnitStats_TriggeredAbility_VariableMultiplierPercentage"),
                            _tb("UnitStats_TriggeredAbility_EnoughAmmo"),
                        ))
                if as_rows:
                    cur.executemany("""
                        INSERT INTO tacticus.ability_state_change (
                            message_id, battle_id, apply_seq, ordinal,
                            squad_id, kind, ability_id, ability_name,
                            cooldown_remaining, can_still_be_used,
                            is_disabled, is_blocked, blocked_reason_effect_type,
                            level, variable_mult_pct, has_enough_ammo
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, as_rows)
            # Drop processed bucket (free memory)
            ctx["pending_events"].pop(runner_id, None)

    conn.commit()
    print(f"  [ingest] battle_id={battle_id} mo={n_moves} msg={n_msgs} "
          f"us={n_units} se={n_streams}")


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


# --- Mode DRAIN cote host (#285) : attendre la levee, ici et NULLE PART AILLEURS --
#
# Quand le host est en DRAIN il refuse la CREATION de runner (et elle seule) avec un
# message portant cette sous-chaine. La conduite correcte est d'ATTENDRE puis de
# reessayer : un drain dure le temps d'une fenetre de maintenance, pas d'une session.
#
# POURQUOI L'ATTENTE VIT ICI, DANS `_rpc`.
# `tests/conftest.py` savait deja attendre sur le cap de runners, mais les probes
# AUTONOMES, eux, recopiaient chacun leur propre marqueur et leur propre boucle
# (`probe_119`, `probe_170`...) -- et une dizaine d'autres appellent `initAndStart`
# en direct sans aucune attente. Cabler le drain probe par probe, c'etait recopier
# le motif une fois de plus et laisser le suivant l'oublier.
#
# `_rpc` est LE point de passage commun : tout le monde y transite, y compris
# `rl_duel.py build` -- donc un probe qui lance `rl_duel build` en SOUS-PROCESSUS
# herite de l'attente sans une ligne de code, le sous-processus bloquant sur son
# propre `_rpc`. Un seul endroit a maintenir, aucun appelant a modifier.
#
# CE QUI RESTE VRAI SI LE DRAIN NE SE LEVE PAS : on rend le dict d'erreur TEL QUEL.
# Le message continue donc de remonter a l'appelant (`resp["error"]`), qui le leve ou
# l'imprime comme avant. L'attente ne masque jamais le refus, elle le DIFFERE.
#
# Portee volontairement etroite : seul le marqueur DRAIN declenche l'attente. Le cap
# de runners (« runner cap reached ») garde la sienne, en amont, dans les appelants
# qui savent quoi liberer -- ici on ne saurait pas quel runner disposer.
_DRAIN_MARKER = "runner creation paused"
_DRAIN_WAIT_S = float(os.environ.get("TACTICUS_DRAIN_WAIT_S", "300"))
_DRAIN_POLL_S = float(os.environ.get("TACTICUS_DRAIN_POLL_S", "15"))


def _rpc(sid: int, method: str, args: list | None = None,
         timeout: float = 60.0) -> dict:
    body = {"method": method, "args": args or [], "timeout": int(timeout * 1000)}
    resp = _http(f"/api/scripts/{sid}/rpc", "POST", body, timeout=timeout + 5)

    # ---- Attente de la levee du drain -------------------------------------------
    #
    # L'ANNONCE PRECEDE L'ATTENTE, et ce n'est pas cosmetique.
    #
    # Un appelant impatient -- `subprocess.run(..., timeout=60)`, un agent qui borne
    # son appel, un pytest sous `--timeout` -- sera TUE pendant qu'on patiente. S'il
    # n'a rien lu a ce moment-la, il ne rapporte qu'un « timeout » opaque : l'attente
    # aurait alors CONVERTI un refus parfaitement explicite en panne muette, soit
    # exactement le defaut #263 (`applyAction` rendait `ok:false` sans message, deux
    # agents y ont perdu des mesures) -- reintroduit par le remede.
    #
    # On imprime donc le message COMPLET sur stderr des le premier refus, AVANT le
    # premier sleep. Un `subprocess.run` tue par timeout expose quand meme ce qui a
    # ete capture (`TimeoutExpired.stderr`) : la raison survit a la mort du process.
    # Corollaire : la duree d'attente devient un reglage de CONFORT, plus un risque
    # de perte d'information -- quel que soit le budget de l'appelant, il sait.
    waited = 0.0
    announced = False
    while _DRAIN_MARKER in str(resp.get("error") or ""):
        if not announced:
            print(f"[drain] {resp.get('error')}", file=sys.stderr, flush=True)
            print(f"[drain] methode refusee : {method} -- attente jusqu'a "
                  f"{_DRAIN_WAIT_S:.0f}s, essai toutes les {_DRAIN_POLL_S:.0f}s. "
                  f"Poser TACTICUS_DRAIN_WAIT_S=0 pour echouer immediatement.",
                  file=sys.stderr, flush=True)
            announced = True
        if waited >= _DRAIN_WAIT_S:
            break
        time.sleep(_DRAIN_POLL_S)
        waited += _DRAIN_POLL_S
        resp = _http(f"/api/scripts/{sid}/rpc", "POST", body, timeout=timeout + 5)
        if _DRAIN_MARKER not in str(resp.get("error") or ""):
            print(f"[drain] leve apres {waited:.0f}s -- {method} reprend",
                  file=sys.stderr, flush=True)
    return resp


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


def bind_ambient_rpc(sid: int):
    """LIE le transport RPC AMBIANT de `engine.runner.snapshot` a la session `sid` (#363). Rend le
    transport PRECEDENT, pour restauration.

    POURQUOI CE HELPER EST ICI, ET POURQUOI IL EST OBLIGATOIRE DANS TOUT MONTAGE QUI GREFFE
    (#448-r3-r1-r1). `load_state` ne seede `UnitContext.{passive,active,config_active,triggered}_
    abilities` que si le canal `unitAbilityStates` a parle -- transport ambiant lie, ou payload
    passe en argument. Sans canal, `triggers/dispatch/core.py::collect_triggered_abilities`
    retombe sur `gameconfig.unit(<greffon>)`, qui ne porte PAS la greffe : le port est AMPUTE et
    toute assertion NEGATIVE passe a vide, EN VERT. Mesure : `probe_448_r2b` rendait 0 echec en CLI
    contre 3 sous pytest, le seul ecart etant ce transport (que `tests/conftest.py::live_session`
    lie et qu'un lancement direct ne liait pas).

    Le montage vivait en COPIE dans chaque probe. Il vit ici, a cote de `_rpc`/`_resolve_session`
    que tout probe importe deja -- un seul foyer, une seule signature.

    Signature attendue par le foyer : `rpc(method, body=None, timeout=...)` -> resultat DEBALLE."""
    from engine.runner.snapshot import bind_live_rpc

    def _ambient(method: str, body=None, timeout: float = 60):
        r = _rpc(sid, method, [body if body is not None else {}], timeout=timeout)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}

    return bind_live_rpc(_ambient)


def _ensure_ai_trace(sid: int) -> dict:
    status = _rpc(sid, "aiTraceStatus", [], timeout=5).get("result") or {}
    for lvl in ("L1", "L2"):
        if not (status.get("enabled") or {}).get(lvl):
            _rpc(sid, "aiTraceEnable", [lvl], timeout=5)
    return _rpc(sid, "aiTraceStatus", [], timeout=5).get("result") or {}


def _dir_size_bytes(p: Path | None) -> int | None:
    """Octets de `*.jsonl` sous `p`. `None` = PAS MESURE (repertoire absent).

    #273 : rendait `0` pour « repertoire absent » comme pour « repertoire vide ».
    Le delta before/after imprime en fin de batch valait alors `0 -> 0`, lu comme
    « le host n'a rien ecrit » alors qu'on ne regardait pas au bon endroit.
    """
    if p is None or not p.exists():
        return None
    return sum(f.stat().st_size for f in p.glob("*.jsonl") if f.is_file())


# ---- BC + pool setup ---------------------------------------------------- #

def _load_seed_bc(path=None) -> dict:
    """Seed BC template (data/seed-bc.json par defaut). `path` (optionnel) = surcharge vers un
    seed BC CUSTOM sur disque -- sert a valider un porteur HORS du pool capture (ex. SavageEchoes
    /bloodTerminator, absent du seed BC) en injectant son bloc Unit dans une copie du seed BC.
    N'ecrit JAMAIS le seed BC partage (le custom vit dans un fichier a part).

    #254 -- le second catalogue (`BC.Abilities`) est RE-SYNTHETISE depuis le gameconfig VIVANT a
    chaque chargement. Le seed BC est la capture d'UN build ; `gameconfig.py` lit le fichier
    VIVANT, donc celui du build COURANT. Une MAJ qui AJOUTE une variable/constante a une ability
    laisse la capture en arriere, et le natif neuf la lit :
    `IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` LEVE sur cle absente ->
    « system error » au cast, ou des `initAndStart` si la cle est lue a la construction du trigger
    d'un PASSIF. Detail, mesures et decompile : `catalog_inject.refresh_ability_configs`.

    #27-4 -- le TROISIEME catalogue (`BC.Utilities`, les poids nommes de l'IA) est re-synthetise de
    la MEME facon, et pour la meme raison. Une MAJ qui ajoute une ability ajoute ses poids ; le
    playbook neuf les lit par
    `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetUtilityValue`, qui
    sur cle absente LOGUE et rend `Fix64(0)`. La degradation est SILENCIEUSE (pas d'exception) : le
    terme custom d'une ability neuve vaut 0 cote natif comme cote moteur, donc INVALIDABLE.
    Detail, mesures et decompile : `catalog_inject.refresh_ai_utilities`.

    #254-bc -- le PREMIER catalogue (`BC.Units`) n'est PAS rattrape, et sa peremption etait MUETTE.
    C'est lui que `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig` parcourt et dont
    `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` tire les passifs montes :
    une entree perimee deploie le kit d'un ANCIEN build, sans erreur ni trace. On ne le rafraichit
    pas ici (un re-dump change le pool spawnable ET les stats de reference de tous les tests live --
    arbitrage ouvert), mais on le DIT a chaque chargement. Detail : `catalog_inject.stale_unit_report`
    et `docs/rl/case-254-bc-bloc-units-perime.md`."""
    p = Path(path) if path else SEED_BC
    if not p.exists():
        raise RuntimeError(
            f"seed BC absent: {p} — artefact live per-hash purge de data/. "
            f"Regenere-le : `python dump_boards.py` (capture live via dumpBattleConfig).")
    bc = json.loads(p.read_text(encoding="utf-8"))
    import catalog_inject                                       # import tardif : charge le gameconfig
    # #375 -- SIDECAR D'EPINGLAGE. Le rattrapage ci-dessus ECRASAIT en silence toute variable
    # deliberement patchee par une fixture : mesure du 2026-07-31, `LightImUp.minDmg[49]` ecrit a
    # `20000` dans un seed BC custom, relu a `831` ici meme. Le regime discriminant de #369 n'a
    # donc JAMAIS ete joue, sans le moindre message. `<seed-bc>.pins.json` nomme les configs a ne
    # pas rattraper ; une epingle qui ne designe RIEN leve, elle ne se tait pas.
    pins = catalog_inject.read_pins(p) if path else []
    if pins:
        node = bc.get("Abilities") or {}
        orphans = [k for k in pins
                   if k.split("/", 1)[-1] not in (node.get(k.split("/", 1)[0]) or {})]
        if orphans:
            raise RuntimeError(
                f"seed BC {p}: epingles introuvables dans BC.Abilities: {orphans} "
                f"(sidecar {catalog_inject.pins_path(p)})")
        print(f"[seed-bc] configs d'ability EPINGLEES (patch delibere, #375), non rattrapees: "
              f"{pins}", file=sys.stderr)
    # #380 -- AXE SYMETRIQUE. Le rattrapage ne fait pas que reecrire des valeurs : sa 2e boucle
    # POSE toute config qu'une entree `Units` reclame au gameconfig. Une fixture dont le point EST
    # l'absence d'une config voit donc son bras negatif comble, sans un mot (mesure : le bras A de
    # `probe_226_seed_bc_ability_configs` repartait avec `SavageEchoes` en place, donc identique a
    # ses deux bras temoins). `withheldAbilityConfigs` NOMME ces absences. Une retenue qui ne
    # retient rien -- la config est en fait presente -- LEVE, comme une epingle orpheline : c'est
    # un montage faux, pas un no-op.
    withheld = catalog_inject.read_withheld(p) if path else []
    if withheld:
        node = bc.get("Abilities") or {}
        present = [k for k in withheld
                   if k.split("/", 1)[-1] in (node.get(k.split("/", 1)[0]) or {})]
        if present:
            raise RuntimeError(
                f"seed BC {p}: retenues CONTRADICTOIRES -- ces configs sont presentes dans "
                f"BC.Abilities: {present} (sidecar {catalog_inject.pins_path(p)})")
        print(f"[seed-bc] configs d'ability RETENUES (absence deliberee, #380), non comblees: "
              f"{withheld}", file=sys.stderr)
    # #448-r3-r1-r1-r1 -- TROISIEME sidecar, meme fichier, meme raison. Un seed BC custom peut
    # avoir ete GREFFE par un AUTRE processus ; le registre de greffes est un fait de PROCESSUS,
    # donc ici il est vide et `snapshot._refuse_if_grafted` reste muet -- alors que c'est
    # exactement le regime ou le port serait AMPUTE (les classes greffees non montees, et toute
    # assertion NEGATIVE passant a vide, en vert). On RE-DECLARE ce que le fichier porte : le
    # processus qui charge devient aussi informe que celui qui a greffe, sans avoir a le savoir.
    if path:
        n_greffes = catalog_inject.redeclare_grafts_from(p)
        if n_greffes:
            print(f"[seed-bc] {n_greffes} greffe(s) ESTAMPEE(S) dans ce seed BC re-declaree(s) "
                  f"pour ce processus (#448-r3-r1-r1-r1) : "
                  f"{catalog_inject.read_grafts(p)}", file=sys.stderr)
    refreshed, added = catalog_inject.refresh_ability_configs(bc, skip=pins, withhold=withheld)
    if refreshed or added:
        print(f"[seed-bc] configs d'ability re-synthetisees depuis le gameconfig courant: "
              f"{len(refreshed)} rafraichies {refreshed} / {len(added)} ajoutees {added}",
              file=sys.stderr)
    u_add, u_chg, u_del = catalog_inject.refresh_ai_utilities(bc)
    if u_add or u_chg or u_del:
        print(f"[seed-bc] poids d'utilite re-synthetises depuis le gameconfig courant: "
              f"{len(u_add)} ajoutes / {len(u_chg)} changes / {len(u_del)} retires "
              f"| ajoutes={u_add} | changes={u_chg} | retires={u_del}",
              file=sys.stderr)
    # #254-bc -- ce catalogue-la n'est PAS rattrape : il est seulement DIT. Le taire, c'est
    # laisser un runner deployer un kit d'un ancien build sans que personne le sache (cout mesure :
    # #354 a lu l'inertie qui en decoule comme un fait du jeu, et supprime 3 vecteurs valides).
    stale = catalog_inject.stale_unit_report(bc)
    if stale:
        print(f"[seed-bc] {stale}", file=sys.stderr)
    # #254-bc-r1 -- l'AUTRE axe du meme silence. `stale_unit_report` parle des entrees PRESENTES qui
    # ont derive ; celui-ci parle de ce que la capture n'a PAS DU TOUT. Il se TAIT tant que l'ecart
    # est exactement celui qui est epingle (donc zero bruit en regime nominal) : il ne parle que
    # quand le gameconfig a ajoute une unite depuis, ou qu'une epinglee est entree au catalogue.
    # Mesure du gisement : l'ecart est passe de 17 a 21 unites `lineup` sans que rien ne le dise.
    gap = catalog_inject.catalog_gap_report(bc)
    if gap:
        print(f"[seed-bc] {gap}", file=sys.stderr)
    return bc


def _load_unspawnable(rank: int) -> tuple[set[str], set[str]]:
    """Return (unspawnable_units, unspawnable_mow) for `rank` — units/MoW that
    pass buildNormalizedBC's stats filter but throw a managed exception at spawn.
    Loaded from the probed cache data/unspawnable_rank{rank}.json (produced by
    the exhaustive spawn-probe); falls back to UNSPAWNABLE_FALLBACK when absent."""
    p = ROOT / "data" / f"unspawnable_rank{rank}.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return (set(d.get("unspawnableUnits") or []),
                    set(d.get("unspawnableMow") or []))
        except Exception:
            pass
    return set(UNSPAWNABLE_FALLBACK), set()


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


def _board_supports_mow(dump: dict) -> bool:
    """True if the board's paired SPS carries a Machine-of-War slot for BOTH
    sides — i.e. the TWPI=0 and TWPI=1 groups both have
    MachineOfWarPosition != 0/None.

    Why it matters: a MoW only deploys if SpawnPointSetConfiguration.
    GroupForPlayer finds a group for the owner's TWPI AND a platform exists
    at the MoW slot (AddMachineOfWarPlatformOperation reads MachineOfWarPosition).
    Without a MoW slot, AddMachineOperation.GetPlatform fails and the MoW is
    silently dropped. Verified empirically: 100% of pvp/syncPvp boards qualify,
    only ~29% of `global` boards do."""
    inner = dump.get("board") or {}
    sps_idx = dump.get("spawnPointsSet")
    sets = inner.get("SpawnPointSets") or []
    if not isinstance(sps_idx, int) or not (0 <= sps_idx < len(sets)):
        return False
    mow_pos = {g.get("TeamWithPlayerIndex"): g.get("MachineOfWarPosition")
               for g in (sets[sps_idx].get("SpawnPointGroups") or [])}
    return (mow_pos.get(0) not in (0, None)
            and mow_pos.get(1) not in (0, None))


def _load_board_pool(kind: str, roster_size: int,
                     require_mow: bool = False) -> list[dict]:
    """Load every dumped board of the given kind. Filters out boards
    whose paired SPS doesn't provide enough TWPI=0 + TWPI=1 spawn points
    (we need `roster_size` per side). PvP boards have the right paired
    SPS for 5v5 by definition, so this is mostly defensive.

    If `require_mow`, additionally drop boards that don't accept a MoW on
    both sides (see `_board_supports_mow`) — otherwise a MoW battle on such
    a board would silently lose its MoW at deployment. Drops are logged."""
    pool_dir = BOARDS_DIR / kind
    if not pool_dir.exists():
        raise FileNotFoundError(f"No board dump dir {pool_dir}")
    out: list[dict] = []
    dropped_pts = 0
    dropped_mow = 0
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
        if not (twpi_counts.get(0, 0) >= roster_size
                and twpi_counts.get(1, 0) >= roster_size):
            dropped_pts += 1
            continue
        if require_mow and not _board_supports_mow(dump):
            dropped_mow += 1
            continue
        out.append(dump)
    if require_mow:
        print(f"[board-pool] {kind}: {len(out)} MoW-capable boards kept "
              f"(dropped {dropped_mow} without MoW slot, "
              f"{dropped_pts} without enough spawn points)")
    return out


# ---- Items equipes : le canal CRIT/BLOCK (#419-r5) ---------------------- #
#
# Les 4 stats CritChance/CritDamage/BlockChance/BlockDamage ne sont PAS dans
# la base d'un heros. Mesure sur le gameconfig du build courant : `adeptMorvenn`
# porte `stats = {Health, Damage, FixedArmor}` -- aucune stat crit/block -- et
# `itemSlots = ["I_Crit", "I_Block", "I_Booster_Block"]`. Elles arrivent
# EXCLUSIVEMENT par les ITEMS equipes, que
# `IdunMetaLogic.Formulas.StatsFormula$$StatsFor` fusionne
# (`IdunMetaLogic.Formulas.UnitDynamicStats$$Merge`) a la base de progression.
#
# `buildNormalizedBC` ECRASE les 8 stats du seed BC par la sortie de
# `IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor`. Appelee
# avec une liste d'items VIDE, celle-ci rend legitimement 0 sur les 4 stats
# crit/block. Le seed portait 352 de CritDamage pour `adeptMorvenn` : le
# template normalise portait 0.
#
# CONSEQUENCE, et c'est elle qui rend ce defaut couteux :
# `IdunBattle.Core.Services.DamageCalculations$$CouldCrit` est
# `GetStat(9) > 0 && GetStat(10) > 0` -- donc AUCUN crit n'etait possible, NI
# cote natif NI cote port, sur AUCUNE unite d'AUCUN runner. Tout accord
# natif-port sur `RollCritical`, sur le gate « never crit » ou sur le canal
# block etait un accord en REGIME DEGENERE : les deux cotes rendaient zero.
# Le meme raisonnement vaut pour le block
# (`IdunBattle.Core.Services.DamageCalculations$$CouldBlock`).
#
# Le regime « heros rank 17 / level 50 / 5 etoiles SANS aucun item » n'existe
# pas dans le jeu. Equiper est donc le regime FIDELE, et l'ancien comportement
# reste joignable par `equip_items=False` (temoin, non-regression).

# LE DEFAUT EST << EQUIPER >> DEPUIS #419-r6 -- c'est le regime FIDELE, et l'ancien etait
# DEGENERE, pas seulement different.
#
# Un heros rank 17 / level 50 / 5 etoiles SANS aucun item n'existe pas dans le jeu. Tant que le
# defaut etait `False`, `CouldCrit` (`GetStat(9) > 0 && GetStat(10) > 0`) etait FAUX sur les 106
# unites du seed, cote NATIF COMME PORT : tout accord sur `RollCritical`, sur le gate
# << never crit >> et sur le block etait un accord en regime degenere -- les deux cotes rendaient
# zero. Voir `docs/rl/case-419-r5-canal-crit-block-muet.md`.
#
# La bascule a un rayon de souffle MESURE (les deux regimes joues sur le meme fichier, temoin
# `TACTICUS_BIS_ITEMS=0`), documente dans `docs/rl/case-419-r6-bascule-du-defaut.md`. Les
# fichiers qui se degradaient ne retenaient qu'un coup << propre >> (sans crit ni block) et le
# trouvaient SANS RIEN DEMANDER tant que le canal etait muet : leur montage est desormais
# EXPLICITE (`NO_NOISE` sur les QUATRE faces -- `--crit`/`--block-player` n'epinglent que les
# p-units, `--crit-target`/`--block-target` que les a-units).
#
# Le regime d'AVANT reste joignable, et c'est ce qui rend la bascule mesurable :
# `equip_items=False`, ou `TACTICUS_BIS_ITEMS=0` pour l'imposer globalement sans toucher au code.
_EQUIP_ITEMS_PAR_DEFAUT = True

_BIS_CACHE: dict[tuple, dict] = {}

# Rarete cible de la normalisation -- `ItemRarity` du build : 0 Common,
# 1 Uncommon, 2 Rare, 3 Epic, 4 Legendary, 5 Mythic (`ITEM_RARITY_NAMES` de
# `frida/hooks/features/normalize-bc/items-catalog.ts`). Sert AUX DEUX
# usages : `targetRarity` de `buildNormalizedBC` et le plafond du picker
# d'items -- un seul regime cible, une seule constante.
_TARGET_RARITY = 5


def _bis_item_specs(sid: int, base_bc: dict, rarity_cap: int = _TARGET_RARITY,
                    exclude_relics: bool = True) -> dict:
    """`itemSpecs` Best-In-Slot pour les unites du BC, via le RPC `previewBis`.

    `previewBis` (`frida/hooks/features/normalize-bc/items-catalog.ts`
    `buildBisItemSpecs`) lit `gameConfig.items` + `gameConfig.units.lineup`,
    et choisit par slot l'item de plus haute rarete (<= `rarity_cap`), puis
    starLvl, puis nombre de niveaux -- au niveau MAX.

    La faction vient du gameconfig (`FactionId`) : le picker s'en sert pour
    ecarter les items a `allowedFactions` restreint. Une unite sans
    `FactionId` (les npc) est simplement omise -- elle n'a de toute facon
    aucune entree `lineup`, donc aucun slot.

    Un echec du RPC LEVE. Retomber en silence sur « pas d'items » rendrait
    EXACTEMENT le regime degenere que ce chemin supprime, et un appelant
    lirait ce zero comme une mesure (cf. l'invariant `data/` tri-etat).
    """
    ids = tuple(sorted(u["Id"] for u in (base_bc.get("Units") or [])
                       if u.get("Id")))
    key = (sid, ids, rarity_cap, exclude_relics)
    cached = _BIS_CACHE.get(key)
    if cached is not None:
        return cached

    units = []
    for uid in ids:
        cfg = _gc.unit(uid) or {}
        faction = cfg.get("FactionId")
        if faction is None:
            continue          # npc : aucune entree `lineup`, aucun slot
        units.append({"unitId": uid, "faction": faction})

    if not units:
        raise RuntimeError(
            "_bis_item_specs : aucune unite du BC n'a de FactionId au "
            "gameconfig -- le canal crit/block resterait MUET (cf. #419-r5). "
            "Passer equip_items=False pour assumer explicitement ce regime.")

    res = _rpc(sid, "previewBis",
               [{"units": units, "rarityCap": rarity_cap,
                 "excludeRelics": exclude_relics}],
               timeout=60).get("result") or {}
    if not res.get("ok"):
        raise RuntimeError(
            f"previewBis a echoue : {res.get('err', '?')!r}. Sans itemSpecs, "
            f"CritChance/CritDamage/BlockChance/BlockDamage valent 0 sur "
            f"TOUTES les unites et le crit devient structurellement "
            f"impossible (#419-r5). Si le catalogue d'items n'est pas "
            f"capture, faire une amorce ; pour assumer le regime sans items, "
            f"passer equip_items=False.")
    specs = res.get("itemSpecs") or {}
    # Un `ok: true` NE SUFFIT PAS -- `previewBis` rend `ok: true` avec des specs VIDES quand le
    # catalogue est la mais qu'aucun slot n'est pourvu (`gameConfig.units.lineup` non resolu,
    # cap de rarete trop bas, filtres de faction). Accepter ce vide, ce serait retomber dans le
    # regime degenere EXACTEMENT comme avant, sans la moindre trace : un zero se lirait comme
    # une mesure. On exige donc qu'au moins une unite reparte AVEC des items.
    pourvues = sum(1 for v in specs.values() if v)
    if pourvues == 0:
        raisons = sorted({it.get("reason") for p in (res.get("perUnit") or [])
                          for it in (p.get("items") or [])
                          if it.get("configId") is None and it.get("reason")})
        raise RuntimeError(
            f"previewBis a rendu ok=true mais AUCUNE unite equipee "
            f"({len(specs)} entree(s), 0 pourvue) -- raisons : {raisons}. "
            f"Le canal CritChance/CritDamage/BlockChance/BlockDamage resterait "
            f"MUET et le crit structurellement impossible (#419-r5). Pour "
            f"assumer explicitement ce regime, passer equip_items=False.")
    _BIS_CACHE[key] = specs
    return specs


#: Champs de `BC.Units[]` que `buildNormalizedBC` RECALCULE, donc qu'un patch du SEED BC ne peut
#: PAS porter (#914-r1). DERIVE du foyer natif -- `frida/hooks/features/normalize-bc/json-build.ts`,
#: toutes ses ecritures `u.<champ> = ...` -- et NON recopie de memoire ; le cliquet
#: `tests/engine/test_914r1_champs_recalcules_offline.py` re-derive la liste du TS et rougit sur
#: tout ecart, dans les DEUX sens.
#:
#: Les huit premiers sortent du buffer de `IStatsFormula.StatsUsingProgressionIndexFor` ;
#: `RemainingHealth` est reposee a `Health` (« spawned unit starts at full HP ») ; `Rank` vient de
#: `targetRank` ; les cinq derniers ne sont ecrits que si l'appelant fournit le `target*` associe --
#: `_normalize_and_extract_pool` les fournit TOUS, donc les 16 sont ecrits sur ce chemin-la.
CHAMPS_RECALCULES_PAR_NORMALISATION = (
    "Health", "Damage", "Armor", "FixedArmor",
    "CritChance", "CritDamage", "BlockChance", "BlockDamage",
    "RemainingHealth", "Rank",
    "Rarity", "Level", "StarLevel", "ActiveAbilityLevel", "PassiveAbilityLevel",
    "TertiaryAbilityLevel",
)


def _seed_bc_reference() -> dict:
    """`data/seed-bc.json` BRUT (aucun rattrapage), mis en cache. Le TEMOIN de « non patche »."""
    if _REF_CACHE.get("bc") is None:
        try:
            _REF_CACHE["bc"] = json.loads(SEED_BC.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _REF_CACHE["bc"] = {}          # reference illisible -> on se TAIT, on n'invente pas
    return _REF_CACHE["bc"]


_REF_CACHE: dict = {"bc": None}


def _rapport_champs_ecrases(base_bc: dict, template: dict) -> list:
    """Lignes de diagnostic pour les patchs du SEED BC que la normalisation vient d'ECRASER.

    LE VICE (#914) : deux probes jumeaux ecrivaient `Health = 900000` dans le seed BC et
    l'ANNONCAIENT (`[bc] astraBullgryn : PV portes a 900000`) ; la cible arrivait a ~9539 PV,
    mourait en cours de serie, et le dernier montant live devenait un OVERKILL -- ce qui a fait
    accuser la magnitude d'un percage porte. Rien, nulle part, ne disait que le champ etait
    recalcule. `--unit-stat` sait deja avertir sur un champ JAMAIS LU (#342) ; il n'existait
    aucun equivalent pour un champ ECRASE, et un patch de seed BC ne passe meme pas par lui.

    LES TROIS CONDITIONS, et pourquoi chacune est necessaire :
      * le champ est dans `CHAMPS_RECALCULES_PAR_NORMALISATION` -- sinon il traverse INTACT ;
      * la valeur du seed DIFFERE de `data/seed-bc.json` : c'est ce qui distingue un PATCH
        DELIBERE du recalcul ordinaire, que subissent les 175 entrees et qui n'interesse
        personne. Une unite ABSENTE de la reference (injectee par `catalog_inject.augment`) est
        ignoree -- on ne sait rien de ce qu'elle « aurait du » valoir, et parler la serait du bruit ;
      * la valeur a EFFECTIVEMENT change entre le seed et le BC rendu. C'est le seul discriminant
        d'ecrasement, et il est SUFFISANT.

    ⚠ CE QU'UNE MUTATION A APPRIS. Ce rapport testait d'abord une QUATRIEME condition -- « l'unite
    est dans `result.normalized` » -- posee pour eviter le faux positif que la fiche nomme : un
    CARRIER DE SUMMON fait LEVER la formule heros, part en `skipped`, et son patch de PV est
    legitime. Elle a ete RETIREE parce que la mutation qui la neutralise laisse le fichier de
    garde INTEGRALEMENT VERT : elle est redondante, et pour une raison structurelle lisible dans
    `json-build.ts` -- une unite `skipped` n'est pas modifiee du tout (les ecritures `u.<champ> =`
    suivent l'appel de formule, donc une levee saute au `catch`), si bien que sa valeur SORT
    IDENTIQUE et que la troisieme condition la couvre deja. La garder aurait laisse une branche
    qu'aucune contre-epreuve ne peut faire mordre.

    Rend `[]` quand il n'y a rien a dire, c.-a-d. sur le chemin par defaut (seed BC = reference).
    """
    ref = {u.get("Id"): u for u in (_seed_bc_reference().get("Units") or []) if u.get("Id")}
    if not ref:
        return []
    apres = {u.get("Id"): u for u in (template.get("Units") or []) if u.get("Id")}
    lignes = []
    for u in (base_bc.get("Units") or []):
        uid = u.get("Id")
        if uid not in ref:
            continue
        ecrases = []
        for champ in CHAMPS_RECALCULES_PAR_NORMALISATION:
            if champ not in u or champ not in ref[uid]:
                continue
            if u[champ] == ref[uid][champ]:
                continue                                   # pas un patch : valeur d'origine
            arrive = apres.get(uid, {}).get(champ)
            if arrive != u[champ]:
                ecrases.append(f"{champ}={u[champ]!r} -> {arrive!r}")
        if ecrases:
            lignes.append(
                f"ATTENTION {uid} : patch du SEED BC ECRASE par buildNormalizedBC -- "
                f"{', '.join(ecrases)}. Ces champs sont RECALCULES (formule "
                f"IStatsFormula.StatsUsingProgressionIndexFor) : le seul levier qui mord est "
                f"`--unit-stat {uid}:<champ>=<valeur>`, applique au BC DEJA NORMALISE (#914-r1).")
    return lignes


def _normalize_and_extract_pool(
    sid: int, base_bc: dict, target_rank: int,
    board_dump: dict | None = None,
    explicit_stats: dict | None = None,
    equip_items: bool | None = None,
    item_specs: dict | None = None,
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

    `explicit_stats` (#419-r1-tr12-r2) = `{unitId: {champ: valeur}}`, le
    CHEMIN DE STATS EXPLICITE des porteurs npc / summon, que la formule
    heros `StatsUsingProgressionIndexFor` fait LEVER (ils n'ont pas de
    table de progression de heros) -- ils partaient donc en `skipped` et
    n'atteignaient jamais le pool. Les valeurs se calculent par
    `catalog_inject.explicit_stats`, mirror des chemins natifs
    `UnitProgression$$GetNpcStats` / `$$GetSummonStats`. Une cle qui ne
    matche aucune entree du catalogue remonte en `explicitUnmatched` et
    fait LEVER ici : sans ce refus, un id mal orthographie retomberait en
    silence sur la formule heros -- exactement la panne que ce chemin
    supprime.

    `equip_items` (#419-r5 ; `None` = le defaut `_EQUIP_ITEMS_PAR_DEFAUT`, dont
    l'arbitrage MESURE est documente sur la constante) = equipe chaque unite de ses items
    Best-In-Slot avant d'appeler la formule. C'est ce qui OUVRE le canal
    crit/block : sans items la formule rend 0 sur les 4 stats concernees, et
    `IdunBattle.Core.Services.DamageCalculations$$CouldCrit` (`GetStat(9) > 0
    && GetStat(10) > 0`) est alors FAUX pour toute unite -- cote natif comme
    cote port. Mesure sur le seed BC au rank 17 : `could_crit` passe de
    0/106 a 98/106, `could_block` de 0/106 a 46/106, `Health`, `Damage` et
    `FixedArmor` restant INCHANGES (les slots crit/block ne portent pas ces
    stats). `equip_items=False` restitue le regime d'avant #419-r5, ou le crit
    et le block sont structurellement impossibles.

    `item_specs` (optionnel) court-circuite le calcul BiS et impose des items
    choisis (meme forme que `previewBis.itemSpecs` :
    `{unitId: [{configId, level}]}`).
    """
    # Bascule GLOBALE, dans les DEUX sens, sans toucher au code :
    #   TACTICUS_BIS_ITEMS=1  -> equipe partout (canal crit/block OUVERT) ;
    #   TACTICUS_BIS_ITEMS=0  -> n'equipe nulle part (regime d'avant #419-r5).
    # Elle sert a etablir un TEMOIN (<< ce rouge existait-il deja ? >>) et a mesurer d'un coup
    # le rayon de souffle d'une bascule du defaut. Un appelant qui a passe `equip_items`
    # EXPLICITEMENT n'est pas ecrase : seul le defaut l'est.
    _bascule = os.environ.get("TACTICUS_BIS_ITEMS")
    if _bascule in ("0", "1") and equip_items is None:
        equip_items = (_bascule == "1")
    if equip_items is None:
        equip_items = _EQUIP_ITEMS_PAR_DEFAUT
    if item_specs is None and equip_items:
        # Le cap de rarete des items est le MEME que la rarete cible de la
        # normalisation -- il n'y a qu'un seul regime cible, pas deux. Les
        # dupliquer laisserait deriver un heros `targetRarity=5` equipe
        # d'items plafonnes ailleurs, en silence.
        item_specs = _bis_item_specs(sid, base_bc, rarity_cap=_TARGET_RARITY)
    base_json = json.dumps(base_bc)
    args: dict = {
        "baseBcJson": base_json,
        "targetRank": target_rank,
        "targetProgressionIndex": target_rank,
        "targetRarity": _TARGET_RARITY,
        "targetLevel": 50,
        "targetStarLevel": 5,
        "targetAbilityLevel": 50,
    }
    if item_specs:
        args["itemSpecs"] = item_specs
    if board_dump is not None:
        inner = board_dump.get("board")
        if not inner:
            raise RuntimeError(
                f"Board dump for {board_dump.get('id')!r} has no .board")
        args["boardJson"] = json.dumps(inner)
        sps = board_dump.get("spawnPointsSet")
        if isinstance(sps, int):
            args["spawnPointSetIndex"] = sps
    if explicit_stats:
        args["explicitStats"] = explicit_stats
    out = _rpc(sid, "buildNormalizedBC", [args], timeout=60).get("result") or {}
    if not out.get("ok"):
        raise RuntimeError(f"buildNormalizedBC failed: {out.get('err', '?')}")
    unmatched = out.get("explicitUnmatched") or []
    if unmatched:
        raise RuntimeError(
            f"buildNormalizedBC: explicitStats sans entree au catalogue: {unmatched} "
            f"-- injecter l'unite d'abord (catalog_inject.augment / --seed-bc)")
    if explicit_stats and not (out.get("explicit") or []):
        # Le RPC a repondu SANS le champ `explicit` : c'est une session dont le
        # bundle est ANTERIEUR a #419-r1-tr12-r2. Les stats explicites ont ete
        # ignorees et la formule heros a tourne -- donc des stats FAUSSES (ou un
        # `skipped`) qui se liraient comme un resultat. On refuse.
        raise RuntimeError(
            "buildNormalizedBC n'a honore AUCUNE stat explicite (champ `explicit` vide) "
            "-- le bundle de hooks injecte est anterieur au chemin de stats explicite "
            "(#419-r1-tr12-r2). Rebuild + reinject requis.")
    template = json.loads(out["configJson"])
    normalized = set(out.get("normalized") or [])
    mow_set = set(out.get("mow") or [])
    # #914-r1 -- un champ RECALCULE patche en amont ne disait RIEN, et le montage mentait alors
    # dans son propre `print`. C'est ICI, et nulle part ailleurs, qu'on voit les TROIS termes
    # necessaires : le seed BC recu, le BC rendu, et QUELLES unites la formule a normalisees.
    for ligne in _rapport_champs_ecrases(base_bc, template):
        print(f"[normalize] {ligne}", file=sys.stderr)
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
    # `owner` : etiquette de proprietaire gardee par le registre cote hooks
    # (cf. rl_duel build). Un batch n'a pas de state-file -> on l'identifie par
    # son process, ce qui suffit a distinguer ses runners de ceux d'un agent.
    init_resp = _rpc(sid, "initAndStart",
                     [{"configJson": json.dumps(bc),
                       "seed": engine_seed,
                       "playerUnits": player_units,
                       "owner": f"rl_collect_batch:pid{os.getpid()}"}], timeout=30)
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
    # Board REQUIRED (cf. #159) : the seed BC skeleton's default board (live
    # capture) has no reliable 5v5 spawns -> a dumped board must be chosen.
    if not args_ns.board and not args_ns.board_pool:
        print("[error] choose a board: --board <id> (e.g. MC1_67, C4_09) or "
              "--board-pool <pvp|syncPvp|global>. Regenerate data/boards/ via "
              "`python dump_boards.py`.", file=sys.stderr)
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
            if not args_ns.no_mow and not _board_supports_mow(board_dump):
                print(f"[warn] fixed board {board_dump.get('id')!r} has no "
                      f"MoW slot (both sides) — any MoW will silently drop. "
                      f"Use --no-mow or a MoW-capable board.", file=sys.stderr)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[error] {e}", file=sys.stderr)
            return 2

    # Setup : normalize + extract pool (with optional fixed board swap)
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

    # Drop units/MoW that pass stats-normalization but throw at spawn (probed
    # denylist). Without this a battle that samples one dies on a deterministic
    # managed exception (Initialize for AI / AddUnit for player).
    bad_u, bad_m = _load_unspawnable(args_ns.target_rank)
    if bad_u or bad_m:
        dropped_u = [u for u in pool if u in bad_u]
        dropped_m = [u for u in pool_mow if u in bad_m]
        pool = [u for u in pool if u not in bad_u]
        pool_mow = [u for u in pool_mow if u not in bad_m]
        if dropped_u or dropped_m:
            print(f"[ok] dropped {len(dropped_u)} unspawnable unit(s) + "
                  f"{len(dropped_m)} MoW (probed denylist, rank "
                  f"{args_ns.target_rank}): {dropped_u + dropped_m}")

    # Board pool loaded AFTER normalization: we need pool_mow to know whether
    # MoW is actually in play, so we can restrict the pool to MoW-capable
    # boards (avoids silent MoW drops on boards without a MoW slot).
    if args_ns.board_pool:
        require_mow = (not args_ns.no_mow) and bool(
            pool_mow or args_ns.mow_player or args_ns.mow_ai)
        try:
            board_pool = _load_board_pool(
                args_ns.board_pool, args_ns.roster_size, require_mow)
            print(f"[ok] board pool ({args_ns.board_pool}): "
                  f"{len(board_pool)} boards eligible "
                  f"(>={args_ns.roster_size} pts/side"
                  f"{', MoW-capable' if require_mow else ''})")
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[error] {e}", file=sys.stderr)
            return 2
        if not board_pool:
            print(f"[error] empty board pool for kind="
                  f"{args_ns.board_pool!r}"
                  f"{' with MoW requirement' if require_mow else ''}",
                  file=sys.stderr)
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

    # #273 : le repertoire de traces est ECRIT PAR LE HOST, dans SON arbre. Un
    # worktree y globait dans le vide et le batch se poursuivait, annoncant
    # `0 -> 0` octets et `active trace = None` comme si le host s'etait tu.
    # Le collect a besoin de ce fichier (offset d'ingest + `trace_files` du
    # summary) : introuvable => ECHEC NOMME, jamais une collecte muette.
    try:
        traces_dir = host_inputs.require(_TRACES)
    except host_inputs.HostInputUnavailable as e:
        print(str(e), file=sys.stderr)
        return 2
    bytes_before = _dir_size_bytes(traces_dir)
    # Snapshot le fichier JSONL trace actif AVANT le run pour pouvoir
    # l'écrire dans le summary (= pointer vers les events Frida de ce batch).
    trace_files_before = set(
        p.name for p in host_inputs.find(_TRACES, "*.jsonl"))
    # Localiser le JSONL actif (le plus recent) pour l'ingest progressif.
    _all_traces = sorted(host_inputs.find(_TRACES, "*.jsonl"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
    active_trace = _all_traces[0] if _all_traces else None
    print(f"[ok] ai-traces dir : {host_inputs.resolve(_TRACES).label()}")
    print(f"[ok] bytes before  : {bytes_before:,}")
    print(f"[ok] active trace  : {active_trace}")
    print(f"[ok] launching {args_ns.num_battles} battles "
          f"(maxTurns={args_ns.max_turns}, roster={args_ns.roster_size}/team)")
    print("-" * 60)

    # Initialize progressive PG ingest if available.
    ingest_ctx = _open_progressive_ingest(args_ns, seed, sid, active_trace)
    # Position offset to start of current trace (we won't re-ingest old events).
    if ingest_ctx and active_trace and active_trace.exists():
        ingest_ctx["trace_offset"] = active_trace.stat().st_size

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

        # Progressive ingest : écrit ce battle en DB tout de suite.
        if ingest_ctx is not None:
            try:
                _ingest_one_battle(ingest_ctx, r)
            except Exception as e:
                print(f"  [ingest] ERROR for battle {i+1}: {e}",
                      file=sys.stderr)
                try: ingest_ctx["conn"].rollback()
                except Exception: pass
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
    bytes_after = _dir_size_bytes(traces_dir)
    delta = (bytes_after or 0) - (bytes_before or 0)

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
    print(f"  ai-traces           : {bytes_before or 0:,} -> "
          f"{bytes_after or 0:,} (+{delta:,} bytes)")
    print(f"  total elapsed       : {total_elapsed:.1f}s")
    if ok_count and total_turns:
        print(f"  avg time / turn     : "
              f"{(total_elapsed/total_turns)*1000:.0f} ms")

    # Écrit un summary JSON pour l'ingestion Postgres.
    # Inclut : args du run, session id, JSONL trace file actif pendant le
    # run, et tous les battles avec rosters/board/runnerId/turns.
    # Le runnerId du Frida permet de joindre avec les events `move_options`
    # et `battle_winner` du JSONL.
    trace_files_after = set(p.name for p in host_inputs.find(_TRACES, "*.jsonl"))
    new_traces = sorted(trace_files_after - trace_files_before)
    # Si plusieurs JSONLs créés pendant le run (rare — typiquement 0 ou 1
    # nouveau), on garde tous. Si aucun, on pointe vers le plus récent
    # existant (l'écriture est append-only au même fichier que le run).
    if new_traces:
        active_traces = new_traces
    else:
        latest = sorted(host_inputs.find(_TRACES, "*.jsonl"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
        active_traces = [latest[0].name] if latest else []

    # SORTIE : le summary accompagne les traces qu'il indexe (`trace_files` y est
    # relatif a TRACES_DIR), donc il s'ecrit dans l'arbre du HOST -- pas dans le
    # worktree, ou `rl_ingest_postgres --all` ne le retrouverait jamais.
    summaries_dir = traces_dir.parent / "rl-batches"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    summary_name = (f"batch-{int(t_global)}-sid{sid}.json")
    summary_path = summaries_dir / summary_name
    summary = {
        "schema_version": 1,
        "started_at": int(t_global),       # monotonic — pour ordering
        "wall_started_at": int(time.time() - total_elapsed),
        "wall_ended_at": int(time.time()),
        "session_id": sid,
        "seed": seed,
        "n_battles": args_ns.num_battles,
        "args": {
            "num_battles": args_ns.num_battles,
            "max_turns": args_ns.max_turns,
            "roster_size": args_ns.roster_size,
            "seed": args_ns.seed,
            "board": getattr(args_ns, "board", None),
            "board_pool": getattr(args_ns, "board_pool", None),
            "mow_player": getattr(args_ns, "mow_player", None),
            "mow_ai": getattr(args_ns, "mow_ai", None),
            "no_mow": getattr(args_ns, "no_mow", False),
            "retry_on_fail": args_ns.retry_on_fail,
        },
        "trace_files": active_traces,      # JSONL relatifs à TRACES_DIR
        "ok_count": ok_count,
        "n_results": len(results),
        "total_turns": total_turns,
        "total_elapsed_sec": total_elapsed,
        "battles": results,                # tous les retours de _one_battle
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"  summary             : {summary_path}")

    # Close progressive ingest connection
    if ingest_ctx is not None:
        try: ingest_ctx["conn"].close()
        except Exception: pass

    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
