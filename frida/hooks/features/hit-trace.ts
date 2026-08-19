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
// pendant le churn reinject) est la raison pour laquelle `modifier-observe`
// n'arme plus rien au register non plus. Armer via `hitTraceArm`, sur un état
// STABLE (post-amorce), et désarmer après la mesure.
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
import {
    arm, disarm, capturing, armedReport, onDisarmed,
} from "../game/armed-runners.js";
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
    /** `initialHealth` — PV de la cible AVANT ce coup. `null` = hors plage de plausibilité
     *  (cf. `readHealthSlot`), jamais un nombre qu'on n'a pas su valider. */
    initialHealth: number | null;
    /** `deniedDamage` — part refusée (bouclier/immunités) telle que l'Operation la reçoit. */
    deniedDamage: number | null;
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
    /** `initialHealth` ; `deniedDamage` = initialHealthSlot+1. Cf. le bloc ci-dessous. */
    initialHealthSlot: number;
}

// ── `initialHealth` / `deniedDamage` — le MONTANT par coup (#503-r4) ────────────────────────────
// POURQUOI. La ventilation par coup manquait à `#503-r4` (tir différé `1237` : `u83` port 12049 vs
// natif 10957, `u81` bit-exact). Ce hook rendait déjà le CARDINAL et l'ORDRE — mesuré le
// 2026-08-10, natif `{81: 2, 83: 2}`, ordre `[81,81,83,83]`, identiques au port : la cause « pas le
// même nombre de coups » est éliminée. Reste l'étage d'APPLICATION du montant, et c'est
// `initialHealth` qui le donne : les PV AVANT chaque coup, donc le montant par différence.
//
// LE DÉCALAGE EST DÉRIVÉ DE LA CALIBRATION, PAS ÉCRIT EN DUR. La signature managée est
// `ExecuteHit(hitIndex:0, attacker:1, defender:2, damageProfileType:3, abilityOrEffect:4,
//  attackDamageOptions:5, initialHealth:6, deniedDamage:7)`. La calibration résout `attacker` par
// sa FORME (deux slots adjacents qui sont des entités) ; tous les autres s'en déduisent par leur
// position managée — `initialHealth` est 5 crans après `attacker` (les deux structs intermédiaires
// passent par pointeur, donc un slot chacun). Le layout mesuré le 2026-08-10 le confirme :
// `attackerSlot=3` ⇒ `hitIndex=2`, `profile=5`, donc `initialHealth=8`. On ne fige pas `8` : on
// écrit `attackerSlot + 5`, qui suit la calibration si elle bouge.
//
// ET ON NE REND JAMAIS UN ENTIER QU'ON N'A PAS VALIDÉ. Un slot mal deviné rendrait un nombre
// plausible et faux — exactement le vice contre lequel l'en-tête de ce fichier a été écrit. D'où
// `readHealthSlot` : hors plage → `null`. Un `null` DIT que la lecture a échoué ; un `0` mentirait.
/** Borne haute de plausibilité des PV (le roster rank 17 plafonne très en-dessous). */
const HEALTH_MAX_PLAUSIBLE = 10_000_000;

const buffers = new OriginBuffers<Hit>(CAP_PER_ORIGIN, "ring");

// ⚠ PAS de `enabled` ici (#483). La porte de capture vit dans `game/armed-runners.ts`,
// armee PAR RUNNER : un `hitTraceDisarm` d'un probe voisin ne peut plus couper la capture
// d'un autre acteur. Ce qui reste ici est l'etat PHYSIQUE du hook (`installed`), qui lui
// est bien global — le detachement est differe au moment ou PLUS PERSONNE n'est arme
// (`onDisarmed`, cf. plus bas).
const state = {
    installed: false,
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
        return {
            attackerSlot: i, hitIndexSlot: i - 1, profileSlot: i + 2,
            initialHealthSlot: i + 5,        // cf. le bloc `initialHealth` ci-dessus
        };
    }
    return null;
}

function readS32Slot(args: InvocationArguments, slot: number): number | null {
    try { return args[slot].toInt32(); } catch { return null; }
}

/** `initialHealth` / `deniedDamage` : un entier NON NÉGATIF et plausible, sinon `null`.
 *  Rendre `null` plutôt qu'un nombre non validé est ce qui empêche une lecture fausse de passer
 *  pour une mesure (cf. le bloc ci-dessus). */
function readHealthSlot(args: InvocationArguments, slot: number): number | null {
    const v = readS32Slot(args, slot);
    if (v === null || v < 0 || v > HEALTH_MAX_PLAUSIBLE) return null;
    return v;
}

function ensureInstalled(): boolean {
    if (state.installed) return true;
    const klass = findClassAnywhere("IdunBattle.Operations", "AttackDamageOperation");
    if (!klass) { log("[hit-trace] AttackDamageOperation non résolue (pre-amorce ?)"); return false; }
    const mi = findMethodByParamCount(klass, "ExecuteHit", 8);
    if (!mi) { log("[hit-trace] ExecuteHit(8) introuvable"); return false; }
    let entry = methodEntry(mi.info);
    if (entry.isNull()) { try { entry = mi.info.readPointer(); } catch { return false; } }
    if (entry.isNull()) { log("[hit-trace] ExecuteHit entry null"); return false; }
    try {
        state.listener = Interceptor.attach(entry, {
            onEnter(args) {
                if (!capturing("hit")) return;
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
                    initialHealth: readHealthSlot(args, L.initialHealthSlot),
                    deniedDamage: readHealthSlot(args, L.initialHealthSlot + 1),
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

    // Le DÉTACHEMENT physique est différé au moment où plus AUCUN acteur n'est armé — sinon
    // le `hitTraceDisarm` d'un probe arracherait l'`Interceptor` sous les pieds d'un autre,
    // qui dumperait un seau tronqué sans erreur (#483). Appelé aussi quand un runner armé
    // est disposé (`purgeArmedForRunner`).
    onDisarmed("hit", () => {
        try { state.listener?.detach(); } catch { /* best effort */ }
        state.listener = null;
        state.installed = false;
    });

    /** Arme le hook. À appeler sur état STABLE (post-amorce).
     *  `runnerId` → armement NOMINATIF ; sans lui → GLOBAL (comportement historique). */
    ctx.rpc.hitTraceArm = (body?: { runnerId?: number }): unknown => {
        const ok = ensureInstalled();
        if (ok) arm("hit", body?.runnerId);
        return { ok, installed: state.installed, ...armedReport("hit", body?.runnerId) };
    };

    /** Désarme. Le buffer est conservé (hitTraceDump reste lisible). Détache SEULEMENT si
     *  plus personne n'est armé — sans `runnerId`, seul le GLOBAL est désarmé. */
    ctx.rpc.hitTraceDisarm = (body?: { runnerId?: number }): unknown => {
        disarm("hit", body?.runnerId);
        return {
            ok: true, installed: state.installed, fires: state.fires,
            ...armedReport("hit", body?.runnerId),
        };
    };

    /** Coups capturés. body: { runnerId?, limit?=200 } */
    ctx.rpc.hitTrace = (body?: { runnerId?: number; limit?: number }): unknown => {
        const lim = typeof body?.limit === "number" ? body.limit : 200;
        const all = buffers.entries(body?.runnerId);
        const report = armedReport("hit", body?.runnerId);
        return {
            ok: true, installed: state.installed,
            ...report,
            // `enabled` : alias historique de `on`. Il DIT désormais « la capture était-elle
            // ouverte POUR L'ORIGINE INTERROGÉE » — un booléen global s'y lisait comme une
            // garantie qu'il ne donnait pas. `armedRunners` publie l'état réel.
            enabled: report.on,
            fires: state.fires, captured: all.length,
            layout: state.layout, calibrationFailures: state.calibrationFailures,
            hits: all.slice(-Math.max(0, lim)),
        };
    };

    /** Ouvre/ferme la capture SANS toucher au hook physique. `runnerId` porte la même
     *  sémantique que sur `hitTraceArm`/`hitTraceDisarm`. */
    ctx.rpc.hitTraceSetEnabled = (
        body?: { on?: boolean; runnerId?: number },
    ): unknown => {
        if (body?.on !== false) {
            // Réinstalle si besoin : un `SetEnabled(false)` qui a fait tomber le dernier
            // acteur a détaché le hook (cf. `onDisarmed`) ; sans ce `ensureInstalled`, le
            // ré-armement rendrait `ok: true` sur un hook ABSENT — un vert qui ment.
            const ok = ensureInstalled();
            if (ok) arm("hit", body?.runnerId);
            return {
                ok, installed: state.installed,
                ...armedReport("hit", body?.runnerId),
            };
        }
        disarm("hit", body?.runnerId);
        return {
            ok: true, installed: state.installed,
            ...armedReport("hit", body?.runnerId),
        };
    };

    ctx.rpc.hitTraceReset = (body?: { runnerId?: number }): unknown => {
        buffers.clear(body?.runnerId);
        if (body?.runnerId === undefined) { state.seq = 0; state.fires = 0; }
        return { ok: true };
    };
}
