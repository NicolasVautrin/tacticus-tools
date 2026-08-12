// #991 — OBSERVER `StartCampaignMatch` AVANT d'y toucher, et MESURER si son `this` est joignable.
//
// LA QUESTION. Le cycle de warmup (`features/warmup-singletons.ts`) pilote l'UI pour lancer une
// bataille : `to-campaign` -> `click-node` -> `click-play`. Ces trois etapes ont un seul effet
// utile, appeler
// `idun.shared.commands.ViewCommandExecutor$$StartCampaignMatch(campaignId, locationIndex,
// campaignType, enemyIsAiControlled)`. Si on savait appeler cette methode directement, la moitie
// fragile du cycle disparaitrait -- celle des clics AVALES (#332), des repos de 800 ms et d'un
// noeud dont le chemin change a chaque run.
//
// ⚠ CE MODULE N'INVOQUE RIEN, ET C'EST LE POINT. `StartCampaignMatch` ECRIT : elle lance une
// vraie bataille (`StartMatch` -> `thor.Loader$$LoadBattle`). Le fait qu'on produise deja cette
// mutation par l'UI a chaque warmup n'autorise pas a INVENTER quatre arguments et regarder ce que
// ca donne -- c'est exactement le geste qui a rendu `ok:true` puis tue le jeu ailleurs. On
// OBSERVE d'abord ce que l'UI passe REELLEMENT, et un eventuel invoke, plus tard, REJOUERA des
// valeurs VUES.
//
// CE QUE LE DECOMPILE ETABLIT DEJA (build `rnca9r7q6c`, aucun live requis) :
//
//   - `idun.shared.commands.ViewCommandExecutor` a pour parent `System.Object` -- ce N'EST PAS un
//     MonoBehaviour. `Object.FindObjectsByType` ne le trouvera JAMAIS. C'est le meme piege que
//     `thor.Menu.MenuSystems` (cf. l'en-tete de `features/ui-windows.ts` : un `Update()` ne prouve
//     pas l'heritage ; `m_CachedPtr`, si). `reach()` ci-dessous le MESURE au lieu de le supposer.
//   - Le seul accesseur publie est `thor.Menu.MenuSystems$$get_ViewCommandExecutor`, et
//     `MenuSystems` est justement la classe mesuree NON enumerable.
//   - MAIS `idun.UI.IdunNavigation$$Init` prend `viewCommandExecutor` en PREMIER parametre et le
//     RANGE dans un champ de `this` (lu au decompile : `*(this + 0x248) = *(deps + 0x18)`), et
//     `IdunNavigation` EST joignable -- le depot la resout deja (`features/auto-boot.ts`,
//     `features/warmup-singletons.ts`). Mesure live du 2026-08-12 par le RPC `classFields` :
//     `_viewCommandExecutor` / offset `0x248` / type `IViewCommandExecutor`, et `_menuSystems`
//     a `0x228`. L'offset n'est PAS ecrit ici : on resout par NOM (`getFieldOffset`), parce que
//     `auto-boot.ts` documente un `_unitProgression` qui a bouge `0x1F0 -> 0x1D8` entre deux
//     builds.
//
// CE QUE LE DECOMPILE ETABLIT SUR LES PRECONDITIONS -- et que `reach()` ne peut pas mesurer :
// l'appelant UI est `ShowCampaignBattlePreviewPopupCommand$$OnPlayBattleTapped`, qui evalue DEUX
// tests sur `ICampaignProgression` avant l'appel (slots d'interface `0x21` puis `0x23`, tous deux
// `(locationIndex) -> bool`, soit `IsLocationReached` et `HasStaminaToPlayCampaignBattle` --
// les deux seules methodes de ce profil sur `IdunMetaLogic.UserProgress.CampaignProgression`).
// Le second echoue vers `NotEnoughResources_campaignBattleTokens_Description`, ce qui le NOMME.
// Un invoke direct court-circuite les deux. En revanche
// `ShowCampaignBattlePreviewPopupCommand$$LoadCampaignMatch` -- l'autre appelant, celui du retour
// de raid -- n'en evalue AUCUN : le jeu lui-meme atteint donc `StartCampaignMatch` sans garde.
//
// LE JOURNAL EST BORNE ET PASSIF : `Interceptor.attach` sur `onEnter`, aucune ecriture, aucun
// `Interceptor.replace`. Il ne s'arme pas tout seul -- `startCampaignMatchCaptureArm` est un
// geste explicite de l'appelant, comme `modifier-observe`.

import {
    findClassAnywhere, findMethodByParamCount, class_get_name, class_get_fields,
    class_get_parent, field_get_name, getFieldOffset, getSystemType, methodParamClass,
    readIl2cppString, s as cstr, MethodRef,
} from "../il2cpp/helpers.js";
import { dumpEnumClass } from "../il2cpp/enum-dump.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

/** Combien d'appels garder. Un warmup en produit UN ; 32 couvre plusieurs cycles sans peser. */
const CAP = 32;

interface Capture {
    /** L'instance de `ViewCommandExecutor` que l'UI a utilisee -- LA valeur qui repond a la
     *  question 1 sans aucune deduction : si `reach()` rend le meme pointeur, le chemin de
     *  champs est CONFIRME par confrontation, pas par lecture de decompile. */
    thisPtr: string;
    /** La classe CONCRETE derriere ce pointeur. `IViewCommandExecutor` a au moins deux
     *  implementations dans le binaire (`ViewCommandExecutor`, `idun.tests.TestViewCommandExecutor`)
     *  -- publier le nom evite de confondre celle qu'on tient avec celle qu'on croit tenir. */
    thisClass: string | null;
    campaignId: string | null;
    locationIndex: number;
    /** L'ordinal ET le membre NOMME. L'ordinal seul serait faux en silence au prochain build. */
    campaignType: number;
    campaignTypeName: string | null;
    /** `System.Nullable<System.Boolean>` -- DEUX octets passes PAR VALEUR dans le registre.
     *
     *  ⚠ ON NE TRANCHE PAS ICI, ET C'EST VOULU. `null` et `false` sont deux etats DIFFERENTS et
     *  le decompile de `StartCampaignMatch` montre qu'ils ne produisent pas le meme booleen : sur
     *  `HasValue == false` il ecrit `1` dans le champ passe au ctor de `CampaignGameModeSource`
     *  (donc l'absence de valeur ne vaut PAS `false`). Publier une seule lecture ferait disparaitre
     *  cette distinction. On rend donc les octets BRUTS plus les deux lectures possibles, et c'est
     *  la CAPTURE qui dira laquelle est la bonne -- pas une supposition sur l'ordre des champs de
     *  `Nullable<T>`.  */
    enemyIsAiControlledRaw: string;
    /** Lecture sous le layout `{ value; hasValue }` (ordre de declaration de `System.Nullable<T>`). */
    enemyIsAiControlledAsValueFirst: boolean | null;
    /** Lecture sous le layout `{ hasValue; value }`. */
    enemyIsAiControlledAsHasValueFirst: boolean | null;
    at: string;
}

let captures: Capture[] = [];
let listener: InvocationListener | null = null;
let cachedType: Record<string, string> | null = null;

/** Le membre NOMME d'un ordinal de `Idun.Shared.CampaignType`, resolu depuis la classe du
 *  PARAMETRE (jamais par `findClassAnywhere("Idun.Shared","CampaignType")` : plusieurs
 *  namespaces peuvent porter un type de ce nom, et on publierait des membres FAUX sans lever). */
function campaignTypeName(ordinal: number): string | null {
    if (!cachedType) return null;
    for (const [name, val] of Object.entries(cachedType)) {
        if (parseInt(val, 10) === ordinal) return name;
    }
    return null;
}

function classNameOf(objPtr: NativePointer): string | null {
    try {
        if (objPtr.isNull()) return null;
        const k = objPtr.readPointer();
        if (k.isNull()) return null;
        return cstr(class_get_name(k) as NativePointer);
    } catch { return null; }
}

function resolveTarget(): MethodRef | null {
    const klass = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
    if (!klass) return null;
    // 4 parametres : campaignId, locationIndex, campaignType, enemyIsAiControlled.
    const m = findMethodByParamCount(klass, "StartCampaignMatch", 4);
    if (!m) return null;
    if (!cachedType) {
        const tk = methodParamClass(m.info, 2);   // Idun.Shared.CampaignType
        if (tk) cachedType = dumpEnumClass(tk);
    }
    return m;
}

function arm(): { ok: boolean; err?: string; armed?: boolean } {
    if (listener) return { ok: true, armed: true };
    const m = resolveTarget();
    if (!m) {
        return { ok: false, err: "ViewCommandExecutor$$StartCampaignMatch(4) introuvable" };
    }
    try {
        listener = Interceptor.attach(m.ptr, {
            onEnter(args) {
                try {
                    const self = ptr(args[0].toString());
                    const raw = args[4].toUInt32() & 0xffff;
                    const b0 = raw & 0xff;
                    const b1 = (raw >> 8) & 0xff;
                    const ordinal = args[3].toInt32();
                    const c: Capture = {
                        thisPtr: self.toString(),
                        thisClass: classNameOf(self),
                        campaignId: readIl2cppString(ptr(args[1].toString())),
                        locationIndex: args[2].toInt32(),
                        campaignType: ordinal,
                        campaignTypeName: campaignTypeName(ordinal),
                        enemyIsAiControlledRaw: "0x" + raw.toString(16).padStart(4, "0"),
                        enemyIsAiControlledAsValueFirst: b1 === 0 ? null : b0 !== 0,
                        enemyIsAiControlledAsHasValueFirst: b0 === 0 ? null : b1 !== 0,
                        at: new Date().toISOString(),
                    };
                    if (captures.length >= CAP) captures.shift();
                    captures.push(c);
                    log("[991] StartCampaignMatch this=" + c.thisPtr
                        + " (" + (c.thisClass ?? "?") + ") id=" + (c.campaignId ?? "?")
                        + " loc=" + c.locationIndex
                        + " type=" + (c.campaignTypeName ?? ordinal)
                        + " aiRaw=" + c.enemyIsAiControlledRaw);
                } catch (e) {
                    log("[991] capture en echec : " + (e as Error).message);
                }
            },
        });
    } catch (e) {
        return { ok: false, err: (e as Error).message };
    }
    return { ok: true, armed: true };
}

function disarm(): { ok: boolean; armed: boolean } {
    if (listener) { listener.detach(); listener = null; }
    return { ok: true, armed: false };
}

/** LA QUESTION 1, MESUREE -- et sans rien invoquer sur `ViewCommandExecutor`.
 *
 *  Trois faits rendus, chacun independamment falsifiable :
 *   - `estMonoBehaviour` : la classe porte-t-elle `m_CachedPtr` (heritage `UnityEngine.Object`) ?
 *     C'est LE discriminant, pas la presence d'un `Update()`.
 *   - `navInstance` : une `IdunNavigation` vivante, par le meme `Object.FindObjectsByType(Type,
 *     SortMode)` non generique que le reste du depot (le generique `FindFirstObjectByType<T>` leve
 *     une exception CPU sous `il2cpp_runtime_invoke`).
 *   - `viaChampNomme` : le pointeur lu dans `IdunNavigation._viewCommandExecutor`, offset resolu
 *     par NOM, plus la classe CONCRETE au bout.
 *
 *  ⚠ DUPLICATION ASSUMEE ET DECLAREE : la resolution de la nav vivante existe deja en foyer
 *  unique dans `features/warmup-singletons.ts` (`findLiveIdunNavigation`). Elle n'y est pas
 *  exportee, et ce fichier-la est en cours de reecriture par une autre tranche (chaine de
 *  retraite) -- le toucher creerait un conflit sur un foyer partage. La fusion des deux
 *  (exporter le foyer, l'importer ici) est un residu ouvert, pas un oubli. */
function reach(): unknown {
    const out: Record<string, unknown> = {};
    const vceKlass = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
    out.classeTrouvee = vceKlass !== null;
    if (vceKlass) {
        // `m_CachedPtr` est DECLARE par `UnityEngine.Object`, et `class_get_fields` n'expose que
        // les champs DECLARES par la classe interrogee : on REMONTE donc la chaine de parents.
        // C'est le discriminant retenu par `features/ui-windows.ts` apres la mesure
        // `MenuSystems -> instances: 0` ; la presence d'un `Update()` ne prouve rien.
        let aCachedPtr: boolean | null = null;
        let chaine: string[] = [];
        try {
            aCachedPtr = false;
            let k: NativePointer = vceKlass;
            let depth = 0;
            while (!k.isNull() && depth < 8) {
                chaine.push(cstr(class_get_name(k) as NativePointer));
                const it = Memory.alloc(Process.pointerSize);
                it.writePointer(ptr(0));
                for (;;) {
                    const f = class_get_fields(k, it) as NativePointer;
                    if (f.isNull()) break;
                    if (cstr(field_get_name(f) as NativePointer) === "m_CachedPtr") {
                        aCachedPtr = true;
                    }
                }
                if (aCachedPtr) break;
                k = class_get_parent(k) as NativePointer;
                depth += 1;
            }
        } catch { aCachedPtr = null; chaine = []; }
        // TRI-ETAT : `null` = la mesure n'a pas abouti, jamais rendu comme un `false`.
        out.aCachedPtrDansLaChaine = aCachedPtr;
        out.chaineDHeritage = chaine;
    }

    let navInst: NativePointer | null = null;
    try {
        const navKlass = findClassAnywhere("idun.UI", "IdunNavigation");
        const objK = findClassAnywhere("UnityEngine", "Object");
        if (!navKlass || !objK) {
            out.navErr = "IdunNavigation ou UnityEngine.Object introuvable";
        } else {
            const find = findMethodByParamCount(objK, "FindObjectsByType", 2);
            if (!find) {
                out.navErr = "Object.FindObjectsByType(Type,Mode) introuvable";
            } else {
                const sortMode = Memory.alloc(4).writeS32(0);   // SortMode.None
                const arr = invokeMethod(
                    find.info, null, [getSystemType(navKlass), sortMode]);
                const len = arr.isNull() ? 0 : arr.add(0x18).readS32();
                out.navInstances = len;
                if (len > 0) {
                    const inst = arr.add(0x20).readPointer();
                    if (!inst.isNull()) navInst = inst;
                }
                out.navInstance = navInst ? navInst.toString() : null;
                if (navInst) {
                    const navCls = navInst.readPointer();
                    const off = getFieldOffset(navCls, "_viewCommandExecutor");
                    out.offsetChamp = off;
                    if (off >= 0) {
                        const vce = navInst.add(off).readPointer();
                        out.viaChampNomme = vce.isNull() ? null : vce.toString();
                        out.classeConcrete = vce.isNull() ? null : classNameOf(vce);
                    } else {
                        out.viaChampNomme = null;
                        out.champErr = "_viewCommandExecutor absent de ce build";
                    }
                    const offMs = getFieldOffset(navCls, "_menuSystems");
                    out.offsetMenuSystems = offMs;
                    if (offMs >= 0) {
                        const ms = navInst.add(offMs).readPointer();
                        out.menuSystems = ms.isNull() ? null : ms.toString();
                    }
                }
            }
        }
    } catch (e) {
        out.navErr = (e as Error).message;
    }
    // TRI-ETAT : `null` = PAS mesure (nav absente, champ absent), jamais rabattu sur un zero.
    return { ok: true, ...out };
}

export function register(ctx: Ctx): void {
    ctx.rpc.startCampaignMatchCaptureArm = () => queueOnMainThread(() => arm());
    ctx.rpc.startCampaignMatchCaptureDisarm = () => queueOnMainThread(() => disarm());
    ctx.rpc.startCampaignMatchCaptures = () => ({
        ok: true, armed: listener !== null, count: captures.length, captures,
    });
    ctx.rpc.startCampaignMatchCapturesReset = () => {
        captures = [];
        return { ok: true, count: 0 };
    };
    ctx.rpc.viewCommandExecutorReach = () => queueOnMainThread(() => reach());
}
