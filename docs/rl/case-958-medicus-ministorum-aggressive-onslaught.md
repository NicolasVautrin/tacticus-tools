# #958 — `MedicusMinistorum` (1069) et `AggressiveOnslaught` (1248), les deux derniers passifs de leur kit

Build `rnca9r7q6c`. Les deux items sont **PORTÉS et CONFRONTÉS LIVE**. Ce document garde ce que le
décompilé dit, les trois pièges que la lecture a évités, et ce qui reste **non couvert**.

## 1. Recensement — par le bloc `methodPointers`, jamais par grep de nom

Colonne « classe déclarante » de `data/symbols/<build>/frida/methods.tsv`. **Zéro homonyme égaré**
sur les deux noms (aucune méthode dont le nom cite l'ability mais dont la classe est autre).

| classe native | base (`classes.tsv`) | corps propres |
|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Active.Loki.MedicusMinistorumAbility` | `BaseTriggeredAbility` | 2 |
| `IdunBattle.AI.Playbook.Loki.MedicusMinistorumPlaybook` | `AdjacentToOwnerNonOwnerPlaybook<...>` | 2 |
| `...Triggered.Loki.AggressiveOnslaught_PrepareAbility` | `BaseTriggeredAbility` | 3 |
| `...Triggered.Loki.AggressiveOnslaught_SummonAbility` | `BaseTriggeredAbility` | 4 |
| `...Triggered.Loki.AggressiveOnslaught_UnsummonAbility` | `BaseTriggeredAbility` | 2 |
| `IdunBattle.View.AbilityConfigs.Loki.AggressiveOnslaughtVisuals` (+6 générées) | couche VUE | hors périmètre |

`BaseTriggeredAbility` expose **23** corps ; aucune des quatre classes de logique n'en surcharge
d'autres. Le build ne porte **qu'un seul** membre `TriggeredAbilityType` par nom (`enums.tsv`) : les
trois `AggressiveOnslaught_*` partagent donc l'id **1248**, forme déjà vue (`LetTheGalaxyBurn`).

⚠ Le namespace de `MedicusMinistorumAbility` dit `...Abilities.**Active**.Loki` alors que sa base
est `BaseTriggeredAbility`. **La base se lit dans `classes.tsv`**, jamais dans le namespace.

### L'événement de chaque trigger a-t-il un émetteur porté ? — OUI, les quatre

`PreAttack` (5) → `dispatch/attack.py::pre_attack_triggers` · `Attack` (9) → `dispatch/attack.py` ·
`UnitAbility` (0xb) → `dispatch/ability.py` · `TurnStart_EffectActivation` (0x12) →
`dispatch/turn.py`. **Aucun étage amont à construire** — c'est ce qui a rendu la tranche courte.

## 2. Les trois pièges que la lecture a évités

### (a) `CurrentDamage` lit `totalDamage`, et l'interpolation rendait `initialDamage`

`IdunBattle.Entities.Formulas.CurrentDamageFormula$$Calculate` = `Nullable<int>.GetValueOrDefault(
entities + 0xe8)`. Les ancres voisines **mesurées** (`wasCrit@0xf8`, `wasBlock@0xfa`,
`blockedHits@0xfc`, `hitIndex@0x108`, `movementSteps@0x11c`) sont espacées comme des champs
séquentiels — l'extrapolation donnait `healthDamage@0xe0 / initialDamage@0xe8 / totalDamage@0xf0`.
`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` (33 paramètres, tous **nommés** dans
`methods.tsv`) écrit en réalité :

    *(this + 0xd8) = initialDamage;   *(this + 0xe0) = healthDamage;
    *(this + 0xe8) = totalDamage;     *(this + 0xf0) = individualHitDamage;

L'ordre **mémoire** n'est pas l'ordre de **déclaration**, et les trois bools sont regroupés
(`wasCrit@0xf8 / hasUsedAttackDamage@0xf9 / wasBlock@0xfa`). Seule la lecture du ctor tranche.

### (b) `First` : `PickFirstN`, pas `PickAtIndex` — tranché par la signature

`probe_951_call_targets.py` rend `DSLSelectors$$First(entities, amount: IAmountFormula,
ignoreForcedTargets: bool)` = **les N premiers**. Le nœud `First(source, index)` du port est
`PickAtIndexSelector`, une classe **distincte**. Le confondre aurait spawné **1** intercessor au
lieu de 2 — et le live rend bien **2**, ce qui sépare les deux lectures.

### (c) `Children` ≠ `ChildrenOf` — un no-op qui ne lève rien

`IdunBattle.Entities.Selectors.ChildrenSelector$$Select` =
`GetChildrenUnits(<parentSelector>.SelectSingle(entities), state)` : les enfants **relus dans
l'état**. Le port a **deux** représentations : `Children` (l'accumulateur `ctx.children` du cast
courant, correct pour un on-appearance) et `ChildrenOf` (l'état, par `parentId`).
`AggressiveOnslaught_UnsummonAbility` court **un tour après** le spawn : câblé sur `Children`, il ne
retirerait **jamais** un summon, sans erreur ni trace. Le live le confirme — les deux summons
disparaissent bien au tour suivant.

⚠ Au passage : la docstring de `Children` attribue le nœud à `AllAliveMachinesSelector` — **mislabel
ICF**. Le build porte `ChildrenSelector$$Select`, et il n'existe **aucun** filtre `AllAlive` natif ;
le seul filtre est « est une unité ».

## 3. Ce que le tooltip promet et que l'arbre ne contient PAS

i2 de 1069 : « Any friendly adjacent **non-mechanical** unit that takes Damage regenerates
{hpToHeal} Health afterwards, **unless it is defeated**. »

Le sélecteur de cible est `Target@<DSLSelectors+0x60>` **nu** — contraste avec son voisin de forme
`SanguinaryPriestAbility$$GetTargets`, qui soustrait explicitement `MechanicalUnits`. Les deux
gardes vivent **sous la feuille**, dans `AttackQuery$$EntityCanBeHealed` (déjà porté) :
`IsMachine` → refus ; `IsDamagedUnit` → « unless defeated » / plein ; `IsAffectedByHealType(., 0 =
NonMechanical)` → « non-mechanical ». Recopier le filtre du voisin l'aurait **compté deux fois**, et
rendu **plus strict** que le natif (`IsAffectedByHealType` laisse passer une unité mécanique portant
`AffectedByHealAndRepair` ; la soustraction `MechanicalUnits` non).

## 4. Validation live — `probe_958_passifs_kit.py`

Runner `rl_duel build --board MC1_67`, géométrie **calculée puis assertionnée**, régime fabriqué
**au seed** (`--unit-stat`), attaquant **piloté** (`attach --team 2`) et jamais l'IA — mesuré :
laissée à elle-même, l'IA visait Isabella au lieu de l'allié, et le régime n'était jamais atteint.

**A. MedicusMinistorum** — Isabella (2,2), allié blessé 15000/30000 (3,2), frappeur (4,2).
Isabella est **hors de portée** du frappeur : un soin observé ne peut donc venir que du passif.

    natif : 4 coups sur l'allie, total 8176 (15000 -> 6824)
    natif : [Ability_Power e=77 <MedicusMinistorum>] HealInfo Amount=1197 Caster_Id=77  -> 8021

* **UN SEUL** soin pour **4** coups ⇒ `On(9 = Attack)` est émis une fois en **sortie d'attaque**,
  pas par coup. C'est ce que le port implémente.
* `Caster_Id=77` = Isabella ⇒ `healer = Owner@<DSLSelectors+0x30>` confirmé.
* `UnitStats_WasWoundedBeforeHeal=1` ⇒ le gate `IsDamagedUnit` sous la feuille est bien traversé.
* **Montant** : le probe balaie la table `hpToHeal` du mirror et demande quels couples
  `(niveau, multiplicateur)` rendent 1197 → **`[(50, 180), (64, 140)]`**. `(50, 180)` est exactement
  le régime normalisé du harnais, **lu** dans la cascade du volet B
  (`UnitStats_TriggeredAbility_Level=50 ..._VariableMultiplierPercentage=180`). C'est une mesure
  d'**identifiabilité**, plus forte qu'une égalité sur un régime posé d'avance : si la table du port
  était fausse, **aucun** couple ne tomberait sur la valeur native.
* **Test négatif obtenu en cours de route** : avec un encaisseur à 1500 PV tué par un coup de
  1500, **aucun** soin — conforme au `selectionType = 3` du trigger et à `IsDamagedUnit`.

**B. AggressiveOnslaught** — Mataneo (2,2) part **hors contact** et arrive au contact (5,1) : c'est
une CHARGE, pas un simple déplacement (`IsCharging` ≠ `has_moved`).

    natif : 2 AddUnit Unit_IsSummoned=1 Unit_Parent_Id=77   (tuiles 67 et 49)
    natif : 2 [Ability_Power e=77 <AggressiveOnslaught>]    (Prepare PUIS Summon)
    natif : ChangeAbility e=99 ... Level=50 VariableMultiplierPercentage=180
    tour suivant : 0/2 summon(s) encore presents

* **2 summons** = `nrOfSummons` ⇒ la surcharge `PickFirstN` est la bonne (`PickAtIndex` rendrait 1).
* **2 events** `Ability_Power` ⇒ les **deux** classes fire ; le `_PrepareAbility` n'est pas du
  code mort.
* `Level=50 / VariableMultiplierPercentage=180` sur le summon ⇒ le paramètre `ability_state=` que le
  port passe à la feuille `Spawn` est le bon (sans lui, la passive du summon lirait l'index 0).
* Unsummon au tour suivant ⇒ `ChildrenOf` (état) et non `Children` (accumulateur).

## 5. NON COUVERT — avec la raison mesurée

* **`UseNormalAttackIfAble` du summon (l'attaque immédiate)** — **NON CONFIRMÉ live**. Dans les deux
  régimes joués, aucun `Attacker_Id=99/104` n'apparaît : au premier essai la cible mourait du coup de
  Mataneo (« IfAble » sans cible), au second elle survivait mais les summons n'ont pas attaqué
  (tuiles de spawn 67/49). Le sous-behaviour **est** porté (motif identique à
  `SendInTheNextWaveAbility$$ExecuteBehaviour`, `caster = ActiveTarget@<+0x68>`), mais son
  déclenchement n'est pas attesté par cette tranche. Résidu à ouvrir si un régime le rend décisif.
* **Le gate `AmountIsGreaterThanZero(CurrentDamage)` lit `health_damage`, pas `totalDamage`** — le
  `TriggerEvent` du port ne thread pas `totalDamage`. Divergence **restrictive**, bornée aux cibles à
  bouclier (`total > 0`, `health == 0` ⇒ le natif soigne, le port non). Résidu **`#958-r1`**.
* **`ChildrenOf` du port applique `_units_of` (tous les parents) là où le natif fait `SelectSingle`
  (UNE entité)** — écart inerte sur `Owner()`, qui est un singleton à tous les call-sites portés.
  Non modifié : foyer partagé, aucun call-site ne passe un multi-sélecteur.
* **La face MOVE non-owner** du playbook (`TriggeredAbilitiesNonOwner`, config séparée) reste non
  portée, comme pour toute la famille `AdjacentToOwnerNonOwnerPlaybook`.
