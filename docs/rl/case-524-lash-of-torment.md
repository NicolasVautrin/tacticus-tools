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

### `#524-r1` — le bond des ENFANTS d'un effet COMPOSITE n'est pas propagé — **FERMÉ (2026-08-07)**

Mesuré : le natif propage `bondedEntityId` aux **trois** sous-effets de `TauntedEffect`
(`25 Taunted_BlockMovement`, `26 Taunted_CantUseAbility`, `1237 Taunted_RefreshUnitTurnFinished`),
`bondMeasured: true` sur chacun. Le port ne le pose que sur le **parent** 27 :

```
BONDED natif={27: 81, 25: 81, 26: 81, 1237: 81}   port={27: 81, 25: None, 26: None, 1237: None}
```

**PRÉEXISTANT, pas introduit par cette tranche.** Reproduire :
`python probe_524_lash_of_torment.py --step taunt --dmin 2 --dmax 2` (ligne `BONDED enfants`).

#### Le rayon de souffle, MESURÉ (il ne s'estime pas)

La première rédaction nommait « `CrushingClaws`, `GetEmRuntz`, `OverwhelmingWrath` » — des
**abilities**, alors que le chemin est porté par des **classes d'effet**. Re-dérivé par le code :

| effets COMPOSITES du port (`sub_effects_on_apply` surchargé) | enfants | posé par un `AddBondEffect` ? |
|---|---|---|
| `Taunted_OnlySpecificTargets` (27) | 25 / 26 / 1237 | **OUI** — 4 call-sites |
| `Stunned` (1162) | 1165 / 1166 / 1167 | **NON** — aucun |

Il n'y a donc que **DEUX** composites, et **UN SEUL** est réellement concerné. `Stunned` est le
**régime dégénéré** : son bond est `None` des deux côtés, la propagation y est inerte — c'est
exactement le piège qu'un test naïf aurait pris pour un vert.

Les **4 call-sites** qui posent le composite 27 bondé, et leur confrontabilité :

| ability | porteur | voie | confronté |
|---|---|---|---|
| `1105 CrushingClaws` | `tyranTyrantGuard` | pool | `test_damage_crushingclaws_live.py` |
| `1045 GetEmRuntz` | `orksRuntherd` (summoner) | pool, taunt posé par l'enfant spawné | via son summoner |
| `1141 OverwhelmingWrath` | `worldEightbound` « Azkor » | pool | `test_overwhelming_wrath_live.py` |
| `1196 LashOfTorment` | `emperLucius` | **hors pool ET hors catalogue** → injection | `test_524_lash_of_torment_live.py` |

**4 portées, 4 confrontables** — aucune ne tombe dans « non pertinent ».

#### Ce que le décompilé dit de la STRUCTURE (et pourquoi on ne recâble rien)

`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` n'énumère pas trois poses à la main :
il alloue **UN objet de contexte**, y écrit le bond **lu du parent**, et le passe aux trois
builders —

```
ctx.<+0x10> = <abilityState de l'effet parent>
ctx.<+0x18> = IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId(this, effect)
AddSubEffectWithSameTurns(this, effect, target, new EffectBuilder(ctx, <25>),   0x19)
AddSubEffectWithSameTurns(this, effect, target, new EffectBuilder(ctx, <26>),   0x1a)
AddSubEffectWithSameTurns(this, effect, target, new EffectBuilder(ctx, <1237>), 0x4d5)
// puis la MÊME valeur `ctx.<+0x18>` alimente `ForcedAttackTargetsComponent` de la cible
```

`IdunBattle.Entities.Effects.BaseEffect$$AddSubEffectWithSameTurns` ne transporte, lui, que
`{ turns = <EffectComponent du parent>.RemainingTurns, parentEffect }` — le bond **n'y passe pas**.
C'est donc l'`EffectBuilder`, via le contexte, qui pose le composant de bond de chaque enfant. Et
la valeur est **la même** que celle qui alimente les cibles forcées : le port l'avait déjà sous la
main, il ne la faisait simplement pas descendre.

⇒ le correctif est **un héritage au foyer**, pas un champ `bonded` à renseigner call-site par
call-site sur `SubEffectSpec`.

À quoi ça sert : `IdunBattle.Entities.Effects.Taunted_RefreshUnitTurnFinishedEffect$$get_Range`
rend `Nullable<int>(1)`, exactement comme `IdunBattle.Entities.Effects.TauntedEffect$$get_Range`.
Chaque enfant porte donc **son propre** gate de rupture de bond (distance au bonded), qu'un
`bonded` nul rend ininterprétable.

#### Le correctif — DEUX foyers, parce qu'il y a deux façons pour un enfant d'exister

| foyer | quand | ce qui manquait |
|---|---|---|
| `runner/operations/effects.py::AddEffectOperation._spawn_sub_effects` | POSE en simulation | l'enfant naissait sans `bonded` |
| `runner/snapshot.py::_load_effect_parent_links` | état RECONSTRUIT d'une capture | idem — et c'est **le foyer que traversent les tests live** |

Ne traiter que le premier aurait laissé la moitié du gisement, invisible : un état hydraté est
exactement ce que charge tout test live. Le second n'écrase jamais un bond déjà posé (même règle
que le `parent_type` qu'il attribue).

#### Garde et validation

`tests/engine/test_524r1_bond_sous_effets_offline.py`, **vue ROUGE avant le fix**, message verbatim :

```
#524-r1 -- le bond du composite NE DESCEND PAS a ses sous-effets. [...]
attendu {25: 81, 26: 81, 1237: 81} ; obtenu {25: None, 26: None, 1237: None}
```

Trois bras : POSE, HYDRATATION, et un bras qui **NOMME le régime dégénéré** (`Stunned` non bondé →
enfants `None`, et l'héritage ne doit pas *fabriquer* un bond). Le bras dégénéré était **vert avant
le fix** — c'est lui qui atteste que les deux rouges venaient du fond et non du montage.

Confronté LIVE (1196, `MC1_67`/777), régime **non dégénéré** (bond = id du caster, non nul) :

```
BONDED enfants natif={25: 81, 26: 81, 1237: 81}   port={25: 81, 26: 81, 1237: 81}   ACCORD
```

L'assertion est désormais **dans** `test_524_lash_of_torment_live.py` (avec témoin non nul), et le
probe **confronte** cette ligne au lieu de la commenter.

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

- Dans le bras 4 (ACCORD), les comptes de tirages divergent quand même : **natif 16, port 15**.
- Éliminés par la mesure : les effets `1516/1517 BeastSlayer_*` de la cible (le même couple accorde
  dans un runner frais), l'état de CHARGE (`charged(caster)` identique), les effets du caster
  (`[1082 Parry_ReduceHits]` dans les deux cas), la chance de crit.

---

## 4bis. `#524-r2`, deuxième passe — ce qui est TRANCHÉ, et ce qui reste

### (a) `#524-r2` et `#511-r1` sont DEUX gisements, pas un

Le « probablement le même gisement » écrit ci-dessus est **RÉFUTÉ**. Critère binaire, énoncé avant
la mesure : *en régime NOMINAL (1ᵉʳ cast, runner frais, dégâts bit-exacts), l'état MT complet
coïncide-t-il après le cast ?*

| | régime nominal | dégâts | tirages natif / port | état MT après |
|---|---|---|---|---|
| `1196` (#524-r2) | 6 coups | bit-exacts | 14/14, 15/15, 16/16 (3 runs) | **IDENTIQUE bit à bit** |
| `1225` (#511-r1) | 3 coups | bit-exacts | **8 / 13** | **DIFFÉRENT dès le 1ᵉʳ cast** |

`1225` fait **moitié moins** de coups que `1196` et écarte de **+5** ; `1196` écarte de **0**.
Une cause par-coup du vecteur ability-attack partagé produirait l'inverse. Les deux signatures
sont donc distinctes : `#511-r1` est un écart **présent dès le premier cast** (le port tire plus
que le natif, ou `dumpRng` n'expose pas tout côté natif) ; `#524-r2` n'apparaît **qu'au second**,
sur un MT dont l'état coïncidait parfaitement au premier.

Re-dérivé le 2026-08-07 : `SFTS_REPRENDRE=1 python probe_511_strike_from_the_shadows.py --step
damage --casts 3`.

### (b) La piste « le knockback consomme un tirage » est RÉFUTÉE — elle a été COMPTÉE

`probe_524 --step pull` découpe désormais les tirages du port par étage (enveloppe de
`PullUnitOneTileOperation.execute`, qui couvre TOUTE la queue commune de
`IdunBattle.Operations.DisplaceUnitOperation$$Execute`, `ApplyKnockbackTo` compris) :

| régime | pull | knockback | tirages port total (dont pull) | MT natif == port |
|---|---|---|---|---|
| d = 2 | DÉPLACE | non | 14 (**pull = 0**) | **True** |
| d = 1 | BLOQUÉ | **oui, 1708** | 14 (**pull = 0**) | **True** |

Le knockback ne coûte **aucun** tirage, ni au natif ni au port, et l'état MT coïncide dans les
**deux** régimes. Le « natif 16 / port 15 » du bras 4 ne lui est donc pas imputable — il appartient
à l'état laissé par le geste 1, comme le reste du résidu.

Lecture du décompilé qui va avec : `IdunBattle.Operations.DisplaceUnitOperation$$ApplyKnockbackTo`
= `if (!doIt || !UnitExtensions.IsTargetable(target)) return;` puis un montant lu au **slot 0xf**
de la query et une opération de dégât — aucun appel de tirage sur ce chemin.

### (c) Le résidu est ENTIÈREMENT dans le canal CRIT

Décomposition par étage : on **éteint** le canal (`--crit "0,0"` sur les `p-units`, ce qui met
`crit_enabled` à faux) et on rejoue le montage qui diverge.

| montage | crit | natif | port | séquences | MT égaux |
|---|---|---|---|---|---|
| `--amorce ability --vecteur ability --dmin 2` | défaut | 3360 | 6581 | **divergentes** | False |
| idem **`--crit "0,0"`** | éteint | **3300** | **3300** | **identiques (6/6)** | **True** |

⇒ le résidu n'est ni dans l'arbre de 1196, ni dans le pull, ni dans le knockback, ni dans le
pipeline de dégât : il est dans le **canal CRIT**, et lui seul.

Décomposition du scalaire (jamais fitté) : `crit_chance` du port vaut **41** au régime par défaut
et **15** quand la base est forcée à 0 — soit `26` (base) `+ 15`, et **15** est exactement
`gameconfig traits.ThrillSeekers.variables.thrillSeekersExtraCritChance`. Le porteur du +15 est
donc le trait `UnitTrait.ThrillSeekers` (1056) du CASTER, dont les events natifs du geste 2
montrent bien le déclenchement (`[group 21] ThrillSeekers`, `[group 22] ThrillSeekers`).

### (d) Hypothèse `HasEffect(activeOnly = 0)` — posée, mesurée, RÉFUTÉE

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility$$CreateBehaviour` est un
`If` à deux branches, et la condition les sépare exactement sur le point qui nous intéresse :

```
If( HasEffect(Owner@0x148, 0x59a, activeOnly = 0, sourceFlags = 6),
    ChangeEffectTurns(Owner, 0x59a, turns, ChangeType.Set),        // REFRESH : aucun nouveau +15
    AddStaticStatModifierEffect(Owner, 0x59a, stat 9 = CRIT_CHANCE, +15, turns, 0) )
```

`activeOnly = 0` ⇒ le natif voit l'effet **même inactif**, alors que `decisionView` DROPPE les
effets dont `IsActive` est faux. Un `Thrilled` survivant au geste 1 mais inactif aurait donc fait
prendre au natif la branche REFRESH et au port la branche ADD — exactement le +15 de trop.

**Mesuré, et c'est non** : avant le geste 2, `decisionView` rend `False`, l'état du port rend
`False`, **et `decisionView` avec `includeInactive: true` rend `ABSENT`**. L'effet n'existe pas ;
les deux côtés prennent la branche `AddStaticStatModifierEffect`, et après le cast les **deux**
portent `Thrilled` (natif `True`, port `True`).

### (e) Ce qui reste OUVERT, et le montage pour reprendre

Il reste à établir **pourquoi la chance de crit EFFECTIVE du natif est plus basse que 41 au second
cast**. Signal chiffré : sur les 6 coups du geste 2, le natif rend `Attack_DidCrit = 0` partout —
à 41 % la probabilité en est `0,59^6 ≈ 4,2 %` — alors qu'il crite au coup 0 dans **tous** les
régimes frais mesurés.

Écartés, et à ne pas re-parcourir : le knockback (b), la chance de crit du PORT (invariante à 41
entre les deux vecteurs), `ThrillSeekers` inactif (d), `BeastSlayer_*` de la cible, l'état de
charge, les effets du caster, `RelentlessMarch_DangerZone` (apparu dans un seul run, dont le
montage différait AUSSI par la distance — non retenu faute de diff propre).

Reprendre par : `python probe_524_lash_of_torment.py --step chaine --amorce ability --vecteur
ability --dmin 2 --dmax 2` (le montage reproduit à l'identique), en instrumentant le **rang du
tirage de crit** dans `AttackDamageOperation._run_hits` plutôt que son résultat — c'est le seul
étage que la mesure n'a pas encore ouvert.

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
