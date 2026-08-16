// applyStack + StreamDispatcher hooks — event trace correlated to triggers.
//
// We hook directly on `IdunBattle.Streams.StreamDispatcher.Action` and
// `.StartGroup` — the dispatcher methods the game calls to emit events.
// Every event passes through here before any listener filtering, so we
// see the full unfiltered stream.
//
// Prereq: the main-thread pumps must use `Interceptor.replace` (not `attach`).
// Frida's `attach` applies a per-thread recursion guard that silently
// suppresses nested hook callbacks fired from inside another `attach`
// onEnter — so if the pump used `attach` and drained pending IL2CPP work
// synchronously in its callback, any hook on those methods would be dead.
// `replace` has no recursion guard. See runtime/main-pump.ts.

import { findClassAnywhere, findMethod } from "../il2cpp/helpers.js";
import { serializeToJson } from "../il2cpp/serializer.js";

export interface StreamEvent {
    kind: "action" | "group" | "finish";
    step?: number;    // action: StepType
    group?: number;   // group: GroupType (StartGroup ouvre ce scope)
    entity: number;   // finish: non significatif (FinishGroup ferme le dernier groupe ouvert)
    // JSON-serialized Dict<TagKey,int>. Host parses + gets enum names for free
    // via the game's Newtonsoft settings (StringEnumConverter registered globally).
    tags?: string | null;
    source?: string | null;
}

export interface ApplyFrame {
    role: "live" | "built" | "mirror";
    target: StreamEvent[];
}

export const applyStack: ApplyFrame[] = [];

export function pushApply(
    role: "live" | "built" | "mirror", target: StreamEvent[],
): void {
    applyStack.push({ role, target });
}

export function popApply(): void {
    applyStack.pop();
}

/** Une frame ORPHELINE désigne son module par son `role` — sans ça, une fuite ne se lit que
 *  comme un nombre, et « qui a poussé » reste à deviner.
 *
 *  Mesuré le 2026-08-09 (#596-r1) : 2 frames survivantes après une bataille dont la bascule
 *  de tour ne s'est jamais faite. Le compte est resté à **exactement 2** à travers deux
 *  batailles saines et ~40 messages de plus (dont deux tours d'IA complets) — ce qui RÉFUTE
 *  notre mode de fuite connu, le recursion guard de Frida qui supprime le `onLeave` des
 *  sub-messages (cf. l'en-tête de `features/message-trace.ts`) : celui-là grossirait à chaque
 *  imbrication. Restent deux événements ponctuels, non nommés. */
export function applyStackRoles(): string[] {
    return applyStack.map((f) => f.role);
}

/** Y a-t-il un `Apply` de message EN VOL ? Fenêtre d'armement pour les capteurs trop chauds
 *  pour tourner en permanence (`System.Exception..ctor`). Compté à part de `applyStack.length`,
 *  qui inclut les frames de capture posées hors apply (`features/battle-events.ts`). */
let _applyDepth = 0;
export function enterApply(): void { _applyDepth++; }
export function leaveApply(): void { if (_applyDepth > 0) _applyDepth--; }
export function insideApply(): number { return _applyDepth; }

// --- LES TROIS ANCRAGES D'`Apply`, DÉBRANCHABLES UN PAR UN (#596-r1) --------------------
//
// POURQUOI. Sous IL2CPP/Windows une exception managée EST une exception SEH ; le jeu en lève
// et en rattrape en permanence (398 relevées en une session). Ce n'est PAS le trampoline
// d'entrée qui gêne, c'est le `onLeave` : pour l'implémenter, Frida RÉÉCRIT L'ADRESSE DE
// RETOUR sur la pile pour la faire pointer sur son thunk. L'`.pdata` du PE ne décrit pas
// cette zone, donc `RtlVirtualUnwind` qui remonte à la recherche d'un `catch` arrive sur une
// adresse qu'aucune information de déroulement ne couvre. Ça expliquerait d'un coup les deux
// symptômes : le `onLeave` jamais appelé (frame orpheline) ET un `catch` natif sauté.
//
// ⚠ CE N'EST QU'UNE HYPOTHÈSE, et la frame orpheline NE LA SOUTIENT PAS : elle s'explique
// déjà par « `onLeave` non appelé sur exception », ce qui arrive sur TOUTE exception, y
// compris parfaitement rattrapée. Le seul relevé qui tranche est la contre-épreuve — d'où
// ces interrupteurs, et d'où le fait qu'il en faille TROIS. `humanAi` seul a été coupé le
// 2026-08-16 : REFUTÉ, la bataille se fige au même point.
//
// Les handles vivent ICI, dans un module FEUILLE, et pas dans `recorder.ts` : le RPC qui les
// bascule est côté `features/`, et le faire dépendre du recorder (qui importe `sim-engine`)
// fabriquerait un cycle. `apply-stack` n'importe que des helpers IL2CPP.
export type AncrageApply = "runnerApply" | "ai" | "humanAi";

const ANCRAGES: AncrageApply[] = ["runnerApply", "ai", "humanAi"];

const handles: Record<AncrageApply, InvocationListener | null> = {
    runnerApply: null, ai: null, humanAi: null,
};
// défaut = comportement historique : on ne change rien sans qu'on le demande.
const voulus: Record<AncrageApply, boolean> = {
    runnerApply: true, ai: true, humanAi: true,
};

export function ancrageVoulu(n: AncrageApply): boolean { return voulus[n]; }

/** Appelé par `recorder.install()` : mémorise le handle pour pouvoir le détacher à chaud. */
export function enregistrerAncrage(
    n: AncrageApply, l: InvocationListener | null,
): void {
    handles[n] = l;
}

export function etatAncrages(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const n of ANCRAGES) out[n] = { voulu: voulus[n], enPlace: handles[n] !== null };
    return out;
}

/** Branche/débranche SANS reinject. Le `voulu` survit à un `install()` ultérieur, sinon un
 *  simple changement de runner rearmerait la sonde au milieu de la contre-épreuve et on
 *  lirait le résultat de l'autre régime.
 *
 *  (!) À jouer HORS bataille : détacher pendant un `Apply` en vol laisserait la frame que
 *  son `onEnter` a poussée sans le `onLeave` qui la dépile — on fabriquerait exactement la
 *  fuite qu'on cherche à mesurer. On rend donc la hauteur de pile, à l'appelant de juger. */
export function reglerAncrages(
    patch: Partial<Record<AncrageApply, boolean>>,
): Record<string, unknown> {
    const actions: Record<string, string> = {};
    let flush = false;
    for (const n of ANCRAGES) {
        const veut = patch[n];
        if (typeof veut !== "boolean" || veut === voulus[n]) continue;
        voulus[n] = veut;
        if (!veut && handles[n]) {
            try { handles[n]!.detach(); actions[n] = "detache"; }
            catch { actions[n] = "detache-echec"; }
            handles[n] = null;
            flush = true;
        } else if (veut && !handles[n]) {
            // Le rattachement passe par `recorder.install()` — c'est lui qui tient les
            // filtres d'identité. On ne le refait pas ici, on DIT que c'est redemandé.
            actions[n] = "redemande-au-prochain-install";
        } else {
            actions[n] = "inchange";
        }
    }
    if (flush) Interceptor.flush();
    return {
        ok: true, actions, etat: etatAncrages(),
        pileApply: applyStack.length,
        avertissement: applyStack.length > 0
            ? "pile NON VIDE : une frame est en vol ou orpheline — basculer HORS bataille"
            : null,
    };
}

let streamHooksInstalled = false;
let _actionFiresTotal = 0;
let _actionFiresStackEmpty = 0;

export function streamHookStats(): Record<string, number> {
    return {
        actionFiresTotal: _actionFiresTotal,
        actionFiresStackEmpty: _actionFiresStackEmpty,
        applyStackDepth: applyStack.length,
        installed: streamHooksInstalled ? 1 : 0,
    };
}

function readManagedString(sp: NativePointer): string | null {
    if (sp.isNull()) return null;
    try {
        const len = sp.add(0x10).readS32();
        if (len > 0 && len < 500) return sp.add(0x14).readUtf16String(len);
    } catch { /* */ }
    return null;
}


export function ensureStreamHooks(): void {
    if (streamHooksInstalled) return;

    const cls = findClassAnywhere("IdunBattle.Streams", "StreamDispatcher");
    if (!cls) {
        send({ t: "stream_hooks_err", reason: "class-missing" });
        try { send({ t: "diag", msg: "[apply-stack] StreamDispatcher class not found — retry later" }); } catch { /* */ }
        // Pas de set installed=true → retry au prochain appel.
        return;
    }
    streamHooksInstalled = true;

    const actionMi = findMethod(cls, "Action");
    const groupMi = findMethod(cls, "StartGroup");
    const finishMi = findMethod(cls, "FinishGroup");

    if (actionMi && !actionMi.ptr.isNull()) {
        // Action(StepType stepType, BEntityId entityId, Dictionary<TagKey,int> tags)
        // ARM64 method entry: (this, stepType, entityId, tags, methodInfo)
        Interceptor.attach(actionMi.ptr, {
            onEnter(args) {
                _actionFiresTotal++;
                if (applyStack.length === 0) {
                    _actionFiresStackEmpty++;
                    return;
                }
                try {
                    applyStack[applyStack.length - 1].target.push({
                        kind: "action",
                        step: args[1].toInt32(),
                        entity: args[2].toInt32(),
                        tags: serializeToJson(args[3]),
                    });
                } catch { /* */ }
            },
        });
    }

    if (groupMi && !groupMi.ptr.isNull()) {
        // StartGroup(GroupType, BEntityId, string, Nullable<BEntityId>)
        Interceptor.attach(groupMi.ptr, {
            onEnter(args) {
                if (applyStack.length === 0) return;
                try {
                    applyStack[applyStack.length - 1].target.push({
                        kind: "group",
                        group: args[1].toInt32(),
                        entity: args[2].toInt32(),
                        source: readManagedString(args[3]),
                    });
                } catch { /* */ }
            },
        });
    }

    if (finishMi && !finishMi.ptr.isNull()) {
        // FinishGroup(this) — paramétrless : ferme le DERNIER groupe ouvert
        // (discipline de pile). On pousse un marqueur de fermeture pour que
        // l'ingest puisse reconstruire le nesting des scopes (chaque action
        // connaît son groupe englobant = ex. User_UseAbility/NormalAttack →
        // entité acteur, qui encadre le Info arme + ses UnitDamaged).
        Interceptor.attach(finishMi.ptr, {
            onEnter() {
                if (applyStack.length === 0) return;
                try {
                    applyStack[applyStack.length - 1].target.push({
                        kind: "finish",
                        entity: 0,
                    });
                } catch { /* */ }
            },
        });
    }

    Interceptor.flush();
    send({ t: "stream_hooks_installed",
        actionPtr: actionMi?.ptr.toString() ?? null,
        groupPtr: groupMi?.ptr.toString() ?? null,
        finishPtr: finishMi?.ptr.toString() ?? null,
    });
    try {
        send({ t: "diag", msg: "[apply-stack] stream hooks installed: "
            + "Action=" + (actionMi?.ptr.toString() ?? "missing")
            + " StartGroup=" + (groupMi?.ptr.toString() ?? "missing")
            + " FinishGroup=" + (finishMi?.ptr.toString() ?? "missing") });
    } catch { /* */ }
}
