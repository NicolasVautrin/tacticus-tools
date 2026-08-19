// vue-exception — L'EXCEPTION QUI VERROUILLE LA BATAILLE, ET LE VERROU QU'ELLE POSE (#10038).
//
// CE QUE LE NATIF FAIT, décompilé puis confronté sur les objets vivants le 2026-08-19
// (`t6dpr4k06g`) :
//
//   IdunBattle.View.Game.IdunGameViews$$HandleException(e)
//       this->_isLogicPausedFromException = 1        <- POSE EN PREMIER, SANS CONDITION
//       si _gameModeSource.<slot 0x13+0x30>(e) :     <- `HandleBattleException`
//              _logger.Log(Format(fmt, e), 0x17, 4)  <- niveau 4 = Error
//       sinon : rien. Pas de popup, pas de trace.
//
//   IdunBattle.View.Game.IdunGameViews$$QueueComputerActions
//       exige les QUATRE drapeaux de pause a 0 -- dont celui-la.
//
// ⚠ IL N'EXISTE AUCUN `ContinueLogicFromException`. `PauseLogic`/`ContinueLogic` et
// `PauseLogicFromVisuals`/`ContinueLogicFromVisuals` vont par paires ; le troisieme drapeau n'a
// PAS de clef. Le verrou est donc DEFINITIF pour la bataille en cours : l'IA adverse n'est plus
// jamais lancee, les entrees ne repondent plus, et RIEN ne le signale a l'ecran. C'est la
// signature mesuree de #10038 -- « je finis mon tour et l'IA ne joue pas ».
//
// ⚠ ET LE CHIEN DE GARDE NE REPARE RIEN. `MessageExecutionQueue$$CheckLastActivityTimeout`
// JOURNALISE au-dela de 10 s puis remet son chrono a zero. Il ne force jamais la completion.
//
// CE MODULE N'INSTALLE RIEN AU REGISTER. Son ancrage est en OBSERVATION PURE (`onEnter`, aucune
// ecriture, aucun `retval.replace`) et s'arme explicitement. Le seul RPC qui ECRIT est
// `vueExceptionDeverrouiller`, garde par `confirmer: true` -- et il MASQUE la cause, il ne la
// repare pas : a n'utiliser que pour poursuivre une observation deja en cours.

import {
    class_get_name, findClassAnywhere, findMethod, findMethodByParamCount,
    getFieldOffset, getStack, getSystemType, s,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { champTexte, estRefus, refus } from "./lecture-champs.js";
import { Refus } from "./view-command.js";
import { Ctx } from "../controller.js";

const NS_VUES = "IdunBattle.View.Game";
const CLS_VUES = "IdunGameViews";
const METH = "HandleException";

/** Les quatre drapeaux que `QueueComputerActions` exige a zero, dans l'ordre des offsets.
 *  Resolus PAR NOM : un offset en dur lirait un voisin au prochain build, en silence. */
const DRAPEAUX = [
    "<IsPaused>k__BackingField",
    "_isLogicPausedFromUI",
    "_isLogicPausedFromVisuals",
    "_isLogicPausedFromException",
] as const;

interface Capture {
    classe: string | null;
    message: string | null;
    pileGeree: string | null;
    pileNative: string[] | null;
    interne: string | null;
    vues: string;
}

const captures: Capture[] = [];
let listener: InvocationListener | null = null;
let fires = 0;
let refusArmement: string | null = null;

/** TOUTES les instances vivantes d'une classe UNITY, pas la premiere.
 *
 *  ⚠ POURQUOI PAS `premiereInstance`. Mesure du 2026-08-19 : apres une retraite suivie d'un
 *  remontage, DEUX `IdunMainView` coexistent, et `FindObjectsByType` rend d'abord la MORTE --
 *  celle dont `gameViews` est nul. Un lecteur bati dessus rend « champ NUL » et se lit
 *  « pas de bataille », alors que la bataille tourne. On enumere donc, et on PUBLIE le compte.
 *
 *  ⚠ ET ELLE NE VAUT QUE POUR UN `UnityEngine.Object`. Mesure du 2026-08-19, faute deja
 *  commise : appelee sur `IdunGameViews` elle rend `null` -- cette classe porte pourtant un
 *  `Update()`, mais c'est `IdunMainView` qui l'appelle, pas Unity. Un `Update()` ne fait pas un
 *  MonoBehaviour (meme piege que `ViewCommandExecutor` et `thor.Menu.MenuSystems`, deja
 *  consigne dans `view-command.ts`). `IdunGameViews` se prend par le champ NOMME `gameViews`
 *  d'`IdunMainView`, jamais par enumeration. */
function toutesInstances(klass: NativePointer): NativePointer[] | Refus {
    const kObj = findClassAnywhere("UnityEngine", "Object");
    if (!kObj) return refus("UnityEngine.Object introuvable");
    const mi3 = findMethodByParamCount(kObj, "FindObjectsByType", 3);
    const mi2 = findMethodByParamCount(kObj, "FindObjectsByType", 2);
    if (!mi3 && !mi2) return refus("`FindObjectsByType` introuvable (2 et 3 parametres)");
    const tri = Memory.alloc(4); tri.writeS32(0);
    const inclure = Memory.alloc(4); inclure.writeS32(1);
    let arr: NativePointer;
    try {
        arr = mi3
            ? invokeMethod(mi3.info, null, [getSystemType(klass), inclure, tri])
            : invokeMethod(mi2!.info, null, [getSystemType(klass), tri]);
    } catch (e) {
        return refus("`FindObjectsByType` a leve : " + (e as Error).message);
    }
    if (arr.isNull()) return refus("`FindObjectsByType` a rendu null");
    const n = arr.add(0x18).readS32();
    if (n <= 0) return [];
    const out: NativePointer[] = [];
    for (let i = 0; i < Math.min(n, 64); i += 1) {
        const p = arr.add(0x20 + i * Process.pointerSize).readPointer();
        if (!p.isNull()) out.push(p);
    }
    return out;
}

/** Les `IdunGameViews` vivantes, atteintes par le champ NOMME `gameViews` de chaque
 *  `IdunMainView` -- la SEULE voie (cf. le bloc ci-dessus). Une vue morte porte `gameViews` nul :
 *  elle est ecartee, mais COMPTEE, pour qu'un remontage rate ne se lise pas comme une absence. */
function vuesVivantes(): { vues: NativePointer[]; ecartees: number } | Refus {
    const kVue = findClassAnywhere("idun", "IdunMainView");
    if (!kVue) return refus("classe idun.IdunMainView introuvable");
    const insts = toutesInstances(kVue);
    if (estRefus(insts)) return insts;
    const vues: NativePointer[] = [];
    let ecartees = 0;
    for (const p of insts) {
        let off = -1;
        try { off = getFieldOffset(p.readPointer(), "gameViews"); } catch { /* -1 */ }
        if (off < 0) { ecartees += 1; continue; }
        let gv: NativePointer;
        try { gv = p.add(off).readPointer(); } catch { ecartees += 1; continue; }
        if (gv.isNull()) { ecartees += 1; continue; }
        vues.push(gv);
    }
    return { vues, ecartees };
}

/** Les quatre drapeaux d'une instance, par leur NOM, avec l'offset publie pour que le lecteur
 *  puisse confronter au decompile. `null` = champ ABSENT de ce build, jamais rabattu sur 0. */
function drapeauxDe(vues: NativePointer): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    let klass: NativePointer;
    try { klass = vues.readPointer(); }
    catch (e) { return { erreur: "classe illisible : " + (e as Error).message }; }
    for (const nom of DRAPEAUX) {
        const off = getFieldOffset(klass, nom);
        if (off < 0) { out[nom] = { offset: -1, valeur: null, note: "champ ABSENT de ce build" }; continue; }
        let v: number | null = null;
        try { v = vues.add(off).readU8(); } catch { v = null; }
        out[nom] = { offset: off, valeur: v };
    }
    return out;
}

function lireException(e: NativePointer, ctx: CpuContext): Capture {
    let classe: string | null = null;
    try { classe = s(class_get_name(e.readPointer()) as NativePointer); } catch { /* null */ }
    // `_stackTraceString` est renseigne par le runtime AU LANCEMENT (`throw`) ; il est donc deja
    // la quand le catch nous appelle. On ne l'INVOQUE pas (`get_StackTrace` alloue et formate) --
    // on le LIT.
    let interne: string | null = null;
    try {
        const inner = (() => {
            const k = e.readPointer();
            const off = getFieldOffset(k, "_innerException");
            return off < 0 ? null : e.add(off).readPointer();
        })();
        if (inner && !inner.isNull()) {
            interne = (s(class_get_name(inner.readPointer()) as NativePointer) ?? "?")
                + " : " + (champTexte(inner, "_message") ?? "(sans message)");
        }
    } catch { /* interne reste null */ }
    return {
        classe,
        message: champTexte(e, "_message"),
        pileGeree: champTexte(e, "_stackTraceString"),
        // La pile NATIVE est le filet quand la pile geree est nulle. `getStack` rend des RVA
        // (offsets depuis `il2cppBase`) : on les publie en HEXA, prets a etre confrontes a
        // `data/symbols/<build>/ghidra/functions.tsv` (VA = base 0x180000000 + RVA), ce qui rend
        // un SYMBOLE -- jamais une adresse absolue, qui serait fausse au prochain build.
        pileNative: (() => {
            try { return getStack(ctx).map((r) => "0x" + (r >>> 0).toString(16)); }
            catch { return null; }
        })(),
        interne,
        vues: "",
    };
}

function armer(): Record<string, unknown> | Refus {
    if (listener) return { ok: true, arme: true, deja: true, fires };
    const k = findClassAnywhere(NS_VUES, CLS_VUES);
    if (!k) return refus(`classe ${NS_VUES}.${CLS_VUES} introuvable`);
    const mi = findMethod(k, METH);
    if (!mi || mi.ptr.isNull()) {
        return refus(`\`${CLS_VUES}$$${METH}\` INTROUVABLE -- chemin PERIME sur ce build`);
    }
    try {
        listener = Interceptor.attach(mi.ptr, {
            onEnter(args): void {
                fires += 1;
                try {
                    const c = lireException(
                        args[1], (this as unknown as { context: CpuContext }).context);
                    c.vues = args[0].toString();
                    captures.push(c);
                    if (captures.length > 8) captures.shift();
                } catch { /* ne jamais lever depuis un ancrage */ }
            },
        });
    } catch (e) {
        refusArmement = "attach a leve : " + (e as Error).message;
        return refus(refusArmement);
    }
    return { ok: true, arme: true, adresse: mi.ptr.toString(),
             note: "OBSERVATION PURE sur `IdunGameViews$$HandleException`. Le verrou "
                 + "`_isLogicPausedFromException` est pose par le natif AVANT nous et n'est PAS "
                 + "retire ici." };
}

export function register(ctx: Ctx): void {

    /** Arme / desarme / lit l'ancrage. Sans argument : lecture seule. */
    ctx.rpc.vueExceptionArmer = (body?: { armer?: boolean }): unknown => {
        if (body == null || body.armer === undefined) {
            return { ok: true, arme: listener !== null, fires, refus: refusArmement,
                     note: "lecture seule -- passer `armer: true` pour armer" };
        }
        if (body.armer === false) {
            if (listener) { try { listener.detach(); } catch { /* best effort */ } }
            listener = null;
            return { ok: true, arme: false, fires };
        }
        return armer();
    };

    /** L'ETAT : les captures, et le verrou tel qu'il est SUR CHAQUE instance vivante.
     *
     *  body: { surVues?: "0x..." } -- viser une `IdunGameViews` explicitement.
     *
     *  ⚠ `fires: 0` avec un verrou POSE veut dire que l'exception est tombee AVANT l'armement --
     *  c'est un etat distinct de « pas d'exception », et il se lit ici sans ambiguite.
     *
     *  ⚠ LES CAPTURES SORTENT TOUJOURS, meme si la resolution des instances echoue. Faute
     *  commise le 2026-08-19 : la premiere version rendait le refus de `FindObjectsByType` AVANT
     *  les captures, donc une exception REELLEMENT captee (`fires: 1`) etait invisible, et il a
     *  fallu un reinject pour la relire -- qui l'a effacee. Un capteur ne doit jamais laisser un
     *  echec ACCESSOIRE masquer ce qu'il a deja mesure. */
    ctx.rpc.vueExceptionEtat = (body?: { surVues?: string }): unknown => {
        const base = { ok: true, arme: listener !== null, fires, captures };
        if (typeof body?.surVues === "string" && /^0x[0-9a-fA-F]+$/.test(body.surVues)) {
            const p = ptr(body.surVues);
            return { ...base, nbVues: 1, ecartees: 0,
                     vues: [{ instance: p.toString(), drapeaux: drapeauxDe(p) }] };
        }
        const r = vuesVivantes();
        if (estRefus(r)) return { ...base, vues: null, refusVues: r.error };
        return { ...base, nbVues: r.vues.length, ecartees: r.ecartees,
                 vues: r.vues.map((p) => ({ instance: p.toString(), drapeaux: drapeauxDe(p) })) };
    };

    /** RETIRER le verrou `_isLogicPausedFromException` sur les instances vivantes.
     *
     *  ⚠ ECRITURE, et elle MASQUE. Le natif n'offre aucun `ContinueLogicFromException` : ce RPC
     *  fait donc quelque chose que le jeu ne fait JAMAIS. Il ne repare pas la cause -- il permet
     *  de poursuivre une observation en cours apres une exception deja captee. Toute conclusion
     *  tiree d'une bataille deverrouillee doit le DIRE.
     *  ⚠ Il refuse si l'ancrage n'a rien capte ET que le verrou est pose : dans ce cas la cause
     *  n'est pas connue, et l'effacer la rendrait inobservable. */
    ctx.rpc.vueExceptionDeverrouiller = (
        body?: { confirmer?: boolean; forcer?: boolean; surVues?: string },
    ): unknown => {
        if (body?.confirmer !== true) {
            return refus("ECRITURE -- exige `confirmer: true`. Ce RPC MASQUE la cause : il retire "
                + "un verrou que le jeu ne retire jamais.");
        }
        let insts: NativePointer[];
        if (typeof body?.surVues === "string" && /^0x[0-9a-fA-F]+$/.test(body.surVues)) {
            insts = [ptr(body.surVues)];
        } else {
            const r = vuesVivantes();
            if (estRefus(r)) return r;
            insts = r.vues;
        }
        const faits: Array<Record<string, unknown>> = [];
        for (const p of insts) {
            let klass: NativePointer;
            try { klass = p.readPointer(); } catch { continue; }
            const off = getFieldOffset(klass, "_isLogicPausedFromException");
            if (off < 0) {
                faits.push({ instance: p.toString(), ok: false,
                             error: "`_isLogicPausedFromException` ABSENT de ce build" });
                continue;
            }
            let avant: number | null = null;
            try { avant = p.add(off).readU8(); } catch { /* null */ }
            if (avant === 0) { faits.push({ instance: p.toString(), ok: true, avant, apres: 0,
                                            note: "deja a zero -- rien ecrit" }); continue; }
            if (captures.length === 0 && body?.forcer !== true) {
                faits.push({ instance: p.toString(), ok: false, avant,
                             error: "verrou POSE mais AUCUNE capture -- la cause est inconnue, "
                                  + "l'effacer la rendrait inobservable. Armer "
                                  + "`vueExceptionArmer` puis reproduire, ou `forcer: true`." });
                continue;
            }
            try { p.add(off).writeU8(0); } catch (e) {
                faits.push({ instance: p.toString(), ok: false, avant,
                             error: "ecriture a leve : " + (e as Error).message });
                continue;
            }
            let apres: number | null = null;
            try { apres = p.add(off).readU8(); } catch { /* null */ }
            faits.push({ instance: p.toString(), ok: apres === 0, offset: off, avant, apres });
        }
        return { ok: true, faits,
                 avertissement: "VERROU RETIRE. La cause n'est PAS reparee -- toute mesure prise "
                     + "apres coup doit le mentionner." };
    };
}
