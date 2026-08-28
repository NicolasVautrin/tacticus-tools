// retreat-capture — le POINT D'INTERCEPTION de la retraite : qui appelle quoi, avec quelle
// pile, sur quelle instance, et avec quelle valeur de retour.
//
// POURQUOI CE MODULE EXISTE
// -------------------------
// L'amorce sort de bataille en PILOTANT L'UI (pause -> retraite -> confirmation), et #390-r2
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
// amorce se retire, et un armement prealable serait une etape de plus a ne pas oublier.

import {
    class_get_name, findClassAnywhere, findCtorByParamCount, findMethod,
    findMethodByParamCount, getSystemType, methodParamClass, s,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { delegateInerte, lireArdoise } from "../il2cpp/delegate.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { captureStack } from "../ai-toolkit/stack-capture.js";
import { queueOnMainThread } from "../runtime/queue.js";
// ⚠ EN NAMESPACE, PAS `import { showFires }` : ce sont des `export let` qui BOUGENT a chaque
// affichage du HUD. Un binding nomme fonctionne aussi en ESM, mais l'acces attributaire rend
// la lecture-a-chaque-appel EVIDENTE au lecteur -- et c'est exactement ce dont depend le garde.
import * as hud from "./deployment-hud.js";
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

/** Un ancrage RESOLU, garde avec de quoi l'attacher plus tard. `listener` nul = resolu mais pas
 *  attache : c'est le defaut, l'attache etant un geste explicite (`retreatArmer`). */
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
 *  ⚠ MESURE DU 2026-08-12, ET C'EST UN DEFAUT QUE CE MODULE AVAIT. Apres l'amorce,
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
 *  EXPORTEE depuis #993 : le cycle d'amorce s'en sert comme etat initial ET comme signal de fin
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
 *  2026-08-12 : apres une amorce, le pointeur epingle survit alors que `FindObjectsByType` rend
 *  **0 instance**. Un predicat qui ne testerait que le premier rendrait `true` sur une coquille.
 *
 *  Rend `false` (et non `null`) quand la vivacite n'est pas mesurable : ici l'appelant ATTEND que
 *  la porte s'ouvre, et « je ne sais pas » ne doit jamais faire passer pour ouverte. Le tri-etat
 *  reste publie par `retreatStatus.mainViewVivant`, dont c'est le role. */
export function sortieJoignable(): boolean {
    return mainViewCourante() !== null;
}

/** L'`IdunMainView` VIVANTE, pour les lecteurs qui ont besoin de la bataille RÉELLEMENT à l'écran.
 *
 *  ⚠ EXPOSÉE PLUTÔT QUE RECOPIÉE. `resoudreParEnumeration` porte trois crans qu'une quatrième
 *  copie n'aurait pas : la surcharge à 3 arguments (celle à 2 EXCLUT les inactifs et rendait
 *  0 instance), l'épinglage, et surtout `encoreVivant` — car après une amorce le pointeur épinglé
 *  survit alors que `FindObjectsByType` rend 0 instance, et l'inverse arrive aussi. */
export function vueVivanteCourante(): NativePointer | null {
    return mainViewCourante();
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
    // ⚠ ON RESOUT, ON N'ATTACHE PAS. Depuis le 2026-08-21 l'attache est un geste EXPLICITE
    // (`retreatArmer`) : voir le pave de `armerTout` plus bas pour ce que l'attache permanente
    // coutait.
    ancres.push({ nom: etiquette, ptr: mr.ptr, spec, listener: null });
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
            ancres.push({ nom: nomCtor, ptr: ctor.ptr, spec, listener: null });
            poses.push(nomCtor);
        } else { rates.push(nomCtor); }
    } else {
        rates.push(`classe ${NS_VIEW}.${CLS_VIEW} INTROUVABLE`);
    }

    // Les PREDICATS. On ancre la base `AGameModeSource` ET la concrete `CampaignGameModeSource` :
    // le mode de l'amorce est campagne, mais laquelle des deux porte le corps EXECUTE est une
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

/** ARMER / DESARMER l'observation. Geste EXPLICITE depuis le 2026-08-21.
 *
 *  ⚠ CE QUI A CHANGE, ET POURQUOI. Ces ancres etaient posees au `register`, donc EN PERMANENCE,
 *  et `provoquerRetraite` les DEPOSAIT puis les REPOSAIT autour de son invoke -- onze `detach`
 *  suivis d'onze `attach`, sur le thread principal, PENDANT le demontage de la scene de
 *  bataille. On payait un piege permanent pour une observation rare, et on le desamorcait au
 *  pire moment.
 *
 *  ⚠ ET LES DEUX REGIMES NE SONT PAS EXCLUSIFS -- la premisse qui les separait est REFUTEE.
 *  Elle disait : « Invoquer une methode qu'on ancre, depuis du JS qui tourne sur le main
 *  thread, deadlocke a coup sur (3 gels sur 3) » (en-tete d'`il2cpp/delegate.ts`,
 *  `docs/rl/case-600-gel-du-dispatch-natif.md`). Contre-epreuve du 2026-08-21, MEME nombre
 *  d'essais : douze ancres armees -- dont la methode invoquee elle-meme -- invoke, 3/3 revenus
 *  en 1,64 / 1,44 / 1,20 s, avec 3 handlers JS ayant tire PENDANT chaque appel et la bataille
 *  effectivement quittee. Le trampoline a donc bien ete re-entre, sans geler.
 *
 *  ⚠ CE QUI N'ETAIT PAS UN CONTRE-EXEMPLE, et qu'il ne faut pas relire comme tel : une retraite
 *  pilotee par l'UI traverse ces memes methodes sans rien geler (`case-992`) -- mais la c'est LE
 *  JEU qui appelle, pas notre JS, donc la pile n'est pas re-entrante. C'est la contre-epreuve
 *  ci-dessus qui tranche, pas cette observation.
 *
 *  L'armement ne commande donc plus qu'UNE chose : observe-t-on, ou non.
 *    - DESARME (defaut)  -- rien n'est journalise. Le verdict d'une retraite se prend sur
 *                           l'ETAT (`get_IsBattleActive`, `sandboxProbe.instance`) ;
 *    - ARME              -- chaque passage est journalise, pile comprise. Utile pour LIRE la
 *                           chaine, qu'elle soit declenchee a la main ou par `retreatInvoke`. */
function armerTout(): { poses: string[]; rates: string[] } {
    const poses: string[] = [];
    const rates: string[] = [];
    for (const a of ancres) {
        if (a.listener !== null) { poses.push(a.nom); continue; }
        try { a.listener = Interceptor.attach(a.ptr, a.spec); poses.push(a.nom); }
        catch (e) { rates.push(`${a.nom} : ${(e as Error).message}`); }
    }
    return { poses, rates };
}

function desarmerTout(): number {
    let n = 0;
    for (const a of ancres) {
        if (a.listener === null) continue;
        try { a.listener.detach(); } catch { /* best effort */ }
        a.listener = null;
        n++;
    }
    return n;
}

/** Les ancres ACTUELLEMENT posees. C'est ce que `provoquerRetraite` doit trouver VIDE. */
function ancresArmees(): string[] {
    return ancres.filter((a) => a.listener !== null).map((a) => a.nom);
}

/** Les entrees qu'on s'autorise a INVOQUER, et rien d'autre. Liste blanche explicite :
 *  `ProcessFinishBattle` prend un `playerEndReason` et `HandleBattleSurrender` en prend NEUF --
 *  les invoquer demanderait de FABRIQUER des valeurs, donc de deviner. */
const INVOCABLES = ["OnBattleSurrender", "ContinueSurrender", "ProcessFinishSurrender",
                    // FERMER L'ECRAN DE FIN -- ajoute le 2026-08-21, sur LECTURE du decompile et
                    // non sur son nom. `idun.IdunMainView$$OnBattleEndClose` est un one-liner :
                    //     return EndBattleAndGoToMeta(this);
                    // et `EndBattleAndGoToMeta` masque l'ecran (`idun.ui.Screen$$Hide`), vide les
                    // widgets de deploiement (`UnitDeploymentHud$$ClearWidgets`), sort des
                    // contextes sonores, puis `thor.Loader$$LoadBackToMeta`. C'est exactement le
                    // chemin du bouton de fermeture, sans argument a fabriquer.
                    //
                    // (!)IL NE << RECLAME >> RIEN, et c'est ce qu'il faut savoir : les recompenses
                    // sont deja acquises cote serveur quand `COMPLETE_LOCATION` part (mesure du
                    // 2026-08-21 : 155+155 gold dans le corps de l'evenement). Ce natif rend la
                    // main a l'ecran meta -- sans lui, la bataille suivante ne peut pas entrer,
                    // la scene de bataille restant montee sur l'ecran de victoire.
                    "OnBattleEndClose",
                    // REJOUER LE MEME NOEUD depuis l'ecran de fin -- le bouton << play again >>.
                    // Lu, pas suppose : `idun.IdunMainView$$OnBattleRetryAfterVictory` est un
                    // one-liner
                    //     return OnBattleRetryInternal(this, startBattleSource: 2, saveReplay: 1);
                    // et `OnBattleRetryInternal` journalise une miette, sauve le replay enregistre
                    // (`SaveAndGetRecordedReplay` -- le repertoire du JEU, pas `data/replays/`),
                    // puis delegue au slot 0x102 de la source de mode. Zero argument a fabriquer.
                    //
                    // (!)C'EST LA VOIE COURTE D'UNE BOUCLE DE REJEU : elle repart du noeud sans
                    // repasser par le meta, donc sans re-naviguer ni re-forger. Le jeton, lui, est
                    // consomme comme pour une entree normale.
                    "OnBattleRetryAfterVictory"] as const;

/** PROVOQUER la retraite sans toucher a l'ecran -- LE FOYER, dont `retreatInvoke` n'est que
 *  l'exposition.
 *
 *  EXTRAIT DU RPC AU #993, et l'extraction est le point : le cycle d'amorce a besoin d'appeler
 *  exactement ce corps-la, avec ses trois refus et son depot d'ancrages. Le recopier ailleurs
 *  ferait exister deux chaines de retraite dont une seule serait corrigee -- c'est litteralement
 *  ce qui est arrive a la chaine de CLICS (#332), corrigee dans l'etape 1bis et laissee intacte
 *  dans l'etape 7 pendant deux jours.
 *
 *  Les gardes et leur justification sont dans la docstring du RPC ci-dessous. */
export function provoquerRetraite(body?: {
    methode?: string; confirmer?: boolean; malgreMontage?: boolean;
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
    // ⛔ PAS DE RETRAITE PENDANT QUE L'ECRAN DE DEPLOIEMENT SE REMPLIT.
    //
    // POURQUOI. `lineupRetraiteCommit` est ancre sur `HandleBattleSurrender` : toute retraite
    // enregistre la composition LUE A CET INSTANT dans le magasin du mode. Or
    // `UnitDeploymentHud$$Show` VIDE ses trois dictionnaires en tete (`ClearWidgets`) et ne les
    // remplit qu'a la fin -- entre les deux, le plateau ne porte qu'un SOUS-ENSEMBLE des unites.
    // Une retraite tiree dans cette fenetre commite donc une composition amputee, et le joueur
    // perd une unite sans un seul message. Mesure du 2026-08-28 : 13 tirs enchaines juste apres
    // des montages, dernier commit = 3 unites ecrites dans la cle `mirror3_4` (4 places).
    //
    // LE CRITERE EST UN COMPTEUR D'ORDRE, PAS UN SEUIL SUR LE CONTENU. « moins d'unites que de
    // places » serait FAUX : le joueur peut parfaitement n'en poser qu'une si le mode l'autorise
    // -- un seuil sur le contenu finit toujours par accuser un cas legitime. `showEnters` et
    // `showFires` comptent les ENTREES et les SORTIES de `Show` : leur ecart dit « un remplissage
    // est EN COURS », sans rien interpreter et sans aucune horloge.
    //
    // ⚠ ET LE FOYER DU COMMIT N'EST PAS EN CAUSE : il repond correctement a un signal natif
    // clair. C'est le MOMENT de l'appel qui etait faux. On repare donc l'appelant, pas le
    // composant sain.
    //
    // ⚠ ON NE REFUSE PAS SUR `showFires === 0` (<< aucun ecran jamais affiche >>). Ce serait un
    // faux refus : apres un reinject les compteurs repartent de zero alors qu'une bataille peut
    // TOURNER, et on bloquerait la seule voie de sortie. Seul l'ECART entre entrees et sorties
    // designe sans ambiguite un remplissage en cours.
    const remplissageEnCours = hud.showEnters > hud.showFires;
    if (remplissageEnCours && body?.malgreMontage !== true) {
        return { ok: false, montageEnCours: true,
            showEnters: hud.showEnters, showFires: hud.showFires,
            error: "REFUS : un `UnitDeploymentHud$$Show` est EN COURS (" + hud.showEnters
                + " entree(s) pour " + hud.showFires + " sortie(s)) -- le plateau n'est que "
                + "PARTIELLEMENT rempli. Se retirer maintenant ferait commiter une composition "
                + "AMPUTEE dans le magasin du mode, sans aucun message. Attendre la fin de "
                + "l'affichage, ou `malgreMontage: true` si le montage est REELLEMENT bloque "
                + "(au prix d'un commit possiblement faux)." };
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
              + "apres une amorce, `FindObjectsByType` rend 0 instance alors que le pointeur "
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
    // ⚠ NI DEPOSE, NI REFUS : ON INVOQUE, ANCRES EN PLACE. Ce module a porte successivement
    // les deux parades, et la MESURE les a rendues toutes deux inutiles.
    //
    // La version d'avant le 2026-08-21 DEPOSAIT les douze ancres puis les REPOSAIT autour de
    // l'invoke -- douze `detach` puis douze `attach` sur le thread principal, en plein demontage
    // de scene. Celle du 2026-08-21 les a remplaces par un REFUS quand des ancres sont armees.
    // Les deux servaient la meme premisse, heritee d'`il2cpp/delegate.ts` :
    //   « Invoquer une methode qu'on ancre, depuis du JS qui tourne sur le main thread,
    //     deadlocke a coup sur (3 gels sur 3). »
    //
    // ⚠ CETTE PREMISSE EST REFUTEE POUR CE CHEMIN -- 3 essais sur 3, le 2026-08-21, meme
    // nombre d'essais que la mesure qu'elle contredit. Protocole : douze ancres ARMEES (dont
    // `IdunMainView$$OnBattleSurrender` elle-meme, la methode invoquee), invoke, bataille de
    // campagne en sandbox. Resultat 3/3 : retour en 1,64 / 1,44 / 1,20 s, TROIS handlers JS
    // ayant tire PENDANT l'appel a chaque fois (donc le trampoline a bien ete re-entre),
    // `get_IsBattleActive()` passe a FAUX (l'effet est produit, pas seulement le retour), et
    // le process `Responding`.
    //
    // ⚠ SUR L'ATTRIBUTION, ON NE TRANCHE PAS, ET C'EST DELIBERE. Deux explications restent
    // ouvertes : (a) la premisse datait du ~2026-08-10, soit DIX JOURS avant le passage de
    // `il2cpp_runtime_invoke` en `exceptions: "propagate"` (`95e88699`), et une exception
    // managee CONFISQUEE par Frida gele exactement comme une re-entrance -- meme symptome, un
    // RPC qui ne revient jamais ; (b) le regime de #600 n'est pas celui-ci (dispatch de
    // DELEGATE natif, pas `runtime_invoke`). Ce qui est etabli, c'est que le piege ne se
    // reproduit pas ICI ; `il2cpp/delegate.ts` garde donc son avertissement pour SON regime.
    //
    // ⚠ PORTEE DE LA MESURE : << charger, puis sortir aussitot >>. C'est le geste que ces
    // parades protegeaient, et c'est aussi celui qui avait gele en guerre de guilde. Une
    // bataille avancee de plusieurs tours n'a PAS ete eprouvee.
    const armees = ancresArmees();
    return queueOnMainThread(() => {
        try {
            invokeMethod(mr.info, cible, null);
        } catch (e) {
            return { ok: false, error: "invoke a leve : " + (e as Error).message };
        }
        // ⚠ `ok` NE VEUT DIRE QUE << l'invoke n'a pas leve >>. Il ne dit PAS qu'on est sorti, et
        // il ne peut pas : `OnBattleSurrender` DIFFERE par construction (`PauseSurrender` rend
        // `true`, puis c'est l'UnityEvent du bouton de confirmation qui appelle
        // `ContinueSurrender`). Le verdict se prend sur l'ETAT, apres -- `get_IsBattleActive`
        // ci-dessous, et `sandboxProbe.instance` cote appelant.
        return { ok: true, methode, batailleEncoreActive: enBataille(),
                 // Ce que l'appel a TRAVERSE. Non vide = on a invoque ancres POSEES, et l'appel
                 // est revenu : c'est le fait qui refute le deadlock, et il se re-mesure a
                 // chaque appel au lieu de se citer.
                 ancragesArmesPendant: armees,
                 firesPendantInvoke: journal.length,
                 note: "`ok` = l'invoke n'a pas leve, PAS << sorti >>. `OnBattleSurrender` "
                     + "DIFFERE : la sortie n'aboutit qu'apres `ContinueSurrender`. Verifier "
                     + "`batailleEncoreActive` puis relire `sandboxProbe.instance`." };
    });
}

export function register(ctx: Ctx): void {
    installer();

    /** L'etat de l'interception : tient-on une instance, quels ancrages sont poses.
     *
     *  TRI-ETAT : `ancrages: null` = JAMAIS pose (classes absentes du build) -- a ne pas lire
     *  comme « pose et silencieux ». `ancragesRates` dit LESQUELS ont echoue, pour qu'une
     *  peremption de nom se voie au lieu de se traduire par un journal vide. */
    /** ARMER l'observation. Sans argument : lecture pure.
     *
     *  ⚠ COMPATIBLE AVEC `retreatInvoke` -- l'exclusion qui figurait ici reposait sur un
     *  deadlock refute 3/3 le 2026-08-21 (cf. le pave d'`armerTout`). Armer pendant un invoke
     *  est meme le moyen de LIRE la chaine qu'il declenche. */
    ctx.rpc.retreatArmer = (body?: { armer?: boolean }): unknown => {
        if (body?.armer === undefined) {
            return { ok: true, lecture: true, armees: ancresArmees(), resolus: ancrages,
                     note: "`armer: true` pour journaliser les passages (pile comprise), "
                         + "`armer: false` pour n'en garder aucun. Sans effet sur "
                         + "`retreatInvoke`, qui fonctionne dans les deux regimes." };
        }
        if (body.armer === false) {
            return { ok: true, desarmes: desarmerTout(), armees: ancresArmees() };
        }
        const r = armerTout();
        return { ok: true, armees: r.poses, rates: r.rates,
                 note: "OBSERVATION armee -- `retreatJournal` publiera les passages." };
    };

    ctx.rpc.retreatStatus = (): unknown => ({
        ok: true,
        ancrages, ancragesRates,
        posesMaintenant: ancresArmees(),
        // ⚠ LA PRECONDITION REELLE DE `retreatInvoke`, et elle n'etait PAS publiee -- un appelant
        // ne pouvait donc pas lire la condition qu'on lui oppose, et devait la DEVINER depuis
        // `mainViewVivant`. Les deux sont DISJOINTS : mesure du 2026-08-21, `mainViewVivant: true`
        // (l'objet Unity existe) avec `get_IsBattleActive() == false` (rien a quitter) -- une
        // attente batie sur le premier rendait la main immediatement et l'invoke refusait.
        // `null` = NON MESURE, jamais rabattu sur `false`.
        batailleActive: enBataille(),
        // ⚠ LA SECONDE PRECONDITION, PUBLIEE POUR LA MEME RAISON QUE LA PREMIERE : un appelant
        // ne doit pas avoir a DEVINER la condition qu'on lui oppose. `montageEnCours` vrai =>
        // `retreatInvoke` refusera (un `Show` remplit le plateau), cf. son garde.
        showEnters: hud.showEnters,
        showFires: hud.showFires,
        montageEnCours: hud.showEnters > hud.showFires,
        // Le pointeur epingle, et la resolution COMPLETE (repli `FindObjectsByType` compris) :
        // `mainView` seul vaut `null` tant qu'aucun ancrage n'a tire, meme sur une scene montee.
        mainViewJoignable: mainViewCourante() !== null,
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
                 + "(`lastSource` de l'amorce), que ce module ne detient pas encore. "
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
     *  3. Une BATAILLE ACTIVE est exigee (`get_IsBattleActive`), et c'est la comptabilite du
     *     jeu, pas un proxy d'ecran. `null` = non mesure -> on refuse aussi.
     *
     *  (!)IL N'Y A PLUS DE TROISIEME PARADE CONTRE LE << DEADLOCK DE TRAMPOLINE >>, ni depose
     *  ni refus : refutee 3/3 le 2026-08-21 dans ce regime. Detail au corps de
     *  `provoquerRetraite`, avec la portee de la mesure et ce qui reste ouvert sur sa cause.
     *
     *  ⚠ CE QUE CE RPC NE DIT PAS, ET QU'IL FAUT ALLER CHERCHER. `ok` signifie << l'invoke n'a
     *  pas leve >>, jamais << on est sorti >> : `OnBattleSurrender` DIFFERE par construction
     *  (`PauseSurrender` rend `true`, puis l'UnityEvent du bouton de confirmation appelle
     *  `ContinueSurrender`). Le verdict se prend sur l'ETAT -- `batailleEncoreActive` rendu ici,
     *  puis `sandboxProbe.instance` cote appelant, et le signal de sortie de #390-r2
     *  (`GuiId.PauseMenu` retire) via `uiWindowEvents`.
     *
     *  (!)LE CRAN << METHODE DEJA OBSERVEE >> A ETE RETIRE AVANT CE COMMIT, et la raison tient
     *  toujours : il exigeait qu'une retraite pilotee par l'UI ait fait tirer la methode DANS LA
     *  SESSION COURANTE, ce qui rendait le chemin non autosuffisant a froid (session 77 : le RPC
     *  refusait, le jeu restait bloque en bataille). L'observation qui le motivait a eu lieu --
     *  c'est `case-992`, et la liste blanche `INVOCABLES` EN EST le resultat. */
    ctx.rpc.retreatInvoke = (body?: {
        methode?: string; confirmer?: boolean; malgreMontage?: boolean;
    }): Promise<unknown> | unknown => provoquerRetraite(body);
}
