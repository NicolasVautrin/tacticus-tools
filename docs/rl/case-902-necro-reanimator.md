# #902 — `necroReanimator` : `1223 ReanimationBeam` et `1224 NanoscarabRepairProtocols`

Porteur : `necroReanimator`, **MACHINE OF WAR** Necrons, `kind: lineup`, **hors pool**
(`rl_duel build --list-pool` : 8 MoW spawnables, pas lui). Montage retenu : **injection catalogue**
(`catalog_inject --units necroReanimator` + `rl_duel build --seed-bc … --p-mow necroReanimator`),
board à slot `MachineOfWarPosition` des deux côtés (`C1_02`).

**Pourquoi cette voie et pas `--explicit-stats necroNpcMoWReanimator`** : l'injection lineup donne
l'entrée de catalogue de l'unité **jouable**, donc ses vraies `level`/`multiplier` d'ability —
mesurées à `level=50 multiplier=160` sur `decisionView.mows[].abilities[]`. La voie NPC substitue un
porteur différent, dont rien ne garantit qu'il partage la configuration d'ability.

## 1. L'audit dit « REPAIR » pour les deux — c'est vrai de 1223 SEULEMENT

La colonne est dérivée de la présence d'une variable `hpToRepair*`. `1224` en a une, et **ne
répare rien** : son `hpToRepair` est lu par l'**EFFET** `1545`
(`IdunBattle.Entities.Effects.Loki.NanoscarabRepairProtocolsEffect$$CreateEffectRepairBonus` =
`EffectBonus.ForAddition(OwnerIsTarget, ConfigVar(0x24 = hpToRepair))`), qui **bonifie** toute
réparation reçue par le porteur. La variable appartient à l'effet, pas au cast.

Le couple forme une **boucle** : 1224 **marque**, 1223 **moissonne** (son sélecteur ET son gate
exigent l'effet 1545).

## 2. Les deux arbres, tels que LUS

`IdunBattleLogic.Entities.Abilities.Active.Loki.NanoscarabRepairProtocolsAbility$$ExecuteBehaviour` :

    [A] AddEffect(0x609 = 1545, abilityState = AbilityStateReference, source = Owner@+0x30,
                  targets = Target@+0x60, options = default(0) -> PERMANENT)
    hp  = GetVariableForLevel(config@this+0x60, 0x1d = hp, abilityState)
    [B] AddDynamicStatModifierEffect(targets = Target@+0x60, source = Owner@+0x30,
                  effectType = 0x60a = 1546, statType = 5 Health,
                  abilityStateSelector = AbilityStateReference, turns = null, isHidden = false)
    [C] ChangeStat(targets = Target@+0x60, stat = Stat(5 Health, part 0 Current), mode = 2 Add,
                  amount = Get(hp), modificationEntity = null, selectionType = 3,
                  isModifiable = false, isHiddenModification = false)
    Execute( ([B] + [C]) + [A] )

`…$$GetExtraMaxHealthBehavior` est le même couple `[B]+[C]`, **inliné** par IL2CPP dans
`$$ExecuteBehaviour` (zéro appelant direct) → un seul foyer côté port.

`IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$ExecuteBehaviour` :

    carriers = EntitiesWithAnyEffect(
                   MechanicalUnits(Friends(of = Owner@+0x30, entities = AllAliveUnits@+0x20, 3), 3),
                   [0x609], effectTarget = 6 Both)
    [A] Repair(mechanic = Caster@+0x48,
               selector = Repairable(carriers, scope 0, removeEffects true, unitsToTarget 3),
               amount   = ConfigVar(0x24 = hpToRepair, abilityState, config@+0x60),
               source   = AbilityOrEffect(0x4c7 = 1223), options = ForRepair())
    [B] $$GetSummonsTakeActionBehaviour(carriers, …) :
            sel  = UnitsWithTrait(carriers, 2 = Summon, 3)
            node = PercentageOfAttackCappedAtMax(ActiveTarget@+0x68, statPart **0 = Current**,
                       ConfigVar(0xd = maxDmg), ConfigVar(0x4a = dmgPct), roundingRule 0)
            ( AddTemporaryAttackOverrideEffect(sel, node)
              & PerformAIAction(sel, actAsAGroup 1, forced 1) ) & ResetTemporaryAttackOverrideEffect(sel)
    [C] AddEffect(0x60b = 1547 ReanimationBeam_Revive, AbilityStateReference,
                  targets = Actor@+0x40, turns = TurnsFromRounds(1))
    Execute( ([A] + [B]) + [C] )

`$$GetRepairBehaviour` et `$$GetAttackDamage` sont les mêmes sous-arbres inlinés ; le second n'a que
des call-sites d'`ExemplarOfHateAbility` — **corps partagé** par déduplication IL2CPP, pas un appel.

Les fabriques écrivent elles-mêmes deux littéraux : `AddTemporaryAttackOverrideEffect` =
`AddStatOverrideEffectBehaviour(targets, **0x510 = 1296 TemporaryStatOverride**, stat 0 Attack,
amount, durée 0, isModifiable 1)` et `ResetTemporaryAttackOverrideEffect` =
`RemoveEffect(targets, Nullable(0x510), 0)`.

**Deux écarts avec `Repair_GalvanicField`, lus et non recopiés** : `statPart` vaut **0 Current** (là
`3 Initial`), et l'action libre passe par `PerformAIAction(asGroup 1, forced 1)` — le *group
operator*, qui boucle `PickNextUnit` — là où GalvanicField appelle
`PerformAIAttackFromCurrentPosition` (attaque sans déplacement). Un summon réanimé peut donc **se
déplacer** puis agir.

Les 9 arguments de `ChangeStat` et les 8 d'`AddDynamicStatModifierEffect` ont été relus **au
désassemblage** : le décompilateur rendait leurs quatre derniers slots en registres non initialisés.

## 3. Masques — surcharge FLAGS DIRECTS, tranchée par les XREFS entrantes

`TargetingOptions$$.ctor` a trois surcharges. Les xrefs entrantes placent les deux ctors sur la
**sept arguments** `(this, isSelfCasting, range, forceMeleeTarget, rules, getDynamicInvalidCasterReason,
getDynamicInvalidTargetReason)` — celle dont le corps **écrit `rules` tel quel** à `options+0x28`
(les deux autres font `template.Rules | additionalRules`, ou une copie de template).

| | isSelfCasting | range | forceMeleeTarget | rules |
|---|---|---|---|---|
| 1223 | **1** | `TargetingRange` statics+0x48 = `RANGE_WHOLE_BOARD` | 1 = `RangedBool.False` | `0x200040000402` |
| 1224 | 0 | idem | 1 | `0x40000402` |

Décomposition (reste = 0 des deux côtés) : `TargetMatchesDynamicRule` `0x2` · `TargetIsFriendly`
`0x400` · `AllowNullCasterTile` `0x40000000` · et pour 1223 seul `TargetIsUnit` `0x200000000000`.
`AActiveAbility..ctor(this, &opts, 2)` sur les deux → `AbilityAttackType.Others`.

Gates dynamiques (mirror verbatim, `onlyActive = null` → `components.has_effect_of_type`, jamais
`ctx.has_effect` dont le défaut `active_only=True` consulterait `EffectComponent.IsActive`) :

    1223 : target != null && HasEffect(target, 0x609) && IsMechanical(target)  -> 0 ; sinon 2
    1224 : target != null && IsMechanical(target)  -> (IsOwnerOfEffect(target, 0x609) ? 2 : 0) ; sinon 2

## 4. Le cran de SEEDING qui rendait 1223 structurellement inerte

`observeBattle.hpMax` publie le maximum **INITIAL** ; `combatSnapshot.healthMax` publie le
**COURANT**. Mesuré après un marquage : `squadId 56 necroSpyder` → `observeBattle 11696/**9037**`
contre `combatSnapshot 11696/**11696**`.

Le port lisait le premier ⇒ `hp > hp_max` ⇒ l'unité passe pour **pleine** ⇒ tous les gates « a-t-elle
des PV manquants » se trompent (`AttackQuery$$EntityCanBeRepaired`, `HealableUnitsSelector`,
`FillUpStatComponent$$MaxFillUp`). Effet mesuré : `Repairable(carriers)` rendait `[]` et **1223 ne
réparait rien** là où le natif réparait 1457 PV. L'écart était **structurel** : c'est 1224 qui relève
le maximum, et le marquage est la condition d'entrée de 1223.

Correctif : `snapshot._hp_by_id(observe, snapshot)` — le snapshot **prime** quand il porte une valeur
exploitable ; `healthMax` absent ou `0` retombe sur `observeBattle` (une entité sans PV publie `0`,
ce n'est pas un maximum de zéro). **N'adresse pas #572-r1** (quand c'est le PORT qui pose le stat-mod
HEALTH, `ctx.stats[5]` ne se propage toujours pas à `HealthComponent`) — autre étage.

## 5. Le volet [C] ne posait AUCUN effet — `ActorSelector` rend VIDE

`IdunBattle.Entities.Selectors.ActorSelector$$Select`, `CasterSelector$$Select` et
`OwnerSelector$$Select` ont le **même corps** à l'offset lu près (`AbilityEntities` `+0x00` / `+0x08`
/ `+0x18`) : slot nul → **liste vide**. `entities_from_state` laissait `actor` à `None`, donc le port
ne posait pas 1547, là où le natif le pose sur la MoW casteuse (`Effect_Refresh e=79 ->
ReceiveEffect e=53`, `Effect_RemainingTurns=2`). Correctif local : `actor_id=caster_id`.

⚠ **Angle mort STRUCTUREL** : sur 1223, `Actor` n'est pas distinguable de `Target`/`Caster`, parce que
`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` commence par
`if (options.isSelfCasting != 0) return caster;` — et 1223 a `isSelfCasting = 1`. Diagnostic mesuré :
`target_id=53 ctx.target=53 ctx.actor=53`. Le mutant `Actor() -> Target()` passe donc **aveugle par
le natif**, pas par le témoin.

## 6. Confrontation live — `probe_902_reanimator.py`, quatre phases

| phase | témoin | résultat |
|---|---|---|
| `gates` | ORACLE NATIF `abilityTargets(…).fromHere` vs `get_invalid_target_reason`, avant/après marquage | 4 comparaisons, **4 égalités** — et les ensembles s'INVERSENT sur la cible marquée (1223 ∅→{56}, 1224 {54,56,58}→{54,58}) |
| `nrp` | delta PV + effets posés, offline vs live | `+2659` des deux côtés ; 1545 et 1546 présents des deux côtés |
| `beam` | delta PV + porteurs neufs de 1547, offline vs live | `{58: 1457}` des deux côtés ; 1547 → `{53}` des deux côtés ; **la cible du cast est u56 et l'unité réparée est u58** |
| `summons` | ensemble des ACTEURS (arbre porté) ; dégâts rapportés | acteurs `{79}` des deux côtés |

Le montant `2659` se re-dérive : `hp[50] = 1662` × `multiplier 160 %`. Le `4432` de 1223 :
`hpToRepair[50] = 2770` × 160 %, **capé** à ce qui manque (1457).

## 7. Mutants — ce qui MORD et ce qui est aveugle, avec la cause

| mutant | phase | verdict |
|---|---|---|
| filtre `EntitiesWithAnyEffect([1545])` retiré | `beam` | **MORD** (le port réparerait u54, +4432, que le natif ne touche pas) |
| `Repair(Repairable(carriers))` → `Repair(Target())` | `beam` | **MORD** |
| gate 1224 sans refus de re-pose | `gates` | **MORD** |
| gate 1223 sans exigence du marqueur | `gates` | **MORD** |
| variable `hp` → `hpToRepair` (1224) | `nrp` | **MORD** (709 vs 2659) |
| seeding max INITIAL (revert du §4) | `beam` | **MORD** |
| retrait du fil `actor_id=caster_id` | `beam` | **MORD** |
| filtre `UnitsWithTrait(carriers, Summon)` retiré | `summons` | **MORD** — mais seulement depuis que le montage marque AUSSI une machine **non-summon** : sans elle `carriers == summons` et le mutant passait aveugle |
| `Actor()` → `Target()` | `beam` | **AVEUGLE par le NATIF** (§5 : self-cast ⇒ les trois slots coïncident) |
| `statPart` Current → Initial | `summons` | **AVEUGLE — régime dégénéré** : le summon vient d'apparaître, `Attack_Current == Attack_Initial` |
| `asGroup` True → False | `summons` | **AVEUGLE — régime dégénéré** : un seul acteur, `execute_group([x]) == execute(x)` |
| override sur `MOVEMENT` au lieu d'`ATTACK` | `summons` | **AVEUGLE — régime dégénéré** : `dmgPct = 100` et `maxDmg_eff = 5318 > Attack ≈ 1996`, donc `Min(cap, Attack×100 %)` est l'**identité** |

Le témoin de `beam` a lui-même dû être **réparé** : il ne lisait que le côté live, donc le mutant
`Actor→Target` passait `rc 0`. Il confronte désormais les porteurs de 1547 des **deux** côtés — et
c'est ce renforcement qui fait mordre le mutant « retrait du fil actor ».

## 8. Ce qui n'est PAS couvert

* **La RÉSURRECTION** de 1547 : la classe d'effet n'est pas portée (`EFFECT_CLASSES` n'a ni 1545, ni
  1546, ni 1547) → `AddEffectOperation` pose un `BaseEffect` nu. L'effet **existe** des deux côtés
  (visible de `decisionView.effects`, du gate de re-pose, de `has_effect`) mais **n'agit** d'aucun.
  Filtre natif lu pour la fiche : `…ReanimationBeam_ReviveEffect$$CreateTargetFilter` =
  `AreFriends(Owner@+0x30, Target@+0x60) & HasTrait(Target, 5 Mechanical) & HasEffect(Target, 0x609,
  effectTarget 6)` ; `$$.ctor` = `ReviveEffect..ctor(this, 2, null, Nullable(AbilityOrEffect(this)), true)`.
* **Le +max HP de 1546** : le nœud DSL est porté, l'effet est posé, mais le maximum ne bouge pas
  côté port — porter la classe serait **inobservable** tant que #572-r1 tient (les stat-mods HEALTH
  vivent dans `ctx.stats[5]`, que rien ne relit pour les PV). Le volet PV **courants** ([C]), lui, mord.
* **Le bonus de réparation de 1545** (`EffectBonus.ForAddition(+hpToRepair)`) : non porté.
* **Le choix de CIBLE de l'attaque libre du summon** : écart d'étage `ComputerActionOperation`
  (moteur d'utilité, résidu #338, foyer partagé). Mesuré : à un seul summon en jeu, accord exact
  (`{49: 3680}` des deux côtés) ; à deux summons dont un seul marqué, le port choisit `u51` et le
  natif `u49`. **L'arbre de 1223 décide QUI agit** (gardé strictement) ; **`ComputerActionOperation`
  décide OÙ et SUR QUI** (rapporté, jamais fitté ici).
* **Les régimes non dégénérés du cap d'override** (`dmgPct < 100`, niveaux < 18 ; ou un porteur dont
  l'Attack dépasse `maxDmg_eff`) : non atteints par ce montage.
