# #287-r4-r1 — les règles dynamiques de ciblage, portées par la MESURE

#287-r4 a rendu le délégué `options+0x38` **appelable** (bug de typage : une CLASSE là où une
INSTANCE est requise). Il répondait alors `0` pour 50 des 65 ids, faute d'avoir porté les **corps**.
Cette tranche en porte quatre — ceux que le corpus témoin exerce — et **recense** les autres.

## 1. Où vit la règle

Le corps est le slot de vtable `+0x480` de la sous-classe (`<X>Ability$$GetDynamicInvalidTargetReason`),
qu'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` publie en délégué à `options+0x38` et que la
surcharge **7 arguments** de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`
invoque **sans garde** sous `TargetingRule.TargetMatchesDynamicRule`.

Côté port, deux canaux, et c'est l'existence d'une classe qui tranche :

| l'ability a une classe de behaviour | où s'écrit la règle |
|---|---|
| oui | **surcharge** `get_dynamic_invalid_target_reason` dans la classe |
| non | entrée de **`DYNAMIC_TARGET_RULE_UNPORTED`** (`abilities/targeting.py`) |

Le second foyer est le pendant exact de `TARGETING_OPTIONS_UNPORTED` : même objet natif, vu par ses
deux champs — `options+0x28` (le masque) et `options+0x38` (le délégué).

## 2. Les quatre corps portés

| id | symbole natif (`…$$GetDynamicInvalidTargetReason`) | corps, verbatim | canal |
|---|---|---|---|
| 1005 `AdaptiveStrategy` | `…Active.Loki.AdaptiveStrategyAbility` | `HasTrait(target, 0x10) ? 2 : 0` | table |
| 1038 `FoulInfusion` | `…Active.Loki.FoulInfusionAbility` | `HasTrait(target, 0x7ea) ? 0 : 2` | table |
| 1201 `SquigMine` | `…Active.Loki.SquigMineAbility` | `target==null?0 : (HasEffect(0x5a1) \|\| HasSteppableUnit) ? 2 : 0` | surcharge |
| 1145 `SporeMineLauncher` | `…Active.Loki.SporeMineLauncherAbility` | `HasSteppableUnit ? (IsEnemy(GetUnit(target), caster) ? 2 : 0) : 0` | surcharge |

`0x10` = `UnitTrait.Hero`, `0x7ea` = `UnitTrait.Chaos`, `0x5a1` = `EffectType.SquigMine_Tile`,
`2` = `TargetingRule.TargetMatchesDynamicRule`.

Deux points que la RE a tranchés, et qu'un mirror naïf rate :

- **`UnitExtensions$$HasTrait(unit, trait)`** = `GetBaseUnitComponent(unit)?.HasTrait(trait) ?? false` :
  il lit l'entité CIBLE elle-même et **ne résout pas** une tuile en son occupant. Le mirror est donc
  `_unit_traits`, pas `unit_of_entity` — contraste avec `TileExtensions$$HasSteppableUnit`, dont
  l'argument transite par `GetUnit` (c'est pourquoi `has_steppable_unit`, lui, l'emploie).
- **`Chaos` est un pseudo-trait d'ALLIANCE**, absent de tout `traits` gameconfig. Il n'existe que
  dans le substrat d'entité (`entity_trait_names`, #264) ; le lire par le kit rendrait `FoulInfusion`
  constamment refusante.

**1005 et 1038 sont de sens INVERSE** (l'une refuse sur présence, l'autre sur absence) : les deux
substrats de mesure sont donc contre-épreuves l'un de l'autre, et une confusion inverserait les deux
verdicts à la fois.

## 3. Pourquoi quatre, et pas cinquante

Le critère est la **mesure**, pas un compte : porteur spawnable (pool régulier ou MoW) **et** corps
intégralement portable avec les primitives déjà présentes. Les corps restants ne sont pas « trop
gros » — ils dépendent d'étages **non portés** : sélecteurs DSL (`MovableTilesInRange`, `Enemies`),
triggers (`IsInTeamSynapseRange` pour 1112, `IsInTeamContagionsOfNurgleAura` pour 1168), formules de
config, `GetNumAttacksReceivedThisTurn` (1213, absent de `combatSnapshot`/`decisionView`). Les porter
serait spéculatif tant que ces étages manquent.

## 4. Chiffres, re-dérivés des deux côtés

`probe_287r4r1_dynamic_target_rules.py` — **évaluabilité** (le port sait-il évaluer le corps ?), un
axe distinct de la **voie** que ventile `probe_287r4` (comment le porteur est fabriqué).

| | avant | après |
|---|---|---|
| ids posant `TargetMatchesDynamicRule` | 65 | 65 |
| surcharge dans la classe portée | 15 | **17** |
| entrée de `DYNAMIC_TARGET_RULE_UNPORTED` | 0 | **2** |
| aucune règle (`0` permissif) | 50 | **46** |
| bascules discriminantes (5 bras) | 0 / 5 | **5 / 5** |
| `a_morde` (mutants) | 0 / 5 | **5 / 5** |
| `_has_valid_targets(1005)`, tous alliés héros | `True` | **`False`** |

## 5. Le rouge, fermé en live

`C1_02` / seed 28704, walker `necroWarden`, `probe_287r1r1_verify_turn_ended.py` :

| | live (natif) | port avant | port après |
|---|---|---|---|
| flags après le pas | `[0, 1, 4]` | `[0, 1]` | **`[0, 1, 4]`** |

`4` = `UnitFlag.NoActionAvailable`. La contre-épreuve `orksWarboss` (généralisation A de #287-r4)
reste verte : `[0,1,4]` des deux côtés.

## 6. Généralisation, avec ATTRIBUTION intégrée

`probe_287r4r1_generalisation_live.py` confronte les quatre règles à l'oracle natif
`abilityReason` (le masque `TargetingRule` complet), cible par cible, puis **re-mesure les mêmes
couples règles DÉSARMÉES**. Une violation qui survit au désarmement est **préexistante** et n'est pas
imputée à la tranche.

| board | couples | refus reproduits à l'identique (bit dynamique) | imputables | préexistantes |
|---|---|---|---|---|
| `MC1_67` | 18 | **2** (→ 0 désarmées) | **0** | 4 |
| `C1_02` | 18 | **2** (→ 0 désarmées) | **0** | **0** |

Les deux refus reproduits sont `1005` sur `deathPutrifier` (héros) et `1038` sur `necroWarden`
(non-Chaos), `0x2` des deux côtés — et ils **tombent à 0** quand on désarme, donc le témoin est bien
porté par ces règles et non par un autre étage du masque.

Deux corrections de MESURE que ce probe a imposées, toutes deux trouvées en le jouant :

- **le domaine**. Une ability TILE-TARGET recevait des ids d'UNITÉ — un régime que le natif ne
  produit pas ; elle reçoit désormais des TUILES (occupées et libres).
- **le critère d'`a_morde`**. Mesuré sur l'arbre d'avant : `après == 0` rendait **5/5** alors
  qu'aucune règle n'y était portée — la mutation n'y retirait rien, et son inertie se comptait comme
  un vert. Le critère est le **delta** (`avant == 2` ET `après == 0`).

## 7. La garde

`tests/engine/test_287r4r1_dynamic_target_rules_offline.py`, cinq étages : recensement non vide et
**bi-canal** ; ordinaux **figés au site** (`probe_313` compare le mirror au build et redeviendrait
vert après un renumérotage qui a déjà faussé le site) ; bascule ; mutants ; et le **chaînon complet**
`_has_valid_targets`, seul étage qui prouve que la règle arrive jusqu'à l'observable.

Le fichier est jouable **des deux côtés** du correctif (repli nommé sur un dict vide) : sans cela son
rouge serait un `ImportError`, qui ne dit rien de la mécanique gardée.

**Vu rouge** sur l'arbre d'avant (`git archive HEAD scripts/python data`) : **10 failed / 6 passed**,
dont l'étage 5 ; `probe_287r4r1` `rc=1`, `a_morde 0/5` avec ses cinq bras déclarés inertes. Vert
après : **16 passed**, `rc=0`.

## 8. Ce qui n'est PAS couvert

- **Résidu #287-r5 — 46 ids sans règle portée**, §9. Le `0` reste la dégradation permissive du
  module ; le natif, lui, **lève** sur un délégué nul. L'asymétrie est nommée, pas silencieuse.
- **Le terme `Steppable` de 1201/1145 n'est pas exercé en LIVE.** Ses porteurs sont les power-ups
  (`powup*`, npc, posés par le BC) : aucun sur `C1_02`/`MC1_67`. Couvert **offline** (bascule +
  mutant, un bras par terme du `||`). Ce n'est pas « non confrontable » — un board portant des
  power-ups le ferait mordre.
- **Écart PRÉEXISTANT, hors tranche** : `SquigMine` sur une tuile OCCUPÉE — natif `0x1`
  (`ValidRequest`, que le natif réutilise comme code de refus), port `0x1000` (`TargetTileIsFree`).
  **4 couples sur `MC1_67`**, mesurés survivants au désarmement des quatre règles. Gisement distinct
  (domaine TILE), à ouvrir séparément.
- Le volet **caster** (`options+0x30`, `CasterMatchesDynamicRule`) : inchangé, aucune règle portée.

## 9. Recensement du résidu #287-r5 — état APRÈS la tranche #287-r5

Le recensement n'est plus une table écrite : il est **dérivé** de
`data/symbols/<build>/ghidra/functions.tsv` par `probe_287r5_etages_bloquants.py`, qui apparie par
nom de classe et **rougit** si un id à surcharge native perd son étage, ou si une entrée d'étage
perd son symbole. Le re-dériver, ne pas citer les chiffres ci-dessous.

### 9.1 Le « 46 » mélangeait deux populations

**Le corps de BASE `IdunBattle.Entities.Abilities.AActiveAbility$$GetDynamicInvalidTargetReason` est
`return 0`.** Il n'apparaît sous ce nom nulle part : IL2CPP déduplique les corps triviaux et Ghidra
l'attribue à `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`. Ce qui l'identifie sans
supposition, c'est le **fallback explicite** de
`...ForwardObserversAbility$$GetDynamicInvalidTargetReason`, qui l'appelle en queue.

| population | compte | ce que vaut le `0` du port |
|---|---|---|
| surcharge native **lisible**, non portée | 16 | **dette réelle** |
| **aucune** surcharge dans la table | 27 | le délégué pointe le corps de base ⇒ le port **coïncide** |

⚠ (b) ne **prouve** pas le non-override — une table indexée par adresse ne le peut pas. Il dit que
le port n'a **rien à lire**, et que la seule lecture disponible concorde. Trancher demanderait le
slot `+0x480` sur l'**instance**, au runtime.

### 9.2 Les étages qui restent, et ce qu'ils retiennent

`AActiveAbility+0x20` est **`IdunBattle.Core.Services.BattleQuery`** (établi par
`TargetingQuery$$Init`, qui le pose en `+0x18`, et par le second site de `GetTilesInRange`). C'est
l'étage le plus répandu — mais éclaté en slots, pas en une primitive unique.

| id | ability | étage qui bloque encore |
|---|---|---|
| 1016 | `SendInTheNextWave` | `GetSurroundingTiles` + `GetUnitMaxRange(unitId)` |
| 1025 | `SkyStrike` | `DidMove` + `GetMainTile` + `AreEntitiesAdjacent` + `GetAdjacentTiles` |
| 1076 | `MV71SniperDroneSquadAttack` | `IsMeleeAttack` + `PickTile` (méthodes de sa classe) |
| 1087 | `ExemplarOfTheKauyon` | `IsFreeTile` + `GetAdjacentUnits` + prédicat LINQ |
| 1101 | `AttemptedPossession` | `GetChildren` + un étage de **SIMULATION** (`SimulateEffects`) |
| 1112 | `AlphaWarrior` | trigger DSL `IsInTeamSynapseRange` |
| 1151 | `TheQuickening` | tuiles de mouvement (`MovableTilesInRange` − `Enemies`) |
| 1164 | `MindControl` | slot 0x7c + un **prédicat statique illisible** (corps dédupliqué) |
| 1168 | `EntropyCannons` | triggers `IsInTeamContagionsOfNurgleAura` + `HasNegativeModifier` |
| 1179 | `CultDemagogue` | trois slots `battleQuery` + `GetStringConstant` |
| 1180 | `HeroicFusillade` | **pathfinding** (`MovementQuery$$IsInMovementRange` + `overrideRange`) |
| 1197 | `ExcruciatingFrequencies` | sélecteur DSL `GetAttackTargets` |
| 1200 | `SquigLaunchas` | triggers DSL `HasMinimumAdjacent{Orks,FriendlyUnits}` |
| 1202 | `VigilanceEternal` | tuiles de mouvement (`GetPossibleMovementTiles`) |
| 1204 | `LeadingTheCharge` | tuiles de mouvement (`GetPossibleMoveTiles`) |
| 1213 | `DeathOnTheWind` | **le SEEDING**, pas l'étage — cf. 9.3 |

Regroupés : **tuiles de mouvement 3** (1151, 1202, 1204), **triggers DSL 3** (1112, 1168, 1200),
**sélecteurs DSL 2**, **pathfinding 1**, le reste isolé.

### 9.3 `1213 DeathOnTheWind` — l'étage est PORTÉ, c'est le seeding qui manque

`EntityExtensions$$GetNumAttacksReceivedThisTurn(unit)` lit `ActorStatisticsComponent+0x38`. Le port
a **déjà** ce compteur (`UnitComponent.times_attacked_this_turn`) et **déjà** son reset au turn-start
(`operations/minimal_health.py::reset_times_attacked`, mirror de
`ActorStatisticsComponent$$ResetAttacksReceivedThisTurn`). Ce qui manque est que `load_state` ne
le **seede** pas : sur un état chargé après une attaque, le port rendrait `0` là où le natif rend
`>= 1`, donc **refuserait des cibles que le natif ACCEPTE**. Point d'ancrage à exposer :
`GetNumAttacksReceivedThisTurn` dans `combatSnapshot`/`decisionView` — un capteur, donc une fenêtre
de reinject.

### 9.4 Ce que #287-r5 a porté et CONFRONTÉ

| id | corps natif, verbatim | code rendu | confrontation live |
|---|---|---|---|
| 1185 `ForwardObservers` | `HasEffect(target, 0x462) ? 2 : <base>` | `0x2` | bascule TEMPORELLE, `MC1_67` + `C1_02` |
| 1177 `LightOfSanguinius` | `GetFreeAdjacentTiles(target).Any(t => GetDistance(t, casterTiles) <= range)` | **`0x20`** | bascule SPATIALE, `MC1_67` + `C1_02` |
| 1175 `BloodChalice` | `AreEntitiesAdjacent && IsAffectedByHealType(target, NonMechanical)` | `0x2` | 4 bras, `MC1_67` + `C1_02` |

`0x462` = `EffectType.Markerlight`. Primitives mirrorées au passage :
`UnitExtensions$$IsMechanical`, `UnitExtensions$$IsAffectedByHealType`, et le mirror d'enum
`IdunBattle.Entities.Enum.HealType` (au registre de `probe_313` dans le même commit).

Trois points que la mesure a imposés, et qu'aucune lecture n'aurait donnés :

- **`1177` ne rend PAS `TargetMatchesDynamicRule`** mais `0x20 TargetHasFreeAdjacentTile`, un bit
  que son masque statique porte déjà. Le recensement se fait donc sur le **bit posé au masque**,
  jamais sur le code rendu — un port qui n'aurait cherché que `0x2` aurait raté la règle entière.
  Le probe sépare les deux origines du `0x20` par désarmement **et** par décomposition (tuiles
  libres / distance minimale).
- **`1185` exige DEUX porteurs.** `AttackQuery$$GetInvalidTargetReason` résout l'instance par
  `ActiveAbilityComponent$$GetOrNull` et rend `0x1` (`ValidRequest` en code de refus) dès que
  l'ability est consommée — **en amont** de la règle. Avec un porteur unique, le natif rendait `0x1`
  après son propre cast et le rouge accusait le PROTOCOLE. L'un caste, l'autre observe.
- **Le terme ADJACENCE de `1175` est NON EXERCÉ**, et sa cause est *assertée* : le ctor pose
  `OverrideRange = 1`, donc l'étage PORTÉE refuse en amont (`0x8000000`, identique des deux côtés).
  Si un build change cette portée, le probe re-exige le terme.

Le porteur de `1185` arrive par le **chemin de stats explicite** (`--explicit-stats
tauNpc5StealthSuit:5`) : le vrai npc, avec ses stats, ses traits et son arme — la greffe de
`case-92 §5bis` n'a pas été nécessaire. Son jumeau summon `tauSmnStealthSuit` n'a **aucun**
invocateur au catalogue (l'ability `ATemptingTrap` qui le déclare n'est portée par personne).

### 9.5 Chiffres, re-dérivés des deux côtés

| | avant #287-r5 | après |
|---|---|---|
| entrées de `DYNAMIC_TARGET_RULE_UNPORTED` | 2 | **5** |
| aucune règle (`0` permissif) | 46 | **43** |
| dont dette réelle (surcharge native lisible) | 19 | **16** |
| dont `0` coïncidant avec le corps de base | 27 | 27 |
