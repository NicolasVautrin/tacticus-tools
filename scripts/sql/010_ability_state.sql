-- 010_ability_state.sql -- maintient l'evolution des abilities (active +
-- triggered) au cours d'une battle.
--
-- Les events StreamDispatcher mentionnent l'ability uniquement quand son
-- state change (cooldown decremente, used, disabled, blocked, etc.). On
-- log chaque change ici. Pour avoir le state d'une ability a un instant t
-- → query v_ability_state_at_apply(battle_id, apply_seq, ...).
--
-- Hypothese : avant le 1er event sur (squad, ability), l'ability est Ready
-- (can_be_used=true, cooldown=0, is_disabled=false). Donc absence de row
-- = etat par defaut = Ready.

CREATE TABLE IF NOT EXISTS tacticus.ability_state_change (
  ability_state_id BIGSERIAL PRIMARY KEY,
  message_id       BIGINT NOT NULL REFERENCES tacticus.message(message_id)
                              ON DELETE CASCADE,
  battle_id        BIGINT NOT NULL REFERENCES tacticus.battle(battle_id)
                              ON DELETE CASCADE,
  apply_seq        BIGINT NOT NULL,
  ordinal          INT    NOT NULL,
  squad_id         INT    NOT NULL,
  kind             TEXT   NOT NULL,  -- 'active' | 'triggered'
  ability_id       INT    NOT NULL,
  ability_name     TEXT,
  -- Active fields (NULL pour triggered) :
  cooldown_remaining INT,
  can_still_be_used  BOOLEAN,
  is_disabled        BOOLEAN,
  is_blocked         BOOLEAN,
  blocked_reason_effect_type INT,
  level              INT,
  variable_mult_pct  INT,
  -- Triggered fields (NULL pour active) :
  has_enough_ammo    BOOLEAN
);

CREATE INDEX IF NOT EXISTS abs_battle_apply_idx
  ON tacticus.ability_state_change (battle_id, apply_seq);
CREATE INDEX IF NOT EXISTS abs_squad_ability_idx
  ON tacticus.ability_state_change (battle_id, squad_id, ability_id);
CREATE INDEX IF NOT EXISTS abs_message_idx
  ON tacticus.ability_state_change (message_id);

-- Vue "last known state" par (battle, apply_seq, squad, ability) :
-- pour BC/RL, prendre la derniere row dont apply_seq <= cible.
CREATE OR REPLACE VIEW tacticus.v_ability_state_latest AS
  SELECT DISTINCT ON (battle_id, squad_id, kind, ability_id)
         battle_id, squad_id, kind, ability_id, ability_name,
         apply_seq, cooldown_remaining, can_still_be_used, is_disabled,
         is_blocked, blocked_reason_effect_type, level, variable_mult_pct,
         has_enough_ammo
    FROM tacticus.ability_state_change
   ORDER BY battle_id, squad_id, kind, ability_id, apply_seq DESC, ordinal DESC;

-- Vue Overwatch ready (signal RL critique : "puis-je move vers cette tile
-- sans suicider mon unit ?") : triggered abilities Overwatch dont
-- HasEnoughAmmo=true et dont la derniere row marque qu'elles ont des
-- charges (le state Used/Ready depend du turn courant — voir Attack_Is_First_Hit
-- pour distinguer overwatch shot vs main turn shot).
CREATE OR REPLACE VIEW tacticus.v_overwatch_ready AS
  SELECT a.*
    FROM tacticus.v_ability_state_latest a
    JOIN tacticus.ref_triggered_ability r ON r.ability_id = a.ability_id
   WHERE a.kind = 'triggered'
     AND r.name ILIKE '%overwatch%'
     AND COALESCE(a.has_enough_ammo, TRUE);
