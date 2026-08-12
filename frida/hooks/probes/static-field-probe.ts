/** `#590-r5` — CAPTEUR : la VALEUR des champs STATIQUES d'une classe, au runtime.
 *
 *  ## Le residu, et pourquoi la lecture doit etre LIVE
 *
 *  `IdunBattle.AI.Utilities.OnlyCertainTargetUtility$$EvaluateAttackInSteps` yield `statics+0x00`
 *  quand `targets.Contains(case.Target)` et `statics+0x20` sinon (LU). Mais la classe n'a **pas de
 *  `.cctor` nomme** et les deux slots sont des `DAT_*` : leur valeur n'est ecrite nulle part que
 *  le decompile expose. Le port de `#590` a retenu l'ELIMINATION (une cible hors liste n'est pas
 *  candidate) sur trois arguments LUS ; si la constante de rejet etait seulement BASSE, le port
 *  refuserait de frapper la ou le natif frapperait faute de mieux.
 *
 *  **Trancher demande de lire les deux champs A L'EXECUTION.** C'est tout ce que fait ce capteur.
 *
 *  ## Ce qu'il rend, et les trois pieges qu'il nomme
 *
 *  Pour chaque champ statique : son nom, son offset dans le bloc de statiques, et sa valeur lue
 *  par `il2cpp_field_static_get_value` — la fonction NOMMEE de l'API, jamais une arithmetique de
 *  pointeur sur un layout devine.
 *
 *  1. ⚠ **Une classe NON INITIALISEE rend des zeros, et un zero est une valeur du domaine.**
 *     Tant que le `.cctor` n'a pas tourne, le bloc de statiques est a zero — et « 0 » se lirait
 *     comme « la constante de rejet vaut 0 », c'est-a-dire exactement le verdict qu'on cherche a
 *     etablir. Le capteur PUBLIE donc l'etat d'initialisation (`initialized`) et peut FORCER
 *     l'initialisation (`il2cpp_runtime_class_init`) sur demande explicite. Un lecteur qui voit
 *     `initialized: false` ne tient pas une mesure.
 *  2. ⚠ **Le TYPE decide la lecture.** Une `Fix64` est un Q32.32 sur 8 octets : la lire en `int32`
 *     rendrait sa moitie basse. On publie donc les 8 octets BRUTS (base 10 signee et hexa) ET
 *     l'interpretation Q32.32, en les etiquetant — le lecteur choisit, le capteur ne devine pas.
 *  3. ⚠ **Un statique de type REFERENCE n'est pas une valeur.** On le signale (`isReference`) et
 *     on ne publie que le pointeur : dereferencer a l'aveugle un objet managé est le genre de
 *     geste qui fige le jeu.
 *
 *  ## Discipline
 *
 *  Lecture PURE : zero `Interceptor`, zero heap scan, aucune ecriture. `runtime_class_init` est le
 *  SEUL appel qui ait un effet, il est sous drapeau explicite (`forceInit`), et c'est exactement
 *  ce que le jeu fait lui-meme au premier acces (les corps decompiles portent tous le motif
 *  `if (*(int *)(DAT_xxx + 0xe4) == 0) il2cpp_runtime_class_init();`).
 */
import {
    class_get_fields, class_get_name, class_get_namespace, cstr, field_get_name,
    field_get_offset, field_get_type, findClassAnywhere, type_get_class_or_element_class,
} from "../il2cpp/helpers.js";

const mod = Process.findModuleByName("GameAssembly.dll");

/** `il2cpp_field_static_get_value(FieldInfo*, void* out)` — la voie NOMMEE. Resolue de facon
 *  TOLERANTE : si l'export manque, on le DIT au lieu de bricoler un offset. */
const field_static_get_value = (() => {
    const p = mod ? mod.findExportByName("il2cpp_field_static_get_value") : null;
    return p ? new NativeFunction(p, "void", ["pointer", "pointer"]) : null;
})();

/** `il2cpp_runtime_class_init(Il2CppClass*)` — ce que le jeu appelle lui-meme au premier acces. */
const runtime_class_init = (() => {
    const p = mod ? mod.findExportByName("il2cpp_runtime_class_init") : null;
    return p ? new NativeFunction(p, "void", ["pointer"]) : null;
})();

/** `il2cpp_field_get_flags(FieldInfo*)` — le bit `FIELD_ATTRIBUTE_STATIC` (0x10). */
const field_get_flags = (() => {
    const p = mod ? mod.findExportByName("il2cpp_field_get_flags") : null;
    return p ? new NativeFunction(p, "int32", ["pointer"]) : null;
})();

const FIELD_ATTRIBUTE_STATIC = 0x10;

/** `Il2CppClass.initialized_and_no_error` vit a `+0xe4` sur ce build — c'est LITTERALEMENT
 *  l'offset que tout corps decompile teste (`if (*(int *)(DAT_xxx + 0xe4) == 0)
 *  il2cpp_runtime_class_init();`). On ne s'en sert QUE pour RAPPORTER l'etat, jamais pour
 *  decider d'une lecture : si l'offset devenait faux, on publierait un etat faux, pas une
 *  valeur fausse. */
const CLASS_INITIALIZED_OFF = 0xe4;

interface StaticRow {
    name: string;
    /** Offset dans le bloc de statiques de la classe. */
    offset: string;
    typeName: string | null;
    isReference: boolean;
    /** Les 8 octets bruts, en hexa — la seule forme qui ne perd rien. `null` si non lu. */
    rawHex: string | null;
    /** Les 8 octets lus comme un entier signe 64 bits (base 10). */
    rawS64: string | null;
    /** Interpretation Q32.32 (`raw / 2^32`) — VALABLE SEULEMENT si le champ est une `Fix64`.
     *  Etiquetee, jamais imposee : le lecteur confronte a `typeName`. */
    asFix64: number | null;
    /** Les 4 octets bas comme `int32`, pour les champs entiers. */
    asInt32: number | null;
    note?: string;
}

export interface StaticFieldArgs {
    ns: string;
    cls: string;
    /** Noms a lire ; vide = TOUS les champs statiques. */
    fields?: string[];
    /** Force `il2cpp_runtime_class_init` avant lecture. Par defaut FAUX : une mesure sur une
     *  classe non initialisee doit se voir, pas se corriger en douce. */
    forceInit?: boolean;
}

export function staticFieldProbe(args: StaticFieldArgs): unknown {
    if (field_static_get_value === null) {
        return { ok: false, error: "`il2cpp_field_static_get_value` n'est pas exporte par ce "
            + "build — la valeur des statiques n'est PAS mesurable par cette voie. Rien n'est "
            + "rendu (un layout devine rendrait des nombres plausibles et faux)." };
    }
    const klass = findClassAnywhere(args.ns, args.cls);
    if (!klass) return { ok: false, error: "classe non resolue: " + args.ns + "." + args.cls };

    let initializedBefore: boolean | null = null;
    try { initializedBefore = klass.add(CLASS_INITIALIZED_OFF).readS32() !== 0; }
    catch { /* offset hors structure : on rend null, jamais un booleen invente */ }

    let forced = false;
    if (args.forceInit && runtime_class_init !== null) {
        try { runtime_class_init(klass); forced = true; } catch { /* */ }
    }
    let initializedAfter: boolean | null = null;
    try { initializedAfter = klass.add(CLASS_INITIALIZED_OFF).readS32() !== 0; }
    catch { /* */ }

    const want = args.fields && args.fields.length ? new Set(args.fields) : null;
    const buf = Memory.alloc(16);
    const rows: StaticRow[] = [];
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        const name = cstr(field_get_name(f) as NativePointer);
        if (want && !want.has(name)) continue;
        // Un champ d'INSTANCE n'a pas de valeur statique : `field_static_get_value` y ecrirait
        // n'importe quoi. On le saute, et on le dit quand il etait explicitement demande.
        let isStatic = true;
        if (field_get_flags !== null) {
            try { isStatic = ((field_get_flags(f) as number) & FIELD_ATTRIBUTE_STATIC) !== 0; }
            catch { /* */ }
        }
        let typeName: string | null = null;
        let isReference = false;
        try {
            const ty = field_get_type(f) as NativePointer;
            const tc = type_get_class_or_element_class(ty) as NativePointer;
            if (!tc.isNull()) {
                const ns = cstr(class_get_namespace(tc) as NativePointer);
                const cn = cstr(class_get_name(tc) as NativePointer);
                typeName = ns ? ns + "." + cn : cn;
                // Heuristique DECLAREE : on ne dispose pas de `il2cpp_class_is_valuetype` ici de
                // facon garantie, donc on se contente de signaler les types dont le nom trahit une
                // reference. Le lecteur a `typeName` sous les yeux.
                isReference = /^(System\.String|System\.Object)$/.test(typeName);
            }
        } catch { /* */ }
        const offset = field_get_offset(f) as number;
        if (!isStatic) {
            rows.push({ name, offset: "0x" + offset.toString(16), typeName, isReference: false,
                rawHex: null, rawS64: null, asFix64: null, asInt32: null,
                note: "champ d'INSTANCE — pas de valeur statique a lire" });
            continue;
        }
        let rawHex: string | null = null;
        let rawS64: string | null = null;
        let asFix64: number | null = null;
        let asInt32: number | null = null;
        let note: string | undefined;
        try {
            buf.writeByteArray(new Array(16).fill(0));
            field_static_get_value(f, buf);
            const bytes = new Uint8Array(buf.readByteArray(8) as ArrayBuffer);
            rawHex = "0x" + Array.from(bytes).reverse()
                .map((b) => b.toString(16).padStart(2, "0")).join("");
            const s64 = buf.readS64();
            rawS64 = s64.toString();
            asInt32 = buf.readS32();
            try { asFix64 = Number(BigInt(s64.toString())) / 4294967296; }
            catch { asFix64 = null; }
        } catch (e) { note = "lecture impossible: " + (e as Error).message; }
        rows.push({ name, offset: "0x" + offset.toString(16), typeName, isReference,
            rawHex, rawS64, asFix64, asInt32, note });
    }

    return {
        ok: true,
        cls: args.ns + "." + args.cls,
        klass: klass.toString(),
        /** ⚠ `initialized: false` ⇒ les valeurs ci-dessous sont celles d'un bloc a ZERO, pas
         *  celles du jeu. Un lecteur qui l'ignore conclura « la constante vaut 0 ». */
        initialized: initializedAfter,
        initializedBefore, forcedInit: forced,
        runtimeClassInitAvailable: runtime_class_init !== null,
        fieldCount: rows.length,
        fields: rows,
    };
}
