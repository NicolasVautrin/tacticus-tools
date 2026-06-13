-- 004_message_matchstate.sql — ajoute le snapshot MatchState pre-action
-- sur chaque message. C'est le `s_t` pour IL/RL.
ALTER TABLE tacticus.message
  ADD COLUMN IF NOT EXISTS match_state JSONB;
