// fsm-input — parler au FSM de sélection du joueur en lui DÉSIGNANT les entités,
// au lieu de simuler une souris (#596).
//
// LA MESURE QUI FONDE CE MODULE
// ------------------------------
// Le raycast n'est PAS dans le FSM. Il vit dans `IdunBattle.View.Game.InputEntityAdapter`
// (`GetEntityAtObject`, `GetTileAtObject`), qui appelle le FSM avec les entités DÉJÀ
// résolues — signatures lues dans `frida/methods.tsv` du build :
//
//   UnitSelectionFsm$$HandleMouseButtonDownThisFrame(mousePosition: Vector3, entity: IEntity)
//   UnitSelectionFsm$$HandleMouseButtonHeldDown     (mousePosition: Vector3, entity: IEntity)
//   UnitSelectionFsm$$HandleMouseButtonUpThisFrame  (mousePosition: Vector3,
//                                                    entityHit: IEntity, tileHit: IEntity)
//
// `HandleMouseButtonUpThisFrame` est un dispatcher pur : l'état courant est en `fsm+0x10`,
// `mousePosition` est seulement RECOPIÉE dans un local puis passée au slot d'interface.
// ⇒ aucune projection écran n'est nécessaire, donc `#595-r2` (position d'un bouton) n'est
// pas un préalable, et on ne touche jamais la souris de l'utilisateur.
//
// CE MODULE EST GÉNÉRIQUE — IL NE CONNAÎT PAS LE DÉPLOIEMENT
// -----------------------------------------------------------
// Le déploiement n'est qu'un ÉTAT parmi ceux du même FSM
// (`UnitDeployment.UnitDeploymentState`), à côté de `NothingSelected.NormalState`,
// `OwnUnit_didntMove_didntAttack.FingerDownOnUnitForFirstTime`, `MovementSuggestionState`,
// `MovementTargetSelectedState`, `Swipe_AttackTargetSelected`, `InspectTileState`,
// `MachineSelection.*`… On expose donc l'ENTRÉE du FSM 1:1 (`fsmInput`) plus le geste
// composé (`fsmTap`), et c'est l'appelant qui sait ce qu'il veut faire. Un verbe
// « déployer » câblé ici aurait figé le module sur un seul écran.
//
// POURQUOI CAPTURER À LA CONSTRUCTION, ET PAS AU PREMIER CLIC
// ------------------------------------------------------------
// On pourrait attraper `this` au premier `HandleMouseButton*`. Ce serait exiger un CLIC
// HUMAIN par bataille avant de pouvoir agir — exactement le genre de dépendance que le
// dépôt proscrit (« ne jamais demander à un humain de cliquer »). Le `.ctor` fire à
// l'entrée en bataille, tout seul.
//
// ⚠ ET UN FSM CAPTURÉ PEUT ÊTRE PÉRIMÉ. Il en naît un par bataille. On mémorise donc le
// `matchState` que le `.ctor` a reçu (son 1er paramètre) et on le CONFRONTE à celui du
// runner live avant d'agir : discordance ⇒ REFUS nommé, jamais un appel à l'aveugle sur
// l'objet d'une bataille morte. Le FSM capturé est épinglé (et le précédent dépinglé), pour
// que cette comparaison porte sur un pointeur encore valide plutôt que sur de la mémoire
// libérée.

import {
    class_get_methods, class_get_name, findClassAnywhere, findCtorByParamCount, findMethod,
    fieldOffsetOr, method_get_name, method_get_param_count, methodParamClassName, readMsgClass, s,
} from "../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { forEachEntity } from "../game/match-state.js";
import { runnerOff } from "../game/runner.js";
import { state } from "../game/state.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

const NS = "IdunBattle.View.FSM";
const CLS = "UnitSelectionFsm";
/** Offset du champ « état courant » sur le FSM — lu au décompilé de
 *  `HandleMouseButtonUpThisFrame` (`plVar1 = *(longlong **)(this + 0x10)`). Offset
 *  RELATIF, pas une VA : il survit au changement de build tant que le champ ne bouge pas,
 *  et `fsmStatus` le rend LISIBLE (nom de classe) pour qu'un glissement se voie. */
const OFF_ETAT = 0x10;
/** Nombre de paramètres du `.ctor` (matchState, matchView, visualBattleQuery,
 *  stateMachineActions, timeQuery, touchInformation, backButtonManager, logger,
 *  gameModeSource). Discriminant plus sûr qu'un simple nom. */
const CTOR_PARAMS = 9;

const fsmClass = findClassAnywhere(NS, CLS);
const miDown = fsmClass ? findMethod(fsmClass, "HandleMouseButtonDownThisFrame") : null;
const miUp = fsmClass ? findMethod(fsmClass, "HandleMouseButtonUpThisFrame") : null;
const miHeld = fsmClass ? findMethod(fsmClass, "HandleMouseButtonHeldDown") : null;
const miBack = fsmClass ? findMethod(fsmClass, "HandleOnBackButtonPressed") : null;
const miEndTurn = fsmClass ? findMethod(fsmClass, "HandleOnEndTurnButtonTapped") : null;

/** Le FSM vivant + le `matchState` avec lequel il a été construit. */
let fsm: NativePointer | null = null;
let fsmMatchState: NativePointer | null = null;
let capturesFsm = 0;

function installCapture(): void {
    if (!fsmClass) return;
    const ctor = findCtorByParamCount(fsmClass, CTOR_PARAMS);
    if (!ctor) return;
    Interceptor.attach(ctor.ptr, {
        onEnter(args) {
            try {
                const nouveau = args[0] as NativePointer;
                if (nouveau.isNull()) return;
                if (fsm) { try { gcRoot.remove(fsm); } catch { /* best effort */ } }
                gcRoot.add(nouveau);
                fsm = nouveau;
                fsmMatchState = args[1] as NativePointer;   // 1er param managé
                capturesFsm++;
                send({ t: "diag", msg: "[fsm-input] UnitSelectionFsm capture #" + capturesFsm });
            } catch { /* ne jamais faire tomber le ctor du jeu */ }
        },
    });
}

/** Le `matchState` de la bataille VIVANTE, ou null si on ne peut pas le lire. */
function matchStateVivant(): NativePointer | null {
    if (!state.liveRunner) return null;
    try {
        const sp = state.liveRunner.add(runnerOff.state).readPointer();
        return sp.isNull() ? null : sp;
    } catch { return null; }
}

/** Nom de classe de l'état courant du FSM — le seul témoin lisible de ce qu'un tap fera. */
function etatCourant(): string | null {
    if (!fsm) return null;
    try {
        const e = fsm.add(OFF_ETAT).readPointer();
        return e.isNull() ? null : readMsgClass(e);
    } catch { return null; }
}

type Refus = { ok: false; error: string };

/** Discriminant EXPLICITE. Un test structurel (`"ok" in x`) sur un `NativePointer` est
 *  vrai par accident dès qu'un champ homonyme existe : on tague plutôt que de deviner. */
function estRefus(x: unknown): x is Refus {
    return typeof x === "object" && x !== null && (x as Refus).ok === false;
}

/** Le FSM est-il utilisable MAINTENANT ? Rend le pointeur, ou un refus NOMMÉ. */
function fsmUtilisable(): NativePointer | Refus {
    if (!fsmClass) {
        return { ok: false, error: NS + "." + CLS + " introuvable dans l'image" };
    }
    if (!fsm) {
        return { ok: false, error: "aucun UnitSelectionFsm capture -- il l'est a la "
            + "CONSTRUCTION, donc il faut ENTRER dans une bataille apres cet inject" };
    }
    const vivant = matchStateVivant();
    if (vivant === null) {
        return { ok: false, error: "aucune bataille vivante (state.liveRunner nul ou "
            + "matchState nul) -- rien a piloter" };
    }
    if (!fsmMatchState || !fsmMatchState.equals(vivant)) {
        return { ok: false, error: "FSM PERIME : il a ete construit pour matchState "
            + (fsmMatchState ? fsmMatchState.toString() : "null") + ", la bataille vivante "
            + "est " + vivant.toString() + " -- entrer dans la bataille courante le "
            + "reconstruira" };
    }
    return fsm;
}

/** Entité de la bataille vivante par son id ECS, ou `null` si absente.
 *  `null` en entrée est LÉGITIME (cliquer le vide) et rend le pointeur nul. */
function entiteParId(id: number | null | undefined): NativePointer | null | "absente" {
    if (id === null || id === undefined) return null;
    const sp = matchStateVivant();
    if (sp === null) return "absente";
    let trouve: NativePointer | null = null;
    forEachEntity(sp, (e, eid) => { if (eid === id) trouve = e; });
    return trouve ?? "absente";
}

/** Un `UnityEngine.Vector3` en mémoire — passé PAR POINTEUR, comme le décompilé le lit. */
function vecteur(v?: number[] | null): NativePointer {
    const p = Memory.alloc(12);
    p.writeFloat(v && v.length > 0 ? v[0] : 0);
    p.add(4).writeFloat(v && v.length > 1 ? v[1] : 0);
    p.add(8).writeFloat(v && v.length > 2 ? v[2] : 0);
    return p;
}

interface CorpsInput {
    kind?: string;
    entityId?: number | null;
    tileEntityId?: number | null;
    pos?: number[];
}

/** Résout les deux entités d'un corps d'appel, ou rend un refus nommé. */
function resoudre(body?: CorpsInput):
    { e: NativePointer; t: NativePointer } | Refus {
    const e = entiteParId(body?.entityId);
    if (e === "absente") {
        return { ok: false, error: "entityId " + body?.entityId + " introuvable dans la "
            + "bataille vivante -- lire les ids par `observeBattle` / `boardGraph`" };
    }
    const t = entiteParId(body?.tileEntityId);
    if (t === "absente") {
        return { ok: false, error: "tileEntityId " + body?.tileEntityId + " introuvable "
            + "dans la bataille vivante -- lire les ids par `boardGraph`" };
    }
    return { e: e ?? ptr(0), t: t ?? ptr(0) };
}

/** L'objet ÉTAT courant du FSM, et sa classe. */
function objetEtat(): { obj: NativePointer; klass: NativePointer } | null {
    if (!fsm) return null;
    try {
        const o = fsm.add(OFF_ETAT).readPointer();
        if (o.isNull()) return null;
        return { obj: o, klass: o.readPointer() };
    } catch { return null; }
}

/** Traduit une valeur JSON en argument IL2CPP.
 *
 *  ⚠ ON NE DEVINE PAS LES TYPES COMPOSÉS. Un `List<T>` ou un tableau exigeraient de
 *  construire un objet managé, donc de choisir une classe : c'est là qu'on écrirait une
 *  conversion plausible et FAUSSE. On REFUSE en le disant — le refus est une réponse. */
function argIl2cpp(v: unknown): NativePointer | Refus {
    if (v === null || v === undefined) return ptr(0);
    if (typeof v === "string") return createManagedString(v);
    if (typeof v === "boolean") {
        const p = Memory.alloc(1); p.writeU8(v ? 1 : 0); return p;
    }
    if (typeof v === "number") {
        if (Number.isInteger(v)) { const p = Memory.alloc(4); p.writeS32(v); return p; }
        const p = Memory.alloc(4); p.writeFloat(v); return p;
    }
    if (typeof v === "object") {
        const o = v as { entityId?: number; float?: number; long?: number };
        if (typeof o.entityId === "number") {
            const e = entiteParId(o.entityId);
            if (e === "absente") {
                return { ok: false, error: "entityId " + o.entityId + " introuvable" };
            }
            return e ?? ptr(0);
        }
        if (typeof o.float === "number") {
            const p = Memory.alloc(4); p.writeFloat(o.float); return p;
        }
        if (typeof o.long === "number") {
            const p = Memory.alloc(8); p.writeS64(o.long); return p;
        }
    }
    return { ok: false, error: "type d'argument non supporte : " + JSON.stringify(v)
        + " (acceptes : chaine, booleen, entier, {float}, {long}, {entityId}, null). "
        + "Les types COMPOSES (List<T>, tableaux) sont refuses volontairement : les "
        + "construire demanderait de choisir une classe, donc de deviner." };
}

export function register(ctx: Ctx): void {
    installCapture();

    /** CE QUE L'ÉTAT COURANT SAIT FAIRE — l'introspection qui rend le module adaptable.
     *  On atterrit dans un état inconnu (`MovementTargetSelectedState`, `InspectTileState`,
     *  `MachineSelection.*`…), on demande ses méthodes et leurs paramètres, puis on appelle.
     *  Aucune connaissance d'écran n'est câblée ici. Read-only. */
    ctx.rpc.fsmStateMethods = (): Promise<unknown> => queueOnMainThread(() => {
        const e = objetEtat();
        if (!e) return { ok: false, error: "aucun etat courant (FSM non capture)" };
        const out: Array<{ nom: string; params: string[] }> = [];
        const iter = Memory.alloc(Process.pointerSize);
        iter.writePointer(ptr(0));
        for (;;) {
            const mi = class_get_methods(e.klass, iter) as NativePointer;
            if (mi.isNull()) break;
            const n = method_get_param_count(mi) as number;
            const params: string[] = [];
            for (let i = 0; i < n; i++) params.push(methodParamClassName(mi, i) ?? "?");
            out.push({ nom: s(method_get_name(mi) as NativePointer), params });
        }
        return {
            ok: true,
            etat: s(class_get_name(e.klass) as NativePointer),
            methodes: out.sort((a, b) => a.nom.localeCompare(b.nom)),
        };
    });

    /** APPELER une méthode de l'ÉTAT COURANT, ou d'un SERVICE que cet état détient.
     *
     *  `target` est un nom de CHAMP de l'état (`_actions`, `_visualBattleQuery`,
     *  `_stateChanger`, `TouchInformation`…). Sans lui, on appelle l'état lui-même.
     *  Pourquoi ce cran : les états délèguent l'essentiel à leurs services — mesuré sur
     *  `UnitDeploymentState.OnUnitInHand`, qui ne fait que relayer l'id à deux méthodes de
     *  `_actions` (`IStateMachineActions`) avant de le stocker. Sans `target`, ces services
     *  ne sont atteignables qu'à travers la méthode qui les enveloppe, donc avec ses
     *  préconditions. Les champs se lisent par le RPC `classFields`.
     *
     *  Le champ est cherché sur la classe RÉELLE puis ses parents (les états dérivent tous
     *  de `BaseSelectionState`, qui déclare la totalité des services).
     *
     *  body: { method, args?: [...], target?: "<champ>" } — types acceptés : cf. `argIl2cpp`. */
    ctx.rpc.fsmStateInvoke = (
        body?: { method?: string; args?: unknown[]; target?: string },
    ): Promise<unknown> => queueOnMainThread(() => {
        const f = fsmUtilisable();
        if (estRefus(f)) return f;
        const e = objetEtat();
        if (!e) return { ok: false, error: "aucun etat courant" };

        let obj = e.obj;
        let klass = e.klass;
        const cible = body?.target;
        if (cible) {
            // Chemin POINTÉ : un service tient lui-même des services. Mesuré —
            // `StateMachineActions.UnitDeployment_PutUnitIntoHand` n'est qu'un relais vers
            // `_hud` (`IIdunGameHud`), et `TryRemoveUnitFromBoard` un relais vers `_views`.
            // Sans traversée, on ne peut ni les atteindre ni distinguer « le service est nul »
            // de « la méthode faute ».
            for (const seg of cible.split(".")) {
                const off = fieldOffsetOr(klass, seg, -1);
                if (off < 0) {
                    return { ok: false, error: "champ " + JSON.stringify(seg) + " absent de "
                        + s(class_get_name(klass) as NativePointer)
                        + " ni de ses parents -- `classFields` liste les champs" };
                }
                const svc = obj.add(off).readPointer();
                if (svc.isNull()) {
                    return { ok: false, error: "champ " + seg + " (+0x" + off.toString(16)
                        + ") de " + s(class_get_name(klass) as NativePointer)
                        + " est NUL -- le service n'est pas branche" };
                }
                obj = svc;
                klass = svc.readPointer();
            }
        }

        const nom = body?.method || "";
        const mr = findMethod(klass, nom);
        if (!mr) {
            return { ok: false, error: "methode " + JSON.stringify(nom) + " absente de "
                + s(class_get_name(klass) as NativePointer)
                + (cible ? " (via le champ " + cible + ")" : "")
                + " -- `fsmStateMethods` liste ce qui existe sur l'etat" };
        }
        const bruts = body?.args ?? [];
        const args: NativePointer[] = [];
        for (const v of bruts) {
            const a = argIl2cpp(v);
            if (estRefus(a)) return a;
            args.push(a as NativePointer);
        }
        const avant = etatCourant();
        invokeMethod(mr.info, obj, args.length ? args : null);
        return {
            ok: true, etat: avant, methode: nom, args: bruts.length, cible: cible ?? null,
            etatApres: etatCourant(),
        };
    });

    /** Ce que le FSM est, et ce qu'il vaut MAINTENANT. À lire AVANT d'agir : le nom de
     *  l'état courant dit ce qu'un tap va produire (déploiement, sélection, mouvement…).
     *  Read-only, ne touche à rien. */
    ctx.rpc.fsmStatus = (): Promise<unknown> => queueOnMainThread(() => {
        const u = fsmUtilisable();
        return {
            ok: true,
            classeTrouvee: fsmClass !== null,
            captures: capturesFsm,
            fsm: fsm ? fsm.toString() : null,
            fsmMatchState: fsmMatchState ? fsmMatchState.toString() : null,
            matchStateVivant: (matchStateVivant() ?? ptr(0)).toString(),
            etatCourant: etatCourant(),
            // `pret` est le VERDICT : utilisable tout de suite, ou la cause NOMMEE.
            pret: !estRefus(u),
            cause: estRefus(u) ? u.error : null,
            methodes: {
                down: miDown !== null, up: miUp !== null, held: miHeld !== null,
                back: miBack !== null, endTurn: miEndTurn !== null,
            },
        };
    });

    /** L'ENTRÉE DU FSM, 1:1 avec le natif. Aucun verbe métier ici.
     *  body: { kind: "down"|"up"|"held"|"back"|"endTurn",
     *          entityId?, tileEntityId?, pos?: [x,y,z] }
     *  `tileEntityId` n'est lu que par `up` (seul le natif `...UpThisFrame` le prend). */
    ctx.rpc.fsmInput = (body?: CorpsInput): Promise<unknown> => queueOnMainThread(() => {
        const f = fsmUtilisable();
        if (estRefus(f)) return f;
        const kind = (body?.kind || "").toLowerCase();

        if (kind === "back" || kind === "endturn") {
            const mi = kind === "back" ? miBack : miEndTurn;
            if (!mi) return { ok: false, error: "methode " + kind + " non resolue" };
            invokeMethod(mi.info, f as NativePointer, null);
            return { ok: true, kind, etatApres: etatCourant() };
        }

        const r = resoudre(body);
        if (estRefus(r)) return r;
        const { e, t } = r as { e: NativePointer; t: NativePointer };
        const pos = vecteur(body?.pos);
        const avant = etatCourant();

        if (kind === "down" || kind === "held") {
            const mi = kind === "down" ? miDown : miHeld;
            if (!mi) return { ok: false, error: "methode " + kind + " non resolue" };
            invokeMethod(mi.info, f as NativePointer, [pos, e]);
        } else if (kind === "up") {
            if (!miUp) return { ok: false, error: "methode up non resolue" };
            invokeMethod(miUp.info, f as NativePointer, [pos, e, t]);
        } else {
            return { ok: false, error: "kind inconnu : " + JSON.stringify(body?.kind)
                + " (attendu down|up|held|back|endTurn)" };
        }
        return { ok: true, kind, etatAvant: avant, etatApres: etatCourant() };
    });

    /** LE GESTE COMPOSÉ : down puis up, avec la MÊME `mousePosition`.
     *
     *  ⚠ L'ÉGALITÉ DES DEUX POSITIONS EST LE POINT À CONFRONTER. `IdunBattle.View.FSM.
     *  TouchInformation` n'expose que `ShouldMoveCamera` / `ShouldMoveCameraWithScrollWheel`,
     *  donc la position sert vraisemblablement à distinguer un TAP d'un SWIPE — deux
     *  positions identiques devraient donc lire comme un tap net. Plausible, PAS prouvé :
     *  si un tap ne porte pas, c'est la première hypothèse à mettre en cause, et
     *  `fsmInput` permet de jouer down/up séparément avec des positions choisies.
     *
     *  body: { entityId?, tileEntityId?, pos? } -> l'état du FSM avant / après. */
    ctx.rpc.fsmTap = (body?: CorpsInput): Promise<unknown> => queueOnMainThread(() => {
        const f = fsmUtilisable();
        if (estRefus(f)) return f;
        if (!miDown || !miUp) {
            return { ok: false, error: "HandleMouseButtonDown/UpThisFrame non resolues" };
        }
        const r = resoudre(body);
        if (estRefus(r)) return r;
        const { e, t } = r as { e: NativePointer; t: NativePointer };
        const pos = vecteur(body?.pos);
        const avant = etatCourant();
        invokeMethod(miDown.info, f as NativePointer, [pos, e]);
        const entreDeux = etatCourant();
        invokeMethod(miUp.info, f as NativePointer, [pos, e, t]);
        return {
            ok: true,
            etatAvant: avant, etatEntreDeux: entreDeux, etatApres: etatCourant(),
            // Le VERDICT ne se prend pas ici : un état inchangé peut être correct
            // (cliquer le vide). L'appelant confronte l'EFFET qu'il attendait.
            aChangeDEtat: avant !== etatCourant(),
        };
    });
}
