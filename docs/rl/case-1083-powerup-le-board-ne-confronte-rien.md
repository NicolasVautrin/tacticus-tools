# #1083 — `PowerUp_*` : le BOARD ne confronte RIEN, et le montage ne dépend pas de lui

**Verdict en une ligne** : l'axe de confrontabilité des 20 passifs `PowerUp_*` n'est **ni le pool,
ni le board** — c'est un montage en trois écritures, **identique pour les 20**, qu'un board place
l'unité ou non.

## 1. Ce qui était supposé, et qui est FAUX

La prémisse de départ était : « 71 boards du disque posent un `powup*`, donc les 4 passifs
correspondants sont confrontables par `rl_duel build --board <id>`, et les 15 autres ne le sont
pas ». Les deux moitiés sont fausses.

Le balayage lui-même est juste et se re-dérive (`probe_1083_powerup_boards.py`) :

```
[1083] boards balayes : 779
[1083] boards qui POSENT au moins un `powup*`
       (voie board.SpawnPointSets[].GameModeTiles[].PowerUpUnits[].UnitId) : 71
[1083] unites `powup*` NOMMEES par au moins un board : 5
   powupDamage 64 · powupArmor 62 · powupHealth 59 · powupMeleeHits 58 · powupHits 44
[1083] Mode des GameModeTiles porteurs : SyncPVP=563   (100 %)
[1083] CONTROLE -- boards nommant un `powup*` HORS de cette voie : 0
```

⚠ **71, pas 72** : `Path.stem` n'identifie pas un board — `global/` et `syncPvp/` collisionnent,
71 boards pour seulement **36** stems distincts. Et les signaux voisins (`DoorActivationTiles`,
`TileEffectSpawnPoints`) ne comptent pas la même chose : les OU-er gonfle le résultat.

**Mais ce compte ne conclut rien sur la confrontabilité**, et c'est le point.

## 2. Le canal natif : `PowerUpUnits` est lu au BUILD DE LA BC, pas au runtime

`PowerUpUnits` est bien le champ vivant (pas `TileEffectSpawnPoints`, qui vit sur
`SpawnPointSetConfiguration` et pas sur `GameModeTilesConfiguration`). Son **unique** lecteur est
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetBoostsConfig`, côté **constructeur de BC** :

- il récupère l'entrée par `IdunBattle.Configuration.SpawnPointSetConfiguration$$GetSpecialTilesConfig`,
  dont l'overload court **code en dur `gameMode = 8`** et dont l'overload long **rejette** toute
  entrée dont `Mode != gameMode` (et `SyncPvpRuleset != ruleSet` quand le ruleset est renseigné) ;
- il en tire une entrée `PredefinedUnits` (`+0x10` = playerId, `+0x18` = la liste d'unités),
  **insérée à l'index 0** ;
- puis `Idun.Source.IdunBattle.View.BattleConfigBuilder$$AddPowerUpSpawnpointGroup` ajoute au
  `SpawnPointSet` un groupe de `TeamWithPlayerIndex == 6` (ou fait un `InsertRange` dans celui qui
  existe déjà).

Côté **runtime**, `IdunBattle.Operations.SetupGameOperation$$AddTiles` ne lit de la
`GameModeTilesConfiguration` que les **trois listes de positions** via
`IdunBattle.Configuration.GameModeTilesConfiguration$$GetGameModeTileProperties` (champs `+0x18`,
`+0x28`, `+0x30`) — **jamais `PowerUpUnits` (`+0x20`)**. Les power-ups arrivent en bataille comme
des `PredefinedUnits` ordinaires, via
`IdunBattle.Operations.SetupGameOperation$$AddPredefinedUnits`.

⇒ Notre seed BC **court-circuite le constructeur du jeu**. Un swap de board n'a donc aucun effet.

## 3. La mesure qui le montre — TÉMOIN NON DÉGÉNÉRÉ

`rl_duel build --board Infested_SyncPvp_Arctic_03` (un des 71) :

| observation | valeur |
|---|---|
| `PowerUpUnits` présents dans la BC **envoyée** au runner | **5** (`powupHealth`, `powupArmor`×2, `powupMeleeHits`, `powupHits`) |
| unités `powup*` **en bataille** | **0** |

Le témoin n'est pas dégénéré : la donnée **est** dans la BC (`bc["Board"] = dump["board"]` copie le
board entier, `GameModeTiles` compris), et elle reste **inerte**. C'est bien le natif qui ne la lit
pas, pas notre chaîne qui l'aurait perdue.

Contrôle croisé : les **17** boards portant déjà un groupe `TeamWithPlayerIndex == 6` sont
**disjoints** des 71 porteurs de `PowerUpUnits` (intersection **0**) — le groupe de power-up des
71 n'existe pas encore dans l'asset, il est écrit par le constructeur.

## 4. Le montage qui MARCHE — trois écritures, indépendant du board

```powershell
python catalog_inject.py --units powup<X> --out <absolu>.json
python rl_duel.py build --seed-bc <absolu>.json --board <n'importe lequel> `
       --explicit-stats powup<X> --a-units "powup<X>,<4 heros>" --state-file <absolu>.json
```

Les trois écritures, et **ce qui échoue en silence si l'une manque** :

1. **`BC.Units` + `BC.Abilities`** (`catalog_inject`) — sans l'entrée catalogue, la fabrique ne
   construit rien : mesuré, `PredefinedUnits` contenait bien `powupHits` et l'unité **n'apparaît
   pas**, sans la moindre erreur.
2. **`BC.PredefinedUnits`** — c'est `--a-units` / `--p-units` qui l'écrit.
3. **`--explicit-stats powup<X>`** — voie NPC/SUMMON (#419-r1-tr12-r2). Sans elle, `--a-units`
   **refuse** : `hors pool / non spawnables au rank 17`. Le pool ne contient que des `lineup`.

**Mesuré, deux fois, dont une en généralisation :**

| unité | placée par un board ? | board utilisé | résultat |
|---|---|---|---|
| `powupHits` | oui (44 boards) | `Infested_SyncPvp_Arctic_03` | `u77 [powupHits] «Hits Power-up» HP0 moveNone` |
| `powupBomb` | **non — 0 board** | `MC1_67` (aucun power-up) | `u77 [powupBomb] «Bomb Power-up» HP0 moveNone` |

La seconde ligne est celle qui tranche : un power-up qu'**aucun** board ne place entre en bataille
sur un board qui n'en porte **aucun**. Le board n'est ni nécessaire ni suffisant.

Profil de l'unité montée : `HP0`, `moveNone`, traits `Steppable` / `Invincible` / `Immune` —
un objet de terrain, conforme à la catégorie `tile` du registre npc.

## 5. Conséquence pour la file de travail

« 4 confrontables / 15 non confrontés » est **faux dans les deux sens**. Les **20** `PowerUp_*` sont
au même état : *aucun n'est confrontable par board*, *tous le sont par le montage ci-dessus*. Écrire
« NON CONFRONTÉ — aucun board ne le place » aurait été un faux verrou de plus, de la même famille
que « absent du pool ⇒ non confrontable ».

## 6. Ce qui reste OUVERT

Aucun des 20 passifs n'est porté (0 classe, 0 effet, 0 entrée de registre — la surface native est
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.APowerUpAbility` et ses sous-classes). Le port
est le résidu **#1083-r1** ; le montage ci-dessus est ce qui le rend validable.
