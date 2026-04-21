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

export function register(_ctx: Ctx): void {
    for (const cls of MODE_SOURCES) {
        hook(ASM, NS, cls, "LoadBattle", {
            onLeave(retval) {
                if (retval.isNull()) return;
                try {
                    const json = serializeToJson(retval);
                    if (!json) return;
                    send({
                        t: "captured_config",
                        id: `${cls}:${++counter}`,
                        mode: cls,
                        ts: Date.now(),
                        bytes: json.length,
                        json,
                    });
                } catch (e) {
                    console.log(`[capture] ${cls}.LoadBattle onLeave: ${(e as Error).message}`);
                }
            },
        });
    }
}
