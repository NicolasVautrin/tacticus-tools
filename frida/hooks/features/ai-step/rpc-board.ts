/** RPCs BOARD/terrain/pathfinding : battleStatus, dumpRng, aiMovableTiles, tileMeta,
 *  boardGraph, pathDistToEnemies.
 *  Scinde de rpc-view.ts (2026-07-11, >2300 l. — seuil ~1000 l.) ; l'API RPC est
 *  INCHANGEE (memes noms ctx.rpc.*), agregee par registerView (rpc-view.ts). */
import {
    class_get_fields, class_get_name, class_get_namespace, field_get_name, field_get_offset,
    field_get_type, fieldOffsetOr, findClass, findClassAnywhere, findMethod,
    findMethodByParamClasses, findMethodByParamCount, getFieldOffset, readIl2cppString, s,
    type_get_class_or_element_class,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import { runnerClass, runnerOff } from "../../game/runner.js";
import { getRunner } from "../../game/runner-registry.js";
import { setTraceOrigin } from "../../game/trace-origin.js";
import {
    EntityType, forEachComponent, forEachEntity, playerComponentClass,
    projectMatchState, readBattleStatus, unitFootComponentClass,
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
    ActionResult, ActionSpec, activeAbilityMsgClass, applyOneAction, ARRAY_FIRST,
    attackQueryOff, battleInServicesOff, currentOwnerIsEnvMi, dpqInServicesOff, entityServicesClass,
    extractTiles, extractTilePtrs,
    entityExtClass, finishUnitTurnMsgClass, getMovableTilesMi, getOnlyTargetsMi, getTilesMi,
    getUnitMainTile,
    invokeBool, isAliveMi, isCtrlByCurMi, isIrrelevantObjMi, isTargetableMi,
    LIST_ITEMS, LIST_SIZE,
    moveUnitMsgClass, movementQueryOff,
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

// ─── #448-r1-r1-r1-r1-r2 — le `ConnectivityComponent` BRUT ──────────────────────────────────────
//
// POURQUOI IL FAUT UN SECOND CANAL, ET PAS UNE CORRECTION DU PREMIER.
// Le champ `neighbours` publié ci-dessous passe par `BattleQuery$$GetAdjacentTiles` ->
// `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, dont la porte
// `|srcElev - Elevation| < 2` est INCONDITIONNELLE. Elle ampute 18 arêtes dirigées sur `MC1_67`.
//
// Cette porte est JUSTE pour les consommateurs dont le natif est `IterateAdjacentTiles` — les
// sélecteurs `AdjacentTiles` du DSL (`Board.neighbours_native`), et `engine/services/ability_range.py`
// (#558), qui l'applique lui-même sans jamais lire `board.neighbours_*`. Elle est FAUSSE pour
// `IdunBattle.Entities.Pathfinding.BasePathfinder$$AddNeighbours`, dont le décompilé énumère la
// `List<int>` du `ConnectivityComponent` et ne teste AUCUNE élévation.
//
// ⇒ Toucher au champ existant CASSERAIT la première famille pour réparer la seconde. On AJOUTE
// donc `connectivity`, et `neighbours` reste bit-pour-bit ce qu'il était.
//
// LE NATIF, relu verbatim sur `rnca9r7q6c` (2026-08-04).
// `IdunBattle.Operations.InitializeConnectivityOperation$$Execute` construit la liste, une tuile à
// la fois, remis en C# :
//     foreach (edge in Enum.GetValues(typeof(TileEdge))) {
//         if (!TileComponent.HasEdge(srcComp, edge))                     continue;
//         (r, c) = (PositionComponent.RowAt(pos, edge), ColumnAt(pos, edge));
//         if (!BoardComponent.IsPositionInside(board, c, r))             continue;
//         nid = board.Grid[c, r];   if (nid == 0)                        continue;
//         if (!TileComponent.HasEdge(GetComponent<TileComponent>(nid),
//                                    (edgeCount / 2 + i) % edgeCount))   continue;   // arête OPPOSÉE
//         list.Add(nid);
//     }
//     GetComponent<ConnectivityComponent>(tile).<liste> = list;
// Le critère est donc purement TOPOLOGIQUE (arêtes des deux côtés + présence sur le plateau) :
// AUCUNE élévation n'y entre. C'est la confirmation par la CONSTRUCTION de ce que la mesure de
// `#448-r1-r1-r1-r1` avait établi par la conséquence (2 tuiles parcourues sur un vol qui exige une
// arête de Δélévation 2).
//
// `ConnectivityComponent` (0x20 boxé, donc 0x10 utile) porte DEUX champs, confirmés par trois
// lectures indépendantes :
//   * `+0x10` : `List<int>` d'entity ids de tuiles voisines — itérée par
//     `BasePathfinder.u003CAddNeighboursu003Ed__19$$MoveNext`, testée par
//     `ConnectivityComponent$$IsNeighbour` (`List.Contains`), reconstruite par
//     `ConnectivityComponent$$Copy` ;
//   * `+0x18` : `int` = l'entity id de la tuile de TÉLÉPORT jumelle, `0` = aucune. Écrit par
//     `InitializeConnectivityOperation$$ConnectTeleportTiles` (les deux tuiles se pointent
//     mutuellement) et lu par les quatre surcharges de
//     `IdunBattle.Entities.TileExtensions$$IsTeleportationTile`.
// Le publier ferme d'un coup DEUX résidus nommés qui citaient la même absence de canal :
// `AddTeleportationTiles` (base_pathfinder.py) et `IsTeleportationTile` (§10 de la case-doc de
// `#448-r1-r1-r1-r1`, le second critère de rétention d'un waypoint de `FlyPathfinder$$FindPath`).
//
// Les deux offsets sont RÉSOLUS PAR NOM DE CHAMP au runtime (`class_get_fields`), avec repli sur
// les littéraux ci-dessus ET publication du layout observé (`connectivityLayout`) : un capteur ne
// doit pas faire passer une lecture d'offset supposé pour une mesure.
const CONNECTIVITY_LIST_FALLBACK = 0x10;
const CONNECTIVITY_TELEPORT_FALLBACK = 0x18;

interface ConnectivityLayout {
    resolved: boolean;
    /** LEQUEL des trois chemins a servi. Un `resolved: true` ne dit pas COMMENT — et la
     *  différence compte : `"fallback"` signifie que la protection contre un changement de
     *  layout n'a pas joué, même si les offsets se trouvent être bons. */
    source: "name" | "type" | "fallback";
    listOffset: number;
    teleportOffset: number;
    fields: Array<{ name: string; offset: number; type: string }>;
    note: string;
}

/** Résout les deux offsets du `ConnectivityComponent` en énumérant SES champs déclarés (pas ceux
 *  de `IdunBattle.Core.BaseComponent`, son parent).
 *
 *  ⚠ MESURÉ le 2026-08-04 (`probe_448r1r1r1r1r2_connectivity_channel_live.py`, build `rnca9r7q6c`,
 *  trois boards) : le choix par TYPE seul **ne résolvait jamais** — le runtime déclare
 *
 *      ComponentId    @0x00  type=ComponentId
 *      NeighbourIds   @0x10  type=List`1
 *      TeleportTileId @0x18  type=BEntityId       <-- PAS `Int32`
 *
 *  donc `ints.length === 1` était faux (0 `Int32` déclarés) et la fonction retombait
 *  systématiquement sur les littéraux. Le repli tombait sur les BONS offsets — les mesures de la
 *  fenêtre restent valides, et c'est précisément parce que le layout observé était publié qu'on
 *  a pu le confronter — mais la résolution runtime, seule protection contre un changement de
 *  layout au prochain build, était INERTE. C'est le défaut que le capteur existait pour éviter.
 *
 *  On résout donc par NOM DÉCLARÉ d'abord (ce que le commentaire d'en-tête annonçait déjà), avec
 *  le choix par type en second et le littéral en dernier ; `source` publie lequel a servi, pour
 *  qu'aucun lecteur ne prenne un repli pour une résolution. Le type de la jumelle accepte
 *  `Int32` **ou** `BEntityId` : c'est un `struct` d'un seul `int` (écrit tel quel par
 *  `IdunBattle.Operations.InitializeConnectivityOperation$$ConnectTeleportTiles`, qui pose
 *  `*(comp + 0x18) = <entity id>`), donc `readS32` reste la lecture juste. */
function resolveConnectivityLayout(klass: NativePointer): ConnectivityLayout {
    const fields: Array<{ name: string; offset: number; type: string }> = [];
    try {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        for (;;) {
            const f = class_get_fields(klass, it) as NativePointer;
            if (f.isNull()) break;
            let type = "?";
            try {
                const tc = type_get_class_or_element_class(
                    field_get_type(f) as NativePointer) as NativePointer;
                if (!tc.isNull()) type = s(class_get_name(tc) as NativePointer);
            } catch { /* laisse "?" */ }
            fields.push({
                name: s(field_get_name(f) as NativePointer),
                offset: field_get_offset(f) as number, type,
            });
        }
    } catch { /* énumération best effort */ }
    // 1) par NOM déclaré — le plus spécifique, et ce que le runtime nomme lui-même.
    const byName = (n: string) => fields.filter((f) => f.name === n);
    const nList = byName("NeighbourIds");
    const nTel = byName("TeleportTileId");
    if (nList.length === 1 && nTel.length === 1) {
        return {
            resolved: true, source: "name",
            listOffset: nList[0].offset, teleportOffset: nTel[0].offset, fields,
            note: "offsets resolus par NOM declare (NeighbourIds / TeleportTileId)",
        };
    }
    // 2) par TYPE — repli si les champs ont été renommés. `BEntityId` est le type effectif de la
    //    jumelle sur `rnca9r7q6c` ; `Int32` reste accepté au cas où le wrapper disparaîtrait.
    const lists = fields.filter((f) => f.type.indexOf("List") === 0);
    const ints = fields.filter((f) => f.type === "Int32" || f.type === "BEntityId");
    if (lists.length === 1 && ints.length === 1) {
        return {
            resolved: true, source: "type",
            listOffset: lists[0].offset, teleportOffset: ints[0].offset, fields,
            note: "offsets resolus par TYPE (1 List + 1 Int32/BEntityId) — noms declares"
                + " introuvables, layout a reconfronter",
        };
    }
    // 3) littéraux du décompilé — jamais présenté comme une résolution.
    return {
        resolved: false, source: "fallback",
        listOffset: CONNECTIVITY_LIST_FALLBACK,
        teleportOffset: CONNECTIVITY_TELEPORT_FALLBACK,
        fields,
        note: "REPLI sur les litteraux du decompile — " + nList.length + "/" + nTel.length
            + " par nom, " + lists.length + " List / " + ints.length
            + " Int32|BEntityId par type ; confronter `fields`",
    };
}

const connectivityComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "ConnectivityComponent");
let connectivityLayout: ConnectivityLayout | null = null;
function getConnectivityLayout(): ConnectivityLayout | null {
    if (!connectivityComponentClass) return null;
    if (!connectivityLayout) {
        connectivityLayout = resolveConnectivityLayout(connectivityComponentClass);
    }
    return connectivityLayout;
}

/** Le `ConnectivityComponent` d'UNE entité tuile, tel quel.
 *  Tri-état assumé : `null` = le composant n'est pas porté par cette entité (ou la classe n'est pas
 *  résolue) — à ne PAS confondre avec `[]`, qui est une liste réellement vide. Les confondre est
 *  exactement la faute que `#381-r3` a déjà payée sur le champ `neighbours`. */
export function readConnectivity(entityPtr: NativePointer):
{ neighbours: number[]; teleportTwinTileId: number; rawSize: number } | null {
    const lay = getConnectivityLayout();
    if (!lay || !connectivityComponentClass) return null;
    let out: { neighbours: number[]; teleportTwinTileId: number; rawSize: number } | null = null;
    forEachComponent(entityPtr, (comp, klass) => {
        if (out !== null) return;
        if (!klass.equals(connectivityComponentClass)) return;
        const neighbours: number[] = [];
        let teleportTwinTileId = 0;
        // `rawSize` = le `_size` NATIF, publié même quand on refuse de le déréférencer. Sans lui,
        // une taille aberrante (offset faux, mémoire recyclée) rendrait `[]` — c'est-à-dire
        // « composant présent, aucune arête », qui se lit comme une MESURE. Le compteur
        // `connectivityOversize` la fait remonter au niveau réponse.
        let rawSize = -1;
        try {
            const list = comp.add(lay.listOffset).readPointer();
            if (!list.isNull()) {
                const items = list.add(LIST_ITEMS).readPointer();
                rawSize = list.add(LIST_SIZE).readS32();
                // Borne : une tuile hex a 6 voisins ; 64 laisse toute la marge d'un board
                // exotique tout en refusant une taille manifestement fausse.
                if (!items.isNull() && rawSize > 0 && rawSize <= 64) {
                    for (let i = 0; i < rawSize; i++) {
                        neighbours.push(items.add(ARRAY_FIRST + i * 4).readS32());
                    }
                }
            }
        } catch { /* liste illisible -> [] ; le composant EXISTE, on ne rend pas null */ }
        try { teleportTwinTileId = comp.add(lay.teleportOffset).readS32(); }
        catch { /* laisse 0 */ }
        out = { neighbours, teleportTwinTileId, rawSize };
    });
    return out;
}

// --- #175-r : PORTES ---------------------------------------------------------------------
// Deux composants, tous deux portés par des entités TUILE (mesuré sur le board `C6_09`, qui
// porte 3 portes) :
//   `IdunBattle.Entities.Components.DoorComponent`           : ActivationTiles(List<BEntityId>)
//                                                              @+0x10 · IsOpen(bool) @+0x18
//   `IdunBattle.Entities.Components.DoorActivationComponent`  : DoorTileId(BEntityId) @+0x10
// Le prédicat des deux feuilles est `!DoorComponent.IsOpen` de la porte DÉSIGNÉE par la tuile
// d'activation — cf. la note de `tileMeta`. Offsets résolus PAR NOM (`fieldOffsetOr`), repli
// sur le décompilé.
const doorComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "DoorComponent");
const doorActivationComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "DoorActivationComponent");
const DOOR_ACTIVATION_TILES_OFF = doorComponentClass
    ? fieldOffsetOr(doorComponentClass, "ActivationTiles", 0x10) : 0x10;
const DOOR_IS_OPEN_OFF = doorComponentClass
    ? fieldOffsetOr(doorComponentClass, "IsOpen", 0x18) : 0x18;
const DOOR_TILE_ID_OFF = doorActivationComponentClass
    ? fieldOffsetOr(doorActivationComponentClass, "DoorTileId", 0x10) : 0x10;

export interface TileDoorInfo {
    /** La tuile PORTE elle-même (elle porte le `DoorComponent`). */
    isDoor: boolean;
    /** `DoorComponent.IsOpen` — de CETTE tuile si c'est une porte, sinon de la porte
     *  désignée par `DoorActivationComponent.DoorTileId`. `null` = non lisible. */
    isOpen: boolean | null;
    /** La tuile est une tuile d'ACTIVATION (elle porte le `DoorActivationComponent`). */
    isActivationTile: boolean;
    /** Entity id de la tuile-porte désignée (tuile d'activation), sinon `null`. */
    doorTileId: number | null;
    /** Hex de cette tuile-porte, `null` si l'entité n'est pas une tuile projetée. */
    doorTile: { col: number; row: number } | null;
    /** Hex des tuiles d'activation (tuile PORTE seulement). */
    activationTiles: Array<{ col: number; row: number }>;
    /** Le PRÉDICAT NATIF des deux feuilles, tel quel : `isActivationTile && !isOpen`.
     *  Publié pour que le consommateur n'ait pas à le ré-assembler — c'est exactement
     *  ce que rend `…DoorOpeningUtility$$IsActivationTile`. `null` = non mesuré. */
    isActivationTileOfClosedDoor: boolean | null;
}

/** Lit les `BEntityId` d'une `List<BEntityId>` (items @0x10, size @0x18, éléments dès +0x20,
 *  stride 4). Borne haute assumée : au-delà, la liste est refusée plutôt que déréférencée. */
function readEntityIdList(list: NativePointer, cap: number): number[] {
    const out: number[] = [];
    if (list.isNull()) return out;
    try {
        const items = list.add(LIST_ITEMS).readPointer();
        const size = list.add(LIST_SIZE).readS32();
        if (items.isNull() || size <= 0 || size > cap) return out;
        for (let i = 0; i < size; i++) out.push(items.add(ARRAY_FIRST + i * 4).readS32());
    } catch { /* liste illisible -> [] */ }
    return out;
}

/** Map entityId de TUILE → info porte. Deux passes : d'abord les tuiles PORTE (pour connaître
 *  leur `IsOpen`), puis les tuiles d'ACTIVATION qui les désignent. Une tuile sans aucun des
 *  deux composants n'entre PAS dans la map (l'appelant publiera `null`). */
function readDoorsByTile(
    statePtr: NativePointer,
    ptrById: Map<number, NativePointer>,
    coordById: Map<number, { col: number; row: number }>,
): Map<number, TileDoorInfo> {
    const out = new Map<number, TileDoorInfo>();
    if (!doorComponentClass && !doorActivationComponentClass) return out;
    const isOpenByDoorTile = new Map<number, boolean>();
    // Passe 1 — les portes.
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Tile || !doorComponentClass) return;
        forEachComponent(e, (comp, klass) => {
            if (!klass.equals(doorComponentClass)) return;
            let isOpen: boolean | null = null;
            try { isOpen = comp.add(DOOR_IS_OPEN_OFF).readU8() !== 0; } catch { /* null */ }
            const acts: Array<{ col: number; row: number }> = [];
            try {
                for (const tid of readEntityIdList(
                    comp.add(DOOR_ACTIVATION_TILES_OFF).readPointer(), 64)) {
                    const c = coordById.get(tid);
                    if (c) acts.push(c);
                }
            } catch { /* [] */ }
            if (isOpen !== null) isOpenByDoorTile.set(id, isOpen);
            out.set(id, {
                isDoor: true, isOpen, isActivationTile: false,
                doorTileId: null, doorTile: null, activationTiles: acts,
                // Une tuile PORTE n'est pas une tuile d'activation : le prédicat natif est faux.
                isActivationTileOfClosedDoor: false,
            });
        });
    });
    // Passe 2 — les tuiles d'activation.
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Tile || !doorActivationComponentClass) return;
        forEachComponent(e, (comp, klass) => {
            if (!klass.equals(doorActivationComponentClass)) return;
            let doorTileId: number | null = null;
            try { doorTileId = comp.add(DOOR_TILE_ID_OFF).readS32(); } catch { /* null */ }
            const isOpen = (doorTileId !== null && isOpenByDoorTile.has(doorTileId))
                ? (isOpenByDoorTile.get(doorTileId) as boolean) : null;
            const prev = out.get(id);
            out.set(id, {
                isDoor: prev ? prev.isDoor : false,
                isOpen,
                isActivationTile: true,
                doorTileId,
                doorTile: (doorTileId !== null ? (coordById.get(doorTileId) ?? null) : null),
                activationTiles: prev ? prev.activationTiles : [],
                isActivationTileOfClosedDoor: isOpen === null ? null : !isOpen,
            });
        });
    });
    // `ptrById` n'est lu que pour attester que l'index a bien été construit par l'appelant :
    // sans lui, un `doorTileId` qui ne résout sur AUCUNE entité serait indiscernable d'un 0.
    for (const [id, info] of out) {
        if (info.doorTileId !== null && info.doorTileId !== 0
            && !ptrById.has(info.doorTileId)) {
            out.set(id, { ...info, doorTile: null });
        }
    }
    return out;
}

// --- #175-r : OCCUPANT + POWER-UP -----------------------------------------------------------
// `UnitExtensions$$GetUnit(tile, state)` = l'unité DEBOUT sur la tuile (le natif de la feuille
// `PowerUp(26)` n'utilise pas d'autre voie), et `UnitExtensions$$IsPowerUp(unit)` est INVOQUÉ :
// son corps itère `StaticBattleRules.TriggeredAbility$$GetPowerUps()` et teste
// `TriggeredAbilityComponent$$TryGetAbility` — une liste STATIQUE que le port n'a pas et qu'on
// se garde de re-dériver.
// ⚠ `GetUnit` a TROIS surcharges de MÊME arité 2 sur `UnitExtensions` (lues dans
// `data/symbols/<build>/frida/methods.tsv`) : `(IEntity, IMatchState)`,
// `(FootEntity, IMatchState)` et `(TileEntity, IMatchState)`. `findMethodByParamCount` en
// rendrait une AU HASARD — et deux des trois ne prennent pas une tuile. La feuille native passe
// `UnitPosition$$get_MainTile(...)`, donc une **TileEntity** : on désambiguïse par la CLASSE du
// premier paramètre, jamais par l'arité (même piège que les six ctors de `TargetingOptions`).
const getUnitOnTileMi = unitExtClass
    ? findMethodByParamClasses(unitExtClass, "GetUnit", ["TileEntity", null]) : null;
const isPowerUpMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "IsPowerUp", 1) : null;

/** Map entityId de TUILE → { occupantId, isPowerUp }. Absente = aucun occupant.
 *  `isPowerUp: null` = PAS MESURÉ (méthode non résolue ou invocation en erreur). */
function readTileOccupants(
    statePtr: NativePointer,
    idByPtr: Map<string, number>,
    tiles: Array<{ id: number }>,
): Map<number, { occupantId: number | null; isPowerUp: boolean | null }> {
    const out = new Map<number, { occupantId: number | null; isPowerUp: boolean | null }>();
    if (!getUnitOnTileMi) return out;
    const ptrByTileId = new Map<number, NativePointer>();
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty === EntityType.Tile) ptrByTileId.set(id, e);
    });
    for (const t of tiles) {
        const tilePtr = ptrByTileId.get(t.id);
        if (!tilePtr) continue;
        let unit: NativePointer;
        try { unit = invokeMethod(getUnitOnTileMi.info, null, [tilePtr, statePtr]); }
        catch { continue; }
        if (unit.isNull()) continue;
        const occupantId = idByPtr.get(unit.toString()) ?? null;
        let isPowerUp: boolean | null = null;
        if (isPowerUpMi) {
            try { isPowerUp = invokeBool(isPowerUpMi, [unit]); } catch { isPowerUp = null; }
        }
        out.set(t.id, { occupantId, isPowerUp });
    }
    return out;
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
     *  positions des summons (decisionView). Read-only.
     *
     *  #175-r — PORTE et OCCUPANT-POWERUP, les deux derniers sujets du `BLOCAGE: capteur`.
     *  Les deux feuilles restantes lisent des composants qu'AUCUN RPC ne remontait :
     *
     *  - `SummonDislikeDoorOpening(29)` / `HeroLikeDoorOpening(30)` :
     *    `IdunBattle.AI.Utilities.SummonDislikeDoorOpeningUtility$$IsActivationTile` et
     *    `IdunBattle.AI.Utilities.HeroDoorOpeningUtility$$IsActivationTile` ont le MÊME corps,
     *    lu à l'octet — `TryGetComponent<DoorActivationComponent>(tile)` puis
     *    `state.GetEntity(DoorActivationComponent.DoorTileId @+0x10)` puis
     *    `TryGetComponent<DoorComponent>(porte)` et le prédicat est
     *    **`DoorComponent.IsOpen @+0x18 == 0`** — donc « tuile d'activation d'une porte FERMÉE ».
     *    Ni la relation activation→porte ni l'état ouvert/fermé n'étaient lisibles.
     *  - `PowerUp(26)` : `IdunBattle.AI.Utilities.PowerUpTileUtility.u003CEvaluateMovementInSteps
     *    u003Ed__2$$MoveNext` fait `UnitExtensions.GetUnit(case.MovementTile.MainTile, state)`
     *    puis `UnitExtensions.IsPowerUp(occupant)`. Ce dernier n'est PAS un trait : il itère
     *    `StaticBattleRules.TriggeredAbility$$GetPowerUps()` et teste
     *    `TriggeredAbilityComponent$$TryGetAbility` — donc INVOQUÉ, jamais re-dérivé.
     *
     *  `roomTileType` (`TileComponent+0x44`, 0=Floor/1=Wall/2=Door) et `isInFog` (`+0x40`)
     *  étaient déjà PROJETÉS par `projectMatchState` et simplement pas publiés ici.
     *  Tri-état : `null` = PAS MESURÉ (classe/méthode non résolue), jamais rabattu sur `false`.
     *  `includeInactive` publie AUSSI les effets de tuile posés-mais-INACTIFS, avec
     *  leur flag `active` (défaut FAUX = comportement historique, que tous les
     *  consommateurs actuels supposent) — strict pendant de `decisionView`, même
     *  raison : sans lui, l'absence d'un effet de tuile est AMBIGUË (non-posé ou
     *  posé-inactif ?). C'est exactement ce qui laisse #368 sans verdict sur la
     *  tuile NON MARCHABLE de la zone de `1148 DaemonicOrdnance` — cf.
     *  `docs/rl/case-368-pose-daemonic-ordnance.md`.
     *  body: { runnerId?, includeInactive?=false } */
    ctx.rpc.tileMeta = (
        body?: { runnerId?: number; includeInactive?: boolean },
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
        const includeInactive = body?.includeInactive === true;
        const effectsByTile = readEffectsByTile(statePtr, { includeInactive });
        // --- #175-r : porte + occupant, lus sur les composants NATIFS -------------------
        // Index (ptr -> entityId) et (entityId -> coord) : le premier pour re-identifier
        // l'occupant rendu par `GetUnit`, le second pour nommer la tuile-porte en hex.
        const idByPtr = new Map<string, number>();
        const ptrById = new Map<number, NativePointer>();
        forEachEntity(statePtr, (e, id) => {
            idByPtr.set(e.toString(), id); ptrById.set(id, e);
        });
        const coordById = new Map<number, { col: number; row: number }>();
        for (const t of (proj.tiles ?? [])) coordById.set(t.id, { col: t.col, row: t.row });
        const doorInfoByTile = readDoorsByTile(statePtr, ptrById, coordById);
        const occupantByTile = readTileOccupants(statePtr, idByPtr, proj.tiles ?? []);
        const tiles = (proj.tiles ?? []).map((t) => {
            const effs = effectsByTile.get(t.id) ?? [];
            const door = doorInfoByTile.get(t.id) ?? null;
            const occ = occupantByTile.get(t.id) ?? null;
            return {
                col: t.col, row: t.row, elevation: t.elevation,
                isWall: t.isWall, isTemporary: t.isTemporary, isTerritory: t.isTerritory,
                // #175-r — déjà projetés par `projectMatchState`, jamais publiés ici.
                isInFog: t.isInFog, roomTileType: t.roomTileType,
                // #175-r — `door` : `null` = ni porte ni tuile d'activation (mesure FAITE) ;
                // `doorMeasured: false` = les classes natives ne sont pas résolues.
                door,
                // #175-r — occupant : `occupantId` = `UnitExtensions$$GetUnit(tile, state)`,
                // `occupantIsPowerUp` = `UnitExtensions$$IsPowerUp` INVOQUÉ (tri-état).
                occupantId: occ ? occ.occupantId : null,
                occupantIsPowerUp: occ ? occ.isPowerUp : null,
                // effects: liste des effets de statut sur la tuile (name = clé de poids
                // Default.TileEffects ; effectType/source pour le multiplicateur natif).
                // `active` n'est publié que sous `includeInactive` — sinon il vaut toujours
                // true (les inactifs sont filtrés en amont) et le champ mentirait par omission.
                effects: effs.map((e) => ({
                    name: e.name, effectType: e.effectType,
                    source: e.source, remaining: e.remaining, level: e.level,
                    ...(includeInactive ? { active: e.active } : {}),
                })),
            };
        });
        return {
            ok: true, runner: label, tileCount: tiles.length, tiles,
            // #175-r — CE QUE LES CAPTEURS ONT RÉSOLU. Sans ce bloc, un `door: null` sur
            // TOUTES les tuiles se lit « ce board n'a pas de porte » alors qu'il peut vouloir
            // dire « la classe `DoorComponent` n'est pas résolue ». Même règle que
            // `abilityStateLayout` de `decisionView` : le lecteur ne DEVINE pas.
            doorMeasured: doorComponentClass !== null
                && doorActivationComponentClass !== null,
            occupantMeasured: getUnitOnTileMi !== null,
            powerUpMeasured: isPowerUpMi !== null,
        };
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
        let adjCalls = 0; let adjFails = 0; let walkFails = 0; let adjUnmapped = 0;
        // #448-r1-r1-r1-r1-r2 — compteurs du canal BRUT, pour que son absence se DISE au lieu de
        // se lire comme « le natif n'a aucune arête » : `connMissing` = tuiles sans composant.
        let connFound = 0; let connMissing = 0; let connEdges = 0; let connTeleports = 0;
        let connOversize = 0;
        const tiles = projTiles.map((t) => {
            const e = ptrById.get(t.id);
            const neighbours: number[] = [];
            let walkable: boolean | null = null;
            // Tri-état STRICT : `null` = pas de `ConnectivityComponent` sur cette entité (ou classe
            // non résolue) ; `[]` = composant présent, liste vide. Cf. `#381-r3`.
            let connectivity: number[] | null = null;
            let teleportTwinTileId: number | null = null;
            if (e && !e.isNull()) {
                const conn = readConnectivity(e);
                if (conn) {
                    connectivity = conn.neighbours;
                    teleportTwinTileId = conn.teleportTwinTileId;
                    connFound++;
                    connEdges += conn.neighbours.length;
                    if (conn.teleportTwinTileId !== 0) connTeleports++;
                    // `_size` natif hors bornes = liste NON déréférencée : `connectivity` vaut
                    // `[]` sans être une mesure. On le COMPTE plutôt que de le taire.
                    if (conn.rawSize > 64 || conn.rawSize < 0) connOversize++;
                } else { connMissing++; }
            }
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
                        // #589-r1-r1-r2-r1-r4 — un voisin que le natif REND et que la table
                        // (col,row) ne sait pas remapper etait JETE EN SILENCE : l'arete
                        // disparaissait du graphe sans qu'aucun compteur ne bouge, et se lisait
                        // ensuite « le natif n'a pas cette arete ». On le COMPTE. Le remapping
                        // reste par coordonnee (les consommateurs du port indexent ainsi), mais
                        // sa perte n'est plus muette. `adjacentTilesNative` publie, lui, la
                        // liste NON remappee.
                        else if (typeof nid !== "number") adjUnmapped++;
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
                // #403 — `IsInFogOfWar` (TileComponent @0x40). Le capteur le LISAIT deja
                // (`match-state.ts` `tileIsInFog`, projete par `projectTile`) mais le
                // `boardGraph` ne le PUBLIAIT pas : l'arete de vol du port ne portait donc
                // que `!IsWall`, la ou `FlyPathfinder$$IsValidPathNode` teste
                // `!IsInFogOfWar && !IsWall`. Degradation PERMISSIVE sur la seule TRAVERSEE
                // (l'ARRIVEE restait gardee par `walkable`, qui inclut le volet fog).
                isWall: t.isWall, isInFog: t.isInFog ?? false, walkable, neighbours,
                // #448-r1-r1-r1-r1-r2 — le `ConnectivityComponent` BRUT, sans la porte
                // d'élévation que `neighbours` (via `TileQuery$$IterateAdjacentTiles`) applique.
                // C'est la source de `BasePathfinder$$AddNeighbours` ; `neighbours` reste la
                // source des sélecteurs `AdjacentTiles`. Les deux coexistent PAR FIDÉLITÉ —
                // chacun mirroir du natif de SON consommateur (cf. le bloc en tête de module).
                connectivity, teleportTwinTileId,
                occupantUnitId: occByTile.get(t.id) ?? null,
            };
        });
        // ─── #311 — POSITION DE MACHINE DE GUERRE, PAR JOUEUR ────────────────────────────
        //
        // POURQUOI ICI. `GetTargetAreaTiles` de `1148 DaemonicOrdnance` fait dépendre la
        // DIRECTION de son triangle de zone de `If(IsPositionMachineForCurrentPlayer(2), 1, 4)`.
        // Ce prédicat n'interroge AUCUNE machine déployée : c'est une propriété du PLATEAU.
        // Le port lisait `MachineComponent.Position` de la MoW déployée et se trompait de
        // cible (52 vs 53, mesuré sur `MC1_67` SANS aucune MoW). Faute de canal, il rend
        // aujourd'hui `None` (= non mesuré) plutôt que de deviner — et il a raison de refuser :
        // un repli naïf serait faux sur ~74 % des plateaux (balayage des 675 boards : 502
        // déclarent une valeur, 173 l'autre).
        //
        // CE QU'ON N'INVENTE PAS. On n'expose PAS la config brute et on ne relit PAS
        // `SpawnPointGroupConfiguration+0x14` nous-mêmes : on invoque la fonction NOMMÉE que
        // le jeu appelle lui-même, `IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer(player)`.
        // Son corps (relu sur `rnca9r7q6c`) lit le TeamId du joueur (`PlayerComponent+0x24`),
        // appelle `IdunBattle.Configuration.SpawnPointSetConfiguration$$GroupForPlayer(teamId,
        // playerNr)` et rend le champ du groupe — AVEC son repli natif quand aucun groupe ne
        // correspond (`teamId 1 -> 2`, `teamId 2 -> 1`, sinon 0). L'invoquer nous donne donc
        // la valeur EFFECTIVE, repli compris, au lieu d'une reconstitution qui pourrait diverger.
        //
        // Tri-état : `null` = pas mesuré (méthode irrésolue), `[]` = mesuré et aucun joueur.
        // Les confondre ferait passer un capteur MORT pour un plateau sans joueurs.
        const posMachineMi = findMethodByParamCount(
            bqClass, "GetPositionMachineForPlayer", 1);
        let mowPositions: Array<{
            playerId: number; teamId: number | null;
            machineOfWarPosition: number | null; error?: string;
        }> | null = null;
        if (posMachineMi) {
            mowPositions = [];
            forEachEntity(statePtr, (e, id, ty) => {
                if (ty !== EntityType.Player) return;
                let teamId: number | null = null;
                if (playerComponentClass) {
                    forEachComponent(e, (comp, klass) => {
                        if (!klass.equals(playerComponentClass!)) return;
                        try { teamId = comp.add(0x24).readS32(); } catch { /* laisse null */ }
                    });
                }
                try {
                    const boxed = invokeMethod(posMachineMi.info, battleQ, [e]);
                    mowPositions!.push({ playerId: id, teamId,
                        machineOfWarPosition: boxed.isNull()
                            ? null : boxed.add(0x10).readS32() });
                } catch (err) {
                    mowPositions!.push({ playerId: id, teamId,
                        machineOfWarPosition: null, error: (err as Error).message });
                }
            });
        }

        return {
            ok: true, runner: label, tileCount: tiles.length,
            occupiedTiles: occByTile.size,
            adjCalls, adjFails, walkFails, adjUnmapped, tiles,
            mowPositions,
            // #448-r1-r1-r1-r1-r2 — le canal BRUT se DÉCRIT lui-même. Sans ce bloc, un
            // `connectivity: null` partout serait indiscernable d'un plateau sans arêtes ;
            // avec lui, `connectivityClassResolved: false` le dit. `connectivityEdges` vs la
            // somme des `neighbours` donne, en UNE mesure, l'amputation exacte du champ hérité
            // (attendu : +18 arêtes dirigées sur `MC1_67`, la mesure de `#448-r1-r1-r1-r1` §9).
            connectivityClassResolved: !!connectivityComponentClass,
            connectivityLayout: getConnectivityLayout(),
            connectivityTiles: connFound, connectivityMissing: connMissing,
            connectivityEdges: connEdges, connectivityTeleportTiles: connTeleports,
            // > 0 ⇒ des `_size` hors bornes : les `connectivity: []` de ces tuiles ne sont PAS
            // des mesures. Non nul ⇒ relire `connectivityLayout` avant toute exploitation.
            connectivityOversize: connOversize,
            neighbourEdges: tiles.reduce((n, t) => n + t.neighbours.length, 0),
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
        // #57l/#26 — MIROIR COMPLET des filtres de `MovementActionGenerator.<FindClosestEnemy>d__8
        // .MoveNext @181197f10` (ordre natif) : le natif ne mesure MinDist(16) QU'AUX ennemis
        // CIBLABLES — skip si `CurrentOwnerIsEnvironment @180eb4d00` (unité du joueur Environment/
        // neutre), si `!IsTargetable @180ed8ff0` (deep-strike non atterri, flag 0x11 — sans ce filtre
        // un Dante deep-strike plus proche par chemin écrasait le vrai ClosestEnemy : 12345 s5, (1,4)
        // valait 6 vers Dante vs 7 vers l'ennemi ciblable), si `IsIrrelevantObject @180ed86d0` (décor :
        // trait 27, ou trait 13 avec stat0<=0), si mort (IsAlive ci-dessus). Chaque prédicat est
        // guardé : méthode non résolue => pas de filtre (dégradation sûre).
        let cands: Array<{ tile: NativePointer; id: number }> = [];
        let me: NativePointer = ptr(0);
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit || !invokeBool(isAliveMi, [e, statePtr])) return;
            if (id === body.unitId) { me = e; return; }
            if (invokeBool(isCtrlByCurMi, [e, statePtr])) return;   // allié → pas une cible
            if (currentOwnerIsEnvMi && invokeBool(currentOwnerIsEnvMi, [e, statePtr])) return;
            if (isTargetableMi && !invokeBool(isTargetableMi, [e])) return;
            if (isIrrelevantObjMi && invokeBool(isIrrelevantObjMi, [e])) return;
            const t = getUnitMainTile(e, statePtr);
            if (t && !t.isNull()) cands.push({ tile: t, id });
        });
        if (me.isNull()) return { ok: false, error: "unit " + body.unitId + " introuvable/morte" };
        // #26 — `GetOnlyTargets @180ed1b10` sur l'unité qui BOUGE : si la liste (List<int> d'ids de
        // cibles FORCÉES — taunt/forced-target) est non vide, le natif restreint le ClosestEnemy aux
        // ids CONTENUS (List.Contains). Si la restriction VIDE le set (cible forcée morte/non-ciblable),
        // le natif rend ClosestEnemy=null (comportement aval non RE'd) → on GARDE le set non restreint
        // (dégradation sûre, signalée par onlyTargetsUnmatched).
        let onlyTargetsCount = 0; let onlyTargetsUnmatched = false;
        if (getOnlyTargetsMi) {
            try {
                const lst = invokeMethod(getOnlyTargetsMi.info, null, [me]);
                if (!lst.isNull()) {
                    const n = lst.add(LIST_SIZE).readS32();
                    const items = lst.add(0x10).readPointer();
                    const ids = new Set<number>();
                    for (let i = 0; i < n && !items.isNull(); i++) {
                        ids.add(items.add(ARRAY_FIRST + 4 * i).readS32());
                    }
                    onlyTargetsCount = ids.size;
                    if (ids.size) {
                        const kept = cands.filter((c) => ids.has(c.id));
                        if (kept.length) cands = kept;
                        else onlyTargetsUnmatched = true;
                    }
                }
            } catch { /* dégradation sûre : pas de restriction */ }
        }
        // Set de candidats VIDE après les prédicats de `FindClosestEnemy` : côté natif c'est
        // `ClosestEnemy == null`, donc le gate d'entrée #3 de la feuille MinDist(16)
        // (`<EvaluateMovementInSteps>d__2.MoveNext` → 0 sur TOUTE tuile), pas une panne du RPC.
        // `noTargetableEnemies` le dit STRUCTURELLEMENT — le port le distinguait jusqu'ici du
        // littéral d'erreur, qui reste en place pour les lecteurs existants (#236).
        if (!cands.length) {
            return { ok: false, error: "aucun ennemi vivant", noTargetableEnemies: true };
        }

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
        // `closestEnemyId` = l'ID de l'unite retenue (pas seulement le booleen `closestResolved`) :
        // c'est le `case.ClosestEnemy` (`UtilityMovementCase+0x20`) que la feuille MinDist(16) lit
        // pour son gate 4 (`UnitCanBeDamaged` -> `HasTrait(Impervious)` sur CETTE unite). Sans lui, le
        // port ne peut trancher l'identite que si les candidats sont unanimes sur le trait, et laisse
        // sinon le gate SUSPENDU (#236 §5). Meme regle de departage que le natif
        // (`IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext` :
        // remplacement sur `<` STRICT, donc KEEP-FIRST a egalite) ; l'ORDRE d'enumeration differe en
        // revanche (`forEachEntity` ici, `StateExtensions$$GetAllEnemyUnitsOfUnit` la-bas), donc a
        // egalite de distance-chemin l'ID retenu peut differer de l'argmin natif.
        let closestTile: NativePointer | null = null;
        let closestEnemyId: number | null = null;
        if (cur && !cur.isNull()) {
            let best = -1;
            for (const ec of cands) {
                const d = pathLen(cur, ec.tile);
                if (d >= 0 && (best < 0 || d < best)) {
                    best = d; closestTile = ec.tile; closestEnemyId = ec.id;
                }
            }
        }
        const distTo = (from: NativePointer): number => {
            if (closestTile) return pathLen(from, closestTile);
            // fallback (pas de tuile courante / aucun chemin depuis cur) : min-sur-tous (etat anterieur)
            let best = -1;
            for (const ec of cands) {
                const d = pathLen(from, ec.tile);
                if (d >= 0 && (best < 0 || d < best)) best = d;
            }
            return best;
        };
        const tiles = tilePtrs.map((t) => ({ col: t.col, row: t.row, pathDist: distTo(t.ptr) }));
        // #26 — positions des ennemis CIBLABLES retenus (post-filtres) : consommées par le moteur
        // (ctx.tgt_epos) comme seed du fallback HEX de MinDist(16) quand pathDist=-1 (inatteignable).
        const enemies = cands.map((c) => {
            const p = readTileCoord(c.tile);
            return { id: c.id, col: p.col, row: p.row };
        });
        return { ok: true, runner: label, unitId: body.unitId,
            enemyCount: cands.length, closestResolved: !!closestTile,
            closestEnemyId,
            enemies, onlyTargetsCount, onlyTargetsUnmatched, tiles };
    });

}
