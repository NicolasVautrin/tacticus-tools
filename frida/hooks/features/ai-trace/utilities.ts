// L3 — Per-utility per-tile evaluation.
// Hooks the 41 *Utility.EvaluateMovementInSteps coroutines (compiler-
// generated `<EvaluateMovementInSteps>d__N.MoveNext`). Captures the
// final yielded Fix64 score along with the UtilityMovementCase being
// scored (target tile, unit, closest enemy, ability if any).
//
// #45b' : hooks AUSSI les coroutines `EvaluateAttackInSteps(Internal)` des
// feuilles du composite Damage(34) — breakdown natif par-feuille d'un case
// d'ATTAQUE (events `utility_score` mode:"attack", acteur/cible projetés
// depuis l'UtilityAttackCase). Sert à NOMMER un résidu additif de l'étage
// UTILITÉ (pairUtility vs formule offline) au lieu de le deviner.
//
// Also dumps ComposedUtility.Utilities once per unique instance so the
// composition tree is visible in the trace.

import {
    findMethod, findClassAnywhere, findClass, getFieldOffset,
    class_get_name, class_get_nested_types, s,
} from "../../il2cpp/helpers.js";
import { abilityName } from "../../data/ability-names.js";
import {
    traceState, installStatus,
    emit, projectEntity, projectFirstTile,
    readFix64Raw,
} from "./state.js";

const L3_UTILITIES: readonly string[] = [
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

// #45b' — feuilles du composite Damage(34) = [40,35,36,38,43,39,37,41,2,4,3,59,42]
// (membership dumpComposedUtility, case-34) hookées en mode ATTACK. Liste MINIMALE
// (chaque hook = un trampoline sur le hot-path du sweep IA — ne pas élargir sans besoin).
// Les 3 Dislike* (modificateur Π, CalculateAttackModifier non-itérateur) ne sont pas
// hookables ici — un Π≠1 se voit à la réconciliation ComposedUtility vs Σ feuilles.
const L3_ATTACK_UTILITIES: readonly string[] = [
    "ComposedUtility",                       // total par case = (Σ feuilles) × Π modifs
    "DamageUtility",                         // 35 DamageDealt
    "KillUnitUtility",                       // 36
    "OverkillUnitUtility",                   // 37
    "TriggeredAbilitiesUtility",             // 2  (owner, vslot 3 des playbooks triggered)
    "TriggeredAbilitiesNonOwnerUtility",     // 4  (IterateAbilities, vslot 1 NonOwner)
    "UnitSpecificBehavioursUtility",         // 3  (behaviours de l'ACTEUR)
    "AttackTargetWithEffectUtility",         // 42 (effets de la CIBLE × poids par nom)
    "EnemyOnTerritoryTileUtility",           // 41
    "OnlyImperviousUnitIfCanBeDamagedUtility",  // 40
    "OptimizedGait_AdjacentFriendsUtility",  // 59 (poids BC 0 ce build — contrôle)
];

// `UtilityAttackCase` (décompilé gqfc5mff6c : @181407890 scorer + @1810e2280 DamageUtility ;
// case-34 §MAJ #45bis) : +0x10 = ACTEUR, +0x18 = UnitPosition, +0x20 = CIBLE. Offsets de
// STRUCT du build courant (pas des RVAs) — mêmes conventions que COMP_FIELD ailleurs.
const ATTACK_CASE_ACTOR_OFF = 0x10;
const ATTACK_CASE_TARGET_OFF = 0x20;

let utilityCaseUnitOffset = -1;
let utilityCaseClosestEnemyOffset = -1;
let utilityCaseAbilityTypeOffset = -1;
let utilityCaseMovementPositionOffset = -1;

// Stable instance IDs — assigned per-class on first sight ("ClassName#N").
// Lets us discriminate multiple instances of the same utility class
// (notably ComposedUtility) without leaking opaque pointers.
const instancePerClassCounter: Map<string, number> = new Map();
const instanceIdByPtr: Map<string, string> = new Map();

function getInstanceId(p: NativePointer, className: string): string {
    if (p.isNull()) return className + "#?";
    const key = p.toString();
    const cached = instanceIdByPtr.get(key);
    if (cached) return cached;
    const next = instancePerClassCounter.get(className) ?? 0;
    instancePerClassCounter.set(className, next + 1);
    const id = className + "#" + next;
    instanceIdByPtr.set(key, id);
    return id;
}

// Call-stack tracking — pushed at MoveNext onEnter, popped at onLeave.
// Reflects the synchronous call chain of utility coroutines (Frida runs
// the hooks on the same thread as the AI).
const utilityCallStack: string[] = [];

// Per-instance event consolidation. Buffer the latest yield event per
// state-machine instance and emit only when the coroutine ends —
// collapses 2..N intermediate yields to 1 canonical (final) score.
const pendingByInstance: Map<string, Record<string, unknown>> = new Map();

// ComposedUtility introspection (one-shot dump per unique instance).
let composedUtilitiesOffset = -1;
const emittedComposedLayouts: Set<string> = new Set();
const MAX_COMPOSED_DEPTH = 5;

function dumpComposedLayoutIfNew(
    utilPtr: NativePointer, depth = 0,
): void {
    if (composedUtilitiesOffset < 0) return;
    if (utilPtr.isNull()) return;
    if (depth > MAX_COMPOSED_DEPTH) return;
    const key = utilPtr.toString();
    if (emittedComposedLayouts.has(key)) return;
    emittedComposedLayouts.add(key);
    try {
        const listPtr = utilPtr.add(composedUtilitiesOffset).readPointer();
        if (listPtr.isNull()) return;
        const items = listPtr.add(0x10).readPointer();
        const size = listPtr.add(0x18).readS32();
        if (items.isNull() || size <= 0 || size > 100) return;
        const utilities: string[] = [];
        const nested: NativePointer[] = [];
        for (let i = 0; i < size; i++) {
            const itemPtr = items.add(0x20 + i * Process.pointerSize)
                .readPointer();
            if (itemPtr.isNull()) { utilities.push("null"); continue; }
            try {
                const itemKlass = itemPtr.readPointer();
                if (itemKlass.isNull()) { utilities.push("?"); continue; }
                const cn = s(class_get_name(itemKlass) as NativePointer)
                    || "?";
                utilities.push(cn);
                if (cn === "ComposedUtility") nested.push(itemPtr);
            } catch { utilities.push("?"); }
        }
        emit({
            evt: "composed_utility_layout",
            instance: getInstanceId(utilPtr, "ComposedUtility"),
            depth,
            nestedCount: nested.length,
            utilities,
        });
        for (const sub of nested) dumpComposedLayoutIfNew(sub, depth + 1);
    } catch { /* skip */ }
}

/** Find a utility's compiler-generated `<EvaluateMovementInSteps>d__N`
 * state machine class via il2cpp_class_get_nested_types. */
function findStateMachineClass(
    utilityKlass: NativePointer, methodName: string,
): NativePointer | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    const expected = "<" + methodName + ">d__";
    let cls: NativePointer;
    while (!(cls = class_get_nested_types(
        utilityKlass, it) as NativePointer).isNull()) {
        const name = s(class_get_name(cls) as NativePointer);
        if (name && name.startsWith(expected)) return cls;
    }
    return null;
}

/** State-machine field name for the captured input parameter varies
 * across compiler versions. Try common variants in order. */
function probeCaseFieldOffset(smKlass: NativePointer): number {
    for (const n of ["case", "<case>5__1", "<case>5__2",
        "<>3__case", "<case>5__3", "movementCase"]) {
        const off = getFieldOffset(smKlass, n);
        if (off >= 0) return off;
    }
    return -1;
}

export function installL3(): void {
    const utilityMovementCaseClass = findClass(
        "BattleLogicAssembly.dll",
        "IdunBattle.AI.Utilities", "UtilityMovementCase");
    if (utilityMovementCaseClass) {
        utilityCaseUnitOffset = getFieldOffset(
            utilityMovementCaseClass, "Unit");
        utilityCaseClosestEnemyOffset = getFieldOffset(
            utilityMovementCaseClass, "ClosestEnemy");
        utilityCaseAbilityTypeOffset = getFieldOffset(
            utilityMovementCaseClass, "AbilityType");
        utilityCaseMovementPositionOffset = getFieldOffset(
            utilityMovementCaseClass, "MovementPosition");
    }

    const composedClass = findClassAnywhere(
        "IdunBattle.AI.Utilities", "ComposedUtility");
    if (composedClass) {
        composedUtilitiesOffset = getFieldOffset(composedClass, "Utilities");
    }

    let okCount = 0;
    for (const cls of L3_UTILITIES) {
        const k = findClassAnywhere("IdunBattle.AI.Utilities", cls)
               ?? findClassAnywhere("IdunBattleLogic.AI.Utilities", cls);
        if (!k) {
            installStatus["L3_" + cls] = "class_not_found";
            continue;
        }
        const sm = findStateMachineClass(k, "EvaluateMovementInSteps");
        if (!sm) {
            installStatus["L3_" + cls] = "state_machine_not_found";
            continue;
        }
        const moveNext = findMethod(sm, "MoveNext");
        if (!moveNext || moveNext.ptr.isNull()) {
            installStatus["L3_" + cls] = "movenext_not_found";
            continue;
        }
        const stateOff = getFieldOffset(sm, "<>1__state");
        const currentOff = getFieldOffset(sm, "<>2__current");
        const thisOff = getFieldOffset(sm, "<>4__this");
        const caseOff = probeCaseFieldOffset(sm);
        if (currentOff < 0) {
            installStatus["L3_" + cls] = "current_field_not_found";
            continue;
        }
        try {
            const baseUtilityName = cls;
            Interceptor.attach(moveNext.ptr, {
                onEnter(args): void {
                    const smPtr = args[0];
                    (this as { smPtr?: NativePointer }).smPtr = smPtr;
                    let rt = baseUtilityName;
                    let utilPtr: NativePointer = ptr(0);
                    if (thisOff >= 0 && !smPtr.isNull()) {
                        try {
                            utilPtr = smPtr.add(thisOff).readPointer();
                            if (!utilPtr.isNull()) {
                                const utilK = utilPtr.readPointer();
                                if (!utilK.isNull()) {
                                    const cn = class_get_name(utilK);
                                    const n = s(cn as NativePointer);
                                    if (n) rt = n;
                                }
                            }
                        } catch { /* keep base */ }
                    }
                    const instanceId = utilPtr.isNull()
                        ? rt + "#?"
                        : getInstanceId(utilPtr, rt);
                    (this as { runtimeUtility?: string }).runtimeUtility = rt;
                    (this as { instanceId?: string }).instanceId = instanceId;
                    (this as { utilPtr?: NativePointer }).utilPtr = utilPtr;
                    utilityCallStack.push(instanceId);
                },
                onLeave(retval): void {
                    // Always pop — pair with the onEnter push regardless of
                    // emit decisions below. Read parent BEFORE pop.
                    const stackLen = utilityCallStack.length;
                    const parent = stackLen >= 2
                        ? utilityCallStack[stackLen - 2] : null;
                    utilityCallStack.pop();

                    if (!traceState.enabled.L3) return;
                    const smPtr = (this as { smPtr?: NativePointer }).smPtr;
                    if (!smPtr || smPtr.isNull()) return;
                    const movenextRetTrue = retval.toInt32() !== 0;
                    let curState = -2;
                    if (stateOff >= 0) {
                        try { curState = smPtr.add(stateOff).readS32(); }
                        catch { /* keep -2 */ }
                    }

                    const score = readFix64Raw(smPtr.add(currentOff));

                    const runtimeUtility = (this as
                        { runtimeUtility?: string }).runtimeUtility
                        ?? baseUtilityName;
                    const instanceId = (this as
                        { instanceId?: string }).instanceId
                        ?? runtimeUtility + "#?";
                    const utilPtr = (this as
                        { utilPtr?: NativePointer }).utilPtr ?? ptr(0);
                    if (runtimeUtility === "ComposedUtility"
                        && !utilPtr.isNull()) {
                        dumpComposedLayoutIfNew(utilPtr);
                    }

                    let unitProj: unknown = null;
                    let enemyProj: unknown = null;
                    let caseTileProj: unknown = null;
                    let caseTileCount = -1;
                    let ability = -1;
                    if (caseOff >= 0) {
                        try {
                            const c = smPtr.add(caseOff).readPointer();
                            if (!c.isNull()) {
                                if (utilityCaseUnitOffset >= 0) {
                                    const p = c.add(utilityCaseUnitOffset)
                                        .readPointer();
                                    unitProj = projectEntity(p, "unit");
                                }
                                if (utilityCaseClosestEnemyOffset >= 0) {
                                    const p = c.add(
                                        utilityCaseClosestEnemyOffset)
                                        .readPointer();
                                    enemyProj = projectEntity(
                                        p, "closestEnemy");
                                }
                                if (utilityCaseMovementPositionOffset >= 0) {
                                    const listPtr = c.add(
                                        utilityCaseMovementPositionOffset)
                                        .readPointer();
                                    const tile = projectFirstTile(
                                        listPtr, "caseTile");
                                    caseTileProj = tile.tile;
                                    caseTileCount = tile.count;
                                }
                                if (utilityCaseAbilityTypeOffset >= 0) {
                                    const nb = c.add(
                                        utilityCaseAbilityTypeOffset);
                                    if (nb.add(4).readU8() !== 0) {
                                        ability = nb.readS32();
                                    }
                                }
                            }
                        } catch { /* skip */ }
                    }

                    const ev = traceState.currentEval;
                    const record: Record<string, unknown> = {
                        evt: "utility_score",
                        utility: instanceId,
                        baseUtility: runtimeUtility !== baseUtilityName
                            ? baseUtilityName : undefined,
                        parent,
                        playbook: ev ? ev.playbookCls : null,
                        playbookAbility: ev
                            ? abilityName(ev.abilityType) : null,
                        playbookSeq: ev ? ev.startedAt : null,
                        score,
                        unit: unitProj,
                        closestEnemy: enemyProj,
                        caseTile: caseTileProj,
                        caseTileCount,
                        ability: abilityName(ability),
                    };

                    const smKey = smPtr.toString();
                    const isYield = movenextRetTrue && curState >= 1;
                    const isEnd = !movenextRetTrue || curState <= -1;
                    if (isYield) {
                        pendingByInstance.set(smKey, record);
                    } else if (isEnd) {
                        const cached = pendingByInstance.get(smKey);
                        pendingByInstance.delete(smKey);
                        emit(cached ?? record);
                    }
                },
            });
            installStatus["L3_" + cls] = "ok";
            okCount++;
        } catch (e) {
            installStatus["L3_" + cls] = "attach_failed: "
                + (e as Error).message;
        }
    }
    installStatus.L3_okCount = String(okCount) + "/" + L3_UTILITIES.length;

    // ── #45b' : hooks ATTACK (feuilles Damage(34)) ────────────────────────────────
    // Internal d'abord (le wrapper `EvaluateAttackInSteps` délègue et double-compterait),
    // fallback sur le wrapper pour les classes sans Internal (DamageUtility, AttackTarget-
    // WithEffect, OptimizedGait, NonOwner…). Émission consolidée identique (dernier yield).
    let atkOk = 0;
    for (const cls of L3_ATTACK_UTILITIES) {
        const k = findClassAnywhere("IdunBattle.AI.Utilities", cls)
               ?? findClassAnywhere("IdunBattleLogic.AI.Utilities", cls);
        if (!k) { installStatus["L3atk_" + cls] = "class_not_found"; continue; }
        const sm = findStateMachineClass(k, "EvaluateAttackInStepsInternal")
                ?? findStateMachineClass(k, "EvaluateAttackInSteps");
        if (!sm) { installStatus["L3atk_" + cls] = "state_machine_not_found"; continue; }
        const moveNext = findMethod(sm, "MoveNext");
        if (!moveNext || moveNext.ptr.isNull()) {
            installStatus["L3atk_" + cls] = "movenext_not_found";
            continue;
        }
        const stateOff = getFieldOffset(sm, "<>1__state");
        const currentOff = getFieldOffset(sm, "<>2__current");
        const thisOff = getFieldOffset(sm, "<>4__this");
        const caseOff = probeCaseFieldOffset(sm);
        if (currentOff < 0) {
            installStatus["L3atk_" + cls] = "current_field_not_found";
            continue;
        }
        try {
            const baseUtilityName = cls;
            Interceptor.attach(moveNext.ptr, {
                onEnter(args): void {
                    const smPtr = args[0];
                    (this as { smPtr?: NativePointer }).smPtr = smPtr;
                    let rt = baseUtilityName;
                    let utilPtr: NativePointer = ptr(0);
                    if (thisOff >= 0 && !smPtr.isNull()) {
                        try {
                            utilPtr = smPtr.add(thisOff).readPointer();
                            if (!utilPtr.isNull()) {
                                const n = s(class_get_name(
                                    utilPtr.readPointer()) as NativePointer);
                                if (n) rt = n;
                            }
                        } catch { /* keep base */ }
                    }
                    const instanceId = utilPtr.isNull()
                        ? rt + "#?" : getInstanceId(utilPtr, rt);
                    (this as { runtimeUtility?: string }).runtimeUtility = rt;
                    (this as { instanceId?: string }).instanceId = instanceId;
                    utilityCallStack.push(instanceId);
                },
                onLeave(retval): void {
                    const stackLen = utilityCallStack.length;
                    const parent = stackLen >= 2
                        ? utilityCallStack[stackLen - 2] : null;
                    utilityCallStack.pop();
                    if (!traceState.enabled.L3) return;
                    const smPtr = (this as { smPtr?: NativePointer }).smPtr;
                    if (!smPtr || smPtr.isNull()) return;
                    const movenextRetTrue = retval.toInt32() !== 0;
                    let curState = -2;
                    if (stateOff >= 0) {
                        try { curState = smPtr.add(stateOff).readS32(); }
                        catch { /* keep -2 */ }
                    }
                    const score = readFix64Raw(smPtr.add(currentOff));
                    const runtimeUtility = (this as
                        { runtimeUtility?: string }).runtimeUtility
                        ?? baseUtilityName;
                    const instanceId = (this as
                        { instanceId?: string }).instanceId
                        ?? runtimeUtility + "#?";
                    // Projection ACTEUR/CIBLE de l'UtilityAttackCase (+0x10/+0x20).
                    let actorProj: unknown = null;
                    let targetProj: unknown = null;
                    if (caseOff >= 0) {
                        try {
                            const c = smPtr.add(caseOff).readPointer();
                            if (!c.isNull()) {
                                actorProj = projectEntity(
                                    c.add(ATTACK_CASE_ACTOR_OFF)
                                        .readPointer(), "unit");
                                targetProj = projectEntity(
                                    c.add(ATTACK_CASE_TARGET_OFF)
                                        .readPointer(), "target");
                            }
                        } catch { /* skip */ }
                    }
                    const ev = traceState.currentEval;
                    const record: Record<string, unknown> = {
                        evt: "utility_score",
                        mode: "attack",
                        utility: instanceId,
                        baseUtility: runtimeUtility !== baseUtilityName
                            ? baseUtilityName : undefined,
                        parent,
                        playbook: ev ? ev.playbookCls : null,
                        playbookAbility: ev
                            ? abilityName(ev.abilityType) : null,
                        score,
                        unit: actorProj,
                        target: targetProj,
                    };
                    const smKey = smPtr.toString();
                    const isYield = movenextRetTrue && curState >= 1;
                    const isEnd = !movenextRetTrue || curState <= -1;
                    if (isYield) {
                        pendingByInstance.set(smKey, record);
                    } else if (isEnd) {
                        const cached = pendingByInstance.get(smKey);
                        pendingByInstance.delete(smKey);
                        emit(cached ?? record);
                    }
                },
            });
            installStatus["L3atk_" + cls] = "ok";
            atkOk++;
        } catch (e) {
            installStatus["L3atk_" + cls] = "attach_failed: "
                + (e as Error).message;
        }
    }
    installStatus.L3atk_okCount = String(atkOk) + "/"
        + L3_ATTACK_UTILITIES.length;
}
