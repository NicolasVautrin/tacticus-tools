# case-1013-r2 — `TheArdentBlade` (relique 1468) : l'étage débloqué, la RE re-confrontée, le port qui reste

RE : décompilé ghidra, build `rnca9r7q6c`. **État : l'étage BLOQUANT est levé et livré ; le port du
trigger n'est PAS écrit** — inventaire exact en §5.

---

## 1. Ce que la re-lecture a CORRIGÉ dans l'énoncé du résidu

L'énoncé de `#1013-r2` (backlog) donnait les trois arbres. Il est **structurellement juste** mais
portait trois erreurs d'argument, dont une qui **casserait** le port.

| # | Ce que disait l'énoncé | Ce que dit le décompilé |
|---|---|---|
| 1 | `Resurrect(<morte>, <tuile>, Get(hp), **2**, ...)` — le `2` en rang neutre | `2` = **`healType` = `HealType.Any`** (`IdunBattle.Entities.Enum.HealType` : `0=NonMechanical, 1=Mechanical, 2=Any`). Or le nœud Python `Resurrect` a **`heal_type: int = 0` par défaut** (`engine/runner/abilities/behaviours/lifecycle.py`) : laisser le défaut **refuserait de ressusciter** une Geminae classée mécanique. À passer explicitement. |
| 2 | `Group(PerformAIAttack(...), ..., 0x20)` | Le `groupEntity` du 2e `Group` est **la CIBLE choisie**, pas `Owner`. Le 1er `Group` (résurrection), lui, porte bien `Owner`. |
| 3 | `On(0x36 = UnitDefeated)` | `IdunBattleLogic.Entities.DSLTriggers$$On(type, ownerNeedsToBeAlive = **true**)` rend `<EventTrigger(0x36)> & <trigger « owner vivant »@this+0x20>` (posé par `$$InitializeShared`). Il y a **six** conjonctions effectives, pas cinq — sans ce ET, le trigger partirait aussi quand Celestine vient de mourir. |

Et **trois arguments que l'énoncé laissait nus**, tous des enums (règle « un entier qui désigne
passe par un enum ») :

* `HasEffect(Owner, 1462, true, **6**)` → `targetType` = `EffectTargetType.Both` (champ de bits,
  `2=Owner | 4=Target`), **pas** un nombre de tours ;
* `AreEnemies(Owner, Target, **1**)` → `UnitTeamSelectionType.ByOriginalTeam` — non cosmétique :
  une unité convertie est jugée sur son équipe **d'origine** ;
* `UnitsWithId(Children(Owner), unitId, **0**)` → `UnitSelectionType.Any`, absent de l'énoncé et
  indispensable (sans `Any`, `DeadUnits` ne trouverait rien).

Enfin, `First(..., 1, **ignoreForcedTargets = false**)` a un 3e argument, et le `Filter` du
sélecteur de cible porte sur l'ensemble **complet** des Geminae (`UnitsWithId`), pas sur le
sous-ensemble mort.

`GroupType` : `0x28 = 40 = Ability_Other` (résurrection), `0x20 = 32 = Ability_Attack` (attaque IA)
— `IdunBattle.Streams.GroupType`.

---

## 2. L'étage qui BLOQUAIT — `DSLBehaviors$$DeactivateEffect`, LIVRÉ

`IdunBattleLogic.Entities.DSLBehaviors$$DeactivateEffect(selector, effectType)` instancie
`IdunBattle.Entities.Behaviours.DeactivateEffectBehaviour` (`+0x50 = selector`,
`+0x60 = (int)effectType`). Son `Execute` est le **JUMEAU EXACT** d'`ActivateEffectBehaviour$$Execute`
— corps identique instruction pour instruction, seul l'index de slot du processeur diffère :
**`0x2d` = 45** contre `0x2c` = 44.

Le slot 45 mène à `IdunBattle.Operations.DeactivateEffectOperation$$Execute`, qui pousse une demande
**typée** au slot 47 (`RefreshEffects`). L'écriture réelle est
`IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` :

```
if (effectComponent->+0x5c == 0)  -> NO-OP (sort sans rien ecrire)
else
    effectComponent->+0x5c = 0                        # IsActive
    UpdateEffectTargets(this, desiredTargets = <List VIDE>, ...)
```

⚠ **Il DÉSACTIVE, il ne RETIRE PAS.** `RemoveEffect` est un slot **DISTINCT** (17) de
`IdunBattle.Core.Services.IOperationProcessor`, jamais emprunté ici : l'entité-effet **survit**, seul
le flag bascule, et le retargetting vers l'ensemble vide fait jouer les `ReverseModification`. C'est
exactement ce dont la relique a besoin — le couple `AddEffect`+`ActivateEffect` / `DeactivateEffect`
lui sert de **jeton à un coup par pose**, relu par le `HasEffect(..., onlyActive = true)` du
`CreateTrigger`. Un port qui supprimerait l'instance romprait le cycle en silence.

**ASYMÉTRIE avec sa jumelle, et elle est voulue** : `ActivateEffect` doit **matérialiser** une
instance absente (le canal de seed `decisionView` DROPPE les effets `IsActive == 0`, donc
« absente » y signifie « désactivée »). Le sens inverse n'a pas cette ambiguïté — une instance
absente côté port est un effet qui n'existe pas, et le natif sort de toute façon en no-op.
Matérialiser pour éteindre serait **inventer une entité**.

Port : `engine/runner/abilities/behaviours/effects.py::DeactivateEffect`.
Cliquet : `tests/engine/test_1013r2_deactivate_effect_offline.py` (11 tests, 5 étages).
**Vu ROUGE sous deux mutations** : instance RETIRÉE au lieu d'éteinte (2 rouges, étage 2) ; filtre
par type supprimé (2 rouges, étage 1).

---

## 3. L'étage qu'on croyait manquant, et qui NE MANQUE PAS

L'énoncé annonçait `SortTilesByUtilityForSummon` « absent comme NŒUD ». **C'est périmé** : le nœud
existe depuis #448-r1 (`engine/entities/selectors/tiles.py::SortTilesByUtility`). Reste à savoir
s'il mirrore le call-site `ForSummon`. Les quatre surcharges natives :

```
SortTilesByUtilityForSummon(tiles, utilityType:UtilityType, parent)          <-- LE SITE
SortTilesByUtilityForSummon(tiles, utilityDefinition, parent)
SortTilesByUtility(tiles, unit, utilityType:UtilityType, parent)
SortTilesByUtility(tiles, unit, utilityDefinition, parent)                    <-- le foyer reel
```

Corps de la surcharge du site :

```
unit = new <selecteur>( state, null, null )      // MEME forme que DSLSelectors$$Get(entity), entity = null
def  = new UtilityDefinition( utilityType )      // OUI, le 7 EST enveloppe
return SortTilesByUtility(tiles, unit, def, parent)
```

⇒ `SortTilesByUtility(source, unit_sel=None, utility_type=UtilityType.Tile, parent_sel=Owner)` est
un mirror **VALEUR-ÉQUIVALENT**, pas structurel : le natif *appelle* un sélecteur qui rend `null`,
le port court-circuite l'appel. Les deux finissent avec `dc.unit = null`, ce que
`engine/utilities/tile.py` documente déjà. **HYPOTHÈSE nommée** : le `SelectUnit` de cette classe de
sélecteur n'a pas été lu — si elle levait sur une entité nulle au lieu de rendre `null`,
l'équivalence tomberait. (La classe est innommable par les tables : son ctor est un corps
dédupliqué attribué à `System.Data.NameNode$$.ctor`.)

Les autres briques du `CreateBehaviour` **existent toutes** côté port : `Resurrect` (feuille DSL +
`operations/resurrect.py`), `PerformAIAttack`, `Group`, `If`, `DeadUnits`, `First`, `Filter`,
`PickRandomly`, `UnitsWithId`, `ChildrenOf`, `CanAddUnit`, `AdjacentTiles`, `IsAlive`, `IsInRange`,
`AmountIsGreaterThanZero`, `OwnerIsActor`, `AreEnemies`, `HasEffect`. Les trois mirrors d'enum de
config sont **concordants** : `AbilityConstantType.unitId = 0`, `.range = 22`,
`AbilityVariableType.hp = 29`.

⚠ Piège doctrinal **actif** ici : `22` est `range` côté `AbilityConstantType` mais `blockDmg_2` côté
`AbilityVariableType` — confondre `GetNumberConstant` et `GetVariableForLevel` serait **silencieux
en ordinal**.

---

## 4. Ce que fait la 2e utilité, que l'énoncé ne mentionnait pas

Le `UtilityDefinition` du `PerformAIAttack` est bâti au site, sans aucun poids :

```
utilities = new WeightedUtility[2]
utilities[0] = new WeightedUtility( 0x6  = 6  = UtilityType.UnitMovement,          weight = null )
utilities[1] = new WeightedUtility( 0x42 = 66 = UtilityType.TheArdentBlade_Geminae, weight = null )
bucket = new UtilityBucket( utilities, minUtilityDifference = null )
def    = new UtilityDefinition( bucket )
```

`IdunBattle.AI.Utilities.TheArdentBlade_GeminaeUtility$$EvaluateAttackInSteps` :

```
x = Fix64(0)
parent = UnitExtensions.GetParent( case.unit, state, root = false )
if ( AreEntitiesAdjacent( UnitPosition.get_MainTile(case), parent ) )
    x += GetUtilityValue("LikesAdjacentCelestine")
yield x
```

Valeur lue dans le `BC.Utilities` de la seed : `"TheArdentBlade_Geminae": {"LikesAdjacentCelestine": 30}`
⇒ **+30 quand la tuile visée est adjacente au parent de la Geminae (Celestine)**. Le mirror
`engine/utilities/utility_type.py` porte déjà `TheArdentBlade_Geminae = 66` ; **l'utilité elle-même
n'est pas portée**.

---

## 5. Ce qui RESTE à porter, et le montage de confrontation

**Non écrit** (le résidu reste OUVERT, `BLOCAGE: aucun` désormais) :

1. `engine/runner/operations/triggers/loki/the_ardent_blade.py` — les deux classes, sur le patron de
   `geminae_superia.py` (même unité porteuse, même `ChildrenOf(Caster())`) :
   * `TheArdentBlade_InitAbility` → `AddEffect(1462, AbilityStateReference, Owner, Owner, options par
     défaut) & ActivateEffect(Owner, 1462)`. Il **ne surcharge pas `CreateTrigger`** : il prend le
     patron `OnOwnerSpecificAbilityInit(<AbilityType>)`, que le port modélise déjà par
     `ABILITY_INIT_OWNER_EFFECTS` (`engine/entities/effects/factory.py`).
     ⚠ `options` n'est PAS `null` : c'est un type valeur de 32 octets, écrit **à zéro** au site
     (options par défaut).
   * `TheArdentBlade_TriggerAbility` → le trigger et le behaviour du §1, avec les trois corrections.
2. L'inscription au registre `engine/runner/operations/triggers/dispatch/registry.py`.
3. L'utilité IA `TheArdentBlade_Geminae` (+30 adjacence au parent) — sinon le choix de cible du
   `PerformAIAttack` n'est pas fidèle. Face DÉCISION, distincte.

**Le porteur — état 3, MESURÉ** : `adeptCelestine` est **HORS POOL** (`rl_duel build --list-pool` :
`adeptCanoness`, `adeptHospitaller`, `adeptMorvenn`, `adeptRetributor` seulement). Le montage est
donc, dans l'ordre :

1. injection catalogue (`catalog_inject.write_augmented_seed_bc` + `build --seed-bc`), cf.
   `case-92` §6 ;
2. **puis** le montage relique (`--equip-relic "adeptCelestine:TheArdentBlade:<lvl>"`), avec les
   trois écritures de `case-237` — dont `TertiaryAbilityLevel >= 1` **AVANT** la normalisation, et
   la config d'ability dans `BC.Abilities.PassiveAbilities` (la config de `TheArdentBlade` est
   **absente** du seed local : `data/seed-bc.json` porte 194 `PassiveAbilities`, aucune « Ardent »).
3. le summon `adeptSmnGeminaeSuperia` **s'observe, ne se commande pas** (#291) : ses actions sont
   dans les events du cast du summoner, ou au `PlayAutomaticUnits` du turn-start suivant.

⚠ **La valeur des trois constantes (`unitId`, `range`, `hp`) n'est PAS vérifiable hors ligne** — la
config d'ability des reliques n'est pas dans `data/seed-bc.json`. Le `'adeptSmnGeminaeSuperia'` de
l'énoncé est **plausible mais NON LU** ; il exige un dump gameconfig ou un `catalog_inject`.
L'unité, elle, existe bien dans le seed (Sisterhood, traits `Imperial`/`Summon`/`Flying`).

---

## 6. Inventaire exhaustif des symboles `TheArdentBlade` du build

11 entrées, identiques côté ghidra et frida — rien d'autre que ce qui est cité ci-dessus :

| Symbole | Rôle |
|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheArdentBlade_InitAbility$$CreateBehaviour` | (a) |
| `...TheArdentBlade_TriggerAbility$$CreateTrigger` | (b) |
| `...TheArdentBlade_TriggerAbility$$CreateBehaviour` | (c) |
| `IdunBattle.AI.Utilities.TheArdentBlade_GeminaeUtility$$.ctor` / `$$EvaluateAttackInSteps` (+ itérateur) | face DÉCISION |
| `IdunBattle.View.AbilityConfigs.Loki.TheArdentBladeVisuals$$ExecuteInternal` (+ itérateur) | couche vue, hors périmètre |

Aucun `$$.ctor` propre aux deux classes d'ability, donc **aucun `TargetingOptions`** — et c'est
structurel, pas une absence de symbole : `get_TargetingOptions` n'est déclaré que par
`IdunBattle.Entities.Abilities.AActiveAbility`, or les deux classes dérivent de
`BaseTriggeredAbility`, qui n'a aucun membre de ce nom. La règle « masque de ciblage dans le même
commit » ne s'applique pas (elle vise `ABILITY_CLASSES`, côté actives).
