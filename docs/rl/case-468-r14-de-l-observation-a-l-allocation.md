# #468-r14 — `--suggere` n'observe plus, elle ALLOUE

**État : LIVRÉ.** `probe_468_collision_numeros.py --suggere` **réserve** le numéro qu'elle rend,
par création exclusive d'un fichier sous le `.git` **commun** à tous les worktrees. Deux appels
concurrents ne peuvent plus rendre le même numéro — pas « improbablement », **pas du tout**.

## 1. Le symptôme, et pourquoi cinq élargissements du corpus ne l'ont pas fermé

Sept collisions en trois jours, toutes dans le **même régime** : deux allocations concurrentes,
**aucune écriture entre les deux**.

| collision | forme |
|---|---|
| `#907` → renuméroté `#911` | un agent l'annonce, un autre le prend **pendant qu'il travaille** |
| `#909` | `--suggere` le rend alors qu'il est **déjà pris** |
| `#479` | **double** — la racine ET `-r1`, deux agents |
| `#420-r1` | **quadruple** — quatre dossiers |

Le corpus de `--suggere` s'était élargi **cinq fois** (contenu `git grep`, noms de fichiers,
messages de commit, refs hors `HEAD`, noms écrits dans les worktrees voisins, corps des PR).
Toutes ces sources répondent à la même question — **« où ce numéro est-il déjà ÉCRIT ? »**.
Aucune ne peut répondre à celle qui produit nos collisions — **« qui vient de le PRENDRE ? »**.

Le gisement du corpus était **épuisé et mesuré** : les 94 branches non fusionnées apportent
**0** changement de numéro (#468-r10), le corps des PR en apporte **2** (#468-r11). Le probe
**nommait lui-même** l'irréductible dans sa section `PORTEE DE LA MESURE`. Un sixième capteur
n'existait pas.

## 2. Le remède : la création exclusive EST l'allocation

```
os.open(<git-common-dir>/tacticus-468-reservations/<clé>.json, O_CREAT | O_EXCL)
```

`O_CREAT|O_EXCL` (`CREATE_NEW` côté Win32) est **atomique** : pour une clé donnée, **exactement
un** processus en sort avec succès. Il n'y a **aucune fenêtre** entre « je constate que c'est
libre » et « je le prends », parce que c'est le **même appel système**. Celui qui perd la course
reçoit `FileExistsError`, inscrit la clé dans son propre `pris`, incrémente et rejoue — donc la
**monotonie** vaut au tour *n* comme au premier.

`suggerer` ne rend une clé **que si** `_reserver` a rendu `True` pour elle. C'est l'invariant
entier, et il ne comporte aucun seuil.

### Où vit la réservation — trois contraintes, un seul emplacement qui les tienne

| contrainte | ce qui la satisfait | mesure |
|---|---|---|
| **visible de tous** — jusqu'à 6 agents, chacun dans son worktree | `git rev-parse --git-common-dir` | rend le **même chemin absolu** depuis l'arbre principal et depuis chacun des **32** worktrees (2026-08-11) |
| **survit au worktree** — un worktree PROPRE est auto-supprimé | le `.git` du principal | ni `git worktree remove` ni `git clean` n'y descendent ; test dédié |
| **hors de tout arbre de travail** | sous `.git/` | `git status` reste **strictement identique** après une allocation (test dédié) |

Le troisième point n'est pas de l'hygiène. Une réservation **versionnée** exigerait commit+push
— donc **sérialiserait** l'allocation et dépendrait du réseau — et ferait de `docs/rl/backlog.md`,
déjà le fichier le plus partagé du dépôt (**36 des 40** dernières PR), le lieu d'un conflit **par
allocation**.

### Trois formes refusées, et le motif de chacune

- **Verrou global + registre JSON** (lire, décider, écrire, déverrouiller) : ajoute un mode de
  panne que la création exclusive n'a pas — le **verrou orphelin**, qu'un processus tué laisse
  derrière lui et qu'il faut alors expirer **par un délai**, c'est-à-dire par un seuil qui se
  dégrade en silence. Ici il n'y a rien à relâcher : l'artefact **est** le résultat.
- **Commit + push d'une ligne de réservation** : sérialise l'allocation entre agents et dépend du
  réseau. C'est la parade que #468-r10 avait déjà nommée puis écartée pour cette raison.
- **Un service** (le host, un daemon) : une pièce mobile de plus, qui peut être éteinte — et un
  allocateur indisponible fait revenir au geste qu'on supprime.

### Le refus est exécutable

Une réservation **impossible** (droits, un fichier occupant la place du dossier) sort en
**`INDISPONIBLE` (99)** et **n'imprime aucun numéro**. C'est le seul chemin par lequel le défaut
d'origine pourrait revenir en silence : l'allocation ne se **dégrade jamais** en observation.
Même frontière que « une mesure incomplète ne rend jamais de numéro », transposée de la
**lecture** à l'**écriture**.

## 3. La contre-épreuve — elle montre le remède MORDRE

`scripts/python/probe_468r14_reservation_concurrente.py`. Quatre bras, même harnais, même
instant, sur des dépôts git jetables. **Mesure à N = 8** :

| bras | ce qu'il fait | mesuré |
|---|---|---|
| **OBSERVER** (le régime d'AVANT) | N processus appellent `candidat_observe` | **8/8 rendent `#911`** — la collision reproduite |
| **RESERVER** (l'invariant nu) | N processus visent la MÊME clé | **1 gagnant** sur 8 |
| **ALLOUER racine** | N processus allouent | **8 numéros distincts**, `911..918` |
| **ALLOUER résidu** | idem sous `#900` | **8 distincts**, `900-r2..r9` |
| **REFUS** | dossier de réservation rendu impossible | `rc = 99`, **aucun** numéro |

Le bras **OBSERVER est le témoin non nul** : s'il rendait des numéros distincts, le bras ALLOUER
ne prouverait rien — on ne saurait pas si la distinction vient du remède ou d'un montage qui ne
met rien en concurrence. Quand il ne collisionne pas, le probe **REFUSE** au lieu de conclure.

**La contention est attestée par un compte EXACT, pas par un délai.** Le rendez-vous est un
**barrage** : chaque enfant mesure le corpus (la partie lente), se déclare PRÊT, et le parent ne
donne le top qu'une fois les N déclarations reçues. Tous les instantanés précèdent donc la
première réservation, tous visent le **même** premier candidat, chaque clé est gagnée par
exactement un enfant — donc le multiensemble des refus vaut `{0..N-1}` et **leur somme vaut
`N(N-1)/2`, exactement**. Mesuré : **28 = 8×7/2**, dans les deux modes. Un délai fixe n'aurait
donné qu'un **étalement** — un seuil, qui se dégrade dès que la machine est chargée. L'étalement
reste imprimé, mais comme **contexte**.

### Quatre mutants, quatre rouges

| mutant du remède | verdict |
|---|---|
| `_reserver` toujours `True` (réservation inerte) | **FAIL** — 6 gagnants au lieu de 1, clés rendues deux fois |
| `O_EXCL` retiré (création non exclusive) | **FAIL** — idem |
| `allouer` rend le candidat sans le prendre | **FAIL** — `#911` et `#900-r2` rendus deux fois |
| dossier LOCAL au worktree | **FAIL** — mais par un **autre** bras ; la visibilité inter-worktree est gardée par le **test**, pas par ce probe |

## 4. Ce que le remède a DÉSARMÉ, et la réparation

C'est le point le plus important de cette tranche, et il a fallu le **mesurer** plutôt que le
supposer. Depuis que `--suggere` **alloue**, le premier appel d'un test **réserve** son numéro :
le second l'écarterait **de toute façon**, quelle que soit la source du corpus qu'on est en train
de mettre à l'épreuve. Cinq contre-épreuves de `test_468_collision_numeros_offline.py` passaient
donc en **accusant la mauvaise cause**.

Mesure — chaque source hors-arbre coupée dans le probe, les tests qui la gardent rejoués :

| source coupée | AVANT #468-r14 | APRÈS, sans réparation | APRÈS réparation |
|---|---|---|---|
| `_identifiants_des_pr` (corps de PR) | 2 ROUGES | **2 VERTS** | 2 ROUGES |
| `_identifiants_des_worktrees` | 2 ROUGES | **2 VERTS** | 2 ROUGES |
| `_identifiants_des_refs_hors_head` | 1 ROUGE | **1 VERT** | 1 ROUGE |

**Réparation** : `_vider_reservations(racine)` entre les deux bras, ce qui **isole l'axe mesuré**
(les sources du corpus). La réservation, elle, n'est pas laissée sans garde : elle a son propre
cliquet.

⚠ Deux pièges rencontrés dans cette réparation même, tous deux trouvés par la mesure et non à la
relecture :

- le helper remettait **`REPO` en dur** au lieu de restaurer la cible précédente. Deux des cinq
  tests appellent `suggerer` **en process** après avoir visé le dépôt jetable : le bras suivant
  repartait sur le dépôt **réel**, qui rend évidemment un autre numéro — vert pour la mauvaise
  raison. Symptôme : « 1 failed, 1 passed » là où les deux devaient rougir ;
- la première version du script de mesure restaurait le probe par `git checkout --`, donc depuis
  l'**INDEX** — qui contenait déjà la version modifiée. Les cas 2 et 3 tournaient sur la mauvaise
  base et rendaient un résultat **faux dans les deux sens**.

Un test a en outre **changé d'exigence**, et c'est assumé :
`test_deux_suggere_concurrents_..._SIGNALENT_leur_angle_mort` exigeait que les deux worktrees
rendent le **MÊME** numéro et se contentent de le **dire**. C'était la formulation honnête de
#468-r10 — le corpus ne pouvait pas les départager. Ce qu'il exigeait est devenu faux ; il
exige désormais l'inverse (`test_deux_suggere_depuis_deux_worktrees_ne_rendent_PLUS_le_meme_numero`),
sur le **même montage**, pour que la comparaison soit directe.

## 5. Le cliquet

`scripts/python/tests/test_468r14_reservation_offline.py` — **19 tests**, quatre propriétés
testées **séparément** parce qu'elles peuvent casser séparément :

1. **EXCLUSIVITÉ** — deuxième prise de la même clé = `False` ; une réservation **tronquée**
   (processus tué entre `open` et `write`) réserve quand même, puisque c'est le **nom** qui porte
   l'identifiant ; la source est **câblée** dans `employes` (c'est le câblage qui manquait à
   `probe_181`, vert et inconditionnel, #430).
2. **VISIBILITÉ** — montage **réel** (`git worktree add`) : même dossier des deux côtés, et ce
   qui est pris d'un côté est **vu** de l'autre (l'égalité des chemins ne suffit pas à
   l'établir) ; `git status` **inchangé** après allocation.
3. **SURVIE** — réservation prise depuis un worktree, `git worktree remove --force`, la
   réservation **reste** et le numéro n'est **pas** re-proposé.
4. **REFUS** — allocation impossible → `99` sans numéro ; parent non conforme (`../ailleurs`,
   `4 20`, `abc/def`, `#*`) → `rc 2` **avant** toute réservation.

Plus la contre-épreuve de concurrence à N = 4, appelée depuis le cliquet.

## 6. CE QUE LE REMÈDE NE COUVRE PAS

- **Un numéro choisi SANS passer par l'outil.** Rien n'oblige un agent à appeler `--suggere` ;
  la doctrine le prescrit, la réservation ne peut pas l'imposer. Un tel numéro reste invisible
  jusqu'à être **écrit** — et retombe alors sur les cinq sources du corpus.
- **Un autre clone du dépôt, ou une autre machine.** L'espace de noms est **per-dépôt**, comme le
  `.git` qui le porte. Un agent tournant dans un environnement distant (`isolation: "remote"`) ne
  voit pas ces réservations. Ce n'est **pas** notre régime actuel — les 32 worktrees mesurés sont
  tous sur la même machine et le même `.git` — mais ça le deviendrait au premier agent distant.
- **Un numéro réservé et jamais livré** brûle un entier. C'est l'asymétrie que la monotonie
  assume déjà : sauter coûte un entier, reprendre coûte une réécriture d'historique. Il n'y a
  donc **pas de `--liberer`** : il rouvrirait une course entre le libérateur et un demandeur pour
  économiser un entier.
- **Le mode DÉTECTER (étapes 1 et 2) ne lit pas les réservations**, et c'est voulu : une collision
  est une relation entre deux **définitions**, une réservation n'en est pas une.
- **L'atomicité de `O_EXCL` suppose un système de fichiers local.** Mesuré sur NTFS. Sur un
  partage réseau, elle n'est pas garantie — le bras RESERVER du probe le **verrait** (plusieurs
  gagnants), il ne le suppose pas.
- **`--reservations` liste, mais ne confronte pas.** Une réservation dont le numéro a depuis été
  écrit est indistinguable d'une allocation encore en vol. Résidu ouvert.

## 7. Fichiers

- `scripts/python/probe_468_collision_numeros.py` — l'allocation (`_chemin_git_commun`,
  `_dossier_reservations`, `_reserver`, `_identifiants_des_reservations`, `candidat_observe`,
  `allouer`, `lister`), `--pour`, `--reservations`.
- `scripts/python/probe_468r14_reservation_concurrente.py` — la contre-épreuve, 4 bras.
- `scripts/python/tests/test_468r14_reservation_offline.py` — le cliquet, 19 tests.
- `scripts/python/tests/test_468_collision_numeros_offline.py` — 5 contre-épreuves ré-armées,
  1 exigence retournée.
