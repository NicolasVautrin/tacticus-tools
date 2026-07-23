# Case #219 — Campagne T-RE des « exceptions dures » du port-roadmap (§5.2)

> Statut : **T-RE FAITE** (orchestrateur, 2026-07-23, build `gqfc5mff6c`, ghidra + gameconfig/i2 +
> RPC live `dumpEnum`). AUCUNE tranche portée ici — ce doc fixe les **verdicts de structure + VAs**
> pour le dispatch solver. Résultat global : **5 des 6 énigmes descendent en `[opus]`** (structure
> connue, templates existants) ; seule Chronometron reste `[fable]` (inchangée, non re-examinée).

## 1. MindControl (1164, genesMagus) — VERDICT : opus-solver

**PAS un owner-swap ECS** (hypothèse initiale réfutée). C'est un paquet debuffs + taunt bondé.

- `MindControlAbility.ExecuteBehaviour @1811f3ec0` (ctor `@1811f4510`, range 3 via config).
- Arbre (dur = `TurnsFromRounds(2)` = « this round and the next ») :
  1. `AddEffect(0x545=1349 MindControl_OutoingDamageReduction, caster -> Target@0x178, dur)`
  2. `AddEffect(0x546=1350 MindControl_IncomingDamageBonus,   caster -> Target,        dur)`
  3. `If(Not(HasTrait(Target, 0x19=25 Immune)), Inform(0xcb=203, cache) & If(cache,`
     `   AddBondEffect(0x1b=27 Taunted_OnlySpecificTargets, Target, bond=cache, dur)`
     ` & AddBondEffect(0x557=1367 MindControl_Taunter,      cache,  bond=Target, dur)))`
  où `cache = Cache(First(SortByFormula(Attackable(Friends(Self@0x148,`
  `AdjacentUnits(Target@0x178, ring1))), StatAmount(It@0x180, 5=Health))))` = **l'allié (du
  caster) adjacent à la cible avec la plus haute Health COURANTE** (i2 mot à mot).
- Effets (⚠ liaison id<->classe par l'enum `EffectType`, INVERSE de l'ordre des ctors) :
  - **1349** = Outgoing : `CreateEffectDamageBonusForAttack @180f5a0a0` =
    `EffectBonus.ForAddition(OwnerIsCaster, Negative(ConfigVar 0x12=dmgReduction))` — FLAT −582.
  - **1350** = Incoming : `@180f59ea0` = `EffectBonus.ForPercentIncrease(OwnerIsTarget,`
    `ConfigVar 0xa)` — +20 % dégâts subis.
  - **1367** MindControl_Taunter (sur l'allié) : `get_Range @180e06540` = 1 ;
    `CreateActiveCondition @180e06380` = `HasEffect(alive(bond), 27) &`
    `HasUsedActiveAbilityThisTurnTrigger(...)` (plomberie d'activation — à trancher au port).
- Gate `Immune` (trait 25) : la partie taunt SEULEMENT (« cannot be Taunted ») — les 2 debuffs
  s'appliquent AUSSI aux unités Immune.
- Légalité `GetDynamicInvalidTargetReason @1811f4300` (+ lambda `@180f29500`) : query vtable
  **token 0x7b** (famille BattleQuery #27) -> liste, `FilterInPlace(!IsSteppable)`, vide ->
  invalid(2). = « ennemi adjacent à ≥1 allié non-Steppable » (i2 : « adjacent to one or more
  friendly units »).
- Décision `MindControlPlaybook.EvaluateNonComparable @18114c310` : 1 action par cible éligible,
  utilité = `Fix64(GetStat(target, 5)=Health courante)` — patron identique VexillaMagnifica
  (`@18117f6f0`).
- **Substrat existant** : `TauntedEffect` composite 27 (`status.py`, mirror `@180f47510`),
  `AddBondEffect` (feuille DSL, CrushingClaws/GetEmRuntz), `SortByFormula`/`First`/`Cache`
  (`selectors.py`), `EffectBonus.ForAddition`/`ForPercentIncrease` (patrons mirrorés). À créer :
  2 classes d'effets 1349/1350, marqueur 1367, sélecteur `AdjacentUnits` ring-1 si absent,
  légalité (mirror direct — pas besoin du sous-système token générique).

## 2. ResurrectionOrb (1009, necroOverlord) — VERDICT : opus-solver

**Summon template pur, PAS de résurrection réelle** (flavor uniquement).

- `ExecuteBehaviour @181200140` : `Spawn(Caster@0x160, PickRandomly(CanAddUnit(AdjacentTiles(`
  `Caster)), N), 'necroSmnWarrior'=stringConst(0), WithStatsFromConfig)`.
- `N` = `GetMaxSummonsFormula @1812006c0` = `Min( Count(Friends(Caster,`
  `UnitsWithTrait(AllDeadOrResurrectedUnits, 1000=LivingMetal))) + StatAmount(Caster,`
  `0xc=12 TURNS_STARTED), Direct(6) )` — i2 mot à mot (« 1 per round started + 1 per friendly
  Living Metal defeated », cap 6 implicite).
- Décision : `ResurrectionOrbPlaybook` `EvaluateNonComparable @181155be0`, `GetNumSummons
  @181156060`, `GetNumPossibleSpawnTilesForTarget @181155f10`, `GetUseProbability @1811560f0`.
- **Nouveau** : sélecteur `AllDeadOrResurrectedUnits` — les morts sont DÉJÀ observables offline
  (decisionView garde les cadavres, `ctx.obs_units` isDead). Template : ScarabHive/GetEmRuntz +
  `_pick_randomly_n` (existant).

## 3. Waaagh (1058, orksWarboss Gulgortz) — VERDICT : opus-solver (2 tranches max)

`ExecuteBehaviour @18122b010` = **5 groupes séquentiels** (tags `Group` 0x22/0x25/0x23/0x20/0x28),
chacun sur un template existant :

1. **Spawn** (0x22) : `PickRandomly(CanAddUnit(AdjacentTiles(CasterTile@0x168)),`
   `nrOfSummons=numConst(0x10))` -> `Spawn('orksOrkBoys')`.
2. **Buff d'équipe** (0x25) : `GetBuffBehaviour @18122b900` (+ `GetBuffedUnitsSelector
   @18122bb30`) — Orks amis + amis adjacents : +1 Movement, +extraDmg flat, +1 hit, fin de tour.
3. **Charge** (0x23) : `MoveUnit(caster -> First(SortTilesByUtility(GetPossibleMovementTiles(`
   `Target@0x178) @18122c060, caster, 0x20)))` — `SortTilesByUtility` déjà porté (TheBetrayer).
4. **Attaque normale** (0x20) : `GetAttackBehaviour @18122b700` — pattern charge+attack = BlackRage
   (#217).
5. **Les Boyz jouent** (0x28) : `PerformAIAction(Friends(caster, UnitsWithVisualId(`
   `VisualUnitIdFromUnitId(Get('orksOrkBoys')))), 1, 1)` — cf. prérequis transverse §7.

Gate « n'a pas bougé » : `GetDynamicInvalidTargetReason @18122bc20`. Cousin même famille :
DaGreatWaaagh 1084 (`@1811ce840`, `GetMoveAndAttackBehaviour @1811cf1d0`, `SpawnBehavior
@1811cf2f0`, `AmountOfSummon2 @1811ce780`).

## 4. SupremeCommander (1028, astraCreed) — VERDICT : opus-solver

`ExecuteBehaviour @18120df30` (ctor `@18120e430`) :

- `count = nrOfSummons(numConst 0x10) + GetAbilityStatModification(caster, 0x10)` ;
  `range = numConst(0x16)`, overridé si `GetAbilityStatModification(caster, 0x16) != 0`
  — le canal « **Kell in play** » (+1 summon, range 3) passe par des ability-stat-mods.
- `Spawn(caster, PickRandomly(CanAddUnit(AdjacentTiles(caster)), count), 'astraSmnGuardsman')`
  en `ExecuteAtomic(0x48)`, puis `PerformAIAction(UnitsWithIds(SurroundingFriends(caster,`
  `casterTile, range, 1, 3), affectedUnitIds=strArrConst(0x3e)), 1, 1)` — les Guardsmen jouent.
- **Nouveau** : mirror `UnitExtensions.GetAbilityStatModification` (petit) + PerformAIAction (§7).

## 5. DutyEternal (1158, ultraDreadnought = MoW Galatian) — VERDICT : [opus] BLOQUÉ substrat

`ExecuteBehaviour @1811d6b70` : **transform MoW -> unité 3-hex stationnaire on-board** — PAS un
« summon à la mort » (hypothèse réfutée).

- Net : `RemoveMachine(Caster@0x160) & Spawn('ultraSmnDreadnought',`
  `ThreeTileUnitSpawnShape(Target@0x178), opts)` avec opts = `WithStatsFromConfig` +
  **questUnitId du caster transféré** (spawnOpts+0x50, flag +0x60=1) + `AddTrait(spawned@0x180,`
  `0x418=1048 Stationary)` + `AddTriggeredAbility(spawned, <1er élément d'une collection du
  caster>)` (probablement ses triggered configurés — détail au port).
- i2 : « Summons Galatian as a stationary unit in a 3 hex area… can no longer be used as a
  Machine of War ». Légalité `@1811d7040` ; décision `DutyEternalPlaybook @18112dfc0`/`@18112e730`.
- **Prérequis DURS nommés** : (a) substrat **unité multi-hex** (footprint 3 tuiles : occupation,
  adjacence, ciblage, spawn-shape) ; (b) harness **MoW** (le caster est le MoW hors-plateau —
  déploiement MoW arena résolu côté BC, mais le cast par le MoW reste à prouver en runner).
  Rejoint le groupe « MoW off-board » (PlagueburstMortar/DaemonicOrdnance/Malleus) avec un
  débloqueur EXPLICITE au lieu de « sémantique inconnue ».

## 6. Identités SavageEchoes / SternguardFocus — RÉSOLUES + enum mirrors STALES (fixés)

Le RPC live `dumpEnum` (session 71) donne la vérité du build — `data/il2cpp_enums.tsv` est
**stale sur la fin des enums** (placeholders `DA_Hero6_*` renommés depuis, entrées absentes) :

| Enum | id | tsv (stale) | live (vérité) |
|---|---|---|---|
| ActiveAbilityType | 1228 | DA_Hero6_Active | **SternguardFocus** (Ramus darkaSternguard) |
| ActiveAbilityType | 1230 | (absent) | **SavageEchoes** (Cezare bloodTerminator) |
| TriggeredAbilityType | 1545 | DA_Hero6_Passive | **SpecialIssueCombiMelta** (passif Ramus) |
| TriggeredAbilityType | 1548 | DA_Hero6_Active | **SternguardFocus_Cooldown** |
| TriggeredAbilityType | 1551 | (absent) | **RedRampage** (passif Cezare) |

Mirrors corrigés (commentés « fix live dumpEnum 2026-07-23 ») : `engine/entities/
active_ability_type.py`, `engine/entities/triggered_ability_type.py`, `scripts/python/
enum_maps.py`. Les deux abilities sortent des « exceptions sans id » et redeviennent des tâches
kit normales :

- **SavageEchoes 1230** : `ExecuteBehaviour @181204660`, `GetDamage @181204ab0`,
  `GetRegenerateCondition @181204bd0` ; playbook `MakeDamagePredictions @181158870`,
  `CalculateCustomUtility @1811586d0`. Config : 4x Eviscerate melee, `healthPct: 50`.
- **SternguardFocus 1228** : `ExecuteBehaviour @18120bca0`, `GetOverrideAttackDamageAmount
  @18120c020` ; triggered 1548 `CreateBehaviour @1811a2240` / `CreateTrigger @1811a2290`
  (`cooldownTurns: 3`) ; playbook `EvaluateNonComparable @18115ee70`, `GetUseProbability
  @18115f300`, `HasAdjacentDarkAngels @18115f4e0`.

À la prochaine mise à jour du jeu : régénérer le tsv (pipeline Il2CppDumper) — les fixes live
sont annotés pour survivre au diff.

## 7. Prérequis transverses AJUSTÉS (répercutés dans port-roadmap §4)

- **`PerformAIAction` — feuille unifiée + dispatch after-hit** : nœud commun à Waaagh (§3),
  SupremeCommander (§4), CultDemagogue (DÉJÀ mirroré : `genestealer.py`,
  `PerformAIActionBehaviour @1811cdc30`), au résidu act-again BlackRage (event 0x16,
  `status.py`) et au fork `PerformAIAttackFromCurrentPosition` (#217, case-217-thequickening §5).
  Le « fix-forward court » du fork est PROMU en sous-système P1 : une feuille contexte-aware
  partagée + dispatch after-hit, réutilisée par tous ces call-sites.
- **`GetAbilityStatModification`** (petit mirror `UnitExtensions`) : SupremeCommander (canal
  Kell) ; probablement réutilisé par d'autres interactions « si X en jeu ».
- **BattleQuery token 0x7b** s'ajoute à l'inventaire des tokens (#27 : 0x44/0x77/0x7c/0x7d/0x7f/
  0xb1) — mais MindControl n'en dépend PAS (mirror direct de sa légalité suffit).
- **Footprint multi-hex** : DutyEternal (§5) — seul item de la campagne à rester bloqué substrat.
