-- 009_tile_ref.sql -- ref des tiles par battle (snapshot statique).
--
-- Capture : au 1er message de chaque battle, message-trace.ts inclut
-- matchState.tiles via projectMatchState(opts.includeTiles=true).
-- Les tiles sont statiques pendant la battle (col/row/elevation/IsWall)
-- donc 1 snapshot suffit. Les changements dynamiques (Fire, Swamp temp.)
-- sont traces via stream_event step_code 16/17 (ReceiveEffect/Lost) sur
-- l'entity_id de la tile.

CREATE TABLE IF NOT EXISTS tacticus.tile_ref (
  battle_id        BIGINT  NOT NULL REFERENCES tacticus.battle(battle_id)
                              ON DELETE CASCADE,
  tile_id          INT     NOT NULL,       -- entity_id du Tile
  col              INT     NOT NULL,
  row              INT     NOT NULL,
  tile_def_id      TEXT,                    -- TileComponent.Id (ex. "RoomTile_Normal_01")
  elevation        INT     NOT NULL DEFAULT 0,
  is_wall          BOOLEAN NOT NULL DEFAULT FALSE,
  is_temporary     BOOLEAN NOT NULL DEFAULT FALSE,
  is_boss_platform BOOLEAN NOT NULL DEFAULT FALSE,
  is_territory     BOOLEAN NOT NULL DEFAULT FALSE,
  is_in_fog        BOOLEAN NOT NULL DEFAULT FALSE,
  room_tile_type   INT     NOT NULL DEFAULT 0,  -- 0=Floor, 1=Wall, 2=Door
  PRIMARY KEY (battle_id, tile_id)
);

CREATE INDEX IF NOT EXISTS tile_ref_pos_idx
  ON tacticus.tile_ref (battle_id, col, row);
CREATE INDEX IF NOT EXISTS tile_ref_def_idx
  ON tacticus.tile_ref (tile_def_id);

-- Vue qui joint stream_event tile + tile_ref pour avoir col/row + def
-- du tile cible par les effets terrain.
CREATE OR REPLACE VIEW tacticus.v_effect_tile_resolved AS
  SELECT m.battle_id, m.apply_seq, e.message_id, e.event_id, e.ordinal,
         e.entity_id AS tile_id,
         tr.col, tr.row, tr.tile_def_id,
         tr.elevation, tr.is_wall, tr.is_temporary, tr.room_tile_type,
         e.effect_id, e.effect_type, e.effect_source_id,
         e.effect_level, e.effect_turns_remaining,
         e.effect_source_active_ability, e.effect_source_triggered_ability,
         e.tags
    FROM tacticus.stream_event e
    JOIN tacticus.message m USING (message_id)
    LEFT JOIN tacticus.tile_ref tr
      ON tr.battle_id = m.battle_id AND tr.tile_id = e.entity_id
   WHERE e.step_code = 16 AND e.target_kind = 'tile';
