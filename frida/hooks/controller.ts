// RPC dispatcher: aggregates feature modules.
//
// Each feature exports `register(ctx)` that attaches its handlers to
// `ctx.rpc`. Adding a feature = create hooks/features/foo.ts +
// import here. No changes to existing features needed.

import * as status from "./features/status.js";
import * as sim from "./features/sim.js";
import * as cheat from "./features/cheat.js";
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
import * as uiScroll from "./features/ui-scroll.js";
import * as uiWindows from "./features/ui-windows.js";
import * as fsmInput from "./features/fsm-input.js";
import * as battleEvents from "./features/battle-events.js";
import * as warmupSingletons from "./features/warmup-singletons.js";
import * as battleConfig from "./features/battle-config.js";
import * as observe from "./features/observe.js";
import * as dumpPvpBoards from "./features/dump-pvp-boards.js";
import * as normalizeBc from "./features/normalize-bc.js";
import * as crashTrap from "./features/crash-trap.js";
import * as netCapture from "./features/net-capture.js";
import * as wsCapture from "./features/ws-capture.js";
import * as expeditionBoard from "./features/expedition-board.js";
import * as rosterOwned from "./features/roster-owned.js";
import * as expeditionDispatch from "./features/expedition-dispatch.js";
import * as gcRendezvous from "./probes/gc-rendezvous.js";
import * as uiMutations from "./features/ui-mutations.js";
import * as initTrace from "./features/init-trace.js";
import * as winnerCapture from "./features/winner-capture.js";
import * as messageTrace from "./features/message-trace.js";
// replay-output-stream = capteur PUREMENT a la demande (#477) : le register n'arme
// AUCUN hook (zero Interceptor). Il expose la trace textuelle canonique du natif
// (`Replay.GetWholeBattleOutputStream`), celle-la meme que `Runner.ReplayValidator`
// compare caractere par caractere.
import * as replayOutputStream from "./features/replay-output-stream.js";
import * as aiStep from "./features/ai-step/index.js";
// modifier-observe = diagnostic PERMANENT on-demand (decompo par etage prediction+combat — l'outil
// doctrine « divergence de degat = decomposition, jamais fit », promu au build standard par #98).
// Le register N'ARME AUCUN hook (auto-arm neutralise depuis l'incident 2026-07-10 : Interceptor sur
// chemins de degat ultra-chauds pendant le churn reinject/warmup = crash) — il n'expose que les RPC
// modifierObserveInstall/Status/Reset ; l'armement est on-demand, sur etat STABLE (post-warmup).
import * as modifierObserve from "./features/modifier-observe.js";
import * as abilityPrefs from "./features/ability-prefs.js";
import * as scorerDamageTrace from "./features/scorer-damage-trace.js";
// effect-bonus-trace = #462-r4a-r1 : quel CANAL de `DamageModifiers` reçoit le bonus d'un effet
// (additif / liste capée / multiplicateur), et sur QUELLE FACE (attaquant vs défenseur). Même
// discipline que hitTrace/modifierObserve : `DamageModifiers$$Add` est sur le chemin de dégât,
// donc le register N'ARME RIEN — armement on-demand par `effectBonusTraceOn`, sous budget
// d'événements qui éteint la capture toute seule.
import * as effectBonusTrace from "./features/effect-bonus-trace.js";
// triggered-move-trace = le terme MOVE d'une triggered ability, ATTRIBUÉ à son unité ET à sa
// tuile (#443-r1a). Même discipline que hitTrace : le register n'arme RIEN (ce `MoveNext` fire
// une fois par tuile candidate ET par step du sweep de mouvement) — armement on-demand par
// `triggeredMoveTraceOn`.
import * as triggeredMoveTrace from "./features/triggered-move-trace.js";
import * as triggerTrace from "./features/trigger-trace.js";
import * as dslTrace from "./features/dsl-trace.js";
import * as dslCtorTrace from "./features/dsl-ctor-trace.js";
import * as gcProbe from "./features/gc-probe.js";
// hit-trace = Interceptor sur AttackDamageOperation$$ExecuteHit (chemin de dégât
// ULTRA-CHAUD) : le register n'arme RIEN, l'armement est on-demand (hitTraceArm).
import * as hitTrace from "./features/hit-trace.js";
// render-budget = pilotage A CHAUD du budget de rendu (le jeu est un hote de CALCUL, pas un objet
// a regarder). SEULE DEROGATION a la regle ci-dessus : ce register AUTO-ARME le bridage de CADENCE
// (vSync=0, 30 fps) a la 1re frame drainee. Ce n'est pas la classe de hook que l'incident du
// 2026-07-10 proscrit -- `set_vSyncCount`/`set_targetFrameRate` sont appeles au plus UNE FOIS PAR
// FRAME, hors du moteur de bataille, et le cout mesure sur le harnais est nul. Sans auto-arm le
// bridage mourait a chaque reinject, en silence (GPU 18,6 % -> 33 %, rien ne le signale).
// La RESOLUTION, elle, n'est jamais posee toute seule : elle survit au reinject, et `SetResolution`
// est le seul appel de ce module qui ait deja tue le process.
// Complementaire de `scripts/tacticus-screen-prefs.ps1`, qui regle la resolution AU DEMARRAGE
// (prefs Unity) et exige, lui, que le jeu soit ferme.
import * as renderBudget from "./features/render-budget.js";

export interface Ctx {
    rpc: Record<string, (...args: any[]) => unknown>;
}

import { dumpComponentFields } from "./probes/dump-comps.js";
import { dumpComponentMethods } from "./probes/dump-methods.js";
import { findActionComponent } from "./probes/find-action.js";
import { dumpAllComponents } from "./probes/list-comps.js";
import { dumpUnitFlagsFields } from "./probes/dump-flags.js";
import { introspectUnitFlags } from "./probes/introspect-flags.js";
import { searchAllClasses } from "./probes/search-classes.js";
import { debugFlagsType } from "./probes/debug-flags-type.js";
import { dumpPathfinderMethods } from "./probes/dump-pathfinder.js";
import { dumpPathfinderParams } from "./probes/dump-params.js";
import { dumpPathfinderReturn } from "./probes/dump-return.js";
import { findPathfindersOffset } from "./probes/find-pathfinder-off.js";
import { dumpRunnerFields } from "./probes/dump-runner-fields.js";
import { dumpStatComponents } from "./probes/dump-stats.js";
import { dumpAbilityFields } from "./probes/dump-ability.js";
import { dumpActiveAbilityProperly } from "./probes/dump-ability-properly.js";
import { dumpAbilityStateFields } from "./probes/dump-ability-state.js";
import { dumpUnitProgression } from "./probes/dump-unit-progression.js";
import { dumpUnitComponentFields } from "./probes/dump-unit-comp.js";
import { dumpWeaponsFields } from "./probes/dump-weapons.js";
import { dumpWeaponFields } from "./probes/dump-weapon-class.js";
import { dumpWeaponsCompTypes } from "./probes/dump-weapons-types.js";
import { dumpWeaponProfileFields } from "./probes/dump-weapon-profile.js";
import { dumpCritBlockComps } from "./probes/dump-crit-block.js";
import { dumpDamageProfileFields } from "./probes/dump-damage-profile.js";
import { dumpDamageProfileProperly } from "./probes/dump-dp-properly.js";
import { dumpWeaponProfileTypes } from "./probes/dump-wp-types.js";
import { dumpAttackDefense } from "./probes/dump-attack-defense.js";
import { dumpUnitEntityFields } from "./probes/dump-unit-entity.js";
import { dumpUnitEntityFields as dumpUnitEntityFieldsCore } from "./probes/dump-unit-entity-core.js";
import { dumpStatComponentFields } from "./probes/dump-stat-comp.js";
import { dumpStatCompTypes } from "./probes/dump-stat-types.js";
import { dumpValueOverrideFields } from "./probes/dump-value-override.js";
import { dumpExtraMaxDmg } from "./probes/dump-extra-dmg.js";
import { dumpProgressionExtensions } from "./probes/dump-prog-ext.js";
import { dumpUnitProgressionFields } from "./probes/dump-unit-prog-fields.js";
import { dumpUnitProgressionAnywhere } from "./probes/dump-prog-anywhere.js";
import { dumpUnitProgressionMethods } from "./probes/dump-unit-prog-methods.js";
import { dumpStatsFormulaMethods } from "./probes/dump-stats-formula.js";
import { dumpStatsFormulaFields } from "./probes/dump-stats-formula-fields.js";
import { findProgressionSingletons } from "./probes/find-prog-instances.js";
import { findD3Index } from "./probes/map-ranks.js";
import { checkGetMaxConfiguredRank } from "./probes/check-method.js";
import { checkParent } from "./probes/check-parent.js";
import { inspectInstance } from "./probes/inspect-instance.js";
import { checkKlass } from "./probes/check-klass.js";
import { dumpMethodInfo } from "./probes/dump-method-info.js";
import { checkInvokerExport } from "./probes/check-invoker.js";
import { dslNodeProbe, dslLazyProbe } from "./probes/dsl-node-probe.js";
import { dumpUnitProgressionDataFields } from "./probes/dump-unit-prog-data-fields.js";
import { dumpUnitProgDataNested } from "./probes/dump-unit-prog-data-nested.js";
import { testStatic } from "./probes/test-static.js";
import { dumpStatComponentFieldTypes } from "./probes/dump-stat-comp-types.js";
import { dumpUnitEntityFields as dumpUnitEntityFieldsV2 } from "./probes/dump-unit-entity-fields.js";
import { dumpUniverseFields } from "./probes/dump-universe.js";
import * as rlBridge from "./features/rl/bridge.js";
import { testSafeInvoke } from "./probes/test-safe-invoke.js";
import { findSingletonsViaGlobals } from "./probes/find-globals.js";
import { searchForGlobals } from "./probes/search-class.js";
import { inspectPtr } from "./probes/inspect-ptr.js";
import { checkMethodParams } from "./probes/check-method-params.js";
import { checkStatsFields } from "./probes/check-stats-fields.js";
// #916-r1 / #590-r2 / #590-r5 — capteurs d'INTROSPECTION PURE (aucun `Interceptor`, aucune
// invocation, aucun heap scan). Ils repondent aux illisibilites STATIQUES : un slot d'interface
// que le decompile ne designe que par un `(**(code **)(*plVar + N))()`, et la valeur d'un champ
// statique dont la classe n'a pas de `.cctor` nomme.
import { interfaceSlotProbe, classInterfaces } from "./probes/interface-slot-probe.js";
import { staticFieldProbe } from "./probes/static-field-probe.js";



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
    ctx.rpc.dumpUnitComp = () => dumpUnitComponentFields();
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
    ctx.rpc.dslNodeProbe = () => dslNodeProbe();
    ctx.rpc.dslLazyProbe = () => dslLazyProbe();
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

    rlBridge.register(ctx);

    /** RPC: Get battle log segment. */
    // movement-trace stays opt-in — its 39 Interceptor.attach hooks on
    // EvaluateMovementInSteps utilities each call 3× class_get_name and
    // produced visible navigation lag. Re-enable explicitly when AI movement
    // debugging is the active task. ai-trace L3 covers the same surface but
    // streams to disk instead of an in-memory ring; default L3=off so this
    // path stays cheap unless the user explicitly enables it.
    void movementTrace;
    [status, sim, cheat, modeSourceCapture, launch,
     unitAssetMap, /* movementTrace, */ unitVisualResolve, introspect,
     campaignBuilder, mowBuilder, aiTrace, aiUtilityTrace, simEngine,
     overwatchFix, bucketAudit, dumpComposed, dispatchObserve, whatifTrigger, autoBoot,
     uiNav, uiScroll, uiWindows, fsmInput, battleEvents, warmupSingletons, battleConfig, observe,
     dumpPvpBoards, normalizeBc, crashTrap, initTrace,
     // net-capture / ws-capture / ui-mutations : s'enregistrent SANS rien installer.
     // `ui-mutations` ancre un chemin CHAUD (GameObject.SetActive) — armé par `{start:true}`,
     // jamais autrement. `ws-capture` couvre le transport que `net-capture` ne PEUT pas voir :
     // le SyncPvp parle WebSocket, pas HTTP — armer `net-capture` dessus rendrait un journal
     // vide, qui se lirait « rien n'est parti ».
     // `expedition-board` lit le plateau d'Operations LA OU LA REPONSE EST APPLIQUEE : l'UI
     // est virtualisee (4 lignes visibles sur 7) et `net-capture` ne voit que le sortant.
     // `roster-owned` DEMANDE la possession au jeu (`UnitProgression$$HasUnitUnlocked`) au
     // lieu de la deduire d'un ecran : toutes alliances, sans navigation ni defilement.
     // `expedition-dispatch` est le SEUL de la famille qui ECRIVE : son RPC d'envoi refuse
     // sans `confirmer: true`, et l'armement n'installe que de l'OBSERVATION.
     // `gc-rendezvous` n'INSTALLE RIEN : il expose un RPC qui force une collecte, et qui
     // PEUT geler le jeu -- c'est ce qu'il mesure (#600). Il ne touche pas au compte.
     netCapture, wsCapture, expeditionBoard, rosterOwned, expeditionDispatch, uiMutations,
     gcRendezvous,
     // messageTrace AVANT winnerCapture — il SET `state.scoringRunnerId` / `state.applySeq`,
     // que winnerCapture LIT pour estampiller son event. (Le troisieme lecteur, move-options,
     // est parti avec le nettoyage : sa surface RPC etait morte et son register inerte.)
     messageTrace, winnerCapture,
     aiStep, abilityPrefs, modifierObserve,   // modifierObserve = diag on-demand (jamais auto-arme)
     scorerDamageTrace, effectBonusTrace, triggeredMoveTrace, triggerTrace, dslTrace, dslCtorTrace,
     // replayOutputStream = capteur on-demand (#477), n'arme rien au register.
     replayOutputStream,
     gcProbe, hitTrace, renderBudget]
        .forEach((f) => f.register(ctx));
}
