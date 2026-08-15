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

- Unites `npc` : **491** ; kits sans manque : **449** ; kits avec du travail : **42**
- Actives distinctes : **147** — `[--]` **1** · `[C-]` **17** · `[CD]` **129**
- Passifs distincts : **177** — portes **133**, non portes **44**
- Traits de kit distincts (AUCUN ecarte — le seuil de frequence a disparu avec #1015) :
  **58** — couverts **57**, non couverts **1**
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
| trait | TwoManTeam | 4 | astraNpc2Lascannon, astraNpc4Mortar, astraNpc4MortarSurv |
| passif | RapidFire | 3 | ultraNpc3Intercessor, ultraNpc4HeavyIntercessor, ultraNpc4HeavyIntercessorSurv |
| passif | BossEndFightUndefeated | 2 | darkaBossLion, deathBossMortarion |
| passif | Bounce | 2 | orksNpc7Squig, orksNpc7SquigSurv |
| passif | Shrapnel | 2 | astraNpc4Mortar, astraNpc4MortarSurv |
| active | Maugetar | 1 | eldarBossMauganRaUltra |
| passif | ArchContaminator | 1 | deathBossMortarion |
| passif | CloudOfFlies | 1 | deathNpc2PlagueMarine |
| passif | Conceal | 1 | eldarNpc2Warlock |
| passif | CrazedFocus | 1 | blackNpc3TraitorGuardsman |
| passif | DaRevolushun | 1 | orksRedGobbo |
| passif | DrawFire | 1 | blackNpc2Terminator |
| passif | EmbodiedProphecy | 1 | adeptNpc2Zephyrim |
| passif | Explosive | 1 | LootObj_ExplOilDrum |
| passif | FiringPosition | 1 | blackNpc4Havoc |
| passif | HostOfPlagues | 1 | deathBossMortarion |
| passif | HuntersInstincts | 1 | tauNpc6Carnivore |
| passif | ItsGonnaBlow | 1 | orksNpc4AmmoGrot |
| passif | MultiTracker | 1 | tauBossRiptide |
| passif | NoHidingFromTheWatchers | 1 | darkaNpc4Watcher |
| passif | OiWatchIt | 1 | orksNpc5LootGrotTeam |
| passif | PileIn | 1 | orksNpc1Grot |
| passif | PowerUp_Bomb | 1 | powupBomb |
| passif | PowerUp_HeroSpawn_BladeChampion | 1 | powupHeroSpawn_BladeChampion |
| passif | PowerUp_HeroSpawn_Uthar | 1 | powupHeroSpawn_Uthar |
| passif | PowerUp_HeroSpawn_VexilusPraetor | 1 | powupHeroSpawn_VexilusPraeto |
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
| passif | RepairEnthusiast | 1 | votanNpc1Ecog |
| passif | RunsAround | 1 | orksNpc4AmmoGrot |
| passif | RunsAway | 1 | orksNpc5LootGrotTeam |
| passif | SelfRepairMechanismReworked | 1 | admecBossBelisarius |
| passif | SynapticImperative | 1 | tyranBossHiveTyrantLeviathan |
| passif | TargetLock | 1 | tauBossRiptide |
| passif | TheEmperorsShield | 1 | darkaBossLion |
| passif | Volatile | 1 | LootObj_AmmoBox |
| passif | WatchedOver | 1 | darkaNpc4Watcher |

## Faces DECISION ouvertes sur des actives EXECUTEES (17)

Ces abilities s'executent fidelement mais sont CHOISIES avec un scoring qui n'est pas celui
du natif. Aucun compteur de manque ne les voit — elles ne sont pas des items absents, ce
sont des **faces** absentes d'items presents.

`ArcScourge`, `BasiliskBarrage`, `CallRipperSwarms`, `Catalyst`, `DevoutPush`, `EntropyCannons`, `ExplosivePresents`, `LeadingTheCharge`, `NovaCharge`, `PrecisionShot`, `Reveal`, `SlashingDive`, `StrikeFromTheShadows`, `TunnelingHorror`, `ValkyrieStrike`, `WallOfMirrors`, `WarConstruct`

## Inventaire complet, par faction

### ? — 51 unites, 15 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| LootObj_AmmoBox | 1 | - | Volatile | - | - |
| LootObj_ExplOilDrum | 1 | - | Explosive | - | - |
| powupBomb | 1 | - | PowerUp_Bomb | - | - |
| powupHeroSpawn_BladeChampion | 1 | - | PowerUp_HeroSpawn_BladeChampion | - | - |
| powupHeroSpawn_Uthar | 1 | - | PowerUp_HeroSpawn_Uthar | - | - |
| powupHeroSpawn_VexilusPraeto | 1 | - | PowerUp_HeroSpawn_VexilusPraetor | - | - |
| powupReinforcement | 1 | - | PowerUp_Reinforcement | - | - |
| powupReinforcementShield | 1 | - | PowerUp_ReinforcementShield | - | - |
| powupResurrect | 1 | - | PowerUp_Resurrect | - | - |
| powupSummonSpawn_bloodSmnIntercessor | 1 | - | PowerUp_SummonSpawn_bloodSmnIntercessor | - | - |
| powupSummonSpawn_darkaSmnHellblaster | 1 | - | PowerUp_SummonSpawn_darkaSmnHellblaster | - | - |
| powupSummonSpawn_darkaSmnTerminator | 1 | - | PowerUp_SummonSpawn_darkaSmnTerminator | - | - |
| powupSummonSpawn_templSmnAggressor | 1 | - | PowerUp_SummonSpawn_templSmnAggressor | - | - |
| powupSummonSpawn_ultraSmnHeavyIntercessor | 1 | - | PowerUp_SummonSpawn_ultraSmnHeavyIntercessor | - | - |
| powupSummonSpawn_ultraSmnInceptor | 1 | - | PowerUp_SummonSpawn_ultraSmnInceptor | - | - |
| LootObj_Blackstone | 0 | - | - | - | - |
| LootObj_CoinCrate | 0 | - | - | - | - |
| LootObj_Crate_Cha | 0 | - | - | - | - |
| LootObj_Crate_Imp | 0 | - | - | - | - |
| LootObj_Crate_Xen | 0 | - | - | - | - |
| LootObj_FancyBox | 0 | - | - | - | - |
| LootObj_OilDrum | 0 | - | - | - | - |
| LootObj_Pod_Common_Cha | 0 | - | - | - | - |
| LootObj_Pod_Common_Imp | 0 | - | - | - | - |
| LootObj_Pod_Common_Xen | 0 | - | - | - | - |
| LootObj_Pod_Epic_Cha | 0 | - | - | - | - |
| LootObj_Pod_Epic_Imp | 0 | - | - | - | - |
| LootObj_Pod_Epic_Xen | 0 | - | - | - | - |
| LootObj_Pod_Legendary_Cha | 0 | - | - | - | - |
| LootObj_Pod_Legendary_Imp | 0 | - | - | - | - |
| LootObj_Pod_Legendary_Xen | 0 | - | - | - | - |
| LootObj_Pod_Mythic_Cha | 0 | - | - | - | - |
| LootObj_Pod_Mythic_Imp | 0 | - | - | - | - |
| LootObj_Pod_Mythic_Xen | 0 | - | - | - | - |
| LootObj_Pod_Rare_Cha | 0 | - | - | - | - |
| LootObj_Pod_Rare_Imp | 0 | - | - | - | - |
| LootObj_Pod_Rare_Xen | 0 | - | - | - | - |
| LootObj_Pod_Uncommon_Cha | 0 | - | - | - | - |
| LootObj_Pod_Uncommon_Imp | 0 | - | - | - | - |
| LootObj_Pod_Uncommon_Xen | 0 | - | - | - | - |
| LootObj_Strongbox_Cha | 0 | - | - | - | - |
| LootObj_Strongbox_Imp | 0 | - | - | - | - |
| LootObj_Strongbox_Xen | 0 | - | - | - | - |
| LootObj_XPBook | 0 | - | - | - | - |
| powupArmor | 0 | - | - | - | - |
| powupDamage | 0 | - | - | - | - |
| powupHealing | 0 | - | - | - | - |
| powupHealth | 0 | - | - | - | - |
| powupHits | 0 | - | - | - | - |
| powupMeleeHits | 0 | - | - | - | - |
| powupReactivateAbility | 0 | - | - | - | - |

### AdeptusAstartes — 2 unites, 0 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| astarCyrus_LHE | 0 | StrikeFromTheShadows(1225)[C-] | - | - | - |
| astarNpc1HaywireMine | 0 | - | - | - | - |

### AdeptusMechanicus — 29 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| admecBossBelisarius | 2 | InvocationOfMachineVengeance(1172)[CD]<br>ArcScourge(1173)[C-]<br>SolarAtomizer(1174)[CD] | SelfRepairMechanismReworked, PreCalibratedPurgeSolution | - | - |
| admecBossDestroyer | 0 | SentinelDirectives(1139)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossDestroyerCE | 0 | SentinelDirectives(1139)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossDestroyerLHE | 0 | SentinelDirectives(1139)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossDominus | 0 | RadBombardment(1116)[CD] | - | - | - |
| admecBossDominusCE | 0 | RadBombardment(1116)[CD] | - | - | - |
| admecBossDominusLEG | 0 | RadBombardment(1116)[CD] | - | - | - |
| admecBossDominusLHE | 0 | RadBombardment(1116)[CD] | - | - | - |
| admecBossDominusSurv | 0 | RadBombardment(1116)[CD] | - | - | - |
| admecBossManipulus | 0 | DefendTheDivineWork(1117)[CD] | - | - | - |
| admecBossManipulusCE | 0 | DefendTheDivineWork(1117)[CD] | - | - | - |
| admecBossManipulusLEG | 0 | DefendTheDivineWork(1117)[CD] | - | - | - |
| admecBossManipulusLHE | 0 | DefendTheDivineWork(1117)[CD] | - | - | - |
| admecBossManipulusSurv | 0 | DefendTheDivineWork(1117)[CD] | - | - | - |
| admecBossMarshall | 0 | DoctrinaImperatives(1118)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossMarshallCE | 0 | DoctrinaImperatives(1118)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossMarshallLEG | 0 | DoctrinaImperatives(1118)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossMarshallLHE | 0 | DoctrinaImperatives(1118)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossMarshallSurv | 0 | DoctrinaImperatives(1118)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossRuststalker | 0 | CordClaw(1122)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossRuststalkerCE | 0 | CordClaw(1122)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossRuststalkerLEG | 0 | CordClaw(1122)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossRuststalkerLHE | 0 | CordClaw(1122)[CD] | - | - | relic:KardiocoreGalvanus |
| admecBossRuststalkerSurv | 0 | CordClaw(1122)[CD] | - | - | relic:KardiocoreGalvanus |
| admecNpc1Vanguard | 0 | - | - | - | - |
| admecNpc1VanguardSurv | 0 | - | - | - | - |
| admecNpc2Techpriest | 0 | - | - | - | - |
| admecNpc3Electropriest | 0 | - | - | - | - |
| admecNpc3ElectropriestSurv | 0 | - | - | - | - |

### Aeldari — 26 unites, 2 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| eldarBossMauganRaUltra | 1 | Maugetar[--]! | - | - | relic:Maugetar |
| eldarNpc2Warlock | 1 | Reveal(1107)[C-] | Conceal | - | - |
| eldarBossAutarch | 0 | Loki_SwoopingHawk(1064)[CD] | - | - | relic:PhoenixGem |
| eldarBossAutarchCamp | 0 | Loki_SwoopingHawk(1064)[CD] | - | - | relic:PhoenixGem |
| eldarBossAutarchLHE | 0 | Loki_SwoopingHawk(1064)[CD] | - | - | relic:PhoenixGem |
| eldarBossFarseer | 0 | Executioner(1066)[CD] | - | - | - |
| eldarBossFarseerCamp | 0 | Executioner(1066)[CD] | - | - | - |
| eldarBossFarseerLEG | 0 | Executioner(1066)[CD] | - | - | - |
| eldarBossFarseerLHE | 0 | Executioner(1066)[CD] | - | - | - |
| eldarBossFarseerSurv | 0 | Executioner(1066)[CD] | - | - | - |
| eldarBossJainZar | 0 | SilentDeath(1068)[CD] | - | - | - |
| eldarBossJainZarCamp | 0 | SilentDeath(1068)[CD] | - | - | - |
| eldarBossJainZarLEG | 0 | SilentDeath(1068)[CD] | - | - | - |
| eldarBossJainZarLHE | 0 | SilentDeath(1068)[CD] | - | - | - |
| eldarBossMauganRa | 0 | HarvesterOfSouls(1067)[CD] | - | - | relic:Maugetar |
| eldarBossMauganRaCamp | 0 | HarvesterOfSouls(1067)[CD] | - | - | relic:Maugetar |
| eldarBossMauganRaLEG | 0 | HarvesterOfSouls(1067)[CD] | - | - | relic:Maugetar |
| eldarBossMauganRaLHE | 0 | HarvesterOfSouls(1067)[CD] | - | - | relic:Maugetar |
| eldarBossRanger | 0 | FireAndReposition(1063)[CD] | - | - | - |
| eldarBossRangerCamp | 0 | FireAndReposition(1063)[CD] | - | - | - |
| eldarBossRangerLHE | 0 | FireAndReposition(1063)[CD] | - | - | - |
| eldarBossRangerSurv | 0 | FireAndReposition(1063)[CD] | - | - | - |
| eldarNpc1Guardian | 0 | PlasmaGrenade(1098)[CD] | - | - | - |
| eldarNpc3Harlequin | 0 | KissOfDeath(1108)[CD] | - | - | - |
| eldarNpc4Wraithguard | 0 | WarConstruct(1133)[C-] | - | - | - |
| eldarNpc4WraithguardSurv | 0 | WarConstruct(1133)[C-] | - | - | - |

### AstraMilitarum — 31 unites, 3 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| astraNpc4Mortar | 2 | - | Shrapnel | TwoManTeam | - |
| astraNpc4MortarSurv | 2 | - | Shrapnel | TwoManTeam | - |
| astraNpc2Lascannon | 1 | - | - | TwoManTeam | - |
| astraBossBullgryn | 0 | FragBomb(1017)[CD] | - | - | relic:RelicOfLostCadia |
| astraBossBullgrynLEG | 0 | FragBomb(1017)[CD] | - | - | relic:RelicOfLostCadia |
| astraBossBullgrynLHE | 0 | FragBomb(1017)[CD] | - | - | relic:RelicOfLostCadia |
| astraBossCreed | 0 | SupremeCommander(1028)[CD] | - | - | - |
| astraBossCreedLEG | 0 | SupremeCommander(1028)[CD] | - | - | - |
| astraBossCreedLHE | 0 | SupremeCommander(1028)[CD] | - | - | - |
| astraBossCreedSurv | 0 | SupremeCommander(1028)[CD] | - | - | - |
| astraBossOrdnance | 0 | BasiliskBarrage(1026)[C-] | - | - | relic:RelicOfLostCadia |
| astraBossOrdnanceLEG | 0 | BasiliskBarrage(1026)[C-] | - | - | relic:RelicOfLostCadia |
| astraBossOrdnanceLHE | 0 | BasiliskBarrage(1026)[C-] | - | - | relic:RelicOfLostCadia |
| astraBossPrimarisPsy | 0 | PsychicMaelstrom(1027)[CD] | - | - | relic:RelicOfLostCadia |
| astraBossPrimarisPsyLHE | 0 | PsychicMaelstrom(1027)[CD] | - | - | relic:RelicOfLostCadia |
| astraBossPrimarisPsySurv | 0 | PsychicMaelstrom(1027)[CD] | - | - | relic:RelicOfLostCadia |
| astraBossYarrick | 0 | SendInTheNextWave(1016)[CD] | - | - | - |
| astraBossYarrickLEG | 0 | SendInTheNextWave(1016)[CD] | - | - | - |
| astraBossYarrickLHE | 0 | SendInTheNextWave(1016)[CD] | - | - | - |
| astraBossYarrickSurv | 0 | SendInTheNextWave(1016)[CD] | - | - | - |
| astraNpc1Guardsman | 0 | - | - | - | - |
| astraNpc3Voxcaster | 0 | ValkyrieStrike(1018)[C-] | - | - | - |
| astraNpc5DeathRider | 0 | - | - | - | - |
| astraNpcBullgryn | 0 | FragBomb(1017)[CD] | - | - | relic:RelicOfLostCadia |
| astraNpcCreed | 0 | SupremeCommander(1028)[CD] | - | - | - |
| astraNpcDreir | 0 | LeadingTheCharge(1204)[C-] | - | - | relic:SabreOfSacrifice |
| astraNpcMowOrdnanceBattery | 0 | MalleusRocketLauncher(1142)[CD]<br>ForwardSpotter(1143)[CD] | - | - | mythic:OnMyPosition |
| astraNpcOrdnance | 0 | BasiliskBarrage(1026)[C-] | - | - | relic:RelicOfLostCadia |
| astraNpcPrimarisPsy | 0 | PsychicMaelstrom(1027)[CD] | - | - | relic:RelicOfLostCadia |
| astraNpcYarrick | 0 | SendInTheNextWave(1016)[CD] | - | - | - |
| astraYarrick_LHE | 0 | SendInTheNextWave(1016)[CD] | - | - | - |

### BlackLegion — 29 unites, 3 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| blackNpc2Terminator | 1 | - | DrawFire | - | - |
| blackNpc3TraitorGuardsman | 1 | - | CrazedFocus | - | - |
| blackNpc4Havoc | 1 | - | FiringPosition | - | - |
| blackBossAbaddon | 0 | Drachnyen(1029)[CD] | - | - | relic:TalonOfHorus |
| blackBossAbaddonCamp | 0 | Drachnyen(1029)[CD] | - | - | relic:TalonOfHorus |
| blackBossAbaddonLEG | 0 | Drachnyen(1029)[CD] | - | - | relic:TalonOfHorus |
| blackBossAbaddonLHE | 0 | Drachnyen(1029)[CD] | - | - | relic:TalonOfHorus |
| blackBossHaarken | 0 | HeraldOfTheApocalypse(1020)[CD] | - | - | relic:Helspear |
| blackBossHaarkenCamp | 0 | HeraldOfTheApocalypse(1020)[CD] | - | - | relic:Helspear |
| blackBossHaarkenLEG | 0 | HeraldOfTheApocalypse(1020)[CD] | - | - | relic:Helspear |
| blackBossHaarkenLHE | 0 | HeraldOfTheApocalypse(1020)[CD] | - | - | relic:Helspear |
| blackBossObliterator | 0 | FrenziedFiring(1036)[CD] | - | - | - |
| blackBossObliteratorCamp | 0 | FrenziedFiring(1036)[CD] | - | - | - |
| blackBossObliteratorLEG | 0 | FrenziedFiring(1036)[CD] | - | - | - |
| blackBossObliteratorLHE | 0 | FrenziedFiring(1036)[CD] | - | - | - |
| blackBossObliteratorSurv | 0 | FrenziedFiring(1036)[CD] | - | - | - |
| blackBossPossession | 0 | Incursion(1021)[CD] | - | - | relic:BookOfFate |
| blackBossPossessionLEG | 0 | Incursion(1021)[CD] | - | - | relic:BookOfFate |
| blackBossPossessionLHE | 0 | Incursion(1021)[CD] | - | - | relic:BookOfFate |
| blackBossPossessionSurv | 0 | Incursion(1021)[CD] | - | - | relic:BookOfFate |
| blackBossTerminator | 0 | BringerOfDespair(1022)[CD] | - | - | relic:DaemonfleshPlate |
| blackBossTerminatorLEG | 0 | BringerOfDespair(1022)[CD] | - | - | relic:DaemonfleshPlate |
| blackBossTerminatorLHE | 0 | BringerOfDespair(1022)[CD] | - | - | relic:DaemonfleshPlate |
| blackNpc1Bloodletter | 0 | - | - | - | - |
| blackNpcAbaddon | 0 | Drachnyen(1029)[CD] | - | - | relic:TalonOfHorus |
| blackNpcHaarken | 0 | HeraldOfTheApocalypse(1020)[CD] | - | - | relic:Helspear |
| blackNpcMowForgefiend | 0 | HadesAutocannons(1147)[CD]<br>DaemonicOrdnance(1148)[CD] | - | - | mythic:ContemptuousDisregard |
| blackNpcObliterator | 0 | FrenziedFiring(1036)[CD] | - | - | - |
| blackNpcTerminator | 0 | BringerOfDespair(1022)[CD] | - | - | relic:DaemonfleshPlate |

### BlackTemplars — 21 unites, 0 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| templBossAggressor | 0 | FragstormGrenadeLauncher(1048)[CD] | - | - | relic:RelicPowerFist |
| templBossAggressorCamp | 0 | FragstormGrenadeLauncher(1048)[CD] | - | - | relic:RelicPowerFist |
| templBossAggressorLEG | 0 | FragstormGrenadeLauncher(1048)[CD] | - | - | relic:RelicPowerFist |
| templBossAggressor_LHE | 0 | FragstormGrenadeLauncher(1048)[CD] | - | - | relic:RelicPowerFist |
| templBossAncient | 0 | UnbreakableDuty(1061)[CD] | - | - | - |
| templBossAncientCamp | 0 | UnbreakableDuty(1061)[CD] | - | - | - |
| templBossAncient_LHE | 0 | UnbreakableDuty(1061)[CD] | - | - | - |
| templBossChampion | 0 | HolyDuel(1050)[CD] | - | - | - |
| templBossChampionCamp | 0 | HolyDuel(1050)[CD] | - | - | - |
| templBossChampionLEG | 0 | HolyDuel(1050)[CD] | - | - | - |
| templBossChampion_LHE | 0 | HolyDuel(1050)[CD] | - | - | - |
| templBossChampion_Surv | 0 | HolyDuel(1050)[CD] | - | - | - |
| templBossHelbrecht | 0 | CrusadeOfWrath(1049)[CD] | - | - | - |
| templBossHelbrecht_LHE | 0 | CrusadeOfWrath(1049)[CD] | - | - | - |
| templBossSwordBrother | 0 | ThunderousAssault(1043)[CD] | - | - | relic:RelicBoltPistol |
| templBossSwordBrotherCamp | 0 | ThunderousAssault(1043)[CD] | - | - | relic:RelicBoltPistol |
| templBossSwordBrother_LHE | 0 | ThunderousAssault(1043)[CD] | - | - | relic:RelicBoltPistol |
| templNpc1Initiate | 0 | DevoutPush(1053)[C-] | - | - | - |
| templNpc2Neophyte | 0 | IncendiaryShells(1044)[CD] | - | - | - |
| templNpc3InitiatePyreblaster | 0 | - | - | - | - |
| templNpc4Aggressor | 0 | Fragstorm(1078)[CD] | - | - | - |

### BloodAngels — 2 unites, 0 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| bloodNpc1Intercessor | 0 | - | - | - | - |
| bloodTerminator_LHE | 0 | SavageEchoes(1230)[CD] | - | - | - |

### DarkAngels — 17 unites, 2 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| darkaBossLion | 2 | InstrumentsOfVengeance(1215)[CD]<br>MartialExemplar(1216)[CD]<br>TheLionsWrath(1217)[CD] | TheEmperorsShield, BossEndFightUndefeated | - | - |
| darkaNpc4Watcher | 2 | - | NoHidingFromTheWatchers, WatchedOver | - | - |
| darkaBossAsmodaiLHE | 0 | ExemplarOfHate(1140)[CD] | - | - | - |
| darkaBossAzraelLHE | 0 | DarkTalonStrike(1092)[CD] | - | - | - |
| darkaBossCompanionLHE | 0 | CalibaniteGreatsword(1189)[CD] | - | - | relic:MonsterSlayerOfCaliban |
| darkaBossHellblasterLHE | 0 | Supercharge(1103)[CD] | - | - | relic:RelicBoltPistol |
| darkaBossSternguardLHE | 0 | SternguardFocus(1228)[CD] | - | - | - |
| darkaBossTerminatorLHE | 0 | PlasmaCannon(1150)[CD] | - | - | relic:RelicPowerFist |
| darkaNpc1Infiltrator | 0 | - | - | - | - |
| darkaNpc2Hellblaster | 0 | - | - | - | - |
| darkaNpc3Terminator | 0 | - | - | - | - |
| darkaNpcAsmodai | 0 | ExemplarOfHate(1140)[CD] | - | - | - |
| darkaNpcAzrael | 0 | DarkTalonStrike(1092)[CD] | - | - | - |
| darkaNpcCompanion | 0 | CalibaniteGreatsword(1189)[CD] | - | - | relic:MonsterSlayerOfCaliban |
| darkaNpcHellblaster | 0 | Supercharge(1103)[CD] | - | - | relic:RelicBoltPistol |
| darkaNpcMowStormSpeeder | 0 | DeathOnTheWind(1213)[CD]<br>Hailstrike(1214)[CD] | - | - | mythic:MastersOfManoeuvre |
| darkaNpcTerminator | 0 | PlasmaCannon(1150)[CD] | - | - | relic:RelicPowerFist |

### DeathGuard — 23 unites, 2 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| deathBossMortarion | 3 | MortarionsPlagueWind(1093)[CD]<br>TheLantern(1094)[CD]<br>ReapingScythe(1095)[CD] | BossEndFightUndefeated, ArchContaminator, HostOfPlagues | - | - |
| deathNpc2PlagueMarine | 1 | BlightGrenades(1176)[CD] | CloudOfFlies | - | - |
| deathBossBlightbringer | 0 | Poxwalkers(1040)[CD] | - | - | relic:OrbsOfDecay |
| deathBossBlightbringerLHE | 0 | Poxwalkers(1040)[CD] | - | - | relic:OrbsOfDecay |
| deathBossBlightlord | 0 | FlailSwing(1042)[CD] | - | - | relic:DaemonfleshPlate |
| deathBossBlightlordLHE | 0 | FlailSwing(1042)[CD] | - | - | relic:DaemonfleshPlate |
| deathBossPutrifier | 0 | FoulInfusion(1038)[CD] | - | - | relic:OrbsOfDecay |
| deathBossPutrifierLHE | 0 | FoulInfusion(1038)[CD] | - | - | relic:OrbsOfDecay |
| deathBossRotbone | 0 | RevitalizingMalignancy(1037)[CD] | - | - | relic:OrbsOfDecay |
| deathBossRotboneLHE | 0 | RevitalizingMalignancy(1037)[CD] | - | - | relic:OrbsOfDecay |
| deathBossTyphus | 0 | PlagueWind(1035)[CD] | - | - | relic:Lakrimae |
| deathBossTyphusLEG | 0 | PlagueWind(1035)[CD] | - | - | relic:Lakrimae |
| deathBossTyphusLHE | 0 | PlagueWind(1035)[CD] | - | - | relic:Lakrimae |
| deathBossTyphusSurv | 0 | PlagueWind(1035)[CD] | - | - | relic:Lakrimae |
| deathNpc1Poxwalker | 0 | - | - | - | - |
| deathNpc3Nurglings | 0 | - | - | - | - |
| deathNpc4BlightlordTerminator | 0 | - | - | - | - |
| deathNpcBlightbringer | 0 | Poxwalkers(1040)[CD] | - | - | relic:OrbsOfDecay |
| deathNpcBlightlord | 0 | FlailSwing(1042)[CD] | - | - | relic:DaemonfleshPlate |
| deathNpcMoWCrawler | 0 | EntropyCannons(1168)[C-]<br>PlagueburstMortar(1169)[CD] | - | - | mythic:BlightedLand |
| deathNpcPutrifier | 0 | FoulInfusion(1038)[CD] | - | - | relic:OrbsOfDecay |
| deathNpcRotbone | 0 | RevitalizingMalignancy(1037)[CD] | - | - | relic:OrbsOfDecay |
| deathNpcTyphus | 0 | PlagueWind(1035)[CD] | - | - | relic:Lakrimae |

### Genestealers — 21 unites, 0 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| genesBossBiophagus | 0 | AberrantHypermorph(1166)[CD] | - | - | relic:AmuletOfTheVoidwyrm |
| genesBossBiophagusLHE | 0 | AberrantHypermorph(1166)[CD] | - | - | relic:AmuletOfTheVoidwyrm |
| genesBossKelermorph | 0 | HeroicFusillade(1180)[CD] | - | - | relic:AmuletOfTheVoidwyrm |
| genesBossKelermorphLHE | 0 | HeroicFusillade(1180)[CD] | - | - | relic:AmuletOfTheVoidwyrm |
| genesBossKelermorphSurv | 0 | HeroicFusillade(1180)[CD] | - | - | relic:AmuletOfTheVoidwyrm |
| genesBossMagus | 0 | MindControl(1164)[CD] | - | - | - |
| genesBossMagusLHE | 0 | MindControl(1164)[CD] | - | - | - |
| genesBossMagusSurv | 0 | MindControl(1164)[CD] | - | - | - |
| genesBossPatriarch | 0 | MightFromBelow(1165)[CD] | - | - | relic:MawClawsOfThyrax |
| genesBossPatriarchLHE | 0 | MightFromBelow(1165)[CD] | - | - | relic:MawClawsOfThyrax |
| genesBossPrimus | 0 | CultDemagogue(1179)[CD] | - | - | relic:AmuletOfTheVoidwyrm |
| genesBossPrimusLHE | 0 | CultDemagogue(1179)[CD] | - | - | relic:AmuletOfTheVoidwyrm |
| genesDecoy | 0 | - | - | - | - |
| genesNpc1Aberrant | 0 | - | - | - | - |
| genesNpc2Genestealer | 0 | - | - | - | - |
| genesNpc3Neophyte | 0 | - | - | - | - |
| genesNpcBiophagus | 0 | AberrantHypermorph(1166)[CD] | - | - | relic:AmuletOfTheVoidwyrm |
| genesNpcKelermorph | 0 | HeroicFusillade(1180)[CD] | - | - | relic:AmuletOfTheVoidwyrm |
| genesNpcMagus | 0 | MindControl(1164)[CD] | - | - | - |
| genesNpcPatriarch | 0 | MightFromBelow(1165)[CD] | - | - | relic:MawClawsOfThyrax |
| genesNpcPrimus | 0 | CultDemagogue(1179)[CD] | - | - | relic:AmuletOfTheVoidwyrm |

### LeaguesOfVotann — 2 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| votanNpc1Ecog | 1 | - | RepairEnthusiast | - | - |
| votanNpc2Steeljack | 0 | - | - | - | - |

### Necrons — 43 unites, 0 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| necroBossC1Destroyer | 0 | MultiThreatEliminator(1006)[CD] | - | - | relic:NetherRealmCasket |
| necroBossC1Overlord | 0 | ResurrectionOrb(1009)[CD] | - | - | relic:PhasalSubjugator |
| necroBossC1Plasmancer | 0 | HarbingerOfDestruction(1008)[CD] | - | - | - |
| necroBossC1Spyder | 0 | ScarabHive(1007)[CD] | - | - | relic:NetherRealmCasket |
| necroBossC1Warden | 0 | AdaptiveStrategy(1005)[CD] | - | - | relic:NetherRealmCasket |
| necroBossChronomancerLHE | 0 | Chronometron(1226)[CD] | - | - | - |
| necroBossChronomancerSurv | 0 | Chronometron(1226)[CD] | - | - | - |
| necroBossDestroyer | 0 | MultiThreatEliminator(1006)[CD] | - | - | relic:NetherRealmCasket |
| necroBossDestroyerLEG | 0 | MultiThreatEliminator(1006)[CD] | - | - | relic:NetherRealmCasket |
| necroBossDestroyerLHE | 0 | MultiThreatEliminator(1006)[CD] | - | - | relic:NetherRealmCasket |
| necroBossOverlord | 0 | ResurrectionOrb(1009)[CD] | - | - | relic:PhasalSubjugator |
| necroBossOverlordLEG | 0 | ResurrectionOrb(1009)[CD] | - | - | relic:PhasalSubjugator |
| necroBossOverlordLHE | 0 | ResurrectionOrb(1009)[CD] | - | - | relic:PhasalSubjugator |
| necroBossPlasmancer | 0 | HarbingerOfDestruction(1008)[CD] | - | - | - |
| necroBossPlasmancerLEG | 0 | HarbingerOfDestruction(1008)[CD] | - | - | - |
| necroBossPlasmancerLHE | 0 | HarbingerOfDestruction(1008)[CD] | - | - | - |
| necroBossSpyder | 0 | ScarabHive(1007)[CD] | - | - | relic:NetherRealmCasket |
| necroBossSpyderLEG | 0 | ScarabHive(1007)[CD] | - | - | relic:NetherRealmCasket |
| necroBossSpyderLHE | 0 | ScarabHive(1007)[CD] | - | - | relic:NetherRealmCasket |
| necroBossWarden | 0 | AdaptiveStrategy(1005)[CD] | - | - | relic:NetherRealmCasket |
| necroBossWardenLEG | 0 | AdaptiveStrategy(1005)[CD] | - | - | relic:NetherRealmCasket |
| necroBossWardenLHE | 0 | AdaptiveStrategy(1005)[CD] | - | - | relic:NetherRealmCasket |
| necroChronomancer_LHE | 0 | Chronometron(1226)[CD] | - | - | - |
| necroNpc1TutWarrior | 0 | - | - | - | - |
| necroNpc1TutWarriorFTUEtest | 0 | - | - | - | - |
| necroNpc1Warrior | 0 | - | - | - | - |
| necroNpc1WarriorSurv | 0 | - | - | - | - |
| necroNpc2FlayedOne | 0 | StormOfFlensingBlades(1010)[CD] | - | - | - |
| necroNpc2TutFlayedOne | 0 | StormOfFlensingBlades(1010)[CD] | - | - | - |
| necroNpc2TutFlayedOneFTUEtest | 0 | StormOfFlensingBlades(1010)[CD] | - | - | - |
| necroNpc3Deathmark | 0 | PrecisionShot(1015)[C-] | - | - | - |
| necroNpc4Destroyer | 0 | TunnelingHorror(1011)[C-] | - | - | - |
| necroNpc4DestroyerLHE | 0 | TunnelingHorror(1011)[C-] | - | - | - |
| necroNpc4DestroyerSurv | 0 | TunnelingHorror(1011)[C-] | - | - | - |
| necroNpc5Swarm | 0 | ScarabSummon(1047)[CD] | - | - | - |
| necroNpcChronomancer | 0 | Chronometron(1226)[CD] | - | - | - |
| necroNpcDestroyer | 0 | MultiThreatEliminator(1006)[CD] | - | - | relic:NetherRealmCasket |
| necroNpcLHESwarm | 0 | ScarabSummon(1047)[CD] | - | - | - |
| necroNpcMoWReanimator | 0 | ReanimationBeam(1223)[CD]<br>NanoscarabRepairProtocols(1224)[CD] | - | - | mythic:GuardianConstruct |
| necroNpcOverlord | 0 | ResurrectionOrb(1009)[CD] | - | - | relic:PhasalSubjugator |
| necroNpcPlasmancer | 0 | HarbingerOfDestruction(1008)[CD] | - | - | - |
| necroNpcSpyder | 0 | ScarabHive(1007)[CD] | - | - | relic:NetherRealmCasket |
| necroNpcWarden | 0 | AdaptiveStrategy(1005)[CD] | - | - | relic:NetherRealmCasket |

### Orks — 30 unites, 6 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| orksNpc5LootGrotTeam | 3 | - | OiWatchIt, RunsAway | TwoManTeam | - |
| orksNpc4AmmoGrot | 2 | - | ItsGonnaBlow, RunsAround | - | - |
| orksNpc1Grot | 1 | - | PileIn | - | - |
| orksNpc7Squig | 1 | - | Bounce | - | - |
| orksNpc7SquigSurv | 1 | - | Bounce | - | - |
| orksRedGobbo | 1 | ExplosivePresents(1170)[C-] | DaRevolushun | - | - |
| orksBossBigMek | 0 | GrotTank(1057)[CD] | - | - | relic:SupaCyborkBody |
| orksBossBigMekLEG | 0 | GrotTank(1057)[CD] | - | - | relic:SupaCyborkBody |
| orksBossBigMekLHE | 0 | GrotTank(1057)[CD] | - | - | relic:SupaCyborkBody |
| orksBossKillaKan | 0 | DakkaDakkaDakka(1171)[CD] | - | - | - |
| orksBossKillaKanLEG | 0 | DakkaDakkaDakka(1171)[CD] | - | - | - |
| orksBossKillaKanLHE | 0 | DakkaDakkaDakka(1171)[CD] | - | - | - |
| orksBossNob | 0 | UnstoppableMomentumReworked(1152)[CD] | - | - | relic:SupaCyborkBody |
| orksBossNobLEG | 0 | UnstoppableMomentumReworked(1152)[CD] | - | - | relic:SupaCyborkBody |
| orksBossNobLHE | 0 | UnstoppableMomentumReworked(1152)[CD] | - | - | relic:SupaCyborkBody |
| orksBossRuntherd | 0 | GetEmRuntz(1045)[CD] | - | - | relic:SupaCyborkBody |
| orksBossRuntherdLEG | 0 | GetEmRuntz(1045)[CD] | - | - | relic:SupaCyborkBody |
| orksBossRuntherdLHE | 0 | GetEmRuntz(1045)[CD] | - | - | relic:SupaCyborkBody |
| orksBossWarboss | 0 | Waaagh(1058)[CD] | - | - | relic:HeadwoppasKillchoppa |
| orksBossWarbossLHE | 0 | Waaagh(1058)[CD] | - | - | relic:HeadwoppasKillchoppa |
| orksNpc2OrkBoy | 0 | Stikkbomb(1051)[CD] | - | - | - |
| orksNpc3GrotTank | 0 | - | - | - | - |
| orksNpc6Stormboy | 0 | - | - | - | - |
| orksNpcBigMek | 0 | GrotTank(1057)[CD] | - | - | relic:SupaCyborkBody |
| orksNpcKillaKan | 0 | DakkaDakkaDakka(1171)[CD] | - | - | - |
| orksNpcMoWRukkatrukk | 0 | SquigLaunchas(1200)[CD]<br>SquigMine(1201)[CD] | - | - | mythic:MoreGitzOverEre |
| orksNpcNob | 0 | UnstoppableMomentumReworked(1152)[CD] | - | - | relic:SupaCyborkBody |
| orksNpcRuntherd | 0 | GetEmRuntz(1045)[CD] | - | - | relic:SupaCyborkBody |
| orksNpcWarboss | 0 | Waaagh(1058)[CD] | - | - | relic:HeadwoppasKillchoppa |
| orksNpcWarbossSurv | 0 | Waaagh(1058)[CD] | - | - | relic:HeadwoppasKillchoppa |

### Sisterhood — 19 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| adeptNpc2Zephyrim | 1 | - | EmbodiedProphecy | - | - |
| adeptBossCanoness | 0 | BrazierOfHolyFire(1041)[CD] | - | - | - |
| adeptBossCanonessLHE | 0 | BrazierOfHolyFire(1041)[CD] | - | - | - |
| adeptBossCelestine | 0 | SkyStrike(1025)[CD] | - | - | relic:TheArdentBlade |
| adeptBossCelestineCE | 0 | SkyStrike(1025)[CD] | - | - | - |
| adeptBossCelestineLHE | 0 | SkyStrike(1025)[CD] | - | - | relic:TheArdentBlade |
| adeptBossHospitaller | 0 | RitesOfRestoration(1039)[CD] | - | - | - |
| adeptBossHospitallerLHE | 0 | RitesOfRestoration(1039)[CD] | - | - | - |
| adeptBossMorvenn | 0 | SanctorumMissile(1062)[CD] | - | - | - |
| adeptBossMorvennLHE | 0 | SanctorumMissile(1062)[CD] | - | - | - |
| adeptBossRetributor | 0 | ArmoriumCherub(1014)[CD] | - | - | - |
| adeptBossRetributorLHE | 0 | ArmoriumCherub(1014)[CD] | - | - | - |
| adeptNpc1BattleSister | 0 | - | - | - | - |
| adeptNpcCanoness | 0 | BrazierOfHolyFire(1041)[CD] | - | - | - |
| adeptNpcCelestine | 0 | SkyStrike(1025)[CD] | - | - | relic:TheArdentBlade |
| adeptNpcHospitaller | 0 | RitesOfRestoration(1039)[CD] | - | - | - |
| adeptNpcMoWExorcist | 0 | ThriceBlessedConflagration(1187)[CD]<br>DevastatingRefrain(1188)[CD] | - | - | mythic:ShieldOfFaith |
| adeptNpcMorvenn | 0 | SanctorumMissile(1062)[CD] | - | - | - |
| adeptNpcRetributor | 0 | ArmoriumCherub(1014)[CD] | - | - | - |

### SpaceWolves — 1 unites, 0 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| spaceStormcaller_LHE | 0 | Stormcaller(1113)[CD] | - | - | - |

### Tau — 33 unites, 2 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| tauBossRiptide | 2 | NovaBoost(1192)[CD]<br>NovaCharge(1193)[C-]<br>NovaShield(1194)[CD] | MultiTracker, TargetLock | - | - |
| tauNpc6Carnivore | 1 | - | HuntersInstincts | - | - |
| tauBossAunShi | 0 | InspiredToGreatness(1082)[CD] | - | - | - |
| tauBossAunShiInc | 0 | InspiredToGreatness(1082)[CD] | - | - | - |
| tauBossAunShiLHE | 0 | InspiredToGreatness(1082)[CD] | - | - | - |
| tauBossCrisis | 0 | EarlyWarningOverride(1077)[CD] | - | - | relic:Dw02AdvancedBurstCannon |
| tauBossCrisisInc | 0 | EarlyWarningOverride(1077)[CD] | - | - | relic:Dw02AdvancedBurstCannon |
| tauBossCrisisLHE | 0 | EarlyWarningOverride(1077)[CD] | - | - | relic:Dw02AdvancedBurstCannon |
| tauBossDarkstrider | 0 | FightingRetreat(1081)[CD] | - | - | - |
| tauBossDarkstriderInc | 0 | FightingRetreat(1081)[CD] | - | - | - |
| tauBossDarkstriderLHE | 0 | FightingRetreat(1081)[CD] | - | - | - |
| tauBossFarsight | 0 | ExemplarOfTheMontka(1210)[CD] | - | - | relic:DawnBlade |
| tauBossFarsightInc | 0 | ExemplarOfTheMontka(1210)[CD] | - | - | relic:DawnBlade |
| tauBossFarsightLHE | 0 | ExemplarOfTheMontka(1210)[CD] | - | - | relic:DawnBlade |
| tauBossFarsightSurv | 0 | ExemplarOfTheMontka(1210)[CD] | - | - | relic:DawnBlade |
| tauBossMarksman | 0 | SeekerMissileFrequencyLock(1069)[CD] | - | - | - |
| tauBossMarksmanInc | 0 | SeekerMissileFrequencyLock(1069)[CD] | - | - | - |
| tauBossMarksmanLHE | 0 | SeekerMissileFrequencyLock(1069)[CD] | - | - | - |
| tauBossShadowsun | 0 | ExemplarOfTheKauyon(1087)[CD] | - | - | - |
| tauBossShadowsunInc | 0 | ExemplarOfTheKauyon(1087)[CD] | - | - | - |
| tauBossShadowsunLHE | 0 | ExemplarOfTheKauyon(1087)[CD] | - | - | - |
| tauNpc1FireWarrior | 0 | - | - | - | - |
| tauNpc2DroneSniper | 0 | - | - | - | - |
| tauNpc3DroneShield | 0 | - | - | - | - |
| tauNpc4DroneCommandLink | 0 | - | - | - | - |
| tauNpc5StealthSuit | 0 | ForwardObservers(1185)[CD]<br>WallOfMirrors(1186)[C-] | - | - | - |
| tauNpcAunShi | 0 | InspiredToGreatness(1082)[CD] | - | - | - |
| tauNpcCrisis | 0 | EarlyWarningOverride(1077)[CD] | - | - | relic:Dw02AdvancedBurstCannon |
| tauNpcDarkstrider | 0 | FightingRetreat(1081)[CD] | - | - | - |
| tauNpcFarsight | 0 | ExemplarOfTheMontka(1210)[CD] | - | - | relic:DawnBlade |
| tauNpcMarksman | 0 | SeekerMissileFrequencyLock(1069)[CD] | - | - | - |
| tauNpcMoWBroadside | 0 | HeavyRailRifle(1160)[CD]<br>TwinSmartMissileSystem(1161)[CD] | - | - | mythic:ElectrochaffBackups |
| tauNpcShadowsun | 0 | ExemplarOfTheKauyon(1087)[CD] | - | - | - |

### ThousandSons — 27 unites, 0 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| thousBossAhriman | 0 | Doombolt(1102)[CD] | - | - | - |
| thousBossAhrimanCamp | 0 | Doombolt(1102)[CD] | - | - | - |
| thousBossAhrimanLHE | 0 | Doombolt(1102)[CD] | - | - | - |
| thousBossInfernalMaster | 0 | MasterOfTheTutelaries(1096)[CD] | - | - | relic:BookOfFate |
| thousBossInfernalMasterCamp | 0 | MasterOfTheTutelaries(1096)[CD] | - | - | relic:BookOfFate |
| thousBossInfernalMasterLHE | 0 | MasterOfTheTutelaries(1096)[CD] | - | - | relic:BookOfFate |
| thousBossInfernalMasterSurv | 0 | MasterOfTheTutelaries(1096)[CD] | - | - | relic:BookOfFate |
| thousBossSorcerer | 0 | AttemptedPossession(1101)[CD] | - | - | relic:BookOfFate |
| thousBossSorcererCamp | 0 | AttemptedPossession(1101)[CD] | - | - | relic:BookOfFate |
| thousBossSorcererLHE | 0 | AttemptedPossession(1101)[CD] | - | - | relic:BookOfFate |
| thousBossTerminator | 0 | HellfyreMissileRack(1088)[CD] | - | - | relic:DaemonfleshPlate |
| thousBossTerminatorCamp | 0 | HellfyreMissileRack(1088)[CD] | - | - | relic:DaemonfleshPlate |
| thousBossTerminatorLHE | 0 | HellfyreMissileRack(1088)[CD] | - | - | relic:DaemonfleshPlate |
| thousBossTerminatorSurv | 0 | HellfyreMissileRack(1088)[CD] | - | - | relic:DaemonfleshPlate |
| thousBossTzaangor | 0 | SorcerousFacade(1100)[CD] | - | - | - |
| thousBossTzaangorCamp | 0 | SorcerousFacade(1100)[CD] | - | - | - |
| thousBossTzaangorLHE | 0 | SorcerousFacade(1100)[CD] | - | - | - |
| thousNpc1PinkHorror | 0 | - | - | - | - |
| thousNpc2Screamer | 0 | SlashingDive(1091)[C-] | - | - | - |
| thousNpc3RubricMarine | 0 | - | - | - | - |
| thousNpc4Terminator | 0 | - | - | - | - |
| thousNpcAhriman | 0 | Doombolt(1102)[CD] | - | - | - |
| thousNpcInfernalMaster | 0 | MasterOfTheTutelaries(1096)[CD] | - | - | relic:BookOfFate |
| thousNpcMowDaemonPrince | 0 | AetherStride(1208)[CD]<br>InfernalCannon(1209)[CD] | - | - | mythic:CabalOfSorcerers |
| thousNpcSorcerer | 0 | AttemptedPossession(1101)[CD] | - | - | relic:BookOfFate |
| thousNpcTerminator | 0 | HellfyreMissileRack(1088)[CD] | - | - | relic:DaemonfleshPlate |
| thousNpcTzaangor | 0 | SorcerousFacade(1100)[CD] | - | - | - |

### Tyranids — 54 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| tyranBossHiveTyrantLeviathan | 2 | CallRipperSwarms(1052)[C-]<br>Catalyst(1032)[C-]<br>StranglethornCannon(1056)[CD] | PrehensilePincerTail, SynapticImperative | - | - |
| tyranBossDeathleaper | 0 | FearOfTheUnseen(1115)[CD] | - | - | - |
| tyranBossDeathleaperCE | 0 | FearOfTheUnseen(1115)[CD] | - | - | - |
| tyranBossDeathleaperLHE | 0 | FearOfTheUnseen(1115)[CD] | - | - | - |
| tyranBossDeathleaperSurv | 0 | FearOfTheUnseen(1115)[CD] | - | - | - |
| tyranBossNeurothrope | 0 | SpiritLeech(1104)[CD] | - | - | relic:NornCrown |
| tyranBossNeurothropeCE | 0 | SpiritLeech(1104)[CD] | - | - | relic:NornCrown |
| tyranBossNeurothropeLHE | 0 | SpiritLeech(1104)[CD] | - | - | relic:NornCrown |
| tyranBossNeurothropeSurv | 0 | SpiritLeech(1104)[CD] | - | - | relic:NornCrown |
| tyranBossParasite | 0 | ItItches(1121)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossParasiteCE | 0 | ItItches(1121)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossParasiteLHE | 0 | ItItches(1121)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossParasiteSurv | 0 | ItItches(1121)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossTyrantGuard | 0 | CrushingClaws(1105)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossTyrantGuardCE | 0 | CrushingClaws(1105)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossTyrantGuardLHE | 0 | CrushingClaws(1105)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossWingedPrime | 0 | AlphaWarrior(1112)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossWingedPrimeCE | 0 | AlphaWarrior(1112)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossWingedPrimeLEG | 0 | AlphaWarrior(1112)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossWingedPrimeLHE | 0 | AlphaWarrior(1112)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranBossWingedPrimeSurv | 0 | AlphaWarrior(1112)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranNpc1Hormagaunt | 0 | - | - | - | - |
| tyranNpc1HormagauntGorgon | 0 | - | - | - | - |
| tyranNpc1HormagauntKronos | 0 | - | - | - | - |
| tyranNpc1Hormagaunt_SyncPvp_Gorgon | 0 | - | - | - | - |
| tyranNpc1Hormagaunt_SyncPvp_Kronos | 0 | - | - | - | - |
| tyranNpc2RipperSwarm | 0 | Burrowers(1023)[CD] | - | - | - |
| tyranNpc2RipperSwarmGorgon | 0 | Burrowers(1023)[CD] | - | - | - |
| tyranNpc2RipperSwarmKronos | 0 | Burrowers(1023)[CD] | - | - | - |
| tyranNpc2RipperSwarm_SyncPvp_Gorgon | 0 | Burrowers(1023)[CD] | - | - | - |
| tyranNpc2RipperSwarm_SyncPvp_Kronos | 0 | Burrowers(1023)[CD] | - | - | - |
| tyranNpc3Termagant | 0 | - | - | - | - |
| tyranNpc3TermagantGorgon | 0 | - | - | - | - |
| tyranNpc3TermagantKronos | 0 | - | - | - | - |
| tyranNpc3Termagant_SyncPvp_Gorgon | 0 | - | - | - | - |
| tyranNpc3Termagant_SyncPvp_Kronos | 0 | - | - | - | - |
| tyranNpc4Warrior | 0 | ScythingTalons(1065)[CD] | - | - | - |
| tyranNpc4WarriorCE2Gorgon | 0 | ScythingTalons(1065)[CD] | - | - | - |
| tyranNpc4WarriorCE2Kronos | 0 | ScythingTalons(1065)[CD] | - | - | - |
| tyranNpc4WarriorSurv | 0 | ScythingTalons(1065)[CD] | - | - | - |
| tyranNpc5Barbgaunt | 0 | - | - | - | - |
| tyranNpc5BarbgauntSurv | 0 | - | - | - | - |
| tyranNpc6SporeMine | 0 | - | - | - | - |
| tyranNpcDeathleaper | 0 | FearOfTheUnseen(1115)[CD] | - | - | - |
| tyranNpcMowBiovore | 0 | BioMinefield(1144)[CD]<br>SporeMineLauncher(1145)[CD] | - | - | mythic:HyperCorrosiveAcid |
| tyranNpcNeurothrope | 0 | SpiritLeech(1104)[CD] | - | - | relic:NornCrown |
| tyranNpcOSDeathleaper | 0 | FearOfTheUnseen(1115)[CD] | - | - | - |
| tyranNpcOSNeurothrope | 0 | SpiritLeech(1104)[CD] | - | - | relic:NornCrown |
| tyranNpcOSParasite | 0 | ItItches(1121)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranNpcOSTyrantGuard | 0 | CrushingClaws(1105)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranNpcOSWingedPrime | 0 | AlphaWarrior(1112)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranNpcParasite | 0 | ItItches(1121)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranNpcTyrantGuard | 0 | CrushingClaws(1105)[CD] | - | - | relic:MawClawsOfThyrax |
| tyranNpcWingedPrime | 0 | AlphaWarrior(1112)[CD] | - | - | relic:MawClawsOfThyrax |

### Ultramarines — 25 unites, 3 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| ultraNpc3Intercessor | 1 | - | RapidFire | - | - |
| ultraNpc4HeavyIntercessor | 1 | HellfireShells(1080)[CD] | RapidFire | - | - |
| ultraNpc4HeavyIntercessorSurv | 1 | HellfireShells(1080)[CD] | RapidFire | - | - |
| ultraBossApothecary | 0 | CombatRestoratives(1002)[CD] | - | - | - |
| ultraBossApothecaryLHE | 0 | CombatRestoratives(1002)[CD] | - | - | - |
| ultraBossCalgar | 0 | GauntletsOfUltramar(1000)[CD] | - | - | - |
| ultraBossCalgarLHE | 0 | GauntletsOfUltramar(1000)[CD] | - | - | - |
| ultraBossEliminatorSgt | 0 | MortisRound(1004)[CD] | - | - | - |
| ultraBossEliminatorSgtCamp | 0 | MortisRound(1004)[CD] | - | - | - |
| ultraBossEliminatorSgtLHE | 0 | MortisRound(1004)[CD] | - | - | - |
| ultraBossInceptorSgt | 0 | DeathFromAbove(1003)[CD] | - | - | relic:RelicBoltPistol |
| ultraBossInceptorSgtLHE | 0 | DeathFromAbove(1003)[CD] | - | - | relic:RelicBoltPistol |
| ultraBossTigurius | 0 | StormOfWrath(1019)[CD] | - | - | - |
| ultraBossTiguriusLHE | 0 | StormOfWrath(1019)[CD] | - | - | - |
| ultraBossTitus | 0 | TacticalPrecision(1154)[CD] | - | - | relic:RelicBoltPistol |
| ultraBossTitusLHE | 0 | TacticalPrecision(1154)[CD] | - | - | relic:RelicBoltPistol |
| ultraBossTitusSurv | 0 | TacticalPrecision(1154)[CD] | - | - | relic:RelicBoltPistol |
| ultraNpc1Inceptor | 0 | - | - | - | - |
| ultraNpc2Eliminator | 0 | - | - | - | - |
| ultraNpcApothecary | 0 | CombatRestoratives(1002)[CD] | - | - | - |
| ultraNpcCalgar | 0 | GauntletsOfUltramar(1000)[CD] | - | - | - |
| ultraNpcEliminatorSgt | 0 | MortisRound(1004)[CD] | - | - | - |
| ultraNpcInceptorSgt | 0 | DeathFromAbove(1003)[CD] | - | - | relic:RelicBoltPistol |
| ultraNpcMoWDreadnought | 0 | DutyEternal(1158)[CD]<br>MacroPlasmaIncinerator(1159)[CD] | - | - | mythic:WisdomOfTheAncients |
| ultraNpcTigurius | 0 | StormOfWrath(1019)[CD] | - | - | - |

### WorldEaters — 5 unites, 0 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| worldBossEightboundLHE | 0 | OverwhelmingWrath(1141)[CD] | - | - | relic:TalismanOfRage |
| worldBossExecutionsLHE | 0 | MurderousSwing(1137)[CD] | - | - | relic:TalismanOfRage |
| worldBossJakhalLHE | 0 | JakhalStimms(1131)[CD] | - | - | relic:TalismanOfRage |
| worldBossKharnLHE | 0 | KillMaimBurn(1132)[CD] | - | - | - |
| worldBossTerminatorLHE | 0 | BloodyFury(1129)[CD] | - | - | relic:DaemonfleshPlate |

