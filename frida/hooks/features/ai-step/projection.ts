import {
    class_get_fields, class_get_name, class_get_parent,
    field_get_name, field_get_offset, field_get_type,
    findMethodByParamCount, s,
    type_get_class_or_element_class,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import {
    EntityType, forEachEntity, projectMatchState,
} from "../../game/match-state.js";
import { abilityName } from "../../data/ability-names.js";
import {
    extractTilePtrs, extractTiles, getMovableTilesMi, getUnitMainTile, invokeBool,
    isAliveMi, isCtrlByCurMi, hasActionLeftMi, isRangedMi,
    mowAbilityTypes, readTileCoord, unitAbilityTypes,
} from "./internals.js";

export interface RankedTile {
    col: number; row: number;
    dmgMin?: number; dmgMax?: number;
    kill?: boolean; killSure?: boolean; mightCrit?: boolean;
}
export interface AttackEval {
    targetId: number; targetVis: string | null;
    targetPos: { col: number; row: number } | null;
    abilityId: number; ability: string; kind: string;
    movableCount: number; rankCount: number;
    ranked: RankedTile[]; err: string | null;
}
export interface UnitAttackPlan {
    unitId: number; visualId: string | null;
    pos: { col: number; row: number } | null;
    currentTile: { col: number; row: number } | null;
    abilities: Array<{ id: number; name: string; kind: string }>;
    evals: AttackEval[];
}

/** Ranking des positions d'attaque par (unit contrôlée, ability, target ennemi)
 *  via shrink-and-recall sur GetBestTileToAttackFrom. Lit les abilities
 *  CONCRÈTES (NormalAttackType + actives) + ajoute la tile courante au set
 *  candidat. NE MUTE PAS le MatchState (seul un IOrderedSet transient est muté). */
export function computeAttackPlans(
    statePtr: NativePointer, movementQuery: NativePointer,
    attackQuery: NativePointer, getBestMi: { info: NativePointer },
    dpq: NativePointer,
    opts: {
        unitId?: number; targetId?: number; manualAbility?: number | null;
        allAbilities?: boolean; maxRank?: number; overrideRange?: number | null;
    },
): { units: UnitAttackPlan[]; enemyCount: number; removeWorks: boolean | null } {
    const manualAbility = opts.manualAbility ?? null;
    const allAbilities = opts.allAbilities === true;
    const maxRank = (opts.maxRank && opts.maxRank > 0) ? opts.maxRank : 8;
    const overrideRange = opts.overrideRange ?? null;

    const proj = projectMatchState(statePtr);
    const visById = new Map<number, string | null>();
    const posById = new Map<number, { col: number; row: number } | null>();
    for (const u of proj.units) {
        visById.set(u.squadId, u.visualId); posById.set(u.squadId, u.pos);
    }
    const myUnits: Array<{ id: number; ptr: NativePointer }> = [];
    const enemies: Array<{ id: number; ptr: NativePointer }> = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        const ctrl = invokeBool(isCtrlByCurMi, [e, statePtr]);
        if (ctrl) {
            if (opts.unitId === undefined || opts.unitId === id) myUnits.push({ id, ptr: e });
        } else if (opts.targetId === undefined || opts.targetId === id) {
            enemies.push({ id, ptr: e });
        }
    });

    const abilBuf = Memory.alloc(4);
    const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
    const optsBuf = Memory.alloc(0x30);
    for (let k = 0; k < 0x30; k += 4) optsBuf.add(k).writeU32(0);
    if (overrideRange !== null) {
        optsBuf.add(0x4).writeU8(1); optsBuf.add(0x8).writeS32(overrideRange);
    }

    let removeMi: { info: NativePointer; ptr: NativePointer } | null = null;
    let addMi: { info: NativePointer; ptr: NativePointer } | null = null;
    let setResolved = false;
    let removeWorks: boolean | null = null;
    const units: UnitAttackPlan[] = [];
    // DamagePrediction (best-effort) : GetAllPredictions(unit, tile, ability)
    // → dict.get_Item(target) → struct (boxed+0x10). dpq résolu par le caller.
    const predMi = dpq.isNull() ? null
        : findMethodByParamCount(dpq.readPointer(), "GetAllPredictions", 3);
    let predItemMi: { info: NativePointer; ptr: NativePointer } | null = null;

    for (const u of myUnits) {
        const abilities = (manualAbility !== null)
            ? [{ id: manualAbility,
                 name: abilityName(manualAbility) ?? "id:" + manualAbility, kind: "manual" }]
            : unitAbilityTypes(u.ptr, allAbilities);
        const mainTile = getUnitMainTile(u.ptr, statePtr);
        const currentTile = mainTile.isNull() ? null : readTileCoord(mainTile);
        const evals: AttackEval[] = [];
        for (const ab of abilities) {
            abilBuf.writeS32(ab.id);
            for (const tgt of enemies) {
                let set: NativePointer;
                try {
                    set = invokeMethod(getMovableTilesMi!.info, movementQuery,
                        [u.ptr, boolFalse, optsBuf]);
                } catch (e) {
                    evals.push({ targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                        targetPos: posById.get(tgt.id) ?? null, abilityId: ab.id,
                        ability: ab.name, kind: ab.kind, movableCount: 0, rankCount: 0,
                        ranked: [], err: "movable: " + (e as Error).message });
                    continue;
                }
                if (set.isNull()) {
                    evals.push({ targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                        targetPos: posById.get(tgt.id) ?? null, abilityId: ab.id,
                        ability: ab.name, kind: ab.kind, movableCount: 0, rankCount: 0,
                        ranked: [], err: "movable null" });
                    continue;
                }
                if (!setResolved) {
                    removeMi = findMethodByParamCount(set.readPointer(), "Remove", 1);
                    addMi = findMethodByParamCount(set.readPointer(), "Add", 1);
                    setResolved = true;
                }
                gcRoot.add(set);
                let err: string | null = null;
                if (!mainTile.isNull() && addMi) {
                    try { invokeMethod(addMi.info, set, [mainTile]); } catch { /* */ }
                }
                const movableCount = extractTilePtrs(set).length;
                const ranked: RankedTile[] = [];
                try {
                    for (let r = 0; r < maxRank; r++) {
                        const best = invokeMethod(getBestMi.info, attackQuery,
                            [u.ptr, set, tgt.ptr, abilBuf]);
                        if (best.isNull()) break;
                        const coord = readTileCoord(best);
                        const entry: RankedTile = { col: coord.col, row: coord.row };
                        // Prédiction de dégâts en atterrissant sur `best` contre tgt.
                        if (predMi && !dpq.isNull()) {
                            try {
                                const dict = invokeMethod(predMi.info, dpq,
                                    [u.ptr, best, abilBuf]);
                                if (!dict.isNull()) {
                                    if (!predItemMi) {
                                        predItemMi = findMethodByParamCount(
                                            dict.readPointer(), "get_Item", 1);
                                    }
                                    if (predItemMi) {
                                        const boxed = invokeMethod(
                                            predItemMi.info, dict, [tgt.ptr]);
                                        if (!boxed.isNull()) {
                                            const bb = boxed.add(0x10);
                                            const hp = bb.readS32();
                                            entry.dmgMin = bb.add(0x60).readS32();
                                            entry.dmgMax = bb.add(0x64).readS32();
                                            // kill = possible (max>=hp) ; killSure
                                            // = garanti (min>=hp, indépendant du roll).
                                            entry.kill = (entry.dmgMax ?? 0) >= hp;
                                            entry.killSure = (entry.dmgMin ?? 0) >= hp;
                                            entry.mightCrit = bb.add(0xb1).readU8() !== 0;
                                        }
                                    }
                                }
                            } catch { /* prédiction best-effort */ }
                        }
                        ranked.push(entry);
                        if (!removeMi) { err = "Remove not resolved (rang tronqué à 1)"; break; }
                        const removed = invokeMethod(removeMi.info, set, [best]);
                        const ok = !removed.isNull() && removed.add(0x10).readU8() !== 0;
                        if (ok) { removeWorks = true; }
                        else { err = "Remove a renvoyé false (stop)"; break; }
                    }
                } catch (e) { err = (e as Error).message; }
                finally { try { gcRoot.remove(set); } catch { /* */ } }
                evals.push({ targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                    targetPos: posById.get(tgt.id) ?? null, abilityId: ab.id,
                    ability: ab.name, kind: ab.kind, movableCount,
                    rankCount: ranked.length, ranked, err });
            }
        }
        units.push({ unitId: u.id, visualId: visById.get(u.id) ?? null,
            pos: posById.get(u.id) ?? null, currentTile, abilities, evals });
    }
    return { units, enemyCount: enemies.length, removeWorks };
}

export interface FullUnit {
    id: number; visualId: string | null;
    pos: { col: number; row: number } | null;
    hp: number | null; owner: number | null; team: number | null;
    alive: boolean; ctrl: boolean; hasAction: boolean; ranged: boolean;
    abilities: Array<{ id: number; name: string; kind: string }>;
}

/** Projection de TOUTES les units (2 camps) : flags vivants + abilities concrètes. */
export function projectUnitsFull(statePtr: NativePointer, allAbilities: boolean): FullUnit[] {
    const proj = projectMatchState(statePtr);
    const base = new Map<number, (typeof proj.units)[number]>();
    for (const u of proj.units) base.set(u.squadId, u);
    const out: FullUnit[] = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        const b = base.get(id);
        out.push({
            id, visualId: b?.visualId ?? null, pos: b?.pos ?? null,
            hp: b?.hp ?? null, owner: b?.ownerId ?? null, team: b?.teamId ?? null,
            alive: invokeBool(isAliveMi, [e, statePtr]),
            ctrl: invokeBool(isCtrlByCurMi, [e, statePtr]),
            hasAction: invokeBool(hasActionLeftMi, [e]),
            ranged: invokeBool(isRangedMi, [e]),
            abilities: unitAbilityTypes(e, allAbilities),
        });
    });
    return out;
}

export interface FullMow {
    /** Platform entityId (ancre sur la grille). */
    id: number;
    /** Machine entityId — porte HP/owner/abilities ; = casterId pour applyAction. */
    machineId: number;
    casterId: number;
    visualId: string | null;
    pos: { col: number; row: number } | null;
    hp: number | null; maxHp: number | null;
    owner: number | null; team: number | null;
    alive: boolean; ctrl: boolean; hasAction: boolean;
    /** Slot de déploiement (MachineOfWarPosition : 1=Top, 2=Bottom) — les MoW
     *  n'ont pas de (col,row) propre, juste un slot mappé aux tiles du board. */
    slot: number | null;
    abilities: Array<{ id: number; name: string; kind: string }>;
}

/** Projection des MoW (MachinePlatform/Machine) prête pour l'oracle. Les MoW ne
 *  bougent pas (ability-only) → pas de plan de move. La projection `proj.mows`
 *  porte déjà pos/hp/owner/team ; on enrichit ici les flags vivants + abilities
 *  concrètes lues sur l'entité Machine (Type 6, porteuse des abilities). Le
 *  casterId pour `applyAction {kind:"ability"}` = machineId. */
export function projectMowsFull(
    statePtr: NativePointer, proj: ReturnType<typeof projectMatchState>,
): FullMow[] {
    const mows = proj.mows ?? [];
    if (mows.length === 0) return [];
    const machinePtr = new Map<number, NativePointer>();
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty === EntityType.Machine) machinePtr.set(id, e);
    });
    const out: FullMow[] = [];
    for (const m of mows) {
        const e = machinePtr.get(m.machineId);
        out.push({
            id: m.id, machineId: m.machineId, casterId: m.machineId,
            visualId: m.visualId, pos: m.pos,
            hp: m.hp, maxHp: m.maxHp, owner: m.ownerId, team: m.teamId,
            alive: e ? invokeBool(isAliveMi, [e, statePtr]) : !m.isDead,
            ctrl: e ? invokeBool(isCtrlByCurMi, [e, statePtr]) : false,
            hasAction: e ? invokeBool(hasActionLeftMi, [e]) : false,
            slot: m.initialSlot,
            abilities: e ? mowAbilityTypes(e) : [],
        });
    }
    return out;
}

/** Danger zone = tiles que les ENNEMIS du joueur courant peuvent frapper au
 *  prochain tour (move ∪ portée d'attaque), agrégées. Read-only. */
export function computeDangerZone(
    statePtr: NativePointer, movementQuery: NativePointer, attackQuery: NativePointer,
): {
    tileCount: number; tiles: Array<{ col: number; row: number }>;
    byEnemy: Array<{ enemyId: number; threatCount: number }>;
} {
    const getAllTilesMi = findMethodByParamCount(
        attackQuery.readPointer(), "GetAllTilesInAbilityRange", 3);
    const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
    const incTrue = Memory.alloc(1); incTrue.writeU8(1);
    const optsBuf = Memory.alloc(0x30);
    for (let k = 0; k < 0x30; k += 4) optsBuf.add(k).writeU32(0);
    const union = new Set<string>();
    const byEnemy: Array<{ enemyId: number; threatCount: number }> = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        if (invokeBool(isCtrlByCurMi, [e, statePtr])) return; // ennemis seulement
        let threat: Array<{ col: number; row: number }> = [];
        try {
            const os = invokeMethod(getMovableTilesMi!.info, movementQuery,
                [e, boolFalse, optsBuf]);
            if (!os.isNull() && getAllTilesMi) {
                const tos = invokeMethod(getAllTilesMi.info, attackQuery, [e, os, incTrue]);
                threat = extractTiles(tos);
            }
        } catch { /* */ }
        for (const t of threat) union.add(t.col + "," + t.row);
        byEnemy.push({ enemyId: id, threatCount: threat.length });
    });
    return {
        tileCount: union.size,
        tiles: [...union].map((k) => {
            const [c, r] = k.split(",").map(Number); return { col: c, row: r };
        }),
        byEnemy,
    };
}

/** Dump RE : champs (nom/offset/type) d'une classe + parents (cap 4 niveaux).
 *  Sert à localiser HP/abilities/position sur des entités atypiques (MoW). */
export function classFieldsDump(
    klass: NativePointer,
): Array<{ name: string; offset: number; type: string }> {
    const out: Array<{ name: string; offset: number; type: string }> = [];
    let k = klass; let depth = 0;
    while (!k.isNull() && depth < 4) {
        try {
            const iter = Memory.alloc(Process.pointerSize);
            iter.writePointer(ptr(0));
            for (;;) {
                const f = class_get_fields(k, iter) as NativePointer;
                if (f.isNull()) break;
                let type = "?";
                try {
                    const tc = type_get_class_or_element_class(
                        field_get_type(f) as NativePointer) as NativePointer;
                    if (!tc.isNull()) type = s(class_get_name(tc) as NativePointer);
                } catch { /* */ }
                out.push({
                    name: s(field_get_name(f) as NativePointer),
                    offset: field_get_offset(f) as number, type,
                });
            }
        } catch { /* */ }
        k = class_get_parent(k) as NativePointer;
        depth++;
    }
    return out;
}
