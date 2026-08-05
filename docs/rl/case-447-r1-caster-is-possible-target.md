# #447-r1 — `CasterIsPossibleTarget` (bit 15) : trois états, et il n'était dans aucun des deux qu'on croyait

**Livré le 2026-08-05.** Build de référence : `rnca9r7q6c`. Résidu de `case-447`.

**Critère binaire** : le port lit-il le bit 15 **là où le natif le lit**, et son effet est-il
confronté — ou n'est-il « couvert » que parce qu'un inventaire l'énumère ?

**Verdict** : la prémisse du résidu est **fausse sur son lecteur**, et son diagnostic était **entre
deux états**. `TargetingQuery$$GetValidTargets` ne teste **jamais** le bit 15 ; le lecteur qui mord
est `GetPossibleTargetsForOptions`, un cran plus haut. Et le bit n'était ni « énuméré seulement »
(état 3) ni confronté (état 1) : **13 sites le DÉCLARENT, 3 le LISENT**, et le seul lecteur qui
décide d'un cast n'existait pas encore. Il existe, et il est confronté.

---

## 1. Les quatre lecteurs natifs, et lequel compte

| # | symbole | ce qu'il fait du bit | porté ? |
|---|---|---|---|
| 1 | `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` | `if ((rules >> 0xf & 1)) <ensemble>.<IOrderedSet slot 0>(bVar12 ? casterTiles : caster)` — **AJOUTE** le caster aux cibles POSSIBLES, en amont des trois `RemoveAll` | **OUI (cette tranche)** |
| 2 | `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` | branche `(int)range == 0` (`bit15 ? OrderedSet(casterTiles) : VIDE`) et `includeCenter` du slot `0x67` | oui, `ability_range.py` (#433-r4-…-r1-r1-r1) |
| 3 | `IdunBattle.Core.Services.TargetingOptions$$get_CanTargetCaster` | `rules >> 0xf & 1`, **déclaratif** — 2 appelants, tous deux UI (`IdunBattle.View.FSM.Actions.UnitSelection$$QueueShowAsSelected`, `idun.Ui.IdunAbilitySelectionHud$$SelectIfPossible`) | oui, `TargetingOptions.can_target_caster` |
| 4 | `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` | branche `else if (options+0x00 == 0 && !(rules & 0x800)) { if (rules & 0x8000) … }` | **NON — code MORT** |

`bVar12 = onlyTiles || (rules >> 6 & 1)` (`TargetIsTile`) : domaine TUILE → ce sont les **tuiles** du
caster qui entrent ; domaine UNITÉ → l'**entité** caster.

**Le (4) est mort, et c'est une lecture de ses appelants, pas une opinion.**
`GetCasterNotAddedReason` a exactement **deux appelants de code** — les deux surcharges 5 arguments
de `TargetingQuery$$GetInvalidTargetReason` — et toutes deux n'y branchent que sous
`if (*(char *)options != 0)`, c'est-à-dire self-cast **posé**, ce que la branche contredit
(`options+0x00 == 0`). Le porter **inventerait** un refus que le natif ne rend jamais.

### ⚠ Ce que le résidu disait, et qui est faux

> « Elle vit par `TargetingQuery$$GetValidTargets`, qui RE-APPLIQUE la cascade CIBLE complète au
> caster. »

`GetValidTargets` a été relu **en entier** : il teste le bit 7 (`AddCaster`), `isSelfCasting || bit 11`,
le bit 22 et le bit 3. **Le bit 15 n'y apparaît pas.** Ce qu'il fait, c'est boucler sur ce que
`GetPossibleTargetsForOptions` lui a rendu — et c'est *là* que le caster est entré.

## 2. Trois états, et la mesure qui les sépare

Le balayage est **AST** et le rôle de chaque occurrence se décide par sa **chaîne de parents**, pas
par sa présence : un `TARGETING_OPTIONS = TargetingOptions(rules=… | TR.CasterIsPossibleTarget, …)`
**DÉCLARE** le bit (état 3) — il ne le lit pas.

```
python scripts/python/probe_447_r1_caster_is_possible_target.py --step lecteurs
```

Mesuré sur `engine/**` : **13 sites DÉCLARENT le masque, 3 le LISENT**. Verdict par lecteur, avec la
clôture d'appel à un niveau (une garde qui exerce un *consommateur* exerce le lecteur qu'il appelle —
sans elle `caster_is_possible_target`, atteint seulement par `caster_is_valid_target`, serait compté
« non testé ») :

| fonction lectrice | avant | après |
|---|---|---|
| `_zone_contains_distance` (`ability_range`) | (2) garde OFFLINE seule | inchangé — cf. `#447-r1-r1` |
| `can_target_caster` | (1) confronté (`test_instruments_of_vengeance_decision_live`) | inchangé |
| `caster_is_possible_target` | **absent** | **(1) PORTÉ ET CONFRONTÉ** |

## 3. Ce qui est porté

* `engine/runner/abilities/targeting.py::caster_is_possible_target` — les **trois** termes de
  l'appartenance du caster à l'ensemble des cibles possibles :
  `UseWholeBoard | CasterIsPossibleTarget | TargetIsCasterOrEnemy`. Les branches `range == 0` et
  `GetSurroundingTiles` lisent le **même** bit 15 que le premier `AddRange` — elles n'ajoutent aucun
  terme. La zone est **déléguée** au foyer `ability_range`, aucun second corps.
* `engine/runner/abilities/targeting.py::caster_is_valid_target` — `GetValidTargets` restreint à
  « le caster figure-t-il dans l'ensemble ? », **étage d'ajout compris** (bit 7 ; `isSelfCasting ||
  bit 11` sous `Count > 0` ; bit 22 ; bit 3).
* `engine/runner/abilities/targeting.py::get_invalid_target_reason(apply_self_cast_switch=)` — le
  port n'avait **qu'un corps pour deux surcharges natives**. La 5 arguments (le CAST) commence par
  l'aiguillage self-cast ; la 7 arguments (celle qu'appelle la boucle de `GetValidTargets`) est le
  **filtre statique pur**. Le drapeau nomme laquelle ; le défaut est l'ancien comportement, donc
  aucun appelant historique ne bouge.
* `engine/services/ability_range.py::zone_contains_for_options` — cf. §5, c'est un **défaut mesuré**
  qui a d'abord rendu une contre-épreuve muette.

**Le bit 15 n'a rien à faire sur le chemin du CAST, et c'est un résultat.** Si `isSelfCasting != 0`
et cible == caster, le natif branche sur `GetCasterNotAddedReason` (où la branche du bit est morte) ;
si `isSelfCasting == 0`, c'est le filtre statique, qui ne teste pas le bit. Le port est **fidèle en
ne le lisant pas** dans `get_invalid_target_reason`.

## 4. La confrontation — et sortir du régime dégénéré

**La paire**, et elle n'est pas choisie à l'œil (l'étape `paire` re-dérive la propriété et refuse de
continuer si elle cesse d'être vraie) :

| ability | porteur (HERO, au pool) | `rules` | `TargetingRange` |
|---|---|---|---|
| `1061 UnbreakableDuty` | `templAncient` | `0x8400` = `TargetIsFriendly \| CasterIsPossibleTarget` | `RANGE_FROM_CONFIG`, reach **2** |
| `1049 CrusadeOfWrath` | `templHelbrecht` | `0x400` = `TargetIsFriendly` | `RANGE_FROM_CONFIG`, reach **2** |

`xor` des masques = **`CasterIsPossibleTarget` et rien d'autre** ; même `isSelfCasting`, même portée.

⚠ **Le régime dégénéré est MESURÉ, pas supposé.** L'étage d'ajout de `GetValidTargets` fait
`if (targets.Count > 0 && !Contains(caster)) Add(caster)` pour toute ability **self-castée** — donc
dès qu'une autre cible existe, le caster entre **quel que soit le bit 15**. Passe A (spawn nu, les
deux casters adjacents, donc alliés à portée l'un de l'autre) : `natif = true` **des deux côtés**.
Un accord lu là ne prouverait rien.

Passe B — `--place` à `(0,0)` et `(5,0)`, distance **5 > reach 2**, plus aucun allié à portée :

| ability | `autres_cibles` | natif `abilityTargets.fromHere` | port |
|---|---|---|---|
| `1061` (bit 15) | **0** | **`[81]` = LE CASTER** | `True` |
| `1049` (sans) | **0** | **`[]`** | `False` |

Le canal est `abilityTargets.fromHere` = `IdunBattle.Core.Services.AttackQuery$$GetValidTargets(unit,
UnitPosition{GetTiles(unit)}, abilityType)`, dont le **seul** gate amont est
`AttackQuery$$IsAlreadyUsedThisTurn` — pas de `get_CanCurrentlyBeUsed`, donc le cooldown ne masque
pas la réponse (c'est exactement le piège que `#447-r2` nomme).

**Contre-épreuve** : bit 15 désarmé côté port → **désaccord** sur `1061` (port `False`, natif `True`),
et le contrôle `1049` ne bouge pas.

## 5. Trouvé en chemin : la contre-épreuve a d'abord rendu un FAUX VERT

Et le rouge qu'elle rendait **accusait le montage** alors que le coupable était le **port**.
`caster_is_possible_target` déléguait à `tiles_in_range_zone_contains(ability_id, …)`, qui **recharge
le masque du registre depuis l'id** : la mutation de l'appelant était silencieusement ignorée, et
la fonction répondait avec le bit *armé*.

Fermé par `ability_range.zone_contains_for_options(options, ability_id, visual_id, distance)`, qui
prend le masque **effectif** — l'`ability_id` n'y sert plus qu'à résoudre le `TargetingRange`
(`UseRangeFromConfig` lit la config de l'ability). **Un seul corps** :
`tiles_in_range_zone_contains` en devient le cas particulier « masque du registre ».

La portée du défaut dépasse cette tranche : **tout** appelant qui aurait muté un masque et interrogé
la zone par l'id était dans le même cas.

## 6. Le gisement

```
python scripts/python/probe_447_r1_caster_is_possible_target.py --step gisement
```

**18** masques lus portent le bit 15 (sur **148** masques RE-lus) — le résidu en annonçait 13, le
compte a bougé et se re-dérive. Ventilation des porteurs : **10** abilities ont un porteur HERO au
pool (`ultraApothecary`, `astraCreed`, `deathRotbone`, `adeptHospitaller`, `orksRuntherd`,
`templAncient`, `tauCrisis`, `spaceBlackmane`, `admecManipulus`, `custoTrajann`), les autres sont
npc-only ou summon. **Deux** masques sont NON self-castés (`28 Repair`, `1119`), donc le bit 15 y est
le **seul** chemin d'entrée du caster, sans même avoir à isoler — mais leurs porteurs passent par le
trait `Mechanic` (attribution hors gameconfig), non exploré ici.

## 7. Validation

* **LIVE** — `tests/engine/runner/test_447_r1_caster_is_possible_target_live.py` : **7 passed**.
  La garde assertionne le régime **dégénéré** avant le discriminant : si le spawn venait à séparer
  les deux casters, la passe A rougit et signale que la passe B a cessé d'être une démonstration
  *de plus*.
* **NON-RÉGRESSION** — `test_targeting_rule_inventory` + `test_ability_registry_ratchet` +
  `test_433_…_source_tile_zone_offline` : **43 passed** ; `test_add_caster_dynamic_rule_live`
  (la tranche parente) : **12 passed**.
* **NON COUVERT**, nommé : cf. `#447-r1-r1`.

## 8. Résidus nommés

* **`#447-r1-r1` — la branche INCLUSION de `_zone_contains_distance` reste en état (2).**
  Cette tranche confronte le bit 15 sur la face **CIBLAGE** (`abilityTargets`) ; la face **DÉCISION**
  (`ability_range` → `is_tile_in_range_of_any_ability`, oracle `aiMovableTiles {threat:true}`) n'a
  toujours qu'une garde offline pour la branche « bit armé » — c'est le résidu
  `#433-r4-r2-r1-r2-r2-r1-r1-r1-r1`, que ce cas ne ferme pas : le blocage qu'il nomme
  (`orksRuntherd`/`1045` annulé par un étage amont, `AttackQuery$$GetInvalidCasterReason` non porté)
  est intact. Les **9** autres porteurs du bit 15 au pool recensés au §6 sont autant de montages non
  tentés pour le rouvrir.
* **`caster_is_valid_target` n'énumère pas** : son `other_valid_targets` est une **entrée**, pas une
  mesure interne — `None` le rend permissif sur l'étage `Count > 0`. Porter
  `GetPossibleTargetsForOptions` en entier reste ce qui débloquerait `AddCasterIfAtLeastOneTarget`
  (bit 11) et `AddCasterIfAtLeastOneFreeTileInRange` (bit 22, `HasFreeTilesInRange` non porté),
  comme `case-447` §7 l'annonçait.

## 9. Re-dériver

```
python scripts/python/probe_447_r1_caster_is_possible_target.py --step lecteurs
python scripts/python/probe_447_r1_caster_is_possible_target.py --step gisement
python scripts/python/probe_447_r1_caster_is_possible_target.py --step live
python -m pytest tests/engine/runner/test_447_r1_caster_is_possible_target_live.py -q
```
