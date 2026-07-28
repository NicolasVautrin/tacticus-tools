# case-66 — Sous-systeme REVIVE-EN-PLACE (base `ReviveEffect`) + TaintedNarthecium

**Statut : SOUS-SYSTEME REVIVE COMPLET — DEBLOQUEUR + RETROFIT #79 + FERMETURE #88/#89 + RESIDU A1
(#88, 2026-07-28) + RESIDU A2 (#213, 2026-07-29).** Les DEUX consommateurs hors-famille sont
desormais portes et valides live. **A1 `FuelledByFury`** (§8.1) : les 3 << blocages >> de sa fiche
etaient PERIMES ou faux — l'emetteur d'`On(PendingDeathAdded = 3)` est
`IdunBattle.Operations.RecordKillOperation$$Execute`, le `TriggeringAbility` a desormais un foyer
unique, et l'effet 1324 est CAPTE live (rien a poser). **A2 `GhostRevive`/`TimeFlux`** (§8.2) : le
SEUL revive NON-IN-PLACE du binaire, porte avec son vecteur `On(PreUnitMove)`, son effet porte par une
TUILE (5 retraits) et le mutateur `SetRevivePosition` — VALIDE LIVE sur deux couples (board, seed) ou
la tuile de mort et la tuile de revive DIFFERENT. Primitive `ReviveEffect`
(revive-en-place) + `ReviveUnitOperation` portees et validees sur le carrier phare **deathRotbone**
(passif `TaintedNarthecium`). Le retrofit #79 a porte **Narthecium** (LIVE-validee end-to-end),
**RitesOfMorkai**, **ReanimationBeam** et **PhoenixGem** (mirror + offline, carriers non montables).

La reprise **#88/#89** a ferme les trois hypotheses restantes **par LECTURE** (§6.0, §7) :
`get_ReviveOnOverkill` et `get_HealType` de ReanimationBeam/RitesOfMorkai (**B1** — et `heal_type=1`
levait un **no-op garanti**), `GetReviveChance` litteral **= 100** (**B2**), le vecteur
`On(UnitRevived)` desormais dispatche (**B3**) ; et surtout elle a tranche la **semantique de la garde
de `KillUnitOperation`** (**volet C**) : le champ `Nullable<ReviveData>` @`UnitComponent+0xa8` fait
qu'**un revive pose pendant `On(1)` ANNULE la mort** (ni `On(2)`, ni `On(0)`, ni `On(55)`, ni `On(54)`).
Restent **FuelledByFury** et **TimeFlux** en residus documentes (artefacts DISTINCTS de `ReviveEffect`,
chantiers propres) — cf. §8.

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

## 6. Retrofit #79 — les consommateurs de la base

### 6.0 Les virtuels de `ReviveEffect`, resolus par LECTURE (jamais par deduction)

`CreateTargetTrigger @180f46d80` appelle 3 virtuels ; `CreateTargetTriggerBehaviour @180f46a70` en appelle
2 de plus. Le dump metadata NE LES LISTE PAS (corps triviaux `return N` deduplique par ICF).
**Alignement : la vtable d'un `Il2CppClass` commence a `+0x138`, chaque entree fait `0x10`
(`{methodPtr, MethodInfo*}`) ⇒ les slots sont a `...8` (0x738 = slot 96, 0x748 = 97, 0x758 = 98,
0x768 = 99, 0x778 = 100), pas a `...0`.**

**DEUX chemins de lecture, croises** :
1. **LIVE** — RPC `resolveVtableSlot` (lecture de pointeurs, ZERO invoke), probe
   `probe_79_revive_vtable.py`. Ne marche que sur une classe **INITIALISEE** : `ReanimationBeam_ReviveEffect`
   et `RitesOfMorkaiEffect` rendent des slots **NULS** (carriers hors pool ⇒ classes jamais construites).
2. **OFFLINE (#88-#89)** — la table `methodPointers` d'IL2CPP est presente **telle quelle dans
   `GameAssembly.dll`** (pointeurs en VA image-base `0x180000000`), donc lisible pour n'importe quelle
   classe. Le bloc d'un `*_ReviveEffect` a la forme (ordre de declaration valide sur la BASE @file
   `0x30fdb28`, ou les **trois** entrees nulles correspondent exactement aux **trois abstraits** que la
   lecture LIVE montre sur la base) :
   `[get_ReviveOnOverkill] [get_HealType?] .ctor CreateTargetFilter GetReviveChance GetReviveHP`.
   Le **type de retour** desambigue les deux entrees triviales : `get_ReviveOnOverkill` renvoie un
   **bool** (corps 1 octet : `@1802b15a0` = `return 0`, `@1802b1590` = `return 1`) ; `get_HealType`
   renvoie un **int** (corps 8 octets : `@1802b15b0` = `return 0`, `@1802cca80` = `return 1`).
   Validation croisee : les valeurs lues pour Narthecium (`0`) et TaintedNarthecium (`1`) coincident
   avec celles que `resolveVtableSlot` rend LIVE sur le slot `0x738`.

| slot | methode | base `ReviveEffect` | Narthecium | TaintedNarthecium | RitesOfMorkai | ReanimationBeam |
|---|---|---|---|---|---|---|
| +0x728 | `get_ActivateOnResurrect` | `@1802b15a0` = 0 | idem | idem | idem | idem |
| +0x738 | `get_ReviveOnOverkill` | `@1802b15a0` = **0** | **0** | `@1802b1590` = **1** | **0** (lu) | **0** (lu) |
| +0x748 | `get_HealType` | `@1802b15b0` = **0** | herite 0 | herite 0 | herite 0 | `@1802cca80` = **1** |
| +0x758 | `CreateTargetFilter` | **abstrait** `@1801e6080` | `@180f5acf0` | `@180f709b0` | `@180f69c10` | `@180f67ac0` |
| +0x768 | `GetReviveChance` | **abstrait** `@1801e6080` | `@180f5ada0` | `@180f5ada0` (ICF) | `@1806e1ac0` | `@1806e1ac0` |
| +0x778 | `GetReviveHP` | **abstrait** `@1801e6080` | `@180f5add0` | `@180f5add0` (ICF) | `@180f5add0` | `@180f5add0` |

(blocs `methodPointers` : base `0x30fdb30`, Narthecium `0x30fffc0`, TaintedNarthecium `0x3100e28`,
RitesOfMorkai `0x3100878`, ReanimationBeam `0x3100698`.)

`get_ReviveOnOverkill` EST le `param_3` de `OnDeathEvent @180df7ad0` : `0` → le trigger ajoute
`NOT(HasFlag(dying,8=overkill))` (« unless Overkilled ») ; `1` → aucun gate (« even if Overkilled »).

**`get_HealType` n'est PAS toujours 0** (residu #89/B1 **ferme**) : ReanimationBeam l'override a **1**.
`IsAffectedByHealType @180ed77d0` est un mirror 1:1 a trois branches —
`HasTrait(AffectedByHealAndRepair=0x421)` → vrai ; `healType==0 && IsMechanical` → faux (Heal) ;
`healType==1 && !IsMechanical` → faux (Repair) ; sinon vrai (`healType==2`, PhoenixGem : aucun filtre).
Avec l'ancien `healType=0` code en dur, `CanBeRevived` rejetait precisement les cibles **Mechanical** que
le `CreateTargetFilter` de ReanimationBeam **exige** ⇒ ce revive etait un **NO-OP GARANTI**. Corrige.

**Deuxieme discriminant, lu dans `CreateTargetTriggerBehaviour @180f46a70`** : le champ `removeEffect`
(0x488, pose au ctor) choisit le 2e volet du `op_add` — `false` → `DeactivateEffect` (once-per-TURN,
reactive au turn-start) ; `true` → `BaseEffect.GetRemoveEffectBehaviour` → `RemoveEffect` (one-shot
**definitif**, « the first time … »).

**Troisieme point (piege), residu #89/B2 FERME** : `GetReviveChance` est **ABSTRAIT dans la base**
(slot 0x768 = stub `@1801e6080`, `MethodInfo` nul — lu LIVE) ⇒ **toute** sous-classe concrete DOIT
l'implementer. Le corps partage `@180f5ada0` = `GetNumberConstant(config, 0x2a='chance')` →
`GetStringConstant @181576bb0` **LEVE une `System.Exception`** si la cle est absente. Les sous-classes
dont le gameconfig n'a pas de constante `chance` (RitesOfMorkai `{range,nrOfRounds}`, ReanimationBeam
`{initialCooldownTurns,munitionsCost}`) ne peuvent donc PAS le partager : elles overrident par un corps
litteral. Ce corps est **@1806e1ac0**, dont les octets sont `b8 64 00 00 00 c3` = **`mov eax,100 ; ret`**.
⇒ `default_chance = 100` **n'est plus une hypothese justifiee par l'i2 : c'est une lecture du binaire.**

### 6.1 Organisation du port (mirror de l'organisation native)

| Fichier | Artefact natif |
|---|---|
| `runner/operations/triggers/revive_effect.py` | **BASE** `IdunBattle.Entities.Effects.ReviveEffect` : feuilles `Revive`/`ConsumeReviveGate`/`RemoveReviveEffect`, `create_target_trigger_behaviour` (@180f46a70), `can_be_revived` (@181058a50), coeur `_ReviveEffectCore` + les 2 rails `ReviveEffectAbility` (passif) / `ReviveEffectTrigger` (effet pose) |
| `.../triggers/loki/narthecium.py` | `Narthecium_ReviveEffect` (@180f5ae20 / @180f5acf0) |
| `.../triggers/loki/tainted_narthecium.py` | `TaintedNarthecium_ReviveEffect` (@180f70a90 / @180f709b0) |
| `.../triggers/loki/rites_of_morkai.py` | `RitesOfMorkaiEffect` (@180f69c30 / @180f69c10) |
| `.../triggers/loki/reanimation_beam.py` | `ReanimationBeam_ReviveEffect` (@180f67b90 / @180f67ac0) |
| `.../triggers/loki/phoenix_gem.py` | `PhoenixGem_ReviveAbility` (@1811117b0 / @181111610) + marqueur `PhoenixGem_CanReviveEffect` (@180f5e680 / @180f5e4a0) |

Deux rails parce que le natif pose le meme `ReviveEffect` de deux facons : d'office par un
**passiveAbility** (Narthecium/TaintedNarthecium → `ABILITY_TRIGGERS`) ou par une **ability ACTIVE**
(RitesOfMorkai/ReanimationBeam → `EFFECT_TRIGGERS[effectType]`). Consequence de fidelite : pour le rail
EFFET, `GetReviveHP` lit l'`abilityState` **porte par l'effet** (niveau/multiplicateur du POSEUR), pas
ceux du porteur — `revive_level()` par rail.

### 6.2 Etat par consommateur

| Consommateur | Carrier | Pool | Voie | Gate overkill | Gate re-fire |
|---|---|---|---|---|---|
| `Narthecium_ReviveEffect` @180f5ae20/@180f5acf0 | `ultraApothecary` | **OUI** (hero) | **LIVE-validee** | **unless** (0x738 = `@1802b15a0` = 0, lu) | once-per-turn (`removeEffect`=0) |
| `TaintedNarthecium_ReviveEffect` @180f70a90/@180f709b0 | `deathRotbone` | OUI | LIVE (case-66) | even-if (0x738 = `@1802b1590` = 1, lu) | once-per-turn |
| `RitesOfMorkaiEffect` @180f69c30/@180f69c10 | `spaceWolfPriest` | **NON** | mirror + offline | **unless** (0x738 = `@1802b15a0` = 0, **lu** dans methodPointers @0x3100878) | one-shot (`removeEffect`=1) |
| `ReanimationBeam_ReviveEffect` @180f67b90/@180f67ac0 | `necroReanimator` (MoW) | **NON** (+ blocage harnais MoW hors-plateau) | mirror + offline | **unless** (0x738 = `@1802b15a0` = 0, **lu** @0x3100698 — residu #89/B1 **ferme**) | one-shot (`removeEffect`=1) |
| `PhoenixGem_ReviveAbility` @1811117b0/@181111610 | relic sur `eldarAutarch` | unite OUI, **relic non posable** | mirror + offline | **even-if** (`OnPreDeath(1)` litteral, lu) | one-shot par BATAILLE (retrait du marqueur 1451) |

Filtres (`CreateTargetFilter`, virtuel +0x758) :
- Narthecium : `baseFilter & AreFriends & IsAdjacent(2)` — **pas** de `HasTrait` ; le « non-Mechanical »
  de l'i2 vient du noeud `CanBeRevived` de la base (`IsAffectedByHealType(0)`), pas du filtre.
- TaintedNarthecium : idem **+ `HasTrait(target, Chaos=0x7ea)`**.
- RitesOfMorkai : `get_OwnerIsTarget` (self-revive ; la portee a ete appliquee a la POSE).
- ReanimationBeam : `AreFriends & HasTrait(target, Mechanical=5) & HasEffect(target, 1545
  NanoscarabRepairProtocols)` — l'INVERSE de Narthecium sur le Mechanical, **coherent** avec son
  `get_HealType = 1` (Repair) ; c'est le meme filtre exprime deux fois (filtre + `CanBeRevived`).
- PhoenixGem (hors famille) : `OnPreDeath(ignoreOverkill=TRUE) & OwnerIsTarget & HasEffect(self, 1451)`.
  Son `CreateBehaviour @181111610` passe des LITTERAUX au noeud `Revive` : `healType = 2` (aucun filtre
  heal/repair) et `priority = -1000` (`0xfffffc18`, la plus BASSE — cf. `IsPreferredRevive` §7.1).

### 6.3 Validation

- **Narthecium — LIVE end-to-end** (`probe_79_narthecium_live.py`, 3 runners) : ennemi mis au contact,
  degat MESURE (12327), 3 scenarios. `A` PV=10477 et `B` PV=7396 (coup letal, `dmg < 2 x PV` ⇒
  non-overkill) → l'allie est **VIVANT** a `hp=5983` **dans les DEUX cas** (valeur ABSOLUE ⇒ c'est un
  revive, pas un degat amorti) et **sur sa propre tuile** ; `C` PV=3698 (`dmg >= 2 x PV` ⇒ overkill) →
  **MORT**. Confrontation offline : `ability_var('Narthecium','hp', level=50, mult=180) = 5983` = la
  valeur live, au PV pres.
- Tests cibles : `test_narthecium_revive_live.py` (9), `test_tainted_narthecium_revive_live.py` (11,
  **garde zero-regression** #66 + 3 offline `IsPreferredRevive`/garde/clamp),
  `test_rites_of_morkai_revive_live.py` (4), `test_revive_retrofit_offline_live.py` (10 :
  ReanimationBeam + PhoenixGem, dont les discriminants `heal_type=1` et « marqueur survivant a un revive
  etranger »), `test_revive_cancels_death_events_live.py` (3, cf. §7.3) = **37 PASS**.

## 7. Le PIVOT `Nullable<ReviveData>` @`UnitComponent + 0xa8` (#88-#89, 2026-07-25)

La reprise #88/#89 a montre que la vue « la feuille `Revive` appelle l'Operation » etait une
**simplification** : le sous-systeme natif est en DEUX TEMPS autour d'un champ d'etat.

### 7.1 Les trois fonctions qui manipulent le champ

| role | fonction native | ce qu'elle fait |
|---|---|---|
| ECRITURE | `ReviveBehaviour.Execute @180fd1230` | pour chaque cible : `amount = Min(formule, GetMaxReviveAmount @180fd1a80)`, construit la `ReviveData`, et si `IsPreferredRevive @180fd1b50` ECRIT `unitComponent + 0xa8 .. +0xe8`. **AUCUNE mutation de PV/flag/position.** |
| GARDE | `KillUnitOperation.Execute @180e76470` @0x180e76c9e | `if (!pendingRevive.HasValue) { ...toute la suite de la mort... }` |
| LECTURE + PURGE | `ReviveUnitOperation.Execute @180e91bd0` | garde @0x180e91e8a (`!HasValue` → `Logger.Error` + return), applique (SetHealth/flags/SetRevivePosition), emet `On(UnitRevived=0x2e)` @0x180e92691, PUIS remet les 9 qwords a 0 @0x180e92977+ |

Identification du champ : le meme helper `thunk_FUN_1801f3000(ptr, <fieldInfo>)` est utilise sur
`unitComponent + 0x98` dans `UnitComponent.Copy @180fac610`, ou il est immediatement suivi de
`System.Nullable<...>.get_Value` ⇒ c'est le `hasValue` d'un `Nullable<T>`. Le champ @0xa8 est le suivant
(le `Nullable<AttackHit>` @0x98 fait 0x10) et les trois fonctions ci-dessus lisent/ecrivent la MEME
plage `0xa8..0xe8` (9 qwords) avec la MEME classe generique (`DAT_1831e4778`).

`IsPreferredRevive @180fd1b50` : `!existing.HasValue` → vrai ; sinon compare la **priorite** (champ
`+0x18` de la `ReviveData`), et a egalite garde le plus GRAND `amount`. Seul `PhoenixGem` pose une
priorite non nulle : **-1000** ⇒ n'importe quel autre revive lui est prefere.

### 7.2 Consequence : **un revive ANNULE la mort** (residu #89/C ferme)

Ordre d'instruction lu dans `KillUnitOperation.Execute @180e76470` :

```
On(1  = PreUnitDeath)    ret 0x180e76c4c   <- profondeur d'accolades 7  (AVANT la garde)
[GARDE  !pendingRevive.HasValue]  @0x180e76c9e
On(2  = PreUnitDeath_2)  ret 0x180e76dea   <- profondeur 9  (DANS la garde)
On(0  = UnitDeath)       ret 0x180e77269   <- profondeur 9
On(55 = UnitDefeated)    ret 0x180e7731c   <- profondeur 9
On(54 = PostUnitKill)    ret 0x180e7749c   <- profondeur 9
```

Il n'y a **aucun `else`**. Sont donc AUSSI sous la garde : `RegisterDefeatedUnit`,
`UnitFlagsComponent.Remove(0xf)` / `Add(6)`, `KillUnitOperation.RemoveEffects`. ⇒ **si un consommateur
d'`On(1)` (ReviveEffect, PhoenixGem, …) pose une `ReviveData`, la mort est ANNULEE** : pas de death-nova
(`On(2)`), pas de decoy Ambush (`On(55)`), pas de bookkeeping de mort.

Le drain natif est la 2e phase de `InputMessageProcessor.VerifyDeaths @180ebb0a0` :
`RunPhase(0xc)` = les kills (lambda `<VerifyDeaths>b__0 @180ecb870` → `KillUnit`, slots 0x60/0x61) puis
`RunPhase(0xd)` = les revives (→ `OperationProcessor.ReviveUnit @180e0b510` → `ReviveUnitOperation`).
Le port COLLAPSE garde + drain dans `kill_unit_revive_gate` (`operations/revive.py`), appelee par
`AttackDamageOperation._fire_death_if_killed` juste apres `On(1)` — c'est l'ordre observable natif.

### 7.3 Validation du volet C

`test_revive_cancels_death_events_live.py` (scenario **crafte**, distinct de ceux qui ont servi a batir
le port) : `ultraApothecary` (Narthecium, chance 100) + `deathPutrifier` (trait `PutridExplosion`, nova
`On(2)`, **non-Mechanical** donc revivable) rendus adjacents, toutes les autres unites ecartees ; la mort
passe par le VRAI chokepoint `_apply_damage_pipeline`.
- revive actif → Putrifier **vivant** a `min(reviveHP,maxPV)`, `kill_cancelled_by_revive` signale, **aucun**
  hit `PutridExplosion`, PV de l'Apothecary **inchanges** ;
- face NEGATIVE sur le MEME etat (`revive_used_this_turn=True`) → Putrifier **mort**, nova **emise**, PV
  de l'Apothecary **en baisse** ⇒ la garde discrimine, elle ne supprime pas en bloc ;
- garde de re-armement : apres `reset_revive_gates`, la mort est de nouveau annulee.

### 7.4 Le vecteur `On(UnitRevived = 46)` (residu #89/B3 ferme)

`ReviveUnitOperation` emet `On(0x2e)` @0x180e92691 **avant** la purge du champ. Le port le dispatche
desormais (`unit_revived_triggers`, `triggers/dispatch.py`), en passant le `sourceId` de la `ReviveData`
comme payload `CurrentAbilityIs`. Consequence : les DEUX triggers de
`PhoenixGem_CanReviveEffect.CreateHandleTriggerAbilitiesInternal @180f5e4a0` sont portes **a part** —
`On(0x2e) & OwnerIsTarget & CurrentAbilityIs(0x5b2=1458)` → `RemoveEffect(1451)` et
`On(0x2f=UnitResurrected) & OwnerIsTarget` → `RemoveEffect(1451)` — au lieu d'etre chainees en dur au
behaviour du revive. Discriminant desormais exprimable (et teste) : un revive venu d'AILLEURS emet bien
`On(0x2e)` mais **ne consomme pas** le marqueur PhoenixGem.
Corollaire structurel : `EFFECT_TRIGGERS` mappe un `effectType` vers une **LISTE** de triggers, mirror de
l'`ArraySet` que renvoie `CreateHandleTriggerAbilitiesInternal`.

## 8. Les deux consommateurs HORS famille `ReviveEffect` (#88 A1 / A2)

Ils appellent bien `DSLFactory.Revive` → `ReviveUnitOperation`, mais ne sont **pas** des sous-classes de
`ReviveEffect` : ce n'est pas un retrofit « filtre + vars + gate », c'est un chantier propre par item.

### 8.1 `FuelledByFury` (`ultraTitus`) — **PORTE ET VALIDE LIVE (#88 A1, 2026-07-28)**

i2 (authoritatif) : « The first time each turn that Titus is defeated he cannot be **Overkilled**.
The first time each turn **he defeats an enemy with an attack triggered by Final Vengeance** he is
immediately revived with a maximum of {hp} Health. » — `ultraTitus.traits = [Hero, BeastSlayer,
**FinalJustice**]`, `passiveAbilities = [FuelledByFury]`.

Arbres LUS :
- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility$$CreateTrigger` =
  `On(3 = PendingDeathAdded) & HasEffect(self@0x148, 0x52c = 1324 EffectType.FuelledByFury_CanRevive, 1, 6)
   & AreEqual(caster@0x160, self@0x148) & TriggeringAbilityIs(AbilityOrEffect(0x400 = 1024 =
   TriggeredAbilityType.FinalJustice))`
- `...FuelledByFury_ReviveAbility$$CreateBehaviour` =
  `Revive(self@0x148, self@0x148, ConfigVar(0x1d='hp', abilityState@0x20), healType=0,
   Nullable(AbilityOrEffect(this.Id = 1251)), 0, priority=0, 0)` — **self-revive inconditionnel**.
- `IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal`
  = `ArraySet{ On(0x21=AbilityInit) & OwnerIsActor → ActivateEffect(self@0x150) ;
  On(0x12=TurnStart_EffectActivation) → ActivateEffect(self@0x150)  [le « first time each TURN »] ;
  On(0x2e=UnitRevived) & OwnerIsTarget & CurrentAbilityIs(0x4e3=1251) → DeactivateEffect(self@0x150) }`.

**Les 3 << blocages >> de la fiche d'origine, tranches un par un :**

1. **L'emetteur d'`On(PendingDeathAdded = 3)` EST LOCALISE** :
   `IdunBattle.Operations.RecordKillOperation$$Execute` (appele par
   `Core.Services.OperationProcessor$$RecordKill`). Sequence lue : gate `UnitFlagsComponent.Has(dying, 6)`
   → compteurs de kills du `PlayerComponent` (`+0x90`, `+0x94`) → `UnitFlagsComponent.Add(dying, 0xf)` →
   `MatchState.AddDeath(killer, dying, …)` → **publie `On(3)`** avec le triplet d'entites
   `(killer, killer, dying)`. La file n'etant drainee que par
   `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` → `KillUnitOperation$$Execute`, **`On(3)`
   precede STRICTEMENT `On(1)`**.
   *Comment il a ete trouve* (methode reutilisable, cf. `probe_88_event_emitters.py` /
   `probe_88_dispatch_scan.py` / `probe_88_on3_publishers.py`) : la publication d'un evenement de
   trigger n'a **pas une forme d'appel unique** — l'`eventType` est tantot en `r9d` (thunk
   `FUN_180026490`, 55 sites, 48 des 77 `EventTriggerType`), tantot en 9e argument (`FUN_180028f50`),
   tantot en 5e argument d'un slot d'interface **INLINE** (`MoveUnitOperation$$
   EvaluateArrivedAtFinalTileTrigger`, `RecordKillOperation$$Execute`). Ne scanner qu'une forme donne un
   FAUX NEGATIF — c'est exactement ce qui avait fait conclure « non localise ». Le balayage qui a
   tranche cherche l'immediat dans **tous** les slots d'argument de pile (`C7 44 24 N imm32`) **et** en
   `r9d`, avec des **temoins obligatoires** (`0x1c`, `0x2f`, `0x2c`) pour prouver que le scan voit bien
   les sites inlines. ⚠ le code IL2CPP vit dans la section **`il2cpp`**, pas `.text`.
2. **`TriggeringAbilityIs` a desormais un contexte** : `AbilityEntities.TriggeringAbility` est ecrit par
   `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute`, qui pose
   `Nullable<AbilityOrEffect>(ability.Id)` **avant** d'executer le behaviour (puis une 2e fois avant
   `On(0xd)`). Foyer UNIQUE cote port : `triggers/dispatch/core.py::evaluate_trigger_operation`
   (sauvegarde/restaure `state.triggering_ability` autour de `execute_behaviour` — l'imbrication native
   est ainsi reproduite). Chaque classe declare son id via `TRIGGERED_ABILITY_ID` (ici `FinalJustice`
   = 1024). Non renseigne = None → gate positif faux, gate negatif vrai (degradation NOMMEE).
3. **La pose de l'effet 1324 n'a jamais eu besoin d'etre portee** : le jeu la fait a l'init de l'unite
   (`On(0x21=AbilityInit) → ActivateEffect`), donc le snapshot live la CAPTE — `ultraTitus` arrive dans
   le runner avec `FuelledByFury_BlockOverkill` **et** `FuelledByFury_CanRevive`. Le port n'a qu'a
   enregistrer les 3 triggers d'etat sous `EFFECT_TRIGGERS[1324]` et lire `BaseEffect.active`.

**BUG REEL leve au passage — la riposte `FinalJustice` etait un NO-OP SILENCIEUX offline.** Le gate
acteur-mort de `damage_ops/normal.py` (#133, mirror de `if (options@0x4a == 0 && IsUnit(caster) &&
IsDead(caster)) return 0` d'`ActiveAbilityOperation$$ExecuteInternal`) supposait qu'« aucune voie du
port ne pose ce flag » — or `IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$Execute` FORCE
un octet a `1` dans les `AbilityOptions` qu'il assemble (`uStack_210._0_2_ =
CONCAT11(*(behaviour + 0xa8), 1)` — le SEUL octet en dur d'une struct autrement recopiee champ par
champ). Mesure live : `ultraTitus` a `hp = 0` porte bel et bien sa riposte, pour **10502** de degat, et
TUE. Le trou n'etait visible dans AUCUN test : `test_finaljustice_live` appelle `after_death_triggers`
sur un Kharn encore VIVANT dans l'ECS, donc le gate ne s'y arme jamais. Corrige par
`allow_dead_caster`, pose **uniquement** par la feuille `UseActiveAbility` (mirror de l'unique poseur
natif) ; toutes les autres voies gardent le gate.

**Port** : `triggers/loki/fuelled_by_fury.py` (`FuelledByFuryReviveAbility` +
`FuelledByFuryCanReviveActivateOnAbilityInit` / `...OnTurnStart` / `...DeactivateOnRevive`),
vecteur `dispatch/move_death.py::pending_death_added_triggers` appele en tete de
`damage.py::_fire_death_if_killed`, registres `ABILITY_TRIGGERS["FuelledByFury"]` (2 abilities) et
`EFFECT_TRIGGERS[1324]` (3 triggers d'etat).

**Validation** — `probe_88_fuelled_by_fury_revive.py`, DEUX regimes LIVE a MEME geometrie et MEME coup
fatal (`hp_player = 12721`, coup mesure `14967` ⇒ letal et NON-overkill), seule la PV des ennemis change :

| regime | riposte | live | port |
|---|---|---|---|
| ennemis a 5251 PV | tue `astraBullgryn` | Titus **VIVANT**, `hp = 7477`, tuile INCHANGEE `(2,2)` | idem, `hp = 7477` |
| ennemis a 31506 PV | ne tue personne | Titus **MORT**, `hp = 0` | idem |

`7477 == round(FuelledByFury.hp[L50] = 4154 x 180 %)` = `ability_var('FuelledByFury','hp', …)`, au PV pres.
Gardes : `tests/engine/runner/test_fuelled_by_fury_revive_live.py` (5 tests — face positive, face
« pas de kill », face « marqueur desarme », face « TriggeringAbility absent », re-armement au tick de
tour). Zero-reg cible : finaljustice / martial_superiority / fuelled_by_fury / revive_cancels_death (13),
famille revive (34), death_nova / ambush / act_of_faith / overwatch (12) — **59 PASS** ; `probe_120` OK.

**Residu NOMME** : `FuelledByFury_BlockOverkillEffect` (`EffectType.FuelledByFury_BlockOverkill` = 1354,
present LIVE sur Titus au meme titre que 1324) — le volet « cannot be Overkilled » de l'i2. Artefacts :
`IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$ApplyInternal` / `$$RevertInternal`
/ `$$CreateHandleTriggerAbilitiesInternal`. MECANIQUE DISTINCTE (pose du flag `UnitFlag.PreventOverkill`
lu par `IsOverkill`), pas un morceau du revive. Second residu : le NOM du slot d'interface 8 lu par
`EvaluateTriggerOperation$$CanGetAbilityTrigger` (le « fire-on-death » natif) n'est pas resolu — sa
valeur VRAIE pour cette ability est etablie par la mesure live, pas par une lecture.

### 8.2 `TimeFlux` / `GhostRevive` (`thousTerminator`, hero **dans le pool**) — **PORTE ET VALIDE LIVE (#213, 2026-07-29)**

i2 : « When Toth **moves**, he leaves a **time ghost** behind on the hex he moved from. The time ghost
vanishes if the hex becomes occupied by another unit or if … » (+ le volet regeneration, deja distinct
et deja porte — `triggers/loki/time_flux.py::TimeFluxRegenAbility`).

**Le blocage (a) de la fiche d'origine est LEVE** : l'emetteur d'`On(PreUnitMove = 31)` est
`IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers` (+ un second site, dans
`IdunBattle.Operations.MoveUnitOperation$$Execute` lui-meme) — les deux passent `eventType = 0x1f` en
`r9d` au thunk `FUN_180026490`, avec `AbilityEntities.ctor(mover, mover, mover, …)`. Le port a deja
`MoveUnitOperation` ; il ne manque que le vecteur (aucun autre consommateur porte ne l'attend, donc
l'ajouter SEUL serait un vecteur registered-but-dead — a poser AVEC le ghost).

Arbres LUS (spec complete, prete a recopier) :
- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GhostReviveAbility$$CreateTrigger` =
  `<trigger de base factory@0xa0> & On(0x1f = PreUnitMove, 1) & OwnerIsCaster`.
- `...GhostReviveAbility$$CreateBehaviour` =
  `tile = CurrentTurnStartTile(sel@0x160)` ;
  `cond = AmountIsEqual(CurrentTurnStartTile(sel@0x160), Direct(0))
        | HasBeenRevivedByAbility(sel@0x160, AbilityOrEffect(this.Id@0x60))
        | NOT(OwnerIsCaster)
        | TileHasTriggeredAbility(tile, 0x1d)` ;
  `If(cond, Nothing(), AddEffect(this.Id@0x60, AbilityStateReference, sel@0x160, tile, default))`.
- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxReviveAbility$$.ctor` = la meme classe
  parametree par `EffectType.TimeFlux_Revive = 0x4a2 = 1186` (le ctor de base est nomme
  `EnvDefenderHealthBuffAbility..ctor` par ICF — **ne pas se fier au nom**).
- `IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTrigger` =
  `OnPreDeath(ignoreOverkill = 1) & AreEqual(EffectSource(self@0x150), target@0x178)`
  ⇒ **even if Overkilled**, et seul le POSEUR du ghost peut le declencher.
- `...GhostEffect$$CreateTargetTriggerBehaviour` =
  `src   = EffectSource(Get(effect))` ;
  `cond  = NOT(IsAlive(src)) & NOT(HasFlag(src, 6)) & NOT(HasBeenRevivedByAbility(src, AbilityOrEffect(effectType)))` ;
  `amount = <si la config porte une variable 'hp' et que le champ Nullable @0x14..0x2c vaut 0x485>
            ? Direct(GetVariableForLevel(config@0x60, 0x1d = 'hp', abilityState))
            : StatAmount(src, Health = 5, max = 3)` ;
  `If(cond, Revive(src, src, amount, healType = 2, Nullable(AbilityOrEffect(effectType)),
                   **tiles = Owner@0x148** (= la TUILE porteuse du ghost), 0, 0)
           + BaseEffect.GetRemoveEffectBehaviour())`.
  ⇒ le 7e argument de `DSLFactory.Revive` (le selecteur de TUILES) est ici **non nul** : c'est LA
  difference avec tous les revives deja portes, et donc le seul endroit du sous-systeme ou la position
  change (`ReviveUnitOperation$$SetRevivePosition`).
- `...GhostEffect$$CreateHandleTriggerAbilitiesInternal` = `ArraySet` de **CINQ** retraits
  (`GetRemoveEffectBehaviour` a chaque fois) — c'est la « condition de disparition » de l'i2 :
  1. `On(0x1f = PreUnitMove, 1) & AreEqual(caster@0x160, EffectSource)` — Toth rebouge : l'ancien ghost part ;
  2. `On(0x33 = UnitAdded, 1) & NOT AreEqual(caster, EffectSource) & Contains(sel@0x190, Owner@0x148)
     & NOT HasTrait(caster, 0x1b)` — une AUTRE unite APPARAIT sur la tuile du ghost ;
  3. `On(0x24 = UnitPositionChanged_1, 1) & NOT AreEqual(caster, EffectSource) & Contains(sel@0x190, Owner@0x148)`
     — une autre unite ARRIVE sur la tuile du ghost ;
  4. `OnDeath(1) & AreEqual(EffectSource, target@0x178) & NOT IsEffectActive(self@0x150)` ;
  5. `On(0x25 = UnitRemoved, 1) & AreEqual(EffectSource, target@0x178)`.

**Trois PRECISIONS de RE ajoutees par le portage** (#213), toutes lues au decompile :

1. **La tuile n'est PAS « the hex he moved from » de l'i2 — c'est la tuile de DEBUT DE TOUR.**
   `IdunBattle.Entities.Selectors.CurrentTurnStartTileSelector$$Select` resout son selecteur, prend
   le `UnitComponent` de l'entite et lit **`+0x18c`** (un id de tuile, `0` -> liste VIDE). Ce champ a
   un ecrivain UNIQUE : `IdunBattle.Operations.StartTurnOperation$$Execute`, dans sa boucle sur
   `PlayerComponent.CurrentlyOwnedUnitIds` du joueur ENTRANT, juste apres le bump de
   `turnsStarted@+0x58` (`mainTile = GetMainTile(unit) ; comp[0x18c] = mainTile?.Id : 0`). Les deux
   formulations coincident tant que l'unite ne bouge qu'une fois par tour.
2. **`HasBeenRevivedByAbility` a un substrat, et c'est un registre de BATAILLE.**
   `Idun.Source.IdunBattle.Logic.Entities.Triggers.HasBeenRevivedAbilityTrigger$$ShouldTrigger` lit
   `ActorStatisticsComponent + 0xe0 .Contains(source)`. Le set est alimente par
   `IdunBattle.Operations.ReviveUnitOperation$$Execute` (`if (sourceId.HasValue) set.Add(...)`, entre
   `SetHealth` et les flags) et **n'est remis a zero NULLE PART** (ni turn-start, ni phase) : le gate
   `NOT HasBeenRevivedByAbility(self, 1186)`, present DEUX fois (pose du ghost + behaviour de
   resurrection), est donc un « une seule fois par bataille ».
3. **`GhostEffect` a DEUX instanciations**, et c'est ce qui explique le fork d'`amount` :
   `TimeFluxReviveAbility$$.ctor` = `GhostReviveAbility..ctor(this, 0x4a2 = 1186)` et
   `EchoesFromTheWarpAbility$$.ctor` = `...(this, 0x504 = 1284)`. Le behaviour compare le champ
   `source` de l'effet a `0x485 = 1157 TriggeredAbilityType.TimeFlux` **a la construction de
   l'arbre** : egal -> `Direct(GetVariableForLevel(config, 'hp'))` (branche TimeFlux, portee) ;
   different -> `StatAmount(src, Health, max)` (branche EchoesFromTheWarp, **non portee** — porteur
   non etabli, hors perimetre #213).

**Port** (fichiers) :

| Fichier | Contenu |
|---|---|
| `triggers/loki/ghost_revive.py` | `GhostReviveAbility` (pose) + `GhostEffectRevive` (resurrection, `TileEffectTrigger`) + les CINQ classes de retrait |
| `operations/revive.py` | `_set_revive_position` (mirror `SetRevivePosition`), `revive_position` dans la `ReviveData`, enregistrement `revived_by_abilities` |
| `triggers/revive_effect.py` | la feuille `Revive` accepte le 7e argument `targetsTile` (nul chez tous les autres consommateurs) |
| `triggers/dispatch/move_death.py` | vecteurs `pre_move_triggers` (`On 0x1f`), `unit_position_changed_1/2_triggers` (`On 0x24`/`0x1d`), `unit_removed_triggers` (`On 0x25`) |
| `operations/movement.py` | `On(PreUnitMove)` emis **en tete** d'`execute` (place native lue : avant `CalculatePaths`/`MoveUnit`) ; `after_move_triggers` dispatche desormais `On(0x24)` en GENERIQUE |
| `operations/spawn.py` | `on_unit_added` dispatche `On(0x33)` en GENERIQUE (retrait n°2) |
| `operations/turnflow.py` + `components.py` | `UnitComponent.current_turn_start_tile` (@+0x18c) et `revived_by_abilities` (@ActorStats+0xe0) |

**Validation** — `probe_213_ghost_revive.py`, **DEUX couples (board, seed)**, montage ou la tuile de
MORT et la tuile de REVIVE DIFFERENT (sans quoi un revive in-place serait indetectable) :

| couple | A (debut de tour) | B (mort) | ghost pose | pos apres mort | hp |
|---|---|---|---|---|---|
| `MC1_67` / 31337 | (1,2) | (3,2) | (1,2) | **(1,2)** live ET port | **3290** live ET port |
| `C4_09` / 777 | (3,3) | (4,3) | (3,3) | **(3,3)** live ET port | **3290** live ET port |

`3290 == round(TimeFlux.hp[L50] = 1828 x 180 %)` = `ability_var('TimeFlux','hp', …)`.
⚠ **Piege de mesure rencontre et neutralise** : avec UN SEUL adversaire, le runner bascule de tour
juste apres le revive et la REGEN `TimeFlux` s'ajoute -> le live rendait **4487 = 3290 + 1197**
(`hpToHeal[L50] x 180 %`). Ce n'etait PAS une divergence de montant mais un confond de PORTEE DE
MESURE ; une 2e unite adverse qui garde son action le supprime. Decomposer l'etage a suffi a le voir
(la somme tombait EXACTEMENT juste) — ne jamais fitter le scalaire.

Gardes : `tests/engine/runner/test_ghost_revive_live.py` (5 tests — face positive A!=B, « pas de move
-> pas de ghost », once-per-battle via `revived_by_abilities`, dissipation par arrivee d'une autre
unite, deplacement du ghost au 2e move). Zero-reg cible : famille revive (42), mouvement/decoys/push
(21 + 1 xfail pre-existant), tuiles/turnflow/spawn (27) = **90 PASS** ; `probe_120` OK.

**RESIDUS NOMMES** :
- **`On(UnitRemoved = 0x25)` n'a aucun emetteur cote port** (`RemoveUnitOperation` non porte : dans le
  runner isole les morts restent en place) -> le retrait n°5 est enregistre et testable via
  `unit_removed_triggers`, mais aucun site de production ne l'atteint.
- **`TileHasTriggeredAbility(tile, 29 = BrokenIce)`** : la table `TriggeredAbilityType -> tileDefId`
  vit dans les Unity assets de tuile (hors gameconfig) -> le gate est structurellement present mais
  toujours FAUX. Il ne peut refuser un ghost a tort que sur un board a glace brisee (40 boards en
  portent, cf. l'inventaire terrain de `runner.md`).
- **`UnitComponent + 0x18c` n'est pas capte** par `combatSnapshot` -> un `load_state` frais part a
  `None` et le 1er move ne pose PAS de ghost tant qu'un `StartTurnOperation` n'a pas tourne. Point
  d'ancrage a hooker si on veut le capter : `UnitComponent+0x18c` cote `combatSnapshot`.
- **Double move dans le MEME tour sur la MEME tuile de debut de tour** : `AddEffectOperation` no-ope
  (effet deja present) puis le retrait n°1 le supprime -> plus de ghost. Cas de bord (une unite ne
  bouge qu'une fois par tour, flag `UnitFlag.Moved`).
- **Branche `StatAmount(src, Health, max)` du fork d'amount** (`EchoesFromTheWarp`, effet 1284) : non
  portee, porteur non etabli.

NB : `RitesOfRestoration` (deja porte) = **Resurrect** (tile-choice/ambush), sous-systeme DISTINCT
(`ResurrectUnitOperation`) — NE PAS confondre avec Revive-en-place.

### 8.3 Technique reutilisable : lire une vtable **sans** classe initialisee

Quand `resolveVtableSlot` (LIVE) rend des slots nuls parce que la classe n'est jamais construite
(carrier hors pool), la table `methodPointers` d'IL2CPP reste lisible **dans le PE**. Recette :
1. prendre 2 methodes de la classe dont on connait la VA (via un symbole ghidra : `.ctor`, un
   `Create*` nomme) et chercher leurs 8 octets LE (`struct.pack('<Q', va)`) dans `GameAssembly.dll` ;
2. les offsets fichier trouves sont ADJACENTS (0x8) → on tient le bloc de la classe ;
3. dumper les qwords voisins : ce sont les autres methodes **dans l'ordre de declaration**, y compris
   celles que l'ICF a fondues (donc sans symbole propre) ;
4. valider l'alignement du bloc sur une classe dont on connait DEJA les valeurs (ici la base + les deux
   Narthecium lus LIVE), et desambiguer deux corps triviaux voisins par leur **taille de retour**
   (`undefined1` = bool vs `undefined8` = int, visible au decompile du corps folde) ;
5. lire le corps avec `read_bytes` (`b8 64 00 00 00 c3` = `mov eax,100 ; ret`).

C'est ce qui a ferme les residus B1 (`get_ReviveOnOverkill` / `get_HealType` de ReanimationBeam et
RitesOfMorkai) et B2 (`GetReviveChance` litteral = 100) sans aucune analogie.
