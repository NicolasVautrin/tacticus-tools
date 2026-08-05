# #468-r10 — l'allocateur DIT ce qu'il ne peut pas voir

**Critère binaire** : deux `--suggere` concurrents, depuis deux worktrees, peuvent-ils rendre le
même numéro **sans le signaler** ? **Ils le pouvaient** — et l'ont fait, à un aller-retour d'agent
près.

Le défaut n'était **pas** une collision manquée. C'était un **`PASS` rassurant rendu dans le seul
régime où nos collisions se produisent** : le corpus de `--suggere` était ce qui est *écrit et
fusionné*, alors qu'une allocation se fait **au début** d'une tranche, quand rien n'existe encore.

---

## 1. La mesure qui ouvre le dossier

Deux agents dispatchés ensemble ont reçu **`#479`** du même `--suggere` — le ménage des branches
orphelines (PR #659) et l'audit des hooks (PR #663). Collision **double** : la racine **et** le
résidu `r1`, pour deux sujets sans rapport. `probe_468` rendait `PASS` pendant tout ce temps, **et
il avait raison** au regard de son corpus : à l'instant de l'allocation, aucun des deux artefacts
n'existait.

C'est le patron traqué partout ailleurs — un capteur qui répond sur ce qu'il regarde, en laissant
croire qu'il a tout regardé.

---

## 2. L'aveuglement se VENTILE en trois niveaux — deux se ferment, le troisième se nomme

| | ce qui est invisible | pourquoi | statut |
|---|---|---|---|
| **N1** | tout commit **hors de la lignée de `HEAD`** | `git log` sans `--all`. Un worktree d'agent est **figé à son commit de lancement** : il est aveugle à `master` qui avance *et* aux branches des voisins | **fermé** — `git log --all --not HEAD`, **+0,06 s** |
| **N2** | les fichiers **du checkout d'à côté** | `git grep --untracked` ne lit que **son** arbre de travail | **fermé** — glob **borné** des noms, **+0,39 s** pour 13 worktrees |
| **N3** | un numéro **pris et pas encore écrit** | aucune lecture de l'arbre ne peut le voir | **irréductible** → **NOMMÉ** (§4) |

`--not HEAD` n'est pas une micro-optimisation : c'est ce qui rend la **provenance** gratuite. Un
`--all` nu coûterait autant mais mélangerait les deux origines, et l'outil ne pourrait plus *dire*
ce qui est en vol.

Le balayage N2 ne lance **aucune commande git dans l'arbre d'autrui** — `git status` y rafraîchirait
l'index, c'est-à-dire une **écriture** chez un agent qui travaille. Il lit des **noms de fichiers**,
par le système de fichiers, sur quatre motifs bornés.

### Effet mesuré, à la révision de lancement (dépôt réel, 2026-08-05)

| régime | racine | `--suggere 425` | `--suggere 448` |
|---|---|---|---|
| avant (3 sources) | #481 | **#425-r3** ← déjà pris | **#448-r3** ← déjà pris |
| après (+N1 +N2) | #481 | **#425-r4** | **#448-r4** |

**Deux collisions imminentes évitées**, sur l'arbre vivant, à l'instant de la mesure. Les porteurs :
`probe_425r3_removed_writers.py` dans un worktree d'agent (N2), `case-448-r3-*.md` commité hors de
la lignée de `HEAD` (N1).

⚠ La mesure a dû être **refaite sur la révision de lancement** : citer `#425-r3` dans un docstring
le **réserve**, le corpus étant l'union mentions comprises. Un outil d'attribution qui se lit
lui-même contamine sa propre démonstration.

---

## 3. Deux extensions MESURÉES PUIS REFUSÉES — le chiffre décide

| extension | coût | apport | verdict |
|---|---|---|---|
| balayer les **94 branches non fusionnées** (diff + log par branche) | ~30 s | **5** identifiants, **une seule racine : `#658`** — et c'est un numéro de **PR**, pas de tâche (`#468-r8`). Numéro rendu : **INCHANGÉ** | **refusée** |
| `git log --all --diff-filter=A --name-only` (couvrirait les branches **sans** worktree) | **+2,64 s** (×1,7) | **25** identifiants dont **24 de bruit pur** — `#arithmetic`, `#dispatcher`, `#selectors`… des noms de modules Python | **refusée** |

La crainte au dossier — « (a) réserverait des dizaines de numéros **morts** » (79 branches survivent
au squash-merge, `#467-r6`) — est **réfutée dans sa forme** : **0 réservation morte**. Le vrai motif
de refus est inverse et plus net : **(a) n'apporte rien**, parce que le contenu d'une branche
squash-mergée est déjà dans le corpus, et que `--all` en capte les messages pour 0,06 s. Ce qu'elle
importerait en propre est un **espace de noms étranger** — celui des PR.

---

## 4. Ce qui est NOMMÉ : la section `PORTEE DE LA MESURE`

Imprimée **inconditionnellement**, après le numéro, dans les deux modes. La rendre conditionnelle
réintroduirait le « `PASS` rassurant » qu'elle existe pour tuer : **même à zéro worktree
concurrent**, une PR en vol ou un worktree déjà supprimé peut porter ce numéro.

Elle porte quatre choses : l'**angle mort N3** en clair ; la **concurrence chiffrée** ; les
identifiants **déjà en vol** avec leur provenance ; et l'injonction d'annoncer le numéro pris.

**Tri-état, deux étages, et aucun ne fabrique un zéro** :

* `git worktree list` **muet** → `concurrence : NON MESUREE`, jamais « 0 autre worktree ».
* un worktree **illisible** (jetable de pytest qui meurt, agent nettoyé) → `ILLISIBLE (non mesuré,
  pas vide)`, **nommé un par un**.

⚠ **Ce capteur ne lève PAS `Indisponible`, contrairement à `git grep` et `git log`** — et c'est un
arbitrage, pas un oubli. C'est un capteur d'**appoint** : sans lui, `--suggere` retombe sur son
comportement d'avant cette tranche, dégradé mais pas faux au sens où l'était un corpus privé de son
historique. Le faire lever transformerait la panne d'un capteur d'appoint en **refus total** — une
régression pour un `git` ancien ou bridé. La contrepartie est stricte, et c'est la portée qui la
tient.

---

## 5. Contre-épreuve — 7 mutations, 7 rouges, et deux ont corrigé le CODE

Chaque mutation est vérifiée **appliquée** avant le run, et chaque bras **non muté** est vert —
sans quoi les rouges ne prouveraient rien.

| mutation | test qui tombe |
|---|---|
| l'**avertissement** est retiré de la sortie | `test_deux_suggere_concurrents_..._SIGNALENT_leur_angle_mort` |
| N2 désarmé (les autres worktrees ne rendent plus rien) | `test_N2_un_numero_ecrit_dans_un_AUTRE_worktree_...` |
| N2 désarmé, **autre combinaison** | `test_N2_generalisation_un_PROBE_du_voisin_bloque_le_mode_RESIDU` |
| N1 désarmé (les refs hors `HEAD` ne sont plus lues) | `test_N1_un_numero_commite_sur_une_ref_HORS_HEAD_...` |
| le capteur **muet** est rabattu sur zéro | `test_un_capteur_de_concurrence_MUET_ne_se_rabat_JAMAIS_sur_zero` |
| une **sortie vide** de `worktree list` est lue comme zéro | `test_un_worktree_list_MUET_n_est_pas_lu_comme_ZERO_WORKTREE` |
| un worktree **illisible** est avalé en silence | `test_un_worktree_ILLISIBLE_est_NOMME_et_non_compte_pour_vide` |

**Généralisation, et ce n'est pas décoratif** : le cas réel mesuré était un **probe** (`probe_425r3_*`)
en mode **résidu** (`--suggere 425`), en graphie **collée**. Un patch qui ne fermerait que le couple
(case-doc, racine) laisserait passer exactement la collision qui a ouvert ce dossier. Les deux
combinaisons sont donc gardées séparément.

La garde de retournement monte **deux vrais worktrees** du même `.git` (`git worktree add`), placés
**à côté** l'un de l'autre : imbriqués, le `git grep` du premier balayerait le second et le test
passerait pour la mauvaise raison. Elle **exige d'abord que le régime soit dégénéré** (`n1 == n2`) —
un montage où les deux se départagent seuls ne met pas l'avertissement à l'épreuve, et serait vert
sans jamais le lire.

**Deux faiblesses trouvées, et corrigées dans le CODE — pas dans le test** :

* **La mutation « worktree illisible » a d'abord rendu VERT.** `Path.glob` sur un répertoire
  **absent** ne lève pas, il rend une liste vide : le test passait par un **second chemin** que la
  mutation ne visait pas. Deux chemins pour un même constat, c'est un chemin **non gardé** —
  refondu en un foyer unique.
* **La relecture a trouvé le vice que ce dossier existe pour supprimer, dans mon propre code.**
  `_git` **tolère `rc=1`**, parce que `git grep` rend 1 quand il ne trouve rien — réponse valide.
  Mais pour `worktree list`, `rc=1` est une **panne** (sous-commande absente d'un git ancien), qui
  sort en stdout **vide** et se serait lue « **0 autre worktree MESURÉ** » : un zéro fabriqué. Le
  discriminant est **dérivé, pas conventionnel** — un `worktree list` qui réussit liste **toujours**
  au moins l'arbre d'où l'on parle, donc une sortie vide ne peut être qu'un capteur muet.

État : `probe_468` **PASS**, **21** auto-tests, **30** tests offline (22 + 8). `probe_439`,
`probe_440`, `probe_365` re-joués **verts** — `probe_440` en particulier, puisque le balayage N2
touche des worktrees (§ ci-dessous).

### 5.1 Ce que ce balayage n'est PAS, et ce qu'il ne voit pas

Ce n'est **pas** la faute de **#434**. Celle-là punit un cliquet qui **énumère depuis la racine** et
ramasse `.claude/worktrees/` sans le vouloir : il paie la traversée × N et rapporte les fichiers du
voisin **comme les siens**. Ici les worktrees sont la **cible**, nommés un par un par `git worktree
list`, sur quatre motifs bornés, et pour leurs seuls **noms** — jamais confondus avec le périmètre
courant, puisqu'ils sortent sous `worktree <nom>`. Et `--suggere` n'est **pas dans la banque**
(`ratchets.ps1` l'appelle sans argument) : ces 0,39 s ne touchent pas le mur des cliquets.

**Limites assumées, à ne pas découvrir plus tard** :

* un numéro écrit chez le voisin dans un fichier **hors des quatre motifs** (une note, une ligne de
  backlog non commitée) reste invisible. Grepper le **contenu** des autres worktrees le verrait,
  au prix de 13 `git grep` — refusé pour la même raison que le `--name-only` du §3 ;
* un worktree **abandonné** (agent mort, nettoyage pas passé) fait réserver un numéro qui ne sera
  peut-être jamais livré. On saute alors un entier pour rien — même asymétrie assumée que la
  monotonie : sauter coûte un entier, reprendre coûte une réécriture d'historique.

---

## 6. La technique, réutilisable

**Quand un capteur ne peut structurellement pas voir une classe de faits, la première livraison
n'est pas de la voir — c'est de DIRE qu'on ne la voit pas.** L'avertissement est indépendant des
parades, donc livrable tout de suite ; les parades, elles, se **mesurent avant de se construire** —
les deux extensions évaluées ici sont mortes sur un chiffre, et l'une d'elles était **la voie la
plus directe**.

Corollaire : **ventiler l'angle mort par niveau avant de choisir la parade.** « `--suggere` ne voit
pas les agents en vol » est un énoncé sur lequel on ne peut rien construire ; ventilé en N1 / N2 /
N3, il rend deux corrections à quelques dixièmes de seconde et une impossibilité qu'on assume.

---

## 7. Résidus

* **`#468-r11` — N3 reste ouvert, et le capteur `gh` (parade (c)) n'est pas construit.** Deux
  `--suggere` lancés **au même instant** rendent toujours le même numéro. Restent non construites :
  **(b)** un registre de réservation versionné, qui **sérialise** l'allocation (commit + push par
  numéro) ; **(c)** `gh pr list`, seul capable de couvrir les PR en vol **dont le worktree est déjà
  supprimé** — le gisement que N1+N2 ne voient pas — mais dont `#467-r6` a mesuré les **trois pannes
  distinctes sous un même `rc`**. *Condition de retournement* : un numéro pris par une PR ouverte
  sans branche locale est écarté, et une panne de `gh` se lit `NON MESUREE`, jamais `0`.
