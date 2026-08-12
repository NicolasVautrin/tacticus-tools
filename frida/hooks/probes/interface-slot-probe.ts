/** `#916-r1` / `#590-r2` — CAPTEUR : NOMMER un slot d'INTERFACE, et LIRE ce que
 *  l'implementation d'une classe concrete en rend.
 *
 *  ## Les deux residus, une seule mecanique
 *
 *  Deux residus butent sur la meme illisibilite, et c'est pour ca qu'ils partagent un capteur :
 *
 *   * `#916-r1` — `IdunBattle.Operations.AddEffectOperation$$UpdateExistingEffect` consulte le
 *     **slot 5** de l'`IEffect` de chaque instance deja posee, et SAUTE (`continue`) celles pour
 *     lesquelles il rend vrai. C'est exactement la bifurcation « empiler ou rafraichir » que le
 *     port encode par `BaseEffect.stacks_stat_mod_on_add` — pose jusqu'ici a la main, effet par
 *     effet, par une MESURE LIVE distincte a chaque fois.
 *   * `#590-r2` — `IdunBattle.Operations.ChangeUnitOwnerOperation$$RemoveEffects` consulte le
 *     **slot 3** d'une interface de CONFIGURATION d'effet, absente des tables de slots versionnees.
 *
 *  Dans les deux cas le decompile montre un appel INDIRECT (`(**(code **)(*plVar + N))()`) : le nom
 *  du slot est une valeur RUNTIME derriere la metadata IL2CPP, donc structurellement illisible
 *  statiquement. Ce capteur va le chercher la ou il est.
 *
 *  ## Ce qu'il rend, et pourquoi CETTE forme
 *
 *  Trois etages, chacun verifiable independamment :
 *
 *   1. **Les methodes de l'INTERFACE, dans l'ordre des slots.** `il2cpp_class_get_methods` enumere
 *      dans l'ordre du metadata, qui EST l'ordre des slots pour une interface. C'est la reponse
 *      directe a « comment s'appelle le slot 5 ».
 *   2. **La vtable de chaque classe CONCRETE**, calibree (cf. ci-dessous) — donc quelle METHODE de
 *      la classe implemente reellement ce slot d'interface.
 *   3. **Le CORPS de cette implementation, DESASSEMBLE** jusqu'au premier `ret` (borne). Un
 *      predicat de cette famille est presque toujours un corps trivial (`mov al,1 ; ret`), donc le
 *      drapeau se DERIVE par LECTURE — sans instance, sans invocation, sans le moindre effet de
 *      bord. C'est ce qui permet de recenser TOUS les types empilables du build d'un coup au lieu
 *      d'en mesurer un par tranche.
 *
 *  ⚠ **Aucune invocation.** « Un natif qui ECRIT s'OBSERVE d'abord » : on ne sait pas, avant de
 *  l'avoir lu, si le slot est un getter pur. Lire les octets ne peut rien casser ; appeler, si.
 *  Quand le corps n'est PAS trivial, on rend `verdict: null` avec le listing — jamais un booleen
 *  devine. Un tri-etat, jamais un faux zero.
 *
 *  ## La CALIBRATION de la vtable, et pourquoi elle n'est pas une constante
 *
 *  L'offset du DEBUT de la vtable dans `Il2CppClass` depend de la version d'IL2CPP. L'ecrire en dur
 *  serait la meme faute que la RVA epinglee : juste aujourd'hui, faux en silence a la prochaine
 *  mise a jour d'Unity, et le symptome serait des noms de slots DECALES — donc un verdict faux,
 *  pas une erreur.
 *
 *  On le MESURE : on balaie les offsets et on cherche celui ou la vtable commence par la signature
 *  de `System.Object` (`Equals`, `Finalize`, `GetHashCode`, `ToString` aux slots 0..3), qui est
 *  invariante par construction du CLR. La calibration est PUBLIEE (`vtableStart`, `calibration`) :
 *  un lecteur qui trouve `calibrated: false` sait que tout le reste est a jeter, au lieu de lire des
 *  noms plausibles et faux.
 *
 *  ## Discipline
 *
 *  Lecture PURE : zero `Interceptor`, zero invocation, zero ecriture. Ce module n'installe rien au
 *  chargement — il n'expose qu'un RPC. Aucun heap scan (on ne parcourt que des structures dont on
 *  tient deja le pointeur, jamais `Process.enumerateRanges` ni `Memory.scan`).
 */
import {
    class_get_methods, class_get_name, class_get_namespace, class_get_parent,
    cstr, findClassAnywhere, il2cppBase, method_get_name, method_get_param_count,
    methodEntry,
} from "../il2cpp/helpers.js";

/** Ghidra a charge `GameAssembly.dll` a cette base : c'est ce qui rend une adresse citable
 *  dans un decompile. Ce n'est PAS une RVA epinglee — rien ne s'y attache. */
const GHIDRA_BASE = ptr("0x180000000");

/** Bornes du balayage de calibration. Large, mais borne : on lit des pointeurs dans une structure
 *  dont on tient l'adresse, jamais de la memoire arbitraire. */
const VTABLE_SCAN_START = 0x80;
const VTABLE_SCAN_END = 0x800;
/** Une entree de vtable IL2CPP = `VirtualInvokeData { methodPtr(8), MethodInfo*(8) }`. */
const VTABLE_STRIDE = 0x10;
/** La signature invariante de `System.Object`, dans l'ordre des slots. */
const OBJECT_SLOTS = ["Equals", "Finalize", "GetHashCode", "ToString"];
/** Borne du desassemblage d'un corps : un predicat trivial tient en 3 instructions ; au-dela on
 *  rend le listing tronque plutot que de derouler une fonction entiere. */
const MAX_INSNS = 24;

interface SlotRow {
    slot: number;
    /** Nom de la methode d'INTERFACE a ce slot (`null` si l'interface n'a pas tant de slots). */
    ifaceMethod: string | null;
    /** Nom de la methode de la classe CONCRETE qui l'implemente. */
    implMethod: string | null;
    /** Classe qui DECLARE l'implementation (une classe de base, souvent). */
    implOwner: string | null;
    entry: string;
    ghidraVA: string;
    /** Le corps desassemble jusqu'au premier `ret`, borne. */
    disasm: string[] | null;
    /** `true`/`false` si le corps est un retour CONSTANT reconnu ; `null` = corps non trivial,
     *  le lecteur tranche sur `disasm`. JAMAIS un booleen devine. */
    verdict: boolean | null;
    /** Pourquoi `verdict` est `null`, quand il l'est. */
    note?: string;
}

/** Desassemble a partir de `entry` jusqu'au premier `ret` (borne `MAX_INSNS`). */
function disassembleBody(entry: NativePointer): string[] | null {
    if (entry.isNull()) return null;
    const out: string[] = [];
    let p = entry;
    try {
        for (let i = 0; i < MAX_INSNS; i++) {
            const insn = Instruction.parse(p);
            out.push(insn.mnemonic + " " + insn.opStr);
            if (insn.mnemonic === "ret" || insn.mnemonic === "jmp") break;
            p = insn.next;
        }
    } catch (e) {
        out.push("<illisible: " + (e as Error).message + ">");
    }
    return out;
}

/** Un corps de predicat trivial -> le booleen qu'il rend. `null` des que la forme n'est pas
 *  RECONNUE : mieux vaut « je ne sais pas » qu'un booleen plausible.
 *
 *  Formes reconnues (x86-64, ce que le backend IL2CPP emet pour `return true/false`) :
 *    `mov al, 1  ; ret`        -> true
 *    `mov eax, 1 ; ret`        -> true
 *    `xor eax, eax ; ret`      -> false
 *    `mov al, 0  ; ret`        -> false
 *  Les prologues neutres (`push`/`sub rsp`/`add rsp`/`pop`/`nop`) sont TRAVERSES : un corps
 *  trivial peut porter un cadre de pile sans cesser d'etre constant. Tout le reste -> `null`. */
function trivialReturn(disasm: string[] | null): { verdict: boolean | null; note?: string } {
    if (!disasm || disasm.length === 0) return { verdict: null, note: "corps illisible" };
    let value: boolean | null = null;
    for (const line of disasm) {
        const t = line.trim().toLowerCase();
        if (t === "ret") {
            if (value === null) return { verdict: null, note: "`ret` sans valeur constante posee" };
            return { verdict: value };
        }
        // Prologue / epilogue neutres : ils ne touchent pas EAX.
        if (/^(push|pop|nop|sub rsp|add rsp|endbr64|int3)/.test(t)) continue;
        let m = /^mov (al|eax), (0x[0-9a-f]+|\d+)$/.exec(t);
        if (m) { value = Number(m[2]) !== 0; continue; }
        m = /^xor (eax, eax|al, al)$/.exec(t);
        if (m) { value = false; continue; }
        return { verdict: null, note: "corps NON trivial (`" + line.trim() + "`)" };
    }
    return { verdict: null, note: "aucun `ret` dans les " + MAX_INSNS + " premieres instructions" };
}

/** Le nom pleinement qualifie d'une classe. */
function fqn(k: NativePointer): string {
    const ns = cstr(class_get_namespace(k) as NativePointer);
    const cls = cstr(class_get_name(k) as NativePointer);
    return ns ? ns + "." + cls : cls;
}

/** Les methodes d'une classe, DANS L'ORDRE d'enumeration du metadata. Pour une INTERFACE, cet
 *  ordre EST celui des slots. */
function methodsInOrder(k: NativePointer): Array<{ name: string; paramCount: number | null }> {
    const out: Array<{ name: string; paramCount: number | null }> = [];
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
        let pc: number | null = null;
        try { pc = method_get_param_count(m) as number; } catch { /* */ }
        out.push({ name: cstr(method_get_name(m) as NativePointer), paramCount: pc });
    }
    return out;
}

/** Lit une entree de vtable a l'offset OCTET `off` : `{ methodPtr, MethodInfo* }`. */
function readVtableEntry(klass: NativePointer, off: number): {
    entry: NativePointer; mi: NativePointer; name: string | null;
} | null {
    try {
        const fp = klass.add(off).readPointer();
        const mi = klass.add(off + 8).readPointer();
        if (mi.isNull()) return null;
        const nm = method_get_name(mi) as NativePointer;
        if (nm.isNull()) return null;
        const name = cstr(nm);
        // Un nom de methode est ASCII imprimable et court : c'est le filtre qui separe une vraie
        // entree de vtable d'un pointeur quelconque lu au hasard dans la structure.
        if (!name || name.length > 200 || !/^[\x20-\x7e]+$/.test(name)) return null;
        return { entry: fp, mi, name };
    } catch { return null; }
}

/** CALIBRE le debut de la vtable en cherchant la signature de `System.Object`.
 *  Rend `null` si aucun offset ne la porte — auquel cas TOUT le reste est a jeter, et on le dit. */
function calibrateVtable(klass: NativePointer): {
    vtableStart: number; matched: string[];
} | null {
    for (let off = VTABLE_SCAN_START; off <= VTABLE_SCAN_END; off += 8) {
        const names: string[] = [];
        let ok = true;
        for (let i = 0; i < OBJECT_SLOTS.length; i++) {
            const e = readVtableEntry(klass, off + i * VTABLE_STRIDE);
            if (e === null || e.name !== OBJECT_SLOTS[i]) { ok = false; break; }
            names.push(e.name);
        }
        if (ok) return { vtableStart: off, matched: names };
    }
    return null;
}

/** `il2cpp_class_get_interface_offset(klass, itf)` — l'index du premier slot de `itf` dans la
 *  vtable PLATE de `klass`. Resolu de facon TOLERANTE : s'il manque, on le DIT et on rend `null`,
 *  jamais un zero qui se lirait « l'interface commence au slot 0 ». */
const class_get_interface_offset = (() => {
    const mod = Process.findModuleByName("GameAssembly.dll");
    const p = mod ? mod.findExportByName("il2cpp_class_get_interface_offset") : null;
    return p ? new NativeFunction(p, "int32", ["pointer", "pointer"]) : null;
})();

export interface InterfaceSlotArgs {
    /** L'interface dont on veut NOMMER les slots. */
    iface: { ns: string; cls: string };
    /** Les classes concretes dont on veut lire l'implementation. Vide = on ne rend que
     *  l'enumeration de l'interface (etage 1), ce qui est deja la reponse a « comment
     *  s'appelle le slot N ». */
    impls?: Array<{ ns: string; cls: string }>;
    /** Les slots a resoudre. Defaut : TOUS ceux de l'interface. */
    slots?: number[];
}

export function interfaceSlotProbe(args: InterfaceSlotArgs): unknown {
    const ifaceKlass = findClassAnywhere(args.iface.ns, args.iface.cls);
    if (!ifaceKlass) {
        return { ok: false, error: "interface non resolue: " + args.iface.ns + "." + args.iface.cls };
    }
    const ifaceMethods = methodsInOrder(ifaceKlass);
    const slots = args.slots ?? ifaceMethods.map((_, i) => i);

    const impls = (args.impls ?? []).map((spec) => {
        const klass = findClassAnywhere(spec.ns, spec.cls);
        if (!klass) {
            return { ns: spec.ns, cls: spec.cls, ok: false,
                error: "classe non resolue: " + spec.ns + "." + spec.cls };
        }
        const cal = calibrateVtable(klass);
        if (cal === null) {
            return { ns: spec.ns, cls: spec.cls, ok: false, calibrated: false,
                error: "CALIBRATION IMPOSSIBLE — la signature `System.Object` "
                    + "(Equals/Finalize/GetHashCode/ToString) n'a ete trouvee a AUCUN offset entre "
                    + "0x" + VTABLE_SCAN_START.toString(16) + " et 0x" + VTABLE_SCAN_END.toString(16)
                    + ". Sans elle l'indexation des slots serait DECALEE, donc tous les noms "
                    + "rendus seraient faux SANS erreur. Rien n'est rendu." };
        }
        let ifaceOffset: number | null = null;
        let offsetNote: string | undefined;
        if (class_get_interface_offset === null) {
            offsetNote = "`il2cpp_class_get_interface_offset` n'est pas exporte par ce build : "
                + "l'index du bloc d'interface dans la vtable plate n'est PAS mesure. Les slots "
                + "rendus ci-dessous sont donc ceux de la vtable BRUTE, pas ceux de l'interface.";
        } else {
            try {
                const v = class_get_interface_offset(klass, ifaceKlass) as number;
                // L'API rend -1 quand la classe n'implemente pas l'interface.
                if (v < 0) {
                    offsetNote = "la classe N'IMPLEMENTE PAS cette interface "
                        + "(`il2cpp_class_get_interface_offset` rend " + v + ").";
                } else { ifaceOffset = v; }
            } catch (e) { offsetNote = "lecture de l'offset d'interface impossible: "
                + (e as Error).message; }
        }

        const rows: SlotRow[] = slots.map((slot) => {
            const vtIndex = (ifaceOffset ?? 0) + slot;
            const off = cal.vtableStart + vtIndex * VTABLE_STRIDE;
            const e = readVtableEntry(klass, off);
            const ifaceMethod = ifaceMethods[slot]?.name ?? null;
            if (e === null) {
                return { slot, ifaceMethod, implMethod: null, implOwner: null,
                    entry: "", ghidraVA: "", disasm: null, verdict: null,
                    note: "aucune entree de vtable lisible a l'index " + vtIndex };
            }
            const disasm = disassembleBody(e.entry);
            const tr = trivialReturn(disasm);
            let ghidraVA = "";
            try { ghidraVA = GHIDRA_BASE.add(e.entry.sub(il2cppBase)).toString(); } catch { /* */ }
            // Le DECLARANT de l'implementation : `MethodInfo.klass` est le champ a +0x18 sur ce
            // layout, mais on ne le suppose pas — on remonte plutot par le nom, qui suffit ici.
            return { slot, ifaceMethod, implMethod: e.name, implOwner: null,
                entry: e.entry.toString(), ghidraVA, disasm,
                verdict: tr.verdict, note: tr.note };
        });

        return { ns: spec.ns, cls: spec.cls, ok: true, calibrated: true,
            klass: klass.toString(), vtableStart: "0x" + cal.vtableStart.toString(16),
            calibration: cal.matched, interfaceOffset: ifaceOffset, offsetNote,
            parent: (() => {
                const p = class_get_parent(klass) as NativePointer;
                return p.isNull() ? null : fqn(p);
            })(),
            slots: rows };
    });

    return {
        ok: true,
        iface: fqn(ifaceKlass),
        ifaceMethodCount: ifaceMethods.length,
        /** L'ordre d'enumeration du metadata EST l'ordre des slots pour une interface : cette
         *  liste est, a elle seule, la reponse a « comment s'appelle le slot N ». */
        ifaceMethods: ifaceMethods.map((m, i) => ({ slot: i, name: m.name, paramCount: m.paramCount })),
        interfaceOffsetApi: class_get_interface_offset !== null,
        impls,
    };
}

/** Les INTERFACES qu'une classe implemente, avec l'offset de chacune dans la vtable plate.
 *  Sert a TROUVER le nom d'une interface qu'un decompile ne designe que par un `DAT_*`
 *  (le cas de `#590-r2` : « une interface de configuration d'effet, absente des deux tables de
 *  slots versionnees »). */
export function classInterfaces(args: { ns: string; cls: string }): unknown {
    const klass = findClassAnywhere(args.ns, args.cls);
    if (!klass) return { ok: false, error: "classe non resolue: " + args.ns + "." + args.cls };
    const mod = Process.findModuleByName("GameAssembly.dll");
    const p = mod ? mod.findExportByName("il2cpp_class_get_interfaces") : null;
    if (p === null) {
        return { ok: false, error: "`il2cpp_class_get_interfaces` non exporte par ce build — "
            + "les interfaces implementees ne sont PAS mesurables par cette voie." };
    }
    const getInterfaces = new NativeFunction(p, "pointer", ["pointer", "pointer"]);
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    const out: Array<{ name: string; offset: number | null; methods: string[] }> = [];
    let i: NativePointer;
    while (!(i = getInterfaces(klass, it) as NativePointer).isNull()) {
        let offset: number | null = null;
        if (class_get_interface_offset !== null) {
            try {
                const v = class_get_interface_offset(klass, i) as number;
                offset = v < 0 ? null : v;
            } catch { /* */ }
        }
        out.push({ name: fqn(i), offset,
            methods: methodsInOrder(i).map((m) => m.name) });
        if (out.length > 200) break;
    }
    return { ok: true, cls: fqn(klass), interfaceOffsetApi: class_get_interface_offset !== null,
        count: out.length, interfaces: out };
}
