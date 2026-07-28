# N8 — `OwnerHasFinishedMinTurns` : compteur PER-UNITÉ (`turnsFinished`), jamais per-JOUEUR

Build `gqfc5mff6c`. Deux questions binaires, indépendantes, tranchées **au décompilé** puis
confirmées live.

---

## 1. Le gate est PER-UNITÉ, et il lit `turnsFinished` (pas `turnsStarted`)

Chaîne complète, du nœud DSL au champ :

```
IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger
  = On(0x17)  &  <trigger caché factory+0xa0>  &  OwnerHasFinishedMinTurns(2)
                &  IsUnitWithStatAmount(Self, Health, Current == StatAmount(Self, Health, Max))

IdunBattleLogic.Entities.DSLFactory$$OwnerHasFinishedMinTurns(int amount)
  -> new IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger(
         selector   = factory + 0x148,      // Self/Owner (map des slots : dsl-effect-nodes.md)
         amount     = <int>   @ this+0x18,  // 2 pour PileIn
         selectType = 3       @ this+0x28)

IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger
  amount = (this+0x20 != null) ? <IAmountFormula @+0x20>.Calculate(entities)   // overload formule
                               : *(int *)(this + 0x18)                          // overload int
  unit   = <selecteur @+0x10>.Select(entities)
  return unit != null && amount <= IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(unit)

IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(entity)
  EntityType 1 (Unit)    -> UnitComponent    + 0x5c
  EntityType 6 (Machine) -> MachineComponent + 0x5c      // même offset : champ de BaseUnitComponent
  sinon                  -> 0
```

**Verdict 1 : PER-UNITÉ.** Le rapport hérité (O4a) avait raison sur la granularité, et il faut y
ajouter une précision qui change le port : le champ lu est **`turnsFinished` (`+0x5c`)**, pas
`turnsStarted` (`+0x58`, exposé lui comme `StatType` 12). Ce sont **deux champs distincts de
`BaseUnitComponent`** (taille 120 = 0x78 dans `data/symbols/gqfc5mff6c/frida/classes.tsv`, d'où le
partage Unit/Machine) :

| champ | écrit par | lu par |
|---|---|---|
| `+0x58` `turnsStarted` | `IdunBattle.Operations.StartTurnOperation$$Execute` | `GetStat(unit, 0xc)` → `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate` |
| `+0x5c` `turnsFinished` | `IdunBattle.Operations.EndTurnOperation$$Execute` | `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished` |

Et un **troisième** compteur, de granularité JOUEUR, que le port confondait avec les deux premiers :
`TurnComponent + 0x38` = `Dictionary<playerId, int>`, lu par
`IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsStartedByCurrentPlayer` et exposé au
DSL par `IdunBattle.Entities.Formulas.CurrentPlayerTurnsStartedFormula$$Calculate` → c'est
`State.turn_counts`.

### Écriture de `+0x5c` — deux sites, et un ORDRE qui compte

`IdunBattle.Operations.EndTurnOperation$$Execute` :

1. copie `PlayerComponent.GetCurrentlyOwnedUnitIds()` du joueur courant dans une `List` locale ;
2. pour chaque id : `*(int *)(unitComponent + 0x5c) += 1`, puis `ResetAbilitiesThatResetOnTurnEnd`,
   `DecreaseAbilityCooldowns`, et le roulement `stats[0x188] = stats[0x18c]` ;
3. même `+= 1` sur la **Machine of War** du joueur (`PlayerComponent + 0x78`) ;
4. **ensuite seulement** l'exécution des trigger-abilities `On(0x17)` (slot 0x51, littéral `0x17`) ;
5. puis `RefreshEffects`.

Deux conséquences portées :

- le porteur voit **déjà** le tour qui s'achève dans son compteur quand son propre gate s'évalue ;
- une unité **spawnée par un trigger `On(0x17)`** (réplique PileIn) n'est **pas** bumpée ce tour-là,
  la liste d'ids ayant été copiée avant.

`GetCurrentlyOwnedUnitIds` = `owned(+0x30) ∪ extra(+0x48)` moins un `RemoveAll` dont le prédicat
`PlayerComponent$$u003Cget_CurrentlyOwnedUnitIdsu003Eb__17_0` teste l'appartenance à la liste des
**défaits** (`+0x40`) ⇒ **les unités mortes ne sont pas bumpées** (même filtre que
`_bump_turns_started`).

### `turnsFinished` n'est PAS dérivable de `turnsStarted`

Les deux compteurs sont bumpés sur le **même ensemble** mais à des **instants différents**, donc leur
écart dépend de la date d'apparition de l'unité :

| unité | pendant le tour de son propriétaire | hors de ce tour |
|---|---|---|
| présente au déploiement | `finished = started − 1` | `finished = started` |
| apparue PENDANT le tour de son propriétaire (tout summon) | `finished = started` | `finished = started + 1` |

Aucun canal live ne dit laquelle des deux lignes s'applique ⇒ toute dérivation serait une invention.

---

## 2. `load_state` ne seede pas `turn_counts` — exact, mais ce n'était pas le bon compteur

**Verdict 2 : NON, `load_state` ne le seede pas**, et `State.turn_counts` part à `{}`
(`engine/runner/state.py`), les lecteurs faisant `get(player, 0)` ⇒ dégradation **permissive et
silencieuse**. Mais après le portage du gate per-unité, **plus aucun consommateur ne dépend de sa
valeur absolue** :

- PileIn ne le lit plus ;
- l'unique lecteur restant, `_eligible_for_resurrect` (`operations/triggers/genestealer.py`,
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$GetUnitsEligibleForResurrect`),
  teste `turn_counts[player] − turn_defeated == 1`, et `turn_defeated` est **écrit depuis
  `turn_counts`** par `Ambush_SummonAbility` ⇒ la différence est **invariante par décalage**.

### Le gap de seed réel — et il est côté HOOKS

Ce qu'il faudrait seeder, c'est le compteur **per-unité**. Il n'est exposé par **aucun** RPC :

- `decisionView` / `observeBattle` / `combatSnapshot` / `tileMeta` (les quatre canaux que
  `load_state` consomme) ne portent aucun compteur de tour ;
- `combatSnapshot` passe par `UnitExtensions.GetStat(unit, StatType)` et **`turnsFinished` n'est pas
  un `StatType`** (l'énumération va de 0 à 26 et n'en contient aucun) : ce canal ne peut pas
  l'atteindre, quel que soit l'id ajouté à `COMBAT_STAT_IDS` ;
- le compteur JOUEUR, lui, est lisible (`readTurnInfo` dans `frida/hooks/game/match-state.ts`,
  `TurnComponent.GetAmountOfTurnsStartedByCurrentPlayer`) mais n'est émis que par `aiTurn`
  (`features/cheat.ts`) et `move-options`, jamais dans le chemin de chargement — et il ne rend que le
  joueur COURANT, pas le dictionnaire.

**Champ manquant, nommément** : `BaseUnitComponent + 0x5c`, à lire directement sur le composant
(comme `match-state.ts` lit déjà `DefeatedByMeleeAttack` / `DeathReason` via
`getFieldOffset(unitComponentClass, …)`) et à émettre p. ex. en `decisionView.units[].turnsFinished`.
Cela exige un rebuild + reinject Frida ⇒ inscrit en résidu **N11** de `port-residuals-inventory.md`,
à grouper avec un autre besoin de capteur.

**Portée réelle du résidu** : nulle dans le cas NOMINAL. Le runner Python charge un snapshot d'un
runner **fraîchement bâti** (tous les compteurs à 0, ce que `load_state` produit déjà) puis reproduit
l'évolution ; et **tous** les porteurs de `PileIn` sont des summons créés par le port lui-même
(`orksNpc1Grot`, `kind = summons`, hors `--list-pool`, amené par `orksRuntherd`/`SquigHound` ou
`Snotflogga`/`GetEmRuntz`) — leur compteur est donc exact sans aucun seed. Seul un **replay one-shot
chargé mi-bataille** doit poser la valeur, et les trois sites qui le font le disent.

---

## 3. Ce qui a été porté

| fichier | changement |
|---|---|
| `engine/runner/components.py` | `UnitComponent.turns_finished` (mirror `BaseUnitComponent + 0x5c`), 0 à la création |
| `engine/runner/operations/turnflow.py` | `_bump_turns_finished(state, player)` + appel dans `EndTurnOperation.execute`, **avant** `end_turn_summon_triggers` |
| `engine/runner/operations/triggers/dispatch/turn.py` | le gate passe de la sortie anticipée `turn_counts[player] < 2` à un test **par candidat** `uc.turns_finished < PILEIN_MIN_OWNER_TURNS` |

Le seuil `PILEIN_MIN_OWNER_TURNS = 2` et le reste du behaviour (`Maybe`, `Count`/`Difference`/
`Multiply`, sélecteur de tuile) sont inchangés.

---

## 4. Mesure — avant / après

`probe_pilein_owner_turns.py` fait naître UN grot (`orksRuntherd` attaque → passif `SquigHound`) puis
mesure, aux fins de tour d'**âge 0** (le tour de sa naissance) et d'**âge 1**, les `genrand_int32`
consommés par le `endturn` natif (re-simulation du MT via `dumpRng`) et par le port sur le **même
état MT**. C'est le seul couple de points où les deux hypothèses divergent : à l'âge 0 le JOUEUR a
déjà fini plusieurs tours, le GROT un seul.

Colonnes `M0` = les deux régimes du port d'avant (`turn_counts`) : `M0-joueur` = joueur âgé → gate
vacant ; `M0-snapshot` = état `load_state`, `turn_counts == {}` → gate toujours faux.

```
seed 777 / MC1_67       seed 31337 / MC1_67     seed 4242 / MC1_44      seed 555 / MC1_63
age PV  LIVE M1 M0j M0s age PV  LIVE M1 M0j M0s age PV  LIVE M1 M0j M0s age PV  LIVE M1 M0j M0s
 0  OUI    0  0   1   0  0  OUI    0  0   1   0  0  OUI    0  0   1   0  0  OUI    0  0   1   0
 1  OUI    1  1   1   0  1  OUI    5  5   5   0  1  OUI    1  1   1   0  1  OUI    1  1   1   0
                         (age 1 : spawn live 1 = port 1)
```

(La 4ᵉ configuration a été mesurée **après** le rebase sur `origin/master`.)

- **LIVE âge 0 = 0 tirage** ⇒ le gate natif est FERMÉ pour un grot d'un tour, alors que son joueur en
  a fini ≥ 2. C'est la réfutation directe de l'hypothèse per-JOUEUR.
- **LIVE âge 1 = 1** (le `Maybe` échoue) ou **5** = 1 `Maybe` + 4 `Randomize` de placement (le `Maybe`
  réussit, 1 spawn) ⇒ gate OUVERT, et le port reproduit **bit-exact** les deux cas.
- Port d'après : accord **8/8** (4 configurations × 2 âges), spawns compris.
- Port d'avant : `M0-joueur` sur-tire à l'âge 0 (**1 vs 0** — et crée un grot fantôme 3 fois sur 4) ;
  `M0-snapshot` sous-tire à l'âge 1 (**0 vs 1..5** — PileIn purement mort).

Le **co-gate PV PLEINS** (`IsUnitWithStatAmount(Health Cur == Max)`) est vérifié SATISFAIT aux huit
points de mesure (colonne `PV`) : sans cela, un « 0 tirage » à l'âge 0 aurait pu venir de lui.

### Gardes vues ROUGES avant le fix

`test_pilein_owner_turns_live.py`, joué contre le code d'avant (gate + bump retirés, champ conservé
pour que la mesure porte sur le COMPORTEMENT et non sur un `AttributeError`) — 6 échecs :

```
AssertionError: 1 tirage(s) pour un grot a 1 tour fini (gate `>= 2` non applique)
AssertionError: 3 tirage(s) pour un grot a 1 tour fini (gate `>= 2` non applique)
AssertionError: 0 tirages pour 1 grots eligibles (attendu 1 `next_bool` chacun)
AssertionError: 0 tirages pour 3 grots eligibles (attendu 1 `next_bool` chacun)
AssertionError: grot non bumpe
AssertionError: assert 0 == (0 + 1)
```

---

## 5. Ce qui n'est PAS couvert

- **Seed de `turnsFinished` depuis le live** — résidu **N11**, gap de capteur (cf. §2).
- **Le compteur de la Machine of War** : le natif bumpe aussi `+0x5c` sur la MoW du joueur. Le port le
  fait (les entités MoW portent un `UnitComponent`, cf. `snapshot._load_machines`) mais **aucun
  consommateur n'est porté** — `IdunBattle.AI.Playbook.Loki.DutyEternalPlaybook$$GetUseProbability` et
  `IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$GetUseProbability`, les deux autres
  lecteurs de `GetTurnsFinished`, sont face DÉCISION et hors périmètre.
- **L'overload FORMULE de `OwnerHasFinishedMinTurns`** (`amount: IAmountFormula`, `unitSelectionType`)
  n'a pas de call-site porté : seul l'overload `int` (celui de PileIn) est exercé.
- ~~**L'ORDRE `RefreshEffects` vs `On(0x17)`**~~ — **CORRIGÉ le 2026-07-28**, cf.
  `case-n8b-endturn-order.md`. Le constat était juste (le natif exécute `On(0x17)` **avant**
  `RefreshEffects`) ; la justification donnée ici était fausse : `RefreshEffects` n'inflige **aucun
  dégât** (c'est `EffectComponent.RemoveOneTurn` + events + `RefreshEffectsOperation`), donc
  l'écart ne pouvait pas « mordre par un DoT ». Ce qu'il changeait réellement : **l'état des effets
  que voient les gates du vecteur**.
- **Le champ `unitSelectionType` (`+0x28`, valeur 3)** du trigger n'est lu nulle part dans
  `ShouldTrigger` : rôle non déterminé, non porté.
