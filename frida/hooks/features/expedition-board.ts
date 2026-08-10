// expedition-board — LE PLATEAU D'OPERATIONS COMPLET, capte a l'application de la reponse.
//
// LE PROBLEME QUE CA RESOUT, ET POURQUOI LES DEUX AUTRES VOIES ECHOUENT.
//
// 1. PAR L'UI. Le plateau est VIRTUALISE : `uiList` n'enumere que les widgets ACTIFS et en
//    rend 4, alors que trois marqueurs par-widget (`Header/IconContainer`,
//    `Header/ReplaceButton`, `BottomLayout/CheatsContainer`) valent tous SEPT. Les autres sont
//    parques sous `WidgetPool(Clone)`, ou `uiClick` ne les resout meme pas. Mesure du
//    2026-08-10 : sur 7 exemplaires de `button_dispatch`, 3 sont parques et UN SEUL ouvre --
//    toujours la meme operation, reproduit sur 3 passes puis re-confirme en ciblant par `ptr`.
//    Lire le plateau a l'ecran, c'est donc lire 4 lignes sur 7 en croyant les avoir toutes.
//
// 2. PAR LE FIL. `net-capture` ancre `WwwWebHelper$$Post*` : il ne voit que ce qui PART. Le
//    plateau arrive en REPONSE. Mesure : l'ouverture de l'ecran emet bien
//    `FETCH_LIVE_EVENT {"liveEventId":"conflict_operations_20260811_1200"}`, mais la charge
//    utile revient par un chemin qu'aucune de nos portes n'ancre.
//
// => ON ANCRE L'ETAGE OU LA REPONSE EST APPLIQUEE. `ExpeditionPlayerStateDto` y arrive
// DESERIALISE, avec `board` complet -- donc les 7 entrees, leurs `bonusObjectives`, leur
// `participants`, leur `grandAlliance` et leurs recompenses, sans toucher a l'UI.
//
//     thor.Client.ResponseProcessing.GameStateSynchronizerLogic$$ApplyExpeditionProgress(
//         expeditions:ExpeditionPlayerStateDto)
//     Idun.Source.IdunMeta.Logic.Features.Expedition.ProgressionData.ExpeditionProgressionData$$
//         SyncFromPlayerState(dto:ExpeditionPlayerStateDto)
//     Idun.Source.IdunMeta.Logic.Features.Expedition.Progression.Commands.
//         ExpeditionClaimRewardApplier$$HandleClaimResponse(expeditions:..., error, errorContext)
//
// TROIS PORTES, ET LE JOURNAL PUBLIE `via`. Rien ne garantit qu'elles tirent toutes, ni
// qu'elles portent la meme charge : `SyncFromPlayerState` peut recevoir un delta la ou
// `ApplyExpeditionProgress` recoit l'etat complet. On les ancre toutes et on MESURE, au lieu
// d'elire la bonne a priori -- c'est la lecon de `PostString` contre `PostData`, ou n'ancrer
// qu'une porte rendait un zero silencieux.
//
// ON SERIALISE A CHAUD, ET C'EST DELIBERE. Le DTO est TRANSITOIRE : `SyncFromPlayerState`
// recopie son contenu dans `ExpeditionProgressionData`, donc rien ne garantit qu'il survive
// jusqu'a un dump differe. Garder le POINTEUR exposerait a un objet collecte -- on garde donc
// la CHAINE JSON, produite dans le hook. C'est plus cher au moment du tir (une poignee de fois
// par session, jamais un chemin chaud) et definitivement sur.
//
// ARME A LA DEMANDE, jamais auto-arme. LECTURE SEULE : aucun envoi, aucune mutation, et
// surtout AUCUN dispatch -- ce module ne fait que lire ce que le serveur vient de dire.

import { findClassAnywhere, findMethodByParamCount } from "../il2cpp/helpers.js";
import { serializeToJson, isSerializerReady } from "../il2cpp/serializer.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

/** Nombre de captures conservees. Le plateau est refetche a chaque ouverture d'ecran ; garder
 *  un historique court permet de comparer deux etats (avant/apres un dispatch, par exemple). */
const CAP = 12;
/** Borne de securite sur la taille d'un JSON conserve. */
const MAX_JSON = 4_000_000;

interface Capture {
    n: number;
    /** Epoch ms ABSOLU -- confrontable aux horodatages serveur portes par les charges. */
    ts: number;
    via: string;
    len: number | null;
    json: string | null;
    /** Renseigne quand le JSON a pu etre relu : nombre d'entrees de `board`. `null` = PAS
     *  MESURE (serialisation indisponible ou JSON illisible), jamais 0 par defaut. */
    entrees: number | null;
    err?: string;
}

const captures: Capture[] = [];
let compteur = 0;
const listeners: InvocationListener[] = [];
const layout: Record<string, unknown> = {};

/** Compte les entrees de `board` SANS parser tout le JSON cote Frida (QuickJS, charge
 *  potentiellement lourde) : on lit la valeur de `board` et on compte ses objets de premier
 *  niveau. Rend `null` si on ne sait pas -- jamais un zero fabrique. */
function compterEntrees(json: string): number | null {
    const i = json.indexOf("\"board\"");
    if (i < 0) return null;
    const d = json.indexOf("[", i);
    if (d < 0) return null;
    let prof = 0, n = 0, dansChaine = false, echap = false;
    for (let k = d; k < json.length; k++) {
        const c = json[k];
        if (dansChaine) {
            if (echap) { echap = false; continue; }
            if (c === "\\") { echap = true; continue; }
            if (c === "\"") dansChaine = false;
            continue;
        }
        if (c === "\"") { dansChaine = true; continue; }
        if (c === "[" || c === "{") { prof++; if (c === "{" && prof === 2) n++; continue; }
        if (c === "]" || c === "}") { prof--; if (prof === 0) return n; }
    }
    return null;
}

function noter(via: string, dto: NativePointer): void {
    if (captures.length >= CAP) captures.shift();
    const c: Capture = {
        n: ++compteur, ts: Date.now(), via, len: null, json: null, entrees: null,
    };
    try {
        if (!isSerializerReady()) {
            c.err = "serialiseur Newtonsoft NON RESOLU";
        } else if (dto.isNull()) {
            c.err = "DTO nul";
        } else {
            const j = serializeToJson(dto);
            if (j === null) {
                c.err = "serialisation en echec";
            } else if (j.length > MAX_JSON) {
                c.len = j.length;
                c.err = "JSON au-dela de la borne (" + MAX_JSON + ")";
            } else {
                c.json = j;
                c.len = j.length;
                c.entrees = compterEntrees(j);
            }
        }
    } catch (e) {
        c.err = "exception : " + String((e as Error).message || e).slice(0, 120);
    }
    captures.push(c);
}

// ---------------------------------------------------------------------------------------
// CAPTURE D'INSTANCE -- la voie qui MARCHE, et pourquoi les portes de reponse ne suffisent pas
//
// MESURE du 2026-08-10 (session 35) : l'ouverture de l'ecran Operations emet bien
// `FETCH_LIVE_EVENT`, verifie par `net-capture` (2 requetes, PostString + PostData), et
// AUCUNE des trois portes de reponse ci-dessus n'a tire -- 0 capture. Le plateau n'est donc
// pas (re)applique a ce moment : il est DEJA en memoire, et ce fetch concerne le module de
// live-event, pas le board.
//
// On ne devine pas le bon chemin de reponse : on prend l'objet qui DETIENT le plateau. On
// ancre quelques methodes d'instance des porteurs, on retient leur `this` au premier tir, et
// un RPC serialise a la demande. Ces objets appartiennent au jeu et vivent aussi longtemps que
// lui -- contrairement au DTO transitoire, stocker leur pointeur est sur.
// ---------------------------------------------------------------------------------------

interface PorteInstance { ns: string; cls: string; methodes: Array<[string, number]> }

const PORTES_INSTANCE: PorteInstance[] = [
    {
        ns: "Idun.Source.IdunMeta.Logic.Features.Expedition.ProgressionData",
        cls: "ExpeditionProgressionData",
        // `get_Points` alimente la barre de progression, `GetExpeditionEntry` est appele par la
        // construction des widgets : l'un des deux tire des que l'ecran s'affiche.
        methodes: [["get_Points", 0], ["GetExpeditionEntry", 1]],
    },
    {
        ns: "Idun.Source.IdunMeta.Logic.Features.Expedition.Progression",
        cls: "ExpeditionProgression",
        methodes: [["CanRefreshBoard", 0], ["IsCrusadeEventActive", 0]],
    },
];

/** Derniere instance vue par classe. Vide = PAS ENCORE VUE, jamais << inexistante >>. */
const instances: Record<string, NativePointer> = {};

interface Porte { ns: string; cls: string; methode: string; arite: number; iDto: number }

const PORTES: Porte[] = [
    {
        ns: "thor.Client.ResponseProcessing", cls: "GameStateSynchronizerLogic",
        methode: "ApplyExpeditionProgress", arite: 1, iDto: 1,
    },
    {
        ns: "Idun.Source.IdunMeta.Logic.Features.Expedition.ProgressionData",
        cls: "ExpeditionProgressionData",
        methode: "SyncFromPlayerState", arite: 1, iDto: 1,
    },
    {
        ns: "Idun.Source.IdunMeta.Logic.Features.Expedition.Progression.Commands",
        cls: "ExpeditionClaimRewardApplier",
        methode: "HandleClaimResponse", arite: 3, iDto: 1,
    },
];

export function register(ctx: Ctx): void {
    /** Arme les portes. Idempotent. body: {} -> { ok, armes, layout } */
    ctx.rpc.expeditionBoardArm = (): Promise<unknown> => queueOnMainThread(() => {
        if (listeners.length > 0) {
            return { ok: true, deja: true, armes: listeners.length, layout };
        }
        for (const p of PORTES) {
            const cle = p.cls + "." + p.methode;
            const klass = findClassAnywhere(p.ns, p.cls);
            if (!klass) { layout[cle] = "CLASSE INTROUVABLE"; continue; }
            const mi = findMethodByParamCount(klass, p.methode, p.arite);
            if (!mi || mi.ptr.isNull()) { layout[cle] = "NON RESOLUE"; continue; }
            try {
                listeners.push(Interceptor.attach(mi.ptr, {
                    onEnter(args) {
                        // Un capteur ne jette JAMAIS : une exception ici remonterait dans le
                        // traitement de la reponse serveur du jeu.
                        try { noter(cle, args[p.iDto]); } catch { /* avale */ }
                    },
                }));
                layout[cle] = true;
            } catch { layout[cle] = "ANCRAGE EN ECHEC"; }
        }
        // Portes d'INSTANCE : on retient `this`, sans rien serialiser dans le hook (ces
        // methodes-la SONT sur un chemin d'affichage, donc potentiellement chaudes).
        for (const p of PORTES_INSTANCE) {
            const klass = findClassAnywhere(p.ns, p.cls);
            if (!klass) { layout["inst:" + p.cls] = "CLASSE INTROUVABLE"; continue; }
            const armees: string[] = [];
            for (const [nom, arite] of p.methodes) {
                const mi = findMethodByParamCount(klass, nom, arite);
                if (!mi || mi.ptr.isNull()) continue;
                try {
                    listeners.push(Interceptor.attach(mi.ptr, {
                        onEnter(args) {
                            try {
                                if (!args[0].isNull()) instances[p.cls] = args[0];
                            } catch { /* avale */ }
                        },
                    }));
                    armees.push(nom + "/" + arite);
                } catch { /* porte suivante */ }
            }
            layout["inst:" + p.cls] = armees.length ? armees.join(",") : "AUCUNE RESOLUE";
        }
        layout["serialiseur"] = isSerializerReady() ? true : "NON RESOLU";
        Interceptor.flush();
        log("[expedition-board] arme : " + listeners.length + " porte(s)");
        return {
            ok: listeners.length > 0, armes: listeners.length,
            attendues: PORTES.length, layout,
            // Le plateau est refetche a l'ouverture de l'ecran Operations : c'est le geste qui
            // fait tirer ce capteur. On le DIT, pour qu'un `count: 0` ne se lise pas comme
            // << il n'y a pas de plateau >>.
            note: "ouvre l'ecran Operations (Crusade -> Operations) pour declencher un fetch",
        };
    });

    /** body: { reset?, dernier?: true, sansJson?: true }
     *  `dernier` ne rend que la capture la plus recente -- le cas courant. */
    ctx.rpc.expeditionBoardDump = (body?: {
        reset?: boolean; dernier?: boolean; sansJson?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        let sel = captures.slice();
        if (body?.dernier) sel = sel.slice(-1);
        const entries = sel.map((c) => (body?.sansJson ? { ...c, json: null } : c));
        const out = {
            ok: true, arme: listeners.length > 0, count: captures.length, plafond: CAP,
            maintenant: Date.now(), entries, layout,
        };
        if (body?.reset) captures.length = 0;
        return out;
    });

    /** Serialise L'INSTANCE captee -- la voie qui rend reellement le plateau.
     *  body: { classe?: string } -> { ok, classe, json, entrees }
     *
     *  Rend `ok: false` avec la liste de ce qui a ete VU si rien n'est disponible : une
     *  reponse vide se lirait << pas de plateau >>, alors que la cause est << l'ecran n'a pas
     *  encore ete ouvert depuis l'armement >>. */
    ctx.rpc.expeditionBoardRead = (body?: { classe?: string }): Promise<unknown> =>
        queueOnMainThread(() => {
            const vues = Object.keys(instances);
            const cls = body?.classe
                || (instances["ExpeditionProgressionData"] ? "ExpeditionProgressionData"
                    : vues[0]);
            if (!cls || !instances[cls]) {
                return {
                    ok: false, vues,
                    err: vues.length
                        ? "classe '" + String(body?.classe) + "' non captee"
                        : "AUCUNE instance captee -- ouvre l'ecran Operations "
                          + "(Crusade -> Operations) apres l'armement, puis relance",
                };
            }
            if (!isSerializerReady()) {
                return { ok: false, classe: cls, err: "serialiseur Newtonsoft NON RESOLU" };
            }
            let json: string | null = null;
            try { json = serializeToJson(instances[cls]); }
            catch (e) {
                return { ok: false, classe: cls,
                         err: "exception : " + String((e as Error).message || e).slice(0, 160) };
            }
            if (json === null) {
                return { ok: false, classe: cls, err: "serialisation en echec" };
            }
            return {
                ok: true, classe: cls, vues, len: json.length,
                entrees: compterEntrees(json), ts: Date.now(),
                json: json.length <= MAX_JSON ? json : null,
                tronque: json.length > MAX_JSON ? json.slice(0, 4000) : undefined,
            };
        });

    ctx.rpc.expeditionBoardDisarm = (): Promise<unknown> => queueOnMainThread(() => {
        for (const l of listeners) { try { l.detach(); } catch { /* deja parti */ } }
        listeners.length = 0;
        return { ok: true, restant: captures.length };
    });

    ctx.rpc.expeditionBoardStatus = (): Promise<unknown> => queueOnMainThread(() => ({
        ok: true, arme: listeners.length > 0, portes: listeners.length,
        count: captures.length, maintenant: Date.now(),
        derniere: captures.length
            ? {
                n: captures[captures.length - 1].n, ts: captures[captures.length - 1].ts,
                via: captures[captures.length - 1].via,
                entrees: captures[captures.length - 1].entrees,
                len: captures[captures.length - 1].len,
                err: captures[captures.length - 1].err,
            }
            : null,
        layout,
    }));
}
