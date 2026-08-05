# #480-r1 / #480-r4 — `frida/hooks/scratch/` est du code de production, et le build ne savait pas écrire

**Deux résidus, une seule classe de faute — mais deux causes distinctes, et c'est le résultat.**
Probe : `scripts/python/probe_480r1_entrees_de_build.py`. Tranche offline : aucun runner, aucun RPC,
aucune session Frida touchée.

## Verdict en une ligne

`frida/hooks/scratch/` n'est pas un brouillon : **73 fichiers versionnés, 66 dans le bundle
injecté** — et six endroits le décrivaient encore comme gitignoré ou jetable. Séparément,
`npm run build:hooks` échouait sur un checkout frais **pour une raison sans rapport** : le
répertoire de **sortie** n'existe pas. `probe_365` gardait les ENTRÉES du build ; personne ne
gardait sa SORTIE.

---

## 1. Ce qu'est réellement `frida/hooks/scratch/` — mesuré, pas déduit

| mesure | valeur | témoin |
|---|---:|---|
| fichiers sur disque (worktree frais) | **73** | — |
| fichiers SUIVIS par git | **73** | `git ls-files` |
| dont `.ts` | 69 | 2 `.cjs`, 1 `.js`, 1 `.json` |
| atteignables depuis `hooks/main.ts` | **67** | fermeture : 192 fichiers, 849 arêtes |
| **présents dans `dist/hooks.js`** | **66** | 226 marqueurs de module, bundle 1 145 561 o |
| non atteignables (vrais one-shots) | **6** | `call-rpc-test.{cjs,js}`, `find-d3-index.ts`, `find-prog-instance.ts`, `run-body.json`, `trigger-inject.cjs` |

**L'écart 67 → 66 est expliqué, pas arrondi** : `dump-stat-comp-types.ts` est importé par
`controller.ts:143`, mais son symbole `dumpStatComponentFieldTypes` n'est **appelé nulle part**
(235 fichiers `.ts`/`.js`/`.cjs` balayés hors `node_modules`/`dist`, 2 occurrences : la définition
et l'import). esbuild tree-shake donc le module entier. C'est un **import mort** — la classe de
faute que `#462-r4c-r3` a déjà nommée, ici sous sa forme « symbole importé jamais appelé ».

Les imports **dynamiques** ne changent rien : fermeture statique et fermeture statique+dynamique
rendent le même ensemble (192 fichiers dans les deux cas).

⇒ **`hooks/scratch/` engage la stabilité de la session injectée.** Ses 142 erreurs `tsc`
(re-mesuré : 146 au total, 142 `scratch` + 3 `normalize-bc/debug-rpcs.ts` + 1 `rl/tensorizer.ts`)
portent sur du code livré, pas sur des brouillons posés à côté du build.

## 2. L'incident du 2026-07-31 : rien n'était récupérable depuis git

Question posée en mesure, pas en raisonnement.

- `git ls-tree -r` sur le parent de `774df416` : **0** entrée sous `frida/hooks/scratch`
  (**témoin : 2 733** entrées dans cet arbre). Le répertoire n'a jamais existé dans git avant
  d'y entrer, le jour même de sa destruction.
- `git log --all --diff-filter=D -- frida/hooks/scratch` : **0** ligne
  (**témoin : 3 176** commits balayés). Jamais supprimé de git non plus — il n'y était pas.
- L'historique du chemin tient en **2 commits**, tous deux du 2026-07-31 : `774df416` (15:18,
  **72** fichiers) puis `81e1a66e` (15:34, **1** fichier).

**« Aucune copie ailleurs » est réfuté sur un point**, et c'est ce point qui a sauvé le build :
`dsl-node-probe.ts` a été **reconstruit depuis `frida/dist/hooks.js`**, le bundle compilé avant la
perte (cf. message de `81e1a66e`). Un module bundlé possède donc une copie *transpilée* — commentaires
et types perdus, structure préservée. Ce n'est pas une sauvegarde, c'est un reste exploitable.

⇒ La description historique était **exacte au moment de l'incident**. Ce qui est faux, c'est de la
lire au présent — et rien, dans le `CLAUDE.md`, ne disait qu'elle avait cessé de l'être.

## 3. Les six mentions fausses — recensées par critère, corrigées à l'état final

| fichier | ligne | ce qu'elle disait |
|---|---:|---|
| `CLAUDE.md` | 699 | « 67 modules, gitignorés, jamais versionnés, aucune copie ailleurs » |
| `.claude/skills/tacticus/references/hooks.md` | 78 | « modules jetables […] **jamais une dépendance de prod** » |
| `.claude/skills/tacticus/references/rpc-api.md` | 204 | « **jamais une dépendance d'un hook live** » |
| `docs/rl/case-477-harnais-de-test-natif.md` | 375, 538 | « 142 dans `hooks/scratch/`, gitignoré » |
| `docs/rl/case-477r11-format-du-flux-de-replay.md` | 249 | « dans `hooks/scratch/` gitignoré » |
| `scripts/python/probe_365_versioned_imports_gitignored.py` | 6 | « `.gitignore` exclut » (au présent) |

Dans les six cas, la propriété correcte est la même : **`frida/hooks/scratch/` est versionné, et
66 de ses modules sont bundlés**.

⚠ **Ce tableau a fait rougir le cliquet — et c'est le comportement voulu.** Une ligne qui *cite*
une qualification fausse est, caractère pour caractère, indiscernable d'une ligne qui la *commet* :
aucun critère textuel ne peut les séparer sans devenir devinatoire. C'est précisément pourquoi le
mécanisme de réhabilitation existe, et la phrase ci-dessus est ce qu'il attend — une affirmation
proche qui **nomme** le répertoire. Le recensement reste lisible, et un futur rédacteur qui recopie
ce tableau ailleurs sans l'accompagner de sa correction sera rattrapé.

**Deux mentions qu'il ne faut PAS corriger**, et le cliquet les laisse passer :
`tacticus-orchestration/SKILL.md:709` raconte l'incident *puis* écrit (L716) que le répertoire est
versionné depuis ; `.gitignore:64-77` porte le correctif lui-même. Le récit d'un état passé est
légitime **quand le même endroit dit l'état présent**.

⚠ **`case-480` §R5 demandait aussi de corriger `case-475` §7 : cette mention n'existe pas.**
Mesuré : **0** occurrence de « scratch » dans `case-475-adresses-epinglees.md` (témoin : 117 lignes).
La référence était elle-même inexacte.

**Portée de ce recensement** : `git ls-files "*.md" "scripts/python/*.py"` — 2 537 documents,
746 923 lignes. Il ne visite ni les commentaires `.ts` ni les messages de commit.

## 4. `#480-r4` — l'étage qui échoue, et pourquoi `#480-r1` ne l'explique pas

Rejoué dans un worktree frais (`38e317f1`), voie par voie :

| étage | commande | résultat |
|---|---|---|
| dépendances absentes | `node node_modules/frida-compile/dist/cli.js …` | `Cannot find module …/frida-compile/dist/cli.js` |
| après `npm ci` (rc 0) | idem | **`Unable to write bundle: ENOENT … frida/dist/hooks.js`**, rc 1 |
| après `mkdir dist` | idem | rc 0, bundle 1 145 561 o |
| via npm | `npm run build:hooks` | même `ENOENT`, rc 1, 13 s |

**La compilation réussissait déjà** : aucun `Cannot find module`, les 849 arêtes d'import résolues.
Seule l'**écriture** échouait. `frida/dist/` est gitignoré (`frida/.gitignore:2`), git ne matérialise
jamais un répertoire vide, et `frida-compile` ne crée pas son répertoire de sortie.

⇒ **Deux causes distinctes.** `#480-r1` (entrées de build non versionnées) est corrigé depuis #365 ;
`#480-r4` vit à l'autre bout de la chaîne. Ce qu'elles partagent est la **classe** — « un checkout
frais ne peut pas produire le bundle » — et c'est ce qui rendait l'hypothèse « même gisement »
raisonnable ; la mesure la sépare.

**Correctif** : `frida/package.json` — `build:hooks` et `watch:hooks` créent `dist/` avant de
compiler. Retournement obtenu : `dist/` absent → `npm run build:hooks` rc 0, sans geste manuel.

⚠ **La voie DIRECTE reste à découvert.** `tacticus-orchestration/SKILL.md:147` documente
`node node_modules\frida-compile\dist\cli.js …`, qui court-circuite le script npm : elle exige
toujours que `dist/` existe. Un correctif structurel (versionner un marqueur dans `frida/dist/`)
couvrirait toutes les voies, mais contredit la lettre de « **Ne jamais commit** : `frida/dist/` ».
Non appliqué — résidu `#480-r5`.

## 5. Le cliquet — et les deux défauts trouvés EN LE POSANT

`probe_480r1_entrees_de_build.py`, deux étages, critère dérivé des deux côtés.

- **Étape 1 (sortie)** — chaque script de `frida/package.json` qui **nomme** son fichier de sortie
  (`-o` / `--outfile`) doit avoir un répertoire de sortie garanti : créé par le script, ou
  matérialisé par un fichier versionné. Dérivé du `package.json` ⇒ mord sur tout script futur.
  Les scripts qui ne nomment pas leur sortie sont **hors portée et le disent** (`build`,
  `build:host`, `dev` : `tsc` crée son `outDir`).
- **Étape 2 (doc)** — les répertoires porteurs d'entrées de build sont dérivés de la **fermeture des
  imports** depuis `hooks/main.ts` (14 répertoires), jamais d'une liste de noms. Aucun ne doit être
  qualifié `gitignore` / `jamais versionné` / `jetable` / « jamais une dépendance » dans un fichier
  versionné, **sauf** si une ligne proche (±12) **nomme le même répertoire** et l'assume.
- **Étape 3 (témoin)** — fermeture vs bundle réel, en **tri-état** : le bundle est gitignoré, son
  absence se dit `NON MESURE`, jamais `0`.

⚠ **La première version de l'étape 2 rendait VERT pendant que les six fautes existaient** — le vice
même que `#365` s'était donné pour cible. Deux causes, toutes deux mesurées :

1. **La réhabilitation était cherchée dans le FICHIER ENTIER.** « versionn » apparaît dans presque
   toute case-doc (`data/`, `hooks-legacy/`…), donc la clause était toujours vraie. Bornée à une
   fenêtre.
2. **Le chemin était cherché en entier.** La doc écrit `hooks/scratch/`, jamais
   `frida/hooks/scratch` : **aucune** des mentions de `case-477` ne matchait. Les formes sont
   maintenant les **suffixes du chemin d'au moins deux segments** (un segment nu — `scratch` —
   matcherait « from scratch » et « scratchpad »).

Et un troisième, trouvé en relisant la sortie : `"jamais versionnés"` **contient** `"versionn"` et
se comptait comme sa propre réhabilitation — la faute la plus nette du corpus se blanchissait toute
seule. Les motifs d'exclusion sont désormais **retirés de la ligne** avant d'y chercher une
réhabilitation. Sans ce retrait : 3 des 6 fautes passaient au vert.

⚠ **Le cliquet a rougi sur MA propre correction** (`CLAUDE.md`, réhabilitation écrite « Il est
VERSIONNÉ » sans nommer le répertoire) — c'est le comportement voulu : une réhabilitation qui ne
nomme pas ce qu'elle réhabilite ne protège pas la ligne d'à côté.

**Limite assumée** : exclusion et mention du répertoire doivent être sur la **même ligne**.
`rpc-api.md:204` (« jamais une dépendance d'un hook live », le répertoire n'apparaissant qu'à
L207) **échappe au critère** ; il a été corrigé à la main. Élargir à une fenêtre ferait rougir des
phrases qui ne qualifient rien — un cliquet qui crie à tort finit désarmé.

## 6. Les deux fichiers non suivis — verdict : laisser, ils sont VIDES

`frida/hooks/scratch/dump-stat-comp-fields.ts` et `list-unit-comps.ts`, non suivis dans l'arbre
principal, font **0 octet** chacun (mtime `2026-07-31 15:14:41`, soit 4 minutes avant `774df416`).

Ce sont les **cadavres de l'incident** : des noms sans contenu, rescapés d'une restauration
partielle. `774df416` le dit explicitement — *« ne sont importés par personne : non versionnés,
sans effet sur le build »*. Confirmé : `probe_365` est **vert** (209 fichiers, 881 imports) et le
bundle se construit sans eux (mon worktree ne les contient pas).

**Coût de leur disparition : nul** — il n'y a aucun contenu à perdre. **Les verser serait
nuisible** : un fichier vide versionné *existe* pour tout contrôle qui teste l'existence, alors
qu'il n'est pas un module — exactement le piège que #365 a mesuré (`probe_365` verdissait sur
l'existence pendant que `frida-compile` rendait « is not a module »). Ils restent donc non suivis,
et **rien dans cette tranche ne les touche**.

## 7. Ce qui n'est PAS couvert

- **Les 142 erreurs `tsc` de `hooks/scratch/` ne sont pas tranchées.** Cette tranche corrige la
  *qualification* qui les écartait ; elle ne décide pas si elles entrent au contrat de typage.
  Le compte est stable et re-mesuré (146 / 142 / 3 / 1). Reste ouvert (`#480-r5`).
- **La voie directe de build** (hors npm) reste sensible à l'absence de `frida/dist/` — §4.
- **Aucune confrontation live** : tranche 100 % offline, aucun runner monté, aucun reinject. Le
  bundle produit ici n'est **pas** chargé dans la session Frida 8 ; le correctif `package.json`
  ne touche à aucun `frida/hooks/*`, donc **aucune fenêtre de reinject n'est requise**.
- **Le recensement ne visite ni les commentaires `.ts` ni les messages de commit** (§3).

## Résidus

- **`#480-r5` — deux restes du même chantier.** (a) Les **142 erreurs `tsc`** d'un répertoire
  versionné et bundlé : les faire entrer au contrat de typage, ou **écrire et motiver** l'exclusion —
  ce que `#480-r1` demandait et que cette tranche ne fait pas. (b) La **voie directe** de build
  (`node node_modules/frida-compile/dist/cli.js`) échoue toujours si `frida/dist/` n'existe pas ; le
  remède qui couvrirait toutes les voies — versionner un marqueur sous `frida/dist/` — contredit la
  lettre de « Ne jamais commit `frida/dist/` » et demande un arbitrage.
  *Retournement* : `tsc -p tsconfig.hooks.json` a un compte assumé et gardé, et un checkout frais
  produit le bundle **par n'importe laquelle** des voies documentées.
