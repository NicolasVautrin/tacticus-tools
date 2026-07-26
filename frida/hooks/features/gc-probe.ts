// Sonde GC managé IL2CPP — l'INSTRUMENT du protocole de mesure #132.
//
// Contexte : `MAX_RUNNERS` valait 10 parce qu'il était dérivé (2026-07-03) d'un
// COMMENTAIRE écrit le 2026-05-24 — « ~100 pins par bataille,
// `IdunRunner.Initialize` échoue au-delà de ~900 » — jamais re-mesuré depuis.
//
// MESURÉ le 2026-07-26 avec ce module (probe_132_gcroot_budget.py) : coût réel
// **3 handles par bataille**, dérive nulle sur 12 cycles, et un build RÉUSSIT
// avec **5004 handles épinglés**. La dérivation était fausse ; le cap est passé
// à 50, borné par la MÉMOIRE (~3,6 Mo de tas managé par runner vivant).
//
// Ce module reste l'instrument : il rend les trois grandeurs qui ont tranché.
//
//   gcStats        count (handles épinglés) + used/heap size du tas managé.
//                  Le tas est le CONTRÔLE : si un échec d'Initialize coïncide
//                  avec un tas au plus haut, les handles ne sont pas prouvés
//                  coupables (même confond qu'on corrige, un étage au-dessus).
//   gcPin(n)       LEST : monte le compteur de handles SANS créer de bataille.
//                  C'est le découplage que l'observation de mai ne pouvait pas
//                  faire — les deux variables y montaient toujours ensemble.
//   gcUnpin        relâche le lest (et lui seul — jamais les pins réels).
//   gcCollect      force un GC managé. Aucun hook n'en appelait jamais.
//
// Read-only sauf gcPin/gcUnpin/gcCollect, qui n'agissent QUE sur le lest et le
// collecteur. Aucun Interceptor, aucun hook armé : le register n'expose que des
// RPC. À n'utiliser qu'ATELIER VIDE (l'échec attendu de la manip B est un
// « system error » natif).

import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { listRunners } from "../game/runner-registry.js";
import { Ctx } from "../controller.js";

function snapshot(): Record<string, unknown> {
    return {
        ok: true,
        count: gcRoot.count(),
        ballast: gcRoot.ballastCount(),
        usedSize: gcRoot.usedSize(),
        heapSize: gcRoot.heapSize(),
        runners: listRunners().length,
    };
}

export function register(ctx: Ctx): void {
    /** Compteur de handles + tas managé + nombre de runners vivants, en un point.
     *  Read-only. Le point de mesure de TOUTES les manips du protocole #132. */
    ctx.rpc.gcStats = (): Promise<unknown> =>
        queueOnMainThread(() => snapshot());

    /** LEST : épingle `n` chaînes managées fraîches pour monter le compteur de
     *  handles sans construire de bataille. body: { n } */
    ctx.rpc.gcPin = (body?: { n?: number }): Promise<unknown> =>
        queueOnMainThread(() => {
            const n = Math.max(0, Math.min(5000, Math.floor(body?.n ?? 0)));
            const r = gcRoot.pinBallast(n);
            return { ...snapshot(), requested: n, pinned: r.pinned };
        });

    /** Relâche TOUT le lest (jamais les pins réels des runners). */
    ctx.rpc.gcUnpin = (): Promise<unknown> =>
        queueOnMainThread(() => {
            const released = gcRoot.releaseBallast();
            return { ...snapshot(), released };
        });

    /** Force un GC managé, puis re-mesure. body: { maxGenerations?=2 } */
    ctx.rpc.gcCollect = (body?: { maxGenerations?: number }): Promise<unknown> =>
        queueOnMainThread(() => {
            const before = snapshot();
            const called = gcRoot.collect(
                typeof body?.maxGenerations === "number" ? body.maxGenerations : 2);
            return { ...snapshot(), called, before };
        });
}
