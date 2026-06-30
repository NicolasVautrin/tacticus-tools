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

### 3.1 Prédiction NON-dégât offline (heal / repair / effet) — **le gros bloqueur structurel**
`aiPredict` = `GetAllPredictions` = **dégât seulement**. Le scoring fidèle des abilities à
SOIN / RÉPARATION / EFFET (et le dégât BOUCLIER `Avg(shieldMinMax)`) est bloqué à la source.
- Gates/tags/custom-utility de Heal/Repair sont **déjà portés** ; il ne manque que la **magnitude prédite**.
- **Voie ouverte** : re-dériver les montants depuis **gameconfig** (`variables[clé][niveau]` + constants — soin/repair inclus), comme on l'a fait pour le dégât (cf. [`prediction.md`](prediction.md) §offline). OU un RPC de prédiction complet (damage+heal+effets).

### 3.2 Bucket-tree INTER-catégorie (ordre summon vs heal vs move vs attack) — **pas encore RE**
La sélection DANS une catégorie = RE'd (argmax). L'**assemblage du bucket racine** + les clés
d'ordre entre catégories d'utilité non-comparables (summon ~0-6 vs kill ~100 vs move ~100s) =
non RE. C'est le « vrai correctif attaque-vs-move » des misses résiduels.

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
