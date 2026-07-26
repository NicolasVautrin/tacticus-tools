# Case #114 — Tau lot 1 : face COMBAT de 3 abilities dont la face DECISION etait deja portee

**Statut : LIVRE.** Les 3 abilities passent de `[-D]` (decision portee, execution NO-OP) a `[CD]`
dans `kit-coverage.md`. RE ghidra `gqfc5mff6c` (decompile = verite), port DSL 1:1, confront LIVE
bit-exact des 3 (4 tests, `tests/engine/runner/test_tau_lot1_live.py`).

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

1. **ActiveCondition de l'overwatch non modelisee** — `RangedAutoAttackEffect$$
   CreateHandleTriggerAbilitiesInternal` : offline, un effet 1009 present est TOUJOURS actif. Le gate
   reellement manquant est `DoesNotHaveFlag(Owner, 2 = ActiveAbilityUsed)` (+ l'echappatoire
   `HasEffect(Owner, 0x516 = 1302)`) : **un overwatcher qui a utilise une ability active pendant son
   tour ne devrait PAS overwatcher au tour adverse**. Sans consequence pour 1077 (qui override
   justement `SetsActiveAbilityUsedFlag`), mais faux pour tout autre porteur d'Overwatch. Chantier
   PRE-EXISTANT (l'effet-trigger `OverwatchAutoAttack` date de #201), a porter dans
   `operations/triggers/effect_triggers.py`.
2. **Retrait de l'override de niveau (1180)** — `InspiredToGreatness_OverrideLevelEffect$$
   CreateRemoveEffectTrigger` = `On(0xc) & OwnerIsCaster` (retrait au PROCHAIN cast du porteur). Non
   branche offline -> l'override sur `active_ability_level` PERSISTE apres la 2e utilisation. Sans
   consequence pratique (le porteur n'a droit qu'a UNE utilisation supplementaire).
3. **Phase 2 d'EarlyWarningOverride** — `EarlyWarningOverride_ReactivateOverwatchEffect`
   (`$$GetOverwatchExtraDamage`, `$$LegitDeathReasons`) : la re-entree en overwatch apres un kill avec
   `hitsReduction=1` (i2 : « she remains in Overwatch, retaining 1 fewer hits »). L'effet 1145 est
   POSE (presence fidele) mais reste un `BaseEffect` inerte. 1149 = visuel pur.
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
