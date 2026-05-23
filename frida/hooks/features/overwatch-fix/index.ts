// Overwatch-aware AI fix — orchestrator + RPCs.
//
// Background: the game's AI has a blind spot — `Overwatch_AutoAttackEffect`
// (1009) isn't a TriggeredAbility (no NonOwnerPlaybook for it), nor does it
// expose a DangerZone. So `TriggeredAbilitiesNonOwnerUtility` and the
// utility-config scoring framework never see the threat. AI units routinely
// suicide into Re'vas / Maugan Ra / Forcas / Calandis overwatch.
//
// This module wires together specialised hook installers:
//   - track.ts            BaseEffect.Apply hook (overwatcher tracking)
//   - hooks/move-next.ts  EvaluateMovementInSteps yield-time penalty
//   - hooks/decide.ts     UtilityDecider.Decide aggregator input filter
//   - hooks/gen-action.ts BasePlaybook.GenerateAction args[3] patch
//   - hooks/consumer-yield.ts ActiveAbilityActionGenerator yield-time observation
//   - hooks/bucket.ts     Bucket<T>.AddAction Utility patch
//   - hooks/calc-utility.ts UtilityDecider.CalculateUtility return override
//
// Plus a proactive scanner (scan.ts) that walks a matchstate at save-load
// time to find OverwatchAutoAttackAbility instances whose owners must be
// pre-armed in the tracker (the dynamic Apply hook only fires when the
// overwatch actually triggers, which is too late for pre-arm).
//
// Affects both live AI and mirror auto-play since the hooked methods are
// shared across runner instances.

import { Ctx } from "../../controller.js";
import { fix64FromInt } from "../../ai-toolkit/fix64.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { classesReady, reportResolution } from "./resolve.js";
import { detachAll, fix, resetDiag, utilityConsts } from "./state.js";
import { autoArm, pickRunnerState, scanStateForOverwatchers } from "./scan.js";
import { installTrackingHook } from "./track.js";
import { installMoveNextHook } from "./hooks/move-next.js";
import { installDecideHooks } from "./hooks/decide.js";
import { installGenActionHooks } from "./hooks/gen-action.js";
import { installConsumerYieldHook } from "./hooks/consumer-yield.js";
import { installBucketHooks } from "./hooks/bucket.js";
import { installCalcUtilityHook } from "./hooks/calc-utility.js";
import { installShouldExecuteHook } from "./hooks/should-execute.js";
import { installTriggerObserveHook } from "./hooks/trigger-observe.js";

function installHooks(): boolean {
    if (!classesReady()) return false;
    if (fix.listeners.length > 0) return true;
    installTrackingHook();
    installMoveNextHook();
    installDecideHooks();
    installGenActionHooks();
    installConsumerYieldHook();
    installBucketHooks();
    installCalcUtilityHook();
    installShouldExecuteHook();
    installTriggerObserveHook();
    Interceptor.flush();
    return true;
}

export function register(ctx: Ctx): void {
    // NOT auto-enabled — POST /api/overwatch-fix/enable to install hooks.

    ctx.rpc.overwatchFixStatus = (): unknown => ({
        enabled: fix.enabled,
        vetoEnabled: fix.vetoEnabled,
        ready: classesReady(),
        overwatchers: [...fix.overwatchers.values()].map((o) => ({
            ownerPtr: o.ownerPtr,
            cachedPos: o.cachedPos,
            range: o.range,
        })),
        infiltratedUnits: [...fix.infiltratedUnits],
        penaltyFix64: fix.penalty.toString(),
        threatRange: fix.threatRange,
        utilityConsts: {
            OK: utilityConsts.OK?.toString() ?? null,
            BONUS: utilityConsts.BONUS?.toString() ?? null,
            TAKE: utilityConsts.TAKE?.toString() ?? null,
            SKIP: utilityConsts.SKIP?.toString() ?? null,
            REJECT: utilityConsts.REJECT?.toString() ?? null,
            REJECT_IF_VALID_EXISTS:
                utilityConsts.REJECT_IF_VALID_EXISTS?.toString() ?? null,
            YIELD_NULL: utilityConsts.YIELD_NULL?.toString() ?? null,
        },
        diag: { ...fix.diag },
        diagMethodFires: { ...fix.diagMethodFires },
        decideListSizes: [...fix.decideListSizes],
        destSamples: fix.destSamples.slice(-10),
        patchedSamples: fix.patchedSamples.slice(-30),
        genActionStacks: [...fix.genActionStacks],
        genActionCategoryCounts: { ...fix.genActionCategoryCounts },
        genActionLeaveUtilSamples: [...fix.genActionLeaveUtilSamples],
        consumerYieldSamples: [...fix.consumerYieldSamples],
        consumerYieldStacks: [...fix.consumerYieldStacks],
        consumerYieldProducers: [...fix.consumerYieldProducers],
        shouldExecuteVetoSamples: [...fix.shouldExecuteVetoSamples],
        capturedTriggerPtrs: [...fix.capturedTriggerPtrs],
        triggerShouldTriggerLog:
            fix.triggerShouldTriggerLog.slice(-50),
        resolution: reportResolution(),
    });

    ctx.rpc.overwatchFixResetDiag = (): unknown => {
        resetDiag();
        return { ok: true };
    };

    ctx.rpc.overwatchFixEnable = (
        body?: { penalty?: number; threatRange?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (body?.penalty !== undefined) {
            fix.penalty = fix64FromInt(-Math.abs(body.penalty));
        }
        if (body?.threatRange !== undefined) {
            fix.threatRange = body.threatRange;
            for (const info of fix.overwatchers.values()) {
                info.range = body.threatRange;
            }
        }
        if (!classesReady()) {
            return { ok: false, error: "classes not ready",
                resolution: reportResolution() };
        }
        const installed = installHooks();
        fix.enabled = installed;
        return {
            ok: installed, listeners: fix.listeners.length,
            penaltyFix64: fix.penalty.toString(),
            threatRange: fix.threatRange,
            resolution: reportResolution(),
        };
    });

    ctx.rpc.overwatchFixDisable = (): unknown => {
        fix.enabled = false;
        detachAll();
        return { ok: true };
    };

    /** Toggle the should-execute veto without detaching any hooks. When
     * vetoEnabled=false, the AI is allowed to suicide as normal — useful
     * to capture runtime fires of `Overwatch_AutoAttackEffect`'s
     * IAbilityTrigger.ShouldTrigger so we can read the actual game-side
     * predicate for OW activation. */
    ctx.rpc.overwatchFixSetVetoEnabled = (
        body?: { enabled?: boolean },
    ): unknown => {
        if (body?.enabled !== undefined) {
            fix.vetoEnabled = !!body.enabled;
        }
        return { ok: true, vetoEnabled: fix.vetoEnabled };
    };

    ctx.rpc.overwatchFixClearTracking = (): unknown => {
        const beforeOw = fix.overwatchers.size;
        const beforeInf = fix.infiltratedUnits.size;
        fix.overwatchers.clear();
        fix.infiltratedUnits.clear();
        return { ok: true, clearedOverwatchers: beforeOw,
            clearedInfiltrated: beforeInf };
    };

    /** Diag-only: scan the matchstate of `scope` (live | build runnerId)
     * and return every Overwatch_AutoAttackEffect sighting WITHOUT
     * touching the tracker. Lets us verify the structure before
     * activating the auto-arm. */
    ctx.rpc.overwatchScanState = (
        body?: { scope?: "live" | number },
    ): Promise<unknown> => queueOnMainThread(() => {
        const scope = (body?.scope ?? "live") as "live" | number;
        const stateP = pickRunnerState(scope);
        if (!stateP) {
            return { ok: false, reason: "no matchstate for scope " + scope };
        }
        const hits = scanStateForOverwatchers(stateP);
        return { ok: true, scope, hits: hits.length, results: hits };
    });

    /** Run the scan + REGISTER any hit owner into the tracker. Idempotent
     * (re-running won't add duplicates). Call after save load and before
     * end-turn to ensure the tracker is armed before AI evaluation. */
    ctx.rpc.overwatchAutoArm = (
        body?: { scope?: "live" | number },
    ): Promise<unknown> => queueOnMainThread(() => {
        const scope = (body?.scope ?? "live") as "live" | number;
        return autoArm(scope);
    });
}
