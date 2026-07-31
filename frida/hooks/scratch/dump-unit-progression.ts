import { runnerOff } from "../game/runner.js";
import { state } from "../game/state.js";
import { projectPaths } from "../il2cpp/project.js";

export function dumpUnitProgression() {
    if (!state.liveRunner) return;
    const matchState = state.liveRunner.add(runnerOff.state).readPointer();
    if (matchState.isNull()) return;

    const entities = projectPaths(matchState, [
        { path: "_entities", out: "list" }
    ]).list as any[];

    if (!entities) return;

    for (const entity of entities) {
        const ePtr = ptr(entity as string);
        const props = projectPaths(ePtr, [
            { path: "Type", out: "type" },
            { path: "Component.Unit.Rank", out: "rank" },
            { path: "Component.Unit.StarLevel", out: "star" },
            { path: "Component.Unit.Level", out: "level" },
            { path: "Component.Health.MaximumValue", out: "hp", type: "fix64" },
            { path: "Component.ExtraMaxDamage.InitialValue", out: "extraDmg" },
        ]);

        if (props.type === 1) { // Unit
            console.log(`[dump] Unit Rank=${props.rank} Star=${props.star} Level=${props.level} HP=${props.hp} ExtraDmg=${props.extraDmg}`);
        }
    }
}
