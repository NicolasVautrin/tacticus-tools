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

import { findClass, findClassAnywhere, findMethod, getFieldOffset } from "../il2cpp/helpers.js";
import { state, clearLogUnpinned } from "../game/state.js";
import { install } from "../game/recorder.js";
import { clearTraceOrigin } from "../game/trace-origin.js";
import { log, traceEnter } from "./diag.js";
import { surveillerFinDeBataille, capturerAvantDetachement }
    from "../features/replay-fin-auto.js";
import { surveillerFinDeFenetre, fermerAvantDetachement }
    from "../features/sandbox-fenetre.js";
import { signalerRunnerVivant } from "../features/runner-signal.js";

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
// ⚠ ET UNE FAUTE *DANS* `origUpdate` EST ATTRAPÉE AUSSI — la version précédente de ce
// fichier disait le contraire (« l'avaler la rendrait invisible »), et c'était FAUX,
// mesuré quelques heures plus tard. Frida l'avalait DÉJÀ : une exception managée qui
// s'échappe de l'`Update` du jeu traverse notre `NativeCallback`, et Frida la convertit
// en `Error: system error` sur le canal que personne ne lit. Elle n'atteignait donc plus
// `IdunMainView` ni `HandleException` de toute façon. L'attraper ici ne change RIEN au
// comportement du jeu et la rend NOMMÉE — c'est strictement mieux que le statu quo.
// La distinguer de la nôtre est le point : la clé porte `origUpdate`, donc « c'est nous »
// et « c'est le jeu » ne se confondent pas.
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

// --- POMPE UI : vidanger DANS LE TICK DE L'EVENT SYSTEM ------------------
//
// ⚠ POURQUOI UNE SECONDE VIDANGE. La pompe principale draine dans `IdunGameViews.Update`,
// c'est-à-dire EN PLEINE FRAME DE LA VUE DE BATAILLE. Mesuré le 2026-08-20 : les travaux qui ne
// touchent que des structures de données y passent, mais tout appel qui manipule des widgets et
// des `GameObject` LÈVE en « system error » -- `UnitDeploymentHud$$HandleOnSwitchToMachinesOfWarUnitsTapped`,
// `FindFirstObjectByType`, et `HandleOnStartBattleTapped` dès que le chemin MoW est en jeu (le
// même appel PASSE avec 5 unités et aucune machine).
//
// Le HUD n'a pas d'`Update` : il est piloté par `UnityEngine.EventSystems.EventSystem$$Update`,
// le tick d'entrée de l'UI -- c'est de là que part le clic humain. On offre donc ce point de
// vidange, et il est EXCLUSIF : quand il est armé, la pompe principale ne draine plus, sinon un
// travail partirait dans l'un ou l'autre contexte au hasard et la mesure ne voudrait rien dire.
//
// ⛔ `attach`, jamais `replace` : on n'a rien à faire AVANT l'original, et un `replace` sur une
// méthode par frame est exactement ce que le `Ne jamais` du projet proscrit.
let uiPumpListener: InvocationListener | null = null;
let uiDrainActif = false;

export function pompeUiEtat(): Record<string, unknown> {
    return { installee: uiPumpListener !== null, actif: uiDrainActif };
}

export function pompeUiArmer(actif: boolean): Record<string, unknown> {
    if (!actif) {
        uiDrainActif = false;
        return { ok: true, ...pompeUiEtat(), note: "la pompe principale redraine" };
    }
    if (uiPumpListener === null) {
        const k = findClassAnywhere("UnityEngine.EventSystems", "EventSystem");
        if (!k) return { ok: false, error: "`UnityEngine.EventSystems.EventSystem` INTROUVABLE" };
        const mi = findMethod(k, "Update");
        if (!mi || mi.ptr.isNull()) return { ok: false, error: "`EventSystem$$Update` INTROUVABLE" };
        try {
            uiPumpListener = Interceptor.attach(mi.ptr, {
                onEnter() {
                    if (!uiDrainActif) return;
                    try { drainPending(); } catch (e) { noteFault("ui-pump", e); }
                },
            });
        } catch (e) {
            return { ok: false, error: "ancrage REFUSÉ : " + (e as Error).message };
        }
    }
    uiDrainActif = true;
    return { ok: true, ...pompeUiEtat(),
             note: "les travaux enfilés se vident désormais dans le tick de l'UI ; la pompe "
                 + "principale ne draine plus tant que c'est armé" };
}

export function installMainPump(): void {
    if (!updateMi || updateMi.ptr.isNull()) {
        log("[main-pump] IdunGameViews.Update not found");
        return;
    }

    // ⛔ `exceptions: "propagate"` N'EST PAS UN DÉTAIL : SANS LUI ON DÉSARME LES `try/catch` DU JEU.
    //
    // Par défaut Frida est en `exceptions: "steal"` : il CONFISQUE l'exception C++ par laquelle
    // IL2CPP transporte une exception managée. Le `catch` du jeu, en amont, ne la voit alors
    // jamais -- son gestionnaire d'erreur ne tourne pas, la frame ne se termine pas proprement,
    // et il ne reste chez nous qu'un « system error » sans cause.
    //
    // Ici c'est la PIRE place possible : ce relais enveloppe l'`Update` de la vue de bataille,
    // donc CHAQUE FRAME DE CHAQUE BATAILLE. Mesuré le 2026-08-20 : 12 « system error » pendant un
    // déploiement de boss de guilde (écran devenu inutilisable), puis 2 sur une bataille de
    // campagne qui s'est bloquée -- alors que le process répondait, que la pompe tournait et que
    // `observeBattle` rendait `stage: Running`. Le jeu n'était pas figé : son traitement d'erreur
    // avait été désarmé.
    //
    // C'est la MÊME cause que le blocage initial de cette tranche sur `il2cpp_runtime_invoke`
    // (cf. `docs/rl/case-10040-frida-confisquait-les-exceptions-managees.md`) -- corrigée là-bas,
    // et restée ici, à l'endroit qui porte le plus de trafic du harnais.
    //
    // ⚠ CONSÉQUENCE ASSUMÉE : une exception propagée traverse notre `catch`, donc `noteFault` ne
    // la compte plus. On perd un compteur, on rend au jeu son droit de se rattraper. Le compteur
    // n'a jamais réparé une bataille.
    const origUpdate = new NativeFunction(
        updateMi.ptr, "void", ["pointer", "pointer"], { exceptions: "propagate" });

    Interceptor.replace(updateMi.ptr, new NativeCallback(function (self, methodInfo) {
        const selfPtr = self as NativePointer;
        try {
        traceEnter("IdunGameViews.Update", 60);

        // Runner switch detection — handle three transitions:
        //   null → r       (battle started)
        //   r1   → r2      (battle switched)
        //   r    → null    (battle ended / quit to menu)
        const r = selfPtr.add(gvRunnerOff).readPointer();
        // La vue et la frame où on l'a vue : c'est ce qui permet à un lecteur de savoir si
        // `liveRunner` est FRAIS ou si la pompe s'est arrêtée (cf. `game/state.ts`).
        state.gameViews = selfPtr;
        state.gameViewsFrame = state.frameNo;
        if (r.isNull()) {
            // Battle ended on the device → drop the live entry. Build runners
            // (if any) stay intact: they're our standalones, independent of
            // the device's battle lifecycle.
            if (state.liveRunner) {
                // ⚠ AVANT le nettoyage : c'est la DERNIERE frame ou le replay est
                // atteignable. Une capture faite apres ne rend plus que « runner has no
                // ReplayRecorder » — un message qui accuse le mecanisme alors que seul le
                // TIMING etait en cause. Deux replays ont ete perdus ainsi.
                capturerAvantDetachement();
                // La fenetre sandbox meurt ici aussi -- et par sa voie la plus courante, la
                // RETRAITE. Le desarmement lui-meme est differe hors frame (cf. le module).
                fermerAvantDetachement();
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
            // LE SIGNAL : une bataille NEUVE existe. Ce qui l'attend est reveille ici, dans la
            // frame meme -- personne n'a plus a sonder `sandboxProbe` (cf. `runner-signal.ts`).
            signalerRunnerVivant();
            setTimeout(() => {
                if (state.installNeeded) {
                    state.installNeeded = false;
                    try { install(); }
                    catch (e) { send({ t: "install_error", err: (e as Error).message }); }
                }
            }, 0);
        }

        state.frameNo++;
        // Second déclencheur de capture : `stage -> Finished` alors que le runner est
        // ENCORE attaché. Ne coûte qu'un test de booléen tant que le module est désarmé.
        surveillerFinDeBataille();
        // Meme transition, autre consequence : les relais d'ecriture montes pour CETTE fenetre
        // sandbox s'eteignent avec elle, au lieu de survivre jusqu'a la prochaine bataille --
        // reelle, le cas echeant.
        surveillerFinDeFenetre();
        // EXCLUSIF : si la pompe UI est armée, c'est ELLE qui draine (cf. son en-tête).
        if (!uiDrainActif) drainPending();
        } catch (e) { noteFault("main-pump", e); }

        // RELAIS INCONDITIONNEL — cf. TRANSPARENCE en tête de fichier.
        try { origUpdate(selfPtr, methodInfo as NativePointer); }
        catch (e) { noteFault("main-pump/origUpdate", e); }
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

    // Même raison que pour la pompe principale ci-dessus : sans `propagate`, on confisque les
    // exceptions managées de l'`Update` qu'on relaie, et on désarme le `try/catch` du jeu.
    const origUpdate = new NativeFunction(
        mi.ptr, "void", ["pointer", "pointer"], { exceptions: "propagate" });

    Interceptor.replace(mi.ptr, new NativeCallback(function (self, methodInfo) {
        try {
            traceEnter("UnityFreezeDetector.Update", 60);
            state.frameNo++;
            drainPending();
        } catch (e) { noteFault("menu-pump", e); }

        // RELAIS INCONDITIONNEL — cf. TRANSPARENCE en tête de fichier.
        try { origUpdate(self as NativePointer, methodInfo as NativePointer); }
        catch (e) { noteFault("menu-pump/origUpdate", e); }
    }, "void", ["pointer", "pointer"]));
    log("[menu-pump] attached (via replace) to UnityFreezeDetector.Update");
}
