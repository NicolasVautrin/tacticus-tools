# #427 — le cliquet des mirrors d'enum a dérivé sur `master`, et il avait pourtant raison

## 1. Le fait

`scripts/python/tests/test_enum_mirror_ratchet_offline.py::test_toute_classe_intenum_du_moteur_est_classee`
échouait sur `origin/master` pur. Deux classes `IntEnum` du moteur n'étaient ni appariées à un
enum natif ni justifiées hors-mirror :

| classe | fichier | entrée par |
|---|---|---|
| `PathfinderType` | `engine/entities/pathfinding/pathfinders.py` | #381-r5 (`051219fb`) |
| `KillUnitStep` | `engine/runner/operations/remove_effects.py` | #389-r2 (`163f62fb`) |

**Le cliquet n'a rien raté.** Il rougissait, correctement, depuis `051219fb`. Ce qui a manqué,
c'est qu'aucune des trois tranches concernées ne l'a lancé — §4.

## 2. Nature du trou — (a) sur les deux enums, (b) un cran plus bas

**Les deux enums = oubli mécanique, pas catégorie inexprimable.** Les deux docstrings déclaraient
déjà un mirror natif, les deux clés existent dans `enums.tsv`
(`IdunBattle.Operations.KillUnitStep`, `IdunBattle.Entities.Pathfinding.PathfinderType`), et les
deux sont bijectifs avec le build. Le registre savait les exprimer ; personne ne les y avait mis.

* `PathfinderType` : 14/14, bijection parfaite en `strict` → registre, sous garde.
* `KillUnitStep` : valeurs justes, mais le port écrivait `PRE_UNIT_REMOVE` là où le jeu dit
  `PreUnitRemove`. Le ranger `strict=False` — le mode qui existe pour `StatType` — **aurait rendu
  muet le sens RENUMEROTÉ**, le pire des trois (il résout, pointe ailleurs, rien ne proteste).
  Mesuré sur la **même** mutation (`AfterUnitRemove` → `AFTER_UNIT_REMOVE`) :

  ```
  strict=True  -> ([], [], [(1, 'AFTER_UNIT_REMOVE', ['AfterUnitRemove'])])   + 3 refs cassées
  strict=False -> ([], [], [])                                                MUET
  ```

  `strict=False` porte sur TOUT le mirror : une exception de confort demandée par un membre est
  payée par les autres. Le port est donc **renommé au nom du jeu**, conformément à sa propre
  docstring (« VERBATIM du dump d'enums »), et entre en `strict`. Sites touchés : la déclaration,
  4 usages dans `damage.py::_kill_unit_operation`, 1 dans `probe_95r2_sworn_protector.py`,
  4 dans `test_389r2_kill_unit_remove_effects_offline.py`.

**Le (b), lui, était dans le DÉTECTEUR.** `probe_313.classes_intenum` ne reconnaissait que les
bases écrites littéralement `IntEnum` / `IntFlag`. Un mirror écrit `class X(int, Enum)` — forme
strictement équivalente et idiomatique — n'aurait été ni apparié, ni orphelin, ni justifié :
**invisible**. C'est le mode de défaillance que l'étape 1 existe pour fermer (« personne n'avait
DÉCIDÉ de ne pas le garder : il n'était dans aucune liste »), réintroduit dans l'outil qui la
ferme. `BASES_ENUM` couvre désormais les six formes. Aucun verdict ne change aujourd'hui — le
dépôt ne contient que 13 `IntEnum` + 1 `IntFlag` — la porte est fermée avant qu'on la franchisse.

**Résidu NOMMÉ** : un alias d'import (`from enum import IntEnum as IE` puis `class X(IE)`) reste
hors de portée d'un AST par fichier ; le résoudre exigerait de suivre les imports. Le cas ne s'est
jamais produit.

## 3. Le cliquet mord toujours — trois contre-épreuves

Mutation vérifiée mordante **avant** de lire le verdict (sur une contre-épreuve, VERT est le
résultat suspect) :

| mutation | attendu | mesuré |
|---|---|---|
| classe `IntEnum` neuve non classée sous `engine/` | rouge | `ORPHELINES=1`, sonde `rc=1`, pytest FAILED |
| `AfterUnitRemove` → `AFTER_UNIT_REMOVE` | rouge | `RENUMEROTES=1` + 3 références INTROUVABLES, `rc=1` |
| `BASES_ENUM` rétréci à `{IntEnum, IntFlag}` | rouge | le test de détecteur FAILED |

Restauré dans les trois cas ; `probe_313` rend `rc=0`, 12 mirrors sous garde, 0 dette,
1795 références qualifiées résolues.

## 4. Ce qui a réellement échoué : l'EXÉCUTION, pas la conception

`probe_313` possède déjà la propriété qu'on cherche à généraliser : **il prouve sa COUVERTURE
dans le même processus que sa conformité** (`test_toute_classe_intenum_du_moteur_est_classee` à
côté de `test_les_mirrors_sous_garde_sont_en_bijection_avec_le_build`). Il a quand même laissé
passer deux dérives. Donc :

> Prouver sa couverture est **nécessaire et non suffisant**. Un balayage qui prouve sa couverture
> mais que rien ne lance a exactement le même résultat observable qu'un balayage aveugle.

Deux modes de défaillance distincts, deux remèdes distincts :

| mode | symptôme | remède |
|---|---|---|
| **CONCEPTION** | la liste de référence est saisie et rien ne vérifie qu'elle est complète | un test de couverture, dans le même fichier |
| **EXÉCUTION** | la garde est juste et rouge, personne ne la lance | l'appartenance à une liste **exécutable** |

**Et la liste des « 9 cliquets permanents » n'est matérialisée nulle part** (mesuré) : aucun
script, aucun Makefile, aucune cible npm/pytest, aucun workflow CI (`.github/` n'existe pas),
aucun hook git (`.git/hooks` ne contient que des `*.sample`), et le seul hook Claude Code du dépôt
(`SessionStart` → `symbols_sync.py`) porte sur un autre sujet. Elle circule en prose, recopiée à
la main dans chaque case-doc, **avec des compositions divergentes** : `case-366-r1` en cite 5,
`case-415` en cite 8 dont 4 qui ne sont pas dans les 9. Aucun fichier du dépôt ne contient les 9
ensemble ; `CLAUDE.md` cite le nombre sans les nommer et n'en prescrit que 4.

C'est le même constat que `#409-r1`, qui propose d'« ajouter `probe_319` à la liste des cliquets »
— alors qu'aucun artefact ne la matérialise.

## 5. Coût, et recommandation

Mesures du 2026-08-01, machine à 22 cœurs logiques **partagée avec d'autres agents** — le bruit
est important (un même item varie du simple au double d'un run à l'autre) ; les chiffres ci-dessous
sont les meilleurs de 3 répétitions.

| | avant #427 | après #427 |
|---|---|---|
| sonde `probe_313_enum_mirror_bijection.py` | **159,2 s** | **22,4 s** |
| pytest `test_enum_mirror_ratchet_offline.py` | ~51 s | **27,6 s** |

Deux gaspillages retirés, aucun assouplissement de la garde :

* le rapport balayait le dépôt **deux fois** (une dans `references_cassees`, une pour afficher le
  total) — 159,2 → 68,9 s, même machine, même minute ;
* pré-filtre textuel **co-extensif** avec le détecteur (un `ast.Name` d'`id` X n'existe pas si le
  token X n'est pas dans la source) : étape 3 38,2 → 31,5 s, étape 1 8,9 → 5,6 s. Résultat
  confronté à l'implémentation d'avant : **1795 références identiques des deux côtés**, 14 classes
  identiques.

Lot des 9 cliquets mesuré ici : **mur parallèle 75,4 s**, somme série 279,3 s, 0 rouge. Le mur est
`pytest signatures` (74,5 s) — `probe_273 --only-scan` (53,3 s) n'est plus en tête.

**Recommandation : oui, ce cliquet doit être permanent — mais l'ajouter à une liste qui n'existe
pas ne change rien.** À 27,6 s il passe sous 4 des 9 et ne déplace pas le mur ; le coût marginal
d'un slot parallèle libre est nul. Le geste qui compte est en amont : **matérialiser la liste en
un artefact unique et exécutable** (un module qui l'énumère et la lance en parallèle, rc agrégé).
Sans lui, « ajouter aux cliquets » reste un vœu, chaque case-doc continue de recopier une liste
différente, et le prochain cliquet juste-mais-jamais-lancé dérivera de la même façon.

Non traité ici, volontairement : la construction de cet artefact. Trois agents instruisaient
simultanément la même question sur trois cliquets différents (#427, `probe_283`, `probe_229`) ;
un runner livré trois fois serait trois conflits. L'arbitrage revient à l'orchestrateur.
