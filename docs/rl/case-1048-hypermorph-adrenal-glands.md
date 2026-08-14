# #1048 — `Hypermorph` PORTÉ + CONFRONTÉ, `AdrenalGlands` PORTÉ (résidu `#1018-r1` FERMÉ)

Deux passifs de SUMMON, sphère Tyranide / Genestealer. Build `rnca9r7q6c`, session 89.
Ils n'ont **aucun étage commun** — c'est la RE de l'un qui a éclairé l'autre, pas le code.

| item | porteurs | verdict |
|---|---|---|
| `Hypermorph` (`EffectType` 0x54d = 1357) | `genesSmnAberrant` (summon), `genesNpc1Aberrant` (npc) | **PORTÉ + CONFRONTÉ** (4 volets) |
| `AdrenalGlands_Effect` (0x419 = 1049) | `tyranSmnHormagaunt` (summon) + **5** npc Hormagaunt | **PORTÉ + CONFRONTÉ** (3 volets), résidu `#1018-r1` fermé |

## 0. Le montage — `--explicit-stats` suffit pour les DEUX, la voie summon n'a pas été nécessaire

`rl_duel build --explicit-stats <npc|summon>` amène le porteur avec **ses** stats natives
(`UnitProgression$$GetNpcStats` / `$$GetSummonStats`), sans passer par la formule héros qui LÈVE
sur eux. Mesuré : `--explicit-stats genesNpc1Aberrant --explicit-stats genesSmnAberrant` fait
apparaître **deux** Aberrants, l'un au palier 1 (75 PV), l'autre au palier 50 (4154 PV), tous deux
avec `Hypermorph` dans `decisionView.effects`.

⚠ La voie summon canonique (spawner `genesBiophagus` → active `AberrantHypermorph` 1166) reste
**NON EMPRUNTÉE**, et c'est un choix : aucune des deux magnitudes ne lit le caster ni le vecteur de
pose. Ce qui n'est donc **pas** couvert : le comportement au moment PRÉCIS de l'apparition
(`SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`).

⚠ `--unit-stat <id>:Health=N` écrit le **MAX**, pas les PV courants (mesuré : `health` reste 75,
`healthMax` passe à 2000, `statDelta.health = -1925`). Pour forcer les PV COURANTS c'est
`--hp-player` / `--hp-target`.

---

## 1. `Hypermorph` (1357) — le passif de l'Aberrant

i2 : « Gains extra Damage equal to `{healthPct}`% of current Health. » ; `constants = {healthPct: 15}`.

⚠ **NE PAS CONFONDRE avec `AberrantHypermorph` (`ActiveAbilityType` 1166)**, l'ACTIVE de
`genesBiophagus` qui invoque ce summon. Deux noms voisins, deux ids sans rapport.

```
HypermorphAbility$$CreateTrigger   = <DSLTriggers+0x30>
                                   | ( On(0x1e = HealthChanged, ownerNeedsToBeAlive: true)
                                       & get_OwnerIsTarget )
HypermorphAbility$$CreateBehaviour = RemoveEffect(Owner@<DSLSelectors+0x30>, Nullable(0x54d))
                                   + AddDynamicStatModifierEffectToOwner(0x54d, statType = 0 Attack,
                                                                         turns = null, isHidden = false)
```

`<DSLTriggers+0x30>` est LU sur CE build dans `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` :
`On(0x21 = AbilityInit) & <this+0x70 = YesTrigger> & get_OwnerIsActor` (et `+0x38` = le même avec
`On(0x41)`). C'est donc un passif d'**INIT** → `ABILITY_INIT_OWNER_EFFECTS`, **plus** un recalcul à
chaque changement de PV du porteur. Le couple RETIRE-puis-REPOSE **est** le mécanisme de recalcul.

```
HypermorphEffect$$GetDynamicStatModificationAmount(owner, target, effect) =
    (int)( Fix64(GetStat(target, 5 Health, 0 Current))
           * Fix64.Round(Fix64(GetNumberConstant(0x4f = healthPct)) / 100 * 100, 0) / 100 )
```

Signature `owner, target, effect -> Nullable<Int32>` LUE dans `frida/methods.tsv` ;
`AddDynamicStatModifierEffectToOwner` met `Owner@<DSLSelectors+0x30>` en source **et** en cible,
donc `target` == le porteur.

### Le `-1` de Fix64 n'est pas une approximation, c'est le résultat natif

`op_Explicit` est un **FLOOR** et `15/100` vaut `0.14999999997671694` en Q31.32 (`op_Division` =
round-half-up sur un quotient accumulé à 2⁻³³). Le round intermédiaire (`/100 * 100` puis `Round`)
rattrape la PREMIÈRE division (14,99999999 → 15,0 exact) ; la SECONDE n'a pas de rattrapage.
⇒ **le natif rend une unité de MOINS que la règle de trois dès que `hp × healthPct / 100` tombe
sur un entier** — soit, à `healthPct = 15`, sur **200 des 4000** premiers PV, tous multiples de 20.

### GROUND TRUTH (`combatSnapshot.statDelta.attack`)

| PV | natif | port | règle de trois |
|---|---|---|---|
| 2000 (`--hp-player 2000`) | **299** | 299 | 300 |
| 900000 (`--hp-player 900000`) | **134999** | 134999 | 135000 |
| 75 (palier 1) | 11 | 11 | 11 |
| 4154 (palier 50) | 623 | 623 | 623 |
| 877274 (après le tour adverse) | **131591** | 131591 | 131591 |

Les PV **naturels** des deux porteurs (75, 4154) confirment la magnitude sans jamais exercer le
quirk : c'est `--hp-player 2000` qui sépare les deux hypothèses. La dernière ligne est le volet
RECALCUL — le porteur encaisse, ses PV bougent, le bonus **suit**.

### Côté port

`EFFECT_CLASSES["Hypermorph"]` + `ABILITY_INIT_OWNER_EFFECTS["Hypermorph"]`. La magnitude est lue
**à la lecture** (`applied_stat_mods(stats_ctx)`, forme OVERRIDE d'`ApplyModification`, le mold de
`ReinforcedHiveNodeExtraArmorEffect`) et re-posée par `refresh_stat_modifier_effects`
(`ValueModification.Modify` = replace par-source) : même observable, sans modéliser la
destruction/reconstruction de l'entité-effet.

---

## 2. `AdrenalGlands` (1049) — le résidu `#1018-r1`, et ce qui manquait vraiment

`case-1018` avait la RE complète et concluait : *« l'étage manquant côté port n'est pas l'effet :
c'est TOUTE la chaîne »*. C'est exact, et c'est cette chaîne qui est livrée ici.

```
engine/services/range_bonus.py                 EffectRangeBonus / RangeBonus / MovementBonusContext
engine/entities/effects/base.py                create_range_bonus_for_movement (slot +0x698)
                                               range_bonus_for_movement (gate Trigger + conversion)
engine/entities/effects/loki/adrenal_glands.py IsValidExtraMove
                                               IsNearestTileToMoveToMeleeWithEnemy
engine/services/movement_query.py              GetRangeBonusForUnit
                                               MovementRangeWithAppliedBonus
                                               GetExtraReachableTiles
                                               + le branchement dans get_movable_tiles_for
```

**Les deux structs, offsets LUS** (pas devinés) : `EffectRangeBonus` (0x20 o) =
`{Trigger@+0x00, ExtraRange@+0x08, ExtraRangeCondition@+0x10, ReduceRange@+0x18}` ;
`RangeBonus` (0x18 o) = `{ExtraRange@+0x00, ExtraRangeCondition@+0x08, ReduceRange@+0x10}`.

**L'asymétrie est le cœur du passif** : `MovementQuery$$MovementRangeWithAppliedBonus` ne lit QUE
`ReduceRange` (nul ici) → AdrenalGlands **n'augmente pas la portée brute**. Tout passe par
`GetExtraReachableTiles`, une tuile à la fois, chacune devant satisfaire `IsValidExtraMove`.

`AnyOrFillMoveableTiles`, l'ordre réel (mirror du branchement) :

```
range = MovementRangeWithAppliedBonus(unit, baseRange, rangeBonuses)   # ReduceRange SEUL
r     = GetReachableTiles(start, type, range, unit)                    # le pathfinding
defaultReachableTiles.AddRange(r) ; r.RemoveAll(!IsMovableTile) ; result.AddRange(r)
foreach (b in rangeBonuses) {
    extra = GetExtraReachableTiles(defaultReachableTiles, type, unit, b)
    extra.RemoveAll(!IsMovableTile)
    defaultReachableTiles.AddRange(extra) ; result.AddRange(extra)     # ACCUMULE d'un bonus au suivant
}
```

Slots `IPathfinders` LUS dans `data/symbols/<build>/metadata/interface_slots.tsv` :
**5** = `IsValidContinuePathTile` (3 args), **2** = `IterateReachableTiles` (4 args) ;
slots `IBattleQuery` : **19** = `GetPathTo`, **79** = `GetAdjacentTiles`, **125** = `GetAdjacentEnemies`.

### Le pseudo-C Ghidra confond deux registres, et le discriminant n'est pas le pseudo-C

Dans `IsNearestTileToMoveToMeleeWithEnemy`, Ghidra écrit `IsWalkable(tile)` / `IsFreeTile(tile)` là
où la boucle porte sur `t` : le `while (tile == t) continue` juste au-dessus n'a de sens que si la
suite porte sur `t`, et `tile` étant par construction une DESTINATION de mouvement (donc walkable
et libre), lire `tile` rendrait les deux filtres invariants — donc inertes.

### GROUND TRUTH — et le premier montage était DÉGÉNÉRÉ

Oracle = `aiMovableTiles` (les tuiles où le natif autorise l'arrêt).

| montage | natif | port (avec) | port (sans bonus) | verdict |
|---|---|---|---|---|
| Hormagaunt @(2,2), ennemi @(2,5) | 26 | 26 | **26** | ACCORD SANS PREUVE — le bonus n'ajoutait RIEN |
| Hormagaunt @(2,2), ennemi @(3,7) | **27** | **27** | **26** | le bonus ajoute `(3,6)` et une seule |

La seconde position est **choisie par balayage du board** : aucun voisin de `(3,7)` n'est à ≤ 3 pas
du porteur, un seul — `(3,6)` — est à exactement 4. Troisième volet : avec `ExtraRangeCondition`
neutralisée, le bonus ajouterait **12** tuiles au lieu de 1 → la condition FILTRE, elle n'est pas
décorative. Et les deux unités SANS le passif rendent 11/11 des deux côtés (rayon de souffle).

### Rayon de souffle — nul en RÉSULTAT, et MESURÉ en COÛT

`get_movable_tiles_for` est le foyer de tout le mouvement du moteur. `BaseEffect.
create_range_bonus_for_movement` rend `None` par défaut ⇒ `get_range_bonus_for_unit` rend `[]` et
les deux étages sont des no-op **exacts** — c'est aussi le régime natif quand `rangeBonuses` est vide.

Le coût, lui, se mesure (session 89, MC1_67, ms/appel) :

| | non-porteurs | porteur |
|---|---|---|
| `get_movable_tiles_for` | **0,08 – 0,16** (identique à `master`) | **2,4** (dont ~1,9 de `GetExtraReachableTiles`) |
| l'étage `get_range_bonus_for_unit` seul | 0,007 | 0,48 |

Le **pré-filtre** teste la SURCHARGE du hook sur la liste BRUTE d'effets, avant toute évaluation de
`CreateActiveCondition` : il ne change AUCUN résultat (un effet qui ne surcharge pas rend `None` par
construction) et évite les **0,358 ms** d'`active_effects` sur une unité riche en conditions portées.
⚠ Le premier commentaire écrit à cet endroit annonçait « 0,2 → 4,7 ms y compris sur les unités sans
effet à hook » : la ventilation par unité l'a **réfuté** (les non-porteurs coûtent 0,007 ms). La
mesure globale était dominée par le porteur.

---

## 3. Ce qui n'est PAS couvert

* **`movement_range_with_applied_bonus`** : la queue native
  `if (HasTriggeredAbility(unit, 0x4b8) || HasTrait(unit, 0x418 Stationary)) return 0;` n'est pas
  reproduite dans ce foyer. Le volet `Stationary` l'est déjà en aval (`get_movable_positions_for`,
  #91) ; le volet `HasTriggeredAbility(0x4b8)` n'a aucun porteur confronté. → résidu **`#1048-r2`**.
* **`RangeBonusForDangerZone`** (slot d'interface 0x20, branche `isDangerZone` de
  `GetRangeBonusForUnit`) : son unique appelant natif est l'affichage de la zone de danger.
* **`ignoreSteppables: false`** de `GetAdjacentEnemies` : le port n'a pas de canal `Steppable` sur
  l'adjacence d'unité (dégradation PERMISSIVE, inerte tant qu'aucun ennemi steppable ne côtoie un
  Hormagaunt). `IsTemporary` d'`IsFreeTile` et `checkFog` d'`IsWalkable` : résidus déjà nommés
  ailleurs (`walk_pathfinder`, `entities/selectors/tiles.py`).
* **L'écart VOL** de `GetExtraReachableTiles` : le natif alimente `defaultReachableTiles` avec le
  retour BRUT de `GetReachableTiles`, le port avec `visited` (déjà filtré `IsMovableTile`). Pour la
  MARCHE l'écart est NUL (l'arête exige déjà `IsWalkable`) ; aucun porteur volant de `RangeBonus`
  n'existe dans le build.
* **La voie SUMMON** des deux passifs : `tyranSmnHormagaunt` et `genesSmnAberrant` n'ont pas été
  amenés par leur summoner. Les deux mécaniques ne lisent ni le caster ni le vecteur de pose, et le
  summon `genesSmnAberrant` a bien été confronté par `--explicit-stats` — mais l'instant de
  l'apparition n'est pas mesuré.
* **`Hypermorph`** : aucune mesure du `RemoveEffect` explicite (le port ne détruit pas l'entité-effet,
  il relit la magnitude) ; aucune mesure sur un porteur à 0 PV.

## 4. Artefacts

* `scripts/python/probe_1048_hypermorph.py` (4 volets), `probe_1048r1_adrenal_glands.py` (3 volets)
* `scripts/python/tests/engine/test_1048_hypermorph_offline.py` (16),
  `test_1048r1_adrenal_glands_offline.py` (8)
* Cliquets transverses rejoués : `test_ctx_traits_substrat_ventilation_offline` (il a MORDU — le
  site neuf `_path_counts` lisait `ctx.traits` en brut ; il passe désormais par le FOYER
  `entity_trait_names`, ce qui est aussi plus fidèle), `probe_313` (cache re-indexé), `probe_570r5`,
  `test_437_r1_face_lists_cells_offline`, `test_270r2_partition_foyers_offline`,
  `test_1041_kit_item_voies_offline`, `test_951r2_voies_de_couverture_offline`,
  `test_refresh_active_flag_discriminant_offline`, `test_camo_seed_inventory_offline`,
  `test_337_dsl_triggers_attestation_offline`, `test_570r5_ordre_de_seeding_offline`,
  `test_1015_trait_channels_offline`, `test_enum_mirror_ratchet_offline`.
* **ROUGES DE BASELINE, non causés par cette tranche** (vérifié : ils accusent des fichiers hors du
  diff) : `test_589r1_tiles_moved_consumers_offline::test_aucun_trigger_a_SEUIL_n_est_porte`
  (accuse `MastersOfManoeuvre` dans `engine/entities/triggers.py`, déjà présent au commit de
  lancement `47550335`) et `probe_468_collision_numeros` `FAIL(6)`.
