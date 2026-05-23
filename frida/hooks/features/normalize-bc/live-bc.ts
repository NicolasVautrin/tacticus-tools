// Live BattleConfiguration helpers used by `normalize-bc/*`:
//   - direct memory access to the captured `_currentBattle` and its
//     `Units[]` templates / `Player.Players` config / `Board.SpawnPointSets`
//   - explicit binary offsets (`UC.*`) for stat + progression fields on
//     `UnitConfiguration` so we can mutate templates in place without
//     round-tripping through JSON
//   - AddUnitMessage builder duplicated from launch.ts / battle-config.ts
//     so this module is self-contained (the helper is trivial enough that
//     duplication beats cross-feature imports)
//
// All offsets are from `data/dumps/<HASH>/dump.cs` for build `rmvdp0v56c`.

import {
    findClass, findCtorByParamCount, findMethodByParamCount,
    readIl2cppString,
} from "../../il2cpp/helpers.js";
import {
    createManagedString, invokeMethod, il2cpp_object_new,
} from "../../il2cpp/invoke.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import { getLastSource } from "../campaign-builder.js";

// UnitConfiguration binary offsets (Unity 6 IL2CPP v39, build rmvdp0v56c).
export const UC = {
    ID: 0x10,
    VISUAL_ID: 0x18,
    FACTION: 0x28,
    HEALTH: 0x38, REMAINING_HP_HASVAL: 0x3C, REMAINING_HP_VAL: 0x40,
    ARMOR: 0x44, FIXED_ARMOR: 0x48, SHIELD: 0x4C, DAMAGE: 0x50,
    MOVEMENT: 0x54, RANGE: 0x5C,
    CRIT_CHANCE: 0x60, CRIT_DAMAGE: 0x64,
    BLOCK_CHANCE: 0x68, BLOCK_DAMAGE: 0x6C,
    LEVEL: 0x7C, RARITY: 0x80, RANK: 0x84, STAR_LEVEL: 0x88,
    ACTIVE_ABILITY_LEVEL: 0xB8,
    PASSIVE_ABILITY_LEVEL: 0xBC,
    TERTIARY_ABILITY_LEVEL: 0xC0,
} as const;

export const BC_OFF_UNITS = 0x80;
export const BC_OFF_PLAYER = 0x30;
export const BC_OFF_BOARD = 0x68;
export const BC_OFF_SPAWN_POINT_SET_INDEX = 0x28;
export const CGMS_OFF_CURRENT_BATTLE = 0x80;
export const LIST_OFF_ITEMS = 0x10;
export const LIST_OFF_SIZE = 0x18;
export const ARRAY_OFF_DATA = 0x20;

// SpawnPointSet/Group offsets (mirrors battle-config.ts).
const BCBC_OFF_SPAWN_POINT_SETS = 0x28; // BattleConfigBoardConfiguration
const SPS_OFF_SPAWN_GROUPS = 0x10;      // SpawnPointSetConfiguration
const SPG_OFF_TEAM_PLAYER_INDEX = 0x10;
const SPG_OFF_SPAWN_POINTS = 0x18;
const SP_OFF_COL = 0x10;
const SP_OFF_ROW = 0x14;

// TeamWithPlayerIndex enum → (teamId, playerIdx). Verified against native
// TeamPlayerIdExtensions.Unfold():
//   0 → (1, 0)  Player team 1, idx 0           ← single-player human player
//   1 → (2, 0)  AI team 2, idx 0               ← single-player AI
//   2 → (1, 1)  Player team 1, idx 1 (coop)
//   3 → (2, 1)  AI team 2, idx 1
//   4 → (3, 0)  Env team 3, idx 0
//   5 → (3, 1)  Env team 3, idx 1
//   6 → (0, 0)  Neutral
export const TWPI_HUMAN_DEFAULT = 0;

export function getLiveBC(): NativePointer | null {
    const src = getLastSource();
    if (src === null) return null;
    try {
        const bc = src.add(CGMS_OFF_CURRENT_BATTLE).readPointer();
        return bc.isNull() ? null : bc;
    } catch { return null; }
}

export function iterTemplates(bc: NativePointer): NativePointer[] {
    const list = bc.add(BC_OFF_UNITS).readPointer();
    if (list.isNull()) return [];
    const items = list.add(LIST_OFF_ITEMS).readPointer();
    const size = list.add(LIST_OFF_SIZE).readS32();
    if (items.isNull() || size < 0 || size > 10000) return [];
    const out: NativePointer[] = [];
    for (let i = 0; i < size; i++) {
        const p = items.add(ARRAY_OFF_DATA + i * Process.pointerSize)
            .readPointer();
        if (!p.isNull()) out.push(p);
    }
    return out;
}

export interface NormalizedTemplateStats {
    health: number; damage: number; armor: number; fixedArmor: number;
    critChance: number; critDamage: number;
    blockChance: number; blockDamage: number;
}

export function writeTemplateStats(
    uc: NativePointer, s: NormalizedTemplateStats,
): void {
    uc.add(UC.HEALTH).writeS32(s.health);
    uc.add(UC.DAMAGE).writeS32(s.damage);
    uc.add(UC.ARMOR).writeS32(s.armor);
    uc.add(UC.FIXED_ARMOR).writeS32(s.fixedArmor);
    uc.add(UC.CRIT_CHANCE).writeS32(s.critChance);
    uc.add(UC.CRIT_DAMAGE).writeS32(s.critDamage);
    uc.add(UC.BLOCK_CHANCE).writeS32(s.blockChance);
    uc.add(UC.BLOCK_DAMAGE).writeS32(s.blockDamage);
    // Reset RemainingHealth = Health (start at full HP)
    uc.add(UC.REMAINING_HP_HASVAL).writeU8(1);
    uc.add(UC.REMAINING_HP_VAL).writeS32(s.health);
}

export function writeTemplateProgression(uc: NativePointer, opts: {
    rank?: number; rarity?: number; level?: number; starLevel?: number;
    abilityLevel?: number;
}): void {
    if (typeof opts.rank === "number") uc.add(UC.RANK).writeS32(opts.rank);
    if (typeof opts.rarity === "number") uc.add(UC.RARITY).writeS32(opts.rarity);
    if (typeof opts.level === "number") uc.add(UC.LEVEL).writeS32(opts.level);
    if (typeof opts.starLevel === "number") {
        uc.add(UC.STAR_LEVEL).writeS32(opts.starLevel);
    }
    if (typeof opts.abilityLevel === "number") {
        // ActiveAbilities[] is the override list (usually empty in templates),
        // but ActiveAbilityLevel/PassiveAbilityLevel always apply to the
        // unit's native abilities from gameConfig.units.lineup[id]. So we
        // write unconditionally.
        uc.add(UC.ACTIVE_ABILITY_LEVEL).writeS32(opts.abilityLevel);
        uc.add(UC.PASSIVE_ABILITY_LEVEL).writeS32(opts.abilityLevel);
        uc.add(UC.TERTIARY_ABILITY_LEVEL).writeS32(opts.abilityLevel);
    }
}

/** Read the spawn points of the BC's active SpawnPointSet group matching
 * `twpi` (default = human player). Returns the (col, row) list in declaration
 * order. Returns empty when no group matches or the board is unreadable. */
export function readSpawnPointsForTwpi(
    bc: NativePointer, twpi: number,
): Array<{ col: number; row: number }> {
    try {
        const board = bc.add(BC_OFF_BOARD).readPointer();
        if (board.isNull()) return [];
        const setIdx = bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).readS32();
        const sets = board.add(BCBC_OFF_SPAWN_POINT_SETS).readPointer();
        if (sets.isNull()) return [];
        const setsArr = sets.add(LIST_OFF_ITEMS).readPointer();
        const setsSize = sets.add(LIST_OFF_SIZE).readS32();
        if (setsArr.isNull() || setIdx < 0 || setIdx >= setsSize) return [];
        const set = setsArr.add(ARRAY_OFF_DATA + setIdx * Process.pointerSize)
            .readPointer();
        if (set.isNull()) return [];
        const groups = set.add(SPS_OFF_SPAWN_GROUPS).readPointer();
        if (groups.isNull()) return [];
        const grpArr = groups.add(LIST_OFF_ITEMS).readPointer();
        const grpSize = groups.add(LIST_OFF_SIZE).readS32();
        if (grpArr.isNull()) return [];
        for (let g = 0; g < grpSize; g++) {
            const grp = grpArr.add(ARRAY_OFF_DATA + g * Process.pointerSize)
                .readPointer();
            if (grp.isNull()) continue;
            const grpTwpi = grp.add(SPG_OFF_TEAM_PLAYER_INDEX).readS32();
            if (grpTwpi !== twpi) continue;
            const pts = grp.add(SPG_OFF_SPAWN_POINTS).readPointer();
            if (pts.isNull()) return [];
            const ptsArr = pts.add(LIST_OFF_ITEMS).readPointer();
            const ptsSize = pts.add(LIST_OFF_SIZE).readS32();
            if (ptsArr.isNull()) return [];
            const out: Array<{ col: number; row: number }> = [];
            for (let i = 0; i < ptsSize; i++) {
                const sp = ptsArr.add(ARRAY_OFF_DATA + i * Process.pointerSize)
                    .readPointer();
                if (sp.isNull()) continue;
                out.push({
                    col: sp.add(SP_OFF_COL).readS32(),
                    row: sp.add(SP_OFF_ROW).readS32(),
                });
            }
            return out;
        }
    } catch { /* fallthrough → [] */ }
    return [];
}

/** Best-effort lookup of the human player's PlayerId via
 * PlayersConfiguration.FindPlayerConfigByType(PlayerType.Human). Returns
 * `Nullable<ValueTuple<PlayerId, PlayerConfiguration>>`.
 *
 * .NET special-cases Nullable<T> boxing: a Nullable<T> with hasValue=true is
 * unwrapped to a *boxed T*; null Nullable boxes to actual null. So we get
 * either `null` (when no Human player exists) or a boxed
 * ValueTuple<PlayerId, PlayerConfiguration>:
 *   +0x10  Item1 = PlayerId (4 bytes, padded to 8)
 *   +0x18  Item2 = PlayerConfiguration ptr (8 bytes)
 *
 * Verified by `probeFindHumanPlayer` on Campaign1_64: Human → 11, AI → 12. */
let _findHumanPlayerMi: { info: NativePointer; ptr: NativePointer } | null = null;
let _findHumanResolved = false;
export function findHumanPlayerId(bc: NativePointer): number | null {
    try {
        const playersConfig = bc.add(BC_OFF_PLAYER).readPointer();
        if (playersConfig.isNull()) return null;
        if (!_findHumanResolved) {
            _findHumanResolved = true;
            const klass = findClass(
                "BattleLogicAssembly.dll", "IdunBattle.Configuration",
                "PlayersConfiguration");
            if (!klass) return null;
            const m = findMethodByParamCount(klass, "FindPlayerConfigByType", 1);
            _findHumanPlayerMi = m;
        }
        if (!_findHumanPlayerMi) return null;
        const playerTypeBuf = Memory.alloc(4); playerTypeBuf.writeS32(0); // Human=0
        const boxed = invokeMethod(_findHumanPlayerMi.info, playersConfig,
            [playerTypeBuf]) as NativePointer;
        if (!boxed || boxed.isNull()) return null;
        return boxed.add(0x10).readS32();
    } catch { return null; }
}

/** Read a unit template's Faction string from the live BC.Units[].
 *  Used by autoBis to satisfy the per-faction filter on items. */
export function readUnitFaction(
    bc: NativePointer, unitId: string,
): string | null {
    const templates = iterTemplates(bc);
    for (const uc of templates) {
        const id = readIl2cppString(uc.add(UC.ID).readPointer());
        if (id !== unitId) continue;
        try {
            return readIl2cppString(uc.add(UC.FACTION).readPointer());
        } catch { return null; }
    }
    return null;
}

// AddUnitMessage builder — duplicated here from launch.ts/battle-config.ts to
// keep this module self-contained. The 4-arg ctor takes (string, PlayerId,
// int, int) where PlayerId is a struct { int } passed as pointer to S32.
const addUnitMsgClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Messages", "AddUnitMessage");
const addUnitMsgCtor4 = addUnitMsgClass
    ? findCtorByParamCount(addUnitMsgClass, 4) : null;
const AUM_OFF_SPAWN_SOURCE = 0x28;
const SPAWN_SOURCE_DEPLOYMENT = 5;

export function buildAddUnitMsg(
    unitId: string, playerId: number, col: number, row: number,
): NativePointer {
    if (!addUnitMsgClass) throw new Error("AddUnitMessage class not found");
    if (!addUnitMsgCtor4) throw new Error("AddUnitMessage 4-arg ctor not found");
    const msg = il2cpp_object_new(addUnitMsgClass) as NativePointer;
    if (msg.isNull()) throw new Error("il2cpp_object_new(AddUnitMessage) returned null");
    gcRoot.add(msg);
    const idStr = createManagedString(unitId);
    const pidBuf = Memory.alloc(4); pidBuf.writeS32(playerId);
    const colBuf = Memory.alloc(4); colBuf.writeS32(col);
    const rowBuf = Memory.alloc(4); rowBuf.writeS32(row);
    invokeMethod(addUnitMsgCtor4.info, msg, [idStr, pidBuf, colBuf, rowBuf]);
    // Without SpawnSource=Deployment, InputMessageProcessor routes the unit
    // to the environment instead of the intended owner.
    msg.add(AUM_OFF_SPAWN_SOURCE).writeS32(SPAWN_SOURCE_DEPLOYMENT);
    return msg;
}
