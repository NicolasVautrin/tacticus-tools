# #486-r36 — le coût de `--mesurer` : mesuré, puis divisé — et trois rouges qu'il masquait

**Verdict : `probe_486r12_declencheurs.py --mesurer` passe de 1 180 s à 265 s de mur (× 4,45)
sans qu'aucune empreinte change, le mode incrémental ramène le geste courant à une entrée, et
le `rc=1` non diagnostiqué était un VRAI rouge — trois cliquets lisent hors de leur périmètre
déclaré. Deux crans de plus ont été trouvés *en mesurant* : huit entrées se déclaraient
confrontées sans rien confronter, et l'empreinte versionnée dépendait de l'état local de la
machine.**

## 1. La distribution, d'abord — c'est elle qui décide, pas l'intuition

Le chrono existait depuis le premier jour (`t0 = time.time()` autour du `subprocess.run`) et
n'atterrissait **nulle part**. Personne ne pouvait donc dire où passaient les ~20 min, et les
deux accélérations possibles répondent à des distributions **opposées** : concentrée, seul
l'incrémental paye ; plate, seul le parallélisme paye.

`scripts/ratchets-457-durations.json` ne couvrait pas ce gisement — il porte des **fichiers de
test**, et son intersection avec les ids de banque est **vide**.

Mesure du 2026-08-10, **49 entrées**, 37 scripts, régime `serie`
(`scripts/declencheurs-durees.json`, désormais versionné) :

| | |
|---|---|
| total | **1 180,4 s** |
| médiane | 11,4 s |
| min / max | 0,8 s / 125,5 s |

| rang | entrée | coût | part | cumul |
|---|---|---|---|---|
| 1 | `probe_486r2` | 125,5 s | 10,6 % | 10,6 % |
| 2 | `probe_319` | 122,9 s | 10,4 % | 21,0 % |
| 3 | `probe_273` | 80,8 s | 6,8 % | 27,9 % |
| 4 | `probe_283:prose` | 76,7 s | 6,5 % | 34,4 % |
| 5 | `probe_455` | 76,6 s | 6,5 % | 40,9 % |

**La distribution est PLATE** : les cinq plus lourdes pèsent 482,4 s sur 1 180,4 s. Il n'y a
donc pas de « une entrée fait les 15 minutes » — les deux accélérations sont justifiées, et
elles ne se remplacent pas.

## 2. Le parallélisme — et pourquoi ce n'était pas un pari

`scripts/ratchets.ps1` joue **déjà** cette même banque en parallèle (`-ThrottleLimit 0` =
`min(nb de cliquets, nb de cœurs)`), et sa documentation en donne la raison : les cliquets sont
100 % **offline** — aucun runner, aucun RPC, aucune session Frida — donc le plafond de 4 du
`CLAUDE.md`, qui borne ce qui **monte un runner**, ne les concerne pas. Vérifié plutôt que cité :
aucun script de la banque n'importe `rl_duel` ni ne parle au host ; les seules lectures du host
passent par `host_inputs`, dont c'est précisément le rôle tri-état.

Mesure, `--jobs 16` sur 22 cœurs, **avec d'autres agents actifs** (donc borne haute) :

| | série | `--jobs 16` |
|---|---|---|
| mur | 1 180 s | **265 s** (× 4,45) |
| somme CPU | 1 180 s | 2 460 s (contention × 2,08) |

⚠ **Une durée `para-N` n'est pas un coût.** Elle porte la contention de ses voisines : le régime
est écrit **avec** chaque durée, et une distribution ne se dérive que d'une passe `serie`. Sans
ce champ, une passe parallèle ferait conclure à une régression là où seul le throttle a changé.

**Ce que le parallélisme ne perturbe pas**, et pourquoi : chaque entrée a son propre dossier de
trace (`TACTICUS_DECLENCHEUR_TRACE`), chaque process y écrit un fichier à **son** pid, et le
`sitecustomize.py` de propagation est écrit **une fois**, avant le pool. Le seul cliquet de la
banque qui écrive dans l'arbre (`probe_313`, son cache de verdicts) n'a qu'**une** entrée : deux
entrées ne peuvent pas s'écraser.

**Contre-épreuve exigée** : les empreintes série et parallèle ont été comparées **entrée par
entrée** (`sha`/`ferm`/`nproc`/`proc` + groupes lus, comptes et témoins). **Aucun écart** —
sauf un, qui n'était pas dû au parallélisme et qui est devenu le § 5.

## 3. L'incrémental — et le piège qu'il fallait fermer AVANT

Le piège est réel : `sha_source` hachait **le seul fichier du cliquet**. Un helper partagé qui
change — `declencheur_trace` qui se met à lire une table, un module `engine/` qui ajoute un
import — ne périmait **rien**, et l'étage 2 servait une empreinte dont le périmètre réel avait pu
bouger. Un incrémental posé là-dessus aurait fabriqué exactement le faux vert que ce cliquet
existe pour attraper.

La clé de fraîcheur (`cle_fraicheur`, **foyer unique**) porte donc **trois** composantes, et
chacune ferme un trou mesuré :

1. le **source** du cliquet — d'origine ;
2. sa **fermeture d'imports** — `declencheur_cliquet.Fermeture`, déjà dérivée ici pour la
   cascade de harnais, et qui prend **tous** les imports, y compris ceux écrits dans un corps de
   fonction (une sous-approximation dans un critère de fraîcheur est un faux vert, exactement
   comme dans un critère de couverture) ;
3. l'**instrument** de mesure (§ 5).

**Le point d'architecture** : `--incremental` ne décide de rien par lui-même. Il appelle
`est_perimee`, **le même critère** que l'étage 2 utilise pour refuser de servir une empreinte.
Le mode rapide re-mesure donc *exactement* ce que l'étage 2 aurait de toute façon rejeté — par
construction, il ne peut pas changer un verdict. Un mode rapide qui déciderait par un critère à
lui (un âge, un diff, une liste) pourrait servir ce que le garde aurait rejeté : le `rc` passerait
de 99 à 0 **par le fait d'avoir sauté des entrées**, ce que le tri-état interdit.

**Une entrée sautée reste attestée par SON empreinte, donc CONFRONTÉE** — jamais supposée verte.
C'est exécutable : `test_une_entree_SAUTEE_reste_CONFRONTEE_donc_un_99_ne_devient_pas_un_0` sert
une empreinte fraîche portant une lecture hors périmètre, et exige le rouge.

### Ce que la péremption ne couvre pas, et qui est DIT plutôt que tu

* un fichier de **données** dont le contenu dirige les lectures (une table qui liste des chemins
  à ouvrir) : il change sans que le source, la fermeture ni l'instrument ne bougent ;
* un fichier **ajouté** à l'arbre qu'un cliquet balayeur lirait alors qu'aucun glob déclaré ne le
  couvre.

Les deux sont des trous de la **péremption**, pas de la mesure : `--mesurer` sans
`--incremental` les dissout, et c'est pourquoi il reste la référence. Un critère « manifeste de
l'arbre » les fermerait — et périmerait presque toutes les entrées à chaque PR, c'est-à-dire un
`rc=99` permanent : la forme la plus sûrement désarmée d'un garde-fou.

## 4. Le `rc=1` était un VRAI rouge — trois déclencheurs trop étroits

Il n'avait jamais été diagnostiqué (le filtre de la tranche précédente avait jeté la sortie).
Il nomme trois cliquets qui **lisent hors de leur périmètre déclaré** :

| entrée | lu hors périmètre | par quel chemin |
|---|---|---|
| `probe_120` | `frida/hooks/data/ability-names.ts` | `gameconfig.py` parse cette map pour résoudre les ids d'`ActiveAbilityType` |
| `probe_467` | `scripts/ratchets-457-footprints.json` | `loop_status` en dérive l'état du harnais |
| `probe_485r1r1_acces` | `data/seed-bc.json` | il **importe** réellement les modules qu'il résout, donc il hérite de ce qu'ils lisent au chargement |

Les trois sont **élargis** (jamais la mesure rétrécie). Le cas `probe_467` mérite d'être cité :
sa raison affirmait mot pour mot « **aucun autre fichier de l'arbre n'est lu** ». C'est la
démonstration de l'étage 2 — croire le source du déclarant revient à lui demander de
s'auto-attester.

## 5. Deux crans trouvés EN MESURANT, que personne ne cherchait

### (a) Une mesure peut être un REFUS, et le refus avait l'air d'une mesure

Les **huit** shards `probe_457:s*` rendaient `rc=99` en ~1,2 s : `probe_457` **refuse** de courir
sans `TACTICUS_ALLOW_RATCHETS=1` (garde anti-réflexe posée le 2026-08-06, un run complet coûtant
~1 425 s). Leur empreinte portait donc **5 lectures** — son propre source et ses imports
immédiats — que n'importe quel glob couvre : **8 des 49 entrées se comptaient CONFRONTÉES sans
avoir rien confronté**.

Le garde `nproc == 0` est structurellement aveugle à ça : le process a bel et bien tourné et
tracé. **Il a tracé son refus.** Le `rc` entre donc dans l'empreinte, et les codes qui *disent*
n'avoir rien mesuré (64 usage, 99 indisponible, timeout) rendent l'entrée **NON MESURÉE** — pas
rouge : ce n'est pas un verdict sur sa déclaration.

La sortie est dans l'environnement de **l'appelant** (`mesurer` hérite de `os.environ`) :
`$env:TACTICUS_ALLOW_RATCHETS=1` les mesure pour de vrai. On ne pose pas la variable d'office —
ce serait décider à sa place de jouer ~1 425 s de tests, exactement ce que le refus empêche.

### (b) L'empreinte versionnée dépendait de l'état LOCAL de la machine

Le seul écart entre les passes série et parallèle : `probe_283:on` et `probe_283:prose`
portaient le groupe `scripts/python/.pytest_cache/*.md` dans l'une et pas dans l'autre. Ce
fichier est **écrit par pytest** et **gitignoré** (par le `.gitignore` que pytest dépose
lui-même) : il n'existe que si quelqu'un a joué une passe dans ce répertoire.

Une empreinte versionnée qui en dépend varie d'une machine à l'autre — et si le déclencheur ne
couvrait pas `.md`, elle produirait un **faux rouge** irreproductible. C'est le même vice que
`source_de` corrige déjà pour `__pycache__` (#464-r2), sur un autre répertoire de cache. Les
répertoires de cache sont désormais reconnus **à n'importe quel niveau** — `_EXCLUS` ne testait
qu'un préfixe, donc il ne voyait même pas `frida/node_modules/`.

⚠ `__pycache__` n'est **pas** dans cette liste et ne doit pas y être : il est *ramené à sa
source*, donc l'exclure ferait disparaître du périmètre tout module importé — précisément ce que
la fermeture d'imports doit voir.

### (c) Et c'est (b) qui a imposé la troisième composante de la clé

Ajouter `.pytest_cache` aux exclusions a changé deux groupes de l'empreinte **sans périmer une
seule entrée** : ni le source d'un cliquet ni sa fermeture ne bougeaient, et `--incremental` les
aurait servies telles quelles. L'instrument n'est importé par **aucun** cliquet — aucune
fermeture ne le porte. D'où une composante à part, `sha_instrument()`.

## 6. Ce qui reste ouvert

* **Le plancher.** À `--jobs 16`, le mur est borné par l'entrée la plus lourde (~125 s isolée,
  ~204 s sous contention). On ne descendra pas sous cet ordre de grandeur sans changer ce que
  fait `probe_486r2` ou `probe_319` — ce sont deux balayeurs qui *lancent* d'autres probes. La
  bonne réponse à ce plancher est l'incrémental, pas plus de workers.
* **Les 8 shards `probe_457`** restent NON MESURÉS tant que l'appelant ne pose pas la variable —
  et le probe le **dit** à chaque passe. Résidu ouvert.
* **Les deux trous de péremption** du § 3, nommés et non fermés.
