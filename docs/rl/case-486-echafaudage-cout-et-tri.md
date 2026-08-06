# #486 — L'échafaudage : ce qu'il coûte, et ce qu'on ne sait plus trier

Mesuré le 2026-08-06. **Re-dériver ces chiffres, jamais les citer** — ils bougent à chaque
tranche. Toutes les commandes sont dans ce document.

## 1. Le coût des cliquets, et pourquoi « cacher l'AST » était le mauvais remède

    probe_477r24r1  85,7 s   SUBPROCESS + TEXTE   <- PAS d'AST
    probe_477r25    79,5 s   SUBPROCESS + TEXTE   <- PAS d'AST
    probe_273       63,9 s   AST
    probe_485       27,7 s   AST
    probe_313       21,9 s   AST + IMPORT
    probe_468        2,2 s   TEXTE
    probe_181        2,1 s   (rien)

    avec AST : 113,5 s        sans AST : 169,5 s  (59 %)

Sur la banque entière (`scripts/ratchets.ps1`), **34 des 46 entrées** utilisent `ast`
(33 directes, `probe_421` via `probe_229`). Mais dans la boucle de merge, les deux plus
chers n'en utilisent **pas** : ils balaient à la regex et résolvent chaque citation contre
la table de symboles. Un cache d'AST ne les toucherait pas d'une seconde.

## 2. Le périmètre : 0,17 % bouge, on relit 100 %

Globs `docs/rl/*.md docs/*.md scripts/python/*.py scripts/python/tests/**/*.py
engine/**/*.py frida/hooks/**/*.ts`, dérivés par `git ls-files` :

    2 947 fichiers, 52,6 Mo relus A CHAQUE PASSAGE
      probes 1355 (27,18 Mo) · docs/rl 657 (13,08) · tests 734 (10,04) · frida/hooks 192 (2,24)

    médiane par commit          5 fichiers  =  0,17 %
    union des 40 derniers     200 fichiers  =  6,8 %
    JAMAIS TOUCHÉS          2 747 fichiers  = 93,2 %

    docs/rl : 630 case-docs sur 657 FIGÉS = 11,56 Mo = 22 % du volume total, relus pour rien

Scorie au passage : `engine/**/*.py` **matche 0 fichier** (le moteur est sous
`scripts/python/engine/`). Les 437 modules sont couverts quand même, parce que le `*` d'un
pathspec git traverse les `/` — `scripts/python/*.py` rend 2 089 fichiers. Glob décoratif,
bénin ici, mais c'est le vice que `case-458` documente pour `probe_431`.

## 3. LA RÈGLE DU CACHE — locale se cache, globale JAMAIS

Un cache incrémental sur un cliquet dont le verdict est **GLOBAL** fabrique des **faux
verts**. `probe_468` détecte qu'un numéro est pris deux fois : un cache par fichier ne
verrait jamais une collision entre un fichier touché et un fichier **non** touché — c'est
littéralement la collision `#477-r43` du 2026-08-05, verte sur chacune des deux PR prise
seule.

- **LOCAL** — le verdict d'un fichier ne dépend que de son contenu (+ des entrées externes
  nommées : table de symboles, hash de build). Clé `(hash du fichier, hash du build)`.
- **GLOBAL** — le verdict dépend de la **relation** entre fichiers (unicité, bijection,
  comptage croisé, cycle d'imports). Reste entier.

La localité s'**établit**, elle ne se suppose pas. « Non cachable, voici pourquoi » est un
résultat.

### Le cache est VERSIONNÉ — sinon il ne sert jamais

⚠ **Pas dans `logs/`.** Tout agent travaille dans un **worktree frais parti de `origin/master`** :
`logs/` est gitignoré, il y naît vide et meurt avec le worktree. Un cache non versionné serait
donc toujours froid **exactement là où il doit servir** — la validation d'une PR — et ne
réchaufferait que la boucle locale de l'orchestrateur. C'est ce coût-là qu'on vise : la banque
retirée mesurait **~891 s par agent et par PR**.

⚠ **Pas dans `data/` non plus** : `data/` est réservé aux ENTRÉES (« `data/` = ce qu'on LIT »),
et `probe_273 --only-scan` étape 0c rougit à bon droit sur un chemin `data/<x>` construit qui ne
désigne pas une entrée versionnée. Le cache est un **dérivé de l'arbre source**, même famille que
`kit-coverage.md` : généré, versionné, et dont un conflit se **régénère** au lieu de se fusionner.

**Ce que le versionnement introduit, et qui doit être traité :** un cache versionné est une
**attestation qui peut mentir** — la parade est structurelle, la clé DOIT être le **hash du
contenu** (+ le hash de build là où le verdict en dépend), pour qu'une entrée périmée ne puisse
que MANQUER ; les **conflits de merge** à 6 agents ; le **churn d'historique** ; et le
**changement de build**, où tout doit manquer.

## 4. Les 825 probes : la moitié n'est jouée par rien, et on ne peut pas les distinguer

Ventilation par citation **EXÉCUTABLE** (AST du citant : `import`, ou `ast.Constant` str
contenant le stem — argv de subprocess, chemin, id de banque ; **docstrings exclues**) :

    CLIQUET (banque)      34    4,1 %
    JOUÉ PAR TEST        319   38,7 %
    JOUÉ PAR SCRIPT       40    4,8 %
    PROSE SEULE          362   43,9 %   <- nommé dans des docs, joué par RIEN
    ORPHELIN              70    8,5 %   <- nommé NULLE PART
    ---------------------------------
    RIEN NE LES JOUE     432   52,4 %

⚠ **Mention ≠ exécution.** En comptant toute mention dans `tests/`, on obtient **442** au
lieu de 319 : **123 probes** avaient l'air joués par un test et ne l'étaient pas — ils
étaient nommés dans un commentaire ou une docstring. C'est la confusion prose/exécutable que
ce dépôt traque partout ailleurs, présente dans son propre outillage.

⚠ **« Rien ne le joue » ≠ « mort ».** Un probe est par doctrine un **instrument à main**
qu'on relance pour re-dériver un chiffre. Un instrument vivant et un cadavre sont
**indiscernables de l'extérieur** : ni le nom, ni le répertoire, ni un champ ne les
séparent. Le seul discriminant est l'**exécutabilité**.

### Deux critères de tri REFUTÉS par la mesure

- **« garder ce qui est cité dans un document »** garde **742 / 825 = 89,9 %**, et n'en
  supprime que 83. Il ne coupe pas : un case-doc cite son probe **pour toujours**. La
  citation en prose enregistre l'**histoire**, pas l'**usage**.
- **« ça casserait ce qu'appellent les autres scripts »** — faux : **0** probe est cité
  exécutablement par un script sans l'être aussi ailleurs.

### Et l'écueil du discriminant d'usage

Une première tentative (« ses imports résolvent-ils ? ») a rendu **22 morts, tous faux** :
les probes posent un `sys.path.insert` puis importent un helper qui vit sous
`scripts/python/tests/engine/runner/` (`_charge_regime`, `_combat_replay`, …). Le
discriminant doit **modéliser le `sys.path` que le probe pose lui-même**.

## 5. Le nommage encode la LIGNÉE, pas l'OBJET

`probe_477r24r1_slots_interface.py` dit quel résidu l'a engendré, jamais ce qu'il refuse.
Preuve : la colonne `seul-a-voir` de `ratchets.ps1 -List` va jusqu'à **~2 000 caractères par
entrée** — elle n'existe que parce que le nom de fichier ne dit rien.

Et le numéro ne désigne pas **un** sujet : la tâche **#462** a engendré à la fois un cliquet
d'outillage (`probe_462_live_tests_status`) **et** tout un arbre de mécaniques de combat
(`test_462_r4b_*` : defender additive, neuroparasite, bond removal, crush steppable…). Un
filtre par numéro ne peut pas les trier.

## 6. L'échafaudage garde l'échafaudage

Sur les 46 entrées de la banque, **~28 gardent l'outillage** et **~18 le portage du jeu**.
**7 gardent d'autres cliquets** : `319`→`273`, `421`→couverture de `229`, `440`→périmètre de
balayage, `443r1c`→angles morts de `283`, `467r4`→contrat de `467`, `471`→tri-état de la
banque, `439`→qu'un cliquet **soit capable de rougir**.

Côté tests : **41 fichiers à la racine de `tests/`** visent l'outillage (banque `457_r5/r6/r8/r9`,
numérotation `468`, locks git `474`, pin de build `431`, identité conftest `391`, cwd des
scripts frères `464`, priorité de la banque de fond `469`, ledger `465`, adresses `475`),
contre **693** sous `tests/engine/` pour le port.

## 7. Le coût des tests offline : une poignée de fichiers, pas une lenteur diffuse

⚠ **Deux mesures PARTIELLES qui ne décrivent pas la même chose — ne pas les mélanger.** Une
passe complète le 2026-08-06 : **3 004 tests, 1 608 s**. Un fichier de poids par test du
2026-08-04 (`logs/ratchets/457-durations.json`) : **128 fichiers, 831 s**. Le dépôt en porte
**709**.

Forme du coût, d'après le second :

    208,1 s  test_380_seed_bc_patch_survival_offline.py
    175,4 s  test_additional_hits_variant_signatures_offline.py
     88,4 s  test_ability_registry_ratchet.py
     61,6 s  test_enum_ordinal_ratchet_offline.py
     61,0 s  test_431_build_pin_offline.py

    50 % du temps dans  3 fichiers (2,3 %) · 80 % dans 7 · 90 % dans 11
    98 des 128 fichiers (77 %) sont sous 1 s et pèsent 9 s A EUX TOUS

**Trois hypothèses RÉFUTÉES par la mesure** — ne pas les rouvrir :
- ce n'est **pas** le chargement d'`engine` (`import engine.runner.snapshot` = 1,24 s payé UNE
  fois, `sys.modules` met en cache ; puis 0,00 s) ;
- ce n'est **pas** le gameconfig (`GC.ability()` : 0,474 s au 1er appel, **0,000 s** au 2e) ;
- ce n'est **pas** l'absence de fixtures à portée : **485** `scope="module"` + **58**
  `scope="session"`, dans **337 des 709** fichiers (47,5 %).

**Deux mécanismes établis :**
- **(A) un balayage AST de TOUT le corpus, à l'intérieur d'un test** —
  `test_additional_hits_variant_signatures` fait `rglob("*.py")` + `ast.walk` sur l'arbre entier,
  175 s pour 6 tests. Même gisement que les cliquets (§2).
- **(B) un calcul dérivé lourd répété par test** — `test_380` : 208 s pour 9 tests, **aucun
  `subprocess`**, et une fixture `scope="module"` qui met en cache le *montage* mais pas les ~8
  appels à `check_seed_bc` dispersés dans les tests.

⚠ La contrainte : on change le **coût**, jamais le **verdict**. Contrôle exigé — la liste des
nodeids `passed` avant == après, pas seulement le `rc` (ce dépôt a déjà été mordu par le vert
vacueux et par le fichier intégralement skippé, cf. `probe_455`).

## 8. Le programme

| tranche | objet | état |
|---|---|---|
| `#486-r1` | cache de verdict `(hash fichier, hash build)` sur les cliquets **locaux** | EN VOL |
| `#486-r2` | discriminant d'**usage** correct, ventilation exhaustive, élagage des orphelins non exécutables, cliquet de garde | EN VOL |
| `#486-r3` | séparer les rôles par **répertoire** (`gardes/` = la banque · `mesures/` = les instruments), dérivable et gardé | OUVERT |
| `#486-r4` | renommer par **objet**, numéro en métadonnée — passe par `probe_468`, qui lit des positions dans `docs/rl` | OUVERT |
| `#486-r5` | le **coût des tests offline** (§7) : mesure à jour, mécanisme établi fichier par fichier, sur le haut du classement seulement | EN VOL |

Ordre contraint : **r2 avant r3/r4** — on ne renomme pas ce qu'on va supprimer.

## Re-dériver

    pwsh -File scripts/ratchets.ps1 -List           # composition de la banque
    python scripts/python/probe_468_collision_numeros.py --suggere 486
