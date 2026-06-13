-- 014_stream_group.sql — matérialise l'arbre des groupes du StreamDispatcher
-- (StartGroup / FinishGroup). Requiert la capture des marqueurs 'finish'
-- (frida/hooks/game/apply-stack.ts) → re-collecte obligatoire (les anciennes
-- battles n'ont pas les fermetures).
--
-- Modèle : chaque nœud = un groupe (1 StartGroup .. 1 FinishGroup). Le nesting
-- est porté par parent_group_id (self-FK). Chaque action `stream_event` est
-- reliée à son groupe englobant immédiat via group_id. On dénormalise aussi
-- caster_entity + weapon_is_melee sur stream_event (calculés à l'ingest depuis
-- la pile) pour les requêtes courantes sans navigation de l'arbre.

CREATE TABLE IF NOT EXISTS tacticus.stream_group (
  group_id        BIGINT PRIMARY KEY,
  message_id      BIGINT NOT NULL REFERENCES tacticus.message(message_id),
  ordinal_open    INT  NOT NULL,                  -- ordinal du StartGroup dans le message
  ordinal_close   INT,                            -- ordinal du FinishGroup correspondant
  depth           INT  NOT NULL,                  -- profondeur dans l'arbre (0 = racine)
  group_code      INT  NOT NULL,                  -- GroupType
  group_name      TEXT,                           -- GroupType dénormalisé (enum_maps)
  entity          INT,                            -- entité qui ouvre le groupe (0 = aucune)
  parent_group_id BIGINT REFERENCES tacticus.stream_group(group_id)
);

CREATE INDEX IF NOT EXISTS stream_group_message_idx ON tacticus.stream_group(message_id);
CREATE INDEX IF NOT EXISTS stream_group_parent_idx  ON tacticus.stream_group(parent_group_id);
CREATE INDEX IF NOT EXISTS stream_group_code_idx    ON tacticus.stream_group(group_code);
CREATE INDEX IF NOT EXISTS stream_group_entity_idx  ON tacticus.stream_group(entity);

ALTER TABLE tacticus.stream_event
  ADD COLUMN IF NOT EXISTS group_id     BIGINT REFERENCES tacticus.stream_group(group_id),
  ADD COLUMN IF NOT EXISTS caster_entity INT;   -- entité de l'ancêtre User_UseAbility/NormalAttack/Ability_Attack

CREATE INDEX IF NOT EXISTS stream_event_group_idx  ON tacticus.stream_event(group_id);
CREATE INDEX IF NOT EXISTS stream_event_caster_ent_idx ON tacticus.stream_event(caster_entity);

-- Dégâts attribués par l'arbre : caster_entity (= attaquant via le scope) + mêlée/distance.
-- Recoupe attacker_id (tag) pour validation. Résout l'unité via squad_id.
CREATE OR REPLACE VIEW tacticus.v_damage_tree AS
  SELECT m.battle_id, se.message_id, se.event_id, se.group_id,
         se.caster_entity, se.attacker_id, se.target_id,
         se.amount, se.member_killed, se.weapon_is_melee,
         se.effect_type, se.effect_type_name,
         se.did_crit, se.was_overkill, se.damage_profile_type
    FROM tacticus.stream_event se
    JOIN tacticus.message m USING (message_id)
   WHERE se.step_name = 'UnitDamaged';
