# case-10046 — la POSE des unités prédéfinies : la chaîne complète, et ses TROIS abandons muets

Lu au décompilé sur `t6dpr4k06g`, en cherchant pourquoi le camp adverse disparaît quand on
inverse les `TeamId`. La chaîne est fermée ; l'étape qui échoue ne l'est **pas** — cf. §5.

## 1. La chaîne, de l'escouade au tuile

```
BC.PredefinedUnits[].Id (playerId)
  -> IdunBattle.Entities.StateExtensions$$GetPlayer(state, playerId)
  -> IdunBattle.Entities.StateExtensions$$GetTeam(state, player)      -> Nullable<(teamId, rang)>
  -> IdunBattle.Configuration.SpawnPointSetConfiguration$$GroupForPlayer(set, teamId, rang)
  -> index -> FirstOrDefault(groupes, g => g.TeamWithPlayerIndex == index)
  -> groupe.SpawnPoints[i] -> la tuile
```

`IdunBattle.Operations.SetupGameOperation$$AddPredefinedUnits(this, spawnPointSet)` porte la
boucle. Le compteur `i` est tenu **par playerId** dans un `SortedDictionary` local.

## 2. ⚠ TROIS ABANDONS MUETS — ce sous-système NE LÈVE JAMAIS

| # | condition | effet |
|---|---|---|
| 1 | `GetTeam` rend un `Nullable` **sans valeur** | escouade **entièrement passée** |
| 2 | `GroupForPlayer` rend **null** | escouade **entièrement passée** |
| 3 | `i >= groupe.SpawnPoints.Count` | `break` — unités restantes **abandonnées** |

Aucun ne produit d'erreur ni d'événement. C'est pour ça que chaque tentative ressemble à
« il ne se passe rien » : il n'y a **rien à voir**, par construction. Même famille que le
`UnitId` absent du catalogue d'une vague (`reference_vague_bc_gabarit_doit_etre_au_catalogue`).

## 3. L'index de groupe est une table à DEUX dimensions

`GroupForPlayer` la calcule **inline** (identique à `TeamPlayerIdExtensions$$GetTeamWithPlayerIndex`) :

```
teamId 0 -> 6                     (l'environnement -- AUCUN groupe ne porte 6, donc null : normal)
teamId 1 -> rang ? 2 : 0
teamId 2 -> rang ? 3 : 1
teamId 3 -> rang ? 5 : 4
sinon    -> ArgumentOutOfRangeException
```

⚠ **Le `rang` n'est PAS le playerId** : c'est la position du joueur dans la liste des joueurs de
SON équipe, comptée par l'énumération de `GetTeam`. Avec un joueur par équipe il vaut 0.

⚠ **Ce n'est PAS `IdunBattle.Core.TeamIdExtensions$$ToOldPlayerIndex`** (`1→0, 2→1, 0→2`), qui
ne sert qu'à `AUnitView$$Create` / `PlaceholderUnitView$$Create`. Les deux tables coïncident sur
les équipes 1 et 2 et **divergent sur l'équipe 0** (2 contre 6). Confondre les deux a coûté deux
diagnostics faux dans la même soirée.

## 4. `CacheSpawnPoints` : la vue, et son piège de doublon

`IdunBattle.View.FSM.VisualBattleQuery$$CacheSpawnPoints` remplit trois caches **clés par
`TeamWithPlayerIndex`**, sur le seul set d'`SpawnPointSetIndex`. Disposition du groupe :

```
groupe+0x10  TeamWithPlayerIndex (int)   +0x14  MachineOfWarPosition   +0x18  SpawnPoints
```

⚠ C'est `Dictionary.Add`, **pas** l'indexeur : **deux groupes au même index lèvent**, et le
cache de points de spawn est perdu en entier. Laisser ce champ dans un état arbitraire n'est
donc pas « un groupe mal attribué », c'est une exception qui emporte tout l'écran.

## 5. ⛔ CE QUI N'EST PAS RÉSOLU

Le camp adverse ne spawne pas quand les `TeamId` sont inversés (`11:1→2`, `12:2→1`), groupes
échangés ou non. **Déroulé à la main, ça devrait marcher** : joueur 12 en équipe 1 rang 0 →
index 0 → le groupe de 12 points ; joueur 11 en équipe 2 rang 0 → index 1 → celui de 5. La
lecture dit oui, la mesure dit non.

Ce que la lecture apporte : il ne reste que **trois points d'observation**, tous nommés au §2.
Un ancrage sur `GetTeam` et `GroupForPlayer` dirait lequel, en un montage.

⚠ L'unique montage où les 7 NPC sont apparus était la configuration **instable** (correspondance
de groupes clé par la VALEUR, donc non idempotente sous `consumeOnce: false`) — un artefact, pas
un succès. « La capacité du groupe explique l'absence » est **RÉFUTÉ**.

⚠ `unitsAlive` en phase `Setup` est un **mauvais oracle** : 5, puis 7, puis 5 selon les
configurations, sans que ce qu'il compte à ce moment-là soit établi. Il a fondé trois
conclusions successives, toutes corrigées par ce que l'utilisateur voyait à l'écran.

## 6. Sûreté — le BOARD persiste, la BC non

Mesuré à la restauration : les `TeamId` étaient **déjà revenus d'eux-mêmes** (la BC est
reconstruite à chaque `LoadBattle`) alors qu'un groupe de spawn portait **encore** l'écriture
d'un montage précédent. Muter `TeamWithPlayerIndex` n'est donc **pas borné à la bataille
courante** : ça survit et ça peut fuir vers une partie réelle. Toute expérience dessus se
termine par une remise à l'état d'origine — et il n'existe aucun garde qui l'impose.

## 7. Outil

`scripts/python/env_ability_patch.py --inverser-equipes` écrit les deux (équipes ET groupes),
en place, par le patch `LoadBattle.onLeave`. La correspondance de groupes est clé par la
**position**, jamais par la valeur : une table `{0→1, 1→0}` lue sur la valeur n'est pas
idempotente et se défait au second passage.
