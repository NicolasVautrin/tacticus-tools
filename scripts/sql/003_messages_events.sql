-- 003_messages_events.sql — tables `message` + `stream_event` + vues
-- typées pour les events les plus utiles. Additif, idempotent.

-- ---------------------------------------------------------------------------
-- message : 1 ligne par runner.Apply / applyAiMessage (timeline d'actions)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tacticus.message (
  message_id   BIGSERIAL PRIMARY KEY,
  battle_id    BIGINT REFERENCES tacticus.battle(battle_id) ON DELETE CASCADE,
  msg_idx      INT,
  apply_seq    INT,
  src          TEXT,
  msg_class    TEXT,
  unit_id_raw  INT,
  runner_id    INT
);
CREATE UNIQUE INDEX IF NOT EXISTS message_battle_msgidx_uq
  ON tacticus.message (battle_id, msg_idx);
CREATE INDEX IF NOT EXISTS message_battle_applyseq_idx
  ON tacticus.message (battle_id, apply_seq);
CREATE INDEX IF NOT EXISTS message_msgclass_idx
  ON tacticus.message (msg_class);

-- ---------------------------------------------------------------------------
-- stream_event : 1 ligne par StreamDispatcher.Action/StartGroup
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tacticus.stream_event (
  event_id     BIGSERIAL PRIMARY KEY,
  message_id   BIGINT REFERENCES tacticus.message(message_id) ON DELETE CASCADE,
  ordinal      INT,
  kind         TEXT,
  step_code    INT,
  step_name    TEXT,
  group_code   INT,
  entity_id    INT,
  tags         JSONB
);
CREATE INDEX IF NOT EXISTS stream_event_msg_ord_idx
  ON tacticus.stream_event (message_id, ordinal);
CREATE INDEX IF NOT EXISTS stream_event_step_idx
  ON tacticus.stream_event (step_code);
CREATE INDEX IF NOT EXISTS stream_event_entity_idx
  ON tacticus.stream_event (entity_id);
CREATE INDEX IF NOT EXISTS stream_event_tags_gin
  ON tacticus.stream_event USING GIN (tags jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- Vues typees par usage
-- ---------------------------------------------------------------------------

-- Damage events (StepType 4 = UnitDamaged)
CREATE OR REPLACE VIEW tacticus.v_damage AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS victim_id,
         (e.tags->>'UnitStats_RemainingHealth')::int AS hp_after,
         (e.tags->>'UnitStats_RemainingArmor')::int AS armor_after,
         (e.tags->>'UnitStats_AliveMembers')::int AS members_alive,
         e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code = 4;

-- Effects reçus (StepType 16 = ReceiveEffect)
CREATE OR REPLACE VIEW tacticus.v_effect_received AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS unit_id, e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code = 16;

-- Effects retirés (StepType 17 = LoseEffect)
CREATE OR REPLACE VIEW tacticus.v_effect_lost AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS unit_id, e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code = 17;

-- Kills (StepType 12 = RemoveUnit, 26 = DirectlyKillUnit)
CREATE OR REPLACE VIEW tacticus.v_kill AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS victim_id, m.msg_class, m.unit_id_raw AS killer_msg_unit
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code IN (12, 26);

-- Position changes (StepType 3 = ChangePosition)
CREATE OR REPLACE VIEW tacticus.v_position_change AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS unit_id, e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code = 3;

-- Heals + Repairs (5, 6, 7)
CREATE OR REPLACE VIEW tacticus.v_heal_or_repair AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         CASE e.step_code WHEN 5 THEN 'heal'
                          WHEN 6 THEN 'repair'
                          WHEN 7 THEN 'restore_armor' END AS kind,
         e.entity_id AS unit_id, e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code IN (5, 6, 7);
