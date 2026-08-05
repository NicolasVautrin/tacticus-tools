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
| explicite (armé) | attendu **oui** | — | **5303** | 1765 | 490 |

La seconde ligne est **calculée et vérifiée offline** ; sa confrontation live attend la fenêtre de
reinject (§6).

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

**Confronté live** : le verrou **désarmé** — `skipped.reason = 'v2 patch: system error'`, stats à 0.

**NON CONFRONTÉ — en attente de fenêtre de reinject** : le chemin **armé** dans
`buildNormalizedBC`. Le champ `explicitStats` vit dans `frida/hooks/**` ; la session courante porte
un bundle antérieur. Ce n'est **pas** une panne silencieuse : `_normalize_and_extract_pool`
**lève** quand `explicitStats` est fourni et que le RPC n'honore aucune entrée (champ `explicit`
vide), et `explicitUnmatched` fait lever de même. Un bundle périmé ne peut donc pas se lire comme
un résultat.

**NON FAIT** : la confrontation de `1303 ElectroShock` sur son porteur réel. Elle dépend
exclusivement de la fenêtre ci-dessus, plus un montage
`rl_duel build --board MC1_67 --explicit-stats admecNpc3Electropriest:33
--p-units admecNpc3Electropriest:33 …` reproduisant les quatre crans de la tranche 12.

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
  `explicitUnmatched`. **Exige une fenêtre de reinject.**
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

* **`#419-r1-tr12-r2-r1` — 9 summons hors portée des trois constantes.** `GetSummonStats(kind, cfg)`
  n'interroge que `unitToSpawn`(8), `unitId`(0), `unitId_2`(4). Neuf summons ne sont atteints par
  aucune : `thousSmnBlueHorrorHSE` / `thousSmnScreamerHSE` sont déclarés par `unitId_3` / `unitId_4`
  (constantes que **cet** overload n'interroge pas — l'overload principal les accepterait, mais rien
  de lu ne les lui passe), `tyranSmnTermagant` n'apparaît que dans une liste `unitIds`, et six
  (`templNeophyte`, `templInitiatePyreblaster`, `eldarSmnGuardian`, `ultraSmnEliminator`,
  `necroSmnDeathmark`, `darkaSmnWatcher`) ne sont nommés par **aucune** constante. Le module **lève**
  pour eux plutôt que de rendre des zéros. Fermer demande de lire quel code les invoque.
* **La branche VIDE de `PassiveAbilityLevel` n'est pas confrontée** — les 4 npc du témoin ont tous un
  passif. Elle est écrite par symétrie avec `ActiveAbilityLevel` et reste sans conséquence : une
  liste d'abilities vide ne donne rien à niveler à
  `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`.
* **`#419-r1-tr12-r3` (la face COMBAT) n'est pas touché par cette tranche** — un chemin de stats ne
  dit rien de l'exécution.

## 10. Portée — ce que ce chemin couvre, et ce qu'il ne couvre pas

**Couvre** : amener en bataille un porteur **npc** avec ses propres stats, traits et armes, par la
table que le jeu lui-même lit ; et amener un **summon** avec les stats que son ability lui donnerait
au spawn. Cela lève la condition « la greffe n'est légitime que si le corps ne lit ni stats, ni
traits, ni armes » pour toute la classe — c'est le même débloqueur que `#419-r1-tr13-r2` et
`#419-r1-tr14-r1` nomment.

**Ne couvre pas** : la face DÉCISION livrée ne dit rien de l'EXÉCUTION ; le chemin **armé** n'est pas
confronté live ; les 9 summons du résidu ; et rien de ce qui concerne le comportement de `1303`
lui-même, qui reste tel que la tranche 12 l'a porté et validé.
