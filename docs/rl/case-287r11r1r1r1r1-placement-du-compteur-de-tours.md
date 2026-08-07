# #287-r11-r1-r1-r1-r1 — le compteur des tours DÉMARRÉS rejoint son écrivain natif

`State.turn_counts` (`TurnComponent+0x38`) était bumpé par `StartTurnOperation.execute`. Le natif
l'écrit ailleurs, et la différence ne se voit que sur un régime : le **NO-OP**.

## 1. L'écrivain, et ce que `StartTurn` fait vraiment

`IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer` écrit les DEUX dictionnaires, et
c'est leur **seul** écrivain (vérifié sur les 19 méthodes de `TurnComponent` par #287-r11-r1-r1-r1) :

    if (get_CurrentPlayerId() == nextPlayerId)  return;                    // NO-OP, AVANT tout bump
    if (!started.ContainsKey(next))             started.Add(next, 0);
    if (get_CurrentPlayerId() != 0) { ended.TryAdd(cur, 0); ended[cur] += 1; }
    prev = get_CurrentPlayerId();
    <+0x24> = nextPlayerId;  <+0x18> = prev;
    started[get_CurrentPlayerId()] += 1;                                   // l'ENTRANT

`IdunBattle.Operations.StartTurnOperation$$Execute` ne fait que **LIRE**
`GetAmountOfTurnsStartedByCurrentPlayer` — décompilé re-lu : la valeur est capturée en tête de corps
et comparée à `1` en toute fin (`if ((int)uVar8 == 1) && ...`), jamais réécrite.

Trois lectures qui ne se devinent pas : le bump de `started` porte sur l'**ENTRANT** (à ce point
`get_CurrentPlayerId()` vaut déjà `nextPlayerId`), là où celui d'`ended` porte sur le **SORTANT** ;
le gate `!= 0` ne couvre **que** `ended` ; et le `started.Add(next, 0)` de tête ne sert qu'à rendre
l'indexeur non levant — un `.get(k, 0) + 1` l'absorbe.

## 2. Où ça mord — le NO-OP, et lui seul

Les deux sites étaient ENCHAÎNÉS par `advance_turn` (`ChangeTurn` puis `StartTurn`), donc l'état
après la paire était identique. Sauf quand `FindNextPlayer` rend le joueur **courant** (seul joueur
encore jouable) : le natif sort avant ses deux bumps, le port comptait un tour de plus. Direction :
le port **SUR-comptait**, dans ce seul régime.

## 3. Les 8 sites qui l'avaient laissé en place — mesurés, pas supposés

Huit appels à `StartTurnOperation.execute` SEUL, tous dans des probes : `probe_213_ghost_revive`,
`probe_227_remove_unit_operation` (×2), `probe_366r1_echoes_revive`, `probe_cvc_contagions_lifecycle`,
`probe_lot_pose` (×3). Leur appel ne fait plus avancer le compteur.

**Aucun des cinq fichiers ne mentionne `turn_counts`, `PlayerTurnsStarted`, `turn_defeated`,
`SereneUnifier` ni `Ambush`** — les deux seuls consommateurs portés de ce dict. Ils appellent
l'opération pour ce qu'elle fait vraiment (resets per-unité, `turnsStarted@+0x58`, vecteurs
turn-start), pas pour le compteur. Le recensement est **exécutable** (étage 5 du cliquet), donc un
probe neuf qui violerait la règle rougira. Un appelant qui veut vraiment avancer d'un tour joue
désormais la **paire** — ce que fait aussi le natif.

## 4. Ce qui a été confronté, et ce qui ne pouvait pas l'être

⚠ **Le NO-OP n'est pas montable live** : il suppose qu'il ne reste qu'un joueur jouable, ce qui
termine le match (`StateExtensions.IsMatchFinished`, tête de `FindNextPlayer`). Il est donc **LU au
décompilé** — le retour anticipé précède les deux bumps, sans ambiguïté — et gardé offline.

Ce qui EST confronté live, c'est la **non-régression du régime nominal**.
`probe_287r11r1r1_caster_has_2_turns_left.py`, bras `bascule` (`MainPlayerRoundLimitation = 3`, un
`casterReason` natif après chaque `endturn`) : **8 pas évalués, 0 désaccord**, rang de bascule
natif = port = **3**, ventilation des verdicts du port `{0x0: 2, CasterHas2TurnsLeft: 6}` (non
dégénérée). Les `turns_ended` sont **chiffre pour chiffre** ceux mesurés avant le déplacement, et
l'identité `ended[p] == started[p] - (p == courant ? 1 : 0)` tient aux 9 pas (ex. pas 3 :
`turn_counts = {3: 2, 4: 2}`, `turns_ended = {3: 2, 4: 1}`, courant `4`).

`test_turnflow_live.py` **2 passed** ; `test_unstoppable_momentum_live.py` **9 passed**.

## 5. Les cliquets

`tests/engine/test_287r11r1r1r1r1_placement_du_compteur_offline.py`, **12 tests / cinq étages** :
l'écrivain (entrant vs sortant, assertionnés ensemble ; le bump inconditionnel depuis le joueur `0`)
; le NO-OP, **avec son propre bras non-vide** ; `StartTurn` qui n'écrit pas `+0x38` **et** continue
d'écrire la stat 12 per-unité ; la divergence par le **chemin réel** (`advance_turn`) avec son
MUTANT — le placement d'avant reproduit **en deux moitiés**, sans quoi il donnerait un double
comptage ou aucun — plus la **coïncidence hors NO-OP** et l'identité sous `advance_turn` ; et le
recensement exécutable des appelants, avec son anti-vacuité.

Vue rouge sur l'arbre témoin (`git archive origin/master`) : **7 failed** pour ce fichier ;
**12 passed** après.

## 6. Ce qui n'est PAS couvert

* **Le NO-OP live**, pour la raison nommée ci-dessus.
* ⚠ **Le NO-OP DÉCOUPLE les deux compteurs de tour, côté NATIF, et le seed en hérite.** Sur le
  NO-OP, `+0x38` ne bouge pas mais `StartTurnOperation` est enfilé séparément par
  `EndTurnOperation$$Execute` et joue quand même, donc `+0x58` per-unité avance. Sur N tours
  consécutifs dans ce régime, `snapshot._load_turn_counts` (`max` de la stat 12) **sur-estime**
  `turn_counts` de N — le « `max(...)` ne SUR-ESTIME jamais » de sa docstring vaut désormais « hors
  NO-OP ». Ce n'est pas un écart de port : la sur-estimation porte sur une mesure prise **sur le
  natif**, et le port produit exactement le même découplage depuis qu'il est fidèle.
* **Les modes de sous-estimation hérités** de `_load_turn_counts` (unités apparues après le début,
  ou mortes) sont inchangés.
