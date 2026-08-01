# case-366-r1 -- `ReinforcedHiveNode` (`1108 ExtraArmor` + `1109 ExtraBlock`) : un corps de
# condition FONDU, une sur-attribution du seed, et un canal OVERRIDE qui n'avait aucun pilote

**Question** : porter les DEUX owner-effects du passif `ReinforcedHiveNode` du summon
`tyranSmnWarrior`.
**Reponse mesuree** : `FixedArmor += 100 % de sa part Initial` (1108, canal ADDITIF) **et**
`BlockChance` FORCEE a 100 (1109, canal OVERRIDE part 7), les DEUX ACTIFS un round sur deux
(`turnsStarted` PAIR). Deux bugs de FOYER PARTAGE que ces ports ont rendus observables :
**le seed attribuait la magnitude d'un effet capte INERTE** (§7 -- `FixedArmor` port **0** contre
live **1595**) et **le seed versait le delta d'un stat OVERRIDE dans le residu opaque**, qui
revenait au `RemoveOverride` (§10 -- `blockChance` port **100** contre live **0**).

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

## 3. DEUX classes, pas une -- et DEUX canaux natifs differents

`data/symbols/<build>/frida/classes.tsv` :

    ReinforcedHiveNode_ExtraArmorEffect -> IdunBattle.Entities.Effects.StaticStatModifierEffect
    ReinforcedHiveNode_ExtraBlockEffect -> IdunBattle.Entities.Effects.StatOverrideEffect

Deux slots `Il2CppClass*`, deux `.ctor` distincts, deux lambdas d'`EffectsDatabase`
(`<InitializeEffects>b__14_135` / `..._136`). Ce n'est PAS une classe unique parametree (contraste
`..._ExtraDmgEffect$$.ctor(this, isDrone)` de #372) -> **deux classes portees**.

`ReinforcedHiveNode_ExtraArmorEffect$$.ctor` (octets relus) :
`StaticStatModifierEffect..ctor(this, Nullable<AbilityOrEffect>(op_Implicit(0x459 = 1113)),
unitEffectType = 0, canBeImmuneTo = 0, keepOnRevive = 1, isMultiply = 0)` -> le defaut
`BaseEffect.can_be_immune_to = False` est exact.

`ReinforcedHiveNode_ExtraBlockEffect$$.ctor` (octets relus) tient en quatre instructions --
`xor r9d,r9d ; xor r8d,r8d ; mov edx,0x459 ; jmp <StatOverrideEffect..ctor>` -- donc
`StatOverrideEffect..ctor(this, sourceAbility = 0x459, isModifiable = 0)`. Et cette surcharge fait
litteralement `movzx edi, r8b ; ... ; mov [rbx+0x480], dil` : **`isModifiable = FALSE`** est le
champ `+0x480` que `ApplyInternal` repasse a `ChangeStat`. Consequence LUE (et non deduite) via
`ValueOverride$$GetOverrideValueWithModification` = `override + (isModifiable ? modTotal : 0)` :
tant que 1109 est actif, `BlockChance` vaut EXACTEMENT 100, aucune modification par-source ne s'y
ajoute.

Le canal, lui, est un **override** (part 7 `SetOverride` / part 8 `RemoveOverride`), pas un
stat-mod additif -- detail du port et du driver en **§10**.

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

⚠ Ce second couple DISSOCIE aussi les deux volets : la magnitude ARMURE bouge (1595 -> 886) alors
que `blockChance` reste 100/0. C'est exactement ce que la RE predit -- `blockChance` est une
CONSTANTE (`GetNumberConstant`), absente de `variablesAffectedByRarityBonus`, donc non scalee ; la
valeur du volet BLOCAGE n'est donc pas un scalaire fitte sur celle du volet ARMURE.

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

`ReinforcedHiveNodeExtraBlockEffect(BaseEffect)`, meme module :

* `is_active(unit_state)` -- STRICTEMENT le meme corps (c'est le corps FONDU, §2).
* `applied_stat_overrides()` = `[(7 BlockChance, blockChance = 100, isModifiable = False)]`. Aucun
  `stats_ctx` : les trois membres sont des DONNEES natives (`StatOverrideComponent+0x10/+0x14` et
  le `+0x480` du DEF), pas des lectures de contexte. Constante gameconfig illisible -> `[]`
  (l'effet est alors INERTE, jamais approche par une valeur inventee).
* Ni `get_stat_modification_stat` ni `applied_stat_mods` : ce n'est PAS un `AStatModifierEffect`.

## 9. Couverture -- et ce qui ne l'est PAS

Garde : `tests/engine/runner/test_reinforced_hive_node_live.py` (6 tests, montage ASSERTE, jamais
un skip ; il EXIGE d'avoir vu les DEUX parites) et
`tests/engine/runner/test_stat_override_refresh_offline.py` (7 tests, cliquet OFFLINE du canal
part 7/8). Contre-epreuves, mutation verifiee mordue par `git diff --stat` a chaque fois :

| mutation | resultat |
|---|---|
| `_carries_modification` force a `True` | ROUGE (`1108 INACTIF et pourtant attribue`) |
| parite inversee (`+1` -> `+0`) | ROUGE x2 (condition ET armure : `1595 != 3190`) |
| magnitude 1108 divisee par 2 | ROUGE (`798 != 1595`) |
| seed prive des overrides (`_overrides = None`) | ROUGE x2 (`port blockChance 100 != live 0`) |
| branche override du driver neutralisee | ROUGE x4 (live + 3 offline) |
| valeur 1109 divisee par 2 **et** `isModifiable` inverse | ROUGE x7 |

⚠ Ce que la derniere ligne a APPRIS : avec `isModifiable = True`, la valeur fausse (50) se
RECONCILIE au seed (`override 50 + CAPTURED_SOURCE 50 = 100 = live`) -- l'assertion « port ==
live » reste VERTE. Seule l'assertion sur le CANAL (slot d'override + `isModifiable`, et absence de
modification par-source) discrimine. Une confrontation de la seule valeur ne prouve donc RIEN sur
un stat overridable.

**NON COUVERT** :
* La **consequence COMBAT** de 1109 : **MESURE**, `blockDamage = 0` sur ce summon aux deux parites
  (i2 : « and - *if it has Block* - 100% Block chance »). L'entree par defaut de
  `GetMultiValueStat(7)` exige `chance > 0 ET amount > 0` (`damage.py::_block_sources`), donc
  `blockChance = 100` reste sans effet observable sur le degat pour CE porteur -- natif ET port
  sont d'accord (aucune source de block), il n'y a rien a confronter. Seule la STAT est confrontee.
  Un porteur de `StatOverrideEffect` dont l'override MORD sur un observable de degat reste a
  trouver.
* Le gate `isModifiable = False` face a une VRAIE modification par-source de `blockChance` sur le
  meme porteur : mirror OFFLINE seul (`test_non_modifiable_override_ignores_per_source_
  modifications`). Aucun montage live ne donne au summon un second modificateur de `blockChance`
  (ses stats viennent d'`AlphaWarrior.variables`, qui n'en a pas).
* La face **DECISION** des DEUX effets n'est pas re-derivee : `playbook/scene.py` appelle
  `UnitContext.from_snapshot(..., effects=None)`, donc ni l'attribution additive ni le canal
  override n'y sont seedes -- la prediction lit le `fixedArmor`/`blockChance` COURANTS du
  `combatSnapshot`, qui portent deja la contribution native. La cle `turns_started` y est posee
  (§8), donc le gate est LISIBLE cote Scene, mais aucun consommateur decision ne l'exerce
  aujourd'hui -- inerte, et c'est correct.
* Le porteur **npc** `tyranNpc4Warrior` (voie `passiveAbilities`) n'est pas confronte : NON
  CONFRONTE, porteur hors-jeu. Le summon suffit -- c'est la MEME classe d'effet.
* Le regime `turnsStarted` >= 5 n'est pas mesure (5 observations consecutives, parites 0/1 vues aux
  deux couples). L'alternance est structurelle (parite d'un entier), pas un motif observe.
* Le `StatOverrideComponent` de l'entite-effet n'est PAS publie par la capture -- **point
  d'ancrage natif a hooker si on veut la valeur A LA SOURCE** : `readStatOverride` symetrique de
  `readStatModifier` dans `frida/hooks/game/effects.ts` (champs `StatType @+0x10`, `Amount @+0x14`,
  `IsHidden @+0x18`, ecrits par `AddStatOverrideEffectBehaviour$$StatOverrideBuilder`). Exige un
  reinject -> non fait ici. En attendant, la valeur est RE-DERIVEE de gameconfig, exacte pour 1109
  (constante non scalee) et confrontee live.

## 10. Le canal OVERRIDE (part 7/8), et pourquoi c'est le MEME driver

### 10.1 Le natif ne connait pas la famille de l'effet

C'est ce qui a permis de porter 1109 sans chemin parallele. `IdunBattle.Operations.
RefreshEffectsOperation$$UpdateEffectTargets` delegue a deux fonctions qui appellent des SLOTS
D'INTERFACE, pas des methodes de famille :

    ApplyEffectsForTargets  -> IEffect+0xe = BaseEffect$$Apply  -> *(vtable+0x548) = ApplyInternal
    RevertEffectsForTargets -> IEffect+0xf = BaseEffect$$Revert -> *(vtable+0x578) = RevertInternal

Pour un `AStatModifierEffect` cela donne `ApplyModification`/`RevertModification` (`ChangeStat`
part 5|9 puis part 6) ; pour un `StatOverrideEffect` cela donne `SetOverride` (part 7) puis
`RemoveOverride` (part 8). Les deux canaux sont donc pilotes par le MEME
`RefreshEffectsOperation$$ShouldBeActive`, evalue UNE fois par effet.

`IdunBattle.Entities.Effects.StatOverrideEffect$$ApplyInternal`, relu :

    comp = <effectEntity>.GetComponent<StatOverrideComponent>()   # +0x10 statType, +0x14 amount,
                                                                  # +0x18 isHidden
    ChangeStat( Entity(target), Position(comp+0x10, part 7 = OVERRIDE), mode 4,
                Direct(comp+0x14), Entity(effect), 3, <this+0x480 = isModifiable>, comp+0x18 )

`RevertInternal` rejoue le MEME appel en `part 8`. `comp+0x14` est ecrit A LA POSE par
`IdunBattle.Entities.Behaviours.AddStatOverrideEffectBehaviour$$StatOverrideBuilder(id, statType,
amount, isHidden)` -- `amount` = le noeud `Direct(GetNumberConstant(0x2d = blockChance))` DEJA
EVALUE.

### 10.2 Ce qui a ete elargi

* **`BaseEffect.applied_stat_overrides()`** (canal DATA, cote `entities/`) -> liste de
  `(StatType, valeur, isModifiable)`. DISTINCT d'`overridden_stats()`, qui mirrore
  `MV71SniperDroneSquad_InitialDmgEffect$$ApplyInternal` : la valeur y est lue SUR LE PARENT a
  l'application, donc la classe n'y declare que des StatTypes.
* **`entities/effects/__init__.py::effect_stat_overrides`** (point de verite unique, pendant
  d'`effect_stat_modifications`) et **`stat_overrides_by_stat`** (chemin SEED, meme filtre
  `_carries_modification` que l'additif : un effet a `IsActive @+0x5c == 0` ne pose AUCUN override).
  Keye par STAT et non par SOURCE, et le dernier gagne : il n'y a qu'UN slot `ValueOverride` par
  `StatComponent` (`+0x20`) et `SetOverride` ECRASE.
* **`entities/stats.py::seed_unit_stats(overrides=...)`** -- cf. §10.3.
* **`runner/operations/refresh_effects.py`** -- la boucle applique/retire l'override sous le MEME
  verdict `active` que l'additif, et AVANT le `continue` « effet non StatModifier » (un effet
  override-only ne declare aucun stat-mod).

### 10.3 Le piege du SEED : la modification FANTOME

Le volet driver seul ne suffit PAS, et c'est le point qui aurait pu passer inapercu.
`IdunBattle.Entities.Components.StatComponent$$get_CurrentValue` rend
`override + (isModifiable ? modTotal : 0)` et **IGNORE la base**. Le chemin de seed ordinaire verse
`d = Current - Initial` dans le residu opaque `CAPTURED_SOURCE` : sur un stat OVERRIDE, cette
modification est invisible tant que l'override est la (il domine), et **revient integralement** des
que le driver joue le `RemoveOverride`. Mesure de la contre-epreuve : port `blockChance` **100**
contre live **0** au round suivant.

`seed_unit_stats` calcule donc, pour un stat override, le residu sur ce que le modele ne reproduit
pas de `Current` (et non sur `d`), et ne le verse que si `isModifiable` -- sinon un residu non nul
est IRREDUCTIBLE (l'override domine) et doit rester VISIBLE, parce qu'il signale une valeur
re-derivee FAUSSE. Le chemin sans override est inchange au caractere pres.

### 10.4 GROUND TRUTH LIVE du volet BLOCAGE

Memes runs qu'au §5/§6, colonne `blockChance` :

| `turnsStarted` | live 1108 / 1109 | `blockChance` live | slot d'override port | modification par-source |
|---|---|---|---|---|
| 0 | actifs | 100 | 100 (`isModifiable=False`) | {} |
| 1 | INACTIFS | 0 | None | {} |
| 2 | actifs | 100 | 100 | {} |
| 3 | INACTIFS | 0 | None | {} |
| 4 | actifs | 100 | 100 | {} |

Part Initial de `blockChance` = **0** aux deux parites : les 100 viennent bien de l'override, pas
d'une base. Identique sur le second couple (`C3_01` / `31337`), ou l'armure vaut pourtant 886/1772.

**La transition** (le vrai discriminant, `test_simulated_next_turn_reproduces_the_live_of_the_next_
round`) : depuis l'etat charge au round *i*, on bump `turnsStarted` (mirror du bump de
`StartTurnOperation$$Execute`) et on rejoue le driver -- le port doit rendre ce que le LIVE affiche
au round *i+1*. Trois transitions consecutives, dans les DEUX sens, sur chaque run.
