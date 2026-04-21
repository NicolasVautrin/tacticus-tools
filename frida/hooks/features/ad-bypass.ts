// Ad bypass: auto-installed at hook load.
//
// Replaces three AdsProgression methods + one AdsTokenProgression check so
// the game treats every rewarded-ad request as an immediate success, without
// any actual video being shown. Applies once at load; idempotent guard.

import { Ctx } from "../controller.js";
import { findClass, findMethod } from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";

// AdsAvailabilityResult enum values (MetaLogicAssembly)
const AdsAvailabilityResult = {
    NoRewardedVideosAvailable: 0,
    NotEnoughTokensLeft: 1,
    IsAlreadyTryingToShowAnAd: 2,
    IsAlreadyShowingAnAd: 3,
    Offline: 4,
    Success: 5,
} as const;

let _installed = false;

function install(): void {
    if (_installed) return;

    // System.Action.Invoke() — used to fire zero-arg delegate callbacks
    const actionClass = findClass("mscorlib.dll", "System", "Action");
    const actionInvokeMi = actionClass ? findMethod(actionClass, "Invoke") : null;
    if (!actionInvokeMi) {
        console.log("[ad-bypass] System.Action.Invoke NOT FOUND — callbacks will not fire");
    }

    const callAction = (delegatePtr: NativePointer): void => {
        if (actionInvokeMi && !delegatePtr.isNull()) {
            try { invokeMethod(actionInvokeMi.info, delegatePtr, null); } catch (_) {}
        }
    };

    // ── AdsProgression (MetaLogicAssembly.dll) ──────────────────────────

    const adsProgClass = findClass(
        "MetaLogicAssembly.dll",
        "IdunMetaLogic.UserProgress",
        "AdsProgression"
    );
    if (!adsProgClass) {
        console.log("[ad-bypass] AdsProgression class NOT FOUND — skipping");
        return;
    }

    // ShowDailyDealsVideo(Action onSuccess, Action onFailure, Action onFocusRegained)
    // → AdsAvailabilityResult (int32)
    // Bypass: fire onSuccess + onFocusRegained immediately, return Success.
    const showDailyMi = findMethod(adsProgClass, "ShowDailyDealsVideo");
    if (showDailyMi) {
        Interceptor.replace(showDailyMi.ptr, new NativeCallback(
            function(
                _self: NativePointer,
                onSuccess: NativePointer,
                _onFailure: NativePointer,
                onFocusRegained: NativePointer,
                _mi: NativePointer
            ): number {
                callAction(onSuccess);
                callAction(onFocusRegained);
                return AdsAvailabilityResult.Success;
            },
            "int32",
            ["pointer", "pointer", "pointer", "pointer", "pointer"]
        ));
        console.log("[ad-bypass] AdsProgression.ShowDailyDealsVideo replaced");
    }

    // ShowVideo(String placement, Action onSuccess, Action onFailure, Action onFocusRegained)
    // → same return type. Covers other placements (stamina, etc.)
    const showVideoMi = findMethod(adsProgClass, "ShowVideo");
    if (showVideoMi) {
        Interceptor.replace(showVideoMi.ptr, new NativeCallback(
            function(
                _self: NativePointer,
                _placement: NativePointer,
                onSuccess: NativePointer,
                _onFailure: NativePointer,
                onFocusRegained: NativePointer,
                _mi: NativePointer
            ): number {
                callAction(onSuccess);
                callAction(onFocusRegained);
                return AdsAvailabilityResult.Success;
            },
            "int32",
            ["pointer", "pointer", "pointer", "pointer", "pointer", "pointer"]
        ));
        console.log("[ad-bypass] AdsProgression.ShowVideo replaced");
    }

    // IsAdAvailable() → bool; always return true so the refresh button stays enabled
    const isAvailableMi = findMethod(adsProgClass, "IsAdAvailable");
    if (isAvailableMi) {
        Interceptor.replace(isAvailableMi.ptr, new NativeCallback(
            function(_self: NativePointer, _mi: NativePointer): number { return 1; },
            "int32", ["pointer", "pointer"]
        ));
        console.log("[ad-bypass] AdsProgression.IsAdAvailable replaced");
    }

    // ── AdsTokenProgression (MetaLogicAssembly.dll) ─────────────────────
    // CanSpendDefaultAmount() → bool; always true so token-gate passes
    const tokenClass = findClass(
        "MetaLogicAssembly.dll",
        "IdunMetaLogic.UserProgress",
        "AdsTokenProgression"
    );
    const canSpendMi = tokenClass ? findMethod(tokenClass, "CanSpendDefaultAmount") : null;
    if (canSpendMi) {
        Interceptor.replace(canSpendMi.ptr, new NativeCallback(
            function(_self: NativePointer, _mi: NativePointer): number { return 1; },
            "int32", ["pointer", "pointer"]
        ));
        console.log("[ad-bypass] AdsTokenProgression.CanSpendDefaultAmount replaced");
    }

    Interceptor.flush();
    _installed = true;
}

export function register(_ctx: Ctx): void {
    install();
}
