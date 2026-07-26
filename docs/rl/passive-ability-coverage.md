# Couverture moteur des abilities PASSIVES

> Genere par `scripts/python/audit_passive_ability_coverage.py` (gameconfig `passiveAbilities` x registres moteur x pool spawnable live). A regenerer au changement de build ou apres tout port. TOUS les chiffres de ce document sont re-derives a chaque run -- aucun n'est recopie.

## Pourquoi cet audit existe : l'angle mort est STRUCTUREL

`audit_combat_ability_coverage.py` (#95) croise `activeAbilities` x `ABILITY_CLASSES`, registre keye par **`ActiveAbilityType`**. Or, mesure de ce run sur les **207 passifs distincts** du parc :

| enum natif d'appartenance | passifs |
|---|---|
| `TriggeredAbilityType` | **206** |
| `ActiveAbilityType` | **1** |
| homonyme d'un `EffectType` | 27 |
| aucun des trois | 0 |

L'intersection nom-a-nom actives/passifs est **VIDE**. Un passif n'est donc pas une ability active « non castable » : c'est une **`TriggeredAbilityType`**, un objet d'un AUTRE enum, instancie a l'init de l'unite (`collect_triggered_abilities` cote port, `AbilityAndEffectCache` cote natif). L'audit des actives ne pouvait structurellement rien en voir.

Cas fondateur : `HeavyGravCannon`, passif d'`admecDestroyer` -- il expliquait un delta de degat live/offline reste longtemps sans cause, et n'apparaissait dans AUCUN audit (cf. `docs/rl/case-220/admec.md`, `docs/rl/case-101-moved-flag.md`). Ce meme cas documente le piege a ne jamais oublier ici, une **homonymie a TROIS faces** : `EffectType 1291 = HeavyGravCannon` (le nom CAPTE live), `TriggeredAbilityType 1233 = HeavyGravCannon` (la CONFIG du passif), `TriggeredAbilityType 1291 = SelfRepairMechanism` (**sans aucun rapport**). Le meme id dans deux enums nomme deux objets differents, et le meme nom dans deux enums porte deux ids differents -> **tout rapprochement par nom ou par id doit qualifier son enum**. Ce run mesure **27** des 207 passifs homonymes d'un `EffectType` : c'est exactement la population exposee a ce piege, et donc la limite du canal **E**.

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

Mesure de ce run : un `substring` brut du nom sur `engine/**/*.py` rend **207/207 presents, 0 manquant**. La cause n'est pas que tout est porte : `engine/entities/triggered_ability_type.py` est un **mirror 1:1 de l'enum natif `TriggeredAbilityType`** (573 membres), ou le nom de CHAQUE passif figure comme membre. **Un catalogue n'est pas un cablage.**

Le signal code de cet audit est donc derive de l'**AST** et exclut les **definitions** de membres d'enum (1904 assignations ecartees dans 248 fichiers `engine/**/*.py`) tout en gardant les **usages** (`TriggeredAbilityType.X` = `ast.Attribute` -> compte). Il separe en outre le CODE (5634 symboles distincts) de la PROSE (2495 ko de commentaires + docstrings, invisibles a l'AST, lus via `tokenize`). Le rapprochement est CamelCase-aware : `HeavyGravCannon` matche `HeavyGravCannonEffect`, `Guard` ne matche ni `Guardsman` ni `RoyalGuard` (ni, pour `Possession`, l'unitId `blackPossession`).

Chaque reference est en outre ATTRIBUEE A SA ZONE du moteur (`__init__, ai, battle_query, dsl, effects, entities, move, playbook, predict, runner, services, utilities, weights`), parce qu'une reference dans `playbook/`/`ai/`/`utilities/` (face DECISION) ne prouve RIEN sur l'execution combat. C'est ce qui separe **B** (litteral exact sous `runner/`) de **R**.

### Confrontabilite des porteurs (gate HERO / MoW / SUMMON -- jamais NPC)

La colonne `kind` de gameconfig MENT sur la spawnabilite -> le pool vient de la verite native `buildNormalizedBC` (`rl_duel.py build --list-pool`, rank **17** : 97 unites regulieres + 8 MoW).

| code | signification | confrontable |
|---|---|---|
| `L+` | lineup PRESENT dans le pool | **oui** |
| `M` | MachineOfWar du pool | **oui** |
| `S+` | hors pool mais ATTEIGNABLE par summon depuis le pool (fermeture transitive du graphe `constants.unitId*`/`unitIds`/`unitToSpawn`, 226 aretes -> 31 unites atteintes) | **oui**, via son summoner |
| `L-` | lineup ABSENT du pool au rank courant | non (hero non spawnable) |
| `S?` | summon sans summoner derivable du gameconfig | **indetermine** (borne basse) |
| `N` | npc non atteignable | non -- NON PERTINENT |

## Bilan

- Passifs distincts dans le parc (lineup 123 / npc 481 / summons 65) : **207**
- **PORTES** (>=1 canal structurel) : **46** (22 %)
- **ZONE-GRISE** (direct-read hors registre, a trancher) : **11**
- **GAPS** (mention seule + absent) : **150** = 39 mention + 111 absent
- Passifs portes par >=1 unite **confrontable** : **116** ; parmi eux, **63 gaps** et **7 zone-grise** -> c'est la FILE reelle.

Ventilation des canaux qui portent (un passif peut en cumuler) : **T**=18, **O**=4, **E**=31, **G**=1, **X**=0, **B**=3

## Tableaux par valeur

Tri : nombre de porteurs spawnables (`L+`+`M`) decroissant, puis `S+`. Un passif non couvert porte par une unite spawnable vaut plus qu'un passif npc-seul.

### GAPS **confrontables** -- non couverts ET portes par une unite spawnable (63)

| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ | symbole natif (a confirmer) |
|---|---|---|---|---|---|---|
| BarbedOvipositor | L+=1 N=6 | tyranParasite | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateBehaviour` |
| Boltstorm | L+=1 N=3 | templAggressor | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BoltstormAbility` |
| CamoCloak | L+=1 S?=1 N=5 | ultraEliminatorSgt | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.CamoCloakAbility$$CreateBehaviour` |
| ChampionOfTheFeast | L+=1 N=3 | templSwordBrother | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ChampionOfTheFeastAbility$$CreateBehaviour` |
| CosmicHorror | L+=1 N=3 | genesPatriarch | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateBehaviour` |
| CursedPlagueBell | L+=1 N=3 | deathBlightbringer | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$CreateBehaviour` |
| Deathwing | L+=1 N=2 | darkaTerminator | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DeathwingAbility$$CreateBehaviour` |
| DestroyTheWitch | L+=1 N=2 | templHelbrecht | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DestroyTheWitchAbility$$CreateBehaviour` |
| EnmityForTheUnworthy | L+=1 N=2 | darkaCompanion | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnmityForTheUnworthyAbility$$CreateBehaviour` |
| FearedInterrogator | L+=1 N=2 | darkaAsmodai | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FearedInterrogatorAbility$$CreateBehaviour` |
| FirstAmongTraitors | L+=1 N=5 | blackAbaddon | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.FirstAmongTraitorsAbility` |
| FuelledByFury | L+=1 N=3 | ultraTitus | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility$$CreateBehaviour` |
| GrimRetribution | L+=1 N=2 | darkaHellblaster | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GrimRetributionAbility` |
| HatefulAssault | L+=1 N=4 | blackTerminator | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.HatefulAssaultAbility$$CreateBehaviour` |
| HazeOfCorruption | L+=1 N=4 | deathBlightlord | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour` |
| HeadClaimer | L+=1 N=5 | blackHaarken | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.HeadClaimerAbility$$CreateBehaviour` |
| InescapableAccuracy | L+=1 N=5 | eldarMauganRa | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracyAbility$$CreateBehaviour` |
| InescapableDeath | L+=1 N=5 | necroDestroyer | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.InescapableDeathAbility` |
| KustomForceFieldReworked | L+=1 N=3 | orksBigMek | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.KustomForceFieldReworkedAbility$$CreateBehaviour` |
| LegacyOfCombat | L+=1 | custoBladeChampion | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegacyOfCombatAbility$$CreateBehaviour` |
| LegendaryCommander | L+=1 | custoTrajann | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegendaryCommanderAbility$$CreateBehaviour` |
| LightImUp | L+=1 N=4 | orksWarboss | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility$$CreateBehaviour` |
| LionHelm | L+=1 N=2 | darkaAzrael | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LionHelmAbility$$CreateBehaviour` |
| MartialSuperiority | L+=1 N=4 | templChampion | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MartialSuperiorityAbility$$CreateBehaviour` |
| MedicusMinistorum | L+=1 N=3 | adeptHospitaller | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.MedicusMinistorumAbility$$CreateBehaviour` |
| ObsessiveAnnunciation | L+=1 | emperKakophonist | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ObsessiveAnnunciationAbility` |
| OptimizedGait | L+=1 N=5 | admecRuststalker | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.OptimizedGaitAbility$$CreateBehaviour` |
| Possession | L+=1 N=4 | blackPossession | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.PossessionAbility$$CreateBehaviour` |
| PsychicStalk | L+=1 N=4 | thousAhriman | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PsychicStalk_ApplyFireTileAbility$$CreateBehaviour` |
| RealityUnbound | L+=1 N=4 | thousTzaangor | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RealityUnboundAbility$$CreateBehaviour` |
| RelentlessMarch | L+=1 N=5 | necroWarden | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility$$CreateBehaviour` |
| SagaOfTheWarriorBorn | L+=1 | spaceBlackmane | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SagaOfTheWarriorBorn_InitAbility` |
| SanguinaryPriest | L+=1 | bloodSanguinary | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SanguinaryPriestAbility$$CreateBehaviour` |
| SavageKiller | L+=1 | spaceWulfen | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SavageKillerAbility$$CreateBehaviour` |
| SereneUnifier | L+=1 N=3 | tauAunShi | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour` |
| ShockAssault | L+=1 N=3 | ultraInceptorSgt | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.ShockAssaultAbility$$CreateBehaviour` |
| Skullsmasher | L+=1 N=1 | worldJakhal | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Skullsmasher_TriggerStunAbility$$CreateBehaviour` |
| SpiritualLeader | L+=1 N=4 | genesMagus | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$CreateBehaviour` |
| StructuralAnalyser | L+=1 N=4 | tauDarkstrider | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddDamageBuffAbility$$CreateBehaviour` |
| SummaryExecution | L+=1 N=6 | astraYarrick | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.SummaryExecutionAbility$$CreateBehaviour` |
| SynapticLinchpin | L+=1 N=7 | tyranWingedPrime | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility$$CreateBehaviour` |
| TerrorsLament | L+=1 N=4 | eldarJainZar | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrorsLamentAbility$$CreateBehaviour` |
| TimeFlux | L+=1 N=5 | thousTerminator | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxAbility$$CreateBehaviour` |
| ToughToKill | L+=1 N=1 | astraDreir | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ToughToKill_CritAbility` |
| TrophyTaker | L+=1 N=1 | worldExecutions | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TrophyTakerAbility$$CreateBehaviour` |
| UnwaveringSentinel | L+=1 | custoKyrus | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.UnwaveringSentinelAbility$$CreateBehaviour` |
| VisionsOfHeresy | L+=1 | bloodDeathCompany | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.VisionsOfHeresy_AttackAbility$$CreateBehaviour` |
| WireweaveNet | L+=1 N=4 | eldarRanger | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WireweaveNetAbility$$CreateBehaviour` |
| WrathfulDevotion | L+=1 N=1 | worldTerminator | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WrathfulDevotionAbility$$CreateBehaviour` |
| AdrenalGlands | S+=2 N=4 | tyranNpc1Hormagaunt, tyranSmnHormagaunt | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.AdrenalGlandsAbility` |
| HungeringSwarm | S+=2 N=4 | tyranNpc1Hormagaunt, tyranSmnHormagaunt | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.HungeringSwarmAbility` |
| ReanimationProtocols | S+=2 S?=1 N=6 | necroSmnSwarm, necroSmnWarrior | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationProtocolsAbility$$CreateBehaviour` |
| AncientFury | S+=1 | ultraSmnDreadnought | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.AncientFury_NormalAttackAbility` |
| CursedOfTheWalkingPox | S+=1 N=1 | deathPoxwalker | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedOfTheWalkingPoxAbility$$CreateBehaviour` |
| FlamesOfMutation | S+=1 S?=1 | thousSmnBlueHorror | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FlamesOfMutationAbility$$CreateBehaviour` |
| FloatingDeath | S+=1 N=1 | tyranSmnSporeMine | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FloatingDeath_InitAbility$$CreateBehaviour` |
| FragLance | S+=1 N=1 | astraSmnDeathRider | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FragLanceAbility` |
| Hypermorph | S+=1 N=1 | genesSmnAberrant | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypermorphAbility$$CreateBehaviour` |
| Ramshackle | S+=1 N=1 | orksGrotTank | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RamshackleAbility` |
| RedThirst | S+=1 N=1 | bloodSmnIntercessor | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RedThirstAbility` |
| ReinforcedHiveNode | S+=1 N=4 | tyranSmnWarrior | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ReinforcedHiveNodeAbility$$CreateBehaviour` |
| Split | S+=1 S?=1 N=1 | thousSmnPinkHorror | GAP-MENTION | **.** | - | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SplitAbility$$CreateBehaviour` |
| UnstoppableFerocity | S+=1 S?=1 N=1 | blackSmnBloodletter | GAP-ABSENT | - | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.UnstoppableFerocityAbility` |

### ZONE-GRISE confrontable -- reference en code hors registre, couverture a TRANCHER (7)

| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ | symbole natif (a confirmer) |
|---|---|---|---|---|---|---|
| AggressiveOnslaught | L+=1 | bloodIntercessor | ZONE-GRISE | **R** | playbook | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AggressiveOnslaught_SummonAbility$$CreateBehaviour` |
| FabricatorClawArray | L+=1 N=5 | necroSpyder | ZONE-GRISE | **R** | playbook | `IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$CreateBehaviour` |
| FuryOfTheAncients | L+=1 | bloodMephiston | ZONE-GRISE | **R** | playbook | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryOfTheAncientsAbility$$CreateBehaviour` |
| GalvanicField | L+=1 N=5 | admecManipulus | ZONE-GRISE | **R** | ai | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GalvanicFieldAbility$$CreateBehaviour` |
| HuntersBeyondDeath | L+=1 | spaceHound | ZONE-GRISE | **R** | playbook, runner | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HuntersBeyondDeathAbility$$CreateBehaviour` |
| TwistedScience | L+=1 N=3 | genesBiophagus | ZONE-GRISE | **R** | ai | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TwistedScienceAbility$$CreateBehaviour` |
| SaviorProtocols | S+=3 N=3 | tauSmnDroneCommandLink, tauSmnDroneShield, tauSmnDroneSniper | ZONE-GRISE | **R** | playbook, utilities | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility$$CreateBehaviour` |

### GAPS non confrontables (npc-only / lineup hors pool / summon indetermine) (87)

| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ |
|---|---|---|---|---|---|
| AllIsDust | S?=1 N=1 | - | GAP-ABSENT | - | - |
| ArchContaminator | N=1 | - | GAP-MENTION | **.** | - |
| ArmourOfShriekingSouls | L-=1 | - | GAP-ABSENT | - | - |
| BattleFocus | S?=1 N=1 | - | GAP-ABSENT | - | - |
| BossEndFightUndefeated | N=2 | - | GAP-MENTION | **.** | - |
| Bounce | N=2 | - | GAP-ABSENT | - | - |
| CallInReinforcements | S?=1 N=1 | - | GAP-ABSENT | - | - |
| CloudOfFlies | N=1 | - | GAP-MENTION | **.** | - |
| Conceal | N=1 | - | GAP-ABSENT | - | - |
| CrazedFocus | N=1 | - | GAP-ABSENT | - | - |
| DaRevolushun | N=1 | - | GAP-ABSENT | - | - |
| DeathwingKnight | S?=1 N=1 | - | GAP-ABSENT | - | - |
| DrawFire | S?=1 N=1 | - | GAP-ABSENT | - | - |
| EcogSupport | L-=1 | - | GAP-ABSENT | - | - |
| EcstaticSlaughter | L-=1 | - | GAP-ABSENT | - | - |
| ElectroShock | S?=1 N=2 | - | GAP-MENTION | **.** | - |
| EmbodiedProphecy | N=1 | - | GAP-ABSENT | - | - |
| Fealty | N=1 | - | GAP-MENTION | **.** | - |
| FiringPosition | S?=1 N=1 | - | GAP-MENTION | **.** | - |
| FullThrottle | N=1 | - | GAP-ABSENT | - | - |
| FuryFromTheDelve | L-=1 N=1 | - | GAP-ABSENT | - | - |
| GeminaeSuperia | L-=1 N=4 | - | GAP-MENTION | **.** | - |
| GrimEfficiency | L-=1 | - | GAP-MENTION | **.** | - |
| HailOfLivingAmmunition | S?=1 N=5 | - | GAP-ABSENT | - | - |
| HarlequinsPanoply | S?=1 N=1 | - | GAP-ABSENT | - | - |
| HaywireMine | L-=1 | - | GAP-MENTION | **.** | - |
| HaywireMineSteppable | S?=1 N=1 | - | GAP-ABSENT | - | - |
| HealingBalms | L-=1 | - | GAP-MENTION | **.** | - |
| HeavyBoltPistol | S?=1 N=1 | - | GAP-ABSENT | - | - |
| HostOfPlagues | N=1 | - | GAP-ABSENT | - | - |
| HunterOfSouls | S?=1 | - | GAP-ABSENT | - | - |
| HuntersInstincts | N=1 | - | GAP-MENTION | **.** | - |
| ItsGonnaBlow | N=1 | - | GAP-ABSENT | - | - |
| Lifewards | S?=1 | - | GAP-MENTION | **.** | - |
| LivingLightning | L-=1 N=5 | - | GAP-ABSENT | - | - |
| MischiefMakers | S?=1 N=1 | - | GAP-ABSENT | - | - |
| MultiTracker | N=1 | - | GAP-ABSENT | - | - |
| NoHidingFromTheWatchers | S?=1 N=1 | - | GAP-ABSENT | - | - |
| OiWatchIt | N=1 | - | GAP-ABSENT | - | - |
| OmnissiahsBlessing | S?=1 N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Armor | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Bomb | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Damage | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Healing | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Health | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_HeroSpawn_BladeChampion | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_HeroSpawn_Uthar | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_HeroSpawn_VexilusPraetor | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Hits | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_MeleeHits | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_ReactivateAbility | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Reinforcement | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_ReinforcementShield | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_Resurrect | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_SummonSpawn_bloodSmnIntercessor | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_SummonSpawn_darkaSmnHellblaster | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_SummonSpawn_darkaSmnTerminator | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_SummonSpawn_templSmnAggressor | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_SummonSpawn_ultraSmnHeavyIntercessor | N=1 | - | GAP-ABSENT | - | - |
| PowerUp_SummonSpawn_ultraSmnInceptor | N=1 | - | GAP-ABSENT | - | - |
| PreCalibratedPurgeSolution | N=1 | - | GAP-ABSENT | - | - |
| PredictiveGuidance | L-=1 | - | GAP-ABSENT | - | - |
| PrehensilePincerTail | N=1 | - | GAP-ABSENT | - | - |
| PrimarchOfTheFirstLegion | N=1 | - | GAP-ABSENT | - | - |
| PurgeResponse | S?=1 N=1 | - | GAP-ABSENT | - | - |
| Pyreblaster | S?=1 N=1 | - | GAP-ABSENT | - | - |
| RapidFire | S?=1 N=3 | - | GAP-ABSENT | - | - |
| RedRampage | L-=1 N=1 | - | GAP-MENTION | **.** | - |
| RefusalToBeOutdone | L-=1 | - | GAP-ABSENT | - | - |
| RepairEnthusiast | S?=1 N=1 | - | GAP-ABSENT | - | - |
| RunsAround | N=1 | - | GAP-ABSENT | - | - |
| RunsAway | N=1 | - | GAP-ABSENT | - | - |
| SelfRepairMechanismReworked | N=1 | - | GAP-ABSENT | - | - |
| Shrapnel | S?=1 N=2 | - | GAP-ABSENT | - | - |
| ShroudPsalm | N=1 | - | GAP-ABSENT | - | - |
| SpecialIssueCombiMelta | L-=1 N=1 | - | GAP-ABSENT | - | - |
| StormboyzStrike | N=1 | - | GAP-ABSENT | - | - |
| SynapticImperative | N=1 | - | GAP-ABSENT | - | - |
| SynapticInsight | S?=1 N=2 | - | GAP-ABSENT | - | - |
| TargetLock | N=1 | - | GAP-ABSENT | - | - |
| TheEmperorsShield | N=1 | - | GAP-ABSENT | - | - |
| TimesplinterMantle | L-=1 N=3 | - | GAP-ABSENT | - | - |
| VengeanceForTheOmnissiah | S?=1 N=1 | - | GAP-ABSENT | - | - |
| Volatile | N=1 | - | GAP-ABSENT | - | - |
| WayOfTheShortBlade | L-=1 N=4 | - | GAP-MENTION | **.** | - |
| WhipcoilBody | S?=1 N=3 | - | GAP-ABSENT | - | - |
| Wraithcannon | N=2 | - | GAP-MENTION | **.** | - |

### ZONE-GRISE non confrontable (4)

| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ |
|---|---|---|---|---|---|
| EchoesFromTheWarp | N=1 | - | ZONE-GRISE | **R** | utilities |
| Explosive | N=1 | - | ZONE-GRISE | **R** | effects |
| VoltagheistField | S?=1 N=2 | - | ZONE-GRISE | **R** | predict |
| WatchedOver | S?=1 N=1 | - | ZONE-GRISE | **R** | playbook, runner |

### PORTES (46)

| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ |
|---|---|---|---|---|---|
| DefenderOfTheGreaterGood | L+=1 S+=1 N=4 | tauShadowsun, tauSmnDroneCommandLink | PORTE | **E**=DefenderOfTheGreaterGood_ExtraDmg | effects, utilities |
| AnvilShield | L+=1 | spaceRockfist | PORTE | **T**=AnvilShieldApplyIceAbility,AnvilShieldApplyStunAbility **O**=AnvilShield_BlockChanceBelowHealthCap **E**=AnvilShield_AdditionalBlock,AnvilShield_BlockChanceBelowHealthCap **G**=AnvilShield_FrozenAttackerAdvantage | effects, runner |
| ArcaneShield | L+=1 N=4 | thousSorcerer | PORTE | **T**=ArcaneShieldAbility | runner |
| AstartesBanner | L+=1 N=3 | templAncient | PORTE | **E**=AstartesBanner_ExtraHit | effects |
| AvalancheOfMuscle | L+=1 N=4 | astraBullgryn | PORTE | **E**=AvalancheOfMuscle_ExtraDamage | effects |
| BeaconOfRage | L+=1 N=1 | worldEightbound | PORTE | **E**=BeaconOfRage_ExtraDamage,BeaconOfRage_FriendlyExtraDamage | effects |
| CondemnorStake | L+=1 N=3 | adeptCanoness | PORTE | **E**=CondemnorStake_ExtraDmg | effects |
| ControlEdict | L+=1 N=5 | admecMarshall | PORTE | **T**=ControlEdictAbility | playbook, runner |
| CyclicIonBlaster | L+=1 N=4 | tauCrisis | PORTE | **E**=CyclicIonBlaster_AdditionalHits | effects, runner |
| DaughterOfTheAbyss | L+=1 | custoAtlacoya | PORTE | **E**=DaughterOfTheAbyss_ExtraDamagePct,DaughterOfTheAbyss_FriendlyDmgReductionPct | effects |
| DecoysAndMisdirection | L+=1 N=3 | genesPrimus | PORTE | **T**=DecoysAndMisdirectionDamageEnemiesAbility,DecoysAndMisdirectionBuffFriendsAbility **E**=DecoysAndMisdirection_ExtraDamage | effects, runner, utilities |
| DestroyerHive | L+=1 N=5 | deathTyphus | PORTE | **T**=DestroyerHiveAbility | runner |
| Doom | L+=1 N=5 | eldarFarseer | PORTE | **E**=Doom_extraDmg | effects, playbook |
| ExplosiveMaladies | L+=1 N=3 | deathPutrifier | PORTE | **E**=ExplosiveMaladies_ExtraMeleeAttack,ExplosiveMaladies_ExtraRangedAttack | effects |
| FeederTendrils | L+=1 N=6 | tyranDeathleaper | PORTE | **E**=FeederTendrils_ExtraDamage | effects |
| FireOfAbsolution | L+=1 N=3 | adeptRetributor | PORTE | **B**=litteral exact sous engine/runner/ | runner |
| FleshmetalGuns | L+=1 N=6 | blackObliterator | PORTE | **T**=FleshmetalGunsRotationAbility | effects, runner |
| GuardianOrganism | L+=1 N=5 | tyranTyrantGuard | PORTE | **E**=GuardianOrganism_DamageReduction | effects, playbook |
| HeavyGravCannon | L+=1 N=3 | admecDestroyer | PORTE | **E**=HeavyGravCannon | effects |
| HypersensoryAbilities | L+=1 N=4 | genesKelermorph | PORTE | **T**=HypersensoryMoveAndSpawnDecoyAbility **O**=HypersensoryAbilities_MinimalHealth **E**=HypersensoryAbilities_MinimalHealth | effects, runner |
| InfernalPacts | L+=1 N=5 | thousInfernalMaster | PORTE | **O**=InfernalPacts_AdditionalHits **E**=InfernalPacts_AdditionalHits | effects |
| LordOfTempests | L+=1 N=1 | spaceStormcaller | PORTE | **T**=LordOfTempestsAddIceAbility **E**=LordOfTempests_ExtraDamage | effects, runner |
| LordOfTheHost | L+=1 | bloodDante | PORTE | **E**=LordOfTheHost_ExtraDamage | effects |
| MV71SniperDroneSquad | L+=1 N=4 | tauMarksman | PORTE | **E**=MV71SniperDroneSquad_InitialDmg,MV71SniperDroneSquad_ResetInitialDmg | effects, playbook, runner |
| MartialApotheosis | L+=1 N=5 | necroOverlord | PORTE | **T**=MartialApotheosisAttackAbility | playbook, runner |
| MasterAnnihilator | L+=1 N=5 | admecDominus | PORTE | **T**=MasterAnnihilatorMarkAbility **E**=MasterAnnihilator_extraHit | effects, runner |
| Narthecium | L+=1 N=3 | ultraApothecary | PORTE | **T**=NartheciumReviveAbility | runner |
| Neuroparasite | L+=1 N=6 | tyranNeurothrope | PORTE | **E**=Neuroparasite | effects |
| Nightshroud | L+=1 N=4 | astraPrimarisPsy | PORTE | **E**=Nightshroud_DmgReduction | effects |
| PathOfCommand | L+=1 N=3 | eldarAutarch | PORTE | **O**=PathOfCommand_ExtraDmg **E**=PathOfCommand_ExtraDmg | effects |
| PowerTrip | L+=1 N=3 | orksKillaKan | PORTE | **E**=PowerTrip_FullHealth,PowerTrip_IgnoreArmor | effects |
| PsychicFortress | L+=1 N=3 | ultraTigurius | PORTE | **E**=PsychicFortress_DmgReduction,PsychicFortress_ExtraBlock | effects |
| RighteousRepugnance | L+=1 N=3 | adeptMorvenn | PORTE | **B**=litteral exact sous engine/runner/ | runner |
| RitesOfBattle | L+=1 N=3 | ultraCalgar | PORTE | **E**=RitesOfBattle_ExtraDmgBasic,RitesOfBattle_ExtraDmgImperial | effects, playbook |
| SmashaEad | L+=1 N=3 | orksNob | PORTE | **E**=SmashaEad | effects |
| SpotterReworked | L+=1 N=4 | astraOrdnance | PORTE | **E**=SpotterReworked_ExtraDamage,SpotterReworked_HeavyWeapon | effects |
| SquigHound | L+=1 N=3 | orksRuntherd | PORTE | **E**=SquigHound_AdditionalHits | effects, runner |
| StandVigil | L+=1 | custoVexilusPraetor | PORTE | **E**=StandVigil_ExtraArmor | effects |
| SwornProtector | L+=1 N=5 | astraCreed | PORTE | **T**=SwornProtectorSummonKellAbility | runner |
| TaintedNarthecium | L+=1 N=3 | deathRotbone | PORTE | **T**=TaintedNartheciumReviveAbility | runner |
| TerrifyingCrescendo | L+=1 | emperNoiseMarine | PORTE | **T**=TerrifyingCrescendoOverkillAbility,TerrifyingCrescendoSuppressAbility **E**=TerrifyingCrescendo_ExtraDmg | effects, runner |
| TheBetrayer | L+=1 N=1 | worldKharn | PORTE | **T**=TheBetrayerAddEffectAbility,TheBetrayerTakeTurnAbility | runner |
| ListenUpMaggots | S+=1 | astraSmnKell | PORTE | **T**=ListenUpMaggotsAddEffectAbility | effects, runner |
| PileIn | S+=1 N=1 | orksGrot | PORTE | **B**=litteral exact sous engine/runner/ | runner |
| RadSaturation | S+=1 N=2 | admecSmnVanguard | PORTE | **T**=RadSaturationAbility | runner |
| SwornProtector_Protect | S+=1 | astraSmnKell | PORTE | **T**=SwornProtectorProtectSwitchAbility | runner |

## FILE DISPATCHABLE

Passifs **non couverts** (GAP-MENTION ou GAP-ABSENT) **ET confrontables** (>=1 porteur `L+`/`M`/`S+`) : **63 items**. Le symbole natif est resolu PAR NOM dans `data/symbols/<build>/frida/methods.tsv` -- **a confirmer en ghidra avant tout port** (`search_symbols_by_name`), ce n'est pas une preuve d'existence de la mecanique.

| # | passif | porteurs spawnables | ventilation | verdict | symbole natif (a confirmer) |
|---|---|---|---|---|---|
| 1 | **BarbedOvipositor** | tyranParasite | L+=1 N=6 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateBehaviour` |
| 2 | **Boltstorm** | templAggressor | L+=1 N=3 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BoltstormAbility` |
| 3 | **CamoCloak** | ultraEliminatorSgt | L+=1 S?=1 N=5 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Active.Loki.CamoCloakAbility$$CreateBehaviour` |
| 4 | **ChampionOfTheFeast** | templSwordBrother | L+=1 N=3 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ChampionOfTheFeastAbility$$CreateBehaviour` |
| 5 | **CosmicHorror** | genesPatriarch | L+=1 N=3 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateBehaviour` |
| 6 | **CursedPlagueBell** | deathBlightbringer | L+=1 N=3 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$CreateBehaviour` |
| 7 | **Deathwing** | darkaTerminator | L+=1 N=2 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DeathwingAbility$$CreateBehaviour` |
| 8 | **DestroyTheWitch** | templHelbrecht | L+=1 N=2 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DestroyTheWitchAbility$$CreateBehaviour` |
| 9 | **EnmityForTheUnworthy** | darkaCompanion | L+=1 N=2 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnmityForTheUnworthyAbility$$CreateBehaviour` |
| 10 | **FearedInterrogator** | darkaAsmodai | L+=1 N=2 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FearedInterrogatorAbility$$CreateBehaviour` |
| 11 | **FirstAmongTraitors** | blackAbaddon | L+=1 N=5 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Active.Loki.FirstAmongTraitorsAbility` |
| 12 | **FuelledByFury** | ultraTitus | L+=1 N=3 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility$$CreateBehaviour` |
| 13 | **GrimRetribution** | darkaHellblaster | L+=1 N=2 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GrimRetributionAbility` |
| 14 | **HatefulAssault** | blackTerminator | L+=1 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Active.Loki.HatefulAssaultAbility$$CreateBehaviour` |
| 15 | **HazeOfCorruption** | deathBlightlord | L+=1 N=4 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour` |
| 16 | **HeadClaimer** | blackHaarken | L+=1 N=5 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Active.Loki.HeadClaimerAbility$$CreateBehaviour` |
| 17 | **InescapableAccuracy** | eldarMauganRa | L+=1 N=5 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracyAbility$$CreateBehaviour` |
| 18 | **InescapableDeath** | necroDestroyer | L+=1 N=5 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Active.Loki.InescapableDeathAbility` |
| 19 | **KustomForceFieldReworked** | orksBigMek | L+=1 N=3 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.KustomForceFieldReworkedAbility$$CreateBehaviour` |
| 20 | **LegacyOfCombat** | custoBladeChampion | L+=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegacyOfCombatAbility$$CreateBehaviour` |
| 21 | **LegendaryCommander** | custoTrajann | L+=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegendaryCommanderAbility$$CreateBehaviour` |
| 22 | **LightImUp** | orksWarboss | L+=1 N=4 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility$$CreateBehaviour` |
| 23 | **LionHelm** | darkaAzrael | L+=1 N=2 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LionHelmAbility$$CreateBehaviour` |
| 24 | **MartialSuperiority** | templChampion | L+=1 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MartialSuperiorityAbility$$CreateBehaviour` |
| 25 | **MedicusMinistorum** | adeptHospitaller | L+=1 N=3 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Active.Loki.MedicusMinistorumAbility$$CreateBehaviour` |
| 26 | **ObsessiveAnnunciation** | emperKakophonist | L+=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ObsessiveAnnunciationAbility` |
| 27 | **OptimizedGait** | admecRuststalker | L+=1 N=5 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.OptimizedGaitAbility$$CreateBehaviour` |
| 28 | **Possession** | blackPossession | L+=1 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Active.Loki.PossessionAbility$$CreateBehaviour` |
| 29 | **PsychicStalk** | thousAhriman | L+=1 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PsychicStalk_ApplyFireTileAbility$$CreateBehaviour` |
| 30 | **RealityUnbound** | thousTzaangor | L+=1 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RealityUnboundAbility$$CreateBehaviour` |
| 31 | **RelentlessMarch** | necroWarden | L+=1 N=5 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility$$CreateBehaviour` |
| 32 | **SagaOfTheWarriorBorn** | spaceBlackmane | L+=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SagaOfTheWarriorBorn_InitAbility` |
| 33 | **SanguinaryPriest** | bloodSanguinary | L+=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SanguinaryPriestAbility$$CreateBehaviour` |
| 34 | **SavageKiller** | spaceWulfen | L+=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SavageKillerAbility$$CreateBehaviour` |
| 35 | **SereneUnifier** | tauAunShi | L+=1 N=3 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour` |
| 36 | **ShockAssault** | ultraInceptorSgt | L+=1 N=3 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Active.Loki.ShockAssaultAbility$$CreateBehaviour` |
| 37 | **Skullsmasher** | worldJakhal | L+=1 N=1 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Skullsmasher_TriggerStunAbility$$CreateBehaviour` |
| 38 | **SpiritualLeader** | genesMagus | L+=1 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$CreateBehaviour` |
| 39 | **StructuralAnalyser** | tauDarkstrider | L+=1 N=4 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddDamageBuffAbility$$CreateBehaviour` |
| 40 | **SummaryExecution** | astraYarrick | L+=1 N=6 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Active.Loki.SummaryExecutionAbility$$CreateBehaviour` |
| 41 | **SynapticLinchpin** | tyranWingedPrime | L+=1 N=7 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility$$CreateBehaviour` |
| 42 | **TerrorsLament** | eldarJainZar | L+=1 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrorsLamentAbility$$CreateBehaviour` |
| 43 | **TimeFlux** | thousTerminator | L+=1 N=5 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxAbility$$CreateBehaviour` |
| 44 | **ToughToKill** | astraDreir | L+=1 N=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ToughToKill_CritAbility` |
| 45 | **TrophyTaker** | worldExecutions | L+=1 N=1 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TrophyTakerAbility$$CreateBehaviour` |
| 46 | **UnwaveringSentinel** | custoKyrus | L+=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.UnwaveringSentinelAbility$$CreateBehaviour` |
| 47 | **VisionsOfHeresy** | bloodDeathCompany | L+=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.VisionsOfHeresy_AttackAbility$$CreateBehaviour` |
| 48 | **WireweaveNet** | eldarRanger | L+=1 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WireweaveNetAbility$$CreateBehaviour` |
| 49 | **WrathfulDevotion** | worldTerminator | L+=1 N=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WrathfulDevotionAbility$$CreateBehaviour` |
| 50 | **AdrenalGlands** | tyranNpc1Hormagaunt, tyranSmnHormagaunt | S+=2 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Active.Loki.AdrenalGlandsAbility` |
| 51 | **HungeringSwarm** | tyranNpc1Hormagaunt, tyranSmnHormagaunt | S+=2 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Active.Loki.HungeringSwarmAbility` |
| 52 | **ReanimationProtocols** | necroSmnSwarm, necroSmnWarrior | S+=2 S?=1 N=6 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationProtocolsAbility$$CreateBehaviour` |
| 53 | **AncientFury** | ultraSmnDreadnought | S+=1 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Active.Loki.AncientFury_NormalAttackAbility` |
| 54 | **CursedOfTheWalkingPox** | deathPoxwalker | S+=1 N=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedOfTheWalkingPoxAbility$$CreateBehaviour` |
| 55 | **FlamesOfMutation** | thousSmnBlueHorror | S+=1 S?=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FlamesOfMutationAbility$$CreateBehaviour` |
| 56 | **FloatingDeath** | tyranSmnSporeMine | S+=1 N=1 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FloatingDeath_InitAbility$$CreateBehaviour` |
| 57 | **FragLance** | astraSmnDeathRider | S+=1 N=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FragLanceAbility` |
| 58 | **Hypermorph** | genesSmnAberrant | S+=1 N=1 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypermorphAbility$$CreateBehaviour` |
| 59 | **Ramshackle** | orksGrotTank | S+=1 N=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RamshackleAbility` |
| 60 | **RedThirst** | bloodSmnIntercessor | S+=1 N=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RedThirstAbility` |
| 61 | **ReinforcedHiveNode** | tyranSmnWarrior | S+=1 N=4 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ReinforcedHiveNodeAbility$$CreateBehaviour` |
| 62 | **Split** | thousSmnPinkHorror | S+=1 S?=1 N=1 | GAP-MENTION | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SplitAbility$$CreateBehaviour` |
| 63 | **UnstoppableFerocity** | blackSmnBloodletter | S+=1 S?=1 N=1 | GAP-ABSENT | `IdunBattleLogic.Entities.Abilities.Active.Loki.UnstoppableFerocityAbility` |

> Rappel de dispatch : un passif **`S+`** se confronte en spawnant son **summoner** (qui, lui, est dans le pool) -- ne jamais le classer « non confrontable ». Les `S?` sont a re-qualifier a la main (leur spawn n'est pas exprime dans `constants`).

## Ce qui n'est PAS couvert par cet audit

- **Fidelite** : un passif PORTE peut l'etre FAUSSEMENT (cas fondateur `HeavyGravCannon`, canal **E**, divergence live). Cet audit mesure la PRESENCE d'un cablage, jamais sa justesse.
- **[E]/[G] reposent sur une convention de NOMMAGE** (meme convention que `audit_kit_coverage._has_effect_named_after`), pas sur un lien lu du natif : verifie sur ce run, **0/207** des `constants` d'un passif nomment un `EffectType`. Le gameconfig n'exprime AUCUN lien passif->effet.
- **Completude d'un passif multi-volets** : un passif dont 1 volet sur 3 est porte compte comme PORTE (ex. `AnvilShield`). Le decoupage par volet est un travail de recon.
- **Face DECISION** : hors perimetre -- un passif ne se caste pas, il n'a pas de playbook. Seule la face COMBAT est auditee.
- **Reachability `S?`** : borne basse assumee -- **36** des 65 summons du parc n'ont AUCUNE arete derivable du gameconfig (leur spawn n'est pas exprime dans `constants`) et sont donc comptes non-confrontables par defaut.
- **Traits** : mecanique voisine mais registre distinct -> `docs/rl/unit-trait-coverage.md`.

### Relation aux audits existants

- `docs/rl/combat-ability-coverage.md` (par-ability ACTIVE) : disjoint de celui-ci -- l'intersection des noms actives/passifs est vide.
- `docs/rl/kit-coverage.md` (par KIT) mesure deja des passifs, mais **des seules unites `lineup`** et avec un booleen a 3 signaux (`ABILITY_TRIGGERS` / `ABILITY_INIT_OWNER_EFFECTS` / effet homonyme). Cet audit-ci couvre **tout le parc** (lineup + npc + summons), rend un verdict PAR PASSIF avec son CANAL, ventile les porteurs par confrontabilite, et ajoute 3 signaux (`ABILITY_OWNER_EFFECTS`, `EFFECT_TRIGGERS`, bespoke `runner/`) -- son jeu de canaux est un SUR-ENSEMBLE. Les deux reposent sur la meme convention de nommage pour le canal effet, donc ils ne peuvent pas se contredire sur les signaux partages ; ils se completent (vue KIT = « que reste-t-il a faire sur cette unite », vue PASSIF = « ce mecanisme est-il branche »).
