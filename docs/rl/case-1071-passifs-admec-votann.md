# #1071 — `RepairEnthusiast` et `VengeanceForTheOmnissiah` : deux `S?=1 N=1`, deux verdicts opposés

Les deux étaient `GAP-ABSENT` dans `docs/rl/passive-ability-coverage.md`, porteurs `S?=1 N=1`
(un summon indéterminé, un npc), sans symbole natif rendu par l'audit. Ils n'ont **pas** la même
issue, et la différence n'est ni le porteur ni la faction — c'est l'existence d'un **étage
consommateur** côté port.

| item | ordinal | porteurs | verdict |
|---|---|---|---|
| `VengeanceForTheOmnissiah` | `TriggeredAbilityType` 0x512 = **1298** | `admecSmnTechpriest` (summon) + `admecNpc2Techpriest` (npc) | **PORTÉ** — faces COMBAT *et* DÉCISION, ACCORD live |
| `RepairEnthusiast` | `TriggeredAbilityType` 0x5ea = **1514** | `votanSmnEcog` (summon) + `votanNpc1Ecog` (npc) | **NON PORTÉ — étage manquant** (résidu #1071-r1) |

⚠ **Le brief les annonçait tous deux AdMech ; `RepairEnthusiast` est VOTANN** (E-COG, Leagues of
Votann). La faction n'a joué aucun rôle dans les deux verdicts, mais l'erreur aurait pu faire
chercher le porteur au mauvais endroit.

---

## 1. Le porteur : les deux summons ont un invocateur, et le jumeau npc est la voie

Contrairement aux deux cas de #1052 (`thousSmnRubricMarine`, invoqué par une ability
d'**environnement** de live-event ; `templInitiatePyreblaster`, **sans aucun** invocateur), les
deux summons d'ici se trouvent par un balayage `constants.unitId` du gameconfig :

| summon | invocateur | porteur de l'invocateur |
|---|---|---|
| `admecSmnTechpriest` | `InvocationOfMachineVengeance` (`ActiveAbilityType` 1172) | `admecBossBelisarius` — **npc/boss** |
| `votanSmnEcog` | `EcogSupport` (`TriggeredAbilityType` 1487) | `votanIronmaster` « Vynn » — **HERO**, mais **hors pool** |

Le `S?` de l'audit ne signifiait donc « inatteignable » dans aucun des deux cas : c'est bien la
cause nommée par #1052 — le graphe de l'audit ne balaie que les abilities **des unités**, et il ne
sait pas trancher.

**La voie retenue est le JUMEAU NPC**, apparié par `visualId` — un **MIRROR**, pas une greffe :

```
gameconfig.units.summons.admecSmnTechpriest.visualId == "admecNpc2Techpriest"
gameconfig.units.summons.votanSmnEcog.visualId       == "votanNpc1Ecog"
```

Les deux jumeaux portent le **même kit** (`passiveAbilities` identiques) et leurs **propres**
stats/traits/armes. Amenés par `--explicit-stats <jumeau>:45`.

⚠ **L'unité entre au pool sous son nom SUFFIXÉ DU PALIER** (`admecNpc2Techpriest:45`) : c'est ce
nom-là qu'attend `--a-units`/`--p-units`, et le nom nu y est refusé (`hors pool / non spawnables`).
Une demi-heure perdue là-dessus ; le message d'erreur ne le dit pas.

---

## 2. `VengeanceForTheOmnissiah` — PORTÉ, deux faces

### 2.1 La face COMBAT

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.VengeanceForTheOmnissiahAbility$$CreateTrigger` :

```
On( 0x36 = 54 UnitDefeated, ownerNeedsToBeAlive: 1 )
  & AreFriends( Owner@+0x30, Target@+0x60, comparisonType: 0, anyEntity: false )
  & IsAdjacent( Owner@+0x30, Target@+0x60, selectionType: 2 )
  & IsMechanical( Target@+0x60, selectionType: 2 )
```

`...VengeanceForTheOmnissiahAbility$$CreateBehaviour` :

```
AddEffectOrIncreaseLevel( 0x555 = 1365 MachineVengeance, AbilityStateReference,
                          source = Owner@+0x30, targets = Owner@+0x30,
                          level = ConfigConst(0x73 = AbilityConstantType.effectLevel),
                          maxLevel = NULL )
```

Quatre lectures load-bearing (détail dans l'en-tête du module) :

1. **`source` ET `targets` sont le MÊME slot `+0x30`** — le décompilé lit deux fois
   `*(<Selectors> + 0x30)`. Le voisin de forme `OmnissiahsBlessing` (#1023), sur la **même unité**,
   vise `Target@+0x60` : recopier son `Target()` poserait la pile sur un **cadavre**.
2. **`IsMechanical` porte sur la VICTIME**, jamais sur le porteur — donc le passif ne lit ni stat,
   ni trait, ni arme de son propre porteur.
3. **Le `2` est un `UnitSelectionType`** (`OnlyTargetable`), pas un rayon — et il **n'appelle pas
   `IsAlive`**. Écrire `OnlyAlive` (1) ou `OnlyAliveAndTargetable` (3) — le réflexe naturel quand on
   écoute une MORT — éteindrait le passif en totalité. Même régime que
   `BattleFatigueAbility$$CreateTrigger`.
4. **Aucun gate sur le TUEUR** : ni `OwnerIsActor` ni `OwnerIsTarget` dans le `CreateTrigger`. Le
   porteur gagne sa pile quel que soit l'auteur du kill.

### 2.2 `ConfigConst` est une NUMBER-CONSTANT — ce qui rend l'item confrontable malgré #1049-r1

Le défaut de harnais `#1049-r1` (`--explicit-stats` annonce un `AbilityState` `(niveau 1, mult 100)`
que `unitAbilityStates` contredit `(65, 200)`) fausse toute lecture **per-niveau**. Il ne mord pas
ici, et c'est **LU**, pas supposé :

```
DSLFormulas$$ConfigConst(this, constantType, config)          // TROIS arguments
  -> ConfigAmount$$.ctor(this, config, constantType)          // l'unique surcharge a 3 params
       ecrit config@+0x10 et Nullable(constantType)@+0x38 ; NE TOUCHE PAS +0x30
ConfigAmount$$Calculate :
  if (HasValue(this+0x30)) return AbilityConfiguration.GetVariableForLevel(..., abilityState.Level);
  if (HasValue(this+0x38)) return AbilityConfiguration.GetNumberConstant(config, <+0x38>);
```

Le niveau d'ability n'entre **jamais** dans la lecture. Confirmé au montage : le porteur annonce
`plvl 65 / mult 200` et le gain vaut **1** — la constante du gameconfig
(`constants.effectLevel = 1`, et `variables` est **vide**).

⚠ Le nœud `entities/formulas.py::ConfigConst` du port ne convient **pas** ici : il appelle
`get_variable_for_level`, donc il mirroire `ConfigVar`. Réserve déjà écrite dans ce fichier ; on lit
la constante au gameconfig, comme `savior_protocols.py::savior_chance`.

⚠ `AbilityConstantType.effectLevel` = **115** ; `effectLevel_2` = **118** est le cap 9 que lit
`ArcScourgeAbility$$GetDynamicInvalidCasterReason` sur une **autre** ability. Homonymes proches, et
les confondre lirait la mauvaise clé **sans lever**.

### 2.3 La face DÉCISION — un terme BINAIRE, le premier du registre

`IdunBattle.AI.Playbook.Loki.VengeanceForTheOmnissiahPlaybook` (`.ctor` littéral `0x512`) :

```
tile    = UnitPosition.get_MainTile(case.<+0x18>);                  // TUILE CANDIDATE
friends = query.<slot 0x83 = GetAdjacentFriends>(tile, case.<+0x10>);
foreach (u in friends) {
    if (!UnitExtensions.IsMechanical(u)) continue;
    if (u == case.<+0x10>)               continue;                  // pas SOI-MEME
    value = getUtilityVal("VengeanceForTheOmnissiah_LikesAdjacentMechanical");   // = 30
    break;                                                          // <-- SORTIE AU PREMIER
}
yield return Fix64.op_Implicit(value);
```

⚠ **LE `break` EST LA LECTURE CENTRALE.** Le terme vaut `30` ou `0` — **jamais `30 × N`**. Tous ses
voisins de forme du registre (`legacy_of_combat`, `close_combat_weakness`, `first_among_traitors`)
sont des `Count × poids` : recopier leur corps multiplierait le terme, **et seulement sur les tuiles
à plusieurs voisins mécaniques** — invisible sur un montage à un seul voisin. C'est la première
feuille binaire de `TRIGGERED_MOVE_PLAYBOOKS`.

Le slot `0x83` = 131 est **`IBattleQuery.GetAdjacentFriends`** (arité 2), LU dans
`data/symbols/<build>/metadata/interface_slots.tsv` — les slots 125..128 y portent
`GetAdjacentEnemies`, les 129..132 `GetAdjacentFriends`. Ce sont donc des **amis**.

L'exclusion du mover n'est **pas décorative** : le porteur est son propre allié **et** il est
`Mechanical` (trait réel), donc sans elle le terme serait constant sur toutes les tuiles.

**La face ATTAQUE est DEAD** : corps entier `yield Fix64.op_Implicit(0)`. Elle n'entre pas dans
`psyker.TRIGGERED_ATTACK_PLAYBOOKS`, et **son absence EST le comportement natif**.

### 2.4 Validation

* **LIVE, face COMBAT — ACCORD** (`probe_1071_vengeance_for_the_omnissiah.py`), deux régimes dont
  la **seule** pièce qui bouge est une POSITION :

  | régime | d(porteur, victime) | victime morte | natif | port |
  |---|---|---|---|---|
  | nominal | **1** | oui | `[] -> [1]` | `0 -> 1` |
  | contre-épreuve | **5** | oui | `[] -> []` | `0 -> 0` |

  La géométrie est **assertionnée par BFS**, jamais espérée ; et la victime meurt dans les **deux**
  régimes, donc le zéro de la contre-épreuve n'est pas dégénéré.
* **OFFLINE** : `test_1071_vengeance_for_the_omnissiah_offline.py`, 28 tests — ordinaux figés au
  site, les 3 conjoints par contre-face, et 5 mutants dont *cible du behaviour = le mort*,
  *`OnlyAlive` au lieu d'`OnlyTargetable`*, et *terme produit au lieu de binaire*.
* **NON COUVERT, et c'est écrit** : (a) le canal DÉGÂT de `1365 MachineVengeance` reste non porté
  (résidu #1023-r1, **inchangé** par cette tranche) — le gain est observable par le NIVEAU, pas par
  un dégât ; (b) le volet `Untargetable` du `selectionType = 2` n'est séparé par aucun montage
  (aucune unité ne porte le flag `0x11`) ; (c) **la face DÉCISION n'est pas confrontée LIVE** —
  mirror 1:1 lu au décompilé, gardé par 7 tests offline et le cliquet #419. Résidu #1071-r2.

---

## 3. `RepairEnthusiast` — NON PORTÉ, et pourquoi ce n'est pas « non confrontable »

### 3.1 Il n'a AUCUNE face COMBAT

`frida/classes.tsv` porte, pour `RepairEnthusiast`, **uniquement** le playbook et ses deux
itérateurs. Pas de `RepairEnthusiastAbility`, pas de `RepairEnthusiastVisuals`, pas d'instanciation
fermée `TriggeredAbilityPlaybook<RepairEnthusiastAbility>`.

⚠ « le symbole n'apparaît pas dans la table » ne prouve normalement **rien** (IL2CPP déduplique les
corps de **méthode**). Deux raisons pour lesquelles la conclusion tient ici : `classes.tsv` est
indexée par **CLASSE**, pas par adresse — la dédup ICF n'y opère pas — et le contrôle exige **deux
témoins positifs** du même patron (`VengeanceForTheOmnissiah`, `OmnissiahsBlessing` portent, eux,
les trois entrées). Sans témoin, un critère aveugle aurait rendu le même « absent ».

Le gameconfig concorde : `RepairEnthusiast` n'a **ni `variables` ni `constants`**, et **aucune
description i2**. C'est un passif purement AI.

### 3.2 Face MOVE triviale, face REPAIR réelle

Tailles re-dérivées du delta d'adresses de `ghidra/functions.tsv` :

| corps | taille | verdict |
|---|---|---|
| `RepairEnthusiastPlaybook.<CalculateMovementUtilityInStepsInternal>d__2$$MoveNext` | `0x80` | **trivial** — `yield Fix64(0)`, lu au décompilé |
| `RepairEnthusiastPlaybook.<CalculateRepairUtilityInStepsInternal>d__3$$MoveNext` | `0xe0` | **réel** |
| base `TriggeredAbilityPlaybook<T>$$CalculateRepairUtilityInStepsInternal` | `0x70` | `yield 0` |

Calibrage : `VengeanceForTheOmnissiahPlaybook.<CalculateAttackUtilityInStepsInternal>` vaut `0x80`
(trivial, lu) et sa face MOVE `0x2e0` (réelle, lue) — le seuil sépare donc, il n'est pas inventé.

Le corps REPAIR, lu :

```
if (case.<+0x10> != case.<+0x20>)                                   // actor != target
    if (!UnitExtensions.HasTriggeredAbility(case.<+0x20>, 0x5ea))   // la CIBLE n'est pas un E-COG
        yield return Fix64.FromInt( getUtilityVal("RepairEnthusiast_LikesRepair") );   // = 100
// sinon : sequence VIDE
```

L'E-COG refuse donc de se réparer lui-même et de réparer un autre E-COG. Le poids
`RepairEnthusiast_LikesRepair = 100` est bien présent dans `data/seed-bc.json`.

### 3.3 Le bloqueur est l'ÉTAGE, pas le porteur

La face REPAIR **n'existe nulle part côté port** : aucune méthode
`calculate_repair_utility_in_steps`, aucun registre REPAIR (les trois registres triggered sont
MOVE, ATTACK, non-owner), aucun `evaluate_repair_in_steps` sur le dispatcher
`TriggeredAbilitiesUtility(2)`, et le composite `Repair(47)` est déclaré dans
`utilities/utility_type.py` mais **aucune `ComposedUtility` ne le monte**.

Ce refus est **déjà écrit et argumenté** dans le dépôt — `engine/playbook/non_owner_attack.py`,
résidu **#271-r7** : le `<slot 6>` d'`IUtility`, par lequel `VoltagheistFieldPlaybook` délègue à la
feuille `RepairedAmount(48)`, n'est pas dans `metadata/interface_slots.tsv`, donc le canal n'est pas
établi. Monter un dispatcher REPAIR dont le registre serait vide est le patron **#419** que ce dépôt
refuse.

Porter cette feuille exige donc **trois pièces neuves** : la méthode sur la classe, un registre
`TRIGGERED_REPAIR_PLAYBOOKS`, et un `evaluate_repair_in_steps` **plus un consommateur qui l'appelle**.
C'est une tranche d'étage, pas une tranche de feuille.

### 3.4 Le cliquet INVERSE

`test_1071_repair_enthusiast_verdict_offline.py` grave le verdict en le **re-dérivant** des tables,
et son dernier étage est **fait pour rougir un jour** : dès qu'un playbook du registre acquiert
`calculate_repair_utility_in_steps`, ou que le dispatcher acquiert `evaluate_repair_in_steps`, il
tombe en nommant l'action à faire (inscrire 1514, corps `0xe0`, gate et poids rappelés).

Sans ce cran, le portage de l'étage et celui de la feuille sont deux tranches différentes, et la
seconde serait simplement oubliée. **La morsure est vérifiée** (mutation des deux voies : rouge,
puis retour au vert).

---

## 4. Ce que cette tranche laisse ouvert

* **#1071-r1** — porter la face REPAIR de `RepairEnthusiastPlaybook` (1514). `BLOCAGE: etage`
  (l'étage REPAIR, cf. #271-r7). Le cliquet inverse ci-dessus est ce qui rappellera de la faire.
* **#1071-r2** — confronter LIVE la face DÉCISION de `VengeanceForTheOmnissiah` (terme de tuile
  `Tile(7)`, feuille `TriggeredAbilities(2)`). Le port est un mirror 1:1 gardé offline, mais aucun
  montage ne l'a exercé au natif. `BLOCAGE: aucun`.
* **#1023-r1** (existant, **inchangé**) — le canal DÉGÂT de `1365 MachineVengeance`.
