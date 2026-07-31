# case-379 — un `--state-file` peut-il piloter le runner d'une AUTRE session ?

**Critère (binaire)** : après une (ré)injection, un state-file écrit *avant* la fenêtre
peut-il faire piloter le runner d'un **autre** agent — sans erreur ni refus ?

**Réponse : OUI, c'était le cas. Fermé par estampillage de la session au `build` + refus franc
au pilotage.** Re-dérivation : `python scripts/python/probe_379_state_file_session_stamp.py`
(`--live` pour l'étape 2).

---

## 1. Le mécanisme — le FICHIER est privé, l'ESPACE D'IDS est partagé

Un `--state-file` vit dans le `logs/` du worktree de son agent (gitignoré, il meurt avec le
worktree) et son chemin absolu est justement la clé `owner` du harnais. **Aucun agent ne lit
le fichier d'un autre** — la collision ne passe pas par là.

Elle passe par le **registre de runners**, unique, dans le script injecté
(`frida/hooks/game/runner-registry.ts`), commun à tous les appelants RPC quel que soit leur
worktree. `case-377` a établi que son `counter` est strictement monotone — donc qu'un id
périmé se fait **refuser** (`runner N not found`) — mais **seulement dans une session**. Une
(ré)injection remet `counter` à `0` pendant que les state-files, eux, **survivent sur
disque**.

## 2. Ce sont les PETITS numéros le danger

`case-377` §4 citait « une session montée à 332, au-delà du 261 de l'incident », ce qui
suggère qu'il faut une longue session pour être exposé. **C'est l'inverse.** Les ids sont
distribués en ordre **croissant** :

| id tenu à travers la fenêtre | délai avant collision |
|---|---|
| **bas** (2, 5, 12) | **quelques minutes** — le nouveau compteur y arrive tout de suite |
| haut (261) | longtemps : `runner N not found` jusqu'à ce que la session le rattrape |

Corollaire de méthode : un test de collision qui exercerait un id élevé ne verrait qu'un refus
bénin et conclurait à tort que la garde ne sert à rien. `probe_379` étape 2 falsifie donc sur
`runnerId = 2`.

## 3. Le tri-état, et la sous-division qui rend « absente » opérante

`scripts/python/runner_state.py` estampe le state-file du triplet `/api/admin/status` au
`build` et le reconfronte à chaque relecture :

| état | condition | décision |
|---|---|---|
| `MATCH` | estampille identique | passe, **silencieux** |
| `MISMATCH` | estampille différente | **REFUS** — nomme les deux sessions + quoi faire |
| `UNSTAMPED_STALE` | pas d'estampille **et** mtime antérieur au `startedAt` | **REFUS** |
| `UNSTAMPED` | pas d'estampille, fichier écrit pendant la session | **avertissement**, non bloquant |

`UNSTAMPED_STALE` n'est pas un raffinement décoratif : **au moment où la garde entre en
service, aucun state-file du disque ne porte d'estampille** — c'est-à-dire que l'état le plus
dangereux (fichier d'avant une fenêtre) est exactement celui que l'estampille ne sait pas
juger. Le mtime le juge quand même : un state-file est **ré-écrit à chaque action**
(`_save_state`), donc un mtime antérieur au `startedAt` **prouve** qu'aucune commande ne l'a
touché depuis l'injection. L'inférence ne vaut que dans ce sens ; un mtime postérieur ne
prouve rien et reste `UNSTAMPED`.

**Pourquoi ne pas refuser sur `UNSTAMPED` tout court** : un agent qui a build avec du code
d'avant puis **rebase en cours de run** (pratique courante — elle est exigée avant d'ouvrir
une PR) pilote ensuite avec le code d'après, sur un runner parfaitement valide. Ce chemin est
traversé par **tous** les tests live du dépôt : un faux refus y coûterait plus cher que le bug
fermé.

## 4. L'identité n'est PAS le seul `sessionId`

`nextSessionId` est un état de module du **host** (`frida/host/sessions.ts:38`), pas du bundle
injecté : un redémarrage du host le remet à `1`. Deux sessions distinctes peuvent donc porter
le même `id`, et une estampille réduite à `id` **validerait** un state-file mort. On estampe
le triplet `id` + `pid` + `startedAt` ; `startedAt` est un ISO à la milliseconde. Un champ
absent d'un côté ne tranche pas — on ne conclut à la divergence que sur un **désaccord
effectif**.

## 5. Le câblage, et ce qu'il garde (`probe_379` étape 0)

Cinq points, chacun perdable en une ligne, chacun dont la perte serait **silencieuse** :

* **G1** `_save_state` passe par `runner_state.stamp` — sans lui plus rien n'est estampé, tout
  retombe en `UNSTAMPED` et la garde s'éteint sans bruit ;
* **G2** `_load_state` fait `verify` + `enforce`, et `sys.exit(2)` **après** l'`enforce` (la
  fonction contient déjà une autre sortie, qui masquerait la disparition de celle-ci) ;
* **G3** le `disposeRunner` de `cmd_build` — **le site le plus dangereux du fichier**, il
  frappe un id relu sur disque — n'agit que sur `verdict.ok`. Le build lui-même n'est **pas**
  refusé : il *est* le geste « repartir à neuf », et il ré-estampe ;
* **G4** `cmd_attach` confronte son `--from` : sinon un id périmé serait recopié dans un
  state-file **neuf** et recevrait une estampille **fraîche** — le mensonge deviendrait
  indétectable en aval ;
* **G5** tout module **tiers** qui écrit un state-file via `rl_duel._save_state` pose
  `SESSION`. `SESSION` est un global de `rl_duel` posé par son `main()` ; `_wave_build.py`
  refait son propre build en le court-circuitant — il le laissait à `None`, donc `stamp`
  n'écrivait rien et la garde ne gardait rien. Trouvé en relisant les importeurs de
  `rl_duel`, corrigé dans le même commit (il dupliquait aussi le `dispose` non gardé de G3).
  Lu **par AST** : un balayage textuel s'attrape lui-même sur les commentaires qui citent
  `X._save_state(` — mesuré en écrivant ce probe.

`scripts/python/tests/test_379_state_file_session_stamp_offline.py` est le pendant pytest, et
**prouve qu'il mord** : 7 mutations du câblage (estampillage retiré, vérification retirée,
refus qui ne sort plus, dispose inconditionnel, `--from` non confronté, `SESSION` non posé
chez un écrivain tiers) + le cas « fichier introuvable ⇒ on le DIT ».

## 6. Mesures

**Étape 2 live**, jouée sur **deux sessions** (`id=3` puis `id=4`, de part et d'autre d'un
reinject) — build à soi (`runnerId` 207 puis 37), estampille posée ; estampille falsifiée ⇒
`view` / `status` / `dispose` sortent tous en **rc 2** en nommant les deux sessions ; sans
estampille + mtime vieilli ⇒ **rc 2** ; sans estampille + fichier récent ⇒ **rc 0 avec
avertissement** ; restauration ⇒ `dispose` accepté.

**G3 isolé, live** : sur un state-file d'estampille falsifiée, `build` laisse l'ancien runner
**intact** (`battleStatus` avant *et* après : `stage=Running`, `unitsAlive=10`) là où le code
précédent l'aurait disposé — et le build **aboutit** quand même, en ré-estampant (`4` → `17`).

**Flux normal** (session `id=4`) : `build` → `view` → `moves` → `act move` → `status` →
`attach` → `dispose`, aucune friction et **aucune ligne parasite** (`MATCH` est silencieux).
Tests live rejoués : `test_runner_state_live` (3 ✓), `test_runner_move_live` +
`test_heal_operation_live` (3 ✓ 1 xfail préexistant), `test_plague_wind_live` (2 ✓).
`test_damage_catalog_live` échoue sur 4 unités **hors pool au rank 17**
(`admecBossManipulusCE`…) — reproduit à l'identique avec un state-file **inexistant**, donc
sans qu'aucune garde puisse s'appliquer : échec préexistant, étranger à ce correctif.

## 7. Traversée d'une VRAIE fenêtre de reinject (2026-07-31)

Le datapoint qu'on ne peut pas fabriquer. Deux state-files conservés depuis la session
précédente, `runnerId` forcé à **2** (le numéro réellement collisionnable), rejoués tels quels
sur la session suivante :

| | avant | après |
|---|---|---|
| `session.id` | **3** | **4** |
| `session.pid` | 84168 | **84168** — identique |
| `session.startedAt` | `2026-07-31T17:44:22.123Z` | `2026-07-31T19:14:29.908Z` |

| state-file conservé | verdict | `rl_duel status` |
|---|---|---|
| estampillé session 3, `runnerId=2` | `MISMATCH` | **rc 2** — refus nommant les deux sessions |
| sans estampille, `runnerId=2`, mtime `19:08:58Z` | `UNSTAMPED_STALE` | **rc 2** — l'antériorité tranche |

**Le `pid` est le même des deux côtés** (reinject sans relancer le jeu) : il ne tranche pas
ici. Ce sont `id` **et** `startedAt` qui refusent — confirmation directe du §4, une estampille
bâtie sur un seul champ aurait validé.

**Et la collision était réelle, pas hypothétique.** Séquence mesurée après réouverture :

1. `listRunners` juste après le reinject → un seul runner, `runnerId=1` (à un autre acteur) ;
2. `battleStatus({runnerId: 2})` → `runner 2 not found` — l'id n'existe pas *encore* ;
3. mon propre `build` obtient **`4`** : les `2` et `3` ont été consommés entre-temps par des
   agents concurrents ;
4. `listRunners` → `runnerId=2` **est vivant**, `owner =`
   `…/worktrees/agent-a110092b34078c63c/logs/_pytest_duel_state-93388-0.json`.

Le `runnerId=2` de mon state-file d'avant la fenêtre désignait donc, **en moins de dix
minutes**, la bataille d'un pytest d'un autre agent. Sans la garde, `status` l'aurait lue et
`act` l'aurait **mutée** — sans erreur ni refus, et la victime aurait accusé son port. C'est
aussi la mesure du §2 : l'id **2** est passé de « pas encore attribué » à « appartient à
quelqu'un d'autre » en quelques minutes, là où un id haut serait resté inoffensif.

## 8. Ce qui n'est PAS couvert

* **Le `--runner` littéral** des probes ne passe par aucun state-file : rien ne le rattache à
  une session. La garde couvre la voie nominale (`rl_duel`), pas un id tapé à la main.
* **Aucun contrôle d'`owner`** sur les RPC de pilotage (fait distinct, cf. `case-377` §4) : un
  agent qui **vise** l'id d'un runner vivant d'autrui le pilote. Ce n'est pas de la
  réattribution — il faut viser juste, pas se tromper.
* **Les autres écrivains de state-file** (`engine_agreement_stages.py`, `pathfind_validate.py`,
  les probes à `uuid`) délèguent leur build à `rl_duel` et relisent le fichier *juste après* :
  ils héritent de l'estampille, mais ne la reconfrontent pas eux-mêmes. Ils ne survivent pas à
  une fenêtre — ce n'est donc pas le vecteur.
