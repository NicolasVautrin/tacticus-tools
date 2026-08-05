# case-haze-ord — le port DRAINAIT la mort immédiatement, le natif l'ENQUEUE

**Question binaire** — au régime OVERKILL, le port émet-il le même nombre de `genrand_int32` que
le natif ? Mesure de référence : **natif 14, port 12** (`HazeOfCorruption` `k = 2`, seed 777,
board `MC1_67`, PV cible **1200**).

**Verdict** : **oui, porté et validé — 14 == 14, dégât par unité 3/3, et 9/9 bit-exacts sur la
matrice de généralisation.** L'écart recouvrait **deux** défauts indépendants, l'un qui retirait 3
tirages et l'autre qui en ajoutait 1. Les deux sont **structurels du pipeline de dégât**, pas de
`HazeOfCorruption`.

---

## 1. Les deux artefacts natifs que le port avait fondus en un

```
IdunBattle.Operations.RecordKillOperation$$Execute            <- ENQUEUE
    gate UnitFlagsComponent.Has(dying, 6)  -> return          (« déjà retiré »)
    compteurs de kills du PlayerComponent (+0x90 / +0x94)
    UnitFlagsComponent.Add(dying, 0xf)                        (PendingDeath)
    IdunBattle.Core.MatchState$$AddDeath(killer, killed,
        killTrigger, attackTrigger, AttackRangeType)          <- la FILE
    publie On(PendingDeathAdded = 3)

IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths       <- DRAIN
    RunPhase(PhaseType.ProcessDeaths /*0xc*/) -> lambda <VerifyDeaths>b__0
                  -> Core.Services.OperationProcessor$$KillUnit
                  -> IdunBattle.Operations.KillUnitOperation$$Execute
                         On(1) -> garde `pendingRevive.HasValue`
                                  |- false -> On(2) -> On(0) -> On(55) -> On(54)
                                  `- true  -> Core.Services.OperationProcessor$$ReviveUnit
                                              -> IdunBattle.Operations.ReviveUnitOperation$$Execute
    RunPhase(PhaseType.ProcessRemovals /*0xd*/) -> lambda <VerifyRemovedUnits>b__0   # les RETRAITS
```

⚠ **CE SCHEMA DISAIT « `RunPhase(PhaseType.ProcessRemovals /*0xd*/)` -> `ReviveUnitOperation` ». C'EST FAUX, ET CORRIGE <!-- [phase-attribution:refute] -->
(#477-r24).** Le revive n'a AUCUNE phase : il est appelé dans la branche `else` de la garde, DANS
`IdunBattle.Operations.KillUnitOperation$$Execute`. Détail :
`docs/rl/case-477r24-le-revive-na-pas-de-phase.md`.

Le port appelait `AttackDamageOperation._fire_death_if_killed` à **chaque** `AttackDamage`, et cette
fonction faisait TOUT : enregistrement **et** application. Or
`IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour`
empile ses **N** feuilles sous **un seul**
`IdunBattle.Entities.Behaviours.AttackBehaviour` — `Attack(bonded, Owner@0x148, RemoveEffect +
N × AttackDamage)`. Aucun `VerifyDeaths` ne tourne entre deux feuilles : les N reports partent
**tous** avant que la mort de leur cible ne soit traitée.

### `killTrigger` — le 3ᵉ argument d'`AddDeath`, load-bearing

`RecordKillOperation$$Execute` recopie dans `AddDeath` l'`AbilityOrEffect` déclencheur lu **à cet
instant** dans le `KillUnitContext`. C'est lui que `KillUnitOperation` rejoue ensuite dans
l'`AbilityEntities+0x138` des événements de mort — donc lui que comparent
`IdunBattleLogic.Entities.DSLFactory$$TriggeringAbilityIs` et `$$TriggeringEffectIs`.

⇒ **différer le drain SANS transporter le déclencheur aurait cassé case-haze-bonded** : la mort du
relais 1, drainée hors du behaviour du report, aurait perdu son `0x435` et le
`NOT TriggeringEffectIs(0x435)` de `HazeCorruption_BonusHitAbility` serait redevenu permissif —
exactement le bug que `8a9e490`/`475064a` avaient fermé. Le port capture donc
`state.triggering_ability` **dans l'entrée de file** et le repose le temps de chaque
`KillUnitOperation`.

## 2. Le deuxième défaut — le site (A) d'`ApplyDamageOperation$$Execute`, RELU VERBATIM

```c
cVar15 = IdunBattle_Entities_UnitExtensions__HasFlag(param_4, 8, 0);   // 8 = Overkilled
if (cVar15 != '\0') {
  IdunBattle_Operations_ApplyDamageOperation__RecordHitStatistics(...);
  IdunBattle_Operations_ApplyDamageOperation__AddLeftoverHit(param_2, param_4, &dmg, &hit, 1, 0);
  return param_1;                                     // <- TOUT LE RESTE EST SAUTÉ
}
```

Le `return` **précède** l'émission d'`On(0x3a)`, la mutation de PV
(`IdunBattle.Entities.Components.FillUpStatComponent$$Reduce`), `On(DamageTaken = 0xf)`, les
écritures `lastHitDamageTaken` (`stats+0x68` / `+0x6c`) et `On(DamageDealt = 0x10)`. Un coup porté
sur une cible **déjà overkillée** n'empile que sa `LeftOverDamage` (base nominale) et **n'émet
rien**.

Le port émettait `On(0x10)` → sur un profil Toxic, le `Maybe(25)` d'`OnToxicDamageAbility` →
**un `genrand_int32` de trop**. C'est exactement le coup bonus de `HazeCorruption_BonusHitAbility`,
qui tombe sur une cible overkillée dès le 1er coup d'arme au régime PV 1200.

**Le flag est RETIRÉ par un revive** (`IdunBattle.Operations.ReviveUnitOperation$$Execute` :
`Remove(0xf)`, `Remove(**8**)`, `Add(0x14)` — décompilé relu, et déjà porté dans `revive.py`) :
une unité ressuscitée après overkill redevient frappable. Sans ce retrait, la garde ci-dessus
l'aurait rendue **invulnérable**.

## 3. La ventilation qui attribue chaque tirage

`probe_hazeord_death_queue.py` trace la PILE d'appel `engine/` de chaque `genrand_int32` du replay
offline — c'est ce qui NOMME les étages au lieu de les deviner (seed 777, PV 1200, `MC1_67`) :

| étage (call-site porté) | natif | port AVANT | port APRÈS |
|---|---|---|---|
| `splash.py::_pick_randomly_n` ← target-finder | 2 | 2 | **2** |
| `normal.py::execute` — les 3 coups d'arme | 3 | 3 | **3** |
| `ability.py::execute_ability_attack` — le coup bonus | 1 | 1 | **1** |
| `dsl/triggers.py::should_trigger` — `Maybe(25)` `OnToxicDamage` | **0** | **1** | **0** |
| `normal_like.py::execute_normal_like` — les reports | 4 + 4 | 4 + **1** | **4 + 4** |
| **total** | **14** | **12** | **14** |

Les deux défauts ne se compensaient pas : −3 d'un côté, +1 de l'autre.

**Témoin direct de la cause**, rendu par le même probe : la liste de `LeftOverDamage` lue quand le
bond du 2ᵉ relais est consommé.

```
AVANT   BOND consomme : relais=81 mort=77 leftOver_lus=[1247, 2609, 2609, 1397]
        BOND consomme : relais=79 mort=81 leftOver_lus=[671]                      <- INCOMPLETE
APRES   BOND consomme : relais=79 mort=81 leftOver_lus=[671, 3914, 3914, 2096]
```

Et le flux natif dit la même chose dans l'autre sens : `Unit_IsDying` du relais 1 apparaît **après**
ses deux événements de dégât, pas entre eux.

## 4. Le rayon de souffle, CHIFFRÉ

`probe_hazeord_blast_radius.py` le dérive du code (registres + scan statique), pour qu'il soit
re-dérivable et non recopié :

* **7** call-sites statiques d'`_apply_damage_pipeline` sous `engine/` (6 réels + 1 mention en
  docstring) — `normal.py`, `ability.py`, `normal_like.py` ×2, `additional_hits.py`, `displace.py` ;
* **1** call-site de `_fire_death_if_killed` (le chokepoint), **1** de `_verify_deaths`, **1** de
  `_add_death` ;
* **83** classes de trigger enregistrées, dont **21** consomment un vecteur de mort
  (`On(0)` ×5, `On(1)` ×11, `On(2)` ×2, `On(3)` ×1, `On(55)` ×2) ;
* dont **8** dont le behaviour peut TUER — le SEUL sous-ensemble réellement touché, puisqu'une mort
  ne s'imbrique que dans une autre : `HazeOfCorruptionDamageTransferTrigger`,
  `HazeCorruptionBonusHitAbility`, `ExplodesAbility`, `PutridExplosionAbility` (vecteur de dégât
  **dans le corps de classe**), plus `ActOfFaithAccumulateAbility`, `FinalJusticeAbility`,
  `TheBetrayerAddEffectAbility`, `AmbushSummonAbility` (vecteur dans une fonction de module — borne
  LARGE).

**Hors de cette fenêtre, le changement est un no-op strict** : au premier appel de la pile, enqueue
et drain restent consécutifs, donc tout appelant top-level voit exactement la séquence d'avant.

## 5. Le correctif

* `engine/runner/state.py` — `State.pending_deaths` (mirror de la file de `MatchState`, entrées
  `(dying, killer, overkill, killTrigger)`) et `State.draining_deaths` (re-entrance de
  `VerifyDeaths`).
* `engine/runner/operations/damage.py` :
  * `_fire_death_if_killed` = `RecordKillOperation$$Execute` (flag `Overkilled`,
    `RecordDeathReason`, `On(3)`, `_add_death`) puis `_verify_deaths` ;
  * `_add_death` = `MatchState$$AddDeath` (+ déduplication : entre l'enqueue et le drain la cible
    reste joignable) ;
  * `_verify_deaths` = `VerifyDeaths`, boucle **non ré-entrante**, repose le `killTrigger` ;
  * `_kill_unit_operation` = `KillUnitOperation$$Execute` (corps inchangé : `On(1)` → garde revive
    → `On(2)` → `On(0)` → `RemoveEffects` → `On(55)`) ;
  * `_apply_damage_pipeline` : `return None` au site (A) si la cible porte déjà `Overkilled`, après
    `record_left_over_damages` et avant toute mutation ou émission.

`uc.alive = False` **reste à l'enqueue** (position du port d'avant) : le natif pose le flag 6 au
DRAIN, mais toute la machinerie `fire_on_death` du port (gate `CanGet*Trigger` de
`dispatch/core.py`) est bâtie sur « l'unité est déjà `alive=False` quand `On(1)` part ». La
divergence est **nommée** et sans consommateur connu : aucun sélecteur n'est évalué entre l'enqueue
et le drain sur ce chemin, et `execute_normal_like` n'a aucun gate `alive` sur sa cible — c'est ce
qui permet aux reports 2..4 d'atteindre le relais tombé.

## 6. Mesures et gardes

| montage | avant | après |
|---|---|---|
| seed 777, PV 1200, `k = 2` — RNG natif vs port | 14 / **12** | 14 / **14** |
| seed 777, PV 1200 — dégât par unité (live vs port) | **1/3** | **3/3** |
| seeds 5 et 21, PV 1200, `k = 2` | — | **RNG + dégât bit-exacts** |

**Généralisation craftée** — même géométrie pilotée (`MC1_67`, caster jamais déplacé,
`--crit 0,0 --block-target 0,0`), trois PV cible pour trois **profondeurs d'overkill**, donc trois
rangs de mort du 1ᵉʳ relais dans SA série de reports : **9/9 bit-exacts** (RNG *et* dégât par unité).

| PV | seed 777 | seed 88 | seed 42 |
|---|---|---|---|
| 800 | 14 (4 + 4) | 14 (4 + 4) | 14 (4 + 4) |
| 1200 | 14 (4 + 4) | **13 (4 + 3)** | 14 (4 + 4) |
| 2000 | **13 (4 + 3)** | **13 (4 + 3)** | **13 (4 + 3)** |

Les quatre montages à **13** sont les plus discriminants : le relais y meurt **en milieu de série**,
donc le 2ᵉ bond doit lire **3** leftovers — ni 4, ni 1. Un port qui drainerait encore inline en
lirait **1** dans les neuf cas.

Non-régression rejouée :

* `test_haze_bonded_chain_live.py` + `test_haze_of_corruption_transfer_live.py` +
  `test_haze_rng_flow_live.py` + `test_haze_of_corruption_rng_live.py` → **45 passed**
  (les gardes `k = 1` et `k = 2` du régime PV 5000 : aucun chiffre n'a bougé) ;
* `test_death_nova_live.py` + `test_revive_cancels_death_events_live.py` +
  `test_fuelled_by_fury_revive_live.py` + `test_fuelled_by_fury_live.py` +
  `test_overkill_gate_live.py` → **26 passed** ;
* `test_damage_roll_live.py` + `test_runner_attack_live.py` + `test_on_toxic_damage_live.py` +
  `test_dakka_dakka_dakka_live.py` + `test_ambush_migration_live.py` + `test_doom_siren_live.py` +
  `test_cosmic_horror_live.py` + `test_barbed_ovipositor_live.py` → **41 passed** ;
* `test_tainted_narthecium_revive_live.py` + `test_narthecium_revive_live.py` +
  `test_rites_of_morkai_revive_live.py` + `test_ghost_revive_live.py` +
  `test_revive_retrofit_offline_live.py` + `test_overkill_decision_live.py` +
  `test_prevent_overkill_decision_live.py` → **49 passed** — c'est le lot qui couvre le DANGER réel
  du gate site (A) : `TaintedNarthecium` = `ReviveOnOverkill`, donc une unité overkillée PUIS
  ressuscitée doit redevenir frappable ;
* **161 tests** au total, tous verts ;
* `engine_validate.py --runner <id> --steps 40` (seed 31337, `MC1_67`) — marche complète de la
  trajectoire IA native : **27/27 abilities**, **29/30** positionnements exacts (96 %, `<= 1 hex`
  100 %), c.-à-d. le baseline. C'est le contrôle « bataille entière, beaucoup de morts » ;
* garde propre : `tests/engine/runner/test_death_queue_ordering_live.py` — **7 offline** (file,
  verrou de ré-entrance, `killTrigger`, déduplication, **ordonnancement imbriqué**, site (A),
  revive-efface-l'overkill) + **15 live** (3 seeds × PV 1200 + la matrice 3 × 3).

Le test offline `test_une_mort_causee_pendant_une_mort_est_traitee_APRES_elle` est le garde-fou
générique : il n'a besoin d'aucun kit, et il tomberait si quelqu'un re-fusionnait enqueue et drain.

## 7. Ce qui n'est PAS couvert

* **La death-nova qui TUE en live.** `ExplodesAbility` / `PutridExplosionAbility` sont les deux
  autres sites d'imbrication à vecteur de dégât en classe ; `test_death_nova_live.py` passe, mais
  aucun de ses montages ne fait TUER la nova (donc l'imbrication n'y est pas exercée). C'est le
  premier scénario à crafter si l'on veut fermer la généralisation par le live plutôt que par
  l'offline.
* **`FinalJusticeAbility` / `TheBetrayerAddEffectAbility` / `AmbushSummonAbility` /
  `ActOfFaithAccumulateAbility`** : borne LARGE du rayon de souffle (le vecteur de dégât est dans
  une fonction de module). `test_fuelled_by_fury_revive_live.py` exerce bien la riposte létale de
  FinalJustice (Titus se revive) et reste vert ; les trois autres ne sont pas confrontés sur un
  montage où leur behaviour TUE.
* **`uc.alive` à l'enqueue plutôt qu'au drain** (§5) — divergence nommée, non confrontée.
* **Le flag `Overkilled` sur les reports 2..4** : le natif le pose (`Attack_WasOverkill: 1` sur le
  2ᵉ report), le port ne le pose pas (son gate est `hp_before > 0`, faux sur un relais déjà tombé).
  Sans effet mesurable ici — `record_left_over_damages` bascule déjà sur `hp <= 0`, et les reports
  3..4 portent `is_first_hit=False` donc n'émettent aucun `Maybe`. Résidu **nommé**.
* **`RecordHitStatistics` du site (A)** : appelé par le natif avant le `return`, sans pendant porté
  (le port n'a pas de couche hit-statistics).
* **Les registrations hors `ApplyDamageOperation`** (`_record_attacked`,
  `_register_received_damage`, `_register_damaged_this_phase`) sont désormais sautées au site (A)
  avec le reste du corps. Leur call-site natif exact est un résidu **pré-existant** (case-202 §6) :
  aucune xref ne l'isole. Le choix retenu est cohérent avec leur propre gate (« du dégât a
  RÉELLEMENT été infligé » — au site (A) l'appliqué est 0), mais il n'est pas prouvé.
* **Le régime armure non nulle** : `--hp-target` force l'armure à 0 (hérité de case-209).
