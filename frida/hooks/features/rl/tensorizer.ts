import { findClass, findMethod } from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { projectPaths } from "../../il2cpp/project.js";

/** 
 * RL State Tensorizer
 * Converts MatchState to a 15x15xN tensor.
 */

const GRID_SIZE = 15;
const CHANNELS = 6;

const pathfindersClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Pathfinding", "Pathfinders");
const findReachableTilesMi = pathfindersClass ? findMethod(pathfindersClass, "FindReachableTiles") : null;

export interface TensorState {
    width: number;
    height: number;
    channels: number;
    data: Float32Array;
}

export function projectMatchStateToTensor(matchState: NativePointer, pathfinders: NativePointer, currentUnitId?: number): TensorState {
    const data = new Float32Array(GRID_SIZE * GRID_SIZE * CHANNELS);
    
    // Channel indices
    const CH_HP_FRIENDLY = 0;
    const CH_HP_ENEMY = 1;
    const CH_STATUS = 2; // Bitmask: 1=Moved, 2=Attacked, 4=Stunned
    const CH_ELEVATION = 3;
    const CH_OVERWATCH = 4;
    const CH_LEGAL_MOVES = 5;

    // 1. Get all entities
    const entities = projectPaths(matchState, [
        { path: "_entities", out: "list" }
    ]).list as any[];

    if (!entities) return { width: GRID_SIZE, height: GRID_SIZE, channels: CHANNELS, data };

    // Find current player team to distinguish friendly/enemy
    let friendlyTeamId = -1;
    let currentUnitEntity: NativePointer = ptr(0);

    for (const entity of entities) {
        const ePtr = ptr(entity as string);
        const props = projectPaths(ePtr, [
            { path: "Id", out: "id" },
            { path: "Type", out: "type" },
            { path: "Owner.PlayerEntityId", out: "ownerId" },
        ]);

        if (props.type === 1 && props.id === currentUnitId) {
            currentUnitEntity = ePtr;
            friendlyTeamId = props.ownerId as number;
            break;
        }
    }

    // Call pathfinder for legal moves if unit is found
    if (!currentUnitEntity.isNull() && findReachableTilesMi) {
        const typeArg = Memory.alloc(4); typeArg.writeS32(0); // Walk
        const rangeArg = Memory.alloc(4); rangeArg.writeS32(99); // Max range for testing, or read from MovementComponent
        const currentTileArg = ptr(0); // Optional?
        
        try {
            const list = invokeMethod(findReachableTilesMi.info, pathfinders, [typeArg, currentUnitEntity, rangeArg, currentTileArg]) as NativePointer;
            if (list && !list.isNull()) {
                const tiles = projectPaths(list, [
                    { path: "_items", out: "items" }
                ]).items as any[];
                
                if (tiles) {
                    for (const tile of tiles) {
                        if (!tile) continue;
                        const tPtr = ptr(tile as string);
                        if (tPtr.isNull()) continue;
                        const tProps = projectPaths(tPtr, [
                            { path: "Position.Coordinate.Column", out: "col" },
                            { path: "Position.Coordinate.Row", out: "row" },
                        ]);
                        const c = tProps.col as number;
                        const r = tProps.row as number;
                        if (c >= 0 && c < GRID_SIZE && r >= 0 && r < GRID_SIZE) {
                            data[(r * GRID_SIZE + c) * CHANNELS + CH_LEGAL_MOVES] = 1.0;
                        }
                    }
                }
            }
        } catch (e) {
            console.log(`[rl] Pathfinder call failed: ${e}`);
        }
    }

    for (const entity of entities) {
        const ePtr = ptr(entity as string);
        const props = projectPaths(ePtr, [
            { path: "Type", out: "type" },
            // For Tile
            { path: "Position.Coordinate.Column", out: "col" },
            { path: "Position.Coordinate.Row", out: "row" },
            { path: "Component.Elevation", out: "elevation" },
            // For Unit
            { path: "Health.RemainingValue", out: "hp", type: "fix64" },
            { path: "Health.MaximumValue", out: "hpMax", type: "fix64" },
            { path: "Owner.PlayerEntityId", out: "ownerId" },
        ]);

        const col = props.col as number;
        const row = props.row as number;

        if (col === undefined || row === undefined || col < 0 || col >= GRID_SIZE || row < 0 || row >= GRID_SIZE) {
            continue;
        }

        const idx = (row * GRID_SIZE + col) * CHANNELS;

        if (props.type === 0) { // Tile
            data[idx + CH_ELEVATION] = (props.elevation as number || 0) / 5.0; // Normalization
        } else if (props.type === 1) { // Unit
            const hp = props.hp as number || 0;
            const hpMax = props.hpMax as number || 1;
            const normHp = hp / hpMax;

            // Simple team heuristic for now
            const isFriendly = (props.ownerId as number) <= 3; // Typically human is 3
            if (isFriendly) {
                data[idx + CH_HP_FRIENDLY] = normHp;
            } else {
                data[idx + CH_HP_ENEMY] = normHp;
            }
        }
    }

    return { width: GRID_SIZE, height: GRID_SIZE, channels: CHANNELS, data };
}
