# #935 — Neuf cliquets rouges que personne ne jouait, et la raison pour laquelle la sélection par diff ne pouvait pas les voir

**Base** : `origin/master` = `7611776e`. **Build** : `rnca9r7q6c`. 100 % offline (aucun runner, aucun RPC).

## 1. Le fait

`scripts/python/tests/` porte **61 fichiers de cliquet à sa racine** — les gardes à l'échelle du
dépôt. Une passe complète les a joués : **9 fichiers rouges, 11 tests**. Sept sont armés par des
merges du **jour même**.

L'orchestrateur en jouait **huit**, choisis à la main et jamais re-dérivés. C'est le vice
« un déclencheur trop étroit est un faux vert », appliqué à la conduite plutôt qu'au code.

## 2. Attribution — chaque rouge, sur arbre témoin détaché

Méthode : `git worktree add --detach`, puis le cliquet rejoué à chaque SHA. Une attribution qui
n'est pas encadrée par un **vert** au commit précédent n'est pas une attribution.

| cliquet | ce qu'il accuse | attribution |
|---|---|---|
| `test_314_absolute_repo_path_offline` | `probe_468_collision_numeros.py:1008` — le chemin absolu du dépôt écrit **en prose** dans une docstring | **armé par le merge #911** (`38b8e1b5`) |
| `test_337_dsl_triggers_attestation_offline` | `DSLTriggers$$IsOverwatchAttack` en `CITE_A_QUALIFIER` | **armé par le merge #922** (`903cbe3e`) — VERT à `46ba95e8` |
| `test_366_r1_bcpatch_port_blindspot_offline` (1) | `HellfireShells` / `nrOfHits`+`extraHit` patchés par `probe_605` et lus par le moteur | **armé par le merge #888** (`9b51d9cf`) — VERT à `9b51d9cf~1` |
| `test_366_r1_bcpatch_port_blindspot_offline` (2) | trou de couverture non nommé : `engine/predict.py` | **armé par le merge #909** (`9f80611d`) — absent à `7471d88b` |
| `test_449_r2_spread_face_combat_offline` | porte de variance neuve `UseNormalAttack.spread_pct`, non attestée | **armé par le merge #900** (`7471d88b`) — VERT à `b141c1be` |
| `test_463r1_ecart_empreinte_offline` | 3 fichiers de test offline jamais mesurés | **armé par #924 / #926 / #927** |
| `test_468_collision_numeros_offline` | « ce test a ALLOUÉ dans le registre partagé : #936 » | **cliquet DÉFECTUEUX** (déclenché par #911, qui a rendu `--suggere` allouante) |
| `test_485r2_portee_des_noms_offline` | `engine.entities.selectors.units.items` manquant, accusé sur `probe_927` | **cliquet DÉFECTUEUX** (résolveur de portée), révélé par le merge #924 |
| `test_host_inputs_offline` | `probe_919` / `probe_926` écrivent sous `scripts/python/logs/` | **armé par #913 et #923** (+ le `probe_468:1008` de #911) |
| `test_step_ordinal_ratchet_offline` | `probe_893_crusade_of_wrath_events.py:82` — ordinal `4` (`UnitDamaged`) en dur | **armé par le merge #893** (`93c64395`) |

### 2.1 Les deux cliquets DÉFECTUEUX, et ce qu'ils mesuraient à la place

**`test_468` accusait par FENÊTRE TEMPORELLE, pas par AUTEUR.** Sa fixture comparait la
*population* du registre de réservations avant/après chaque test. Or ce registre vit dans le
`.git` **commun** — partagé par 35 worktrees, alimenté en continu par les agents en vol. Mesure :
`#936` y est apparu pendant le test, alloué par `worktree-agent-ab5c3278368678ce3` (pid 62856),
ni par ce test ni même depuis ce worktree. Le cliquet rougissait donc **exactement quand la
campagne tourne** — quand on en a le plus besoin.

Le discriminant est le `pid` écrit dans la métadonnée, et la faute historique (`#917`, `#900-r8`)
était une allocation **EN PROCESS**. La fixture accuse désormais `pid == os.getpid()` et se
contente d'**imprimer** les allocations tierces. La portée perdue — un sous-processus du fichier —
est fermée par l'autre bout, **statiquement** :
`test_aucun_sous_process_de_ce_fichier_ne_vise_le_depot_REEL` dérive de l'AST du fichier que ses
quinze lancements de `probe_468` passent tous `--racine <dépôt jetable>`. Contre-épreuve jouée :
le garde rougit sur `sans --racine` **et** sur `--racine REPO`, et son anti-vacuité a mordu au
premier rejeu (`vus = 0` : la première version lisait les éléments de la liste au premier niveau,
alors que la forme réelle est `str(PROBE)`).

**`probe_485r1r1` confondait AFFECTATION et PARAMÈTRE.** `probe_927_fury_of_the_ancients.py` porte
`import engine.entities.selectors.units as U` ligne 238 (dans une fonction) et
`U = _live_units(...)` ligne 376 (dans une **autre**). Le dernier recours plat du résolveur
attribuait les `U.items()` de la seconde à la liaison de module de la première.

C'est le **faux positif exact** que #485-r2 avait déjà réparé pour `F` — la même forme, rouverte
par une autre porte. L'argument qui rend l'inconnu transparent porte sur les **paramètres**
(l'appelant y passe réellement le module ; 8 accès vrais mesurés). Une **affectation** dont on lit
la valeur dans le fichier même n'a pas cette propriété : `U = <appel>` ne lie jamais un module.
Le critère posé est conservateur — seules les valeurs qui **ne peuvent pas** désigner un module
masquent ; `M = <Name>` / `M = <Attribute>` (les deux seules formes de re-liaison), et
`importlib.import_module(...)`, restent transparents. Après correctif : **4 595 lectures /
651 écritures / 202 modules visés**, `rc=0`.

### 2.2 `IsOverwatchAttack` — attesté par LECTURE, pas par signature

Le brief l'exigeait, et c'est ce qui distingue une attestation d'un tampon. Deux surcharges au
build courant :

* la **0-aire** (celle que citent tous les gates portés) est
  `TriggeringAbilityIs(AbilityOrEffect.op_Implicit(<Effect = 1009 Overwatch_AutoAttack>))`.
  Le pseudo-C n'affiche que `op_Implicit(local_28)` : **l'immédiat est effacé**, et se lit aux
  octets du prologue — `ba f1 03 00 00`, soit `mov edx, 0x3f1`. Même piège que #924, et c'est ce
  qui rendait l'appariement impossible pour l'heuristique ;
* la **1-aire** prend un `IAbilityTypeSelector` et enveloppe `DSLSelectors$$Direct(<le même
  AbilityOrEffect>)` ; aucun call-site porté ne l'emploie.

Le port ne construit **aucun nœud** : il collapse le prédicat en un booléen `is_overwatch`, posé à
`True` par l'unique vecteur natif de l'auto-attaque d'overwatch
(`triggers/effect_triggers.py` → `AttackDamageOperation.execute(is_overwatch=True,
triggering_ability=1009)`), threadé par `_Normal.execute` jusqu'au `ctx` des effets, et lu par les
deux seuls gates natifs qui le testent (`effects/loki/darkangels.py` pour la disjonction
`IsRangedAttack | IsOverwatchAttack`, `effects/loki/dark_angels_passives.py` pour la branche A de
LionHelm). Verdict : **`PORTE_HORS_FACADE`**, même forme que `AttackUsedAttackDamage`.

### 2.3 `UseNormalAttack.spread_pct` — le régime lu, pas recopié du voisin

`IdunBattleLogic.Entities.DSLBehaviors$$UseNormalAttack` alloue
`DSLSelectors$$UnitNormalAttackType(caster)` puis construit
`UseActiveAbilityBehaviour$$.ctor(caster, target, <ce type>, parentAbility, triggerAbilityOrEffect,
options)` en **recopiant les options telles quelles** — aucun champ n'y est écrit. Ce sont des
`AbilityOptions` (0x14 octets), **pas** des `AttackDamageBehaviourOptions` : l'octet d'aiguillage
plate-vs-spread (`options+6`) n'existe pas sur ce chemin. Rien ici ne peut imposer une variance,
donc le régime est celui de l'attaque normale — `LU_BC`.

## 3. La voie DÉRIVÉE, et la mesure qui la commande

`probe_457_offline_tests_green.py` **est** la voie dérivée : son périmètre se dérive (tout test
non-`_live.py`, **323 fichiers**), donc un cliquet neuf y entre tout seul. Le problème n'est pas
la dérivation du périmètre — c'est la **sélection**.

### 3.1 `--since` manque 6 des 13 cas, et pas au bord

Mesure : pour chaque merge fautif, `probe_457 --since <merge>~1 --list` joué **sur l'arbre de ce
merge**, et l'on regarde si le cliquet qui a rougi y figure.

| merge | sélection | cliquet rouge | retenu ? |
|---|---|---|---|
| #911 | 45/313 (14 %) | `test_314_absolute_repo_path` | **NON** |
| #911 | 45/313 (14 %) | `test_host_inputs` | **NON** |
| #888 | 273/305 (90 %) | `test_366_r1_bcpatch_port_blindspot` | **NON** |
| #893 | 275/307 (90 %) | `test_step_ordinal_ratchet` | **NON** |
| #900 | 283/309 (92 %) | `test_449_r2_spread_face_combat` | **NON** |
| #909 | 284/312 (91 %) | `test_366_r1_bcpatch_port_blindspot` | **NON** |
| #913 | 288/315 (91 %) | `test_host_inputs` | oui |
| #922 | 189/318 (59 %) | `test_337_dsl_triggers_attestation` | oui |
| #923 | 319/319 (100 %) | `test_host_inputs` | oui |
| #924 | 292/320 (91 %) | `test_485r2` + `test_463r1` | oui |
| #926 | 292/322 (91 %) | `test_463r1` | oui |
| #927 | 189/323 (59 %) | `test_463r1` | oui |

**Ce n'est pas une question d'étroitesse.** À #893 la sélection retenait **90 %** du périmètre et
manquait quand même le cliquet fautif.

### 3.2 La cause est structurelle, et le code la nomme déjà sans la combler

Dans `impacted_files`, la moitié MESURÉE traite les `.py` par le **graphe d'imports** ; l'empreinte
(`dirs`) ne sert que pour les changements **hors-`.py`**. Un cliquet qui **BALAIE** des `.py` sans
les importer — `probe_273._scan_abs_repo`, le sweep de `test_step_ordinal`, l'inventaire de
`probe_449r2`, celui de `probe_366_r1` — n'a **aucune arête** vers le fichier qu'il accuse.

Le commentaire de #464-r2 le dit mot pour mot : « rien ne distingue, dans une empreinte déjà
écrite, la lecture d'IMPORT de la lecture APPLICATIVE d'un `.py` par un conftest-balayage (qui
n'est couverte par rien) ».

Même angle mort pour un cliquet qui délègue à un **sous-processus** : `test_host_inputs_offline.py`
a une empreinte `dirs: []`, `temoins: []` alors qu'il lance `probe_273` en entier — l'empreinte
n'instrumente que le process du test.

Et les `temoins` ne rattrapent pas : ce sont **deux chemins par (répertoire, extension)**, un
échantillon (67 témoins pour un balayage de ~1 400 fichiers), pas la liste.

### 3.3 Ce qui est livré

`probe_935_cliquets_insellectionnables.py` rend cette classe **dérivable** : il lit l'AST du
fichier de test **et de la clôture de ses imports locaux**, et classe INSÉLECTIONNABLE tout ce qui
balaie des `.py` (`rglob`/`glob` à motif `.py`, `walk`/`iterdir`/`scandir`, `git ls-files`) ou
sous-traite à un processus fils. Un cliquet neuf de cette forme entre dans la liste **sans que
personne y pense**.

⚠ **Le MOTIF est le discriminant, et sans lui la classe explose** : mesuré, un critère par nom
d'appel seul rendait **289 insélectionnables sur 323** — `gameconfig.glob` (données JSON) et un
`--name-only` cité **en prose** suffisaient à contaminer toute la clôture. Avec le motif :
**156 / 323**.

## 4. Le geste, et son coût

Le périmètre complet (**323 fichiers**) à 8 shards est le seul geste qui n'a pas d'angle mort :

```powershell
cd scripts/python ; $env:TACTICUS_ALLOW_RATCHETS=1
python probe_457_offline_tests_green.py --jobs 8
```

Coûts mesurés le 2026-08-11, **sous charge** (plusieurs agents actifs) :

| geste | périmètre | mur |
|---|---|---|
| les 61 cliquets racine, un process pytest par fichier, 8 en parallèle | 61 | **661 s** (somme série : 3 780 s) |
| les mêmes après réparation, 6 en parallèle | 61 | **496 s** |
| `probe_457 --jobs 8`, périmètre COMPLET | **323** | **763 s** |

Soit **763 s pour 323 fichiers** contre **661 s pour 61**. Le geste complet est donc, à la louche,
**cinq fois plus efficient par fichier** — et c'est le seul qui n'ait pas d'angle mort.

⚠ **Jouer les 61 racine séparément coûte PLUS CHER que jouer les 323 par `probe_457`** : un process
pytest par fichier paie l'import et la collecte 61 fois. Le shard par poids les amortit. La
partition « racine vs `tests/engine/` » n'a donc aucun intérêt — c'est une fausse piste que la
mesure élimine.

### 4.1 La partition n'est pas retenue, et c'est une MESURE qui la refuse

Le critère qui répartirait est écrit et **dérivé** (`probe_935`) : *un cliquet est sélectionnable
par diff si, et seulement si, tout ce dont son verdict dépend passe par ses imports ou par une
lecture hors-`.py`* — **156 insélectionnables / 167 sélectionnables**. La composition serait
`{insélectionnables} ∪ {sélection --since}`.

**Elle n'achèterait presque rien.** Taux de rétention de `--since` mesuré sur les 11 merges :

    14 %, 59 %, 59 %, 90 %, 90 %, 91 %, 91 %, 91 %, 91 %, 92 %, 100 %

**Médiane : 90 %.** La cause est structurelle elle aussi : un merge de ce dépôt touche
`engine/**`, et la clôture arrière du graphe d'imports y remonte vers presque tout le périmètre.
Les deux seuls cas économes (14 %, 59 %) sont des merges d'OUTILLAGE — et le premier est
précisément celui dont `--since` a manqué les deux cliquets rouges.

⇒ **À chaque merge, jouer le COMPLET.** Une partition qui économise 10 % du mur en échange d'un
angle mort qui a laissé passer **6 rouges sur 13** est un mauvais échange. `probe_935` n'est donc
pas livré comme sélecteur : il est livré comme la **mesure qui interdit** de « ré-optimiser » plus
tard vers `--since` sans traiter d'abord son angle mort (résidu #935-r1).

⚠ Le câblage de `probe_935` **dans** `impacted_files` a été essayé puis écarté : la
classification coûte **73,7 s**, à ajouter aux 32,7 s du graphe, pour récupérer 10 % de mur. Le
rapport coût/gain est contre.

## 4.2 Ce que la passe complète a mis au jour, HORS de cette tranche

Le mur de 763 s a inscrit au ledger **309 VERT / 14 ROUGE**, et les 14 vivent tous dans
`tests/engine/` — hors des 61 cliquets à l'échelle du dépôt. **Aucun n'est le fait de cette
tranche** : les 14 ont été rejoués dans un arbre témoin détaché à `7611776e` **pur** et y rendent
`rc=1` à l'identique (14/14 PRÉEXISTANTS).

```
tests/engine/runner/test_287r14_get_actual_target_offline.py
tests/engine/runner/test_287r14r1_resolution_tile_target_offline.py
tests/engine/runner/test_421_effect_active_gate_offline.py
tests/engine/runner/test_camo_seed_inventory_offline.py
tests/engine/runner/test_refresh_active_flag_discriminant_offline.py
tests/engine/runner/test_statmod_captured_channel_offline.py
tests/engine/test_270r1_volet2_dict_keys_enum_offline.py
tests/engine/test_270r4r2_cycles_imports_offline.py
tests/engine/test_270r4r2r2r3_gardes_du_hissage_offline.py
tests/engine/test_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason_offline.py
tests/engine/test_433r4r1r4r2r1r1_derivation_morte_offline.py
tests/engine/test_462r4eor2_over_reduce_purge_offline.py
tests/engine/test_477r24r1_slots_interface_offline.py
tests/engine/test_lions_wrath_custom_utility.py
```

⚠ **Le ledger frais n'est PAS commité, et c'est délibéré.** `probe_547_ledger_sans_verdict_non_vert`
est **PASS** sur le ledger versionné et **FAIL** sur le frais : **12** de ces 14 ne sont pas dans
`NON_VERTS_DECLARES`, et deux déclarations y deviennent PÉRIMÉES (`tests/test_337_...` — réparé
ici — et `tests/test_480r8_...`). Régénérer le ledger exigerait donc d'attribuer et de déclarer
12 rouges hors périmètre : c'est une tranche à part entière, pas un artefact à régénérer au
passage. Le ledger versionné reste tel quel (il est simplement en retard : 17 fichiers sans
entrée, 5 attestations périmées).

## 4.3 La démonstration est arrivée seule, pendant la tranche

Le rebase sur `ff80e064` (cache de board avancé, qui porte le merge **#932** `Deathwing`) a
**ré-armé `test_463r1` immédiatement** : `tests/engine/test_932_deathwing_offline.py` entre au
périmètre offline sans entrée d'empreinte, donc « 1 fichier offline NON MESURÉ ». Refermé par
`probe_457 --measure-missing` et l'artefact commité.

C'est le régime, pas l'accident : **tout merge qui ajoute un test offline rouvre ce cliquet**, et
il n'existe aucun moyen de le voir sans jouer le cliquet. La cadence mesurée du dépôt est de
plusieurs merges par jour.

**Puis une seconde fois, sur un autre cliquet.** Le rebase sur `5dbe6c9c` (merge #928,
`TwistedScience`) a fait rougir `test_366_r1` sur un trou de couverture qui n'existait pas au
lancement de la tranche : `engine/runner/abilities/genestealer.py:755` —
`ability_var(self.ABILITY_ID, AbilityConstantType.range.name, is_constant=True)`. Aucun des deux
axes ne se résout (attribut de classe lu par `self.`, membre d'enum), soit la **troisième**
occurrence de la lacune que `abilities/base.py` nommait déjà en annonçant qu'elle **croîtrait** —
« écrire le membre d'enum plutôt que le littéral est ce que `CLAUDE.md` prescrit, donc ce patron
se répandra ». Trou nommé, perte mesurée nulle (`(HeroicFusillade, range)` n'est patché par aucune
fixture).

⚠ Ces deux rouges **n'existent que parce que la tranche a rebasé et re-joué**. Aucun n'était dans
son diff. C'est l'argument le plus direct pour la prescription du §4 — et ils sont apparus en
**quatre heures**.

## 5. Ce qui n'est PAS couvert

* La **sur-approximation** de `probe_935` va dans le sens sûr mais reste grossière : un module qui
  `glob` un répertoire de données avec un motif contenant `.py` est classé balayeur à tort. Le
  compte des deux classes est imprimé à chaque run, donc une dérive se voit — mais rien ne la
  rougit. Résidu **#935-r1**.
* Le **correctif de fond** — apprendre à `impacted_files` que l'empreinte couvre aussi les `.py`
  balayés — n'est pas livré : il touche un foyer très partagé, et le grain disponible
  (`dirs`, granularité répertoire) sur-sélectionnerait massivement pour les tests qui *importent*.
  Résidu **#935-r1**.
* Le trou de couverture `engine/predict.py` est **nommé**, pas résolu : sa cause de fond est le
  résidu **#484-r1** (résoudre une constante importée d'un AUTRE module — l'env du résolveur de
  `probe_366_r1` est PAR MODULE). La perte est bornée et mesurée : le couple
  `(NetherRealmCasket, hpToHeal)` n'est patché par aucune fixture du dépôt.
* La face `#924-r2` (`InescapableDeath`, bonus d'overwatch désarmé) reste ouverte telle quelle :
  l'attestation `IsOverwatchAttack` posée ici décrit le port **actuel**, elle ne livre rien.
* **Aucune confrontation live** : tous ces cliquets sont offline, et aucun n'a exigé de session.
