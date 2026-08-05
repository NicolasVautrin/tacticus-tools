# #480-r6 — `hooks/scratch/` devient `hooks/probes/`, et le code mort se mesure au SYMBOLE

Probes : `scripts/python/probe_480r6_code_mort.py` (3 étages), `probe_480r6_bundle_equivalent.py`
(invariant). Tranche 100 % offline : aucun runner monté, aucun reinject, aucun redémarrage du host.

## Verdict en une ligne

Le compte au FICHIER (**3,8 %** de morts) **réfute** « beaucoup de fichiers morts » — mais il en
**surestimait le nombre de 5 sur 8** *et* n'en voyait pas 3 autres. Le gisement réel est au
**SYMBOLE** : **155 des 321 RPC** du bundle (48 %) n'ont aucun appelant, et **13 exports** ne sont
utilisés nulle part, pas même chez eux. Le répertoire, lui, est renommé : un nom qui déclare du
code jetable le fait écarter des audits, et celui-ci l'a été pendant quatre jours.

---

## 1. La mesure au FICHIER — 8 annoncés, 6 réels, et 5 réfutés

| origine | verdict | témoin |
|---|---|---|
| 3 × `features/normalize-bc/` | **RÉFUTÉ — atteignables** | chemin exhibé, 3 à 4 arêtes |
| 1 × `features/ai-step/`, 1 × `features/ai-trace/` | **RÉFUTÉ — atteignables** | idem, 20/20 modules de ces deux répertoires |
| 2 × `scratch/*.ts` + 3 × `scratch/*.{js,cjs}` | confirmés | hors périmètre `.ts` du scan initial |
| 1 × `frida/tools/` | **RÉHABILITÉ** | §3 |

Un scan qui ne descend pas dans les sous-répertoires manque les imports **relatifs au dossier**
(`from "./formula.js"` depuis `normalize-bc/json-build.ts`). D'où `--chemin` : « atteignable »
n'est plus une opinion, c'est une chaîne d'arêtes qu'on **affiche**. Sans lui, deux comptes qui
divergent se départagent à l'autorité.

Après tranchage : **0 non atteignable** sur 207 fichiers, 882 arêtes.

## 2. Les six morts — supprimés, un par un et pour une raison LUE

| fichier | pourquoi |
|---|---|
| `call-rpc-test.cjs` / `.js` | **deux copies du même script**, différant d'**une ligne** (le nom du RPC appelé). Port en dur ; doublonné par `scripts/python/`. |
| `trigger-inject.cjs` | `POST /api/admin/inject` en un geste, sans garde — **le geste explicitement interdit aux agents**, à portée d'un `node <fichier>`. |
| `run-body.json` | PID en dur (`42656`) + chemin absolu d'une machine. Périmé par construction. |
| `find-d3-index.ts` | corps **vide** (trois commentaires, aucune instruction). L'homonyme **vivant** `findD3Index` est dans `map-ranks.ts`, importé par `controller.ts`. |
| `find-prog-instance.ts` | boucle qui s'arrête sur trois commentaires. Le vivant est `find-prog-instances.ts` (**pluriel**). |

Les deux paires d'homonymes (`find-d3-index` / `map-ranks`, `…instance` / `…instances`) sont le
vrai coût : elles font lire le brouillon en croyant lire le module câblé.

## 3. `frida/tools/probe-279-layout-by-name.ts` — GARDÉ, et le scan corrigé

Non atteignable **par construction** : c'est un harnais lancé par `npx tsx`, qui exécute le code
de PRODUCTION de `hooks/game/damage-prediction.ts` sous mutations adversariales. Re-joué ici :
**`BILAN : OK`**. Le supprimer aurait détruit la seule garde de #279/#372 qui tourne hors du
process de jeu.

**Correction du scan, par critère dérivé, jamais par liste de noms** : un fichier qui **cite son
propre lancement** dans son en-tête (`tsx <son chemin>`) est une ENTRÉE. Il est le seul du dépôt
dans ce cas — le critère ne blanchit aucun mort.

## 4. Le gisement réel — au SYMBOLE

### 4a. Exports : 729 exportés, et le chiffre brut ment

**157** ne sont mentionnés dans aucun autre fichier. Ce nombre n'est **pas** 157 fonctions
mortes, et le ventiler est ce qui le rend exploitable :

- **64 sans poids à l'exécution** — `interface`/`type`, effacés à la transpilation ;
- **144 SUR-EXPORTÉS** — utilisés dans leur propre fichier ; c'est l'`export` qui est superflu,
  pas le code ;
- **13 sans AUCUN usage, nulle part, pas même chez eux** — 8 `function`, 5 `const`. Voilà le
  gisement, un ordre de grandeur sous le chiffre brut.

`disarmCxxThrowTrap`, `pinnedAddressRefusals`, `resolveThunk`, `invokeMethodDirect`,
`projectFromBase`, `aiTraceStoreStatus`, `stopRunnerReconciler`, `cleanupSession`, plus
`DPR_BOXED_SIZE`, `PDE_BOXED_SIZE`, `SMALL_EVENT_BOXED_SIZE`, `BOND_ENTITY_ID_FIELD_NAME`,
`EFFECT_TARGET_IDS_FIELD_NAME`. Non tranchés ici — **`#480-r7`**.

### 4b. RPC : 155 sur 321 sans appelant

Croisé sur **trois langages**, parce qu'un RPC n'est presque jamais appelé depuis TypeScript :
host TS (14 fichiers), front JS (23), Python (1 237 + 679 de tests), doc (633), autre (66).

**Deux comptes rendus, jamais un seul** : le LARGE (le nom entre quotes) ne peut pas conclure
« vivant » ; le STRICT (le nom dans une forme d'appel RPC) ne peut pas conclure « mort » — #480 a
mesuré pourquoi (`commit` matche 137 fois côté Python, tous faux positifs). Un RPC n'est listé que
si les **deux** rendent zéro hors `frida/hooks/`.

⚠ **48 % n'est pas un verdict, c'est un axe de tri** : l'essentiel de ces 155 sont les enveloppes
des sondes, appelées à la main. Leur absence d'appelant est leur **nature**. Tranchage :
**`#480-r8`**.

## 5. L'invariant du déplacement — pourquoi le `sha256` nu ne pouvait PAS tenir

**Mesuré, pas supposé.** Le bundle de référence, reconstruit dans un worktree frais, est
**bit-à-bit identique** à celui de la session injectée (`52E499C3…`) : le build est reproductible.
Mais esbuild **écrit le chemin de chaque module** dans la sortie — **226** chemins, dont **66**
portant `scratch` — et l'en-tête du manifeste porte la taille : `1 149 437 → 1 149 371`, soit
**exactement 66** octets de moins pour 66 modules dont le répertoire perd un caractère.

L'invariant descend donc d'un cran, à **trois niveaux qui se resserrent** :

| | avant → après déplacement |
|---|---|
| **N1** contrat RPC (ce qu'un appelant VOIT) | 321 = 321, 0 perdu, 0 apparu |
| **N2** jeu de modules (noms de base) | 228 = 228 |
| **N3** corps normalisé (instructions, ordre, identifiants esbuild) | `sha256` **IDENTIQUE** |

**Un invariant qui ne peut pas rougir ne vaut rien** : `--casser rpc|module|corps` mute le bundle
et exige le rouge. Les trois mordent, et `--casser corps` ne rougit **que** N3 — c'est ce qui
prouve que les niveaux ne sont pas redondants.

⚠ **Défaut trouvé EN POSANT l'invariant** : le lookbehind excluait le point, donc `ctx.rpc.X`
n'était jamais vu ; N1 rendait `ref=0 neuf=0` et concluait **VERT sur un contrat vide**. Un
plancher accuse désormais le CAPTEUR (`< 50 méthodes ⇒ rouge`) au lieu de verdir. Le compte
corrigé — **321** — coïncide avec celui des sources, mesuré indépendamment.

## 6. Ce que le renommage referme

`loop_status.py` portait `"frida/hooks/scratch/"` dans `UNTRACKED_CONNUS`, décrit « modules de
travail hors bundle » — **doublement faux** depuis #365 (versionné ; 66 modules dans le bundle).
L'entrée écartait donc silencieusement du rapport « arbre sale » exactement ce que la doctrine
demande de surveiller. **Retirée** : retirer une exclusion rend le rapport plus bavard, jamais
moins.

Et la mine du `.gitignore` se dissout : la règle générique `/scratch/` ne peut plus atteindre du
code livré, puisque **plus aucun répertoire de production ne s'appelle `scratch`**.

Effet mesuré sur **#480-r5** : erreurs `tsc` **146 → 143** (139 dans `probes/`) — la suppression
du code mort réduit la dette sans qu'on ait rien corrigé.

## 7. Ce qui n'est PAS couvert

- **Aucune confrontation live.** Le bundle produit ici n'est pas chargé dans la session ; il est
  prouvé ÉQUIVALENT à celui qui l'est. Une fenêtre de reinject reste requise pour l'activer.
- **Les scans ne voient pas** : `require()`/`import()` à chaîne calculée (**0** rencontré), la
  réflexion (`obj[nom]`), un RPC invoqué à la main (curl, console), et ce que la **session expose
  réellement** — résidu **`#480-r3`**, toujours ouvert.
- **`master` est ROUGE et ce n'est pas moi** : `test_enum_ordinal_ratchet_offline.py` échoue à
  l'identique sur `origin/master` (`StepType.None_ = 0`, le build `rnca9r7q6c` dit MEMBRE ABSENT).
  Vérifié par extraction d'un arbre témoin.
- **`scripts/ratchets-457-footprints.json` porte le chemin mort** `frida/hooks/scratch`. Non
  régénéré : `--measure` est un rejeu complet (977 s, « maintenance, pas une étape de PR »), et
  l'empreinte s'annonce **déjà inverifiable sur `master`** (`_commit 57bb2a7c` inconnu de git) —
  elle dégrade proprement en rejouant tout. À reprendre à la prochaine maintenance #457.
- **`frida/tools/` n'est couvert par AUCUN `tsconfig`** (`include` = `hooks/**` et `host/**`) :
  le harnais #279 n'est jamais typechecké. **`#480-r9`**.
- **`dump-stat-comp-types.ts`** reste un **import mort** de `controller.ts` (symbole jamais
  appelé ⇒ tree-shaké). Déjà mesuré par #480-r1 ; déplacé tel quel, comportement inchangé.
- ⚠ **`find-prog-instances.ts` fait un heap scan** (`Process.enumerateRanges` + `Memory.scanSync`).
  Conforme *parce que* l'appel est on-demand ; signalé, pas corrigé (hors périmètre).

## Résidus

- **`#480-r7`** — **13 exports sans aucun usage** (8 `function`, 5 `const`), listés au §4a.
  Trancher un par un : retrait, ou raison écrite de les garder. *Retournement* : l'étage 2 de
  `probe_480r6_code_mort.py` rend `[B] = 0`, ou chaque survivant porte sa justification.
- **`#480-r8`** — **155 RPC sans appelant sur 321**. Axe de tri, pas verdict : séparer les
  enveloppes de sondes (absence d'appelant = nature) du vrai mort. `sim.ts` (3 RPC) est déjà
  nommé par #480 R6. *Retournement* : chaque RPC listé est soit appelé, soit retiré, soit
  justifié.
- **`#480-r9`** — **`frida/tools/` hors de tout `tsconfig`**. Le harnais qui garde #279/#372
  n'est jamais typechecké ; une erreur de type ne s'y verrait qu'à l'exécution.
  *Retournement* : `tsc` couvre `tools/**` et rend un compte assumé.
