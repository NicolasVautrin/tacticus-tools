// IL2CPP object creation & managed method invocation.
// Exceptions thrown from managed code are re-thrown as JS Error with
// the managed Message + StackTrace included (resolved lazily).

import {
    class_get_name, class_get_fields, field_get_name, field_get_offset,
    findClass, findClassAnywhere, findMethod, method_get_name,
    IL2CPP_MODULE_NAME, MethodRef, s,
} from "./helpers.js";
import { emit as _emitAiTrace } from "../features/ai-trace/state.js";
import { log } from "../runtime/diag.js";

function _emitException(rec: Record<string, unknown>): void {
    try { _emitAiTrace(rec); } catch { /* never throw */ }
    // Console-log error events to the host log too. The ai-trace stream only
    // keeps a counter; the invoked method + decoded MANAGED exception is the
    // single most useful signal when an il2cpp invoke faults ("system error").
    try {
        const evt = String(rec.evt ?? "");
        if (evt !== "invoke_native_error" && evt !== "invoke_exception") return;
        const mx = rec.managedException as
            { className?: string; message?: string } | null | undefined;
        const mgd = mx
            ? ` managed=${mx.className ?? "?"}: ${(mx.message ?? "").slice(0, 300)}`
            : (rec.className
                ? ` managed=${rec.className}: ${String(rec.message ?? "").slice(0, 300)}`
                : " managed=<none>");
        let btStr = "";
        const bt = rec.backtrace as Array<{ addr?: string }> | undefined;
        if (Array.isArray(bt) && bt.length) {
            const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
            const base = lib ? lib.base : null;
            const size = lib ? lib.size : 0;
            btStr = " bt=[ " + bt.slice(0, 14).map((f) => {
                try {
                    const a = ptr(String(f.addr));
                    if (base && a.compare(base) >= 0
                        && a.compare(base.add(size)) < 0) {
                        return "rva:0x" + a.sub(base).toString(16);
                    }
                    return String(f.addr);
                } catch { return String(f.addr); }
            }).join(" ") + " ]";
        }
        log(`[invoke-err] evt=${evt} method=${rec.method ?? "?"}`
            + ` msg=${String(rec.message ?? "").slice(0, 160)}${mgd}${btStr}`);
    } catch { /* never throw */ }
}

function exp(name: string): NativePointer {
    const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
    if (!lib) throw new Error(`${IL2CPP_MODULE_NAME} not loaded`);
    const p = lib.findExportByName(name);
    if (p === null) {
        throw new Error(`${IL2CPP_MODULE_NAME} export not found: ${name}`);
    }
    return p;
}

export const il2cpp_object_new = new NativeFunction(
    exp("il2cpp_object_new"), "pointer", ["pointer"]);

/**
 * ⚠ `exceptions: "propagate"` N'EST PAS UN RÉGLAGE DE CONFORT — SANS LUI, TOUT `try/catch`
 * MANAGÉ SITUÉ SOUS UN `invokeMethod` EST DÉSARMÉ, EN SILENCE.
 *
 * Le défaut de Frida est `exceptions: "steal"` : il pose son propre gestionnaire autour de
 * l'appel et CONFISQUE l'exception native. Or IL2CPP lève une exception managée comme une
 * exception C++ (`RaiseException`), et le dérouleur doit remonter jusqu'au `catch` managé.
 * Volée par Frida, elle n'y arrive jamais : le `catch` ne joue pas, `il2cpp_runtime_invoke`
 * n'écrit RIEN dans son paramètre de sortie `exc`, et il ne reste qu'un `Error("system
 * error")` sans classe ni message. C'est aussi pourquoi `decodeManagedException` ne rendait
 * jamais rien et pourquoi les ai-traces d'exception restaient vides.
 *
 * MESURE QUI L'ÉTABLIT (2026-08-20, build t6dpr4k06g, tranche #10040) -- même montage, même
 * plateau, même traceur ARMÉ dans les deux cas ; seul l'appelant change :
 *
 *   notre `invokeMethod(HandleOnStartBattleTapped)`
 *       `Ability_Power_GroupHandler$$ParseAbilityType` ENTRE et ne SORT PAS -> « system error »
 *   le CLIC HUMAIN sur le même bouton
 *       la même méthode, sur la MÊME source `DaemonicOrdnance_Crit`, ENTRE et SORT ;
 *       14 autres passages sortent aussi (`VoltagheistField`, `BeastSlayer`, ...) ;
 *       la bataille démarre et les 7 pas valent la référence AU CARACTÈRE (11980 compris).
 *
 * Le chemin en cause est ordinaire : `IdunMeta.Utils.Extensions.Enum$$TryParse` appelle
 * `System.Enum$$Parse`, qui LÈVE dès que le nom n'est pas dans l'enum visé -- et le jeu
 * traverse ça pour CHAQUE passif, puisque `ParseAbilityType` essaie « Ability_Active: »
 * avant « Ability_Passive: ». Le `catch` qui l'avale est un funclet, invisible au décompilé.
 *
 * ⚠ CE QUE ÇA COÛTE, ET POURQUOI C'EST QUAND MÊME LE BON CHOIX. Avec `propagate`, un VRAI
 * défaut natif (accès invalide) sous un invoke n'est plus converti en erreur JS : il tombe.
 * En échange, le contrat normal d'IL2CPP est rétabli -- `il2cpp_runtime_invoke` rattrape
 * lui-même l'exception managée et la rend par `exc`, que le code ci-dessous décode déjà.
 * Confisquer était pire : ça cassait le rattrapage du JEU, pas seulement le nôtre.
 */
export const il2cpp_runtime_invoke = new NativeFunction(
    exp("il2cpp_runtime_invoke"), "pointer",
    ["pointer", "pointer", "pointer", "pointer"],
    { exceptions: "propagate" });

const il2cpp_string_new = new NativeFunction(
    exp("il2cpp_string_new"), "pointer", ["pointer"]);

/** Build a managed System.String from a JS string (UTF-8 roundtrip). */
export function createManagedString(str: string): NativePointer {
    const buf = Memory.allocUtf8String(str);
    const p = il2cpp_string_new(buf) as NativePointer;
    if (p.isNull()) throw new Error("il2cpp_string_new returned null");
    return p;
}

// Resolved lazily on the first throw — direct field reads instead of
// recursive get_Message/get_StackTrace invokes, which themselves can throw
// and silently swallow the actual error.
//
// System.Exception layout (Unity 6 / IL2CPP v39, x64):
//   header     : 0x10
//   _message   : Il2CppString*  (offset resolved at runtime, typically 0x18)
//   _stackTraceString : Il2CppString*  (offset resolved at runtime)
let _excFieldsResolved = false;
let _excMessageOff = -1;
let _excStackOff = -1;

function _ensureExceptionFields(): void {
    if (_excFieldsResolved) return;
    _excFieldsResolved = true;
    let excClass = findClass("System.Private.CoreLib.dll", "System", "Exception");
    if (!excClass) excClass = findClass("mscorlib.dll", "System", "Exception");
    if (!excClass) excClass = findClassAnywhere("System", "Exception");
    if (!excClass) return;
    const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(excClass, it) as NativePointer).isNull()) {
        const name = s(field_get_name(f) as NativePointer);
        const off = field_get_offset(f) as number;
        if (name === "_message") _excMessageOff = off;
        else if (name === "_stackTraceString") _excStackOff = off;
        if (_excMessageOff >= 0 && _excStackOff >= 0) break;
    }
}

function _readManagedString(strPtr: NativePointer): string | null {
    if (strPtr.isNull()) return null;
    try {
        const len = strPtr.add(0x10).readS32();
        if (len <= 0 || len > 100000) return null;
        return strPtr.add(0x14).readUtf16String(len);
    } catch { return null; }
}

/** Decode a managed System.Exception object pointer into a structured
 *  payload (class name + message + stack). Best-effort: a malformed or
 *  freed exception ptr returns `{ className: "?" }` instead of throwing.
 *  Shared by `invokeMethod` and `crash-trap` so we have a single
 *  exception-decoder. */
export function decodeManagedException(excPtr: NativePointer): {
    className: string; message: string | null; stack: string | null;
} {
    let className = "?";
    try {
        if (!excPtr.isNull()) {
            className = s(class_get_name(excPtr.readPointer()) as NativePointer);
        }
    } catch { /* keep "?" */ }
    let message: string | null = null;
    let stack: string | null = null;
    try {
        _ensureExceptionFields();
        if (_excMessageOff >= 0) {
            const msgPtr = excPtr.add(_excMessageOff).readPointer();
            message = _readManagedString(msgPtr);
        }
        if (_excStackOff >= 0) {
            const stPtr = excPtr.add(_excStackOff).readPointer();
            stack = _readManagedString(stPtr);
        }
    } catch { /* best effort */ }
    return { className, message, stack };
}

/** Invoke a managed method. Throws with managed exception details on failure. */
export function invokeMethod(
    methodInfo: NativePointer,
    obj: NativePointer | null,
    args: NativePointer[] | null,
): NativePointer {
    const exc = Memory.alloc(Process.pointerSize);
    exc.writePointer(ptr(0));
    let params: NativePointer = ptr(0);
    if (args && args.length > 0) {
        params = Memory.alloc(args.length * Process.pointerSize);
        for (let i = 0; i < args.length; i++) {
            params.add(i * Process.pointerSize).writePointer(args[i]);
        }
    }
    let result: NativePointer;
    try {
        result = il2cpp_runtime_invoke(
            methodInfo, obj ?? ptr(0), params, exc) as NativePointer;
    } catch (e) {
        // NativeFunction-level error (Frida wraps native SEH / bad
        // signature / abi mismatch as a plain Error, often with
        // "system error" as message). Capture the method we were
        // trying to invoke + a native backtrace so we know where in
        // the call chain the failure happened.
        let methodName: string | null = null;
        try {
            methodName = s(method_get_name(methodInfo) as NativePointer);
        } catch { /* ignore */ }
        let bt: Array<{ addr: string; mod: string | null; name: string | null }> = [];
        try {
            bt = Thread.backtrace(undefined, Backtracer.FUZZY)
                .slice(0, 24)
                .map((addr) => {
                    const ds = DebugSymbol.fromAddress(addr);
                    return {
                        addr: addr.toString(),
                        mod: ds.moduleName ?? null,
                        name: ds.name ?? null,
                    };
                });
        } catch { /* keep [] */ }
        // Frida wraps the failure as a JS throw BEFORE we get a chance
        // to look at the *exc out-param. But often IL2CPP still wrote
        // the managed exception ptr into our `exc` buffer before
        // unwinding (e.g., when the throw is a managed C# exception
        // that propagated past IL2CPP's catch). Try to decode — if
        // we find a non-null exception, that's our real cause.
        let managed: ReturnType<typeof decodeManagedException> | null = null;
        try {
            const excValOnError = exc.readPointer();
            if (!excValOnError.isNull()) {
                managed = decodeManagedException(excValOnError);
            }
        } catch { /* best effort */ }
        _emitException({
            evt: "invoke_native_error",
            method: methodName,
            message: (e as Error).message,
            backtrace: bt,
            managedException: managed,
        });
        throw e;
    }
    const excVal = exc.readPointer();
    if (!excVal.isNull()) {
        const decoded = decodeManagedException(excVal);
        let methodName: string | null = null;
        try {
            methodName = s(method_get_name(methodInfo) as NativePointer);
        } catch { /* ignore */ }
        // Emit a structured ai-trace event so the JSONL captures the
        // managed exception details (class + message + first lines of
        // stack) — `invokeMethod` is the choke point for every
        // IL2CPP_RUNTIME_INVOKE wrapped call (deserialize, ctor, Apply,
        // etc.), so this catches the moment any of them throws.
        _emitException({
            evt: "invoke_exception",
            method: methodName,
            className: decoded.className,
            message: decoded.message,
            stack: decoded.stack ? decoded.stack.slice(0, 2000) : null,
        });
        let excMsg = `IL2CPP exception (${decoded.className})`;
        if (decoded.message) excMsg += ": " + decoded.message;
        if (decoded.stack) excMsg += "\n" + decoded.stack;
        throw new Error(excMsg);
    }
    return result;
}

// RETIRE (#480-r7) : `invokeMethodDirect` n'avait aucun appelant, et son corps
// CONTREDISAIT la regle etablie dans `il2cpp/helpers.ts` (`methodEntry`) : il lisait le
// `methodPointer` par `methodInfo.readPointer()`, que le commentaire de `methodEntry`
// declare UNSAFE -- « the first field of MethodInfo varies across IL2CPP versions (some
// have invoker_method first, methodPointer second) ». Le premier appelant l'aurait donc
// pris pour une voie validee. Le chemin sur : `invokeMethod` ci-dessus, qui passe par
// `il2cpp_runtime_invoke`.

/** Allocate + invoke the first parameterless ctor. For multi-ctor classes use
 * `findCtorByParamCount` + manual `invokeMethod`. */
export function createObject(klass: NativePointer): NativePointer {
    const obj = il2cpp_object_new(klass) as NativePointer;
    if (obj.isNull()) throw new Error("il2cpp_object_new returned null");
    const ctor = findMethod(klass, ".ctor");
    if (ctor) invokeMethod(ctor.info, obj, null);
    return obj;
}
