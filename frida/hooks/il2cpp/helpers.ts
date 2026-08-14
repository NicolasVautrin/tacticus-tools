// IL2CPP low-level helpers — class/method/field resolution, string reader,
// stack trace, `hook()` convenience wrapper. All wrappers cached.

import { log, traceEnter } from "../runtime/diag.js";

// Windows IL2CPP build of Unity — module is GameAssembly.dll, exported
// alongside Tacticus.exe in `Tacticus_Data\..` per the standard layout.
export const IL2CPP_MODULE_NAME = "GameAssembly.dll";

const il2cpp = Process.findModuleByName(IL2CPP_MODULE_NAME);
if (il2cpp === null) {
    throw new Error(`${IL2CPP_MODULE_NAME} not loaded`);
}
export const il2cppBase = il2cpp.base;
export const il2cppSize = il2cpp.size;

function exp(name: string): NativePointer {
    const p = il2cpp!.findExportByName(name);
    if (p === null) {
        throw new Error(`${IL2CPP_MODULE_NAME} export not found: ${name}`);
    }
    return p;
}

// --- IL2CPP C API wrappers ---
export const domain_get = new NativeFunction(
    exp("il2cpp_domain_get"), "pointer", []);
export const domain_get_assemblies = new NativeFunction(
    exp("il2cpp_domain_get_assemblies"), "pointer", ["pointer", "pointer"]);
export const assembly_get_image = new NativeFunction(
    exp("il2cpp_assembly_get_image"), "pointer", ["pointer"]);
export const image_get_class_count = new NativeFunction(
    exp("il2cpp_image_get_class_count"), "uint32", ["pointer"]);
export const image_get_class = new NativeFunction(
    exp("il2cpp_image_get_class"), "pointer", ["pointer", "uint32"]);
export const class_get_name = new NativeFunction(
    exp("il2cpp_class_get_name"), "pointer", ["pointer"]);
export const class_get_namespace = new NativeFunction(
    exp("il2cpp_class_get_namespace"), "pointer", ["pointer"]);
const image_get_name = new NativeFunction(
    exp("il2cpp_image_get_name"), "pointer", ["pointer"]);
export const class_get_methods = new NativeFunction(
    exp("il2cpp_class_get_methods"), "pointer", ["pointer", "pointer"]);
export const method_get_name = new NativeFunction(
    exp("il2cpp_method_get_name"), "pointer", ["pointer"]);
export const class_get_fields = new NativeFunction(
    exp("il2cpp_class_get_fields"), "pointer", ["pointer", "pointer"]);
export const class_get_parent = new NativeFunction(
    exp("il2cpp_class_get_parent"), "pointer", ["pointer"]);
export const field_get_name = new NativeFunction(
    exp("il2cpp_field_get_name"), "pointer", ["pointer"]);
export const field_get_offset = new NativeFunction(
    exp("il2cpp_field_get_offset"), "int32", ["pointer"]);
export const field_get_type = new NativeFunction(
    exp("il2cpp_field_get_type"), "pointer", ["pointer"]);
export const type_get_class_or_element_class = new NativeFunction(
    exp("il2cpp_type_get_class_or_element_class"), "pointer", ["pointer"]);
export const class_get_nested_types = new NativeFunction(
    exp("il2cpp_class_get_nested_types"), "pointer", ["pointer", "pointer"]);
export const method_get_param_count = new NativeFunction(
    exp("il2cpp_method_get_param_count"), "uint32", ["pointer"]);
export const method_get_param = new NativeFunction(
    exp("il2cpp_method_get_param"), "pointer", ["pointer", "uint32"]);
const class_get_type = new NativeFunction(
    exp("il2cpp_class_get_type"), "pointer", ["pointer"]);
const type_get_object = new NativeFunction(
    exp("il2cpp_type_get_object"), "pointer", ["pointer"]);

/** `il2cpp_method_get_return_type(MethodInfo*)` → `Il2CppType*` du RETOUR.
 *
 *  C'est la voie qui donne une INSTANCE INFLATÉE d'un générique sans en connaître de
 *  sous-classe : `image_get_class` n'énumère que les DÉFINITIONS ouvertes (`Bucket\`1`),
 *  dont le `methodPointer` est un thunk d'invocation — pas le corps partagé (#259 §3).
 *  Combiné à `type_get_class_or_element_class`, il rend l'`Il2CppClass*` de l'instance
 *  fermée (`Bucket<UnitAction>`), qui porte bien le corps gshared (#259-b).
 *
 *  Résolu de façon TOLÉRANTE (null si l'export manque) : il ne sert qu'à des résolutions
 *  de hook, et un export absent ne doit pas empêcher le script de se charger. */
export const method_get_return_type = (() => {
    const p = il2cpp!.findExportByName("il2cpp_method_get_return_type");
    return p ? new NativeFunction(p, "pointer", ["pointer"]) : null;
})();

/** `il2cpp_class_instance_size(Il2CppClass*)` — taille BOXÉE de la classe, en octets
 *  (pour un `System.ValueType` : header IL2CPP 0x10 + taille des champs). C'est la
 *  colonne `size` de `data/symbols/<build>/frida/classes.tsv`, donc la MÊME grandeur
 *  qu'on peut confronter offline.
 *
 *  Résolu de façon TOLÉRANTE (null si l'export manque) : il ne sert qu'aux gardes de
 *  layout, et un export absent ne doit pas empêcher le script de se charger. */
export const class_instance_size = (() => {
    const p = il2cpp!.findExportByName("il2cpp_class_instance_size");
    return p ? new NativeFunction(p, "int32", ["pointer"]) : null;
})();

/** `il2cpp_class_get_declaring_type(Il2CppClass*)` — la classe ENGLOBANTE d'une classe nested,
 *  `NULL` pour une classe top-level.
 *
 *  À quoi ça sert, concrètement : NOMMER une state machine d'itérateur. `class_get_name` d'un
 *  `<Method>d__N` rend le nom COURT, qui **collisionne massivement** — mesuré sur `rnca9r7q6c` :
 *  39 classes portent un `<EvaluateMovementInSteps>d__N`, dont plusieurs le même `d__2`. Publier
 *  ce nom court seul rend un label AMBIGU, et le chercher par `findClassAnywhere` rendrait la
 *  PREMIÈRE classe trouvée — potentiellement la mauvaise, sans la moindre erreur. Le déclarant
 *  lève l'ambiguïté (`SaviorProtocolsPlaybook.<CalculateMovementUtilityInStepsInternal>d__4`).
 *
 *  Résolu de façon TOLÉRANTE (null si l'export manque) : à l'appelant de décider ce qu'il publie
 *  quand il ne sait pas — un nom court étiqueté comme tel, jamais un nom qualifié inventé. */
export const class_get_declaring_type = (() => {
    const p = il2cpp!.findExportByName("il2cpp_class_get_declaring_type");
    return p ? new NativeFunction(p, "pointer", ["pointer"]) : null;
})();

/** `il2cpp_class_is_valuetype(Il2CppClass*)` — non nul pour un `System.ValueType`.
 *
 *  Deux conséquences, et les deux comptent pour un décodeur de struct (#279) :
 *  ses champs sont INLINE dans le conteneur (pas déréférencés), et
 *  `il2cpp_field_get_offset` rend pour lui un offset **BOXÉ** — header IL2CPP de
 *  `0x10` inclus. Composer une chaîne de champs sans retrancher ce header décale
 *  de 16 octets par maillon.
 *
 *  Résolu de façon TOLÉRANTE (null si l'export manque) : c'est à l'appelant de
 *  décider si « je ne sais pas » l'autorise à lire. */
export const class_is_valuetype = (() => {
    const p = il2cpp!.findExportByName("il2cpp_class_is_valuetype");
    return p ? new NativeFunction(p, "int32", ["pointer"]) : null;
})();

/** `il2cpp_runtime_class_init(Il2CppClass*)` — ce que le jeu appelle LUI-MÊME au premier accès
 *  (tout corps décompilé porte le motif
 *  `if (*(int *)(DAT_xxx + 0xe4) == 0) il2cpp_runtime_class_init();`).
 *
 *  À quoi ça sert, concrètement : IL2CPP ne remplit ni le bloc de statiques ni la VTABLE d'une
 *  classe tant qu'elle n'a pas été INITIALISÉE. Lire l'un ou l'autre à froid rend des ZÉROS — et
 *  un zéro est une valeur du domaine, donc la panne est indiscernable de la mesure. C'est
 *  exactement le trou mesuré par #982-r6 : `probe_916r1_effect_slots.py` ne mesure que 244 des
 *  465 classes d'effet, les 221 autres n'ayant jamais été instanciées dans la session.
 *
 *  ⚠ C'est le SEUL wrapper de ce fichier qui ait un EFFET. Il ne doit jamais être appelé
 *  implicitement : les appelants (`features/introspect.ts::resolveVtableSlot`,
 *  `probes/static-field-probe.ts`) le mettent sous un drapeau explicite `forceInit`, et
 *  PUBLIENT `initializedBefore` pour que le lecteur sache s'il tient une mesure ou un forçage.
 *  Le foyer de cette discipline est `il2cpp/class-init.ts`, pas ici.
 *
 *  Résolu de façon TOLÉRANTE (null si l'export manque) : à l'appelant de dire « je n'ai pas pu
 *  forcer », jamais de prétendre l'avoir fait. */
export const runtime_class_init = (() => {
    const p = il2cpp!.findExportByName("il2cpp_runtime_class_init");
    return p ? new NativeFunction(p, "void", ["pointer"]) : null;
})();

/** `il2cpp_class_get_element_class(Il2CppClass*)` — pour un `T[]`, la classe de `T`.
 *
 *  À quoi ça sert, concrètement : décider le STRIDE d'un tableau managé sans le
 *  supposer. `System.Collections.Generic.List<T>$$get_Item` lit l'élément à
 *  `items + 0x20 + element_size * i`, où `element_size` vient du `Il2CppClass` du
 *  tableau — donc `8` pour une référence, mais la TAILLE DE LA STRUCT pour un type
 *  valeur. Un décodeur qui écrit `8` en dur rend du garbage plausible sur le second
 *  cas. Croisé avec `class_is_valuetype`, cet accesseur permet de RÉPONDRE « je ne
 *  sais pas lire » au lieu de rendre des nombres faux.
 *
 *  Résolu de façon TOLÉRANTE (null si l'export manque), comme ses deux voisins. */
export const class_get_element_class = (() => {
    const p = il2cpp!.findExportByName("il2cpp_class_get_element_class");
    return p ? new NativeFunction(p, "pointer", ["pointer"]) : null;
})();

// Use the stable public API to get the method code pointer. The first field
// of MethodInfo varies across IL2CPP versions (some have invoker_method first,
// methodPointer second) so readPointer() is unsafe.
const _method_get_pointer = (() => {
    const p = il2cpp!.findExportByName("il2cpp_method_get_pointer");
    return p ? new NativeFunction(p, "pointer", ["pointer"]) : null;
})();

export function methodEntry(methodInfo: NativePointer): NativePointer {
    if (_method_get_pointer) {
        return _method_get_pointer(methodInfo) as NativePointer;
    }
    return methodInfo.readPointer();
}

/** The invoker_method stub. In IL2CPP, `il2cpp_runtime_invoke` dispatches
 * through `methodInfo->invoker_method(methodPointer, methodInfo, obj, params)`
 * — this stub unpacks args and calls the real method. */
export function methodInvoker(methodInfo: NativePointer): NativePointer {
    return methodInfo.add(8).readPointer();
}

// RETIRE (#480-r7) : `resolveThunk(entry)` rendait `entry` INCHANGE. Le decodeur de
// thunks decrit dans sa docstring visait ARM64 ; sur la cible x86-64 il n'a jamais
// existe, donc la fonction etait l'IDENTITE sous un nom qui promet une resolution.
// Aucun appelant, dans aucune des trois langues du depot. Un futur besoin de chasser
// un `JMP rel32` (`E9 xx xx xx xx`) s'ecrira comme un decodeur qui MESURE, pas comme
// une identite qu'on croit avoir appelee.

/** Get the managed System.Type object for an IL2CPP class. */
export function getSystemType(klass: NativePointer): NativePointer {
    const t = class_get_type(klass) as NativePointer;
    return type_get_object(t) as NativePointer;
}

// --- String helpers ---

/** Read a native UTF-8 C string from an IL2CPP export pointer, empty on failure. */
export function cstr(p: NativePointer): string {
    try { return p.readUtf8String() || ""; }
    catch { return ""; }
}
/** Legacy alias. New code should import `cstr`. */
export const s = cstr;

/** Read a managed System.String from an IL2CPP object. Null on failure. */
export function readIl2cppString(objPtr: NativePointer): string | null {
    if (objPtr.isNull()) return null;
    try {
        const len = objPtr.add(0x10).readS32();
        if (len <= 0 || len > 500) return null;
        return objPtr.add(0x14).readUtf16String(len);
    } catch { return null; }
}

// --- Stack trace (raw offsets) ---

/** Returns up to 15 backtrace offsets inside the IL2CPP module. Backend resolves to symbols. */
export function getStack(ctx: CpuContext): number[] {
    const bt = Thread.backtrace(ctx, Backtracer.ACCURATE);
    const frames: number[] = [];
    for (let i = 0; i < Math.min(bt.length, 15); i++) {
        const off = bt[i].sub(il2cppBase);
        if (off.compare(0) >= 0 && off.compare(il2cppSize) < 0) {
            frames.push(off.toInt32());
        }
    }
    return frames;
}

// --- Class / method resolution (cached) ---

export interface MethodRef {
    info: NativePointer;  // MethodInfo* (for il2cpp_runtime_invoke)
    ptr: NativePointer;   // entry address (for Interceptor.attach)
}

const classCache: Record<string, NativePointer> = {};
/** Scan every loaded assembly for a class matching (ns, cls). Use when the
 * owning assembly isn't known — slower than findClass but resolves anywhere. */
export function findClassAnywhere(ns: string, cls: string): NativePointer | null {
    const key = `*::${ns}.${cls}`;
    if (classCache[key]) return classCache[key];
    const domain = domain_get() as NativePointer;
    const sizePtr = Memory.alloc(4);
    const assemblies = domain_get_assemblies(domain, sizePtr) as NativePointer;
    const count = sizePtr.readU32();
    for (let i = 0; i < count; i++) {
        const assembly = assemblies.add(i * Process.pointerSize).readPointer();
        const image = assembly_get_image(assembly) as NativePointer;
        const cc = image_get_class_count(image) as number;
        for (let j = 0; j < cc; j++) {
            const k = image_get_class(image, j) as NativePointer;
            if (s(class_get_name(k) as NativePointer) === cls &&
                s(class_get_namespace(k) as NativePointer) === ns) {
                classCache[key] = k;
                return k;
            }
        }
    }
    return null;
}

export function findClass(asm: string, ns: string, cls: string): NativePointer | null {
    const key = `${asm}::${ns}.${cls}`;
    if (classCache[key]) return classCache[key];
    const domain = domain_get() as NativePointer;
    const sizePtr = Memory.alloc(4);
    const assemblies = domain_get_assemblies(domain, sizePtr) as NativePointer;
    const count = sizePtr.readU32();
    for (let i = 0; i < count; i++) {
        const assembly = assemblies.add(i * Process.pointerSize).readPointer();
        const image = assembly_get_image(assembly) as NativePointer;
        if (s(image_get_name(image) as NativePointer) !== asm) continue;
        const cc = image_get_class_count(image) as number;
        for (let j = 0; j < cc; j++) {
            const k = image_get_class(image, j) as NativePointer;
            if (s(class_get_name(k) as NativePointer) === cls &&
                s(class_get_namespace(k) as NativePointer) === ns) {
                classCache[key] = k;
                return k;
            }
        }
    }
    return null;
}

export function findMethod(klass: NativePointer, name: string): MethodRef | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        if (s(method_get_name(m) as NativePointer) === name) {
            return { info: m, ptr: methodEntry(m) };
        }
    }
    return null;
}

/** Find a ctor by exact parameter count — findMethod(".ctor") picks the first
 * which may be the wrong overload. Use this for classes with multiple ctors. */
export function findCtorByParamCount(
    klass: NativePointer, paramCount: number): MethodRef | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        if (s(method_get_name(m) as NativePointer) !== ".ctor") continue;
        try {
            if ((method_get_param_count(m) as number) === paramCount) {
                return { info: m, ptr: methodEntry(m) };
            }
        } catch { /* skip */ }
    }
    return null;
}

/** Nom de la classe (ou élément) du param `index` d'une méthode — sert à
 * désambiguïser des overloads de MÊME arité (que findMethodByParamCount ne sait
 * pas distinguer). ex. GetValidTargets a deux overloads 3-param : param[1] =
 * "UnitPosition" vs "IOrderedSet`1". null si indéterminable. */
export function methodParamClassName(
    m: NativePointer, index: number,
): string | null {
    const cls = methodParamClass(m, index);
    if (cls === null) return null;
    try { return s(class_get_name(cls) as NativePointer); } catch { return null; }
}

/** La CLASSE du param `index` (et non son seul nom). Une classe porte ce qu'un nom ne
 *  donne pas — offsets de champs par nom, taille d'instance — donc c'est elle qu'il faut
 *  quand on doit CONSTRUIRE la valeur d'un paramètre ValueType (ex. le
 *  `Nullable<AbilityOrEffect>` que prend `UtilityAttackCase$$Base`) au lieu de simplement
 *  désambiguïser un overload. `null` si indéterminable. */
export function methodParamClass(
    m: NativePointer, index: number,
): NativePointer | null {
    try {
        const ty = method_get_param(m, index) as NativePointer;
        if (ty.isNull()) return null;
        const cls = type_get_class_or_element_class(ty) as NativePointer;
        return cls.isNull() ? null : cls;
    } catch { return null; }
}

/** Find an overload by name + param CLASS NAMES (par position ; `null` = joker).
 * Désambiguïse là où findMethodByParamCount échoue (overloads de même arité).
 * Walk la chaîne d'héritage. ex. :
 *   findMethodByParamClasses(k, "GetValidTargets", [null, "UnitPosition", null]) */
export function findMethodByParamClasses(
    klass: NativePointer, name: string, classNames: Array<string | null>,
): MethodRef | null {
    let k = klass;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
            if (s(method_get_name(m) as NativePointer) !== name) continue;
            try {
                if ((method_get_param_count(m) as number) !== classNames.length) continue;
            } catch { continue; }
            let ok = true;
            for (let i = 0; i < classNames.length; i++) {
                const want = classNames[i];
                if (want === null) continue;
                if (methodParamClassName(m, i) !== want) { ok = false; break; }
            }
            if (ok) return { info: m, ptr: methodEntry(m) };
        }
        k = class_get_parent(k) as NativePointer;
    }
    return null;
}

/** Find a method overload by exact name + parameter count. Walks the
 * inheritance chain. Useful when multiple overloads of the same method
 * exist (e.g., GetStats has 5 overloads on UnitProgression). */
export function findMethodByParamCount(
    klass: NativePointer, name: string, paramCount: number,
): MethodRef | null {
    let k = klass;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
            if (s(method_get_name(m) as NativePointer) !== name) continue;
            try {
                if ((method_get_param_count(m) as number) === paramCount) {
                    return { info: m, ptr: methodEntry(m) };
                }
            } catch { /* skip */ }
        }
        k = class_get_parent(k) as NativePointer;
    }
    return null;
}

/** Find a method by BASE name (+ exact param count), matching either the plain
 *  name OR an explicit-interface-qualified name `Namespace.IFace<T>.<base>` — whose
 *  il2cpp `method_get_name` is the fully-qualified string that findMethod's exact
 *  match misses. ex. le `System.Collections.Generic.IEnumerable<ProbableDamageEvent>
 *  .GetEnumerator` d'une machine d'état yield `<M>d__N`. Walk la chaîne d'héritage. */
export function findMethodByNameSuffix(
    klass: NativePointer, base: string, paramCount: number,
): MethodRef | null {
    const dotted = "." + base;
    let k = klass;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
            const nm = s(method_get_name(m) as NativePointer);
            if (nm !== base && !nm.endsWith(dotted)) continue;
            try {
                if ((method_get_param_count(m) as number) === paramCount) {
                    return { info: m, ptr: methodEntry(m) };
                }
            } catch { /* skip */ }
        }
        k = class_get_parent(k) as NativePointer;
    }
    return null;
}

// --- Field offset resolution (cached, walks inheritance chain) ---

const fieldOffsetCache: Record<string, number> = {};
export function getFieldOffset(klass: NativePointer, fieldName: string): number {
    const key = klass.toString() + "." + fieldName;
    if (fieldOffsetCache[key] !== undefined) return fieldOffsetCache[key];
    let k = klass;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(k, it) as NativePointer).isNull()) {
            if (s(field_get_name(f) as NativePointer) === fieldName) {
                const off = field_get_offset(f) as number;
                fieldOffsetCache[key] = off;
                return off;
            }
        }
        k = class_get_parent(k) as NativePointer;
    }
    fieldOffsetCache[key] = -1;
    return -1;
}

/**
 * `getFieldOffset` avec repli DÉCOMPILÉ — la seule façon correcte d'écrire
 * « offset par nom, sinon la constante lue au décompilé ».
 *
 * **Le piège que ce helper existe pour fermer** : `getFieldOffset` rend **`-1`** sur un nom
 * ABSENT (cf. juste au-dessus), et l'idiome spontané `getFieldOffset(k, "X") || 0xec` ne teste
 * que `0` — or **`-1` est *truthy* en JavaScript**. Le repli n'est donc JAMAIS pris, l'offset
 * vaut `-1`, et le hook lit `comp - 1` : du garbage, **sans la moindre erreur**. Deux champs
 * résolus ainsi lisent la MÊME adresse et rendent donc la MÊME valeur — c'est la signature.
 *
 * MESURÉ le 2026-07-31 (`probe_340_r1_actorstats_live.py`, résidu `#340-r1`) : dans le RPC
 * `actorStats`, `TilesMovedThisBattle` (`+0xec`) et `TilesMovedLastTurn` (`+0xf4`) rendaient tous
 * deux **-1201836032**, la même valeur constante, pendant que `TilesMovedThisTurn` (`+0xf0`) —
 * dont le nom, lui, existe — était exact sur les deux transitions du composant. Les trois offsets
 * étaient pourtant justes au décompilé : ce n'était pas une erreur de RE, mais le repli qui ne
 * se déclenchait pas.
 *
 * Un nom de champ IL2CPP n'est pas vérifiable offline (aucun `fields.tsv` dans `data/symbols/`),
 * donc l'absence d'un nom est un cas NORMAL, pas un incident — d'où le repli. Ce qui n'est pas
 * normal, c'est de lire du garbage en croyant se replier.
 */
export function fieldOffsetOr(
    klass: NativePointer, fieldName: string, fallback: number,
): number {
    const off = getFieldOffset(klass, fieldName);
    return off >= 0 ? off : fallback;
}

/** Returns FieldInfo* for `fieldName` walking the inheritance chain, or null. */
export function getFieldInfo(
    klass: NativePointer, fieldName: string,
): NativePointer | null {
    let k = klass;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(k, it) as NativePointer).isNull()) {
            if (s(field_get_name(f) as NativePointer) === fieldName) {
                return f;
            }
        }
        k = class_get_parent(k) as NativePointer;
    }
    return null;
}

// --- Hook convenience wrapper ---

export function hook(
    asm: string, ns: string, cls: string, mth: string,
    cb: InvocationListenerCallbacks,
): void {
    const k = findClass(asm, ns, cls);
    if (!k) { log("[-] " + cls + " not found"); return; }
    const m = findMethod(k, mth);
    if (!m || m.ptr.isNull()) { log("[-] " + cls + "." + mth + " not found"); return; }
    try {
        // Wrap the user callback with traceEnter so every invocation is
        // logged with a sequence number — the last trace entry before a
        // crash points at the culprit hook. We only wrap callback-style
        // hooks (object form); raw probe callbacks pass through untouched.
        const traceName = cls + "." + mth;
        const cbAny = cb as { onEnter?: Function; onLeave?: Function };
        const userOnEnter = cbAny.onEnter;
        const wrapped = {
            ...(cb as object),
            onEnter(this: InvocationContext, args: InvocationArguments) {
                traceEnter(traceName);
                if (typeof userOnEnter === "function") {
                    userOnEnter.call(this, args);
                }
            },
        } as unknown as InvocationListenerCallbacks;
        Interceptor.attach(m.ptr, wrapped);
        log("[+] " + cls + "." + mth);
    } catch (e) {
        log("[!] " + cls + "." + mth + " — cannot hook: " + (e as Error).message);
    }
}

// --- Message introspection ---

/** Read the IL2CPP class name of a managed object. */
export function readMsgClass(msgPtr: NativePointer): string {
    try { return s(class_get_name(msgPtr.readPointer()) as NativePointer); }
    catch { return "?"; }
}

/** Read both namespace + class name — enough to round-trip a class through
 * findClassAnywhere(ns, cls) at load time. Returns empty strings on failure. */
export function readMsgIdentity(msgPtr: NativePointer): {
    ns: string; cls: string;
} {
    try {
        const klass = msgPtr.readPointer();
        return {
            ns: s(class_get_namespace(klass) as NativePointer),
            cls: s(class_get_name(klass) as NativePointer),
        };
    } catch {
        return { ns: "", cls: "?" };
    }
}
