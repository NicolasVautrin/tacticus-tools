// #149 — Traceur d'EXECUTION de l'arbre DSL natif (confront node-par-node vs le port Python).
//
// Le walker natif execute l'arbre par RECURSION : chaque nœud appelle ses enfants via un des 4
// contrats d'eval. On hooke les 4 familles (bases abstraites de `IdunBattle.DSL`), on maintient une
// PROFONDEUR d'appel par thread, et la sequence (classe, profondeur, kind) EST l'arbre (preorder +
// depth = bijection). cf. docs/rl/dsl-effect-nodes.md + le probe `dslNodeProbe`/`dslLazyProbe`.
//
//   Effets     : AbilityBehaviour.Execute        (kind E) ~76 concretes
//   Predicats  : AbilityTrigger.ShouldTrigger    (kind T) ~108
//   Selecteurs : TargetsSelector.Select          (kind S) ~147
//   Valeurs    : AAmountFormula.Calculate         (kind V) ~88
//
// ON-DEMAND (jamais auto-arme) : ~419 hooks sur des methodes ULTRA-CHAUDES -> attache a l'arm,
// DETACHE au disarm. GATE sur la fenetre d'un `<Ability>.ExecuteBehaviour` precis (resolu par nom) :
// on ne capture QUE ce qui execute entre son enter et son leave (sur le thread), pas le churn IA/pred.

import {
    findClassAnywhere, findMethod, s, class_get_name, class_get_namespace, class_get_parent,
    domain_get, domain_get_assemblies, assembly_get_image, image_get_class_count, image_get_class,
} from "../il2cpp/helpers.js";
import { log } from "../runtime/diag.js";

interface Ctx { rpc: Record<string, (...args: any[]) => unknown>; }

// [namespace, classe de base, methode d'eval, kind]
const FAMILIES: Array<[string, string, string, string]> = [
    ["IdunBattle.DSL", "AbilityBehaviour", "Execute", "E"],
    ["IdunBattle.DSL", "AbilityTrigger", "ShouldTrigger", "T"],
    ["IdunBattle.DSL", "TargetsSelector", "Select", "S"],
    ["IdunBattle.DSL", "AAmountFormula", "Calculate", "V"],
];

function fqn(k: NativePointer): string {
    const ns = s(class_get_namespace(k) as NativePointer);
    const cn = s(class_get_name(k) as NativePointer);
    return ns ? ns + "." + cn : cn;
}
function hasAncestor(k: NativePointer, target: NativePointer): boolean {
    let p = class_get_parent(k) as NativePointer;
    let g = 0;
    while (!p.isNull() && g++ < 12) {
        if (p.equals(target)) return true;
        p = class_get_parent(p) as NativePointer;
    }
    return false;
}

interface Target { name: string; kind: string; ptr: NativePointer; }

let targets: Target[] | null = null;     // enumere une fois (cache)
const listeners: InvocationListener[] = [];   // hooks des 4 familles (detaches au disarm)
let gateListener: InvocationListener | null = null;

// Etat de capture (thread unique de logique de bataille — 1 pile de profondeur/thread).
let windowOpen = false;                  // dans la fenetre ExecuteBehaviour ?
let maxTrees = 1;
const trees: Array<Array<{ cls: string; kind: string; depth: number }>> = [];
const depthByThread = new Map<number, number>();
let current: Array<{ cls: string; kind: string; depth: number }> | null = null;

/** Enumere les sous-classes concretes des 4 familles (scan unique, cache). */
function enumerate(): Target[] {
    if (targets) return targets;
    const bases = FAMILIES.map(([ns, cls, ev, kind]) => {
        const b = findClassAnywhere(ns, cls);
        if (b === null) log("[dsl-trace] base introuvable: " + ns + "." + cls);
        return { base: b, ev, kind };
    }).filter((x) => x.base !== null) as Array<{ base: NativePointer; ev: string; kind: string }>;

    const out: Target[] = [];
    const domain = domain_get() as NativePointer;
    const sizePtr = Memory.alloc(4);
    const assemblies = domain_get_assemblies(domain, sizePtr) as NativePointer;
    const acount = sizePtr.readU32();
    for (let i = 0; i < acount; i++) {
        const asm = assemblies.add(i * Process.pointerSize).readPointer();
        const image = assembly_get_image(asm) as NativePointer;
        const cc = image_get_class_count(image) as number;
        for (let j = 0; j < cc; j++) {
            const k = image_get_class(image, j) as NativePointer;
            for (const { base, ev, kind } of bases) {
                if (!hasAncestor(k, base)) continue;
                const m = findMethod(k, ev);
                if (m && !m.ptr.isNull()) out.push({ name: fqn(k), kind, ptr: m.ptr });
                break;   // une classe n'appartient qu'a une famille
            }
        }
    }
    targets = out;
    log("[dsl-trace] enumere " + out.length + " methodes d'eval (4 familles)");
    return out;
}

function nodeOnEnter(this: InvocationContext, name: string, kind: string): void {
    if (!windowOpen) return;
    const tid = this.threadId;
    const d = depthByThread.get(tid) || 0;
    if (d === 0) current = [];
    if (current) current.push({ cls: name, kind, depth: d });
    depthByThread.set(tid, d + 1);
}
function nodeOnLeave(this: InvocationContext): void {
    if (!windowOpen) return;
    const tid = this.threadId;
    const d = (depthByThread.get(tid) || 1) - 1;
    depthByThread.set(tid, d);
    if (d === 0 && current) {
        trees.push(current);
        current = null;
        if (trees.length >= maxTrees) windowOpen = false;   // assez capture -> stop (sans detacher)
    }
}

/** Arme : (1) hooke les 4 familles, (2) hooke la fenetre = `<abilityNs>.<abilityCls>.ExecuteBehaviour`
 * (resolu par nom) qui OUVRE/FERME la capture. `nTrees` = nb d'arbres a capturer (defaut 1). */
function arm(abilityNs: string, abilityCls: string, nTrees?: number): unknown {
    if (listeners.length > 0) return { ok: false, error: "deja arme — disarm d'abord", hooks: listeners.length };
    const gateKlass = findClassAnywhere(abilityNs, abilityCls);
    if (gateKlass === null) return { ok: false, error: "ability introuvable: " + abilityNs + "." + abilityCls };
    const gate = findMethod(gateKlass, "ExecuteBehaviour");
    if (!gate || gate.ptr.isNull()) return { ok: false, error: abilityCls + ".ExecuteBehaviour introuvable" };

    const tg = enumerate();
    maxTrees = nTrees && nTrees > 0 ? nTrees : 1;
    trees.length = 0;
    depthByThread.clear();
    current = null;
    windowOpen = false;

    // Hooks des 4 familles (gated par windowOpen — cheap boolean quand ferme).
    for (const t of tg) {
        const name = t.name, kind = t.kind;
        try {
            listeners.push(Interceptor.attach(t.ptr, {
                onEnter(this: InvocationContext) { nodeOnEnter.call(this, name, kind); },
                onLeave(this: InvocationContext) { nodeOnLeave.call(this); },
            }));
        } catch { /* body absent/gshared — skip */ }
    }
    // Gate : ouvre la capture a l'entree de ExecuteBehaviour, ferme a la sortie (par thread implicite —
    // le tree racine est bracketise par depth 0). On (re)ouvre tant qu'on n'a pas atteint maxTrees.
    gateListener = Interceptor.attach(gate.ptr, {
        onEnter() { if (trees.length < maxTrees) windowOpen = true; },
        onLeave() { windowOpen = false; },
    });
    return { ok: true, hooks: listeners.length, gate: abilityNs + "." + abilityCls + ".ExecuteBehaviour", maxTrees };
}

function disarm(): unknown {
    for (const l of listeners) { try { l.detach(); } catch { /* */ } }
    listeners.length = 0;
    if (gateListener) { try { gateListener.detach(); } catch { /* */ } gateListener = null; }
    windowOpen = false;
    depthByThread.clear();
    current = null;
    return { ok: true, disarmed: true };
}

/** Renvoie les arbres captures (chacun = sequence {cls, kind, depth} = preorder+profondeur). */
function lastCast(): unknown {
    return { ok: true, armed: listeners.length > 0, capturedTrees: trees.length, trees };
}

export function register(ctx: Ctx): void {
    ctx.rpc.dslTraceArm = (ns: string, cls: string, n?: number) => arm(ns, cls, n);
    ctx.rpc.dslTraceLastCast = () => lastCast();
    ctx.rpc.dslTraceDisarm = () => disarm();
}
