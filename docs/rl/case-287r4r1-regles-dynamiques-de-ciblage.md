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

## 9. Recensement du résidu #287-r5

**19 des 46** ont une surcharge native lisible dans `data/symbols/<build>/ghidra/functions.tsv`
(toutes `IdunBattleLogic.Entities.Abilities.…$$GetDynamicInvalidTargetReason`) :

| id | ability | ce qui bloque le port |
|---|---|---|
| 1016 | `SendInTheNextWave` | sélecteur de tuiles par slot d'interface |
| 1025 | `SkyStrike` | `DidMove` + `GetMainTile` + deux slots `battleQuery` |
| 1076 | `MV71SniperDroneSquadAttack` | `IsMeleeAttack` + `PickTile` |
| 1087 | `ExemplarOfTheKauyon` | `IsFreeTile` + prédicat LINQ sur un sélecteur |
| 1101 | `AttemptedPossession` | `GetChildren` (deux appels) + `GetPreferredAttackTarget` |
| 1112 | `AlphaWarrior` | `DSLTriggers$$IsInTeamSynapseRange` — **trigger non porté** |
| 1151 | `TheQuickening` | `MovableTilesInRange` − `Enemies`, puis `GetFeetCount` |
| 1164 | `MindControl` | slot 0x7c + `FilterInPlace` générique |
| 1168 | `EntropyCannons` | `IsInTeamContagionsOfNurgleAura` + `HasNegativeModifier` |
| 1175 | `BloodChalice` | slot 0x62 + `IsAffectedByHealType` |
| 1177 | `LightOfSanguinius` | `GetNumberConstant(0x16)` + `Enumerable.Any` |
| 1179 | `CultDemagogue` | trois slots `battleQuery` + `GetStringConstant` |
| 1180 | `HeroicFusillade` | slots 0x67/0x6f + `Where`/`ToList` |
| 1185 | `ForwardObservers` | (non décompilé — porteur summon) |
| 1197 | `ExcruciatingFrequencies` | `GetAttackTargets` |
| 1200 | `SquigLaunchas` | (non décompilé) |
| 1202 | `VigilanceEternal` | slot 0x62 + `GetPossibleMovementTiles` |
| 1204 | `LeadingTheCharge` | `GetPossibleMoveTiles` + slot 2 |
| 1213 | `DeathOnTheWind` | `GetNumAttacksReceivedThisTurn` — **absent des canaux de mesure** |

Les **27 autres** (1006, 1014, 1027, 1035, 1036, 1041, 1044, 1048, 1051, 1062, 1063, 1066, 1067,
1069, 1078, 1080, 1088, 1093, 1097, 1098, 1103, 1104, 1113, 1150, 1169, 1171, 1206) n'ont **aucune**
surcharge dans la table de symboles.

⚠ Cela **ne prouve pas** qu'elles ne surchargent pas : IL2CPP déduplique les corps triviaux et
n'attribue qu'**un** propriétaire (cf. CLAUDE.md, « l'ABSENCE d'une méthode dans les tables ne prouve
RIEN »). Conclure demanderait le slot `+0x480` sur l'instance, au runtime.
