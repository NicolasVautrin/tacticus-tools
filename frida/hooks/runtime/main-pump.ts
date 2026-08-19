// Main-thread pumps.
//
//   1. IdunGameViews.Update — fires during battle view. Handles runner switch
//      (new battle detected → install live-runner hooks) + drains pending RPC.
//   2. UnityFreezeDetector.Update — fires EVERY frame (menu + battle).
//      Drains pending RPC too so Phase 3 launch works without an active battle.
//
// Both pumps share `state.pending`. The queue is shift()-based so fn's run at
// most once; having two pumps guarantees main-thread work proceeds regardless
// of game state.
//
// Both pumps use `Interceptor.replace` (not `attach`): Frida's `attach`
// applies a per-thread recursion guard that silently suppresses any nested
// hook callback fired from inside an `attach` onEnter. Because `drainPending`
// invokes IL2CPP methods synchronously (on the main thread, as required by
// the runtime), any listener we've installed on those invoked methods would
// be dead under an `attach`-pump. `replace` has no recursion guard and
// preserves the main-thread context, so hooks downstream of `drainPending`
// fire correctly.

import { findClass, findMethod, getFieldOffset } from "../il2cpp/helpers.js";
import { state, clearLogUnpinned } from "../game/state.js";
import { install } from "../game/recorder.js";
import { clearTraceOrigin } from "../game/trace-origin.js";
import { log, traceEnter } from "./diag.js";

// ------------------------------------------------------------- TRANSPARENCE
//
// LES DEUX POMPES *REMPLACENT* `Update` — la frame du jeu n'a donc lieu QUE SI notre
// JS atteint `origUpdate`. Toute faute au-dessus (lecture d'un champ sur un `self`
// invalide, SEH d'un invoke IL2CPP qui remonte de `drainPending`) SUPPRIME une frame
// entière de la vue de bataille. Et elle la supprime EN SILENCE : Frida n'émet qu'un
// `Error: system error` sur le canal `error` de la session, qui n'est ni journalisé
// par défaut (`/api/admin/inject` ne passe pas de `logDir`) ni relu par personne — il
// ne vit que dans l'anneau WebSocket du host.
//
// Mesuré le 2026-08-19 sur la session 41 : TROIS frames ainsi supprimées, trouvées
// seulement en vidant cet anneau à la main. Le relais est donc désormais
// INCONDITIONNEL — notre code ne peut plus décider que le jeu ne tourne pas.
//
// Ce qui reste volontairement NON attrapé : une faute DANS `origUpdate`, qui est
// celle du jeu. L'avaler la rendrait invisible alors que c'est le seul cas où le
// message de Frida désigne vraiment un problème du jeu.
//
// La faute est NOMMÉE et DÉDOUBLONNÉE : à 60 frames/s, une faute permanente émettrait
// 60 messages par seconde et noierait le canal qu'on essaie justement de rendre
// lisible. On n'émet qu'à la PREMIÈRE occurrence, et on garde le compte et les bornes,
// relus par le RPC `pumpFaults`.

export interface PumpFault {
    pump: string;
    message: string;
    count: number;
    firstFrame: number;
    lastFrame: number;
}

const pumpFaults = new Map<string, PumpFault>();

function noteFault(pump: string, e: unknown): void {
    try {
        const message = (e as Error)?.message ?? String(e);
        const key = pump + " | " + message;
        let f = pumpFaults.get(key);
        if (!f) {
            f = {
                pump, message, count: 0,
                firstFrame: state.frameNo, lastFrame: state.frameNo,
            };
            pumpFaults.set(key, f);
            send({ t: "diag", msg: "[" + pump + "] faute AVANT relais — frame du jeu "
                + "PRESERVEE : " + message });
        }
        f.count++;
        f.lastFrame = state.frameNo;
    } catch { /* le signalement ne doit JAMAIS empêcher le relais */ }
}

/** Les fautes retenues par les pompes, pour que « ça a sauté une frame » soit une
 *  MESURE et pas une trace perdue dans un anneau. Vide = aucune faute depuis l'inject. */
export function pumpFaultList(): PumpFault[] {
    return [...pumpFaults.values()];
}

function drainPending(): void {
    while (state.pending.length > 0) {
        const req = state.pending.shift()!;
        try {
            const result = req.fn();
            if (result instanceof Promise) {
                result.then(req.resolve, (e) => req.reject((e as Error).message));
            } else {
                req.resolve(result);
            }
        } catch (e) {
            req.reject((e as Error).message);
        } finally {
            // L'origine de trace posée par les RPCs de pilotage ne vaut que
            // pour CE job (évaluation native synchrone) — les hooks qui fire
            // hors job (IA du jeu live) doivent retomber sur null.
            clearTraceOrigin();
        }
    }
}

const gameViewsClass = findClass(
    "Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
const gvRunnerOff = gameViewsClass
    ? getFieldOffset(gameViewsClass, "_runner") : -1;
const updateMi = gameViewsClass ? findMethod(gameViewsClass, "Update") : null;

export function installMainPump(): void {
    if (!updateMi || updateMi.ptr.isNull()) {
        log("[main-pump] IdunGameViews.Update not found");
        return;
    }

    const origUpdate = new NativeFunction(
        updateMi.ptr, "void", ["pointer", "pointer"]);

    Interceptor.replace(updateMi.ptr, new NativeCallback(function (self, methodInfo) {
        const selfPtr = self as NativePointer;
        try {
        traceEnter("IdunGameViews.Update", 60);

        // Runner switch detection — handle three transitions:
        //   null → r       (battle started)
        //   r1   → r2      (battle switched)
        //   r    → null    (battle ended / quit to menu)
        const r = selfPtr.add(gvRunnerOff).readPointer();
        if (r.isNull()) {
            // Battle ended on the device → drop the live entry. Build runners
            // (if any) stay intact: they're our standalones, independent of
            // the device's battle lifecycle.
            if (state.liveRunner) {
                state.watchedRunners.delete(state.liveRunner.toString());
                state.liveRunner = null;
                state.runnerInstance = null;
                send({ t: "diag", msg: "[main-pump] live battle ended — liveRunner cleared" });
            }
        } else if (!r.equals(state.liveRunner ?? ptr(0))) {
            // Drop the previous live's watch entry (its build siblings stay).
            if (state.liveRunner) {
                state.watchedRunners.delete(state.liveRunner.toString());
            }
            state.liveRunner = r;
            state.runnerInstance = r;  // legacy alias
            state.watchedRunners.set(r.toString(), "live");
            state.counter = 0;
            // Dépingle AVANT de vider : les messages du log sont épinglés par le
            // recorder, et un `state.log = []` à cru en fait des handles
            // orphelins définitifs (cf. game/state.ts).
            clearLogUnpinned();
            state.installNeeded = true;
            setTimeout(() => {
                if (state.installNeeded) {
                    state.installNeeded = false;
                    try { install(); }
                    catch (e) { send({ t: "install_error", err: (e as Error).message }); }
                }
            }, 0);
        }

        state.frameNo++;
        drainPending();
        } catch (e) { noteFault("main-pump", e); }

        // RELAIS INCONDITIONNEL — cf. TRANSPARENCE en tête de fichier.
        origUpdate(selfPtr, methodInfo as NativePointer);
    }, "void", ["pointer", "pointer"]));
}

export function installMenuPump(): void {
    const cls = findClass(
        "Assembly-CSharp.dll", "idun.unity.utils", "UnityFreezeDetector");
    if (!cls) { log("[menu-pump] UnityFreezeDetector not found"); return; }
    const mi = findMethod(cls, "Update");
    if (!mi || mi.ptr.isNull()) {
        log("[menu-pump] UnityFreezeDetector.Update not found");
        return;
    }

    const origUpdate = new NativeFunction(
        mi.ptr, "void", ["pointer", "pointer"]);

    Interceptor.replace(mi.ptr, new NativeCallback(function (self, methodInfo) {
        try {
            traceEnter("UnityFreezeDetector.Update", 60);
            state.frameNo++;
            drainPending();
        } catch (e) { noteFault("menu-pump", e); }

        // RELAIS INCONDITIONNEL — cf. TRANSPARENCE en tête de fichier.
        origUpdate(self as NativePointer, methodInfo as NativePointer);
    }, "void", ["pointer", "pointer"]));
    log("[menu-pump] attached (via replace) to UnityFreezeDetector.Update");
}
