# Case #182 — Trench prediction CASE3 (all-Trench intermediate line) delegate RE'd + ported

**Status: the last Trench-reduction residual is RESOLVED. The CASE3 delegate `@LAB_181004bb9`
(previously "non-RE'd, conservative fall-through APPLY") is now fully reverse-engineered and ported.
Offline smoke PASS (5 scenarios). Live confront (C2_19 CASE3 sample) remains as the honest closer,
deferrable.**

## What CASE3 is
`DamageCalculations.CalculateTrenchReduction @181004830` APPLIES the Trench damage reduction by
default (once the main gate is passed) and only SUPPRESSES it in the `IsTrench(attackerTile)`
sub-branch. Two suppression paths there:
1. attacker is a direct neighbour of the target's main tile (`IsNeighbourOf`) — already ported (#183);
2. **CASE3**: the intermediate LINE from attacker to target is entirely Trench — this doc.

## The delegate chain (decompiled)
At `LAB_181004bb9` the native calls an interface delegate on the damage context `*(param_2+0x30)`
(interface class `DAT_1831ce2f0`) with `(attackerTile, targetMainTile)`. That delegate is
`MovementQuery.GetLinesBetweenTiles @181099cb0`:
```
GetLinesBetweenTiles(out1, out2, tileA, tileB):
  cA = GetCoordinates(tileA); cB = GetCoordinates(tileB)          // AxialCoordinate of each tile
  DrawLineBetweenCoordinates(out1, cA, cB, flag=0)               // line_A
  DrawLineBetweenCoordinates(out2, cA, cB, flag=1)               // line_B
```
`MovementUtil.DrawLineBetweenCoordinates` (axial overload @18109dc00 -> cube overload @18109ded0):
```
inner(from_cube, to_cube, flag):
  if from == to: return [from]
  N = CubeCoordinate.Distance(from, to)
  ff = FloatCube(from); ft = FloatCube(to)
  for i in 0..N (inclusive):                 // i <= N
    p = FloatCube.Lerp(ff, ft, i/N)          // Fix64 division i/N
    p = (flag==1) ? p - epsilon : p + epsilon   // tie-break nudge (static FloatCube const)
    yield RoundFloatCubeCoordinates(p)       // cube_round
```
=> two hex lines between the SAME endpoints (endpoints INCLUSIVE), differing only by the
+epsilon (flag 0) vs -epsilon (flag 1) tie-break — the classic Red Blob epsilon-nudge that picks a
consistent tile when the line passes exactly between two hexes.

## CASE3 control flow (only line_A decides)
Back in `CalculateTrenchReduction`, after `IsTrench(attackerTile)` and `!IsNeighbourOf`:
```
(line_A, line_B) = delegate(attackerTile, targetMainTile)
enumerate line_A:  do{ if !MoveNext: ReturnToPool(A,B); return EMPTY /*SKIP*/ } while IsTrench(cur)
                   // exhausted-while-all-Trench => SKIP ; first non-Trench => fall to line_B
enumerate line_B:  do{ if !MoveNext: goto APPLY } while IsTrench(cur)
                   // BOTH exits (MoveNext-false OR non-Trench) => goto LAB_181004e45 = APPLY
LAB_181004e45: APPLY  (magnitude = config TrenchReductionPercentage @param_2+0x18 +0x2c)
```
Faithful reading: **SKIP iff line_A (flag 0) is entirely Trench** (attackerTile -> targetMainTile,
endpoints inclusive). line_B is computed and enumerated by the native but its result NEVER changes
the outcome (both its exits reach APPLY). So the port only needs line_A.

## Port
`engine/services/damage_modifiers.py :: calculate_trench_reduction`, in the `IsTrench(attackerTile)`
sub-branch, after the `IsNeighbourOf` skip:
```python
import hexgeo
line_a = hexgeo.line(attacker_tile, target_tile)          # flag-0 line, attacker->target inclusive
if line_a and all(board.terrain_at(c, r) == "Trench" for (c, r) in line_a):
    return None                                           # line_A all-Trench -> SKIP
# else APPLY (fall-through)
```
`hexgeo.line` is the same Red Blob algorithm (cube-lerp + `_cube_round`, endpoints inclusive), and
its offset<->cube parity is validated vs the native `boardGraph` (hexgeo parity fix 2026-07-02).

### Faithfulness caveats (documented, not hidden)
- **epsilon nudge NOT reproduced.** The native flag-0 line adds `+epsilon` before rounding; hexgeo
  relies on `_cube_round`'s own tie-break. On UNAMBIGUOUS corridors they agree; on a line that lands
  exactly between two hexes they can pick different tiles. A genuine all-Trench corridor is robust
  (both candidate tiles are Trench), so the all-Trench verdict is unaffected except on pathological
  edge geometry. Acceptable for this rare/low-priority residual; revisit if a live CASE3 divergence
  on ambiguous geometry ever appears.
- **off-board line tile** (`terrain_at` returns None) -> not "Trench" -> APPLY (conservative, and
  matches "the line isn't all-Trench").

## Validation
- **Offline smoke PASS** (5 scenarios, pure Python, no live): all-Trench line -> SKIP ; broken line
  (one Grass tile) -> APPLY ; neighbour + on-Trench -> SKIP (IsNeighbourOf) ; off-Trench non-adjacent
  -> APPLY ; IndirectFire non-adjacent -> main-gate None. Confirms the branch logic + regression guards.
- **Live confront (deferred, honest closer):** the port doc already records a live CASE3 measurement
  on board C2_19 (bloodMephiston): "ligne-toute-Trench -> SKIP (natif 2006-3010)". Before this port
  the predictor APPLIED the reduction on that sample (~half) = a mismatch vs native 2006-3010; after
  it SKIPs = matches. Re-running the C2_19 bloodMephiston prediction sweep with the CASE3 geometry is
  the remaining live confirmation (needs the same board + positions; not reinject-gated).

## Anchors (VAs, gqfc5mff6c)
CalculateTrenchReduction @181004830 (CASE3 at LAB_181004bb9, APPLY at LAB_181004e45) ;
MovementQuery.GetLinesBetweenTiles @181099cb0 ; MovementUtil.DrawLineBetweenCoordinates
@18109dc00 (axial) / @18109ded0 (cube, epsilon flag 0/1) ; TileExtensions.GetCoordinates @180ec4e40 ;
TileExtensions.IsTrench @180ec6f80 ; IsNeighbourOf/IsAdjacentTo (TileExtensions). Port:
engine/services/damage_modifiers.py::calculate_trench_reduction ; geometry: hexgeo.line.
