// Budget de RENDU du jeu, pilote A CHAUD depuis le process (RPC `renderBudget`).
//
// POURQUOI. Tacticus n'est pas ici un jeu qu'on regarde : c'est un HOTE DE CALCUL IL2CPP pilote
// par Frida. Mesure du 2026-07-28 : seul client de la RTX 4070, il y consommait 33 % en moyenne
// (43 % en pointe), 23 W, SM a 1500 MHz, 62 C -- pour afficher un ecran de bataille STATIQUE. La
// cause n'est pas un rendu couteux mais sa SURFACE : `utilization.gpu` a 43 % pendant que
// `utilization.memory` reste a 3 % = scene triviale, repeinte sur enormement de pixels
// (3840x2400 = 9,2 Mpx, plus qu'un 4K, a 90 Hz -> ~830 Mpx/s).
//
// CE MODULE ET LE SCRIPT `scripts/tacticus-screen-prefs.ps1` NE FONT PAS LA MEME CHOSE -- ils sont
// complementaires, et c'est deliberement DEUX leviers, pas un fork :
//   * le .ps1 ecrit les PREFS UNITY (HKCU\Software\Snowprint\...) = la resolution AU DEMARRAGE.
//     Persistant, mais Unity REECRIT ces clefs en quittant -> applicable seulement jeu FERME.
//   * ce module appelle `UnityEngine.Screen.SetResolution` sur le process VIVANT = effet immediat,
//     sans fermer le jeu, et volatile (perdu au prochain lancement).
// Les deux ensemble : le .ps1 pour que ca reparte bien, ce RPC pour la session en cours.
//
// LE PIEGE A NE PAS TOMBER DEDANS -- `targetFrameRate` n'est PAS un levier gratuit. Le pump RPC
// (`runtime/queue.ts`) draine `state.pending` dans le hook `IdunGameViews.Update`, donc UNE FOIS
// PAR FRAME : le framerate est le plancher de latence de CHAQUE RPC. A 10 fps, un probe qui
// enchaine 400 RPC sequentiels paie 40 s d'attente pure. La RESOLUTION, elle, ne touche pas du
// tout la cadence du pump -- c'est le levier a prendre en premier, et le seul qui soit sans
// contrepartie pour le harnais. `targetFrameRate` reste expose, mais il faut le choisir en
// connaissance de cause, pas le baisser par reflexe.
//
// Read-only par defaut : sans argument, le RPC ne fait que LIRE l'etat courant.
//
// ⛔ NE JAMAIS demander `fullScreenMode = 0` (ExclusiveFullScreen) : c'est le seul mode qui force
// un changement de mode d'affichage DXGI, et il a DEJA tue le process une fois (cf. le bloc
// `SetResolution` plus bas). Le defaut `Windowed` est le chemin sur.

import {
    findClass, findClassAnywhere, findMethodByParamCount,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

const CORE = "UnityEngine.CoreModule.dll";

// `UnityEngine.FullScreenMode` : 0=ExclusiveFullScreen, 1=FullScreenWindow, 2=MaximizedWindow,
// 3=Windowed. MEME enum, MEMES valeurs que le `$MODE_WINDOWED = 3` de
// `scripts/tacticus-screen-prefs.ps1` — les deux leviers ecrivent le meme reglage, l'un dans les
// prefs de demarrage, l'autre sur le process vivant.
const MODE_WINDOWED = 3;

function klass(ns: string, cls: string): NativePointer | null {
    return findClass(CORE, ns, cls) ?? findClassAnywhere(ns, cls);
}

/** Invoque une methode STATIQUE rendant un int (resultat boxe : valeur @0x10, comme `invokeInt`).
 *  `null` -- PAS 0 -- si irresolue ou en echec : 0 est une valeur LEGITIME du domaine
 *  (`vSyncCount = 0`, `targetFrameRate = -1`), il faut pouvoir distinguer « lu » de « pas lu ». */
function callInt(mi: { info: NativePointer } | null): number | null {
    if (!mi) return null;
    try {
        const r = invokeMethod(mi.info, null, []);
        return r.isNull() ? null : r.add(0x10).readS32();
    } catch { return null; }
}

// --- BRIDAGE de la cadence : le jeu REECRIT vSync/targetFrameRate a chaque frame -------------
//
// MESURE du 2026-07-28, deux RPC consecutifs :
//     set        -> applied:["vSyncCount","targetFrameRate"]  after {targetFrameRate:30, vSyncCount:0}
//     relecture  ->                                                 {targetFrameRate:-1, vSyncCount:1}
// L'ecriture PASSE puis est ANNULEE dans la frame. Une pose one-shot de ces deux valeurs est donc
// INUTILE -- et c'est le seul levier qui compte pour la conso restante : `utilization.gpu` mesure
// un RAPPORT CYCLIQUE, pas une quantite de travail ; a 90 Hz de vSync le GPU est reveille 90x/s
// quel que soit le nombre de pixels. C'est pour ca que diviser la surface par 9 a fait tomber la
// PUISSANCE (18,6 W -> 6,6 W) sans bouger le pourcentage d'utilisation.
//
// ⚠ CE N'EST VRAI QU'A CADENCE LIBRE, et la nuance a ete mesuree le 2026-07-28 (12 echantillons
// par point, meme scene, cadence bridee a 30 fps) :
//     1 806 080 px -> 36,3 % / 6,4 W        1 024 000 px -> 21,2 % / 5,5 W
// soit un rapport d'utilisation de 1,71 pour un rapport de surface de 1,76. UNE FOIS LA CADENCE
// FIXEE, l'utilisation redevient donc proportionnelle a la SURFACE -- le nombre de reveils ne
// varie plus, c'est leur DUREE qui porte le signal. Les deux leviers ne sont pas substituables :
// la cadence enleve les reveils inutiles, la surface raccourcit ceux qui restent.
//
// On intercepte donc les deux setters et on REECRIT leur argument : quoi que le jeu se reimpose,
// il obtient la valeur bridee. `Interceptor.attach` + reecriture de `args[0]` suffit (pas besoin
// de `replace` : on ne reimplemente rien, et Frida detache tout seul au unload).
//
// PAS de hot path ici : ces setters sont appeles au plus une fois par frame -- rien a voir avec
// les getters de serialisation a 27 000 appels/s que le `Ne jamais` du CLAUDE.md proscrit.
//
// COUT POUR LE HARNAIS -- j'avais annonce une penalite, la MESURE dit l'inverse. Le pump RPC
// (`runtime/queue.ts`) draine `state.pending` dans `IdunGameViews.Update`, donc UNE FOIS PAR
// FRAME : brider a N fps pose bien un plancher de 1000/N ms par RPC (33 ms a 30 fps contre 11 ms
// a 90 Hz). Mais ce plancher est NOYE dans le cout du transport. Mesure du 2026-07-28, meme
// protocole (20 RPC sequentiels via curl) :
//     90 Hz  -> 134,8 ms/RPC        30 fps bride -> 106,4 ms/RPC
// et les 3 gardes live d'O5 passent en 11 s sous bridage. C'est PLUS RAPIDE : la latence RPC est
// dominee par le spawn de process + HTTP, pas par la periode de frame, et la machine entiere
// respire une fois le GPU sorti de saturation.
//
// ⚠ Ca ne vaut PAS a n'importe quelle valeur : a 10 fps le plancher passe a 100 ms et depasserait
// le cout du transport. La mesure ci-dessus a ete faite a 30 fps ; en dessous, rien n'est mesure.
//
// ⚠ LA VALEUR ARMEE EST 60, PAS 30 -- correction de l'utilisateur, 2026-08-13. La mesure de
// latence ci-dessus reste vraie telle qu'elle a ete faite, mais elle ne dit RIEN de ce qu'il
// faut choisir : elle compare 90 Hz a 30 fps sur le seul axe du COUT RPC, et conclut que le
// bridage ne penalise pas le harnais. Elle n'etablit pas que 30 soit la bonne cadence pour le
// JEU -- le plancher par RPC y est deux fois plus haut qu'a 60 (33 ms contre 17 ms), pour un gain
// GPU que la reduction de SURFACE (560x800, cf. `scripts/tacticus-screen-prefs.ps1`) apporte
// deja. Ne pas << re-optimiser >> vers 30 en citant le tableau ci-dessus : il ne porte pas
// sur cette question.
//
let vsListener: InvocationListener | null = null;
let fpsListener: InvocationListener | null = null;
let clampedVSync: number | null = null;
let clampedFps: number | null = null;

function clampArg0(mi: { ptr: NativePointer } | null, get: () => number | null,
): InvocationListener | null {
    if (!mi || mi.ptr.isNull()) return null;
    return Interceptor.attach(mi.ptr, {
        onEnter(args) {
            const v = get();
            if (v !== null) args[0] = ptr(v);
        },
    });
}

// --- AUTO-ARM au register --------------------------------------------------------------------
//
// POURQUOI ON DEROGE ICI a la regle « le register n'arme rien » (controller.ts, incident du
// 2026-07-10) : cette regle vise les Interceptor sur des chemins de degat ULTRA-CHAUDS
// (`ExecuteHit`, getters de serialisation a 27 000 appels/s) dont la surcharge de trampoline
// destabilise IL2CPP pendant le churn reinject/warmup. `set_vSyncCount` / `set_targetFrameRate`
// sont a l'exact oppose : appeles AU PLUS UNE FOIS PAR FRAME, sur du code UnityEngine sans rapport
// avec le moteur de bataille. Le cout mesure du bridage sur le harnais est NUL (106,4 ms/RPC bride
// contre 134,8 ms a 90 Hz, cf. plus haut) -- l'auto-arm ne peut donc pas ralentir un probe.
//
// CE QUE CA REPARE : le bridage vit dans des `InvocationListener`, donc il MEURT a chaque reinject
// -- et un reinject est un geste courant. Sans auto-arm il fallait le reposer a la main, et
// l'oubli est SILENCIEUX (le GPU repart a 33 %, rien ne le signale).
//
// ON N'AUTO-ARME QUE LA CADENCE, PAS LA RESOLUTION. La resolution, elle, SURVIT au reinject (elle
// vit dans le process Unity, le jeu ne la reimpose pas -- c'est pourquoi un `SetResolution`
// one-shot suffit) ; au prochain LANCEMENT c'est le `.ps1` qui prend le relais via les prefs. Et
// surtout `SetResolution` est le seul appel de ce module qui ait deja tue le process : on ne le
// declenche pas tout seul au demarrage.
//
// QUAND : pas au load du script (les metadonnees IL2CPP peuvent ne pas etre pretes -> faute 0x2c),
// mais via `queueOnMainThread`, donc a la 1re frame drainee par le pump -- main thread, runtime
// pret. Si les setters ne resolvent pas encore, on RE-QUEUE (jusqu'a AUTOARM_TRIES frames).
//
// OBSERVABLE : un auto-arm qui echoue en silence serait exactement le defaut qu'on combat.
// `renderBudget` (lecture seule) rend donc `autoArm: {done, attempts, error}` -- un `done:false`
// avec un `error` se voit d'un coup d'oeil.
const AUTOARM_VSYNC = 0;    // 0 = vSync desactive (sinon Unity IGNORE targetFrameRate)
const AUTOARM_FPS = 60;     // 2026-08-13, correction utilisateur ; cf. l'avertissement en tete
const AUTOARM_TRIES = 30;

const autoArm = { done: false, attempts: 0, error: null as string | null };
// Un reglage EXPLICITE de l'appelant fait autorite : si un RPC a touche aux clamps avant que le
// pump n'ait draine l'auto-arm, celui-ci s'abstient -- sinon il ecraserait un choix delibere
// (typiquement un `clampFrameRate: null` pose pour un probe qui veut le plein regime).
let clampsTouchedByRpc = false;

function tryAutoArm(): void {
    if (autoArm.done || clampsTouchedByRpc) return;
    autoArm.attempts += 1;
    try {
        const appK = klass("UnityEngine", "Application");
        const qualK = klass("UnityEngine", "QualitySettings");
        const setFps = appK ? findMethodByParamCount(appK, "set_targetFrameRate", 1) : null;
        const setVs = qualK ? findMethodByParamCount(qualK, "set_vSyncCount", 1) : null;
        if (!setFps || !setVs) {
            autoArm.error = "setters non resolus (Application/QualitySettings)";
            if (autoArm.attempts < AUTOARM_TRIES) void queueOnMainThread(tryAutoArm);
            return;
        }
        clampedVSync = AUTOARM_VSYNC;
        clampedFps = AUTOARM_FPS;
        vsListener = clampArg0(setVs, () => clampedVSync);
        fpsListener = clampArg0(setFps, () => clampedFps);
        // Le clamp ne mord qu'au PROCHAIN appel du setter par le jeu. Comme il les reimpose a
        // chaque frame, c'est immediat -- mais on pose quand meme les valeurs tout de suite, pour
        // que le cas « le jeu ne les rappelle pas » (pause, scene sans rendu) soit couvert aussi.
        const b0 = Memory.alloc(4); b0.writeS32(AUTOARM_VSYNC);
        const b1 = Memory.alloc(4); b1.writeS32(AUTOARM_FPS);
        invokeMethod(setVs.info, null, [b0]);
        invokeMethod(setFps.info, null, [b1]);
        autoArm.done = true;
        autoArm.error = null;
    } catch (e) {
        autoArm.error = (e as Error).message;
        if (autoArm.attempts < AUTOARM_TRIES) void queueOnMainThread(tryAutoArm);
    }
}

export function register(ctx: Ctx): void {
    // Arme le bridage de CADENCE des la 1re frame drainee (cf. le bloc AUTO-ARM). Pas ici et
    // maintenant : au load du script, IL2CPP peut ne pas etre pret.
    void queueOnMainThread(tryAutoArm);

    /** LIT (et optionnellement REGLE) le budget de rendu du process VIVANT.
     *  Sans argument : lecture seule. body: { width?, height?, fullscreen?=false,
     *  targetFrameRate?, vSyncCount? } */
    ctx.rpc.renderBudget = (
        body?: {
            width?: number; height?: number; fullScreenMode?: number;
            targetFrameRate?: number; vSyncCount?: number;
            clampVSync?: number | null; clampFrameRate?: number | null;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        const screenK = klass("UnityEngine", "Screen");
        const appK = klass("UnityEngine", "Application");
        const qualK = klass("UnityEngine", "QualitySettings");
        if (!screenK) return { ok: false, error: "UnityEngine.Screen non resolu" };

        const getW = findMethodByParamCount(screenK, "get_width", 0);
        const getH = findMethodByParamCount(screenK, "get_height", 0);
        // ⚠ Sur ce build (Unity 6000.3.13f1) `Screen.SetResolution` n'a PAS de surcharge
        // `(int,int,bool)` : `methods.tsv` n'en donne que deux,
        //   `SetResolution(width, height, fullscreenMode:FullScreenMode)`                  <- 3 params
        //   `SetResolution(width, height, fullscreenMode, preferredRefreshRate:RefreshRate)`
        // Le 3e argument est donc un ENUM, pas un booleen -- et le confondre a COUTE LE JEU.
        //
        // MESURE du 2026-07-28, `Player-prev.log` VERBATIM : en passant `fullscreen=false -> 0` on
        // demandait `ExclusiveFullScreen`, pas `Windowed` (0 = ExclusiveFullScreen dans
        // `UnityEngine.FullScreenMode`) --
        //     dxgi: swapchain SetFullscreenState failed (887a0022).
        //     Failed to apply requested ExclusiveFullScreen resolution (1280x800)...will try again
        //     Unable to apply ... again ...reverting to current display resolution: 3840x2400
        //     Failed to change display to ExclusiveFullscreen...reverting to FullscreenWindow
        //     Direct3D: detected that IDXGISwapChain::GetFrameStatistics is broken
        // -- swapchain jamais recupere, GPU MONTE (49 % / 30 W / 67 C contre 33 % / 23 W / 62 C
        // avant), process perdu ensuite. Cote RPC ca s'etait vu comme `applied:["resolution"]`,
        // `errors:[]`, resolution inchangee : le retour ne dit RIEN de l'echec, il faut le lire
        // dans le log Unity.
        //
        // D'ou le parametre explicite `fullScreenMode`, et le defaut `Windowed` : en fenetre il
        // n'y a AUCUN changement de mode d'affichage, donc aucun `SetFullscreenState` -- c'est le
        // seul chemin qui coupe la surface sans toucher au swapchain.
        const setRes = findMethodByParamCount(screenK, "SetResolution", 3);
        const getFps = appK ? findMethodByParamCount(appK, "get_targetFrameRate", 0) : null;
        const setFps = appK ? findMethodByParamCount(appK, "set_targetFrameRate", 1) : null;
        const getVs = qualK ? findMethodByParamCount(qualK, "get_vSyncCount", 0) : null;
        const setVs = qualK ? findMethodByParamCount(qualK, "set_vSyncCount", 1) : null;

        const read = () => ({
            width: callInt(getW), height: callInt(getH),
            targetFrameRate: callInt(getFps), vSyncCount: callInt(getVs),
        });
        const before = read();
        const applied: string[] = [];
        const errors: string[] = [];

        // vSync EN PREMIER : tant que `vSyncCount != 0`, Unity IGNORE `targetFrameRate` (le
        // framerate est cale sur le rafraichissement ecran). Regler l'un sans l'autre donnerait un
        // reglage qui a l'air pris en compte et ne fait rien.
        if (typeof body?.vSyncCount === "number") {
            if (!setVs) errors.push("QualitySettings.set_vSyncCount non resolu");
            else {
                const b = Memory.alloc(4); b.writeS32(body.vSyncCount);
                try { invokeMethod(setVs.info, null, [b]); applied.push("vSyncCount"); }
                catch (e) { errors.push("set_vSyncCount: " + (e as Error).message); }
            }
        }
        if (typeof body?.targetFrameRate === "number") {
            if (!setFps) errors.push("Application.set_targetFrameRate non resolu");
            else {
                const b = Memory.alloc(4); b.writeS32(body.targetFrameRate);
                try { invokeMethod(setFps.info, null, [b]); applied.push("targetFrameRate"); }
                catch (e) { errors.push("set_targetFrameRate: " + (e as Error).message); }
            }
        }
        if (typeof body?.width === "number" && typeof body?.height === "number") {
            if (!setRes) errors.push("Screen.SetResolution(3) non resolu");
            else {
                const mode = typeof body.fullScreenMode === "number"
                    ? body.fullScreenMode : MODE_WINDOWED;
                const w = Memory.alloc(4); w.writeS32(body.width);
                const h = Memory.alloc(4); h.writeS32(body.height);
                const m = Memory.alloc(4); m.writeS32(mode);
                try {
                    invokeMethod(setRes.info, null, [w, h, m]);
                    applied.push("resolution");
                } catch (e) { errors.push("SetResolution: " + (e as Error).message); }
            }
        }

        // BRIDAGE (on-demand) : `clampVSync` / `clampFrameRate`. `null` explicite = retirer le
        // bridage de cet axe. Sans les clefs, on ne touche a rien -- le bridage en place SURVIT.
        if (body && "clampVSync" in body) {
            clampsTouchedByRpc = true;
            clampedVSync = typeof body.clampVSync === "number" ? body.clampVSync : null;
            if (clampedVSync === null && vsListener) { vsListener.detach(); vsListener = null; }
            else if (clampedVSync !== null && !vsListener) {
                vsListener = clampArg0(setVs, () => clampedVSync);
                if (!vsListener) errors.push("clamp vSyncCount: setter irresolu");
            }
            applied.push("clampVSync");
        }
        if (body && "clampFrameRate" in body) {
            clampsTouchedByRpc = true;
            clampedFps = typeof body.clampFrameRate === "number" ? body.clampFrameRate : null;
            if (clampedFps === null && fpsListener) { fpsListener.detach(); fpsListener = null; }
            else if (clampedFps !== null && !fpsListener) {
                fpsListener = clampArg0(setFps, () => clampedFps);
                if (!fpsListener) errors.push("clamp targetFrameRate: setter irresolu");
            }
            applied.push("clampFrameRate");
        }

        const after = read();
        // La surface est la grandeur qui PILOTE la consommation (cf. l'en-tete) : on la rend
        // explicitement plutot que de laisser l'appelant la recalculer.
        const px = (s: { width: number | null; height: number | null }) =>
            (s.width !== null && s.height !== null) ? s.width * s.height : null;
        return { ok: errors.length === 0, before, after, applied, errors,
            pixelsBefore: px(before), pixelsAfter: px(after),
            clamps: { vSync: clampedVSync, frameRate: clampedFps },
            // Rendu MEME quand tout va bien : c'est le seul endroit d'ou l'on voit qu'un auto-arm
            // a echoue (`done:false` + `error`), sinon la panne serait exactement le defaut
            // silencieux que l'auto-arm vient supprimer.
            autoArm: { ...autoArm, overriddenByRpc: clampsTouchedByRpc } };
    });
}
