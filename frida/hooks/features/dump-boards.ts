// dumpAllBoards — enumerate the full BoardConfiguration catalog from the
// captured IdunUniverse (offset 0x28 = List<BoardConfiguration>).
//
// Each Board is serialized via Newtonsoft (same path used by saved-bundle
// configs) so the output is directly drop-in compatible with a BC's
// `.Board` field — i.e., you can swap a Board into any BC JSON and
// re-init a runner from it.
//
// No live BattleConfiguration required — only IdunUniverse, which is
// captured early via Globals.currentIdunUniverse (see unit-visual-resolve).
//
// Layout (BoardConfiguration : UnityWrapperConfiguration<BattleConfigBoardConfiguration>):
//   +0x18  string Id
//   +0x20  int Width
//   +0x24  int Height
//   +0x28  BoardTilesConfiguration[] Tiles
//   +0x30  List<SpawnPointSetConfiguration> SpawnPointSets
//   +0x38  List<BossPlatform> BossPlatforms
//   +0x40  List<DoorConfiguration> Doors
//   +0x48  int TreasureBeachWaveHeight
//
// IdunUniverse.Boards is at offset 0x28 (List<BoardConfiguration>).

import { readIl2cppString } from "../il2cpp/helpers.js";
import { serializeToJson, isSerializerReady } from "../il2cpp/serializer.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { getCapturedUniverse } from "./unit-visual-resolve.js";
import { Ctx } from "../controller.js";

const UNI_OFF_BOARDS = 0x28;        // IdunUniverse.Boards
const LIST_OFF_ITEMS = 0x10;
const LIST_OFF_SIZE = 0x18;
const ARRAY_OFF_DATA = 0x20;
const BOARD_OFF_ID = 0x18;
const BOARD_OFF_W = 0x20;
const BOARD_OFF_H = 0x24;

interface BoardEntry {
    id: string;
    width: number;
    height: number;
    json: string | null;
    err?: string;
}

function dumpAllBoards(opts?: { filter?: string }): {
    ok: boolean;
    total: number;
    matched: number;
    boards: BoardEntry[];
    err?: string;
} {
    const universe = getCapturedUniverse();
    if (!universe) {
        return { ok: false, total: 0, matched: 0, boards: [],
            err: "IdunUniverse not captured" };
    }
    if (!isSerializerReady()) {
        return { ok: false, total: 0, matched: 0, boards: [],
            err: "Newtonsoft serializer not ready" };
    }

    const listRef = universe.add(UNI_OFF_BOARDS).readPointer();
    if (listRef.isNull()) {
        return { ok: false, total: 0, matched: 0, boards: [],
            err: `Universe.Boards list is null (universe=${universe}, off=0x28)` };
    }
    const itemsArr = listRef.add(LIST_OFF_ITEMS).readPointer();
    const size = listRef.add(LIST_OFF_SIZE).readS32();
    if (itemsArr.isNull() || size <= 0 || size > 100000) {
        // Probe nearby offsets in case the offset has shifted
        const probes: Record<string, string> = {};
        for (const off of [0x18, 0x20, 0x28, 0x30, 0x38, 0x40, 0x48, 0x50, 0x58]) {
            try {
                const p = universe.add(off).readPointer();
                if (p.isNull()) { probes[`+0x${off.toString(16)}`] = "null"; continue; }
                const items = p.add(0x10).readPointer();
                const sz = p.add(0x18).readS32();
                probes[`+0x${off.toString(16)}`] =
                    `list@${p} items=${items} size=${sz}`;
            } catch (e) {
                probes[`+0x${off.toString(16)}`] = "err:" + (e as Error).message;
            }
        }
        return { ok: false, total: 0, matched: 0, boards: [],
            err: `Boards list invalid (listRef=${listRef}, itemsArr=${itemsArr}, size=${size}); probes=${JSON.stringify(probes)}` };
    }

    const filterRe = opts?.filter ? new RegExp(opts.filter, "i") : null;
    const out: BoardEntry[] = [];
    let matched = 0;

    for (let i = 0; i < size; i++) {
        const boardPtr = itemsArr.add(ARRAY_OFF_DATA + i * 8).readPointer();
        if (boardPtr.isNull()) continue;
        let id = "";
        let w = 0, h = 0;
        try {
            id = readIl2cppString(
                boardPtr.add(BOARD_OFF_ID).readPointer()) ?? "";
            w = boardPtr.add(BOARD_OFF_W).readS32();
            h = boardPtr.add(BOARD_OFF_H).readS32();
        } catch (e) {
            out.push({
                id: `<idx${i}>`, width: 0, height: 0, json: null,
                err: "id/dim read failed: " + (e as Error).message,
            });
            continue;
        }
        if (filterRe && !filterRe.test(id)) continue;
        matched++;
        let json: string | null = null;
        let err: string | undefined;
        try {
            json = serializeToJson(boardPtr);
        } catch (e) {
            err = "serialize failed: " + (e as Error).message;
        }
        out.push({ id, width: w, height: h, json, err });
    }

    return { ok: true, total: size, matched, boards: out };
}

export function register(ctx: Ctx): void {
    ctx.rpc.dumpAllBoards = (opts?: { filter?: string }) =>
        queueOnMainThread(() => dumpAllBoards(opts));
}
