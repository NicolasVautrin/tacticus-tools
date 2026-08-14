# Couverture moteur des abilities PASSIVES

> Genere par `scripts/python/audit_passive_ability_coverage.py` (gameconfig `passiveAbilities` x registres moteur x pool spawnable live). A regenerer au changement de build ou apres tout port. TOUS les chiffres de ce document sont re-derives a chaque run -- aucun n'est recopie.

## Pourquoi cet audit existe : l'angle mort est STRUCTUREL

`audit_combat_ability_coverage.py` (#95) croise `activeAbilities` x `ABILITY_CLASSES`, registre keye par **`ActiveAbilityType`**. Or, mesure de ce run sur les **211 passifs distincts** du parc :

| enum natif d'appartenance | passifs |
|---|---|
| `TriggeredAbilityType` | **210** |
| `ActiveAbilityType` | **1** |
| homonyme d'un `EffectType` | 28 |
| aucun des trois | 0 |

L'intersection nom-a-nom actives/passifs est **VIDE**. Un passif n'est donc pas une ability active « non castable » : c'est une **`TriggeredAbilityType`**, un objet d'un AUTRE enum, instancie a l'init de l'unite (`collect_triggered_abilities` cote port, `AbilityAndEffectCache` cote natif). L'audit des actives ne pouvait structurellement rien en voir.

Cas fondateur : `HeavyGravCannon`, passif d'`admecDestroyer` -- il expliquait un delta de degat live/offline reste longtemps sans cause, et n'apparaissait dans AUCUN audit (cf. `docs/rl/case-220/admec.md`, `docs/rl/case-101-moved-flag.md`). Ce meme cas documente le piege a ne jamais oublier ici, une **homonymie a TROIS faces** : `EffectType 1291 = HeavyGravCannon` (le nom CAPTE live), `TriggeredAbilityType 1233 = HeavyGravCannon` (la CONFIG du passif), `TriggeredAbilityType 1291 = SelfRepairMechanism` (**sans aucun rapport**). Le meme id dans deux enums nomme deux objets differents, et le meme nom dans deux enums porte deux ids differents -> **tout rapprochement par nom ou par id doit qualifier son enum**. Ce run mesure **28** des 211 passifs homonymes d'un `EffectType` : c'est exactement la population exposee a ce piege, et donc la limite du canal **E**.

## CRITERE DE COUVERTURE (enonce)

Un passif est **PORTE** si AU MOINS UN de ces canaux -- tous structurels (appartenance a un registre moteur) -- le prend en charge :

| canal | signal | consommateur du port |
|---|---|---|
| **T** trigger | `triggers.dispatch.ABILITY_TRIGGERS[<passif>]` | `collect_triggered_abilities` (canal CANONIQUE : le passif EST une triggered-ability) |
| **O** owner-effect | `factory.ABILITY_INIT_OWNER_EFFECTS` / `ABILITY_OWNER_EFFECTS` -> >=1 effet present dans `EFFECT_CLASSES` | `spawn._seed_ability_owner_effects` |
| **E** effet | cle `<passif>` ou `<passif>_...` dans `factory.EFFECT_CLASSES` | `EffectFactory.create` (effet seede depuis `decisionView.effects`) |
| **G** effet-trigger | l'id `EffectType` de cet effet est dans `triggers.dispatch.EFFECT_TRIGGERS` | `collect_effect_triggers` |
| **X** exec | id `ActiveAbilityType` present dans `runner.abilities.handler.ABILITY_CLASSES` | `AbilityHandler` |
| **B** bespoke-combat | le nom gameconfig apparait comme **litteral de chaine EXACT** dans du code sous `engine/runner/` | cablage keye sur le nom, DELIBEREMENT hors registres (cf. ci-dessous) |

Le canal **B** n'est pas un repli commode : il a ete AJOUTE apres avoir fait tomber le critere en faux GAP sur `PileIn`, dont le port ecrit noir sur blanc « PileIn reste BESPOKE -- pas dans `ABILITY_TRIGGERS` -> pas de double-fire par le dispatch generique » et se cable par un `if "PileIn" not in (...).passiveAbilities` dans le hook fin-de-tour. Un lookup keye sur le nom gameconfig EST un cablage.

Sinon, trois verdicts NEGATIFS distincts :

- **ZONE-GRISE [R]** -- aucun registre, mais le nom est reference dans le **code executable** d'`engine/` HORS `runner/` (ou seulement comme fragment d'identifiant). Deux causes mesurees, toutes deux a trancher au recon : (a) le passif est porte sur une AUTRE FACE -- `FuryOfTheAncients` et `SaviorProtocols` n'existent que comme feuille d'utilite AI (`playbook/`, `utilities/`), face DECISION, sans aucune execution combat ; (b) **faux ami d'enum** -- `GalvanicField` (passif, `TriggeredAbilityType`) ne matche que `Repair_GalvanicField` (`ActiveAbilityType` 1119), une ability ACTIVE differente. **C'est pour ca que la colonne `zones engine/` existe** : elle dit en un coup d'oeil sur quelle face vit la reference.
- **GAP-MENTION [.]** -- le nom n'existe que dans de la **prose** (commentaire / docstring). Le passif a ete VU, jamais BRANCHE.
- **GAP-ABSENT [ ]** -- aucune trace, nulle part.

### Le critere naif « le nom apparait dans engine/ » est SATURE

Mesure de ce run : un `substring` brut du nom sur `engine/**/*.py` rend **211/211 presents, 0 manquant**. La cause n'est pas que tout est porte : `engine/entities/triggered_ability_type.py` est un **mirror 1:1 de l'enum natif `TriggeredAbilityType`** (573 membres), ou le nom de CHAQUE passif figure comme membre. **Un catalogue n'est pas un cablage.**

Le signal code de cet audit est donc derive de l'**AST** et exclut les **definitions** de membres d'enum (2638 assignations ecartees dans 671 fichiers `engine/**/*.py`) tout en gardant les **usages** (`TriggeredAbilityType.X` = `ast.Attribute` -> compte). Il separe en outre le CODE (13933 symboles distincts) de la PROSE (11660 ko de commentaires + docstrings, invisibles a l'AST, lus via `tokenize`). Le rapprochement est CamelCase-aware : `HeavyGravCannon` matche `HeavyGravCannonEffect`, `Guard` ne matche ni `Guardsman` ni `RoyalGuard` (ni, pour `Possession`, l'unitId `blackPossession`).

Chaque reference est en outre ATTRIBUEE A SA ZONE du moteur (`__init__, ai, battle_query, dsl, effects, entities, hex_corner, hex_edge, move, playbook, predict, runner, services, streams, utilities, weights`), parce qu'une reference dans `playbook/`/`ai/`/`utilities/` (face DECISION) ne prouve RIEN sur l'execution combat. C'est ce qui separe **B** (litteral exact sous `runner/`) de **R**.

### Confrontabilite des porteurs (gate HERO / MoW / SUMMON -- jamais NPC)

La colonne `kind` de gameconfig MENT sur la spawnabilite -> le pool vient de la verite native `buildNormalizedBC` (`rl_duel.py build --list-pool`, rank **17** : 97 unites regulieres + 8 MoW).

| code | signification | confrontable |
|---|---|---|
| `L+` | lineup PRESENT dans le pool | **oui** |
| `M` | MachineOfWar du pool | **oui** |
| `S+` | hors pool mais ATTEIGNABLE par summon depuis le pool (fermeture transitive du graphe `constants.unitId*`/`unitIds`/`unitToSpawn`, 230 aretes -> 31 unites atteintes) | **oui**, via son summoner |
| `L~` | lineup ABSENT du pool -> **INJECTABLE** (21 unites) | **oui**, via `catalog_inject` |
| `L!` | lineup dans la liste des NON SPAWNABLES (1) | non -- leve a la construction |
| `S?` | summon sans summoner derivable du gameconfig | **indetermine** (borne basse) |
| `N` | npc non atteignable | non -- NON PERTINENT |

> **`L~` compte comme confrontable.** Le pool derive du seed BC, qui est la capture d'UNE bataille : son catalogue ne porte que les unites possedees ce jour-la. Un heros hors pool s'INJECTE -- `catalog_inject.write_augmented_seed_bc(<hors data/>, [unitId])` alimente les DEUX catalogues (`Units` ET `Abilities`), puis `rl_duel.py build --seed-bc <chemin>`. Sans la config d'ability le porteur se deploie et FAUTE au cast (#226). Le seul refus legitime est `L!`, lu de `data/unspawnable_rank<N>.json` (repli : `rl_collect_batch.UNSPAWNABLE_FALLBACK`).

## Bilan

- Passifs distincts dans le parc (lineup 127 / npc 491 / summons 65) : **211**
- **PORTES** (>=1 canal structurel) : **144** (68 %)
- **ZONE-GRISE** (direct-read hors registre, a trancher) : **15**
- **GAPS** (mention seule + absent) : **52** = 21 mention + 31 absent
- Passifs portes par >=1 unite **confrontable** : **134** ; parmi eux, **1 gaps** et **3 zone-grise** -> c'est la FILE reelle.

Ventilation des canaux qui portent (un passif peut en cumuler) : **T**=74, **O**=28, **E**=89, **G**=10, **X**=0, **B**=8

## Tableaux par valeur

Tri : nombre de porteurs spawnables SANS AMENAGEMENT (`L+`+`M`) decroissant, puis `S+` (un summon a amener), puis `L~` (une injection de catalogue). Un passif non couvert porte par une unite spawnable vaut plus qu'un passif npc-seul, et un porteur direct coute moins cher a confronter qu'un porteur a amener.

### GAPS **confrontables** -- non couverts ET portes par une unite spawnable (1)

| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ | symbole natif (a confirmer) |
|---|---|---|---|---|---|---|
| FragLance | S+=1 N=1 | astraSmnDeathRider | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FragLanceAbility` |

### ZONE-GRISE confrontable -- reference en code hors registre, couverture a TRANCHER (3)

| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ | symbole natif (a confirmer) |
|---|---|---|---|---|---|---|
| OptimizedGait | L+=1 N=5 | admecRuststalker | ZONE-GRISE | **R** | runner, services | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.OptimizedGaitAbility$$CreateBehaviour` |
| AncientFury | S+=1 | ultraSmnDreadnought | ZONE-GRISE | **R** | runner, services | `IdunBattleLogic.Entities.Abilities.Active.Loki.AncientFury_NormalAttackAbility` |
| FloatingDeath | S+=1 N=1 | tyranSmnSporeMine | ZONE-GRISE | **R** | runner, services | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FloatingDeath_InitAbility$$CreateBehaviour` |

### GAPS non confrontables (npc-only / non spawnable `L!` / summon indetermine `S?`) (51)

| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ |
|---|---|---|---|---|---|
| AllIsDust | S?=1 N=1 | - | GAP-ABSENT | - | - |
| ArchContaminator | N=1 | - | GAP-MENTION | **.** | - |
| BattleFocus | S?=1 N=1 | - | GAP-MENTION | **.** | - |
| BossEndFightUndefeated | N=2 | - | GAP-MENTION | **.** | - |
| CallInReinforcements | S?=1 N=1 | - | GAP-MENTION | **.** | - |
| CloudOfFlies | N=1 | - | GAP-MENTION | **.** | - |
| Conceal | N=1 | - | GAP-MENTION | **.** | - |
| CrazedFocus | N=1 | - | GAP-ABSENT | - | - |
| DaRevolushun | N=1 | - | GAP-MENTION | **.** | - |
| DeathwingKnight | S?=1 N=1 | - | GAP-MENTION | **.** | - |
| EmbodiedProphecy | N=1 | - | GAP-ABSENT | - | - |
| FiringPosition | S?=1 N=1 | - | GAP-MENTION | **.** | - |
| HailOfLivingAmmunition | S?=1 N=5 | - | GAP-MENTION | **.** | - |
| HostOfPlagues | N=1 | - | GAP-ABSENT | - | - |
| HunterOfSouls | S?=1 | - | GAP-MENTION | **.** | - |
| HuntersInstincts | N=1 | - | GAP-MENTION | **.** | - |
| MischiefMakers | S?=1 N=1 | - | GAP-MENTION | **.** | - |
| MultiTracker | N=1 | - | GAP-ABSENT | - | - |
| OiWatchIt | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Bomb | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Damage | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Healing | N=1 | - | GAP-MENTION | **.** | - |
| PowerUp_Health | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_HeroSpawn_BladeChampion | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_HeroSpawn_Uthar | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_HeroSpawn_VexilusPraetor | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Hits | N=1 | - | GAP-MENTION | **.** | - |
| PowerUp_MeleeHits | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_ReactivateAbility | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Reinforcement | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_ReinforcementShield | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Resurrect | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_SummonSpawn_bloodSmnIntercessor | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_SummonSpawn_darkaSmnHellblaster | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_SummonSpawn_darkaSmnTerminator | N=1 | - | GAP-MENTION | **.** | - |
| PowerUp_SummonSpawn_templSmnAggressor | N=1 | - | GAP-MENTION | **.** | - |
| PowerUp_SummonSpawn_ultraSmnHeavyIntercessor | N=1 | - | GAP-MENTION | **.** | - |
| PowerUp_SummonSpawn_ultraSmnInceptor | N=1 | - | GAP-ABSENT | - | - |
| PreCalibratedPurgeSolution | N=1 | - | GAP-ABSENT | - | - |
| PrehensilePincerTail | N=1 | - | GAP-ABSENT | - | - |
| Pyreblaster | S?=1 N=1 | - | GAP-ABSENT | - | - |
| RepairEnthusiast | S?=1 N=1 | - | GAP-ABSENT | - | - |
| RunsAround | N=1 | - | GAP-MENTION | **.** | - |
| RunsAway | N=1 | - | GAP-MENTION | **.** | - |
| SelfRepairMechanismReworked | N=1 | - | GAP-ABSENT | - | - |
| SynapticImperative | N=1 | - | GAP-ABSENT | - | - |
| SynapticInsight | S?=1 N=2 | - | GAP-MENTION | **.** | - |
| TargetLock | N=1 | - | GAP-ABSENT | - | - |
| TheEmperorsShield | N=1 | - | GAP-ABSENT | - | - |
| VengeanceForTheOmnissiah | S?=1 N=1 | - | GAP-ABSENT | - | - |
| Volatile | N=1 | - | GAP-ABSENT | - | - |

### ZONE-GRISE non confrontable (12)

| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ |
|---|---|---|---|---|---|
| Bounce | N=2 | - | ZONE-GRISE | **R** | streams |
| ElectroShock | S?=1 N=2 | - | ZONE-GRISE | **R** | playbook, runner, services |
| Explosive | N=1 | - | ZONE-GRISE | **R** | effects, entities, playbook, runner |
| HeavyBoltPistol | S?=1 N=1 | - | ZONE-GRISE | **R** | playbook, runner, services |
| ItsGonnaBlow | N=1 | - | ZONE-GRISE | **R** | runner |
| Lifewards | S?=1 | - | ZONE-GRISE | **R** | runner |
| NoHidingFromTheWatchers | S?=1 N=1 | - | ZONE-GRISE | **R** | playbook |
| PowerUp_Armor | N=1 | - | ZONE-GRISE | **R** | runner |
| RapidFire | S?=1 N=3 | - | ZONE-GRISE | **R** | playbook |
| Shrapnel | S?=1 N=2 | - | ZONE-GRISE | **R** | playbook |
| WatchedOver | S?=1 N=1 | - | ZONE-GRISE | **R** | playbook, runner |
| Wraithcannon | N=2 | - | ZONE-GRISE | **R** | runner, services |

### PORTES (144)

| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ |
|---|---|---|---|---|---|
| DefenderOfTheGreaterGood | L+=1 S+=1 N=5 | tauShadowsun, tauSmnDroneCommandLink | PORTE | **E**=DefenderOfTheGreaterGood_ExtraDmg,DefenderOfTheGreaterGood_ExtraDmgDrone | effects, runner, utilities |
| AggressiveOnslaught | L+=1 | bloodIntercessor | PORTE | **T**=AggressiveOnslaughtPrepareAbility,AggressiveOnslaughtSummonAbility | playbook, runner |
| AnvilShield | L+=1 | spaceRockfist | PORTE | **T**=AnvilShieldApplyIceAbility,AnvilShieldApplyStunAbility **O**=AnvilShield_BlockChanceBelowHealthCap **E**=AnvilShield_AdditionalBlock,AnvilShield_BlockChanceBelowHealthCap **G**=AnvilShield_FrozenAttackerAdvantage | effects, runner |
| ArcaneShield | L+=1 N=4 | thousSorcerer | PORTE | **T**=ArcaneShieldAbility | runner |
| AstartesBanner | L+=1 N=3 | templAncient | PORTE | **E**=AstartesBanner_ExtraHit | effects, playbook |
| AvalancheOfMuscle | L+=1 N=4 | astraBullgryn | PORTE | **E**=AvalancheOfMuscle_ExtraDamage | effects, playbook |
| BarbedOvipositor | L+=1 N=6 | tyranParasite | PORTE | **T**=BarbedOvipositorSummonAbility | playbook, runner |
| BeaconOfRage | L+=1 N=1 | worldEightbound | PORTE | **E**=BeaconOfRage_ExtraDamage,BeaconOfRage_FriendlyExtraDamage | effects |
| Boltstorm | L+=1 N=4 | templAggressor | PORTE | **B**=litteral exact sous engine/runner/ | playbook, runner, services |
| CamoCloak | L+=1 S?=1 N=5 | ultraEliminatorSgt | PORTE | **O**=CamoCloak_DmgReduction **E**=CamoCloak_DmgReduction | effects |
| ChampionOfTheFeast | L+=1 N=3 | templSwordBrother | PORTE | **T**=ChampionOfTheFeastAbility **E**=ChampionOfTheFeast_ReduceArmor | effects, runner |
| CondemnorStake | L+=1 N=3 | adeptCanoness | PORTE | **E**=CondemnorStake_ExtraDmg | effects |
| ControlEdict | L+=1 N=5 | admecMarshall | PORTE | **T**=ControlEdictAbility | playbook, runner |
| CosmicHorror | L+=1 N=3 | genesPatriarch | PORTE | **T**=CosmicHorrorOnKillAbility,CosmicHorrorOnMoveAbility | playbook, runner |
| CursedPlagueBell | L+=1 N=3 | deathBlightbringer | PORTE | **T**=CursedPlagueBellMovementAbility,CursedPlagueBellAttackAbility **E**=CursedPlagueBell_ExtraMove | effects, playbook, runner |
| CyclicIonBlaster | L+=1 N=4 | tauCrisis | PORTE | **E**=CyclicIonBlaster_AdditionalHits | effects, runner |
| DaughterOfTheAbyss | L+=1 | custoAtlacoya | PORTE | **E**=DaughterOfTheAbyss_ExtraDamagePct,DaughterOfTheAbyss_FriendlyDmgReductionPct | effects |
| Deathwing | L+=1 N=2 | darkaTerminator | PORTE | **T**=DeathwingAbility **E**=Deathwing | effects, playbook, runner |
| DecoysAndMisdirection | L+=1 N=3 | genesPrimus | PORTE | **T**=DecoysAndMisdirectionDamageEnemiesAbility,DecoysAndMisdirectionBuffFriendsAbility **E**=DecoysAndMisdirection_ExtraDamage | effects, runner, utilities |
| DestroyTheWitch | L+=1 N=2 | templHelbrecht | PORTE | **E**=DestroyTheWitch_ExtraDamage,DestroyTheWitch_ExtraMove | effects |
| DestroyerHive | L+=1 N=5 | deathTyphus | PORTE | **T**=DestroyerHiveAbility | runner |
| Doom | L+=1 N=5 | eldarFarseer | PORTE | **E**=Doom_extraDmg | effects, entities, playbook, runner |
| EnmityForTheUnworthy | L+=1 N=2 | darkaCompanion | PORTE | **O**=EnmityForTheUnworthy_ExtraDamage,EnmityForTheUnworthy_ExtraDamagePct **E**=EnmityForTheUnworthy_ExtraDamage,EnmityForTheUnworthy_ExtraDamagePct | effects |
| ExplosiveMaladies | L+=1 N=3 | deathPutrifier | PORTE | **E**=ExplosiveMaladies_ExtraMeleeAttack,ExplosiveMaladies_ExtraRangedAttack | effects |
| FabricatorClawArray | L+=1 N=5 | necroSpyder | PORTE | **T**=FabricatorClawArrayAbility | playbook, runner |
| FearedInterrogator | L+=1 N=2 | darkaAsmodai | PORTE | **O**=FearedInterrogator_Owner,FearedInterrogator_Target **E**=FearedInterrogator_Owner,FearedInterrogator_Target | effects, playbook |
| FeederTendrils | L+=1 N=6 | tyranDeathleaper | PORTE | **E**=FeederTendrils_ExtraDamage | effects, runner, services |
| FireOfAbsolution | L+=1 N=3 | adeptRetributor | PORTE | **B**=litteral exact sous engine/runner/ | playbook, runner |
| FirstAmongTraitors | L+=1 N=5 | blackAbaddon | PORTE | **O**=FirstAmongTraitors_ExtraDmg **E**=FirstAmongTraitors_ExtraDmg | effects, playbook |
| FleshmetalGuns | L+=1 N=6 | blackObliterator | PORTE | **T**=FleshmetalGunsRotationAbility,FleshmetalGunsTileEffectAbility | effects, runner |
| FuelledByFury | L+=1 N=3 | ultraTitus | PORTE | **T**=FuelledByFuryExtraDamageAbility,FuelledByFuryReviveAbility **E**=FuelledByFury_ExtraDamage | effects, runner |
| FuryOfTheAncients | L+=1 | bloodMephiston | PORTE | **T**=FuryOfTheAncientsAbility **E**=FuryOfTheAncients | effects, entities, playbook, runner |
| GalvanicField | L+=1 N=5 | admecManipulus | PORTE | **B**=litteral exact sous engine/runner/ | ai, entities, playbook, runner, services |
| GrimRetribution | L+=1 N=2 | darkaHellblaster | PORTE | **E**=GrimRetribution_CounterAttack **G**=GrimRetribution_CounterAttack | effects, runner |
| GuardianOrganism | L+=1 N=5 | tyranTyrantGuard | PORTE | **E**=GuardianOrganism_DamageReduction | effects, playbook |
| HatefulAssault | L+=1 N=4 | blackTerminator | PORTE | **T**=HatefulAssaultAttackAbility **E**=HatefulAssault_AlreadyAttacked **G**=HatefulAssault_AlreadyAttacked | effects, playbook, runner |
| HazeOfCorruption | L+=1 N=4 | deathBlightlord | PORTE | **T**=HazeOfCorruptionTargetFinderAbility,HazeCorruptionBonusHitAbility | runner |
| HeadClaimer | L+=1 N=5 | blackHaarken | PORTE | **T**=HeadClaimerOnDeathAbility,HeadClaimerOnFledAbility **E**=HeadClaimer_ExtraDmg,HeadClaimer_ExtraHit | effects, runner |
| HeavyGravCannon | L+=1 N=3 | admecDestroyer | PORTE | **E**=HeavyGravCannon | effects |
| HuntersBeyondDeath | L+=1 | spaceHound | PORTE | **O**=HuntersBeyondDeath,HuntersBeyondDeath_ExtraDamage **E**=HuntersBeyondDeath,HuntersBeyondDeath_ExtraDamage | effects, entities, playbook, runner |
| HypersensoryAbilities | L+=1 N=4 | genesKelermorph | PORTE | **T**=HypersensoryMoveAndSpawnDecoyAbility **O**=HypersensoryAbilities_MinimalHealth **E**=HypersensoryAbilities_MinimalHealth | effects, runner |
| InescapableAccuracy | L+=1 N=5 | eldarMauganRa | PORTE | **E**=InescapableAccuracy_extraCritChance,InescapableAccuracy_extraCritDmg | effects |
| InescapableDeath | L+=1 N=5 | necroDestroyer | PORTE | **O**=InescapableDeath_Effect **E**=InescapableDeath_Effect **G**=InescapableDeath_Effect | effects, runner |
| InfernalPacts | L+=1 N=5 | thousInfernalMaster | PORTE | **O**=InfernalPacts_AdditionalHits **E**=InfernalPacts_AdditionalHits | effects |
| KustomForceFieldReworked | L+=1 N=4 | orksBigMek | PORTE | **O**=KustomForceFieldReworked,KustomForceFieldReworked_Orks **E**=KustomForceFieldReworked,KustomForceFieldReworked_Orks | effects, playbook |
| LegacyOfCombat | L+=1 | custoBladeChampion | PORTE | **T**=LegacyOfCombatAdditionalAttackAbility | effects, playbook, runner |
| LegendaryCommander | L+=1 | custoTrajann | PORTE | **E**=LegendaryCommander_ExtraHits **G**=LegendaryCommander_ExtraHits | effects, runner |
| LightImUp | L+=1 N=4 | orksWarboss | PORTE | **T**=LightImUpAbility | entities, playbook, runner |
| LionHelm | L+=1 N=2 | darkaAzrael | PORTE | **O**=LionHelm_ExtraDmg,LionHelm_ExtraBlockChance **E**=LionHelm_ExtraBlockChance,LionHelm_ExtraBlockDamage | effects |
| LordOfTempests | L+=1 N=1 | spaceStormcaller | PORTE | **T**=LordOfTempestsAddIceAbility **E**=LordOfTempests_ExtraDamage | effects, runner |
| LordOfTheHost | L+=1 | bloodDante | PORTE | **E**=LordOfTheHost_ExtraDamage | effects |
| MV71SniperDroneSquad | L+=1 N=4 | tauMarksman | PORTE | **E**=MV71SniperDroneSquad_InitialDmg,MV71SniperDroneSquad_ResetInitialDmg | effects, playbook, runner, services |
| MartialSuperiority | L+=1 N=5 | templChampion | PORTE | **T**=MartialSuperiorityRiposteAbility **E**=MartialSuperiority_Visual | effects, runner |
| MasterAnnihilator | L+=1 N=5 | admecDominus | PORTE | **T**=MasterAnnihilatorMarkAbility **E**=MasterAnnihilator_extraHit | effects, runner |
| MedicusMinistorum | L+=1 N=3 | adeptHospitaller | PORTE | **T**=MedicusMinistorumAbility | playbook, runner |
| MyWillBeDoneOverlord | L+=1 N=5 | necroOverlord | PORTE | **T**=MyWillBeDoneOverlordAttackAbility,MyWillBeDoneOverlordClearAbility **E**=MyWillBeDoneOverlord_ExtraDamage | effects, playbook, runner |
| Narthecium | L+=1 N=3 | ultraApothecary | PORTE | **T**=NartheciumReviveAbility | runner |
| Neuroparasite | L+=1 N=6 | tyranNeurothrope | PORTE | **T**=NeuroparasiteAddBondEffectAbility **E**=Neuroparasite **G**=Neuroparasite | effects, playbook, runner |
| Nightshroud | L+=1 N=4 | astraPrimarisPsy | PORTE | **E**=Nightshroud_DmgReduction | effects |
| ObsessiveAnnunciation | L+=1 | emperKakophonist | PORTE | **T**=ObsessiveAnnunciationOverkillAbility **O**=ObsessiveAnnunciation_ExtraDmg **E**=ObsessiveAnnunciation_ExtraCritDmg,ObsessiveAnnunciation_ExtraDmg | effects, playbook, runner |
| PathOfCommand | L+=1 N=3 | eldarAutarch | PORTE | **O**=PathOfCommand_ExtraCrit,PathOfCommand_ExtraDmg **E**=PathOfCommand_ExtraCrit,PathOfCommand_ExtraDmg | effects |
| Possession | L+=1 N=4 | blackPossession | PORTE | **T**=PossessionSummonOnKillAbility | runner |
| PowerTrip | L+=1 N=4 | orksKillaKan | PORTE | **E**=PowerTrip_FullHealth,PowerTrip_IgnoreArmor | effects |
| PsychicFortress | L+=1 N=3 | ultraTigurius | PORTE | **E**=PsychicFortress_DmgReduction,PsychicFortress_ExtraBlock | effects, playbook |
| PsychicStalk | L+=1 N=4 | thousAhriman | PORTE | **E**=PsychicStalk_ExtraAttackDamage,PsychicStalk_FriendlyChaosExtraDamage | effects |
| RealityUnbound | L+=1 N=4 | thousTzaangor | PORTE | **T**=RealityUnboundAbility,RealityUnboundExtraMaxDamageAbility **E**=RealityUnbound_ExtraMaxDamage,RealityUnbound_Movement | effects, runner |
| RelentlessMarch | L+=1 N=5 | necroWarden | PORTE | **T**=RelentlessMarchAbility **E**=RelentlessMarch_Effect | effects, runner |
| RighteousRepugnance | L+=1 N=3 | adeptMorvenn | PORTE | **B**=litteral exact sous engine/runner/ | playbook, runner, services |
| RitesOfBattle | L+=1 N=3 | ultraCalgar | PORTE | **E**=RitesOfBattle_ExtraDmgBasic,RitesOfBattle_ExtraDmgImperial | effects, playbook |
| SagaOfTheWarriorBorn | L+=1 | spaceBlackmane | PORTE | **E**=SagaOfTheWarriorBorn_OtherSpaceWolves,SagaOfTheWarriorBorn_Owner | effects |
| SanguinaryPriest | L+=1 | bloodSanguinary | PORTE | **T**=SanguinaryPriestAbility | playbook, runner |
| SavageKiller | L+=1 | spaceWulfen | PORTE | **T**=SavageKillerAbility | runner |
| SereneUnifier | L+=1 N=4 | tauAunShi | PORTE | **T**=SereneUnifierRotationAbility | effects, playbook, runner |
| ShockAssault | L+=1 N=3 | ultraInceptorSgt | PORTE | **E**=ShockAssault_Buff **G**=ShockAssault_Buff | effects, runner |
| Skullsmasher | L+=1 N=1 | worldJakhal | PORTE | **T**=SkullsmasherActivateStunAbility,SkullsmasherTriggerStunAbility **O**=Skullsmasher_ExtraDamage **E**=Skullsmasher_ExtraDamage | effects, runner |
| SmashaEad | L+=1 N=4 | orksNob | PORTE | **E**=SmashaEad | effects |
| SpiritualLeader | L+=1 N=4 | genesMagus | PORTE | **T**=SpiritualLeaderAbility | playbook, runner |
| SpotterReworked | L+=1 N=4 | astraOrdnance | PORTE | **E**=SpotterReworked_ExtraDamage,SpotterReworked_HeavyWeapon | effects |
| SquigHound | L+=1 N=4 | orksRuntherd | PORTE | **E**=SquigHound_AdditionalHits | effects, runner |
| StandVigil | L+=1 | custoVexilusPraetor | PORTE | **E**=StandVigil_ExtraArmor | effects |
| StructuralAnalyser | L+=1 N=4 | tauDarkstrider | PORTE | **E**=StructuralAnalyser_Visual | effects, runner |
| SummaryExecution | L+=1 N=6 | astraYarrick | PORTE | **T**=SummaryExecutionAbility **O**=SummaryExecution_BaseEffect **E**=SummaryExecution_BaseEffect,SummaryExecution_Effect | effects, runner |
| SwornProtector | L+=1 N=5 | astraCreed | PORTE | **T**=SwornProtectorSummonKellAbility | runner, utilities |
| SynapticLinchpin | L+=1 N=7 | tyranWingedPrime | PORTE | **T**=SynapticLinchpinAbility | runner |
| TaintedNarthecium | L+=1 N=3 | deathRotbone | PORTE | **T**=TaintedNartheciumReviveAbility | runner |
| TerrifyingCrescendo | L+=1 | emperNoiseMarine | PORTE | **T**=TerrifyingCrescendoOverkillAbility,TerrifyingCrescendoSuppressAbility **E**=TerrifyingCrescendo_ExtraDmg | effects, runner |
| TerrorsLament | L+=1 N=4 | eldarJainZar | PORTE | **O**=TerrorsLament_DamageReduction,TerrorsLament_HitReduction **E**=TerrorsLament_DamageReduction,TerrorsLament_HitReduction | effects |
| TheBetrayer | L+=1 N=1 | worldKharn | PORTE | **T**=TheBetrayerAddEffectAbility,TheBetrayerTakeTurnAbility | runner |
| TimeFlux | L+=1 N=5 | thousTerminator | PORTE | **T**=TimeFluxRegenAbility,TimeFluxReviveAbility | runner |
| ToughToKill | L+=1 N=1 | astraDreir | PORTE | **T**=ToughToKillHealAbility **O**=ToughToKill **E**=ToughToKill | effects, runner |
| TrophyTaker | L+=1 N=1 | worldExecutions | PORTE | **T**=TrophyTakerOnUnitDefeatedAbility **E**=TrophyTaker_ExtraCritDamage | effects, runner |
| TwistedScience | L+=1 N=3 | genesBiophagus | PORTE | **E**=TwistedScience_ExtraDmg,TwistedScience_ExtraHp | ai, effects, entities, playbook, runner |
| UnwaveringSentinel | L+=1 | custoKyrus | PORTE | **E**=UnwaveringSentinel_CounterAttack **G**=UnwaveringSentinel_CounterAttack | effects, runner |
| VisionsOfHeresy | L+=1 | bloodDeathCompany | PORTE | **O**=VisionsOfHeresy_ExtraPierceMelee,VisionsOfHeresy_ExtraPierceRanged **E**=VisionsOfHeresy_ExtraPierceMelee,VisionsOfHeresy_ExtraPierceRanged | effects |
| WireweaveNet | L+=1 N=4 | eldarRanger | PORTE | **E**=WireweaveNet_CounterAttack **G**=WireweaveNet_CounterAttack | effects, runner, utilities |
| WrathfulDevotion | L+=1 N=1 | worldTerminator | PORTE | **T**=WrathfulDevotionAbility | runner |
| SaviorProtocols | S+=3 N=3 | tauSmnDroneCommandLink, tauSmnDroneShield, tauSmnDroneSniper | PORTE | **T**=SaviorProtocolsAbility | playbook, runner, utilities |
| AdrenalGlands | S+=2 N=4 | tyranNpc1Hormagaunt, tyranSmnHormagaunt | PORTE | **O**=AdrenalGlands_Effect **E**=AdrenalGlands_Effect | effects |
| HungeringSwarm | S+=2 N=4 | tyranNpc1Hormagaunt, tyranSmnHormagaunt | PORTE | **E**=HungeringSwarm_ExtraHits | effects |
| ReanimationProtocols | S+=2 S?=1 N=6 | necroSmnSwarm, necroSmnWarrior | PORTE | **T**=ReanimationProtocolsAbility | runner |
| CursedOfTheWalkingPox | S+=1 N=1 | deathPoxwalker | PORTE | **T**=CursedOfTheWalkingPoxSummonAbility | runner |
| FlamesOfMutation | S+=1 S?=1 | thousSmnBlueHorror | PORTE | **T**=FlamesOfMutationAbility | runner |
| Hypermorph | S+=1 N=1 | genesSmnAberrant | PORTE | **O**=Hypermorph **E**=Hypermorph | effects |
| ListenUpMaggots | S+=1 | astraSmnKell | PORTE | **T**=ListenUpMaggotsAddEffectAbility | effects, runner |
| PileIn | S+=1 N=1 | orksGrot | PORTE | **B**=litteral exact sous engine/runner/ | runner |
| RadSaturation | S+=1 N=2 | admecSmnVanguard | PORTE | **T**=RadSaturationAbility | playbook, runner |
| Ramshackle | S+=1 N=1 | orksGrotTank | PORTE | **O**=Ramshackle_DmgReduction **E**=Ramshackle_DmgReduction | effects |
| RedThirst | S+=1 N=1 | bloodSmnIntercessor | PORTE | **O**=RedThirst_ExtraDamageAndHit **E**=RedThirst_ExtraDamageAndHit | effects |
| ReinforcedHiveNode | S+=1 N=4 | tyranSmnWarrior | PORTE | **E**=ReinforcedHiveNode_ExtraArmor,ReinforcedHiveNode_ExtraBlock | effects |
| Split | S+=1 S?=1 N=1 | thousSmnPinkHorror | PORTE | **T**=SplitAbility | runner |
| SwornProtector_Protect | S+=1 | astraSmnKell | PORTE | **T**=SwornProtectorProtectSwitchAbility | runner |
| UnstoppableFerocity | S+=1 S?=1 N=1 | blackSmnBloodletter | PORTE | **E**=UnstoppableFerocity_OwnerEffect | effects |
| ArmourOfShriekingSouls | L~=1 | emperLucius | PORTE | **T**=ArmourOfShriekingSoulsOnDeathAbility | runner |
| EcogSupport | L~=1 | votanIronmaster | PORTE | **T**=ECogSupportAbility | effects, playbook, runner |
| EcstaticSlaughter | L~=1 | emperFlawlessBlade | PORTE | **T**=EcstaticSlaughterOnThrilledAbility,EcstaticSlaughterOnOverkillAbility | runner |
| FuryFromTheDelve | L~=1 | votanBeserk | PORTE | **T**=FuryFromTheDelveCheckTargetHealthAbility,FuryFromTheDelveAttackOrPinAbility | runner |
| GeminaeSuperia | L~=1 N=4 | adeptCelestine | PORTE | **T**=GeminaeSuperiaAbility | playbook, runner |
| GrimEfficiency | L~=1 | votanUthar | PORTE | **O**=GrimEfficiency_ExtraArmor,GrimEfficiency_ExtraPierce **E**=GrimEfficiency_ExtraArmor,GrimEfficiency_ExtraPierce | effects, playbook |
| HaywireMine | L~=1 N=1 | astarCyrus | PORTE | **T**=HaywireMinePlaceOnMoveAbility,HaywireMinePlaceOnTurnEndAbility | playbook, runner |
| HealingBalms | L~=1 | spaceWolfPriest | PORTE | **E**=HealingBalms_ExtraCritChance,HealingBalms_ExtraCritDamage | ai, effects, entities, playbook, runner |
| IconOfObstinacy | L~=1 | astarLysander | PORTE | **T**=IconOfObstinacyAddArmourBuffAbility **O**=IconOfObstinacy_ExtraDmg **E**=IconOfObstinacy_ExtraArmor,IconOfObstinacy_ExtraDmg | effects, playbook, runner |
| ModifiedExoarmour | L~=1 | votanChampion | PORTE | **O**=ModifiedExoarmour_ExtraDmg **E**=ModifiedExoarmour_ExtraDmg | effects, playbook |
| PredictiveGuidance | L~=1 | votanMemnyr | PORTE | **O**=PredictiveGuidance_Melee,PredictiveGuidance_Ranged **E**=PredictiveGuidance_ExtraHits,PredictiveGuidance_Melee | effects |
| PropheticSentinel | L~=1 | thousSekhetar | PORTE | **T**=PropheticSentinelOverwatchAbility **O**=PropheticSentinel_ExtraArmor,PropheticSentinel_ExtraBlockChance **E**=PropheticSentinel_ExtraArmor,PropheticSentinel_ExtraBlockChance | effects, playbook, runner |
| RedRampage | L~=1 N=1 | bloodTerminator | PORTE | **T**=RedRampageAttackAbility,RedRampageBuffAbility | playbook, runner |
| RefusalToBeOutdone | L~=1 | emperExultant | PORTE | **T**=RefusalToBeOutdoneRecordHitAbility,RefusalToBeOutdoneResetOnTurnEndAbility | runner |
| SpecialIssueCombiMelta | L~=1 N=1 | darkaSternguard | PORTE | **T**=SpecialIssueCombiMeltaAddEffectAbility **E**=SpecialIssueCombiMelta_AdditionalHits,SpecialIssueCombiMelta_ExtraDmg | effects, playbook, runner |
| TimesplinterMantle | L~=1 N=4 | necroChronomancer | PORTE | **T**=TimesplinterMantleAbility **E**=TimesplinterMantle_DamageReduction **G**=TimesplinterMantle_DamageReduction | effects, playbook, runner |
| WayOfTheShortBlade | L~=1 N=5 | tauFarsight | PORTE | **E**=WayOfTheShortBlade_AdditionalAttackMarker,WayOfTheShortBlade_DamageBuff | effects, playbook |
| WhisperingWeb | L~=1 | eldarLhykhis | PORTE | **T**=WhisperingWebAbility | runner |
| DrawFire | S?=1 N=1 | - | PORTE | **B**=litteral exact sous engine/runner/ | runner |
| EchoesFromTheWarp | N=1 | - | PORTE | **T**=EchoesFromTheWarpAbility | runner, utilities |
| Fealty | N=1 | - | PORTE | **B**=litteral exact sous engine/runner/ | runner, services |
| FullThrottle | N=1 | - | PORTE | **T**=FullThrottlePassiveAbility | runner |
| HarlequinsPanoply | S?=1 N=1 | - | PORTE | **B**=litteral exact sous engine/runner/ | runner |
| HaywireMineSteppable | S?=1 N=1 | - | PORTE | **T**=HaywireMineSteppableAbility | runner |
| LivingLightning | L!=1 N=5 | - | PORTE | **T**=LivingLightningAttackAbility,LivingLightningMoveEffectAbility | runner |
| OmnissiahsBlessing | S?=1 N=1 | - | PORTE | **T**=OmnissiahsBlessingAbility | runner |
| PrimarchOfTheFirstLegion | N=1 | - | PORTE | **E**=PrimarchOfTheFirstLegion_ExtraDamage | effects, playbook, runner |
| PurgeResponse | S?=1 N=1 | - | PORTE | **E**=PurgeResponse | effects, playbook |
| ShroudPsalm | N=1 | - | PORTE | **E**=ShroudPsalm | effects |
| StormboyzStrike | N=1 | - | PORTE | **T**=StormboyzStrikeTeleportAbility,StormboyzStrikeFallbackAbility | ai, effects, entities, runner, services |
| VoltagheistField | S?=1 N=2 | - | PORTE | **E**=VoltagheistField_ExtraHit | effects, predict |
| WhipcoilBody | S?=1 N=3 | - | PORTE | **O**=WhipcoilBody_ReduceDmg **E**=WhipcoilBody_ReduceDmg | effects |

## FILE DISPATCHABLE

Passifs **non couverts** (GAP-MENTION ou GAP-ABSENT) **ET confrontables** (>=1 porteur `L+`/`M`/`S+`) : **1 items**. Le symbole natif est resolu PAR NOM dans `data/symbols/<build>/frida/methods.tsv` -- **a confirmer en ghidra avant tout port** (`search_symbols_by_name`), ce n'est pas une preuve d'existence de la mecanique.

| # | passif | porteurs spawnables | ventilation | verdict | symbole natif (a confirmer) |
|---|---|---|---|---|---|
| 1 | **FragLance** | astraSmnDeathRider | S+=1 N=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FragLanceAbility` |

> Rappel de dispatch : un passif **`S+`** se confronte en spawnant son **summoner** (qui, lui, est dans le pool) -- ne jamais le classer « non confrontable ». Les `S?` sont a re-qualifier a la main (leur spawn n'est pas exprime dans `constants`).

## Ce qui n'est PAS couvert par cet audit

- **Fidelite** : un passif PORTE peut l'etre FAUSSEMENT (cas fondateur `HeavyGravCannon`, canal **E**, divergence live). Cet audit mesure la PRESENCE d'un cablage, jamais sa justesse.
- **[E]/[G] reposent sur une convention de NOMMAGE** (meme convention que `audit_kit_coverage._has_effect_named_after`), pas sur un lien lu du natif : verifie sur ce run, **0/211** des `constants` d'un passif nomment un `EffectType`. Le gameconfig n'exprime AUCUN lien passif->effet.
- **Completude d'un passif multi-volets** : un passif dont 1 volet sur 3 est porte compte comme PORTE (ex. `AnvilShield`). Le decoupage par volet est un travail de recon.
- **Face DECISION** : hors perimetre -- un passif ne se caste pas, il n'a pas de playbook. Seule la face COMBAT est auditee.
- **Reachability `S?`** : borne basse assumee -- **36** des 65 summons du parc n'ont AUCUNE arete derivable du gameconfig (leur spawn n'est pas exprime dans `constants`) et sont donc comptes non-confrontables par defaut.
- **Traits** : mecanique voisine mais registre distinct -> `docs/rl/unit-trait-coverage.md`.

### Relation aux audits existants

- `docs/rl/combat-ability-coverage.md` (par-ability ACTIVE) : disjoint de celui-ci -- l'intersection des noms actives/passifs est vide.
- `docs/rl/kit-coverage.md` (par KIT) mesure deja des passifs, mais **des seules unites `lineup`** et avec un booleen a 3 signaux (`ABILITY_TRIGGERS` / `ABILITY_INIT_OWNER_EFFECTS` / effet homonyme). Cet audit-ci couvre **tout le parc** (lineup + npc + summons), rend un verdict PAR PASSIF avec son CANAL, ventile les porteurs par confrontabilite, et ajoute 3 signaux (`ABILITY_OWNER_EFFECTS`, `EFFECT_TRIGGERS`, bespoke `runner/`) -- son jeu de canaux est un SUR-ENSEMBLE. Les deux reposent sur la meme convention de nommage pour le canal effet, donc ils ne peuvent pas se contredire sur les signaux partages ; ils se completent (vue KIT = « que reste-t-il a faire sur cette unite », vue PASSIF = « ce mecanisme est-il branche »).
