# Playbook Engine — état de validation & ce qui reste

> La réponse directe à « **qu'est-ce qui nous manque pour reproduire fidèlement l'IA ?** ».
> Métrique = agreement vs l'IA native sur le MÊME état (`engine_validate.py`, `aiStepDryRun`).

## 1. Agreement actuel

| Axe | Mesure | Seed |
|-----|--------|------|
| Décision — **positioning** | **55 % exact / 77 % ≤1 hex** | 777 |
| Décision — **ability** | **100 %** (4/4) | 777 |
| Décision (régression) | 44 % / 61 % / 100 % | 2024 |
| **Prédiction de dégât** (xmod) | **11/11** (u90 fermé) | 777 |
| **Pathfinding** WalkPathfinder | **4/4 EXACT** (à la stat Movement réelle) | 777 |

## 2. Ce qui est porté + validé

- **Spine décisionnel** complet (PickNextUnit -> buckets -> ChooseAction = argmax-utilité-parmi-légales). cf. [`architecture.md`](architecture.md).
- **Formule d'utilité** + poids `Utilities.{Default,MovementSuggestion}` + composites. **Dégât** porté & validé ; **Tile(7)** partiel. cf. [`scoring.md`](scoring.md).
- **Prédiction de dégât OFFLINE faithful** (gameconfig + scenario-math, pas de DSL) : multi-coups, crit/block, modifiers (additif/pierce/pénétration), traits exploités, multiplier par-entité, ancrage position d'attaque. **11/11**. cf. [`prediction.md`](prediction.md).
- **Scoring de mouvement** (MinDist domine / MaxDist module / RangedAdj gaté gameconfig ; UnitTile OFF confirmé ghidra) + **pathfinder Walk** exact (flood-fill par niveaux, adjacence even-q). cf. [`pathfinding.md`](pathfinding.md).
- **Playbooks communs** (Default/NormalAttack/Heal/Repair) = scorer générique partagé, portés & validés offline (19/19). cf. [`playbooks.md`](playbooks.md).

## 3. Ce qui RESTE pour la fidélité (par ordre d'impact)

### 3.1 Prédiction NON-dégât offline (heal / repair / effet) — ~~bloqueur structurel~~ → SOIN+REPAIR RE'd+portés
`aiPredict` = `GetAllPredictions` = **dégât seulement** (l'oracle live ne couvre pas le non-dégât).
- **SOIN** : chaîne `PredictHeal`/`HealUtility` **RE'd + portée** offline (`predict.py` PARTIE 3 ; cf.
  [`prediction.md`](prediction.md) §9). Wirée + gatée dans `engine_decide` (seuil `ENGINE_HEAL_MIN_UTIL`).
- **RÉPARATION** : chaîne `PredictRepair`/`RepairedAmountUtility` **RE'd + portée** offline (`predict.py`
  PARTIE 4 ; [`prediction.md`](prediction.md) §9bis) — utilité à 2 termes (Health W=100 + Armor W=50)×bossMod,
  pas de friendSign. **Pas encore wirée** dans un `RepairPlaybook`/`engine_decide` (mécanique rare).
- **POSE D'EFFET** : `AddedEffectUtility` **RE'd + portée** offline (`predict.py` PARTIE 5 ;
  [`prediction.md`](prediction.md) §9ter). **Pas de magnitude** — poids plat par type d'effet,
  `U = Weight[name] ± Weight["Unit_on_"+name]`, lu du BC `Utilities.Default` (data-driven, valeurs réelles
  vérifiées : Fire ennemi=25 / allié=−5). C'est une **feuille** du scorer BC général (cf. §3.2 / #38).
- **RESTE** : dégât BOUCLIER `Avg(shieldMinMax)` ; magnitude heal/repair sourcée du gameconfig
  (`hpToHeal`/`hpToRepair` par level × mult) ; **wiring** des utilités heal/repair/effet dans les playbooks
  + agreement LIVE des décisions correspondantes.

### 3.2 Sélection INTER-catégorie — **RE'd (modèle corrigé)**, refacto moteur EN ATTENTE
Mécanisme natif **confirmé dans le code** (cf. [`architecture.md`](architecture.md) §2.3) et il
**invalide deux modèles antérieurs** (« argmax devise unifiée » ET le seuil `ENGINE_HEAL_MIN_UTIL`) :
- Liste ORDONNÉE de générateurs `[ability@1000, @100, @0, @-100, @-1000, @final, MOVE]`
  (`DefaultAiUnitTactic..ctor @1810eebc0`), **premier-non-null** (`CalculateNextActionForUnit @1810f54e0`).
- Tier d'une ability = son **`playbook.Preference`** (`InitAbilityTypeLists @1810ed540`).
- Un tier = **argmax** (`Bucket.ChooseAction`) des actions LÉGALES de ses abilities, ou **null** si rien.
- **MOVE = fallback pur** : fire ssi aucun tier d'ability n'a d'action légale. **Pas de seuil ability/move.**

**✅ « VERDICT B » était une ERREUR DE MESURE** (le « natif bouge sans soigner »). Le dump de l'action
COMPLÈTE de Rotbone (`aiDryRunAllUnits`, chunk entier) = `[MoveUnitMessage→(1,2), ActiveAbilityMessage
abilityType=18 (Heal)]` : **Rotbone se déplace PUIS soigne**. `native_first` renvoyait `"move"` (1er
message) et masquait le heal. Donc « premier-non-null PUR » est **maintenu** (le soin a bien été émis,
en `move+heal`) et la RE était correcte. Leçon : comparer le **chunk entier** (move ∧ ability), jamais
`native_first[0]`.

**Gate RE'd (cf. [`architecture.md`](architecture.md) §2.3bis)** : chaque action comparable s'auto-gate à
l'émission via `Playbook.ShouldExecute` (vtable +0x328, appelé dans `CalculateActionUtility @181406ee0`) ;
`HealPlaybook.ShouldExecute @181184b30` = **`heal_utility > 0`** (+ règle boss). Si `<= 0` →
`CalculateActionUtility` renvoie `null` → `EvaluateInternal @181408980` n'émet pas l'action → fallback MOVE.
⇒ **Remplaçant fidèle de `ENGINE_HEAL_MIN_UTIL` = seuil 0** (pas 50) sur l'utilité de soin déjà portée (#37).

**✅ Refonte moteur — 1ère tranche FAITE + VALIDÉE LIVE.** `engine_decide` : la branche soin **balaie
les tuiles** `(tuile atteignable × cible valide)`, score `pred_util + tile_util(tuile)`, gate
`ShouldExecute` = `pred_util > 0` (seuil `ENGINE_HEAL_MIN_UTIL`=50 **RETIRÉ**), argmax `full_util` ; MOVE
= fallback (premier-non-null) → produit une **action composée move+heal**. **Rotbone : MATCH EXACT**
(moteur = natif : move→(1,2) + heal ability 18 sur self, util≈20) après fix `is_friend` (= `me.team`
1/2, PAS `currentPlayer` 3/4). **RESTE** : (a) `HEAL_RANGE=1` mêlée en dur → portée gameconfig pour
soins à distance ; (b) `tile_util` = `move.move_utility` (MovementSuggestion) en proxy du tile_util
d'action natif (`Default`/`CalculateUtilityFromTilePrediction`) — calibration §3.5 ; (c) intégrer
summon/buff au pool unifié (encore en fallback) ; (d) **non-régression** : tests ciblés attaque/heal
(la branche attaque passe de return-immédiat à candidat-poolé) AVANT commit ; (e) corriger
`native_first`/le harnais d'agreement pour comparer le **chunk complet** (move ∧ ability).

### 3.3 Longue traîne des ~351 leaf playbooks bespoke
Catalogue `InitializePlaybookBuilders` @1810d02b0 = 351 entrées. Les communs sont faits ;
les **bespoke** (`Loki.*`, SaviorProtocols, …) = ajouts incrémentaux **agreement-driven**.
- Reste : finir le **join clé<->classe** (décompiler chaque `b__31_N`) + porter gate+énumération+clés.
- Poids **extractibles offline** (`playbook_keys.py`) — pas un blocage. cf. [`playbooks.md`](playbooks.md).

### 3.4 Pathfinding non-Walk + portée
- **Fly / ATeleportPathfinder** non portés (u96-like ; mapper id d'effet téléport <-> type pathfinder).
- `MovementRangeWithAppliedBonus` @18109cdc0 : bonus de portée / réductions / **enracinement** (range 0) non câblés.
- **Elevation** : pas de data d'élévation par tuile dans `decisionView` (terme omis).

### 3.5 Raffinements (non bloquants)
- `order_strategy` exacte de `PickNextUnit` (un ordre `UnitOrder` + priorité suffit pour l'instant).
- Prédicat de validité exact `FUN_18004cc80` (remplacé par filtre de légalité via `abilityReason`/`abilityTargets`).
- **Fix64** exact : nécessaire pour l'agreement sur la VALEUR d'utilité ; **inutile pour l'argmax** (= la décision). On compare l'argmax.
- Données statiques restantes : signes/poids par-feuille des composites ; 26 leaves Tile(7) en stub=0 (manque métadata par-tuile : effets/steppable/occupant).

## 4. Modèle mental

La **fidélité de la DÉCISION** dépend surtout de §3.1 (prédiction non-dégât) et §3.2 (ordre inter-catégorie),
PAS de plus de précision sur la position (rendement nul confirmé). Les playbooks bespoke (§3.3) ferment
la longue traîne. Le reste (§3.5) est cosmétique pour l'argmax.

L'**architecture d'override** (la raison de réimplémenter : rendre chaque décision modifiable) est
décrite dans [`architecture.md`](architecture.md) — base fidèle mesurée vs natif + couche de modifiers opt-in tracés.
