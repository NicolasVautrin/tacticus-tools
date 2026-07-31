# case-361 — `RammingSpeed` batchs 3/4 : ni la gate, ni `GetTileToMoveTo` — le MONTAGE

Suite de `#353-r1` volet (b), `#372`, `#365/#386`, `#370`.

> **⚠ CE QUI A CHANGÉ (#370, 2026-07-31) — lire §8.5 AVANT le reste.** Les §1 à §8.4 restent
> valables comme MESURES, mais leur conclusion §8.4 (« l'arbre `GetTileToMoveTo` rend VIDE dans le
> contexte du playbook ») est **RÉFUTÉE** : sur la géométrie EXACTE de §1, avec le build STRICTEMENT
> identique, le natif émet **5 events == 5 attendus** dès que la géométrie est montée par un AUTRE
> chemin. Le vide de §1 est un **artefact du montage de `probe_361`**, pas une propriété du natif.

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

### 8.4 Verdict de #386 — **RÉFUTÉ par #370**, cf. §8.5

Il disait : « `RammingSpeedAbility$$GetTileToMoveTo`, évalué dans le contexte que
`ComparablePlaybook<T>$$GenerateAttackPredictions` construit, rend un ensemble VIDE ». Cette
conclusion tirait d'un montage UNIQUE (celui de `probe_361`) une propriété du NATIF. Elle est
fausse : le même natif, sur la même géométrie, émet les batchs dès que le montage change.

### 8.5 Les batchs 3/4 SORTENT — et le sélecteur est EXACT (#370)

`probe_361_movable_tiles_selector.py` monte le bras `ramming` par `montage_361.build_montage`
(greffe `orksKillaKan ← 1059`, `--hp-player 60`, caster borné à la portée de charge), puis rejoue
sur le MÊME runner la géométrie de §1, reproduite **littéralement** (`GEO_386`).

| montage | géométrie | build | events | attendu | verdict |
|---|---|---|---|---|---|
| `montage_361` — bras A | cible (3,4), ami (2,3), ennemi (2,4), caster (6,7), tuile (3,5) | seed 37000 | **4** | 4 | **EXACT** |
| `montage_361` — bras B | **§1 verbatim** : cible (4,7), ami (4,6), ennemi (5,8), caster (1,4), tuile (5,7) | seed 37000 | **5** | 5 | **EXACT** |
| `montage_361` — bras B | idem | **seed 36100, mult 100** (= `probe_361`) | **5** | 5 | **EXACT** |
| `probe_361` | idem §1 | seed 36100, mult 100 | **2** | 5 | batchs absents |

Les trois premières lignes portent les événements attendus, **avec leurs cibles exactes** :
bras B rend `necroWarden`(4, batch 1), `orksKillaKan`(60, batch 2 — le recul), puis
`astraBullgryn`(41, batch 3 `Friends`), `ultraTitus`(27) et `necroWarden`(27) (batch 4 `Enemies`).
Le second event de `necroWarden` porte un dégât DIFFÉRENT du premier (27 ≠ 4) : c'est bien un autre
batch, pas un doublon de lecture. La cible apparaît deux fois **par construction** — la tuile
d'arrivée sort de `CanAddUnit(AdjacentTiles(Target))`, elle lui est donc toujours adjacente.

⇒ **`AdjacentUnits(GetTileToMoveTo(), 1, 3)`, `Friends`, `Enemies` et le contexte du playbook sont
tous OPÉRANTS.** Le natif émet les batchs 3/4, et il les émet JUSTES.

**Ce qui reste ouvert** : *quel élément du montage de `probe_361`* vide le pool. Les deux builds
sont identiques (même seed, même rank, mêmes unités, même `--hp-player`, mêmes dégâts mesurés :
`necroWarden` à 4), la géométrie finale est identique, la session est la même. La seule différence
constatée est le **chemin de drive** — `probe_361` déplace les quatre unités en UN `drive_to`, là
où `montage_361` en fait deux (voisinage puis caster, parade au blocage de trajet) et où le bras B
en ajoute deux autres. C'est un résidu NOMMÉ, et c'est exactement ce que le capteur de §9 tranche :
il est câblé sur `probe_361` **et** sur `probe_361_movable_tiles_selector`, donc il lira les deux
régimes côte à côte.

## 9. Le maillon interne : le capteur, LIVRÉ (#370) — inerte jusqu'au reinject

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

### 9.1 Le capteur livré — `frida/hooks/features/ai-step/movable-tiles-probe.ts` (#370)

Point d'ancrage principal : **`IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select`**,
re-confirmé au décompilé. Son corps porte **trois** issues, dans cet ordre :

```
entity   = unitSelector.<slot 7>(ctx)        ; if (entity == null)   -> rend la List VIDE
fromTile = unitTileSelector.<slot 0xc>(ctx)  ; if (fromTile == null) -> rend la MEME List VIDE
return     IBattleQuery.GetMovableTilesInRange(entity, fromTile, ignoreFlags, options)
```

Le ctor donne les champs (`MovableTilesInRangeSelector$$.ctor` : `state`, `battleQuery`,
`unitSelector`, `unitTileSelector`, `overrideRange`, `ignoreFlags`, `ignoreUnitsOnTiles`) — le
capteur les lit par leur **nom runtime**, aucun offset écrit en dur.

⚠ `entity` et `fromTile` sont des **LOCALES** : un `Interceptor.attach` sur `Select` seul ne les
voit pas. Le capteur arme donc AUSSI les deux sous-sélecteurs qui les produisent, tous deux
NOMMÉS et à corps court — c'est la seule correction apportée au choix d'ancrage de #386 :

* `IdunBattle.Entities.Selectors.CasterSelector$$Select` — corps ENTIER :
  `if (ctx+0x08 == 0) return new List<T>(); l = new List<T>(1); l.Add(ctx+0x08); return l;`
  ⇒ sa taille de retour EST le maillon 1.
* `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` — corps ENTIER :
  `tiles = ctx+0x48; if (tiles == null) tiles = ToList(ctx+0x40);
   if (tiles == null) tiles = EntityExtensions$$GetTiles(ctx+0x08, state); return new List<T>(tiles);`
  ⇒ sa taille de retour EST le maillon 2, et la branche prise se lit sur `+0x48`/`+0x40`.
  Le slot `0xc` est `IdunBattle.DSL.TargetsSelector$$SelectTile`, qui rend `0` quand son
  énumération ne produit ni tuile ni unité placée — le seul chemin vers `fromTile == null`.

Discipline : armé à la demande (flag RPC `tileProbe` d'`aiPlaybookPredict`, composable avec
`gateProbe`), filtré sur le thread appelant, détaché en `finally`, borné à 64 entrées, résolution
par `findClassAnywhere` + `findMethod` (aucune RVA). **Tri-état par maillon.**

### 9.2 Les onze états du décodeur, deux à deux distincts

`probe_361_movable_tiles_selector._tile_verdict` dérive le verdict des CHAMPS. Garde offline :
`scripts/python/tests/engine/test_370_tile_probe_tristate_offline.py` (11 tests, 100 % offline).

| état | ce qu'il établit |
|---|---|
| `absent` | capteur pas dans le bundle injecté |
| `non-arme` | demandé, maillon non résolu — erreur NOMMÉE |
| `zero-appel` | `Select` jamais appelé ⇒ l'arbre n'est PAS évalué, cause en **AMONT** (`First` / `SortTilesByUtility` / `op_BitwiseAnd` / `AdjacentTiles`) |
| `pool-non-vide` | pool rendu non vide ⇒ perte en **AVAL** |
| `retour-illisible` | forme du retour non décodable — une ERREUR, pas un zéro |
| `unit-null` | pool vide **et** `CasterSelector` rend 0 ⇒ `ctx+0x08` nul |
| `from-tile-null` | pool vide, caster présent, `CasterTileSelector` rend 0 ⇒ `SelectTile` null |
| `query-vide` | les deux entrées présentes ⇒ c'est `GetMovableTilesInRange` qui rend vide |
| `structure-inattendue` | les sous-sélecteurs ne sont pas ceux attendus — le décodeur REFUSE de conclure |
| `sous-maillon-non-arme` | le nœud est armé, pas les sous-sélecteurs |
| `fenetre-vide` | corrélation par séquence en échec |

Le piège que la garde verrouille : **`nodes == []` et `returnedCount == 0` portent des verdicts
OPPOSÉS** (amont vs pool). Mutation adversariale jouée, message ROUGE verbatim :
`AssertionError: assert 'zero-appel' != 'zero-appel'`.

### 9.3 Le retour se lit en DEUX formes — le capteur n'en décodait qu'une (#374)

Premier tir **armé** (session 3) : le capteur fire — **4 appels de
`MovableTilesInRangeSelector$$Select` sur chacun des deux bras** — et rend `[retour-illisible]`
partout, `classes = ['OrderedSet`1' ×4]`. Le contrôle positif disait l'inverse (bras A : 4 events
== 4 attendus ; bras B : 5 == 5), d'où le verdict `CAPTEUR INCOHERENT AVEC LE CONTROLE POSITIF`.

**Le tri-état a fait exactement son travail** : il a refusé de rendre `[vide]`. Un décodeur
permissif aurait ici re-fabriqué le faux « pool vide » que §8.5 venait de réfuter.

La cause, lue au décompilé — `MovableTilesInRangeSelector$$Select` rend **deux types différents** :

| issue | ce qui est rendu |
|---|---|
| `entity == null` | la `System.Collections.Generic.List`1` VIDE que le corps vient d'allouer |
| `fromTile == null` | la **même** `List`1` vide |
| la requête a répondu | le retour d'`IBattleQuery.GetMovableTilesInRange` = un **`idun.shared.collections.OrderedSet`1`** |

⇒ La **classe du retour est elle-même discriminante**, et c'était l'information manquante.

**`OrderedSet<T>` DÉRIVE de `List<T>`** — établi sur le binaire, pas supposé :

* `idun.shared.collections.OrderedSet<T>$$.ctor` appelle
  `System.Collections.Generic.List<T>$$.ctor` **sur le même `this`**, puis n'ajoute que son
  `HashSet<T>` propre à `this+0x28` ;
* `OrderedSet<T>$$get_Item` **délègue** à `List<T>$$get_Item(this, index, …)` ;
* `List<T>$$get_Item` donne le layout VERBATIM : borne `_size` = `*(uint*)(this+0x18)`, tableau
  `_items` = `*(this+0x10)`, élément à `items + 0x20 + element_size * i`.

**Confirmé LIVE sur la session courante**, deux voies indépendantes (aucun reinject requis) :

| voie | mesure |
|---|---|
| RPC `classFields("idun.shared.collections", "OrderedSet`1")` | `_items` **@+0x10** et `_size` **@+0x18**, tous deux `declaredBy = List`1` ; `_set` (`HashSet`1`) déclaré par `OrderedSet`1` |
| RPC `aiMovableTiles` (runner 111, `MC1_67`) | **166 tuiles** décodées sur 10 unités, **0 coordonnée invalide** — `internals.extractTiles` lit déjà un `IOrderedSet<IEntity>` natif à ce layout exact |

**Le correctif** (`readRefList`) reconnaît la forme par la **chaîne d'héritage IL2CPP**
(`class_get_parent` jusqu'à `List`1`), jamais par une liste de noms en dur : toute sous-classe se
décode, et ce qui n'en est pas une reste une ERREUR NOMMÉE. Le **stride n'est pas supposé** non
plus — la classe d'élément est interrogée (`class_get_element_class` + `class_is_valuetype`) et un
élément de type VALEUR fait répondre `-1` plutôt que des coordonnées plausibles.

**Ce qui NE change pas** : les 11 états restent 11, et `[retour-illisible]` reste strictement
distinct de `[vide]`. Ce qui s'ajoute est de l'information, pas de la permissivité — le capteur
publie la forme de stockage retenue, le chemin d'héritage, la classe d'élément et la **raison
nommée** d'un refus. Garde portée à **16 tests** offline.

⚠ **Un `[retour-illisible]` a désormais DEUX lectures, et le décodeur les sépare** : le capteur à
jour qui refuse un type inconnu, contre un **bundle injecté antérieur au correctif** (le code est
livré, pas chargé). Discriminant : le capteur corrigé pose toujours `returnedStorage`
(`probe_predates_374`). Sans cette distinction, un rouge post-correctif se lirait « le correctif ne
marche pas » — l'ambiguïté même qui fait tourner ce résidu en rond. Le **verdict du run** en tient
compte : un capteur armé mais non corrigé bascule en **`NON CONFRONTÉ`**, plus en
`CAPTEUR INCOHERENT AVEC LE CONTROLE POSITIF` — accuser le capteur quand la correction n'est pas
chargée est un faux diagnostic. `ok` reste `False` dans les deux cas : aucune permissivité gagnée.

État mesuré après correctif (session 3, bundle **non** rebuildé) :

```
[370] NON CONFRONTE : ... Le capteur INJECTE est ANTERIEUR a #374 (il ne publie pas
      `returnedStorage`) : la lecture d'`OrderedSet` est livree mais PAS CHARGEE -- fenetre de
      reinject en attente, rien n'est conclu du natif. Les DEUX bras sont PRETS et DISCRIMINANTS
      ... bras A ((6,7)) emet 4 events == 4 attendus, bras B ((1,4), geometrie de #386) 5 pour 5.
```

**Ce que la garde offline ne couvre PAS** : elle verrouille le **décodeur** (`_tile_verdict`,
`probe_predates_374`), pas le **capteur TS**. Un capteur qui rendrait `0` là où il ne sait pas lire
tromperait le décodeur sans qu'aucun test offline ne le voie — c'est précisément pourquoi
`readRefList` ne possède **aucun** chemin qui produise `0` sur une forme non reconnue.

## 10. Ce qui n'est PAS couvert

* **`1059` n'entre toujours pas dans `ABILITY_CLASSES`** (seule `GetTileToMoveTo` est portée,
  #353-r1 volet a). Mais la justification de #386 (« le natif n'émet aucun batch ») **tombe** :
  §8.5 mesure 4/4 et 5/5. Le port des batchs 3/4 redevient une tâche ouverte, pas un refus étayé.
* **Le capteur de §9 a été armé une fois (session 3) et n'a rien pu LIRE** — sa correction (§9.3)
  est à son tour livrée, compilée (`frida-compile`, rc 0) et **NON CHARGÉE** : elle vit dans
  `frida/hooks/*` et demande une fenêtre de reinject. Le verdict cohérent avec le contrôle positif
  reste donc **NON CONFRONTÉ**. Ce qui EST confronté sur la session courante : la structure lue
  (`classFields` → `_items`@+0x10 / `_size`@+0x18 `declaredBy = List`1`) et le décodage à ce layout
  d'un `IOrderedSet` natif (`aiMovableTiles` → 166 tuiles, 0 coordonnée invalide).
* **Quel élément du montage de `probe_361` vide le pool** (§8.5) : résidu nommé, non tranché. Seule
  différence constatée : le chemin de drive (un `drive_to` groupé contre deux en cascade).
* **La gate de Fragstorm** (§5) : son ouverture reste indéterminée, son batch étant mort en aval.
* **Le régime fully-shared generic** : l'hypothèse « le lambda reçoit un pointeur décalé » est
  ÉCARTÉE par le capteur (`get_WillBeKill` rend TRUE sur l'objet décodé), pas démontrée impossible.
* **Quatre géométries** ont été jouées côté `RammingSpeed` (§1, §8.3, et les deux bras de §8.5) ;
  côté `ExplosivePresents`, trois bras sur une seule géométrie de board `MC1_67`.
