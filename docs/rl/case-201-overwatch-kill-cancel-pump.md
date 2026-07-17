# Case #201 — Pump FIFO différé (RunPhase) : overwatch kill-cancel

**Symptôme** : deux overwatchers en portée d'un même mover ennemi. Le 1er tire et TUE le mover.
Le port faisait tirer le 2e overwatch **sur le cadavre** (2 tirs). Le natif n'en tire qu'**1**
(le 2e fizzle, plus de cible). Divergence d'ORDRE de cascade (umbrella #149, CAP archi mirror-native).

## Structure native (RE ghidra, build gqfc5mff6c)

Le natif traite les triggers via un **pump à deux niveaux** :

1. **Dispatch** — `EvaluateTriggerOperation.ExecuteInternal @180e6ef40` : itère le registre GLOBAL
   `AbilityAndEffectCache` (composant #3 = les triggers de CET event) → `EvaluateAbilityOrEffectTrigger`
   par entrée → **ENFILE** un *pending triggered-ability* (file #5). Il n'EXÉCUTE PAS inline.
   - `EvaluateTriggerOperation.Execute @180e6fac0` = variante différée : si on est déjà dans une phase
     (flag de ré-entrance) → **enfile un `BattleEvent`** ; sinon → `ExecuteInternal` immédiat.
   - `MoveUnitOperation.EvaluateAfterMoveTriggers @180e79770` construit l'`AbilityEntities` du move et
     **poste des messages** (codes `0x24`, `4`=UnitAfterMove, `0x1d`) sur le processor.

2. **Drain** — `ProcessPendingTriggeredAbilities @180eba680` : **SNAPSHOT** la file #5 dans une List +
   **`Queue.Clear`**, puis `foreach` item → **`RunPhase(0xf, item) @180ebaa80`**.

3. **`RunPhase(phase, callback)`** : invoque le callback (le behaviour de l'item) PUIS
   **`VerifyDeaths @180ebb0a0`** PUIS `ProcessDamageEvents @180eba4f0` PUIS
   `ProcessPendingTriggeredAbilities` (cascade imbriquée). => les morts causées par l'item **N** sont
   **retirées avant l'item N+1**.

**Kill-cancel** : les 2 overwatch after-move sont enfilés comme pending. Le drain lance
`RunPhase(0xf, OW_B)` → OW_B attaque → mover à 0 PV → `VerifyDeaths` le retire → puis
`RunPhase(0xf, OW_C)` → le behaviour `Overwatch_AutoAttackEffect.GetAttackBehaviour @180f5d3e0`
= `UseActiveAbility(NormalAttack)` sur le mover, mais il est mort/retiré (les sélecteurs DSL de cible
opèrent sur `AllAliveMachines`, cf. #202) → **fizzle**. Donc **1 tir**.

## Le port EST déjà le pump collapsé

`evaluate_trigger_operation` (dispatch.py) fait, en UNE boucle, l'équivalent observable :

- `registry = collect_triggered_abilities + collect_effect_triggers` = liste **matérialisée une fois**
  = le SNAPSHOT (les effets ajoutés pendant le drain n'entrent pas dans CE registre).
- la boucle draine le snapshot en ordre FIFO ; le **re-appel de `matches` par item** contre l'état
  COURANT = la re-validation de cible du `RunPhase(0xf)`.
- les morts sont appliquées **INLINE** par `_fire_death_if_killed` (`alive=False` + `after_death_triggers`
  LIFO) DANS `execute_behaviour` = le `VerifyDeaths`-entre-items (la victime est morte avant l'item suivant).

Une vraie file *pending* explicite (ordre snapshot-clear multi-rounds) n'ajoute **aucun effet observable**
pour la cascade #201 → **non portée** (blast-radius / ordre RNG) tant qu'aucune divergence ne l'exige.

## La vraie cause : leg *target-validity* manquante

Le port avait donc déjà le squelette du pump. Le seul trou : la re-validation par-item était
**incomplète**. `OverwatchAutoAttack.matches` vérifiait team + portée + immunité du mover, mais **jamais
que le mover est VIVANT**. Donc après que OW_B a mis `mover.alive = False` (inline), `OW_C.matches`
renvoyait encore `True` → tir sur le cadavre.

**Fix (faithful, pas band-aid)** — `OverwatchAutoAttack.matches` teste désormais `mover.alive` :

```python
mvu = mv.get_component(UnitComponent)
if mvu is not None and not mvu.alive:
    return False
```

C'est la **re-validation de cible du drain** (mirror : `VerifyDeaths` retire le mort → `AllAliveMachines`
ne le liste plus → `UseActiveAbility` fizzle). Ce n'est pas une rustine : c'est porter la validité-de-cible
que le natif applique structurellement entre items pending. La leg vit dans `matches` parce que le port
collapse « pending enqueue + drain » en « boucle avec re-`matches` par item ».

## Preuve (les DEUX faces)

- **Offline déterministe** (`scratchpad/probe_dual_overwatch.py`) : `necroOverlord` mover 1 PV entre 2
  `eldarRanger` (effet 1009 au déploiement). AVANT : port tire 2 (OW 79 sur cadavre, `matches=True`).
  APRÈS : OW 77 tire (mover 1→0, alive=False), OW 79 `mover_alive_before=False matches=False` → **1 tir**
  (drain manuel ET `after_move_triggers`). == natif.
- **Live A/B** (`scratchpad/probe_dual_overwatch_live.py`, signal = consommation de l'effet 1009) :
  mover survivant (`--hp-player 50000`) → 2/2 overwatchers tirent (les 2 en portée, cible vivante) ;
  mover fragile tué par le 1er → **1/2** (le 2e annulé par la mort). Natif=1 au kill, port désormais=1.
- **Non-régression** : `tests/engine/runner/test_overwatch_live.py` (single overwatch, mover survit) PASS
  → le gate alive ne casse pas le tir normal (mover vivant → `matches` inchangé).

## Fichiers

- `engine/runner/operations/triggers/effect_triggers.py` — `OverwatchAutoAttack.matches` + import
  `UnitComponent`.
- `engine/runner/operations/triggers/dispatch.py` — docstring de `evaluate_trigger_operation` : mapping
  explicite collapsed-pump ↔ natif (`ExecuteInternal` + `ProcessPendingTriggeredAbilities` + `RunPhase(0xf)`
  + `VerifyDeaths`).

## Résidu (hors scope, non requis par #201)

La vraie file pending explicite + `ProcessDamageEvents` (file #7, `RunPhase(0xe)`) restent collapsés.
Aucune divergence observée ne les exige aujourd'hui ; à ne porter que si un cas multi-mort / damage-event
différé exhibe un écart d'ordre RNG vs live (créer une tâche à ce moment-là).
