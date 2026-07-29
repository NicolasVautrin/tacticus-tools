# #234 — `load_state` consomme `turnsFinished` (résidu N11 FERMÉ)

`combatSnapshot.units[].turnsFinished` était **émis** par le capteur (#N11) mais **non consommé** :
`UnitComponent.turns_finished` restait à **0** pour toute unité d'un état monté par `load_state`. Le
gate `OwnerHasFinishedMinTurns` rendait donc FAUX sur une unité ayant pourtant terminé N tours côté
natif — dégradation **restrictive** et silencieuse (le trigger ne fire jamais offline, ni erreur ni
crash).

## 1. La chaîne native

```
IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger
  -> IdunBattleLogic.Entities.DSLFactory$$OwnerHasFinishedMinTurns(2)
  -> IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger
       = IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(Self@0x148) >= amount@0x18
```

`GetTurnsFinished` rend `BaseUnitComponent + 0x5c`. **Écriture** : la boucle d'
`IdunBattle.Operations.EndTurnOperation$$Execute` sur `PlayerComponent.CurrentlyOwnedUnitIds` du
joueur qui finit son tour (`*(int *)(unitComponent + 0x5c) += 1`), **puis** le même `+= 1` sur sa
Machine of War (`PlayerComponent+0x78`) — deux sites, même offset, `GetTurnsFinished` ayant les deux
branches d'`EntityType` (1 = Unit, 6 = Machine). Ce bump précède le vecteur `On(0x17 = TurnEnd)`.

Ce n'est **pas** un `StatType` (l'énumération va de 0 à 26 et n'en contient aucun) : ni
`combatSnapshot.stats` ni `GetStat` ne peuvent l'atteindre, d'où l'accesseur dédié côté capteur —
qui **invoque la fonction nommée** plutôt que de lire `+0x5c` en brut (un offset est vrai jusqu'à la
prochaine MAJ et faux silencieusement après).

Et il n'est **pas dérivable** de `turnsStarted` (`+0x58`, stat 12) : une unité apparue PENDANT le
tour de son propriétaire (tout summon) rate le bump de `StartTurn` mais prend celui d'`EndTurn`, et
garde `turnsFinished == turnsStarted + 1` pour le reste de la bataille.

## 2. Le port

| fichier | changement |
|---|---|
| `engine/runner/snapshot.py` | `_load_unit_turn_state` lit un **troisième** champ d'état de tour : `turnsFinished` (`@+0x5c`), à côté de `currentTurnStartTile` (`@+0x18c`) et `chargedUnitIds` (`@+0x190`) |

Même boucle, même discipline **tri-état** que `_load_unit_flags` : champ ABSENT ou `null` = **non
mesuré** → le défaut du port (0) reste intact, comportement strictement antérieur ; un entier =
mesure, on écrit. Ici le tri-état n'est pas une précaution de style — le capteur rend `null` quand
`GetTurnsFinished` est irrésolue et `0` quand l'unité a réellement fini zéro tour.

Portée : les lignes `EntityType.Unit` **et** `EntityType.Machine`, le port matérialisant la MoW avec
un `UnitComponent` (`_load_machines`, qui tourne avant cet appel) — une seule boucle couvre les deux
sites natifs.

## 3. Mesure — le montage discriminant

Le seuil ne sépare qu'à l'**âge 1** du grot : `turnsFinished == 1` à la capture, le bump
d'`EndTurnOperation` le porte à 2, `2 >= 2` → gate OUVERT. Avec 0 en entrée (l'état d'avant), le bump
ne donne que 1 → gate FERMÉ. L'âge 0 est le témoin (gate fermé dans les trois régimes).

Porteur : `orksNpc1Grot` (`kind = summons`, hors `--list-pool`), amené par son summoner
`orksRuntherd` (passif `SquigHound` : 1 grot par attaque). Co-gate PV pleins
(`IsUnitWithStatAmount(Health Cur == Max)`) vérifié aux deux points — sans lui un « 0 tirage » ne
prouverait rien.

`probe_234_turnsfinished_seed.py`, deux couples (seed, board) :

| couple | âge | snap `tf` | LIVE rolls | PORT (load_state seul) | PORT sans seed | spawn live / après / avant |
|---|---|---|---|---|---|---|
| 777 / `MC1_67` | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 |
| 777 / `MC1_67` | **1** | **1** | **1** | **1** | **0** | 0 / 0 / 0 |
| 31337 / `C4_09` | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 |
| 31337 / `C4_09` | **1** | **1** | **2** | **2** | **0** | **1 / 1 / 0** |

Sur `C4_09`/31337 le `Maybe` **réussit en live** : le natif spawne une réplique (2 tirages = `Maybe`
+ `Randomize` de placement), le port seedé la spawne aussi, le port privé du seed n'en spawne
aucune. L'écart n'est donc pas seulement un flux PRNG — c'est une **entité manquante** dans l'état
offline.

**Observable de cardinalité** (flux PRNG offline, balayage de graines jusqu'au succès du `Maybe`) :
avec seed 1 réplique spawnée, sans seed 0, sur les deux couples.

**Seed lui-même** (partie A du probe, garde de non-vacuité : au moins deux valeurs distinctes dans
le même snapshot) : `tf=2` sur 2 unités et `tf=3` sur 2 unités après 5 fins de tour, **4/4 unités
confrontées, 0 écart**, sur les deux couples.

**Contre-épreuve** : le cliquet rejoué contre la version pré-fix de `snapshot.py` échoue sur les deux
tests, avec `live=1 port=0` — le port rendait le verdict **opposé**.

## 4. Gardes

| fichier | rôle |
|---|---|
| `scripts/python/tests/engine/runner/test_load_state_turns_finished_live.py` | cliquet à deux faces : SEED (chaque unité porte exactement le compteur natif, ≥ 2 valeurs distinctes exigées) et GATE (à l'âge 1, `load_state` seul accorde au natif ; le même état privé du seed rend 0) |
| `scripts/python/probe_234_turnsfinished_seed.py` | mesure : distribution du compteur, sweep d'âge 0/1 avec les trois régimes, observable de cardinalité |

## 5. Ce qui n'est PAS couvert

- **Les deux autres lecteurs natifs de `GetTurnsFinished`** —
  `IdunBattle.AI.Playbook.Loki.DutyEternalPlaybook$$GetUseProbability` et
  `IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$GetUseProbability` — sont face
  DÉCISION et **non portés** : aucun consommateur Python ne lit `turns_finished` hors du gate PileIn
  (`operations/triggers/dispatch/turn.py`). Le seed les servira le jour où ils seront portés.
- **L'overload FORMULE d'`OwnerHasFinishedMinTurns`** (`amount: IAmountFormula`,
  `unitSelectionType`) reste non porté — le gate PileIn passe par l'overload `int`.
- **La ligne `EntityType.Machine`** est couverte par construction (même boucle, `UnitComponent` posé
  par `_load_machines`) mais **non confrontée live** : aucun montage n'a mis une MoW dans un état
  rechargé où un gate lise son `turnsFinished`.
