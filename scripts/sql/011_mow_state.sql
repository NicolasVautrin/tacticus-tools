-- 011_mow_state.sql -- snapshot des Machines of War.
--
-- Modele analogue a unit_state :
--   unit_state : 1 row par UnitFoot (entity visible sur le board),
--                lie au Squad parent via squad_id (= wrapper logique).
--   mow_state  : 1 row par MachinePlatform (entity visible sur le board),
--                lie a la Machine parent via machine_id.
--
-- Une MoW occupe N tiles → N rows mow_state par message, qui partagent
-- le meme machine_id (HP, owner, visual_id).
--
-- Spawn dynamique : certaines MoW apparaissent mid-battle (pas seulement
-- aux slots Top/Bottom). Pour ces cas, initial_slot=None (0) — la position
-- col/row reste la verite.

CREATE TABLE IF NOT EXISTS tacticus.mow_state (
  mow_state_id BIGSERIAL PRIMARY KEY,
  message_id   BIGINT NOT NULL REFERENCES tacticus.message(message_id)
                              ON DELETE CASCADE,
  platform_id  INT    NOT NULL,   -- entityId de la MachinePlatform (= unit_id chez UnitFoot)
  machine_id   INT    NOT NULL,   -- entityId de la Machine (= squad_id chez Squad)
  col          INT,
  row          INT,
  hp           INT,
  hp_max       INT,
  owner_id     INT,
  team_id      INT,
  visual_id    TEXT,
  rank         INT,
  initial_slot INT NOT NULL DEFAULT 0,  -- 0=None, 1=Top, 2=Bottom (MachineOfWarPosition enum)
  is_dead      BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS mow_state_msg_idx ON tacticus.mow_state (message_id);
CREATE INDEX IF NOT EXISTS mow_state_machine_idx ON tacticus.mow_state (machine_id);
CREATE INDEX IF NOT EXISTS mow_state_pos_idx ON tacticus.mow_state (col, row);
CREATE INDEX IF NOT EXISTS mow_state_team_idx ON tacticus.mow_state (team_id);

-- Vue qui liste les MoW distinctes par battle (1 row par machine_id unique).
CREATE OR REPLACE VIEW tacticus.v_mows_per_battle AS
  SELECT m.battle_id, ms.machine_id, ms.visual_id, ms.owner_id, ms.team_id,
         MIN(ms.initial_slot) initial_slot,
         COUNT(DISTINCT ms.platform_id) platform_count
    FROM tacticus.mow_state ms JOIN tacticus.message m USING (message_id)
   GROUP BY m.battle_id, ms.machine_id, ms.visual_id, ms.owner_id, ms.team_id;
