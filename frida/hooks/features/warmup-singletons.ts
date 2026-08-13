// Le WARMUP : capturer `CampaignGameModeSource` pour armer le builder, SANS UN SEUL CLIC.
//
// TROIS APPELS NATIFS, et c'est tout le cycle (#993, build `rnca9r7q6c`) :
//
//     ViewCommandExecutor$$StartCampaignMatch(campaignId, locationIndex, type, nullable)
//     IdunMainView$$OnBattleSurrender()      -> popup de confirmation (PauseSurrender DIFFERE)
//     IdunMainView$$ContinueSurrender()      -> fin de bataille, retour au meta
//
// ZERO stamina : on se retire AVANT le deploiement, ce que le natif nomme lui-meme
// `hasSurrenderedBeforeDeployment`. Mesure a froid : la capture tombe a **2,1 s** apres l'invoke,
// et `campaignBuilderStatus` rend alors `hasGameConfig` + `hasUnitProgression` + `hasInstance`.
//
// LE PILOTAGE D'UI A ETE RETIRE, IL N'EN RESTE PAS DE REPLI. Ce n'est pas un oubli : un repli
// silencieux aurait rendu la voie native INVERIFIABLE -- le jour ou elle cesserait de porter, le
// warmup resterait VERT en repayant les clics, et personne ne le saurait. Si les trois appels
// echouent, le warmup est ROUGE et son motif est nomme.
//
// ⚠ POURQUOI LE VERDICT « NON CONTOURNABLE » DE #989 ETAIT FAUX, ET EN QUOI IL AVAIT RAISON.
// #989 avait etabli, correctement, que `CampaignGameModeSource` n'a qu'UN SEUL site de creation
// (`ViewCommandExecutor$$StartCampaignMatch`, qui alloue et appelle le ctor INLINE puis enchaine
// sur `thor.Loader$$LoadBattle` sans point de sortie), qu'aucun conteneur DI n'existe dans ce
// binaire (`Zenject` = 0 symbole), et que trois des 17 parametres du ctor DECRIVENT la bataille
// lancee. Conclusion tiree : « creer l'instance et lancer la bataille sont LE MEME GESTE, donc le
// pilotage d'UI n'est pas contournable ». La premisse tient toujours ; la conclusion ne s'en
// deduisait pas. La question posee etait « peut-on RESOUDRE l'instance sans bataille ? » (non),
// alors que la bonne etait « peut-on APPELER la methode que les clics appellent ? » (oui).
//
// CE QUI RESTE DE L'UI ICI, ET CE QUE C'EST : DES SIGNAUX, JAMAIS DES GESTES.
// Le cycle ne clique plus rien -- il n'y a pas un seul appel de clic dans ce fichier. Il LIT
// trois choses, et chacune parce qu'aucune lecture native equivalente n'est etablie :
//   - la POSE de la scene de bataille (trois objets d'UI de deploiement) ;
//   - la presence du popup de confirmation, seul effet observable d'`OnBattleSurrender` (les
//     fires de la chaine ne sont pas mesurables pendant l'invoke : il faut deposer les ancrages
//     sous peine de GEL).
// La troisieme lecture, elle, est NATIVE : `IdunNavigation` vivante = scene meta remontee.
//
// ⚠ ET LE CYCLE NE DIT PAS AU JEU OU SE RETROUVER. Le cran final exigeait le noeud de campagne ;
// mesure du 2026-08-13 : la retraite rend la main sur `Idun_UI_Navigation` (131 boutons), pas sur
// la campagne. On charge une bataille, on en sort, et on verifie seulement qu'un ecran est
// remonte. Le remede qui rappelait `ToCampaign` a ete retire avec ce critere : il ne pouvait
// reparer que « pas sur la campagne », qui n'est plus une panne.

import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";
import { getCampaignGameModeSourcePtr } from "./campaign-builder.js";
// LE SIGNAL, et pas un balayage de boutons : `ui-windows.ts` ancre les cinq points de
// `idun.ui.ScreenVisibilityManager` et pousse chaque transition NOMMEE a ses abonnes.
import { ecouterTransitions, EcouteTransitions } from "./ui-windows.js";
import {
    findClassAnywhere, class_get_methods, method_get_name,
    method_get_param_count, methodEntry, s as cstr, getSystemType, MethodRef,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import {
    runEntreeProgrammatique, EntreeProgDeps, EffetDeSurrender, SortieMethode,
} from "./warmup-programmatique.js";
// Les TROIS appels natifs. On importe les FOYERS, on ne les recopie pas : `invoquerCommande`
// porte la resolution de cible et la coercition d'arguments, `provoquerRetraite` porte les trois
// refus et le depot d'ancrages sans lequel l'invoke GELE.
import { invoquerCommande } from "./view-command.js";
import { enBataille, provoquerRetraite, sortieJoignable } from "./retreat-capture.js";
// ⚠ Un `feature` qui importe un `probe`, et c'est VOULU : ce probe ANCRE `StartCampaignMatch`,
// que nous INVOQUONS. « Ne jamais ancrer la methode qu'on invoque » (3 gels sur 3) ne s'applique
// pas par une phrase mais par un depot d'ancrage -- cet import EST le desarmement.
import { deposerCapteur, reposerCapteur } from "../probes/start-campaign-match-capture.js";
// L'ETAT DU CHARGEUR DE SCENES. Le seul signal qui separe un cycle qui marche d'un cycle qui
// bloque le jeu -- et il ne concerne pas que le warmup : `thor.Loader$$LoadScene` refuse en
// silence pour TOUT changement de scene. D'ou une lib, pas un helper local (`game/loader.ts`).
import { chargementEnCours } from "../game/loader.js";

// --- Ce que le cycle vise dans le jeu ---

const CAMPAIGN_TYPE_INDOMITUS = 0; // Idun.Shared.CampaignType.Standard
const CAMPAIGN_ID_INDOMITUS = "campaign1";

/** LE NOEUD QUE LE CYCLE LANCE -- et d'ou vient ce nombre.
 *
 * ⚠ VALEUR OBSERVEE, PAS CHOISIE, et c'est toute la difference. C'est le `locationIndex` que
 * L'UI ELLE-MEME passait a `ViewCommandExecutor$$StartCampaignMatch` pendant un warmup nominal,
 * relu par le capteur `startCampaignMatchCaptures` (#991, build `rnca9r7q6c`). On REJOUE une
 * valeur mesuree ; on ne compose pas une valeur plausible -- meme discipline que la forme
 * d'argument `{brut, octets}` ci-dessous.
 *
 * ⚠ CE QU'ELLE NE GARANTIT PAS. Un invoke direct court-circuite les deux preconditions que
 * l'appelant UI evaluait (`IsLocationReached`, `HasStaminaToPlayCampaignBattle` -- cf. #991 §3),
 * donc rien ici ne verifie que ce noeud est atteint sur un AUTRE compte. Le jeu, lui, atteint
 * deja `StartCampaignMatch` sans ces gardes par son propre chemin de retour de raid
 * (`ShowCampaignBattlePreviewPopupCommand$$LoadCampaignMatch`) : le regime n'est pas inconnu du
 * binaire. Si le noeud ne charge pas, `prog-capture` rougit et le warmup echoue en le DISANT. */
const PROG_LOCATION_INDEX = 74;

/** `enemyIsAiControlled : System.Nullable<System.Boolean>` -- les DEUX octets OBSERVES.
 *
 * L'UI passe `0x0101`, donc `hasValue` et `value` valent tous deux 1 et les deux lectures
 * possibles CONCORDENT : la disposition de `Nullable<T>` reste NON TRANCHEE, et la forme
 * `{brut, octets}` transporte les octets tels quels plutot que de les recomposer depuis une
 * hypothese sur l'ordre des champs. */
const PROG_ENEMY_AI_BRUT = { brut: "0101", octets: 2 } as const;

/** LE POPUP DE CONFIRMATION DE RETRAITE, tel que `ScreenVisibilityManager` le NOMME.
 *
 * Mesure du 2026-08-13 (journal `uiWindowEvents`, entree + retraite completes) : la classe reelle
 * est `GenericMessagePopup` et son `idun.tracking.GuiId` est `MessagePopup`. Les deux sont
 * confrontes -- le `GuiId` peut rendre `Unknown` sur certains ecrans (mesure : c'est le cas de
 * `BlurredBackgroundScreen`, qui accompagne ce popup), donc s'y fier seul raterait le signal. */
function estLePopupDeConfirmation(t: { classe: string | null; gui: { nom: string | null } }): boolean {
    return t.classe === "GenericMessagePopup" || t.gui.nom === "MessagePopup";
}

// --- Helpers ---

function sleep(ms: number): Promise<void> {
    return new Promise<void>((r) => { setTimeout(r, ms); });
}

/** Attend un SIGNAL : sonde `fn` toutes les `intervalMs` jusqu'a ce qu'il rende non-null, au plus
 * tard apres `timeoutMs`. Les budgets sont des PLAFONDS, jamais des attentes -- le chemin nominal
 * rend la main des que le signal arrive. Il n'y a aucun repos fixe dans ce fichier : rien n'est
 * accorde « pour laisser le temps », tout est attendu jusqu'a etre VU. */
async function waitFor<T>(
    fn: () => T | null,
    timeoutMs: number,
    intervalMs = 100,
): Promise<T | null> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        const v = await queueOnMainThread(fn);
        if (v !== null && v !== undefined) return v;
        await sleep(intervalMs);
    }
    return null;
}

// --- IdunNavigation : le signal « la scene meta est chargee » ---

interface IdunNavRefs {
    findObjectsByType: MethodRef;
    navSystemType: NativePointer;
}
let _navRefs: IdunNavRefs | null = null;

function findMethodByParamCount(
    klass: NativePointer, name: string, paramCount: number,
): MethodRef | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        if (cstr(method_get_name(m) as NativePointer) !== name) continue;
        try {
            if ((method_get_param_count(m) as number) === paramCount) {
                return { info: m, ptr: methodEntry(m) };
            }
        } catch { /* skip */ }
    }
    return null;
}

function ensureNavRefs(): IdunNavRefs {
    if (_navRefs) return _navRefs;
    const navKlass = findClassAnywhere("idun.UI", "IdunNavigation");
    if (!navKlass) throw new Error("IdunNavigation class not found");
    const objK = findClassAnywhere("UnityEngine", "Object");
    if (!objK) throw new Error("UnityEngine.Object not found");
    const findObjectsByType = findMethodByParamCount(objK, "FindObjectsByType", 2);
    if (!findObjectsByType) {
        throw new Error("Object.FindObjectsByType(Type,Mode) not found");
    }
    _navRefs = { findObjectsByType, navSystemType: getSystemType(navKlass) };
    return _navRefs;
}

/** Une `idun.UI.IdunNavigation` vivante = LA SCENE META EST CHARGEE.
 *
 * Signal NATIF, et le seul qui distingue « sorti de bataille » de « ecran noir » : mesure du
 * 2026-08-12, `get_IsBattleActive()` rend `false` dans les deux cas. Dans le run qui a wedge, la
 * reponse ici etait « aucune instance vivante » ; dans celui qui a rendu la main sur un ecran
 * complet, `navInstances: 1`.
 *
 * Passe par la surcharge NON generique `FindObjectsByType(Type, SortMode)` -- la generique
 * `FindFirstObjectByType<T>` leve une exception CPU sous `il2cpp_runtime_invoke`. */
function metaChargee(): boolean {
    try {
        const n = ensureNavRefs();
        const sortMode = Memory.alloc(4).writeS32(0); // SortMode.None
        const arr = invokeMethod(
            n.findObjectsByType.info, null, [n.navSystemType, sortMode]);
        if (arr.isNull()) return false;
        return arr.add(0x18).readS32() > 0;
    } catch {
        return false;
    }
}

// --- Step types for traceable status reporting ---

interface StepLog {
    step: string;
    ok: boolean;
    info?: string;
}

interface WarmupResult {
    ok: boolean;
    skipped?: "already-ready" | "heap-scan";
    capturedAt?: string;
    steps?: StepLog[];
    err?: string;
}

// --- Orchestration ---

/** L'ENTREE, LA CAPTURE ET LA RETRAITE, par les trois appels natifs.
 *
 * Ne porte QUE le cablage : l'ordre des appels, les gardes et les bornes vivent dans le module
 * PUR `warmup-programmatique.ts`, exerce hors Frida par
 * `frida/tools/probe-993-warmup-programmatique.ts`. Ici, rien que des effets. */
async function entreeCaptureRetraite(
    ecoute: EcouteTransitions, steps: StepLog[], opts?: { stopAfterCapture?: boolean },
): Promise<{ captured: NativePointer } | { err: string }> {
    const deps: EntreeProgDeps = {
        enBataille: () => queueOnMainThread(() => enBataille()),

        // `get_IsActive` -- le garde que `StartMatch(checkIfAlreadyRunning)` teste, et qui n'est
        // PAS `get_IsBattleActive`. Les deux sont statiques et se lisent sans instance.
        gardeDejaEnCours: async () => {
            const brut = await invoquerCommande({
                cible: "statique", methode: "get_IsActive", confirmer: true,
            }) as { ok?: boolean; retour?: { decode?: boolean; valeur?: unknown } };
            if (brut?.ok !== true || brut.retour?.decode !== true) return null;
            return brut.retour.valeur === true;
        },

        desarmerGarde: async () => {
            const brut = await invoquerCommande({
                cible: "statique", methode: "SetBattleNotRunning", confirmer: true,
            }) as { ok?: boolean; error?: string };
            return { ok: brut?.ok === true, err: brut?.error };
        },

        lancerBataille: async () => {
            // ⚠ NE JAMAIS ANCRER LA METHODE QU'ON INVOQUE — 3 gels sur 3. Le capteur #991
            // ancre precisement `StartCampaignMatch` ; il ne s'arme pas tout seul, mais un
            // operateur a pu l'armer. On le DEPOSE, et on ne le repose que s'il etait pose.
            const aReposer = await queueOnMainThread(() => deposerCapteur());
            try {
                const res = await invoquerCommande({
                    cible: "executor", methode: "StartCampaignMatch",
                    args: [CAMPAIGN_ID_INDOMITUS, PROG_LOCATION_INDEX,
                           CAMPAIGN_TYPE_INDOMITUS, PROG_ENEMY_AI_BRUT],
                    confirmer: true,
                }) as { ok?: boolean; error?: string };
                return { ok: res?.ok === true, err: res?.error };
            } finally {
                if (aReposer) await queueOnMainThread(() => reposerCapteur());
            }
        },

        attendreCapture: async (ms) => {
            const p = await waitFor(() => getCampaignGameModeSourcePtr(), ms, 300);
            return p === null ? null : p.toString();
        },

        // LE SIGNAL DECISIF, et il est CAUSAL : tant que `thor.Loader` charge, tout changement de
        // scene est refuse EN SILENCE -- donc la retraite terminerait la bataille sans jamais
        // ramener le meta. Aucun repos ici : on attend que l'etape retombe a 0.
        attendreChargementTermine: async (ms) =>
            await waitFor(() => (chargementEnCours() === false ? true : null), ms, 300) !== null,

        attendrePorteDeSortie: async (ms) =>
            await waitFor(() => (sortieJoignable() ? true : null), ms, 300) !== null,

        invoquerSortie: async (m: SortieMethode) => {
            const brut = await provoquerRetraite({ methode: m, confirmer: true });
            const res = brut as { ok?: boolean; error?: string };
            return { ok: res?.ok === true, err: res?.error };
        },

        // TROIS issues, et la premiere est un SIGNAL POUSSE : `montre-fin` sur le popup de
        // confirmation. On ne cherche AUCUN bouton -- « le bouton existe » arrive des
        // `montre-debut`, et agir la laisse le jeu bloque sur le popup (mesure #993).
        // L'autre branche legitime (`PauseSurrender` ne differe pas, la bataille se termine
        // seule) reste sondee sur l'etat NATIF, en course avec le signal.
        attendreEffetDeSurrender: async (ms) => {
            const signal = ecoute.attendre(
                (t) => t.quoi === "montre-fin" && estLePopupDeConfirmation(t), ms)
                .then((t): EffetDeSurrender | null => (t === null ? null : "popup-de-confirmation"));
            const fin = waitFor(() => (enBataille() === false ? true : null), ms, 300)
                .then((v): EffetDeSurrender | null => (v === null ? null : "bataille-terminee"));
            const gagnant = await Promise.race([
                signal, fin,
                // La course ne doit pas se resoudre sur le premier `null` venu : les deux bras
                // partagent le meme plafond, donc on laisse le second repondre.
                Promise.all([signal, fin]).then(([a, b]) => a ?? b),
            ]);
            return gagnant ?? "rien";
        },

        // L'EFFET de `ContinueSurrender` : `cache-debut` sur le meme popup. C'est ce qui separe
        // « la confirmation a porte » de l'etat wedge, ou le popup restait a l'ecran.
        attendreDisparitionDuPopup: async (ms) =>
            await ecoute.attendre(
                (t) => t.quoi === "cache-debut" && estLePopupDeConfirmation(t), ms) !== null,

        attendreFinDeBataille: async (ms) =>
            await waitFor(() => (enBataille() === false ? true : null), ms, 300) !== null,

        attendreMetaChargee: async (ms) =>
            await waitFor(() => (metaChargee() ? true : null), ms, 300) !== null,

        log,
    };

    const res = await runEntreeProgrammatique(
        deps, { stopAfterCapture: opts?.stopAfterCapture === true });
    for (const s of res.steps) steps.push(s);

    if (!res.ok || res.capturedAt === null) {
        log(`[warmup-singletons] FAIL : ${res.reason}`);
        return { err: res.reason };
    }
    return { captured: ptr(res.capturedAt) };
}

async function warmupGameSingletons(
    opts?: { force?: boolean; stopAfterCapture?: boolean },
): Promise<WarmupResult> {
    // 0. Idempotence: if a previous session already captured it, no-op.
    //    Pass { force: true } to skip this short-circuit (useful for
    //    benchmarking or when the cached ptr is suspected stale).
    if (!opts?.force) {
        const existing = await queueOnMainThread(() => getCampaignGameModeSourcePtr());
        if (existing !== null) {
            log(`[warmup-singletons] already ready @ ${existing} — skipping cycle`);
            return {
                ok: true,
                skipped: "already-ready",
                capturedAt: existing.toString(),
            };
        }
    }

    // NOTE: tempting to drop a heap-scan fast path here, but a full heap scan
    // for GameConfigDto can take ~15s on Tacticus PC — UnityFreezeDetector
    // kills the process before we recover. `tryActiveDiscoveryOfSources()`
    // remains available as an *explicit* user-triggered fallback (e.g. from
    // dumpCampaignCatalog allowHeapScan).

    const steps: StepLog[] = [];

    // L'ECOUTE EST OUVERTE AVANT LE PREMIER APPEL, et fermee dans un `finally`. Une transition
    // emise entre l'invoke et l'abonnement serait perdue -- et c'est precisement celle qui
    // compte. Un abonne oublie, lui, ferait lire le `GuiId` a chaque transition pour rien.
    const ecoute = ecouterTransitions();
    let entree: { captured: NativePointer } | { err: string };
    try {
        // ENTREE -> CAPTURE -> RETRAITE, en trois appels natifs. Rien avant, rien apres : aucun
        // popup a fermer (aucun ne bloque un invoke), aucun ecran d'arrivee a exiger -- le
        // module pur verifie que la scene meta est remontee, et c'est tout ce qui est exigible.
        entree = await entreeCaptureRetraite(ecoute, steps, opts);
    } finally {
        ecoute.fermer();
    }
    if ("err" in entree) {
        return { ok: false, err: entree.err, steps };
    }

    log(`[warmup-singletons] cycle complete — CGMS @ ${entree.captured}, builder ready`);
    return { ok: true, capturedAt: entree.captured.toString(), steps };
}

export function register(ctx: Ctx): void {
    ctx.rpc.warmupGameSingletons = (
        opts?: { force?: boolean; stopAfterCapture?: boolean },
    ) => warmupGameSingletons(opts);
    // LE RPC `navToCampaign` A ETE RETIRE (2026-08-07), et son FOYER avec lui (#993).
    //
    // Le levier reparait l'ECRAN, jamais le VERDICT : joue quatre fois de suite le jour ou il a
    // ete mesure, il a bien ramene la campagne a chaque coup -- pendant que `warm-gate`
    // continuait de refuser toute creation de runner, puisque le RPC de warmup rendait toujours
    // `ok:false`. Un levier qui rend l'ecran conforme sans rendre la session utilisable est pire
    // qu'absent.
    //
    // Le foyer lui-meme est parti avec le cran qui exigeait la campagne : le cycle ne dit plus au
    // jeu ou se retrouver, donc « pas sur la campagne » n'est plus une panne a reparer.
}
