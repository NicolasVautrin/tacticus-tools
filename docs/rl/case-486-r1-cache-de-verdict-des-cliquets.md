# #486-r1 -- LE CACHE DE VERDICT DES CLIQUETS LOCAUX

**Livre le 2026-08-06.** Les cliquets de la boucle de merge relisaient 2 947 fichiers a chaque
passage alors que la mediane par commit est de **5 fichiers touches**. On memoise la contribution
**PAR FICHIER**, sous une cle qui contient le **hash de son contenu** -- mais **seulement** pour
les cliquets dont on a **ETABLI** que le verdict est LOCAL.

## 0. Le gain, mesure

⚠ **UN CHIFFRE SANS SA CHARGE NE VEUT RIEN DIRE, et ce depot l'a mesure ailleurs** (#486-r5 :
51,3 s au classement contre 33,0 s reels, **+55 % de contention**). Les mesures ci-dessous sont
prises sur une machine **CALME** -- **1 worktree** d'agent (le mien), **0** process python demarre
dans les 5 minutes, **22** CPU logiques, charge moyenne **0 %** -- et l'arbre est celui de la PR
apres rebase sur `922fcd14`.

```
cliquet          SANS CACHE     FROID     CHAUD    gain
probe_477r24r1       26,6 s     25,9 s     2,4 s    91 %
probe_477r25         31,0 s     37,2 s     3,1 s    90 %
probe_313            13,2 s     16,0 s     4,5 s    66 %
TOTAL                70,8 s     79,1 s    10,0 s    86 %
```

Les memes cliquets, mesures **sous 11 worktrees actifs** quelques heures plus tot : 30,1 / 41,2 /
14,6 s sans cache pour 2,3 / 5,1 / 3,9 s a chaud. **Le gain relatif est stable (87 % vs 86 %) ; les
absolus bougent de ~20 %** -- c'est exactement pourquoi la charge est declaree ici.

⚠ **La colonne FROID est parfois PLUS LENTE que SANS CACHE** (37,2 contre 31,0 sur `477r25`) : le
run froid calcule *et* ecrit 6 682 entrees. Ce n'est pas du bruit, c'est le cout du premier
remplissage -- et il se paie une fois.

⚠ **Les deux premieres lignes ont d'abord plafonne a 16,1 et 19,1 s** -- le residu etant
integralement `deriver()`, declare NON cachable a tort (cf. §5, corrige sur intervention de
l'utilisateur). C'est ce second etage qui fait passer le regime normal de « moitie moins cher » a
« quelques secondes ».

⚠ La colonne SANS CACHE porte deja la LECTURE MUTUALISEE du perimetre (une seule traversee pour
les 3 a 4 recoltes de chaque cliquet, au lieu d'une par recolte) : elle n'est donc pas l'etat
d'avant la PR, elle isole le gain du CACHE SEUL. Reference du debut de session, avant toute
modification, en serie : `477r24r1` 52,6 s, `477r25` 65,7 s, `313` 20,6 s.

## 1. La regle, et pourquoi elle est la seule qui compte

**Un cache incremental sur un cliquet dont le verdict est GLOBAL fabrique des FAUX VERTS.**

| | |
|---|---|
| **LOCAL** | le verdict d'un fichier ne depend QUE de son contenu, plus d'entrees externes NOMMEES (source du cliquet, table de symboles). **Cachable.** |
| **GLOBAL** | le verdict depend de la RELATION entre fichiers -- unicite, bijection, comptage croise, cycle d'imports. **NON cachable par fichier**, et le dire est un RESULTAT. |

Cas d'ecole non hypothetique : `probe_468` detecte qu'un numero est attribue DEUX FOIS. Un cache
par fichier ne verrait jamais une collision entre un fichier TOUCHE et un fichier NON TOUCHE --
c'est litteralement la collision `#477-r43` du 2026-08-05, verte sur chacune des deux PR prise
seule.

## 2. Verdict par cliquet

| cliquet | verdict | ce qui a ete etabli |
|---|---|---|
| `probe_477r24r1` | **CACHE** | `recolter` ne lit que le texte d'UN fichier ; les variables partagees etaient des ACCUMULATEURS et la cle de dedup commence par `rel` |
| `probe_477r25` | **CACHE** | idem ; `recense` est purement ADDITIF |
| `probe_313` | **CACHE** | `intenums_du_moteur` et `references_qualifiees` : parse d'UN fichier, constantes du cliquet |
| `probe_273` | **NON CACHE** | etapes 0 / 0c : POINT FIXE sur un `modenv` PARTAGE. **Mesure : 58 fichiers sur 2 090 (2,8 %) empruntent une racine a un AUTRE module** |
| `probe_485` | **NON CACHE** | le critere CYCLE charge la cible dans un process FRAIS : le verdict depend du **sous-graphe** d'imports atteignable, pas d'un fichier |
| `probe_468` | **NON CACHE** | GLOBAL par construction (cf. ci-dessus) ; et il coute 1,5 s |
| `probe_181` | **NON CACHE** | aucun perimetre de fichiers : il croise un REGISTRE importe, verdict sur le compte GLOBAL ; 1,2 s |

### Ce que la mesure a montre pour `probe_273`, et pourquoi ce n'est pas un renoncement

Ventilation du cout, une passe, arbre chaud :

```
lecture parallele   1,7 s
parse + buckets    44,1 s   <- LOCAL par fichier, mais le produit porte des NOEUDS AST
point fixe + eval   1,6 s   <- INTER-fichiers (etapes 0 et 0c)
balayage textuel    1,8 s   <- LOCAL (etape 0b)
```

Le poste dominant (`ast.parse` + `_FileInfo`) **est** local -- mais son produit n'est pas
serialisable : `_Eval` consomme des noeuds AST, et `frags` porte des `id()` de noeuds. Le cacher
demanderait de re-implementer `_Eval` sur une representation intermediaire, c'est-a-dire de
**changer ce qui est calcule** par le cliquet qui garde l'invariant 3. Les deux etages locaux
serialisables (0b, 1,8 s) ne rachetent pas leur propre cle. **Residu `#486-r9`** : un cache A
DEPENDANCES, cle `(sha du fichier, sha des modules dont il emprunte une racine)`, qui stockerait
`envs[f]` (des `Path`, serialisables) au lieu des noeuds.

## 3. Ou vit le cache, et pourquoi il est VERSIONNE

`scripts/cliquets-cache/<cliquet>.tsv`, **versionne**.

- **PAS `logs/`** (l'idee de depart, corrigee) : tout agent part d'un worktree FRAIS ou `logs/`
  nait vide. Un cache gitignore serait **toujours froid exactement la ou il doit servir** -- il ne
  rechaufferait que la boucle locale de l'orchestrateur, jamais la validation d'une PR.
- **PAS `data/`** : reserve aux ENTREES du jeu (invariant 3), garde par `probe_273 --only-scan`
  etape 0c.
- Famille : celle de `docs/rl/kit-coverage.md` -- un artefact **GENERE et VERSIONNE**, donc
  **jamais fusionne a la main, toujours REGENERE** en cas de conflit.

## 4. Les quatre dangers du versionnement, et ce qui les ferme

### 4.1 Une attestation qui ment

La cle est le **sha256 du CONTENU LOGIQUE** (`verdict_cache.sha_texte` : le TEXTE, fins de ligne
normalisees -- `core.autocrlf` vaut `true` ici, un sha sur les octets rendrait le cache invalide
d'une plateforme a l'autre, et le cache se lirait « toujours froid »). Une entree perimee ne peut
donc que **MANQUER**, jamais mentir.

**CE QUI RESTE OUVERT, ET AUCUN CACHE NE LE FERME** : une entree **falsifiee de facon coherente**
-- verdict faux ecrit en face du hash JUSTE. Mesure, sur un fichier rendu ROUGE puis dont les 4
entrees ont recu la valeur SAINE avec le bon sha :

```
SAIN                     rc=0
MUTE (cache recalcule)   rc=1   a_mordu=True
FALSIFIEES               4 entree(s)
MUTE + cache falsifie    rc=0   << le cache MENT >>=True
--verifier-cache         rc=3   4 DIVERGENCE VALEUR FALSIFIEE ... nommees
```

La parade n'est pas dans la cle, elle est dans la **RE-VERIFICATION** : `--verifier-cache`
recalcule tout en mode ESPION (le fichier est charge, jamais servi) et confronte entree par
entree. rc **3** DEDIE -- ce n'est pas le verdict du cliquet sur le depot, c'est le cache qui ment,
et les confondre ferait corriger le code a la place de l'artefact.

⚠ **UNE ENTREE FALSIFIEE EST AUTO-PERSISTANTE, et la reparation n'est PAS un rejeu.** Le run
suivant la RELIT (le sha correspond) et la REECRIT telle quelle -- mesure. Rejouer le cliquet ne
lave donc rien : il faut `--verifier-cache` pour la NOMMER, puis **supprimer le fichier** et
regenerer. Le test offline fige ce fait.

⚠ **Toutes les entrees ne portent pas le meme risque.** Une entree de BALAYAGE falsifiee produit
un faux **VERT** (silencieux) ; une entree `deriver` falsifiee produit un faux **ROUGE** (bruyant),
parce que l'autre cote de la confrontation -- l'entree versionnee -- reste intact. Voir §5.

### 4.2 Les conflits de merge

TSV, **une ligne par (fichier, appel)**, **triee par (fichier, appel)** -- pas par le sha. Deux
agents qui touchent des fichiers differents ecrivent a des endroits differents. Le tri est
**garde par le test offline** : c'est lui qui rend le diff proportionnel aux fichiers touches.
En cas de conflit : **REGENERER** (rejouer le cliquet), jamais fusionner.

### 4.3 Le churn d'historique -- LA question qui decide si le cache survit

**13 094 lignes / 3,87 Mo versionnes en 3 fichiers.** Si toucher UN fichier en reecrivait des
milliers, le cache polluerait chaque PR et se ferait desactiver -- c'est le mecanisme social qui a
fait retirer la banque de cliquets. **MESURE, par regeneration reelle puis `git diff --stat`** :

| fichier touche (1 ligne ajoutee) | 477r24r1 | 477r25 | 313 | TOTAL | part des 13 094 |
|---|---|---|---|---|---|
| `case-100-...md` -- **SANS `slot`** (255 des `docs/rl/*.md`) | 0 | **1** | 0 | **1 ligne** | **0,008 %** |
| `wiki.md` -- 2 occurrences de `slot` | 4 | 4 | 0 | **8 lignes** | 0,06 % |
| `backlog.md` -- **307** occurrences (pire cas) | 4 | 4 | 0 | **8 lignes** | 0,06 % |

**Le churn ne depend PAS de la taille du fichier ni du nombre de citations** : il vaut **une ligne
par APPEL** qui visite ce fichier. `477r24r1` en fait 4, `477r25` 4 (dont `autre_casse`, le SEUL
qui couvre tout le perimetre -- d'ou la ligne unique du cas median), `313` 0 pour un `docs/rl/`.
La restauration ramene le cache **bit-a-bit** au commit dans les trois cas.

C'est le pre-filtre bon marche du cliquet (`"slot" not in texte`, `any(cls in texte)`) qui tient
ce chiffre : il reste JOUE a chaque run et n'entre pas au cache, donc les ~2 600 fichiers qu'il
ecarte n'ont **aucune** ligne. Tailles : **1,20 / 2,00 / 0,65 Mo** pour **4 965 / 6 682 / 1 447**
entrees.

**L'AUTRE BOUT DE L'ECHELLE, mesure au rebase de cette PR** : 12 fichiers du perimetre apportes
par `922fcd14` -> **42 insertions / 33 suppressions**, et la regeneration coute **3,4 / 6,2 /
3,3 s** au lieu du plein tarif. Un rebase plus large (490 fichiers, mesure precedente) donne
2 616 / 2 599 lignes, soit ~5,3 par fichier -- la proportionnalite tient sur deux ordres de
grandeur.

⚠ **`autre_casse` est le seul appel qui couvre TOUT le perimetre** (son pre-filtre n'existe pas :
il compte des lignes que `RE_SLOT` ne voit justement pas), d'ou +2 947 entrees sur `477r25`. C'est
le seul endroit ou la taille de l'artefact a ete arbitree contre un gain : ~13 s a chaud pour
~0,4 Mo versionne.

**L'AUTRE BOUT DE L'ECHELLE, mesure au rebase de cette PR** -- 8 commits amont, **490 fichiers du
perimetre modifies** : les trois caches bougent de **2 616 insertions / 2 599 suppressions**, soit
~5,3 lignes par fichier touche. Le cout du rejeu reste tres en dessous du froid (26,3 / 31,8 /
12,4 s contre 35,3 / 38,2 / 14,6 s sans cache) : les 2 457 fichiers non touches restent chauds.
C'est le regime pour lequel le cache est VERSIONNE.

### 4.4 Le changement de build -- et ce que devient le fichier VERSIONNE

Le contexte (en-tete du fichier) porte le sha du SOURCE du cliquet, celui d'`il2cpp_metadata.py`
**et** celui de la table de slots versionnee. Simulation d'un changement de build (la table
versionnee change, ce que produit un `--regenerer` sur un nouveau build) :

```
                    AVANT                              APRES
477r24r1   hits=4965 recalculs=0    2,1 s     hits=0 recalculs=4965   27,4 s
477r25     hits=6682 recalculs=0    2,2 s     hits=0 recalculs=6682   32,3 s
```

**100 % des entrees MANQUENT** -- `hits=0`, cout plein, une fois.

**Ce que devient le fichier : il est REECRIT EN ENTIER, et il ne porte QU'UN SEUL BUILD.**
Mesure : **1 seule en-tete `# format=`** avant comme apres, contexte passe de `b89e7785…` a
`3826032b…` (`477r24r1`) et de `b10fc11b…` a `78b82878…` (`477r25`), pour le **meme nombre
d'entrees** (4 965 / 6 682 -- c'est le contexte qui change, pas le perimetre). **Aucune entree de
l'ancien build n'est conservee** : `_charger` refuse un fichier dont le contexte differe (il ne lit
RIEN, plutot que de deviner), et `enregistrer` reecrit exactement les entrees VUES par le run. Il
n'y a donc ni empilement multi-builds, ni commande de menage a se rappeler de lancer.

Le retour au build precedent est symetrique et complet : contexte revenu a l'identique, 4 965 /
6 682 entrees. Le prix a payer est un aller-retour a plein tarif, ce qui est la contrepartie
assumee d'un fichier mono-build.

⚠ `probe_313` est **BUILD-INDEPENDANT** sur ses deux balayages caches (le build n'entre que par
`enum_natif`, hors cache) : son contexte ne porte donc pas le build. Ce n'est pas un raccourci,
c'est la mesure de ce dont ses entrees dependent reellement.

## 5. LA DERIVATION DEPUIS LE BINAIRE DU JEU -- cachee, et pourquoi ce n'est PAS tautologique

`deriver()` -> `il2cpp_metadata.locate()` coutait **~14 s** dans CHACUN des deux cliquets #477 :
c'etait le plancher, et il a d'abord ete declare **non cachable**. Ce verdict etait FAUX, et la
correction vient de l'utilisateur : *« on pourrait quand meme hasher `global-metadata.dat` et
decider s'il est encore a recroiser avec le repo »*.

**Ce que le premier verdict confondait.** Le danger reel serait de cacher l'entree VERSIONNEE et
de la comparer a elle-meme -- l'etage 2 deviendrait un miroir. Mais ce qui est memoise ici est
l'**AUTRE COTE** de la confrontation : le resultat d'une lecture reelle du binaire du jeu, sous
une cle qui contient le **hash de ce binaire** (`global-metadata.dat` + `frida/methods.tsv`).
L'entree n'est reutilisee que si la source de la derivation est **bit-a-bit identique**. Les deux
cotes restent donc INDEPENDANTS.

**Et c'est verifiable, pas seulement argumentable** : falsifier l'entree `deriver` (table tronquee
a 40 slots, hash laisse JUSTE) rend le cliquet **ROUGE** -- `[2] CLIQUET : 110 ecart(s) derivation
vs entree versionnee`, `rc=1`. Un cote falsifie DIVERGE de l'autre. **Cette famille d'entrees ne
peut donc produire qu'un faux ROUGE, bruyant -- jamais un faux VERT, silencieux.**

```
cout du hachage : 0,05 s pour 21,6 Mo   (vs ~14 s de derivation)   rapport 280:1
477r24r1  30,1 s sans cache -> 2,3 s a chaud   (-92 %)
477r25    41,2 s sans cache -> 5,1 s a chaud   (-88 %)
```

**Le tri-etat est preserve** : sans le jeu installe, `build_pin.global_metadata()` leve deja
(PAS MESURE) ; et si le hash n'est pas calculable, `sha_gros_fichiers` rend **`None`** -- on
RECALCULE au lieu de servir une attestation qu'aucune machine n'a produite ici. Mesure :
`sha_gros_fichiers(<absent>)` rend `None`, jamais une chaine.

Reste ouvert, sur un autre axe : **`#486-r10`** -- alleger `locate` lui-meme (10,1 s de `tottime`,
778 `bytes.find`). Ce n'est plus le plancher du regime normal, mais c'est encore le cout du run
FROID et de chaque changement de build.

## 6. Controles livres

- **FIDELITE** -- sur les trois cliquets, **TROIS regimes rendent la meme sortie, bit pour bit** :
  cache DESACTIVE (`TACTICUS_SANS_CACHE_CLIQUET=1`), cache FROID, cache CHAUD. Sorties COMPLETES
  comparees, pas le seul `rc`. Corollaire de conception : le cache **n'imprime rien** dans le
  regime normal, sinon les deux sorties differeraient.
  ⚠ **C'est ce controle, et lui seul, qui a trouve la faute la plus grave du chantier.** En
  cablant `_compter_autre_casse`, `probe_477r25` s'est mis a cacher DEUX FORMES de valeur (des
  citations, et un simple entier) sous UN seul encodeur : le run SANS cache passait, le run AVEC
  cache levait `TypeError`. Aucun test ne le voyait -- le contrat `encoder(valeur, appel)` est
  desormais FIGE par `test_l_encodeur_recoit_l_APPEL_et_pas_seulement_la_valeur`.
- **CONTRE-EPREUVE** -- 3 mutations sur des sites REELS ; les 3 mordent, le cache MANQUE (le sha
  stocke change), le site est NOMME, et la remise en etat restaure le vert :

  | cliquet | mutation | rc | cache |
  |---|---|---|---|
  | `477r24r1` | `backlog.md:101` `ApplyDamage` -> `ZzFaux486` | 0 -> **1** | a MANQUE |
  | `477r25` | `backlog.md:41` `IsTurnOfUnit` -> `InitLogger` (autre slot de la MEME interface) | 0 -> **1** | a MANQUE |
  | `313` | `probe_120:189` `EffectType.<X>` -> `EffectType.ZzFaux486` | 0 -> **1** | a MANQUE |

  ⚠ Une premiere mutation de `477r25` (nom absent de l'interface) **n'a pas mordu** -- et c'etait
  le MONTAGE, pas le cache : ce cliquet range un nom hors interface en **INDECIDABLE**, « ni vert
  ni rouge », par critere. Le cache avait bien MANQUE. Sur une contre-epreuve, le VERT est le
  resultat suspect : il faut trouver POURQUOI avant de conclure.
- **CONTRE-EPREUVE DE L'ETAGE `deriver`** -- trois epreuves, les trois mordent :
  **(A)** la SOURCE change (`frida/methods.tsv` mute) -> le sha passe de `2867918942357a4c` a
  `cd99ee1253c16be9`, l'entree MANQUE, et le sha revient a l'identique apres restauration ;
  **(B)** fichier ABSENT -> `sha_gros_fichiers` rend `None`, donc RECALCUL, jamais une attestation ;
  **(C)** entree FALSIFIEE de facon coherente (table tronquee a 40, sha JUSTE) -> le cliquet rend
  **ROUGE** (`110 ecart(s) derivation vs entree versionnee`, rc=1) et `--verifier-cache` la NOMME.
- **TEST OFFLINE** : `scripts/python/tests/test_486_r1_cache_verdict_offline.py`, 39 verts,
  montage 100 % jetable (`tmp_path`). Il garde la peremption, la fidelite, le contexte, le menage,
  les pannes, **et la regle** (`test_aucun_cliquet_a_verdict_GLOBAL_n_est_cache` : les quatre
  non-cachables ne doivent pas importer `verdict_cache`, chacun avec SA raison ecrite). Il fige
  aussi la LIMITE : `test_une_entree_falsifiee_de_facon_COHERENTE_est_SERVIE`.
- **CONTRE-EPREUVE DU TEST** : 9 mutants, **9 mordent**.
  ⚠ **Deux ne mordaient pas au premier passage, et la cause est instructive** : le critere
  enumerait les appels a `sha_fichiers` au lieu des **constructions de `CacheCliquet`**. Un
  cliquet en construit DEUX (le normal, l'espion), donc muter le contexte de l'un laissait
  l'autre satisfaire le `any`. Corrige une fois en passant a « un contexte par appel », le critere
  restait aveugle a la mutation qui **RETIRE** l'appel -- un critere qui n'enumere que ce qu'il
  trouve ne peut pas voir ce qui a ete retire. Enumerer les CONSTRUCTIONS ferme les deux.

## 6bis. DEUX collisions de numero dans la MEME tranche -- l'angle mort de `--suggere`, vecu

`probe_468 --suggere 486` a rendu `#486-r6` puis `#486-r7`. Les deux ont ete pris entre-temps par
d'autres agents (`#486-r3` puis `#486-r5`, mergees pendant ce chantier), et `probe_468` les a
attrapees **au re-jeu d'apres rebase**, jamais avant. Renumerotes en `#486-r9` et `#486-r10`.

Ce n'est pas une defaillance du cliquet : c'est exactement l'angle mort que sa `PORTEE DE LA
MESURE` nomme -- *un numero pris et pas encore ecrit est invisible de toute lecture de l'arbre*.
Ce qui est neuf, c'est la **frequence** : deux fois en une tranche, parce qu'un chantier long
alloue tot et livre tard. La parade praticable n'est pas de reserver (ce qui serialiserait
l'allocation) : c'est de **re-jouer `probe_468` APRES chaque rebase**, ce que cette PR a fait
deux fois -- et de ne pas s'etonner d'un rouge la.

## 7. Non couvert

- Les **runs concurrents** : deux cliquets caches lances en meme temps ecrivent des fichiers
  DIFFERENTS (un par cliquet), mais deux instances du MEME cliquet se marcheraient dessus a
  l'ecriture. Consequence bornee -- la derniere ecriture gagne, le contenu reste valide, aucun
  verdict ne bouge. Non teste.
- Le **raccourci de lecture** : les 2 947 fichiers sont LUS a chaque run (~1,8 s en parallele),
  puisqu'il faut leur contenu pour hasher. Utiliser le blob de l'index git eviterait la lecture ;
  ecarte ici (`core.autocrlf`, filtres, `assume-unchanged`) au profit d'un sha du contenu
  reellement lu. **Residu `#486-r8`**.
- `probe_273`, `probe_485`, `probe_468`, `probe_181` restent **au cout plein**, par decision
  motivee ci-dessus.
