// Movement-scoring observability — read-only hooks on the 42
// `IdunBattle.AI.Utilities.*Utility.EvaluateMovementInSteps` factories.
//
// Purpose: discover empirically WHICH utilities fire for WHICH units/contexts,
// before deciding which ones to mutate. Each `EvaluateMovementInSteps` call
// emits a trace entry with the utility class and best-effort arg inspection
// (arg classes + raw entity ids when the first arg looks like an `IEntity`).
//
// No `Interceptor.replace` — only `attach`, so session cleanup is handled
// automatically by Frida. Ring-buffered to 5000 entries.

import {
    class_get_name, findClassAnywhere, findMethod, s,
} from "../il2cpp/helpers.js";
import { Ctx } from "../controller.js";

const NS_IDUNBATTLE = "IdunBattle.AI.Utilities";
const NS_IDUNBATTLELOGIC = "IdunBattleLogic.AI.Utilities";

// All 42 classes confirmed via il2cpp_full.json with an
// `EvaluateMovementInSteps` method. Namespace varies between the two
// (most are IdunBattle, a handful live under IdunBattleLogic).
const MOVEMENT_UTILITIES: readonly string[] = [
    "ATriggeredAbilityUtility",
    "AUnitEffectsUtility",
    "AdjacentToadstoolUtility",
    "AdjacentTreeAncientHealUtility",
    "AttractMechanicalsUtility",
    "AttractToDecoysUtility",
    "BaseUtility",
    "CapturePointTileUtility",
    "ComposedUtility",
    "ContaminatedUtility",
    "DespoiledGroundUtility",
    "DevoutPush_AdjacentRangedEnemies",
    "DislikeStartingTilesUtility",
    "EarlyWarningOverride_SpawnSummmonUtility",
    "EchoesFromTheWarp_FriendliesAvoidGhostUtility",
    "ElevationUtility",
    "EnvEndBombardmentUtility",
    "HeroDoorOpeningUtility",
    "LeadingTheCharge_ChargeTileUtility",
    "MV71SniperDroneSquad_SpawnTileUtility",
    "MaxDistanceToEnemiesUtility",
    "MaxDistanceToUnitTileUtility",
    "MinDistanceToClosestEnemyUtility",
    "MoltenForm_TilesUtility",
    "MoveTowardsUnitUtility",
    "NoMovementToTileWithAdjacentEnemiesUtility",
    "Phantasm_AvoidFriendlyPhantasmUtility",
    "PowerUpTileUtility",
    "RammingSpeed_MostAdjacentEnemies",
    "RangedAdjacentEnemyUtility",
    "RoyalGuard_AvoidAdjacentEnemiesUtility",
    "SteppableUnitUtility",
    "SummonDislikeDoorOpeningUtility",
    "SwornProtector_AvoidAdjacentEnemiesUtility",
    "TemporaryTileUtility",
    "TileDistanceUtility",
    "TileEffectsUtility",
    "TilePendingBlockableSummonUtility",
    "TriggeredAbilitiesNonOwnerUtility",
    "TriggeredAbilitiesUtility",
    "UnitSpecificBehavioursUtility",
];

interface TraceEntry {
    seq: number;
    ts: number;
    utility: string;
    // Best-effort: class name of first N args if they look like managed objs.
    argClasses: (string | null)[];
}

const MAX_TRACES = 5000;
const traces: TraceEntry[] = [];
const installStatus: Record<string, string> = {};
let installed = false;
let seq = 0;

// Try to read an IL2CPP object's class name. If the pointer isn't a managed
// obj (or is null/invalid), return null silently — this is best-effort
// introspection run inside Interceptor.attach where we mustn't throw.
function safeClassName(p: NativePointer): string | null {
    if (p.isNull()) return null;
    try {
        const klass = p.readPointer();
        if (klass.isNull()) return null;
        const name = s(class_get_name(klass) as NativePointer);
        if (!name || name.length === 0 || name.length > 128) return null;
        // Reject if name has non-printable chars — means we mis-read a non-obj.
        for (let i = 0; i < name.length; i++) {
            const c = name.charCodeAt(i);
            if (c < 32 || c > 126) return null;
        }
        return name;
    } catch { return null; }
}

function installOnce(): void {
    if (installed) return;
    installed = true;

    for (const cls of MOVEMENT_UTILITIES) {
        const k = findClassAnywhere(NS_IDUNBATTLE, cls)
               ?? findClassAnywhere(NS_IDUNBATTLELOGIC, cls);
        if (!k) { installStatus[cls] = "class_not_found"; continue; }
        const m = findMethod(k, "EvaluateMovementInSteps");
        if (!m || m.ptr.isNull()) {
            installStatus[cls] = "method_not_found";
            continue;
        }
        try {
            const utilityName = cls;
            Interceptor.attach(m.ptr, {
                onEnter(args): void {
                    if (traces.length >= MAX_TRACES) {
                        traces.shift();
                    }
                    // args[0]=this, args[1..3]=first real params (best-effort
                    // since signature isn't known for all overloads).
                    const argClasses: (string | null)[] = [];
                    for (let i = 1; i <= 3; i++) {
                        argClasses.push(safeClassName(args[i]));
                    }
                    traces.push({
                        seq: seq++,
                        ts: Date.now(),
                        utility: utilityName,
                        argClasses,
                    });
                },
            });
            installStatus[cls] = "ok";
        } catch (e) {
            installStatus[cls] = "attach_failed: " + (e as Error).message;
        }
    }
    Interceptor.flush();
    const okCount = Object.values(installStatus)
        .filter((v) => v === "ok").length;
    console.log("[movement-trace] installed on "
        + okCount + "/" + MOVEMENT_UTILITIES.length
        + " EvaluateMovementInSteps factories");
}

export function register(ctx: Ctx): void {
    // Auto-install at hook setup — no RPC needed to prime. Same pattern
    // as mode-source-capture: observability should be live by default.
    installOnce();

    ctx.rpc.movementTraceInstallStatus = (): unknown => ({
        installed,
        total: MOVEMENT_UTILITIES.length,
        okCount: Object.values(installStatus)
            .filter((v) => v === "ok").length,
        byStatus: installStatus,
    });

    ctx.rpc.dumpMovementTrace = (limit?: number): unknown => {
        const max = typeof limit === "number" && limit > 0 ? limit : 200;
        return {
            total: traces.length,
            seq,
            entries: traces.slice(-max),
        };
    };

    ctx.rpc.movementTraceStats = (): unknown => {
        const byUtility: Record<string, number> = {};
        for (const t of traces) {
            byUtility[t.utility] = (byUtility[t.utility] ?? 0) + 1;
        }
        // Sort descending by count for readability.
        const sorted = Object.entries(byUtility)
            .sort((a, b) => b[1] - a[1])
            .map(([k, v]) => ({ utility: k, count: v }));
        return {
            total: traces.length,
            seq,
            installedCount: Object.values(installStatus)
                .filter((v) => v === "ok").length,
            byUtility: sorted,
        };
    };

    ctx.rpc.clearMovementTrace = (): unknown => {
        traces.length = 0;
        return { ok: true };
    };
}
