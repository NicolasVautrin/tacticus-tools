# #477-r15 tranches A + B + E — le port ÉMET le flux de replay, et un cliquet le juge

**Build** `rnca9r7q6c`. Mesure live session Frida **8** (2 runners montés et disposés), plus une
garde offline. Code : `scripts/python/engine/streams/`. Probe :
`probe_477r15a_stream_conformance.py`. Garde : `tests/engine/test_477r15_stream_emitter_offline.py`.

## Verdict en une ligne

Le port émet désormais le flux, et sur le déploiement il est **identique au natif caractère par
caractère** : **161 / 204** lignes égales sur `C1_02`, **273 / 316** sur `MC1_67`, **0 divergence
NOUVELLE** des deux côtés. Tout ce qui manque est une ligne `ChangeStats` / `ChangeAbility` dont le
producteur natif est maintenant **nommé** — et ce n'est pas celui qu'annonçait la fiche parente.

> ⚠ **Ces deux fractions sont celles de CETTE tranche, et elles sont PÉRIMÉES depuis.** La
> **tranche D** a fermé les 43 divergences restantes : `204 / 204` et `316 / 316`, registre de
> divergences **VIDE**. Détail : `docs/rl/case-477r15d-tags-etat-complet-unite.md`. Les sections
> ci-dessous décrivent l'état À LA FIN DES TRANCHES A + B + E — les re-dériver, pas les citer.

## 1. La grammaire : ce que le décompilé donne, et ce qu'il ne donne pas

`IdunBattle.BattleStream.Loggers.StreamCache` est le writer. Sa disposition et ses quatre méthodes
se lisent intégralement (`+0x10` profondeur, `+0x18` `StringBuilder`, `+0x20` listeners), et le
mirror Python est ligne à ligne. **Cinq littéraux ne s'y lisent pas** : les chaînes .NET vivent
dans `global-metadata.dat`, pas dans le PE — Ghidra ne rend que des `DAT_*`. Ils sont donc
**MESURÉS** sur le flux réel, et la docstring du mirror le déclare.

| trait | valeur | d'où |
|---|---|---|
| unité d'indentation | **4 espaces** | mesuré (`case-477` §10.7 disait « tabulations » — faux) |
| séparateur | **LF**, dans les gabarits | mesuré : 11 645 octets, **0 CR**, **0 TAB**, 319 LF |
| `Group=` | `Group={0} Entity={1} Source={2} InitialTarget={3}\n` | mesuré |
| `Action=` | `Action={0} Entity={1}\n` | mesuré |
| `Tag=` | `Tag={0}:{1}\n` | mesuré |

### Le tri des tags est par ORDINAL, jamais alphabétique

`StreamCache$$Action` recopie les tags dans un `SortedDictionary<TagKey,int>` : le comparateur par
défaut d'un enum .NET trie sur la **valeur**. Mesure de contrôle sur le flux de `C1_02` — **66**
blocs d'action, **0** hors de l'ordre des ordinaux, **49** hors de l'ordre alphabétique. Un writer
qui trierait par nom produirait un flux faux sur les trois quarts de ses blocs.

Ce point tranche aussi une **hypothèse laissée ouverte par la RE des producteurs de tags** : ceux-ci
insèrent dans un `Dictionary` non ordonné, et l'ordre d'insertion natif n'est pas celui du flux. Le
lieu du tri n'était pas localisé — il l'est : c'est `StreamCache$$Action`, pas le producteur.

### `Entity=NO_ENTITY` n'est pas un cas particulier du writer

L'identifiant est **boxé** avant formatage, et le type boxé est `IdunBattle.Core.BEntityId`, un enum
à un seul membre (`0=NO_ENTITY`). `Enum.ToString()` de .NET rend le nom quand la valeur est un
membre et le décimal sinon — d'où `0 → NO_ENTITY` et `49 → 49` sans aucune branche. Le même boxage
se relit dans `IdunBattle.Core.Entity$$ToString`. Mirror : `format_enum_value`, qui sert aussi aux
trois enums de stream (un ordinal inconnu doit s'écrire en clair, pas lever).

## 2. Ce que le port émet

Face STREAM seule — rien de ce qui construit l'état.

| natif | port | vérifié |
|---|---|---|
| `SetupGameOperation$$Execute` | `emit_game_setup` | `StartGroup(3, 1, null, null)` puis `FinishGroup` |
| `AddPlayerOperation$$Execute` | `add_player` | `Action(AddPlayer, e, {Player_Id})` |
| `AddTileOperation$$DispatchTileAddedEvent` | `add_tile` | `{Tile_Column, Tile_Row, Tile_IsTerritory}` |
| `AddMachineOfWarPlatformOperation$$Execute` | `add_machine_platform` | `Action` NUE, `{MachinePosition}` |
| `StreamHelper$$GetAddUnitTags` | `get_add_unit_tags` | 6 tags + 7 tuiles de pied |
| `StreamDispatcher` / `StreamCache` | `dispatcher.py` / `stream_cache.py` | mirror 1:1 |

**Les deux positions de plateforme sont EN DUR dans le décompilé** — `SetupGameOperation` appelle
deux fois `AddMachineOfWarPlatform` avec `position = 2` **puis** `1`. Le port les émet donc ; seuls
leurs ids d'entité restent des entrées.

### Le groupe `AddUnit` est CONDITIONNEL, et c'était invisible du flux

`StartGroup` **et** `FinishGroup` d'`AddUnitOperation$$Execute` sont tous deux enveloppés dans le
même test `IdunBattle.Core.Services.BattleQuery$$get_UseGroupForAddUnit` (un drapeau de la
configuration de bataille, lu à `config+0xe0`). Si le drapeau est faux, les trois `Action` sont émis
**sans groupe englobant**. Le port l'expose en paramètre (`use_group_for_add_unit`) plutôt qu'en
structure figée ; sa valeur par défaut `True` est **OBSERVÉE**, pas lue — cf. résidu `#477-r15-r2`.

## 3. Le cliquet à trois états

`conforme` / `divergent CONNU` (inscrit au registre avec sa cause) / `divergent NOUVEAU` — le seul
qui rougit. La classification nomme chaque divergence par sa **forme** et son **symbole**
(`MANQUANT Action=ChangeStats`), jamais par un extrait de texte : une renumérotation de build fait
bouger le nom, pas la clé.

### La propagation de cause, bornée à UN cran

Une `Action=` absente entraîne **mécaniquement** l'absence de tous ses `Tag=`. Sans propagation, le
premier run rendait **39 divergences NOUVELLES pour 6 causes**, et la seule issue aurait été
d'inscrire 37 tags au registre — c'est-à-dire de le faire grossir jusqu'à tout couvrir, exactement
ce que la purge existe pour empêcher. Un `Tag=` hérite donc de son **porteur** (déterminé
structurellement par l'indentation : `StreamCache$$Action` écrit ses tags à `depth+1`), et
seulement si ce porteur est lui-même inscrit **sous la même forme**. Un `Tag=` manquant sous une
action que le port **émet** reste NOUVEAU — c'est le cas qui compte, et il est gardé par un test.

### La purge a mordu dès son premier passage

`MANQUANT Action=AddMachine` avait été inscrite au registre **par anticipation**, sans qu'aucun
scénario ne l'exerce. Le premier run l'a signalée **PÉRIMÉE** et fait rougir la passe. Elle a été
supprimée, pas élargie. C'est la mécanique voulue : un registre qu'on n'a pas le droit de garnir
« au cas où ».

⚠ La purge s'évalue sur le **corpus complet** d'une passe (l'union des clés exercées par tous les
scénarios), jamais sur un scénario isolé — sinon jouer un seul board rendrait périmées les entrées
de tous les autres.

### Le non-comparé est PUBLIÉ, en trois bornes DÉRIVÉES

Le rapport imprime, à chaque run :

- **(a)** le périmètre dérivé des **enums** (104 / 62 / 244), avec le compte exercé — sur le
  déploiement : `GroupType` **2/104**, `StepType` **6/62**, `TagKey` **36/244**. Un comparateur
  calibré sur l'observé serait muet sur le reste **sans le dire** (`#477-r13`) ;
- **(b)** les **12** omissions structurelles du flux — `Defense`, `EvasionChance`, les 7 stats
  `Extra*` (modification seule), `visualId`, `rank`, le tirage PRNG brut. Aucun diff de flux ne les
  tranchera, quoi qu'on porte ;
- **(c)** les grandeurs que le port a **reçues du flux natif**. Comparer une valeur copiée de
  l'oracle ne mesure rien — elles sont nommées et exclues du verdict. Elles étaient **5** ; le merge
  de `#477-r16` en cours de tranche les a ramenées à **2** (voir ci-dessous).

**Non comparé ≠ égal.**

### L'hypothèse « les ids d'entité sont des ENTRÉES » est RELEVÉE

Cette tranche a commencé avec une hypothèse explicite : le port ne calcule aucun id d'entité, il les
reçoit, et ils sont donc **exclus du verdict**. Ce qu'elle interdisait : conclure quoi que ce soit de
l'égalité des `Entity=` — donc de la moitié des caractères de chaque ligne.

`#477-r16` (mergé le 2026-08-05) a rendu la règle **mécanique**, et le probe la consomme :
`deriver_regle()` rend `3 + P + E` depuis les entrées versionnées, et le probe en dérive les ids des
joueurs, des tuiles, des **deux plateformes** et de la **première unité**. Mesure, sur les deux
boards :

| board | 1ʳᵉ tuile | plateformes | 1ʳᵉ unité (dérivée) | 1ʳᵉ unité (`observeBattle.squadId`) |
|---|---:|---|---:|---:|
| C1_02 (35 tuiles) | 12 | 47, 48 | **49** | **49** |
| MC1_67 (63 tuiles) | 12 | 75, 76 | **77** | **77** |

Les ids ne sont donc plus fournis : ils sont **calculés puis confrontés**, et le probe **rougit** si
la règle dérivée ne recoupe ni le flux natif (plateformes) ni `observeBattle` (première unité). Que
les 161 / 273 lignes restent égales prouve d'ailleurs qu'ils sont justes — un seul id faux aurait
décalé tout le reste.

**Il reste UN terme non dérivé, et on ne le fige pas** : `GetDerivedEnvironmentAbilities` vaut 1 sur
tous les boards mesurés, mais il est obtenu **par différence** — il absorberait donc silencieusement
toute autre allocation manquée avant les tuiles. Le probe le calcule, le PUBLIE en borne (c) et le
rattache à `#477-r16-r1`. La borne (c) est donc réduite à ce terme et à `Tile_IsTerritory`.

## 4. Ce qui rend la mesure honnête : des canaux INDÉPENDANTS

Reconstruire les entrées depuis le flux natif rendrait l'oracle à lui-même. Chaque grandeur comparée
vient donc d'ailleurs :

| grandeur | canal |
|---|---|
| colonne / ligne de chaque tuile, **et leur ordre** | le **board dump** `data/boards/<kind>/<id>.json`, parcouru `Tiles[c].Tile[r]` |
| `Player_Id` de chaque joueur, **et leur ordre** | `BC.Player.Players`, trié par clé (le natif itère un `SortedDictionary`) |
| ids d'entité (joueurs, tuiles, plateformes, unités) | **calculés** par `#477-r16` — cf. ci-dessus |
| id d'entité de chaque unité (recoupement) | `observeBattle.units[].squadId` — dont #477-r15 a mesuré qu'il **est** le `Entity=` du flux |
| propriétaire, position d'unité | `observeBattle` |

⚠ **Un désaccord de NOMMAGE, sans désaccord de fait** : `case-477r16` §3 écrit le parcours des
tuiles `for row in 0..Width-1 { for col in 0..Height-1 }`, alors que le port parcourt le dump
`Tiles[c].Tile[r]` — soit, en termes de tags émis, colonne fixe et ligne variant
(`Tile_Column:0 Tile_Row:0`, puis `0/1`, … puis `1/0`). Les deux descriptions désignent le **même**
balayage : les indices du dump ne portent pas les mêmes noms que ceux du décompilé. Ce qui tranche
est la mesure — **98 lignes `AddTile` égales** sur les deux boards.

**L'ordre des tuiles est la mesure la plus forte du lot** : le parcours colonne-par-colonne du board
dump reproduit exactement l'ordre de `SetupGameOperation$$AddTiles`. S'il avait différé, les 35 (ou
63) lignes `AddTile` **et** le `Unit_Foot_Tile_Id_1` de chaque unité auraient divergé d'un coup.

⚠ **Un piège de lecture, transposé du flux vers le RPC d'état** : `observeBattle.units[].playerId`
porte l'**entité** du joueur (3, 4), **pas** son `PlayerId` de configuration (11, 12). C'est le
premier des trois pièges de #477-r11, et il a fait échouer le premier run du probe.

⚠ **Hypothèse de MONTAGE, pas du natif** : sur un runner `rl_duel build`, seules les unités de
l'équipe **adverse** sont posées par `AddPredefinedUnits` ; celles du joueur arrivent dans un groupe
racine séparé (`User_PlaceUnit`). Le probe le **vérifie** contre le nombre d'`Action=AddUnit` du
groupe natif et refuse d'attribuer la divergence au port si le compte ne colle pas.

## 5. La contre-épreuve — sans elle, « 0 nouvelle » ne vaut rien

Un comparateur qui rendrait vert quoi qu'il arrive donnerait exactement le même résultat. **Huit
mutations** du writer, chacune cassant un choix, et chacune doit rougir : indentation par
tabulation, indentation à 2 espaces, séparateur CRLF, tri alphabétique des tags, valeur de tag
fausse, ordre des tuiles inversé, positions de plateforme inversées, groupe `AddUnit` désarmé.
**8 / 8 détectées**, avec un bras témoin qui établit que le flux juste est conforme.

⚠ Et chaque bras vérifie d'abord que **la mutation a mordu** (`flux_mute != FRAGMENT_NATIF`) : un
bras négatif qui passe parce que le patch ne s'est pas appliqué rend le même vert qu'un comparateur
qui discrimine.

## 6. Ce que la RE a corrigé de la fiche parente

`case-477r15` §5 annonçait les tags par famille comme **10 `StreamHelper$$Get*Tags`**. Les tags de
`ChangeStats` et `ChangeAbility` — ceux qui manquent au groupe `AddUnit` — n'en font **pas partie** :
ce sont les **trois surcharges** de `IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags`,
partagées avec `AddMachineOperation$$Execute`, `ReAddMachineOperation$$Execute` et
`ResurrectUnitOperation$$SendStreamEvents`. La tranche D est donc plus large que recensée, et sa RE
est **faite** (tables complètes des 16 + 8 + 3 tags, avec leurs conditions) : ce qui manque au port,
ce sont les **entrées**, pas la rétro-ingénierie.

⚠ **Cette RE a été RE-VÉRIFIÉE au décompilé avant d'être portée, et elle était incomplète sur trois
points** que la tranche D a dû établir : la garde d'entrée rend un dictionnaire vide (donc une
`Action=ChangeStats` **sans aucun tag**, pas « pas de ligne ») ; `RemainingCooldownTurns` passe par
`GetValueOrDefault`, donc son tag est **toujours** émis ; et le dernier tag de la première surcharge
lit **trois** porteurs, dont deux enums qui partagent le nom `FinalJustice` à des ordinaux
différents. Tables complètes : `case-477r15d-tags-etat-complet-unite.md` § 2.

Deux pièges qu'un port écrit depuis le seul flux observé raterait :

- `UnitStats_TriggeredAbility_AmmoCost` (29) et `_EnoughAmmo` (30) sont **conditionnels** (abilities
  à munitions) et n'apparaissent dans aucun de nos flux ;
- `GetFullStateUpdateTags(unit)` a une garde d'entrée `EntityType.Unit` : sur toute autre entité il
  rend un **dictionnaire vide**, et l'`Action` est émis quand même.

## 7. Ce que je n'ai PAS fait

- **Aucune tranche C écrite dans `engine/`** : la règle d'allocation est **RE'd** (`#477-r16`, mergé
  pendant cette tranche) et le **probe** la consomme, mais l'émetteur lui-même reçoit toujours ses
  ids. Les porter dans `engine/streams/` — un `MatchComponent$$NextId` mirroré, avec son `+= 1`
  pré-incrémenté, son `ReturnLastId` et le fait que l'échec d'`AddUnitOperation` **brûle** l'id — est
  une tranche à part entière, et elle reste bloquée par `#477-r16-r1` pour son offset initial.
- ~~**Aucun `ChangeStats` / `ChangeAbility` émis** — tranche D.~~ **FAIT** (tranche D,
  `case-477r15d-tags-etat-complet-unite.md`) : les trois surcharges sont portées dans
  `engine/streams/unit_extensions.py`, le registre de divergences est vide, et la borne (c) est
  passée de 2 à 6 entrées — c'est le prix, PUBLIÉ, de ce que les canaux ECS ne discriminent pas.
- **`replaySteps` / `replayRngEvents` non exploités.** Ils sont vivants depuis la session 8, mais
  l'oracle de cette tranche est le **texte brut** de `GetWholeBattleOutputStream` : la barre reste
  l'égalité brute, et ces deux canaux ne l'auraient ni renforcée ni remplacée. Ils vaudront pour la
  tranche qui portera le déroulé.
- **Aucun scénario destiné à élargir la couverture du vocabulaire** (`#477-r13` intact) : le
  déploiement n'exerce que 2 `GroupType` sur 104.
- **Aucune modification d'`engine/runner/events.py`.** Le stub mort reste en place : 25 modules
  d'opération l'importent, et le supprimer serait une tranche à lui seul, sans rapport avec
  l'émission.

## Résidus

- **#477-r15-r1** — **Aucune table de STRING LITERALS IL2CPP dans `data/symbols/<build>/`.** Le
  `sourceId` passé par `AddUnitOperation$$Execute` à `StartGroup` est un handle de littéral, non
  résoluble statiquement (les chaînes vivent dans `global-metadata.dat`, pas dans le PE) ; le flux
  réel montre `Source=` **vide**, donc chaîne vide ou `null` — indiscernables après `String.Format`.
  Le même mur bloquera tout `Source=` **non vide** (`AvalancheOfMuscle_ExtraDamage`,
  `BlockEnteringUnits`…), c'est-à-dire la quasi-totalité du déroulé de bataille. **Condition de
  retournement exécutable** : ajouter au pipeline de dump un TSV `index → valeur` extrait de
  `global-metadata.dat`, puis vérifier qu'il rend `""` pour ce handle et le nom symbolique attendu
  pour un `Ability_Power`.
- **#477-r15-r2** — **`BattleQuery$$get_UseGroupForAddUnit` n'a jamais été confronté à FAUX.** Le
  port l'expose en paramètre, mais sa valeur par défaut (`True`) est **observée**, pas lue : le
  drapeau vit à `config+0xe0` d'une configuration de bataille dont le porteur exact n'est pas
  identifié. **Condition de retournement exécutable** : nommer le champ de `BattleConfiguration` qui
  l'alimente, monter un runner où il est faux, et vérifier que le flux natif émet bien les trois
  `Action` **sans** `Group=AddUnit` — et que le port le suit.
- **#477-r15-r3** — **`Tile_IsTerritory` est émis à 0 EN DUR.** Le natif le lit à `config+0x22` d'une
  configuration de tuile ; le board dump versionné n'expose aucun champ correspondant. Sur nos deux
  boards il vaut 0 partout, donc la constante passe — mais elle passerait aussi si elle était
  fausse. **Condition de retournement exécutable** : trouver un board (mode territoire /
  `TerritoryCapture`) où le flux natif porte `Tag=Tile_IsTerritory:1`, et vérifier que le probe le
  fait rougir en `VALEUR Tag=Tile_IsTerritory` avant de dériver le champ.
