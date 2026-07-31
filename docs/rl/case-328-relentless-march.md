# case-328 — `RelentlessMarchAbility` (les DEUX faces) — tranche 1 de l'inventaire #317

**Porteur** : `necroWarden` (Makhotep), HERO, **dans le pool rank 17** (vérifié :
`python rl_duel.py build --list-pool`). 5 npc `necroBoss*Warden` / `necroNpcWarden` le portent aussi
(hors jeu). Aucune injection de catalogue.

**Enums, qualifiées** :

| valeur | enum | nom |
|---|---|---|
| `0x3ec` = 1004 | **`TriggeredAbilityType`** | `RelentlessMarch` (**homonyme d'id** avec `ActiveAbilityType` 1004 `MortisRound`) |
| `0x3f3` = 1011 | `EffectType` | `RelentlessMarch_Effect` |
| `0x42c` = 1068 | `EffectType` | `RelentlessMarch_DangerZone` |
| `0x418` = 1048 | `UnitTrait` | `Stationary` |
| `0x24` = 36 | `AbilityVariableType` | `hpToRepair` |
| `0x13` = 19 / `0x20` = 32 | `EventTriggerType` | `TurnStart_Other` / `Custom` |

---

## 1. `IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility$$CreateTrigger`

```
IdunBattleLogic.Entities.DSLTriggers$$On(0x13 = TurnStart_Other, ownerNeedsToBeAlive = true)
  & <DSLTriggers+0x28>
```

L'overload d'`On` retenu est celui qui prend un **`bool`** (`On(triggerType) &
(ownerNeedsToBeAlive ? this+0x20 : this+0x70)`) — identifié par l'adresse du `call`, pas par la
signature affichée : les deux overloads homonymes ont la même. Le volet « owner vivant » (`+0x20` =
`OwnerIsAliveAbilityTrigger`) est déjà le gate `CanGet*Trigger` du dispatch porté.

### `<DSLTriggers+0x28>` n'est PAS `get_OwnerIsActor` — correction de nommage

Les deux modules qui consomment déjà ce slot (`living_metal.py`, `cursed_plague_bell.py`) le nomment
« OwnerIsActor ». **Le slot et la propriété sont deux objets différents**, et
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` les construit côte à côte :

```
this+0x28 = new <DAT_1833ab568>( DSLSelectors+0x30 = Owner, dsl+0x10 = state, 0 )
get_OwnerIsActor() = new <DAT_1833a6968>( DSLSelectors+0x30 = Owner, DSLSelectors+0x40 = Actor, 0 )
```

Deux tokens de classe distincts, deux 2ᵉˢ arguments distincts. Le token `DAT_1833ab568` est celui
qu'alloue **`IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)`** (unique instanciateur du
build) → `+0x28` = `IsTurnOf(Owner)` → `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger`.
Son `$$ShouldTrigger` résout le sélecteur, puis :
* si l'entité est un JOUEUR (`EntityExtensions$$IsPlayer`) → égalité de l'index de joueur avec celui
  du contexte ;
* sinon (une UNITÉ) → même comparaison en remontant au joueur de l'unité.

C'est exactement la sémantique que le port collapse déjà en `ev.player_id == OwnerComponent.player`
(prouvée live par `probe_203` : la regen `LivingMetal` ne fire qu'au tour du propriétaire). **Le
comportement porté est juste ; seul le NOM était emprunté.** Rien n'est renommé ici (hors périmètre) —
la correction est consignée pour que la prochaine lecture parte du bon symbole.

---

## 2. `...RelentlessMarchAbility$$CreateBehaviour(abilityState, triggerType)`

Relu verbatim, **et l'ordre des sous-arbres compte** (§3) :

```
targets = DSLSelectors.Friends( of      = Owner@DSLSelectors+0x30,
                                entities= DSLSelectors.AdjacentUnits(Owner, unique = 1,
                                                                     selectionType = 3),
                                selectionType = 3 )

v = AbilityConfiguration.GetVariableForLevel(config@this+0x20, 0x24 = hpToRepair, abilityState, 0)

if (triggerType == 0x20 = EventTriggerType.Custom)                      # <- BRANCHE
    targets = targets  op_Subtraction  DSLSelectors.HeroUnits(targets, 3)

return   DSLBehaviors.AddEffect( effectType   = 0x3f3 = RelentlessMarch_Effect,
                                 abilityState = BaseTriggeredAbility.get_AbilityStateReference(this),
                                 targets      = DSLSelectors.UnitsWithoutTrait(targets,
                                                          0x418 = Stationary, 3),
                                 turns        = Nullable<int>(1) )
       op_Addition
         DSLBehaviors.Repair( mechanic = Owner@DSLSelectors+0x30,
                              selector = targets,                        # <- SANS le filtre de trait
                              amount   = DSLFormulas.Direct(v),
                              source   = (AbilityOrEffect)(TriggeredAbilityType 0x3ec),
                              options  = RepairBehaviourOptions.ForRepair() )   # scope 0, removeEffects 1
```

* `DSLSelectors$$AdjacentUnits(origin, unique, selType)` = `Units(AdjacentTiles(origin), unique,
  selType) op_Subtraction origin` → **l'Owner est exclu de sa propre sélection**, et le sélecteur ne
  filtre AUCUNE équipe (c'est le `Friends` au-dessus qui le fait, référent = l'Owner).
* `DSLSelectors$$HeroUnits(src, selType)` **délègue littéralement** à `UnitsWithTrait(src, 0x10 =
  UnitTrait.Hero, selType)` (aucune classe dédiée).
* `RepairBehaviourOptions$$ForRepair` relue sur `rnca9r7q6c` : `+0x10 = 0` (scope), `+0x14 = 1`
  (removeEffects).
* `AbilityOrEffect$$op_Implicit` @ `181669f80` (l'overload retenu, identifié par l'adresse du `call`)
  fait `set_TriggeredAbility(Nullable<TriggeredAbilityType>(v))` → le littéral `0x3ec` est bien un
  **`TriggeredAbilityType`**, pas un `ActiveAbilityType`.
* l'overload d'`AddEffect` retenu est celui à **5 paramètres** `(effectType, abilityState, targets,
  turns:Nullable<Int32>)` (`source` passé à `0` par la fabrique) — identifié par l'adresse du `call`
  (`180e9eca0`), pas par la signature affichée : quatre overloads homonymes coexistent.

## 3. Ce que la fiche #317 disait de FAUX

> « `AddEffect(0x3f3) + Repair(Owner, UnitsWithoutTrait(Friends(AdjacentUnits(Owner)), 0x418), …)` »

**Le `UnitsWithoutTrait(0x418)` filtre la cible de l'`AddEffect`, PAS celle du `Repair`.** Lecture au
désassemblage (les deux appels, dans l'ordre) :

```
mov rdx, rbx            ; entities = rbx   = Friends(AdjacentUnits(Owner))
mov r8d, 0x418          ; trait
call DSLSelectors$$UnitsWithoutTrait
mov r14, rax            ; r14 = le résultat FILTRÉ
...
mov r9, r14             ; 4e arg d'AddEffect = targets     <- FILTRÉ
call DSLBehaviors$$AddEffect
...
mov r8, rbx             ; 3e arg de Repair  = selector     <- NON filtré
call DSLBehaviors$$Repair
```

Conséquence de jeu, et elle est observable : **un allié adjacent `Stationary` ne reçoit PAS le
+1 Mouvement, mais il est RÉPARÉ.** Un port qui aurait recopié la fiche aurait refusé la réparation
d'un allié `Stationary` — dégradation restrictive, silencieuse, et invisible sans un montage qui
place un porteur du trait.

## 4. La branche `triggerType == Custom` — REACHABILITY, mesurée

`Custom` n'arrive **jamais** par le trigger propre de l'ability (`On(TurnStart_Other)`). Le producteur
est unique et nommé :

```
IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility
   ... (*(code *)*puVar13)(plVar1, &abilityState, entities, 0x20)      # ITriggeredAbility.ExecuteBy
```

le littéral `0x20` = `EventTriggerType.Custom` y est **écrit en dur**. Cette Operation est le bout de
chaîne de `DSLBehaviors$$TriggerAbility` / `$$TriggerAbilityDelayed` → « une AUTRE ability déclenche
EXPLICITEMENT cette triggered-ability ».

**Le déclencheur existe, et c'est l'ACTIVE du même porteur** —
`IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$ExecuteBehaviour`
(`ActiveAbilityType` 1005, `necroWarden.activeAbilities`) :

```
If( DSLTriggers.ActorHasTriggeredAbility(ActiveTarget@DSLSelectors+0x48, 0x3ec),
    DSLBehaviors.TriggerAbility(entity = ActiveTarget@0x48, triggeredAbilityType = 0x3ec,
                                actor=0, caster=0, target=0, unitFeetTiles=0,
                                selectionType = 3, ignoreUnitHavingAbility = 0) )
+ AddStatOverrideEffect(GetNonCharacterFriendsSelector(...), 0x3f4, …, MinMaxDamage, …)
+ PerformAIAction(GetNonCharacterFriendsSelector(...), …)
+ RemoveEffect(…)
```

`AdaptiveStrategyAbility$$GetNonCharacterFriendsSelector(units)` = `Friends(Owner, units) −
HeroUnits(units)` : **la même soustraction que la branche `Custom`**, et elle dit ce que la branche
veut dire — quand `RelentlessMarch` est rejouée par `AdaptiveStrategy`, elle ne bénéficie qu'aux
alliés **non-Character**.

**Verdict de portage** : la branche est portée (mirror 1:1, nœud `Sub(targets, hero_units(targets))`),
mais **elle n'a aujourd'hui AUCUN appelant côté port** — `ActiveAbilityType` 1005 `AdaptiveStrategy`
n'est pas dans `ABILITY_CLASSES` (vérifié par grep : seul l'id d'enum existe). Elle devient
confrontable live le jour où `AdaptiveStrategyAbility` est portée. **Résidu NOMMÉ, pas un trou muet** :
le paramètre `trigger_type` de `relentless_march_targets` est exercé par un test unitaire hors-live,
et la face `TurnStart_Other` (la seule atteignable) est, elle, confrontée live.

## 5. La classe d'effet `IdunBattle.Entities.Effects.Loki.RelentlessMarchEffect` (1011)

Même forme OVERRIDE que `CursedPlagueBell_ExtraMoveEffect` (quatre corps natifs, deux à deux
identiques — `ApplyInternal` == `AddStatModifier`, `RevertInternal` == `RevertStatModifier`) :

```
// $$ApplyInternal == $$AddStatModifier
DSLBehaviors.ChangeStat( targets            = DSLSelectors.Entity(target),
                         stat               = Stat(1 = Movement, 5 = Modification),
                         mode               = 4 = Modify,
                         amount             = DSLFormulas.Direct(1),        // LITTÉRAL, pas GetNumberConstant
                         modificationEntity = DSLSelectors.Entity(effect),
                         selectionType      = 3, ... )

// $$RevertInternal == $$RevertStatModifier
   ... stat = Stat(1 = Movement, 6 = ResetModification), amount = <DSLFormulas+0x18> = Direct(0)
```

⚠ **Écart avec `CursedPlagueBell_ExtraMove`** : là-bas le montant vient de
`GetNumberConstant(cfg, 0xe = extraMovement)` ; **ici c'est le littéral `1`** passé à
`DSLFormulas$$Direct`. L'ability `RelentlessMarch` n'a d'ailleurs **aucune** constante au gameconfig
(`variables = {hpToRepair}` seulement) : lire un `extraMovement` inexistant aurait rendu 0 et le
+1 Mouvement aurait été silencieusement inerte.

i2 : « Gives +1 Movement to all friendly units that start their turn in an adjacent hex. Also repairs
affected Mechanical units for {hpToRepair} Health. » — « affected Mechanical » n'est PAS un sélecteur :
c'est le gate `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` de l'Operation qui écarte
les cibles non mécaniques. Le `Repair` natif vise TOUS les alliés adjacents.

**Garde anti-« effet inerte »** : un effet qui pose 0 ne casse **aucun** test par construction — il
est POSÉ, visible dans `decisionView`, et sans conséquence. `test_rm_effect_grants_exactly_one_movement`
l'attrape par les deux bouts : il mesure le **ΔMOVEMENT natif** (`combatSnapshot`, `GetStat`) sur
chaque porteur de 1011 (**+1**, mesuré 3/3 tours × 3 unités) et vérifie côté port que
`applied_stat_mods` rend `[(MOVEMENT, 1)]` — donc **rouge immédiat** si quelqu'un transposait le
`GetNumberConstant(extraMovement)` du voisin (`ability_var("RelentlessMarch", "extraMovement",
is_constant=True)` rend `None`, ce que le test assère aussi, pour que sa propre prémisse reste vraie).

## 6. Le gate `EntityCanBeRepaired` MORD-il ? — OUI, deux fois

Contrairement à `LivingMetal` (gate tautologique : porter `LivingMetal` implique `IsMechanical`), ici
la cible n'est PAS le porteur :

* `UnitExtensions$$IsAffectedByHealType(target, 1)` = `HasTrait(0x421 AffectedByHealAndRepair) ||
  IsMechanical(target)` — un allié adjacent **organique** (`astraBullgryn` : `Hero`, `BigTarget`)
  reçoit le +1 Mouvement et **rien** en PV ;
* `IsDamagedUnit(target)` — un allié adjacent à PV pleins n'est pas réparé ;
* `!IsMachine(target)` — une Machine of War adjacente n'est jamais réparée (et, étant `Stationary`,
  ne reçoit pas non plus l'effet).

## 7. Confrontabilité et forme du port

`RelentlessMarchAbility` dérive de `IdunBattle.Entities.Abilities.BaseTriggeredAbility`
(`data/symbols/rnca9r7q6c/frida/classes.tsv`, taille 96), **pas** d'`AActiveAbility` — malgré le
namespace `Abilities.Active.Loki`. C'est donc un **PASSIF triggered** : il entre dans
`ABILITY_TRIGGERS` (clé = `units.passiveAbilities` = `RelentlessMarch`), **pas** dans
`handler.ABILITY_CLASSES`. Corollaire : ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne
s'appliquent (les deux règles de non-régression du CLAUDE.md portent sur `ABILITY_CLASSES` ;
`probe_181` / `probe_120` le vérifient — aucune entrée ajoutée).

Doctrine #149 : `CreateBehaviour` → **arbre DSL** (`Seq(AddEffect(UnitsWithoutTrait(...)),
Repair(...))`, sélecteurs `AdjacentUnits`/`Friends`/`UnitsWithoutTrait`/`hero_units`/`Sub` du
vocabulaire EXISTANT — aucun nœud neuf) ; les prédicats du `CreateTrigger` sont collapsés
impérativement dans `matches`, comme `LivingMetal` et `CursedPlagueBell`.

## 8. Résidus NOMMÉS

* **branche `Custom`** — portée, sans appelant côté port tant qu'`AdaptiveStrategyAbility` (1005)
  n'est pas dans `ABILITY_CLASSES` (§4).
* **`RelentlessMarchDangerZoneAbility`** (classe native distincte, parent
  `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`, `$$GetEffectType` = `return 0x42c`)
  et `RelentlessMarchDangerZoneEffect$$CreateRangeBonusForDangerZone` : axe PRÉDICTION de zone de
  danger de l'IA, non porté (même choix que `CursedPlagueBellDangerZoneAbility`).
* **`IdunBattle.AI.Playbook.Loki.RelentlessMarchPlaybook`** (`TriggeredAbilityPlaybook<
  RelentlessMarchAbility>`, `$$CalculateMovementUtilityInStepsInternal`) : face DÉCISION, hors
  périmètre de cette tranche.
* **`unitSelectionType = 3`** (`OnlyAliveAndTargetable`) propagé à tous les sélecteurs : le port
  n'honore que le volet ALIVE — résidu partagé par tous les sélecteurs d'occupation du port.
* **`unique = true`** d'`AdjacentUnits` : sans effet observable (une unité = une position).
* **`source = AbilityOrEffect(RelentlessMarch)`** du `Repair` : l'attribution n'a aucun observable
  d'état porté (même choix que la feuille `Repair` de #299).
* **conjonction du `Repair` et de `LivingMetalRepair`** : `necroWarden` porte AUSSI le trait
  `LivingMetal`, dont le trigger part sur le MÊME `On(TurnStart_Other)`. Les deux sont portés ; le
  montage de validation choisit des cibles **Mechanical mais NON-`LivingMetal`** (Adeptus Mechanicus)
  pour que le delta de PV mesuré soit imputable au seul `RelentlessMarch`.

## 9. Validation live — MESURÉE

Probe : `python scripts/python/probe_328_relentless_march.py` — garde :
`scripts/python/tests/engine/runner/test_relentless_march_live.py` (**12 tests, 12 passés, 0 skip**).
Positions DRIVÉES, aucune dépendance aux spawns. Protocole : capture au tour ADVERSE → `endturn`
(turn-start natif) → relecture ; côté port `load_state` + `_bump_turns_started` +
`turn_start_other_triggers`. `applyAction` ne fait pas jouer l'IA ⇒ **aucun bruit adverse**.

### Montage A — `--seed 777 --board C1_75 --turns 3`, **3 tours, 0 désaccord**

| unité | rôle | effet 1011 | ΔPV live / port | ΔMOVEMENT natif |
|---|---|---|---|---|
| `necroWarden` | porteur, dist 0 | non | — | 0 |
| `admecRuststalker` | allié Mechanical, ENDOMMAGÉ, dist 1 | oui, `remaining = 1` | **+1996 / +1996** (T3 : +1544, saturation `FillUp`) | **+1** |
| `astraBullgryn` | allié ORGANIQUE, ENDOMMAGÉ, dist 1 | oui, `remaining = 1` | 0 / 0 — gate `IsAffectedByHealType` | **+1** |
| `admecDominus` | allié Mechanical, PV PLEINS, dist 1 | oui, `remaining = 1` | 0 / 0 — gate `IsDamagedUnit` | **+1** |
| `admecManipulus` | allié Mechanical, dist 2 | non | — | 0 |
| `blackTerminator` | ennemi, dist 1 | non | — | 0 |

`hpToRepair[50] × 180 %` = **1996** au gameconfig — le montant natif mesuré, à l'unité.
Contrefactuels : `friends` **3/3 MORD**, `adjacent` **3/3 MORD**.

### Montage B — `--stationary`, **2 tours, 0 désaccord** : LE DISCRIMINANT DE §3

`tauShadowsun` (HERO du pool) placée sur le ring-1 du porteur caste `ExemplarOfTheKauyon` (1087)
sur la tuile légale la plus lointaine : elle se téléporte, et `tauSmnDroneCommandLink`
(`Summon`/`Flying`/**`Mechanical`** + `AddTrait(0x418)` on-appearance) naît **sur sa tuile**, donc
adjacent au porteur. Le drone est ensuite ÉGRATIGNÉ (l'ennemi, `Damage` calibré à 1500 — au-dessus
de son armure 1091, très en dessous de ses 3989 PV) puis l'ennemi est EXILÉ à 4 hex.

| observable | mesure |
|---|---|
| drone dans les porteurs de 1011 | **NON**, live ET port, 2/2 tours |
| allié adjacent non-`Stationary` dans 1011 | **OUI**, live ET port |
| **ΔPV du drone `Stationary`** | **+291 live / +291 port** — il EST réparé |
| mutation `stationary` (filtre retiré) | **MORD 2/2** (le drone entre dans 1011) |
| mutation `repairfilter` (= la faute de la fiche #317) | **MORD 1/2** (T1 ; T2 le drone est déjà à PV pleins) |
| mutation `nostationary` (filtre sur les DEUX feuilles) | **MORD 1/2**, idem |

C'est la démonstration complète : le `Stationary` adjacent **n'a pas** le +1 Mouvement **et est
réparé**. Un port conforme à la fiche #317 aurait raté cette réparation.

### Pourquoi l'ennemi est EXILÉ après l'égratignure — et ce que ça révèle

Collé au drone, l'ennemi subissait **−2490 PV au turn-start de P, côté live, 0 côté port**. Ce n'est
PAS une faute de cette tranche : c'est l'**activation AUTOMATIQUE du summon** au turn-start de sa
team (`PlayAutomaticUnits`, trait `Summon` — cf. #291), un étage **non porté**. L'éloigner isole la
mesure au lieu de la maquiller. Le désaccord est reproductible si on le remet à portée.

### Ce qui n'est PAS couvert

* **branche `Custom`** : aucun appelant côté port (§4) — exercée offline seulement
  (`test_rm_custom_branch_subtracts_heroes`), jamais live ;
* **`unitSelectionType = 3`** (volet TARGETABLE), **`unique = true`**, **`source = AbilityOrEffect`** :
  résidus §8, sans observable ;
* **activation automatique du summon au turn-start** (le −2490 ci-dessus) : étage distinct, non porté,
  hors périmètre — nommé ici pour qu'il ne soit pas re-découvert comme « bug de #328 » ;
* **`RelentlessMarchDangerZoneAbility`** et le playbook 1004 : faces DÉCISION/preview, non portées.
