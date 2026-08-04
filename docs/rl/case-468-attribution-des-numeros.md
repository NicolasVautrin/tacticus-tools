# #468 — l'attribution des NUMÉROS de tâche et de résidu

**Critère binaire** : un numéro peut-il être attribué deux fois sans que rien ne le dise ?
**Oui, et ça arrive** — deux occurrences indépendantes le 2026-08-04, à quelques heures d'écart.
Un cliquet le voit désormais, et il a trouvé **une troisième collision, quadruple, jamais vue à
l'œil**.

---

## 1. Le défaut

Rien n'alloue les numéros de ce dépôt. Ils sont pris au vol par qui en a besoin — un agent qui
ouvre un résidu, un rapport qui en nomme un, l'orchestrateur qui dispatche. Toute la traçabilité
en dépend pourtant : `docs/rl/case-<n>-*.md`, `scripts/python/probe_<n>_*.py`,
`scripts/python/tests/**/test_<n>_*.py`, les lignes de `docs/rl/backlog.md`, et les **messages de
commit** (`git log --grep` en dépend).

Les deux occurrences mesurées :

| numéro | dossier 1 | dossier 2 | découvert |
|---|---|---|---|
| `#465` | ledger `probe_462` (PR #560) | état de boucle (PR #562) | à l'œil, au merge — **deux `#465-r1` à neuf lignes d'écart** dans `backlog.md` |
| `#448-r1-r1-r2` | résidu de PERFORMANCE (ligne de backlog) | second bras d'`IsLikeFlying` (PR #571) | à l'œil, **après** le dispatch |

**Le coût est ASYMÉTRIQUE selon le moment où on la trouve.** Avant livraison, c'est un choix de
nom. Après, c'est une **réécriture d'historique** : fichiers, résidus, références internes, ET
messages de commit. C'est ce qui justifie un garde mécanique plutôt qu'une convention écrite —
une convention arrive toujours au bon moment pour celui qui y pense, et jamais pour les autres.

---

## 2. Le critère : DÉFINITION, jamais MENTION

C'est le cœur du problème. Un cliquet qui rougirait sur la simple présence de `#<n>` rougirait
sur la quasi-totalité du dépôt : les renvois croisés y sont la norme (une case-doc qui cite le
résidu d'une autre, une colonne « Point d'entrée » qui pointe la voisine, un commit qui référence
un numéro).

**DÉFINITION** — le numéro est en position d'**identifiant d'entrée**. Trois positions, et trois
seulement :

| # | position | forme |
|---|---|---|
| (a) | **première cellule** d'une ligne du tableau de `backlog.md` | `\| #465-r1 \| **titre** \| [opus] \| ptr \|` |
| (b) | **tête** d'une puce de premier niveau de `backlog.md` | `- **`#420-r1`** — …` |
| (c) | **préfixe** d'un nom de fichier `docs/rl/case-<n>-*.md` | `case-448-r1-r1-r2-second-bras-…md` |

**MENTION** — tout le reste, et le cliquet ne la lit **jamais**.

**Mesure de séparation**, rejouée à chaque run (étape 0b) : sur `docs/rl` (532 fichiers),
**6 580** occurrences `#<n>` pour **836** définitions — **12,7 %**. L'échantillon négatif est donc
le dépôt lui-même, et il pèse sept fois plus que le positif. (Chiffres à **re-dériver**
— `--report` —, pas à citer : ils bougent à chaque tranche livrée.)

Trois détails que la mesure a imposés :

* **La puce est ancrée en début de ligne, sans espace de tête.** Une puce *indentée* est une
  continuation ou une sous-puce, jamais l'ouverture d'un dossier — et les lignes de continuation
  du backlog portent des dizaines de renvois. Le test `test_aucune_mention_reelle_du_backlog_…`
  les passe toutes.
* **Le barré se lit AVANT le numéro.** `~~#462~~` est clos ; un `~~…~~` situé *après* le numéro ne
  barre que le titre (`| #448-r1-r1-r1-r1-r1 | ~~**à moitié**~~ **…** |` reste ouvert).
* **Les deux graphies se rejoignent.** Le dépôt écrit `#366-r1` et `#366r1` pour le même résidu
  (`case-366-r1-camo-seed.md` à côté de `case-366r1-echoes-from-the-warp-revive.md`). La
  normalisation retire `-` et `_` : sans elle, une collision passerait entre les deux écritures.

---

## 3. Ce que la CONFRONTATION a changé — deux formes sur trois sont RÉFUTÉES

Trois formes avaient été relevées à l'œil. Passées au dépôt, **une seule est décidable**.

### 3.1 « Deux `case-<n>-*.md` pour un même `<n>` » — RÉFUTÉE

**33 identifiants** portent ≥ 2 case-docs, dont `366r1` avec **26 fichiers**, `224` avec 6, `217`
et `231` et `250` avec 4. Ce sont des **tranches d'une même tâche**, livrées au fil de l'eau.

Aucun critère textuel ne sépare un multi-items d'une collision : les deux ont le même numéro et
des sujets sans rapport. `case-217-blackrage` / `-stormcaller` / `-thequickening` /
`-phantom-action-routing` sont indiscernables, de l'extérieur, de deux tâches qui auraient pris
`#217`.

Même réponse pour les artefacts de **code** : **73** identifiants portent ≥ 2 `probe_<n>_*.py`,
**36** portent ≥ 2 `test_<n>_*.py` (le couple `_live` / `_offline` à lui seul).

⇒ Rendue en **inventaire** (`--report`), jamais bloquante. Le constat est **figé par un test**
(`test_forme_C_deux_case_docs_n_est_PAS_un_critere`) : si le gisement se tarissait, la forme
redeviendrait peut-être gardable — et il faudrait alors réfuter ce test avant de la faire rougir.

### 3.2 « Un `<n>` à la fois dans une ligne OUVERTE et dans une case-doc » — INDÉCIDABLE, gardée par LEDGER

**8 identifiants** en cohabitation (11 paires, `#217` en portant 4), **7 légitimes** :

| identifiant | pourquoi c'est légitime |
|---|---|
| `#202` | la case-doc **est** celle de la tâche ; tranches A/B/C livrées, ligne ouverte pour le résidu |
| `#217` (×4) | tâche-**parapluie** (P0 décider≠exécuter, 20 actives) qui livre ses items un par un |
| `#369` | même sujet mot pour mot ; ligne non barrée car le correctif est livré mais **inerte** |
| `#419-r1` | la case-doc se déclare « sixième résidu ATTACK de #419-r1 fermé », et la ligne cite cette livraison |
| `#419-r1-tr14-r5-r2-r1-r1-r1` | la case-doc ferme 15 des 43 `ShouldExecute`, la ligne garde les autres |
| `#437-r1` | **dossier ré-ouvert** : même écart de 1 point sur le même test overwatch |
| `#437-r1-r1-r3` | **dossier CLOS dont la ligne n'a pas été barrée** — entré par un merge pendant cette tranche ; la case-doc **réfute** le résidu que sa ligne décrit |

**Quatre critères dérivés ont été essayés pour séparer les légitimes du vrai positif — les quatre
échouent**, et la plupart en *ratant* la vraie collision :

| critère essayé | verdict |
|---|---|
| « la ligne cite le nom de fichier de la case-doc » | 5 faux positifs (seul `#369` cite le nom exact) |
| « la ligne cite un préfixe `case-<n>` » | **rate `#420-r1`** : sa ligne cite `case-420`, préfixe de sa propre case-doc |
| « la colonne Modèle porte un tag `[opus]`/`[fable]` » | n'écarte que `#369` — 5 faux positifs restants |
| « comparer le titre H1 de la case-doc au titre de la ligne » | comparaison de sujets : indécidable par construction |

⇒ Gardée par **ledger** (`scripts/ratchets-468-numeros-attestes.json`, patron `probe_462`) :
chaque cohabitation connue porte sa **raison**, obligatoire et non vide. Toute cohabitation
**nouvelle** rougit — c'est-à-dire exactement le geste de l'occurrence `#448-r1-r1-r2` : livrer
une case-doc sous un numéro qu'une ligne de backlog ouvrait déjà pour autre chose.

Le coût est faible **par mesure** : 11 paires sur **451** case-docs. Et le flux est réel sans être
lourd — **une cohabitation neuve est entrée par un merge pendant cette tranche même**
(`#437-r1-r1-r3`), tranchée sur pièces en une lecture d'en-tête.

### 3.3 « Deux définitions de `#<n>-r<k>` à des lignes différentes du backlog » — RETENUE, restreinte

C'est la seule forme décidable **sans jugement** : une tâche = une ligne ; deux lignes **ouvertes**
= deux tâches sous un numéro.

La restriction « ouvertes » est ce qui la rend exploitable. Sans elle, 3 identifiants rougissent ;
avec elle, **1**. Les deux écartés (`#27-r4`, `#437-r1`) ont une ligne **barrée** (dossier clos) à
côté d'une ligne ouverte du **même** sujet — une ré-ouverture, pas deux dossiers.

**Zéro faux positif mesuré.**

---

## 4. Ce que le cliquet a trouvé : `#420-r1` porte QUATRE dossiers

Trouvé au premier passage, jamais vu à l'œil, **encore ouvert** :

| dossier | où | sujet |
|---|---|---|
| A | ligne **barrée** `backlog.md:294` + `case-420-r1-dotgg-extra-dmg-gate.md` | axe DÉGÂT de `DefenderOfTheGreaterGood` (1182 / drone 1306) — **LIVRÉ** |
| B | ligne **ouverte** `backlog.md:342` | les 16 quotes verbatim `FUN_<addr>(0x4d\|0x50, …)` indécidables |
| C | puce **ouverte** `backlog.md:547` | « pré-perçage » FAUX dans quatre docstrings d'aura-dégât |
| D | puce **ouverte** `backlog.md:555` | filtre CARRIER `UnitsWithRangedWeaponsExcludingDamageProfile` non porté |

**Rien n'est renuméroté ici.** Le dossier A est **livré** : le renommer réécrirait l'historique,
et c'est précisément le coût que cette tâche existe pour éviter de payer par surprise. L'arbitrage
revient à l'orchestrateur. La collision est donc **figée** au ledger avec le statut
`COLLISION-OUVERTE` et **ré-imprimée à chaque run** — un ledger n'est pas un silencieux, c'est une
ligne de base.

---

## 5. Ce que le cliquet garde

`scripts/python/probe_468_collision_numeros.py`, dans la banque (`scripts/ratchets.ps1`) :

| étape | ce qu'elle voit | bloquante |
|---|---|---|
| 0a | **auto-test** des détecteurs, 21 cas positifs et négatifs jumelés | oui |
| 0b | **contre-épreuve sur pièces** : ventilation définitions / mentions du dépôt réel, plus le garde d'**indigence du corpus** (un balayage qui rend zéro se lit « rien à signaler ») | oui |
| 1 | **double ouverture** : ≥ 2 définitions non barrées du même identifiant | oui |
| 2 | **cohabitation** ouvert-au-backlog × case-doc, non attestée au ledger | oui |

**Tri-état** (contrat de banque `scripts/ratchets-verdict.ps1`, #471) : `0` vert · `N` rouges de
gisement · **`99` INDISPONIBLE** quand le *montage* a échoué. La frontière est appliquée telle que
le contrat la pose — « un dépôt PARFAIT aurait-il subi ce même échec ? » :

| situation | état | pourquoi |
|---|---|---|
| `docs/rl` introuvable (CWD faux, `--racine` erroné) | **99** | le dépôt n'est pas en cause |
| `OSError` sur `backlog.md` ou le ledger (verrou, droits) | **99** | idem |
| `backlog.md` absent ou réduit à du **blanc** | **ROUGE** | fait sur le **contenu** — le registre a disparu |
| ledger au **JSON invalide** | **ROUGE** | le ledger est *dans* le dépôt |
| corpus indigent | **ROUGE** | même frontière que « `git ls-files` rc=0, liste vide » |

Le troisième cas a été **trouvé par la contre-épreuve, pas à la relecture** : `not lignes` ne suffit
pas, `"\n".splitlines()` rend `['']`, qui est **vrai**. Un backlog réduit à du blanc passait donc
pour mesuré.

Deux points de conception, chacun payé par un test :

* **La portée `@backlog`.** Une attestation de cohabitation (étape 2) ne doit *jamais* dispenser
  de la double ouverture (étape 1) : ce sont deux constats. Sans portée distincte, attester le
  premier aurait posé un silencieux sur le second par mégarde
  (`test_bout_en_bout_une_attestation_eteint_la_cohabitation_pas_la_double_ouverture`).
* **Une attestation sans raison est refusée** (rc 2). Une attestation vide est un blanc-seing, et
  c'est exactement ce que ce cliquet garde.

---

## 6. Contre-épreuve

**Le garde mord.** Quatre mutations du probe, quatre rouges du test — chaque mutation vérifiée
comme **appliquée** avant le run (un patch qui ne matche pas rend vert et ne prouve rien) :

| mutation | test qui tombe |
|---|---|
| puce **non ancrée** (une continuation ouvrirait un dossier) | `test_aucune_mention_reelle_du_backlog_…` |
| étape 1 compte aussi les entrées **barrées** | `test_forme_A_une_ligne_BARREE_ne_compte_pas` |
| normalisation qui ne joint plus `#366-r1` et `#366r1` | `test_forme_A_les_deux_graphies_se_rejoignent` |
| étape 2 **ignore le ledger** (tout réputé attesté) | `test_bout_en_bout_…` |

**Et il reste vert sur le légitime.** Les bras non mutés sont verts dans chaque test — sans quoi
les rouges ne prouveraient rien. L'échantillon négatif n'est pas synthétique : lignes de
continuation réelles du backlog, 400 messages de commit réels, les 448 noms de case-docs.

Le bout-en-bout joue le probe **en sous-processus** contre un dépôt jetable
(`mkdtemp()` **sans** `dir=` — #455) : c'est le câblage (lecture, ledger, code de sortie) qui est
gardé là, pas seulement les détecteurs. C'est par ce trou que `probe_181` rendait `0`
inconditionnellement (#430).

Périmètre : le balayage est **confiné** à `docs/rl` et `scripts/python` (jamais la racine), donc
`probe_440` R1 et R3 le laissent passer — vérifié, vert.

### 6.1 Un rouge de banque trouvé **au rejeu après rebase**, et qui n'est pas de cette tranche

Le rebase sur `origin/master` a fait rougir `probe_457:s2` :
`tests/test_431_build_pin_offline.py::test_le_nettoyage_des_residus_est_IDEMPOTENT_et_chirurgical`,
sur `OSError [Errno 22] Invalid argument` en ouvrant `scripts/python/probe_88_on3_emitter.py` en
écriture. **Ce n'est pas cette tranche** : `master` n'a touché aucun des fichiers en cause, le test
passe **37/37 en isolé**, et le test de #468 tombe dans un **autre shard** (6, pas 2).

C'est une **course**, et elle est structurelle : `test_431` fait `write_bytes` **en place dans
`scripts/python/`** pendant que les 40 autres cliquets énumèrent et lisent ce même arbre. Sous
Windows, une écriture en place ne déplace aucune entrée de répertoire — mais elle fait échouer
l'**ouverture** concurrente du fichier. `probe_440` R3 ne le voit pas, deux fois : son périmètre
est l'ensemble des **entrées** de `ratchets.ps1` (ce test est joué *indirectement*, par
`probe_457`), et il exclut la réécriture en place **par choix explicite**. Ouvert en `#468-r6` ;
non corrigé ici — l'arbitrage entre « élargir R3 » et « faire travailler `test_431` sur une copie »
appartient au propriétaire de ce cliquet.

⚠ Un rejeu vert ne referme pas ce constat : le symptôme est une course, exactement la leçon de
#455. Mesuré : **1 run sur 2**.

---

## 7. La technique, réutilisable

**Quand un défaut se formule « X apparaît deux fois », le travail n'est pas de compter X — c'est
de séparer les positions où X *existe* de celles où X est *cité*.** Le gisement légitime écrase le
fautif d'un ordre de grandeur (ici 7 pour 1), et un critère par présence est donc désarmé le jour
même. Trois gestes, dans cet ordre :

1. **Énoncer les positions de définition AVANT de coder**, et les rendre énumérables (ici : trois,
   pas « tout ce qui ressemble à un identifiant »).
2. **Mesurer le ratio définitions / occurrences sur le dépôt réel**, et en faire une **étape du
   cliquet** — pas une note. Si le détecteur cesse un jour de séparer, c'est ce chiffre qui le
   dira, pas une relecture.
3. **Confronter chaque forme relevée à l'œil au gisement**, et accepter d'en réfuter. Deux des
   trois formes de cette tâche étaient indécidables ; les coder aurait produit **33 + 7 rouges**
   sur un dépôt sain, c'est-à-dire un cliquet désarmé en une journée. Un critère qu'on ne peut pas
   rendre décidable se garde par **ledger**, ou pas du tout — jamais par un seuil arbitraire.

Corollaire qui a servi ici : **quand aucun critère dérivé ne sépare deux populations, l'écrire
noir sur blanc avec les critères ESSAYÉS ET RÉFUTÉS vaut mieux qu'un critère approximatif.** Les
quatre du §3.2 sont dans la case-doc pour que personne ne les re-essaie.

---

## 8. Résidus

* **`#468-r1` — les tokens purement NUMÉRIQUES ne prolongent pas l'identifiant.**
  `case-302-2-prediction-tile-target.md` est lu `302`, alors que son identifiant réel est `302-2` ;
  les absorber casserait `case-229-1502-rites-of-morkai-*`, où `1502` est un **id d'ability**. Rien
  ne distingue les deux au niveau du nom. Effet : quelques identifiants à suffixe numérique se
  regroupent sur leur racine — côté **sûr** (ça peut faire voir une cohabitation, jamais la
  manquer). Trancher demanderait une convention d'écriture, pas un détecteur.
* **`#468-r2` — le cliquet ne voit pas la collision AU MOMENT où elle naît.** Il lit l'arbre, pas
  le diff : il mord quand la définition en trop est **livrée**, c'est-à-dire au dernier moment
  utile — juste avant la PR, quand renommer ne coûte encore qu'un choix de nom. Un mode `--gate
  <ref>` (patron `probe_462`) pointerait la définition **introduite par la PR** plutôt que
  l'identifiant ; le gain serait un message plus précis, pas une détection de plus.
* **`#468-r3` — les probes et les tests ne sont pas des positions de définition.**
  `probe_<n>_*.py` et `test_<n>_*.py` portent le numéro mais suivent le dossier de leur tranche
  (73 et 36 identifiants à ≥ 2 fichiers, §3.1) : ils sont inventoriés, jamais gardés. Une
  collision qui ne se manifesterait QUE par deux probes de sujets différents passerait — non
  mesurée, et probablement vide (un probe naît avec sa case-doc).
* **`#468-r4` — l'attribution reste manuelle.** Ce cliquet dit qu'un numéro est pris ; il n'en
  **donne** pas un libre. Un `--suggere` (le plus petit entier non défini, toutes positions
  confondues) supprimerait le geste fautif au lieu de le rattraper.
