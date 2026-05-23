import { findClassAnywhere, readIl2cppString } from "../../il2cpp/helpers.js";
import { state } from "../../game/state.js";
import { runnerOff } from "../../game/runner.js";
import { forEachEntity } from "../../game/match-state.js";
import { log } from "../../runtime/diag.js";

// Diamond 3 (D3) / Blue Wing / Level 50 baseline calibration table for typical reinforcement learning units
const D3_BASELINES: Record<string, { hp: number, damage: number, armor: number }> = {
    // Ultramarines (Space Marines)
    "ultraTigurius": { hp: 5800, damage: 1650, armor: 540 },
    "ultraBellator": { hp: 7200, damage: 1200, armor: 980 },
    "ultraCertus": { hp: 4900, damage: 1980, armor: 410 },
    
    // Necrons
    "necronsAleph": { hp: 5200, damage: 1350, armor: 620 },
    "necronsImospek": { hp: 6100, damage: 1540, armor: 780 },
    "necronsMakhotep": { hp: 5500, damage: 1280, armor: 690 },
    "necronsAnuphet": { hp: 6500, damage: 1420, armor: 850 },
    
    // Default baseline for campaign enemies or uncalibrated units (keeps battle balanced)
    "default": { hp: 4500, damage: 1100, armor: 400 }
};

/** 
 * Force all active units in the MatchState to Diamond 3 / Blue Wing / Level 50 stats.
 * This establishes a uniform baseline for reinforcement learning (RL) training safely.
 */
export function normalizeUnits(force: boolean = false) {
    if (!state.liveRunner) {
        log("[normalizer] state.liveRunner is null! Cannot normalize outside of an active battle.");
        return { ok: false, msg: "No active battle runner found" };
    }
    
    const matchState = state.liveRunner.add(runnerOff.state).readPointer();
    if (matchState.isNull()) {
        log("[normalizer] MatchState is null!");
        return { ok: false, msg: "MatchState is null" };
    }
    
    log("[normalizer] Starting unit statistics normalization to Diamond 3 (D3)...");
    
    let normalizedCount = 0;
    
    forEachEntity(matchState, (entityPtr, id, type) => {
        if (type !== 1) return; // Only process Units
        
        // 1. Resolve unit visualId to identify the unit
        const unitComp = entityPtr.add(0x28).readPointer();
        if (unitComp.isNull()) return;
        
        const visualIdPtr = unitComp.add(0x20).readPointer();
        const visualId = visualIdPtr.isNull() ? null : readIl2cppString(visualIdPtr);
        const nameKey = visualId ?? "default";
        
        // Determine calibration stats (D3)
        const baseline = D3_BASELINES[nameKey] || D3_BASELINES["default"];
        
        log(`[normalizer] Calibrating Unit ID=${id} (${nameKey}) to D3 baseline: HP=${baseline.hp}, Armor=${baseline.armor}, Damage=${baseline.damage}`);
        
        // 2. Resolve components
        const healthComp = entityPtr.add(0x58).readPointer();
        const armorComp = entityPtr.add(0x60).readPointer();
        const attackComp = entityPtr.add(0x38).readPointer();
        
        // 3. Write D3 Stats safely into their respective components
        
        // Health component (FillUpStatComponent):
        // +0x10 -> InitialValue (Int32)
        // +0x14 -> MaximumValue (Int32)
        // +0x18 -> RemainingValue (Int32) (also fully heals the unit to avoid instant death)
        if (!healthComp.isNull()) {
            healthComp.add(0x10).writeS32(baseline.hp);
            healthComp.add(0x14).writeS32(baseline.hp);
            healthComp.add(0x18).writeS32(baseline.hp);
        }
        
        // Armor component (StatComponent):
        // +0x48 -> InitialValue (Int32)
        if (!armorComp.isNull()) {
            armorComp.add(0x48).writeS32(baseline.armor);
        }
        
        // Attack component (StatComponent):
        // +0x48 -> InitialValue (Int32)
        if (!attackComp.isNull()) {
            attackComp.add(0x48).writeS32(baseline.damage);
        }
        
        normalizedCount++;
    });
    
    log(`[normalizer] Successfully normalized ${normalizedCount} active units to D3 stats.`);
    return { ok: true, msg: `Normalized ${normalizedCount} units successfully` };
}
