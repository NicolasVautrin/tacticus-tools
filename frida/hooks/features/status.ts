// Status/diagnostic RPCs — info, summary, dump, clear, battleStatus,
// forceInstall. Read-only except `clear` (wipes log) and `forceInstall`
// (re-attaches live hooks).

import { il2cppBase, il2cppSize } from "../il2cpp/helpers.js";
import { isSerializerReady } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { installedBuild, pinnedAddressRefusals } from "../il2cpp/build-pin.js";
import {
    BOND_ENTITY_ID_FIELD_NAME, EFFECT_TARGET_IDS_FIELD_NAME,
} from "../game/effects.js";
import { state, LogEntry, clearLogUnpinned } from "../game/state.js";
import { runnerOff } from "../game/runner.js";
import { readBattleStatus } from "../game/match-state.js";
import { install, ensureInstalled } from "../game/recorder.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

// Strip ArrayBuffer from prng snapshot for JSON-safe return.
function sanitizeEntry(e: LogEntry): Record<string, unknown> {
    const o: Record<string, unknown> = {
        idx: e.idx, src: e.src, cls: e.cls, ptr: e.ptr,
        unitId: e.unitId, ts: e.ts,
    };
    if (e.turn !== undefined) o.turn = e.turn;
    if (e.prng) {
        o.prng = {
            seed: e.prng.seed, count: e.prng.count,
            mti: e.prng.mti, mtLen: e.prng.mtLen,
        };
    }
    return o;
}

export function register(ctx: Ctx): void {
    ctx.rpc.ping = () => "pong";

    ctx.rpc.info = () => ({
        name: "frida",
        version: 1,
        runtime: Process.arch,
        platform: Process.platform,
        il2cppBase: il2cppBase.toString(),
        il2cppSize,
        serializerReady: isSerializerReady(),
        runner: state.liveRunner?.toString() ?? null,
        realAiControl: state.realAiControl?.toString() ?? null,
        logSize: state.log.length,
        listeners: state.installedListeners.length,
        // SANS garde `listPtr()` : depuis la migration gchandle (2026-05-07) ce
        // legacy rend TOUJOURS null, donc `info` publiait `gcRootCount: null`
        // depuis 2,5 mois — un null ne fait pas de bruit, personne ne l'a vu.
        // `count()` est la taille de la Map de gchandles, exacte et sans état
        // externe (init-trace.ts l'appelle directement depuis toujours).
        gcRootCount: gcRoot.count(),
    });

    ctx.rpc.summary = () => queueOnMainThread(() => {
        const byKind: Record<string, number> = {
            top: 0, ai: 0, humanAi: 0, top_boot: 0,
        };
        const byCls: Record<string, number> = {};
        for (const e of state.log) {
            byKind[e.src] = (byKind[e.src] ?? 0) + 1;
            byCls[e.cls] = (byCls[e.cls] ?? 0) + 1;
        }
        return {
            total: state.log.length,
            byKind,
            byCls,
            head: state.log.slice(0, 15).map(sanitizeEntry),
            tail: state.log.slice(-10).map(sanitizeEntry),
        };
    });

    ctx.rpc.dump = () => queueOnMainThread(() => ({
        log: state.log.map(sanitizeEntry),
    }));

    ctx.rpc.clear = () => queueOnMainThread(() => {
        // Dépingle AVANT de vider (cf. game/state.ts) : sinon chaque message
        // épinglé par le recorder devient un handle orphelin définitif.
        const unpinned = clearLogUnpinned();
        state.counter = 0;
        return { ok: true, unpinned };
    });

    ctx.rpc.battleStatus = () => queueOnMainThread(() => {
        ensureInstalled();
        if (!state.liveRunner) return { err: "no runner" };
        const statePtr = state.liveRunner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { err: "state null" };
        return readBattleStatus(statePtr);
    });

    // Ce que la session a résolu PAR NOM, et ce qu'elle a REFUSÉ (#480-r7).
    //
    // Trois capteurs existaient déjà, chacun documenté comme « exporté pour qu'une MAJ se
    // VOIE » — et AUCUN n'avait de lecteur : un garde-fou qu'on croit armé et qui ne peut
    // pas signaler. Ils sont ici, sur le SEUL canal qu'un appelant peut interroger.
    //
    // Aucun accès mémoire : tout est déjà résolu au chargement des modules. Pas de
    // `queueOnMainThread` — l'appel n'a pas à attendre la boucle Unity pour rendre trois
    // valeurs figées.
    ctx.rpc.nameResolutionStatus = (): unknown => {
        const probe = installedBuild();
        return {
            // Tri-état : `build: null` = NON MESURÉ, et `why` dit laquelle des trois
            // pannes c'est. Jamais rabattu sur « un autre build ».
            build: probe.build,
            buildWhy: probe.why === "" ? null : probe.why,
            // Refus d'adresses épinglées depuis le chargement du script. Liste VIDE =
            // mesurée et vide ; c'est le cas nominal.
            pinnedAddressRefusals: pinnedAddressRefusals(),
            // Noms natifs des champs retenus par résolution d'offset. `null` = le champ
            // n'a pas été résolu et la lecture retombe sur l'offset RE — c'est
            // exactement ce qu'une MAJ de disposition rend visible ici.
            fieldNames: {
                effectTargetIds: EFFECT_TARGET_IDS_FIELD_NAME,
                bondEntityId: BOND_ENTITY_ID_FIELD_NAME,
            },
        };
    };

    ctx.rpc.forceInstall = () => queueOnMainThread(() => {
        const before = state.installedListeners.length;
        const ok = install();
        return {
            ok,
            before,
            after: state.installedListeners.length,
            runner: state.liveRunner?.toString() ?? null,
            aiControl: state.realAiControl?.toString() ?? null,
            logSize: state.log.length,
        };
    });
}
