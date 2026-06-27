// RPC dispatcher: aggregates feature modules.
//
// Each feature exports `register(ctx)` that attaches its handlers to
// `ctx.rpc`. Adding a feature = create hooks/features/foo.ts +
// import here. No changes to existing features needed.

import * as status from "./features/status.js";
import * as sim from "./features/sim.js";
import * as compare from "./features/compare.js";
import * as cheat from "./features/cheat.js";
import * as configIo from "./features/config-io.js";
import * as modeSourceCapture from "./features/mode-source-capture.js";
import * as launch from "./features/launch.js";
import * as unitAssetMap from "./features/unit-asset-map.js";
import * as movementTrace from "./features/movement-trace.js";
import * as unitVisualResolve from "./features/unit-visual-resolve.js";
import * as introspect from "./features/introspect.js";
import * as campaignBuilder from "./features/campaign-builder.js";
import * as mowBuilder from "./features/mow-builder.js";
import * as aiTrace from "./features/ai-trace.js";
import * as aiUtilityTrace from "./features/ai-utility-trace.js";
import * as simEngine from "./features/sim-engine.js";
import * as overwatchFix from "./features/overwatch-fix/index.js";
import * as bucketAudit from "./features/bucket-audit.js";
import * as dumpComposed from "./features/dump-composed.js";
import * as dispatchObserve from "./features/dispatch-observe.js";
import * as whatifTrigger from "./features/whatif-trigger.js";
import * as autoBoot from "./features/auto-boot.js";
import * as uiNav from "./features/ui-nav.js";
import * as warmupSingletons from "./features/warmup-singletons.js";
import * as battleConfig from "./features/battle-config.js";
import * as observe from "./features/observe.js";
import * as dumpBoards from "./features/dump-boards.js";
import * as boardTrace from "./features/board-trace.js";
import * as dumpPvpBoards from "./features/dump-pvp-boards.js";
import * as normalizeBc from "./features/normalize-bc.js";
import * as crashTrap from "./features/crash-trap.js";
import * as initTrace from "./features/init-trace.js";
import * as moveOptions from "./features/move-options.js";
import * as winnerCapture from "./features/winner-capture.js";
import * as messageTrace from "./features/message-trace.js";
import * as aiStep from "./features/ai-step/index.js";
import * as modifierObserve from "./features/modifier-observe.js";

export interface Ctx {
    rpc: Record<string, (...args: any[]) => unknown>;
}

import { dumpComponentFields } from "./scratch/dump-comps.js";
import { dumpComponentMethods } from "./scratch/dump-methods.js";
import { findActionComponent } from "./scratch/find-action.js";
import { dumpAllComponents } from "./scratch/list-comps.js";
import { dumpUnitFlagsFields } from "./scratch/dump-flags.js";
import { introspectUnitFlags } from "./scratch/introspect-flags.js";
import { searchAllClasses } from "./scratch/search-classes.js";
import { debugFlagsType } from "./scratch/debug-flags-type.js";
import { dumpPathfinderMethods } from "./scratch/dump-pathfinder.js";
import { dumpPathfinderParams } from "./scratch/dump-params.js";
import { dumpPathfinderReturn } from "./scratch/dump-return.js";
import { findPathfindersOffset } from "./scratch/find-pathfinder-off.js";
import { dumpRunnerFields } from "./scratch/dump-runner-fields.js";
import { dumpStatComponents } from "./scratch/dump-stats.js";
import { dumpAbilityFields } from "./scratch/dump-ability.js";
import { dumpActiveAbilityProperly } from "./scratch/dump-ability-properly.js";
import { dumpAbilityStateFields } from "./scratch/dump-ability-state.js";
import { dumpUnitProgression } from "./scratch/dump-unit-progression.js";
import { dumpUnitComponentFields } from "./scratch/dump-unit-comp.js";
import { dumpWeaponsFields } from "./scratch/dump-weapons.js";
import { dumpWeaponFields } from "./scratch/dump-weapon-class.js";
import { dumpWeaponsCompTypes } from "./scratch/dump-weapons-types.js";
import { dumpWeaponProfileFields } from "./scratch/dump-weapon-profile.js";
import { dumpCritBlockComps } from "./scratch/dump-crit-block.js";
import { dumpDamageProfileFields } from "./scratch/dump-damage-profile.js";
import { dumpDamageProfileProperly } from "./scratch/dump-dp-properly.js";
import { dumpWeaponProfileTypes } from "./scratch/dump-wp-types.js";
import { dumpAttackDefense } from "./scratch/dump-attack-defense.js";
import { dumpUnitEntityFields } from "./scratch/dump-unit-entity.js";
import { dumpUnitEntityFields as dumpUnitEntityFieldsCore } from "./scratch/dump-unit-entity-core.js";
import { dumpStatComponentFields } from "./scratch/dump-stat-comp.js";
import { dumpStatCompTypes } from "./scratch/dump-stat-types.js";
import { dumpValueOverrideFields } from "./scratch/dump-value-override.js";
import { dumpExtraMaxDmg } from "./scratch/dump-extra-dmg.js";
import { dumpProgressionExtensions } from "./scratch/dump-prog-ext.js";
import { dumpUnitProgressionFields } from "./scratch/dump-unit-prog-fields.js";
import { dumpUnitProgressionAnywhere } from "./scratch/dump-prog-anywhere.js";
import { dumpUnitProgressionMethods } from "./scratch/dump-unit-prog-methods.js";
import { dumpStatsFormulaMethods } from "./scratch/dump-stats-formula.js";
import { dumpStatsFormulaFields } from "./scratch/dump-stats-formula-fields.js";
import { findProgressionSingletons } from "./scratch/find-prog-instances.js";
import { findD3Index } from "./scratch/map-ranks.js";
import { checkGetMaxConfiguredRank } from "./scratch/check-method.js";
import { checkParent } from "./scratch/check-parent.js";
import { inspectInstance } from "./scratch/inspect-instance.js";
import { checkKlass } from "./scratch/check-klass.js";
import { dumpMethodInfo } from "./scratch/dump-method-info.js";
import { checkInvokerExport } from "./scratch/check-invoker.js";
import { dumpUnitProgressionDataFields } from "./scratch/dump-unit-prog-data-fields.js";
import { dumpUnitProgDataNested } from "./scratch/dump-unit-prog-data-nested.js";
import { testStatic } from "./scratch/test-static.js";
import { dumpStatComponentFieldTypes } from "./scratch/dump-stat-comp-types.js";
import { dumpUnitEntityFields as dumpUnitEntityFieldsV2 } from "./scratch/dump-unit-entity-fields.js";
import { dumpUniverseFields } from "./scratch/dump-universe.js";
import * as rlBridge from "./features/rl/bridge.js";
import { testSafeInvoke } from "./scratch/test-safe-invoke.js";
import { findSingletonsViaGlobals } from "./scratch/find-globals.js";
import { searchForGlobals } from "./scratch/search-class.js";
import { inspectPtr } from "./scratch/inspect-ptr.js";
import { checkMethodParams } from "./scratch/check-method-params.js";
import { checkStatsFields } from "./scratch/check-stats-fields.js";
import { registerTestFind } from "./scratch/test-unity-find.js";
import { registerTestScene } from "./scratch/test-scene.js";
import { register as registerDumpNav } from "./scratch/dump-navigation-methods.js";
import { register as registerInspectCgms } from "./scratch/inspect-cgms.js";
import { register as registerDumpIdunNavInfo } from "./scratch/dump-idun-nav-info.js";
import { register as registerTryToCampaign } from "./scratch/try-to-campaign.js";



export function wireRpc(ctx: Ctx): void {
    ctx.rpc.dumpComps = () => {
        dumpComponentFields();
        return { ok: true };
    };
    ctx.rpc.dumpMethods = () => {
        dumpComponentMethods();
        return { ok: true };
    };
    ctx.rpc.findAction = () => {
        findActionComponent();
        return { ok: true };
    };
    ctx.rpc.listComps = () => {
        dumpAllComponents();
        return { ok: true };
    };
    ctx.rpc.dumpFlags = () => {
        dumpUnitFlagsFields();
        return { ok: true };
    };
    ctx.rpc.introspectFlags = () => {
        introspectUnitFlags();
        return { ok: true };
    };
    ctx.rpc.searchClasses = (query: string) => {
        searchAllClasses(query);
        return { ok: true };
    };
    ctx.rpc.searchMethods = (query: string) => {
        return { ok: false, msg: "Not implemented yet" };
    };
    ctx.rpc.debugFlagsType = () => {
        debugFlagsType();
        return { ok: true };
    };
    ctx.rpc.dumpPathfinder = () => {
        dumpPathfinderMethods();
        return { ok: true };
    };
    ctx.rpc.dumpParams = () => {
        dumpPathfinderParams();
        return { ok: true };
    };
    ctx.rpc.dumpReturn = () => {
        dumpPathfinderReturn();
        return { ok: true };
    };
    ctx.rpc.findPathfinderOff = () => {
        findPathfindersOffset();
        return { ok: true };
    };
    ctx.rpc.dumpRunnerFields = () => {
        dumpRunnerFields();
        return { ok: true };
    };
    ctx.rpc.dumpStats = () => {
        dumpStatComponents();
        return { ok: true };
    };
    ctx.rpc.dumpAbility = () => {
        dumpAbilityFields();
        return { ok: true };
    };
    ctx.rpc.dumpAbilityProperly = () => {
        dumpActiveAbilityProperly();
        return { ok: true };
    };
    ctx.rpc.dumpAbilityState = () => {
        dumpAbilityStateFields();
        return { ok: true };
    };
    ctx.rpc.dumpUnitProgression = () => {
        dumpUnitProgression();
        return { ok: true };
    };
    ctx.rpc.dumpUnitComp = () => {
        dumpUnitComponentFields();
        return { ok: true };
    };
    ctx.rpc.dumpWeapons = () => {
        dumpWeaponsFields();
        return { ok: true };
    };
    ctx.rpc.dumpWeaponClass = () => {
        dumpWeaponFields();
        return { ok: true };
    };
    ctx.rpc.dumpWeaponsTypes = () => {
        dumpWeaponsCompTypes();
        return { ok: true };
    };
    ctx.rpc.dumpWeaponProfile = () => {
        dumpWeaponProfileFields();
        return { ok: true };
    };
    ctx.rpc.dumpCritBlock = () => {
        dumpCritBlockComps();
        return { ok: true };
    };
    ctx.rpc.dumpAttackDefense = () => {
        dumpAttackDefense();
        return { ok: true };
    };
    ctx.rpc.dumpUnitEntity = () => {
        dumpUnitEntityFields();
        dumpUnitEntityFieldsV2();
        return { ok: true };
    };
    ctx.rpc.dumpStatComp = () => {
        dumpStatComponentFields();
        return { ok: true };
    };
    ctx.rpc.dumpStatTypes = () => {
        dumpStatCompTypes();
        return { ok: true };
    };
    ctx.rpc.dumpValueOverride = () => {
        dumpValueOverrideFields();
        return { ok: true };
    };
    ctx.rpc.dumpExtraDmg = () => {
        dumpExtraMaxDmg();
        return { ok: true };
    };
    ctx.rpc.dumpProgExt = () => {
        dumpProgressionExtensions();
        return { ok: true };
    };
    ctx.rpc.dumpUnitProgFields = () => {
        dumpUnitProgressionFields();
        return { ok: true };
    };
    ctx.rpc.dumpProgAnywhere = () => {
        dumpUnitProgressionAnywhere();
        return { ok: true };
    };
    ctx.rpc.dumpUniverse = () => {
        dumpUniverseFields();
        return { ok: true };
    };
    ctx.rpc.dumpUnitProgMethods = () => {
        dumpUnitProgressionMethods();
        return { ok: true };
    };
    ctx.rpc.dumpStatsFormula = () => {
        dumpStatsFormulaMethods();
        return { ok: true };
    };
    ctx.rpc.dumpStatsFormulaFields = () => {
        dumpStatsFormulaFields();
        return { ok: true };
    };
    ctx.rpc.findProgInstances = () => {
        return findProgressionSingletons();
    };
    ctx.rpc.mapRanks = () => {
        findD3Index();
        return { ok: true };
    };
    ctx.rpc.checkMethod = () => {
        checkGetMaxConfiguredRank();
        return { ok: true };
    };
    ctx.rpc.checkParent = () => {
        checkParent();
        return { ok: true };
    };
    ctx.rpc.inspectInstance = () => {
        inspectInstance();
        return { ok: true };
    };
    ctx.rpc.checkKlass = () => {
        checkKlass();
        return { ok: true };
    };
    ctx.rpc.dumpMethod = (m: string) => {
        dumpMethodInfo(ptr(m));
        return { ok: true };
    };
    ctx.rpc.checkInvoker = () => {
        checkInvokerExport();
        return { ok: true };
    };
    ctx.rpc.dumpUnitProgData = () => {
        dumpUnitProgressionDataFields();
        return { ok: true };
    };
    ctx.rpc.dumpUnitProgDataNested = () => {
        dumpUnitProgDataNested();
        return { ok: true };
    };
    ctx.rpc.testStatic = () => {
        testStatic();
        return { ok: true };
    };
    ctx.rpc.dumpStatComp = () => {
        dumpStatComponentFields();
        return { ok: true };
    };
    ctx.rpc.dumpUnitEntityCore = () => {
        dumpUnitEntityFieldsCore();
        return { ok: true };
    };
    ctx.rpc.dumpDamageProfile = () => {
        dumpDamageProfileFields();
        return { ok: true };
    };
    ctx.rpc.dumpDpProperly = () => {
        dumpDamageProfileProperly();
        return { ok: true };
    };
    ctx.rpc.dumpWpTypes = () => {
        dumpWeaponProfileTypes();
        return { ok: true };
    };
    ctx.rpc.testSafeInvoke = () => { testSafeInvoke(); return { ok: true }; };
    ctx.rpc.checkMethodParams = () => { checkMethodParams(); return { ok: true }; };
    ctx.rpc.checkStatsFields = () => { checkStatsFields(); return { ok: true }; };
    ctx.rpc.findGlobals = () => { findSingletonsViaGlobals(); return { ok: true }; };


    ctx.rpc.searchClass = () => { searchForGlobals(); return { ok: true }; };
    ctx.rpc.inspectPtr = (p: string) => { inspectPtr(p); return { ok: true }; };

    registerTestFind(ctx);
    registerTestScene(ctx);
    registerDumpNav(ctx);
    registerInspectCgms(ctx);
    registerDumpIdunNavInfo(ctx);
    registerTryToCampaign(ctx);
    rlBridge.register(ctx);

    /** RPC: Get battle log segment. */
    // movement-trace stays opt-in — its 39 Interceptor.attach hooks on
    // EvaluateMovementInSteps utilities each call 3× class_get_name and
    // produced visible navigation lag. Re-enable explicitly when AI movement
    // debugging is the active task. ai-trace L3 covers the same surface but
    // streams to disk instead of an in-memory ring; default L3=off so this
    // path stays cheap unless the user explicitly enables it.
    void movementTrace;
    [status, sim, compare, cheat, configIo, modeSourceCapture, launch,
     unitAssetMap, /* movementTrace, */ unitVisualResolve, introspect,
     campaignBuilder, mowBuilder, aiTrace, aiUtilityTrace, simEngine,
     overwatchFix, bucketAudit, dumpComposed, dispatchObserve, whatifTrigger, autoBoot,
     uiNav, warmupSingletons, battleConfig, observe, dumpBoards, boardTrace,
     dumpPvpBoards, normalizeBc, crashTrap, initTrace,
     // messageTrace AVANT moveOptions — il set scoringRunnerId/applySeq.
     messageTrace, moveOptions, winnerCapture, aiStep, modifierObserve]
        .forEach((f) => f.register(ctx));
}
