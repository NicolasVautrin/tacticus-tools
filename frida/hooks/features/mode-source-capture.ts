// Passive capture of BattleConfiguration assembled by the game's own
// GameModeSource.LoadBattle(isRestart) → BattleConfiguration.
//
// Each concrete game mode (Campaign, PVP, GuildBoss, etc.) overrides LoadBattle
// to stitch a full BattleConfiguration from static bundles + user state. Hooking
// all of them lets us record every battle the user is about to play, without
// reimplementing the assembly logic ourselves.
//
// On capture, the config is serialized to JSON and broadcast via `send()`.
// The Frida host forwards it to subscribed WS clients — the browser view then
// renders board + initial unit placements from the JSON.

import { hook } from "../il2cpp/helpers.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

const ASM = "Assembly-CSharp.dll";
const NS = "IdunBattle.ViewLogic.BattleSource";

// Concrete GameModeSource classes (abstract/interface types omitted).
const MODE_SOURCES = [
    "CampaignGameModeSource",
    "CampaignEventGameModeSource",
    "PvpGameModeSource",
    "PvpStarterSeasonGameModeSource",
    "SyncPvpGameModeSource",
    "GuildBossGameModeSource",
    "GuildWarsGameModeSource",
    "MachinesOfWarEventGameModeSource",
    "LegendaryEventGameModeSource",
    "SurvivalEventGameModeSource",
    "TreasureBeachGameModeSource",
    "SandboxGameModeSource",
    "FriendlyGameModeSource",
    "EndlessGameModeSource",
    "AutomaticBattlesGameModeSource",
    "UserReplayGameModeSource",
    "DebugReplayGameModeSource",
    "TrailerGameModeSource",
];

let counter = 0;

// CampaignGameModeSource exposes the live `_currentCampaignId` (string ptr at
// offset 0x68) and `_currentLocationIndex` (int at 0x70). Capturing them at
// LoadBattle time gives the archive panel a much richer identity than the
// generic class name. Other GameModeSource subclasses have different
// layouts — for now we only enrich the Campaign one.
const CGMS_OFF_CAMPAIGN_ID = 0x68;
const CGMS_OFF_LOCATION_INDEX = 0x70;

function readManagedString(ptr_: NativePointer): string | null {
    // Il2CppString layout (Il2CppObject prefix is 0x10 bytes on x64):
    //   0x00: Il2CppClass* klass
    //   0x08: void*        monitor
    //   0x10: int32        length
    //   0x14: char16_t     chars[length]
    // Strict bounds — never fall through to an unbounded read because a
    // garbage `length` could otherwise make readUtf16String scan unmapped
    // memory and hang the calling thread.
    try {
        if (ptr_.isNull()) return null;
        const length = ptr_.add(0x10).readS32();
        if (length <= 0 || length > 1024) return null;
        return ptr_.add(0x14).readUtf16String(length);
    } catch { return null; }
}

export function register(_ctx: Ctx): void {
    for (const cls of MODE_SOURCES) {
        hook(ASM, NS, cls, "LoadBattle", {
            onEnter(args) {
                // Stash `this` for onLeave — we need the source instance to
                // read identity fields.
                this.sourcePtr = ptr(args[0].toString());
            },
            onLeave(retval) {
                if (retval.isNull()) return;
                // Newtonsoft serialization of a 540 KB BattleConfiguration
                // takes 200–500 ms via il2cpp_runtime_invoke. Doing it in
                // onLeave blocks LoadBattle's return on the game thread,
                // freezing the loading transition. Pin the pointer (gcRoot)
                // and defer the heavy work to the next main-pump tick — the
                // game proceeds immediately, capture finishes asynchronously.
                let battleConfigPtr: NativePointer;
                try { battleConfigPtr = ptr(retval.toString()); }
                catch { return; }
                if (battleConfigPtr.isNull()) return;
                // Read identity fields synchronously (cheap memory reads)
                // while sourcePtr is still valid.
                let campaignId: string | null = null;
                let locationIndex: number | null = null;
                if (cls === "CampaignGameModeSource") {
                    const sp = this.sourcePtr as NativePointer | undefined;
                    if (sp && !sp.isNull()) {
                        try {
                            campaignId = readManagedString(
                                sp.add(CGMS_OFF_CAMPAIGN_ID).readPointer());
                            locationIndex = sp.add(CGMS_OFF_LOCATION_INDEX)
                                .readS32();
                        } catch { /* skip enrichment on read failure */ }
                    }
                }
                // Pin so GC doesn't reclaim it before the deferred serialize
                // runs.
                try { gcRoot.add(battleConfigPtr); } catch { /* */ }
                queueOnMainThread(() => {
                    try {
                        const json = serializeToJson(battleConfigPtr);
                        if (json) {
                            send({
                                t: "captured_config",
                                id: `${cls}:${++counter}`,
                                mode: cls,
                                ts: Date.now(),
                                bytes: json.length,
                                campaignId,
                                locationIndex,
                                json,
                            });
                        }
                    } catch (e) {
                        log(`[capture] ${cls}.LoadBattle deferred: ${(e as Error).message}`);
                    } finally {
                        try { gcRoot.remove(battleConfigPtr); } catch { /* */ }
                    }
                }).catch((e) => {
                    log(`[capture] ${cls}.LoadBattle queue: ${(e as Error).message}`);
                });
            },
        });
    }
}
