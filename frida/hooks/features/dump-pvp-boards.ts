// dumpPvpAndSyncBoards — enumerate all PvP arena + SyncPvP board IDs
// from gameConfig.battles, then call `IdunAssetsUtil.LoadBoard(string)`
// for each → BoardConfiguration → serialize via Newtonsoft.
//
// Output is a {id, kind, json} array drop-in compatible with any BC's
// `.Board` field. Combined with patched PredefinedUnits + addUnit, this
// gives full map-swap capability offline (one-time dump, then reuse).
//
// Layout (BattlesConfigDto):
//   +0x10  campaigns: CampaignsConfigDto
//   +0x18  pvpBoards: List<PvpBoardConfigDto>           ← arena
//   +0x20  syncPvpBoards: List<SyncPvpBoardConfigDto>   ← sync PvP
//   +0x28  onslaught: OnslaughtConfigDto
//
// Layout (PvpBoardConfigDto):
//   +0x10  BoardId: string
//   +0x18  SpawnPointsSet: int
//
// Layout (SyncPvpBoardConfigDto):
//   +0x10  BoardId: string

import {
    findClassAnywhere, findMethod, getFieldOffset, readIl2cppString,
} from "../il2cpp/helpers.js";
import {
    createManagedString, invokeMethod,
} from "../il2cpp/invoke.js";
import { serializeToJson, isSerializerReady } from "../il2cpp/serializer.js";
import { getLastGameConfig } from "./campaign-builder.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

const BATTLES_OFF_PVP_BOARDS = 0x18;
const BATTLES_OFF_SYNC_PVP_BOARDS = 0x20;
const LIST_OFF_ITEMS = 0x10;
const LIST_OFF_SIZE = 0x18;
const ARRAY_OFF_DATA = 0x20;
const DTO_OFF_BOARD_ID = 0x10;
const DTO_OFF_SPAWN_POINT_SET = 0x18;
// GameConfigDto.boardsToInclude: List<BoardToInclude> @ 0xE8 — master
// catalog including Guild War / Guild Boss / Onslaught / etc. boards.
// BoardToInclude.BoardId @ 0x10 (string), SandboxGuildBosses @ 0x18 (list).
const GAMECONFIG_OFF_BOARDS_TO_INCLUDE = 0xE8;

interface BoardDump {
    id: string;
    kind: "pvp" | "syncPvp" | "global";
    spawnPointsSet: number | null;
    json: string | null;
    err?: string;
}

function readBoardIdList(listRef: NativePointer): Array<{ id: string; sps: number | null }> {
    if (listRef.isNull()) return [];
    const items = listRef.add(LIST_OFF_ITEMS).readPointer();
    const size = listRef.add(LIST_OFF_SIZE).readS32();
    if (items.isNull() || size <= 0 || size > 10000) return [];
    const out: Array<{ id: string; sps: number | null }> = [];
    for (let i = 0; i < size; i++) {
        const dtoPtr = items.add(ARRAY_OFF_DATA + i * 8).readPointer();
        if (dtoPtr.isNull()) continue;
        try {
            const idP = dtoPtr.add(DTO_OFF_BOARD_ID).readPointer();
            const id = readIl2cppString(idP) ?? "";
            let sps: number | null = null;
            try { sps = dtoPtr.add(DTO_OFF_SPAWN_POINT_SET).readS32(); } catch { /* */ }
            if (id) out.push({ id, sps });
        } catch { /* skip */ }
    }
    return out;
}

function dumpPvpAndSyncBoards(opts?: {
    pvp?: boolean; syncPvp?: boolean; global?: boolean;
}): {
    ok: boolean; pvpCount: number; syncCount: number; globalCount: number;
    boards: BoardDump[]; err?: string;
} {
    if (!isSerializerReady()) {
        return { ok: false, pvpCount: 0, syncCount: 0, globalCount: 0, boards: [],
            err: "Newtonsoft serializer not ready" };
    }

    const wantPvp = opts?.pvp ?? true;
    const wantSync = opts?.syncPvp ?? true;
    const wantGlobal = opts?.global ?? true;

    const gameConfig = getLastGameConfig();
    if (!gameConfig) {
        return { ok: false, pvpCount: 0, syncCount: 0, globalCount: 0, boards: [],
            err: "lastGameConfig not captured — run buildCampaignConfig once or amorce" };
    }

    // Resolve GameConfigDto.battles field offset dynamically
    const gameConfigClass = gameConfig.readPointer();
    if (gameConfigClass.isNull()) {
        return { ok: false, pvpCount: 0, syncCount: 0, globalCount: 0, boards: [],
            err: "gameConfig class pointer null" };
    }
    const offBattles = getFieldOffset(gameConfigClass, "battles");
    if (offBattles < 0) {
        return { ok: false, pvpCount: 0, syncCount: 0, globalCount: 0, boards: [],
            err: "GameConfigDto.battles offset not found" };
    }
    const battlesPtr = gameConfig.add(offBattles).readPointer();
    if (battlesPtr.isNull()) {
        return { ok: false, pvpCount: 0, syncCount: 0, globalCount: 0, boards: [],
            err: "gameConfig.battles is null" };
    }

    // Find IdunAssetsUtil.LoadBoard(string) — static
    const assetsUtilClass = findClassAnywhere(
        "idun.Idun.Source.Scripts", "IdunAssetsUtil");
    if (!assetsUtilClass) {
        return { ok: false, pvpCount: 0, syncCount: 0, globalCount: 0, boards: [],
            err: "IdunAssetsUtil class not found" };
    }
    const loadBoardMi = findMethod(assetsUtilClass, "LoadBoard");
    if (!loadBoardMi) {
        return { ok: false, pvpCount: 0, syncCount: 0, globalCount: 0, boards: [],
            err: "IdunAssetsUtil.LoadBoard method not found" };
    }

    const pvpList = wantPvp
        ? readBoardIdList(battlesPtr.add(BATTLES_OFF_PVP_BOARDS).readPointer())
        : [];
    const syncList = wantSync
        ? readBoardIdList(battlesPtr.add(BATTLES_OFF_SYNC_PVP_BOARDS).readPointer())
        : [];
    // boardsToInclude is on GameConfigDto root (0xE8), not under battles.
    const globalList = wantGlobal
        ? readBoardIdList(gameConfig.add(GAMECONFIG_OFF_BOARDS_TO_INCLUDE).readPointer())
        : [];

    const out: BoardDump[] = [];

    for (const { id, sps } of pvpList) {
        const dump: BoardDump = { id, kind: "pvp", spawnPointsSet: sps, json: null };
        try {
            const idStr = createManagedString(id);
            const boardPtr = invokeMethod(loadBoardMi.info, null, [idStr]) as NativePointer;
            if (!boardPtr || boardPtr.isNull()) {
                dump.err = "LoadBoard returned null";
            } else {
                dump.json = serializeToJson(boardPtr);
            }
        } catch (e) {
            dump.err = "load/serialize failed: " + (e as Error).message;
        }
        out.push(dump);
    }

    for (const { id, sps } of syncList) {
        const dump: BoardDump = { id, kind: "syncPvp", spawnPointsSet: sps, json: null };
        try {
            const idStr = createManagedString(id);
            const boardPtr = invokeMethod(loadBoardMi.info, null, [idStr]) as NativePointer;
            if (!boardPtr || boardPtr.isNull()) {
                dump.err = "LoadBoard returned null";
            } else {
                dump.json = serializeToJson(boardPtr);
            }
        } catch (e) {
            dump.err = "load/serialize failed: " + (e as Error).message;
        }
        out.push(dump);
    }

    for (const { id, sps } of globalList) {
        const dump: BoardDump = { id, kind: "global", spawnPointsSet: sps, json: null };
        try {
            const idStr = createManagedString(id);
            const boardPtr = invokeMethod(loadBoardMi.info, null, [idStr]) as NativePointer;
            if (!boardPtr || boardPtr.isNull()) {
                dump.err = "LoadBoard returned null";
            } else {
                dump.json = serializeToJson(boardPtr);
            }
        } catch (e) {
            dump.err = "load/serialize failed: " + (e as Error).message;
        }
        out.push(dump);
    }

    return {
        ok: true,
        pvpCount: pvpList.length,
        syncCount: syncList.length,
        globalCount: globalList.length,
        boards: out,
    };
}

export function register(ctx: Ctx): void {
    ctx.rpc.dumpPvpAndSyncBoards = (opts?: { pvp?: boolean; syncPvp?: boolean }) =>
        queueOnMainThread(() => dumpPvpAndSyncBoards(opts));
}
