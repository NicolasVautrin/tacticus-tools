import { projectMatchStateToTensor } from "./tensorizer.js";
import { state } from "../../game/state.js";
import { runnerOff } from "../../game/runner.js";
import { Ctx } from "../../controller.js";

export function register(ctx: Ctx): void {
    ctx.rpc.rlGetObservation = (unitId?: number) => {
        const runner = state.liveRunner;
        if (!runner) return { error: "No live runner found" };

        const matchState = runner.add(runnerOff.state).readPointer();
        if (matchState.isNull()) return { error: "MatchState is null" };

        const pathfinders = runner.add(0x118).readPointer(); // <Pathfinders>k__BackingField

        const tensor = projectMatchStateToTensor(matchState, pathfinders, unitId);
        
        // Return as plain array for JSON serialization
        return {
            width: tensor.width,
            height: tensor.height,
            channels: tensor.channels,
            data: Array.from(tensor.data)
        };
    };
}
