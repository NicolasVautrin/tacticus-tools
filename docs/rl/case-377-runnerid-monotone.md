# case-377 — un `runnerId` est-il RÉATTRIBUABLE après `disposeRunner` ?

**Critère (binaire)** : après `disposeRunner`, l'id peut-il revenir à un runner créé ensuite —
et donc un agent qui pilote un id périmé peut-il polluer le runner d'un **autre** agent, sans
erreur ni refus ?

**Réponse : NON. Le compteur est STRICTEMENT MONOTONE par session Frida, et rien n'est recyclé.**
L'incident qui a ouvert le cas — quatre `endturn`/`aiturn` passés sur `--runner 261` *après* l'avoir
disposé — est donc **BÉNIN** : ces quatre tours n'ont touché aucun runner. Ils ont été **refusés**,
un par un, par `runner 261 not found`.

Ce résultat se lit dans le **code d'allocation**, pas dans une observation : deux builds consécutifs
ne disent rien du recyclage *après* dispose. Re-dérivation :
`python scripts/python/probe_377_runnerid_reuse.py` (ajouter `--live` pour la confirmation).

---

## 1. Les quatre lignes qui tranchent

`frida/hooks/game/runner-registry.ts` — **seul** producteur d'id du dépôt :

```ts
const byId = new Map<number, Entry>();   // NON exporté
let counter = 0;
...  { ...h, runnerId: ++counter, ... }; byId.set(e.runnerId, e);
...  return byId.delete(runnerId);       // dispose : retrait SEC
```

`disposeRunner` dépingle, purge les traces, puis **supprime**. Il ne décrémente pas `counter`, ne
range l'id dans aucune free-list, n'expose aucun pool. Les trois appelants de `registerRunner`
(`initRunner` et `initAndStart` dans `frida/hooks/features/launch.ts`, `buildPatchedRunner` dans
`frida/hooks/features/battle-config.ts`) passent tous par ce même `++counter`.

⇒ **un id disposé reste libre pour toujours** dans la session. « Combien de temps » n'a pas de
réponse en secondes : la question ne se pose pas.

## 2. Le refus est FRANC, et c'est un passage obligé

Tout RPC qui accepte un `runnerId` le résout par `getRunner`, qui **lève** `runner <id> not found` ;
les RPC le rendent en `{ ok: false, error: … }`. Balayage de `frida/hooks/**` : **31 sites** de
garde `typeof body?.runnerId === "number"`, **31** suivis de `getRunner(body.runnerId)`, sans
exception. Les deux fichiers qui lisent un `runnerId` sans `getRunner` — `ai-utility-trace.ts`
(`aiUtilityTraceClear`) et `bucket-audit.ts` (`bucketAuditReset`) — vident un **bucket de traces
diagnostiques** indexé par id ; ils ne pilotent aucune bataille.

Côté outil, la voie nominale est déjà correcte : hors `attach`, **aucune** commande de `rl_duel.py`
n'accepte de `--runner` littéral — toutes relisent `runnerId` depuis leur `--state-file`
(`_load_state`). Le `--runner` littéral existe surtout dans les **probes**.

## 3. Confirmation live (2026-07-31, session Frida `id=3`)

Trois runners **à moi**, dispose du premier, quatrième mesure sur l'id mort :

| étape | mesure |
|---|---|
| build A, build B | `145`, `146` |
| `disposeRunner(145)` | ok |
| build C, **après** la dispose | **`147`** — ni `145` ni un trou repris |
| `battleStatus({runnerId: 145})` | `{ok:false, error:"runner 145 not found"}` — l'id est **nommé** |
| `battleStatus({runnerId: 147})` depuis un autre contexte | **accepté** — cf. §4 |

## 4. Ce qui n'est PAS fermé, et pourquoi ce n'est pas ce cas

* **Cross-drive VOLONTAIRE** : aucun contrôle d'`owner` sur les RPC de pilotage. L'`owner` est bien
  enregistré (`rl_duel build` passe `owner = <state-file absolu>`, `registerRunner` le stocke,
  `listRunners` le rend) mais il ne sert qu'à la purge sûre des orphelins
  (`reference_orphan_runner_detection`). Un agent qui **tape** l'id d'un runner vivant qui n'est pas
  le sien le pilote. Ce n'est pas de la réattribution : il faut viser juste, pas se tromper.
* **La monotonie vaut PAR SESSION Frida.** `counter` est un état de module du bundle injecté : une
  (ré)injection le remet à `0`. Au même instant `byId` est vide — tous les runners meurent, donc
  aucune victime. Le seul chemin résiduel de collision est **inter-session** : un `--runner` (ou un
  `--state-file`) d'avant un reinject, réutilisé après, une fois que la nouvelle session a dépassé
  ce numéro. Ce n'est pas hors d'atteinte : `case-321` a mesuré une session montée à **332** ids,
  au-delà du `261` de l'incident. Un reinject casse déjà tout le harnais en vol (c'est pourquoi
  c'est un geste orchestrateur planifié), mais un **state-file survit sur disque**, lui.
  → résidu nommé, correctif **Python pur** (donc actif sans reinject) : estamper le state-file avec
  le `sessionId` au `build`, et **refuser franchement** toute commande dont la session courante
  diffère — tri-état obligatoire (`sessionId` absent = state-file d'avant la garde ⇒ avertir, ne pas
  refuser, sinon on casse les agents en vol). Sites : `_save_state` / `_load_state` / `cmd_attach`
  de `scripts/python/rl_duel.py`.

## 5. Le cliquet

La monotonie n'est **pas déclarée** : elle émerge de cinq détails, chacun perdable en une ligne.
`probe_377_runnerid_reuse.py` étape 0 (statique, aucune session) les tient — `byId` const non
exporté (I1), un seul `byId.set(` (I2), `counter` jamais réaffecté ni décrémenté (I3), un seul
`++counter` et c'est lui qui alimente `runnerId` (I4), aucun identifiant de recyclage (I5).

`scripts/python/tests/test_377_runnerid_monotone_offline.py` est son pendant pytest, et **prouve
qu'il mord** : six mutations du registre (free-list dans `disposeRunner`, remise à zéro du compteur,
décrément, id fourni par l'appelant, map exportée, second point d'insertion) le font rougir, plus le
cas « registre introuvable ⇒ on le DIT ». Un cliquet dont on n'a jamais vu le rouge ne garantit rien.

La régression qu'il rend visible : quelqu'un ajoute `freeIds.push(runnerId)` dans `disposeRunner`
« pour ne pas gonfler les ids », et rouvre le mode d'échec le plus coûteux du harnais — la victime
ne voit ni erreur ni refus, seulement un état de bataille qui a avancé tout seul, et elle accusera
**son port**.
