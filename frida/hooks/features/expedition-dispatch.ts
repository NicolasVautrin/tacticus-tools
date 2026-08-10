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
    class_get_fields, field_get_name, field_get_offset, class_get_parent,
    s as cstr, readIl2cppString, MethodRef,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString, createObject, il2cpp_object_new } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
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
// L'ETAGE N'EST PAS ISOLE, et c'est exactement ce qu'il faut faire avant de rouvrir : deux
// gestes NOUVEAUX sont apparus en meme temps dans #4/#5 -- l'ALLOCATION du delegate
// (`il2cpp_object_new`) et l'APPEL avec un 4e argument non nul. #3 faisait le second sans
// le premier et ne gelait pas. `expeditionCallbackForge` separe les deux : il fabrique le
// delegate et N'ENVOIE RIEN. S'il gele, la cause est l'allocation ; s'il rend la main, elle
// est dans l'appel. Tant que cette question n'a pas de reponse MESUREE, on n'envoie plus.
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

/** Offset d'un champ, resolu PAR SON NOM, EN REMONTANT LES CLASSES DE BASE.
 *
 *  ⚠ La remontee n'est pas un raffinement, c'est la condition pour que ca marche sur un
 *  delegate : `class_get_fields` n'enumere que les champs DECLARES par la classe, et
 *  `Action<System.Boolean>` n'en declare AUCUN -- `method_ptr`, `invoke_impl`, `m_target`,
 *  `method`, `method_code` vivent tous sur `System.Delegate`. Sans remontee, la recherche
 *  rend un ensemble VIDE qui se lit comme << classe inconnue >> alors que la classe est
 *  bonne. Mesure du 2026-08-10 : `{"INCOMPLET": {}}`, 0 champ sur 5.
 *
 *  Rend -1 si le nom n'existe nulle part -- on refuse alors de lire, plutot que de
 *  dereferencer un offset suppose. */
function offsetChamp(klass: NativePointer, nom: string): number {
    let k: NativePointer = klass;
    let profondeur = 0;
    while (!k.isNull() && profondeur < 8) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(k, it) as NativePointer).isNull()) {
            if (cstr(field_get_name(f) as NativePointer) === nom) {
                return field_get_offset(f) as number;
            }
        }
        try { k = class_get_parent(k) as NativePointer; } catch { break; }
        profondeur++;
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

/** Pas de `NativeCallback` ici : du code natif PUR, un `ret`.
 *
 *  ⚠ ET LA RAISON N'EST PAS CELLE QUE J'AI ECRITE D'ABORD. Le premier jet mettait un
 *  `NativeCallback` JS dans `invoke_impl` ; le jeu a gele, et j'ai conclu << Frida doit
 *  entrer dans QuickJS depuis le thread de reponse reseau, runtime mono-thread deja occupe,
 *  DEADLOCK >>. Le stub natif ci-dessous a ete ecrit contre CETTE explication -- et le gel
 *  s'est reproduit a l'identique, avec ZERO JavaScript dans le chemin. L'explication est
 *  donc REFUTEE : elle n'a pas survecu a la suppression de sa cause supposee.
 *
 *  Ce qui reste vrai et mesure : le gel ne se SIGNALE PAS. Process vivant, session Frida
 *  `running`, `/api/admin/status` serein -- et plus aucun RPC ne repond, parce que le main
 *  thread garde le verrou QuickJS pendant qu'il attend. Ne jamais lire le status comme une
 *  preuve de sante ; le seul temoin est un RPC qui revient.
 *
 *  Le `ret` reste le bon choix (signature `void`, ABI x64 Windows : nettoyage a l'appelant),
 *  simplement il n'est pas le remede qu'on croyait -- il n'y a pas encore de remede.
 *
 *  ⚠ REFERENCE FORTE OBLIGATOIRE : la page allouee est liberee avec l'objet JS qui la
 *  detient. La perdre laisserait un pointeur pendant dans un delegate encore vivant.
 */
let pageRet: NativePointer | null = null;

/** Un `ret` natif, alloue une fois. Zero JS dans le chemin d'appel. */
function stubRet(): NativePointer | null {
    if (pageRet) return pageRet;
    try {
        const p = Memory.alloc(Process.pageSize);
        Memory.patchCode(p, 1, (code) => { code.writeU8(0xc3); });   // ret
        Memory.protect(p, Process.pageSize, "r-x");
        pageRet = p;
        return p;
    } catch { return null; }
}
let dispoDelegate: { klass: NativePointer; offsets: Record<string, number> } | null = null;

/** Fabrique un `Action<System.Boolean>` inerte.
 *
 *  Rend `{ptr}` ou `{err}` -- JAMAIS un `null` muet. Un `catch { return null; }` a deja
 *  fait lire << impossible de fabriquer >> alors que les cinq offsets etaient resolus et
 *  affiches juste a cote : le refus etait juste, son motif introuvable. */
function fabriquerCallback(): { ptr?: NativePointer; err?: string } {
    if (!dispoDelegate) return { err: "classe du callback NON RESOLUE" };
    const { klass, offsets } = dispoDelegate;
    const manquants = ["invoke_impl", "method_ptr", "method_code", "method", "m_target"]
        .filter((n) => offsets[n] === undefined);
    if (manquants.length) {
        return { err: "champs manquants : " + manquants.join(", ") };
    }
    const ret = stubRet();
    if (!ret) return { err: "stub `ret` natif NON ALLOUE" };
    // ⚠ `il2cpp_object_new` NU, PAS `createObject`. Ce dernier enchaine sur
    // `findMethod(klass, ".ctor")` et l'invoque avec `args = null` -- or le ctor d'un
    // delegate en prend DEUX (`object target, IntPtr method`). `runtime_invoke` lit alors
    // `params[0]` a 0x0 et `params[1]` a 0x8, d'ou le tres litteral
    // << access violation accessing 0x8 >> mesure le 2026-08-10.
    //
    // Un delegate ne se construit PAS par son ctor ici : on alloue, et on ecrit nous-memes
    // les champs (c'est tout ce que le ctor managé ferait, sans le detour par un
    // `MethodInfo*` qu'on n'a pas).
    let d: NativePointer;
    try {
        d = il2cpp_object_new(klass) as NativePointer;
    } catch (e) {
        return { err: "il2cpp_object_new : "
                    + String((e as Error).message || e).slice(0, 140) };
    }
    if (d.isNull()) return { err: "il2cpp_object_new a rendu NULL" };
    // ⚠ ENRACINER, ET LE FAIRE TOUT DE SUITE. `il2cpp_object_new` rend un objet que RIEN de
    // managé ne reference : notre seule prise est un `NativePointer` dans le tas de Frida,
    // que le GC IL2CPP ne scanne pas. Entre cette ligne et le moment ou le natif range le
    // delegate dans son display class, une collecte peut donc le liberer -- et le natif
    // invoquerait alors `invoke_impl` sur de la memoire recyclee, a la RECEPTION de la
    // reponse, loin d'ici. `gcRoot.add` pose un `il2cpp_gchandle_new(obj, pinned)`, la
    // seule prise que le GC honore.
    //
    // On ne le relache PAS : le delegate doit survivre jusqu'a l'appel du callback, dont
    // l'instant ne nous est pas connu (il vient de la reponse serveur). Un handle par
    // envoi, quelques octets -- `gcRoot.count()` les rend visibles.
    gcRoot.add(d);
    try {
        d.add(offsets["invoke_impl"]).writePointer(ret);
        d.add(offsets["method_ptr"]).writePointer(ret);
        d.add(offsets["method_code"]).writePointer(ptr(0));
        d.add(offsets["method"]).writePointer(ptr(0));
        d.add(offsets["m_target"]).writePointer(ptr(0));
    } catch (e) {
        return { err: "ecriture des champs : "
                    + String((e as Error).message || e).slice(0, 140) };
    }
    return { ptr: d };
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
        // La classe du CALLBACK vient elle aussi de la signature native (parametre 3),
        // et ses offsets de champ sont resolus PAR NOM -- meme discipline que la liste.
        const kCb = methodParamClass(miDispatch.info, 3);
        if (kCb) {
            const offs: Record<string, number> = {};
            for (const nom of ["invoke_impl", "method_ptr", "method_code", "method",
                               "m_target"]) {
                const o = offsetChamp(kCb, nom);
                if (o >= 0) offs[nom] = o;
            }
            dispoDelegate = { klass: kCb, offsets: offs };
            layout["Action<Boolean>"] = Object.keys(offs).length === 5
                ? offs : { INCOMPLET: offs };
        } else {
            layout["Action<Boolean>"] = "CLASSE NON RESOLUE (parametre 3)";
        }

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
     *  Il n'immobilise aucune unite et ne touche pas au compte. body: {} */
    ctx.rpc.expeditionCallbackForge = (): Promise<unknown> =>
        queueOnMainThread(() => {
            const avant = gcRoot.count();
            const t0 = Date.now();
            const r = fabriquerCallback();
            const ms = Date.now() - t0;
            if (!r.ptr) {
                return { ok: false, err: r.err, ms,
                         layout: layout["Action<Boolean>"] };
            }
            // Relire ce qu'on vient d'ecrire : si les champs ne se relisent pas, l'objet
            // n'est pas ce qu'on croit, et l'envoi partirait sur une base fausse.
            const { offsets } = dispoDelegate as { offsets: Record<string, number> };
            const relu: Record<string, string | null> = {};
            for (const n of ["invoke_impl", "method_ptr", "method_code", "method",
                             "m_target"]) {
                try { relu[n] = r.ptr.add(offsets[n]).readPointer().toString(); }
                catch { relu[n] = null; }
            }
            return {
                ok: true, ms, delegate: r.ptr.toString(),
                classe: (() => {
                    try { return r.ptr.readPointer().toString(); } catch { return null; }
                })(),
                classeAttendue: dispoDelegate
                    ? dispoDelegate.klass.toString() : null,
                stubRet: pageRet ? pageRet.toString() : null,
                relu,
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
