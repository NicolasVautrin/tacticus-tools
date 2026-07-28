// Observation du GATE D'IMMUNITE d'effet (#151 / residu #137).
//
// QUESTION TRANCHEE PAR CE HOOK — sur une cible portant `TerminatorArmour`,
// pendant la pose de `Pinned`, l'appel d'immunite fait par
// `IdunBattle.Operations.AddEffectOperation$$Execute` rend-il VRAI ou FAUX ?
//
// CE QUE LE DECOMPILE ETABLIT DEJA (a ne pas re-deriver) :
//
//   `IdunBattle.Operations.AddEffectOperation$$Execute` :
//       def = EffectsDatabase.Get(effectType)          // param_5
//       if (<dispatch dynamique 0x28>(def, target))    // param_3
//           return 0;                                  // ABANDON, aucun event
//       if (IsUnit(target) && UnitExtensions.HasFlag(target, 6 /* Dead */))
//           return 0;                                  // 2e et DERNIER abandon
//
//   Il n'y a donc QUE DEUX abandons dans `Execute`, et l'immunite est le premier.
//
//   `IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect(this, entity)` :
//       if (UnitExtensions.HasTrait(entity, 0x19 /* Immune */))
//           return this->get_CanBeImmuneTo();
//       return false;
//
//   C'est une CONJONCTION, et c'est le point que la fiche #137 avait reduit a son
//   premier terme. Elle explique la mesure ENTIERE si la cible porte le trait 25
//   AU RUNTIME : `Pinned.CanBeImmuneTo` vrai -> refuse ; `Stunned.CanBeImmuneTo`
//   faux -> passe ; cible sans le trait -> passe. #137 a cherche `Immune` dans le
//   GAMECONFIG et ne l'y a pas trouve — l'ensemble de traits RUNTIME peut differer.
//
// TROIS ISSUES POSSIBLES, et chacune designe une suite differente :
//   1. le gate fire et rend VRAI  -> l'etage natif du refus est IDENTIFIE ; reste a
//      dire POURQUOI `HasTrait(cible, 25)` est vrai (le `traitProbe` le dit) ;
//   2. le gate fire et rend FAUX  -> le refus vient d'ailleurs ; le seul autre
//      abandon d'`Execute` est le flag `Dead`, a verifier ensuite ;
//   3. le gate ne fire JAMAIS     -> soit `Execute` n'est pas atteinte (le refus est
//      EN AMONT, cote behaviour/selecteur), soit le corps appele n'est pas celui de
//      `BaseEffect` (donc une surcharge EXISTE, invisible des tables parce que
//      IL2CPP DEDUPLIQUE les corps identiques — cf. `docs/rl/case-170-get-priority.md`).
//   Le compteur `addEffectExecutes` separe 3a de 3b : s'il monte pendant qu'aucun
//   gate ne fire, `Execute` EST atteinte et le corps appele est ailleurs.
//
// `get_CanBeImmuneTo` n'est PAS hooke : il se DEDUIT. `hasTraitImmune == true` et
// `retval == false` => `CanBeImmuneTo` faux, sans trampoline supplementaire.
//
// Defaut OFF, jamais auto-arme (`docs` : seuls les diag LEGERS s'arment au register ;
// `UnitExtensions$$HasTrait` est un chemin CHAUD, d'ou `traitProbe` en opt-in et
// borne a la fenetre d'un `AddEffectOperation$$Execute` en cours).

import { Ctx } from "../controller.js";
import {
    class_get_name, class_get_namespace, cstr, findClassAnywhere, findMethod,
    findMethodByParamCount,
} from "../il2cpp/helpers.js";
import { EFFECT_TYPE_NAMES } from "../data/effect-type-names.js";
import { log } from "../runtime/diag.js";
import { queueOnMainThread } from "../runtime/queue.js";

/** `UnitTrait.Immune`, le litteral teste par `BaseEffect$$EntityIsImmuneToEffect`. */
const TRAIT_IMMUNE = 0x19;
const LOG_MAX = 200;
const TRAIT_LOG_MAX = 400;

interface ImmunityFire {
    /** FQN de la classe de l'effet-DEF (`this` du gate). */
    effectClass: string;
    entity: string;
    retval: boolean;
    /** Resultat de `HasTrait(entity, 25)` observe DANS le meme appel — n'est
     *  renseigne que si `traitProbe` est arme. `null` = non observe. */
    hasTraitImmune: boolean | null;
    /** Deduit : trait present mais gate faux => `get_CanBeImmuneTo` faux. */
    canBeImmuneTo: boolean | null;
    /** effectType de l'`AddEffectOperation$$Execute` englobante, si connue. */
    effectType: number | null;
    effectName: string | null;
    ts: number;
}

interface AddEffectFire {
    effectType: number;
    effectName: string;
    target: string;
    source: string;
    /** Retour d'`Execute` : 0 = ABANDON (immunite, cible morte) ou aucune entite
     *  creee ; non-nul = l'entite-effet a ete produite. */
    retval: string;
    aborted: boolean;
    /** Le gate d'immunite a-t-il fire pendant CETTE execution ? C'est ce qui
     *  separe « refus par immunite » de « refus en amont / autre corps ». */
    immunityGateFired: boolean;
    ts: number;
}

const obs = {
    enabled: false,
    traitProbe: false,
    listeners: [] as InvocationListener[],
    addEffectExecutes: 0,
    immunityGateCalls: 0,
    /** Fenetre courante : renseignee par `AddEffectOperation$$Execute.onEnter`,
     *  effacee au `onLeave`. Mono-thread (thread Unity) — pas de reentrance
     *  attendue, mais la pile la rend robuste si le natif en imbriquait. */
    window: [] as Array<{
        effectType: number; target: string; gateFired: boolean;
        traitImmune: boolean | null;
    }>,
    immunityLog: [] as ImmunityFire[],
    addEffectLog: [] as AddEffectFire[],
    /** Traits interroges sur la cible pendant une fenetre — tout id, pas
     *  seulement 25 : si le refus vient d'un AUTRE trait, il apparait ici. */
    traitLog: [] as Array<{
        entity: string; trait: number; retval: boolean; ts: number;
    }>,
};

function readClassFqn(objPtr: NativePointer): string {
    try {
        const klass = objPtr.readPointer();
        if (klass.isNull()) return "<null-klass>";
        const ns = cstr(class_get_namespace(klass) as NativePointer);
        const name = cstr(class_get_name(klass) as NativePointer);
        return ns ? ns + "." + name : name;
    } catch { return "<read-failed>"; }
}

function topWindow() {
    return obs.window.length ? obs.window[obs.window.length - 1] : null;
}

function hookAddEffectExecute(): boolean {
    const klass = findClassAnywhere(
        "IdunBattle.Operations", "AddEffectOperation");
    if (!klass) {
        log("[effect-immunity] AddEffectOperation non resolue");
        return false;
    }
    // `Execute(source, target, ?, effectType, ref <options>)` = 5 parametres
    // apres `this` (cf. le decompile en tete de fichier). On passe par le
    // compte de parametres pour ne pas attraper une surcharge voisine.
    const m = findMethodByParamCount(klass, "Execute", 5)
        || findMethod(klass, "Execute");
    if (!m || m.ptr.isNull()) {
        log("[effect-immunity] AddEffectOperation$$Execute introuvable");
        return false;
    }
    obs.listeners.push(Interceptor.attach(m.ptr, {
        onEnter(args) {
            obs.addEffectExecutes++;
            // args[0]=this, args[1]=param_2 (source), args[2]=param_3 (cible),
            // args[4]=param_5 (effectType).
            const effectType = args[4].toInt32();
            const target = args[2];
            obs.window.push({
                effectType, target: target.toString(),
                gateFired: false, traitImmune: null,
            });
            const ictx = (this as Record<string, unknown>);
            ictx.__ei_type = effectType;
            ictx.__ei_target = target.toString();
            ictx.__ei_source = args[1].toString();
        },
        onLeave(retval) {
            const w = obs.window.pop();
            const ictx = (this as Record<string, unknown>);
            const effectType = (ictx.__ei_type as number) ?? -1;
            if (obs.addEffectLog.length < LOG_MAX) {
                obs.addEffectLog.push({
                    effectType,
                    effectName: EFFECT_TYPE_NAMES[effectType] || "<?>",
                    target: (ictx.__ei_target as string) || "<?>",
                    source: (ictx.__ei_source as string) || "<?>",
                    retval: retval.toString(),
                    aborted: retval.isNull(),
                    immunityGateFired: !!(w && w.gateFired),
                    ts: Date.now(),
                });
            }
        },
    }));
    return true;
}

function hookImmunityGate(): boolean {
    const klass = findClassAnywhere(
        "IdunBattle.Entities.Effects", "BaseEffect");
    if (!klass) {
        log("[effect-immunity] BaseEffect non resolue");
        return false;
    }
    const m = findMethod(klass, "EntityIsImmuneToEffect");
    if (!m || m.ptr.isNull()) {
        log("[effect-immunity] BaseEffect$$EntityIsImmuneToEffect introuvable");
        return false;
    }
    obs.listeners.push(Interceptor.attach(m.ptr, {
        onEnter(args) {
            obs.immunityGateCalls++;
            const w = topWindow();
            if (w) w.gateFired = true;
            const ictx = (this as Record<string, unknown>);
            ictx.__ei_cls = readClassFqn(args[0]);
            ictx.__ei_ent = args[1].toString();
        },
        onLeave(retval) {
            const ictx = (this as Record<string, unknown>);
            const result = retval.toInt32() !== 0;
            const w = topWindow();
            const traitImmune = w ? w.traitImmune : null;
            if (obs.immunityLog.length < LOG_MAX) {
                obs.immunityLog.push({
                    effectClass: (ictx.__ei_cls as string) || "<?>",
                    entity: (ictx.__ei_ent as string) || "<?>",
                    retval: result,
                    hasTraitImmune: traitImmune,
                    // Deduction, pas une mesure directe : le gate ne rend vrai
                    // QUE si les deux conjoints le sont.
                    canBeImmuneTo: traitImmune === null
                        ? null : (traitImmune ? result : null),
                    effectType: w ? w.effectType : null,
                    effectName: w
                        ? (EFFECT_TYPE_NAMES[w.effectType] || "<?>") : null,
                    ts: Date.now(),
                });
            }
        },
    }));
    return true;
}

/** Sonde CHAUDE : `UnitExtensions$$HasTrait` est appele en permanence. Le corps
 *  sort immediatement hors d'une fenetre `AddEffectOperation$$Execute`, ce qui
 *  borne le cout au strict necessaire — et le log ne retient que les appels
 *  portant sur la CIBLE de la pose en cours. */
function hookHasTrait(): boolean {
    const klass = findClassAnywhere(
        "IdunBattle.Entities", "UnitExtensions");
    if (!klass) {
        log("[effect-immunity] UnitExtensions non resolue");
        return false;
    }
    const m = findMethodByParamCount(klass, "HasTrait", 2)
        || findMethod(klass, "HasTrait");
    if (!m || m.ptr.isNull()) {
        log("[effect-immunity] UnitExtensions$$HasTrait introuvable");
        return false;
    }
    obs.listeners.push(Interceptor.attach(m.ptr, {
        onEnter(args) {
            const w = topWindow();
            if (!w) return;                       // hors fenetre : cout nul
            const ictx = (this as Record<string, unknown>);
            ictx.__ei_ht_ent = args[0].toString();
            ictx.__ei_ht_trait = args[1].toInt32();
        },
        onLeave(retval) {
            const ictx = (this as Record<string, unknown>);
            const ent = ictx.__ei_ht_ent as string | undefined;
            if (ent === undefined) return;
            const w = topWindow();
            if (!w) return;
            const trait = ictx.__ei_ht_trait as number;
            const result = retval.toInt32() !== 0;
            if (trait === TRAIT_IMMUNE && ent === w.target) {
                w.traitImmune = result;
            }
            if (obs.traitLog.length < TRAIT_LOG_MAX) {
                obs.traitLog.push(
                    { entity: ent, trait, retval: result, ts: Date.now() });
            }
        },
    }));
    return true;
}

function detachAll(): void {
    for (const l of obs.listeners) {
        try { l.detach(); } catch { /* */ }
    }
    obs.listeners = [];
    obs.window = [];
}

export function register(ctx: Ctx): void {
    ctx.rpc.effectImmunityObserveEnable = (
        opts?: { traitProbe?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (obs.enabled) {
            return { ok: true, alreadyEnabled: true,
                listeners: obs.listeners.length,
                traitProbe: obs.traitProbe };
        }
        const wantTrait = !!(opts && opts.traitProbe);
        const okExec = hookAddEffectExecute();
        const okGate = hookImmunityGate();
        const okTrait = wantTrait ? hookHasTrait() : true;
        try { Interceptor.flush(); } catch { /* */ }
        const ok = okExec && okGate && okTrait;
        if (!ok) detachAll();
        obs.enabled = ok;
        obs.traitProbe = ok && wantTrait;
        return { ok, addEffectExecute: okExec, immunityGate: okGate,
            traitProbe: obs.traitProbe, listeners: obs.listeners.length };
    });

    ctx.rpc.effectImmunityObserveDisable = (): unknown => {
        detachAll();
        obs.enabled = false;
        obs.traitProbe = false;
        return { ok: true };
    };

    ctx.rpc.effectImmunityObserveStatus = (): unknown => ({
        enabled: obs.enabled,
        traitProbe: obs.traitProbe,
        listeners: obs.listeners.length,
        // Le couple de compteurs EST le discriminant de l'issue 3 : des
        // `Execute` sans aucun appel de gate => le corps appele n'est pas celui
        // de `BaseEffect` (surcharge dedupliquee), ou `Execute` abandonne avant.
        addEffectExecutes: obs.addEffectExecutes,
        immunityGateCalls: obs.immunityGateCalls,
        addEffectLog: obs.addEffectLog.slice(-60),
        immunityLog: obs.immunityLog.slice(-60),
        traitLog: obs.traitLog.slice(-120),
    });

    ctx.rpc.effectImmunityObserveReset = (): unknown => {
        obs.addEffectExecutes = 0;
        obs.immunityGateCalls = 0;
        obs.addEffectLog = [];
        obs.immunityLog = [];
        obs.traitLog = [];
        obs.window = [];
        return { ok: true };
    };
}
