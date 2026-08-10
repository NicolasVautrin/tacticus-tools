// gc-rendezvous — un GC force sous Frida gele-t-il le jeu ? OUI. MESURE.
//
// ═══ VERDICT, 2026-08-10, build `rnca9r7q6c` ═══
//
// Le TEMOIN a suffi : `contexte: "frida"` (donc PAS depuis le pump), sans aucun envoi, sans
// delegate, sans `runtime_invoke` -- le RPC n'est jamais revenu (60 s) et
// `Get-Process().Responding` est passe a `False`. Lecture du process fige : **145 threads
// dans `ntdll.dll`** + 1 dans `win32u`, AUCUN dans `GameAssembly.dll`, et le main thread
// parque avec ZERO cadre `GameAssembly` -- suspendu a un safepoint, pas bloque dans du code.
//
// Le regime `pump` n'a donc jamais eu besoin d'etre joue : le couple GC x Frida suffit, la
// question du contexte est sans objet.
//
// CE QUE CA RETOURNE DANS #600 : le callback etait un FAUX COUPABLE pour le gel. Il y avait
// DEUX pannes traitees comme une seule --
//   (a) callback NUL -> `raise_null_reference_exception` a la RECEPTION -> process MORT ;
//   (b) une collecte GC pendant l'envoi -> stop-the-world qui ne repart pas -> process FIGE.
// (a) est etabli par le decompile, (b) par cette sonde. Elles n'ont rien a voir.
//
// La sonde reste versionnee : elle est la SEULE facon de remesurer (b) au prochain build, et
// `gcRoot.collect()` REFUSE desormais par defaut a cause d'elle.
//
// POURQUOI CETTE SONDE EXISTE (#600, 2026-08-10)
//
// L'envoi natif d'une Operation a gele le jeu deux fois. La lecture du process fige
// (`OpenThread` + `GetThreadContext`, aucun debugger sur la machine) a donne :
//
//   - 142 threads sur 142 avec le RIP dans `ntdll.dll`, AUCUN dans `GameAssembly.dll` ;
//   - le main thread sur trois cadres : `il2cpp_runtime_invoke` -> `Runtime::Invoke` ->
//     `FUN_1801eb760+0xd5`, une primitive de RENDEZ-VOUS (compteur de recursion en TLS,
//     LOCK/UNLOCK, puis << tant qu'il reste des attendeurs : signaler, attendre >>) ;
//   - CPU du process plat.
//
// Personne ne boucle : tout le monde attend. La lecture la plus economique est un
// stop-the-world qui ne repart pas -- un GC, ou une suspension de threads. `CLAUDE.md`
// porte deja l'avertissement jumeau : Frida suspend les threads pendant un scan de tas
// IL2CPP, et le detecteur de freeze d'Unity tue alors le process.
//
// CE QUE LA SONDE TRANCHE, ET CE QU'ELLE NE TRANCHE PAS
//
// Si forcer une collecte GELE le jeu, alors le gel n'a RIEN A VOIR avec le callback ni avec
// l'envoi : il y a deux pannes distinctes que le chantier traitait comme une seule -- le
// callback nul qui LEVE a la reception (etabli par le decompile) et un rendez-vous GC au
// moment de l'envoi. Si la collecte passe, l'hypothese est affaiblie, PAS morte : une
// collecte forcee a un instant calme n'est pas une collecte declenchee au milieu d'un appel.
// Ecrire le second resultat comme un blanc-seing serait la meme faute que d'habitude.
//
// DEUX REGIMES, ET L'ORDRE COMPTE
//
//   `contexte: "frida"` -- collecte depuis le thread RPC de Frida. C'est le TEMOIN.
//   `contexte: "pump"`  -- collecte depuis l'interieur du handler `Interceptor` du pump,
//                          sur le main thread. C'est le regime SUSPECT : c'est exactement
//                          la ou tournait `expeditionDispatch`.
//
// Jouer le temoin d'abord : s'il gele, on n'aura plus l'occasion de jouer l'autre, et on
// saura deja que le couple GC x Frida suffit, sans le pump.
//
// ⚠ NE PAS ARMER CETTE SONDE EN ROUTINE. `gcRoot.collect()` est reserve a une demande
// explicite (cf. `gc-root.ts`) : un GC complet sur ce jeu n'est pas gratuit.

import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

interface Mesure {
    utiliseAvant: number | null;
    tasAvant: number | null;
    utiliseApres: number | null;
    tasApres: number | null;
    /** `true` si l'export a repondu. `false` = `il2cpp_gc_collect` absent, donc RIEN
     *  n'a ete tente -- a ne surtout pas lire comme << la collecte a echoue >>. */
    appelee: boolean;
    ms: number;
}

function collecter(generations: number): Mesure {
    const utiliseAvant = gcRoot.usedSize();
    const tasAvant = gcRoot.heapSize();
    const t0 = Date.now();
    // `true` = l'echappatoire consciente : cette sonde EXISTE pour declencher le gel.
    const appelee = gcRoot.collect(generations, true);
    const ms = Date.now() - t0;
    return {
        utiliseAvant, tasAvant,
        utiliseApres: gcRoot.usedSize(), tasApres: gcRoot.heapSize(),
        appelee, ms,
    };
}

export function register(ctx: Ctx): void {
    /** body: { contexte?: "frida" | "pump", generations?: number }
     *
     *  ⚠ CE RPC PEUT GELER LE JEU -- c'est precisement ce qu'il mesure. Il n'ecrit rien
     *  sur le compte : au pire il coute une relance. */
    ctx.rpc.gcRendezvous = (body?: {
        contexte?: string; generations?: number;
    }): Promise<unknown> => {
        const contexte = body?.contexte === "pump" ? "pump" : "frida";
        const generations = typeof body?.generations === "number"
            ? body.generations : 2;

        // Le journal part vers le host AVANT la collecte : si le jeu gele pendant, cette
        // ligne est la derniere chose qu'on aura, et elle dit lequel des deux regimes
        // tournait. Un temoin qui reste dans le process fige ne sert a rien.
        log("[gc-rendezvous] collecte demandee, contexte=" + contexte
            + " generations=" + generations);

        if (contexte === "frida") {
            // Pas de `queueOnMainThread` : on reste sur le thread RPC de Frida.
            const m = collecter(generations);
            log("[gc-rendezvous] frida : rendu en " + m.ms + " ms");
            return Promise.resolve({ ok: true, contexte, ...m,
                note: "TEMOIN -- collecte hors du pump. Rendre la main ici ne dit RIEN "
                    + "du regime `pump`, qui est le suspect." });
        }
        return queueOnMainThread(() => {
            const m = collecter(generations);
            log("[gc-rendezvous] pump : rendu en " + m.ms + " ms");
            return { ok: true, contexte, ...m,
                note: "REGIME SUSPECT -- collecte depuis l'interieur du handler du pump, "
                    + "sur le main thread, la ou tournait `expeditionDispatch`. Rendre la "
                    + "main AFFAIBLIT l'hypothese du rendez-vous GC ; ca ne la tue pas, "
                    + "une collecte a un instant calme n'etant pas une collecte declenchee "
                    + "au milieu d'un appel natif." };
        });
    };
}
