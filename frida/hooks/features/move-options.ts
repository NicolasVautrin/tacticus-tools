// move-options — capture les sets de tiles atteignables retournés par
// `IdunBattle.Core.Services.MovementQuery.GetMovableTilesFor`.
//
// Step 2 : enrichi avec contexte runner + unit + turn + MovementOptions
// pour pouvoir joindre chaque event avec (battle, turn, unit) dans la DB.
//
// L'idée clé pour Mode A (CheatRunAIMessage joue toutes les units en un
// Apply) vs Mode B (engine RL dispatch unit par unit) : on stamp chaque
// fire avec `applySeq` (window de l'Apply en cours) + `unitEntityId`
// (l'unit scorée). Le couple (applySeq, unitEntityId) identifie une
// "décision logique" dans les deux modes.
//
// Static analysis (data/dumps/rmvdp0v56c/dump.cs:418636) :
//   RVA: 0x11169C0 Slot: 4
//   public IOrderedSet<IEntity> GetMovableTilesFor(
//       IEntity unit, bool ignoreUnitFlags, MovementOptions options);
//
// MovementOptions struct (24 bytes, x64 ABI: passé par référence) :
//   +0x0  IgnoreSpecialMovement: bool
//   +0x1  IgnoreUnitsOnTiles:    bool
//   +0x2  IsDangerZone:          bool
//   +0x4  OverrideRange:         Nullable<int>      (HasValue@4, Value@8)
//   +0x10 OverrideRangeBonus:    Nullable<RangeBonus>

import { findClass, findMethodByParamCount } from "../il2cpp/helpers.js";
import { emit, readEntityId } from "./ai-trace/state.js";
import { state } from "../game/state.js";
import { runnerOff } from "../game/runner.js";
import {
    readTurnInfo, forEachComponent, positionComponentClass,
} from "../game/match-state.js";
import { getRunner as getRegistryRunner } from "../game/runner-registry.js";
import { Ctx } from "../controller.js";

// PositionComponent layout (cf. match-state.ts: COMP_FIELD.posCol/posRow) :
//   Coordinate.Column @ +0x10
//   Coordinate.Row    @ +0x14
const POS_COL_OFF = 0x10;
const POS_ROW_OFF = 0x14;

// OrderedSet<IEntity> extends List<IEntity>. List<T> IL2CPP layout :
//   +0x10  _items : T[]
//   +0x18  _size  : int
// T[] (managed array) layout :
//   +0x18  max_length : int
//   +0x20  items[0]
const LIST_ITEMS_OFF = 0x10;
const LIST_SIZE_OFF = 0x18;
const ARRAY_FIRST_ITEM_OFF = 0x20;

/** Cache tile_ptr → (col, row). Les tiles ne bougent pas dans une battle
 * → après la première résolution via forEachComponent, on hit le cache.
 * Bornage modeste (10k entries max) — au-delà on évacue tout (les tiles
 * resservent rarement après une vidange complète d'une nouvelle battle). */
const tileCoordCache: Map<string, { col: number; row: number }> = new Map();
const TILE_COORD_CACHE_MAX = 10000;

function getTileCoord(tile: NativePointer): {
    col: number; row: number;
} {
    if (!positionComponentClass) return { col: -1, row: -1 };
    const key = tile.toString();
    const hit = tileCoordCache.get(key);
    if (hit) return hit;
    let col = -1, row = -1;
    try {
        forEachComponent(tile, (comp, klass) => {
            if (!klass.equals(positionComponentClass!)) return;
            try { col = comp.add(POS_COL_OFF).readS32(); }
            catch { /* leave -1 */ }
            try { row = comp.add(POS_ROW_OFF).readS32(); }
            catch { /* leave -1 */ }
        });
    } catch { /* leave -1 */ }
    if (tileCoordCache.size >= TILE_COORD_CACHE_MAX) {
        tileCoordCache.clear();
    }
    const coord = { col, row };
    tileCoordCache.set(key, coord);
    return coord;
}

/** Itère l'OrderedSet<IEntity> retourné et renvoie la liste des tile
 * coordonnées. Borne le size par sécurité — un set normal contient au
 * plus quelques dizaines de tiles. */
function extractCandidates(orderedSet: NativePointer): Array<{
    col: number; row: number; entityId: number;
}> {
    const out: Array<{ col: number; row: number; entityId: number }> = [];
    if (orderedSet.isNull()) return out;
    let items: NativePointer;
    let size: number;
    try {
        items = orderedSet.add(LIST_ITEMS_OFF).readPointer();
        size = orderedSet.add(LIST_SIZE_OFF).readS32();
    } catch { return out; }
    if (items.isNull() || size <= 0 || size > 500) return out;
    for (let i = 0; i < size; i++) {
        let tile: NativePointer;
        try {
            tile = items.add(ARRAY_FIRST_ITEM_OFF + i * Process.pointerSize)
                .readPointer();
        } catch { continue; }
        if (tile.isNull()) continue;
        const entityId = readEntityId(tile);
        const c = getTileCoord(tile);
        out.push({ col: c.col, row: c.row, entityId });
    }
    return out;
}

let installed = false;
let armed = false;
let listener: InvocationListener | null = null;

// Dédup par (apply_seq, unit_entity_id, options-signature) : l'AI scoring
// re-call GetMovableTilesFor plusieurs fois pour le même unit dans le
// même Apply window — parfois avec DIFFERENT MovementOptions (scoring
// d'abilities qui modifient le range, etc.). On dédup les répétitions
// strictement identiques (même unit + mêmes options) mais on GARDE les
// variantes d'options (= sémantiquement différentes).
//
// Reset quand state.applySeq change → nouveau Set vide.
let dedupApplySeq = -1;
const dedupSeenKeys: Set<string> = new Set();

// Compteurs diagnostic.
let fires = 0;        // total fires (tous contextes confondus)
let firesLive = 0;    // origin === "live"
let firesBuild = 0;   // origin === number (build runner)
let firesOrphan = 0;  // scoringRunnerId === null (hors d'un Apply watched)
let firesNullRet = 0; // retval null (sanity check)

interface ResolvedTarget {
    klass: NativePointer | null;
    klassName: string;
    method: { ptr: NativePointer; info: NativePointer } | null;
    err: string | null;
}

function resolveTarget(): ResolvedTarget {
    const klass = findClass(
        "BattleLogicAssembly.dll",
        "IdunBattle.Core.Services", "MovementQuery");
    if (!klass) {
        return { klass: null, klassName: "MovementQuery",
            method: null,
            err: "MovementQuery class not found" };
    }
    // 3-param overload (Slot 4) — l'autre est 4-param (IList<IEntity>).
    const m = findMethodByParamCount(klass, "GetMovableTilesFor", 3);
    if (!m || m.ptr.isNull()) {
        return { klass, klassName: "MovementQuery", method: null,
            err: "GetMovableTilesFor(3 params) not found" };
    }
    return { klass, klassName: "MovementQuery", method: m, err: null };
}

let resolved: ResolvedTarget | null = null;

interface ParsedOptions {
    ignSpecial: boolean;
    ignUnits: boolean;
    isDanger: boolean;
    /** OverrideRange value (null if HasValue=false). */
    overrideRange: number | null;
    /** OverrideRangeBonus.HasValue (struct content lu seulement si true). */
    hasRangeBonus: boolean;
}

/** Lit le struct MovementOptions à l'adresse `p` (24 bytes). Layout dans
 * le commentaire de tête. Échec silencieux → renvoie null. */
function readMovementOptions(p: NativePointer): ParsedOptions | null {
    if (p.isNull()) return null;
    try {
        const ignSpecial = p.add(0x0).readU8() !== 0;
        const ignUnits   = p.add(0x1).readU8() !== 0;
        const isDanger   = p.add(0x2).readU8() !== 0;
        const overrideRangeHas = p.add(0x4).readU8() !== 0;
        const overrideRangeVal = overrideRangeHas
            ? p.add(0x8).readS32() : null;
        const hasRangeBonus = p.add(0x10).readU8() !== 0;
        return {
            ignSpecial, ignUnits, isDanger,
            overrideRange: overrideRangeVal,
            hasRangeBonus,
        };
    } catch { return null; }
}

/** Résout le runner ptr depuis le tag `scoringRunnerId`. */
function resolveScoringRunner(): NativePointer | null {
    const tag = state.scoringRunnerId;
    if (tag === null) return null;
    if (tag === "live") return state.liveRunner;
    try { return getRegistryRunner(tag).runner; }
    catch { return null; }
}

interface TurnInfo {
    player: number | null;
    round: number | null;
}

function readTurnFor(runner: NativePointer | null): TurnInfo {
    if (!runner) return { player: null, round: null };
    try {
        const sp = runner.add(runnerOff.state).readPointer();
        if (sp.isNull()) return { player: null, round: null };
        const ti = readTurnInfo(sp);
        return { player: ti.player, round: ti.round };
    } catch { return { player: null, round: null }; }
}

function install(): { ok: boolean; err?: string } {
    if (installed) return { ok: true };
    resolved = resolveTarget();
    if (!resolved.method) {
        return { ok: false, err: resolved.err ?? "unknown" };
    }
    listener = Interceptor.attach(resolved.method.ptr, {
        onEnter(args) {
            if (!armed) return;
            fires++;
            const runnerId = state.scoringRunnerId;
            // Bucket attribution.
            let bucket: "live" | "build" | "orphan";
            if (runnerId === "live") { firesLive++; bucket = "live"; }
            else if (typeof runnerId === "number") {
                firesBuild++; bucket = "build";
            } else { firesOrphan++; bucket = "orphan"; }

            const ctx = this as InvocationContext & {
                _mooEmit?: boolean;
                _mooFireNo?: number;
                _mooApplySeq?: number;
                _mooRunnerId?: "live" | number | null;
                _mooBucket?: "live" | "build" | "orphan";
                _mooUnitEntityId?: number;
                _mooUnitPtr?: string;
                _mooIgnoreFlags?: boolean;
                _mooOptions?: ParsedOptions | null;
                _mooTurn?: number | null;
                _mooTurnPlayer?: number | null;
            };

            // Hot-path : skip orphan fires (UI preview, mirror outside
            // captureMirrorMessages, …) — pas d'attribution possible.
            if (bucket === "orphan") return;

            // Read MovementOptions struct (passé par ptr en x64).
            const opts = readMovementOptions(args[3]);

            // Filter le SEUL noise pur : isDanger = UI preview, jamais
            // une décision d'AI. Les autres flags (override_range,
            // range_bonus, ign_units, ign_special) sont des scoring
            // d'abilities légitimes (Warboss active, Royal Warden buff,
            // Deep Strike, etc.) — on les garde.
            if (opts && opts.isDanger) return;

            // Dédup signature = unit_entity_id + options.
            // On garde la 1ère fire pour chaque (unit, options-tuple) dans
            // l'apply window. Permet de capturer les différents scenarios
            // d'abilities sans dupliquer les répétitions strictes.
            const unitEid = readEntityId(args[1]);
            const optSig = opts
                ? [opts.ignSpecial ? 1 : 0,
                   opts.ignUnits ? 1 : 0,
                   opts.overrideRange ?? "n",
                   opts.hasRangeBonus ? 1 : 0].join("|")
                : "noopts";
            const dedupKey = unitEid + ":" + optSig;
            if (state.applySeq !== dedupApplySeq) {
                dedupApplySeq = state.applySeq;
                dedupSeenKeys.clear();
            }
            if (dedupSeenKeys.has(dedupKey)) return;
            dedupSeenKeys.add(dedupKey);

            // Resolve turn info for this runner.
            const runner = resolveScoringRunner();
            const turn = readTurnFor(runner);

            // Stash le contexte sur `this` ; l'emit (avec candidates) se
            // fait en onLeave pour avoir le retval.
            ctx._mooEmit = true;
            ctx._mooFireNo = fires;
            ctx._mooApplySeq = state.applySeq;
            ctx._mooRunnerId = runnerId;
            ctx._mooBucket = bucket;
            ctx._mooUnitEntityId = unitEid;
            ctx._mooUnitPtr = args[1].toString();
            ctx._mooIgnoreFlags = (args[2].toUInt32() & 1) !== 0;
            ctx._mooOptions = opts;
            ctx._mooTurn = turn.round;
            ctx._mooTurnPlayer = turn.player;
        },
        onLeave(retval) {
            if (!armed) return;
            if (retval.isNull()) firesNullRet++;
            const ctx = this as InvocationContext & {
                _mooEmit?: boolean;
                _mooFireNo?: number;
                _mooApplySeq?: number;
                _mooRunnerId?: "live" | number | null;
                _mooBucket?: "live" | "build" | "orphan";
                _mooUnitEntityId?: number;
                _mooUnitPtr?: string;
                _mooIgnoreFlags?: boolean;
                _mooOptions?: ParsedOptions | null;
                _mooTurn?: number | null;
                _mooTurnPlayer?: number | null;
            };
            if (!ctx._mooEmit) return;
            const candidates = extractCandidates(retval);
            emit({
                evt: "move_options",
                fireNo: ctx._mooFireNo,
                applySeq: ctx._mooApplySeq,
                runnerId: ctx._mooRunnerId,
                bucket: ctx._mooBucket,
                turn: ctx._mooTurn,
                turnPlayer: ctx._mooTurnPlayer,
                unitEntityId: ctx._mooUnitEntityId,
                unitPtr: ctx._mooUnitPtr,
                ignoreFlags: ctx._mooIgnoreFlags,
                options: ctx._mooOptions,
                candidatesCount: candidates.length,
                candidates,
            });
        },
    });
    Interceptor.flush();
    installed = true;
    return { ok: true };
}

function counters(): Record<string, unknown> {
    return {
        installed, armed,
        fires, firesLive, firesBuild, firesOrphan, firesNullRet,
        klass: resolved?.klassName ?? null,
        methodPtr: resolved?.method?.ptr.toString() ?? null,
        err: resolved?.err ?? null,
    };
}

// Note : le set de `state.scoringRunnerId` + l'increment de `state.applySeq`
// + le push de l'apply frame est désormais fait par `message-trace.ts`.
// move-options en consomme la valeur, ne la set plus.

export function register(ctx: Ctx): void {
    ctx.rpc.armMoveOptionsTrace = () => {
        const r = install();
        if (!r.ok) return { ok: false, err: r.err, counters: counters() };
        armed = true;
        return { ok: true, counters: counters() };
    };

    ctx.rpc.disarmMoveOptionsTrace = () => {
        armed = false;
        return { ok: true, counters: counters() };
    };

    ctx.rpc.moveOptionsTraceStatus = () => counters();

    ctx.rpc.moveOptionsTraceReset = () => {
        fires = 0;
        firesLive = 0;
        firesBuild = 0;
        firesOrphan = 0;
        firesNullRet = 0;
        return { ok: true, counters: counters() };
    };

    void listener;
}
