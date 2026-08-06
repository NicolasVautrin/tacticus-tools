// Armement PAR RUNNER des captures diagnostiques (#483).
//
// LE DEFAUT QUE CE MODULE FERME. Six features de `frida/hooks/features/` capturent
// PAR RUNNER (`OriginBuffers` + `getTraceOrigin()`, champ `originRunnerId`) et leurs
// RPC `*Dump`/`*Clear` filtrent bien par `runnerId` — mais leur PORTE d'armement
// etait un booleen de MODULE, session-global (`trace.on`, `trace.enabled`,
// `audit.enabled`, `state.enabled`). Les probes appellent leur `*Off` dans un
// `finally`, donc il s'execute TOUJOURS : en regime 4-en-parallele, le premier probe
// qui finit DESARME la capture des autres. La victime dumpe alors un seau TRONQUE,
// sans aucune erreur — un vert qui ment.
//
// L'ASYMETRIE est ce qui compte. Un `On` de trop ne corrompt AUCUNE donnee (les seaux
// sont deja par origine) : il ne coute que de la perf. Un `Off` de trop detruit une
// mesure en silence. Ce module ne rend donc pas l'armement « exact » : il rend le
// DESARMEMENT incapable de traverser la frontiere d'un autre acteur.
//
// SEMANTIQUE, et la compatibilite ascendante qui va avec :
//   - `arm(kind)`      (sans runnerId) = armement GLOBAL — le comportement historique.
//                      `capturing()` devient vrai pour TOUTES les origines.
//   - `arm(kind, rid)` = armement NOMINATIF — seuls les events dont l'origine courante
//                      est `rid` sont captures.
//   - `disarm(kind)`   (sans runnerId) = desarme le GLOBAL, et **ne touche PAS** aux
//                      armements nominatifs. C'est LA regle : un appelant qui a oublie
//                      de passer son `runnerId` ne peut plus eteindre celui d'un autre.
//   - `disarm(kind, rid)` = desarme CE runner, et laisse le global intact.
// Consequence : aucun appelant existant ne regresse (il arme et desarme le global,
// comme avant), et le defaut disparait des que l'appelant passe son `runnerId`.
//
// COUT SUR CHEMIN CHAUD. `capturing()` est appele depuis des callbacks
// d'`Interceptor` qui firent AUSSI pendant l'IA du jeu live (p.ex.
// `IdunBattle.Core.Services.ProbableDamageEvent$$.ctor`). Il est ecrit pour que le cas
// dominant — rien d'arme — coute DEUX lectures de champ et rien d'autre : le `Set`
// vide court-circuite AVANT meme d'appeler `getTraceOrigin()`. Quand quelque chose est
// arme, s'y ajoutent une lecture de variable de module (`getTraceOrigin` est
// `return current;`) et un `Set.has`. La doctrine « pas de broad-hooks sur hot path »
// reste entiere : ce module ne pose aucun hook, il ne fait que decider.
//
// CE QU'IL NE FAIT PAS. Il ne connait ni les buffers ni les `Interceptor` : une feature
// qui doit DETACHER quand plus personne n'est arme enregistre un `onDisarmed(kind, cb)`.
// Le callback n'est appele que sur une transition vers « plus aucun acteur », jamais a
// l'armement — c'est ce qui garde le detachement physique en phase avec la porte
// logique, y compris quand un runner meurt (`purgeArmedForRunner`, appele par
// `runner-registry.disposeRunner`, meme hygiene que `purgeTracesForRunner`).

import { getTraceOrigin } from "./trace-origin.js";

/** Familles de capture armables. Un `kind` par FAMILLE, pas par hook : c'est la
 *  granularite a laquelle les RPC `*On`/`*Off` existent deja cote appelant. */
export type TraceKind =
    | "scorerDamage"
    | "triggeredMove"
    | "effectBonus"
    | "hit"
    | "aiUtility"
    | "aiUtilityDiagSampler"
    | "bucketAudit";

/** Ce qu'un `*Dump`/`*Status` publie a la place de l'ancien `on: <booleen global>`.
 *  Le booleen seul etait TROMPEUR des lors que l'armement est par runner : il ne
 *  disait pas POUR QUI la capture etait ouverte. */
export interface ArmedReport {
    /** Interroge avec un `runnerId` : la capture etait-elle ouverte POUR LUI.
     *  Sans `runnerId` : l'etait-elle pour QUELQU'UN (`anyArmed`). */
    on: boolean;
    /** Armement GLOBAL en cours (`On({})` sans `runnerId`). */
    armedGlobal: boolean;
    /** Runners armes NOMINATIVEMENT, tries — l'etat REEL, pas un resume. */
    armedRunners: number[];
}

class ArmedSet {
    private global = false;
    private runners = new Set<number>();

    arm(runnerId?: number | null): void {
        if (typeof runnerId === "number") this.runners.add(runnerId);
        else this.global = true;
    }

    /** ⚠ Sans `runnerId` : desarme le GLOBAL SEULEMENT. Les armements nominatifs
     *  survivent — c'est l'invariant central de ce module. */
    disarm(runnerId?: number | null): void {
        if (typeof runnerId === "number") this.runners.delete(runnerId);
        else this.global = false;
    }

    disarmAll(): void { this.global = false; this.runners.clear(); }

    /** Post-condition : `capturingFor(origin)` est FAUX apres cet appel.
     *  Sert aux extinctions par BUDGET, qui doivent pouvoir garantir qu'une origine
     *  cesse de consommer — y compris quand elle etait couverte par le global. */
    extinguish(origin: number | null): void {
        if (origin !== null) this.runners.delete(origin);
        // Le global couvrait cette origine : sans ca, la post-condition serait fausse
        // et le budget se re-testerait a chaque event (boucle d'extinction sterile).
        this.global = false;
    }

    anyArmed(): boolean { return this.global || this.runners.size > 0; }

    capturingFor(origin: number | null): boolean {
        if (this.global) return true;
        return origin !== null && this.runners.has(origin);
    }

    /** CHEMIN CHAUD — cf. l'en-tete pour le cout. */
    capturing(): boolean {
        if (this.global) return true;
        if (this.runners.size === 0) return false;
        const o = getTraceOrigin();
        return o !== null && this.runners.has(o);
    }

    report(runnerId?: number): ArmedReport {
        return {
            on: typeof runnerId === "number"
                ? this.capturingFor(runnerId)
                : this.anyArmed(),
            armedGlobal: this.global,
            armedRunners: [...this.runners].sort((a, b) => a - b),
        };
    }
}

/** Tous les kinds sont instancies d'emblee : un `armedStatusAll()` qui n'enumererait
 *  que les familles DEJA armees ne pourrait pas montrer celle qui ne l'est pas — le
 *  vice « un recenseur ne rend pas zero sur ce qu'il ne visite pas ». */
export const ALL_TRACE_KINDS: TraceKind[] = [
    "scorerDamage", "triggeredMove", "effectBonus",
    "hit", "aiUtility", "aiUtilityDiagSampler", "bucketAudit",
];

const sets = new Map<TraceKind, ArmedSet>(
    ALL_TRACE_KINDS.map((k) => [k, new ArmedSet()] as [TraceKind, ArmedSet]),
);
const disarmCallbacks = new Map<TraceKind, () => void>();

function setFor(kind: TraceKind): ArmedSet {
    let s = sets.get(kind);
    if (!s) { s = new ArmedSet(); sets.set(kind, s); }
    return s;
}

/** Appele apres tout desarmement : si plus PERSONNE n'est arme, laisse la feature
 *  detacher ses `Interceptor`. Jamais appele a l'armement. */
function notifyIfNobodyLeft(kind: TraceKind): void {
    if (setFor(kind).anyArmed()) return;
    const cb = disarmCallbacks.get(kind);
    if (!cb) return;
    try { cb(); } catch { /* best effort — un detach rate ne doit rien bloquer */ }
}

/** Arme. `runnerId` absent => armement GLOBAL (comportement historique). */
export function arm(kind: TraceKind, runnerId?: number | null): void {
    setFor(kind).arm(runnerId);
}

/** Desarme. `runnerId` absent => desarme le GLOBAL uniquement. */
export function disarm(kind: TraceKind, runnerId?: number | null): void {
    setFor(kind).disarm(runnerId);
    notifyIfNobodyLeft(kind);
}

/** Desarme TOUT (global + nominatifs). Reserve aux extinctions volontaires globales. */
export function disarmAll(kind: TraceKind): void {
    setFor(kind).disarmAll();
    notifyIfNobodyLeft(kind);
}

/** Ferme la capture POUR UNE ORIGINE (extinction par budget). */
export function extinguish(kind: TraceKind, origin: number | null): void {
    setFor(kind).extinguish(origin);
    notifyIfNobodyLeft(kind);
}

/** La capture est-elle ouverte pour l'origine COURANTE ? (garde de capture) */
export function capturing(kind: TraceKind): boolean {
    return setFor(kind).capturing();
}

/** La capture est-elle ouverte pour CETTE origine ? (compte-rendu, tests) */
export function capturingFor(kind: TraceKind, origin: number | null): boolean {
    return setFor(kind).capturingFor(origin);
}

/** Quelqu'un — global ou nominatif — est-il arme ? (decision de DETACHER) */
export function anyArmed(kind: TraceKind): boolean {
    return setFor(kind).anyArmed();
}

/** Etat REEL a publier dans un `*Dump`/`*Status`. */
export function armedReport(kind: TraceKind, runnerId?: number): ArmedReport {
    return setFor(kind).report(runnerId);
}

/** Enregistre le detachement physique a jouer quand plus personne n'est arme.
 *  Un seul par `kind` — la derniere inscription gagne (le register d'une feature
 *  ne tourne qu'une fois). */
export function onDisarmed(kind: TraceKind, cb: () => void): void {
    disarmCallbacks.set(kind, cb);
}

/** Appele par `runner-registry.disposeRunner` : un runner mort ne doit pas laisser
 *  une porte ouverte derriere lui — sinon `anyArmed()` resterait vrai pour toujours
 *  et les hooks physiques ne se detacheraient jamais. Meme hygiene que
 *  `purgeTracesForRunner`. */
export function purgeArmedForRunner(runnerId: number): void {
    for (const [kind, s] of sets) {
        try {
            s.disarm(runnerId);
            notifyIfNobodyLeft(kind);
        } catch { /* best effort — jamais bloquant */ }
    }
}

/** Etat COMPLET, tous kinds — diagnostic transverse (`traceArmedStatus`). */
export function armedStatusAll(): Record<string, ArmedReport> {
    const out: Record<string, ArmedReport> = {};
    for (const [kind, s] of sets) out[kind] = s.report();
    return out;
}
