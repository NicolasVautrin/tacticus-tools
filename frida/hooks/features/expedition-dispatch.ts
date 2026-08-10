// expedition-dispatch — ENVOYER une Operation sans passer par l'ecran.
//
// ⚠ CE MODULE ECRIT. C'est le seul de la famille Expedition qui ne soit pas en lecture
// seule, et il vit dans son propre fichier pour cette raison : un envoi immobilise des
// personnages pour la duree de l'operation (10 h sur le plateau du 2026-08-10). Le
// melanger aux capteurs rendrait un `expeditionBoard*` innocent indistinguable d'un geste
// qui engage le compte.
//
// LA PORTE, ET POURQUOI CELLE-LA
//
//     Idun.Source.IdunMeta.Logic.Features.Expedition.Progression.ExpeditionGameEvents$$
//         DispatchExpedition(expeditionId:System.String,
//                            unitIds:System.Collections.Generic.List<System.String>,
//                            bonusFulfilled:System.Boolean,
//                            callback:System.Action<System.Boolean>)
//
// C'est l'etage LOGIQUE, et il prend exactement ce qu'un plan produit : un identifiant
// d'operation et une liste d'unites.
//
// ⚠ NE PAS CONFONDRE AVEC `ExpeditionProgressionData$$DispatchExpeditionLocally`, qui
// porte les memes trois premiers arguments. Celle-la n'est que l'ECHO LOCAL : l'appeler
// seule avancerait l'etat client sans rien envoyer au serveur -- un mensonge d'affichage
// qui se corrigerait au prochain sync, apres avoir fait croire au depart. On l'ancre pour
// l'OBSERVER, jamais pour l'appeler.
//
// ON OBSERVE AVANT D'ECRIRE, ET LES DEUX PORTES SONT ANCREES POUR CA. Un envoi fait par
// l'ecran fait tirer la chaine reelle : on lit alors les arguments VRAIS (ordre, valeur de
// `bonusFulfilled`, forme des identifiants) au lieu de les deduire d'une signature. Le
// journal est ce qui autorise a reproduire -- pas la lecture du decompile seule.
//
// GARDE : `expeditionDispatch` REFUSE sans `confirmer: true`. Ce n'est pas de la ceremonie :
// le RPC est a un caractere de distance d'un `expeditionBoardRead`, et les deux vivent dans
// la meme console.

import {
    findClassAnywhere, findMethodByParamCount, methodParamClass,
    class_get_fields, field_get_name, field_get_offset,
    s as cstr, readIl2cppString, MethodRef,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString, createObject } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

/** Borne de securite sur la taille d'un envoi. Le plateau du 2026-08-10 plafonne a 5
 *  participants ; la borne est large mais elle existe pour qu'un appelant fautif ne
 *  parte pas avec le roster entier. */
const MAX_UNITES = 12;

/** ⛔ L'envoi natif est FERME (cf. le bloc de refus dans `expeditionDispatch`). Ce n'est
 *  PAS un reglage a basculer parce qu'on est presse : le rouvrir demande d'avoir ISOLE
 *  pourquoi `runtime_invoke` sur cette chaine tue le process -- ce qu'aucune des trois
 *  tentatives n'a etabli. Une constante, pas un RPC : un interrupteur accessible serait
 *  actionne. */
const AUTORISER_ENVOI_NATIF = false;

interface Envoi {
    n: number;
    ts: number;
    /** `observe` = vu passer (l'ecran, ou nous) ; `emis` = c'est NOUS qui l'avons appele. */
    origine: "observe" | "emis";
    via: string;
    expeditionId: string | null;
    unitIds: string[] | null;
    bonusFulfilled: boolean | null;
    /** Renseigne seulement pour `emis`. */
    err?: string;
}

const journal: Envoi[] = [];
let compteur = 0;

const listeners: InvocationListener[] = [];
const layout: Record<string, unknown> = {};

let miDispatch: MethodRef | null = null;
let instanceEvents: NativePointer | null = null;
/** `ExpeditionProgression`, le porteur qui donne acces a tous les sous-objets. */
let instanceProgression: NativePointer | null = null;
let offGameEvents = -1;
/** La classe CONCRETE attendue pour `this`. Sert de garde, pas de decor. */
let klassEvents: NativePointer | null = null;

/** Le `Il2CppClass*` d'un objet managé : c'est son PREMIER champ.
 *
 *  ⚠ CETTE GARDE EXISTE PARCE QUE SON ABSENCE A COUTE DEUX INCIDENTS. Un pointeur
 *  d'objet ne porte pas son type dans notre code TypeScript : `NativePointer` est
 *  `NativePointer`. Appliquer le `MethodInfo` d'une classe a l'instance d'une AUTRE fait
 *  lire ses champs a des offsets qui ne veulent rien dire -- sans erreur, jusqu'au
 *  dereferencement fatal. Comparer la classe est le seul controle qui le voie AVANT. */
function estDeClasse(obj: NativePointer, klass: NativePointer | null): boolean | null {
    if (!klass) return null;
    try { return obj.readPointer().equals(klass); } catch { return null; }
}

/** Offset d'un champ, resolu PAR SON NOM. Rend -1 si le nom n'existe pas -- on refuse
 *  alors de lire, plutot que de dereferencer un offset supposé. */
function offsetChamp(klass: NativePointer, nom: string): number {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        if (cstr(field_get_name(f) as NativePointer) === nom) {
            return field_get_offset(f) as number;
        }
    }
    return -1;
}

/** L'`ExpeditionGameEvents` vivant.
 *
 *  DEUX VOIES, et la seconde existe parce que la premiere est CIRCULAIRE : l'instance ne
 *  se capte au vol qu'a un envoi, or il faut l'instance POUR envoyer. `ExpeditionProgression`
 *  la porte en champ (`<GameEvents>k__BackingField`), et ce porteur-la, lui, se capte des
 *  qu'un ecran d'Operations s'affiche.
 *
 *  Le champ est lu par un offset RESOLU PAR NOM a l'armement. Ses accesseurs
 *  (`get_GameEvents`) n'existent pas dans la table : corps trivial, donc DEDUPLIQUE par
 *  IL2CPP -- l'absence n'y prouve rien, et il n'y a rien a invoquer. */
function evenements(): NativePointer | null {
    if (instanceEvents) return instanceEvents;
    if (instanceProgression && offGameEvents >= 0) {
        try {
            const p = instanceProgression.add(offGameEvents).readPointer();
            if (!p.isNull()) return p;
        } catch { /* rend null */ }
    }
    return null;
}

/** Disposition de `List<System.String>`, MESUREE sur la classe reelle (jamais supposee). */
interface DispoListe {
    klass: NativePointer;
    offItems: number;
    offSize: number;
    ctor: MethodRef | null;
    add: MethodRef | null;
}
let dispoListe: DispoListe | null = null;

function mesurerListe(klass: NativePointer): DispoListe | null {
    // Les offsets de `_items` / `_size` sont stables sur IL2CPP x64, mais les SUPPOSER
    // ferait lire n'importe quoi en silence si la disposition changeait. On les prend
    // dans la table des champs, et on refuse si l'un des deux manque.
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    let offItems = -1;
    let offSize = -1;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        const nom = cstr(field_get_name(f) as NativePointer);
        if (nom === "_items") offItems = field_get_offset(f) as number;
        else if (nom === "_size") offSize = field_get_offset(f) as number;
    }
    if (offItems < 0 || offSize < 0) return null;
    return {
        klass, offItems, offSize,
        ctor: findMethodByParamCount(klass, ".ctor", 0),
        add: findMethodByParamCount(klass, "Add", 1),
    };
}

/** Lit une `List<System.String>` par sa memoire -- pas d'invocation dans un hook. */
function lireListe(p: NativePointer, d: DispoListe): string[] | null {
    if (p.isNull()) return null;
    try {
        const size = p.add(d.offSize).readS32();
        if (size < 0 || size > 512) return null;
        const items = p.add(d.offItems).readPointer();
        if (items.isNull()) return size === 0 ? [] : null;
        const out: string[] = [];
        for (let i = 0; i < size; i++) {
            const e = items.add(0x20 + i * Process.pointerSize).readPointer();
            out.push(e.isNull() ? "<null>" : (readIl2cppString(e) ?? "<illisible>"));
        }
        return out;
    } catch { return null; }
}

function noter(via: string, origine: Envoi["origine"], id: NativePointer,
               liste: NativePointer, bonus: NativePointer | number): void {
    const e: Envoi = {
        n: ++compteur, ts: Date.now(), origine, via,
        expeditionId: id.isNull() ? null : readIl2cppString(id),
        unitIds: dispoListe ? lireListe(liste, dispoListe) : null,
        bonusFulfilled: typeof bonus === "number"
            ? bonus !== 0
            : (bonus.isNull() ? null : (bonus.toInt32() & 1) !== 0),
    };
    if (journal.length >= 64) journal.shift();
    journal.push(e);
    log("[expedition-dispatch] " + origine + " " + via + " : "
        + String(e.expeditionId) + " <- " + JSON.stringify(e.unitIds)
        + " bonus=" + String(e.bonusFulfilled));
}

export function register(ctx: Ctx): void {
    /** Arme l'OBSERVATION. N'envoie rien. body: {} -> { ok, armes, layout } */
    ctx.rpc.expeditionDispatchArm = (): Promise<unknown> => queueOnMainThread(() => {
        if (listeners.length > 0) {
            const e = evenements();
            return { ok: true, deja: true, armes: listeners.length, layout,
                     instanceVue: e !== null,
                     source: instanceEvents ? "captee au vol"
                         : (instanceProgression ? "champ <GameEvents>" : null),
                     classeOk: e ? estDeClasse(e, klassEvents) : null };
        }
        const kEvents = findClassAnywhere(
            "Idun.Source.IdunMeta.Logic.Features.Expedition.Progression",
            "ExpeditionGameEvents");
        if (!kEvents) return { ok: false, error: "ExpeditionGameEvents introuvable" };
        klassEvents = kEvents;
        miDispatch = findMethodByParamCount(kEvents, "DispatchExpedition", 4);
        layout["ExpeditionGameEvents.DispatchExpedition"] = miDispatch ? true : "NON RESOLUE";
        if (!miDispatch) return { ok: false, error: "DispatchExpedition NON RESOLUE", layout };

        // La classe de la liste vient de la SIGNATURE NATIVE, pas d'une recherche par nom :
        // `List<System.String>` est un generique INFLATE, absent de `classes.tsv`, et le
        // chercher par nom rendrait au mieux la definition ouverte.
        const kListe = methodParamClass(miDispatch.info, 1);
        dispoListe = kListe ? mesurerListe(kListe) : null;
        layout["List<String>"] = dispoListe
            ? { _items: dispoListe.offItems, _size: dispoListe.offSize,
                ctor: !!dispoListe.ctor, Add: !!dispoListe.add }
            : "DISPOSITION NON MESUREE";

        // Le porteur : `ExpeditionProgression` detient `GameEvents` en champ. On ancre deux
        // de ses methodes pour retenir `this` -- l'une des deux tire des que l'ecran
        // d'Operations s'affiche.
        const kProg = findClassAnywhere(
            "Idun.Source.IdunMeta.Logic.Features.Expedition.Progression",
            "ExpeditionProgression");
        offGameEvents = kProg ? offsetChamp(kProg, "<GameEvents>k__BackingField") : -1;
        layout["ExpeditionProgression.<GameEvents>"] = offGameEvents >= 0
            ? "+0x" + offGameEvents.toString(16)
            : "CHAMP INTROUVABLE";
        if (kProg && offGameEvents >= 0) {
            for (const [nom, arite] of [["CanRefreshBoard", 0],
                                        ["IsCrusadeEventActive", 0]] as Array<[string, number]>) {
                const mi = findMethodByParamCount(kProg, nom, arite);
                if (!mi || mi.ptr.isNull()) continue;
                try {
                    listeners.push(Interceptor.attach(mi.ptr, {
                        onEnter(args) {
                            try { if (!args[0].isNull()) instanceProgression = args[0]; }
                            catch { /* avale */ }
                        },
                    }));
                } catch { /* porte suivante */ }
            }
        }

        const portes: Array<[string, NativePointer | null, string, number]> = [
            ["ExpeditionGameEvents.DispatchExpedition", kEvents, "DispatchExpedition", 4],
            ["ExpeditionProgressionData.DispatchExpeditionLocally",
             findClassAnywhere(
                 "Idun.Source.IdunMeta.Logic.Features.Expedition.ProgressionData",
                 "ExpeditionProgressionData"), "DispatchExpeditionLocally", 3],
        ];
        for (const [cle, klass, nom, arite] of portes) {
            if (!klass) { layout[cle] = "CLASSE INTROUVABLE"; continue; }
            const mi = findMethodByParamCount(klass, nom, arite);
            if (!mi || mi.ptr.isNull()) { layout[cle] = "NON RESOLUE"; continue; }
            try {
                // ⚠ `this` NE SE STASHE QUE DEPUIS SA PROPRE PORTE.
                //
                // Le premier jet ecrivait `instanceEvents = args[0]` pour LES DEUX portes.
                // Or `DispatchExpeditionLocally` est portee par `ExpeditionProgressionData`,
                // et elle tire APRES : `instanceEvents` finissait donc par contenir un
                // `ExpeditionProgressionData`. Invoquer `DispatchExpedition` dessus lit
                // `this+0x10` comme `_dispatchCommand` alors que c'est tout autre chose --
                // erreur native, MESUREE le 2026-08-10.
                //
                // Le piege est fourbe : le hook `observe` tire quand meme (un `Interceptor`
                // se declenche sur l'ADRESSE de la fonction, quel que soit `this`), donc le
                // journal montrait un appel << reussi >> jusqu'a l'erreur.
                const estPorteur = klass === kEvents;
                listeners.push(Interceptor.attach(mi.ptr, {
                    onEnter(args) {
                        // Un capteur ne jette JAMAIS : on est sur le chemin d'un envoi reel.
                        try {
                            if (estPorteur && !args[0].isNull()) instanceEvents = args[0];
                            noter(cle, "observe", args[1], args[2], args[3]);
                        } catch { /* avale */ }
                    },
                }));
                layout[cle] = true;
            } catch { layout[cle] = "ANCRAGE EN ECHEC"; }
        }
        Interceptor.flush();
        // DIAGNOSTIC EN LECTURE : l'objet joignable est-il de la bonne classe ? On le dit
        // ICI, sans rien envoyer -- c'est la question qu'il fallait pouvoir poser avant
        // d'invoquer, et qu'aucun RPC ne permettait de poser.
        const evt = evenements();
        return { ok: true, armes: listeners.length, layout,
                 instanceVue: evt !== null,
                 source: instanceEvents ? "captee au vol"
                     : (instanceProgression ? "champ <GameEvents>" : null),
                 classeOk: evt ? estDeClasse(evt, klassEvents) : null,
                 note: "OBSERVATION seule. L'instance se capte au PREMIER envoi -- fais-en "
                     + "un par l'ecran avant d'esperer envoyer par RPC." };
    });

    /** Le journal des envois VUS et EMIS. body: { reset?: true } */
    ctx.rpc.expeditionDispatchJournal = (body?: { reset?: boolean }): Promise<unknown> =>
        queueOnMainThread(() => {
            const e = evenements();
            const out = { ok: true, arme: listeners.length > 0, count: journal.length,
                          instanceVue: e !== null,
                          source: instanceEvents ? "captee au vol"
                              : (instanceProgression ? "champ <GameEvents>" : null),
                          classeOk: e ? estDeClasse(e, klassEvents) : null,
                          dispoListe: dispoListe
                              ? { _items: dispoListe.offItems, _size: dispoListe.offSize }
                              : null,
                          envois: journal.slice() };
            if (body?.reset) journal.length = 0;
            return out;
        });

    /** ⚠ ENVOIE. Immobilise les unites pour la duree de l'operation.
     *
     *  body: { expeditionId, unitIds: string[], bonusFulfilled?: boolean,
     *          confirmer: true } */
    ctx.rpc.expeditionDispatch = (body?: {
        expeditionId?: string; unitIds?: string[]; bonusFulfilled?: boolean;
        participants?: number; confirmer?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        // ⛔ VOIE FERMEE. `runtime_invoke` SUR CETTE CHAINE TUE LE JEU, CAUSE INCONNUE.
        //
        // BILAN MESURE du 2026-08-10 -- trois tentatives, trois echecs, zero succes :
        //
        //   #1  2 unites / 3 places, classe correcte           -> PROCESS MORT
        //   #2  4 unites / 4 places, classe FAUSSE (bug ici)   -> exception capturee
        //   #3  4 unites / 4 places, classe VERIFIEE True,
        //       `participants` verifie, callback innocente     -> PROCESS MORT
        //
        // Le seul envoi qui ait JAMAIS abouti est celui fait A LA MAIN, par l'ecran.
        //
        // CE QUE J'AI CRU, ET QUI EST FAUX. Apres #1 et #2 j'avais conclu a deux causes
        // distinctes -- equipe incomplete d'un cote, mauvaise classe de l'autre -- et pose
        // une garde pour chacune. #3 les avait TOUTES LES DEUX vertes et a tue le jeu
        // pareil. Le raisonnement etait plausible et il etait faux : deux echecs suffisent
        // toujours a fabriquer deux causes, ca ne les rend pas vraies.
        //
        // CE QUI RESTE ETABLI, ET QUI N'EST PAS RIEN :
        //   - les ARGUMENTS sont bons (journal d'un envoi reel : GUID + ids internes +
        //     `bonusFulfilled` -- identiques a ce qu'on construit) ;
        //   - le callback nul est TOLERE (`<Execute>b__0` teste `!= 0` dans les deux
        //     branches) ;
        //   - l'objet du champ `<GameEvents>` est de la BONNE classe.
        // Rien de tout ca n'explique la mort du process. La cause est en aval, dans
        // `DispatchExpeditionCommand$$Execute` ou plus loin (client web, closure), et elle
        // n'a pas ete isolee.
        //
        // POUR ROUVRIR, il faut une EXPLICATION, pas une garde de plus : instrumenter
        // `Execute` pas a pas (ancrer ses appels sortants et voir lequel ne revient pas),
        // ou comparer octet a octet la pile d'un appel UI et du notre. Tant que ce n'est
        // pas fait, toute nouvelle garde ne fera que deplacer le point de rupture -- c'est
        // exactement ce qu'ont fait les deux precedentes.
        //
        // La voie SURE existe et coute peu : piloter l'ECRAN (`uiScroll` + `uiClick`), qui
        // passe par le chemin que le jeu supporte.
        if (!AUTORISER_ENVOI_NATIF) {
            return {
                ok: false, refus: "voie fermee",
                err: "expeditionDispatch est FERME : 3 tentatives par runtime_invoke, "
                   + "2 process morts, 0 succes, cause NON IDENTIFIEE. Les gardes posees "
                   + "(classe, completude) etaient vertes au dernier crash. Passe par "
                   + "l'ecran, ou isole la cause dans `DispatchExpeditionCommand$$Execute` "
                   + "avant de rouvrir.",
                bilan: {tentatives: 3, processMorts: 2, succes: 0},
            };
        }
        if (body?.confirmer !== true) {
            return { ok: false, refus: "confirmation",
                     err: "expeditionDispatch ENVOIE et immobilise les unites. Repasse "
                        + "avec `confirmer: true` si c'est bien ce que tu veux." };
        }
        const id = body?.expeditionId;
        const unites = body?.unitIds;
        if (typeof id !== "string" || !id) {
            return { ok: false, err: "`expeditionId` (chaine non vide) requis" };
        }
        if (!Array.isArray(unites) || unites.length === 0) {
            return { ok: false, err: "`unitIds` (liste non vide) requis" };
        }
        if (unites.length > MAX_UNITES) {
            return { ok: false, err: unites.length + " unites > borne " + MAX_UNITES };
        }
        if (unites.some((u) => typeof u !== "string" || !u)) {
            return { ok: false, err: "`unitIds` contient une entree non-chaine" };
        }
        // ⚠ L'EQUIPE DOIT ETRE COMPLETE, ET C'EST LA GARDE QUI MANQUAIT AU CRASH DUR.
        //
        // Recoupement des deux envois du 2026-08-10 :
        //     2 unites pour 3 places, classe CORRECTE  -> le jeu MEURT
        //     4 unites pour 4 places, classe fausse    -> erreur capturee, jeu vivant
        //
        // La couche logique ne verifie PAS le compte : c'est l'ECRAN qui le fait
        // (`ExpeditionDispatchScreen$$HandleOnDispatchTapped` retourne sans envoyer si
        // `SelectedCount() < ParticipantsRequired`). En appelant la logique directement on
        // court-circuite ce controle, et `Execute` deref au-dela de ce qu'on lui a donne.
        //
        // `participants` est donc EXIGE de l'appelant : le deduire serait le deviner, et
        // c'est precisement ce qu'on ne veut plus faire ici.
        const places = body?.participants;
        if (typeof places !== "number" || !Number.isInteger(places) || places < 1) {
            return { ok: false, err: "`participants` (entier >= 1) REQUIS -- le nombre de "
                                   + "places de l'operation. La couche logique ne le "
                                   + "verifie pas ; une equipe incomplete a TUE le jeu." };
        }
        if (unites.length !== places) {
            return { ok: false, refus: "equipe incomplete",
                     err: "l'operation a " + places + " place(s) et l'equipe en compte "
                        + unites.length + " -- ENVOI ANNULE. L'ecran refuserait aussi, "
                        + "mais la couche logique, elle, DEREFERENCE au-dela." };
        }
        const ev = evenements();
        if (!ev || !miDispatch) {
            return {
                ok: false,
                err: ev
                    ? "DispatchExpedition NON RESOLUE"
                    : "AUCUN ExpeditionGameEvents joignable -- ni capte au vol, ni lisible "
                      + "dans `ExpeditionProgression.<GameEvents>`. Arme, puis ouvre l'ecran "
                      + "Operations (Crusade -> Operations) pour que le porteur passe.",
            };
        }
        if (!dispoListe || !dispoListe.ctor || !dispoListe.add) {
            return { ok: false, err: "List<String> : disposition ou .ctor/Add NON RESOLUS",
                     layout: layout["List<String>"] };
        }
        // LA GARDE DE TYPE, avant tout le reste. Un `this` de la mauvaise classe fait lire
        // `this+0x10` comme `_dispatchCommand` alors que c'est autre chose : erreur native
        // en aval, loin d'ici, et le hook d'observation tire quand meme (il se declenche
        // sur l'ADRESSE de la fonction) -- donc le journal a l'air normal jusqu'au bout.
        const bonneClasse = estDeClasse(ev, klassEvents);
        if (bonneClasse !== true) {
            return {
                ok: false, refus: "classe",
                err: "l'objet vise n'est PAS un ExpeditionGameEvents ("
                   + (bonneClasse === null ? "classe ILLISIBLE" : "classe differente")
                   + ") -- ENVOI ANNULE. C'est exactement la faute qui a tue le jeu le "
                   + "2026-08-10 : le MethodInfo d'une classe applique a l'instance d'une "
                   + "autre.",
                classeObjet: (() => {
                    try { return ev.readPointer().toString(); } catch { return null; }
                })(),
                classeAttendue: klassEvents ? klassEvents.toString() : null,
            };
        }
        // Construction de la `List<System.String>` : classe prise dans la signature.
        let liste: NativePointer;
        try {
            liste = createObject(dispoListe.klass);
            invokeMethod(dispoListe.ctor.info, liste, null);
            for (const u of unites) {
                invokeMethod(dispoListe.add.info, liste, [createManagedString(u)]);
            }
        } catch (e) {
            return { ok: false,
                     err: "construction de la liste : "
                        + String((e as Error).message || e).slice(0, 160) };
        }
        // Relecture AVANT envoi : si la liste construite ne contient pas ce qu'on croit,
        // on ne part pas. Un envoi est irreversible a l'echelle de l'operation.
        const relu = lireListe(liste, dispoListe);
        if (!relu || relu.length !== unites.length
            || relu.some((v, i) => v !== unites[i])) {
            return { ok: false, err: "la liste construite ne se relit pas identique -- "
                                   + "ENVOI ANNULE", attendu: unites, relu };
        }
        const bonus = Memory.alloc(4);
        bonus.writeS32(body?.bonusFulfilled ? 1 : 0);
        const e: Envoi = {
            n: ++compteur, ts: Date.now(), origine: "emis",
            via: "expeditionDispatch", expeditionId: id, unitIds: unites.slice(),
            bonusFulfilled: !!body?.bonusFulfilled,
        };
        try {
            // `callback` a null : le jeu s'en sert pour rafraichir SON ecran, qu'on n'a pas
            // ouvert. Le hook d'observation nous dira si l'appel est bien parti.
            invokeMethod(miDispatch.info, ev,
                         [createManagedString(id), liste, bonus, ptr(0)]);
        } catch (ex) {
            e.err = String((ex as Error).message || ex).slice(0, 200);
        }
        if (journal.length >= 64) journal.shift();
        journal.push(e);
        return {
            ok: !e.err, envoi: e,
            note: "Verifie par `expeditionDispatchJournal` qu'une entree `observe` de "
                + "`DispatchExpeditionLocally` a suivi : c'est elle qui atteste que la "
                + "chaine du jeu a bien traite l'envoi, pas notre propre appel.",
        };
    });

    ctx.rpc.expeditionDispatchDisarm = (): Promise<unknown> => queueOnMainThread(() => {
        for (const l of listeners) { try { l.detach(); } catch { /* deja parti */ } }
        listeners.length = 0;
        return { ok: true, instanceConservee: evenements() !== null };
    });
}
