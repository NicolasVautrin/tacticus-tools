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
    class_get_methods, class_get_name, class_is_valuetype, findClassAnywhere,
    findCtorByParamCount, findMethod, findMethodByParamCount, fieldOffsetOr, method_get_name, method_get_param_count,
    method_get_return_type, methodParamClassName, readIl2cppString, readMsgClass, s,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { EntityType, forEachEntity } from "../game/match-state.js";
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

// ------------------------------------------------------------------ LA TRACE
//
// POURQUOI ELLE EXISTE : on ne DEVINE pas ce qu'attend `OnFingerDownThisFrameInternal`.
// `fsmTap` sur une tuile de spawn libre, unité en main, ne produit RIEN — et trois
// hypothèses restaient ouvertes (entité tuile vs entité point-de-spawn ; `mousePosition`
// significative ou non ; down seul vs down+up). Aucune ne se tranche au décompilé : elles se
// tranchent en LISANT ce que le jeu passe quand un humain clique. C'est la seule voie qui ne
// suppose rien.
//
// Les deux points d'entrée du FSM sont hookés parce qu'ils portent des arguments DIFFÉRENTS :
// `Down` n'a qu'une entité, `Up` a le COUPLE `entityHit`/`tileHit` — précisément la
// distinction en cause. Coût nul hors clic : ce sont des méthodes d'entrée souris, pas un
// chemin chaud (≠ les getters d'UI que le dépôt proscrit de hooker).

interface DescEntite {
    ptr: string; classe: string | null; id: number | null; type: number | null;
}

const TRACE_MAX = 60;
const trace: Array<Record<string, unknown>> = [];
let traceTotal = 0;

/** Décrit un `IEntity` reçu du jeu. Les champs `id`/`type` sont lus aux offsets que
 *  `forEachEntity` utilise déjà (16 / 20) — s'ils ne sont pas lisibles, ils sortent `null`,
 *  jamais un zéro. */
function decrireEntite(p: NativePointer | null): DescEntite | null {
    if (!p || p.isNull()) return null;
    const d: DescEntite = { ptr: p.toString(), classe: null, id: null, type: null };
    try { d.classe = readMsgClass(p); } catch { /* garde null */ }
    try { d.id = p.add(16).readS32(); } catch { /* garde null */ }
    try { d.type = p.add(20).readS32(); } catch { /* garde null */ }
    return d;
}

function lireVec3(p: NativePointer | null): number[] | null {
    if (!p || p.isNull()) return null;
    try { return [p.readFloat(), p.add(4).readFloat(), p.add(8).readFloat()]; }
    catch { return null; }
}

function noter(e: Record<string, unknown>): void {
    traceTotal++;
    trace.push(e);
    if (trace.length > TRACE_MAX) trace.shift();
}

function installTrace(): void {
    if (!fsmClass) return;
    if (miDown) {
        Interceptor.attach(miDown.ptr, {
            onEnter(args) {
                try {
                    noter({ quoi: "down", frame: state.frameNo, etat: etatCourant(),
                            pos: lireVec3(args[1] as NativePointer),
                            entity: decrireEntite(args[2] as NativePointer) });
                } catch { /* ne jamais faire tomber l'input du jeu */ }
            },
        });
    }
    if (miUp) {
        Interceptor.attach(miUp.ptr, {
            onEnter(args) {
                try {
                    noter({ quoi: "up", frame: state.frameNo, etat: etatCourant(),
                            pos: lireVec3(args[1] as NativePointer),
                            entity: decrireEntite(args[2] as NativePointer),
                            tile: decrireEntite(args[3] as NativePointer) });
                } catch { /* idem */ }
            },
        });
    }
}

// -------------------------------------------------- EXECUTER DEPUIS L'INPUT DU JEU
//
// POURQUOI. Rejouer les arguments EXACTS du jeu (entité tuile, `tileHit` identique,
// `mousePosition` capturée) ne produit rien, alors que le clic humain place l'unité. Les
// arguments sont donc démontrés justes et il ne reste qu'une variable : le MOMENT dans la
// frame. `queueOnMainThread` s'exécute depuis la pompe ; le jeu, lui, appelle depuis son
// propre traitement d'input — et c'est là que la construction du visuel réussit.
//
// LE POINT D'ANCRAGE. `BaseSelectionState.OnFingerDownThisFrame` appelle le service
// `TouchInformation` (champ `+0x38`) AVANT de dispatcher vers l'état : ce service vit donc
// dans la phase d'input. On draine la file depuis lui.
//
// ⚠ CE HOOK PEUT NE PAS BATTRE À CHAQUE FRAME, et le module ne le SUPPOSE pas : `fsmStatus`
// publie son compteur d'appels, et une action non drainée sort en REFUS nommé au bout du
// délai plutôt qu'en attente muette. Si le compteur reste à 0, c'est le hook qu'il faut
// changer — pas l'hypothèse.

const touchClass = findClassAnywhere(NS, "TouchInformation");
const miShouldMove = touchClass ? findMethod(touchClass, "ShouldMoveCamera") : null;
let appelsInput = 0;
const fileInput: Array<() => void> = [];

function installDrainInput(): void {
    if (!miShouldMove) return;
    Interceptor.attach(miShouldMove.ptr, {
        onEnter() {
            appelsInput++;
            if (!fileInput.length) return;
            const f = fileInput.shift();
            // UNE seule action par battement : on ne réentre pas en rafale dans le jeu.
            try { f!(); } catch { /* l'action rapporte elle-meme son echec */ }
        },
    });
}

/** Exécute `fn` depuis la phase d'input du jeu. Rend sa valeur, ou un REFUS nommé si le
 *  point d'ancrage n'a pas battu dans le délai — jamais une attente muette. */
function depuisInput<T>(fn: () => T, delaiMs = 4000): Promise<T | Refus> {
    if (!miShouldMove) {
        return Promise.resolve({ ok: false as const,
            error: NS + ".TouchInformation.ShouldMoveCamera non resolue -- pas de point "
                + "d'ancrage dans la phase d'input" });
    }
    return new Promise((resolve) => {
        let fini = false;
        const action = (): void => {
            if (fini) return;
            fini = true;
            try { resolve(fn()); }
            catch (e) { resolve({ ok: false as const,
                error: "depuis l'input : " + (e as Error).message }); }
        };
        fileInput.push(action);
        setTimeout(() => {
            if (fini) return;
            fini = true;
            const i = fileInput.indexOf(action);
            if (i >= 0) fileInput.splice(i, 1);
            resolve({ ok: false as const,
                error: "le point d'ancrage d'input n'a pas battu en " + delaiMs + " ms ("
                    + appelsInput + " appel(s) depuis l'inject) -- action NON JOUEE" });
        }, delaiMs);
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
    const t = chercherEntite(id);
    if (t === null || t === "absente") return t;
    return t.ptr;
}

/** L'entité ET son `EntityType` — c'est le type qui permet de REFUSER un id de pied. */
function chercherEntite(
    id: number | null | undefined,
): { ptr: NativePointer; type: number } | null | "absente" {
    if (id === null || id === undefined) return null;
    const sp = matchStateVivant();
    if (sp === null) return "absente";
    let trouve: { ptr: NativePointer; type: number } | null = null;
    forEachEntity(sp, (e, eid, ty) => { if (eid === id) trouve = { ptr: e, type: ty }; });
    return trouve ?? "absente";
}

/** Motif de REFUS si `id` désigne un `UnitFoot`, sinon `null`.
 *
 *  ⚠ POURQUOI CE REFUS EXISTE, ET POURQUOI IL EST EXÉCUTABLE. `observeBattle` publie
 *  `entityId` = le PIED et `squadId` = l'ESCOUADE ; le FSM, `applyAction` et
 *  `decisionView` adressent tous l'ESCOUADE. Sur une unité mono-pied l'écart vaut +1
 *  EXACTEMENT, donc l'id fautif désigne une AUTRE ENTITÉ VALIDE : rien ne lève, le geste
 *  part, et il ne se passe rien. Mesuré le 2026-08-09 — six gestes d'attaque sans effet,
 *  jusqu'à ce que `_unit.ToString()` rende `[Unit 101, unitId: spaceBlackmane]` là où
 *  `observeBattle` disait 102. Une note en commentaire n'aurait rien arrêté. */
function refusSiPied(id: number | null | undefined, champ: string): Refus | null {
    const t = chercherEntite(id);
    if (t === null || t === "absente") return null;      // absent : dit ailleurs
    if (t.type !== EntityType.UnitFoot) return null;
    return { ok: false, error: champ + " " + id + " designe un UnitFoot (le PIED), pas "
        + "l'unite -- le FSM adresse l'ESCOUADE. Passer `squadId` d'`observeBattle`, ou "
        + "`unitId`/`targetId` de `decisionView`. Sur une unite mono-pied l'ecart vaut "
        + "+1, donc l'id fautif designe une entite VALIDE et le geste echoue en SILENCE" };
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
    const pied = refusSiPied(body?.entityId, "entityId")
        ?? refusSiPied(body?.tileEntityId, "tileEntityId");
    if (pied) return pied;
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
/** ⚠ EXPORTEE (#992) pour `features/view-command.ts`, qui invoque des commandes du jeu et a
 *  besoin EXACTEMENT de la meme coercition. La recopier aurait fait diverger en silence deux
 *  tables d'arguments -- le depot proscrit de recopier le voisin de forme.
 *  RESIDU : sa place est dans `il2cpp/`, pas dans un module de FEATURE. Le deplacement touche
 *  un fichier partage, il se fera dans une tranche qui n'a pas une fenetre en attente. */
export function argIl2cpp(v: unknown): NativePointer | Refus {
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
        const o = v as {
            entityId?: number; float?: number; long?: number;
            brut?: string; octets?: number;
        };
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
        // `{brut: "0x0101", octets: 2}` — un TYPE VALEUR passe TEL QUEL.
        //
        // ⚠ POURQUOI CETTE FORME EXISTE (#992). `il2cpp_runtime_invoke` attend, pour un type
        // valeur, un POINTEUR VERS LA VALEUR BRUTE -- pas un objet boxe. Les formes ci-dessus
        // couvrent les primitives, mais pas un `Nullable<T>` ni un petit `struct` : les
        // fabriquer demanderait de savoir OU est `hasValue`, donc de deviner une disposition.
        // Mesure : `ViewCommandExecutor$$StartCampaignMatch` prend
        // `enemyIsAiControlled : Nullable<Boolean>` et l'UI y passe `0x0101` -- les deux octets
        // a 1, donc les deux lectures possibles CONCORDENT et la disposition reste NON TRANCHEE.
        // On transporte donc les octets OBSERVES tels quels, au lieu de les reconstruire depuis
        // une hypothese : c'est « rejouer une valeur mesuree », pas « composer une valeur
        // plausible ». Le jour ou un `0x0001` sera observe, la disposition se lira sans que ce
        // code change.
        if (typeof o.brut === "string") {
            const n = typeof o.octets === "number" ? o.octets : 0;
            if (n < 1 || n > 32) {
                return { ok: false, error: "`brut` exige `octets` entre 1 et 32 (recu : "
                    + String(o.octets) + ") -- la largeur ne se devine pas depuis la chaine" };
            }
            const hex = o.brut.replace(/^0x/i, "");
            if (!/^[0-9a-fA-F]+$/.test(hex) || hex.length !== n * 2) {
                return { ok: false, error: "`brut` doit etre exactement " + (n * 2)
                    + " chiffres hexadecimaux pour " + n + " octet(s) -- recu "
                    + JSON.stringify(o.brut) + ". Un remplissage implicite ecrirait des octets "
                    + "que personne n'a mesures." };
            }
            const p = Memory.alloc(n);
            // Petit-boutiste : `0x0101` decrit les octets DANS L'ORDRE OU LE CAPTEUR LES A LUS,
            // donc on ecrit du poids fort vers le poids faible, a l'envers.
            for (let i = 0; i < n; i++) {
                p.add(n - 1 - i).writeU8(parseInt(hex.substr(i * 2, 2), 16));
            }
            return p;
        }
    }
    return { ok: false, error: "type d'argument non supporte : " + JSON.stringify(v)
        + " (acceptes : chaine, booleen, entier, {float}, {long}, {entityId}, "
        + "{brut,octets}, null). "
        + "Les types COMPOSES (List<T>, tableaux) sont refuses volontairement : les "
        + "construire demanderait de choisir une classe, donc de deviner." };
}

/** Décode la valeur de retour d'un `il2cpp_runtime_invoke`.
 *
 *  ⚠ POURQUOI CE CODE EXISTE. `IdunGameHud.UnitDeployment_TryPlaceUnitOnBoard(String,
 *  Boolean) -> Boolean` s'exécutait SANS erreur et SANS effet : en jetant la valeur de
 *  retour, on rendait « a refusé » et « a marché » INDISCERNABLES — exactement le vice
 *  qu'on reproche à `uiClick`, reproduit dans notre propre outil.
 *
 *  ⚠ ET IL DIT CE QU'IL NE SAIT PAS LIRE. `runtime_invoke` rend un objet BOXÉ pour un type
 *  valeur (charge utile à +0x10, cf. l'en-tête de 0x10 sur tout ValueType) ; les types que
 *  la table ci-dessous ne couvre pas sortent en `decode: false` avec leur nom de type et le
 *  pointeur brut. Inventer une lecture plausible serait pire que de ne rien rendre. */
export function decoderRetour(mi: NativePointer, res: NativePointer): Record<string, unknown> {
    let nom = "?";
    let estValeur = false;
    // ⚠ `method_get_return_type` et `class_is_valuetype` sont des exports POSSIBLEMENT NULS
    // (résolus par IIFE dans `helpers.ts` : l'export manque sur certains builds). Sans eux
    // on ne PEUT pas nommer le type — on le DIT, on ne rend pas un type inventé.
    const litType = method_get_return_type;
    const estVT = class_is_valuetype;
    if (!litType || !estVT) {
        return { type: null, decode: false, objet: res.toString(),
                 note: "type de retour NON MESURE : method_get_return_type / "
                     + "class_is_valuetype absents de cette image" };
    }
    try {
        const rt = litType(mi) as NativePointer;
        const rc = type_get_class_or_element_class(rt) as NativePointer;
        nom = s(class_get_name(rc) as NativePointer);
        estValeur = (estVT(rc) as number) !== 0;
    } catch { /* nom reste "?" */ }

    if (nom === "Void") return { type: "Void", decode: true, valeur: null };
    if (res.isNull()) return { type: nom, decode: true, valeur: null };

    if (estValeur) {
        const p = res.add(0x10);              // charge utile derriere l'en-tete de boxe
        try {
            switch (nom) {
                case "Boolean": return { type: nom, decode: true, valeur: p.readU8() !== 0 };
                case "Byte": return { type: nom, decode: true, valeur: p.readU8() };
                case "SByte": return { type: nom, decode: true, valeur: p.readS8() };
                case "Int16": return { type: nom, decode: true, valeur: p.readS16() };
                case "UInt16": return { type: nom, decode: true, valeur: p.readU16() };
                case "Int32": return { type: nom, decode: true, valeur: p.readS32() };
                case "UInt32": return { type: nom, decode: true, valeur: p.readU32() };
                case "Int64": return { type: nom, decode: true, valeur: p.readS64().toString() };
                case "Single": return { type: nom, decode: true, valeur: p.readFloat() };
                case "Double": return { type: nom, decode: true, valeur: p.readDouble() };
                default: break;
            }
        } catch { /* tombe dans le non-decode */ }
        return { type: nom, decode: false, boxe: res.toString(),
                 note: "type valeur non couvert -- lire a +0x10 si besoin" };
    }

    if (nom === "String") {
        try { return { type: nom, decode: true, valeur: readIl2cppString(res) }; }
        catch { /* tombe dans le non-decode */ }
    }
    // Type reference : le POINTEUR est la seule chose vraie qu'on puisse rendre.
    let classeReelle: string | null = null;
    try { classeReelle = readMsgClass(res); } catch { /* garde null */ }
    return { type: nom, decode: false, objet: res.toString(), classeReelle,
             note: "type reference -- objet rendu par pointeur, non deserialise" };
}

interface Cible { obj: NativePointer; klass: NativePointer }

/** Suit un chemin `target` depuis un objet de départ. Deux formes de segment :
 *
 *    `champ`     DÉRÉFÉRENCE le champ (cherché sur la classe réelle puis ses parents)
 *    `methode()` APPELLE une méthode sans paramètre et continue sur son résultat
 *
 *  ⚠ POURQUOI LE SEGMENT APPELANT EXISTE. Mesuré : `MenuSystems+0x188` est
 *  `unitDeploymentHud : IMenu<UnitDeploymentHud>` — un WRAPPER. Le jeu obtient l'instance
 *  concrète par un appel de propriété, pas par un champ de plus. Sans ce segment, la
 *  traversée s'arrête sur le wrapper et tout ce qui vit derrière reste hors d'atteinte.
 *
 *  ⚠ ET ELLE REFUSE DE TRAVERSER UN TYPE VALEUR. `runtime_invoke` rend un objet BOXÉ pour un
 *  type valeur ; en continuer la traversée lirait la classe de la BOÎTE et donnerait un
 *  chemin plausible et faux. On refuse en le nommant. */
function traverser(depart: Cible, chemin?: string): Cible | Refus {
    let { obj, klass } = depart;
    if (!chemin) return { obj, klass };
    for (const brut of chemin.split(".")) {
        const seg = brut.trim();
        if (!seg) continue;
        const nomClasse = (): string => {
            try { return s(class_get_name(klass) as NativePointer); } catch { return "?"; }
        };

        if (seg.endsWith("()")) {
            const nom = seg.slice(0, -2);
            // ⚠ SÉLECTION PAR ARITÉ, PAS PAR NOM. Mesuré : `Menu<T>` porte DEUX `Get` —
            // `Get()` et `Get(Transform)` — et `findMethod` rend la PREMIÈRE trouvée, ici
            // la mauvaise. Un segment de chemin ne passe aucun argument : c'est donc
            // l'arité 0 qu'on cherche, explicitement.
            const mr = findMethodByParamCount(klass, nom, 0);
            if (!mr) {
                const parNom = findMethod(klass, nom);
                return { ok: false, error: "segment appelant " + JSON.stringify(seg)
                    + " : aucune surcharge SANS PARAMETRE de " + JSON.stringify(nom)
                    + " sur " + nomClasse()
                    + (parNom
                        ? " (il en existe une a " + (method_get_param_count(parNom.info) as number)
                          + " parametre(s), qu'un segment de chemin ne peut pas appeler)"
                        : "")
                    + " -- `fsmStateMethods` avec le meme `target` liste ce qui existe" };
            }
            // Un type valeur reviendrait BOXÉ : on ne traverse pas une boîte.
            const litType = method_get_return_type;
            const estVT = class_is_valuetype;
            if (litType && estVT) {
                try {
                    const rc = type_get_class_or_element_class(
                        litType(mr.info) as NativePointer) as NativePointer;
                    if ((estVT(rc) as number) !== 0) {
                        return { ok: false, error: "segment appelant " + JSON.stringify(seg)
                            + " rend un TYPE VALEUR (" + s(class_get_name(rc) as NativePointer)
                            + ") -- on ne traverse pas une boite ; lire la valeur par "
                            + "`fsmStateInvoke` sans `target` au-dela" };
                    }
                } catch { /* on tente l'appel quand meme */ }
            }
            const res = invokeMethod(mr.info, obj, null);
            if (res.isNull()) {
                return { ok: false, error: "segment appelant " + seg + " sur " + nomClasse()
                    + " a rendu NUL -- rien a traverser au-dela" };
            }
            obj = res;
            klass = res.readPointer();
            continue;
        }

        const off = fieldOffsetOr(klass, seg, -1);
        if (off < 0) {
            return { ok: false, error: "champ " + JSON.stringify(seg) + " absent de "
                + nomClasse() + " ni de ses parents -- `classFields` liste les champs "
                + "(un segment APPELANT s'ecrit `nom()`)" };
        }
        const svc = obj.add(off).readPointer();
        if (svc.isNull()) {
            return { ok: false, error: "champ " + seg + " (+0x" + off.toString(16) + ") de "
                + nomClasse() + " est NUL -- le service n'est pas branche" };
        }
        obj = svc;
        klass = svc.readPointer();
    }
    return { obj, klass };
}

export function register(ctx: Ctx): void {
    installCapture();
    installTrace();
    installDrainInput();

    /** CE QUE LE JEU PASSE VRAIMENT au FSM quand un HUMAIN clique. Read-only.
     *  body: { clear?: true } -> { ok, total, gardees, entrees: [...] }
     *
     *  `total` compte TOUS les appels depuis l'inject, `entrees` n'en garde que les 60
     *  derniers : un compte qui n'égale pas la longueur dit qu'on a perdu le début, au lieu
     *  de le laisser croire complet. */
    ctx.rpc.fsmTrace = (
        body?: { clear?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        const entrees = trace.slice();
        if (body?.clear) { trace.length = 0; traceTotal = 0; }
        return {
            ok: true,
            armee: { down: miDown !== null, up: miUp !== null },
            total: traceTotal,
            gardees: entrees.length,
            plafond: TRACE_MAX,
            entrees,
        };
    });

    /** CE QUE L'ÉTAT COURANT SAIT FAIRE — l'introspection qui rend le module adaptable.
     *  On atterrit dans un état inconnu (`MovementTargetSelectedState`, `InspectTileState`,
     *  `MachineSelection.*`…), on demande ses méthodes et leurs paramètres, puis on appelle.
     *  Aucune connaissance d'écran n'est câblée ici. Read-only. */
    ctx.rpc.fsmStateMethods = (
        body?: { target?: string },
    ): Promise<unknown> => queueOnMainThread(() => {
        const e = objetEtat();
        if (!e) return { ok: false, error: "aucun etat courant (FSM non capture)" };
        // MÊME `target` que `fsmStateInvoke` : sans ça, on ne peut pas DÉCOUVRIR le nom à
        // appeler sur un objet qu'on vient d'atteindre — et un chemin appelant se réduirait
        // à deviner un accesseur.
        const t = traverser(e, body?.target);
        if (estRefus(t)) return t;
        const { klass } = t as Cible;
        const out: Array<{ nom: string; params: string[] }> = [];
        const iter = Memory.alloc(Process.pointerSize);
        iter.writePointer(ptr(0));
        for (;;) {
            const mi = class_get_methods(klass, iter) as NativePointer;
            if (mi.isNull()) break;
            const n = method_get_param_count(mi) as number;
            const params: string[] = [];
            for (let i = 0; i < n; i++) params.push(methodParamClassName(mi, i) ?? "?");
            out.push({ nom: s(method_get_name(mi) as NativePointer), params });
        }
        return {
            ok: true,
            etat: s(class_get_name(klass) as NativePointer),
            cible: body?.target ?? null,
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
     *  `depuisInput: true` exécute l'appel depuis la phase d'INPUT du jeu au lieu de la
     *  pompe (cf. l'en-tête de `depuisInput`) — la seule variable qui restait quand les
     *  arguments se sont révélés justes.
     *
     *  body: { method, args?: [...], target?: "<champ>", depuisInput?: true } — types
     *  acceptés : cf. `argIl2cpp`. */
    ctx.rpc.fsmStateInvoke = (
        body?: { method?: string; args?: unknown[]; target?: string; depuisInput?: boolean },
    ): Promise<unknown> => {
        const corps = () => {
        const f = fsmUtilisable();
        if (estRefus(f)) return f;
        const e = objetEtat();
        if (!e) return { ok: false, error: "aucun etat courant" };

        const cible = body?.target;
        const t = traverser(e, cible);
        if (estRefus(t)) return t;
        const { obj, klass } = t as Cible;

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
        const res = invokeMethod(mr.info, obj, args.length ? args : null);
        return {
            ok: true, etat: avant, methode: nom, args: bruts.length, cible: cible ?? null,
            etatApres: etatCourant(),
            // LA VALEUR DE RETOUR : sans elle, << a refuse >> et << a marche >> sont
            // indiscernables (cf. l'en-tete de decoderRetour).
            retour: decoderRetour(mr.info, res),
            voie: body?.depuisInput ? "input" : "pompe",
        };
        };
        return body?.depuisInput ? depuisInput(corps) : queueOnMainThread(corps);
    };

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
            // Le point d'ancrage d'input SE JUGE : s'il n'a jamais battu, `depuisInput`
            // n'est pas une voie, et il faut le dire au lieu de laisser attendre.
            ancrageInput: {
                arme: miShouldMove !== null,
                appels: appelsInput,
                enAttente: fileInput.length,
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
