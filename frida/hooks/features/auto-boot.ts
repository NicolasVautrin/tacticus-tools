// Zero-click auto-boot sequence: automatically extracts GameConfigDto and
// UnitProgression pointers directly from the IdunNavigation instance at boot.
//
// Relies on a passive hook on IdunNavigation.Init or ShowScreenAndHideOthers
// to capture the navigation instance immediately at boot.
// Fallback: targeted fast active discovery for IdunNavigation if passive hooks haven't
// fired after 6 seconds.

import {
    findClassAnywhere, findMethod, findClass,
    class_get_fields, field_get_name, field_get_offset,
    class_get_methods, method_get_name, method_get_param_count,
    s, getSystemType, methodEntry, findCtorByParamCount
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";
import {
    getLastSource,
    getLastGameConfig,
    tryActiveDiscoveryOfSources,
    setLastGameConfig,
    setLastUnitProgression
} from "./campaign-builder.js";

let lastNavigationInstance: NativePointer | null = null;
let lastLevelMapWidgetContainerInstance: NativePointer | null = null;
let autoBootExecuted = false;

export function extractDependenciesAndNavigate(navInstance: NativePointer): void {
    if (autoBootExecuted) return;

    log(`[auto-boot] Starting direct dependency extraction from IdunNavigation @ ${navInstance}...`);

    try {
        // Read unitProgression pointer at offset 0x1f0
        const unitProgressionPtr = navInstance.add(0x1f0).readPointer();
        // Read gameConfig pointer at offset 0x240
        const gameConfigPtr = navInstance.add(0x240).readPointer();

        log(`[auto-boot] Extracted pointers: _gameConfig=${gameConfigPtr}, _unitProgression=${unitProgressionPtr}`);

        if (!gameConfigPtr.isNull()) {
            setLastGameConfig(gameConfigPtr);
        } else {
            log("[auto-boot] Warning: extracted _gameConfig pointer is null!");
        }

        if (!unitProgressionPtr.isNull()) {
            setLastUnitProgression(unitProgressionPtr);
        } else {
            log("[auto-boot] Warning: extracted _unitProgression pointer is null!");
        }

        // Try early active discovery. If captured both, exit early.
        const discovered = tryActiveDiscoveryOfSources();
        if (discovered && getLastSource() !== null) {
            log("[auto-boot] SUCCESS! CampaignGameModeSource and GameConfigDto already captured naturally, skipping auto-navigation.");
            autoBootExecuted = true;
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
                            setTimeout(() => {
                                const updatedDiscovered = tryActiveDiscoveryOfSources();
                                const updatedSource = getLastSource();
                                if (updatedSource) {
                                    log(`[auto-boot] CampaignGameModeSource successfully captured @ ${updatedSource}!`);
                                } else {
                                    log("[auto-boot] Warning: CampaignGameModeSource was not captured. Running active discovery fallback...");
                                    tryActiveDiscoveryOfSources();
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

    // Active discovery loop (zero-click warmup for late-attach / warm-restarts)
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

    ctx.rpc.triggerAutoBoot = () => {
        return queueOnMainThread(() => {
            const nav = lastNavigationInstance;
            if (!nav) {
                throw new Error("Aucune instance d'IdunNavigation n'a encore été capturée. Veuillez naviguer en jeu pour la capturer.");
            }
            autoBootExecuted = false; // Reset to allow force-trigger
            extractDependenciesAndNavigate(nav);
            return { ok: true, instance: nav.toString() };
        });
    };

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
        hasSource: getLastSource() !== null,
    });
}
