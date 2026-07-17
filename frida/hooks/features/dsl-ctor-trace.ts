// #200 — Traceur de CONSTRUCTION de l'arbre DSL natif (GENERIQUE, toute ability).
//
// POURQUOI construction et pas execution : le traceur d'EXECUTION (dsl-trace.ts) hooke les 4
// familles concretes (`.Execute`/`.Select`/`.ShouldTrigger`/`.Calculate`), mais le runtime dispatche
// via interface/gshared (FUN_1800291d0 lit klass+0xb0) -> le pointeur code execute differe du pointeur
// hooke -> AVEUGLE (1 seul noeud capture). La CONSTRUCTION, elle, est faite par des APPELS DIRECTS aux
// methodes `DSLFactory.*` (+ operateurs `op_Addition`/`op_BitwiseAnd`, + drivers `Execute`/`ExecuteAtomic`)
// INLINE dans le corps de `<Ability>.ExecuteBehaviour` -> hookable, synchrone, dans la fenetre.
//
// GENERIQUE : on n'epingle AUCUNE ability. On hooke toute la classe `DSLFactory`, les operateurs des 4
// bases DSL, les 2 drivers, et on GATE sur la fenetre de N'IMPORTE QUEL `<Ability>.ExecuteBehaviour`
// (enum des overrides du namespace Abilities). Chaque cast est tague par la classe reelle lue sur `this`.
//
// RECONSTRUCTION (offline, cote Python) : chaque appel = {seq, method, ret, args}. Regle UNIFORME d'arete
// parent->enfant : un arg est un enfant SSI il egale le `ret` d'un appel anterieur. Cela gere sans cas
// particulier les factories d'INSTANCE (arg0 = factory `this`, jamais un ret -> exclu) ET les operateurs
// STATIQUES (arg0/arg1 = deux noeuds). Le `cache` partage (meme ret consomme par Spawn ET PerformAIAttack)
// reconstruit le DAG memoise en live. Les drivers `ExecuteAtomic`/`Execute` marquent les racines top-level
// dans l'ordre des statements -> Seq(AtomicGroup(root1), root2).
//
// ON-DEMAND (jamais auto-arme) : ~130 hooks factory + operateurs + ~300 gates ExecuteBehaviour. La
// CONSTRUCTION est BEAUCOUP plus froide que l'execution (dsl-trace) -> plus sur. Gate ferme = no-op boolean.

import {
    findClassAnywhere, findMethod, s, class_get_name, class_get_namespace, class_get_parent,
    class_get_methods, method_get_name, method_get_param_count, methodEntry, readMsgClass,
    domain_get, domain_get_assemblies, assembly_get_image, image_get_class_count, image_get_class,
} from "../il2cpp/helpers.js";
import { log } from "../runtime/diag.js";

interface Ctx { rpc: Record<string, (...args: any[]) => unknown>; }

// --- Cibles de construction (factory + operateurs + drivers) ---
interface CtorTarget { name: string; ptr: NativePointer; nargs: number; }
// --- Gate (override ExecuteBehaviour d'une ability) ---
interface GateTarget { ptr: NativePointer; }

const DSL_NS = "IdunBattle.DSL";
const DSL_BASES = ["AbilityBehaviour", "AbilityTrigger", "TargetsSelector", "AAmountFormula"];
const DSL_OPERATORS = ["op_Addition", "op_BitwiseAnd", "op_BitwiseOr", "op_Multiply",
    "op_Subtraction", "op_UnaryNegation"];
// Prefixe de namespace des abilities (GetEmRuntzAbility = IdunBattleLogic.Entities.Abilities.Active.Loki).
const ABILITY_NS_PREFIX = "IdunBattleLogic.Entities.Abilities";
const MAX_ARGS = 7;         // this + params (methodInfo tronque) ; le retval-match filtre le bruit
const MAX_CALLS = 4000;     // garde-fou anti-emballement par arm

let ctorTargets: CtorTarget[] | null = null;   // enumere une fois (cache)
let gateTargets: GateTarget[] | null = null;

const listeners: InvocationListener[] = [];    // tous les hooks (detaches au disarm)

// Etat de capture. La logique de bataille est mono-thread -> une pile de casts suffit.
interface Call { seq: number; m: string; ret: string; args: string[]; }
interface Cast { ability: string; calls: Call[]; }
const castStack: Cast[] = [];        // casts en cours (nesting -> profondeur)
const completed: Cast[] = [];        // casts termines (retour RPC)
let seq = 0;
let totalCalls = 0;
let armed = false;

function fqn(k: NativePointer): string {
    const ns = s(class_get_namespace(k) as NativePointer);
    const cn = s(class_get_name(k) as NativePointer);
    return ns ? ns + "." + cn : cn;
}

/** Enumere les cibles de CONSTRUCTION : toutes les methodes de `DSLFactory`, les operateurs des 4
 * bases DSL, et les 2 drivers `AActiveAbility.Execute`/`ExecuteAtomic`. Resolus par nom (pas de RVA). */
function enumCtorTargets(): CtorTarget[] {
    if (ctorTargets) return ctorTargets;
    const out: CtorTarget[] = [];
    const seen = new Set<string>();
    const push = (name: string, m: { info: NativePointer; ptr: NativePointer } | null) => {
        if (!m || m.ptr.isNull()) return;
        const key = m.ptr.toString();
        if (seen.has(key)) return;
        seen.add(key);
        let pc = 0;
        try { pc = method_get_param_count(m.info) as number; } catch { pc = 0; }
        out.push({ name, ptr: m.ptr, nargs: Math.min(pc + 1, MAX_ARGS) });
    };

    // (1) TOUTE la classe DSLFactory (avec overloads).
    const factory = findClassAnywhere("IdunBattleLogic.Entities", "DSLFactory");
    if (factory === null) log("[dsl-ctor] DSLFactory introuvable");
    else {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(factory, it) as NativePointer).isNull()) {
            const nm = s(method_get_name(m) as NativePointer);
            if (nm === ".ctor" || nm === ".cctor") continue;
            push(nm, { info: m, ptr: methodEntry(m) });
        }
    }

    // (2) Operateurs des 4 bases DSL (combinateurs statiques : op_Addition, op_BitwiseAnd, ...).
    for (const base of DSL_BASES) {
        const k = findClassAnywhere(DSL_NS, base);
        if (k === null) continue;
        for (const op of DSL_OPERATORS) {
            const mm = findMethod(k, op);
            if (mm) push(base + "." + op, mm);
        }
    }

    // (3) Drivers d'execution top-level : marquent les racines des statements.
    const active = findClassAnywhere("IdunBattle.Entities.Abilities", "AActiveAbility");
    if (active !== null) {
        for (const drv of ["Execute", "ExecuteAtomic"]) {
            const mm = findMethod(active, drv);
            if (mm) push("AActiveAbility." + drv, mm);
        }
    }

    ctorTargets = out;
    log("[dsl-ctor] enumere " + out.length + " cibles de construction (factory+op+drivers)");
    return out;
}

/** Enumere les gates : l'override `ExecuteBehaviour` de chaque ability (namespace Abilities.*). */
function enumGates(): GateTarget[] {
    if (gateTargets) return gateTargets;
    const out: GateTarget[] = [];
    const seen = new Set<string>();
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
            const ns = s(class_get_namespace(k) as NativePointer);
            if (!ns.startsWith(ABILITY_NS_PREFIX)) continue;
            const m = findMethod(k, "ExecuteBehaviour");
            if (!m || m.ptr.isNull()) continue;
            const key = m.ptr.toString();
            if (seen.has(key)) continue;   // override partage (rare) — un seul hook
            seen.add(key);
            out.push({ ptr: m.ptr });
        }
    }
    gateTargets = out;
    log("[dsl-ctor] enumere " + out.length + " gates ExecuteBehaviour (abilities)");
    return out;
}

function ctorOnEnter(this: InvocationContext, args: InvocationArguments, nargs: number): void {
    if (castStack.length === 0) { (this as any)._cap = false; return; }
    (this as any)._cap = true;
    const a: string[] = [];
    for (let i = 0; i < nargs; i++) a.push(args[i].toString());
    (this as any)._a = a;
}
function ctorOnLeave(this: InvocationContext, retval: InvocationReturnValue, name: string): void {
    if (!(this as any)._cap) return;
    const cast = castStack[castStack.length - 1];
    if (!cast || totalCalls >= MAX_CALLS) return;
    cast.calls.push({ seq: seq++, m: name, ret: retval.toString(), args: (this as any)._a });
    totalCalls++;
}

function gateOnEnter(this: InvocationContext, args: InvocationArguments): void {
    let ability = "?";
    try { ability = readMsgClass(args[0]); } catch { /* */ }
    castStack.push({ ability, calls: [] });
}
function gateOnLeave(): void {
    const c = castStack.pop();
    if (c) completed.push(c);
}

/** Arme : hooke les cibles de construction (gated) + les gates ExecuteBehaviour (ouvrent/ferment). */
function arm(): unknown {
    if (armed) return { ok: false, error: "deja arme — disarm d'abord", hooks: listeners.length };
    const ct = enumCtorTargets();
    const gt = enumGates();
    castStack.length = 0;
    completed.length = 0;
    seq = 0;
    totalCalls = 0;

    for (const t of ct) {
        const name = t.name, nargs = t.nargs;
        try {
            listeners.push(Interceptor.attach(t.ptr, {
                onEnter(this: InvocationContext, args: InvocationArguments) { ctorOnEnter.call(this, args, nargs); },
                onLeave(this: InvocationContext, retval: InvocationReturnValue) { ctorOnLeave.call(this, retval, name); },
            }));
        } catch { /* body absent/gshared — skip */ }
    }
    for (const g of gt) {
        try {
            listeners.push(Interceptor.attach(g.ptr, {
                onEnter(this: InvocationContext, args: InvocationArguments) { gateOnEnter.call(this, args); },
                onLeave() { gateOnLeave(); },
            }));
        } catch { /* skip */ }
    }
    armed = true;
    return { ok: true, ctorHooks: ct.length, gateHooks: gt.length, totalHooks: listeners.length };
}

function disarm(): unknown {
    for (const l of listeners) { try { l.detach(); } catch { /* */ } }
    listeners.length = 0;
    castStack.length = 0;
    armed = false;
    return { ok: true, disarmed: true };
}

/** Renvoie les casts captures (chacun = {ability, calls:[{seq,m,ret,args}]}) pour reconstruction offline. */
function casts(): unknown {
    return { ok: true, armed, capturedCasts: completed.length, casts: completed };
}

export function register(ctx: Ctx): void {
    ctx.rpc.dslCtorArm = () => arm();
    ctx.rpc.dslCtorCasts = () => casts();
    ctx.rpc.dslCtorDisarm = () => disarm();
}
