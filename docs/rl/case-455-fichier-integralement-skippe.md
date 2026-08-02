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

Trois étapes, **25 cas**, **14,3 s** (mesure du 2026-08-02, machine sous charge) — très en dessous
du mur de la banque, donc coût marginal en parallèle quasi nul.

0. **Auto-test du critère** sur des rapports synthétiques (14 cas). Chaque cas positif a son jumeau
   NÉGATIF : c'est lui qui interdit de faire mordre le garde en élargissant son critère.
1. **Bout en bout** dans un répertoire isolé, plugin chargé par `-p green_skip_guard` (8 cas). Le
   cas « le MÊME fichier **sans** le plugin → vert » rend le rouge **attribuable** : sans lui, on
   ne saurait pas si c'est le garde qui rougit ou le fichier synthétique.
2. **CÂBLAGE** (#421 — prouver sa couverture dans le MÊME processus que sa conformité). Un garde
   qui mord dans un tmpdir mais n'est pas chargé par la suite réelle ne garde **rien**. On dépose
   donc un fichier inerte sous `scripts/python/tests/` et on exige un rouge **sans aucun `-p`** :
   le seul chemin de chargement possible est l'import du conftest de production. Contre-épreuve
   dans le même geste : le même fichier, hors de `tests/`, doit rendre vert. Le dépôt est
   temporaire (nom porté par le PID), effacé en `finally`.

**Preuve dans les deux sens** (2026-08-02, mutations jouées puis restaurées) :

| mutation | étape 0 | étape 1 | étape 2 | verdict |
|---|---|---|---|---|
| aucune | 0/14 | 0/8 | 0/3 | **PASS** |
| critère neutralisé (`fichiers_inertes` rend toujours vide) | 5 KO | 2 KO | 1 KO | **FAIL (8)** |
| import retiré de `tests/conftest.py` | 0 | 0 | **2 KO** | **FAIL (2)** |

La seconde mutation est la plus instructive : le garde reste parfaitement fonctionnel (étapes 0 et
1 vertes) et ne garde plus rien. Seule l'étape 2 le voit.

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

<!-- RELEVE -->

---

## 7. Résidus nommés

* **#455-r1** — le gisement n'est mesuré que sur un ÉCHANTILLON des 153 candidats. Le reste est
  NON MESURÉ, pas « propre ». Il se révélera au fil de l'eau, chaque agent jouant sa tranche : le
  garde est actif partout.
* **#455-r2** — le garde lit `terminalreporter.stats`. Sous `pytest -p no:terminal` (aucun agent
  ne le fait) il se tait, sans le dire. Le durcir demanderait un accumulateur propre via
  `pytest_runtest_logreport` — mais ce hook est résolu **par chemin** depuis un conftest non-racine,
  ce qui rouvrirait un angle mort différent.
* **#455-r3** — le critère ne voit pas un fichier dont **tous les tests ont disparu** (0 collecté) :
  aucun report, donc aucun bilan. Un fichier vidé de ses tests est un vert qui ment d'une autre
  forme, que ce cliquet ne couvre pas.
