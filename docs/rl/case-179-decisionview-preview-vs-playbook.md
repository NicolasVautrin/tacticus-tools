# Case #179 residual — decisionView.attackPlans PREVIEW collapses min=max for config-based specials

**Status: RESOLVED as an ORACLE-SOURCE mismatch, NOT an engine bug. The SquigHound/BeastSlayer bound
was already fixed+committed (133c23a). The remaining astraPrimarisPsy (Sibyll) residual — decisionView
`(5522,5522)` vs engine `(2507,5522)` — is a `predict_samples.py` harness artifact: it reads the
GetAllPredictions PREVIEW, which is wrong for config-based specials. The engine matches the true
per-ability oracle `aiPlaybookPredict`.**

## The two oracle sources (why they differ)
| source | native path | for config-based special (PsychicMaelstrom 1027) |
|---|---|---|
| `decisionView.attackPlans` dmgMin/dmgMax | `DamagePredictionQuery.GetAllPredictions @181090f50` -> `FUN_18000cdc0` = **interface-slot-3** on the ability (generic "predict-vs-target") | COLLAPSES to a single value -> `(5522,5522)` |
| `aiPlaybookPredict` | `<Ability>Playbook.MakeDamagePredictions` (vtable +0x358, the path the AI actually scores) | keeps variance -> `(2505,5522)` |

`GetAllPredictions` builds ONE `DamagePredictionResult` (MinMax@0x90: Min@0x98/Max@0x9C) per target by
calling the ability's generic interface method (`FUN_18000cdc0(..., slot 3, ability, caster, pos,
target)`), which is Attack-based **whatever the abilityType**. For a plain NORMAL attack that generic
path == the real prediction (fine). For a config-based SPECIAL (bespoke playbook, `param_8=null` pierce
profile — PsychicMaelstrom is a #169 candidate) it does NOT run `MakeDamagePredictions`, so its
per-ability variance is lost and min collapses onto max.

## Evidence
- astraPrimarisPsy (Sibyll) active = **PsychicMaelstrom (1027)**, Ranged/Psychic, vars minDmg+maxDmg
  (a genuine damage range) — a config-based special with a bespoke playbook.
- Recorded measurements (seed 500, u87; re-expert): decisionView.attackPlans `(5522,5522)` ;
  aiPlaybookPredict `(2505,5522)` ; engine `(2507,5522)`.
- The engine matches `aiPlaybookPredict` (the true per-ability oracle) to within 2 units. The MAX
  (5522) agrees across all three; only the MIN collapses in the preview (5522) while playbook + engine
  keep it (~2505).
- The codebase already codifies the doctrine (prediction.py ~L432-434): "la verite per-ability =
  aiPlaybookPredict (#102), JAMAIS aiPredict/GetAllPredictions".

## Root cause in the harness
`predict_samples.py` compares the engine against `decisionView.attackPlans` (the preview). It is a
NORMAL-attack sampler, but a config-based special that ranks first in `attackPlans` (PsychicMaelstrom
does) gets sampled too -> false gap. `predict_sweep.py` already uses `aiPlaybookPredict` (correct
per-ability oracle) and shows NO gap. Fix applied: a WARNING in `predict_samples.py` header stating its
attackPlans oracle is the GetAllPredictions preview — valid for normal attacks, WRONG for config-based
specials (use `predict_sweep` for those). Recommended follow-up (not done, adds coupling): have
`predict_samples` SKIP config-based specials via the engine's `_PREDICT_VIA_NORMAL_ATTACK`/config
classification so it never false-flags them.

## Micro-residual (separate, tolerance-level)
engine MIN `2507` vs aiPlaybookPredict `2505` = a 2-unit (0.08%) diff on the min, a Fix64/rounding-order
artifact (min branch after pierce/armor), within the known #98/#170 rounding conventions. Not the
`5522` gap; flagged only for completeness. Revisit only if a systematic min under/over shows up.

## Anchors (VAs, gqfc5mff6c)
DamagePredictionQuery.GetAllPredictions @181090f50 (preview; per-target DamagePredictionResult) ;
FUN_18000cdc0 (generic interface-slot-3 predict-vs-target dispatcher) ; DamagePredictionResult MinMax
@0x90 (Min@0x98/Max@0x9C) ; <Ability>Playbook.MakeDamagePredictions (vtable +0x358 = aiPlaybookPredict,
per-ability truth). Harness: predict_samples.py (attackPlans preview oracle, guarded) vs predict_sweep.py
(aiPlaybookPredict oracle). Carrier: astraPrimarisPsy / PsychicMaelstrom 1027.
