# #894 — La VOIE du gameconfig ne dit pas l'ENUM, et `1173 ArcScourge`

## 1. Le verrou : `admecBossBelisarius` était INMONTABLE

`catalog_inject.synthesize` résolvait `passiveAbilities` par `triggered_ability_id` et
`activeAbilities` par `active_ability_id` — « la VOIE dit l'enum ». Deux entrées du gameconfig
contredisent cette équation, et l'une levait :

```
KeyError: TriggeredAbilityType.ShroudPsalm inconnu du build courant
```

**Ce que le natif fait, LU.** `Idun.Source.IdunBattle.View.BattleConfigBuilder$$SetupAbilities`
itère UNE liste (`IdunMetaLogic.UserProgress.UnitProgression$$GetAllAbilities` =
`GetAbilities(isActive:true)` PUIS `GetAbilities(isActive:false)`) de
`IdunMetaLogic.UserProgress.Model.UnitAbility`, dont les champs sont écrits par
`IdunMetaLogic.UserProgress.UnitProgression$$GetAbility` :

| offset | contenu |
|---|---|
| `+0x00` | `abilityId` (string) — **le seul discriminant** |
| `+0x0c` | `activeAbilities.Contains(abilityId)` — **le HINT de voie** |
| `+0x0e` | `Level.IsZero` — ability verrouillée |
| `+0x10` | `IdunBattle.Entities.Enum.AbilityHierarchy` (3 = Tertiary/relique) |

et l'aiguillage :

```
si +0x0e != 0                     -> entree IGNOREE
sinon si +0x0c != 0 (voie ACTIVE) -> UnitAbility$$TryParseActiveAbilityType
      reussite -> TrySetupActiveAbility  -> UnitConfiguration+0xa0 (ActiveAbilities)
      ECHEC    -> TOMBE dans le chemin passif ci-dessous  (pas de `continue`)
chemin passif                     -> TrySetupPassiveAbility
      = UnitAbility$$TryParseTriggeredAbilityType
      reussite -> +0xa8 (PassiveAbilities), ou +0xb0 si hierarchy == 3
      ECHEC    -> RIEN N'EST AJOUTE, sans log
```

⇒ **le repli est ASYMÉTRIQUE** : ACTIVE → PASSIVE existe, PASSIVE → ACTIVE **n'existe pas**.
Une résolution croisée « symétrique » (essayer les deux enums) serait donc infidèle une fois sur
deux : elle monterait `ShroudPsalm`, que le jeu abandonne.

## 2. Le gisement, mesuré

`probe_894_voie_vs_enum.py`, tout re-dérivé du gameconfig VIVANT et des deux tables d'enum du
build : **1382 occurrences / 421 noms** sur les quatre voies (`activeAbilities`,
`passiveAbilities`, `mythicAbilities`, `relicAbilities`) — **2 mal rangées**, **0 ambiguë**
(aucun nom dans les deux enums), **0 orpheline**.

| unité | voie écrite | enum qui porte le nom | routage natif |
|---|---|---|---|
| `eldarBossMauganRaUltra` | `activeAbilities` | `TriggeredAbilityType.Maugetar` 1498 | → `PassiveAbilities` |
| `admecBossBelisarius` | `passiveAbilities` | `ActiveAbilityType.ShroudPsalm` 1181 | → **ABANDONNÉE** |

`mythicAbilities` (11 noms) et `relicAbilities` (25) sont 100 % `TriggeredAbilityType`.

⚠ **L'ordinal ne rattrape rien, et la faute serait SILENCIEUSE** : `ActiveAbilityType.ShroudPsalm`
= 1181 est aussi `TriggeredAbilityType.GuardianOrganism`. Écrire 1181 dans `PassiveAbilities`
monterait un passif étranger, sans erreur. Sur ce build, les deux enums partagent **233**
ordinaux, dont **231 nomment autre chose**.

## 3. Le second verrou : `BC.Abilities` est TYPÉ par son enum

`_ability_names` choisissait aussi le nœud (`ActiveAbilities` / `PassiveAbilities`) par la voie.
Or ces deux dicts sont lus par `IdunBattle.Configuration.AbilitiesConfiguration$$GetActive(ActiveAbilityType)`
et `$$GetPassive(TriggeredAbilityType)` : ce sont des `Dictionary<<enum>, AbilityConfiguration>`,
donc une clé qui ne parse pas fait LEVER `Newtonsoft.Json.Utilities.EnumUtils$$ParseEnum` à la
relecture du BC — le mécanisme documenté pour `Traits`, d'où « [error] initAndStart: system error ».

**Témoin, sur la capture écrite PAR LE JEU** (`data/seed-bc.json`) : `ActiveAbilities` = 131/131
membres d'`ActiveAbilityType`, `PassiveAbilities` = 194/194 membres de `TriggeredAbilityType`,
**0 clé hors enum**. Le témoin **DISCRIMINE** : sur le même fichier, `EnvironmentAbilities` en
porte **135** hors enum et `Traits` **3** — ces deux nœuds-là sont keyés par une string libre. Un
`0` partout ne prouverait rien.

**Contre-épreuve du garde** (mutation du CODE, pas du test) : remettre « la voie dit l'enum » fait
LEVER `synthesize` sur exactement ces 2 unités — étage 3 de
`tests/engine/test_894_routage_ability_par_nom_offline.py`.

## 4. `1173 ArcScourge` — la chaîne qui CAPITALISE

`IdunBattleLogic.Entities.Abilities.Active.ArcScourgeAbility$$ExecuteBehaviour`, mirror LU
(slots `DSLSelectors` : `+0x48 Caster`, `+0x60 Target`, `+0x68 ActiveTarget`) :

```
ChainBehaviour( preselected = Target, jump = <ExecuteBehaviour>b__4_0,
                maxTargets = Direct(maxAdjacentTargets = 3), behaviour = perTarget,
                options{+0x12 = 1 -> coup DIFFERE d'un cran} )
perTarget = If( AreEnemies(Caster, ActiveTarget),
                AttackWithAttackDamage(Particle, nrOfHits = 3)
                  + If( IsMechanical(ActiveTarget), AddEffect(1162 Stunned) + AddPersistentData, 0 ),
                AddPersistentData + Inform(TagKey 0xcb) )
b__4_0(lastTargets) = UnitsWithTrait(sans, Mechanical).Otherwise( Enemies(Caster, sans) )
      avec sans = UnitsWithoutTraits( AdjacentUnits(lastTargets) - Caster, [Steppable, Object] )
puis If( HasEffect(Caster, 1365 MachineVengeance, onlyActive 0),
         IncreaseEffectLevel(Caster, 1365, GetPersistentData("EffectLevel")),
         AddEffect(1365, Caster, level = GetPersistentData("EffectLevel")) )
     + SetPersistentData("EffectLevel", 0)
ExecuteAtomic(..., 0x2a)
```

**Lectures qui ne se devinent pas :**

* le `Func` de saut est invoqué sur `Entities(pickedTargets)` — **toutes** les cibles déjà
  piquées, pas la dernière (`ChainBehaviourBehaviour$$Execute`) ;
* `engine.entities.behaviours.ChainBehaviour` (écrit pour Incursion) **ignore**
  `preselectedTargets` et ne connaît pas le cran différé. Inoffensif pour Incursion (`Null()`),
  **faux** pour 1173 (`Target()`). D'où `ChainBehaviourGeneric` dans `behaviours/chain.py`, qui
  reprend la boucle native exacte ;
* la clé de donnée persistante est le string literal **#7679** du build : `"EffectLevel"` ;
* `UnitsWithoutTraits` (pluriel) est une **INTERSECTION** `op_BitwiseAnd` des `UnitsWithoutTrait` ;
* `Otherwise` = `IdunBattle.DSL.OtherwiseSelector$$Select` : gauche si `Enumerable.Any`, droite sinon.

**Registres, dans le même commit.** `TARGETING_OPTIONS` = `0x4006` =
`TargetMatchesDynamicRule | CasterMatchesDynamicRule | TargetIsEnemy` (décomposition exhaustive,
0 bit résiduel) ; portée `<TargetingRange statics>+0x18` = `RANGE_FROM_CONFIG` → `range` = 2 ;
`forceMeleeTarget` = 1 = `RangedBool.False`. `ABILITY_ATTACK_TYPE` = **2 `Others`**, RELU — alors
que l'ability FRAPPE, ce qui aurait pu faire écrire `DirectTargetAttack`.
La **surcharge** est tranchée par la SIGNATURE : des trois `TargetingOptions..ctor` de
`frida/methods.tsv`, seule celle à six paramètres accepte cet appel — les deux autres sont des
COPIES (`template` seul, `template + additionalRules`).

**Règles dynamiques** (les deux bits ci-dessus les arment) :
* caster — `GetOwnedEffect(caster, 1365)` de niveau `>= effectLevel_2 = 9` ⇒ refus. Le second
  bras (`AlreadyUseThisTurn`) est **NON PORTÉ et nommé** : le port n'a pas de « tour de dernière
  utilisation » par ability ;
* cible — valide si la cible est mécanique, ou si `IBattleQuery$$GetAdjacentUnits` (slot **122**,
  lu dans `metadata/interface_slots.tsv`) rend un ennemi ou un allié mécanique. L'arc exige un
  CONDUCTEUR.

## 5. Confrontation LIVE — ce que la mesure a montré

Board `GB_Belisarius_01` (sa carte, déclarée par le gameconfig), boss placé en **(0,2)** via
`--place` — sans quoi `ArcScourge` n'a **aucune** cible légale et le boss est `moveNone`.

```
cast 1 : 2 maillons x 3 hits (u92 puis u88), DamageProfileType=5, Active_Ability_Type=1173
         -> Effect_Refresh MachineVengeance sur le CASTER, Effect_CurrentLevel=0
cast 2 : 3 maillons x 3 hits (u92, u84, u88)
         -> UpdateEffectLevel e=97 Effect_PreviousLevel=0 Effect_CurrentLevel=0
```

Le niveau **0** n'est pas une divergence : aucune des cibles n'est mécanique, donc la branche
`If(IsMechanical, Stunned + AddPersistentData, 0)` n'est **jamais** prise et le compteur reste à
zéro. C'est une **confirmation forte** de la structure lue — et aucun `Stunned` n'apparaît non
plus, cohérent.

⚠ **Le témoin discrimine, dans le MÊME flux** : au même instant, `ThrillSeekers` sur u88 porte
`Effect_CurrentLevel=1`. Le champ sait valoir autre chose ; le `0` de `MachineVengeance` mesure
donc bien une absence d'incrément.

**Empreinte du boss** : `HP 34277`, `moveNone`, traits `Boss, Immune, BigTarget, Mechanical`,
effet `BigTarget_AdjacentEffect`. Le jeu le publie sous l'id remappé
`GuildBoss10Boss1AdmecBelisarius` (d'où `TACTICUS_ALLOW_ROSTER_DEFICIT=1`).

## 6. Ce qui n'est PAS couvert

* le régime **MÉCANIQUE** (maillon mécanique ⇒ `Stunned` + incrément ⇒ `MachineVengeance` de
  niveau non nul) et le régime **ALLIÉ** (relais) : aucun ennemi du roster par défaut de ce board
  n'est mécanique ;
* la **garde live** : la mesure ci-dessus a été faite à la main (`rl_duel act`), pas sous pytest —
  `applyAction` rend une cascade de groupes dont la forme n'a pas été établie (`#894-r1`) ;
* `1174 SolarAtomizer` et `1172 InvocationOfMachineVengeance` : **NON PORTÉES** (`#894-r2`,
  `#894-r3`), RE disponible pour la seconde ;
* `ShroudPsalm` (1181) : le natif l'**abandonne** pour `admecBossBelisarius` — à confirmer contre
  la voie `GetGuildBossBattleConfig`, qui n'a pas été lue.
