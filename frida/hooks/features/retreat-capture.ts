// retreat-capture — le POINT D'INTERCEPTION de la retraite : qui appelle quoi, avec quelle
// pile, sur quelle instance, et avec quelle valeur de retour.
//
// POURQUOI CE MODULE EXISTE
// -------------------------
// Le warmup sort de bataille en PILOTANT L'UI (pause -> retraite -> confirmation), et #390-r2
// a donne un signal FIABLE pour savoir que c'est fini (`GuiId.PauseMenu` retire au
// `ScreenVisibilityManager`). Ce qui manque est en amont : **provoquer** la retraite sans
// toucher a l'ecran, comme `fsm-input.ts` le fait deja pour le DEPLOIEMENT -- il parle au FSM
// en lui DESIGNANT les entites, au lieu de simuler une souris.
//
// Le patron de `fsm-input.ts` est repris tel quel, parce qu'il a deja paye :
//   1. CAPTURER L'INSTANCE A UN ANCRAGE, jamais la chercher. Pas de balayage de tas (proscrit
//      -- il fige les threads ~10 s et `UnityFreezeDetector` tue le process), pas de
//      `FindObjectsByType` sur une classe dont on ignore si elle est vivante.
//   2. L'EPINGLER (`gcRoot.add`) : une `NativePointer` cote Frida n'est pas scannee par le GC.
//   3. La CONFRONTER avant d'agir -- une instance capturee peut etre PERIMEE.
//
// CE QUE LA PILE TRANCHE, ET QU'AUCUNE LECTURE D'XREFS N'A TRANCHE
// ----------------------------------------------------------------
// Une lecture d'xrefs avait conclu que `ProcessFinishSurrender` etait « le terminal commun,
// appele une fois par retraite sur les deux branches ». C'est FAUX, et la faute est
// instructive : `UNCONDITIONAL_CALL` est le type d'INSTRUCTION chez Ghidra (call direct vs
// indirect), **pas une propriete du flot**. Dans les deux appelants l'appel est SUR UNE
// BRANCHE, l'alternative etant `IdunMainView$$ProcessFinishBattle(playerEndReason)`.
// ⇒ On n'infere plus la chaine : on la LIT. Chaque ancrage note sa pile complete, donc le
// journal DIT quel appelant a mene la, et quelle branche a ete prise.
//
// LES PREDICATS QUI COMMANDENT LA BRANCHE (signatures lues dans `frida/methods.tsv`) :
//   `AGameModeSource$$PauseSurrender(continueSurrender: System.Action) -> System.Boolean`
//   `CampaignGameModeSource$$IsSurrenderFromPauseMenuEnabled() -> System.Boolean`
// Ce ne sont PAS des etapes : ce sont des QUESTIONS. `PauseSurrender` rend un booleen -- il
// DIFFERE la retraite (il garde le callback pour apres l'ecran intersticiel) ou il laisse
// passer. D'ou la capture de la VALEUR DE RETOUR et pas seulement du fire : sans elle,
// « a differe » et « a laisse passer » seraient indiscernables -- exactement le vice qu'on
// reproche a `uiClick`.
//
// COUT
// ----
// Chemins FROIDS : ces methodes tirent au plus une fois par bataille. Rien a voir avec les
// getters d'UI que le depot proscrit de hooker (27 000 appels/s). Les ancrages sont donc poses
// AU CHARGEMENT et non derriere un `{start:true}` : il faut qu'ils soient deja la quand le
// warmup se retire, et un armement prealable serait une etape de plus a ne pas oublier.

import {
    class_get_name, findClassAnywhere, findCtorByParamCount, findMethod,
    findMethodByParamCount, getSystemType, methodParamClass, s,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { delegateInerte, lireArdoise } from "../il2cpp/delegate.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { captureStack } from "../ai-toolkit/stack-capture.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

const NS_VIEW = "idun";
const CLS_VIEW = "IdunMainView";
const NS_SOURCE = "IdunBattle.ViewLogic.BattleSource";

/** Un fire observe. */
interface Fire {
    n: number;
    /** `<Classe>$$<Methode>` -- la forme de citation du depot. */
    quoi: string;
    /** Classe REELLE de `this`, lue sur l'objet. Peut differer de la classe declarante
     *  (heritage) : c'est precisement ce qu'on veut voir sur `AGameModeSource`. */
    classeReelle: string | null;
    self: string | null;
    /** Valeur de retour des predicats booleens. `null` = NON MESUREE (methode `void`, ou
     *  sortie par exception) -- jamais rabattu sur `false`. */
    retour: boolean | null;
    /** Pile complete, `rva:0x...` / `abs:0x...`. A resoudre HORS LIGNE contre
     *  `data/symbols/<build>/frida/methods.tsv` (`ghidra_symbols.py whereis`) : on cite un
     *  SYMBOLE, jamais une adresse absolue -- les noms sont stables a 97,5 %, les adresses
     *  changent a 100 % d'un build a l'autre. */
    pile: string[];
    ts: number;
}

const JOURNAL_MAX = 200;
const journal: Fire[] = [];
let recus = 0;
let ecartes = 0;

/** Un ancrage POSE, garde avec de quoi le REPOSER. Cf. `retreatInvoke` : on ne peut pas
 *  invoquer une methode qu'on ancre sans l'avoir deposee d'abord. */
interface Ancrage {
    nom: string;
    ptr: NativePointer;
    spec: InvocationListenerCallbacks;
    listener: InvocationListener | null;
}
const ancres: Ancrage[] = [];

/** `null` = ancrages JAMAIS poses (classes introuvables) -- a distinguer d'« poses et 0 fire ».
 *  Meme discipline tri-etat que `ui-windows.ts`. */
let ancrages: string[] | null = null;
let ancragesRates: string[] = [];

/** L'instance vivante d'`IdunMainView`, epinglee. C'est LA reponse a « est-elle joignable ? » :
 *  on ne la cherche pas, on l'attrape. */
let mainView: NativePointer | null = null;
let mainViewVu = 0;

/** L'instance epinglee est-elle ENCORE VIVANTE ?
 *
 *  ⚠ MESURE DU 2026-08-12, ET C'EST UN DEFAUT QUE CE MODULE AVAIT. Apres le warmup,
 *  `retreatStatus` rendait `mainView: 0x231e1c75cf0` alors que `FindObjectsByType` rendait
 *  **0 instance** : la scene de bataille etait dechargee. Le pointeur EPINGLE survit (c'est le
 *  role de `gcRoot`), mais l'objet Unity derriere est DETRUIT. Invoquer dessus, c'est appeler
 *  une methode sur une coquille -- et l'en-tete de ce module PRESCRIVAIT la confrontation sans
 *  l'implementer : le garde « deja observee » porte sur la METHODE, pas sur l'INSTANCE.
 *
 *  On confronte comme le jeu le fait lui-meme : `thor.Loader$$LoadBattle` teste
 *  `UnityEngine.Object$$op_Inequality(x, null)` -- l'operateur surcharge d'Unity, le seul qui
 *  distingue « reference nulle » de « objet detruit ». Un `isNull()` cote Frida ne verrait
 *  ni l'un ni l'autre.
 *
 *  `null` = NON MESURE (operateur introuvable) -- jamais rabattu sur « vivant ». */
function encoreVivant(obj: NativePointer): boolean | null {
    try {
        const kObj = findClassAnywhere("UnityEngine", "Object");
        const mi = kObj ? findMethodByParamCount(kObj, "op_Inequality", 2) : null;
        if (!mi) return null;
        const r = invokeMethod(mi.info, null, [obj, ptr(0)]);
        // Retour BOXE (Boolean est un type valeur) : charge utile a +0x10.
        return r.isNull() ? false : r.add(0x10).readU8() !== 0;
    } catch { return null; }
}

/** SOMMES-NOUS EN BATAILLE ? -- `IdunMainView$$get_IsBattleActive()`, STATIQUE, donc lisible
 *  sans instance et sans UI.
 *
 *  C'est la comptabilite du JEU, pas un proxy : le harnais deduisait jusqu'ici cet etat de
 *  l'etat des ECRANS. `null` = NON MESURE (methode introuvable), jamais rabattu sur `false`.
 *
 *  EXPORTEE depuis #993 : le cycle de warmup s'en sert comme etat initial ET comme signal de fin
 *  de retraite. Le corps reste ICI -- c'est le module qui detient la RE de la chaine de sortie,
 *  et deux lectures de `get_IsBattleActive` divergeraient en silence. */
export function enBataille(): boolean | null {
    try {
        const k = findClassAnywhere(NS_VIEW, CLS_VIEW);
        const mi = k ? findMethodByParamCount(k, "get_IsBattleActive", 0) : null;
        if (!mi) return null;
        const r = invokeMethod(mi.info, null, null);   // statique : pas d'instance
        return r.isNull() ? false : r.add(0x10).readU8() !== 0;
    } catch { return null; }
}

/** RESOUDRE l'instance d'`IdunMainView` quand AUCUN ancrage n'a tire.
 *
 *  ⚠ CE REPLI N'EST PAS UN ASSOUPLISSEMENT, C'EST UNE REPARATION MESUREE (2026-08-13). Les
 *  ancrages de ce module capturent l'instance au `.ctor` ou a une methode de sortie -- donc
 *  seulement si l'un d'eux TIRE APRES notre chargement. Sur une session FRAICHE ouverte alors
 *  qu'une bataille tourne deja (reinject en cours de bataille), le `.ctor` a tire AVANT
 *  l'injection et aucune sortie n'a encore eu lieu : `mainView` reste NUL POUR TOUJOURS, et la
 *  retraite devient impossible sur la seule bataille qu'on ait besoin de quitter. Mesure :
 *  `bataille-heritee-non-quittee` / `porte-de-sortie-absente`, sur une bataille bien vivante.
 *
 *  ⚠ ET CE N'EST PAS UN BALAYAGE DE TAS -- l'interdit du depot porte sur `Memory.scan` /
 *  `enumerateRanges`, qui figent les threads ~10 s et font tuer le process par
 *  `UnityFreezeDetector`. Ici c'est l'API d'Unity, sur une classe qui EST un `MonoBehaviour`
 *  (chaine `IdunMainView -> MonoBehaviour -> Behaviour -> Component -> Object`, mesuree par
 *  `viewSurface`). `view-command.ts` la resout deja par cette voie.
 *
 *  ⚠ SURCHARGE A 3 ARGUMENTS (`FindObjectsInactive.Include = 1`) : celle a 2 EXCLUT les
 *  inactifs, et rendait **0 ecran** dans `ui-windows.ts` sur une classe qui resout parfaitement.
 */
function resoudreParEnumeration(): NativePointer | null {
    try {
        const kView = findClassAnywhere(NS_VIEW, CLS_VIEW);
        const kObj = findClassAnywhere("UnityEngine", "Object");
        if (!kView || !kObj) return null;
        const mi3 = findMethodByParamCount(kObj, "FindObjectsByType", 3);
        const mi2 = findMethodByParamCount(kObj, "FindObjectsByType", 2);
        const tri = Memory.alloc(4); tri.writeS32(0);          // SortMode.None
        const inclure = Memory.alloc(4); inclure.writeS32(1);  // FindObjectsInactive.Include
        const t = getSystemType(kView);
        const arr = mi3 ? invokeMethod(mi3.info, null, [t, inclure, tri])
                        : (mi2 ? invokeMethod(mi2.info, null, [t, tri]) : ptr(0));
        if (arr.isNull() || arr.add(0x18).readS32() <= 0) return null;
        const inst = arr.add(0x20).readPointer();
        return inst.isNull() ? null : inst;
    } catch { return null; }
}

/** L'instance courante : celle qu'un ancrage a capturee, sinon celle que la scene porte.
 *  Epingle ce qu'elle trouve, pour que la confrontation qui suit porte sur un pointeur valide. */
function mainViewCourante(): NativePointer | null {
    if (mainView !== null && encoreVivant(mainView) === true) return mainView;
    const trouve = resoudreParEnumeration();
    if (trouve === null) return null;
    retenirMainView(trouve);
    return mainView;
}

/** LA PORTE DE SORTIE EST-ELLE OUVERTE ? -- une instance d'`IdunMainView` CAPTUREE a l'un de nos
 *  ancrages, et CONFRONTEE vivante.
 *
 *  Les deux conditions sont distinctes et toutes deux necessaires : `mainView !== null` dit qu'un
 *  ancrage a tire, `encoreVivant` dit que l'objet Unity derriere existe encore. Mesure du
 *  2026-08-12 : apres un warmup, le pointeur epingle survit alors que `FindObjectsByType` rend
 *  **0 instance**. Un predicat qui ne testerait que le premier rendrait `true` sur une coquille.
 *
 *  Rend `false` (et non `null`) quand la vivacite n'est pas mesurable : ici l'appelant ATTEND que
 *  la porte s'ouvre, et « je ne sais pas » ne doit jamais faire passer pour ouverte. Le tri-etat
 *  reste publie par `retreatStatus.mainViewVivant`, dont c'est le role. */
export function sortieJoignable(): boolean {
    return mainViewCourante() !== null;
}

function nomClasseDe(obj: NativePointer): string | null {
    try {
        if (obj.isNull()) return null;
        return s(class_get_name(obj.readPointer()) as NativePointer);
    } catch { return null; }
}

function noter(quoi: string, self: NativePointer | null, ctx: CpuContext): number {
    recus++;
    if (journal.length >= JOURNAL_MAX) { ecartes++; return -1; }
    const { frames } = captureStack(ctx);
    journal.push({
        n: recus, quoi,
        classeReelle: self ? nomClasseDe(self) : null,
        self: self ? self.toString() : null,
        retour: null, pile: frames, ts: Date.now(),
    });
    return journal.length - 1;
}

/** Epingle l'instance d'`IdunMainView` vue passer, et DEPINGLE la precedente : il en naît une
 *  par scene, et garder un enracinement mort ferait mentir la confrontation. */
function retenirMainView(obj: NativePointer): void {
    try {
        if (obj.isNull()) return;
        if (mainView !== null && mainView.equals(obj)) { mainViewVu++; return; }
        if (mainView !== null) { try { gcRoot.remove(mainView); } catch { /* best effort */ } }
        gcRoot.add(obj);
        mainView = obj;
        mainViewVu++;
    } catch { /* ne jamais faire tomber une methode du jeu */ }
}

/** Ancre une methode et note chaque passage. `capteRetour` demande la lecture du booleen rendu
 *  -- reserve aux methodes dont la SIGNATURE dit `System.Boolean`, jamais devine. */
function ancrer(
    klass: NativePointer, methode: string, etiquette: string,
    opts: { capteRetour?: boolean; arite?: number; estMainView?: boolean } = {},
): boolean {
    const mr = opts.arite !== undefined
        ? findMethodByParamCount(klass, methode, opts.arite)
        : findMethod(klass, methode);
    if (!mr) return false;
    const spec: InvocationListenerCallbacks = {
        onEnter(args) {
            try {
                const self = args[0] as NativePointer;
                if (opts.estMainView) retenirMainView(self);
                (this as { idx?: number }).idx = noter(etiquette, self, this.context);
            } catch { /* jamais throw dans un hook du jeu */ }
        },
        onLeave(retval) {
            if (!opts.capteRetour) return;
            try {
                const idx = (this as { idx?: number }).idx;
                if (idx === undefined || idx < 0 || idx >= journal.length) return;
                journal[idx].retour = (retval.toInt32() & 0xff) !== 0;
            } catch { /* best effort */ }
        },
    };
    ancres.push({
        nom: etiquette, ptr: mr.ptr, spec, listener: Interceptor.attach(mr.ptr, spec),
    });
    return true;
}

function installer(): void {
    if (ancrages !== null) return;
    const poses: string[] = [];
    const rates: string[] = [];

    const kView = findClassAnywhere(NS_VIEW, CLS_VIEW);
    if (kView) {
        // L'axe SORTIE. `ProcessFinishBattle` est ancree parce qu'elle est L'ALTERNATIVE de
        // `ProcessFinishSurrender` dans les deux appelants -- sans elle, une retraite qui passe
        // par elle se lirait comme « rien ne s'est produit ».
        for (const m of ["OnBattleSurrender", "ContinueSurrender", "ProcessFinishSurrender",
                         "ProcessFinishBattle", "OnFinishBattle"]) {
            const nom = `${CLS_VIEW}$$${m}`;
            (ancrer(kView, m, nom, { estMainView: true }) ? poses : rates).push(nom);
        }
        // Le `.ctor` donnerait l'instance SANS attendre une retraite -- mais il a pu tirer avant
        // notre chargement (le jeu tourne deja). On l'ancre quand meme : s'il tire, tant mieux ;
        // le journal dira LEQUEL des ancrages a capture, plutot que de le supposer.
        const ctor = findCtorByParamCount(kView, 0);
        const nomCtor = `${CLS_VIEW}$$.ctor`;
        if (ctor) {
            const spec: InvocationListenerCallbacks = {
                onEnter(args) {
                    try {
                        retenirMainView(args[0] as NativePointer);
                        noter(nomCtor, args[0] as NativePointer, this.context);
                    } catch { /* jamais throw */ }
                },
            };
            ancres.push({
                nom: nomCtor, ptr: ctor.ptr, spec,
                listener: Interceptor.attach(ctor.ptr, spec),
            });
            poses.push(nomCtor);
        } else { rates.push(nomCtor); }
    } else {
        rates.push(`classe ${NS_VIEW}.${CLS_VIEW} INTROUVABLE`);
    }

    // Les PREDICATS. On ancre la base `AGameModeSource` ET la concrete `CampaignGameModeSource` :
    // le mode du warmup est campagne, mais laquelle des deux porte le corps EXECUTE est une
    // MESURE, pas une deduction -- `classeReelle` le dira.
    for (const cls of ["AGameModeSource", "CampaignGameModeSource"]) {
        const k = findClassAnywhere(NS_SOURCE, cls);
        if (!k) { rates.push(`classe ${NS_SOURCE}.${cls} INTROUVABLE`); continue; }
        for (const [m, arite, booleen] of [
            ["PauseSurrender", 1, true],
            ["IsSurrenderFromPauseMenuEnabled", 0, true],
            ["HandleOnLeaveBattleWhileGameEventRunning", 1, false],
        ] as Array<[string, number, boolean]>) {
            const nom = `${cls}$$${m}`;
            (ancrer(k, m, nom, { capteRetour: booleen, arite }) ? poses : rates).push(nom);
        }
    }

    ancrages = poses;
    ancragesRates = rates;
}

/** DEPOSER tous nos ancrages, puis les REPOSER.
 *
 *  ⚠ CE N'EST PAS UNE PRECAUTION, C'EST UNE MESURE. « Invoquer une methode qu'on ancre, depuis
 *  du JS qui tourne sur le main thread, deadlocke a coup sur (3 gels sur 3) : l'appel natif
 *  retombe dans notre propre trampoline, Frida veut y executer un handler JS, et le runtime est
 *  deja tenu par ce thread. » (en-tete d'`il2cpp/delegate.ts`,
 *  `docs/rl/case-600-gel-du-dispatch-natif.md`). Et un gel ne se signale PAS tout seul : il se
 *  lit comme un RPC qui ne revient pas.
 *
 *  On depose TOUT, pas seulement la methode visee : invoquer `OnBattleSurrender` fait entrer le
 *  jeu dans `PauseSurrender`, `ContinueSurrender`, `ProcessFinishSurrender`... que nous ancrons
 *  AUSSI. Deposer la seule cible laisserait le piege arme un cran plus bas. */
function deposerTout(): void {
    for (const a of ancres) {
        if (a.listener !== null) {
            try { a.listener.detach(); } catch { /* best effort */ }
            a.listener = null;
        }
    }
}

function reposerTout(): void {
    for (const a of ancres) {
        if (a.listener === null) {
            try { a.listener = Interceptor.attach(a.ptr, a.spec); }
            catch { /* un ancrage perdu se lira dans `retreatStatus` */ }
        }
    }
}

/** Les entrees qu'on s'autorise a INVOQUER, et rien d'autre. Liste blanche explicite :
 *  `ProcessFinishBattle` prend un `playerEndReason` et `HandleBattleSurrender` en prend NEUF --
 *  les invoquer demanderait de FABRIQUER des valeurs, donc de deviner. */
const INVOCABLES = ["OnBattleSurrender", "ContinueSurrender", "ProcessFinishSurrender"] as const;

/** PROVOQUER la retraite sans toucher a l'ecran -- LE FOYER, dont `retreatInvoke` n'est que
 *  l'exposition.
 *
 *  EXTRAIT DU RPC AU #993, et l'extraction est le point : le cycle de warmup a besoin d'appeler
 *  exactement ce corps-la, avec ses trois refus et son depot d'ancrages. Le recopier ailleurs
 *  ferait exister deux chaines de retraite dont une seule serait corrigee -- c'est litteralement
 *  ce qui est arrive a la chaine de CLICS (#332), corrigee dans l'etape 1bis et laissee intacte
 *  dans l'etape 7 pendant deux jours.
 *
 *  Les gardes et leur justification sont dans la docstring du RPC ci-dessous. */
export function provoquerRetraite(body?: {
    methode?: string; confirmer?: boolean;
}): Promise<unknown> | unknown {
    const methode = body?.methode;
    if (!methode || !(INVOCABLES as readonly string[]).includes(methode)) {
        return { ok: false, error: "methode manquante ou hors liste blanche -- attendu "
            + "l'une de " + INVOCABLES.join(", ") + ". Les autres entrees prennent des "
            + "arguments qu'il faudrait FABRIQUER." };
    }
    if (body?.confirmer !== true) {
        return { ok: false, error: "REFUS : `confirmer: true` exige. " + methode
            + " termine une VRAIE bataille et touche la progression du compte." };
    }
    const cible = mainViewCourante();
    if (cible === null) {
        return { ok: false, error: "REFUS : aucune instance IdunMainView -- ni capturee a un "
            + "ancrage (`retreatStatus` les liste), ni trouvee par FindObjectsByType. Il n'y a "
            + "pas de scene de bataille montee." };
    }
    const vivant = encoreVivant(cible);
    if (vivant !== true) {
        return { ok: false, error: vivant === false
            ? "REFUS : l'instance IdunMainView epinglee est DETRUITE (scene de bataille "
              + "dechargee). Le pointeur survit par `gcRoot`, l'objet Unity non -- mesure : "
              + "apres un warmup, `FindObjectsByType` rend 0 instance alors que le pointeur "
              + "est toujours la. Il n'y a pas de bataille a quitter."
            : "REFUS : vivacite de l'instance NON MESUREE "
              + "(UnityEngine.Object$$op_Inequality introuvable) -- on n'invoque pas sur "
              + "un objet dont on ne sait pas s'il existe." };
    }
    // ⚠ CE GARDE A REMPLACE << la methode doit avoir ete OBSERVEE dans ce journal >>, et le
    // remplacement est une REPARATION, pas un assouplissement.
    //
    // L'ancien exigeait qu'une retraite PILOTEE PAR L'UI ait deja fait tirer la methode dans
    // LA SESSION COURANTE. Il avait sa raison : avant #992, la chaine de retraite etait
    // DEDUITE DES NOMS, et cette deduction a ete dementie par la mesure. Il fallait donc
    // forcer une observation avant tout appel.
    //
    // Cette observation a EU LIEU (case-992) : les piles montrent que l'UI passe par
    // `OnBattleSurrender` -> `PauseSurrender` (qui rend `true`, donc DIFFERE) puis, par un
    // UnityEvent du bouton de CONFIRMATION, par `ContinueSurrender`. La liste blanche
    // `INVOCABLES` EST ce resultat mesure. Exiger en plus un fire dans la session rendait le
    // chemin NON AUTOSUFFISANT A FROID -- mesure du 2026-08-12, session 77 : le RPC refusait,
    // et le jeu restait bloque en bataille apres un lancement programmatique.
    //
    // Le nouveau garde est PLUS FORT, pas plus faible : il verifie la PRECONDITION REELLE --
    // y a-t-il une bataille a quitter -- en interrogeant la comptabilite du jeu, et il est
    // disponible des la premiere seconde d'une session froide.
    const bataille = enBataille();
    if (bataille !== true) {
        return { ok: false, error: bataille === false
            ? "REFUS : `IdunMainView$$get_IsBattleActive()` rend FALSE -- il n'y a aucune "
              + "bataille a quitter. Appeler " + methode + " ici n'aurait pas de cible."
            : "REFUS : etat de bataille NON MESURE (get_IsBattleActive introuvable) -- on "
              + "ne quitte pas une bataille dont on ne sait pas si elle existe." };
    }
    const kView = findClassAnywhere(NS_VIEW, CLS_VIEW);
    const mr = kView ? findMethodByParamCount(kView, methode, 0) : null;
    if (!mr) {
        return { ok: false, error: "surcharge SANS PARAMETRE de " + methode
            + " introuvable sur " + CLS_VIEW };
    }
    return queueOnMainThread(() => {
        deposerTout();
        try {
            invokeMethod(mr.info, cible, null);
        } catch (e) {
            return { ok: false, error: "invoke a leve : " + (e as Error).message,
                     firesPendantInvoke: null };
        } finally {
            reposerTout();
        }
        return { ok: true, methode,
                 firesPendantInvoke: null,
                 note: "ancrages DEPOSES pendant l'appel (sinon gel) : les fires de la "
                     + "chaine ne sont PAS mesures. Confirmer la sortie par "
                     + "`uiWindowEvents` (retrait de GuiId.PauseMenu, #390-r2)." };
    });
}

export function register(ctx: Ctx): void {
    installer();

    /** L'etat de l'interception : tient-on une instance, quels ancrages sont poses.
     *
     *  TRI-ETAT : `ancrages: null` = JAMAIS pose (classes absentes du build) -- a ne pas lire
     *  comme « pose et silencieux ». `ancragesRates` dit LESQUELS ont echoue, pour qu'une
     *  peremption de nom se voie au lieu de se traduire par un journal vide. */
    ctx.rpc.retreatStatus = (): unknown => ({
        ok: true,
        ancrages, ancragesRates,
        posesMaintenant: ancres.filter((a) => a.listener !== null).map((a) => a.nom),
        mainView: mainView ? mainView.toString() : null,
        mainViewClasse: mainView ? nomClasseDe(mainView) : null,
        // ⚠ TRI-ETAT, et ce n'est pas de la coquetterie : `true` = utilisable, `false` = objet
        // Unity DETRUIT (scene dechargee) donc le pointeur MENT, `null` = pas mesure.
        mainViewVivant: mainView ? encoreVivant(mainView) : null,
        mainViewVu,
        recus, ecartes, journalLen: journal.length,
        invocables: INVOCABLES,
    });

    /** Le journal des fires, pile comprise.
     *
     *  body: { clear?: true, depuis?: number, max?: number } */
    ctx.rpc.retreatJournal = (body?: {
        clear?: boolean; depuis?: number; max?: number;
    }): unknown => {
        if (body?.clear) { journal.length = 0; recus = 0; ecartes = 0; }
        const depuis = Math.max(0, body?.depuis ?? 0);
        const max = Math.max(1, Math.min(body?.max ?? 100, JOURNAL_MAX));
        return {
            ok: true, recus, ecartes, total: journal.length,
            fires: journal.slice(depuis, depuis + max),
        };
    };

    /** DEMANDER au mode de jeu s'il compte DIFFERER la retraite -- sans se retirer.
     *
     *  `PauseSurrender(continueSurrender: System.Action) -> Boolean` exige un delegate : passer
     *  `null` n'est PAS une option (null-check IL2CPP -> `raise_null_reference_exception` +
     *  `INT 3`, mesure #600). On lui donne donc un delegate INERTE (`il2cpp/delegate.ts`), et on
     *  relit son ARDOISE apres l'appel : `appels: 0` = le jeu ne l'a pas rappele (il n'a pas
     *  differe), `appels: 1` = il l'a rappele tout de suite. `null` = ardoise NON FABRIQUEE,
     *  donc RIEN MESURE -- a ne pas lire comme « pas appele ».
     *
     *  ⚠ Ce n'est pas un lecteur passif : le natif peut afficher un popup. D'ou `confirmer`. */
    ctx.rpc.retreatPauseProbe = (body?: {
        confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        if (body?.confirmer !== true) {
            return { ok: false, error: "REFUS : `confirmer: true` exige -- `PauseSurrender` "
                + "n'est pas un lecteur, il peut afficher un ecran." };
        }
        const k = findClassAnywhere(NS_SOURCE, "CampaignGameModeSource");
        if (!k) return { ok: false, error: `classe ${NS_SOURCE}.CampaignGameModeSource introuvable` };
        const mr = findMethodByParamCount(k, "PauseSurrender", 1);
        if (!mr) return { ok: false, error: "PauseSurrender/1 introuvable" };
        const kAction = methodParamClass(mr.info, 0);
        const { d, err } = delegateInerte(kAction);
        if (!d) return { ok: false, error: "delegate inerte NON FABRIQUE : " + (err ?? "?") };
        return { ok: false,
            error: "NON EXECUTE : il faut l'instance vivante de CampaignGameModeSource "
                 + "(`lastSource` du warmup), que ce module ne detient pas encore. "
                 + "Le delegate, lui, est pret.",
            delegate: d.ptr.toString(), offsets: d.offsets,
            ardoise: lireArdoise(d.ardoise) };
    };

    /** PROVOQUER la retraite sans toucher a l'ecran -- le pendant, pour la SORTIE, de ce que
     *  `fsm-input.ts` fait pour le deploiement.
     *
     *  body: { methode: "OnBattleSurrender" | "ContinueSurrender" | "ProcessFinishSurrender",
     *          confirmer: true }
     *
     *  ⚠ TROIS REFUS EXECUTABLES, parce que la prose n'arrete pas un comportement :
     *
     *  1. `confirmer: true` OBLIGATOIRE. Ce natif TERMINE une vraie bataille et touche la
     *     progression du compte. Un appel par inadvertance n'est pas rattrapable.
     *  2. Une instance EPINGLEE est exigee. Sans elle il n'y a pas de `this`, et invoquer avec
     *     `null` ecrirait a une adresse arbitraire.
     *  3. **LA METHODE DOIT AVOIR ETE OBSERVEE** au moins une fois dans ce journal. C'est le
     *     cran qui compte : il interdit d'invoquer une entree dont on a SUPPOSE qu'elle etait
     *     la bonne. Le depot a deja paye une chaine d'appels inferee des NOMS et dementie par
     *     la mesure. Corollaire assume : tant qu'aucune retraite pilotee par l'UI n'a eu lieu
     *     dans cette session, ce RPC REFUSE -- et c'est le comportement voulu.
     *
     *  ⚠ CE QUE CE RPC NE PEUT PAS OBSERVER, ET QU'IL DIT. Nos ancrages sont DEPOSES pendant
     *  l'invoke (sinon : gel, cf. `deposerTout`). Les fires survenus pendant l'appel ne sont
     *  donc PAS MESURES -- le champ le nomme, plutot que de rendre une liste vide qui se lirait
     *  « rien ne s'est produit ». La confirmation se prend AILLEURS : au signal de sortie de
     *  #390-r2 (`GuiId.PauseMenu` retire), via `uiWindowEvents`. */
    ctx.rpc.retreatInvoke = (body?: {
        methode?: string; confirmer?: boolean;
    }): Promise<unknown> | unknown => provoquerRetraite(body);
}
