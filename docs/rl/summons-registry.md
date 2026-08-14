# Registre des unites `summons` — kit complet et etat des DEUX FACES

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

- Unites `summons` : **65** ; kits sans manque : **34** ; kits avec du travail : **31**
- Actives distinctes : **16** — `[--]` **1** · `[C-]` **6** · `[CD]` **9**
- Passifs distincts : **47** — portes **21**, non portes **26**
- Traits de kit distincts (AUCUN ecarte — le seuil de frequence a disparu avec #1015) :
  **43** — couverts **41**, non couverts **2**

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
| trait | InstinctiveBehaviour | 5 | tyranSmnBarbgaunt, tyranSmnHormagaunt, tyranSmnRipperSwarm |
| passif | FlamesOfMutation | 2 | thousSmnBlueHorror, thousSmnBlueHorrorHSE |
| passif | Split | 2 | thousSmnPinkHorror, thousSmnPinkHorrorHSE |
| trait | TwoManTeam | 2 | astraSmnLascannon, astraSmnMortar |
| active | PrecisionShot | 1 | necroSmnDeathmark |
| passif | AdrenalGlands | 1 | tyranSmnHormagaunt |
| passif | AllIsDust | 1 | thousSmnRubricMarine |
| passif | BattleFocus | 1 | eldarSmnGuardian |
| passif | CallInReinforcements | 1 | astraSmnVoxcaster |
| passif | CursedOfTheWalkingPox | 1 | deathPoxwalker |
| passif | DeathwingKnight | 1 | darkaSmnTerminator |
| passif | DrawFire | 1 | blackSmnTerminator |
| passif | FiringPosition | 1 | blackSmnHavoc |
| passif | FragLance | 1 | astraSmnDeathRider |
| passif | HailOfLivingAmmunition | 1 | tyranSmnTermagant |
| passif | HunterOfSouls | 1 | thousSmnDaemonPrince |
| passif | Hypermorph | 1 | genesSmnAberrant |
| passif | Lifewards | 1 | adeptSmnGeminaeSuperia |
| passif | MischiefMakers | 1 | deathSmnNurglings |
| passif | NoHidingFromTheWatchers | 1 | darkaSmnWatcher |
| passif | PileIn | 1 | orksGrot |
| passif | Pyreblaster | 1 | templInitiatePyreblaster |
| passif | RapidFire | 1 | ultraSmnHeavyIntercessor |
| passif | RedThirst | 1 | bloodSmnIntercessor |
| passif | RepairEnthusiast | 1 | votanSmnEcog |
| passif | Shrapnel | 1 | astraSmnMortar |
| passif | SynapticInsight | 1 | tyranSmnBarbgaunt |
| passif | VengeanceForTheOmnissiah | 1 | admecSmnTechpriest |
| passif | WatchedOver | 1 | darkaSmnWatcher |

## Faces DECISION ouvertes sur des actives EXECUTEES (6)

Ces abilities s'executent fidelement mais sont CHOISIES avec un scoring qui n'est pas celui
du natif. Aucun compteur de manque ne les voit — elles ne sont pas des items absents, ce
sont des **faces** absentes d'items presents.

`Burrowers`, `KissOfDeath`, `SlashingDive`, `TunnelingHorror`, `ValkyrieStrike`, `WallOfMirrors`

## Inventaire complet, par faction

### AdeptusAstartes — 1 unites, 0 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| astarSmnHaywireMine | 0 | - | - | - | - |

### AdeptusMechanicus — 3 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| admecSmnTechpriest | 1 | - | VengeanceForTheOmnissiah | - | - |
| admecSmnElectropriest | 0 | - | - | - | - |
| admecSmnVanguard | 0 | - | - | - | - |

### Aeldari — 2 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| eldarSmnGuardian | 1 | PlasmaGrenade(1098)[CD] | BattleFocus | - | - |
| eldarSmnHarlequin | 0 | KissOfDeath(1108)[C-] | - | - | - |

### AstraMilitarum — 6 unites, 4 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| astraSmnMortar | 2 | - | Shrapnel | TwoManTeam | - |
| astraSmnDeathRider | 1 | - | FragLance | - | - |
| astraSmnLascannon | 1 | - | - | TwoManTeam | - |
| astraSmnVoxcaster | 1 | ValkyrieStrike(1018)[C-] | CallInReinforcements | - | - |
| astraSmnGuardsman | 0 | - | - | - | - |
| astraSmnKell | 0 | - | - | - | - |

### BlackLegion — 4 unites, 2 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| blackSmnHavoc | 1 | - | FiringPosition | - | - |
| blackSmnTerminator | 1 | - | DrawFire | - | - |
| blackSmnBloodletter | 0 | - | - | - | - |
| blackSmnBloodletterHSE | 0 | - | - | - | - |

### BlackTemplars — 4 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| templInitiatePyreblaster | 1 | - | Pyreblaster | - | - |
| templInitiate | 0 | DevoutPush(1053)[CD] | - | - | - |
| templNeophyte | 0 | IncendiaryShells(1044)[CD] | - | - | - |
| templSmnAggressor | 0 | Fragstorm(1078)[CD] | - | - | - |

### BloodAngels — 1 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| bloodSmnIntercessor | 1 | - | RedThirst | - | - |

### DarkAngels — 4 unites, 2 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| darkaSmnWatcher | 2 | - | NoHidingFromTheWatchers, WatchedOver | - | - |
| darkaSmnTerminator | 1 | - | DeathwingKnight | - | - |
| darkaSmnHellblaster | 0 | - | - | - | - |
| darkaSmnInfiltrator | 0 | - | - | - | - |

### DeathGuard — 2 unites, 2 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| deathPoxwalker | 1 | - | CursedOfTheWalkingPox | - | - |
| deathSmnNurglings | 1 | - | MischiefMakers | - | - |

### Genestealers — 4 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| genesSmnAberrant | 1 | - | Hypermorph | - | - |
| genesSmnDecoy | 0 | - | - | - | - |
| genesSmnGenestealer | 0 | - | - | - | - |
| genesSmnNeophyte | 0 | - | - | - | - |

### LeaguesOfVotann — 2 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| votanSmnEcog | 1 | - | RepairEnthusiast | - | - |
| votanSmnSteeljack | 0 | - | - | - | - |

### Necrons — 4 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| necroSmnDeathmark | 1 | PrecisionShot(1015)[--] | - | - | - |
| necroSmnDestroyer | 0 | TunnelingHorror(1011)[C-] | - | - | - |
| necroSmnSwarm | 0 | ScarabSummon(1047)[CD] | - | - | - |
| necroSmnWarrior | 0 | - | - | - | - |

### Orks — 4 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| orksGrot | 1 | - | PileIn | - | - |
| orksGrotTank | 0 | - | - | - | - |
| orksOrkBoys | 0 | Stikkbomb(1051)[CD] | - | - | - |
| orksSmnSquig | 0 | - | - | - | - |

### Sisterhood — 2 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| adeptSmnGeminaeSuperia | 1 | - | Lifewards | - | - |
| adeptSmnBattleSister | 0 | - | - | - | - |

### Tau — 4 unites, 0 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| tauSmnDroneCommandLink | 0 | - | - | - | - |
| tauSmnDroneShield | 0 | - | - | - | - |
| tauSmnDroneSniper | 0 | - | - | - | - |
| tauSmnStealthSuit | 0 | ForwardObservers(1185)[CD]<br>WallOfMirrors(1186)[C-] | - | - | - |

### ThousandSons — 8 unites, 6 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| thousSmnBlueHorror | 1 | - | FlamesOfMutation | - | - |
| thousSmnBlueHorrorHSE | 1 | - | FlamesOfMutation | - | - |
| thousSmnDaemonPrince | 1 | - | HunterOfSouls | - | - |
| thousSmnPinkHorror | 1 | - | Split | - | - |
| thousSmnPinkHorrorHSE | 1 | - | Split | - | - |
| thousSmnRubricMarine | 1 | - | AllIsDust | - | - |
| thousSmnScreamer | 0 | SlashingDive(1091)[C-] | - | - | - |
| thousSmnScreamerHSE | 0 | SlashingDive(1091)[C-] | - | - | - |

### Tyranids — 6 unites, 5 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| tyranSmnBarbgaunt | 2 | - | SynapticInsight | InstinctiveBehaviour | - |
| tyranSmnHormagaunt | 2 | - | AdrenalGlands | InstinctiveBehaviour | - |
| tyranSmnTermagant | 2 | - | HailOfLivingAmmunition | InstinctiveBehaviour | - |
| tyranSmnRipperSwarm | 1 | Burrowers(1023)[C-] | - | InstinctiveBehaviour | - |
| tyranSmnSporeMine | 1 | - | - | InstinctiveBehaviour | - |
| tyranSmnWarrior | 0 | ScythingTalons(1065)[CD] | - | - | - |

### Ultramarines — 4 unites, 1 avec du travail

| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |
|---|---:|---|---|---|---|
| ultraSmnHeavyIntercessor | 1 | HellfireShells(1080)[CD] | RapidFire | - | - |
| ultraSmnDreadnought | 0 | - | - | - | - |
| ultraSmnEliminator | 0 | - | - | - | - |
| ultraSmnInceptor | 0 | - | - | - | - |

