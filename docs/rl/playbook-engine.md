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

## 13. Phase 2c — architecture native DÉFINITIVE du scoring + sélection (RE complète, ground truth)

> Déclencheur : « on veut juste répliquer » + « pourquoi tu utilises pas ghidra ? ». Toute cette section
> est **lue dans ghidra (gqfc5mff6c), pas mesurée**. La mesure d'utilités ne sert PAS à répliquer un
> argmax (transformation monotone ⇒ même argmax) ; on **réimplémente les fonctions natives**. La mesure
> ne reste qu'un filet pour lever une ambiguïté de décompilation.

### 13.1 Le scoreur unifié `ComparablePlaybook.CalculateActionUtility` (@181406ee0)

Toute action comparable (attaque / heal / effet / bannière) est scorée par **UNE seule** fonction, en
**UNE seule devise** Fix64 :

```
U(action) = CalculateUtilityFromPredictions(action)              # Σ dégât + Σ heal + Σ effet + Σ repair
          + [si gate caster-pos] Weight[54].Eval(casterBase)     # terme position du caster (secondaire)
          + CalculateUtilityFromTilePrediction(action)           # utilité de la TUILE d'arrivée (Weight[Tile=7])
```

`CalculateUtilityFromPredictions` (@181407890) somme, par famille de prédiction :
- **Dégât** : `Σ proba × Weight[Damage=34].Eval(UtilityAttackCase.ForDamagePrediction(ev))`
- **Heal** : `Σ Probability × Weight[Heal=44].Eval(UtilityAttackCase.ForHealPrediction(tgt, healPred))`
- **Effet** : `Σ proba × Weight[AddedTileEffects=45].Eval(ForEffect(0x2d))`  (+ une 2ᵉ passe `× proba`)
- **Repair** : `Σ Weight[Repair=46].Eval(ForRepairPrediction(0x2e))`

⚠ Les `UtilityAttackCase.For*` (@181104fb0/181105420/181105260) **ne sont PAS les scoreurs** : ce sont des
**constructeurs** (`memset 200o` + alloc + remplissage de champs) d'un objet `UtilityAttackCase` portant
les inputs. Le score réel = `Weight_k.Evaluate(caseObj)` via les helpers gshared
`FUN_180006940(…, playbook.weights@0x40, k)` (récupère le poids d'index `k`) puis `FUN_180003bd0(5, …)`
(invoke `Evaluate`). `Weight_k` = une **config Utility nommée** de `BattleConfiguration.Utilities.Default`.

### 13.2 `UtilityType` → poids (indices lus dans le décompilé)

`Damage=34 · KillUnit=36 · OverkillUnit=37 · DamageDealt=35 · Tile=7 · Heal=44 · AddedTileEffects=45 ·
Repair=46`. **`Damage` est COMPOSÉE** (cf. 13.3) : son `Eval` = somme de ses sous-utilités (dont
KillUnit/OverkillUnit configurées + DamageDealt magnitude). ⇒ mon barème kill 50/100 capturait une
*partie* de Damage, mais ratait **DamageDealt (dégât brut)** et **toute la branche effet/AoE**.

BC `Utilities.Default` (54 catégories, **toutes non-null**) — clés clés présentes : `KillUnit
{PossibleKill 50, DefinitelyKill 100}`, `OverkillUnit {Possible 15, Definite 40}`, `AddedTileEffects
{SpiderWeb 10, Fire 10, Ice 5, Unit_on_* 15/15/0}`, `AttackTargetWithEffect {ArmourOfShriekingSouls 20}`,
`Elevation {HighestElevation 10, LowestElevation −5, Multiplier 10}`, `MinDistanceToClosestEnemy
{PerTileDistance −100}`, `MaxDistanceToUnitTile {ClosestTile 400, FarthestTile 700}`, `MaxDistanceToEnemies
{ClosestEnemy 10, FarthestEnemy 100}`. **`Damage`/`DamageDealt`/`Heal`/`Tile`/`Repair` = ABSENTES** du
dict (clés inexistantes) ⇒ leur `IUtility` est un comportement par défaut/hardcodé (pas de courbe BC) —
typiquement une magnitude (dégât/soin brut) ⇒ **échelle native ≈ PV/dégât brut**, ce qui domine le
barème kill (50/100). `aiPredict` = **GetAllPredictions = query de DÉGÂT seulement** (pas d'effets/heal ;
même mur que le heal §11/12) ⇒ scorer fidèlement une ability à EFFET offline est **bloqué à la source de
prédiction**.

### 13.3 `_composedUtilityLookup` — `UtilitiesDatabase.InitializeUtilities` (@1810C9390, lu EN ENTIER)

Deux dicts construits : `_composedUtilityLookup` (7 composites → tableau d'enfants) puis
`_utilitiesBuilder` (**70 builders** `UtilityType → classe *Utility`, registre complet). Composites :

| Composite | → enfants (UtilityType) |
|---|---|
| **MovementSuggestion(32)** | **[Tile(7), TileDistance(33)]** |
| Tile(7) | tableau statique **29 éléments** (blob `InitializeArray`) |
| UnitMovement(6) | [Tile(7), MinDistanceToClosestEnemy(16)] |
| **UnitMovementFromTemporary(5)** | [UnitMovement(6), **MaxDistanceToUnitTile(17)**] |
| Damage(34) | tableau statique **13 éléments** |
| Repair(46) | [3 éléments] |
| Spawn(0) | [Tile(7), SingleAdjacency(1)] |

**Conséquence #1 (tranche le point bloquant Phase 2a)** : `MaxDistanceToUnitTile(17)` (le terme 400/700,
gaté OFF dans `move.py`) n'est **PAS** dans `MovementSuggestion` — uniquement dans
`UnitMovementFromTemporary`. Donc le défaut `off` est **CONFIRMÉ par ghidra**, pas un coup de chance A/B :
le move pur n'utilise jamais ce terme.

**Conséquence #2** : le décideur de move pur = **Tile(7)[29] + TileDistance(33)**. Le set exact des 29
sous-utilités Tile reste le **seul datum non extrait** : c'est un blob int32 statique référencé par
`RuntimeHelpers.InitializeArray(arr, DAT_1831c7a48)` ; `read_bytes` au DAT rend un **token de métadonnée**,
pas les ints. À résoudre via la metadata Il2CppDumper (script.json / field default-value) ou une micro-lecture
Frida runtime du champ — PAS via `read_bytes` du DAT.

### 13.4 Sélection = bucket-tree `Bucket.ChooseAction` (@1813fc0d0) + gate `FUN_18004cc80`

```
ChooseAction(bucket):
  si feasible(bucket.defaultAction):  return bucket.defaultAction          # action par défaut prioritaire
  sinon: enfant = ChooseActionFromBuckets(bucket.children triés)           # SortedList par clé/priorité
         return feasible(enfant) ? enfant : null
```

`ChooseActionFromBuckets` (@1813fbe00) : itère la **SortedList** d'enfants en ordre de clé, renvoie la
**1ʳᵉ** action faisable (récursivement). Gate `FUN_18004cc80(bucket, action, ctx)` :

```
feasible(action) = action != null
                && ( bucket.minUtilityDifference absent  OU  action.Utility >= bucket.minUtilityDifference )
```

**Où le seuil est CONFIGURÉ (RE complète, redirige le plan)** : config = `IdunBattleLogic.AI.Utilities`
`UtilityDefinition{ UtilityBucket[] }` → `UtilityBucket{ WeightedUtility[] Utilities, bool
RejectAllNoneBestCases, Fix64 MinUtilityDifference@0x20 }`. Les ctors `UtilityBucket(UtilityType,
Nullable<Fix64> minUtilityDifference)` (@180e432b0, concret) ne sont appelés en nombre que par
**`DefaultGroupOperator..ctor` (@181183dc0)** — qui construit **8 buckets EN ORDRE** :

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

⇒ **ce décideur à seuils est le `PickNextUnit` (ORDONNANCEMENT des unités), PAS le décideur d'action.**
C'est la définition authoritative de l'ordre de jeu des unités (cf. mémoire UnitOrder/PickNextUnit) :
priorité summons → non-boss → fraîchement-spawn (chacun gate util≥1) → UnitOrder (garde le meilleur) →
… → reste.

**Conséquence pour les 4 misses (steps 11/12/17/20 = natif MOVE / moteur ATTAQUE) — le plan CHANGE** :
le harnais compare déjà la MÊME unité (`activatedUnitId`) ⇒ l'ordonnancement d'unité n'est PAS la cause.
Et le tree d'**action par-unité** est bâti dynamiquement par `CreateBucket`/`GetOrCreateBucket` (@1813fc170/
1813fc550) qui créent des buckets **SANS seuil** (gate `FUN_18004cc80` → `return 1` quand le Nullable est
absent ⇒ toujours faisable). Donc « attaque-vs-move » par-unité ne se joue **PAS** sur un
`minUtilityDifference` ; il se joue sur (a) la **clé de CATÉGORIE** d'action (ordre SortedList) et/ou
(b) l'**utilité unifiée** (la meilleure action d'une catégorie = sa defaultAction). Prochaine couche RE =
l'émission des actions playbook dans les buckets (la **catégorie** assignée à move vs attack via
`GenerateAction`) + savoir si la sélection finale est argmax-utilité ou priorité-de-catégorie.

### 13.6 Sélection d'action par-unité = argmax-UTILITÉ unifiée (RE terminée — le vrai correctif des 4 misses)

- **`Bucket.AddAction` (@1813fbcc0)** : dans un bucket, `defaultAction` = l'action de **plus haute
  utilité** passant le gate (`if action.Utility > default.Utility: default = action`, `op_GreaterThan`).
  ⇒ **argmax-utilité dans une catégorie**.
- **`Bucket.AddActionToBucket` (@1813fbb60)** : range l'action dans un sous-bucket par **catégorie**
  (SortedList key=param_2), créé sans seuil ; argmax dedans. **`ChooseAction`** descend les catégories
  en ordre de clé, 1ʳᵉ faisable.
- **`DefaultAiUnitTactic..ctor` (@1810eebc0)** : la liste des générateurs = `GetDefaultActiveAbility
  ActionGenerators()` **PUIS `MovementActionGenerator` AJOUTÉ EN DERNIER** (field@0x58, list@0x60).
  Tactics : Default / OnlyMove / Random / BossSkipActiveAbility / SkipTurn (cf. TF). Générateurs :
  `ActiveAbilityActionGenerator`, `MovementActionGenerator`, `RandomAbilityActionGenerator`.

**Conclusion (réfute « priorité de catégorie » ET « seuil » pour attaque-vs-move)** : si la sélection
était une pure priorité de catégorie avec movement en DERNIER, l'attaque primerait TOUJOURS le move dès
qu'une attaque est faisable → le natif ne bougerait jamais avec une attaque dispo. Or il MOVE aux steps
11/12/17/20. Donc les actions comparables (attaque/ability/**approche-mouvement**) sont départagées par
**argmax-utilité sur la devise unifiée** (cohérent avec `AddAction` op_GreaterThan + Phase 0
« ChooseAction = argmax-among-legal »). Le natif MOVE quand `U(move) > U(meilleure attaque)`.

**Correctif moteur (défini, non bloqué par la source de prédiction)** : aujourd'hui `engine_decide`
attaque dès qu'une attaque a `util>0`, sans jamais comparer au move. Fix = **scorer move ET attaque sur
LA MÊME devise et argmax** :
- `U(attaque) = U_damage_composé (KillUnit+OverkillUnit+DamageDealt) + tile_util(tuile d'attaque)`
- `U(move)    = tile_util(tuile de move)`     (déjà calculé par `move.py` : MinDist×−100 + Σ MaxDistEnemies)
- argmax → le moteur ne s'engage dans l'attaque que si elle bat le repositionnement.
- **Point ouvert (scale)** : `tile_util` (centaines, ex. MaxDistEnemies 10/100, MinDist −100) doit être
  homogène à `U_damage` (KillUnit 50/100 + **DamageDealt brut**, magnitude inconnue car config Damage
  absente du BC → comportement défaut = dégât brut ?). C'est la SEULE inconnue numérique restante ;
  à caler par l'agreement (le harnais départage) une fois `tile_util(tuile d'attaque)` ajouté au moteur.

### 13.7 Barème de dégât FIDÈLE (RE'd — répond au « scale », pas de knob) + ce qui reste bloqué

> Déclencheur : tentative de caler le scale par un knob `_MVA_DMG_SCALE` → **devinette** (rejetée par le
> user « t'es encore en train de deviner »). La réponse correcte = LIRE le barème, ci-dessous.

`DamageDealt` (UtilityType 35) = `IdunBattle.AI.Utilities.DamageUtility`. `.cctor` (@1810cf2e0) pose 2
constantes statiques : **`W_damage = Fix64(0x50) = 80`**, **`W_remaining = Fix64(0x14) = 20`**. Formule
(`<EvaluateAttackInSteps>d__2.MoveNext` @1810e2280) :

```
dmg         = Avg(healthMinMax) + Avg(shieldMinMax)            # dégât moyen prédit (santé + bouclier)
combinedMax = (target.MaxHealth + 1) + (target.Shield + 1)     # boss : MaxHealth→169
u_damage    = Clamp(dmg / combinedMax, 0, 1) × 80              # FRACTION des PV max × 80
u_remaining = (1 − Clamp((remaining − dmg) / combinedMax, 0, 1)) × 20   # finir les blessés
u           = u_damage + u_remaining ;  ×(−1) si friendly-fire (cible = ami)
```

⇒ le terme dégât est une **fraction [0,1] des PV max × 80** (≈ [0,100] pour une cible pleine), **PAS des
milliers bruts** — même ordre de grandeur que `KillUnit` (50/100). Donc un kill DOMINE naturellement
(KillUnit 100 + DamageDealt ≈ 100 sur la cible tuée), sans aucun facteur ad-hoc. `KillUnitUtility`
(@1810e1a90) : `+GetUtilityValue(WillBeKill→DefinitelyKill 100 / MightBeKill→PossibleKill 50)`, ×(−1) si
friendly-fire. `OverkillUnitUtility` (@1810e1ed0) : `+DefinitelyOverkill 40 / PossibleOverkill 15`
(ADDITIONNÉ — sous réserve du signe/poids du composite, cf. ci-dessous).

**Ce qui reste BLOQUÉ (extraction des arrays statiques)** — empêche un barème 100 % fidèle :
- L'**assemblage du composite `Damage(34)`** = tableau statique de **13** `UtilityType` (+ les poids/signes
  `WeightedUtility.Weight` par feuille). On connaît 3 feuilles (DamageDealt 80/20, KillUnit, Overkill),
  pas les 10 autres ni les signes (ex. Overkill réellement `+` ou pénalité `−` ?).
- Le composite **`Tile(7)` = 29 él** (idem) dont dépend `tile_util` fidèle.
- Ces 2 blobs sont des `RuntimeHelpers.InitializeArray(arr, DAT)` ; `read_bytes(DAT)` rend un **token de
  métadonnée**, pas les ints. À extraire via la metadata Il2CppDumper (field default-value / script.json)
  ou une **micro-lecture Frida runtime** de `_composedUtilityLookup[Damage]`/`[Tile]` (lecture d'une
  STRUCTURE de config, pas d'une utilité — légitime, pas une devinette).

**Statut moteur** : `_MVA_DMG_SCALE` (knob) SUPPRIMÉ. Gate `ENGINE_MOVE_VS_ATTACK` laissé OFF + marqué
NON FIDÈLE (utilise `best[0]`, pas le composite Damage). Comportement par défaut INCHANGÉ (55/77 / 100 %).
Prochaine étape réelle = extraire les 2 arrays (composite), porter `DamageUtility` fidèle dans
`engine/utility.py`, puis activer la comparaison move-vs-attack sur une devise homogène.

### 13.8 Composition des composites — LECTURE RUNTIME (ground truth, le « quoi chercher » résolu)

> `read_bytes` du DAT ne décode pas les blobs `InitializeArray` (token de métadonnée). Lu donc à
> l'exécution : nouveau RPC `dumpComposedUtility` (`frida/hooks/features/dump-composed.ts`) capture la
> `UtilitiesDatabase` via `DefaultGroupOperator..ctor` arg[4] puis walk `_composedUtilityLookup`
> (offset résolu par nom = **88=0x58**, conforme dump.cs ; `Dictionary<UtilityType, UtilityType[]>`).
> Session 8, runner seed 777. **C'est une lecture de STRUCTURE de config, pas une utilité — légitime.**

```
Damage(34) [13] = OnlyImperviousUnitIfCanBeDamaged(40) · DamageDealt(35) · KillUnit(36) · DislikeObjects(38)
                · DislikeBoss(43) · DislikeEnvironmentUnits(39) · OverkillUnit(37) · EnemyOnTerritoryTile(41)
                · TriggeredAbilities(2) · TriggeredAbilitiesNonOwner(4) · UnitSpecificBehaviours(3)
                · OptimizedGait_AdjacentFriends(59) · AttackTargetWithEffect(42)
Tile(7) [29]    = Elevation(8) · TemporaryTile(13) · TileEffects(9) · UnitEffectsAdjacent(10)
                · UnitEffectsSurrounding(11) · UnitEffectsRanged(12) · RangedAdjacentEnemy(15) · SteppableUnit(19)
                · CapturePoint(24) · TriggeredAbilities(2) · TriggeredAbilitiesNonOwner(4) · UnitSpecificBehaviours(3)
                · KustomForceField(20) · DefenderOfTheGreaterGood(21) · SaviorProtocols(22) · TilePendingBlockableSummon(14)
                · PowerUp(26) · DoctrinaImperatives(57) · Phantasm(60) · EchoesFromTheWarp(58) · Contaminated(25)
                · MoltenForm(23) · BioMinefield(61) · MasterOfTheTutelaries(62) · DecoysAndMisdirection(64)
                · DespoiledGround(28) · SummonDislikeDoorOpening(29) · HeroLikeDoorOpening(30) · EnvEndBombardment(31)
Repair(46) [3]  = RepairedAmount(47) · TriggeredAbilities(2) · TriggeredAbilitiesNonOwner(4)
Spawn(0) [2]    = Tile(7) · SingleAdjacency(1)
MovementSuggestion(32) [2] = Tile(7) · TileDistance(33)
UnitMovement(6) [2]        = Tile(7) · MinDistanceToClosestEnemy(16)
UnitMovementFromTemporary(5) [2] = UnitMovement(6) · MaxDistanceToUnitTile(17)
```

**Décodage** :
- **Damage** : dominants = `DamageDealt(80/20) + KillUnit(100/50) + OverkillUnit(40/15)` (RE'd §13.7) ; les
  10 autres = modificateurs SITUATIONNELS, poids BC connus (`DislikeBoss 80`, `DislikeObjects 50`,
  `AttackTargetWithEffect 20`, `EnemyOnTerritoryTile 10`, `OnlyImpervious`=gate, knobs traits Triggered/
  UnitSpecific) → 0 sur une attaque basique d'unité. Donc le barème « 3 feuilles » est une bonne 1ʳᵉ coupe.
- **Tile(7) ne contient AUCUNE distance.** Les distances sont des leaves séparées :
  `UnitMovement = Tile + MinDist(16)`, `UnitMovementFromTemporary = UnitMovement + MaxDistToUnitTile(17)`.
  **`MaxDistanceToEnemies(18)` n'est dans AUCUN composite** (leaf standalone, decider spécifique). ⇒ mon
  `move.py` (MinDist + MaxDistEnemies) est un PROXY : MinDist ✓, MaxDistEnemies à tort, et il rate tout le
  composite Tile(7) (dont Elevation, TileEffects…). 55/77 = chance que MinDist domine la direction ici.

### 13.9 Plan de portage des leaf-utilities (le « ré-implémenter les utilities »)

La composition runtime donne la LISTE EXACTE des feuilles à porter → `engine/utilities/` (une fn par
UtilityType, depuis son `*Utility.<Evaluate*InSteps>d__N.MoveNext` ghidra + poids BC). Statut RE :
- **PORTÉ + VALIDÉ (défaut)** : composite **Damage(34)** dominant (`engine/utilities/damage.py`) =
  `DamageDealt(35, 80/20) + KillUnit(36, 100/50) + OverkillUnit(36, 40/15 ADDITIONNÉ)`. Branché
  `engine_validate` (`ENGINE_DAMAGE_MODEL=faithful` par défaut ; `legacy` = ancien barème deviné pour A/B).
  maxHP cible via observeBattle (clé squadId). **Bug trouvé PAR MESURE (DEBUG, pas deviné)** : `kill`/
  `killSure` (WillBeKill/MightBeKill) sont au niveau RÉSULTAT d'`aiPredict`, PAS dans `pred` → KillUnit ne
  voyait jamais le kill (u84 kill garanti hp=dmax=1147 non scoré → perdait contre u80). Fix = ré-injecter
  `kill`/`killSure` dans `pred`. **Résultat : parité legacy sur 777 (60/80/100) + 2024 (45/65/100), zéro
  régression — barème FIDÈLE remplace le deviné.** ⚠ TODO : dégât BOUCLIER (Avg(shieldMinMax), non exposé
  par aiPredict) ; 10 leaves situationnels du composite (DislikeBoss/Objects/Env, AttackTargetWithEffect…).
- **RE'd, à porter dans `utilities/`** : MaxDistanceToUnitTile(17, `700-300/d` réf=tuile courante), MinDist(16),
  MaxDistEnemies(18), RangedAdjacentEnemy(15, -50 si ranged+adjacent) [dans move.py].
- **Tile(7) PORTÉ (formules) — `engine/utilities/tile.py`** : registry des 29 feuilles. RE'd+portées :
  **Elevation(8)** = `Multiplier(10)×elev + HighestElevation(10 si max) + LowestElevation(-5 si min)`
  (`ElevationUtility.<d__8>` @1811019a0) ; **SteppableUnit(19)** = poids selon summon/decoy × ami/ennemi
  (Enemy 50 / Friendly -50 / FriendlyDecoy -50 / EnemyDecoy 1, `<d__10>` @1810f9850) ; **TileEffects(9)**
  partiel = Σ poids BC des effets de statut sur la tuile (`<d__1>` @1810fbe50). Les 26 autres = STUBS=0
  (situationnels : trait/effet/terrain ; =0 sur bataille basique, fidèle). ⚠ **DÉPENDANCE DONNÉE** :
  les leaves consomment une METADATA PAR TUILE (`{elevation, elevation_max/min, effects[], steppable}`)
  qu'AUCUN RPC n'expose (`aiMovableTiles`/`decisionView` = col/row seuls). ⇒ PLUMBING requis (enrichir
  un RPC tuile avec élévation/effets/occupant) AVANT de pouvoir évaluer/valider Tile(7). Sans données,
  `tile_composite` rend ≈0 (correct en plat, mais inexploitable pour l'agreement).
- **PLUMBING ÉLÉVATION FAIT + VALIDÉ** : nouveau RPC **`tileMeta`** (`rpc-view.ts`) =
  `projectMatchState(state,{includeTiles:true}).tiles` → `[{col,row,elevation,isWall,isTemporary,
  isTerritory}]` (TileComponent). Build+reinjecté session 10. Bataille seed-777 a du RELIEF (élévation
  1-4, distribution variée). **E2E validé** : `tileMeta → tile_composite` ; pour u88, tuiles élev=2 → 15
  (`10×2−5`, min), tuile élev=3 → 40 (`10×3+10`, max). Elevation produit des valeurs différenciées par
  tuile. (Occupant steppable + effets de tuile = dérivables/à enrichir ensuite ; élévation = la donnée
  clé pour le move scoring, faite.) **NEXT** : intégrer `tile_composite` au scoring de move (décideur =
  Tile + MinDist, virer MaxDistEnemies hors-composite), trancher le décideur (UnitMovement vs
  MovementSuggestion) par l'agreement.

### 13.10 Intégration `tile_composite` au move scoring — A/B (décideur à trancher)

`move.best_move_faithful` = **UnitMovement(6) = Tile(7) + MinDist(16)** (composition runtime §13.8) :
`U = tile_composite(Elevation + situationnels) + wMin×min_d`, SANS MaxDistEnemies (hors composite).
Branché `engine_validate` (`ENGINE_MOVE_MODEL` : `proxy` défaut / `unitmovement` fidèle), élévation via
`tileMeta` (1×/décision). **A/B seed 777** :

| modèle | positioning | ability |
|---|---|---|
| `proxy` (MinDist + MaxDistEnemies) | **60 % / 80 %** | 100 % |
| `unitmovement` (Tile(7) + MinDist) | 55 % / 75 % | 100 % |

**Finding (honnête, pas une régression — le fidèle reste GATÉ, proxy défaut)** : le modèle fidèle
UnitMovement(6) est SOUS le proxy. Comme Tile(7) ≈ Elevation seul ici (les 26 situationnels = 0), ça se
réduit à `Elevation + MinDist` vs `MaxDistEnemies + MinDist` → **le terme `MaxDistEnemies` (spread)
corrèle mieux au move natif que `Elevation`**, alors qu'il n'est dans AUCUN composite. ⇒ le décideur du
move pur n'est probablement PAS UnitMovement(6). Hypothèses : (a) c'est `MovementSuggestion(32)` =
Tile + **TileDistance(33)** (TileDistance non RE'd — pourrait jouer le rôle de spread) ; (b) le
`MovementActionGenerator` utilise `MaxDistanceToEnemies(18)` en LEAF STANDALONE (hors composite) ;
(c) Tile(7) a besoin de plus de leaves portées. **À RE** : `MovementActionGenerator.GenerateActions`
(quel `UtilityDecider`/composite il applique aux move-actions) + `TileDistanceUtility`. C'est la clé pour
trancher le décideur — l'agreement départagera une fois le bon composite identifié.

### 13.11 Décideur de move — TRANCHÉ par RE (`MovementActionGenerator`)

`MovementActionGenerator.<GenerateActions>d__6.MoveNext` (@181199d50) construit son décideur :
`utilDef = new UtilityDefinition((TileExtensions.IsTemporary(mainTile) ^ 1) + 5)` ⇒ tuile NORMALE
(isTemp=0) → `(0^1)+5 = 6` = **UnitMovement(6) = Tile(7) + MinDist(16)** ; tuile TEMPORAIRE → `(1^1)+5 = 5`
= **UnitMovementFromTemporary(5) = UnitMovement + MaxDistanceToUnitTile(17)**. Score chaque tuile candidate
via ce décideur (UtilityMovementCase, FindClosestEnemy en référence) → argmax. **CONFIRME : le move pur =
`Tile(7) + MinDist` — `MaxDistanceToEnemies(18)` n'y est PAS.** `TileDistanceUtility(33)` =
`DistanceTo(case, tuile-réf)`, utilisé par `MovementSuggestion(32)` = mécanisme DIFFÉRENT (non pertinent).

**Diagnostic (A/B seed 777)** : MinDist-seul (`ENGINE_TILE_OFF=1`) = **55/75** = IDENTIQUE à
Tile(Elevation)+MinDist → Elevation ne change pas l'argmax ici (MinDist domine). Proxy = 60/80. ⇒ tout
l'écart vient de `MaxDistEnemies` (NON-natif) ; il score +5% **par coïncidence** (mon Tile(7) incomplet =
Elevation seul ; MaxDistEnemies corrèle avec la contribution Tile(7) manquante). **Structure fidèle
CONFIRMÉE** ; défaut reste `proxy` (60/80, meilleur tant que Tile(7) incomplet, mais NON-fidèle). Combler
les 5% = compléter les leaves Tile(7) non-nuls ici (SteppableUnit si summons, UnitEffects*, traits) →
plomber effets/occupation par tuile + RE par leaf. MaxDistToUnitTile(17) RE'd, à activer pour moves
depuis tuile temporaire (UnitMovementFromTemporary).

### 13.12 La VRAIE divergence du move = distance CHEMIN, pas hex (RE MinDist)

Vérif empirique d'abord : la bataille seed-777 n'a **AUCUN summon** (10 unités = roster exact) et les
effets présents (InescapableAccuracy, RangedSpecialist, Terrifying…) **ne matchent AUCUN trigger** des
leaves UnitEffects (InfernalPacts/HunterOfSouls/FirstAmongTraitors/VexillaImperius/PathOfCommand/
DaughterOfTheAbyss). ⇒ **les leaves Tile(7) non-portées sont TOUTES à 0 ici** — les porter ne change pas
l'agreement de CETTE bataille. Le gap 5% vient d'ailleurs.

RE `MinDistanceToClosestEnemyUtility.<d__2>.MoveNext` (@1810fe690) + `GetMinDistanceToEnemy` (@1810f04a0) :
```
u = 0
if target(=closest enemy) == null OR IsNonAttacking(target) OR !UnitCanBeDamaged(target): return 0
d = GetMinDistanceToEnemy(movingUnit, evalTile, target)        # Nullable<int>
u = FromInt(d) × GetUtilityValue(PerTileDistance = -100)       # = -100 × d
```
**`GetMinDistanceToEnemy` = `IterateTiles(target)` × PATHFINDER (`path.Length@0x18`), min sur les tuiles
occupées par l'ennemi** — c'est une **distance de CHEMIN** (contourne murs/obstacles), PAS la distance hex.
Mon `move.py`/`best_move_faithful` utilise `hexgeo.distance` (hex straight-line). ⇒ **divergence réelle =
path-distance vs hex-distance** : quand le chemin se courbe (relief/obstacles), l'argmax diverge (45% de
mismatch). Le proxy (hex aussi) diverge pareil ; `MaxDistEnemies` compense par coïncidence. Le coefficient
(-100) et la forme `-100×d` SONT corrects ; seule la MÉTRIQUE de distance est fausse (hex au lieu de chemin).
+ 2 gates : MinDist=0 si l'ennemi le plus proche est NonAttacking / non-damageable.

**Conséquence (redirige le plan)** : compléter Tile(7) ne ferme PAS le gap ici (leaves=0). Le levier réel
= **une source de distance-CHEMIN** par tuile candidate vers l'ennemi le plus proche (RPC pathfinder, ou
distance-chemin offline depuis la carte d'obstacles). C'est ça qu'il faut plomber, pas les effets de tuile.

### 13.13 RPC pathfinder + intégration — le fidèle DÉPASSE le proxy (move résolu)

Nouveau RPC **`pathDistToEnemies`** (`rpc-view.ts`) : pour `unitId`, distance de CHEMIN MIN de chaque
tuile atteignable vers une tuile ennemie. Implémentation = `Pathfinders.GetPath(type=1, unit, from, to,
Nullable<UseTeleporter>=null)` (overload 5-param @180f20190, comme `GetMinDistanceToEnemy`) → `List<IEntity>`,
`Count@0x18` = longueur du chemin. Accès : `runner.<Pathfinders>k__BackingField` (PAS `_pathfinders` =
le Dict interne) ; GetPath résolu lazy depuis la classe runtime de l'instance. **Pièges résolus** : (1)
mauvais champ runner (`_pathfinders`→`<Pathfinders>k__BackingField`) ; (2) overload 4-param (dérive le
type) rendait `null` → 5-param avec **type=1** explicite marche (`len=11`, path≠hex sur 10/10 tuiles).

`move.best_move_faithful` consomme `pathdist_by_pos` (sinon fallback hex). `engine_validate`
`ENGINE_MOVE_MODEL=unitmovement` (DÉFAUT) fetch tileMeta + pathDistToEnemies 1×/unité.

**A/B (le path remplace hex) — le fidèle DÉPASSE le proxy sur les 2 seeds** :

| seed | proxy (hex MinDist+MaxDistEnemies) | unitmovement hex | **unitmovement PATH (fidèle, défaut)** |
|---|---|---|---|
| 777  | 60 / 80 | 55 / 75 | **65 / 80** |
| 2024 | 45 / 65 | — | **55 / 75** |

ability **100 %** partout. ⇒ **move pur RÉSOLU fidèlement** : décideur UnitMovement(6) = Tile(7) +
MinDist sur distance-CHEMIN. La distance-chemin (vs hex) était la pièce manquante ; le proxy
(MaxDistEnemies) n'était qu'un placeholder coïncidentel, maintenant battu par le modèle natif RE'd.
`unitmovement` passé en DÉFAUT. (Cleanup : champ `dbg` diagnostic du RPC `pathDistToEnemies` retiré
— rebuild OK ; prend effet au prochain reinject.)
- **Leaves Tile(7) restantes → portées fidèle (§13.14).**
- **Sélecteur de decider** : confirmer lequel pilote le « move pur » du harnais (UnitMovement(6) vs
  MovementSuggestion(32) vs UnitMovementFromTemporary(5)) — détermine si MinDist/MaxDistToUnitTile
  s'appliquent. À trancher par l'agreement une fois Tile(7) porté.

### 13.14 Port FIDÈLE des leaves Tile(7) restantes (RE ghidra + clés BC réelles)

RE complète (ghidra gqfc5mff6c, fan-out d'agents sur les `*Utility.<EvaluateMovementInSteps>d__N.MoveNext`)
+ clés de poids lues dans `data/arena-battle-config-newtonsoft.json` (`Utilities.Default.<EnumName>` —
le nom de catégorie BC == le nom du membre `UtilityType`). Les string-keys de poids ne sont PAS
résolvables depuis la DLL (elles vivent dans `global-metadata.dat`) → on les prend dans la BC.

**Mécanisme commun** : chaque leaf `u=Fix64(0)` ; gate (effet/trait/ability/flag-tuile) ; si gate
passe `u += GetUtilityValue(this,<clé>)` (poids BC) éventuellement × constante ; sinon 0. `GetUtilityValue`
= lookup string-key dans le dict de poids `this+0x58` (peuplé depuis la BC).

| leaf (id) | gate (ids hex/déc) | formule + poids BC réel |
|---|---|---|
| TemporaryTile(13) | tuile `isTemporary` | **-10000** (constante, pas BC) — **ACTIVE** |
| CapturePoint(24) | tuile territoire (tile+0x2e) + flag trait 2/13 | flag→`summons_dislike_capture_points`(-300) sinon `heroes_on_capture_points`(+300) |
| PowerUp(26) | occupant `IsPowerUp` + flag trait 2/13 | `summons_dislike_tiles_with_powerups`(-300) |
| Contaminated(25) | tile-effect 1244(0x4dc) + non-exclu | `AffectedUnit`(-25) |
| MoltenForm(23) | trigger 1221(0x4c5) + effet tuile 5/10 | `MoltenForm_ResistFireTiles`(+25, eff5) / `MoltenForm_AvoidHealingTiles`(-25, eff10) |
| TilePendingBlockableSummon(14) | summon en attente type 1094(0x446) | `EnemySummon`(+25)/`FriendlySummon`(-25) **par** entrée |
| EnvEndBombardment(31) | tuile ciblée effet 1359(0x54f)/1360(0x550) | `EnvEndBombardment_TileToAvoid`(-30), ×2 si 1360 |
| DespoiledGround(28) | tile-effect 1476(0x5c4) + trait 2026 / 26\|1006 | `ChaosAffectedUnit`(-5) / `ImperialAndXenosAffectedUnit`(-25) |
| SummonDislikeDoorOpening(29) | affected (AI \| human+trait2) + porte fermée | `Dislike`(-50) |
| HeroLikeDoorOpening(30) | hero (trait 16/0x10) | **hardcodé** : -50 si sur porte fermée (mode A) ; (10-coûtChemin)×10 (mode B) |
| Phantasm(60) | tuile effet 1279(0x4ff) + phantasme ami adj | `Phantasm_AvoidFriendlyPhantasm`(-40) |
| EchoesFromTheWarp(58) | tuile owner effet 1284(0x504) + ghost ami adj | `GhostTile`(+10) |
| DoctrinaImperatives/AttractMechanicals(57) | trait 5 + voisin active-ability 1118(0x45e) | `Marshal_AttractMechanicals`(+10) |
| DecoysAndMisdirection/AttractToDecoys(64) | faction 15(0xf) + steppable(trait27) non-ennemi | `DecoysAndMisdirection_FriendlyGSCLikeDecoys`(+75) **par** ami trigger 1304(0x518) |
| KustomForceField(20) | base `ATriggeredAbilityUtility` (count×poids) | +20 × count(amis adj R1 ability 1102/0x44e) |
| DefenderOfTheGreaterGood(21) | gate unité arme-à-distance | +25 × count(amis R1, R2 si faction9, ability 1155/0x483) |
| SaviorProtocols(22) | gate unité faction9 & !ability1120 | +20 × count(amis adj R1 ability 1120/0x460) |
| BioMinefield(61) | cible ability/effet 1315(0x523) | **-100 × hexdist**(candidate, cible) |
| MasterOfTheTutelaries(62) | cible 1096(0x448), trait 2026\|1019 | **-20 × hexdist**(candidate, cible) |
| UnitEffects Adjacent/Surrounding/Ranged(10/11/12) | amis voisinage R1/R1/R2 (`AdjacentFriends`/`SurroundingFriends r1/r2`) | Σ poids[`EffectType.ToString()`] sur leurs effets (clés dynamiques = noms d'effets) |
| RangedAdjacentEnemy(15) | — | =0 dans Default (clé `HasAdjacentEnemy` absente) |
| TriggeredAbilities(2)/NonOwner(4)/UnitSpecificBehaviours(3) | — | **dispatchers** : `LoadPlaybook(unitId)` / `LoadPlaybookNonOwner(abilityId)` / `LoadPlaybook(behaviourId)`, Σ des playbooks par-ability → **moteur Playbook séparé**, pas un simple terme de tuile |

**Implémentation** : `engine/utilities/tile.py` — chaque leaf lit un contrat `meta` (par-tuile) / `ctx`
(par-unité) documenté en tête de module ; **DORMANTES** (rendent 0) tant que la metadata par-tuile/trait
n'est pas plombée — c'est la dégradation native exacte. Validé OFFLINE : 26/26 formules = valeurs BC
attendues ; `tile_composite` à meta vide → 0 (aucune régression par construction). Plumbing actuel :
`is_temporary` (→ TemporaryTile ACTIVE) via `tileMeta`. **Suite (plumbing prioritaire par feature)** :
exposer is_territory/tile-effect-type-ids/occupant/door/pending-summons/voisinages-amis + traits/
abilities/faction de l'unité pour activer les leaves correspondantes. **Re-vérif LIVE (session 16) :
RÉGRESSION NULLE PROUVÉE** — seed-777 a 0 tuile temporaire/territoire (tileMeta) → TemporaryTile (seule
leaf active) inerte → scoring move byte-identique à l'avant-port. seed-777 = 72% exact / 90% ≤1hex /
ability 100% (reproductible) ; seed-2024 = 70% exact / 90% ≤1hex.

### 13.5 Bilan portage — ce qui est bloqué / la suite

- **Acquis ghidra-authoritative** : scoreur unifié (13.1), mapping poids (13.2), composition (13.3),
  sélection bucket-tree + gate (13.4). `move.py` mode `off` justifié par ghidra.
- **Bloqué à la source** : scorer fidèlement les abilities à EFFET/heal offline tant qu'on n'a que
  `aiPredict`=GetAllPredictions (dégât-only). Débloquer = un RPC de prédiction complet
  (damage+heal+effets, comme `GetAllPredictions` natif rend déjà les 3 familles côté moteur).
- **Non extrait** : tableaux statiques Tile(29)/Damage(13) (13.3) → metadata, pas `read_bytes`.
- **Prochaine couche** : seuils `minUtilityDifference` + construction bucket-tree (13.4) — le vrai
  correctif « attaque-vs-move » des 4 misses.
