/** RPCs BOARD/terrain/pathfinding : battleStatus, dumpRng, aiMovableTiles, tileMeta,
 *  boardGraph, pathDistToEnemies.
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

// --- Pathfinder (distance CHEMIN, pour le scoring de move fidèle, doc §13.12) ---
// `MinDistanceToClosestEnemyUtility.GetMinDistanceToEnemy` mesure une distance de CHEMIN
// (`Pathfinders.GetPath(...).Count`), PAS la distance hex. On expose donc la distance-chemin
// par tuile candidate → le `ClosestEnemy` UNIQUE (fidélité #32 : le natif cible l'ennemi le plus
// proche de la position COURANTE via FindClosestEnemy, PAS le min sur tous les ennemis — cf. la
// sélection ClosestEnemy dans pathDistToEnemies ci-dessous), pour remplacer hexgeo.distance côté moteur.
// Champ runner = auto-property `<Pathfinders>k__BackingField` (IPathfinders), PAS `_pathfinders`
// (ça c'est le Dict interne de la classe Pathfinders). GetPath résolu LAZY depuis la classe
// runtime de l'instance (robuste à l'assembly) : GetPath(unit, from, to, Nullable<UseTeleporter>)
// (4 params, overload @180f202b0 qui dérive le type pathfinder de l'unité). Count = long. du chemin.
const pathfindersOff = runnerClass
    ? getFieldOffset(runnerClass, "<Pathfinders>k__BackingField") : -1;
// 5-param overload `GetPath(PathfinderType type, unit, from, to, Nullable<UseTeleporter>)`
// (@180f20190) — type=1 comme `GetMinDistanceToEnemy` (`GetPath(1, unit, evalTile, enemyTile, 0)`).
let getPathMi: { info: NativePointer; ptr: NativePointer } | null = null;
function resolveGetPath(pathfinders: NativePointer): typeof getPathMi {
    if (getPathMi) return getPathMi;
    try { getPathMi = findMethodByParamCount(pathfinders.readPointer(), "GetPath", 5); }
    catch { getPathMi = null; }
    return getPathMi;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function registerViewBoard(ctx: Ctx): void {
    /** STATUS LÉGER pour le long-poll de hand-off self-play : lit SEULEMENT
     *  stage + currentPlayer du runner, sans projection/units/danger-zone (≠
     *  decisionView qui peut overrun une frame seule). Conçu pour être poll-é
     *  toutes les ~400 ms par l'endpoint host /api/selfplay/:id/await.
     *  body: { runnerId } -> { ok, stage, stageName, currentPlayer }.
     *  cf. docs/rl/design.md §Self-play. */
    ctx.rpc.battleStatus = (
        body?: { runnerId?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
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
        return {
            ok: true, runner: label,
            stage: status.stage, stageName: status.stageName,
            currentPlayer: status.currentTurnPlayer,
            // winner = champ natif (MatchComponent) lisible AUSSI post-Finished tant que
            // l'entité Match n'est pas purgée -> adjudication autoritative (H59 : distingue
            // élimination d'un no-winner round-cap, que `decisionView` ne peut pas car il
            // refuse hors-Running). unitsAlive = nb d'entités Unit vivantes.
            winner: status.winner, unitsAlive: status.unitsAlive,
            cheatFinished: status.cheatFinished,
        };
    });

    /** DUMP de l'état du RNG de combat (MT19937) — pour synchroniser le runner
     *  Python (engine/runner/prng.py) sur le live et reproduire un tirage EXACT
     *  (ex. overwatch). RE `IdunRunner.Initialize` : le RNG de combat
     *  (IntBasedMersenneTwister) est stocké sur le runner @0x38 (passé à
     *  DSLFactory.ctor → DisallowablePseudoRNG). Layout MT (de genrand_int32 @180e3a3e0) :
     *  compteur d'appels @+0x14, tableau d'état uint[624] @+0x20 (len @+0x18, data @+0x20),
     *  mti @+0x28. Garde-fou : len doit valoir 624 (sinon offset/build invalide).
     *  body: { runnerId } -> { ok, mt:[624], mti, callCount }. Read-only. */
    ctx.rpc.dumpRng = (
        body?: { runnerId?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
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
        try {
            const rng = runner.add(0x38).readPointer();          // IntBasedMersenneTwister
            if (rng.isNull()) return { ok: false, error: "rng null @0x38" };
            const arr = rng.add(0x20).readPointer();             // uint[] d'état
            if (arr.isNull()) return { ok: false, error: "mt state array null" };
            const len = arr.add(0x18).readS32();
            if (len !== 624) {
                return { ok: false, error: "mt len=" + len + " (attendu 624 — offset/build ?)" };
            }
            const mt: number[] = new Array(624);
            const data = arr.add(0x20);
            for (let i = 0; i < 624; i++) mt[i] = data.add(i * 4).readU32();
            return {
                ok: true, runner: label,
                mti: rng.add(0x28).readS32(),
                callCount: rng.add(0x14).readS32(),
                mt,
            };
        } catch (e) { return { ok: false, error: (e as Error).message }; }
    });

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

    /** METADATA PAR TUILE — élévation + attributs terrain pour le moteur playbook
     *  (engine/utilities/tile.py : ElevationUtility, TileEffects, …). `aiMovableTiles`
     *  ne rend que col/row ; ce RPC projette TOUTES les tiles (TileComponent) avec
     *  leur élévation/terrain. L'occupant steppable se dérive côté moteur via les
     *  positions des summons (decisionView). Read-only. body: { runnerId? }. */
    ctx.rpc.tileMeta = (
        body?: { runnerId?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
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
        const proj = projectMatchState(statePtr, { includeTiles: true });
        // Effets de statut de tuile (EffectsOwnedComponent sur l'entité Tile) — la feuille
        // TileEffectsUtility somme Default.TileEffects.<EffectName> pour chaque effet présent.
        // Clé = entity id de la tuile ; on joint sur t.id de la projection.
        const effectsByTile = readEffectsByTile(statePtr);
        const tiles = (proj.tiles ?? []).map((t) => {
            const effs = effectsByTile.get(t.id) ?? [];
            return {
                col: t.col, row: t.row, elevation: t.elevation,
                isWall: t.isWall, isTemporary: t.isTemporary, isTerritory: t.isTerritory,
                // effects: liste des effets de statut sur la tuile (name = clé de poids
                // Default.TileEffects ; effectType/source pour le multiplicateur natif).
                effects: effs.map((e) => ({
                    name: e.name, effectType: e.effectType,
                    source: e.source, remaining: e.remaining, level: e.level,
                })),
            };
        });
        return { ok: true, runner: label, tileCount: tiles.length, tiles };
    });

    /** GRAPHE DE BOARD STATIQUE — adjacence hex RÉELLE + walkable + élévation,
     *  pour le pathfinding fidèle (engine/entities/pathfinding/, port du
     *  WalkPathfinder natif). `tileMeta` ne donne que col/row/élévation/isWall ;
     *  ici on AJOUTE :
     *   - `neighbours` : voisins NATIFS via `BattleQuery.GetAdjacentTiles(tile,
     *     param3=false, param4=false, param5=true)` = le set géométrique COMPLET
     *     (seule la porte `|dElev|<2` de `TileQuery.<>d__8 @1810acef0`,
     *     INCONDITIONNELLE, s'applique). RE #148 (via les CTORs des itérateurs, pas
     *     seulement MoveNext) : `BattleQuery.IterateAdjacentTiles @181070df0` range
     *     param3/4/5 en ASCENDANT (+0x41/+0x43/+0x45) mais `TileQuery
     *     .IterateAdjacentTiles @1810acae0` les range en INVERSE (param3->+0x45,
     *     param5->+0x41). `d__8.MoveNext` lit ascendant = (IsTemporary, IsWalkable,
     *     IsEmptyOrSteppable). Net -> mapping RÉEL : **param3=requireEmptyOrSteppable
     *     (occupance), param4=requireWalkable (murs), param5=allowTemporary**
     *     (polarité inversée : 1=inclure). L'ANCIEN `(true,true,true)` — copié à tort
     *     de `GetFreeAdjacentTiles @181061650` (tuiles LIBRES) — EXCLUAIT les tuiles
     *     OCCUPÉES (param3=requireEmptyOrSteppable=1) ET les murs (param4=1), gelant
     *     l'occupance de CAPTURE dans un graphe censé STATIQUE (2 unités voisines
     *     mutuellement absentes de leurs neighbours). Le complet = param3=0 (inclure
     *     occupées) + param4=0 (inclure murs) + param5=1 (inclure temporaires).
     *     Murs + occupants = PROPRIÉTÉS de tuile (`walkable` ci-dessous /
     *     `occupantUnitId` / positions live), filtrées PAR LE CONSOMMATEUR
     *     (WalkPathfinder.IsValidPathNode @180f2ee50 -> `is_valid_path_node` côté
     *     port), PAS des arêtes manquantes.
     *   - `walkable` : `BattleQuery.IsWalkableTile(tile)` = le `TileExtensions
     *     .IsWalkable` consommé par IsValidPathNode (≠ isWall TileComponent ; on
     *     garde les deux pour recoupement).
     *  Graphe STATIQUE (les tuiles ne bougent pas) → capter UNE fois par bataille.
     *  Les occupants (dynamiques) se dérivent côté moteur via les positions
     *  d'unités (decisionView). Read-only. body: { runnerId? }. */
    ctx.rpc.boardGraph = (
        body?: { runnerId?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
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
        if (servicesOff < 0 || battleInServicesOff < 0) {
            return { ok: false, error: "services/Battle offsets unresolved" };
        }
        const services = runner.add(servicesOff).readPointer();
        if (services.isNull()) return { ok: false, error: "EntityServices null" };
        const battleQ = services.add(battleInServicesOff).readPointer();
        if (battleQ.isNull()) return { ok: false, error: "BattleQuery null (<Battle>)" };
        const bqClass = battleQ.readPointer();
        // GetAdjacentTiles(tile, bool, bool, bool) = 4 params (l'autre overload
        // prend une List → 3 params). IsWalkableTile(tile) = 1 param.
        const getAdjMi = findMethodByParamCount(bqClass, "GetAdjacentTiles", 4);
        if (!getAdjMi) {
            return { ok: false, error: "GetAdjacentTiles(4) non résolu sur "
                + s(class_get_name(bqClass) as NativePointer) };
        }
        const isWalkMi = findMethodByParamCount(bqClass, "IsWalkableTile", 1);

        // Props statiques par tuile (col/row/élévation/isWall) via la projection.
        const proj = projectMatchState(statePtr, { includeTiles: true });
        const projTiles = proj.tiles ?? [];
        const idByCoord = new Map<string, number>();
        for (const t of projTiles) idByCoord.set(t.col + "," + t.row, t.id);
        // ptr natif par id de tuile (pour les appels GetAdjacentTiles/IsWalkableTile).
        const ptrById = new Map<number, NativePointer>();
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty === EntityType.Tile) ptrById.set(id, e);
        });

        // OCCUPANCE par tuile : tile_entity_id -> squad unitId qui l'occupe. Lue via
        // les UnitFoot (UnitFootComponent.UnitId@0x10, TileId@0x14) → couvre les
        // EMPREINTES MULTI-HEX (une unité 2-3 hex = plusieurs UnitFoot → plusieurs
        // tuiles occupées). Indispensable au pathfinding fidèle : UnitIsBlockedByEnemyUnit
        // @180f2ef50 bloque l'entrée sur TOUTE tuile occupée par l'ennemi, pas que sa
        // tuile principale (sinon le moteur traverse les tuiles d'empreinte → sur-portée).
        const occByTile = new Map<number, number>();
        if (unitFootComponentClass) {
            forEachEntity(statePtr, (e, _id, ty) => {
                if (ty !== EntityType.UnitFoot) return;
                forEachComponent(e, (comp, klass) => {
                    if (!klass.equals(unitFootComponentClass!)) return;
                    try {
                        const footUnit = comp.add(0x10).readS32();   // UnitId (squad)
                        const footTile = comp.add(0x14).readS32();   // TileId (entité tuile)
                        occByTile.set(footTile, footUnit);
                    } catch { /* skip */ }
                });
            });
        }

        const bTrue = Memory.alloc(1); bTrue.writeU8(1);
        const bFalse = Memory.alloc(1); bFalse.writeU8(0);
        let adjCalls = 0; let adjFails = 0; let walkFails = 0;
        const tiles = projTiles.map((t) => {
            const e = ptrById.get(t.id);
            const neighbours: number[] = [];
            let walkable: boolean | null = null;
            if (e && !e.isNull()) {
                try {
                    // #148 : (param3=requireEmptyOrSteppable=0, param4=requireWalkable=0,
                    // param5=allowTemporary=1) = graphe géométrique COMPLET (occupance/walkable
                    // dérivés dynamiquement côté moteur). Mapping via ctors @181070df0/@1810acae0.
                    const os = invokeMethod(getAdjMi.info, battleQ, [e, bFalse, bFalse, bTrue]);
                    adjCalls++;
                    for (const n of extractTilePtrs(os)) {
                        const nid = idByCoord.get(n.col + "," + n.row);
                        if (typeof nid === "number" && nid !== t.id) neighbours.push(nid);
                    }
                } catch { adjFails++; }
                if (isWalkMi) {
                    try {
                        const r = invokeMethod(isWalkMi.info, battleQ, [e]);
                        walkable = !r.isNull() && r.add(0x10).readU8() !== 0;
                    } catch { walkFails++; }
                }
            }
            return {
                id: t.id, col: t.col, row: t.row, elevation: t.elevation,
                // tileDefId = terrain (TileId de la BC : Grass/DryBush/Trench/FirstAid/...) — source des
                // effets de tuile (LightCover=DryBush, Trench, ...) pour le moteur (docs/rl/terrain-effects.md).
                // isTemporary = tuile temporaire (HulkDoor, tuiles posees en combat).
                tileDefId: t.tileDefId ?? null, isTemporary: t.isTemporary ?? false,
                isWall: t.isWall, walkable, neighbours,
                occupantUnitId: occByTile.get(t.id) ?? null,
            };
        });
        return {
            ok: true, runner: label, tileCount: tiles.length,
            occupiedTiles: occByTile.size,
            adjCalls, adjFails, walkFails, tiles,
        };
    });

    /** DISTANCE-CHEMIN par tuile candidate → ennemi le plus proche (doc §13.12).
     *  Le move natif (UnitMovement(6) MinDist) mesure une distance de CHEMIN via
     *  `Pathfinders.GetPath(unit, from, to).Count`, PAS hex. On l'expose pour le moteur :
     *  pour `unitId`, distance-chemin MIN de chaque tuile atteignable vers une tuile ennemie.
     *  body: { runnerId, unitId }. Renvoie tiles:[{col,row,pathDist}] (-1 = inatteignable). */
    ctx.rpc.pathDistToEnemies = (
        body?: { runnerId?: number; unitId?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (pathfindersOff < 0) {
            return { ok: false, error: "runner.<Pathfinders>k__BackingField non résolu" };
        }
        if (typeof body?.unitId !== "number") return { ok: false, error: "unitId requis" };
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const pathfinders = runner.add(pathfindersOff).readPointer();
        if (pathfinders.isNull()) return { ok: false, error: "Pathfinders null" };
        const gp = resolveGetPath(pathfinders);
        if (!gp) return { ok: false, error: "Pathfinders.GetPath(4) non résolu" };
        const movementQuery = runner.add(movementQueryOff).readPointer();

        // Tuile ennemie (MainTile) de chaque unité adverse vivante (= !ctrl par le joueur courant).
        const enemyTiles: NativePointer[] = [];
        let me: NativePointer = ptr(0);
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit || !invokeBool(isAliveMi, [e, statePtr])) return;
            if (id === body.unitId) { me = e; return; }
            if (invokeBool(isCtrlByCurMi, [e, statePtr])) return;   // allié → pas une cible
            const t = getUnitMainTile(e, statePtr);
            if (t && !t.isNull()) enemyTiles.push(t);
        });
        if (me.isNull()) return { ok: false, error: "unit " + body.unitId + " introuvable/morte" };
        if (!enemyTiles.length) return { ok: false, error: "aucun ennemi vivant" };

        const tele = Memory.alloc(8); tele.writeU32(0); tele.add(4).writeU32(0);  // Nullable<UseTeleporter>=null
        const typeBuf = Memory.alloc(4); typeBuf.writeS32(1);  // PathfinderType=1 (cf. GetMinDistanceToEnemy)
        const pathLen = (from: NativePointer, to: NativePointer): number => {
            try {
                const p = invokeMethod(gp.info, pathfinders, [typeBuf, me, from, to, tele]);
                return (p.isNull()) ? -1 : p.add(LIST_SIZE).readS32();
            } catch {
                return -1;
            }
        };
        // Tuiles atteignables (GetMovableTilesFor) + tuile COURANTE (rester sur place).
        const boolBuf = Memory.alloc(1); boolBuf.writeU8(0);
        const optsBuf = Memory.alloc(0x30); for (let k = 0; k < 0x30; k += 4) optsBuf.add(k).writeU32(0);
        let tilePtrs: Array<{ ptr: NativePointer; col: number; row: number }> = [];
        try {
            const os = invokeMethod(getMovableTilesMi!.info, movementQuery, [me, boolBuf, optsBuf]);
            tilePtrs = extractTilePtrs(os);
        } catch (e) { return { ok: false, error: "GetMovableTilesFor: " + (e as Error).message }; }
        const cur = getUnitMainTile(me, statePtr);
        if (cur && !cur.isNull()) {
            const c = readTileCoord(cur);
            if (!tilePtrs.some((t) => t.col === c.col && t.row === c.row)) {
                tilePtrs.push({ ptr: cur, col: c.col, row: c.row });
            }
        }

        // #32 — FIDELITE MinDistanceToClosestEnemyUtility : le natif ne prend PAS le min sur TOUS les
        // ennemis. `GetMinDistanceToEnemy @1810f04a0` fait `IterateTiles(closestEnemy)` sur UN SEUL
        // ennemi = le `ClosestEnemy` precalcule par `MovementActionGenerator.FindClosestEnemy @181197f10`
        // (l'ennemi le plus proche de la POSITION COURANTE de l'unite, via `GetDistanceToEnemy @1811855e0`).
        // On reproduit : (1) selectionne le ClosestEnemy = argmin distance-de-chemin depuis la tuile
        // courante ; (2) mesure chaque tuile candidate vers CET ennemi. L'ancien min-sur-tous ecrasait
        // le tiebreak MinDist (toutes distances = la plus courte) -> divergence move-pur seed 909
        // (cf. docs/rl/agreement-stages.md lead 7 : natif MinDist 3/4/5 par tuile, nous 3 partout).
        let closestTile: NativePointer | null = null;
        if (cur && !cur.isNull()) {
            let best = -1;
            for (const et of enemyTiles) {
                const d = pathLen(cur, et);
                if (d >= 0 && (best < 0 || d < best)) { best = d; closestTile = et; }
            }
        }
        const distTo = (from: NativePointer): number => {
            if (closestTile) return pathLen(from, closestTile);
            // fallback (pas de tuile courante / aucun chemin depuis cur) : min-sur-tous (etat anterieur)
            let best = -1;
            for (const et of enemyTiles) {
                const d = pathLen(from, et);
                if (d >= 0 && (best < 0 || d < best)) best = d;
            }
            return best;
        };
        const tiles = tilePtrs.map((t) => ({ col: t.col, row: t.row, pathDist: distTo(t.ptr) }));
        return { ok: true, runner: label, unitId: body.unitId,
            enemyCount: enemyTiles.length, closestResolved: !!closestTile, tiles };
    });

}
