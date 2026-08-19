// AI evaluation trace — captures the AI's "thinking" and streams events
// to the host for on-disk JSONL persistence.
//
// Coverage (each layer in its own focused submodule under ./ai-trace/):
//   playbooks    — L1: BasePlaybook.Evaluate + GenerateAction
//   generators   — L2: MovementActionGenerator + ActiveAbilityActionGenerator
//   utilities    — L3: per-utility per-tile state-machine yields
//   predictions  — Damage / Heal / Repair / ArmorRestore predictions
//   ai-control   — ApplyAiMessage (winner) + RunComputerActionsForPlayer
//
// Shared module state, projection schemas, and low-level helpers live in
// ./ai-trace/state.ts. All event records flow via `send({t:"ai_trace",
// ...})` → host writes a JSONL line. Tous les niveaux sont OFF par défaut,
// et l'INSTALLATION des hooks est LAZY (premier `aiTraceEnable`) : ~50
// trampolines (39 L3 MoveNext + L3atk + Predict* + L1/L2) sur les chemins
// IL2CPP les plus chauds — attachés au register, ils taxaient CHAQUE fire
// de la bataille réelle de l'amorce même gated (pattern de l'incident
// modifier-observe 2026-07-10 : churn inject + hooks chauds = crash).
// Un inject frais ne porte donc plus AUCUN trampoline ai-trace.
//
// Anchors used in projections (driven by aiTraceSetProjection RPC):
//   caster, target, closestEnemy, unit  (IEntity heap obj)
//   casterTile, actionTile, caseTile    (TileEntity = UnitPosition.Tiles[0])

import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";
import {
    traceState, installStatus, projections, ANCHORS,
    emit, type Levels,
} from "./ai-trace/state.js";
import { type PathSpec } from "../il2cpp/project.js";
import { installL1 } from "./ai-trace/playbooks.js";
import { installL2 } from "./ai-trace/generators.js";
import { installL3 } from "./ai-trace/utilities.js";
import {
    installDamagePredictionHook, installHealRepairHooks,
} from "./ai-trace/predictions.js";
import { installAiControlHooks } from "./ai-trace/ai-control.js";
import { queueOnMainThread } from "../runtime/queue.js";

function installOnce(): void {
    if (traceState.installed) return;
    traceState.installed = true;
    try { installL1(); } catch (e) {
        log("[ai-trace] L1 install failed: " + (e as Error).message);
    }
    try { installL2(); } catch (e) {
        log("[ai-trace] L2 install failed: " + (e as Error).message);
    }
    try { installL3(); } catch (e) {
        log("[ai-trace] L3 install failed: " + (e as Error).message);
    }
    try { installDamagePredictionHook(); } catch (e) {
        log("[ai-trace] damage prediction install failed: "
            + (e as Error).message);
    }
    try { installHealRepairHooks(); } catch (e) {
        log("[ai-trace] heal/repair install failed: "
            + (e as Error).message);
    }
    try { installAiControlHooks(); } catch (e) {
        log("[ai-trace] ai-control install failed: "
            + (e as Error).message);
    }
    Interceptor.flush();
    log("[ai-trace] installed — L1=" + (installStatus.L1_evaluate ?? "?")
        + ", L2=" + (installStatus.L2_MovementActionGenerator ?? "?")
        + ", L3=" + (installStatus.L3_okCount ?? "?")
        + ", PredictNormalAttack=" + (installStatus.PredictNormalAttack ?? "?")
        + ", PredictAttack=" + (installStatus.PredictAttack ?? "?")
        + ", PredictHeal=" + (installStatus.PredictHeal ?? "?")
        + ", PredictRepair=" + (installStatus.PredictRepair ?? "?")
        + ", PredictArmorRestore="
        + (installStatus.PredictArmorRestore ?? "?")
        + ", ApplyAiMessage=" + (installStatus.ApplyAiMessage ?? "?")
        + ", RunComputerActions="
        + (installStatus.RunComputerActions ?? "?"));
}

function isPathSpec(x: unknown): x is PathSpec {
    if (!x || typeof x !== "object") return false;
    const o = x as Record<string, unknown>;
    return typeof o.path === "string"
        && (o.out === undefined || typeof o.out === "string")
        && (o.type === undefined || typeof o.type === "string");
}

export function register(ctx: Ctx): void {
    // PAS d'installOnce() ici — install LAZY au premier aiTraceEnable (cf. en-tête : zéro
    // trampoline sur les hot paths pendant inject ; l'enable arme sur état CALME).

    ctx.rpc.aiTraceStatus = (): unknown => ({
        installed: traceState.installed,
        enabled: { ...traceState.enabled },
        seq: traceState.seq,
        installStatus,
        anchors: ANCHORS,
    });

    ctx.rpc.aiTraceEnable = (level: string): unknown => {
        const lv = level.toUpperCase() as keyof Levels;
        if (lv !== "L1" && lv !== "L2" && lv !== "L3") {
            return { ok: false, error: "level must be L1|L2|L3" };
        }
        // Install LAZY au premier enable (main thread : findClass/attach sur état calme,
        // post-amorce). Les enables suivants ne repayent rien (installOnce idempotent).
        if (!traceState.installed) {
            return queueOnMainThread(() => {
                installOnce();
                traceState.enabled[lv] = true;
                emit({ evt: "control", op: "enable", level: lv });
                return { ok: true, enabled: traceState.enabled, installedNow: true };
            });
        }
        traceState.enabled[lv] = true;
        emit({ evt: "control", op: "enable", level: lv });
        return { ok: true, enabled: traceState.enabled };
    };

    ctx.rpc.aiTraceDisable = (level: string): unknown => {
        const lv = level.toUpperCase() as keyof Levels;
        if (lv !== "L1" && lv !== "L2" && lv !== "L3") {
            return { ok: false, error: "level must be L1|L2|L3" };
        }
        traceState.enabled[lv] = false;
        emit({ evt: "control", op: "disable", level: lv });
        return { ok: true, enabled: traceState.enabled };
    };

    /** Returns the full projection map. */
    ctx.rpc.aiTraceGetProjections = (): unknown => projections;

    /** Replace the projection list for one anchor.
     * Body: { anchor: string, paths: PathSpec[] }
     * Pass paths: [] to clear (no fields → empty record). */
    ctx.rpc.aiTraceSetProjection = (
        body: { anchor: string; paths: PathSpec[] },
    ): unknown => {
        if (!body || typeof body.anchor !== "string"
            || !Array.isArray(body.paths)) {
            return { ok: false, error: "body must be { anchor, paths[] }" };
        }
        if (!ANCHORS.includes(body.anchor)) {
            return { ok: false, error: "unknown anchor; valid: "
                + ANCHORS.join(", ") };
        }
        for (const p of body.paths) {
            if (!isPathSpec(p)) {
                return { ok: false, error: "invalid PathSpec: "
                    + JSON.stringify(p) };
            }
        }
        projections[body.anchor] = body.paths;
        emit({ evt: "control", op: "setProjection",
            anchor: body.anchor, count: body.paths.length });
        return { ok: true, anchor: body.anchor, paths: body.paths };
    };
}
