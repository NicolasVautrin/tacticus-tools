# case-10026 — trois rouges de `master`, trois causes distinctes, **zéro défaut de port**

`#10026`. Trois fichiers non-VERT sur `master` (`609c8a53`, build `t6dpr4k06g`), traités
séparément parce que rien ne les unifie. Verdict des trois : **aucun n'accusait le port**. Ce qui
est réparé, ce sont les **instruments** — et chacun a été rendu **plus mordant** qu'avant, jamais
retiré.

| fichier | avant | après | cause |
|---|---|---|---|
| `tests/engine/runner/test_951r1_in_melee_offline.py` | 3 failed / 8 passed | **11 passed** | montage PÉRIMÉ |
| `tests/engine/runner/test_936_wrathful_devotion_offline.py` | 1 failed / 21 passed | **23 passed** | INVENTAIRE FAUX |
| `tests/engine/test_920_maw_claws_of_thyrax_offline.py` | 1 failed / 18 passed | **19 passed** | PRÉMISSE EXPIRÉE |
| `tests/engine/test_908_nether_realm_casket_offline.py` (hors liste) | 14 passed — **FAUX VERT** | **14 passed**, et il mord | même cause que `920` |

---

## 1. `951r1` — un raccord NATIF légitime a périmé un DOUBLE de test

### Le rouge, lu

Les trois tests rouges passent tous par le même helper, et tombent au même endroit :

    engine/runner/operations/remove_unit.py:184
    AttributeError: '_Ent' object has no attribute 'add_component'

`RemoveUnitOperation.execute` fait `e.add_component(UnitFlagsComponent())` quand l'entité n'en
porte pas. Le fichier de test montait deux doubles maison — `_Ent`, `_St` — dont la docstring
disait explicitement « le strict minimum que `register_defeated_unit` consulte ».

### La cause

`#10015-r3` (`ab7a5e44`) a **raccordé le retrait de plateau à sa place native** dans
`AttackDamageOperation._kill_unit_operation` : `IOperationProcessor` slot 6 =
`RemoveUnit(killed, removeEffects: 0, keepActive: 1)`, appelé par
`IdunBattle.Operations.KillUnitOperation$$Execute` entre ses deux premiers `RemoveEffects`. Le
port est **juste** — le décompilé le porte, la chaîne est citée dans l'en-tête de
`engine/runner/operations/remove_unit.py`.

Ce qui a cassé, c'est le **montage** : un double dont la surface est « le minimum d'aujourd'hui »
se périme dès qu'un étage est raccordé en amont. Le test ne disait donc plus rien du port ; il
accusait sa propre maquette.

### Le remède

1. **Les doubles disparaissent** : `Entity` et `State` réels (`engine/runner/state.py`). Ils
   suivent le moteur par construction, donc cette classe de faute est fermée, pas déplacée.
2. **La liste des vecteurs neutralisés est DÉRIVÉE**, plus écrite : elle était figée à cinq noms,
   et `RemoveUnitOperation` en publie un **sixième** — `On(0x25 = UnitRemoved)`, via
   `move_death.unit_removed_triggers`. On neutralise tout ce que `move_death` expose sous
   `*_triggers`, **et** on vérifie que les six connus y sont — sinon un renommage viderait le
   montage en silence.
3. **`RemoveUnitOperation` n'est PAS neutralisé** : il est sur le chemin natif de la mort. Le
   neutraliser rendrait le fichier vert sur un câblage qui n'existe plus.
4. Le `DECLENCHEUR` déclare enfin les **deux foyers traversés** (`remove_unit.py`, `state.py`) —
   c'est exactement par là que le fichier est devenu rouge sans que son verdict ait bougé.

### Contre-épreuves — le cran mord, et pour la bonne raison

| mutation posée dans `engine/runner/operations/damage.py` | effet attendu | mesuré |
|---|---|---|
| écriture du marqueur victime (`UnitComponent+0x178`) neutralisée | les 2 tests du couple rougissent | **2 failed / 9 passed** |
| `in_melee` forcé à `None` à l'appel de `register_defeated_unit` | le test des DEUX faces rougit | **1 failed / 10 passed** |
| raccord `RemoveUnitOperation.execute` retiré | le fichier reste VERT (il ne teste pas le retrait) | **11 passed** |

La troisième ligne est celle qui compte le plus : elle établit que la réparation n'a **pas** créé
de dépendance parasite au raccord. Le retrait reste gardé par ses propres crans
(`test_1088_remove_on_death_step_offline.py`, famille `#10015`).

---

## 2. `936` — un NOM de `functions.tsv` ne désigne pas une ADRESSE

### Le rouge, lu

    AssertionError: AUCUN appel a `DSLTriggers$$On` reconnu dans `$$CreateTrigger`

Le test se protégeait lui-même : il refuse de conclure « `UnitDeath` n'est pas abonné » quand il
n'a rien vu du tout. Sans cette garde d'anti-vacuité, il serait resté **vert sur zéro**.

### La vérité gardée est INTACTE — vérifiée au décompilé

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WrathfulDevotionAbility$$CreateTrigger`, relu
verbatim sur `t6dpr4k06g` :

    On(0x36) & get_OwnerIsActor & IsDefeatedByMeleeAttack(...)
      |  On(0x3b) & get_OwnerIsTarget & CurrentAbilityIs(...)

Exactement `{UnitDefeated, UnitBecameTargetable}`, et **pas** `UnitDeath`. Le verdict DEAD CODE de
la troisième branche du `switch` de `$$CreateBehaviour` tient.

### La cause : l'INVENTAIRE

`_va_of` rendait la **première** ligne de `functions.tsv` portant le nom cherché.
`IdunBattleLogic.Entities.DSLTriggers$$On` en a **TROIS** :

| rang (adresse croissante) | signature lue au décompilé |
|---|---|
| 1 | `On(triggerType, ownerNeedsToBeAlive)` — `op_BitwiseOr` sur `<this+0x20>` |
| 2 | `On(triggerType, ownerNeedsToBeAlive)` — `<this+0x20>` si alive, `<this+0x70>` sinon |
| 3 | `On(params int[] triggers)` — boucle de `op_BitwiseOr` |

`$$CreateTrigger` appelle la **deuxième**. Le reconnaisseur cherchait la première, donc voyait
zéro appel — pour deux immédiats parfaitement présents dans les octets (`BA 36 00 00 00 ; E8 …`
et `BA 3B 00 00 00 ; E8 …`, chacun collé à son `call`).

⚠ **Le motif de décodage n'a jamais changé.** Ce qui a changé entre `rnca9r7q6c` et
`t6dpr4k06g`, c'est la surcharge que le codegen appelle — les trois `$$On` sont présentes **à
l'identique dans les deux tables** (mêmes tailles, mêmes voisins, même rang), donc le test passait
sur l'ancien build parce que le codegen visait alors la première.

### L'ampleur, MESURÉE — ce n'est pas un accident local

Sur `t6dpr4k06g` : `ghidra/functions.tsv` = **154 182 lignes pour 145 703 noms distincts**, dont
**5 341 noms (3,7 %) portent PLUSIEURS VA**. Chiffres **identiques** sur `rnca9r7q6c`. C'est le
pendant, sur l'axe des adresses, de ce que le `CLAUDE.md` dit déjà de l'axe inverse
(« l'ABSENCE d'une méthode dans les tables ne prouve RIEN ») : ici c'est la **présence** qui ne
prouve pas l'unicité.

### Le remède

* `_vas_of(build, symbole)` rend **toutes** les VA ;
* `_va_of` reste pour les symboles dont l'unicité est attendue, mais **ROUGIT sur un nom partagé**
  au lieu d'en choisir un — une adresse prise au hasard dans une famille est une mesure fabriquée ;
* `_on_immediates` prend un **ensemble** de cibles. La 3ᵉ surcharge (`params int[]`) ne peut pas
  produire de faux positif : elle reçoit un pointeur, jamais un `mov edx, imm32`.

### Le cran SOUS le cran

`test_le_decodeur_d_appels_On_n_est_PAS_aveugle` — sans DLL, sur des octets **fabriqués** :

1. deux immédiats visant des surcharges **différentes** sont rendus tous les deux ;
2. un `On(UnitDeath = 0)` fabriqué **EST VU** — sans quoi le verdict DEAD serait vacu ;
3. un `mov edx, imm32 ; call <autre chose>` est **ignoré** (pas de faux positif) ;
4. `_va_of` **refuse** le nom partagé, et `$$On` a bien `>= 2` VA dans ce build.

Le point 2 est le seul qui garde la conclusion : un décodeur aveugle et un natif qui n'abonne pas
`UnitDeath` rendent la **même** liste vide.

---

## 3. `920` — le grep de SOURCE ne mesure pas la PUBLICATION

### Le rouge, lu

    assert 'adjacent_summons_of' in '<source de AttackDamageOperation._crit_board>'

La clé **est** publiée. `#1042-r5` a remplacé les littéraux de `_crit_board` par des **alias
importés** (`_CTX_ADJACENT_SUMMONS_OF`), et le grep de source est tombé — sans que rien du port
ait bougé.

### La faute SYMÉTRIQUE est bien pire, et elle était armée

`_crit_board` **nomme quatre clés voisines dans ses commentaires**, précisément pour dire qu'il ne
les réutilise pas. Un grep de source passe donc sur une clé **dépubliée** dès qu'un commentaire la
mentionne. Mesuré, pas redouté :

> Contre-épreuve : `_CTX_ADJACENT_FRIENDLY_MECHANICAL_UNITS_OF` remplacé par un nom mort dans le
> dict rendu par `_crit_board` → la clé de `NetherRealmCasket` **n'est plus publiée**, et
> `tests/engine/test_908_nether_realm_casket_offline.py` restait **14 passed**.

`908` portait donc le même cran, **en faux vert**. Il est réparé ici même (il rougit sous cette
mutation : `1 failed / 13 passed`) — débordement assumé de trois lignes, sur un fichier hors de
tout territoire réservé, parce qu'un faux vert **démontré** ne se signale pas, il se ferme.

### Le remède

On interroge le **dict rendu** par `_crit_board(State(), None, None)`, ce qui est strictement plus
fort que le texte :

* la clé doit être **présente** ;
* sa valeur doit être **callable** — forme paresseuse par-porteur, parce que la boucle native
  écrase `AbilityEntities+0x18` à chaque itération ;
* **contre-épreuve du critère lui-même** : un nom absent doit **manquer**, sinon un conteneur
  permissif ferait passer n'importe quoi.

Le `State()` nu suffit : les compteurs sont des lambdas, rien n'est calculé à la construction.

---

## 4. Ce que cette tranche NE couvre PAS

* **Aucun fichier `engine/**` n'est modifié.** Les quatre fichiers touchés sont des tests. Les
  trois verdicts de port (`inMelee`, `WrathfulDevotion` DEAD, `MawClawsOfThyrax`) sont
  **confirmés**, pas révisés.
* **Rien n'est confronté LIVE** — les quatre fichiers sont offline par construction, et les deux
  confrontations live de ces familles existent déjà ailleurs (`#951-r3`
  `decisionView.units[].defeatedByMelee` ; bras `--ennemi` du probe `#920`).
* **Le gisement des homonymes n'est traité que sur `936`** : `_va_of` est **dupliqué** dans
  `test_929_savage_killer_offline.py` et `test_936r1_expiry_removal_offline.py`, tous deux verts
  aujourd'hui **par chance** (leurs symboles ont 1 VA sur ce build), pas par construction. Résidu
  `#10026-r1`.
  ⚠ Deux autres fichiers visent des symboles à **plusieurs** VA
  (`DSLSelectors$$CanAddUnit` = 3, `DSLSelectors$$FreeTilesOrAdjacentFreeTiles` = 2) mais leur
  helper `_symbols` rend **déjà une liste** — ils sont hors gisement, vérifié en les rejouant.
* **Le recensement complet des rouges de `master` n'est pas fait** : la liste reçue était
  explicitement tronquée (38 fichiers non-VERT annoncés).
