# case-130 — `PickRandomly` consomme du RNG même quand le pool tient déjà dans `n` (GAP #215)

## Le critère

> **Le sélecteur natif de tirage aléatoire consomme-t-il des tirages du PRNG de bataille lorsque le
> nombre de candidats est `<= amount` — c'est-à-dire quand il n'y a AUCUN choix à faire ?**

## La réponse

**OUI.** Le sélecteur tire **`min(len(pool), amount)`** fois, avec les bornes **décroissantes
`len(pool)`, `len(pool)-1`, … 1**, y compris quand le pool tient entièrement dans `amount`. Il n'y a
**aucun court-circuit** « le pool tient » dans le code natif.

Conséquence : le court-circuit du port (`if len(items) <= n: return items`) était un **bug de flux
RNG**, invisible sur le tirage lui-même (le SET rendu était le bon) et visible uniquement **en aval** —
tout ce qui consomme du RNG après le pick (dégât, crit, block, tirages de cible suivants) était décalé.

## La preuve décompilée

Nœud DSL : `IdunBattleLogic.Entities.DSLFactory$$PickRandomly` (deux surcharges : `amount` littéral vs
`amount` = nœud formule) → construit `IdunBattle.Entities.Selectors.PickRandomAmountSelector`.

Champs du sélecteur, lus dans `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$.ctor`
(mapping par le ctor, **jamais** deviné) :

| champ | rôle |
|---|---|
| `+0x18` | sélecteur SOURCE (le pool) |
| `+0x20` | `amount` (int résolu) |
| `+0x28` | `amount` formule (surcharge 2) → écrit `+0x20` au `Select` |
| `+0x30` | `allowRepeat` (bool) |
| `+0x34` | `maxRepeat` (int) |
| `+0x38` | `ignoreForcedTargets` (bool) |
| `+0x40` | service RNG (`IPseudoRNG`) |

Corps de `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select`, remis en C# :

```csharp
var candidates = source.Select(entities).ToList();          // +0x18
if (amountFormula != null) amount = amountFormula.Calculate(entities);   // +0x28 -> +0x20
var result = new List<T>();
if (!ignoreForcedTargets)                                   // +0x38
    AddForcedTargetsAndUpdateCandidates(this, caster, candidates, result, allowRepeat, amount);

int i = result.Count;
while (i < amount) {                                        // +0x20
    if (candidates.Count < 1) return result;                // SEULE sortie anticipée
    var dc  = new <>c__DisplayClass11_0();
    int idx = rng.NextInternal(0, candidates.Count);         // <-- 1 TIRAGE, INCONDITIONNEL
    var picked = candidates.ElementAt(idx);
    dc.item = picked;
    result.Add(picked);
    if (!allowRepeat) candidates.RemoveAt(idx);              // +0x30
    else if (result.Count(x => x.Id == dc.item.Id) == maxRepeat) candidates.RemoveAt(idx);   // +0x34
    i++;
}
return result;
```

Trois lectures qui tranchent :

1. **Il n'existe aucun test `candidates.Count <= amount`.** La seule sortie anticipée est
   `candidates.Count < 1` — *pool VIDE*, pas *pool qui tient*. Donc pour `k = len(pool) <= amount`, la
   boucle tourne `k` fois puis sort sur pool vide → **`k` tirages**.
2. **La dernière borne vaut 1, et une borne de 1 CONSOMME.**
   `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` avec `range == 1` prend la branche
   *puissance-de-deux* (`(-rng & rng) == rng` est vrai pour 1) : elle appelle `genrand_int32()` et
   retourne 0. Un tirage « sans choix » reste **un tirage** — même famille de piège que le
   wasted-resolve `Next(v, v+1)` de largeur 1.
3. **`allowRepeat` est FAUX pour les `PickRandomly` du jeu.** Vérifié au call-site :
   `IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormAbility$$ExecuteBehaviour` passe `0`
   (`+0x30`) et `0x7fffffff` (`+0x34`) — donc `RemoveAt` à chaque tour, donc les bornes décroissent
   strictement `k, k-1, … 1`.

L'ordre rendu est l'**ordre de tirage** (le natif `Add`e au fur et à mesure). Pour un consommateur
d'ATTAQUE cet ordre est ensuite écrasé :
`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` fait, après avoir résolu son sélecteur de
cibles, `if (targets.Count > 1) targets = targets.OrderBy(<>c.<Execute>b__5_0).ToList()` — un `OrderBy`
sur une clé scalaire par unité. **Le pick fixe donc le SET et la CONSOMMATION ; l'`OrderBy` fixe
l'ordre d'application des coups.**

## La mesure discriminante

Sonde : `scripts/python/probe_215_pick_randomly_rng.py` (versionnée). Porteur **PlasmaCannon** (1150,
`darkaTerminator`, héros spawnable) : son splash est
`PickRandomly(UnitsDirectlyBehind(caster, target), nrOfTargets = 2)` — un pool d'**unités** (pas de
tuiles vides), donc le cardinal natif du pool == celui du port, et la consommation est confrontable
sans le résidu « pool en hexes » propre à Fragstorm.

**Instrument** — on ne compte pas des events (ils sous-estiment : une sous-opération qui retourne tôt
n'émet rien). On compte les `genrand_int32` **directement** : `dumpRng` avant/après le cast rend l'état
complet du Mersenne Twister (`mt[624]`, `mti`) ; on re-simule l'état AVANT pas à pas jusqu'à retrouver
l'état APRÈS, et **le nombre de pas EST le nombre de tirages**.

**Deux régimes** (indispensable — un seul ne sépare rien) : pool `k = 1` puis `k = 2`, avec
`amount = 2` dans les deux cas, donc `pool <= amount` partout. Géométrie identique (même board `MC1_67`,
même seed, mêmes tuiles) ; seul le nombre d'unités placées derrière la cible change.

| modèle | surplus prédit vs port sans pick (k=1, k=2) |
|---|---|
| « le natif ne roll pas quand le set tient » (port d'avant) | 0 , 0 |
| **`min(k, amount)` tirages, bornes décroissantes (décompilé)** | **1 , 2** |
| « `amount` tirages quoi qu'il arrive » | 2 , 2 |
| « un seul tirage » | 1 , 1 |

**Mesuré** (session 78, build `gqfc5mff6c`, seed 777) :

```
k=1 : LIVE 13 genrand | port sans pick 12  -> surplus 1
k=2 : LIVE 20 genrand | port sans pick 18  -> surplus 2
```

→ seul le modèle décompilé survit aux **deux** régimes. Et le port corrigé, exécuté en entier
(`PlasmaCannonAbility.execute_behaviour` → arbre DSL → `_pick_randomly_n`), consomme exactement
13 / 20 et devient **bit-exact per-coup vs live sur la MAIN *et* le SPLASH** :

| modèle | k=1 : spread(ratio live/offline) | k=2 |
|---|---|---|
| 0 tirage (avant) | 0.386 | 0.367 |
| **`min(k,n)` (après)** | **0.000** | **0.000** |
| `n` tirages | 0.413 | 0.000 |
| 1 tirage | 0.000 | 0.442 |

La MAIN reste à 1.0 dans tous les modèles (elle **précède** le pick) : c'est le contrôle qui prouve que
le désalignement mesuré vient bien du pick et pas d'un confond de magnitude.

## Ce qui a été corrigé

- **Foyer unique** : `scripts/python/engine/runner/abilities/loki/splash.py::_pick_randomly_n` — mirror
  1:1 de la boucle native. Les consommateurs (PlasmaCannon, Fragstorm, BringerOfDespair, Supercharge,
  Harbinger, Executioner, MartialApotheosis, summons/tuiles…) en héritent **sans code propre**.
- **`AttackWithAttackDamage(multi=True, pick_n=…)`**
  (`abilities/behaviours/combat.py`) re-trie par id **APRÈS** le pick : le `PickRandomly` vit dans le
  sélecteur (ordre de tirage), l'`OrderBy` de `AttackBehaviour$$Execute` s'applique après la résolution.
- **Oracles A/B de trois tests** rectifiés — ils comparaient l'arbre à une séquence directe
  `execute_ability_attack` **sans** le tirage du pick, c'est-à-dire à un flux RNG qui n'existe pas :
  `test_bringer_of_despair_live.py`, `test_executioner_live.py`, `test_martial_apotheosis_live.py`,
  `test_harbinger_of_destruction_live.py`. Le tirage est désormais reproduit explicitement dans la
  baseline, avec sa borne.

## La garde

`scripts/python/tests/engine/runner/test_pick_randomly_rng_live.py`

- **offline** : la loi dans le helper — `min(k, n)` tirages, bornes `(0,k), (0,k-1), …`, set = pool
  entier quand `k <= n` ; paramétré sur `(k,n) ∈ {(1,2),(2,2),(3,3),(4,2),(0,2)}`.
- **live (1)** : surplus de tirages mesuré == `{1: 1, 2: 2}`, et **exige que les deux régimes diffèrent**
  (sinon le scénario ne discrimine plus « `min(k,n)` » d'une constante, et le test le dit).
- **live (2)** : le port réel consomme exactement ce que le live consomme, et est bit-exact per-coup sur
  main + splash.
- **live (3) anti-tautologie** : le modèle « 0 tirage » est vérifié **NON** bit-exact sur le même état —
  si le court-circuit revenait, la garde rougirait ; et si le scénario cessait de discriminer, elle le
  dirait au lieu de passer.

Vérifié en conditions adversariales : court-circuit ré-injecté → **5 tests rouges** (dont le comptage
live et la bit-exactness du splash) ; court-circuit retiré → 9 verts.

## Le helper frère `n = 1` — même loi, autre foyer (CLOS)

Deux helpers portaient un `PickRandomly(source, 1)` en court-circuitant le tirage quand le pool ne
contenait qu'un candidat. Le décompilé les tranche : `amount = 1` et pool `k >= 1` → la boucle tourne
une fois et appelle `NextInternal(0, k)`, **même à `k == 1`**.

### Les six appelants, démêlés un par un

Le helper de `operations/spawn.py` était **ambigu** : ses appelants ne construisent pas tous le même
nœud natif. Chacun a été remonté à son `CreateBehaviour`/`ExecuteBehaviour` :

| appelant (port) | nœud natif LU | tirages |
|---|---|---|
| `triggers/base.py::_pick_randomly` ← `PsykerExtraAttackAbility$$CreateBehaviour` | `PickRandomly(Damageable(Enemies(caster, AdjacentUnits(target@0x178, 1, 3))), 1, 0, 0x7fffffff, false)` | **1** |
| `triggers/base.py::_pick_randomly` ← `EnvAmbushResurrectAbility$$CreateBehaviour` | `PickRandomly(GetValidDecoys(), 1, …)` sous `Foreach` | **1 / ressuscité** |
| `spawn.py::execute_self_replica` ← `ScarabSummonAbility$$ExecuteBehaviour` | `PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1, …)` | **1** |
| `spawn.py::execute_master_of_tutelaries_screamer` ← `MasterOfTheTutelaries_SummonAbility$$CreateSummonBehaviour` | `PickRandomly(TilesUnitCanAttackFrom(…).Otherwise(possible), 1, …)` | **1** |
| `spawn.py::execute` (ScarabHive) ← `ScarabHiveAbility$$ExecuteBehaviour` | `Cache(First(Get(SelectTiles(SortByDistance(SortByDistance(CanAddUnit(AdjacentTiles(target@0x178)), caster), caster))), count), 1)` | **0** |
| `spawn.py::execute_squighound_summon` ← `SquigHoundSummonUnitAbility$$CreateBehaviour` | `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(target@0x178)), 7, caster@0x160), 1)` | **0** |
| `spawn.py::execute_control_edict_summon` ← `ControlEdictAbility$$SummonMinion` | `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(caster@0x148)), 7, @0x160), 1)` | **0** |
| `spawn.py::execute_pilein_replica` ← `PileInAbility$$CreateBehaviour` | `First(SortByFormula(Randomize(CanAddUnit(AdjacentTiles(self@0x148))), If(HasTrait(0x1b), …)), 1)` | **`len(pool)`** |

Les quatre derniers ne sont **pas** des `PickRandomly` : les faire tirer aurait décalé le PRNG de tous
les spawns en aval. Le helper a donc été **scindé** — `_pick_randomly_one` (les deux sites `PickRandomly`,
délègue à `_pick_randomly_n`) et `_pick_placement_tile` (les quatre autres, inchangé).
`operations/triggers/loki/destroyer_hive.py::_pick_target` appliquait déjà la bonne loi — c'était le
seul site correct avant #130.

`DSLFactory$$Randomize` mérite d'être nommé : il construit **lui aussi** un
`PickRandomAmountSelector`, mais avec `amount = 0x7fffffff` — c'est donc un mélange complet qui
consomme **`len(pool)`** tirages, bornes décroissantes. PileIn relève de ce troisième nœud, pas des
deux autres.

### La mesure

Sonde : `scripts/python/probe_130_pick_randomly_one_rng.py`. Porteur **`astraPrimarisPsy`** (héros
spawnable) : son attaque normale RANGED psychique déclenche le splash Psyker, dont la cible sort d'un
`PickRandomly(…, 1)`. Même instrument que ci-dessus (`dumpRng` avant/après + re-simulation du MT).

**Trois régimes**, `k` = nb d'ennemis adjacents à la cible primaire = `|pool|` du pick :

| k | rôle |
|---|---|
| 0 | le splash ne fire pas → **baseline** : isole le coût de l'attaque principale seule |
| 1 | le modèle court-circuité saute le tirage, le décompilé le consomme |
| 2 | les deux modèles tirent (borne 2) → **contrôle** : le fix ne doit pas sur-tirer |

Le discriminant est le **contraste k=1 / k=2** : si le natif ne tirait pas quand le pool tient,
`live(k=1)` vaudrait `live(k=2) − 1`.

**Mesuré** (build `gqfc5mff6c`) — identique sur `seed 777 / MC1_67`, `seed 31337 / MC1_67` et
`seed 777 / C2_37`, avec des dégâts principaux différents à chaque fois (3336 / 2984 / 4278, donc de
vrais états PRNG distincts) :

```
k=0 : LIVE 1 | port corrigé 1 | port court-circuité 1
k=1 : LIVE 3 | port corrigé 2 | port court-circuité 1
k=2 : LIVE 3 | port corrigé 2 | port court-circuité 2
```

`live(k=1) == live(k=2)` → **le natif tire autant avec un pool de 1 qu'avec un pool de 2**. Le port
corrigé reproduit ce contraste (2, 2) ; le court-circuité ne le reproduit pas (1, 2).

**Pourquoi un comptage et pas une égalité de dégâts** : le montant du smite est PLAT
(`PercentageOf(StatAmount(Attack), psykerExtraDmg)`, aucune variance). Les per-coup live et offline
sont identiques **sous les deux modèles** — deux flux RNG décalés rendent ici le même dégât. Seul le
comptage sépare.

### Ce que la décomposition par étage a mis au jour

À `k = 0`, live et port consomment **exactement 1** : l'attaque principale est exacte. Dès que le
splash fire, il reste un écart **constant de 1 tirage** (k=1 comme k=2) — donc étranger au pick, et
imputable au volet smite : `HitDamage.get_damage` court-circuite à `min == max` (montant plat), alors
que le resolve natif `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` appelle
`Next(v, v+1)` **sans gate largeur-1**. Le port ne matérialise ce resolve que dans la branche ability
bounds-mode (`is_attack_damage_op`), pas dans `execute_normal_like`. Résidu nommé, chiffré, hors
périmètre — au backlog.

### La garde

`scripts/python/tests/engine/runner/test_pick_randomly_one_rng_live.py`

- **offline** : les deux helpers `n = 1` tirent `min(k, 1)` fois, borne `(0, k)`, pour
  `k ∈ {0, 1, 2, 5}` ;
- **offline, anti-fusion** : `_pick_placement_tile` est vérifié **distinct** (0 tirage à `k = 1`) — la
  garde rougit si quelqu'un « uniformise » les deux helpers ;
- **live** : `live(k=1) == live(k=2)` et `live(k=1) > live(k=0)` (sinon le scénario ne mesure pas le
  pick, et le test le dit) ;
- **live, anti-tautologie** : le modèle court-circuité est vérifié **incapable** de reproduire le
  contraste ; s'il y parvenait, le scénario ne distinguerait plus les deux réponses ;
- **live, attribution** : `k = 0` exact, et l'écart résiduel figé à 1 tirage par volet splash — il ne
  peut plus dériver en silence.

Vérifié en conditions adversariales : court-circuit ré-injecté → **3 tests rouges** (le helper
offline, le contraste live, l'attribution) ; retiré → 15 verts.

## Ce qui n'est PAS couvert

0. **Le régime « une seule tuile libre » des deux sites de SPAWN.** `execute_self_replica` et
   `execute_master_of_tutelaries_screamer` sont corrigés par mirror du même nœud natif (lu verbatim),
   et leurs tests ciblés restent verts — mais la géométrie où leur pool de tuiles tombe à **1** (summon
   entièrement encerclé) n'a pas été montée live. La loi, elle, est mesurée sur le vecteur Psyker.
1. **Ordre d'énumération du pool quand `len(pool) > amount`.** Le natif tire dans l'ordre du sélecteur
   source (ordre ECS, pas trié) ; le port id-trie avant de tirer. La **consommation** est désormais
   exacte dans tous les cas, mais **QUI** est piqué peut différer dès que le pool déborde `amount`.
   Résidu #215 restant (Fragstorm, PlasmaCannon >2 derrière, BringerOfDespair >1 adjacent, Harbinger,
   Supercharge).
2. **Fragstorm : pool en HEXES, pas en occupants.** `PickRandomly(AdjacentTiles(target) −
   Tiles(Friends(caster)), 4)` tire des **tuiles**, vides incluses (un tirage sur une tuile vide = coup
   gaspillé). Le port tire des occupants → le **cardinal** du pool diffère, donc le nombre de tirages
   aussi. Le fix du helper ne le couvre pas : il faut porter le sélecteur en tuiles. Cas à part.
3. **`AddForcedTargetsAndUpdateCandidates`.** `ignoreForcedTargets` (`+0x38`) est FAUX pour toutes les
   factories `PickRandomly` → le natif pré-remplit `result` avec les « only targets » du caster
   (`IdunBattle.Entities.UnitExtensions$$GetOnlyTargets`, non vide quand le caster est sous contrainte
   de ciblage type Taunt) et les retire des candidats. Ça change le nombre de tirages
   (`amount − forced`). Non porté, non mesuré ici (le harnais ne pose pas de contrainte de ciblage sur
   le caster).
4. **Le TRI natif des quatre sites de placement `First(…)`.** `_pick_placement_tile` rend la première
   tuile en ordre d'id et **consomme un tirage dès que le pool dépasse 1** — deux écarts, aucun lié au
   pick :
   - `SortTilesByUtilityForSummon(pool, 7, caster)` (SquigHound, ControlEdict) et le double
     `SortByDistance(…, caster)` de ScarabHive ne sont pas portés → la tuile choisie peut différer, mais
     le natif ne tire **rien** ;
   - PileIn passe par `Randomize` = `PickRandomAmountSelector(amount = int.MaxValue)` → **`len(pool)`
     tirages**, plus un `SortByFormula(If(HasTrait(0x1b), …))` non porté.
   Le tirage que le helper consomme à `len(pool) > 1` est donc faux dans les deux cas, et le corriger
   demande de porter les tris — cas à part entière.
5. **Le resolve slot-8 dans `execute_normal_like`.** `HitDamage.get_damage` court-circuite à
   `min == max` alors que `DamagePrediction$$RandomlyResolveMinMaxDamage` appelle `Next(v, v+1)` sans
   gate largeur-1. Mesuré : **1 tirage manquant par volet splash** sur le vecteur Psyker (montant plat).
   Le port ne matérialise ce resolve que dans la branche ability bounds-mode.
6. **Ordre de tirage hors consommateur d'attaque.** Pour les picks de **tuiles** (spawn de summons), le
   helper rend désormais l'ordre de tirage (fidèle au natif) au lieu de l'ordre trié. Comme l'ordre du
   pool du port est une approximation, la permutation obtenue n'est pas garantie identique à celle du
   natif — le SET, lui, reste identique quand `len(pool) <= n`.
