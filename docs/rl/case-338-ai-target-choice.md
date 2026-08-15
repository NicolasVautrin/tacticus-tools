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

⚠ **Et « borner par la PORTÉE » ne suffisait pas — le domaine natif est la CASCADE entière**
(#334-r2, 2026-08-11). `GetEligibleTargetsForNormalAttack(caster, casterPosition)` tient en une
ligne : `battleQuery.<slot 0x42>(caster, casterPosition, UnitExtensions$$GetNormalAttackType(caster))`,
et cette surcharge — `IdunBattle.Core.Services.BattleQuery$$GetValidTargets(unit, from, abilityType)`
— délègue au **slot 6 de `ITargetingQuery`**, c'est-à-dire au même filtre que
`get_invalid_target_reason`, pas à une comparaison de distance. Mesuré sur le montage `two` :
`admecDestroyer` porte `max_range = 3`, donc `_in_attack_range` acceptait l'ennemi `110` (distance 2)
que la cascade **refuse** par `TargetingRule.TargetIsInRange` (`only_adjacent` de ses
`TargetingOptions` d'attaque normale) — `valid_normal_attack_targets` ne rendait que `[79]`, et le
natif frappait `79`. Le gate porte donc désormais **les deux** : portée depuis la tuile candidate,
puis cascade complète **sur la tuile courante** (la cascade du port n'a pas de variante « depuis une
tuile hypothétique » — écart nommé, borné au régime d'approche de `PerformAIAttack`).

Ce que ça n'a PAS fermé : avec **deux** acteurs enchaînés, le 2ᵉ diverge encore — même domaine des
deux côtés, choix différent (résidu **#334-r3**). Discriminant mesuré : le **même** acteur, **seul**
(régime `attack`), est **bit-exact** avec le natif (`4670` sur l'entité `110`, ventilation confrontée
par ENTITÉ des deux côtés).

### 3bis. #334-r3 RE-MESURÉ (2026-08-15) — ce n'est PAS un choix de cible, c'est un coup EN TROP

**L'énoncé du résidu était mal posé, et ses deux hypothèses avec lui.** Il décrivait une
REDISTRIBUTION à total constant (« port : `85 → 79` puis `83 → 110` ; natif : tout sur `79` »). Les
totaux, eux, **diffèrent** — et l'entité `79` reçoit **exactement le même montant des deux côtés** :

| régime (board `MC1_67`, seed 777, `--advance 4`) | port, par entité | natif, par entité | total port / natif |
|---|---|---|---|
| `two` | `79: −18371`, `110: −4986` | `79: −18371` | 23357 / **18371** |
| `two_blind --blind admecRuststalker` | `79: −18371`, `110: −4548` | `79: −18371` | 22919 / **18371** |

Deux runs indépendants, **géométrie identique** (caster (5,5), acteurs (5,4) et (6,4), ennemis 77/79/110/112).
`79` retombe sur `−18371` **à l'unité près** des deux côtés et dans les deux runs ; seul le dégât
porté à `110` bouge, et **uniquement côté port**. Le natif n'inflige **rien** à `110`.

⇒ **Le 2ᵉ acteur ATTAQUE alors que le natif ne le fait pas attaquer.** Le port n'élit pas la
mauvaise cible : il émet une attaque surnuméraire. C'est aussi pourquoi la ventilation d'origine
semblait « redistribuée » — `attacks[].total` (10710) n'est **pas** la perte HP appliquée (18371) :
le vecteur **after-hit** (`On(0x26)`/`On(8)`/`On(9)`, rendu séparément dans `after_hit`) s'y ajoute.
Lire `attacks[].total` comme un delta HP était l'erreur de lecture d'origine.

**H1 est RÉFUTÉE, au décompilé.** `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`
décide **et** applique **par acteur, dans la même itération** (`<slot 0x37>` =
`IdunBattle.Core.Services.AiControl$$ExecuteAbilityActionFor`, appelé dans la boucle du sélecteur
`+0x50`) : les deux côtés voient donc le **même** état séquentiel. Le mécanisme est partagé — il ne
peut pas produire l'écart à lui seul.

**Le montage discriminant par la GÉOMÉTRIE est insatisfiable**, et c'est mesuré : `admecDestroyer`
porte une portée d'arme de **3**, donc il ne peut pas être à la fois adjacent au caster et hors de
portée de l'ennemi que le caster jouxte (`range_diag` le montre : `79: (True, 0)` depuis sa tuile).
Le levier de STATS le remplace — `probe_334_defend_the_divine_work.py --scenario two_blind --blind
<visualId>` pose `Damage = 0` sur un acteur sans toucher aux positions. Il **mord partiellement** :
sur `admecDestroyer` l'attaque tombe à `total = 0` ; sur `admecRuststalker` elle tombe de `6814` à
`2211` sans s'annuler — l'override `1242` (`Min(maxDmg, Attack_INITIALE × dmgPct)`) ne se réduit pas
au `Damage` de la BC seul. À raffiner avant d'en faire un interrupteur.

**Témoin DÉGÉNÉRÉ à ne pas compter pour un succès** : `two_blind --blind admecDestroyer` rend port et
natif **sur la même cible** (`77`, 8397 / 8452) — mais le montage y donne à `admecRuststalker` un
domaine **SINGLETON** (`ids : {admecRuststalker: [77]}`), donc le choix est forcé et l'accord ne
montre rien.

**Ce qui reste OUVERT** : pourquoi le natif ne fait-il pas attaquer le 2ᵉ acteur ici, alors qu'il le
fait dans le régime où le 1ᵉʳ est neutralisé ? La différence est que le 1ᵉʳ a attaqué avant lui.
Piste non tranchée, à lire au décompilé : ce qui, dans `AActiveAbility$$Execute` / le
`skipAtomicCheck` (`behaviour+0x71`) ou le gate `HasFlag(unit, ActiveAbilityUsed)` du
`ActiveAbilityActionGenerator`, peut rendre le générateur MUET pour le 2ᵉ acteur après la première
attaque du groupe. Le test `test_two_adjacent_mechanics_both_attack_and_the_caster_still_does_not`
reste ROUGE, et son ÉNONCÉ est à revoir : il attend « les deux attaquent », or la mesure dit que le
natif n'en fait attaquer **qu'un**.

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

* **R31 : FERMÉ depuis** (`case-348-ai-approach.md`). `move_amount` est passé tel quel à
  `GenerateActionTiles`, le `MovementActionGenerator` est en queue quand `allowMoveAction`, et le
  `MoveUnitMessage` est appliqué AVANT l'attaque.
* **`customUtility`** (`behaviour+0x90`, seul `TheQuickening` en pose un) : threadé jusqu'à
  `calculate_ability_action_for_unit` et **ignoré**. Le résidu est désormais localisé là.
* **Branche NonComparable de `d__6`** : aucun call-site (les deux nœuds passent
  `GetNormalAttackType`, qui est Comparable) — non portée, non spéculée.
* **Montant de l'attaque du régime 1166** : le natif buffe le summon à l'apparition (`Hypermorph`
  → `UnitStats_Attack_Modification`), passive non portée. Résidu PRÉ-EXISTANT, déjà nommé par
  `test_aberrant_hypermorph_live`, sans rapport avec le choix de cible — d'où le verrouillage de
  l'IDENTITÉ de la victime et non du montant sur ce régime-là.
