# case-175-e — l'« exclusion » des feuilles `DespoiledGround`/`Contaminated` est un gate d'IMMUNITÉ

Build `rnca9r7q6c`. Garde : `scripts/python/tests/engine/test_175e_175r_tile_meta_live.py`.

## 1. Ce que le natif fait vraiment

`case-175` §5 décrivait l'ouverture des deux corps comme
`cfg = TryGetValue(this+0x60, <EffectType>) ; if (Contains(cfg, unit)) return 0`. Les deux étages
sont **nommés**, et ce ne sont ni un `TryGetValue` ni un `Contains` :

```c
// IdunBattle.AI.Utilities.DespoiledGroundUtility.u003CEvaluateMovementInStepsu003Ed__5$$MoveNext
// IdunBattle.AI.Utilities.ContaminatedUtility.u003CEvaluateMovementInStepsu003Ed__4$$MoveNext
if (case.unit == null) yield break;
IEffect eff = <this+0x60>.GetEffect(<effectType>);      // IEffectsDatabase slot 0, 1 argument
if (eff.EntityIsImmuneToEffect(case.unit)) yield break; // IEffect slot 40, 1 argument
foreach (e in EffectsOwnedComponent(case.Position.MainTile)) { ... }
```

* `this+0x60` = le paramètre **`effectsDatabase`** du `.ctor` des deux utilities — TYPE DÉCLARÉ
  `IdunBattle.Core.Services.IEffectsQuery`, lu dans `frida/methods.tsv` ;
* les deux slots sont LUS : `IEffectsDatabase` ne déclare qu'**UNE** méthode (`GetEffect`, slot 0),
  et `IEffect` slot 40 = `EntityIsImmuneToEffect` (`metadata/interface_slots.tsv`). Le slot 0
  d'`IEffectsQuery`, lui, est `GetEffectTargetingEntity` (**2** arguments) — c'est ce qui établit
  que l'appel passe par l'interface `IEffectsDatabase`, pas par celle du type déclaré ;
* `BaseEffect$$EntityIsImmuneToEffect` = `HasTrait(entity, UnitTrait.Immune /*0x19*/) &&
  this.CanBeImmuneTo` — le virtuel est le **slot 59**, `get_CanBeImmuneTo` (l'appel décompilé lit
  `klass+0x4e8`, et `(0x4e8 - 0x138)/16 = 59`) ;
* `ContaminatedEffect$$EntityIsImmuneToEffect` **surcharge** :
  `HasTrait(0x7eb = ContagionsOfNurgle) || IsMechanical(entity) || base(entity)`.

## 2. Les deux défauts du port, et le troisième trouvé en chemin

1. **`DespoiledGroundEffect.can_be_immune_to` manquait.** La classe ne surcharge PAS
   `EntityIsImmuneToEffect` (slot 75) mais surcharge bien `get_CanBeImmuneTo` (slot 59) à **`true`**
   ⇒ le prédicat vaut `HasTrait(u, Immune)`. Le port héritait le `False` de la base : le gate rendait
   `False` **inconditionnellement**.
   ⚠ La docstring du port affirmait « les TROIS SEULS virtuels que la classe surcharge (recherche
   EXHAUSTIVE des symboles `DespoiledGroundEffect$$*`) ». La classe n'a **aucun** symbole ghidra
   (ses 4 corps sont fondus par l'ICF) : la recherche par symbole ne pouvait structurellement rien
   voir. Et le recensement runtime de #224 ne pouvait pas la voir non plus — il balayait le
   **namespace** `IdunBattle.Entities.Effects.*`, or elle vit sous
   `Idun.Source.IdunBattle.Logic.Entities.Effects`.
2. **Aucune des deux feuilles n'appelait le gate.** Côté `Contaminated`, `ctx.contaminated_excluded`
   n'était peuplé par aucun des trois constructeurs de `ctx` — et sa FORME était fausse (un booléen
   par-décision au lieu d'un prédicat à deux étages).
3. **`ContaminatedUtility` n'avait pas le gate `case.unit == null`.** Sa sœur `DespoiledGround` l'a
   depuis case-205 ; elle versait donc son `-25` sur une décision de tuile de SPAWN.

S'y ajoute un **fork** réparé : `IsMechanical` était approximé par le seul trait `Mechanical` alors
que `engine/playbook/non_owner.py::_is_mechanical` lit déjà correctement les **trois**
(`Mechanical` 5 | `LivingMetal` 0x3e8 | `Vehicle` 0x405). Sur ce build les deux ensembles coïncident
(130 unités), donc l'écart était inobservable au kit — mais `entity_trait_names` porte aussi les
traits accordés en bataille.

## 3. Comment la valeur a été lue (trois sources, et ce que chacune ne voit pas)

| source | ce qu'elle donne | angle mort |
|---|---|---|
| `global-metadata.dat` (déclarations) | qui DÉCLARE quoi, complet | ne donne pas la valeur |
| PE `methodPointers`, ancre **locale** | la valeur, alignement contrôlé sur les méthodes nommées | exige ≥ 1 corps nommé (`DespoiledGroundEffect` n'en a **aucun**) |
| PE `methodPointers`, ancre **globale** (index metadata) | la valeur pour n'importe quelle classe | exige un calage, ici corroboré par **275** méthodes nommées concordantes |

Le calage global est vérifié par des valeurs qu'on n'a pas choisies : il rend pour
`BaseEffect$$EntityIsImmuneToEffect` et `ContaminatedEffect$$EntityIsImmuneToEffect` **exactement**
les deux VA que ghidra leur attribue.

## 4. Témoin NON NUL

| régime | avant | après |
|---|---:|---:|
| `DespoiledGroundUtility`, unité `Imperial` sur tuile 1476 | −25 | −25 |
| **idem + trait `Immune`** | **−25** | **0** |
| `ContaminatedUtility`, régime SPAWN sur tuile 1244 | **−25** | **0** |
| `ContaminatedEffect.entity_is_immune_to_effect(['LivingMetal'])` | **False** | **True** |

Contre-épreuve par MUTATION : **6 mutations sur 6** font rougir la garde (dont M0 = l'état exact
d'avant-fix).

**NON COUVERT** — la confrontation du **SCORE natif** par feuille. Elle exigerait
`aiUtilityTrace`/`scorer-damage-trace`, dont les RVA sont celles de `gqfc5mff6c` et ne se
ré-arment pas sans reinject (même limite que `case-175` §6 et `case-271` §7.4). Le côté NATIF est
donc mesuré **au binaire**, pas au score.

Les 28 porteurs de `UnitTrait.Immune` du catalogue sont tous **npc** ou **summons**
(`darkaSmnWatcher` est le seul summon ; `deathBossMortarion`, `tauBossRiptide`,
`adeptBossCelestineCE`, `darkaBossLion`, `tyranBossHiveTyrantLeviathan` et les 22 power-ups sont
npc) : un montage live du terme passe donc par une injection catalogue, non faite ici.

## 5. Résidu ouvert — `#175-r2`

L'inventaire de `get_CanBeImmuneTo` re-dérivé sur la **fermeture transitive** de `BaseEffect`
(464 descendants, dont **29 hors** du namespace balayé par #224) donne **8** classes qui le
déclarent à `true` : `DespoiledGroundEffect`, `BlockTileMovementEffect`,
`BlockUnitMovementBondEffect`, `ContagionsOfNurgle_ArmorReduction_Effect`, `ContaminatedEffect`,
`PinnedEffect`, **`StunnedEffect`**, **`TauntedEffect`** (+ celles qui en héritent :
`FireEffect`, `IceEffect`, `BlockEnteringUnitsTileEffect`).

Trois d'entre elles (`StunnedEffect`, `TauntedEffect`, `BlockUnitMovementBondEffect`) sont à
`False` dans le port, et `tests/engine/runner/test_effect_immunity_live.py` **affirme** `stunned.
can_be_immune_to is False`. L'écart n'est pas corrigé ici : il change le gate de **POSE**
(`AddEffectOperation`), donc le combat, et mérite sa propre tranche avec ses propres témoins.
