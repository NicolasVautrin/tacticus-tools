# #471 — Un cliquet qui rougit SANS AVOIR RIEN VU : le tri-état de la banque

## 1. Le défaut, et sa mesure

`scripts/ratchets.ps1` rabattait **tout** code de sortie non nul sur `ROUGE` et le comptait dans
`$rouges.Count`. Un cliquet qui n'avait **rien pu mesurer** était donc indistinguable d'un cliquet
qui avait mesuré et trouvé un trou.

**Mesure du 2026-08-04, banque sur `d2ede23d`** :

```
[ratchets] BANQUE ROUGE -- 1/40 cliquet(s) : probe_457:s3
```

Or cette tranche n'a joué **aucun test**. Elle a crashé en **4,5 s** dans son propre montage :

```
subprocess.CalledProcessError: Command '['git', 'ls-files', 'scripts/python/tests']'
returned non-zero exit status 128
(probe_457_offline_tests_green.py:239, appele depuis main():1041)
```

Les 7 autres tranches étaient **vertes** (`s5` : 412,7 s, rc=0) et la commande rejouée à la main
dans le même worktree rendait `rc=0` immédiatement — donc **transitoire**, pas un état cassé.

Une exception non rattrapée rend `1` en Python. Le crash sortait donc **exactement** comme
« un test offline est rouge », sur un dépôt sain.

C'est le vice que le dépôt combat partout ailleurs : le tri-état de `scripts/python/host_inputs.py`
(`null` = pas mesuré, **jamais** rabattu sur un zéro) et la leçon **#467-r6** (une panne de capteur
doit porter son NOM — `gh` rendait `rc=127` pour trois pannes distinctes, ce qui a fait diagnostiquer
la mauvaise cause). Le symétrique est **#439** : là-bas un cliquet qui ne *pouvait pas* rougir, ici
un cliquet qui rougit *sans avoir rien vu*.

## 2. Le critère — énoncé avant le code

Un cliquet répond à **deux** questions, dans cet ordre :

1. **MONTAGE** — « ai-je pu CONSTITUER l'objet de ma mesure, et l'observer ? »
2. **MESURE** — « l'observation viole-t-elle mon invariant ? »

**La ligne de partage** : le montage est tout ce dont le cliquet dépend et qui **n'est pas le
dépôt** — le CWD que l'appelant lui donne, les outils externes qu'il invoque (`git`, `pwsh`,
`pytest` en tant que programme), le système de fichiers. La mesure est ce qui vient du **contenu**
du dépôt.

**Test opérationnel, en une question** :

> « un dépôt **PARFAIT**, à cet instant, sur cette machine, aurait-il produit ce même échec ? »
> **OUI** → `INDISPONIBLE` (le dépôt n'est pas accusé) · **NON** → `ROUGE`

Ce que le critère tranche, et qu'il faut écrire pour qu'il ne glisse pas :

| Situation | Verdict | Pourquoi |
|---|---|---|
| `git ls-files` rend 128 | INDISPONIBLE | un dépôt parfait le subit aussi |
| `pytest` rc 2 / 3 / 4 (interrompu, erreur interne, usage) | INDISPONIBLE | rien n'a été joué |
| CWD faux imposé par l'appelant | INDISPONIBLE | défaut du câblage, pas du dépôt |
| un test offline **échoue** (`pytest rc=1`) | ROUGE | fait établi sur le dépôt |
| `git ls-files` rend **rc=0 et une liste VIDE** | **ROUGE** | réponse *valide* de l'outil ⇒ fait sur le dépôt : le périmètre s'est effondré |

La dernière ligne est **la** frontière à ne pas laisser glisser. Sans elle, « je n'ai rien trouvé »
deviendrait « je n'ai pas pu regarder », et tout finirait `INDISPONIBLE`.

### Pourquoi ce n'est pas une échappatoire

`INDISPONIBLE` est **BLOQUANT** : le code de sortie de la banque n'est jamais `0` quand une entrée
est indisponible, et l'état s'imprime en clair avec son extrait de cause. Reclasser un rouge en
indisponible ne fait donc **rien taire** — ça change l'**accusé** (le harnais au lieu du code
fusionné), pas le blocage. C'est ce qui distingue ce tri-état d'un `|| true`.

## 3. Ce qui a été livré

### 3.1 La table — `scripts/ratchets-verdict.ps1` (neuf)

Deux fonctions, dot-sourcées par `ratchets.ps1` :

- `Get-EtatCliquet <rc>` → `OK` (0) | `INDISPO` (99, 64) | `ROUGE` (tout le reste) ;
- `Get-CodeSortieBanque -Rouges R -Indispos I` → `R` si `R>0`, sinon `99` si `I>0`, sinon `0`.

**Le rouge prime** : il accuse le code fusionné, information plus actionnable qu'un capteur muet,
et le contrat historique (`rc = nombre de cliquets rouges`) reste vrai dès qu'il y a un rouge.

Fichier **séparé**, et c'est structurel : dot-sourcer `ratchets.ps1` lui-même *jouerait la banque*,
donc aucun garde ne pourrait interroger la table sans la réimplémenter — et un garde-fou dont le
verdict dérive ne vaut rien (leçon de `probe_319`).

**La convention n'est pas inventée** : `99` était déjà tenu par `scripts/ratchets-bg.ps1`
(« MONTAGE EN ECHEC — aucun verdict sur le depot ») et par `probe_457` (`EX_NON_MESURE = 99`,
déjà rendu par son garde de CWD depuis #464) ; `64` était déjà documenté « à traiter comme non
mesuré ». Les trois ne se parlaient simplement pas — la banque **écrasait** le 99 de `probe_457`
en `ROUGE`. Ce fichier les réunit.

### 3.2 La banque — `scripts/ratchets.ps1`

Trois seaux au lieu de deux ; l'affichage porte `OK` / `INDISP` / `ROUGE`, et un indisponible
reçoit **le même bloc de détail** qu'un rouge (commande, « seul à voir », doc, log, extrait) avec
un motif de cause dédié (`REFUS`, `rc=99`, `MONTAGE`, `CalledProcessError`…) — sans motif propre,
l'extrait retomberait sur la queue du log et noierait la cause.

Ligne de bilan : `BANQUE VERTE` / `BANQUE ROUGE` / **`BANQUE INDISPONIBLE`**. Quand les deux
coexistent, le rouge donne le code de sortie **et** les indisponibles sont nommés quand même —
sinon corriger le rouge rendrait la banque verte sur une entrée jamais mesurée.

### 3.3 Le probe — `scripts/python/probe_457_offline_tests_green.py`

- `MontageImpossible` : exception **dédiée**, levée aux seuls sites de montage ;
- `_git(...)` : **foyer unique** des appels git. Une `OSError` lève toujours ; un `rc` non nul lève
  sauf `tolere_rc=True` (le `git diff` de `--since`, dont le rc non nul signifie « ref inconnue »,
  information que `impacted_files` traduit déjà en « TOUT rejoué ») ;
- `main` **traduit** `MontageImpossible` en `EX_NON_MESURE`. L'attrape est **étroite** par
  construction — un `except Exception` avalerait un bug du probe lui-même et le ferait passer pour
  une indisponibilité, l'échappatoire exacte que ce tri-état doit éviter.

**Un trou adjacent, fermé au passage** : `_modules_du_graphe` rendait `{}` **en silence** quand git
échouait. C'était pire qu'un crash — avec `mods` vide, la clôture du graphe d'imports est vide et
`impacted_files` **sous-sélectionne**, c'est-à-dire un **faux vert** (exactement le mode de
défaillance qu'une empreinte vidée produit, décrit par `_footprints_path`).

### 3.4 Le cliquet — `scripts/python/probe_471_tri_etat_cliquets.py` (neuf, dans la banque)

Cinq étapes ; les quatre premières sont dans l'ordre table → branchement → contre-épreuve →
inventaire :

1. **La table** est *interrogée* (dot-source `pwsh`), jamais réimplémentée : 7 codes × 6 régimes.
2. **Le branchement** — une table juste mais **débranchée** passerait pour un garde-fou (c'est
   l'étape 2 de `probe_455`, même forme). Trois marques exigées dans le texte de `ratchets.ps1`,
   et deux **interdits** (`Rc -ne 0`, `exit $rouges.Count`) : sans la seconde direction, l'ancien
   classement pourrait cohabiter avec le neuf, et le premier gagnerait.
3. **La contre-épreuve, en montage RÉEL** (§4).
4. **L'inventaire** (§5), non bloquant.
5. **La sentinelle MORTE** — un script qui *définit* une constante de non-mesure sans jamais la
   rendre depuis son point d'entrée porte la marque du tri-état sans le tenir. Même forme que la
   `Rougit = 'compteur'` morte que `probe_439` garde dans l'autre direction. Bloquant.

Il **n'a aucun drapeau qui désarme une étape**. Un `--skip-contre-epreuve` a été écrit puis
**retiré** : la contre-épreuve *est* le cliquet (sans elle il ne reste qu'un parse de texte), et une
porte de sortie finit toujours par être empruntée par un appelant pressé.

## 4. La contre-épreuve

### 4.1 Le montage RÉEL, rejoué à chaque passage

`probe_457` dérive sa racine de son **propre fichier** (`_PYDIR.parents[1]`) et son périmètre de
`git ls-files`. Le recopier dans une arborescence `scripts/python/` jetable suffit donc à le faire
travailler sur *ce* dépôt-là — avec le vrai binaire, le vrai `pytest`, le vrai `git`. **Un seul**
dépôt, dans un **tmpdir système** (`mkdtemp()` sans `dir=`, #455), que les trois scénarios font
**évoluer** :

| scénario | montage | rc attendu | ce qui prouve que la mutation a MORDU |
|---|---|---|---|
| **VERT** | `git init` + 1 test qui passe | `0` | `VERDICT: PASS` + `1 test(s) joue(s)` |
| **ROUGE** | + 1 test qui échoue, `git add` | `1` | `VERDICT: FAIL` + **`1 failed`** |
| **MONTAGE CASSÉ** | `.git` renommé ⇒ `git ls-files` rend **128** | `99` | `MONTAGE EN ECHEC` + `RIEN n'a ete mesure` + **aucun `Traceback`** |

Le dépôt unique n'est pas qu'une économie de mur (80,9 s → **20,1 s** isolé, dont contre-épreuve
55,5 → 10,5 s ; une part de l'écart vient aussi du cache disque chaud). Il **renforce** la
contre-épreuve : le scénario cassé hérite du **test rouge**, donc son `99` ne peut pas venir d'une
absence de gisement — il y avait bien de quoi rougir, et le probe a quand même dit « je n'ai pas pu
mesurer ».

Le témoin **VERT** n'est pas décoratif : sans lui, un probe qui rendrait `1` ou `99` *en toutes
circonstances* passerait les deux autres scénarios. Le scénario cassé **reproduit le gisement** au
lieu de saboter le binaire : retirer `.git` fait rendre `128` à git, c'est-à-dire le rc mesuré.
`GIT_CEILING_DIRECTORIES` empêche git de remonter à un dépôt parent — sans ce plafond, la
contre-épreuve mesurerait autre chose que ce qu'elle annonce.

### 4.2 L'état AVANT, mesuré sur le gisement exact

La version `origin/master` de `probe_457`, jouée dans le même montage cassé :

```
=== AVANT (origin/master), git hors service -> rc=1
subprocess.CalledProcessError: Command '['git', 'ls-files', 'scripts/python/tests']'
returned non-zero exit status 128
```

**rc=1 + traceback** — le crash du 2026-08-04 reproduit à l'identique, et classé `ROUGE` par la
banque d'alors. Après : **rc=99**, `MONTAGE EN ECHEC`, aucun traceback, classé `INDISPONIBLE`.

### 4.3 Les cinq mutations — le probe MORD dans les deux sens

Chaque mutation est injectée, jouée, puis **annulée** ; le contrôle non muté est vérifié vert.

| mutation | étape | verdict |
|---|---|---|
| `Get-EtatCliquet` : 99 → ROUGE | 1 | `ROUGE Get-EtatCliquet(99) = 'ROUGE', attendu 'INDISPO'` |
| `Get-CodeSortieBanque` : `-gt` → `-lt` (rend 0 sur indispo) | 1 | 2 régimes rouges |
| `exit (Get-CodeSortieBanque …)` → `exit $rouges.Count` | 2 | absent **et** interdit détectés |
| seau `$indispos` → `@()` | 2 | branchement absent |
| `except MontageImpossible` → `except NotImplementedError` | 3 | `rc=1, attendu 99` ; `porte 'Traceback'` |
| `probe_457` rend 99 partout | 3 | **`CONTRE-EPREUVE VERT : rc=99, attendu 0`** |
| `if int(rc) != 0` → `not in (0, 1)` (rouge non détecté) | 3 | `CONTRE-EPREUVE ROUGE : rc=0, attendu 1` |

Les deux dernières prouvent que les témoins VERT et ROUGE sont **discriminants**, pas décoratifs.

## 5. Le balayage — quelles AUTRES entrées confondent encore

Dérivé de `scripts/ratchets.ps1` (parse textuel, comme `probe_439` — aucune liste saisie), sur les
**40 entrées** de la banque au 2026-08-04 :

| classe | compte | entrées |
|---|---|---|
| **portent** le tri-état (rendent 99) | **8** | les 8 shards `probe_457` |
| **gisement DIRECT** sans tri-état | **11** | `probe_273`, `probe_313`, `probe_319`, `probe_365`, `probe_391`, `probe_431`, `probe_439`, `probe_455`, `probe_462`, `probe_462r5`, `probe_464` |
| gisement **seulement par un module importé** | **3** | `probe_440`, `probe_467`, `probe_467r4` |
| aucun outil externe direct | **18** | les 6 étapes `probe_283`, `probe_120`, `probe_181`, `probe_229`, `probe_274`, `probe_366×3`, `probe_421`, `probe_443×3`, `probe_449r2` |

« Gisement » = le fichier d'entrée appelle `subprocess.run/check_output/check_call/Popen`,
`shutil.which` ou `pytest.main`. Chez ces 14 entrées, une panne d'outil sort en `rc=1`, donc en
**rouge de gisement**.

**Ce que je laisse, et pourquoi** : les 14 restent telles quelles (**résidu #471-r1**). Les
convertir en bloc ferait rougir la banque sur une douzaine d'entrées à la fois, et un garde-fou qui
rougit partout se fait désactiver — c'est écrit noir sur blanc dans `probe_439`
(`forme_appel_externe` : « on ne rougit que sur PREUVE d'impossibilité ; l'inverse ferait de ce
cliquet un générateur de faux rouges »). Le tri-état se pose **entrée par entrée, quand son
gisement mord** — `probe_457` l'a fait parce que le sien a mordu, en production, avec une mesure.

⚠ **Limite du compte** : il est **direct** (le fichier d'entrée). Le gisement transitif au-delà de
la profondeur 1 n'est pas mesuré. Ne pas lire cet inventaire comme exhaustif.

## 6. Ce qui n'est PAS fait

- **La CAUSE du `128` n'est pas tranchée, et aucune parade n'est codée dessus** (**résidu
  #471-r2**). L'hypothèse « contention git » — les worktrees partagent `.git/`, la banque tournait
  pendant un `git merge --no-ff` dans l'arbre principal — est **plausible et non établie**. La
  trancher demanderait de rejouer une passe **avec** et **sans** opération git concurrente. Le
  défaut fermé ici est le **tri-état**, qui vaut quelle que soit la cause.
- **Aucun rejeu automatique.** « Un rejeu qui passe ne prouve rien » : la conduite à tenir est
  imprimée dans le bloc `INDISPONIBLE` (rejouer *cette* entrée seule ; si elle passe, le dire dans
  la PR, ne pas la taire), pas exécutée en silence.
- **Le gisement transitif** (§5) n'est pas mesuré.
- `ratchets-bg.ps1` n'est **pas** modifié : il traduisait déjà `99` en « MONTAGE EN ECHEC — aucun
  verdict sur le depot », et `loop_status._lire_verdict` lit cette étiquette. Le 99 de la banque y
  arrive donc correctement, par une branche qui existait déjà mais que **rien ne pouvait
  atteindre** — `ratchets.ps1` ne rendait jamais 99.

## 7. Relevé de validation (2026-08-04)

| épreuve | résultat |
|---|---|
| `probe_471` (5 étapes) | `VERDICT: PASS` |
| 7 mutations injectées (§4.3) | 7 rouges, contrôle non muté vert |
| les 3 mutations d'étape 3, **rejouées après la mutualisation** du dépôt | 3 rouges, contrôle vert |
| montage cassé, `probe_457` **AVANT** (`origin/master`) | `rc=1` + `CalledProcessError … 128` (gisement reproduit) |
| montage cassé, `probe_457` **APRÈS** | `rc=99`, `MONTAGE EN ECHEC`, aucun traceback |
| `probe_439` sur la banque enrichie | `VERDICT: PASS` — `probe_471` classé capable de rougir |
| `Get-EtatCliquet` / `Get-CodeSortieBanque` | 7 codes + 6 régimes conformes |
| **bout en bout**, un cliquet indisponible dans la banque réelle | `INDISP` + bloc de détail + `BANQUE INDISPONIBLE` + **rc=99** |
| **bout en bout**, 1 rouge **et** 1 indisponible | **rc=1** (le rouge prime) et l'indisponible reste **nommé** au bilan |
| `probe_471` isolé | **20,1 s** (`-Only probe_471 -Serial`) |
| banque complète, après rebase | cf. §9 |

Les deux épreuves « bout en bout » comblent le seul chemin que les étapes 1–3 ne couvraient pas :
l'**affichage** et le **code de sortie** de la banque réelle sur un indisponible. Elles ont été
jouées par mutation temporaire d'un cliquet (rendu `99`, et `probe_439` rendu `1`), puis restaurées
par `git checkout --`.

## 8. La technique, pour le prochain cas du même genre

**Symptôme-type** : un instrument de garde (cliquet, capteur, balayage) rend **un seul** code
d'échec pour deux situations incompatibles — une panne de son propre **montage**, et un verdict
défavorable sur ce qu'il **mesure**. On corrige alors la mauvaise cause. Déjà vu à trois étages
différents : `host_inputs.py` (`null` ≠ 0), `#467-r6` (trois pannes de `gh` derrière un `rc=127`),
et ici la banque.

1. **Énoncer le critère AVANT de toucher au code de retour.** La plomberie est triviale ; la ligne
   de partage porte tout. Celle qui tient : « un **sujet parfait**, à cet instant, sur cette
   machine, aurait-il produit ce même échec ? »
2. **Borner le critère par son cas limite, sinon il glisse et tout devient indisponible.** Le cas
   qui tranche est l'outil qui répond `rc=0` avec un résultat **vide** : réponse valide ⇒ fait sur
   le sujet ⇒ **rouge**. Sans cette borne écrite, « je n'ai rien trouvé » devient « je n'ai pas pu
   regarder ».
3. **Rendre l'état neuf BLOQUANT**, sinon c'est un `|| true` déguisé : code de sortie propre,
   extrait de cause imprimé, rc global jamais 0.
4. **Attrape ÉTROITE, jamais un attrape-tout** : type dédié levé aux seuls sites de montage,
   traduit en un point. Un attrape-tout avalerait un bug de l'instrument lui-même et le ferait
   passer pour une indisponibilité. Corollaire : **foyer unique** des appels d'outil externe,
   sinon le trou se rouvre au premier appel ajouté.
5. **Contre-épreuve en montage RÉEL, pas simulé** — le patron réutilisable : un outil qui dérive sa
   racine de *son propre fichier* et son périmètre de `git ls-files` se rejoue intégralement dans
   un dépôt jetable (tmpdir + `git init` + `git add`), avec le vrai binaire. On y joue **les trois
   issues**, et le scénario cassé **reproduit** le gisement au lieu de saboter le binaire.
   `GIT_CEILING_DIRECTORIES` est obligatoire — sans plafond, git remonte à un dépôt parent et la
   contre-épreuve mesure autre chose que ce qu'elle annonce.
6. **Le témoin sain n'est pas décoratif** : sans lui, un instrument qui rendrait `1` ou `99` en
   toutes circonstances passerait les deux autres scénarios.
7. **Sur une contre-épreuve, VERT est le résultat suspect** : chaque scénario exige une preuve que
   sa mutation a mordu (le rouge doit porter `1 failed`, l'indisponible sa cause **et aucun
   traceback**).
8. **Inventorier sans rougir quand le gisement est massif** (§5) — un garde-fou qui rougit partout
   se fait désactiver.
9. **Ne pas coder de parade sur une cause non établie** (§6) — et pas de rejeu automatique : il ne
   prouverait rien et masquerait la mesure qui permettrait de trancher.

Deux pièges d'outillage rencontrés, notés pour ne pas les repayer :

- **Indexer tôt sauve une mutation qui dérape.** Un timeout d'outil a interrompu une boucle de
  mutation et laissé `ratchets-verdict.ps1` **muté** sur disque ; `git checkout -- <chemin>` l'a
  restauré depuis l'index. Indexer avant d'injecter des mutations est le filet, pas une formalité.
- **Ne jamais écrire de la prose markdown par here-string PowerShell interpolée** (`@"..."@`) : les
  backticks du markdown y sont des **échappements**. Mesuré — `` `ratchets.ps1` `` est devenu un
  retour chariot (`` `r ``) et `` `null` `` un saut de ligne (`` `n ``). La corruption est
  silencieuse et ne se voit qu'à la relecture. Passer par l'outil d'édition, ou `@'...'@`.

## 9. Relevé de banque

Joué **après** rebase sur `origin/master` (12 commits rattrapés, dont **aucun** ne touche les
fichiers de cette tranche — vérifié par `git log --name-only`) :

```
[ratchets] BANQUE VERTE -- 41 cliquet(s), mur 623,5 s.
```

Les 41 verts, `probe_471` compris (115,9 s **sous charge**, 20,1 s isolé, pour un mur dominé par
`probe_457:s1` à 504,9 s) — donc **coût marginal en parallèle nul**, qui est le critère d'admission
écrit dans `ratchets.ps1`, jamais le coût absolu.

⚠ Le mur de 623,5 s est celui d'un **worktree froid** : `logs/ratchets/457-durations.json` est
gitignoré, donc `probe_457` retombe sur le repli md5 (mur sous-optimal, **verdict inchangé** — c'est
l'arbitrage déjà documenté dans `_weights_path`). Chiffre à re-dériver, pas à citer.

La composition de la banque est **définie** par `scripts/ratchets.ps1` et ne se recopie nulle part ;
cette case-doc **atteste** ce qui a été joué, elle ne définit rien.
