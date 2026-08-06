# #477-r24-r1 / -r2 — le mapping slot ↔ méthode d'`IOperationProcessor` SE LIT ; les deux lectures qui se contredisaient étaient JUSTES

**LIVRÉ.** Build `rnca9r7q6c`, metadata IL2CPP + ghidra-mcp. Aucun runner, aucune injection.

```powershell
python scripts/python/probe_477r24r1_slots_interface.py [--mutants|--regenerer]
python -m pytest scripts/python/tests/engine/test_477r24r1_slots_interface_offline.py -q
```

## 1. La contradiction, et pourquoi elle n'en était pas une

Deux fiches publiées se contredisaient sur le mapping slot ↔ méthode de
`Core.Services.IOperationProcessor` :

| | ce qui était affirmé | verdict mesuré |
|---|---|---|
| `case-477r24` | `0x57` = `HealUnit`, `0x60` = `KillUnit`, `0x61` = `DestroyMachine`, slot 99 = `ReviveUnit` | **JUSTE, 4/4** |
| `case-477r20` | `0x16` = `ContinueTurnPhase`, `0x20` = `VerifyAutomaticTurnEnd`, `0x12` = `StartMatch` | **JUSTE, 3/3** |

**Aucune des deux n'est fausse. Ce qui était faux, c'est la grandeur par laquelle on les
comparait** : un « décalage » entre le slot et la *position* de la méthode dans le dump de la
**classe**. Le slot d'interface est un rang dans la table de l'**interface** ; ce sont deux ordres
distincts, qu'aucune relation ne lie. Leur soustraction n'avait donc aucune raison d'être
constante, et deux valeurs locales différentes (12 ici, 4 là) ne prouvaient rien.

Pire : cette « position » n'est même pas définie. `frida/methods.tsv` est indexée par **adresse**,
donc elle **perd les surcharges à corps dédupliqué** — mesuré, **149** lignes pour **150** entrées
réelles, l'écart s'installant dès l'index 87, c'est-à-dire *au milieu* de la zone où le décalage de
12 avait été mesuré.

⇒ **La leçon n'est pas « l'un des deux avait tort ». C'est qu'un désaccord entre deux mesures
justes accuse la GRANDEUR qui les relie.** Trois tranches ont cherché laquelle des deux lectures
retirer ; il fallait retirer le *pont*.

## 2. Ce qui le dérive — le champ `slot`, et pourquoi personne ne l'avait lu

Le rang d'une méthode d'interface vit dans `Il2CppMethodDefinition.slot`, dans
`global-metadata.dat`. Il est invisible partout ailleurs, et c'est ce qui avait rendu la question
« non dérivable » :

* aucune ligne dans `frida/methods.tsv` — **0** dont la colonne classe vaut
  `Core.Services.IOperationProcessor` (les 146 occurrences du nom y sont des **types de
  paramètres**) ;
* aucun symbole dans `ghidra/functions.tsv` : une méthode d'interface n'a pas de corps ;
* rien à décompiler.

**Le décompilé, lui, ne porte que le nombre — mais il le porte LITTÉRALEMENT**, additionné à
l'`interfaceOffset` de la classe réceptrice. Dans
`IdunBattle.Entities.Behaviours.HealBehaviour$$Execute` :

```c
if (*(longlong *)(*(longlong *)(K + 0xb0) + i * 0x10) == DAT_18336dba8) {   /* IOperationProcessor */
    puVar12 = (undefined8 *)
              ((longlong)(*(int *)(*(longlong *)(K + 0xb0) + 8 + i * 0x10) + 0x57) * 0x10
               + 0x138 + K);
...
puVar12 = (undefined8 *)FUN_1801e7040(in_R9,DAT_18336dba8,0x57);   /* fallback */
```

`+ 0xb0` = `interfaceOffsets`, `+ 0x12e` = son compte, entrées de `0x10` octets, `+ 0x138` = début
de la vtable. Le `0x57` est donc **le slot d'interface**, sans transformation.

### La localisation ne lit PAS le header

Ce build annonce `version = 39`, qui n'est aucune version Unity publique, et son header ne suit pas
le layout `Il2CppGlobalMetadataHeader` connu : la paire (offset, taille) de la table des méthodes
n'est à **aucune** des positions attendues — seule celle des chaînes y tombe juste. `il2cpp_metadata.py`
n'en lit donc **aucun champ** et localise les tables **par contenu** :

1. les méthodes d'un type sont **consécutives** dans la table, et les **différences** de
   `nameIndex` valent exactement les différences de position des chaînes dans le fichier —
   grandeur observable, elle, quand le décalage de base ne l'est pas ;
2. la localisation n'est retenue que si elle se **vérifie** : on re-décode les méthodes de la
   classe et on exige nom **et** arité concordants sur un préfixe d'au moins 40. Une localisation
   non vérifiée est **refusée**, jamais rendue au petit bonheur.

Résultat : pas de 32 octets, **150** slots (`0..149`), tous `flags = 0x05c6` (abstract | virtual |
newslot | public) ; la 151ᵉ entrée bascule sur `0x01e6` — l'implémentation concrète. **La table se
délimite elle-même.**

### Le contrôle qui rend le résultat sûr

Pour chaque ancre, `file_offset - slot × pas` doit donner **le même** début de table. Si `slot`
n'indexait pas une table contiguë, les six ancres divergeraient. Elles ne divergent pas — c'est
mesuré, et le module **refuse** si ce n'est plus le cas.

## 3. La confrontation — 9 call-sites, 9 arités concordantes

`IdunBattle.Operations.KillUnitOperation$$Execute` porte **9** dispatchs sur cette interface. Le
tableau est la contre-épreuve : aucune arité ne se contredit.

| slot | méthode (metadata) | `param_count` | args au site | branche |
|---|---|---:|---:|---|
| `0x4d` ×4 | `EvaluateAbilities` | 2 | 2 | avant la garde / `if` ×2 / queue commune |
| `0x50` | `EvaluateAbilitiesImmediately` | 2 | 2 | `if` |
| `0x82` | `ProcessVictoryPointEvent` | 1 | 1 | `if` |
| `0x8f` | `AddScore` | 1 | 1 | `if` |
| `0x06` | `RemoveUnit` | 3 | 3 (`killed, 0, 1`) | `if` |
| `0x55` | `UnregisterEntityFromTriggers` | 2 | 2 | `if`, dernière instruction |
| `0x63` | `ReviveUnit` | 1 | 1 (`killed`) | **`else`, seul et unique contenu** |

Les quatre `0x4d` passent `1`, `0`, `0x36`, `0x35` en premier argument — des `EventTriggerType`,
ce qui recoupe indépendamment la séquence d'événements de mort établie par `#462-r4b`.

⚠ **Ghidra imprime le slot du revive en DÉCIMAL (`FUN_180003c00(99,DAT_18336dba8,…)`)**, ce qui le
rend invisible à toute recherche portant sur `0x63`. C'est ce qui a fait échouer trois recherches
littérales avant qu'un balayage complet du décompilé ne le trouve.

### Et 43 attestations déjà écrites dans le dépôt

Le dépôt cite des slots de cette interface depuis des dizaines de tranches indépendantes. Confrontées
à la table : **43 attestations, 1 seule fausse** (§ 5). Les concordances couvrent `0x23`
= `FinishUnitTurn` (`case-291`), `0x76`/`0x77` = `MarkUnitAs{No,}ActionAvailable` (`case-287-r1-r1`),
`0x46` = `DiscardHit` (`case-366-r1`), `0x26`/`0x27` = `AddTrait`/`RemoveTrait` (`case-366-r1`),
`0x3a`/`0x3b` = `StartAttack`/`FinishAttack` (`#437`), `0x42`/`0x43` = `DealDamage`/`ApplyDamage`
(`#462-r4e-o`), `0x58` = `RepairUnit` (`case-299`)… Une table fausse aurait fait rougir des dizaines
de fiches écrites sans se connaître.

## 4. `-r2` — le slot `0x55` : ni `RemoveUnit`, ni `RotateUnit`

`IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass50_0$$u003CVerifyRemovedUnitsu003Eb__0`
appelle `FUN_180005260(0x55, DAT_18336dba8, <processor>, <entité>, 1)` — **deux** arguments.

| candidat | slot | arité | verdict |
|---|---|---:|---|
| `RemoveUnit` (lecture de `#477-r19`) | `0x06` | 3 | **exclu** — mauvais slot ET mauvaise arité |
| `RotateUnit` (crainte de `#477-r24`) | `0x86` | 2 | **exclu** — mauvais slot |
| **`UnregisterEntityFromTriggers`** | **`0x55`** | **2** | **retenu** |

Sémantiquement net : quand un acteur quitte le match, on le **désinscrit des triggers**.

**Effet de bord : `#477-r19-r1` est DISSOUS.** Ce résidu postulait un contenu
(`Action=RemoveUnit` + `Unit_IsDying` + `Unit_WasOverkilled`) que quatre gardes auraient masqué,
et cherchait le montage qui le ferait apparaître. Il n'y a pas de contenu :
`UnregisterEntityFromTriggers` n'émet aucune action de flux. Les **11 occurrences vides** mesurées
par `#477-r19` étaient la mesure **juste** d'un groupe qui est une enveloppe, toujours. Le port
était donc déjà complet, et on chassait un fantôme créé par une attribution de slot fausse.

⚠ La même lambda était déjà décrite par `case-227` (étape 11, « slot `0x55` `(entity, false)` »),
qui l'avait laissée **non identifiée** plutôt que devinée. Ne pas nommer valait mieux que mal
nommer : c'est `#477-r19`, en lui donnant un nom plausible, qui a introduit la faute.

## 5. Les gardes

`probe_477r24r1_slots_interface.py` (mesure) + `test_477r24r1_slots_interface_offline.py`
(cliquet, 22 verts), quatre étages :

1. **DÉRIVATION** — relit les slots dans le metadata. Tri-état : metadata absent ou désynchronisé
   ⇒ `PAS MESURE`, jamais un zéro ni un vert (`build_pin.global_metadata()`, pendant exact de
   `game_dll()`).
2. **CLIQUET** — confronte la dérivation à l'entrée **versionnée**
   `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`. C'est elle qui rend les étages
   3-4 jouables dans un worktree où le jeu n'est pas installé.
3. **CITATIONS** — balaie le dépôt (périmètre **dérivé** d'un `git ls-files`, aucune liste
   blanche) et confronte chaque couple (slot, nom).
4. **ARITÉ** — compare le nombre d'arguments écrit au site au `param_count`.

**Ce que l'étage 3 ÉCARTE est compté et imprimé** : **5 684** lignes dont le récepteur ne désigne
pas cet `OperationProcessor` (les slots d'`IBattleQuery`, `IAttackQuery`, `IMatchState`, des
effets — le dépôt en cite beaucoup plus que des nôtres), **129** qui citent un slot sans lui
accoler de nom (rien à contredire, donc rien à garder), **1** fichier exclu et nommé (le probe
lui-même, dont les regex de documentation contiennent des exemples de syntaxe).

**La garde a été vue ROUGE avant d'être crue** — et sur une vraie faute, pas un mutant :
`engine/runner/operations/revive.py` citait `slot 0x7e = MoveUnit` là où `0x7e` est
`SetUnitPosition` (3 arguments, ce que le site passe ; `MoveUnit` est au slot `0x65` et en prend 4).
Corrigé.

**Contre-épreuve : 4 mutants, 4 mordent**, chacun sur l'étage visé — `slot-decale`
(cliquet 0→146), `nom-permute` (0→2 / 0→5), `table-tronquee` (0→110 / 0→36), `arite-fausse`
(0→150 / arité 0→4). `a_mordu` est rendu **séparément** du verdict.

⚠ **`nom-permute` a d'abord été INERTE** : il permutait les slots `22` et `99`, qu'aucun site ne
nomme — la contre-épreuve passait pour mordante en ne touchant rien. Les deux slots sont désormais
**dérivés des citations réelles**, et le mutant refuse de s'exécuter s'il y en a moins de deux.

⚠ **Le premier extracteur de noms rendait 32 désaccords, dont 30 FAUX** : il retenait tout mot
capitalisé de la ligne, si bien qu'une ligne de `backlog.md` fournissait trente « noms ». Il ne
retient plus que des couples (slot, nom) **adjacents**, et refuse trois formes précises qui
produisaient chacune un faux positif mesuré : un nom suivi de `$$` (c'est une **classe**,
`FinishAttackOperation$$Execute`), un `slot` intercalé entre les deux (`StartAttack slot 0x3a … 
FinishAttack slot 0x3b` attribuait le nom du second au premier), et une parenthèse **fermante**
franchie (le nom appartenait à la proposition suivante). Le lookahead qui rejette `$$` doit aussi
interdire les caractères de mot, faute de quoi le moteur backtracke et rend un nom **tronqué**
qui, lui, n'est plus suivi de `$$` (mesuré : `FinishAttackOperatio`).

**Ce que les gardes ne voient pas, et c'est dit** : les slots des **autres** interfaces (résidu
`#477-r25`) ; les citations de slot sans nom ; la prose.

## Résidus

- **#477-r25 — les slots des AUTRES interfaces ne sont pas gardés, et le gisement est
  probablement fautif.** Le dépôt cite couramment `battleQuery.<slot 0x7f>`,
  `attackQuery.<slot 0x11>`, `matchState.<slot 0x31>`, des slots d'effets et de
  `IStreamDispatcher` — **5 684** lignes écartées par l'étage 3 en portent la majeure partie, et
  **aucune** n'est confrontée à quoi que ce soit. Le mécanisme livré ici est générique
  (`il2cpp_metadata.interface_table` prend l'interface en paramètre) : il ne manque que
  l'appariement `nom d'interface ↔ récepteur écrit au site`, qui n'est pas mécanique
  (`battleQuery` désigne `IBattleQuery`, mais `aq`, `def`, `effectAction` demandent une lecture).

  **Sondage sur `IBattleQuery` (219 slots) — 2 concordent, 3 divergent** : `0x64` =
  `GetTilesAtDistance` ✅ (`case-433-r4…`), `0x7f` = `GetAdjacentEnemies` ✅ (`case-27`) ; mais
  `GetAdjacentFriends` est lu en `0x81..0x84` là où `case-250` écrit `0x80`, et
  `GetFreeAdjacentTiles` en `0x52`/`0x53` là où `case-250` et `case-243` écrivent `0x51` (qui est
  `GetAdjacentTiles`, 4 arguments).

  ⚠ **Ce sondage n'est PAS concluant, et il ne doit pas être cité comme un verdict.** Deux
  raisons : le décompilé d'`IBattleQuery` n'a **pas** été confronté (ici, ce sont 9 call-sites
  décompilés qui verrouillent la table) ; et un décalage global de −1 rendrait `case-250`
  entièrement juste tout en cassant `case-433`. Ce qui est **certain**, en revanche, c'est que
  le dépôt se contredit **déjà lui-même** : `case-27` place `GetAdjacentEnemies` au slot `0x7f`,
  `case-250` au slot `0x7c`. Au moins une des deux est fausse, indépendamment de toute table.
  ⇒ **Le retournement annoncé est acquis : le gisement mérite le même traitement.** Ce qu'il
  faut pour le traiter : des call-sites décompilés sur `IBattleQuery`, comme ici.
