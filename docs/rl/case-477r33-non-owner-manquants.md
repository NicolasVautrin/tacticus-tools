# #477-r33 — le recensement était faux de trois façons, et **un seul** confond était armé au seed

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp + un runner à la fois. Aucune injection.

```powershell
python scripts/python/probe_477r33_non_owner_registry_gaps.py --offline-only
python scripts/python/probe_477r33_non_owner_registry_gaps.py --board MC1_67 --seed 777 --montage kardio
python scripts/python/probe_477r33_non_owner_registry_gaps.py --board MC1_67 --seed 777 --montage kardio-gate
python scripts/python/probe_477r33_non_owner_registry_gaps.py --board MC1_67 --seed 777 --montage bookoffate
python scripts/python/probe_477r33_non_owner_registry_gaps.py --board MC1_67 --seed 777 --montage norncrown
python scripts/python/probe_477r33_non_owner_registry_gaps.py --board MC1_67 --seed 777 --montage norncrown-gate
python -m pytest scripts/python/tests/engine/test_477r33_non_owner_playbooks_live.py -q
```

## 1. La réponse à la question binaire

**Un seul** des manquants est armé sans qu'on l'ait demandé : `1457 KardiocoreGalvanus`, équipée
**au seed** sur `admecMarshall` **et** `admecRuststalker`. Elle vaut **+20** sur les tuiles
adjacentes à son porteur ami, sous le gate `IsMechanical(case.Unit)`. Deux autres sont armables sur
nos montages par une seule ligne (`--equip-relic`) : `1461 BookOfFate` (5) et `1495 NornCrown` (10).
Les trois sont **portées, inscrites au registre et confrontées live**.

Le décompte des confonds **armés sans aucun montage** passe de **3 à 1** — le dernier,
`1064 FirstAmongTraitors` sur `blackAbaddon`, est gaté sur un trait `Chaos` que **0 unité sur les
1 083** du gameconfig porte (`lineup` + `npc` + `summons`), donc son terme est inerte.

## 2. Le compte hérité était faux — trois fois, et toujours par la même cause

Le résidu #477-r31 annonçait « **13** des **25** `*NonOwnerPlaybook` ». Re-dérivé
(`probe_477r33 --offline-only`, filtre sur le **PARENT** dans `data/symbols/<build>/frida/classes.tsv`) :

| | hérité (#477-r33 tel qu'ouvert) | mesuré | cause |
|---|---|---|---|
| concrets de la famille | 25 | **28** | compte par NOM — le vice que #433-r4-r3-r1 avait déjà corrigé |
| faces MOVE | (implicite 25) | **24** | 3 ATTACK + 1 REPAIR ne passent pas par cette feuille |
| « manquants » | 13 | **11** (+1 écrite hors registre) | voir ci-dessous |

Les trois erreurs de la liste des « 13 » :

1. **trois faces ATTACK y figuraient** — `1453 ShieldOfFaith`, `1500 WayOfTheShortBlade`,
   `1523 NoHidingFromTheWatchers`. Leur `Calculate*UtilityInSteps` est
   `CalculateAttackUtilityInSteps` : elles sont consommées par
   `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext`,
   pas par la face MOUVEMENT ;
2. **deux concrets manquaient** — `CabalOfSorcerersPlaybook` (1496) et `WisdomOfTheAncientsPlaybook`
   (1451) ne portent pas le suffixe `NonOwnerPlaybook`, donc le grep les rate **deux fois** (leurs
   state machines nichées ne portent pas la chaîne non plus) ;
3. **`1522 RedemptionOfTheRisen` y était comptée comme manquante** alors qu'elle est **écrite** et
   volontairement hors registre (0 porteur, cliquet #419).

Et une erreur d'attribution, qui changeait le verdict opérationnel : le résidu écrivait
« `orksRuntherd` → `MastersOfManoeuvre` ». **Faux.** `BC.Units[].TertiaryAbility` d'`orksRuntherd`
vaut **1475 = `SupaCyborkBody`**, qui n'a **aucun** `*NonOwnerPlaybook` dans le binaire — donc
**zéro** confond. Les quatre reliques du seed se ventilent en trois états, pas en un :

| unité | relique | id | état |
|---|---|--:|---|
| `admecMarshall` | `KardiocoreGalvanus` | 1457 | **confond armé** → porté ici |
| `admecRuststalker` | `KardiocoreGalvanus` | 1457 | **confond armé** → porté ici |
| `necroSpyder` | `NetherRealmCasket` | 1462 | déjà porté (#433-r4-r3-r1) |
| `orksRuntherd` | `SupaCyborkBody` | 1475 | **aucun playbook non-owner** — rien à porter |

`probe_477r33` rend ces trois états explicitement : rabattre « pas dans le registre » sur
« non porté » ferait lire `1475` comme une entrée du registre, ce qu'elle n'est pas.

## 3. Le recensement complet des 24 faces MOVE

Poids **résolus au littéral** (`probe_212_bc_key_literals.py` sur la state machine, ou sur le
`.cctor` quand la clé vit dans un champ statique), confrontés à `data/seed-bc.json` **et** au
gameconfig vivant. Les 15 portées ne sont pas reprises ici (elles ont leurs case-docs).

| id | classe | poids | gate du corps | porteurs | atteignable |
|--:|---|--:|---|---|---|
| **1457** | `KardiocoreGalvanusNonOwnerPlaybook` | **20** | `IsMechanical(mover)` | `admecMarshall`, `admecRuststalker` (pool, **équipés au seed**), `admecDestroyer` | **PORTÉ + CONFRONTÉ** |
| **1461** | `BookOfFateNonOwnerPlaybook` | **5** | *aucun* | `blackPossession`, `thousInfernalMaster`, `thousSorcerer` (pool, relique) | **PORTÉ + CONFRONTÉ** |
| **1495** | `NornCrownNonOwnerPlaybook` | **10** | `Psyker` **ou** `Summon` (mover) | `tyranNeurothrope` (pool, relique) | **PORTÉ + CONFRONTÉ** |
| 1064 | `FirstAmongTraitorsNonOwnerPlaybook` | 20 | `HasTrait(mover, Chaos)` + `GetDistance(tuile, tuiles owner) <= GetRange` | `blackAbaddon` (pool, **passif**) | porteur OUI, **gate mort** (0 unité `Chaos`) |
| 1469 | `MawClawsOfThyraxNonOwnerPlaybook` | 5 | adjacence + `HasTrait(mover, Summon)` + slot `0x92` | `tyranWingedPrime`, `genesPatriarch`, `tyranTyrantGuard` (pool, relique) | relique + mover SUMMON |
| 1478 | `SabreOfSacrificeNonOwnerPlaybook` | 35 | `!StaysOnTile` + adjacence + `SabreOfSacrificeAbility$$IsAffectedSummon` (sélecteur DSL) | `astraDreir` (pool, relique) | relique, corps DSL |
| 1496 | `CabalOfSorcerersPlaybook` | 20 | `rarity == Mythic` + `Psyker`, puis voisins amis `Hero`+`Psyker` | `thousDaemonPrince` (**MoW**) | MoW |
| 1451 | `WisdomOfTheAncientsPlaybook` | 20 | `rarity == Mythic`, puis voisins amis `Hero` | `ultraDreadnought` (**MoW**) | MoW |
| 1508 | `MastersOfManoeuvreNonOwnerPlaybook` | 25 | `HasRarity(mover, Mythic)` + un ami adjacent `DarkAngels` **et** `Mythic` | `darkaStormSpeeder` (**MoW**) | MoW + **canal `rarity` absent du `ctx`** |
| 1526 | `PurgeResponseNonOwnerPlaybook` | 20 | `HasFaction(mover, LeaguesOfVotann)` | `votanSmnSteeljack` (summon), npc | **0 unité Votann au pool** |
| 1531 | `HaywireMineNonOwnerPlaybook` | **−50** ami / **−30** ennemi | occupant `Steppable` de la tuile dont l'`unitId` == `GetStringConstant(cfg, 8)` | `astarCyrus` (**hors pool**), `astarSmnHaywireMine` | hors pool + question du `<slot 4>` (§7) |
| 1522 | `RedemptionOfTheRisenNonOwnerPlaybook` | 20 | `HasFaction(mover, DarkAngels)` | **aucun** | **écrite, hors registre** (dead code, #419) |

## 4. Les trois corps portés, et ce que le décompilé tranche

`KardiocoreGalvanus` — SM `case @+0x20, playbook @+0x28, owner @+0x30` :

```
if (case.unit == null)                       { yield Fix64.Zero; yield break; }
if (!UnitExtensions.IsMechanical(case.unit))   yield break;
if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(owner, case.MovementTile))
    yield return GetUtilityValue("KardiocoreGalvanus_AdjacentFriendly");   // 20
```

⚠ `IsMechanical` **n'est pas** `HasTrait(Mechanical)` : c'est la chaîne de trois `HasTrait` en OU
court-circuité (`Mechanical`, `LivingMetal`, `Vehicle`). C'est **observable** — un `Vehicle` non
`Mechanical` franchit ce gate et **pas** celui de `NetherRealmCasketNonOwnerPlaybook`, qui teste le
trait nu. Les deux classes cohabitent au registre : confondre les deux lectures diverge selon le
mover, sans jamais lever. Exercé offline dans les deux sens.

`BookOfFate` — SM `playbook @+0x20, owner @+0x28, case @+0x30`, une **quatrième** disposition,
distincte des trois déjà mesurées (#433-r4-r3 en a mesuré deux, #433-r4-r3-r1 une troisième) :

```
if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(owner, case.MovementTile))
    yield return GetUtilityValue("BookOfFate_AdjacentSummons");            // 5
```

**Aucun gate** — pas même `case.unit == null`. ⚠ Le « Summons » du nom de clé n'est **pas** porté
par le corps : il n'y a aucun `HasTrait(Summon)`. Le nom de clé décrit l'intention du designer, pas
la condition ; le lire comme un gate ferait disparaître le terme pour tout mover non-summon.

`NornCrown` — SM `case @+0x20, playbook @+0x28`, et la méthode-usine **n'écrit pas `owner`** :

```
if (case.unit == null) yield break;
if (!HasTrait(case.unit, 0x3ea) && !HasTrait(case.unit, 0x2)) yield break;   // Psyker OU Summon
units = Query.<slot 0x79 = GetSurroundingFriends, arite 4>(
            case.unit, TExtensions.ToList(case.MovementTile), 2, true);
if (Any(units, f => HasTrait(f, 0x7e8)))                                     // Synapse
    yield return GetUtilityValue("NornCrown_SummonsAndPsykers");             // 10
```

Quatre lectures qui ne se devinent pas :

* **le corps ne lit ni `owner` ni sa position** — la méthode-usine ne stocke même pas l'argument.
  Le terme ne pèse que le voisinage du MOVER ;
* **le gate est une DISJONCTION**, à l'inverse de `RelicOfLostCadia` qui conjugue `Imperial ET Summon` ;
* **le disque est PUREMENT géométrique** : `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`
  n'a **aucune** porte d'élévation, donc `battle_query.is_surrounding` et surtout pas
  `are_entities_adjacent` ; `includeCenter = true` (littéral `1`), rayon `2` (littéral) ;
* **l'acteur n'est pas exclu** de son propre voisinage, et le mover est encore sur son ORIGINE
  pendant tout le sweep. Un mover `Synapse` se satisfait donc lui-même.

⚠ **Le NOM d'un slot ne dit ni le camp ni la surcharge.** `AreEntitiesAdjacent` occupe les slots
96/97/98 et `GetSurroundingFriends` les slots 129..132 (arité 2) — c'est le **type des arguments au
call-site** qui fixe la surcharge, jamais l'indice ni le nom. Faute commise deux fois dans cette
lignée (#477-r29 puis #477-r31), non re-commise ici.

## 5. Les cinq montages, et pourquoi le confond de #477-r31 devient le mesurande

Géométrie `camp` de `probe_477r31` (zone plate, cible neutre au centre, porteur ALLIÉ et porteur
ENNEMI en miroir) — **réutilisée, pas réinventée** : c'est la seule dont il est *mesuré* que
`scorerTileTermTrace` couvre les DEUX bras (il ne voit que le tier COMPARABLE, les tuiles
d'ATTAQUE ; un montage dont un bras n'est pas observé ne sépare rien).

* **`kardio`** — la géométrie `camp` **sans** `unequip_relic`. Là où #477-r31 devait retirer la
  relique pour mesurer sa propre feuille, ici elle **est** le mesurande.
* **`kardio-gate`** — même géométrie, carrier NON Mechanical.
* **`bookoffate`** / **`norncrown`** — même géométrie, la relique posée des DEUX côtés
  (`catalog_inject.equip_relic`, état 2) ; c'est le porteur **ennemi** qui exerce le pré-gate.
* **`norncrown-gate`** — même montage, mover ni `Psyker` ni `Summon`.

### Le choix des carriers est DÉRIVÉ, et deux l'ont été par une mesure rouge

* `orksNob` (le carrier de #477-r29) a été essayé pour `kardio-gate` et **rejeté** : il porte
  `IdunBattle.AI.Playbook.Loki.SmashaEadPlaybook$$CalculateMovementUtilityInStepsInternal` et
  `IdunBattle.AI.Playbook.Loki.UnstoppableMomentumReworkedPlaybook$$EvaluateNonComparable`, dont le
  port ne rend rien → `X_nat` valait **+1 uniforme** sur 7 tuiles des DEUX bras. Ce terme est
  orthogonal au mesurande (il ne dépend pas du camp) mais il interdit l'accord absolu.
  `eldarAutarch` est le **seul** héros non-Mechanical du pool dont aucune des deux abilities n'a de
  `*Playbook$$.ctor` dans le binaire — critère **dérivé** d'un balayage de `ghidra/functions.tsv`.
* `eldarAutarch` a ensuite été essayé comme carrier de `bookoffate` et **rejeté** à son tour : sa
  trajectoire native ne hooke que le bras ENNEMI (2 puis 5 tuiles). Le carrier retenu est
  `admecDominus`, dont il est **mesuré** qu'il hooke les deux bras sur cette géométrie ; son gate
  `AttractMechanicals` y est **inerte par algèbre** (aucune unité du montage ne porte
  `ActiveAbilityType.DoctrinaImperatives`), ce que la mesure confirme (`X_nat = 5`, pas 15).

## 6. Les mesures

`kardio` / `MC1_67` / 777 — 11 tuiles hookées, **0 désaccord**. `X_nat = AttractMechanicals(10) +
KardiocoreGalvanus(20)` :

| tuile | nA | nE | `X_nat` | `X_port` |
|---|--:|--:|--:|--:|
| (2,6) (3,7) (3,8) | 1 | 0 | **30** | 30 |
| (5,7) (5,8) (6,6) | 0 | 1 | **0** | 0 |
| (3,6) (4,5) (4,6) (5,6) (6,5) | 0 | 0 | 0 | 0 |

`bookoffate` / `MC1_67` / 777 — mêmes 11 tuiles, `X_nat = 5` sur le bras ALLIÉ, `0` sur l'ennemi.

`norncrown` / `MC1_67` / 777 — 13 tuiles, `X_nat = 10` exactement là où un ami `Synapse` est dans le
disque de rayon 2 ; **0** sur (3,3), qui n'a qu'un `Synapse` **ennemi** dans son disque.

`kardio-gate` et `norncrown-gate` — `X_nat = 0` sur **toutes** les tuiles, les deux bras compris.

### Contre-épreuve — `a_mordu` rendu SÉPARÉMENT du verdict

| modèle | `kardio` | `kardio-gate` | `bookoffate` | `norncrown` |
|---|--:|--:|--:|--:|
| `PORT` | 0 / 11 | 0 / 8 | 0 / 11 | 0 / 13 |
| `CAMP-DEUX` | **3** | 0 (inerte) | **3** | **1** |
| `CAMP-ENNEMI` | **6** | 0 (inerte) | **6** | — |
| `SANS-GATE` | 0 (non séparé) | **2** | — | 0 (non séparé) |
| `RAYON-1` | — | — | — | **7** |
| `SANS-SELF` | — | — | — | 0 (inerte par algèbre) |
| `PRE-GATE-OFF` | — | — | — | **10** |
| `COUNT (x n)` | 0 (non séparé) | 0 (inerte) | 0 (non séparé) | — |
| `ABSENT` = l'état du port avant cette tranche | **3** | 0 | **3** | **10** |

La ligne `ABSENT` **chiffre le bug corrigé** : 3 tuiles × 20 sur `kardio`, 3 × 5 sur `bookoffate`,
10 × 10 sur `norncrown`.

`RAYON-1` (7 tuiles) prouve le littéral `2` du call-site ; `PRE-GATE-OFF` (10) prouve que le
pré-gate `IsFriend` d'`IterateAbilities` est bien appliqué — sans lui, le dispatcher sommerait le
terme **une fois par porteur**, ennemi compris, et doublerait la valeur (le corps de 1495 ne lit
pas le porteur).

**Deux inerties, déclarées et assertionnées DANS LES DEUX SENS** :
* montages `*-gate` : le gate coupe ⇒ **tout** mutant qui n'y touche pas est inerte, et le probe le
  vérifie mutant par mutant plutôt que de se taire ;
* `norncrown` : le carrier `thousInfernalMaster` n'est pas `Synapse` ⇒ `SANS-SELF` ne **peut pas**
  mordre. Le volet self est donc **exercé offline**
  (`test_NORNCROWN_gate_DISJONCTIF_rayon_2_et_self_INCLUS`, branches `self_syn` / `self_loin`).

## 6bis. Une contrainte PRÉ-EXISTANTE, trouvée par le re-jeu : `scorerDamageTrace` est SESSION-GLOBAL

`scorerDamageTraceOn` / `scorerDamageTraceOff` sont des interrupteurs **session-globaux** (seuls les
`*Dump` filtrent par `runnerId`). Deux processus pytest qui les arment et les désarment en même
temps se coupent l'un l'autre : le perdant de la course mesure avec les hooks **désarmés**, son
`X_nat` est tronqué, et le rouge tombe sur un cas **aléatoire**. Trois passes successives ont ainsi
accusé trois victimes différentes (`MC1_67-777-kardio`, puis `C4_09-31337-kardio`, puis
`477r29/MC1_67-777`), toutes **vertes en solo** — le symptôme classique d'une ressource partagée,
qu'on aurait pu prendre pour une interaction avec du code mergé pendant le rebase.

**A/B à un seul facteur**, mesuré :

| bras | ce qui tourne en parallèle | résultat |
|---|---|---|
| A | `test_477r33_…` + `test_433_r4_r3_r1_…` (n'arme **pas** ces hooks) | **41 + 38 verts** |
| B | `test_477r33_…` + `test_477r31_…` (les arme) | `477r31` → **6 failed / 21 passed** |
| — | les trois fichiers de la famille, **séquentiels** | **83 verts en 107 s** |

La contrainte est **pré-existante et partagée** : `probe_477r29` et `probe_477r31` l'avaient déjà,
elle n'avait jamais été nommée (les deux tranches les avaient validés en solo). La discipline
« 4 fichiers en parallèle » du `CLAUDE.md` ne s'applique donc pas à cette famille. Nommé dans
l'en-tête de la garde ; un rouge de cette famille en passe parallèle **n'accuse pas le port**, et le
premier geste est de le rejouer SEUL.

## 7. Ce qui est livré

* `engine/playbook/non_owner.py` — trois classes (`KardiocoreGalvanusNonOwnerPlaybook`,
  `BookOfFateNonOwnerPlaybook`, `NornCrownNonOwnerPlaybook`) + leurs entrées de registre ; le
  commentaire de tête du registre corrigé (le compte « 25 » s'y était re-glissé) ;
* `probe_477r33_non_owner_registry_gaps.py` — recensement re-dérivé (28 concrets par le PARENT,
  faces créditées depuis le parent pour les 10 du corps partagé, ids relus au `.ctor`, clés BC
  résolues au littéral), **décompte des confonds**, et les 5 montages live ;
* `test_477r33_non_owner_playbooks_live.py` — 5 étages offline + 6 étages live × 6 cas.

## 8. Ce qui n'est PAS couvert

* **Les 8 faces MOVE restantes** (résidu **#477-r35**) : `1064`, `1451`, `1469`, `1478`, `1496`,
  `1508`, `1526`, `1531`. Leur RE est faite (§3) ; aucune n'est armée sans montage.
* **Le `<slot 4>` de `HaywireMineNonOwnerPlaybook`.** Son corps branche explicitement
  `IsFriend(case.unit, owner)` → clé `HaywireMine_FriendlyAvoidMine` (**−50**) *sinon*
  `HaywireMine_EnemyAvoidMine` (**−30**). Or le pré-gate `<slot 4> || IsFriend` mesuré par
  #433-r4-r3 vaut `false` **sur les trois classes qu'il a lues** — si c'était vrai ici aussi, la
  branche ENNEMI serait **inatteignable**, ce qui contredirait l'existence de sa clé. **Il faut
  relire le `methodPointers` de CETTE classe avant de la porter** : c'est le seul cas de la famille
  où le corps rend le slot observable.
* **Le canal `rarity`** manque au `ctx` des feuilles de tuile — `1451`, `1496` et `1508` en
  dépendent (`HasRarity(u, 5)` / `BaseUnitComponent+0x74 == 5`, `idun.meta.Rarity.Mythic`).
* **La face ATTACK de `TriggeredAbilitiesNonOwner`** (`<EvaluateAttackInSteps>d__1`) n'est pas
  portée : ses 3 classes (`ShieldOfFaith`, `WayOfTheShortBlade`, `NoHidingFromTheWatchers`) sont
  hors de cette feuille. Résidu pré-existant, non ouvert ici.
* **Le régime SPAWN** de la feuille 4 reste muet (le `ctx` de spawn ne porte aucune clé de sujet) —
  résidu pré-existant, inchangé. `BookOfFate` y serait le premier concerné : son corps ne teste
  même pas `case.unit == null`.
* **Les entités MULTI-TUILES** : le port compare deux positions là où `AreEntitiesAdjacent` compare
  deux listes. Aucun porteur des trois abilities n'est multi-tuiles ; le mover, lui, pourrait l'être.

## Résidus

- **#477-r35 — 8 faces MOVE `*NonOwnerPlaybook` restent non portées** (§3, §8). Aucune n'est armée
  sans montage ; trois attendent un canal `rarity`, une (`1531 HaywireMine`) attend la relecture de
  son `<slot 4>`, une (`1526 PurgeResponse`) n'a aucun mover `LeaguesOfVotann` au pool.
