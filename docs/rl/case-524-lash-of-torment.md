# case-524 — `1196 LashOfTorment` (`emperLucius` « Lucius »), face COMBAT

> Tranche de la campagne de classification [case-220](case-220-classification-campaign.md)
> (§6.4 EmperorsChildren). RE ghidra sur le build `rnca9r7q6c`.

**AVANT** : 1196 était absente d'`ABILITY_CLASSES` — la DÉCISION acceptait le cast, l'EXÉCUTION
l'ignorait. 0 dégât, 0 pull, 0 taunt, **aucune erreur**. C'est le no-op silencieux du §« présent ≠
exécuté ».

**APRÈS** : arbre DSL porté, masque et attack-type au registre, confronté live coup par coup.

---

## 1. L'arbre natif, verbatim

`IdunBattleLogic.Entities.Abilities.Active.Loki.LashOfTormentAbility$$ExecuteBehaviour`. Slots de
`DSLSelectors` (`factory+0x90`, champs de la factory décalés de `0x118`) : `sel+0x48 = Caster`
(`factory+0x160`), `sel+0x60 = Target` (`factory+0x178`) ; `factory+0x78 = DSLBehaviors`,
`factory+0x80 = DSLFormulas`, `factory+0x88 = DSLTriggers`.

```
attaque = AttackWithAttackDamage( caster@0x48, target@0x60,
                                  MinMaxDamage(abilityState, isPrediction: 0),
                                  Nullable(GetDamageProfile()), GetHits(),
                                  AbilityOrEffect(abilityState), <options ZERO>,
                                  selectionType: 2 )
pull    = PullUnitOneTile( caster@0x48, target@0x60,
                           elevationDifferenceForKnockback: <Nullable NUL> )
bond    = AddBondEffect( 0x1b = 27 Taunted_OnlySpecificTargets, AbilityStateReference,
                         source = caster@0x48, targets = target@0x60,
                         bondedEntity = caster@0x48,
                         turns = TurnsFromRounds(GetVariableForLevel(0x68 = nrOfRounds)) )
taunt   = If( IsAdjacent(caster@0x48, target@0x60, selectionType: 3), bond )
queue   = IfAlive( caster@0x48, pull op_BitwiseAnd taunt )
AActiveAbility.Execute( attaque op_BitwiseAnd queue )
```

Quatre lectures qui ne se déduisent d'aucune autre ability :

- **`Execute`, PAS `ExecuteAtomic`** (callee à 2 arguments) → aucun `AtomicGroup`.
- **L'ATTAQUE PRÉCÈDE LE PULL** — `op_BitwiseAnd(attaque, IfAlive(...))`, et
  `IdunBattle.DSL.CombinedBehaviour$$Execute` exécute gauche puis droite. C'est l'**inverse** de
  `GrapnelLauncher` (1090), dont l'`ExecuteBehaviour` ouvre par le pull.
- **`IfAlive` porte sur le CASTER** (`sel+0x48`), pas sur la cible — même patron que
  `light_of_sanguinius_tree` et `loki/leading_the_charge.py`.
- **`elevationDifferenceForKnockback` est NUL** (4ᵉ argument littéral `0`), contraste avec 1090 qui
  y met `Nullable(GetNumberConstant(0x5b = knockbackRange))`.

### `6` n'est PAS un littéral de l'arbre

`IdunBattle.Entities.Abilities.AActiveAbility$$GetHits` =
`AbilityConfiguration.GetNumberConstant(config, 0x2f = nrOfHits)` — une **constante de config**,
pas une formule et pas un `Direct(6)`. Aucun `IAmountFormula` optionnel n'est lu ici (contraste avec
le champ qu'évalue `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$ExecuteTarget`). Le port
passe donc `hits_key="nrOfHits"` et **n'écrit aucun 6** ; `test_524 ::test_arbre_offline` échoue si
quelqu'un le code en dur.

### Qualification des deux ordinaux

| littéral | enum | membre | l'autre enum nommerait |
|---|---|---|---|
| `0x1b` (27) | `EffectType` | `Taunted_OnlySpecificTargets` | — |
| `0x68` (104) | `AbilityVariableType` (accesseur `GetVariableForLevel`) | `nrOfRounds` | `AbilityConstantType(104)` = `unitId` |
| `3` (`IsAdjacent`) | `IdunBattle.Entities.Enum.UnitSelectionType` | `OnlyAliveAndTargetable` | — |

Le gameconfig de 1196 porte bien un **tableau** `nrOfRounds` (1 au lvl 1..17, 2 jusqu'au 35, 3
ensuite) : c'est une VARIABLE par niveau, pas une constante — la voie confirme le nom.

## 2. Les deux données obligatoires du registre

`...LashOfTormentAbility$$.ctor` n'appelle **aucun** `IdunBattle.Core.Services.TargetingOptions$$.ctor` :
forme **STATIC-COPY**, il recopie les 0x40 octets du preset `<TargetingOptions statics>+0x140`
(les 8 qwords `+0x140..+0x178`), puis `AActiveAbility..ctor(this, &opts, 0)`.

Valeurs LUES dans le bloc de `IdunBattle.Core.Services.TargetingOptions$$.cctor` qui écrit ce preset :

| offset | champ | valeur |
|---|---|---|
| `statics+0x140` (`preset+0x00`) | `isSelfCasting` | `0` |
| `statics+0x148` (`preset+0x08`) | `range` | `<TargetingRange statics+0x18>` = `RANGE_FROM_CONFIG` |
| `statics+0x160` (`preset+0x20`) | `forceMeleeTarget` | `0` = `RangedBool.True` |
| `statics+0x168` (`preset+0x28`) | `Rules` | **`0x4002`** |

C'est le **même preset** que `astartes.py::StrikeFromTheShadowsAbility` (1225) — relu, pas hérité.
Décomposition EXHAUSTIVE de `0x4002` (`0x2 + 0x4000`, aucun bit résiduel) :

- `0x2` `TargetMatchesDynamicRule` → consulte `get_dynamic_invalid_target_reason`. La classe n'a
  **aucun** corps `GetDynamicInvalidTargetReason` (ses deux seuls symboles sont `$$.ctor` et
  `$$ExecuteBehaviour`, dans les **deux** tables) → le virtuel `+0x480` retombe sur la base, qui
  rend `0`.
- `0x4000` `TargetIsEnemy` → porté.

`RANGE_FROM_CONFIG` → `AActiveAbility$$SetConfigValuesInTargetingOptions` pose
`OverrideRange = GetNumberConstant(0x16 = range)` = **2** (== l'i2 « within range 2 »).

`ABILITY_ATTACK_TYPE[1196] = AbilityAttackType.DirectTargetAttack` — 3ᵉ argument littéral `0` du
ctor, **transcrit**, jamais déduit du profil de dégât.

## 3. Ce qui a été confronté LIVE, et ce que ça a trouvé

Porteur **hors pool ET hors catalogue** → `catalog_inject.write_augmented_seed_bc` +
`rl_duel build --seed-bc` (recette : `case-92-catalog-injection.md` §6). Board `MC1_67`, seed 777,
`--no-ai`, MT offline calé sur `dumpRng` avant chaque cast.

| régime | natif | port | verdict |
|---|---|---|---|
| 6 coups, cible d=2 (`necroWarden`) | `[2127*, 589, 507, 572, 579, 500]` | idem | ACCORD, MT égaux |
| 6 coups, cible d=2 (`orksNob`) | `[2127*, 594, 503, 528, 541, 590]` | idem | ACCORD, MT égaux |
| pull, cible d=2 | `(6,7) -> (5,7)`, d 2→1, aucun knockback | idem | ACCORD |
| pull, cible **déjà adjacente** | pas de déplacement + **knockback 1708** (7ᵉ montant) | idem | ACCORD |
| taunt, cible tirée à l'adjacence | `27 + 25/26/1237`, `remaining = 6`, `bondedEntityId = 81` | idem | ACCORD |
| taunt, branche **négative** (cible morte) | `[]` | `[]` **après correctif** | ACCORD |

`*` = crit.

Le **quirk « déjà adjacente »** est lu au décompilé et absent de l'i2 : l'arc AVANT se réduit à la
tuile du CASTER, `FindTileToPullOnce` n'applique son filtre `IsEmptyOrSteppable` que si la liste a
plus d'une tuile, donc il rend cette tuile OCCUPÉE → `IsFilled` → aucun déplacement mais un
`ApplyKnockbackTo(caster, target)`. Mesuré : **+1708** de dégât en plus des six coups.

### Le correctif que la confrontation a imposé : le `selectionType` de l'`IsAdjacent`

`probe_524 --step taunt-dead --dmin 1 --dmax 1` (cible **adjacente** tuée par le cast) :

| | natif | port avant | port après |
|---|---|---|---|
| effets posés sur la cible | `[]` | `[25, 26, 27, 1237]` | `[]` |

Le natif résout `IsAdjacent(caster, target, selectionType: 3 = OnlyAliveAndTargetable)` sur un
ensemble `B` **vide** → `!B.Any()` → faux. Le port, lui, évaluait l'adjacence du **cadavre**, qui
garde ses tuiles (`feet(cadavre) = [(6,7)]`, `IsAdjacent = True`) : il tauntait un mort.

**Le même régime à distance 2 accordait déjà des deux côtés** — l'accord y venait de la DISTANCE
(le pull est refusé sur un mort, donc la cible reste à 2), pas d'un filtre. Une garde qui n'aurait
joué que ce régime-là aurait été verte.

Correctif : `entities/triggers.py::IsAdjacent` consomme désormais son `selection_type` pour le volet
`IsAlive`, mirror de `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` :

```
if (unit == null || !EntityExtensions.IsUnit(unit))  return false;
if (selectionType == 1)  return IsAlive(unit, state);
if (selectionType == 2)  return !HasFlag(unit, 0x11 = UnitFlag.Untargetable);
if (selectionType == 3)  return IsAlive(unit, state) && !HasFlag(unit, 0x11);
return true;                                          // 0 = Any
```

**Rayon de souffle NUL, et c'est lu, pas espéré** : `OnlyTargetable` (2) n'appelle PAS `IsAlive` au
décompilé, donc les **trois** call-sites portés qui passent `2` (`runner/operations/behaviour.py`
BattleFatigue, `.../loki/narthecium.py`, `.../loki/tainted_narthecium.py`) sont inchangés, comme les
call-sites qui ne passent rien (`selection_type=None`). Re-joué : 20 + 19 + 11 + 25 tests verts.

Le volet `HasFlag(Untargetable)` reste hors de portée ici — `DslContext` ne porte ni `state` ni la
table d'effets, et le signal offline du port vit dans `ai/state_bridge.py`
(`UNTARGETABLE_EFFECT_TYPES`). C'est le reliquat de `#433-r3-r2`, désormais **réduit à ce seul volet**.

### Le mirror `UnitSelectionType`, et les trois copies à la main

Écrire `3` au call-site exigeait un membre d'enum. `IdunBattle.Entities.Enum.UnitSelectionType`
existe au build (4 valeurs) : mirror créé (`engine/entities/unit_selection_type.py`) et **inscrit au
registre de `probe_313` dans le commit qui le crée** (35 mirrors, bijection, 0 dette). Le port en
portait déjà **trois** copies à la main (`ONLY_TARGETABLE = 2` dans trois modules distincts) :
converties, value-preserving.

## 4. Résidus ouverts

### `#524-r1` — le bond des ENFANTS d'un effet COMPOSITE n'est pas propagé

Mesuré : le natif propage `bondedEntityId` aux **trois** sous-effets de `TauntedEffect`
(`25 Taunted_BlockMovement`, `26 Taunted_CantUseAbility`, `1237 Taunted_RefreshUnitTurnFinished`),
`bondMeasured: true` sur chacun. Le port ne le pose que sur le **parent** 27 :

```
BONDED natif={27: 81, 25: 81, 26: 81, 1237: 81}   port={27: 81, 25: None, 26: None, 1237: None}
```

**PRÉEXISTANT, pas introduit par cette tranche** : `entities/effects/base.py::SubEffectSpec` n'a
aucun champ `bonded`, et le chemin de création des sous-effets est PARTAGÉ par tous les composites
(`CrushingClaws` 1105, `GetEmRuntz` 1045, `OverwhelmingWrath` 1141). Le consommateur connu du bond
(`writes_forced_attack_targets` → `ForcedAttackTargetsComponent`) lit le **parent**, donc l'écart
est aujourd'hui sans effet mesuré sur le ciblage ; il est visible dans toute comparaison d'effets.
Reproduire : `python probe_524_lash_of_torment.py --step taunt --dmin 2 --dmax 2` (ligne
`BONDED enfants`).

### `#524-r2` — DEUX casts de 1196 enchaînés : le second diverge

**NON RÉSOLU.** Reproductible, chiffré, et **non localisé**.

Montage : `python probe_524_lash_of_torment.py --step chaine --amorce ability --vecteur ability
[--dmin 1 --dmax 1]` — cast 1196, `endturn`, ré-approche, cast 1196.

```
natif  [527, 583, 574, 586, 528, 562]           total 3360
port   [2151*, 2252*, 586, 528, 562, 502]       total 6581
```

Le port CRITE aux coups 0 et 1 là où le natif ne crite pas ; `port[2..4] == natif[3..5]`, donc le
flux est **décalé d'un tirage au début**. La chance de crit du port est identique dans les deux
vecteurs (`(41, 3248, True)`), donc l'écart n'est pas dans l'étage CRIT-CHANCE.

**La matrice 2×2 est ce qui borne le résidu** (même caster, même cible, même position MT, même état
de charge) :

| amorce (1ᵉʳ geste) | vecteur (2ᵉ geste) | dist | verdict |
|---|---|---|---|
| `1196` | `1196` | 2 | **DÉSACCORD** |
| `1196` | `1196` | 1 | **DÉSACCORD** |
| `1196` | attaque NORMALE | 1 | ACCORD, MT égaux |
| attaque NORMALE | `1196` | 1 | ACCORD (per-hit identique) |

⇒ il faut **les deux** : que le premier geste soit 1196 **et** que le second le soit. Le vecteur
seul est sain (bras 4), et l'état laissé par 1196 ne casse pas une attaque normale (bras 3).
L'écart vit donc dans une INTERACTION entre l'état que 1196 laisse en live et ce que
`load_state` en reconstruit, lue seulement par le vecteur ability.

Deux observations complémentaires, non refermées :

- Dans le bras 4 (ACCORD), les comptes de tirages divergent quand même : **natif 16, port 15**. Le
  natif consomme UN tirage de plus dans un cast où le **knockback** tire (régime « déjà
  adjacente ») ; sans knockback (d=2) les comptes sont égaux (14/14, 15/15, 16/16 sur trois runs).
  Piste : `ApplyKnockbackTo` consommerait un tirage que `PullUnitOneTileOperation` ne mirrore pas.
- Éliminés par la mesure : les effets `1516/1517 BeastSlayer_*` de la cible (le même couple accorde
  dans un runner frais), l'état de CHARGE (`charged(caster)` identique), les effets du caster
  (`[1082 Parry_ReduceHits]` dans les deux cas), la chance de crit.

**Ce que le test de garde couvre donc** : le régime DIRECT (un cast par runner), qui est le régime
naturel. Le régime chaîné est nommé ici, pas maquillé.

## 5. Ce qui n'est PAS couvert

- La branche négative de l'`If(IsAdjacent, bond)` **par blocage du pull** (`--step taunt-bloque`) :
  le montage exige que l'allié atteigne l'unique tuile de l'arc AVANT, ce que la géométrie
  `MC1_67`/seed 777 n'a pas permis (`rc=2`, « NON CONFRONTÉ »). La branche négative EST exercée par
  l'autre voie (cible morte, `--step taunt-dead`).
- Face DÉCISION : `IdunBattle.AI.Playbook.Loki.LashOfTormentPlaybook$$MakeDamagePredictions` — 1196
  est déjà classée famille (b) `_PREDICTION_MINMAX_RANDOM_READ`
  (`entities/abilities/active_ability.py`), qui coïncide avec le défaut. Non ré-ouvert par cette
  tranche.
- `is_melee=False` est **transcrit** du gameconfig (`attackRangeType: Ranged`) mais **inerte** dans
  les régimes mesurés : la mutation `is_melee=True` n'a pas fait bouger le bras dégât (elle fait
  rougir le bras `test_arbre_offline`, qui garde le littéral).
