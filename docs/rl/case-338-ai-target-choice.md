# case-338 — le choix de cible de `PerformAIAttack` est le moteur d'utilité, pas la distance

**Résidu fermé** : `#334-r1`. **Portée** : les **8 fichiers** de `engine/**` qui traversent le corps
unique `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`.

## 1. Le fait

`perform_ai_ability_unit_behaviour` (`engine/runner/abilities/loki/summon.py`) choisissait sa cible
par `_nearest_enemy` (ennemi vivant le plus proche, tie-break `id`). Le natif ne choisit rien : il
délègue.

```
PerformAIAbilityUnitBehaviour$$Execute                       (behaviour+0x50 = sélecteur d'ACTEURS)
  abilityId = <behaviour+0x68>(actor)                        Func<IEntity,int>
  AiControl$$ExecuteAbilityActionFor(actor, abilityId, {allowOnlyMove, skipAtomic, true,
                                                        Nullable<int> moveAmount, customUtility})
    DefaultAiUnitTactic.<CalculateAbilityActionForUnit>d__6$$MoveNext
      actionTiles = ABaseAiUnitTactic$$GenerateActionTiles(unit, true, <d__6+0x34>)
      generators  = [ new ActiveAbilityActionGenerator({abilityId}, …) ]
                    + [ tactic+0x58 MovementActionGenerator ] si allowOnlyMove
      -> ActiveAbilityActionGenerator.<GenerateActions>d__7 -> Bucket$$ChooseAction
      -> InputBuilder$$GenerateInputMessagesFromUnitAction(action, unit, mainTile, { 1, …, … })
```

Trois points lus au décompilé, chacun load-bearing :

* **UN seul générateur, sur un set d'UNE ability** (`OrderedSet<int>` à `generator+0x28`, testé par
  `abilityIds.Contains`) — là où `CalculateNextActionForUnit` (`d__5`) en instancie six.
  Réutiliser `decide_and_apply` (qui mirrore `d__5`) aurait donc été un **fork**.
* **L'ability est l'ATTAQUE NORMALE de l'acteur.** Le `Func<IEntity,int>` de
  `DSLBehaviors$$PerformAIAttack` et de `…PerformAIAttackFromCurrentPosition` a pour corps
  `IdunBattle.Entities.UnitExtensions$$GetNormalAttackType(unit)` (= `ActiveAbilityComponent+0x28`).
  Corps **dédupliqué** : Ghidra ne lui nomme qu'un propriétaire
  (`…ShockAssaultAbility.u003Cu003Ec$$u003CCreateBehaviouru003Eb__1_0`) et **7** slots de delegate y
  pointent — cas d'école de la note « l'absence dans les tables ne prouve rien ».
* **`options[0] = 1`** passé à `InputBuilder` (littéral, contre `{0,0,0}` chez `d__5`) : le
  court-circuit est pris, donc **pas de repli `FinishUnitTurnMessage`** — un behaviour de free-attack
  ne termine jamais le tour de son acteur.

## 2. Le chiffre

Montage `two` de `probe_334_defend_the_divine_work.py` (deux alliés mécaniques attaquant une fois
chacun) — **total identique des deux côtés, répartition fausse** :

| | dégât total | ventilation |
|---|---|---|
| natif | 18038 | **7795 + 10243** sur DEUX ennemis |
| port (avant) | 18038 | **18038** sur UN seul |
| port (après) | 18038 | **7795 + 10243** — exact |

C'est parce que seul le TOTAL était comparé qu'aucun test ne l'attrapait.

## 3. Le port

* `engine/ai/action_generators.py` — `ComparableAbilityGenerator(ability_ids=…)` : mirror du champ
  `generator+0x28`. `None` = comportement historique (tier Comparable complet).
* `engine/ai/tactic.py` — `calculate_ability_action_for_unit(ctx, ability_id, allow_only_move)` :
  mirror de `d__6` ; `input_messages_from_unit_action(…, options_first=1)` pour le court-circuit.
* `engine/ai/state_bridge.py` — `build_from_state(…, max_distance=…)` : mirror du 3ᵉ argument de
  `GenerateActionTiles`. `0` ⇒ tuile courante seule.
* `engine/runner/operations/summon_ai.py` — `ai_control_execute_ability_action_for(…)` : mirror
  d'`AiControl$$ExecuteAbilityActionFor` (surcharge `options`). Il **lève** au lieu d'avaler : un
  échec de bridge rendu en « pas d'attaque » se lirait comme une mesure.

`range_gate` : la portée EFFECTIVE (`_in_attack_range`, mirror `TargetingQuery$$GetRange`, clamp
`ForcedInMelee 0x529` inclus) **borne l'énumération des cibles** au lieu de couper après coup —
c'est ce que fait `BasePlaybook$$GetEligibleTargetsForNormalAttack`. Sans elle, le moteur pouvait
élire une cible que l'acteur ne peut pas frapper (les plans offline sont bornés par
`_max_attack_range` gameconfig, qui ignore le clamp), et l'appelant n'avait plus qu'à ne rien faire.

## 4. Validation

* **Oracle direct** — `test_defend_the_divine_work_live.py` verrouille désormais le delta HP **par
  ennemi** (régimes `attack` et `two`), plus seulement le total.
* **Régime indépendant** — `probe_338_ai_target_choice.py` / `test_ai_target_choice_live.py` :
  `AberrantHypermorph` (1166), deux ennemis à distance **égale** (1) de la tuile de spawn, `maxHP`
  d'un ordre de grandeur d'écart. À distance égale `_nearest_enemy` ne peut départager que par son
  tie-break `id` ; le moteur d'utilité suit le `maxHP` (`healthDmg/(maxHP+1)*100`).

  | `maxHP` bas sur | `_nearest_enemy` | natif | port |
  |---|---|---|---|
  | `orksKillaKan` (grand id) | `orksWarboss` | **`orksKillaKan`** | **`orksKillaKan`** |
  | `orksWarboss` (petit id) | `orksWarboss` | **`orksWarboss`** | **`orksWarboss`** |

  Le second régime n'est pas discriminant *par construction* : c'est la contre-épreuve de bascule.
* **Les deux gardes ont été vérifiées ROUGES** en remettant `_nearest_enemy`.

## 5. Ce qui n'est PAS couvert

* **R31 reste OUVERT** (résidu jumeau, hors périmètre) : `move_amount is None` n'ouvre PAS la plage
  de déplacement. `ai_control_execute_ability_action_for` force `max_distance=0` dans les DEUX
  branches — l'ouvrir sans porter l'apply du `MoveUnitMessage` ferait calculer l'attaque depuis une
  tuile où l'unité n'est pas. Ce qui est fermé de R31 : « un seul générateur sur une seule ability ».
  Ce qui reste : `GenerateActionTiles(null)` + `MovementActionGenerator` + l'apply du déplacement.
* **`customUtility`** (`behaviour+0x90`, seul `TheQuickening` en pose un) : threadé jusqu'à
  `calculate_ability_action_for_unit` et **ignoré**. Le résidu est désormais localisé là.
* **Branche NonComparable de `d__6`** : aucun call-site (les deux nœuds passent
  `GetNormalAttackType`, qui est Comparable) — non portée, non spéculée.
* **Montant de l'attaque du régime 1166** : le natif buffe le summon à l'apparition (`Hypermorph`
  → `UnitStats_Attack_Modification`), passive non portée. Résidu PRÉ-EXISTANT, déjà nommé par
  `test_aberrant_hypermorph_live`, sans rapport avec le choix de cible — d'où le verrouillage de
  l'IDENTITÉ de la victime et non du montant sur ce régime-là.
