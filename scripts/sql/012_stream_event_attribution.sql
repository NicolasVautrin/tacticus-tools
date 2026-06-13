-- 012_stream_event_attribution.sql
-- Promote attribution + combat-quality + lifecycle tags from stream_event.tags
-- (JSONB) to typed columns — same "hot cols" pattern as 007. Lets us attribute
-- damage/kills to the acting entity and analyse combat quality without
-- re-parsing JSONB.
--
-- Why attribution matters: combat events (UnitDamaged, ...) are bucketed under
-- the top-level CheatRunAIMessage (unit_id=0), NOT the sub-message of the real
-- actor. But the actor IS in the event tags (Attacker_Id / Caster_Id), and
-- effect/DoT source is already columned by 007 (effect_source_id) — combine
-- them for full damage attribution (e.g. tyranBiovore deals via effects).

ALTER TABLE tacticus.stream_event
  -- attribution
  ADD COLUMN IF NOT EXISTS attacker_id          INT,   -- Attacker_Id (direct-attack source)
  ADD COLUMN IF NOT EXISTS amount               INT,   -- Amount (damage dealt this hit)
  ADD COLUMN IF NOT EXISTS member_killed         INT,   -- Attack_WasMemberKilled (0/1)
  ADD COLUMN IF NOT EXISTS target_id            INT,   -- Target_Id
  ADD COLUMN IF NOT EXISTS caster_id            INT,   -- Caster_Id (ability/effect caster)
  ADD COLUMN IF NOT EXISTS active_ability_type  INT,   -- Active_Ability_Type
  ADD COLUMN IF NOT EXISTS killed_unit_id        INT,   -- Killed_Unit_Id
  -- combat quality (every UnitDamaged)
  ADD COLUMN IF NOT EXISTS did_crit             INT,   -- Attack_DidCrit (0/1)
  ADD COLUMN IF NOT EXISTS did_block            INT,   -- Attack_DidBlock (0/1)
  ADD COLUMN IF NOT EXISTS did_evade            INT,   -- Attack_DidEvade (0/1)
  ADD COLUMN IF NOT EXISTS was_overkill         INT,   -- Attack_WasOverkill (0/1)
  ADD COLUMN IF NOT EXISTS is_first_hit         INT,   -- Attack_Is_First_Hit (0/1)
  ADD COLUMN IF NOT EXISTS damage_profile_type  INT,   -- DamageProfileType
  ADD COLUMN IF NOT EXISTS weapon_is_melee      INT,   -- Attack_Weapon_IsMelee (0/1)
  -- ability / state
  ADD COLUMN IF NOT EXISTS passive_ability_type INT,   -- Passive_Ability_Type
  ADD COLUMN IF NOT EXISTS transformed          INT,   -- UnitStats_Transformed (flag, 1 when set)
  -- lifecycle (kill / spawn)
  ADD COLUMN IF NOT EXISTS unit_was_overkilled  INT,   -- Unit_WasOverkilled (0/1)
  ADD COLUMN IF NOT EXISTS unit_is_dying        INT,   -- Unit_IsDying (0/1)
  ADD COLUMN IF NOT EXISTS unit_is_summoned     INT,   -- Unit_IsSummoned (0/1)
  ADD COLUMN IF NOT EXISTS unit_spawn_source    INT,   -- Unit_SpawnSource (enum)
  ADD COLUMN IF NOT EXISTS unit_parent_id       INT;   -- Unit_Parent_Id (MoW parts / summoner)

-- Backfill existing rows from JSONB. Absent keys yield NULL (no error); these
-- tag values are always integers in the game's serialization.
UPDATE tacticus.stream_event SET
  attacker_id          = (tags->>'Attacker_Id')::int,
  amount               = (tags->>'Amount')::int,
  member_killed         = (tags->>'Attack_WasMemberKilled')::int,
  target_id            = (tags->>'Target_Id')::int,
  caster_id            = (tags->>'Caster_Id')::int,
  active_ability_type  = (tags->>'Active_Ability_Type')::int,
  killed_unit_id        = (tags->>'Killed_Unit_Id')::int,
  did_crit             = (tags->>'Attack_DidCrit')::int,
  did_block            = (tags->>'Attack_DidBlock')::int,
  did_evade            = (tags->>'Attack_DidEvade')::int,
  was_overkill         = (tags->>'Attack_WasOverkill')::int,
  is_first_hit         = (tags->>'Attack_Is_First_Hit')::int,
  damage_profile_type  = (tags->>'DamageProfileType')::int,
  weapon_is_melee      = (tags->>'Attack_Weapon_IsMelee')::int,
  passive_ability_type = (tags->>'Passive_Ability_Type')::int,
  transformed          = (tags->>'UnitStats_Transformed')::int,
  unit_was_overkilled  = (tags->>'Unit_WasOverkilled')::int,
  unit_is_dying        = (tags->>'Unit_IsDying')::int,
  unit_is_summoned     = (tags->>'Unit_IsSummoned')::int,
  unit_spawn_source    = (tags->>'Unit_SpawnSource')::int,
  unit_parent_id       = (tags->>'Unit_Parent_Id')::int
WHERE tags IS NOT NULL;

CREATE INDEX IF NOT EXISTS stream_event_attacker_idx ON tacticus.stream_event (attacker_id);
CREATE INDEX IF NOT EXISTS stream_event_caster_idx   ON tacticus.stream_event (caster_id);
CREATE INDEX IF NOT EXISTS stream_event_target_idx   ON tacticus.stream_event (target_id);

-- Damage attributed to its source. source_id coalesces direct attacker with the
-- effect source so DoT/spore damage (e.g. tyranBiovore) is credited too. Join
-- with mow_state.machine_id or unit_state.squad_id to resolve the dealer.
CREATE OR REPLACE VIEW tacticus.v_damage_by_caster AS
  SELECT m.battle_id, se.message_id, se.event_id,
         COALESCE(se.attacker_id, se.effect_source_id, se.caster_id) AS source_id,
         se.attacker_id, se.effect_source_id, se.caster_id,
         se.target_id, se.amount, se.member_killed,
         se.did_crit, se.was_overkill, se.weapon_is_melee,
         se.damage_profile_type, se.active_ability_type
    FROM tacticus.stream_event se
    JOIN tacticus.message m USING (message_id)
   WHERE se.step_name = 'UnitDamaged';
