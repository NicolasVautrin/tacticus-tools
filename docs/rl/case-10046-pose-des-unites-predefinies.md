# case-10046 — la POSE des unités prédéfinies : la chaîne complète, et ses CINQ abandons muets

Lu au décompilé sur `t6dpr4k06g`, en cherchant pourquoi le camp adverse disparaît quand on
inverse les `TeamId`. La chaîne est fermée, **et l'étape qui échoue l'est aussi depuis le
2026-08-23** — mais ce n'est **aucune** de celles que ce document accusait : cf. §5.

⛔ **VERDICT : inverser les `TeamId` FONCTIONNE côté natif.** Les cinq abandons muets sont
négatifs et les 10 unités montent, dès lors qu'on ne laisse pas le HARNAIS viser un groupe de
spawn qui ne lui appartient plus (§5ter). La « disparition du camp adverse » était une collision
de tuiles causée par un `TWPI 0` codé en dur dans `rl_duel`, pas un refus du jeu.

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

## 2. ⚠ CINQ ABANDONS MUETS — ce sous-système NE LÈVE JAMAIS

| # | condition | effet | mesuré (§5) |
|---|---|---|---|
| 1 | `GetTeam` rend un `Nullable` **sans valeur** | escouade **entièrement passée** | ne tire **jamais** |
| 2 | `GroupForPlayer` rend **null** | escouade **entièrement passée** | ne tire **jamais** |
| 3 | `i >= groupe.SpawnPoints.Count` | `break` — unités restantes **abandonnées** | ne tire pas |
| 4 | `IsPredefinedUnitDisabledByModifiers` | unité **sautée**, compteur seul incrémenté | ne tire pas |
| 5 | `AddUnitOperation$$AreTilesDisallowedAndLog` | `Execute` rend **null** — unité inexistante | **C'EST LUI** |

Aucun ne produit d'erreur ni d'événement. C'est pour ça que chaque tentative ressemble à
« il ne se passe rien » : il n'y a **rien à voir**, par construction. Même famille que le
`UnitId` absent du catalogue d'une vague (`reference_vague_bc_gabarit_doit_etre_au_catalogue`).

⚠ **Le n°1 est structurellement INATTEIGNABLE**, et ça se lit :
`StateExtensions.u003CGetTeamPlayersu003Ed__39$$MoveNext` filtre sur `PlayerComponent+0x24`, soit
le **même champ** dont `GetTeam` tire le `teamId` qu'il passe — un joueur est donc toujours présent
dans l'énumération de sa propre équipe. Mesuré `hasValue` vrai **5/5** dans les deux régimes.

⚠ **Le n°4 est ORTHOGONAL à l'équipe** : son corps ne lit que la liste de modificateurs indexée par
`unitId`, jamais un `TeamId`. Il écarterait les mêmes unités dans les deux sens.

⚠ **Le n°5 n'est PAS dans `AddPredefinedUnits`** — il est en **aval**, dans l'opération de
placement, et c'est pourquoi quatre relectures de la pose ne pouvaient pas le trouver.

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

## 5. RÉSOLU (2026-08-23) — c'est l'OCCUPATION DE TUILE, en aval de la pose

**La prémisse de ce document était fausse.** « Un des abandons de `AddPredefinedUnits` tire » est
**réfuté par la mesure** : sous inversion, les quatre sont négatifs et la pose se déroule
**parfaitement** — puis la bataille est vide quand même.

Capteur : `frida/hooks/probes/setup-spawn-trace.ts` (`setupSpawnTrace {action:"arm"}`), qui ancre
les cinq points. Ce que le régime inversé rend :

```
GetTeam            5 fires   VIDE=0                  <- n°1 negatif
GroupForPlayer     5 fires   NULL=1 (equipe 0 seule) <- n°2 negatif, le null est l'environnement
DisabledByModifiers 5 fires  DISABLED=0              <- n°4 negatif
                   5 unites pour un groupe de 5      <- n°3 negatif
AddUnitOperation.Execute 10 fires  RENDU-NULL=5
gates: disallowed=5  reserved=0  inFog=0  pendingDraft=0
```

Les 5 unités **prédéfinies** se posent (`executeNull=False`) ; les 5 unités **du joueur**, placées
**après** `setupLeave`, sont refusées 5/5 par `AreTilesDisallowedAndLog`. Les trois autres gates
valent `None` — jamais atteintes, celle-là court-circuite avant.

**Cause : collision de tuiles, DOSE-DÉPENDANTE.** Le même montage avec **une seule** unité adverse
rend **exactement une** refusée (`custoAtlacoya`) et **les quatre autres montent**. Un pour un :
les N unités prédéfinies occupent N tuiles du groupe, et N unités du joueur sont refusées.

**Ce qui n'est PAS en cause** : la résolution d'équipe. Sous inversion, `GetTeam` et
`GroupForPlayer` s'échangent proprement (joueur 12 → équipe 1 → index 0 ; joueur 11 → équipe 2 →
index 1), et l'index re-dérivé du §3 concorde **4/4** avec le natif.

## 5ter. Le choix de tuile est HARNAIS — et le natif encaisse l'inversion SANS BRONCHER

**Tranché le 2026-08-23.** `rl_duel.py` (≈ l.1205) place les unités du joueur sur **TWPI 0, en dur** :

```python
spawns = _spawn_points_by_twpi(bc)
player_pts = spawns.get(0) or []          # <- TWPI 0 CODE EN DUR
```

Après inversion, le joueur 11 passe en équipe 2, donc son groupe natif est TWPI **1** — mais le
harnais l'envoie toujours sur TWPI 0, devenu celui de l'IA, dont l'escouade prédéfinie vient
d'occuper les 5 tuiles. D'où la collision, et d'où le rapport 1-pour-1.

**Preuve** : même seed inversée, mais unités du joueur placées explicitement sur les points de
TWPI 1 (`--place custoAtlacoya:6,8 ...`) :

```
AddUnitOperation.Execute  10 fires  RENDU-NULL=0
gates: disallowed=0  reserved=0  inFog=0  pendingDraft=0
```

**Les 10 unités montent**, confirmé au second canal (`rl_duel view` : A-E et a-e sur le plateau),
et la vue annonce « c'est le tour de l'ADVERSAIRE (team 1) » — l'inversion porte jusque dans
l'ordre des tours. ⇒ **Inverser les `TeamId` FONCTIONNE côté natif.** Aucun gate ne tire.

⚠ **DEUX faux rouges du harnais sous inversion**, à ne pas prendre pour des refus natifs :

| symptôme | réalité |
|---|---|
| `roster NON MONTE ... x0` | comptabilité indexée par ÉQUIPE, désalignée par l'inversion |
| `placement NON HONORE ... @NULLE PART` | idem — l'unité est là, sur l'autre équipe |

Les deux ont accusé des unités **démontrablement présentes**. C'est l'hypothèse `p-units == team 1`
qui traverse tout `rl_duel` (`--p-units` « MON roster (team 1) », `_verify_roster` qui itère
`(1, p_units), (2, a_units)`), pas un verdict du jeu.

⚠ L'unique montage où les 7 NPC sont apparus était la configuration **instable** (correspondance
de groupes clé par la VALEUR, donc non idempotente sous `consumeOnce: false`) — un artefact, pas
un succès. « La capacité du groupe explique l'absence » est **RÉFUTÉ**.

⚠ `unitsAlive` en phase `Setup` est un **mauvais oracle** : 5, puis 7, puis 5 selon les
configurations, sans que ce qu'il compte à ce moment-là soit établi. Il a fondé trois
conclusions successives, toutes corrigées par ce que l'utilisateur voyait à l'écran.

## 5bis. Reproduction HORS LIGNE — plus besoin d'une bataille réelle

```powershell
python -c "import json; bc=json.load(open('data/seed-bc.json',encoding='utf-8')); p=bc['Player']['Players']; p['11']['TeamId']=2; p['12']['TeamId']=1; json.dump(bc,open('logs/_inv.json','w',encoding='utf-8'))"
python scripts/python/rl_duel.py build --seed 777 --board MC1_67 --seed-bc logs/_inv.json --state-file logs/_inv_state.json
```

**Le TÉMOIN doit passer par `--seed-bc` lui aussi** (copie non modifiée) : cette voie déclenche une
re-synthèse d'abilities que le chemin par défaut ne fait pas. Contrôlé — le témoin `--seed-bc`
monte sans erreur, donc **seul le `TeamId` diffère** entre les deux runs.

⚠ La seed BC ne porte qu'**UNE** entrée `PredefinedUnits`, `Id=12` — le joueur **IA**.
`AddPredefinedUnits` ne pose donc **que l'escouade adverse** ; les unités du joueur arrivent par un
autre chemin. Toute lecture qui suppose les deux camps posés là est fausse.

⚠ Le contrôle de roster de `rl_duel` rend « NON MONTE » pour des unités **réellement présentes**
sous inversion : sa comptabilité est indexée par équipe, et l'inversion la désaligne. Ne pas
conclure de ce message ; lire la trace (cf. §5ter).

**Pour monter une bataille inversée QUI MARCHE**, ajouter le placement explicite sur le groupe
réel du joueur (TWPI 1 après inversion) — sinon le harnais vise TWPI 0 et tout se télescope :

```powershell
python -c "import sys; sys.path.insert(0,'scripts/python'); from rl_collect_batch import _load_board_dump, _spawn_points_by_twpi as f; d=_load_board_dump('MC1_67'); print(f({'Board':d['board'],'SpawnPointSetIndex':d.get('spawnPointsSet') or 0}))"
# -> TWPI 1 = [(6,8),(6,7),(5,8),(4,8),(6,6)] pour MC1_67
rl_duel.py build ... --place "custoAtlacoya:6,8" --place "genesKelermorph:6,7" ...
```

Le déficit de roster reste imprimé (faux rouge, §5ter) : `TACTICUS_ALLOW_ROSTER_DEFICIT=1` le lève.

## 6. Sûreté — le BOARD persiste, la BC non

Mesuré à la restauration : les `TeamId` étaient **déjà revenus d'eux-mêmes** (la BC est
reconstruite à chaque `LoadBattle`) alors qu'un groupe de spawn portait **encore** l'écriture
d'un montage précédent. Muter `TeamWithPlayerIndex` n'est donc **pas borné à la bataille
courante** : ça survit et ça peut fuir vers une partie réelle. Toute expérience dessus se
termine par une remise à l'état d'origine — et il n'existe aucun garde qui l'impose.

## 6bis. ⚠ Deux pièges d'ANCRAGE, tous deux payés

**`GetTeam` a un PREMIER ARGUMENT CACHÉ.** Il rend un `Nullable<ValueTuple<TeamId,TeamPlayerIndex>>`
— 12 octets, donc retourné par **pointeur caché (sret)**. Le profil réel est
`GetTeam(bufferRetour, state, player)`, le joueur arrivant en `R8`. **Ghidra nomme ses paramètres à
côté de la plaque** : son `state` EST le buffer, son `player` EST l'état, et le joueur réel
n'apparaît que comme un `in_R8` **non déclaré**. Lire `args[1]` comme « le joueur » lit l'ÉTAT,
silencieusement.

**La disposition du buffer est l'INVERSE de la disposition C#.** `Nullable<T>` s'écrit
`{ T value; bool hasValue; }` en C# ; IL2CPP émet ici :

```
buf+0x0  hasValue (int32)   buf+0x4  TeamId   buf+0x8  TeamPlayerIndex/rang
```

⚠ **La faute était INDÉTECTABLE au décompilé** — les deux lectures sont cohérentes avec le code —
**et elle se présentait comme un RÉSULTAT CRÉDIBLE** : `hasValue` sortait faux **5/5**, soit
exactement la sortie muette n°1 qu'on cherchait. Ce qui l'a tuée est un **SECOND CANAL** : les
arguments que `GroupForPlayer` reçoit juste après sont `(teamId, rang)`, et ils coïncidaient 5/5
avec `buf+0x4`/`buf+0x8`, jamais avec `buf+0x0`. **Un capteur qui ne se recoupe avec rien peut
confirmer l'hypothèse qui l'a fait naître** — c'est la leçon la plus chère de cette tranche.

## 7. Outil

`scripts/python/env_ability_patch.py --inverser-equipes` écrit les deux (équipes ET groupes),
en place, par le patch `LoadBattle.onLeave`. La correspondance de groupes est clé par la
**position**, jamais par la valeur : une table `{0→1, 1→0}` lue sur la valeur n'est pas
idempotente et se défait au second passage.
