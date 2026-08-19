# #10039-r1 — la FORGE a périmé 21 gardes, et son témoin élargi a trouvé deux mirrors faux

`data/seed-bc.json` n'est plus une **capture** (175 entrées, 4 npc, figée sur `gqfc5mff6c`) mais
une **forge** : 717 entrées produites par `Idun.Source.IdunBattle.View.BattleConfigBuilder`
(`forge_seed_bc.py`) contre le build et le gameconfig **courants** — `lineup` 127/127,
`summons` 65/65, `npc` 489/491.

**21 tests offline rouges → 0** (25 avec les 4 de `test_237r1`, qui préexistaient sur `master`
et ne figuraient pas dans l'inventaire). Aucun ne signalait un bug : ils épinglaient une
**prémisse**. Mais l'oracle élargi, lui, en a montré **trois**.

## 1. Deux branches du mirror npc, jamais confrontées, toutes deux FAUSSES

Les 4 npc de la capture étaient tous non-MoW et tous pourvus d'un passif. Deux branches de
`catalog_inject` n'y étaient donc **structurellement pas atteignables** — même régime dégénéré que
le `NPC` posé à tout `kind == npc` (`78a574c7`), que 4 entrées ne pouvaient pas non plus distinguer.

| mirror | ce qu'il faisait | ce que dit le natif | écart |
|---|---|---|---|
| `npc_progression_multiplier_pct` | indexait `units.heroProgressionSteps` | `IdunMetaLogic.UserProgress.UnitConfigUtil$$GetAbilityVariablesMultiplierPercentageForProgressionIndex` branche AVANT d'indexer : `IsMachineOfWar` ⇒ `unitsConfig+0x88` (`heroProgressionStepsMoW`), sinon `+0x80` ; champ `+0x24` | 11 npc MoW, **180** rendu contre **165** écrit |
| `npc_stats` → `PassiveAbilityLevel` | `ab if passiveAbilities else 1` | `IdunMetaLogic.UserProgress.UnitProgression$$GetHierarchyForAbility` : `Primary` **uniquement** pour `BaseUnitConfigDto.PrimaryAbility` (= `config+0x78[0]`, la 1ʳᵉ active), `Secondary` pour **tout le reste** du kit — donc aussi une **deuxième active** | 12 entrées à 2 actives / 0 passif rendaient **1** au lieu d'`AbilityLevel` |

Règle B vérifiée **507/508** avant lecture, puis **lue** au décompilé. Effet sur
`npc_witness_diff` : **29 divergences → 6**, toutes sur `LootObj_CoinCrate:23` (§4).
Contre-épreuve : défaire A rend 11 divergences, défaire B en rend 12, vider l'épingle en rend 1.

## 2. Un test devenu VACUEUX — trouvé par contre-épreuve, pas par lecture

`test_le_rattrapage_repare_exactement_les_configs_dability_qui_derivent` comparait deux ensembles
calculés indépendamment. Mais le catalogue forgé **ne dérive plus** (0 config) : l'égalité se
réduisait à `set() == set()`, vraie même si `refresh_ability_configs` ne faisait plus rien.
Mesure : le mutant « rattrapage INERTE » de `probe_254bc --step 4` passait **VERT**.

Trois gardes avaient la même forme, et les trois **fabriquent** désormais leur cas au lieu de
l'attendre d'un accident de build :

* celle-ci (dérive d'ability fabriquée) ;
* le **3ᵉ terme** de `#380` (`base`), qui seul sépare « la base a dérivé » de « la fixture a
  patché » — il n'était exercé que parce que la capture était périmée ;
* le bras `clone` de `probe_226`, **neutralisé une seconde fois** par une autre porte que `#375` :
  « énumérer les configs manquantes » rendait `[]` puisque `BC.Abilities` porte tout le roster.
  Il **retire** maintenant les configs, et **remplace** l'entrée `Units` homonyme au lieu de s'y
  ajouter — `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig` rend la **première** entrée qui
  matche, donc un clone posé en queue n'aurait jamais été lu.

## 3. Les épingles re-dérivées (aucune assertion affaiblie, aucun seuil substitué)

| épingle | avant | après | ce qui a changé |
|---|---|---|---|
| `STALE_UNIT_ENTRIES` | 1 (`necroOverlord`) | **26** | la péremption **inter-build** a disparu ; ce qui reste est l'**état JOUEUR** |
| `MISSING_LINEUP_ENTRIES` | 21 | **0** | l'**état 3** de la gate de confrontabilité est **vide** : plus un héros n'exige `write_augmented_seed_bc` |
| `MISSING_NPC_ENTRIES` | — | **2** | les npc passent de « rapportés, jamais gardés » (487 absents) à **épinglés nominalement**, gardés dans les deux sens |
| configs de relique absentes | 29 | **11** | et le critère se **dérive** : une config est au catalogue **ssi** une entrée la porte en `TertiaryAbility` (bijection 21/21) |
| ventilation relique | 4 / 52 / 9 | **4 / 61 / 0** | les 9 hors-pool sont entrés au catalogue |
| `#1044-r2` | 14 / 0 / 98 / 63 / 47 sur 175 | **17 / 0 / 438 / 262 / 233 sur 717** | `perdent` reste **0** (structurel) ; le verdict **tient et se renforce** : 3,4× → 13,7× |

**L'attribution est un CROISEMENT, pas un récit.** Les 20 entrées `lineup` divergentes sont
exactement celles dont le catalogue porte `ActiveAbilities` / `PassiveAbilities` **vides** — la
fabrique énumère l'`IUnitProgression` du compte, donc une unité non possédée sort à Rank 0 avec ses
abilities non débloquées, quand `synthesize` lit le kit complet du gameconfig. Croisement
(BC vide) × (divergente) : **107 / 20**, les **deux** cellules de contre-exemple à **ZÉRO**
(`catalog_inject.player_state_gap`).
⚠ **`Rank == 0` ne suffirait pas** : 48 entrées `lineup` y sont, 20 seulement divergent —
`thousDaemonPrince` est Rank 0 / StarLevel 0 / Rarity 0 **avec** ses deux actives.

## 4. Ce qui reste FAUTIF, et qui l'est côté FORGE — pas côté mirror

`LootObj_CoinCrate:23` sort du **repli HÉROS** (`VisualId` suffixé, `Weapons: null`, progression à
zéro) alors que ses jumelles `:1` et `:18` sortent correctes ; 7 ids sont en **double** (25 entrées
surnuméraires) ; 5 `GuildBoss*Npc*` sont au catalogue et **absents du gameconfig**. Les trois sont
**épinglés** (`STALE_UNIT_ENTRIES`, `NPC_WITNESS_STALE`) donc visibles — résidu **`#10039-r2`**.

## 5. Deux gardes qui ont changé de nature

* **SUPPRIMÉE** — `test_la_derive_du_bloc_units_est_attribuee_a_la_migration_de_build` attribuait
  la dérive de `necroOverlord` à la MAJ `gqfc5mff6c` → `rnca9r7q6c` par les deux tables d'enum
  archivées. Cette dérive **n'existe plus** (même build des deux côtés) : la garde serait restée
  **VERTE en expliquant un phénomène disparu**. Remplacée par l'attribution à l'état joueur, qui
  porte ses contre-exemples ; `probe_254bc` étape 2 suit et **vérifie que l'ancien accusé ne
  revient pas**.
* **RETOURNÉE** — `#270-d` gardait par l'**absence de cas** : `astarLysander`, seul porteur, n'était
  pas dans la capture. Il est dans la forge, et le **JEU écarte `ImperialFists` exactement comme le
  filtre**. Le test confronte désormais le filtre à la fabrique native au lieu de l'éviter : ce
  n'est plus une conséquence du typage, c'est un comportement **observé**.

## Fichiers

* mirror + épingles : `scripts/python/catalog_inject.py`
  (`npc_progression_multiplier_pct`, `npc_stats`, `NPC_WITNESS_STALE`, `npc_witness_unpinned`,
  `player_state_gap`, `MISSING_NPC_ENTRIES`, `CATALOG_GAP_PINS`)
* contre-épreuve adversariale : `scripts/python/probe_254bc_seed_bc_units_perime.py`
  (**13 mutants, 13 rouges**, contrôle sans mutation vert)
* montages réparés : `probe_226_seed_bc_ability_configs.py`,
  `probe_419r1tr12r2_stats_npc_summon.py` (étage 1)
* gardes : `tests/engine/runner/test_catalog_inject_offline.py`,
  `tests/test_237_relic_equip_offline.py`, `tests/engine/test_237r1_equip_relic_catalogue_offline.py`,
  `tests/engine/test_1044r2_forcage_traits_offline.py`,
  `tests/engine/test_419r1tr12r2_stats_npc_summon_offline.py`,
  `tests/test_380_seed_bc_patch_survival_offline.py`,
  `tests/engine/test_270d_catalog_traits_enum.py`

**Re-dériver les chiffres, ne pas citer cette page** : ils bougent au prochain re-forgeage.
