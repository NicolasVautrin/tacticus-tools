# Registre des unites `npc` — kit complet et etat des DEUX FACES

> Genere par `scripts/python/audit_npc_registry.py`. **Ne jamais fusionner un conflit sur
> ce fichier : le REGENERER.** A rejouer au changement de build ou apres tout port.
>
> Pendant NPC de `kit-coverage.md`, qui ne balaie que les 127 `lineup`. Tous les predicats
> de couverture viennent des FOYERS PARTAGES (`ABILITY_CLASSES`, `decision_face_voies`,
> `_passive_covered`, les registres trait->X) — aucune liste blanche locale.

## Les deux faces, et pourquoi elles se comptent SEPAREMENT

`[CD]` = combat et decision portees · `[C-]` = executee fidelement mais **choisie avec un
scoring qui n'est pas celui du natif** · `[-D]` = scoree mais **NO-OP silencieux** a
l'execution · `[--]` = ni l'un ni l'autre. Le suffixe `!` marque une **voie inversee**
(le nom n'est pas un `ActiveAbilityType` — l'ability vit dans un autre enum).

Une divergence `[C-]` est INVISIBLE en replay : l'execution est fidele, seule la POLITIQUE
differe. C'est la doctrine « DECIDER != EXECUTER ».

## Bilan

- Unites `npc` : **491** ; kits sans manque : **5** ; kits avec du travail : **486**
- Actives distinctes : **147** — `[--]` **9** · `[-D]` **1** · `[C-]` **14** · `[CD]` **123**
- Passifs distincts : **177** — portes **107**, non portes **70**
- Traits de kit distincts (AUCUN ecarte — le seuil de frequence a disparu avec #1015) :
  **58** — couverts **28**, non couverts **30**
- **Voies inversees** (nom absent d'`ActiveAbilityType`) : **1** — `Maugetar`

## Ce que ce registre NE VOIT PAS

Quatre voies d'attribution ne sont derivables d'AUCUNE source offline. Un kit affiche sans
manque l'est au sens des voies du gameconfig, **pas au sens absolu** — c'est exactement le
faux zero de #323, et le dire est ce qui empeche de le relire comme une preuve.

- **`trait`** — un TRAIT accorde l'ability (mapping NATIF, hors gameconfig) -- ex. `Mechanic` -> ActiveAbilityType 28 Repair, `LivingMetal` -> TriggeredAbilityType 1010. Interroger `find --trait <T>`.
- **`liveevent`** — enhancement de live-event (`Enhancement*`) : accorde hors bataille reguliere, a aucune unite du catalogue.
- **`summon`** — un summon porte SON kit propre ; il n'apparait pas sur son summoner. Chercher le summon, puis remonter au summoner (qui, lui, doit etre spawnable).
- **`tile`** — power-up de TERRAIN (`PowerUp_*`) : pose par le BOARD, pas par une unite.

> ⚠ Et le kit gameconfig **n'est pas** l'entite en bataille : le natif monte
> `BC.Units[].PassiveAbilities`, pas le kit. Une greffe `replace=True` VIDE
> `PassiveAbilities`. La verite de ce qu'une unite porte en bataille est le canal
> `unitAbilityStates`, jamais ce document.

## Travail restant, par ITEM (l'unite de travail reelle)

Une ability portee par six npc se porte **une** fois : c'est l'item qui prioritise, pas
l'unite. La colonne `porteurs` dit l'exposition.

| type | item | porteurs | exemples |
|---|---|---:|---|
| trait | Hero | 323 | adeptBossCanoness, adeptBossCanonessLHE, adeptBossCelestine |
| trait | Mechanical | 98 | adeptBossMorvenn, adeptBossMorvennLHE, adeptNpcMorvenn |
| trait | Flying | 94 | adeptBossCelestine, adeptBossCelestineCE, adeptBossCelestineLHE |
| trait | Resilient | 42 | admecNpc3Electropriest, admecNpc3ElectropriestSurv, astraBossYarrick |
| trait | Infiltrate | 36 | admecBossRuststalker, admecBossRuststalkerCE, admecBossRuststalkerLEG |
| trait | Overwatch | 35 | admecBossDestroyer, admecBossDestroyerCE, admecBossDestroyerLHE |
| trait | BattleFatigue | 28 | astraNpc1Guardsman, astraNpc2Lascannon, astraNpc3Voxcaster |
| trait | Object | 28 | LootObj_AmmoBox, LootObj_Crate_Cha, LootObj_Crate_Imp |
| trait | Immune | 27 | adeptBossCelestineCE, admecBossBelisarius, darkaBossLion |
| trait | Synapse | 27 | genesBossPatriarch, genesBossPatriarchLHE, genesNpcPatriarch |
| trait | Steppable | 25 | LootObj_Blackstone, LootObj_CoinCrate, LootObj_XPBook |
| trait | TeleportStrike | 22 | adeptNpc2Zephyrim, blackBossTerminator, blackBossTerminatorLEG |
| trait | Mechanic | 21 | admecBossDominus, admecBossDominusCE, admecBossDominusLEG |
| trait | GetStuckIn | 20 | orksBossBigMek, orksBossBigMekLEG, orksBossBigMekLHE |
| trait | Invincible | 20 | powupArmor, powupBomb, powupDamage |
| trait | Unstoppable | 19 | admecBossRuststalker, admecBossRuststalkerCE, admecBossRuststalkerLEG |
| trait | InstinctiveBehaviour | 18 | tyranNpc1Hormagaunt, tyranNpc1HormagauntGorgon, tyranNpc1HormagauntKronos |
| trait | CloseCombatWeakness | 16 | tauBossCrisis, tauBossCrisisInc, tauBossCrisisLHE |
| trait | MkXGravis | 14 | templBossAggressor, templBossAggressorCamp, templBossAggressorLEG |
| trait | Healer | 12 | adeptBossHospitaller, adeptBossHospitallerLHE, adeptNpcHospitaller |
| trait | MachineOfWar | 11 | adeptNpcMoWExorcist, astraNpcMowOrdnanceBattery, blackNpcMowForgefiend |
| trait | Boss | 6 | adeptBossCelestineCE, admecBossBelisarius, darkaBossLion |
| passif | AdrenalGlands | 5 | tyranNpc1Hormagaunt, tyranNpc1HormagauntGorgon, tyranNpc1HormagauntKronos |
| passif | HailOfLivingAmmunition | 5 | tyranNpc3Termagant, tyranNpc3TermagantGorgon, tyranNpc3TermagantKronos |
| passif | HungeringSwarm | 5 | tyranNpc1Hormagaunt, tyranNpc1HormagauntGorgon, tyranNpc1HormagauntKronos |
| trait | Vehicle | 5 | admecBossDestroyer, admecBossDestroyerCE, admecBossDestroyerLHE |
| trait | TwoManTeam | 4 | astraNpc2Lascannon, astraNpc4Mortar, astraNpc4MortarSurv |
| passif | RapidFire | 3 | ultraNpc3Intercessor, ultraNpc4HeavyIntercessor, ultraNpc4HeavyIntercessorSurv |
| passif | SaviorProtocols | 3 | tauNpc2DroneSniper, tauNpc3DroneShield, tauNpc4DroneCommandLink |
| trait | Emplacement | 3 | astraNpc2Lascannon, astraNpc4Mortar, astraNpc4MortarSurv |
| trait | Impervious | 3 | LootObj_Strongbox_Cha, LootObj_Strongbox_Imp, LootObj_Strongbox_Xen |
| passif | BossEndFightUndefeated | 2 | darkaBossLion, deathBossMortarion |
| passif | Bounce | 2 | orksNpc7Squig, orksNpc7SquigSurv |
| passif | Shrapnel | 2 | astraNpc4Mortar, astraNpc4MortarSurv |
| passif | SynapticInsight | 2 | tyranNpc5Barbgaunt, tyranNpc5BarbgauntSurv |
| trait | NonAttacking | 2 | orksNpc4AmmoGrot, orksNpc5LootGrotTeam |
| trait | PermaDeath | 2 | darkaNpc4Watcher, tyranNpc6SporeMine |
| active | CallRipperSwarms | 1 | tyranBossHiveTyrantLeviathan |
| active | DevoutPush | 1 | templNpc1Initiate |
| active | InstrumentsOfVengeance | 1 | darkaBossLion |
| active | InvocationOfMachineVengeance | 1 | admecBossBelisarius |
| active | Maugetar | 1 | eldarBossMauganRaUltra |
| active | NovaCharge | 1 | tauBossRiptide |
| active | PrecisionShot | 1 | necroNpc3Deathmark |
| active | Reveal | 1 | eldarNpc2Warlock |
| active | SolarAtomizer | 1 | admecBossBelisarius |
| active | TheLantern | 1 | deathBossMortarion |
| passif | AllIsDust | 1 | thousNpc3RubricMarine |
| passif | ArchContaminator | 1 | deathBossMortarion |
| passif | BattleFocus | 1 | eldarNpc1Guardian |
| passif | CallInReinforcements | 1 | astraNpc3Voxcaster |
| passif | CloudOfFlies | 1 | deathNpc2PlagueMarine |
| passif | Conceal | 1 | eldarNpc2Warlock |
| passif | CrazedFocus | 1 | blackNpc3TraitorGuardsman |
| passif | CursedOfTheWalkingPox | 1 | deathNpc1Poxwalker |
| passif | DaRevolushun | 1 | orksRedGobbo |
| passif | DeathwingKnight | 1 | darkaNpc3Terminator |
| passif | DrawFire | 1 | blackNpc2Terminator |
| passif | EmbodiedProphecy | 1 | adeptNpc2Zephyrim |
| passif | Explosive | 1 | LootObj_ExplOilDrum |
| passif | FiringPosition | 1 | blackNpc4Havoc |
| passif | FragLance | 1 | astraNpc5DeathRider |
| passif | HarlequinsPanoply | 1 | eldarNpc3Harlequin |
| passif | HostOfPlagues | 1 | deathBossMortarion |
| passif | HuntersInstincts | 1 | tauNpc6Carnivore |
| passif | Hypermorph | 1 | genesNpc1Aberrant |
| passif | ItsGonnaBlow | 1 | orksNpc4AmmoGrot |
| passif | MischiefMakers | 1 | deathNpc3Nurglings |
| passif | MultiTracker | 1 | tauBossRiptide |
| passif | NoHidingFromTheWatchers | 1 | darkaNpc4Watcher |
| passif | OiWatchIt | 1 | orksNpc5LootGrotTeam |
| passif | OmnissiahsBlessing | 1 | admecNpc2Techpriest |
| passif | PileIn | 1 | orksNpc1Grot |
| passif | PowerUp_Armor | 1 | powupArmor |
| passif | PowerUp_Bomb | 1 | powupBomb |
| passif | PowerUp_Damage | 1 | powupDamage |
| passif | PowerUp_Healing | 1 | powupHealing |
| passif | PowerUp_Health | 1 | powupHealth |
| passif | PowerUp_HeroSpawn_BladeChampion | 1 | powupHeroSpawn_BladeChampion |
| passif | PowerUp_HeroSpawn_Uthar | 1 | powupHeroSpawn_Uthar |
| passif | PowerUp_HeroSpawn_VexilusPraetor | 1 | powupHeroSpawn_VexilusPraeto |
| passif | PowerUp_Hits | 1 | powupHits |
| passif | PowerUp_MeleeHits | 1 | powupMeleeHits |
| passif | PowerUp_ReactivateAbility | 1 | powupReactivateAbility |
| passif | PowerUp_Reinforcement | 1 | powupReinforcement |
| passif | PowerUp_ReinforcementShield | 1 | powupReinforcementShield |
| passif | PowerUp_Resurrect | 1 | powupResurrect |
| passif | PowerUp_SummonSpawn_bloodSmnIntercessor | 1 | powupSummonSpawn_bloodSmnIntercessor |
| passif | PowerUp_SummonSpawn_darkaSmnHellblaster | 1 | powupSummonSpawn_darkaSmnHellblaster |
| passif | PowerUp_SummonSpawn_darkaSmnTerminator | 1 | powupSummonSpawn_darkaSmnTerminator |
| passif | PowerUp_SummonSpawn_templSmnAggressor | 1 | powupSummonSpawn_templSmnAggressor |
| passif | PowerUp_SummonSpawn_ultraSmnHeavyIntercessor | 1 | powupSummonSpawn_ultraSmnHeavyIntercessor |
| passif | PowerUp_SummonSpawn_ultraSmnInceptor | 1 | powupSummonSpawn_ultraSmnInceptor |
| passif | PreCalibratedPurgeSolution | 1 | admecBossBelisarius |
| passif | PrehensilePincerTail | 1 | tyranBossHiveTyrantLeviathan |
| passif | Pyreblaster | 1 | templNpc3InitiatePyreblaster |
| passif | RedThirst | 1 | bloodNpc1Intercessor |
| passif | RepairEnthusiast | 1 | votanNpc1Ecog |
| passif | RunsAround | 1 | orksNpc4AmmoGrot |
| passif | RunsAway | 1 | orksNpc5LootGrotTeam |
| passif | SelfRepairMechanismReworked | 1 | admecBossBelisarius |
| passif | Split | 1 | thousNpc1PinkHorror |
| passif | SynapticImperative | 1 | tyranBossHiveTyrantLeviathan |
| passif | TargetLock | 1 | tauBossRiptide |
| passif | TheEmperorsShield | 1 | darkaBossLion |
| passif | VengeanceForTheOmnissiah | 1 | admecNpc2Techpriest |
| passif | Volatile | 1 | LootObj_AmmoBox |
| passif | WatchedOver | 1 | darkaNpc4Watcher |
| trait | BeastSnagga | 1 | tauNpcFarsight |
| trait | Decoy | 1 | genesDecoy |

## Faces DECISION ouvertes sur des actives EXECUTEES (14)

Ces abilities s'executent fidelement mais sont CHOISIES avec un scoring qui n'est pas celui
du natif. Aucun compteur de manque ne les voit — elles ne sont pas des items absents, ce
sont des **faces** absentes d'items presents.

`ArcScourge`, `BasiliskBarrage`, `Burrowers`, `Catalyst`, `EntropyCannons`, `ExplosivePresents`, `KissOfDeath`, `MacroPlasmaIncinerator`, `SlashingDive`, `SquigLaunchas`, `TunnelingHorror`, `ValkyrieStrike`, `WallOfMirrors`, `WarConstruct`

## Inventaire complet, par faction

### ? — 51 unites, 51 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| powupArmor | 4 | - | PowerUp_Armor | Steppable, Invincible, Immune | - |
| powupBomb | 4 | - | PowerUp_Bomb | Steppable, Invincible, Immune | - |
| powupDamage | 4 | - | PowerUp_Damage | Steppable, Invincible, Immune | - |
| powupHealing | 4 | - | PowerUp_Healing | Steppable, Invincible, Immune | - |
| powupHealth | 4 | - | PowerUp_Health | Steppable, Invincible, Immune | - |
| powupHeroSpawn_BladeChampion | 4 | - | PowerUp_HeroSpawn_BladeChampion | Steppable, Invincible, Immune | - |
| powupHeroSpawn_Uthar | 4 | - | PowerUp_HeroSpawn_Uthar | Steppable, Invincible, Immune | - |
| powupHeroSpawn_VexilusPraeto | 4 | - | PowerUp_HeroSpawn_VexilusPraetor | Steppable, Invincible, Immune | - |
| powupHits | 4 | - | PowerUp_Hits | Steppable, Invincible, Immune | - |
| powupMeleeHits | 4 | - | PowerUp_MeleeHits | Steppable, Invincible, Immune | - |
| powupReactivateAbility | 4 | - | PowerUp_ReactivateAbility | Steppable, Invincible, Immune | - |
| powupReinforcement | 4 | - | PowerUp_Reinforcement | Steppable, Invincible, Immune | - |
| powupReinforcementShield | 4 | - | PowerUp_ReinforcementShield | Steppable, Invincible, Immune | - |
| powupResurrect | 4 | - | PowerUp_Resurrect | Steppable, Invincible, Immune | - |
| powupSummonSpawn_bloodSmnIntercessor | 4 | - | PowerUp_SummonSpawn_bloodSmnIntercessor | Steppable, Invincible, Immune | - |
| powupSummonSpawn_darkaSmnHellblaster | 4 | - | PowerUp_SummonSpawn_darkaSmnHellblaster | Steppable, Invincible, Immune | - |
| powupSummonSpawn_darkaSmnTerminator | 4 | - | PowerUp_SummonSpawn_darkaSmnTerminator | Steppable, Invincible, Immune | - |
| powupSummonSpawn_templSmnAggressor | 4 | - | PowerUp_SummonSpawn_templSmnAggressor | Steppable, Invincible, Immune | - |
| powupSummonSpawn_ultraSmnHeavyIntercessor | 4 | - | PowerUp_SummonSpawn_ultraSmnHeavyIntercessor | Steppable, Invincible, Immune | - |
| powupSummonSpawn_ultraSmnInceptor | 4 | - | PowerUp_SummonSpawn_ultraSmnInceptor | Steppable, Invincible, Immune | - |
| LootObj_AmmoBox | 2 | - | Volatile | Object | - |
| LootObj_ExplOilDrum | 2 | - | Explosive | Object | - |
| LootObj_Strongbox_Cha | 2 | - | - | Object, Impervious | - |
| LootObj_Strongbox_Imp | 2 | - | - | Object, Impervious | - |
| LootObj_Strongbox_Xen | 2 | - | - | Object, Impervious | - |
| LootObj_Blackstone | 1 | - | - | Steppable | - |
| LootObj_CoinCrate | 1 | - | - | Steppable | - |
| LootObj_Crate_Cha | 1 | - | - | Object | - |
| LootObj_Crate_Imp | 1 | - | - | Object | - |
| LootObj_Crate_Xen | 1 | - | - | Object | - |
| LootObj_FancyBox | 1 | - | - | Object | - |
| LootObj_OilDrum | 1 | - | - | Object | - |
| LootObj_Pod_Common_Cha | 1 | - | - | Object | - |
| LootObj_Pod_Common_Imp | 1 | - | - | Object | - |
| LootObj_Pod_Common_Xen | 1 | - | - | Object | - |
| LootObj_Pod_Epic_Cha | 1 | - | - | Object | - |
| LootObj_Pod_Epic_Imp | 1 | - | - | Object | - |
| LootObj_Pod_Epic_Xen | 1 | - | - | Object | - |
| LootObj_Pod_Legendary_Cha | 1 | - | - | Object | - |
| LootObj_Pod_Legendary_Imp | 1 | - | - | Object | - |
| LootObj_Pod_Legendary_Xen | 1 | - | - | Object | - |
| LootObj_Pod_Mythic_Cha | 1 | - | - | Object | - |
| LootObj_Pod_Mythic_Imp | 1 | - | - | Object | - |
| LootObj_Pod_Mythic_Xen | 1 | - | - | Object | - |
| LootObj_Pod_Rare_Cha | 1 | - | - | Object | - |
| LootObj_Pod_Rare_Imp | 1 | - | - | Object | - |
| LootObj_Pod_Rare_Xen | 1 | - | - | Object | - |
| LootObj_Pod_Uncommon_Cha | 1 | - | - | Object | - |
| LootObj_Pod_Uncommon_Imp | 1 | - | - | Object | - |
| LootObj_Pod_Uncommon_Xen | 1 | - | - | Object | - |
| LootObj_XPBook | 1 | - | - | Steppable | - |

### AdeptusAstartes — 2 unites, 2 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| astarCyrus_LHE | 2 | StrikeFromTheShadows(1225)[CD] | - | Hero, Infiltrate | - |
| astarNpc1HaywireMine | 1 | - | - | Steppable | - |

### AdeptusMechanicus — 29 unites, 29 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| admecBossBelisarius | 7 | InvocationOfMachineVengeance(1172)[--]<br>ArcScourge(1173)[C-]<br>SolarAtomizer(1174)[--] | SelfRepairMechanismReworked, PreCalibratedPurgeSolution | Boss, Immune, Mechanical | - |
| admecBossDestroyer | 4 | SentinelDirectives(1139)[CD] | - | Hero, Mechanical, Overwatch, Vehicle | relic:KardiocoreGalvanus |
| admecBossDestroyerCE | 4 | SentinelDirectives(1139)[CD] | - | Hero, Mechanical, Overwatch, Vehicle | relic:KardiocoreGalvanus |
| admecBossDestroyerLHE | 4 | SentinelDirectives(1139)[CD] | - | Hero, Mechanical, Overwatch, Vehicle | relic:KardiocoreGalvanus |
| admecBossManipulus | 4 | DefendTheDivineWork(1117)[CD] | - | Hero, Mechanical, Mechanic, Flying | - |
| admecBossManipulusCE | 4 | DefendTheDivineWork(1117)[CD] | - | Hero, Mechanical, Mechanic, Flying | - |
| admecBossManipulusLEG | 4 | DefendTheDivineWork(1117)[CD] | - | Hero, Mechanical, Mechanic, Flying | - |
| admecBossManipulusLHE | 4 | DefendTheDivineWork(1117)[CD] | - | Hero, Mechanical, Mechanic, Flying | - |
| admecBossManipulusSurv | 4 | DefendTheDivineWork(1117)[CD] | - | Hero, Mechanical, Mechanic, Flying | - |
| admecBossRuststalker | 4 | CordClaw(1122)[CD] | - | Hero, Mechanical, Infiltrate, Unstoppable | relic:KardiocoreGalvanus |
| admecBossRuststalkerCE | 4 | CordClaw(1122)[CD] | - | Hero, Mechanical, Infiltrate, Unstoppable | relic:KardiocoreGalvanus |
| admecBossRuststalkerLEG | 4 | CordClaw(1122)[CD] | - | Hero, Mechanical, Infiltrate, Unstoppable | relic:KardiocoreGalvanus |
| admecBossRuststalkerLHE | 4 | CordClaw(1122)[CD] | - | Hero, Mechanical, Infiltrate, Unstoppable | relic:KardiocoreGalvanus |
| admecBossRuststalkerSurv | 4 | CordClaw(1122)[CD] | - | Hero, Mechanical, Infiltrate, Unstoppable | relic:KardiocoreGalvanus |
| admecNpc2Techpriest | 4 | - | VengeanceForTheOmnissiah, OmnissiahsBlessing | Mechanical, Mechanic | - |
| admecBossDominus | 3 | RadBombardment(1116)[CD] | - | Hero, Mechanical, Mechanic | - |
| admecBossDominusCE | 3 | RadBombardment(1116)[CD] | - | Hero, Mechanical, Mechanic | - |
| admecBossDominusLEG | 3 | RadBombardment(1116)[CD] | - | Hero, Mechanical, Mechanic | - |
| admecBossDominusLHE | 3 | RadBombardment(1116)[CD] | - | Hero, Mechanical, Mechanic | - |
| admecBossDominusSurv | 3 | RadBombardment(1116)[CD] | - | Hero, Mechanical, Mechanic | - |
| admecBossMarshall | 2 | DoctrinaImperatives(1118)[CD] | - | Hero, Mechanical | relic:KardiocoreGalvanus |
| admecBossMarshallCE | 2 | DoctrinaImperatives(1118)[CD] | - | Hero, Mechanical | relic:KardiocoreGalvanus |
| admecBossMarshallLEG | 2 | DoctrinaImperatives(1118)[CD] | - | Hero, Mechanical | relic:KardiocoreGalvanus |
| admecBossMarshallLHE | 2 | DoctrinaImperatives(1118)[CD] | - | Hero, Mechanical | relic:KardiocoreGalvanus |
| admecBossMarshallSurv | 2 | DoctrinaImperatives(1118)[CD] | - | Hero, Mechanical | relic:KardiocoreGalvanus |
| admecNpc3Electropriest | 2 | - | - | Mechanical, Resilient | - |
| admecNpc3ElectropriestSurv | 2 | - | - | Mechanical, Resilient | - |
| admecNpc1Vanguard | 1 | - | - | Mechanical | - |
| admecNpc1VanguardSurv | 1 | - | - | Mechanical | - |

### Aeldari — 26 unites, 26 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| eldarBossAutarch | 3 | Loki_SwoopingHawk(1064)[CD] | - | Hero, Flying, TeleportStrike | relic:PhoenixGem |
| eldarBossAutarchCamp | 3 | Loki_SwoopingHawk(1064)[CD] | - | Hero, Flying, TeleportStrike | relic:PhoenixGem |
| eldarBossAutarchLHE | 3 | Loki_SwoopingHawk(1064)[CD] | - | Hero, Flying, TeleportStrike | relic:PhoenixGem |
| eldarBossMauganRaUltra | 3 | Maugetar[--]! | - | Hero, Overwatch | relic:Maugetar |
| eldarNpc3Harlequin | 3 | KissOfDeath(1108)[C-] | HarlequinsPanoply | Infiltrate, Unstoppable | - |
| eldarBossJainZar | 2 | SilentDeath(1068)[CD] | - | Hero, Infiltrate | - |
| eldarBossJainZarCamp | 2 | SilentDeath(1068)[CD] | - | Hero, Infiltrate | - |
| eldarBossJainZarLEG | 2 | SilentDeath(1068)[CD] | - | Hero, Infiltrate | - |
| eldarBossJainZarLHE | 2 | SilentDeath(1068)[CD] | - | Hero, Infiltrate | - |
| eldarBossMauganRa | 2 | HarvesterOfSouls(1067)[CD] | - | Hero, Overwatch | relic:Maugetar |
| eldarBossMauganRaCamp | 2 | HarvesterOfSouls(1067)[CD] | - | Hero, Overwatch | relic:Maugetar |
| eldarBossMauganRaLEG | 2 | HarvesterOfSouls(1067)[CD] | - | Hero, Overwatch | relic:Maugetar |
| eldarBossMauganRaLHE | 2 | HarvesterOfSouls(1067)[CD] | - | Hero, Overwatch | relic:Maugetar |
| eldarBossRanger | 2 | FireAndReposition(1063)[CD] | - | Hero, Overwatch | - |
| eldarBossRangerCamp | 2 | FireAndReposition(1063)[CD] | - | Hero, Overwatch | - |
| eldarBossRangerLHE | 2 | FireAndReposition(1063)[CD] | - | Hero, Overwatch | - |
| eldarBossRangerSurv | 2 | FireAndReposition(1063)[CD] | - | Hero, Overwatch | - |
| eldarNpc1Guardian | 2 | PlasmaGrenade(1098)[CD] | BattleFocus | BattleFatigue | - |
| eldarNpc2Warlock | 2 | Reveal(1107)[--] | Conceal | - | - |
| eldarBossFarseer | 1 | Executioner(1066)[CD] | - | Hero | - |
| eldarBossFarseerCamp | 1 | Executioner(1066)[CD] | - | Hero | - |
| eldarBossFarseerLEG | 1 | Executioner(1066)[CD] | - | Hero | - |
| eldarBossFarseerLHE | 1 | Executioner(1066)[CD] | - | Hero | - |
| eldarBossFarseerSurv | 1 | Executioner(1066)[CD] | - | Hero | - |
| eldarNpc4Wraithguard | 1 | WarConstruct(1133)[C-] | - | Overwatch | - |
| eldarNpc4WraithguardSurv | 1 | WarConstruct(1133)[C-] | - | Overwatch | - |

### AstraMilitarum — 31 unites, 31 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| astraNpc2Lascannon | 4 | - | - | Emplacement, BattleFatigue, TwoManTeam, Overwatch | - |
| astraNpc4Mortar | 4 | - | Shrapnel | Emplacement, BattleFatigue, TwoManTeam | - |
| astraNpc4MortarSurv | 4 | - | Shrapnel | Emplacement, BattleFatigue, TwoManTeam | - |
| astraNpcDreir | 3 | LeadingTheCharge(1204)[CD] | - | Hero, Resilient, Unstoppable | relic:SabreOfSacrifice |
| astraBossYarrick | 2 | SendInTheNextWave(1016)[CD] | - | Hero, Resilient | - |
| astraBossYarrickLEG | 2 | SendInTheNextWave(1016)[CD] | - | Hero, Resilient | - |
| astraBossYarrickLHE | 2 | SendInTheNextWave(1016)[CD] | - | Hero, Resilient | - |
| astraBossYarrickSurv | 2 | SendInTheNextWave(1016)[CD] | - | Hero, Resilient | - |
| astraNpc3Voxcaster | 2 | ValkyrieStrike(1018)[C-] | CallInReinforcements | BattleFatigue | - |
| astraNpc5DeathRider | 2 | - | FragLance | Unstoppable | - |
| astraNpcYarrick | 2 | SendInTheNextWave(1016)[CD] | - | Hero, Resilient | - |
| astraYarrick_LHE | 2 | SendInTheNextWave(1016)[CD] | - | Hero, Resilient | - |
| astraBossBullgryn | 1 | FragBomb(1017)[CD] | - | Hero | relic:RelicOfLostCadia |
| astraBossBullgrynLEG | 1 | FragBomb(1017)[CD] | - | Hero | relic:RelicOfLostCadia |
| astraBossBullgrynLHE | 1 | FragBomb(1017)[CD] | - | Hero | relic:RelicOfLostCadia |
| astraBossCreed | 1 | SupremeCommander(1028)[CD] | - | Hero | - |
| astraBossCreedLEG | 1 | SupremeCommander(1028)[CD] | - | Hero | - |
| astraBossCreedLHE | 1 | SupremeCommander(1028)[CD] | - | Hero | - |
| astraBossCreedSurv | 1 | SupremeCommander(1028)[CD] | - | Hero | - |
| astraBossOrdnance | 1 | BasiliskBarrage(1026)[C-] | - | Hero | relic:RelicOfLostCadia |
| astraBossOrdnanceLEG | 1 | BasiliskBarrage(1026)[C-] | - | Hero | relic:RelicOfLostCadia |
| astraBossOrdnanceLHE | 1 | BasiliskBarrage(1026)[C-] | - | Hero | relic:RelicOfLostCadia |
| astraBossPrimarisPsy | 1 | PsychicMaelstrom(1027)[CD] | - | Hero | relic:RelicOfLostCadia |
| astraBossPrimarisPsyLHE | 1 | PsychicMaelstrom(1027)[CD] | - | Hero | relic:RelicOfLostCadia |
| astraBossPrimarisPsySurv | 1 | PsychicMaelstrom(1027)[CD] | - | Hero | relic:RelicOfLostCadia |
| astraNpc1Guardsman | 1 | - | - | BattleFatigue | - |
| astraNpcBullgryn | 1 | FragBomb(1017)[CD] | - | Hero | relic:RelicOfLostCadia |
| astraNpcCreed | 1 | SupremeCommander(1028)[CD] | - | Hero | - |
| astraNpcMowOrdnanceBattery | 1 | MalleusRocketLauncher(1142)[CD]<br>ForwardSpotter(1143)[CD] | - | MachineOfWar | mythic:OnMyPosition |
| astraNpcOrdnance | 1 | BasiliskBarrage(1026)[C-] | - | Hero | relic:RelicOfLostCadia |
| astraNpcPrimarisPsy | 1 | PsychicMaelstrom(1027)[CD] | - | Hero | relic:RelicOfLostCadia |

### BlackLegion — 29 unites, 28 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| blackBossAbaddon | 2 | Drachnyen(1029)[CD] | - | Hero, Resilient | relic:TalonOfHorus |
| blackBossAbaddonCamp | 2 | Drachnyen(1029)[CD] | - | Hero, Resilient | relic:TalonOfHorus |
| blackBossAbaddonLEG | 2 | Drachnyen(1029)[CD] | - | Hero, Resilient | relic:TalonOfHorus |
| blackBossAbaddonLHE | 2 | Drachnyen(1029)[CD] | - | Hero, Resilient | relic:TalonOfHorus |
| blackBossHaarken | 2 | HeraldOfTheApocalypse(1020)[CD] | - | Hero, Flying | relic:Helspear |
| blackBossHaarkenCamp | 2 | HeraldOfTheApocalypse(1020)[CD] | - | Hero, Flying | relic:Helspear |
| blackBossHaarkenLEG | 2 | HeraldOfTheApocalypse(1020)[CD] | - | Hero, Flying | relic:Helspear |
| blackBossHaarkenLHE | 2 | HeraldOfTheApocalypse(1020)[CD] | - | Hero, Flying | relic:Helspear |
| blackBossTerminator | 2 | BringerOfDespair(1022)[CD] | - | Hero, TeleportStrike | relic:DaemonfleshPlate |
| blackBossTerminatorLEG | 2 | BringerOfDespair(1022)[CD] | - | Hero, TeleportStrike | relic:DaemonfleshPlate |
| blackBossTerminatorLHE | 2 | BringerOfDespair(1022)[CD] | - | Hero, TeleportStrike | relic:DaemonfleshPlate |
| blackNpc2Terminator | 2 | - | DrawFire | TeleportStrike | - |
| blackNpc3TraitorGuardsman | 2 | - | CrazedFocus | BattleFatigue | - |
| blackNpc4Havoc | 2 | - | FiringPosition | Overwatch | - |
| blackNpcAbaddon | 2 | Drachnyen(1029)[CD] | - | Hero, Resilient | relic:TalonOfHorus |
| blackNpcHaarken | 2 | HeraldOfTheApocalypse(1020)[CD] | - | Hero, Flying | relic:Helspear |
| blackNpcTerminator | 2 | BringerOfDespair(1022)[CD] | - | Hero, TeleportStrike | relic:DaemonfleshPlate |
| blackBossObliterator | 1 | FrenziedFiring(1036)[CD] | - | Hero | - |
| blackBossObliteratorCamp | 1 | FrenziedFiring(1036)[CD] | - | Hero | - |
| blackBossObliteratorLEG | 1 | FrenziedFiring(1036)[CD] | - | Hero | - |
| blackBossObliteratorLHE | 1 | FrenziedFiring(1036)[CD] | - | Hero | - |
| blackBossObliteratorSurv | 1 | FrenziedFiring(1036)[CD] | - | Hero | - |
| blackBossPossession | 1 | Incursion(1021)[CD] | - | Hero | relic:BookOfFate |
| blackBossPossessionLEG | 1 | Incursion(1021)[CD] | - | Hero | relic:BookOfFate |
| blackBossPossessionLHE | 1 | Incursion(1021)[CD] | - | Hero | relic:BookOfFate |
| blackBossPossessionSurv | 1 | Incursion(1021)[CD] | - | Hero | relic:BookOfFate |
| blackNpcMowForgefiend | 1 | HadesAutocannons(1147)[CD]<br>DaemonicOrdnance(1148)[CD] | - | MachineOfWar | mythic:ContemptuousDisregard |
| blackNpcObliterator | 1 | FrenziedFiring(1036)[CD] | - | Hero | - |
| blackNpc1Bloodletter | 0 | - | - | - | - |

### BlackTemplars — 21 unites, 20 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| templBossAggressor | 2 | FragstormGrenadeLauncher(1048)[CD] | - | Hero, MkXGravis | relic:RelicPowerFist |
| templBossAggressorCamp | 2 | FragstormGrenadeLauncher(1048)[CD] | - | Hero, MkXGravis | relic:RelicPowerFist |
| templBossAggressorLEG | 2 | FragstormGrenadeLauncher(1048)[CD] | - | Hero, MkXGravis | relic:RelicPowerFist |
| templBossAggressor_LHE | 2 | FragstormGrenadeLauncher(1048)[CD] | - | Hero, MkXGravis | relic:RelicPowerFist |
| templBossAncient | 1 | UnbreakableDuty(1061)[CD] | - | Hero | - |
| templBossAncientCamp | 1 | UnbreakableDuty(1061)[CD] | - | Hero | - |
| templBossAncient_LHE | 1 | UnbreakableDuty(1061)[CD] | - | Hero | - |
| templBossChampion | 1 | HolyDuel(1050)[CD] | - | Hero | - |
| templBossChampionCamp | 1 | HolyDuel(1050)[CD] | - | Hero | - |
| templBossChampionLEG | 1 | HolyDuel(1050)[CD] | - | Hero | - |
| templBossChampion_LHE | 1 | HolyDuel(1050)[CD] | - | Hero | - |
| templBossChampion_Surv | 1 | HolyDuel(1050)[CD] | - | Hero | - |
| templBossHelbrecht | 1 | CrusadeOfWrath(1049)[CD] | - | Hero | - |
| templBossHelbrecht_LHE | 1 | CrusadeOfWrath(1049)[CD] | - | Hero | - |
| templBossSwordBrother | 1 | ThunderousAssault(1043)[CD] | - | Hero | relic:RelicBoltPistol |
| templBossSwordBrotherCamp | 1 | ThunderousAssault(1043)[CD] | - | Hero | relic:RelicBoltPistol |
| templBossSwordBrother_LHE | 1 | ThunderousAssault(1043)[CD] | - | Hero | relic:RelicBoltPistol |
| templNpc1Initiate | 1 | DevoutPush(1053)[--] | - | - | - |
| templNpc3InitiatePyreblaster | 1 | - | Pyreblaster | - | - |
| templNpc4Aggressor | 1 | Fragstorm(1078)[CD] | - | MkXGravis | - |
| templNpc2Neophyte | 0 | IncendiaryShells(1044)[CD] | - | - | - |

### BloodAngels — 2 unites, 2 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| bloodNpc1Intercessor | 3 | - | RedThirst | TeleportStrike, Flying | - |
| bloodTerminator_LHE | 2 | SavageEchoes(1230)[CD] | - | Hero, TeleportStrike | - |

### DarkAngels — 17 unites, 16 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| darkaBossLion | 6 | InstrumentsOfVengeance(1215)[-D]<br>MartialExemplar(1216)[CD]<br>TheLionsWrath(1217)[CD] | TheEmperorsShield, BossEndFightUndefeated | Boss, Immune, Overwatch | - |
| darkaNpc4Watcher | 4 | - | NoHidingFromTheWatchers, WatchedOver | Immune, PermaDeath | - |
| darkaBossAzraelLHE | 2 | DarkTalonStrike(1092)[CD] | - | Hero, Overwatch | - |
| darkaBossHellblasterLHE | 2 | Supercharge(1103)[CD] | - | Hero, Overwatch | relic:RelicBoltPistol |
| darkaBossSternguardLHE | 2 | SternguardFocus(1228)[CD] | - | Hero, Overwatch | - |
| darkaBossTerminatorLHE | 2 | PlasmaCannon(1150)[CD] | - | Hero, TeleportStrike | relic:RelicPowerFist |
| darkaNpc1Infiltrator | 2 | - | - | Infiltrate, Overwatch | - |
| darkaNpc3Terminator | 2 | - | DeathwingKnight | TeleportStrike | - |
| darkaNpcAzrael | 2 | DarkTalonStrike(1092)[CD] | - | Hero, Overwatch | - |
| darkaNpcHellblaster | 2 | Supercharge(1103)[CD] | - | Hero, Overwatch | relic:RelicBoltPistol |
| darkaNpcTerminator | 2 | PlasmaCannon(1150)[CD] | - | Hero, TeleportStrike | relic:RelicPowerFist |
| darkaBossAsmodaiLHE | 1 | ExemplarOfHate(1140)[CD] | - | Hero | - |
| darkaBossCompanionLHE | 1 | CalibaniteGreatsword(1189)[CD] | - | Hero | relic:MonsterSlayerOfCaliban |
| darkaNpcAsmodai | 1 | ExemplarOfHate(1140)[CD] | - | Hero | - |
| darkaNpcCompanion | 1 | CalibaniteGreatsword(1189)[CD] | - | Hero | relic:MonsterSlayerOfCaliban |
| darkaNpcMowStormSpeeder | 1 | DeathOnTheWind(1213)[CD]<br>Hailstrike(1214)[CD] | - | MachineOfWar | mythic:MastersOfManoeuvre |
| darkaNpc2Hellblaster | 0 | - | - | - | - |

### DeathGuard — 23 unites, 23 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| deathBossMortarion | 7 | MortarionsPlagueWind(1093)[CD]<br>TheLantern(1094)[--]<br>ReapingScythe(1095)[CD] | BossEndFightUndefeated, ArchContaminator, HostOfPlagues | Boss, Immune, Flying | - |
| deathBossRotbone | 3 | RevitalizingMalignancy(1037)[CD] | - | Hero, Resilient, Healer | relic:OrbsOfDecay |
| deathBossRotboneLHE | 3 | RevitalizingMalignancy(1037)[CD] | - | Hero, Resilient, Healer | relic:OrbsOfDecay |
| deathNpcRotbone | 3 | RevitalizingMalignancy(1037)[CD] | - | Hero, Resilient, Healer | relic:OrbsOfDecay |
| deathBossBlightbringer | 2 | Poxwalkers(1040)[CD] | - | Hero, Resilient | relic:OrbsOfDecay |
| deathBossBlightbringerLHE | 2 | Poxwalkers(1040)[CD] | - | Hero, Resilient | relic:OrbsOfDecay |
| deathBossBlightlord | 2 | FlailSwing(1042)[CD] | - | Hero, Resilient | relic:DaemonfleshPlate |
| deathBossBlightlordLHE | 2 | FlailSwing(1042)[CD] | - | Hero, Resilient | relic:DaemonfleshPlate |
| deathBossPutrifier | 2 | FoulInfusion(1038)[CD] | - | Hero, Resilient | relic:OrbsOfDecay |
| deathBossPutrifierLHE | 2 | FoulInfusion(1038)[CD] | - | Hero, Resilient | relic:OrbsOfDecay |
| deathBossTyphus | 2 | PlagueWind(1035)[CD] | - | Hero, Resilient | relic:Lakrimae |
| deathBossTyphusLEG | 2 | PlagueWind(1035)[CD] | - | Hero, Resilient | relic:Lakrimae |
| deathBossTyphusLHE | 2 | PlagueWind(1035)[CD] | - | Hero, Resilient | relic:Lakrimae |
| deathBossTyphusSurv | 2 | PlagueWind(1035)[CD] | - | Hero, Resilient | relic:Lakrimae |
| deathNpc2PlagueMarine | 2 | BlightGrenades(1176)[CD] | CloudOfFlies | Resilient | - |
| deathNpc3Nurglings | 2 | - | MischiefMakers | TeleportStrike | - |
| deathNpcBlightbringer | 2 | Poxwalkers(1040)[CD] | - | Hero, Resilient | relic:OrbsOfDecay |
| deathNpcBlightlord | 2 | FlailSwing(1042)[CD] | - | Hero, Resilient | relic:DaemonfleshPlate |
| deathNpcPutrifier | 2 | FoulInfusion(1038)[CD] | - | Hero, Resilient | relic:OrbsOfDecay |
| deathNpcTyphus | 2 | PlagueWind(1035)[CD] | - | Hero, Resilient | relic:Lakrimae |
| deathNpc1Poxwalker | 1 | - | CursedOfTheWalkingPox | - | - |
| deathNpc4BlightlordTerminator | 1 | - | - | Resilient | - |
| deathNpcMoWCrawler | 1 | EntropyCannons(1168)[C-]<br>PlagueburstMortar(1169)[CD] | - | MachineOfWar | mythic:BlightedLand |

### Genestealers — 21 unites, 21 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| genesBossPatriarch | 4 | MightFromBelow(1165)[CD] | - | Hero, Infiltrate, Synapse, Unstoppable | relic:MawClawsOfThyrax |
| genesBossPatriarchLHE | 4 | MightFromBelow(1165)[CD] | - | Hero, Infiltrate, Synapse, Unstoppable | relic:MawClawsOfThyrax |
| genesNpcPatriarch | 4 | MightFromBelow(1165)[CD] | - | Hero, Infiltrate, Synapse, Unstoppable | relic:MawClawsOfThyrax |
| genesBossBiophagus | 2 | AberrantHypermorph(1166)[CD] | - | Hero, Healer | relic:AmuletOfTheVoidwyrm |
| genesBossBiophagusLHE | 2 | AberrantHypermorph(1166)[CD] | - | Hero, Healer | relic:AmuletOfTheVoidwyrm |
| genesDecoy | 2 | - | - | Steppable, Decoy | - |
| genesNpc1Aberrant | 2 | - | Hypermorph | Resilient | - |
| genesNpc2Genestealer | 2 | - | - | Infiltrate, Unstoppable | - |
| genesNpcBiophagus | 2 | AberrantHypermorph(1166)[CD] | - | Hero, Healer | relic:AmuletOfTheVoidwyrm |
| genesBossKelermorph | 1 | HeroicFusillade(1180)[CD] | - | Hero | relic:AmuletOfTheVoidwyrm |
| genesBossKelermorphLHE | 1 | HeroicFusillade(1180)[CD] | - | Hero | relic:AmuletOfTheVoidwyrm |
| genesBossKelermorphSurv | 1 | HeroicFusillade(1180)[CD] | - | Hero | relic:AmuletOfTheVoidwyrm |
| genesBossMagus | 1 | MindControl(1164)[CD] | - | Hero | - |
| genesBossMagusLHE | 1 | MindControl(1164)[CD] | - | Hero | - |
| genesBossMagusSurv | 1 | MindControl(1164)[CD] | - | Hero | - |
| genesBossPrimus | 1 | CultDemagogue(1179)[CD] | - | Hero | relic:AmuletOfTheVoidwyrm |
| genesBossPrimusLHE | 1 | CultDemagogue(1179)[CD] | - | Hero | relic:AmuletOfTheVoidwyrm |
| genesNpc3Neophyte | 1 | - | - | BattleFatigue | - |
| genesNpcKelermorph | 1 | HeroicFusillade(1180)[CD] | - | Hero | relic:AmuletOfTheVoidwyrm |
| genesNpcMagus | 1 | MindControl(1164)[CD] | - | Hero | - |
| genesNpcPrimus | 1 | CultDemagogue(1179)[CD] | - | Hero | relic:AmuletOfTheVoidwyrm |

### LeaguesOfVotann — 2 unites, 2 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| votanNpc1Ecog | 4 | - | RepairEnthusiast | Flying, Mechanical, Mechanic | - |
| votanNpc2Steeljack | 2 | - | - | Mechanical, Overwatch | - |

### Necrons — 43 unites, 43 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| necroBossC1Spyder | 4 | ScarabHive(1007)[CD] | - | Hero, Mechanical, Flying, Mechanic | relic:NetherRealmCasket |
| necroBossSpyder | 4 | ScarabHive(1007)[CD] | - | Hero, Mechanical, Flying, Mechanic | relic:NetherRealmCasket |
| necroBossSpyderLEG | 4 | ScarabHive(1007)[CD] | - | Hero, Mechanical, Flying, Mechanic | relic:NetherRealmCasket |
| necroBossSpyderLHE | 4 | ScarabHive(1007)[CD] | - | Hero, Mechanical, Flying, Mechanic | relic:NetherRealmCasket |
| necroNpcSpyder | 4 | ScarabHive(1007)[CD] | - | Hero, Mechanical, Flying, Mechanic | relic:NetherRealmCasket |
| necroBossC1Destroyer | 3 | MultiThreatEliminator(1006)[CD] | - | Hero, Overwatch, Mechanical | relic:NetherRealmCasket |
| necroBossC1Overlord | 3 | ResurrectionOrb(1009)[CD] | - | Hero, Mechanical, Resilient | relic:PhasalSubjugator |
| necroBossC1Plasmancer | 3 | HarbingerOfDestruction(1008)[CD] | - | Hero, Mechanical, Flying | - |
| necroBossChronomancerLHE | 3 | Chronometron(1226)[CD] | - | Hero, Mechanical, Flying | - |
| necroBossChronomancerSurv | 3 | Chronometron(1226)[CD] | - | Hero, Mechanical, Flying | - |
| necroBossDestroyer | 3 | MultiThreatEliminator(1006)[CD] | - | Hero, Overwatch, Mechanical | relic:NetherRealmCasket |
| necroBossDestroyerLEG | 3 | MultiThreatEliminator(1006)[CD] | - | Hero, Overwatch, Mechanical | relic:NetherRealmCasket |
| necroBossDestroyerLHE | 3 | MultiThreatEliminator(1006)[CD] | - | Hero, Overwatch, Mechanical | relic:NetherRealmCasket |
| necroBossOverlord | 3 | ResurrectionOrb(1009)[CD] | - | Hero, Mechanical, Resilient | relic:PhasalSubjugator |
| necroBossOverlordLEG | 3 | ResurrectionOrb(1009)[CD] | - | Hero, Mechanical, Resilient | relic:PhasalSubjugator |
| necroBossOverlordLHE | 3 | ResurrectionOrb(1009)[CD] | - | Hero, Mechanical, Resilient | relic:PhasalSubjugator |
| necroBossPlasmancer | 3 | HarbingerOfDestruction(1008)[CD] | - | Hero, Mechanical, Flying | - |
| necroBossPlasmancerLEG | 3 | HarbingerOfDestruction(1008)[CD] | - | Hero, Mechanical, Flying | - |
| necroBossPlasmancerLHE | 3 | HarbingerOfDestruction(1008)[CD] | - | Hero, Mechanical, Flying | - |
| necroChronomancer_LHE | 3 | Chronometron(1226)[CD] | - | Hero, Mechanical, Flying | - |
| necroNpcChronomancer | 3 | Chronometron(1226)[CD] | - | Hero, Mechanical, Flying | - |
| necroNpcDestroyer | 3 | MultiThreatEliminator(1006)[CD] | - | Hero, Overwatch, Mechanical | relic:NetherRealmCasket |
| necroNpcOverlord | 3 | ResurrectionOrb(1009)[CD] | - | Hero, Mechanical, Resilient | relic:PhasalSubjugator |
| necroNpcPlasmancer | 3 | HarbingerOfDestruction(1008)[CD] | - | Hero, Mechanical, Flying | - |
| necroBossC1Warden | 2 | AdaptiveStrategy(1005)[CD] | - | Hero, Mechanical | relic:NetherRealmCasket |
| necroBossWarden | 2 | AdaptiveStrategy(1005)[CD] | - | Hero, Mechanical | relic:NetherRealmCasket |
| necroBossWardenLEG | 2 | AdaptiveStrategy(1005)[CD] | - | Hero, Mechanical | relic:NetherRealmCasket |
| necroBossWardenLHE | 2 | AdaptiveStrategy(1005)[CD] | - | Hero, Mechanical | relic:NetherRealmCasket |
| necroNpc3Deathmark | 2 | PrecisionShot(1015)[--] | - | Mechanical | - |
| necroNpc5Swarm | 2 | ScarabSummon(1047)[CD] | - | Mechanical, Flying | - |
| necroNpcLHESwarm | 2 | ScarabSummon(1047)[CD] | - | Mechanical, Flying | - |
| necroNpcWarden | 2 | AdaptiveStrategy(1005)[CD] | - | Hero, Mechanical | relic:NetherRealmCasket |
| necroNpc1TutWarrior | 1 | - | - | Mechanical | - |
| necroNpc1TutWarriorFTUEtest | 1 | - | - | Mechanical | - |
| necroNpc1Warrior | 1 | - | - | Mechanical | - |
| necroNpc1WarriorSurv | 1 | - | - | Mechanical | - |
| necroNpc2FlayedOne | 1 | StormOfFlensingBlades(1010)[CD] | - | Mechanical | - |
| necroNpc2TutFlayedOne | 1 | StormOfFlensingBlades(1010)[CD] | - | Mechanical | - |
| necroNpc2TutFlayedOneFTUEtest | 1 | StormOfFlensingBlades(1010)[CD] | - | Mechanical | - |
| necroNpc4Destroyer | 1 | TunnelingHorror(1011)[C-] | - | Mechanical | - |
| necroNpc4DestroyerLHE | 1 | TunnelingHorror(1011)[C-] | - | Mechanical | - |
| necroNpc4DestroyerSurv | 1 | TunnelingHorror(1011)[C-] | - | Mechanical | - |
| necroNpcMoWReanimator | 1 | ReanimationBeam(1223)[CD]<br>NanoscarabRepairProtocols(1224)[CD] | - | MachineOfWar | mythic:GuardianConstruct |

### Orks — 30 unites, 30 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| orksNpc5LootGrotTeam | 5 | - | OiWatchIt, RunsAway | BattleFatigue, TwoManTeam, NonAttacking | - |
| orksNpc4AmmoGrot | 4 | - | ItsGonnaBlow, RunsAround | BattleFatigue, NonAttacking | - |
| orksBossBigMek | 3 | GrotTank(1057)[CD] | - | Hero, GetStuckIn, Mechanic | relic:SupaCyborkBody |
| orksBossBigMekLEG | 3 | GrotTank(1057)[CD] | - | Hero, GetStuckIn, Mechanic | relic:SupaCyborkBody |
| orksBossBigMekLHE | 3 | GrotTank(1057)[CD] | - | Hero, GetStuckIn, Mechanic | relic:SupaCyborkBody |
| orksBossKillaKan | 3 | DakkaDakkaDakka(1171)[CD] | - | Hero, GetStuckIn, Mechanical | - |
| orksBossKillaKanLEG | 3 | DakkaDakkaDakka(1171)[CD] | - | Hero, GetStuckIn, Mechanical | - |
| orksBossKillaKanLHE | 3 | DakkaDakkaDakka(1171)[CD] | - | Hero, GetStuckIn, Mechanical | - |
| orksBossNob | 3 | UnstoppableMomentumReworked(1152)[CD] | - | Hero, GetStuckIn, Unstoppable | relic:SupaCyborkBody |
| orksBossNobLEG | 3 | UnstoppableMomentumReworked(1152)[CD] | - | Hero, GetStuckIn, Unstoppable | relic:SupaCyborkBody |
| orksBossNobLHE | 3 | UnstoppableMomentumReworked(1152)[CD] | - | Hero, GetStuckIn, Unstoppable | relic:SupaCyborkBody |
| orksBossWarboss | 3 | Waaagh(1058)[CD] | - | Hero, GetStuckIn, Mechanical | relic:HeadwoppasKillchoppa |
| orksBossWarbossLHE | 3 | Waaagh(1058)[CD] | - | Hero, GetStuckIn, Mechanical | relic:HeadwoppasKillchoppa |
| orksNpc3GrotTank | 3 | - | - | Mechanical, BattleFatigue, Vehicle | - |
| orksNpcBigMek | 3 | GrotTank(1057)[CD] | - | Hero, GetStuckIn, Mechanic | relic:SupaCyborkBody |
| orksNpcKillaKan | 3 | DakkaDakkaDakka(1171)[CD] | - | Hero, GetStuckIn, Mechanical | - |
| orksNpcNob | 3 | UnstoppableMomentumReworked(1152)[CD] | - | Hero, GetStuckIn, Unstoppable | relic:SupaCyborkBody |
| orksNpcWarboss | 3 | Waaagh(1058)[CD] | - | Hero, GetStuckIn, Mechanical | relic:HeadwoppasKillchoppa |
| orksNpcWarbossSurv | 3 | Waaagh(1058)[CD] | - | Hero, GetStuckIn, Mechanical | relic:HeadwoppasKillchoppa |
| orksRedGobbo | 3 | ExplosivePresents(1170)[C-] | DaRevolushun | Hero, Resilient | - |
| orksBossRuntherd | 2 | GetEmRuntz(1045)[CD] | - | Hero, GetStuckIn | relic:SupaCyborkBody |
| orksBossRuntherdLEG | 2 | GetEmRuntz(1045)[CD] | - | Hero, GetStuckIn | relic:SupaCyborkBody |
| orksBossRuntherdLHE | 2 | GetEmRuntz(1045)[CD] | - | Hero, GetStuckIn | relic:SupaCyborkBody |
| orksNpc1Grot | 2 | - | PileIn | BattleFatigue | - |
| orksNpcRuntherd | 2 | GetEmRuntz(1045)[CD] | - | Hero, GetStuckIn | relic:SupaCyborkBody |
| orksNpc2OrkBoy | 1 | Stikkbomb(1051)[CD] | - | BattleFatigue | - |
| orksNpc6Stormboy | 1 | - | - | Flying | - |
| orksNpc7Squig | 1 | - | Bounce | - | - |
| orksNpc7SquigSurv | 1 | - | Bounce | - | - |
| orksNpcMoWRukkatrukk | 1 | SquigLaunchas(1200)[C-]<br>SquigMine(1201)[CD] | - | MachineOfWar | mythic:MoreGitzOverEre |

### Sisterhood — 19 unites, 18 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| adeptBossCelestineCE | 3 | SkyStrike(1025)[CD] | - | Boss, Immune, Flying | - |
| adeptNpc2Zephyrim | 3 | - | EmbodiedProphecy | Flying, TeleportStrike | - |
| adeptBossCelestine | 2 | SkyStrike(1025)[CD] | - | Hero, Flying | relic:TheArdentBlade |
| adeptBossCelestineLHE | 2 | SkyStrike(1025)[CD] | - | Hero, Flying | relic:TheArdentBlade |
| adeptBossHospitaller | 2 | RitesOfRestoration(1039)[CD] | - | Hero, Healer | - |
| adeptBossHospitallerLHE | 2 | RitesOfRestoration(1039)[CD] | - | Hero, Healer | - |
| adeptBossMorvenn | 2 | SanctorumMissile(1062)[CD] | - | Hero, Mechanical | - |
| adeptBossMorvennLHE | 2 | SanctorumMissile(1062)[CD] | - | Hero, Mechanical | - |
| adeptNpcCelestine | 2 | SkyStrike(1025)[CD] | - | Hero, Flying | relic:TheArdentBlade |
| adeptNpcHospitaller | 2 | RitesOfRestoration(1039)[CD] | - | Hero, Healer | - |
| adeptNpcMorvenn | 2 | SanctorumMissile(1062)[CD] | - | Hero, Mechanical | - |
| adeptBossCanoness | 1 | BrazierOfHolyFire(1041)[CD] | - | Hero | - |
| adeptBossCanonessLHE | 1 | BrazierOfHolyFire(1041)[CD] | - | Hero | - |
| adeptBossRetributor | 1 | ArmoriumCherub(1014)[CD] | - | Hero | - |
| adeptBossRetributorLHE | 1 | ArmoriumCherub(1014)[CD] | - | Hero | - |
| adeptNpcCanoness | 1 | BrazierOfHolyFire(1041)[CD] | - | Hero | - |
| adeptNpcMoWExorcist | 1 | ThriceBlessedConflagration(1187)[CD]<br>DevastatingRefrain(1188)[CD] | - | MachineOfWar | mythic:ShieldOfFaith |
| adeptNpcRetributor | 1 | ArmoriumCherub(1014)[CD] | - | Hero | - |
| adeptNpc1BattleSister | 0 | - | - | - | - |

### SpaceWolves — 1 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| spaceStormcaller_LHE | 2 | Stormcaller(1113)[CD] | - | Hero, Unstoppable | - |

### Tau — 33 unites, 33 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| tauBossRiptide | 8 | NovaBoost(1192)[CD]<br>NovaCharge(1193)[--]<br>NovaShield(1194)[CD] | MultiTracker, TargetLock | Boss, Immune, Flying, Vehicle, Mechanical | - |
| tauBossCrisis | 4 | EarlyWarningOverride(1077)[CD] | - | Hero, CloseCombatWeakness, Flying, Mechanical | relic:Dw02AdvancedBurstCannon |
| tauBossCrisisInc | 4 | EarlyWarningOverride(1077)[CD] | - | Hero, CloseCombatWeakness, Flying, Mechanical | relic:Dw02AdvancedBurstCannon |
| tauBossCrisisLHE | 4 | EarlyWarningOverride(1077)[CD] | - | Hero, CloseCombatWeakness, Flying, Mechanical | relic:Dw02AdvancedBurstCannon |
| tauBossShadowsun | 4 | ExemplarOfTheKauyon(1087)[CD] | - | Hero, CloseCombatWeakness, Flying, Infiltrate | - |
| tauBossShadowsunInc | 4 | ExemplarOfTheKauyon(1087)[CD] | - | Hero, CloseCombatWeakness, Flying, Infiltrate | - |
| tauBossShadowsunLHE | 4 | ExemplarOfTheKauyon(1087)[CD] | - | Hero, CloseCombatWeakness, Flying, Infiltrate | - |
| tauNpcCrisis | 4 | EarlyWarningOverride(1077)[CD] | - | Hero, CloseCombatWeakness, Flying, Mechanical | relic:Dw02AdvancedBurstCannon |
| tauNpcFarsight | 4 | ExemplarOfTheMontka(1210)[CD] | - | Hero, BeastSnagga, Flying, Mechanical | relic:DawnBlade |
| tauNpcShadowsun | 4 | ExemplarOfTheKauyon(1087)[CD] | - | Hero, CloseCombatWeakness, Flying, Infiltrate | - |
| tauBossDarkstrider | 3 | FightingRetreat(1081)[CD] | - | Hero, CloseCombatWeakness, Infiltrate | - |
| tauBossDarkstriderInc | 3 | FightingRetreat(1081)[CD] | - | Hero, CloseCombatWeakness, Infiltrate | - |
| tauBossDarkstriderLHE | 3 | FightingRetreat(1081)[CD] | - | Hero, CloseCombatWeakness, Infiltrate | - |
| tauBossFarsight | 3 | ExemplarOfTheMontka(1210)[CD] | - | Hero, Flying, Mechanical | relic:DawnBlade |
| tauBossFarsightInc | 3 | ExemplarOfTheMontka(1210)[CD] | - | Hero, Flying, Mechanical | relic:DawnBlade |
| tauBossFarsightLHE | 3 | ExemplarOfTheMontka(1210)[CD] | - | Hero, Flying, Mechanical | relic:DawnBlade |
| tauBossFarsightSurv | 3 | ExemplarOfTheMontka(1210)[CD] | - | Hero, Flying, Mechanical | relic:DawnBlade |
| tauNpc2DroneSniper | 3 | - | SaviorProtocols | Flying, Mechanical | - |
| tauNpc3DroneShield | 3 | - | SaviorProtocols | Flying, Mechanical | - |
| tauNpc4DroneCommandLink | 3 | - | SaviorProtocols | Flying, Mechanical | - |
| tauNpcDarkstrider | 3 | FightingRetreat(1081)[CD] | - | Hero, CloseCombatWeakness, Infiltrate | - |
| tauBossMarksman | 2 | SeekerMissileFrequencyLock(1069)[CD] | - | Hero, CloseCombatWeakness | - |
| tauBossMarksmanInc | 2 | SeekerMissileFrequencyLock(1069)[CD] | - | Hero, CloseCombatWeakness | - |
| tauBossMarksmanLHE | 2 | SeekerMissileFrequencyLock(1069)[CD] | - | Hero, CloseCombatWeakness | - |
| tauNpc5StealthSuit | 2 | ForwardObservers(1185)[CD]<br>WallOfMirrors(1186)[C-] | - | Infiltrate, Flying | - |
| tauNpc6Carnivore | 2 | - | HuntersInstincts | Infiltrate | - |
| tauNpcMarksman | 2 | SeekerMissileFrequencyLock(1069)[CD] | - | Hero, CloseCombatWeakness | - |
| tauBossAunShi | 1 | InspiredToGreatness(1082)[CD] | - | Hero | - |
| tauBossAunShiInc | 1 | InspiredToGreatness(1082)[CD] | - | Hero | - |
| tauBossAunShiLHE | 1 | InspiredToGreatness(1082)[CD] | - | Hero | - |
| tauNpc1FireWarrior | 1 | - | - | Overwatch | - |
| tauNpcAunShi | 1 | InspiredToGreatness(1082)[CD] | - | Hero | - |
| tauNpcMoWBroadside | 1 | HeavyRailRifle(1160)[CD]<br>TwinSmartMissileSystem(1161)[CD] | - | MachineOfWar | mythic:ElectrochaffBackups |

### ThousandSons — 27 unites, 26 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| thousBossAhriman | 2 | Doombolt(1102)[CD] | - | Hero, Flying | - |
| thousBossAhrimanCamp | 2 | Doombolt(1102)[CD] | - | Hero, Flying | - |
| thousBossAhrimanLHE | 2 | Doombolt(1102)[CD] | - | Hero, Flying | - |
| thousBossSorcerer | 2 | AttemptedPossession(1101)[CD] | - | Hero, Flying | relic:BookOfFate |
| thousBossSorcererCamp | 2 | AttemptedPossession(1101)[CD] | - | Hero, Flying | relic:BookOfFate |
| thousBossSorcererLHE | 2 | AttemptedPossession(1101)[CD] | - | Hero, Flying | relic:BookOfFate |
| thousBossTzaangor | 2 | SorcerousFacade(1100)[CD] | - | Hero, Flying | - |
| thousBossTzaangorCamp | 2 | SorcerousFacade(1100)[CD] | - | Hero, Flying | - |
| thousBossTzaangorLHE | 2 | SorcerousFacade(1100)[CD] | - | Hero, Flying | - |
| thousNpcAhriman | 2 | Doombolt(1102)[CD] | - | Hero, Flying | - |
| thousNpcSorcerer | 2 | AttemptedPossession(1101)[CD] | - | Hero, Flying | relic:BookOfFate |
| thousNpcTzaangor | 2 | SorcerousFacade(1100)[CD] | - | Hero, Flying | - |
| thousBossInfernalMaster | 1 | MasterOfTheTutelaries(1096)[CD] | - | Hero | relic:BookOfFate |
| thousBossInfernalMasterCamp | 1 | MasterOfTheTutelaries(1096)[CD] | - | Hero | relic:BookOfFate |
| thousBossInfernalMasterLHE | 1 | MasterOfTheTutelaries(1096)[CD] | - | Hero | relic:BookOfFate |
| thousBossInfernalMasterSurv | 1 | MasterOfTheTutelaries(1096)[CD] | - | Hero | relic:BookOfFate |
| thousBossTerminator | 1 | HellfyreMissileRack(1088)[CD] | - | Hero | relic:DaemonfleshPlate |
| thousBossTerminatorCamp | 1 | HellfyreMissileRack(1088)[CD] | - | Hero | relic:DaemonfleshPlate |
| thousBossTerminatorLHE | 1 | HellfyreMissileRack(1088)[CD] | - | Hero | relic:DaemonfleshPlate |
| thousBossTerminatorSurv | 1 | HellfyreMissileRack(1088)[CD] | - | Hero | relic:DaemonfleshPlate |
| thousNpc1PinkHorror | 1 | - | Split | - | - |
| thousNpc2Screamer | 1 | SlashingDive(1091)[C-] | - | Flying | - |
| thousNpc3RubricMarine | 1 | - | AllIsDust | - | - |
| thousNpcInfernalMaster | 1 | MasterOfTheTutelaries(1096)[CD] | - | Hero | relic:BookOfFate |
| thousNpcMowDaemonPrince | 1 | AetherStride(1208)[CD]<br>InfernalCannon(1209)[CD] | - | MachineOfWar | mythic:CabalOfSorcerers |
| thousNpcTerminator | 1 | HellfyreMissileRack(1088)[CD] | - | Hero | relic:DaemonfleshPlate |
| thousNpc4Terminator | 0 | - | - | - | - |

### Tyranids — 54 unites, 54 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| tyranBossHiveTyrantLeviathan | 7 | CallRipperSwarms(1052)[--]<br>Catalyst(1032)[C-]<br>StranglethornCannon(1056)[CD] | PrehensilePincerTail, SynapticImperative | Boss, Synapse, Flying, Immune | - |
| tyranNpc1Hormagaunt | 4 | - | AdrenalGlands, HungeringSwarm | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc1HormagauntGorgon | 4 | - | AdrenalGlands, HungeringSwarm | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc1HormagauntKronos | 4 | - | AdrenalGlands, HungeringSwarm | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc1Hormagaunt_SyncPvp_Gorgon | 4 | - | AdrenalGlands, HungeringSwarm | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc1Hormagaunt_SyncPvp_Kronos | 4 | - | AdrenalGlands, HungeringSwarm | InstinctiveBehaviour, BattleFatigue | - |
| tyranBossDeathleaper | 3 | FearOfTheUnseen(1115)[CD] | - | Hero, TeleportStrike, Infiltrate | - |
| tyranBossDeathleaperCE | 3 | FearOfTheUnseen(1115)[CD] | - | Hero, TeleportStrike, Infiltrate | - |
| tyranBossDeathleaperLHE | 3 | FearOfTheUnseen(1115)[CD] | - | Hero, TeleportStrike, Infiltrate | - |
| tyranBossDeathleaperSurv | 3 | FearOfTheUnseen(1115)[CD] | - | Hero, TeleportStrike, Infiltrate | - |
| tyranBossNeurothrope | 3 | SpiritLeech(1104)[CD] | - | Hero, Flying, Synapse | relic:NornCrown |
| tyranBossNeurothropeCE | 3 | SpiritLeech(1104)[CD] | - | Hero, Flying, Synapse | relic:NornCrown |
| tyranBossNeurothropeLHE | 3 | SpiritLeech(1104)[CD] | - | Hero, Flying, Synapse | relic:NornCrown |
| tyranBossNeurothropeSurv | 3 | SpiritLeech(1104)[CD] | - | Hero, Flying, Synapse | relic:NornCrown |
| tyranBossParasite | 3 | ItItches(1121)[CD] | - | Hero, Flying, Synapse | relic:MawClawsOfThyrax |
| tyranBossParasiteCE | 3 | ItItches(1121)[CD] | - | Hero, Flying, Synapse | relic:MawClawsOfThyrax |
| tyranBossParasiteLHE | 3 | ItItches(1121)[CD] | - | Hero, Flying, Synapse | relic:MawClawsOfThyrax |
| tyranBossParasiteSurv | 3 | ItItches(1121)[CD] | - | Hero, Flying, Synapse | relic:MawClawsOfThyrax |
| tyranBossWingedPrime | 3 | AlphaWarrior(1112)[CD] | - | Hero, Synapse, Flying | relic:MawClawsOfThyrax |
| tyranBossWingedPrimeCE | 3 | AlphaWarrior(1112)[CD] | - | Hero, Synapse, Flying | relic:MawClawsOfThyrax |
| tyranBossWingedPrimeLEG | 3 | AlphaWarrior(1112)[CD] | - | Hero, Synapse, Flying | relic:MawClawsOfThyrax |
| tyranBossWingedPrimeLHE | 3 | AlphaWarrior(1112)[CD] | - | Hero, Synapse, Flying | relic:MawClawsOfThyrax |
| tyranBossWingedPrimeSurv | 3 | AlphaWarrior(1112)[CD] | - | Hero, Synapse, Flying | relic:MawClawsOfThyrax |
| tyranNpc3Termagant | 3 | - | HailOfLivingAmmunition | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc3TermagantGorgon | 3 | - | HailOfLivingAmmunition | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc3TermagantKronos | 3 | - | HailOfLivingAmmunition | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc3Termagant_SyncPvp_Gorgon | 3 | - | HailOfLivingAmmunition | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc3Termagant_SyncPvp_Kronos | 3 | - | HailOfLivingAmmunition | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc6SporeMine | 3 | - | - | InstinctiveBehaviour, Flying, PermaDeath | - |
| tyranNpcDeathleaper | 3 | FearOfTheUnseen(1115)[CD] | - | Hero, TeleportStrike, Infiltrate | - |
| tyranNpcNeurothrope | 3 | SpiritLeech(1104)[CD] | - | Hero, Flying, Synapse | relic:NornCrown |
| tyranNpcOSDeathleaper | 3 | FearOfTheUnseen(1115)[CD] | - | Hero, TeleportStrike, Infiltrate | - |
| tyranNpcOSNeurothrope | 3 | SpiritLeech(1104)[CD] | - | Hero, Flying, Synapse | relic:NornCrown |
| tyranNpcOSParasite | 3 | ItItches(1121)[CD] | - | Hero, Flying, Synapse | relic:MawClawsOfThyrax |
| tyranNpcOSWingedPrime | 3 | AlphaWarrior(1112)[CD] | - | Hero, Synapse, Flying | relic:MawClawsOfThyrax |
| tyranNpcParasite | 3 | ItItches(1121)[CD] | - | Hero, Flying, Synapse | relic:MawClawsOfThyrax |
| tyranNpcWingedPrime | 3 | AlphaWarrior(1112)[CD] | - | Hero, Synapse, Flying | relic:MawClawsOfThyrax |
| tyranNpc2RipperSwarm | 2 | Burrowers(1023)[C-] | - | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc2RipperSwarmGorgon | 2 | Burrowers(1023)[C-] | - | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc2RipperSwarmKronos | 2 | Burrowers(1023)[C-] | - | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc2RipperSwarm_SyncPvp_Gorgon | 2 | Burrowers(1023)[C-] | - | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc2RipperSwarm_SyncPvp_Kronos | 2 | Burrowers(1023)[C-] | - | InstinctiveBehaviour, BattleFatigue | - |
| tyranNpc5Barbgaunt | 2 | - | SynapticInsight | InstinctiveBehaviour | - |
| tyranNpc5BarbgauntSurv | 2 | - | SynapticInsight | InstinctiveBehaviour | - |
| tyranBossTyrantGuard | 1 | CrushingClaws(1105)[CD] | - | Hero | relic:MawClawsOfThyrax |
| tyranBossTyrantGuardCE | 1 | CrushingClaws(1105)[CD] | - | Hero | relic:MawClawsOfThyrax |
| tyranBossTyrantGuardLHE | 1 | CrushingClaws(1105)[CD] | - | Hero | relic:MawClawsOfThyrax |
| tyranNpc4Warrior | 1 | ScythingTalons(1065)[CD] | - | Synapse | - |
| tyranNpc4WarriorCE2Gorgon | 1 | ScythingTalons(1065)[CD] | - | Synapse | - |
| tyranNpc4WarriorCE2Kronos | 1 | ScythingTalons(1065)[CD] | - | Synapse | - |
| tyranNpc4WarriorSurv | 1 | ScythingTalons(1065)[CD] | - | Synapse | - |
| tyranNpcMowBiovore | 1 | BioMinefield(1144)[CD]<br>SporeMineLauncher(1145)[CD] | - | MachineOfWar | mythic:HyperCorrosiveAcid |
| tyranNpcOSTyrantGuard | 1 | CrushingClaws(1105)[CD] | - | Hero | relic:MawClawsOfThyrax |
| tyranNpcTyrantGuard | 1 | CrushingClaws(1105)[CD] | - | Hero | relic:MawClawsOfThyrax |

### Ultramarines — 25 unites, 25 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| ultraBossEliminatorSgt | 3 | MortisRound(1004)[CD] | - | Hero, Overwatch, Infiltrate | - |
| ultraBossEliminatorSgtCamp | 3 | MortisRound(1004)[CD] | - | Hero, Overwatch, Infiltrate | - |
| ultraBossEliminatorSgtLHE | 3 | MortisRound(1004)[CD] | - | Hero, Overwatch, Infiltrate | - |
| ultraBossInceptorSgt | 3 | DeathFromAbove(1003)[CD] | - | Hero, Flying, MkXGravis | relic:RelicBoltPistol |
| ultraBossInceptorSgtLHE | 3 | DeathFromAbove(1003)[CD] | - | Hero, Flying, MkXGravis | relic:RelicBoltPistol |
| ultraNpcEliminatorSgt | 3 | MortisRound(1004)[CD] | - | Hero, Overwatch, Infiltrate | - |
| ultraNpcInceptorSgt | 3 | DeathFromAbove(1003)[CD] | - | Hero, Flying, MkXGravis | relic:RelicBoltPistol |
| ultraBossApothecary | 2 | CombatRestoratives(1002)[CD] | - | Hero, Healer | - |
| ultraBossApothecaryLHE | 2 | CombatRestoratives(1002)[CD] | - | Hero, Healer | - |
| ultraBossCalgar | 2 | GauntletsOfUltramar(1000)[CD] | - | Hero, MkXGravis | - |
| ultraBossCalgarLHE | 2 | GauntletsOfUltramar(1000)[CD] | - | Hero, MkXGravis | - |
| ultraNpc1Inceptor | 2 | - | - | Flying, MkXGravis | - |
| ultraNpc4HeavyIntercessor | 2 | HellfireShells(1080)[CD] | RapidFire | MkXGravis | - |
| ultraNpc4HeavyIntercessorSurv | 2 | HellfireShells(1080)[CD] | RapidFire | MkXGravis | - |
| ultraNpcApothecary | 2 | CombatRestoratives(1002)[CD] | - | Hero, Healer | - |
| ultraNpcCalgar | 2 | GauntletsOfUltramar(1000)[CD] | - | Hero, MkXGravis | - |
| ultraBossTigurius | 1 | StormOfWrath(1019)[CD] | - | Hero | - |
| ultraBossTiguriusLHE | 1 | StormOfWrath(1019)[CD] | - | Hero | - |
| ultraBossTitus | 1 | TacticalPrecision(1154)[CD] | - | Hero | relic:RelicBoltPistol |
| ultraBossTitusLHE | 1 | TacticalPrecision(1154)[CD] | - | Hero | relic:RelicBoltPistol |
| ultraBossTitusSurv | 1 | TacticalPrecision(1154)[CD] | - | Hero | relic:RelicBoltPistol |
| ultraNpc2Eliminator | 1 | - | - | Overwatch | - |
| ultraNpc3Intercessor | 1 | - | RapidFire | - | - |
| ultraNpcMoWDreadnought | 1 | DutyEternal(1158)[CD]<br>MacroPlasmaIncinerator(1159)[C-] | - | MachineOfWar | mythic:WisdomOfTheAncients |
| ultraNpcTigurius | 1 | StormOfWrath(1019)[CD] | - | Hero | - |

### WorldEaters — 5 unites, 5 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| worldBossEightboundLHE | 3 | OverwhelmingWrath(1141)[CD] | - | Hero, Resilient, Unstoppable | relic:TalismanOfRage |
| worldBossTerminatorLHE | 3 | BloodyFury(1129)[CD] | - | Hero, TeleportStrike, Unstoppable | relic:DaemonfleshPlate |
| worldBossJakhalLHE | 2 | JakhalStimms(1131)[CD] | - | Hero, Resilient | relic:TalismanOfRage |
| worldBossExecutionsLHE | 1 | MurderousSwing(1137)[CD] | - | Hero | relic:TalismanOfRage |
| worldBossKharnLHE | 1 | KillMaimBurn(1132)[CD] | - | Hero | - |

