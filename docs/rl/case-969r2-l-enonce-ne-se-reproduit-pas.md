# #969-r2 — « le port vise la mauvaise cible » : l'énoncé ne se reproduit pas, et deux capteurs mentaient

**Verdict : ÉNONCÉ PÉRIMÉ.** Sur trois montages contrôlés, l'utilité et l'argmax de
`DeathFromAbovePlaybook` concordent avec le natif. Un étage réellement non porté a été trouvé
en chemin, par lecture du décompilé, et sort en résidu `#969-r4`.

## 1. Ce que l'énoncé affirmait

> `DeathFromAbovePlaybook` vise la MAUVAISE CIBLE : le natif caste `1003` sur `u77`, le port sur
> `u114`. Deux hypothèses non départagées : (a) `_spawn_tiles` sur-compte — `occupied` ne connaît
> que `epos`/`fpos`/l'origine ; (b) l'ordre de `fromHere` diverge.

Une précision de protocole ajoutait une troisième hypothèse — port et natif n'énumèrent pas les
mêmes cibles — et nommait l'oracle : `ncEvaluate`, qui rend par position `util`,
`action.targetLow` et `actionCount`.

## 2. La mesure — `probe_969r2_terme_divergent.py`

Board `MC1_67`, seed 777, caster `ultraInceptorSgt` @(3,4), trois cibles adjacentes
(`RANGE_ADJACENT` : le masque de `1003` ne porte pas plus loin). Positions **forcées**
(`--place` / `--a-place`) : la configuration ne se produit pas au spawn.

| montage | alliés placés     | comptes u87/u89/u85 | `util` natif | argmax port |
|---------|-------------------|---------------------|--------------|-------------|
| A       | (2,3) (4,5) (5,5) | 3 / 2 / **4**       | **4**        | u85         |
| B       | (2,3) (3,2) (2,2) | **4** / **4** / 2   | **4**        | u87 (égalité) |
| C       | (2,3) (3,2) (5,5) | **4** / 3 / 3       | **4**        | u87         |

A et C portent un **maximum unique** sur des cibles **différentes** — c'est ce qui interdit de
lire l'accord comme une coïncidence. B porte une égalité en tête : il ne juge pas l'argmax par
l'utilité, il garde le **tie-break keep-first** (`Bucket$$AddAction` remplace sur
`op_GreaterThan` STRICT).

**Aucune des deux hypothèses ne tient pour ce miss** :

- **(a) multi-hex** — `dv.units[].feet` est mesuré sur les 8 unités des trois montages :
  **aucune** n'a plus d'un pied. Le mécanisme reste réel (`#969-r3` : le natif décide
  l'occupation par `TileContentComponent$$IsEmpty`, donc PAR PIED, là où le port dérive
  `occupied` des main tiles) mais il n'est pas **déclenché** ici. L'étage E4 du probe recalcule
  le compte avec l'occupation dérivée de l'empreinte : **argmax inchangé** aux trois montages.
- **(b) ordre de `fromHere`** — le tie-break est exact, et le test le garde dans les deux sens
  (ordre natif → u87 ; ordre inversé → u89).

## 3. Deux capteurs qui mentaient — et c'est la vraie leçon

### 3.1 `actionCount` ne mesure PAS le cardinal des cibles

Le premier run du probe a rendu « cardinal port = 3, natif = 1 → **ENSEMBLE DIVERGENT** ». C'était
un **faux positif fabriqué par le probe lui-même**. `countActions`
(`frida/hooks/ai-toolkit/bucket-decode.ts`) somme le champ `best` de la racine et de chaque
sous-bucket :

```ts
let n = b.best ? 1 : 0;
for (const s of b.subBuckets) n += countActions(s.bucket);
```

Or `Bucket$$AddAction` **écrase** `best`, et `DeathFromAbovePlaybook` n'ouvre **aucun**
sous-bucket. Donc `actionCount` vaut **1 dès qu'une seule action est admise**, quel que soit le
nombre de cibles énumérées. Le cardinal natif n'est pas observable par ce champ ; le probe
l'affiche désormais comme contexte, avec la raison écrite au-dessus.

### 3.2 Un montage DÉGÉNÉRÉ rend un accord — et un désaccord — également vides

Le premier montage serré donnait des comptes 3/3/3. `util` natif = 3 : il ne **désigne** aucune
cible. Ni l'accord ni le désaccord n'y prouvent quoi que ce soit. Le probe le dit maintenant
(`DEGENERE`) au lieu de conclure, et il imprime le **voisinage natif** de chaque cible — ce qui
rend le montage pilotable vers un régime non dégénéré au lieu d'être deviné.

## 4. L'étage réellement non porté — résidu `#969-r4`

Lu au décompilé (`rnca9r7q6c`), `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable`
(surcharge `possibleCasterTile`, celle qu'appelle `EvaluateNonComparable` via
`UnitPosition$$get_MainTile`) :

```
var pos     = new UnitPosition(possibleCasterTile);
var targets = <slot 0x42 d'IAttackQuery>(caster, pos, this.<+0x10> = abilityType).<+0x10>;
ListExtensions.Remove(targets, new Predicate(this, <lambda>));     // <-- CET ETAGE
foreach (entity in targets) Add(result, AbilityEntities{ Caster, Target = entity, ... });
```

La lambda est `IdunBattle.AI.Playbook.BasePlaybook$$u003CGetEligibleTargetsEntitiesu003Eb__58_0` :

```c
return !this.<vtable slot 0x248>(t);        // Remove tout ce dont ShouldEvaluateTarget est FAUX
```

et le corps de base, `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluateTarget` :

```c
if (IsUnit(target) && CurrentOwnerIsEnvironment(target, state))  return false;
if (IsIrrelevantObject(target))                                   return false;
return true;
```

Le port n'a **aucun homologue** : `fromHere` est la sortie du slot, sans ce `Remove`. Le même trou
existe dans `engine/playbook/nonattack.py::eligible_targets`, dont la docstring **décrit** déjà ce
prédicat sans le porter. Dégradation **permissive**. Le slot `0x248` étant **virtuel**, un playbook
peut le surcharger — l'absence d'un `<X>Playbook$$ShouldEvaluateTarget` dans les tables ne prouve
rien (dédup ICF).

Il ne mord sur aucun des trois montages (aucune unité Environment ni IrrelevantObject en jeu),
donc il n'explique pas non plus l'écart annoncé. Substrat manquant : ni `CurrentOwnerIsEnvironment`
ni `IsIrrelevantObject` n'ont de canal publié par unité — le probe le sort en `NON MESURE`, jamais
en verdict fabriqué.

## 5. Ce qui reste vrai, et ce qui n'est pas couvert

- Le MISS observé sur les montages est **`natif ab=69` (attaque normale) contre `port ab=1003`** :
  un écart d'**arbitrage inter-ability**, pas de cible. `DeathFromAbovePlaybook$$ShouldEvaluate`
  finit par un **tirage RNG** (`this.<+0x30>.<slot 4>(prob)`) que le moteur déterministe ne
  modélise pas — écart déjà documenté et assumé.
- **Non couvert** : le régime MULTI-HEX. Le seul porteur multi-hex de la face DÉCISION est un
  **summon** (`ultraSmnDreadnought`, 3 hexes — une MoW, elle, est **hors plateau**,
  `decisionView.mows[].pos is null`, donc elle n'occupe rien chez personne). Le confronter
  demande d'amener ce summon en bataille ; c'est le périmètre de `#969-r3`, pas de celui-ci.
- **Non couvert** : les autres canaux d'occupation du natif que `can_add_unit` ne porte pas —
  `IsTileReservedForOtherUnit`, `IsTilePendingDrafting`, `TileComponent+0x2c` (réservé), et la
  co-location par trait `0x1b`. Aucun ne mord sur un duel simple.

## 6. Garde

`scripts/python/tests/engine/playbook/test_969r2_death_from_above_utility_offline.py` — 14 tests,
offline pur. Le voisinage natif des trois cibles y est **dérivé des mesures live** (union des
voisins libres des trois montages + tuiles occupées en permanence = exactement six voisins par
cible), et les comptes attendus sont les valeurs **relevées live**, pas des valeurs recalculées.

Vue ROUGE par deux mutations adversariales :

| mutation                                          | rouges |
|---------------------------------------------------|--------|
| tie-break `>` → `>=`                               | 2      |
| `occupied` ampute des alliés (`fpos` retiré)       | 9      |

Message verbatim (mutation 1) :

```
AssertionError: ordre inverse : cible retenue 87 au lieu de 89 (la premiere enumeree a egalite)
```
