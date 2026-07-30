// Damage / heal / repair / armor predictions on the `DamagePrediction`
// service. Captures the AI's expected impact magnitudes for melee
// (PredictNormalAttack), abilities (PredictAttack × 2 overloads), heals
// (PredictHeal), repairs (PredictRepair), and armor restores
// (PredictArmorRestore).
//
// Win64 ABI for return values:
//   ≤ 8 bytes: returned in RAX (Frida `retval` is the 64-bit value)
//   > 8 bytes: returned via sret pointer in args[0]
//
// PredictStealStat is intentionally skipped — its 24-byte return holds a
// nested Dictionary<IEntity,...> not worth decoding for the rare drain
// abilities.

import { findClass, findMethod } from "../../il2cpp/helpers.js";
import { abilityName } from "../../data/ability-names.js";
import {
    traceState, installStatus,
    emit, projectEntity,
    readDamagePredictionAt, readAbilityOrEffect,
    splitU64, enumerateMethodsByName,
} from "./state.js";

interface CarriedPtrs {
    sretPtr?: NativePointer;
    casterPtr?: NativePointer;
    targetPtr?: NativePointer;
    attackerPtr?: NativePointer;
    defenderPtr?: NativePointer;
    reqPtr?: NativePointer;
    amount?: number;
}

export function installDamagePredictionHook(): void {
    const dpClass = findClass(
        "BattleLogicAssembly.dll",
        "IdunBattle.Core.Services", "DamagePrediction");
    if (!dpClass) {
        installStatus.PredictNormalAttack = "DamagePrediction class not found";
        return;
    }

    // PredictNormalAttack(IEntity attacker, UnitPosition pos, IEntity defender)
    //   → DamagePredictionResult (>16B sret).
    // args[0]=sret, args[1]=this, args[2]=attacker, args[3]=Tiles ptr,
    // args[4]=defender.
    const m = findMethod(dpClass, "PredictNormalAttack");
    if (!m || m.ptr.isNull()) {
        installStatus.PredictNormalAttack = "method not found";
    } else {
        try {
            Interceptor.attach(m.ptr, {
                onEnter(args): void {
                    const c = this as CarriedPtrs;
                    c.sretPtr = args[0];
                    c.attackerPtr = args[2];
                    c.defenderPtr = args[4];
                },
                onLeave(_retval): void {
                    if (!traceState.enabled.L1) return;
                    const c = this as CarriedPtrs;
                    if (!c.sretPtr || c.sretPtr.isNull()) return;
                    const prediction = readDamagePredictionAt(c.sretPtr);
                    const ev = traceState.currentEval;
                    emit({
                        evt: "damage_prediction",
                        source: "normal_attack",
                        attacker: projectEntity(
                            c.attackerPtr ?? ptr(0), "unit"),
                        defender: projectEntity(
                            c.defenderPtr ?? ptr(0), "unit"),
                        prediction,
                        playbook: ev ? ev.playbookCls : null,
                        playbookAbility: ev
                            ? abilityName(ev.abilityType) : null,
                    });
                },
            });
            installStatus.PredictNormalAttack = "ok";
        } catch (e) {
            installStatus.PredictNormalAttack = "attach_failed: "
                + (e as Error).message;
        }
    }

    // PredictAttack overloads — covers ability-driven damage. Both
    // overloads (Slot 9: simple, Slot 10: with callbacks) share the
    // first 3 arg layout: args[0]=sret, args[1]=this, args[2]=&request.
    //
    // AttackPredictionRequest layout:
    //   +0x00  TriggeringAbilityOrEffect: Nullable<AbilityOrEffect> (28B)
    //   +0x1C  CurrentAbilityOrEffect:    Nullable<AbilityOrEffect> (28B)
    //   +0x38  Attacker: IEntity*
    //   +0x40  AttackerPosition: Nullable<UnitPosition> (16B)
    //   +0x50  Defender: IEntity*
    let predictAttackCount = 0;
    for (const pa of enumerateMethodsByName(dpClass, "PredictAttack")) {
        try {
            Interceptor.attach(pa.ptr, {
                onEnter(args): void {
                    const c = this as CarriedPtrs;
                    c.sretPtr = args[0];
                    c.reqPtr = args[2];
                },
                onLeave(_retval): void {
                    if (!traceState.enabled.L1) return;
                    const c = this as CarriedPtrs;
                    if (!c.sretPtr || c.sretPtr.isNull()) return;
                    if (!c.reqPtr || c.reqPtr.isNull()) return;
                    const prediction = readDamagePredictionAt(c.sretPtr);
                    let attackerPtr: NativePointer = ptr(0);
                    let defenderPtr: NativePointer = ptr(0);
                    let abilityInfo: Record<string, unknown> | null = null;
                    try {
                        attackerPtr = c.reqPtr.add(0x38).readPointer();
                        defenderPtr = c.reqPtr.add(0x50).readPointer();
                        if (c.reqPtr.add(0x1C).readU8() !== 0) {
                            abilityInfo = readAbilityOrEffect(
                                c.reqPtr.add(0x20));
                        }
                        // Fallback: if Current is None, try TriggeringAbility
                        // at +0x0 — fires when prediction is for a chained
                        // triggered hit (e.g., Overwatch reaction).
                        if (!abilityInfo
                            && c.reqPtr.add(0x0).readU8() !== 0) {
                            abilityInfo = readAbilityOrEffect(
                                c.reqPtr.add(0x4));
                            if (abilityInfo) {
                                (abilityInfo as Record<string, unknown>)
                                    ._role = "triggering";
                            }
                        }
                    } catch { /* keep defaults */ }
                    const ev = traceState.currentEval;
                    emit({
                        evt: "damage_prediction",
                        source: "ability",
                        ability: abilityInfo,
                        attacker: projectEntity(attackerPtr, "unit"),
                        defender: projectEntity(defenderPtr, "unit"),
                        prediction,
                        playbook: ev ? ev.playbookCls : null,
                        playbookAbility: ev
                            ? abilityName(ev.abilityType) : null,
                    });
                },
            });
            predictAttackCount++;
        } catch (e) {
            installStatus["PredictAttack#" + predictAttackCount]
                = "attach_failed: " + (e as Error).message;
        }
    }
    installStatus.PredictAttack = predictAttackCount + " overloads";
}

export function installHealRepairHooks(): void {
    const dpClass = findClass(
        "BattleLogicAssembly.dll",
        "IdunBattle.Core.Services", "DamagePrediction");
    if (!dpClass) {
        installStatus.HealRepairHooks = "DamagePrediction class not found";
        return;
    }

    // PredictHeal(IEntity caster, IEntity casterTile, IEntity target,
    //             int amount, HealScope scope) → 8B in RAX.
    const ph = findMethod(dpClass, "PredictHeal");
    if (ph && !ph.ptr.isNull()) {
        try {
            Interceptor.attach(ph.ptr, {
                onEnter(args): void {
                    const c = this as CarriedPtrs;
                    c.casterPtr = args[1];
                    c.targetPtr = args[3];
                    c.amount = args[4].toInt32();
                },
                onLeave(retval): void {
                    if (!traceState.enabled.L1) return;
                    const c = this as CarriedPtrs;
                    const { lo, hi } = splitU64(retval);
                    const ev = traceState.currentEval;
                    emit({
                        evt: "heal_prediction",
                        caster: projectEntity(
                            c.casterPtr ?? ptr(0), "caster"),
                        target: projectEntity(
                            c.targetPtr ?? ptr(0), "target"),
                        amount: c.amount,
                        prediction: { currentHealth: lo, totalHeal: hi },
                        playbook: ev ? ev.playbookCls : null,
                        playbookAbility: ev
                            ? abilityName(ev.abilityType) : null,
                    });
                },
            });
            installStatus.PredictHeal = "ok";
        } catch (e) {
            installStatus.PredictHeal = "attach_failed: "
                + (e as Error).message;
        }
    } else {
        installStatus.PredictHeal = "method not found";
    }

    // PredictRepair(caster, target, casterPosition, amount, scope, source)
    //   → RepairPredictionResult, 8 octets DANS RAX (pas de sret).
    //
    // ⚠ CE CANAL A ETE FAUX SUR TOUT, ET SILENCIEUSEMENT — corrige le 2026-07-30 (#278).
    // Le code precedent supposait un retour par `sret`, ce qui decale d'un cran TOUS les
    // arguments. Il publiait donc :
    //     args[0] pris pour le sret     -> c'est `this` : la prediction etait decodee
    //                                      depuis l'objet service lui-meme
    //     args[2] pris pour le caster   -> c'est la CIBLE
    //     args[3] pris pour la cible    -> c'est `casterPosition`, une VALEUR (UnitPosition),
    //                                      pas une entite
    //     args[5] pris pour le montant  -> c'est `scope`, un enum a petite valeur -- donc
    //                                      parfaitement plausible a l'oeil
    // Aucune de ces erreurs ne pouvait se voir dans les traces : tout restait « du bon
    // ordre de grandeur ». C'est la signature du decodage faux, pas du bug bruyant.
    //
    // CE QUI TRANCHE, et pourquoi c'est sur cette fois :
    //   1. `classFields` (RPC live) : `RepairPredictionResult` = 8 octets de champs,
    //      `CurrentHealth` puis `TotalHeal` -- STRICTEMENT la meme forme que
    //      `HealPredictionResult`. Meme taille => meme ABI de retour.
    //   2. Le decompile donne `undefined8 PredictRepair(this, caster, target,
    //      casterPosition, amount, scope, source)` -- retour en RAX, aucun sret -- et
    //      finit par `CONCAT44(MaxFillUp(...), GetStat(target, Health))`, soit
    //      lo = CurrentHealth, hi = TotalHeal. Exactement `PredictHeal` ci-dessus.
    //
    // Il n'y a donc PLUS d'offset a maintenir ici : deux int32 dans un registre. Le piege
    // de taille boxee (#276) ne peut plus mordre sur ce canal.
    const pr = findMethod(dpClass, "PredictRepair");
    if (pr && !pr.ptr.isNull()) {
        try {
            Interceptor.attach(pr.ptr, {
                onEnter(args): void {
                    const c = this as CarriedPtrs;
                    c.casterPtr = args[1];
                    c.targetPtr = args[2];
                    // args[3] = casterPosition (UnitPosition, par valeur) — non trace.
                    c.amount = args[4].toInt32();
                },
                onLeave(retval): void {
                    if (!traceState.enabled.L1) return;
                    const c = this as CarriedPtrs;
                    const { lo, hi } = splitU64(retval);
                    const ev = traceState.currentEval;
                    emit({
                        evt: "repair_prediction",
                        caster: projectEntity(
                            c.casterPtr ?? ptr(0), "caster"),
                        target: projectEntity(
                            c.targetPtr ?? ptr(0), "target"),
                        amount: c.amount,
                        prediction: { currentHealth: lo, totalHeal: hi },
                        playbook: ev ? ev.playbookCls : null,
                        playbookAbility: ev
                            ? abilityName(ev.abilityType) : null,
                    });
                },
            });
            installStatus.PredictRepair = "ok";
        } catch (e) {
            installStatus.PredictRepair = "attach_failed: "
                + (e as Error).message;
        }
    } else {
        installStatus.PredictRepair = "method not found";
    }

    // PredictArmorRestore(IEntity caster, IEntity target, int amount)
    //   → ArmorRestorePredictionResult (8B in RAX).
    const par = findMethod(dpClass, "PredictArmorRestore");
    if (par && !par.ptr.isNull()) {
        try {
            Interceptor.attach(par.ptr, {
                onEnter(args): void {
                    const c = this as CarriedPtrs;
                    c.casterPtr = args[1];
                    c.targetPtr = args[2];
                    c.amount = args[3].toInt32();
                },
                onLeave(retval): void {
                    if (!traceState.enabled.L1) return;
                    const c = this as CarriedPtrs;
                    const { lo, hi } = splitU64(retval);
                    const ev = traceState.currentEval;
                    emit({
                        evt: "armor_prediction",
                        caster: projectEntity(
                            c.casterPtr ?? ptr(0), "caster"),
                        target: projectEntity(
                            c.targetPtr ?? ptr(0), "target"),
                        amount: c.amount,
                        prediction: { currentArmor: lo, totalArmorRepair: hi },
                        playbook: ev ? ev.playbookCls : null,
                        playbookAbility: ev
                            ? abilityName(ev.abilityType) : null,
                    });
                },
            });
            installStatus.PredictArmorRestore = "ok";
        } catch (e) {
            installStatus.PredictArmorRestore = "attach_failed: "
                + (e as Error).message;
        }
    } else {
        installStatus.PredictArmorRestore = "method not found";
    }
}
