# case-348 — un acteur de free-attack S'APPROCHE

**Résidu fermé** : `#338-r1` / R31. **Portée** : les **8 consommateurs** du corps unique
`IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`.

## 1. Le fait

Le port forçait `max_distance = 0` dans les DEUX branches et n'appliquait AUCUN déplacement. Le natif
passe le `Nullable<int>` de `behaviour+0x78` **tel quel** :

```
DefaultAiUnitTactic.<CalculateAbilityActionForUnit>d__6$$MoveNext          (relu, rnca9r7q6c)
  actionTiles = ABaseAiUnitTactic$$GenerateActionTiles(unit, ignoreFlags: 1, <d__6+0x34>)
                                                                 ^ littéral      ^ moveAmount
  generators  = [ ActiveAbilityActionGenerator({abilityId}, …) ]
                + [ tactic+0x58 MovementActionGenerator ] si <d__6+0x30> allowOnlyMove
AiControl$$ExecuteAbilityActionFor(unit, abilityType, options)             (surcharge `options`)
  while (e.MoveNext()) ;  ApplyAiMessages(this, e.Current)                 -> MoveUnitMessage
                                                                              puis ActiveAbilityMessage
```

`0` (`Direct(0)`, nœud `…FromCurrentPosition`) ⇒ la tuile courante seule ; `null` (nœud
`DSLBehaviors$$PerformAIAttack`) ⇒ la **plage de déplacement normale**. `d__5`, lui, passe
`GenerateActionTiles(unit, 0, 0)` — `ignoreFlags` **false** : les deux entrées diffèrent aussi là.

**Contrainte d'ordre, load-bearing** : l'apply du `MoveUnitMessage` a été porté EN PREMIER. Ouvrir la
plage sans lui ferait calculer l'attaque depuis une tuile où l'unité n'est pas.

## 2. Le chiffre

`probe_348_ai_approach.py`, porteur `ForwardSpotter` (1143, MoW `astraOrdnanceBattery`) — son masque
`0x40000422` porte `TargetIsFriendly`, donc le guardsman naît adjacent à un **allié choisi** : la
distance spawn↔ennemi est pilotable au hex près.

| régime | d(spawn, ennemi) | natif | port avant | port après |
|---|---|---|---|---|
| `approach` | 5 | tuile 15 → **35**, −9667 | reste en 15, **0 dégât** | 35, −9667 |
| `stay` | 2 | reste en 15, −6655 | idem | idem |
| `touch` | 1 | tuile 15 → **33**, −6655 | reste en 15 | 33, −6655 |
| `move_only` | 9 | tuile 13 → 16, 0 dégât | reste en 13 | 42, 0 dégât |

`touch` est le régime qui surprend et qui compte : **le natif change de tuile alors qu'il peut déjà
frapper** — l'argmax porte sur le couple (tuile, cible), pas sur « suis-je à portée ». Ce pas
déclenche le vecteur after-move de la cible (overwatch), qui peut tuer l'acteur avant son attaque.
C'est le natif, et deux montages offline l'ont pris pour une régression du port.

## 3. Le port

* `engine/runner/operations/summon_ai.py` — `ai_control_execute_ability_action_for` passe
  `max_distance=move_amount` ; `range_gate` devient **position-aware** `(target, tile) -> bool` et
  élague les `ranked` tuile par tuile (mirror de `GetEligibleTargetsForNormalAttack`, que
  `ComparablePlaybook.EvaluateInternal(unit, position, ctx)` réévalue à chaque position).
* `engine/runner/abilities/loki/summon.py` — `_apply_move_message` : le `MoveUnitMessage` passe par
  `MovementHandler.visit_MoveUnitMessage` (donc `MoveUnitOperation$$Execute` **+
  `EvaluateAfterMoveTriggers`**), jamais par un `MoveUnitOperation` recâblé.
* `engine/runner/operations/triggers/base.py` — `_in_attack_range(..., from_pos=)`.
* Contrat de retour **inchangé** : `None` = aucune ATTAQUE. Un déplacement pur mute l'état et rend
  `None` — les 8 consommateurs ne tiennent que la comptabilité des attaques.

## 4. Validation

* **4 gardes live** (`test_ai_approach_live.py`), toutes vérifiées **ROUGES** par mutation :
  `max_distance=0` → `approach` et `move_only` tombent ; apply neutralisé → `approach` tombe (le port
  ne bouge ni ne frappe : le double filet `_in_attack_range` interdit l'attaque illégale).
* **Non-régression** : `test_perform_ai_attack_node_live` (5), `test_ai_target_choice_live` (2),
  `test_defend_the_divine_work_live`, `test_the_quickening_live`, `test_aberrant_hypermorph_live`,
  `test_summon_consumers_live`, `test_mow_groups_bcd_live`, `test_astramilitarum_targeting_live`,
  `test_repair_execution_live`, `test_repair_decision_rail_live` — verts.
* **Deux montages offline recalibrés** (ils lisaient la position FINALE là où ils voulaient le point
  de chute) : `test_perform_ai_attack_node_live` D/E et `test_scarab_summon_migration_live`. Les
  émissions `SpawnUnit` portent désormais `pos` (tuile d'atterrissage).

## 5. Ce qui n'est PAS couvert

* **Le SCORING de mouvement**, en régime `move_only` : le natif élit 16, le port 42. Décomposition
  par étage — la tuile du natif **est** dans l'ensemble de candidats du port ⇒ `GenerateActionTiles`
  est bon, l'écart est dans `move.best_move_faithful`. Non comparable ici de toute façon (point
  suivant).
* **Identité du summon** : le port matérialise le `unitId` du gameconfig (`astraSmnGuardsman`, traits
  `[Summon, BattleFatigue]`), le jeu matérialise `astraNpc1Guardsman` (`[BattleFatigue]`) — même kit
  d'arme et de mouvement, mais le composite de mouvement lit les traits. Résidu PRÉ-EXISTANT de
  `SpawnUnitOperation`.
* **`customUtility`** (`behaviour+0x90`) : threadé jusqu'à `calculate_ability_action_for_unit` et
  ignoré. Seul `TheQuickening` en pose un.
* **Une TROISIÈME forme du couple, non portée** : sur les **7** xrefs de
  `DSLBehaviors$$PerformAIAttack`, six passent `(sel, 1, 0, 0, 0)` ; `AetherStrideAbility$$ExecuteBehaviour`
  passe `(targets@0x68, 0, <DSLFormulas+0x18>, 0, 0)` — `allowMoveAction` FAUX et un `moveAmount`
  ENTIER (nœud `IAmount`). `build_from_state` traite toute valeur ≠ `0`/`None` comme `0`. Inerte :
  1208 `AetherStride` (`thousDaemonPrince`) n'est pas portée.
