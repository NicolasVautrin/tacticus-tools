# #419-r1-tr12-r2 — un chemin de stats EXPLICITE pour les NPC et les SUMMONS

Débloqueur de harnais, pas correctif ponctuel. Il porte **toute la classe** des mécaniques dont le
seul porteur est un npc ou un summon — aujourd'hui confrontables par **greffe** de l'ability sur un
héros du pool, et seulement quand le corps natif ne lit ni stats, ni traits, ni armes du caster.

## 1. Le verrou, mesuré des deux côtés

`buildNormalizedBC` calcule **toutes** les stats par un seul chemin,
`IStatsFormula.StatsUsingProgressionIndexFor` — la formule des **héros**. Une unité sans table de
progression de héros y lève ; le RPC la range dans `skipped` et elle n'atteint jamais le pool de
`--p-units`.

Mesuré **live** (session 10, build `rnca9r7q6c`), sur `admecNpc3Electropriest:33` injecté au
catalogue :

| chemin | `normalized` | `skipped.reason` | Health | Damage | FixedArmor |
|---|---|---|---|---|---|
| formule héros (désarmé) | **non** | `v2 patch: system error` | **0** | 0 | 0 |
| explicite (armé) | **oui** | — | **5303** | 1765 | 490 |

Les deux lignes sont **confrontées live**. Côté armé, le npc entre au roster contrôlé avec ses
valeurs de catalogue, son `Movement` 3 et son arme de mêlée :
`u83 [admecNpc3Electropriest] HP5303 move3 melee`.

## 2. Le natif a DEUX autres chemins, et ils ne se ressemblent pas

### NPC — la table est dans le gameconfig

```
IdunMetaLogic.UserProgress.UnitProgression$$GetNpcStats(unitId, level)
  -> $$GetTieredUnitConfig(unitId, kind = 1)
  -> idun.meta.extensions.UnitConfigExtensions$$GetStatsForLevel(config, level)
  -> IdunMetaLogic.UserProgress.Model.UnitStats$$Init(stats, row)
```

`GetStatsForLevel` = `stats[Math.Min(ToZeroBasedIndex(level), Count - 1)]` — **clamp HAUT
seulement**. `idun.Idun.Source.Shared.UnitLevelExtensions$$ToZeroBasedIndex` **lève** sur
`level <= 0` (pas de clamp bas). Le `level` est le suffixe `:<n>` de l'unitId, lu par
`idun.shared.UnitNamingConventions$$GetLevelFromUnitId` : `split(':')`, `Int32.TryParse` de la 2ᵉ
part, et **défaut 1** — ni 0 (qui ferait lever), ni le dernier palier.

**491 des 491 npc** du gameconfig portent cette table `stats[]`.

Champs de progression, recopiés par
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` : `Rank` ← `row.Rank`,
`StarLevel` ← `row.StarLevel`, `Level` ← `row.AbilityLevel`, et
`AbilityVariablesMultiplierPercentage` ← `heroProgressionSteps[row.ProgressionIndex]
.abilityStatMultiplierPct` — **indexation directe** par le progression index, mirror de
`IdunMetaLogic.UserProgress.UnitConfigUtil$$GetAbilityVariablesMultiplierPercentageForProgressionIndex`.
C'est le point où le npc **diffère** du héros : `ability_multiplier_pct` doit *deviner* le palier
d'un héros non possédé (premier `maxRank >= rank`) ; pour un npc l'index est **écrit dans sa
ligne**.

⚠ `ActiveAbilityLevel` / `PassiveAbilityLevel` ne viennent **pas** de la ligne.
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$SetupAbilities` les prend des slots `0x1c` /
`0x1d` d'`IUnitModel` (`GetPrimaryAbility()` / `GetSecondaryAbility()`, champ `+0x08`) et les écrit
en `UnitConfiguration+0xb8` / `+0xbc`. Sans ability de cette hiérarchie il n'y a aucun niveau à lire
et le champ reste au **défaut 1**.

### SUMMON — la table n'existe pas, les stats sont dans l'ABILITY

```
IdunMetaLogic.UserProgress.UnitProgression$$GetSummonStats(constantType, abilityConfig)
```

Les **65** summons du gameconfig n'ont **aucun** `stats[]`. Le natif lit, par
`idun.meta.StatefulAbilityConfiguration$$GetVariableForLevel`, les variables `summon*` de
l'ability qui invoque :

| champ | régime PRIMARY | régime `_2` |
|---|---|---|
| `Health` | `summonHp` (41) | `summonHp_2` (67) |
| `Damage` | `summonDmg` (42) | `summonDmg_2` (68) |
| `FixedArmor` | `summonArmor` (43) | `summonArmor_2` (69) |
| `CritChance` | `summonCritChance` (84) | `…_2` (88) |
| `BlockDamage` | `summonBlockDmg` (85) | `…_2` (89) |
| `BlockChance` | `summonBlockChance` (86) | `…_2` (90) |
| `CritDamage` | `summonCritDmg` (87) | `…_2` (91) |

`isPrimary = (constantType == unitId(0) || constantType == unitToSpawn(8))`, lu tel quel au
décompilé. L'overload de sélection essaie `unitToSpawn` puis `unitId` (kind 0), ou `unitId_2`
(kind 1). Une variable **absente ou nulle laisse le champ inchangé** (`if (var != 0)`).

## 3. Ce que le catalogue porte VRAIMENT pour un summon — et pourquoi ça change le verdict

**Mesure : les 65 entrées summon du seed BC capturé portent `Health = 0`, écrit PAR LE JEU.**

Donc écrire des stats non nulles sur une entrée summon **n'est pas** un mirror du catalogue : c'est
un **montage** qui reproduit l'état **post-spawn** — le natif les pose au spawn, en `StatModifier`,
par `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$GetStatsToOverride`, sur une unité déjà
construite depuis sa `UnitConfiguration`. Les deux régimes sont donc **séparés** et
`catalog_inject.explicit_stats` les **nomme** : `source = "npc"` (mirror de catalogue) vs
`source = "summon-spawn"` (montage).

Corollaire pour ce résidu : **le porteur confrontable de `1303 ElectroShock` est le NPC.**
`admecNpc3Electropriest` porte exactement le même kit que `admecSmnElectropriest` — mêmes
`passiveAbilities` (`VoltagheistField`, `ElectroShock`), même arme (3 hits `Particle`), même
`Movement` 3 — la seule différence étant le trait `Summon`. Et lui a une table de stats.

## 4. Le témoin — non nul, non dégénéré, et il n'est pas de notre côté

Le mirror npc est confronté aux entrées npc que **le jeu** a écrites dans le seed BC capturé. Ce
n'est pas un accord entre deux lectures de la même table : à gauche le gameconfig vivant, à droite
la sortie de `BattleConfigBuilder$$GetUnitConfiguration` en bataille réelle, figée par la capture.

**4 npc × 14 champs = 56 champs confrontés, 0 divergence.** Health du témoin =
`[198, 151, 222, 100]` — non nul, donc pas de régime dégénéré.

Une divergence a été trouvée puis **expliquée, pas ajustée** : `necroNpc1Warrior:7` portait
`ActiveAbilityLevel = 1` là où sa ligne dit `AbilityLevel = 17`. C'est le seul des 4 sans
`activeAbilities` — d'où le §2 sur `SetupAbilities`.

**Second témoin, celui-là LIVE et indépendant** : `MasterOfTheTutelaries` déclare
`thousSmnPinkHorror` en `unitId` (PRIMARY) et `thousSmnScreamer` en `unitId_2` (SECONDAIRE), et
porte les **deux** jeux de variables (`summonHp[50] = 1994`, `summonHp_2[50] = 2493`). Le mirror
rend **4487** pour le Screamer au multiplicateur 180 — exactement la valeur mesurée live par #202c
(runner 183) et citée dans `engine/runner/operations/spawn.py`. Le régime PRIMARY aurait donné
**3589**.

## 5. Les deux régimes, chiffrés

| | Health | Damage | FixedArmor |
|---|---|---|---|
| `admecNpc3Electropriest:33` (npc, Rank 17) | **5 303** | 1 765 | 490 |
| `admecNpc3ElectropriestSurv` (npc, Rank 17) | **69 238** | 47 656 | 16 248 |
| catalogue **avant** le chemin explicite | **0** | 0 | 0 |
| 98 héros normalisés rank 17 (formule HÉROS) | 5 522 … 12 551 | | |

Aucun des 98 héros ne porte exactement un des deux Health npc. Et les deux paliers npc, tous deux
« Rank 17 », diffèrent d'un facteur 13 : **la table discrimine là où le rank ne discrimine pas**.

## 6. Ce qui est CONFRONTÉ, et ce qui ne l'est pas

**Confronté offline** (20 gardes, `test_419r1tr12r2_stats_npc_summon_offline.py`) : le témoin npc
(4/4), le témoin live `_2` (4487), l'indexation (défaut 1, clamp haut, refus de `level <= 0`,
paliers voisins), le multiplicateur par progression index, le zéro du catalogue summon (65/65), le
refus des déclarants ambigus, le filtre du multiplicateur de rareté.

**Confronté live** : les DEUX faces du verrou. Désarmé — `skipped.reason = 'v2 patch: system
error'`, stats à 0. Armé — le npc entre au pool avec `hp = 5303`, et le montage complet de §11 en
dépend de bout en bout. Le chemin ne peut pas rendre un faux vert : `_normalize_and_extract_pool`
**lève** quand `explicitStats` est fourni et que le RPC n'honore aucune entrée (champ `explicit`
vide), et `explicitUnmatched` fait lever de même.

**NON CONFRONTÉ** : le régime `summon-spawn` (§2), qui n'a été exercé par aucun montage live —
résidu `#419-r1-tr12-r2-r2` (§9). Et les 9 summons du résidu `#419-r1-tr12-r2-r1`.

## 7. Ce qui a été ÉPROUVÉ contre soi-même

`probe_419r1tr12r2_mutants_garde.py` mute le fichier livré, rejoue la garde, restaure — et **lève
si un motif est introuvable** (un remplacement qui ne matche pas produirait un vert trompeur, piège
mesuré par la tranche 12).

**8 mutants sur 8 font rougir la garde** : clamp bas au lieu de lever, défaut de level = dernier
palier, absence de clamp haut, multiplicateur cherché par rank, régime `_2` ignoré, balayage des
déclarants restreint à `unitId`, ambiguïté tranchée en silence, `source` indistincte.

**1 mutant est INERTE, déclaré et démontré** : remplacer `if (var != 0) continue` par un
écrasement inconditionnel écrit `0` là où le champ valait déjà `0` — la valeur de départ d'un
summon **est** 0, donc les deux formulations sont algébriquement identiques dans ce régime. Le
garde reste écrit parce que c'est ce que dit le décompilé ; le probe **rougit** si cet inerte se
met à mordre (sa démonstration serait périmée).

⚠ Deux tests ont dû être **réécrits parce qu'ils étaient faux**, pas parce que le code l'était :
un premier balayage « `summonArmor` non flaggé » rendait **0 cas** parce que son critère était trop
étroit ; le balayage exhaustif en trouve **11**, et `PhasalSubjugator` (aucun
`variablesAffectedByRarityBonus`) sert désormais de vraie contre-épreuve du filtre.

## 8. Livré

* `frida/hooks/features/normalize-bc/json-build.ts` — `explicitStats` / `explicit` /
  `explicitUnmatched`. Injecté et confronté live (§1, §11).
* `scripts/python/catalog_inject.py` — `npc_stats`, `summon_stats`, `explicit_stats`,
  `apply_explicit_stats`, `npc_witness_diff`, `unit_level_from_id`,
  `npc_progression_multiplier_pct` ; CLI `--explicit-stats` / `--explicit-stats-witness`.
* `scripts/python/rl_collect_batch.py` — `_normalize_and_extract_pool(explicit_stats=…)` + les
  deux refus qui empêchent un bundle périmé de passer pour un résultat.
* `scripts/python/rl_duel.py` — `build --explicit-stats <unitId>` (injecte au catalogue si besoin).
* `scripts/python/probe_419r1tr12r2_stats_npc_summon.py` — témoin, deux régimes, contre-épreuves
  live désarmée/armée, mutants du mirror.
* `scripts/python/probe_419r1tr12r2_mutants_garde.py` — contre-épreuve de la garde.
* `scripts/python/tests/engine/test_419r1tr12r2_stats_npc_summon_offline.py` — 20 gardes.

## 9. Résidus

* ~~**`#419-r1-tr12-r2-r1` — 9 summons hors portée des trois constantes.**~~ **RÉSOLU (2026-08-15)**
  — et l'axe de l'énoncé était **le mauvais**. Détail : §12.
* **La branche VIDE de `PassiveAbilityLevel` n'est pas confrontée** — les 4 npc du témoin ont tous un
  passif. Elle est écrite par symétrie avec `ActiveAbilityLevel` et reste sans conséquence : une
  liste d'abilities vide ne donne rien à niveler à
  `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`.
* **`#419-r1-tr12-r2-r2` — le TROISIÈME porteur, le SUMMON, n'est pas confronté.**
  `admecSmnElectropriest` porte le même kit que le npc au trait `Summon` près. Le régime
  `summon-spawn` d'`explicit_stats` pourrait l'amener, mais son ability déclarante est
  `EnvFactionSummons:AdeptusMechanicus`, qu'aucune unité ne porte — il n'y a donc pas de summoner
  à spawner, et un summon n'entre jamais dans `decisionView.toActivate` (#291). Reste à établir si
  `pairUtility` répond sur une entité qui n'est pas activable. Le régime `summon-spawn` du chemin
  de stats est **non exercé live** par la même occasion.
* **`#419-r1-tr12-r3` (la face COMBAT) n'est pas touché par cette tranche** — un chemin de stats ne
  dit rien de l'exécution.

## 10. Portée — ce que ce chemin couvre, et ce qu'il ne couvre pas

**Couvre** : amener en bataille un porteur **npc** avec ses propres stats, traits et armes, par la
table que le jeu lui-même lit ; et amener un **summon** avec les stats que son ability lui donnerait
au spawn. Cela lève la condition « la greffe n'est légitime que si le corps ne lit ni stats, ni
traits, ni armes » pour toute la classe — c'est le même débloqueur que `#419-r1-tr13-r2` et
`#419-r1-tr14-r1` nomment.

**Ne couvre pas** : la face DÉCISION livrée ne dit rien de l'EXÉCUTION (`#419-r1-tr12-r3`) ; le
régime `summon-spawn` n'est exercé par aucun montage live (`#419-r1-tr12-r2-r2`) ; les 9 summons du
résidu `#419-r1-tr12-r2-r1`.

## 11. Le montage JOUÉ — `1303 ElectroShock` sur son porteur RÉEL

Les quatre crans de la tranche 12 ont été rejoués sur `admecNpc3Electropriest:33`, amené par ce
chemin. Le terme natif est mesuré par **bras apparié** (`natif_porteur − natif_base`, deux runners
identiques à `1303` près), board `MC1_67`, seed `41303`.

| cran | ennemis adj. | amis adj. | natif porteur | natif base | **TERME natif** | port | **TERME port** |
|---|---|---|---|---|---|---|---|
| `c0` | 0 | 0 | 4.629769 | 4.629769 | **+0.000000** | 4.629769 | +0.000000 |
| `cF` | 0 | **1** | 4.629769 | 4.629769 | **+0.000000** | 4.629769 | +0.000000 |
| `c1` | **1** | 0 | 54.629769 | 4.629769 | **+50.000000** | 54.629769 | +50.000000 |
| `c2` | **2** | 0 | 54.629769 | 4.629769 | **+50.000000** | 54.629769 | +50.000000 |

Trois résultats que la greffe ne pouvait pas donner.

### L'arme du porteur réel est de MÊLÉE — et c'est la lecture de la TUILE D'ACTION qui sauve le montage

`tauMarksman` tirait à 3 ; l'`Electropriest` a une seule arme `Particle` **sans `Range`**, donc
`IsMelee` (`catalog_inject._weapons`). Un caster de mêlée est adjacent à sa cible, donc un **voisin
AMI permanent** : `c0` cesserait d'être un « zéro voisin » et les contre-épreuves
`friends` / `any_neighbour` / `no_gate` mordraient **exactement les mêmes crans** — l'axe CAMP ne
serait plus exercé.

Ce qui l'évite est **lu**, pas contourné : `pairUtility` résout `col`/`row` dans le movable set
(`BattleQuery$$GetMovableTiles`) et construit un `UnitPosition` par `GetUnitPositionAtTile` — il ne
**déplace rien** dans l'ECS. Or le playbook lit `GetAdjacentEnemies(case.Target, case.Caster,
false)`, dont les occupants viennent de `GetUnit(tile)` sur l'état RÉEL. Le caster reste donc garé
loin de sa cible pendant que la paire est évaluée depuis une tuile `A` adjacente à elle. Le port
fait pareil (`count_adjacent_by_camp` lit `scene.pos` ; `attack_tile` est accepté et ignoré), et
c'est précisément ce que ce montage confronte : le terme reste nul quand la cible n'a aucun voisin,
alors que la **tuile d'attaque**, elle, en est voisine.

⚠ **Le mirror OFFLINE du déplacement ne suffit pas à choisir `A`.** Un BFS `_move_ring` à `move`
pas proposait `(0,2)` depuis `(3,4)` alors que le movable set natif ne la contient pas — le
pathfinder du jeu n'a pas le même coût de terrain que le ring nu, et `pairUtility` refuse la tuile
(« ni courante ni dans le movable set »). `A` est donc prise dans les tuiles d'action **mesurées**.

### Les deux bras diffèrent par DEUX choses, et la seconde est neutralisée par construction

`ElectroShock` est une clé de `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive` :
retirer `1303` retire aussi l'attaque normale custom. Mesuré aux deux bras —
`porteur = [(1178, ElectroShock_NormalAttack)]`, `base = [(69, Loki_NormalAttack)]`. L'axe ne pollue
pas le terme parce que `pairUtility` reçoit le **même** `abilityType` des deux côtés (`1178`) ; le
montage le **mesure** au lieu de le supposer.

### Le terme ne dépend d'AUCUN étage du porteur — deux porteurs, facteur 52 sur le niveau

Le second npc, `admecNpc3ElectropriestSurv:33`, porte le même kit et une ligne `stats[]` d'un tout
autre ordre (`Damage` 47656 contre 1765, `FixedArmor` 16248 contre 490, multiplicateur 180). Les
deux sont pourtant « Rank 17 ».

| porteur | niveau de la paire (bras base) | TERME `c1`/`c2` | écart natif↔port |
|---|---|---|---|
| `admecNpc3Electropriest:33` | 4.629769 | **+50.000000** | **0.000000** |
| `admecNpc3ElectropriestSurv:33` | 239.995000 | **+50.000000** | **0.000000** |

Le niveau bouge d'un facteur ~52, le terme ne bouge pas d'un iota : c'est la décomposition par
étage, pas un scalaire ajusté. Les deux npc partagent le **même `VisualId`**
(`admecNpc3Electropriest`) — d'où le refus d'ambiguïté de `_roster`, qui lève plutôt que de choisir
en silence lequel des deux il mesure.

### L'écart natif↔port est NUL, pas seulement constant

Le montage greffe portait un résidu constant de `+1.364932` (le dispatch d'attaque normale, fermé
par `#419-r1-tr14-r5`). Sur le porteur réel, le port rend **exactement** la valeur native aux quatre
crans et sur les deux npc. La garde l'assertionne séparément, en **nommant son accusé** : si ce
test-là rougit seul, c'est le composite de dégât de la paire, pas le terme.

### Contre-épreuves — deux étages, tous deux mordants

Les quatre mutants du calcul (`product`, `any_neighbour`, `no_gate`, `friends`) sont joués à chaque
cran : chacun mord au moins un cran, épargne au moins un autre, et **aucune paire ne mord les mêmes
crans** (assertion de non-colinéarité — c'est elle qui détecterait la dégénérescence décrite
plus haut).

Et la garde elle-même a été éprouvée par mutation du **fichier livré**
`engine/playbook/electro_shock.py` (`probe_419r1tr12r2_mutants_garde_reel.py`, qui **lève si un
motif est introuvable** — la tranche 12 avait mesuré qu'un remplacement muet produit un vert
trompeur) : `friends` → **7 rouges / 12**, `product` → **7 / 12**, `no_gate` → **6 / 12** ;
restauration re-jouée → **12 passed**.

### Livré par ce montage

* `scripts/python/probe_419r1tr12_electro_shock.py` — profils de montage (`GRAFT`, `REAL`,
  `REAL_SURV`), portée d'arme **dérivée** du gameconfig, tuile d'action distincte de la position du
  caster, refus d'ambiguïté de `VisualId`.
* `scripts/python/probe_419r1tr12r2_mutants_garde_reel.py` — contre-épreuve de la garde.
* `scripts/python/tests/engine/test_419r1tr12r2_electro_shock_reel_live.py` — 12 gardes.

## 12. `#419-r1-tr12-r2-r1` — DEUX ÉTAGES de stats de spawn, pas trois constantes trop étroites

Build lu : `t6dpr4k06g`. La fiche proposait d'élargir `GetSummonStats` aux constantes `unitId_3` /
`unitId_4`. Le décompilé dit que ce serait **faux**, et rendrait 8 zéros.

### Ce que le natif a VRAIMENT

| étage | symbole | régime choisi par | famille de variables |
|---|---|---|---|
| META | `IdunMetaLogic.UserProgress.UnitProgression$$GetSummonStats` | la **CONSTANTE** d'id (`isPrimary = ct == unitId(0) \|\| ct == unitToSpawn(8)`) | `summon*` / `summon*_2` |
| BATAILLE | `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig{,2,3}` | un **ORDINAL** passé par le behaviour (1, 2, 3) | `summon*` à cet ordinal |
| BATAILLE | `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfigSpawn` | idem | **`spawn*`** à cet ordinal |

Les deux fabriques de bataille posent les **mêmes 7 `StatType`**, par sept appels à
`IdunBattle.Entities.Behaviours.SpawnUnitOptions$$SetStatFromConfig` — `summonHp`(0x29)→5,
`summonDmg`(0x2a)→0, `summonArmor`(0x2b)→0x10, `summonBlockChance`(0x56)→7,
`summonBlockDmg`(0x55)→8, `summonCritChance`(0x54)→9, `summonCritDmg`(0x57)→10 ; la version `Spawn`
lit `spawnHp`(0x6a), `spawnDmg`(0x69), `spawnArmor`(0x6b), `spawnBlockChance`(0x6e),
`spawnBlockDmg`(0x6f), `spawnCritChance`(0x6c), `spawnCritDmg`(0x6d).

Le nom RÉEL vient de
`IdunBattle.Configuration.AbilityConfiguration$$GetDynamicTypeu003C__Il2CppFullySharedGenericStructTypeu003E` :
`Enum.ToString(base)`, puis `Concat(nom, "_", ordinal)` **si `ordinal > 1`**, puis `Enum.TryParse`
— et il **lève** si le membre n'existe pas. C'est le même foyer qui sert
`$$GetDynamicStringConstant(cfg, AbilityConstantType.unitId, ordinal)`, d'où les ids
`unitId` / `unitId_2` / `unitId_3` … `unitId_6` (0, 4, 109, 123, 124, 125).

⇒ **`unitId_3` et `unitId_4` ne sont pas des constantes « oubliées » par l'overload de sélection :
ce sont les ordinaux 3 et 4 de la voie DYNAMIQUE**, et cette voie lit une autre famille.

### Les 9, re-ventilés — et deux affirmations de la fiche tombent

* **2** (`thousSmnBlueHorrorHSE` ordinal 3, `thousSmnScreamerHSE` ordinal 4) sont déclarés par
  `EnvAllyAndEnemyNpcs:WarpSurge` — un `battleEnvironmentAbility` **PvP**
  (`gameModeRestrictions.allowed = ["PvP"]`, `traitRestrictions.allowed = ["Chaos"]`), porté par
  **aucune unité**, dont la classe est
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAllyAndEnemyNpcsAbility`. Son
  `$$SpawnUnits` lit `nrOfUnitIds`(0x7a), tire un ordinal par `DSLFormulas.RandomAmount(0, n-1)`,
  résout l'id par `$$GetDynamicStringConstant` et appelle `$$WithStatsFromConfigSpawn`. Cette
  ability ne porte **AUCUNE** variable `summon*` — elle porte `spawnHp`, `spawnHp_2`, `spawnHp_3`,
  `spawnHp_4`, `spawnDmg*`, `spawnArmor_2/_4`. Élargir `GetSummonStats` leur aurait rendu **8
  zéros** (`if (var != 0)` laisse le champ), un zéro qui se lit comme une mesure.
* **7** n'ont **aucun** invocateur : une seule occurrence textuelle dans tout le gameconfig — leur
  propre définition sous `units.summons`. ⚠ **`tyranSmnTermagant` en fait partie** : la fiche
  disait « n'apparaît que dans une liste `unitIds` », c'est **RÉFUTÉ** sur ce build.

### Ce que la re-mesure a trouvé EN PLUS, et qui était pire

Ventilation des 65 summons : 39 rendent des stats non nulles, 9 sans déclarant, 13 refusés pour
ambiguïté — et **4 rendaient 8 ZÉROS EN SILENCE** (`astarSmnHaywireMine`,
`blackSmnBloodletterHSE`, `genesSmnDecoy`, `thousSmnPinkHorrorHSE`). Le refus d'ambiguïté ne les
protégeait pas : `genesSmnDecoy` a **5** abilities déclarantes dont les 5 profils sont **égaux
parce que tous nuls** — l'accord en régime dégénéré.

Deux causes, mesurées : l'ability ne porte aucune variable de stats (`HaywireMine`), ou le régime
déduit de la constante n'est pas celui du behaviour (`SpiritualLeader` déclare `genesSmnDecoy` par
`unitId_2`, donc régime `_2` côté META, alors qu'elle ne porte que `summonHp`/`summonDmg`/
`summonArmor` **nus**, donc l'ordinal 1 côté bataille).

**Et la victime existe, déjà documentée sans avoir été comprise** : `probe_477r35` monte
`astarSmnHaywireMine` par `--explicit-stats` et note que « la tuile qui porte la mesure est une mine
SPAWNÉE (2,7), pas celle posée à la main en (5,5) ». La mine posée à la main arrivait à **0 PV**.

### Livré

* `catalog_inject.dynamic_member_name` (mirror de `GetDynamicType<>`), `SPAWN_STAT_BASES`,
  `DYNAMIC_ID_MAX_ORDINAL`, `spawn_declaring_abilities`, `summon_spawn_regimes` (le recensement qui
  manquait : `--summon-regimes <id>`).
* **REFUS** du patch `summon-spawn` intégralement nul dans `explicit_stats` — échappatoire nommée
  `allow_zero_profile` / `--allow-zero-spawn-stats`, et `rl_duel` l'imprime en clair quand elle est
  utilisée. `probe_477r35` migré dessus.
* Le message du `KeyError` **nomme l'étage** : `summon ORPHELIN` vs `voie DYNAMIQUE`.
* 6 gardes neuves + le test des déclarants **renforcé** (il exigeait un message, il exige désormais
  la ventilation dans les deux formes) — `tests/engine/test_419r1tr12r2_stats_npc_summon_offline.py`,
  25 tests verts.

### Ce qui n'est PAS couvert

* **La famille `spawn*` n'est pas portée** (6 régimes, ordinaux 105..147). Aucun consommateur ne la
  demande : son seul porteur du gameconfig est une ability d'environnement **PvP** que le harnais
  n'atteint pas. Porter sans porteur serait spéculatif.
* **Le 3ᵉ régime `summon*_3`** (95..101) existe dans l'enum et n'est lu par **aucun** des trois
  overloads de `GetSummonStats` — il n'est atteignable que par `$$WithStatsFromConfig3`. Non porté,
  même raison.
* Le régime `summon-spawn` reste **non exercé live** (`#419-r1-tr12-r2-r2`, inchangé).
