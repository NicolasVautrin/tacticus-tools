// Extraction du TIER DE PRÉFÉRENCE par-ability (`playbook.get_Preference()`).
//
// RE (gqfc5mff6c) : `ABaseAiActorTactic.InitAbilityTypeLists @1810ed540` range chaque
// ActiveAbilityType dans `Dict<Preference, List<AbilityType>>` via
// `pref = playbook.get_Preference()` (slot 0 de l'interface playbook). Ce tier ordonne les
// générateurs, itérés PREMIER-NON-NULL : `[1000, 100, 0, -100, -1000, FINAL]`
// (`GetDefaultActiveAbilityActionGenerators @1810ed0c0`). cf. docs/rl/playbook/architecture.md §2.3.
//
// `get_Preference` est un virtuel per-playbook SANS symbole statique → on lit la valeur LIVE.
// On capture PASSIVEMENT une `PlaybookDatabase` vivante en hookant `LoadPlaybook` (fire à chaque
// décision AI), puis l'RPC appelle `LoadPlaybook(db, ability, isOwner=1)` + `get_Preference` par
// ability. LECTURE SEULE (aucune mutation d'état ; `get_Preference` = getter constant/champ).

import {
    findClassAnywhere, findMethodByParamCount, class_get_name, cstr,
    class_get_methods, method_get_name, method_get_param_count, class_get_parent,
} from "../il2cpp/helpers.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

// Cherche une méthode 0-param nommée parmi `names` dans la hiérarchie de `klass`.
function findGetter(klass: NativePointer, names: string[]) {
    for (const n of names) {
        const m = findMethodByParamCount(klass, n, 0);
        if (m) return { ref: m, name: n };
    }
    return null;
}

// Dump des noms de méthodes (0-param) de klass+parents contenant `needle` (diagnostic).
function methodsMatching(klass: NativePointer, needle: string): string[] {
    const out: string[] = [];
    let k = klass;
    let guard = 0;
    while (!k.isNull() && guard++ < 14) {
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
            const nm = cstr(method_get_name(m) as NativePointer);
            if (nm.toLowerCase().includes(needle)) {
                let pc = -1;
                try { pc = method_get_param_count(m) as number; } catch { /* skip */ }
                out.push(`${nm}/${pc}`);
            }
        }
        k = class_get_parent(k) as NativePointer;
    }
    return out;
}

// Dernière PlaybookDatabase vue passer par LoadPlaybook (mise à jour à chaque décision AI →
// toujours fraîche vis-à-vis du runner courant). Le hook = un simple store de pointeur.
let capturedDb: NativePointer | null = null;
let loadPlaybook: { info: NativePointer; ptr: NativePointer } | null = null;

export function register(ctx: Ctx): void {
    // Arme la capture passive : `LoadPlaybook(db, ability, isOwner)` = 2 params managés (la
    // surcharge utilisée par InitAbilityTypeLists ET le générateur). args[0] = `this` = le DB.
    try {
        const dbClass = findClassAnywhere("IdunBattle.AI", "PlaybookDatabase");
        if (dbClass) {
            const lp = findMethodByParamCount(dbClass, "LoadPlaybook", 2);
            if (lp) {
                loadPlaybook = { info: lp.info, ptr: lp.ptr };
                Interceptor.attach(lp.ptr, {
                    onEnter(args) { capturedDb = args[0]; },
                });
            } else {
                log("[ability-prefs] LoadPlaybook(2 params) introuvable");
            }
        } else {
            log("[ability-prefs] classe PlaybookDatabase introuvable");
        }
    } catch (e) {
        log("[ability-prefs] arm failed: " + e);
    }

    /** Tier de préférence (`playbook.get_Preference()`) par ability. Requiert une
     * PlaybookDatabase capturée (une décision AI l'amorce ; ré-armée à chaque LoadPlaybook).
     * LECTURE SEULE. args: `{ abilities: number[] }`. Renvoie
     * `{ ok, db, preferences: { <ability>: { preference, playbookClass, error? } } }`. */
    ctx.rpc.abilityPreferences = (a: { abilities?: number[] }) => {
        if (capturedDb === null || loadPlaybook === null) {
            return {
                ok: false,
                error: "no live PlaybookDatabase captured — lance une décision AI (aiStepDryRun) d'abord",
            };
        }
        const abilities = (a && a.abilities) || [];
        if (!abilities.length) return { ok: false, error: "pass { abilities: [ids] }" };
        // `exceptions: "propagate"` -- on appelle du MANAGE : sans lui, Frida confisque
        // l'exception C++ par laquelle IL2CPP la transporte, et les `try/catch` DU JEU en
        // amont ne jouent pas. Le pourquoi complet est au foyer, `il2cpp/invoke.ts`.
        const loadFn = new NativeFunction(
            loadPlaybook.ptr, "pointer", ["pointer", "int32", "int32", "pointer"],
            { exceptions: "propagate" });
        // Le getter de tier = `get_Priority` (confirmé live gqfc5mff6c). Les autres = fallback.
        const PREF_NAMES = [
            "get_Priority", "get_Preference", "get_PlaybookPreference", "get_ActionPriority",
        ];
        const out: Record<string, unknown> = {};
        for (const ab of abilities) {
            const rec: {
                preference: number | null; playbookClass: string | null;
                prefMethod?: string; candidates?: string[]; error?: string;
            } = { preference: null, playbookClass: null };
            try {
                const pb = loadFn(capturedDb, ab, 1, loadPlaybook.info) as NativePointer;
                if (pb.isNull()) { rec.error = "no playbook (builder absent)"; out[ab] = rec; continue; }
                const pbClass = pb.readPointer();
                rec.playbookClass = cstr(class_get_name(pbClass) as NativePointer);
                const g = findGetter(pbClass, PREF_NAMES);
                if (!g) {
                    // Diagnostic : quels getters "pref"/"prior"/"order" existent ?
                    rec.candidates = [
                        ...methodsMatching(pbClass, "pref"),
                        ...methodsMatching(pbClass, "prior"),
                        ...methodsMatching(pbClass, "order"),
                    ];
                    rec.error = "no known preference getter";
                    out[ab] = rec; continue;
                }
                rec.prefMethod = g.name;
                // `propagate` : appel MANAGE, cf. `il2cpp/invoke.ts`.
                const gpFn = new NativeFunction(g.ref.ptr, "int32", ["pointer", "pointer"],
                                                { exceptions: "propagate" });
                rec.preference = gpFn(pb, g.ref.info) as number;
            } catch (e) {
                rec.error = String(e);
            }
            out[ab] = rec;
        }
        return { ok: true, db: capturedDb.toString(), preferences: out };
    };
}
