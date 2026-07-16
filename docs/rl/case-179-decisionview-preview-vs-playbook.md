# Case #179 residual — astraPrimarisPsy NORMAL-attack attackPlans PREVIEW collapses min->max

**Status: PARTIALLY resolved + a PRIOR MISDIAGNOSIS CORRECTED. The SquigHound/BeastSlayer bound was
fixed+committed (133c23a). The remaining astraPrimarisPsy (Sibyll) residual is a real
`decisionView.attackPlans` PREVIEW-vs-truth discordance on the unit's NORMAL attack (NOT a config-based
special). The engine matches the true per-ability oracle `aiPlaybookPredict`. The exact MECHANISM of the
preview's min->max collapse is still OPEN (needs a clean live capture).**

## CORRECTION of an earlier (wrong) diagnosis
An earlier version of this doc + commit 7b991b3 attributed the residual to the config-based special
**PsychicMaelstrom (1027)** leaking through `predict_samples` via an empty `norm_ids` filter. **That is
WRONG.** Live ground truth (seed 500, board MC1_67):

- astraPrimarisPsy = id 85, **HP 5522**, abilities = `[(69,'normal'), (1027,'active')]` -> `norm_ids = {69}`
  is **NON-empty**.
- `predict_samples` therefore keeps **only the NORMAL attack (69)** and filters PsychicMaelstrom OUT.
  The sampled/compared ability is the **NORMAL attack**, not a config-based special.

So: no special leaked, `norm_ids` is not empty, and the "skip config-based specials" harness fix
(tracked as #186) is MOOT for this case. Retracted.

## What the residual actually is
For astraPrimarisPsy's NORMAL attack (69) on seed 500 (task's re-expert record):
- `decisionView.attackPlans` dmgMin/dmgMax = **(5522, 5522)** (min collapsed UP to the max).
- `aiPlaybookPredict(69)` = **(2505, 5522)** (variance kept) — matches the engine `(2507, 5522)`.

The engine (via `make_normal_attack_predictions`) agrees with `aiPlaybookPredict` to within 2 units. The
divergence is ONLY the decisionView preview's min, which equals the max (5522). Note 5522 also equals
astraPrimarisPsy's own HP — likely coincidence (Psyker glass cannon: HP ~ max hit), NOT proven related.

## Where the collapse is NOT
`projection.ts::applyDmg` sets `entry.dmgMin = dmgMin; entry.dmgMax = dmgMax` verbatim from the source
(playbook event `healthDmgMin/Max`, or the preview `DamagePredictionResult` AccurateHealthDamage). It
applies NO min->max clamp itself (only the kill/killSure flags use effective death thresholds). So the
collapse is UPSTREAM of projection.ts — either:
- the native PREVIEW `DamagePredictionResult` (from `GetAllPredictions @181090f50` -> `FUN_18000cdc0`
  interface-slot-3) reports AccurateHealthDamage min==max for this attack, OR
- the attackPlans eval for this target was filled from the preview path (not the playbook path) because
  the playbook prediction had no event for that target.

## OPEN (needs a clean live capture to resolve)
Drive astraPrimarisPsy into normal-attack range of a specific target on seed 500 MC1_67 and record, in
ONE state: the target HP/armor, the attackPlans eval (dmgMin/dmgMax + which path filled it) and
`aiPlaybookPredict(69)` side by side + the engine base/pierce/armor/hits. Determine WHY the preview min
collapses to max (candidate: the native preview `DamagePredictionResult` min==max for astraPrimarisPsy's
weapon, or an overkill/kill-guarantee display transform — task title hint "overkill-cap"). This capture
was attempted here but astraPrimarisPsy did not reach attack range within the generic drive; a targeted
per-unit drive is needed. Deferred (may share findings with #184, also normal-attack prediction).

## What still stands (general, verified)
`decisionView.attackPlans` (dmgMin/dmgMax) is a PREVIEW that can DIVERGE from the per-ability truth
`aiPlaybookPredict` (= `MakeDamagePredictions`). The engine is built to match the per-ability truth
(prediction.py doctrine ~L432-434). `predict_sweep.py` (oracle = aiPlaybookPredict) shows NO gap here.
`predict_samples.py` (oracle = attackPlans preview) surfaced this preview-vs-truth discordance. Use
`predict_sweep` for per-ability truth.

## Anchors (VAs, gqfc5mff6c)
DamagePredictionQuery.GetAllPredictions @181090f50 (preview) ; FUN_18000cdc0 (interface-slot-3
predict-vs-target dispatcher) ; DamagePredictionResult MinMax @0x90 (Min@0x98/Max@0x9C) ;
projection.ts::applyDmg (sets dmgMin/dmgMax verbatim, no collapse) ; <Ability>Playbook.MakeDamagePredictions
(= aiPlaybookPredict, per-ability truth). Carrier: astraPrimarisPsy id 85 (HP 5522), NORMAL attack 69.
