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

- `engine_validate.py` : sur N états (rejoués depuis les démos `logs/selfplay/` OU
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
          + Weight[54].Eval(casterBase)                          # CORRECTION: 54 = WireweaveNet_FirstAttack
                                                                 #   (dump.cs), PAS "position caster". Gate:
                                                                 #   cible adjacente + cible a l'effet 1111
                                                                 #   -> 0 sinon (cf. architecture.md 2.3quater)
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

## 14. Subsystem Playbook — `PlaybookDatabase` + playbooks par-ability (RE ghidra gqfc5mff6c)

RE complète (fan-out d'agents ghidra) du **second étage** de l'IA, sous le scorer Utilities : la couche
de décision **par-ability**. Les leaves Tile `TriggeredAbilities(2)`/`NonOwner(4)`/`UnitSpecificBehaviours(3)`
y délèguent (§13.14) : elles chargent un playbook via `PlaybookDatabase`, énumèrent son
`Calculate{Movement,Attack,Repair}UtilityInSteps` et **somment** les Fix64 rendus.

### 14.1 `PlaybookDatabase` = factory+cache paresseuse (`..ctor` @1810e0380)
- ctor reçoit **11 services injectés** (champs 0x10–0x60 : match-state, battle-query, registres
  ability/config, config Utilities, RNG — identités non toutes résolues) qu'il **forwarde dans CHAQUE
  playbook construit**. La DB est sans état décisionnel : pure factory ; tout l'état vit dans les refs.
- **4 registres paresseux**, chacun = une map `(int → builder Func)` + un cache `(int → instance)` ;
  peuplés à la 1ʳᵉ `Load`. Pattern uniforme : `cache.TryGetValue → builder.TryGetValue →
  builder.Invoke(slot 0x18) → wrap-ctor (forward 0x10–0x60) → cache.Add` :

  | champ map/cache | clé | overload | rôle |
  |---|---|---|---|
  | 0x68 / 0x70 | AbilityType id | `LoadPlaybook(int,bool)` @1810e0090 | **active-ability** (218 entrées) ; +fallback DEFAULT |
  | 0x78 / 0x80 | (param. par la clé) | `LoadDefaultActiveAbilityPlaybook` @1810df810 | builder par défaut (1 délégué) |
  | 0x88 / 0x90 | id (unit/type) | `LoadPlaybook(int)` @1810dfd10 | owner/unit (104 entrées) ; wrap 1-arg |
  | 0x98 / 0xa0 | ability id | `LoadPlaybookNonOwner` @1810df9a0 | **non-owner**, SÉPARÉ (25), init-via-interface |
  | 0xa8 / 0xb0 | behaviour {0,1,2,3} | `LoadPlaybook(int)` @1810dfed0 | unit-specific behaviour (4) |

  `HasNonOwnerPlaybook` @1810d0250 = `ContainsKey(0x98)`. **351 registrations** au total
  (218+104+25+4) dans `InitializePlaybookBuilders` @1810d02b0.

### 14.2 Catalogue (`InitializePlaybookBuilders` @1810d02b0 — ~62 KB, 351 `Add`)
- Chaque registration = `dict.Add(<keyImm32>, <lambda b__31_N>)` ; **clé = valeur enum AbilityType**
  (17/18 = normal-attack génériques ; bloc contigu **1000–1230** = abilities par-personnage ; outliers
  1152, 1182, 1220, 9007). Chaque lambda = factory singleton paresseuse → `new <X>Playbook(...)`.
- Namespaces : `Playbook.Common.*` (génériques : `DefaultActiveAbilityPlaybook` = fallback, `HealPlaybook`,
  `RepairPlaybook`), `Playbook.Idun.*` (`NormalAttackPlaybook`, `GetOverHerePlaybook`), `Playbook.Loki.*`
  (par-personnage : StormOfFlensingBlades, MortisRound, MightOfHeroes, PrecisionShot_Aim/Attack,
  MultiThreatEliminator, FragBomb, …). Join clé↔classe complet = décompiler chaque `b__31_N`
  (mécanique, ~1 ctor chacun ; différé — l'ordre de registration == ordre des lambdas par map).

### 14.3 Interface playbook (hiérarchie générique)
`Playbook<T>` → `TriggeredAbilityPlaybook<T>` → `TriggeredAbilityNonOwnerPlaybook<T>` ; sœur non-triggered
`BasePlaybook`. Méthodes : `Calculate{Movement,Attack,Repair}UtilityInSteps` → **`IEnumerable<Fix64>`**
(state-machines `d__N` ; `get_Current` boxe le Fix64 @iter+0x18). `GetUtilityValue(key)` →
`Dictionary<string,int>.TryGetValue` (défaut **0** + warn) lifté en Fix64. + `GenerateAction`,
`ShouldEvaluate`/`Evaluate`, `GetAbilityState`. **Contrat de yield : un seul Fix64 par (ability, case)** =
l'utilité totale de l'ability, sommée par le dispatcher Tile.

### 14.4 Playbook représentatif — `Loki.SaviorProtocolsPlaybook` (base `TriggeredAbilityPlaybook<T>`)
ctor pose l'ability id **0x460 (1120)**. Deux scorers :
- **ATTACK** (`d__5.MoveNext` @18118ff00) : gate `HasEffect(target, 0x462 (1122) marker)` → `+weight[KEY_A]`. 1 yield.
- **MOVEMENT** (`d__4.MoveNext` @181195b10) : énumère les **alliés près de la tuile caster** (query 0x79) ;
  par candidat valide (`TargetIsValidTrigger` : `AreFriends` + `HasFaction(9)` + `NOT casterHasAbility(1120)`
  + `target≠self`) → `+weight[KEY_M1]`, et `+weight[KEY_M2]` si le caster est le parent/owner du candidat.
  Somme sur les candidats → 1 yield. `FilterMovementTiles` @181188150 élague (melee only ; ranged skip)
  les tuiles aux seules d'où le trigger peut partir (adjacence à un allié protégeable).

### 14.5 Modèle générique à porter
`score(case) = Σ_{candidat énuméré} [ gate(candidat) ? Σ weightKeys_applicables(candidat) : 0 ]`, avec
`weight = playbookWeights[key]` (int, défaut 0) → Fix64. **Par-ability = uniquement** (a) le gate
(effet/trait/faction/adjacence + ids), (b) l'énumération (quel ensemble cibles/tuiles), (c) les clés de
poids + l'arithmétique. Tout le reste (scaffolding itérateur, GetUtilityValue, layout source) est dans la base.

### 14.6 Ce qu'il faut pour porter le subsystem
1. **Registry** : map AbilityType id → playbook (351 entrées ; join clé↔classe à finir en décompilant les `b__31_N`).
2. **Scaffolding de base** + le contrat 1-Fix64/case.
3. **Par-ability** : porter gate+énumération+clés (uniforme ; ~351 abilities = longue traîne, portable
   incrémentalement — commencer par les communes : NormalAttack/Heal/Repair/Default puis les abilities
   réellement présentes dans les batailles ciblées).
4. **POIDS de playbook = EXTRACTIBLES OFFLINE** (correction d'une claim erronée antérieure « capture
   live requise »). Pipeline : décompile → `DAT_<VA>` passé à `GetUtilityValue` → RVA = VA-0x180000000
   → `data/dumps/<hash>/stringliteral.json` → clé string → valeur dans `Utilities.Default.<catégorie>`.
   Outil : `scripts/python/playbook_keys.py`. **Vérifié SaviorProtocols** : `0x18325a560`→
   `SAVIORPROTOCOLS_MarkedTarget`=60 ; `0x18325a2e0`→`SAVIORPROTOCOLS_AdjacentTauFriend`=20 ;
   `0x18325a420`→`SAVIORPROTOCOLS_AdjacentTauParent`=30. Les poids playbook vivent dans
   `Utilities.Default.TriggeredAbilities` (owner, ~107 clés) / `TriggeredAbilitiesNonOwner` (~24) /
   `UnitSpecificBehaviours` (~3) / `ActiveAbilities` (~18), sous des clés `<ABILITY>_<Condition>` (PAS
   sous le nom de l'ability). Plus généralement **TOUT `DAT_` métadonnée** (string/type/méthode/champ)
   est résoluble via `stringliteral.json` + `script.json` (ScriptMetadata/ScriptMethod) → RE EXACTE sans
   inférence ; seuls les globals mutables runtime (gardes cctor `init-once`) n'ont pas de valeur statique.
5. **Prédiction non-dégât** (heal/repair/effets) reste bloquée par `aiPredict` dégât-only (§13.5) — c'est
   le SEUL vrai prérequis live restant pour le port complet.

### 14.7 Playbooks COMMUNS = le scorer générique (découverte qui dé-risque le port)

RE des 4 playbooks à plus forte couverture (Default/NormalAttack/Heal/Repair) → **ils ne sont PAS des
playbooks bespoke à clés-strings**. Ce sont des sous-classes MINCES de
`ComparablePlaybook<T> → Playbook<T>` qui héritent du **scorer générique partagé**
`ComparablePlaybook<T>.CalculateActionUtility` @181406ee0 — **identique au §13.1** :

    score(action) = CustomUtility(hook)
                  + CalculateUtilityFromPredictions @181407890   # Σ dégât/soin/effet/repair events,
                        #   dégât = (prédDmg × mult) × GetUtilityValue(ForDamagePrediction, idx 0x22=Damage34)
                        #   soin  = HealRatio × GetUtilityValue(ForHealPrediction, idx 5 -> Heal44)
                        #   effet = ForEffect (idx 5) × magnitude ;  repair = ForRepairPrediction (idx 6 -> Repair46)
                  + UtilityAttackCase.Base (idx 0x36 = 54)
                  + CalculateUtilityFromTilePrediction @181408740  # positional/move (Tile7, idx 8)

=> le calcul **prédiction->utilité** est le **PIPELINE PARTAGÉ** (= engine/utility.py + utilities/{damage,
tile}.py, via les utilités COMPOSÉES Damage34/Heal44/Repair46/AddedTileEffects45/Tile7 déjà portées),
**PAS du code par-playbook**. Les GetUtilityValue ici sont des génériques GetUtilityValue<TCase>
sélectionnés par INDEX (0x22/5/6/8/0x36), pas des clés-strings -> **aucune nouvelle clé BC à résoudre**
pour les communs.

Chaque playbook commun n'override QUE : (a) le **tag** d'ability (ctor) ; (b) ShouldExecute (gate) ;
(c) CalculateCustomUtility (constante) ; (d) Make{Damage,Heal,Repair}Predictions (fournisseur).

| playbook | base | tag | ShouldExecute (gate) | CustomUtility | scoring |
|---|---|---|---|---|---|
| **DefaultActiveAbilityPlaybook** | BasePlaybook | per-id | ability usable | - | **flat 1.5 / cible éligible** (zéro prédiction/poids) - ENTIÈREMENT porté |
| **NormalAttackPlaybook** | ComparablePlaybook<T> | 0x11(17) | !HasTriggeredAbility(0x48=72) ET dispo | **+1** | dégât = pipeline (Damage34 = damage.py) |
| **HealPlaybook** | ComparablePlaybook<T> | 0x12(18) | heal>0 ET non(boss self-heal) | 0 | HealRatio × Heal44 (montant bloqué) |
| **RepairPlaybook** | ComparablePlaybook<T> | 0x1c(28) | off-cooldown | 0 | Repair46 additif (montant bloqué) |

ATTENTION **Soin/Repair montant** : Heal = StatAmount(weapon)×max(WeaponHighestHits,1) clampé HP-manquant
-> HealRatio=min(1, usefulHeal/predHeal) ; Repair = prédiction (classe IBattleQuery idx 0x29, sœur du
heal idx 0x28). aiPredict est dégât-only -> ces montants restent **BLOQUÉS** (cf. §13.5) ; gates/tags/
custom portés, le scoring soin/repair s'active avec un RPC de prédiction complet.

**Implication (dé-risque le port)** : le **cœur générique** (CalculateActionUtility) que je construis déjà
EST le moteur des abilities COMMUNES (= la grande majorité des actions). Le dégât marche (damage.py) ;
soin/repair ne manquent que la prédiction. Les playbooks **bespoke** (Loki.*, SaviorProtocols...) sont des
**ajouts incrémentaux à clés-strings** (résolus offline via playbook_keys.py) par-dessus ce cœur.

**Port** : engine/playbook/common.py (NormalAttack/Heal/Repair/Default + fallback get_playbook_or_default),
base étendue (should_execute/custom_utility). Validé OFFLINE (19/19 : registry 17/18/28/1120, fallback,
gates, custom +1, Default 1.5).

## 15. Prédiction OFFLINE = données gameconfig + scenario-math (le DSL n'est PAS requis)

Question : « les formules DSL sont-elles extractibles ? » Réponse après RE :

- **Le DSL (`IdunBattle.DSL.*` / `Entities.Formulas.*`) est un vrai langage d'expression, mais ses
  PROGRAMMES (arbres de formule) sont du C# (construits en code), PAS des données sérialisées** —
  `gameconfig-abilities.json` n'a aucun `$type`/nœud `*Formula`. `StatAmountFormula.Calculate`
  (@180f22d40) ne stocke qu'un **statId** (ctor @180f230f0, param_1+0x18) et fait
  `Σ UnitExtensions.GetStat(unit, statId)` → **le DSL ne fait que LIRE des stats**.
- **MAIS on n'a pas besoin du DSL** : ses SORTIES résolues sont déjà des données par niveau dans
  gameconfig (`AbilityConfigDto`) : `variables` = `minDmg/maxDmg/hpToHeal/hpToRepair/extraDmg/
  pierceRatio/…[niveau]` ; `constants` = `nrOfHits/nrOfTargets/damageProfile/armorReduction/
  HealPercentage/…`. C'est EXACTEMENT ce que `GetStat` renvoie. Le « désérialiseur » = `AbilityConfigDto`.
- Les CONSTANTES de combat sont aussi des données : `BC.Damage` = `ArmorPercentage 50, ElevationBonus 50,
  ClassBonus 25, AffinityBonus 50, DamageSpreadPercentage 20, RangedInMeleeReduction -50,
  TrenchReduction -50, OverkillDmgPctOfHealth 100, DamageProfiles[p].PiercingDamageRatio`.

**Pipeline de prédiction offline (sans DSL)** :
1. **montants** = gameconfig `variables[clé][niveau]` + `constants` (data ; soin/repair inclus → débloque
   Heal/Repair des playbooks communs §14.7).
2. **scenario-math** = `DamagePrediction.PredictAttackRaw` @181032fb0 → `CalculateDamagePredictionScenario`
   @18102ed00 (cœur RE'd : `max(0, rawDmg − armor)` − réduction par cible (FillUpStat) → cap trait
   (`MaxReduceByMinimum`) → `MinMaxDamage.ApplyCap`). Armor = `GetStat(target, 0x19=25)`. Scenario
   appelé 2× (min/max). Bonus Elevation/Class/Affinity + pierce par `damageProfile` = constantes
   `BC.Damage`. (Assemblage complet = **lu EN ENTIER**, cf. §16.)
3. **validation** = `aiPredict` (live) comme ORACLE : predict offline vs live par scénario, corriger les
   modificateurs (buffs/effets) au fil des écarts. Méthodo agreement-driven.

⇒ Le chantier « prédiction offline » se réduit à un **lecteur de données gameconfig** + une **petite
scenario-math** validée contre l'oracle — PAS un interpréteur DSL. Étape suivante : `engine/predict.py`
(montants data + scenario-math) + harnais `predict vs aiPredict` sur seed-777.

## 16. `PredictAttackRaw` @181032fb0 — RE LECTURE INTÉGRALE (cœur prédiction, 2026-06-27)

Fonction lue **en entier** (3037 lignes décompilées) + 3 helpers scalaires décompilés. C'est LE noyau où
convergent les 3 chemins de prédiction (aiPredict / combatSnapshot / le scorer). ~80 % du décompilé =
bruit de la convention *generic-struct* (recopies `do/while` du scenario 0xc8 o, cctor amorce, alloca).

**Signature** : `PredictAttackRaw(state param_2, Scenario* param_3) → DamagePredictionResult* param_1`.
- `param_3` = struct-valeur ~0xc8 o (25 qwords) = **AttackScenario** : [10]=target, [0xb]=damage(Nullable),
  [0xc]=DamageProfile, +0x84=armorOverride(Nullable), +0x7c=autre Nullable, byte flags dans [0xd]/[0x17].
- `param_2` : +0x20=match/registry, +0x40=attacker entity, +0x10=rules, +0x48/0x50=services.
- `param_1` (out, 0xc0) offsets confirmés : 0x58 `AccurateHealthDamage` MinMax(Min@0x60,Max@0x64) ;
  0x88 `TotalDamage` MinMax(Min@0x90,Max@0x94) ; 0x50 List<ProbableDamageEvent> (1 Add/coup) ;
  0x98 List<HitDamage> ; 0xb1 `MightCrit` ; 0xb3 HasFlag(0x13) ; 0xbc `AppliedHits`.

### 16.1 Pipeline (ordre exact)
1. `base = max(0, scenario.damage)` ; écrasé par variable d'ability `maxDmg`(id 0xd) si présente.
2. **MinMax base** `local_938` : flag spread=0 → point `{base,base}` ; sinon `GetBaseDamageFix64(base, isMaxOut)`
   = **spread ±`DamageSpreadPercentage`(20 %)** (confirme u92 : base 2530 → 2024/3036). Plancher `minDmg`.
3. **Armure** : `armorOverride = scenario.+0x84 ?? 0` ; `armorMM` = piercing par bout ;
   `postArmor = {base.min−armor.min, base.max−armor.max}`.
4. **Bonus plat** = variable d'ability `0xe` (ajouté identiquement aux 2 bouts).
5. **Tous modificateurs** → `local_8c8` = `CalculateBaseDamageWithAllModifiers(postArmor.min+bonus)` et
   `…(postArmor.max+bonus)` (cf. §16.3). Plancher minDmg + `MathMax`. Puis `ApplyTraitDamageLimitsToDamage`.
6. **BOUCLE MULTI-COUP** @2390 (LE point qui manquait) :
   - `perHitList = service.<slot0>(attacker)` (dispatch interface `FUN_1800053f0`, **Count(+0x18) = nrOfHits**,
     chaque élément 8 o `{lo32=hitDmg, hi32=critChance%}`).
   - si `DamageProfile.HasTrait(0)` → SKIP la boucle. `remaining = Fix64(1)`.
   - `for i in range(Count)` : `w = remaining × (critChance%/100)` ;
     `ev = CalculateDamagePredictionScenario(dmgMM=local_8c8, armorMM, prevHits=cumul, prob=w×100)` (§16.2) ;
     `result.events.Add(ev)` ; `remaining ×= (1 − w)`.
7. **Outcome dominant** (proba `remaining`) → `CalculateDamagePredictionScenario(prevHits=0)` → `param_1[3..9]`.
8. `TotalDamage`(0x88) = postArmor + armure absorbée ; `MightCrit`(0xb1) via vtable IsCrit(attacker) ;
   `AppliedHits`(0xbc)=nrOfHits ; conversions Nullable→MinMax→`ApplyCap` pour [0xb]/[0xd]/[0xf].

### 16.2 `CalculateDamagePredictionScenario` @18102ed00 (le cœur par-outcome — PETIT, à porter tel quel)
`(out, state, target3, comp4, dmgMM*, armorMM*, prevHits u32, prob% u32, outBool*)` :
```
eff.min = max(0, Fix64(dmgMM.min) − Fix64(prevHits))      # dmgMM @+0x10=min, @+0x18=max
eff.max = max(0, Fix64(dmgMM.max) − Fix64(prevHits))
shieldAbs = absorbShield(eff)                             # interface slot 0xb (FUN_1800068b0)
healthDmg = max(0, eff − shieldAbs)
if target.FillUpStatComponent: healthDmg = FillUpStatComponent.MaxReduceByMinimum(healthDmg) → out overkill
return { +0=prob%, +4=healthDmg MinMax(ApplyCap), +0x14=shieldAbs MinMax, +0x24=armorMM MinMax }
```
⇒ `prevHits` (param_7) = **previousHitsPrediction** : chaque coup retire le dégât cumulé → ne compte que
sur la santé restante. C'est la chaîne multi-coup (explique les plages larges, ex. u80 4 hits 2136-6416).

### 16.3 `CalculateBaseDamageWithAllModifiers` @18102d3f0
`(state, rawInt, target, comp, p5, critA Nullable, critB Nullable, flag8, flag9)` :
```
d = GetBaseDamageWithFixedPiercedArmor(state, Fix64(raw), critA.f0, critB.f0, target, comp, p5,
                                       flag8, flag9, critA.f8 + critB.f8)        # @181030d10 (déjà RE)
if critA: d = applyModif(slot 0x11, critA)   ; if critB: d = applyModif(slot 0x11, critB)   # FUN_180031890
if critA: d = applyModif(slot 0x10, critA.f8); if critB: d = applyModif(slot 0x10, critB.f8) # FUN_18000c030
if critB (+ sous-cond): d = critB.Value (override)
return d
```
⇒ crit/profil = modificateurs interface (slots 0x10/0x11) appliqués DÉTERMINISTE sur min ET max.

### 16.4 Conséquences pour le port (fidèle)
- **Portable tel quel maintenant** : `CalculateDamagePredictionScenario` (§16.2, petit & exact) +
  l'ossature boucle multi-coup (§16.1.6). À mettre dans `engine/services/damage_prediction.py`
  (`get_attack_prediction` → vraie boucle per-hit) + `engine/playbook/comparable_playbook.py`.
- **À calibrer vs aiPredict** (les feuilles dont je n'ai pas le scalaire exact) : `perHitList`
  (contenu hitDmg/critChance par coup — dispatch interface, source service non identifiée), les
  slots crit 0x10/0x11, `absorbShield`/`FillUpStat.MaxReduceByMinimum`. Live = CONFIRMATION, pas source.
- **Blast/multi-membres = AU-DESSUS** (`GenerateMultiHitAttackPredictions` @181409da0 itère les membres
  → rappelle ce noyau par membre). Pas dans `PredictAttackRaw`. Reste l'axe (b).
- Détail brut + corps décompilés : working-notes `predict_attack_raw_algo.md` (scratchpad session).

### 16.5 Énigme « enveloppe large » RÉSOLUE via ghidra (2026-06-27 — fns nommées, pas l'inline)
Sonde live seed-777 : **crit/block/members = 0/0/1 PARTOUT** → ni crit, ni block, ni Blast. La largeur
(u80 2136-6416 ratio 3.0, u86 2.7 ; vs u92/u96 ratio 1.5=spread) vient de DEUX leaves combinées :
- `CalculateBaseDamageWithModifiers`@1810021c0 = `Round(base × modifier)`. modifier = `DamageModifiers`
  (additif@+0x10, mult@+0x30=One, %list@+0x18 ; `Empty`@181006370 + `Add`@181005f10/ea0). Construit par
  `Calculate{Attacker,Defender}ModifiersForPrediction`@181000590/@181002c30 (élévation via GetMainTile,
  effet 0x423, classe/affinité). **TARGET-dépendant → monte le HAUT.**
- `GetBaseDamageFix64`@181030ba0 = `{base−spread, base+spread+ExtraMaxDamage(25)}` (extraMax = asymétrie
  HAUT, attaquant) puis `GetDamageWithPiercing`@1815598b0 = `max(max(0,bout−armure), bout×pierce%/100)`
  PAR BOUT (perçage=PLANCHER). **Quand l'armure cible mord, écrase le BAS au plancher perçage.**
⇒ **min↓ (plancher perçage, armure cible) + max↑ (modifier ×, monte tout) = élargissement asymétrique
target-dépendant, SANS crit/block.** u92/u96 target-indépendants = perçage HAUT (armure ne mord jamais
→ largeur = spread pur). pierceRatio (GetBaseDamageWithFixedPiercedArmor@181030d10) = `clamp(0..100,
GetPiercingRatio(profile,traits)+ExtraPierce(26)+ExtraPierce{Melee21/Ranged22})` ; armorEff =
`max(FixedArmor(16)−pen,0)` ; hitMult 1/2(trait 1013)/3(ability 0x4b6).
**PORTÉ** (`engine/services/damage_prediction.py`, NON commité) : `get_base_damage_fix64` (asym extraMax)
+ `get_attack_prediction(modifier, extra_max, pierce_pct, armor, hit_mult)` = chaîne base×modifier →
{∓spread, +extraMax} → GetDamageWithPiercing par bout → ×hits. Défauts (modifier1/armor0/pierce100/
extraMax0) = rétro-compat exact (u92 2024-3036, u96 2122-3182). Smoke : asym mod1.5/pierce30/armor900 →
ratio 2.67 (mécanisme prouvé).

> ⚠ **§16.5 partiellement CORRIGÉ par §17** : (1) le `modifier` (DamageModifiers) ne s'applique PAS sur
> la base avant spread — il s'applique **par coup, APRÈS perçage/armure** (`ApplyCappedModifiers`,
> preuve numérique exacte §17.2). (2) Source = **effets de bonus de dégât actifs** (pas affinité/classe ;
> il n'y a PAS d'affinité/classe dans le dégât de combat — cf. §17.1). (3) L'« enveloppe large » d'u90
> (≠ u94) vient de `PowerTrip_IgnoreArmor` (axe armure dans `PredictAttackRaw`, pas le modifier).

## 17. Couche MODIFIER — RE intégrale + confirmation live (2026-06-27, fns nommées)

Objectif : fermer le gap d'exactitude restant (≠ 8/11). Mesure live seed-777 (confirmation, pas fitting) :
`xmod = oracle/offline` → **u94 ×1.25**, **u90 ×2.83** ; les 8 autres ×1.00 (chaîne base×hits+pierce+armure
déjà exacte). Identités live : u94=`templChampion` (effet `RapidAssault_ExtraDamage` actif),
u90=`orksKillaKan` (effet `PowerTrip_IgnoreArmor` actif). ⇒ **DEUX axes distincts.**

### 17.1 Le modifier (`DamageModifiers`) — structure RE'd
- **`DamageModifiers` (accumulateur)** : `additif`@+0x10 (Fix64), `%-list`@+0x18 (`List<{mult,cap}>`),
  `mult`@+0x30 (Fix64=One), `detail-list`@+0x38. `Empty`@181006370 ; `Add`@181005f10.
  `Add(acc, entry, extraNullable)` : `additif += FromInt(entry.DamageBonus)` (+5) ; `additif -=
  FromInt(entry.DamageReduction)` (+6) ; si `entry[+9]` → `%-list.Add(1 + round(v/100*100)/100)`.
- **Construction** : `Calculate{Attacker,Defender}ModifiersForPrediction`@181000590/@181002c30 itèrent
  les effets/abilities de l'unité + `CalculateModifiersFromStatModifications`@181004380, et pour chaque
  appellent `GetDamageBonusForAttack` (slots 0x16/0x17/0x18) → un `DamageBonus` (Nullable) →
  `GetMultiplierFromDamageBonus`@181005210 → `Add`. **Pas d'affinité/classe** (GrandAlliance.GetTrait
  ne fait que mapper alliance→trait ; l'affinité est UI/méta, jamais dans le dégât de combat).
- **`GetMultiplierFromDamageBonus(b)`** = `1 + b/100` si `b≥1`, sinon `1 − |b|/100` (Fix64).
- **Réducteur = `ApplyCappedModifiers`@181000020** `(acc, value)` : POUR CHAQUE entrée `{mult,cap}` de la
  `%-list` : `value = Clamp(Round(value × mult, 1), −cap, +cap)`. (Le `additif`/`mult` plat se composent
  à part ; `CalculateBaseDamageWithModifiers`@1810021c0 = `Round(base×mod)` clamp `≤0→0`, `<1→1`.)
- **Leaves positionnels** (chacun = un `DamageModifier` singulier, kind@+0 + Nullable@+0x20) :
  - **Élévation** `CalculateElevationBonusModifier`@181003ea0 : si tile attaquant **plus haut** que tile
    cible → `+ElevationPercentage`(config). Sauté si attaquant **ou** cible a effet `0x423`.
  - **Ranged-in-melee** `CalculateRangedInMeleeReduction`@181004700 → `ShouldApplyRangedInMelee`@181005810 :
    attaquant trait `0xb` (Ranged) adjacent à un ennemi melee-able → `−RangedInMeleeReduction`(config).
  - **Trench** `CalculateTrenchReduction`@181004830 : cible sur tuile trench + adjacence → `−TrenchReduction`.

### 17.2 Placement = APRÈS perçage, PAR COUP (preuve numérique, branche-distinguante)
Le modifier est **absent de `PredictAttackRaw`** (grep) → appliqué par la chaîne appelante au résultat.
Preuve (u94, ×1.25, vs DEUX cibles d'armure différente) :
- u94→u84 (armure 1806) : per-coup non-modifié `[803,1206]` × 1.25 = `[1004,1508]` ×3 = **3012-4524 = oracle EXACT**
- u94→u86 (armure 2008) : per-coup non-modifié `[803,1205]` × 1.25 = `[1004,1506]` ×3 = **3012-4518 = oracle EXACT**
La différence d'armure bascule la branche max (`dmg−armure` 1206 vs plancher `dmg×40%` 1205) et ×1.25
reproduit les DEUX à l'unité. Le modifier-sur-base donnerait 5877/5880 (faux). ⇒ **post-perçage par coup.**

### 17.3 Source du bonus = effet par-unité (pas de playbook — c'est un triggered+effect)
`RapidAssault` = **trait** → `RapidAssaultAbility` (triggered, pose l'effet) + `RapidAssault_ExtraDamageEffect`
(porte le bonus) + `RapidAssault_Remove*EffectAbility` (le retire). **Aucun playbook** (les playbooks sont
pour les abilities actives que l'IA *choisit*). Le bonus entre par :
`RapidAssault_ExtraDamageEffect.CreateEffectDamageBonusForAttack`@180f67940 :
```
extraDmgPct = DSLFactory.ConfigConst(effect, 0xf, ...)              # constante config idx 0xf
bonus       = EffectBonus.ForPercentIncrease(ownerIsCaster, extraDmgPct)   # DamageBonus +pct%
return Nullable(bonus)
```
⇒ magnitude = **constante de config de l'ability/trait** (ici extraDmgPct, live=25), wrap `ForPercentIncrease`.
Conditionnel : RapidAssault = « 1re attaque du combat + attaques suivantes du même tour » → actif quand
l'IA prédit (1re attaque) ; **confirmé par la présence de l'effet `RapidAssault_ExtraDamage` au live.**

### 17.4 ⚠ Effet-NOM ≠ bonus appliqué (garde-fou, ré-confirme la règle EFFECT RECON)
u88 `custoVexilusPraetor` porte `StandVigil_ExtraDmg` + `MartialKatah_DmgBonus` **et matche modifier=1.0**.
Donc un effet nommé « DmgBonus » N'IMPLIQUE PAS un bonus appliqué (inactif, ou pour l'ability active
seulement, ou c'est un ExtraMaxDamage). ⇒ porter via **statut-actif + magnitude recalculée**, JAMAIS le nom.

### 17.5 Axe SÉPARÉ — ignore-armure (u90, n'est PAS le modifier)
u90 `PowerTrip_IgnoreArmor` : enveloppe oracle 2048-7592 (ratio 3.7×, min×1.85≠max×3.30 → pas un scalaire).
= le flag `HasTrait 0x420(1056) / HasEffect 0x59a(1434)` de `PredictAttackRaw` step 10 (ignore-armure/
true-dmg), conditionnel (min=armure s'applique, max=ignorée). À porter dans l'axe **perçage/armure** de
`get_attack_prediction`, pas dans `DamageModifiers`.

### 17.6 Plan de port (fidèle, recalcul depuis entrées)
- `engine/services/damage_modifiers.py` : `DamageModifiers` (Empty/Add) + `get_multiplier_from_damage_bonus`
  + `apply_capped_modifiers(value, mods)` + leaves élévation/ranged-in-melee/trench. **Structure 1:1.**
- Par-effet `create_effect_damage_bonus_for_attack` : pattern dominant `ForPercentIncrease(ConfigConst)`
  (couvre RapidAssault + probablement la majorité) → mapping effet→(ability/trait, config-const-idx).
- **Entrées** : effets ACTIFS captés (decisionView.effects, statut live) × magnitude gameconfig
  (constante de config) ; positions/tiles pour élévation/trench/ranged-in-melee ; flag ignore-armure
  (trait/effet) pour l'axe armure (u90).
- **Câblage** dans `get_attack_prediction` : `value_per_hit = apply_capped_modifiers(value_post_pierce, mods)`
  (PAS sur la base). Valide via `predict_validate.py` (cible ×mod≈1.00 sur u94).

### 17.7 Intégration TRACÉE EN LIVE (hook `modifier-observe`, 2026-06-27) — CORRIGE §17.2
Hook d'observation read-only (`frida/hooks/features/modifier-observe.ts`, auto-arm + RPC
`modifierObserveInstall/Status/Reset`) posé sur les 4 fns modifier + `PredictAttackRaw` +
`GetAllPredictions` ; backtraces dumpés (RVA→ghidra = `+0x180000000`). Résultat :
- **Le name-search statique était trompeur** : les 3 fns modifier + `ApplyCappedModifiers` ne sont
  référencées QUE par elles-mêmes (literal search) car **tous leurs appels passent par dispatch
  MethodInfo** (appels indirects). Mon « PredictAttackRaw n'a pas de modifier » (§17.2) était FAUX —
  basé sur un grep qui rate les appels dispatchés.
- **Chaîne live réelle** :
  `decisionView → CachedDamagePredictionQuery.GetAllPredictions (CACHE) → DamagePredictionQuery.
  GetAllPredictions → DamagePrediction.<PredictAttack>b__0 (0x181054041) → PredictAttackRaw`.
- **Dans `PredictAttackRaw` (@181032fb0)** — backtraces (offset dans la fn) :
  - `+0x18EE (0x18103489e)` → `CalculateAttackerModifiersForPrediction`
  - `+0x1E9E (0x181034e4e)` → `CalculateDefenderModifiersForPrediction`
  - `+0x2176 (0x181035126)` → `CalculateBaseDamageWithAllModifiers` (@18102d3f0)
       `→ +0x3d9 (0x18102d7c9)` → `ApplyCappedModifiers`
  Donc `ApplyCappedModifiers` est appelé DANS `CalculateBaseDamageWithAllModifiers` (après
  `GetBaseDamageWithFixedPiercedArmor` = perçage/armure) → **×bonus post-perçage par coup, confirmé
  en runtime** (= la preuve numérique §17.2, désormais localisée dans le code).
- **Le CACHE masquait le recalcul** : tant qu'aucun changement d'état, decisionView relit
  `CachedDamagePredictionQuery` (0 recompute, 0 fire). Il faut **buster le cache** (un `applyAction move`)
  pour déclencher la chaîne. ⚠ corollaire pour toute future observation de prédiction : changer l'état
  avant de mesurer, sinon on lit du cache.
- **`param_5`** (liste des sources de bonus passée au builder) = **construit dans `PredictAttackRaw`**.
  Reste à dumper son contenu (énumération live) pour figer sa composition exacte.
- **Conséquence port** : appeler les builders modifier au sein de la chaîne per-coup de
  `get_attack_prediction`, exactement comme `CalculateBaseDamageWithAllModifiers` le fait (perçage PUIS
  `apply_capped_modifiers`), nourri par `param_5` reconstruit depuis les effets actifs captés.

### 17.8 `param_5` (la liste de sources) — RE STATIQUE (ghidra, pas de live)
Décompilé de `PredictAttackRaw` (working-notes `PredictAttackRaw.c`), call sites repérés via les marqueurs
d'adresse-retour `*(puVar45-8)=0x...` (= les RVA du backtrace §17.7) :
- **Builder attaquant** : ligne 1473 `FUN_180031950(&out, 0xd, DAT_183287db8)` (trampoline dispatch,
  slot 0xd) ; args stagés lignes 1469-1471 : `+0x30=local_988` (=param_5), `+0x28=&local_748`
  (=AbilityEntities du scénario), `+0x20=state`.
- **Builder défenseur** : ligne 1796, slot `0xe`, 4 params (résout la cible via l'AbilityEntities
  `local_748` ; param_5 non utilisé).
- **Construction de `param_5`** : ligne 1239 `local_988 = FUN_180002560(9, DAT_1831b7938, <obj>)`.
  `FUN_180002560(slot, ifaceType, obj)` = **dispatch de méthode d'INTERFACE** (cherche `ifaceType` dans
  l'itable de `obj`, appelle `offset+slot`). **`DAT_1831b7938` = l'interface des EFFETS** — prouvé : même
  `DAT` que `EntityExtensions.{HasOneOfEffects,IsOwnerOfOneOfEffects,IsTargetOfOneOfEffects}`.
- ⇒ **`param_5` = la collection d'EFFETS actifs de l'unité** (slot 9 = énumérable groupé). Le builder
  l'itère (groupes/effets) → `GetDamageBonusForAttack` (= `CreateEffectDamageBonusForAttack`) par effet.
  Confirme « sources de bonus = effets actifs » (modèle 1-classe-par-effet §17.3).
- **Seule ambiguïté** : l'`obj` du slot-9 (ligne 1239) est **droppé par le décompilateur** (registre r8
  non tracké) → entité-attaquant vs service `state.+0x48` non tranché statiquement. Sans impact sur le
  port (ce sont les effets actifs de l'unité, recapturables offline via `decisionView.effects`).
- **INTERFACE MODIFIER 100% RE'd** (builder interne + param_5=effets + per-effet + placement post-perçage).

### 17.9 PORT FAIT + VALIDÉ (2026-06-27, NON commité)
Modules créés (structure 1:1 native, VA citées) :
- `engine/services/effect_bonus.py` : `EffectBonus` + fabriques `for_percent_increase/decrease/addition/
  subtraction/piercing` (@180f40xxx).
- `engine/services/damage_modifiers.py` : `DamageModifiers`(Empty/additif/%-list/mult) + `add_modifier`
  (@181005f10) + `get_multiplier_from_damage_bonus` (@181005210) + `apply_capped_modifiers` (@181000020 :
  `v=clamp(round(v×mult),±cap)`) + `apply_all_modifiers` (%-list puis additif, HYPOTHÈSE ordre) +
  `build_attacker_modifiers` (@181000590) + leaves élévation/ranged-in-melee/trench.
- `engine/services/effects_damage_bonus.py` : registre par-effet nom→fabrique (`CreateEffect*ForAttack`),
  RapidAssault posé ; `build_modifiers_from_active_effects(active, magnitudes)`.
- `get_attack_prediction` rewiré : `modifier:float` (sur la base) → `mods:DamageModifiers|None`, appliqué
  **post-perçage PAR BOUT** (`apply_all_modifiers`), None=rétro-compat.
**VALIDÉ (offline, vs nombres natifs mesurés)** : mods=None → 8 cas OK inchangés (u88 EXACT, u92 ±1,
u96 ±3=résidu Fix64). u94 RapidAssault +25% → u94→u84 **3012-4524 EXACT**, u94→u86 3012-4515 vs 4518
(±3 = résidu `//100` vs Fix64 sur la branche plancher-perçage, PAS une erreur modifier ; u84 tombe sur la
branche armure → exact). End-to-end registre : effets actifs captés (non-dmg ignorés) → mods → EXACT.
**SOURCE DES MAGNITUDES — RÉSOLUE (2026-06-27)** : `gameconfig.globalValues.traitVariables` (traits),
exposé par `gameconfig.trait(name)["variables"]` — clé = camelCase(trait)+suffixe. Confirmé :
`trait("RapidAssault").variables.rapidAssaultExtraDmgPct = 25` (= le ×1.25 mesuré live) ;
`trait("Parry").parryHitReduction = 1`. (Pour une ability : `ability(aid)["variables"/"constants"]`.)
`effects_damage_bonus.EFFECT_DAMAGE_BONUS` mappe nom-d'effet→(trait, var_key, fabrique) ; la magnitude
s'AUTO-résout depuis gameconfig (`build_modifiers_from_active_effects` sans input). End-to-end validé :
effet actif `RapidAssault_ExtraDamage` → 25 → mods → u94→u84 EXACT.
**RESTE (wiring live)** : (1) `UnitContext.active_effects` capté (decisionView.effects) ; (3)
comparable_playbook/NormalAttackAbility bâtissent `mods` depuis les effets du caster ; (4) predict_validate
construit `mods` par attaquant → u94 doit passer ×mod≈1.00 ; (5) **conditions par-effet** (§17.4) : RE le
`CreateEffectDamageBonusForAttack` des autres effets dégât du roster (HeavyWeapon/MartialKatah/StandVigil
étaient PRÉSENTS mais non-appliqués sur u88/u96 → condition interne) avant de les inscrire au registre.

### 17.10 La magnitude = DSL re-évalué par-décision depuis l'INSTANCE d'effet (RE complète) — `effects_damage_bonus` registre statique = MAUVAIS ENDROIT
Tout `*_Effect.CreateEffectDamageBonusForAttack` **construit une expression DSL** (≠ valeur figée) et la
**ré-évalue à chaque coup/prédiction** (appelé par CalculateAttackerModifiersForPrediction DANS PredictAttackRaw).
Chaîne d'évaluation RE'd :
- `EffectBonus.ForPercentIncrease/ForAddition(ownerCond, ConfigAmount)` — nœud DSL {condition, formule}.
- magnitude = `ConfigAmount` (formule paresseuse) `.Calculate` @180f171c0 → selon le nœud :
  - **const** : `AbilityConfiguration.GetNumberConstant(cfg, key)` @181576af0 = `GetStringConstant(cfg,key)`→`Int32.Parse`.
  - **var/level** : `AbilityConfiguration.GetVariableForLevel(cfg, key, level)` @181576fb0 =
    `TryGetVariableArrayForLevel(cfg, key, level)` → valeur par-niveau.
  - **`key` = un ENUM** (AbilityVariableType / clé-constante), PAS un index positionnel ; `cfg` =
    l'`AbilityConfiguration` de l'effet (via son AbilityState `effect.+0x48` → `AbilityStateFromEffect`) ;
    `level` = `effect.+0x60`.
  - effets DYNAMIQUES : méthode propre (ex. `EnmityForTheUnworthy.CurrentDamagePct`) lisant l'état courant (stacks).
- **Modèle = « remonte à la source à chaque fois »** (formule re-évaluée vs cfg+niveau+état), PAS de snapshot à la création.
**Conséquence (tranche le design)** : re-dériver offline par nom gameconfig est IMPRATICABLE — il faudrait
(a) l'enum clé→nom `AbilityVariableType` (ABSENT du dump enums.json = 7 groupes seulement) + (b) identifier
le `cfg` exact de chaque effet + (c) gérer les dynamiques. ⇒ **le bon endroit = lire les variables sur
l'INSTANCE d'effet active** (son AbilityConfiguration résout le lookup keyé nativement). C.-à-d. :
**CAPTURER par effet actif ses variables/constantes résolues** (GetVariableForLevel/GetNumberConstant au
niveau de l'effet, ou la valeur dynamique) → l'engine consomme. `engine/services/effects_damage_bonus.py`
(registre nom→variable-gameconfig statique) est donc à REMPLACER par une capture-instance (garde RapidAssault
validé comme cas-test, mais le mécanisme général = capture). ⚠ Toujours le garde-fou §17.4 (présent≠appliqué :
la CONDITION DSL `ownerCond`/triggers décide ; ne compter que les effets dont le bonus s'évalue >0 in-situ).

### 17.11 Décision design (Option A) + wiring fait — magnitude depuis gameconfig indexée par level, capture origin-agnostique (2026-06-27)
RE de clôture (ghidra, read-only) qui tranche le « comment lire l'instance » de §17.10 :
- **L'`AbilityConfiguration` n'est PAS sur l'`EffectComponent` capté.** Décompilé `EffectComponent..ctor`/
  `GetPropertiesString` : champs = OwnerId@0x14, listes@0x48/0x50/0x78, EffectType@0x58, IsActive@0x5c,
  Removed@0x5f, RemainingTurns@0x64, Level@0x68 — **aucune** réf AbilityState/AbilityConfiguration.
  L'objet `effect` de `CreateEffectDamageBonusForAttack` (avec `+0x48`=AbilityState, `+0x60`=level) est une
  **instance `*_Effect` distincte** (sous-système `param_5`), pas le composant ECS. Donc « lire la variable
  sur l'instance » = atteindre la collection `*_Effect` (param_5, propriétaire non tranché) **puis** soit
  ré-implémenter le lookup dict keyé, soit invoquer le resolver natif (`NativeFunction`) sur jeu live (risque).
- **`ConfigAmount.Calculate` @180f171c0** (resolver RE'd) : cache la cfg @node+0x10 (résolue depuis +0x40/+0x48),
  puis **constante** → `GetNumberConstant(cfg,key)` (pur, sans contexte) ; **variable** → `GetVariableForLevel
  (cfg,key,level)` (renvoie l'élément [0] du tableau per-niveau). `RapidAssault` = chemin **constante**
  (`ConfigConst(abilityState, key=0xf, level)` @180f67940).
- **PIVOT** : l'`AbilityConfiguration` n'est que le **miroir live, par-instance, de gameconfig**, indexé
  `key`+`level`. Or on capte déjà `level` (decisionView.effects). ⇒ **Option A (choisie)** : magnitude =
  gameconfig **indexée par le level capté** (= la donnée que l'instance résoudrait), read-only, zéro
  invocation native. Seuls les effets **DYNAMIQUES** (stacks) exigent une vraie lecture live (champ
  `dynamic` du registre, à brancher au cas par cas).

**`effects_damage_bonus.py` réécrit (registre fidèle 1:1 des `*_Effect`)** — `EffectDef{kind, source_type,
source_name, var_key, native_key, is_constant, cap, condition, dynamic, va}` ; résolution
`effect_bonus_for(effect, override?)` (ordre magnitude : override > dynamic(live) > gameconfig[level]) ;
builder `build_modifiers_from_active_effects(active_effects, magnitudes?)`. Registre = `RapidAssault_ExtraDamage`
(trait, key 0xf, scalaire 25). Validé : effet capté → +25% → u94→u84 **3012-4524 EXACT** (+ override + back-compat str/tuple).

**SOURCE trait ≠ ability (point user 2026-06-27)** — un effet peut être **lié à un TRAIT** (passif), pas
seulement à une active. Deux axes distincts, séparés dans le registre :
- **Capture = origin-agnostique** : `decisionView.effects` (= `ActiveEffectIds`, IsActive-filtré) liste **tous**
  les effets qui s'appliquent, quelle que soit l'origine (trait/active/triggered/environnement). « actifs » =
  *en cours d'application*, PAS « issus d'une active ». Un effet posé par un trait y est.
- **Source de la magnitude** = champ `source_type` : `trait`→`gameconfig.trait(name).variables` (scalaire,
  `traitVariables`) | `ability`→`gameconfig.ability(id).variables[level-1]`/`.constants`. **RapidAssault EST
  un effet trait-sourcé** (trait→RapidAssaultAbility pose l'effet ; magnitude dans `traitVariables`) ⇒ le cas
  **trait est le cas VALIDÉ**, pas l'exception.
- ⚠ **ANGLE MORT** : un trait qui contribue un modifier **sans poser d'effet-entité** (pure
  stat-modification / contribution directe au builder — cf. `CalculateModifiersFromStatModifications` §17.1)
  **n'apparaît pas** dans `ActiveEffectIds` → la capture par effet le rate. **Règle d'extension** : avant
  d'inscrire un effet au registre, vérifier qu'il surface bien comme effet capté ; sinon (trait modifier pur),
  passer par l'axe stat-modification (à RE/porter séparément).

**Wiring fait (offline-validé, NON commité)** : (1) `UnitContext.active_effects: list[dict]` + méthode
`attacker_modifiers()` (build depuis les effets captés ; re-évalué par-décision, non figé par from_snapshot) ;
(2) `comparable_playbook.generate_multi_hit_attack_predictions` bâtit `mods = caster.attacker_modifiers()` et
le passe à `get_attack_prediction(..., mods=mods)` ; (3) `predict_validate.py` : `effects_by_id` depuis
decisionView → `mods` par attaquant → `get_attack_prediction(mods=…)`. Empty mods = no-op exact (8 cas clean
inchangés). **RESTE (live)** : confirmer u94 → xmod≈1.00 via `predict_validate --seed 777` (re-amorce requis) ;
étendre le registre au roster (conditions §17.4 par effet) ; brancher `dynamic` au 1er effet dynamique.

**CONFIRMÉ LIVE (session 27, seed-777, 2026-06-27)** : la couche modifier (Option A) reproduit le buff in-situ.
`RapidAssault_ExtraDamage` capté (effet **trait-sourcé**) → ×1.25 post-perçage par bout → u94→u84 **3012-4524
xmod=1.00 EXACT** (était 1.25), u94→u86 ±3 (arrondi). **Agreement seed-777 : 8/11 → 10/11**. Seul miss clean
restant = **u90 xmod 2.83** = `PowerTrip_IgnoreArmor` (axe ignore-armure SÉPARÉ, pas le scalaire
DamageModifiers — §17.5). NEXT modifier : porter l'axe ignore-armure (u90, flag HasTrait 0x420/HasEffect
0x59a dans get_attack_prediction) ; étendre le registre au roster (conditions §17.4) ; brancher `dynamic`.

### 17.12 IGNORE-ARMURE = axe PÉNÉTRATION (RE complète) — §17.5 « flag asymétrique » RÉFUTÉ (2026-06-27)
RE intégrale de l'axe armure (décompilé, PAS de fitting) :
- `CalculateBaseDamageWithAllModifiers` @18102d3f0 extrait des DEUX `DamageModifiers` (attaquant+défenseur)
  deux champs : **pierce-extra** (struct @0x20) et **armor-penetration** (@0x28, sommés att+def), passés à
  `GetBaseDamageWithFixedPiercedArmor` @181030d10 → `pierce_eff = clamp(pierce+extra, 0, 100)` ;
  **`armor_eff = max(FixedArmor − penetration, 0)`**. ⇒ ignore-armure = une **pénétration d'armure**, PAS un flag.
- **§17.5 RÉFUTÉ** : grep de `PredictAttackRaw` (108K sauvé) = **0** occurrence de `HasTrait 0x420`/`HasEffect
  0x59a`/`HasEffect`/`HasTrait`. Il n'existe AUCUN flag ignore-armure dans PredictAttackRaw. L'« asymétrie
  min garde l'armure / max ignore » était une invention non lue → supprimée.
- **`DamageModifiers.Add` @181005f10** ne route QUE additif (slot 5)/soustraction (6)/percent (9 + cap 10).
  Il **ne touche pas** pierce/pénétration → ceux-ci viennent d'une **méthode d'interface par-effet dédiée**,
  pas de `CreateEffectDamageBonusForAttack`. Source confirmée : `KanOpenerEffect.IgnoreArmor` @180f65100 =
  `ConfigVar(state, key=0x40, level)` (pénétration per-niveau).
- **`PowerTrip_IgnoreArmorEffect.CreateEffectDamageBonusForAttack` @180f64fa0 = NO-OP** (EffectBonus
  condition-seule `IsNormalAttack & OwnerIsCaster & !OwnerIsTarget`, tous slots valeur vides → 0 contribution
  à DamageModifiers) ; et l'effet n'a **PAS** de méthode `IgnoreArmor` (seul KanOpener en a). ⇒ le mécanisme
  exact par lequel PowerTrip_IgnoreArmor annule l'armure reste **non tranché** (à RE : peut-être via une autre
  interface, ou l'effet n'est pas la vraie source de l'écart u90).
- **`PowerTrip_FullHealthEffect`** = axe SÉPARÉ : `CreateEffectHitsBonusForAttack` @180f64cf0 =
  `EffectBonus.ForAddition(ConfigConst(key=0x2b))` (extra HITS), gaté `CreateActiveCondition` = `!IsDamaged`
  (PV pleins). ⇒ +N coups quand l'unité est à PV pleins = MULTIPLIE le total (axe hits, pas le scalaire ni l'armure).
- **u90 NON expliqué par l'ignore-armure** : full-ignore offline = **5550-8322** ≠ oracle **2048-7592**
  (min ÷ par rapport à la base, max ↑). L'écart vient de l'axe **hits (PowerTrip_FullHealth)** + une réduction
  du min non encore identifiée — PAS de l'ignore-armure. À reprendre via la MATÉRIALISATION des effets (savoir
  quels effets PowerTrip sont actifs offline + leurs valeurs), pas en fittant les nombres.

**PORT (axe armure/perçage, FAIT, NON commité)** : `DamageModifiers` += `extra_pierce`(@0x20)/`armor_penetration`
(@0x28)/`ignore_armor`(bool, =armor_eff 0) ; `add_modifier` route `Piercing`→extra_pierce, `ArmorPenetration`→
armor_penetration, `IgnoreArmor`→ignore_armor ; `effect_bonus` += `for_armor_penetration`/`for_ignore_armor` ;
`get_attack_prediction` calcule `pierce_eff`/`armor_eff` depuis mods AVANT le perçage (= GetBaseDamageWith-
FixedPiercedArmor), le scalaire %-list/additif RESTE post-perçage (= ApplyCappedModifiers). **Validé offline :
None == mods vides == (1110,2298) (no-regress) ; ignore_armor == pénétration=armure == pierce+80=100 == bout
plein (5550,8322).** AUCUN effet inscrit au registre sur cet axe (valeurs par-effet = via matérialisation).

### 17.13 EFFETS = hiérarchie de classes (BaseEffect + sous-classes + factory + registre) + matérialisation offline (2026-06-27)
Refonte (directive user : « classe de base + classes dérivées + registre + factory ») — mirror FIDÈLE du
modèle natif « 1 classe par effet ». Remplace l'ancien registre de données (`effects_damage_bonus.EffectDef`
+ dict `EFFECT_LIFECYCLE`), supprimé.
- **`engine/entities/effects/`** : `base.py::BaseEffect` (interface = `create_effect_damage_bonus_for_attack`
  / `create_effect_hits_bonus_for_attack` / `get_armor_penetration` (IgnoreArmor) / `is_active`
  (CreateActiveCondition) + cycle de vie `removed_after_attack`/`one_shot`/`expired`) ; `loki.py` = 1
  sous-classe par effet (RapidAssaultExtraDamageEffect @180f67940, PowerTripFullHealthEffect @180f64cf0/cond
  @180f64cb0, PowerTripIgnoreArmorEffect @180f64fa0 (no-op), KanOpenerEffect @180f65100) ; `magnitude.py` =
  résolution gameconfig (trait/ability×level, Option A) ; `factory.py` = `EffectFactory` + `EFFECT_CLASSES`
  (nom EffectType→classe ; inconnu→BaseEffect no-op) ; `__init__` = `build_attacker_modifiers_from_effects`
  + `hits_bonus_from_effects`.
- **`engine/entities/effects_state.py::EffectsState`** = matérialisation **seed one-shot + évolution** :
  `seed({uid:[capture]})` → instances via factory ; `active_effects(uid, state)` = non-consommés/non-expirés/
  `is_active` (ce que l'engine consomme par décision, AU LIEU d'une relecture live) ; `on_attack` (one-shot),
  `on_turn_end(attacked)` (retrait RapidAssault si attaqué + décrément timers).
- **Mapping natif** : BaseEffect↔BaseEffect ; `*_Effect`↔sous-classes ; dispatch `EffectType→classe`↔factory ;
  effets posés (triggered `AddEffect`)/portés (`EffectsOwnedComponent`)/itérés (builder `param_5`)/retirés
  (trigger)↔EffectsState seed+lifecycle. **2 écarts par conception (100% offline)** : magnitude = gameconfig
  offline indexée level (vs DSL live) ; effets = seed one-shot + évolution (vs ECS temps réel).
- **Validé offline** : factory dispatche ; matérialisation+cycle de vie OK (PowerTrip_FullHealth actif SSI
  PV pleins ; RapidAssault retiré après attaque) ; **RapidAssault EXACT préservé** ; UnitContext.attacker_modifiers
  accepte instances OU dicts. **RESTE** : (a) `combatSnapshot.effects` one-shot (hook, rebuild+reinject) — pour
  l'instant seed depuis decisionView (oracle) en validation ; (b) magnitudes PowerTrip (clés 0x2b hits / 0x40
  pénétration → noms gameconfig) ; (c) re-valider live (10/11) après refonte ; (d) u90 (hits full-health + pén).

**§17.13 RE-VALIDÉ LIVE (session 27, seed-777, 2026-06-27)** : refonte classes+factory+matérialisation =
**10/11** (u94→u84 3012-4524 EXACT, mods ×1.25 via la chaîne EffectsState→factory→RapidAssaultExtraDamageEffect).
⚠ GOTCHA corrigé : `RemainingTurns` capté = **0 pour TOUS** les effets seed-777 (passifs/aura/this-turn ;
retrait géré par TRIGGER, pas par timer). Le filtre `expired` (remaining<=0) droppait donc TOUS les effets
(régression 8/11) → fix dans `EffectFactory.create` : `rem=0 → None` (permanent/no-countdown) ; seul `rem>0`
est chronométré (expire après décrément `on_turn_end`).

### 17.14 PowerTrip — magnitudes MAPPÉES + u90 NON fermé proprement (RE, 2026-06-27)
PowerTrip = **ability PASSIVE** de orksKillaKan (PAS un trait ; traits KillaKan = Hero/GetStuckIn/BigTarget/
Explodes/Mechanical). `gameconfig.ability('PowerTrip')` : constants `{extraHit:1, hpPct:5}` ; variables
`{armorIgnored:[5,6,7], armorReduction:[5,6,7]}`. Application RE'd (3 sous-mécanismes DISTINCTS) :
- **`PowerTrip_FullHealthEffect.CreateEffectHitsBonusForAttack` @180f64cf0** = `ForAddition(extraHit=1)`,
  gaté `!IsDamaged` (PV pleins, `CreateActiveCondition` @180f64cb0) → **+1 COUP** (prédiction-time, PORTÉ).
- **`PowerTrip_OnAttackAbility.CreateBehaviour` @181111e40** = ON ATTACK : `AddStaticStatModifierEffect
  (cible, FixedArmor, −GetVariableForLevel(key 0x30=armorReduction[lvl]))` + self `ChangeStat(Health, +hpPct%)`.
  ⇒ réduction d'armure **STATEFUL** (mute la stat FixedArmor de la cible dans le temps), PAS un modifier de
  prédiction (la prédiction lit déjà l'armure courante) → RIEN à ajouter au DamageModifiers.
- **`PowerTrip_IgnoreArmorEffect.CreateEffectDamageBonusForAttack` @180f64fa0 = NO-OP** ; `armorIgnored`
  (var distincte) consommateur non tranché → no-op (pas d'invention).
- `PowerTrip_InitAbility.CreateBehaviour` @181111d20 pose les effets 0x551/0x552 (FullHealth/IgnoreArmor).

**WIRING** : `PowerTripFullHealthEffect` +1 coup câblé (magnitude.ability_var('PowerTrip','extraHit',const)) +
`hits_bonus_from_effects` branché dans predict_validate (`hits += Σ bonus`). **Effet LIVE** : u90→u86 hits 3→4,
offline 1110-2298 → **1480-3064**, xmod **2.83 → 2.12** ; **10/11 préservé** (seul u90 affecté).
**u90 PAS FERMÉ — résidu = enveloppe per-coup LARGE & ASYMÉTRIQUE non fittable** : oracle per-coup
[512,1898] vs offline [370,766] (min ×1.4, max ×2.5 — ratio ≠ scalaire ≠ armure uniforme ≠ +hits). Ne
correspond à AUCUN axe porté (modifier/armure/hits). Hypothèses NON vérifiées (à RE, PAS à fitter) :
modifiers DÉFENSEUR de u86 (BigTarget/Explodes/PowerTrip côté cible) et/ou armure déjà réduite live (stateful
OnAttack) et/ou per-coup à armure décroissante. ⇒ fermeture = RE `CalculateDefenderModifiersForPrediction`
sur u86 + l'asymétrie per-coup, refusée tant que non lue (règle anti-fitting).

### 17.15 Défenseur RE'd — u86 contribue ZÉRO ; u90 NON fermable en RE statique (2026-06-27)
`CalculateDefenderModifiersForPrediction` @181002c30 (lu) : `Empty` + `CalculateModifiersFromStatModifications`
puis itère les EFFETS du DÉFENSEUR (param_5) ; par effet 3 slots — `0x1a`/`0x1b` (FUN_18002fd50 →
Nullable damage-malus, ajoutés à la %-list via DamageModifiers.Add) + sous-check FUN_1800058b0 → pénétration
`iVar28`→param_1[5]=@0x28 ; `0x19` (FUN_180024fa0 → pierce `iVar29`→param_1[4]=@0x20). = famille
`CreateEffectDamageMalusForDefense`/`CreateDamageDefenseModifier`. **CONFIRME** : défenseur alimente le MÊME
@0x20 (pierce)/@0x28 (pénétration) + une %-list, combinés attaquant+défenseur dans CalculateBaseDamageWith-
AllModifiers.
**MAIS u90→u86 NON fermé** : (1) effets de u86 (PowerTrip_IgnoreArmor/PowerTrip_FullHealth/BigTarget_Adjacent)
n'ont AUCUNE méthode de défense (la famille Malus = d'AUTRES effets) → **défenseur u86 = ZÉRO modifier** ;
(2) `BigTargetAdjacentEffect.CreateEffectHitsBonusForAttack` @180f33ac0 = condition `OwnerIsTarget &
IsRangedAttack` (bond ABondEffect 0x406 sur friends adjacents, CreateTargetSelector=Friends(AdjacentUnits))
→ **tir uniquement** ; attaque normale u90 = arme Chain MÊLÉE → N/A.
⇒ **TOUS les axes candidats RE'd sont épuisés et AUCUN n'explique u90** (oracle 2048-7592 vs offline 1480-3064
à 4 coups). Résidu = enveloppe per-coup large/asymétrique [512,1898] vs [370,766]. PowerTrip_IgnoreArmor
(`armorIgnored` [5,6,7]) reste non consommé (effet = no-op damage bonus, pas d'autre méthode). **Conclusion
méthodo** : ne PAS fitter ; passer à la CONFIRMATION LIVE — étendre `modifier-observe` pour dumper les VALEURS
réelles (DamageModifiers additif/%-list/pierce/pénétration + hits + armor_eff) au point CalculateBaseDamageWith-
AllModifiers de u90→u86, pour identifier l'axe manquant. (Port défenseur = structure RE'd, à porter quand une
unité a des effets de défense ; inutile pour u86 qui n'en a pas.)

### 17.16 u90 DIAGNOSTIQUÉ via value-dump live — pénétration 499 + 6 coups (GetStuckIn) (2026-06-27)
Extension `modifier-observe` : value-dump sur `GetBaseDamageWithFixedPiercedArmor` @181030d10 (onEnter args
Fix64 base/pierceA/pierceB/pénétration + onLeave result ; Fix64=Q31.32 confirmé `0x73a00000000>>32=1850`).
RPC `modifierObserveStatus.valueDumps`. **Dump u90→u86 (bouts base 1850/2774)** :
- **pénétration = 499** (param_10) → armor_eff = 2008−499 = **1509** ; result lo = 1850−1509 = **341**, hi =
  2774−1509 = **1265** (les DEUX sur la branche `base−armor` ⇒ le plancher perçage n'a PAS gagné → pierce
  effectif BAS ici, ≠ 20 supposé ; pierceA/pierceB args = 0).
- **`[341,1265] × 6 coups = [2046,7590] ≈ oracle [2048,7592]`** (±2 arrondi). ⇒ u90 = **6 COUPS** + pénétration 499.
**Source des 2 axes (RE)** :
- **6 coups = trait GetStuckIn** : `GetStuckInAbility.CreateBehaviour` @180f83280 = `AddBonusHitsToCurrentHitGroup
  (effet 0x4d2)` sous `Maybe(GetBonusHitChance)` ; `CreateTrigger` @180f83350 = `On(8) & CurrentHitIndex IsOdd
  & OwnerIsCaster & !(MinDistance>2)` (mêlée) ; `GetBonusHitChance` @180f83460 = ConfigConst 0x2a
  (`getStuckInChance`=30) / 0x33 (`getStuckInChance_2`=100), 100% si ≥2 Orks adjacents (faction 5) OU ≥4 unités
  adjacentes. ⇒ ajoute un coup bonus par coup d'index IMPAIR en mêlée → **double ~3→6** (100% ici, 2 orks adjacents).
- **pénétration 499** = NON encore sourcée (≠ PowerTrip armorIgnored/reduction=5-7 ; ≈25% de 2008=502). À RE :
  le chemin pénétration du builder ATTAQUANT (`CalculateAttackerModifiersForPrediction` @181000590, champ @0x28).
**CONCLUSION** : value-dump = CONFIRMATION réussie (méthodo respectée, zéro fitting). u90 = 6 coups (GetStuckIn,
positionnel/parité d'index) × per-bout[341,1265] (pénétration 499). **PORT pour fermer** = (a) porter GetStuckIn
(coups bonus odd-index + ≥2 orks adjacents → +hits ; positionnel), (b) sourcer+porter la pénétration 499
(RE builder attaquant @0x28), (c) profil/pierce réel de l'attaque (bas, ≠ Chain 20). Hook value-dump = NON commité.

### 17.17 LES TRAITS SONT EXPLOITÉS DIRECTEMENT DANS rawDamagePrediction (correction majeure, 2026-06-27)
**2 erreurs à moi corrigées :** (a) §17.5 (`HasTrait 0x420`/`HasEffect 0x59a` dans PredictAttackRaw) était
**CORRECT** — je l'avais réfuté à tort en grepant le `.compact.c` (LOSSY) ; le `.c` complet l'a (ligne 2227-2232).
**Ne jamais conclure « absent » depuis le décompilé compacté — grep le fichier complet.** (b) J'ai ancré toute
la RE modifier sur le chemin **effet→DamageModifiers** et **loupé que les traits sont exploités DIRECTEMENT**
dans `PredictAttackRaw` + ses helpers.

**RÉPONSE « les traits sont matérialisés ? » — DEUX chemins d'exploitation :**
1. **Matérialisés** au battle-init en : (a) ABILITIES accordées par le trait (`<Trait>Ability` triggered/active :
   GetStuckInAbility, PowerTrip_Init/OnAttack, BigTargetAbility, RapidAssaultAbility…) ; (b) EFFETS que ces
   abilities posent (`AddEffect(id)` → EffectEntity dans ActiveEffectIds → `decisionView.effects`, SOUS-ENSEMBLE).
   GetStuckIn = matérialisé en ABILITY (coups bonus transitoires `AddBonusHitsToCurrentHitGroup`), PAS en effet
   nommé → invisible dans la capture (d'où le miss).
2. **Exploités DIRECTEMENT dans rawDamagePrediction** (PredictAttackRaw + helpers), via `HasTrait`/`HasEffect`/
   `GetTraits`/`TryGetAbility`/`HasTriggeredAbility` — couche que l'engine ignorait totalement.

**CONTRAT d'exploitation des traits dans le raw prediction (= la GARDE systématique, fonctions NOMMÉES finies) :**
- `GetBaseDamageWithFixedPiercedArmor` @181030d10 : `HasTrait(cible, 0x3f5=1013)` → hit-twice (×2) ;
  `GetPiercingRatio(profil, GetTraits(attaquant))` → pierce trait (lasCannon 0x3e9/0x3f8) ; `TryGetAbility
  (cible, 0x4b6=1206)` + var 0x51 → triple-hit.
- PredictAttackRaw @2227 : `HasTrait(attaquant, 0x420=1056) & HasEffect(attaquant, 0x59a=1434)` → flag
  true-damage/ignore-armure (uVar17 → scenario).
- PredictAttackRaw @2294 : `ApplyTraitDamageLimitsToDamage` @18102c650 → `ApplyGroupUnitDamageLimit` (×2) +
  `ApplyResilientTraitDamageLimit` (trait **Resilient**, cap/coup) + `ApplyImperviousTraitDamageLimit` (trait
  **Impervious**) + cap `HasTriggeredAbility(cible, 0x5d4)` → dmg ≤ `GetStat(MaxHP)×GetNumberConstant(0x12)/100`.
- PredictAttackRaw @2385 : `DamageProfile.HasTrait`.
- (+ effet→DamageModifiers = traits matérialisés en effets.)
⇒ **Pour ne RIEN louper : auditer ce contrat (ces fns nommées) + le chemin trait→ability/effet, PAS seulement
les effets captés.** Couche jamais portée dans l'engine (Resilient/Impervious/GroupUnit caps, ignore-armure
flag, hit-twice/triple-hit, profile-traits) = chantier de portage à part entière.
**u90** : 6 coups = GetStuckIn (confirmé) ; pénétration 499 = champ @0x28 des DamageModifiers (param_10),
source précise encore à isoler (dump attaquant-vs-défenseur séparé) — mais la LEÇON = la couche trait-direct
du raw prediction, désormais cartographiée.

### 17.18 MATÉRIALISATION DES TRAITS (framework, 2026-06-27) — symétrique des effets
Directive user « il faut materialiser les traits aussi ». Même patron que les effets, mais traits =
**innés/statiques** (gameconfig.unit().traits, jamais retirés ⇒ pas d'évolution). Package
`engine/entities/traits/` : `base.py::BaseTrait` (contrat = points §17.17 : `as_attacker_bonus_hits`/
`as_attacker_pierce_bonus`/`as_attacker_ignores_armor`/`as_target_hit_multiplier`/`as_target_damage_cap`,
défaut no-op) ; `combat.py` (GetStuckInTrait confirmé + ResilientTrait/ImperviousTrait scaffold) ;
`factory.py` (TraitFactory + TRAIT_CLASSES nom gameconfig→classe, inconnu→BaseTrait no-op) ; `__init__`
(agrégateurs attacker_bonus_hits/…/target_damage_cap). `engine/entities/traits_state.py::TraitsState`
(seed `{uid:[noms]}` → instances, statique). `UnitContext.trait_objects()` = matérialise self.traits.
**GetStuckInTrait** : `as_attacker_bonus_hits` = ×2 (bonus=base_hits) en mêlée + ≥2 Orks adjacents (ou ≥4
unités) ; **VALIDÉ offline = value-dump u90 (base 3→6)** ; 0 si données d'adjacence absentes (pas d'invention).
Resilient/Impervious = scaffold (formule cap `ApplyResilient/ImperviousTraitDamageLimit` TODO RE).
**RESTE** : (a) câbler le contrat dans `get_attack_prediction` (appliquer attacker bonus_hits/pierce/
ignore-armure + target hit-mult/damage-cap, avec ctx adjacence/positions) ; (b) RE les formules par-trait
restantes (Resilient/Impervious caps, hit-twice 0x3f5, lasCannon-pierce, flag ignore-armure 0x420/0x59a) ;
(c) **pénétration 499 de u90 toujours NON sourcée** (champ @0x28 des DamageModifiers ; ni trait ni effet
identifié de u90/u86 ne la produit → besoin d'un dump séparé attaquant-vs-défenseur de @0x28). u90 = 6 coups
SOURCÉS (GetStuckIn) ; pénétration = pièce manquante.

### 17.19 Pénétration 499 SOURCÉE = côté ATTAQUANT (u90), via slot-0x16 du builder attaquant (2026-06-27)
Étendu `modifier-observe` : mods-dump des champs `DamageModifiers` (additif@0x10 / pierce@0x20 / pénétration@0x28)
retournés par CHAQUE builder (RPC `modifierObserveStatus.modsDumps`). **Résultat u90→u86** :
`attacker @0x28 = 499`, `defender @0x28 = 0` (distinct par côté : attacker {0,499}, defender {0}).
⇒ **la pénétration 499 est ATTAQUANT (u90), PAS défenseur.** (CalculateBaseDamageWithAllModifiers somme
att+def → param_10=499.)
**Mécanisme (attacker builder @181000590, compact l.796-841)** : pour chaque effet, slot `0x16`
(`GetDamageBonusForAttack`=`CreateEffectDamageBonusForAttack`) → EffectBonus ; un champ Nullable (FUN_1800058b0
HasValue) est sommé dans `iVar31` → `param_1[5]`=@0x28=pénétration. (slot 0x17 = autre ; 0x18=FUN_180024fa0=pierce@0x20.)
**SNAG honnête** : les 3 effets CAPTÉS de u90 (PowerTrip_IgnoreArmor=condition-seule, PowerTrip_FullHealth/
BigTarget=hits) ne produisent PAS statiquement 499 via slot 0x16. ⇒ soit (a) un 4e effet non capté par
decisionView.effects (effet transitoire/non-listé), soit (b) un champ pénétration **DYNAMIQUE** de l'EffectBonus
(rempli à l'évaluation, pas à CreateEffect ; 499 ≈ 25% de l'armure 2008 = peut-être un %-armure dynamique).
**NEXT (confirmation)** : dump PAR EFFET — hook `<Effect>.CreateEffectDamageBonusForAttack` de u90 + lire le
champ pénétration de l'EffectBonus retourné (avec l'identité de l'effet) → isole l'effet + la formule (statique
vs %-armure dynamique). La QUESTION du user (« dump @0x28 att-vs-def ») est RÉPONDUE : attaquant, 499.

### 17.20 u90 = arme PROJECTILE (pierce 15, RANGED), pas Chain — catch user « weapon ? » (2026-06-27)
Le per-bout réel (value-dump) lo=341 = `1850−1509` (branche ARMURE). Or le plancher perçage Chain(20)=370
AURAIT gagné (>341) → résultat 370, FAUX. Plancher Projectile(15)=277 (<341) → branche armure 341 gagne ✓.
**⇒ u90's normal attack = arme Projectile (pierce 15, RANGED), PAS Chain (20).** Vérif : Projectile+pen499
→ per-bout [341,1265]×6 = **[2046,7590] ≈ oracle [2048,7592]** ; Chain → min 2220 (≠2048).
**BUG predict_validate** : `_normal_weapon_pierce` choisit l'arme par `hits==normal_hits` ; u90 a 2 armes à
hits=3 (Chain melee, Projectile ranged) → prend la 1re (Chain) = FAUX. La sélection d'arme doit dépendre du
contexte (mêlée/portée), pas du 1er match hits.
**CASCADE de corrections (3 conclusions hâtives à moi) :**
1. pierce 20→15 (mauvaise arme). 
2. **Attaque RANGED** ⇒ GetStuckIn (MÊLÉE, `!MinDistance>2`) ne s'applique probablement PAS → **les 6 coups
   sont vraisemblablement BigTarget** (`BigTargetAdjacentEffect.CreateEffectHitsBonusForAttack` condition
   `OwnerIsTarget & IsRangedAttack`, u86=big target) **et NON GetStuckIn**. ⚠ Mon attribution GetStuckIn
   (§17.16/17.18) + le port `GetStuckInTrait` = **à RE-VÉRIFIER** (probablement la mauvaise source pour u90).
3. (§17.5 déjà corrigé : compact-grep.)
**Pénétration 499** : toujours côté attaquant, source ouverte — possiblement liée au ranged/BigTarget (à RE).
**LEÇON** : vérifier l'ARME (mêlée/ranged) AVANT d'attribuer hits/pierce — le choix d'arme conditionne quels
traits/effets s'appliquent (ranged vs melee gating). cf. [[feedback_recon_full_kit_not_captured_effects]].

### 17.21 PÉNÉTRATION 499 CRACKÉE = armorIgnored × AbilityVariablesMultiplierPercentage (RÈGLE GÉNÉRALE, 2026-06-27)
Dump par-source live (idée user : hooker les dispatchers de construction du modifier + **stacktrace**).
Ajouté à `modifier-observe.ts` : 3 hooks génériques dédupliqués `(tag,srcClass)` —
`BaseEffect.HitsBonusForAttack` @180f12a30 (bonus coups prédiction), `BaseEffect.DamageBonusForAttack`
@180f0f5e0 (bonus dégât/perçage/pénétration prédiction), `AddBonusHitsToCurrentHitGroupBehaviour.Execute`
@180f93410 (GetStuckIn EXÉCUTION). `srcClass` lu depuis `this`=args[1] (après le ptr de retour struct).

**DÉCOUVERTE MAJEURE — magnitude d'une variable d'ABILITY = `gameconfig.variables[level] × AbilityVariablesMultiplierPercentage/100`, arrondie.**
- u90 = orksKillaKan **L50**, `AbilityVariablesMultiplierPercentage = 180` (champ BC `Units[*]`). PowerTrip
  `armorIgnored[50] = 277` (gameconfig, `variablesAffectedByRarityBonus`). **`round(277 × 1.80) = round(498.6) = 499`** = pénétration live (@0x28 attaquant). ✅✅ fit 3 points (gameconfig + BC + live).
- **Variables de TRAIT (traitVariables) = globales, NON scalées** (RapidAssault 25% exact sans mult). Seules
  les variables d'ABILITY (`ability.variables[level]`) sont scalées par le mult de l'unité. Les **constantes**
  (`GetNumberConstant`, ex. PowerTrip `extraHit`=1) ne sont PAS scalées non plus.
- ⚠ Mon moteur lit `ability_var(level)` BRUT → manque le ×mult. **Fix général à câbler** : `magnitude.ability_var`
  doit multiplier par `UnitContext.ability_variables_multiplier` (à capter depuis BC/combatSnapshot).

**PowerTrip mécanique RE'd (décompile leaves) :**
- `PowerTrip_FullHealthEffect.CreateEffectHitsBonusForAttack` @180f64cf0 = `ForAddition(value=GetNumberConstant(0x2b=extraHit=1))`
  sous `IsNormalAttack & OwnerIsCaster`. Le gating PV-pleins = **présence de l'effet** (pas la condition du bonus).
  ⇒ **+1 coup** (constante, non scalée). base 3 → 4.
- `PowerTrip_IgnoreArmorEffect.CreateEffectDamageBonusForAttack` @180f64fa0 = bonus **condition-seule VALEUR 0**
  (`IsNormalAttack & OwnerIsCaster & !OwnerIsTarget`, val=0). **N'EST PAS le porteur du 499.** ⇒ correction : la
  pénétration est bâtie DIRECTEMENT dans `CalculateAttackerModifiersForPrediction` (lit la config PowerTrip), pas
  via le `DamageBonusForAttack` de l'effet. (≈ pattern d'exploitation directe §17.17, mais pour pénétration.)

**GetStuckIn PAS simulé en prédiction** : `addBonusHitsExec` fires=**0** pendant le decisionView. La prédiction
n'exécute pas le behaviour triggered GetStuckIn (`On(8) & CurrentHitIndex.IsOdd & OwnerIsCaster & !(MinDistance>2)`,
chance `If(orks_adj≥2 OU units_adj≥4, chance_2[0x33], chance[0x2a])`). ⇒ **les coups bonus GetStuckIn ne sont PAS
dans dmgMax** ; le port `GetStuckInTrait` ne doit PAS contribuer à la prédiction (mais reste vrai à l'exécution).

**MÉTHODE — value-dump ≠ hit count** : `GetBaseDamageWithFixedPiercedArmor` calcule le per-bout UNE fois (lo+hi)
par PRÉDICTION ; le nb de coups est un MULTIPLICATEUR aval (caller). `GenerateMultiHitAttackPredictions`@181409da0
boucle sur les MEMBRES de squad (param_5), pas les coups ; `hits`=param_7 passé au per-membre. `GetDefaultAttackHits`
@181032520 = `Max(0, nrOfHits + GetStat(17 ExtraHits) + [melee? GetStat(23 ExtraHitsMelee)])` (PAS GetStuckIn/effet).

**u90 FERMÉ — hit-multiplier = 6, CONFIRMÉ sur 2 cibles (arithmétique exacte, pen=499) :**
- base per-bout = `attack 2312 ±20%` = [1850,2774] ; `armor_eff = target_armor − 499`.
- u86 (armor 2008) : per-bout [341,1265] ×6 = **[2044,7592] ≈ oracle [2048,7592]** ✓ (×4=[1362,5062] ✗).
- u84 (armor 1806) : per-bout [543,1467] ×6 = **[3256,8804] ≈ native normalAttack [3260,8804]** ✓ (×4=[2170,5870] ✗).
- soustraction d'armure UNIFORME lo+hi (pas de modifier/extraMax ; crit/block/extraMax/members = 0 vérifié snapshot).
**⇒ hits damage = 6 = 3 (Projectile) + 1 (PowerTrip PV-pleins) + 2 (GetStuckIn = `floor(4/2)`, 100% car ≥2 orks adj).**
**Le CHAMP `normalAttack.hits` = 4** (GetDefaultAttackHits 3 + PowerTrip 1, **EXCLUT GetStuckIn**) ; mais le DÉGÂT
applique ×6 (GetStuckIn inclus). GetStuckIn EST dans la prédiction (`!MinDistance>2` = **portée 2, PAS mêlée-only**
→ s'applique au tir Projectile si cible ≤2 hex) **mais PAS via `AddBonusHitsToCurrentHitGroupBehaviour.Execute`**
(addBonusHitsExec fires=0) → chemin hits prédiction-spécifique (pas encore localisé en code). **Corrige §17.20**
(« probablement BigTarget, pas GetStuckIn » = FAUX : GetStuckIn EST le +2) **et le port `GetStuckInTrait`** (×2
doubling = FAUX ; vrai = `+floor(hits_post_PowerTrip / 2)` = floor(4/2)=2 au taux plein).
**RESTE (engine)** : (1) câbler `ability_var × AbilityVariablesMultiplierPercentage/100` arrondi (capter le champ BC
dans UnitContext) → pénétration 499 ; (2) PowerTrip armorIgnored → pénétration attaquant (normal attack, owner=caster,
toujours-on, scalé) ; (3) GetStuckIn `+floor(hits/2)` au taux plein (≥2 orks adj OU ≥4 unités adj, portée ≤2) ; (4)
localiser le chemin prédiction GetStuckIn en code (≠ Execute) pour fidélité exacte.

### 17.22 SOURCE du multiplier + WIRING points 1-3 (RE config-driven + port, 2026-06-27)
**Multiplier sourcé (catch user « trouve dans ghidra d'où le multiplier » + « config a des magnitudes par level ») :**
- **VALEUR** = `AbilityVariablesMultiplierPercentage` par-unité (BC `Units[*]`, =180 pour u90 L50), dérivée de la
  progression par `UnitConfigUtil.GetAbilityVariablesMultiplierPercentageForProgressionIndex` @181696230 (table
  per-progression-index, défaut 100 ; meta-side `IdunMetaLogic.UserProgress.*`).
- **QUELLES variables** = config-driven : BC `Abilities.PassiveAbilities.PowerTrip` porte les **arrays BASE**
  `[5..364]` + le flag `VariablesAffectedByUnitRarityMultiplier:[64,48]` (= gameconfig `variablesAffectedByRarityBonus:
  [armorIgnored,armorReduction]`). Seules ces variables sont scalées ; constantes (extraHit) non.
- **FORMULE** = `effective = round(base[level] × mult/100)` → round(277×1.8)=499. `GetVariableForLevel` @181576fb0
  rend la base brute (pas de scaling là) → le scaling est appliqué au build config par-unité (BC→runtime).
- **GOTCHA `level` (bug trouvé live)** : `decisionView.effects[].level=1` = **stack level**, PAS le niveau d'ability.
  `armorIgnored` est indexé par le **PassiveAbilityLevel (=50)**. Avec le stack level (1) → armorIgnored[0]=5 → pen=9
  (FAUX). Fix = champ `BaseEffect.ability_level` distinct (seedé depuis l'unité), utilisé pour les variables d'ability.

**WIRING points 1-3 FAIT + VALIDÉ LIVE (NON commité) :**
- (1) `magnitude.ability_var(multiplier_pct)` scale les vars `variablesAffectedByRarityBonus` (round). 
- (2) `PowerTripIgnoreArmorEffect.get_armor_penetration` = `ability_var(armorIgnored, ability_level, mult)` → 499 ;
  threadé via `BaseEffect.{ability_variables_multiplier,ability_level}` + `EffectFactory`/`EffectsState.seed(mult_by_unit,
  ability_level_by_unit)` + `UnitContext.ability_variables_multiplier`. **Live u90→u86 : offline hi 3100→5060** (pen 499
  appliqué : per-bout 1265 = 2774−(2008−499)). 
- (3) `GetStuckInTrait.as_attacker_bonus_hits` = `+floor(hits/2)` au taux plein ; câblé predict_validate (ctx adjacence
  cible/portée≤2). **Offline OK** (base4→+2→6).
- **predict_validate** capte mult + PassiveAbilityLevel depuis la BC (par visualId ; capture per-entité combatSnapshot =
  TODO robustesse). **AGREEMENT 10/11 préservé** (zéro régression).
- **(a) SÉLECTION ARME mêlée/ranged FAITHFUL FAIT (2026-06-27)** : RE `ALoki_NormalAttackAbility.PredictAttack`
  @1811afa50 → `FindAttackWeapon` @1811aeb80 (sélectionne l'arme par PORTÉE/atteignabilité, DamageProfile@0x10).
  `_normal_weapon_pierce(ctx, dist)` réécrit : cible adjacente (dist≤1)→arme mêlée, sinon→arme ranged (fallback ranged
  si dispo) ; déplacé PAR-CIBLE (dist=cheby position courante). **u90 → pierce 15 (Projectile, était 20 Chain)** →
  per-bout [341,1265] = `[1850,2774]−(2008−499)` = **EXACT value-dump**. offline 1364-5060. 10/11 préservé (autres
  unités mono-arme, inchangées). ⚠ branche mêlée-adjacent non exercée seed-777 (règle portée standard, hypothèse).
- **u90 = 1 SEUL résidu restant = hit count (4 vs 6)** : tout le per-bout est EXACT (base, pierce 15, pénétration 499,
  PowerTrip +1, armure). GetStuckIn ne fire pas à la position COURANTE (cheby u90↔u86 >2) alors que l'oracle prédit
  **post-move** (×6) → **(b) position-aware** (évaluer à la meilleure tuile d'attaque comme l'oracle). Avec h6 →
  [2046,7590]≈oracle [2048,7592]. Points 1-3 + (a) = corrects ; reste UNIQUEMENT (b).

### 17.23 u90 FERMÉ — prédiction ANCRÉE À LA POSITION D'ATTAQUE → AGREEMENT 11/11 (catch user, 2026-06-27)
**Point user décisif** : « la prédiction de dégât est relative à UNE position, et celle-ci est soit mêlée soit ranged ».
⇒ pas 2 problèmes (arme + position) mais UN : ancrer la prédiction à la **position d'attaque que l'oracle a utilisée**.
`decisionView.attackPlans[].evals[].ranked[]` EXPOSE cette tuile : `{col,row,dmgMin,dmgMax,...}`. u90→u86 :
`ranked[0]=(5,4)` (post-move), cible (6,6) → **dist 2** (≠ dist courante 4). Fix : `predict_validate` consomme
`(r0.col,r0.row)` comme position d'attaque pour la **distance** (→ arme) ET le **within-range-2** (→ GetStuckIn).
- À dist 2 : non-adjacent → **arme ranged (Projectile pierce 15)** ; within range 2 → GetStuckIn trigger OK.
- **GetStuckIn = prédiction OPTIMISTE** : oracle u90→u86 a dmgMin ET dmgMax à 6 coups, alors que la condition de
  CHANCE est 30% (1 seul ami adjacent à la cible, <2 orks/<4 amis ADJACENTS range 1). ⇒ le moteur de prédiction
  résout `Maybe(GetBonusHitChance)` comme « atterrit » (cf. predOptimistic) → compte `+floor(hits/2)` dès que le
  trigger STRUCTUREL tient (within range 2), SANS gate sur la chance. `GetStuckInTrait.as_attacker_bonus_hits` =
  `+floor(hits/2)` sur within_range2 seul (orks/amis = info 30 vs 100% réel, pas de gate).
- **RÉSULTAT** : u90→u86 = 3(Projectile)+1(PowerTrip)+2(GetStuckIn) = **6 coups**, per-bout [341,1265] ×6 =
  **[2046,7590] ≈ oracle [2048,7592] = xmod 1.00 OK**. **AGREEMENT 11/11** (était 10/11), 0 régression. Les 4 OPT
  (cibles à réduction) restent hors compte propre. Points 1-3 + (a) + ancrage position = **u90 FERMÉ**. RIEN COMMITÉ.

### 17.24 MULTIPLIER CAPTÉ PAR-ENTITÉ via combatSnapshot (live, 2026-06-27)
Remplace le fallback BC-offline-par-visualId. `AbilityVariablesMultiplierPercentage` vit sur **`UnitConfiguration`**
(dump gqfc5mff6c : `Id@0x10, VisualId@0x18, mult@0x74, tertiaryMult@0x78, Level@0x7C, ActiveAbilityLevel@0xB8,
PassiveAbilityLevel@0xBC` ; `Level`=struct int). PAS sur l'entité (`UnitComponent` = VisualId@0x20/Rank@0x1A4 sans
mult). Registre runtime = **`BattleQuery.GetUnitConfig(unitId)`** (EntityServices.`<Battle>`@battleInServicesOff ;
clé = VisualId, Id==VisualId). `combatSnapshot` (rpc-view.ts) ajoute par unité `unitConfig` = {visualId,
abilityVariablesMultiplier, tertiaryAbilityVariablesMultiplier, level, activeAbilityLevel, passiveAbilityLevel} :
lit la VisualId-string de l'entité (UnitComponent.VisualId@0x20 via forEachComponent) → `GetUnitConfig` → champs.
`predict_validate` consomme `snap.units[].unitConfig` (mult_by_id/ablvl_by_id par entityId ; entityId==decisionView.id),
fallback BC si hook ancien. **Per-entité réel confirmé : mult VARIE (u88=160, u94=200, autres=180)** (table de
progression @181696230 par unité). **AGREEMENT 11/11 préservé, sourcé LIVE** (plus de dépendance duel_state.bc).
Build+reinject session 31. RIEN COMMITÉ. (TODO robustesse : duplicates même VisualId mais Id unique en bataille
non-miroir → clé Id de l'entité requise ; non bloquant pour arène-miroir.)

## §18 — Pathfinding fidèle (énumération des tuiles atteignables) — approche A (capture live)

**Objectif** : reproduire en Python l'énumération des tuiles atteignables que l'IA consomme
(`aiMovableTiles` = `MovementQuery.GetMovableTilesFor`), pour le moteur playbook (positionnement).

### Modèle natif (RE ghidra gqfc5mff6c — decompile=vérité)
Deux moteurs DISTINCTS, l'IA n'utilise que le premier :
1. **Énumération (reachable set)** = FLOOD-FILL PAR NIVEAUX, NON pondéré. 1 pas = 1 niveau, `range`
   niveaux. Chaîne : `GetMovableTilesFor` @18109a330 → `FindAnyOrAllMoveableTiles` @181098cb0 →
   `BasePathfinder.GetMovablePositions` @180ee25d0 (itér. @180f27840, `NodesInNextLevel`,
   profondeur −1/niveau). **Aucun coût accumulé.**
2. **Chemin exact (A*)** = `GenerateBreadthFirstTree` @180ee21a0 + `WeightCost` @180f2f120
   (coût/pas = (10 ou 10000 si bloquant)−élévation). Sert UNIQUEMENT à `GetPathTo`. PAS porté.

**Prédicat d'arête** `WalkPathfinder.IsValidPathNode` @180f2ee50 (entrer sur `to` depuis `from`) :
- `IsWalkable(to)` (@180ec6fc0) ;
- `|elev(to)−elev(from)| ≤ 1` (`IsReachableElevationDifference` @180f2ed80 = `abs<2`, **symétrique**,
  exception paires de téléporteurs) ;
- `!UnitIsBlockedByEnemyUnit(to, unit)` (@180f2ef50) : un **ENNEMI** sur la tuile bloque le passage ;
  un **ALLIÉ laisse passer** (traversable, pas d'arrêt) ; ennemi avec trait `0x1b` laisse passer.
**Tuile d'ARRÊT** = `GetTileBlockingReasons==0` (`IsValidContinuePathTile` @180f2ee30) = NON occupée
(ni allié ni ennemi). Start (tuile courante) exclu du set. `GetEffectiveDepth` (hazard→`Min(1,depth)`,
@180f2e920) = non plombé (pas de hazard board basique).

**Portée** `MovementRangeWithAppliedBonus` @18109cdc0 = stat Movement (`StatComponent.CurrentValue`)
`+ GetRangeBonusForUnit − Σ réductions`, plancher 0 ; **0 si enraciné** (trait `0x418` / triggered `0x4b8`).
**Pathfinder type** `GetPathfinderTypeForUnit` @18109a7b0 : `Walk(0)` défaut, `Fly(3)` si `IsLikeFlying`,
6–13 = blink/téléport (effets `0x40b/0x474/0x4d6/9999`). Cas IA normal = Walk.

### Capture live (approche A) — RPC `boardGraph` (rpc-view.ts)
Dump statique par tuile `{id,col,row,elevation,isWall,walkable,neighbours[]}` :
- `walkable` = `BattleQuery.IsWalkableTile(tile)` (= IsWalkable du pathfinder ; **≠ isWall** : 1 tuile
  walkable=False isWall=False observée → walkable natif = le vrai signal).
- `neighbours` = `BattleQuery.GetAdjacentTiles(tile,true,true,true)` (set complet, cf.
  `GetFreeAdjacentTiles` @181061650 qui passe ces flags puis filtre).
- élévation = PositionComponent@0x18 (révélé par `GetCoordinates` @180ec4e40 : col@0x10,row@0x14,elev@0x18).

### Résultat de validation (`pathfind_validate.py` vs `aiMovableTiles`, seed 777, 7×9=63 tuiles)
- **L'adjacence native `GetAdjacentTiles` est LOSSY** : asymétrique (~18 arêtes one-way),
  (0,0) renvoie 0 voisin (corner e3) → modes `native`/`native_sym` échouent (1–2/5).
- **L'adjacence hex EVEN-Q est fidèle** (parité par COLONNE, convention VÉRIFIÉE sur les tuiles natives
  à 6 voisins : col pair → `(-1,0)(-1,1)(0,-1)(0,1)(1,0)(1,1)` ; col impair → `(-1,-1)(-1,0)(0,-1)(0,1)(1,-1)(1,0)`).
  → **WalkPathfinder 4/4 EXACT** sur toutes les unités WALK (u88/u90/u92/u94, à leur **stat Movement
  réelle** 3/3/3/4 via combatSnapshot). Murs = propriété de tuile (walkable), PAS arête manquante.
- **u96 (darkaTerminator) — RÉSOLU = non-Walk, PAS un bug** : stat Movement = **2** mais atteint **47**
  tuiles → impossible en Walk. L'unité a `TeleportStrike_TeleportingIn` actif → `GetPathfinderTypeForUnit`
  @18109a7b0 renvoie un type **téléport** (HasEffect 0x40b/0x474/0x4d6/9999), reach ignorant la portée de
  marche. Modèle Walk non applicable. Le harnais le **détecte** (portée effective en pas de marche >
  stat Movement ⇒ Fly/Teleport/range-bonus, exclu du score Walk). (TODO porter Fly/ATeleportPathfinder ;
  mapper l'id d'effet TeleportStrike ↔ type pathfinder.)
- **Diagnostic en route (chemins écartés)** : pas d'empreintes multi-hex (10 unités = 1 tuile,
  `occupiedTiles=10`) ni MoW ici ; capture d'occupance complète via `UnitFootComponent` (UnitId@0x10,
  TileId@0x14) AJOUTÉE à `boardGraph` (`occupantUnitId` par tuile) = faithful, prête pour empreintes/MoW
  réels. Bug harnais corrigé : la portée DOIT venir de la stat Movement (l'inférence depuis le natif
  sur-comptait via divergences de distance even-q en terrain varié). `aiMovableTiles` (défaut) = RAW
  `GetMovableTilesFor` (pas de filtre danger-zone). `aiMovableTiles.units` N'A PAS de `team` → decisionView.

### Fichiers (NON commités)
- `frida/hooks/features/ai-step/rpc-view.ts` : RPC `boardGraph` (read-only) + occupance UnitFoot.
  Build+reinject session 33.
- `scripts/python/engine/entities/pathfinding/` : `board.py` (3 modes adjacence), `walk_pathfinder.py`
  (flood-fill niveaux + IsValidPathNode), `__init__.py`.
- `scripts/python/pathfind_validate.py` : harnais (portée réelle = stat Movement, détection non-Walk).
TODO : Fly/ATeleportPathfinder (u96-like) ; MovementRangeWithAppliedBonus (bonus/réduction/enraciné) ;
GetEffectiveDepth (hazard) ; câblage moteur playbook.
