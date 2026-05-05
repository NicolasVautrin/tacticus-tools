// L1 — Playbook scoring.
// Hooks BasePlaybook.Evaluate (sets per-evaluation context: caster +
// position + ability) and BasePlaybook.GenerateAction × 3 overloads
// (each call = one scored UnitAction with its Fix64 utility + embedded
// damage prediction).

import {
    findClass, findMethod, getFieldOffset,
} from "../../il2cpp/helpers.js";
import { abilityName } from "../../data/ability-names.js";
import {
    traceState, installStatus,
    emit, projectEntity, projectFirstTile, safeKlassName,
    readFix64FromArg, readDamagePrediction,
    enumerateMethodsByName,
    type EvalCtx,
} from "./state.js";

interface GenActionCtx {
    targetPtr: NativePointer;
    utility: number;
    actionTile: { count: number; tile: Record<string, unknown> | null };
}

let basePlaybookClass: NativePointer | null = null;
let basePlaybookAbilityTypeOffset = -1;

export function installL1(): void {
    basePlaybookClass = findClass(
        "BattleLogicAssembly.dll", "IdunBattle.AI.Playbook", "BasePlaybook");
    if (!basePlaybookClass) {
        installStatus.L1_class = "BasePlaybook not found";
        return;
    }
    basePlaybookAbilityTypeOffset = getFieldOffset(
        basePlaybookClass, "ActiveAbilityType");

    const evalMi = findMethod(basePlaybookClass, "Evaluate");
    if (!evalMi || evalMi.ptr.isNull()) {
        installStatus.L1_evaluate = "method not found";
    } else {
        try {
            Interceptor.attach(evalMi.ptr, {
                onEnter(args): void {
                    if (!traceState.enabled.L1) return;
                    const playbook = args[0];
                    const caster = args[1];
                    const casterPos = args[2];
                    let abilityType = -1;
                    if (basePlaybookAbilityTypeOffset >= 0) {
                        try {
                            abilityType = playbook.add(
                                basePlaybookAbilityTypeOffset).readS32();
                        } catch { /* default -1 */ }
                    }
                    const tile = projectFirstTile(casterPos, "casterTile");
                    const playbookKlass = !playbook.isNull()
                        ? safeKlassName(playbook.readPointer()) : "?";
                    const ctx: EvalCtx = {
                        caster: projectEntity(caster, "caster"),
                        casterTile: tile.tile,
                        abilityType,
                        playbookCls: playbookKlass,
                        startedAt: traceState.seq,
                    };
                    traceState.currentEval = ctx;
                    emit({
                        evt: "playbook_eval_begin",
                        playbook: ctx.playbookCls,
                        caster: ctx.caster,
                        casterTile: ctx.casterTile,
                        casterPosCount: tile.count,
                        ability: abilityName(abilityType),
                    });
                },
                onLeave(retval): void {
                    if (!traceState.enabled.L1) return;
                    const ev = traceState.currentEval;
                    if (ev) {
                        emit({
                            evt: "playbook_eval_end",
                            playbook: ev.playbookCls,
                            caster: ev.caster,
                            ability: abilityName(ev.abilityType),
                            bucketPtr: retval.toString(),
                            startedAt: ev.startedAt,
                        });
                    }
                    traceState.currentEval = null;
                },
            });
            installStatus.L1_evaluate = "ok";
        } catch (e) {
            installStatus.L1_evaluate = "attach_failed: "
                + (e as Error).message;
        }
    }

    let gaCount = 0;
    for (const m of enumerateMethodsByName(
        basePlaybookClass, "GenerateAction")) {
        try {
            Interceptor.attach(m.ptr, {
                onEnter(args): void {
                    if (!traceState.enabled.L1) return;
                    if (!traceState.currentEval) return;
                    // Stash inputs on the per-call context — emit happens
                    // in onLeave once the BucketAction (with its embedded
                    // UnitAction.DamagePrediction) is computed.
                    (this as { ctx?: GenActionCtx }).ctx = {
                        targetPtr: args[2],
                        utility: readFix64FromArg(args[3]),
                        actionTile: projectFirstTile(args[1], "actionTile"),
                    };
                },
                onLeave(retval): void {
                    if (!traceState.enabled.L1) return;
                    const ev = traceState.currentEval;
                    if (!ev) return;
                    const ctx = (this as { ctx?: GenActionCtx }).ctx;
                    if (!ctx) return;

                    // retval = BucketAction<UnitAction>* (heap pointer).
                    // Layout: object header (0x10) + Content (UnitAction*)
                    // at +0x10 + Utility (Fix64) at +0x18.
                    let prediction: Record<string, unknown> | null = null;
                    try {
                        if (!retval.isNull()) {
                            const ua = retval.add(0x10).readPointer();
                            if (!ua.isNull()) {
                                prediction = readDamagePrediction(ua);
                            }
                        }
                    } catch { /* keep null */ }

                    emit({
                        evt: "playbook_action",
                        playbook: ev.playbookCls,
                        caster: ev.caster,
                        ability: abilityName(ev.abilityType),
                        actionTile: ctx.actionTile.tile,
                        actionPosCount: ctx.actionTile.count,
                        target: projectEntity(ctx.targetPtr, "target"),
                        utility: ctx.utility,
                        prediction,
                        startedAt: ev.startedAt,
                    });
                },
            });
            gaCount++;
        } catch (e) {
            installStatus["L1_generateAction#" + gaCount]
                = "attach_failed: " + (e as Error).message;
        }
    }
    installStatus.L1_generateActionCount = String(gaCount);
}
