# Playbook Engine — réimplémentation Python de l'IA playbook du jeu

> **But** : un moteur Python *standalone* qui reproduit le système de playbook de l'IA
> native de Tacticus, **vivant à CÔTÉ de l'oracle** (pas un remplacement). Driver pair :
> oracle (LLM) · IA native (`aiPlayByUnit`) · humain · **moteur playbook** (ce doc).
> Débloque les appariements oracle-vs-moteur (= bench baseline), moteur-vs-natif, etc.
>
> **Principe directeur : la validation est le pilier.** Chaque pièce portée est comparée
> à la décision de l'IA native sur le MÊME état (agreement %). On ne porte jamais à l'aveugle.

## 1. Architecture de l'IA native (RE, build gqfc5mff6c)

L'IA du jeu = **maximisation d'utilité par buckets**, PAS 200 algos indépendants.

```
Tour d'une équipe (CheatRunAIMessage / ReplayRunner.RunAi)
  └─ boucle: PickNextUnit (OperationalDeciders.DefaultGroupOperator) → unité à activer
       └─ pour chaque ability de l'unité → sa Playbook (registre 1 classe/ability)
            ├─ NonComparablePlaybook<T> : GenerateBucketWithActionForEveryEligibleTarget
            │     → remplit un BUCKET de candidats (cibles/tuiles éligibles)
            └─ ComparablePlaybook<T> : score chaque candidat via CalculateActionUtility
       └─ Bucket.ChooseActionFromBuckets → pick l'action de MEILLEURE utilité
```

### 1.1 La formule d'utilité (cœur — `ComparablePlaybook.CalculateActionUtility`)

`utility(action) =` somme pondérée de :

| terme | source | poids (offset config) |
|-------|--------|----------------------|
| dégâts prédits (par DamageEvent) | `Playbook.CalculateUtilityFromDamageEvent` | `cfg+0x80` |
| soin prédit (par HealEvent) | `CalculateUtilityFromHealEvent` | `cfg+0x90` |
| réparation (repair) | `UtilityAttackCase.ForRepairPrediction` | poids idx 6 (ability 0x2e=46) |
| effets appliqués | `UtilityAttackCase.ForEffect` × magnitude | poids idx 5 (ability 0x2d=45) |
| utilité de POSITION du caster | virtuel `+0x348`, gaté par `+0x328` | `+0x350` |
| utilité de la TUILE | `CalculateUtilityFromTilePrediction` | `cfg+0x60` |
| **utilité CUSTOM par-ability** | virtuel `+0x338` (override par playbook) | `cfg+0x340` |

- Les prédictions (dégât/soin/effet) viennent du moteur de prédiction natif
  (`DamagePredictionQuery.GetAllPredictions` = déjà exposé par le hook `aiPredict`).
- Eval **déterministe** : `BasePlaybook.Evaluate` fait `SetDisallowRandom` autour.
- `cfg` = la config de la playbook (`playbook.<config>@0x20 → .<UtilityWeights>@0xc0`),
  qui dérive de **`BattleConfiguration.Utilities`** (poids statiques, déjà dans les archives
  JSON — cf. mémoire [[project_ai_weights_in_battle_config]]).

### 1.2 Conséquence pour le portage

- **Le SPINE est petit** : `PickNextUnit` + `ChooseActionFromBuckets` + la somme pondérée
  + les générateurs de candidats (`GenerateBucketWithActionForEveryEligibleTarget`,
  `GenerateAttackPredictions`). ~5 méthodes.
- **Les prédictions sont déjà calculables** : `aiPredict` (DamagePrediction native) OU
  re-dérivables de gameconfig.
- **Les poids sont extractibles** : `BattleConfiguration.Utilities` (archives JSON).
- **Les ~200 leaf playbooks = surtout des DELTAS** : (a) base Comparable vs NonComparable,
  (b) génération de candidats (quelles cibles/tuiles), (c) override `CalculateCustomUtility`.
  Beaucoup n'ont AUCUN custom (pur comportement de base) → deviennent de la *donnée*, pas du code.

### 1.3 Le pattern uniforme + les 2 régimes de score (vérifié sur 3 leaves)

Décompilation de 3 leaves témoins (`DefaultActiveAbility`, `MasterOfTheTutelaries`,
`FightingRetreat`) → **toutes suivent le MÊME squelette** :

```python
evaluate(unit, pos) -> Bucket:
    bucket = Bucket()
    for cand in enumerate_candidates(unit):   # cibles/tuiles éligibles (GetEligibleTargetsSelectable / movableTiles)
        u = score(cand)                        # ← LE seul delta par-playbook
        bucket.AddAction(GenerateAction(unit, pos, cand, u))
    return bucket
```

Et **DEUX régimes de score** (raffinement de §1.1) :
- **NonComparable** (summons, buffs, mouvement) → **heuristique entière DANS la leaf** (visible,
  simple). Ex. `MasterOfTheTutelaries` : `u = 1 + max(enemyCount-1,0)*10 + max(freeAdjacent-3,0)*10
  (+100 si tuile optimale)`, **gardé par `freeAdjacent>2 && enemyCount>0`** (= la légalité spawn-tile
  de TF12, confirmée ici). `FightingRetreat` : `u = count(retreatTiles)(+ reachable)`.
- **Comparable** (attaques, soins) → la **somme pondérée sur prédictions** partagée
  (`CalculateActionUtility`, §1.1).

Le `DefaultActiveAbilityPlaybook` (la majorité des abilities) est **trivial** : énumère les cibles,
priorité **constante `Fix64(3/2)=1.5`**, aucune heuristique. Le plus gros leaf vu (`MasterOfTheTutelaries`)
= **~12 lignes** de vraie logique. → confirmé : pas de monstre, des deltas de 5-15 lignes.

Interface de portage = **1 interface uniforme** (`enumerate_candidates` + `score`) + **2 scoreurs**
(`predict_utility` partagé / `heuristic` par-leaf).

### 1.4 Sélection + ordre intra-tour (spine, RE)

**Sélection — `Bucket.ChooseAction` / `ChooseActionFromBuckets`** : les actions candidates sont
rangées dans une **`SortedList` par priorité = utilité** (clé décroissante), parcourue dans l'ordre,
et on retourne la **PREMIÈRE action VALIDE**. La validité = un gate de faisabilité/légalité
(`FUN_18004cc80(action, seuil@cfg+0x40)`). Le bucket-tree (sous-buckets imbriqués, récursion) est un
détail d'implémentation. **Modèle Python équivalent** :
```python
def choose_action(candidates, ctx):                  # candidates = [(action, utility)]
    for action, _u in sorted(candidates, key=lambda c: -c[1]):  # priorité décroissante
        if is_valid(action, ctx):                    # gate de faisabilité/légalité
            return action
    return None                                       # = argmax(utilité) parmi les actions LÉGALES
```

**Ordre intra-tour — `DefaultGroupOperator.PickNextUnit`** (itérateur) :
```python
def pick_next_unit(state):
    units = GetValidUnits(state)          # vivantes + contrôlées + action restante
    for u in order_strategy(units):       # stratégie pluggable (operator.0x28) — ordering par priorité d'unité
        yield u
```
La `order_strategy` (vtable idx 1 sur `operator.0x28`) est l'ordonnancement par priorité d'unité —
à raffiner si l'agreement le réclame (sinon un ordre raisonnable suffit, le scoring par-action domine).

**→ Spine décisionnel complet** :
```
while valid_units:                        # PickNextUnit
    unit = next ordered valid unit
    cands = []
    for ability in unit.abilities:        # 1 playbook/ability
        cands += playbook_for(ability).evaluate(unit, pos)   # §1.3 (Comparable=prédictions / NonComparable=heuristique)
    action = choose_action(cands, ctx)    # §1.4 max-utilité-parmi-légales
    apply(action)
```

### 1.5 Les poids `Utilities` (RE archive JSON — chargeable directement)

`BattleConfiguration.Utilities` est un **config NOMMÉ** (pas des offsets) → `weights.py` le charge
tel quel depuis `data/arena-battle-config-newtonsoft.json`. **2 profils** : `Default` et
`MovementSuggestion`. Sous `Default`, ~55 catégories, dont :

- **cœur dégât/kill** : `KillUnit`, `OverkillUnit` (le `CalculateUtilityFromDamageEvent` mappe un
  damage-event → utilité via ces poids).
- **position** : `MaxDistanceToEnemies`, `MinDistanceToClosestEnemy`, `MaxDistanceToUnitTile`,
  `Elevation`, `DislikeStartingTilesUtility`, `MinDistanceToClosestEnemy`…
- **effets** : `TileEffects`, `AddedTileEffects`, `UnitEffectsAdjacent/Ranged/Surrounding`,
  `AttackTargetWithEffect`.
- **ordre intra-tour** : `UnitOrder` (= les poids de `PickNextUnit`).
- **triggers / overwatch** : `TriggeredAbilities`, `TriggeredAbilitiesNonOwner` (= le levier pour
  l'override anti-overwatch-suicide).
- **knobs custom par-ability** : `ActiveAbilities.<Name>` (ex. `ArcScourge_AdjacentEnemies:20`,
  `TwistedScience_ExtraDamageUtility:100`, `PlagueburstMortar_AdjacentEnemy:10`,
  `MasterOfTheTutelaries_MoveTowardsTarget`) — les constantes que lisent les leaves NonComparable.

→ Surcharge « par-poids » (§3.1) = patcher une clé de ce dict, 0 code. La validation Fix64 reste sur
l'**argmax** (la décision), pas la valeur exacte.

## 2. Layout du package Python (proposé)

```
scripts/python/engine/
  __init__.py
  state.py        # adaptateur : decisionView/attackPlans/abilityTargets/aiPredict → état interne
  weights.py      # loader des poids depuis BattleConfiguration.Utilities (archive JSON)
  predict.py      # prédictions : passe par aiPredict (natif) en Phase 1 ; gameconfig plus tard
  utility.py      # LA somme pondérée (CalculateActionUtility) — le cœur
  buckets.py      # génération de candidats + ChooseActionFromBuckets (sélection argmax)
  order.py        # PickNextUnit (ordre intra-tour)
  playbooks/      # registre 1 entrée/ability : base + deltas (custom utility, candidate-gen)
    __init__.py   #   registry: abilityType → Playbook (fallback = DefaultActiveAbility)
    base.py       #   ComparablePlaybook / NonComparablePlaybook génériques
    _generated/   #   leaves portées (Phase 2, agreement-driven)
  policy.py       # Policy = base + modifiers (cf. §3) ; FAITHFUL vs variantes
  modifiers.py    # modifiers transverses (OverwatchPenalty, AggressiveBias, …)
  engine.py       # API driver : decide_turn(runnerId) → liste d'actions (applyAction)
engine_validate.py # harnais : IA native (aiStepDryRun) vs moteur → agreement % par état
```

**API driver** (pour coexister avec l'oracle dans l'infra de match) :
`engine.decide_unit(state, unitId) → action` et `engine.decide_turn(state) → [actions]`,
applicables via le même `applyAction` que l'oracle/self-play.

## 3. Architecture d'override (modifiabilité — la raison de réimplémenter)

L'IA native est une boîte noire **non-surchargeable** ; la réimplémentation rend chaque
décision **modifiable**. C'est un objectif de design de premier ordre.

### 3.1 Trois granularités de surcharge

| portée | mécanisme | exemple |
|--------|-----------|---------|
| **par-ability** | remplacer l'entrée du registre `PLAYBOOKS[abilityType]` | réécrire le scoring de `MasterOfTheTutelaries` |
| **par-poids** (Comparable only) | patcher un poids `Utilities` (0 code) | monter `w_dmg`, baisser `w_heal` |
| **global / transverse** | un *modifier* appliqué à TOUT score | pénaliser toute tuile dans un overwatch (blindspot connu) |

```python
# engine/playbooks/registry.py
PLAYBOOKS: dict[int, Playbook] = {}                  # abilityType -> Playbook
def playbook_for(ab: int) -> Playbook:
    return PLAYBOOKS.get(ab, DEFAULT_ACTIVE_ABILITY)  # défaut = trivial (§1.3)

@register(MASTER_OF_TUTELARIES)                       # surcharger UNE ability
class MyMoTT(NonComparablePlaybook):
    def score(self, cand): ...                        # ta variante du heuristique

# engine/policy.py
class Policy:
    def __init__(self, base=FAITHFUL, modifiers=()):
        self.base, self.modifiers = base, modifiers
    def score(self, unit, ability, cand):
        u = self.base.score(unit, ability, cand)
        for m in self.modifiers:                       # OverwatchPenalty, AggressiveBias, …
            u = m(unit, ability, cand, u)
        return u
```

### 3.2 Principe : séparer le BASE fidèle de la COUCHE d'override

```python
faithful = Engine()                                   # clone du jeu, VALIDÉ vs natif (agreement ~100%)
improved  = Engine(overrides=[OverwatchPenalty(), AggressiveBias()])  # déviations VOULUES, traçables
```

- Le **base** reste mesuré contre l'IA native (harnais §4) → baseline de fidélité honnête.
- Les **overrides** sont des deltas **opt-in** et **traçables** (« cette décision diffère du natif
  PARCE QUE le modifier X »). Sans cette séparation, un override polluerait la métrique de fidélité
  et on ne saurait plus si un désaccord = bug de portage ou amélioration volontaire.

Débloque : corriger les faiblesses (overwatch-suicide, sur-extension), générer des **variantes**
(aggressive/defensive → diversité du dataset IL), faire de l'**A/B** natif-fidèle vs amélioré.

## 4. Stratégie de validation (le pilier)

- `engine_validate.py` : sur N états (rejoués depuis les démos `data/selfplay-logs/` OU
  états aléatoires d'un runner), comparer **action choisie par le moteur** vs **action de
  l'IA native** (`aiStepDryRun`/`aiPlayByUnit` dry-run) → **agreement %** global + par ability.
- Métrique cible : agreement monte vers ~100 % à mesure qu'on porte les playbooks.
- Désaccords = la to-do priorisée de la Phase 2 (porter d'abord ce qui diverge le plus).

## 5. État RE (Phase 0)

✅ Décompilé/compris : `BasePlaybook.Evaluate` (virtuel EvaluateNonComparable),
`ComparablePlaybook.CalculateActionUtility` + `CalculateUtilityFromPredictions` (la formule),
inventaire bucket-system + Comparable/NonComparable + les ~200 leaves, **3 leaves témoins**
(`DefaultActiveAbility` trivial, `MasterOfTheTutelaries` heuristique, `FightingRetreat`) → pattern
uniforme + 2 régimes de score figés (§1.3).

✅ **Spine complet** (§1.4) : `ChooseAction`/`ChooseActionFromBuckets` (= argmax-utilité-parmi-légales,
SortedList par priorité + gate de faisabilité) + `DefaultGroupOperator.PickNextUnit` (unités valides
ordonnées par priorité). Le squelette décisionnel bout-en-bout est figé.

✅ **Poids `Utilities` localisés** (§1.5) : config nommé `Utilities.{Default,MovementSuggestion}` dans
la BC JSON, chargeable directement.

**→ Phase 0 CLÔTURÉE.** Le modèle décisionnel complet est figé (spine + 2 régimes de score + sélection
+ ordre + poids + archi d'override). Reste des raffinements *agreement-driven* (pas des blocages),
à traiter en Phase 1/2 quand le harnais les réclamera :
- la `order_strategy` exacte de `PickNextUnit` (sinon un ordre par `UnitOrder` + priorité suffit) ;
- le prédicat de validité `FUN_18004cc80` (sinon : filtrer par légalité via `abilityReason`/`abilityTargets`) ;
- le mapping exact damage-event → utilité (`KillUnit`/`OverkillUnit` + barème) ;
- le portage des ~200 leaves (Phase 2).

## 6. Risques / garde-fous

- **Dérive de fidélité** = risque #1 → validation continue (§3), jamais de portage non validé.
- **FixMath Fix64** : le jeu calcule en virgule fixe 64-bit (`FixMath.NET.Fix64`). Pour
  l'agreement exact il faudra répliquer l'arithmétique Fix64 (ou tolérer un epsilon et ne
  comparer que l'ARGMAX, pas la valeur d'utilité — l'argmax est ce qui compte pour la décision).
- **Dépendance prédictions** : Phase 1 s'appuie sur `aiPredict` (natif, donc dépend du jeu
  live). L'offline complet (Phase 3, hors-scope initial) exigerait de re-dériver les
  prédictions de gameconfig.

## 7. Phase 1 — squelette + premier agreement (FAIT)

Modules livrés + testés : `engine/weights.py` (charge `Utilities`, validé réel : kill 100/50,
overkill 40/15, 107 `TriggeredAbilities`, 18 `ActiveAbilities`), `engine/select.py`
(argmax-parmi-légales), `engine/utility.py` (barème attaque kill/overkill aligné TF04),
`engine_validate.py` (LE harnais : marche la trajectoire `aiStepDryRun` natif, compare la
décision moteur sur le même état).

**Métrique** : le natif splitte une activation en chunks (`MoveUnitMessage` puis
`ActiveAbilityMessage`), le moteur les combine → on compare la **DESTINATION** (tuile où va
l'unité, qu'elle soit étiquetée move ou attack-approach), pas le label, + le **cast** d'une
ability en place.

**Premier résultat (seed 777, 18 pas, premier jet zéro leaf portée)** :
- **positioning : 50 % exact, 75 % ≤1 hex** (8/16 tuiles identiques au natif, 12/16 à ≤1 hex).
- **ability : 50 %** (matche la normale `ab=69`; rate un cast NonComparable `1167` non porté).

**Diagnostic = la to-do priorisée de la Phase 2** :
1. **Move-scoring** (repositionnement pur) : « min-distance ennemi » trop grossier → porter
   `MovementSuggestion` (poids `MaxDistanceToEnemies`/`MinDistanceToClosestEnemy`/`Elevation`/
   `MaxDistanceToUnitTile`…). C'est le plus gros gain (la plupart des ~1hex et le gros miss step0).
2. **Leaves NonComparable** (buffs/summons/heals) : porter les playbooks des abilities castées
   en place (`1167`…) — agreement-driven (porter d'abord celles qui ratent le plus).
3. **Tie-break / multi-cible** : quelques ~1hex sur les attaques = choix de tuile/cible à
   utilité proche → raffiner le barème (terme position-caster `CalculateCasterPositionUtility`).

**Note archi** : la décision est pour l'instant inlinée dans `engine_validate.py` (`engine_decide`).
À refactorer dans le layout §2 (`state.py`/`playbooks.py`/`engine.py`) en Phase 2 — la logique est
figée, le déplacement est mécanique.

## 8. Phase 2a — MovementSuggestion porté + A/B (FAIT)

**RE des 4 termes de position** (ghidra, `IdunBattle.AI.Utilities.*Utility.<EvaluateMovementInSteps>`
+ `BaseUtility.GetUtilityValue` = lit le poids nommé BC → `Fix64.FromInt`) :

| terme (`*Utility`) | formule RE'd | poids (`Default.<cat>`) |
|--------------------|--------------|--------------------------|
| `MinDistanceToClosestEnemy` | `wMin × min_d(tile, enemies)` | `PerTileDistance −100` |
| `MaxDistanceToEnemies` | `Σ_e [ Wfar − (Wfar−Wclose)/d_e ]` | `ClosestEnemy 10, FarthestEnemy 100` |
| `MaxDistanceToUnitTile` | `Wfar − (Wfar−Wclose)/d_ref` | `ClosestTile 400, FarthestTile 700` |
| `Elevation` | `Mult·elev (+Highest si max, +Lowest si min)` | `Mult 10, Highest 10, Lowest −5` |

Forme commune des deux `MaxDistance*` : `f(d)=Wfar−(Wfar−Wclose)/max(d,1)` (f(1)=Wclose, f(∞)→Wfar,
rendements décroissants). Module porté = `engine/move.py` (`move_utility`/`best_move`). Elevation
omise (pas de data d'élévation de tuile dans `decisionView`). `RangedAdjacentEnemy` (profil
`MovementSuggestion`, `HasAdjacentEnemy −50`) inclus pour les unités ranged.

**A/B agreement-driven du terme dominant `MaxDistanceToUnitTile`** (assignation Wfar/Wclose + tuile
de référence ambiguës sans résoudre le DAT→string) — harnais sur trajectoire native déterministe :

| seed | far (s'éloigne origine) | near | **off (défaut retenu)** |
|------|-------------------------|------|--------------------------|
| 777  | 50 % / 72 % | 44 % / 66 % | 50 % / 72 % |
| 2024 | 44 % / 55 % (u84 sprint coin ~6hex) | — | 44 % / **61 %** (u84 → ~1hex) |

→ **`off` ≥ `far` sur les 2 seeds** (777 : far==off, le terme ne flippe aucun argmax ; 2024 : `far`
fait sprinter u84 dans un coin, `off` le corrige). **Conclusion : interpréter `MaxDistanceToUnitTile`
comme « distance à la tuile d'ORIGINE » est FAUX** — la vraie tuile de référence est autre chose
(formation alliée / tuile-cible). Terme **désactivé par défaut**, gardé GATÉ (`ENGINE_UNITTILE_MODE`)
pour réactivation une fois la référence RE'd.

**Diagnostic clé (re-priorise la Phase 2b)** : le scoring de position générique se réduit en pratique
à « avancer vers l'ennemi le plus proche » (MinDist domine ; MaxDistToEnemies module ; UnitTile off ;
Elevation no-data). Il matche le natif sur les **movers normaux** (777 : u88 EXACT, u90/u94 ≤1hex).
Les désaccords résiduels ne sont **PAS** de la précision de position — ce sont des **playbooks de
mouvement SPÉCIAUX** + des **abilities NonComparable jamais castées** :
- `TeleportStrike`/DEEP-STRIKE (777 step0 u96 → ~5hex ; placement de téléportation, pas de marche) ;
- kite ranged/overwatch (777 step17 u78 ~3hex ; 2024 u80/u84) ;
- casts NonComparable buff/summon `1167`/`1171`/… (le moteur défaut move/normal-attack → MISS).

**→ Phase 2b (re-priorisée)** : (1) playbooks de mouvement spéciaux (TeleportStrike d'abord = plus
gros miss isolé), (2) leaves NonComparable (registre `abilityType→Playbook` pour buffs/summons),
(3) refactor `engine_decide` → layout package §2. Plus de précision sur les termes de position =
rendement nul (validé). NB harnais : `listRunners` renvoie désormais des objets `{runnerId,…}` (fix
résolution `--runner` auto livré).

## 9. Phase 2b — « TeleportStrike » : faux playbook, vrai terme RangedAdjacentEnemy (FAIT)

**Mesure ground-truth d'abord** (probe live du step0 u96, seed 777) : l'action native de u96
(`darkaTerminator`, DEEP-STRIKE + `TeleportStrike_TeleportingIn`) est un **`MoveUnitMessage` NORMAL**
vers (6,4) — **PAS** un message spécial de téléportation. `TeleportStrike` est un **effet VISUEL**
(`View.AbilityConfigs.*EffectVisuals`), il n'existe **aucun playbook de mouvement TeleportStrike** à
porter. La RE de `IdunBattle.AI.Playbook.*Teleport*` ne renvoie que du View.

**Le vrai désaccord** : le natif place u96 à (6,4) = min-dist **2** (NON adjacent) ; mon moteur le
plaçait à (3,7)/(5,5) = min-dist **1** (adjacent). Cause RE'd = `IdunBattle.AI.Utilities.
RangedAdjacentEnemyUtility` :
- `ShouldApply(unit)` = l'**arme/ability** de l'unité est RANGED (`WeaponProfile.get_IsRanged` pour
  l'attaque régulière ; RangedBool `@0x3d` sinon) — **PAS** le flag unité-classe
  `UnitExtensions.IsRanged` qu'expose `decisionView.ranged` (= False pour u96 mêlée-classe, alors que
  sa PlasmaCannon est ranged).
- `EvaluateMovementInSteps` : si ShouldApply **et** la tuile candidate a **≥1 ennemi adjacent** →
  ajoute `MovementSuggestion.RangedAdjacentEnemy.HasAdjacentEnemy` (**−50**).

**Fix** : terme `RangedAdjacentEnemy` (déjà dans `engine/move.py`) gaté sur un signal « ranged » DÉRIVÉ
de **gameconfig** par `visualId` (vérité offline) = `arme Range≥2 OU active attackRangeType=='Ranged'`
(env `ENGINE_RANGED_DEF`), pas le flag `decisionView.ranged` (le harnais fournit ce `ranged` ;
`engine/move.py` reste pur). Capture u96 (PlasmaCannon) que le flag unité ratait.

**Validation** (UnitTile off, terme ranged ON) :

| seed | avant (sans RangedAdj) | **après** |
|------|------------------------|-----------|
| 777  | 50 % / 72 % (u96 step0 ~5hex) | **55 % / 77 %** (u96 step0 **EXACT**) |
| 2024 | 44 % / 61 % | 44 % / 61 % (pas de régression) |

→ net positif (777 : u96 step0 ~5hex→EXACT, +5/+5 ; 2024 neutre). **Apprentissage structurel** : le
scoring de mouvement est **par-ability** — une unité avec ability ranged évite l'adjacence
(`RangedAdjacentEnemy`), une mêlée la recherche. `decisionView.ranged` (unité-classe) est insuffisant ;
la source correcte du « ranged-pour-mouvement » = l'arme/ability (gameconfig). Reste Phase 2b : leaves
NonComparable (casts `1167`/`1171` toujours MISS) + refactor package.

## 10. Phase 2b — leaf NonComparable (summon) + sélection bucket-tree (RE + port, FAIT)

**Ground-truth d'abord — les ids du plan étaient mal étiquetés** : `1167 = Heal_TwistedScience`
(un HEAL, **Comparable**), `1171 = DakkaDakkaDakka` (une attaque spéciale, **Comparable**),
`1166 = AberrantHypermorph` (un SUMMON, **NonComparable**). Aucune des deux que le plan appelait
« NonComparable » ne l'est. Le vrai leaf NonComparable = le summon `1166`.

**RE du leaf** (`AberrantHypermorphPlaybook`) : `GetUtility(tile)` / `EvaluateNonComparable` =
**utilité d'une tuile de spawn = NOMBRE d'ennemis ADJACENTS** (hex-dist 1) à la tuile
(`FUN_180007c20(0x7e)` get-adjacent-enemies → `.Count` → `Fix64`). L'IA invoque là où le summon
engage le plus d'ennemis. Candidats = `GetEligibleTargetsSelectable` (= les tuiles `abilityTargets`).
Porté dans `engine/leaves.py` (registre `abilityType→scoreur`, extensible).

**RE de la SÉLECTION (bucket-tree)** : `Bucket.ChooseAction` = retourne l'action **DÉFAUT** du nœud
(field 0x20) si elle passe la gate de faisabilité `FUN_18004cc80`, sinon descend dans les enfants
(`SortedList` field 0x28) **ordonnés par utilité**, et renvoie la **première faisable**. Le
`UnitAction` = (position, target, **abilityType**) — pas de priorité dedans. → l'ordre **inter-CATÉGORIE**
(summon vs move vs attack) vient de l'assemblage du bucket racine + des clés de catégorie, **pas
encore RE** (les utilités ne sont PAS comparables : summon ~0-6 vs kill ~100 vs move ~100s).

**Increment livré + validé** : `allAbilities:True` (le moteur voit les abilities actives + attaques
spéciales) ; leaf summon + **règle de tir empirique** (tire si aucune attaque dispo ET une tuile a
≥1 ennemi adjacent) ; gate `_is_leaf` → ne tire QUE pour les leaves portées (sûr, pas de régression).

**Résultat (seed 777)** : **inchangé 55 % / 77 % / 50 %** — le summon `1166` **ne tire jamais** dans
la fenêtre (ennemis non encore en mêlée → 0 adjacent → utilité 0, le natif ne summon pas non plus =
cohérent). Les casts réels de la trajectoire sont **Comparable** : `1167` heal (step1, le moteur n'a
PAS de modèle de soin → bouge = MISS) et `1171` DakkaDakkaDakka (step21 : surfacé par allAbilities mais
le barème d'attaque score normal-69 ≥ 1171 = **précision**, pas candidat manquant). Le leaf summon est
**porté + correct** (wiring validé : argmax adjacent-enemy OK) mais **non exercé** ici.

**→ Vrais leviers seed-777 (re-priorisés)** : (1) **modèle de SOIN** (`Heal_TwistedScience` 1167 =
le miss step1 ; Comparable, poids heal `cfg+0x90`/`CalculateUtilityFromHealEvent`) ; (2) **précision
attaque spéciale** (pourquoi `DakkaDakkaDakka` > normal — multi-hit / knob `ActiveAbilities`) ; (3)
le **bucket-tree par-catégorie** (clé d'ordre summon/heal/move/attack) pour la sélection inter-type ;
(4) refactor package. Le leaf summon reste prêt pour les seeds/états où la mêlée le rend bénéfique.

## 11. Phase 2b — tie-break attaque spéciale > normale (FAIT) + heal bloqué

**Ground-truth (harnais ENGINE_DEBUG, dump des prédictions par-ability)** :
- **step21 (DakkaDakkaDakka)** : `(69→84, util 50, dmax 1147=hp)` ET `(1171→84, util 50, dmax 1147=hp)`
  — les deux TUENT u84, **utilité ÉGALE**. La prédiction de dégât est cappée à la PV cible donc 69 et
  1171 sont indiscernables pour le barème. Le natif prend la **spéciale** `1171` ; mon tie-break
  « premier gagne » prenait `69`. Aucun knob BC pour DakkaDakkaDakka → préférence **structurelle**
  (bucket d'ability active > bucket normal-attack).
- **Fix livré** : tie-break = à utilité égale, préférer l'ability **non-normale** (`name` sans
  « NormalAttack »). Clé `(util, is_special)`. **Sans régression** (steps15/19 : pas de spéciale à
  égalité — 1116 util 0, 1183 hors-portée). **Résultat seed777 : ability 50 %→75 % (3/4)** ; seed2024
  inchangé (100 %/2). step15/19 restent MATCH.

**Heal `1167` — BLOQUÉ (diagnostic)** : `Heal_TwistedScience` **n'est PAS une ability autonome** —
c'est l'effet du **passif `TwistedScience`** de genesBiophagus (gameconfig : seul actif =
`AberrantHypermorph` ; `Heal_TwistedScience` = entrée d'effet vide). Le natif l'émet comme
`ActiveAbilityMessage(1167)` mais elle **n'apparaît PAS** dans `unitAbilityTypes` (= [69, 1166]) →
le moteur ne peut pas l'énumérer comme candidat. Débloquer = surfacer les abilities **granted par
passif** (hook ActiveAbilityComponent au-delà de GetActives, OU dériver du passif via gameconfig) +
modèle de soin (Comparable, poids heal) + sélection bucket-tree (heal vs move). → reste sur task #17.

**État agreement seed777 : positioning 55 %/77 %, ability 75 %.**

## 12. Phase 2b — unblock énumération des abilities GRANTED-par-passif (FAIT) + heal câblé

**Le blocage (RE)** : `unitAbilityTypes` énumérait via `ActiveAbilityComponent.GetActives()`, qui
**filtre par `IsActiveAbility(type@0x44)`** → RATE les actives **granted-par-trigger** comme le heal
du passif `TwistedScience` (`TwistedScienceAbility` triggered → grant `TwistedScience_HealAbility`
1167, type hors enum « active »). Mesuré : `GetActives(u92)` = [69,1166] aux steps 0 ET 1, alors que
`abilityTargets(1167)` rend ok+2 cibles (l'ability EST castable via `GetOrNull`, juste pas listée).

**Le fix (hook, livré + reinject + validé)** : `GetActives` et `GetUnusedAbilities` itèrent la MÊME
collection `+0x20` ; `GetActives` filtre par type, `GetUnusedAbilities` par le flag `unused@0x28` →
inclut les granted. Ajout d'un **pass `GetUnusedAbilities`** dans `unitAbilityTypes` (internals.ts,
`getUnusedAbilitiesMi`) qui complète la liste avec les abilities castables manquantes (kind=`granted`).
→ `decisionView.abilities(u92)` rend désormais `(1167,'Heal_TwistedScience','granted',usable)`.
Bénéfice large : les granted deviennent visibles pour le moteur ET l'oracle/decisionView.

**Heal câblé bout-en-bout** (`engine_validate`, branche HEAL avant le summon) : énumère les abilities
`name~Heal`, cibles UNIT via `abilityTargets`, score = soin prédit (`aiPredict.healthDmgMax` = magnitude
de soin — le prédicteur réutilise les champs dmg). Règle de tir : si AUCUNE attaque, soigne la cible au
plus gros soin. **Résultat : le moteur CAST le heal au step1 (ability 1167 MATCH)** — sans régression
(seed777 55/77/75 %, seed2024 44/61/100 % inchangés ; le heal ne tire que sans attaque dispo).

**Précision de la CIBLE (88 vs 94) — RÉSOLU, ability 100 %.** Le chemin (et mes 2 erreurs de mesure) :
- **Erreur 1 (faction)** : supposé faction-15 = Custodes → FAUX. `dump.cs` : `UnitFaction.Genestealers=15`
  (Custodes=18, BlackTemplars=6). NI u88 NI u94 n'est Genestealers → CustomUtility ÉGALE (base 100).
- **Erreur 2 (magnitude)** : mon `aiPredict` appelle **`GetAllPredictions`** (query de DÉGÂT), PAS
  `PredictHeal`. Sur un heal il renvoyait `2429`/`3036` = **bruit**. La vraie fonction (lue ghidra)
  `DamagePrediction.PredictHeal` = `MaxFillUp(target, healAmount)` = **cappé à `maxHP − currentHP`**.
- **Ground truth (mesuré)** : au step1, u88 ET u94 sont à **PV PLEINS** (`hp==hpMax`, missing=0) → soin
  effectif = `min(healAmount,0)` = **0 pour les deux**. Le cast ne restaure rien : il sert à poser le
  **buff `TwistedScience_ExtraHp`**. Struct `ProbableHealEvent` (`dump.cs`) : `[0x10]=Probability` (=1) ;
  la magnitude est dans `HealPrediction@0x8`. Donc utilité ∝ soin effectif (0 ici) → 88/94 **à égalité**.
- **Fix (scoreur remplacé)** : score = `CalculateCustomUtility` fidèle = `base 100 + (100 si cible
  Genestealers/faction-15) + soin effectif (missing HP via observeBattle)`, **gaté à 0 si la cible a
  déjà `TwistedScience_ExtraHp`**, tie-break **id croissant** (ordre natif). `aiPredict.healthDmgMax`
  SUPPRIMÉ du heal (mauvaise query). → step1 pick **u88** (égalité custom+missing → id 88 < 94) = MATCH.

**Résultat : ability 50 %→75 %→100 % (4/4) seed777 ; seed2024 100 % inchangé ; positioning 55/77.**
