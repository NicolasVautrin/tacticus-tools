# case-66 — Sous-systeme REVIVE-EN-PLACE (base `ReviveEffect`) + TaintedNarthecium

**Statut : DEBLOQUEUR LIVRE.** Primitive `ReviveEffect` (revive-en-place) + `ReviveUnitOperation` portees
et validees sur le carrier phare **deathRotbone** (passif `TaintedNarthecium`). Les autres consommateurs de
la base = **retrofit** (taches backlog, cf. §6).

Build RE : `gqfc5mff6c`. Toutes VA en decimal-hex natif (RVA = VA - 0x180000000, calculee en code).

## 1. Artefact natif

`IdunBattle.Entities.Effects.ReviveEffect` = effet BOND (base `ABondEffect`) qui PORTE un trigger + un
behaviour. C'est une **famille** : la base fournit la STRUCTURE (trigger + behaviour DSL), chaque sous-classe
`Loki.*_ReviveEffect` surcharge le FILTRE + les vars (hp/chance).

| Element | VA | Role |
|---|---|---|
| `ReviveEffect$$.ctor` | `@180f46e60` | stocke {0x480=int, 0x484=int, 0x488=bool} (Narthecium & Tainted: 1,2,0 IDENTIQUES) |
| `ReviveEffect$$CreateTargetTrigger` | `@180f46d80` | `OnPreDeath(target, ignoreOverkill) & CanBeRevived(target) & CreateTargetFilter` |
| `ReviveEffect$$CreateTargetTriggerBehaviour` | `@180f46a70` | `Maybe(chance){ Revive(self,target,Min(reviveHP,maxHP),tile,sourceId) ; DeactivateEffect }` |
| `Narthecium_ReviveEffect` | ctor `@180f5ae20`, `GetReviveHP@180f5add0` (var 0x1d='hp'), `GetReviveChance@180f5ada0` (const 0x2a='chance'), filter `@180f5acf0` | Apothicaire (Imperial), « unless Overkilled », non-Mechanical |
| `TaintedNarthecium_ReviveEffect` | ctor `@180f70a90`, filter `@180f709b0` (source 0x42b=1067) | deathRotbone (Chaos), « even if Overkilled », Chaos-only |

### 1.1 Trigger (`CreateTargetTrigger @180f46d80`)
```
OnPreDeath(sel_dying, byte_ignoreOverkill)  &  CanBeRevived(target)  &  CreateTargetFilter
```
- `OnPreDeath @180df7f10` -> `OnDeathEvent(eventType=1, param_3=byte_738, param_4=0) @180df7ad0`. Le
  DECOMPILE de `OnDeathEvent` REVELE le gate overkill : `if param_3==0 -> AND NOT(HasFlag(dying, 8=overkill))`
  (« unless Overkilled ») ; `if param_3!=0 -> AUCUN gate overkill` (« even if Overkilled »). **`param_3` =
  virtuel `GetIgnoreOverkill @vtable+0x738`** — TaintedNarthecium retourne non-nul (even-if), Narthecium
  retourne 0 (unless). C'est LA distinction i2 encodee. `param_4=0 -> AND NOT(CurrentShield(dying,0x1b))`
  (shield==0, present pour les DEUX, implicite a la mort).
- `CanBeRevived @180deb4a0 -> CanBeRevivedTrigger @180f96b00 -> BattleQuery.CanBeRevived @181058a50` :
  `GetStat(unit,Health,0)<1` (mort) & `IsAffectedByHealType(healType)` & `NOT HasFlag(unit,0xd)` &
  `NOT HasTrait(PermaDeath=0x41a=1050)` & `NOT HasHealBlockers`.

### 1.2 Filtre TaintedNarthecium (`CreateTargetFilter @180f709b0`)
```
baseFilter & AreFriends(self,target) & HasTrait(target, Chaos=0x7ea=2026) & IsAdjacent(self,target,2)
```
(Narthecium `@180f5acf0` = idem SANS `HasTrait(Chaos)` -> tout ami non-Mechanical.)

### 1.3 Behaviour (`CreateTargetTriggerBehaviour @180f46a70`)
```
Maybe( chance=GetReviveChance ){
    op_add(
        Revive( self@0x148, target@0x178, Min(Direct(GetReviveHP), StatAmount(target,Health,max)),
                tile, AbilityOrEffect(sourceId) ) ,   # DSLFactory.Revive @180dfa4f0 -> ReviveBehaviour @180fd1230
        DeactivateEffect                              # DSLFactory.DeactivateEffect @180dede20 (once-per-turn)
    )
}
```
- `Maybe @180df6610 -> MaybeBehaviour.Execute @180fc9dc0` : UN tirage `NextBool(chance)` ; le func (op_add)
  ne s'execute QUE sur SUCCES. Donc un roll RATE ne consomme PAS le gate (re-roll a la mort adjacente suivante).
- `ReviveBehaviour.Execute @180fd1230` : re-clamp `Min(hp, GetMaxReviveAmount)` ou `GetMaxReviveAmount
  @180fd1a80 -> BattleQuery.GetMaximumReviveHealth @181063b10 = Min(maxHealth, configCap 0x12)`.
- `DeactivateEffect(factory,effect,false) @180dede20 -> ActivateEffectBehaviour(effect,active=false)` :
  desactive l'effet -> son trigger ne fire plus jusqu'a REACTIVATION au turn-start.

### 1.4 Operation imperative (`ReviveUnitOperation.Execute @180e91bd0`)
Params `(this, unit)`. HP data-driven (composant ReviveEffect). Sequence : `SetHealth @180e93450`
(`Min(hp, GetStat(unit,Health,max))`) -> flags `Remove(0xf), Remove(8=overkill), Add(0x14)` (l'unite
redevient VIVANTE ; **PAS 0xe AmbushConsumed** — un revive-en-place n'est PAS un ambush one-shot, contraste
`ResurrectUnitOperation @180e8e4c0` = Remove(6,0xf,8,0x1a,9)+Add(2,0xe)) -> `SetRevivePosition @180e936e0`
(repositionne sur la tuile de l'unite = **IN-PLACE**, position inchangee) -> emet `On(UnitRevived=46=0x2e)`.

### 1.5 i2 (authoritatif, confirme chaque gate)
- TaintedNarthecium : « An adjacent friendly **Chaos** unit that is defeated has a **{chance}%** chance to
  be revived with a maximum of **{hp} Health**, **even if Overkilled**. Can only be triggered **once per turn**. »
- Narthecium : « When an adjacent friendly **non-Mechanical** unit is defeated, it is immediately revived
  ... **unless Overkilled**. Can only be triggered once per turn. » (retrofit).

## 2. Frontiere DSL vs imperatif (#149)
- DECLARATIF (arbre DSL) : trigger (`OnPreDeath & CanBeRevived & filter`), `Maybe(75%)` PRNG, gate once-per-turn
  (`DeactivateEffect`), bypass overkill (byte 0x738) -> EMERGENT du `matches` + de l'arbre `Maybe(op_add(Revive,
  ConsumeReviveGate))`.
- IMPERATIF (mutateur ECS) : le revive lui-meme -> `ReviveUnitOperation` (repositionne=in-place, restaure HP,
  retire des morts). La feuille DSL `Revive` l'APPELLE (frontiere = le `.execute` de la feuille).
- **SEPARES** : `operations/revive.py` (Operation) != `triggers/loki/tainted_narthecium.py` (feuille + behaviour +
  trigger) — jamais fusionnes.

## 3. Port (fichiers)
| Fichier | Contenu |
|---|---|
| `runner/operations/revive.py` | `ReviveUnitOperation.execute` (mirror @180e91bd0, in-place) + `reset_revive_gates` (reactivation turn-start) |
| `runner/operations/triggers/loki/tainted_narthecium.py` | `TaintedNartheciumReviveAbility(TriggeredAbility)` + feuilles `Revive`/`ConsumeReviveGate` + `tainted_narthecium_revive_tree` |
| `runner/operations/triggers/dispatch.py` | `ABILITY_TRIGGERS["TaintedNarthecium"]` + `reset_revive_gates` dans `start_turn_triggers` |
| `runner/components.py` | `UnitComponent.revive_used_this_turn` (gate once-per-turn, reset turn-start) |

- Route = `ABILITY_TRIGGERS` (TaintedNarthecium est un **passiveAbility** de deathRotbone, PAS un trait ni un
  effet capte de decisionView) — comme DestroyerHive/MartialApotheosis. `matches`=checks directs mirroir de
  chaque noeud (idiome ActOfFaith/FinalJustice) ; `execute_behaviour`=arbre DSL.
- reviveHP = `ability_var("TaintedNarthecium","hp", passive_level, mult)` (var 'hp' dans
  `variablesAffectedByRarityBonus` -> rarity-scale). chance = `constants.chance`=75.
- once-per-turn = `owner.revive_used_this_turn` : pose True par `ConsumeReviveGate` sur SUCCES du Maybe, remis
  False pour toutes les unites au turn-start (`reset_revive_gates`, patron `reset_times_attacked`).

## 4. Validation (probe `probe_66_revive.py`, live-agreement offline sur etat LIVE-capture)
Build deathRotbone + deathBlightbringer(Chaos) + eldarRanger(Xenos) rank17 ; load_state (board/stats/traits
REELS) ; positions DRIVEES ; mort simulee via `after_death_triggers` ; RNG seedee (patron etat_avec/etat_flip).
deathRotbone level 50 mult 180 -> **reviveHP=round(2715x1.8)=4887**, chance=75.

| Gate | Resultat |
|---|---|
| base (RNG True) | alive=True, hp=4887=min(4887,maxHP), **MEME position** (5,7)->(5,7), TaintedNarthecium fired |
| no-revive (RNG False) | alive=False (roll rate) |
| proba ~75% (400 seeds) | **77.5%** (310/400) dans la bande 70-80% |
| once-per-turn | revive1=True, gate consomme, revive2=**False** (2e mort meme tour), reset->revive3=True |
| even-if-Overkilled | overkill=True -> alive=True (aucun gate overkill) |
| Chaos-only | ally Xenos tue -> alive=False (pas de revive) |
| adjacence | ally Chaos dist=3 -> alive=False (IsAdjacent 2) |
| CanBeRevived | ally Chaos Mechanical (toggle) -> alive=False |
| clamp maxHP<reviveHP | offline : maxHP=1200<4887 -> hp=1200 (SetHealth clamp), in-place |

Zero-reg (tests cibles) : `test_revitalizing_malignancy_live` (MEME carrier deathRotbone) + `test_finaljustice_live`
(dispatch PreUnitDeath partage) + `test_ambush_migration_live` (resurrect voisin) + `test_act_of_faith_live`
(PreUnitDeath + Maybe) = **9 tests PASS**. Import smoke : EFFECT_CLASSES(79)/dispatch intacts.

## 5. Residus / limites documentes
- **Flag 0xd** (`CanBeRevived`) & **HasHealBlockers** non modelises : le flag overkill 0xd n'est pas encore pose
  a l'instant de l'OnPreDeath (le revive fire AVANT le clear-dead qui le pose) -> non-bloquant pour ce port.
- **Shield gate** `NOT(CurrentShield(dying,0x1b))` : implicite a la mort (shield==0), non modelise.
- **GetMaximumReviveHealth configCap (0x12)** : le port clampe a `maxHealth` seul ; le cap config 0x12 (~%
  ou global) est >= maxHealth dans les cas testes (hp==reviveHP quand reviveHP<maxHP). A raffiner si un live
  montre un cap inferieur.
- **once-per-turn = reset a CHAQUE turn-start** (les deux camps) : modelise « once per turn » ; la periode
  exacte de reactivation native (turn-start owner vs tout turn-start) n'est pas discriminee par le decompile
  seul -> le comportement observable (2e mort meme tour -> pas de revive) est valide ; le raffinement
  cross-turn est un residu si un walk multi-tour l'exerce.

## 6. Retrofit — autres consommateurs de `ReviveEffect` (taches backlog `[opus]`)
Tous heritent la base (structure DEJA portee) ; ne restent que le FILTRE + les vars + le gate overkill/HealType.
Chacun EXIGE un carrier spawnable validable (cf. `feedback_no_unvalidatable_ability_ports`).

| Consommateur | VA | Specifite |
|---|---|---|
| `Narthecium_ReviveEffect` (ultraApothecary, Imperial) | `@180f5ae20/@180f5acf0` | non-Mechanical, **unless Overkilled** (byte 0x738=0), chance=100 |
| `ReanimationBeam_ReviveEffect` | ctor `@180f67b90`, filter `@180f67ac0` | carrier a identifier |
| `PhoenixGem_CanReviveEffect` | ctor `@180f5e680`, `CreateHandleTriggerAbilitiesInternal @180f5e4a0` | variante « Can »-revive (PhoenixGem_ReviveAbility `@181111610`/`@1811117b0`) |
| `FuelledByFury_CanReviveEffect` | `CreateHandleTriggerAbilitiesInternal @180f4ab10` | RitesOfMorkai / FuelledByFury (spaceWolfPriest `RitesOfMorkai 1211`) ; `FuelledByFury_ReviveAbility @180f810c0/@180f81250` |
| `GhostReviveAbility` | `CreateBehaviour @180f83600`, `CreateTrigger @180f83800` | thousTerminator `TimeFlux` |

NB : `RitesOfRestoration` (deja porte) = **Resurrect** (tile-choice/ambush), sous-systeme DISTINCT
(`ResurrectUnitOperation`) — NE PAS confondre avec Revive-en-place.
