-- 001_init_schema.sql — schema initial pour la pipeline RL Tacticus.
-- Cibles : 3 tables (batch / battle / move_options_event) + indexes.
-- À ré-exécuter avec idempotence (IF NOT EXISTS partout).

CREATE SCHEMA IF NOT EXISTS tacticus;

-- ---------------------------------------------------------------------------
-- batch — une ligne par exécution du script rl_collect_batch.py
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tacticus.batch (
  batch_id   BIGSERIAL PRIMARY KEY,
  started_at TIMESTAMPTZ DEFAULT now(),
  seed       INT,
  n_battles  INT,
  game_hash  TEXT,        -- ex. "rmvdp0v56c"
  config     JSONB,       -- args complets du script
  hooks_sha  TEXT         -- git rev de frida/hooks/ au moment du run
);

-- ---------------------------------------------------------------------------
-- battle — une ligne par battle dans un batch
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tacticus.battle (
  battle_id        BIGSERIAL PRIMARY KEY,
  batch_id         BIGINT REFERENCES tacticus.batch(batch_id) ON DELETE CASCADE,
  idx              INT,                  -- index dans le batch (1..n)
  runner_id        INT,                  -- buildId Frida
  roster_p         TEXT[],
  roster_a         TEXT[],
  mow_p            TEXT,
  mow_a            TEXT,
  board_id         TEXT,
  engine_seed      INT,
  ok               BOOL,
  final_stage      INT,
  reached_finished BOOL,
  hit_max_turns    BOOL,
  turns_count      INT,
  elapsed_ms       INT,
  err              TEXT
);
CREATE INDEX IF NOT EXISTS battle_batch_idx     ON tacticus.battle (batch_id);
CREATE INDEX IF NOT EXISTS battle_roster_p_gin  ON tacticus.battle USING GIN (roster_p);
CREATE INDEX IF NOT EXISTS battle_roster_a_gin  ON tacticus.battle USING GIN (roster_a);

-- ---------------------------------------------------------------------------
-- move_options_event — une ligne par fire de MovementQuery.GetMovableTilesFor
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tacticus.move_options_event (
  event_id            BIGSERIAL PRIMARY KEY,
  battle_id           BIGINT REFERENCES tacticus.battle(battle_id) ON DELETE CASCADE,
  apply_seq           INT,        -- window de l'Apply (groupe les fires d'un même tour)
  unit_entity_id      INT,        -- l'unit scoré
  turn                INT,
  turn_player         INT,
  ignore_flags        BOOL,
  opt_ign_special     BOOL,
  opt_ign_units       BOOL,
  opt_is_danger       BOOL,
  opt_override_range  INT,        -- NULL si HasValue=false
  opt_has_range_bonus BOOL,
  fire_no             INT,        -- ordre Frida (debug/correl avec JSONL)
  candidates          JSONB       -- placeholder — rempli au step 3 avec [{col,row}, ...]
);
CREATE INDEX IF NOT EXISTS moe_battle_apply_unit
  ON tacticus.move_options_event (battle_id, apply_seq, unit_entity_id);
CREATE INDEX IF NOT EXISTS moe_unit_idx
  ON tacticus.move_options_event (unit_entity_id);
