// Zero-click auto-boot sequence: automatically extracts GameConfigDto and
// UnitProgression pointers directly from the IdunNavigation instance at boot.
//
// Relies on a passive hook on IdunNavigation.Init or ShowScreenAndHideOthers
// to capture the navigation instance immediately at boot.
// Fallback: targeted fast active discovery for IdunNavigation if passive hooks haven't
// fired after 6 seconds.

import {
    findClassAnywhere, findMethod, findClass, getFieldOffset,
    class_get_fields, field_get_name, field_get_offset,
    class_get_methods, method_get_name, method_get_param_count,
    s, getSystemType, methodEntry, findCtorByParamCount
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
// Repli d'instance par appel MOTEUR (`UnityEngine.Object.FindObjectsByType`) — pas un scan
// de tas : cf. `autoBootExtraire`.
import { premiereInstance } from "./view-command.js";
// L'`IdunUniverse` ne vit pas sur `IdunNavigation` : elle est posee par repli statique sur
// `thor.Globals.currentIdunUniverse`. Cf. le bloc dans `autoBootExtraire`.
import { getCapturedUniverse, tryGlobalsCapture } from "./unit-visual-resolve.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";
import {
    getCampaignGameModeSourcePtr,
    getLastGameConfig,
    tryActiveDiscoveryOfSources,
    setLastGameConfig,
    setUnitProgressionPtr
} from "./campaign-builder.js";

let lastNavigationInstance: NativePointer | null = null;
let lastLevelMapWidgetContainerInstance: NativePointer | null = null;
let autoBootExecuted = false;

/** La navigation automatique vers la campagne. DESACTIVEE par defaut — cf. le bloc de
 *  commentaire dans `extractDependenciesAndNavigate`. L'extraction de pointeurs, elle,
 *  reste toujours active : elle est passive et ne deplace rien. */
let navigationAutoActive = false;

export async function extractDependenciesAndNavigate(navInstance: NativePointer): Promise<void> {
    if (autoBootExecuted) return;

    log(`[auto-boot] Starting direct dependency extraction from IdunNavigation @ ${navInstance}...`);

    try {
        // Resolve field offsets by NAME via the IL2CPP API — IdunNavigation's
        // layout shifts between Unity versions (_unitProgression moved
        // 0x1F0→0x1D8, _gameConfig 0x240→0x228 between builds kqkbjqfb6c and
        // gqfc5mff6c). A hardcoded offset reads the wrong field on the next
        // game update and sets a non-null GARBAGE pointer, which silently
        // blocks the heap-scan / GetUnit-hook fallbacks (they only run when
        // unitProgressionPtr is still null) — symptom downstream:
        // "GetIndicesOfAppliedUpgrades(2) not found". cf. CLAUDE.md
        // "résolution runtime, pas de RVA hardcodées".
        const navClass = navInstance.readPointer();
        const upOff = getFieldOffset(navClass, "_unitProgression");
        const gcOff = getFieldOffset(navClass, "_gameConfig");
        const unitProgressionPtr = upOff >= 0
            ? navInstance.add(upOff).readPointer() : ptr(0);
        const gameConfigPtr = gcOff >= 0
            ? navInstance.add(gcOff).readPointer() : ptr(0);

        log(`[auto-boot] Extracted pointers (_unitProgression@0x${upOff.toString(16)}, _gameConfig@0x${gcOff.toString(16)}): _gameConfig=${gameConfigPtr}, _unitProgression=${unitProgressionPtr}`);

        if (!gameConfigPtr.isNull()) {
            setLastGameConfig(gameConfigPtr);
        } else {
            log("[auto-boot] Warning: extracted _gameConfig pointer is null!");
        }

        if (!unitProgressionPtr.isNull()) {
            setUnitProgressionPtr(unitProgressionPtr);
        } else {
            log("[auto-boot] Warning: extracted _unitProgression pointer is null!");
        }

        // Try early active discovery. If captured both, exit early.
        const discovered = await tryActiveDiscoveryOfSources();
        if (discovered && getCampaignGameModeSourcePtr() !== null) {
            log("[auto-boot] SUCCESS! CampaignGameModeSource and GameConfigDto already captured naturally, skipping auto-navigation.");
            autoBootExecuted = true;
            return;
        }

        // ⚠ LA NAVIGATION AUTOMATIQUE EST DESACTIVEE PAR DEFAUT (2026-08-10).
        //
        // L'EXTRACTION ci-dessus reste faite a chaque boot : elle est passive, elle ne
        // deplace rien, et ses pointeurs servent au campaign-builder. Ce qui suit, en
        // revanche, PILOTE L'UI (`ToCampaign` + taps) -- et le faisait a CHAQUE injection.
        //
        // Mesure du 2026-08-10 : quatre reinjects successifs pendant un travail sur
        // l'ecran Operations ont ramene le jeu sur la campagne Indomitus a chaque fois.
        // `{ amorce: false }` n'y changeait rien -- ce n'est pas l'amorce qui navigue,
        // c'est ce module, par un chemin independant. Le symptome se lit comme un caprice
        // du jeu alors qu'il vient de nous.
        //
        // Le declenchement reste disponible A LA DEMANDE : RPC `triggerAutoBoot`, ou
        // `setAutoBootNavigation({ actif: true })`. On ne supprime pas la capacite, on lui
        // retire son automatisme.
        if (!navigationAutoActive) {
            log("[auto-boot] navigation auto DESACTIVEE (defaut) — pointeurs extraits, UI "
                + "NON deplacee. `triggerAutoBoot` pour la lancer explicitement.");
            return;
        }

        // Otherwise, run programmatic navigation sequence
        autoBootExecuted = true;
        log(`[auto-boot] CampaignGameModeSource not yet instantiated. Starting auto-navigation sequence...`);

        const navKlass = findClassAnywhere("idun.UI", "IdunNavigation");
        if (!navKlass) {
            log("[auto-boot] IdunNavigation class not found!");
            autoBootExecuted = false;
            return;
        }

        const showScreen = findMethod(navKlass, "ShowScreenAndHideOthers");
        if (!showScreen || showScreen.ptr.isNull()) {
            log("[auto-boot] ShowScreenAndHideOthers method not found!");
            autoBootExecuted = false;
            return;
        }

        const toCampaign = findMethod(navKlass, "ToCampaign");
        if (!toCampaign || toCampaign.ptr.isNull()) {
            log("[auto-boot] ToCampaign method not found!");
            autoBootExecuted = false;
            return;
        }

        const toHome = findMethod(navKlass, "ToHome");
        if (!toHome || toHome.ptr.isNull()) {
            log("[auto-boot] ToHome method not found!");
            autoBootExecuted = false;
            return;
        }

        const addressKlass = findClassAnywhere("Idun.Shared", "CampaignAddress");
        if (!addressKlass) {
            log("[auto-boot] CampaignAddress class not found!");
            autoBootExecuted = false;
            return;
        }

        const addressCtor = findCtorByParamCount(addressKlass, 3);
        if (!addressCtor || addressCtor.ptr.isNull()) {
            log("[auto-boot] CampaignAddress 3-argument constructor not found!");
            autoBootExecuted = false;
            return;
        }

        void queueOnMainThread(() => {
            log("[auto-boot] Step 1: Navigating to Campaign & scrolling to Level 6 via ToCampaign...");
            const animVal = Memory.alloc(1).writeU8(1); // animated = true
            const campaignTypeVal = Memory.alloc(4).writeS32(0); // CampaignType.Standard = 0
            const campaignIdVal = createManagedString("campaign1"); // Indomitus

            try {
                // Construct CampaignAddress for Indomitus level 6 (location index 5)
                log("[auto-boot] Constructing CampaignAddress for Indomitus Level 6 (locationIndex=5)...");
                const addressBuffer = Memory.alloc(40);
                const locationIndexVal = Memory.alloc(4).writeS32(5); // Node 6 = Index 5
                
                invokeMethod(addressCtor.info, addressBuffer, [locationIndexVal, campaignTypeVal, campaignIdVal]);
                log("[auto-boot] CampaignAddress constructed successfully!");

                // Wrap in Nullable<CampaignAddress>
                const nullableAddressVal = Memory.alloc(48);
                Memory.copy(nullableAddressVal, addressBuffer, 40);
                nullableAddressVal.add(40).writeU8(1); // hasValue = true

                invokeMethod(toCampaign.info, navInstance, [animVal, campaignTypeVal, campaignIdVal, nullableAddressVal]);
                log("[auto-boot] Step 1 complete (ToCampaign invoked). Initiating wait-and-tap sequence for Level 6...");

                // Start checking for container loading and buttons ready
                let attempts = 0;
                const maxAttempts = 60; // 60 * 500ms = 30 seconds max wait
                const checkInterval = setInterval(() => {
                    attempts++;
                    if (attempts > maxAttempts) {
                        log("[auto-boot] Tap sequence TIMEOUT: Level buttons were not loaded in time.");
                        clearInterval(checkInterval);
                        return;
                    }

                    void queueOnMainThread(() => {
                        try {
                            let container = lastLevelMapWidgetContainerInstance;
                            if (!container || container.isNull()) {
                                container = discoverActiveContainerInstance();
                                if (container && !container.isNull()) {
                                    lastLevelMapWidgetContainerInstance = container;
                                }
                            }

                            if (!container || container.isNull()) {
                                return; // LevelMapWidgetContainer not yet loaded
                            }

                            // Read LevelMapWidget _levelMapWidget pointer at offset 0xA8
                            const levelMapWidget = container.add(0xA8).readPointer();
                            if (levelMapWidget.isNull()) return;

                            // Read LevelMapPartWidget _partInstance pointer at offset 0xC0
                            const partInstance = levelMapWidget.add(0xC0).readPointer();
                            if (partInstance.isNull()) return;

                            // Dynamically resolve LevelMapPartWidget class and methods
                            const partKlass = findClassAnywhere("idun.UI.Screens.CampaignScreen", "LevelMapPartWidget");
                            if (!partKlass) return;

                            const getButtonsLoaded = findMethod(partKlass, "get_ButtonsLoaded");
                            const getButton = findMethod(partKlass, "GetButton");
                            if (!getButtonsLoaded || getButtonsLoaded.ptr.isNull() || !getButton || getButton.ptr.isNull()) {
                                return;
                            }

                            const buttonsLoaded = invokeMethod(getButtonsLoaded.info, partInstance, null).toInt32() === 1;
                            if (!buttonsLoaded) {
                                return; // Standby, not loaded yet
                            }

                            // Buttons are loaded! Stop the interval.
                            clearInterval(checkInterval);
                            log("[auto-boot] LevelMapPartWidget buttons loaded! Retrieving level button at index 5...");

                            const buttonIndexVal = Memory.alloc(4).writeS32(5); // Node 6 = index 5
                            const buttonPtr = invokeMethod(getButton.info, partInstance, [buttonIndexVal]);
                            if (buttonPtr.isNull()) {
                                log("[auto-boot] Error: LevelButton pointer at index 5 is null!");
                                return;
                            }

                            log(`[auto-boot] LevelButton retrieved @ ${buttonPtr}. Resolving CampaignScreen...`);

                            const campaignMenuPtr = navInstance.add(0x100).readPointer();
                            if (campaignMenuPtr.isNull()) {
                                log("[auto-boot] CampaignMenu backing field is null!");
                                return;
                            }
                            const campaignScreenPtr = campaignMenuPtr.add(0x10).readPointer();
                            if (campaignScreenPtr.isNull()) {
                                log("[auto-boot] IdunCampaignScreen screen pointer is null!");
                                return;
                            }

                            const campaignScreenKlass = findClassAnywhere("idun.UI.Screens.CampaignScreen", "IdunCampaignScreen");
                            if (!campaignScreenKlass) {
                                log("[auto-boot] IdunCampaignScreen class not found!");
                                return;
                            }
                            const handleLevelTapped = findMethod(campaignScreenKlass, "HandleLevelTapped");
                            if (!handleLevelTapped || handleLevelTapped.ptr.isNull()) {
                                log("[auto-boot] HandleLevelTapped method not found!");
                                return;
                            }

                            log(`[auto-boot] Invoking HandleLevelTapped on CampaignScreen @ ${campaignScreenPtr}...`);
                            const campaignIdVal = createManagedString("campaign1");
                            const locationIndexVal = Memory.alloc(4).writeS32(5);

                            invokeMethod(handleLevelTapped.info, campaignScreenPtr, [buttonPtr, campaignIdVal, locationIndexVal]);
                            log("[auto-boot] SUCCESS! HandleLevelTapped invoked programmatically. Pre-battle dialog should be open.");

                            // Trigger active discovery to capture the newly instantiated CampaignGameModeSource
                            setTimeout(async () => {
                                await tryActiveDiscoveryOfSources();
                                const updatedSource = getCampaignGameModeSourcePtr();
                                if (updatedSource) {
                                    log(`[auto-boot] CampaignGameModeSource successfully captured @ ${updatedSource}!`);
                                } else {
                                    log("[auto-boot] Warning: CampaignGameModeSource was not captured. Running active discovery fallback...");
                                    await tryActiveDiscoveryOfSources();
                                }
                            }, 1500);
                        } catch (errInner) {
                            log(`[auto-boot] Error inside wait loop: ${(errInner as Error).message}`);
                        }
                    });
                }, 500);
            } catch (errShow) {
                log(`[auto-boot] Error during ToCampaign transition: ${(errShow as Error).message}`);
                autoBootExecuted = false; // allow retry
            }
        });
    } catch (e) {
        log(`[auto-boot] Error during direct dependency extraction: ${(e as Error).message}`);
        autoBootExecuted = false;
    }
}

function discoverActiveInstance(): NativePointer | null {
    try {
        const uoKlass = findClass("UnityEngine.CoreModule.dll", "UnityEngine", "Object");
        if (!uoKlass) {
            log("[auto-boot] UnityEngine.Object class not found!");
            return null;
        }

        const navKlass = findClassAnywhere("idun.UI", "IdunNavigation");
        if (!navKlass) {
            log("[auto-boot] IdunNavigation class not found!");
            return null;
        }

        const navType = getSystemType(navKlass);
        if (navType.isNull()) {
            log("[auto-boot] IdunNavigation System.Type is null!");
            return null;
        }

        // Search for FindFirstObjectByType or FindObjectOfType overload taking 1 parameter
        let targetMi: NativePointer = ptr(0);
        
        // 1. Try FindFirstObjectByType first
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(uoKlass, it) as NativePointer).isNull()) {
            const mName = s(method_get_name(m) as NativePointer);
            if (mName === "FindFirstObjectByType" && (method_get_param_count(m) as number) === 1) {
                try {
                    // Test if this is the correct overload by dry-running it
                    invokeMethod(m, null, [navType]);
                    targetMi = m;
                    break;
                } catch {
                    // Try next overload
                }
            }
        }

        // 2. Fallback to FindObjectOfType
        if (targetMi.isNull()) {
            it.writePointer(ptr(0));
            while (!(m = class_get_methods(uoKlass, it) as NativePointer).isNull()) {
                const mName = s(method_get_name(m) as NativePointer);
                if (mName === "FindObjectOfType" && (method_get_param_count(m) as number) === 1) {
                    try {
                        invokeMethod(m, null, [navType]);
                        targetMi = m;
                        break;
                    } catch {
                        // Try next
                    }
                }
            }
        }

        if (targetMi.isNull()) {
            log("[auto-boot] FindFirstObjectByType/FindObjectOfType method overload not found!");
            return null;
        }

        const inst = invokeMethod(targetMi, null, [navType]);
        if (!inst.isNull()) {
            log(`[auto-boot] Active instance discovered: ${inst}`);
            return inst;
        }
    } catch (e) {
        log(`[auto-boot] Error during active instance discovery: ${(e as Error).message}`);
    }
    return null;
}

function discoverActiveContainerInstance(): NativePointer | null {
    try {
        const uoKlass = findClass("UnityEngine.CoreModule.dll", "UnityEngine", "Object");
        if (!uoKlass) return null;

        const containerKlass = findClassAnywhere("idun.Idun.Source.IdunMeta.View.Hud.Screens.CampaignScreen", "LevelMapWidgetContainer");
        if (!containerKlass) return null;

        const containerType = getSystemType(containerKlass);
        if (containerType.isNull()) return null;

        let targetMi: NativePointer = ptr(0);
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        
        while (!(m = class_get_methods(uoKlass, it) as NativePointer).isNull()) {
            const mName = s(method_get_name(m) as NativePointer);
            if (mName === "FindFirstObjectByType" && (method_get_param_count(m) as number) === 1) {
                try {
                    invokeMethod(m, null, [containerType]);
                    targetMi = m;
                    break;
                } catch {
                    // Try next
                }
            }
        }

        if (targetMi.isNull()) {
            it.writePointer(ptr(0));
            while (!(m = class_get_methods(uoKlass, it) as NativePointer).isNull()) {
                const mName = s(method_get_name(m) as NativePointer);
                if (mName === "FindObjectOfType" && (method_get_param_count(m) as number) === 1) {
                    try {
                        invokeMethod(m, null, [containerType]);
                        targetMi = m;
                        break;
                    } catch {
                        // Try next
                    }
                }
            }
        }

        if (targetMi.isNull()) return null;

        const inst = invokeMethod(targetMi, null, [containerType]);
        if (!inst.isNull()) {
            log(`[auto-boot] Active LevelMapWidgetContainer discovered: ${inst}`);
            return inst;
        }
    } catch (e) {
        log(`[auto-boot] Error during active container discovery: ${(e as Error).message}`);
    }
    return null;
}

export function register(ctx: Ctx): void {
    const navKlass = findClassAnywhere("idun.UI", "IdunNavigation");
    if (navKlass) {
        log(`[auto-boot-debug] IdunNavigation klass found @ ${navKlass}`);
        const itFields = Memory.alloc(Process.pointerSize);
        itFields.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(navKlass, itFields) as NativePointer).isNull()) {
            const fieldName = s(field_get_name(f) as NativePointer);
            const offset = field_get_offset(f) as number;
            log(`[auto-boot-debug]   Field: ${fieldName} @ offset 0x${offset.toString(16)}`);
        }

        const itMethods = Memory.alloc(Process.pointerSize);
        itMethods.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(navKlass, itMethods) as NativePointer).isNull()) {
            const methodName = s(method_get_name(m) as NativePointer);
            log(`[auto-boot-debug]   Method: ${methodName} (param count: ${method_get_param_count(m)})`);
        }

        const initMethod = findMethod(navKlass, "Init");
        if (initMethod && !initMethod.ptr.isNull()) {
            try {
                Interceptor.attach(initMethod.ptr, {
                    onEnter(args) {
                        const self = ptr(args[0].toString());
                        if (!lastNavigationInstance || !lastNavigationInstance.equals(self)) {
                            lastNavigationInstance = self;
                            log(`[auto-boot] Captured IdunNavigation @ ${self} via Init hook!`);

                            // Trigger dependency extraction after a delay to ensure scene variables are fully populated
                            setTimeout(() => {
                                if (lastNavigationInstance) {
                                    extractDependenciesAndNavigate(lastNavigationInstance);
                                }
                            }, 4000);
                        }
                    }
                });
                log("[+] IdunNavigation.Init (startup capture hook installed)");
            } catch (e) {
                log(`[auto-boot] Failed to hook Init: ${(e as Error).message}`);
            }
        }

        const showScreen = findMethod(navKlass, "ShowScreenAndHideOthers");
        if (showScreen && !showScreen.ptr.isNull()) {
            try {
                Interceptor.attach(showScreen.ptr, {
                    onEnter(args) {
                        const self = ptr(args[0].toString());
                        const screenId = args[1].toInt32();

                        if (!lastNavigationInstance || !lastNavigationInstance.equals(self)) {
                            lastNavigationInstance = self;
                            log(`[auto-boot] Captured IdunNavigation @ ${self} via passive hook (screenId=${screenId})`);

                            // Trigger dependency extraction after a short delay
                            setTimeout(() => {
                                if (lastNavigationInstance) {
                                    extractDependenciesAndNavigate(lastNavigationInstance);
                                }
                            }, 500);
                        }
                    }
                });
                log("[+] IdunNavigation.ShowScreenAndHideOthers (passive capture hook installed)");
            } catch (e) {
                log(`[auto-boot] Failed to hook ShowScreenAndHideOthers: ${(e as Error).message}`);
            }
        }
    } else {
        log("[auto-boot] IdunNavigation class not found during registration");
    }

    const containerKlass = findClassAnywhere("idun.Idun.Source.IdunMeta.View.Hud.Screens.CampaignScreen", "LevelMapWidgetContainer");
    if (containerKlass) {
        log(`[auto-boot-debug] LevelMapWidgetContainer klass found @ ${containerKlass}`);
        const loadMethod = findMethod(containerKlass, "Load");
        if (loadMethod && !loadMethod.ptr.isNull()) {
            try {
                Interceptor.attach(loadMethod.ptr, {
                    onEnter(args) {
                        const self = ptr(args[0].toString());
                        lastLevelMapWidgetContainerInstance = self;
                        log(`[auto-boot] Captured LevelMapWidgetContainer @ ${self} via Load hook!`);
                    }
                });
                log("[+] LevelMapWidgetContainer.Load (active campaign container capture hook installed)");
            } catch (e) {
                log(`[auto-boot] Failed to hook LevelMapWidgetContainer.Load: ${(e as Error).message}`);
            }
        }
    } else {
        log("[auto-boot] Warning: LevelMapWidgetContainer class not found during registration");
    }

    // Active discovery loop (zero-click amorce for late-attach / warm-restarts)
    let discoveryAttempts = 0;
    const maxDiscoveryAttempts = 8;
    
    function attemptActiveDiscovery() {
        if (lastNavigationInstance || autoBootExecuted) return;
        
        log(`[auto-boot] Running active discovery (attempt ${discoveryAttempts + 1}/${maxDiscoveryAttempts})...`);
        void queueOnMainThread(() => {
            const inst = discoverActiveInstance();
            if (inst && !inst.isNull()) {
                lastNavigationInstance = inst;
                log(`[auto-boot] Active discovery SUCCESS! Captured IdunNavigation @ ${inst}`);
                extractDependenciesAndNavigate(inst);
            } else {
                discoveryAttempts++;
                if (discoveryAttempts < maxDiscoveryAttempts) {
                    setTimeout(attemptActiveDiscovery, 3000);
                } else {
                    log("[auto-boot] Active discovery did not locate IdunNavigation. Standing by for passive hooks (user interaction)...");
                }
            }
        });
    }

    // Start discovery after a 6-second delay to allow scene settling during boot
    setTimeout(attemptActiveDiscovery, 6000);

    /**
     * EXTRACTION SEULE — le catalogue d'items SANS bataille, SANS navigation, SANS heap scan.
     *
     * ⚠ POURQUOI CE RPC EXISTE, ET CE QU'IL REMPLACE. Mesuré le 2026-08-19 sur un process
     * FROID (jeu relancé, aucune bataille jamais entrée, `amorce.autoAmorces = 0` vérifié
     * avant et après) : un runner se monte ET SE JOUE sans aucune amorce — `rl_duel build` en
     * 8,1 s, `aiturn` 156 events, stage `Running`, jeu vivant. Aucun crash `0x2c`. Le SEUL
     * manquant était `lastGameConfig` : `previewBis` refusait par « no lastGameConfig
     * captured », et sans lui CritChance/CritDamage/BlockChance/BlockDamage valent 0 sur
     * TOUTES les unités (#419-r5).
     *
     * Or ce pointeur ne vient PAS d'une bataille : il est lu dans `IdunNavigation._gameConfig`,
     * donc sur un ÉCRAN MÉTA. L'amorce, qui entre en bataille puis se retire pour l'obtenir,
     * faisait un détour de ~14 s — et c'est ce détour qui pilote l'UI, donc qui peut coincer
     * le jeu. Ici : deux champs lus, rien d'autre.
     *
     * ⛔ CE RPC NE NAVIGUE PAS. `triggerAutoBoot`, lui, allume `navigationAutoActive` et ramène
     * le jeu sur la campagne — c'est précisément pourquoi il est éteint par défaut depuis le
     * 2026-08-10.
     * ⛔ ET IL NE SCANNE PAS LE TAS. `tryActiveDiscoveryOfSources` fait des heap scans de 30 à
     * 60 s, proscrits hors action explicite.
     *
     * ⚠ Il EXIGE que l'instance d'`IdunNavigation` ait été captée par le hook passif. Si elle
     * ne l'est pas, il le DIT et ne se rabat sur RIEN : un pointeur deviné ici serait pire que
     * l'absence, parce qu'un `_gameConfig` non nul mais faux désarme silencieusement les
     * replis en aval (ils ne s'arment que sur `null`).
     */
    ctx.rpc.autoBootExtraire = () => queueOnMainThread(() => {
        // ⚠ DEUX SOURCES, PAR ORDRE D'AUTORITÉ — et la seconde est indispensable.
        // Le hook de capture est PASSIF (`Init` / `ShowScreenAndHideOthers`) : il ne tire qu'à
        // une transition d'écran. Un inject POSTÉRIEUR au boot le manque, et `captured: false`
        // se lit alors comme « pas de navigation » alors que l'instance est bien là, vivante.
        // Mesuré le 2026-08-19 : la session auto-restaurée au boot du host l'avait
        // (`0x29df434a960`), la session injectée ensuite ne l'avait pas -- même jeu, même
        // écran. Une source unique fait donc échouer le RPC sur un ordre d'arrivée.
        // Le repli passe par `FindObjectsByType`, un appel MOTEUR (pas un scan de tas).
        let nav = lastNavigationInstance;
        let source = "hook passif (`Init` / `ShowScreenAndHideOthers`)";
        if (nav === null || nav.isNull()) {
            const k = findClassAnywhere("idun.UI", "IdunNavigation");
            if (!k) return { ok: false, error: "`idun.UI.IdunNavigation` INTROUVABLE sur ce build" };
            const trouve = premiereInstance(k);
            if (!(trouve instanceof NativePointer)) {
                return { ok: false, error: "aucune `IdunNavigation` joignable -- " + trouve.error };
            }
            if (trouve.isNull()) {
                return { ok: false, error: "`FindObjectsByType` a rendu un pointeur NUL" };
            }
            nav = trouve;
            source = "REPLI `FindObjectsByType` -- le hook passif n'avait pas tiré";
        }
        const navClass = nav.readPointer();
        // Offsets résolus PAR NOM : la disposition d'`IdunNavigation` bouge entre versions
        // d'Unity (cf. le commentaire d'`extractDependenciesAndNavigate`).
        const upOff = getFieldOffset(navClass, "_unitProgression");
        const gcOff = getFieldOffset(navClass, "_gameConfig");
        const gcPtr = gcOff >= 0 ? nav.add(gcOff).readPointer() : ptr(0);
        const upPtr = upOff >= 0 ? nav.add(upOff).readPointer() : ptr(0);
        if (!gcPtr.isNull()) setLastGameConfig(gcPtr);
        if (!upPtr.isNull()) setUnitProgressionPtr(upPtr);
        const dto = getLastGameConfig();

        // TROISIÈME DÉPENDANCE : l'`IdunUniverse`.
        //
        // ⚠ ELLE MANQUAIT, ET SON ABSENCE NE SE VOYAIT QU'EN AVAL. `IdunNavigation` ne la
        // porte pas ; elle vit sur le singleton `thor.Globals` (`currentIdunUniverse`), qui
        // survit aux changements de scène. Tant qu'on ne la posait pas ici, tout appelant du
        // builder natif se faisait refuser (« `IdunUniverse` NON CAPTURE ») alors que l'amorce
        // venait de rendre `ok: true` -- un vert qui ne couvrait pas ce qu'on croyait.
        // `BattleConfigGameConfigValues..ctor(GameConfigDto, ITileConfigurationSource)` en a
        // besoin, et l'univers implémente AUSSI `IReleasableUnitsSource` : c'est donc lui qui
        // porte `BC.Tiles` et le catalogue relâchable, pas une capture de bataille.
        //
        // La voie est un REPLI STATIQUE (lecture d'un champ d'instance sur un singleton), pas
        // un scan de tas : elle tient la promesse « aucune bataille, aucun scan » ci-dessous.
        // Idempotente -- elle rend « already captured » si le hook passif l'a déjà posée.
        let universe: string | null = null;
        let universeVia: string | null = null;
        try {
            universeVia = tryGlobalsCapture();
            const u = getCapturedUniverse();
            universe = u !== null && !u.isNull() ? u.toString() : null;
        } catch (e) {
            // On NOMME l'échec au lieu de le taire : un `null` muet ferait diagnostiquer
            // « pas d'univers sur ce build » là où c'est la lecture qui a fauté.
            universeVia = "ÉCHEC : " + (e as Error).message;
        }

        return {
            // ⚠ `ok` reste indexé sur le `gameConfigDto` SEUL, et c'est délibéré : l'univers
            // est une dépendance du builder natif, pas de l'amorce. Le rabattre dans `ok`
            // ferait rougir l'amorce sur un jeu où tout ce qu'elle promet est pourtant posé.
            ok: dto !== null && !dto.isNull(),
            navigation: nav.toString(),
            // ⚠ PUBLIÉE, jamais tue : un résultat obtenu par le repli ne doit pas se lire
            // comme un résultat obtenu sur l'instance que le jeu emploie.
            source,
            champs: { _gameConfig: `+0x${gcOff.toString(16)}`,
                      _unitProgression: `+0x${upOff.toString(16)}` },
            // TRI-ÉTAT : `null` = pas capturé. Jamais rendu comme une chaîne vide, qui se
            // lirait comme « capturé mais sans contenu ».
            gameConfigDto: dto !== null && !dto.isNull() ? dto.toString() : null,
            unitProgression: upPtr.isNull() ? null : upPtr.toString(),
            idunUniverse: universe,
            idunUniverseVia: universeVia,
            note: "aucune bataille, aucune navigation, aucun scan de tas",
        };
    });

    ctx.rpc.triggerAutoBoot = () => {
        return queueOnMainThread(() => {
            const nav = lastNavigationInstance;
            if (!nav) {
                throw new Error("Aucune instance d'IdunNavigation n'a encore été capturée. Veuillez naviguer en jeu pour la capturer.");
            }
            autoBootExecuted = false; // Reset to allow force-trigger
            // Appel EXPLICITE : on leve la desactivation par defaut, puisque c'est
            // precisement ce que l'appelant demande.
            navigationAutoActive = true;
            extractDependenciesAndNavigate(nav);
            return { ok: true, instance: nav.toString(), navigationAuto: true };
        });
    };

    /** Rallume (ou reeteint) la navigation AUTOMATIQUE au boot.
     *
     *  Elle est eteinte par defaut depuis le 2026-08-10 : elle ramenait le jeu sur la
     *  campagne a chaque injection, y compris avec `{ amorce: false }`, en plein travail
     *  sur un autre ecran. body: { actif: boolean } */
    ctx.rpc.setAutoBootNavigation = (body?: { actif?: boolean }) =>
        queueOnMainThread(() => {
            if (typeof body?.actif !== "boolean") {
                return { ok: false, err: "setAutoBootNavigation: `actif` (booleen) requis",
                         actuel: navigationAutoActive };
            }
            navigationAutoActive = body.actif;
            return { ok: true, navigationAuto: navigationAutoActive };
        });

    ctx.rpc.diagnoseCampaign = () => {
        return queueOnMainThread(() => {
            const container = lastLevelMapWidgetContainerInstance;
            if (!container || container.isNull()) {
                return { ok: false, error: "No container captured" };
            }
            // Read LevelMapWidget _levelMapWidget pointer at offset 0xA8
            const levelMapWidget = container.add(0xA8).readPointer();
            // Read LevelMapPartWidget _partInstance pointer at offset 0xC0
            const partInstance = levelMapWidget.isNull() ? ptr(0) : levelMapWidget.add(0xC0).readPointer();
            
            let buttonsLoaded = false;
            let buttonPtrStr = "null";
            if (!partInstance.isNull()) {
                const partKlass = findClassAnywhere("idun.UI.Screens.CampaignScreen", "LevelMapPartWidget");
                if (partKlass) {
                    const getButtonsLoaded = findMethod(partKlass, "get_ButtonsLoaded");
                    if (getButtonsLoaded) {
                        buttonsLoaded = invokeMethod(getButtonsLoaded.info, partInstance, null).toInt32() === 1;
                    }
                    const getButton = findMethod(partKlass, "GetButton");
                    if (getButton && buttonsLoaded) {
                        const buttonPtr = invokeMethod(getButton.info, partInstance, [Memory.alloc(4).writeS32(5)]);
                        buttonPtrStr = buttonPtr.toString();
                    }
                }
            }
            return {
                ok: true,
                container: container.toString(),
                levelMapWidget: levelMapWidget.toString(),
                partInstance: partInstance.toString(),
                buttonsLoaded,
                buttonPtr: buttonPtrStr
            };
        });
    };

    ctx.rpc.getAutoBootStatus = () => ({
        captured: lastNavigationInstance !== null,
        instance: lastNavigationInstance ? lastNavigationInstance.toString() : null,
        containerCaptured: lastLevelMapWidgetContainerInstance !== null,
        containerInstance: lastLevelMapWidgetContainerInstance ? lastLevelMapWidgetContainerInstance.toString() : null,
        executed: autoBootExecuted,
        hasSource: getCampaignGameModeSourcePtr() !== null,
        // Publie, parce qu'un module qui ne bouge plus l'UI doit pouvoir le DIRE : sinon
        // << la campagne ne revient plus >> se lit comme une panne au lieu d'un reglage.
        navigationAuto: navigationAutoActive,
    });
}
