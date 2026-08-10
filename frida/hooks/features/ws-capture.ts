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
// DEUX ÉTAGES, ET LE SECOND EST CELUI QUI NOMME. Le socket brut ne transporte que du JSON
// anonyme : l'exploiter voudrait dire rétro-ingénierer un format. Or l'étage au-dessus,
// `IdunBattleLogic.Synchronous.SynchronousNetwork`, est le SEUL consommateur SyncPvp de ce
// socket (`HandleOnMessageFromConnectionReceived`) et il expose le protocole DÉJÀ nommé —
// `HandleGameActionTransient` vs `HandleGameActionPersisted`, `HandleStartGame`,
// `HandleGameEnded`, `GameDiscrepancyDetected`. On ancre les DEUX : le brut garantit qu'on ne
// rate rien (y compris ce que la couche sémantique ignore), le sémantique donne le sens sans
// parser. Les deux se recoupent, et ce recoupement est une MESURE de couverture.
//
// L'ARCHITECTURE SE LIT DANS LES SIGNATURES, avant toute capture :
//   SendAction(clientActionIndex, clientSequenceIndex, message:IInputMessage,
//              metaMessage:IGameActionMetaData, turn, stateHash:System.String, skipGameAction)
//   HandleGameActionTransient(payload, matchId)                  <- coup adverse PROVISOIRE
//   HandleGameActionPersisted(payload, userId, matchId, eventId) <- CONFIRME par le serveur
//   GetGameActions(fromActionIndex)  ·  GameDiscrepancyDetected()
// => lockstep indexé, avec `stateHash` par action et détection de divergence : le serveur
// ARBITRE. C'est une lecture de symboles, pas une capture — à confirmer sur trame réelle.
//
// L'AUTRE CONSOMMATEUR DU MÊME SOCKET est `thor.Logic.Client.Web.ChannelManager`
// (`HandleOnMessageFromConnectionReceived` lui aussi). Donc le socket n'est PAS réservé au
// SyncPvp : c'est par là qu'un témoin est possible hors saison.
//
// ARMÉ À LA DEMANDE, jamais auto-armé. OBSERVATION SEULE : ce module n'écrit rien, n'injecte
// aucun message et ne modifie aucun retour.

import {
    findClassAnywhere, findMethod, findMethodByParamCount, getFieldOffset, readMsgClass,
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
    /** Champs nommés de l'étage sémantique (index d'action, tour, `stateHash`, type du message
     *  d'entrée…). Clés = noms de paramètres natifs VERBATIM, pour que le grep code <-> table
     *  reste immédiat. `null` = argument présent mais illisible, jamais « absent ». */
    champs?: Record<string, string | number | null>;
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
    champs?: Record<string, string | number | null>,
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
    if (champs) trame.champs = champs;
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

/** Une porte de l'étage SÉMANTIQUE. `args[0]` est `this` (toutes ces méthodes sont des méthodes
 *  d'instance), donc les indices ci-dessous coïncident avec le rang du paramètre natif. */
interface PorteSem {
    ns: string;
    cls: string;
    methode: string;
    /** Arité NATIVE, hors `this`. L'ancrage passe par elle et jamais par le nom seul :
     *  `Send` existe en DEUX surcharges (1 et 3 paramètres) et les confondre lirait
     *  silencieusement le mauvais argument. */
    arite: number;
    sens: Sens;
    /** Argument portant la charge principale (va dans `corps`). */
    corpsDe?: number;
    /** Arguments relevés comme chaînes : [indice, nom du paramètre natif VERBATIM]. */
    chaines?: Array<[number, string]>;
    /** Arguments relevés comme entiers (int, enum, bool). */
    entiers?: Array<[number, string]>;
    /** Argument objet dont on relève le NOM DE CLASSE : c'est le TYPE de l'action jouée —
     *  l'information la plus dense de tout `SendAction`, et elle n'est nulle part ailleurs. */
    classeDe?: [number, string];
    /** Relever le retour, qui est une `System.String` (`SendAction` rend l'eventId — celui-là
     *  même que `HandleGameActionPersisted` renverra : c'est ce qui apparie aller et retour). */
    retourChaine?: boolean;
}

const NS_SYNC = "IdunBattleLogic.Synchronous";
const NS_WEB = "thor.Logic.Client.Web";

const PORTES_SEM: PorteSem[] = [
    // ---- SORTANT : ce que NOUS envoyons -----------------------------------------------------
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "SendAction", arite: 7, sens: "out",
        classeDe: [3, "message"], chaines: [[6, "stateHash"]], retourChaine: true,
        entiers: [[1, "clientActionIndex"], [2, "clientSequenceIndex"], [5, "turn"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "ResendAction", arite: 8, sens: "out",
        classeDe: [3, "message"], chaines: [[6, "stateHash"], [8, "eventId"]],
        entiers: [[1, "clientActionIndex"], [2, "clientSequenceIndex"], [5, "turn"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "Send", arite: 3, sens: "out",
        corpsDe: 2, chaines: [[3, "eventId"]], entiers: [[1, "type"]], retourChaine: true,
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "Send", arite: 1, sens: "out",
        entiers: [[1, "type"]], retourChaine: true,
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "SendMessage", arite: 1, sens: "out",
        corpsDe: 1,
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "PlayGame", arite: 5, sens: "out",
        chaines: [[1, "name"], [4, "machineOfWar"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "GetGameActions", arite: 1, sens: "out",
        entiers: [[1, "fromActionIndex"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "Surrender", arite: 1, sens: "out",
        entiers: [[1, "surrenderType"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "EndGame", arite: 1, sens: "out",
        chaines: [[1, "winnerUserId"]],
    },
    { ns: NS_SYNC, cls: "SynchronousNetwork", methode: "PlayerReady", arite: 0, sens: "out" },
    { ns: NS_SYNC, cls: "SynchronousNetwork", methode: "CancelGame", arite: 0, sens: "out" },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "GameDiscrepancyDetected",
        arite: 0, sens: "out",
    },

    // ---- ENTRANT : ce que le serveur (et donc l'ADVERSAIRE) nous envoie ----------------------
    // La racine attrape TOUT l'entrant SyncPvp ; les portes typées qui suivent le NOMMENT. Les
    // deux tirent sur la même trame : ce doublon est voulu, c'est lui qui mesure la couverture.
    {
        ns: NS_SYNC, cls: "SynchronousNetwork",
        methode: "HandleOnMessageFromConnectionReceived", arite: 1, sens: "in", corpsDe: 1,
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "HandleCreateGame", arite: 1,
        sens: "in", corpsDe: 1,
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "HandleStartGame", arite: 2,
        sens: "in", corpsDe: 1, chaines: [[2, "matchId"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "HandleGameActionTransient", arite: 2,
        sens: "in", corpsDe: 1, chaines: [[2, "matchId"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "HandleGameActionPersisted", arite: 4,
        sens: "in", corpsDe: 1,
        chaines: [[2, "userId"], [3, "matchId"], [4, "eventId"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "HandleGetGameActions", arite: 2,
        sens: "in", corpsDe: 1, chaines: [[2, "matchId"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "HandleGameEnded", arite: 2,
        sens: "in", corpsDe: 1, chaines: [[2, "matchId"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "HandlePlayGameError", arite: 1,
        sens: "in", corpsDe: 1,
    },

    // ---- ÉTAT ------------------------------------------------------------------------------
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "HandleGameDiscrepancy", arite: 0,
        sens: "etat",
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "HandleOnConnectionStatusChanged",
        arite: 1, sens: "etat", entiers: [[1, "status"]],
    },
    {
        ns: NS_SYNC, cls: "SynchronousNetwork", methode: "Connect", arite: 1, sens: "etat",
        chaines: [[1, "userId"]],
    },

    // ---- L'AUTRE CONSOMMATEUR DU MÊME SOCKET -------------------------------------------------
    // `ChannelManager` n'est pas du SyncPvp : c'est la couche canaux générique. On l'ancre parce
    // qu'elle prouve que le socket vit HORS saison — c'est par elle qu'un témoin est atteignable
    // quand le PvP synchrone est fermé.
    {
        ns: NS_WEB, cls: "ChannelManager", methode: "HandleOnMessageFromConnectionReceived",
        arite: 1, sens: "in", corpsDe: 1,
    },
];

/** Ancre une porte sémantique. Les classes absentes du build sont RAPPORTÉES, jamais tues. */
function ancrerSem(porte: PorteSem): void {
    const cle = porte.cls + "." + porte.methode + "/" + porte.arite;
    const klass = findClassAnywhere(porte.ns, porte.cls);
    if (!klass) { layout[cle] = "CLASSE INTROUVABLE"; return; }
    const mi = findMethodByParamCount(klass, porte.methode, porte.arite);
    if (!mi || mi.ptr.isNull()) { layout[cle] = "NON RESOLUE"; return; }
    try {
        listeners.push(Interceptor.attach(mi.ptr, {
            onEnter(args) {
                try {
                    const champs: Record<string, string | number | null> = {};
                    for (const [i, nom] of porte.chaines ?? []) {
                        const s = chaine(args[i]);
                        champs[nom] = s ? s.lire(400) : null;
                    }
                    for (const [i, nom] of porte.entiers ?? []) {
                        try { champs[nom] = args[i].toInt32(); } catch { champs[nom] = null; }
                    }
                    if (porte.classeDe) {
                        const [i, nom] = porte.classeDe;
                        try { champs[nom] = readMsgClass(args[i]) ?? null; }
                        catch { champs[nom] = null; }
                    }
                    const idx = noter(
                        porte.sens, cle, null,
                        porte.corpsDe !== undefined ? chaine(args[porte.corpsDe]) : null,
                        false, champs,
                    );
                    if (porte.retourChaine) (this as unknown as CtxInvoc)._idx = idx;
                } catch { /* un capteur ne jette jamais */ }
            },
            onLeave(ret) {
                if (!porte.retourChaine) return;
                try {
                    const idx = (this as unknown as CtxInvoc)._idx;
                    if (typeof idx !== "number" || idx < 0 || idx >= tampon.length) return;
                    const s = chaine(ret);
                    const t = tampon[idx];
                    t.champs = t.champs ?? {};
                    t.champs["<retour>"] = s ? s.lire(200) : null;
                } catch { /* idem */ }
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

        // Étage sémantique. Une porte absente n'interrompt RIEN : elle est rapportée dans
        // `layout` et les autres s'arment. Un capteur qui refuse de s'armer en entier parce
        // qu'un symbole a bougé ne mesurerait plus rien du tout.
        const brutes = listeners.length;
        for (const porte of PORTES_SEM) ancrerSem(porte);

        Interceptor.flush();
        // On publie la ventilation brut / sémantique : `armes` seul ne dirait pas QUEL étage a
        // échoué, or ils échouent pour des raisons différentes (le brut suit le SDK client, le
        // sémantique suit la logique de bataille).
        const resume = {
            ok: true, armes: listeners.length,
            armesBrutes: brutes, armesSemantiques: listeners.length - brutes,
            attenduesSemantiques: PORTES_SEM.length, layout,
        };
        log("[ws-capture] arme : " + resume.armesBrutes + " brute(s) + "
            + resume.armesSemantiques + "/" + PORTES_SEM.length + " semantique(s)");
        return resume;
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
