# case-389 — `RammingSpeed` (1059) face COMBAT : le nœud `<DSLTriggers+0x20>` est NOMMÉ, l'ability entre au registre

Clôt les résidus `#383-r1`, `#389-r1` (§5) et `#389-r2` (§6). Suites ouvertes : `#389-r3`,
`#389-r4`, `#389-r5` (§7).

## 1. Le verrou, et comment il tombe

`#383` §6 refusait de porter `RammingSpeedAbility$$ExecuteBehaviour` pour UNE raison : le `If` qui
gate les deux attaques lit `<DSLTriggers+0x20>`, un champ alloué par
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` (`new <DAT_183343468>(dsl.state@+0x10)`)
dont **la classe n'est nommée nulle part**. Le slot de metadata-usage n'a **qu'une seule xref** dans
tout le binaire — donc la classe n'est instanciée nulle part ailleurs, donc aucun
`DSLTriggers$$<X>` nommé ne la désigne.

**Verdict : `<DSLTriggers+0x20>` = `IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger`**, la
propriété DSL `OwnerIsAlive`. Trois sources indépendantes, aucune n'étant suffisante seule :

1. **GABARIT.** Le ctor pose UN champ (`+0x10`) ⇒ taille 24, parent `IdunBattle.DSL.AbilityTrigger`
   (taille 16). `data/symbols/<build>/frida/classes.tsv` en compte **23**.
2. **TYPE DU CHAMP.** L'argument est `dsl.state` (un `MatchState`), pas un sélecteur. Sur les 23,
   **21** ont un allocateur NOMMÉ (`DSLTriggers$$CanMove` → `DAT_18333f810`, `$$HasTile` →
   `DAT_183329628`, `$$IsMoving` → `DAT_1833aa4c0`, `$$IsWounded`, `$$IsEffectActive`,
   `$$IsEffectCreatedThisTurn`, `$$TriggeringAbilityIsNone`, `$$IsAbilityCountedOnlyOnce`,
   `$$IsPartialAttackAbility`, `$$CanBeDisplaced`, `$$IsSpecialActiveAbility`, …) qui leur passe un
   **SÉLECTEUR** — leur slot de classe n'est donc pas `DAT_183343468`. Restent **DEUX** classes sans
   allocateur nommé, et ce sont exactement les deux qu'`InitializeShared` alloue :
   * `IsMeleePositionAbilityTrigger` — son `ShouldTrigger` invoque le **slot d'interface 9
     d'`IBattleQuery`** SUR `this+0x10` ⇒ son champ est un **BattleQuery** = `dsl+0x28` = `<+0x18>` ;
   * `OwnerIsAliveAbilityTrigger` — son champ part en 2ᵉ argument d'`UnitExtensions$$IsAlive(unit,
     state)` ⇒ un **MatchState** = `dsl+0x10` = `<+0x20>`.
   L'appariement est FORCÉ par le type, il n'y a pas de degré de liberté.
3. **CORPS TRIVIAL DONT LE SLOT EST L'UNIQUE OPÉRANDE.** `DSLTriggers$$IsRangedPosition` est
   littéralement `AbilityTrigger$$op_LogicalNot(this+0x18)` — ce qui NOMME `<+0x18>` =
   « IsMeleePosition » indépendamment, et confirme la moitié battleQuery. (Même voie que celle qui
   avait nommé `<+0x28>` = `IsTurnOf(Owner)` : `DSLTriggers$$IsTurnOf` alloue le MÊME
   `DAT_1833ab568` avec les MÊMES arguments — reproduit ici.)

Corps du nœud (`OwnerIsAliveAbilityTrigger$$ShouldTrigger`) :

```
if (!EntityExtensions.IsUnit(entities.Owner@+0x18))  return true;
return UnitExtensions.IsAlive(entities.Owner@+0x18, this._state@+0x10);
```

Les TROIS porteurs de `<+0x20>` (xrefs du motif `<dsl+0x88>+0x20`) le placent au même endroit —
APRÈS un déplacement, AVANT l'attaque : `RammingSpeedAbility`, `SkyStrikeAbility`,
`ExemplarOfTheKauyonAbility`. C'est le gate « le porteur a-t-il SURVÉCU au déplacement ? ».

⚠ **Correction d'un mirror FAUX déjà en place** : `sky_strike_tree` écrivait
`If(IsAlive(caster) & IsAlive(target), …)` pour ce MÊME nœud. Le nœud natif est **sans opérande** et
ne teste que l'Owner. Les deux lectures coïncident sur tout montage joué (la cible ne peut pas
mourir entre le move et l'attaque), mais le conjoint `IsAlive(Target())` était inventé. Corrigé.

## 2. L'arbre porté, mirror 1:1

```
amount = RandomAmount( GetVariableForLevel(0xc = minDmg), GetVariableForLevel(0xd = maxDmg) )
prof   = GetDamageProfile(config@0x60)                                    # constants.damageProfile
ifMove = If( NOT IsAdjacent(Caster@0x48, Target@0x60, 3),
             MoveUnit(Caster@0x48, GetTileToMoveTo(), <options ZERO>) )
atk1   = AttackWithAttackDamage( Owner@0x30, Target@0x60, amount, prof,
                                 hits = GetNumberConstant(0x2f = nrOfHits), …, 2 )
atk2   = AttackWithAttackDamage( Owner@0x30, Owner@0x30,  amount, prof,
                                 hits = GetNumberConstant(0x32 = nrOfHits_2), …, 2 )
addEff = AddEffect( 0x44a = 1098 RammingSpeed_ExtraExplode, AbilityStateReference,
                    source = Owner@0x30, targets = Owner@0x30, <options ZERO> )
Execute( (ifMove + addEff) + If(OwnerIsAlive, atk1 + atk2) )              # PLAIN, pas d'ExecuteAtomic
```

**Deux surcharges homonymes résolues PAR L'ADRESSE DU CALL**, pas par le nom :

| appel | overload retenu | ce qui tranche |
|---|---|---|
| `AttackWithAttackDamage` | celui dont `hits` est un **INT** (il l'emballe lui-même en `ConstantAmount`) | le natif passe le retour d'un `GetNumberConstant` (un int) ; les deux autres surcharges de même arité prennent un NŒUD, et leurs xrefs entrantes ne contiennent pas `RammingSpeedAbility$$ExecuteBehaviour`. Elle construit `AttackDamageBehaviour` + `AttackBehaviour` ⇒ famille **ATTACK**, `native_factory="attack"`. |
| `AddEffect` | l'overload 6-args dont le dernier paramètre est une **struct d'options de 0x20 octets copiée par valeur** | l'autre 6-args prend un NŒUD de durée ; le natif zéroifie 4 qwords et passe leur adresse. Options ZERO ⇒ **aucun override de durée** (`duration_rounds=None`) et une SOURCE explicite (`Owner`). |

## 3. Les deux données de registre, LUES au ctor

```
RammingSpeedAbility$$.ctor  — forme « FLAGS DIRECTS » (7 arguments, le `range` est une struct
                              TargetingRange de 0x18 octets copiée depuis les statiques) :
    TargetingOptions..ctor(&opts, isSelfCasting = 0, range = &<TargetingRange statics>+0x18,
                           forceMeleeTarget = 1, rules = 0x4002, 0, 0)
    AActiveAbility..ctor(this, &opts, 0)          <- 0 = AbilityAttackType.DirectTargetAttack
```

* `rules = 0x4002` = `TargetMatchesDynamicRule (0x2) | TargetIsEnemy (0x4000)` — le littéral EST le
  masque (ce n'est ni la surcharge `(this, template)` ni `(this, template, additionalRules)`, dont
  les listes d'appelants ne contiennent pas ce ctor) ;
* `range` = `TargetingRange` statics `+0x18` = `RANGE_FROM_CONFIG` → `overrideRange =
  GetNumberConstant(0x16 = range)` = 5 ;
* `forceMeleeTarget = 1` = `RangedBool.False`.

`getDynamicInvalidTargetReason` est passé **nul** : le bit `0x2` consulte l'**override virtuel**
`RammingSpeedAbility$$GetDynamicInvalidTargetReason`, porté ici :

```
casterTile = casterTiles[0]
movedOrOffTile = DidMove(caster) || GetMainTile(caster) != casterTile
isAdjacent     = battleQuery.<slot 0x61>(casterTiles, target)
if (movedOrOffTile && !isAdjacent)                         return 0x10;       # CasterHasNotMoved
if (!isAdjacent) {
    if (battleQuery.<slot 0x4f>(target,1,1,1).Count < 1)   return 0x20;       # TargetHasFreeAdjacentTile
    tile = GetTileToMoveTo().SelectTile(<ctx: caster, target, casterTile>)
    if (tile != null && battleQuery.<slot 0x14>(caster, tile, 0) non vide) return 0;
    return 0x8000000;                                                        # TargetIsInRange
}
return 0;                                                  # DÉJÀ au contact -> toujours valide
```

Le test de CHEMIN (`slot 0x14`) est SUBSUMÉ côté port : `ramming_speed_tile_to_move_to` n'émet que
des tuiles issues du nœud DSL `MovableTilesInRange`, qui porte le gate d'expansion #131 depuis
`case-381-r1`. Les résidus qui restent sur ce pool (`#381-r2` `FlyPathfinder`, `#381-r3` voisinage
`evenq` vs `boardGraph.neighbours`) peuvent donc faire ACCEPTER une cible que le natif refuse.
Écart d'acceptation, jamais de refus inventé.

## 4. La confrontation LIVE

`probe_389_ramming_speed_combat_port.py` — **état + rng dumpés AVANT le cast** (recette
`probe_226r`), cinq observables comparés : tuile d'arrivée, coups sur la CIBLE, coups sur SOI,
POSE de l'effet 1098, et **les PV finaux de toutes les unités**. Montage hérité de `probe_353r1`
(greffe `orksKillaKan ← 1059`, `drive_to` + `ensure_turn`, board CHOISI).

| bras (board / seed / PV joueur) | tuile | coups cible | coups soi | pose 1098 | PV finaux |
|---|---|---|---|---|---|
| MC1_67 / 38900 / 900k | (5,7) **==** | 6 **bit-exact** | 2 **bit-exact** | oui/oui | **4/4 ==** |
| MC1_67 / 38901 / **5000** (caster TUÉ) | (5,7) **==** | 5 **bit-exact** | 2 **==** | oui/oui | **4/4 ==** |
| C1_20 / 38903 / 900k | (2,6) **==** | 4 **bit-exact** | 3 **bit-exact** | oui/oui | **4/4 ==** |
| MC1_63 / 38903 / 900k | (0,3) **==** | 4 **bit-exact** | 3 **bit-exact** | oui/oui | **4/4 ==** |
| C1_03 / 38905 / **5000** (caster TUÉ) | (3,3) **==** | 4 **bit-exact** | 2 **==** | oui/oui | **4/4 ==** |

(Tous re-joués APRÈS le rebase sur `origin/master` — dont `case-381-r1`, qui a changé le nœud
`MovableTilesInRange` sous ce port : le gate d'expansion #131 et la signature `ignore_flags` /
`ignore_units_on_tiles`. La tuile de charge est inchangée sur les 5 bras.)

**Le bras LÉTHAL est le seul canal où la POSE de 1098 est observable EN DÉGÂT**, et il clôt un
résidu de `#383` §7. `orksKillaKan` porte le trait `Explodes` : quand le contrecoup le tue, la nova
part PENDANT le cast et `ExplodesAbility$$GetDamage` lit `HasEffect(Owner, 1098)`. Mesure MC1_67 :
le voisin perd **3750** PV = **75 %** du maxPV du caster (5000) = `explodesDmg` (25) +
`extraDmgPct` (50) — donc la **branche VRAIE du `ConditionalAmount`**, jusqu'ici exercée
uniquement offline. La garde `--mutate no-effect` en mode léthal rend **1250** (25 % seuls) : le
bras DISCRIMINE.

Sept gardes adversariales, **chacune ROUGE** (le port muté DIVERGE du natif) :

| mutation | ce qu'elle ampute | ce qui diverge |
|---|---|---|
| `no-move` | la feuille `MoveUnit` | tuile, coups cible, coups soi |
| `no-self-attack` | le 2ᵉ `AttackWithAttackDamage` (= l'état d'AVANT #389) | coups soi |
| `swap-hits` | `nrOfHits_2` lu comme `nrOfHits` | coups soi |
| `gate-closed` | `<DSLTriggers+0x20>` forcé à FAUX | coups cible **et** coups soi |
| `self-attack-on-target` | le contrecoup dirigé sur la CIBLE | PV finaux |
| `no-effect` | la feuille `AddEffect` | pose 1098 |
| `no-effect` **en mode léthal** | idem, mais mesuré EN DÉGÂT | PV du voisin (1250 vs 3750) |

Gardes offline : `tests/engine/runner/test_389_ramming_speed_combat_offline.py` (13 cliquets) —
dont la **face que le live n'atteint pas** : gate FERMÉE (owner mort ⇒ aucune attaque, mais le
`MoveUnit` et l'`AddEffect`, qui sont HORS du `If`, restent), la garde structurelle « le nœud est un
`OwnerIsAlive` SANS opérande » (sur les DEUX ports, RammingSpeed et SkyStrike), et les quatre
branches de `GetDynamicInvalidTargetReason`.

## 5. Le retrait de 1098 — `On(PhaseEnd)`, dans le MÊME `applyAction` (clôt `#389-r1`)

L'entité-effet est **créée** (`Effect_SourceActiveAbility = 1059`, `Effect_SourceId = <caster>`,
`Effect_CurrentLevel = 1`) puis **retirée** avant la fin du même `applyAction`. Le mécanisme est
**`RammingSpeed_ExtraExplodeEffect$$CreateTargetTrigger` = `IdunBattleLogic.Entities.DSLTriggers$$On(
EventTriggerType.PhaseEnd = 0x3a, ownerNeedsToBeAlive: false)`**, couplé à
`$$CreateTargetTriggerBehaviour` = `IdunBattle.Entities.Effects.BaseEffect$$GetRemoveEffectBehaviour`
= `IdunBattleLogic.Entities.DSLBehaviors$$RemoveEffect(entities@+0x38 = Effect)`.

### 5.1. Pourquoi il n'était pas nommé : **quatre corps DÉDUPLIQUÉS**

La classe n'a **aucune méthode à son nom** dans `frida/methods.tsv` ni dans `ghidra/functions.tsv` —
seulement son `.ctor`. Ses quatre overrides ont des corps triviaux que IL2CPP partage avec d'autres
classes, et la table n'en garde qu'**un seul propriétaire** (CLAUDE.md, « l'absence d'une méthode
dans les tables ne prouve RIEN »). Un `search_symbols_by_name` sur `RammingSpeed` ne les voit donc
jamais.

Ce qui les rend tous : le **bloc de 5 entrées consécutives du type** dans la table de pointeurs de
méthodes IL2CPP, délimité par son `.ctor` en tête et par le `.ctor` du type suivant (`HealAbility`).

| # | corps (propriétaire DÉDUPLIQUANT) | ce que le corps FAIT | slot |
|---|---|---|---|
| 1 | `RammingSpeed_ExtraExplodeEffect$$.ctor` | `BaseEffect..ctor(&abilityOrEffect, hasAutomaticActivation: 1)` | `.ctor` |
| 2 | `WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateActiveCondition` | `return dsl.triggers@+0x40` | `CreateActiveCondition` |
| 3 | `WhisperingWebEffect$$CreateTargetSelector` | `return dsl.entities@+0x30` = **Owner** | `CreateTargetSelector` |
| 4 | `UntilOfEndPhaseEffect$$CreateRemoveEffectTrigger` | `DSLTriggers$$On(0x3a, false)` | `CreateTargetTrigger` |
| 5 | `MV71SniperDroneSquad_ResetInitialDmgEffect$$CreateTargetTriggerBehaviour` | `BaseEffect$$GetRemoveEffectBehaviour(this)` | `CreateTargetTriggerBehaviour` |

L'appariement position ↔ slot est **CALIBRÉ** sur `IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect`,
dont les quatre overrides sont NOMMÉS : son bloc donne l'ordre canonique `.ctor`,
`CreateActiveCondition`, `CreateTargetSelector` (**exactement le même corps partagé**, position 3 des
deux côtés), `CreateEffectHitsBonusForAttack`, `CreateTargetTrigger`, `CreateTargetTriggerBehaviour`.
Il est recoupé par le NOM du propriétaire dédupliquant de chaque corps (qui coïncide avec la
position) et par la SIGNATURE (seul `CreateTargetTriggerBehaviour` prend 4 paramètres). Les
accesseurs d'entités sont nommés **indépendamment** par `DSLTriggers$$get_OwnerIsTarget` /
`$$get_OwnerIsActor` / `$$get_CasterIsTarget` (`AreEqual(entities+0x30, +0x60)`, etc.) :
**`+0x30 = Owner`**, `+0x38 = Effect`, `+0x40 = Actor`, `+0x48 = Caster`, `+0x60 = Target`.

⚠ Le nom `UntilOfEndPhaseEffect$$…` de l'entrée 4 est celui du **propriétaire dédupliquant**, pas le
slot de ce type : `RammingSpeed_ExtraExplodeEffect` hérite **directement** de `BaseEffect`
(`classes.tsv`), il n'est PAS un `UntilOfEndPhaseEffect`. Les deux lectures possibles de l'entrée 4
(`CreateTargetTrigger` ou `CreateRemoveEffectTrigger`) rendent de toute façon le MÊME verdict de
retrait — seule change la fonction qui assemble le `Triggered(trigger, RemoveEffect)`.

### 5.2. `0x3a = PhaseEnd`, et pourquoi il tombe DANS le même `applyAction`

`0x3a` = `IdunBattle.DSL.EventTriggerType.PhaseEnd` (58) — appariement vérifié par **deux noms de
classe** : `UntilOfEndTurnEffect` → `On(0x17 = TurnEnd)`, `UntilOfEndPhaseEffect` → `On(0x3a =
PhaseEnd)`.

L'émetteur est **`IdunBattle.Operations.EndPhaseOperation$$Execute`** (publie `0x3a`, puis
`$$ResetTileReservation` + `$$ResetEntityPhase`), atteint par
`Core.Services.OperationProcessor$$EndPhase` — qui n'a **aucun appelant direct** dans le binaire,
seulement le slot appelé par `IdunBattle.Messages.InputMessageProcessor$$RunPhase` dans sa branche
`isInternalPhase == false`. Or `RunPhase` **est** le corps d'un `applyAction` : les
`InputMessageProcessor$$Visit` (un par type de message d'entrée) l'appellent avec `isInternalPhase =
0` (lu sur le `Visit` d'AddUnit : `RunPhase(this, 0x4, action, 0, 0)`), tandis que la cascade interne
`$$ProcessPendingTriggeredAbilities` l'appelle avec `RunPhase(this, 0xf, action, 1, 0)`.
**Une phase = un message top-level**, et sa clôture émet `PhaseEnd`.

### 5.3. Le mirror

* `runner/operations/triggers/dispatch/phase.py` — vecteur `phase_end_triggers`, mirror de la
  publication `0x3a` d'`EndPhaseOperation$$Execute`, émis **en sortie de `Runner.apply`** (qui
  portait déjà `state.reset_trigger_phases()`, l'AUTRE geste de la même opération native).
* `runner/operations/triggers/loki/ramming_speed.py` — `EFFECT_TRIGGERS[1098]`.
* `probe_389` : son chemin port passe désormais par **`Runner.apply(ActiveAbilityMessage)** et non
  par `AbilityHandler.visit_ActiveAbilityMessage` appelé nu — le handler nu exécute le même arbre
  (même tuile, mêmes coups, vérifié) mais court-circuite la borne de phase, ce qui rendrait
  `effect_persists_port_only` VRAI par construction.

⚠ **Piège de CANAL, mesuré** : `decisionView` par DÉFAUT laisse tomber les effets INERTES ; seul
`snapshot.decision_view_seed_body` (`includeInactive`) est comparable à `State.effects.by_unit`.
Le premier jet du probe croisait les deux canaux et voyait un faux écart (`PowerTrip_FullHealth`
1362 « disparu » alors qu'il était seulement désactivé — il a bien un `CreateActiveCondition`
(`!IsDamaged`), et **aucun** `RemoveEffect` : c'est ce qui le sépare de 1098, à couple d'événements
de vue identique `LoseEffect (16)` / `DeactivateEffect (18)`).

### 5.4. Ce que la mesure rend

| bras | 1098 après le cast, natif | 1098 après le cast, port |
|---|---|---|
| MC1_67 / 38900 | absent (`[1026, 1361, 1362]`) | absent (`[1026, 1361, 1362]`) |
| C1_20 / 38903 | absent | absent |
| MC1_63 / 38903 | absent | absent |
| MC1_67 / 38901 **léthal** | `[]` (mort → tous retirés) | `[1026, 1098, 1361, 1362]` — cf. §6 |
| C1_03 / 38905 **léthal** | `[]` | `[1026, 1098, 1361, 1362]` — cf. §6 |

Sur un bras non léthal le natif retire 1098 **alors que 1026/1361/1362 RESTENT** : c'est bien le
trigger propre à 1098, pas un nettoyage global.

**Huitième garde adversariale, `--mutate keep-effect`** (vide `EFFECT_TRIGGERS[1098]` = l'état
d'avant) : le port muté rend `[1026, 1098, 1361, 1362]` là où le natif rend `[1026, 1361, 1362]` —
**ROUGE**. Gardes offline : 5 cliquets de plus dans
`tests/engine/runner/test_389_ramming_speed_combat_offline.py` (18 au total), dont le **régime qui
mord**, bout en bout : une nova survenant APRÈS le cast lit `explodesDmg` seul (25 % du maxPV =
**25000**) au lieu d'`explodesDmg + extraDmgPct` (75 % = **75000**).

**Deuxième résidu, GÉNÉRIQUE au pipeline d'attaque** (pas propre à 1059) : quand un coup TUE le
défenseur, le tag `Amount` natif porte le dégât RÉELLEMENT appliqué (borné par les PV restants) et
la série S'ARRÊTE ; le port continue la boucle et rapporte le montant BRUT. **L'ÉTAT est identique
des deux côtés** (`HealthComponent.reduce` borne à 0) — seule la TRACE diffère. Le probe convertit
donc la série roulée du port en série RAPPORTÉE (`_as_reported`, transformation définie, aucun degré
de liberté) : sur C1_03 léthal, port `[3105, …]` roulé → `[3105, 1895]` rapporté == natif.

## 6. La mort vide TOUS les effets — `KillUnitOperation$$RemoveEffects` (clôt `#389-r2`)

**Question binaire : quand une unité MEURT, quels effets restent attachés à elle ?**
Réponse native : **aucun**. Le port en gardait la totalité sauf un volet étroit.

### 6.1. Trois appels, un `KillUnitStep` chacun

`IdunBattle.Operations.KillUnitOperation$$Execute` appelle **trois fois**
`IdunBattle.Operations.KillUnitOperation$$RemoveEffects(killed, step)` (signature lue dans
`frida/methods.tsv`), un par valeur de **`IdunBattle.Operations.KillUnitStep`** =
`0=PreUnitRemove, 1=AfterUnitRemove, 2=AfterDeathTrigger` (dump d'enums, build `rnca9r7q6c`).
L'adaptateur emballe le `step` dans un `Nullable<KillUnitStep>`, met à 0 le second champ des
options, et appelle le **slot 0x5a** de `Core.Services.OperationProcessor` →
`IdunBattle.Operations.RemoveEffectsOperation$$Execute`.

Séquence complète, ré-dérivée au décompilé (offsets = adresses de RETOUR des call-sites,
relatives à `KillUnitOperation$$Execute`) :

```
+0x505  savedHp = health.hp ; health.hp = 0
+0x7cc  On(PreUnitDeath = 1)
+0x81c  GARDE REVIVE : if (!unitComponent.PendingRevive@+0xa8 .HasValue) {
+0x979      On(PreUnitDeath_2 = 2)
+0x999      unitFlags.Remove(0xf) ; +0x9ad unitFlags.Add(6 = Dead)
+0x9be      RemoveEffects(killed, PreUnitRemove = 0)          <-- STEP 0
+0xd34      processor.<slot 6>(killed,0,1) ; +0xd88 matchState.<slot 0x31>(killed)
+0xd9c      RemoveEffects(killed, AfterUnitRemove = 1)        <-- STEP 1
+0xe49      On(UnitDeath = 0)
+0xefc      On(UnitDefeated = 0x36)
+0xf35      GARDE HEAL : if (health.hp > 0) RETURN
+0xf59      RemoveEffects(killed, AfterDeathTrigger = 2)      <-- STEP 2
        } else { +0xfcc matchState.<slot 0x63>(killed) }
        unitComponent.PendingRevive@+0xa8..+0xe8 = 0
+0x10ac On(PostUnitKill = 0x35)
```

**Deux rectifications d'ordre** que ce port apporte, toutes deux lues à la profondeur d'accolades :
le retrait était émis ENTRE `On(UnitDeath)` et `On(UnitDefeated)` alors que le natif le fait AVANT
`On(UnitDeath)` ; et `On(PostUnitKill)` n'est **pas** sous la garde revive (il est après le
`if/else`) — l'ancienne docstring l'affirmait. Sans conséquence portée (aucun consommateur de
`On(53)`). La **GARDE HEAL**, elle, saute bien `On(53)` : c'est un `return`.

### 6.2. `RemoveEffectsOptions` et le prédicat DÉDUPLIQUÉ

```
+0x00  Nullable<KillUnitStep> step
+0x08  bool <non nomme>                    # 0 aux TROIS call-sites de mort -> non porte
```

`RemoveEffectsOperation$$Execute` collecte d'abord (`effectObj.<IEffect slot 4> == options.step`),
puis retire — deux boucles distinctes, ordre load-bearing. Les deux prédicats sont des slots de
`IdunBattle.Entities.Effects.IEffect` dont **le corps est un getteur constant DÉDUPLIQUÉ par
IL2CPP** : absents des deux tables de symboles, et `IEffect` ne déclare aucune méthode dans le dump.
⚠ **Hypothèse nommée** : le step par défaut est `PreUnitRemove`. Elle est **sans conséquence sur
l'observable de sortie** (les trois steps tournent dans la même opération), et ne mordrait que sur
un consommateur de `On(UnitDeath)`/`On(UnitDefeated)` qui lirait un effet du mort — il n'y en a
aucun de porté. Toute surcharge se pose en `BaseEffect.remove_on_kill_step`.

### 6.3. Le port

`runner/operations/remove_effects.py` — **foyer impératif unique**, partagé avec la feuille DSL
`RemoveEffect` (frontière #149 : le nœud déclaratif au-dessus, l'Operation en dessous) :
`remove_effect_instance` (mirror de `RemoveEffectOperation$$Execute` : gates d'idempotence
`+0x5f`/`+0x5e`, `On(0x3f)`, revert stat-mods/overrides/ability-mods, retrait d'`ActiveEffectIds`,
`On(0x40)`) et `remove_effects_operation`. `damage._kill_unit_operation` pose les trois appels et la
garde HEAL. `damage._revert_ability_modifications_of_dead` (le volet étroit) est **supprimé**.

### 6.4. La confrontation LIVE — deux natures de mort

| nature | montage | effets du mort, natif | port AVANT | port APRÈS |
|---|---|---|---|---|
| **attaque normale** | `probe_389r2` MC1_67/39100, `orksKillaKan → necroDestroyer` (PV 1) | `[]` | `[1009, 1018]` | `[]` |
| **ability + nova** | `probe_389 --seed 38901 --hp-player 5000` (le contrecoup tue le caster `Explodes`) | `[]` | `[1026, 1098, 1361, 1362]` | `[]` |
| **contrôle négatif** | `probe_389 --seed 38900` (caster VIVANT) | `[1026, 1361, 1362]` | — | `[1026, 1361, 1362]` |

PV finaux identiques sur les 4 unités dans les trois bras. Canal : `decisionView`
**`includeInactive`** (`snapshot.decision_view_seed_body`) — le seul comparable à
`State.effects.by_unit` (piège de canal mesuré en `#389-r1`).

**Troisième mesure, sur un porteur à revive** : `probe_389r2 --a-units necroWarden,ultraTitus
--target-visual ultraTitus` — Titus meurt en portant `[1324 FuelledByFury_CanRevive,
1354 FuelledByFury_BlockOverkill, 1516 BeastSlayer_ExtraDmg, 1517 BeastSlayer_ExtraBlock]`, le natif
le laisse avec `[]`. C'est cette mesure qui **corrige une assertion de test qui mesurait l'ancien
port** : `test_fuelled_by_fury_revive_requires_a_kill_live` exigeait que le marqueur 1324 reste
ARMÉ après une mort sans revive. Le marqueur est désarmé dans les deux faces, mais par deux
mécanismes distincts, et `consumed` les sépare : face POSITIVE la mort est **annulée** (aucun
`RemoveEffects`) et le marqueur est seulement DÉSACTIVÉ ; face NÉGATIVE l'instance est **retirée**.

Gardes : `--mutate no-kill-remove` de `probe_389r2` (l'état d'avant → ROUGE), le cliquet de retrait
de `probe_389` **RE-ARMÉ sur bras léthal** (`removal_checked` inconditionnel,
`dead_carrier_keeps_effects_port_only` entre dans le `match`), et
`tests/engine/runner/test_389r2_kill_unit_remove_effects_offline.py` (**10 cliquets**, dont les deux
faces que le live n'atteint pas : la garde REVIVE et la garde HEAL). Contre-épreuves des gardes
offline : `no-kill-remove` → **5 rouges**, `no-step-filter` → **2 rouges**, `no-heal-gate` →
**1 rouge** (exactement celui de la garde HEAL).

## 7. Ce qui n'est PAS couvert

* **La gate `OwnerIsAlive` FERMÉE n'est pas confrontée LIVE** : il faudrait un tir RÉACTIF
  (overwatch/piège) qui tue le charger pendant son `MoveUnit`. Elle est verrouillée OFFLINE.
* **Les résidus de pool `#381-r2` / `#381-r3`** (`FlyPathfinder`, voisinage `evenq` vs
  `boardGraph.neighbours`) mordent sur DEUX faces de 1059 : l'étage MOVE et le gate de ciblage.
  Aucun bras joué ici n'est en régime ring-saturé. (`#381-r1` lui-même est FERMÉ — le nœud DSL
  porte le gate d'expansion #131 depuis `case-381-r1`.)
* **La ventilation par `KillUnitStep` est portée en MÉCANIQUE, pas en DONNÉE** (§6.2) : le prédicat
  `IEffect` slot 4 est un getteur constant dédupliqué, illisible offline, et le défaut
  `PreUnitRemove` est une hypothèse. Inobservable en sortie de séquence de mort ; la seule voie de
  résolution serait d'invoquer le slot de vtable en live (`reference_il2cpp_methodptr_uninit_class`),
  ce qui exige un capteur neuf. **Résidu → `#389-r3`.**
* **Le second champ de `RemoveEffectsOptions`** (`+0x08`, bool) n'est pas porté : 0 aux trois
  call-sites de mort, aucun appelant porté ne l'active, slot non nommé.
* **`IdunBattle.Operations.RemoveUnitOperation$$RemoveEffects`** (le DESPAWN, étape 14 de
  `remove_unit.py`) appelle le MÊME slot 0x5a mais garde son retrait BRUT (`consumed = True` sans
  revert ni event). Écart PRÉEXISTANT, laissé tel quel : le brancher ferait fire `On(63)`/`On(64)` et
  des reverts sur les évictions/clones. **Résidu → `#389-r4`.**
* **Écart de PV, ÉTRANGER à ce cas mais mesuré ici** : sur `probe_389r2 --a-units
  necroWarden,ultraTitus --target-visual ultraTitus`, le natif inflige **45 000 PV de plus** à
  l'attaquant que le port (842 447 contre 887 447 sur 900 000). Identique **avec et sans** le fix
  (bras `--mutate no-kill-remove`), donc indépendant de `#389-r2` ; non diagnostiqué. C'est pourquoi
  `ultraTitus` est ÉCARTÉ du roster par défaut du probe. **Résidu → `#389-r5`.**
* **La branche `ownerNeedsToBeAlive: false`** du trigger de retrait n'est pas portée : le dispatch du
  port gate sur « owner vivant » (`CanGet*Trigger`). Écart identique à `UntilOfEndTurnRemove` ; il
  était observable par `#389-r2` (porteur mort dont les effets survivaient), et ne l'est plus depuis
  que la mort les retire.
* **Un seul niveau d'ability** (celui du build, rank 17) et **un seul greffon** (`orksKillaKan`) :
  1059 a ZÉRO porteur au gameconfig, donc aucune autre voie n'existe.
* **Le `2` en dernier argument des deux `AttackWithAttackDamage`** (`selectionType`) n'est pas
  modélisé séparément — même résidu que tous les autres call-sites portés.
* **`TargetsSelector$$SelectUniqueUnits`** et le flag `0x11 NotTargetable` : hors de cet arbre
  (mono-cible des deux côtés), sans objet ici.
