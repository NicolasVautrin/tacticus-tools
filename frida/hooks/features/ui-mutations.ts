// ui-mutations — LE point d'interception UNIQUE des mutations d'interface, un cran SOUS l'écran.
//
// POURQUOI, ET CE QUE `uiWindowEvents` NE COUVRE PAS. Le journal de `ui-windows.ts` est ancré
// sur `idun.ui.ScreenVisibilityManager` : sa granularité est l'ÉCRAN. Mesuré le 2026-08-10,
// avec témoin positif — cliquer le nœud de campagne 6 (qui ouvre) rend **4** transitions
// (`montre-debut`/`montre-fin` de `BattlePreviewPopup`) ; cliquer le nœud 2 (un nœud de
// TUTORIEL, qui REFUSE en affichant quelque chose) en rend **0**. Le refus se joue donc sous
// la couche écran, et aucun ancrage de cette couche ne peut le voir.
//
// Et l'énumération par TYPE ne le voit pas non plus : photographié avant/après ce même clic,
// par multiplicité, `uiListAll` rend 48 -> 48 boutons actifs et 455 -> 455 inactifs compris —
// **0 apparu, 0 disparu**. Ce qui s'affiche ne porte AUCUN `UnityEngine.UI.Button`. Courir
// après les types un par un (`Button`, puis `TMP_Text`, puis `Image`...) est une course sans
// fin ; `UnityEngine.GameObject$$SetActive` est le goulot par lequel TOUT affichage passe,
// quel que soit le composant.
//
// ⚠ CE N'EST PAS UN CHEMIN FROID, et le `CLAUDE.md` proscrit les hooks larges sur l'UI chaude
// (c'est ce qui a déjà déstabilisé le jeu). Trois brides, toutes nécessaires :
//   1. JAMAIS auto-armé — `register` ne pose rien, seul `{start:true}` installe.
//   2. FENÊTRÉ — on arme, on fait UNE action, on lit, on `{stop:true}`.
//   3. PLAFONNÉ — au-delà de `PLAFOND` on cesse d'enregistrer et on COMPTE (`ecartes`),
//      plutôt que de grossir sans borne ou de tronquer en silence.
//
// ⚠ `stop` ARRÊTE D'ENREGISTRER, il ne DÉTACHE PAS — même raison que `uiWindowEvents` : un
// détachement partiel laisserait un journal muet qui se lirait « rien ne s'est passé ».
//
// ⚠ CE QUE CE POINT NE COUVRE PAS. Un widget CRÉÉ à la demande (instancié) plutôt que
// réactivé apparaît sans qu'aucun `SetActive(true)` ne soit appelé. Le jeu utilise un
// `idun.ui.widgetPool.IWidgetPool`, donc le recyclage — donc `SetActive` — est le cas
// attendu ; mais si le témoin ci-dessous reste muet sur le nœud 2, c'est l'hypothèse à lever,
// PAS une preuve que rien ne s'affiche.

import {
    findClassAnywhere, findMethod, class_get_methods, method_get_name,
    method_get_param_count, methodEntry, readIl2cppString, s as cstr, MethodRef,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

interface Mutation { n: number; actif: boolean; nom: string | null }

const journal: Mutation[] = [];
let recus = 0;
let ecartes = 0;
let actif = false;
let ancrages: number | null = null;   // null = hooks JAMAIS posés (≠ posés et 0 fire)
const PLAFOND = 800;

/** `UnityEngine.Object$$get_name`, résolu une fois. `GameObject` en hérite. */
let getNameMi: MethodRef | null | undefined;
function nomDe(go: NativePointer): string | null {
    if (getNameMi === undefined) {
        const k = findClassAnywhere("UnityEngine", "Object");
        getNameMi = k ? findMethod(k, "get_name") : null;
    }
    if (!getNameMi) return null;
    try { return readIl2cppString(invokeMethod(getNameMi.info, go, [])); }
    catch { return null; }
}

function noter(go: NativePointer, valeur: number): void {
    if (!actif) return;
    try {
        recus++;
        // Au-delà du plafond on COMPTE sans résoudre : `get_name` est un invoke, et c'est lui
        // qui coûte. Un compte qui n'égale pas la longueur du journal dit qu'on a perdu des
        // entrées, au lieu de laisser croire la liste complète.
        if (journal.length >= PLAFOND) { ecartes++; return; }
        journal.push({ n: recus, actif: valeur !== 0, nom: nomDe(go) });
    } catch { /* un capteur ne jette jamais */ }
}

/** Attache TOUTES les surcharges à 1 paramètre — on ne présuppose pas qu'il n'y en a qu'une. */
function installer(): number | null {
    const klass = findClassAnywhere("UnityEngine", "GameObject");
    if (!klass) return null;
    let poses = 0;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let mi: NativePointer;
    while (!(mi = class_get_methods(klass, it) as NativePointer).isNull()) {
        if (cstr(method_get_name(mi) as NativePointer) !== "SetActive") continue;
        if ((method_get_param_count(mi) as number) !== 1) continue;
        try {
            const p = methodEntry(mi);
            if (p === null || p.isNull()) continue;
            Interceptor.attach(p, {
                onEnter(args) { noter(args[0], args[1].toInt32()); },
            });
            poses++;
        } catch { /* une ancre qui echoue ne doit pas emporter les autres */ }
    }
    Interceptor.flush();
    return poses;
}

export function register(ctx: Ctx): void {
    /** body: { start?, stop?, clear?, depuis?: number, max?: number }
     *
     *  `depuis = recus` du relevé précédent rend exactement les nouvelles entrées — à
     *  condition qu'`ecartes` n'ait pas bougé, ce que la réponse publie aussi.
     *
     *  ⚠ `ancrages: null` = hooks JAMAIS POSÉS. À ne pas confondre avec `ancrages: 1` et zéro
     *  mutation : le premier est une panne, le second une mesure. */
    ctx.rpc.uiMutations = (body?: {
        start?: boolean; stop?: boolean; clear?: boolean;
        depuis?: number; max?: number;
    }): unknown => {
        if (body?.stop) actif = false;
        if (body?.start) {
            if (ancrages === null) ancrages = installer();
            if (ancrages === null) {
                return { ok: false, ancrages: null,
                    error: "UnityEngine.GameObject introuvable -- rien n'a ete ancre" };
            }
            actif = true;
            log("[ui-mutations] arme : " + ancrages + " ancrage(s) sur GameObject.SetActive");
        }
        if (body?.clear) { journal.length = 0; recus = 0; ecartes = 0; }

        const depuis = typeof body?.depuis === "number" ? body.depuis : 0;
        const max = typeof body?.max === "number" ? body.max : 200;
        const filtrees = journal.filter((m) => m.n > depuis);
        return {
            ok: true, actif, ancrages,
            recus, ecartes, plafond: PLAFOND,
            enTampon: journal.length,
            rendus: Math.min(filtrees.length, max),
            mutations: filtrees.slice(0, max),
        };
    };
}
