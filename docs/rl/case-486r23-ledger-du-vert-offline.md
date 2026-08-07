# #486-r23 -- le VERT offline se VERSIONNE, et le `0,21 %` qui l'avait de-oblige mesurait son EFFICACITE

## 1. Le biais du survivant applique a un garde-fou

Le 2026-08-05, `d82ec527` retire la banque de cliquets de `CLAUDE.md` (-153 lignes) et du skill
d'orchestration (-60). L'argument est une mesure : sur les 67 runs de `logs/ratchets-bg`,
**2 437 lignes de cliquet lues, 5 non nulles -- 0,21 %**, dont deux faux rouges documentes.
Conclusion ecrite alors : « ce sont des prises de FONDATION, pas de GARDE ».

**Cette conclusion est refutee par le resultat.** De-oblige le 05, la suite offline portait
**14-15 echecs** le 07 -- **7 confirmes sur 5 fichiers en 101 s**. Onze fichiers rouges en 48 h.

Le vice a un nom : **biais du survivant applique a un garde-fou**. `0,21 %` de lignes non nulles
ne mesure pas l'inutilite du cliquet, ca mesure son **EFFICACITE** -- un garde qui tient une
propriete ne se voit jamais rougir, precisement parce qu'il empeche la derive qu'il garderait.
L'argument aurait ete **identique, au chiffre pres, pour n'importe quel garde qui fonctionne** :
c'est ce qui le disqualifie comme critere. Un taux de declenchement bas est compatible avec les
deux hypotheses opposees (« inutile » / « efficace ») ; il ne les separe pas, donc il ne conclut
rien.

**Ce qui SEPARE les deux hypotheses est une contre-epreuve, pas un ratio** : retirer le garde et
mesurer la derive. Elle a eu lieu par accident, et elle a tranche en 48 h.

⚠ Ne jamais re-de-obliger un garde sur son taux de declenchement. Le critere valable est le
**COUT**, confronte au **cout de la derive qu'il empeche** -- et c'est cette confrontation-la que
la presente tranche instruit, chiffres a l'appui.

⚠ Corollaire, et c'est ce qui distingue `probe_457` des 45 autres cliquets : **la refutation ne
vaut que pour lui**. Il pese 67 % de la banque et c'est LUI qui a laisse passer les 14 rouges,
parce qu'il n'est pas un cliquet de gisement mais un **lanceur de suite de tests**. Les 32
cliquets de gisement n'ont pas tire une seule fois en 67 runs, et rien ici ne dit ce que vaut
leur de-obligation. **Aucun d'eux n'est retabli par cette tranche.**

## 2. Ce que coute l'etape de PR -- en SECONDES, jamais en pourcentage de fichiers

Le pourcentage de fichiers selectionnes est un indicateur **trompeur** : le cout n'est pas
proportionnel au compte.

Mesure du 2026-08-07 sur `c46bb3cd`, `probe_457 --since HEAD~1`, MONO-SHARD, worktree d'agent :

| grandeur | valeur |
| --- | --- |
| diff | **1 chemin** (`docs/rl/backlog.md`) -- la PR la plus petite possible |
| fichiers retenus | 10 / 236 |
| tests joues | 248 |
| **mur total** | **550,8 s** |
| dont pytest | 476,4 s |
| dont selection (graphe d'imports) | **~40 s** |

Une **PR purement documentaire** paie donc **550,8 s** en mono-shard. La borne basse par les
poids (`logs/ratchets/457-durations.json`, 230,9 s en serie) **sous-estime d'un facteur 2,4** :
les poids chronometrent l'EXECUTION des tests, pas l'import ni la collecte.

Distribution de la selection sur les 20 derniers commits de `master` (empreinte de `c46bb3cd`) :
**min 5, mediane 25, max 236 fichiers**, et **5 commits sur 20 rejouent TOUT**. Quatre de ces
cinq TOUT-rejeux ont la meme cause, auto-infligee : `scripts/ratchets-457-footprints.json` est
une **lecture GLOBALE** de l'empreinte, donc **toute PR qui met a jour l'empreinte declenche un
rejeu complet** -- c'est-a-dire exactement ce que prescrit la consigne « si tu ajoutes un test
offline, mesure son empreinte et commite le JSON ».

## 3. La cause du PLANCHER : pourquoi un diff `docs/` tire dix fichiers

Ventilation des 10 fichiers retenus par le diff `docs/rl/backlog.md` seul (motif exact, pas
l'agregat) :

| fichier | cause | motif |
| --- | --- | --- |
| `test_366_r1_grapnel_launcher_cast_offline.py` | **graphe/incertain** | import non resolu |
| `test_381r1_movable_tiles_pool_offline.py` | **graphe/incertain** | import non resolu |
| `test_270r1r1r3_role_enum_offline.py` | **graphe/incertain** | import non resolu |
| `test_270r4_role_enum_offline.py` | **graphe/incertain** | import non resolu |
| `test_477r24_phase_attribution_offline.py` | hors .py | empreinte lit `docs/rl` |
| `test_477r24r1_slots_interface_offline.py` | hors .py | empreinte lit `docs/rl` |
| `test_477r25_slots_autres_interfaces_offline.py` | hors .py | empreinte lit `docs/rl` |
| `test_337_dsl_triggers_attestation_offline.py` | hors .py | empreinte lit `docs/rl` |
| `test_480r8_rpc_joignable_offline.py` | hors .py | empreinte lit `docs/rl` |
| `test_468_collision_numeros_offline.py` | declare | `DECLENCHEUR` couvre `docs/rl/backlog.md` |

**Aucun des dix n'est une declaration trop large.** Le soupcon porte sur
`test_366_r1_grapnel_launcher_cast` et `test_381r1_movable_tiles_pool` -- ils ne dependent PAS de
`backlog.md`, et la mesure le confirme : ils sont retenus par une voie qui **ne regarde pas le
diff du tout**.

**DEUX causes structurelles, et une seule legitime :**

1. **`incertains` du graphe d'imports -- retenu INDEPENDAMMENT du diff.**
   `impacted_files` fait `if abs_rel in touches or abs_rel in incertains`. Or `incertains` est
   construit par `_calculer_import_graph` sur trois criteres qui ne dependent que du FICHIER :
   import relatif (`n.level`), appel dynamique (`import_module`/`__import__`/`load_module`/
   `exec_module`), ou source illisible. **Un fichier `incertain` est donc rejoue a CHAQUE PR,
   quel que soit le diff** -- y compris un diff vide de tout `.py`. C'est un plancher constant,
   invisible, que le rapport de causes agrege sous le mot « graphe ».

2. **La granularite REPERTOIRE des dependances hors-`.py`.** L'empreinte stocke des
   REPERTOIRES (`par_test[rel]["dirs"]`), pas des fichiers. Un test qui lit UNE case-doc de
   `docs/rl` est enregistre comme dependant de **tout `docs/rl`** (~800 fichiers). Comme presque
   toute PR de ce depot touche `docs/rl` (backlog + case-doc), **ces tests rejouent sur presque
   toute PR**. C'est cette voie qui apporte les fichiers LOURDS (`test_477r24r1` 40,9 s,
   `test_480r8` 38,3 s, `test_477r25` 31,8 s).

Legitime, en revanche : `test_468_collision_numeros_offline` **declare** `docs/rl/backlog.md`
parce que c'est l'allocateur de numeros et qu'il lit le backlog par construction. Il est aussi le
plus lourd (**82,5 s**), donc il fixe a lui seul le plancher du mur shardé.

## 4. Le LEDGER VERSIONNE du vert offline

`scripts/ratchets-457-vert-offline.json`, foyer `scripts/python/ledger_vert_offline.py`.

Trois artefacts, et il faut distinguer ce que chacun sait :

| artefact | sait | ne sait pas | versionne |
| --- | --- | --- | --- |
| empreinte `ratchets-457-footprints.json` | de quoi un test DEPEND (`dirs`, `temoins`) | s'il est PASSE | oui |
| poids `logs/ratchets/457-durations.json` | combien il prend | tout le reste | **non** (gitignore) |
| ledger `ratchets-457-vert-offline.json` | qu'il est PASSE, quand, a quel cout, avec quel bilan | -- | **oui** |

Le ledger porte la **signature du ledger live** `ratchets-462-live-attestations.json` (`_at`,
`_blob`, `_commit`, `verdict`, `sec`, et le bilan ventile `passed/failed/error/skipped/xfailed`
+ `messages`). Le bilan n'est pas decoratif : c'est lui qui rend possible le garde **#455**
(`passed == 0 and skipped > 0` est un vert qui ment) -- un champ `verdict` seul ne saurait pas le
voir. Le `sec`, lui, est le POIDS, et **versionne** cette fois : le fichier de poids etant
gitignore, un worktree d'agent n'en a JAMAIS, ce qui est la cause exacte du bug de
`--measure-missing` (235/235 fichiers retenus au lieu de 1).

### La semantique du ledger LIVE ne se recopie pas -- elle s'INVERSE

`probe_462.verdict_effectif` rend **VERT TEL QUEL, sans aucune condition sur le commit** (son
« trou B », ouvert et assume). C'est defendable la-bas : ce ledger sert a **BLOQUER** sur les
rouges, donc la peremption n'y touche que le RECIT d'un non-vert.

Ici, un vert sert a **SAUTER un test**. Un vert perime n'y est pas conservateur : c'est le FAUX
VERT que **#465** nomme comme le mode de defaillance a interdire, et il est **silencieux par
construction** -- le test n'est pas joue, donc rien ne le signale. Recopier l'asymetrie de
`probe_462` aurait produit un ledger permissif sans qu'aucun test ne rougisse.

### La regle de composition : quand un vert reste valable

`raison_de_rejeu` est le **foyer unique**. `None` = le vert tient. Sinon, une chaine qui dit
pourquoi. Six chemins, et aucun autre :

1. pas d'entree -> **jamais joue** ;
2. `verdict != VERT` (y compris `VIDE` du garde #455 et `SETUP`) ;
3. entree sans `_blob`, ou **blob courant non mesurable** (git muet -> PAS MESURE, jamais
   rabattu sur « blob egal ») ;
4. `_blob != blob COURANT DU WORKTREE` (`git hash-object`, **pas** `git ls-files -s` qui lirait
   l'INDEX et serait aveugle a une edition non commitee) ;
5. aucune ancre lisible (les deux mortes) ;
6. le fichier est **IMPACTE** par le diff `ancre..HEAD` au sens exact de
   `probe_457.impacted_files` -- empreinte, graphe d'imports, `DECLENCHEUR` et lectures globales
   ensemble.

Le point 6 **est** la composition : l'empreinte repond a « de quoi depend-il », le ledger a
« quand etait-il vert ». Ni l'un ni l'autre ne conclut seul. C'est aussi ce qui repare le defaut
mesure par #465, ou la cle etait le **blob du fichier de test SEUL** alors qu'un verdict depend du
depot entier (les trois rouges du ledger live etaient PERIMES, 2026-08-04).

Contre-epreuve : `scripts/python/tests/test_486r23_ledger_vert_offline.py`, qui balaie **576
combinaisons** (verdict x ancres ecrites x ancre effective x blob de l'entree x blob courant x
impact) et exige **UNE seule forme passante**. Il **assertionne son propre non-vide** -- un
cartesien vide passerait pour vert sans rien eprouver (#270-r1-r1-r3).

### DEUX ancres, et c'est une mesure qui l'a impose

Premiere conception : une seule ancre, la **base** (`git merge-base HEAD origin/master`), choisie
parce qu'elle survit au squash-merge qui tue la branche d'agent -- defaut exact repare par
#486-r15 sur le `_commit` global de l'empreinte.

Mesure du 2026-08-07, ledger COMPLET simule (237 entrees VERT au blob courant) :

| regime | fichiers retenus | cout serie |
| --- | --- | --- |
| `--since <base>` seul | 33 / 237 | 494 s |
| `--depuis-ledger`, ancre = base seule | **33 / 237** | **494 s** |

**Identique.** C'est structurel, pas un hasard : si toutes les attestations portent la base de la
PR, la question posee au ledger EST celle que `--since` pose deja. Le ledger n'apportait alors que
de la SURETE (il attrape les rouges et les jamais-attestes), **zero economie**.

D'ou les deux ancres :

- `_depuis` = **HEAD reel** -- PRECISE. C'est elle qui fait gagner : entre deux passes d'une meme
  tranche, le diff `HEAD_precedent..HEAD` ne porte que ce que l'agent vient de changer. Elle MEURT
  au squash-merge.
- `_base` = **merge-base** -- SURVIVANTE, mais grossiere.

`ancre_effective` prend **la plus precise qui soit CONNUE de git**. La degradation est SURE dans
les deux sens : une ancre plus ancienne allonge le diff, donc **sur**-selectionne. On perd du mur,
jamais de la surete.

## 4bis. CE QUE LE LEDGER ECONOMISE -- mesure, par REGIME de diff

Passe REELLE mono-shard du 2026-08-07 : **3 366 tests, 16 failed, 1 795 s de mur**, ledger ecrit
avec **237 entrees / 224 VERT / 13 non-VERT**, ancres `_depuis=416e4229`, `_base=c46bb3cd`. Les
`sec` ci-dessous viennent de ce ledger -- donc **versionnes**, mesures par cette passe.

| regime de diff | fichiers retenus | cout |
| --- | --- | --- |
| perimetre complet, sans ledger | 237 | **1 636 s** |
| diff VIDE (rien n'a bouge depuis l'attestation) | **13** | **509 s** |
| diff DOC seul (`docs/rl/backlog.md`) | 21 | 758 s |
| diff **1 `.py` de probe isole** | 30 | 703 s |
| diff **1 `.py` du moteur** (`engine/utilities/tile.py`) | **199** | **1 198 s** |

**Un chiffre unique serait trompeur** : l'economie va de **69 %** (diff vide) a **27 %** (un
module moteur). Et les 13 retenus du regime nominal sont **exactement les 13 fichiers rouges** --
le ledger ne saute que du vert.

### Coup IRREDUCTIBLE contre coup FABRIQUE

Ventilation d'`impacted_files` sur un diff d'UN SEUL `.py` :

| diff | total impactes | par `DECLENCHEUR` | par le GRAPHE d'imports |
| --- | --- | --- | --- |
| `engine/utilities/tile.py` | 196 | **16** (232 s) | **180** |
| `probe_291_summon_activation.py` | 19 | **15** (232 s) | 4 |

Les **180** du module moteur sont **legitimes** : `tile.py` est reellement importe par ces
tests. Les **15-16 declares**, eux, sont les **mêmes a chaque fois, pour 232 s**, parce qu'ils
portent un glob couvrant tout le Python (`scripts/python/**/*.py`, `*`, `**`...). C'est un
**plancher FABRIQUE**, paye par TOUTE PR qui touche le moindre `.py`, et il ne depend pas du
contenu du diff.

⚠ Ce recensement est celui du volet OFFLINE. `#486-r24` mesure le gisement complet : **43 des 52
fichiers declarants (83 %) portent un glob universel, dont 25 tests LIVE** -- qui ne sont pas dans
les `sec` ci-dessus. **232 s est donc une borne BASSE, et de loin.** La cause est dans l'outil :
`probe_486r15` ne rougit que sur le TROP ETROIT, donc une declaration fine rougit au premier
import ajoute tandis qu'un glob universel est vert pour toujours -- le cliquet recompense ce
qu'il est cense empecher. Sweep hors de cette tranche.

⚠ **Consequence pour le ledger** : sa cle DELEGUE l'impact a `impacted_files`, donc elle **herite
de la largeur des declarations**. Un test qui declare « tout le Python » voit son entree invalidee
par n'importe quel commit Python -- **zero reutilisation**, ce que le ledger existe precisement
pour eviter. Le ledger ne CREE pas ce defaut et n'en depend pas structurellement (il ne stocke
aucun glob) ; il en herite tant que `#486-r24` n'est pas fait, et il en beneficiera
automatiquement une fois fait.

## 5. La CONCURRENCE -- mesuree, pas supposee

Cinq a six agents produisent des verts en parallele, chacun dans son worktree. Mesure par
`git merge-tree` sur un depot jetable (236 entrees ; 10 communes -- le plancher du paragraphe 3 --
et 8 propres par agent) :

| forme du fichier | agents DISJOINTS | agents avec entrees COMMUNES |
| --- | --- | --- |
| A. JSON indente (~12 lignes/entree) | pas de conflit | conflit, **1 hunk global** |
| B. une LIGNE par entree *(retenue)* | conflit (proximite) | conflit, 1 hunk |
| C. un FICHIER par entree | pas de conflit | conflit, **10** (un par entree disputee) |

**Le conflit sur les entrees communes est INTRINSEQUE** : deux agents attestent le meme test sur
des arbres DIFFERENTS, donc ce sont deux affirmations distinctes. Aucune forme ne l'evite.

Ce qui differe, c'est la **granularite** et donc ce qu'on perd en resolvant. La forme A perd tout
un hunk illisible. La forme C est la plus precise mais met 236 fichiers dans l'arbre. La forme B
localise le conflit a la ligne, donc a l'entree -- au prix d'une collision par **proximite** (une
entree = une ligne, et git prend 3 lignes de contexte, donc trois entrees voisines).

### La regle de resolution : en conflit, on SUPPRIME l'entree

`resoudre_conflit` abandonne **les deux cotes** d'un hunk conflictuel et rend les entrees hors
conflit. Mesure sur le scenario ci-dessus :

- **221 / 236 entrees retenues** ;
- **15 abandonnees** : les **10 reellement disputees** + **5 emportees par la proximite** ;
- cout = le rejeu de ces 15 fichiers. **Jamais un faux vert.**

**Pourquoi ce n'est PAS la faute que la doctrine interdit** (« un doc genere se REGENERE, il ne se
fusionne pas ») : sur un doc genere, un etat hybride MENT -- il affiche des comptes qui ne
correspondent a aucune generation. Ici, **toute perte est SURE** : une entree absente est lue
« jamais joue », donc le fichier REJOUE. La validite est reverifiee **a la lecture**, contre le
depot, et n'est jamais presumee du fait qu'une ligne existe. Une ligne abimee par une fusion est
d'ailleurs ecartee seule, sans faire tomber les 235 autres.

C'est aussi pourquoi on sur-abandonne (les cles presentes d'un seul cote du hunk partent aussi) :
git ne dit pas QUELLES lignes se contredisent ; sur-abandonner coute du mur, sous-abandonner
ferait survivre une entree que personne n'a ecrite telle quelle.

## 6. Ce qui BLOQUE la mise en service -- criteres verifiables

Aucune obligation n'est cablee par cette tranche : ni `CLAUDE.md`, ni le skill d'orchestration, ni
hook, ni cliquet. Voici ce qu'il faudrait mesurer AVANT de le faire.

### B1. Les GLOBALES sont comparees au REPERTOIRE -- le ledger s'auto-invalide

`impacted_files` compare tout changement hors-`.py` aux **repertoires** des lectures globales :

```
_globales : data/seed-bc.json, data/symbols/CURRENT, scripts/python/pytest.ini,
            scripts/ratchets-486r15-dette-declencheurs.txt
repertoires impliques : data, data/symbols, scripts, scripts/python
```

Donc **tout fichier hors-`.py` modifie sous `scripts/` ou `data/` declenche TOUT REJOUE**. Or
l'empreinte ET le ledger vivent sous `scripts/`. Consequences mesurees :

- sur les 20 derniers commits de `master`, **5 rejouent TOUT**, dont **4** par cette voie
  (`scripts/ratchets-457-footprints.json`) ;
- le ledger, ecrit sous `scripts/`, **invaliderait sa propre selection a chaque ecriture**.

**Critere de levee** : sur les 20 derniers commits de `master`, `impacted_files` rend
`TOUT rejoue` pour cause de lecture globale **0 fois** (contre 4 aujourd'hui). La piste est de
comparer les globales au **FICHIER** et non a son repertoire -- non faite ici : elle touche le
foyer de #486-r15 et c'est une decision de politique de selection, pas une correction locale.

**DEMONSTRATION, faite le 2026-08-07** -- l'economie du §4bis est annulee par le seul fait de
COMMITER le ledger :

| moment | `--depuis-ledger` |
| --- | --- |
| ledger ecrit, **pas encore commite** | **13 / 237** |
| ledger **commite** (aucun autre changement) | **237 / 237** |

Raison rendue par l'outil : `changement dans une lecture GLOBALE
(scripts/ratchets-457-vert-offline.json) -- TOUT rejoue`. Le meme diff, prive de ce seul chemin,
rend `aucun fichier change`. C'est bien le repertoire `scripts` qui declenche, pas le contenu :
**le ledger s'auto-invalide a chaque ecriture**, et c'est ce qui rend B1 bloquant plutot que
seulement couteux.

### B2. Le plancher des `incertains` -- rejeu inconditionnel

`impacted_files` retient tout fichier de `incertains` **sans regarder le diff**. `incertains` est
construit sur trois criteres qui ne dependent que du fichier : import relatif, appel dynamique
(`import_module`/`__import__`/`load_module`/`exec_module`), source illisible. **4 fichiers** sont
dans ce cas et rejouent donc a chaque PR, y compris sur un diff sans aucun `.py`.

**Critere de levee** : le nombre de fichiers offline `incertains` est **0**, ou bien ils sont
retenus par une voie qui REGARDE le diff. (Le ledger, lui, les couvre deja : s'ils sont verts et
non impactes, `raison_de_rejeu` les fait sauter -- mais seulement une fois B1 leve.)

### B3. Le mur d'une PR documentaire

Aujourd'hui **550,8 s** en mono-shard pour un diff d'un seul chemin `docs/`. Le plancher shardé
est fixe par `test_468_collision_numeros_offline` (**82,5 s**, et il lit le backlog **par
construction** -- c'est l'allocateur de numeros, dependance legitime).

**Critere de levee** : le mur d'une PR purement documentaire est sous **60 s**, mesure et non
simule (le mur d'une banque ne se simule pas -- cf. l'ecart 629 s simules / 297,8 s mesures).

### B4. L'ecriture du ledger en MULTI-SHARD

Les 8 shards sont 8 processus : chacun ne connait que sa part et ecraserait celle des autres.
`_ecrire_ledger` **REFUSE** d'ecrire des que `n_shards > 1`, et le dit. Le ledger ne se peuple
donc aujourd'hui qu'en mono-shard.

**Critere de levee** : une consolidation inter-shards existe (chaque shard ecrit sa part, une
passe finale fusionne), ou le mono-shard est assez rapide pour etre le mode nominal.

**ET EN REGIME REEL, B1 DOMINE TOUT.** Mesure faite APRES le rebase de cette PR sur 12 commits
de `master` :

```
--depuis-ledger                    : 239/239 [dependance changee 223, ROUGE 13,
                                              aucune attestation 2, blob change 1]
--since origin/master              : changement dans une lecture GLOBALE
                                     (scripts/ratchets-457-footprints.json) -- TOUT rejoue
```

Les trois autres causes montrent que le mecanisme est **CORRECT** -- il voit les 2 fichiers de
test NEUFS arrives avec `master` (« aucune attestation »), et le fichier que j'ai modifie
(« blob change »). Mais les **223** restants tombent tous par B1. **Tant que B1 tient, le ledger
n'economise rien en pratique**, quelle que soit la qualite de sa cle.

### B5. La garde de retrait empeche le peuplement

`probe_457` REFUSE de se lancer sans `TACTICUS_ALLOW_RATCHETS` (garde posee le 2026-08-06 apres
qu'un agent l'a joue par reflexe). Tant qu'elle est la, **le ledger ne se peuple pas dans le cours
normal**. Ce n'est pas un defaut a corriger tant qu'aucune obligation n'est cablee -- c'est une
dependance a lever EN MEME TEMPS que la mise en service, pas avant.

### B6. Une passe COMPLETE SALIT un fichier VERSIONNE

Trouve au rebase de cette PR : apres la passe de 1 795 s, `git status` portait
`M scripts/cliquets-cache/probe_270r4r2_import_en_premier.tsv` (**367 insertions, 348
suppressions**) -- un cache de cliquet, VERSIONNE, reecrit par un test pendant la passe.

Consequence si `probe_457` redevenait une etape de PR : **chaque agent verrait ce fichier sali**,
donc soit il l'embarquerait dans sa PR (conflit garanti avec les autres, sur un artefact genere),
soit il le restaurerait a la main sans savoir pourquoi. Le probe garantit deja qu'il n'ecrit rien
sous `scripts/python/` (`-p no:cacheprovider`, #455) -- mais un TEST qu'il joue, lui, ecrit
ailleurs.

**Critere de levee** : apres une passe complete, `git status` est **propre** (hors artefacts que
le probe ecrit deliberement : empreinte, ledger).

## 7. Comment s'en servir AUJOURD'HUI (aucune obligation -- un mode d'emploi)

```powershell
$env:TACTICUS_ALLOW_RATCHETS=1        # la garde de retrait est toujours en place (B5)
cd scripts\python
python probe_457_offline_tests_green.py --since origin/master --depuis-ledger
```

**La base est `origin/master`, et pas le merge-base**, pour une raison qui tient au sens de
l'erreur : apres le rebase prescrit avant toute PR, les deux coincident. Si l'agent n'a PAS
rebase, `git diff origin/master HEAD` porte EN PLUS les changements de `master` inverses -- donc
il SUR-selectionne. On se trompe du cote sur. Le merge-base, lui, donnerait la selection juste
dans les deux cas mais **tairait** le fait que la branche est en retard.

`--since` et `--depuis-ledger` se CUMULENT et ne repondent pas a la meme question :
`--since` demande « ce diff touche-t-il ce test ? », le ledger demande « ce test etait-il vert,
et rien de ce dont il depend n'a-t-il bouge depuis ? ». L'intersection est jouee.

`--list` n'execute rien et ne demande pas la variable -- c'est la facon de CHIFFRER une selection
avant de decider de la payer.

## 8. Ce qui n'a PAS ete fait, et pourquoi

- **Aucune obligation ecrite** (`CLAUDE.md`, skill d'orchestration) et **aucun cran executable**
  (hook `Stop`, garde de PR, cliquet declencheur) : decision de l'utilisateur du 2026-08-07, sur
  la mesure du paragraphe 2.
- **Les 45 autres cliquets ne sont pas retablis.** La refutation du `0,21 %` porte sur
  `probe_457` -- 67 % de la banque, et un **lanceur de suite de tests**, pas un cliquet de
  gisement. Les 32 cliquets de gisement n'ont pas tire une seule fois en 67 runs et rien ici ne
  dit ce que vaut LEUR de-obligation. Les retablir par symetrie serait refaire, en sens inverse,
  l'erreur de raisonnement du paragraphe 1.
- **Ni `impacted_files` ni les poids ne sont modifies.** B1 est nomme et chiffre, pas corrige :
  c'est le foyer de #486-r15, en cours de reparation par un autre agent, et le changement est une
  decision de politique de selection.
- **Rouges rencontres et NON traites** (herites de `master`, hors perimetre) :
  `test_270r1r1r3_role_enum_offline::test_etage6...`,
  `test_337_dsl_triggers_attestation_offline`,
  `test_519_comptes_derives_offline::test_le_bloc_genere_est_a_jour` (bloc genere perime,
  `TARGETING_OPTIONS_UNPORTED` 25 vs 26 -- se regenere par
  `probe_519_comptes_de_table.py --ecrire`).
