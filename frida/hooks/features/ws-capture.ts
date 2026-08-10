// ws-capture — LE PROTOCOLE DU PvP SYNCHRONE, capté AUX DEUX SENS.
//
// POURQUOI CE MODULE, ALORS QUE `net-capture` EXISTE DÉJÀ.
// `net-capture` ancre `Snowprint.ClientSdk.Web.WwwWebHelper$$PostString/PostBytes/PostData` :
// c'est de l'HTTP. `IdunBattle.ViewLogic.BattleSource.SyncPvpGameModeSource` ne passe PAS par
// là — son transport est un WebSocket (`thor.Logic.Client.Web.WebsocketController`). Armer
// `net-capture` sur une partie SyncPvp rendrait donc un journal VIDE, et un journal vide se lit
// comme « rien n'est parti ». C'est exactement la faute déjà commise en n'ancrant que
// `PostString` alors que `PostData` était une porte distincte : une porte non ancrée ne produit
// pas d'erreur, elle produit un ZÉRO.
//
// LES DEUX SENS — c'est tout l'intérêt. `net-capture` ne voit que ce qui PART. En PvP
// synchrone les coups de l'adversaire ARRIVENT ; sans le sens entrant on n'observe qu'une
// moitié de conversation.
//
//   thor.Logic.Client.Web.WebsocketController$$Send(message:System.String) : System.Boolean
//   thor.Logic.Client.Web.WebsocketController$$OnMessage(ws:IWebSocket, message:System.String)
//   idun.Idun.Source.WebSocket.NativeWebSocketWrapper$$Send(message:System.String) : Boolean
//
// DEUX COUCHES SUR LE SORTANT, VOLONTAIREMENT. `WebsocketController$$CreateNewWebsocket` rend
// un `IWebSocket`, que `NativeWebSocketWrapper` implémente : le `Send` du contrôleur délègue
// PROBABLEMENT à celui du wrapper. « Probablement » n'est pas une mesure — on ancre les deux et
// le journal publie `via`, donc la délégation se LIT (doublons appariés sur le même `t`) au
// lieu de se supposer. Si elle se confirme, retirer une couche sera un geste informé.
//
// LE RETOUR DE `Send` EST CAPTÉ (`ok`). Il rend un `Boolean` : `false` = message NON transmis.
// L'ignorer reproduirait le vice du `ok:true` pris pour un effet — un envoi refusé se lirait
// comme un envoi.
//
// LE CYCLE DE VIE AUSSI (`OnOpen`, `OnClosed`, `Reconnect`). Sans lui un silence est AMBIGU :
// socket fermée, ou socket ouverte et rien à dire ? Les deux rendent « 0 message ».
//
// HORODATAGE RELATIF (`t`, ms depuis l'armement). Un protocole temps réel ne se lit pas sans
// les délais : `t` sépare une réponse en 10 ms d'une en 3 s, et rend les pings visibles.
//
// ⚠ LE SENS ENTRANT PEUT ARRIVER HORS DU THREAD PRINCIPAL (réception socket). Les callbacks ne
// font donc que des LECTURES MÉMOIRE et un push — aucun appel runtime IL2CPP, aucun
// `queueOnMainThread`. C'est une différence réelle avec `net-capture`, dont les POST partaient
// du thread principal.
//
// ⚠ IDENTITÉ DU SOCKET RÉSOLUE AU RUNTIME, JAMAIS PAR OFFSET DEVINÉ. Il peut exister plusieurs
// `WebsocketController` (le ctor prend un `serviceUri`). On publie le pointeur d'instance comme
// discriminant SÛR, et on tente en plus de lire l'URI par un champ résolu PAR NOM — `uri: null`
// signifie « PAS MESURÉ », jamais « pas d'URI ». Le nom du champ retenu est publié dans
// `layout.champUri` pour que l'échec soit visible plutôt que silencieux.
//
// ARMÉ À LA DEMANDE, jamais auto-armé. OBSERVATION SEULE : ce module n'écrit rien, n'injecte
// aucun message et ne modifie aucun retour.

import {
    findClassAnywhere, findMethod, findMethodByParamCount, getFieldOffset,
} from "../il2cpp/helpers.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

/** Plafond d'entrées. Un match temps réel bavarde (actions + pings) : bien plus haut que le
 *  plafond de `net-capture`, qui comptait des POST de fin de bataille. */
const CAP = 4000;
/** Ce qu'on garde d'un corps quand on ne le garde pas en entier. */
const PREFIXE = 300;
/** Budget TOTAL de caractères conservés. Au-delà : taille + préfixe, et `corpsOmis` compte les
 *  renoncements — un journal qui tronque en silence se lirait comme complet. */
const BUDGET_CORPS = 4_000_000;
/** Noms candidats pour le champ portant l'URI de service. Testés dans l'ordre au moment de
 *  l'armement ; le premier qui résout est publié dans `layout.champUri`.
 *
 *  `_socketUri` est le nom RÉEL, LU sur le build `rnca9r7q6c` via le RPC `classFields` — pas
 *  deviné. Les six noms qui semblaient évidents (`_serviceUri` en tête, calqué sur le paramètre
 *  `serviceUri` du ctor) ont TOUS échoué au premier armement : c'est le tri-état `null` = PAS
 *  MESURÉ qui l'a dit, là où un offset en dur aurait lu une chaîne voisine sans rien signaler.
 *  Les suivants restent comme filet inter-build ; si un jour `champUri` revient `null`,
 *  re-dériver par `classFields("thor.Logic.Client.Web", "WebsocketController")` plutôt que
 *  d'allonger cette liste à l'aveugle. */
const CANDIDATS_URI = [
    "_socketUri", "_serviceUri", "serviceUri", "_uri", "uri", "_url", "url",
];

type Sens = "out" | "in" | "etat";

interface Trame {
    n: number;
    /** ms depuis l'armement — l'axe qui rend un protocole temps réel lisible. */
    t: number;
    sens: Sens;
    via: string;
    /** Pointeur d'instance : discriminant SÛR entre plusieurs sockets. */
    ctrl: string | null;
    /** URI de service, ou `null` = PAS MESURÉ (champ non résolu). */
    uri: string | null;
    len: number | null;
    prefixe: string | null;
    corps: string | null;
    /** Retour de `Send` : `false` = NON transmis. `null` tant que l'appel n'est pas revenu. */
    ok?: boolean | null;
    corpsOmis?: true;
}

const tampon: Trame[] = [];
let compteur = 0;
let budgetRestant = BUDGET_CORPS;
let corpsOmis = 0;
let t0 = 0;
let offUri = -1;
const listeners: InvocationListener[] = [];
const layout: Record<string, unknown> = {};

/** `System.String` IL2CPP : longueur @+0x10, caractères UTF-16 @+0x14. On lit la longueur SANS
 *  matérialiser la chaîne. Bornes strictes : une longueur aberrante ferait scanner de la
 *  mémoire non mappée depuis un thread qu'on ne contrôle pas. */
function chaine(p: NativePointer): { len: number; lire: (n: number) => string | null } | null {
    if (p.isNull()) return null;
    try {
        const len = p.add(0x10).readS32();
        if (len < 0 || len > 0x4000000) return null;
        return {
            len,
            lire: (n: number) => {
                try { return p.add(0x14).readUtf16String(Math.min(len, n)); }
                catch { return null; }
            },
        };
    } catch { return null; }
}

/** Lit l'URI de service depuis l'instance, si et seulement si le champ a été résolu par nom. */
function lireUri(inst: NativePointer): string | null {
    if (offUri < 0 || inst.isNull()) return null;
    try {
        const s = chaine(inst.add(offUri).readPointer());
        return s ? s.lire(200) : null;
    } catch { return null; }
}

/** Enregistre une trame. Rend son index dans le tampon, ou -1 si elle n'a pas été retenue
 *  (plafond atteint) — l'appelant en a besoin pour renseigner `ok` au retour. */
function noter(
    sens: Sens, via: string, inst: NativePointer | null,
    charge: { len: number; lire: (n: number) => string | null } | null,
    attendUnRetour: boolean,
): number {
    if (tampon.length >= CAP) return -1;
    const trame: Trame = {
        n: ++compteur,
        t: Date.now() - t0,
        sens, via,
        ctrl: inst && !inst.isNull() ? inst.toString() : null,
        uri: inst ? lireUri(inst) : null,
        len: charge ? charge.len : null,
        prefixe: charge ? charge.lire(PREFIXE) : null,
        corps: null,
    };
    // Corps ENTIER tant que le budget le permet — c'est lui, la donnée.
    if (charge !== null) {
        if (charge.len <= budgetRestant) {
            trame.corps = charge.lire(charge.len);
            if (trame.corps !== null) budgetRestant -= charge.len;
        } else {
            trame.corpsOmis = true;
            corpsOmis++;
        }
    }
    if (attendUnRetour) trame.ok = null;
    tampon.push(trame);
    return tampon.length - 1;
}

/** Contexte d'invocation Frida, où l'on stocke l'index entre `onEnter` et `onLeave`. */
interface CtxInvoc { _idx?: number }

/** Ancre une porte porteuse d'un message. `iMsg` = indice de l'argument message
 *  (`args[0]` est `this` : ces trois méthodes sont toutes des méthodes d'INSTANCE). */
function ancrer(
    mi: { ptr: NativePointer } | null, cle: string,
    sens: Sens, iMsg: number, capteLeRetour: boolean,
): void {
    if (!mi || mi.ptr.isNull()) { layout[cle] = "NON RESOLUE"; return; }
    try {
        listeners.push(Interceptor.attach(mi.ptr, {
            onEnter(args) {
                try {
                    const idx = noter(sens, cle, args[0], chaine(args[iMsg]), capteLeRetour);
                    if (capteLeRetour) (this as unknown as CtxInvoc)._idx = idx;
                } catch { /* un capteur ne jette jamais */ }
            },
            onLeave(ret) {
                if (!capteLeRetour) return;
                try {
                    const idx = (this as unknown as CtxInvoc)._idx;
                    if (typeof idx !== "number" || idx < 0 || idx >= tampon.length) return;
                    tampon[idx].ok = !ret.isNull() && ret.toInt32() !== 0;
                } catch { /* idem */ }
            },
        }));
        layout[cle] = true;
    } catch { layout[cle] = "ANCRAGE EN ECHEC"; }
}

/** Ancre une porte de cycle de vie : pas de message, juste le fait qu'elle ait tiré. `iTexte`
 *  < 0 quand la méthode ne porte aucune chaîne (`OnOpen`). */
function ancrerEtat(
    mi: { ptr: NativePointer } | null, cle: string, iTexte: number,
): void {
    if (!mi || mi.ptr.isNull()) { layout[cle] = "NON RESOLUE"; return; }
    try {
        listeners.push(Interceptor.attach(mi.ptr, {
            onEnter(args) {
                try {
                    noter("etat", cle, args[0],
                          iTexte >= 0 ? chaine(args[iTexte]) : null, false);
                } catch { /* un capteur ne jette jamais */ }
            },
        }));
        layout[cle] = true;
    } catch { layout[cle] = "ANCRAGE EN ECHEC"; }
}

export function register(ctx: Ctx): void {
    /** Arme les portes. Idempotent.
     *  body: {} -> { ok, armes, layout } */
    ctx.rpc.wsCaptureArm = (): Promise<unknown> => queueOnMainThread(() => {
        if (listeners.length > 0) {
            return { ok: true, deja: true, armes: listeners.length, layout };
        }
        const ctrl = findClassAnywhere("thor.Logic.Client.Web", "WebsocketController");
        const wrap = findClassAnywhere("idun.Idun.Source.WebSocket", "NativeWebSocketWrapper");
        if (!ctrl && !wrap) {
            return {
                ok: false,
                error: "thor.Logic.Client.Web.WebsocketController ET "
                     + "idun.Idun.Source.WebSocket.NativeWebSocketWrapper introuvables",
            };
        }
        t0 = Date.now();

        if (ctrl) {
            // Champ d'URI : résolu PAR NOM, et on publie lequel a mordu. `null` = pas mesuré.
            offUri = -1;
            layout.champUri = null;
            for (const nom of CANDIDATS_URI) {
                const off = getFieldOffset(ctrl, nom);
                if (off >= 0) { offUri = off; layout.champUri = nom; break; }
            }
            // Arités explicites : `Send(message)` = 1, `OnMessage(ws, message)` = 2. Passer par
            // l'arité plutôt que par le nom seul évite d'attraper une surcharge voisine sans
            // le dire — un mauvais indice d'argument lirait du vide en silence.
            ancrer(findMethodByParamCount(ctrl, "Send", 1),
                   "WebsocketController.Send", "out", 1, true);
            ancrer(findMethodByParamCount(ctrl, "OnMessage", 2),
                   "WebsocketController.OnMessage", "in", 2, false);
            ancrerEtat(findMethodByParamCount(ctrl, "OnOpen", 1),
                       "WebsocketController.OnOpen", -1);
            ancrerEtat(findMethodByParamCount(ctrl, "OnClosed", 3),
                       "WebsocketController.OnClosed", 3);
            ancrerEtat(findMethodByParamCount(ctrl, "Reconnect", 1),
                       "WebsocketController.Reconnect", 1);
        } else {
            layout["WebsocketController"] = "CLASSE INTROUVABLE";
        }

        if (wrap) {
            ancrer(findMethodByParamCount(wrap, "Send", 1),
                   "NativeWebSocketWrapper.Send", "out", 1, true);
        } else {
            layout["NativeWebSocketWrapper"] = "CLASSE INTROUVABLE";
        }

        Interceptor.flush();
        log("[ws-capture] arme : " + listeners.length + " porte(s)");
        return { ok: true, armes: listeners.length, layout };
    });

    /** body: { reset?, depuis?: number, sansCorps?: true, contient?: string, sens?: Sens }
     *
     *  `sansCorps` liste sans rapatrier les charges. `contient` filtre sur le corps ET l'URI.
     *  `sens` isole un sens ("out" | "in" | "etat"). */
    ctx.rpc.wsCaptureDump = (body?: {
        reset?: boolean; depuis?: number; sansCorps?: boolean;
        contient?: string; sens?: Sens;
    }): Promise<unknown> => queueOnMainThread(() => {
        const depuis = typeof body?.depuis === "number" ? body.depuis : 0;
        const filtre = typeof body?.contient === "string" && body.contient
            ? body.contient.toLowerCase() : null;
        let entries = tampon.filter((e) => e.n > depuis);
        if (body?.sens) entries = entries.filter((e) => e.sens === body.sens);
        if (filtre) {
            entries = entries.filter((e) =>
                ((e.corps ?? e.prefixe ?? "") + " " + (e.uri ?? ""))
                    .toLowerCase().includes(filtre));
        }
        if (body?.sansCorps) entries = entries.map((e) => ({ ...e, corps: null }));
        // Ventilation par sens : un total seul ne dirait pas qu'un des deux sens est resté MUET,
        // ce qui est précisément le symptôme d'une porte mal ancrée.
        const parSens = { out: 0, in: 0, etat: 0 };
        for (const e of tampon) parSens[e.sens]++;
        const out = {
            ok: true, arme: listeners.length > 0, count: tampon.length, plafond: CAP,
            parSens, corpsOmis, budgetRestant, entries, layout,
        };
        if (body?.reset) {
            tampon.length = 0; corpsOmis = 0; budgetRestant = BUDGET_CORPS; t0 = Date.now();
        }
        return out;
    });

    ctx.rpc.wsCaptureDisarm = (): Promise<unknown> => queueOnMainThread(() => {
        for (const l of listeners) { try { l.detach(); } catch { /* deja parti */ } }
        listeners.length = 0;
        return { ok: true, restant: tampon.length };
    });

    ctx.rpc.wsCaptureStatus = (): Promise<unknown> => queueOnMainThread(() => {
        const parSens = { out: 0, in: 0, etat: 0 };
        for (const e of tampon) parSens[e.sens]++;
        return {
            ok: true, arme: listeners.length > 0, portes: listeners.length,
            count: tampon.length, parSens, corpsOmis, budgetRestant, layout,
        };
    });
}
