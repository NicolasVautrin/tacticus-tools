import {
    class_get_name, class_get_namespace, findMethod, findMethodByParamCount, s,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import { runnerOff } from "../../game/runner.js";
import { getRunner } from "../../game/runner-registry.js";
import {
    EntityType, forEachComponent, forEachEntity, projectMatchState,
    readBattleStatus,
} from "../../game/match-state.js";
import { readEffectsByUnit } from "../../game/effects.js";
import { state } from "../../game/state.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { abilityName } from "../../data/ability-names.js";
import { Ctx } from "../../controller.js";
import {
    ActionResult, ActionSpec, activeAbilityMsgClass, applyOneAction,
    attackQueryOff, dpqInServicesOff, extractTiles, extractTilePtrs,
    finishUnitTurnMsgClass, getMovableTilesMi, getUnitMainTile, invokeBool,
    isAliveMi, isCtrlByCurMi, moveUnitMsgClass, movementQueryOff, readTileCoord,
    resolveDpq, servicesOff, summarize, unitAbilityTypes,
} from "./internals.js";
import { applyAiMsgMi } from "../../game/ai-control.js";
import {
    classFieldsDump, computeAttackPlans, computeDangerZone, computeExposure,
    projectMowsFull, projectUnitsFull,
} from "./projection.js";

export function registerView(ctx: Ctx): void {
    /** DRY-RUN des tiles atteignables : pour chaque squad contrôlé+vivant du
     *  joueur courant, appelle `MovementQuery.GetMovableTilesFor(unit, false, {})`
     *  et extrait l'ensemble des tiles légales — SANS muter. Une deep-strike
     *  unit (TeleportStrike) aura un ensemble plus large (téléport). body:
     *  { runnerId } */
    ctx.rpc.aiMovableTiles = (
        body?: {
            runnerId?: number;
            side?: "friendly" | "enemy" | "all";
            dangerZone?: boolean;
            threat?: boolean;
            extraRange?: number;     // OverrideRangeBonus.ExtraRange (+N, buff)
            overrideRange?: number;  // OverrideRange (absolu, sûr)
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        const side = body?.side ?? "friendly";
        const dangerZone = body?.dangerZone === true;
        const threat = body?.threat === true;
        const extraRange = (typeof body?.extraRange === "number")
            ? (body.extraRange | 0) : 0;
        const overrideRange = (typeof body?.overrideRange === "number")
            ? (body.overrideRange | 0) : null;
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getMovableTilesMi) {
            return { ok: false, error: "GetMovableTilesFor(3) not resolved" };
        }
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status.stageName ?? status.stage) };
        }
        const playerId = status.currentTurnPlayer;
        const movementQuery = runner.add(movementQueryOff).readPointer();
        if (movementQuery.isNull()) {
            return { ok: false, error: "MovementQuery null on runner" };
        }
        const attackQuery = runner.add(attackQueryOff).readPointer();
        let getAllTilesMi: { info: NativePointer; ptr: NativePointer } | null = null;

        const proj = projectMatchState(statePtr);
        const visById = new Map<number, string | null>();
        const posById = new Map<number, { col: number; row: number } | null>();
        for (const u of proj.units) {
            visById.set(u.squadId, u.visualId);
            posById.set(u.squadId, u.pos);
        }

        const before = summarize(statePtr);
        const results: Array<{
            unitId: number; visualId: string | null;
            pos: { col: number; row: number } | null;
            tileCount: number; tiles: Array<{ col: number; row: number }>;
            threatCount: number; threatTiles: Array<{ col: number; row: number }>;
            err: string | null;
        }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit) return;
            if (!invokeBool(isAliveMi, [e, statePtr])) return;
            const ctrl = invokeBool(isCtrlByCurMi, [e, statePtr]);
            if (side === "friendly" && !ctrl) return;
            if (side === "enemy" && ctrl) return;
            const boolBuf = Memory.alloc(1); boolBuf.writeU8(0);
            // MovementOptions = 0x30 octets (Nullable<RangeBonus> @0x10).
            const optsBuf = Memory.alloc(0x30);
            for (let k = 0; k < 0x30; k += 4) optsBuf.add(k).writeU32(0);
            // MovementOptions.IsDangerZone @0x2 — ce que l'UI passe pour la
            // surbrillance rouge (menace : déplacement + portée d'attaque).
            if (dangerZone) optsBuf.add(0x2).writeU8(1);
            // OverrideRange (Nullable<int> @0x4 : hasValue@0x4, value@0x8) — absolu.
            if (overrideRange !== null) {
                optsBuf.add(0x4).writeU8(1);
                optsBuf.add(0x8).writeS32(overrideRange);
            }
            // OverrideRangeBonus (Nullable<RangeBonus> @0x10) — le VRAI champ
            // d'un buff de move (Warboss actif, Sibyll/Makothep) :
            //   hasValue@0x10 · RangeBonus.ExtraRange@0x18 ·
            //   ExtraRangeCondition(Func)@0x20=null (→ inconditionnel) ·
            //   ReduceRange(Nullable<int>)@0x28=0.
            if (extraRange !== 0) {
                optsBuf.add(0x10).writeU8(1);
                optsBuf.add(0x18).writeS32(extraRange);
            }
            let tiles: Array<{ col: number; row: number }> = [];
            let threatTiles: Array<{ col: number; row: number }> = [];
            let err: string | null = null;
            try {
                const os = invokeMethod(
                    getMovableTilesMi!.info, movementQuery, [e, boolBuf, optsBuf]);
                tiles = extractTiles(os);
                // Menace = move ∪ portée d'attaque depuis ces tiles :
                // AttackQuery.GetAllTilesInAbilityRange(unit, moveTiles, true).
                if (threat && !attackQuery.isNull() && !os.isNull()) {
                    if (!getAllTilesMi) {
                        getAllTilesMi = findMethodByParamCount(
                            attackQuery.readPointer(),
                            "GetAllTilesInAbilityRange", 3);
                    }
                    if (getAllTilesMi) {
                        const incBuf = Memory.alloc(1); incBuf.writeU8(1);
                        const tos = invokeMethod(
                            getAllTilesMi.info, attackQuery, [e, os, incBuf]);
                        threatTiles = extractTiles(tos);
                    }
                }
            } catch (ex) { err = (ex as Error).message; }
            results.push({
                unitId: id, visualId: visById.get(id) ?? null,
                pos: posById.get(id) ?? null,
                tileCount: tiles.length, tiles,
                threatCount: threatTiles.length, threatTiles,
                err,
            });
        });
        const after = summarize(statePtr);
        // Union (danger zone agrégée) — sur la menace si threat, sinon le move.
        const unionKeys = new Set<string>();
        for (const r of results) {
            const src = threat ? r.threatTiles : r.tiles;
            for (const t of src) unionKeys.add(t.col + "," + t.row);
        }
        return {
            ok: true, runner: label, playerId, side, dangerZone,
            mutated: before.sig !== after.sig,
            unionTileCount: unionKeys.size,
            unionTiles: [...unionKeys].map((k) => {
                const [c, r] = k.split(",").map(Number);
                return { col: c, row: r };
            }),
            unitCount: results.length, units: results,
        };
    });

    /** RANKING des tiles d'attaque par (unit, target) — shrink-and-recall sur
     *  `AttackQuery.GetBestTileToAttackFrom(unit, movableSet, target, ability)`.
     *  GetBestTileToAttackFrom rend l'argmax de l'utilité IA (1 tile) parmi les
     *  positions LÉGALES d'où `unit` peut attaquer `target` avec `ability`. On
     *  retire cette tile du set et on rappelle → 2e meilleure, etc. Donne, par
     *  ennemi ciblable, la LISTE RANKÉE des positions d'attaque (fallback quand
     *  2 units se disputent une tile : l'unité battue prend sa tile suivante).
     *  Read-only sur l'état (on ne mute qu'un IOrderedSet transient créé par
     *  GetMovableTilesFor, pas le MatchState). Signature C# (dump kqkbjqfb6c) :
     *    IEntity GetBestTileToAttackFrom(IEntity unit, IOrderedSet<IEntity> tiles,
     *                                    IEntity target, ActiveAbilityType ability)
     *  AUTONOME : si `abilityType` n'est pas fourni, on lit les abilities
     *  CONCRÈTES de chaque unité (NormalAttackType + GetActives si allAbilities) —
     *  l'attaque normale a un id typé par unité (ex. Loki_NormalAttack=69), pas
     *  l'abstrait 17. La tile COURANTE de l'unité (GetMainTile) est ajoutée au set
     *  candidat (GetMovableTilesFor l'exclut → sinon « rester sur place et
     *  attaquer » manquerait au ranking).
     *  body: { runnerId, unitId?, targetId?, abilityType?, allAbilities?=false,
     *          maxRank?=8, overrideRange? } — unitId/targetId absents = toutes les
     *  units/ennemis ; abilityType absent = abilities réelles de chaque unité. */
    ctx.rpc.aiAttackRank = (
        body?: {
            runnerId?: number; unitId?: number; targetId?: number;
            abilityType?: number; allAbilities?: boolean;
            maxRank?: number; overrideRange?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        const manualAbility = (typeof body?.abilityType === "number")
            ? (body.abilityType | 0) : null;
        const allAbilities = body?.allAbilities === true;
        const maxRank = (typeof body?.maxRank === "number" && body.maxRank > 0)
            ? (body.maxRank | 0) : 8;
        // Diag : portée de move forcée (Nullable<int> @0x4) — géante = toute la
        // map atteignable, isole « hors portée » de « ability non résolue ».
        const overrideRange = (typeof body?.overrideRange === "number")
            ? (body.overrideRange | 0) : null;
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getMovableTilesMi) {
            return { ok: false, error: "GetMovableTilesFor(3) not resolved" };
        }
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status.stageName ?? status.stage) + " (need Running)" };
        }
        const playerId = status.currentTurnPlayer;
        const movementQuery = runner.add(movementQueryOff).readPointer();
        if (movementQuery.isNull()) return { ok: false, error: "MovementQuery null" };
        const attackQuery = runner.add(attackQueryOff).readPointer();
        if (attackQuery.isNull()) return { ok: false, error: "AttackQuery null" };

        // GetBestTileToAttackFrom(unit, tiles, target, ability) — 4 params logiques.
        const getBestMi = findMethodByParamCount(
            attackQuery.readPointer(), "GetBestTileToAttackFrom", 4);
        if (!getBestMi) {
            return { ok: false, error: "GetBestTileToAttackFrom(4) not resolved on "
                + s(class_get_name(attackQuery.readPointer()) as NativePointer) };
        }

        // Identité (visualId/pos) pour lisibilité.
        const proj = projectMatchState(statePtr);
        const visById = new Map<number, string | null>();
        const posById = new Map<number, { col: number; row: number } | null>();
        for (const u of proj.units) {
            visById.set(u.squadId, u.visualId);
            posById.set(u.squadId, u.pos);
        }

        // Units à ranker (contrôlées+vivantes) et cibles ennemies (vivantes).
        const myUnits: Array<{ id: number; ptr: NativePointer }> = [];
        const enemies: Array<{ id: number; ptr: NativePointer }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit) return;
            if (!invokeBool(isAliveMi, [e, statePtr])) return;
            const ctrl = invokeBool(isCtrlByCurMi, [e, statePtr]);
            if (ctrl) {
                if (body?.unitId === undefined || body.unitId === id) {
                    myUnits.push({ id, ptr: e });
                }
            } else if (body?.targetId === undefined || body.targetId === id) {
                enemies.push({ id, ptr: e });
            }
        });

        // Args value-type : ability (int) réécrit par eval ; bool false.
        const abilBuf = Memory.alloc(4);
        const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
        // MovementOptions = 0x30 octets, tout à zéro (pas de buff/override).
        const optsZero = Memory.alloc(0x30);
        for (let k = 0; k < 0x30; k += 4) optsZero.add(k).writeU32(0);
        if (overrideRange !== null) {
            optsZero.add(0x4).writeU8(1);
            optsZero.add(0x8).writeS32(overrideRange);
        }

        // Remove/Add(IEntity) sur l'IOrderedSet (résolus lazy depuis sa classe runtime).
        let removeMi: { info: NativePointer; ptr: NativePointer } | null = null;
        let addMi: { info: NativePointer; ptr: NativePointer } | null = null;
        let setResolved = false;
        let removeWorks: boolean | null = null;

        const before = summarize(statePtr);
        const t0 = Date.now();
        interface AttackEval {
            targetId: number; targetVis: string | null;
            targetPos: { col: number; row: number } | null;
            abilityId: number; ability: string; kind: string;
            movableCount: number; rankCount: number;
            ranked: Array<{ col: number; row: number }>; err: string | null;
        }
        const results: Array<{
            unitId: number; visualId: string | null;
            pos: { col: number; row: number } | null;
            currentTile: { col: number; row: number } | null;
            abilities: Array<{ id: number; name: string; kind: string }>;
            evals: AttackEval[];
        }> = [];

        for (const u of myUnits) {
            // Abilities concrètes à ranker : override manuel sinon auto-découverte.
            const abilities = (manualAbility !== null)
                ? [{ id: manualAbility,
                     name: abilityName(manualAbility) ?? "id:" + manualAbility,
                     kind: "manual" }]
                : unitAbilityTypes(u.ptr, allAbilities);
            // Tile courante (ajoutée au set candidat = option « rester sur place »).
            const mainTile = getUnitMainTile(u.ptr, statePtr);
            const currentTile = mainTile.isNull() ? null : readTileCoord(mainTile);
            const evals: AttackEval[] = [];

            for (const ab of abilities) {
                abilBuf.writeS32(ab.id);
                for (const tgt of enemies) {
                    // Set FRAIS (mutable) pour CE triplet (unit, ability, target).
                    let set: NativePointer;
                    try {
                        set = invokeMethod(
                            getMovableTilesMi.info, movementQuery,
                            [u.ptr, boolFalse, optsZero]);
                    } catch (e) {
                        evals.push({
                            targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                            targetPos: posById.get(tgt.id) ?? null,
                            abilityId: ab.id, ability: ab.name, kind: ab.kind,
                            movableCount: 0, rankCount: 0, ranked: [],
                            err: "movable: " + (e as Error).message });
                        continue;
                    }
                    if (set.isNull()) {
                        evals.push({
                            targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                            targetPos: posById.get(tgt.id) ?? null,
                            abilityId: ab.id, ability: ab.name, kind: ab.kind,
                            movableCount: 0, rankCount: 0, ranked: [], err: "movable null" });
                        continue;
                    }
                    if (!setResolved) {
                        removeMi = findMethodByParamCount(set.readPointer(), "Remove", 1);
                        addMi = findMethodByParamCount(set.readPointer(), "Add", 1);
                        setResolved = true;
                    }
                    gcRoot.add(set);
                    let err: string | null = null;
                    // Ajoute la tile courante au set candidat (Add idempotent).
                    if (!mainTile.isNull() && addMi) {
                        try { invokeMethod(addMi.info, set, [mainTile]); }
                        catch { /* */ }
                    }
                    const movableCount = extractTilePtrs(set).length;
                    const ranked: Array<{ col: number; row: number }> = [];
                    try {
                        for (let r = 0; r < maxRank; r++) {
                            const best = invokeMethod(
                                getBestMi.info, attackQuery,
                                [u.ptr, set, tgt.ptr, abilBuf]);
                            if (best.isNull()) break;  // plus de position d'attaque
                            ranked.push(readTileCoord(best));
                            if (!removeMi) {
                                err = "Remove not resolved (rang tronqué à 1)"; break;
                            }
                            const removed = invokeMethod(removeMi.info, set, [best]);
                            const ok = !removed.isNull() && removed.add(0x10).readU8() !== 0;
                            if (ok) { removeWorks = true; }
                            else { err = "Remove a renvoyé false (stop)"; break; }
                        }
                    } catch (e) { err = (e as Error).message; }
                    finally { try { gcRoot.remove(set); } catch { /* */ } }
                    evals.push({
                        targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                        targetPos: posById.get(tgt.id) ?? null,
                        abilityId: ab.id, ability: ab.name, kind: ab.kind,
                        movableCount, rankCount: ranked.length, ranked, err,
                    });
                }
            }
            results.push({
                unitId: u.id, visualId: visById.get(u.id) ?? null,
                pos: posById.get(u.id) ?? null, currentTile, abilities, evals,
            });
        }
        const after = summarize(statePtr);
        return {
            ok: true, runner: label, playerId,
            abilityMode: manualAbility !== null
                ? "manual:" + manualAbility
                : (allAbilities ? "auto+actives" : "auto-normal"),
            maxRank, overrideRange,
            mutated: before.sig !== after.sig, removeWorks,
            ms: Date.now() - t0,
            unitCount: results.length, enemyCount: enemies.length, units: results,
        };
    });

    /** decisionView — LA vue décision-ready en UN appel (couche DYNAMIQUE de
     *  l'oracle). Agrège : méta (stage/tour/joueur courant) ; TOUTES les units
     *  (pos hex/HP/team/owner/alive/ctrl/hasAction/ranged/abilities concrètes) ;
     *  les units à activer ; les plans d'attaque rankés du joueur courant
     *  (computeAttackPlans, normal attack par défaut) ; la DANGER ZONE ennemie.
     *  Read-only (mutated=false attendu). Python merge ensuite avec board.py
     *  (terrain/hex) + gameconfig.py (kits) + wiki (tactique).
     *  body: { runnerId, maxRank?=6, allAbilities?=false } */
    ctx.rpc.decisionView = (
        body?: { runnerId?: number; maxRank?: number; allAbilities?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        const allAbilities = body?.allAbilities === true;
        const maxRank = (typeof body?.maxRank === "number" && body.maxRank > 0)
            ? (body.maxRank | 0) : 6;
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getMovableTilesMi) {
            return { ok: false, error: "GetMovableTilesFor(3) not resolved" };
        }
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status.stageName ?? status.stage) + " (need Running)" };
        }
        const playerId = status.currentTurnPlayer;
        const movementQuery = runner.add(movementQueryOff).readPointer();
        if (movementQuery.isNull()) return { ok: false, error: "MovementQuery null" };
        const attackQuery = runner.add(attackQueryOff).readPointer();
        if (attackQuery.isNull()) return { ok: false, error: "AttackQuery null" };
        const getBestMi = findMethodByParamCount(
            attackQuery.readPointer(), "GetBestTileToAttackFrom", 4);
        if (!getBestMi) {
            return { ok: false, error: "GetBestTileToAttackFrom(4) not resolved" };
        }

        const before = summarize(statePtr);
        const t0 = Date.now();
        const proj = projectMatchState(statePtr);
        const units = projectUnitsFull(statePtr, allAbilities);
        const mows = projectMowsFull(statePtr, proj);
        // toActivate inclut les MoW jouables (ability-only) du joueur courant.
        const toActivate = [
            ...units.filter((u) => u.ctrl && u.alive && u.hasAction).map((u) => u.id),
            ...mows.filter((m) => m.ctrl && m.alive && m.hasAction).map((m) => m.casterId),
        ];
        const plans = computeAttackPlans(
            statePtr, movementQuery, attackQuery, getBestMi, resolveDpq(runner),
            { allAbilities, maxRank });
        const danger = computeDangerZone(statePtr, movementQuery, attackQuery);
        // Effets actifs par unité — lus depuis la liste native du jeu
        // (EffectsOwnedComponent.ActiveEffectIds), = ce que l'UI render en
        // icônes de statut. Attaché par unit/mow (railgun-mark, OW armé, Ice,
        // heal-block, Stun… surfacés sans scan ad-hoc — cf. game/effects.ts).
        const effectsByUnit = readEffectsByUnit(statePtr);
        const after = summarize(statePtr);
        return {
            ok: true, runner: label,
            stage: status.stage, stageName: status.stageName,
            turn: proj.turn, currentPlayer: playerId,
            mutated: before.sig !== after.sig, ms: Date.now() - t0,
            unitCount: units.length,
            units: units.map((u) => ({
                ...u, effects: effectsByUnit.get(u.id) ?? [],
            })),
            mowCount: mows.length,
            mows: mows.map((m) => ({
                ...m, effects: effectsByUnit.get(m.casterId) ?? [],
            })),
            toActivateCount: toActivate.length, toActivate,
            attackPlans: plans.units, removeWorks: plans.removeWorks,
            dangerZone: danger,
        };
    });

    /** exposureView — MOVE-GUARD (l'INVERSE de decisionView.attackPlans). Pour
     *  chaque MON unité contrôlée+vivante U, somme le dégât que les ENNEMIS peuvent
     *  lui infliger AU PROCHAIN TOUR (reach_dmg = Σ_E best(E→U), dégât fidèle via le
     *  prédicteur natif) → flag `exposed` = exposition LÉTALE possible AVEC une tuile
     *  sûre dispo (movable ∖ danger zone). Read-only. À appeler PRÉ-endturn (U déjà
     *  posé à sa tuile de fin de tour) pour le rapport/garde anti-over-extension.
     *  body: { runnerId, unitId?, allAbilities?=true } */
    ctx.rpc.exposureView = (
        body?: {
            runnerId?: number; unitId?: number; allAbilities?: boolean;
            victimsOffTurn?: boolean;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getMovableTilesMi) {
            return { ok: false, error: "GetMovableTilesFor(3) not resolved" };
        }
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status.stageName ?? status.stage) + " (need Running)" };
        }
        const playerId = status.currentTurnPlayer;
        const movementQuery = runner.add(movementQueryOff).readPointer();
        if (movementQuery.isNull()) return { ok: false, error: "MovementQuery null" };
        const attackQuery = runner.add(attackQueryOff).readPointer();
        if (attackQuery.isNull()) return { ok: false, error: "AttackQuery null" };
        const getBestMi = findMethodByParamCount(
            attackQuery.readPointer(), "GetBestTileToAttackFrom", 4);
        if (!getBestMi) {
            return { ok: false, error: "GetBestTileToAttackFrom(4) not resolved" };
        }

        const before = summarize(statePtr);
        const t0 = Date.now();
        // NATIF = dégât fidèle ennemi→moi seulement. La géométrie (hasSafeTile /
        // exposed) est calculée côté Python via oracle.geometric_danger_zone (le
        // RPC dangerZone natif renvoie 0 sur ce build — cf. oracle.py).
        const exp = computeExposure(
            statePtr, movementQuery, attackQuery, getBestMi, resolveDpq(runner),
            { unitId: body?.unitId, allAbilities: body?.allAbilities,
              victimsOffTurn: body?.victimsOffTurn });
        const after = summarize(statePtr);
        return {
            ok: true, runner: label,
            stage: status.stage, stageName: status.stageName,
            turn: projectMatchState(statePtr).turn, currentPlayer: playerId,
            mutated: before.sig !== after.sig, ms: Date.now() - t0,
            unitCount: exp.units.length, enemyCount: exp.enemyCount,
            lethalCount: exp.units.filter((u) => u.lethalPossible).length,
            units: exp.units,
        };
    });

    /** DEBUG RE — dumpe les composants (classe + ns + champs nom/offset/type)
     *  d'une entité par id. Sert à localiser HP/abilities/position sur les MoW
     *  (Machine Type 6 / MachinePlatform Type 7) dont la structure diffère des
     *  squads. body: { runnerId?, entityId, withFields?=true } */
    ctx.rpc.dumpEntityComponents = (
        body?: { runnerId?: number; entityId?: number; withFields?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
        } else if (state.liveRunner) { runner = state.liveRunner; }
        else return { ok: false, error: "no runner — pass runnerId" };
        if (runner.isNull()) return { ok: false, error: "runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const target = body?.entityId;
        if (typeof target !== "number") return { ok: false, error: "pass entityId" };
        const withFields = body?.withFields !== false;
        let result: unknown = { ok: false, error: "entity " + target + " not found" };
        forEachEntity(statePtr, (e, id, ty) => {
            if (id !== target) return;
            const components: Array<unknown> = [];
            forEachComponent(e, (comp, klass) => {
                components.push({
                    cls: s(class_get_name(klass) as NativePointer),
                    ns: s(class_get_namespace(klass) as NativePointer),
                    comp: comp.toString(),
                    fields: withFields ? classFieldsDump(klass) : undefined,
                });
            });
            result = { ok: true, id, type: ty, entityPtr: e.toString(), components };
        });
        return result;
    });

    /** APPLIQUER MON COUP (Phase 5) — construit + applique une (ou des) action(s)
     *  via AiControl.ApplyAiMessage sur le runner, avec snapshot AVANT/APRÈS pour
     *  observer le résultat réel. Décomposable : 1 action par appel (move PUIS
     *  observe PUIS ability) → jouer une unité « en 2 temps ». MoW = ability seule
     *  (ne bougent pas). Faithful : SkipFlags=false → le moteur valide portée /
     *  action restante / overwatch.
     *  body: { runnerId?, action?, actions?[] }
     *    action: { kind:"move", unitId, to:{col,row} | feet:[{col,row}...] }
     *          | { kind:"ability", casterId, targetId, abilityType }
     *          | { kind:"finish", unitId } */
    ctx.rpc.applyAction = (
        body?: {
            runnerId?: number;
            action?: ActionSpec; actions?: ActionSpec[];
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (!applyAiMsgMi) return { ok: false, error: "ApplyAiMessage not resolved" };
        if (!moveUnitMsgClass || !activeAbilityMsgClass || !finishUnitTurnMsgClass) {
            return { ok: false, error: "message classes not resolved" };
        }
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status0 = readBattleStatus(statePtr);
        if (status0.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status0.stageName ?? status0.stage)
                    + " (need Running)" };
        }
        const aiControl = runner.add(runnerOff.aiControl).readPointer();
        if (aiControl.isNull()) return { ok: false, error: "aiControl null" };

        const actions = body?.actions ?? (body?.action ? [body.action] : []);
        if (!actions.length) {
            return { ok: false, error: "no action(s) — pass action/actions" };
        }

        const t0 = Date.now();
        const results: ActionResult[] = [];
        for (const a of actions) results.push(applyOneAction(runner, aiControl, a));

        const stateF = runner.add(runnerOff.state).readPointer();
        const finalStatus = readBattleStatus(stateF);
        const units = projectMatchState(stateF).units.map((u) => ({
            squadId: u.squadId, pos: u.pos, hp: u.hp, ownerId: u.ownerId,
        }));
        return {
            ok: results.every((r) => r.ok), runner: label, ms: Date.now() - t0,
            actions: results,
            stage: finalStatus.stage, stageName: finalStatus.stageName,
            currentPlayer: finalStatus.currentTurnPlayer,
            units,
        };
    });

    /** PROBE prédiction de dégâts : pour (unit, target) depuis une tile choisie
     *  (col,row ; défaut = tile courante), appelle
     *  `DamagePredictionQuery.GetAllPredictions(unit, selectedTile, ability)` →
     *  IDictionary<IEntity, DamagePredictionResult>, puis `dict.get_Item(target)`
     *  → struct boxée lue à +0x10. Read-only. Valide la chaîne d'invoke avant
     *  d'intégrer la prédiction aux attackPlans.
     *  body: { runnerId, unitId, targetId, abilityType?, col?, row? } */
    ctx.rpc.aiPredict = (
        body?: {
            runnerId?: number; unitId?: number; targetId?: number;
            abilityType?: number; col?: number; row?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getMovableTilesMi) return { ok: false, error: "GetMovableTilesFor(3) not resolved" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, error: "stage " + (status.stageName ?? status.stage) };
        }
        const movementQuery = runner.add(movementQueryOff).readPointer();
        // Instance portant GetAllPredictions : <DamagePredictionQuery> du runner
        // si présent, sinon l'attackQuery (BattleQuery god-object implémente tout).
        const dpqCands: Array<{ inst: NativePointer; src: string }> = [];
        if (servicesOff >= 0 && dpqInServicesOff >= 0) {
            const services = runner.add(servicesOff).readPointer();
            if (!services.isNull()) {
                const d = services.add(dpqInServicesOff).readPointer();
                if (!d.isNull()) {
                    dpqCands.push({ inst: d, src: "EntityServices.<DamagePredictionQuery>" });
                }
            }
        }
        const aq0 = runner.add(attackQueryOff).readPointer();
        if (!aq0.isNull()) dpqCands.push({ inst: aq0, src: "attackQuery" });
        let dpq = ptr(0);
        let getAllPredMi: { info: NativePointer; ptr: NativePointer } | null = null;
        let dpqSrc = "none";
        for (const c of dpqCands) {
            const mi = findMethodByParamCount(c.inst.readPointer(), "GetAllPredictions", 3);
            if (mi) { dpq = c.inst; getAllPredMi = mi; dpqSrc = c.src; break; }
        }
        if (!getAllPredMi) {
            return { ok: false, error: "GetAllPredictions(3) introuvable (servicesOff="
                + servicesOff + ", dpqInServices=" + dpqInServicesOff
                + ", cands=" + dpqCands.map((c) => c.src).join(",") + ")" };
        }

        let unit = ptr(0); let target = ptr(0);
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit) return;
            if (id === body?.unitId) unit = e;
            if (id === body?.targetId) target = e;
        });
        if (unit.isNull()) return { ok: false, error: "unit " + body?.unitId + " not found" };
        if (target.isNull()) return { ok: false, error: "target " + body?.targetId + " not found" };

        let ability = body?.abilityType;
        if (typeof ability !== "number") {
            const abs = unitAbilityTypes(unit, false);
            ability = abs.length ? abs[0].id : 0;
        }
        const abilBuf = Memory.alloc(4); abilBuf.writeS32(ability);

        // Tile attaquante : (col,row) dans le movable set, sinon tile courante.
        let tile = ptr(0);
        const wantCol = body?.col; const wantRow = body?.row;
        if (typeof wantCol === "number" && typeof wantRow === "number") {
            const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
            const optsZero = Memory.alloc(0x30);
            for (let k = 0; k < 0x30; k += 4) optsZero.add(k).writeU32(0);
            try {
                const os = invokeMethod(getMovableTilesMi.info, movementQuery,
                    [unit, boolFalse, optsZero]);
                for (const t of extractTilePtrs(os)) {
                    if (t.col === wantCol && t.row === wantRow) { tile = t.ptr; break; }
                }
            } catch { /* */ }
            if (tile.isNull()) {
                const mt = getUnitMainTile(unit, statePtr);
                if (!mt.isNull()) {
                    const c = readTileCoord(mt);
                    if (c.col === wantCol && c.row === wantRow) tile = mt;
                }
            }
            if (tile.isNull()) {
                return { ok: false, error: "tile (" + wantCol + "," + wantRow + ") pas dans le movable set" };
            }
        } else {
            tile = getUnitMainTile(unit, statePtr);
            if (tile.isNull()) return { ok: false, error: "current tile null" };
        }

        const before = summarize(statePtr);
        let dict: NativePointer;
        try { dict = invokeMethod(getAllPredMi.info, dpq, [unit, tile, abilBuf]); }
        catch (e) { return { ok: false, error: "GetAllPredictions threw: " + (e as Error).message }; }
        let dictCount = -1; let pred: Record<string, number> | null = null;
        let err: string | null = null;
        if (!dict.isNull()) {
            const dictClass = dict.readPointer();
            const getCountMi = findMethod(dictClass, "get_Count");
            if (getCountMi) {
                try { dictCount = invokeMethod(getCountMi.info, dict, null).add(0x10).readS32(); }
                catch { /* */ }
            }
            const getItemMi = findMethodByParamCount(dictClass, "get_Item", 1);
            if (getItemMi) {
                try {
                    const boxed = invokeMethod(getItemMi.info, dict, [target]);
                    if (!boxed.isNull()) {
                        // struct DamagePredictionResult @ boxed+0x10 (dump kqkbjqfb6c) :
                        // CurrentHealth@0 Armor@4 Shield@8 ;
                        // AccurateHealthDamage(MinMaxDamage)@0x58 (Min@0x60,Max@0x64) ;
                        // TotalDamage@0x88 (Min@0x90,Max@0x94) ;
                        // MightCrit@0xB1 ForceOverkill@0xB2 AppliedHits@0xBC.
                        const b = boxed.add(0x10);
                        pred = {
                            hpBefore: b.readS32(), armorBefore: b.add(0x4).readS32(),
                            shieldBefore: b.add(0x8).readS32(),
                            healthDmgMin: b.add(0x60).readS32(),
                            healthDmgMax: b.add(0x64).readS32(),
                            totalDmgMin: b.add(0x90).readS32(),
                            totalDmgMax: b.add(0x94).readS32(),
                            mightCrit: b.add(0xb1).readU8(),
                            appliedHits: b.add(0xbc).readS32(),
                        };
                    }
                } catch (e) { err = "get_Item: " + (e as Error).message; }
            } else { err = "get_Item not resolved"; }
        }
        const after = summarize(statePtr);
        return {
            ok: true, runner: label, dpqSrc,
            unitId: body?.unitId, targetId: body?.targetId,
            ability, abilityName: abilityName(ability), tile: readTileCoord(tile),
            dictNull: dict.isNull(), dictCount, pred,
            kill: pred ? (pred.healthDmgMax >= pred.hpBefore) : null,
            killSure: pred ? (pred.healthDmgMin >= pred.hpBefore) : null,
            mutated: before.sig !== after.sig, err,
        };
    });
}
