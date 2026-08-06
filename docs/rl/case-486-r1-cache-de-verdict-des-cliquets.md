# #486-r1 -- LE CACHE DE VERDICT DES CLIQUETS LOCAUX

**Livre le 2026-08-06.** Les cliquets de la boucle de merge relisaient 2 947 fichiers a chaque
passage alors que la mediane par commit est de **5 fichiers touches**. On memoise la contribution
**PAR FICHIER**, sous une cle qui contient le **hash de son contenu** -- mais **seulement** pour
les cliquets dont on a **ETABLI** que le verdict est LOCAL.

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
serialisables (0b, 1,8 s) ne rachetent pas leur propre cle. **Residu `#486-r6`** : un cache A
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

Soit exactement **une ligne par appel de recolte** -- 4 pour `477r24r1`, 3 pour `477r25`. Le cache
ne porte QUE les fichiers dont le calcul est cher : le pre-filtre bon marche du cliquet
(`"slot" not in texte`, `any(cls in texte)`) reste JOUE a chaque run et n'entre pas au cache.
Tailles : 1,2 / 1,6 / 0,65 Mo pour 4 944 / 3 708 / 1 433 entrees.

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

## 5. Ce qui NE peut PAS etre cache, et qui reste le plancher

`deriver()` -> `il2cpp_metadata.locate()` coute **~14 s** dans CHACUN des deux cliquets #477.
Son verdict ne depend que du build : il **aurait** l'air cachable. Il ne l'est pas -- le cacher
dans un artefact VERSIONNE rendrait l'etage 2 **tautologique**, puisque `cliquet(table,
versionne)` confronte precisement cette derivation a l'entree versionnee `interface_slots.tsv`.
Deux artefacts censes etre independants deviendraient copiables l'un de l'autre. **Residu
`#486-r7`** : alleger `locate` (10,1 s de `tottime`, 778 `bytes.find`), ce qui ne touche a aucun
critere.

## 6. Controles livres

- **FIDELITE** -- sortie a chaud **IDENTIQUE bit pour bit** a la sortie a froid, pour les trois
  cliquets (comparaison des sorties COMPLETES, pas du seul `rc`). Corollaire de conception : le
  cache **n'imprime rien** dans le regime normal, sinon les deux sorties differeraient.
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
- **TEST OFFLINE** : `scripts/python/tests/test_486_r1_cache_verdict_offline.py`, 34 verts,
  montage 100 % jetable (`tmp_path`). Il garde la peremption, la fidelite, le contexte, le menage,
  les pannes, **et la regle** (`test_aucun_cliquet_a_verdict_GLOBAL_n_est_cache` : les quatre
  non-cachables ne doivent pas importer `verdict_cache`, chacun avec SA raison ecrite). Il fige
  aussi la LIMITE : `test_une_entree_falsifiee_de_facon_COHERENTE_est_SERVIE`.
- **CONTRE-EPREUVE DU TEST** : 7 mutants, **7 mordent**.
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
