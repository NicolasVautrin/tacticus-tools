# `#254b-b` — les ordinaux `StepType` / `GroupType` écrits en dur

`step` et `group` sont les 1ers arguments de `IdunBattle.Streams.StreamDispatcher$$Action(StepType,
BEntityId, Dictionary<TagKey,int>)` et `IdunBattle.Streams.StreamDispatcher$$StartGroup(GroupType,
BEntityId, string, Nullable<BEntityId>)`. Ces enums sont **implicitement numérotées** : retirer un
membre au milieu décale de −1 tout ce qui suit. La MAJ `gqfc5mff6c` → `rnca9r7q6c` a retiré
`StepType.RestoreArmorInfo` (7) — 63 membres → 62.

Un littéral figé ne rend alors pas « rien » : il rend **un autre pas**, sans erreur ni trace.

## 1. La question binaire, et sa réponse

**Après correction, `probe_202c_tutelaries.py` rend-il le même verdict qu'avant sur le cas connu
(seed 20203) ?**

| run | code | build | verdict |
|---|---|---|---|
| publié — `case-202` §8 | littéraux `gqfc5mff6c` | `gqfc5mff6c` | **PASS** |
| contre-épreuve jouée ici — probe INCHANGÉ | littéraux `gqfc5mff6c` | `rnca9r7q6c` | **FAIL** `A1:effet, A2:no-spawn, A4:count, B:chain-count` |
| après correction | `step_id`/`group_id` par NOM | `rnca9r7q6c` | **PASS** |

**Le verdict publié est CONFIRMÉ, aucun des deux résultats publiés antérieurement n'était erroné.**

* `case-202` §8 (« probe 202c seed 20203 — PASS ») était **juste** : il a été mesuré sur
  `gqfc5mff6c`, où les littéraux désignaient les bons pas. Il est aujourd'hui **re-mesuré vrai**
  sur `rnca9r7q6c`, aux mêmes chiffres (ci-dessous).
* `case-254bis` §5 et `case-254b-a` §6 annonçaient « son bloc `spawn_meta` ne se remplit plus »
  en le marquant **« non rejoué »**. La contre-épreuve le confirme et l'**élargit** : ce n'est pas
  seulement `spawn_meta`, ce sont A1 (l'effet 1197), A2/A3 (les deux spawns) et la chaîne de B qui
  disparaissent — 4 sous-verdicts sur 6.

Le `FAIL` intermédiaire n'a jamais été publié : c'est l'artefact des ordinaux décalés, **pas** une
régression du port. Aucun fichier `engine/**` n'a été modifié par ce cas.

### Le sens de la dégradation dépend des co-prédicats

`case-254b-a` avait mesuré une dégradation par **sur-comptage** (les pas voisins visés par
`analyze()` valaient 28 `ChangeStats` et 31 `LoseEffect` là où on croyait lire des morts et des
effets). Ici c'est l'inverse : chaque filtre de `probe_202c` est accompagné d'un test de **tag**
(`Unit_Parent_Id`, `UnitStats_MaxHealth`, `Effect_SourceActiveAbility`…) que le pas voisin ne porte
pas — donc **zéro** match au lieu de N. Les deux formes sont muettes ; on ne peut pas prédire
laquelle on subit sans lire le site.

## 2. Ce que désignaient les littéraux

| littéral | visé (`gqfc5mff6c`) | désigné sur `rnca9r7q6c` | valeur correcte |
|---|---|---|---|
| `step == 10` | `AddUnit` | `AddMachine` | 9 |
| `step == 13` | `ChangeStats` | `ChangeAbility` | 12 |
| `step == 14` | `ChangeAbility` | `FinishMatch` | 13 |
| `step == 16` | `ReceiveEffect` | `LoseEffect` | 15 |
| `step == 30` | `Info` | `TerritoryCapture` | 29 |
| `step == 4` | `UnitDamaged` | `UnitDamaged` | 4 (précède le membre retiré) |

`Info` est bien le pas porteur du profil d'arme : le run corrigé **mesure** 1 event `Info` portant
`Attack_Weapon_DamageProfile` (`[202c] A0`, diagnostic permanent du probe). Sans cette mesure, A4
pourrait passer sur le seul groupe `EffectAdditionalHits` et un mauvais nom de pas resterait
invisible — c'est le cas dans ce scénario précis, où l'attaque est déjà qualifiée par le groupe.

`GroupType`, lui, n'a **pas** bougé (104 membres, 0 ordinal divergent entre les deux builds). Les
littéraux de groupe étaient donc justes — et corrigés quand même : un ordinal juste aujourd'hui est
faux au prochain build, en silence.

## 3. Le balayage du dépôt — 25 sites, 4 tables

`probe_202c_tutelaries.py` avait été trouvé **par hasard**. Le balayage AST
(`probe_274_step_ordinals_sweep.py`) en rend 24 autres, plus quatre tables de noms indexées par
ordinal que la recherche de comparaisons ne voit pas.

**Décalés, donc FAUX sur `rnca9r7q6c`** :

| fichier | sites | ce qu'il lisait à la place |
|---|---|---|
| `probe_202c_tutelaries.py` | 5 | cf. §2 |
| `probe_217_thequickening.py` | 5 (`(16,18)`, `(17,19)`, `13`) | ajout et retrait d'effet **intervertis** (`LoseEffect`/`DeactivateEffect` comptés comme ajouts) |
| `probe_217_blackrage.py` | 2 (`13`, `16`) | `set_health` et `effects` restaient vides |
| `rl_collect_batch.py` | 1 (`30`) + table `STEP_NAMES` | le fallback `Info(arme)` ne s'armait plus ; la colonne `stream_event.step_name` de la base RL décalait de +1 tout pas ≥ 7 |
| `rl_ingest_postgres.py` | table `STEP_NAMES` | idem (copie du même littéral) |
| `frida/public/src/battle-log.js` | tables `STEP_LABEL` / `GROUP_LABEL` + map `STEP` + `switch` | le journal de bataille étiquetait chaque pas ≥ 7 du nom du **précédent** ; `processStreamEvents` posait/déplaçait/retirait les pions sur les MAUVAIS events (`AddUnit`, `AddMachine`, `RemoveUnit`, `FinishMatch`, `DirectlyKillUnit` tous décalés) |

**Justes aujourd'hui, corrigés quand même** : `probe_60bis_directcap.py` (`4`, `(5,6)`),
`probe_67_combat_limits.py`, `probe_knockback_pct.py`, `probe_mortis_round.py`,
`probe_rngcrit_1202.py`, `_probe_betrayer.py` (`4`, `3`),
`tests/engine/runner/test_savage_echoes_live.py` (`4`),
`test_darkangels_lot1_live.py` + `test_effect_immunity_live.py` (`group == 22`).

## 4. Un SECOND défaut, indépendant du build : la table qu'on lisait mentait déjà

`enum_maps.GROUP_TYPE` (généré par `rl_gen_enum_columns.py` depuis un `dump.cs`) porte **102**
membres au lieu de 104 : `Ability_Displace` (36) et `EndTurn` (48) y manquent. Tout ordinal ≥ 36 y
est donc décalé — et ce décalage **précède les deux builds** (`GroupType` est identique sur
`gqfc5mff6c` et `rnca9r7q6c`).

Conséquence mesurée dans `rl_collect_batch.py` :

```
_ATTACK = (12, 32, 59)         # User_UseAbility, Ability_Attack, NormalAttack
```

`59` vaut `NormalAttack_AtomicDamage` **dans `enum_maps`** — d'où le commentaire. Sur le build réel,
`59 = ZingerAbility` et `NormalAttack_AtomicDamage = 61`. Le fallback « 015 » censé rattraper les
~3 % de coups dont l'`Info(arme)` est dans un scope frère **ne s'est donc jamais armé sur une
attaque normale** : il s'armait sur les scopes d'une ability sans rapport.

Corrigé en résolvant par nom. C'est un **changement de comportement** de l'ingest RL, assumé et
signalé ici : le littéral portait l'intention `NormalAttack`, la table le trahissait.

`enum_maps.py` lui-même n'est pas régénéré (cf. §7).

## 5. Le geste

* `stream_events.group_id(nom)` — pendant exact de `step_id`, même contrat : résout contre
  `data/symbols/<CURRENT>/frida/enums.tsv` (**versionnée**, donc lisible dans un worktree frais
  depuis `#254b-a`) et **lève** si le membre a disparu. Un membre disparu doit casser, jamais se
  replier sur un ordinal qui appartient désormais à un autre pas.
* Tous les sites du §3 passent par `step_id("<Nom>")` / `group_id("<Nom>")`.
* Les tables `STEP_NAMES` de `rl_collect_batch` et `rl_ingest_postgres` ne sont plus des littéraux :
  elles délèguent à `stream_events.step_name`.
* `battle-log.js` : tables régénérées depuis `enums.tsv`, map `STEP` **dérivée** de `STEP_LABEL` par
  nom (un nom absent rend `-1` — donc « plus aucun rendu », jamais « un autre pas » — et la console
  le dit), `switch` branché sur le NOM du pas.

### Le cliquet

* `python scripts/python/probe_274_step_ordinals_sweep.py` — balayage AST (accès direct, alias de
  variable, `in` sur tuple, **et** le couple « constante-tuple nommée + champ de dict » par lequel
  `rl_collect_batch` cachait ses ordinaux de groupe), plus la comparaison des tables du frontend à
  `enums.tsv`. Il imprime, pour chaque littéral, ce qu'il désignait **avant** et ce qu'il désigne
  **maintenant**.
* `scripts/python/tests/test_step_ordinal_ratchet_offline.py` — offline, sans runner. Il vérifie
  **deux** choses : que le dépôt est propre, **et** que le détecteur mord sur les quatre motifs
  réellement rencontrés. Un cliquet qui ne détecte rien passerait au vert sur un dépôt pourri.

## 6. Validation

| mesure | résultat |
|---|---|
| `probe_202c_tutelaries.py --seed 20203`, probe **inchangé**, build `rnca9r7q6c` | **FAIL** `A1:effet, A2:no-spawn, A4:count, B:chain-count` |
| `probe_202c_tutelaries.py --seed 20203`, probe **corrigé** | **PASS** — identique au verdict publié |
| chiffres du run corrigé | A1 `Effect_RemainingTurns=1` ; A2 Horror `(5,8)` hp **3589** = `summonHp[50]×180 %` ; A3 Screamer `(4,6)` hp **4487** = `summonHp_2[50]×180 %` ; A4 1 == 1 ; B screamers 1 → 3, cascade **2 spawns == 2 attaques Psychic** ; C **+0** |
| A0 (diagnostic neuf) | **1** event `Info` portant `Attack_Weapon_DamageProfile` ⇒ le pas nommé est bien le porteur |
| `probe_274_step_ordinals_sweep.py` avant | **FAIL (64)** — 25 littéraux + 39 divergences de labels |
| `probe_274_step_ordinals_sweep.py` après | **PASS** — 0 / 0 |
| `pytest tests/test_step_ordinal_ratchet_offline.py tests/test_stream_events_offline.py` | **24 passed** |
| `python stream_events.py` (smoke aller-retour) | `StepType(62) GroupType(104) ; UnitDamaged=4 RemoveUnit=11 ReceiveEffect=15 ; User_UseAbility=12 NormalAttack_AtomicDamage=61` |
| `node --check frida/public/src/battle-log.js` | OK |
| `py_compile` des 13 fichiers Python touchés ; `pytest --collect-only` des 3 tests live touchés | OK — **18 tests collectés** |

Le run **avant** est la mesure discriminante : le jeu, lui, spawnait bien (`B` observe
`screamers 1 -> 3` par `decisionView`) pendant que le parseur rendait `spawns=0`. C'est la signature
exacte d'un filtre qui regarde le mauvais pas.

## 7. Ce qui n'est PAS couvert

* **`enum_maps.GROUP_TYPE` reste périmée** (102/104, décalée à partir de 36). Sa régénération passe
  par `python scripts/python/rl_gen_enum_columns.py`, qui lit un `dump.cs` — artefact **gitignoré**,
  absent d'un worktree. Le seul **consommateur** de cette table (`rl_collect_batch._group_name`) est
  repointé sur `enums.tsv` ici, donc la base RL est correcte ; la table elle-même reste fausse pour
  quiconque l'importerait directement. La même incertitude vaut pour les autres enums qu'elle porte
  (`effect_type`, `active_ability_type`, `passive_ability_type`, `damage_profile_type`,
  `unit_spawn_source`) — **non vérifiées ici**.
* **La colonne `step_name` / `group_name` des batches DÉJÀ ingérés n'est pas rétro-corrigée.** Les
  batches ingérés depuis la MAJ portent des noms décalés en base ; le SQL de backfill de
  `013_enum_fk_and_names.sql` ne couvre que les colonnes `*_name` d'enums d'ability/effet.
* **Le changement de `_ATTACK`/`_ACTOR` (§4) n'est pas confronté live** : il modifie la
  classification `normal_melee` / `normal_ranged` de l'ingest RL, qui ne se mesure que sur un batch
  complet. La correction est justifiée par la lecture (intention du commentaire × table réelle), pas
  par une mesure de bout en bout.
* **Le balayage ne couvre que Python + `battle-log.js`.** Les hooks TypeScript (`frida/hooks/**`) ne
  comparent aucun ordinal de `StepType`/`GroupType` (vérifié par grep), mais aucun cliquet ne le
  garde.
* **Le détecteur ne suit pas la donnée à travers un appel de fonction** : un ordinal passé en
  argument puis comparé dans une autre fonction échappe au balayage. Les motifs couverts sont ceux
  qui existaient réellement, pas une preuve d'exhaustivité.
