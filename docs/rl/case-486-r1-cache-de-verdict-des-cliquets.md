# #486-r1 -- LE CACHE DE VERDICT DES CLIQUETS LOCAUX

**Livre le 2026-08-06.** Les cliquets de la boucle de merge relisaient 2 947 fichiers a chaque
passage alors que la mediane par commit est de **5 fichiers touches**. On memoise la contribution
**PAR FICHIER**, sous une cle qui contient le **hash de son contenu** -- mais **seulement** pour
les cliquets dont on a **ETABLI** que le verdict est LOCAL.

## 0. Le gain, mesure

⚠ **La mesure est ALTERNEE, et c'est la seule qui vaille sur cette machine.** Onze worktrees
d'agents y travaillent en meme temps : une passe « avant » suivie d'une passe « apres » mesure
surtout la charge du moment (premiere tentative : `probe_273`, qui n'a AUCUN cache, passait de
50,7 s a 85,8 s). On alterne donc cache ON / cache OFF (`TACTICUS_SANS_CACHE_CLIQUET=1`) sur le
MEME arbre, et on retient le **min de 3 repetitions**.

```
cliquet          SANS CACHE   AVEC CACHE   gain
probe_477r24r1       30,1 s        2,3 s     92 %
probe_477r25         41,2 s        5,1 s     88 %
probe_313            14,6 s        3,9 s     73 %
TOTAL                85,9 s       11,3 s     87 %
```

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

### 4.3 Le churn

**MESURE, sur un commit qui touche UN fichier du perimetre** (`probe_313_enum_mirror_bijection.py`) :

```
scripts/cliquets-cache/probe_477r24r1_slots_interface.tsv       | 8 ++++----   (4 lignes)
scripts/cliquets-cache/probe_477r25_slots_autres_interfaces.tsv | 6 +++---     (3 lignes)
```

Soit exactement **une ligne par appel de recolte** -- 4 pour `477r24r1`, 3 pour `477r25` (4 depuis
que `_compter_autre_casse` est cache). Le cache ne porte QUE les fichiers dont le calcul est cher :
le pre-filtre bon marche du cliquet (`"slot" not in texte`, `any(cls in texte)`) reste JOUE a
chaque run et n'entre pas au cache. Tailles : **1,20 / 2,00 / 0,65 Mo** pour **4 957 / 6 668 /
1 438** entrees.

⚠ **`autre_casse` est le seul appel qui couvre TOUT le perimetre** (son pre-filtre n'existe pas :
il compte des lignes que `RE_SLOT` ne voit justement pas), d'ou +2 947 entrees sur `477r25`. C'est
le seul endroit ou la taille de l'artefact a ete arbitree contre un gain : ~13 s a chaud pour
~0,4 Mo versionne.

**L'AUTRE BOUT DE L'ECHELLE, mesure au rebase de cette PR** -- 8 commits amont, **490 fichiers du
perimetre modifies** : les trois caches bougent de **2 616 insertions / 2 599 suppressions**, soit
~5,3 lignes par fichier touche. Le cout du rejeu reste tres en dessous du froid (26,3 / 31,8 /
12,4 s contre 35,3 / 38,2 / 14,6 s sans cache) : les 2 457 fichiers non touches restent chauds.
C'est le regime pour lequel le cache est VERSIONNE.

### 4.4 Le changement de build

Le contexte (en-tete du fichier) porte le sha du SOURCE du cliquet **et** celui des entrees
externes qui gouvernent le calcul cache -- table de slots comprise. Simulation d'un changement de
la table versionnee :

```
477r24r1  AVANT  hits=4944 recalculs=0    APRES  hits=0 recalculs=4944   22,5 s -> 48,2 s
477r25    AVANT  hits=3708 recalculs=0    APRES  hits=0 recalculs=3708   30,3 s -> 64,5 s
```

**100 % des entrees manquent**, cout plein une fois. Il n'y a pas d'entrees multi-builds : un
contexte different vide le fichier, et la reecriture integrale fait le menage.

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

Reste ouvert, sur un autre axe : **`#486-r7`** -- alleger `locate` lui-meme (10,1 s de `tottime`,
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
