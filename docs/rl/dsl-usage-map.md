# Carte d'usage du DSL -- primitive <-> ability (phase 1, xrefs)

> **FICHIER GENERE** par `python scripts/python/dsl_xref_map.py report`.
> En cas de conflit au rebase : **REGENERER, ne pas fusionner** -- aucun cote
> d'un diff genere n'est "juste".
> Build : `t6dpr4k06g`. Source : xrefs `ghidra-mcp` sur `GameAssembly.dll`.

## Ce que repond cette carte

Le vocabulaire DSL etait **classe** (`dsl-effect-nodes.md`) mais son **graphe
d'usage** n'existait nulle part : impossible de dire quelles abilities composent
une primitive donnee, ni quel vocabulaire emploie une ability. Cette carte est ce
graphe, derive des **xrefs entrantes de type CALL** vers les fabriques statiques
du DSL. Le nom de classe du site appelant donne le proprietaire.

Sont retenus comme **primitives** :

  * toute methode des fabriques statiques (une methode = un noeud) --
    `IdunBattleLogic.Entities.DSLBehaviors` ;
    `IdunBattleLogic.Entities.DSLSelectors` ;
    `IdunBattleLogic.Entities.DSLTriggers` ;
    `IdunBattleLogic.Entities.DSLFormulas` ;
    `IdunBattleLogic.Entities.DSLFactory` ;
  * les **combinateurs**, c.-a-d. les operateurs surcharges des types de noeud
    `IdunBattle.DSL.*$$op_*` (`a & b`, `a | b`, `!a`, `a + b`, `a - b`). Les omettre etait un
    angle mort : aucune fabrique ne porte `&`, alors que c'est LE combinateur
    de sequence des arbres de behaviour.

## Comptes re-derives (build `t6dpr4k06g`)

| grandeur | valeur |
|---|---|
| corps de primitive interroges | 748 |
| noms de primitive distincts (surcharges agregees) | 609 |
| xrefs d'appel retenues | 13899 |
| proprietaires distincts (toutes categories) | 1203 |
| &nbsp;&nbsp;dont `ability` | 741 |
| &nbsp;&nbsp;dont `effect` | 367 |
| &nbsp;&nbsp;dont `utility` | 69 |
| &nbsp;&nbsp;dont `other` | 21 |
| &nbsp;&nbsp;dont `dsl-internal` | 5 |

## Couverture TRI-ETAT (jamais binaire)

| etat | primitives | lecture |
|---|---|---|
| `measured` | 593 | au moins un site appelant **nomme** |
| `measured_empty` | 16 | interrogee, **aucun xref d'appel** -- corps probablement deduplique, inline, ou atteint uniquement par un corps non nomme |
| `callers_anonymous` | 0 | des appels EXISTENT mais leur fonction appelante n'est **pas nommee** -- usage reel, proprietaire illisible |
| `not_measured` | 0 | requete non aboutie / non parcourue -- **jamais** a confondre avec `measured_empty` |
| `NON MESURABLE (gshared)` | etat d'**axe** | voir ci-dessous : se lit dans `coverage_axes` du manifeste, pas dans la colonne `coverage` |

Sites appelants **non nommes** au total : **0** (repartis sur 0 primitives).

### L'axe UTILITY (gshared) -- mesure exacte, ni masquee ni exageree

Le trou gshared (`case-259`) est reel, mais il frappe la chaine **FRIDA**, pas
Ghidra -- et cette carte est batie sur les xrefs **Ghidra**. Le verifier plutot
que l'heriter change la conclusion : proclamer « NON MESURABLE » ici serait
aussi faux qu'un zero silencieux.

| build sur disque | `u003C__Il2CppFullySharedGenericTypeu003E` nommes (ghidra) | (frida) |
|---|---:|---:|
| `gqfc5mff6c` | 2844 | 0 |
| `kqkbjqfb6c` | 2849 | non mesure |
| `rnca9r7q6c` | 2830 | 0 |
| `t6dpr4k06g` | 2830 | 0 |

Sur `t6dpr4k06g`, l'axe UTILITY est donc **PARTIELLEMENT MESURABLE** :

  * `dont corps pleinement partages` : 97 symboles nommes
  * `BucketSystem` : 14 symboles nommes
  * `Playbook$$Calculate*` : 196 symboles nommes
  * `namespace IdunBattle.AI.Playbook` : 2184 symboles nommes
  * proprietaires de kind `utility` effectivement vus en arete : **69**

**Ce qui reste hors d'atteinte, et pourquoi** :

  1. les corps gshared que Ghidra n'a **pas** nommes -- leur nombre n'est **pas
     bornable** par cette methode (l'absence d'un symbole ne prouve rien) ;
  2. un probe **live** sur cette couche reste aveugle (chaine Frida a 0) ;
  3. l'axe **scoring** -- *quel playbook evalue quelle ability* -- est un AUTRE
     graphe, absent ici **par construction** et non par mesure vide : il ne
     passe pas par les fabriques DSL. Le manifeste le declare
     `utility_scoring.status = OUT_OF_SCOPE_PHASE_1`.

### Couverture INVERSE -- les sites de composition non atteints

On balaie les fonctions dont la methode est un point de composition (`CreateBehaviour`, `ExecuteBehaviour`, `CreateTrigger`, `CreateEffect`, `ShouldTrigger`, `CreateSelector`, `CreateFormula`)
et on regarde lesquelles appellent au moins une primitive.

| grandeur | valeur |
|---|---|
| proprietaires possedant un site de composition | 805 |
| &nbsp;&nbsp;atteints par au moins une arete | 697 |
| &nbsp;&nbsp;**sans aucune primitive nommee** | 108 |
| proprietaires vus en arete **sans** site de composition nomme | 506 |

Un proprietaire « sans aucune primitive nommee » n'est **pas** un trou de
mesure : il compose imperativement, ou via du code non nomme. C'est un fait a
verifier au decompile, primitive par primitive. La liste complete est dans
`composition_sites.owners_with_site_but_no_named_primitive` du manifeste.

La reciproque compte autant : 506 proprietaires composent depuis une methode
**auxiliaire** et seraient invisibles a un balayage qui ne regarderait que
`CreateBehaviour`. La distribution MESUREE des points de composition le montre :

| methode d'ou part l'appel | appels |
|---|---:|
| `CreateBehaviour` | 2819 |
| `ExecuteBehaviour` | 2454 |
| `CreateTrigger` | 2208 |
| `CreateEffectDamageBonusForAttack` | 484 |
| `CreateHandleTriggerAbilitiesInternal` | 362 |
| `CreateTargetSelector` | 299 |
| `CreateEffectHitsBonusForAttack` | 186 |
| `CreateTargetTrigger` | 158 |
| `CreateEffectDamageMalusForDefense` | 153 |
| `CreateDamageModifier` | 121 |
| `CreateTargetTriggerBehaviour` | 114 |
| `CreateActiveCondition` | 114 |
| `CreateAdditionalHits` | 96 |
| `CreateRemoveEffectTrigger` | 63 |
| `GetTargetTiles` | 63 |
| `MoveNext` | 53 |

(distribution complete dans `composition_sites.methods_observed` du manifeste)

### Les autres motifs d'invisibilite (rappel doctrinal)

Un xref vide ne prouve **rien** : les corps triviaux sont **dedupliques** (un seul
proprietaire nomme pour N classes) et les **bases generiques** ne sont pas dumpees.
La formule juste est « **aucun xref nomme** », pas « personne ne l'utilise ».

## Contrat MACHINE (chemins stables -- a citer, pas a parser depuis ce .md)

| fichier | contenu | colonnes |
|---|---|---|
| `docs/rl/dsl-usage/dsl-usage-edges.tsv` | une ligne par **arete** primitive -> site | `primitive / primitive_family / primitive_method / owner / owner_kind / owner_short / site_method / n_calls` |
| `docs/rl/dsl-usage/dsl-usage-primitives.tsv` | **Table A** : une ligne par primitive + couverture | `primitive / primitive_family / primitive_method / coverage / n_bodies / n_composers / n_owners / n_call_sites / n_anonymous_call_sites / owners` |
| `docs/rl/dsl-usage/dsl-usage-owners.tsv` | **Table B** : une ligne par proprietaire | `owner / owner_kind / owner_short / n_primitives / primitives` |
| `docs/rl/dsl-usage/dsl-usage.json` | manifeste : schema, comptes, `coverage_axes` | JSON |

`schema_version` = **1.0**. Brut non versionne : `logs/dsl_xrefs_raw.json`
(gitignore, meurt avec le worktree ; regenerable par `dsl_xref_map.py scan`).

Completude de ce tirage : `scan_complete=true` (748 corps interroges sur 748).

## Classement des primitives par LEVIER

`n_composers` = nombre d'abilities/effets **distincts** qui appellent la primitive.
C'est la mesure du deblocage : porter la primitive du haut sert `n_composers`
abilities d'un coup. `n_sites` compte les appels (une ability peut appeler 3 fois).

| # | primitive | n_composers | n_owners | n_sites | anon |
|---:|---|---:|---:|---:|---:|
| 1 | `AbilityTrigger$$op_BitwiseAnd` | 540 | 541 | 1416 | 0 |
| 2 | `DSLTriggers$$On` | 277 | 278 | 364 | 0 |
| 3 | `DSLBehaviors$$AddEffect` | 274 | 274 | 396 | 0 |
| 4 | `AbilityBehaviour$$op_BitwiseAnd` | 229 | 233 | 441 | 0 |
| 5 | `DSLFormulas$$ConfigVar` | 229 | 229 | 302 | 0 |
| 6 | `DSLFormulas$$Direct` | 228 | 232 | 404 | 0 |
| 7 | `AbilityTrigger$$op_LogicalNot` | 222 | 224 | 371 | 0 |
| 8 | `DSLTriggers$$get_OwnerIsTarget` | 191 | 192 | 214 | 0 |
| 9 | `DSLTriggers$$get_OwnerIsCaster` | 178 | 178 | 189 | 0 |
| 10 | `DSLBehaviors$$If` | 174 | 175 | 250 | 0 |
| 11 | `DSLFormulas$$Get` | 149 | 156 | 259 | 0 |
| 12 | `AbilityBehaviour$$op_Addition` | 147 | 147 | 312 | 0 |
| 13 | `DSLBehaviors$$AttackWithAttackDamage` | 135 | 135 | 168 | 0 |
| 14 | `AbilityTrigger$$op_BitwiseOr` | 133 | 134 | 202 | 0 |
| 15 | `DSLFormulas$$ConfigConst` | 115 | 115 | 175 | 0 |
| 16 | `DSLTriggers$$AmountIsGreaterThanZero` | 107 | 109 | 141 | 0 |
| 17 | `TargetsSelector$$op_Addition` | 106 | 109 | 176 | 0 |
| 18 | `DSLTriggers$$HasEffect` | 103 | 107 | 137 | 0 |
| 19 | `DSLSelectors$$First` | 103 | 105 | 146 | 0 |
| 20 | `DSLSelectors$$Enemies` | 100 | 113 | 172 | 0 |
| 21 | `DSLTriggers$$HasTrait` | 99 | 99 | 146 | 0 |
| 22 | `DSLTriggers$$get_OwnerIsActor` | 96 | 97 | 107 | 0 |
| 23 | `DSLSelectors$$Tiles` | 90 | 92 | 126 | 0 |
| 24 | `DSLSelectors$$Cache` | 89 | 89 | 121 | 0 |
| 25 | `DSLFormulas$$TurnsFromRounds` | 87 | 87 | 121 | 0 |
| 26 | `DSLSelectors$$CanAddUnit` | 82 | 85 | 137 | 0 |
| 27 | `DSLBehaviors$$RemoveEffect` | 82 | 83 | 123 | 0 |
| 28 | `DSLBehaviors$$Spawn` | 82 | 82 | 89 | 0 |
| 29 | `DSLFormulas$$Multiply` | 81 | 81 | 108 | 0 |
| 30 | `DSLSelectors$$Friends` | 80 | 85 | 116 | 0 |
| 31 | `DSLSelectors$$AdjacentTiles` | 80 | 83 | 154 | 0 |
| 32 | `DSLFormulas$$StatAmount` | 78 | 80 | 108 | 0 |
| 33 | `DSLSelectors$$PickRandomly` | 75 | 76 | 99 | 0 |
| 34 | `TargetsSelector$$op_Subtraction` | 72 | 78 | 127 | 0 |
| 35 | `DSLTriggers$$AreFriends` | 71 | 71 | 79 | 0 |
| 36 | `DSLSelectors$$Units` | 69 | 75 | 133 | 0 |
| 37 | `DSLFormulas$$Sum` | 68 | 69 | 102 | 0 |
| 38 | `DSLSelectors$$AdjacentFriends` | 65 | 66 | 90 | 0 |
| 39 | `DSLTriggers$$IsMeleeAttack` | 65 | 65 | 71 | 0 |
| 40 | `DSLSelectors$$AdjacentUnits` | 64 | 77 | 112 | 0 |
| 41 | `DSLTriggers$$AreEqual` | 63 | 64 | 82 | 0 |
| 42 | `DSLFormulas$$Count` | 60 | 61 | 83 | 0 |
| 43 | `DSLSelectors$$UnitsWithTrait` | 58 | 60 | 92 | 0 |
| 44 | `DSLBehaviors$$AttackWithAbilityDamage` | 57 | 58 | 75 | 0 |
| 45 | `DSLSelectors$$Direct` | 56 | 57 | 91 | 0 |
| 46 | `DSLSelectors$$EffectSource` | 56 | 56 | 86 | 0 |
| 47 | `DSLSelectors$$Filter` | 55 | 56 | 85 | 0 |
| 48 | `DSLFormulas$$PercentageOf` | 52 | 53 | 70 | 0 |
| 49 | `DSLTriggers$$AreEnemies` | 51 | 51 | 54 | 0 |
| 50 | `DSLTriggers$$IsRangedAttack` | 51 | 51 | 52 | 0 |
| 51 | `DSLSelectors$$AdjacentEnemies` | 47 | 47 | 69 | 0 |
| 52 | `DSLTriggers$$AmountIsEqualOrGreater` | 42 | 42 | 51 | 0 |
| 53 | `TargetsSelector$$op_BitwiseAnd` | 41 | 44 | 68 | 0 |
| 54 | `DSLBehaviors$$AddStaticStatModifierEffect` | 41 | 42 | 61 | 0 |
| 55 | `DSLBehaviors$$Foreach` | 40 | 40 | 52 | 0 |
| 56 | `DSLBehaviors$$Inform` | 39 | 40 | 43 | 0 |
| 57 | `DSLFormulas$$If` | 38 | 39 | 59 | 0 |
| 58 | `DSLTriggers$$IsAdjacent` | 37 | 43 | 44 | 0 |
| 59 | `DSLSelectors$$Get` | 36 | 62 | 119 | 0 |
| 60 | `DSLFormulas$$ConditionalAmount` | 35 | 36 | 61 | 0 |
| 61 | `DSLTriggers$$IsNormalAttack` | 35 | 36 | 40 | 0 |
| 62 | `DSLFormulas$$RandomAmount` | 35 | 35 | 47 | 0 |
| 63 | `DSLSelectors$$Unique` | 35 | 35 | 43 | 0 |
| 64 | `DSLTriggers$$IsAlive` | 34 | 37 | 46 | 0 |
| 65 | `DSLBehaviors$$AddBondEffect` | 34 | 34 | 40 | 0 |
| 66 | `DSLFactory$$Triggered` | 34 | 34 | 63 | 0 |
| 67 | `DSLSelectors$$SortByFormula` | 34 | 34 | 44 | 0 |
| 68 | `DSLSelectors$$UnitsFromFaction` | 33 | 33 | 41 | 0 |
| 69 | `DSLSelectors$$EntitiesWithAnyEffect` | 32 | 32 | 37 | 0 |
| 70 | `DSLSelectors$$Randomize` | 32 | 32 | 45 | 0 |
| 71 | `DSLBehaviors$$Nothing` | 30 | 33 | 49 | 0 |
| 72 | `DSLTriggers$$AmountIsGreater` | 30 | 31 | 35 | 0 |
| 73 | `DSLFormulas$$GetPersistentData` | 28 | 30 | 44 | 0 |
| 74 | `DSLBehaviors$$AtomicGroup` | 28 | 28 | 30 | 0 |
| 75 | `DSLTriggers$$AmountIsEqual` | 27 | 28 | 34 | 0 |
| 76 | `DSLBehaviors$$Heal` | 27 | 27 | 30 | 0 |
| 77 | `DSLSelectors$$SurroundingFriends` | 26 | 30 | 35 | 0 |
| 78 | `DSLTriggers$$TriggeringAbilityIs` | 26 | 27 | 34 | 0 |
| 79 | `DSLBehaviors$$Group` | 26 | 26 | 51 | 0 |
| 80 | `DSLBehaviors$$MoveUnit` | 26 | 26 | 30 | 0 |

### Par famille

| famille | primitives | dont avec >=1 composer | composers cumules (non dedup) |
|---|---:|---:|---:|
| `AbilityBehaviour` | 2 | 2 | 376 |
| `AbilityTrigger` | 3 | 3 | 895 |
| `DSLBehaviors` | 127 | 126 | 1722 |
| `DSLFactory` | 4 | 1 | 34 |
| `DSLFormulas` | 112 | 110 | 1629 |
| `DSLSelectors` | 194 | 185 | 2204 |
| `DSLTriggers` | 164 | 150 | 2159 |
| `TargetsSelector` | 3 | 3 | 219 |

### Primitives SANS aucun composer nomme

A lire comme « aucun xref nomme » -- pas comme « inutilisee ».

Nombre : **29** / 609.

  * `DSLBehaviors$$Transform`
  * `DSLFactory$$Init`
  * `DSLFactory$$SetAllowRandom`
  * `DSLFactory$$SetDisallowRandom`
  * `DSLFormulas$$PercentageOfStatCappedAtMax`
  * `DSLFormulas$$TimesBlockedThisTurn`
  * `DSLSelectors$$DownedUnits`
  * `DSLSelectors$$EnhancementTarget`
  * `DSLSelectors$$Entities`
  * `DSLSelectors$$GetDefaultUnitSelectionType`
  * `DSLSelectors$$InitializeShared`
  * `DSLSelectors$$SpawnTiles`
  * `DSLSelectors$$TerritoryTiles`
  * `DSLSelectors$$Trench`
  * `DSLSelectors$$UnitsWithRangedAbilities`
  * `DSLTriggers$$AmountIsEven`
  * `DSLTriggers$$HasAdjacentFreeTiles`
  * `DSLTriggers$$InitializeShared`
  * `DSLTriggers$$IsAbilityCountedOnlyOnce`
  * `DSLTriggers$$IsEmptyOrSteppable`
  * `DSLTriggers$$IsNormalAttackOrHealOrRepair`
  * `DSLTriggers$$IsPlayerDefeated`
  * `DSLTriggers$$IsTeamDefeated`
  * `DSLTriggers$$IsTriggeringAbilityNormalAttackOrHealOrRepair`
  * `DSLTriggers$$Not`
  * `DSLTriggers$$OnAttackFromAbility`
  * `DSLTriggers$$StatPercentageIsBelowOrEqual`
  * `DSLTriggers$$TriggeringAbilityHasAttackType`
  * `DSLTriggers$$get_OwnerTileIsTarget`

## Proprietaires les plus riches (table B, extrait)

| proprietaire | kind | n_primitives |
|---|---|---:|
| `ArmouredMight_MoveAbility` | ability | 47 |
| `DSLTriggers` | dsl-internal | 44 |
| `LeadingTheChargeAbility` | ability | 35 |
| `LivingBatteringRamAbility` | ability | 34 |
| `MyWillBeDoneOverlordAbility` | ability | 34 |
| `UnstoppableMomentumReworkedAbility` | ability | 32 |
| `BounceAbility` | ability | 32 |
| `HypersensoryAbilitiesAbility_MoveAndSpawnDecoy` | ability | 32 |
| `MV71SniperDroneSquadAttackAbility` | ability | 32 |
| `DiveAttackAbilityBase` | ability | 31 |
| `WaaaghAbility` | ability | 31 |
| `ResurrectionOrbAbility` | ability | 29 |
| `TreasonOfTzeentchAbility` | ability | 29 |
| `HeavyRailRifle_AttackAbility` | ability | 29 |
| `TheQuickeningAbility` | ability | 28 |
| `EnvAmbushResurrectAbility` | ability | 28 |
| `InstrumentsOfVengeance_AttackAbility` | ability | 28 |
| `PrimarchOfTheFirstLegionAbility` | ability | 28 |
| `DakkaDakkaDakkaAbility` | ability | 27 |
| `EnvEndBombardment_DamageAbility` | ability | 27 |
| `TheBetrayer_TakeTurnAbility` | ability | 27 |
| `MartialExemplarAbility` | ability | 26 |
| `SwornProtectorAbility` | ability | 26 |
| `SolarAtomizerAbility` | ability | 26 |
| `WyrdmakersHelmAbility` | ability | 26 |
| `DarkTalonStrikeAbility` | ability | 25 |
| `InstinctiveBehaviour_UpdateTargetAbility` | ability | 25 |
| `InstrumentsOfVengeanceAbility` | ability | 25 |
| `EnvAngelsOfDeathAbility` | ability | 25 |
| `RefusalToBeOutdoneAbility` | ability | 25 |
| `TheArdentBlade_TriggerAbility` | ability | 25 |
| `EreWeGo_AttackAbility` | ability | 24 |
| `NovaChargeAbility` | ability | 24 |
| `TunnelingHorror_AppearAbility` | ability | 24 |
| `HaywireMineAbility` | ability | 23 |
| `GetEmRuntzAbility` | ability | 22 |
| `PileInAbility` | ability | 22 |
| `RitesOfMorkaiAbility` | ability | 22 |
| `SpiritLeechAbility` | ability | 22 |
| `ThriceBlessedConflagrationAbility` | ability | 22 |
| `EnvStrategicBuffAbility` | ability | 22 |
| `SpiritualLeaderAbility` | ability | 22 |
| `TheEmperorsShieldAbility` | ability | 22 |
| `DSLSelectors` | dsl-internal | 22 |
| `AReactivateOverwatchEffect` | effect | 21 |
| `GhostEffect` | effect | 21 |
| `LegendaryCommander_ExtraHitsEffect` | effect | 21 |
| `ArcScourgeAbility` | ability | 21 |
| `EnvDespoiledGroundTileAbility` | ability | 21 |
| `FrenziedFiringAbility` | ability | 21 |
| `GrapnelLauncherAbility` | ability | 21 |
| `HammerOfWrathAbility` | ability | 21 |
| `HeroicFusilladeAbility` | ability | 21 |
| `MalleusRocketLauncher_AttackAbility` | ability | 21 |
| `APowerUpAbility` | ability | 21 |
| `BookOfFateAbility` | ability | 21 |
| `ControlEdictAbility` | ability | 21 |
| `SabreOfSacrificeAbility` | ability | 21 |
| `MoreGitzOverEre_ExtraDamagePctEffect` | effect | 20 |
| `TerminatorArmour_ReduceDmg_Effect` | effect | 20 |
| `TzeentchsFirestormBaseEffect` | effect | 20 |
| `ActOfFaithAbility` | ability | 20 |
| `DaemonicOrdnanceAbility` | ability | 20 |
| `DeathOnTheWindAbility` | ability | 20 |
| `DevastatingRefrain_AttackAbility` | ability | 20 |
| `GeminaeSuperiaAbility` | ability | 20 |
| `ItItchesAbility` | ability | 20 |
| `ArcaneShieldAbility` | ability | 20 |
| `EcstaticSlaughterAbility` | ability | 20 |
| `GazeOfMagnusAbility` | ability | 20 |
| `HarlequinsPanoplyAbility` | ability | 20 |
| `LightImUpAbility` | ability | 20 |
| `NovaBoost_AttackAbility` | ability | 20 |
| `SynapticLinchpinAbility` | ability | 20 |
| `TheWrathOfKhaineUnleashedRework_AttackAbility` | ability | 20 |
| `LightOfSanguiniusAbility` | ability | 19 |
| `BattleFatigueAbility` | ability | 19 |
| `DaGreatWaaaghAbility` | ability | 19 |
| `DeathToTheFalseEmperorAbility` | ability | 19 |
| `MassDriverAcceleratorAbility` | ability | 19 |

