# Playbook Engine — état de validation & ce qui reste

> La réponse directe à « **qu'est-ce qui nous manque pour reproduire fidèlement l'IA ?** ».
> Métrique = agreement vs l'IA native sur le MÊME état (`engine_validate.py`, `aiStepDryRun`).

## 1. Agreement actuel

> ⚠ **MàJ (harnais chunk-complet, §3.2 (e))** : `native_first` a été remplacé par `native_chunk`
> (compare move ∧ ability du chunk COMPOSÉ, plus seulement le 1er message). Ça a **révélé un
> FAUX-VERT** : l'« ability 100 % » ne mesurait QUE les casts in-place — les casts **composés**
> (move+attaque/soin) étaient invisibles à la métrique ability. Vraie mesure (seed 777, 14 pas) :
> **ability 30 % (3/10)**, positioning **61 % exact / 84 % ≤1 hex** (13 moves). Les désaccords
> révélés étaient **pré-existants** (boucle `best`/tiers), juste masqués. ⇒ le pytest
> `test_ability_selection_matches_native` (exige 100 %) échoue désormais **à juste titre**.

| Axe | Mesure (harnais chunk-complet) | Seed |
|-----|--------|------|
| Décision — **positioning** | **61 % exact / 84 % ≤1 hex** (13 moves) | 777 |
| Décision — **ability** | **30 % (3/10)** — casts composés enfin comptés | 777 |
| **Prédiction de dégât** (xmod) | **11/11** (u90 fermé) | 777 |
| **Pathfinding** WalkPathfinder | **4/4 EXACT** (à la stat Movement réelle) | 777 |

**Désaccords ability révélés (à porter — §3.2/§3.3)** : (1) **tier tie-break** = le `Preference` par-ability
(`InitAbilityTypeLists`), PAS le « spécial>normal » codé en dur (ex. natif normal `69` vs moteur `1171`) ;
(2) **target tie-break** (même ability, cible différente) ; (3) **abilities non-attaque** non modélisées
(self-buff `1081`, etc. → le moteur retombe sur l'attaque). C'est la vraie longue traîne de fidélité ability.

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
1/2, PAS `currentPlayer` 3/4). **RESTE** :
- (a) ~~`HEAL_RANGE=1` → portée gameconfig pour soins à distance~~ **NON — vérifié gameconfig : les soins
  d'allié ciblés n'ont AUCUN `range` constant → adjacents (range 1), `HEAL_RANGE=1` est CORRECT.** Les seules
  abilities « heal » avec `range` sont du **vol de vie sur attaque** (`healthPct`, soin du lanceur, range =
  portée d'attaque → chemin DÉGÂT) ou du **soin global count-based** (RitesOfRestoration `nrOfHeroes`/
  `nrOfSummons`, sans tuile-cible). Vrai reste = ces deux **modes** (self-cast global + vol de vie), pas la portée.
- (b) `tile_util` **RE fait** (cf. [`architecture.md`](architecture.md) §2.3ter). Résultats (décompilé) :
  (1) le terme de tuile natif = `CalculateUtilityFromTilePrediction @181408740` = composite **`Tile(7)`**
  évalué sur `UtilityMovementCase(caster, tuile-prédite)` — **déjà porté** = `engine/utilities/tile.py::
  tile_composite` (sa docstring le cite). Il n'y a PAS de profil `MovementSuggestion` de scoring IA : le BC
  n'a que `Default` (54 groupes, IA) + `MovementSuggestion` (1 groupe = overlay UI swipe). Sur carte plate
  `Tile(7) ≈ 0`. (2) La **tuile du caster** vient du **prédicteur `vtable +0x398`**, PAS d'un balayage
  `move_utility` → `move.move_utility` n'est PAS le mécanisme natif (il a matché Rotbone par coïncidence).
  **+0x398 RÉSOLU (vtable runtime via Frida, voie 1)** = **`MakeFinalTilePrediction` = identité**
  (`mov rax,r8;ret` @0x1803088d0, retourne la position candidate inchangée ; même stub pour Heal/Repair/
  MightFromBelow — base de tout `ComparablePlaybook`). ⇒ H2 confirmée, H1 réfutée : aucun terme d'utilité
  ne discrimine la tuile d'un soin plat (Tile7≈0 + CasterPositionUtility=0). **Énumération des tuiles RE'd**
  (architecture.md §2.3quater) : le **générateur** `ActiveAbilityActionGenerator.MoveNext @18119a3f0` énumère
  les tuiles de mouvement, `Evaluate(unit, tuile)` (EvaluateInternal, qui lui énumère les CIBLES à tuile
  fixée) par tuile, `Bucket.Merge` puis `ChooseAction` (argmax, **premier sur égalité** `>` strict, action-top
  si légale). ⇒ **le sweep `tuile × cible` + argmax du moteur EST le modèle natif** ; seul le terme de tuile
  diffère (natif = `CalculateActionUtility`, pas `move.move_utility`). **(b') CLOS** — les 2 termes RE'd
  (architecture.md §2.3quater) : `CalculateUtilityFromPredictions @181407890` = Σ event-utilities au tile
  (VARIE par tuile pour une ATTAQUE via le dégât/kill prédit ; CONSTANT pour un self-heal) ; key-0x36 =
  UtilityType **54 = `WireweaveNet_FirstAttack`** (dump.cs ; le label journal « position caster » était FAUX),
  gaté cible-adjacente + effet 1111 → **0 pour un heal**. ⇒ **(1,2) d'un self-heal plat = tie-break (première
  tuile énumérée), PAS un engage** ; `move.move_utility` DÉFINITIVEMENT unfaithful. **Fix moteur** : tuile
  d'attaque = argmax `CalculateUtilityFromPredictions@tuile + Tile7@tuile` (dégât prédit, déjà portable) ;
  tuile de self-heal = arbitraire (répliquer l'ordre d'énumération @0x68, ou accepter le wash). **Zéro empirisme.**
  - **✅ IMPLÉMENTÉ + MESURÉ** (`engine_validate.py::engine_decide`) : `move.move_utility` **RETIRÉ** du
    scoring d'action, remplacé par le helper `_tile_term` = **`tile_composite` (Tile7)** (élévation/temp via
    tileMeta ; ctx par-unité non plombé → feuilles situationnelles=0, dégradation native). Branche soin :
    `reach` = **destinations de mouvement** (origin en fallback seul) → le natif BOUGE (§2.3quater). Mesures :
    **seed 31337 = 100% exact / 100% ≤1hex** ; **seed 777 = 72% exact / 90% ≤1hex** (≥ baseline 55/77) ;
    **Rotbone move+heal reproduit** (ability 18 self EXACT ; tuile (1,1) vs natif (1,2) = **≤1hex**, tie-break
    tile-indépendant : ordre RPC `aiMovableTiles` ≠ ordre énumérateur natif @0x68 — wash, documenté). Pas de
    régression ability (le seul MISS seed-777 = ability 1167 identique, cible 88 vs 94, vient de la boucle
    `best` NON modifiée). **RESTE** : agreement exact tuile self-heal = ordre @0x68 (deferred, wash).
- (c) intégrer summon/buff au pool unifié (encore en fallback).
- (d) **non-régression** : tests ciblés attaque/heal (la branche attaque passe de return-immédiat à
  candidat-poolé) AVANT commit.
- (e) ✅ **FAIT** — `native_first` → `native_chunk` : le harnais compare le **chunk complet** (move ∧
  ability), chaque chunk composé contribue aux DEUX métriques. A révélé le faux-vert ability (cf. §1).

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
