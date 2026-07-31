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
| 1107 | PathOfCommand_ExtraCrit | `GetDynamicStatModificationAmount` + `CreateTargetSelector` (axe CRIT) | `eldarAutarch` | HERO, pool -- **PORTE (#373)**, cf. §3.3bis |
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
| ~~1183~~ | ~~DefenderOfTheGreaterGood_ExtraHits~~ | **PORTE par #372** (avec les jumeaux drone 1306/1307) -- `docs/rl/case-372-dotgg-extra-hits.md` | `tauShadowsun` | HERO, pool |
| 1215 | PsychicStalk_ExtraAttackDamage | `CreateEffectDamageMalusForDefense` | `thousAhriman` | HERO, pool |
| 1216 | PsychicStalk_VisualEffect | `CreateActiveCondition` + `CreateTargetSelector` | `thousAhriman` | HERO, pool |
| ~~1222~~ | ~~WarHowl_ExtraDamage_Unstoppable~~ | **PORTE par #366-r1** -- `docs/rl/case-366-r1-war-howl-extra-damage.md`. Les TROIS artefacts annonces existent et tombent dans TROIS canaux : `CreateEffectDamageBonusForAttack` (additif per-coup) et `CreateCritChanceBonus` (**canal neuf** -- `create_effect_crit_chance_bonus_for_attack` n'avait AUCUN contexte cote port) sont portes ; `ApplyInternal`/`RevertInternal` = `AddTrait`/`RemoveTrait(0x412 = 1042 Unstoppable, isTemporary)`, deja LU par le substrat d'entite, POSE non portee (attend l'ability 1106) | `spaceBlackmane` (poseur) -> lui-meme + tout ami MELEE non-Summon (recu par `spaceWulfen`/`spaceHound`, PAS par `spaceRockfist`/`spaceStormcaller`) | HERO, pool |
| ~~1224~~ | ~~SagaOfTheWarriorBorn_OtherSpaceWolves~~ | **PORTE par #366-r1** -- `docs/rl/case-366-r1-saga-other-space-wolves.md`. « MEME classe que `1223` » est CONFIRME au slot `Il2CppClass*` (`0x1833a1190`, 2 ids sur 607, fabriques bit-identiques) : le port pointe LA MEME classe depuis les deux entrees | `spaceBlackmane` (poseur) -> les 4 autres Space Wolves du pool (receveurs) | HERO, pool |
| 1227 | HarlequinsPanoply_IgnoreHits | (classe propre) | `eldarSmnHarlequin` | SUMMON |
| 1251 | UnbreakableDuty_Health | `StaticStatModifierEffect` | `templAncient` | HERO, pool |
| 1255 | MartialSuperiority_Visual | `CreateActiveCondition` -- deja documente `: BaseEffect` cote port | `templChampion` | HERO, pool |
| 1256 | UnbreakableDuty_Damage | `StaticStatModifierEffect` | `templAncient` | HERO, pool |
| 1284 | EchoesFromTheWarp_Revive | MEME classe que `1186 TimeFlux_Revive` (portee) -- un REVIVE | `thousNpc4Terminator` (npc SEUL) | GREFFE npc (`case-92` 5bis) : un revive ne lit ni stats ni traits du caster |
| ~~1345~~ | ~~VisionsOfHeresy_ExtraPierceMelee~~ | **PORTE par #366-r1** (avec `1346`) -- `docs/rl/case-366-r1-visions-of-heresy-pierce.md` | `bloodDeathCompany` | HERO, pool |
| ~~1346~~ | ~~VisionsOfHeresy_ExtraPierceRanged~~ | idem -- MEME classe native, le `statType` de la pose est le seul discriminant | `bloodDeathCompany` | HERO, pool |
| 1435 | PsychicStalk_FriendlyChaosExtraDamage | `CreateEffectDamageBonusForAttack` | `thousAhriman` | HERO, pool |

### 3.3ter -- `1345`/`1346 VisionsOfHeresy_ExtraPierce{Melee,Ranged}` : PORTES (#366-r1)

UNE SEULE classe native pour les deux ids -- tranche par le **slot `Il2CppClass*`** (identique pour
les deux, et DISTINCT de celui de `StaticStatModifierEffect`), pas par le nom du ctor. Le
discriminant melee/ranged est le `statType` que passe le poseur
`...VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour` : `0x15 = 21 EXTRA_PIERCE_MELEE` pour
`1345`, `0x16 = 22 EXTRA_PIERCE_RANGED` pour `1346`, MEME montant
(`ConfigVar(0x3f = extraPierceRatio)`), `turns = NULL`.

**Canal = la STAT**, lue par `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio`
(`GetStat(attacker, isMelee ? 0x15 : 0x16)`) -- ni `EffectBonus.ForPiercing`, ni groupe #179.
Active-condition `HealthPctIsBelowOrEqual(Owner, ConfigConst(0x4f = healthPct) = 50)`, donc ABSENTS
du canal `decisionView` ACTIF-ONLY tant que Lucien est au-dessus du seuil : ils entrent par
`ABILITY_INIT_OWNER_EFFECTS["VisionsOfHeresy"]`. Detail, mesures et mutations :
`docs/rl/case-366-r1-visions-of-heresy-pierce.md`.

### 3.3quater -- `1222 WarHowl_ExtraDamage_Unstoppable` : PORTE (#366-r1)

TROIS artefacts, TROIS canaux -- et c'est la lecon transferable de ce cas : la fiche d'inventaire
donne les NOMS des methodes, pas les canaux. Ici, `CreateEffectDamageBonusForAttack` tombe dans un
canal deja branche (additif per-coup, gate `IsMeleeAttack & IsNormalAttack`) ; `CreateCritChanceBonus`
tombe dans un canal **AVEUGLE** (`create_effect_crit_chance_bonus_for_attack(self)` ne prenait AUCUN
argument, alors que son quatrieme noeud est
`AmountIsGreaterThanZero(StatAmount(Caster, 0x9 CriticalChance, StatPart.Current))`) -- il a fallu y
threader le contexte au foyer `AttackDamageOperation._crit_params`, symetrique exact du residu `N14`
du canal crit-DEGAT ; `ApplyInternal`/`RevertInternal` ne tombent dans AUCUN canal d'effet : ce sont
`AddTrait`/`RemoveTrait(0x412 = 1042 UnitTrait.Unstoppable, isTemporary: 1)`, dont la LECTURE passe
deja par le substrat d'entite (`combatSnapshot.units[].traits`, MESURE : `u81` gagne 1042 au cast) et
dont la POSE attend l'ability 1106.

Le ctor lit `mov edx, 0x452` -> surcharge **ACTIVE** d'`op_Implicit` (tranchee par l'ADRESSE) =
`ActiveAbilityType.WarHowl` 1106. Classe DEDIEE : slot `Il2CppClass*` `0x1833908e8` unique, et un
seul appelant du `$$.ctor` parmi les 607 fabriques. Mesures, vues rouges et residus (#382 mesure a
**+177 par coup**) : `docs/rl/case-366-r1-war-howl-extra-damage.md`.

### 3.3bis -- `1107 PathOfCommand_ExtraCrit` : PORTE (#373)

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandAbility$$CreateBehaviour` pose
**deux** `IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffectToOwner`, et c'est le
2e argument (`statType`) qui separe les deux axes :

    AddDynamicStatModifierEffectToOwner( 0x453 = 1107, statType = 0x9 = CritChance, null, false )
  & AddDynamicStatModifierEffectToOwner( 0x458 = 1112, statType = 0x0 = Attack,     null, false )

-> `1107` porte une **chance de critique**, pas un multiplicateur de degat critique (aucun
`statType 0xa`). L'asymetrie interne du kit est donc fermee.

**Le noeud discriminant** (que le jumeau ATTACK n'a pas) --
`...PathOfCommandExtraCritEffect$$CreateTargetSelector` :

    UnitsWithStatBiggerThan(
        SurroundingFriends(Owner, GetNumberConstant(0x16 = range), unique, OnlyAliveAndTargetable),
        statType = 0x9, statPart = 0x0 = Current, amount = <DSLFormulas+0x18> = Constant(0),
        excludingEffect = true )

`IdunBattle.Entities.Selectors.UnitsWithStatBiggerThanSelector$$Select` garde l'unite si
`GetStat(Current) - GetStat(part 5, source = CET effet) > 0`. **Un allie a portee dont la chance de
crit est nulle n'est PAS cible.** (Le champ `+0x18` de `DSLFormulas` est le `Constant(0)` ecrit par
`IdunBattleLogic.Entities.DSLFormulas$$.ctor` ; +0x20/+0x28/+0x30/+0x38 y valent 1/2/100/-1.)

**Magnitude** -- `...$$GetDynamicStatModificationAmount` =
`ConfigVar(TriggeredAbilityType.PathOfCommand = 0x458, EffectSource(Get(effect)),
AbilityVariableType.extraCritChance = 0x41)`, surcharge
`IdunBattleLogic.Entities.DSLFormulas$$ConfigVar(this, abilityType, unit, variableType)` (tranchee
par ses xrefs entrantes, pas a l'oeil) -> `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` ->
`GetVariableForLevel`. Indexee sur l'`AbilityState` de la **SOURCE**. `extraCritChance` n'est pas
dans `variablesAffectedByRarityBonus` de `PathOfCommand` -> aucun scaling de rarete
(`extraCritChance[L1] = 15`, `[L50] = 20`). Pas de gate de faction ici : le
`If(IsSameFaction(...))` est propre au jumeau ATTACK.

**Canal de port** = l'aura stat-mod **PROJETEE** (`runner/operations/aura_stat_mods.py`, interface
`aura_stat_modification_stat/_amount/_targets`), la meme que `LionHelm` -- et **pas** un canal de
lecture `create_aura_*`. Raison : sur l'axe ATTACK le canal de lecture existe parce que la chaine de
PREDICTION re-positionne l'attaquant sur une tuile CANDIDATE (#153) ; l'axe CRIT n'a pas cet usage
(sa seule lecture numerique est `GetStat(9)` dans `_crit_params`, a la position reelle), donc un
canal de lecture y aurait ete un gate MORT. Trois cablages : attribution au SEED
(`attribute_aura_stat_modifiers`), re-evaluation au MOUVEMENT (`refresh_aura_stat_modifiers`), et
-- ajoute par #373 -- **a la POSE de l'owner-effect** (`land_deep_strike`), sans quoi
l'atterrissage d'un deep-strike posait l'effet chez le porteur sans rien projeter.

**GROUND TRUTH LIVE** (runner MC1_67 / seed 31337, `eldarAutarch` ablvl 50, event stream de
l'atterrissage) :

    [Effect_Refresh e=101 <<PathOfCommand_ExtraCrit>>]
      ActivateEffect e=83 ; ReceiveEffect e=85 ; ChangeStats e=85 CritChance_Modification_Change=20
    [Effect_Refresh e=102 <<PathOfCommand_ExtraDmg>>]
      ActivateEffect e=83 ; ReceiveEffect e=85 ET e=87 ; ChangeStats e=85 ET e=87 Attack +699

`eldarFarseer` (u87), a la MEME portee, recoit le +699 d'Attack et **rien** en crit : son
`CritChance` de base est 0 (la normalisation `buildNormalizedBC` met le crit a 0 partout ; on
remonte celui du Ranger par `--unit-stat eldarRanger:CritChance=20`). Le gate est donc exerce par
la CHANCE DE CRIT, pas par la distance. Mesure : `probe_373_path_of_command_extra_crit.py` ;
garde : `tests/engine/runner/test_path_of_command_crit_aura_live.py`.

**Residus nommes** : (a) `...PathOfCommandEffect$$CreateActiveCondition = IsTargetable(Owner)`
n'est pas porte -- meme regime que le jumeau 1112 deja livre ; (b) le natif re-evalue le selecteur
sur `RefreshEffectTrigger.EffectsChanged` aussi, le port ne le fait qu'au mouvement et a la pose :
un allie dont la chance de crit passe de 0 a >0 en cours de bataille (ex. `ActOfFaith`) n'entre
dans l'aura, cote port, qu'au prochain deplacement.

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
* ~~**`31 StatModifier` : QUI le pose n'est pas tranche.**~~ -- **TRANCHE par #371 : PERSONNE.**
  Deux balayages qui se recoupent (case-371 §5). (a) Les SIX chemins de pose sont inventories par
  xrefs ; les deux seuls ou l'`effectType` n'est pas un litteral (`APowerUpAbility$$AddAbsoluteBoost`
  / `$$AddPctBasedBoost`, qui lisent un champ de record) sont ELIMINES -- leurs trois implementations
  concretes portent `0x473`/`0x477`/`0x475`. (b) Sur TOUT le binaire, `(void *)0x1f,` n'apparait que
  dans **5 fonctions sur 65 000**, dont AUCUNE n'est une pose d'effet (`On(0x1f)` = TriggerEvent,
  `AtomicGroup(0x1f)` x2, deux classes d'effet de TUILE) ; `&DAT_0000001f` = **0 occurrence**.
  ⇒ la fabrique est enregistree mais **rien ne la reference** : `31` est du **registered-but-dead**,
  il n'y a rien a porter. (Limite : `search_code` porte sur le pseudo-C INDEXE ; la conclusion tient
  sur la conjonction (a) ET (b).)
* **Aucune mesure live** : ce cas est 100 % offline (binaire + tables versionnees + gameconfig).
