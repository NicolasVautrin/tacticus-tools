// Trace PER-COUP du vecteur ATTAQUE — hook de
// `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`.
//
// POURQUOI. Certains vecteurs ne rendent RIEN d'observable : `martial_apotheosis`
// (déclenchement au début de tour) donne `applyAction endturn` + `captureEvents`
// = 1 action / **0 event**, donc aucun coup individuel visible. Le compte de
// coups d'un port ne peut alors être confronté qu'au PORT lui-même — c'est-à-dire
// pas confronté du tout. Ce hook rend le coup observable à sa source.
//
// ON-DEMAND, JAMAIS auto-armé. `ExecuteHit` est sur le chemin de dégât le plus
// chaud du jeu ; l'incident du 2026-07-10 (Interceptor auto-armé sur ces chemins
// pendant le churn reinject/warmup) est la raison pour laquelle `modifier-observe`
// n'arme plus rien au register non plus. Armer via `hitTraceArm`, sur un état
// STABLE (post-warmup), et désarmer après la mesure.
//
// LAYOUT DES ARGUMENTS — CALIBRÉ, PAS SUPPOSÉ. La signature managée est
//   ExecuteHit(hitIndex:Int32, attacker:IEntity, defender:IEntity,
//              damageProfileType:DamageProfileType, abilityOrEffect:AbilityOrEffect,
//              attackDamageOptions:AttackDamageOptions, initialHealth:Int32,
//              deniedDamage:Int32) -> OperationResult
// mais le mapping vers les slots NATIFS dépend de conventions qu'on ne peut pas
// deviner sans risque : `OperationResult` est un ValueType de 80 o (retour par
// pointeur caché probable, qui décalerait TOUT d'un cran), `AbilityOrEffect` (40 o)
// et `AttackDamageOptions` (160 o) passent eux aussi par pointeur. Plutôt que de
// figer un décalage — et de lire des ids faux en silence si l'hypothèse est
// fausse — on CALIBRE au premier fire : on cherche deux slots ADJACENTS qui
// pointent tous deux sur une entité plausible (klass lisible, id @+0x10 et type
// @+0x14 dans des plages saines). Ce couple EST (attacker, defender) ; le slot
// juste avant est `hitIndex`, celui juste après `damageProfileType`. Le layout
// résolu est publié dans la charge utile, et les 3 premiers fires embarquent
// leurs slots BRUTS : si la calibration se trompe, ça se voit, au lieu de rendre
// des ids plausibles et faux.
//
// Read-only : aucun `Interceptor.replace`.

import { Ctx } from "../controller.js";
import { findClassAnywhere, findMethodByParamCount, methodEntry } from "../il2cpp/helpers.js";
import { OriginBuffers, getTraceOrigin } from "../game/trace-origin.js";
import { log } from "../runtime/diag.js";

/** entityId / entityType sur une base Entity (cf. forEachEntity, match-state.ts). */
const ENTITY_ID_OFF = 0x10;
const ENTITY_TYPE_OFF = 0x14;
/** Nombre de slots natifs sondés à la calibration. */
const PROBE_SLOTS = 10;
/** Fires dont on garde les slots BRUTS (audit de la calibration). */
const RAW_SAMPLES = 3;
const CAP_PER_ORIGIN = 500;

interface Hit {
    seq: number;
    hitIndex: number | null;
    attackerId: number | null;
    defenderId: number | null;
    /** DamageProfileType (enum brut) — non décodé ici, corrélable tel quel. */
    profile: number | null;
    originRunnerId: number | null;
    ts: number;
    /** Slots natifs bruts — présents seulement sur les RAW_SAMPLES premiers. */
    raw?: string[];
}

interface Layout {
    /** Slot natif de `attacker` ; defender = attacker+1. */
    attackerSlot: number;
    hitIndexSlot: number;
    profileSlot: number;
}

const buffers = new OriginBuffers<Hit>(CAP_PER_ORIGIN, "ring");

const state = {
    installed: false,
    enabled: true,
    seq: 0,
    fires: 0,
    listener: null as InvocationListener | null,
    layout: null as Layout | null,
    calibrationFailures: 0,
};

/** Un pointeur qui ressemble à une entité de bataille ? (klass lisible, id et
 *  type dans des plages saines). Sert UNIQUEMENT à la calibration. */
function looksLikeEntity(p: NativePointer): number | null {
    try {
        if (p.isNull()) return null;
        const klass = p.readPointer();          // objet managé : klass en tête
        if (klass.isNull()) return null;
        const id = p.add(ENTITY_ID_OFF).readS32();
        const ty = p.add(ENTITY_TYPE_OFF).readS32();
        if (id <= 0 || id > 1000000) return null;
        if (ty < 0 || ty > 16) return null;
        return id;
    } catch { return null; }
}

function calibrate(args: InvocationArguments): Layout | null {
    // Deux slots ADJACENTS qui sont tous deux des entités = (attacker, defender).
    // On commence à 1 : le slot 0 est `this` ou le buffer de retour, jamais une
    // entité de bataille — et on veut un slot AVANT pour `hitIndex`.
    for (let i = 1; i + 1 < PROBE_SLOTS; i++) {
        if (looksLikeEntity(args[i]) === null) continue;
        if (looksLikeEntity(args[i + 1]) === null) continue;
        return { attackerSlot: i, hitIndexSlot: i - 1, profileSlot: i + 2 };
    }
    return null;
}

function readS32Slot(args: InvocationArguments, slot: number): number | null {
    try { return args[slot].toInt32(); } catch { return null; }
}

function ensureInstalled(): boolean {
    if (state.installed) return true;
    const klass = findClassAnywhere("IdunBattle.Operations", "AttackDamageOperation");
    if (!klass) { log("[hit-trace] AttackDamageOperation non résolue (pre-warmup ?)"); return false; }
    const mi = findMethodByParamCount(klass, "ExecuteHit", 8);
    if (!mi) { log("[hit-trace] ExecuteHit(8) introuvable"); return false; }
    let entry = methodEntry(mi.info);
    if (entry.isNull()) { try { entry = mi.info.readPointer(); } catch { return false; } }
    if (entry.isNull()) { log("[hit-trace] ExecuteHit entry null"); return false; }
    try {
        state.listener = Interceptor.attach(entry, {
            onEnter(args) {
                if (!state.enabled) return;
                state.fires++;
                if (!state.layout) {
                    state.layout = calibrate(args);
                    if (!state.layout) { state.calibrationFailures++; return; }
                    log("[hit-trace] layout calibré : attacker=slot"
                        + state.layout.attackerSlot);
                }
                const L = state.layout;
                const hit: Hit = {
                    seq: ++state.seq,
                    hitIndex: readS32Slot(args, L.hitIndexSlot),
                    attackerId: looksLikeEntity(args[L.attackerSlot]),
                    defenderId: looksLikeEntity(args[L.attackerSlot + 1]),
                    profile: readS32Slot(args, L.profileSlot),
                    originRunnerId: getTraceOrigin(),
                    ts: Date.now(),
                };
                if (hit.seq <= RAW_SAMPLES) {
                    const raw: string[] = [];
                    for (let i = 0; i < PROBE_SLOTS; i++) {
                        try { raw.push(args[i].toString()); } catch { raw.push("<err>"); }
                    }
                    hit.raw = raw;
                }
                buffers.push(hit);
            },
        });
    } catch (e) {
        log("[hit-trace] attach FAILED: " + (e as Error).message);
        return false;
    }
    state.installed = true;
    log("[hit-trace] hooke AttackDamageOperation.ExecuteHit @ " + entry);
    return true;
}

export function register(ctx: Ctx): void {
    // AUCUN auto-arm : chemin de dégât ultra-chaud (cf. en-tête).

    /** Arme le hook. À appeler sur état STABLE (post-warmup). */
    ctx.rpc.hitTraceArm = (): unknown =>
        ({ ok: ensureInstalled(), installed: state.installed });

    /** Désarme et détache. Le buffer est conservé (hitTraceDump reste lisible). */
    ctx.rpc.hitTraceDisarm = (): unknown => {
        try { state.listener?.detach(); } catch { /* best effort */ }
        state.listener = null;
        state.installed = false;
        return { ok: true, installed: false, fires: state.fires };
    };

    /** Coups capturés. body: { runnerId?, limit?=200 } */
    ctx.rpc.hitTrace = (body?: { runnerId?: number; limit?: number }): unknown => {
        const lim = typeof body?.limit === "number" ? body.limit : 200;
        const all = buffers.entries(body?.runnerId);
        return {
            ok: true, installed: state.installed, enabled: state.enabled,
            fires: state.fires, captured: all.length,
            layout: state.layout, calibrationFailures: state.calibrationFailures,
            hits: all.slice(-Math.max(0, lim)),
        };
    };

    ctx.rpc.hitTraceSetEnabled = (body?: { on?: boolean }): unknown => {
        state.enabled = body?.on !== false;
        return { ok: true, enabled: state.enabled };
    };

    ctx.rpc.hitTraceReset = (body?: { runnerId?: number }): unknown => {
        buffers.clear(body?.runnerId);
        if (body?.runnerId === undefined) { state.seq = 0; state.fires = 0; }
        return { ok: true };
    };
}
