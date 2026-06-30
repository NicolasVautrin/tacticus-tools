# Architecture de l'IA playbook (vue d'ensemble + spine décisionnel)

> But : carte fidèle de l'IA native de Tacticus (build gqfc5mff6c) — comment une équipe
> choisit *quelle unité* active *quelle action*, et comment cette architecture se réimplémente
> de façon **modifiable** en Python. Le détail du calcul de score est dans `scoring.md`, les
> prédictions dans `prediction.md`, le déplacement dans `pathfinding.md`, les feuilles par-ability
> dans `playbooks.md`, l'état d'avancement dans `status.md`.

## 1. Les deux étages

L'IA = **maximisation d'utilité par buckets**, PAS 200 algorithmes indépendants. Deux étages :

1. **Étage scorer — `Utilities`** (somme pondérée). Au-dessus : une devise unifiée. Chaque action
   candidate reçoit une utilité Fix64 = somme pondérée de prédictions (dégât/soin/effet/repair) +
   utilités de position/tuile, poids tirés de `BattleConfiguration.Utilities` (config NOMMÉ, déjà
   dans les archives JSON, profils `Default` et `MovementSuggestion`). Cœur =
   `ComparablePlaybook.CalculateActionUtility`. Détail des termes et poids → `scoring.md`.
2. **Étage playbooks par-ability** (1 classe/ability, registre ~351 entrées). En dessous : chaque
   ability possède sa `Playbook` qui (a) énumère ses candidats (cibles/tuiles éligibles) et
   (b) leur attribue un score. La majorité héritent du comportement de base ; seuls quelques deltas
   par feuille. Détail des feuilles → `playbooks.md`.

## 2. Le spine décisionnel (complet)

```
while valid_units:                              # PickNextUnit — ordonnancement des unités
    unit = next ordered valid unit
    cands = []
    for ability in unit.abilities:              # 1 playbook / ability
        cands += playbook_for(ability).evaluate(unit, pos)   # remplit un BUCKET de candidats
    action = choose_action(cands, ctx)          # argmax-utilité parmi les actions LÉGALES
    apply(action)
```

### 2.1 `PickNextUnit` — choix de l'unité à activer

`OperationalDeciders.DefaultGroupOperator` itère les unités valides (vivantes + contrôlées + action
restante, `GetValidUnits`) selon une `order_strategy` (vtable idx 1 sur `operator.0x28`).

L'ordonnancement authoritative est un **décideur à 8 buckets à seuils**, construit EN ORDRE par
`DefaultGroupOperator..ctor` (@181183dc0) via le ctor `UtilityBucket(UtilityType, Nullable<Fix64>
minUtilityDifference)` (@180e432b0) :

| # | UtilityType | MinUtilityDifference | flag |
|---|---|---|---|
| 1 | PreferSummons(74) | **1** | |
| 2 | PreferNonBoss(68) | **1** | |
| 3 | PreferFreshlySpawned(69) | **1** | |
| 4 | UnitOrder(76) | — | **RejectAllNoneBestCases=true** |
| 5 | LastAbilities(75) | — | |
| 6 | PreferAbilities(73) | — | |
| 7 | UnitWithShortestPathToEnemy(71) | — | |
| 8 | Remaining(72) | — | |

Priorité : summons → non-boss → fraîchement-spawn (chacun gate `util≥1`) → UnitOrder (garde le
meilleur) → … → reste. Le seuil `minUtilityDifference` est porté par la config
`IdunBattleLogic.AI.Utilities` (`UtilityDefinition{ UtilityBucket[] }`,
`UtilityBucket{ WeightedUtility[] Utilities, bool RejectAllNoneBestCases, Fix64 MinUtilityDifference@0x20 }`).

### 2.2 Évaluation par-ability — remplissage du bucket

Pour chaque ability, sa `Playbook` énumère ses candidats et émet une action scorée. Squelette uniforme
(`BasePlaybook.Evaluate`, déterministe : `SetDisallowRandom` autour) :

```
evaluate(unit, pos) -> Bucket:
    bucket = Bucket()
    for cand in enumerate_candidates(unit):     # GenerateBucketWithActionForEveryEligibleTarget
        u = score(cand)                          # ← seul delta par-playbook
        bucket.AddAction(GenerateAction(unit, pos, cand, u))
    return bucket
```

Deux **régimes de score** (juste nommés ici, détail → `scoring.md`) :
- **Comparable** (`ComparablePlaybook<T>`) — attaques, soins : somme pondérée sur prédictions partagée
  (`CalculateActionUtility`).
- **NonComparable** (`NonComparablePlaybook<T>`) — summons, buffs, mouvement : heuristique entière
  écrite DANS la feuille (ex. `MasterOfTheTutelaries`, `FightingRetreat`).

`DefaultActiveAbilityPlaybook` (la majorité des abilities) est trivial : énumère les cibles, priorité
constante `Fix64(3/2)=1.5`, aucune heuristique.

### 2.3 `ChooseAction` / `ChooseActionFromBuckets` — argmax parmi les légales

Le bucket-tree (sous-buckets imbriqués par catégorie, récursion) est un détail d'implémentation ; le
résultat net est **argmax-utilité parmi les actions légales** :

```
ChooseAction(bucket)               @1813fc0d0:
  si feasible(bucket.defaultAction):  return bucket.defaultAction
  sinon: return ChooseActionFromBuckets(bucket.children triés)    # SortedList par clé/priorité

ChooseActionFromBuckets            @1813fbe00:  itère la SortedList en ordre de clé,
                                                renvoie la 1ʳᵉ action faisable (récursif)
```

- Gate de faisabilité `FUN_18004cc80(bucket, action, ctx)` :
  `action != null && (bucket.minUtilityDifference absent OU action.Utility >= bucket.minUtilityDifference)`.
- `Bucket.AddAction` (@1813fbcc0) : `defaultAction` = action de **plus haute utilité** passant le gate
  (`if action.Utility > default.Utility: default = action`, `op_GreaterThan`) ⇒ **argmax dans une
  catégorie**.
- `Bucket.AddActionToBucket` (@1813fbb60) : range l'action dans un sous-bucket par **catégorie**
  (SortedList key=catégorie, créé SANS seuil par `CreateBucket`/`GetOrCreateBucket`
  @1813fc170/1813fc550 ⇒ gate toujours faisable).

**Résolu : « attaque vs move » n'est PAS une priorité-de-catégorie ni un seuil.** Si le movement
(ajouté EN DERNIER par `DefaultAiUnitTactic..ctor` @1810eebc0, après
`GetDefaultActiveAbilityActionGenerators()`) était départagé par ordre de catégorie, l'attaque
primerait toujours et le natif ne bougerait jamais avec une attaque dispo — or il MOVE. Donc
attaque / ability / approche-mouvement sont départagées par **argmax sur la devise unifiée** : le natif
MOVE quand `U(move) > U(meilleure attaque)`. Générateurs : `ActiveAbilityActionGenerator`,
`MovementActionGenerator`, `RandomAbilityActionGenerator` ; tactics : Default / OnlyMove / Random /
BossSkipActiveAbility / SkipTurn.

### 2.4 Modèle générique des feuilles (à porter)

`score(case) = Σ_{candidat énuméré} [ gate(candidat) ? Σ weightKeys_applicables(candidat) : 0 ]`, avec
`weight = playbookWeights[key]` (int, défaut 0) → Fix64. **Par-ability = uniquement** (a) le gate
(effet/trait/faction/adjacence + ids), (b) l'énumération (quel ensemble cibles/tuiles), (c) les clés de
poids + l'arithmétique. Tout le reste (scaffolding itérateur, `GetUtilityValue`, layout source) vit dans
la base. Cf. `playbooks.md`.

## 3. Architecture d'override (la raison de réimplémenter)

L'IA native est une boîte noire **non-surchargeable** ; la réimplémentation rend chaque décision
**modifiable**. Trois granularités, séparées du base fidèle :

| portée | mécanisme | exemple |
|--------|-----------|---------|
| **par-ability** | remplacer l'entrée du registre `PLAYBOOKS[abilityType]` | réécrire le scoring de `MasterOfTheTutelaries` |
| **par-poids** (Comparable only) | patcher un poids `Utilities` (0 code) | monter `w_dmg`, baisser `w_heal` |
| **global / transverse** | un *modifier* appliqué à TOUT score | pénaliser toute tuile dans un overwatch (blindspot connu) |

```python
faithful = Engine()                                            # clone validé vs natif (agreement ~100%)
improved  = Engine(overrides=[OverwatchPenalty(), AggressiveBias()])   # déviations VOULUES, traçables
```

- Le **base** reste mesuré contre l'IA native → baseline de fidélité honnête (`status.md`).
- Les **overrides** sont des deltas **opt-in** et **traçables** (« cette décision diffère du natif
  PARCE QUE le modifier X »). Sans cette séparation, un override polluerait la métrique de fidélité :
  on ne saurait plus si un désaccord = bug de portage ou amélioration volontaire.

Débloque : corriger les faiblesses (overwatch-suicide, sur-extension), générer des variantes
(aggressive/defensive → diversité du dataset IL), faire de l'A/B natif-fidèle vs amélioré.

## 4. Ce qui RESTE / est OUVERT (spine)

- **`order_strategy` de `PickNextUnit`** : modèle posé (8 buckets §2.1). À raffiner uniquement si
  l'agreement le réclame — le harnais compare déjà la MÊME unité (`activatedUnitId`), donc
  l'ordonnancement n'est PAS la cause des misses attaque-vs-move connus. Un ordre raisonnable suffit
  tant que le scoring par-action domine.
- **OUVERT (scale, → `scoring.md`)** : homogénéité numérique `tile_util` (centaines : MaxDistEnemies,
  MinDist −100) vs `U_damage` (KillUnit 50/100 + DamageDealt brut, magnitude inconnue — config Damage
  absente du BC). SEULE inconnue numérique restante de l'argmax move-vs-attaque ; à caler par
  l'agreement une fois `tile_util(tuile d'attaque)` ajouté au moteur.
