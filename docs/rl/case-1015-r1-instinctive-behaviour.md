# #1015-r1 — `InstinctiveBehaviour` : le trait que le port NOMMAIT sans l'EXÉCUTER

`UnitTrait.InstinctiveBehaviour` (0x7e5 = **2021**), **23 porteurs** (18 npc + 5 summons Tyranides :
`tyranSmn{RipperSwarm,Hormagaunt,Barbgaunt,Termagant,SporeMine}`).

i2 — `Traits/InstinctiveBehaviour_Description` : « If there are targets in range, this unit does not
move and attacks the closest target. »

**Le point de départ** : `trait_channels.canaux('InstinctiveBehaviour')` rendait `[]` — aucune
évaluation nulle part dans `engine/**`. Et le mirror `EffectType.InstinctiveBehaviour_BlockMovement`
(1235) existait **sans aucune classe d'effet portée** : le port nommait la donnée sans exécuter la
mécanique.

---

## 1. La chaîne native, de bout en bout

```
UnitTrait.InstinctiveBehaviour (2021)
  └─ AddTraitOperation$$AddDerivedAbilities        (dict `Trait +0x0`, Trait$$GetTriggeredAbility)
     └─ TriggeredAbilityType.InstinctiveBehaviour = 0x413 = 1043
        ├─ InstinctiveBehaviour_UpdateTargetAbility   (BaseTriggeredAbility)      -> face CIBLAGE
        └─ InstinctiveBehaviour_InitAbility           (AOwnerEffectSpecificTriggeredAbility(0x413))
           └─ $$GetEffectType -> `return 0x4d3`  =  EffectType.InstinctiveBehaviour_BlockMovement
              └─ InstinctiveBehaviourBlockMovementEffect (: BlockUnitMovementEffect)  -> face MOUVEMENT
```

`AbilitiesDatabase.<>c$$<InitializeTriggeredAbilities>b__28_46` construit l'`InitAbility` ; son
`.ctor` passe `0x413` à `AOwnerEffectSpecificTriggeredAbility$$.ctor`, donc son `CreateTrigger`
hérité est `OnOwnerSpecificAbilityInit(0x413)` et son `CreateBehaviour` hérité est l'`AddEffect`
permanent d'`AOwnerEffectTriggeredAbility` — patron `Terrifying` / `Diminutive` / `Vitarus_InitAbility`.

---

## 2. Face CIBLAGE — `InstinctiveBehaviour_UpdateTargetAbility`

### `$$GetUpdatedForcedTarget`

```
tiles   = DSLSelectors$$Tiles( Owner@<DSLSelectors+0x30> )
rng     = DSLFormulas$$NormalAttackRange( unit = Owner, unitTile = tiles )
mv      = DSLFormulas$$StatAmount( Owner, StatType.Movement = 1, StatPart.Current = 0, null, 0 )
enemies = DSLSelectors$$NearestAttackableEnemies( Owner, DistanceType.Simple = 0,
                                                  maxDistance = DSLFormulas$$Sum(rng, mv) )
gate    =   AmountIsEqualOrGreater( Count(Tiles(Owner)), <DSLFormulas+0x20> = Direct(1) )
          & NOT IsEffectTarget( Owner, 0x41c = EffectType.Synapse_Effect )
return    DSLSelectors$$If( gate, enemies, DSLSelectors$$None() )
```

⚠ **`StatType 0x1` est `Movement`, pas `Range`.** La portée du sélecteur est donc
`portée d'arme + mouvement` — « ce que l'unité peut atteindre CE TOUR ». C'est ce qui articule les
deux faces : l'ability DÉSIGNE une cible qu'il faudra peut-être approcher, l'effet ne BLOQUE le
mouvement que si elle est **déjà** à portée.

`NearestAttackableEnemies` n'est pas une classe, c'est une composition (LUE) :
`Nearest( Unobscured( UnitsWithoutTrait( Enemies(Owner, AllAliveUnits@<DSLSelectors+0x20>, 3),
Steppable = 0x1b, 3 ), Owner ), target = Owner, pathfindingUnit = Owner, distanceType, maxDistance )`.
« Attackable » ne désigne **aucun** gate de ciblage : c'est « ennemi vivant et ciblable, non
Steppable, non obscurci ».

### `$$CreateTrigger` = `IsValidTrigger & IsNotTaunted & HasTargetChanged`

`IsNotTaunted` = `NOT IsEffectTarget(Owner, 27 Taunted_OnlySpecificTargets)`. **Le taunt gagne** :
une unité tauntée ne voit pas sa liste réécrite par son instinct. La docstring de
`ForcedAttackTargetsComponent` notait la non-coexistence des voies 1 (taunt, REMPLACE) et 3
(instinct, INCRÉMENTE) comme un fait du PORT — c'est en réalité le natif qui l'organise.

`$$IsValidTrigger` — dix vecteurs, `ownerNeedsToBeAlive: true` partout, avec
`C = AreEnemies(Owner@+0x30, Other@+0x60, ByCurrentTeam) | IsOwnerOfEffect(Other@+0x60, Synapse_Effect, false)` :

| vecteur | garde |
|---|---|
| `On(0x12 TurnStart_EffectActivation)` | — |
| `On(0x32 UnitAdded)` | `C` |
| `OnDeath(overkill: true, steppable: false)` | — |
| `On(0x2e UnitResurrected)` | `C` |
| `On(0x2d UnitRevived)` | `C` |
| `On(0x34 UnitFled)` | `C` |
| `On(0x1d UnitPositionChanged_2)` | `C` |
| `On(0x1d UnitPositionChanged_2)` | `get_OwnerIsTarget` |
| `On(0x3b UnitBecameTargetable)` | `C` |
| `On(0x2b UnitHealed)` | `get_OwnerIsTarget` |

### `$$CreateBehaviour` — un DIFF, pas un remplacement

```
toRemove = ForcedAttackTargets(Owner) − GetUpdatedForcedTarget()
toAdd    = GetUpdatedForcedTarget()   − ForcedAttackTargets(Owner)
return ( RemoveForcedAttackTarget(Owner, toRemove) & AddForcedAttackTarget(Owner, toAdd) )
       & RefreshEffects( RefreshEffectTrigger.UnitStateChanged = 3 )
```

Ce sont les **voies 3 et 4** du `ForcedAttackTargetsComponent`, que sa propre docstring nommait
comme « non portées ». `AddForcedAttackTargetBehaviour$$Execute` teste `Contains` avant `Add` ;
`RemoveForcedAttackTargetBehaviour$$Execute` appelle `Remove` **sans** garde — asymétrie LUE,
transcrite.

---

## 3. Face MOUVEMENT — l'effet 1235, et la prose du port qu'il RÉFUTE

`BlockUnitMovementEffect$$ApplyInternal` / `$$RevertInternal`, LUS :

```
ApplyInternal (this, owner, target, effect) : target.GetComponent<MovementComponent>()
                                                    .<+0x50 : Dictionary>.Add(effect.Id, effect.Id)
RevertInternal(this, owner, target, effect) : mc.<+0x50>.Remove(effect.Id)
MovementComponent$$IsAllowedToMove          : <+0x50>.Count == 0
```

⚠ **`turnflow._can_move` écrivait que ce 4ᵉ étage n'était pas portable, « aucun écrivain n'étant une
méthode NOMMÉE du binaire : les écritures sont inline ».** C'est faux : les écrivains sont **deux**,
tous deux nommés — ceux ci-dessus et leurs jumeaux `BlockUnitMovementBondEffect$${Apply,Revert}Internal`,
qui écrivent le **même** champ. La prescription qui en découlait (« on ne le fabrique PAS depuis les
effets `*_BlockMovement` : ce serait une hypothèse déguisée en mirror ») tombe avec sa prémisse.

### `$$CreateActiveCondition` — mirror 1:1

```
fat = ForcedAttackTargets( Owner@<DSLSelectors+0x30> )
c1  = AmountIsGreaterThanZero( fat )
c2  = Any( fat,                 IsInAttackOrAbilityRange( Owner, <DSLSelectors+0x68> ) )
c3  = Any( Tiles(Owner),        IsWalkable(               <DSLSelectors+0x68> ) )
return ( <DSLTriggers+0x28> & c3 ) & ( c1 & c2 )
```

`<DSLTriggers+0x28>` = **`IsTurnOf(Owner)`** (champ pré-alloué par `DSLTriggers$$InitializeShared`,
lecture déjà établie par `runner/components.py`). **L'effet n'est donc ACTIF que pendant le tour de
son porteur.**

⚠ **Les deux `Any` NE COLLAPSENT PAS.** Le collapse attesté (`docs/rl/dsl-port-attestations.tsv`)
vaut pour `Any(sel, HasEffect(élément, T))`, parce que le `HasEffect` du port itère déjà son
sélecteur. Ici les corps sont `IsInAttackOrAbilityRange` et `IsWalkable` : sans le vrai nœud `Any`
(mirror de `XAnyYTrigger`, dont la lambda construit `new AbilityEntities(base, selected)` — le
**même slot `ActiveTarget`** que `Filter`), l'élément ne serait jamais lié et les deux prédicats
liraient le contexte englobant.

---

## 4. Ce que la MESURE LIVE a trouvé — deux bugs SILENCIEUX du port

`probe_1015r1_instinctive_behaviour.py` : trait 2021 **forcé** (`--unit-stat Traits=[...]`, levier
qui mord sur 104 des 105 membres) sur une unité du pool, **deux régimes** et un **témoin non nul**.
Le forçage est légitime : le natif dérive l'ability DU TRAIT, donc donner le trait c'est donner la
mécanique — et un summon s'OBSERVE mais ne se COMMANDE pas (#291), donc on ne pourrait pas le
conduire aux deux régimes.

Board `MC1_67`, seed 777, porteur `tyranTyrantGuard` (mêlée), témoin `ultraCalgar` :

| | LOIN (d = 3) | PRÈS (d = 1) |
|---|---|---|
| natif `aiMovableTiles` (porteur) | **12** | **0** |
| port `_can_move` | `True` | `False` |
| natif `abilityReason` sur une AUTRE cible | `0x800000 TargetIsAllowedForCaster` | `0x800000` |
| natif `abilityReason` sur la cible forcée | `0x8000000 TargetIsInRange` | `0` |
| port `get_only_targets` | `[79]` | `[79]` |
| effet 1235 actif (port) | non | **oui** |
| **TÉMOIN** natif / port | 11 / libre | 10 / libre |

Le natif refuse l'autre cible avec `TargetIsAllowedForCaster` dans les **deux** régimes : il a donc,
lui aussi, une liste de cibles forcées non vide, et elle désigne la **même** unité que le port.

GÉNÉRALISATION rejouée : board `C4_09`, seed 31337, porteur **RANGED** `necroWarden` (portée 3,
`--far 5`) — cinq crans verts.

### Bug 1 — `Enemies` : l'ordre des deux premiers arguments est INVERSÉ entre natif et port

Natif `Enemies(of, entities, selectionType)` ; nœud porté `Enemies(inner, reference, selection_type)`.
`nearest_attackable_enemies` rendait `[le porteur lui-même]` : l'unité se forçait à s'attaquer, sans
aucune erreur.

### Bug 2 — `snapshot.load_state` n'appelait QUE LA MOITIÉ de `InitializeActorAbilitiesOperation$$Execute`

L'opération native a **deux** boucles : ABILITIES et **TRAITS**. `runner/operations/spawn.py`
appelle bien les deux ; le chemin de la CAPTURE n'appelait que la première. Une unité **déjà sur le
plateau au capture** n'avait donc jamais ses owner-effects de TRAIT.

C'est resté invisible tant que tous les owner-effects de trait portés étaient **inconditionnels**
(`BigTarget`, `Daemon`, `Terrifying`, `Diminutive`, `ShadowInTheWarp`, `HeavyWeapon`, `MartialKatah`,
`RangedSpecialist`) : le natif les a dès la création, donc le canal actif-only les publie, donc
`EffectsState.seed` les avait déjà et les deux `_materialize_owner_effect` sont des no-op
(idempotents). **1235 est le premier owner-effet de trait dont la `CreateActiveCondition` soit
CONDITIONNELLE.**

**RAYON DE SOUFFLE MESURÉ : 0** instance d'effet change sur un montage standard de 8 unités
(`necroWarden` / `ultraCalgar` / `tyranTyrantGuard` / `orksRuntherd` vs `darkaAzrael` /
`astraBullgryn` / `tauCrisis` / `bloodMephiston`).

### La voie SPAWN, confrontée séparément

Un `tyranSmnHormagaunt` spawné par `SpawnUnitOperation` (traits de kit
`['Summon', 'InstinctiveBehaviour', 'BattleFatigue']`) reçoit bien l'effet 1235 **et**
`InstinctiveBehaviourUpdateTargetAbility` — les deux voies (CAPTURE et SPAWN) sont donc couvertes.

---

## 5. Effet de bord utile — `SynapseEffect$$CreateTargetSelector` entre au foyer

`IsEffectTarget(Owner, Synapse_Effect)` exigeait la géométrie de l'aura, qui n'était pas portée.
LUE et inscrite dans `entities/effect_targets.py` :

```
S = SurroundingUnits( Owner@+0x30, range = 2, unique = true, includeCenter = FALSE, sel = 3 )
F = Friends( Owner@+0x30, S, 3 )
return Unique(   UnitsWithTrait(F, 0x3f7 = 1015 BattleFatigue,        3)
               + UnitsWithTrait(F, 0x7e5 = 2021 InstinctiveBehaviour, 3)
               + UnitsFromFaction( UnitsWithoutTrait(F, 0x7e8 = 2024 Synapse, 3),
                                   0xc = UnitFaction.Tyranids, 3) )
```

⚠ **`includeCenter = FALSE` : l'émetteur n'est PAS dans sa propre bulle.** C'est le même fait que la
mesure live #1011 (patte SELF à 0 avec le Neurothrope pour seul porteur `Synapse`), ici établi par un
**second site natif indépendant** — `BattleQuery$$GetInRangeAuraAmount` le disait sur l'axe AURA, ce
sélecteur-ci le dit sur l'axe CIBLES.

Le 3ᵉ disjoint exige un canal FACTION, **optionnel** du protocole `EffectTargetWorld` : un substrat
qui ne le publie pas fait rendre `None` (NON MESURÉ), **jamais un ensemble partiel**. Seul le
substrat RUNNER l'implémente.

---

## 6. Nœuds DSL neufs (mirrors 1:1)

| nœud | natif |
|---|---|
| `Any(list, trigger)` | `DSLTriggers$$Any` → `XAnyYTrigger` |
| `IsWalkable(sel)` | `DSLTriggers$$IsWalkable` = `Count(Walkable(sel)) >= 1` |
| `IsInAttackOrAbilityRange(a, t)` | `IsInAttackOrAbilityRangeTrigger$$ShouldTrigger` (+ `IBattleQuery` slot **0x41 `IsValidTarget`**, lu dans `metadata/interface_slots.tsv`) |
| `IsEffectTarget(e, type)` | `DSLTriggers$$IsEffectTarget` (le foyer de géométrie existait, le nœud non) |
| `NormalAttackRange(u, tiles)` | `NormalAttackRangeFormula$$Calculate` |
| `ForcedAttackTargets(u)` | `UnitForcedAttackTargetsSelector$$Select` |
| `nearest_attackable_enemies(...)` | `DSLSelectors$$NearestAttackableEnemies` (composition) |
| `Add`/`RemoveForcedAttackTarget`, `RefreshEffects` | les trois feuilles du `CreateBehaviour` |

⚠ **`IsWalkable` travaille sur des ID DE TUILE** (`board.walkable(tid)`) : `Tiles(..., as_ids=True)`
est obligatoire — même piège que `Vitarus`.

⚠ **Le module de l'effet et celui de son ARBRE sont SÉPARÉS, et c'est mesuré** :
`entities/triggers.py` importe `services/movement_query`, qui importe `runner/components`, qui
importe `entities/effects/__init__` → `factory` → la classe d'effet. Laisser l'arbre dans le module
de la classe fermait le cycle (`ImportError` sur `OwnerComponent`, `probe_313` étape 5 ROUGE). La
parade est la **première** de la doctrine — DÉPLACER (`instinctive_behaviour_condition.py`), pas
différer.

---

## 7. Résidus nommés

* **`#1015-r2`** — `BlockUnitMovementBondEffect$$ApplyInternal` écrit le **même**
  `MovementComponent+0x50`. `Taunted_BlockMovement` (25), `Vines_BlockMovement` (91) et
  `PrecisionShot_BlockMovement` (1016) y passent probablement, mais leur appariement
  `EffectType → classe` n'a **pas** été lu dans l'`EffectsDatabase` : les inscrire sur la foi du NOM
  serait le vice de `case-270r1-volet2-cles-ambigues`. Écart PERMISSIF et **inchangé** par cette
  tranche.
* **`On(0x2b = 43 UnitHealed)` n'a aucun émetteur porté** (`runner/operations/heal.py` le nomme dans
  ses non-portés ; #1037 n'a câblé que `0x2c`). Coût **nul** sur cette ability :
  `NearestAttackableEnemies` ne lit ni PV ni bouclier. Le bras n'existe côté natif que parce qu'un
  soin peut RANIMER — et la voie ranimation est couverte par `On(0x2d)` / `On(0x2e)`, tous deux émis.
* **`IsNotTaunted` est INERTE aujourd'hui** : `is_effect_target` n'a pas de géométrie portée pour
  l'effet 27, donc il rend `None` et le port ne conclut pas au taunt. Direction : le port continue à
  maintenir la liste là où le natif s'arrêterait — mais la voie 1 (`TauntedEffect$$ApplyInternal`)
  REMPLACE la liste au moment du cast, donc l'écart n'est observable qu'entre deux réécritures.
