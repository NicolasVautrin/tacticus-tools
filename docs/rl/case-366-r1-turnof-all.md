# case-366-r1-turnof — `IsTurnOf` agrège par `all`, et le set VIDE rend VRAI

**Question, binaire.** Quand un sélecteur multi-entités est passé à `IsTurnOf`, le natif rend-il VRAI
si UNE SEULE des entités appartient au joueur courant (`any`), ou seulement si TOUTES y appartiennent
(`all`) ?

**Réponse : `all`** — et le corollaire que la formulation du résidu ne posait pas : **le set VIDE rend
VRAI** (vérité vacue). Le port faisait `any(...)` ; il fait `all(...)` depuis ce cas.

**Confrontation live : IMPOSSIBLE, et la raison est mesurée** — sur les **17** opérandes que le build
soumet au nœud, **aucun** ne peut en rendre deux (§3). L'écart corrigé est donc INERTE au natif ;
c'est une correction de FIDÉLITÉ, gardée offline (§5).

## 1. Le décompilé — `IsTurnOfUnitTrigger$$ShouldTrigger`

`IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger`, en clair :

```
if (ctx.CurrentPlayer == null) return false;                  # garde de TETE, ctx@+0x50
sel = this@+0x10;  if (sel == null) throw;
first = sel.SelectFirst(ctx);                                 # slot 1 de l'interface selecteur
if (first != null && EntityExtensions.IsPlayer(first))        # EntityType == 4
    return first.Id == ctx.CurrentPlayer.Id;                  # chemin PLAYER (sec.4)
seq = sel.<slot 6>(ctx, selectionType = 0);                   # variante ACTEURS
if (seq == null) throw;
foreach (e in seq)
    if (e.GetComponent<OwnerComponent>().CurrentPlayerEntityId != ctx.CurrentPlayer.Id)
        return false;                                         # sort FAUX des qu'UNE diverge
return true;                                                  # enumeration epuisee -> VRAI
```

La boucle est un `do { if (!MoveNext()) { Dispose(); return 1; } … } while (owner == current);` — la
sortie par la condition du `while` tombe sur le `return 0`. Donc : `all`, et **`MoveNext()` faux du
premier coup rend `1`**.

Trois lectures ferment la sémantique de la boucle, chacune par une seconde source :

* **le composant** est `IdunBattle.Entities.Components.OwnerComponent`, champ
  `get_CurrentPlayerEntityId` (+0x10) : le même couple de champs, dans le même ordre, que
  `IdunBattle.View.FSM.VisualBattleQuery$$IsControlledByCurrentPlayer`, qui l'appelle **par son nom**
  (le seul endroit où ghidra le nomme). Donc bien le propriétaire **COURANT** — mind-control inclus —
  et non l'original.
* **`slot 1` = `IdunBattle.DSL.TargetsSelector$$SelectFirst`** : ce membre par défaut énumère
  `Select(ctx)` (slot 0x17) et rend la **première entité non nulle**. Recoupé par
  `IdunBattle.Entities.Triggers.IsSteppableUnitTrigger$$ShouldTrigger`, qui appelle le même slot 1 et
  traite le retour comme UNE unité.
* **`selectionType = 0` ne filtre RIEN** : l'énumération mappe chaque entité par
  `IdunBattle.DSL.TargetsSelector$$SelectUnit(e, selectionType)`, et
  `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` rend VRAI inconditionnellement pour
  `0` (seuls `1` = vivant, `2` = sans flag 0x11, `3` = les deux, testent quoi que ce soit). Un porteur
  **MORT reste dans le set**. Le même `SelectUnit` résout une **TUILE** (ou un `UnitFoot`) en son
  occupant — une tuile VIDE disparaît donc du set, et c'est la seule façon d'atteindre « set vide ».

⚠ Ne pas confondre avec `IdunBattle.Core.Services.BattleQuery$$IsTurnOfUnit` (5 refs) : prédicat
impératif per-unité, sans rapport avec le nœud DSL.

## 2. La correction du port

`scripts/python/engine/entities/triggers.py::IsTurnOf.should_trigger` : `any(...)` → `all(...)`.
La garde `current_player_id is None -> False` était déjà juste — mais elle n'était pas une
« dégradation conservatrice » comme le disait la docstring : c'est **littéralement la garde de tête du
natif** (`ctx@+0x50 == 0`). Elle est désormais citée comme telle, et elle **doit** rester AVANT
l'agrégation, sinon la vérité vacue la mangerait.

**Limite assumée** : le natif LÈVE quand la sélection est `null`, là où une sélection VIDE rend VRAI.
`_units_of` confond les deux (`None -> []`) — le port n'a pas de canal d'exception. Ce n'est pas une
perte : côté port, un accesseur singleton qui rend `None` signifie « le contexte n'a pas cette
entité », ce qui est exactement le cas natif « `SelectUnit` filtre l'entité → set vide → VRAI ».

## 3. Recensement des opérandes — pourquoi la géométrie discriminante est INATTEIGNABLE

Mesure **exhaustive** (base de références ghidra, pas un balayage de texte) : `list_xrefs` sur le slot
de cache de classe qu'alloue `IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf` rend **3** fonctions
allocatrices — la factory, plus **deux allocations INLINÉES** qui n'apparaissent dans aucun xref de la
factory (c'est le piège de ce recensement) :

| allocateur | opérande |
|---|---|
| `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` (inliné) | `<DSLSelectors+0x30>` = **Owner** → c'est `<DSLTriggers+0x28>`, le nœud partagé `IsTurnOf(Owner)` de tout le port |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyStun$$CreateBehaviour` (inliné) | `<DSLSelectors+0x48>` = **Caster** (le MÊME sélecteur que les `targets` de son `AddEffect(0x48a)`) |
| `IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf` | 15 call-sites, ci-dessous |

Les 15 call-sites de la factory :

| opérande | call-sites |
|---|---|
| **Owner** (`<DSLSelectors+0x30>`) | `NightshroudAbility$$CreateTrigger`, `EmbodiedProphecyAbility$$CreateTrigger`, `GazeOfMagnusAbility$$CreateTrigger`, `GuardianOrganismAbility$$CreateTrigger`, `GuardianOrganism_DamageReductionEffect$$CreateTargetTrigger` |
| **sujet de `Foreach`** (`elem`) | `EnvDespoiledGroundTileAbility$$CreateBehaviour` |
| **`EffectSource(<DSLSelectors+0x38>)`** | `TzeentchsFirestormBaseEffect$$CreateHandleTriggerAbilitiesInternal` |
| **`ABondEffect$$BondedEntitySelector`** (= `BondedEntityFromEffect(<DSLSelectors+0x38>)`) | `CallRipperSwarms_PendingSummonEffect$$CreateHandleTriggerAbilitiesInternal` et `$$GetTurnStartBehaviourTrigger` |
| **slot virtuel `+0x758`** = `GetAttackingUnitSelector` | `APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal` et `$$GetAttackTrigger` |
| **`Player(team)`** → `PlayersByTeamSelector` | `EnvAngelsOfDeathAbility$$CreateTrigger` (team 2), `EnvValkyrieStrikeAbility$$CreateTrigger` (1), `EnvValkyrieStrike_AttackAbility$$CreateTrigger` (2) |
| **`Units(Owner, unique = 1, selectionType = 3)`** → `UnitsOnTilesSelector` | `FirstAidHealEffect$$CreateTargetTrigger` |

Ventilation :

* **13 opérandes SINGLETONS** — les accesseurs partagés (`DSLSelectors$$InitializeShared` alloue 13
  slots, chacun par un ctor à 1 argument = une lecture de champ du contexte), le sujet d'un `Foreach`,
  et les accesseurs d'effet.
* **3 opérandes `Player(team)`** — `IdunBattle.Entities.Selectors.PlayersByTeamSelector` rend des
  entités de type PLAYER, donc `IsPlayer(SelectFirst(...))` est VRAI et le natif **court-circuite la
  boucle** : ces trois-là n'atteignent jamais l'agrégation.
* **1 opérande de collection** — `Units(Owner)` de FirstAid. Et son `Owner` est **UNE tuile** :
  `IdunBattleLogic.Entities.Abilities.Tiles.FirstAidHealAbility$$CreateBehaviour` est
  `AddEffect(0xa = 10, AbilityStateReference, <DSLSelectors+0x30>, 0)` — une ability de TUILE, dont
  l'owner est la tuile. `UnitsOnTilesSelector` en rend donc **l'occupant**, soit ≤ 1 unité.

⇒ **aucun site du build ne peut soumettre 2 entités-unités au nœud.** L'écart `any`/`all` était
INERTE, et la géométrie qui le discrimine n'est pas montable LIVE — pas par manque de harnais, mais
parce que le jeu ne l'écrit nulle part.

**La seule cardinalité de l'inventaire qui soit INFÉRÉE et non lue** est celle du slot virtuel
`+0x758` : le défaut de `APendingAttackEffect` n'apparaît pas nommé dans la table (corps trivial
dédupliqué), et l'unique override nommé du build,
`Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.InstrumentsOfVengeance_PendingAttackEffect$$GetAttackingUnitSelector`,
alloue un sélecteur d'effet à un argument (singleton). Le nom du slot (« AttackingUnit », singulier)
va dans le même sens. À relire si un `PendingAttackEffect` neuf apparaît.

## 4. Le chemin PLAYER — lu, NON porté

Quand `SelectFirst` rend une entité de type PLAYER (`EntityType == 4`, testé par
`IdunBattle.Entities.EntityExtensions$$IsPlayer`), le natif compare directement `first.Id` à
`ctx.CurrentPlayer.Id`, sans énumérer. Trois call-sites l'empruntent (§3), aucun n'est porté : le port
n'a pas d'entité-JOUEUR ni de nœud `Player(team)`. Le mirror **ne l'écrit pas** — ce serait inventer
une représentation. Résidu à rouvrir le jour où l'une des trois `Env*Ability` entre au registre.

## 5. Validation

* **Gardes** : `scripts/python/tests/engine/entities/test_366_r1_turnof_all_offline.py` — 8 cliquets,
  100 % offline, montés sur le VRAI sélecteur du port (`Units(<tiles>)` = mirror d'
  `UnitsOnTilesSelector`, la forme exacte du seul call-site natif de collection) avec DEUX tuiles
  occupées par deux camps. Chaque cas vérifie d'abord que la sélection a la cardinalité voulue —
  sans quoi un « FAUX » ne prouverait rien.
* **Mutations adversariales** :

  | mutation | rouges |
  |---|---|
  | **M1** retour à `any(...)` | **4** (les 3 faces du discriminant + la vérité vacue) |
  | **M2** `all(...)` + garde « conservatrice » `if not units: return False` | **2** (les deux faces de la vérité vacue) |

* **Non-régression LIVE** : le seul consommateur du nœud dans le port est
  `runner/operations/triggers/loki/despoiled_ground.py` (`IsTurnOf(Target())`, singleton) —
  `test_despoiled_ground_live.py` **5/5**. Et `test_firstaid_heal_live.py` **2/2** (le call-site natif
  de collection, dans sa cardinalité réelle : 1 occupant, les deux polarités).

## 6. Ce qui n'est PAS couvert

* **Le régime à ≥ 2 entités n'est pas confronté LIVE** — et ne peut pas l'être : §3. Ce qui est
  confronté, c'est le régime réel (≤ 1 entité), sur les deux polarités.
* **Le chemin PLAYER n'est pas porté** (§4).
* **La sélection `null`** (que le natif traite en levant) n'est pas distinguée de la sélection VIDE
  (§2).
* La face **DÉCISION** n'a pas de consommateur du nœud : `playbook/scene.py::Scene.is_turn_of` et
  `runner/damage_model.py::_owner_turn_flag` sont les foyers IMPÉRATIFS du singleton `IsTurnOf(Owner)`
  (`<DSLTriggers+0x28>`), inchangés par ce cas.
