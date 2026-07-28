# case-193 — inventaire RE-DERIVABLE du gisement « playbooks de MOUVEMENT »

Inventaire, pas port. Le livrable est ce document **plus** le script qui le dérive —
`scripts/python/probe_193_move_playbook_inventory.py` — pour qu'il se re-dérive au lieu de se
périmer. Tous les chiffres ci-dessous sortent de ce script (build `gqfc5mff6c`), aucun n'est
recopié d'une fiche antérieure.

```bash
cd scripts/python && python probe_193_move_playbook_inventory.py --list
```

## 1. Les deux chiffres, re-dérivés — et pourquoi l'hérité était FAUX par omission

Le chiffre hérité disait « **84** corps de playbook de mouvement, **7** portés ». Les deux sont à
corriger, mais pas de la même façon.

| | hérité | re-dérivé | verdict |
|---|---|---|---|
| natif | 84 | **108** | INCOMPLET (le 84 est juste, mais ne compte qu'UNE des deux populations) |
| porté | 7 | **8** | PÉRIMÉ (PR #196 a ajouté `GeminaeSuperiaPlaybook` 1048) |

Le gisement natif a **deux** populations, et les confondre est exactement le piège que le
CLAUDE.md décrit :

* **84 corps PROPRES** — la classe possède son itérateur imbriqué
  `<CalculateMovementUtilityInStepsInternal>d__N`. 80 dérivent de
  `IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1`, 4 de
  `IdunBattle.AI.Playbook.AUnitSpecificBehaviourPlaybook`.
* **24 corps HÉRITÉS** — la classe dérive de
  `IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook`1` **sans** itérateur
  propre : elle partage le corps commun et n'override que `GetAdjacent{Friend,Enemy}Utility`.

**La seconde population est INVISIBLE dans `methods.tsv` / `ghidra/functions.tsv`** — corps
dédupliqué, tables indexées par ADRESSE. C'est pour ça que le chiffre hérité s'arrêtait à 84 :
il comptait des itérateurs. **La seconde source indépendante, indexée par NOM, est
`data/symbols/<build>/frida/classes.tsv`** (classes + parent) — c'est elle qui rend les 24
visibles, et c'est elle que le script interroge. Preuve que l'omission était réelle : **4 des 8
playbooks DÉJÀ portés** (`GuardianOrganism` 1181, `RitesOfBattle` 1014, `MartialApotheosis` 1045,
`FabricatorClawArray` 1006) sont dans les 24 — donc absents des « 84 ».

**Exhaustivité, contrôlée et re-jouable.** Le script porte un garde-fou : il ventile TOUTE classe
descendant de `IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1` qui n'est ni un corps propre ni un
concret `AdjacentUnitPreference`, et échoue le compte si elle n'est pas du bruit connu. Résultat
**0 suspect** : les 25 autres descendantes sont les instanciations génériques FERMÉES des mêmes 24
classes (`AdjacentUnitPreferenceTriggeredAbilityPlaybook<XxxAbility>`) plus la base abstraite
`AUnitSpecificBehaviourPlaybook`. Ni doublon, ni omission.

## 2. Le filtre décisif : 34 corps propres ne départagent JAMAIS

Sur les 84 corps propres, **34 sont réduits à `yield Fix64.FromInt(0)`** : le playbook est bien
enregistré, le dispatcher le charge, et il rend 0 quelle que soit la tuile. Pour le mouvement,
c'est du code inerte.

**Comment c'est établi** (proxy trié, verdict confirmé) : un tel corps pèse exactement `0x80`
octets sur ce build. Le script trie par cette taille (delta d'adresses dans `ghidra/functions.tsv`),
et le verdict a été **CONFIRMÉ AU DÉCOMPILÉ sur 13 corps de `0x80`** — `PsykerPlaybook` (1013),
`AggressiveOnslaughtPlaybook` (1248), `BarbedOvipositorPlaybook` (1204),
`FireOfAbsolutionPlaybook` (1017), `RepairEnthusiastPlaybook` (1514), `SuppressiveFirePlaybook`
(1044), `TalonOfHorusPlaybook` (1484), `ElectroShockPlaybook` (1303), `OmnissiahsBlessingPlaybook`
(1299), `SpecialIssueCombiMeltaPlaybook` (1545), `CosmicHorrorPlaybook` (1277),
`RighteousRepugnancePlaybook` (1107), `BoltstormPlaybook` (1090) — **13/13 rendent 0**. Le premier
corps ACTIF au-dessus pèse `0xd0` (`SwornProtector_ProtectPlaybook`, qui appelle bien
`IdunBattle.AI.Playbook.Loki.SwornProtector_ProtectPlaybook$$GetPositionUtility`). La taille reste
un proxy : tout item classé ici se relit au décompilé avant d'être porté.

⚠ **Le piège que ce filtre désamorce** : ces 34 abilities ONT des poids BC bien réels et parfois
gros — `RepairEnthusiast_LikesRepair` = **100**, `SUPPRESSIVEFIRE_TargetWithOverwatch` = **35**,
`BARBEDOVIPOSITOR_DefinitelyKill` = **50**, `ElectroShock_TargetHasAdjacentEnemy` = **50**,
`AggressiveOnslaught_PerFreeTileAfterCharge` = **40**, `FIREOFABSOLUTION_AdjacentEnemy` = **20**.
Trier le gisement au poids BC aurait mis ces items EN TÊTE alors qu'ils ne peuvent rien changer au
tri de tuiles. Leurs poids sont lus ailleurs (face NonOwner, utilité de CAST) — pas ici.

## 3. Gate de confrontabilité, dérivée OFFLINE

* `lineup` **présent dans `BC.Units`** du seed partagé → spawnable tel quel (**106** des 123
  lineup du gameconfig).
* `lineup` **absent** → `catalog_inject.py` (**17** unités, cf. `runner.md` §1bis). Jamais un
  blocage.
* `summons` → via son summoner.
* `npc` SEUL → NON PERTINENT (pas « bloqué » : hors-jeu).

**Un 2e chemin d'octroi a dû être ajouté au script — les RELIQUES.** `items[<relicId>].abilityId`
porte l'ability et `.allowedUnits` les héros qui peuvent l'équiper (ex.
`R_Booster_Crit_KardiocoreGalvanus` → `admecDestroyer`/`admecRuststalker`/`admecMarshall`). Sans ce
chemin, 9 items tombaient à tort en « porteur indirect » — dont `KardiocoreGalvanus`, qui est
**déjà porté**. Le prendre en compte fait passer le gisement confrontable de 38 à **45**.

## 4. Le compte qui compte

```
NATIF    108   = 84 corps propres + 24 corps hérités
PORTE      8
non portés 100 = 34 constant-zero + 46 actifs + 20 corps commun
   dont NON CONFRONTABLES : 12 npc-only + 19 porteur-indirect (chemin d'octroi non établi)
==> GISEMENT REEL (terme non nul ET porteur confrontable) :  45
```

**45**, pas 84 ni 100. C'est le seul chiffre sur lequel dispatcher.

## 5. Classement par valeur décroissante

### Rang A — les 16 « corps commun » confrontables : régime le PLUS LARGE, coût 3 lignes

Régime **déjà établi** (corps commun, déjà porté dans `adjacent_unit_preference.py`) :
`Σ poids sur amis R1(tuile) + Σ poids sur ennemis R1(tuile)`. **Le terme cesse d'être constant dès
que le nombre de voisins R1 qualifiants diffère entre deux tuiles candidates** — c'est-à-dire dans
le cas GÉNÉRAL, sur n'importe quelle géométrie où des unités sont dans les parages. C'est
l'opposé exact du régime `GeminaeSuperia` de #200 (constant en plein plateau, 50 points au bord).
Coût unitaire : un `get_adjacent_{friend,enemy}_utility` de 3 lignes + une entrée au registre.

| # | playbook | id | porteur (1er) | confront. | poids BC |
|---|---|---|---|---|---|
| 1 | `FearedInterrogatorPlaybook` | 1235 | `darkaAsmodai` | lineup-direct | `FearedInterrogator_AdjacentDAFriend`=30 |
| 2 | `DrawFirePlaybook` | 1109 | `blackSmnTerminator` | summon | `DRAWFIRE_AdjacentFriend`=25 |
| 3 | `CursedPlagueBellPlaybook` | 1071 | `deathBlightbringer` | lineup-direct | `_AdjacentChaosFriend`=20 ; `_AdjacentPsychicEnemy`=10 |
| 4 | `HatefulAssaultPlaybook` | 1038 | `blackTerminator` | lineup-direct | `HATEFULASSAULT_AdjacentEnemyRanged`=20 ; `_Default`=10 |
| 5 | `PsychicFortressPlaybook` | 1000 | `ultraTigurius` | lineup-direct | `PSYCHICFORTRESS_AdjacentFriend`=5 (+NonOwner 20) |
| 6 | `RedRampagePlaybook` | 1551 | `bloodTerminator` | lineup-inject | `RedRampage_LikesAdjacentEnemies`=20 |
| 7 | `MedicusMinistorumPlaybook` | 1069 | `adeptHospitaller` | lineup-direct | `MEDICUSMINISTORUM_AdjacentFriend`=15 |
| 8 | `DeathwingKnightPlaybook` | 1510 | `darkaSmnTerminator` | summon | `DEATHWINGKNIGHT_AdjacentDAFriend`=10 |
| 9 | `DeathwingPlaybook` | 1245 | `darkaTerminator` | lineup-direct | `DEATHWING_AdjacentDAFriend`=10 |
| 10 | `NartheciumPlaybook` | 1001 | `ultraApothecary` | lineup-direct | `NARTHECIUM_AdjacentFriend`=5 |
| 11 | `TaintedNartheciumPlaybook` | 1067 | `deathRotbone` | lineup-direct | `TAINTEDNARTHECIUM_AdjacentChaosFriend`=5 |
| 12 | `EcstaticSlaughterPlaybook` | 1472 | `emperFlawlessBlade` | lineup-inject | `EcstaticSlaughter_LikesAdjacentEnemies`=5 |
| 13 | `TimesplinterMantlePlaybook` | 1534 | `necroChronomancer` | lineup-inject | `TimesplinterMantle_LikesAdjacentMechanicalFriends`=5 |

**NON-PRIORITÉS de ce rang, et c'est un résultat** :

* `KustomForceFieldReworkedPlaybook` (1547, `orksBigMek`) — ses **deux** clés BC valent **0**
  (`KustomForceFieldReworked_LikesAdjacentFriends`=0, `_FriendsLikeToBeAdjacent`=0). Le terme est
  rigoureusement nul sur TOUTE géométrie. À ne pas porter.
* `ExplosiveMaladiesPlaybook` (1068), `SpiritualLeaderPlaybook` (1275) — aucune clé BC ne matche
  leur préfixe. Soit le poids est lu sous une clé qui ne suit pas la convention de nommage, soit
  l'override rend 0. **À trancher au décompilé de `GetAdjacent{Friend,Enemy}Utility` avant tout
  port** — c'est 1 décompilation chacun, pas un chantier.

### Rang B — corps ACTIFS confrontables, régime LU au décompilé

Six corps ont été remis en C# ; leur régime est établi, pas déduit.

| playbook | id | porteur | régime — QUAND le terme cesse d'être constant |
|---|---|---|---|
| `DefenderOfTheGreaterGoodPlaybook` | 1155 | `tauShadowsun` (lineup-direct) | `GetAbilityEntities(case)` → `DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector(DSLFactory.Get(casterTile), …)` → `TargetsSelector$$SelectAllUnits` ; `val = n × 25` (0 si n=0). **Mord dès que le nombre d'alliés dans la zone de buff diffère entre candidates.** Poids 25 — le plus fort du rang B en lineup-direct. |
| `ShockAssaultPlaybook` | 1002 | `ultraInceptorSgt` (lineup-direct) | `SHOCKASSAULT_AdjacentSummon` = 25 par summon adjacent. **Mord seulement s'il y a des SUMMONS sur le plateau** — régime conditionné à la présence d'invocations, pas à la géométrie seule. Corps non lu (1264 o). |
| `RelentlessMarchPlaybook` | 1004 | `necroWarden` (lineup-direct) | `IBattleQuery.<slot 0x82>(casterTile, case.unit)` = amis R1, self exclu ; `val = 10 × n`. **Même régime large que le rang A** (corps propre, mais sémantique identique). |
| `DaughterOfTheAbyssPlaybook` | 1329 | `custoAtlacoya` (lineup-direct) | `range = AbilityConfiguration$$GetNumberConstant(cfg, 0x16)` puis `IBattleQuery.<slot 0x78>(…, range)` = amis dans un RAYON configuré ; `val = 20 × n`. **Rayon > 1 ⇒ départage plus souvent que R1**, poids 20. |
| `StandVigilPlaybook` | 1308 | `custoVexilusPraetor` (lineup-direct) | `range = StandVigil.UpdateEffectRangeAbility$$GetCurrentRange(ability)` puis même slot `0x78` ; `val = 5 × n` amis dans ce rayon. **Rayon dynamique (dépend de l'état de l'effet)** ; poids faible mais large couverture. |
| `SanguinaryPriestPlaybook` | 1296 | `bloodSanguinary` (lineup-direct) | amis adjacents avec `UnitExtensions$$IsAffectedByHealType` → +5, **+6 de plus si `UnitExtensions$$IsDamagedUnit`**. Le 1er terme mord dès qu'un ami soignable est R1 ; **le 2e ne mord qu'à partir du moment où un allié a PERDU des PV** — régime de mi-combat, invisible au tour 1. |
| `CamoCloakPlaybook` | 1003 | `ultraEliminatorSgt` (lineup-direct) | `DSLFactory$$Entity(casterTile)` → `DSLFactory$$HasEffect(tile, 1013, 0, 6)` → prédicat BOOLÉEN ; +15 si vrai. **Régime le plus ÉTROIT du rang B : board-dépendant.** Ne mord que si certaines candidates portent l'effet couverture-légère et d'autres non — donc uniquement sur un board qui a ce terrain (cf. `runner.md` §2bis pour choisir le board). ⚠ le `1013` est un **EffectType**, pas un `TriggeredAbilityType` (où 1013 = `PsykerExtraAttack`) : enum à qualifier avant tout port. |

Les 22 autres corps actifs confrontables (`SaviorProtocols` 1120 w=60, `Lifewards` 1049 w=50,
`ECogSupport` 1487 w=30, `VengeanceForTheOmnissiah` 1298 w=30, `FirstAmongTraitors` 1064 w=20,
`PurgeResponse` 1526 w=20, `WatchedOver` 1524 w=20, `LegacyOfCombat` 1319, `NornCrown` 1495,
`ObsessiveAnnunciation` 1443, `RadSaturation` 1202, `AmuletOfTheVoidwyrm` 1464, `BookOfFate` 1461,
`GrimEfficiency` 1490, `IntoxicatingElixir` 1463, `MawClawsOfThyrax` 1469, `NetherRealmCasket` 1462,
`RelicOfLostCadia` 1459, `SereneUnifier` 1145, `SmashaEad` 1246, `SpotterReworked` 1503,
`SwornProtector_Protect` 1075) sont **listés avec porteur, poids et symbole par le script**, mais
leur corps n'a PAS été lu : leur régime est à établir. C'est explicitement hors périmètre de cet
inventaire, pas un oubli. Indice de tri fourni par les clés BC : `_Adjacent*` = ring-1 (régime
large), `_*InRange` / `_Surrounding*` = rayon > 1 (régime large), `_Likes*` = prédicat (régime
potentiellement étroit, à lire).

### Rang C — écartés, avec le motif

* **34 `constant-zero`** (§2) : le playbook ne contribue rien au mouvement. Ne pas dispatcher.
* **12 `npc-only`** : `ArchContaminator` 1168, `CloudOfFlies` 1300, `DaRevolushun` 1283,
  `HuntersInstincts` 1448, `PreCalibratedPurgeSolution` 1293, `PrimarchOfTheFirstLegion` 1511,
  `RunsAround` 1089, `RunsAway` 1088, plus 4 déjà `constant-zero`. **NON PERTINENTS**, pas bloqués.
* **19 `porteur-indirect`** : chemin d'octroi non établi (ni `passiveAbilities`/`activeAbilities`,
  ni relique). Dont les 4 `*SpecificBehaviourPlaybook` — qui, eux, sont un cas **résolu** : leur
  ctor appelle `IdunBattle.AI.Playbook.AUnitSpecificBehaviourPlaybook$$.ctor(this, <index>)` (vérifié
  sur `IdunBattleLogic.Playbook.UnitSpecificBehaviour.CyrusSpecificBehaviourPlaybook$$.ctor`,
  index 0) : ils **ne portent aucun `TriggeredAbilityType`** et leurs poids vivent dans
  `Utilities.Default.UnitSpecificBehaviours` (3 clés seulement). `ability_id = None` est le verdict
  juste pour eux, pas un trou.

## 6. Second volet de la fiche — « kit déclenché non exposé OFFLINE » : PÉRIMÉ, avec preuve

**Le volet est périmé.** `engine/entities/triggered_ability_type.py::triggered_ability_ids(visualId)`
dérive le kit déclenché **offline** depuis `gameconfig.passiveAbilities` → enum
`TriggeredAbilityType`, et `engine/utilities/tile.py::runner_tile_leaf_ctx` (PR #196) le pose dans
`ctx["unit_triggered_abilities"]`, que la feuille `TriggeredAbilities(2)` consomme. Vérifié :
`triggered_ability_ids('adeptCelestine')` = `[1048]`. Il n'y a plus de dépendance live pour lire le
kit.

**Mais la mesure a fait apparaître deux écarts d'ALIMENTATION**, tous deux dérivés par le script
(section `[volet 2]`) :

* **G1 — le slot RELIQUE n'est jamais lu.** `BC.Units[].TertiaryAbility` porte l'ability de la
  relique équipée, et **le seed BC partagé en a déjà 4** : `necroSpyder`→**1462** NetherRealmCasket,
  `orksRuntherd`→1475, `admecMarshall`→**1457** KardiocoreGalvanus, `admecRuststalker`→**1457**.
  Or `triggered_ability_ids` ne lit que `passiveAbilities` : `triggered_ability_ids('admecMarshall')`
  = `[1200]`, **sans 1457**. Conséquence mesurée : **`KardiocoreGalvanusPlaybook`, qui EST au
  registre `TRIGGERED_MOVE_PLAYBOOKS`, est inatteignable côté port** — le dispatcher ne verra jamais
  1457 dans le kit. Même chose d'avance pour `NetherRealmCasketPlaybook` (1462), dont le porteur
  `necroSpyder` a pourtant sa relique équipée dans le seed par défaut. **C'est le résidu le plus
  actionnable de cet inventaire** : il rend opérant un port déjà livré, et il n'exige aucun RE
  nouveau.
* **G2 — les abilities accordées par TRAIT ne sont pas dans ce foyer, et ça n'a AUCUN impact ici.**
  Le foyer appelle `triggered_ability_ids` et non `kit_triggered_ability_ids` (qui, lui, ajoute
  `TRAIT_TRIGGERED_ABILITY_IDS`). Vérifié : les ids concernés (1013 `PsykerExtraAttack`, 1142
  `TerminatorArmour`, 1021 `Explodes`, 1074 `PutridExplosion`) **n'ont aucun playbook de mouvement
  actif** — 1013 est précisément l'un des 34 `constant-zero`, les trois autres n'ont pas de classe
  playbook du tout. **Ne pas y brûler d'agent.**
* Écart mineur consigné : 4 npc nécrons du seed portent `PassiveAbilities=[1008]` que le gameconfig
  ne rend pas. Sans playbook de mouvement associé → sans effet ici.

## 7. Ce que cet inventaire n'établit PAS

* **Le régime de 22 des 29 corps actifs confrontables** (rang B, 2e paragraphe) : porteur, poids et
  symbole sont listés, le corps n'est pas lu.
* **Le chemin d'octroi des 19 `porteur-indirect`** hors reliques et hors `*SpecificBehaviour` —
  notamment `Spotter` 1047, `CloseCombatWeakness` 1130, `Loki_Camouflage` 1131, `UnbridledCarnage`
  1150 / `UnbridledCarnageReworked` 1259, `LethalMiasma` 1058, `KustomForceField` 1102,
  `PriorityReclamation` 1295, `RadZoneCorps` 1294, `RedemptionOfTheRisen` 1522. Ils ne sont ni dans
  `passiveAbilities`, ni dans `items[].abilityId`. Un 3e chemin existe (sous-ability d'une active,
  octroi par effet) et n'a pas été tracé.
* **Aucune confrontation LIVE** : le host Frida était éteint pendant tout ce travail
  (`127.0.0.1:8080` refusé). La gate de confrontabilité est donc dérivée du seed BC + gameconfig
  (§3), **pas** croisée avec `rl_duel.py --list-pool`. Les deux devraient coïncider — le seed BC est
  la source du pool — mais ce n'est pas vérifié.
* **Le cap `vtbl+0x228/0x238`** du corps commun (jamais observé liant) reste non répliqué, inchangé
  par ce cas.
