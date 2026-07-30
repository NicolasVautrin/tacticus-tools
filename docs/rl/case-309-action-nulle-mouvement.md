# case-309 — l'ACTION NULLE : `FinishUnitTurnMessage` sur l'axe MOUVEMENT

Le `MovementActionGenerator` du port rendait **toujours** une action, là où le natif finit le tour.
Dégradation **permissive** — ni erreur, ni crash, et aucune métrique existante ne pouvait rougir.

**État : LIVRÉ.** Le mirror est `engine.ai.tactic.input_messages_from_unit_action`.

---

## 1. Ce que le natif fait — et ce que l'analogie prédisait à tort

Le cas était posé comme « le pendant, sur l'axe MOUVEMENT, du gate que #17 a porté sur l'axe
ABILITY ». **La lecture du décompilé (`rnca9r7q6c`) réfute cette analogie**, et c'est le premier
résultat de la tranche.

### 1.1 Le générateur de mouvement ne porte AUCUN gate d'unité

`IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CGenerateActionsu003Ed__6$$MoveNext`
(état 0), en clair :

```
if (UnitPosition.op_Equality(startPosition, null))          yield break;
if (UnitPosition.IsEmpty(startPosition))                    yield break;
mainTile = startPosition.MainTile
utility  = overrideUtility ?? new UtilityDefinition(TileExtensions.IsTemporary(mainTile) ? 5 : 6)
closest  = FindClosestEnemy(unit, new UnitPosition(mainTile))     // itérateur, pompé
cases    = new UtilityMovementCase[positions.Count]
foreach (pos in positions)  cases[i++] = new UtilityMovementCase(unit, pos, closest, …)
best     = <generator+0x28>.GetBest(cases, utility)               // itérateur, pompé
if (best == null)                                           yield break;
yield return <action de mouvement vers best.MovementTile>
```

Aucun `HasFlag`. Contraste **direct** avec
`IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`,
dont la première instruction est `if (HasFlag(unit, 2)) return 0`.

La variante multi-tuiles
(`...MovementActionGenerator.u003CGenerateActionsMultiTileUnitu003Ed__7$$MoveNext`) a la même
structure ; elle ne teste que `startPosition == null` (pas `IsEmpty`) et fige `UtilityDefinition(6)`.

### 1.2 …et ses sorties à zéro action ne se produisent jamais en pratique

`positions` lui vient de `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles(this, unit,
ignoreFlags: false, null)` = `GetMovableTilesFor(unit, false, null)`, étendu par les playbooks de
chaque ability de l'unité. Le natif y adjoint la position **courante**
(`BattleQuery$$GetCurrentAndMovablePositionsFor` — déjà consigné dans `engine_validate.run_agreement`).
Pour une unité vivante l'ensemble n'est donc jamais vide : le chooser rend toujours un cas, et le
générateur rend toujours une action. **Sur ce point, le natif se comporte exactement comme le port.**

### 1.3 Le filtre est un cran plus bas — `InputBuilder`

`IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext` ne
rend pas l'action : il sort de sa double boucle (`if (action != 0) break`) avec une action
**éventuellement nulle**, appelle `IdunBattle.AI.Tactics.ABaseAiActorTactic$$LogInvalidUnitAction
(this, unit, action)`, puis :

```
IdunBattle.AI.ActionGenerators.InputBuilder$$GenerateInputMessagesFromUnitAction(
        action, unit, new UnitPosition(mainTile), &options) :

    msgs = new List<IInputMessage>()
    if (action != null) {
        if (UnitPosition.op_Inequality(action.Position, null)
            && !currentPosition.Equals(action.Position))
            msgs.Add(MoveUnitMessage{ unitId, positions })
        if (action.Target != null)
            msgs.Add(ActiveAbilityMessage{ unitId, targetId, abilityType })
    }
    if (options[0] != 0) return msgs            // options = {0,0,0} sur ce chemin
    if (msgs.Count != 0) return msgs
    msgs.Add(FinishUnitTurnMessage{ unitId })   // <=== L'ACTION NULLE
    return msgs
```

**Deux familles produisent donc `FinishUnitTurnMessage`**, et la seconde est celle qu'un gate posé à
l'entrée du générateur aurait manquée :

| famille | condition | ce que le port faisait |
|---|---|---|
| A — action nulle | aucun générateur n'a produit | jamais atteinte (le port rendait toujours une action) |
| B — action inerte | destination absente **ou** égale à la tuile courante, et pas de cible | rendue telle quelle comme un `move` |

Le passage par `LogInvalidUnitAction` avec une action nulle établit que le cas A est **prévu** par le
natif, pas accidentel.

---

## 2. L'angle mort qui l'a laissé vivre

`engine_validate.run_agreement` n'entre dans sa comparaison que sous
`if (nat["move"] or nat["ability"])`. Un pas dont le chunk natif est un `FinishUnitTurnMessage` seul
est journalisé « non comparé, on avance ». **Aucune métrique existante ne pouvait donc rougir** :
`pos`, `ability` et `stay` ignorent précisément les pas concernés.

C'est ce qui rend la dégradation dangereuse : elle est invisible en self-play, et c'est exactement le
trou qu'un entraînement irait exploiter (une unité qui « bouge » gratuitement quand le jeu lui fait
finir son tour).

---

## 3. Ce qui change côté port

| fichier | changement |
|---|---|
| `engine/ai/tactic.py` | **nouveau** `input_messages_from_unit_action(ctx, action)` — mirror 1:1 de `InputBuilder$$GenerateInputMessagesFromUnitAction`, réduit à la forme d'action du port |
| `engine/ai/tactic.py` | `DefaultAiUnitTactic.calculate_next_action` retient l'action du premier générateur non nul **puis la traduit**, au lieu de la rendre brute |

Le `MovementActionGenerator` n'est **pas** modifié : le natif ne le gate pas, le port non plus.

`{"kind": "finish", "to": None}` n'est pas un format neuf : `DefaultMachineTactic` le rendait déjà
(chemin natif dédié `DefaultMachineTactic$$GenerateInputMessagesFromUnitAction`), et il est traduit en
`FinishUnitTurnMessage` par `rl_duel`, `rl_collect_batch` et `stream_events`.

---

## 4. Ce qui est mesuré

`scripts/python/probe_309_movement_null_action.py` — le montage nommé est le couple *(board, seed)*,
reproductible tel quel (roster tiré par la seed, aucun `--p-units`).

Le probe confronte le port **sur les pas que `run_agreement` ne compare pas**, et les ventile en
**trois étages** (`_classify`) — distinction découverte à la mesure, et décisive, parce que les trois
se corrigent à des endroits opposés :

| étage | ce que le port propose | verdict |
|---|---|---|
| `mirror` | une action qui n'émettrait **aucun** message natif (destination absente, ou égale à la tuile courante) | **périmètre de #309** — corrigé |
| `scoring` | un déplacement **réel** vers une autre tuile | hors périmètre : `InputBuilder` émettrait bien un `MoveUnitMessage`, le mirror est **fidèle** en le laissant passer ; le désaccord est dans le CHOIX de tuile |
| `ability` | un cast | hors périmètre : `InputBuilder` émet toujours un `ActiveAbilityMessage` dès que `Target != null`, donc ce sont les générateurs d'ability du natif qui n'ont rien produit — en amont |

Un mirror qui « corrigerait » les deux derniers troquerait un défaut mesurable contre un accord de
façade.

### Chiffres

| montage | pas natifs `finish` seuls | ventilation | bras câblé | bras neutralisé |
|---|---|---|---|---|
| `MC1_67` / 12100 | 1 (sur 40 pas ; move=25, ability=22) | `mirror` 1 | **1/1 accord** | **0/1** |
| `MC1_67` / 909 | 3 | `mirror` 1, `ability` 2 | 1/1 accord | 0/1 |
| `C1_12` / 12100 | 1 | `scoring` 1 | hors périmètre (cf. §5) | idem |
| `C1_03` / {777, 909, 12100, 31337} | **0** | — | montage muet, écarté | — |
| `C1_03` / 4242 | 1 | `ability` 1 | hors périmètre (cf. §5) | idem |

Le pas de `MC1_67` / 12100 est le **step 5, unité `u89`** : le port rendait `move to=None` (branche
`not ctx.move_tiles or not ctx.enemies`), il rend désormais `finish`.

**Non-régression par mutation** (`--noreg`, `MC1_67` / 12100, 40 pas) — le walk d'agreement de
référence est **strictement inchangé** :

```
pos      AVEC mirror={'n': 25, 'exact': 21, 'near': 22} | SANS={'n': 25, 'exact': 21, 'near': 22}
ability  AVEC mirror={'n': 22, 'match': 16}             | SANS={'n': 22, 'match': 16}
stay     AVEC mirror={'n': 6,  'match': 5}              | SANS={'n': 6,  'match': 5}
mirror : 31 appels | intercepte={} | conserve={'move': 9, 'ability': 22}
```

Les **22 actions d'ability vues et conservées** sont ce qui donne son mordant à « aucun cast
avalé » : sans elles, l'assertion serait vraie sans rien prouver.

Bras systématiques : `cable` (mirror actif), `neutralise` (mirror court-circuité = le port d'avant),
`--noreg` (non-régression par mutation), `--scan` (choix d'un montage sur critère **mesuré**).

Garde : `scripts/python/tests/engine/test_movement_null_action_live.py`.

---

## 5. Résidus nommés

- **Étage `scoring` — le port vise une AUTRE tuile là où le natif finit le tour.** Mesuré sur
  `C1_12` / seed 12100, **step 8, unité `u79`** : origine `(3,6)`, **15** tuiles movables, le port
  propose `(4,5)` ; le natif n'émet rien. Le mirror laisse passer — et c'est **correct**, puisque
  `InputBuilder` émettrait un `MoveUnitMessage` pour toute destination différente de la tuile
  courante. Le désaccord est donc dans le **choix de tuile** : soit le chooser natif
  (`<generator+0x28>.GetBest(cases, utility)`) ne retient aucun cas, soit il retient la tuile
  courante et `move.best_move_faithful` en préfère une autre. Les deux se départagent en lisant
  l'utilité attribuée à la tuile d'origine — non fait ici. Voisin des fiches
  `case-193` / `case-201` / `case-206` (scoring `MovementSuggestion`). **Le probe le compte
  séparément pour qu'il reste visible au lieu d'être absorbé.**
- **Étage `ability` — le port caste là où le natif finit le tour.** Réel aussi : `C1_03` / seed 4242,
  pas 13, unité `u91` (cast sur la cible 79 depuis `(2,2)`), et **deux** occurrences sur
  `MC1_67` / 909. Cause en amont de la traduction en messages — gate d'ability, disponibilité, ou
  refus de cible — à chercher là, pas dans `InputBuilder`.
- **Comparaison de position réduite à la MAIN tile.** Le natif compare deux `UnitPosition`, c'est-à-dire
  deux **ensembles** de tuiles (`currentPosition.Equals(action.Position)`). Le port compare la tuile
  principale. Pour une unité multi-tuiles dont seule une tuile secondaire changerait, le natif
  émettrait un `MoveUnitMessage` que ce mirror tairait. Les héros du pool sont mono-tuile — non
  exercé, donc non mesuré.
- **`DefaultMachineTactic` n'est pas touché.** Son émission passe par une AUTRE fonction native
  (`DefaultMachineTactic$$GenerateInputMessagesFromUnitAction`), non relue par cette tranche ; le port
  y rend déjà `{kind:"finish"}` quand aucun générateur ne produit, mais le cas « action inerte »
  (famille B) n'y est pas confronté.
- **Le court-circuit `options[0] != 0`** d'`InputBuilder` n'est pas porté : sur le chemin du tactic
  d'unité, `options` est un `&local_58` remis à zéro, donc la branche est morte ici. Elle ne l'est
  pas forcément pour les autres appelants d'`InputBuilder` (9 xrefs).
