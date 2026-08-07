# #287-r11-r1-r1-r1 — le compteur manquant n'était pas une donnée à capter, c'était une IDENTITÉ

`BattleQuery$$HasMinimumRemainingTurns` a deux bras. Le port rendait `true` au premier (mesure) et
**LEVAIT** au second, faute de `TurnComponent.<Dictionary @+0x40>` — les tours **TERMINÉS**, ventilés
par joueur. La fiche interdisait explicitement les deux rabattements évidents. Elle avait raison sur
les deux, et il n'a fallu ni capteur ni fenêtre de reinject : le dictionnaire est **algébriquement
déterminé** par son jumeau et par le joueur courant.

## 1. Ce qui débloque — l'ÉCRIVAIN UNIQUE

`IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer` écrit les DEUX dictionnaires, et
c'est le **seul** (vérifié sur les **19** méthodes de `TurnComponent` : `.ctor` les construit vides,
`Copy` les clone, `Block/UnblockTurnChange` écrivent `+0x30`, `SetTempChangeToPlayer` /
`ResetTempPlayerTurn` `+0x28`, `GetNextTurnStage` lit `+0x10/+0x14`). Il n'a qu'**un** appelant,
`IdunBattle.Operations.ChangeTurnOperation$$Execute` (xrefs). Corps verbatim :

    if (get_CurrentPlayerId() == nextPlayerId)  return;                    // NO-OP, AVANT tout bump
    if (!started.ContainsKey(next))             started.Add(next, 0);
    if (get_CurrentPlayerId() != 0) { ended.TryAdd(cur, 0); ended[cur] += 1; }
    prev = get_CurrentPlayerId();
    <+0x24> = nextPlayerId;  <+0x18> = prev;
    started[get_CurrentPlayerId()] += 1;

(`started` = `+0x38`, `ended` = `+0x40`, `get_CurrentPlayerId` = `tempPlayer.HasValue ?
tempPlayer.Value : <+0x24>`.)

⇒ **`ended[p] == started[p] - (p == CurrentPlayerId ? 1 : 0)`**, à tout instant. Le joueur courant a
un tour démarré de plus que terminé ; tous les autres sont à égalité. L'identité tient aussi sous
joueur TEMPORAIRE (`+0x28`) : les deux bumps portent alors sur le temp, donc l'écart reste 1.

⚠ **`StartTurnOperation$$Execute` N'ÉCRIT PAS `+0x38`** — il ne fait que le LIRE
(`GetAmountOfTurnsStartedByCurrentPlayer`, comparé à `1`). La docstring du port qui l'affirmait
depuis toujours était fausse ; c'est corrigé, et le résidu `#287-r11-r1-r1-r1-r1` nomme la
conséquence (le port bumpe `turn_counts` un cran trop tard).

## 2. Le port

| pièce | rôle |
|---|---|
| `State.turns_ended` | mirror de `+0x40`, jumeau de `turn_counts` (`+0x38`) |
| `turnflow.set_current_player` | mirror 1:1 de `SetCurrentPlayer` — NO-OP, garde `cur != 0`, bump du **SORTANT** |
| `snapshot._load_turns_ended` | seed par l'identité, APRÈS `_load_turn_counts` |
| `battle_query.get_amount_of_turns_ended_by_player` | `ContainsKey ? [p] : 0` — le zéro est une LECTURE |
| `battle_query.get_player_turn_order` | `GetPlayerTurnOrder`, remonté à son foyer natif ; `turnflow.player_turn_order` DÉLÈGUE |

Le déménagement de `player_turn_order` n'est pas cosmétique : `HasMinimumRemainingTurns` l'appelle,
et deux stand-ins de l'ordre de tour libres de diverger auraient été un bug muet. La délégation est
en **forme B** et gardée par MORSURE (`monkeypatch` sur le foyer doit mordre à travers).

L'import `services.battle_query -> runner.components` (pour `OwnerComponent`) est **DIFFÉRÉ et
PORTEUR**, classé par la mesure prescrite : `python -c "import engine.runner.components"` charge
`engine.services.battle_query` (chaîne `components -> entities.effects.loki.* ->
services.damage_modifiers -> services.battle_query`, 107 modules) ⇒ le hisser fermerait un cycle.

## 3. La confrontation LIVE — l'encadrement ne suffisait plus

`probe_287r11r1r1_caster_has_2_turns_left.py`, porteur `astraOrdnanceBattery` (MoW), ability `1142`,
board `C1_02`, `MachineOfWarAmmo = 9`. Les trois bras statiques passent comme avant. Le bras
`bascule` (`MainPlayerRoundLimitation = 3`, un `casterReason` après chaque `endturn`) porte le cran
neuf : à CHAQUE pas, l'état du port est rechargé et on lui demande son verdict **sans lui souffler
`ended`**.

| pas | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| natif `casterReason` | `0x1` ÉCARTÉ | `0x0` | `0x0` | **refus** | refus | refus | refus | refus | refus |
| **port** (sans aide) | — | `0x0` | `0x0` | **refus** | refus | refus | refus | refus | refus |
| `turns_ended` du port | `{3:0,4:0}` | `{3:1,4:0}` | `{3:1,4:1}` | `{3:2,4:1}` | `{3:2,4:2}` | `{3:3,4:2}` | `{3:3,4:3}` | `{3:4,4:3}` | `{3:4,4:4}` |

**0 désaccord sur 8 pas évalués ; rang de bascule natif = port = 3 ; ventilation des verdicts du
port `{0x0: 2, refus: 6}`** (non dégénérée). Le pas 0 est écarté pour la raison déjà nommée
(`broken(ValidRequest)`, la règle n'est pas évaluée).

⚠ **Le chiffre décisif** : au pas de bascule, la formule impose `ended = limit - turns + 1 = 2`, et
le port MESURE `turns_ended[3] = 2`. L'accord n'est plus booléen — il porte sur la **valeur** du
compteur. C'est exactement ce que l'encadrement (« vrai pour tout `ended` de l'intervalle ») ne
pouvait pas donner : il acceptait n'importe quel compteur.

## 4. Ce qui n'est PAS couvert

* **`turns_ended` est exact PAR RAPPORT à `turn_counts`**, qui est lui-même DÉRIVÉ
  (`_load_turn_counts` = `max` de la stat 12 per-unité). Les modes de sous-estimation sont hérités
  tels quels (toutes les unités d'un joueur apparues après le début, ou mortes). Direction :
  `ended` sous-estimé ⇒ PERMISSIF. Le supprimer demande un capteur publiant les deux dictionnaires —
  aucun RPC ne le fait (`readTurnInfo` n'invoque `GetAmountOfTurnsStartedByPlayer` que pour le
  joueur COURANT, et vers `recorder`/`cheat`/`move-options`).
* **Le placement de `turn_counts`** reste à `StartTurnOperation`, alors que le natif l'écrit dans
  `ChangeTurn`. Équivalent sur la paire enchaînée, DIVERGENT sur le NO-OP. Résidu
  `#287-r11-r1-r1-r1-r1`.
* **Les deux autres porteurs du bit** (1160, 1188) restent non confrontés live — le gate est global
  au match, donc leur régime est identique, mais c'est un raisonnement.
* **Aucun régime à plafond de rounds hors de ce probe** : la seed versionnée n'en porte pas.
* Le stand-in `GetPlayerTurnOrder` (ids d'entité croissants) n'a pas bougé — résidu
  `#462-r4e-o-r2-r1-r1-r1-r1` inchangé.

## 5. Les cliquets

`tests/engine/test_287r11r1r1r1_turns_ended_par_joueur_offline.py`, **15 tests / six étages** :
substrat distinct de ses deux voisins ; écrivain (SORTANT, NO-OP, joueur `0`) ; identité vérifiée
sur une séquence de tours réelle ; seed et son tri-état ; lecture `!ContainsKey -> 0` **ventilée** ;
foyer unique de `GetPlayerTurnOrder` vérifié par MORSURE. Plus le MUTANT `turn_counts`, qui
**assertionne son propre non-vide**.

Vue rouge sur l'arbre témoin (`git archive origin/master`, arbre complet) : **15 failed** ;
**15 passed** après. `test_287r11r1r1_caster_has_2_turns_left_offline.py` passe de 18 à 18 tests, le
contrat du second bras inversé (« LÈVE » → « rend une VALEUR dans les deux sens »).
