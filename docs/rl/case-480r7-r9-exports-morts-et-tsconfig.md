# #480-r7 / #480-r9 — un export mort se tranche par sa CAUSE, et un tsconfig par un critère dérivé

Probes : `probe_480r9_tsconfig_couverture.py` (cliquet, 3 étages + 2 contre-épreuves),
`probe_480r7_name_resolution.py` (lecteur des capteurs câblés). Tranche 100 % offline :
aucun runner monté, aucun reinject, aucun redémarrage du host.

## Verdict en une ligne

**Un seul** `.ts` versionné échappait au typecheck, et il n'y ajoute **0 erreur**. Les
**13** exports sans usage n'étaient pas 13 fois le même cas : **6 mentent** (retirés),
**6 sont des capteurs dont le câblage manquait** (câblés), **1 est l'interface d'un bloc
gardé pour référence** (dé-exporté). Et le recenseur lui-même comptait les commentaires
comme des usages — corrigé, il en trouve **2 de plus**.

---

## 1. `#480-r9` — la mesure tient en une soustraction

| | |
|---|---|
| `.ts` versionnés sous `frida/` | **207** |
| couverts par l'union des `tsc --listFilesOnly` | **206** |
| **orphelin** | **1** — `frida/tools/probe-279-layout-by-name.ts` |

`tsconfig.tools.json` le couvre : **4** fichiers tirés (le harnais + les 3 modules `hooks`
que son `import()` amène), **0 erreur**. `npm run typecheck:tools`. Aucun build n'est
touché : `frida-compile` ne lit aucun de ces `tsconfig` (il n'existe pas de `tsconfig.json`
à la racine de `frida/`), et `build:host` garde le sien.

**Le piège est dans la dérivation, pas dans le compte.** `tsconfig.base.json` ne porte
aucun `include` : lancé seul, `tsc` y prend le répertoire ENTIER, et l'invariant serait
**trivialement vrai** — un orphelin de tout projet réel serait déclaré couvert par la base
que personne ne compile. Le tri PROJET/BASE est dérivé des `extends`, et l'étape 3 du
cliquet **rougit s'il ne reconnaît aucune base**.

## 2. `#480-r5` — les 143 erreurs sont UN défaut, pas 143 bugs

Re-mesuré : **TS2584** (`console`) × 140, **TS2591** (`require`) × 3, **rien d'autre**.
`lib: ["ES2020"]` sans `dom`, et `@types/frida-gum` ne déclare pas `console` (0 occurrence
dans son `index.d.ts`) alors que le runtime Frida le fournit. Non tranché ici — mais
**borné** : l'invariant du cliquet porte sur la **nature**, pas sur le nombre. Un seuil
(`<= 143`) cesserait de mordre dès qu'un fichier sortirait du périmètre.

## 3. `#480-r7` — les 13, tranchés par leur CAUSE

**RETIRÉS — le symbole ment, ou double un chemin vivant** :

| export | pourquoi |
|---|---|
| `resolveThunk` | rendait son argument **inchangé**. Le décodeur de sa docstring visait ARM64 ; sur x86-64 c'est l'identité sous un nom qui promet une résolution. |
| `invokeMethodDirect` | lisait `methodInfo.readPointer()`, que `methodEntry` du **même paquet** déclare UNSAFE (l'ordre des champs de `MethodInfo` varie selon la version IL2CPP). |
| `projectFromBase` + `continueInline` | 109 lignes ; variante de `projectPaths` pour base inline, couverte par `projectPaths` + `stepInto`. Retrait **en cascade** : garder l'appelée aurait converti un mort EXPORTÉ (mesurable) en mort PRIVÉ (invisible). |
| `DPR_BOXED_SIZE`, `PDE_BOXED_SIZE`, `SMALL_EVENT_BOXED_SIZE` | dérivés triviaux (stride + `0x10`) sans lecteur, plus les 3 champs de `PredictionLayout` qui n'existaient que pour eux. |

**CÂBLÉS — le symbole est un capteur, c'est son câblage qui manquait** :

| export | où |
|---|---|
| `pinnedAddressRefusals`, `EFFECT_TARGET_IDS_FIELD_NAME`, `BOND_ENTITY_ID_FIELD_NAME` | RPC **`nameResolutionStatus`** (`hooks/features/status.ts`) |
| `cleanupSession` | `stopSession`. Sans lui le ring WS (`RING_SIZE` = 10 000 événements) et le Set d'abonnés restaient en mémoire pour **chaque** session stoppée, sur toute la vie du host. Rien d'observable perdu : le front ne se réabonne qu'à `status === "running"`. |
| `stopRunnerReconciler` | shutdown gracieux, **avant** `stopAllPreservingState` — sinon le réconciliateur mesure un registre en train de disparaître. |
| `aiTraceStoreStatus` | `GET /api/ai-trace/status`, champ `store`. Ferme le volet (c) de **#273-r** : personne ne pouvait DEMANDER au host où il écrit, on l'INFÉRAIT. |

Les trois premiers portaient tous, en toutes lettres, « exporté pour qu'une MAJ se VOIE ».
Aucun n'avait de lecteur : **un garde-fou qu'on croit armé et qui ne peut pas signaler**.

**DÉ-EXPORTÉ** : `armCxxThrowTrap` / `disarmCxxThrowTrap`. Le hook qui lit leur flag
(`installRaiseExceptionHook`) est explicitement conservé pour référence et **non câblé** —
c'est l'`export` qui mentait. Aucun RPC ne doit les exposer : armer un flag que personne ne
lit ferait croire le piège actif.

## 4. Le recenseur comptait les COMMENTAIRES comme des usages

« Utilisé chez lui » se testait sur le fichier ENTIER. **`DPR_SIZE`** (cité par le
commentaire de la constante voisine) et **`predictionLayoutDrift`** (deux « Cf. … ») étaient
donc rangés en `[A] SUR-EXPORTÉ` — **morts, et hors du tranchage**. Le second est le capteur
de dérive de #279 : il rejoint `nameResolutionStatus`.

Le nettoyeur est un **scanner à états**, après **trois** versions prises en défaut par la
mesure — et c'est l'ordre qui compte, chacune corrigeant la précédente :

1. effacer les template literals accusait `DRAIN_MARKER`, dont l'unique usage local est
   `${DRAIN_MARKER}` — une interpolation **est** du code ;
2. un `//` **dans une chaîne** mangeait la backquote fermante ; l'appariement suivant
   emportait des centaines de lignes — `readHealEvent`, `decodeEventsGeneric`, bien
   appelées, classées mortes ;
3. les littéraux **regex** sont un état à part : `config-store.ts` porte six guillemets
   dans un `/…/` et le scanner y perdait **91 %** du fichier.

**Le garde qui a trouvé (3) est un garde de PERTE** : un fichier dont le nettoyage retire
plus de 85 % accuse le NETTOYEUR, pas le fichier. Il a rougi avant toute conclusion, sur le
fichier exact d'où venaient les deux faux morts.

Après correction : exports **729 → 720**, `[A]` **144 → 140**, `[B]` **13 → 0**.

## 5. N2 du comparateur de bundles jugeait la MULTIPLICITÉ

Ajouter un `import` à un module déjà embarqué **réordonne** le graphe et déplace des modules
entre inline (1 frontière) et `__esm` (2 frontières) : **228 → 227** occurrences pour
**186 modules DISTINCTS identiques**, 0 disparu, 0 apparu. Le verdict porte désormais sur
l'**ensemble** ; la multiplicité reste imprimée en NOTE. `--casser module` rougit toujours.

## 6. Ce qui n'est PAS couvert

- **Aucune confrontation live.** Le RPC `nameResolutionStatus` et le champ `store` sont dans
  l'arbre, **pas dans les processus** : le premier exige une **ré-injection**, le second un
  **redémarrage du host** — deux gestes orchestrateur. `probe_480r7_name_resolution.py` rend
  aujourd'hui `NON MESURE` sur ses deux volets, chacun nommant sa cause.
- **`#480-r3` est nuancé, pas fermé** : mesuré sur la session 10, un `HTTP 500` ne dit rien
  **par son code**, mais son **corps** discrimine — Frida rend littéralement
  `unable to find method '<nom>'` quand `rpc.exports` ne porte pas la clé. Rien n'ÉNUMÈRE
  toujours ce que la session expose.
- **Les 143 erreurs `tsc`** restent (#480-r5), bornées par nature, pas corrigées.
- Le scanner de `code_seul` ne tokenise pas TypeScript : une regex littérale contenant un
  `/*`, ou un `/` de division précédé d'un opérateur, l'induiraient en erreur. Le garde de
  perte est ce qui le dirait.
