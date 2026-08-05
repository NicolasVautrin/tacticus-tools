# #468-r11 — l'allocateur est MONOTONE des deux côtés, et il lit le corps des PR

**Deux critères binaires, tranchés séparément :**

1. `--suggere` refuse un trou pour une **racine** et en **propose un** pour un **résidu** —
   asymétrie **voulue ou pas** ? **Pas voulue** : elle contredisait le docstring de la fonction
   elle-même, qui affirmait déjà la monotonie pour les deux modes.
2. La parade `gh` que `#468-r10` a **nommée sans la construire** vaut-elle son coût ?
   **Oui, et le chiffre le dit** : elle change **2 numéros rendus** sur l'arbre vivant, là où les
   deux extensions refusées par `#468-r10` en changeaient **0**.

---

## 1. Défaut 1 — les résidus au-delà du trou étaient VUS, et tus

Le signalement : `--suggere 477` rendait `#477-r14` alors que `#477-r15`, `-r16` et `-r17`
existent. La sortie affichait `pris sous #477 : r1 … r13` et s'arrêtait là.

**Première question, et elle devait être MESURÉE, pas déduite de la sortie** : le corpus les
voyait-il ? Interrogation directe du dict `pris` que `suggerer()` consomme (`employes()`) :

| identifiant | sources vues par le corpus |
|---|---|
| `477r15` | 2 case-docs, 2 probes, 1 test, `git grep`, `git log`, **1 ref non fusionnée**, **5 worktrees** |
| `477r16` | 1 case-doc, 1 probe, `git grep`, `git log`, **5 worktrees** |
| `477r17` | `git grep` |

⇒ **Vus, tous les trois.** Ce n'était donc pas un trou de couverture — le second défaut, plus
grave, que le signalement redoutait. C'était la **RESTITUTION** : la boucle s'arrêtait au premier
trou, et n'imprimait comme « pris » que le **préfixe contigu** qu'elle avait traversé. Un compte
filtré qui ne dit pas ce qu'il filtre : le vice exact que `#468-r10` venait de fermer ailleurs.

**Ampleur, mesurée** : sur **218** parents connus du corpus, **11** proposaient un trou alors que
des résidus **supérieurs** existaient — `#66`, `#95`, `#229` (seul `r2` écrit, `r1` jamais),
`#437-r1` (`r1` et `r3`), `#462-r4d`, `#462-r4b-r1-r1-r1-r1c`, `#477`, et quatre branches profondes
de `#419-r1`.

### Ce que l'asymétrie valait, et pourquoi elle tombe

Le motif écrit pour les racines — « un trou peut être réservé par une PR en vol » — s'applique
**mot pour mot** à un résidu, et le code le disait déjà : le docstring de `suggerer` porte
« On ne recycle JAMAIS un trou … La suggestion est donc MONOTONE », pour la fonction **entière**.
Seule la branche racine l'implémentait. C'était une **contradiction interne**, pas un arbitrage —
donc rien à justifier, tout à aligner.

Les deux modes partent désormais du **plus grand pris + 1**, et les trous sont **listés** :

```
[468] LIBRE : #437-r1-r4
   pris sous #437-r1 : r1, r3
   1 trou(s) libre(s) SOUS r4, NON proposes (un trou peut etre reserve par une PR en vol) : r2
```

⚠ **Un trou de résidu n'a pas la même origine qu'un trou de racine, et c'est le côté sûr qui
tranche.** Un `r14` libre entre `r13` et `r15` vient soit d'un numéro pris et jamais écrit (N3),
soit d'un dossier renommé, soit d'une PR ouverte dont le worktree est déjà supprimé. Aucune de ces
trois causes ne se lit dans l'arbre. Sauter coûte un entier ; reprendre coûte une réécriture
d'historique.

---

## 2. Défaut 2 — le corps d'une PR n'est PAS dans l'arbre

`#468-r10` avait laissé la parade `gh` non construite, en la décrivant comme la seule capable de
couvrir « les PR en vol **dont le worktree est déjà supprimé** ». La mesure a trouvé un gisement
**plus large et plus stable** que celui-là : **le corps d'une PR n'entre jamais dans l'arbre**, y
compris après fusion — le squash-merge ne le recopie pas dans le message de commit.

Le cas mesuré est exemplaire. La PR **#663** écrit, dans son corps :

> `probe_252` **VERT**, 6 tables en bijection exacte ; mais son verdict ne pèse pas `manquants`
> ⇒ **#479-r2**.

Or `git grep -E "479-?r2" -- docs/rl scripts/python` rend **0**, et
`git log --all --grep "479-r2"` rend **0**. `--suggere 479` rendait donc `#479-r2` — un numéro
**déjà ouvert**, invisible des cinq sources existantes. Même symptôme que `#425-r3` et `#448-r3`
au niveau N1/N2, sur une **quatrième** source hors-arbre.

### Le chiffre qui décide — même protocole que les deux extensions REFUSÉES

Identifiants **absents** du corpus des autres sources, apportés par le **titre + le corps** des PR :

| PR lues | inédits | dont résidus | **changent le numéro rendu** | coût |
|---|---|---|---|---|
| 25 | 4 | 1 | **1** (`--suggere 479` : r2 → r3) | ~1,5 s |
| **200 (retenu)** | 20 | 2 | **2** (+ `--suggere 449-r2-r5` : r4 → r5) | ~3,9 s |
| 670 (toutes) | 25 | 2 | **2 — aucun de plus** | ~7,3 s |

**Le gisement se tarit** : les 470 PR les plus anciennes n'apportent **aucun** changement de
numéro (leur contenu a fini dans l'arbre). `GH_LIMITE_PR = 200` capture donc **100 % du signal
mesuré pour 53 % du coût** de la lecture intégrale. Coût de bout en bout de `--suggere` :
**3,1-3,9 s sans `gh`, 6,0-9,1 s avec** (3 mesures dans chaque régime, 11 worktrees actifs).

**Ce coût ne touche pas le mur des cliquets** : `ratchets.ps1` appelle `probe_468` **sans**
`--suggere` (le commentaire y est explicite), donc la banque ne paie rien.

### Deux choix de forme, tous deux dictés par la mesure

* **Le NOM DE BRANCHE n'est pas lu.** Lu par `couper_nom` — la voie que le probe emploie déjà pour
  les noms de fichiers — il rend `worktree` et `agent` : **0 signal**, du bruit pur. Même famille
  que le `git log --name-only` refusé par `#468-r10`.
* **Les numéros de PR sont GARDÉS, et c'est le côté sûr.** Sur 200 PR, **18 des 20** inédits sont
  des numéros de **pull request** cités en prose (`#631`, `#655`…) que rien ne distingue d'une
  tâche (`#468-r8`). Ils n'ont **aucun effet aujourd'hui** — la borne des tâches est 478, le
  balayage part de 479 et ne les rencontre pas — et feront sauter un entier le jour où les deux
  espaces se rejoindront (~670). Les écarter risquerait de rater une vraie racine.

### Le tri-état, et pourquoi ce capteur NE LÈVE PAS `Indisponible`

Même arbitrage que `git worktree list`, et pour la même raison : `gh` est un capteur d'**appoint**.
Sans lui, `--suggere` retombe sur les cinq sources d'avant — dégradé, pas faux. Le faire lever
rendrait l'outil inutilisable **hors ligne ou sans `gh`**, donc ferait revenir au geste qu'il
supprime (choisir son numéro au vol).

La contrepartie est stricte, et c'est la portée qui la tient :

```
   PR GitHub : NON MESUREES -- `gh` introuvable sur le PATH
   PR GitHub : 200 lue(s) sur les 200 plus recentes ; les plus ANCIENNES ne sont PAS lues
```

* **La panne porte son NOM, par son STDERR** — un `rc` ne nomme rien : sur `gh 2.88.1`, `rc=1`
  couvre à lui seul le token invalide (HTTP 401), le dépôt inconnu (GraphQL) et l'erreur d'usage
  (`#467-r6`). Sept formes de panne sont gardées, chacune vérifiant **deux** choses : que la raison
  est nommée, **et** qu'aucune ne rend une liste vide.
* **Aucun repli sur cache.** Un cache disant « 0 PR » ne prouverait rien et ferait taire l'outil
  sur une PR ouverte depuis. Il peut signaler, jamais rassurer — donc il n'existe pas.
* **Pas de discriminant dérivé ici, contrairement à `worktree list`.** Là-bas, une sortie vide ne
  *peut pas* être vraie. Ici, un dépôt sans aucune PR rend légitimement `[]` : `rc == 0` + JSON
  valide est le seul discriminant disponible, et il est écrit comme tel plutôt que maquillé en
  règle.

---

## 3. Contre-épreuve — 9 mutations, 9 rouges, et **DEUX ont accusé ma garde**

Chaque mutation est vérifiée **appliquée** (le motif doit exister, le texte doit changer, le
fichier est restauré et son hash re-vérifié), et chaque bras **témoin** non muté est vert.

| mutation | test qui tombe |
|---|---|
| mode résidu : retour au **premier trou** | `test_le_mode_RESIDU_ne_RECYCLE_pas_un_trou_lui_non_plus` |
| restitution : n'imprimer que le **préfixe contigu** | `test_le_mode_RESIDU_LISTE_ce_qui_est_pris_AU_DELA_du_trou` |
| la liste des trous **tronque en silence** | `test_la_liste_des_trous_ne_MENT_pas_sur_ce_qu_elle_tronque` |
| la source `gh` **désarmée** dans `suggerer` | les **deux** tests de la source (racine ET résidu) |
| `gh` ne lit que le **titre** | `test_un_numero_ouvert_SEULEMENT_dans_le_CORPS_d_une_PR_…` |
| `gh` ne lit que le **corps** | `test_le_mode_RESIDU_ecarte_lui_aussi_un_numero_venu_d_une_PR` |
| une panne de `gh` **rabattue sur `[]`** | `test_une_panne_de_gh_est_NOMMEE_et_ne_fabrique_JAMAIS_un_zero` |
| la panne n'est plus **nommée** au lecteur | `test_la_PORTEE_distingue_PR_NON_MESUREES_de_PR_LUES` |
| `gh` lit **aussi le nom de branche** (via `couper_nom`) | `test_gh_ne_lit_PAS_le_nom_de_branche_et_c_est_une_MESURE` |

**Généralisation, et elle n'est pas décorative** : le cas réel mesuré (`#479-r2`) était un
**résidu**, pas une racine. Un correctif câblant la source dans le seul mode racine aurait laissé
passer exactement la collision qui a ouvert le dossier — d'où deux mutations symétriques
(titre seul / corps seul) qui rougissent chacune **un** mode.

### Les deux mutants qui n'ont pas mordu, et ce qu'ils ont corrigé

* **« restitution = préfixe contigu » est resté VERT au premier jet**, parce que la mutation
  imprimait `range(1, max+1)` — c'est-à-dire une restitution **correcte**. Un mutant qui n'est pas
  une **dégradation** ne peut pas mordre : c'est le mutant qui était mal formé, pas la garde. La
  vraie dégradation reproduit l'arrêt au premier trou.
* **« `gh` lit aussi le nom de branche » est resté VERT, et là c'est la GARDE qui était en cause —
  ainsi que le chiffre qui la justifiait.** Ajouter `headRefName` à la boucle `RE_TOKEN_LARGE` ne
  change **rien** : ce motif exige un `#`, qu'un nom de branche ne porte pas. Re-mesuré sur 40 PR :

  | forme de lecture | identifiants | inédits |
  |---|---|---|
  | `RE_TOKEN_LARGE` tel quel | **0** | 0 |
  | `couper_nom` (la voie réaliste) | **2** (`worktree`, `agent`) | 1 |
  | `RE_TOKEN_LARGE` + `#` préfixé artificiellement | 40 | 39 |

  La **troisième ligne était ma première mesure** — elle préfixait un `#` que le code n'écrit
  jamais. Le « 24 identifiants de bruit » que j'en avais tiré est **faux**, et c'est le mutant qui
  l'a montré. Corrigés tous les deux : l'assertion est devenue une **égalité stricte** (elle rougit
  sur *toute* forme de lecture du nom de branche), et le chiffre au docstring est celui de la forme
  réaliste.

**État** : `probe_468` **PASS** ; **21** auto-tests d'étape 0a inchangés ; **46** tests offline
(30 + 16). `probe_440`, `probe_439`, `probe_365` re-joués **verts**.

---

## 4. La technique, réutilisable

**Quand un outil rend un résultat qui n'est pas *faux*, la question n'est pas « est-il juste ? »
mais « le lecteur peut-il juger ? ».** `#477-r14` était réellement libre : la sortie ne mentait
pas. Elle taisait ce qu'elle avait vu au-delà, et cette omission suffisait à rendre le verdict
inexploitable. **Mesurer ce que le corpus VOIT avant d'accuser sa couverture** est ce qui a séparé
les deux hypothèses en une seule interrogation du dict.

Corollaire : **une contradiction entre le code et son propre docstring n'est pas un arbitrage à
justifier — c'est un bug à aligner.** Le docstring affirmait la monotonie pour les deux modes ;
une seule branche l'appliquait. Chercher « pourquoi cette asymétrie » aurait fait inventer une
raison à ce qui n'en avait pas.

⚠ **Ce dossier CONSOMME les numéros qu'il cite** — le corpus est l'union, mentions comprises
(`case-468` §9). `#477-r14`, `#66-r1`, `#437-r1-r2` et les autres trous nommés ici sont désormais
**pris par cette fiche**. Sauter un entier est le bon côté de l'asymétrie, mais il faut le savoir :
un outil d'attribution qui se lit lui-même contamine sa propre démonstration.

---

## 5. Résidus

* **`#468-r12` — N3 reste irréductible, et seule la parade (b) le fermerait.** Deux `--suggere`
  lancés **au même instant** rendent toujours le même numéro : `gh` couvre les PR **écrites**, pas
  les numéros **alloués et pas encore écrits**. La seule parade restante est un **registre de
  réservation versionné**, qui **sérialise** l'allocation (commit + push par numéro) — coût de
  merge à chaque résidu ouvert, exactement ce que `case-468` §9.1 avait écarté. L'arbitrage n'a pas
  bougé ; ce qui a bougé, c'est qu'il ne reste plus **que** lui.
* **Les PR au-delà des 200 plus récentes ne sont pas lues.** Mesuré aujourd'hui : **0 changement de
  numéro** à 670. Ce n'est pas une garantie — c'est un chiffre qui se re-dérive, et la sortie le
  dit (`les plus ANCIENNES ne sont PAS lues`).
