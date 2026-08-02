# #455 — Un fichier de test INTÉGRALEMENT skippé est un vert qui ment

**Mesure d'origine.** `scripts/python/tests/engine/runner/test_summon_trait_effects_live.py` rendait
**8 skipped, 0 passed, rc 0** sur `origin/master`, sans aucune PR appliquée. Bannière verte, zéro
assertion évaluée. Il a été trouvé en **écartant une PR** — mesure de contrôle — pas cherché : rien
dans le dépôt ne le signalait.

**Le skip n'est pas le défaut.** C'est la bonne réponse à un montage qui rate : un test qui
échouerait franchement sur un montage impossible serait un faux rouge, et démêler un rouge de
MONTAGE d'un rouge de PORT a déjà coûté des heures ici. Le défaut, c'est que le fichier **ne se
voit pas**.

---

## 1. Pourquoi les gardes existants ne le voyaient pas

`tests/conftest.py` porte déjà un garde (#77) : `pytest_runtest_makereport` lit la **RAISON** d'un
skip et la convertit en échec quand elle dit « harnais indisponible » (`build runner KO`,
`runner cap reached`, `runner creation paused`, `pas de session Frida active`, `warmup KO`).

Ce garde-là est **structurellement aveugle** au gisement de #455, et c'est mesurable sur le cas
lui-même : la raison levée était `spawn tauSmnStealthSuit KO`. Aucun marqueur de harnais, aucune
conversion. Un skip de **MONTAGE** est précisément celui qui ne dit rien du harnais.

Les deux gardes lisent des choses différentes, à des échelles différentes :

| | #77 | #455 |
|---|---|---|
| lit | la **raison** d'un skip | un **bilan** |
| échelle | le **test** | le **FICHIER** |
| voit | harnais indisponible | rien n'a été confronté |

L'échelle du fichier est celle qui compte : un test skippé parmi dix qui passent est une
information ; un fichier où **rien** n'a été évalué est une garde qui n'en est plus une.

---

## 2. Le garde-fou — `scripts/python/green_skip_guard.py`

Plugin pytest, branché par `tests/conftest.py` (un conftest non-racine ne peut pas déclarer
`pytest_plugins` depuis pytest 7 ; le module vit donc à part, ce qui permet aussi de le charger par
`-p green_skip_guard` sur un répertoire arbitraire — c'est ce qui rend le cliquet possible).

**Critère** : `passed == 0 and skipped > 0`, par fichier. Littéral. Un fichier qui a en plus des
`failed` y entre — il est déjà visible en rouge, mais il reste vrai que rien n'y a été confronté.

**Compté comme JOUÉ** : `xfail` et `xpass` — l'assertion a bien été évaluée, son échec était
attendu. `passed` ne se compte que sur la phase `call` (sinon chaque test passant en vaudrait
trois) ; les skips se comptent sur toutes les phases (un skip de fixture n'émet qu'un report
`setup`).

**Il se tait quand la sélection est PARTIELLE** — trois causes, toutes lues sur la session, aucune
saisie :

* items **déselectionnés** (`-k`, `-m`, `--deselect`, `--lf`) → hook `pytest_deselected` ;
* **nodeid explicite** en argument (`fichier.py::test_x`) → `config.args` ;
* session **interrompue** (`-x`, `--maxfail`, KeyboardInterrupt) → `session.shouldstop`.

Plus l'échappatoire consciente `TACTICUS_ALLOW_GREEN_SKIP=1` — la **même** que le garde #77. Sans
elle, une inspection de la collecte sans jeu lancé rendrait TOUT fichier live inerte, et le verdict
n'apprendrait rien.

**Coût** : nul. Le garde ne fait rien pendant la passe ; il lit `terminalreporter.stats` à la fin.

---

## 3. Le cliquet — `probe_455_all_skipped_file.py` (banque `scripts/ratchets.ps1`)

Le garde runtime est ce qui **voit** le gisement, à chaque passe ciblée que joue n'importe quel
agent. Le cliquet garde que ce garde **mord** et **est branché**.

Trois étapes, **26 cas**, **10,8 s** machine calme (62,6 s dans la banque en parallèle, mur 102,9 s)
— très en dessous du mur, donc coût marginal quasi nul.

0. **Auto-test du critère** sur des rapports synthétiques (14 cas). Chaque cas positif a son jumeau
   NÉGATIF : c'est lui qui interdit de faire mordre le garde en élargissant son critère.
1. **Bout en bout** dans un répertoire isolé, plugin chargé par `-p green_skip_guard` (8 cas). Le
   cas « le MÊME fichier **sans** le plugin → vert » rend le rouge **attribuable** : sans lui, on
   ne saurait pas si c'est le garde qui rougit ou le fichier synthétique.
2. **CÂBLAGE** (#421 — prouver sa couverture dans le MÊME processus que sa conformité), 4 cas. Un
   garde qui mord dans un tmpdir mais n'est pas chargé par la suite réelle ne garde **rien**. On
   **copie** donc le `tests/conftest.py` DE PRODUCTION dans une arborescence MIROIR en tmpdir
   système, et on exige un rouge **sans aucun `-p`** : le seul chemin de chargement possible est ce
   conftest. Contre-épreuve dans le même geste (même miroir SANS le conftest → vert), plus deux
   volets qui lisent le chemin de PRODUCTION (hooks re-exportés ; le conftest couvre bien des tests
   réels) — ce que la copie ne prouve plus.

   Deux détails du miroir ne sont pas décoratifs, et tous deux sont **mesurés** (§8) : sa
   **profondeur** (`scripts/python/tests/cas`, parce que le conftest calcule `ROOT = parents[3]` et
   y crée `logs/`), et la **copie du `pytest.ini`** — c'est lui qui fixe `rootdir`, donc
   `confcutdir`, donc jusqu'où pytest REMONTE chercher les conftest. Sans lui : `3 skipped`, aucun
   rapport de garde, un **faux négatif du cliquet**.

**Preuve dans les deux sens** (2026-08-02, mutations jouées puis restaurées) :

| mutation | étape 0 | étape 1 | étape 2 | verdict |
|---|---|---|---|---|
| aucune | 0/14 | 0/8 | 0/4 | **PASS** |
| critère neutralisé (`fichiers_inertes` rend toujours vide) | 5 KO | 2 KO | 1 KO | **FAIL (8)** |
| import retiré de `tests/conftest.py` | 0 | 0 | **2 KO** | **FAIL (2)** |

La seconde mutation est la plus instructive : le garde reste parfaitement fonctionnel (étapes 0 et
1 vertes) et ne garde plus rien. Seule l'étape 2 le voit — et elle le voit **toujours** depuis
qu'elle travaille sur une copie (§8).

`probe_439` classe l'entrée CAPABLE de rougir (`sys.exit(main(...))`).

---

## 4. Le cas d'origine — le port est CORRECT, le montage était caduc

**RE.** `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute`, lu au décompilé : le
tile-sélecteur (`entities+0x58`) est résolu **UNE FOIS** (`Select`), puis, dans la branche mono-pied
(`SpawnUnitOptions+0x60 == 0`), un `GetEnumerator` / `while (MoveNext())` sur la liste de tuiles ;
c'est **dans** cette boucle que `GetAddUnitOptions` puis l'appel à `AddUnitOperation` créent
l'unité, et la liste des unités créées n'alimente `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`
qu'ensuite.

⇒ **Zéro tuile itérée, zéro appel, zéro entité.** C'est exactement ce que le port mirrore depuis
`case-spawn-requires-tile` (#251) — avant lui, une boucle `range(count)` créait l'unité PUIS lui
cherchait une place, et laissait un summon FANTÔME sans `PositionComponent` quand la cible était
encerclée (#246).

**Le montage.** Le test posait `target_id = caster_id` avec le commentaire « placement indifférent
(on teste les effets, pas la tuile) ». Il l'était tant que l'entité naissait avant sa tuile ; il a
cessé de l'être avec #251, **sans qu'aucun test ne rougisse** — le skip de secours a avalé les huit.

**Mesure** (board `MC1_67` / seed 777, la configuration par défaut de `build_runner`) : la première
unité de `decisionView` (u77, tuile 74) a **2 voisins**, `65` et `73`, tous deux tenus par ses
alliés → `free = []` sur les **cinq** visuals. Sur les dix unités de cette bataille, **six** ont au
moins une tuile libre au contact.

**Réparation.** La cible se **dérive** désormais du même sélecteur que l'opération
(`_free_tiles_adjacent`, le mirror de `CanAddUnit(AdjacentTiles(target))`), au lieu d'être supposée.
Le caster reste `units[0]` : il ne fournit que le couple (`active_ability_level`,
`ability_variables_multiplier`) qui dimensionne les stats du summon. Un montage qui ne s'installe
pas **ÉCHOUE** (#268, doctrine déjà écrite dans `tests/engine/conftest.py`), il ne skippe pas.

**Résultat** : `8 skipped / 0 passed` → **`8 passed`** (146 s). Aucune assertion n'a dû être
modifiée — le port était juste, et les huit verdicts qu'il portait dormaient depuis #251.

---

## 5. Le gisement

Il ne se dérive **que d'une exécution** : un skip de montage dépend de l'état live, il est
indécidable statiquement. Or la suite complète est proscrite et chaque fichier live monte un runner.

**Sur-ensemble statique** (`probe_455_all_skipped_file.py --inventaire`, HORS VERDICT) : les
fichiers dont **tous** les tests peuvent atteindre un `pytest.skip` (fermeture transitive des
helpers du module + markers `skip`/`skipif`). Mesure du 2026-08-02 : **153 candidats sur 502**
fichiers de test. Un candidat n'est **pas** un fichier inerte — c'est le seul sous-ensemble qu'il
vaille la peine de jouer.

**Échantillon mesuré.** Voir §6 pour le relevé daté. Le mode `--inventaire` rend toujours 0 : un
sur-ensemble ne conclut rien, et le faire entrer au verdict ferait rougir des fichiers sains.

---

## 6. Relevé du 2026-08-02

**Échantillon** : 45 des 153 candidats, tirés au sort (`random.Random(455).shuffle`), joués 3 en
parallèle, instrument = le garde lui-même. **1 fichier INERTE**.

| fichier | avant | après | verdict |
|---|---|---|---|
| `test_summon_trait_effects_live.py` | 8 skipped / 0 passed | **8 passed** | montage RÉPARÉ (§4) |
| `test_offbyone_armor_38_live.py` | 2 skipped / 0 passed | **2 passed** | montage RÉPARÉ (ci-dessous) |

Deux rouges **pré-existants** sont tombés au passage — ils ne sont pas dans le gisement (ils ont
des `passed`), mais l'échantillon les a levés :

| fichier | état | suite |
|---|---|---|
| `test_normal_like_bounds_rounding_live.py` | 1 failed / 1 passed | **RÉPARÉ → 2 passed** (même cause) |
| `test_env_fire_tile_migration_live.py` | 1 failed / 2 passed | `pytest.fail("cible morte avant la fenetre discriminante")` — rouge de MONTAGE conforme à #268, sans rapport. Résidu **#455-r4**. |

### Le premier inerte trouvé était un CLIQUET, éteint le jour même

`test_offbyone_armor_38_live.py` est le cliquet du résidu **#38** (off-by-one `+1` à armure > 0).
Il rendait `2 skipped` — donc ne gardait plus rien.

**Cause, datée et prouvée offline.** `0ad4b9e8` (#446-r2, **2026-08-02**, l'arrondi INTER-FACES) a
porté le mirror des étapes 3 et 4 de
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` **dans**
`apply_pierce_and_modifiers`, qui appelle désormais `calculate_base_damage_with_modifiers` **deux
fois, inconditionnellement**. La valeur arrive donc **déjà entière** à `apply_all_modifiers`, où
`round_materialize` — le seul knob que les tests forçaient — est devenu un **no-op strict**.
Mesure directe du régime (pierce 40, armure 6000) :

```
apply_pierce_and_modifiers(2009.6) = 804.0     round=804  floor=804
apply_pierce_and_modifiers(3014.4) = 1206.0    round=1206 floor=1206
apply_pierce_and_modifiers(2890)   = 1156.0    round=1156 floor=1156
```

`round == floor` pour **toute** entrée : aucun seed, aucune armure ne peut plus discriminer.

**Le point qui justifie ce cliquet à lui seul** : la MÊME dérive a produit **deux signaux
opposés**. `test_normal_like_bounds_rounding_live.py` a **crié** (son `assert floor != round` a été
atteint → rouge visible sur `master`). `test_offbyone_armor_38_live.py` a **avalé** : il possède le
même assert, mais son balayage de seeds `pytest.skip` **avant** de l'atteindre — le skip a mangé
l'assert. Sans le garde de ce cas, seul le premier se serait vu, et on aurait réparé un test en
laissant l'autre éteint.

**Correctif** : le forçage vise les **deux** étages. `_sans_round` mirrore
`calculate_base_damage_with_modifiers` privé de son unique `Fix64.Round(x, AwayFromZero)` (gates
`x <= 0 -> 0` et `0 < x < 1 -> 1` conservés) ; « floor » signifie désormais « aucune matérialisation
intermédiaire, la fraction du perçage survit jusqu'à `op_Explicit` » — exactement la loi que #38
accuse. Posé au FOYER (`_pierce_floor_regime.replay_materializations`, 2 consommateurs) et dans le
`_replay` local de #38. Aucun code moteur touché.

**Non-régression** des voisins du foyer : `test_additional_hits_roll_order_live.py` (5 passed),
`test_failed_block_attack_scope_live.py` (3 passed), `test_evasion_order_before_block_live.py`
(3 passed), `test_additional_hits_rounding_live.py` (3 passed).

### Banque, après la correction de §8

**3 passages complets EN PARALLÈLE** (jamais `-Serial`, jamais `-Only` : un passage série
masquerait précisément le défaut de §8) : **VERTE 3/3, 29 cliquets**, murs **102,9 / 88,6 / 91,3 s**.
`probe_391` et `probe_455` verts ensemble à chaque fois. ⚠ Ces trois verts ne sont pas la preuve —
la preuve est structurelle (`probe_440` R3) ; ils en sont la confirmation.

### Ce que l'échantillon ne dit pas

108 des 153 candidats n'ont pas été joués, et 349 fichiers ne sont même pas candidats. Le taux
mesuré (1/45) borne l'ordre de grandeur, pas le gisement. Le garde étant actif sur toute passe, le
reste se révélera au fil de l'eau — c'est le résidu **#455-r1**.

---

## 7. Résidus nommés

* **#455-r1** — le gisement n'est mesuré que sur un ÉCHANTILLON (45 des 153 candidats). Le reste
  est NON MESURÉ, pas « propre ». Il se révélera au fil de l'eau, chaque agent jouant sa tranche :
  le garde est actif partout. Relever les inertes trouvés ici (§6) au lieu de les traiter en
  silence.
* **#455-r2** — le garde lit `terminalreporter.stats`. Sous `pytest -p no:terminal` (aucun agent
  ne le fait) il se tait, sans le dire. Le durcir demanderait un accumulateur propre via
  `pytest_runtest_logreport` — mais ce hook est résolu **par chemin** depuis un conftest non-racine,
  ce qui rouvrirait un angle mort différent. Même remarque pour `pytest-xdist` : **non installé**
  ici (les agents lancent N processus pytest séparés, où le garde fonctionne pleinement) ; sous
  xdist, `pytest_deselected` est appelé côté worker et le master pourrait ne pas le voir.
* **#455-r3** — le critère ne voit pas un fichier dont **tous les tests ont disparu** (0 collecté) :
  aucun report, donc aucun bilan. Un fichier vidé de ses tests est un vert qui ment d'une autre
  forme, que ce cliquet ne couvre pas.
* **#455-r4** — `test_env_fire_tile_migration_live.py::test_env_fire_tile_dot_applies_resilient_cap_live`
  est ROUGE sur `master` : `pytest.fail("cible morte avant la fenetre discriminante")`. C'est un
  rouge de MONTAGE conforme à #268 (il échoue au lieu de skipper, c'est correct), sans rapport avec
  ce cas ni avec #446-r2. Trouvé par l'échantillon, non traité — hors périmètre.
* **#455-r5** — FERMÉ dans cette même livraison, et gardé : la première version de l'étape 2
  écrivait dans l'arbre de production. Détail en §8 ; le garde générique est `probe_440` R3
  (`docs/rl/case-434-perimetre-des-cliquets.md` §11).

---

## 8. La faute que cette livraison a commise — un cliquet ne doit rien ÉCRIRE dans l'arbre partagé

Elle vaut d'être écrite ici, parce qu'elle a **fait renvoyer la PR** et qu'elle n'était ni dans le
critère ni dans le câblage.

**La mesure.** La première étape 2 déposait `_probe455_cablage_<pid>` sous `tests/` et
`_probe455_hors_<pid>` sous `scripts/python/`, le temps d'un run pytest. Or **la banque tourne en
PARALLÈLE par conception** (`ForEach-Object -Parallel`) :

| ce qui a été joué | résultat |
|---|---|
| `probe_391` SEUL | **VERT** |
| `probe_455` SEUL | **VERT**, zéro résidu après coup |
| les DEUX dans la banque, EN PARALLÈLE | `probe_391` **ROUGE** — `FileNotFoundError: ...\scripts\python\_probe455_hors_87960` |

`probe_391` (`TESTS_ROOT.rglob` + `pytest --co`) collecte cet arbre au même moment et voyait un
répertoire **apparaître puis DISPARAÎTRE**. Le rouge était attribué au mauvais cliquet.

**C'est la leçon de #434 transposée** : là-bas un cliquet **LISAIT** hors de son périmètre, ici il
y **ÉCRIVAIT**. Même faute, autre sens.

**Ce qu'il ne fallait pas faire** : supprimer l'étape 2. C'est la moitié qui compte — la ligne de
banque de ce cliquet le dit, et la table des mutations le prouve (seule l'étape 2 voit un conftest
débranché). Le problème n'était pas qu'elle écrive, mais qu'elle laisse une **fenêtre visible aux
autres**.

**La correction** : arborescence miroir en **tmpdir système**, où l'on copie le conftest de
production. Ce que la copie prouve est exactement ce qu'on veut — *le conftest réel, tel qu'il est
sur disque, charge le garde quand pytest l'applique* — et elle importe le **vrai**
`green_skip_guard` via `PYTHONPATH`. Vérifié : la mutation « import retiré du conftest de
production » fait **toujours** rougir l'étape 2 (2 cas), étapes 0 et 1 vertes. Ce que la copie ne
prouve plus (que `tests/` est l'ancêtre des tests réels) est repris par deux volets qui lisent le
chemin de production.

Deux pièges du miroir, tous deux **mesurés, pas anticipés** :

* **la profondeur**. Le conftest calcule `ROOT = Path(__file__).resolve().parents[3]` puis crée
  `<ROOT>/logs`. Copié *à plat* dans un tmpdir, il aurait écrit dans un répertoire quelconque du
  système — le vice qu'on corrige, simplement déplacé. Le miroir `scripts/python/tests/cas` rend
  `parents[3]` = le tmpdir.
* **le `pytest.ini`**, qu'il faut copier AUSSI : il fixe `rootdir`, donc `confcutdir`, donc jusqu'où
  pytest remonte chercher les conftest. Sans lui, `rootdir` vaut le répertoire de test et le
  conftest parent n'est **jamais chargé** : `3 skipped`, aucun rapport — un **faux négatif du
  cliquet**, découvert en le jouant. Le copier rend le miroir identique à la production et laisse
  le conftest comme **seule** variable entre les deux bras.

**Et la règle générale, gardée** (`probe_440` R3, `case-434` §11) : un rejeu qui passe ne prouve
**rien** sur une course — le vert est ici le résultat *suspect*. La garantie doit être
**structurelle**. R3 rougit sur toute entrée de la banque qui crée ou supprime une entrée de
répertoire sous `scripts/python/`, périmètre dérivé de `ratchets.ps1`. Auto-test **23/23**
(4 cas négatifs, dont « `write_text` en place », qui protège les modes `--fix`), étape 3 = **0** sur
les 29 entrées, et **FAIL (2)** quand la faute d'origine est remise.
