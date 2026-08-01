# case-366-r1 -- `1108 ReinforcedHiveNode_ExtraArmor` : un corps de condition FONDU, et une
# sur-attribution du seed qu'il a fait sortir

**Question** : porter le volet ARMURE du passif `ReinforcedHiveNode` du summon `tyranSmnWarrior`.
**Reponse mesuree** : `FixedArmor += 100 % de sa part Initial`, ACTIF un round sur deux
(`turnsStarted` PAIR). Et, au passage, un bug de FOYER PARTAGE que ce port a rendu observable :
**le seed attribuait la magnitude d'un effet capte INERTE** -- `FixedArmor` port **0** contre live
**1595** apres un `refresh_stat_modifier_effects`.

> Enums QUALIFIES : `1108` = `EffectType.ReinforcedHiveNode_ExtraArmor` (0x454) ; `1109` =
> `EffectType.ReinforcedHiveNode_ExtraBlock` (0x455) ; `1113` =
> `TriggeredAbilityType.ReinforcedHiveNode` (0x459) ; `1112` = `ActiveAbilityType.AlphaWarrior`.
> ⚠ `1113` en `EffectType` est `TunnelingHorror_PendingSummon` -- rien a voir.

## 1. La POSE

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ReinforcedHiveNodeAbility$$CreateBehaviour` :

    AddStaticStatModifierEffectToOwner(
        0x454 = 1108, statType = 0x10 = 16 FixedArmor,
        PercentageOf( StatAmount(Owner@DSLSelectors+0x30, 0x10 FixedArmor, 3 = Initial, null, 0),
                      Direct( GetNumberConstant(0x4a = extraArmorPct) ), roundingRule = 0 ),
        turns = null, isHidden = false )
  & AddStatOverrideEffectToOwner(
        0x455 = 1109, statType = 7 BlockChance,
        Direct( GetNumberConstant(0x2d = blockChance) ), turns = null )

Slots `DSLFactory` : `+0x78 Behaviors · +0x80 Formulas · +0x88 Triggers · +0x90 Selectors` ;
`DSLSelectors+0x30 = Owner`. `gameconfig.ability('ReinforcedHiveNode')` n'a **aucune** `variables` :
deux `constants`, `extraArmorPct = 100` et `blockChance = 100`. Ni niveau ni
`variablesAffectedByRarityBonus` -- le volet ARMURE est donc un **doublement exact** de l'armure de
base du porteur.

## 2. La CONDITION -- corps FONDU, et pourquoi les tables de symboles mentent ici

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ReinforcedHiveNodeAbility$$GetEffectActiveCondition` :

    AmountIsOdd( Sum( RoundsStarted(Owner@DSLSelectors+0x30), <DSLFormulas+0x20 = Direct(1)> ) )

`AmountIsOdd(a)` = `op_LogicalNot(<AmountIsEven>(a))` -> **actif ssi `turnsStarted(porteur)` est
PAIR**. `RoundsStarted` = `IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate` (somme de
`UnitComponent.turnsStarted@+0x58` sur le selecteur -- ici mono-unite), meme grandeur que
`GetStat(unit, 0xc = TURNS_STARTED)`.

**Les DEUX tables de symboles n'attribuent ce corps qu'a `ReinforcedHiveNode_ExtraBlockEffect`.**
Les lire aurait fait conclure « 1108 n'a PAS de condition active » -- et c'est FAUX. Le
discriminant employe n'est ni un nom ni une xref, c'est la **table `g_MethodPointers`, ordonnee par
CLASSE** ; deux blocs consecutifs de trois entrees, structurellement identiques :

    <bloc A>  ReinforcedHiveNode_ExtraArmorEffect$$.ctor
              <corps de CreateActiveCondition>          <- MEME adresse
              <corps de CreateTargetSelector>           <- MEME adresse
    <bloc B>  ReinforcedHiveNode_ExtraBlockEffect$$.ctor
              <corps de CreateActiveCondition>          <- MEME adresse
              <corps de CreateTargetSelector>           <- MEME adresse

Le voisin immediat (`RedemptionOfTheRisen_DamageReductionEffect`, 4 methodes nommees dans l'ordre
`.ctor · CreateActiveCondition · CreateTargetSelector · CreateEffectDamageMalusForDefense`) sert de
temoin d'ordre. Le `CreateTargetSelector` fondu est celui que les tables nomment
`IdunBattle.Entities.Effects.Loki.WhisperingWebEffect$$CreateTargetSelector`
(`return <this+0x48>->Selectors+0x30` = **Owner**). Meme patron que `DestroyTheWitch_*`.

GROUND TRUTH LIVE qui le confirme (§5) : les deux effets s'eteignent et se rallument ENSEMBLE.

## 3. DEUX classes, pas une -- 1109 reste un RESIDU

`data/symbols/<build>/frida/classes.tsv` :

    ReinforcedHiveNode_ExtraArmorEffect -> IdunBattle.Entities.Effects.StaticStatModifierEffect
    ReinforcedHiveNode_ExtraBlockEffect -> IdunBattle.Entities.Effects.StatOverrideEffect

Deux slots `Il2CppClass*`, deux `.ctor` distincts, deux lambdas d'`EffectsDatabase`
(`<InitializeEffects>b__14_135` / `..._136`). Ce n'est PAS une classe unique parametree (contraste
`..._ExtraDmgEffect$$.ctor(this, isDrone)` de #372) -> **seul 1108 est porte ici**.

`ReinforcedHiveNode_ExtraArmorEffect$$.ctor` (octets relus) :
`StaticStatModifierEffect..ctor(this, Nullable<AbilityOrEffect>(op_Implicit(0x459 = 1113)),
unitEffectType = 0, canBeImmuneTo = 0, keepOnRevive = 1, isMultiply = 0)` -> le defaut
`BaseEffect.can_be_immune_to = False` est exact.

**RESIDU `1109`** : `StatOverrideEffect..ctor(this, 0x459, 0)` -- un **override** (part 7,
`ValueOverride.SetOverride`), pas un stat-mod additif : `BlockChance` est FORCEE a 100. Le port n'a
pas de canal declaratif `overridden_stats` pilote par une `CreateActiveCondition`
(`overridden_stats()` n'est lu que par `AddEffectOperation._apply_stat_overrides`, chemin de POSE,
jamais par `refresh_stat_modifier_effects`). Le porter exige d'elargir ce driver. Observable live :
`blockChance` 100 <-> 0 au meme rythme que l'armure (§5).

## 4. La voie SUMMON, et un piege de visualId

`tyranSmnWarrior` n'est pas au pool ; son summoner `tyranWingedPrime` y est (rank 17). Un cast
d'`AlphaWarrior` (1112) sur une tuile libre le fait apparaitre.

⚠ **Le summon se PROJETTE sous le visualId `tyranNpc4Warrior`**, pas `tyranSmnWarrior`. Un probe
qui filtre sur le visualId attendu rend **zero unite** et se lit comme « pas de porteur ». Le
porteur s'identifie par ses EFFETS.

Ses stats viennent de `AlphaWarrior.variables` (`summonHp/summonDmg/summonArmor`, TOUTES dans
`variablesAffectedByRarityBonus`), pas du roster : `--hp-target`/`--hp-player` ne l'atteignent pas.
Le levier qui DISSOCIE sa magnitude est
`--unit-stat "tyranWingedPrime:AbilityVariablesMultiplierPercentage=<n>"` (§6).

## 5. GROUND TRUTH LIVE -- board `MC1_67`, seed 777, rank 17

`probe_366_r1_reinforced_hive_node.py`. Le summon apparait avec `turnsStarted = 0`.

| `turnsStarted` | live 1108 / 1109 | `fixedArmor` live | `blockChance` live |
|---|---|---|---|
| 0 | actifs | 3190 (= 1595 + 1595) | 100 |
| 1 | INACTIFS | 1595 | 0 |
| 2 | actifs | 3190 | 100 |
| 3 | INACTIFS | 1595 | 0 |
| 4 | actifs | 3190 | 100 |

`1595` = `summonArmor[L50] = 886 x 180 % (AbilityVariablesMultiplierPercentage du summoner)`. La
contribution de 1108 vaut donc EXACTEMENT la part Initial -- `extraArmorPct = 100`.

## 6. GENERALISATION -- second couple (board, seed) + regime DISSOCIE

Board `C3_01`, seed `31337`, `--unit-stat "tyranWingedPrime:AbilityVariablesMultiplierPercentage=100"`
-> part Initial **886** au lieu de 1595 (la magnitude n'est donc pas un scalaire fitte) :

    ts=0 live=True  armor 1772  port 1772  (apres refresh 1772)  initial=886  block=100
    ts=1 live=False armor  886  port  886  (apres refresh  886)  initial=886  block=0
    ts=2 live=True  armor 1772  port 1772  (apres refresh 1772)  initial=886  block=100
    ts=3 live=False armor  886  port  886  (apres refresh  886)  initial=886  block=0
    ts=4 live=True  armor 1772  port 1772  (apres refresh 1772)  initial=886  block=100

Residu opaque `CAPTURED_SOURCE` **nul** dans les deux regimes : la contribution est entierement
attribuee a l'entite-effet 1108 (validation NON circulaire -- magnitude calculee == delta natif).

## 7. LE BUG DE FOYER PARTAGE que ce port a fait sortir

`engine/entities/effects/__init__.py::stat_modifications_by_source` promettait « les effets
**actifs** » dans sa docstring et **ne filtrait rien**. Un effet capte INERTE par le canal
`decisionView { includeInactive: true }` (`active: false`) se voyait donc attribuer une magnitude
que le natif n'applique PAS ; `seed_unit_stats` compensait par un residu NEGATIF sous
`CAPTURED_SOURCE`, et le premier `refresh_stat_modifier_effects` -- qui retire la part attribuee, a
raison -- laissait ce residu negatif SEUL :

    turnsStarted = 3, live fixedArmor = 1595
      per_source AVANT refresh : {('statmod', 1108, 105, '...ExtraArmor'): 1595, 'captured': -1595}
      port APRES refresh       : 0        <- contre 1595 live

**Verite native** : `IdunBattle.Operations.RefreshEffectsOperation$$ActivateEffect` ecrit
`EffectComponent.IsActive @+0x5c = 1` (et `RefreshEffect` enchaine `UpdateEffectTargets(<cibles>)`
-> `AStatModifierEffect$$ApplyModification`), tandis que
`IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` ecrit `+0x5c = 0` **puis**
`UpdateEffectTargets(<liste VIDE>)` -> `RevertModification`. Un effet a `+0x5c == 0` n'a **aucune**
entree `ValueModification.per_source` chez sa cible.

Fix : helper `_carries_modification(eff)` (le FLAG, defaut `True` -- le canal par defaut droppe les
inertes, donc « present == actif »), applique dans `stat_modifications_by_source` **et**
`apply_effect_stat_modifications`. Blast radius : `stat_modifications_by_source` n'a qu'un appelant
(`UnitContext.from_snapshot`, deux passes) ; `apply_effect_stat_modifications` n'en a aucun. Le
filtre ne mord QUE sur les effets seedes `active: false`.

**Le trou etait latent pour les 17 classes a `CreateActiveCondition` portee qui declarent un
stat-mod** (`AnvilShield_BlockChanceBelowHealthCap`, les DEUX `ContagionsOfNurgle_ArmorReduction`,
les DEUX `DestroyTheWitch_*`, `VisionsOfHeresy_*`, `InescapableAccuracy_*`, ...) ; il n'etait
inobservable que parce qu'aucune n'avait encore ete captee INERTE dans un test.

## 8. Forme du port

`engine/entities/effects/loki/reinforced_hive_node.py` --
`ReinforcedHiveNodeExtraArmorEffect(BaseEffect)` :

* `is_active(unit_state)` = `((turns_started + 1) & 1) == 1`. Cle `turns_started` ABSENTE -> `True`
  (« present == actif », meme degradation que `DestroyTheWitch_*`).
* `get_stat_modification_stat()` = `FIXED_ARMOR (16)` -- c'est ce que lit le driver pour savoir QUEL
  stat reverter quand la condition tombe.
* `applied_stat_mods(stats_ctx)` (forme OVERRIDE d'`ApplyModification`) : la magnitude lit une STAT
  DU PORTEUR (`StatAmount(Owner, FixedArmor, Initial)`), illisible sans ctx ->
  `_round_fix64(Fraction(initial x extraArmorPct, 100), 0)` (`PercentageOf$$CalculateInternal` +
  `AAmountFormula$$RoundFix64Result` mode 0 = demi-vers-le-PAIR). `stats_ctx = None` -> `[]`
  (degradation fidele, jamais devinee).
* `reverted_stats()` = `[FIXED_ARMOR]`.

C'est la PREMIERE classe du registre a declarer `applied_stat_mods` **et** a surcharger
`is_active` -- exactement ce que le discriminant `_active_condition_is_ported` (#417) autorise. Le
skip du driver porte sur la CLE de pose (`stat_mod_source`), pas sur la methode declaree ; l'effet
n'a AUCUN vecteur de pose OFFLINE (il arrive par le seed), donc `stat_mod_source is None` et il
reste pilote par `refresh_stat_modifier_effects`.

Deux clefs `turns_started` ajoutees, symetriques : `runner/components.py::UnitEffectStateView`
(face COMBAT) et `playbook/scene.py::Scene.unit_state` (face DECISION -- le compteur y etait deja
materialise dans `turns_started_by_id`).

## 9. Couverture -- et ce qui ne l'est PAS

Garde : `tests/engine/runner/test_reinforced_hive_node_live.py` (3 tests, montage ASSERTE, jamais
un skip ; il EXIGE d'avoir vu les DEUX parites). Trois contre-epreuves, mutation verifiee mordue
par `git diff --stat` a chaque fois :

| mutation | resultat |
|---|---|
| `_carries_modification` force a `True` | ROUGE (`1108 INACTIF et pourtant attribue`) |
| parite inversee (`+1` -> `+0`) | ROUGE x2 (condition ET armure : `1595 != 3190`) |
| magnitude divisee par 2 | ROUGE (`798 != 1595`) |

**NON COUVERT** :
* **`1109 ReinforcedHiveNode_ExtraBlock`** -- residu (§3). Observable live, non porte.
* La face **DECISION** de 1108 n'est pas re-derivee : la prediction lit le `fixedArmor` COURANT du
  `combatSnapshot`, qui porte deja la contribution native. La cle `turns_started` y est desormais
  posee (§8), donc le gate est LISIBLE cote Scene, mais aucun consommateur decision ne l'exerce
  aujourd'hui -- inerte, et c'est correct.
* Le porteur **npc** `tyranNpc4Warrior` (voie `passiveAbilities`) n'est pas confronte : NON
  CONFRONTE, porteur hors-jeu. Le summon suffit -- c'est la MEME classe d'effet.
* Le regime `turnsStarted` >= 5 n'est pas mesure (5 observations consecutives, parites 0/1 vues aux
  deux couples). L'alternance est structurelle (parite d'un entier), pas un motif observe.
