# case-321 — `/api/runners` = 306, `listRunners` = 0 : qui compte, qui gate ?

**Critère** : que publie exactement `GET /api/runners` — des runners **vivants** ou un historique —
et quel compteur gate **réellement** la création d'un runner ?

**Réponse — c'est (b), et (b) n'est pas une alerte capacité.** Les deux propositions sont vraies
simultanément et les confondre est ce qui a produit la fausse alerte :

1. `GET /api/runners` publie un **cache host de runners VIVANTS** (pas un journal d'audit), et il
   **fuyait** : la création s'y inférait toute seule, la mort n'y était câblée nulle part sur le
   chemin qu'empruntent tous les agents. → fuite de comptabilité réelle, corrigée ici.
2. Ce compteur **ne gate rien**. `MAX_RUNNERS` vit et s'applique **côté hooks**. Le chiffre 306
   n'entrait dans aucune décision — d'où le fait, correctement relevé, que **les builds passaient**.

Re-dérivation : `python scripts/python/probe_321_runner_registry_drift.py`

---

## 1. La ligne de code qui tranche

Le plafond est déclaré dans `frida/hooks/game/runner-registry.ts` :

```ts
export const MAX_RUNNERS = 50;
```

et il n'est comparé qu'à `listRunners()` **du même module** (la map `byId` des hooks), aux **deux
seuls** points de création :

| fichier | ligne effective |
|---|---|
| `frida/hooks/features/launch.ts` (`initAndStart`) | `const active = listRunners(); if (active.length >= MAX_RUNNERS) throw ...` |
| `frida/hooks/features/battle-config.ts` (`buildPatchedRunner`) | `const active = listRegistryRunners(); if (active.length >= MAX_RUNNERS) return { ok:false, err:"runner cap reached ..." }` |

`listRegistryRunners` est l'import aliasé de ce même `runner-registry.ts`. **Aucun** de ces deux
`active` ne vient du host. Le gate est donc **entièrement côté hooks**, dans le process du jeu.

Côté host, `GET /api/runners` rend `listRunners()` de `frida/host/battle-store.ts` — une `Map`
alimentée pour l'affichage. Le host **ne refuse jamais** une création pour cause de nombre.

Le dépôt le savait déjà à un endroit, et c'est la seule raison pour laquelle la jauge de drain est
juste — `frida/host/router.ts`, `GET /api/admin/drain` : « ELLE LIT LE REGISTRE DES HOOKS, PAS CELUI
DU HOST […] le registre host est un cache, il dérive ». Ce que #321 ajoute, c'est de le dire **là où
on lit le chiffre** (l'endpoint lui-même), et de **supprimer la dérive** au lieu de seulement la
signaler.

## 2. La mesure, et ce qui la rend concluante

`2026-07-31`, dans le même instant, session Frida `id=3` :

| source | valeur |
|---|---|
| `GET /api/runners` (cache host) | **318** puis **332** quelques minutes plus tard |
| RPC `listRunners` (registre hooks, **autorité**) | **0** puis **2** |

Le chiffre brut ne prouve rien tout seul. Ce sont les **trois invariants du contenu** qui tranchent :

* `configId` absent sur **332 / 332** → aucune entrée n'est venue de `registerRunner()`
  (`/api/launch`, `/api/mirror/*`) ; **toutes** viennent de l'auto-inférence `battle_event` ;
* `runnerId` = **1..332, zéro trou** → aucune entrée n'a **jamais** été retirée depuis le début de
  la session. Un registre qui purge laisse des trous ; celui-ci n'en a aucun ;
* `sessionId` = `3` pour toutes → `pruneRunnersBySession` n'a jamais eu l'occasion de tirer (la
  session n'est pas morte).

Coût mesuré, au cas où la fuite serait relue comme cosmétique : **320 répertoires / 1 147 fichiers /
455 Mo** de dumps `matchState` sous `frida/logs/runs/`, que `removeRunner` aurait effacés au fil de
l'eau (il fait `fs.rm(logs/runs/<id>, {recursive:true})`).

## 3. Cause : une comptabilité asymétrique

| événement | le host l'apprend-il ? | par quoi |
|---|---|---|
| **création** (n'importe quelle voie) | **oui, toujours** | premier `battle_event` d'un `runnerId` inconnu → `runners.set(...)` (`battle-store.ts`) |
| dispose par le front | oui | `DELETE /api/runners/:id` |
| réconciliation manuelle | oui | `POST /api/runners/sync` (rechargement dur du front) |
| mort de la session Frida | oui | `pruneRunnersBySession` (`sessions.ts`) |
| auto-dispose fin de match | oui, **mais** | `send({t:"runner_disposed"})` de `recorder.ts` — **uniquement** pour `autoDispose !== false`, donc **jamais** pour les runners RL/isolés (`initAndStart`, `buildPatchedRunner`, qui posent explicitement `autoDispose: false` pour TF06) |
| **dispose par RPC `disposeRunner`** — le chemin de **tous** les agents | **NON** | rien. `POST /api/scripts/:id/rpc` est un passe-plat : il appelle `rpcCall` et rend `{result}` sans relire ni la méthode ni les arguments |

`ctx.rpc.disposeRunner` (`frida/hooks/features/launch.ts`) supprime bien l'entrée hooks-side et rend
`{removed}` — mais **n'émet aucun `send`**. Le host n'avait donc littéralement aucun canal pour
apprendre la mort d'un runner d'agent.

## 4. Le correctif

**Racine — la symétrie, posée au point de passage unique.** `rpcCall` (`frida/host/sessions.ts`)
relit la méthode qui vient de réussir : sur `disposeRunner`, il purge l'entrée host
(`noteRunnerDeath`). C'est **exactement l'argument déjà écrit dans `drain.ts`** pour
`assertCreationAllowed` : la porte est dans `rpcCall` et non dans la route HTTP parce que
`/api/launch` et la route de replay sim appellent `rpcCall` en interne — durcir le point de passage,
pas les 250 appelants. Le retrait a lieu que la RPC ait rendu `{removed:true}` ou `{removed:false}` :
un `false` signifie que les hooks n'avaient **déjà** plus ce runner, donc l'entrée host est stale à
plus forte raison.

**Filet — convergence périodique vers l'autorité.** `frida/host/runner-reconcile.ts` interroge la RPC
`listRunners` toutes les 60 s et purge ce que l'autorité ne connaît plus. Il ne remplace pas le
correctif racine : il couvre les chemins de mort **qui n'existent pas encore**. C'est la fragilité
que `drain.ts` documente pour sa liste noire (« si une méthode apparaît un jour sans être ajoutée
ici, le drain FUIT ») — une liste de chemins de mort tenue à la main ré-ouvrirait la même dérive
silencieuse ; une convergence vers l'autorité, non.

Deux disciplines y sont explicites :

* **tri-état** (`host_inputs.py` #273, jauge de drain #285) : pas de session vivante, RPC en échec ou
  réponse inattendue ⇒ **aucune purge**. « Je n'ai pas pu compter » n'est jamais « il n'y a rien ».
  C'est ce qui distingue le filet automatique de `POST /api/runners/sync`, qui purge tout en
  l'absence de session — correct pour un geste **manuel** de l'utilisateur, faux pour un timer qui
  pourrait tomber pendant une fenêtre de ré-attache ;
* **fermeture de course** : `pruneRunners(keep, createdBefore)` ne purge que les entrées
  enregistrées **avant** la photo du registre hooks. Sans cette borne, un runner créé par un autre
  agent pendant l'aller-retour RPC — absent de la photo parce qu'il n'existait pas encore — serait
  purgé et ses dumps effacés sous ses pieds. La même borne est passée par `/api/runners/sync`.

**Lever l'ambiguïté est un livrable, pas un lot de consolation.** L'en-tête de `battle-store.ts` et
le bloc de `GET /api/runners` nomment désormais : ce que la map **est** (cache de présentation), ce
qu'elle **n'est pas** (historique, jauge de capacité), **où** vit le gate (fichier + symbole + les
deux call-sites), et **par quoi** compter des runners vivants (RPC `listRunners`, ou
`GET /api/admin/drain` champ `liveRunners` avec son tri-état).

Effet de bord corrigé au passage : `DELETE /api/runners/:id` lit `hasRunner(id)` **avant** la RPC.
Sans ça, la purge amont de `rpcCall` ferait rendre `removed:false` sur le chemin nominal — la route
mentirait. Et le commentaire de `POST /api/runners/sync`, coupé en deux par des insertions
successives (sa première moitié s'était retrouvée collée au bloc `/api/rpc-queue`), est recollé.

## 5. Le conftest de `tests/engine/runner/` — l'accusation est FAUSSE

Vérifié fichier par fichier. `scripts/python/tests/engine/runner/conftest.py` ne construit **aucun**
runner lui-même : chaque fixture est la porte pytest d'un probe, et **tout probe qui construit
dispose dans un `finally`** :

| probe | dispose |
|---|---|
| `probe_psychic_aoe.py` | `finally: live.rpc("disposeRunner", ...)` |
| `probe_178_overkill_gate.py` | 3 `finally` → 3 `disposeRunner` |
| `probe_r34_overkill_decision.py` | 5 `finally` → 5 `disposeRunner` |
| `probe_195_prevent_overkill_decision.py` | 3 `finally` → 3 `disposeRunner` |
| `probe_o5_unit_flags.py` | 2 `finally` → 2 `disposeRunner` |
| `probe_294` / `probe_301` / `probe_306` | ne construisent **rien** (offline assumé, pas de `live_session`) |

Le conftest **racine** (`scripts/python/tests/conftest.py`) dispose lui aussi, au fil de l'eau, par
propriétaire réel (`_release_runners`, `_DISPOSER` → RPC `disposeRunner`).

**Et ça ne comptait de toute façon pas** : ces disposes vont au registre **hooks**, le seul qui gate.
La signature d'une vraie fuite de runner est connue et documentée — `probe_308_normal_attack_bonus.py`
en porte la mesure du 2026-07-30 : « chaque itération FUIT un runner […] cap `MAX_RUNNERS` (50)
saturé en une seule passe, 49 orphelins à purger ». Le cap **mord** quand quelque chose fuit
vraiment. Ici il n'a pas mordu, et pour cause : hooks-side, le compte était **0**.

## 6. Ce qui reste NON VÉRIFIÉ EN VOL

Le correctif est **entièrement dans `frida/host/*`**, donc **inactif tant que le host n'a pas
redémarré** (`npm run dev` exécute les sources TS via `tsx` ; il n'y a pas de hot-reload, et il est
proscrit). Le redémarrage n'a **pas** été fait : plusieurs agents partagent la session Frida vivante.

Ce qui **est** vérifié sans redémarrage :

* `tsc -p tsconfig.host.json --noEmit` → **exit 0** ;
* la sonde `probe_321_runner_registry_drift.py` tourne et rend le diagnostic complet
  (gate relu dans les sources, deux compteurs, dérive, invariants de contenu) ;
* aucun consommateur de `GET /api/runners` hors du front (`frida/public/src/api.js` →
  `refreshRunners`), qui ne lit que la forme tableau — inchangée.

Ce qui **exige la fenêtre de restart** :

1. la purge à la dispose ferme bien la dérive ;
2. le réconciliateur converge et ne purge jamais sur mesure absente ;
3. `DELETE /api/runners/:id` rapporte toujours `removed:true` sur un runner connu.

**Procédure de vérification, après restart du host** :

```
python scripts/python/probe_321_runner_registry_drift.py --sync
   # -> attendu : derive ~0. Le --sync rattrape en une fois les ~330 entrees
   #    heritees d'avant le correctif (elles ne disparaissent pas toutes seules :
   #    le reconciliateur les purgera aussi, en <= 60 s).

# puis, cycle nominal :
python scripts/python/rl_duel.py build --seed 777 --board MC1_67 --state-file logs/_st321.json
python scripts/python/probe_321_runner_registry_drift.py     # host = hooks + 0
python scripts/python/rl_duel.py dispose --state-file logs/_st321.json
python scripts/python/probe_321_runner_registry_drift.py --max-drift 0   # exit 0 attendu
```

`--max-drift 0` est le **cliquet** : après la fenêtre, il doit rendre 0 et le rester.

## 7. Hors périmètre, signalé et non touché

`RUNS_DIR` vaut `path.resolve(process.cwd(), "logs", "runs")` et `process.cwd()` est `frida/` →
les dumps atterrissent dans **`frida/logs/runs/`**, alors que l'en-tête de `frida/host/index.ts`
énonce la règle inverse (« Les SORTIES du host vont sous `logs/` A LA RACINE DU DEPOT, pas sous
`frida/` », écrite après une mesure de 3 663 Mo accumulés au même endroit). Corriger le chemin
**orphelinerait** les 455 Mo existants (plus aucun `removeRunner` ne les atteindrait). À traiter
comme une tâche à part, avec sa migration.
