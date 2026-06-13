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
    from enum_maps import BY_COLUMN as _ENUM_MAPS, GROUP_TYPE as _GROUP_TYPE
except ImportError:
    _ENUM_MAPS = {}
    _GROUP_TYPE = {}


def _enum_name(v: int | None, col: str) -> str | None:
    """Libellé dénormalisé d'une valeur enum (None si inconnue/absente)."""
    if v is None:
        return None
    return _ENUM_MAPS.get(col, {}).get(v)


def _group_name(code: int | None) -> str | None:
    """Libellé GroupType (stream_group.group_name)."""
    if code is None:
        return None
    return _GROUP_TYPE.get(code)


HOST = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[2]
TRACES_DIR = ROOT / "frida" / "data" / "ai-traces"
SUMMARIES_DIR = ROOT / "frida" / "data" / "rl-batches"
ARENA_SEED_BC = ROOT / "data" / "arena-battle-config-newtonsoft.json"
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


STEP_NAMES = {
    0: "None", 1: "StartMatch", 2: "StartTurn", 3: "ChangePosition",
    4: "UnitDamaged", 5: "HealInfo", 6: "RepairInfo", 7: "RestoreArmorInfo",
    8: "AddPlayer", 9: "AddTile", 10: "AddUnit", 11: "AddMachine",
    12: "RemoveUnit", 13: "ChangeStats", 14: "ChangeAbility",
    15: "FinishMatch", 16: "ReceiveEffect", 17: "LoseEffect",
    18: "ActivateEffect", 19: "DeactivateEffect", 20: "UpdateEffect",
    21: "UpdateEffectTurns", 22: "AttackTile", 23: "UnitDraft",
    24: "SpawnPointDraft", 25: "ExtraAttackDamage", 26: "DirectlyKillUnit",
    27: "LootInfo", 28: "RemoveUnitFromTiles", 29: "Revive", 30: "Info",
    31: "TerritoryCapture", 32: "TerritoryScoreModifierChange",
    33: "AddVictoryPoints", 34: "RemoveVictoryPoints",
    35: "UpdateAbilityModification", 36: "TransferDamage", 37: "Resurrect",
    38: "OverrideMovementTarget", 39: "PrepareTurn", 40: "ChangeUnitOwner",
    41: "UpdateEffectLevel", 42: "UnitFled", 43: "RotateUnit",
    44: "AddMachinePlatform", 45: "MachineHit", 46: "RemoveMachine",
    47: "SpendAmmo", 48: "ChangePlayerReinforcement",
    49: "ChangeUnitConfig", 50: "AddScore", 51: "SetTempPlayer",
    52: "ResetTempPlayer", 53: "AddReinforcementShield", 54: "PickUnit",
    55: "ChangeResurrectDraftingPoints", 56: "AddOrUpdateShield",
    57: "RemoveShield", 58: "RevealFogOfWar", 59: "HideDoorActivationTile",
    60: "OpenDoor", 61: "ReaddMachine", 62: "PlayerInitialRarity",
}


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
    env = _load_env(ROOT / ".env")
    pwd = env.get("PG_PASSWORD")
    if not pwd:
        print("[ingest] PG_PASSWORD vide — ingestion desactivee", file=sys.stderr)
        return None
    conn = psycopg.connect(
        host=env.get("PG_HOST", "localhost"),
        port=int(env.get("PG_PORT", "5433")),
        dbname=env.get("PG_DATABASE", "TACTICUS"),
        user=env.get("PG_USER", "postgres"),
        password=pwd,
    )
    # Detect game_hash
    game_hash = None
    games_dir = Path(os.path.expandvars(r"%LOCALAPPDATA%\tacticus\games"))
    if games_dir.exists():
        ents = list(games_dir.iterdir())
        if ents:
            game_hash = ents[0].name
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
        "trace_path": trace_path or TRACES_DIR / "_unknown.jsonl",
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
                _ATTACK = (12, 32, 59)         # User_UseAbility, Ability_Attack, NormalAttack
                _ACTOR = (11, 12, 13, 32, 59)  # + User_MoveUnit/PlaceUnit
                se_rows = []
                sg_rows: list[list[Any]] = []
                gstack: list[dict[str, Any]] = []
                for ord_idx, ev in enumerate(msg.get("_events") or []):
                    kind = ev.get("kind")
                    if kind == "group":
                        gcode = _safe_int(ev.get("group"))
                        gent = _safe_int(ev.get("entity"))
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
                    if step == 30 and "Attack_Weapon_IsMelee" in tags_dict:
                        _mv = _t("Attack_Weapon_IsMelee")
                        for fr in reversed(gstack):
                            if fr["code"] in _ATTACK:
                                fr["melee"] = _mv
                                break
                    melee_val = None
                    for fr in reversed(gstack):
                        if fr["melee"] is not None:
                            melee_val = fr["melee"]
                            break

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
                            group_id, caster_entity
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
                            %s, %s
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

    bytes_before = _dir_size_bytes(TRACES_DIR)
    # Snapshot le fichier JSONL trace actif AVANT le run pour pouvoir
    # l'écrire dans le summary (= pointer vers les events Frida de ce batch).
    trace_files_before = set(
        p.name for p in TRACES_DIR.glob("*.jsonl"))
    # Localiser le JSONL actif (le plus recent) pour l'ingest progressif.
    _all_traces = sorted(TRACES_DIR.glob("*.jsonl"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
    active_trace = _all_traces[0] if _all_traces else None
    print(f"[ok] ai-traces dir : {TRACES_DIR}")
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

    # Écrit un summary JSON pour l'ingestion Postgres.
    # Inclut : args du run, session id, JSONL trace file actif pendant le
    # run, et tous les battles avec rosters/board/runnerId/turns.
    # Le runnerId du Frida permet de joindre avec les events `move_options`
    # et `battle_winner` du JSONL.
    trace_files_after = set(p.name for p in TRACES_DIR.glob("*.jsonl"))
    new_traces = sorted(trace_files_after - trace_files_before)
    # Si plusieurs JSONLs créés pendant le run (rare — typiquement 0 ou 1
    # nouveau), on garde tous. Si aucun, on pointe vers le plus récent
    # existant (l'écriture est append-only au même fichier que le run).
    if new_traces:
        active_traces = new_traces
    else:
        latest = sorted(
            [p for p in TRACES_DIR.glob("*.jsonl")],
            key=lambda p: p.stat().st_mtime, reverse=True)
        active_traces = [latest[0].name] if latest else []

    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    summary_name = (f"batch-{int(t_global)}-sid{sid}.json")
    summary_path = SUMMARIES_DIR / summary_name
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
