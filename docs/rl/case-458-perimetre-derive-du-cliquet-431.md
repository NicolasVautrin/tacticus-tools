# #458 — `probe_431` rendait VERT sur un tiers de son gisement

**État : FERMÉ (2026-08-02).** Le périmètre du cliquet se dérive désormais de l'**extension**,
et le cliquet **prouve sa couverture dans le même processus que sa conformité** (mécanisme #421).

Suite de `case-431-litteraux-de-build.md` (le cliquet) et de
`case-449-r2-r5-derive-vs-saisi.md` (l'audit qui l'a désigné premier des cinq risques hauts).

---

## 1. La cause, en une ligne

```python
EXEC_GLOBS = ("scripts/**/*.py", "frida/hooks/**/*.ts", ...)
any(Path(rel).match(g) for g in EXEC_GLOBS)          # <- le trou
```

`PurePath.match` **ne développe pas `**`** : il le lit comme **un** segment, et matche depuis la
droite. `scripts/**/*.py` sélectionnait donc **exactement la profondeur 3**, ni plus ni moins.
`full_match` (3.13) le développerait — il n'était pas appelé.

## 2. Le trou est BILATÉRAL, et sa moitié haute n'avait pas été soupçonnée

Mesuré sur `842429e7`, 3 268 fichiers suivis :

| régime | fichiers | exemples |
|---|---|---|
| **trop profond** | **950** | tout `scripts/python/engine/**` (364), tout `scripts/python/tests/**` (544) |
| **pas assez profond** | **17** | `frida/host/router.ts`, `frida/host/index.ts`, `frida/hooks/main.ts`, `frida/public/app.js` |
| **total hors de tout seau** | **967** | — |

La seconde moitié vient de ce que `**` **exige** un segment : un fichier posé à la racine même du
glob est raté *par le haut*. C'est le cœur du host et du hook.

Ces 967 fichiers n'étaient pas « en échec » : ils n'étaient **ni EXEC ni PROSE**, donc lus par
`tracked_files()` puis **jetés en silence**, sous un denominateur (`fichiers balayés : 903`) qui se
lisait comme une couverture.

## 3. Les quatre chiffres annoncés, re-dérivés — trois sont faux

| annoncé | mesuré | verdict |
|---|---|---|
| 1 577 `.py` suivis sous `scripts/` | **1 592** | faux (+15) |
| 900 dans aucun seau | **909** | faux (+9) |
| tout `scripts/python/engine/**` hors seau | **364 / 364** | **exact** |
| 316 hors-seau citant un hash | **284** | faux (−32) |

Les écarts viennent d'un inventaire pris à un commit antérieur. **Et l'annonce ne portait que sur
`scripts/`** : les 17 fichiers ratés *par le haut*, dont `frida/host/router.ts`, n'y figurent pas.

## 4. Ce que le nouveau périmètre trouve : **zéro rouge réel**

C'est la conclusion qui compte, et elle inverse la lecture de l'audit. Sur les 967 fichiers :

- **284** citent un hash de build ;
- **278** ne le font qu'en **prose** (docstring ou commentaire) — l'AST les écarte exactement ;
- **30** occurrences sont en position exécutable, dont **17 RESOLUTION**, dans **3 fichiers** ;
- **les 17 sont des DONNÉES DE FIXTURE**, aucune n'ouvre d'artefact.

Tranché fichier par fichier :

| site | nature | traitement |
|---|---|---|
| `test_431_build_pin_offline.py` (14) | l'**auto-test du cliquet** : il porte par construction un exemple de chaque classe que `classify` distingue | **exemption dérivée** du nom du module, bornée et imprimée |
| `test_symbols_coverage_guard_offline.py` (2) | deux **étiquettes de transition**, `LOAD-BEARING` (clé de `PERTES_CONNUES`) | **composées** (`"gqfc5mff" + "6c"`) |
| `test_314_absolute_repo_path_offline.py` (1) | le hash est le **contenu** d'un fichier factice écrit en `tmp_path` | **composé** |

La composition n'est pas une astuce pour faire taire le garde : c'est le patron **déjà écrit et
documenté** dans `test_314` (`_SEG = "tacticus" + "-tools"`, « la meilleure preuve que le cliquet
n'exempte personne, pas même son auteur »). Neutraliser les deux noms en `buildA`/`buildB` aurait
**affaibli** le test — `comparer_couverture` les utilise comme clé de registre.

## 5. La correction

**Le périmètre se dérive de l'EXTENSION, plus d'une liste de racines.** Une liste de racines est un
inventaire à maintenir, et sa péremption est muette : celle-ci n'avait **jamais** couvert
`scripts/frida/*.js` (les scripts Frida vivants que `CLAUDE.md` nomme), `scripts/node/*.mjs`,
`lib/*.py`, `frida/tools/*.ts` — 17 fichiers de plus, à aucune profondeur.

**Étape 0 — COUVERTURE.** Toute extension présente dans l'arbre suivi et absente des trois seaux
(`EXT_EXEC` / `PROSE_EXT` / `NEUTRE_EXT`) fait **rougir**. C'est ce qui rend le vert du cliquet
signifiant : sans elle, un fichier hors de tout seau est indiscernable d'un fichier propre.

Effet mesuré : seau EXEC **903 → 1 928**, non classés **967 → 0**. Les extensions neuves entrées au
seau EXEC (`.java`, `.sql`, `.ps1`) ont chacune leur syntaxe de commentaire ; leurs 4 citations sont
toutes en commentaire (vérifiées à la main).

## 6. La contre-épreuve

`test_le_cliquet_ROUGIT_sur_une_resolution_A_CHACUNE_DES_TROIS_PROFONDEURS` mute trois fichiers
réellement suivis — `probe_88_on3_emitter.py` (profondeur 3, la seule vue avant),
`tools/damage_decomp.py` (trop profond), `frida/hooks/controller.ts` (racine du glob) — et exige
que **les trois soient nommées dans la même sortie**. Le témoin négatif (mention en prose) est joué
aux trois profondeurs lui aussi.

⚠ **Un `finally` ne survit pas à un kill.** Mesuré en écrivant ce test : un pytest tué par un
timeout externe a laissé les **trois** cibles mutées — dont un fichier du bundle Frida. Un résidu de
cette forme rend la banque **entière** rouge, avec le rouge attribué au mauvais cliquet (#455, même
leçon). La parade est un nettoyage **idempotent** en tête de mutation, par **troncature sur les
octets** au `\n` qui précède le marqueur : un filtrage par lignes laissait la ligne vide ajoutée,
soit une diff permanente d'un octet dans l'arbre de chaque agent — trouvé par son propre test, pas
par relecture.

## 7. Coût : le périmètre double, le cliquet accélère

| | avant | après |
|---|---|---|
| fichiers au seau EXEC | 903 | **1 928** |
| `probe_431 --cliquet`, isolé | 33,1 s | **28,6 s** |

Le gain vient de la suppression du `Path.match` lui-même (6 constructions de `Path` + matching par
fichier, sur 3 268 fichiers) au profit d'un lookup d'extension. Banque complète re-jouée : **33
cliquets, VERTE**.

## 8. Résidus

- **`#458-r1`** — l'exemption **auto-test** est bornée à « importe le module du cliquet » et
  imprimée à chaque run, mais elle reste une exemption **de fichier entier** : un vrai chemin
  d'artefact écrit dans `test_431_build_pin_offline.py` ne serait pas vu. Un critère plus fin
  demanderait de distinguer « chaîne-donnée » de « chaîne-chemin », ce que le docstring du probe
  refuse explicitement (deux critères contextuels essayés et rejetés, tous deux vers le vert faux).
- **`#458-r2`** — `NEUTRE_EXT` déclare `.css/.html/.ini/.example` sans extension : c'est un
  jugement, pas une dérivation. Il est gardé par l'étape 0 dans un seul sens (une extension neuve
  rougit), pas dans l'autre (une extension mal classée neutre reste muette).
- **`#458-r3`** — la face `.ts/.js/.java/.ps1/.sql` reste **heuristique de ligne** (pas d'AST),
  et c'est annoncé comme tel depuis #431. Le seau a doublé, donc l'exposition à cette heuristique
  aussi : 206 `.ts` + 82 `.js` + 41 autres.
