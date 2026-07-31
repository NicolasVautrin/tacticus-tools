# case-361 — `RammingSpeed` batchs 3/4 : c'est `GetTileToMoveTo` qui rend VIDE, pas la gate

Suite de `#353-r1` volet (b) et de `#372`. Trois causes étaient déjà tombées ; ce cas en fait tomber
**six de plus** et referme la question : le vide des deux batchs vient de l'**`origin`** des
sélecteurs — l'arbre `RammingSpeedAbility$$GetTileToMoveTo()`, évalué dans le contexte du playbook.
Le résidu restant est le maillon INTERNE de cet arbre (§9), avec le point d'ancrage à hooker nommé.

Rappel du natif (`IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions`) :

```
list = <batch 1 : la CIBLE>            // 1 event
self = <batch 2 : le CASTER (recul)>   // 1 event
list.AddRange(self)
if (!self.Any(p => p.Prediction.WillBeKill)) return list;   // <>c$$<MakeDamagePredictions>b__2_0
tile = RammingSpeedAbility$$GetTileToMoveTo(ability)
list.AddRange(GenerateAttackPredictions(..., Friends(<Caster>, AdjacentUnits(tile, 1, 3), 3), ...))
list.AddRange(GenerateAttackPredictions(..., Enemies(<Caster>, AdjacentUnits(tile, 1, 3), 3), ...))
```

---

## 1. La mesure, sur une géométrie qui exerce TOUT

`probe_361_ramming_speed_explosion_batches.py`, board `MC1_67`, greffe `orksKillaKan ← 1059`
(`case-92` §5bis), drive pas-à-pas + `endturn` (le caster n'a pas bougé) :

| élément | mesuré |
|---|---|
| géométrie | cible (4,7), caster (1,4) à d=3, ami (4,6), 2ᵉ ennemi (5,8) |
| tuile d'arrivée, port | **(5,7)** |
| tuile d'arrivée, NATIF (cast réel) | **(5,7)** — MATCH |
| voisinage de (5,7) | **1 ami** (`astraBullgryn`) + **2 ennemis** (`necroWarden`, `ultraTitus`) |
| gate | `willBeKill = true`, `cannotBeGuaranteedKilled = 0`, `blockScenarioCount = 0` (hp 60 ≤ 104) |
| events natifs | **2** — attendu si les batchs sortaient : **5** |

`ComparablePlaybook<T>$$GenerateAttackPredictions` émet **un event par entité** rendue par le
sélecteur (boucle sur l'énumérateur) et **lève** si le sélecteur est nul : 2 events sans erreur
n'est compatible qu'avec « les deux sélecteurs rendent un ensemble VIDE », ou « la gate est fermée ».

## 2. « Le pool de tuiles est vide » — ÉCARTÉ, par la RE puis par le cast

`RammingSpeedAbility$$GetDynamicInvalidTargetReason` évalue le **même arbre**
(`TargetsSelector$$SelectTile(GetTileToMoveTo())`) dans un contexte qu'il construit lui-même :
`memset(ctx, 0, 0x128)` puis **seulement** `ctx+0x08 = caster`, `ctx+0x10 = target`,
`ctx+0x40 = casterTiles[0]` — et rend `0x8000000` (cast REFUSÉ) dès que l'arbre ne rend rien.

`GenerateAttackPredictions` renseigne **ces mêmes trois champs** (`+0x08 = caster`, `+0x10 = target`,
`+0x40 = UnitPosition$$get_MainTile(casterPosition)`) **et davantage** (`+0x18`, `+0x38`, `+0x48`).
Son contexte est donc un **sur-ensemble** de celui du gate. Or le cast réel PASSE et pose le caster
en (5,7). Le pool ne peut pas être vide là où le gate le trouve non vide.

## 3. « `get_WillBeKill` ne gouverne pas » — ÉCARTÉ, par un playbook qui n'a QUE cette gate

`IdunBattle.AI.Playbook.Loki.StormOfFlensingBladesPlaybook$$MakeDamagePredictions` est le test PUR :

```
ev = ProbableDamageEvent(target, <IBattleQuery slot 0x22 (caster, target, casterPosition)>, ...)
if (!get_WillBeKill(&ev.Prediction))  return new[]{ ev, ev };   // DEUX fois le MEME event
else                                  return new ProbableDamageEvent[0];
```

Le compte d'events y dépend **uniquement** du flag — aucun sélecteur, aucun contexte, aucun `Any`.
`&ev.Prediction` = `&ev + 0x08`, exactement le `PDE_PREDICTION_OFF` que décode le capteur #372.

`probe_361_will_be_kill_gate_direct.py` volet A, greffe `orksKillaKan ← 1010` (porteurs NPC-only ⇒
greffe légitime : ce playbook ne lit ni stats, ni traits, ni config) :

| bras | `willKillDmg` / `hpBefore` | `willBeKill` | events |
|---|---|---|---|
| `alive` (`--hp-target 999999`) | 7400 / 999999 | false | **2** |
| `kill` (`--hp-target 1`) | 7400 / 1 | true | **0** |

⇒ `get_WillBeKill` **gouverne**, et le capteur #372 dit vrai.

⚠ **Le 1ᵉʳ jet de ce bras ne prouvait RIEN** : sans drive, la cible est hors portée, la prédiction
rend un dégât NUL (`willKillDmg = 0`), `1 <= 0` est faux, et on lisait 2 events dans les deux bras.
Le probe porte désormais la garde qui refuse ce montage (borne < PV ⇒ `BRAS NON DISCRIMINANT`).

## 4. Le capteur de gate, et ce qu'il a rendu

Le prédicat de `System.Linq.Enumerable$$Any<T>(selfPreds,
RammingSpeedPlaybook.<>c$$<MakeDamagePredictions>b__2_0)` était le dernier maillon non instrumenté :
le capteur #372 lit `get_WillBeKill` sur l'event **RENDU**, personne n'avait lu ce que le natif
**APPELLE**.

`frida/hooks/features/ai-step/playbook-gate-probe.ts` + le flag `gateProbe` d'`aiPlaybookPredict`
intercepte `get_WillBeKill` — foyer UNIQUE du prédicat, quel que soit le chemin — **le temps d'une
invocation**, filtré sur le thread appelant, détaché en `finally` (ce symbole est aussi appelé par
`idun.Ui.IdunUnitHud$$ShowPrediction` à chaque frame : jamais de hook permanent). Trois issues,
toutes discriminantes, et `probe_361` les traduit (`_gate_verdict`) :

| mesure | ce qu'elle établit |
|---|---|
| **0 appel** | `Any` n'invoque pas le prédicat — la liste qu'il itère est vide CÔTÉ NATIF |
| **rend `true`** | la gate OUVRE ⇒ la cause est en AVAL, dans l'évaluation des sélecteurs 3/4 |
| **rend `false`** | le natif lit un AUTRE objet que celui décodé (paramètre du lambda en régime fully-shared generic) |

**Mesuré** (session 2, capteur déployé) : `rend true`, **1 appel** — sur les deux géométries de §1
et de §8.3. La gate OUVRE ; la cause est en aval.

## 5. Le candidat écarté — et pourquoi il fallait le grepper d'abord

`FragstormGrenadeLauncherPlaybook$$MakeDamagePredictions` (1048) porte le même motif — gate
`get_WillBeKill` DIRECTE, puis un batch supplémentaire — et semblait donc être LE discriminant. Il ne
l'est pas : son batch est **inobservable**, `TargetsSelector$$SelectUniqueUnits` y étant évalué sur un
contexte `memset(0, 0x128)` **jamais renseigné**, donc `GetOtherTargets` =
`Damageable(SurroundingEnemies(Owner@0x30, range, 1, 3) − Target@0x60)` est vide que la gate ouvre ou
non. Mesuré (volet B, `templAggressor`, porteur ACTIF du pool, un 2ᵉ ennemi à distance 1) : **1 event
dans les deux bras**, `willBeKill` false puis true. Le probe l'enregistre et **refuse** de le compter
comme discriminant.

⚠ **C'était DÉJÀ ÉTABLI** — `case-352` §3 / backlog `#352-r1` : « les volets secondaires de 1098 et
1048 sont MORTS, ne pas les réparer » (1048 : `memset(0)` complet ; gate `WillBeKill` pourtant
franchi). Le re-découvrir a coûté un bras de probe. **Grepper le backlog avant de choisir un
discriminant**, c'est ce qui aurait envoyé directement sur `StormOfFlensingBlades` (§3), dont le
compte d'events ne dépend d'AUCUN sélecteur.

## 6. La « seconde porte » `GetDamage` — ce n'est PAS une porte (#365)

Entre la gate et les batchs, le natif intercale :

```
lVar20 = ExplodesAbility$$GetDamage(this+0x18);
FUN_1802abdd0(local_2a8, 0, 0x128);     // memset du contexte
pvStack_290 = caster;                    // ctx+0x18 = Owner, ET RIEN D'AUTRE
if (lVar20 != 0) { ...batchs 3/4... return list; }
```

Deux lectures tuent l'hypothèse « `GetDamage` rend 0/null, donc les batchs sautent » :

1. **`GetDamage` rend un ARBRE DSL, pas un montant.** Elle ne fait que composer des nœuds :
   `PercentageOf(StatAmount(Owner@0x30, …), Sum(ConfigConst(0x3fd, Owner), ConditionalAmount(HasEffect(Owner, 0x44a), ConfigConst(0x423, Owner), Get(0))))`.
   Toutes ses sorties d'échec vont dans le thrower — elle rend un nœud non nul **ou lève**.
2. **Le chemin `lVar20 == 0` NE REND RIEN.** Il ne fait pas `return list` : il tombe dans
   `FUN_1801f51f0` (le null-check IL2CPP qui précède l'appel d'interface d'évaluation
   `FUN_180025fb0(1, …)`). Un `GetDamage` nul produirait donc une **exception**, jamais 2 events.

⇒ Dans `MakeDamagePredictions`, **il n'existe que DEUX `return`** : celui de `Any == false`
(2 events) et celui qui suit les deux `AddRange`. Donc `n_events == 2` **sans erreur native**
n'admet que deux causes, et le capteur en écarte une :

| `Any` | conséquence |
|---|---|
| `false` | retour anticipé — écarté, le capteur mesure `get_WillBeKill → TRUE` |
| `true` | **les deux `GenerateAttackPredictions` rendent VIDE** |

Le **contexte creux** (`memset(0,0x128)` + le seul `ctx+0x18`) n'est pas non plus coupable, et le
rapprochement avec `FragstormGrenadeLauncher` (`case-352` §3) ne tient pas ici : `ctx+0x18` est
exactement `Owner`, le SEUL champ que l'arbre de `GetDamage` lit. Ce contexte est **suffisant pour
ce qu'il évalue**, et il ne sert **qu'à** l'évaluation du montant — les sélecteurs 3/4, eux, sont
évalués dans le contexte PLEIN que `GenerateAttackPredictions` construit lui-même.

⚠ Et `GenerateAttackPredictions` **lève** si le sélecteur rend `null` (`if (lVar17 != 0)` sinon
thrower), mais **rend la liste vide** si l'énumérateur ne produit rien. « Vide » est donc la seule
issue silencieuse.

## 7. La chaîne des sélecteurs 3/4, lue nœud par nœud (#365)

Contexte construit par `ComparablePlaybook<T>$$GenerateAttackPredictions` (`memset(+0x50, 0, 0xd8)`,
tout le reste écrit explicitement) :

| offset | valeur écrite | nœud qui le lit |
|---|---|---|
| `+0x08` | `caster` | `CasterSelector$$Select` |
| `+0x10` | `target` | `TargetSelector$$Select` |
| `+0x18` | `caster` | `OwnerSelector$$Select` |
| `+0x38` | `EntityExtensions$$GetTiles(target)` | `TargetTilesSelector$$Select` |
| `+0x40` | `UnitPosition$$get_MainTile(casterPosition)` | `CasterTileSelector` (repli 2) |
| `+0x48` | `casterPosition` (les tuiles du caster) | `CasterTileSelector` (voie 1) |

Composition mesurée au décompilé :

* `DSLSelectors$$AdjacentUnits(origin, unique, selectionType)` =
  `Units(AdjacentTiles(origin), unique, selectionType) op_Subtraction origin` — elle n'alloue AUCUN
  sélecteur dédié.
* `DSLSelectors$$AdjacentTiles(origin)` alloue un sélecteur `(state, battleQuery, origin)` dont le
  `Select` est `AdjacentTilesSelector$$Select` : il énumère `origin`, prend les voisines de chacune,
  et **exclut déjà les tuiles d'origine**.
* `DSLSelectors$$Units(entities, unique, selectionType)` = `UnitsOnTilesSelector(state, entities,
  unique, selectionType)`. Son `Select` appelle sur `entities` la méthode d'index **3**
  (`unique == false`) ou **4** (`unique == true`), avec `(ctx, selectionType)`.
* `DSLSelectors$$Friends/Enemies(of, entities, selectionType)` = `UnitsFromFactionSelector`. Son
  `Select` appelle l'index **4** sur `entities` avec `(ctx, selectionType)`, puis garde les unités
  dont `UnitExtensions$$HasFaction` égale le booléen `friends`.
* `TargetsSelector$$op_Subtraction(left, right)` = `CombinedSelector{Left, Right, Op = 2}` ;
  `CombinedSelector$$Select` évalue les DEUX côtés puis `SelectExclusion` (left privé des éléments
  que `right.Contains` accepte).
* `GenerateAttackPredictions` appelle sur le sélecteur racine l'index **4** avec `(ctx, 3)`.
  L'index 4 est `TargetsSelector$$SelectUniqueUnits` : `results = this.Select(ctx)`, puis — sauf si
  deux getters virtuels sont vrais — chaque entité passe par `TargetsSelector$$SelectUnit(entity,
  selectionType)`, qui **écarte tout ce qui n'est pas une unité** et applique
  `UnitExtensions$$MatchesUnitSelectionType`.
* `UnitExtensions$$MatchesUnitSelectionType(unit, selectionType, state)` : `0` (ou > 3) → vrai ;
  `1` → `IsAlive` ; `2` → `!HasFlag(0x11)` ; `3` → `IsAlive && !HasFlag(0x11)`. Le `3` des batchs
  3/4 est donc « vivante ET sans le flag `0x11` ». `DSLSelectors$$Units(entities, unique, onlyAlive)`
  (l'autre surcharge) écrit `selectionType = onlyAlive + 2`, ce qui confirme la lecture.

## 8. Le maillon, ISOLÉ : c'est l'`origin`, pas la composition (#365)

Deux mesures l'établissent, chacune écartant une cause que l'autre laissait ouverte.

### 8.1 `Friends` et `Enemies` PARTITIONNENT — les deux vides ⟹ leur entrée est vide

`DSLSelectors$$Friends` et `DSLSelectors$$Enemies` allouent le **même** `UnitsFromFactionSelector`
à un bit près (`friends = 1` / `0`). Son `Select` évalue `entities` une fois
(`SelectUniqueUnits(ctx, selectionType)`) puis garde les unités dont
`UnitExtensions$$HasFaction` égale ce bit — une **partition**, pas deux filtres indépendants.

⇒ « les deux batchs vides » équivaut à « `AdjacentUnits(GetTileToMoveTo(), 1, 3)` est vide ».

### 8.2 La composition `AdjacentUnits` est VIVANTE — mesuré 3/3

Trois playbooks seulement appellent `ComparablePlaybook<T>$$GenerateAttackPredictions` (xrefs) :
`ExplosivePresentsPlaybook`, `MortisRoundPlaybook`, `RammingSpeedPlaybook` (×2). Les deux premiers
encadrent la question, et se greffent (`case-92` §5bis — leurs playbooks ne lisent ni stats ni
traits du caster). `probe_361_adjacent_units_selector.py`, board `MC1_67`, greffon `orksKillaKan` :

| bras | ability / sélecteur natif | attendu (dérivé) | natif |
|---|---|---|---|
| `control` | `1004 MortisRound` — `Entity(target)` | 1 : la cible | **1, cible exacte** |
| `adjacent` | `1170 ExplosivePresents` — `(Target@0x60 + AdjacentUnits(Target@0x60,1,3)) − Caster@0x48`, caster LOIN | 3 : cible + 2 voisins | **3, cibles exactes** |
| `adjacent`, caster POSÉ adjacent à la cible | idem | 3 : le caster est RETIRÉ | **3, cibles exactes** |

Garde adversariale (`--mutate no-subtraction`, l'attendu compte le caster adjacent) — ROUGE :
`COMPTE DIFFERENT : 3 events pour 4 attendus (natif=[77, 79, 83] attendu=[77, 79, 81, 83]).`
Le 3ᵉ bras discrimine donc bien `op_Subtraction Caster@0x48`.

⇒ `AdjacentUnits(origin, 1, 3)`, `op_Subtraction`, `SelectUniqueUnits(ctx, 3)` et le contexte
construit par `GenerateAttackPredictions` sont **tous opérants**. Le seul terme qui reste est
l'`origin` — `RammingSpeedAbility$$GetTileToMoveTo()` chez `RammingSpeed`, `Target@0x60` ici.

### 8.3 L'arbre rend VIDE — il ne désigne pas une tuile isolée

Restaient deux causes indiscernables au compte d'events : l'arbre rend vide, ou il rend une tuile
dont le voisinage est vide. `probe_361_ramming_speed_forced_tile.py` **sature le ring** de la cible
(4 unités sur 6 voisins) : le pool de charge tombe à quelques tuiles, et le probe VÉRIFIE que
chacune porte au moins un voisin occupé — sous ce montage, « tuile isolée » est impossible.

| mesuré | valeur |
|---|---|
| pool (voisins libres de la cible) | `(2,3) (2,4) (4,3) (4,4)` |
| voisins occupés, par tuile du pool | **2 partout** (`min = 2`) |
| tuile du port | `(2,3)` |
| gate | `willBeKill = TRUE` (capteur #361, 1 appel) |
| events natifs, caster SANS la main (`aiMovableTiles` = absent) | **2** |
| events natifs, caster AYANT la main (`aiMovableTiles` = **13 tuiles**) | **2** |

Le second tir réfute l'explication de montage : `MovableTilesInRangeSelector$$Select` délègue à
`IBattleQuery.GetMovableTilesInRange(unit, fromTile, ignoreFlags, options)` avec `ignoreFlags = 0`
(le littéral que `GetTileToMoveTo` passe), donc un caster sans mouvement aurait vidé l'arbre pour
une raison de harnais. Avec 13 tuiles disponibles, le compte ne bouge pas d'un iota.

### 8.4 Verdict

**`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo`, évalué
dans le contexte que `ComparablePlaybook<T>$$GenerateAttackPredictions` construit, rend un ensemble
VIDE** — alors que le MÊME arbre rend la bonne tuile dans le contexte de
`RammingSpeedAbility$$GetDynamicInvalidTargetReason` (cast réel : MATCH 2/2, `case-353` §5bis) et
dans celui du combat.

## 9. Le maillon interne : résidu NOMMÉ, et le point d'ancrage qui le tranche

Le pool est `MovableTilesInRange(Caster@0x48, CasterTile@0x50, Direct(range), 0, 0)
op_BitwiseAnd CanAddUnit(AdjacentTiles(Target@0x60))`, trié puis `First(…, 1)`.

Ce que la lecture donne, et qui **oriente sans trancher** :

* Les deux contextes diffèrent sur **trois** slots : `+0x18` (`Owner`), `+0x38` (`TargetTiles`),
  `+0x48` (les tuiles du caster). Le gate ne renseigne que `+0x08`, `+0x10`, `+0x40`.
* Un seul nœud de l'arbre **change de branche** entre les deux : `CasterTileSelector$$Select` lit
  `ctx+0x48` en PRIORITÉ, et ne retombe sur `ToList(ctx+0x40)` que si `+0x48` est nul — c'est-à-dire
  exactement le cas du gate.
* `MovableTilesInRangeSelector$$Select` est le **seul retour vide silencieux** de la chaîne haute :
  il rend une liste vide si le sélecteur d'unité rend `null`, et si `fromTileSelector` rend `null`.
  Partout ailleurs un maillon absent tombe dans le thrower.
* `DSLSelectors$$CanAddUnit(tiles)` (surcharge à 2 arguments, celle qu'emploie `GetTileToMoveTo`)
  fixe son `parent` à un sélecteur alloué `new …(state, null, null)` — donc **indépendant du
  contexte** ; et `TileExtensions$$CanAddUnitFromAbility` est plus PERMISSIF avec un `parent` non
  nul (`IsTileReservedForOtherUnit`). Ce n'est donc pas là que le playbook perdrait des tuiles.

**Capteur à poser** (aucun n'existe — l'agent ne peut pas réinjecter) :
`IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select`, en lisant l'unité rendue par
le sélecteur d'unité, la tuile rendue par le sélecteur de tuile, et la taille du retour. Un seul
hook sépare les trois hypothèses restantes (`unit == null` / `fromTile == null` / query vide).
Second choix, un cran plus haut : `IdunBattle.Entities.Selectors.CasterTileSelector$$Select`.

## 10. Ce qui n'est PAS couvert

* **Les batchs 3/4 restent NON PORTÉS**, et c'est désormais un choix ÉTAYÉ : le natif n'en émet
  aucun, sur aucun montage joué — un port les émettrait là où le jeu ne les émet pas. `1059`
  n'entre toujours pas dans `ABILITY_CLASSES` (seule `GetTileToMoveTo` est portée, #353-r1 volet a).
* **Le maillon interne de `GetTileToMoveTo`** (§9) : nommé, non tranché, faute de capteur.
* **La gate de Fragstorm** (§5) : son ouverture reste indéterminée, son batch étant mort en aval.
* **Le régime fully-shared generic** : l'hypothèse « le lambda reçoit un pointeur décalé » est
  ÉCARTÉE par le capteur (`get_WillBeKill` rend TRUE sur l'objet décodé), pas démontrée impossible.
* **Deux géométries** ont été jouées côté `RammingSpeed` (§1 et §8.3) ; côté `ExplosivePresents`,
  trois bras sur une seule géométrie de board `MC1_67`.
