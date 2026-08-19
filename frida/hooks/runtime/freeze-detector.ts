// Neutralisation du UnityFreezeDetector — la garde qui TUE le process Tacticus.
//
// POURQUOI. Le detecteur de freeze du jeu conclut « main thread fige » des qu'une
// operation bloque la boucle Unity trop longtemps, et appelle alors
// `UnityEngine.Diagnostics.Utils.ForceCrash(0,0)`. C'est LUI qui rend interdits les
// heap scans (`Memory.scan` suspend les threads ~10 s), qui fait tomber le jeu pendant
// une amorce un peu long, et qui oblige `battle-config.ts` a decouper son travail en
// chunks. C'est la contrainte de fond du harnais, pas une fatalite.
//
// CHAINE NATIVE (lue au decompile, build gqfc5mff6c) :
//   `IdunMetaLogic.FeatureUnlocker$$HasUnityFreezeDetectorIn{Battle,Meta}Enabled` -> bool
//     -> `idun.shared.commands.UseUnityFreezeDetectorIfNecessaryCommand$$Use...IfNecessary`
//          arg=0 -> `UnityFreezeDetector$$Disable` (retire le handler + `TimeoutDetector.Stop`)
//          arg=1 -> arme le TimeoutDetector
//            -> `UnityFreezeDetector$$HandleOnFreezeDetected` :
//                 mode(this+0x44)=0 -> `Debug.LogError` seulement
//                 mode=1            -> rapport IdunCrashlyticsError
//                 mode=2            -> `UnityEngine.Diagnostics.Utils.ForceCrash(0,0)`  <-- le kill
//
// DEUX VERROUS (ceinture + bretelles) :
//
//  1. Les deux `Has...Enabled` rendent 0. C'est le jeu LUI-MEME qui decide alors de ne
//     pas armer le detecteur, par son propre chemin de code, et ca tient a CHAQUE
//     transition meta <-> bataille. Appeler `Disable()` sur l'instance ne suffirait PAS :
//     `UseUnityFreezeDetectorIfNecessaryCommand` le re-arme au changement de mode.
//
//  2. `HandleOnFreezeDetected` devient un no-op qui remonte un `diag`. Si quelque chose
//     arme quand meme le detecteur, le pire devient une ligne de log au lieu d'un process
//     tue. On ne touche PAS au champ mode `this+0x44` : sa semantique est une INFERENCE du
//     decompile (branches 0/1/2), alors que court-circuiter la methode entiere ne repose
//     sur aucune hypothese de layout.
//
// `Interceptor.replace` est sur ici : aucune des trois methodes n'est un hot path
// (les `Has...` fire aux transitions, `HandleOnFreezeDetected` seulement sur un vrai gel).
// A NE PAS confondre avec les pumps de `main-pump.ts`, qui remplacent `Update` (chaque
// frame) et DOIVENT rappeler l'original.

import { findClass, findClassAnywhere, findMethod } from "../il2cpp/helpers.js";
import { log } from "./diag.js";

/** Garde les NativeCallback en vie (sinon le GC de Frida les collecte -> crash). */
const keepAlive: NativeCallback<"void" | "bool", ["pointer", "pointer"]>[] = [];

function forceFalse(klass: NativePointer | null, clsName: string, method: string): boolean {
    if (!klass) return false;
    const mi = findMethod(klass, method);
    if (!mi || mi.ptr.isNull()) {
        log(`[freeze] ${clsName}.${method} introuvable`);
        return false;
    }
    const cb = new NativeCallback(function () {
        return 0;                       // le jeu n'arme jamais le detecteur
    }, "bool", ["pointer", "pointer"]);
    Interceptor.replace(mi.ptr, cb);
    keepAlive.push(cb as never);
    log(`[freeze] ${clsName}.${method} -> false`);
    return true;
}

/**
 * Desarme le UnityFreezeDetector. Idempotent, sans effet si les classes sont absentes
 * (le harnais doit rester fonctionnel meme si le jeu change de structure).
 */
export function installFreezeDetectorNeutralizer(): void {
    let n = 0;

    // --- Verrou 1 : les feature-flags rendent false ---------------------------------
    // `FeatureUnlocker` porte la vraie decision ; `FeatureUnlockerProxy` la delegue —
    // on neutralise les DEUX, l'appelant reel dependant du contexte (meta vs bataille).
    for (const cls of ["FeatureUnlocker", "FeatureUnlockerProxy"]) {
        const k = findClassAnywhere("IdunMetaLogic", cls);
        if (!k) { log(`[freeze] IdunMetaLogic.${cls} introuvable`); continue; }
        for (const m of ["HasUnityFreezeDetectorInBattleEnabled",
                         "HasUnityFreezeDetectorInMetaEnabled"]) {
            if (forceFalse(k, cls, m)) n++;
        }
    }

    // --- Verrou 2 : la detection ne peut plus tuer ----------------------------------
    const fd = findClass("Assembly-CSharp.dll", "idun.unity.utils", "UnityFreezeDetector")
        ?? findClassAnywhere("idun.unity.utils", "UnityFreezeDetector");
    if (!fd) {
        log("[freeze] UnityFreezeDetector introuvable — verrou 2 non pose");
    } else {
        const mi = findMethod(fd, "HandleOnFreezeDetected");
        if (!mi || mi.ptr.isNull()) {
            log("[freeze] HandleOnFreezeDetected introuvable — verrou 2 non pose");
        } else {
            const cb = new NativeCallback(function () {
                // On NE rappelle PAS l'original : c'est lui qui contient le ForceCrash.
                send({ t: "diag", msg: "[freeze] gel detecte par le jeu — kill neutralise" });
            }, "void", ["pointer", "pointer"]);
            Interceptor.replace(mi.ptr, cb);
            keepAlive.push(cb as never);
            log("[freeze] HandleOnFreezeDetected -> no-op (ForceCrash neutralise)");
            n++;
        }
    }

    log(`[freeze] neutralisation posee (${n} point(s))`);
}
