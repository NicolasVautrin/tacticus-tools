-- 015_damage_kind_heal_repair.sql — classification damage_kind + vues soins/répa.
--
-- damage_kind : catégorise chaque UnitDamaged (rempli à l'ingest, a le contexte
-- battle_machines pour détecter l'artillerie MoW) :
--   normal_melee / normal_ranged (weapon_is_melee) · effect (effect_type) ·
--   mow_artillery (attaquant = MoW) · ability (active_ability_type) · unknown.

ALTER TABLE tacticus.stream_event
  ADD COLUMN IF NOT EXISTS damage_kind TEXT;
CREATE INDEX IF NOT EXISTS stream_event_damage_kind_idx
  ON tacticus.stream_event(damage_kind);

-- Soins (HealInfo, step 5) : montant = Amount, soigneur = Caster_Id, cible = entity.
CREATE OR REPLACE VIEW tacticus.v_heal AS
  SELECT m.battle_id, se.message_id, se.event_id,
         se.entity_id AS healed_id, se.caster_id AS healer_id,
         se.amount   AS heal_amount,
         (se.tags->>'UnitStats_WasWoundedBeforeHeal')::int   AS was_wounded,
         (se.tags->>'UnitStats_RemovedNegativeUnitEffects')::int AS cleansed
    FROM tacticus.stream_event se JOIN tacticus.message m USING (message_id)
   WHERE se.step_code = 5;

-- Réparations (RepairInfo, step 6) : pas de tag Amount, et la répa restaure les
-- **PV** (mécanique/MoW), pas l'armure (RemainingArmor=0 sur ces events) → montant
-- = delta de hp_remaining (event moins hp_remaining précédent de l'entité dans la
-- battle, borné >= 0). Cible = entity (unité mécanique / MoW).
DROP VIEW IF EXISTS tacticus.v_repair;
CREATE VIEW tacticus.v_repair AS
  WITH ev AS (
    SELECT m.battle_id, m.apply_seq, se.ordinal, se.event_id, se.entity_id,
           se.step_code, se.hp_remaining
      FROM tacticus.stream_event se JOIN tacticus.message m USING (message_id)
     WHERE se.hp_remaining IS NOT NULL AND se.entity_id IS NOT NULL
  ), d AS (
    SELECT *, lag(hp_remaining) OVER (
               PARTITION BY battle_id, entity_id
               ORDER BY apply_seq, ordinal) AS prev_hp
      FROM ev
  )
  SELECT battle_id, event_id, entity_id, hp_remaining,
         greatest(hp_remaining - coalesce(prev_hp, hp_remaining), 0)
           AS repair_amount
    FROM d
   WHERE step_code = 6;
