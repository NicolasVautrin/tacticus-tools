# #468 — l'attribution des NUMÉROS de tâche et de résidu

**Critère binaire** : un numéro peut-il être attribué deux fois sans que rien ne le dise ?
**Oui, et ça arrive** — deux occurrences indépendantes le 2026-08-04, à quelques heures d'écart.
Un cliquet le voit désormais, et il a trouvé **une troisième collision, quadruple, jamais vue à
l'œil** — depuis **résolue** (§4).

Le cliquet **rattrapait** le geste fautif ; `--suggere` le **supprime** en donnant un numéro libre
(§9), sur un critère qui est l'exact opposé du sien. Et le soupçon de dette qui avait lancé la
tranche — « 85 identifiants cités sans définition » — est **réfuté** : **0 orphelin** (§8).

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

## 4. Ce que le cliquet a trouvé : `#420-r1` portait QUATRE dossiers — **RÉSOLU**

Trouvé au premier passage, jamais vu à l'œil :

| dossier | où | sujet | devenu |
|---|---|---|---|
| A | ligne **barrée** + `case-420-r1-dotgg-extra-dmg-gate.md` | axe DÉGÂT de `DefenderOfTheGreaterGood` (1182 / drone 1306) — **LIVRÉ** | garde `#420-r1` |
| B | ligne **ouverte** | les 16 quotes verbatim `FUN_<addr>(0x4d\|0x50, …)` indécidables | **`#420-r5`** |
| C | puce **ouverte** | « pré-perçage » FAUX dans quatre docstrings d'aura-dégât | **`#420-r1-r1`** |
| D | puce **ouverte** | filtre CARRIER `UnitsWithRangedWeaponsExcludingDamageProfile` non porté | **`#420-r1-r2`** |

A est **livré** : le renommer réécrirait l'historique — fichiers, références, messages de commit —
c'est-à-dire le coût même que cette tâche existe pour ne plus payer par surprise. B, C et D
n'avaient aucun artefact : les renuméroter ne coûtait qu'un choix de nom.

**Le rattachement se LIT, il ne s'invente pas**, et les trois ne vont pas au même endroit. B pointe
`case-420` §9 et siège entre `#420-r2` et `#420-r4` : c'est un résidu de la **tâche #420**, mal
numéroté en `-r1` → `#420-r5`. C et D pointent `case-420-r1-dotgg-extra-dmg-gate.md`, la case-doc
de **A** : ce sont de vrais résidus **de A** → `#420-r1-r1` et `#420-r1-r2`, la filiation que le
dépôt écrit déjà (`#433-r3-r1a-r1`, `#419-r1-tr14-r5-r2-r1-r1-r1`). Les trois identifiants sortent
de `--suggere` (§9).

Mesure de la résolution : étape 1 **1 → 0**, étape 2 **11 → 10**, et le ledger ne porte plus
**aucune** `COLLISION-OUVERTE`.

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

## 8. Le tri des « cités sans définition » : **0 orphelin**, et un axe qui s'inverse

Le soupçon de départ : 85 identifiants cités dans les case-docs n'ont aucune définition en
colonne 1 du backlog — une dette possible. **Réfuté par la ventilation.**

Périmètre restreint aux **résidus** (`-r<k>`, `-tr<k>`…), les seuls non ambigus : un `#472` nu peut
être une PR GitHub ou un ordinal (`« du Triggered #1 »`), un `#472-r1` ne peut être que d'ici.

| | n | verdict |
|---|---|---|
| résidus cités dans les case-docs | 333 | |
| — définis au backlog | 242 | |
| — **sans définition au backlog** | **91** | à trier |
| … case-doc à leur nom (position (c)) | 12 | **définis** ailleurs |
| … `probe_<n>` / `test_<n>` à leur nom | 6 | employés |
| … mentionnés au backlog sans y être définis | 39 | employés |
| … descendants d'un identifiant défini | 30 | employés |
| … **aucune trace ailleurs** | **4** | à ouvrir |

Et les 4 derniers sont **employés aussi** : `#336-r1` est le résidu-mère que `case-343` traite
(son H1 le dit), `#472-r1/-r2/-r3` sont définis en **puces d'une case-doc** (`case-467` §Résidus),
position que le critère ne lit que dans `backlog.md`.

⇒ **0 orphelin, 0 collision.** Les 91 ne sont pas une dette : `backlog.md` ne liste **que les
tâches ouvertes**, par conception — son propre en-tête le dit. « Cité sans définition au backlog »
mesure donc le travail **fini**, pas un trou.

**Ce que le tri a réellement produit, c'est l'inversion du critère.** Le découpage
citation/définition est le bon axe pour **détecter** (§2) et le mauvais pour **attribuer** : les
4 « orphelins » sont introuvables par les positions de définition, et pourtant tous pris. D'où §9.

---

## 9. `--suggere` — ATTRIBUER n'est pas DÉTECTER (`#468-r4`, fermé)

Les étapes 1 et 2 **rattrapent** le geste fautif. `--suggere` le **supprime** : elle donne un
identifiant libre — une racine, ou le plus petit `r<k>` sous un parent.

**Son critère est l'exact opposé.** Détecter exige de séparer définition et mention (87 % des
occurrences sont des renvois légitimes ; un critère par présence serait désarmé le jour même).
Attribuer exige l'**union** : un numéro seulement **mentionné** est déjà pris — c'est
littéralement l'occurrence `#448-r1-r1-r2`, où le rapport employait le numéro avant tout artefact.
C'est aussi ce qui rend `--suggere` insensible aux trous connus du détecteur (`#468-r1/-r2/-r3`,
et la puce de case-doc) : elle n'a pas besoin de savoir ce qu'est une définition.

**Trois mesures ont dicté la forme :**

* **L'historique compte.** 13 racines pures < 500 — dont `#28`, `#269`, `#297`, `#300`, `#307` —
  n'existent **que** dans les messages de commit. Le corpus documentaire les donne pour des trous
  libres ; `git log --grep` prouve le contraire. ⇒ **une mesure incomplète ne rend jamais de
  numéro** : git muet → `INDISPONIBLE` (99), rien de suggéré. Suggérer sur un corpus amputé
  fabrique exactement la collision qu'on prétend éviter.
* **La borne se dérive, et doit être filtrée.** C'est la plus grande racine **définie** que
  `backlog.md` connaît. Sans le filtre « connue du backlog », elle saute à **1547** : les noms
  `case-1014-*`, `case-1203-*`, `case-1547-*` portent des id d'ability, pas des tâches. Elle n'a
  pas besoin d'être exacte, seulement **≤ la vraie frontière** — le balayage avance jusqu'au
  premier libre.
* **On ne recycle pas un trou**, même libre : il peut être réservé par une PR **en vol**, que
  l'arbre ne voit pas. La suggestion est **monotone** ; les 31 trous sont listés, jamais proposés.

**Le coût était un défaut fonctionnel, pas un confort** — 111 s pour rendre un numéro, et un outil
qu'on attend deux minutes ne sera pas utilisé, donc ne supprimera aucun geste. Le suspect évident
était **faux** : la regex coûte 0,1 s sur le corpus déjà en mémoire ; c'est la **lecture** de
2 284 fichiers qui dominait. `git grep` la remplace — **0,6 s**, résultat strictement équivalent
(0 manquant, 0 en trop, vérifié dans les deux sens), pathspecs bornés donc `.claude/worktrees/`
hors de portée par construction (#434).

⚠ **Le périmètre n'était pas réductible** : l'apport marginal du contenu des `.py` est de 34
identifiants, dont la racine **476** — précisément ce que `docs/rl` seul donnait pour libre.
C'était la lecture à accélérer, pas la source à retirer.

### 9.1 Pourquoi PAS un fichier de registre

L'autre forme possible était un fichier d'allocation versionné. **Écartée**, et pas sur une
préférence :

* **Il se paierait à chaque merge.** `scripts/ratchets-462-live-attestations.json` est le
  précédent mesuré — point de conflit connu et documenté (`#462-r2`). Un registre que *toute* PR
  ouvrant un résidu devrait toucher serait pire : la fréquence est plus haute.
* **Il serait redondant.** L'information existe déjà, complète, dans l'arbre — c'est ce que §8
  établit : **0 orphelin**, tout numéro employé est trouvable. Un registre n'ajouterait aucune
  donnée, seulement une **seconde source à tenir synchronisée**, donc une occasion de divergence.
* **Il ne peut pas être plus frais que l'arbre.** Un fichier ne connaît que ce qu'on y a écrit ;
  `--suggere` voit aussi ce que personne n'a déclaré — les mentions en prose et les messages de
  commit, d'où viennent 13 racines qui n'existent nulle part ailleurs.

⇒ **Le registre est DÉRIVÉ, pas tenu.** Ce qui reste hors de sa portée est nommé : un numéro pris
par une PR **en vol** (non fusionnée) — d'où la monotonie, qui ne recycle jamais un trou.

### 9.2 Le corpus n'est PAS l'arbre courant (`#468-r10`, fermé)

Tout ce qui précède mesure ce qui est **écrit et fusionné** — or une allocation se fait **au début**
d'une tranche. `--suggere` rendait donc un numéro d'air sûr dans le **seul régime où nos collisions
se produisent** : deux agents dispatchés ensemble ont pris `#479`, collision **double** (racine et
`r1`), pendant que le cliquet rendait `PASS`.

Le corpus couvre depuis lors les **refs hors `HEAD`** (`git log --all --not HEAD`, +0,06 s — un
worktree d'agent est figé à son commit de lancement) et les **noms écrits dans les autres
worktrees** (glob borné, +0,39 s — `git grep --untracked` ne lit que *son* checkout). Effet mesuré :
`--suggere 425` et `--suggere 448` rendaient `#425-r3` et `#448-r3`, **tous deux déjà portés par des
dossiers en vol**. Ce qui reste — un numéro pris et **pas encore écrit** — est irréductible sans
réservation, et se lit dans la section `PORTEE DE LA MESURE`, imprimée **inconditionnellement**.

Détail, parades chiffrées et les cinq mutations :
**`docs/rl/case-468-r10-angle-mort-des-agents-en-vol.md`**.

### 9.3 La MONOTONIE ne valait que d'un côté, et le corps des PR n'était pas lu (`#468-r11`, fermé)

Deux défauts de la même passe, tous deux dans `--suggere`.

**L'asymétrie racine / résidu était une contradiction interne**, pas un arbitrage : le docstring de
`suggerer` affirmait la monotonie pour la fonction entière, et seule la branche racine
l'appliquait. La branche résidu s'arrêtait au **premier trou** et le proposait —
`--suggere 477` rendait `#477-r14` quand `-r15`, `-r16` et `-r17` existent. **Les résidus au-delà
du trou étaient VUS** (mesuré dans `employes()`, pas déduit de la sortie : 2 case-docs, 3 probes,
1 test, `git log`, une ref non fusionnée, 5 worktrees) — c'est la **restitution** qui n'imprimait
que le préfixe contigu. **11 parents sur 218** étaient dans ce cas. Les deux modes partent
désormais du plus grand pris + 1, et les trous sont listés.

**Le corps d'une PR n'entre JAMAIS dans l'arbre** — le squash-merge ne le recopie pas dans le
message de commit. `git grep -E "479-?r2"` et `git log --all --grep "479-r2"` rendent **0**, et
pourtant la PR #663 y ouvre `#479-r2` : `--suggere 479` le rendait comme libre. La parade **(c)**
de `#468-r10` est donc construite, et le **même protocole** qui avait refusé ses deux extensions
(0 changement de numéro) la **retient** : **2 changements** sur l'arbre vivant. `GH_LIMITE_PR = 200`
— à 670 PR, **0 changement de plus** pour ×1,9 le coût. Le capteur ne lève **pas** `Indisponible`
(appoint, comme `git worktree list`) mais sa panne est **nommée par son stderr**, jamais rabattue
sur `[]`, et sans aucun cache. Détail, chiffres et les 9 mutations :
**`docs/rl/case-468-r11-monotonie-des-deux-modes-et-corps-des-pr.md`**.

⚠ **Sous flotte chargée, `git grep` passe de 0,6 s à 20-40 s** (3 mesures dans chaque régime, à
10 worktrees actifs) : de la **contention git** pure — `.git/` est partagé — et non un effet de
`--untracked`, sans lequel c'est même plus lent. `--suggere` n'est pas dans la banque et le chemin
bloquant ne l'appelle pas : ce coût ne touche pas le mur des cliquets. Constat utile à `#471-r2`,
dont l'hypothèse de contention n'était pas établie — il la rend **observable et chiffrée**, sans
trancher la cause du `128`.

---

## 10. Résidus

* ~~**`#468-r1` — les tokens purement NUMÉRIQUES ne prolongent pas l'identifiant.**~~ —
  **RÉSOLU (2026-08-15), et son énoncé était FAUX du côté le plus important** : voir §11.1. La
  grammaire ne *repliait* pas sur la racine, elle faisait **DISPARAÎTRE** — **72 lignes de
  tableau** du backlog n'étaient AUCUNE définition. Ce qui reste ouvert n'est pas un détecteur
  mais une **convention d'écriture** : `normaliser` retire les tirets, donc `#222-1` et un futur
  `#2221` sont indistinguables, et `--suggere` subit déjà cette confusion à l'identique.
* ~~**`#468-r2` — le cliquet ne voit pas la collision AU MOMENT où elle naît.**~~ —
  **LIVRÉ (2026-08-15)** : `--gate <ref>`, §11.2. Merge-base (jamais `ref` nu), arbre de travail
  inclus, appariement par le **texte** de la ligne. Gain de précision, pas de détection — comme
  l'énoncé le prévoyait.
* ~~**`#468-r3` — les probes et les tests ne sont pas des positions de définition.**~~ —
  **MESURÉ (2026-08-15), critère REFUSÉ**, §11.3. Le « probablement vide » est **faux** :
  **177** identifiants n'ont AUCUNE autre position que du code, dont **40** à ≥ 2 fichiers. Mais
  **0 collision établie** — donc inventaire, comme §3.1.
* ~~**`#468-r4`**~~ — **FERMÉ** par `--suggere` (§9).
* ~~**`#468-r10`**~~ — **FERMÉ** (§9.2) : `--suggere` lit les refs hors `HEAD` et les autres
  worktrees, et **nomme** l'angle mort qui reste. Ouvre `#468-r11` (parade `gh`, non construite).
* ~~**`#468-r11`**~~ — **FERMÉ** (§9.3) : la monotonie vaut des **deux** côtés, et le **corps des
  PR** est lu (parade (c) construite, 2 numéros rendus changent). Ouvre **`#468-r12`** — N3 reste
  irréductible, il ne reste plus que la parade **(b)**, le registre de réservation versionné, que
  §9.1 avait écarté sur son coût de merge. Cet arbitrage-là n'a pas bougé.
* ~~**`#468-r7` — la puce de résidu d'une case-doc n'est PAS une position de définition.**~~ —
  **RÉSOLU (2026-08-15)**, §11.4 : la 4ᵉ position est **portée et mesurée**, puis rendue en
  **INVENTAIRE** (`--report`), jamais bloquante. Le remède que l'énoncé proposait — « un critère
  de SECTION » — est **réfuté par la mesure** ; celui qui marche est le **propriétaire au plus
  long préfixe**, et il préserve le cas motivant.
* **`#468-r8` — `#<n>` désigne à la fois une TÂCHE et une PULL REQUEST, sans rien pour les
  distinguer.** Mesuré : `case-434` écrit « 3 PR intégrées entre-temps : #472, #473, #474 » quand
  `case-467` §10 ouvre la **tâche** `#472`. Les deux espaces se remplissent en parallèle — tâches
  à ~474, PR à ~595 — et 39 racines de la plage 501-588 sont déjà citées comme PR. Rien ne casse
  aujourd'hui (`--suggere` traite l'union, donc côté sûr : il saute les numéros de PR cités), mais
  `git log --grep "#<n>"` est **structurellement ambigu**, et c'est la voie que le §1 nomme comme
  dépendante. Trancher demanderait une convention d'écriture (préfixer les PR), pas un détecteur.
  — **FERMÉ (2026-08-14)** par la **BANDE** (`PLANCHER_RACINE = 10000`), cf. CLAUDE.md.
* ~~**`#468-r13` — l'espace des TÂCHES a rattrapé celui des PR, et `--suggere` est aveugle aux
  commits de MERGE.**~~ — **RÉSOLU (2026-08-15)**, §11.5. Volet **(a)** livré ; volet **(b)** sans
  objet, `#468-r8` l'a tranché par la bande.

---

## 11. Ce que la tranche du 2026-08-15 a mesuré, et ce qu'elle a refusé

Cinq résidus instruits d'un coup au même foyer. **Trois énoncés sur cinq étaient inexacts**, et
c'est la mesure qui l'a dit — jamais la relecture.

### 11.1 `#468-r1` — la grammaire ne repliait pas, elle faisait DISPARAÎTRE

`ID` s'arrête au premier segment qu'il ne sait pas lire (`-c1`, `-b-r1`, `-src`, `-1`, une
majuscule). Comme `RE_LIGNE_TABLEAU` exige un `|` **juste après** l'identifiant, la ligne
**entière** cesse de correspondre : elle ne se replie pas sur sa racine, elle sort du registre.

| | n |
|---|---|
| lignes de tableau du backlog INVISIBLES au détecteur | **72** (7 % du registre) |
| — familles `#462-r4b-…-b/-c-r<k>` / `#462-r4e-o-r<k>` / `#366-r1-<mot>` | 31 / 9 / 13 |
| — `#433-r4-r2-r1-r1-a/c-r<k>` / `#443-r2-b<k>` | 3 / 2 |
| — non numériques (`#o10-a/-c`, `#PAI-c/-k`, `#BL-*`, `#haze-ord`, `#254-bc*`, `#222-1`…) | 14 |
| clés portant ≥ 2 identifiants ÉCRITS distincts (écrasement) | **12** |

Le correctif est le **principe même du cliquet** poussé jusqu'au bout : en position de définition,
c'est la **cellule** qui dit où l'identifiant finit, pas une grammaire (`ID_POSITION`). `ID` reste
le scanner de **mentions**. Effet : définitions **1872 → 1944**, étape 1 **0 → 0**, étape 2
**inchangée** (26 cohabitations, 4 non attestées, avant comme après).

### 11.2 `#468-r2` — `--gate <ref>`

Trois choix de forme, tous repris de `probe_462_live_tests_status._live_in_diff` : le diff part du
**merge-base** (sinon la gate accuse ce que les autres agents ont poussé — quatre PR mergées en
deux heures sur ce dépôt) ; l'**arbre de travail** est inclus (mordre avant le commit, tant que
renommer est gratuit) ; l'appariement se fait par le **texte** de la ligne, jamais par son numéro,
`backlog.md` étant le fichier le plus partagé du dépôt. Ref inconnue ⇒ **99**, jamais un vert.

Le cliquet a **deux bras opposés**, et c'est le second qui prouve quelque chose : une collision
**déjà présente dans le merge-base** doit laisser la gate **VERTE** alors que le balayage complet
du même arbre est **ROUGE**. Sans lui, le test serait vert sur une gate qui n'a jamais ouvert
`git diff`.

### 11.3 `#468-r3` — le gisement n'est pas vide, et il reste indécidable

Sur **928** identifiants portés par un `probe_<n>`/`test_<n>`, **177** n'ont aucune autre position
et **40** portent ≥ 2 fichiers : le « probablement vide » est faux. Mais les cinq plus ambigus par
leurs slugs, tracés par une **seconde source** (`git log --grep`), donnent **3 tranches
multi-facettes** (`#1066` = « les trois dernières faces DECISION d'actives de kit ») et **2
indécidables** (dossier clos, sans case-doc). **0 collision établie** ⇒ inventaire, comme §3.1.
`--report` imprime désormais cette sous-population, au lieu du compte brut qui la noyait.

### 11.4 `#468-r7` — la 4ᵉ position, portée puis rendue en inventaire

| | n |
|---|---|
| case-docs à section « Résidus » (sections) | **435** / 869 (520) |
| puces de tête `#<n>` dans ces sections | **588** |
| identifiants OUVERTS en puce | **456**, dont **104 sans aucune autre position** |
| doubles avec le critère de SECTION SEUL | **33** ⇒ le remède proposé ne sépare pas |
| doubles après le discriminant PROPRIÉTAIRE | **6** (fichiers différents) **+ 3** (même fichier) |
| verdict de lecture de ces neuf | **9/9 légitimes** |

Le discriminant : la case-doc **possède** l'identifiant quand sa clé en est un **préfixe** ; entre
prétendants, le **plus long** gagne ; et **sans propriétaire, toutes les puces définissent** —
sans cette troisième règle, le cas motivant (`case-467` ouvrant `#472-r1`) serait perdu. Taux de
faux positifs **9/9** ⇒ un critère bloquant se ferait désarmer dans la semaine. La seule forme qui
le deviendrait (deux dossiers, **aucun** propriétaire) est **comptée à chaque run** : elle vaut 0.

### 11.5 `#468-r13` — les 647 sujets de merge

`--no-merges` était un défaut jamais examiné, et il jetait la **seule** trace que le squash-merge
laisse dans l'arbre. **698** merges, dont **647 portent un `#`** ⇒ **96 identifiants inédits** et
**1 numéro rendu change** : `--suggere 432` proposait `#432-r1`, livré par la **PR #479**, alors
que `git grep -E '#432-?r1'` rend **0**. Coût **nul**.

**Troisième extension mesurée puis REFUSÉE**, même protocole que les deux de §9.2 :
`_identifiants_des_refs_hors_head` garde son `--no-merges` — **+1,0 s** pour **0** inédit, et la
mesure a été rejouée **hors du régime dégénéré** (un worktree frais ne prouve rien : simulation
d'un retard de 5, 20, 40, 80 commits, apport nul à chaque palier).

### 11.6 Ce qui n'est PAS couvert

* La confusion `#222-1` / `#2221` (`normaliser` retire les tirets) reste entière : c'est une
  convention d'écriture, et `--suggere` la subit déjà.
* `couper_nom` sur les **noms de fichiers** n'absorbe toujours pas les tokens purement numériques
  (`case-302-2-*` → `302`) : l'ambiguïté avec `case-229-1502-rites-of-morkai-*`, où `1502` est un
  id d'ability, n'a pas de discriminant au niveau du nom.
* La 4ᵉ position n'est **pas** bloquante, par mesure — une collision qui n'existerait que là se
  lit dans `--report`, aucun `rc` ne la crie.
* `--gate` ne juge que `backlog.md` et les case-docs **ajoutées** ; un fichier de code neuf
  (`probe_<n>_*.py`) n'y est pas une définition, conformément à §11.3.
