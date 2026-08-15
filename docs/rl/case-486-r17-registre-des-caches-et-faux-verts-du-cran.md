# #486-r17 — Le registre des caches de verdict, et les quatre faux verts du cran de fraîcheur

Tranche du 2026-08-15. Foyer : `scripts/python/verdict_cache.py` (+ `import_closure.py`,
`probe_485_imports_differes.py`, `probe_283_enum_ordinal_sweep.py`,
`probe_486r12_declencheurs.py`). **100 % offline** — le jeu n'était pas lancé.

Cette fiche couvre cinq résidus du même foyer : `#486-r17`, `#486-r16`, `#486-r8`, `#486-r9`,
`#943-r2`. Les chiffres se **re-dérivent** (les commandes sont données) ; ne pas les citer.

---

## 1. Le registre des caches avait DÉCROCHÉ — 4 connus sur 11 réels

`test_486_r1_cache_verdict_offline.py` portait un registre **ÉNUMÉRÉ** (`CACHES`, 4 entrées).
Mesure : le dépôt porte **11** fichiers sous `scripts/cliquets-cache/`, produits par **8**
modules. **Sept caches versionnés n'étaient gardés par rien** — ni forme, ni contexte, ni
fraîcheur, ni fidélité.

Et deux d'entre eux ont été pris en flagrant délit de **dérive silencieuse** :

| cliquet | rc | diff du cache versionné |
|---|---|---|
| `probe_326_dsl_primitive_inventory.py` | `0` | +1 / −2 |
| `probe_283_enum_ordinal_sweep.py --step mirror` | `0` | **+402 / −237** |

`probe_283` est **dans la banque** : la dérive se produisait à chaque passe, sans signal —
exactement le régime que #486-r22 disait avoir fermé, sur des cliquets que son cran ne
couvrait pas (`rendre_compte_du_cache` était appelé par **4 constructions sur 8**).

**Livré** : `CACHES_VERSIONNES`, écrit à la main et confronté au code dans les **trois** sens
(disque → registre, registre → disque, code → registre), régime `cran`/`espion` **déclaré avec
sa raison** et **contre-épreuve bidirectionnelle** (un `False` qui appelle quand même le cran
rougit : une exemption périmée se recopie).

⚠ **Le registre est écrit à la main EXPRÈS.** Dérivé du disque, il épouserait tout fichier neuf
et l'étage serait tautologique. Ce qui est dérivé, c'est la **réalité** ; ce qui est déclaré,
c'est l'**attendu**.

---

## 2. `cache_a_commiter` rendait un vert par QUATRE portes

Sa prémisse écrite — « le run vient d'écrire le fichier de toute façon » — **n'est pas établie
par l'appel**. Dans les quatre cas ci-dessous, `git diff --quiet` comparait le fichier d'une
passe **précédente** à l'index et rendait `0`, lu comme « à jour ».

1. `enregistrer()` **jamais appelé** (mode partiel, `--verifier-cache`) ;
2. `enregistrer()` appelé, **rien vu** (périmètre vide, pré-filtre qui écarte tout) ;
3. `enregistrer()` appelé, **écriture en échec** (disque, fichier verrouillé) ;
4. **fichier NON SUIVI par git** — `git diff --quiet -- <chemin>` l'**ignore**.

La 4ᵉ est la plus coûteuse et elle a été prise **en flagrant délit** : au câblage du cache de
`probe_485`, le TSV neuf était `??` et le cran se taisait. Conséquence exacte : le cache
versionné **n'entre jamais dans le dépôt**, donc tout worktree frais repart **FROID** — le
régime précis pour lequel il est versionné.

**Livré** : tri-état `CacheCliquet.ecrit` (`None` / `True` / `False` + `motif_non_ecrit`) et un
`git ls-files --error-unmatch` en amont du `git diff`. Les trois premiers cas sortent en
**PAS MESURÉ**, le quatrième en **ROUGE**. Contre-épreuve : le cran **mord** encore après une
écriture réelle, **s'éteint** après `git add` (vérifié rc 6 → rc 0), et **ne teinte pas** le rc
quand il n'a pas mesuré.

---

## 3. `#486-r17` (a) — la clé à dépendances câblée sur `probe_485`

`probe_485_imports_differes` portait le **même critère** que `probe_270r4r2` (charger la cible
dans un process frais) donc la **même clé** (la fermeture de `import_closure`), et restait dans
`NON_CACHABLES` avec une raison qui décrivait une clé **existante**.

| | froid | chaud |
|---|---|---|
| interpréteurs lancés | 93 / 93 | **0 / 93** |
| poste `_atteints` | ~37 s | **0,47 s** |
| run complet | 46,5 s | 33,1 s |

Verdict **identique** froid/chaud (328 recensés, 272 porteurs, 56 gratuits), **0 cible opaque**.
Le reste du temps est ailleurs et hors périmètre de ce résidu : `recenser` 9,9 s, calcul des
fermetures 8,4 s, `_redondants` 9,8 s.

**Foyer unique** : le détecteur de génération est **hissé** de `probe_270r4r2_import_en_premier`
vers `import_closure.Generation` — deux instances videraient la même `Cloture` chacune de son
côté et se feraient mutuellement recalculer. Les trois fonctions publiques du probe **délèguent**
(deux fichiers de test les appellent).

**(c) RÉFUTÉ.** « Les trois cliquets de #486-r1 portent toujours le défaut `sha_fichiers` » était
**périmé de huit jours** (`d4b78353`, 2026-08-07). Compte re-dérivé du code : **13** sites
`sha_fichiers_texte`, **0** site `sha_fichiers`. Le zéro est désormais tenu par un cliquet
(`test_aucun_CONTEXTE_ne_passe_par_la_variante_OCTETS`), pas par une phrase — `sha_fichiers`
**survit** parce que le test des deux variantes en a besoin comme témoin.

---

## 4. `#486-r8` — RÉFUTÉ, dans l'attribution ET dans le bénéfice

Énoncé : « le cache LIT les 2 947 fichiers à chaque run **pour pouvoir les hacher** ; le blob de
l'index git donnerait le hash sans lire ».

**Mesure.** Sur les **7** sites qui hachent un texte, **5 portent un pré-filtre qui consomme le
texte AVANT tout hachage** (`"slot" not in texte`, `"Enum" not in texte and "Flag" not in texte`,
`not any(cls in texte for cls in PAR_CLS)`) et les 2 autres partagent la lecture d'un balayage
dont un autre étage du même probe a besoin. **Aucun consommateur ne lit pour hacher** : le
cliquet lit parce qu'il a besoin du texte, et le hash se prend sur un texte déjà en main.

Le blob ne supprimerait donc une lecture qu'en supprimant d'abord le pré-filtre — or celui-ci
écarte **2 431 fichiers sur 4 345** (mesure sur `probe_477r24r1`), qu'il faudrait alors **faire
entrer au cache** : `+9 724` lignes sur un TSV de 7 656, soit **+127 %**, sur l'artefact dont
`#943-r2` dit précisément que la volatilité est le problème.

Bilan : gain théorique **~1,9 s** (2,97 s de lecture − 1,07 s de `git ls-files -s` +
`git diff-files`) contre un doublement du fichier versionné. **Résidu clos.**

---

## 5. `#486-r16` (a) — deux fermetures essayées, deux réfutées ; l'amplitude est PUBLIÉE

L'empreinte agrège par `(dossier, extension)` avec deux témoins (min/max lexicographiques) ; un
glob discriminant sur le nom de base peut les couvrir tous les deux et rater un troisième fichier
du groupe.

* **Garder tous les chemins** : **55 555** lignes `lu` au lieu de **1 197** (**×46**) — l'empreinte
  passerait de 191 ko à ~9 Mo.
* **Confronter DANS la mesure** (gratuit en taille) : le verdict serait **figé** et dépendrait de
  `declencheur_cliquet.couvre`, qui **n'est pas dans `cle_fraicheur`** — on échangerait une
  approximation **bornée** contre un trou **non borné**. Et le poser exigerait de re-mesurer toute
  la banque (~1 425 s).

**Livré** : l'étage 2 **imprime l'amplitude à chaque run, même à zéro**. Mesure courante :
**1 groupe** à risque sur **816** groupes de plus de deux fichiers — `probe_455`,
`scripts/python/*.py`, groupe de 3.

⚠ C'est une **MAJORATION** (le cliquet n'a lu que `n` fichiers du groupe), donc un **INVENTAIRE
et jamais un gate** : rougir dessus accuserait à tort, et le remède serait d'**élargir** les
déclencheurs — c'est-à-dire de masquer le trou au lieu de le mesurer, ce que le résidu interdit.
Une panne de `git ls-files` sort en **NON MESURÉE**, jamais en zéro.

Re-dériver : `python scripts/python/probe_486r12_declencheurs.py` (bloc `AGREGATION`).

---

## 6. `#486-r9` — NON RÉSOLU. Prémisse corrigée, viabilité établie, obstacle NOUVEAU

**Ventilation re-mesurée** (l'arbre a grossi : 3 161 fichiers, pas 2 090) :

| poste | fiche | re-mesuré |
|---|---|---|
| `_sources` (lecture parallèle) | — | 1,67 s |
| `ast.parse` + `_FileInfo` | 44,1 s | **81,4 s** |
| point fixe + éval | 1,6 s | 3,50 s |

**« 58 fichiers sur 2 090 empruntent une racine à un autre module » — RÉFUTÉ en valeur, confirmé
en nature.** Les deux comptes que la fiche confond :

* **EFFET** (racine qui VIENT effectivement d'un autre module, point fixe résolu) : **11 / 3 161** ;
* **SURFACE** (modules dont un fichier POURRAIT emprunter — ce que la clé doit porter, puisqu'on
  ne sait pas sans parser si l'emprunt aboutit) : **3 158 / 3 161 (99,9 %)**.

**La clé à dépendances NE dégénère PAS**, et c'est la mesure qui le dit : fermeture d'emprunt
**médiane 10**, moyenne 16, **max 140** sur 3 161 modules ; **0 %** dépassent la moitié de
l'arbre. Invalidation : toucher un module en invalide **1 en médiane** (moyenne 16, max 2 173).
Le montage est donc **viable et payant** — ce n'est pas ce qui bloque.

⚠ **L'OBSTACLE QUE LA FICHE NE NOMME PAS, et il est du même genre que celui qui a coûté 119 s à
#486-r11** : `envs[f]` porte des **`Path` ABSOLUS**. Sérialisés tels quels dans un cache
**VERSIONNÉ**, ils diffèrent d'un worktree à l'autre — le cache serait **froid en permanence**,
c'est-à-dire inutile là où il existe. C'est exactement le vice `sha_fichiers` / `core.autocrlf`,
transposé de la **CLÉ** aux **VALEURS**. Le relativiser à `scan_root` ne suffit pas : `envs[f]`
contient aussi des chemins **hors du dépôt** (AppData, temp) qui peuvent servir de base à un
`join` ultérieur, donc une sérialisation « relatif ou HORS » perdrait de l'information.

**Ce qui reste à faire** : sérialiser `envs[f]` sous une forme **portable et sans perte** (ancre
nommée + suffixe relatif), plus cacher le **graphe d'emprunt** de chaque fichier (clé par
`sha(f)` seul) pour pouvoir calculer la fermeture **sans parser**. Et re-jouer
`probe_319_scan_fidelity.py`, qui garde la fidélité du balayage.

---

## 7. `#943-r2` — le remède de la fiche est RÉFUTÉ ; la cause racine est ailleurs

**Prémisse CONFIRMÉE** : `probe_477r24r1_slots_interface.py` rendait **`rc=6`** sur ce checkout.

**Cause racine, mesurée** : la dernière régénération commitée date du **2026-08-08**
(`89aacff9`), soit **927 commits** d'écart avec `origin/master`. Et `probe_477r24r1` **n'est dans
AUCUNE banque** (`scripts/ratchets.ps1` ne le nomme pas, `probe_477r25` non plus) : son `rc=6`
n'arrête aucune PR, donc le cache dérive **sans limite**. Ce n'est pas « toute PR qui touche
`docs/rl` l'invalide » — mesuré sur les 40 derniers commits, un commit déplace **14,6 lignes** en
moyenne, pas 2 372.

**Remède proposé — « rendre le cache insensible aux fichiers qui ne portent aucune citation » —
RÉFUTÉ** : sur les **1 914** fichiers en cache, **1 849 (96,6 %)** sont muets (aucune citation,
aucun nom seul) mais portent des **compteurs non nuls** qui entrent au total imprimé ; **aucune**
entrée n'est strictement nulle. Les sortir du cache imposerait de les **recalculer**, ce qui
détruit le gain : run **6,9 s** à chaud contre **83,1 s** avec `TACTICUS_SANS_CACHE_CLIQUET=1`,
soit un facteur **12**. La volatilité tomberait bien de 14,6 à 2,7 lignes par commit, mais au
prix de +76 s par run.

**Livré** : la régénération (l'option 1 de la fiche — passe dédiée). **Reste ouvert** : rien ne
déclenche la suivante → résidu **`#943-r9`**.

---

## Résidus ouverts par cette tranche

* **`#943-r9`** — `probe_477r24r1` / `probe_477r25` ne sont dans aucune banque, donc leur cache
  versionné dérive sans limite (927 commits mesurés) et leur `rc=6` n'arrête personne. Les
  inscrire coûte 6,9 s (chaud) / 83,1 s (froid) par passe, et ferait rougir toute PR qui touche
  un fichier balayé tant qu'elle n'a pas commité le TSV.
