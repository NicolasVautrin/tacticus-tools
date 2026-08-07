# #526 — Inventaire CLASSÉ et PRIORISÉ des résidus moteur

> **Artefact re-dérivable** : `scripts/python/probe_526_inventaire_residus.py`
> (`--top 20`, `--tsv <chemin>`, `--detail <id>`, `--portee`, `--mesures-ecartees`).
> La prose ci-dessous se périme ; le script se rejoue. **Re-dériver, ne pas citer.**
>
> Tranche **OFFLINE PURE** : aucun runner, aucun RPC, aucun test live, aucun reinject.
> Aucune réparation — c'est un inventaire.

## 1. Portée mesurée

Le backlog porte **sept** sections. Une seule est dispatchable, et le grep est **borné à
elle** : `## Tâches ouvertes` = **278 entrées** sur **91 racines** (les six autres portent un
autre statut, dont `## Fiches PERIMEES ou REFUTEES — NE PAS re-dispatcher`). Un match non
borné mélangerait les deux — c'est le vice qui a coûté 5 dispatches sur du déjà-mergé le
2026-08-07, sur `combat-ability-coverage.md`.

Ventilation **dérivée** (score moteur vs score harnais, cf. §3 A) :

| périmètre | n | |
|---|---|---|
| `MOTEUR` | 134 | ancre forte : symbole natif, id d'ability, ou chemin `engine/` |
| `MOTEUR-FAIBLE` | 24 | lexique de combat seul |
| `MIXTE` | 15 | égalité des deux scores — lecture humaine requise |
| `HARNAIS` | 96 | |
| `PERIMETRE-INDETERMINE` | 9 | aucun signal |

**Soit 173 côté moteur contre 96 côté harnais.** La ventilation à vue de l'orchestrateur
(176 / 97) est donc **juste à 3 entrées près** — elle n'avait pas besoin d'être corrigée.
Les six plus grosses familles annoncées au brief sont exactes sauf une omission : **#462
pèse 28 entrées** (2ᵉ famille du fichier, derrière #419 à 36), et elle est **entièrement
harnais** (ledger des tests live) — ce qui explique qu'elle n'apparaisse pas côté moteur.

⚠ **Taux d'erreur mesuré de l'étage mécanique sur le périmètre : ~20 % dans le haut du
classement.** Sur les 30 têtes, **6** sont en réalité de l'`OUTILLAGE` et ont été
requalifiées à la main (§4 *écartés*) : elles citent un fichier `engine/` sans que le réparer
change le comportement en bataille. C'est la limite structurelle d'un classement lexical.

## 2. Ce que vaut la confrontation de référence

`docs/rl/port-residuals-inventory.md` est la dernière confrontation item-par-item — **passe 3
du 2026-07-27**, commit `bec119f` (le backlog l'annonce au 2026-07-26 / `7f47c29` : cette
citation est elle-même en retard d'une passe). Onze jours et **~600 PR mergées** plus tard.

Elle est **structurellement inappariable au backlog** : elle indexe par clés internes
(`R8`, `O1`, `N7`, `O4a`…), le backlog par `#<n>-r<k>`. Aucun appariement mécanique n'existe
entre les deux jeux d'identifiants — c'est un résultat, pas un manque de mesure, et c'est ce
qui rend son recalage coûteux. Elle signale de plus elle-même que son §4.d (**13 items « en
veille »**) n'a **aucune colonne Fichiers**, donc échappe à son propre scoping par diff.

**Conséquence pour le dispatch** : ne pas s'en servir comme source de fraîcheur. Elle décrit
un état à 11 jours, sous une clé qui ne se raccorde pas.

## 3. Les trois axes

### A. FRAÎCHEUR — l'axe le plus précieux, et le moins mécanisable

**Résultat principal de la tranche, et il est négatif : la fraîcheur ne se dérive pas.**
`PERIME-CANDIDAT` **10 / 278 (3,6 %)**, `INDETERMINE` **268**. Quatre signaux ont été
mesurés ; deux seulement survivent, et leur rappel est faible.

| signal | mesure | retenu |
|---|---|---|
| `git log` corps compris | **187 / 278** — un résidu est cité par le commit qui l'**OUVRE** | non |
| case-doc au numéro exact | 5 / 278 — très spécifique, rappel nul | non |
| **E1** id en **position de sujet** d'un commit **postérieur** au blame | **7 / 278** | oui |
| **E2** id en position de sujet d'un **titre de PR mergée** postérieure | **10 / 278** (dont 6 invisibles de E1) | oui |
| **E3** chemin cité qui n'existe plus | rend `INDETERMINE (citation morte)` | oui |

La borne de **position de sujet** est ce qui rend E1/E2 utilisables : sans elle,
`docs(#486-r15) : … et le résidu #486-r16` compterait comme une livraison de `#486-r16` alors
qu'il l'**ouvre**.

⚠ **Mode de faux positif NOMMÉ — l'entrée « P0 rolling ».** `#217` et `#419-r1` sont des
compteurs mis à jour à chaque livraison partielle (`~~27~~ 20`, « était 20 ; compte
RE-DÉRIVÉ ») : ils seront marqués périmés **à chaque passe**, et resteront **vivants**. Les
reconnaître au texte barré ou à la formule de recompte.

Sur les 10 candidats : **1 confirmé** (`#haze-ord`, dont le titre porte déjà
`~~…~~ — LIVRÉ (2026-07-29)` : ligne à retirer du backlog), **2 faux positifs P0-rolling**,
**3 probables** (`#437-r1-r1-r3` PR #588, `#448-r1-r1-r1-r1-r2-r1` PR #589,
`#419-r1-tr14-r5-r2-r1-r1-r1` PR #581), **4 harnais**.

**Une mesure ÉCARTÉE, et c'est un résultat** (`--mesures-ecartees`) : « le symbole natif cité
est-il dans `engine/` ? » rend **159/161 sur le nom court** (aucun pouvoir discriminant) et
**135/161 sur le symbole complet** — mais nos ports **citent verbatim** le symbole qu'ils
déclarent non porté (règle d'écriture du `CLAUDE.md`). La présence ne dit donc **rien** du
portage. Écartée du verdict, pas oubliée.

### B. NATURE — dérivée de ce que la ligne AFFIRME

`NATURE-INDETERMINEE` **104 / 278 (37 %)** : le lexique ne couvre pas tout, et un tiers de
non-classé est le prix d'un classement qui refuse de deviner.

| nature | n |
|---|---|
| `NATURE-INDETERMINEE` | 104 |
| `MIRROR-INCOMPLET` | 62 |
| `OUTILLAGE` | 55 |
| `BUG-SILENCIEUX` | 37 |
| `CONFRONTATION-MANQUANTE` | 18 |
| `MESURE-MANQUANTE` | 5 |
| `PROSE` | 2 |

Deux **drapeaux de gravité** orthogonaux, ajoutés parce que la taxonomie seule sous-classait
des symptômes déjà constatés :

- **`E!` écart chiffré** — la ligne porte un écart natif-vs-port **mesuré** (`9575` contre
  `10073`). Ce n'est plus une intention, c'est un symptôme ; +25 au score.
- **`R!` bloqué reinject** — le résidu exige un **capteur neuf** (`frida/hooks`). Il n'est
  **pas dispatchable seul** : il attend une fenêtre qui appartient à l'orchestrateur.

### C. CONFRONTABILITÉ — la voie, jamais un oui/non

`data/unspawnable_rank<N>.json` **n'existe pas** dans l'arbre (mesuré) : le seul refus
légitime de la gate n'a **aucun porteur**. L'axe rend donc la **voie d'arrivée en bataille**.

| voie | n |
|---|---|
| `VOIE-A-ETABLIR` | 135 |
| `SANS-OBJET` (harnais) | 96 |
| `MONTAGE-ECRIT` (un probe existe déjà) | 31 |
| `CONFRONTABLE-CATALOGUE` | 14 |
| `CONFRONTABLE-PAR-GREFFE` (porteurs npc-only) | 2 |

⚠ Un `VOIE-A-ETABLIR` **n'est pas une preuve de mort** : les voies trait / summon /
liveevent / tile ne sont pas dérivées ici, et `unit_map` l'imprime lui-même quand il rend
zéro (#323).

## 4. Classement priorisé — les 20 premiers

Critère de tête : **un bug silencieux confrontable et vivant passe devant tout le reste** —
c'est le seul défaut qu'un entraînement RL irait exploiter. `PERIME-CANDIDAT` et `HARNAIS`
sont **écartés** (score −1), pas rétrogradés.

| # | résidu | pourquoi ici |
|---|---|---|
| 1 | `#494` | `1102 Doombolt` **au registre**, écart de cible mesuré (`{81,83,87}` natif contre `{81,83,85}` port) — et `test_doombolt_live.py` **reste VERT** : son montage ne produit pas de reste non nul, le gisement lui est structurellement invisible. |
| 2 | `#488-r1` | Un trait de dégât touche le pipeline de **toutes** les attaques ; verdict `case-72` falsifié au décompilé, rapports natif/port **1,42** et **2,00**. `E!` |
| 3 | `#512-r1` | Écart **chiffré et attribué** (`9575`/`10073` puis `7101`/`7766`, bit-exact sans le passif), montage écrit, **49 porteurs** du trait dont 8 lineup. `E!` |
| 4 | `#287-r11` | 4 règles de ciblage dynamiques dont le port rend `0` **permissif** ; **2 des 4 ids sont déjà au registre** (`1076`, `1213`) donc confrontables sans montage neuf. |
| 5 | `#287-r12` | `Target()` **nul** pour 5 abilities TILE-TARGET — **les 5 sont au registre** (`1017`, `1018`, `1026`, `1148`, `1169`) : le gisement est armé et muet. |
| 6 | `#508-r1` | Le gate de spawn de `1204` (au registre) **collapse** sur un compteur inexistant ; l'équivalence n'est établie que sur cet arbre. `E!` |
| 7 | `#511-r1` | Décalage de **flux RNG en cours d'attaque** (natif 7–8 tirages, port 10–13) qui n'empêche pas l'accord nominal — exactement la forme qui se réveille ailleurs. `E!` |
| 8 | `#429-r1-r1-r1-r1` | Le repli de `summon_ai` rend `0` pour toute ability sans `minDmg`/`maxDmg` ; `1015` **absent du registre**, porteur summon → greffe, pas un refus. |
| 9 | `#462-r4b-r1-r1-r1-r1-b-r1-r1-r2` | **5 des 8** call-sites natifs d'`IsObjectOrSteppable` non portés — un prédicat de garde manquant est permissif par construction. |
| 10 | `#447-r1-r1-r3` | `is_turn_of_unit` câblé par **aucun** appelant de production : 2ᵉ clause de `CasterHasNotMoved` inerte, dégradation **permissive** sur 13 porteurs. |
| 11 | `#287-r11-r1-r1-r2` | Le pendant **RESTRICTIF** du précédent côté runner : le port **refuse des casts que le natif accepte**. Les deux faces d'un même préfixe, à traiter ensemble. |
| 12 | `#448-r1-r1-r2-r2` | `MoveUnitOperation` ne matérialise **ni** la garde d'abandon **ni** les tuiles traversées : tout effet de traversée est muet. |
| 13 | `#448-r1-r2` | Le gate `TilesAreEmpty` de `MoveUnitOperation$$Execute` n'est pas porté — même foyer que le précédent, à instruire dans la même tranche. |
| 14 | `#448-r2b-r1` | `UntargetableEffect` (`1238` + 4 `EffectType`) **hors du domaine du port** : une unité intouchable reste ciblable offline. |
| 15 | `#27-r9` | Le PRNG de **décision** n'est pas porté : deux gates à tirage restent **permissifs** — un biais de politique, pas un écart de dégât. |
| 16 | `#489-r1` | La loi de report de `GetLeftOverHits` est fausse sur un régime, dans un foyer **PARTAGÉ** (`1048` et `1006`) ; la loi corrigée reproduit **6 régimes sur 6**. |
| 17 | `#419-r1-tr9-r4-r1-r2-r1c` | La **pose** de `1395` n'est pas portée (`1395` absent du registre) : invisible tant que le harnais hydrate depuis le live, faux dès qu'on simule. |
| 18 | `#433-r4-r2-r1-r1-a-r1` | La tuile **occupée** : trois gates natifs la retirent, le port ne la modélise pas — `1168` et `1200`, confrontables au catalogue. |
| 19 | `#BL-1029r` | `Drachnyen_ExtraAttackAbility` (`1485`) absente offline : **~40 %** du dégât observé d'Abaddon, `10 coups live contre 5 offline`. `E!` |
| 20 | `#287-r5-r2` | Régression **permissive-inversée** sur un compteur non seedé — mais `R!` : exige d'exposer le compteur dans `combatSnapshot`, donc une **fenêtre de reinject**. À planifier, pas à dispatcher. |

**Écartés du top par requalification humaine** (l'étage mécanique les classait moteur ;
ce sont des résidus d'`OUTILLAGE`, chantier harnais arrêté) : `#281-r2`, `#287-r13`,
`#431-r1`, `#485-r1-r1-r2`, `#270-r2`, `#277-r1`, `#449-r2-r4-r2`.

**Écartés comme PERIME-CANDIDAT** : `#haze-ord` (confirmé livré — **à retirer du backlog**),
`#437-r1-r1-r3`, `#448-r1-r1-r1-r1-r2-r1`, `#419-r1-tr14-r5-r2-r1-r1-r1`.

## 5. Ce qui n'est PAS couvert

- **La fraîcheur de 268 entrées sur 278.** Aucun signal mécanique ne les atteint. Les
  trancher demande la lecture, et c'est le coût que cette tranche a mesuré plutôt que payé.
- **`gh pr list --limit 600`** ne remonte qu'au **2026-07-28** : une livraison antérieure est
  hors de portée de E2.
- **Le blame date la dernière RÉÉCRITURE** de la ligne, pas son ajout : une ligne remaniée
  peut masquer une livraison antérieure.
- **NATURE et PÉRIMÈTRE sont lexicaux** : ils classent ce que la ligne **dit**, pas ce que le
  code fait. Un contresens de rédaction se propage tel quel — d'où les 6 requalifications.
- **La confrontabilité réelle** (pool au rank courant, summoner, état de relique) n'est pas
  dérivée : seules les 5 voies gameconfig le sont.
- **Les 6 autres sections du backlog** (dont les 27 « résidus documentés » et les 32
  cliquets) sont hors périmètre.
