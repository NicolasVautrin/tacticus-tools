# #969-r1 / #971-r2 — la porte ALÉATOIRE de `BasePlaybook$$ShouldEvaluate`

**Question posée** : porter une porte aléatoire dans un moteur déterministe n'a de sens que si
notre tirage peut être confronté au sien. Fallait-il **reproduire** le tirage, ou **modéliser** la
porte comme une probabilité ?

**Réponse tranchée par la RE, pas par commodité : MODÉLISER.** Et la probabilité est désormais
**mesurée**, pas assumée.

## 1. Le mécanisme, LU de bout en bout

`IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate(unit)` (les deux arités) :

```
p = <virtuelle +0x1f8 GetUseProbability>(this, unit[, actionTiles]);
if (Fix64.op_GreaterThanOrEqual(p, Fix64(1))) return true;    // extrémité DÉTERMINISTE
if (Fix64.op_LessThanOrEqual   (p, Fix64(0))) return false;   // extrémité DÉTERMINISTE
return <IPseudoRNG @this+0x30>.<slot 4 NextBool>(p);          // TIRAGE
```

Le slot 4 d'`IdunBattle.Utils.PRNG.IPseudoRNG` est `NextBool(Fix64)` — à distinguer du **slot 5**,
`NextBool(int)`, qui prend un **pourcentage 1..99** et tire un `genrand_int32() % 99`. Le corps
terminal est `IdunBattle.Utils.PRNG.MersenneTwister$$NextBool` :
`genrand_real2() < p`, un **Mersenne Twister**.

## 2. Pourquoi la reproduction est ÉCARTÉE — trois faits, tous lus

1. **Le PRNG est injecté**, pas construit : `IdunBattle.AI.Playbook.BasePlaybook$$Init(…, random, …)`
   écrit `this.<+0x30>` ; il vient d'`IdunBattle.AI.PlaybookDatabase$$.ctor(…, random, …)`.
2. **`IdunBattle.Runner.IdunRunner$$Initialize` construit DEUX `PlaybookDatabase`**, et
   `IdunBattle.Core.Services.AiControl$$Init` **nomme ses paramètres**, ce qui tranche laquelle
   sert à quoi :
   * `playbookDatabase` / `random` → le `pseudoRNG` de la bataille
     (`IdunBattle.Utils.PRNG.MersenneTwister$$.ctor(rngSeed)`) — **déterministe** ;
   * `humanAiPlaybook` / `humanAiRandom` → un MT **neuf**, seedé par
     `System.DateTime$$get_Now().Ticks` — **non reproductible EN PRINCIPE**, quelle que soit la seed
     de la BC.
3. **Le MT de bataille est PARTAGÉ.** Le même objet est passé à
   `IdunBattleLogic.Entities.DSLFactory$$.ctor` (qui l'enveloppe dans
   `IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$.ctor`), à
   `IdunBattle.Core.Services.DamageCalculations$$Init`, à
   `IdunBattle.Core.Services.UtilitiesDatabase$$.ctor` et à `AiControl$$Init`.

⇒ Reproduire le tirage exigerait de rejouer **toute** la séquence de consommation du même flux
depuis le début de la bataille (dégâts, esquive, blocage, sélecteurs DSL, utilities, stratégie),
dans l'ordre exact — et **une seule consommation non modélisée décale tout le reste sans erreur**.

**Confirmation empirique, gratuite** : deux exécutions du **même** `aiDryRunAllUnits` sur le **même
état** ont rendu `False` puis `True` pour `Waaagh` à `p = 0.25`. Le tirage n'est pas une fonction
de l'état que le port voit.

## 3. Ce qui est livré : `p` devient une VALEUR, donc confrontable

Le port sépare les deux étages **comme le natif** :

* `NonComparablePlaybook.use_probability(ctx)` — mirror du slot `0x1f8`. Défaut `1.0` (les deux
  surcharges de base rendent `Fix64(1)`), donc **value-preserving** pour tout playbook qui ne
  surcharge rien ; `None` = **pas mesuré**, jamais `0.0` (qui ferait REFUSER).
* `_base.probability_gate(p)` — le triage des trois branches, **foyer unique**.

Les trois porteurs, **mirror 1:1** :

| ability | formule native LUE | notes |
|---|---|---|
| `1049 CrusadeOfWrath` | `<statics +0x08> * Fix64(GetMaxFriendlyUnitsBuffed(unit))` | `<statics +0x08>` = `Fix64.FromIntFraction(1, 10)` écrit par le `.cctor` ⇒ **0,1 × maxBuffé** |
| `1106 WarHowl` | `0` si `mine.Items.Count == 0` ; sinon `pct(n >= 3 ? 100 : (n == 1 ? 75 : 50))` | `n` = allié buffé ayant une cible d'attaque normale. **NON monotone** : `n = 0` et `n = 2` valent tous deux `50` |
| `1058 Waaagh` | `Fix64(nB * ts) * Fix64.FromIntFraction(5, 100)` | `ts` = `GetStat(unit, 0xc = TurnsStarted)` |

**`n` de WarHowl est désormais porté**, alors que le port argumentait — à raison — que c'était du
code mort (les trois valeurs sont > 0, donc aucune ne déplace un verdict). L'argument est **périmé**
depuis que `p` est confrontable : sans `n`, ce porteur serait le seul des trois à n'avoir rien à
comparer.

## 4. La confrontation — `probe_969r1_prob_confrontee.py`

Le capteur `shouldEvaluateTrace` (`frida/hooks/probes/should-evaluate-trace.ts`) était **en vol et
ON-DEMAND** ; il ne manquait que de l'armer. Il ancre aussi
`IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextBool` (overload `Fix64`), dont `args[1]` **EST**
`p`, et n'attribue un tirage que s'il est **imbriqué** dans un `ShouldEvaluate` sur le même thread.

Seed 777 / **MC1_67**, capteur armé, `aiDryRunAllUnits` (read-only) :

| montage | unité | ability | port | natif | verdict |
|---|---|---|---|---|---|
| SPAWN | u83 `templHelbrecht` | CrusadeOfWrath | 0,40 | 0,40 | **ACCORD** |
| SPAWN | u85 `spaceBlackmane` | WarHowl | 0,00 | *aucun tirage* | **ACCORD** (extrémité déterministe) |
| SPAWN | u87 `orksWarboss` | Waaagh | 0,25 | 0,25 | **ACCORD** |
| CONTACT | u79 `templHelbrecht` | CrusadeOfWrath | 0,40 | 0,40 | **ACCORD** |
| CONTACT | u81 `spaceBlackmane` | WarHowl | **0,75** | **0,75** | **ACCORD** |
| CONTACT | u83 `orksWarboss` | Waaagh | 0,15 | 0,15 | **ACCORD** |

**6/6.** Le montage CONTACT n'est pas un doublon : il **déplace** les unités (`--place`/`--a-place`)
pour amener Ragnar au contact, **seul régime** où WarHowl sort de son zéro déterministe et entre
dans la bande de tirage — c'est lui qui exerce `n` (valeur `0,75` ⇒ `n = 1`).

**Il a trouvé un vrai bug** : `has_ranged_weapon` vit dans `engine.services.battle_query`, pas
`engine.battle_query`. Le montage de spawn ne l'atteignait pas (WarHowl y rend `0.0` avant), donc
un smoke offline l'aurait laissé passer.

⚠ **Limite assumée de l'appariement** : `ShouldEvaluate` ne publie pas l'ability. Le probe apparie
par **unité** et ne prononce un verdict que si l'unité n'a produit **qu'une seule** valeur de
tirage ; deux valeurs ou plus ⇒ `AMBIGU`, jamais un appariement deviné.

## 5. Ce qui reste OUVERT

L'écart de comportement **demeure** et il est nommé : dans la bande `]0,1[` le moteur PROPOSE là où
le natif TIRE. Le port reste **permissif** à dessein (refuser rendrait l'ability invisible, le
défaut le plus cher, #967). Ce qui a changé : l'écart est **mesuré** au lieu d'être assumé, et la
formule qui le produit est **vérifiée exacte**.

Résidu neuf : **`#969-r6`** — l'écart de la bande n'est pas *quantifié* (à quelle fréquence le
natif refuse-t-il un cast que le port propose ?). Le capteur rend cette mesure possible en
répétition ; elle n'est pas faite ici.

## 6. Re-dériver

```powershell
python scripts/python/probe_969r1_prob_confrontee.py --runner <id>
python -m pytest scripts/python/tests/engine/test_969r1_use_probability_offline.py -q
```
