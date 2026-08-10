/** `#589-r1-r1-r2-r1-r4` — CAPTEUR : le ring-1 NATIF, tel que le selecteur DSL le voit.
 *
 *  ## Ce que le decompile a deja tranche, et ce qu'il ne tranche pas
 *
 *  Le residu laissait DEUX lectures ouvertes : « le selecteur est-il reellement geometrique, ou
 *  la capture `boardGraph` est-elle incomplete ? ». **La premiere est ELIMINEE par la lecture** :
 *
 *      // IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext
 *      elevOrigin = tile.<+0x20>.<+0x18>
 *      foreach (id in tile.<+0x30>.<+0x10>)          // une LISTE STOCKEE, aucune geometrie
 *          t = state.GetEntity(id)
 *          if (t == null) continue
 *          if (!allowTemporary   && TileExtensions$$IsTemporary(t))          continue
 *          if ( onlyWalkableTiles && !TileExtensions$$IsWalkable(t, true))    continue
 *          if ( onlyEmptyOrSteppable && !TileExtensions$$IsEmptyOrSteppable(t, state)) continue
 *          if (abs(elevOrigin - t.<+0x20>.<+0x18>) < 2) yield t
 *
 *  Aucun calcul de coordonnees : le ring-1 est une liste de voisins PORTEE PAR LA TUILE, filtree.
 *  Le selecteur ne peut donc pas « etre geometrique ».
 *
 *  Et la chaine du consommateur de `#589` est UNIQUE, contrairement a ce que sa fiche ecrivait :
 *
 *      DSLSelectors$$AdjacentFriends(unit, unique, selType)
 *        = Friends( unit, Units(AdjacentTiles(unit), unique, selType) - unit, selType )
 *      DSLSelectors$$AdjacentTiles(origin) -> new AdjacentTilesSelector(state, battleQuery, origin)
 *      IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select
 *        -> battleQuery.<slot 80 = IBattleQuery.IterateAdjacentTiles>(t, false, true, true)
 *      IdunBattle.Core.Services.BattleQuery.u003CIterateAdjacentTilesu003Ed__95$$MoveNext
 *        = foreach t in EntityExtensions$$IterateTiles(from) : foreach n in tileQuery.IterateAdjacentTiles(t, ...)
 *
 *  Le slot **80 = 0x50** est LU dans `data/symbols/<build>/metadata/interface_slots.tsv`
 *  (`IBattleQuery 80 IterateAdjacentTiles 4`), pas deduit du nom.
 *  ⇒ `AdjacentTilesSelector` et `BattleQuery$$IterateAdjacentTiles` lisent **LE MEME substrat**.
 *  L'affirmation inverse de `case-589-r1-r1-r2-r1` sec.6 est REFUTEE par ce chemin d'appel.
 *
 *  ## Reste donc a mesurer : POURQUOI la capture diverge
 *
 *  `boardGraph.neighbours` invoque `BattleQuery$$GetAdjacentTiles(tile, false, false, true)` —
 *  dont le corps est `new OrderedSet(6); AddRange(IterateAdjacentTiles(...))`, donc la
 *  materialisation EXACTE du meme iterateur — puis **reprojette chaque voisin en (col,row) et
 *  JETTE EN SILENCE celui qu'il ne sait pas remapper** (`idByCoord.get(...)`, sans compteur).
 *  Deux ecarts sont donc possibles entre ce que le selecteur voit et ce que le port lit :
 *   * les ARGUMENTS (`onlyWalkableTiles` vaut **true** pour le selecteur, **false** pour
 *     `boardGraph`) — le graphe est un SUR-ensemble, donc cet ecart ne peut pas faire manquer
 *     une arete ;
 *   * la REPROJECTION, qui, elle, le peut.
 *
 *  Ce RPC publie les voisins **par entityId ET par (col,row)**, sans jamais en jeter un, dans les
 *  DEUX regimes d'arguments, et accepte une UNITE comme origine (ce que `boardGraph`, indexe par
 *  tuile, ne sait pas faire alors que le selecteur, lui, part de `Owner`).
 *
 *  Aucun `Interceptor` : on INVOQUE la fonction nommee, on n'ancre rien.
 */
import { findMethodByParamCount, class_get_name, s } from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import {
    EntityType, forEachEntity, projectMatchState,
} from "../../game/match-state.js";
import { runnerOff } from "../../game/runner.js";
import { getRunner } from "../../game/runner-registry.js";
import { setTraceOrigin } from "../../game/trace-origin.js";
import { state } from "../../game/state.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { Ctx } from "../../controller.js";
import {
    battleInServicesOff, extractTilePtrs, getTilesMi, servicesOff,
} from "./internals.js";
import { readConnectivity } from "./rpc-board.js";

/** Les deux jeux d'arguments qui comptent, NOMMES — un booleen nu au site d'appel ne dit pas
 *  lequel des trois filtres il gouverne, et l'ordre reel a deja coute une inversion (#148). */
const REGIMES: Record<string, { oes: boolean; owt: boolean; at: boolean; why: string }> = {
    // `AdjacentTilesSelector$$Select` : `(t, 0, 1, 1)`, LU au decompile.
    selector: { oes: false, owt: true, at: true,
        why: "arguments EXACTS d'AdjacentTilesSelector$$Select" },
    // `boardGraph` : `(e, 0, 0, 1)` — le sur-ensemble geometrique.
    graph: { oes: false, owt: false, at: true,
        why: "arguments de boardGraph.neighbours (sur-ensemble)" },
};

export function registerViewAdjacency(ctx: Ctx): void {
    /** `adjacentTilesNative` — ce que `IBattleQuery.GetAdjacentTiles` rend REELLEMENT, par
     *  origine et par regime d'arguments.
     *
     *  body: { runnerId?, entityIds?: number[], tiles?: Array<{col,row}>, regimes?: string[] }
     *
     *  `entityIds` accepte des UNITES autant que des TUILES : `BattleQuery$$IterateAdjacentTiles`
     *  resout son `from` par `EntityExtensions$$IterateTiles`, donc l'union des ring-1 de tous les
     *  pieds. C'est la forme que prend l'appel quand le DSL passe `Owner`.
     *  Sans `entityIds` ni `tiles` : TOUTES les tuiles du plateau (le pendant de `boardGraph`,
     *  mais sans reprojection destructrice). Read-only. */
    ctx.rpc.adjacentTilesNative = (
        body?: {
            runnerId?: number; entityIds?: number[];
            tiles?: Array<{ col: number; row: number }>; regimes?: string[];
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
        const getAdjMi = findMethodByParamCount(bqClass, "GetAdjacentTiles", 4);
        if (!getAdjMi) {
            return { ok: false, error: "GetAdjacentTiles(4) non resolu sur "
                + s(class_get_name(bqClass) as NativePointer) };
        }

        // Table (col,row) -> entityId de tuile, et l'INVERSE. La seconde est ce que `boardGraph`
        // n'a pas : elle permet de dire d'un voisin non remappable qu'il EXISTE, au lieu de le
        // faire disparaitre.
        const proj = projectMatchState(statePtr, { includeTiles: true });
        const projTiles = proj.tiles ?? [];
        const idByCoord = new Map<string, number>();
        const coordById = new Map<number, { col: number; row: number }>();
        for (const t of projTiles) {
            idByCoord.set(t.col + "," + t.row, t.id);
            coordById.set(t.id, { col: t.col, row: t.row });
        }
        const ptrById = new Map<number, NativePointer>();
        const typeById = new Map<number, number>();
        forEachEntity(statePtr, (e, id, ty) => { ptrById.set(id, e); typeById.set(id, ty); });

        // Origines demandees.
        const origins: Array<{ id: number; kind: string; ptr: NativePointer }> = [];
        const missing: Array<Record<string, unknown>> = [];
        for (const eid of (body?.entityIds ?? [])) {
            const p = ptrById.get(eid);
            if (!p) { missing.push({ entityId: eid, why: "entite absente de l'etat" }); continue; }
            origins.push({ id: eid, kind: "entity:" + (typeById.get(eid) ?? -1), ptr: p });
        }
        for (const c of (body?.tiles ?? [])) {
            const tid = idByCoord.get(c.col + "," + c.row);
            const p = tid === undefined ? undefined : ptrById.get(tid);
            if (!p || tid === undefined) {
                missing.push({ col: c.col, row: c.row, why: "aucune tuile a cette coordonnee" });
                continue;
            }
            origins.push({ id: tid, kind: "tile", ptr: p });
        }
        if (origins.length === 0 && !(body?.entityIds) && !(body?.tiles)) {
            for (const t of projTiles) {
                const p = ptrById.get(t.id);
                if (p) origins.push({ id: t.id, kind: "tile", ptr: p });
            }
        }

        const wanted = (body?.regimes ?? ["selector", "graph"])
            .filter((r) => Object.prototype.hasOwnProperty.call(REGIMES, r));
        const bufs: Record<string, NativePointer> = {};
        const b = (v: boolean): NativePointer => {
            const k = v ? "1" : "0";
            if (!bufs[k]) { bufs[k] = Memory.alloc(1); bufs[k].writeU8(v ? 1 : 0); }
            return bufs[k];
        };

        let calls = 0; let fails = 0; let unmapped = 0;
        const rows = origins.map((o) => {
            const byRegime: Record<string, unknown> = {};
            for (const rn of wanted) {
                const r = REGIMES[rn];
                try {
                    const os = invokeMethod(getAdjMi.info, battleQ,
                        [o.ptr, b(r.oes), b(r.owt), b(r.at)]);
                    calls++;
                    const out = extractTilePtrs(os).map((n) => {
                        // L'entityId est lu SUR LE POINTEUR rendu (`Entity+0x10`), donc il ne
                        // depend d'aucune reprojection. `coordById` ne sert qu'a etiqueter ; un
                        // voisin qu'elle ignore reste PRESENT, marque `projected:false`.
                        let nid: number | null = null;
                        try { nid = n.ptr.add(0x10).readS32(); } catch { /* */ }
                        const projected = nid !== null && coordById.has(nid);
                        if (!projected) unmapped++;
                        return { id: nid, col: n.col, row: n.row, projected };
                    });
                    byRegime[rn] = { count: out.length, tiles: out };
                } catch (e) {
                    fails++;
                    byRegime[rn] = { error: (e as Error).message };
                }
            }
            // Le composant BRUT de l'origine quand c'est une tuile — la liste que
            // `TileQuery.<IterateAdjacentTiles>d__8$$MoveNext` filtre. Publie ICI pour que le
            // filtre (elevation, walkable, temporaire) se lise comme une DIFFERENCE et pas comme
            // une absence.
            let connectivity: number[] | null = null;
            if (typeById.get(o.id) === EntityType.Tile) {
                const c = readConnectivity(o.ptr);
                if (c) connectivity = c.neighbours;
            }
            // Les tuiles de l'origine — `EntityExtensions$$GetTiles`, le meme artefact que
            // `BattleQuery.<IterateAdjacentTiles>d__95$$MoveNext` applique a son `from`.
            let originTiles: Array<{ col: number; row: number }> | null = null;
            if (getTilesMi) {
                try {
                    const l = invokeMethod(getTilesMi.info, null, [o.ptr, statePtr]);
                    if (!l.isNull()) {
                        originTiles = extractTilePtrs(l).map((t) => ({ col: t.col, row: t.row }));
                    }
                } catch { /* tri-etat : null = non mesure */ }
            }
            return {
                originId: o.id, kind: o.kind,
                pos: coordById.get(o.id) ?? null,
                originTiles, connectivity, byRegime,
            };
        });

        return {
            ok: true, runner: label,
            regimes: Object.fromEntries(wanted.map((r) => [r, REGIMES[r]])),
            originCount: rows.length, missing,
            // `unmapped > 0` EST le verdict cherche par `#589-r1-r1-r2-r1-r4` : le natif rend un
            // voisin que la table (col,row) du port ne sait pas nommer. Zero partout dit l'inverse
            // — et alors c'est la MESURE de la fiche qu'il faut reprendre, pas le capteur.
            diag: { calls, fails, unmappedNeighbours: unmapped, tileCount: projTiles.length },
            origins: rows,
        };
    });
}
