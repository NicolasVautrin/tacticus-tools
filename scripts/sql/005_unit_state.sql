-- 005_unit_state.sql — révise le snapshot MatchState : decompose en
-- colonnes typees + table unit_state (1 row per unit per snapshot)
-- au lieu d'un gros JSONB.

-- 1. Drop le JSONB (pas encore utilise)
ALTER TABLE tacticus.message DROP COLUMN IF EXISTS match_state;

-- 2. Globals typees sur message
ALTER TABLE tacticus.message
  ADD COLUMN IF NOT EXISTS turn            INT,
  ADD COLUMN IF NOT EXISTS stage           INT,
  ADD COLUMN IF NOT EXISTS stage_name      TEXT,
  ADD COLUMN IF NOT EXISTS player_on_turn  INT;

-- 3. unit_state : 1 ligne par (message, unit_foot)
CREATE TABLE IF NOT EXISTS tacticus.unit_state (
  unit_state_id BIGSERIAL PRIMARY KEY,
  message_id    BIGINT REFERENCES tacticus.message(message_id) ON DELETE CASCADE,
  unit_id       INT,           -- BEntityId du UnitFoot (= une tile occupee)
  squad_id      INT,           -- parent squad
  col           INT,
  row           INT,
  hp            INT,
  hp_max        INT,
  owner_id      INT,           -- BEntityId du Player
  team_id       INT,           -- 1, 2, 3
  visual_id     TEXT,
  rank          INT,
  is_dead       BOOL
);
CREATE INDEX IF NOT EXISTS unit_state_msg_idx ON tacticus.unit_state (message_id);
CREATE INDEX IF NOT EXISTS unit_state_squad_idx ON tacticus.unit_state (squad_id);
CREATE INDEX IF NOT EXISTS unit_state_team_idx ON tacticus.unit_state (team_id);
CREATE INDEX IF NOT EXISTS unit_state_pos_idx ON tacticus.unit_state (col, row);
