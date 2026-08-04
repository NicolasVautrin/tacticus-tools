# #469 -- Le mur de `ratchets-bg` : deconfondre avant de regler

`ratchets-bg` prend 16 coeurs en aveugle et ralentit la flotte qu'il est cense ne pas gener.
Trois causes candidates, aucune separee des autres : **(a)** taille de la flotte, **(b)** perimetre
du diff, **(c)** contention du `.git/` partage. Regler `-ThrottleLimit` sur une correlation aurait
ete le vice meme que la tache denonce.

Instruments (versionnes) : `scripts/python/probe_469_contention_deconfusion.py` (sondes + rampe +
scalabilite), `probe_469b_bras_cpu_vs_io.py` (le bras de NATURE), `probe_469c_mur_vs_flotte.py`
(mur **et** temoin d'agent, mesures conjointes), `probe_469d_priorite_mecanisme.py` (le mecanisme
de la parade, par alternance appariee). Garde : `tests/test_469_priorite_banque_de_fond_offline.py`.

**En un paragraphe.** (c) est REFUTEE ; (b) est reelle et voulue ; (a) est reelle mais **le
`-ThrottleLimit` n'en est pas le levier** -- le baisser degrade le mur ET les agents. Ce qui marche
est la **priorite de process** : elle ne retire aucun creneau, elle change qui passe devant, et elle
rend ~20 % de CPU aux agents (deux instruments concordants). Le mur, lui, a un plancher qu'aucun
reglage de parallelisme n'atteint : un cliquet insecable.

Machine : Intel Core Ultra 9 185H, **16 coeurs physiques / 22 logiques** (heterogene : P-cores +
E-cores), 63,5 Go. Depot : 3 498 fichiers suivis, 10 131 objets loose, 32 packs.
Chiffres a RE-DERIVER, jamais a citer.

---

## 1. (c) contention du `.git/` partage -- **REFUTEE**

Bras : les MEMES commandes git en lecture seule, au MEME instant, sur deux depots -- le depot
PARTAGE (arbre principal + 5 worktrees d'agents + `ratchets-bg`) et un CLONE PRIVE
(`git clone --local --no-hardlinks` : meme contenu, meme volume d'objets, index / refs / locks a
lui). Les deux subissent la meme machine a la meme seconde ; la seule chose qui les distingue est
le PARTAGE. Aucune fenetre calme n'est necessaire, et c'est ce qui rend ce bras jouable.

| geste | `.git` PARTAGE | clone PRIVE | ratio |
|---|---|---|---|
| `git grep -l TARGETING_OPTIONS` (mesure isolee) | 26,21 s | 26,99 s | **0,97** |
| `git grep` (mediane de 3, sous banque) | 13,76 s | 16,65 s | **0,83** |
| `rev-parse` / `ls-files` / `diff` | equivalents a la variance pres | | ~1 |

Le partage ne coute **rien de mesurable** en lecture. Le depot partage est meme legerement
AVANTAGE -- il est constamment accede, donc chaud.

**Ce que `git grep` coute vraiment** : 12 a 26 s, sur le partage comme sur le prive, **sans
amelioration au rejeu** (3 passes consecutives : 14,2 / 22,1 / 12,4 s). Ce n'est pas un cache
froid et ce n'est pas le `.git/` : c'est le balayage de 1 759 a 3 498 fichiers. La lecture
heritee (`git grep` 0,6 s -> 20-40 s **a 10 worktrees**) confondait deux choses : a 10 worktrees
il y a 10 agents qui TRAVAILLENT, donc du CPU pris. Le nombre de worktrees et le CPU pris ne sont
pas le meme axe, et c'est le second qui mord (cf. section 2).

### L'artefact qui a failli prouver l'inverse

Premiere passe : `git status` a **16-27 s sur le clone** contre 0,6-2,5 s sur le partage, stable
sur trois passes. Lu tel quel, ce ratio de 0,07 << demontrait >> que le partage etait un avantage
enorme -- verdict spectaculaire et **faux**.

Cause : juste apres un clone, les entrees de l'index portent le mtime du checkout ; git les tient
pour douteuses (`racily clean`) et **relit le contenu des 3 498 fichiers** a chaque `status`. Un
`status` ordinaire reecrirait l'index et sortirait de ce regime -- mais nos sondes passent
`--no-optional-locks` (obligatoire : elles tournent pendant que quatre agents ecrivent, cf. #474),
ce qui interdit justement cette reecriture. Le clone restait donc racy **a vie**.

Correction : un `status` autorise a reecrire l'index, **une fois, dans le depot jetable** ->
0,87 s, stable. C'est le seul geste de tout ce probe qui puisse prendre un lock, et il le prend
dans un depot qui n'appartient a personne.

> Un CONTROLE doit etre dans le meme REGIME que le traite, pas seulement dans le meme
> environnement. Ici les deux depots subissaient la meme machine a la meme seconde -- et
> mesuraient quand meme deux choses differentes.

---

## 2. Quelle ressource borne reellement -- **le CPU**, et le bras qui le montre

Un premier faisceau de sondes pointait ailleurs, avec force. Sous banque, le cout d'**ouvrir** un
fichier passait de 0,43 ms a **19 ms** (x44) pendant que le calcul pur mono-thread ne bougeait que
de **+23 %**, et que le debit en octets restait nul-cout (**0,027 s** pour le plus gros TSV du
depot, une seule ouverture). Lecture naturelle : << c'est l'acces fichier qui sature, pas le CPU >>.

**Cette lecture est REFUTEE**, par un bras a un seul degre de liberte : le MEME cliquet reel, le
MEME nombre K = 8 de process injectes, on ne change que **leur NATURE** (calcul pur / ouvertures
de fichiers en boucle). Conditions ALTERNEES A,B,C,A,B,C -- la charge de fond derive de minute en
minute, la grouper l'attribuerait a la condition.

| cliquet | A temoin | B `cpu+8` | C `io+8` | B/A | C/A |
|---|---|---|---|---|---|
| `probe_313_enum_mirror_bijection.py` | 23,82 s | 42,55 s | 25,02 s | **1,79** | 1,05 |
| `probe_440_repo_root_scan_guard.py` | 35,30 s | 41,05 s | 28,27 s | **1,16** | 0,80 |

La charge I/O ne ralentit rien ; la charge CPU ralentit jusqu'a x1,79.

**Pourquoi la sonde mentait** : un `open()` est un point de preemption. Sur une machine
sursouscrite, un thread qui fait beaucoup d'appels systeme rend la main a chaque appel et doit
etre RE-ORDONNANCE, alors qu'une boucle de calcul garde son quantum. Une sonde riche en appels
systeme est donc un capteur **tres sensible de saturation CPU**, pas un capteur d'I/O. Le signe
qui aurait du alerter etait deja dans la table : si l'acces disque saturait, le gros fichier
(1 ouverture, beaucoup d'octets) aurait souffert -- il coutait 0,027 s.

> Un capteur sensible n'est pas un capteur specifique. `fs_ouvertures` bougeait 44 fois plus que
> `cpu1` **parce qu'il repond mieux a la meme cause**, pas parce qu'il en revelait une autre.

---

## 3. (b) perimetre du diff -- facteur reel, **voulu**, et neutralise dans les mesures

Le facteur 2,9x deja mesure (564,0 s pour un diff de gardes de ciblage, 1 156,0 s pour un diff
touchant `damage_prediction.py`, 400,7 s pour un diff doc-seule) est le comportement **voulu** de
`probe_457 --since` : l'empreinte mesuree et le graphe d'imports rejouent d'autant plus que le
fichier touche est central. Ce n'est pas un defaut a corriger, c'est la selection qui fonctionne.

Consequence de methode, pas de reglage : **toute comparaison de throttle doit tenir le commit
FIXE**. A defaut on compare deux diffs, et l'effet du perimetre ecrase tout effet du parallelisme.
C'est ce que fait `probe_469c`.

---

## 4. `-ThrottleLimit` n'est pas le levier -- **le baisser degrade les DEUX chiffres**

Bras : banque COMPLETE (44 entrees), commit FIXE `995015c8`, sans `--since`, un seul degre de
liberte -- `-ThrottleLimit`. Un TEMOIN D'AGENT (`probe_313`, cliquet reel) est joue en boucle
pendant toute la banque : sa duree dit combien un agent est ralenti. Baselines du temoin prises
avant ET apres, banque eteinte : 13,83 s puis 16,11 s (la derive de fond se lit dans l'ecart).

| `-ThrottleLimit` | mur | temoin median | temoin / baseline | coeurs occupes | **surcout par agent** |
|---|---|---|---|---|---|
| defaut (**16**) | **497,3 s** | 24,94 s | 1,67 | 13,96 / 22 | ~333 s |
| **6** | **564,3 s** (+13,5 %) | 26,32 s | 1,76 | 13,74 / 22 | ~429 s |

Le surcout par agent est `mur x (temoin/base - 1)` : ce que la banque facture a CHAQUE agent
pendant qu'elle tourne. A 4 agents, le total passe de ~1 830 s a ~2 280 s.

**Baisser le throttle allonge le mur ET ralentit davantage les agents.** Il n'y a pas d'arbitrage
a rendre : les deux chiffres, le visible et l'invisible, se degradent ensemble.

⚠ La comparaison qui decide **ne depend pas de la baseline** : 497,3 contre 564,3 s et 24,94
contre 26,32 s sont deux mesures directes. La baseline ne sert qu'a exprimer le surcout en
valeur absolue.

### Pourquoi -- le plancher du mur est un CLIQUET, pas le parallelisme

Ventilation du run a throttle 6 (`logs/ratchets/durations.json`) : **3 287 s** de travail sur 44
entrees, dont **1 887 s (57 %)** pour les 8 shards de `probe_457`, et un plus long cliquet a
**404,2 s**.

* a **T=16**, la borne est `max(plus_long, somme/T)` = `max(404, 205)` = **404 s** -> le mur (497 s)
  est le plus long cliquet **plus** l'inefficacite de contention ;
* a **T=6**, la borne devient `max(404, 548)` = **548 s** -> le mur (564 s) est a **97 %** de son
  optimum theorique : la banque n'a plus assez de creneaux.

Le mur ne peut donc pas descendre sous ~400 s **quel que soit le throttle** : il est borne par un
cliquet INSECABLE. Observation directe qui le confirme -- en fin de run a T=16, il ne restait
qu'UN shard, seul, avec la machine a **11,68 coeurs occupes sur 22** : plus aucune contention, et
pourtant le mur continuait de courir.

> Le mur d'une banque a DEUX regimes : une phase saturee (ou le parallelisme decide) et une QUEUE
> (ou le cliquet le plus long decide, seul). Un reglage de parallelisme n'agit que sur la
> premiere. Le seul levier sur la seconde est d'alleger le cliquet -- residu **#457-r6**, deja
> ouvert.

---

## 4bis. (a) taille de la flotte -- CONFIRMEE, et chiffree par accident

Le meme bras a ete rejoue plus tard dans la soiree, MEME commit, MEME throttle, MEME priorite --
mais un agent avait lance sa propre banque en parallele, donc la machine portait **DEUX banques**
au lieu d'une :

| charge concurrente | mur | temoin median |
|---|---|---|
| flotte + **1** banque (la notre) | 497,3 s | 24,94 s |
| flotte + **2** banques | **1 171,3 s** (x2,36) | **45,6 s** (x1,83) |

C'est la mesure la plus directe de (a) obtenue ici, et elle vient d'un fait d'exploitation qu'on
n'avait pas prevu : **deux banques peuvent tourner en meme temps** (l'orchestrateur lance
`ratchets-bg`, un agent joue `ratchets.ps1` avant sa PR). Rien ne l'empeche ni ne le signale.

⚠ **Le compteur de coeurs occupes ne voit pas ce doublement** : 13,96 contre 13,70 sur 22. Il
sature. Un indicateur d'occupation ne mesure pas la FILE D'ATTENTE -- pour le mur, c'est la file
qui decide, et il faut la lire dans une charge de travail temoin, pas dans un pourcentage.

---

## 5. La parade qui marche : la PRIORITE, pas le parallelisme

Meme bras, throttle constant (defaut), seul degre de liberte : la **classe de priorite Win32** du
`pwsh` de la banque -- heritee par les 44 process Python qu'il lance, donc rien a changer dans
`ratchets.ps1`.

| priorite | mur | temoin median | temoin / base | **surcout par agent** |
|---|---|---|---|---|
| normale | 1 171,3 s | 45,60 s | 2,28 | **1 499 s** |
| **basse** (`BELOW_NORMAL`) | **1 073,3 s** (-8,4 %) | **36,62 s** (-19,7 %) | 1,83 | **891 s** (-41 %) |

Temps total a 4 agents : **7 167 s -> 4 637 s**, soit **-35 %**.

Pourquoi ca marche la ou le throttle echoue : baisser le throttle **retire des creneaux** a la
banque (donc allonge le mur) sans en rendre a personne, puisque le travail total ne change pas.
La priorite n'en retire aucun -- elle change seulement **qui passe devant quand il y a file**. Le
debit agrege est preserve ; seul l'ordre de service change.

⚠ **Ce qui est etabli et ce qui ne l'est pas.** Le gain sur le TEMOIN (-19,7 %) est confirme par un
second instrument (§5bis). Le gain sur le MUR (-8,4 %) est **dans le bruit** : les deux conditions
n'ont pas subi exactement la meme charge (13,70 contre 12,98 coeurs) et une banque tierce tournait.
Ce qui est solide, c'est que la priorite basse **ne DEGRADE PAS le mur** -- contrairement au
throttle, qui le degrade de +13,5 %.

### 5bis. La preuve du MECANISME, et pourquoi il a fallu changer d'instrument

La replication du bras complet en ordre inverse a ete lancee puis **tuee par le harnais** avant sa
seconde condition. Elle n'aurait probablement rien tranche : la machine portait alors **4 banques**
concurrentes, et le meme temoin passait de 26,5 a 47,6 s d'un tour a l'autre **sans qu'on ait rien
change**. Un effet de 20 % ne se lit pas dans ce bruit.

Le remede n'est pas de mesurer plus longtemps, c'est de mesurer AUTREMENT
(`probe_469d_priorite_mecanisme.py`, **60 s**) : la charge de fond est posee UNE FOIS et ne bouge
plus ; on ne bascule que sa **classe de priorite**, sur les process deja vivants
(`SetPriorityClass`, instantane) ; on ALTERNE a haute frequence, en inversant l'ordre a chaque
cycle. Une derive de fond frappe alors les deux conditions pareil et **s'annule dans le rapport
apparie**.

| bruit de fond (10 process CPU) | temoin median |
|---|---|
| priorite NORMALE | 0,721 s |
| priorite **BASSE** | **0,583 s** |
| rapport apparie par cycle | **0,805** |
| cycles ou BASSE gagne | **11 / 12** |

**Convergence** : `0,805` ici, `36,62 / 45,60 = 0,803` sur la banque reelle. Deux instruments
independants -- un micro-temoin sous charge synthetique, un cliquet reel sous la banque entiere --
donnent le meme chiffre a 0,3 % pres. C'est cette convergence qui fonde la parade, pas le run
unique.

---

## 6. Le budget de 4 runners live n'est pas le facteur limitant

Mesure directe pendant les deux runs de banque (`GET /api/admin/drain`) : **`liveRunners` = 1**,
`liveRunnersSource: hooks`, `hostRegistryRunners: 1` -- et ce 1 appartenait a un test live d'agent,
pas a la banque.

C'est structurel, pas circonstanciel : les 44 entrees sont OFFLINE par construction.
`probe_457` exclut `_live.py` **par choix** (c'est ce qui justifie `probe_462`), `probe_462` ne lit
que git et le ledger, `probe_467r4` fait au plus un GET HTTP. **La banque ne monte aucun runner**,
donc le plafond de 4 ne la borne pas -- et la borner dessus n'aurait aucun effet.

---

## 7. Ce que ce dossier N'A PAS pu separer

* **La fenetre << flotte vide >> n'a pas ete obtenue** : les 5 slots etaient pleins pendant tout le
  travail (4 agents + celui-ci), et un agent ne peut pas vider la flotte. Le bras (a) a donc ete
  joue par **augmentation controlee** (charge injectee, section 2) et non par soustraction. Ce
  substitut donne la PENTE, pas l'ordonnee a l'origine : on sait ce que +8 coeurs de charge font
  (x1,79 sur un cliquet), on ne sait pas ce que la banque durerait sur machine deserte.
* **La charge de fond n'est pas tenue fixe** entre deux conditions -- elle appartient a
  l'orchestrateur. Chaque condition rapporte donc les coeurs occupes mesures PENDANT elle
  (13,96 et 13,74 : proches, ce qui rend la comparaison recevable). Deux conditions jouees sous
  des charges tres differentes ne se compareraient pas, et le dire vaut mieux qu'un ratio propre.
* **Le temoin est un MAJORANT du ralentissement d'agent.** `probe_313` est purement CPU ; un agent
  reel passe une part de son temps a attendre des RPC vers le runner (qui vit dans `Tacticus.exe`,
  hors de son process). Le x1,67 mesure ce qu'un agent subit **sur sa part CPU**, pas sur sa duree
  totale.

---

## 8. Le fait d'exploitation que personne ne regardait : **N banques a la fois**

Aucun verrou n'empeche plusieurs banques de tourner ensemble. `ratchets-bg.ps1` en a un, mais il
protege le **worktree persistant** (un second run se rabat sur un worktree jetable et part quand
meme), et `ratchets.ps1` joue directement depuis n'importe quel arbre -- ce que fait tout agent
avant sa PR. Compte releve pendant ce dossier, par `Get-CimInstance Win32_Process` :
**jusqu'a 4 banques simultanees** le 2026-08-04 au soir, soit ~64 process de cliquets pour
16 coeurs.

Effet mesure : le mur de la MEME banque, meme commit, meme throttle, passe de **497,3 s** (une
banque) a **1 171,3 s** (deux). Personne n'est prevenu, et le verdict reste juste -- seul le cout
explose.

⚠ Et l'instrument qui aurait du le montrer ne le montre pas : les **coeurs occupes** valent 13,96
a une banque et 13,70 a deux. **Un indicateur d'occupation sature ; il ne mesure pas la FILE.**
Pour un mur, c'est la file qui decide -- elle se lit dans une charge de travail TEMOIN, jamais
dans un pourcentage. C'est la meme lecon que #467 sur `liveRunners` : le chiffre qui gouverne une
decision doit etre celui qu'on ne peut pas deviner.

---

## 9. Residus

| # | quoi |
|---|---|
| `#469-r1` | **Le gain de la priorite sur le MUR n'est pas etabli** (-8,4 %, dans le bruit de deux charges non identiques). Le gain sur les AGENTS l'est (deux instruments, 0,805 et 0,803). Trancher le mur demanderait des conditions a charge tenue -- donc une fenetre calme, hors de portee d'un agent. |
| `#469-r2` | **Rien ne serialise les banques concurrentes** (§8). 4 observees ensemble ; deux doublent le mur. Un verrou d'ADMISSION (pas de worktree : de RUN) rendrait le mur predictible. A arbitrer : refuser, ou attendre, ou degrader en `-Only`. |
| `#469-r3` | **Le plancher du mur reste un cliquet insecable de ~400 s** (`probe_457`, 57 % du travail). C'est `#457-r6`, deja ouvert -- ce dossier le CHIFFRE et montre qu'aucun reglage de parallelisme ne l'atteindra. |
| `#469-r4` | **Aucune fenetre << flotte vide >>** n'a pu etre obtenue : la pente est mesuree, l'ordonnee a l'origine non (§7). |
