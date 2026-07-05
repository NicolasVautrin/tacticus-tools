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
import { readEffectsByUnit, readEffectsByTile, readRoundCapClock } from "../../game/effects.js";
import { state } from "../../game/state.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { abilityName } from "../../data/ability-names.js";
import { TARGETING_RULE_BITS } from "../../data/targeting-rule-names.js";
import { Ctx } from "../../controller.js";
import {
    ActionResult, ActionSpec, activeAbilityMsgClass, applyOneAction,
    attackQueryOff, battleInServicesOff, dpqInServicesOff, extractTiles, extractTilePtrs,
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
// par tuile candidate → ennemi le plus proche, pour remplacer hexgeo.distance dans le moteur.
// Champ runner = auto-property `<Pathfinders>k__BackingField` (IPathfinders), PAS `_pathfinders`
// (ça c'est le Dict interne de la classe Pathfinders). GetPath résolu LAZY depuis la classe
// runtime de l'instance (robuste à l'assembly) : GetPath(unit, from, to, Nullable<UseTeleporter>)
// (4 params, overload @180f202b0 qui dérive le type pathfinder de l'unité). Count = long. du chemin.
const pathfindersOff = runnerClass
    ? getFieldOffset(runnerClass, "<Pathfinders>k__BackingField") : -1;
// --- Snapshot one-shot des stats de combat résolues (prédiction 100% offline, doc §16) ---
// `UnitExtensions.GetStat(actor, StatType, StatPart, Nullable<BEntityId>)` (static 4-args
// @180ed3cb0) → valeur résolue (boxée int @+0x10). StatPart.Current=0 = valeur courante.
// StatType (enum): Attack=0 Movement=1 Defense=3 Health=5 BlockChance=7 BlockDamage=8
// CriticalChance=9 CriticalDamage=10 FixedArmor=16 ExtraHits=17 ExtraPierceMelee=21
// ExtraPierceRanged=22 ExtraMaxDamage=25 ExtraPierce=26. Faction/class/profil/traits = gameconfig ;
// effets = decisionView. C'est le SEUL accès live (one-shot au chargement BC) du prédicteur offline.
const getStatMi = unitExtClass ? findMethodByParamCount(unitExtClass, "GetStat", 4) : null;
// StatType ids (enum) partagés par `combatSnapshot` + `statModSources` — source unique
// (évite la divergence si on ajoute un stat d'un côté seulement, cf. discipline « check own port »).
const COMBAT_STAT_IDS: Record<string, number> = {
    attack: 0, movement: 1, defense: 3, health: 5, blockChance: 7,
    blockDamage: 8, critChance: 9, critDamage: 10, fixedArmor: 16,
    extraHits: 17, activeAbilityLevel: 18, numberOfMembers: 20,
    extraPierceMelee: 21, extraPierceRanged: 22, extraHitsMelee: 23,
    extraMaxDamage: 25, extraPierce: 26,
};
// 5-param overload `GetPath(PathfinderType type, unit, from, to, Nullable<UseTeleporter>)`
// (@180f20190) — type=1 comme `GetMinDistanceToEnemy` (`GetPath(1, unit, evalTile, enemyTile, 0)`).
let getPathMi: { info: NativePointer; ptr: NativePointer } | null = null;
function resolveGetPath(pathfinders: NativePointer): typeof getPathMi {
    if (getPathMi) return getPathMi;
    try { getPathMi = findMethodByParamCount(pathfinders.readPointer(), "GetPath", 5); }
    catch { getPathMi = null; }
    return getPathMi;
}

export function registerView(ctx: Ctx): void {
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
     *     true,true,true)` — le set COMPLET non filtré (cf. `GetFreeAdjacentTiles`
     *     @181061650 qui appelle exactement ces flags puis filtre). L'adjacence
     *     du board est géométrique (les murs sont des PROPRIÉTÉS de tuile filtrées
     *     par IsWalkable, PAS des arêtes manquantes — cf. WalkPathfinder
     *     .IsValidPathNode @180f2ee50).
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
        let adjCalls = 0; let adjFails = 0; let walkFails = 0;
        const tiles = projTiles.map((t) => {
            const e = ptrById.get(t.id);
            const neighbours: number[] = [];
            let walkable: boolean | null = null;
            if (e && !e.isNull()) {
                try {
                    const os = invokeMethod(getAdjMi.info, battleQ, [e, bTrue, bTrue, bTrue]);
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
        const minToEnemies = (from: NativePointer): number => {
            let best = -1;
            for (const et of enemyTiles) {
                const d = pathLen(from, et);
                if (d >= 0 && (best < 0 || d < best)) best = d;
            }
            return best;
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
        const tiles = tilePtrs.map((t) => ({ col: t.col, row: t.row, pathDist: minToEnemies(t.ptr) }));
        return { ok: true, runner: label, unitId: body.unitId, enemyCount: enemyTiles.length, tiles };
    });

    /** SNAPSHOT one-shot des STATS DE COMBAT RÉSOLUES par unité (prédiction 100% offline,
     *  doc §16). Lit `UnitExtensions.GetStat(entity, StatType)` pour chaque stat combat-
     *  pertinente. C'est le SEUL accès live du prédicteur offline (à appeler une fois au
     *  chargement de la BattleConfig) ; faction/class/profil/traits viennent de gameconfig,
     *  effets de decisionView. Read-only. body: { runnerId } */
    ctx.rpc.combatSnapshot = (
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
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getStatMi) return { ok: false, error: "UnitExtensions.GetStat(4) non résolu" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };

        const STAT_IDS = COMBAT_STAT_IDS;
        const idBufs: Record<string, NativePointer> = {};
        for (const k of Object.keys(STAT_IDS)) {
            const buf = Memory.alloc(4); buf.writeS32(STAT_IDS[k]); idBufs[k] = buf;
        }
        const partBuf = Memory.alloc(4); partBuf.writeS32(0);        // StatPart.Current
        const partBufInit = Memory.alloc(4); partBufInit.writeS32(3); // StatPart.Initial (=base)
        // Nullable<BEntityId> = null (HasValue=false) : struct zéroé (taille large par sûreté).
        const nullId = Memory.alloc(16); for (let i = 0; i < 16; i += 4) nullId.add(i).writeS32(0);
        const getStatP = (e: NativePointer, k: string, pb: NativePointer): number | null => {
            try {
                const r = invokeMethod(getStatMi!.info, null, [e, idBufs[k], pb, nullId]);
                return r.isNull() ? null : r.add(0x10).readS32();
            } catch { return null; }
        };
        const getStat = (e: NativePointer, k: string): number | null => getStatP(e, k, partBuf);

        // DÉGÂT D'ARME de l'attaque normale (one-shot) : le dégât/hits ne sont PAS des StatType
        // unité (la stat Attack agrégée ≠ dégât d'arme résolu). On capture la PRÉDICTION native
        // de l'attaque normale par paire via `CachedDamagePredictionQuery.GetNormalAttackPrediction
        // (attacker, target, attackerPosition)` (slot 13) — contrairement à `GetAllPredictions`,
        // CE chemin ne filtre PAS par portée (cible explicite) → capturable à froid au déploiement.
        // Le dégât de BASE est indépendant de la cible (cf. mesures) sauf effets de réduction sur la
        // cible → on prend le MAX sur plusieurs cibles ennemies = base NON réduite.
        //   UnitPosition (dump.cs @385083) = struct 8o {IList Tiles} ; obtenue via
        //   UnitExtensions.GetUnitPosition(unit, state). DamagePredictionResult : AccurateHealthDamage
        //   Min@0x60/Max@0x64 ; TotalDamage Min@0x90/Max@0x94 ; AppliedHits@0xBC ; MightCrit@0xB1.
        const dpq = resolveDpq(runner);
        const getNormPredMi = dpq.isNull() ? null
            : findMethodByParamCount(dpq.readPointer(), "GetNormalAttackPrediction", 3);
        const getUnitPosMi = entityExtClass
            ? findMethodByParamCount(entityExtClass, "GetUnitPosition", 2) : null;
        // toutes les unités vivantes (servent de cibles de référence pour la prédiction)
        const allUnits: Array<{ e: NativePointer; id: number }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty === EntityType.Unit && invokeBool(isAliveMi, [e, statePtr])) {
                allUnits.push({ e, id });
            }
        });
        // DÉGÂT DE BASE de l'attaque normale (one-shot, iso-AI) via `GetNormalAttackPrediction
        // (attacker, target, pos)`. Ce chemin calcule pour les cibles ATTEIGNABLES (0 sinon) ; au
        // déploiement seuls les alliés sont adjacents → ils donnent la base (le dégât de base EST
        // indépendant de la cible, cf. mesures, sauf armes Blast/multi-membres). On retient donc
        // la meilleure entrée NON NULLE = dégât de base d'arme. Les réductions par cible sont
        // appliquées offline (decisionView.effects) ; le détail par cible (Blast) = amélioration.
        const readNormalAttack = (attacker: NativePointer): Record<string, unknown> => {
            if (dpq.isNull()) return { error: "dpq null" };
            if (!getNormPredMi) return { error: "GetNormalAttackPrediction(3) non résolu sur "
                + s(class_get_name(dpq.readPointer()) as NativePointer) };
            if (!getUnitPosMi) return { error: "GetUnitPosition(2) non résolu" };
            let posPtr: NativePointer;
            try {
                const pos = invokeMethod(getUnitPosMi.info, null, [attacker, statePtr]);
                if (pos.isNull()) return { error: "GetUnitPosition null" };
                posPtr = pos.add(0x10);                              // struct UnitPosition (8o)
            } catch (err) { return { error: "GetUnitPosition: " + (err as Error).message }; }
            let best: Record<string, unknown> | null = null;
            let reachable = 0;
            for (const t of allUnits) {
                if (t.e.equals(attacker)) continue;
                let boxed: NativePointer;
                try { boxed = invokeMethod(getNormPredMi.info, dpq, [attacker, t.e, posPtr]); }
                catch { continue; }
                if (boxed.isNull()) continue;
                const b = boxed.add(0x10);
                const hMax = b.add(0x64).readS32();
                if (hMax <= 0) continue;                             // cible non atteignable → 0
                reachable++;
                if (best === null || hMax > (best.maxDmg as number)) {
                    best = {
                        minDmg: b.add(0x60).readS32(), maxDmg: hMax,
                        hits: b.add(0xbc).readS32(), mightCrit: b.add(0xb1).readU8(),
                        vsTarget: t.id,
                    };
                }
            }
            if (best) { best.reachable = reachable; return best; }
            return { error: "aucune cible atteignable au déploiement (base non capturable)" };
        };

        // --- multiplier d'ability-variable PAR ENTITÉ (UnitConfiguration via BattleQuery.GetUnitConfig) ---
        // `AbilityVariablesMultiplierPercentage` (UnitConfiguration@0x74, dérivé progression) scale les
        // variables d'ability « rareté » (ex. PowerTrip.armorIgnored §17.21). PAS porté sur l'entité ; on
        // remonte via le registre `BattleQuery.GetUnitConfig(unitId)` (EntityServices.<Battle>@battleInServices).
        // Clé = la VisualId (string managée) de l'unité (UnitComponent.VisualId@0x20 ; Id==VisualId). Offsets
        // UnitConfiguration (dump gqfc5mff6c) : mult@0x74, tertiaryMult@0x78, Level@0x7C, ActiveAbilityLevel
        // @0xB8, PassiveAbilityLevel@0xBC (struct Level = int). Per-entité (≠ BC offline par visualId).
        const battleQ = (servicesOff >= 0 && battleInServicesOff >= 0)
            ? (() => {
                const sv = runner.add(servicesOff).readPointer();
                return sv.isNull() ? ptr(0) : sv.add(battleInServicesOff).readPointer();
            })() : ptr(0);
        const getUnitConfigMi = (!battleQ.isNull())
            ? findMethodByParamCount(battleQ.readPointer(), "GetUnitConfig", 1) : null;
        const unitCompClass = findClassAnywhere("IdunBattle.Entities.Components", "UnitComponent");
        const VISUALID_OFF = 0x20;     // (Base)UnitComponent.VisualId (System.String)
        const UCFG = { mult: 0x74, tertMult: 0x78, level: 0x7c, activeLvl: 0xb8, passiveLvl: 0xbc };
        const readUnitConfig = (e: NativePointer): Record<string, unknown> => {
            if (!getUnitConfigMi) return { error: "GetUnitConfig(1) non résolu" };
            if (!unitCompClass) return { error: "UnitComponent non résolu" };
            let vidPtr: NativePointer | null = null;
            forEachComponent(e, (comp, klass) => {
                if (vidPtr === null && klass.equals(unitCompClass)) {
                    const p = comp.add(VISUALID_OFF).readPointer();
                    if (!p.isNull()) vidPtr = p;
                }
            });
            if (!vidPtr) return { error: "visualId introuvable" };
            let cfg: NativePointer;
            try { cfg = invokeMethod(getUnitConfigMi.info, battleQ, [vidPtr]); }
            catch (err) { return { error: "GetUnitConfig: " + (err as Error).message }; }
            if (cfg.isNull()) return { error: "config null" };
            return {
                visualId: readIl2cppString(vidPtr),
                abilityVariablesMultiplier: cfg.add(UCFG.mult).readS32(),
                tertiaryAbilityVariablesMultiplier: cfg.add(UCFG.tertMult).readS32(),
                level: cfg.add(UCFG.level).readS32(),
                activeAbilityLevel: cfg.add(UCFG.activeLvl).readS32(),
                passiveAbilityLevel: cfg.add(UCFG.passiveLvl).readS32(),
            };
        };

        // BOUCLIERS (ShieldComponent @180fa8770) : liste d'instances @+0x10 (List<ShieldInstance>,
        // _items@+0x10/_size@+0x18 ; éléments = pointeurs, data array @+0x20). ShieldInstance :
        // id@+0x10, amount@+0x30, remaining Nullable<int>@+0x3c (None=permanent). Layout du Nullable
        // incertain → on émet remainingRaw=[s32@0x3c, s32@0x40] pour trancher en validation, + une
        // estimation `remaining` (convention .NET {hasValue@0, value@4} : has=byte@0x3c, val=s32@0x40).
        const shieldCompClass = findClassAnywhere("IdunBattle.Entities.Components", "ShieldComponent");
        const SH = { id: 0x10, amount: 0x30, rem0: 0x3c, rem1: 0x40 };
        const readShields = (e: NativePointer): Array<Record<string, unknown>> => {
            if (!shieldCompClass) return [];
            let comp: NativePointer | null = null;
            forEachComponent(e, (c, klass) => {
                if (comp === null && klass.equals(shieldCompClass)) comp = c;
            });
            if (comp === null) return [];
            const list = (comp as NativePointer).add(0x10).readPointer();
            if (list.isNull()) return [];
            const items = list.add(0x10).readPointer();
            const size = list.add(0x18).readS32();
            if (items.isNull() || size <= 0 || size > 64) return [];
            const out: Array<Record<string, unknown>> = [];
            for (let i = 0; i < size; i++) {
                const inst = items.add(0x20 + i * 8).readPointer();
                if (inst.isNull()) continue;
                const w0 = inst.add(SH.rem0).readS32();
                const w1 = inst.add(SH.rem1).readS32();
                const has = inst.add(SH.rem0).readU8();   // convention .NET hasValue@+0
                out.push({
                    id: inst.add(SH.id).readS32(),
                    amount: inst.add(SH.amount).readS32(),
                    remaining: has ? w1 : null,
                    remainingRaw: [w0, w1],
                });
            }
            return out;
        };

        const units: Array<Record<string, unknown>> = [];
        for (const { e, id } of allUnits) {
            const stats: Record<string, number | null> = {};
            // AXE STAT-MODIFICATION (§7bis prediction.md) : delta Current-Initial par StatType.
            // `CalculateModifiersFromStatModifications` @181004380 ne s'active QUE si CurrentValue !=
            // BaseValue → un delta non-nul = présence de modifications de stat (source des modifiers de
            // dégât par-cible non exposés comme effets nommés, ex. le +50% sur worldTerminator). Emis
            // pour NOMMER le modifier par capture (INPUT), pas pour deviner.
            const statDelta: Record<string, number> = {};
            for (const k of Object.keys(STAT_IDS)) {
                stats[k] = getStat(e, k);
                const init = getStatP(e, k, partBufInit);
                if (init !== null && stats[k] !== null && stats[k] !== init) {
                    statDelta[k] = (stats[k] as number) - init;
                }
            }
            units.push({
                entityId: id, ctrl: invokeBool(isCtrlByCurMi, [e, statePtr]),
                stats, statDelta, normalAttack: readNormalAttack(e), unitConfig: readUnitConfig(e),
                shields: readShields(e),
            });
        }
        return { ok: true, runner: label, statTypes: STAT_IDS, units };
    });

    /** PER-SOURCE STAT-MODIFICATION breakdown — la sonde DÉFINITIVE pour SOURCER un
     *  `statDelta` opaque : « le +1298 Attack sur u92 vient de QUELLE entité ? »
     *  devient une LECTURE au lieu d'une triangulation (base↔tuile + recon allié +
     *  gameconfig). Chemin natif VÉRIFIÉ (décompilé) :
     *    `UnitExtensions.GetStat(entity, statType, StatPart=5, Nullable<BEntityId> src)`
     *    → `StatComponent.GetStatPart @180fa8bb0` case 5/9 :
     *        • src.HasValue=false → `*(int*)(comp+0x10)` = TOTAL Σ des modifications
     *        • src.HasValue=true  → `ValueModification.GetModificationFromEntity(
     *            comp+0x10, srcId) @180fadf10` → Dict<BEntityId,Modifier> keyé par
     *          l'ENTITÉ SOURCE du buff → contribution de CETTE source.
     *  On lit le total (part 5, src null) par stat ; si non-nul, on SCANNE toutes les
     *  entités comme sources candidates (BEntityId = `forEachEntity` id) et on garde
     *  les contributions non-nulles. `residual = total - Σ(sources)` : 0 = tout
     *  attribué à des entités (cas aura d'allié / self-buff) ; non-nul = une source
     *  non-entité (modif SETUP `ModifyUnit*` / système) → à investiguer, pas deviner.
     *  Ne matérialise QUE ce qui est présent dans la ValueModification À CET INSTANT
     *  (une aura d'adjacence n'y est que si l'unité est actuellement adjacente au
     *  porteur — cf. #49 : re-évaluée par candidat en prédiction). Read-only, one-shot.
     *  body: { runnerId?, unitId?, stats?: string[], minAbs?=1 } */
    ctx.rpc.statModSources = (
        body?: {
            runnerId?: number; unitId?: number; stats?: string[]; minAbs?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getStatMi) return { ok: false, error: "UnitExtensions.GetStat(4) non résolu" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };

        const requested = (Array.isArray(body?.stats) && body!.stats!.length)
            ? body!.stats!.filter((k) => k in COMBAT_STAT_IDS)
            : Object.keys(COMBAT_STAT_IDS);
        const minAbs = typeof body?.minAbs === "number"
            ? Math.abs(body.minAbs) : 1;

        const idBufs: Record<string, NativePointer> = {};
        for (const k of requested) {
            const buf = Memory.alloc(4); buf.writeS32(COMBAT_STAT_IDS[k]); idBufs[k] = buf;
        }
        const partBuf5 = Memory.alloc(4); partBuf5.writeS32(5);   // StatPart = branche modification
        // Nullable<BEntityId> — layout Mono : hasValue byte @+0, value(int32 BEntityId) @+4.
        const nullSrc = Memory.alloc(16); for (let i = 0; i < 16; i += 4) nullSrc.add(i).writeS32(0);
        const srcBuf = Memory.alloc(16); for (let i = 0; i < 16; i += 4) srcBuf.add(i).writeS32(0);
        srcBuf.writeU8(1);   // HasValue = true (réécrit srcBuf+4 = value à chaque source)
        // GetStat(4-arg) rend un int BOXÉ → valeur signée @+0x10 (idem combatSnapshot).
        const getMod = (e: NativePointer, k: string, src: NativePointer): number => {
            try {
                const r = invokeMethod(getStatMi!.info, null, [e, idBufs[k], partBuf5, src]);
                return r.isNull() ? 0 : r.add(0x10).readS32();
            } catch { return 0; }
        };

        // Toutes les entités = sources candidates ; unités vivantes (filtrées par unitId) = cibles.
        const allEntities: Array<{ e: NativePointer; id: number; isUnit: boolean }> = [];
        const targetUnits: Array<{ e: NativePointer; id: number }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            const isUnit = ty === EntityType.Unit;
            allEntities.push({ e, id, isUnit });
            if (isUnit && (body?.unitId === undefined || id === body.unitId)
                && invokeBool(isAliveMi, [e, statePtr])) {
                targetUnits.push({ e, id });
            }
        });

        const units: Array<Record<string, unknown>> = [];
        for (const { e, id } of targetUnits) {
            const mods: Record<string, unknown> = {};
            for (const k of requested) {
                const total = getMod(e, k, nullSrc);
                if (Math.abs(total) < minAbs) continue;          // pas de modification → skip le scan
                const bySource: Array<Record<string, unknown>> = [];
                for (const src of allEntities) {
                    srcBuf.add(4).writeS32(src.id);              // value = BEntityId de la source
                    const amount = getMod(e, k, srcBuf);
                    if (amount !== 0) {
                        bySource.push({
                            source: src.id, amount,
                            self: src.id === id, sourceIsUnit: src.isUnit,
                        });
                    }
                }
                const attributed = bySource.reduce(
                    (a, b) => a + (b.amount as number), 0);
                mods[k] = { total, residual: total - attributed, bySource };
            }
            units.push({
                entityId: id, ctrl: invokeBool(isCtrlByCurMi, [e, statePtr]), mods,
            });
        }
        return { ok: true, runner: label, statTypes: COMBAT_STAT_IDS, units };
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
                    out.push({ kind: "tile", tile: { col: p.col, row: p.row } });
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
        let abilityState:
            { usable?: boolean; cooldown?: number | null; disabled?: boolean } | null = null;
        try {
            const ab = unitAbilityTypes(caster, true).find((x) => x.id === body.abilityType);
            if (ab && (ab.usable !== undefined || ab.cooldown !== undefined
                       || ab.disabled !== undefined)) {
                abilityState = {
                    usable: ab.usable, cooldown: ab.cooldown ?? null, disabled: ab.disabled,
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
                // NoBrokenTargetingRule = valide ; sinon règle non décodable en flag.
                return { ruleClass: clsName, hex: "0x0", reasons: [] };
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
        // Round-cap clock — board-wide bombardment telegraph (EnvEndBombardment_Incoming).
        // NOT in any unit's owned effects, so surfaced separately (cf. hypotheses.md H58).
        const roundCap = readRoundCapClock(statePtr);
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
            dangerZone: danger, roundCap,
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
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
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
