// Shared state for the overwatch-fix feature: the live `fix` singleton with
// the overwatcher map, configuration knobs, diagnostic counters and sample
// buffers. Every hook module reads/writes this — kept in a separate file so
// hook modules don't form circular imports with each other.

import { fix64FromInt, readUtilityConstants } from "../../ai-toolkit/fix64.js";

// --- Threat range default ---
// Empirical knowledge from the game (player-reported):
//   - Most overwatchers: range 3 hex
//   - Re'vas (Crisis Suit, Cyclic Ion Blaster): range 2 hex
//   - Forcas (Calibanite Greatsword): melee = range 1 hex
// Default to 3 — covers the majority. Per-unit refinement should come from
// either:
//   (a) reading the unit's NormalAttackRangeFormula at runtime, OR
//   (b) matching on the unit's VisualId (string) to a known table.
// For v2 we use the global default; tunable per-unit via overwatchFixEnable
// {threatRange: N}.
export const DEFAULT_THREAT_RANGE = 3;

// Replacement Fix64 — large enough to dominate typical utility scores (10s-100s)
// but small enough that summing N yields per move stays well within int64
// range (avoid overflow → sign flip → inverse effect).
//   -10000 Fix64 raw = -4.3e13. Sum of 100 yields = -4.3e15, far from int64
//   limits (~9.2e18).
export const DEFAULT_PENALTY_FIX64 = fix64FromInt(-10000);

// REJECT/SKIP/BONUS/... are directive sentinels the score aggregator
// interprets specially (REJECT short-circuits a candidate). Read via
// ai-toolkit/fix64.readUtilityConstants — see that module for context.
export const utilityConsts = readUtilityConstants();

export interface OverwatcherInfo {
    ownerPtr: string;
    sinceTs: number;
    /** Cached resolved (col, row) — set lazily on first MoveNext fire that
     * sees this overwatcher. Re'vas etc. usually don't move while
     * Overwatching, so cache is stable for the duration. */
    cachedPos: { col: number; row: number } | null;
    /** Per-overwatcher threat range. Defaults to DEFAULT_THREAT_RANGE; can
     * be overridden per-unit in v3. */
    range: number;
}

export const fix = {
    enabled: false,
    /** Master gate on the should-execute veto. When false, the trigger
     * observation hook still records data but the AI is allowed to suicide
     * — used to reproduce the OW firing path so we can observe what the
     * runtime predicate (`Overwatch_AutoAttackEffect`'s IAbilityTrigger)
     * actually evaluates. Toggle via `overwatchFixSetVetoEnabled` RPC. */
    vetoEnabled: true,
    penalty: DEFAULT_PENALTY_FIX64,
    threatRange: DEFAULT_THREAT_RANGE,
    overwatchers: new Map<string, OverwatcherInfo>(),
    /** Units carrying an `Infiltrate_UnitEffect`. Infiltrate makes a unit
     * invisible to Overwatch triggers — they enter an Overwatch zone
     * without being shot. We must NOT veto their NormalAttack actions
     * even when their casterTile is inside an OW range.
     * Key: unit IEntity pointer as hex string (same form `BaseEffect.Apply`
     * sees on its `target` arg). */
    infiltratedUnits: new Set<string>(),
    diag: {
        applyHookFires: 0,
        overwatchersTracked: 0,
        overwatchersPruned: 0,
        moveNextFires: 0,
        moveNextInjections: 0,
        moveNextSkippedNoOverwatchers: 0,
        moveNextSkippedNotInRange: 0,
        moveNextSkippedReadFailed: 0,
        positionResolveErrors: 0,
        writeFix64Errors: 0,
        // Aggregator (UtilityDecider.CalculateUtility) hook diag.
        calcUtilityFires: 0,
        calcUtilitySkippedNotMoveCase: 0,
        calcUtilitySkippedNoOverwatchers: 0,
        calcUtilitySkippedNoCachedPos: 0,
        calcUtilitySkippedNotInRange: 0,
        calcUtilityRejected: 0,
        calcUtilityReadFailed: 0,
        calcUtilityCasesScanned: 0,
        calcUtilityCasesIdentified: 0,
        // Bucket<T>.AddAction hook diag (broad catch for ability-driven moves).
        bucketAddActionFires: 0,
        bucketSkippedNoOverwatchers: 0,
        bucketSkippedNotInRange: 0,
        bucketActionsPatched: 0,
        bucketWriteFailed: 0,
        // BasePlaybook.GenerateAction hook diag.
        genActionFires: 0,
        genActionSkippedNotInRange: 0,
        genActionPatched: 0,
        genActionWriteFailed: 0,
        // onLeave verification: did our REJECT score actually survive into
        // the returned BucketAction<UnitAction>.Utility?
        genActionLeaveSurvived: 0,
        genActionLeaveOverwritten: 0,
        genActionLeaveNullRet: 0,
        genActionLeaveReadFailed: 0,
        // ActiveAbilityActionGenerator.<GenerateActions>d__6.MoveNext consumer
        // diag — observes which UnitAction the coroutine actually yields, vs
        // our patched bucket.
        consumerYieldFires: 0,
        consumerYields: 0,
        consumerYieldedInRange: 0,
        consumerYieldReadFailed: 0,
        // ALoki_NormalAttackPlaybook<T>.ShouldExecute hook diag — last-mile
        // veto on Loki normal-attack actions whose caster ends up in OW.
        shouldExecuteFires: 0,
        shouldExecuteSkippedNoOverwatchers: 0,
        shouldExecuteSkippedNotInRange: 0,
        shouldExecuteSkippedInfiltrate: 0,
        shouldExecuteVetoed: 0,
        shouldExecuteReadFailed: 0,
        shouldExecuteWriteFailed: 0,
        // Infiltrate tracking diag.
        infiltrateApplyFires: 0,
        infiltrateUnitsTracked: 0,
        // Trigger observation hook diag — captures Overwatch effect's
        // IAbilityTrigger.ShouldTrigger at runtime so we can read the actual
        // game-side predicate ("is owner stunned / engaged / out-of-ammo /
        // ...") without guessing.
        triggerCreateFires: 0,
        triggerCaptured: 0,
        triggerShouldTriggerFires: 0,
        triggerShouldTriggerTrue: 0,
        triggerShouldTriggerFalse: 0,
    },
    /** Sample of utility values seen at GenerateAction.onLeave for patched
     * fires. If REJECT round-trips, every entry should be REJECT (the magic
     * value -9223372036854775808). If GenerateAction recomputes, the values
     * will be normal Fix64 scores. */
    genActionLeaveUtilSamples: [] as Array<{
        utility: string; expectedReject: boolean; ts: number;
    }>,
    /** Per Decide call: list size + class names — to pinpoint which
     * collection layout the AI uses for movement candidates. */
    decideListSizes: [] as Array<{
        size: number; listCls: string; elemCls: string; itemsNull: boolean;
    }>,
    /** Sampled destination tile coordinates from MoveNext fires, for diag.
     * Helps verify moveCase reading is correct. */
    destSamples: [] as Array<{ col: number; row: number; ts: number }>,
    /** Positions actually patched by GenerateAction onEnter — distinct from
     * destSamples (which mixes MoveNext+GenerateAction noise). */
    patchedSamples: [] as Array<{ col: number; row: number; ts: number }>,
    /** Backtraces captured at GenerateAction.onEnter, deduped by category +
     * topRva. RVAs are emitted as hex offsets into GameAssembly.dll, to be
     * resolved offline against data/dumps/<HASH>/. Three buckets:
     *   - "patched": dest read OK, in-range, args[3] muted
     *   - "out_of_range": dest read OK, distance > threat range
     *   - "no_dest": args[1] read failed (likely ability-driven path with
     *     a different signature — Charge/Leap/Kamikaze, NOT UnitPosition) */
    genActionStacks: [] as Array<{
        category: "patched" | "out_of_range" | "no_dest";
        topRva: number; frames: string[]; ts: number;
    }>,
    /** Counters for each category — to know how many fires are in each bucket
     * even when their stack signature dedups out. */
    genActionCategoryCounts: {
        patched: 0, out_of_range: 0, no_dest: 0,
    } as Record<string, number>,
    /** Sampled positions yielded by ActiveAbilityActionGenerator.MoveNext —
     * should never include positions in OW range if our patch worked
     * through. */
    consumerYieldSamples: [] as Array<{
        col: number; row: number; inRange: boolean; ts: number;
    }>,
    /** Backtraces captured at ActiveAbilityActionGenerator.MoveNext onLeave
     * when an in-range yield happens — to identify the upstream caller
     * chain that ignores our patched BucketAction.Utility. */
    consumerYieldStacks: [] as Array<{
        topRva: number; frames: string[]; pos: { col: number; row: number };
        ts: number;
    }>,
    /** Per-yield identification of the playbook + ability type producing
     * the in-range UnitAction. Read from the state machine's
     * <playbook>5__5 (@0x58) and <activeAbilityType>5__4 (@0x50). The stack
     * frames only show generic `BasePlaybook.Evaluate` — they don't reveal
     * which IPlaybook subclass is concretely wired in for this ability. */
    consumerYieldProducers: [] as Array<{
        pos: { col: number; row: number };
        playbookClass: string | null;
        playbookNs: string | null;
        activeAbilityType: number | null;
        ts: number;
    }>,
    /** Dedup tracker for producers. */
    _consumerYieldProducerKeys: new Set<string>(),
    /** Sampled positions where ShouldExecute returned an override-to-false.
     * Lets us correlate the veto with the actual suicide spot the AI was
     * about to commit. */
    shouldExecuteVetoSamples: [] as Array<{
        col: number; row: number; ts: number;
    }>,
    /** Set of trigger root pointers captured from
     * `Overwatch_AutoAttackEffect.CreateActiveCondition`. Used to filter
     * `ShouldTrigger` fires to just our overwatch instances. */
    capturedTriggerPtrs: new Set<string>(),
    /** ShouldTrigger fire log — one entry per call. Useful for offline
     * analysis of when the predicate returned false (= OW disabled). */
    triggerShouldTriggerLog: [] as Array<{
        triggerPtr: string;
        retval: boolean;
        ownerPtr: string | null;
        targetPtr: string | null;
        casterTilePtr: string | null;
        ts: number;
    }>,
    listeners: [] as InvocationListener[],
    /** Per-method invocation counts for UtilityDecider — temporary diag to
     * identify which entry method the AI's decision actually goes through. */
    diagMethodFires: {} as Record<string, number>,
};

/** Detach every listener registered by hook modules. Called from the RPC
 * layer on `disable`. */
export function detachAll(): void {
    for (const l of fix.listeners) {
        try { l.detach(); } catch { /* */ }
    }
    fix.listeners = [];
}

/** Reset every diag counter and sample buffer back to zero. Called from the
 * RPC layer (`/api/overwatch-fix/reset-diag`). */
export function resetDiag(): void {
    Object.keys(fix.diag).forEach((k) => {
        (fix.diag as Record<string, number>)[k] = 0;
    });
    Object.keys(fix.diagMethodFires).forEach((k) => {
        fix.diagMethodFires[k] = 0;
    });
    fix.destSamples = [];
    fix.patchedSamples = [];
    fix.genActionStacks = [];
    Object.keys(fix.genActionCategoryCounts).forEach((k) => {
        fix.genActionCategoryCounts[k] = 0;
    });
    fix.genActionLeaveUtilSamples = [];
    fix.consumerYieldSamples = [];
    fix.consumerYieldStacks = [];
    fix.consumerYieldProducers = [];
    fix._consumerYieldProducerKeys.clear();
    fix.shouldExecuteVetoSamples = [];
    fix.triggerShouldTriggerLog = [];
}
