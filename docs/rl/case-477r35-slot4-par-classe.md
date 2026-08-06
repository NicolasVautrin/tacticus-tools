# #477-r35 — le `<slot 4>` n'est pas une constante de famille, et le dispatcher en avait fait une

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp + un runner à la fois. Aucune injection.

```powershell
python scripts/python/probe_477r35_non_owner_gates_montables.py --offline-only
python scripts/python/probe_477r35_non_owner_gates_montables.py --board MC1_67 --seed 777 --montage purge
python scripts/python/probe_477r35_non_owner_gates_montables.py --board MC1_67 --seed 777 --montage purge-gate
python scripts/python/probe_477r35_non_owner_gates_montables.py --board MC1_67 --seed 777 --montage haywire
python -m pytest scripts/python/tests/engine/test_477r35_non_owner_gates_montables_live.py -q
```

## 1. Le résultat qui vaut la tranche

`#433-r4-r3` avait lu le `<slot 4>` sur **trois** classes, l'avait trouvé `false`, et le port en
avait fait une **règle de famille** : `TriggeredAbilitiesNonOwnerUtility.evaluate` écartait *tous*
les porteurs ennemis d'un bloc, **avant même de charger le playbook**.

`HaywireMineNonOwnerPlaybook` porte `slot 4 == true`. Son corps trivial est
`UnityEngine.U2D.IK.Solver2D$$DoValidate` (`return 1`) ; les deux classes qui surchargent
explicitement en `false` portent `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`
(`return 0`). Conséquence **mesurée** sur la tuile minée du montage `haywire` :

| | `X_nat` | `X_port` avant | `X_port` après |
|---|--:|--:|--:|
| tuile `(2,7)`, mine amie | **−130** | −100 | **−130** |

Il manquait exactement **−30** = `HaywireMine_EnemyAvoidMine`. Aucune autre ability du montage n'a
de `*NonOwnerPlaybook` (vérifié sur les six ids présents : `1542 HaywireMineSteppable`,
`1246 SmashaEad`, `1234 GetStuckIn`, `1518 BeastSlayer`, `1004 RelentlessMarch`,
`1010 LivingMetalRepair`) — le terme ne pouvait venir que de là.

## 2. Le premier critère de lecture rendait VERT, et c'est le vrai enseignement

Le probe a d'abord lu le bloc `methodPointers` en postulant qu'**il commence au `.ctor`** : « `.ctor`
+ `Calculate*` + les six corps de la state machine ⇒ aucun override ». Les **six** classes relues le
satisfaisaient, `HaywireMine` comprise. Le verdict « slot 4 = false partout » est donc sorti
**VERT**, et il était faux.

Le discriminant est l'entrée **qui PRÉCÈDE** le `.ctor` :

| classe | entrée avant le `.ctor` | slot 4 |
|---|---|:--:|
| `HaywireMineNonOwnerPlaybook` | `Solver2D$$DoValidate` = `return 1` | **true** |
| `ECogSupportPlaybookNonOwnerPlaybook` | `UnityAdsIdentifier$$get_UserId` = `return 0` | false |
| `KustomForceFieldReworkedNonOwnerPlaybook` | idem | false |
| `PsychicFortressNonOwnerPlaybook` | `…get_Current` d'une AUTRE classe → aucun override | false (hérité) |
| `MawClawsOfThyraxNonOwnerPlaybook` | idem | false (hérité) |
| `PurgeResponseNonOwnerPlaybook` | idem | false (hérité) |

Deux corollaires :

* le `d__5` de la state machine de `HaywireMine` (vs `d__2` partout ailleurs) **ne signalait pas**
  la méthode en plus — c'est un compteur du compilateur C#. S'y fier aurait donné la bonne réponse
  pour la mauvaise raison ;
* **c'est la MESURE LIVE qui a renversé le verdict offline**, pas une relecture. Le port était déjà
  écrit, commité, et son probe vert.

Le port porte désormais `SLOT_4` **par classe** (`engine/playbook/non_owner.py`), et le pré-gate du
dispatcher le lit sur le playbook :

```python
if not (getattr(pb, "SLOT_4", False) or is_friend):
    continue          # `!<slot 4> && !IsFriend` = IsInvalidEntityForPlaybook
```

## 3. Les trois faces portées, et ce que le décompilé tranche

`PurgeResponse` (1526) — SM `case @+0x20, playbook @+0x28, owner @+0x30` :

```
if (case.unit == null) yield break;
if (!UnitExtensions.HasFaction(case.unit, 0x14)) yield break;      // UnitFaction.LeaguesOfVotann
if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(case.MovementTile, owner))
    yield return GetUtilityValue("PurgeResponse_FriendlyVotannLikeSteeljack");   // 20
```

* le gate porte sur la **faction du MOVER**, jamais sur le porteur — le canal existait déjà
  (`ctx.unit_faction`) ;
* `0x14` est qualifié par le **type déclaré** lu dans `frida/methods.tsv`
  (`HasFaction(unit, faction: IdunBattle.Entities.Enum.UnitFaction)`), pas par son ordinal ; la
  surcharge jumelle prend un `System.String` ;
* l'ordre des arguments d'adjacence est **inversé** par rapport à `KardiocoreGalvanus` — sans
  effet (le prédicat est symétrique), mais c'est la **surcharge** qui fixe le slot, jamais l'ordre.

`MawClawsOfThyrax` (1469) — le **seul** corps de la famille à porter **deux branches** :

```
if (case.unit != null) {
    if (AreEntitiesAdjacent(case.MovementTile, owner)
        && HasTrait(case.unit, 0x2)                                  // UnitTrait.Summon
        && Query.<slot 0x92 = AreFriends, arite 3>(case.unit, owner, 0))
        yield return GetUtilityValue("MawClawsOfThyrax_AdjacentSummons");   // 5
    yield break;
}
if (case.parent == null) yield break;                                // BRANCHE SPAWN
if (AreEntitiesAdjacent(case.MovementTile, owner) && AreFriends(case.parent, owner, 0))
    yield return GetUtilityValue("MawClawsOfThyrax_AdjacentSummons");
```

* le slot `0x92` est **`AreFriends`**, résolu par la vtable runtime
  (`probe_27_4g_battlequery_slots.py --slots 0x92` : slot d'interface `0x92` + 4 = index `0x96`).
  Le voisin `0x8e` est `GetAllEnemiesOf` — se tromper d'un slot donnait un prédicat de camp
  **inversé** ;
* son 3ᵉ argument `0` est un **`UnitTeamSelectionType`**, pas un booléen (type déclaré dans
  `frida/methods.tsv`). Le mirror **n'existait pas** : il est créé et inscrit au registre de
  `probe_313` dans le même commit ;
* ce gate `AreFriends` est **redondant, et c'est mesuré** :
  `BattleQuery$$AreFriends(a, b, sel)` délègue à `UnitExtensions$$IsFriend(a, b, sel, State)`, dont
  la branche `sel == ByCurrentTeam` est mot pour mot le corps de la surcharge à trois arguments —
  celle du pré-gate, appliquée au même sujet. Il ne peut jamais couper. Le port le mirrore quand
  même.

`HaywireMine` (1531) — SM `case @+0x20, playbook @+0x28, owner @+0x30` :

```
if (case.unit == null) yield break;
if (!TileExtensions.GetSteppableUnit(case.MovementTile, State, out u)) yield break;
if (!UnitExtensions.HasUnitId(u, cfg.GetStringConstant(8), State)) yield break;
yield return GetUtilityValue(IsFriend(case.unit, owner, State)
                             ? "HaywireMine_FriendlyAvoidMine"    // -50
                             : "HaywireMine_EnemyAvoidMine");     // -30
```

* le gate ne porte **ni sur le mover ni sur le porteur**, mais sur l'**occupant de la tuile
  candidate** ; `HasUnitId` compare via
  `idun.shared.UnitNamingConventions$$GetUnitIdWithoutRarity`, donc **sans suffixe de rareté** ;
* `8` est un **`AbilityConstantType`** (type déclaré :
  `AbilityConfiguration.GetStringConstant(constantType: AbilityConstantType)`), et vaut
  `unitToSpawn` = `"astarSmnHaywireMine"` au gameconfig vivant.

## 4. Les trois voies de montage, et les deux verrous

| face | porteur | voie de montage | confronté |
|---|---|---|---|
| 1526 | `votanSmnSteeljack` (summon), `votanNpc2Steeljack` (npc) | **greffe** du passif sur `necroWarden` + **injection catalogue** d'un mover Votann (les 9 sont hors pool) | **LIVE** |
| 1531 | `astarCyrus` (hors pool), `astarCyrus_LHE` (npc) | **greffe** du passif — qui fait *spawner* la mine | **LIVE** |
| 1469 | relique de `genesPatriarch`/`tyranParasite`/`tyranTyrantGuard`/`tyranWingedPrime`, **les 4 au pool** | `--equip-relic` + trait `Summon` **accordé** au mover | **OFFLINE** (verrou §5) |

Le choix du carrier de `purge` a été **payé par une mesure rouge**, comme celui de #477-r33 : le
premier essayé, `votanUthar`, porte
`IdunBattle.AI.Playbook.Loki.GrimEfficiencyPlaybook$$CalculateMovementUtilityInStepsInternal`, que le
port ne rend pas → **+5 sur 5 des 11 tuiles**. Le critère est dérivé d'un balayage de
`ghidra/functions.tsv` sur les abilities des **5** héros Votann : `votanUthar` et `votanChampion` ont
une face MOUVEMENT ; `votanBeserk`, `votanIronmaster` et `votanMemnyr` n'ont qu'un
`EvaluateNonComparable`. Retenu : **`votanBeserk`**.

Deuxième mesure rouge, la même que #477-r33 : **sans ami neutre**, la trajectoire ne hooke qu'un
bras (4 tuiles, bras AMI = 0). Il est replacé.

## 5. Les deux verrous, mesurés — et ce ne sont pas des échecs de montage

**`1469 MawClawsOfThyrax` — verrou STRUCTUREL.** Son gate est `HasTrait(mover, Summon)`. Or
`IdunBattle.Entities.UnitExtensions$$IsAutomatic(unit)` vaut exactement
`HasTrait(0x2 Summon) || HasTrait(0xd Object)`, **sans aucune exemption** (pas même `Hero`), et
c'est le seul filtre de `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute`. **Tout** mover
qui franchit le gate de 1469 est donc joué au turn-start et n'entre **jamais** dans la trajectoire
d'activation que `aiStepDryRun` marche. Mesure : trait `Summon` accordé à `eldarAutarch` (pose
vérifiée — `traitsAfter` le porte), 25 pas, **0 activation du carrier**. Le régime observable de
cette face est le tour automatique d'un summon, que le harnais ne couvre pas. Le gate est exercé
**offline, dans les deux sens**.

**Le gate `HasUnitId` de 1531** ne se contrôle pas en live : la greffe **fait spawner** la mine
(c'est l'objet de l'ability), des deux côtés — **4 mines** pour une posée à la main — donc aucun
montage n'offre un plateau « sans mine ». Et le steppable témoin (`genesSmnDecoy`), placé à la
position `neutral`, n'a été hooké à **aucun** des 4 pas. Exercé offline. ⚠ Corollaire : la tuile qui
porte la mesure de `haywire` est une mine **spawnée** `(2,7)`, pas celle posée en `(5,5)`.

## 6. Les mesures

`purge` / `MC1_67` / 777 — **7 tuiles hookées, 0 désaccord**. `X_nat = 20` sur la tuile adjacente au
porteur ami, `0` ailleurs.

`purge-gate` / `MC1_67` / 777 — **8 tuiles, 0 désaccord**, `X_nat = 0` partout (mover
`eldarAutarch`, non Votann).

`haywire` / `MC1_67` / 777 — **10 tuiles, 0 désaccord**, `X_nat = -130` sur la tuile minée.

### Contre-épreuve — `a_mordu` rendu SÉPARÉMENT du verdict

| modèle | `purge` | `purge-gate` | `haywire` |
|---|--:|--:|--:|
| `PORT` | 0 / 7 | 0 / 8 | 0 / 10 |
| `CAMP-DEUX` | **4** | 0 (inerte) | — |
| `CAMP-ENNEMI` | **5** | 0 (inerte) | — |
| `SANS-GATE` | 0 (non séparé) | **2** | 0 (non séparé) |
| `COUNT (x n)` | 0 (non séparé) | 0 (inerte) | — |
| `SLOT4-OFF` = l'état du port AVANT le fix | — | — | **1** |
| `UNE-SEULE-CLE` | — | — | **1** |
| `CLES-INVERSEES` | — | — | 0 (non séparé) |
| `ABSENT` = l'état d'avant la tranche | **1** | 0 | **1** |

`SLOT4-OFF` **chiffre le bug corrigé** : 1 tuile × (−30). `CLES-INVERSEES` n'est pas séparé parce
que le montage a `na == ne == 1`, donc `we + wa == wa + we` — dit, pas tu ; il est exercé offline.

## 7. Ce qui est livré

* `engine/playbook/non_owner.py` — trois classes (`PurgeResponseNonOwnerPlaybook`,
  `MawClawsOfThyraxNonOwnerPlaybook`, `HaywireMineNonOwnerPlaybook`), leurs entrées de registre
  (15 → **18**), et l'attribut `SLOT_4` **par classe** ;
* `engine/utilities/tile.py` — le pré-gate du dispatcher lit `pb.SLOT_4` ; `_steppable_occupant`
  délègue au foyer déplacé ;
* `engine/entities/tile_extensions.py` — `get_steppable_unit` (mirror de
  `IdunBattle.Entities.TileExtensions$$GetSteppableUnit`), **déplacé** depuis `tile.py` parce qu'un
  second consommateur est apparu qui ne peut pas importer `tile`, et **étendu** du champ `vis` ;
* `probe_477r35_import_isole.py` — le **cliquet** né de la relecture de PR (§9) ;
* `engine/entities/unit_team_selection_type.py` — mirror **neuf**, inscrit à `probe_313` dans le
  même commit ;
* `probe_477r35_non_owner_gates_montables.py` — recensement re-dérivé, verdict du `<slot 4>`
  classe par classe, 3 montages ;
* `test_477r35_non_owner_gates_montables_live.py` — 6 étages offline + 4 × 3 cas live.

## 8. Ce qui n'est PAS couvert

* **Les 5 faces MOVE restantes** (résidu **#477-r37**, LIVRÉ) : `1064 FirstAmongTraitors` (gate
  `HasTrait(Chaos)`, **0 unité sur 1083** — terme inerte) ; `1451`, `1496`, `1508` (gates sur la
  **rareté** du mover, aucun canal `rarity` dans le `ctx`) ; `1478 SabreOfSacrifice` (gate =
  sélecteur DSL `SabreOfSacrificeAbility$$IsAffectedSummon`, invoqué par vtable sur une struct de
  0x128 octets).
  ⚠⚠ **Le « 0 unité sur 1083 » de `1064` est FAUX, et #477-r37 l'a mesuré.** Ce compte portait sur
  `gameconfig.unit(vis).traits` — la source dont `engine/entities/traits/unit_trait.py` écrit
  qu'elle **ne contient jamais** le pseudo-trait de grande-alliance. Le substrat que
  `BaseUnitComponent$$HasTrait` interroge en donne **127 sur 683** : la face est vivante, elle est
  portée depuis #477-r37, et son porteur `blackAbaddon` est un héros **du pool**. Il en reste
  **4**. Détail : `docs/rl/case-477r37-slot4-des-28-et-la-face-dite-inerte.md`.
* **La branche SPAWN de 1469** — le `ctx` de spawn ne produit aucune clé de sujet ni de parent.
  Résidu pré-existant de la feuille, inchangé.
* **Le régime automatique** (`PlayAutomaticUnitsOperation`) — c'est le seul régime où la face 1469
  pèse, et le harnais `aiStepDryRun` ne le marche pas. **C'est le vrai résidu ouvert par ce cas.**
* **`CLES-INVERSEES` de 1531** : non séparé en live faute d'un montage à `na != ne` (il faudrait un
  troisième porteur). Exercé offline seulement.
* **Le `<slot 4>` des 22 autres classes** du registre n'a PAS été relu : seules 6 le sont. Rien ne
  dit qu'une autre ne vaut pas `true` — et c'est exactement l'erreur que ce cas vient de corriger,
  transposée d'un cran.
  ⚠ **RELU par #477-r37, sur les 28, et le CRITÈRE de ce cas-ci était FAUX DES DEUX CÔTÉS.** Le
  `<slot 4>` est `get_ShouldIncludingEnemiesWhenCalculate` (nom LU dans le `global-metadata.dat`) ;
  `NoHidingFromTheWatchersNonOwnerPlaybook` le déclare **APRÈS** son `.ctor` et vaut `true` (faux
  négatif), tandis qu'`ECogSupport` / `KustomForceFieldReworked` ne déclarent **RIEN** là où le
  §2 lit un override `return 0` — cette entrée appartient au **type précédent** (faux positif). Le
  tableau du §2 rendait donc les bonnes valeurs pour la mauvaise raison. `step0b` **délègue**
  désormais au lecteur complet.

## 9. Le déplacement du foyer a cassé un artefact versionné — trouvé à la relecture de PR

La première version posait `get_steppable_unit` dans `engine/battle_query.py`. Ce module a besoin
d'`UnitTrait`, donc d'`engine.entities`, dont l'`__init__.py` cascade jusqu'à
`selectors/units.py` → `from ...battle_query import is_target_tile_obscured`. Résultat :

```
python -c "import engine.battle_query"      master OK  /  branche ImportError
probe_433_r1_identity_shortcircuit.py       master rc=0 /  branche rc=1
```

**165 tests verts ne l'ont pas vu.** Un cycle Python est *sensible à l'ordre* : il se dissout dès
qu'un appelant importe `engine.entities` d'abord, ce que font toutes nos passes. Le seul
consommateur qui l'a payé est un **probe versionné**, qui n'émet aucun report pytest.

**Deux emplacements ont été essayés et mesurés avant le bon** — le second casse aussi, par une arête
*retour* :

| emplacement | `import` isolé | cause |
|---|---|---|
| `engine/battle_query.py` | **casse** | `battle_query` est ré-entré par la cascade d'`entities` |
| `engine/tile_extensions.py` (racine) | **casse** | la cascade atteint `utilities/tile.py`, qui l'importe |
| **`engine/entities/tile_extensions.py`** | **OK** | sous-module d'`entities` : chargé intégralement quand la cascade le demande |

C'est le patron que le `CLAUDE.md` documente déjà pour `AbilityConstantType` (« leur emplacement est
fonctionnel, pas cosmétique »). Le cycle est **supprimé, pas retardé** : les trois consommateurs
importent au **niveau module**, aucun différé dans cette chaîne. Le cas était dans la classe
**gratuite** — `get_steppable_unit` ne dépend que d'`UnitTrait` — donc un placement l'évitait ;
un différé aurait ajouté un contournement là où une réparation existait.

**Le cliquet qui manquait** : `probe_477r35_import_isole.py` importe **chaque** module `engine.*`
seul, en process frais (430 modules, ~13 s, offline pur). Critère `en_echec == 0`, **inconditionnel** ;
`--temoin` n'entre pas dans le verdict, il **attribue** (régression / pré-existant / neuf-cassé). Il
est joué par la garde pytest de la tranche.

⚠ **Un vert de ce cliquet ne dit PAS « le graphe est propre ».** Le 430/430 est tenu par **262**
imports différés *porteurs* (sur 314, dont **212 sans raison écrite**) — c'est un acquis adossé à une
dette, et le lire comme un certificat serait exactement le faux positif que ce dépôt chasse.

## Résidus

- ~~**#477-r37**~~ — **LIVRÉ**. Les trois volets sont tranchés :
  `<slot 4>` relu sur les **28** (2 surchargent, les deux à `true` ; le port était juste, le
  critère de ce cas-ci ne l'était pas) ; `1064` **portée et confrontée live** (le « terme inerte »
  comptait dans le mauvais substrat) ; le régime automatique est **ouvrable sans hook**
  (`PlayAutomaticUnitsOperation` passe par `ComputerAction`). Résidus ouverts là-bas : **#477-r43**
  (canal `rarity`), **#477-r44** (régime automatique), **#477-r45** (`1478` en arbre DSL).
  cf. `docs/rl/case-477r37-slot4-des-28-et-la-face-dite-inerte.md`.
- **#485 — les 314 imports différés d'`engine/**`, ventilés** (§9). **262 porteurs** (hisser
  fermerait un cycle) dont **212 sans raison écrite** : un lecteur ne peut pas distinguer
  « structurel, n'y touche pas » d'une scorie — et c'est vraisemblablement par imitation que les
  **52 gratuits** (hissables, aucun cycle ; **3** seulement portent une raison) sont apparus. Les 52
  sont un chantier borné, offline pur, qui ratchette à 0.
