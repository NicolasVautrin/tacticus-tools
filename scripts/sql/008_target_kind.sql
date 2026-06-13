-- 008_target_kind.sql -- distingue tile vs unit pour les stream_events.
--
-- Heuristique :
--   stream_event.entity_id IN (SELECT squad_id FROM unit_state JOIN message)
--   pour le meme battle  →  target_kind = 'unit'
--   sinon                →  target_kind = 'tile'
--
-- Rationale : match-state.ts projette des UnitFoots (unit_id) + leur Squad
-- parent (squad_id). Les events StreamDispatcher.Action ciblent le Squad
-- entity, jamais le UnitFoot. Tout entity_id absent du set des squads
-- vus dans la battle est un autre type d'entity (Tile, Projectile, ...).
--
-- Pour l'instant on classe simplement unit/tile. Le set "tile" englobe
-- des tiles (Fire, SwampBlockMovement, BlockEnteringUnits, ...) mais aussi
-- potentiellement des entities transients (projectiles, summoned non
-- traques par UnitFoot). A affiner plus tard si besoin.

ALTER TABLE tacticus.stream_event
  ADD COLUMN IF NOT EXISTS target_kind TEXT;  -- 'unit' | 'tile' | NULL

-- Backfill : table temp avec la map (battle_id, squad_id) puis UPDATE.
DROP TABLE IF EXISTS _tmp_squads;
CREATE TEMP TABLE _tmp_squads AS
  SELECT DISTINCT m.battle_id, us.squad_id
    FROM tacticus.unit_state us
    JOIN tacticus.message m USING (message_id);
CREATE INDEX ON _tmp_squads (battle_id, squad_id);

UPDATE tacticus.stream_event se
   SET target_kind = CASE WHEN EXISTS (
         SELECT 1 FROM tacticus.message m
           JOIN _tmp_squads s ON s.battle_id = m.battle_id
                              AND s.squad_id = se.entity_id
          WHERE m.message_id = se.message_id
       ) THEN 'unit' ELSE 'tile' END
 WHERE se.target_kind IS NULL;

CREATE INDEX IF NOT EXISTS se_target_kind_idx
  ON tacticus.stream_event (target_kind);

-- Vues split : effects sur units vs tiles.
-- Drop v_effect_received d'abord car elle depend de v_effect_received_unit.
DROP VIEW IF EXISTS tacticus.v_effect_received;
DROP VIEW IF EXISTS tacticus.v_effect_received_unit;
CREATE VIEW tacticus.v_effect_received_unit AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS squad_id,
         e.effect_id, e.effect_type, e.effect_source_id,
         e.effect_level, e.effect_turns_remaining,
         e.effect_source_active_ability, e.effect_source_triggered_ability,
         e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code = 16 AND e.target_kind = 'unit';

DROP VIEW IF EXISTS tacticus.v_effect_received_tile;
CREATE VIEW tacticus.v_effect_received_tile AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS tile_id,
         e.effect_id, e.effect_type, e.effect_source_id,
         e.effect_level, e.effect_turns_remaining,
         e.effect_source_active_ability, e.effect_source_triggered_ability,
         e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code = 16 AND e.target_kind = 'tile';

-- v_effect_received existante : on reaffecte pour ne lister QUE les unit
-- (le cas tile est traite par v_effect_received_tile).
DROP VIEW IF EXISTS tacticus.v_effect_received;
CREATE VIEW tacticus.v_effect_received AS
  SELECT * FROM tacticus.v_effect_received_unit;

-- v_effect_lost : split aussi
DROP VIEW IF EXISTS tacticus.v_effect_lost;
CREATE VIEW tacticus.v_effect_lost AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id, e.target_kind,
         e.effect_id, e.effect_type, e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
   WHERE e.step_code = 17;
