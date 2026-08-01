# #437 — `On(9 = Attack)` n'est pas émis par une opération de dégât : son foyer est le nœud DSL `Attack(...)`

## 1. Le fait

Le port émettait `On(9)` au niveau **MESSAGE** (`DamageHandler.visit_AttackUnitMessage` →
`after_hit_normal_attack`). Une attaque née d'un **TRIGGER** ne traverse pas ce chemin : le tir
d'overwatch appelle directement `AttackDamageOperation.execute`. Conséquence mesurée sur
`1147 TerminatorArmour_ReduceDmg` (44 porteurs) : un tir d'overwatch **ne consommait pas** l'armure
côté port alors que le natif la consomme — elle restait armée pour l'attaque suivante, réduite à tort.

**Écart livré**, `MC1_67`/seed 4321, porteur `spaceStormcaller` sous **double overwatch**
(`eldarRanger` + `admecDestroyer`, deux tirs sur le même move) : natif **15 280**, port d'avant
**4 828** — **10 452 points de dégât escamotés sur un seul déplacement**.

## 2. La RE (décompilé = vérité)

`On(9)` ne sort **d'aucune** opération de dégât. Chaîne lue :

    IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute       # le nœud DSL `Attack(...)`
        caster  = Select(entities+0x50)
        targets = Select(entities+0x58)                           # OrderBy si > 1
        options = AttackBehaviour$$GetAttackOptions(entities)
        for tgt in targets:
            if prev is null or prev != tgt: processor.StartAttack   (slot 0x3a)
            <inner behaviour>                                      # AttackDamage & ...
            if next is null or next != tgt: processor.FinishAttack  (slot 0x3b)
    Core.Services.OperationProcessor$$FinishAttack
        -> IdunBattle.Operations.FinishAttackOperation$$Execute
               FUN_1800280e0(0x50, .., 9, entities)                # On(9)  : INCONDITIONNEL
               if (currentAttack@+0x2c) FUN_1800280e0(.., 10, ..)  # On(10) : GATE

Les slots sont **lus**, pas supposés : `StartAttackBehaviour$$Execute` n'appelle que `0x3a`,
`FinishAttackBehaviour$$Execute` que `0x3b`, et `AttackBehaviour$$Execute` les deux, autour de son
behaviour interne. `FinishAttackOperation$$Execute` n'a **qu'un** appelant
(`OperationProcessor$$FinishAttack`), lui-même appelé par ces deux nœuds.

⇒ **`On(9)` est émis PAR CIBLE**, après le dégât de cette cible, et son porteur est **l'arbre de
l'ability**, pas l'opération.

**L'attaque NORMALE traverse ce nœud** — c'est ce qui rend le constat universel :
`ALoki_NormalAttackAbility$$ExecuteBehaviour` → `$$ExecuteNormalAttack` →
`$$GetAttackDamageBehaviour`, dont la **dernière** construction est
`IdunBattleLogic.Entities.DSLBehaviors$$Attack(selectors, target, <AttackDamage & ...>, options)`.

**Donc le tir d'overwatch aussi** : `Overwatch_AutoAttackEffect$$GetAttackBehaviour =
UseActiveAbility(NormalAttack)` entre dans le même arbre.

### 2.1 Deux inversions d'ordre, corrigées au passage

* `On(9)` **avant** `On(10)` — les deux sortent du même `FinishAttackOperation$$Execute`, 9 puis 10.
  Le port avait `On(10)` (déjà à la sortie de l'opération) **avant** `On(9)` (au niveau message).
* `On(9)` **avant** `On(0x26 = NormalAttack)` — le natif émet 0x26 depuis
  `ALoki_NormalAttackAbility$$ExecuteTriggerAbilities` (= `DSLBehaviors$$EvaluateAbilities(0x26)`),
  appelé **après** `ExecuteNormalAttack`. Le port avait l'ordre inverse.

## 3. Le rayon de souffle, chiffré AVANT le correctif

`probe_437_on9_blast_radius.py` (re-dérivable) — **12** classes-triggers écoutent `On(9)` :

| voie | clé | classe | porteurs (lineup / npc / summons) |
|---|---|---|---|
| trait | `WeaverOfFate` | `WeaverOfFateAbility` | 6 / 26 / 8 |
| trait | `LetTheGalaxyBurn` | `LetTheGalaxyBurnResetAbility` | 5 / 26 / 2 |
| trait | `ActOfFaith` | `ActOfFaithResetAbility` | 5 / 18 / 1 |
| passive | `RealityUnbound` | `RealityUnboundAbility` | 1 / 4 |
| passive | `HypersensoryAbilities` | `HypersensoryMoveAndSpawnDecoyAbility` | 1 / 4 |
| passive | `CursedPlagueBell` | `CursedPlagueBellAttackAbility` | 1 / 3 |
| passive | `LordOfTempests` | `LordOfTempestsAddIceAbility` (branche 2) | 1 / 1 |
| active | `Hailstrike` | `HailstrikeAttackAbility` | 1 / 1 |
| effect | 1147 | `TerminatorArmourDeactivateOnAttack` | 44 (cf. #432) |
| effect | 1197 | `MasterOfTheTutelariesSummonAbility` | posé en bataille |
| effect | 1227 | `HarlequinsPanoplyIgnoreHitsRemove` | posé en bataille |
| effect | 1550 | `ChronometronExtraDamageRemove` | posé en bataille |

**Tous confrontables** (les 8 premiers ont un porteur `lineup`). Le correctif les touche **tous à la
fois** — d'où le re-jeu ciblé de leurs gardes (§5).

**Le risque de DOUBLE ÉMISSION est mesuré, pas raisonné** : les **4** appelants de
`after_hit_normal_attack` (`damage.py`, `summon_ai.py`, `abilities/loki/summon.py`,
`abilities/loki/mv71.py`) sont **tous** précédés d'un `AttackDamageOperation.execute`. Retirer
l'émission de l'un et la poser dans l'autre est donc un **déplacement**, jamais un doublon. Les
trois early-returns d'`execute` (stats manquantes, caster mort post-`On(0x2a)`, re-entrance sur
cible remplacée) sont **avant** le foyer : aucun n'a résolu d'attaque, le natif n'émettrait pas non
plus.

**Résidu d'ordre, mesuré NON OBSERVABLE** : le port émet `On(8 = AttackHit)` après ce vecteur, alors
que le natif l'émet **par coup** dans l'opération (donc avant). **Zéro** trigger porté n'écoute
l'event 8 — l'inversion est inerte. (Divergence préexistante : `On(8)` était déjà après `On(0x42)`
et `On(10)`.)

## 4. Le port

* `finish_attack_triggers` (`triggers/dispatch/attack.py`) — mirror du volet `On(9)` de
  `FinishAttackOperation$$Execute`, appelé à la **sortie** de `AttackDamageOperation.execute`
  (`damage_ops/normal.py`), **juste avant** `attack_damage_attack_triggers` (`On(10)`).
* `after_hit_normal_attack` perd son `ev_at` et les deux paramètres qui n'appartenaient qu'à lui
  (`profiles`, `health_damage`) ; ses 4 appelants suivent.
* **Payload inchangé** : mêmes valeurs, calculées au même étage (`profiles` = arme + coups bonus
  #179 ; `health_damage` = `r["total"]`, part santé seule ; `was_block` = `r["did_block"]`).
  `ability_type` reste `None` sur la voie NORMALE — le poser ferait fire la branche 2 de
  `LordOfTempestsAddIceAbility` (gate `kind == 1013`) sur l'attaque normale de Njal, en plus de sa
  branche 1 `On(0x26)`. **Hors périmètre, non élargi.**
* **Canal de diagnostic** : `execute` rend les résultats du vecteur sous la clé `finish_attack`, que
  les 4 exposeurs d'`after_hit` remettent **en tête** (= l'ordre natif). Sans ça un trigger `On(9)`
  fire **sans être observable** — c'est exactement ce qui a fait rougir
  `test_hailstrike_phase2_live` alors que le comportement était juste.

**Sites qui GAGNENT un `On(9)`, et c'est le but** : le tir d'overwatch
(`effect_triggers.py::OverwatchAutoAttack`), la feuille DSL `UseActiveAbility`
(`abilities/behaviours/combat.py` — FinalJustice…), `control_edict.py`, `draw_fire.py`,
`primarch_first_legion.py`, et l'attaque commandée du drone MV71. Côté natif, chacun est un
`UseActiveAbility(NormalAttack)` : tous traversent `FinishAttack`.

## 5. Validation

* **Confrontation LIVE du cas** (`probe_437_overwatch_consumes_armour.py`, garde
  `tests/engine/test_437_overwatch_consumes_armour_live.py`, 4 tests) :
  * **natif** — flag `EffectComponent.IsActive @+0x5c` du porteur : `True` avant le move,
    **`False`** après le tir d'overwatch (observable **binaire**, `decisionView({includeInactive:true})`) ;
  * **port** — même trajectoire, et **même dégât à l'unité** (1 184 sur le bras à un tir) ;
  * **contre-épreuve** — foyer `finish_attack_triggers` neutralisé (= l'état d'`origin/master` pour
    une attaque déclenchée par un trigger) : le flag **reste `True`**. La mutation est vérifiée avoir
    **mordu** avant qu'on lise le verdict. ⚠ Le patch doit viser le **package** `dispatch`, pas le
    module `dispatch.attack` : `damage_ops.normal.execute` importe depuis le package, et patcher le
    module a rendu un premier bras **VERT** — sur une contre-épreuve, VERT est le résultat suspect.
  * **régime à DEUX TIRS** (le dégât devient l'observable, un flag n'est pas un dégât) : natif
    **15 280** = port **15 280**, port sans foyer **4 828**. Le nombre de tirs est **compté** par le
    désarmement 1009 de chaque overwatcher (`On(10) & OwnerIsActor -> DeactivateEffect`), jamais
    supposé — sur le second couple la géométrie n'en a amené qu'**un**.
* **Généralisation** : second couple `C3_01`/seed 777 (1 tir, `admecDestroyer`) — vert.
* **Rayon de souffle re-joué** — les gardes des 12 écouteurs : `test_432_terminator_armour_cycle_live`,
  `test_hypersensory_moveandspawndecoy_live`, `test_act_of_faith_crit_resets_both_paths`,
  `test_hailstrike_phase2_live`, `test_harlequins_panoply_live`, `test_cursed_plague_bell_attack_live`,
  `test_let_the_galaxy_burn_live`, `test_master_tutelaries_active_gate_live`,
  `test_reality_unbound_time_flux_live`, `test_lord_of_tempests_ice_live`, `test_lot_pose_live`,
  `test_chronometron_decision_live` — **tous verts**. Plus les gardes damage/overwatch :
  `test_damage_roll_live`, `test_runner_attack_live`, `test_overwatch_live`,
  `test_overwatch_single_shot_per_activation(_live)`, `test_overwatch_activation_condition`.
* **Cliquets** — `scripts/ratchets.ps1` : **20/20 verts, mur 205,5 s**.
* **Deux tests suivent le foyer** (adaptation signalée, pas un contournement) :
  `test_act_of_faith_crit_resets_both_paths` et `test_hypersensory_moveandspawndecoy_live`
  appelaient `after_hit_normal_attack` pour observer `On(9)` ; ils appellent désormais
  `finish_attack_triggers`. L'observable est inchangé — seul le point d'appel a suivi le vecteur.

## 6. Ce qui n'est PAS couvert

* **Le régime MULTI-CIBLES du nœud natif** : `AttackBehaviour$$Execute` émet `Start`/`Finish` par
  **groupe de cibles consécutives identiques** (`prev != tgt` / `next != tgt`). Le port n'a qu'une
  cible par `AttackDamageOperation.execute` : le régime « la même cible apparaît deux fois de suite
  dans la liste triée » (qui, côté natif, n'émettrait qu'**un** couple Start/Finish) n'a **aucun
  porteur** dans le port et n'est pas modélisé.
* **`ability_type` sur la voie NORMALE** reste `None` (cf. §4) — le poser exige de trancher la
  double-fire de `LordOfTempestsAddIceAbility`.
* **`On(8 = AttackHit)`** reste émis après `On(9)` au lieu d'avant, et **par attaque** au lieu de
  **par coup** : inerte (0 écouteur), non élargi ici.
* **La voie ABILITY n'a PAS bougé** : `after_hit_ability_attack` émet déjà son `On(9)` depuis
  l'intérieur des opérations d'ability (`damage_ops/ability.py`, `damage_ops/normal_like.py`), donc
  une attaque d'ability déclenchée par un trigger le traversait déjà.
* **Les autres écouteurs sous tir d'overwatch** ne sont pas confrontés un par un : seul 1147 l'est.
  Le déplacement les réveille tous sur ce chemin ; leurs gardes existantes (§5) attestent la
  non-régression sur le chemin d'attaque ORDINAIRE, pas le comportement neuf sous overwatch.
