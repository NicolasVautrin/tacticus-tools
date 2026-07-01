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

### 2.3 Sélection de l'action — générateurs ordonnés, PREMIER NON-NULL (RE confirmé, modèle corrigé)

> ⚠ **Correction** : l'ancienne section affirmait un « argmax sur une devise unifiée » entre
> attaque/heal/move. **C'est FAUX** (vérifié dans le code, build gqfc5mff6c). Le vrai mécanisme est
> une **liste ordonnée de générateurs, premier-non-null**, mouvement en dernier (fallback).

`DefaultAiUnitTactic..ctor` (@1810eebc0) construit une LISTE ORDONNÉE de générateurs (@tactic+0x60) :

```
[ Gen(pref=1000), Gen(100), Gen(0), Gen(-100), Gen(-1000), Gen(final), MovementActionGenerator ]
  \________ 6 ActiveAbilityActionGenerator, un par TIER de préférence ________/   \_ move EN DERNIER _/
```

`CalculateNextActionForUnit.MoveNext` (@1810f54e0) itère la liste et renvoie la **PREMIÈRE action
NON-NULL** (`if (action != 0) break`). Pas d'argmax inter-générateurs — **premier-non-null par tier**.

**Tier de préférence par ability = sa PLAYBOOK.** `InitAbilityTypeLists` (@1810ed540) range chaque
ability dans la liste de son `playbook.Preference` (1000/100/0/-100/-1000 ; sans préférence → liste
« final »). Dict tier→abilities @tactic+0x40. `GetDefaultActiveAbilityActionGenerators` (@1810ed0c0)
crée un `ActiveAbilityActionGenerator` par tier dans cet ordre.

**Un générateur de tier** — `ActiveAbilityActionGenerator.GenerateActions` (@18119a3f0) :
1. énumère les abilities du tier que possède l'unité (`GetUnitAbilitiesInOrder` @181182a40, ordre
   déclaré, shuffle optionnel selon `ShouldRandomizeOrder`) ;
2. pour chaque ability UTILISABLE (`!IsAbilityBlocked`, `CanCurrentlyBeUsed`, playbook can-evaluate),
   exécute sa playbook → actions scorées → `Bucket.Merge` ;
3. termine par **`Bucket.ChooseAction`** (argmax-faisable, cf. ci-dessous) → renvoie l'action, ou
   **null si le bucket est VIDE** (aucune ability du tier n'a produit d'action LÉGALE).

**`ChooseAction` (argmax DANS un bucket)** :
```
ChooseAction(bucket)        @1813fc0d0:  feasible(default) ? default : ChooseActionFromBuckets(children)
ChooseActionFromBuckets     @1813fbe00:  itère la SortedList par clé, 1ʳᵉ action faisable (récursif)
Bucket.AddAction            @1813fbcc0:  default = action de plus haute utilité (op_GreaterThan) ⇒ argmax
Bucket.AddActionToBucket    @1813fbb60:  sous-bucket par catégorie (SortedList, SANS seuil ⇒ feasible)
gate FUN_18004cc80       :  action != null && (minUtilityDifference absent OU U >= minUtilityDifference)
```

**Conséquences (modèle corrigé) :**
- Ordre inter-catégorie = **tiers de préférence par-ability** (hard priority), PAS un ordre figé
  attack>heal>summon, PAS un argmax sur devise commune.
- DANS un tier, plusieurs abilities se départagent par **argmax d'utilité** (le bucket).
- Le **MOUVEMENT est un FALLBACK** : il ne fire QUE si AUCUN tier d'ability n'a produit d'action
  légale (= rien d'atteignable/utilisable). **Pas de seuil utilité ability-vs-move.**
- « Bouger pour mieux attaquer » N'EST PAS le MovementGen : c'est une **action d'ability avec
  composante de déplacement** (la playbook énumère les couples (tuile atteignable, cible) ; le bucket
  prend le meilleur). Le MovementGen pur (approche) ne sert que quand aucune attaque n'est possible
  depuis aucune tuile atteignable.

> **Re-validation LIVE (Rotbone, #38 option A) → VERDICT B** : Rotbone, allié adjacent **manque 2007 PV**
> (cible LÉGALE de Heal 18 ET Active 1037 via `abilityTargets`), Rotbone sans attaque → **le natif BOUGE**.
> Donc « premier-non-null PUR » est incomplet : un tier peut renvoyer null **malgré une cible ciblable**.

### 2.3bis Le GATE par-action (`ShouldExecute`) — RE complet

Chaque action *comparable* (attaque/soin/repair) s'auto-gate à l'**émission**. Flux (RE) :

```
ComparablePlaybook.EvaluateInternal   @181408980 :  pour chaque cible éligible
    util = CalculateActionUtility(...)              # Nullable<TimeSpan>
    if util.HasValue:                               # <-- GATE : sinon AUCUNE action émise
        action = GenerateAction(unit, cible, util.Value)
        if FUN_18004cc80(bucket, action): bucket.argmax(action)

CalculateActionUtility                @181406ee0 :
    u = predictionUtility(...)                      # heal: CalculateUtilityFromHealEvent (cf. §9)
    if !ShouldExecute(unit, cible, u): return null  # vtable +0x328  → Nullable.null
    u += tileUtility (CalculateUtilityFromTilePrediction) + UtilityAttackCase + ...
    return Nullable(u)                              # (sentinels TimeSpan Zero/Min/Max gérés à part)

HealPlaybook.ShouldExecute            @181184b30 :  return u > 0 && (cibleNonBoss || cible != caster)
```

⇒ **Le gate = `prédiction d'utilité > 0`.** Si l'utilité de soin (la cible) est `<= 0`, `ShouldExecute`
renvoie false → `CalculateActionUtility` renvoie `null` → `EvaluateInternal` **n'émet pas** d'action →
le tier soin renvoie null → fallback MOVE. (Légalité de ciblage `abilityTargets` ≠ utilité > 0.)

> ⇒ **Remplaçant fidèle de `ENGINE_HEAL_MIN_UTIL`** : émettre le soin **ssi `heal_utility > 0`** (seuil
> **0**, pas 50), sur l'utilité de soin déjà portée (#37, `predict.py` PARTIE 3). Idem attaque (utilité
> de prédiction > 0, + sentinels kill).
>
> **✅ RÉSOLU — « VERDICT B » était une ERREUR DE MESURE, pas un comportement natif.** Le dump de
> l'action COMPLÈTE de Rotbone (`aiDryRunAllUnits`, chunk entier, pas juste le 1er message) :
> `[ MoveUnitMessage u80→(1,2), ActiveAbilityMessage caster=80 target=80 abilityType=18 (Heal) ]`.
> **Rotbone se DÉPLACE PUIS SOIGNE.** Le helper `native_first` renvoyait `"move"` sur le premier
> message et **masquait le heal qui suit** → tout le « contradiction / gate mystère » poursuivait un
> **fantôme**. La chaîne RE était **correcte depuis le début** : `heal_utility > 0` ⟹ le soin EST émis.
> Les sous-pistes (IsFriend par-joueur `@180ed8550`, magnitude `Damage×hits`, éligibilité
> `ShouldEvaluateTarget @18111fb10` sans filtre « déjà agi », `get_CanCurrentlyBeUsed @180f8fdb0`
> cooldown/charges, abilities `18`+`1037` `usable=true`) restent des RE valides, mais elles cherchaient
> à expliquer un non-événement.
>
> **Leçon (mesurer la vérité terrain, pas un proxy)** : l'action native est souvent **COMPOSÉE**
> (`move + ability`). Toute comparaison moteur-vs-natif doit lire le **chunk entier**, pas
> `native_first[0]`. ⚠ **`ENGINE_HEAL_MIN_UTIL` est très probablement FAUX** : il fait *bouger* le moteur
> là où le natif fait *move+heal* ; la « concordance » mesurée plus tôt ne tenait qu'au 1er message
> (le move), par coïncidence.
>
> **✅ REFONTE SCORING UNIFIÉ (1ère tranche, `engine_decide` — VALIDÉE LIVE).** Modèle natif porté :
> chaque ability candidate = `(tuile atteignable, cible)` scorée `pred_util + tile_util(tuile)` ;
> gate `ShouldExecute` = `pred_util > 0` (l'ancien seuil 50 RETIRÉ — il était faux) ; argmax `full_util`
> ; le MOVE est le **fallback** (RE premier-non-null). La branche soin **balaie les tuiles** (cible
> joignable depuis T ssi `hexdist(T,cible) ≤ HEAL_RANGE`, self depuis toute tuile) → produit une action
> **composée move+heal**. **Validation Rotbone : MATCH EXACT** (moteur = natif : move→(1,2) + heal
> ability 18 sur self) après fix `is_friend` (comparer à `me.team` 1/2, pas `currentPlayer` 3/4).
> **RESTE** : (a) `HEAL_RANGE=1` (mêlée) en dur → portée gameconfig pour soins à distance ; (b)
> `tile_util` = `move.move_utility` (profil MovementSuggestion) en proxy du tile_util d'action natif
> (profil `Default` `CalculateUtilityFromTilePrediction`) — calibration ouverte (§3.5) ; (c) intégrer
> summon/buff au pool unifié (encore en branche fallback) ; (d) **non-régression** : lancer les tests
> ciblés attaque/heal (la branche attaque passe de return-immédiat à candidat-poolé) avant tout commit ;
> (e) corriger `native_first`/le harnais d'agreement pour comparer le **chunk complet** (move ∧ ability).

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
