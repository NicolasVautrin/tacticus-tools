    // Scorer / utility / damage-modifier TRACE TOOLKIT — capture, during a FRESH scoring pass, exactly what
// the native AI computes per attack candidate: scorer damage, JOINT (tile,target) utility, tile-term,
// tile-leaf outputs, composite children, damage bonuses. A reusable agreement-debugging kit (NOT a one-shot).
//
// ═══ CAPTURE RECIPE (post multi-runner refacto #43 — 3 gotchas, sinon buffer VIDE) ═════════════════════
// Le helper Python `scripts/python/scorer_trace_capture.py::capture(seed, want=...)` encapsule ce flux —
// s'en servir plutot que de le re-deriver. Les 3 gotchas :
//   1. Runner isole : `rl_duel build --state-file data/X.json` (ROOT-ANCHORED, <repo>/data/) ; le runnerId
//      se lit DANS ce fichier JSON, pas dans stdout.
//   2. Traces = OriginBuffers PAR ORIGINE (#43, purge au dispose) : dumper avec `{runnerId: rid}`. Les RPC
//      ai-step posent `setTraceOrigin(runnerId)` ; sans le bon filtre le dump revient vide (hooks OK quand meme).
//   3. Les hooks (ctor + AllMods) ne firent que quand l'IA native SCORE vraiment (tour joué :
//      `aiStepDryRun`, ou l'`endturn` d'un joueur IA). `aiStepDryRun` ne score que l'action CHOISIE
//      (si l'IA choisit un move => AUCUN ctor d'attaque). Le `decisionView` du drive NE suffit PAS a
//      lui seul (chemin de prediction d'AFFICHAGE, + CachedDamagePrediction). => activer
//      `scorerDamageTraceOn` AVANT que le scenario tourne (p.ex. avant le drive) ET capter sur les
//      tours REELLEMENT joués. OBSERVE : un drive skewe vers les attaques ENNEMIES (scorees pendant
//      leurs endturn) ; capter l'attaque d'une unite AMIE precise demande que l'IA CHOISISSE cette
//      attaque (positionner pour que ce soit son meilleur coup). L'ancienne mention « during
//      aiStepDryRun » n'etait pas fausse mais incomplete (endturn IA score aussi).
// ═════════════════════════════════════════════════════════════════════════════════════════════════════
//
// ═══ ⚠ BUILD-SPECIFIC RVA HOOKS — REFRESH FROM DUMP ON EVERY HASH CHANGE ═══════════════════════════════
// Only ONE hook resolves cleanly across builds: `ProbableDamageEvent..ctor` (findMethod — the scorer damage,
// auto-armed at register). ALL the others (CalculateActionUtility, CalculateUtilityFromTilePrediction, the
// ElevationUtility / tile-leaf iterators, ComposedUtility.MoveNext, GetMultiplierFromDamageBonus) are gshared
// / iterator bodies that findMethod CANNOT resolve → hooked by HARDCODED RVA valid for hash `gqfc5mff6c` ONLY.
// On the next build these RVAs point to RANDOM code and Interceptor.attach would corrupt it, so they are
// ARMED LAZILY by `scorerDamageTraceOn` (installRvaHooks), NEVER auto-attached at register. Before re-arming
// on a new build: refresh every RVA_* constant + LEAF_HOOKS_VA from the fresh dump (search_symbols_by_name on
// the class → VA − 0x180000000, computed in code). cf. feedback_rva_transcription_from_va.
// ═════════════════════════════════════════════════════════════════════════════════════════════════════
//
// Choke point: `ProbableDamageEvent..ctor(IEntity target, DamagePredictionResult
// damagePrediction, Nullable<Fix64> probability, Nullable<Fix64> weight)` — EVERY
// playbook's MakeDamagePredictions (vtable+0x358) builds its events through this
// ctor. Hooking it passively during `aiStepDryRun` records exactly the (target,
// min/max health damage, hits) the scorer used per candidate — with CrushingStrike
// / Terrifying / all attacker+defender modifiers applied by the native.
//
// Struct (dump gqfc5mff6c, TypeDefIndex 12292):
//   ProbableDamageEvent { IEntity Target@0x0; DamagePredictionResult DamagePrediction@0x8;
//                         Fix64 Probability@0xC8; Fix64 Weight@0xD0 }
//   DamagePredictionResult : CurrentHealth@0, Armor@4, Shield@8,
//     AccurateHealthDamage(Min@0x60,Max@0x64), TotalDamage(Min@0x90,Max@0x94), AppliedHits@0xBC.
//   IEntity : id@+0x10 (BEntityId 4B), type@+0x14 (EntityType).
//
// Gated by `trace.on` (default OFF — the ctor also fires during live game AI). The findMethod ctor hook is
// auto-armed at register (buffer gated); the RVA hooks arm on first `scorerDamageTraceOn`.
// RPC: scorerDamageTrace{On,Off,Clear,Dump} + scorer{Util,TileTerm,Elev,Leaf,Bonus}TraceDump + scorerComposedDump.

import { Ctx } from "../controller.js";
import { findClassAnywhere, findMethod, il2cppBase, class_get_name, s } from "../il2cpp/helpers.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { getTraceOrigin, OriginBuffers } from "../game/trace-origin.js";
import { readTileCoord } from "./ai-step/internals.js";

// Attribution runner : les buffers sont SÉPARÉS PAR ORIGINE (OriginBuffers =
// Map originRunnerId → bucket, null = IA live ; CAP par bucket, éviction
// dropNew = comportement historique). Chaque event porte aussi
// `originRunnerId`. Dumps : `runnerId` → bucket direct ; sans → concat
// toutes origines (ordre seq). Clear scopable par `runnerId` ; le dispose
// d'un runner purge ses buckets automatiquement (cf. game/trace-origin.ts).

// Cap PAR BUCKET (par origine) de chaque famille de buffers ci-dessous.
const CAP = 4000;

// ComposedUtility.<EvaluateMovementInSteps>d__8.MoveNext — RVA gqfc5mff6c (@181101600 - base). Le
// composite Tile(7) est un ComposedUtility qui SOMME ses enfants (liste List<IUtility> @ this+0x18,
// this = d__8+0x20). On énumère les noms de classe des enfants (une fois par instance `this`) pour
// IDENTIFIER de façon déterministe la feuille -25 (plutôt que hooker feuille par feuille). À REFAIRE au hash.
const RVA_COMPOSED_UTILITY = 0x1101600;

// DamageCalculations.GetMultiplierFromDamageBonus @181005210 (RVA 0x1005210) — convertit un bonus %
// (Nullable<int> @ param_3+0x20) en multiplicateur (>0: 1+b/100 ; <0: 1-|b|/100). Signature :
// (ret*, p2, param_3). Hooké pour CAPTURER chaque bonus appliqué pendant la prédiction (le +50 sur 82,
// le -30 Terrifying sur 78) + backtrace pour distinguer ATTAQUANT (CalculateAttackerModifiers @181000590)
// vs DÉFENSEUR (CalculateDefenderModifiers @181002c30/a70). À REFAIRE au changement de hash.
// Deux variantes (instanciations génériques) : @181005210 (concrète, refcount 10) + @1810053e0 (refcount 3).
const RVA_GET_MULT_DMG_BONUS: number[] = [0x1005210, 0x10053e0];

// CalculateActionUtility (gshared, non résolu par findMethod) — RVA build-spécifique gqfc5mff6c
// (ghidra @181406ee0 - 0x180000000). Donne l'UTILITÉ TOTALE par-candidat (le discriminateur : le
// dégât seul ne suffit pas). Signature : (ret Nullable<Fix64>*, this, p3, position UnitPosition,
// p5, ability*, ...). À REFAIRE au changement de hash.
const RVA_CALC_ACTION_UTILITY = 0x1406ee0;

// ElevationUtility.<EvaluateMovementInSteps>d__8.MoveNext (itérateur, non résolu par findMethod)
// — RVA build-spécifique gqfc5mff6c (ghidra @1811019a0 - 0x180000000). Confirme la feuille Elevation :
// valeur d'élévation NATIVE de la tuile candidate (util+0x6c), max (util+0x60) / min (util+0x64) du
// DOMAINE PERTINENT, et la sortie de feuille yieldée (d__8+0x18, Fix64). d__8+0x20 = l'ElevationUtility ;
// d__8+0x28 = la position candidate (MainTile via +0x18). À REFAIRE au changement de hash.
const RVA_ELEVATION_LEAF = 0x11019a0;

// ComparablePlaybook.CalculateUtilityFromTilePrediction (gshared) — RVA build-spécifique gqfc5mff6c
// (ghidra @181408740 - 0x180000000). Retourne le TERME DE TUILE COMPLET (composite Tile(7) = SOMME des
// 29 feuilles, pas seulement Elevation) par candidat, en Fix64 (RAX). Appelée DANS CalculateActionUtility
// → on tague le retour avec curCaster déjà posé. Sépare damage-util de tile-term (départage le +24).
// À REFAIRE au changement de hash.
const RVA_CALC_TILE_PRED = 0x1408740;

interface UtilEvent {
    seq: number;
    originRunnerId: number | null;   // runner du RPC déclencheur (null = IA live)
    casterCol: number;
    casterRow: number;
    targets: number[];   // cibles des ProbableDamageEvents produits dans CET appel
    utility: number;     // Fix64 -> nombre
    hasValue: number;
    stack?: string[];    // backtrace (offsets rel. il2cppBase) — 1ers events seulement
}
const utilTrace: {
    buf: OriginBuffers<UtilEvent>; targets: number[]; stacksLeft: number;
} = { buf: new OriginBuffers<UtilEvent>(CAP, "dropNew"),
      targets: [], stacksLeft: 0 };

interface ElevEvent {
    seq: number;
    originRunnerId: number | null;
    col: number;
    row: number;
    elev: number;   // valeur composant Elevation NATIVE de la tuile candidate (util+0x6c)
    max: number;    // max du domaine pertinent (util+0x60)
    min: number;    // min du domaine pertinent (util+0x64)
    leaf: number;   // sortie de feuille yieldée (d__8+0x18, Fix64 -> nombre)
    stack?: string[];  // backtrace (1ers events) -> révèle l'AGRÉGATEUR qui somme les feuilles
}
const elevTrace: { buf: OriginBuffers<ElevEvent>; stacksLeft: number } =
    { buf: new OriginBuffers<ElevEvent>(CAP, "dropNew"), stacksLeft: 0 };

interface TileTermEvent {
    seq: number;
    originRunnerId: number | null;
    casterCol: number;
    casterRow: number;
    tileTerm: number;   // composite Tile(7) COMPLET (retour Fix64 de CalculateUtilityFromTilePrediction)
}
const tileTermTrace: { buf: OriginBuffers<TileTermEvent> } =
    { buf: new OriginBuffers<TileTermEvent>(CAP, "dropNew") };

// Capture générique de la SORTIE d'une feuille de tuile situationnelle (itérateur *Utility.<d__N>.MoveNext).
// Layout itérateur : yielded Fix64 @ d__+0x18 ; utility @ d__+0x20 ou +0x28 ; position candidate à
// posOff (décodée en MainTile via +0x18). Sert à IDENTIFIER la feuille -25 active sur (5,3).
interface LeafEvent {
    seq: number;
    originRunnerId: number | null;
    leaf: string;   // label de la feuille (ex. "TileEffects", "Contaminated")
    col: number;
    row: number;
    value: number;  // sortie de feuille yieldée (significative seulement si ret==1)
    ret: number;    // retour MoveNext (1=valeur fraîche, 0=fin/gate) — voir quels enfants sont appelés
}
const leafTrace: { buf: OriginBuffers<LeafEvent> } =
    { buf: new OriginBuffers<LeafEvent>(CAP, "dropNew") };

// Énumération des enfants des composites vus (dédup par ptr `this`). key = ptr hex, val = [classNames].
const composedChildren: { seen: Map<string, string[]> } = { seen: new Map() };

interface BonusEvent {
    seq: number;
    originRunnerId: number | null;
    bonus: number;       // valeur du bonus % (param_3+0x20 Nullable<int>) — +50, -30, …
    hasValue: number;
    casterCol: number;   // tuile caster courante (via CalculateActionUtility) — corrèle le CS tile-dépendant
    casterRow: number;
    stack?: string[];    // backtrace -> ATTAQUANT (CalcAttackerModifiers) vs DÉFENSEUR (CalcDefenderModifiers)
}
const bonusTrace: { buf: OriginBuffers<BonusEvent>; stacksLeft: number } =
    { buf: new OriginBuffers<BonusEvent>(CAP, "dropNew"), stacksLeft: 0 };
// Capture GÉNÉRIQUE de la sortie yieldée d'une feuille de tuile (*Utility.<d__N>.MoveNext). Machinerie
// réutilisable : `scorerLeafTraceDump` donne la valeur + tuile candidate par feuille hookée. Set par
// DÉFAUT minimal (TileEffects = la feuille -25 identifiée + CapturePoint = contrôle connu-firing) ;
// pour investiguer d'autres feuilles, énumérer d'abord les enfants d'un composite via `scorerComposedDump`
// puis AJOUTER ici les VA voulues (VA COMPLÈTE ghidra → RVA = va − base, en code, cf. la transcription
// 0x1810fXXXX → 0x10fXXXX). ⚠ NE PAS dépasser ~10 hooks à la fois (35 = cctor cascade → détache la
// session) NI hooker des feuilles CHAUDES (distances MinDist/MaxDist/TileDistance : PAS enfants du
// composite Tile de toute façon). La position candidate est décodée par essai d'offsets (0x28/0x20).
const IL2CPP_VA_BASE = 0x180000000;
const LEAF_HOOKS_VA: Array<[number, string]> = [
    [0x1810fbe50, "TileEffects"],       // la feuille -25 (Thorns_DefenseReduction) — cf. this session
    [0x1811000a0, "CapturePointTile"],  // contrôle : connue-firing (sanity du mécanisme de hook)
];
const LEAF_HOOKS: Array<[number, string]> =
    LEAF_HOOKS_VA.map(([va, label]) => [va - IL2CPP_VA_BASE, label]);
const LEAF_POS_OFFSETS = [0x28, 0x20];

interface DmgEvent {
    seq: number;
    originRunnerId: number | null;
    targetId: number;
    targetType: number;
    curHealth: number;
    healthMin: number;
    healthMax: number;
    // AccurateShieldDamage @0x78 (MinMaxDamage Min@+8/Max@+0xc, dump.cs TypeDefIndex 11757) —
    // consommé par DamageUtility.MoveNext @1810e2280 (D = hAvg + sAvg). + LimitedByMinHp @0xB0
    // (si set, GetHealthDamage @1810cec60 retourne CurrentHealth entier).
    shieldMin: number;
    shieldMax: number;
    limitedByMinHp: number;
    hits: number;
    // Tuile caster du candidat (via MakeDamagePredictions param_3=position) — le nerf de
    // CrushingStrike (+50% mêlée si non-bougé) dépend de si cette tuile == pos courante du caster.
    casterCol: number;
    casterRow: number;
}

// Position caster du candidat courant, posée par le hook MakeDamagePredictions onEnter et lue par
// le ctor ProbableDamageEvent qui suit immédiatement (1 MakeDamagePredictions -> ses events).
let curCaster: { col: number; row: number } | null = null;

const trace: { on: boolean; seq: number; buf: OriginBuffers<DmgEvent> } = {
    on: false, seq: 0, buf: new OriginBuffers<DmgEvent>(CAP, "dropNew"),
};

// DamagePrediction.CalculateBaseDamageWithAllModifiers @18102d3f0 (méthode NOMMÉE, findMethod —
// survit au hash) : (this, int baseDamage, IEntity attacker, IEntity defender, DamageProfile,
// Nullable<DamageModifiers> att, Nullable<DamageModifiers> def, bool isCrit, bool isMelee) → Fix64.
// Capture (baseDamage, isCrit, isMelee, retour Fix64, call-site via returnAddress) par appel pendant
// aiStepDryRun → tranche le chemin santé par-coup des SPÉCIALES (÷hits ? crit du bout max ?).
interface AllModsEvent {
    seq: number;
    originRunnerId: number | null;
    input: number;      // baseDamage int (args[1])
    isCrit: number;
    isMelee: number;
    out: number;        // retour Fix64 -> nombre
    site: string;       // returnAddress rel. il2cppBase (hex) — distingue les call sites min/max
    casterCol: number;
    casterRow: number;
}
const allModsTrace: { buf: OriginBuffers<AllModsEvent> } =
    { buf: new OriginBuffers<AllModsEvent>(CAP, "dropNew") };
let allModsInstalled = false;
function installAllModsHook(): boolean {
    if (allModsInstalled) return true;
    const klass = findClassAnywhere("IdunBattle.Core.Services", "DamagePrediction");
    if (!klass) { log("[scorer-trace] DamagePrediction class not found"); return false; }
    const mi = findMethod(klass, "CalculateBaseDamageWithAllModifiers");
    if (!mi || mi.ptr.isNull()) { log("[scorer-trace] CalculateBaseDamageWithAllModifiers not resolved"); return false; }
    Interceptor.attach(mi.ptr, {
        onEnter(args) {
            if (!trace.on) return;
            const self = this as { _in?: number; _crit?: number; _melee?: number; _site?: string; _on?: boolean };
            self._on = true;
            self._in = args[1].toInt32();
            self._crit = args[7].toInt32() & 0xff;
            self._melee = args[8].toInt32() & 0xff;
            try {
                const off = this.returnAddress.sub(il2cppBase);
                self._site = "il2cpp+0x" + off.toString(16);
            } catch { self._site = "?"; }
        },
        onLeave(retval) {
            const self = this as { _in?: number; _crit?: number; _melee?: number; _site?: string; _on?: boolean };
            if (!self._on || !trace.on) return;
            try {
                let raw = BigInt(retval.toString());
                if (raw >= (1n << 63n)) raw -= (1n << 64n);
                allModsTrace.buf.push({
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    input: self._in ?? -1, isCrit: self._crit ?? -1, isMelee: self._melee ?? -1,
                    out: Number(raw) / 4294967296,
                    site: self._site ?? "?",
                    casterCol: curCaster ? curCaster.col : -1,
                    casterRow: curCaster ? curCaster.row : -1,
                });
            } catch { /* transient — skip */ }
        },
    });
    allModsInstalled = true;
    log("[scorer-trace] hooked CalculateBaseDamageWithAllModifiers @ " + mi.ptr);
    return true;
}

let installed = false;
function installHook(): boolean {
    if (installed) return true;
    const klass = findClassAnywhere("IdunBattle.AI.Playbook", "ProbableDamageEvent");
    if (!klass) { log("[scorer-trace] ProbableDamageEvent class not found"); return false; }
    const ctor = findMethod(klass, ".ctor");
    if (!ctor || ctor.ptr.isNull()) { log("[scorer-trace] .ctor not resolved"); return false; }
    Interceptor.attach(ctor.ptr, {
        onEnter(args) {
            if (!trace.on) return;
            try {
                const target = args[1];
                const dpr = args[2];            // DamagePredictionResult*
                if (target.isNull() || dpr.isNull()) return;
                const targetId = target.add(0x10).readS32();
                utilTrace.targets.push(targetId);   // corrélation: cible de CET event -> l'appel util courant
                trace.buf.push({
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    targetId,
                    targetType: target.add(0x14).readS32(),
                    curHealth: dpr.readS32(),
                    healthMin: dpr.add(0x60).readS32(),
                    healthMax: dpr.add(0x64).readS32(),
                    shieldMin: dpr.add(0x80).readS32(),
                    shieldMax: dpr.add(0x84).readS32(),
                    limitedByMinHp: dpr.add(0xb0).readU8(),
                    hits: dpr.add(0xbc).readS32(),
                    casterCol: curCaster ? curCaster.col : -1,
                    casterRow: curCaster ? curCaster.row : -1,
                });
            } catch { /* transient — skip */ }
        },
    });
    installed = true;
    log("[scorer-trace] hooked ProbableDamageEvent..ctor @ " + ctor.ptr);
    return true;
}

// ⚠ RVA BUILD-SPÉCIFIQUES — attaches DIFFÉRÉES (armées seulement par scorerDamageTraceOn, PAS au register).
// Toutes les fonctions ci-dessous sont gshared / itérateurs → NON résolubles par findMethod → hookées par
// RVA hardcodée valide UNIQUEMENT pour le hash `gqfc5mff6c`. Au prochain changement de build, ces RVA
// pointent du CODE ALÉATOIRE et `Interceptor.attach` corromprait le prologue → on N'ATTACHE PAS au register
// (le ctor findMethod ci-dessus, lui, survit au hash et reste auto-armé). RAFRAÎCHIR CES RVA DEPUIS LE DUMP
// À CHAQUE CHANGEMENT DE HASH avant de ré-armer. cf. feedback_rva_transcription_from_va.
let rvaInstalled = false;
function installRvaHooks(): boolean {
    if (rvaInstalled) return true;
    log("[scorer-trace] ⚠ arming BUILD-SPECIFIC RVA hooks (valid for hash gqfc5mff6c ONLY — "
        + "refresh RVAs from dump on hash change)");
    installUtilHook();
    installElevHook();
    installTileTermHook();
    installLeafHooks();
    installComposedHook();
    installBonusHook();
    rvaInstalled = true;
    return true;
}

// RVA hook sur la feuille Elevation (itérateur MoveNext) — confirme valeur d'élévation native +
// max/min du domaine pertinent + sortie de feuille, par tuile candidate. Tranche le mystère
// (terme de tuile 26/31/21 non-multiple-de-5 : la feuille ne produit que des multiples de 5).
let elevInstalled = false;
function installElevHook(): boolean {
    if (elevInstalled) return true;
    if (il2cppBase.isNull()) { log("[scorer-trace] il2cppBase null — elev hook skipped"); return false; }
    const ptrFn = il2cppBase.add(RVA_ELEVATION_LEAF);
    Interceptor.attach(ptrFn, {
        onEnter(args) {
            const self = this as { _d8?: NativePointer; _stk?: string[] };
            self._d8 = args[0];
            // Backtrace (1ers events) -> révèle l'AGRÉGATEUR qui somme les feuilles de tuile.
            if (trace.on && elevTrace.stacksLeft > 0) {
                try {
                    self._stk = Thread.backtrace(this.context, Backtracer.ACCURATE)
                        .slice(0, 20)
                        .map((a) => {
                            const off = a.sub(il2cppBase);
                            return (off.compare(0) > 0 && off.compare(il2cppBase) < 0)
                                ? "il2cpp+0x" + off.toString(16) : a.toString();
                        });
                } catch { self._stk = undefined; }
            }
        },
        onLeave(retval) {
            if (!trace.on) return;
            // yield=1 -> MoveNext a calculé une valeur fraîche (d__8+0x18) ; 0 -> fin d'itération (stale).
            if (retval.toInt32() !== 1) return;
            try {
                const d8 = (this as { _d8?: NativePointer })._d8;
                if (!d8 || d8.isNull()) return;
                const util = d8.add(0x20).readPointer();
                if (util.isNull()) return;
                const elev = util.add(0x6c).readS32();
                const mx = util.add(0x60).readS32();
                const mn = util.add(0x64).readS32();
                const leaf = Number(BigInt(d8.add(0x18).readS64().toString())) / 4294967296;
                // position candidate : *(d__8+0x28) -> objet, MainTile via +0x18 (cf. décompilé).
                let col = -1, row = -1;
                try {
                    const posObj = d8.add(0x28).readPointer();
                    if (!posObj.isNull()) {
                        const c = decodePos(posObj.add(0x18));
                        if (c) { col = c.col; row = c.row; }
                    }
                } catch { /* col/row optionnel */ }
                const ev: ElevEvent = { seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    col, row, elev, max: mx, min: mn, leaf };
                const stk = (this as { _stk?: string[] })._stk;
                if (stk) { ev.stack = stk; elevTrace.stacksLeft--; }
                elevTrace.buf.push(ev);
            } catch { /* transient — skip */ }
        },
    });
    elevInstalled = true;
    log("[scorer-trace] hooked ElevationUtility leaf (RVA) @ " + ptrFn);
    return true;
}

// RVA hook sur CalculateUtilityFromTilePrediction — capture le TERME DE TUILE COMPLET (composite Tile(7))
// par candidat. Appelée DANS CalculateActionUtility (curCaster déjà posé). Départage : si tile-term ==
// feuille Elevation (50/30/20) → le +24 est dans le DÉGÂT ; sinon une autre feuille de tuile est active.
let tileTermInstalled = false;
function installTileTermHook(): boolean {
    if (tileTermInstalled) return true;
    if (il2cppBase.isNull()) { log("[scorer-trace] il2cppBase null — tileTerm hook skipped"); return false; }
    const ptrFn = il2cppBase.add(RVA_CALC_TILE_PRED);
    Interceptor.attach(ptrFn, {
        onLeave(retval) {
            if (!trace.on) return;
            try {
                // Fix64 (int64 signé) retourné dans RAX. retval = valeur brute (NativePointer).
                let raw = BigInt(retval.toString());
                if (raw >= (1n << 63n)) raw -= (1n << 64n);   // signe
                const tt = Number(raw) / 4294967296;
                tileTermTrace.buf.push({
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    casterCol: curCaster ? curCaster.col : -1,
                    casterRow: curCaster ? curCaster.row : -1,
                    tileTerm: tt,
                });
            } catch { /* transient — skip */ }
        },
    });
    tileTermInstalled = true;
    log("[scorer-trace] hooked CalculateUtilityFromTilePrediction (RVA) @ " + ptrFn);
    return true;
}

// RVA hooks sur les feuilles candidates au -25 (TileEffects, Contaminated) — capture leur sortie
// yieldée par tuile candidate pour IDENTIFIER laquelle est la feuille -25 active sur (5,3).
let leafInstalled = false;
function installLeafHooks(): boolean {
    if (leafInstalled) return true;
    if (il2cppBase.isNull()) { log("[scorer-trace] il2cppBase null — leaf hooks skipped"); return false; }
    for (const [rva, label] of LEAF_HOOKS) {
        const ptrFn = il2cppBase.add(rva);
        Interceptor.attach(ptrFn, {
            onEnter(args) {
                (this as { _d?: NativePointer })._d = args[0];
            },
            onLeave(retval) {
                if (!trace.on) return;
                const ret = retval.toInt32();
                try {
                    const d = (this as { _d?: NativePointer })._d;
                    if (!d || d.isNull()) return;
                    const value = Number(BigInt(d.add(0x18).readS64().toString())) / 4294967296;
                    // Position candidate : selon le layout d'itérateur, l'objet-position est à +0x28 ou
                    // +0x20 (Contaminated inversé). On essaie les deux, MainTile via +0x18.
                    let col = -1, row = -1;
                    for (const off of LEAF_POS_OFFSETS) {
                        try {
                            const posObj = d.add(off).readPointer();
                            if (posObj.isNull()) continue;
                            const c = decodePos(posObj.add(0x18));
                            if (c) { col = c.col; row = c.row; break; }
                        } catch { /* essayer l'offset suivant */ }
                    }
                    leafTrace.buf.push({ seq: ++trace.seq,
                        originRunnerId: getTraceOrigin(),
                        leaf: label, col, row, value, ret });
                } catch { /* transient — skip */ }
            },
        });
        log("[scorer-trace] hooked leaf " + label + " (RVA) @ " + ptrFn);
    }
    leafInstalled = true;
    return true;
}

// RVA hook sur ComposedUtility.MoveNext — énumère les enfants (List<IUtility> @ this+0x18) de chaque
// composite (dédup par ptr this). Identifie les feuilles réellement présentes dans le composite Tile.
let composedInstalled = false;
function installComposedHook(): boolean {
    if (composedInstalled) return true;
    if (il2cppBase.isNull()) { log("[scorer-trace] il2cppBase null — composed hook skipped"); return false; }
    const ptrFn = il2cppBase.add(RVA_COMPOSED_UTILITY);
    Interceptor.attach(ptrFn, {
        onEnter(args) {
            if (!trace.on) return;
            try {
                const self = args[0].add(0x20).readPointer();   // d__8+0x20 = this (ComposedUtility)
                if (self.isNull()) return;
                const key = self.toString();
                if (composedChildren.seen.has(key)) return;      // une fois par instance
                const list = self.add(0x18).readPointer();        // children List<IUtility>
                if (list.isNull()) return;
                const items = list.add(0x10).readPointer();       // T[] backing
                const count = list.add(0x18).readS32();           // _size
                const names: string[] = [];
                if (!items.isNull() && count > 0 && count < 64) {
                    for (let i = 0; i < count; i++) {
                        const child = items.add(0x20 + i * 8).readPointer();
                        if (child.isNull()) { names.push("<null>"); continue; }
                        try {
                            const klass = child.readPointer();
                            names.push(s(class_get_name(klass) as NativePointer));
                        } catch { names.push("<?>"); }
                    }
                }
                composedChildren.seen.set(key, names);
            } catch { /* transient — skip */ }
        },
    });
    composedInstalled = true;
    log("[scorer-trace] hooked ComposedUtility.MoveNext (RVA) @ " + ptrFn);
    return true;
}

// RVA hook sur GetMultiplierFromDamageBonus — capture chaque bonus % appliqué + backtrace (source
// attaquant/défenseur) + tuile caster. Identifie la source du +50 sur 82 (CS ? défenseur ?) sans deviner.
let bonusInstalled = false;
function installBonusHook(): boolean {
    if (bonusInstalled) return true;
    if (il2cppBase.isNull()) { log("[scorer-trace] il2cppBase null — bonus hook skipped"); return false; }
    for (const rva of RVA_GET_MULT_DMG_BONUS) {
    const ptrFn = il2cppBase.add(rva);
    Interceptor.attach(ptrFn, {
        onEnter(args) {
            if (!trace.on) return;
            try {
                const p3 = args[2];   // param_3 : porte le Nullable<int> bonus @ +0x20
                if (p3.isNull()) return;
                // Nullable<int> layout IL2CPP : value@0x0, hasValue@0x4 (relatif à p3+0x20).
                const bonus = p3.add(0x20).readS32();
                const hasValue = p3.add(0x24).readU8();
                if (!hasValue) return;   // pas de bonus -> multiplicateur nul (skip)
                const ev: BonusEvent = {
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    bonus, hasValue,
                    casterCol: curCaster ? curCaster.col : -1,
                    casterRow: curCaster ? curCaster.row : -1,
                };
                if (bonusTrace.stacksLeft > 0) {
                    try {
                        ev.stack = Thread.backtrace(this.context, Backtracer.ACCURATE)
                            .slice(0, 12)
                            .map((a) => {
                                const off = a.sub(il2cppBase);
                                return (off.compare(0) > 0 && off.compare(il2cppBase) < 0)
                                    ? "il2cpp+0x" + off.toString(16) : a.toString();
                            });
                        bonusTrace.stacksLeft--;
                    } catch { /* */ }
                }
                bonusTrace.buf.push(ev);
            } catch { /* transient — skip */ }
        },
    });
    log("[scorer-trace] hooked GetMultiplierFromDamageBonus (RVA) @ " + ptrFn);
    }
    bonusInstalled = true;
    return true;
}

// Décode une UnitPosition (args = valeur 8B {IList Tiles} OU ptr vers) -> tuile MainTile col/row.
function decodePos(a: NativePointer): { col: number; row: number } | null {
    try {
        for (const list of [a, a.readPointer()]) {
            if (list.isNull()) continue;
            const items = list.add(0x10).readPointer();
            const size = list.add(0x18).readS32();
            if (items.isNull() || size <= 0 || size > 32) continue;
            const tile = items.add(0x20).readPointer();
            if (tile.isNull()) continue;
            const c = readTileCoord(tile);
            if (c.col >= 0 && c.row >= 0) return c;
        }
    } catch { /* */ }
    return null;
}

// RVA hook sur CalculateActionUtility (gshared) — UTILITÉ TOTALE par-candidat + tuile caster (param_4)
// + corrélation cibles (les ProbableDamageEvents produits dans l'appel). onLeave lit le retour
// Nullable<Fix64> (param_1). Le discriminateur du pick (dégât seul insuffisant) est ICI.
let utilInstalled = false;
function installUtilHook(): boolean {
    if (utilInstalled) return true;
    if (il2cppBase.isNull()) { log("[scorer-trace] il2cppBase null — util hook skipped"); return false; }
    const ptrFn = il2cppBase.add(RVA_CALC_ACTION_UTILITY);
    Interceptor.attach(ptrFn, {
        onEnter(args) {
            if (!trace.on) return;
            // args = [ret Nullable<Fix64>*, this, p3, position, p5, ability*, ...].
            const self = this as { _ret?: NativePointer; _on?: boolean; _stk?: string[] };
            self._ret = args[0];
            self._on = true;
            curCaster = decodePos(args[3]);
            utilTrace.targets = [];
            // Backtrace (1ers events) : comprendre QUI appelle CalculateActionUtility et où se
            // fait la sélection (argmax / bucket / tri). Offsets rel. il2cppBase -> résoluble ghidra.
            if (utilTrace.stacksLeft > 0) {
                try {
                    self._stk = Thread.backtrace(this.context, Backtracer.ACCURATE)
                        .slice(0, 16)
                        .map((a) => {
                            const off = a.sub(il2cppBase);
                            return (off.compare(0) > 0 && off.compare(il2cppBase) < 0)
                                ? "il2cpp+0x" + off.toString(16) : a.toString();
                        });
                } catch { self._stk = undefined; }
            }
        },
        onLeave() {
            const self = this as { _ret?: NativePointer; _on?: boolean; _stk?: string[] };
            if (!self._on || !trace.on) return;
            try {
                const ret = self._ret;
                if (!ret || ret.isNull()) return;
                // Nullable<Fix64> layout à confirmer : on capte les DEUX candidats Fix64 (@0 et @8).
                const raw0 = Number(BigInt(ret.readS64().toString())) / 4294967296;
                const raw8 = Number(BigInt(ret.add(8).readS64().toString())) / 4294967296;
                const ev: UtilEvent = {
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    casterCol: curCaster ? curCaster.col : -1,
                    casterRow: curCaster ? curCaster.row : -1,
                    targets: utilTrace.targets.slice(),
                    utility: raw8,     // hypothèse : value@8 (fractionnaire observé)
                    hasValue: raw0,    // debug : l'autre candidat
                };
                if (self._stk) { ev.stack = self._stk; utilTrace.stacksLeft--; }
                utilTrace.buf.push(ev);
            } catch { /* */ }
            curCaster = null;
        },
    });
    utilInstalled = true;
    log("[scorer-trace] hooked CalculateActionUtility (RVA) @ " + ptrFn);
    return true;
}

export function register(ctx: Ctx): void {
    // Auto-arm UNIQUEMENT le hook sûr (ProbableDamageEvent.ctor via findMethod, survit au hash). Les hooks
    // RVA build-spécifiques sont armés à la demande par scorerDamageTraceOn (cf. installRvaHooks).
    installHook();   // buffer reste gated par trace.on (défaut false)

    ctx.rpc.scorerDamageTraceOn = (): Promise<unknown> =>
        queueOnMainThread(() => {
            const ok = installHook();
            installAllModsHook();   // findMethod (nommé) — survit au hash
            installRvaHooks();   // arme les RVA build-spécifiques (l'utilisateur confirme le hash en armant)
            trace.on = ok;
            return { ok, on: trace.on, installed, rvaInstalled, allModsInstalled };
        });

    ctx.rpc.scorerDamageTraceOff = (): unknown => {
        trace.on = false;
        return { ok: true, bufferSize: trace.buf.size() };
    };

    ctx.rpc.scorerDamageTraceClear = (
        body?: { stacks?: number; runnerId?: number },
    ): unknown => {
        // runnerId → clear SCOPÉ (drop du bucket de CE runner, les captures
        // des autres acteurs et du live survivent) ; sans → clear GLOBAL.
        const rid = body?.runnerId;
        trace.buf.clear(rid); utilTrace.buf.clear(rid);
        elevTrace.buf.clear(rid); tileTermTrace.buf.clear(rid);
        leafTrace.buf.clear(rid); bonusTrace.buf.clear(rid);
        allModsTrace.buf.clear(rid);
        if (typeof rid !== "number") {
            trace.seq = 0; utilTrace.targets = [];
            composedChildren.seen.clear();
        }
        utilTrace.stacksLeft = body?.stacks ?? 6;   // capture les N 1res backtraces après clear
        elevTrace.stacksLeft = body?.stacks ?? 6;   // idem pour la feuille Elevation (-> agrégateur)
        bonusTrace.stacksLeft = body?.stacks ?? 6;   // idem pour les bonus de dégât (-> source att/def)
        return { ok: true, stacksLeft: utilTrace.stacksLeft };
    };

    /** Dump per-candidate ELEVATION leaf (valeur native + max/min domaine pertinent + sortie feuille). */
    ctx.rpc.scorerElevTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            on: trace.on, elevInstalled,
            bufferSize: elevTrace.buf.size(),
            entries: elevTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump per-candidate TILE-TERM COMPLET (composite Tile(7) via CalculateUtilityFromTilePrediction). */
    ctx.rpc.scorerTileTermTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            on: trace.on, tileTermInstalled,
            bufferSize: tileTermTrace.buf.size(),
            entries: tileTermTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump per-candidate SORTIE des feuilles situationnelles hookées (TileEffects/Contaminated). */
    ctx.rpc.scorerLeafTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            on: trace.on, leafInstalled,
            bufferSize: leafTrace.buf.size(),
            entries: leafTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump les bonus de dégât capturés (valeur % + tuile caster + backtrace source att/def). */
    ctx.rpc.scorerBonusTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            on: trace.on, bonusInstalled,
            bufferSize: bonusTrace.buf.size(),
            entries: bonusTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump les enfants (noms de classe) de chaque ComposedUtility vu — identifie les feuilles du composite. */
    ctx.rpc.scorerComposedDump = (): unknown => {
        const composites = Array.from(composedChildren.seen.entries())
            .map(([ptr, children]) => ({ ptr, count: children.length, children }));
        return { on: trace.on, composedInstalled, composites };
    };

    /** Dump des appels CalculateBaseDamageWithAllModifiers (input/isCrit/isMelee/output/site). */
    ctx.rpc.scorerAllModsTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            on: trace.on, allModsInstalled,
            bufferSize: allModsTrace.buf.size(),
            entries: allModsTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump per-candidate TOTAL utility (CalculateActionUtility) — le discriminateur du pick. */
    ctx.rpc.scorerUtilTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            on: trace.on, utilInstalled,
            bufferSize: utilTrace.buf.size(),
            entries: utilTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump captured events. Body: { since?: seq, max?: number }. */
    ctx.rpc.scorerDamageTraceDump = (
        body?: { since?: number; max?: number; runnerId?: number },
    ): unknown => {
        const since = body?.since ?? 0;
        const max = body?.max ?? 2000;
        let filtered = trace.buf.entries(body?.runnerId);
        if (since > 0) filtered = filtered.filter((e) => e.seq > since);
        return {
            on: trace.on, installed, totalSeq: trace.seq,
            bufferSize: trace.buf.size(), returned: Math.min(filtered.length, max),
            entries: filtered.slice(-max),
        };
    };
}
