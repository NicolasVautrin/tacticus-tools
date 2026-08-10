// ui-scroll — FAIRE DEFILER, parce que sans ça on lit la moitie d'un ecran en croyant l'avoir lu.
//
// LE PROBLEME, MESURE TROIS FOIS. Les listes du jeu sont VIRTUALISEES : `uiList` n'enumere que
// les widgets ACTIFS, et un widget hors viewport est parque sous `WidgetPool(Clone)` -- absent,
// ou present avec une donnee liee MORTE. Consequences relevees le 2026-08-10 :
//
//   - plateau d'Operations : 4 lignes vues sur 7 (les trois autres n'existaient nulle part) ;
//   - `button_dispatch` : 7 exemplaires, 3 parques, UN SEUL qui ouvre ;
//   - menu Play : aucun `CrusadeGameModeButton` -- l'entree Crusade est ailleurs, mais on ne
//     pouvait pas le SAVOIR sans pouvoir dérouler la liste.
//
// Chaque fois, le contournement a marche (lire le modele plutot que l'ecran) et chaque fois il
// etait SPECIFIQUE. Le defaut de fond reste : un ecran a liste n'est pas lisible, et un compte
// partiel ne se distingue pas d'un compte complet.
//
// CE QU'ON POSE ICI, ET CE QU'ON NE POSE PAS. Deux RPC minces sur `UnityEngine.UI.ScrollRect` :
// enumerer les zones defilables, et poser leur position normalisee. Le BALAYAGE (parcourir la
// plage et unir ce qu'on voit) est DELIBEREMENT laisse a l'appelant :
//
//   la virtualisation ne se reconstruit pas dans la frame ou l'on pose la position. Un balayage
//   fait ici tiendrait le main thread pendant toute sa duree -- or `UnityFreezeDetector` est
//   hooke pour le pump, et un main thread tenu trop longtemps fait TUER le process. Cote
//   appelant, chaque palier est un RPC distinct : les frames passent entre deux, la liste se
//   reconstruit, et rien ne fige.
//
// `scripts/python/ui_scroll.py` porte le balayage.
//
// LECTURE + POSITION D'UNE VUE. Aucun clic, aucune depense, aucun envoi : deplacer une barre de
// defilement ne valide rien.

import { ensureRefs, getPath, UiRefs } from "./ui-nav.js";
import {
    findClassAnywhere, methodEntry, class_get_methods,
    method_get_name, method_get_param_count, s as cstr, getSystemType, MethodRef,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

interface ScrollRefs {
    scrollSystemType: NativePointer;
    getV: MethodRef | null;
    setV: MethodRef | null;
    getH: MethodRef | null;
    setH: MethodRef | null;
    axeV: MethodRef | null;
    axeH: MethodRef | null;
    stop: MethodRef | null;
}

let _sr: ScrollRefs | null = null;

function parAriteM(klass: NativePointer, nom: string, arite: number): MethodRef | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        if (cstr(method_get_name(m) as NativePointer) !== nom) continue;
        try {
            if ((method_get_param_count(m) as number) === arite) {
                return { info: m, ptr: methodEntry(m) };
            }
        } catch { /* suivante */ }
    }
    return null;
}

function refsScroll(): ScrollRefs | null {
    if (_sr) return _sr;
    const k = findClassAnywhere("UnityEngine.UI", "ScrollRect");
    if (!k) return null;
    const t = getSystemType(k);
    if (!t || t.isNull()) return null;
    _sr = {
        scrollSystemType: t,
        getV: parAriteM(k, "get_verticalNormalizedPosition", 0),
        setV: parAriteM(k, "set_verticalNormalizedPosition", 1),
        getH: parAriteM(k, "get_horizontalNormalizedPosition", 0),
        setH: parAriteM(k, "set_horizontalNormalizedPosition", 1),
        axeV: parAriteM(k, "get_vertical", 0),
        axeH: parAriteM(k, "get_horizontal", 0),
        stop: parAriteM(k, "StopMovement", 0),
    };
    return _sr;
}

/** `System.Single` rendu par `runtime_invoke` : BOXE, valeur utile a +0x10. */
function floatBoxe(p: NativePointer): number | null {
    if (p.isNull()) return null;
    try { return p.add(0x10).readFloat(); } catch { return null; }
}

function boolBoxe(p: NativePointer): boolean | null {
    if (p.isNull()) return null;
    try { return p.add(0x10).readU8() !== 0; } catch { return null; }
}

interface Vue {
    path: string;
    ptr: string;
    /** Position normalisee. `null` = NON LUE, jamais rabattue sur 0 -- 0 est le BAS de la
     *  liste, donc un `null` pris pour 0 se lirait << deja au bout >>. */
    v: number | null;
    h: number | null;
    axeV: boolean | null;
    axeH: boolean | null;
    actif: boolean | null;
}

function enumererVues(r: UiRefs, sr: ScrollRefs, inclureInactifs: boolean): Vue[] {
    const sortMode = Memory.alloc(4).writeS32(0);
    let arr: NativePointer;
    if (inclureInactifs && r.findObjectsByTypeInactifs) {
        const inact = Memory.alloc(4).writeS32(1);
        arr = invokeMethod(r.findObjectsByTypeInactifs.info, null,
                           [sr.scrollSystemType, inact, sortMode]);
    } else {
        arr = invokeMethod(r.findObjectsByType.info, null, [sr.scrollSystemType, sortMode]);
    }
    if (arr.isNull()) return [];
    const len = arr.add(0x18).readS32();
    if (len <= 0 || len > 100000) return [];

    const out: Vue[] = [];
    for (let i = 0; i < len; i++) {
        const sc = arr.add(0x20 + i * Process.pointerSize).readPointer();
        if (sc.isNull()) continue;
        let actif: boolean | null = null;
        try { actif = boolBoxe(invokeMethod(r.behaviourGetActiveAndEnabled.info, sc, [])); }
        catch { actif = null; }
        const lireF = (m: MethodRef | null): number | null => {
            if (!m) return null;
            try { return floatBoxe(invokeMethod(m.info, sc, [])); } catch { return null; }
        };
        const lireB = (m: MethodRef | null): boolean | null => {
            if (!m) return null;
            try { return boolBoxe(invokeMethod(m.info, sc, [])); } catch { return null; }
        };
        out.push({
            path: getPath(r, sc), ptr: sc.toString(),
            v: lireF(sr.getV), h: lireF(sr.getH),
            axeV: lireB(sr.axeV), axeH: lireB(sr.axeH),
            actif,
        });
    }
    return out;
}

function choisir(vues: Vue[], body?: { path?: string; ptr?: string; index?: number }) {
    if (body?.ptr) {
        const c = vues.filter((x) => x.ptr === body.ptr);
        return { candidats: c, choisi: c[0] ?? null };
    }
    const c = body?.path ? vues.filter((x) => x.path === body.path) : vues;
    const i = body?.index ?? 0;
    return { candidats: c, choisi: c[i] ?? null };
}

export function register(ctx: Ctx): void {
    /** Enumere les zones defilables. body: { inclureInactifs?, actifsSeuls? } */
    ctx.rpc.uiScrollList = (body?: {
        inclureInactifs?: boolean; actifsSeuls?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        const sr = refsScroll();
        if (!sr) return { ok: false, err: "UnityEngine.UI.ScrollRect introuvable" };
        const r = ensureRefs();
        let vues = enumererVues(r, sr, !!body?.inclureInactifs);
        if (body?.actifsSeuls) vues = vues.filter((x) => x.actif !== false);
        return {
            ok: true, count: vues.length, vues,
            // Ce que le module NE SAIT PAS dire, et le dit : si le contenu deborde
            // reellement de sa fenetre. Le savoir exigerait de comparer deux `Rect`, que
            // `runtime_invoke` rend par valeur -- non fait. Le balayage le CONSTATE plutot
            // qu'il ne le predit : si l'union des boutons ne bouge pas, il n'y avait rien.
            debordement: null,
            layout: {
                get_verticalNormalizedPosition: !!sr.getV,
                set_verticalNormalizedPosition: !!sr.setV,
                get_horizontalNormalizedPosition: !!sr.getH,
                set_horizontalNormalizedPosition: !!sr.setH,
                StopMovement: !!sr.stop,
            },
        };
    });

    /** Pose la position normalisee d'une zone defilable.
     *
     *  `v`/`h` dans [0,1] -- et `1` est le HAUT d'une liste verticale (convention uGUI),
     *  `0` le bas. Une valeur hors bornes est REFUSEE, pas clampee : un clamp silencieux
     *  ferait passer une erreur d'appelant pour un deplacement reussi.
     *
     *  body: { path?|ptr?, index?, v?, h? } */
    ctx.rpc.uiScrollSet = (body?: {
        path?: string; ptr?: string; index?: number; v?: number; h?: number;
    }): Promise<unknown> => queueOnMainThread(() => {
        const sr = refsScroll();
        if (!sr) return { ok: false, err: "UnityEngine.UI.ScrollRect introuvable" };
        if (body?.v === undefined && body?.h === undefined) {
            return { ok: false, err: "uiScrollSet: `v` et/ou `h` requis (dans [0,1])" };
        }
        for (const [nom, val] of [["v", body?.v], ["h", body?.h]] as Array<[string, number?]>) {
            if (val !== undefined && (typeof val !== "number" || !(val >= 0 && val <= 1))) {
                return { ok: false, err: "uiScrollSet: `" + nom + "` hors [0,1] : "
                                       + String(val) };
            }
        }
        const r = ensureRefs();
        const vues = enumererVues(r, sr, false);
        const { candidats, choisi } = choisir(vues, body);
        if (!choisi) {
            return {
                ok: false, matches: candidats.length, count: vues.length,
                err: candidats.length
                    ? "index " + String(body?.index) + " hors des " + candidats.length
                      + " candidats"
                    : "aucune zone defilable pour ce path/ptr -- `uiScrollList` d'abord",
            };
        }
        const sc = ptr(choisi.ptr);
        // On tue l'inertie AVANT de poser : un `ScrollRect` en cours de deceleration
        // repartirait de lui-meme et la position posee ne tiendrait pas.
        if (sr.stop) { try { invokeMethod(sr.stop.info, sc, []); } catch { /* avale */ } }
        const poser = (m: MethodRef | null, val: number | undefined): string | null => {
            if (val === undefined) return null;
            if (!m) return "setter NON RESOLU";
            try {
                const a = Memory.alloc(4);
                a.writeFloat(val);
                invokeMethod(m.info, sc, [a]);
                return null;
            } catch (e) { return String((e as Error).message || e).slice(0, 120); }
        };
        const errV = poser(sr.setV, body?.v);
        const errH = poser(sr.setH, body?.h);
        // On RELIT : le `ScrollRect` peut refuser (axe desactive, contenu plus petit que la
        // fenetre). Rendre la valeur demandee ferait croire au deplacement.
        const relire = (m: MethodRef | null): number | null => {
            if (!m) return null;
            try { return floatBoxe(invokeMethod(m.info, sc, [])); } catch { return null; }
        };
        return {
            ok: !errV && !errH,
            path: choisi.path, ptr: choisi.ptr, matches: candidats.length,
            demande: { v: body?.v ?? null, h: body?.h ?? null },
            avant: { v: choisi.v, h: choisi.h },
            apres: { v: relire(sr.getV), h: relire(sr.getH) },
            axeV: choisi.axeV, axeH: choisi.axeH,
            err: errV || errH || undefined,
            note: "`apres` peut EGALER `avant` sans faute : axe desactive, ou contenu qui "
                + "ne deborde pas. Compare les deux plutot que de supposer.",
        };
    });
}
