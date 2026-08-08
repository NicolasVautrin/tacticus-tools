# #564 — `1039 RitesOfRestoration` : la catégorie annoncée était HEAL, la moitié bloquante était RESURRECT

`adeptHospitaller` « Isabella » (Adepta Sororitas, `lineup`, **dans le pool rank 17**). 4 porteurs
(1 lineup + 3 npc). Avant cette tranche, 1039 était un **no-op silencieux** : absente
d'`ABILITY_CLASSES`, `AbilityHandler.visit_ActiveAbilityMessage` rendait `ported: False` — 0 soin,
0 résurrection, **aucune erreur** — alors que la face DÉCISION (`RitesOfRestorationPlaybook`,
`engine/playbook/noncomparable/heals.py`) était, elle, déjà portée et **scorait le cast**.

## 1. La catégorie RÉELLE : HEAL **+ RESURRECT**

`docs/rl/combat-ability-coverage.md` classe 1039 en `HEAL`. Ce n'est pas faux, c'est **incomplet**,
et c'est la moitié manquante qui bloquait : le volet RESURRECT n'existait dans **aucun** arbre porté.

`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$ExecuteBehaviour`, lu
verbatim (`rnca9r7q6c`) :

```
heal = DSLBehaviors.Heal(healer   = selectors@+0x48 (Caster),
                         selector = GetHealTargets(),
                         amount   = DSLFormulas.ConfigVar(0x20),      # AbilityVariableType.hpToHeal
                         options  = HealBehaviourOptions.ForHeal)
res  = DSLBehaviors.Resurrect(targets   = <GetResurrectTargets, inline>,
                              tiles     = CanAddUnit(AdjacentTiles(selectors@+0x50)),
                              hp        = DSLFormulas.ConfigVar(0x1d),   # AbilityVariableType.hp
                              healType  = 0,
                              abilityType = Nullable(AbilityType.op_Implicit(abilityState)),
                              options   = false)                        # takesImmediateTurn
AActiveAbility.Execute(this, op_BitwiseAnd(heal, res))                   # `Execute` PLAIN
```

i2 mot à mot : « Heals herself and all adjacent friendly units for {hpToHeal} Health. Resurrects
{nrOfHeroes} random friendly Imperial Character and up to {nrOfSummons} random friendly Imperial
Summons that have been defeated in this battle. Resurrected units appear in free adjacent hexes with
{hp} Health **and are unable to act on this turn**. Only affects non-Mechanical units. »

**La fabrique d'options LUE est `HealBehaviourOptions$$ForHeal`** → `(scope 0, removeEffects 1)`.
Ce n'est pas `ForRegenerate` (`(1, 0)`) : `scope 1` armerait le cap de groupe de `PredictHeal` et
`removeEffects 0` supprimerait un disjunct du gate.

Les quatre lectures de config, par leur **membre nommé** (jamais l'ordinal nu) :
`ConfigVar(0x20)` = `AbilityVariableType.hpToHeal` · `ConfigVar(0x1d)` = `AbilityVariableType.hp` ·
`GetNumberConstant(0x43)` = `AbilityConstantType.nrOfHeroes` (=1) ·
`GetNumberConstant(0x10)` = `AbilityConstantType.nrOfSummons` (=2).

### Les sélecteurs, mirror 1:1

| natif | port |
|---|---|
| `$$GetHealTargets` = `Healable(caster@0x48, caster + AdjacentFriends(caster, casterTile@0x50, unique), 0)` | `sisterhood.rites_of_restoration_heal_targets` |
| `$$GetPossibleResurrectTargets` = `UnitsAffectedByHealType(UnitsWithTrait(Friends(AllDeadUnits, @0x30), 0x1a Imperial), 0)` | `..._possible_resurrect_targets` |
| `$$GetPossibleResurrectHeroTargets` = `UnitsWithTrait(possible, 0x10 Hero)` | `..._hero_targets` |
| `$$GetPossibleResurrectSummonTargets` = `UnitsWithTrait(possible, 0x2 Summon)` | `..._summon_targets` |
| `$$GetResurrectTargets` = `PickRandomly(heroes, nrOfHeroes) + PickRandomly(summons, nrOfSummons)` | `..._resurrect_targets` |

**L'ordre `heroes` PUIS `summons` est load-bearing deux fois** : il décide quelles tuiles du zip
sont consommées, et l'ordre de consommation du PRNG par les deux `PickRandomly`.
⚠ `$$GetDynamicInvalidCasterReason` additionne dans l'ordre **inverse** (`summons` puis `heroes`) —
inobservable là-bas (il ne compte que des cardinalités), transcrit tel quel.

## 2. Trois étages qui MANQUAIENT au runner, et leur mode de panne

### (a) La feuille DSL `Resurrect` n'existait pas

L'Operation `IdunBattle.Operations.ResurrectUnitOperation$$Execute` était portée
(`engine/runner/operations/resurrect.py`) mais son **unique** appelant était le trigger Ambush
genestealer. Aucune feuille DSL ne l'appelait. Ajoutée :
`engine/runner/abilities/behaviours/lifecycle.py::Resurrect`, mirror de
`IdunBattle.Entities.Behaviours.ResurrectBehaviour$$Execute` :

```
hp      = <+0x60>.Calculate(entities)                    # UNE fois, AVANT les sélecteurs
targets = <+0x50>.Select(entities)
ListExtensions.Remove(targets, t => !IsValidTarget(t))   # `u003CExecuteu003Eb__9_0`
tiles   = <+0x58>.Select(entities)
for i in 0 .. Math.Min(|targets|, |tiles|) - 1 :
    processor.ResurrectUnit(targets[i], healType, tiles[i], hp, abilityType, options)
```

C'est un **ZIP**, pas une recherche de tuile — et le pré-filtre `IsValidTarget` vit **dans la
feuille**, donc il **décale l'appariement** : une cible écartée ne consomme pas sa tuile. Le porter
en aval (dans l'Operation) donnerait le même *ensemble* de ressuscités mais pas le même
*placement*. C'est exactement ce que le test live confronte au natif.

### (b) L'Operation n'appelait NI son gate NI la branche `!options`

Même forme de panne que #520 côté heal, et elle était **invisible** : l'Operation mutait sans
jamais consulter `battleQuery.<slot 0x31>`.

* **Gate ajouté** : `IdunBattle.Core.Services.BattleQuery$$CanBeResurrected(target, healType)`,
  porté dans `engine/runner/abilities/attack_query.py::can_be_resurrected`. Il écarte
  `UnitFlag.PreventResurrect` (0x16), `UnitTrait.PermaDeath` (0x41a), une unité debout à PV > 0, et
  **le mauvais `HealType`**.
  ⚠ Sa branche `Fled` est un **OU**, pas un ET : une unité qui a fui est ressuscitable sans être
  morte — le natif court-circuite pour elle les deux tests de mort.
* **`HealType` : trois valeurs, trois abilities.** `IsAffectedByHealType` ne branche que sur `0` et
  `1`, donc `2` ne filtre RIEN. Lu call-site par call-site :
  `RitesOfRestorationAbility$$ExecuteBehaviour` → **0** (non-mécaniques) ;
  `ResurrectionOrbAbility$$GetResurrectBehaviour` → **1** (héros MÉCANIQUES) ;
  `EnvAmbushResurrectAbility$$CreateBehaviour` → **2** (aucun filtre). Le défaut de l'Operation est
  `0` ; le call-site Ambush passe donc `heal_type=2` **explicitement**, sans quoi le gate neuf
  l'aurait restreint aux non-mécaniques.
* **Branche `!options` ajoutée** : `if (!options) processor.<slot 0x23>(unit, 1)` =
  `MarkUnitAsNoActionAvailableOperation$$Execute`. C'est le « unable to act on this turn » de l'i2 ;
  1039 est le SEUL call-site porté qui la prenne (Ambush passe `true`).

### (c) Le sélecteur `Healable` n'existait pas

`IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select` = `EntityCanBeHealed(caster, u,
scope, removeEffects=1)`. Ajouté dans `engine/entities/selectors/units.py`, avec un accesseur de
contexte **distinct** de son jumeau `Repairable`.

⚠ **Asymétrie LUE, pas déduite** : `RepairableUnitsSelector` appelle la surcharge à **trois**
arguments (sans caster), `HealableUnitsSelector` la surcharge à **quatre** (il résout d'abord son
propre sélecteur de caster `+0x18`). Recopier le patron du jumeau ferait tomber le disjunct
`caster != null && HasFlag(caster, CanHealFullHealthUnits)` — le seul qui rend soignable une cible à
pleins PV.

## 3. Ce qui a été confronté LIVE, et ce qui ne l'a pas été

Montage (`probe_564_rites_of_restoration.py`) : `adeptHospitaller` reste à son spawn, `ultraCalgar`
(Hero, Imperial, non mécanique) part au contact, un tour adverse le tue. Board `MC1_67`, seed 777,
`--hp-player 300 --dmg-target 6000`.

| face | mesure | verdict |
|---|---|---|
| GATE DE CASTER, régime t0 (rien à soigner, rien à ressusciter) | natif `abilityTargets.fromHere` = `[]` ; port `get_caster_not_added_reason` = `2` | **ACCORD** |
| GATE DE CASTER, régime t1 (un mort Imperial + hex libres) | natif `[caster]` ; port `0` | **ACCORD** |
| étages du gate | `resurrect=[allié]`, `heroes=[allié]`, `summons=[]`, `tiles=[22, 30, 12]` | mesurés séparément |
| EXÉCUTION — **la tuile de réapparition** | port prédit `(1,1)` ; natif pose `(1,1)` | **ACCORD** |
| EXÉCUTION — retour à la vie et PV | natif : `alive=True`, `hp = Min(config 2493, hpMax 300) = 300` | **ACCORD** |

Le régime t0 est ce qui rend l'accord de t1 non trivial : **le natif change d'avis** entre les deux.

**NON CONFRONTÉ**, et nommé :

* le **volet SOIN** — au moment du cast, aucun allié adjacent n'était blessé (`heal targets = []`).
  La feuille `Heal` est portée et le montant lu, mais la confrontation live du montant reste à
  faire. → résidu **#564-r1** ;
* le **`no-action`** du ressuscité — le cast a terminé le tour du joueur, donc `toActivate` n'était
  plus lisible. Gardé OFFLINE (les deux bras du `if (options)`), pas confronté live.
  → résidu **#564-r2** ;
* les **gates de tuile** de l'Operation (`TilesAreOccupied`, `TilesAreWalkable`,
  `GetFeetCount != tiles.Count`, le slot `0xa5`), le `DraftingComponent`, `ResetPersistentData`,
  `ResetFeet`, `Add(0x11)` — non portés (le port pose la position directement ; `CanAddUnit` en
  amont couvre le cas nominal). → résidu **#564-r3**.

## 4. Deux pièges de MESURE rencontrés, tous deux silencieux

1. **Un mirroir `load_state` SANS board refuse TOUT.** `AdjacentTiles` rend `[]`, donc
   `CanAddUnit(AdjacentTiles(CasterTile()))` rend `[]`, donc `GetDynamicInvalidCasterReason` refuse
   **toujours** — et l'accord avec un natif qui refusait alors pour une AUTRE raison ressemblait à
   une validation. C'est l'état de la première passe du probe. `load_state(dv, ob, sn, board=...)`
   le dissout ; le test garde le non-vide de `tiles` pour que le cas ne revienne pas.
2. **`abilityTargets` et `observeBattle` n'ont pas la forme devinée.** `abilityTargets` rend
   `units[].abilities[].fromHere[].targetId` (pas `rows[]`), et `observeBattle.units[]` porte
   `squadId` **et** `entityId` — lire `id` rendait `None` partout, donc « le natif n'a rien fait »
   là où il venait de ressusciter l'unité. Un parseur qui rend `[]` sur une clé absente fabrique un
   désaccord.

## 5. Livré

* `engine/runner/abilities/sisterhood.py` — l'ability, ses 5 sélecteurs, son arbre, son
  `get_dynamic_invalid_caster_reason`, son `TARGETING_OPTIONS` (`0x8508`, forme FLAGS DIRECTS) ;
* `engine/runner/abilities/behaviours/lifecycle.py::Resurrect` — la feuille DSL ;
* `engine/runner/abilities/attack_query.py::can_be_resurrected` — le gate ;
* `engine/runner/operations/resurrect.py` — gate + branche `!options` + `heal_type` ;
* `engine/entities/selectors/units.py::Healable` + `DslContext.entity_can_be_healed` ;
* registre (`handler.py`), `ABILITY_ATTACK_TYPE` (= `Others`, 3ᵉ argument du ctor), retrait de
  `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction) ;
* `tests/engine/runner/test_564_rites_of_restoration_live.py` (5 crans) et
  `tests/engine/test_564_resurrect_pipeline_offline.py` (16 crans), **4 mutations adversariales
  vues rouges** (gate retiré · pré-filtre déplacé en aval · branche `!options` retirée · zip
  non borné).
