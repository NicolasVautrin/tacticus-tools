# Playbooks de DÉCISION genestealer (G4 CultDemagogue, G5 HeroicFusillade)

> Verdict RE (build `gqfc5mff6c`, 2026-07-18). Ferme la question de la « face prédiction »
> des slices genestealer (tâche #15) : **il n'y a AUCUNE prédiction de dégât native pour ces
> abilities** — ce sont des playbooks **NonComparable / bespoke**, dont la décision est une
> heuristique directe. Le terme « prédiction » était donc mal employé ; il s'agit de la **face
> DÉCISION**.

## 1. Rappel d'architecture

`BasePlaybook -> { ComparablePlaybook<T>, NonComparablePlaybook<T> }`.

- **Comparable** (attaques/soins) : `EvaluateInternal @181408980` boucle les cibles, score chacune
  via `CalculateActionUtility` = Σ **prédictions de dégât** (`MakeDamagePredictions`, vtable) + effets
  + tuile, puis argmax. → la prédiction n'est qu'un **input de scoring**.
- **NonComparable** : `EvaluateInternal @18149e900` appelle juste le virtuel `EvaluateNonComparable`
  (vtable +0x318) qui **génère directement les actions** (bucket), **sans aucune `MakeDamagePredictions`**.

## 2. Les deux actifs genestealer sont NonComparable / bespoke

| Ability | Playbook natif | Type | MakeDamagePredictions | cctor MIN_UTILITY |
|---|---|---|---|---|
| **HeroicFusillade** (1180, Judh) | `HeroicFusilladePlaybook` @181144ac0 | `NonComparablePlaybook<T>` (arg ctor `0x49c`=1180) | **ABSENT** | `FromInt(1)` = **1** (@181144a50) |
| **CultDemagogue** (1179, Isaak) | `CultDemagoguePlaybook` @1811280f0 | `EvaluateInternal` **override bespoke** @1811278c0 | **ABSENT** | `FromInt(1)` = **1** (@181128080) |

- **HeroicFusilladePlaybook.EvaluateNonComparable @181144510** : bucket MIN_UTILITY=1 ;
  `GetEligibleTargetsSelectable` ; par cible éligible qui passe les gates, utilité **plate = 1**
  (`Fix64.FromInt(1)`), `GenerateAction` + `AddAction`. Gates observés (À CONFIRMER par le port
  fidèle) : `HasTrait(<item>, 0x10=Hero)` + présence d'un ennemi dans la liste `slot 0x76`
  (`IsEnemy`). L'identité exacte de `<item>` (cible vs caster embarqué) reste à trancher —
  ne PAS l'inventer.
- **CultDemagoguePlaybook.EvaluateInternal @1811278c0** : bucket MIN_UTILITY=1 ; par cible éligible :
  `utilité = 1 + min(#PossibleTilesForDecoys, GetDecoyAmount(pos)) × W + (#FriendlyDecoysAroundTarget
  + #FriendlyNeophytesAroundTarget) × W`, où `W = Playbook.GetUtilityValue(<UtilityType DAT_18327dcc8>)`
  et les « AroundTarget » via `TargetsSelector.SelectUniqueUnits(..., 3)` → `.Count`. VAs des helpers :
  `PossibleTilesForDecoys @1811ce650`, `GetDecoyAmount @1811ce240`, `FriendlyDecoysAroundTarget
  @1811ce0f0`, `FriendlyNeophytesAroundTarget @1811ce190`. Le `UtilityType` nommé reste à identifier.

- **G1 (fondation Decoy) / G2 (DecoysAndMisdirection)** = **passifs** → aucun playbook actif, aucune
  décision d'ability à porter (normal).

## 3. Le vrai gap dans le port

Dans notre port, 1180 et 1179 sont enregistrés côté **runner/exécution** (`handler.py`) mais **absents
du layer playbook** (ni `engine.playbook.base.REGISTRY` Comparable, ni le registre NonComparable de
`noncomparable.py`). → la décision offline les route sur `DefaultActiveAbilityPlaybook` (prédiction
générique Comparable) = **DIVERGENCE** vs le natif NonComparable.

**Fix** = porter 2 playbooks NonComparable dans `engine/playbook/noncomparable.py`, sur le motif des
classes déjà portées fidèlement : `BloodyFuryPlaybook` (@181122be0, `1 + #adj×10`), `AberrantHypermorphPlaybook`
(@1811197d0, move+summon), `VexillaMagnificaPlaybook`, `FightingRetreatPlaybook`.

## 4. Validation

Face DÉCISION → `engine_validate.py --runner <rid>` (agreement playbook) sur un roster genestealer
(Judh/Isaak buildables en lineup) : comparer l'action choisie offline vs l'IA live. (Contrairement à
NovaBoost/Riptide « arène-inagreable », ces unités se spawnent.)

### Baseline AVANT port (routing DÉFAUT, 2026-07-18)

`rl_duel build --seed 777 --p-units genesKelermorph,genesPrimus --a-units orksNob,orksNob
--board-pool pvp` puis `engine_validate --runner 33 --steps 14` :

- **step 4** u81 Judh : natif=normal(69)->77, engine=**HeroicFusillade(1180)**->79 -> MISS
  (l'engine SUR-choisit 1180 via la prédiction générique).
- **step 5** u83 Isaak : natif=**CultDemagogue(1179)**->79, engine=normal(69)->79 -> MISS
  (l'engine NE choisit JAMAIS 1179 : pas de prédiction de dégât -> non candidate).
- **step 8** u81 Judh : natif=normal(69)->79, engine=**HeroicFusillade(1180)**->79 -> MISS (idem step 4).
- Positionnement 7/7 (100 %) ; abilities **2/7 (28 %)**. (steps 6-7 = ability orks 1152, hors périmètre.)

**Cible post-port** : steps 4/5/8 -> MATCH (Judh joue normal quand le gate NC de HeroicFusillade ne
passe pas ; Isaak joue CultDemagogue). Le gate restrictif de HeroicFusillade (Hero + ennemi voisin)
est CRUCIAL : sans lui, le port sur-choisirait 1180 comme le défaut actuel.

### Résultat APRÈS port (2026-07-18) — TOUS les steps genestealer MATCH

`engine_validate --runner <rid>` (même seed/roster) : **steps 4/5/8 -> MATCH** (Judh normal 69 / Isaak
CultDemagogue 1179 / Judh normal 69). Ability agreement **28% -> 71% (5/7)** ; positioning 100%. Les 2
misses restants (steps 6-7) = ability **orks 1152** (ennemi, hors périmètre). A/B seed-777 roster par
défaut : agreement INCHANGÉ (42% ability / 56% pos avant == après) -> **zéro régression**.

### VERDICT ARCHITECTURAL (re-expert) — 2 corrections vs l'hypothèse initiale

1. **CultDemagogue (1179) = ComparablePlaybook bespoke**, PAS NonComparable (ctor @1811280f0 =
   `ComparablePlaybook(0x49b)`). Home = `bespoke_heals.py` + dict `BESPOKE_SELFCAST` (régime Comparable,
   dispatch `_bespoke_candidates`), PAS `noncomparable.py`. Formule VA-citée @1811278c0 :
   `u = 1 + min(#tuilesLibresAutourCaster r2, nrOfSummons[lvl]) x W + (#decoys + #neophytes amis autour
   cible r2) x W`, **W=20** (`CultDemagogue_FriendlyDecoysAndNeophytes`, MÊME poids les 2 termes),
   MIN_UTILITY=1. `nrOfSummons` = 4->8 (NON rarity-scaled).
2. **HeroicFusillade (1180) = NonComparablePlaybook** (ctor @181144ac0 = `NonComparablePlaybook(0x49c)`),
   util PLATE=1, gates `HasTrait(cible,Hero)` + `>=1 ennemi ring-1 de la cible` (slot 0x76
   GetSurroundingUnits). Home = `noncomparable.py` + dict `PLAYBOOKS`.

### La pièce structurelle manquante : filtre `is_noncomp` dans le tier Comparable

Le vrai bug (steps 4/8) : le tier Comparable (`ComparableAbilityGenerator._best_attack`) itère les
`attackPlans.evals` et repêchait 1180 via le fallback générique **même après** que son playbook NC ait
gaté (`[]`). Or `InitAbilityTypeLists @1810ed540` range chaque ability dans **UN SEUL** tier (flag
IsComparable) : une NonComparable n'est JAMAIS évaluée par le Comparable. Fix = skip
`playbooks.is_noncomp(ab)` en tête de `_best_attack`. **C'est ce skip, pas les gates, qui a fait basculer
steps 4/8** (les gates NC retournaient déjà `[]` correctement). Changement général mais neutre (A/B
seed-777 inchangé) : une NC en attackPlans est désormais routée au tier NC seul, fidèle au natif.

### Fichiers du port (mutations moteur)
- `engine/playbook/bespoke_heals.py` : `CultDemagoguePlaybook` + entrée `BESPOKE_SELFCAST`.
- `engine/playbook/noncomparable.py` : `HeroicFusilladePlaybook` + entrée `PLAYBOOKS`.
- `engine/ai/action_generators.py` : skip `is_noncomp(ab)` dans `_best_attack`.

### Chemins NON encore exercés (à valider séparément)
- **CultDemagogue terme 2** (#decoys/#neophytes amis autour cible) : =0 au 1er cast (aucun summon sur le
  board) -> le port a matché sans exercer ce terme. À valider après un cast qui pose des decoys.
- **HeroicFusillade multi-cibles** : ici 1 seule cible passait les gates -> l'ordre de tie (keep-first)
  non exercé.
- Flags v1 re-expert : `nrOfSummons` index (confirmé gameconfig), interprétation « friendly around
  target » (déduction), `SelectUniqueUnits` count != cap 3.
