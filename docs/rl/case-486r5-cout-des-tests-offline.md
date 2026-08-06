# #486-r5 -- Le cout des tests offline : le meme corpus, relu et reparse N fois

**Livre le 2026-08-06.** Perimetre : les fichiers de test non-`_live.py` et les helpers qu'ils
appellent. Hors perimetre par coordination : `probe_477r24r1`, `probe_477r25`, `probe_273`,
`probe_485`, `probe_313` (servis par le cache de verdict de #486-r1) et toute suppression de
probe (#486-r2).

## 1. La mesure a jour, et ce qu'elle couvre

`probe_457_offline_tests_green.py --measure`, commit `a96b3bab`, machine sous charge (4 agents) :

    218 fichiers joues -- TOUT le perimetre non-`_live.py`, derive par `git ls-files`
    3 004 tests : 1 failed, 2 999 passed, 4 skipped
    1 963 s de mur (32 min 43 s), 1 880 s de temps de test mesure

Ce que la mesure NE couvre PAS, et le dire fait partie du resultat :

* les **491** fichiers `_live.py` (ils montent un runner ; le critere de perimetre est le suffixe,
  DECLARATIF, cf. `probe_457`) ;
* **1 item** deselectionne par le filet de cloture de fixtures
  (`test_act_of_faith_crit_resets_both_paths.py`, fichier MIXTE) : il ne produit aucun report,
  donc aucun poids ;
* le **prechauffage du bytecode** (168,9 s) est un cout de la MESURE, pas de la banque.

Les deux mesures citees au lancement de la tranche ne se recouvrent pas et n'ont pas ete
melangees : le fichier de poids du 2026-08-04 pesait **128** fichiers, celui-ci en pese **218**.

### Le rouge PRE-EXISTANT, non lie a cette tranche

`tests/engine/test_270r4r2r2_differes_offline.py::test_etage3_seuil_le_compte_ne_remonte_pas`
echoue sur `a96b3bab` : **349 instructions pour un plafond de 346**. C'est un cliquet de SEUIL sur
les imports differes d'`engine/`, perimetre auquel cette tranche ne touche pas. Il echoue a
l'identique avant et apres.

## 2. Le mecanisme, etabli fichier par fichier -- pas suppose

Un seul mecanisme domine, et ce n'est aucun de ceux qu'on attendait : **le meme corpus
(`scripts/python/**`, 2 089 fichiers, 37 Mo) est LU et `ast.parse`-e plusieurs fois dans le meme
process.** Ventilation mesuree, machine chargee :

| etage | cout |
| --- | --- |
| lecture PARALLELE (`repo_read`, 16 threads) | **0,8 s** |
| lecture SERIE, 2e passe (cache OS chaud) | 3,1 s |
| decodage utf-8 + fins de ligne | 0,3 s |
| **`ast.parse` de tout le corpus** | **24 a 37 s** |
| `ast.walk` complet (3,9 M de noeuds) | 6,3 a 7,0 s |

C'est donc `ast.parse` qui pese, pas l'ouverture -- l'inverse de ce que #457-r6 avait mesure sur
son propre gisement, et la raison pour laquelle la parallelisation de la lecture (deja faite
ailleurs) ne suffisait pas ici.

**Un cache d'AST GLOBAL est refuse, sur mesure** : retenir les 2 089 arbres de ce corpus coute
**1 013 Mo** de tas Python (`tracemalloc`, valeur retenue apres `gc.collect()`). Avec quatre
agents en parallele, c'est inacceptable. Toutes les corrections livrees memoisent donc un
**RESULTAT** (quelques centaines d'octets a 180 records), jamais un arbre -- ou passent l'arbre en
ARGUMENT, auquel cas la memoire reste celle d'UN arbre.

### 2.1 `_substitution_impls` -- 3 balayages pour une seule information

`tests/test_additional_hits_variant_signatures_offline.py`. Mesure : **18 a 26 s par appel**, et
le 2e appel ne coute pas moins que le premier. Trois tests l'appelaient.
-> cache de resultat (`tuple` de `tuple`s, immuable) + lecture parallele.

### 2.2 `P380.scan()` -- 2 balayages, et trois couts parasites

`probe_380_seed_bc_patch_survival.py`. Mesure : **32 a 36 s par appel**, deux appels.
Ventilation : `ast.parse` 27,8 s, la visite `_Sweep` 10,4 s, la lecture en SERIE 3,2 s, et
`Path(__file__).resolve()` **recalcule a chaque fichier** 2,3 s.
-> cache par racine (rendu en copie profonde -- les records sont des dicts MUTABLES), lecture
parallele, `resolve()` hors boucle.

**L'hypothese de depart de la tranche est REFUTEE** : `check_seed_bc` ne coute pas ~23 s mais
**0,11 a 0,66 s**, et tous ses etages sont negligeables (`_base_seed_bc` 0,02 s, `baseline_readds`
0,00 s, `ai_utilities_from_gameconfig` 0,00 s, `deepcopy` + `refresh_ability_configs` 0,07 s).
Idem pour les montages du fichier (`write_variable_patched_seed_bc` 0,11 s, `P226.build_seed`
0,10 s, `_load_seed_bc` 0,05 s). Le cout etait ailleurs -- dans un balayage AST que l'enonce ne
mentionnait pas.

### 2.3 `test_ability_registry_ratchet` -- 2 visites, 2 lectures + 2 parses

Deux tests balaient le meme corpus pour en tirer deux listes de fautifs.
-> une seule passe qui produit LES DEUX releves, memoisee. Chaque test garde son releve, son
assertion et son message.

### 2.4 `probe_448_r3_r1_r1` -- TROIS `ast.parse` par fichier

`index()` parsait, puis `resolve_calls()` re-parsait, puis `file_symbols()` re-parsait encore --
chacun avec sa propre relecture disque.
-> l'arbre est passe en ARGUMENT ; lecture parallele. Aucun arbre n'est retenu.

### 2.5 `probe_270r4r2_import_en_premier._essayer` -- 201 modules essayes DEUX fois

`_essayer` lance **un interpreteur par module** : 0,54 s piece, 131,6 s pour les 437 modules
d'`engine/` a 8 workers. Deux fichiers de test balaient dans la MEME passe, et leurs perimetres
se recouvrent a **201 modules sur 437** (`PAQUETS_DEFAUT` est un sous-ensemble strict de
`("engine",)`) -- soit **44,1 s payes deux fois**.
-> `essayer_tous(mods, jobs)`, memoise. **La cle porte l'EMPREINTE de l'arbre `engine/`**
(chemin, mtime_ns, taille) : une source modifiee entre deux mesures invalide le cache au lieu de
rendre un verdict perime -- et perime dans le sens VERT, le seul qui ne se voit pas.

### 2.6 `probe_283._signatures_positionnelles` -- deux `ast.walk` la ou un suffit

Le premier walk ne servait qu'a construire `classe_de`. Fusionne : les `def` sont accumules puis
traites APRES la boucle, donc le resultat ne depend d'aucune hypothese sur l'ordre de parcours.
**Equivalence verifiee sur le corpus reel** : 16 appelables, ensembles IDENTIQUES ; 21,77 s ->
11,60 s.

### 2.7 `probe_457._import_graph` -- 3 appels sur l'arbre reel

`tests/test_457_r8_selection_par_diff_offline.py` l'exerce trois fois sans substitution.
-> memoise, **et FIGE** : la valeur rendue est un `dict` de `frozenset` et un `frozenset`, la ou
c'etait un `defaultdict(set)` mutable partage. Cle = empreinte des sources + domaine.

## 3. Avant / apres, en secondes ET en nodeids

Mesures en ISOLATION (meme machine, meme charge), `-rA` pour capturer les nodeids `PASSED` :

| fichier(s) | avant | apres | delta | nodeids passed |
| --- | ---: | ---: | ---: | --- |
| `test_additional_hits_variant_signatures` + `test_ability_registry_ratchet` + `test_380` | 185,4 s | **79,6 s** | -105,8 s (-57 %) | 26 == 26, DIFF AUCUNE |
| `test_448_r3_r1_r1_greffe_sans_canal` | 154,7 s | **96,5 s** | -58,2 s (-38 %) | 13 == 13, DIFF AUCUNE |
| `test_270r4r2_cycles_imports` + `test_270r4r2r2_differes` | 191,4 s | **127,9 s** | -63,5 s (-33 %) | 9 == 9 (+1 failed pre-existant, identique) |
| `test_enum_ordinal_ratchet` | 107,9 s | **84,2 s** | -23,7 s (-22 %) | 18 == 18, DIFF AUCUNE |
| `test_457_r8_selection_par_diff` | 55,7 s | **37,9 s** | -17,8 s (-32 %) | 24 == 24, DIFF AUCUNE |

Le controle est la **liste** des nodeids, pas leur compte : `Compare-Object` sur les lignes
`PASSED` rend un ensemble vide dans les cinq cas.

## 4. La garde du mecanisme -- et son propre cout, qui a failli tout annuler

`tests/test_486r5_balayages_memoises_offline.py`, 14 tests, quatre etages :

1. **le balayage VOIT encore** -- exerce sur un corpus SYNTHETIQUE dont on connait la reponse
   (un cache pose sur un balayage devenu aveugle rendrait le silence definitif) ;
2. **pas de fuite d'etat** -- valeur immuable, ou objets DISTINCTS a chaque appel : muter le
   retour du premier appel ne doit rien changer au second ;
3. **le cache MORD** -- par SUBSTITUTION du balayage (compteur d'appels), jamais par un
   chronometre ;
4. **le cache se PERIME** -- une source modifiee le fait recalculer.

⚠ **Une premiere version de cette garde coutait +150 s** : ses etages de fidelite re-balayaient le
corpus complet, soit plus que le gain qu'ils gardaient. Un cliquet qui rouvre le gisement qu'il
ferme n'est pas un cliquet. La version livree coute **2,1 s** -- les balayages sont exerces sur
des racines jetables, ce qui a demande de rendre trois d'entre eux parametrables par racine
(`_iter_py_files`, `_sources_python`, `_balayer_ciblage` ; defaut inchange).

## 5. Ce qui a ete REFUSE, et pourquoi

* **Cache d'AST global** -- 1 013 Mo mesures. Refuse.
* **Pre-filtre textuel avant `ast.parse`** (« un fichier sans `attacker_id` ne peut pas porter la
  signature du canal ») : exact en principe, mais il faudrait DERIVER l'ancre necessaire de chaque
  visiteur, et une derivation fausse retirerait des fichiers du perimetre EN SILENCE. Non fait.
* **Monter `max_workers` de 8 a 16** dans `essayer_tous` (la machine a 22 coeurs) : c'est un
  parametre d'ORCHESTRATION partage, et le pump comme le CPU le sont avec les autres agents.
  Le gain irait a l'un au prix des autres. Non fait -- residu possible.
* **`python -S -c "import X"`** pour alleger les 437 interpreteurs : cela changerait le REGIME
  d'import (site-packages absents), donc le critere. Refuse.

## 6. Ce qui reste, et ce qui n'est pas explique

Fichiers du haut du classement NON traites, avec la raison :

| fichier | poids | pourquoi |
| --- | ---: | --- |
| `test_477r25_slots_autres_interfaces` | 218,3 s | perimetre #486-r1 (cache de verdict) |
| `test_477r24r1_slots_interface` | 130,0 s | perimetre #486-r1 |
| `test_host_inputs` | 76,3 s | lance `probe_273` en subprocess -- perimetre #486-r1 |
| `test_enum_mirror_ratchet` | 34,8 s | `probe_313` -- perimetre #486-r1 |
| `test_468_collision_numeros` | 84,0 s | cout STRUCTUREL : chaque contre-epreuve monte un depot git jetable (`git init`, `worktree add`) et relance le probe en subprocess. Rien n'est repete a l'identique. |
| `test_465_ledger_validite` | 78,2 s | idem, ~75 sous-processus git ; la fixture `scope="module"` est deja posee |
| `test_431_build_pin` | 55,5 s | 5 lancements de `probe_431 --cliquet` en subprocess + un `git worktree add`. Les 3 mutations sont SEQUENTIELLES par construction (elles mutent l'arbre l'une apres l'autre). |
| `test_step_ordinal_ratchet` | 43,9 s | `probe_274.sweep_py` : UN seul balayage, lecture deja parallele, et sa double passe `_Aliases` est deliberee (les cles de dict dependent des alias deja liees). Aucune redondance a retirer. |
| `test_433r4r1r4r2r1r1_derivation_morte` | 63,0 s | **cout NON EXPLIQUE** -- fixture `scope="module"` deja posee, mecanisme non etabli. Nomme, pas optimise. |
| `test_270r4r2r2r3_gardes_du_hissage` | 51,3 s | **cout NON EXPLIQUE** -- `OM.balayer` lit en serie (gain theorique ~2,4 s seulement) et son second `ast.parse` n'est arme que si `elargi=True`, ce qu'aucun appelant ne fait. Le reste des 51,3 s n'est pas localise. |

⚠ **Les residus laisses par ce dossier sont des couts NON EXPLIQUES, pas des optimisations
identifiees.** La discipline retenue est celle du brief : un fichier dont le mecanisme n'est pas
etabli par la mesure n'est pas touche -- il est nomme.
