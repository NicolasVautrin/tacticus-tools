# case-361 — `RammingSpeed` batchs 3/4 : la gate n'est pas coupable, et le pool non plus

Suite de `#353-r1` volet (b) et de `#372`. Trois causes étaient déjà tombées ; ce cas en fait tomber
**trois de plus** et réduit le résidu à **un seul maillon**, avec le capteur qui le tranche livré.

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

## 4. Ce qu'il reste, et le capteur qui le tranche

Tuile juste, voisinage peuplé, flag opérant, contexte plus riche que celui qui suffit au gate — et
0 event. **Un seul maillon n'a jamais été instrumenté** : ce que
`System.Linq.Enumerable$$Any<T>(selfPreds, RammingSpeedPlaybook.<>c$$<MakeDamagePredictions>b__2_0)`
fait du prédicat. Le capteur #372 lit `get_WillBeKill` sur l'event **RENDU** ; personne n'a lu ce que
le natif **APPELLE**.

**Livré, INERTE jusqu'au prochain reinject** : `frida/hooks/features/ai-step/playbook-gate-probe.ts`
+ le flag `gateProbe` d'`aiPlaybookPredict`. Il intercepte `get_WillBeKill` — foyer UNIQUE du
prédicat, quel que soit le chemin — **le temps d'une invocation**, filtré sur le thread appelant,
détaché en `finally` (ce symbole est aussi appelé par `idun.Ui.IdunUnitHud$$ShowPrediction` à chaque
frame : jamais de hook permanent). Trois issues, toutes discriminantes, et `probe_361` les traduit
déjà (`_gate_verdict`) :

| mesure | ce qu'elle établit |
|---|---|
| **0 appel** | `Any` n'invoque pas le prédicat — la liste qu'il itère est vide CÔTÉ NATIF |
| **rend `true`** | la gate OUVRE ⇒ la cause est en AVAL, dans l'évaluation des sélecteurs 3/4 |
| **rend `false`** | le natif lit un AUTRE objet que celui décodé (paramètre du lambda en régime fully-shared generic) |

## 5. Trouvaille de bord : un batch natif MORT par contexte vide

`FragstormGrenadeLauncherPlaybook$$MakeDamagePredictions` (1048) porte le même motif — gate
`get_WillBeKill` DIRECTE, puis un batch supplémentaire — mais son batch est **inobservable, et c'est
LU** : `TargetsSelector$$SelectUniqueUnits` y est évalué sur un contexte `memset(0, 0x128)` **jamais
renseigné**, donc `GetOtherTargets` = `Damageable(SurroundingEnemies(Owner@0x30, range, 1, 3) −
Target@0x60)` est vide que la gate ouvre ou non. Mesuré (volet B, `templAggressor`, porteur ACTIF du
pool, un 2ᵉ ennemi à distance 1) : **1 event dans les deux bras**, `willBeKill` false puis true.
Le probe l'enregistre et **refuse** de le compter comme discriminant.

## 6. Ce qui n'est PAS couvert

* **Les batchs 3/4 restent NON PORTÉS** — pas de port spéculatif : tant que le natif n'en émet aucun,
  rien n'est confrontable. `1059` n'entre toujours pas dans `ABILITY_CLASSES` (seule
  `GetTileToMoveTo` est portée, #353-r1 volet a).
* **La gate de Fragstorm** (§5) : son ouverture reste indéterminée, son batch étant mort en aval.
* **Le régime fully-shared generic** : l'hypothèse « le lambda reçoit un pointeur décalé » est
  NOMMÉE, pas tranchée — c'est précisément ce que le capteur mesurera.
* **Une seule géométrie** a été jouée pour la mesure principale (§1) ; elle exerce les deux
  sélecteurs (amis ET ennemis adjacents), mais un balayage n'a pas été fait — inutile tant que le
  compte ne bouge pas d'un iota.
