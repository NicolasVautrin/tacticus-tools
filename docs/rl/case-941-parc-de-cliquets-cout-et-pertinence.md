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

### 2.3 Ce qui N'EST PAS du gaspillage, et pourquoi on n'y touche pas

* **`probe_283` (`test_enum_ordinal_ratchet`, 5 étapes, 235 s mesurés)** — cinq balayages, mais
  **cinq verdicts différents**. Les mutualiser exigerait une passe unique à N visiteurs : gros
  refactor, gain plafonné à 4 × 22,7 s, risque d'infidélité élevé. NON FAIT.
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
* Les **19 autres fichiers** du patron « ≥ 2 tests chers » (`test_468`, `test_431_build_pin`,
  `test_486r24`, `test_519`, `test_457_r8`…) ne sont pas traités : chacun demande de vérifier À
  LA LECTURE que les tests refont bien le MÊME calcul. Reste ~900 s de gain potentiel, borne
  haute. Résidu `#941-r2`.
* La **vacuité** n'a été instruite que par un critère syntaxique (assertions de vide sans
  contre-partie). Il ne voit pas un cliquet dont la population est non vide mais dont le
  PRÉDICAT ne discrimine plus.
