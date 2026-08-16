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
    findClassAnywhere, findMethodByParamCount, methodParamClass, IL2CPP_MODULE_NAME,
    class_get_fields, field_get_name, field_get_offset, getFieldOffset,
    s as cstr, readIl2cppString, MethodRef,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString, createObject } from "../il2cpp/invoke.js";
import { delegateInerte, ardoiseDelegate } from "../il2cpp/delegate.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";
// Le FOYER de la resolution du `ViewCommandExecutor`. Importe plutot que re-marche : ce
// module porte deja, plus bas, le rappel chiffre de ce qu'une resolution dupliquee a coute.
import { executeurVivant, Refus as RefusVue } from "./view-command.js";

/** `executeurVivant` rend un REFUS NOMME plutot qu'un `null` -- on le reconnait par sa forme. */
function estRefusVue(x: NativePointer | RefusVue): x is RefusVue {
    return typeof x === "object" && x !== null && (x as RefusVue).ok === false;
}

/** Borne de securite sur la taille d'un envoi. Le plateau du 2026-08-10 plafonne a 5
 *  participants ; la borne est large mais elle existe pour qu'un appelant fautif ne
 *  parte pas avec le roster entier. */
const MAX_UNITES = 12;

/** ⛔ L'envoi natif est FERME (cf. le bloc de refus dans `expeditionDispatch`). Ce n'est
 *  PAS un reglage a basculer parce qu'on est presse : le rouvrir demande d'avoir ISOLE
 *  pourquoi `runtime_invoke` sur cette chaine tue le process -- ce qu'aucune des trois
 *  tentatives n'a etabli. Une constante, pas un RPC : un interrupteur accessible serait
 *  actionne. */
// ROUVERT le 2026-08-10 sur l'identification du callback obligatoire -- puis REFERME LE
// MEME JOUR, parce que le delegate fabrique GELE LE JEU (2 tentatives sur 2).
//
// ⚠ ET LE GEL N'EST PAS CELUI QUE J'AVAIS DIAGNOSTIQUE. La premiere version mettait un
// `NativeCallback` JS dans `invoke_impl` ; j'en avais conclu << deadlock QuickJS depuis le
// thread reseau >> et remplace le callback par un stub natif `ret`, ZERO JavaScript. Le
// gel s'est reproduit A L'IDENTIQUE. Une explication qui survit a la suppression de sa
// cause supposee n'explique rien : elle est REFUTEE, pas affinee.
//
// CE QUE LA MESURE DIT (2026-08-10, PID fige lu par GetThreadContext, cf.
// `docs/rl/case-600-gel-du-dispatch-natif.md`) :
//
//   - 142 threads sur 142 ont leur RIP dans `ntdll.dll`. AUCUN dans `GameAssembly.dll`.
//     Personne ne boucle : tout le monde ATTEND. CPU du process plat (+0,05 s en 3 s).
//   - Le main thread porte exactement trois cadres `GameAssembly` :
//         FUN_1801f7b30+0x59   -- `il2cpp_runtime_invoke` (pose `exc = 0` puis appelle)
//         FUN_1801f8090+0x49   -- `Runtime::Invoke`, retour d'`invoker_method(...)`
//         FUN_1801eb760+0xd5   -- primitive de VERROU (compteur de recursion en TLS,
//                                 LOCK/UNLOCK, puis attente) <- le plus interne
//
//   Donc : notre `invokeMethod` entre dans le natif, et le natif se bloque sur un verrou
//   d'ou personne ne le relache. Un stop-the-world qui ne repart pas.
//
// ═══ ROUVERT, ET CETTE FOIS SUR UNE MESURE QUI DISCULPE LE CHEMIN ═══
//
// L'etage a ete isole, en deux temps, et le resultat retourne le diagnostic :
//
//   1. `expeditionCallbackForge` fabrique le delegate SANS envoyer. Six appels, 0 ms
//      chacun, jeu vivant -> l'ALLOCATION est innocente.
//   2. `probes/gc-rendezvous.ts` force une collecte depuis le thread RPC de Frida, SANS
//      envoi ni delegate ni `runtime_invoke` -> LE JEU GELE. 145 threads dans `ntdll`,
//      aucun dans `GameAssembly`, main thread parque a un safepoint.
//
// Le gel est donc un STOP-THE-WORLD DU GC sous instrumentation Frida. Il n'a RIEN a voir
// avec le callback, ni avec cette chaine d'envoi : il se declenche sur du code qui ne fait
// rien d'autre que collecter. Les tentatives #4 et #5 ont eu la malchance de tomber sur une
// collecte pendant l'envoi.
//
// ⚠ CE QUI RESTE, ET QUI N'EST PAS SUPPRIMABLE : la malchance. Une collecte peut survenir
// pendant n'importe quel appel natif qui alloue. Ce qu'on a fait pour la rendre moins
// probable, c'est baisser NOTRE part d'allocations -- le delegate est desormais alloue UNE
// FOIS et partage (`callbackPartage`), la ou #4/#5 en creaient un par envoi. Le reste (la
// `List<String>`, trois chaines) est ce que faisait deja #3, qui n'a pas gele.
//
// ⚠ ET SI CA REGELE : c'est un TROISIEME TIRAGE SUR LE MEME DE, pas une nouvelle enigme.
// Ne pas repartir en quete d'une cause -- lire `tasAvant`/`tasApres` ci-dessous, et surtout
// VERIFIER `expeditionBoardRead` avant de retenter : un envoi part meme si le jeu gele.
const AUTORISER_ENVOI_NATIF = true;

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
    /** D'OU L'ON VIENT. RVA (adresse - base du module), pas VA : une VA est fausse au
     *  prochain build, une RVA se resout contre `data/symbols/<build>/`. Cote appelant :
     *  `python scripts/python/ghidra_symbols.py whereis <VA>`. */
    pile?: string[];
    /** Le thread appelant. Une chaine UI et un `runtime_invoke` peuvent ne pas etre sur le
     *  meme, et c'est un candidat serieux pour la mort du process. */
    thread?: number;
    /** Le `callback` etait-il nul ? Un appel LEGITIME ne l'est jamais -- et c'est
     *  precisement ce qui manquait aux notres. */
    callbackNul?: boolean;
    /** `Il2CppClass*` du delegate observe, pour savoir quoi fabriquer. */
    callbackClasse?: string;
}

/** Le dernier `Action<Boolean>` vu passer sur un appel LEGITIME. Temoin, pas piece de
 *  rechange : il porte la closure d'un ecran precis (son invocation fait `Screen.Hide()`).
 *  Sert a valider le delegate qu'on fabriquera, pas a le remplacer. */
let dernierCallback: NativePointer | null = null;

/** Les N premieres frames, en RVA. `null` si la pile n'est pas lisible. */
function pileRva(ctx: CpuContext | null): string[] | null {
    try {
        const base = Process.getModuleByName(IL2CPP_MODULE_NAME).base;
        return Thread.backtrace(ctx ?? undefined, Backtracer.ACCURATE)
            .slice(0, 24)
            .map((a) => {
                try {
                    const d = a.sub(base);
                    // Hors module : on le DIT plutot que de rendre un offset absurde.
                    return (d.compare(0) >= 0 && d.compare(0x8000000) < 0)
                        ? "+0x" + d.toString(16)
                        : "hors-module:" + a.toString();
                } catch { return a.toString(); }
            });
    } catch { return null; }
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

// ⚠ `offsetChamp` VIVAIT ICI, ET C'ETAIT UNE REIMPLEMENTATION DE `getFieldOffset`.
//
// Ce module avait sa propre resolution de champ par nom. Ecrite d'abord SANS remonter les
// classes de base, elle rendait `{"INCOMPLET": {}}` -- 0 champ sur 5 -- sur
// `Action<System.Boolean>`, qui n'en DECLARE aucun : `invoke_impl`, `method_ptr`,
// `m_target`, `method`, `method_code` vivent tous sur `System.Delegate`. Un ensemble vide
// se lit comme << classe inconnue >> alors que la classe etait bonne, et ca a coute un
// aller-retour entier.
//
// Or `il2cpp/helpers.ts` expose `getFieldOffset` DEPUIS TOUJOURS, et elle remonte deja la
// chaine d'heritage -- en plus d'etre MEMOISEE, ce que la version locale n'etait pas. Le
// bug << decouvert >> ici etait deja corrige dans la lib partagee ; seule la duplication
// l'avait rouvert.
//
// Mesure du gisement (2026-08-10) : **53 fichiers** de `frida/hooks/**` cherchent un champ
// par son nom (`field_get_name`), **17** seulement remontent les parents
// (`class_get_parent`). L'ecart n'est pas toujours un bug -- un probe de dump veut souvent
// n'enumerer QUE les champs declares -- mais chaque resolution par nom ecrite a la main
// rouvre le meme angle mort. Passer par `getFieldOffset` le ferme d'office.
//
// `getFieldOffset` rend **-1** sur un nom absent. ⚠ `-1` est *truthy* en JS : ne jamais
// ecrire `getFieldOffset(k, "X") || <repli>` -- utiliser `fieldOffsetOr`, qui existe pour
// ca et dont le piege est documente dans `helpers.ts`.

/** `ExpeditionProgression` pris SANS ecran, par le `ViewCommandExecutor`.
 *
 *  LA TROISIEME VOIE, ET C'EST ELLE QUI SUPPRIME L'INTERFACE. Les deux autres attendent un
 *  EVENEMENT (un envoi, ou l'affichage de l'ecran d'Operations) ; celle-ci LIT un champ, donc
 *  elle marche depuis n'importe quel ecran -- y compris en pleine bataille. Mesure du
 *  2026-08-15, build `t6dpr4k06g` : `ViewCommandExecutor._expeditionProgression` porte un
 *  pointeur vivant de classe REELLE `ExpeditionProgression`, lu par `viewField` alors que le
 *  jeu etait sur l'ecran des Guildes puis en bataille.
 *
 *  ⚠ RESOLU PAR NOM a chaque appel, jamais par l'offset mesure (+1160) : c'est la meme regle
 *  que pour `_viewCommandExecutor` lui-meme, dont l'offset a deja bouge d'un build a l'autre.
 *  ⚠ L'executeur vient de `view-command.ts`, PAS d'une seconde marche de la chaine
 *  `IdunNavigation._viewCommandExecutor` : ce module-la porte le rappel de ce qu'une
 *  resolution de champ dupliquee a coute ici meme (cf. le pave sur `offsetChamp`).
 *  ⚠ Lecture PURE -- aucun `invoke`, aucune commande de vue jouee, donc aucun effet sur ce
 *  que le joueur a a l'ecran. */
function progressionParExecuteur(): NativePointer | null {
    try {
        const exec = executeurVivant();
        if (estRefusVue(exec)) return null;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return null;
        const off = getFieldOffset(kExec, "_expeditionProgression");
        if (off < 0) return null;                 // ⚠ -1 est *truthy* : tester `< 0`, jamais `||`
        const p = (exec as NativePointer).add(off).readPointer();
        return p.isNull() ? null : p;
    } catch { return null; }
}

/** L'`ExpeditionGameEvents` vivant.
 *
 *  TROIS VOIES, et les deux dernieres existent parce que la premiere est CIRCULAIRE :
 *  l'instance ne se capte au vol qu'a un envoi, or il faut l'instance POUR envoyer.
 *  `ExpeditionProgression` la porte en champ (`<GameEvents>k__BackingField`) ; ce porteur-la
 *  se capte soit a l'affichage d'un ecran d'Operations (interception, voie historique), soit
 *  DIRECTEMENT sur le `ViewCommandExecutor`, sans aucun ecran.
 *
 *  Le champ est lu par un offset RESOLU PAR NOM a l'armement. Ses accesseurs
 *  (`get_GameEvents`) n'existent pas dans la table : corps trivial, donc DEDUPLIQUE par
 *  IL2CPP -- l'absence n'y prouve rien, et il n'y a rien a invoquer. */
function evenements(): NativePointer | null {
    if (instanceEvents) return instanceEvents;
    if (offGameEvents < 0) return null;
    // L'interception d'abord (elle a pu retenir le porteur), l'executeur ensuite : ce dernier
    // n'exige aucun ecran, donc il RATTRAPE le cas ou rien n'a encore tire.
    for (const porteur of [instanceProgression, progressionParExecuteur()]) {
        if (!porteur) continue;
        try {
            const p = porteur.add(offGameEvents).readPointer();
            if (!p.isNull()) return p;
        } catch { /* porteur suivant */ }
    }
    return null;
}

// ---------------------------------------------------------------------------------------
// LE CALLBACK FABRIQUE -- la piece sans laquelle la reponse serveur tue le process.
//
// `<Execute>b__0` invoque le delegate ainsi (decompile, offsets confirmes par
// `classFields('System','Delegate')`) :
//
//     (*(code**)(d + 0x18))( *(d + 0x40), <valeur>, *(d + 0x28) )
//          invoke_impl          method_code               method
//
// On fabrique donc un delegate MINIMAL : `invoke_impl` pointe sur une page NATIVE contenant
// un seul `ret`, et les autres champs sont nuls. Un callback qui ignore ses arguments ne
// peut pas les mal interpreter -- c'est ce qui rend cette construction sure malgre
// l'incertitude sur la convention exacte de passage du `bool`.
//
// ET CE QUE LE DECOMPILE DIT DE SON ROLE JUSTIFIE LE `ret`. Le callback que construit le
// presenter (`ExpeditionDispatchScreenPresenter$$<OnDispatch>b__0`) fait, en entier :
//
//     if (succes != 0) return;                       // SUCCES -> RIEN
//     msg = String.Concat(<prefixe>, expeditionId, <suffixe>);
//     <affiche l'erreur a l'ecran>                   // ECHEC -> un message, c'est tout
//
// C'est un RAPPORTEUR D'ERREUR d'UI, pas un maillon fonctionnel. La mutation, elle, precede
// l'appel : dans `DispatchExpeditionCommand$$<Execute>b__0`, la reponse est appliquee au
// modele local PUIS le callback est notifie. C'est pourquoi la tentative #3 (callback nul)
// avait ete ENREGISTREE avant de lever. Un `ret` reproduit donc fidelement la branche
// succes ; il ne sacrifie que le message d'erreur, qu'on remplace par `expeditionBoardRead`.
//
// POURQUOI PAS UNE METHODE DU JEU. Le dump n'offre aucune `static void(bool)` inoffensive :
// toutes activent ou desactivent quelque chose (`SetEnabled`, `set_runInBackground`,
// `Consent`...). Emprunter l'une d'elles echangerait un crash contre un effet de bord
// silencieux.
//
// POURQUOI PAS LE DELEGATE TEMOIN. Celui du presenter porte la closure d'un ecran precis ;
// son invocation fait `Screen.Hide()`. Il sert de reference, pas de piece de rechange.
// ---------------------------------------------------------------------------------------

// ⚠ LA FABRIQUE DE DELEGATE VIVAIT ICI. Elle est partie dans `il2cpp/delegate.ts`.
//
// Elle n'avait rien d'Expedition : « fabriquer un `Action<T>` inerte pour un natif qui exige
// un callback » est un besoin de TOUTE la couche IL2CPP, et les quatre pieges qu'elle porte
// (ctor a ne pas invoquer, enracinement GC, zero JS dans le corps, une seule instance
// partagee) ont chacun coute un aller-retour ici. Les laisser dans un module metier, c'etait
// garantir qu'on les repaye ailleurs -- exactement ce qui venait d'arriver avec
// `offsetChamp`, reimplementation d'un `getFieldOffset` deja correct.
//
// Ce qui RESTE ici, parce que c'est propre a cette porte : QUELLE classe de delegate
// (`methodParamClass(miDispatch, 3)`), et le fait qu'on refuse d'envoyer sans.
//
// POURQUOI PAS UNE METHODE DU JEU comme callback. Le dump n'offre aucune `static void(bool)`
// inoffensive : toutes activent ou desactivent quelque chose (`SetEnabled`,
// `set_runInBackground`, `Consent`...). Emprunter l'une d'elles echangerait un crash contre
// un effet de bord silencieux.
//
// POURQUOI PAS LE DELEGATE TEMOIN. Celui du presenter porte la closure d'un ecran precis ;
// son invocation fait `Screen.Hide()`. Il sert de reference, pas de piece de rechange.
// ---------------------------------------------------------------------------------------

/** La classe du callback, prise dans la SIGNATURE NATIVE (parametre 3) a l'armement. */
let klassCallback: NativePointer | null = null;

/** Fabrique (ou reutilise) le callback inerte. Mince enveloppe sur `il2cpp/delegate.ts` :
 *  tout le savoir-faire est la-bas, seule la CLASSE est locale. */
function fabriquerCallback(neuf?: boolean): { ptr?: NativePointer; err?: string;
                                              reutilise?: boolean } {
    const r = delegateInerte(klassCallback, { neuf });
    if (!r.d) return { err: r.err };
    return { ptr: r.d.ptr, reutilise: r.d.reutilise };
}

/** Ce que le stub natif a depose, lu DEPUIS LE PUMP. `null` = aucun delegate fabrique, donc
 *  RIEN N'A ETE MESURE -- a ne pas lire comme << le callback n'a pas ete appele >>, qui se
 *  dit `appels: 0`. */
function lireArdoise(): ReturnType<typeof ardoiseDelegate> {
    return ardoiseDelegate(klassCallback);
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
               liste: NativePointer, bonus: NativePointer | number): Envoi | null {
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
    return e;
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
        // La classe du CALLBACK vient elle aussi de la signature native (parametre 3). C'est
        // la SEULE chose propre a cette porte : la fabrique, elle, vit dans
        // `il2cpp/delegate.ts` et resout ses offsets elle-meme.
        klassCallback = methodParamClass(miDispatch.info, 3);
        layout["Action<Boolean>"] = klassCallback
            ? klassCallback.toString()
            : "CLASSE NON RESOLUE (parametre 3)";

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
        offGameEvents = kProg
            ? getFieldOffset(kProg, "<GameEvents>k__BackingField")   // -1 si absent
            : -1;
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
            // LE CORPS REEL, celui qui parle au reseau. `DispatchExpedition` ne fait que
            // relayer ; c'est ICI que la closure de reponse est construite et que l'appel
            // web part. Sa PILE dit d'ou vient la chaine -- c'est la mesure qui manque pour
            // comprendre pourquoi notre `runtime_invoke` aboutit ET tue le process.
            ["DispatchExpeditionCommand.Execute",
             findClassAnywhere(
                 "Idun.Source.IdunMeta.Logic.Features.Expedition.Progression.Commands"
                 + ".DispatchExpedition", "DispatchExpeditionCommand"), "Execute", 4],
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
                            const e = noter(cle, "observe", args[1], args[2], args[3]);
                            if (e) {
                                e.pile = pileRva(this.context) ?? undefined;
                                e.thread = this.threadId;
                                // LE CALLBACK. C'est la piece qui manquait a nos envois :
                                // `b__0` LEVE quand il est nul (cf. le bloc de refus). On
                                // retient celui d'un appel legitime -- il sert de temoin
                                // pour valider le delegate qu'on fabriquera.
                                if (estPorteur) {
                                    try {
                                        const cb = args[4];
                                        e.callbackNul = cb.isNull();
                                        if (!cb.isNull()) {
                                            dernierCallback = cb;
                                            e.callbackClasse = cb.readPointer().toString();
                                        }
                                    } catch { /* avale */ }
                                }
                            }
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
                          callbackTemoin: dernierCallback
                              ? dernierCallback.toString() : null,
                          // C'est ICI qu'on ramasse ce que le stub natif a depose. Le
                          // journal tourne sur le pump : la lecture se fait donc sur le
                          // main thread, jamais sur le thread de la reponse.
                          ardoise: lireArdoise(),
                          dispoListe: dispoListe
                              ? { _items: dispoListe.offItems, _size: dispoListe.offSize }
                              : null,
                          envois: journal.slice() };
            if (body?.reset) journal.length = 0;
            return out;
        });

    /** L'ISOLATEUR D'ETAGE. Fabrique le delegate et N'ENVOIE RIEN.
     *
     *  ⚠ IL EXISTE PARCE QUE DEUX GESTES NOUVEAUX SONT ARRIVES ENSEMBLE. Les tentatives
     *  #4 et #5 ont ajoute, dans le meme appel, une ALLOCATION managee
     *  (`il2cpp_object_new` d'un `Action<System.Boolean>`) et un APPEL natif avec un 4e
     *  argument non nul. Les deux ont gele le jeu ; la #3 faisait le second SANS le
     *  premier et n'a pas gele. Deux causes candidates, une seule mesure : c'est
     *  exactement la situation ou l'on n'a le droit de conclure ni l'une ni l'autre.
     *
     *  Ce RPC coupe le paquet en deux. S'il GELE, la cause est l'allocation (init de
     *  classe, GC, ou l'un des deux sous Frida). S'il REND LA MAIN, l'allocation est
     *  innocente et le blocage est dans l'appel natif -- et l'on saura alors que le
     *  verrou vu sous `il2cpp_runtime_invoke` appartient a `DispatchExpedition`.
     *
     *  Il n'immobilise aucune unite et ne touche pas au compte.
     *
     *  body: { neuf?: true } -- `neuf` FORCE une allocation fraiche au lieu de rendre le
     *  delegate partage. C'est ce qui permet de mesurer l'allocation elle-meme ; en
     *  contrepartie chaque appel laisse un objet EPINGLE de plus. A n'utiliser que pour
     *  mesurer, et a lire dans `gcHandles`. */
    ctx.rpc.expeditionCallbackForge = (body?: { neuf?: boolean }): Promise<unknown> =>
        queueOnMainThread(() => {
            const avant = gcRoot.count();
            const t0 = Date.now();
            const r = delegateInerte(klassCallback, { neuf: body?.neuf });
            const ms = Date.now() - t0;
            if (!r.d) {
                return { ok: false, err: r.err, ms,
                         layout: layout["Action<Boolean>"] };
            }
            // Relire ce qu'on vient d'ecrire : si les champs ne se relisent pas, l'objet
            // n'est pas ce qu'on croit, et l'envoi partirait sur une base fausse.
            const relu: Record<string, string | null> = {};
            for (const [n, off] of Object.entries(r.d.offsets)) {
                try { relu[n] = r.d.ptr.add(off).readPointer().toString(); }
                catch { relu[n] = null; }
            }
            return {
                ok: true, ms, delegate: r.d.ptr.toString(), reutilise: r.d.reutilise,
                classe: (() => {
                    try { return r.d.ptr.readPointer().toString(); } catch { return null; }
                })(),
                classeAttendue: klassCallback ? klassCallback.toString() : null,
                offsets: r.d.offsets,
                relu,
                ardoise: lireArdoise(),
                gcHandles: { avant, apres: gcRoot.count() },
                note: "AUCUN envoi. Si ce RPC revient, l'allocation du delegate est hors "
                    + "de cause dans le gel -- le blocage est dans l'appel natif.",
            };
        });

    /** ⚠ ENVOIE. Immobilise les unites pour la duree de l'operation.
     *
     *  body: { expeditionId, unitIds: string[], bonusFulfilled?: boolean,
     *          confirmer: true } */
    ctx.rpc.expeditionDispatch = (body?: {
        expeditionId?: string; unitIds?: string[]; bonusFulfilled?: boolean;
        participants?: number; confirmer?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        // ⛔ VOIE FERMEE -- CAUSE IDENTIFIEE : LE `callback` N'EST PAS OPTIONNEL.
        //
        // TROUVE PAR LA PILE D'UN DISPATCH MANUEL (2026-08-10). La chaine legitime est :
        //
        //   EventSystem$$Update -> InputSystemUIInputModule$$ProcessPointerButton
        //     -> ExecuteEvents$$Execute -> OptimisedButton$$OnPointerClick
        //       -> UnityEvent$$Invoke -> ExpeditionDispatchScreen$$HandleOnDispatchTapped
        //         -> ExpeditionDispatchScreenPresenter$$...ICallbacks.OnDispatch
        //           -> ExpeditionGameEvents$$DispatchExpedition
        //             -> DispatchExpeditionCommand$$Execute
        //
        // Le chainon que nous court-circuitons est le PRESENTER, et c'est lui qui
        // CONSTRUIT LE CALLBACK (un delegate bati sur sa closure) avant d'appeler
        // `DispatchExpedition`. Nous passions `null`.
        //
        // ⚠ J'AVAIS ECRIT L'INVERSE, ET C'ETAIT FAUX. Le commentaire precedent affirmait
        // << le callback nul est TOLERE : `<Execute>b__0` teste `!= 0` dans les deux
        // branches >>. Relecture complete de `b__0` :
        //
        //     if (succes) { ... if (callback != 0) { ...; goto INVOKE; } }
        //     else        {      if (callback != 0) { ...; goto INVOKE; } }
        //     FUN_1801f51f0();     <-- raise_null_reference_exception + swi(3) / INT 3
        //
        // Ce `if (callback != 0)` n'est PAS une tolerance : c'est le null-check que le
        // compilateur IL2CPP insere AVANT l'appel du delegate, et sa branche << faux >>
        // LEVE. J'ai vu le test et lu << optionnel >>.
        //
        // CA EXPLIQUE TOUT CE QU'ON A MESURE :
        //   - l'envoi PART et le serveur l'enregistre (le reseau est atteint) ;
        //   - le process meurt APRES, a la RECEPTION de la reponse, quand `b__0` court ;
        //   - #2 n'a pas tue le jeu parce qu'il a echoue AVANT le reseau (mauvaise classe,
        //     exception native rattrapee par Frida) -- donc `b__0` n'a jamais tourne.
        //
        // POUR ROUVRIR il faut FOURNIR un `Action<System.Boolean>` non nul. Deux voies :
        //   (a) capturer `args[4]` d'un dispatch MANUEL et le reutiliser -- simple, mais le
        //       delegate porte la closure d'un ECRAN precis (il fait `Screen.Hide()`) ;
        //   (b) fabriquer le delegate (NativeCallback + champs `method_ptr`/`invoke_impl`/
        //       `m_target`) -- propre, et sans effet de bord sur l'UI.
        // (b) est la bonne, (a) sert a la valider.
        //
        // ANCIENNE ANALYSE (conservee pour ce qu'elle a coute) : l'envoi part, le process
        // meurt apres.
        //
        // BILAN MESURE du 2026-08-10, verifie CONTRE L'ETAT DU COMPTE apres relance :
        //
        //   #1  2 unites / 3 places, classe correcte     -> PROCESS MORT, rien enregistre
        //   #2  4 / 4, classe FAUSSE (bug du stash)      -> exception capturee, rien envoye
        //   #3  4 / 4, classe VERIFIEE, participants
        //       verifie, callback innocente              -> ENREGISTRE PAR LE SERVEUR,
        //                                                   PUIS process mort
        //
        // ⚠ #3 A REUSSI. Le plateau porte l'operation en `status: 1` avec exactement les
        // quatre unites envoyees. L'appel natif FONCTIONNE : ce qui tue le process est en
        // AVAL de l'envoi -- traitement de la reponse, closure, ou rafraichissement d'un
        // ecran qu'on n'a pas ouvert. Ce n'est donc PAS un probleme d'arguments ni de
        // cible, et toutes les gardes du monde a l'entree n'y changeront rien.
        //
        // CE QUE J'AVAIS CONCLU, ET QUI ETAIT FAUX -- DEUX FOIS. D'abord << deux causes
        // distinctes >> (equipe incomplete / mauvaise classe), refute par #3 qui avait les
        // deux gardes vertes. Puis << 3 echecs, 0 succes, la voie ne marche pas >>, refute
        // par l'etat du compte : #3 etait un SUCCES cote serveur. Les deux fois, j'ai
        // conclu depuis les seuls symptomes que j'avais sous les yeux, sans aller LIRE
        // l'etat reel -- alors qu'il suffisait d'un `expeditionBoardRead` apres relance.
        //
        // ETABLI : arguments bons (journal d'un envoi manuel), callback nul tolere
        // (`<Execute>b__0` teste `!= 0` dans les deux branches), classe correcte
        // (`classeOk: True`), et l'envoi ABOUTIT.
        // NON ETABLI : ce qui tue le process ensuite.
        //
        // POUR ROUVRIR : ancrer ce qui suit l'envoi (`DispatchExpeditionLocally`, le
        // callback de reponse, les commandes de vue) et voir laquelle ne revient pas. Une
        // piste concrete : l'UI n'etant pas sur l'ecran de dispatch, un rafraichissement
        // post-reponse peut viser un widget detruit.
        //
        // ⚠ CONSEQUENCE PRATIQUE : un envoi PART meme si le jeu meurt. Ne PAS retenter en
        // croyant que << ca n'a pas marche >> -- on dispatcherait deux fois.
        if (!AUTORISER_ENVOI_NATIF) {
            return {
                ok: false, refus: "voie fermee",
                err: "expeditionDispatch est FERME : avec un callback NUL l'envoi aboutit "
                   + "mais le process meurt a la reception ; avec un callback FABRIQUE le "
                   + "jeu GELE (2/2), main thread bloque sur un verrou sous "
                   + "`il2cpp_runtime_invoke`, 142 threads sur 142 parques dans ntdll. "
                   + "L'etage n'est pas isole : joue d'abord `expeditionCallbackForge`, "
                   + "qui fabrique le delegate SANS envoyer. ⚠ Un envoi part meme si le "
                   + "jeu meurt ou gele : lis `expeditionBoardRead` AVANT de retenter, "
                   + "sinon tu dispatches deux fois.",
                bilan: {
                    tentatives: 5, processMorts: 2, gels: 2,
                    enregistresParLeServeur: 1,
                    isolant: "expeditionCallbackForge",
                },
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
        // LE CALLBACK, ET IL EST OBLIGATOIRE. `null` faisait lever `<Execute>b__0` a la
        // RECEPTION de la reponse -- envoi enregistre, puis process mort. On refuse de
        // partir sans, plutot que de repeter l'incident.
        const rappel = fabriquerCallback();
        if (!rappel.ptr) {
            return { ok: false, refus: "callback",
                     err: "impossible de fabriquer l'`Action<System.Boolean>` -- ENVOI "
                        + "ANNULE. Sans lui, la reponse serveur leve une "
                        + "NullReferenceException et tue le process.",
                     cause: rappel.err,
                     layout: layout["Action<Boolean>"] };
        }
        // ═══ DETACHER NOS PROPRES SONDES AVANT D'APPELER. C'EST LA CAUSE DU GEL. ═══
        //
        // `expeditionDispatchArm` ancre `ExpeditionGameEvents$$DispatchExpedition` -- la
        // methode que ce RPC INVOQUE. Notre closure tourne deja en JS sur le main thread
        // (via `queueOnMainThread`, donc a l'interieur du handler du pump) ; l'appel natif
        // retombe aussitot dans notre propre trampoline, Frida veut y executer un handler
        // JS, et le runtime est deja tenu PAR CE MEME THREAD. Personne ne le rendra.
        //
        // MESURE (2026-08-10, 3 gels sur 3, pile du main thread lue par GetThreadContext,
        // du plus PROFOND au plus externe) :
        //
        //     [ 1- 2]  ntdll.dll                     <- l'attente
        //     [ 3-29]  frida-agent.dll               <- 27 cadres DANS Frida
        //     [30   ]  GameAssembly FUN_1801eb760+0xd5   <- le verrou du jeu
        //     [31-42]  frida-agent.dll
        //     [43   ]  GameAssembly FUN_1801f7b30+0x59   <- il2cpp_runtime_invoke, NOTRE appel
        //     [44-79]  UnityPlayer / USER32              <- la boucle de messages
        //
        // Le verrou du jeu APPELLE DANS frida-agent, et c'est la que tout s'arrete. Ce
        // n'est pas un GC : le gel du GC, lui, laisse le main thread parque a un safepoint
        // avec ZERO cadre `GameAssembly` (cf. `probes/gc-rendezvous.ts`). Deux gels de
        // formes differentes -- encore deux pannes que j'ai prises pour une.
        //
        // ⚠ ON NE REARME PAS TOUT SEUL APRES. La reponse serveur arrive plus tard, sur un
        // AUTRE thread : rearmer `DispatchExpeditionLocally` avant qu'elle arrive ferait
        // tourner un handler JS depuis ce thread-la. L'appelant rearme quand il a lu son
        // resultat -- explicitement.
        const detachees = listeners.length;
        for (const l of listeners) { try { l.detach(); } catch { /* deja parti */ } }
        listeners.length = 0;
        Interceptor.flush();

        // Telemetrie du tas, de part et d'autre de l'appel. Elle ne PREVIENT rien -- on ne
        // sait pas ou est le seuil de declenchement du GC -- mais si le jeu regele, la
        // derniere valeur connue de `tasAvant` est la seule chose qu'on aura pour dire si
        // on etait pres d'une collecte. Tri-etat : `null` = export absent, pas zero.
        const tasAvant = gcRoot.heapSize();
        const utiliseAvant = gcRoot.usedSize();
        log("[expedition-dispatch] envoi " + id + " (" + unites.length + " unites), tas="
            + utiliseAvant + "/" + tasAvant + " -- si le jeu gele, cette ligne est la"
            + " derniere sortie du process");
        try {
            invokeMethod(miDispatch.info, ev,
                         [createManagedString(id), liste, bonus, rappel.ptr]);
        } catch (ex) {
            e.err = String((ex as Error).message || ex).slice(0, 200);
        }
        if (journal.length >= 64) journal.shift();
        journal.push(e);
        return {
            ok: !e.err, envoi: e,
            callbackReutilise: !!rappel.reutilise,
            observationDetachee: detachees,
            tas: { utiliseAvant, tasAvant,
                   utiliseApres: gcRoot.usedSize(), tasApres: gcRoot.heapSize() },
            rearmer: "L'observation est DETACHEE (" + detachees + " porte(s)) : ce module "
                + "ancrait la methode qu'on invoque, et s'auto-bloquait dessus. Rearme par "
                + "`expeditionDispatchArm` APRES avoir lu le resultat -- pas avant, la "
                + "reponse serveur arrive sur un autre thread.",
            note: "Verifie par `expeditionDispatchJournal` qu'une entree `observe` de "
                + "`DispatchExpeditionLocally` a suivi : c'est elle qui atteste que la "
                + "chaine du jeu a bien traite l'envoi, pas notre propre appel.",
        };
    });

    /** RÉCLAMER les récompenses d'Operations terminées, sans aucun écran.
     *
     *  LA PORTE :
     *      ExpeditionGameEvents$$ClaimReward(expeditionId:System.String)
     *      ExpeditionGameEvents$$ClaimAllRewards(expeditionIds:List<System.String>)
     *
     *  ⚠ CE RPC ÉCRIT. Même famille que `expeditionDispatch`, même garde `confirmer: true`.
     *
     *  POURQUOI C'EST MOINS RISQUÉ QUE L'ENVOI, et ce n'est pas une impression :
     *  `ClaimReward` ne déclare AUCUN callback. Toute la pièce fragile de l'envoi — le
     *  delegate fabriqué, ses trois champs, la convention de passage du `bool` — n'existe
     *  pas ici. Notre part d'allocation se réduit à UNE chaîne managée (ou une `List` pour
     *  la forme groupée), donc la fenêtre où une collecte peut tomber est plus étroite.
     *
     *  ⚠ MAIS LE RISQUE RÉSIDUEL EST LE MÊME, ET IL N'EST PAS SUPPRIMABLE : un
     *  stop-the-world du GC sous instrumentation Frida peut figer n'importe quel appel
     *  natif qui alloue (mesuré, `probes/gc-rendezvous.ts` gèle SANS aucun envoi —
     *  `docs/rl/case-600-gel-du-dispatch-natif.md`). Si ça gèle : ce n'est pas une énigme,
     *  c'est un tirage de plus sur le même dé.
     *
     *  ⚠ ET UNE RÉCLAMATION PART MÊME SI LE JEU MEURT. Ne jamais retenter à l'aveugle :
     *  relire le plateau (`expeditionBoardRead`) et n'inclure QUE ce qui est encore
     *  réclamable. C'est la règle qui vaut déjà pour l'envoi (#600).
     *
     *  UN SEUL id -> `ClaimReward`. PLUSIEURS -> `ClaimAllRewards`. On ne boucle PAS sur la
     *  forme unitaire pour un lot : le jeu offre la forme groupée, et N appels natifs, c'est
     *  N fenêtres de collecte au lieu d'une. */
    ctx.rpc.expeditionClaim = (body?: {
        ids?: string[]; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const ids = Array.isArray(body?.ids) ? (body as { ids: string[] }).ids : [];
        if (ids.length === 0) {
            return { ok: false, error: "`ids` manquant ou vide -- ce RPC n'ÉNUMÈRE PAS. "
                + "Lire le plateau (`expeditionBoardRead`) et lui passer les identifiants "
                + "des Operations RÉELLEMENT terminées." };
        }
        if (ids.some((x) => typeof x !== "string" || !x)) {
            return { ok: false, error: "`ids` doit être une liste de chaînes non vides" };
        }
        if (ids.length > MAX_UNITES) {
            return { ok: false, error: `réclamation de ${ids.length} > ${MAX_UNITES} -- borne `
                + "de sécurité, comme pour l'envoi" };
        }
        if (body?.confirmer !== true) {
            return { ok: false, error: "REFUS : `confirmer: true` exigé. Ce RPC ÉCRIT sur le "
                + "compte -- il est à un caractère de `expeditionBoardRead`, qui ne fait que lire." };
        }
        return queueOnMainThread(() => {
            const ev = evenements();
            if (ev === null) {
                return { ok: false, error: "`ExpeditionGameEvents` introuvable : ni capté à "
                    + "l'écran, ni lisible sur `ViewCommandExecutor._expeditionProgression`. "
                    + "Jouer `expeditionDispatchArm` d'abord (il résout l'offset par NOM)." };
            }
            const kEvents = findClassAnywhere(
                "Idun.Source.IdunMeta.Logic.Features.Expedition.Progression",
                "ExpeditionGameEvents");
            if (!kEvents) {
                return { ok: false, error: "classe `ExpeditionGameEvents` absente de ce build" };
            }
            const unitaire = ids.length === 1;
            const mi = unitaire
                ? findMethodByParamCount(kEvents, "ClaimReward", 1)
                : findMethodByParamCount(kEvents, "ClaimAllRewards", 1);
            if (!mi) {
                return { ok: false, error: (unitaire ? "ClaimReward" : "ClaimAllRewards")
                    + " à 1 paramètre INTROUVABLE -- chemin PÉRIMÉ sur ce build, "
                    + "ne pas replier sur l'autre forme" };
            }

            // L'argument. Forme unitaire : une chaîne. Forme groupée : la `List<String>`
            // mesurée par `mesurerListe`, exactement comme l'envoi -- on ne refabrique pas
            // une disposition, on réutilise celle qui a déjà servi.
            let arg: NativePointer;
            if (unitaire) {
                arg = createManagedString(ids[0] as string);
            } else {
                const kListe = methodParamClass(mi.info, 0);
                const dispo = kListe ? mesurerListe(kListe) : null;
                // ⚠ `mesurerListe` rend `ctor`/`add` à `null` quand la méthode manque : on les
                // exige EXPLICITEMENT. Les supposer présents fabriquerait une liste vide qui
                // partirait quand même -- une réclamation de RIEN, avec un `ok: true`.
                if (!dispo || !dispo.ctor || !dispo.add) {
                    return { ok: false, error: "`List<String>` de `ClaimAllRewards` non "
                        + `mesurable (dispo=${dispo !== null} ctor=${!!dispo?.ctor} `
                        + `add=${!!dispo?.add}) -- réclamer un par un plutôt que de `
                        + "fabriquer une liste au jugé" };
                }
                arg = createObject(dispo.klass);
                invokeMethod(dispo.ctor.info, arg, null);
                for (const x of ids) invokeMethod(dispo.add.info, arg, [createManagedString(x)]);
            }
            gcRoot.add(arg);

            const tasAvant = gcRoot.heapSize();
            const utiliseAvant = gcRoot.usedSize();
            log("[expedition-dispatch] réclamation " + ids.join(",") + " via "
                + (unitaire ? "ClaimReward" : "ClaimAllRewards") + ", tas=" + utiliseAvant
                + "/" + tasAvant + " -- si le jeu gèle, cette ligne est la dernière sortie");
            const e: Envoi = {
                n: journal.length + 1, ts: Date.now(), origine: "emis",
                via: unitaire ? "ClaimReward" : "ClaimAllRewards",
                expeditionId: unitaire ? (ids[0] as string) : null,
                unitIds: unitaire ? null : ids.slice(),
                bonusFulfilled: null,
            };
            try {
                invokeMethod(mi.info, ev, [arg]);
            } catch (ex) {
                e.err = String((ex as Error).message || ex).slice(0, 200);
            }
            try { gcRoot.remove(arg); } catch { /* best effort */ }
            if (journal.length >= 64) journal.shift();
            journal.push(e);
            return {
                ok: !e.err, reclamation: e,
                tas: { utiliseAvant, tasAvant,
                       utiliseApres: gcRoot.usedSize(), tasApres: gcRoot.heapSize() },
                note: "L'appel est passé -- ça ne prouve PAS que la récompense est créditée. "
                    + "Confronter au plateau (`expeditionBoardRead`) : c'est lui qui atteste, "
                    + "pas ce retour. Et une réclamation part même si le jeu gèle ensuite.",
            };
        });
    };

    ctx.rpc.expeditionDispatchDisarm = (): Promise<unknown> => queueOnMainThread(() => {
        for (const l of listeners) { try { l.detach(); } catch { /* deja parti */ } }
        listeners.length = 0;
        return { ok: true, instanceConservee: evenements() !== null };
    });
}
