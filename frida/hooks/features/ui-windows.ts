// QUELLE VUE EST DEVANT — lu dans le gestionnaire de fenêtres DU JEU, pas déduit de l'arbre.
//
// POURQUOI CE MODULE EXISTE
// -------------------------
// `uiList` énumère les `Button` par `Object.FindObjectsByType` : une liste PLATE, sans aucun
// ordre de rendu (`FindObjectsByType` ne garantit même pas son ordre d'énumération). Côté
// Python, `gamenav/vue.py` en déduit les popups par le NOM du prefab — ça dit LESQUELS sont
// montés, jamais LEQUEL est devant. Mesure du 2026-08-09 : avec un `InterstitialPopup`
// d'offres en travers de tout l'écran, `identifier()` rendait `TRANSITOIRE`, et un appelant
// a conclu « le bouton de campagne a disparu ».
//
// Or le jeu tient son PROPRE gestionnaire de fenêtres, et il a déjà fait le calcul :
//
//     thor.Menu.MenuSystems                      ~230 slots `IMenu<T>` NOMMÉS, un par vue
//       <VisibilityManager>k__BackingField    -> idun.ui.ScreenVisibilityManager
//            _screenVisibilities                 la PILE (List<idun.ui.ScreenVisibility>)
//            _lastScreenRendered                 le dernier écran RENDU, en String
//       _hideableMenus                           ce qui peut être masqué
//       _blurredBackgroundManager                le fond flouté = signal MODAL
//
// `MenuSystems` porte un `Update()` : c'est un MonoBehaviour, donc `FindObjectsByType` le
// trouve — aucune dépendance au FSM, aucune bataille requise. C'est ce qui rend ce module
// petit là où la traversée `_actions._hud._menuSystems` aurait exigé une bataille en cours.
//
// LA CLÉ EST UN ENUM, ET C'EST CE QUI REND LA SORTIE LISIBLE
// -----------------------------------------------------------
// Chaque `ScreenVisibility` porte `<GuiId>k__BackingField` : un `idun.tracking.GuiId`, ~250
// membres qui nomment CHAQUE vue du jeu — `34=PauseMenu`, `70=InterstitialPopup`,
// `46=GenericMessagePopup`, `25=BattlePreviewPopup`, `21=UnitDeploymentHud`, `13=GameHud`.
// Publier l'ordinal nu serait la faute que le dépôt documente partout : juste aujourd'hui,
// faux en silence au prochain build. On publie donc le MEMBRE.
//
// ⚠ ET LES NOMS DE MEMBRES SE RÉSOLVENT DEPUIS LA CLASSE DU CHAMP, JAMAIS PAR SON NOM.
// `_state` est de type `idun.ui.ScreenVisibility.State` — pour IL2CPP il s'appelle juste
// `State`, dans le namespace `idun.ui`. Un `findClassAnywhere("idun.ui", "State")`
// attraperait n'importe quel `State` du namespace et publierait des membres FAUX sans lever.
// D'où `dumpEnumClass(klass)` : on part du champ, sa classe de type EST la réponse.
//
// ⚠ CE QUE `_lastScreenRendered` DIT, ET CE QU'IL NE DIT PAS. C'est le dernier écran RENDU
// (`ScreenVisibilityManager$$SetLastScreenRendered`, appelé par `RenderScreenIfNotObstructed`)
// — l'axe du RENDU, pas celui du RAYCAST. Tant qu'il n'a pas été confronté à un empilement
// connu (Pause + confirmation de retraite), le lire comme « ce que mon clic va toucher »
// serait une extrapolation. On le publie brut et on ne conclut rien.
//
// ⚠ LES SLOTS DE MENU SONT LISTÉS, JAMAIS APPELÉS. `IMenu<T>.Get()` est un GET-OR-CREATE
// (`MenuSystems$$CreateMenu<T>`, `$$InitialiseMenu<T>`, `$$UnloadLeastRecentlyOpenedMenus`) :
// l'appeler sur 230 slots chargerait toutes les fenêtres du jeu. C'est le même piège que
// `UnitDeployment_TryPlaceUnitOnBoard`, le « getter » qui MARQUE. Ce module rend les NOMS de
// slots et la nullité du pointeur ; ouvrir un menu reste un geste explicite de l'appelant.

import {
    class_get_fields, class_get_name, field_get_name, field_get_offset, field_get_type,
    findClassAnywhere, getSystemType, readIl2cppString, s as cstr,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { dumpEnumClass } from "../il2cpp/enum-dump.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { ensureRefs } from "./ui-nav.js";
import { Ctx } from "../controller.js";

/** Garde-fou d'itération : une `List<T>` de taille aberrante signale un pointeur mal résolu,
 *  pas une pile géante. On REFUSE plutôt que de balayer la mémoire. */
const PLAFOND_LISTE = 4096;

interface Champ { nom: string; offset: number; typeKlass: NativePointer | null }

/** Le champ NOMMÉ d'une classe : son offset ET la classe de son type. Rend `null` quand le
 *  champ n'existe pas dans CE build — l'appelant doit le DIRE, pas lire à l'offset 0. */
function champ(klass: NativePointer, nom: string): Champ | null {
    let k = klass;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(k, it) as NativePointer).isNull()) {
            if (cstr(field_get_name(f) as NativePointer) !== nom) continue;
            let tk: NativePointer | null = null;
            try {
                tk = type_get_class_or_element_class(
                    field_get_type(f) as NativePointer) as NativePointer;
                if (tk.isNull()) tk = null;
            } catch { tk = null; }
            return { nom, offset: field_get_offset(f) as number, typeKlass: tk };
        }
        // `class_get_parent` n'est pas importé ici : les champs visés sont tous DÉCLARÉS par
        // la classe elle-même (mesuré par `classFields`). Remonter la hiérarchie ferait
        // porter au module une dette qu'il n'a pas.
        break;
    }
    return null;
}

function lirePointeur(obj: NativePointer, c: Champ | null): NativePointer | null {
    if (c === null || obj.isNull()) return null;
    try {
        const p = obj.add(c.offset).readPointer();
        return p.isNull() ? null : p;
    } catch { return null; }
}

function lireInt(obj: NativePointer, c: Champ | null): number | null {
    if (c === null || obj.isNull()) return null;
    try { return obj.add(c.offset).readS32(); } catch { return null; }
}

/** ordinal -> membre, construit UNE fois par classe d'enum. `null` = enum non dumpable :
 *  l'appelant publie alors l'ordinal SEUL, il ne fabrique pas un nom. */
function tableEnum(k: NativePointer | null): Record<number, string> | null {
    if (k === null) return null;
    const brut = dumpEnumClass(k);
    if (!brut) return null;
    const out: Record<number, string> = {};
    for (const [nom, val] of Object.entries(brut)) {
        const n = parseInt(val, 10);
        if (!Number.isNaN(n) && out[n] === undefined) out[n] = nom;
    }
    return out;
}

/** L'ordinal ET son membre. Le membre vaut `null` quand la table manque — jamais une
 *  invention, jamais l'ordinal déguisé en nom. */
function membre(
    v: number | null, t: Record<number, string> | null,
): { v: number | null; nom: string | null } {
    if (v === null) return { v: null, nom: null };
    return { v, nom: t ? (t[v] ?? null) : null };
}

/** Les éléments d'une `List<T>` IL2CPP (`_items` @+0x10, `_size` @+0x18, données @+0x20).
 *  `null` = PAS LU (liste absente ou taille aberrante), jamais `[]` : un tableau vide se
 *  lirait comme « la pile est vide », ce qui est une mesure, pas une panne. */
function elementsDeListe(liste: NativePointer | null): NativePointer[] | null {
    if (liste === null) return null;
    try {
        const taille = liste.add(0x18).readS32();
        if (taille < 0 || taille > PLAFOND_LISTE) return null;
        const items = liste.add(0x10).readPointer();
        if (items.isNull()) return taille === 0 ? [] : null;
        const out: NativePointer[] = [];
        for (let i = 0; i < taille; i++) {
            out.push(items.add(0x20 + i * Process.pointerSize).readPointer());
        }
        return out;
    } catch { return null; }
}

/** Les slots `IMenu<T>` de `MenuSystems`, par NOM. On ne lit que la nullité du pointeur —
 *  cf. l'avertissement GET-OR-CREATE de l'en-tête. */
function slotsDeMenus(
    klass: NativePointer, ms: NativePointer,
): Array<{ nom: string; monte: boolean }> {
    const out: Array<{ nom: string; monte: boolean }> = [];
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        let tn = "";
        try {
            const tk = type_get_class_or_element_class(
                field_get_type(f) as NativePointer) as NativePointer;
            tn = tk.isNull() ? "" : cstr(class_get_name(tk) as NativePointer);
        } catch { continue; }
        // `IMenu\`1`, `IExternalMenu\`1`, `IAsyncMenu\`1`, `Menu\`1` — la marque est le
        // suffixe generique, pas un prefixe : les quatre coexistent dans la meme classe.
        if (!/^(I)?(External|Async)?Menu`1$/.test(tn)) continue;
        const nom = cstr(field_get_name(f) as NativePointer);
        const off = field_get_offset(f) as number;
        let monte = false;
        try { monte = !ms.add(off).readPointer().isNull(); } catch { /* */ }
        out.push({ nom, monte });
    }
    return out;
}

export function register(ctx: Ctx): void {
    /** Le gestionnaire de fenêtres DU JEU, tel quel. Read-only, n'ouvre et ne clique rien.
     *
     *  body: { menus?: true }  -> inclut la liste des ~230 slots (verbeux, hors défaut)
     *
     *  TRI-ÉTAT partout : `null` = PAS MESURÉ (champ absent de ce build, liste illisible),
     *  jamais rabattu sur vide/0/faux. `champsAbsents` dit LESQUELS, pour qu'un `null` se
     *  lise comme une péremption et non comme un état du jeu.
     */
    ctx.rpc.uiWindows = (body?: { menus?: boolean }): Promise<unknown> =>
        queueOnMainThread(() => {
            const klass = findClassAnywhere("thor.Menu", "MenuSystems");
            if (!klass) {
                return { ok: false, error: "classe thor.Menu.MenuSystems introuvable -- "
                    + "gestionnaire de fenetres renomme, ou build change" };
            }

            // MÊME service que `uiList` (`Object.FindObjectsByType`), résolu une seule fois
            // dans `ui-nav.ensureRefs` — pas une seconde résolution qui pourrait diverger.
            const r = ensureRefs();
            const sortMode = Memory.alloc(4).writeS32(0);
            const arr = invokeMethod(
                r.findObjectsByType.info, null, [getSystemType(klass), sortMode]);
            const n = arr.isNull() ? 0 : arr.add(0x18).readS32();
            if (n <= 0) {
                return { ok: false, instances: 0, error: "aucun MenuSystems vivant -- "
                    + "l'UI n'est pas montee (jeu en cours de chargement ?)" };
            }
            const ms = arr.add(0x20).readPointer();

            const absents: string[] = [];
            const exige = (k: NativePointer, nom: string): Champ | null => {
                const c = champ(k, nom);
                if (c === null) absents.push(nom);
                return c;
            };

            const cVis = exige(klass, "<VisibilityManager>k__BackingField");
            const cHide = exige(klass, "_hideableMenus");
            const cFlou = exige(klass, "_blurredBackgroundManager");

            const vis = lirePointeur(ms, cVis);
            let devant: string | null = null;
            let pile: unknown[] | null = null;

            if (vis !== null) {
                const kVis = vis.readPointer();
                const cDernier = exige(kVis, "_lastScreenRendered");
                const cPile = exige(kVis, "_screenVisibilities");
                const sDernier = lirePointeur(vis, cDernier);
                devant = sDernier === null ? null : readIl2cppString(sDernier);

                const els = elementsDeListe(lirePointeur(vis, cPile));
                if (els === null) {
                    pile = null;
                } else if (els.length === 0) {
                    pile = [];
                } else {
                    // Les champs se résolvent sur la classe du PREMIER élément, une fois —
                    // pas par élément : ils sont tous du même type.
                    const kSv = els[0].isNull()
                        ? null : els[0].readPointer();
                    const cGui = kSv ? champ(kSv, "<GuiId>k__BackingField") : null;
                    const cEtat = kSv ? champ(kSv, "_state") : null;
                    const cRendu = kSv ? champ(kSv, "<RenderStatus>k__BackingField") : null;
                    const cOverlay = kSv ? champ(kSv, "OverlayType") : null;
                    const cCanvas = kSv ? champ(kSv, "Canvas") : null;
                    const cRay = kSv ? champ(kSv, "Raycaster") : null;
                    for (const [nom, c] of [
                        ["<GuiId>k__BackingField", cGui], ["_state", cEtat],
                        ["<RenderStatus>k__BackingField", cRendu],
                        ["OverlayType", cOverlay],
                    ] as Array<[string, Champ | null]>) {
                        if (c === null) absents.push(nom);
                    }
                    const tGui = tableEnum(cGui?.typeKlass ?? null);
                    const tEtat = tableEnum(cEtat?.typeKlass ?? null);
                    const tRendu = tableEnum(cRendu?.typeKlass ?? null);
                    const tOverlay = tableEnum(cOverlay?.typeKlass ?? null);

                    pile = els.map((e, i) => ({
                        i,
                        // L'ORDRE EST CELUI DU JEU (`_screenVisibilities`), pas un tri de
                        // notre fait : `ScreenVisibilityManager$$CompareHideables` est SA
                        // fonction de classement, et la reproduire ici serait un fork.
                        gui: membre(lireInt(e, cGui), tGui),
                        etat: membre(lireInt(e, cEtat), tEtat),
                        rendu: membre(lireInt(e, cRendu), tRendu),
                        overlay: membre(lireInt(e, cOverlay), tOverlay),
                        aCanvas: cCanvas === null ? null : lirePointeur(e, cCanvas) !== null,
                        aRaycaster: cRay === null ? null : lirePointeur(e, cRay) !== null,
                    }));
                }
            }

            const hide = elementsDeListe(lirePointeur(ms, cHide));

            return {
                ok: true,
                instances: n,
                devant,
                pile,
                hideables: hide === null ? null : hide.length,
                fondFloute: cFlou === null ? null : lirePointeur(ms, cFlou) !== null,
                champsAbsents: absents,
                menus: body?.menus ? slotsDeMenus(klass, ms) : undefined,
            };
        });
}
