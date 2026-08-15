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

import { findClassAnywhere, findMethodByParamCount, getFieldOffset } from "../il2cpp/helpers.js";
// Le FOYER de la resolution du `ViewCommandExecutor` -- importe, jamais re-marche.
import { executeurVivant, Refus as RefusVue } from "./view-command.js";
import { serializeToJson, isSerializerReady } from "../il2cpp/serializer.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
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
    {
        // Porteur du SEUIL DE RANG. `IsEligibleFor` compare le rang de l'unite a
        // `GetRequiredRankFor(entry.rarity)` -- un seuil qui depend du NIVEAU d'expedition du
        // joueur, donc introuvable dans le gameconfig. C'est la seule piece de la regle qui ne
        // se derive ni du plateau ni du roster.
        ns: "Idun.Source.IdunMeta.Logic.Features.Expedition.Progression.Level",
        cls: "ExpeditionLevelProgression",
        methodes: [["GetCurrentLevel", 0], ["GetRequiredRankFor", 1], ["GetMaxLevel", 0]],
    },
];

/** Derniere instance vue par classe. Vide = PAS ENCORE VUE, jamais << inexistante >>. */
const instances: Record<string, NativePointer> = {};

/** Le chemin de CHAQUE porteur depuis le `ViewCommandExecutor`, resolu PAR NOM.
 *
 *  CE QUI SUPPRIME LA DEPENDANCE A L'ECRAN. Les interceptions ci-dessus attendent un
 *  EVENEMENT (l'affichage de l'ecran d'Operations fait tirer `CanRefreshBoard`,
 *  `get_Points`, ...). Ces chemins-la se LISENT, donc ils marchent depuis n'importe quel
 *  ecran -- mesure du 2026-08-15, build `t6dpr4k06g` : les CINQ ont rendu leur classe
 *  CONCRETE alors que le jeu etait EN BATAILLE (`get_IsBattleActive` = true), sans qu'aucun
 *  ecran d'Operations soit affiche ni aucun clic emis.
 *
 *  Une seule racine porte toute la famille : `ExpeditionProgression` declare SEPT champs,
 *  dont `<Board>`, `<Level>`, `<UnitEligibility>` et `<GameEvents>`.
 *
 *  ⚠ Chemins par NOM DE CHAMP, jamais par les offsets mesures (+1152, +1160, +32, +48) :
 *  meme regle que pour `_viewCommandExecutor`, dont l'offset a deja bouge d'un build a
 *  l'autre. Un nom absent rend `null` en le DISANT, il ne se replie sur rien. */
const CHEMINS_EXECUTEUR: Record<string, string[]> = {
    ExpeditionProgression: ["_expeditionProgression"],
    ExpeditionProgressionData: ["_expeditionProgressionData"],
    ExpeditionLevelProgression: ["_expeditionProgression", "<Level>k__BackingField"],
    ExpeditionUnitEligibility: ["_expeditionProgression", "<UnitEligibility>k__BackingField"],
    ExpeditionBoardQuery: ["_expeditionProgression", "<Board>k__BackingField"],
};

/** Le `Il2CppClass*` d'un objet manage : son PREMIER champ. Sert a resoudre le pas SUIVANT
 *  sur la classe REELLE, pas sur le type DECLARE du champ -- un champ declare `IFoo` porte
 *  une implementation concrete dont les champs ne sont pas ceux de l'interface. */
function classeReelle(obj: NativePointer): NativePointer | null {
    try {
        const k = obj.readPointer();
        return k.isNull() ? null : k;
    } catch { return null; }
}

/** Le porteur d'une classe : l'intercepte s'il a tire, SINON celui de l'executeur.
 *
 *  L'ordre compte : un `this` capte au vol est l'instance que le jeu utilise VRAIMENT a cet
 *  instant ; l'executeur est le RATTRAPAGE, pour le cas -- desormais le cas normal -- ou
 *  aucun ecran n'a ete ouvert. Ce qui est resolu est MEMOISE dans `instances`, donc `vues`
 *  continue de dire la verite sur ce qui est disponible. */
function porteur(cls: string): NativePointer | null {
    const deja = instances[cls];
    if (deja) return deja;
    const chemin = CHEMINS_EXECUTEUR[cls];
    if (!chemin) return null;
    try {
        const exec = executeurVivant();
        if (typeof exec === "object" && exec !== null && (exec as RefusVue).ok === false) {
            return null;
        }
        let cur = exec as NativePointer;
        let k = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        for (const champ of chemin) {
            if (!k) return null;
            const off = getFieldOffset(k, champ);
            if (off < 0) return null;      // ⚠ -1 est *truthy* : tester `< 0`, jamais `||`
            cur = cur.add(off).readPointer();
            if (cur.isNull()) return null;
            k = classeReelle(cur);
        }
        instances[cls] = cur;
        return cur;
    } catch { return null; }
}

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

// ---------------------------------------------------------------------------------------
// ELIGIBILITE PAR OPERATION -- combien d'unites POSSEDEES peuvent partir, operation par
// operation, SANS ouvrir le moindre ecran de dispatch.
//
// Pourquoi c'est necessaire : l'ecran de dispatch n'est atteignable que pour UNE operation
// (les autres boutons levent), donc le pool des operations Chaos / sans restriction reste
// hors de portee par l'UI. Or le jeu CALCULE deja ce compte pour afficher ses widgets :
// `ExpeditionUnitEligibility$$CountEligibleUnits(entry)` tire une fois par operation au
// rendu du plateau. On lit son RETOUR.
//
// Un compte a zero est un RESULTAT, pas une panne : il dit qu'aucune unite possedee ne
// convient a cette operation -- et donc que son bonus est hors d'atteinte, ce qu'aucune
// autre voie ne nous disait.
// ---------------------------------------------------------------------------------------

interface Eligibilite {
    n: number; ts: number;
    expeditionId: string | null;
    grandAlliance: string | null;
    participants: number | null;
    /** Retour de `CountEligibleUnits`. `null` = appel non revenu / illisible. */
    eligibles: number | null;
}

const eligibilites: Eligibilite[] = [];

/** Extrait un champ scalaire d'un JSON sans le parser entierement (QuickJS, appels chauds). */
function champ(json: string, nom: string): string | null {
    const m = new RegExp("\"" + nom + "\"\\s*:\\s*(\"([^\"]*)\"|null|(-?\\d+))").exec(json);
    if (!m) return null;
    if (m[2] !== undefined) return m[2];
    if (m[3] !== undefined) return m[3];
    return null;
}

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
        // Eligibilite par operation : une porte, un retour entier, sept tirs au rendu.
        {
            const cle = "ExpeditionUnitEligibility.CountEligibleUnits";
            const klass = findClassAnywhere(
                "Idun.Source.IdunMeta.Logic.Features.Expedition.Progression.UnitEligibility",
                "ExpeditionUnitEligibility");
            const mi = klass ? findMethodByParamCount(klass, "CountEligibleUnits", 1) : null;
            if (!klass) { layout[cle] = "CLASSE INTROUVABLE"; }
            else if (!mi || mi.ptr.isNull()) { layout[cle] = "NON RESOLUE"; }
            else {
                try {
                    listeners.push(Interceptor.attach(mi.ptr, {
                        onEnter(args) {
                            try {
                                // `this` = l'ExpeditionUnitEligibility. On le retient : c'est
                                // lui qui porte `IsEligibleFor`, donc l'oracle unite-par-unite.
                                if (!args[0].isNull()) {
                                    instances["ExpeditionUnitEligibility"] = args[0];
                                }
                                const e: Eligibilite = {
                                    n: ++compteur, ts: Date.now(), expeditionId: null,
                                    grandAlliance: null, participants: null, eligibles: null,
                                };
                                // L'entree est petite (~1 Ko) et le tir est rare (7 par
                                // rendu) : la serialiser est moins fragile que de deviner
                                // des offsets de champ.
                                if (isSerializerReady() && !args[1].isNull()) {
                                    const j = serializeToJson(args[1]);
                                    if (j) {
                                        e.expeditionId = champ(j, "expeditionId");
                                        e.grandAlliance = champ(j, "grandAlliance");
                                        const p = champ(j, "participants");
                                        e.participants = p === null ? null : parseInt(p, 10);
                                    }
                                }
                                if (eligibilites.length >= CAP * 4) eligibilites.shift();
                                eligibilites.push(e);
                                (this as unknown as { _e?: Eligibilite })._e = e;
                            } catch { /* avale */ }
                        },
                        onLeave(ret) {
                            try {
                                const e = (this as unknown as { _e?: Eligibilite })._e;
                                if (e) e.eligibles = ret.toInt32();
                            } catch { /* avale */ }
                        },
                    }));
                    layout[cle] = true;
                } catch { layout[cle] = "ANCRAGE EN ECHEC"; }
            }
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
            // PAS DE REPLI SILENCIEUX SUR `vues[0]`. Mesure du 2026-08-10 : la porte du
            // plateau n'avait pas tire, et le repli a rendu `ok: true` sur un
            // `ExpeditionUnitEligibility` -- un objet sans rapport, serialise en `{}`, avec
            // `entrees: null`. Ca se lit comme un succes. Le porteur du plateau est
            // `ExpeditionProgressionData` et lui seul ; a defaut on REFUSE en le nommant.
            const cls = body?.classe || "ExpeditionProgressionData";
            const inst = porteur(cls);
            if (!inst) {
                return {
                    ok: false, vues, classe: cls,
                    err: "classe '" + cls + "' NON CAPTEE"
                       + (vues.length ? " (captees : " + vues.join(", ") + ")" : "")
                       + (CHEMINS_EXECUTEUR[cls]
                          ? " -- et son chemin depuis le ViewCommandExecutor ("
                            + CHEMINS_EXECUTEUR[cls].join(".") + ") n'a rien rendu : champ "
                            + "renomme sur ce build, ou nav pas encore initialisee."
                          : " -- aucun chemin d'executeur connu pour cette classe ; ouvre "
                            + "l'ecran Operations (Crusade -> Operations) APRES l'armement."),
                };
            }
            if (!isSerializerReady()) {
                return { ok: false, classe: cls, err: "serialiseur Newtonsoft NON RESOLU" };
            }
            let json: string | null = null;
            try { json = serializeToJson(inst); }
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

    // -----------------------------------------------------------------------------------
    // LE SEUIL DE RANG -- la seule piece de la regle d'eligibilite qui n'est ni dans le
    // plateau ni dans le roster.
    //
    // `ExpeditionUnitEligibility$$IsEligibleFor` (decompile) tient en quatre gates :
    //
    //     rarete de l'unite PRESENTE           (sinon : non debloquee)
    //     rarete de l'unite >= entry.rarity    (sinon : UnitLowRarity)
    //     rang de l'unite   >= level.GetRequiredRankFor(entry.rarity)   (sinon : UnitLowRank)
    //     entry.grandAlliance nul, ou egal a celui de l'unite
    //
    // Les trois premieres se calculent des qu'on tient le seuil ; la quatrieme sort du
    // gameconfig. Ce seuil-la depend du NIVEAU d'expedition du joueur : il monte quand le
    // joueur progresse, donc le figer serait le perimer.
    // -----------------------------------------------------------------------------------

    /** La table `rarete -> rang minimum` du niveau d'expedition COURANT.
     *  body: {} -> { ok, niveau, niveauMax, seuils } */
    ctx.rpc.expeditionRankRequirements = (): Promise<unknown> => queueOnMainThread(() => {
        const inst = porteur("ExpeditionLevelProgression");
        if (!inst) {
            return {
                ok: false, vues: Object.keys(instances),
                err: "AUCUNE instance d'ExpeditionLevelProgression -- ni captee a l'ecran, ni "
                   + "lisible en `_expeditionProgression.<Level>k__BackingField` sur le "
                   + "ViewCommandExecutor (champ renomme sur ce build, ou nav pas initialisee)",
            };
        }
        const klass = findClassAnywhere(
            "Idun.Source.IdunMeta.Logic.Features.Expedition.Progression.Level",
            "ExpeditionLevelProgression");
        if (!klass) return { ok: false, err: "ExpeditionLevelProgression introuvable" };
        const miReq = findMethodByParamCount(klass, "GetRequiredRankFor", 1);
        const miCur = findMethodByParamCount(klass, "GetCurrentLevel", 0);
        const miMax = findMethodByParamCount(klass, "GetMaxLevel", 0);
        if (!miReq) return { ok: false, err: "GetRequiredRankFor NON RESOLUE" };

        /** `System.Int32` rendu par `runtime_invoke` : BOXE, valeur utile a +0x10. */
        const entierBoxe = (p: NativePointer): number | null => {
            if (p.isNull()) return null;
            try { return p.add(0x10).readS32(); } catch { return null; }
        };
        const scalaire = (mi: typeof miCur): number | null => {
            if (!mi) return null;
            try { return entierBoxe(invokeMethod(mi.info, inst, null)); } catch { return null; }
        };

        // `UnitRarity` (enums.tsv) : 0=Common .. 5=Mythic.
        const RARETES = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic"];
        const seuils: Record<string, number | null> = {};
        for (let r = 0; r < RARETES.length; r++) {
            // Argument de type VALEUR : `runtime_invoke` attend un pointeur vers la donnee
            // NON boxee, pas un objet. (Le BOXAGE, lui, ne concerne que le RETOUR.)
            const arg = Memory.alloc(4);
            arg.writeS32(r);
            let v: number | null = null;
            try { v = entierBoxe(invokeMethod(miReq.info, inst, [arg])); } catch { v = null; }
            seuils[RARETES[r]] = v;
        }
        return {
            ok: true, ts: Date.now(),
            niveau: scalaire(miCur), niveauMax: scalaire(miMax),
            seuils,
            // Tri-etat assume : une rarete a `null` n'est PAS un seuil de 0. Un zero se lirait
            // << aucune exigence de rang >>, donc toute unite eligible -- l'inverse du vrai.
            illisibles: Object.keys(seuils).filter((k) => seuils[k] === null),
        };
    });

    /** Le compte d'eligibles pour des operations NOMMEES -- sans attendre que l'UI les rende.
     *
     *  `expeditionEligibility` (plus bas) est PASSIF : il lit ce que le jeu calcule au rendu,
     *  donc il ne voit que les widgets rendus. Mesure du 2026-08-10 : 4 operations sur 7, la
     *  virtualisation du plateau laissant les trois autres muettes. Ici on DEMANDE, sur les
     *  identifiants qu'on veut :
     *
     *      ExpeditionProgressionData$$GetExpeditionEntry(expeditionId) -> entry
     *      ExpeditionUnitEligibility$$CountEligibleUnits(entry)        -> Int32
     *
     *  body: { ids: string[] } -> { ok, comptes: {id: n|null}, absents } */
    ctx.rpc.expeditionEligibilityFor = (body?: { ids?: string[] }): Promise<unknown> =>
        queueOnMainThread(() => {
            const ids = body?.ids;
            if (!Array.isArray(ids) || ids.length === 0) {
                return { ok: false, err: "expeditionEligibilityFor: `ids` (liste non vide) "
                                       + "requis -- les `expeditionId` du plateau" };
            }
            const data = porteur("ExpeditionProgressionData");
            const elig = porteur("ExpeditionUnitEligibility");
            if (!data || !elig) {
                return {
                    ok: false, vues: Object.keys(instances),
                    err: "instance manquante : "
                       + (!data ? "ExpeditionProgressionData " : "")
                       + (!elig ? "ExpeditionUnitEligibility" : "")
                       + " -- ni captee a l'ecran, ni lisible depuis le ViewCommandExecutor",
                };
            }
            const kData = findClassAnywhere(
                "Idun.Source.IdunMeta.Logic.Features.Expedition.ProgressionData",
                "ExpeditionProgressionData");
            const kElig = findClassAnywhere(
                "Idun.Source.IdunMeta.Logic.Features.Expedition.Progression.UnitEligibility",
                "ExpeditionUnitEligibility");
            const miGet = kData ? findMethodByParamCount(kData, "GetExpeditionEntry", 1) : null;
            const miCnt = kElig ? findMethodByParamCount(kElig, "CountEligibleUnits", 1) : null;
            if (!miGet || !miCnt) {
                return { ok: false, err: (miGet ? "" : "GetExpeditionEntry ")
                                       + (miCnt ? "" : "CountEligibleUnits ") + "NON RESOLUE" };
            }
            const comptes: Record<string, number | null> = {};
            const absents: string[] = [];
            for (const id of ids) {
                if (typeof id !== "string" || !id) continue;
                let entry: NativePointer | null = null;
                try {
                    // Le DTO est un type REFERENCE : `runtime_invoke` rend le pointeur tel
                    // quel. Seuls les types VALEUR reviennent boxes.
                    entry = invokeMethod(miGet.info, data, [createManagedString(id)]);
                } catch { entry = null; }
                if (!entry || entry.isNull()) { absents.push(id); comptes[id] = null; continue; }
                try {
                    const r = invokeMethod(miCnt.info, elig, [entry]);
                    comptes[id] = r.isNull() ? null : r.add(0x10).readS32();
                } catch { comptes[id] = null; }
            }
            return {
                ok: true, ts: Date.now(), comptes,
                // `absents` = le plateau ne connait pas cet identifiant. Distinct d'un compte
                // `null`, qui veut dire << l'appel n'est pas revenu >>.
                absents,
                illisibles: Object.keys(comptes).filter((k) => comptes[k] === null
                                                              && absents.indexOf(k) < 0),
            };
        });

    /** Combien d'unites POSSEDEES sont eligibles, operation par operation.
     *  body: { reset?: true } -> { ok, count, entries } */
    ctx.rpc.expeditionEligibility = (body?: { reset?: boolean }): Promise<unknown> =>
        queueOnMainThread(() => {
            // On replie sur la DERNIERE mesure par operation : le plateau se re-rend a
            // chaque visite, et empiler les repetitions ferait lire sept operations comme
            // vingt et une.
            const dernier: Record<string, Eligibilite> = {};
            for (const e of eligibilites) {
                dernier[e.expeditionId || ("?" + e.n)] = e;
            }
            const out = {
                ok: true, arme: listeners.length > 0,
                brut: eligibilites.length, count: Object.keys(dernier).length,
                entries: Object.values(dernier),
                note: "un compte a 0 est un RESULTAT : aucune unite possedee ne convient a "
                    + "cette operation, donc son bonus est hors d'atteinte",
            };
            if (body?.reset) eligibilites.length = 0;
            return out;
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
