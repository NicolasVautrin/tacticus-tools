# case-224 item 1 — `CursedPlagueBellMovementAbility` : la face COMBAT du passif de Corrodius

Suite de **case-211**, qui avait porté la face PLAYBOOK de `CursedPlagueBell` (1071) et laissé la
face COMBAT entière au backlog (§5, dernier point). Cet item porte **une** des quatre pièces
listées là-bas : `CursedPlagueBellMovementAbility`. Les trois autres
(`CursedPlagueBell_ExtraMoveEffect`, `CursedPlagueBell_DangerZoneEffect`,
`CursedPlagueBellAttackAbility$$IsInContagionsOfNurgleRange`) restent hors périmètre.

Porteur : `deathBlightbringer` (Corrodius, Death Guard) — **POOL-HERO** rank 17, présent tel quel
dans `rl_duel.py build --list-pool`. `passiveAbilities = ["CursedPlagueBell"]`.

i2 : « Friendly Chaos units **starting their turn** within Corrodius' Contagion aura gain
**+1 Movement for this turn**. »

---

## 1. C'est une TRIGGERED ability — donc ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE`

`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellMovementAbility` est dans le
namespace `Abilities.Active.Loki`, mais `classes.tsv` du build donne son parent DIRECT :
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`, elle-même fille de `System.Object` — **pas**
de `AActiveAbility`. Même configuration que `DestroyerHiveAbility`, `FireOfAbsolution`,
`ControlEdict` (le placement était déjà documenté dans `triggers/loki/destroyer_hive.py`, qui cite
nommément `CursedPlagueBell`).

Conséquence directe sur les deux règles de non-régression du CLAUDE.md : elles portent sur
`ABILITY_CLASSES`, le registre des **actives**. Les deux données qu'elles exigent sont celles que
`AActiveAbility$$.ctor` reçoit — le `TargetingOptions` construit par
`IdunBattle.Core.Services.TargetingOptions$$.ctor` et le 3ᵉ argument `AbilityAttackType`.
`BaseTriggeredAbility$$Init(abilityConfigId, dsl, query, state, config, operationProcessor,
effectsDatabase, logger)` n'en prend **aucune**, et la classe n'a ni `.ctor` propre ni champ de
ciblage. L'ability entre donc dans `ABILITY_TRIGGERS` (clé = `passiveAbilities`), et les deux
garde-fous restent à zéro dette : `probe_181_targeting_gaps` = **94 / 94, 0 manquante** ;
`probe_120` étape 0 = « littéral de ctor manquant: aucun », `PROBE OK`.

---

## 2. Le décompilé

### 2.1 `CreateTrigger` — un corps PARTAGÉ, identifié par sa place dans le bloc de classe

    On(TurnStart_Other = 0x13 = 19, 1) & <DSLTriggers+0x28 = OwnerIsActor>

`methods.tsv` n'attribue à `CursedPlagueBellMovementAbility` que `CreateBehaviour` et
`GetTargetsSelector` : IL2CPP a **dédupliqué** le corps de son `CreateTrigger` avec celui de
`IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility$$CreateTrigger`, qui en est
le seul propriétaire dans les tables indexées par adresse. Deux éléments l'établissent — aucun
n'est un argument tiré de l'absence :

* le **bloc de classe est contigu** dans `ghidra/functions.tsv` :
  `CursedPlagueBellMovementAbility$$CreateBehaviour`, puis le corps attribué à
  `RelentlessMarchAbility$$CreateTrigger`, puis
  `CursedPlagueBellMovementAbility$$GetTargetsSelector` — exactement la place qu'occupe le
  `CreateTrigger` de CETTE classe dans SON bloc ;
* `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetTrigger` appelle le slot de vtable
  `+0x2d8` (`CreateTrigger`) et la base n'a **aucun corps propre** (abstraite) : la classe DOIT en
  avoir un.

`<DSLTriggers+0x28>` est le même slot que celui de
`IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateTrigger`
(`+0x28 & On(0x13,1) & IsDamaged(Owner)`), que le port nomme `OwnerIsActor` et qui est **prouvé
live** (#203 : la regen ne fire qu'au tour du propriétaire). Vecteur porté :
`turn_start_other_triggers` (`dispatch/turn.py`).

Il n'y a **aucun** gate supplémentaire — pas d'`AmountIsGreaterThanZero`, contrairement à
`DestroyerHive`. Un arbre de cibles vide est un no-op du behaviour, pas un refus du trigger.

### 2.2 `GetTargetsSelector(dsl, isDangerZone)`

    range   = DSLFormulas.ContagionsOfNurgleRange(unit = Owner,
                                                  unitSelectionType = 0 = Any,
                                                  isNextTurn = isDangerZone)
    targets = UnitsWithoutTrait(
                UnitsWithTrait(
                  SurroundingFriends(unit = Owner, range = range, unique = true,
                                     unitSelectionType = 3 = OnlyAliveAndTargetable),
                  trait = 0x7ea = UnitTrait.Chaos,     selectionType = 3),
                trait = 0x418 = UnitTrait.Stationary,  selectionType = 3)

`Owner` = `DSLSelectors+0x30`, le slot que `LivingMetalRepairAbility` passe à `IsDamaged` et que
`RelentlessMarchAbility` passe à `AdjacentUnits`/`Friends`.

`DSLSelectors$$SurroundingFriends(unit, range:IAmountFormula, unique, selType)` (l'overload à
4 paramètres, distingué des trois autres par la signature de `methods.tsv`) se déplie en

    Friends( of = unit,
             Units( SurroundingTiles(unit, includeCenter=1, range) - Tiles(unit), unique, selType ),
             selType )

— disque hex de rayon `range` autour de l'Owner, **centre EXCLU** par la soustraction
`- Tiles(unit)`, filtré ALLIÉS de l'Owner.

### 2.3 `CreateBehaviour(abilityState, triggerType)`

    AddEffect( effectType   = 0x431 = 1073 = EffectType.CursedPlagueBell_ExtraMove,
               abilityState = BaseTriggeredAbility.get_AbilityStateReference(this),
               targets      = <2.2 avec isDangerZone = false>,
               turns        = Nullable<int>(1) )

C'est l'overload `DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns:Nullable<Int32>)`
— la durée est **déjà en TOURS**, il n'y a pas de `TurnsFromRounds`, donc pas de
`ConvertRoundsToTurns`. Le behaviour ne lit pas `triggerType` (aucune branche, contrairement à
`RelentlessMarchAbility`).

### 2.4 `ContagionsOfNurgleRange` — la primitive d'aura

    DSLFormulas$$ContagionsOfNurgleRange(unit, unitSelectionType, isNextTurn)
      = new IdunBattle.Entities.Triggers.AuraEffectRangeFormula(
              effects, unit, effectType = 0x42f, unitSelectionType, isNextTurn)

    AuraEffectRangeFormula$$Calculate(entities) :
        unit = <sélecteur `unit`>.Select(entities)
        if (unit == null) return 0
        def = effectsDatabase.Get(0x42f)                    // IAuraEffect
        if (!UnitExtensions.HasTrait(unit, def.GetTrait())) return 0
        entities.<slot Owner> = unit                        // ré-ancrage
        return (isNextTurn ? def.GetNextTurnRange() : def.GetCurrentRange()).Calculate(entities)

L'implémentation `IAuraEffect` est
`IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect` :

| membre | corps lu |
|---|---|
| `$$GetTrait` | `return 0x7eb` (= `UnitTrait.ContagionsOfNurgle`, 2027) — littéral |
| `$$GetCurrentRange` | `GetRangeOnOwnerTurn( StatAmount(Owner, 0xc = TurnsStarted, part 0) )` |
| `$$GetNextTurnRange` | `GetRangeOnOwnerTurn( Sum(StatAmount(Owner, 0xc, 0), Direct(1)) )` |
| `$$GetRangeOnOwnerTurn(n)` | `ConditionalAmount( Not(AmountIsGreater(n, Direct(2))), Direct(1), ConditionalAmount( Not(AmountIsGreater(n, Direct(4))), Direct(2), Direct(3) ) )` |
| `$$CalculateRange(unit)` | `s = GetStat(unit, 0xc, Current) ; s > 2 ? (s > 4 ? 3 : 2) : 1` |

Les deux dernières lignes sont **le même barème**, écrit une fois en DSL et une fois en impératif.
Le port n'en garde qu'un foyer : `runner/abilities/deathguard.contagions_of_nurgle_range_for_turns`
(extrait de `contagions_of_nurgle_range`, value-preserving), que la voie impérative
(`SpawnPoxwalkers`, pose de l'aura) et le nouveau nœud DSL appellent tous deux.

⚠ **Qualification d'enum** : `0x42f` vaut 1071 dans deux enums qui interviennent tous deux ici —
`TriggeredAbilityType.CursedPlagueBell` (l'id du passif) et
`EffectType.ContagionsOfNurgle_ArmorReduction1` (celui que lit `ContagionsOfNurgleRange`). Le
littéral de la formule est l'**EffectType**.

---

## 3. Ce qui a été porté

| Fichier | Contenu |
|---|---|
| `engine/runner/operations/triggers/loki/cursed_plague_bell.py` (**neuf**) | nœud `ContagionsOfNurgleRange` (mirror `DSLFormulas$$ContagionsOfNurgleRange` / `AuraEffectRangeFormula$$Calculate`), `cursed_plague_bell_targets_selector` (mirror `GetTargetsSelector`), `cursed_plague_bell_movement_tree` (mirror `CreateBehaviour`), classe `CursedPlagueBellMovementAbility` |
| `engine/runner/operations/triggers/dispatch/registry.py` | `ABILITY_TRIGGERS["CursedPlagueBell"] = [CursedPlagueBellMovementAbility]` |
| `engine/runner/abilities/deathguard.py` | extraction de `contagions_of_nurgle_range_for_turns` (le barème `GetRangeOnOwnerTurn`), pour que la voie DSL et la voie impérative partagent un seul foyer |
| `scripts/python/probe_224_cursed_plague_bell.py` (**neuf**) | montage + confrontation live-vs-port + contrefactuels par gate |
| `tests/engine/runner/test_cursed_plague_bell_movement_live.py` (**neuf**) | 7 gardes (enregistrement, agreement, seuils de rayon, scoping, 3 contrefactuels) |

L'arbre est composé de nœuds **existants** (`SurroundingFriends`, `UnitsWithTrait`,
`UnitsWithoutTrait`, feuille `AddEffect`) : conformément à la doctrine #149, seuls les prédicats du
`CreateTrigger` (`On` + `OwnerIsActor`) sont collapsés impérativement dans `matches` — le ciblage
émerge des nœuds, il n'est pas recâblé.

---

## 4. Validation live

Montage `probe_224_cursed_plague_bell` — **toutes les positions sont drivées** (`applyAction move`
téléporte, aucune contrainte de portée), sur un board à **≥ 6 spawns joueur** et une tuile de
porteur à **6 voisins** (le spawn de Corrodius sur `MC1_67` est en coin, 3 voisins : le voisinage y
serait silencieusement sous-exercé). Six cas discriminants sur un seul plateau :

| unité | alliance | distance au porteur | attendu |
|---|---|---|---|
| `deathPutrifier` | Chaos, allié | 1 | reçoit 1073 |
| `worldJakhal` | Chaos, allié | 2 | rien tant que rayon = 1, puis reçoit |
| `thousTzaangor` | Chaos, allié | 3 | rien tant que rayon < 3, puis reçoit |
| `necroWarden` | **Xenos**, allié | 1 | rien (gate `UnitsWithTrait(Chaos)`) |
| `astraBullgryn` | **Imperial**, allié | 1 | rien (gate `UnitsWithTrait(Chaos)`) |
| `blackTerminator` | Chaos, **ennemi** | 1 | rien (gate `SurroundingFriends`) |
| Corrodius lui-même | — | 0 | rien (centre exclu, `- Tiles(unit)`) |

Le protocole, par tour du porteur : capture au tour ADVERSE (`decisionView allAbilities` +
`observeBattle` + `combatSnapshot` + `boardGraph`), puis `endturn` LIVE (le `StartTurnOperation`
natif émet `On(0x13)` et pose), relecture de l'ensemble des porteurs de 1073 ; côté port,
`load_state(capture)` + `_bump_turns_started(P)` (mirror de l'ordre natif : l'incrément précède
l'émission des cinq events) + `turn_start_other_triggers(P)`.

### 4.1 Agreement — 11 tours, 0 désaccord

`C1_75` / seed 777, 6 tours :

| tour | `TurnsStarted` | rayon | porteurs de 1073 — natif **et** port | `remaining` |
|---|---|---|---|---|
| 1 | 2 | 1 | `deathPutrifier` | 1 |
| 2 | 3 | **2** | `deathPutrifier`, **`worldJakhal`** | 1 |
| 3 | 4 | 2 | `deathPutrifier`, `worldJakhal` | 1 |
| 4 | 5 | **3** | `deathPutrifier`, `worldJakhal`, **`thousTzaangor`** | 1 |
| 5 | 6 | 3 | idem | 1 |
| 6 | 7 | 3 | idem | 1 |

`LHE_temp_01` / seed 31337, 5 tours : même table, mêmes bascules. **11 tours confrontés,
0 désaccord**, `remaining` compris.

Les deux bascules (tour 2 et tour 4) sont le point du cas : le rayon d'aura n'est pas une constante
mais une fonction du `TurnsStarted` du porteur, et les **deux seuils** de `GetRangeOnOwnerTurn`
(2 et 4) sont franchis dans la même mesure. Aucun rayon fixe ne produit cette table.

Le `remaining = 1` mesuré côté natif est le discriminant du `turns = Nullable<int>(1)` : un port qui
aurait lu un `TurnsFromRounds(1)` rendrait 2 (facteur = nombre de joueurs non-Environment, cf. la
mesure `Pinned` de `AddEffectOperation`), et un port sans durée rendrait `remaining = 0`
(permanent), puisque `DefaultAmountOfRounds(1073)` est absent de la table.

### 4.2 Contrefactuels — trois gates sur quatre mordent

Chaque gate retiré à tour de rôle, mesure rejouée **sur les mêmes captures** (`--mutate`) :

| gate neutralisé | effet mesuré (`C1_75`/777, 6 tours) |
|---|---|
| `UnitsWithTrait(Chaos)` | **6/6 tours rouges** — `necroWarden` (Xenos) et `astraBullgryn` (Imperial) entrent dans l'ensemble |
| `SurroundingFriends` → `SurroundingEnemies` | **6/6 tours rouges** — seul `blackTerminator` (ennemi Chaos adjacent) reste |
| rayon figé à 1 | **5/6 tours rouges** — exactement les tours où le rayon réel vaut 2 ou 3 |
| `UnitsWithoutTrait(Stationary)` | **0/6** — inerte, cf. §5 |

### 4.3 Non-régression

Tests rejoués, tous verts : `test_cursed_plague_bell_movement_live.py` (7), `test_destroyer_hive_live.py`
+ `test_necrons_lot1_live.py` (9 — le vecteur `On(0x13)` est partagé avec `LivingMetalRepair`),
`test_contagions_of_nurgle_new_unit_live.py` + `test_deathguard_targeting_live.py` (9 — l'aura
Contagion et le barème de rayon refactoré), `test_summon_consumers_live.py -k "contagion or nurgle
or pox or range"` (8 — le seul consommateur de `contagions_of_nurgle_range`),
`test_ability_registry_ratchet.py` (8), `test_tile_term_unit_gated_playbooks_live.py -k
deathBlightbringer` (10 — le playbook de case-211). Garde-fous : `probe_181_targeting_gaps`
(94/94, 0 manquante) et `probe_120` (PROBE OK).

---

## 5. Ce que ce cas n'établit PAS

* **Le gate `UnitsWithoutTrait(Stationary)` est INERTE, et c'est mesuré** : le trait `1048` n'est
  porté par aucune des 683 unités du gameconfig, ni par aucune entité du `combatSnapshot` —
  Machines of War comprises, dont les traits runtime se réduisent à `[1049 MachineOfWar, 2026
  Chaos]` (scan du build `rnca9r7q6c`, canal `combatSnapshot.units[].traits`). Le gate est porté
  parce que le décompilé le porte, pas parce qu'un montage le distingue.
* **Le gate `HasTrait(unit, IAuraEffect.GetTrait())` de `AuraEffectRangeFormula` n'est jamais faux
  en pratique** : les quatre porteurs de `CursedPlagueBell` du gameconfig (`deathBlightbringer` +
  trois npc) portent tous `ContagionsOfNurgle`. Le gate est porté (le décompilé le lit avant tout
  calcul de rayon, et il rend `0` — donc un disque vide) mais aucun montage ne le distingue du
  chemin nominal. Il deviendra observable si un poseur de trait, ou un second `IAuraEffect`, entre
  au port.
* **`unitSelectionType = 3 = OnlyAliveAndTargetable`** : le port n'honore que le volet ALIVE
  (`_within` filtre les cadavres). Le volet TARGETABLE n'est matérialisé nulle part côté port — une
  unité vivante mais non ciblable (deep-strike en cours d'atterrissage) serait comptée. Résidu
  commun à tous les sélecteurs d'occupation du port.
* **La branche `isNextTurn = true`** de `GetTargetsSelector` (celle que consomme la DANGER ZONE)
  n'est pas portée : aucun appelant ici, `CreateBehaviour` passe `false`. Le nœud LÈVE si on la
  demande, au lieu de rendre un rayon faux en silence. C'est le prérequis de l'item
  `CursedPlagueBell_DangerZoneEffect`.
* **L'EFFET posé** (`CursedPlagueBell_ExtraMoveEffect$$AddStatModifier`, le +1 Movement effectif)
  n'est pas porté : cet item porte la POSE, dont l'observable confronté est la présence et la durée
  de l'instance 1073 sur les bonnes unités.
* **Les deux autres classes du passif** — `CursedPlagueBellAttackAbility` (dégât Psychic aux
  psykers ennemis dans l'aura, avec `$$IsInContagionsOfNurgleRange`) et
  `CursedPlagueBellDangerZoneAbility` — restent hors périmètre.
* **Un trait `Chaos` ACCORDÉ en bataille** (`AddTraitOperation`) sur un allié initialement
  non-Chaos : non exercé (aucun poseur porté ne l'accorde), même limite que case-211 §5.

---

## 6. Reproduire

```bash
cd scripts/python
python probe_224_cursed_plague_bell.py --seed 777   --board C1_75       --turns 6 --mutate
python probe_224_cursed_plague_bell.py --seed 31337 --board LHE_temp_01 --turns 5
python -m pytest tests/engine/runner/test_cursed_plague_bell_movement_live.py -q
```

⚠ Le montage a besoin d'un board à **≥ 6 spawns joueur** (six unités) : `MC1_67` n'en a que cinq et
le build REFUSE. Les boards éligibles se re-dérivent (jamais une liste figée) :

```python
# depuis scripts/python
import rl_collect_batch as R
from rl_collect_batch import _load_board_dump, _spawn_points_by_twpi
ids = {p.stem for k in ("pvp", "syncPvp", "global")
       for p in ((R.BOARDS_DIR / k).glob("*.json") if (R.BOARDS_DIR / k).exists() else [])}
for i in sorted(ids):
    d = _load_board_dump(i)                       # MEME resolveur que `rl_duel build --board`
    sp = _spawn_points_by_twpi({"Board": d["board"], "SpawnPointSetIndex": d.get("spawnPointsSet", 0)})
    if len(sp.get(0) or []) >= 6:
        print(i, d.get("kind"), len(sp[0]), len(sp.get(1) or []))
```

Passer par `_load_board_dump` et non par un scan direct des répertoires : un même id peut exister
dans deux pools avec des `SpawnPointSets` différents (`MC1_64` a 7 spawns en `global` et 5 en
`pvp` — c'est le `pvp` que le build résout, et le build échoue).
