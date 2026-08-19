// Modifier-layer observation — diagnostic PERMANENT on-demand de la chaîne de
// dégât (prédiction ET combat), JAMAIS auto-armé (voir register()). C'est
// l'outil de DÉCOMPOSITION PAR ÉTAGE côté prédiction (doctrine CLAUDE.md
// « divergence de dégât = décomposition, jamais fit de scalaire ») :
//   armer (modifierObserveInstall) → reset → déclencher le calcul natif
//   (aiPlayByUnit = le tour de décision IA remplit le cache de prédiction EN
//   ÉTANT observé — c'est LA fenêtre de mesure fiable, cf. #96/#98 : aiPredict
//   seul sert le cache/le preview, pas le playbook) → modifierObserveStatus.
// Étages exposés : baseDmgPierced (bouts per-coup post-perçage) · multDumps
// (chaque multiplicateur composé — la décomposition du ×k) · predCalcDumps
// (application des mods côté prédiction) · calcDmgDumps (côté combat) ·
// bonusDumps (attribution par effet) · varLevelDumps (résolution des variables
// d'ability niveau×mult) · hitDmgDumps (roll combat par coup).
//
// Context: `DamageCalculations.CalculateAttackerModifiersForPrediction`,
// `CalculateDefenderModifiersForPrediction`, `ApplyCappedModifiers` and the
// per-effect `*_ExtraDamageEffect.CreateEffectDamageBonusForAttack` are all
// invoked PURELY via IL2CPP MethodInfo dispatch (interface/virtual). Literal
// code search finds zero by-name callers → the caller + the runtime origin of
// the builder's `param_5` (effect/ability source list) are invisible to static
// RE. The decompiled AI-prediction path (PredictAttackRaw + every wrapper:
// PredictAttack, the b__0 lambdas, GetNormalAttackPrediction,
// BattleQuery/DamagePredictionQuery.GetAttackPrediction) never calls the
// modifier builder by name.
//
// This hook attaches to those methods and CAPTURES THE BACKTRACE on the first
// few fires. The backtrace's IL2CPP frames are emitted as RVAs (`rva:0x...`,
// offset from GameAssembly.dll base) — add 0x180000000 to each to get the
// ghidra preferred-image address and look it up against the build dump. That
// reveals: (1) whether the modifier builder fires AT ALL during an AI
// prediction (→ tells us if the AI uses this path or a different one), and
// (2) the exact caller chain → where param_5 is built.
//
// This is OBSERVATION of an already-RE'd mechanism (who calls it, from where),
// not formula-fitting. Read-only; no code is replaced.
//
// Auto-arms best-effort at register (battle classes may not be resolved yet at
// script load → the install is retried via the modifierObserveInstall RPC,
// which is what the scenario driver calls after amorce).

import { Ctx } from "../controller.js";
import {
    class_get_name, findClassAnywhere, findMethod, findMethodByParamCount, il2cppBase, s,
} from "../il2cpp/helpers.js";
import { pinnedAddress } from "../il2cpp/build-pin.js";
import { captureStack } from "../ai-toolkit/stack-capture.js";
import { log } from "../runtime/diag.js";
import { queueOnMainThread } from "../runtime/queue.js";

interface Target {
    ns: string;
    cls: string;
    method: string;
    /** short tag used as the capture key */
    tag: string;
}

const TARGETS: Target[] = [
    {
        ns: "IdunBattle.Core.Services", cls: "DamageCalculations",
        method: "CalculateAttackerModifiersForPrediction", tag: "attackerMods",
    },
    {
        ns: "IdunBattle.Core.Services", cls: "DamageCalculations",
        method: "CalculateDefenderModifiersForPrediction", tag: "defenderMods",
    },
    {
        ns: "IdunBattle.Core.Services", cls: "DamageCalculations",
        method: "ApplyCappedModifiers", tag: "applyCapped",
    },
    // Per-effect source of the +25% (RapidAssault). If THIS fires during the
    // AI prediction, the effect→DamageBonus path is live (vs UI-only).
    {
        ns: "IdunBattle.Entities.Effects.Loki",
        cls: "RapidAssault_ExtraDamageEffect",
        method: "CreateEffectDamageBonusForAttack", tag: "rapidAssaultBonus",
    },
    // The ACTUAL AI-prediction path (decisionView reads dmgMin/dmgMax from
    // DamagePredictionQuery.GetAllPredictions → ... → PredictAttackRaw).
    // PredictAttackRaw's backtrace = "d'où on vient" (the full caller chain
    // from the AI entry down to the core). If the builders above stay at 0
    // while these fire, the ×1.25 enters this chain without the builders.
    {
        ns: "IdunBattle.Core.Services", cls: "DamagePrediction",
        method: "PredictAttackRaw", tag: "predictRaw",
    },
    {
        ns: "IdunBattle.Core.Services", cls: "DamagePredictionQuery",
        method: "GetAllPredictions", tag: "getAllPred",
    },
    // The CACHED query is what decisionView actually calls (resolveDpq). It
    // returns cached predictions on a hit (no recompute → no downstream fire).
    // Hooking it confirms decisionView hits it; on a cache MISS (after a state
    // change) it calls the underlying chain → PredictAttackRaw fires.
    {
        ns: "IdunBattleLogic.Core.Services.Caches",
        cls: "CachedDamagePredictionQuery",
        method: "GetAllPredictions", tag: "cachedGetAll",
    },
];

/** Capture at most this many backtraces per target (one-shot — we only need a
 * specimen of the caller chain, and the methods may be moderately hot during
 * an AI turn). After the cap the onEnter still counts fires but stops
 * capturing, keeping overhead negligible. */
const MAX_CAPTURES_PER_TARGET = 6;

// ── VALUE DUMP — per-bout armour/pierce inputs+output ───────────────────────
// To find the axis that explains u90 (oracle per-hit ≫ offline), dump the REAL
// values the native feeds to the per-bout core `GetBaseDamageWithFixedPiercedArmor`
// (@181030d10) : base bout (param_2), pierce-extras (param_3/param_4), armour
// penetration (param_10), and the returned per-bout damage. base bout ≈ 1850 /
// 2774 identifies u90's lo/hi; result vs offline [370,766] + penetration reveals
// whether armour/pierce is being modified. CONFIRMATION of an RE'd chain (which
// input differs), not fitting. Read-only.
const DUMP_TARGET: Target = {
    ns: "IdunBattle.Core.Services", cls: "DamagePrediction",
    method: "GetBaseDamageWithFixedPiercedArmor", tag: "baseDmgPierced",
};
// #98 : 40 (first-N) perdait la queue d'un tour de décision complet (33 prédictions × 2 bouts = 66
// fires : les normales évaluées en dernier étaient DROPPÉES → « je ne vois que les plasma »). Ring
// buffer (garde les DERNIERS) + cap large : un tour de décision entier tient.
const MAX_VALUE_DUMPS = 200;

/** Ring push : garde les `cap` DERNIERS éléments (les buffers first-N perdaient la fin du tour). */
function pushRing<T>(arr: T[], v: T, cap: number): void {
    arr.push(v);
    if (arr.length > cap) arr.shift();
}

/** FixMath.NET Fix64 = Q31.32 (64-bit, 32 fractional bits) → integer part = raw >> 32.
 * Damage values are positive so the logical shift is fine. Returns the int part
 * and the raw hex (for format sanity-checks). */
function fix64(p: NativePointer): { i: number; raw: string } {
    let i = NaN;
    try { i = p.shr(32).toInt32(); } catch { /* */ }
    return { i, raw: p.toString() };
}

interface ValueDump {
    idx: number;
    baseIn: { i: number; raw: string };
    pierceA: { i: number; raw: string };
    pierceB: { i: number; raw: string };
    penetration: { i: number; raw: string };
    result: { i: number; raw: string };
    ts: number;
}

// ── VAR-FOR-LEVEL DUMP — the ability-variable resolution (#68) ────────────────────────────────
// `AbilityConfiguration.GetVariableForLevel(config, variableId, Level, ...)` resolves an ability variable
// (e.g. SmashaEad.extraDmg id 8) for a given Level {level@0, multiplier@4}. TryGetVariableArrayForLevel
// applies `round(base * (Level+4)/100)` iff the var is rarity-flagged. MEASURING (variableId, level, mult,
// result) here tells us the ACTUAL multiplier the game applies per resolution — combat vs prediction — so we
// stop INFERRING (#68: is combat mult 90 vs prediction 180?). args: [0]=config, [1]=variableId, [2]=&Level.
const VARLEVEL_TARGET: Target = {
    ns: "IdunBattle.Configuration", cls: "AbilityConfiguration",
    method: "GetVariableForLevel", tag: "varForLevel",
};
const MAX_VARLEVEL_DUMPS = 120;
interface VarLevelDump {
    idx: number;
    variableId: number;
    level: number;
    mult: number;      // Level+4 — the multiplier the game applies (100=none, 180=normal, 90=rarity?)
    result: number;    // resolved variable value (int part)
    ts: number;
    topRva?: number;   // #68 : backtrace to CLASSIFY the fire — a COMBAT resolution (via
    frames?: string[]; // AttackDamageOperation/ExecuteHit) vs a PREDICTION one (PredictAttackRaw).
}

// ── HIT-DAMAGE DUMP — the combat per-hit range {min,max} + roll (#68) ─────────────────────────
// `HitDamage.GetDamage(HitDamage{min@0,max@4}, rng, avgFlag)` : avgFlag!=0 -> (min+max)/2 ; else rolls in
// [min,max]. This is the COMBAT per-hit core (fires in combat). Reading min/max shows how the additive is
// FOLDED into the range: additive flat -> both min+max shift ; ExtraMaxDamage -> only max shifts (then a
// midpoint/roll reflects ~half). This is the last read to pin the #68 combat /2. args: [0]=&HitDamage,[2]=avgFlag.
const HITDMG_TARGET: Target = {
    ns: "IdunBattle.Core", cls: "HitDamage", method: "GetDamage", tag: "hitDmgGet",
};
const MAX_HITDMG_DUMPS = 60;
interface HitDmgDump {
    idx: number;
    min: number;
    max: number;
    avgFlag: number;   // param_3 : 0=roll, else midpoint
    result: number;
    ts: number;
}

// ── MODS DUMP — DamageModifiers struct fields per builder (attacker vs defender) ──────────────
// To SOURCE the 499 penetration: each builder fills its output DamageModifiers (args[0]) — field
// @0x10=additive(Fix64), @0x20=pierce-extra(Fix64), @0x28=penetration(Fix64). Reading both builders'
// @0x28 separately tells which SIDE (attacker u90 / defender u86) contributes the 499. Read-only.
const MODS_DUMP_TARGETS: Target[] = [
    {
        ns: "IdunBattle.Core.Services", cls: "DamageCalculations",
        method: "CalculateAttackerModifiersForPrediction", tag: "attModsDump",
    },
    {
        ns: "IdunBattle.Core.Services", cls: "DamageCalculations",
        method: "CalculateDefenderModifiersForPrediction", tag: "defModsDump",
    },
];
const MAX_MODS_DUMPS = 80;

interface ModsDump {
    idx: number;
    side: string;            // "attacker" | "defender"
    additive: { i: number; raw: string };
    pierce: { i: number; raw: string };       // @0x20
    penetration: { i: number; raw: string };  // @0x28
    percentsX1000?: number[];                 // @0x18 List<Fix64> x1000 (500 = 0.5x reduction)
    ts: number;
}

// ── MULT DUMP — chaque multiplicateur composé dans la DamageModifiers (#98) ──────────────────
// `DamageCalculations.GetMultiplierFromDamageBonus @181005210` convertit UNE contribution (effet
// OU feuille positionnelle élévation/RangedInMelee/trench) en multiplicateur Fix64 (1 ± pct/100)
// juste avant `DamageModifiers.Add`. Struct-return via args[0] (16 o : Fix64 mult @0). Dumper
// multX1000 + topRva = LA décomposition « quels multiplicateurs composent le ×k » (#98 : ×2.25 =
// [1500, 1500] = CrushingStrike × Élévation) — ce que ni modsDumps (struct composée, offsets
// fragiles) ni bonusDumps (retWords ambigus) ne donnaient. Ring buffer (garde les derniers).
interface MultDump {
    idx: number;
    /** Fix64 multiplicateur ×1000 (quad 1 du struct retour — layout MESURÉ #98 : quad0 = flag/pad,
     * quad1 = Fix64 mult). 1500 = ×1.5 ; 1250 = ×1.25 ; 0 = Nullable vide (contribution nulle). */
    multX1000: number;
    q0X1000?: number;     // quad 0 (flag/pad — gardé pour sanity)
    topRva: number;       // frame appelant (ghidra = +0x180000000) : boucle effets vs feuille positionnelle
    ts: number;
}
const MAX_MULT_DUMPS = 160;

// ── PRED-CALC DUMP — l'application des mods côté PRÉDICTION (#98) ────────────────────────────
// `DamagePrediction.CalculateBaseDamageWithAllModifiers` (appelée par PredictAttackRaw @181032fb0
// L1940/L2062, une par bout min/max) = l'étage où le ×mods s'applique au bout per-coup EN
// PRÉDICTION. L'ancien hook calcDmgOp ne couvrait que le COMBAT (CalculateDamageOperation) →
// l'étage prédiction était un ANGLE MORT (#98 : « modsDumps vides mais ×2.25 au final » restait
// invisible). in = args[1] (bout int, post-perçage) ; out = retval (int ET vue Fix64 — prendre
// celle qui est cohérente avec in×mult).
interface PredCalcDump { idx: number; incoming: number; outInt: number; outFix: number; ts: number; }
const MAX_PREDCALC_DUMPS = 160;

// ── BONUS DUMP — per-source attribution via the BASE dispatchers + stacktrace ────────────────
// User's idea: hook the modifier *construction* point with a backtrace so every bonus is
// attributed to its SOURCE (which effect / which path created it). The two prediction-time
// dispatchers read the per-effect cached bonus:
//   • BaseEffect.HitsBonusForAttack  @180f12a30 → hits axis (PowerTrip_FullHealthEffect +1, …)
//   • BaseEffect.DamageBonusForAttack@180f0f5e0 → dmg/pierce/penetration axis (RapidAssault %, ignore-armour)
// `this` (the effect instance) = args[1] (after the hidden struct-return ptr) → its class name
// IS the source. The execution-time triggered-hits behaviour is a SEPARATE path:
//   • AddBonusHitsToCurrentHitGroupBehaviour.Execute @180f93410 → GetStuckIn's per-odd-hit bonus.
// If THIS fires during a decisionView-only window (no real attack), the PREDICTION simulates
// GetStuckIn (→ the 6 hits include it); if only the dispatchers fire, the prediction is
// base+effects only. Deduped by (tag, srcClass) so it stays bounded on hot paths. Read-only.
interface BonusTarget extends Target {
    /** arg index of the effect/source `this` (after the hidden struct-return ptr). */
    thisArgIdx: number;
}
const BONUS_TARGETS: BonusTarget[] = [
    {
        ns: "IdunBattle.Entities.Effects", cls: "BaseEffect",
        method: "HitsBonusForAttack", tag: "hitsBonus", thisArgIdx: 1,
    },
    {
        ns: "IdunBattle.Entities.Effects", cls: "BaseEffect",
        method: "DamageBonusForAttack", tag: "dmgBonus", thisArgIdx: 1,
    },
    {
        ns: "IdunBattle.Entities.Behaviours",
        cls: "AddBonusHitsToCurrentHitGroupBehaviour",
        method: "Execute", tag: "addBonusHitsExec", thisArgIdx: 1,
    },
];
const MAX_BONUS_DUMPS = 120;

interface BonusDump {
    idx: number;
    tag: string;
    srcClass: string | null;   // effect/source class name (read from `this`)
    topRva: number;
    /** frames as `rva:0x...` / `abs:0x...` — add 0x180000000 to each rva for ghidra. */
    frames: string[];
    /** #v2 combat capture — RETURN struct words (raw s32 @0x0..0x60) of the per-effect DamageBonus/HitsBonus
     * dispatcher (struct-return via args[0]). Read onLeave so we MEASURE each effect's contributed value +
     * its offset (SmashaEad additive etc.) instead of guessing the struct layout. */
    retWords: number[] | null;
    ts: number;
}

interface Capture {
    tag: string;
    fireIdx: number;
    topRva: number;
    /** frames as `rva:0x...` (IL2CPP) / `abs:0x...` (outside). Add
     * 0x180000000 to each rva to get the ghidra address. */
    frames: string[];
    ts: number;
}

const state = {
    installed: false,
    listeners: [] as InvocationListener[],
    fires: {} as Record<string, number>,
    resolved: {} as Record<string, string>,
    missing: [] as string[],
    captures: [] as Capture[],
    valueDumps: [] as ValueDump[],
    varLevelDumps: [] as VarLevelDump[],
    hitDmgDumps: [] as HitDmgDump[],
    modsDumps: [] as ModsDump[],
    multDumps: [] as MultDump[],           // #98 : chaque multiplicateur composé (décomposition ×k)
    predCalcDumps: [] as PredCalcDump[],   // #98 : application des mods côté PRÉDICTION (per-bout)
    bonusDumps: [] as BonusDump[],
    bonusSeen: new Set<string>(),
    dispatchDumps: [] as DispatchDump[],   // #68 TEMP : resolve the opaque ExecuteHit final-damage service
    dispatchSeen: new Set<string>(),
    calcDmgDumps: [] as CalcDmgDump[],     // #68 TEMP : incoming vs outgoing damage in CalculateDamageOperation
    critCtorDumps: [] as CritCtorDump[],   // #68 TEMP : CritDamageInfo..ctor callers (name the +300 leaf)
    critCtorSeen: new Set<number>(),
};

// #68 TEMP DIAGNOSTIC (a retirer avant commit) : le degat combat final est calcule par un service
// INTERFACE-dispatche (`FUN_180028580(out, slot, iface, obj, ...)`). On resout la methode
// concrete en repliquant le walk vtable il2cpp du decompile : klass=*obj ; table interfaces @klass+0xb0
// (count @+0x12e) ; vid = klass+0x138 + (ifaceOffset+slot)*0x10 ; methodPtr = *vid. On enregistre le RVA
// (methodPtr-il2cppBase) + le nom de classe pour le decompiler. Filtre slot==0x42 (le dispatch final).
// ⚠ ET LE FILTRE `slot == 0x42` N'ISOLE PAS `ExecuteHit` -- mesure du 2026-08-15 sur `t6dpr4k06g`.
// L'invocateur n'a que DEUX appelants DIRECTS (`list_xrefs` ; il porte AUSSI une reference DATA, donc
// une invocation indirecte par cette table ne serait vue par aucun appel direct), et les DEUX passent
// `0x42` sur la MEME interface :
// `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (le degat, notre cible) et
// `IdunBattle.Operations.DisplaceUnitOperation$$ApplyKnockbackTo` (`mov edx,0x42` lu a l'octet).
// Consequence sur la LECTURE, pas sur la surete : le dump peut porter DEUX entrees, discriminees par
// `topRva` (le sommet de pile) et par `cls`. Ne pas lire une entree unique comme << le dispatch final >>.
interface DispatchDump {
    slot: number; rva: string; cls: string | null; topRva: number; ts: number;
}
// #68 TEMP : `DamagePrediction.CalculateDamageOperation(out, p2, p3, p4, msg)` @18102dc30 = le calcul
// combat de degat REEL (soustrait armure/block/crit sur le degat ENTRANT du message). On lit le degat
// ENTRANT (msg[0] = AttackHit) et le degat SORTANT (out[+4]) par coup -> si entrant = base+~300, le +300
// est un BONUS PRE-ARMURE dans l'AttackHit (amont ExecuteHit), PAS l'additif ForAddition (599, prediction).
interface CalcDmgDump { incoming: number; outgoing: number; ts: number; }
// #68 TEMP : le leaf qui produit le +300 (ExecuteHit board-node slot 0xb) construit un CritDamageInfo.
// Hooker `CritDamageInfo..ctor @180fff850` + backtrace -> le frame appelant = ce leaf. On lit aussi le
// damage arg (arg1) pour voir si le +300/1540 y transite. Dedup par topRva.
interface CritCtorDump { damage: number; topRva: number; frames: string[]; ts: number; }
// #475 : la constante `CRIT_CTOR_RVA` qui vivait ici est SUPPRIMEE. Elle etait MORTE (declaree,
// plus aucun attachement depuis le retrait ci-dessous) ET PERIMEE -- mesure du 2026-08-04 : sa VA
// vaut, sur `rnca9r7q6c`, `AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal+0x130`,
// au milieu d'une fonction sans rapport. `CritDamageInfo$$.ctor` n'est present dans AUCUNE des
// deux tables du build courant (ni ghidra ni frida) : corps de ctor de ValueType, DEDUPLIQUE --
// donc NON RESOLUBLE par symbole, et rien a re-epingler tant que ce hook reste retire.
// Les `critCtorDumps` ci-dessous restent donc STRUCTURELLEMENT VIDES.
//
// #68 TEMP : `FUN_180028580` -- helper NON nomme (aucun `MethodInfo`), donc NON RESOLUBLE par
// symbole : c'est le cas ou une VA en dur reste le seul ancrage. Elle passe par le FOYER
// `build-pin`, qui REFUSE d'attacher des que le build a bouge.
// ⚠ RE-MESUREE le 2026-08-15 sur `t6dpr4k06g` (residu #475-r2). Elle valait `0x1800267c0` sur
// `gqfc5mff6c`, ou ce nom EXISTE dans la table -- et cette VA tombait a `FUN_180026780+0x40` sur
// `rnca9r7q6c`, au milieu d'une AUTRE fonction. Sur `t6dpr4k06g`, `FUN_1800267c0` n'existe meme
// plus comme fonction (la table porte `FUN_1800267e0`) : les frontieres ont bouge.
// LA RE-DERIVATION N'EST PAS UN GREP -- le nom d'un `FUN_*` EST son ancienne adresse, donc le
// retrouver ne prouverait rien. Elle tient en DEUX pas, tous deux LUS au decompile :
//   1. le CALL SITE : `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` appelle
//      `FUN_180028580(&out, 0x42, DAT_18336edb0, *(hitIndex+0x20), defender, unit, entities)` ;
//   2. le CORPS du callee : il fait EXACTEMENT le walk que ce hook replique --
//      `lVar1 = *param_4` ; boucle sur `*(lVar1+0xb0)` tant que `< *(ushort *)(lVar1+0x12e)` ;
//      `vid = lVar1 + 0x138 + (*(int *)(itable+8+i*0x10) + param_2) * 0x10` ; repli
//      `FUN_1801e72b0(param_4, param_3, param_2)`. Signature relue :
//      `(param_1 out, param_2 slot (ushort), param_3 iface, param_4 obj, ...)`, ce qui confirme
//      `args[1]=slot`, `args[2]=iface`, `args[3]=obj`.
const DISPATCH_HELPER_PIN = {
    va: 0x180028580, build: "t6dpr4k06g", symbol: "FUN_180028580",
    what: "invocateur d'interface -- resout la methode concrete du slot 0x42 (degat combat final)",
    how: "ghidra sur le build courant : partir du call site dans"
        + " IdunBattle.Operations.AttackDamageOperation$$ExecuteHit (le call a 7 arguments dont le"
        + " 2e vaut 0x42), suivre le CALLEE, puis VERIFIER SON CORPS -- il doit faire le walk"
        + " d'itable klass+0xb0 / count klass+0x12e / vid = klass+0x138 + (off+slot)*0x10.",
};
const DISPATCH_SLOT_FILTER = 0x42;

function installOnce(): {
    ok: boolean; hooked: string[]; missing: string[];
} {
    if (state.installed) {
        return {
            ok: true, hooked: Object.values(state.resolved),
            missing: state.missing,
        };
    }
    const hooked: string[] = [];
    const missing: string[] = [];
    for (const t of TARGETS) {
        const klass = findClassAnywhere(t.ns, t.cls);
        if (!klass) { missing.push(`${t.cls} (class not resolved)`); continue; }
        const m = findMethod(klass, t.method);
        if (!m || m.ptr.isNull()) {
            missing.push(`${t.cls}.${t.method} (method not found)`);
            continue;
        }
        state.fires[t.tag] = 0;
        const tag = t.tag;
        try {
            state.listeners.push(Interceptor.attach(m.ptr, {
                onEnter(this: InvocationContext) {
                    const n = (state.fires[tag] = (state.fires[tag] ?? 0) + 1);
                    if (n > MAX_CAPTURES_PER_TARGET) return;
                    const { topRva, frames } = captureStack(this.context);
                    state.captures.push({
                        tag, fireIdx: n, topRva, frames, ts: Date.now(),
                    });
                    log(`[modifier-observe] ${tag} fire#${n} top=rva:0x`
                        + topRva.toString(16) + " (ghidra 0x"
                        + (0x180000000 + topRva).toString(16) + ")");
                },
            }));
            const ghidra = 0x180000000 + m.ptr.sub(il2cppBase).toInt32();
            state.resolved[t.tag] = `${t.cls}.${t.method} @ ${m.ptr} `
                + `(ghidra 0x${ghidra.toString(16)})`;
            hooked.push(state.resolved[t.tag]);
        } catch (e) {
            missing.push(`${t.cls}.${t.method} (attach: `
                + (e as Error).message + ")");
        }
    }
    // Value-dump hook on the per-bout core (onEnter args + onLeave result).
    try {
        const dk = findClassAnywhere(DUMP_TARGET.ns, DUMP_TARGET.cls);
        const dm = dk ? findMethod(dk, DUMP_TARGET.method) : null;
        if (!dm || dm.ptr.isNull()) {
            missing.push(`${DUMP_TARGET.cls}.${DUMP_TARGET.method} (value-dump method not found)`);
        } else {
            state.fires[DUMP_TARGET.tag] = 0;
            state.listeners.push(Interceptor.attach(dm.ptr, {
                // args: [0]=this/param_1, [1]=base bout, [2]=pierceA, [3]=pierceB,
                // [4]=attacker, [5]=target, [6]=profile, [7]=p8, [8]=p9, [9]=penetration.
                onEnter(this: InvocationContext & { _vd?: ValueDump },
                        args: InvocationArguments) {
                    const n = (state.fires[DUMP_TARGET.tag] =
                        (state.fires[DUMP_TARGET.tag] ?? 0) + 1);
                    this._vd = {
                        idx: n - 1,
                        baseIn: fix64(args[1]),
                        pierceA: fix64(args[2]),
                        pierceB: fix64(args[3]),
                        penetration: fix64(args[9]),
                        result: { i: NaN, raw: "" }, ts: Date.now(),
                    };
                },
                onLeave(this: InvocationContext & { _vd?: ValueDump }, retval) {
                    if (!this._vd) return;
                    this._vd.result = fix64(retval);
                    pushRing(state.valueDumps, this._vd, MAX_VALUE_DUMPS);
                },
            }));
            const ghidra = 0x180000000 + dm.ptr.sub(il2cppBase).toInt32();
            state.resolved[DUMP_TARGET.tag] =
                `${DUMP_TARGET.cls}.${DUMP_TARGET.method} @ ${dm.ptr} `
                + `(ghidra 0x${ghidra.toString(16)}) [value-dump]`;
            hooked.push(state.resolved[DUMP_TARGET.tag]);
        }
    } catch (e) {
        missing.push(`${DUMP_TARGET.cls}.${DUMP_TARGET.method} (value-dump attach: `
            + (e as Error).message + ")");
    }

    // #68 var-for-level dump : the ACTUAL multiplier applied to each ability variable resolution.
    try {
        const vk = findClassAnywhere(VARLEVEL_TARGET.ns, VARLEVEL_TARGET.cls);
        const vm = vk ? findMethod(vk, VARLEVEL_TARGET.method) : null;
        if (!vm || vm.ptr.isNull()) {
            missing.push(`${VARLEVEL_TARGET.cls}.${VARLEVEL_TARGET.method} (var-level method not found)`);
        } else {
            state.fires[VARLEVEL_TARGET.tag] = 0;
            state.listeners.push(Interceptor.attach(vm.ptr, {
                // args: [0]=config, [1]=variableId (enum int), [2]=&Level {level@0, multiplier@4}.
                onEnter(this: InvocationContext & { _v?: VarLevelDump }, args: InvocationArguments) {
                    state.fires[VARLEVEL_TARGET.tag] = (state.fires[VARLEVEL_TARGET.tag] ?? 0) + 1;
                    if (state.varLevelDumps.length >= MAX_VARLEVEL_DUMPS) return;
                    let variableId = -1; let level = -1; let mult = -1;
                    try { variableId = args[1].toInt32(); } catch { /* */ }
                    try { level = args[2].readS32(); mult = args[2].add(4).readS32(); } catch { /* */ }
                    this._v = { idx: state.varLevelDumps.length, variableId, level, mult, result: NaN,
                                ts: Date.now() };
                    // #68 : the mult (90 vs 180) alone can't tell WHICH pipeline resolved this var.
                    // Backtrace it so offline we classify combat-vs-prediction by the caller chain.
                    try {
                        const { topRva, frames } = captureStack(this.context);
                        this._v.topRva = topRva; this._v.frames = frames;
                    } catch { /* */ }
                },
                onLeave(this: InvocationContext & { _v?: VarLevelDump }, retval) {
                    if (!this._v) return;
                    try { this._v.result = retval.toInt32(); } catch { /* */ }
                    state.varLevelDumps.push(this._v);
                },
            }));
            hooked.push(`${VARLEVEL_TARGET.cls}.${VARLEVEL_TARGET.method} @ ${vm.ptr} [var-level dump]`);
        }
    } catch (e) {
        missing.push(`${VARLEVEL_TARGET.cls}.${VARLEVEL_TARGET.method} (var-level attach: `
            + (e as Error).message + ")");
    }

    // #68 hit-damage range dump : combat per-hit {min,max} to see how the additive folds into the range.
    try {
        const hk = findClassAnywhere(HITDMG_TARGET.ns, HITDMG_TARGET.cls);
        const hm = hk ? findMethod(hk, HITDMG_TARGET.method) : null;
        if (!hm || hm.ptr.isNull()) {
            missing.push(`${HITDMG_TARGET.cls}.${HITDMG_TARGET.method} (hit-dmg method not found)`);
        } else {
            state.fires[HITDMG_TARGET.tag] = 0;
            state.listeners.push(Interceptor.attach(hm.ptr, {
                onEnter(this: InvocationContext & { _h?: HitDmgDump }, args: InvocationArguments) {
                    state.fires[HITDMG_TARGET.tag] = (state.fires[HITDMG_TARGET.tag] ?? 0) + 1;
                    if (state.hitDmgDumps.length >= MAX_HITDMG_DUMPS) return;
                    let min = -1; let max = -1; let avgFlag = -1;
                    try { min = args[0].readS32(); max = args[0].add(4).readS32(); } catch { /* */ }
                    try { avgFlag = args[2].toInt32() & 0xff; } catch { /* */ }
                    this._h = { idx: state.hitDmgDumps.length, min, max, avgFlag, result: NaN,
                                ts: Date.now() };
                },
                onLeave(this: InvocationContext & { _h?: HitDmgDump }, retval) {
                    if (!this._h) return;
                    try { this._h.result = retval.toInt32(); } catch { /* */ }
                    state.hitDmgDumps.push(this._h);
                },
            }));
            hooked.push(`${HITDMG_TARGET.cls}.${HITDMG_TARGET.method} @ ${hm.ptr} [hit-dmg dump]`);
        }
    } catch (e) {
        missing.push(`${HITDMG_TARGET.cls}.${HITDMG_TARGET.method} (hit-dmg attach: `
            + (e as Error).message + ")");
    }

    // #68 TEMP : resolve the opaque final-damage interface method (slot 0x42) dispatched from ExecuteHit.
    // L'adresse passe par le FOYER `build-pin` : `null` = build different (ou non mesurable), donc
    // AUCUN attachement. Le foyer a deja imprime la cause ; on la remonte dans `missing` pour qu'un
    // lecteur de `modifierObserveStatus` voie ce capteur ABSENT plutot que silencieux.
    const dispatchHelper = pinnedAddress(DISPATCH_HELPER_PIN);
    if (dispatchHelper === null) {
        missing.push("FUN_180028580 (dispatch-42 : adresse EPINGLEE REFUSEE -- le build a bouge"
            + " ou n'est pas mesurable ; cf. log [build-pin] REFUS)");
    } else try {
        const helper = dispatchHelper;
        state.fires["dispatch42"] = 0;
        state.listeners.push(Interceptor.attach(helper, {
            // FUN_180028580(out, slot, iface, obj, p5, p6, entities) : args[1]=slot, args[2]=iface, args[3]=obj.
            onEnter(this: InvocationContext, args: InvocationArguments) {
                let slot = -1;
                try { slot = args[1].toInt32(); } catch { return; }
                if (slot !== DISPATCH_SLOT_FILTER) return;
                state.fires["dispatch42"] = (state.fires["dispatch42"] ?? 0) + 1;
                if (state.dispatchDumps.length >= 24) return;
                try {
                    const iface = args[2];
                    const obj = args[3];
                    if (obj.isNull()) return;
                    const klass = obj.readPointer();
                    if (klass.isNull()) return;
                    const ifaceCount = klass.add(0x12e).readU16();
                    const ifaceTable = klass.add(0xb0).readPointer();
                    let ifaceOffset = -1;
                    for (let i = 0; i < ifaceCount; i++) {
                        const entry = ifaceTable.add(i * 0x10);
                        if (entry.readPointer().equals(iface)) {
                            ifaceOffset = entry.add(8).readS32(); break;
                        }
                    }
                    if (ifaceOffset < 0) return;
                    const vid = klass.add(0x138 + (ifaceOffset + slot) * 0x10);
                    const methodPtr = vid.readPointer();
                    if (methodPtr.isNull()) return;
                    const rva = "0x" + methodPtr.sub(il2cppBase).toString(16);
                    let cls: string | null = null;
                    try { cls = s(class_get_name(klass) as NativePointer); } catch { /* */ }
                    const key = cls + "|" + rva;
                    if (state.dispatchSeen.has(key)) return;
                    state.dispatchSeen.add(key);
                    const { topRva } = captureStack(this.context);
                    state.dispatchDumps.push({ slot, rva, cls, topRva, ts: Date.now() });
                } catch { /* */ }
            },
        }));
        hooked.push(`FUN_180028580 @ ${helper} [dispatch-42 vtable resolve]`);
    } catch (e) {
        missing.push(`FUN_180028580 (dispatch attach: ${(e as Error).message})`);
    }

    // #68 : hook CritDamageInfo..ctor RETIRE — Thread.backtrace sur ce ctor (chemin de degat TRES chaud,
    // fire a chaque prediction) suspend les threads -> freeze -> UnityFreezeDetector tue le jeu pendant le
    // amorce (anti-pattern CLAUDE.md). Nommer le leaf ExecuteHit slot 0xb = via un chemin SANS backtrace-hot.

    // #68 TEMP : CalculateDamageOperation — incoming AttackHit damage (msg[0]) vs outgoing (out[+4]).
    try {
        const ck = findClassAnywhere("IdunBattle.Core.Services", "DamagePrediction");
        const cm = ck ? findMethod(ck, "CalculateDamageOperation") : null;
        if (!cm || cm.ptr.isNull()) {
            missing.push("DamagePrediction.CalculateDamageOperation (calc-dmg method not found)");
        } else {
            state.fires["calcDmgOp"] = 0;
            state.listeners.push(Interceptor.attach(cm.ptr, {
                // (out, p2, p3, p4, msg) : args[0]=out, args[4]=msg ; msg[0] low32 = incoming damage.
                onEnter(this: InvocationContext & { _o?: NativePointer; _in?: number },
                        args: InvocationArguments) {
                    state.fires["calcDmgOp"] = (state.fires["calcDmgOp"] ?? 0) + 1;
                    this._o = args[0];
                    try { this._in = args[4].readS32(); } catch { this._in = -1; }
                },
                onLeave(this: InvocationContext & { _o?: NativePointer; _in?: number }) {
                    if (state.calcDmgDumps.length >= 30) return;
                    let outgoing = -1;
                    try { if (this._o) outgoing = this._o.add(4).readS32(); } catch { /* */ }
                    state.calcDmgDumps.push({ incoming: this._in ?? -1, outgoing, ts: Date.now() });
                },
            }));
            hooked.push(`DamagePrediction.CalculateDamageOperation @ ${cm.ptr} [calc-dmg in/out]`);
        }
    } catch (e) {
        missing.push(`DamagePrediction.CalculateDamageOperation (calc-dmg attach: ${(e as Error).message})`);
    }

    // Per-builder DamageModifiers struct dump (attacker vs defender → source the penetration).
    for (const mt of MODS_DUMP_TARGETS) {
        try {
            const mk = findClassAnywhere(mt.ns, mt.cls);
            const mm = mk ? findMethod(mk, mt.method) : null;
            if (!mm || mm.ptr.isNull()) {
                missing.push(`${mt.cls}.${mt.method} (mods-dump method not found)`);
                continue;
            }
            const side = mt.tag === "attModsDump" ? "attacker" : "defender";
            state.listeners.push(Interceptor.attach(mm.ptr, {
                onEnter(this: InvocationContext & { _p1?: NativePointer },
                        args: InvocationArguments) {
                    this._p1 = args[0];   // output DamageModifiers struct ptr
                },
                onLeave(this: InvocationContext & { _p1?: NativePointer }) {
                    if (!this._p1 || this._p1.isNull()) return;
                    if (state.modsDumps.length >= MAX_MODS_DUMPS) return;
                    const p1 = this._p1;
                    // #68 defense: read the %-MULTIPLIER list @0x18 (List<Fix64>) — a defender x0.5 reduction
                    // lives here (NOT in additive@0x10). Fix64 value = raw/2^32 ; emit approx float x1000.
                    const percents: number[] = [];
                    try {
                        const list = p1.add(0x18).readPointer();
                        if (!list.isNull()) {
                            const size = list.add(0x18).readS32();
                            const items = list.add(0x10).readPointer();
                            const n = Math.max(0, Math.min(size, 8));
                            for (let i = 0; i < n; i++) {
                                // Fix64 = Q31.32 ; value = hi + lo/2^32. Emit x1000 (500 = 0.5x, 1000 = 1.0x).
                                const lo = items.add(0x20 + i * 8).readU32();
                                const hi = items.add(0x20 + i * 8 + 4).readS32();
                                percents.push(Math.round((hi + lo / 4294967296) * 1000));
                            }
                        }
                    } catch { /* */ }
                    try {
                        state.modsDumps.push({
                            idx: state.modsDumps.length, side,
                            additive: fix64(p1.add(0x10).readPointer()),
                            pierce: fix64(p1.add(0x20).readPointer()),
                            penetration: fix64(p1.add(0x28).readPointer()),
                            percentsX1000: percents,
                            ts: Date.now(),
                        });
                    } catch { /* */ }
                },
            }));
            hooked.push(`${mt.cls}.${mt.method} @ ${mm.ptr} [mods-dump ${side}]`);
        } catch (e) {
            missing.push(`${mt.cls}.${mt.method} (mods-dump attach: `
                + (e as Error).message + ")");
        }
    }

    // #98 : chaque multiplicateur composé — GetMultiplierFromDamageBonus (2 OVERLOADS natifs :
    // @181005210 refcount 10 + @1810053e0 refcount 3 — hooker LES DEUX, le builder peut appeler
    // l'un ou l'autre). Struct-return 16 o via hidden pointer (RAX = ptr, l'appelant lit 2 quads) ;
    // le quad porteur du Fix64 n'est pas tranché statiquement -> dumper LES DEUX (q0/q1, ×1000).
    // topRva attribue la contribution (boucle effets vs feuille positionnelle).
    try {
        const gk = findClassAnywhere("IdunBattle.Core.Services", "DamageCalculations");
        const seenPtrs: string[] = [];
        const cands: Array<{ info: NativePointer; ptr: NativePointer }> = [];
        for (const pc of [1, 2, 3]) {
            const mi = gk ? findMethodByParamCount(gk, "GetMultiplierFromDamageBonus", pc) : null;
            if (mi && !mi.ptr.isNull() && seenPtrs.indexOf(mi.ptr.toString()) < 0) {
                seenPtrs.push(mi.ptr.toString());
                cands.push(mi);
            }
        }
        if (!cands.length) {
            missing.push("DamageCalculations.GetMultiplierFromDamageBonus (mult-dump method not found)");
        } else {
            state.fires["multFromBonus"] = 0;
            for (const gm of cands) {
                state.listeners.push(Interceptor.attach(gm.ptr, {
                    onEnter(this: InvocationContext & { _rva?: number; _out?: NativePointer },
                            args: InvocationArguments) {
                        state.fires["multFromBonus"] = (state.fires["multFromBonus"] ?? 0) + 1;
                        this._out = args[0];
                        try { this._rva = captureStack(this.context).topRva; } catch { this._rva = -1; }
                    },
                    onLeave(this: InvocationContext & { _rva?: number; _out?: NativePointer }, retval) {
                        const src = (retval && !retval.isNull()) ? retval : this._out;
                        if (!src || src.isNull()) return;
                        const rd = (off: number): number => {
                            try {
                                const lo = src.add(off).readU32();
                                const hi = src.add(off + 4).readS32();
                                return Math.round((hi + lo / 4294967296) * 1000);
                            } catch { return NaN; }
                        };
                        // layout MESURÉ (#98) : quad 0 = flag/pad (0), quad 1 = Fix64 multiplicateur.
                        pushRing(state.multDumps, {
                            idx: (state.fires["multFromBonus"] ?? 1) - 1,
                            multX1000: rd(8), q0X1000: rd(0),
                            topRva: this._rva ?? -1, ts: Date.now(),
                        }, MAX_MULT_DUMPS);
                    },
                }));
                hooked.push(`DamageCalculations.GetMultiplierFromDamageBonus @ ${gm.ptr} [mult-dump]`);
            }
        }
    } catch (e) {
        missing.push("GetMultiplierFromDamageBonus (mult-dump attach: " + (e as Error).message + ")");
    }

    // #98 : application des mods côté PRÉDICTION (une par bout, PredictAttackRaw L1940/L2062).
    try {
        const pk = findClassAnywhere("IdunBattle.Core.Services", "DamagePrediction");
        const pm = pk ? findMethod(pk, "CalculateBaseDamageWithAllModifiers") : null;
        if (!pm || pm.ptr.isNull()) {
            missing.push("DamagePrediction.CalculateBaseDamageWithAllModifiers (pred-calc method not found)");
        } else {
            state.fires["predCalcDmg"] = 0;
            state.listeners.push(Interceptor.attach(pm.ptr, {
                onEnter(this: InvocationContext & { _in?: number }, args: InvocationArguments) {
                    state.fires["predCalcDmg"] = (state.fires["predCalcDmg"] ?? 0) + 1;
                    try { this._in = args[1].toInt32(); } catch { this._in = -1; }
                },
                onLeave(this: InvocationContext & { _in?: number }, retval) {
                    let outInt = NaN; let outFix = NaN;
                    try { outInt = retval.toInt32(); } catch { /* */ }
                    try { outFix = retval.shr(32).toInt32(); } catch { /* */ }
                    pushRing(state.predCalcDumps, {
                        idx: (state.fires["predCalcDmg"] ?? 1) - 1,
                        incoming: this._in ?? -1, outInt, outFix, ts: Date.now(),
                    }, MAX_PREDCALC_DUMPS);
                },
            }));
            hooked.push(`DamagePrediction.CalculateBaseDamageWithAllModifiers @ ${pm.ptr} [pred-calc in/out]`);
        }
    } catch (e) {
        missing.push("DamagePrediction.CalculateBaseDamageWithAllModifiers (pred-calc attach: "
            + (e as Error).message + ")");
    }

    // Per-source bonus attribution (base dispatchers + execution behaviour) + backtrace.
    for (const bt of BONUS_TARGETS) {
        try {
            const bk = findClassAnywhere(bt.ns, bt.cls);
            const bm = bk ? findMethod(bk, bt.method) : null;
            if (!bm || bm.ptr.isNull()) {
                missing.push(`${bt.cls}.${bt.method} (bonus-dump method not found)`);
                continue;
            }
            state.fires[bt.tag] = 0;
            const tag = bt.tag;
            const thisIdx = bt.thisArgIdx;
            // The dmg/hits dispatchers are struct-returns: args[0] = sret out ptr (this = args[1]).
            // Execute (addBonusHitsExec) returns void -> no return struct to read.
            const hasRet = tag === "dmgBonus" || tag === "hitsBonus";
            state.listeners.push(Interceptor.attach(bm.ptr, {
                onEnter(this: InvocationContext & { _dump?: BonusDump; _out?: NativePointer },
                        args: InvocationArguments) {
                    state.fires[tag] = (state.fires[tag] ?? 0) + 1;
                    if (state.bonusDumps.length >= MAX_BONUS_DUMPS) return;
                    let srcClass: string | null = null;
                    try {
                        const self = args[thisIdx];
                        if (self && !self.isNull()) {
                            srcClass = s(
                                class_get_name(self.readPointer()) as NativePointer);
                        }
                    } catch { /* unreadable this → leave null */ }
                    // Dedup by (tag, srcClass): one specimen per source keeps the
                    // capture bounded even when the dispatcher is hot.
                    const key = `${tag}|${srcClass ?? "?"}`;
                    if (state.bonusSeen.has(key)) return;
                    state.bonusSeen.add(key);
                    const { topRva, frames } = captureStack(this.context);
                    const dump: BonusDump = {
                        idx: state.bonusDumps.length, tag, srcClass,
                        topRva, frames, retWords: null, ts: Date.now(),
                    };
                    state.bonusDumps.push(dump);
                    // #v2 : stash the sret out ptr to MEASURE this effect's contributed value onLeave.
                    if (hasRet) { this._dump = dump; this._out = args[0]; }
                    log(`[modifier-observe] ${tag} src=${srcClass ?? "?"} `
                        + `top=rva:0x${topRva.toString(16)} (ghidra 0x`
                        + (0x180000000 + topRva).toString(16) + ")");
                },
                onLeave(this: InvocationContext & { _dump?: BonusDump; _out?: NativePointer }) {
                    if (!this._dump || !this._out || this._out.isNull()) return;
                    const words: number[] = [];
                    for (let o = 0; o <= 0x60; o += 4) {
                        try { words.push(this._out.add(o).readS32()); } catch { words.push(-999999); }
                    }
                    this._dump.retWords = words;
                },
            }));
            hooked.push(`${bt.cls}.${bt.method} @ ${bm.ptr} [bonus-dump ${tag}]`);
        } catch (e) {
            missing.push(`${bt.cls}.${bt.method} (bonus-dump attach: `
                + (e as Error).message + ")");
        }
    }

    try { Interceptor.flush(); } catch { /* */ }
    state.missing = missing;
    state.installed = hooked.length > 0;
    log(`[modifier-observe] install: ${hooked.length} hooked, `
        + `${missing.length} missing`);
    return { ok: state.installed, hooked, missing };
}

export function register(ctx: Ctx): void {
    // #98 : auto-arm au register NEUTRALISE. `installOnce()` fait des Interceptor.replace sur des
    // chemins de degat ULTRA-CHAUDS -> crash du jeu sous churn reinject s'il s'arme au mauvais
    // moment (incident 2026-07-10, cause du disable #75). On N'ARME QUE on-demand via
    // modifierObserveInstall (queueOnMainThread), sur un etat STABLE (post-amorce, hors churn). Le
    // register n'expose plus que les RPC ci-dessous.

    ctx.rpc.modifierObserveInstall = (): Promise<unknown> =>
        queueOnMainThread(() => installOnce());

    ctx.rpc.modifierObserveStatus = (): unknown => ({
        installed: state.installed,
        listeners: state.listeners.length,
        resolved: { ...state.resolved },
        missing: [...state.missing],
        fires: { ...state.fires },
        captures: state.captures.map((c) => ({ ...c })),
        valueDumps: state.valueDumps.map((v) => ({ ...v })),
        varLevelDumps: state.varLevelDumps.map((v) => ({ ...v })),
        hitDmgDumps: state.hitDmgDumps.map((v) => ({ ...v })),
        modsDumps: state.modsDumps.map((v) => ({ ...v })),
        multDumps: state.multDumps.map((v) => ({ ...v })),
        predCalcDumps: state.predCalcDumps.map((v) => ({ ...v })),
        bonusDumps: state.bonusDumps.map((v) => ({ ...v })),
        dispatchDumps: state.dispatchDumps.map((v) => ({ ...v })),
        calcDmgDumps: state.calcDmgDumps.map((v) => ({ ...v })),
        critCtorDumps: state.critCtorDumps.map((v) => ({ ...v })),
    });

    ctx.rpc.modifierObserveReset = (): unknown => {
        for (const k of Object.keys(state.fires)) state.fires[k] = 0;
        state.captures = [];
        state.valueDumps = [];
        state.varLevelDumps = [];
        state.hitDmgDumps = [];
        state.modsDumps = [];
        state.multDumps = [];
        state.predCalcDumps = [];
        state.bonusDumps = [];
        state.bonusSeen.clear();
        state.dispatchDumps = [];
        state.dispatchSeen.clear();
        state.calcDmgDumps = [];
        state.critCtorDumps = [];
        state.critCtorSeen.clear();
        return { ok: true };
    };
}
