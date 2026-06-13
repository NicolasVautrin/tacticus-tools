-- 007_stream_event_hot_cols.sql — extrait 20 tags les plus utiles
-- depuis `tags` JSONB vers colonnes typees indexables.
-- Le JSONB `tags` reste pour les autres 224 tags rares.

ALTER TABLE tacticus.stream_event
  ADD COLUMN IF NOT EXISTS hp_remaining                   INT,
  ADD COLUMN IF NOT EXISTS hp_max                         INT,
  ADD COLUMN IF NOT EXISTS armor_remaining                INT,
  ADD COLUMN IF NOT EXISTS armor_max                      INT,
  ADD COLUMN IF NOT EXISTS members_current                INT,
  ADD COLUMN IF NOT EXISTS members_max                    INT,
  ADD COLUMN IF NOT EXISTS attack                         INT,
  ADD COLUMN IF NOT EXISTS attack_range                   INT,
  ADD COLUMN IF NOT EXISTS movement                       INT,
  ADD COLUMN IF NOT EXISTS active_ability_id              INT,
  ADD COLUMN IF NOT EXISTS active_ability_cooldown        INT,
  ADD COLUMN IF NOT EXISTS triggered_ability_id           INT,
  ADD COLUMN IF NOT EXISTS effect_id                      INT,
  ADD COLUMN IF NOT EXISTS effect_type                    INT,
  ADD COLUMN IF NOT EXISTS effect_source_id               INT,
  ADD COLUMN IF NOT EXISTS effect_level                   INT,
  ADD COLUMN IF NOT EXISTS effect_turns_remaining         INT,
  ADD COLUMN IF NOT EXISTS effect_source_active_ability   INT,
  ADD COLUMN IF NOT EXISTS effect_source_triggered_ability INT,
  ADD COLUMN IF NOT EXISTS unit_owner_id                  INT;

-- Indexes sur colonnes hot pour queries rapides
CREATE INDEX IF NOT EXISTS se_active_ability_idx
  ON tacticus.stream_event (active_ability_id);
CREATE INDEX IF NOT EXISTS se_triggered_ability_idx
  ON tacticus.stream_event (triggered_ability_id);
CREATE INDEX IF NOT EXISTS se_effect_id_idx
  ON tacticus.stream_event (effect_id);
CREATE INDEX IF NOT EXISTS se_unit_owner_idx
  ON tacticus.stream_event (unit_owner_id);

-- Refresh des vues pour exposer les nouvelles colonnes
DROP VIEW IF EXISTS tacticus.v_damage;
CREATE VIEW tacticus.v_damage AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS victim_id,
         e.hp_remaining,
         e.armor_remaining,
         e.members_current,
         e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code = 4;

DROP VIEW IF EXISTS tacticus.v_effect_received;
CREATE VIEW tacticus.v_effect_received AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS unit_id,
         e.effect_id, e.effect_type, e.effect_source_id,
         e.effect_level, e.effect_turns_remaining,
         e.effect_source_active_ability, e.effect_source_triggered_ability,
         e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code = 16;

DROP VIEW IF EXISTS tacticus.v_effect_lost;
CREATE VIEW tacticus.v_effect_lost AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS unit_id, e.effect_id, e.effect_type, e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code = 17;
