# #545 — un `UnitFlagsComponent` VIDE est un ÉTAT, pas une absence (et #508-r1, le compteur d'attaques)

Deux substrats manquants, même forme : le port n'écrivait pas ce que le natif tient pour acquis.

## 1. Le fait natif, et ce que le port en faisait

`IdunBattle.Entities.Components.UnitFlagsComponent$$.ctor` construit un `OrderedSet` **VIDE**, et
`IdunBattle.Entities.Factories.UnitFactory` le monte sur **chaque** unité.
`IdunBattle.Entities.Behaviours.AddFlagBehaviour$$Execute` (et son jumeau `RemoveFlag`) résout le
composant **sans garde** et **LÈVE** s'il est absent — il ne l'ignore pas. Natif, « unité sans
`UnitFlagsComponent` » n'existe pas.

`snapshot._load_unit_flags` ne le matérialisait que sur une liste **NON VIDE** (`or not flags:
continue`). Toute unité sans aucun flag n'en avait donc pas, et chaque site qui fait
`if fc is None: return` avant de POSER un flag devenait un **no-op silencieux**. Mesure #498-r4-r1 :
après le cast de `1152`, le natif rend `unitFlags = [1, 2, 3, 4, 25]` et le port ne posait RIEN —
l'écart que cette tranche-là visait était **inobservable**, masqué par celui-ci.

## 2. Le rayon de souffle, MESURÉ avant l'édition

`probe_545_unit_flags_component_vide.py` — recensement **AST** de tous les sites
`get_component(UnitFlagsComponent)` d'`engine/**`, classés par ce que le site fait du cas `None`,
puis **contrefactuel exécutable** (chaque fonction rejouée sans composant puis avec un composant
vide, sur le même état).

| classe | compte | ce qu'un composant VIDE y change |
|---|---|---|
| `CREE` | 13 | rien (le site créait déjà le composant absent) |
| `NEUTRE` | 31 | rien (`fl is not None and fl.has(X)` — indiscernable d'un set vide) |
| `DISTINGUANT` | **5** | la branche change |
| **total** | **49** | somme = partition exhaustive |

Les **5** qui distinguent : `abilities/behaviours/movement.py::ResetMovement.execute`, et **quatre**
dans `operations/turnflow.py` (`MarkUnitAsNoActionAvailableOperation.execute`,
`VerifyUnitsTurnFinishedOperation.verify_unit_turn_ended`, `has_tiles_to_move_to`,
`has_action_available`). Toutes s'**abstenaient** sur composant absent ; elles deviennent actives —
ce qui **est** le comportement natif (`TryGetComponent` sur une unité qui en porte toujours un, ou
`GetComponent` qui lève). Le contrefactuel exécutable mord sur `has_tiles_to_move_to` (`None` →
`True`).

Deux pièges du probe, trouvés en le construisant :
* le classement AST doit voir les **deux** écritures de création — `add_component(UnitFlagsComponent())`
  **et** `fl = UnitFlagsComponent()` puis `add_component(fl)` ; n'en voir qu'une classait
  `summon_ai._flags` en `DISTINGUANT` ;
* l'empreinte du contrefactuel doit hacher la **valeur**, pas la représentation : `entities_from_state`
  rendait une divergence **fausse**, uniquement par les adresses mémoire de ses closures.

## 3. Ce que la tranche livre

* `snapshot._load_unit_flags` matérialise le composant sur **toute ligne MESURÉE**, liste vide
  comprise, en **tri-état** : `unitFlags` absent ou `null` = canal non mesuré → on ne touche à rien ;
  le compte des lignes vides est rendu (`state.unit_flags_seed["vides"]`).
* `operations/revive.py` ne **saute** plus sa rafale de flags quand le composant manque (`Add(0x14 =
  Revived)` n'était jamais posé) — c'était le dernier écrivain de la même forme, le recensement AST
  le confirme.
* `tests/engine/runner/test_545_unit_flags_component_vide_offline.py` — 12 tests.

## 4. #508-r1 — le compteur d'attaques ÉMISES, dans le même commit

`IdunBattle.Entities.Formulas.AmountOfAttacksMadeThisTurnFormula$$Calculate` lit
`ActorStatisticsComponent+0x24` quand son `Nullable<rangeType>` est **vide** (`+0x2c` si `Melee = 1`,
`+0x28` si `Ranged = 2`). Les deux foyers du port existaient déjà et étaient appelés au bon instant :

* `register_attack_made` — `this[0x24] += 1`, à **chaque** attaque (contraste `+0x30`, qui n'avance
  qu'au **premier** coup du tour) ;
* `reset_units_attacked_this_turn` — **son nom ne le dit pas, l'assembleur si** :
  `*(long long*)(this + 0x24) = 0` (une écriture 64 bits qui couvre `+0x24` **et** `+0x28`) puis
  `this[0x2c] = 0`. Les **deux** `ActorStatisticsComponent$$ResetThisTurn` n'y touchent pas — le
  premier écrit dans son paramètre `data`, le second roule `+0xf0/+0x78/+0xe4/+0x58/+0xa0` et les
  champs des sous-structures de son dictionnaire.

`LeadingTheCharge` lit désormais le compteur (`SetCache` avant / `AmountIsGreater` après) au lieu de
son collapse « une émission d'attaque de plus ». **Aucun changement observable sur 1204** — le
collapse était structurellement équivalent sur cet arbre, et les 12 tests de #508 restent verts.

**Ce qui a tranché le rayon** : le nœud `IdunBattleLogic.Entities.DSLFormulas$$TimesAttackMadeThisTurn`
a **quatre** call-sites natifs pour **trois** abilities — `LeadingTheChargeAbility$$ExecuteBehaviour`
(×2), `IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger` et `LegacyOfCombatAbility$$CreateTrigger`,
ces deux dernières **non portées** faute de ce substrat. L'écrivain est **unique**
(`RegisterAttackOperation$$Execute`).

## 5. Ce qui n'est PAS couvert

* **`+0x28`/`+0x2c`** — résidu `#508-r2`. Le `rangeType` est un argument propagé depuis l'enqueue du
  slot `IOperationProcessor` **74** (`RegisterAttack`, arité 4), dont le call-site n'est pas localisé.
  Le deviner écrirait une valeur fausse dans deux compteurs, ce qui est pire que leur absence.
* **Le seed live de `+0x24`** — résidu `#545-r1`. `rpc-snapshot.ts` publie `totalTurnsWithAttacksMade`
  (`+0x30`), pas `+0x24` : un état rechargé repart de `0`. Inerte pour `LeadingTheCharge`, qui compare
  le compteur **à lui-même** dans le même rejeu ; bloquant pour tout lecteur de la valeur absolue.
  Poser le champ exige une **réinjection**.
* **`ResetMovement.execute`** garde son `continue` sur composant absent : en régime mesuré le
  composant existe désormais toujours, donc l'événement `ResetMovement` est émis comme chez le natif ;
  hors régime mesuré, l'abstention reste (elle ne pose ni ne retire rien, seul l'événement diffère).
* Le composant vide n'est **pas** confronté live : la mesure native qui l'établit est celle de
  #498-r4-r1 (`unitFlags = [1, 2, 3, 4, 25]` sur une unité que le port laissait sans composant).
