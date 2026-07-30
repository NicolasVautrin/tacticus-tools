# case-283 — les quatre enums renumérotés : ce qui s'EXÉCUTE, ce qui se lit, ce qui n'est ni l'un ni l'autre

**Résidu `#281-r3`.** #281 §0 annonçait « 113 occurrences de `On(0x2b)`, erreur **inerte** à
l'exécution ». Les deux moitiés de la phrase sont fausses : le gisement fait **728 citations**
sur les quatre enums, et **il n'est pas inerte** — trois sites l'exécutaient.

Rejouer : `python scripts/python/probe_283_enum_ordinal_sweep.py` (offline pur, 5 étapes) ;
`--step live` ajoute la confrontation au binaire **chargé** (session vivante, aucune injection) ;
cliquet : `python -m pytest scripts/python/tests/test_enum_ordinal_ratchet_offline.py`.

---

## 1. Le diff, re-dérivé des deux tables VERSIONNÉES

`data/symbols/<build>/frida/enums.tsv` existe pour les deux builds : le rapport de changement
est donc calculable dans un worktree frais, sans session ni dump (`--step diff`).

| enum | `gqfc5mff6c` → `rnca9r7q6c` | ce qui a bougé | membres déplacés |
|---|---|---|---|
| `IdunBattle.DSL.EventTriggerType` | 77 → 76 | **retire** `ArmorChanged` (40) | 36 (41..76 → 40..75) |
| `IdunBattle.Configuration.UtilityType` | 82 → 83 | **insère** `AttackTile` (8) | 73 (8..81 → 9..82) |
| `IdunBattle.Streams.StepType` | 63 → 62 | **retire** `RestoreArmorInfo` (7) | 55 |
| `IdunBattle.Operations.DisplaceDirection` | 8 → 7 | **retire** `Pull` (0) | **7 sur 7** |

Aucun décalage n'est supposé : ils sont lus. `DisplaceDirection` est le cas extrême — le membre
retiré est le **premier**, donc *tous* les ordinaux survivants changent, y compris `Push` (1 → 0).

## 2. Le piège qui interdit tout `sed`, et la règle qui le désamorce

`0x2b` a deux sens : `EventTriggerType.UnitHealed`, **et** la clé de config `extraHit`
(`AbilityConfiguration$$GetNumberConstant(cfg, 0x2b)`, ~100 occurrences légitimes). La règle du
probe est donc : **jamais un nombre nu** — seule compte la CO-OCCURRENCE d'un nombre et du **nom
d'un membre**. L'ambiguïté est elle-même mesurée, pas devinée : un nom présent dans plusieurs
enums du build à des ordinaux différents (`Attack`, `Spawn`, `Damage`, `Push`, `Info`…) ne compte
que si la prose nomme aussi l'enum.

Ce que ça donne sur le corpus : **0 faux positif d'homonyme**, et la contre-épreuve est gardée
(`test_la_prose_ne_signale_pas_l_homonyme_extraHit`).

## 3. Le tri en trois catégories, et le seul chiffre qui compte

| catégorie | compte | verdict |
|---|---|---|
| **EXÉCUTABLE** | **3 sites** (+ 5 ordinaux figés justes-mais-muets) | corrigés, gardés |
| **PROSE** | 728 citations dérivées dépôt entier (681 = ancien ordinal **prouvé**) | 298 corrigées, 383 en résidu |
| **HOMONYME** | ~100 `extraHit` + tout `On(<n>)` sous le point de décalage | intouchés, par construction |

### 3.1 Les EXÉCUTABLES

**`frida/hooks/features/ai-utility-trace.ts` — `UTILITY_TYPE_NAMES`.** 82 entrées figées sur
`gqfc5mff6c`, **37 fausses**. La table vivait **INLINE dans un `features/`**, donc hors de la
garde #252 qui ne couvre que `frida/hooks/data/`. Elle n'est pas décorative :
`prePopulateKnownConfigs` **appelle** `UtilitiesDatabase$$GetUtilityConfig(type, coll)` avec ces
ordinaux, puis enregistre la config rendue sous le nom associé. Deux dégradations, silencieuses
toutes les deux :

* à partir de l'id 8, chaque entrée de `knownConfigs` porte le libellé de l'utilité **voisine**
  (`Elevation` étiquetait `AttackTile`, `CapturePoint` étiquetait `MoltenForm`…) ;
* `AttackTile` étant **inséré**, l'enum a gagné un ordinal que la table n'avait pas : la dernière
  utilité n'était **jamais** interrogée.

Geste : rapatriée en `frida/hooks/data/utility-type-names.ts`, **générée** par
`regen_hook_name_tables.py` et **gardée** par `probe_252_hook_name_tables.py` — pas un mécanisme
parallèle, l'infra #256/#252 existait déjà et ce fichier lui manquait.

**`scripts/python/probe_hazeord_blast_radius.py` — `DEATH_EVENTS`.** La table portait
`55: "UnitDefeated"` ; `UnitDefeated` vaut **54** depuis la MAJ, et 55 est `AttackChanged`. Or
`DEATH_EVENTS` est **intersectée** avec l'`event_id` des classes du registre : les consommateurs
d'`UnitDefeated` sortaient de l'inventaire sans erreur ni trace. Mesure avant/après :

```
avant : registre TOTAL = 84 classes ; consommateurs de mort = 19
apres : registre TOTAL = 84 classes ; consommateurs de mort = 21
        On(54 UnitDefeated) x2 : AmbushSummonAbility, CosmicHorrorOnKillAbility
```

Le sens de la dégradation était le **sous-comptage**, pas le sur-comptage : aucune classe portée
n'écoute `AttackChanged`. C'est un coup de chance, pas une propriété — la forme symétrique
(compter un voisin peuplé) est celle qu'avait mesurée `case-254b-a`.

**Les 5 ordinaux figés JUSTES aujourd'hui** (`probe_n8b_turnend_consumers.py::TURN_END = 23`,
`probe_o10_defork.py::DAMAGE_DEALT = 16`, et trois `assert t.event_id == 19|22|9`) : tous sous le
point de décalage, donc exacts sur les deux builds. C'est **exactement** ce qui les rendait
dangereux — rien n'aurait signalé leur invalidation, comme `CAPTURE_POINT = 24` de #272 jusqu'à
ce qu'un test rouge le trahisse. Résolus par membre.

### 3.2 La PROSE — 298 corrigées, et la preuve qu'elles l'étaient

Le critère de réécriture automatique n'est pas « le nombre a l'air faux » mais **« le nombre vaut
EXACTEMENT l'ordinal de ce membre sur le build précédent »**. C'est une preuve, pas une
heuristique : elle identifie la citation comme une reproduction du décompilé de `gqfc5mff6c`.

Sur `scripts/python` : **296 citations sur 305 portaient cette signature** ; les 9 autres sont
des faux positifs de proximité, tous vérifiés à la main (`Elevation 10/niveau` = un poids BC,
`Damage 437 Armour` = une stat d'unité, `MoltenForm 5,10` = des ids d'effet, `UnitDamaged = 6
coups` = un compte…). Aucun n'était une vraie dérive. Plus 2 dans `frida/hooks/features/
dump-composed.ts`.

**Contrôle adversarial de la migration** (le seul qui compte pour un fix de 296 lignes) : pour
chacun des 88 fichiers touchés, les flux de tokens **hors COMMENT/STRING** avant et après sont
comparés. Résultat **88/88 identiques**, et 0 token de prose ajouté ou supprimé. La migration est
donc *prouvée* inerte, pas supposée.

Deux choix de fond, qui pourraient se discuter et qui sont assumés :

* **on met l'ordinal à jour, on ne le supprime pas.** Un lecteur qui ouvre Ghidra sur le binaire
  INSTALLÉ y lit `0x2a` : c'est le service que rend la citation. Écrire `On(PreUnitAbility)` sans
  ordinal supprimerait cette dérivation ;
* **la paire nom + ordinal devient auto-vérifiable.** C'est ce que le cliquet contrôle en
  permanence — un prochain build fera rougir le probe, qui pointera les lignes. Le nombre n'est
  plus une bombe silencieuse, il est *gardé*.

Effet de bord assumé : plusieurs docstrings annoncent « RE (décompilé ghidra, build
`gqfc5mff6c`) » tout en citant désormais l'ordinal de `rnca9r7q6c`. L'estampille de build est un
gisement distinct (elle désigne un binaire qui n'est plus installé) — non traité ici.

## 4. Ce qui est INDÉCIDABLE, et pourquoi ce n'est pas de la paresse

`--step on` compte les `On(<n>)` **nus** — sans nom de membre accolé. L'ancre est sûre :
`IdunBattleLogic.Entities.DSLFactory$$On(EventTriggerType, ...)` garantit que le nombre EST un
`EventTriggerType`, sans risque d'homonyme. **Le verdict, lui, ne l'est pas** :

```
scripts/python : 613 stables, 132 ambigus
docs           : 360 stables, 73 ambigus
```

« Ambigu » = l'ordinal a changé de propriétaire, donc la citation dit une chose si elle a été
écrite avant la MAJ, une autre après. Et les deux existent, mesurés :

| site | écrit | verdict |
|---|---|---|
| `probe_281_pre_unit_ability_shortcut.py` : `On(0x2a) & IsNormalAttack` | après la MAJ | **JUSTE** |
| `engine/runner/abilities/handler.py` : `On(0x2b)` | après la MAJ | **FAUX** (recopié) |

**Le `git blame` ne tranche pas non plus** — mesuré : sur les 7 sites `On(<n>)` ambigus écrits
APRÈS la migration, **6 recopiaient l'ancienne valeur**. Une correction automatique par
« décalage » aurait donc cassé la citation juste de `probe_281` tout en réparant les six autres.

Corriger un de ces sites exige de relire **quel trigger natif il cite** : c'est un travail de RE
par site, pas une migration. → backlog `#283-r1`.

## 5. Le cliquet

`scripts/python/tests/test_enum_ordinal_ratchet_offline.py` — offline, sans runner. Il vérifie
**deux** choses, et la seconde n'est pas décorative :

1. les trois gates exécutables sont verts (mirrors Python, littéraux, tables indexées) ;
2. **le détecteur mord** sur les motifs réellement rencontrés — dont deux qui ont produit des
   erreurs pendant la mise au point de ce cas même : le faux positif
   `TILE_LEAVES[UtilityType.CapturePoint][1]` (7 occurrences, toutes sur du code *déjà correct*)
   et le faux négatif de l'homonyme `extraHit`.

Un cliquet qui ne détecte rien passerait au vert sur un dépôt pourri. C'est arrivé **deux fois
pendant ce cas**, et les deux fois le symptôme était un zéro qui se lisait « rien à signaler » :

* `_SKIP_PARTS` filtrait sur le chemin **absolu**, qui contient `worktrees` pour tout agent — le
  balayage rendait « 0 classe trouvée » et `VERDICT: PASS`. Même famille que l'exclusion par
  sous-chaîne `engine` mesurée en #281 §3 ;
* la confrontation live (§6) parsait `values` comme une liste alors que `dumpEnum` rend un
  **dict** — `live=0` pour les quatre enums, donc `0 divergent`, donc « OK ».

**Un compte de zéro se vérifie, il ne s'interprète pas.** C'est le même invariant que le
tri-état de `host_inputs` (`null` = pas mesuré ≠ `[]` = mesuré et vide).

## 6. Validation

| mesure | résultat |
|---|---|
| `probe_283 --step live` (seconde source **indépendante**) | `dumpEnum` sur le binaire CHARGÉ vs `enums.tsv` : **228 membres, 0 divergence** sur les 4 enums |
| `probe_283 --step mirror` | 2 mirrors (`EventTriggerType` 76/76, `UtilityType` 68/83), **0 divergent** |
| `probe_283 --step exec` avant / après | **5 figés + 3 tables** / **0** |
| `probe_283 --step tables` avant / après | **46 entrées divergentes** / **0** |
| `probe_hazeord_blast_radius.py` avant / après | consommateurs de mort **19 → 21** |
| contrôle d'inertie du `--fix` (88 fichiers) | **88/88** flux de tokens exécutables identiques |
| `pytest tests/test_enum_ordinal_ratchet_offline.py` | **9 passed** |
| `pytest` des 3 tests live touchés (CPB / DestroyerHive / Hypersensory) | **18 passed** |
| `probe_274` (StepType/GroupType) | **PASS** — 0/0 |
| `probe_252` (tables de hooks) | **OK** sur les 6 tables, dont la nouvelle |
| `probe_275` (enum_maps) | **OK** — les 6 blocs collent |
| `probe_181` / `probe_281 --step classify` | **94/94, 0 manquante** / **GATE VERT** |
| `tsc --noEmit -p tsconfig.hooks.json` | **0 erreur** sur `ai-utility-trace.ts` et `utility-type-names.ts` |
| `py_compile` de tout `scripts/python` | OK |

## 7. Ce qui n'est PAS couvert

* **La correction du hook n'est pas confrontée live.** `frida/hooks/*` exige un rebuild + un
  **reinject** — geste proscrit tant qu'un autre agent tourne. Ce qui EST établi : la table colle
  au build (`probe_252`), le fichier typecheck, et la boucle consommatrice est protégée par son
  `try/catch` (l'ordinal `9999 = STRIPPED`, désormais présent, tombera en `skipped++`). Ce qui ne
  l'est PAS : que `prePopulateKnownConfigs` peuple bien 3 configs de plus en session réelle.
* **Les 205 `On(<n>)` nus ambigus** (132 dans `scripts/python`, 73 dans `docs/`) — §4,
  backlog `#283-r1`.
* **`docs/` n'est pas migré** : 394 citations dérivées, dont 356 à signature « ancien ordinal ».
  C'est un choix, cohérent avec `case-272` §5 (« les lire comme des étiquettes historiques ») et
  avec `case-254b-b` §7 (on ne rétro-corrige pas un compte rendu produit par un autre build). Les
  case-docs sont **datées** ; `probe_283 --step prose --racine docs --fix` migrerait les 356 d'un
  coup si on décidait l'inverse. → backlog `#283-r2`.
* **Le détecteur ne suit pas la donnée à travers un appel de fonction.** Un ordinal passé en
  argument puis comparé ailleurs échappe au balayage — même limite que `probe_274` §7. Les motifs
  couverts sont ceux qui existaient réellement, pas une preuve d'exhaustivité.
* **`DisplaceDirection` n'a AUCUN consommateur d'ordinal dans le dépôt** — vérifié : le nom
  n'apparaît nulle part sous `scripts/python`, et `engine/runner/operations/displace.py` ne porte
  la valeur que dans sa prose (`type=1 = FindTileToPush`, corrigé en `type=0`). Le port
  n'implémente que le push et ne compare jamais d'ordinal. C'est le plus renuméroté des quatre
  (7/7) et le seul totalement inerte — signalé parce qu'un futur port de `Pull`/`Switch` devra
  partir de la table, jamais d'une doc antérieure au 2026-07-29.
* **Aucun mirror Python de `StepType` ni de `DisplaceDirection`** : le premier se résout par nom
  (`stream_events.step_id`), le second n'est pas porté. L'étape `mirror` le DIT plutôt que de
  rendre un silence.
