# #10022 — L'etage `UnitPicker` : QUI JOUE ENSUITE (INVENTAIRE)

Build `t6dpr4k06g`. **Livrable = l'INVENTAIRE. Aucun port dans cette tranche** — la mesure ci-dessous
etablit que la colonne vertebrale ne tient pas dans une tranche, et §8 le chiffre.

---

## 0. Deux premisses du cadrage sont FAUSSES, et il faut les corriger avant tout

### 0.1 `decisionView.toActivate` n'est PAS l'ordre choisi par le natif

Le brief le presente comme « l'ordre qu'il a choisi », donc comme un oracle direct. **Mesure** :
`frida/hooks/features/ai-step/internals.ts` (`toActivateSquads`) et
`frida/hooks/features/ai-step/rpc-decision.ts` construisent ce champ ainsi :

```
forEachEntity(statePtr, ...) : ty == Unit && IsControlledByCurrent && IsAlive && HasActionLeft
```

C'est **l'ENSEMBLE des unites activables du joueur courant, dans l'ordre d'iteration du conteneur
d'entites de l'ECS**. Ce n'est pas une sortie de `PickNextUnit` — c'est, a une condition pres, son
**ENTREE** (`IdunBattle.AI.OperationalDeciders.AnAiGroupOperator$$GetValidUnits`, cf. §2.3).

Le court-circuit est donc **PIRE** que ce que le brief redoutait : comparer un port de `PickNextUnit`
a `toActivate` ne compare pas « le natif a lui-meme », ca compare un **ordre de decision** a un
**ordre d'iteration ECS**, qui ne porte aucune information d'ordonnancement. Une garde batie
dessus serait fausse dans les deux sens.

⚠ Corollaire pour la doctrine : `engine/playbook/noncomparable/storm_speeder.py` ecrit que l'etage
`UnitPicker` est « **que le natif nous fournit deja (`toActivate`)** ». C'est **FAUX**. Le natif ne
nous fournit pas l'ordre ; il nous fournit l'ensemble des candidats. Corrige dans le meme commit.

### 0.2 `PickUnitOperation` / `OperationProcessor$$PickUnit` n'ont AUCUN rapport avec l'ordonnancement

Point declare « non verifie » par le brief, **tranche** :
`IdunBattle.Operations.PickUnitOperation$$Execute` lit `DraftingComponent`
(`get_IsPendingDraftingDecision`, `RegisterUnitDrafted`, `ClearPendingDrafting`) et delegue a
`IdunBattle.Operations.PickUnitOperation$$ExecuteStandardDraft` /
`IdunBattle.Operations.PickUnitOperation$$ExecuteResurrectDraft`. C'est le **DRAFT** (choix d'une
unite a deployer), pas le choix de l'unite qui joue.
`Core.Services.OperationProcessor$$PickUnit` n'est qu'un forwarder d'une ligne vers lui.

**A ecarter du perimetre `UnitPicker`.**

---

## 1. Le decideur en bataille : lequel des deux `PickNextUnit` ?

`IdunBattle.Core.Services.AiControl$$Init` construit **cinq** strategies et
`IdunBattle.Core.Services.AiControl$$GetAi(playerEntityId)` en choisit une, LU verbatim :

| `PlayerComponent.<+0x20>` | `AiControl.<+0x70>` (`configurationRandomizeAiInput`) | strategie |
|---|---|---|
| `2` | — | `IdunBattle.AI.EnvironmentPlayerStrategy` (`+0x30`) |
| `4` | faux / vrai | `DefaultPlayerStrategy` humanAi (`+0x28`) / `WithSomeRandomnessStrategy` humanAi (`+0x68`) |
| autre | faux / vrai | `DefaultPlayerStrategy` (`+0x20`) / `WithSomeRandomnessStrategy` (`+0x60`) |

- `IdunBattle.AI.DefaultPlayerStrategy$$.ctor` -> `IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$.ctor`
  -> **l'etage `UnitPicker`** (8 buckets d'utilite, §3).
- `IdunBattle.AI.WithSomeRandomnessStrategy$$.ctor` -> `IdunBattle.AI.OperationalDeciders.RandomGroupOperation$$.ctor`,
  dont `IdunBattle.AI.OperationalDeciders.RandomGroupOperation.u003CPickNextUnitu003Ed__7$$MoveNext`
  fait `validUnits[random.<iface slot 1>(validUnits.Count)]` — **tirage uniforme, AUCUNE utilite**.

⚠ **HYPOTHESE NON TRANCHEE** : la valeur de `configurationRandomizeAiInput` en bataille ordinaire.
Elle arrive en argument d'`AiControl$$Init`, dont aucun appelant direct n'est resolu (appel
d'interface). Tant qu'elle n'est pas mesuree, **on ne sait pas si l'etage `UnitPicker` est meme
ACTIF** en bataille ordinaire. C'est la premiere chose a etablir avant tout port -> residu
**#10022-r1**. Elle se lit en live (`AiControl` instance, champ `+0x70`) ou par la chaine de
configuration.

---

## 2. La colonne vertebrale, lue de bout en bout

### 2.1 La boucle d'activation

`IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$CalculateNextActionForPlayer(player)` :
`GetEntitiesFromIds(PlayerComponent.get_CurrentlyOwnedUnitIds())`, puis appel VIRTUEL du slot
`+0x1a8` = `CalculateNextActionForUnitGroup(units)`.

`IdunBattle.AI.OperationalDeciders.DefaultGroupOperator.u003CCalculateNextActionForUnitGroupu003Ed__6$$MoveNext`,
remis en C# :

```csharp
var e = PickNextUnit(units);
while (e.MoveNext()) yield return null;        // « en steps »
var u = e.Current;                             // LA valeur, apres MoveNext() == false
if (u == null || u.IsDead(state)) { yield return new List<IInputMessage>(); yield break; }
u.GetBaseUnitComponent().<+0x60> += 1;         // compteur d'activations IA
aiLogger.<slot 4>(new AIActions(u, DateTime.Now, GetCurrentTeamId(u) != 1));
var tactic = GetUnitTactic(u);                 // state.<+0x20>
foreach (var msgs in tactic.CalculateNextActionForUnit(u)) yield return msgs;
```

⚠ **Le pattern « en steps » est le piege central de tout ce chantier**, et il vaut pour les DIX
utilites comme pour les trois enumerateurs de l'etage : un iterateur yield `null` tant qu'il
travaille, et **sa valeur est dans `Current` APRES que `MoveNext()` a rendu `false`** (la state
machine Roslyn ne remet pas `<>2__current` a zero au `yield break`). Lire la methode nommee
`$$EvaluateUnitInSteps` ne montre que l'allocation de la machine a etats ; le corps est dans
`u003CEvaluateUnitInStepsu003Ed__N$$MoveNext`.

### 2.2 `PickNextUnit`

`IdunBattle.AI.OperationalDeciders.DefaultGroupOperator.u003CPickNextUnitu003Ed__7$$MoveNext` :

```csharp
if (state.GetMatch().<+0x24> == 2) { yield return null; yield break; }   // match termine
var valid = GetValidUnits(inputUnits);
var e = _utilityDecider.Decide(valid, _pickUnitDefinition);   // iface slot 1, this.<+0x28>/<+0x30>
while (e.MoveNext()) yield return null;
yield return e.Current;                                        // L'UNITE choisie, ou null
```

Signature LUE (`frida/methods.tsv`) :
`PickNextUnit(inputUnits: IList<IEntity>) -> IEnumerator<IEntity>`.
⚠ **`PickNextUnit` rend UNE unite, pas un ordre.** L'ordre d'activation EMERGE de la boucle §2.1,
chaque tour re-filtrant par `HasActionLeft`.

### 2.3 `GetValidUnits` — le filtre d'entree

`IdunBattle.AI.OperationalDeciders.AnAiGroupOperator$$GetValidUnits(inputUnits)` :

```csharp
var res = new List<IEntity>();
foreach (var u in inputUnits)
    if (u.HasActionLeft() && !u.IsDead(state))
        if (u.GetBaseUnitComponent().<+0x60> < 0x3e9) res.Add(u);   // 1001
        else logger.Warn(...);                                       // et l'unite est EXCLUE
return res;
```

Les deux premieres conditions sont exactement celles de `toActivate` (§0.1). La troisieme est un
garde anti-boucle-infinie sur le compteur incremente en §2.1. Le port en a deja le mirror :
`engine/runner/operations/summon_ai.py::ai_control_execute_for_group` (`MAX_AI_ACTIONS_PER_UNIT`).

---

## 3. L'etage d'arbitrage : `UtilityDecider` — un TRI LEXICOGRAPHIQUE PAR BUCKETS

C'est le coeur, et il est **entierement porte-able offline** (aucun etat natif hors les utilites).

### 3.1 `DecideEnumerator<T>`

`IdunBattleLogic.AI.Utilities.UtilityDecider.u003CDecideEnumeratoru003Ed__6u003Cobjectu003E$$MoveNext` :

```csharp
var scores = new Fix64[cases.Count];
foreach (var c in cases) scores[k++] = Fix64.Zero;
foreach (var bucket in definition.Buckets) {           // DANS L'ORDRE
    var r = <dernier Current de> CalculateUtilitiesForCasesEnumerated(db, cases, bucket, scores, evaluate);
    if (r.first != null && r.second == null) { yield return r.first; yield break; }   // DECIDE
}
yield return <le dernier r.first>;                     // buckets epuises sans departage
```

⚠ **`scores` est PARTAGE entre les buckets** : chaque bucket ACCUMULE dessus, et une elimination
posee par un bucket vaut pour tous les suivants. Ce n'est donc pas « N tris independants ».

### 3.2 `CalculateUtilitiesForCasesEnumerated` — le corps qui decide

`IdunBattleLogic.AI.Utilities.UtilityDecider.u003CCalculateUtilitiesForCasesEnumeratedu003Ed__7u003Cobjectu003E$$MoveNext` :

```csharp
IEntity best = null, second = null;
Fix64 bestScore = BaseUtility.<statics+0x20>, secondScore = BaseUtility.<statics+0x20>;   // MinValue
var vetoed = new bool[cases.Count];
int i = -1;
foreach (var c in cases) {
    yield return null; i++;
    if (scores[i] == BaseUtility.<statics+0x20>) continue;          // deja elimine -> JAMAIS reevalue
    var r = <dernier Current de> CalculateUtilityInSteps(db, c, bucket, evaluate);
    if      (r == BaseUtility.<statics+0x10>) { best = c; bestScore = <statics+0x10>;
                                                second = null; secondScore = <statics+0x20>; break; }
    else if (r == BaseUtility.<statics+0x18>) { /* RIEN : hors course pour CE bucket */ }
    else if (r == BaseUtility.<statics+0x20>) { scores[i] = BaseUtility.<statics+0x20>; }
    else if (r == BaseUtility.<statics+0x28>) { vetoed[i] = true; }
    else {
        var total = scores[i] + r;  scores[i] = total;
        if      (total > bestScore)   { second = best; secondScore = bestScore; best = c; bestScore = total; }
        else if (total > secondScore) { second = c; secondScore = total; }
    }
}
if (best != null) for (j) if (vetoed[j]) scores[j] = BaseUtility.<statics+0x20>;
if (bestScore - secondScore > bucket.minUtilityDifference) second = null;
if (bucket.<+0x18> && best != null) {
    for (j) if (scores[j] < bestScore) scores[<index>] = BaseUtility.<statics+0x20>;
    if (second != null && secondScore < bestScore) second = null;
}
yield return new { first = best, second = second };
```

### 3.3 Les CINQ valeurs de `BaseUtility`, et ce qu'elles FONT

`IdunBattle.AI.Utilities.BaseUtility$$.cctor` + `FixMath.NET.Fix64$$.cctor`, LUS :

| champ | valeur | role dans §3.2 |
|---|---|---|
| `statics+0x00` | `Fix64(0)` | **NEUTRE** — concourt avec un score nul |
| `statics+0x08` | `Fix64(100000)` | (pas de sentinelle : passe par la branche NORMAL) |
| `statics+0x10` | `Fix64.MaxValue` | **MUST-DO** — `best`, et **arret immediat** du bucket |
| `statics+0x18` | `Fix64.MinValue / (1000001/1000000)` | **HORS COURSE pour ce bucket** — score inchange, jamais `best`/`second` |
| `statics+0x20` | `Fix64.MinValue` | **VETO FERME** — `scores[i] = MinValue`, elimine pour TOUS les buckets suivants |
| `statics+0x28` | `Fix64.MinValue / (1000002/1000000)` | **VETO CONDITIONNEL** — elimine **seulement si un `best` a emerge dans ce bucket** |
| `statics+0x30` | `Fix64(-12345)` | valeur de **pas** des iterateurs « en steps » (jamais le dernier `Current`) |

`FixMath.NET.Fix64.statics` : `+0x10 = 0x7fffffffffffffff` (MaxValue), `+0x18 = 0x8000000000000000`
(MinValue), `+0x20 = 0x100000000` (One), `+0x28 = 0` (**Zero**).

⚠ **La distinction `+0x18` (hors course) / `+0x20` (veto ferme) n'est pas cosmetique — c'est ce qui
fait fonctionner le jeu.** Elle est etablie DEUX fois, independamment :
1. **par l'indentation du decompile** : le test `statics+0x18` n'a PAS de branche `else`, celui de
   `statics+0x20` en a une (`scores[i] = statics+0x20`) ;
2. **par reduction a l'absurde** : `PreferAbilitiesUtility` rend `statics+0x18` pour **toute**
   unite dans ce build (§4.5, tableau statique VIDE). Si `+0x18` eliminait, ce bucket (position 5)
   mettrait **tous** les scores a `MinValue`, les buckets 6 et 7 sauteraient tout le monde, et
   `PickNextUnit` rendrait **`null`** — donc `CalculateNextActionForUnitGroup` rendrait une liste
   vide et **aucune unite IA ne jouerait jamais** des que les 4 premiers buckets ne departagent pas.
   Le jeu tourne : `+0x18` ne peut pas eliminer.

⚠ **UNE INCERTITUDE DECLAREE, a re-lire au DESASSEMBLAGE avant tout port** : dans la boucle du flag
`bucket.<+0x18>`, Ghidra lit `scores[uVar12]` (indice de boucle) mais **ECRIT** a
`scores[*(uint*)(param_1 + 0x70)]` (l'indice du DERNIER case traite). C'est asymetrique avec la
boucle `vetoed` juste au-dessus, qui lit et ecrit au meme indice — donc probablement une mauvaise
reconstruction de registre, mais **ce n'est pas etabli**. Ne pas porter cette boucle sans avoir
tranche.

### 3.4 `CalculateUtilityInSteps` — deja porte, et fidele

`IdunBattleLogic.AI.Utilities.UtilityDecider.u003CCalculateUtilityInStepsu003Ed__9u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`
confirme mot pour mot ce que `engine/utilities/decider.py::calculate_utility` documente deja :
somme ponderee `Sigma weight_i * evaluate(case, u_i)`, `r == null -> 0`, et **les 4 sentinelles
court-circuitent le bucket entier** (ordre des tests : `+0x20`, `+0x28`, `+0x18`, `+0x10`).

⚠ **Le port ne modelise PAS les sentinelles** (`decider.py` le dit : « aucune des utilites portees
n'en rend une »). Pour l'etage `UnitPicker`, **les DIX en rendent** — c'est donc ici, dans
`engine/utilities/decider.py`, que le premier morceau de (B) doit atterrir.

---

## 4. La definition d'utilite de `PickNextUnit` : HUIT buckets, dans CET ordre

`IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$.ctor` alloue `new UtilityBucket[8]` et le
remplit element par element. Signature LUE : `UtilityBucket..ctor(utilityType, minUtilityDifference)`
— le 2e argument est bien la **difference minimale**, pas un poids.

| # | `UtilityType` | `minUtilityDifference` | flag `+0x18` |
|---|---|---|---|
| 0 | `PreferSummons` (75) | **1** | non |
| 1 | `PreferNonBoss` (69) | **1** | non |
| 2 | `PreferFreshlySpawned` (70) | **1** | non |
| 3 | `UnitOrder` (77) | 0 (`null`) | **OUI** |
| 4 | `LastAbilities` (76) | 0 (`null`) | non |
| 5 | `PreferAbilities` (74) | 0 (`null`) | non |
| 6 | `UnitWithShortestPathToEnemy` (72) | 0 (`null`) | non |
| 7 | `Remaining` (73) | 0 (`null`) | non |

Le `minUtilityDifference = 1` des trois premiers est ce qui fait que **deux summons ex-aequo ne sont
pas departages par leur propre bucket** (`diff = 0`, `0 > 1` faux -> `second` survit -> bucket
suivant), alors que le seul summon d'un groupe l'est immediatement.

⚠ **`MinPossibleNormalAttackTarget` (71) et `Random` (78) NE SONT DANS AUCUN BUCKET.** Verifie par
les xrefs des **trois** surcharges de `UtilityBucket$$.ctor` et des **trois** de
`UtilityDefinition$$.ctor` : les seuls call-sites sont `DefaultGroupOperator$$.ctor` (les 8
ci-dessus), `BioMinefieldAbility$$.ctor`, `DevoutPushAbility$$.ctor`, `DSLSelectors$$SortTilesByUtility`
et consorts (tuiles/attaques, pas unites). Elles sont **enregistrees** dans `UtilitiesDatabase`
(`u003CInitializeUtilitiesu003Eb__18_31` pour la premiere) et **jamais demandees** -> **DEAD CODE
dans ce build**.

---

## 5. INVENTAIRE DES DIX UTILITES

Toutes heritent d'`IdunBattle.AI.Utilities.BaseUtility` (taille 96) ; leur `$$.ctor` est trivial
(`BaseUtility..ctor`), leurs dependances viennent de
`IdunBattle.AI.Utilities.BaseUtility$$Init(state, query, config, dsl, pathfinders, random, logger,
logSpamFilter, playbookDatabase, abilityAndEffectCache)` — champs `+0x10 state`, `+0x18 dsl`,
`+0x20 query`, `+0x28 pathfinders`, `+0x30 random`, `+0x48 playbookDatabase`, `+0x58 config`.

| # | Utilite | Ce qu'elle score | Entrees | Substrat publie ? | Confrontable ? | Cout de port |
|---|---|---|---|---|---|---|
| 1 | `RemainingUtility` (73) | **constante `Fix64(0)`** | aucune | s/o | oui | **trivial** |
| 2 | `PreferNonBossUtility` (69) | `IsBoss ? VETO_COND : 0` | `UnitExtensions$$IsBoss` | oui (`is_boss` porte) | oui | **trivial** |
| 3 | `PreferSummonsAndObjectsUtility` (75) | `HasTrait(Summon\|Object) ? 0 : VETO_COND` | traits `2`/`13` | oui (`has_trait` porte) | oui | **trivial** |
| 4 | `PreferFreshlySpawnedUtility` (70) | `BaseUnitComponent.<+0x58> != 0 ? VETO_COND : 0` | champ `+0x58` | **NON — champ non identifie** | non | **BLOQUE** |
| 5 | `PreferAbilitiesUtility` (74) | **constante `HORS_COURSE`** (tableau statique VIDE) | — | s/o | oui | **trivial** |
| 6 | `LastAbilitiesUtility` (76) | `HasTriggeredAbility(RealityUnbound) ? HORS_COURSE : <rien>` | `TriggeredAbilityType.RealityUnbound` (1174) | oui | porteur a trouver | **faible** |
| 7 | `UnitWithShortestPathToEnemyUtility` (72) | `-min(longueur de chemin vers un ennemi)`, ou `HORS_COURSE` | pathfinders, `GetAllEnemyUnitsOfUnit`, `GetMainTile` | oui (pathfinding porte) | oui | **LOURD** |
| 8 | `UnitOrderUtility` (77) | somme de poids de config + `playbook.GetCustomUnitOrderUtility` | `aiUtilities.Default.UnitOrder`, abilities, traits, `PlaybookDatabase` | oui (§6) | oui | **LOURD** |
| 9 | `MinPossibleNormalAttackTargetUtility` (71) | `-count(cibles possibles)`, `MUST_DO`, `HORS_COURSE`, `0` | `GetOnlyTargets`, `GetNormalAttackType`, requete de cibles | oui | **DEAD** (aucun bucket) | s/o |
| 10 | `RandomUtility` (78) | `Fix64(random.<slot 2>(-1, 1))` | `IPseudoRNG` | oui | **DEAD** (aucun bucket) | s/o |

### Detail des non-triviales

**`UnitOrderUtility` (77)** — `IdunBattleLogic.AI.Utilities.UnitPicker.UnitOrderUtility$$Priority(unit)`,
appele directement par le `MoveNext` (un seul `yield return`) :

```csharp
Fix64 x = Fix64.Zero;                                                  // Fix64.statics+0x28
var id = UnitNamingConventions.GetUnitIdWithoutRarity(unit.GetUnitId());
if (HasUtilityValue(id)) x += GetUtilityValue(id);
// (a) ACTIVE abilities
foreach (var ab in unit.Get<ActiveAbilityComponent>().<+0x20>) {
    var name = ((ActiveAbilityType)ab.<+0x44>).ToString();
    if (HasUtilityValue(name)) x += GetUtilityValue(name);
    var pb = _playbookDatabase.LoadPlaybook(ab.<+0x44>, null);
    if (pb != null) x += pb.<vtable slot 8>(unit);                     // GetCustomUnitOrderUtility
}
// (b) TRIGGERED abilities
foreach (var t in unit.Get<TriggeredAbilityComponent>().<+0x18>) { ... GetUtilityValue(<enum>.ToString()) ... }
// (c) TRAITS, si unit.IsUnit()
foreach (var tr in unit.Get<...>().<+0x40>) { ... GetUtilityValue(<enum>.ToString()) ... }
return x;
```

`IdunBattle.AI.Utilities.BaseUtility$$GetUtilityValue(name)` = `config.TryGetValue(name, out int v)
? Fix64(v) : Fix64(0)` (+ un warning journalise sur absence) ; `HasUtilityValue` = `ContainsKey`.

⚠ **Le slot 8 est bien `GetCustomUnitOrderUtility`** : `IdunBattle.AI.Playbook.BasePlaybook$$GetCustomUnitOrderUtility`
rend `Fix64(0)`, et **deux** surcharges existent dans la table —
`IdunBattle.AI.Playbook.Loki.DeathOnTheWindPlaybook$$GetCustomUnitOrderUtility`
(`vtable[+0x1a8](this, unit) ? -99 : 0`) et
`IdunBattle.AI.Playbook.Loki.TitanhammerSquadPlaybook$$GetCustomUnitOrderUtility`
(`(count + 1) * GetUtilityValue(<cle>)`). **Ce compte de 2 ne prouve rien** (cf. `case-170` :
IL2CPP deduplique les corps triviaux) — toute surcharge rendant `Fix64(0)` serait invisible.
Le port doit donc balayer les playbooks par le **slot de vtable sur l'instance**, pas par la table.
Ceci ferme la question ouverte du brief : **`UnitOrderUtility$$Priority` participe bien a
l'ORDONNANCEMENT** (c'est le corps entier de son `EvaluateUnitInSteps`), pas au choix d'ability.

**`UnitWithShortestPathToEnemyUtility` (72)** —
`IdunBattleLogic.AI.Utilities.UnitPicker.ShortestPathToEnemyUtility.u003CEvaluateUnitInStepsu003Ed__0$$MoveNext` :

```csharp
var dc = new <>c__DisplayClass0_0 { <>4__this = this, unitTile = unit.GetMainTile(state) };
int? minSteps = null;
foreach (var target in Enumerable.OrderBy(state.GetAllEnemyUnitsOfUnit(unit), dc.<EvaluateUnitInSteps>b__0)) {
    yield return BaseUtility.<statics+0x30>;                    // pas de travail (-12345)
    var targetTile = target.GetMainTile(state);
    if (minSteps.HasValue && minSteps.Value <= <distance approx>(unitTile, targetTile)) continue;
    var path = _pathfinders.<slot +4>(1, unit, unitTile, targetTile);
    if (path != null) {
        if (minSteps.HasValue && path.Count >= minSteps.Value) continue;
        minSteps = path.Count;
        if (minSteps.Value == 1) break;
    }
}
yield return minSteps.HasValue ? Fix64(-minSteps.Value) : BaseUtility.<statics+0x18>;
```

Le comparateur du `OrderBy` est `<>c__DisplayClass0_0.<EvaluateUnitInSteps>b__0(target) -> Int32`
(signature LUE) : une distance, qui sert **uniquement** a l'ordre de visite et a l'elagage.

**`MinPossibleNormalAttackTargetUtility` (71), DEAD** — pour memoire :
`IsBoss -> Fix64(0)` ; `!IsNullOrEmpty(GetOnlyTargets(unit)) -> MUST_DO` ; sinon, requete des
cibles de l'attaque normale (`GetNormalAttackType`, iface slot `+0x46`), `yield HORS_COURSE` en
steps, puis `count == 0 -> HORS_COURSE`, `count == 1 -> MUST_DO`, sinon `Fix64(-count)`.

---

## 6. Le SUBSTRAT est publie, et il est MINCE

`data/symbols/t6dpr4k06g/gameconfig.json` -> `clientGameConfig.aiUtilities` porte **2 collections**
(`Default`, `MovementSuggestion`) — ce qui nomme l'argument `utilityCollectionType` de
`IdunBattle.Core.Services.UtilitiesDatabase$$GetUtilityConfig` (`0` = `Default`, et le fallback
natif re-interroge `Default` quand la collection specifique n'a rien).

`aiUtilities.Default` compte **54** entrees. Sur les 10 utilites de `UnitPicker`, **UNE SEULE** y
figure :

```
UnitOrder = { Psyker: 1, WeaverOfFate: -2, SorcerousFacade: 2, MasterOfTheTutelaries: 2,
              Doombolt: 1, MasterAnnihilator: 1, CordClaw: 1, BloodChalice: 1,
              Hailstrike: 10, VoltagheistField: -2 }
```

Neuf clefs d'ability + `Psyker` (un `UnitTrait`) — exactement les trois voies (a)/(b)/(c) de
`UnitOrderUtility$$Priority`. Les neuf autres utilites n'ont **aucune** entree, ce qui est
coherent : aucune ne lit la config.

⚠ Consequence directe pour (B) : **`UnitOrder` ne departage que 10 noms sur tout le jeu**. Sur un
groupe d'unites ordinaires il rend `0` partout, donc n'eliminera personne malgre son flag de cut,
et le departage retombe sur le bucket 6, `UnitWithShortestPathToEnemy`.

---

## 7. Confrontabilite — l'oracle REEL

`toActivate` est ecarte (§0.1). Deux oracles restent, tous deux **deja outilles** :

1. **`PerformAIAction(asGroup: true)`** — `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour`
   confie son groupe au `DefaultGroupOperator`, qui **boucle `PickNextUnit`**. Le port a deja le
   consommateur : `engine/runner/operations/summon_ai.py::ai_control_execute_for_group`, dont le
   commentaire de residu ecrit noir sur blanc « **l'ORDRE rendu par le picker natif est un argmax
   d'UTILITE ; le port garde l'ORDRE DU SELECTEUR** » et rapporte l'observation live « les 2 gardes
   agissent dans l'ordre INVERSE de leur spawn ». **C'est l'oracle : la sequence d'unites dans les
   events du cast.**
2. **Le tour IA complet** (`aiturn`) : la sequence d'unites qui agissent, lue dans les events.

⚠ **La garde anti-court-circuit se specifie ainsi, et elle doit etre vue ROUGE avant le fix** :
le port calcule l'ordre a partir de l'ETAT SEUL (positions, traits, abilities, board) et on le
confronte a la sequence OBSERVEE. Le montage doit **assertionner qu'aucune entree du port ne
provient de `toActivate` ni d'un champ de `decisionView` derive d'une decision native** —
concretement : la fixture ne passe au port que le `State` reconstruit, et le test echoue si la
sequence attendue est **egale a l'ordre d'iteration ECS** (regime degenere : dans ce cas la
comparaison ne prouve rien, il faut DEPLACER les unites pour que l'ordre du picker et l'ordre ECS
divergent). Sans cette seconde assertion, la garde est verte par construction — c'est exactement
la forme d'accord en regime degenere.

⚠ Rappel : **un summon n'entre jamais dans `toActivate`** et le natif termine son tour a
l'apparition (#291). Une absence n'est donc pas une divergence d'ordre.

---

## 8. Pourquoi (B) N'EST PAS atteignable dans cette tranche — le chiffre

Le cas motivant (`SupremeCommander`, deux gardes clones) traverse les buckets ainsi :

| bucket | resultat sur 2 gardes clones | departage ? |
|---|---|---|
| 0 `PreferSummons` | tous deux `Summon` -> `0` | non (`diff 0 > 1` faux) |
| 1 `PreferNonBoss` | tous deux non-boss -> `0` | non |
| 2 `PreferFreshlySpawned` | identique -> `0` ou `VETO_COND` des deux cotes | non |
| 3 `UnitOrder` | aucune clef de config -> `0` des deux cotes | non (`diff 0 > 0` faux ; le cut n'elimine personne) |
| 4 `LastAbilities` | pas `RealityUnbound` -> `null` -> `0` | non |
| 5 `PreferAbilities` | `HORS_COURSE` des deux cotes -> `best = null` | non |
| **6 `UnitWithShortestPathToEnemy`** | `-minSteps`, **DIFFERENT** selon la position | **OUI** |
| 7 `Remaining` | `0` | — |

⇒ **Sur le seul regime confrontable aujourd'hui, c'est la plus LOURDE des dix qui decide.** Porter
la colonne vertebrale sans `UnitWithShortestPathToEnemy` produirait un port qui rend
systematiquement le premier candidat — donc **exactement le comportement actuel du port**
(`valid[0]`), avec en plus l'illusion d'un etage. Et le valider serait un accord en regime
degenere de plus.

La tranche minimale qui CHANGE un resultat observable est donc :
`decider.py` (sentinelles + `decide` + `calculate_utilities_for_cases`, ~150 lignes de mirror avec
une incertitude declaree en §3.3) **+** les 5 utilites triviales **+**
`UnitWithShortestPathToEnemy` (pathfinding, tri, deux elagages) **+** le cablage de
`ai_control_execute_for_group` **+** le montage de garde de §7. Plus la reponse a #10022-r1 (§1),
sans laquelle on ne sait meme pas si l'etage est actif.

**C'est plusieurs tranches. Rendu en inventaire, decoupe en §9.**

---

## 9. Residus ouverts

| # | Objet | Pourquoi separe |
|---|---|---|
| **#10022-r1** | Mesurer `configurationRandomizeAiInput` (`AiControl.<+0x70>`) en bataille ordinaire | **PREALABLE A TOUT** : si vrai, c'est `RandomGroupOperation` (tirage uniforme) qui decide et tout l'etage `UnitPicker` est inerte |
| **#10022-r2** | Porter l'etage d'arbitrage `UtilityDecider` (les 4 sentinelles dans `calculate_utility`, `decide`, `calculate_utilities_for_cases`, `UtilityBucket.<+0x18>`) + les 5 utilites triviales (`Remaining`, `PreferNonBoss`, `PreferSummonsAndObjects`, `PreferAbilities`, `LastAbilities`) | Le coeur. Inclut la levee de l'incertitude §3.3 au desassemblage |
| **#10022-r3** | Porter `UnitWithShortestPathToEnemyUtility` (72) | Le seul departage effectif du regime confrontable (§8) ; pathfinding + `OrderBy` + 2 elagages |
| **#10022-r4** | Porter `UnitOrderUtility` (77) + `Priority` + `GetCustomUnitOrderUtility` par slot de vtable | Ferme aussi `#967-r1` ; exige le balayage par slot, pas par table (`case-170`) |
| **#10022-r5** | Identifier `BaseUnitComponent.<+0x58>` puis porter `PreferFreshlySpawnedUtility` (70) | Bloque : le champ n'a aucun accesseur nomme (`GetTurnsFinished` lit son voisin `+0x5c`) |

`MinPossibleNormalAttackTargetUtility` (71) et `RandomUtility` (78) **ne recoivent pas de residu** :
DEAD CODE mesure (§4). Les rouvrir exigerait qu'un bucket les demande, ce qu'aucun ne fait.

---

## 10. Ce qui N'EST PAS couvert par cette tranche

- La valeur de `configurationRandomizeAiInput` (#10022-r1) — donc **l'ACTIVITE de tout l'etage**.
- Le nom de `BaseUnitComponent.<+0x58>` (#10022-r5).
- L'indice ecrit par la boucle du flag `bucket.<+0x18>` (§3.3) — lu en decompile, pas au
  desassemblage.
- `IdunBattle.AI.EnvironmentPlayerStrategy` et `IdunBattle.AI.OperationalDeciders.EnvironmentGroupOperator`
  (le joueur `2`), hors perimetre.
- Le second `utilityCollectionType` (`MovementSuggestion`, 1 entree) : hors `UnitPicker`.
- Aucune confrontation live n'a ete jouee : cette tranche est **100 % offline** (decompile +
  tables versionnees + gameconfig).
