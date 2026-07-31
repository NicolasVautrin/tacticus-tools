import { runnerClass, runnerOff } from "../game/runner.js";
import { getFieldOffset } from "../il2cpp/helpers.js";

export function findPathfindersOffset() {
    const off = getFieldOffset(runnerClass!, "_pathfinders");
    console.log(`[dump] Pathfinders offset: 0x${off.toString(16)}`);
}
