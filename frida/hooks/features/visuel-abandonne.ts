// visuel-abandonne — LE PAS VISUEL QUI NE SE REFERME JAMAIS, ET L'ETAGE QUI LE LACHE (#10038).
//
// CE QUI EST MESURE, pas suppose (session 41, build `t6dpr4k06g`, 2026-08-19) :
//
//   MessageExecutionQueue._currentlyProcessingMessage reste `true` pour toujours,
//   `_lastActivity` = "Ability_Active:Loki_NormalAttack", `_lastActivityStep` = "start",
//   6 messages coinces derriere. Le groupe bloque porte `<EntityId> 85` (eldarMauganRa),
//   `<Source> "Loki_NormalAttack"`, 3 messages, `_nextMessageIndex` 0 -- aucun execute.
//   Consequence : le runner continue d'appliquer les coups, l'ECRAN est fige. Quatre des cinq
//   vues du joueur restent sur leur case de deploiement.
//
// CE QUE LE DECOMPILE ETABLIT :
//
//   IdunBattle.View.BattleStream.GroupHandlers.Ability_Power_GroupHandler$$SetupAndExecuteAbility
//       this->_ability = ability
//       AbilityVisualsBase$$Init(ability, ...)        <- pose RootGroup (+0x100) et MainGroup
//       <fabrique le delegue onFinished>
//       AbilityVisualsBase$$Execute(ability, onFinished)
//
//   `Execute` ecrit `_onFinished` (+0x118) en TOUTE PREMIERE INSTRUCTION. Sur le visuel abandonne
//   `_onFinished` est NUL, alors que `RootGroup`/`MainGroup` sont poses ==> `Init` a rendu la main
//   par une EXCEPTION, et `Execute` n'a jamais tourne. Rien entre les deux ne peut echouer
//   autrement (une allocation mise a part), donc l'etage fautif est DANS `Init`.
//
//   Le dernier geste d'`Init` est `ParseTargetsFromQueue`, qui deref sans garde a une douzaine
//   d'endroits (`GroupMessage._messages` a +0x48, `AbilityVisualsUtils` a +0x90 puis son
//   `StreamMessages` a +0x88, chaque enumerateur...). C'est le suspect, PAS une certitude --
//   d'ou ce capteur.
//
// POURQUOI UN COMPTEUR ENTREE/SORTIE, ET PAS UN TRACEUR D'EXCEPTION
// ------------------------------------------------------------------
// `exception-tracer` ancre `il2cpp_raise_exception` et `_CxxThrowException` : sur cet incident il
// a rendu ZERO ligne, parce qu'un null-deref genere par IL2CPP passe par son helper interne
// (`FUN_1801f5460`), pas par l'API publique. Le signal qui, lui, ne peut pas mentir est
// structurel : quand une fonction part en exception, le deroulage de pile SAUTE son `onLeave`.
// Un `onEnter` sans `onLeave` EST donc un jet, quel que soit le chemin emprunte.
//
// LECTURE PURE : `onEnter`/`onLeave` seulement, aucune ecriture, aucun `retval.replace`.
// Ancre au register : ce sont des chemins FROIDS (un passage par cast d'ability), pas des
// getters d'UI -- le depot ne proscrit que les `replace` de chemin chaud.

import { findClassAnywhere, findMethod, getFieldOffset, il2cppBase } from "../il2cpp/helpers.js";
import { pinnedAddress } from "../il2cpp/build-pin.js";
import { champTexte } from "./lecture-champs.js";
import { Ctx } from "../controller.js";

interface Ancre {
    /** Nom cite au rapport, en SYMBOLE (jamais une adresse). */
    symbole: string;
    ns: string;
    cls: string;
    methode: string;
    /** Index de l'argument qui porte le visuel d'ability, ou `null` si c'est `this` (arg 0). */
    argVisuel: number;
    /** L'ancre la plus EXTERNE du cast — c'est elle qui porte `profondeur`. */
    externe?: boolean;
    /** Photographier les champs A L'ENTREE (cf. `photographier`). */
    photo?: boolean;
    entrees: number;
    sorties: number;
    /** Les `this`/visuels entres et pas encore ressortis, dans l'ordre. */
    enVol: string[];
    /** Photos prises a l'entree, en parallele de `enVol` — meme empilement, meme depilement. */
    photos: Record<string, unknown>[];
    /** Le THREAD de chaque appel en vol, empile/depile comme `enVol`. */
    threads: number[];
    refus: string | null;
}

// ⚠ << UN `onEnter` SANS `onLeave` EST UN JET >> — CETTE PREMISSE, ECRITE EN TETE DE FICHIER,
// EST INCOMPLETE, ET LA MESURE DU 2026-08-19 L'A MISE EN DEFAUT.
//
// Sur la 5e reproduction, avec tous les capteurs armes : les CINQ conditions gardees de
// `ParseTargetsFromQueue` sont NON NULLES a l'entree (photo prise sur place), le helper de jet
// n'a PAS tire (`jetsVus: 0`), et il n'y a AUCUNE `access-violation` (0 sur 311 exceptions,
// toutes `system`). Autrement dit : rien n'indique un jet, et pourtant l'appel n'est pas revenu.
//
// Il reste une explication que la premisse EXCLUT A TORT : l'appel est peut-etre ENCORE EN VOL.
// Un `onEnter` sans `onLeave` veut dire << pas revenu >>, ce qui couvre le jet ET l'appel qui
// dure. Les deux se distinguent par le THREAD : si l'appel tourne encore, son thread existe et
// il est distinct du thread principal (celui-ci n'est PAS bloque -- 364 frames en 3 s).
//
// D'ou ce releve. Il ne prouve rien a lui seul ; il RETIRE une confusion que le compteur
// entrees/sorties ne peut pas lever.

/** Le thread du dernier appel REVENU normalement — la reference a laquelle comparer un
 *  orphelin. `null` = aucun appel sain observe. */
let dernierThreadSain: number | null = null;

/** `null` = PAS MESURE (l'enumeration a echoue), jamais rabattu sur << mort >> : un capteur qui
 *  rend `false` sur sa propre panne fermerait a tort l'hypothese << encore en vol >>. */
function threadVivant(id: number): boolean | null {
    try { return Process.enumerateThreads().some((t) => t.id === id); }
    catch { return null; }
}

function threadsVivants(): number[] | null {
    try { return Process.enumerateThreads().map((t) => t.id); }
    catch { return null; }
}

const ANCRES: Ancre[] = [
    {
        symbole: "IdunBattle.View.BattleStream.GroupHandlers.Ability_Power_GroupHandler"
            + "$$SetupAndExecuteAbility",
        ns: "IdunBattle.View.BattleStream.GroupHandlers",
        cls: "Ability_Power_GroupHandler",
        methode: "SetupAndExecuteAbility",
        argVisuel: 1, externe: true,
        entrees: 0, sorties: 0, enVol: [], photos: [], threads: [], refus: null,
    },
    {
        symbole: "IdunBattle.View.AbilityConfigs.AbilityVisualsBase$$Init",
        ns: "IdunBattle.View.AbilityConfigs",
        cls: "AbilityVisualsBase",
        methode: "Init",
        argVisuel: 0,
        entrees: 0, sorties: 0, enVol: [], photos: [], threads: [], refus: null,
    },
    {
        symbole: "IdunBattle.View.AbilityConfigs.AbilityVisualsBase$$ParseTargetsFromQueue",
        ns: "IdunBattle.View.AbilityConfigs",
        cls: "AbilityVisualsBase",
        methode: "ParseTargetsFromQueue",
        argVisuel: 0, photo: true,
        entrees: 0, sorties: 0, enVol: [], photos: [], threads: [], refus: null,
    },
    {
        symbole: "IdunBattle.View.AbilityConfigs.AbilityVisualsBase$$Execute",
        ns: "IdunBattle.View.AbilityConfigs",
        cls: "AbilityVisualsBase",
        methode: "Execute",
        argVisuel: 0,
        entrees: 0, sorties: 0, enVol: [], photos: [], threads: [], refus: null,
    },
];

// --------------------------- LES CINQ CONDITIONS DE JET, PHOTOGRAPHIEES A L'ENTREE
//
// Le decompile de `ParseTargetsFromQueue` donne une liste FINIE : le corps retombe sur le
// helper de jet FINAL si l'une de ces cinq valeurs est nulle --
//   (A) `HitTargets` (+0xf8) ; (B) le tableau de filtre `{0x1a, 0x1b}` alloue localement ;
//   (C) `MainGroup` (+0x108) ; (D) `GetGroupMessages(MainGroup, 0x3d)` ; (E)
//   `GetGroupMessages(MainGroup, filtre)`.
//
// POURQUOI A L'ENTREE, ET PAS APRES COUP. Le post-mortem a deja conclu << donnee INTACTE >>
// sur ces memes champs -- une conclusion qui ne vaut RIEN sur un `MonoBehaviour` POOLE : entre
// l'abandon et la relecture, l'instance peut avoir ete rendue au pool puis re-louee, donc on
// relit l'etat d'un AUTRE usage sous le meme pointeur. La photo prise a l'entree ne souffre
// pas de ca. (Ce que la relecture etablit quand meme : `RootGroup`/`MainGroup` designaient
// toujours le meme groupe abandonne -- donc CE recyclage-la n'a pas eu lieu. La photo tranche
// pour de bon.)
//
// LECTURE PURE : que des `readPointer` sur des offsets resolus par nom.

function photographier(p: NativePointer): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    let klass: NativePointer;
    try { klass = p.readPointer(); }
    catch (e) { return { erreur: "`this` illisible : " + (e as Error).message }; }

    /** Rend le pointeur du champ, ou une CHAINE qui dit pourquoi on n'a pas pu — jamais
     *  `null` par defaut : << champ absent >> et << champ nul >> ne se confondent pas. */
    const lire = (nom: string, ...alias: string[]): NativePointer | string => {
        for (const a of [nom, ...alias]) {
            try {
                const off = getFieldOffset(klass, a);
                if (off > 0) return p.add(off).readPointer();
            } catch { /* alias suivant */ }
        }
        return "<champ introuvable>";
    };
    const dire = (v: NativePointer | string): unknown =>
        typeof v === "string" ? v : (v.isNull() ? null : v.toString());

    const hit = lire("HitTargets", "<HitTargets>k__BackingField");
    const main = lire("MainGroup", "<MainGroup>k__BackingField");
    const root = lire("RootGroup", "<RootGroup>k__BackingField");
    const utils = lire("Utils", "<Utils>k__BackingField");
    out.HitTargets = dire(hit);   // (A)
    out.MainGroup = dire(main);   // (C)
    out.RootGroup = dire(root);
    out.Utils = dire(utils);

    // `Utils.StreamMessages` (+0x88) est deref SANS garde en tete de boucle : s'il manque,
    // c'est une faute d'ACCES, pas un jet propre.
    if (typeof utils !== "string" && !utils.isNull()) {
        try {
            const off = getFieldOffset(utils.readPointer(), "StreamMessages");
            out.StreamMessages = off > 0
                ? (utils.add(off).readPointer().isNull() ? null : "pose")
                : "<champ introuvable>";
        } catch (e) { out.StreamMessages = "<illisible : " + (e as Error).message + ">"; }
    } else {
        out.StreamMessages = "<Utils absent>";
    }

    // Le nombre de messages du groupe : c'est ce que (D)/(E) filtrent.
    if (typeof main !== "string" && !main.isNull()) {
        try {
            const off = getFieldOffset(main.readPointer(), "_messages");
            out.messagesDuGroupe = off > 0 && !main.add(off).readPointer().isNull()
                ? main.add(off).readPointer().add(0x18).readS32()
                : null;
        } catch { out.messagesDuGroupe = "<illisible>"; }
    }
    return out;
}

const listeners: InvocationListener[] = [];
let ancre = false;

// ------------------------------------------------- LA PILE, AU MOMENT DU JET
//
// L'ECART entrees/sorties dit QUEL ETAGE lache. Il ne dit pas OU dans son corps, et le
// post-mortem ne le rendra pas : mesure du 2026-08-19, tous les deref non gardes de
// `ParseTargetsFromQueue` ont leur donnee INTACTE apres coup, et le sous-groupe `0x3d` du
// groupe ABANDONNE porte exactement les memes types (26 x6 + 21) que celui d'un groupe SAIN
// de la MEME unite. La forme des donnees ne discrimine pas -> il faut la PILE.
//
// `exception-tracer` est aveugle ici (0 ligne sur 8 668 evenements) : un null-deref genere par
// IL2CPP n'appelle pas `il2cpp_raise_exception`, il appelle son helper INTERNE. Cet helper n'a
// AUCUN symbole -- c'est un placeholder `FUN_*`, sans `MethodInfo`. C'est exactement le cas que
// `pinnedAddress` existe pour couvrir : le porteur DECLARE son build, le foyer le CONFRONTE au
// build charge, et rend `null` en le DISANT plutot que d'attacher sur du code arbitraire.
//
// ARME A LA DEMANDE, et ce n'est pas de la prudence de facade : ce helper est appele pour TOUT
// null-deref du jeu, pas seulement les notres. On ne l'ancre que le temps d'une reproduction,
// et on ne RETIENT une pile que si un cast d'ability est en vol (`profondeur > 0`) -- sinon on
// capturerait le bruit de tout le reste du jeu.

const PIN_JET_NUL = {
    build: "t6dpr4k06g",
    va: 0x1801f5460,
    symbol: "FUN_1801f5460",
    what: "helper IL2CPP de jet -- construit l'exception puis `int 3` inatteignable ; appele a "
        + "chaque deref non garde. AUCUN symbole : placeholder `FUN_*`, sans `MethodInfo`.",
    how: "chercher dans le decompile d'une methode a null-checks (ex. "
        + "`IdunBattle.View.AbilityConfigs.AbilityVisualsBase$$ParseTargetsFromQueue`) le "
        + "`FUN_*` marque « Subroutine does not return » -- il est appele une douzaine de fois.",
};

interface Pile {
    /** Les cadres, en RVA (jamais en VA : une VA ne survit pas au build). */
    cadres: string[];
    horsModule: number;
    /** Ce qui etait en vol au moment du jet, pour rattacher la pile a une ability. */
    enVol: Record<string, unknown> | null;
}

const piles: Pile[] = [];
const PILES_MAX = 8;
let listenerJet: InvocationListener | null = null;
let refusJet: string | null = null;
let jetsVus = 0;

/** Profondeur de cast d'ability en cours — portee par l'ancre la plus EXTERNE
 *  (`SetupAndExecuteAbility`), donc elle couvre `Init` ET `ParseTargetsFromQueue`. */
let profondeur = 0;

// ------------------------------------ LA FAUTE MATERIELLE, ATTRAPEE LA OU ELLE TOMBE
//
// POURQUOI CE CAPTEUR-CI, ET PAS UN DE PLUS SUR LE HELPER DE JET. Le helper epingle
// (`FUN_1801f5460`) EST le jet des cinq branches gardees de `ParseTargetsFromQueue` -- et il
// n'a JAMAIS tire. Donc l'abandon ne passe par aucune de ces cinq branches : ce qui reste est
// un deref NON garde, c'est-a-dire une faute d'ACCES materielle. Le decompile en expose un
// tres visible des la tete de fonction, un triple deref sur une statique de classe, sans le
// moindre test.
//
// Une faute d'acces ne s'observe pas avec un `Interceptor` : elle ne franchit aucun appel.
// `Process.setExceptionHandler` la voit LA OU ELLE TOMBE, avec l'instruction fautive et
// l'adresse deref. C'est le seul instrument qui nomme le deref coupable.
//
// ⚠ IL N'Y A PAS DE `removeExceptionHandler` DANS FRIDA. Le gestionnaire est donc pose UNE
// fois et garde par un drapeau : << desarmer >> l'eteint, ne le retire pas. Le dire plutot que
// laisser croire a un retrait.
//
// ⚠ ET IL NE GERE JAMAIS RIEN. Il rend TOUJOURS `false`, donc la chaine SEH du jeu se deroule
// exactement comme si on n'etait pas la : ce capteur ne peut pas changer l'issue qu'il
// observe. Rendre `true` reprendrait l'execution et FABRIQUERAIT un comportement -- c'est
// precisement la faute que << un natif qui ECRIT s'OBSERVE d'abord >> interdit.

// ⚠ ET IL FILTRE SUR `access-violation`, PARCE QU'IL VOIT *TOUTES* LES EXCEPTIONS.
// Mesure du 2026-08-19, premiere mise en service : sur une bataille sans le moindre blocage, il
// a retenu **6** << fautes >> pendant des casts (et compte **353** hors cast). Toutes portaient
// `type: "system"`, AUCUNE `memory`, une adresse fautive HORS module (`0x7ffd...`, une DLL
// systeme), la MEME pile aux six, et surtout `onFinished: true` -- des casts REUSSIS. La pile,
// resolue : `IdunMeta.Utils.Extensions.Enum$$TryParse<T>` -> `System.Enum$$Parse` ->
// `System.Enum$$TryParseEnum` -> helper de jet -> `RaiseException`. Autrement dit un `TryParse`
// implemente par try/catch autour de `Parse` : du bruit de fonctionnement normal, des centaines
// de fois par bataille.
//
// Un capteur qui rend ce bruit-la sous le nom de << faute >> ne se contente pas d'etre inutile :
// il FABRIQUE une correlation (6 fautes, 6 casts) qu'un lecteur presse prendrait pour la cause.
// D'ou le filtre. Les types ECARTES sont COMPTES et publies (`parType`) -- sans quoi << 0
// retenue >> se lirait comme << aucune exception >>, ce qui serait faux de trois ordres de
// grandeur.

interface FauteNative {
    type: string;
    /** L'instruction fautive, en RVA (jamais en VA : une VA ne survit pas au build). */
    ou: string | null;
    ouBrut: string;
    /** Le module qui porte l'instruction — `null` si elle tombe hors de tout module connu.
     *  Une faute hors `GameAssembly.dll` n'accuse PAS le jeu. */
    module: string | null;
    /** L'acces qui a faute, et l'adresse VISEE — c'est elle qui nomme le champ nul. */
    operation: string | null;
    adresseVisee: string | null;
    cadres: string[];
    horsModule: number;
    profondeur: number;
    /** Ce qui etait en vol, pour rattacher la faute a une ability. */
    enVol: Record<string, unknown> | null;
}

/** Le SEUL type retenu. Les autres sont comptes, jamais rendus comme des fautes. */
const TYPE_RETENU = "access-violation";

const fautes: FauteNative[] = [];
const FAUTES_MAX = 8;
let sehPose = false;
let sehActif = false;
let fautesVues = 0;
/** Fautes tombees HORS cast — comptees seulement, pour que << 0 retenue >> ne se lise pas
 *  comme << aucune faute dans le process >>. */
let fautesHorsCast = 0;
/** Toutes les exceptions vues, PAR TYPE, cast ou pas — la mesure de ce qu'on ecarte. */
const parType: Record<string, number> = {};

function poserSeh(): boolean {
    if (sehPose) return sehPose;
    sehPose = true;
    Process.setExceptionHandler((d): boolean => {
        // JAMAIS gere — cf. l'avertissement ci-dessus. Tous les retours sont `false`.
        try {
            if (!sehActif) return false;
            parType[d.type] = (parType[d.type] ?? 0) + 1;
            if (d.type !== TYPE_RETENU) return false;
            if (profondeur <= 0) { fautesHorsCast++; return false; }
            fautesVues++;
            if (fautes.length >= FAUTES_MAX) return false;
            let cadres: string[] = [];
            let horsModule = 0;
            try {
                for (const a of Thread.backtrace(d.context, Backtracer.ACCURATE)) {
                    const r = rvaDe(a);
                    if (r === null) { horsModule++; continue; }
                    cadres.push(r);
                }
            } catch (e) { cadres = ["<pile illisible : " + (e as Error).message + ">"]; }
            const ext = ANCRES.find((a) => a.externe);
            const dernier = ext && ext.enVol.length ? ext.enVol[ext.enVol.length - 1] : null;
            let quoi: Record<string, unknown> | null = null;
            if (dernier) { try { quoi = decrireVisuel(ptr(dernier)); } catch { quoi = null; } }
            let mod: string | null = null;
            try { mod = Process.findModuleByAddress(d.address)?.name ?? null; } catch { mod = null; }
            fautes.push({
                type: d.type,
                ou: rvaDe(d.address),
                ouBrut: d.address.toString(),
                module: mod,
                operation: d.memory ? d.memory.operation : null,
                adresseVisee: d.memory ? d.memory.address.toString() : null,
                cadres, horsModule, profondeur, enVol: quoi,
            });
        } catch { /* un capteur ne doit JAMAIS changer l'issue qu'il observe */ }
        return false;
    });
    return sehPose;
}

function rvaDe(a: NativePointer): string | null {
    try {
        const d = a.sub(il2cppBase);
        const n = d.toUInt32();
        // Un cadre hors du module rend un delta absurde : le COMPTER, pas l'inventer.
        if (d.compare(ptr(0)) < 0 || n > 0x8000000) return null;
        return "rva:0x" + n.toString(16);
    } catch { return null; }
}

/** Le groupe porte par un visuel, NOMME. `null` quand le champ n'est pas encore pose --
 *  ce qui est le cas normal a l'ENTREE d'`Init`, et c'est pour ca qu'on relit au rapport. */
function decrireVisuel(p: NativePointer): Record<string, unknown> {
    const out: Record<string, unknown> = { ptr: p.toString() };
    for (const champ of ["RootGroup", "MainGroup"]) {
        try {
            const off = getFieldOffset(p.readPointer(), champ);
            if (off <= 0) { out[champ] = null; continue; }
            const g = p.add(off).readPointer();
            if (g.isNull()) { out[champ] = null; continue; }
            const desc: Record<string, unknown> = { ptr: g.toString() };
            try {
                const offEnt = getFieldOffset(g.readPointer(), "<EntityId>k__BackingField");
                desc.entityId = offEnt > 0 ? g.add(offEnt).readS32() : null;
            } catch { desc.entityId = null; }
            try {
                desc.source = champTexte(g, "<Source>k__BackingField");
            } catch { desc.source = null; }
            out[champ] = desc;
        } catch { out[champ] = null; }
    }
    // `_onFinished` est LE discriminant : pose en 1re instruction d'`Execute`.
    try {
        const off = getFieldOffset(p.readPointer(), "_onFinished");
        out.onFinished = off > 0 && !p.add(off).readPointer().isNull();
    } catch { out.onFinished = null; }
    return out;
}

function ancrer(): void {
    if (ancre) return;
    ancre = true;
    for (const a of ANCRES) {
        try {
            const klass = findClassAnywhere(a.ns, a.cls);
            if (!klass || klass.isNull()) { a.refus = "classe introuvable"; continue; }
            const mi = findMethod(klass, a.methode);
            if (!mi || mi.ptr.isNull()) { a.refus = "methode non resolue"; continue; }
            listeners.push(Interceptor.attach(mi.ptr, {
                onEnter(args) {
                    a.entrees++;
                    if (a.externe) profondeur++;
                    try { a.threads.push(Process.getCurrentThreadId()); }
                    catch { a.threads.push(-1); }
                    try { a.enVol.push(args[a.argVisuel].toString()); }
                    catch { a.enVol.push("<argument illisible>"); }
                    if (a.photo) {
                        // Empile TOUJOURS, meme en echec : `photos` doit rester en phase avec
                        // `enVol`, sinon le depilement associe une photo au mauvais appel.
                        try { a.photos.push(photographier(args[a.argVisuel])); }
                        catch (e) { a.photos.push({ erreur: (e as Error).message }); }
                    }
                },
                onLeave() {
                    a.sorties++;
                    if (a.externe && profondeur > 0) profondeur--;
                    // Le deroulage d'exception SAUTE ce bloc : ce qui reste dans `enVol` est
                    // exactement ce qui n'est jamais revenu -- jet OU appel encore en vol.
                    a.enVol.pop();
                    if (a.photo) a.photos.pop();
                    const t = a.threads.pop();
                    if (typeof t === "number" && t > 0) dernierThreadSain = t;
                },
            }));
        } catch (e) {
            a.refus = (e as Error).message;
        }
    }
}

/** L'ancrage du helper de jet. Rendu SEPAREMENT du reste : il est armable, et son refus doit
 *  se lire (build qui a bouge -> `pinnedAddress` rend `null` en le disant). */
function armerJet(armer: boolean): { ok: boolean; arme: boolean; error?: string } {
    if (!armer) {
        if (listenerJet) { listenerJet.detach(); listenerJet = null; }
        return { ok: true, arme: false };
    }
    if (listenerJet) return { ok: true, arme: true };
    const p = pinnedAddress(PIN_JET_NUL);
    if (p === null) {
        refusJet = "adresse epinglee REFUSEE -- cf. `nameResolutionStatus.pinnedAddressRefusals`";
        return { ok: false, arme: false, error: refusJet };
    }
    refusJet = null;
    listenerJet = Interceptor.attach(p, {
        onEnter() {
            // Le helper tire pour TOUT le jeu. On ne retient que ce qui tombe PENDANT un cast.
            if (profondeur <= 0) return;
            jetsVus++;
            if (piles.length >= PILES_MAX) return;
            let cadres: string[] = [];
            let horsModule = 0;
            try {
                for (const a of Thread.backtrace(this.context, Backtracer.ACCURATE)) {
                    const r = rvaDe(a);
                    if (r === null) { horsModule++; continue; }
                    cadres.push(r);
                }
            } catch (e) { cadres = ["<pile illisible : " + (e as Error).message + ">"]; }
            const ext = ANCRES.find((a) => a.externe);
            const dernier = ext && ext.enVol.length ? ext.enVol[ext.enVol.length - 1] : null;
            let quoi: Record<string, unknown> | null = null;
            if (dernier) { try { quoi = decrireVisuel(ptr(dernier)); } catch { quoi = null; } }
            piles.push({ cadres, horsModule, enVol: quoi });
        },
    });
    return { ok: true, arme: true };
}

export function register(ctx: Ctx): void {
    ancrer();

    /** QUEL ETAGE A LACHE, et sur quel groupe. Read-only.
     *
     *  `ecart > 0` sur une ancre = autant d'appels partis en EXCEPTION a cet etage. L'ancre la
     *  plus PROFONDE qui montre un ecart est le foyer ; ses parentes en montrent un aussi, parce
     *  que le jet les traverse.
     *
     *  `ecart == 0` PARTOUT alors que la file est bloquee refute l'hypothese du jet -- et c'est
     *  une reponse, pas un echec du capteur. */
    /** ARMER la capture de PILE au moment du jet. Ecrit RIEN dans le jeu (un `attach` en
     *  `onEnter` pur), mais s'arme explicitement : le helper vise est appele pour TOUT
     *  null-deref du jeu, pas seulement les notres. */
    ctx.rpc.visuelAbandonnePile = (body?: { armer?: boolean }): unknown => {
        const r = body?.armer === false ? armerJet(false) : armerJet(true);
        return { ...r, jetsVus, piles: piles.length, plafond: PILES_MAX, refus: refusJet };
    };

    /** ARMER la capture de FAUTE MATERIELLE. Le gestionnaire ne GERE rien (il rend toujours
     *  `false`), donc il ne peut pas changer l'issue qu'il observe. `armer: false` l'ETEINT ;
     *  il ne le retire pas — Frida n'offre aucun retrait, et le pretendre serait faux. */
    ctx.rpc.visuelAbandonneFaute = (body?: { armer?: boolean }): unknown => {
        const veut = body?.armer !== false;
        if (veut) poserSeh();
        sehActif = veut;
        return {
            ok: true, actif: sehActif, pose: sehPose,
            typeRetenu: TYPE_RETENU, parType,
            fautesVues, fautesHorsCast, retenues: fautes.length, plafond: FAUTES_MAX,
            note: "rend TOUJOURS `false` a Windows : la chaine SEH du jeu se deroule inchangee. "
                + "`armer:false` ETEINT le gestionnaire, il ne le retire pas (Frida n'a pas de "
                + "`removeExceptionHandler`). Seul `" + TYPE_RETENU + "` est retenu : les autres "
                + "types sont du bruit de fonctionnement (`Enum.TryParse`), comptes dans "
                + "`parType`.",
        };
    };

    ctx.rpc.visuelAbandonneEtat = (): unknown => ({
        ok: true,
        ancre,
        jet: { arme: listenerJet !== null, refus: refusJet, jetsVus, piles },
        faute: {
            actif: sehActif, pose: sehPose, typeRetenu: TYPE_RETENU, parType,
            fautesVues, fautesHorsCast, fautes,
        },
        etages: ANCRES.map((a) => ({
            symbole: a.symbole,
            refus: a.refus,
            entrees: a.entrees,
            sorties: a.sorties,
            ecart: a.entrees - a.sorties,
            // On RELIT les objets restes en vol : a l'entree d'`Init` les groupes ne sont pas
            // encore poses, donc seule une relecture tardive les nomme.
            enVol: a.enVol.map((s) => {
                try { return decrireVisuel(ptr(s)); }
                catch { return { ptr: s, relecture: "impossible" }; }
            }),
            // Les PHOTOS, elles, datent de l'ENTREE — c'est ce qui les rend opposables a un
            // objet poole, contrairement a la relecture ci-dessus.
            photos: a.photo ? a.photos : undefined,
            // LE THREAD de chaque appel resté en vol, et s'il VIT ENCORE. C'est ce qui
            // distingue << a jete >> de << tourne toujours >> : un thread mort ferme la
            // seconde hypothese, un thread vivant la rend probable.
            threadsEnVol: a.threads.map((t) => ({ thread: t, vivant: threadVivant(t) })),
        })),
        // La reference : le thread des appels qui, eux, sont revenus.
        dernierThreadSain,
        threadsVivants: threadsVivants(),
    });
}

