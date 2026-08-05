/** Sonde de la couche DSL : `dslNodeProbe` (famille `AbilityBehaviour`) + `dslLazyProbe`
 *  (familles `AbilityTrigger` / sélecteurs / formules de valeur).
 *
 *  ⚠ PROVENANCE — CE FICHIER A ÉTÉ RECONSTRUIT LE 2026-07-31, PAS RESTAURÉ.
 *  Le fichier source d'origine a été détruit (cf. `probe_365_versioned_imports_gitignored.py`
 *  et l'invariant « jamais de junction » du CLAUDE.md) et n'existait dans aucune sauvegarde.
 *  Le corps ci-dessous est extrait du bundle `frida/dist/hooks.js` compilé AVANT la perte
 *  (délimité par le marqueur `// hooks/probes/dsl-node-probe.ts`, 198 lignes) : `frida-compile`
 *  retire les types mais préserve la structure, donc la logique est celle d'origine, à
 *  l'identique. Trois différences, toutes MÉCANIQUES et vérifiables :
 *    1. les helpers locaux `rva2`/`fqn2`/`hasAncestor2` retrouvent leur nom (`rva`/`fqn`/
 *       `hasAncestor`) — le suffixe numérique venait du bundler, qui désambiguïse les
 *       homonymes entre modules ;
 *    2. les appels `init_node_globals()` / `init_helpers()` sont supprimés — ce sont des
 *       amorces d'esbuild, pas du code source ; ils correspondent à l'import ci-dessous ;
 *    3. les annotations de type sont RÉÉCRITES (elles ne survivent pas à la compilation).
 *  Ce qui n'a PAS pu être reconstruit : les commentaires d'origine.
 */
import {
    IL2CPP_MODULE_NAME, il2cppBase, s,
    class_get_name, class_get_namespace, class_get_parent, class_get_methods, method_get_name,
    domain_get, domain_get_assemblies, assembly_get_image, image_get_class_count, image_get_class,
    findClassAnywhere, findMethod, methodInvoker,
} from "../il2cpp/helpers.js";

const lib = Process.findModuleByName(IL2CPP_MODULE_NAME)!;
const class_get_interfaces = new NativeFunction(
    lib.findExportByName("il2cpp_class_get_interfaces")!, "pointer", ["pointer", "pointer"]);

function rva(p: NativePointer): string {
    return p.isNull() ? "null" : "0x" + p.sub(il2cppBase).toString(16);
}

function fqn(k: NativePointer): string {
    const ns = s(class_get_namespace(k) as NativePointer);
    const cn = s(class_get_name(k) as NativePointer);
    return ns ? ns + "." + cn : cn;
}

function parentChain(k: NativePointer): string[] {
    const out: string[] = [];
    let p = class_get_parent(k) as NativePointer;
    let guard = 0;
    while (!p.isNull() && guard++ < 12) {
        out.push(fqn(p));
        p = class_get_parent(p) as NativePointer;
    }
    return out;
}

function interfaces(k: NativePointer): string[] {
    const out: string[] = [];
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let ifc: NativePointer;
    let guard = 0;
    while (!(ifc = class_get_interfaces(k, it) as NativePointer).isNull() && guard++ < 40) {
        out.push(fqn(ifc));
    }
    return out;
}

function hasAncestor(k: NativePointer, target: NativePointer): boolean {
    let p = class_get_parent(k) as NativePointer;
    let guard = 0;
    while (!p.isNull() && guard++ < 12) {
        if (p.equals(target)) return true;
        p = class_get_parent(p) as NativePointer;
    }
    return false;
}

/** Énumère la famille `IdunBattle.DSL.AbilityBehaviour` et compte ses invokers DISTINCTS.
 *  `distinctInvokers === 1` veut dire invoker PARTAGÉ, donc un hook unique est viable. */
export function dslNodeProbe(): Record<string, unknown> {
    const base = findClassAnywhere("IdunBattle.DSL", "AbilityBehaviour");
    if (base === null) return { ok: false, error: "AbilityBehaviour introuvable" };

    const family: Array<Record<string, unknown>> = [];
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
            if (!hasAncestor(k, base)) continue;
            const m = findMethod(k, "Execute");
            family.push({
                cls: fqn(k),
                execEntry: m ? rva(m.ptr) : "NO-Execute(herite?)",
                execInvoker: m ? rva(methodInvoker(m.info)) : "-",
            });
        }
    }

    const invokers = new Set(family
        .filter((f) => typeof f.execInvoker === "string" && f.execInvoker !== "-")
        .map((f) => f.execInvoker as string));

    const sample: Array<Record<string, unknown>> = [];
    for (const [ns, cls] of [
        ["IdunBattle.DSL", "CombinedBehaviour"],
        ["IdunBattle.Entities.Behaviours", "ForeachBehaviour"],
        ["IdunBattle.Entities.Behaviours", "SpawnUnitBehaviour"],
    ] as Array<[string, string]>) {
        const k = findClassAnywhere(ns, cls);
        if (k === null) {
            sample.push({ cls: ns + "." + cls, found: false });
            continue;
        }
        const m = findMethod(k, "Execute");
        sample.push({
            cls: ns + "." + cls,
            parents: parentChain(k),
            interfaces: interfaces(k),
            execEntry: m ? rva(m.ptr) : "null",
            execInvoker: m ? rva(methodInvoker(m.info)) : "null",
        });
    }

    return {
        ok: true,
        baseAbilityBehaviour: rva(base),   // sanity : la base resout
        familyCount: family.length,        // nb de noeuds (sous-classes)
        distinctInvokers: invokers.size,   // 1 => invoker PARTAGE => hook unique viable
        invokers: [...invokers].slice(0, 8),
        family: family.slice(0, 80),       // liste des noeuds (borne)
        sample,                            // parents + interfaces des noeuds temoins
    };
}

function methodNames(k: NativePointer): string[] {
    const out: string[] = [];
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    let g = 0;
    while (!(m = class_get_methods(k, it) as NativePointer).isNull() && g++ < 60) {
        out.push(s(method_get_name(m) as NativePointer));
    }
    return out;
}

function findByName(cls: string): NativePointer | null {
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
            if (s(class_get_name(k) as NativePointer) === cls) return k;
        }
    }
    return null;
}

function enumFamily(base: NativePointer, evalName: string): Record<string, unknown> {
    const members: Array<{ cls: string; entry: string }> = [];
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
            if (!hasAncestor(k, base)) continue;
            const m = findMethod(k, evalName);
            members.push({ cls: fqn(k), entry: m ? rva(m.ptr) : "NO-" + evalName });
        }
    }
    const concrete = members.filter((m) => !m.entry.startsWith("NO-"));
    return {
        base: fqn(base),
        evalName,
        total: members.length,
        concrete: concrete.length,
        sample: members.slice(0, 30),
    };
}

/** Remonte jusqu'a la derniere classe AVANT `System.Object` (la racine de la famille). */
function topBase(k: NativePointer): NativePointer | null {
    let p: NativePointer = k;
    let prev: NativePointer | null = null;
    let g = 0;
    while (!p.isNull() && g++ < 12) {
        const par = class_get_parent(p) as NativePointer;
        if (par.isNull() || fqn(par) === "System.Object") return p;
        prev = p;
        p = par;
    }
    return prev;
}

/** Familles TRIGGER / SELECTEUR / VALEUR, chacune enumeree depuis un TEMOIN dont on remonte
 *  la racine — les bases DSL n'etant pas toutes resolvables par nom. */
export function dslLazyProbe(): Record<string, unknown> {
    const out: Record<string, unknown> = { ok: true };

    const trig = findClassAnywhere("IdunBattle.DSL", "AbilityTrigger");
    out.triggerMethods = trig ? methodNames(trig) : [];
    out.trigger = trig ? enumFamily(trig, "ShouldTrigger")
        : { error: "AbilityTrigger introuvable" };

    const selW = findByName("AllAliveMachinesSelector");
    if (selW !== null) {
        out.selectorWitness = { fqn: fqn(selW), parents: parentChain(selW), methods: methodNames(selW) };
        const selBase = topBase(selW);
        if (selBase !== null) out.selector = enumFamily(selBase, "Select");
    } else {
        out.selectorWitness = { error: "AllAliveMachinesSelector introuvable" };
    }

    const valW = findByName("StatAmountFormula")
        || findByName("ConfigAmount")
        || findByName("TurnsFromRoundsFormula");
    if (valW !== null) {
        out.valueWitness = { fqn: fqn(valW), parents: parentChain(valW), methods: methodNames(valW) };
        const valBase = topBase(valW);
        if (valBase !== null) out.value = enumFamily(valBase, "Calculate");
    } else {
        out.valueWitness = {
            error: "aucun temoin valeur (StatAmountFormula/ConfigAmount/TurnsFromRoundsFormula)",
        };
    }

    return out;
}
