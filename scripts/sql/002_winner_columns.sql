-- 002_winner_columns.sql — ajoute les colonnes du WinnerInfo capturé par
-- winner-capture.ts. Ré-exécutable (IF NOT EXISTS).

ALTER TABLE tacticus.battle ADD COLUMN IF NOT EXISTS winner_player_id INT;
ALTER TABLE tacticus.battle ADD COLUMN IF NOT EXISTS winner_team_id   INT;
ALTER TABLE tacticus.battle ADD COLUMN IF NOT EXISTS winner_entity_id INT;
ALTER TABLE tacticus.battle ADD COLUMN IF NOT EXISTS outcome          TEXT;
ALTER TABLE tacticus.battle ADD COLUMN IF NOT EXISTS reason_code      INT;
ALTER TABLE tacticus.battle ADD COLUMN IF NOT EXISTS reason_name      TEXT;
