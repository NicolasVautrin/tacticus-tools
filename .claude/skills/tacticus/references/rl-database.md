# RL dataset — base Postgres `TACTICUS`

Schéma de la base qui stocke les battles RL (runner isolé, 0 token) ingérées
depuis les ai-traces. **Lire ceci AVANT toute requête** — ne pas redécouvrir la
structure au coup par coup.

## Connexion

| | |
|---|---|
| db | **TACTICUS** |
| host / port | `localhost` / **5433** |
| schema | **tacticus** (faire `SET search_path TO tacticus`) |
| user / pwd | `postgres` / dans (file:///C:/Users/nicolasv/tacticus-tools/.env) (`PG_PASSWORD`) |

**Python** : utiliser le launcher **`py`** (Python 3.13, a `psycopg2`), PAS `python`
(pas le module). `.env` est gitignored — ne jamais committer le mot de passe.

```python
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, dbname='TACTICUS',
                        user='postgres', password='admin')
cur = conn.cursor(); cur.execute('SET search_path TO tacticus')
```

## Modèle (fait + dimensions, star-schema)

Tout pend de `message`. Chaîne de jointure :

```
batch (1 run rl_collect_batch)
  └─ battle (1 battle)                         FK batch_id
       └─ message (1 message de jeu appliqué)  FK battle_id
            ├─ stream_group (arbre des scopes) FK message_id   ← nesting (014)
            │    └─ stream_event (actions)     FK message_id, FK group_id → table de faits
            ├─ unit_state   (snapshot unités)  FK message_id
            ├─ mow_state    (snapshot MoW)     FK message_id
            └─ ability_state_change            FK message_id + battle_id
       └─ tile_ref (board, 1 par battle)       FK battle_id   PK (battle_id, tile_id)
       └─ move_options_event (vide ici)        FK battle_id

Dimensions (id → libellé) : ref_active_ability, ref_triggered_ability,
                            ref_effect, ref_unit
```

FK déclarées : `*_id → message/battle/batch`, **+ migration 013/014** : colonnes
enum → ref tables (`active_ability_id`, `triggered_ability_id`, `effect_type`,
`visual_id`) et `stream_event.group_id → stream_group`, `stream_group.parent_group_id`
(self).

## Tables (volumétrie indicative ; varie selon la dernière re-collecte ~50 battles MoW)

### `batch` (PK `batch_id`) — 1 ligne / run
`seed, n_battles, game_hash, config jsonb, hooks_sha, started_at`.

### `battle` (PK `battle_id`, FK `batch_id`) — 85
`idx, runner_id, roster_p text[], roster_a text[], mow_p, mow_a, board_id,
engine_seed, ok, final_stage, reached_finished, hit_max_turns, turns_count,
elapsed_ms, err, winner_player_id, winner_team_id, winner_entity_id, outcome,
reason_code, reason_name`. `roster_*` = unitIds (`ref_unit`). `mow_p/mow_a` = MoW
visualId. Joueur = player_id 11 / team 1 ; IA = 12 / team 2.

### `message` (PK `message_id`, FK `battle_id`) — 6 839
`msg_idx, apply_seq, src ('ai'|...), msg_class, unit_id_raw, runner_id, turn,
stage, stage_name, player_on_turn`. Ordre intra-battle = `msg_idx`.
- ⚠️ **`unit_id_raw` du `CheatRunAIMessage` n'est PAS l'unité qui agit** (≠ attacker
  9566/9578 fois) — n'offre aucun contexte de tour. L'acteur se lit via les tags de
  l'event (`attacker_id`, etc.), pas via le message parent.
- ⚠️ **`turn` ≈ horodatage matchState (peu de valeurs), pas un compteur de round.**
  L'ordre/round se reconstruit depuis la séquence `msg_class IN ('MoveUnitMessage',
  'ActiveAbilityMessage')` triée par `msg_idx`. Cf. [[project_turn_order_dynamic]].

### `stream_event` (PK `event_id`, FK `message_id`, FK `group_id`) — **table de faits**
58 colonnes. **action-only** depuis 014 : les events `group`/`finish` ne sont plus
des lignes ici (→ `stream_group`). Identité : `ordinal, kind ('action'), step_code,
step_name, entity_id, target_kind ('unit'|'machine'|'tile'), tags jsonb`
(`group_code` = NULL sur les actions ; le scope est via `group_id`).
- **Hot columns (migration 007)** extraites des tags : `hp_remaining, hp_max,
  armor_remaining, armor_max, members_current, members_max, attack, attack_range,
  movement, active_ability_id, active_ability_cooldown, triggered_ability_id,
  effect_id, effect_type, effect_source_id, effect_level, effect_turns_remaining,
  effect_source_active_ability, effect_source_triggered_ability, unit_owner_id`.
- **Attribution / combat-quality (migration 012)** : `attacker_id, amount,
  member_killed, target_id, caster_id, active_ability_type, killed_unit_id,
  did_crit, did_block, did_evade, was_overkill, is_first_hit, damage_profile_type,
  weapon_is_melee, passive_ability_type, transformed, unit_was_overkilled,
  unit_is_dying, unit_is_summoned, unit_spawn_source, unit_parent_id`.
- `tags` (JSONB) garde **tout** le reste (clés non promues, ex. `UnitStats_*_Override`,
  `Shields_*`, `Match_*`). Pour une clé absente des colonnes : `tags->>'Cle'`.
- **`effect_type`** distingue les dégâts d'effet/overwatch/DoT des attaques d'arme
  (cf. [[project_effect_type_attribution]]) : `1009`=Overwatch_AutoAttack, `5`=Fire (DoT).
  ⚠️ **`effect_id` ≠ `effect_type`** : `effect_id` est un id d'**instance** d'effet
  (PAS l'enum `EffectType`) → aucune FK dessus. Seul `effect_type` est l'enum.
- **Libellés enum dénormalisés (migration 013, stratégie hybride)** — 5 colonnes
  `*_name` text remplies à l'ingest depuis `enum_maps.py` :
  `effect_type_name` (EffectType), `active_ability_type_name` (ActiveAbilityType),
  `passive_ability_type_name` (TriggeredAbilityType), `damage_profile_type_name`
  (DamageProfileType), `unit_spawn_source_name` (SpawnSource). Lisible **sans join**.
- **Arbre de groupes (migration 014)** : `group_id` (FK → `stream_group`, groupe
  englobant immédiat), `caster_entity` (entité de l'ancêtre `User_UseAbility`/
  `NormalAttack`/`Ability_Attack` = unité agissante), et **`weapon_is_melee`
  désormais REMPLI** (réutilise la colonne 012) depuis le `Info`(arme) du scope
  d'attaque. Cf. [[project_stream_group_tree]].

**Catégories de dégâts (UnitDamaged) — comment lire `weapon_is_melee`=NULL :**
`weapon_is_melee` ne s'applique qu'aux **attaques d'arme normales**. Décomposition
des UnitDamaged (≈49 battles) :
- `weapon_is_melee=1` → **mêlée** (attaque d'arme corps-à-corps) ;
- `weapon_is_melee=0` → **distance** (attaque d'arme à distance) ;
- `effect_type IS NOT NULL` → **dégât d'effet/DoT/overwatch** (`effect_type_name`) ;
- `weapon_is_melee NULL` + `effect_type NULL` (le « reste », ~32%) **n'est PAS un
  trou** — il se ventile (analysé via l'arbre) :
  - **~70% dégâts d'ability** (`active_ability_type` rempli, scope `User_UseAbility`/
    `Ability_Attack`) : l'ability frappe sans émettre de `Info` arme → ni mêlée ni
    distance *par nature* (catégorie légitime distincte) ;
  - **~24% artillerie MoW** (attaquant = MoW, scope `Ability_Power` hors cast) :
    pas d'arme mêlée/distance pour de l'artillerie ;
  - **~6% (~98 hits) seul vrai manque** : `NormalAttack_AtomicDamage` sans `Info`
    capturé dans le scope.
- → **colonne `damage_kind` (migration 015)** remplie à l'ingest, qui encode
  directement cette classification : `normal_melee` / `normal_ranged` / `effect` /
  `mow_artillery` (attaquant MoW) / `ability` / `unknown`. (Ordre : effect → melee/
  ranged → MoW → ability → unknown.) Le fallback positionnel borné (015) récupère
  les ~98 ex-ratés → mêlée/distance ~99,5% sur les attaques d'arme.

**Soins & réparations :**
- **HealInfo (step 5)** : `amount` = PV soignés, `caster_id` (= `Caster_Id`, le soigneur),
  `entity_id` = la cible. Tags : `UnitStats_WasWoundedBeforeHeal`,
  `UnitStats_RemovedNegativeUnitEffects` (cleanse). Mix abilities de soin **et vol de
  vie** (un soin sous `Loki_NormalAttack` = lifesteal, pas une ability de soin). Vue `v_heal`.
- **RepairInfo (step 6)** : restaure l'**armure** (`UnitStats_RemainingArmor`,
  `Shields_RemainingAmount`). ⚠️ **Pas de tag `Amount`** → le montant réparé se dérive
  du **delta d'armure** (vue `v_repair`, via `lag(armor_remaining)`).

### `stream_group` (PK `group_id`, FK `message_id`, self-FK `parent_group_id`) — **arbre des scopes (014)**
Un nœud par groupe `StreamDispatcher` (1 `StartGroup` .. 1 `FinishGroup`).
`ordinal_open, ordinal_close, depth, group_code, group_name (GroupType dénormalisé),
entity (qui ouvre le scope), parent_group_id`. Le nesting = `parent_group_id`.
Requiert la capture des marqueurs `finish` (apply-stack.ts) → seules les battles
re-collectées après ce hook l'ont. `GroupType` clés : 12=User_UseAbility,
59=NormalAttack_AtomicDamage, 32=Ability_Attack, 26=Damage, 11=User_MoveUnit.
Walk hiérarchique via `WITH RECURSIVE` sur `parent_group_id`.

### `unit_state` (PK `unit_state_id`, FK `message_id`) — 106 218
Snapshot par UnitFoot à chaque message : `unit_id, squad_id, col, row, hp, hp_max,
owner_id, team_id, visual_id, rank, is_dead`. **Pas d'initiative** (à ajouter si on
veut feature-iser l'ordre). `visual_id` → `ref_unit`.

### `mow_state` (PK `mow_state_id`, FK `message_id`) — 13 678
Snapshot MoW (Machine type-6) : `platform_id, machine_id, col, row, hp, hp_max,
owner_id, team_id, visual_id, rank, initial_slot, is_dead`. `hp`/`col`/`row` souvent
NULL by-design (MoW n'a ni Health ni Position component). Cf. status note.

### `ability_state_change` (PK `ability_state_id`, FK `message_id`+`battle_id`) — 9 218
1 ligne par event mentionnant une ability : `squad_id, kind ('active'|'triggered'),
ability_id, ability_name, cooldown_remaining, can_still_be_used, is_disabled,
is_blocked, blocked_reason_effect_type, level, variable_mult_pct, has_enough_ammo`.

### `tile_ref` (PK `(battle_id, tile_id)`, FK `battle_id`) — 4 872
Board par battle : `col, row, tile_def_id, elevation, is_wall, is_temporary,
is_boss_platform, is_territory, is_in_fog, room_tile_type`.

### `move_options_event` — **0 ligne** (capture move-options non peuplée sur ce dataset).

### Ref tables (dimensions)
| table | clé | autres | source |
|---|---|---|---|
| `ref_active_ability` | `ability_id` int | `name` | `frida/hooks/data/ability-names.ts` |
| `ref_triggered_ability` | `ability_id` int | `name` | `frida/hooks/data/triggered-ability-names.ts` |
| `ref_effect` | `effect_id` int | `name` | enum `EffectType` de `data/dumps/<hash>/dump.cs` |
| `ref_unit` | `unit_id` **text** | `faction, first_seen` | rosters + visual_id déjà ingérés (PAS de `name`) |

## Enums : quelle colonne → quelle ref / quel enum IL2CPP

Stratégie **hybride** (migration 013, générée par `rl_gen_enum_columns.py`) :

**Id-dims grosse cardinalité → ref tables, avec FK déclarée** :
- `active_ability_id`, `effect_source_active_ability` → `ref_active_ability(ability_id)` (FK)
- `triggered_ability_id`, `effect_source_triggered_ability` → `ref_triggered_ability(ability_id)` (FK)
- **`effect_type`** → `ref_effect(effect_id)` (FK ; enum `EffectType`)
- `unit_state.visual_id`, `mow_state.visual_id` → `ref_unit(unit_id)` (FK)
- Sans FK : `ability_state_change.ability_id` (active OU triggered selon `kind`),
  `battle.roster_p/roster_a` (text[] → `ref_unit`). ⚠️ `effect_id` : **jamais** (instance).

**Petits enum-type → libellé dénormalisé `*_name`** (cf. § `stream_event`) :
`effect_type` (EffectType), `active_ability_type` (ActiveAbilityType, 74 val),
`passive_ability_type` (TriggeredAbilityType, 32), `damage_profile_type`
(DamageProfileType, 22), `unit_spawn_source` (SpawnSource, 2). Source = enums IL2CPP
parsés du `dump.cs` du build courant.

**Encore opaques (ni ref ni name)** : `group_code` (48), `kind`, `battle.reason_code`.

**`step_code` → `step_name`** est **déjà dénormalisé** (les deux colonnes existent) —
pas besoin de ref table. Map (enum `StepType`) :

| code | name | code | name | code | name |
|---|---|---|---|---|---|
| 1 StartMatch | 13 ChangeStats | 28 RemoveUnitFromTiles |
| 2 StartTurn | 14 ChangeAbility | 29 Revive |
| 3 ChangePosition | 15 FinishMatch | 30 Info |
| 4 UnitDamaged | 16 ReceiveEffect | 35 UpdateAbilityModification |
| 5 HealInfo | 17 LoseEffect | 36 TransferDamage |
| 6 RepairInfo | 18 ActivateEffect | 37 Resurrect |
| 10 AddUnit | 19 DeactivateEffect | 39 PrepareTurn |
| 12 RemoveUnit | 20 UpdateEffect | 40 ChangeUnitOwner |
| 22 AttackTile | 21 UpdateEffectTurns | 41 UpdateEffectLevel |
| 26 DirectlyKillUnit | 42 UnitFled | 46 RemoveMachine |
| 47 SpendAmmo | 56 AddOrUpdateShield | 57 RemoveShield |

## ⚠️ Espaces d'ids (le piège n°1)

- **`attacker_id` / `target_id` / `caster_id` / `killed_unit_id` / `entity_id` (unit)
  ↔ `unit_state.squad_id`** — **PAS `unit_state.unit_id`**. Join sur `unit_id` =
  tout en NULL. Pour les MoW ↔ `mow_state.machine_id`.
- `entity_id` selon `target_kind` : `'unit'`→squad_id, `'machine'`→machine_id,
  `'tile'`→`tile_ref.tile_id`.
- `owner_id` / `player_on_turn` / `winner_player_id` = PlayerId (11 joueur, 12 IA).
- `team_id` / `winner_team_id` = 1 joueur, 2 IA.
- `visual_id` (text, ex. `'tauCrisis'`) résout l'unité ; `squad_id`/`unit_id`/
  `machine_id` sont des **ids d'entité par-battle**, pas globaux.

## Vues (13)

| vue | contenu |
|---|---|
| `v_damage` | step 4 (UnitDamaged) + victim + hp/armor/members |
| `v_damage_by_caster` | dégâts attribués : `source_id = coalesce(attacker_id, effect_source_id, caster_id)`, + crit/overkill/melee/profile |
| `v_damage_tree` (014) | dégâts via l'arbre : `caster_entity` + `weapon_is_melee` + `effect_type_name`, recoupe `attacker_id` |
| `v_kill` | step 12/26 (RemoveUnit/DirectlyKillUnit) |
| `v_heal_or_repair` | step 5/6/7 (heal/repair/restore_armor) |
| `v_heal` (015) | soins attribués : `healer_id` (Caster_Id), `healed_id`, `heal_amount`, `was_wounded`, `cleansed` |
| `v_repair` (015) | réparations : `repair_amount` = delta `armor_remaining` (pas de tag Amount) |
| `v_position_change` | step 3 |
| `v_effect_received` / `_unit` / `_tile` / `_tile_resolved` | step 16 (ReceiveEffect), résolu unité/tile |
| `v_effect_lost` | step 17 (LoseEffect) |
| `v_ability_state_latest` | dernier état par (battle, squad, kind, ability) |
| `v_overwatch_ready` | unités avec triggered ability dont `ref_triggered_ability.name ~* 'overwatch'` prête |
| `v_mows_per_battle` | MoW distincts par battle |

## Build-hash : les ids enum sont spécifiques au build

Les ids (`effect_type`, ability ids, `step_code`, …) sont émis par **un build IL2CPP
précis**. `ref_effect` + les colonnes `*_name` (parsés de `dump.cs`) **doivent venir
du build qui a produit la donnée** (actuellement **kqkbjqfb6c**). Les deux générateurs
**auto-détectent** le hash de build (dossier unique de
`AppData/Local/tacticus/games/`, hors `.temp`) — plus aucun hash hardcodé ; override
via `$TACTICUS_BUILD_HASH`. **Au changement de build** : re-dump, puis re-générer :

```
py scripts/python/rl_gen_ref_tables.py --apply     # ref_effect/active/triggered/unit (upsert, FK-safe)
py scripts/python/rl_gen_enum_columns.py --apply   # FK + colonnes *_name + enum_maps.py
```

## Ingest & migrations

> ⚠️ **Interpréteur Python (piège vérifié)** : `rl_collect_batch.py` utilise
> **`psycopg` (v3)** → le lancer avec **`python`** (3.14, a psycopg3), **PAS `py`**
> (a psycopg2 seulement). Sous `py`, `_PSYCOPG_OK=False` → **l'ingest est
> silencieusement désactivé** (les battles tournent, rien n'est écrit en PG, aucune
> erreur). Pour les **requêtes/migrations manuelles** en psycopg2, utiliser `py`.
> Résumé : batch → `python` ; requêtes psycopg2 → `py`.

- **Progressif (live)** : `python scripts/python/rl_collect_batch.py` ingère pendant le
  run — **toutes** les colonnes (hot 007, attribution 012, `*_name` 013, arbre 014 :
  `stream_group` + `group_id` + `caster_entity` + `weapon_is_melee`). Chemin par défaut.
- **Post-hoc (fallback)** : `scripts/python/rl_ingest_postgres.py` rejoue
  `summary.json` + JSONL mais n'insère que l'**identité + `tags` JSONB brut** (8 cols) ;
  les colonnes typées dépendent alors du **backfill des migrations** (pas remplies à
  l'insert). Ne pas s'y fier pour les hot/attribution/`*_name`.
- **Générateurs** : `rl_gen_ref_tables.py` (ref tables, upsert), `rl_gen_enum_columns.py`
  (migration 013 + `enum_maps.py`). Tous deux build-aware.
- **Migrations** : `scripts/sql/001_…` → `015_…` (init, winner, messages/events,
  matchstate, unit_state, **006 ref_tables**, **007 hot_cols**, target_kind, tile_ref,
  ability_state, mow_state, **012 attribution**, **013 enum FK + `*_name`**,
  **014 stream_group + group_id/caster_entity**, **015 damage_kind + v_heal/v_repair**).
  Appliquer via `psql -f`, `--apply` des générateurs, ou psycopg2.
- **GroupType** (102 membres) est dans `enum_maps.py` (`GROUP_TYPE`) pour `group_name`.

## Recettes

```sql
-- dégâts par dealer (résolu en nom)
SELECT n.visual_id, sum(v.amount), sum(v.member_killed)
FROM v_damage_by_caster v
JOIN message m ON m.message_id=v.message_id
JOIN (SELECT DISTINCT m2.battle_id, us.squad_id, us.visual_id
        FROM unit_state us JOIN message m2 USING(message_id)) n
  ON n.battle_id=v.battle_id AND n.squad_id=v.source_id
GROUP BY 1 ORDER BY 2 DESC;

-- dégâts d'effet/overwatch/DoT par type (libellé dénormalisé, zéro join — 013)
SELECT effect_type_name, count(*), sum(amount)
FROM stream_event WHERE step_name='UnitDamaged' AND effect_type IS NOT NULL
GROUP BY 1 ORDER BY 3 DESC;   -- Overwatch_AutoAttack, Fire, ...

-- ability/effect id → nom via FK ref table (join, grosse cardinalité)
SELECT ra.name, count(*) FROM stream_event se
JOIN ref_active_ability ra ON ra.ability_id = se.active_ability_id
GROUP BY 1 ORDER BY 2 DESC;

-- mêlée vs distance (arbre 014, weapon_is_melee rempli)
SELECT weapon_is_melee, count(*), sum(amount)
FROM stream_event WHERE step_name='UnitDamaged' GROUP BY 1;  -- NULL = effet/DoT

-- arbre : remonter les ancêtres d'une action (WITH RECURSIVE sur parent_group_id)
WITH RECURSIVE anc AS (
  SELECT g.group_id, g.parent_group_id, g.group_name, g.entity, 0 AS lvl
    FROM stream_group g WHERE g.group_id = (SELECT group_id FROM stream_event
       WHERE step_name='UnitDamaged' AND group_id IS NOT NULL LIMIT 1)
  UNION ALL
  SELECT g.group_id, g.parent_group_id, g.group_name, g.entity, anc.lvl+1
    FROM stream_group g JOIN anc ON g.group_id = anc.parent_group_id)
SELECT lvl, group_name, entity FROM anc ORDER BY lvl DESC;
```
