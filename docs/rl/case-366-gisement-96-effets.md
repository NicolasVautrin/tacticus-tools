# case-366 -- les 96 `EffectType` que #358 rendait invisibles : inventaire TRANCHE

**Question, en deux temps.** (1) Quels sont, nommement, les `EffectType` que l'inventaire corrige
de #382 fait apparaitre ? (2) Parmi eux, lesquels sont VIVANTS et NON PORTES -- lesquels changent
quelque chose si on les porte ?

**Ce document ne porte rien.** Il TRANCHE : 96 lignes, verdict + porteur + voie. Les ports partent
en taches filles, une par ability.

Probe : `scripts/python/probe_366_inventaire_effets_forme_b.py` (tout est RE-DERIVE du binaire,
rien n'est recopie). Garde : `scripts/python/tests/engine/test_366_effects_registry_partition_offline.py`.

## 1. La cecite, MESUREE (et non racontee)

`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` enregistre **607** fabriques,
reparties en DEUX formes d'appel selon la maniere dont la cle atteint `Dictionary<,>$$Add` :

| forme | comment la cle est passee | nombre |
|---|---|---|
| A | `mov edx, <EffectType>` -- immediat en registre | **511** |
| B | `lea rdx, [rsp+d]` + `mov dword ptr [rsp+d], <EffectType>` -- **par adresse** | **96** |

Le dictionnaire est gshared a cle `ValueType` : IL2CPP passe donc la cle par reference, et le
litteral est en PILE. Rien n'est cache -- il est simplement ailleurs.

**Pourquoi #358 rendait 511.** Ses deux balayages cherchaient l'octet-cle `4c 8b c6` (`mov r8, rsi`,
le chargement du delegate en 3e argument) SUIVI de `BA` (`mov edx, imm32`). Mesure, reproduite a
l'octet pres par `probe_366.legacy_blind_scan` :

```
occurrences de l'octet-cle partage `mov r8, rsi` : 607
retenues (suivies de `mov edx, imm32`)           : 511
rejetees sur le SECOND octet                     : 96
```

Le motif **voyait les 607 sites** et en rejetait 96 sur le second octet. L'accord `511 == 511` de
ses deux balayages etait un accord sur CE rejet. Forme canonique du faux negatif : **deux sources
qui partagent leur cecite s'accordent parfaitement.** La garde exige `legacy == forme A` exactement,
et `occurrences - retenues == 96` : c'est l'ECART entre les deux methodes qui est fige, pas un total.

## 2. Un nom de ctor N'EST PAS un nom de classe

Premiere tentative de typage : lire, dans chaque fabrique `<>c$$<InitializeEffects>b__14_N`, le
`$$.ctor` appele. Elle rend des absurdites -- `5 Fire` -> `FireEffect$$.ctor` (juste), mais
`9 Shrub_BonusDefense` -> `RitesOfBattleExtraDmgImperialEffect$$.ctor` (faux).

Mesure qui tranche, sur les **607** fabriques : **440** slots `Il2CppClass*` distincts pour
seulement **365** noms de `$$.ctor`, dont **51** couvrent PLUSIEURS classes. Champion :
`IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_ResetInitialDmgEffect$$.ctor` porte **13**
classes. C'est la regle CLAUDE.md « l'absence d'une methode dans les tables ne prouve RIEN » vue par
l'autre bout : IL2CPP **deduplique les corps de ctor triviaux**, et la table n'en nomme qu'un
proprietaire.

**L'identite fiable est le slot `Il2CppClass*`** charge dans `rcx` avant `il2cpp_object_new`. Il
donne aussi les GROUPES : `StaticStatModifierEffect` = 63 `EffectType`, `NoneEffect` = 56,
`StatOverrideEffect` = 5.

## 3. Inventaire tranche -- 40 portes, 6 inertes, 50 a porter

### 3.1 DEJA PORTE (40)

**Par `EFFECT_CLASSES` (23)** : `27 Taunted_OnlySpecificTargets`, `78 Terrifying_ExtraDefense`,
`1002/1003 RitesOfBattle_ExtraDmg{Basic,Imperial}`, `1007 PsychicFortress_ExtraBlock`,
`1010 PsychicFortress_DmgReduction`, `1011 RelentlessMarch_Effect`, `1099/1100/1101 Waaagh_*`,
`1106 AstartesBanner_ExtraHit`, `1112 PathOfCommand_ExtraDmg`, `1114 Doom_extraDmg`,
`1169 SereneUnifierSenseOfStone`, `1182 DefenderOfTheGreaterGood_ExtraDmg`,
`1217 GuardianOrganism_DamageReduction`, `1218 Neuroparasite`, `1223 SagaOfTheWarriorBorn_Owner`,
`1244 Contaminated`, `1245 Contaminated_Unit`, `1249 MasterAnnihilator_extraHit`,
`1291 HeavyGravCannon`, `1319 SmashaEad`.

**Par `EFFECT_TRIGGERS` seul (3)** : `5 Fire`, `1180 InspiredToGreatness_OverrideLevel`,
`1186 TimeFlux_Revive`.

**Par une AUTRE voie du port (14)** -- c'est le piege du croisement : se limiter aux deux registres
aurait classe ces 14 en « non portes ».

| id | nom | ou le port le traite |
|---|---|---|
| 0 | BlockEnteringUnits | `entities/pathfinding/tile_blocking.py`, `walk_pathfinder.py`, `services/static_battle_rules.py`, gate `playbook/prediction/normal_attack.py` |
| 10 | FirstAidHeal | `runner/operations/triggers/tiles.py` (ability + trigger de l'effet) |
| 11 | Thorns_DefenseReduction | `utilities/tile.py`, `runner/damage_model.py`, `runner/operations/spawn.py` |
| 17 | Ice | `ICE_TILE` : `abilities/spacewolves.py`, `abilities/loki/stormcaller.py`, `triggers/loki/anvil_shield.py`, `triggers/loki/lord_of_tempests.py`, `runner/damage_model.py` |
| 25 | Taunted_BlockMovement | sous-effet du composite `TauntedEffect`, `entities/effects/loki/status.py` |
| 26 | Taunted_CantUseAbility | idem (+ `battle_query.py`) |
| 103 | FriendlyFire | `runner/abilities/targeting.py` |
| 1001 | Narthecium_Revive | `runner/operations/triggers/loki/narthecium.py` |
| 1068 | RelentlessMarch_DangerZone | `runner/operations/triggers/loki/relentless_march.py` |
| 1098 | RammingSpeed_ExtraExplode | `runner/operations/triggers/loki/death_nova.py` |
| 1237 | Taunted_RefreshUnitTurnFinished | sous-effet du composite `TauntedEffect` |
| 1242 | GalvanicField_DmgOverride | `runner/abilities/repair.py` (`AddStatOverrideEffect`) |
| 1274 | MoltenForm | face DECISION seule : `MoltenForm_TilesUtility` (`utilities/tile.py`) -- la classe d'effet `MoltenFormEffect$$CreateDamageDefenseModifier` reste NON portee |
| 1279 | Phantasm | face DECISION seule : `Phantasm_AvoidFriendlyPhantasmUtility` -- `PhantasmEffect$$CreateEffectDamageMalusForDefense` reste NON portee |

### 3.2 INERTE DEMONTRE (6) -- fabrique = `NoneEffect`

`1176 SereneUnifierSenseOfStone_Visual`, `1177 SereneUnifierZephyrsGrace_Visual`,
`1178 SereneUnifierStormOfFire_Visual`, `1179 StormboyzStrike_AlreadyUsedTile`,
`1266 WeakerRearArmourOwner`, `1273 TheWrathOfKhaineUnleashed_PendingTarget`.

Les six partagent le slot de `IdunBattle.Entities.Effects.NoneEffect` -- la classe que
`EffectsDatabase$$GetEffect` construit deja quand une fabrique MANQUE. **Le port retombe sur
`BaseEffect` (no-op) : comportement IDENTIQUE au natif.** Rien a porter cote classe. Ce qui compte
pour eux est la face TRIGGER/condition (un marqueur se LIT), hors perimetre « classe d'effet ».

### 3.3 A PORTER (50)

Deux axes INDEPENDANTS, qui se croisent -- ne pas additionner G1 avec G2/G3 :

* axe **FABRIQUE** : G1 = instance generique (11) / le reste = classe bespoke (39) ;
* axe **PORTEUR** : G2 = aucun porteur d'unite (21) / G3 = porteur confrontable (28) /
  `31 StatModifier` = poseur NON TRANCHE par ce cas (1). **21 + 28 + 1 = 50.**

#### G1 -- instance GENERIQUE `StaticStatModifierEffect`, patron etabli (11)

`31 StatModifier`, `1004/1005/1006 MightOfHeroes_{ExtraHits,ExtraDamage,ExtraArmor}`,
`1103 KanOpener_ReduceArmor`, `1171 SereneUnifierStormOfFire`,
`1251/1256 UnbreakableDuty_{Health,Damage}`, `1351/1352/1507 EnvStatBoost_{Damage,Health,Armor}`.

Meme slot que `1099 Waaagh_ExtraMovement`, `1434 ThrillSeekers`, `1205/1206/1207 RealityUnbound_*`,
`1342 BlackRage_ExtraMove`, `1202 AnvilShield_AdditionalBlock` -- **tous deja au registre** (le slot
en compte 63 au total). Le patron est donc etabli, et
l'enjeu du port n'est PAS le calcul : c'est l'ATTRIBUTION PAR SOURCE. Declare, l'effet fait poser sa
`ValueModification` par-source, donc son EXPIRATION la retire (#118) ; non declare, la stat-mod du
seed reste a vie. Trancher a-t-il un porteur est donc secondaire pour ce groupe -- ce qui compte est
la duree.

> **TRAITE par #371 -- `docs/rl/case-371-g1-static-stat-modifier.md`** (table RE complete : poseur,
> stat, montant, `turns`, pour les 11). **3 inscrits** : `1171 SereneUnifierStormOfFire` (`tauAunShi`,
> le SEUL des onze a porter un vrai timer -- `TurnsFromRounds(1)`), `1251/1256 UnbreakableDuty_*`
> (`templAncient`, `turns` NULL donc PERMANENTS : leur inscription ferme l'ATTRIBUTION, pas une duree).
> **8 non inscrits**, avec la raison : `1004/1005/1006 MightOfHeroes_*` DEAD (ability absente du
> gameconfig -> magnitude irresoluble, un port serait inerte), `1103 KanOpener_ReduceArmor` 0 porteur,
> `1351/1352/1507 EnvStatBoost_*` environnement ET magnitude CONTEXTUELLE (`PercentageOf(StatAmount(
> <stat>, part 3), GetNumberConstant(<cle>))`, forme OVERRIDE), `31 StatModifier` toujours non tranche
> (mais les 6 chemins de pose sont inventories et les 2 non-litteraux elimines -- case-371 §5).

#### G2 -- vivant en binaire, AUCUN porteur d'unite (21)

Aucun de ces effets n'a de porteur au catalogue d'unites (`unit_map`, 5 voies) ; l'ability est soit
absente du gameconfig (DEAD), soit presente sans porteur, soit une ability d'ENVIRONNEMENT.

| id | nom | statut du poseur |
|---|---|---|
| 6 | Electrified_CounterAttack | TUILE (`ElectrifiedMeleeCounterAttackEffect$$GetAttackBehaviour`) |
| 9 | Shrub_BonusDefense | TUILE (`ShrubBonusDefenseAbility$$CreateBehaviour`) |
| 18 | BrokenIceBlocker | TUILE (`BrokenIceAbility$$CreateBehaviour`, `BrokenIceBlockerEffect$$ApplyInternal/RevertInternal`) |
| 35 | DryBush_DefenseBonus | TUILE -- ⚠ porte `DryBush_DefenseBonusEffect$$CreateEffectDamageBonusForAttack`, canal DEGAT non porte (le port n'a mesure que la face UTILITE : `DryBush` n'heberge que `LightCover`) |
| 58 | Darkness | TUILE (`DarknessEffect`) |
| 77 | BurnedByLight_ExtraDmg | TUILE (`BurnedByLightExtraDamageEffect$$CreateEffectDamageBonusForAttack`) |
| 91 | Vines_BlockMovement | TUILE (classe partagee avec `Taunted_BlockMovement`) |
| 94 | LandMine_BlockTileMovement | TUILE (`LandMineAbility$$CreateBehaviour`) |
| 1004/1005/1006 | MightOfHeroes_* | **DEAD** : `MightOfHeroesAbility$$ExecuteBehaviour` existe en binaire, l'ability est ABSENTE du gameconfig |
| 1102 | KanOpener_IgnoreArmor | ability au gameconfig, **0 porteur** (cf. 4.) |
| 1103 | KanOpener_ReduceArmor | idem |
| 1104 | SmashaSquigJaws_CounterAttack | **DEAD** : `SmashaSquigJawsAbility$$GetEffectType` en binaire, ability ABSENTE du gameconfig |
| 1105 | Dakka_ExtraHits | **DEAD** : `DakkaAbility$$GetEffectType` en binaire, ability `Dakka` ABSENTE du gameconfig. ⚠ `DakkaDakkaDakka` (`orksKillaKan`) est une ability DIFFERENTE (`DakkaDakkaDakkaAbility`, 18 symboles) -- ne pas les confondre |
| 1265 | WeakerRearArmourTile | ability au gameconfig, **0 porteur** |
| 1311 | EnvArmourSuppliedArmourBuff | ENVIRONNEMENT (`EnvArmourSuppliesAbility$$CreateBehaviourForTargets`) |
| 1351/1352/1507 | EnvStatBoost_* | ENVIRONNEMENT (`BaseStatBoostAbility$$CreateBehaviour`), aussi en G1 |
| 1513 | TheWrathOfKhaineUnleashedRework_PendingAttack | ability au gameconfig, **0 porteur** |

⚠ **Un zero d'`unit_map` n'est pas une preuve de mort** (#323). Ce qui le rend opposable ici, c'est
la DEUXIEME source : la presence/absence de l'ability dans `gameconfig`. Les huit TUILES, elles, ne
sont pas mortes du tout -- leur poseur est le SETUP de board, pas une unite : la voie de
confrontation est **un board qui porte la tuile**, jamais un roster.

#### G3 -- A PORTER, porteur CONFRONTABLE (28)

Pool spawnable relu au rank courant : **97** unites.

| id | nom | ce que fait la classe | porteur | voie |
|---|---|---|---|---|
| 1000 | ShockAssault_Buff | (classe propre, corps de ctor fondu) | `ultraInceptorSgt` | HERO, pool |
| 1014 | CamoCloak_DmgReduction | `CreateDamageModifier` + `CreateActiveCondition` | `ultraEliminatorSgt` | HERO, pool (+ summon `ultraSmnEliminator`) |
| 1107 | PathOfCommand_ExtraCrit | `GetDynamicStatModificationAmount` + `CreateTargetSelector` (axe CRIT) | `eldarAutarch` | HERO, pool -- **residu deja NOMME** dans `factory.py` |
| 1108 | ReinforcedHiveNode_ExtraArmor | (classe propre) | `tyranSmnWarrior` | SUMMON (via son summoner) |
| 1109 | ReinforcedHiveNode_ExtraBlock | `CreateActiveCondition` | `tyranSmnWarrior` | SUMMON |
| 1110 | FireAndReposition_ReduceDmg | `CreateEffectDamageMalusForDefense` | `eldarRanger` | HERO, pool |
| 1111 | WireweaveNet_CounterAttack | (classe propre) | `eldarRanger` | HERO, pool |
| 1113 | TunnelingHorror_PendingSummon | marqueur de summon pending | `necroSmnDestroyer` | SUMMON |
| 1115 | InescapableAccuracy_extraCritChance | (classe propre, ctor fondu avec 1116) | `eldarMauganRa` | HERO, pool |
| 1116 | InescapableAccuracy_extraCritDmg | idem | `eldarMauganRa` | HERO, pool |
| 1117 | InescapableAccuracy_overrideHits | idem | `eldarMauganRa` | HERO, pool |
| 1171 | SereneUnifierStormOfFire | `StaticStatModifierEffect` (phase 3 du cycle ; phase 1 = `1169`, portee) | `tauAunShi` | HERO, pool |
| 1174 | StructuralAnalyser_Visual | `CreateActiveCondition` | `tauDarkstrider` | HERO, pool |
| 1175 | HatefulAssault_AlreadyAttacked | `UntilOfEndTurnEffect` (marqueur a duree) | `blackTerminator` | HERO, pool |
| 1181 | ExemplarOfTheKauyon_AdditionalHits | COUPS | `tauShadowsun` | HERO, pool |
| 1183 | DefenderOfTheGreaterGood_ExtraHits | `CreateEffectHitsBonusForAttack` + `CreateTargetSelector` | `tauShadowsun` | HERO, pool -- **residu deja NOMME** (+ jumeaux drone 1306/1307) |
| 1215 | PsychicStalk_ExtraAttackDamage | `CreateEffectDamageMalusForDefense` | `thousAhriman` | HERO, pool |
| 1216 | PsychicStalk_VisualEffect | `CreateActiveCondition` + `CreateTargetSelector` | `thousAhriman` | HERO, pool |
| 1222 | WarHowl_ExtraDamage_Unstoppable | `CreateEffectDamageBonusForAttack` + `CreateCritChanceBonus` + `ApplyInternal`/`RevertInternal` | `spaceBlackmane` | HERO, pool |
| 1224 | SagaOfTheWarriorBorn_OtherSpaceWolves | MEME classe que `1223` (portee) : `CreateCritDamageBonus` + `CreateEffectHitsBonusForAttack` | `spaceBlackmane` | HERO, pool -- **residu deja NOMME** (`effects/loki/hits.py`) |
| 1227 | HarlequinsPanoply_IgnoreHits | (classe propre) | `eldarSmnHarlequin` | SUMMON |
| 1251 | UnbreakableDuty_Health | `StaticStatModifierEffect` | `templAncient` | HERO, pool |
| 1255 | MartialSuperiority_Visual | `CreateActiveCondition` -- deja documente `: BaseEffect` cote port | `templChampion` | HERO, pool |
| 1256 | UnbreakableDuty_Damage | `StaticStatModifierEffect` | `templAncient` | HERO, pool |
| 1284 | EchoesFromTheWarp_Revive | MEME classe que `1186 TimeFlux_Revive` (portee) -- un REVIVE | `thousNpc4Terminator` (npc SEUL) | GREFFE npc (`case-92` 5bis) : un revive ne lit ni stats ni traits du caster |
| 1345 | VisionsOfHeresy_ExtraPierceMelee | axe PERCAGE | `bloodDeathCompany` | HERO, pool |
| 1346 | VisionsOfHeresy_ExtraPierceRanged | axe PERCAGE | `bloodDeathCompany` | HERO, pool |
| 1435 | PsychicStalk_FriendlyChaosExtraDamage | `CreateEffectDamageBonusForAttack` | `thousAhriman` | HERO, pool |

## 4. Le residu que ce cas FERME, sans le porter

`scripts/python/engine/entities/effects/factory.py` porte, depuis longtemps, la ligne :

```python
    # KanOpener : nom d'EffectType à confirmer avant inscription.
```

La classe `KanOpenerEffect` EXISTE cote port (`entities/effects/loki/hits.py`) ; **seul le nom
manquait**, et il manquait parce que #358 rendait ces `EffectType` « non enregistres ». Les voici :

* **`1102 KanOpener_IgnoreArmor`** -- classe propre `IdunBattleLogic.Entities.Abilities.Triggered.Loki.KanOpenerEffect` (slot dedie),
  c'est celle que le port a deja ecrite ;
* **`1103 KanOpener_ReduceArmor`** -- instance generique `StaticStatModifierEffect`.

⚠ L'inscription ne change RIEN a une bataille tant qu'aucune unite ne porte l'ability : `KanOpener`
existe au gameconfig mais a **0 porteur** sur les 5 voies. C'est le point que le commentaire du port
ne pouvait pas trancher -- et `orksKillaKan` porte `DakkaDakkaDakka`, pas `KanOpener`.

## 5. Ce qui n'est PAS couvert par ce cas

* **Aucun port.** Les 28 de G3 sont des taches filles, une par ability.
* **Le typage des classes bespoke n'est pas relu au decompile** : il vient du slot `Il2CppClass*`
  (identite) et des methodes `Create*` presentes dans la table (contribution). Une methode ABSENTE
  ne prouve rien (corps fondus) -- la colonne « ce que fait la classe » est donc un plancher, jamais
  un plafond.
* **La confrontabilite des 8 effets de TUILE** (G2) n'est pas etablie board par board : elle exige
  de recenser quels boards portent Shrub / DryBush / Vines / LandMine / BrokenIce / Darkness.
* **`31 StatModifier` : QUI le pose n'est pas tranche.** C'est la cle « anonyme » du nOEud DSL
  `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect` ; le balayage d'immediat
  n'est PAS discriminant a cette valeur (un immediat n'est pas type, et 31 est partout). Il faut un
  autre angle -- p. ex. lire les arbres DSL qui passent 31 en argument.
  ⚠ **Champ REDUIT par #371** (case-371 §5) : les SIX chemins de pose sont inventories par xrefs, et
  les deux seuls ou l'`effectType` n'est pas un litteral (`APowerUpAbility$$AddAbsoluteBoost` /
  `$$AddPctBasedBoost`, qui lisent un champ de record) sont ELIMINES -- leurs trois implementations
  concretes portent `0x473`/`0x477`/`0x475`. Reste a balayer les ~60 call-sites litteraux.
* **Aucune mesure live** : ce cas est 100 % offline (binaire + tables versionnees + gameconfig).
