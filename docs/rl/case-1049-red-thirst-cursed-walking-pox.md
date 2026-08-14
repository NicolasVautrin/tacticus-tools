# #1049 — `RedThirst` (1249) et `CursedOfTheWalkingPox` (1072) : deux passifs de SUMMON

> Build `rnca9r7q6c`. Les deux derniers **GAPS confrontables** de `passive-ability-coverage.md`
> portés par un summon de faction différente. Verdict : **PORTÉS tous les deux**, confrontés live
> bit-exact.

| item | enum | effet / vecteur | verdict |
|---|---|---|---|
| `RedThirst` | `TriggeredAbilityType` 0x4e1 = 1249 | owner-effect `RedThirst_ExtraDamageAndHit` (0x52a = 1322) | **PORTÉ** — 2 canaux + active-condition |
| `CursedOfTheWalkingPox` | `TriggeredAbilityType` 0x430 = **1072** | `ABILITY_TRIGGERS`, `On(0x35 = PostUnitKill)` | **PORTÉ** — trigger + `Spawn` |

## 1. `CursedOfTheWalkingPox` n'est PAS une voie inversée — et l'ordinal ne le dirait pas

Le brief demandait de trancher : namespace natif `...Abilities.**Active**.Loki`, item classé
*passif*. Trois lectures concordantes, aucune déduite :

* le NOM est dans `IdunBattle.Entities.Enum.TriggeredAbilityType` (`1072 = CursedOfTheWalkingPox`),
  et le gameconfig le porte en `units.summons.deathPoxwalker.passiveAbilities` — **voie et enum
  concordent** ;
* `frida/classes.tsv` donne le parent `IdunBattle.Entities.Abilities.**BaseTriggeredAbility**` ;
* la classe de vue `CursedOfTheWalkingPoxVisuals` dérive d'`IdunBattle.View.AbilityConfigs.
  **APassiveAbilityVisualsBase**`.

Le namespace `Active` est structurellement non fiable — `AdrenalGlands`, `CloseCombatWeakness`,
`InstinctiveBehaviour_InitAbility` y vivent aussi en étant des `TriggeredAbilityType`.
⚠ **`ActiveAbilityType 1072 = MyWillBeDone`** : lire l'id dans le mauvais enum ne lève RIEN.
Cliquet : `test_1049_..._offline.py::test_le_meme_ordinal_nomme_autre_chose_dans_l_autre_enum`
(il assertionne son propre non-vide).

## 2. `RedThirst` — DEUX canaux, et la PROSE i2 se trompe sur l'un des deux

`RedThirstAbility` a pour parent `AOwnerEffectTriggeredAbility` et n'override QUE `$$GetEffectType`
(corps entier `return 0x52a`) : owner-effect PERMANENT posé à l'init, patron `ToughToKill` /
`HammerOfWrath`. Les trois corps de l'effet, lus verbatim :

```
CreateActiveCondition            = HealthPctIsBelowOrEqual( Owner@<DSLSelectors+0x30>,
                                       ConfigConst(0x4e1, Owner, AbilityConstantType.healthPct = 0x4f) )
CreateEffectDamageBonusForAttack = ForAddition( get_OwnerIsCaster,
                                       ConfigVar(0x4e1, Owner, AbilityVariableType.extraDmg = 8) )
CreateEffectHitsBonusForAttack   = ForAddition( get_OwnerIsCaster & IsCharging(Owner@+0x30, Target@+0x60),
                                       ConfigConst(0x4e1, Owner, AbilityConstantType.extraHit = 0x2b) )
```

**Le canal DÉGÂT n'a qu'UN nœud de trigger.** L'i2 dit « gains +{extraDmg} Damage and scores
+{extraHit} hit **when charging** » et rattache la charge aux DEUX termes ; le décompilé ne la met
que sur le second. Le natif tranche — mesure ci-dessous, régime `NOSTEP_BLESSE`.

Magnitudes : `extraDmg` est une **variable** (indexée par niveau, **seule** entrée de
`variablesAffectedByRarityBonus` → scalée par le multiplicateur) ; `extraHit` une **constante**
(= 1, jamais scalée). Confondre les deux accesseurs ne lèverait aucune erreur.

C'est l'entrée **#8** de l'inventaire d'`IsCharging` (`case-ischarging-hits-channel.md` §2), la
dernière du canal COUPS restée « absente (canal absent) ».

## 3. `CursedOfTheWalkingPox` — le gameconfig VIDE impose `CopyOwner`

```
CreateTrigger   = On(0x35 = PostUnitKill) & get_OwnerIsActor
                & AreEnemies(Owner@+0x30, Target@+0x60) & IsDead(Target@+0x60)
                & NOT TriggeringAbilityIs(<cette ability>) & IsCanAddUnit(Target@+0x60)
                & NOT IsObjectOrSteppable(Target@+0x60)
                & NOT HasTrait(Target@+0x60, 0x5 = UnitTrait.Mechanical)
CreateBehaviour = options = SpawnUnitOptions.CopyOwner(dsl, abilityState)
                  options.<+0x48> = Nullable<bool>(true)                    # finishTurnOnSpawn
                  options.<+0x40> = Nullable<UnitOverrideType>(2 = Summon)  # overrideType
                  Spawn( Owner@+0x30,
                         First(CanAddUnit(TargetTiles@<DSLSelectors+0x78>), 1, 0),
                         UnitIdFromUnit(Owner@+0x30), options )
```

Le gameconfig de l'ability est **VIDE** (`{"upgrades": null, "variables": {}}`, aucune constante) :
ni `unitId`, ni `summonHp`. **Aucun `GetStringConstant`/`WithStatsFromConfig` n'aurait quoi lire** —
c'est ce qui impose `UnitIdFromUnit(Owner)` (le clone porte le `visualId` du porteur, donc le même
kit : le passif est **récursif**) et `CopyOwner` (stats COURANTES du parent).

`SpawnUnitOptions$$CopyOwner`, lu : cinq `StatModifierFormula(StatAmount(Owner, <StatType>,
StatPart.Current = 3))` — `5 Health`, `0x10 FixedArmor`, `0 Attack`, `1 Movement`,
**`0x14 NumberOfMembers`** (le cinquième était écrit `20` sans nom dans la docstring
d'`execute_self_replica` ; il est nommé ici) — puis `CreateSpawnOptions(abilityState, null, null,
null)`. Le port en fait un **foyer unique**, `operations/spawn.py::_spawn_copy_owner_at_tile`,
partagé avec `execute_self_replica` (l'autre consommateur natif).

Les deux champs d'options sont LUS et sans effet observable ici, ce qui est dit :
`+0x48` OVERRIDE le calcul `HasTrait(Steppable) ? false : !HasTrait(Hero)` de
`SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` — un Poxwalker n'étant ni l'un ni l'autre, le
défaut valait déjà `true` ; `+0x40` (`overrideType = Summon`) n'a **aucun modèle côté port**
(résidu **déjà ouvert** : `#1044-r1`/`#1044-r2`).

Ce port ferme le **3ᵉ** des quatre consommateurs natifs d'`On(0x35)` recensés par
`case-462-r4b-r1-r1-r1-r1-c-r3-r1-r4` §3 (restent `Lakrimae_SummonPoxwalker` et le volet de
`PossessionAbility` déjà porté).

## 4. Confrontation LIVE — deux montages, et le choix de chacun est une mesure

`probe_1049_red_thirst_walking_pox.py`, MC1_67 / seed 777.

### `RedThirst` — GREFFE sur un héros du pool, PAS le jumeau npc

`--unit-stat "astraBullgryn:PassiveAbilities=[1249],RemainingHealth=<X>"` (4 coups Physical mêlée ;
son passif d'origine `AvalancheOfMuscle`, lui aussi gaté `IsCharging`, disparaît avec la greffe —
ce qui évite qu'il confonde le régime).

| régime | live | offline | contrôle (1322 retiré) |
|---|---|---|---|
| `CHARGE_BLESSE` (41 % PV, pas 2→1 hex) | n=5 `[5281, 3132, 4010, 4016, 3486]` | **bit-exact** | n=4 `[4682, 2533, 3411, 3417]` |
| `NOSTEP_BLESSE` (41 % PV, aucun pas) | n=4 `[5281, 3132, 4010, 4016]` | **bit-exact** | n=4 `[4682, 2533, 3411, 3417]` |
| `CHARGE_PLEIN` (100 % PV) | n=4 `[4682, 2533, 3411, 3417]` | **bit-exact** | identique (non discriminant, attendu) |

Trois faits séparés : `+599 = extraDmg[50] × 180 %` par coup **dès que les PV sont sous le seuil,
charge ou non** (le décompilé contre la prose i2) ; `+1 coup` **seulement** en charge ; **rien** à
PV pleins (et le natif publie l'effet avec `active: false`, mesure `includeInactive`).

⚠ **Pourquoi PAS le porteur exact `bloodNpc1Intercessor:45`** : mesuré, son
`combatSnapshot.unitConfig` rend `{"passiveAbilityLevel": 1, "abilityVariablesMultiplier": 100}`
alors que `unitAbilityStates` rend `(65, 200)` pour la MÊME entité. `snapshot.py::
_ability_state_with_channel` ne comble QUE le trou (`passive_level` falsy) et ce `1` est truthy →
l'offline lisait `extraDmg[1] = 6` là où le natif lit `extraDmg[65] × 200 %`, soit **+7 contre
+1092 par coup**. C'est un artefact du montage `--explicit-stats` (une unité **invoquée**, elle,
n'a AUCUN `unitConfig` → le canal gagne) — il aurait fait accuser le port. Résidu **`#1049-r1`**.

### `CursedOfTheWalkingPox` — le JUMEAU NPC, piloté au lieu d'être observé

`--p-units deathNpc1Poxwalker:45 --explicit-stats deathNpc1Poxwalker:45` : même `visualId`, même
`passiveAbilities`, même arme que le summon. Tout le montage « un summon ne se commande pas »
(#291) tombe.

| bras | victime | live | offline |
|---|---|---|---|
| POSITIF | `orksNob` (non-mécanique) | 1 `deathPoxwalker` en (6,8), hp **6555**, parent **u81** | **identique** |
| MÉCANIQUE | `necroWarden` (**Mechanical**) | 0 spawn | 0 spawn |

Les PV sont l'observable qui sépare `CopyOwner` de `WithStatsFromConfig` : l'ability n'a aucune
variable `summonHp`, donc l'autre chemin poserait un clone à **0 PV** — vivant, faux, sans erreur.
Les events natifs le confirment mot pour mot : `Unit_IsSummoned: 1`, `Unit_SpawnSource: 2`
(= `UnitOverrideType.Summon`), `Unit_Parent_Id: 79`, `UnitStats_MaxHealth: 6555`, puis
`UnitStats_TriggeredAbility_Id: 1072` sur le clone (donc récursif).

⚠ **Piège de montage, mesuré** : avec un SEUL ennemi, le kill termine le match
(`Match_Winner`) et le `decisionView` d'après rend `units: []` — le spawn, pourtant émis dans les
events du même `applyAction`, devient **inobservable**. Un « 0 spawn » lu là aurait accusé le port.
D'où le 2ᵉ ennemi témoin, jamais attaqué.

## 5. Matrice de mutants — 4 rouges sur 5, et le 5ᵉ a RENFORCÉ une garde

| mutant | ce qu'il casse | verdict |
|---|---|---|
| M1 — `is_charging_attack` retiré du canal COUPS | le gate de charge | **ROUGE** (`nostep_blesse`) |
| M2 — `is_charging_attack` AJOUTÉ au canal DÉGÂT (la lecture i2) | le nœud unique du canal dégât | **ROUGE** (live `nostep` + offline) |
| M3 — `is_active` câblé à `True` | l'active-condition | **ROUGE offline… et VERT live au 1ᵉʳ jet** |
| M4 — gate `Mechanical` retiré | la contre-épreuve du gate | **ROUGE** (`pox_mecanique`) |
| M5 — `link_parent=False` | le 1ᵉʳ argument de `Spawn` | **ROUGE** (`pox_positif`) |
| M6 — `Tiles(Target)` au lieu de `Tiles(TargetTile)` | le domaine du sélecteur | **VERT — non discriminant** |

**M3 est la trouvaille.** Le bras `CHARGE_PLEIN` restait VERT avec un `is_active` inerte : sur
l'hôte de GREFFE l'instance 1322 **n'existe pas** à PV pleins (canal `decisionView.effects`
ACTIF-ONLY, et le seed `ABILITY_INIT_OWNER_EFFECTS` lit le kit **gameconfig** du `visualId`, où la
greffe — qui vit dans la `BC` — n'apparaît pas). Le bras prouvait « live == offline » sans rien
dire de la condition. Un **3ᵉ bras** a été ajouté : l'instance est matérialisée DE FORCE
(`_materialize_owner_effect`, niveau 50 / mult 180 = l'état du vrai porteur) et doit rester
INERTE. M3 rougit alors. Sur le VRAI porteur (`bloodSmnIntercessor`, dont le kit gameconfig porte
`RedThirst`) le seed fonctionne — c'est le régime que ce 3ᵉ bras reproduit.

**M6 n'est pas un trou** : pour une unité mono-hex les deux nœuds rendent la même tuile. La
distinction native (`TargetTiles@+0x78` = `TargetPosition.Tiles ?? [TargetTile] ?? GetTiles`) ne
mord que sur une empreinte multi-hex ou une `TargetPosition` explicite.

## 6. Validation — ce qui a été rejoué

* **`test_1049_..._offline.py`** — 13 verts : registres, ordinaux ÉCRITS aux sites, qualification
  d'enum, magnitudes gameconfig, active-condition paramétrée (5 points dont l'égalité au seuil),
  les deux canaux, foyer `CopyOwner`.
* **`test_1049_..._live.py`** — 7 verts (5 runners) : 3 régimes `RedThirst`, 2 bras `Poxwalker`,
  2 généralisations `C1_25` / 31337.
* **Cliquets transverses**, tous rejoués et **complétés dans le même commit** :
  `test_refresh_active_flag_discriminant_offline` (attestation de la surcharge `is_active`),
  `test_camo_seed_inventory_offline` + `probe_366_camo_seed_inventory.POSE_VECTOR` (verdict de
  pose), `test_ctx_traits_substrat_ventilation_offline` (deux sites `ctx.traits` neufs ; l'entrée
  `execute_self_replica` a **déménagé**, pas disparu). Plus `test_337`, `test_1041`, `test_951r2`,
  `test_270r2`, `test_enum_mirror_ratchet`, `test_437_r1`, `test_1015_trait_channels`,
  `test_341_kit_coverage_voies`, `test_570r5`, `test_1038_rebake`, `test_999r3r1` — **81 + 95
  verts**. `probe_313` rc 0 (cache régénéré et indexé), `probe_181` rc 0, `probe_366` rc 0,
  `probe_433_r1` rc 0.
* **Audits régénérés** — `passive-ability-coverage.md`, `summons-registry`, `npc-registry`,
  `kit-coverage`, `combat-ability-coverage`. Les deux items y passent de `GAP-ABSENT` /
  `GAP-MENTION` à **`PORTE`** : `CursedOfTheWalkingPox` avec le canal **`T`** (le trigger), et
  `RedThirst` avec **`O`** + **`E`** (owner-effect et effet). ⚠ **Les totaux ne sont pas cités
  ici** : les audits ont été rebasés sur `origin/master` alors que quatre tranches sœurs
  fusionnaient, donc tout `avant → après` global mesurerait leur travail autant que le nôtre —
  les re-dériver (`python audit_passive_ability_coverage.py`), jamais recopier une ligne.

## 7. Non couvert, et nommé

* **`#1049-r1`** — l'`AbilityState` d'un npc monté par `--explicit-stats` (cf. §4).
* **`NOT TriggeringAbilityIs(<self>)`** : le canal `TriggerEvent.triggering_ability` est
  inconditionnellement vide sur le vecteur MORT — gate ÉCRIT, inerte. MÊME résidu, MÊME cause et
  MÊME sens (PERMISSIF) que `#955-r1`. Effet réel côté natif : empêcher une CASCADE ; côté port,
  aucun vecteur ne produit ce cas (le spawn ne tue personne).
* **`overrideType = Summon`** (`SpawnUnitOptions+0x40`) : non modélisé — résidus **déjà ouverts**
  `#1044-r1` / `#1044-r2`, qui portent exactement ce champ.
* **`IsCanAddUnit` du port passe `allow_steppable=False`** là où la surcharge native à 2 arguments
  de `DSLSelectors$$CanAddUnit` lit `<DSLTriggers+0x48>` = `op_LogicalNot(YesTrigger)` → **VRAI**.
  Écart INERTE à ce call-site (la victime est morte, sa tuile est libre des deux façons) et
  **préexistant** (foyer partagé avec `GrapnelLauncherAbility`) : non touché. Le call-site du
  `CreateBehaviour`, lui, passe bien `allow_steppable=True`.
* **`ignoreOverkill`** du `On(0x35)` : non threadé sur ce vecteur (même statut que
  `CosmicHorrorOnMoveAbility` et `PossessionSummonOnKillAbility`).
* **Face DÉCISION** : aucun playbook natif pour ces deux ids (`search_symbols_by_name` n'en rend
  aucun) — rien à porter de ce côté.
* **Le summon lui-même n'a pas été piloté** : les deux confrontations passent par un porteur
  COMMANDABLE (greffe / jumeau npc), pas par la chaîne `AggressiveOnslaught` → Intercessor ni
  `Poxwalkers` → Poxwalker. Le code exercé est le même objet natif (le passif est chargé PAR
  ABILITY), mais la chaîne d'invocation, elle, n'est pas confrontée ici.
