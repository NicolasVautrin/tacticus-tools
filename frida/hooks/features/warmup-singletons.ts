// High-level orchestration: warm up CampaignGameModeSource without any
// human in-game click. Drives the existing ui-nav primitives through the
// full chain (campaign node → battle preview → play → ctor capture →
// pause → retreat → confirm) and leaves the game back at the campaign
// screen. Idempotent: if campaign-builder already holds campaignGameModeSourcePtr, no-op.
//
// Intended usage at session start, after auto-inject, to guarantee that
// builder_ready is pushed without needing the user to navigate first.

import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";
import { ensureRefs, enumerateButtons, clickByPath, ButtonRow, UiRefs }
    from "./ui-nav.js";
import {
    getCampaignGameModeSourcePtr, getUnitProgressionPtr, tryActiveDiscoveryOfSources,
} from "./campaign-builder.js";
import {
    findClassAnywhere, findMethod, class_get_methods, method_get_name,
    method_get_param_count, methodEntry, s as cstr, getSystemType,
    MethodRef,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";

// --- Constants describing the in-game button paths we drive through ---

// idun.UI.IdunNavigation.ToCampaign signature (4 params):
//   ToCampaign(bool animated, CampaignType type, string campaignId,
//              Nullable<CampaignAddress> address)
// Calling this directly bypasses the UI tile maze (Home → GameModesScreen →
// Indomitus tile) — one IL2CPP invoke replaces 2-3 fragile clicks. The Indomitus
// campaign is CampaignType.Standard (=0) with campaignId "campaign1".
const CAMPAIGN_TYPE_INDOMITUS = 0; // Idun.Shared.CampaignType.Standard
const CAMPAIGN_ID_INDOMITUS = "campaign1";

const NODE_SUFFIX = "/Idun_CampaignScreenLevelButton(Clone)";

// Generic popup pattern: any active root canvas under SafeCanvas whose name
// matches /Popup\b/ (case-insensitive). Dismissal path: append `/Blocker`
// (transparent fullscreen click-catcher used to "click outside to close").
const POPUP_NAME_REGEX = /Popup/i;
const PLAY_BUTTON_KEY = "/Idun_BattlePreviewPopup(Clone)/" +
    "CanvasGroup/Scale/popup/buttons_container/play_button";
const PAUSE_BUTTON_KEY = "/Idun_UI_Game_HUD(Clone)/PauseButton";
const RETREAT_BUTTON_KEY = "/UI_PauseMenu(Clone)/" +
    "CanvasGroup/Test/Popup/Container - Popup/Buttons/button_retreat";
const RETREAT_CONFIRM_KEY = "/GenericMessagePopup(Clone)/" +
    "CanvasGroup/Scale/Popup/Buttons /Button1";

// Deployment-phase stability signals — all three must be present + interactable
// before it's safe to hit Pause+Retreat. PauseButton mounts as soon as the
// battle HUD canvas is built, well before the scene is actually loaded; using
// it alone as a "ready" signal led to retreating mid-transition and freezing
// the renderer (cf. observed broken-state screenshot).
const DEPLOYMENT_HUD_KEY = "/UnitDeploymentHud(Clone)/";
const START_BATTLE_KEY = "/StartBattleContainer";

// --- Helpers ---

function sleep(ms: number): Promise<void> {
    return new Promise<void>((r) => { setTimeout(r, ms); });
}

/** Poll a queueOnMainThread predicate at `intervalMs` until it returns
 * non-null or `timeoutMs` elapses. Resolves with the value or null.
 * Default interval 100ms — fine-grained enough to track popup animations
 * (~300-500ms) without round-trip waste, since each poll is one main-thread
 * frame (~16ms at 60fps). */
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

/** Poll until a button matching `frag` appears, then CLICK IT in the same
 * main-thread tick — saves one round-trip compared to waitFor + click.
 * Returns the click result + the matched path, or null on timeout. */
async function waitForAndClick(
    r: UiRefs, frag: string, timeoutMs: number, intervalMs = 100,
): Promise<{ ok: boolean; path: string; err?: string } | null> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        const result = await queueOnMainThread(() => {
            const btn = findButtonByContains(r, frag);
            if (!btn) return null;
            const click = clickByPath(r, btn.path);
            return { ok: click.ok, path: btn.path, err: click.err };
        });
        if (result !== null) return result;
        await sleep(intervalMs);
    }
    return null;
}

/** Find a button whose path ends with `suffix`, on the next main-thread tick.
 * Only considers active & interactable buttons. */
function findButtonBySuffix(r: UiRefs, suffix: string): ButtonRow | null {
    const rows = enumerateButtons(r, false);
    return rows.find((b) => b.path.endsWith(suffix)) ?? null;
}

/** Find a button whose path *contains* `frag` (anywhere). Active+interactable. */
function findButtonByContains(r: UiRefs, frag: string): ButtonRow | null {
    const rows = enumerateButtons(r, false);
    return rows.find((b) => b.path.indexOf(frag) >= 0) ?? null;
}

/** Return `true` when every fragment in `frags` is matched by at least one
 * active+interactable button. Used to detect composite stability signals
 * like "deployment phase is fully ready" (HUD + StartBattle + Pause all up). */
function allFragmentsPresent(r: UiRefs, frags: string[]): true | null {
    const rows = enumerateButtons(r, false);
    for (const f of frags) {
        if (!rows.some((b) => b.path.indexOf(f) >= 0)) return null;
    }
    return true;
}

// --- IdunNavigation direct invoke (bypasses UI tile clicks) ---

interface IdunNavRefs {
    navKlass: NativePointer;
    findObjectsByType: MethodRef;
    toCampaign: MethodRef;
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
    const findObjectsByType = findMethodByParamCount(
        objK, "FindObjectsByType", 2);
    if (!findObjectsByType) {
        throw new Error("Object.FindObjectsByType(Type,Mode) not found");
    }
    const toCampaign = findMethodByParamCount(navKlass, "ToCampaign", 4);
    if (!toCampaign) {
        throw new Error("IdunNavigation.ToCampaign(4 params) not found");
    }
    _navRefs = {
        navKlass, findObjectsByType, toCampaign,
        navSystemType: getSystemType(navKlass),
    };
    return _navRefs;
}

/** Locate the live IdunNavigation singleton in the scene. Uses the non-generic
 * Object.FindObjectsByType(Type, SortMode) — the generic FindFirstObjectByType<T>
 * cannot be invoked via il2cpp_runtime_invoke (raises a CPU exception). */
function findLiveIdunNavigation(n: IdunNavRefs): NativePointer | null {
    const sortMode = Memory.alloc(4).writeS32(0); // SortMode.None
    const arr = invokeMethod(
        n.findObjectsByType.info, null, [n.navSystemType, sortMode]);
    if (arr.isNull()) return null;
    const len = arr.add(0x18).readS32();
    if (len <= 0) return null;
    const inst = arr.add(0x20).readPointer();
    return inst.isNull() ? null : inst;
}

/** Invoke IdunNavigation.ToCampaign(animated, type, campaignId, nullable-address).
 * Returns the instance pointer used, or throws on managed exception. */
function invokeToCampaign(
    n: IdunNavRefs, navInstance: NativePointer,
    animated: boolean, campaignType: number, campaignId: string,
): void {
    const argAnimated = Memory.alloc(1).writeU8(animated ? 1 : 0);
    const argType = Memory.alloc(4).writeS32(campaignType);
    const argId = createManagedString(campaignId);
    // Nullable<CampaignAddress>: zero-filled buffer ⇒ HasValue=false (null).
    // CampaignAddress is 0x28 bytes; 64-byte buffer covers any padding/layout.
    const argNullable = Memory.alloc(64);
    for (let i = 0; i < 64; i += 4) argNullable.add(i).writeU32(0);
    invokeMethod(n.toCampaign.info, navInstance,
        [argAnimated, argType, argId, argNullable]);
}

/** Walk active+interactable buttons, build the set of SafeCanvas roots
 * whose name matches the popup pattern. Returns one Blocker path per popup
 * (deduplicated by root) so the caller can click each in turn to dismiss. */
function findPopupBlockerPaths(r: UiRefs): string[] {
    const rows = enumerateButtons(r, false);
    const blockersByRoot: Record<string, string> = {};
    for (const b of rows) {
        // Path layout: UI_Canvas_*/Canvas/Viewport/SafeCanvas/<root>/...
        const seg = b.path.split("/");
        if (seg.length < 5) continue;
        const root = seg[4];
        if (!POPUP_NAME_REGEX.test(root)) continue;
        if (b.path.endsWith("/Blocker")) {
            blockersByRoot[root] = b.path;
        }
    }
    return Object.values(blockersByRoot);
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
    // kills the process before we recover. The 8ms "cache hit" measured
    // earlier was already-resolved ptrs (auto-boot or earlier session), not
    // a cold scan. UI nav is slower (~30s) but safe.
    // `tryActiveDiscoveryOfSources()` remains available as an *explicit*
    // user-triggered fallback (e.g. from dumpCampaignCatalog allowHeapScan).

    const steps: StepLog[] = [];
    const fail = (step: string, err: string): WarmupResult => {
        steps.push({ step, ok: false, info: err });
        log(`[warmup-singletons] FAIL at ${step}: ${err}`);
        return { ok: false, err: `${step}: ${err}`, steps };
    };

    const r = ensureRefs();

    // 1. Dismiss any blocking modal popup before doing anything else.
    //    Examples observed: Idun_UI_LiveEventInterstitialPopup (random ad),
    //    GenericMessagePopup (system message). They disable everything behind
    //    them so we can't find/click anything until they're gone.
    //    Loop up to 3 times in case dismissing one reveals another.
    let dismissed: string[] = [];
    for (let i = 0; i < 3; i++) {
        const blockers = await queueOnMainThread(
            () => findPopupBlockerPaths(r));
        if (blockers.length === 0) break;
        for (const path of blockers) {
            const c = await queueOnMainThread(() => clickByPath(r, path));
            if (c.ok) dismissed.push(path.split("/SafeCanvas/")[1]?.split("/")[0] ?? path);
        }
        // Give the popup animations time to tear down.
        await sleep(200);
    }
    steps.push({
        step: "dismiss-popups", ok: true,
        info: dismissed.length === 0 ? "none" : dismissed.join(","),
    });

    // 2. Navigate to the Indomitus campaign screen. If we're already there,
    //    no-op. Otherwise call IdunNavigation.ToCampaign() directly via IL2CPP
    //    — the same method the game uses internally for its own nav. Replaces
    //    the previous multi-hop UI tile chase (BattleButton → GameModesScreen
    //    → Indomitus tile), which was fragile because FindObjectsByType doesn't
    //    guarantee ordering and the "first" /RegularContainer/Button could land
    //    on a sibling campaign that crashes on click without proper context.
    // Invoke IdunNavigation.ToCampaign UNCONDITIONALLY to normalize the view to
    // the Indomitus campaign OVERVIEW. Even when level nodes are already present
    // in the hierarchy, the screen can be left zoomed into a sub-part (e.g.
    // CampaignScreen_Part_1_5) whose first-found node isn't launchable, so the
    // BattlePreview popup never mounts and click-play fails. The old code
    // short-circuited ToCampaign on "already-on-campaign", trusting that stale
    // zoomed view. ToCampaign is the game's own idempotent nav ("if already
    // there, no-op" — see below), so resetting is safe and re-centers on a
    // launchable node. Best-effort: if the nav instance can't be resolved but
    // nodes are already present, fall back to the current view (no regression).
    const onCampaignAlready = await queueOnMainThread(
        () => findButtonBySuffix(r, NODE_SUFFIX) !== null);

    const navResult = await queueOnMainThread(() => {
        try {
            const n = ensureNavRefs();
            const inst = findLiveIdunNavigation(n);
            if (inst === null) {
                return { ok: false, err: "no live IdunNavigation instance" };
            }
            invokeToCampaign(n, inst, true,
                CAMPAIGN_TYPE_INDOMITUS, CAMPAIGN_ID_INDOMITUS);
            return { ok: true, navInstance: inst.toString() };
        } catch (e) {
            return { ok: false, err: (e as Error).message };
        }
    });
    if (!navResult.ok) {
        if (!onCampaignAlready) {
            return fail("to-campaign", navResult.err ?? "ToCampaign failed");
        }
        // Couldn't reset the view, but nodes are present -> proceed with the
        // current campaign screen (exactly the pre-fix behaviour, no regression).
        steps.push({
            step: "to-campaign", ok: true,
            info: `no-reset (${navResult.err}); nodes-already-present`,
        });
    } else {
        // Wait for the campaign screen with its level nodes to (re)mount after
        // the reset.
        const ready = await waitFor(
            () => findButtonBySuffix(r, NODE_SUFFIX), 5000);
        if (ready === null) {
            return fail("to-campaign",
                "no level nodes appeared 5s after ToCampaign invoke");
        }
        steps.push({
            step: "to-campaign", ok: true,
            info: `reset-via-idun-nav (@${navResult.navInstance})`,
        });
    }

    // 3. Find + click a level node (one main-thread tick).
    const nodeClick = await queueOnMainThread(() => {
        const node = findButtonBySuffix(r, NODE_SUFFIX);
        if (!node) return null;
        const click = clickByPath(r, node.path);
        return { path: node.path, ok: click.ok, err: click.err };
    });
    if (nodeClick === null) {
        return fail("click-node", "no level node available after to-campaign");
    }
    if (!nodeClick.ok) return fail("click-node", nodeClick.err ?? "?");
    steps.push({ step: "click-node", ok: true, info: nodeClick.path });

    // 2. Wait for the popup to appear AND click play_button in one go.
    const playClick = await waitForAndClick(r, PLAY_BUTTON_KEY, 5000);
    if (playClick === null) {
        return fail("click-play",
            "BattlePreview popup did not show within 5s");
    }
    if (!playClick.ok) return fail("click-play", playClick.err ?? "?");
    steps.push({ step: "click-play", ok: true, info: playClick.path });

    // 5. Wait for the ctor hook to capture CampaignGameModeSource.
    //    Battle loading can be slow on cold boot — up to 20s.
    const captured = await waitFor(() => getCampaignGameModeSourcePtr(), 20000, 300);
    if (captured === null) {
        return fail("wait-ctor",
            "CampaignGameModeSource..ctor did not fire within 20s");
    }
    steps.push({
        step: "wait-ctor", ok: true, info: captured.toString(),
    });
    log(`[warmup-singletons] CGMS captured @ ${captured}`);

    // 5bis. `stopAfterCapture` — SORTIE ICI, avant toute transition d'ecran.
    //
    // Le but du warmup est ATTEINT a cette ligne : la capture est faite, le builder est arme,
    // les runners isoles sont utilisables. Tout ce qui suit (pause -> retreat -> confirm ->
    // retour campagne) n'est que du MENAGE d'ecran — et c'est precisement la ou le cycle
    // wedge : `wait-back-to-campaign` echoue (campagne qui ne remonte pas en 45 s), l'UI
    // reste morte, et `navToCampaign` ne rattrape pas (« no live IdunNavigation instance »).
    // Observe le 2026-07-22 (3 fois, la game mourait ensuite) et le 2026-07-25 (la game
    // survit depuis `runtime/freeze-detector.ts`, mais l'UI reste figee).
    //
    // En sortant ici on ne NEGOCIE AUCUNE transition, donc il n'y a rien a wedger. Le prix :
    // le jeu reste sur l'ecran de bataille de warmup, en phase de deploiement. Acceptable —
    // les runners isoles ne consomment pas l'ecran campagne (cf. `runner.md`).
    //
    // C'EST LE DEFAUT depuis le 2026-07-25. Mesure live (session 77, build gqfc5mff6c) :
    //     cycle complet    61,2 s  ok:false (9/10)  UI figee, relance du jeu obligatoire
    //     sortie ici        3,9 s  ok:true          jeu utilisable
    // Validation FONCTIONNELLE et pas seulement « etape verte » : `dumpCampaignCatalog` rend
    // les memes 1 230 459 octets qu'apres un cycle complet — le builder EST arme.
    // L'appelant qui veut vraiment l'ecran campagne rendu propre passe explicitement
    // `stopAfterCapture: false` ; il herite alors du risque de wedge decrit ci-dessus.
    if (opts?.stopAfterCapture !== false) {
        steps.push({
            step: "stop-after-capture", ok: true,
            info: "menage d'ecran saute (pause/retreat/retour campagne) — aucune transition",
        });
        log("[warmup-singletons] stopAfterCapture — cycle arrete apres la capture, "
            + "le jeu reste sur l'ecran de bataille");
        return { ok: true, capturedAt: captured.toString(), steps };
    }

    // 6. Wait for the deployment phase to be FULLY stable before pausing.
    //    PauseButton alone mounts way too early (with the HUD canvas, while
    //    the scene is still loading). Retreating then leaves Unity in a
    //    half-rendered state. The reliable signal is the combination of:
    //      - UnitDeploymentHud(Clone) present (deploy UI mounted)
    //      - StartBattleContainer present (only interactable when deploy is ready)
    //      - PauseButton present (HUD ready)
    //    All three together + a small grace period for animations.
    const stable = await waitFor(
        () => allFragmentsPresent(r, [
            DEPLOYMENT_HUD_KEY, START_BATTLE_KEY, PAUSE_BUTTON_KEY,
        ]),
        30000,
        300,
    );
    if (stable === null) {
        return fail("wait-deployment-stable",
            "deployment phase did not stabilize within 30s — aborting " +
            "without retreat to avoid corrupting the UI state");
    }
    steps.push({ step: "wait-deployment-stable", ok: true });
    // Grace period: let camera-fly-in / unit-pop-in animations finish.
    // 500ms is enough — StartBattleContainer interactable already implies
    // the major animations are done.
    await sleep(500);

    // 7. Pause → retreat → confirm. Each step polls until the next button
    //    appears, then clicks it in the same main-thread tick.
    const pauseClick = await waitForAndClick(r, PAUSE_BUTTON_KEY, 3000);
    if (pauseClick === null || !pauseClick.ok) {
        return fail("click-pause", pauseClick?.err ?? "pause button not found");
    }
    steps.push({ step: "click-pause", ok: true });

    const retreatClick = await waitForAndClick(r, RETREAT_BUTTON_KEY, 3000);
    if (retreatClick === null || !retreatClick.ok) {
        return fail("click-retreat",
            retreatClick?.err ?? "retreat button not found");
    }
    steps.push({ step: "click-retreat", ok: true });

    const confirmClick = await waitForAndClick(r, RETREAT_CONFIRM_KEY, 3000);
    if (confirmClick === null || !confirmClick.ok) {
        return fail("click-confirm",
            confirmClick?.err ?? "confirm button not found");
    }
    steps.push({ step: "click-confirm", ok: true });

    // 8. Verify the post-retreat transition actually COMPLETES (battle scene
    //    unloaded, campaign screen re-mounted with its level nodes). Without
    //    this gate the cycle reported ok right after click-confirm; a hung
    //    transition (frozen screen, ZERO clickable buttons anywhere) went
    //    unnoticed — observed 2026-07-20: engine kept pumping (RPCs fine) but
    //    the UI was dead until a game relaunch. 45s: scene unload+reload can
    //    exceed 30s on a busy frame budget.
    const backHome = await waitFor(
        () => findButtonBySuffix(r, NODE_SUFFIX), 45000, 500);
    if (backHome === null) {
        // The ctor WAS captured (builder armed) — report the wedge precisely
        // instead of pretending the cycle is healthy. `navToCampaign` (RPC
        // below) is the recovery lever to try before relaunching the game.
        steps.push({ step: "wait-back-to-campaign", ok: false });
        log("[warmup-singletons] WEDGE: campaign screen did not remount 45s "
            + "after retreat-confirm — try rpc navToCampaign");
        return {
            ok: false, capturedAt: captured.toString(), steps,
            err: "wait-back-to-campaign: campaign screen did not remount "
                + "within 45s after retreat-confirm — UI likely stuck in "
                + "transition; try rpc navToCampaign, else relaunch the game",
        };
    }
    steps.push({ step: "wait-back-to-campaign", ok: true });

    log("[warmup-singletons] cycle complete — builder ready, game retreated");
    return { ok: true, capturedAt: captured.toString(), steps };
}

export function register(ctx: Ctx): void {
    ctx.rpc.warmupGameSingletons = (
        opts?: { force?: boolean; stopAfterCapture?: boolean },
    ) => warmupGameSingletons(opts);
    // Recovery lever: force the game's OWN navigation back to the campaign
    // screen (same IL2CPP invoke the warmup nav uses, animated=false). Unsticks
    // a UI wedged in the post-retreat transition without relaunching the game.
    // No battle-state mutation; safe anytime.
    ctx.rpc.navToCampaign = () => queueOnMainThread(() => {
        try {
            const n = ensureNavRefs();
            const inst = findLiveIdunNavigation(n);
            if (inst === null) {
                return { ok: false, err: "no live IdunNavigation instance" };
            }
            invokeToCampaign(n, inst, false,
                CAMPAIGN_TYPE_INDOMITUS, CAMPAIGN_ID_INDOMITUS);
            return { ok: true, navInstance: inst.toString() };
        } catch (e) {
            return { ok: false, err: (e as Error).message };
        }
    });
}
