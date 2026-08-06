/** RPCs TARGETING/ranking/legalite : aiAttackRank, abilityTargets, abilityReason,
 *  castFromTiles.
 *  Scinde de rpc-view.ts (2026-07-11, >2300 l. — seuil ~1000 l.) ; l'API RPC est
 *  INCHANGEE (memes noms ctx.rpc.*), agregee par registerView (rpc-view.ts). */
import {
    class_get_name, class_get_namespace, findClass, findClassAnywhere, findMethod,
    findMethodByParamClasses, findMethodByParamCount, getFieldOffset, readIl2cppString, s,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import { runnerClass, runnerOff } from "../../game/runner.js";
import { getRunner } from "../../game/runner-registry.js";
import { setTraceOrigin } from "../../game/trace-origin.js";
import {
    EntityType, forEachComponent, forEachEntity, projectMatchState,
    readBattleStatus, unitFootComponentClass,
} from "../../game/match-state.js";
import {
    readEffectsByUnit, readEffectsByTile, readRoundCapClock, readEffectAbilityStateRaw,
} from "../../game/effects.js";
import { state } from "../../game/state.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { abilityName } from "../../data/ability-names.js";
import { TARGETING_RULE_BITS } from "../../data/targeting-rule-names.js";

/**
 * Classes d'`IBrokenTargetingRule` dont le code N'EST PAS un champ mais le retour de leur
 * `get_Type`. Recensé au décompilé sur `rnca9r7q6c` : `NoBrokenTargetingRule` (valide) et
 * `ObscuredTerrainBrokenTargetingRule` — `IdunBattle.Core.Services.ObscuredTerrainBrokenTargetingRule$$get_Type`
 * rend le littéral `0x1000000` = bit 24 `TargetIsUnobscured`. Toute autre classe reste non décodable
 * et sort en `hex: "0x0"` avec sa `ruleClass`, comme avant.
 */
const NON_GENERIC_RULE_CODES: Record<string, number> = {
    NoBrokenTargetingRule: 0,
    ObscuredTerrainBrokenTargetingRule: 0x1000000,
};
import { Ctx } from "../../controller.js";
import {
    ActionResult, ActionSpec, activeAbilityMsgClass, applyOneAction,
    attackQueryOff, battleInServicesOff, dpqInServicesOff, entityServicesClass,
    extractTiles, extractTilePtrs,
    entityExtClass, finishUnitTurnMsgClass, getMovableTilesMi, getTilesMi, getUnitMainTile,
    invokeBool, isAliveMi, isCtrlByCurMi, LIST_SIZE, moveUnitMsgClass, movementQueryOff,
    mowAbilityTypes, readTileCoord, resolveDpq, servicesOff, summarize, unitAbilityTypes,
    unitExtClass,
} from "./internals.js";
import { applyAiMsgMi } from "../../game/ai-control.js";
import {
    classFieldsDump, computeAttackPlans, computeDangerZone, computeExposure,
    projectMowsFull, projectUnitsFull,
} from "./projection.js";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function registerViewTargeting(ctx: Ctx): void {
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
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
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

    /** abilityTargets — énumération des CIBLES LÉGALES par (unit contrôlée,
     *  ability), l'analogue ability de `aiMovableTiles`/`moves` pour TOUTES les
     *  abilities — y compris non-attaque (buff/heal/summon/hex) ABSENTES des
     *  attackPlans. Pour chaque unit ctrl+vivante × chaque ability concrète,
     *  appelle `BattleQuery.GetAllValidTargetsFromAllPossibleMovementTiles(unit,
     *  ability, ignoreMovementFlag=false)` (= ce que l'IA `BasePlaybook` consomme)
     *  → `ValidTargets.AllTargets@0x10` → mappe en cibles (units → squadId/
     *  visualId/pos ; hex libres → tile coord). DEUX champs par ability :
     *  `targets` = « ce TOUR, déplacement INCLUS » (superset) ; `fromHere` =
     *  castable SANS bouger depuis la tuile courante (via `AttackQuery.GetValidTargets(
     *  unit, UnitPosition{GetTiles}, ability)`, légalité EXACTE du cast immédiat).
     *  → net H55 précis : ∉ des deux ⇒ no-op certain ; ∈ targets mais ∉ fromHere ⇒
     *  « bouger d'abord ». Read-only (mutated=false attendu). body: { runnerId,
     *  unitId?, abilityType?, allAbilities?=true }. cf. docs/rl/ai-step-toolkit.md §d. */
    ctx.rpc.abilityTargets = (
        body?: {
            runnerId?: number; unitId?: number;
            abilityType?: number; allAbilities?: boolean;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        const manualAbility = (typeof body?.abilityType === "number")
            ? (body.abilityType | 0) : null;
        const allAbilities = body?.allAbilities !== false;   // défaut TRUE
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status.stageName ?? status.stage) + " (need Running)" };
        }
        const playerId = status.currentTurnPlayer;
        if (servicesOff < 0 || battleInServicesOff < 0) {
            return { ok: false, error: "services/Battle offsets unresolved" };
        }
        const services = runner.add(servicesOff).readPointer();
        if (services.isNull()) return { ok: false, error: "EntityServices null" };
        const battleQuery = services.add(battleInServicesOff).readPointer();
        if (battleQuery.isNull()) return { ok: false, error: "BattleQuery null (<Battle>)" };
        const getAllValidMi = findMethodByParamCount(
            battleQuery.readPointer(),
            "GetAllValidTargetsFromAllPossibleMovementTiles", 3);
        if (!getAllValidMi) {
            return { ok: false, error:
                "GetAllValidTargetsFromAllPossibleMovementTiles(3) not resolved on "
                + s(class_get_name(battleQuery.readPointer()) as NativePointer) };
        }
        // Overload per-position « depuis la tuile courante, SANS bouger » :
        // AttackQuery.GetValidTargets(IEntity unit, UnitPosition from, ActiveAbilityType).
        // DEUX overloads 3-param (l'autre prend IOrderedSet<UnitPosition>) → désambiguïsé
        // par le type du param[1] == "UnitPosition". null = fromHere indispo (dégradé).
        const attackQuery = runner.add(attackQueryOff).readPointer();
        const getValidFromPosMi = (!attackQuery.isNull() && getTilesMi)
            ? findMethodByParamClasses(
                attackQuery.readPointer(), "GetValidTargets",
                [null, "UnitPosition", null])
            : null;

        // Carte ptr-entité → {id, type} pour résoudre les cibles renvoyées.
        const entById = new Map<string, { id: number; ty: number }>();
        forEachEntity(statePtr, (e, id, ty) => {
            entById.set(e.toString(), { id, ty });
        });
        const proj = projectMatchState(statePtr);
        const visById = new Map<number, string | null>();
        const posById = new Map<number, { col: number; row: number } | null>();
        for (const u of proj.units) {
            visById.set(u.squadId, u.visualId);
            posById.set(u.squadId, u.pos);
        }
        // Identité MoW : l'entité Machine porte HP/owner/abilities ; casterId = machineId.
        for (const m of projectMowsFull(statePtr, proj)) {
            visById.set(m.casterId, m.visualId);
            posById.set(m.casterId, m.pos);
        }

        // Casters à scanner : units (Type Unit) + MoW (Type Machine), ctrl+vivants,
        // filtrables par unitId. Les MoW ne bougent pas mais castent depuis leur place.
        const myUnits: Array<{ id: number; ptr: NativePointer; isMow: boolean }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            const isMow = ty === EntityType.Machine;
            if (ty !== EntityType.Unit && !isMow) return;
            if (!invokeBool(isAliveMi, [e, statePtr])) return;
            if (!invokeBool(isCtrlByCurMi, [e, statePtr])) return;
            if (body?.unitId === undefined || body.unitId === id) {
                myUnits.push({ id, ptr: e, isMow });
            }
        });

        const abilBuf = Memory.alloc(4);
        const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
        const before = summarize(statePtr);
        const t0 = Date.now();
        type Tgt = {
            kind: "unit" | "tile"; targetId?: number; visualId?: string | null;
            pos?: { col: number; row: number } | null;
            tile?: { col: number; row: number };
            // #302 tranche 5 — sur `kind: "tile"`, l'id de l'ENTITÉ de tuile quand
            // `forEachEntity` l'a indexée, ACCOMPAGNÉ de son `EntityType`. Publier l'id nu
            // ferait passer pour une tuile n'importe quelle entité tombée dans la branche
            // par défaut ; le canal se décrit donc lui-même, comme `targetEntityType` de
            // `pairUtility` (#302-t5). Les DEUX restent ABSENTS quand l'entité n'est pas
            // indexée — jamais fabriqués.
            targetEntityType?: number;
        };
        interface AbilTargets {
            abilityId: number; ability: string; kind: string;
            usable?: boolean; cooldown?: number | null; disabled?: boolean;
            targetCount: number; targets: Tgt[];     // ce tour, MOVE inclus (superset)
            fromHereCount: number; fromHere: Tgt[];  // SANS bouger (tuile courante)
            err?: string;
        }
        const results: Array<{
            unitId: number; isMow: boolean; visualId: string | null;
            pos: { col: number; row: number } | null;
            abilities: AbilTargets[];
        }> = [];

        // ValidTargets.AllTargets@0x10 (OrderedSet<IEntity>) → cibles mappées
        // (Unit → squadId/visualId/pos ; hex libre → tile coord).
        const mapTargets = (vt: NativePointer): Tgt[] => {
            const out: Tgt[] = [];
            if (vt.isNull()) return out;
            let allTargets: NativePointer;
            try { allTargets = vt.add(0x10).readPointer(); } catch { return out; }
            if (allTargets.isNull()) return out;
            for (const p of extractTilePtrs(allTargets)) {
                const info = entById.get(p.ptr.toString());
                if (info && (info.ty === EntityType.Unit
                             || info.ty === EntityType.Machine)) {
                    out.push({
                        kind: "unit", targetId: info.id,
                        visualId: visById.get(info.id) ?? null,
                        pos: posById.get(info.id) ?? { col: p.col, row: p.row },
                    });
                } else {
                    // #302 tranche 5 — `forEachEntity` INDEXE les `EntityType.Tile` : l'id
                    // était disponible ici et jeté. C'est celui qu'`applyAction` attend comme
                    // cible d'une self-cast AoE (`findTileEntityId`) et que `pairUtility`
                    // résout désormais sur TOUS les `EntityType`. Le port s'en passait par
                    // `boardGraph` (d'où « confort, pas blocage ») ; l'émettre ici évite
                    // l'aller-retour et le ré-appariement par coordonnées.
                    const t: Tgt = { kind: "tile", tile: { col: p.col, row: p.row } };
                    if (info) { t.targetId = info.id; t.targetEntityType = info.ty; }
                    out.push(t);
                }
            }
            return out;
        };

        for (const u of myUnits) {
            const abilities = (manualAbility !== null)
                ? [{ id: manualAbility,
                     name: abilityName(manualAbility) ?? "id:" + manualAbility,
                     kind: "manual" as string }]
                : (u.isMow
                    ? mowAbilityTypes(u.ptr)        // Primary/Secondary machine + actives
                    : unitAbilityTypes(u.ptr, allAbilities));
            const abOut: AbilTargets[] = [];
            // UnitPosition value {Tiles=GetTiles(unit,state)} pour le call per-position
            // « sans bouger ». gcRoot tant qu'on l'utilise (GetValidTargets alloue du
            // managé → GC possible entre deux abilities).
            let unitPosBuf: NativePointer | null = null;
            let tilesList: NativePointer | null = null;
            if (getValidFromPosMi && getTilesMi) {
                try {
                    const tl = invokeMethod(getTilesMi.info, null, [u.ptr, statePtr]);
                    if (!tl.isNull()) {
                        tilesList = tl; gcRoot.add(tl);
                        unitPosBuf = Memory.alloc(Process.pointerSize);
                        unitPosBuf.writePointer(tl);
                    }
                } catch { /* fromHere indispo pour cette unit */ }
            }
            for (const ab of abilities) {
                abilBuf.writeS32(ab.id);
                const entry: AbilTargets = {
                    abilityId: ab.id, ability: ab.name, kind: ab.kind,
                    targetCount: 0, targets: [], fromHereCount: 0, fromHere: [],
                };
                // état live (présent sur les actives via unitAbilityTypes).
                const st = ab as Partial<{
                    usable: boolean; cooldown: number | null; disabled: boolean;
                }>;
                if (st.usable !== undefined) entry.usable = st.usable;
                if (st.cooldown !== undefined) entry.cooldown = st.cooldown;
                if (st.disabled !== undefined) entry.disabled = st.disabled;
                // targetsThisTurn (MOVE inclus) via BattleQuery.
                try {
                    entry.targets = mapTargets(invokeMethod(
                        getAllValidMi.info, battleQuery, [u.ptr, abilBuf, boolFalse]));
                } catch (e) { entry.err = (e as Error).message; }
                // fromHere (SANS bouger) via AttackQuery.GetValidTargets(unit, pos, ability).
                if (unitPosBuf) {
                    try {
                        entry.fromHere = mapTargets(invokeMethod(
                            getValidFromPosMi!.info, attackQuery,
                            [u.ptr, unitPosBuf, abilBuf]));
                    } catch { /* laisse [] */ }
                }
                entry.targetCount = entry.targets.length;
                entry.fromHereCount = entry.fromHere.length;
                abOut.push(entry);
            }
            if (tilesList) { try { gcRoot.remove(tilesList); } catch { /* */ } }
            results.push({
                unitId: u.id, isMow: u.isMow, visualId: visById.get(u.id) ?? null,
                pos: posById.get(u.id) ?? null, abilities: abOut,
            });
        }
        const after = summarize(statePtr);
        return {
            ok: true, runner: label, playerId,
            abilityMode: manualAbility !== null
                ? "manual:" + manualAbility
                : (allAbilities ? "auto+actives" : "auto-normal"),
            fromHereResolved: !!getValidFromPosMi,
            semantics: "targets=ce tour MOVE inclus (superset) ; fromHere=SANS bouger "
                + "(légalité exacte du cast immédiat). absent des deux => no-op certain ; "
                + "dans targets mais pas fromHere => bouger d'abord.",
            mutated: before.sig !== after.sig, ms: Date.now() - t0,
            unitCount: results.length, units: results,
        };
    });

    /** abilityReason — RAISON STRUCTURÉE d'un cast invalide (volet H55) via
     *  `AttackQuery.GetInvalidTargetReason(attacker, attackerTile, defender, ability)`
     *  + `GetInvalidCasterReason(attacker, attackerTile, ability)` → `IBrokenTargetingRule.
     *  Type` (flag `TargetingRule` 64-bit décodé en NOMS via TARGETING_RULE_BITS).
     *  Explique POURQUOI une ability ne passe pas : hors portée (`TargetIsInRange`),
     *  déjà utilisée (`AlreadyUseThisTurn`), mauvais type de cible (`TargetIsHealable`/
     *  `TargetIsEnemy`…), LoS (`TargetIsUnobscured`), tuile occupée (`TargetTileIsFree`)…
     *  Overloads désambiguïsés via findMethodByParamClasses (param tile = "IEntity").
     *  body: { runnerId, casterId, abilityType, targetId? }. Read-only.
     *  cf. docs/rl/ai-step-toolkit.md §d. */
    ctx.rpc.abilityReason = (
        body?: { runnerId?: number; casterId?: number;
                 targetId?: number; abilityType?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.casterId !== "number" || typeof body?.abilityType !== "number") {
            return { ok: false, error: "need casterId + abilityType" };
        }
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) { runner = state.liveRunner; label = "live"; }
        else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, error: "stage " + (status.stageName ?? status.stage) };
        }
        const attackQuery = runner.add(attackQueryOff).readPointer();
        if (attackQuery.isNull()) return { ok: false, error: "AttackQuery null" };
        const aqClass = attackQuery.readPointer();
        // Overloads 4-/3-param désambiguïsés par le type de la tuile = "IEntity"
        // (≠ "UnitPosition" / "IList`1").
        const tgtReasonMi = findMethodByParamClasses(
            aqClass, "GetInvalidTargetReason", [null, "IEntity", null, null]);
        const casterReasonMi = findMethodByParamClasses(
            aqClass, "GetInvalidCasterReason", [null, "IEntity", null]);

        const ptrById = new Map<number, NativePointer>();
        forEachEntity(statePtr, (e, id) => { ptrById.set(id, e); });
        const caster = ptrById.get(body.casterId) ?? ptr(0);
        if (caster.isNull()) {
            return { ok: false, error: "caster u" + body.casterId + " introuvable" };
        }
        const casterTile = getUnitMainTile(caster, statePtr);
        const abilBuf = Memory.alloc(4); abilBuf.writeS32(body.abilityType | 0);

        // État LIVE de l'ability demandée (cooldown/usable/disabled) lu sur son
        // objet components.ActiveAbility. La couche targeting (TargetingRule)
        // n'a AUCUN flag de cooldown → GetInvalidTargetReason/CasterReason rendent
        // `ValidRequest` même cooldown-locked (TF24) : sans cet ajout, `reason`
        // laisse croire l'ability castable alors qu'elle est en recharge. null =
        // ability absente des actives (attaque normale, ou ability-machine
        // Primary/Secondary dont le cooldown n'est pas porté par un ActiveAbility).
        // ⚠ `ammoCost`/`hasAmmo` SONT DANS CE PAYLOAD DEPUIS #287-r9, et ce n'est pas cosmétique.
        // `AttackQuery$$GetInvalidTargetReason` court-circuite AUSSI sur `*(int*)(ability+0x44) == 0`,
        // qui est le terme MUNITIONS d'une MACHINE OF WAR. MESURÉ le 2026-08-06 sur
        // `ultraDreadnought` / `DutyEternal` (1158) : avec `MachineOfWarAmmo = 0`, `casterReason`
        // reste `ValidRequest` APRÈS 4 tours alors que `cooldown` est retombé à `0` — le lecteur
        // voyait donc un court-circuit dont AUCUN champ publié ne donnait la cause, et
        // `oracle_targeting.cause_du_court_circuit` le rangeait en `indeterminee`. Avec
        // `MachineOfWarAmmo = 9`, le même couple bascule à `0`. Les deux champs sont déjà lus par
        // `readAbilityState` (`ActiveAbility+<abAmmoCostOff>` / `+<abHasAmmoOff>`) et publiés par
        // `decisionView` : ils ne coûtaient qu'une recopie ici.
        let abilityState: {
            usable?: boolean; cooldown?: number | null; disabled?: boolean;
            ammoCost?: number | null; hasAmmo?: boolean;
        } | null = null;
        try {
            const ab = unitAbilityTypes(caster, true).find((x) => x.id === body.abilityType);
            if (ab && (ab.usable !== undefined || ab.cooldown !== undefined
                       || ab.disabled !== undefined || ab.hasAmmo !== undefined
                       || ab.ammoCost !== undefined)) {
                abilityState = {
                    usable: ab.usable, cooldown: ab.cooldown ?? null, disabled: ab.disabled,
                    ammoCost: ab.ammoCost ?? null, hasAmmo: ab.hasAmmo,
                };
            }
        } catch { /* best-effort */ }

        // GetInvalidTargetReason renvoie un IBrokenTargetingRule BOXÉ (struct value-type) :
        //  - NoBrokenTargetingRule = cible VALIDE (pas de champ).
        //  - GenericBrokenTargetingRule = { TargetingRule <Type>@0x0 } → 1 FLAG unique de
        //    la règle cassée (range / enemy / healable / AlreadyUseThisTurn…). Boxé → le
        //    champ est à obj+0x10. (On lit le champ DIRECT, pas get_Type() : invoquer un
        //    getter de struct boxée demande this=obj+0x10 ; le lire est plus simple+sûr.)
        //  - autres types (obscured/unwalkable) = règle non-flag → on remonte la classe.
        const decodeRule = (
            ruleObj: NativePointer,
        ): { ruleClass: string; hex: string; reasons: string[] } | null => {
            if (ruleObj.isNull()) return null;
            const clsName = s(class_get_name(ruleObj.readPointer()) as NativePointer);
            if (clsName !== "GenericBrokenTargetingRule") {
                // NoBrokenTargetingRule = valide ; sinon règle non-flag → le code vient de son
                // `get_Type`, PAS d'un champ. Une seule classe est dans ce cas sur `rnca9r7q6c` :
                // `ObscuredTerrainBrokenTargetingRule` (la LIGNE DE VUE), dont
                // `IdunBattle.Core.Services.ObscuredTerrainBrokenTargetingRule$$get_Type` rend le
                // littéral 0x1000000 = `TargetIsUnobscured`. Sans cette ligne le canal publiait
                // `hex: "0x0"` — donc « cible VALIDE » — pour un refus (#444) : la dégradation était
                // SILENCIEUSE, et invisible tant que le port ne portait pas la règle non plus.
                const code = NON_GENERIC_RULE_CODES[clsName];
                if (code === undefined) {
                    return { ruleClass: clsName, hex: "0x0", reasons: [] };
                }
                return {
                    ruleClass: clsName,
                    hex: "0x" + code.toString(16).padStart(16, "0"),
                    reasons: code === 0 ? [] : [TARGETING_RULE_BITS[Math.log2(code)] ?? clsName],
                };
            }
            const lo = ruleObj.add(0x10).readU32();
            const hi = ruleObj.add(0x14).readU32();
            const reasons: string[] = [];
            for (let b = 0; b < 58; b++) {
                const set = b < 32
                    ? (lo & (1 << b)) !== 0
                    : (hi & (1 << (b - 32))) !== 0;
                if (set && TARGETING_RULE_BITS[b]) reasons.push(TARGETING_RULE_BITS[b]);
            }
            const hex = "0x" + hi.toString(16).padStart(8, "0")
                + lo.toString(16).padStart(8, "0");
            return { ruleClass: clsName, hex, reasons };
        };

        const before = summarize(statePtr);
        let casterReason: { hex: string; reasons: string[] } | null = null;
        let targetReason: { hex: string; reasons: string[] } | null = null;
        if (casterReasonMi) {
            try {
                casterReason = decodeRule(invokeMethod(
                    casterReasonMi.info, attackQuery, [caster, casterTile, abilBuf]));
            } catch { /* */ }
        }
        if (typeof body.targetId === "number" && tgtReasonMi) {
            const target = ptrById.get(body.targetId) ?? ptr(0);
            if (!target.isNull()) {
                try {
                    targetReason = decodeRule(invokeMethod(tgtReasonMi.info, attackQuery,
                        [caster, casterTile, target, abilBuf]));
                } catch { /* */ }
            }
        }
        const after = summarize(statePtr);
        return {
            ok: true, runner: label,
            casterId: body.casterId, targetId: body.targetId ?? null,
            abilityType: body.abilityType,
            resolved: { caster: !!casterReasonMi, target: !!tgtReasonMi },
            casterReason, targetReason, abilityState,
            mutated: before.sig !== after.sig,
        };
    });

    /** castFromTiles — les tuiles (COURANTE + MOVE) d'où le cast de `abilityType` sur `targetId`
     *  est LÉGAL, via `AttackQuery.GetInvalidTargetReason(caster, tile, target, ability)` == valide
     *  (`NoBrokenTargetingRule`). La tuile est un param EXPLICITE (IEntity) → pas besoin de
     *  construire un `UnitPosition` par tuile. Résout le positionnement MOVE-TO-REACH des NC
     *  ally-targeted (#81 : InspiredToGreatness caste 1082 depuis une tuile de move quand l'allié
     *  n'est pas atteignable in-place). Le port choisit : origine si `currentValid`, sinon la 1re
     *  tuile de `moveTiles` (ordre `GetMovableTilesFor`). Read-only (mutated=false attendu). body:
     *  { runnerId, casterId, targetId, abilityType }. */
    ctx.rpc.castFromTiles = (
        body?: { runnerId?: number; casterId?: number; targetId?: number; abilityType?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.casterId !== "number" || typeof body?.targetId !== "number"
            || typeof body?.abilityType !== "number") {
            return { ok: false, error: "need casterId + targetId + abilityType" };
        }
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) { runner = state.liveRunner; label = "live"; }
        else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getMovableTilesMi) return { ok: false, error: "GetMovableTilesFor not resolved" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, error: "stage " + (status.stageName ?? status.stage) };
        }
        const attackQuery = runner.add(attackQueryOff).readPointer();
        const movementQuery = runner.add(movementQueryOff).readPointer();
        if (attackQuery.isNull() || movementQuery.isNull()) {
            return { ok: false, error: "AttackQuery/MovementQuery null" };
        }
        const tgtReasonMi = findMethodByParamClasses(
            attackQuery.readPointer(), "GetInvalidTargetReason", [null, "IEntity", null, null]);
        if (!tgtReasonMi) return { ok: false, error: "GetInvalidTargetReason not resolved" };
        const ptrById = new Map<number, NativePointer>();
        forEachEntity(statePtr, (e, id) => { ptrById.set(id, e); });
        const caster = ptrById.get(body.casterId) ?? ptr(0);
        const target = ptrById.get(body.targetId) ?? ptr(0);
        if (caster.isNull() || target.isNull()) {
            return { ok: false, error: "caster/target introuvable" };
        }
        const abilBuf = Memory.alloc(4); abilBuf.writeS32(body.abilityType | 0);
        // Cast légal depuis `tilePtr` = GetInvalidTargetReason rend NoBrokenTargetingRule.
        const isValid = (tilePtr: NativePointer): boolean => {
            try {
                const rule = invokeMethod(tgtReasonMi.info, attackQuery,
                    [caster, tilePtr, target, abilBuf]);
                if (rule.isNull()) return false;
                return s(class_get_name(rule.readPointer()) as NativePointer)
                    === "NoBrokenTargetingRule";
            } catch { return false; }
        };
        const before = summarize(statePtr);
        const curTile = getUnitMainTile(caster, statePtr);
        const currentValid = !curTile.isNull() && isValid(curTile);
        // Tuiles de move (GetMovableTilesFor(caster, false, {})) en ORDRE ; on garde celles d'ou
        // le cast sur la cible est legal (mirror du sweep de positions du generateur natif).
        const boolBuf = Memory.alloc(1); boolBuf.writeU8(0);
        const optsBuf = Memory.alloc(0x30);
        for (let k = 0; k < 0x30; k += 4) optsBuf.add(k).writeU32(0);
        const moveTiles: Array<{ col: number; row: number }> = [];
        try {
            const os = invokeMethod(getMovableTilesMi.info, movementQuery, [caster, boolBuf, optsBuf]);
            for (const t of extractTilePtrs(os)) {
                if (isValid(t.ptr)) moveTiles.push({ col: t.col, row: t.row });
            }
        } catch { /* moveTiles reste [] */ }
        const after = summarize(statePtr);
        return {
            ok: true, runner: label, casterId: body.casterId, targetId: body.targetId,
            abilityType: body.abilityType, currentValid, moveTiles,
            mutated: before.sig !== after.sig,
        };
    });

}
