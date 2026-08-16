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

// --- l'ancrage `AiControl$$ApplyHumanAiMessage`, DEBRANCHABLE (#596-r1) -----------------
//
// POURQUOI CE SEUL ANCRAGE A SON INTERRUPTEUR. Sous IL2CPP/Windows une exception managée EST
// une exception SEH ; le jeu en lève et en rattrape en permanence (398 relevées en une
// session). Un `Interceptor.attach` pose un trampoline SANS information de déroulement
// enregistrée, donc un unwind qui le traverse peut ne pas retrouver son `catch` natif : la
// sonde transformerait une exception RATTRAPABLE en rupture. C'est une hypothèse, et elle
// n'est testable que par une CONTRE-ÉPREUVE — d'où l'interrupteur.
//
// Et c'est CET ancrage-là parce qu'il est le seul que le régime « l'IA joue le joueur »
// traverse et qu'une partie humaine ne traverse pas : partie à la main = pas de blocage,
// partie en `--player-type 1` = blocage. C'est le seul différentiel structurel connu.
//
// Le handle vit ICI, dans un module FEUILLE, et pas dans `recorder.ts` : le RPC qui le
// bascule est côté `features/`, et le faire dépendre du recorder (qui importe `sim-engine`)
// fabriquerait un cycle. `apply-stack` n'importe que des helpers IL2CPP.
let humanAiListener: InvocationListener | null = null;
let humanAiWanted = true;   // défaut = comportement historique, on ne change rien sans le dire

export function humanAiHookWanted(): boolean { return humanAiWanted; }

/** Appelé par `recorder.install()` : mémorise le handle pour pouvoir le détacher à chaud. */
export function registerHumanAiListener(l: InvocationListener | null): void {
    humanAiListener = l;
}

/** Branche/débranche l'ancrage SANS reinject. Le `wanted` survit à un `install()` ultérieur,
 *  sinon un simple changement de runner rearmerait la sonde au milieu de la contre-épreuve.
 *
 *  (!) À jouer HORS bataille : détacher pendant un `Apply` en vol laisserait la frame que
 *  son `onEnter` a poussée sans le `onLeave` qui la dépile — on fabriquerait exactement la
 *  fuite qu'on cherche à mesurer. On rend donc la hauteur de pile, à l'appelant de vérifier. */
export function setHumanAiHook(enabled: boolean): Record<string, unknown> {
    const avant = humanAiWanted;
    humanAiWanted = enabled;
    let action = "inchange";
    if (!enabled && humanAiListener) {
        try { humanAiListener.detach(); action = "detache"; }
        catch { action = "detache-echec"; }
        humanAiListener = null;
        Interceptor.flush();
    } else if (enabled && !humanAiListener) {
        // Le rattachement passe par `recorder.install()` (c'est lui qui tient les filtres
        // d'identité) — on ne le refait pas ici, on dit juste que c'est REDEMANDE.
        action = "redemande-au-prochain-install";
    }
    return {
        ok: true, avant, apres: humanAiWanted, action,
        ancrageEnPlace: humanAiListener !== null,
        pileApply: applyStack.length,
        avertissement: applyStack.length > 0
            ? "pile NON VIDE : une frame est en vol ou orpheline — lire `pile` de battleEvents"
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
