// Generic TRIGGERED-ABILITY tracer — l'equivalent "trigger" de ce que
// `statModSources` fait pour les auras stat-mod : voir QUELS triggered abilities
// sont evalues, POUR QUI, sur QUEL evenement, et s'ils firent.
//
// Generalisation de `overwatch-fix/hooks/trigger-observe.ts` (scope Overwatch)
// et de `dispatch-observe.ts` (forensique RVA/what-if) : ici on hooke le point
// GENERIQUE `IdunBattle.Entities.Abilities.BaseTriggeredAbility.ShouldTrigger`
// (2 params managed: AbilityEntities entities, EventTriggerType triggerType) qui
// est appele pour CHAQUE triggered ability a chaque evaluation d'evenement.
// Un seul hook -> tous les triggered abilities (overwatch, DoT, contre-attaques,
// reactions on-hit/on-death, heals reactifs, effets d'environnement...).
//
// Decodage (RE decompile-verifie, build gqfc5mff6c) :
//   - type d'ability = `*(int*)(this + 0x10)` -> `BaseTriggeredAbility.
//     get_AbilityStateReference @180fbcbe0` lit `AbilityType.op_Implicit(this+0x10)`.
//     Decode best-effort via TRIGGERED_ABILITY_NAMES ; le FQN de classe est
//     l'identifiant FIABLE (le nom decode peut differer si AbilityType != enum
//     TriggeredAbilityType) -> on emet les DEUX.
//   - contexte = AbilityEntities (args[1], struct dump.cs) : les champs Owner@0x18,
//     Target@0x10, CasterTile@0x40 sont des IEntity (references d'entite). On
//     resout l'entityId de chacune via id = *(int*)(entity + 0x10) (layout base
//     Entity, cf. forEachEntity match-state.ts : id@0x10, type@0x14).
//   - eventTriggerType = args[2] (int32) -> nom via EVENT_TRIGGER_TYPE_NAMES ;
//     retval onLeave = should-fire (bool).
//
// ON par defaut (auto-arme au register, cf. "debug features on by default"),
// cout par-fire minimal (quelques lectures + ring borne), tout en try/catch.
// Read-only : aucun `Interceptor.replace`.

import { Ctx } from "../controller.js";
import {
    class_get_name, class_get_namespace, cstr, findClassAnywhere,
    IL2CPP_MODULE_NAME, methodEntry,
} from "../il2cpp/helpers.js";
import { TRIGGERED_ABILITY_NAMES } from "../data/triggered-ability-names.js";
import { EVENT_TRIGGER_TYPE_NAMES } from "../data/event-trigger-type-names.js";
import { log } from "../runtime/diag.js";

const _il2cppLib = Process.findModuleByName(IL2CPP_MODULE_NAME);
const _classGetMethodFromName = (() => {
    if (!_il2cppLib) return null;
    const p = _il2cppLib.findExportByName("il2cpp_class_get_method_from_name");
    return p ? new NativeFunction(p, "pointer", ["pointer", "pointer", "int"]) : null;
})();

// Ring PARTAGE entre tous les agents. A 200, une seule etape de build en produit davantage
// (mesure du 2026-08-06 : 211 fires pour un 2v2, 1333 pour un 5v5), donc une lecture unique ne
// rend qu'une QUEUE ARBITRAIRE -- c'est ce qui faisait basculer le verdict de
// `probe_477r21r2b_activation_cache.py` entre deux passages du meme commit (#477-r28). Le probe
// s'en sort par un poll continu, mais la rafale d'init deborde encore 200 entrees en moins de
// 50 ms. Le cout d'un ring large est un tableau de N objets plats, borne et sans copie.
const FIRE_LOG_MAX = 4000;
/** offset du type d'ability sur l'instance BaseTriggeredAbility (cf. header). */
const ABILITY_TYPE_OFF = 0x10;
/** offsets AbilityEntities (dump.cs) — IEntity references. */
const AE = { target: 0x10, owner: 0x18, casterTile: 0x40 };
/** entityId sur une base Entity (cf. forEachEntity : id@0x10, type@0x14). */
const ENTITY_ID_OFF = 0x10;

/** resout l'entityId d'un champ IEntity de l'AbilityEntities (null si absent). */
function entityIdAt(entities: NativePointer, off: number): number | null {
    try {
        const e = entities.add(off).readPointer();
        if (e.isNull()) return null;
        return e.add(ENTITY_ID_OFF).readS32();
    } catch { return null; }
}

interface Fire {
    seq: number;
    /** nom decode (best-effort) du TriggeredAbilityType, ou null. */
    ability: string | null;
    /** type brut lu @this+0x10 (fiable pour correler). */
    rawType: number;
    /** FQN de la classe concrete du triggered ability (identifiant FIABLE). */
    cls: string;
    /** should-fire (retval) : true = l'ability va s'executer. */
    fired: boolean;
    /** EventTriggerType (enum int) qui a declenche l'evaluation. */
    event: number;
    /** nom de l'EventTriggerType (null si hors table). */
    eventName: string | null;
    /** entityId des IEntity du contexte (null si absent). */
    ownerId: number | null;
    targetId: number | null;
    casterTileId: number | null;
    ts: number;
}

interface TypeStats { fires: number; trueCount: number; falseCount: number; }

const state = {
    installed: false,
    enabled: true,
    seq: 0,
    listener: null as InvocationListener | null,
    fires: [] as Fire[],
    byType: {} as Record<string, TypeStats>,
};

function fqnOf(klassPtr: NativePointer): string {
    try {
        const ns = cstr(class_get_namespace(klassPtr) as NativePointer);
        const name = cstr(class_get_name(klassPtr) as NativePointer);
        return ns ? ns + "." + name : name;
    } catch { return "<read-failed>"; }
}

function bump(key: string, fired: boolean): void {
    let s = state.byType[key];
    if (!s) { s = { fires: 0, trueCount: 0, falseCount: 0 }; state.byType[key] = s; }
    s.fires++;
    if (fired) s.trueCount++; else s.falseCount++;
}

function ensureInstalled(): boolean {
    if (state.installed) return true;
    if (!_classGetMethodFromName) {
        log("[trigger-trace] il2cpp_class_get_method_from_name non exporte");
        return false;
    }
    const klass = findClassAnywhere(
        "IdunBattle.Entities.Abilities", "BaseTriggeredAbility");
    if (!klass) return false;   // classe pas encore resolue (pre-amorce) -> retry plus tard
    const nameBuf = Memory.allocUtf8String("ShouldTrigger");
    const mi = _classGetMethodFromName(klass, nameBuf, 2) as NativePointer;
    if (mi.isNull()) {
        log("[trigger-trace] ShouldTrigger(2) introuvable sur BaseTriggeredAbility");
        return false;
    }
    let entry = methodEntry(mi);
    if (entry.isNull()) { try { entry = mi.readPointer(); } catch { return false; } }
    if (entry.isNull()) { log("[trigger-trace] ShouldTrigger entry null"); return false; }
    try {
        state.listener = Interceptor.attach(entry, {
            onEnter(this: InvocationContext & {
                _tt?: { self: NativePointer; ent: NativePointer; evt: number };
            }, args) {
                if (!state.enabled) return;
                this._tt = { self: args[0], ent: args[1], evt: args[2].toInt32() };
            },
            onLeave(this: InvocationContext & {
                _tt?: { self: NativePointer; ent: NativePointer; evt: number };
            }, retval) {
                const c = this._tt;
                if (!c) return;
                const fired = retval.toInt32() !== 0;
                let cls = "<unknown>"; let rawType = -1;
                let ability: string | null = null;
                try { cls = fqnOf(c.self.readPointer()); } catch { /* keep */ }
                try {
                    rawType = c.self.add(ABILITY_TYPE_OFF).readS32();
                    ability = TRIGGERED_ABILITY_NAMES[rawType] ?? null;
                } catch { /* keep */ }
                const ownerId = entityIdAt(c.ent, AE.owner);
                const targetId = entityIdAt(c.ent, AE.target);
                const casterTileId = entityIdAt(c.ent, AE.casterTile);
                bump(ability ?? cls, fired);
                if (state.fires.length >= FIRE_LOG_MAX) state.fires.shift();
                state.fires.push({
                    seq: ++state.seq, ability, rawType, cls, fired,
                    event: c.evt, eventName: EVENT_TRIGGER_TYPE_NAMES[c.evt] ?? null,
                    ownerId, targetId, casterTileId, ts: Date.now(),
                });
            },
        });
    } catch (e) {
        log("[trigger-trace] attach FAILED: " + (e as Error).message);
        return false;
    }
    state.installed = true;
    log("[trigger-trace] hooke BaseTriggeredAbility.ShouldTrigger @ " + entry);
    return true;
}

export function register(ctx: Ctx): void {
    // Auto-arme best-effort au register. Les classes de bataille ne sont
    // souvent PAS resolues au chargement du script -> ensureInstalled retry
    // (lazy) au premier triggerTrace()/triggerTraceInstall apres amorce.
    try { ensureInstalled(); } catch (e) {
        log("[trigger-trace] auto-arm skip: " + (e as Error).message);
    }

    ctx.rpc.triggerTrace = (body?: { limit?: number }): unknown => {
        ensureInstalled();   // retry si pas encore arme (load-order)
        const lim = typeof body?.limit === "number" ? body.limit : 50;
        const recent = state.fires.slice(-Math.max(0, lim)).reverse();
        return {
            // `ringMax` est PUBLIE pour qu'un lecteur sache combien il peut demander sans
            // deviner : la constante ci-dessus a change, et un lecteur qui garderait 200 en dur
            // se croirait exhaustif en lisant 5 % du ring. Un lecteur qui ne le trouve pas
            // (hook anterieur) doit retomber sur 200 EN LE DISANT, jamais supposer la valeur.
            ok: true, installed: state.installed, enabled: state.enabled, ringMax: FIRE_LOG_MAX,
            totalFires: state.seq, byType: { ...state.byType }, recent,
        };
    };

    ctx.rpc.triggerTraceInstall = (): unknown =>
        ({ ok: ensureInstalled(), installed: state.installed });

    ctx.rpc.triggerTraceSetEnabled = (body?: { on?: boolean }): unknown => {
        state.enabled = body?.on !== false;
        return { ok: true, enabled: state.enabled };
    };

    ctx.rpc.triggerTraceReset = (): unknown => {
        state.fires = []; state.byType = {}; state.seq = 0;
        return { ok: true };
    };
}
