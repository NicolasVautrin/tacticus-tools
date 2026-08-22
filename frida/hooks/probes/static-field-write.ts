/** ÉCRIRE un champ STATIQUE — le pendant de `static-field-probe.ts`, par la même voie NOMMÉE.
 *
 *  ## Pourquoi ce module existe
 *
 *  Mesure du 2026-08-22. `ViewCommandExecutor$$StartMatch` refuse de monter une bataille quand un
 *  booléen statique « un match tourne déjà » est armé -- il journalise via `LogError` et
 *  **RETOURNE**, sans code de retour ni exception. Le porteur est
 *  `idun.IdunMainView` / `<IsActive>k__BackingField`.
 *
 *  Ce latch se libère normalement en quittant la bataille (`OnBattleSurrender` +
 *  `ContinueSurrender`, qui remettent les deux statiques à 0). **Mais il existe un régime où il
 *  est armé SANS bataille montée** : il n'y a alors rien à abandonner, aucune voie native ne le
 *  rend, et seule une relance du jeu le lève. C'est ce régime-là que ce module répare.
 *
 *  ⚠ ET IL NE SE DEVINE PAS DEPUIS `IsBattleActive` : les deux DIVERGENT. Mesuré, `IsActive` = 1
 *  avec `get_IsBattleActive()` = **false**, chargeur au repos, aucune bataille. Un correctif bâti
 *  sur le second saute exactement le cas qu'il devait réparer.
 *
 *  ## Discipline — c'est une ÉCRITURE, donc tout y est plus strict qu'en lecture
 *
 *  1. **`confirmer: true` EXIGÉ.** Sans lui, on rend le plan et on n'écrit rien.
 *  2. **On relit APRÈS, et on rend les DEUX valeurs.** Une écriture qui ne se confronte pas est
 *     une croyance : `avant`/`apres`/`mordu` sont publiés, et `mordu: false` est un résultat
 *     normal (le jeu peut réécrire derrière nous) -- pas une erreur qu'on masque.
 *  3. **Les types RÉFÉRENCE sont REFUSÉS.** Poser un entier là où le runtime attend un objet
 *     managé, c'est corrompre le tas -- et le GC ne tombe que bien plus tard, ailleurs, sur un
 *     symptôme qui n'accuse plus personne. Seuls les types VALEUR primitifs passent.
 *  4. **Une classe NON INITIALISÉE est REFUSÉE.** Son bloc de statiques est à zéro et n'appartient
 *     encore à personne ; y écrire n'a pas de sens, et le `.cctor` écrasera ensuite.
 *  5. **Aucun repli sur un offset.** Si `il2cpp_field_static_set_value` manque à l'export, on le
 *     DIT. Une arithmétique de pointeur sur un layout deviné écrirait à côté, en silence.
 */
import {
    class_get_fields, class_get_name, class_get_namespace, cstr, field_get_name,
    field_get_offset, field_get_type, findClassAnywhere, type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { classInitState, LIVE_CLASS_INIT_PROBE } from "../il2cpp/class-init.js";

const mod = Process.findModuleByName("GameAssembly.dll");

/** `il2cpp_field_static_set_value(FieldInfo*, void* value)` — la voie NOMMÉE. */
const field_static_set_value = (() => {
    const p = mod ? mod.findExportByName("il2cpp_field_static_set_value") : null;
    return p ? new NativeFunction(p, "void", ["pointer", "pointer"]) : null;
})();

/** `il2cpp_field_static_get_value(FieldInfo*, void* out)` — pour l'AVANT et l'APRÈS. */
const field_static_get_value = (() => {
    const p = mod ? mod.findExportByName("il2cpp_field_static_get_value") : null;
    return p ? new NativeFunction(p, "void", ["pointer", "pointer"]) : null;
})();

const field_get_flags = (() => {
    const p = mod ? mod.findExportByName("il2cpp_field_get_flags") : null;
    return p ? new NativeFunction(p, "int32", ["pointer"]) : null;
})();

const FIELD_ATTRIBUTE_STATIC = 0x10;

/** Les types VALEUR qu'on accepte d'écrire. Liste BLANCHE : tout ce qui n'y est pas est refusé,
 *  parce qu'un type inconnu peut être une référence déguisée ou une structure plus large. */
const TYPES_ECRIVABLES = new Set([
    "System.Boolean", "System.Byte", "System.SByte", "System.Int16", "System.UInt16",
    "System.Int32", "System.UInt32", "System.Int64", "System.UInt64", "System.Char",
]);

export interface StaticWriteArgs {
    ns: string;
    cls: string;
    /** Le champ à écrire. Un seul par appel -- une écriture se fait en le regardant. */
    field: string;
    /** La valeur, en entier. Les octets copiés sont ceux que le type déclare. */
    valeur: number;
    confirmer?: boolean;
}

function lire(f: NativePointer, buf: NativePointer): string | null {
    if (field_static_get_value === null) return null;
    try {
        buf.writeByteArray(new Array(16).fill(0));
        field_static_get_value(f, buf);
        const bytes = new Uint8Array(buf.readByteArray(8) as ArrayBuffer);
        return "0x" + Array.from(bytes).reverse()
            .map((b) => b.toString(16).padStart(2, "0")).join("");
    } catch { return null; }
}

export function staticFieldWrite(args: StaticWriteArgs): unknown {
    if (field_static_set_value === null || field_static_get_value === null) {
        return { ok: false, error: "`il2cpp_field_static_set_value` / `..._get_value` ne sont pas "
            + "exportes par ce build -- l'ecriture n'est PAS possible par cette voie, et on ne se "
            + "replie pas sur un offset (il ecrirait a cote, en silence)." };
    }
    if (!args || !args.ns || !args.cls || !args.field) {
        return { ok: false, error: "`ns`, `cls` et `field` sont EXIGES -- on n'ecrit pas sur une "
            + "cible devinee." };
    }
    const klass = findClassAnywhere(args.ns, args.cls);
    if (!klass) return { ok: false, error: "classe non resolue : " + args.ns + "." + args.cls };

    // ⚠ ON NE FORCE PAS L'INITIALISATION. Ecrire dans un bloc de statiques que le `.cctor` n'a
    //   pas encore rempli, c'est poser une valeur qu'il ECRASERA -- et le lecteur croirait avoir
    //   agi. On refuse, et on le nomme.
    const init = classInitState(LIVE_CLASS_INIT_PROBE, klass, false);
    if (init.initialized !== true) {
        return { ok: false, error: "classe NON INITIALISEE -- son bloc de statiques est a zero et "
            + "le `.cctor` ecraserait toute ecriture. Refus.", initialized: init.initialized };
    }

    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    let cible: NativePointer | null = null;
    let typeName: string | null = null;
    let offset = -1;
    let isStatic = true;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        let nom: string;
        try { nom = cstr(field_get_name(f) as NativePointer); } catch { continue; }
        if (nom !== args.field) continue;
        cible = f;
        offset = field_get_offset(f) as number;
        if (field_get_flags !== null) {
            try { isStatic = ((field_get_flags(f) as number) & FIELD_ATTRIBUTE_STATIC) !== 0; }
            catch { /* on garde `true` et le type tranchera */ }
        }
        try {
            const tc = type_get_class_or_element_class(
                field_get_type(f) as NativePointer) as NativePointer;
            if (!tc.isNull()) {
                const ns = cstr(class_get_namespace(tc) as NativePointer);
                const cn = cstr(class_get_name(tc) as NativePointer);
                typeName = ns ? ns + "." + cn : cn;
            }
        } catch { /* typeName reste null -- et un type inconnu sera refuse */ }
        break;
    }
    if (cible === null) {
        return { ok: false, error: "champ `" + args.field + "` ABSENT de " + args.ns + "."
            + args.cls + " -- `staticFieldProbe` liste ce qui existe." };
    }
    if (!isStatic) {
        return { ok: false, error: "`" + args.field + "` est un champ d'INSTANCE : il n'a pas de "
            + "valeur statique, et `field_static_set_value` y ecrirait n'importe ou." };
    }
    if (typeName === null || !TYPES_ECRIVABLES.has(typeName)) {
        return { ok: false, error: "type `" + (typeName ?? "INCONNU") + "` REFUSE a l'ecriture. "
            + "Seuls les primitifs VALEUR sont acceptes : poser un entier la ou le runtime attend "
            + "un objet mange corrompt le tas, et le GC ne tombe que plus tard, ailleurs.",
            typeName, ecrivables: Array.from(TYPES_ECRIVABLES) };
    }

    const buf = Memory.alloc(16);
    const avant = lire(cible, buf);
    if (args.confirmer !== true) {
        return { ok: true, plan: true, ecrit: false,
                 cible: args.ns + "." + args.cls + "::" + args.field,
                 typeName, offset: "0x" + offset.toString(16), avant,
                 valeurDemandee: args.valeur,
                 note: "PLAN SEUL -- rien n'a ete ecrit. Repasser avec `confirmer: true`." };
    }

    const src = Memory.alloc(16);
    src.writeByteArray(new Array(16).fill(0));
    // Le runtime copie le nombre d'octets que DECLARE le type ; un tampon de 8 octets a zero dont
    // on ne pose que le bas convient donc a tous les primitifs de la liste blanche.
    src.writeS64(int64(String(Math.trunc(args.valeur))));
    try {
        field_static_set_value(cible, src);
    } catch (e) {
        return { ok: false, error: "`field_static_set_value` a leve : " + (e as Error).message,
                 avant };
    }

    // ⚠ ON RELIT. Une ecriture qui ne se confronte pas est une croyance -- et le jeu peut tres
    //   bien reecrire derriere nous a la frame suivante.
    const apres = lire(cible, buf);
    return { ok: true, ecrit: true,
             cible: args.ns + "." + args.cls + "::" + args.field,
             typeName, offset: "0x" + offset.toString(16),
             avant, apres, valeurDemandee: args.valeur,
             mordu: apres !== null && avant !== null ? apres !== avant : null,
             note: "`mordu: false` n'est pas une erreur -- c'est une MESURE : la valeur demandee "
                 + "etait peut-etre deja en place, ou le jeu a reecrit derriere. `null` = une des "
                 + "deux lectures a echoue, donc NON MESURE." };
}
