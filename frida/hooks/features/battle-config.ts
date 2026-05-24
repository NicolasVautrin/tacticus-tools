// Live BattleConfiguration inspection + (eventually) mutation.
//
// BattleConfiguration is the per-battle config stitched by
// CampaignGameModeSource.LoadBattle() and stored at _currentBattle (+0x80).
// We read from the warmup-captured campaignGameModeSourcePtr — so any inspection RPC requires
// a successful warmup first.
//
// Layout reference (from decompilation):
//   BattleConfiguration                     class
//     +0x10  Id                             string
//     +0x28  SpawnPointSetIndex             int
//     +0x30  Player                         PlayersConfiguration
//     +0x40  PredefinedUnits                List<PredefinedUnits>
//     +0x68  Board                          BattleConfigBoardConfiguration
//     +0x80  Units                          List<UnitConfiguration>  (templates)
//     +0x88  Tiles                          List<BattleConfigTileConfiguration> (palette)
//     +0xE7  RandomizeAiInput               bool
//
//   PredefinedUnits (per-player squad)      class
//     +0x10  Id                             PlayerId (enum int)
//     +0x18  Units                          List<PredefinedUnit>
//
//   PredefinedUnit                          class
//     +0x10  UnitId                         string
//     +0x18  RemainingHealth                Nullable<int>
//     +0x20  MaxHealth                      Nullable<int>
//
//   UnitConfiguration (template)            class
//     +0x10  Id                             string
//     +0x18  VisualId                       string
//     +0x28  Faction                        string
//     +0x38  Health                         int
//
//   BattleConfigBoardConfiguration          class
//     +0x10  Id                             string
//     +0x18  Width                          int
//     +0x1C  Height                         int
//
//   System.Collections.Generic.List<T>      class (IL2CPP)
//     +0x10  _items                         T[]  (Il2CppArray: len at +0x18, data at +0x20)
//     +0x18  _size                          int

import {
    readIl2cppString, findClassAnywhere, findMethod, class_get_methods,
    method_get_name, method_get_param_count, methodEntry, s as cstr, MethodRef,
} from "../il2cpp/helpers.js";
import { createManagedString } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { getCampaignGameModeSourcePtr } from "./campaign-builder.js";
import { buildRunner, runnerApplyMi } from "../game/runner.js";
import { registerRunner, getRunner as getRegistryRunner }
    from "../game/runner-registry.js";
import { findClass, findCtorByParamCount } from "../il2cpp/helpers.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

// --- Offsets ---

const CGMS_OFF_CURRENT_BATTLE = 0x80;

const BC_OFF_ID = 0x10;
const BC_OFF_SPAWN_POINT_SET_INDEX = 0x28;
const BC_OFF_PREDEFINED_UNITS = 0x40;
const BC_OFF_BOARD = 0x68;
const BC_OFF_UNITS = 0x80;       // List<UnitConfiguration>
const BC_OFF_TILES = 0x88;       // List<BattleConfigTileConfiguration>
const BC_OFF_RANDOMIZE_AI = 0xE7;

const LIST_OFF_ITEMS = 0x10;
const LIST_OFF_SIZE = 0x18;

const ARRAY_OFF_LEN = 0x18;
const ARRAY_OFF_DATA = 0x20;

const PU_OFF_ID = 0x10;
const PU_OFF_UNITS = 0x18;

const PUNIT_OFF_UNIT_ID = 0x10;
const PUNIT_OFF_REMAINING_HP = 0x18; // Nullable<int>: {hasValue@0x10?, value@0x14?} — confirm at runtime
const PUNIT_OFF_MAX_HP = 0x20;

const UC_OFF_ID = 0x10;
const UC_OFF_VISUAL_ID = 0x18;
const UC_OFF_FACTION = 0x28;
const UC_OFF_HEALTH = 0x38;
const UC_OFF_DAMAGE = 0x50;

const BCBC_OFF_ID = 0x10;        // Board.Id (also at +0x10 on master BoardConfiguration but with different base)
const BCBC_OFF_WIDTH = 0x18;
const BCBC_OFF_HEIGHT = 0x1C;

// --- Helpers ---

/** Resolve the live BattleConfiguration from the warmup-captured campaignGameModeSourcePtr.
 * Null if no source captured, or if source captured but LoadBattle hasn't fired
 * yet (very brief window — _currentBattle is set by LoadBattle return). */
function getLiveBattleConfig(): NativePointer | null {
    const src = getCampaignGameModeSourcePtr();
    if (src === null) return null;
    try {
        const bc = src.add(CGMS_OFF_CURRENT_BATTLE).readPointer();
        return bc.isNull() ? null : bc;
    } catch { return null; }
}

/** Read a managed `List<T>` of reference-type elements. Returns the raw
 * Il2CppArray pointer + element count. Element i lives at `arrayPtr + 0x20 + i*8`
 * (already-typed reference). Returns null if the list itself is null. */
function readManagedList(
    listPtr: NativePointer,
): { array: NativePointer; size: number } | null {
    if (listPtr.isNull()) return null;
    try {
        const items = listPtr.add(LIST_OFF_ITEMS).readPointer();
        const size = listPtr.add(LIST_OFF_SIZE).readS32();
        if (items.isNull() || size < 0 || size > 10000) return null;
        return { array: items, size };
    } catch { return null; }
}

function readListItem(
    listInfo: { array: NativePointer; size: number }, i: number,
): NativePointer {
    return listInfo.array.add(ARRAY_OFF_DATA + i * Process.pointerSize)
        .readPointer();
}

// --- Inspection RPC ---

interface BattleConfigSnapshot {
    ok: boolean;
    bcPtr?: string;
    id?: string | null;
    spawnPointSetIndex?: number;
    randomizeAiInput?: boolean;
    board?: {
        ptr: string;
        id: string | null;
        width: number;
        height: number;
    };
    palette?: { tileTypeCount: number };
    templates?: {
        unitTemplateCount: number;
        sample: Array<{ id: string | null; visualId: string | null;
                        faction: string | null; health: number }>;
    };
    predefinedUnits?: Array<{
        playerId: number;
        unitCount: number;
        units: Array<{ unitId: string | null }>;
    }>;
    err?: string;
}

function inspectBattleConfig(): BattleConfigSnapshot {
    const bc = getLiveBattleConfig();
    if (bc === null) {
        return {
            ok: false,
            err: "no live BattleConfiguration — warmup not run OR " +
                 "LoadBattle hasn't fired yet (warmup retreats too early?)",
        };
    }

    const snap: BattleConfigSnapshot = { ok: true, bcPtr: bc.toString() };

    try {
        snap.id = readIl2cppString(bc.add(BC_OFF_ID).readPointer());
        snap.spawnPointSetIndex = bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).readS32();
        snap.randomizeAiInput = bc.add(BC_OFF_RANDOMIZE_AI).readU8() !== 0;
    } catch (e) {
        snap.err = `header read: ${(e as Error).message}`;
    }

    // Board
    try {
        const board = bc.add(BC_OFF_BOARD).readPointer();
        if (!board.isNull()) {
            snap.board = {
                ptr: board.toString(),
                id: readIl2cppString(board.add(BCBC_OFF_ID).readPointer()),
                width: board.add(BCBC_OFF_WIDTH).readS32(),
                height: board.add(BCBC_OFF_HEIGHT).readS32(),
            };
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | board: ${(e as Error).message}`;
    }

    // Tiles palette
    try {
        const tiles = readManagedList(bc.add(BC_OFF_TILES).readPointer());
        if (tiles) snap.palette = { tileTypeCount: tiles.size };
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | tiles: ${(e as Error).message}`;
    }

    // Unit templates (with a small sample to verify offsets)
    try {
        const units = readManagedList(bc.add(BC_OFF_UNITS).readPointer());
        if (units) {
            const sample = [];
            const N = Math.min(units.size, 5);
            for (let i = 0; i < N; i++) {
                const uc = readListItem(units, i);
                if (uc.isNull()) continue;
                sample.push({
                    id: readIl2cppString(uc.add(UC_OFF_ID).readPointer()),
                    visualId: readIl2cppString(
                        uc.add(UC_OFF_VISUAL_ID).readPointer()),
                    faction: readIl2cppString(
                        uc.add(UC_OFF_FACTION).readPointer()),
                    health: uc.add(UC_OFF_HEALTH).readS32(),
                });
            }
            snap.templates = {
                unitTemplateCount: units.size,
                sample,
            };
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | templates: ${(e as Error).message}`;
    }

    // PredefinedUnits (composition per player)
    try {
        const pu = readManagedList(bc.add(BC_OFF_PREDEFINED_UNITS).readPointer());
        if (pu) {
            const players: BattleConfigSnapshot["predefinedUnits"] = [];
            for (let i = 0; i < pu.size; i++) {
                const grp = readListItem(pu, i);
                if (grp.isNull()) continue;
                const playerId = grp.add(PU_OFF_ID).readS32();
                const unitsList = readManagedList(
                    grp.add(PU_OFF_UNITS).readPointer());
                const units: Array<{ unitId: string | null }> = [];
                if (unitsList) {
                    for (let j = 0; j < unitsList.size; j++) {
                        const pUnit = readListItem(unitsList, j);
                        if (pUnit.isNull()) continue;
                        units.push({
                            unitId: readIl2cppString(
                                pUnit.add(PUNIT_OFF_UNIT_ID).readPointer()),
                        });
                    }
                }
                players.push({
                    playerId,
                    unitCount: unitsList?.size ?? 0,
                    units,
                });
            }
            snap.predefinedUnits = players;
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | predef: ${(e as Error).message}`;
    }

    return snap;
}

// --- Patch / mutation API ---
//
// A `BattleConfigPatch` describes a set of in-place mutations to apply to
// the next BattleConfiguration assembled by LoadBattle. Stored in module
// state via `setBattleConfigPatch`; applied automatically by the
// LoadBattle.onLeave hook on CampaignGameModeSource. `consumeOnce` (default
// true) auto-clears the patch after a single application so a subsequent
// human-driven battle isn't accidentally affected.

interface UnitStatsOverride {
    health?: number;
    damage?: number;
    armor?: number;        // legacy Armor field (Idun)
    fixedArmor?: number;
    shield?: number;
    movement?: number;
    range?: number;
    critChance?: number;
    critDamage?: number;
    blockChance?: number;
    blockDamage?: number;
}

interface BattleConfigPatch {
    /** Replace all AI units (PredefinedUnits[0].Units). Must match current
     * count — list resizing not implemented yet. Format: "unitId:level"
     * e.g., "necroNpc1Warrior:6". */
    aiUnits?: string[];
    /** Or: replace specific AI unit slots by index. Same format as aiUnits. */
    aiUnitsAt?: Record<number, string>;
    /** Override stats on unit templates by their Id. Affects ALL spawned
     * instances of that unit. Useful for normalizing power level (RL D3 baseline). */
    templateOverrides?: Record<string, UnitStatsOverride>;
    /** Toggle the BattleConfiguration.RandomizeAiInput flag. */
    randomizeAi?: boolean;
    /** Set the spawn-point preset index (each board has 1-N presets). */
    spawnPointSetIndex?: number;
    /** If true (default), the patch is cleared after a single application. */
    consumeOnce?: boolean;
}

interface PatchApplyResult {
    ok: boolean;
    appliedAt: string;            // ISO timestamp
    bcPtr: string;
    operations: string[];         // human-readable log of what was changed
    warnings: string[];
}

let pendingPatch: BattleConfigPatch | null = null;
let lastApply: PatchApplyResult | null = null;

// Extra UnitConfiguration offsets used only by patch (read-only ones are
// already declared above for inspectBattleConfig).
const UC_OFF_ARMOR = 0x44;       // legacy Armor (Idun-only, Obsolete)
const UC_OFF_FIXED_ARMOR = 0x48;
const UC_OFF_SHIELD = 0x4C;
const UC_OFF_MOVEMENT = 0x54;
const UC_OFF_RANGE = 0x5C;
const UC_OFF_CRIT_CHANCE = 0x60;
const UC_OFF_CRIT_DAMAGE = 0x64;
const UC_OFF_BLOCK_CHANCE = 0x68;
const UC_OFF_BLOCK_DAMAGE = 0x6C;

function applyPatchToConfig(
    bc: NativePointer, patch: BattleConfigPatch,
): PatchApplyResult {
    const ops: string[] = [];
    const warnings: string[] = [];

    // Toggle randomize AI
    if (patch.randomizeAi !== undefined) {
        try {
            bc.add(BC_OFF_RANDOMIZE_AI).writeU8(patch.randomizeAi ? 1 : 0);
            ops.push(`randomizeAi=${patch.randomizeAi}`);
        } catch (e) {
            warnings.push(`randomizeAi: ${(e as Error).message}`);
        }
    }

    // SpawnPointSetIndex
    if (patch.spawnPointSetIndex !== undefined) {
        try {
            bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).writeS32(
                patch.spawnPointSetIndex);
            ops.push(`spawnPointSetIndex=${patch.spawnPointSetIndex}`);
        } catch (e) {
            warnings.push(
                `spawnPointSetIndex: ${(e as Error).message}`);
        }
    }

    // Index template by Id, for both AI unit validation and stat overrides.
    const templates = readManagedList(bc.add(BC_OFF_UNITS).readPointer());
    const templatesById = new Map<string, NativePointer>();
    if (templates) {
        for (let i = 0; i < templates.size; i++) {
            const uc = readListItem(templates, i);
            if (uc.isNull()) continue;
            const id = readIl2cppString(uc.add(UC_OFF_ID).readPointer());
            if (id) templatesById.set(id, uc);
        }
    }

    // AI unit swap
    const wantedAiUnits = mergeAiUnitsSpec(patch);
    if (wantedAiUnits !== null) {
        const pu = readManagedList(
            bc.add(BC_OFF_PREDEFINED_UNITS).readPointer());
        if (!pu || pu.size < 1) {
            warnings.push("aiUnits: PredefinedUnits list empty");
        } else {
            // First entry assumed to be the AI player (validated by
            // inspectBattleConfig observation: single group, playerId=12).
            const aiGroup = readListItem(pu, 0);
            const aiUnits = readManagedList(
                aiGroup.add(PU_OFF_UNITS).readPointer());
            if (!aiUnits) {
                warnings.push("aiUnits: AI group's Units list null");
            } else if (wantedAiUnits.length !== aiUnits.size) {
                warnings.push(
                    `aiUnits: count mismatch — spec wants ` +
                    `${wantedAiUnits.length}, current has ${aiUnits.size}. ` +
                    `List resize not implemented; keeping original.`);
            } else {
                // No template validation here — BattleConfiguration.Units
                // holds the PLAYER roster, not AI enemies. AI unit IDs are
                // resolved at spawn time against a global registry (likely
                // GameConfigData). We just write the strings and let the
                // game complain if an ID is genuinely invalid.
                for (let i = 0; i < wantedAiUnits.length; i++) {
                    const pUnit = readListItem(aiUnits, i);
                    if (pUnit.isNull()) continue;
                    const newStr = createManagedString(wantedAiUnits[i]);
                    pUnit.add(PUNIT_OFF_UNIT_ID).writePointer(newStr);
                }
                ops.push(`aiUnits=${wantedAiUnits.length} slots replaced`);
            }
        }
    }

    // Template stat overrides
    if (patch.templateOverrides) {
        for (const [unitId, stats] of Object.entries(patch.templateOverrides)) {
            const uc = templatesById.get(unitId);
            if (!uc) {
                warnings.push(`templateOverrides: unknown unit ${unitId}`);
                continue;
            }
            const changed: string[] = [];
            try {
                if (stats.health !== undefined) {
                    uc.add(UC_OFF_HEALTH).writeS32(stats.health);
                    changed.push(`hp=${stats.health}`);
                }
                if (stats.damage !== undefined) {
                    uc.add(UC_OFF_DAMAGE).writeS32(stats.damage);
                    changed.push(`dmg=${stats.damage}`);
                }
                if (stats.armor !== undefined) {
                    uc.add(UC_OFF_ARMOR).writeS32(stats.armor);
                    changed.push(`armor=${stats.armor}`);
                }
                if (stats.fixedArmor !== undefined) {
                    uc.add(UC_OFF_FIXED_ARMOR).writeS32(stats.fixedArmor);
                    changed.push(`fixedArmor=${stats.fixedArmor}`);
                }
                if (stats.shield !== undefined) {
                    uc.add(UC_OFF_SHIELD).writeS32(stats.shield);
                    changed.push(`shield=${stats.shield}`);
                }
                if (stats.movement !== undefined) {
                    uc.add(UC_OFF_MOVEMENT).writeS32(stats.movement);
                    changed.push(`mv=${stats.movement}`);
                }
                if (stats.range !== undefined) {
                    uc.add(UC_OFF_RANGE).writeS32(stats.range);
                    changed.push(`range=${stats.range}`);
                }
                if (stats.critChance !== undefined) {
                    uc.add(UC_OFF_CRIT_CHANCE).writeS32(stats.critChance);
                    changed.push(`crit%=${stats.critChance}`);
                }
                if (stats.critDamage !== undefined) {
                    uc.add(UC_OFF_CRIT_DAMAGE).writeS32(stats.critDamage);
                    changed.push(`critDmg=${stats.critDamage}`);
                }
                if (stats.blockChance !== undefined) {
                    uc.add(UC_OFF_BLOCK_CHANCE).writeS32(stats.blockChance);
                    changed.push(`block%=${stats.blockChance}`);
                }
                if (stats.blockDamage !== undefined) {
                    uc.add(UC_OFF_BLOCK_DAMAGE).writeS32(stats.blockDamage);
                    changed.push(`blockDmg=${stats.blockDamage}`);
                }
            } catch (e) {
                warnings.push(
                    `templateOverrides ${unitId}: ${(e as Error).message}`);
                continue;
            }
            ops.push(`${unitId}{${changed.join(",")}}`);
        }
    }

    return {
        ok: warnings.length === 0,
        appliedAt: new Date().toISOString(),
        bcPtr: bc.toString(),
        operations: ops,
        warnings,
    };
}

function mergeAiUnitsSpec(patch: BattleConfigPatch): string[] | null {
    if (patch.aiUnits) return patch.aiUnits.slice();
    if (patch.aiUnitsAt) {
        // Need to know current count; we'll merge against existing inside the
        // application logic. Return null here; caller handles the partial case
        // via a separate path. Simpler approach: caller resolves aiUnitsAt
        // into a full-length array using inspectBattleConfig data — but for
        // now treat partial as not supported in v1 of the patch API.
        // TODO: handle partial slot replacement
        return null;
    }
    return null;
}

// --- Spawn helper: materialize PredefinedUnits into runner via AddUnitMessage ---
//
// buildRunner gives us a SKELETON (tiles + match + players) but no Unit
// entities. We need to apply AddUnitMessage(unitId, playerId, col, row) for
// each PredefinedUnit, using the SpawnPointGroup matching the player's team.
//
// Layout reminders:
//   BattleConfiguration.Board.SpawnPointSets : List<SpawnPointSetConfiguration>
//   SpawnPointSetConfiguration.SpawnPointGroups : List<SpawnPointGroupConfiguration>
//   SpawnPointGroupConfiguration:
//     +0x10  TeamWithPlayerIndex (int)
//     +0x14  MachineOfWarPosition
//     +0x18  SpawnPoints : List<SpawnPointConfiguration>
//   SpawnPointConfiguration : BattleConfigPosition
//     +0x10  Column
//     +0x14  Row
//   AddUnitMessage (4-arg ctor): (string unitId, PlayerId, int col, int row)
//     +0x28  SpawnSource (set to Deployment=5 per launch.ts)

const BCBC_OFF_SPAWN_POINT_SETS = 0x28; // BattleConfigBoardConfiguration
const SPS_OFF_SPAWN_GROUPS = 0x10;      // SpawnPointSetConfiguration
const SPG_OFF_TEAM_PLAYER_INDEX = 0x10; // SpawnPointGroupConfiguration
const SPG_OFF_SPAWN_POINTS = 0x18;
const SP_OFF_COL = 0x10;
const SP_OFF_ROW = 0x14;

const addUnitMsgClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Messages", "AddUnitMessage");
const addUnitMsgCtor4 = addUnitMsgClass
    ? findCtorByParamCount(addUnitMsgClass, 4) : null;

function buildAddUnitMessage(
    unitId: string, playerId: number, col: number, row: number,
): NativePointer {
    if (!addUnitMsgClass) throw new Error("AddUnitMessage class not found");
    if (!addUnitMsgCtor4) throw new Error("AddUnitMessage 4-arg ctor not found");
    const msg = il2cpp_object_new(addUnitMsgClass) as NativePointer;
    if (msg.isNull()) throw new Error("il2cpp_object_new(AddUnitMessage) returned null");
    gcRoot.add(msg);
    const unitIdStr = createManagedString(unitId);
    const pidBuf = Memory.alloc(4); pidBuf.writeS32(playerId);
    const colBuf = Memory.alloc(4); colBuf.writeS32(col);
    const rowBuf = Memory.alloc(4); rowBuf.writeS32(row);
    invokeMethod(addUnitMsgCtor4.info, msg, [unitIdStr, pidBuf, colBuf, rowBuf]);
    // SpawnSource = Deployment (5) — matches what the live game writes
    // for pre-battle player placements.
    msg.add(0x28).writeS32(5);
    return msg;
}

/** Read all SpawnPointGroups in the BC's active SpawnPointSet, each with
 * its team-player-index and spawn point coordinates. */
function readAllSpawnGroups(bc: NativePointer): Array<{
    teamWithPlayerIndex: number;
    points: Array<{ col: number; row: number }>;
}> {
    const board = bc.add(BC_OFF_BOARD).readPointer();
    if (board.isNull()) return [];
    const setIdx = bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).readS32();
    const sets = readManagedList(
        board.add(BCBC_OFF_SPAWN_POINT_SETS).readPointer());
    if (!sets || setIdx < 0 || setIdx >= sets.size) return [];
    const set = readListItem(sets, setIdx);
    const groups = readManagedList(set.add(SPS_OFF_SPAWN_GROUPS).readPointer());
    if (!groups) return [];
    const out = [];
    for (let g = 0; g < groups.size; g++) {
        const grp = readListItem(groups, g);
        if (grp.isNull()) continue;
        const tpi = grp.add(SPG_OFF_TEAM_PLAYER_INDEX).readS32();
        const spawnPts = readManagedList(
            grp.add(SPG_OFF_SPAWN_POINTS).readPointer());
        const points: Array<{ col: number; row: number }> = [];
        if (spawnPts) {
            for (let i = 0; i < spawnPts.size; i++) {
                const sp = readListItem(spawnPts, i);
                if (sp.isNull()) continue;
                points.push({
                    col: sp.add(SP_OFF_COL).readS32(),
                    row: sp.add(SP_OFF_ROW).readS32(),
                });
            }
        }
        out.push({ teamWithPlayerIndex: tpi, points });
    }
    return out;
}

/** Auto-spawn every unit listed in BC.PredefinedUnits into the given runner.
 * Maps PredefinedUnits[i] to SpawnPointGroup[i].SpawnPoints[j] positionally
 * — relies on the convention that PredefinedUnits and SpawnPointGroups are
 * declared in the same order (typically [human, ai]). Returns per-player
 * spawn count + any errors. */
function spawnPredefinedUnitsInto(
    runner: NativePointer, bc: NativePointer,
): {
    ok: boolean;
    spawned: Array<{
        playerId: number; pickedGroupIndex: number;
        teamWithPlayerIndex: number; count: number; errors: string[];
    }>;
} {
    if (!runnerApplyMi) throw new Error("runner.Apply not resolved");
    const pu = readManagedList(bc.add(BC_OFF_PREDEFINED_UNITS).readPointer());
    if (!pu) return { ok: false, spawned: [] };

    const allGroups = readAllSpawnGroups(bc);
    // Heuristic to find which SpawnPointGroup serves a given PredefinedUnits
    // group: pick the spawn group with enough points AND the largest count,
    // preferring exact size match if it exists. Skip groups already consumed
    // by a previous PredefinedUnits group in the same call.
    const consumed = new Set<number>();
    const pickGroup = (needed: number) => {
        let bestIdx = -1;
        let bestScore = -Infinity;
        for (let i = 0; i < allGroups.length; i++) {
            if (consumed.has(i)) continue;
            const avail = allGroups[i].points.length;
            if (avail < needed) continue;
            // Score: prefer exact match (high), penalize over-allocation,
            // but reward more available slots over less.
            const score = avail === needed ? 1000 : avail - needed * 2;
            if (score > bestScore) { bestScore = score; bestIdx = i; }
        }
        return bestIdx;
    };

    const result: Array<{
        playerId: number; pickedGroupIndex: number;
        teamWithPlayerIndex: number; count: number; errors: string[];
    }> = [];
    for (let g = 0; g < pu.size; g++) {
        const grp = readListItem(pu, g);
        if (grp.isNull()) continue;
        const playerId = grp.add(PU_OFF_ID).readS32();
        const unitsList = readManagedList(
            grp.add(PU_OFF_UNITS).readPointer());
        if (!unitsList) {
            result.push({
                playerId, pickedGroupIndex: -1, teamWithPlayerIndex: -1,
                count: 0, errors: ["units list null"],
            });
            continue;
        }
        const pickedIdx = pickGroup(unitsList.size);
        if (pickedIdx < 0) {
            result.push({
                playerId, pickedGroupIndex: -1, teamWithPlayerIndex: -1,
                count: 0,
                errors: [`no SpawnPointGroup with at least ${unitsList.size} ` +
                         `points available (groups: ${allGroups.map(
                            (g, i) => `${i}=${g.points.length}`).join(",")})`],
            });
            continue;
        }
        consumed.add(pickedIdx);
        const picked = allGroups[pickedIdx];
        const errors: string[] = [];
        let count = 0;
        for (let i = 0; i < unitsList.size; i++) {
            const pUnit = readListItem(unitsList, i);
            if (pUnit.isNull()) continue;
            const unitId = readIl2cppString(
                pUnit.add(PUNIT_OFF_UNIT_ID).readPointer());
            if (!unitId) { errors.push(`slot ${i}: null unitId`); continue; }
            const sp = picked.points[i];
            try {
                const msg = buildAddUnitMessage(
                    unitId, playerId, sp.col, sp.row);
                invokeMethod(runnerApplyMi.info, runner, [msg]);
                count++;
            } catch (e) {
                errors.push(`slot ${i} (${unitId} @ ${sp.col},${sp.row}): ` +
                            `${(e as Error).message}`);
            }
        }
        result.push({
            playerId, pickedGroupIndex: pickedIdx,
            teamWithPlayerIndex: picked.teamWithPlayerIndex,
            count, errors,
        });
    }
    return { ok: result.every((r) => r.errors.length === 0), spawned: result };
}

// --- LoadBattle.onLeave hook ---
//
// Hooks CampaignGameModeSource.LoadBattle specifically (not all mode sources)
// and applies the pending patch to the return value. Multiple Interceptor
// attaches on the same method are safe — mode-source-capture.ts already
// hooks LoadBattle for capture purposes; we add a side-channel for mutation.

function installLoadBattleHook(): void {
    const klass = findClassAnywhere(
        "IdunBattle.ViewLogic.BattleSource", "CampaignGameModeSource");
    if (!klass) {
        log("[battle-config] CampaignGameModeSource not found — patch hook disabled");
        return;
    }
    const m = findMethod(klass, "LoadBattle");
    if (!m) {
        log("[battle-config] LoadBattle not found — patch hook disabled");
        return;
    }
    try {
        Interceptor.attach(m.ptr, {
            onLeave(retval) {
                if (pendingPatch === null) return;
                if (retval.isNull()) return;
                const patch = pendingPatch;
                if (patch.consumeOnce !== false) {
                    pendingPatch = null; // consume now to avoid re-apply
                }
                try {
                    const result = applyPatchToConfig(retval, patch);
                    lastApply = result;
                    log(`[battle-config] patch applied: ` +
                        `${result.operations.join("; ")}` +
                        (result.warnings.length > 0
                            ? ` | warnings: ${result.warnings.join("; ")}`
                            : ""));
                } catch (e) {
                    log(`[battle-config] patch threw: ${(e as Error).message}`);
                    lastApply = {
                        ok: false,
                        appliedAt: new Date().toISOString(),
                        bcPtr: retval.toString(),
                        operations: [],
                        warnings: [`exception: ${(e as Error).message}`],
                    };
                }
            },
        });
        log("[battle-config] LoadBattle.onLeave patch hook installed");
    } catch (e) {
        log(`[battle-config] failed to install patch hook: ${(e as Error).message}`);
    }
}

export function register(ctx: Ctx): void {
    installLoadBattleHook();

    ctx.rpc.inspectBattleConfig = () => queueOnMainThread(
        () => inspectBattleConfig());

    /** Dump SpawnPointSets structure for the live BC — useful to figure
     * out which group serves which player. */
    ctx.rpc.inspectSpawnPoints = () => queueOnMainThread(() => {
        const bc = getLiveBattleConfig();
        if (bc === null) return { ok: false, err: "no live BC" };
        const board = bc.add(BC_OFF_BOARD).readPointer();
        if (board.isNull()) return { ok: false, err: "board null" };
        const setIdx = bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).readS32();
        const sets = readManagedList(
            board.add(BCBC_OFF_SPAWN_POINT_SETS).readPointer());
        if (!sets) return { ok: false, err: "spawn point sets null" };
        const allSets = [];
        for (let s = 0; s < sets.size; s++) {
            const set = readListItem(sets, s);
            const groups = readManagedList(
                set.add(SPS_OFF_SPAWN_GROUPS).readPointer());
            const grpInfo = [];
            if (groups) {
                for (let g = 0; g < groups.size; g++) {
                    const grp = readListItem(groups, g);
                    const team = grp.add(SPG_OFF_TEAM_PLAYER_INDEX).readS32();
                    const pts = readManagedList(
                        grp.add(SPG_OFF_SPAWN_POINTS).readPointer());
                    const ptList = [];
                    if (pts) {
                        for (let p = 0; p < pts.size; p++) {
                            const sp = readListItem(pts, p);
                            ptList.push({
                                col: sp.add(SP_OFF_COL).readS32(),
                                row: sp.add(SP_OFF_ROW).readS32(),
                            });
                        }
                    }
                    grpInfo.push({
                        groupIndex: g,
                        teamWithPlayerIndex: team,
                        count: ptList.length,
                        points: ptList,
                    });
                }
            }
            allSets.push({
                setIndex: s,
                active: s === setIdx,
                groupCount: groups?.size ?? 0,
                groups: grpInfo,
            });
        }
        return { ok: true, activeSetIndex: setIdx, sets: allSets };
    });

    /** Set the patch applied at the next LoadBattle. Pass null/undefined
     * fields to leave them unchanged. Default consumeOnce=true means the
     * patch is cleared after one application — set consumeOnce=false to
     * make it sticky across multiple battles. */
    ctx.rpc.setBattleConfigPatch = (patch: BattleConfigPatch) => {
        if (!patch || typeof patch !== "object") {
            return { ok: false, err: "patch must be an object" };
        }
        pendingPatch = { ...patch };
        return {
            ok: true,
            stored: pendingPatch,
            note: "applied at next CampaignGameModeSource.LoadBattle",
        };
    };

    ctx.rpc.clearBattleConfigPatch = () => {
        pendingPatch = null;
        return { ok: true };
    };

    ctx.rpc.getBattleConfigPatchStatus = () => ({
        ok: true,
        pending: pendingPatch,
        lastApply,
    });

    /** Apply a patch DIRECTLY to the live BattleConfiguration (no LoadBattle
     * required). Useful when the battle is already loaded and you want to
     * tweak stats mid-deployment, or when inspectBattleConfig already shows
     * a live config. */
    ctx.rpc.applyBattleConfigPatchNow = (patch: BattleConfigPatch) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) {
                return {
                    ok: false,
                    err: "no live BattleConfiguration to mutate",
                };
            }
            const result = applyPatchToConfig(bc, patch);
            lastApply = result;
            return result;
        });
    };

    /** Build a fresh ISOLATED IdunRunner from the live captured
     * BattleConfiguration, optionally applying a patch first.
     *
     * This is the clean RL workflow: no UI involvement, no in-game battle
     * lifecycle. The new runner is constructed with the patched config —
     * since StartingActions (spawn messages) are built INSIDE Initialize()
     * from PredefinedUnits, our patch IS reflected in what spawns.
     *
     * The runner is registered in the runner-registry; the returned
     * `runnerId` can then be used with `observeBattle({runnerId})`,
     * `applyAddUnit`, `startBattle`, etc.
     *
     * The original captured BC is mutated in-place. Callers wanting to
     * preserve the original should clone it first (not yet implemented). */
    /** Auto-spawn all PredefinedUnits into the given runner. Maps each
     * PredefinedUnits group to the SpawnPointGroup at the same index, and
     * each unit to its corresponding SpawnPoint. */
    ctx.rpc.spawnPredefinedUnits = (opts: { runnerId: number }) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return { ok: false, err: "no live BC" };
            try {
                const entry = getRegistryRunner(opts.runnerId);
                return spawnPredefinedUnitsInto(entry.runner, bc);
            } catch (e) {
                return { ok: false, err: (e as Error).message };
            }
        });
    };

    ctx.rpc.buildPatchedRunner = (patch?: BattleConfigPatch) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) {
                return {
                    ok: false,
                    err: "no live BattleConfiguration captured — " +
                         "warmupGameSingletons first",
                };
            }
            let patchResult: PatchApplyResult | null = null;
            if (patch) {
                patchResult = applyPatchToConfig(bc, patch);
                lastApply = patchResult;
            }
            try {
                const handle = buildRunner(bc);
                const entry = registerRunner(handle);
                log(`[battle-config] buildPatchedRunner: runnerId=` +
                    `${entry.runnerId} runner=${handle.runner} seed=${handle.seed}`);
                return {
                    ok: true,
                    runnerId: entry.runnerId,
                    runner: handle.runner.toString(),
                    seed: handle.seed,
                    bcPtr: bc.toString(),
                    patch: patchResult,
                };
            } catch (e) {
                return {
                    ok: false,
                    err: `buildRunner failed: ${(e as Error).message}`,
                    patch: patchResult,
                };
            }
        });
    };
}
