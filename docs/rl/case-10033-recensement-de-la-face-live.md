# #10033 — La face LIVE, mesurée pour la première fois

`probe_457_offline_tests_green.py` s'annonce, dans sa propre première ligne :

> #457 -- CLIQUET : TOUT fichier de test qui n'est pas `_live.py` doit etre VERT.

Le critère est explicite dans son code (`not name.endswith("_live.py")`, documenté aux lignes
103-107) et il est **déclaratif** — le suffixe est tenu par le dépôt, pas deviné. Un critère plus
fin avait été essayé puis retiré : il classait « offline » des dizaines de `*_live.py` et dépassait
600 s.

Ce que personne n'avait chiffré, c'est **ce que ce critère laisse dehors**.

---

## 1. La taille de l'axe — mesure GRATUITE et EXHAUSTIVE

Aucun runner monté. `pytest --collect-only`, sortie redirigée vers un **fichier** (jamais un pipe).

| | |
|---|---|
| fichiers `test_*.py` sous `tests/` | **1176** |
| dont `_offline.py` | 509 |
| dont ni `_live` ni `_offline` | 25 |
| **dont `_live.py`** | **642** |
| périmètre annoncé par `probe_457 --list` | **534** fichiers (509 + 25), coût annoncé ~2155 s |
| **hors périmètre de `probe_457`** | **642 fichiers, soit 54,6 % du corpus de tests** |

Et à l'intérieur de la face live :

| | |
|---|---|
| tests collectés dans les `_live.py` | **4198** |
| fichiers qui collectent | **642 / 642** |
| **erreurs de collecte** | **0** |
| fichiers sans aucun test collecté | **0** |

Donc **aucun rouge gratuit** : la face live ne cache pas de fichier cassé à l'import. Tout ce qui
peut y être rouge exige de l'exécuter.

### Un rouge trouvé au passage, par la collecte seule

```
[486r15] 1 fichier(s) de test COLLECTE(S) sans `DECLENCHEUR` et hors dette :
           scripts/python/tests/engine/runner/test_448r1r1r3r1_movement_start_live.py
```

Le garde `declencheur_guard` est actif sur **tous** les fichiers collectés, live compris. Celui-ci
fait passer toute passe qui le collecte en `rc 1`. C'est un rouge **réel**, indépendant de la
couleur des tests eux-mêmes, et il ne coûte aucun runner à trouver. Résidu **#10033-r2**.

---

## 2. Le suffixe `_live.py` est-il FIDÈLE ? — oui à 98,4 %

La question compte pour « faut-il étendre un cliquet à la face live » : si beaucoup de `_live.py`
n'avaient en réalité besoin d'aucun runner, ils pourraient rejoindre l'axe offline à coût nul.

Critère **conservateur** (un fichier est réputé live dès qu'un des 16 marqueurs — `rpc`,
`build_runner`, `live_session`, `runnerId`, `import probe_*`, `rl_duel`, `applyAction`,
`decisionView`, `--state-file`, … — apparaît **n'importe où** dans son source) :

| | |
|---|---|
| portent au moins un marqueur live | **632 / 642 (98,4 %)** |
| n'en portent aucun (candidats à l'axe offline) | **10** |

⚠ Le sens de l'erreur est **optimiste sur la colonne de droite** : un fichier qui atteindrait le
harnais par une voie non listée serait compté à tort comme candidat. Les 10 sont donc un **majorant**
à trancher fichier par fichier, jamais en masse.

⚠ Une première version de cette mesure, par **AST des signatures de test**, donnait « 394 fichiers
sans fixture live » — un chiffre **faux**, parce qu'elle ne suivait pas les fixtures **locales** :
`test_510_light_of_sanguinius_live.py` déclare une fixture `mesure` qui monte le runner en appelant
son probe, et aucun de ses tests ne prend `rpc`/`build_runner`. `mesure` apparaît **169 fois** comme
argument de test dans le corpus. Le recenseur naïf ne visitait pas ce qu'il prétendait compter.

**Conséquence directe** : étendre `probe_457` à la face live reviendrait à monter des runners pour
**632 fichiers**. Il n'y a pas de raccourci par reclassement.

---

## 3. La couleur — ÉCHANTILLON, et c'est dit comme tel

Une passe complète est hors de portée : le pump est **partagé** (4 autres agents en vol pendant
cette tranche, `liveRunners` mesuré entre 4 et 13), et la doctrine du dépôt plafonne à **4 workers**
toute passe qui monte des runners. Aux durées mesurées sur cette tranche (`test_381r4…_live` = 26 s
pour 2 tests / 2 runners ; `test_510…_live` = 34 s pour 10 tests / 1 runner), 642 fichiers valent
**~5 h en série**, plus d'une heure à 4 workers — sur un harnais partagé.

Le recenseur (`probe_10033_recensement_live.py`) joue donc un **échantillon tiré au sort à graine
fixe**, parallélisé **par processus** (`xdist` n'est pas installé sur cet arbre) et découpé **par
fichier**, ce qui reproduit `--dist loadfile` : un fichier = un processus = un runner en
`scope="module"`.

### Ce que le recenseur a d'abord dit, et pourquoi c'était faux

Premier tir, 30 fichiers :

```
bilan  : {'passed': 214, 'failed': 2, 'skipped': 0}
fichiers ROUGES : 0
items rouges    : 0
```

`-r` **remplace** la liste des caractères rapportés : le `-rs` posé pour voir les skips avait
**effacé les lignes `FAILED`** du short summary. Le recenseur comptait donc `0` là où pytest en
annonçait `2` — et un « 0 rouge » se lit comme un inventaire. C'est la faute que ce probe existe
pour ne pas commettre.

Deux corrections : `-rsfE`, et un **cran de cohérence** qui rougit dès que le recensement liste
moins d'items que le bilan n'annonce de `failed + error`. Un recenseur qui sous-compte ment
**toujours dans le sens rassurant**.

### Le tir, avec le parseur réparé

`probe_10033_recensement_live.py --echantillon 30 --graine 10033 --workers 3` :

| | |
|---|---|
| fichiers joués | **30 / 642 (4,7 %)** |
| **fichiers rouges** | **2 / 30 (6,7 %)** |
| items rouges | **2** sur 216 exécutés |
| bilan pytest | `passed 214, failed 2, skipped 0, error 0` |
| cohérence recenseur / bilan | **OK** |
| items **skippés** | **0** — donc aucun fichier de l'échantillon n'est dans le régime « vert qui ment » de `#455` |

**Extrapolé, 6,7 % de 642 vaut ~43 fichiers rouges.** C'est une estimation sur n = 30 ; l'intervalle
est large et le tir dépend de l'état de la session. À lire comme un ordre de grandeur, pas comme un
inventaire.

### La VENTILATION — les deux rouges, lus un par un

Le classifieur automatique les a mis tous les deux sous **`NON CLASSÉ`**, et c'est le comportement
voulu : il imprime ce seau **en entier** plutôt que de forcer une étiquette. Lus à la main :

**1. `test_scarab_summon_migration_live.py::test_scarab_summon_migration_is_dsl_tree`**

```
[SCARABSUMMON geo] parent@12 ; seule libre P@13 ; cible@14 ; bloquees=[21, 22]
[SCARABSUMMON migration] dsl=True replica=True spawned=[3] attacks=[]
AssertionError: aucune attaque on-appearance emise
```

Le montage a **réussi** : runner monté, arbre DSL en place (`dsl=True`), réplique conforme
(`replica=True`), trois scarabs apparus (`spawned=[3]`). Ce qui manque est l'**attaque
on-appearance**. C'est une divergence de **comportement porté**, pas un incident de harnais.
Non tranché ici entre dette de port et géométrie de montage trop contrainte (« seule libre P@13 »).

**2. `test_tau_lot1_residues_live.py::test_early_warning_override_reactivate_overwatch_live`**

```
[1146] revas=u81 tue u77 en (2, 2)
       off  [1009, 1026, 1144, 1145, 1148, 1149, 1515]
       live [1009, 1026, 1144, 1145, 1146, 1148, 1149, 1515]
AssertionError: le port n'a PAS pose 1146 apres le kill en overwatch
```

**Dette de port, confrontée au natif, localisée au coup près** : le jeu pose l'effet `1146`, le port
ne le pose pas. Le montage a fonctionné de bout en bout (le kill en overwatch a eu lieu, les deux
listes d'effets sont comparables).

**Bilan de la ventilation : 2/2 sont des divergences de PORT, aucune n'est un incident de montage,
de board, de porteur ou de contention de runner.** C'est contre-intuitif — on s'attendait à du
bruit de harnais — et c'est le résultat le plus utile de ce volet : sur cet échantillon, un rouge
live **vaut la peine d'être lu**. ⚠ n = 2 : ne pas en faire une loi.

---

## 4. Ce que cette mesure NE couvre PAS

* la **couleur** des fichiers hors échantillon ;
* toute dépendance à l'**état de la session au moment du tir** — contention de runner, fenêtre
  DRAIN, autre agent qui sature le pump ; un même fichier peut être rouge à un tir et vert au
  suivant, et c'est précisément pourquoi un rouge live doit être **lu** avant d'être compté comme
  dette ;
* les **probes** (`scripts/python/probe_*.py`) : aucun cliquet ne les joue, et `#10031` montre ce
  que ça coûte — `probe_381r4_imperative_collapses.py` a rendu `rc 1` pendant 13 jours sans que
  personne ne le voie. C'est un **troisième axe**, distinct de l'offline et du live.

---

## 5. Faut-il étendre un cliquet à la face live ?

**Non, pas sous la forme de `probe_457`** — et la mesure le dit :

* le coût est **structurel**, pas accidentel : 632 des 642 fichiers montent réellement un runner
  (§2), donc aucun reclassement ne le réduit ;
* le pump est **partagé**, ce qui rend une passe complète non seulement chère mais **nuisible aux
  autres agents** ;
* et surtout, un cliquet live serait **instable par construction** : `probe_457` tient parce qu'un
  test offline est déterministe. Un rouge live peut venir du montage, d'un board, d'un porteur, ou
  d'une contention — un cliquet qui rougit pour ces raisons-là **se fait désarmer**, ce que le
  dépôt a déjà mesuré ailleurs.

**Ce qui est recommandé à la place**, par ordre de rapport valeur/coût :

1. **La COLLECTE, à chaque passe** — gratuite, exhaustive, déterministe. Elle attrape les erreurs
   d'import, les fichiers vidés (#455-r3) et les `DECLENCHEUR` manquants. Elle vient de trouver un
   rouge réel (§1) pour 33 s de calcul et zéro runner.
2. **Un ÉCHANTILLON PÉRIODIQUE**, tiré à graine tournante, joué quand la flotte est calme — un
   **taux**, jamais un inventaire, et étiqueté comme tel.
3. **Les PROBES**, qui sont l'angle mort le moins cher à fermer : beaucoup sont offline
   (`probe_381r4` l'est), donc jouables sans runner, et `#10031` prouve qu'ils portent de la dette
   invisible.

Ce qui n'est **pas** recommandé : brancher les 642 fichiers sur un cliquet bloquant.
