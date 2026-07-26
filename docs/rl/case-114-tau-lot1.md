# Case #114 — Tau lot 1 : face COMBAT de 3 abilities dont la face DECISION etait deja portee

**Statut : LIVRE.** Les 3 abilities passent de `[-D]` (decision portee, execution NO-OP) a `[CD]`
dans `kit-coverage.md`. RE ghidra `gqfc5mff6c` (decompile = verite), port DSL 1:1, confront LIVE
bit-exact des 3 (4 tests, `tests/engine/runner/test_tau_lot1_live.py`).

**Les DEUX residus de §5 sont LEVES** (§7 retrait de l'override de niveau 1180, §8 re-entree en
overwatch 1145) — 3 tests supplementaires, `tests/engine/runner/test_tau_lot1_residues_live.py`.

| ability | id | porteur | artefact natif | verdict |
|---|---|---|---|---|
| FightingRetreat | 1081 | `tauDarkstrider` (HERO) | `...Active.Loki.FightingRetreatAbility$$ExecuteBehaviour` (arbre DSL, 5 volets) | **porte + live-valide** (2 scenarios discriminants) |
| EarlyWarningOverride | 1077 | `tauCrisis` Re'vas (HERO) | `...Active.Loki.EarlyWarningOverrideAbility$$ExecuteBehaviour` (arbre DSL : 4 `AddEffect` + `Spawn`) | **porte + live-valide** |
| InspiredToGreatness | 1082 | `tauAunShi` (HERO) | `...Active.Loki.InspiredToGreatnessAbility$$ExecuteBehaviour` (arbre DSL, split canReset) | **porte + live-valide** (magnitude bit-exacte) |

Les trois artefacts natifs sont des `ExecuteBehaviour` renvoyant un **arbre de noeuds `DSLFactory`**
(kinds E/T/S/V) -> critere #149 : le port **DOIT** etre un arbre DSL. C'est le cas des trois ; les
seuls collapses sont des **selecteurs/formules S et V** (doctrine slice-18/19), listes en §5.

---

## 1. FightingRetreat (1081)

### 1.1 Arbre natif (MIRROR 1:1)

```
adjEnemies = NonSteppableOrObjectUnits( AdjacentEnemies(Owner@0x148, 1, 3), 3 )
adjFriends = NonSteppableOrObjectUnits( AdjacentFriends(Owner@0x148, 1, 3), 3 )
turns      = TurnsUntilEndOfCurrentPlayersNextTurn()
n          = adjEnemies.Count(entities)          # virtuel slot 0x18, EVALUE A LA CONSTRUCTION

Execute(
    AddEffect(0x485 = 1157 FightingRetreatDmgReduction, absRef, src=Owner@0x148, adjEnemies, turns)
  + AddEffect(0x486 = 1158 FightingRetreatHitReduction, absRef, src=Owner@0x148, adjEnemies, turns)
  + Foreach(adjEnemies,
            AddEffect(0x462 = 1122 Markerlight, absRef, src=caster@0x160, subject@0x180, turns))
  + Foreach(adjFriends op_Addition caster@0x160,
            If( HasTrait(subject@0x180, 0x424 = 1060 RangedSpecialist),
                ActivateEffect( EffectFromOwner(subject@0x180, 0x5eb = 1515 RangedSpecialist) ) ))
  + If( AmountIsGreater(Direct(n), Direct(0)), ResetTurn(Owner@0x148, 1), FinishTurn(Owner@0x148) ) )
```

- `NonSteppableOrObjectUnits(sel, 3)` = `(sel & UnitsWithoutTrait(sel, 0x1b Steppable)) &
  UnitsWithoutTrait(sel, 0xd Object)` (decompile de la factory) — helper deja porte, PARTAGE avec les
  predicats de ciblage de SquigLaunchas.
- `TurnsUntilEndOfCurrentPlayersNextTurn` = `Sum(TurnsFromRounds(1), Direct(1))` (la factory alloue
  un `TurnsFromRoundsFormula(ctx, query, 1)` + un noeud constant `1`) -> **porte comme helper nomme**
  `turns_until_end_of_current_players_next_turn` (`abilities/base.py`), consomme aussi par le
  `Stunned` d'AnvilShield (ground truth live anterieur `remaining 3`).
- Le COMPTE d'ennemis adjacents est **fige a la construction** (`Direct(n)`), pas relu a l'execution.

### 1.2 Deux canaux DISTINCTS pour le meme predicat « ennemi adjacent »

Le 5e volet (`ResetTurn`/`FinishTurn`) est **dans le behaviour**. La pose des flags de tour, elle,
vit dans la QUEUE d'`ActiveAbilityOperation` — `FightingRetreatAbility$$SetsActiveAbilityUsedFlag` =
`Direct(!Any(<ennemis adjacents>))`, deja portee (#139, `_fighting_retreat_sets_flags`). Les deux
convergent : ennemi adjacent -> `ResetTurn` + aucun flag ; aucun ennemi adjacent -> `FinishTurn` +
flags poses. MESURE LIVE : `actionConsumed=false` dans le 1er cas, `true` dans le 2e.

### 1.3 `ActivateEffect` et le modele « presence == IsActive »

`ActivateEffect(EffectFromOwner(subject, 1515))` ecrit `EffectComponent.IsActive @+0x5c = 1` (le champ
que `FightingRetreatAbility$$HasDeactivatedRangedSpecialist` LIT : `GetOwnedEffect(unit, .., 0x5eb)
!= null && effect.IsActive == 0`).

Cote port, `IsActive` n'est pas un champ stocke : le canal de seed (`readEffectsByUnit`) **DROPPE**
les effets inactifs (`if (!info.active || info.removed) continue`), donc **presence == IsActive**
(modele etabli par case-160). La feuille `ActivateEffect` rend donc l'effet PRESENT : instance deja
la -> no-op ; absente -> materialisation de l'owner-effect (meme primitive que le seed des
owner-effects de trait, `StaticBattleRules.Trait$$GetEffectToBeAddedToOwnerForTrait`).

C'est **observable et discriminant** : `RangedSpecialistEffect$$CreateHandleTriggerAbilitiesInternal`
= `On(0x12) & If(HasAdjacentEnemies, DeactivateEffect, ActivateEffect)` -> une unite qui DEMARRE son
tour au contact perd son 1515, et FightingRetreat le lui REND.

### 1.4 Cast LEGAL (gate AMONT, non porte)

`FightingRetreatAbility$$GetDynamicInvalidTargetReason` : reason 2 sauf si le caster a **>=1 ennemi
adjacent** OU si un **allie adjacent a un `RangedSpecialist` DESACTIVE**
(`HasDeactivatedRangedSpecialist`). Mesure : `abilityTargets(...).fromHere == []` au spawn (aucun
ennemi a portee) — un cast lance la rendrait `mutated:false`, indiscernable d'une ability inerte
(#111). Les deux tests prennent leur cible dans `fromHere`.

---

## 2. EarlyWarningOverride (1077)

### 2.1 Arbre natif (MIRROR 1:1)

```
unitId      = GetStringConstant(config@0x60, 0)                  # tauSmnDroneShield
nrOfSummons = GetNumberConstant(config@0x60, 0x10)               # 2
opts        = SpawnUnitOptions.WithStatsFromConfig(config@0x60, entities)
opts+0x18   = PerformAIAttackFromCurrentPosition(ActiveTarget@0x180)     # on-appearance
tiles       = First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(Owner@0x148)),
                                                  TestUnitProvider(UtilityBucket(WeightedUtility 7,
                                                                                 WeightedUtility 0x38)),
                                                  Owner@0x148 ),
                     Direct(nrOfSummons) )
Execute( Nothing()
       + AddEffect(0x3f1 = 1009 Overwatch_AutoAttack,                     snapshot, Owner, TurnsFromRounds(1))
       + AddEffect(0x478 = 1144 SuppressCloseCombatWeakness,              snapshot, Owner, ...)
       + AddEffect(0x479 = 1145 EarlyWarningOverride_ReactivateOverwatch, snapshot, Owner, ...)
       + AddEffect(0x47d = 1149 EarlyWarningOverride_Visual,              snapshot, Owner, ...)
       + Spawn(Owner@0x148, tiles, unitId, opts) )
```

### 2.2 Le piege de mesure : 2 des 4 effets sont INVISIBLES au moment du cast

MESURE LIVE juste apres le cast : seuls **1144 et 1149** apparaissent dans `decisionView.effects`.
Ce n'est PAS un sur-port : `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` (decompile)
donne l'ActiveCondition de 1009 :

```
Triggered( On(0x12) & NOT IsTurnOf(owner)
           & ( HasEffect(Owner, 0x516 = 1302 IgnoreUsedAbilityInOverwatch)
             | DoesNotHaveFlag(Owner, 2 = ActiveAbilityUsed) )
           & NOT HasEffect(Owner, 0x429 = 1065 Pinned),            # AdditionalActivateTrigger
           ActivateEffect(Effect@0x150) )
Triggered( On(0x12) & IsTurnOf(owner),  DeactivateEffect(Effect@0x150) )
Triggered( On(10)   & OwnerIsActor,     DeactivateEffect(Effect@0x150) )
```

-> l'overwatch ne s'ACTIVE qu'au turn-start d'un tour qui n'est PAS celui du porteur ; tant que c'est
son tour, `IsActive = 0` et `readEffectsByUnit` le DROPPE. MESURE : apres un `endturn`, les **4**
effets sont visibles. Le test confronte donc en DEUX temps (immediat : sous-ensemble exact avec
`remaining` ; apres endturn : egalite des TYPES).

**Coherence de design a noter** : 1077 override `SetsActiveAbilityUsedFlag` (#139, table
`NO_ABILITY_USED_FLAG_ABILITY_TYPES`) — sans quoi le flag `ActiveAbilityUsed` pose par son propre
cast FERMERAIT la porte `DoesNotHaveFlag(Owner, 2)` et Re'vas n'overwatcherait jamais.

### 2.3 `PerformAIAttack` : gate de PORTEE ajoute (correction de fidelite)

Le natif est une routine IA « depuis la position COURANTE » : l'acteur n'attaque que s'il a une cible
ATTEIGNABLE sans bouger (i2 : « can immediately attack an enemy **in melee** »). La feuille partagee
`PerformAIAttack` du port frappait `_nearest_enemy` **sans aucun test de portee** — un drone spawne a
9 hex de l'ork le plus proche l'attaquait quand meme. Gate ajoute : `_in_attack_range` (mirror
`DSLFactory.IsInAttackRange(attacker, target, 3)`, la MEME primitive que l'overwatch).

Inerte pour tous les call-sites anterieurs (ForwardSpotter / SendInTheNextWave / Incursion spawnent
sur des tuiles ADJACENTES A LA CIBLE ; GetEmRuntz sur des tuiles adjacentes aux ennemis) — verifie
par re-jeu : `test_aberrant_hypermorph_live`, `test_alpha_warrior_live`, `test_ironkin_steeljack_live`,
`test_mow_groups_bcd_live`, `test_summon_consumers_live`, `test_spore_mine_launcher_live`,
`test_scarab_summon_migration_live` (52 tests verts).

---

## 3. InspiredToGreatness (1082)

### 3.1 Arbre natif (MIRROR 1:1)

```
hpUsed    = GetVariableForLevel(config, 0x20)   # = hpToHeal    [lvl65 = 1091]
hpUnused  = GetVariableForLevel(config, 0x22)   # = hpToHeal_2  [lvl65 = 4365]
canReset  = UnitsThatCanHaveActiveAbilityReset( target@0x178 )
cantReset = TargetsSelector.op_Subtraction( target@0x178, canReset )
lvl       = Min( AbilityLevelAmount(Owner@0x148, AbilityType(0x43a)),
                 PrimaryActiveAbilityLevelAmount(canReset) )

Execute( ( RepairOrHeal(canReset,  hpUsed,   canReset)
         & RepairOrHeal(cantReset, hpUnused, cantReset) )
       & AddStatOverrideEffect(canReset, 0x49c = 1180 InspiredToGreatness_OverrideLevel,
                               0x12 = 18 ACTIVE_ABILITY_LEVEL, lvl)
       & ResetActiveAbility(canReset, 0) )

InspiredToGreatnessAbility$$RepairOrHeal(sel, amt, sel2) =
    If( IsRepairable(sel), Repair(caster@0x160, sel, Direct(amt), AbilityOrEffect(0x43a)),
                           Heal  (caster@0x160, sel2, Direct(amt)) )
```

Le SPLIT **EST** la mecanique de l'i2 (« heals or repairs it for 1091 Health. [...] If that unit has
**not used** their active ability yet, then **4365** Health is restored instead »).

### 3.2 Le debloqueur : l'etat d'utilisation des abilities actives

`UnitsThatCanHaveActiveAbilityReset` consomme
`BattleQuery$$EntityCanHaveActiveAbilityReset(unit, ignoreTurnFlag)` (decompile) :

```
foreach ab in unit.ActiveAbilityComponent.Collection :
    if (!abilitiesDb[ab.AbilityName].<slot 0x12 = resettable>) continue
    if (!ab.IsInCooldown) { if (ab.CanStillBeUsed == 0) return true }
    else if (ab.<+0x34> == 0) {
        if (ignoreTurnFlag)                    return true
        if (!HasFlag(unit, 3 = TurnFinished))  return true
        if (ab.RemainingCooldownTurns > 1)     return true
    }
return false
```

Le runner ne modelisait **AUCUN** etat d'ability. Porte ici :

- composant `ActiveAbilitiesComponent` + entree `ActiveAbility` (`runner/components.py`), mirror de
  `IdunBattle.Entities.Components.ActiveAbilityComponent` / `ActiveAbility` — champs
  `CanStillBeUsed@0x28` / `RemainingCooldownTurns@0x2c` / `IsDisabled@0x35` / `AbilityName@0x44` /
  `_abilityState@0x4c`, exactement ceux que `readAbilityState` (frida `ai-step/internals.ts`) lit ;
- SEED dans `load_state` depuis `decisionView.units[].abilities` (kinds `active`/`granted` seulement —
  l'entree `normal` n'a pas d'objet `ActiveAbility` derriere, et le natif l'exclut via
  `IsRegularAttack`) ;
- `entity_can_have_active_ability_reset` + `ResetActiveAbilityOperation`
  (`runner/operations/ability_reset.py`) ;
- accesseur `DslContext.can_have_active_ability_reset` + selecteur
  `UnitsThatCanHaveActiveAbilityReset`.

**Verdict INCONNU explicite** : sans `allAbilities: true` sur `decisionView`, le canal ne porte que
l'attaque normale -> composant ABSENT -> le predicat rend `None` (pas `False`). L'ability le
JOURNALISE (`diag["unknown_reset_verdict"]`) plutot que de laisser le split basculer en silence sur
le gros montant. Le test l'assert.

### 3.3 `IsRepairable` : semantique deduite, DISCRIMINEE au live

Le ctor du trigger est mislabele par ghidra -> lecture par la STRUCTURE (un operande-unite + un flag)
et par l'i2 : `IsAffectedByHealType(unit, 1 = Repair)` = `HasTrait(AffectedByHealAndRepair 0x421)` OU
`IsMechanical` — le COMPLEMENTAIRE exact du type 0 deja porte (`healable_heal_type_0`).

**Le live tranche** : `tauCrisis` est **Mechanical**. Si le port prenait la branche `Heal`, la garde
`healable_heal_type_0` la rejetterait et le gain de PV serait **0**. Mesure : **+1496 PV** offline
ET live -> la branche `Repair` est la bonne.

---

## 4. Confront LIVE (mesures)

`tests/engine/runner/test_tau_lot1_live.py` — 4 tests, 4/4 verts. Toutes les cibles sont prises dans
`abilityTargets(...).fromHere` (jamais `targets`, superset move-inclus, cf. #111).

| test | scenario (DRIVE des positions) | offline | live |
|---|---|---|---|
| `test_fighting_retreat_confront_live` | Darkstrider engage un ork, passe 2 tours (son 1515 se DESACTIVE), puis caste | `{ork: {1157:3, 1158:3, 1122:3}, ds: {1515:0}}` | **identique** ; `actionConsumed=false` |
| `test_fighting_retreat_ally_reactivation_and_finishturn_live` | Re'vas au contact (1515 desactive), Darkstrider adjacent a ELLE mais a >=2 des orks | `{revas: {1515:0}}`, `n_adj=0`, flow=`FinishTurn` | **identique** ; `actionConsumed=true` |
| `test_early_warning_override_confront_live` | self-cast | `{revas: {1009:2, 1144:2, 1145:2, 1149:2}}`, 2 tuiles adjacentes | tour du caster : `{1144:2, 1149:2}` (sous-ensemble exact) ; tour adverse : les **4** types ; 2 drones adjacents |
| `test_inspired_to_greatness_confront_live` | Re'vas blessee par l'IA native + ayant consomme son actif ; 3e unite non activee pour que le tour ne se termine pas | dHP `{revas: +1496}` (= `hpToHeal`, PAS `hpToHeal_2=5983`), eff `{revas: {1180:0}}`, `reset=[1077] gate=true` | **identique** ; `usable(1077)` repasse a `true` |

Points de mesure notables :

- `remaining 3` des 3 debuffs = `ConvertRoundsToTurns(1)=2 + 1` -> confirme
  `TurnsUntilEndOfCurrentPlayersNextTurn` sur un 2e consommateur independant (le 1er etait AnvilShield).
- Le montant `1496` = `hpToHeal[level 50] = 831` x `multiplier 180 %`. La 2e branche vaudrait 5983 —
  facteur 4, donc un mauvais aiguillage du split serait immanquable.
- `applyAction endturn` **ne fait PAS jouer l'IA** : sans `aiPlayByUnit`, l'ennemi ne bouge ni ne
  frappe jamais (c'est ce qui empechait de blesser la cible de 1082 ; note de harnais reutilisable).

### Non couvert (explicite)

- **FightingRetreat** : la branche `Heal` d'aucun volet (l'ability n'en a pas) ; le cas `>1 ennemi
  adjacent` (les scenarios en ont 1) — le port itere le selecteur, mais la mesure n'a pas de
  multi-adjacence ; l'exclusion `Steppable`/`Object` (aucun decoy dans le roster de test).
- **EarlyWarningOverride** : le comportement d'overwatch REEL des effets poses (le tir after-move)
  n'est pas re-mesure ici — il est couvert par `test_overwatch_live` (re-joue vert) ; l'attaque
  on-appearance des drones n'est pas exercee (aucun ennemi a portee dans le scenario).
- **InspiredToGreatness** : la branche `cantReset` (allie qui n'a PAS utilise son actif) n'est pas
  atteignable en cast LEGAL sans une cible par ailleurs blessee/reparable — non craftee ; la branche
  `Heal` (cible NON mecanique) non craftee ; l'override de niveau n'est pas re-mesure sur un 2e cast
  de la cible.

---

## 5. Collapses assumes et residus (candidats taches)

**Collapses S/V** (doctrine slice-18/19 — le natif compose, le port evalue imperativement) :

- `SortTilesByUtilityForSummon(..., UtilityBucket(WeightedUtility 7, WeightedUtility 0x38), Owner)`
  (1077) : moteur d'utilite IA COMPLET, NON porte -> on conserve l'ordre du selecteur
  (`CanAddUnit(AdjacentTiles(caster))`, voisinage natif). **Residu** : avec plus de tuiles libres que
  `nrOfSummons`, la TUILE choisie peut differer du live ; POOL et CARDINAL sont exacts. Meme classe de
  residu que ForwardSpotter / SendInTheNextWave / SwornProtector.
- `AbilityLevelAmount` / `PrimaryActiveAbilityLevelAmount` (1082) : formules V collapsees en scalaire.
- `adjEnemies.Count(entities)` (1081) : evalue a la construction, injecte en `Const` — c'est ce que
  fait le natif.

**Residus a lever (nommes, avec leur ancrage) :**

1. ~~**ActiveCondition de l'overwatch non modelisee**~~ — **LEVE par case-127**
   (`case-127-overwatch-active-condition`). La condition d'ACTIVATION de
   `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` (`NOT IsTurnOf(owner)` &
   (`HasEffect(owner, 1302)` | `DoesNotHaveFlag(owner, 2)`) & `AdditionalActivateTrigger`) est
   repliee dans `OverwatchAutoAttack.matches` (helper `_ranged_auto_attack_is_active`), confrontee
   live avec controle interne (`eldarRanger`/1063 flag pose -> 1009 ABSENT vs `admecDestroyer`/1139
   override -> 1009 PRESENT, meme tour, meme cible). Le 3e `Triggered()` (`On(10) & OwnerIsActor ->
   DeactivateEffect` = **un seul tir par activation**) est FERME lui aussi : `case-127` §8 (flag
   `EffectComponent.IsActive @+0x5c` par instance + vecteur `On(AttackDamageAttack)`).
2. ~~**Retrait de l'override de niveau (1180)**~~ — **LEVE** (cf. §7).
3. ~~**Phase 2 d'EarlyWarningOverride**~~ — **LEVE** (cf. §8). 1149 reste VISUEL pur (inerte assume).
4. **`ab.<+0x34>`** (champ non nomme entre `IsDisabled@0x35` et le Nullable de cooldown), lu comme 0
   dans `entity_can_have_active_ability_reset` -> la branche « en cooldown » est toujours PRISE. Non
   observable par le canal live actuel.
5. **`abilitiesDb[type].<slot 0x12>`** (« l'ability est-elle resettable ») approxime par « entree de
   kind active/granted ». Le natif exclut de toute facon l'attaque normale (`IsRegularAttack`), que le
   seed ne materialise pas.

**Extension #115 prete a poser (masques `TargetingOptions` RE-lus)** — le lot ne CABLE pas de
`TARGETING_OPTIONS` (c'est le point d'extension de #115, arrive dans `master` pendant le lot), mais
les masques du ctor natif sont lus et notes ici pour que le cablage soit mecanique :

| ability | `TargetingOptions..ctor(this, ?, opts, ?, RULES, ...)` | bits |
|---|---|---|
| 1081 FightingRetreat | `RULES = 0x802` | 0x2 `TargetMatchesDynamicRule` + 0x800 (bit 11, hors inventaire porte) |
| 1082 InspiredToGreatness | `RULES = 0x402` | 0x2 `TargetMatchesDynamicRule` + 0x400 `TargetIsFriendly` (**les deux portes**) |
| 1077 EarlyWarningOverride | options STATIQUES de classe (`cctor+0x280`) — masque non lisible inline | — |

Le `GetDynamicInvalidTargetReason` de chacune est decompile en §1.4 (1081) et §3 (1082) : cabler les
deux (masque + regle dynamique) rendrait le port CAPABLE de refuser les casts illegaux offline,
comme le natif.

**Hors perimetre du lot** (non touches) : `SereneUnifier` (passif tauAunShi), `StructuralAnalyser`
(passif tauDarkstrider — deja porte cote effets), `CyclicIonBlaster` (passif tauCrisis — porte),
`ExemplarOfTheMontka(1210)`, `SeekerMissileFrequencyLock(1069)`, `ExemplarOfTheKauyon(1087)`.

---

## 6. Primitives NEUVES (reutilisables)

| primitive | fichier | natif |
|---|---|---|
| `ActivateEffect` (feuille) | `runner/abilities/behaviours/effects.py` | `ActivateEffectBehaviour$$Execute` (branche selecteur-d'effets +0x58) |
| `AddStatOverrideEffect` (feuille) | idem | `AddStatOverrideEffectBehaviour$$Execute` |
| `ResetTurn` / `FinishTurn` (feuilles) | `runner/abilities/behaviours/turnflow.py` | `ResetUnitTurnBehaviour$$Execute` / `FinishUnitTurnBehaviour$$Execute` |
| `ResetActiveAbility` (feuille) | `runner/abilities/behaviours/ability_state.py` | `ResetActiveAbilityBehaviour$$Execute` |
| `Repair` (feuille) + `repairable_heal_type_1` | `runner/abilities/behaviours/stats.py` | `RepairBehaviour$$Execute` / `UnitExtensions$$IsAffectedByHealType(unit, 1)` |
| `IsRepairable` (predicat T) | `entities/triggers.py` | `DSLFactory$$IsRepairable` |
| `UnitsThatCanHaveActiveAbilityReset` (selecteur S) | `entities/selectors.py` | `UnitsThatCanHaveActiveAbilityResetSelector$$Select` |
| `ActiveAbility` / `ActiveAbilitiesComponent` (ECS) | `runner/components.py` | `Components.ActiveAbility` / `ActiveAbilityComponent` |
| `entity_can_have_active_ability_reset` / `ResetActiveAbilityOperation` | `runner/operations/ability_reset.py` | `BattleQuery$$EntityCanHaveActiveAbilityReset` / `ResetActiveAbilityOperation$$Execute` |
| `turns_until_end_of_current_players_next_turn` | `runner/abilities/base.py` | `DSLFactory$$TurnsUntilEndOfCurrentPlayersNextTurn` |
| gate de PORTEE de `PerformAIAttack` | `runner/abilities/behaviours/summon.py` | `PerformAIAbilityUnitBehaviour$$Execute` (routine AI depuis la position courante) |
| `turns_until_unit_owner_turn` | `runner/abilities/base.py` | `DSLFactory$$TurnsUntilUnitOwnerTurn` / `TurnsUntilUnitOwnerTurnFormula$$GetTurnsUntilUnitOwnerTurn` |
| `is_active_ability` | `runner/abilities/attack_type.py` | `StaticBattleRules.ActiveAbility$$IsActiveAbility` |
| vecteur `On(UnitActiveAbility = 0xc)` | `runner/operations/triggers/dispatch.py` | `ActiveAbilityOperation$$ExecuteInternal` (`FUN_180026490(0x4d, .., 0xc)` sous gate) |
| `UnitComponent.death_source` + `_record_death_reason` / `_damage_source_ability` | `runner/components.py`, `runner/operations/damage.py` | `KillUnitOperation$$RecordDeathReason` / `StaticBattleRules$$GetDamageSourceAbility` |
| `has_death_reason` (predicat T) | `runner/operations/triggers/loki/reactivate_overwatch.py` | `HasDeathReasonTrigger$$ShouldTrigger` / `$$IsMatchingDeathReason` |

---

## 7. Residu 2 LEVE — retrait de l'override de niveau (1180)

### 7.1 Artefact natif

`IdunBattle.Entities.Effects.Loki.InspiredToGreatness_OverrideLevelEffect$$CreateRemoveEffectTrigger`
= `On(0xc) & get_OwnerIsCaster`. Le trigger n'est pas enregistre par la classe d'effet : c'est
`IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities` (wrapper GENERIQUE au-dessus de
`CreateHandleTriggerAbilitiesInternal`) qui, quand ce virtuel rend un trigger non nul, AJOUTE a
l'`ArraySet` de l'effet :

```
Triggered( CreateRemoveEffectTrigger(),
           DSLFactory.RemoveEffect(df@0x150) )        # == BaseEffect$$GetRemoveEffectBehaviour
```

`df@0x150` = le selecteur d'entite-effet COURANTE -> le behaviour retire CETTE instance.

### 7.2 Le gate qui fait la semantique : `On(0xc)` N'EST PAS emis par une attaque normale

`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (sequence LUE au decompile) :

```
On(0x2b) PreUnitAbility            <- avant l'execution
... execution de la behaviour ...
On(0xb)  UnitAbility               <- inconditionnel
if (StaticBattleRules.ActiveAbility$$IsActiveAbility(abilityType))  On(0xc) UnitActiveAbility
AddFlagsAfterAbilityExecution(...)
On(0xe)  UnitPostAbility
```

`IsActiveAbility(t)` = `!IsRegularAttack(t) && t not in {0x12 Heal, 0x1c Repair, 0x45f
Repair_GalvanicField, 0x48f Heal_TwistedScience, 0x4bc HealingBalms_Heal}`. L'attaque NORMALE emprunte
pourtant la MEME operation (elle EST une active ability) : c'est ce gate, et lui seul, qui borne le
retrait au **prochain CAST D'ACTIF** du porteur — l'utilisation supplementaire que 1082 vient de lui
accorder — et non a sa prochaine action.

Le port emet donc `On(0xc)` depuis la SEULE voie ability (`AbilityHandler.visit_ActiveAbilityMessage`),
au rang natif (apres l'execution, avant `AddFlagsAfterAbilityExecution`) et avec le gate re-applique
dans le vecteur. La voie normale (`damage.py`) n'a rien a emettre.

### 7.3 Le revert doit RESTAURER `active_ability_level`

`AddStatOverrideEffect` ecrit le stat 18 dans `UnitContext.active_ability_level` (seul canal lu par
`ability_var`/`ability_attack_params`, donc seul mirror OBSERVABLE de `GetStat(unit,
ACTIVE_ABILITY_LEVEL)`) et memorise `overridden_prev`. Le `ResetStat` (part 8) de
`AddEffectOperation.revert_stat_overrides` restaure desormais cette valeur — sinon le retrait de 1180
laisserait le niveau plafonne a vie.

---

## 8. Residu 3 LEVE — re-entree en overwatch + reduction de coups (1145)

### 8.1 Hierarchie native

`EarlyWarningOverride_ReactivateOverwatchEffect` (1145) etend
`IdunBattle.Entities.Effects.AReactivateOverwatchEffect` (qui etend `DamageModifierAbilityEffect`) ;
son ctor = `AReactivateOverwatchEffect..ctor(this, 0x435 = 1077)` -> l'effet resout ses `ConfigVar`
contre la config de 1077. Trois autres sous-classes partagent la meme mecanique :
`FiringPosition_ReactivateOverwatchEffect` (1150), `CalibaniteGreatsword_StrikeOverwatchingEffect`,
`InescapableDeathEffect`.

### 8.2 `AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal` (MIRROR 1:1)

```
Triggered(                                                     # (1) LA RE-ENTREE
    On(1 = PreUnitDeath) & get_OwnerIsActor
      & NOT df@0xa0                                            # IsTurnOf(owner@0x148)
      & AmountIsGreater( Max(RangedAttackHits(Owner), MeleeAttackHits(Owner)),
                         HitReductionValue() )                 # vtable +0x748
      & LegitDeathReasons(),                                   # vtable +0x738
    ActivateEffect(Owner, 0x3f1 = 1009)                        # GetReactivateOverwatchBehaviour
    & AddStaticStatModifierEffect(Owner, GetHitReductionEffectType(),   # vtable +0x758
                                  0x11 = EXTRA_HITS, Negative(HitReductionValue()),
                                  TurnsUntilUnitOwnerTurn(Owner), isHidden=0) )

Triggered(                                                     # (2) LA PURGE
    ( On(0 = UnitDeath) | On(0x11 = PostDamageTaken) )
      & NOT HasEffect(Owner, 0x3f1, onlyActive=1, targetType=6=Both),
    RemoveEffect(Owner, Nullable(GetHitReductionEffectType())) )
```

`AReactivateOverwatchEffect$$HitReductionValue` = `Direct(GetNumberConstant(config@0x60, 0x2c))` =
la constante `hitsReduction` de l'ability source (=1 pour 1077).

Overrides de 1145 :
- `$$GetHitReductionEffectType` = `return 0x47a` = **1146 `EarlyWarningOverride_HitReduction`** ;
- `$$LegitDeathReasons` = `HasDeathReason(dying@0x178, Ability, 0x3f1 = 1009)
  | HasDeathReason(dying@0x178, Ability, 0x47c = 1148 CyclicIonBlaster_AdditionalHits)` — la base ne
  garde que la 1re branche. Un kill porte par les 3 coups Particle du passif de Re'vas compte AUSSI :
  c'est ce que « toute mort re-arme » aurait rate.

### 8.3 Le canal DEATH-REASON (la piece qui manquait au port)

`HasDeathReasonTrigger$$ShouldTrigger` resout son SELECTEUR, prend le `UnitComponent` de chaque unite
selectionnee, lit son `Nullable<DamageSource>` @`+0x108` et delegue a `$$IsMatchingDeathReason` :

```
if (!src.HasValue) return false
if (src.DamageReason != this.deathReason) return false                 # 0=Ability 1=Knockback 2=Steppable
if (!this.abilityOrEffect.HasValue) return true
return src.AbilityOrEffect.HasValue && src.AbilityOrEffect == this.abilityOrEffect
```

Le champ est ecrit par `KillUnitOperation$$RecordDeathReason(killer, killed, killedUnitComponent,
deathReason)`, appelee par `KillUnitOperation$$Execute` **AVANT** l'emission d'`On(PreUnitDeath=1)`
(ordre lu au decompile). Son `AbilityOrEffect` vient de la `DamageSource` construite PAR COUP par
`AttackDamageOperation$$ExecuteHit` / `AbilityDamageOperation$$ExecuteHit` via

```
StaticBattleRules$$GetDamageSourceAbility(currentAbility, triggeringAbility) =
    IsRegularAttack(currentAbility) && triggeringAbility.HasValue ? triggeringAbility : currentAbility
```

=> un tir d'OVERWATCH (`Overwatch_AutoAttackEffect$$GetAttackBehaviour` =
`UseActiveAbility(NormalAttack)`, donc une attaque REGULIERE declenchee par l'effet 1009) enregistre
**1009** comme source. Le port FUSIONNE les deux morceaux au moment du kill
(`AttackDamageOperation._record_death_reason`, alimente par `_damage_source_ability` et par le
`triggering_ability` que le call-site overwatch passe) — il n'a pas le transport
`DamageAppliedResult.source` du natif.

MESURE (test de garde) : `death_source = (81, 0, 1009)` sur la victime d'un tir d'overwatch,
`(81, 0, 1013)` sur la victime d'une attaque normale du MEME porteur.

### 8.4 Ce que le port modelise, et ce qu'il ne modelise pas

- **La reduction de coups est pleinement observable** : 1146 apparait sur le porteur avec un stat-mod
  `EXTRA_HITS = -hitsReduction` (mesure : `-1`) de duree `TurnsUntilUnitOwnerTurn` (mesure : 1 tour,
  offline == live) ; `attack_hits_with_modifiers` le consomme -> le tir suivant a un coup de moins.
- **`ActivateEffect(Owner, 1009)` = le CONTREPOIDS du « un seul tir par activation »** (`case-127` §8,
  3e `Triggered()` de `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` :
  `On(AttackDamageAttack=10) & OwnerIsActor -> DeactivateEffect`). Le tir d'overwatch CONSOMME
  l'instance 1009 ; ce behaviour la RE-ARME quand le tir a tue. La feuille `ActivateEffect` ecrit
  desormais le flag `BaseEffect.active` (= `EffectComponent.IsActive @+0x5c`, porte par `case-127`) en
  plus de la presence — sans ce complement, `GetReactivateOverwatchBehaviour` restait vide.
  GROUND TRUTH LIVE (test de garde §9) : apres le kill en overwatch, 1009 est TOUJOURS present dans
  `decisionView` (donc `IsActive != 0`) — « she remains in Overwatch ».
- **`On(PostDamageTaken = 0x11)`** (2e disjonct de la purge) : aucun vecteur du port ne l'emet (site
  d'emission natif non localise — ni `ApplyDamageOperation$$Execute`, qui n'emet que 0x3a/0xf/0x10, ni
  `KillUnitOperation$$Execute`). La classe l'ECOUTE (`event_ids`) ; l'ecoute est dormante. Aucun port
  speculatif du vecteur.
- **Branche 1148** de `LegitDeathReasons` : le port ne materialise pas la `DamageSource` PAR COUP, donc
  un kill porte par un coup additionnel `CyclicIonBlaster_AdditionalHits` s'enregistre sous la source
  de l'attaque porteuse. Le predicat porte la branche ; elle ne peut pas matcher aujourd'hui.

### 8.5 Pieges de RE traverses (a ne pas re-payer)

- Ghidra nomme `EarlyWarningOverride_ReactivateOverwatchEffect$$GetOverwatchExtraDamage` la fonction
  @RVA `f40360` : la table FRIDA (AMONT de Ghidra dans la chaine de symboles) dit que c'est
  `InescapableDeathEffect.GetOverwatchExtraDamage`. 1145 n'override PAS `GetOverwatchExtraDamage` ;
  son 2e override est `GetHitReductionEffectType` @`f40350`, que Ghidra n'a meme pas en fonction
  (corps `mov eax,0x47a ; ret`, lu en OCTETS).
- Les ctors gshared (`IsUnitWIthIdTrigger`, `ModuloAbilityTrigger`) sont mislabeles : c'est la
  STRUCTURE des arguments qui identifie `RangedAttackHits` / `MeleeAttackHits` (meme classe, flag
  ranged 1/0) et `TurnsUntilUnitOwnerTurn`.
- Qualification d'enum : `1145` est AUSSI `ActiveAbilityType.SporeMineLauncher` (deja portee) et
  `1148` AUSSI `ActiveAbilityType.DaemonicOrdnance`. Le contexte est `EffectType` des DEUX cotes.

### 8.6 Collapses assumes

| noeud natif | collapse |
|---|---|
| `RangedAttackHits` / `MeleeAttackHits` (`AttackHitsFormula$$Calculate`) | `arme(profil).Hits + ExtraHits(0x11) [+ ExtraHitsMelee(0x17) en melee]` = `GetDefaultAttackHits`, la base exacte de la facade `GetAttackHits` (la formule native est evaluee SANS defenseur) |
| `TurnsUntilUnitOwnerTurn` | le port ne detient pas la liste `TurnOrder` (seulement `current_player_id` + `turn_order_player_count`) : sur un duel — le seul vecteur du port — la boucle native ne compte que le joueur courant, soit **1**. Au-dela de 2 joueurs non-Environment, la fonction rend 1 (borne INFERIEURE) |
| `NOT df@0xa0` (`IsTurnOf(owner)`) du Triggered #1 | REDONDANT sur le canal porte : `AReactivateOverwatchEffect$$CreateActiveCondition` = `NOT IsTurnOf(owner)`, donc l'effet 1145 est INACTIF pendant le tour de son porteur et `readEffectsByUnit` le DROPPE — le trigger n'est meme pas enregistre. Le conjoint est porte quand meme (il redevient load-bearing le jour ou l'`IsActive` par instance existe) |

---

## 9. Confront LIVE des deux residus

`tests/engine/runner/test_tau_lot1_residues_live.py` — 3 tests, 3/3 verts. Chaque test exerce la
branche AVANT **et** APRES ; les trois ECHOUENT si l'on desactive les entrees `EFFECT_TRIGGERS`
(verifie).

| test | scenario (DRIVE des positions) | mesure |
|---|---|---|
| `test_inspired_to_greatness_override_removed_on_next_active_cast_live` | Re'vas consomme 1077 -> Aun'Shi caste 1082 (1180 pose) -> tour suivant, Re'vas RE-CASTE 1077 | 1180 PRESENT avant, ABSENT apres — offline **et** live. Controle `OwnerIsCaster` : le cast de 1082, rejoue OFFLINE, emet lui aussi `On(0xc)` (caster = Aun'Shi) APRES sa behaviour et ne retire PAS le 1180 qu'il vient de poser |
| `test_early_warning_override_reactivate_overwatch_live` | Re'vas caste 1077, la main passe a l'adversaire, un ork (`--hp-target 1`) est DRIVE d'un pas dans sa portee -> overwatch -> kill | 1146 ABSENT avant, PRESENT apres — offline **et** live, `remaining` identique ; `EXTRA_HITS = -1` ; `death_source = (revas, Ability, 1009)` |
| `test_tau_lot1_residues_gates_negative_live` | MEME unite, MEME etat (1180 pose, overwatch arme), mais une ATTAQUE NORMALE qui TUE, pendant SON tour | 1180 SURVIT (gate `IsActiveAbility`) et 1146 n'est PAS pose ; `death_source = (revas, Ability, 1013)` = le marqueur de kind attaque-normale, pas 1009 |

**Le drive du camp ADVERSE est un acquis de harnais** : `applyAction move` accepte l'unite du joueur
COURANT, adversaire compris (`mutated: true`, position changee) — c'est ce qui rend un kill en
overwatch CRAFTABLE sans dependre de l'IA native. `aiMovableTiles` sans `side` rend les unites du
joueur courant. En revanche, `applyAction endturn` emis pendant le tour adverse a fait passer le
runner en `stage Finished` : on laisse le tour adverse basculer SEUL (il le fait des que ses unites
n'ont plus d'action).

### Non couvert (explicite)

- **Branche 1148** de `LegitDeathReasons` (kill par un coup additionnel `CyclicIonBlaster`) : non
  atteignable tant que la `DamageSource` n'est pas materialisee PAR COUP (cf. §8.4).
- **`ActivateEffect(1009)`** : no-op sous le modele presence == IsActive ; sa validation appartient au
  chantier « un seul tir par activation » (`case-127` §6.1).
- **Le disjonct `On(PostDamageTaken)`** de la purge : vecteur non emis par le port.
- **Le gate de coups** `Max(Ranged, Melee AttackHits) > hitsReduction` : exerce en positif seulement
  (Re'vas a plus d'un coup) ; aucun porteur du roster ne le met en defaut.
- **`FiringPosition_ReactivateOverwatchEffect` (1150)** : meme base, porteur non identifie — non
  enregistre (le registre `EFFECT_TRIGGERS` est keye par `effectType`, l'ajout serait mecanique).
