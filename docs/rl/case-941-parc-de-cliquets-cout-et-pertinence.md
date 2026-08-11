# #941 — Le parc de cliquets offline : où va le coût, et ce qu'il y a à retirer

Deux axes, deux réponses, et la seconde est un **refus argumenté**.

> ⚠ Tous les chiffres ci-dessous se **re-dérivent** (`probe_457 --measure`,
> `scripts/ratchets-457-durations.json`). Ne pas les citer : ils bougent à chaque tranche.

## 1. La mesure de référence — une passe COMPLÈTE, 4 shards

326 fichiers, LPT sur les poids versionnés, `--durations=0`, **machine partagée avec 3 autres
agents** (2026-08-11, `8f357878`) :

```
MUR = 1440 s a 4 shards   (attendu 499 s/shard depuis les poids ; reel 1391-1421 s/shard)
somme setup+call+teardown = 4337 s   -> la CONTENTION vaut x2,8 sur les poids versionnes
bilan : 4475 passed, 3 skipped, 22 FAILED dans 16 fichiers
```

**Un mur ne se simule pas** (`probe_457` le dit déjà) : la contention x2,8 est la seule grandeur
qui compte pour « jouable à chaque merge », et elle n'est dans aucun poids.

## 2. AXE 1 — le coût

### 2.1 Où il va, mesuré et non supposé

Le coût N'EST PAS diffus. Il tient dans **un petit nombre de balayages du corpus entier**, et le
balayage lui-même est irréductible :

```
lire + `ast.parse` tout `scripts/python/**` (2576 fichiers, 47,2 Mo)
    rglob 0,90 s | read 4,20 s | ast.parse 22,74 s  ->  27,8 s PAR BALAYAGE
```

`ast.parse` pèse **82 %**, et il n'est pas cachable en mémoire : retenir les 2576 arbres coûte
~1 Go de tas (mesure #486-r5). Ce qui reste attaquable est donc **le NOMBRE de balayages**, pas
leur prix unitaire.

### 2.2 Le gisement : le MÊME balayage recalculé par plusieurs tests du même fichier

Critère dérivé des `--durations=0` : un fichier où **≥ 2 tests coûtent chacun ≥ 8 s**.
**23 fichiers**, gain potentiel **1213 s sur 4337 s (28 %)** — borne HAUTE, car deux tests chers
ne sont pas toujours le même calcul. Quatre cas ont été **vérifiés à la lecture** puis corrigés :

| cliquet | ce qui était refait | correction |
|---|---|---|
| `probe_287r13r1.invocations()` | balayage de tout `git ls-files` + `ast.unparse`, **×3** | mémo de résultat, valeur immuable |
| `probe_287r14r1.appels_directs()` / `.ventiler()` | balayage complet, **×2** / **×3** | idem (la fixture `scope="module"` ne couvrait que 3 des 5 appels) |
| `probe_514.etape_1()` | balayage `_PORTEE` + un `ast.walk` complet PAR SITE, **×2** | idem, retour re-construit (pas de fuite d'état) |
| `probe_547r1` étages 3 et 4 | **DEUX worktrees témoins** pour le même arbre `HEAD` | un seul témoin, restauré entre les deux étages |

Le worktree témoin est le coût unitaire le plus élevé du parc : **35,0 s** (`worktree add
--detach`) + **18,4 s** (`remove --force`) = **53 s**, dont l'essentiel vient de `data/` (170 Mo,
807 fichiers). En monter deux pour le même `HEAD` était pur gaspillage — et la version à deux
témoins **fuit** : un `wt547r1_*` du 2026-08-08 (4699 fichiers) était encore enregistré dans
`git worktree list` au moment de cette tranche.

### 2.2bis Ce que ça rend — et pourquoi le CHRONOMÈTRE n'est pas la preuve

**La preuve est STRUCTURELLE, pas horaire.** Les `--durations` d'après correction montrent, pour
chacun des quatre fichiers, **un seul** test cher et tous les autres sous 1,5 s :

```
AVANT (passe 4 shards)                        APRES (mesure dediee)
  514  : 63,3 s + 59,6 s                        514  : 81,5 s + tout le reste < 0,1 s
  287r14r1 : 55,1 s + 53,6 s                    287r14r1 : 76,0 s + tout le reste < 1,5 s
  287r13r1 : 61,8 + 59,8 + 59,1 s               287r13r1 : 41,1 s + 2 tests a 0,02 s
  547r1 : 100,8 s + 92,8 s                      547r1 : 48,6 s + 14,2 s (un seul worktree)
```

**Un A/B en temps de mur ne conclut PAS sur cette machine**, et c'est une mesure : joué
séquentiellement, arbre pristine puis arbre corrigé, il rend **605,1 s → 436,6 s (−27,8 %)** —
mais le détail est incohérent (`test_514` : 102,8 s → 100,7 s alors qu'un balayage entier a
disparu). La cause est la **charge partagée**, qui varie d'un facteur ~2 entre les deux bras :
la passe complète elle-même mesure **x2,8** entre les poids versionnés et le réel. Le chiffre de
mur est donc rapporté, pas invoqué.

**L'estimation SANS charge**, seule défendable, se fait en unités mesurées — un balayage du
corpus = 27,8 s, un worktree témoin = 53 s :

```
287r13r1 : 2 balayages evites   287r14r1 : 1 balayage + 2 ventilations
514      : 1 balayage evite     547r1    : 1 worktree evite
-> ~4 balayages + 1 worktree  =  ~164 s   sur 1997 s de mur serie  =  -8,2 %
```

Et le fichier le plus lourd du parc — celui qui fixe le **plancher de sharding** — passe de
**139,1 s à ~86 s**.

**Le relevé le plus propre** (rejeu post-rebase, machine nettement moins chargée — 5 fichiers,
`51 passed, 1 failed` en **238 s**) donne, par test cher restant :

```
547r1 : 54,1 s + 14,4 s (les DEUX etages a temoin, UN seul worktree)
514      : 48,5 s        287r14r1 : 37,9 s        287r13r1 : 32,9 s
```

À comparer aux **355,8 s** de poids versionnés des quatre fichiers touchés (17,8 % du mur série)
— et au bras AVANT de l'A/B, **605,1 s** pour ces mêmes fichiers plus un témoin non touché.

⚠ `scripts/ratchets-457-durations.json` n'est PAS remis à jour ici : `--measure` rejoue tout le
périmètre (~976 s) et le faire sous cette charge écrirait des poids gonflés. Des poids
sur-estimés sont **conservateurs** pour l'équilibrage LPT (le fichier reçoit trop de place, jamais
trop peu). À re-mesurer machine calme.

### 2.2ter Seconde passe (#941-r2) — huit fichiers LUS, quatre corrigés, quatre refusés

Le critère qui a produit la liste de 23 est un **proxy**, et il faut le dire avant les résultats :
« ≥ 2 tests coûtant chacun ≥ 8 s » a été appliqué aux `--durations` d'une passe **à 4 shards**,
donc à des durées gonflées par la contention (x2,8). Re-mesurés **fichier seul**, deux des huit ne
portent qu'**UN** test cher : le proxy les avait retenus sur du bruit. Un troisième les comptait
par son *setup* de fixture — qui est précisément le montage **déjà partagé**.

**Le vrai discriminant n'est pas « combien de verdicts », c'est « combien d'APPELS ».** §2.3
écartait `probe_283` sur « cinq balayages, cinq verdicts différents » : c'est exact pour les
verdicts et **faux pour les appels**. `step_on(verbose=False)` y est appelé **deux fois avec les
mêmes arguments**, un test lisant `decales` et l'autre `fails` — deux positions du **même tuple**.
Un fichier peut donc porter N verdicts et N-1 balayages, et seule la lecture le dit.

| fichier (mesuré SEUL) | avant | après | tests ≥ 8 s | ce qui était refait |
|---|---|---|---|---|
| `test_enum_ordinal_ratchet` | 275,0 s | 220,4 s | 5 → 4 | `step_on()` **×2**, arguments identiques |
| `test_519_comptes_derives` | 112,1 s | 27,8 s | 5 → 1 | `temoins.balayer()` **×5**, `ordinaux.balayer()` **×2** |
| `test_486r24_bypass_confrontation` | 89,7 s | 72,5 s | 4 → 2 | `Fermeture(ROOT)` reconstruite **×3** |
| `test_480r8_rpc_joignable` | 55,1-58,5 s | 41,1-50,5 s | 2 → 1 | le dépôt lu **des DEUX côtés** d'un `subprocess` |

Et les quatre refusés — **c'est un résultat, pas un abandon** :

* **`test_431_build_pin`** — ses trois appels chers (30,1 + 29,3 + 29,3 s) lancent le cliquet sur
  **trois états d'arbre différents** (intact / résolution réintroduite / mention en prose). Il n'y
  a rien de commun à mémoïser : mutualiser reviendrait à ne plus éprouver que l'un des trois. Le
  worktree témoin, lui, est **déjà unique** (fixture `scope="module"`, 59,6 s de `add` + 23,3 s de
  `remove`) — le gisement `probe_547r1` de §2.2 n'a pas d'équivalent ici.
* **`test_457_r8_selection_par_diff`** — **UN** seul test cher (62,7 s) ; les deux suivants sont à
  **4,4 s** parce que `_import_graph` est mémoïsé depuis #486-r5. Le fichier était déjà corrigé,
  la liste ne pouvait pas le savoir.
* **`test_465_ledger_validite`** — **UN** seul test cher (29,7 s, produit cartésien 7 verdicts × 5
  positions × 2 blobs). Le « second test cher » de la liste est le **setup** de `_depot_shas`
  (59,9 s), une fixture `scope="module"` **déjà partagée** par les 12 tests qui en dépendent.
* **`test_468_collision_numeros`** — 20 tests entre 1 et 31 s, et **aucun couple ne calcule la même
  chose** : chacun construit **son** dépôt git jetable (mentions, messages de commit, worktree
  voisin, ledger) puis lance `probe_468` dessus. Le coût est le montage, et il est propre à chaque
  cas.

**La preuve est structurelle, et les murs ci-dessus ne la portent pas** : les deux colonnes ont été
mesurées à des charges différentes (8 fichiers en parallèle contre 4). Ce qui se compte :

```
519      : 5 appels de balayer -> 1 balayage ; les 4 tests a 15,2-23,5 s tombent sous 0,005 s
283      : 2 appels de step_on -> 1 balayage ; `test_aucune_ancre_ANNOTEE` : 30,5 s -> < 0,005 s
486r24   : 3 fermetures       -> 1          ; les deux mutations : 19,1 + 8,4 s -> 0,39 + 0,18 s
480r8    : 6 lectures du depot -> 3         ; l'etage 2 : 18,6 s -> 6,9 s
```

**La contre-épreuve, elle, ne se délègue pas au chronomètre** : pour chaque mémo posé, une mutation
du sujet gardé a été écrite dans l'arbre, vérifiée présente, puis le test cible joué — **9 verdicts
attendus sur 9**. S'y ajoute la **disjonction** pour `step_on`, qui est la propriété que la
mémoïsation menaçait directement : l'ancre annotée périmée fait rougir `fails` **et laisse
`decales` vert**, la quote indécidable l'inverse. Deux verdicts tirés d'un seul balayage restent
deux verdicts.

⚠ **Le mur EN PARALLÈLE a failli faire renoncer à une correction qui gagne 25 %.** `test_480r8`
mesuré à 4 jobs concurrents rendait **73,8 s avant / 73,6 s après** — « aucun gain », et la
tentation d'annuler. Rejoué **en série et ALTERNÉ** sur la même machine (A/B/A/B), il rend
**50,5 et 41,1 s après** contre **58,5 et 55,1 s avant**, avec **un test de PLUS**. Le bruit d'une
machine partagée est du même ordre que le gain qu'on mesure : quatre passes alternées coûtent
3 minutes et tranchent, une passe parallèle ne tranche rien — dans aucun des deux sens.

⚠ **Un mémo peut figer autre chose qu'un coût : un VERDICT.** `probe_519_temoins_de_camp.balayer`
rend des sites **avec leur verdict**, et ce verdict ne vient pas du disque — il interroge l'état du
moteur (`ABILITY_CLASSES`, `TARGETING_OPTIONS_UNPORTED`, `targeting_options_for`), que notre
cadence de portage fait bouger. Le mémo s'arrête donc au **corpus** (8,97 s mesurées) et les
verdicts sont **re-posés** à chaque appel (0,00 s pour 15 sites). Mémoïser le tuple entier aurait
coûté zéro et rendu le cliquet aveugle à ce qu'il garde. C'est le seul étage vraiment neuf de
`test_486r5_balayages_memoises_offline.py` §9.

⚠ **Un mémo ne traverse pas une frontière de PROCESS, et `test_480r8` payait exactement ça** : son
étage 1 lançait le probe en `subprocess`, son étage 2 refaisait les trois mêmes lectures
in-process (recensement 6,32 s, corpus exécutable 7,90 s, corpus doc 1,66 s). Les réunir dans un
seul process est ce qui rend le mémo payant — mais **le sous-process exerçait aussi l'entrée
script**, et `probe_480r8` **n'est pas une entrée de `scripts/ratchets.ps1`** (vérifié) : ce
fichier était le seul à la jouer. Elle n'est donc pas abandonnée, elle est **rendue bon marché** —
un `--help` en sous-process (0,80 s) traverse imports, `__main__` et `argparse` sans balayer quoi
que ce soit, pendant que le CORPS de `main` est exercé in-process. Coquille d'un côté, contenu de
l'autre.

⚠ **`confronter` a reçu une INJECTION, pas un cache**, et l'écart n'est pas cosmétique : ce
fichier de test **écrit** dans des arbres jetables entre deux confrontations (`_monte_arbre`, qui
vide `DC._HARNAIS`). Un cache global y aurait servi un relevé périmé. Le défaut reste une fermeture
neuve — aucun appelant existant ne change de comportement — et c'est l'appelant, seul à connaître
la fraîcheur de son arbre, qui décide de partager la sienne.

### 2.3 Ce qui N'EST PAS du gaspillage, et pourquoi on n'y touche pas

* **`probe_283` (`test_enum_ordinal_ratchet`, 5 étapes, 235 s mesurés)** — cinq balayages, mais
  **cinq verdicts différents**. Les mutualiser exigerait une passe unique à N visiteurs : gros
  refactor, gain plafonné à 4 × 22,7 s, risque d'infidélité élevé. NON FAIT.
  ⚠ **Vrai pour QUATRE d'entre eux, faux pour le cinquième** : `step_on` était appelé **deux fois**
  avec les mêmes arguments, et #941-r2 l'a mémoïsé (cf. §2.2ter). Le reste du paragraphe tient :
  `step_mirror`, `step_exec`, `step_tables` et `step_on` sont bien quatre balayages distincts.
* **Le cache de verdict par fichier (`verdict_cache`, #486-r1) est REFUSÉ pour `step_exec`** —
  par sa propre règle d'admission. Son verdict est **GLOBAL** : `sigs =
  _signatures_positionnelles(arbres)` se dérive de TOUS les fichiers (« un appel peut précéder
  la `def` d'un autre fichier »). Un cache par fichier y fabriquerait des faux verts.
* **`_import_graph` de `probe_457`** est déjà mémoïsé (33,4 s → 0,56 s au second appel).
* **`test_477r24r1` / `test_477r25`** lisent le metadata IL2CPP (~12 s) et récoltent (~20 s) dans
  des fixtures `scope="module"`. Coût intrinsèque, déjà partagé au mieux : à 4 shards les deux
  fichiers tombent dans des shards DIFFÉRENTS, donc une fixture `session` n'achèterait rien.

### 2.4 Le palier par coût — MESURÉ, puis ÉCARTÉ

`probe_457` n'a aucune coupe par coût. Question posée : « jouer tout ce qui coûte ≤ N s » est-il
la bonne réponse ? **Non**, et c'est la même forme de réfutation que `--since` (#935).

Deux populations de rouges INDÉPENDANTES — les 9 attribués par #935 et les 16 fichiers de la
passe ci-dessus, **25 en union** :

```
les 25 fichiers rouges pesent 30,3 % du mur pour 7,6 % des fichiers  -> x4,0 de sur-representation
  palier <=  2 s : joue 252/328 fichiers pour  2,1 % du mur -> attrape  8/25 rouges
  palier <=  5 s : joue 270/328              5,1 %          ->         11/25
  palier <= 15 s : joue 292/328             14,3 %          ->         14/25
  palier <= 60 s : joue 319/328             60,3 %          ->         21/25
```

Le rouge vit dans la **queue chère**. Un palier ne peut donc pas remplacer la passe complète, et
un quatrième mode de sélection sur un fichier qui en porte déjà trois (`--since`,
`--depuis-ledger`, `--shard`) serait surtout un piège de lecture de plus. **Le levier est de
rendre les chers rapides, pas de couper par le coût** — c'est ce que fait §2.2.

*Réserve honnête* : `≤ 2 s` = 2,1 % du mur pour un tiers des rouges reste un excellent ratio
**si et seulement si** on l'appelle un fumigène et jamais un verdict. Non implémenté ici.

### 2.5 Le verrouillage du gain — CINQ étages ajoutés, ZÉRO fichier neuf

La consigne était « pas de cliquet de plus tant que le parc n'est pas assaini ». Les crans posés
sont donc des **étages dans des fichiers existants**, et tous par **SUBSTITUTION** (aucun corpus
réel balayé, aucun worktree réel monté) :

* `test_486r5_balayages_memoises_offline.py` — 3 étages (`invocations`, les deux mémos de
  `287r14r1`, `etape_1` de `514`). Le fichier passe de 14 à 17 tests ; il garde déjà exactement
  cette famille depuis #486-r5 (le cache MORD / il ne FUIT pas / il rend ce que le balayage rend).
* `test_547r1_mesure_missing_non_verdict_offline.py` — 2 étages : `worktree add` compté **une
  seule fois** pour les étages 3+4, et `_restaurer` qui **REFUSE** si un résidu subsiste (sans
  lui, l'étage 4 trouverait « rien à mesurer » et rendrait son `rc` pour une raison étrangère au
  critère — exactement la lecture rassurante que ce cliquet existe pour interdire). Le fichier
  passe de 9 à 11 tests.

**Coût des cinq étages, mesuré** : `0,05 s` pour le compteur de worktree, `< 0,005 s` pour les
quatre autres. Un cliquet qui, pour garder un gain de 53 s, en coûterait 53 rouvrirait le gisement
qu'il ferme — c'est la leçon que #486-r5 avait déjà payée (+150 s pour une première version qui
balayait le corpus réel).

## 3. AXE 2 — la pertinence : **rien à retirer, et voici la mesure**

Quatre critères mécaniques, joués sur les 326 fichiers :

| critère | résultat |
|---|---|
| le probe accusé a DISPARU (import mort) | **0 / 326** |
| un chemin du `DECLENCHEUR` ne désigne rien | **1 / 326** — `data/gameconfig.json`, entrée gitignorée **légitime** (lue par `host_inputs`), pas un sujet mort |
| redondance : un probe gardé par ≥ 2 fichiers | **25 probes** — tous examinés, **aucune fusion défendable** (cf. §3.1) |
| vacuité : une assertion de VIDE sans AUCUNE assertion de non-vide dans le fichier | **7 / 326**, dont **un seul** au-dessus de 1 s — résidu `#941-r3` |

⚠ **Le premier jet du critère de vacuité rendait 29 candidats, et 22 étaient FAUX** : il classait
`assert names == ["_mutation.py"]` comme « ni vide ni non-vide » parce qu'il ne regardait que les
littéraux VIDES. Une contre-épreuve qui compare à une liste **non vide** est précisément une
assertion de non-vacuité. Corrigé, le recensement tombe à 7 — un critère de recensement se
vérifie sur un cas qu'on sait classer (ici `test_314_absolute_repo_path`, qui porte deux
contre-épreuves explicites et n'aurait jamais dû sortir).

**Aucun proxy automatique ne tranche l'utilité**, et le proxy évident est faux : « nombre de
commits touchant le cliquet » mesure l'inverse de ce qu'on veut — un bon cliquet ne bouge jamais,
ses rouges se réparent dans le code ACCUSÉ. Le tri s'est donc fait à la lecture, sur une liste
courte.

### 3.1 Les redondances examinées, et gardées

* `probe_477r24r1` gardé par `test_477r24r1` **et** `test_477r25` : les périmètres sont
  **DISJOINTS** (`IOperationProcessor` d'un côté, 17 autres interfaces de l'autre), et l'étage 5
  de `r25` est un **recoupement délibéré** des deux dérivations. GARDÉS.
* `probe_287r4r1` gardé par **7** fichiers : un par ability/régime. GARDÉS.
* Les 22 autres paires pèsent **< 3 s au total** : les fusionner ne rachèterait rien et ferait
  perdre l'attribution. GARDÉS.

### 3.2 Ce qui plaide CONTRE tout élagage : le parc mord, et personne ne le lit

La passe complète rend **22 tests rouges dans 16 fichiers**. **7** de ces fichiers sont déjà
nommés par `#934` ; **9 ne le sont nulle part**, et l'un d'eux (`test_477r24r1`) est ROUGE dans le
ledger VERSIONNÉ depuis sa dernière attestation — l'entrée existe, elle dit `ROUGE`, personne ne
l'a lue. S'y ajoute `probe_486r15_declencheurs_tests.py`, **FAIL sur 2 fichiers**, et lui n'est
**ni** une entrée de `scripts/ratchets.ps1` **ni** un `test_*.py` : aucune des deux machineries ne
le joue.

Le parc n'est pas surdimensionné — il est **sous-joué**. C'est l'argument central contre tout
élagage : on ne retire pas des gardes qui mordent, on les LIT. Détail et résidu : `#941-r1`.

## 4. Ce qui n'est PAS couvert

* Le **mur APRÈS** est mesuré fichier par fichier (§2.2), pas par une seconde passe complète :
  une passe coûte ~24 min de machine partagée, et la rejouer deux fois pour un gain déjà
  attribuable fichier par fichier ne se justifiait pas.
* **Onze** des 19 fichiers du patron « ≥ 2 tests chers » restent à lire. Huit l'ont été
  (#941-r2, §2.2ter) : quatre corrigés, quatre refusés avec mesure. Le reste du gain annoncé
  (~290 s de borne haute) porte sur `test_433r4r1r4r2r1r1`, `test_477r25`, `test_477r24r1`,
  `test_468r14`, `test_474_optional_locks`, `test_477r24_phase_attribution`,
  `test_448_r3_r1_noms_non_resolvables`, `test_270r4r2r2r3`, `test_486r15_empreinte_par_entree`,
  `test_ctx_traits_substrat_ventilation`, `test_515_adjacence_elevation`. Résidu `#941-r2`.
* Les **poids de `scripts/ratchets-457-durations.json` n'ont PAS été re-mesurés** — ni par #941,
  ni ici (vérifié : `git show <sha>:scripts/ratchets-457-durations.json` rend le même fichier
  avant et après #941). `--jobs` répartit donc les shards sur des poids périmés pour les huit
  fichiers déjà optimisés : les surcharges sont **conservatrices** pour l'équilibrage LPT (le
  shard reçoit trop de place, jamais trop peu), mais elles cessent de décrire le parc.
  `--measure` rejoue tout le périmètre (~2000 s) et le lancer sous la charge d'une flotte
  graverait des poids gonflés de x2,8 : **à re-mesurer machine calme**, en un seul geste, pas
  par tranche.
* Le **montage** de deux fichiers refusés est un gisement RÉEL mais d'une autre nature que le
  patron de ce résidu — un coût de fixture, pas un balayage dupliqué. Résidu `#941-r4`.
* La **vacuité** n'a été instruite que par un critère syntaxique (assertions de vide sans
  contre-partie). Il ne voit pas un cliquet dont la population est non vide mais dont le
  PRÉDICAT ne discrimine plus.
