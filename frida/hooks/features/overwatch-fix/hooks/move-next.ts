// Hook: TriggeredAbilitiesNonOwnerUtility.<EvaluateMovementInSteps>d__N.MoveNext
//
// The state machine's MoveNext yields one Fix64 score per movement candidate.
// We hook onLeave; if the iterator yielded (retval=true) and the move's
// destination tile sits within hex range of any tracked overwatcher, we
// overwrite both `<>2__current` (the yielded value) and `<evaluation>5__2`
// (the inner accumulator) with `BaseUtility.REJECT` — the directive
// sentinel the score aggregator interprets as "discard this candidate
// entirely".

import { hexDistance } from "../../../ai-toolkit/hex.js";
import {
    BU_STATE, LIST_ITEMS_BASE, LIST_ITEMS_PTR, UMC,
} from "../../../ai-toolkit/unit-action.js";
import { readTilePosition } from "../../../game/match-state.js";
import { moveNextMi, SM } from "../resolve.js";
import { fix, utilityConsts } from "../state.js";
import { resolveOverwatcherPos } from "../track.js";

export function installMoveNextHook(): void {
    if (!moveNextMi || moveNextMi.ptr.isNull()) return;
    fix.listeners.push(Interceptor.attach(moveNextMi.ptr, {
        onEnter(args) {
            (this as { _sm?: NativePointer })._sm = args[0];
        },
        onLeave(retval) {
            fix.diag.moveNextFires++;
            if (retval.toInt32() === 0) return;  // iterator done
            if (fix.overwatchers.size === 0) {
                fix.diag.moveNextSkippedNoOverwatchers++;
                return;
            }
            const sm = (this as { _sm?: NativePointer })._sm;
            if (!sm || sm.isNull()) return;

            // Read state from utility @ <>4__this @ 0x28, then State @ 0x10
            // on BaseUtility-derived class.
            let state: NativePointer;
            let destPos: { col: number; row: number } | null;
            try {
                const utility = sm.add(SM.thisRef).readPointer();
                if (utility.isNull()) {
                    fix.diag.moveNextSkippedReadFailed++; return;
                }
                state = utility.add(BU_STATE).readPointer();
                if (state.isNull()) {
                    fix.diag.moveNextSkippedReadFailed++; return;
                }
                // Read dest tile from moveCase.MovementPosition.Tiles[0]
                const moveCase = sm.add(SM.moveCase).readPointer();
                if (moveCase.isNull()) {
                    fix.diag.moveNextSkippedReadFailed++; return;
                }
                const tileList =
                    moveCase.add(UMC.movementPosition).readPointer();
                if (tileList.isNull()) {
                    fix.diag.moveNextSkippedReadFailed++; return;
                }
                const items = tileList.add(LIST_ITEMS_PTR).readPointer();
                if (items.isNull()) {
                    fix.diag.moveNextSkippedReadFailed++; return;
                }
                const destTile = items.add(LIST_ITEMS_BASE).readPointer();
                if (destTile.isNull()) {
                    fix.diag.moveNextSkippedReadFailed++; return;
                }
                destPos = readTilePosition(destTile);
                if (!destPos) {
                    fix.diag.moveNextSkippedReadFailed++; return;
                }
            } catch {
                fix.diag.moveNextSkippedReadFailed++; return;
            }

            // Keep a small sample buffer of destination coordinates for
            // diagnostic — lets us verify moveCase reading is correct.
            if (fix.destSamples.length < 30) {
                fix.destSamples.push({
                    col: destPos.col, row: destPos.row, ts: Date.now(),
                });
            }

            // For each tracked overwatcher: re-resolve position fresh on
            // every MoveNext (cheap — ~50 entity reads). If a tracked
            // overwatcher no longer has a UnitFoot in current state, it's
            // dead/removed → prune. Avoids stale tracking polluting the
            // injection across multiple matches/turns.
            let inRange = false;
            const stale: string[] = [];
            for (const [key, info] of fix.overwatchers) {
                let pos: { col: number; row: number } | null;
                try {
                    pos = resolveOverwatcherPos(state, ptr(info.ownerPtr));
                } catch {
                    fix.diag.positionResolveErrors++;
                    pos = null;
                }
                if (!pos) {
                    stale.push(key);
                    continue;
                }
                info.cachedPos = pos;  // update cache for status inspection
                const d = hexDistance(
                    destPos.col, destPos.row, pos.col, pos.row);
                if (d <= info.range) { inRange = true; }
            }
            for (const key of stale) {
                fix.overwatchers.delete(key);
                fix.diag.overwatchersPruned++;
            }
            if (!inRange) {
                fix.diag.moveNextSkippedNotInRange++;
                return;
            }
            // YIELD `BaseUtility.REJECT` — the sentinel value the AI's
            // utility aggregator interprets as "discard this candidate
            // entirely". A plain numeric -10000 (our v2 attempt) was
            // summed into the total score and could lose to other
            // utilities' positive contributions. `REJECT` short-circuits
            // the candidate selection deterministically.
            //
            // We also overwrite `<>5__2` (the per-iter accumulator) with
            // the same sentinel as a belt-and-suspenders measure in case
            // the aggregator reads the accumulator field directly after
            // the iterator completes.
            const yieldVal = utilityConsts.REJECT ?? fix.penalty;
            try {
                sm.add(SM.current).writeS64(yieldVal);
                sm.add(SM.evaluation).writeS64(yieldVal);
                fix.diag.moveNextInjections++;
            } catch { fix.diag.writeFix64Errors++; }
        },
    }));
}
