// ai-step — pilotage de l'IA du jeu UNE UNITÉ À LA FOIS (Mode B).
//
// Objectif IL (imitation learning) : produire des démos (état, action) au
// grain d'UNE activation d'unité, au lieu de jouer toute la team d'un coup
// via CheatRunAIMessage (qui bucketise tout sous un wrapper, cf.
// project_turn_order_dynamic). Le jeu n'a PAS d'initiative : c'est
// `DefaultGroupOperator.PickNextUnit` (scoring d'utilité) qui choisit quelle
// unité activer ensuite — l'ordre est une policy émergente, à capturer.
//
// Mécanisme (dump kqkbjqfb6c) :
//   AiControl.CalculateAndApplyAllComputerActions joue toute la team via :
//     e = strategy.CalculateNextActionForPlayer(player)  // IEnumerator<List<IInputMessage>>
//     while e.MoveNext():               <-- 1 itération = 1 activation d'unité
//         foreach msg in e.Current: ApplyAiMessage(msg)
//   → en pilotant `e` nous-mêmes, 1 MoveNext() = l'action complète d'1 unité
//     (Move + Ability + FinishUnitTurn), qu'on peut décoder + snapshotter
//     l'état AVANT.
//
// Chaîne de résolution :
//   currentTurnPlayer (BEntityId int)  →  state.GetEntity(BEntityId) → IEntity
//   aiControl.GetAi(Nullable<BEntityId>) → IAiPlayerStrategy
//   strategy.CalculateNextActionForPlayer(player) → enumerator
//   enumerator.MoveNext() ; lire <>2__current @0x18 (la List<IInputMessage>)
//
// Étape 1 (ce module) : `aiStepDryRun` — UN MoveNext, décode, NE COMMITE PAS
// (read-only, ne mute pas le runner → sûr même sur un build runner engagé).
// Sert à valider que le pilotage manuel marche sur le runner isolé (le mémo
// project_ai_plays_player notait un blocage, mais sur le tour HUMAIN du live).

import {
    class_get_fields, class_get_name, class_get_namespace, class_get_parent,
    field_get_name, field_get_offset, field_get_type,
    findClass, findClassAnywhere, findCtorByParamCount,
    findMethod, findMethodByParamCount, getFieldOffset, s,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { runnerApplyMi, runnerClass, runnerOff } from "../game/runner.js";
import { getRunner } from "../game/runner-registry.js";
import {
    EntityType, forEachComponent, forEachEntity, positionComponentClass,
    projectMatchState, readBattleStatus,
} from "../game/match-state.js";
import { aiControlClass, applyAiMsgMi } from "../game/ai-control.js";
import {
    ensureStreamHooks, popApply, pushApply, StreamEvent,
} from "../game/apply-stack.js";
import { state } from "../game/state.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { abilityName } from "../data/ability-names.js";
import { Ctx } from "../controller.js";

// --- Résolution statique (une fois au load) ---

// AiControl.GetAi(Nullable<BEntityId>) → IAiPlayerStrategy.
const getAiMi = findMethod(aiControlClass!, "GetAi");
// Fallback direct : AiControl._defaultPlayerAiStrategy (cas standard joueur).
const defaultStratOff = getFieldOffset(aiControlClass!, "_defaultPlayerAiStrategy");

// Helpers statiques UnitExtensions (IdunBattle.Entities) — invocables, zéro
// offset brut. Servent à calculer le set « units à activer » de façon vivante
// (gère les kills) : un squad est à activer s'il est contrôlé par le joueur
// courant ET vivant ET a encore une action.
const unitExtClass = findClassAnywhere("IdunBattle.Entities", "UnitExtensions");
const hasActionLeftMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "HasActionLeft", 1) : null;
const isAliveMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "IsAlive", 2) : null;
const isCtrlByCurMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "IsControlledByCurrentPlayer", 2) : null;
const isRangedMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "IsRanged", 1) : null;

// EndTurnMessage — appliqué pour passer la main à l'autre équipe quand
// l'épuisement de l'énumérateur n'a pas auto-flippé le tour.
const endTurnClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Messages", "EndTurnMessage");
const endTurnCtor = endTurnClass ? findCtorByParamCount(endTurnClass, 0) : null;

// MovementQuery.GetMovableTilesFor(unit, ignoreUnitFlags, MovementOptions) →
// IOrderedSet<IEntity> (tiles atteignables). L'instance vit sur le runner
// (<MovementQuery>k__BackingField). 3-param overload (cf. move-options.ts).
const movementQueryClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Core.Services", "MovementQuery");
const getMovableTilesMi = movementQueryClass
    ? findMethodByParamCount(movementQueryClass, "GetMovableTilesFor", 3) : null;
const movementQueryOff = getFieldOffset(
    runnerClass!, "<MovementQuery>k__BackingField");
// IAttackQuery.GetAllTilesInAbilityRange(unit, possibleTiles, includeNormalAttack)
// → tiles frappables depuis un ensemble de positions. Move ∪ ça = danger zone.
// L'instance vit sur le runner (<AttackQuery>k__BackingField).
const attackQueryOff = getFieldOffset(
    runnerClass!, "<AttackQuery>k__BackingField");
// IDamagePredictionQuery.GetAllPredictions(attacker, selectedAttackerTile,
// ActiveAbilityType) → IDictionary<IEntity, DamagePredictionResult>.
// DamagePredictionResult struct : CurrentHealth@0, CurrentArmor@4,
// CurrentShield@8, TotalDamage(MinMaxDamage)@0x90 (Min@+8=0x98, Max@+0xC=0x9C).
// L'instance vit dans EntityServices (container god-object) tenu par le runner
// via <Services>@0xC8 ; EntityServices.<DamagePredictionQuery>@0x88.
const servicesOff = getFieldOffset(runnerClass!, "<Services>k__BackingField");
const entityServicesClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Core.Services", "EntityServices");
const dpqInServicesOff = entityServicesClass
    ? getFieldOffset(entityServicesClass, "<DamagePredictionQuery>k__BackingField") : -1;
// PositionComponent : Coordinate.Column @0x10, Row @0x14 (cf. move-options).
const POS_COL_OFF = 0x10;
const POS_ROW_OFF = 0x14;

// --- Abilities concrètes d'une unité (pour ranker) ---
// L'attaque normale a un id TYPÉ PAR UNITÉ (ex. Loki_NormalAttack=69), PAS
// l'abstrait NormalAttack=17 (absent des components → GetOrNull échoue).
// ActiveAbilityComponent : Abilities (KeyedCollection) @0x20, NormalAttackType
// @0x28 ; GetActives() → List<ActiveAbility> ; Components.ActiveAbility.AbilityName
// @0x44 = son ActiveAbilityType.
const activeAbilityComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "ActiveAbilityComponent");
const normalAttackTypeOff = activeAbilityComponentClass
    ? getFieldOffset(activeAbilityComponentClass, "NormalAttackType") : -1;
// MoW : leurs abilities ne sont PAS l'attaque normale (NormalAttackType=0) mais
// Primary/SecondaryMachineAbilityType (artillerie). Offsets résolus runtime.
const primaryMachineAbilityOff = activeAbilityComponentClass
    ? getFieldOffset(activeAbilityComponentClass, "PrimaryMachineAbilityType") : -1;
const secondaryMachineAbilityOff = activeAbilityComponentClass
    ? getFieldOffset(activeAbilityComponentClass, "SecondaryMachineAbilityType") : -1;
const getActivesMi = activeAbilityComponentClass
    ? findMethodByParamCount(activeAbilityComponentClass, "GetActives", 0) : null;
const componentsActiveAbilityClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "ActiveAbility");
const abilityNameOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "AbilityName") : -1;
// EntityExtensions.GetMainTile(entity, state) → la tile courante de l'unité
// (GetMovableTilesFor exclut la tile d'origine ; on l'ajoute au set candidat
// pour que « rester sur place et attaquer » soit rankée).
const entityExtClass = findClassAnywhere("IdunBattle.Entities", "EntityExtensions");
const getMainTileMi = entityExtClass
    ? findMethodByParamCount(entityExtClass, "GetMainTile", 2) : null;

/** Invoque une méthode statique retournant bool (résultat boxé : valeur @0x10). */
function invokeBool(
    mi: { info: NativePointer } | null, args: NativePointer[],
): boolean {
    if (!mi) return false;
    try {
        const r = invokeMethod(mi.info, null, args);
        return !r.isNull() && r.add(0x10).readU8() !== 0;
    } catch { return false; }
}

// Champs des IInputMessage (offsets validés sur le dump kqkbjqfb6c).
const MSG_OFF = {
    moveUnitId: 0x10,       // MoveUnitMessage.UnitId (BEntityId)
    moveFeet: 0x18,         // MoveUnitMessage.UnitFeetPositions (List<Position>)
    abilCaster: 0x10,       // ActiveAbilityMessage.CasterId
    abilTarget: 0x14,       // ActiveAbilityMessage.TargetId
    abilType: 0x18,         // ActiveAbilityMessage.ActiveAbilityType (enum int)
    finishUnitId: 0x10,     // FinishUnitTurnMessage.UnitId
} as const;

// List<T> IL2CPP : _items @0x10, _size @0x18, données du tableau dès +0x20.
const LIST_ITEMS = 0x10;
const LIST_SIZE = 0x18;
const ARRAY_FIRST = 0x20;
// Position : value-type 8 octets { Column:int@0, Row:int@4 }.
const POS_STRIDE = 8;

// --- Construction de messages (applyAction : appliquer MON coup) ---
// Classes IInputMessage que je construis from scratch (il2cpp_object_new + ctor
// 0-arg + écriture des champs), puis applique via AiControl.ApplyAiMessage —
// le MÊME chemin prouvé que les messages générés par l'IA (cf. aiPlayByUnit).
//   MoveUnitMessage     : UnitId@0x10, UnitFeetPositions@0x18 (List<Position>),
//                         SkipFlags@0x20. UnitFeetPositions = FOOTPRINT de
//                         destination (get_To = feet[0]), PAS le chemin —
//                         le moteur recalcule le trajet + l'overwatch.
//   ActiveAbilityMessage: CasterId@0x10, TargetId@0x14, ActiveAbilityType@0x18,
//                         SkipFlags@0x1C. Pas de position → bouger AVANT si
//                         besoin. Les MoW ne bougent pas → ability seule.
//   FinishUnitTurnMessage: UnitId@0x10.
const moveUnitMsgClass = findClassAnywhere("IdunBattle.Messages", "MoveUnitMessage");
const activeAbilityMsgClass = findClassAnywhere(
    "IdunBattle.Messages", "ActiveAbilityMessage");
const finishUnitTurnMsgClass = findClassAnywhere(
    "IdunBattle.Messages", "FinishUnitTurnMessage");

/** Classe d'un champ (par nom) — sert à récupérer le type inflé List<Position>
 *  du champ UnitFeetPositions (instanciation générique, non trouvable par nom). */
function fieldClass(klass: NativePointer, fieldName: string): NativePointer {
    const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        if (s(field_get_name(f) as NativePointer) === fieldName) {
            try {
                return type_get_class_or_element_class(
                    field_get_type(f) as NativePointer) as NativePointer;
            } catch { return ptr(0); }
        }
    }
    return ptr(0);
}
const listPositionClass = moveUnitMsgClass
    ? fieldClass(moveUnitMsgClass, "UnitFeetPositions") : ptr(0);
const listPositionCtor = (listPositionClass && !listPositionClass.isNull())
    ? findCtorByParamCount(listPositionClass, 0) : null;
const listPositionAddMi = (listPositionClass && !listPositionClass.isNull())
    ? findMethodByParamCount(listPositionClass, "Add", 1) : null;
const moveCtor0 = moveUnitMsgClass ? findCtorByParamCount(moveUnitMsgClass, 0) : null;
const abilityCtor0 = activeAbilityMsgClass
    ? findCtorByParamCount(activeAbilityMsgClass, 0) : null;
const finishCtor0 = finishUnitTurnMsgClass
    ? findCtorByParamCount(finishUnitTurnMsgClass, 0) : null;

/** Construit une List<Position> peuplée des tiles `feet` (footprint). */
function buildPositionList(
    feet: Array<{ col: number; row: number }>,
): NativePointer {
    if (!listPositionClass || listPositionClass.isNull() || !listPositionAddMi) {
        return ptr(0);
    }
    const list = il2cpp_object_new(listPositionClass) as NativePointer;
    if (list.isNull()) return ptr(0);
    if (listPositionCtor) invokeMethod(listPositionCtor.info, list, null);
    for (const f of feet) {
        const pos = Memory.alloc(POS_STRIDE);
        pos.writeS32(f.col); pos.add(4).writeS32(f.row);
        invokeMethod(listPositionAddMi.info, list, [pos]);  // Position by-value (ptr)
    }
    return list;
}

/** MoveUnitMessage(unitId, feet). feet = footprint destination (1 tile pour les
 *  unités mono-tile). */
function buildMoveMsg(
    unitId: number, feet: Array<{ col: number; row: number }>,
): NativePointer {
    if (!moveUnitMsgClass) return ptr(0);
    const msg = il2cpp_object_new(moveUnitMsgClass) as NativePointer;
    if (msg.isNull()) return ptr(0);
    if (moveCtor0) invokeMethod(moveCtor0.info, msg, null);
    const list = buildPositionList(feet);
    if (list.isNull()) return ptr(0);
    gcRoot.add(list);
    msg.add(MSG_OFF.moveUnitId).writeS32(unitId);      // BEntityId = int
    msg.add(MSG_OFF.moveFeet).writePointer(list);      // List<Position>
    msg.add(0x20).writeU8(0);                          // SkipFlags = false
    return msg;
}

/** ActiveAbilityMessage(caster, target, abilityType). Validation complète
 *  (SkipFlags=false) → fidèle (portée/action/overwatch jugés par le moteur). */
function buildAbilityMsg(
    casterId: number, targetId: number, abilityType: number,
): NativePointer {
    if (!activeAbilityMsgClass) return ptr(0);
    const msg = il2cpp_object_new(activeAbilityMsgClass) as NativePointer;
    if (msg.isNull()) return ptr(0);
    if (abilityCtor0) invokeMethod(abilityCtor0.info, msg, null);
    msg.add(MSG_OFF.abilCaster).writeS32(casterId);
    msg.add(MSG_OFF.abilTarget).writeS32(targetId);
    msg.add(MSG_OFF.abilType).writeS32(abilityType);
    msg.add(0x1c).writeU8(0);   // SkipFlags = false (0x1D/0x1E/0x20 → défaut ctor)
    return msg;
}

/** FinishUnitTurnMessage(unitId) — termine explicitement l'activation. */
function buildFinishMsg(unitId: number): NativePointer {
    if (!finishUnitTurnMsgClass) return ptr(0);
    const msg = il2cpp_object_new(finishUnitTurnMsgClass) as NativePointer;
    if (msg.isNull()) return ptr(0);
    if (finishCtor0) invokeMethod(finishCtor0.info, msg, null);
    msg.add(MSG_OFF.finishUnitId).writeS32(unitId);
    return msg;
}

interface ActionSpec {
    kind: "move" | "ability" | "finish" | "endturn";
    unitId?: number;
    to?: { col: number; row: number };
    feet?: Array<{ col: number; row: number }>;
    casterId?: number;
    targetId?: number;
    abilityType?: number;
}

interface UnitChange {
    squadId: number;
    from?: { col: number; row: number } | null;
    to?: { col: number; row: number } | null;
    moved?: boolean;
    hpBefore?: number | null;
    hpAfter?: number | null;
    hpDelta?: number;
    killed?: boolean;
    appeared?: boolean;
}

/** Diff de deux summaries : units déplacées / blessées / tuées / apparues. */
function diffUnits(before: StateSummary, after: StateSummary): UnitChange[] {
    const bById = new Map(before.units.map((u) => [u.squadId, u]));
    const changes: UnitChange[] = [];
    const posKey = (p: { col: number; row: number } | null) =>
        p ? p.col + "," + p.row : "x";
    const afterIds = new Set<number>();
    for (const a of after.units) {
        afterIds.add(a.squadId);
        const b = bById.get(a.squadId);
        if (!b) {
            changes.push({ squadId: a.squadId, appeared: true, to: a.pos, hpAfter: a.hp });
            continue;
        }
        const moved = posKey(b.pos) !== posKey(a.pos);
        const hpDelta = (a.hp ?? 0) - (b.hp ?? 0);
        if (moved || hpDelta !== 0) {
            changes.push({
                squadId: a.squadId, from: b.pos, to: a.pos, moved,
                hpBefore: b.hp, hpAfter: a.hp, hpDelta,
            });
        }
    }
    for (const b of before.units) {
        if (!afterIds.has(b.squadId)) {
            changes.push({ squadId: b.squadId, killed: true, hpBefore: b.hp });
        }
    }
    return changes;
}

interface ActionResult {
    kind: string;
    ok: boolean;
    error: string | null;
    mutated: boolean;
    changes: UnitChange[];
    /** Cascade StreamDispatcher capturée pendant l'apply (UnitDamaged,
     *  ReceiveEffect, groups…) — révèle l'overwatch / DoT / crit qu'un simple
     *  diff HP confond. tags = Dict<TagKey,int> JSON (Effect_Type, dégâts…). */
    events: StreamEvent[];
    eventCount: number;
    stage: number | null;
    currentPlayer: number | null;
}

/** Construit + applique UNE action via ApplyAiMessage, en snapshotant l'état
 *  AVANT/APRÈS → diff observable. Coeur de la décomposition « 2 temps » :
 *  un appel = une action, on observe, puis on décide la suivante. */
function applyOneAction(
    runner: NativePointer, aiControl: NativePointer, action: ActionSpec,
): ActionResult {
    let msg: NativePointer = ptr(0);
    let buildErr: string | null = null;
    try {
        if (action.kind === "move") {
            const feet = action.feet ?? (action.to ? [action.to] : []);
            if (!feet.length || action.unitId === undefined) {
                buildErr = "move: need unitId + to/feet";
            } else { msg = buildMoveMsg(action.unitId, feet); }
        } else if (action.kind === "ability") {
            if (action.casterId === undefined || action.targetId === undefined
                || action.abilityType === undefined) {
                buildErr = "ability: need casterId + targetId + abilityType";
            } else {
                msg = buildAbilityMsg(
                    action.casterId, action.targetId, action.abilityType);
            }
        } else if (action.kind === "finish") {
            if (action.unitId === undefined) buildErr = "finish: need unitId";
            else msg = buildFinishMsg(action.unitId);
        } else if (action.kind === "endturn") {
            if (!endTurnClass) buildErr = "endturn: EndTurnMessage class missing";
            else {
                msg = il2cpp_object_new(endTurnClass) as NativePointer;
                if (!msg.isNull() && endTurnCtor) {
                    invokeMethod(endTurnCtor.info, msg, null);
                }
            }
        } else {
            buildErr = "unknown kind: " + action.kind;
        }
    } catch (e) { buildErr = "build: " + (e as Error).message; }

    const statePtr0 = runner.add(runnerOff.state).readPointer();
    const before = summarize(statePtr0);
    if (buildErr || msg.isNull()) {
        const st = readBattleStatus(statePtr0);
        return {
            kind: action.kind, ok: false,
            error: buildErr ?? "build returned null",
            mutated: false, changes: [], events: [], eventCount: 0,
            stage: st.stage, currentPlayer: st.currentTurnPlayer,
        };
    }
    gcRoot.add(msg);
    // Frame de capture : ApplyAiMessage est hooké en NON-top par message-trace
    // (il le suppose imbriqué dans runner.Apply), donc appelé en direct ici il
    // n'a aucune frame → les StreamDispatcher events tomberaient dans le vide.
    // On pushe NOTRE frame autour de l'invoke → toute la cascade (dont
    // l'overwatch déclenché par l'ability) atterrit dans `events`.
    ensureStreamHooks();
    const events: StreamEvent[] = [];
    pushApply("built", events);
    let applyErr: string | null = null;
    try {
        // EndTurnMessage passe par runner.Apply (message moteur, pas IA) ;
        // move/ability/finish par AiControl.ApplyAiMessage (chemin IA).
        if (action.kind === "endturn") {
            invokeMethod(runnerApplyMi!.info, runner, [msg]);
        } else {
            invokeMethod(applyAiMsgMi!.info, aiControl, [msg]);
        }
    } catch (e) { applyErr = (e as Error).message; }
    finally {
        try { popApply(); } catch { /* */ }
        try { gcRoot.remove(msg); } catch { /* */ }
    }

    const statePtr1 = runner.add(runnerOff.state).readPointer();
    const after = summarize(statePtr1);
    const st = readBattleStatus(statePtr1);
    return {
        kind: action.kind, ok: applyErr === null, error: applyErr,
        mutated: before.sig !== after.sig, changes: diffUnits(before, after),
        events, eventCount: events.length,
        stage: st.stage, currentPlayer: st.currentTurnPlayer,
    };
}

/** Lit une List<Position> (chemin des pieds de l'unité). */
function readPositionList(
    listPtr: NativePointer, max = 64,
): Array<{ col: number; row: number }> {
    if (listPtr.isNull()) return [];
    try {
        const items = listPtr.add(LIST_ITEMS).readPointer();
        const size = listPtr.add(LIST_SIZE).readS32();
        if (items.isNull() || size <= 0 || size > 1000) return [];
        const out: Array<{ col: number; row: number }> = [];
        const n = Math.min(size, max);
        for (let i = 0; i < n; i++) {
            const base = items.add(ARRAY_FIRST + i * POS_STRIDE);
            out.push({ col: base.readS32(), row: base.add(4).readS32() });
        }
        return out;
    } catch { return []; }
}

interface DecodedMsg {
    cls: string;
    unitId?: number;
    casterId?: number;
    targetId?: number;
    abilityType?: number;
    to?: { col: number; row: number } | null;
    pathLen?: number;
}

/** Décode un IInputMessage selon son type runtime. */
function decodeMsg(msg: NativePointer, cls: string): DecodedMsg {
    try {
        switch (cls) {
            case "MoveUnitMessage": {
                const path = readPositionList(msg.add(MSG_OFF.moveFeet).readPointer());
                return {
                    cls,
                    unitId: msg.add(MSG_OFF.moveUnitId).readS32(),
                    to: path.length ? path[path.length - 1] : null,
                    pathLen: path.length,
                };
            }
            case "ActiveAbilityMessage":
                return {
                    cls,
                    casterId: msg.add(MSG_OFF.abilCaster).readS32(),
                    targetId: msg.add(MSG_OFF.abilTarget).readS32(),
                    abilityType: msg.add(MSG_OFF.abilType).readS32(),
                };
            case "FinishUnitTurnMessage":
                return { cls, unitId: msg.add(MSG_OFF.finishUnitId).readS32() };
            default:
                return { cls };
        }
    } catch { return { cls }; }
}

/** Décode la List<IInputMessage> yieldée par un MoveNext (l'action d'1 unité). */
function decodeMsgList(list: NativePointer): {
    count: number; messages: DecodedMsg[];
} {
    if (list.isNull()) return { count: 0, messages: [] };
    let items: NativePointer; let size: number;
    try {
        items = list.add(LIST_ITEMS).readPointer();
        size = list.add(LIST_SIZE).readS32();
    } catch { return { count: 0, messages: [] }; }
    if (items.isNull() || size <= 0 || size > 200) {
        return { count: size, messages: [] };
    }
    const out: DecodedMsg[] = [];
    for (let i = 0; i < size; i++) {
        let msg: NativePointer;
        try { msg = items.add(ARRAY_FIRST + i * Process.pointerSize).readPointer(); }
        catch { continue; }
        if (msg.isNull()) continue;
        let cls = "?";
        try { cls = s(class_get_name(msg.readPointer()) as NativePointer); }
        catch { /* keep ? */ }
        out.push(decodeMsg(msg, cls));
    }
    return { count: size, messages: out };
}

interface StateSummary {
    turn: number | null;
    playerOnTurn: number | null;
    units: Array<{
        squadId: number; pos: { col: number; row: number } | null;
        hp: number | null; ownerId: number | null;
    }>;
    sig: string;
}

/** Résumé compact de l'état (assez pour eyeball + détecter une mutation). */
function summarize(statePtr: NativePointer): StateSummary {
    const proj = projectMatchState(statePtr);
    const units = proj.units.map((u) => ({
        squadId: u.squadId, pos: u.pos,
        hp: u.hp, ownerId: u.ownerId,
    }));
    const sig = units
        .map((u) => `${u.squadId}:${u.pos ? u.pos.col + "," + u.pos.row : "x"}:${u.hp}`)
        .sort()
        .join("|");
    return { turn: proj.turn, playerOnTurn: proj.playerOnTurn, units, sig };
}

/** Résout l'IEntity du joueur dont l'id == playerId (le player on turn).
 *  Pas de GetEntity (qui vit sur un Query, pas sur MatchState) : on scanne
 *  les entités de l'état — le player est l'entité portant ce BEntityId. */
function resolvePlayerEntity(
    statePtr: NativePointer, playerId: number,
): NativePointer {
    let found = ptr(0);
    forEachEntity(statePtr, (e, id) => {
        if (found.isNull() && id === playerId) found = e;
    });
    return found;
}

/** Résout la stratégie IA du joueur courant. GetAi gère default/human/env ;
 *  fallback sur le champ _defaultPlayerAiStrategy si GetAi échoue. */
function resolveStrategy(
    aiControl: NativePointer, playerId: number,
): { strategy: NativePointer; src: string; err: string | null } {
    let err: string | null = null;
    if (getAiMi) {
        try {
            // Nullable<BEntityId> : 8 octets, hasValue @0 (1B + pad), value @4.
            const nullable = Memory.alloc(8);
            nullable.writeU8(1);
            nullable.add(4).writeS32(playerId);
            const strat = invokeMethod(getAiMi.info, aiControl, [nullable]);
            if (!strat.isNull()) return { strategy: strat, src: "GetAi", err: null };
        } catch (e) { err = (e as Error).message; }
    }
    // Fallback champ direct.
    try {
        const strat = aiControl.add(defaultStratOff).readPointer();
        if (!strat.isNull()) {
            return { strategy: strat, src: "_defaultPlayerAiStrategy", err };
        }
    } catch { /* fallthrough */ }
    return { strategy: ptr(0), src: "none", err };
}

interface DryRunResult {
    ok: boolean;
    error?: string;
    runner?: string;
    playerId?: number | null;
    strategySrc?: string;
    strategyErr?: string | null;
    hasNext?: boolean;
    moveNextCalls?: number;
    emptyYields?: number;
    action?: { count: number; messages: DecodedMsg[] } | null;
    /** L'unité activée (UnitId du MoveUnitMessage, sinon du Finish). */
    activatedUnitId?: number | null;
    mutated?: boolean;
    before?: StateSummary;
}

/** Itère une List<IInputMessage> en renvoyant pour chaque message son PTR
 *  brut (pour runner.Apply) ET son décodage. */
function processMsgList(
    list: NativePointer,
): Array<{ ptr: NativePointer; decoded: DecodedMsg }> {
    const out: Array<{ ptr: NativePointer; decoded: DecodedMsg }> = [];
    if (list.isNull()) return out;
    let items: NativePointer; let size: number;
    try {
        items = list.add(LIST_ITEMS).readPointer();
        size = list.add(LIST_SIZE).readS32();
    } catch { return out; }
    if (items.isNull() || size <= 0 || size > 200) return out;
    for (let i = 0; i < size; i++) {
        let msg: NativePointer;
        try { msg = items.add(ARRAY_FIRST + i * Process.pointerSize).readPointer(); }
        catch { continue; }
        if (msg.isNull()) continue;
        let cls = "?";
        try { cls = s(class_get_name(msg.readPointer()) as NativePointer); }
        catch { /* keep ? */ }
        out.push({ ptr: msg, decoded: decodeMsg(msg, cls) });
    }
    return out;
}

/** Squads (EntityType.Unit) « à activer » par le joueur courant : contrôlés
 *  par lui ET vivants ET ayant encore une action. Calculé sur l'état VIVANT
 *  (gère les kills) via les helpers UnitExtensions. */
function toActivateSquads(statePtr: NativePointer): number[] {
    const out: number[] = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        if (!invokeBool(isCtrlByCurMi, [e, statePtr])) return;
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        if (!invokeBool(hasActionLeftMi, [e])) return;
        out.push(id);
    });
    return out;
}

/** Squads activables du joueur courant AVEC leur ptr d'entité, ordonnés selon
 *  `order` : "asc"/"desc" par squadId, ou une liste explicite de squadIds (les
 *  ids absents sont rejetés en fin). Sert à IMPOSER l'ordre d'activation
 *  (contourne PickNextUnit). Le ptr d'entité d'un squad est stable sur la
 *  battle (l'objet persiste même mort) ; on re-vérifie vivant/action au moment
 *  de jouer. */
function validSquadsOrdered(
    statePtr: NativePointer, order: "asc" | "desc" | number[],
): Array<{ id: number; ptr: NativePointer }> {
    const list: Array<{ id: number; ptr: NativePointer }> = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        if (!invokeBool(isCtrlByCurMi, [e, statePtr])) return;
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        if (!invokeBool(hasActionLeftMi, [e])) return;
        list.push({ id, ptr: e });
    });
    if (Array.isArray(order)) {
        const rank = new Map<number, number>();
        order.forEach((sid, i) => rank.set(sid, i));
        list.sort((a, b) =>
            (rank.get(a.id) ?? 9999) - (rank.get(b.id) ?? 9999));
    } else if (order === "asc") {
        list.sort((a, b) => a.id - b.id);
    } else {
        list.sort((a, b) => b.id - a.id);
    }
    return list;
}

interface DemoState {
    units: Array<{
        squadId: number; pos: { col: number; row: number } | null;
        hp: number | null; owner: number | null; team: number | null;
    }>;
    toActivate: number[];
}

/** Snapshot d'état pour une démo IL (avant l'application de l'action). */
function captureStateForDemo(statePtr: NativePointer): DemoState {
    const proj = projectMatchState(statePtr);
    return {
        units: proj.units.map((u) => ({
            squadId: u.squadId, pos: u.pos, hp: u.hp,
            owner: u.ownerId, team: u.teamId ?? null,
        })),
        toActivate: toActivateSquads(statePtr),
    };
}

/** Applique un EndTurnMessage sur le runner (passe la main à l'autre équipe). */
function applyEndTurn(runner: NativePointer, events?: StreamEvent[]): boolean {
    if (!endTurnClass || !runnerApplyMi) return false;
    const msg = il2cpp_object_new(endTurnClass) as NativePointer;
    if (msg.isNull()) return false;
    gcRoot.add(msg);
    // Si `events` fourni : wrappe l'apply dans une frame pour capturer les
    // effets de FRONTIÈRE de tour (ticks d'AoE de tile, DoT, abilities déclenchées
    // en fin de tour) — sinon ils tomberaient dans le vide (runner.Apply hooké
    // NON-top par message-trace). C'est là que se résout l'artillerie retardée.
    if (events) { ensureStreamHooks(); pushApply("built", events); }
    try {
        if (endTurnCtor) invokeMethod(endTurnCtor.info, msg, null);
        invokeMethod(runnerApplyMi.info, runner, [msg]);
    } finally {
        if (events) { try { popApply(); } catch { /* */ } }
        try { gcRoot.remove(msg); } catch { /* best effort */ }
    }
    return true;
}

interface UnitProposal {
    unitId: number;
    hasActionLeft: boolean;
    pumps: number;
    exhausted: boolean;
    proposed: DecodedMsg[];
}

/** Sweep READ-ONLY : pour chaque squad contrôlé+vivant du joueur courant,
 *  pompe `CalculateNextActionForUnit(unit)` et lit l'action proposée SANS
 *  l'appliquer. Chaque proposition est conditionnée au MÊME état courant
 *  (« si l'unité jouait en premier »). `moveNextRef` cache le MethodInfo
 *  MoveNext entre appels. Ne mute pas le runner. */
function sweepAllUnitProposals(
    statePtr: NativePointer, strategy: NativePointer,
    calcUnitMi: { info: NativePointer }, maxPump: number,
    moveNextRef: { mi: { info: NativePointer; ptr: NativePointer } | null },
): { units: UnitProposal[]; pumps: number } {
    const squads: Array<{ id: number; ptr: NativePointer; hasAction: boolean }> = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        if (!invokeBool(isCtrlByCurMi, [e, statePtr])) return;
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        squads.push({ id, ptr: e, hasAction: invokeBool(hasActionLeftMi, [e]) });
    });
    const out: UnitProposal[] = [];
    let pumps = 0;
    for (const sq of squads) {
        let chunk: DecodedMsg[] = [];
        let p = 0; let exhausted = false; let err: string | null = null;
        try {
            const e = invokeMethod(calcUnitMi.info, strategy, [sq.ptr]);
            if (e.isNull()) { exhausted = true; }
            else {
                gcRoot.add(e);
                try {
                    if (!moveNextRef.mi) {
                        moveNextRef.mi = findMethod(e.readPointer(), "MoveNext");
                    }
                    while (moveNextRef.mi && p < maxPump) {
                        const boxed = invokeMethod(moveNextRef.mi.info, e, null);
                        p++; pumps++;
                        if (boxed.isNull() || boxed.add(0x10).readU8() === 0) {
                            exhausted = true; break;
                        }
                        const decoded = decodeMsgList(e.add(0x18).readPointer());
                        if (decoded.count > 0) { chunk = decoded.messages; break; }
                    }
                } finally { try { gcRoot.remove(e); } catch { /* */ } }
            }
        } catch (ex) { err = (ex as Error).message; }
        out.push({
            unitId: sq.id, hasActionLeft: sq.hasAction, pumps: p, exhausted,
            proposed: err ? [{ cls: "ERR:" + err }] : chunk,
        });
    }
    return { units: out, pumps };
}

interface UnitDemo {
    turnIndex: number;
    player: number;
    activatedUnitId: number;
    move: { to: { col: number; row: number } | null; pathLen: number };
    toActivate: number[];
    units: DemoState["units"];
}

/** Lit (col,row) d'une tile via sa PositionComponent. */
function readTileCoord(tile: NativePointer): { col: number; row: number } {
    let col = -1; let row = -1;
    if (positionComponentClass && !tile.isNull()) {
        try {
            forEachComponent(tile, (comp, klass) => {
                if (!klass.equals(positionComponentClass!)) return;
                try { col = comp.add(POS_COL_OFF).readS32(); } catch { /* */ }
                try { row = comp.add(POS_ROW_OFF).readS32(); } catch { /* */ }
            });
        } catch { /* */ }
    }
    return { col, row };
}

/** Extrait les tiles d'un IOrderedSet<IEntity> (List<T> : items@0x10, size@0x18,
 *  données dès +0x20). */
function extractTiles(
    orderedSet: NativePointer,
): Array<{ col: number; row: number }> {
    const out: Array<{ col: number; row: number }> = [];
    if (orderedSet.isNull()) return out;
    let items: NativePointer; let size: number;
    try {
        items = orderedSet.add(LIST_ITEMS).readPointer();
        size = orderedSet.add(LIST_SIZE).readS32();
    } catch { return out; }
    if (items.isNull() || size <= 0 || size > 1000) return out;
    for (let i = 0; i < size; i++) {
        let tile: NativePointer;
        try { tile = items.add(ARRAY_FIRST + i * Process.pointerSize).readPointer(); }
        catch { continue; }
        if (tile.isNull()) continue;
        out.push(readTileCoord(tile));
    }
    return out;
}

/** Comme extractTiles mais CONSERVE le pointeur de chaque tile — nécessaire au
 *  shrink-and-recall (on doit pouvoir `set.Remove(tilePtr)` la meilleure tile
 *  entre deux appels de GetBestTileToAttackFrom). */
function extractTilePtrs(
    orderedSet: NativePointer,
): Array<{ ptr: NativePointer; col: number; row: number }> {
    const out: Array<{ ptr: NativePointer; col: number; row: number }> = [];
    if (orderedSet.isNull()) return out;
    let items: NativePointer; let size: number;
    try {
        items = orderedSet.add(LIST_ITEMS).readPointer();
        size = orderedSet.add(LIST_SIZE).readS32();
    } catch { return out; }
    if (items.isNull() || size <= 0 || size > 1000) return out;
    for (let i = 0; i < size; i++) {
        let tile: NativePointer;
        try { tile = items.add(ARRAY_FIRST + i * Process.pointerSize).readPointer(); }
        catch { continue; }
        if (tile.isNull()) continue;
        const c = readTileCoord(tile);
        out.push({ ptr: tile, col: c.col, row: c.row });
    }
    return out;
}

/** ActiveAbilityComponent d'une unité (ou ptr null). */
function getAbilityComponent(unit: NativePointer): NativePointer {
    let comp = ptr(0);
    if (!activeAbilityComponentClass) return comp;
    try {
        forEachComponent(unit, (c, klass) => {
            if (comp.isNull() && klass.equals(activeAbilityComponentClass!)) comp = c;
        });
    } catch { /* */ }
    return comp;
}

/** ActiveAbilityType CONCRETS d'une unité : son attaque normale
 *  (NormalAttackType @0x28) + (si includeActives) ses actives (GetActives →
 *  .AbilityName @0x44). Filtre 0/None. C'est ce qu'il faut passer à
 *  GetBestTileToAttackFrom (pas l'abstrait 17). */
function unitAbilityTypes(
    unit: NativePointer, includeActives: boolean,
): Array<{ id: number; name: string; kind: string }> {
    const out: Array<{ id: number; name: string; kind: string }> = [];
    const comp = getAbilityComponent(unit);
    if (comp.isNull()) return out;
    if (normalAttackTypeOff >= 0) {
        try {
            const na = comp.add(normalAttackTypeOff).readS32();
            if (na !== 0) {
                out.push({ id: na, name: abilityName(na) ?? "id:" + na, kind: "normal" });
            }
        } catch { /* */ }
    }
    if (includeActives && getActivesMi && abilityNameOff >= 0) {
        try {
            const list = invokeMethod(getActivesMi.info, comp, null);
            if (!list.isNull()) {
                const items = list.add(LIST_ITEMS).readPointer();
                const size = list.add(LIST_SIZE).readS32();
                if (!items.isNull() && size > 0 && size < 64) {
                    for (let i = 0; i < size; i++) {
                        const ab = items
                            .add(ARRAY_FIRST + i * Process.pointerSize).readPointer();
                        if (ab.isNull()) continue;
                        const t = ab.add(abilityNameOff).readS32();
                        if (t !== 0 && !out.some((e) => e.id === t)) {
                            out.push({ id: t, name: abilityName(t) ?? "id:" + t, kind: "active" });
                        }
                    }
                }
            }
        } catch { /* */ }
    }
    return out;
}

/** Abilities d'un MoW (Machine) : NormalAttack(=0 souvent) + actives + surtout
 *  Primary/SecondaryMachineAbilityType (= l'artillerie, ce qu'on TIRE). */
function mowAbilityTypes(
    machine: NativePointer,
): Array<{ id: number; name: string; kind: string }> {
    const out = unitAbilityTypes(machine, true);  // normal + actives
    const comp = getAbilityComponent(machine);
    if (!comp.isNull()) {
        const extra: Array<[number, string]> = [
            [primaryMachineAbilityOff, "machinePrimary"],
            [secondaryMachineAbilityOff, "machineSecondary"],
        ];
        for (const [off, kind] of extra) {
            if (off < 0) continue;
            try {
                const t = comp.add(off).readS32();
                if (t !== 0 && !out.some((e) => e.id === t)) {
                    out.push({ id: t, name: abilityName(t) ?? "id:" + t, kind });
                }
            } catch { /* */ }
        }
    }
    return out;
}

/** Tile courante d'une unité — EntityExtensions.GetMainTile(unit, state). */
function getUnitMainTile(
    unit: NativePointer, statePtr: NativePointer,
): NativePointer {
    if (!getMainTileMi) return ptr(0);
    try { return invokeMethod(getMainTileMi.info, null, [unit, statePtr]); }
    catch { return ptr(0); }
}

// ===== Cœur partagé (utilisé par aiAttackRank ET decisionView) =====

/** Instance DamagePredictionQuery du runner via EntityServices.<DPQ>@0x88
 *  (runner.<Services>@0xC8). ptr(0) si indisponible. */
function resolveDpq(runner: NativePointer): NativePointer {
    if (servicesOff < 0 || dpqInServicesOff < 0) return ptr(0);
    try {
        const services = runner.add(servicesOff).readPointer();
        if (services.isNull()) return ptr(0);
        return services.add(dpqInServicesOff).readPointer();
    } catch { return ptr(0); }
}

interface RankedTile {
    col: number; row: number;
    dmgMin?: number; dmgMax?: number;
    kill?: boolean; killSure?: boolean; mightCrit?: boolean;
}
interface AttackEval {
    targetId: number; targetVis: string | null;
    targetPos: { col: number; row: number } | null;
    abilityId: number; ability: string; kind: string;
    movableCount: number; rankCount: number;
    ranked: RankedTile[]; err: string | null;
}
interface UnitAttackPlan {
    unitId: number; visualId: string | null;
    pos: { col: number; row: number } | null;
    currentTile: { col: number; row: number } | null;
    abilities: Array<{ id: number; name: string; kind: string }>;
    evals: AttackEval[];
}

/** Ranking des positions d'attaque par (unit contrôlée, ability, target ennemi)
 *  via shrink-and-recall sur GetBestTileToAttackFrom. Lit les abilities
 *  CONCRÈTES (NormalAttackType + actives) + ajoute la tile courante au set
 *  candidat. NE MUTE PAS le MatchState (seul un IOrderedSet transient est muté). */
function computeAttackPlans(
    statePtr: NativePointer, movementQuery: NativePointer,
    attackQuery: NativePointer, getBestMi: { info: NativePointer },
    dpq: NativePointer,
    opts: {
        unitId?: number; targetId?: number; manualAbility?: number | null;
        allAbilities?: boolean; maxRank?: number; overrideRange?: number | null;
    },
): { units: UnitAttackPlan[]; enemyCount: number; removeWorks: boolean | null } {
    const manualAbility = opts.manualAbility ?? null;
    const allAbilities = opts.allAbilities === true;
    const maxRank = (opts.maxRank && opts.maxRank > 0) ? opts.maxRank : 8;
    const overrideRange = opts.overrideRange ?? null;

    const proj = projectMatchState(statePtr);
    const visById = new Map<number, string | null>();
    const posById = new Map<number, { col: number; row: number } | null>();
    for (const u of proj.units) {
        visById.set(u.squadId, u.visualId); posById.set(u.squadId, u.pos);
    }
    const myUnits: Array<{ id: number; ptr: NativePointer }> = [];
    const enemies: Array<{ id: number; ptr: NativePointer }> = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        const ctrl = invokeBool(isCtrlByCurMi, [e, statePtr]);
        if (ctrl) {
            if (opts.unitId === undefined || opts.unitId === id) myUnits.push({ id, ptr: e });
        } else if (opts.targetId === undefined || opts.targetId === id) {
            enemies.push({ id, ptr: e });
        }
    });

    const abilBuf = Memory.alloc(4);
    const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
    const optsBuf = Memory.alloc(0x30);
    for (let k = 0; k < 0x30; k += 4) optsBuf.add(k).writeU32(0);
    if (overrideRange !== null) {
        optsBuf.add(0x4).writeU8(1); optsBuf.add(0x8).writeS32(overrideRange);
    }

    let removeMi: { info: NativePointer; ptr: NativePointer } | null = null;
    let addMi: { info: NativePointer; ptr: NativePointer } | null = null;
    let setResolved = false;
    let removeWorks: boolean | null = null;
    const units: UnitAttackPlan[] = [];
    // DamagePrediction (best-effort) : GetAllPredictions(unit, tile, ability)
    // → dict.get_Item(target) → struct (boxed+0x10). dpq résolu par le caller.
    const predMi = dpq.isNull() ? null
        : findMethodByParamCount(dpq.readPointer(), "GetAllPredictions", 3);
    let predItemMi: { info: NativePointer; ptr: NativePointer } | null = null;

    for (const u of myUnits) {
        const abilities = (manualAbility !== null)
            ? [{ id: manualAbility,
                 name: abilityName(manualAbility) ?? "id:" + manualAbility, kind: "manual" }]
            : unitAbilityTypes(u.ptr, allAbilities);
        const mainTile = getUnitMainTile(u.ptr, statePtr);
        const currentTile = mainTile.isNull() ? null : readTileCoord(mainTile);
        const evals: AttackEval[] = [];
        for (const ab of abilities) {
            abilBuf.writeS32(ab.id);
            for (const tgt of enemies) {
                let set: NativePointer;
                try {
                    set = invokeMethod(getMovableTilesMi!.info, movementQuery,
                        [u.ptr, boolFalse, optsBuf]);
                } catch (e) {
                    evals.push({ targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                        targetPos: posById.get(tgt.id) ?? null, abilityId: ab.id,
                        ability: ab.name, kind: ab.kind, movableCount: 0, rankCount: 0,
                        ranked: [], err: "movable: " + (e as Error).message });
                    continue;
                }
                if (set.isNull()) {
                    evals.push({ targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                        targetPos: posById.get(tgt.id) ?? null, abilityId: ab.id,
                        ability: ab.name, kind: ab.kind, movableCount: 0, rankCount: 0,
                        ranked: [], err: "movable null" });
                    continue;
                }
                if (!setResolved) {
                    removeMi = findMethodByParamCount(set.readPointer(), "Remove", 1);
                    addMi = findMethodByParamCount(set.readPointer(), "Add", 1);
                    setResolved = true;
                }
                gcRoot.add(set);
                let err: string | null = null;
                if (!mainTile.isNull() && addMi) {
                    try { invokeMethod(addMi.info, set, [mainTile]); } catch { /* */ }
                }
                const movableCount = extractTilePtrs(set).length;
                const ranked: RankedTile[] = [];
                try {
                    for (let r = 0; r < maxRank; r++) {
                        const best = invokeMethod(getBestMi.info, attackQuery,
                            [u.ptr, set, tgt.ptr, abilBuf]);
                        if (best.isNull()) break;
                        const coord = readTileCoord(best);
                        const entry: RankedTile = { col: coord.col, row: coord.row };
                        // Prédiction de dégâts en atterrissant sur `best` contre tgt.
                        if (predMi && !dpq.isNull()) {
                            try {
                                const dict = invokeMethod(predMi.info, dpq,
                                    [u.ptr, best, abilBuf]);
                                if (!dict.isNull()) {
                                    if (!predItemMi) {
                                        predItemMi = findMethodByParamCount(
                                            dict.readPointer(), "get_Item", 1);
                                    }
                                    if (predItemMi) {
                                        const boxed = invokeMethod(
                                            predItemMi.info, dict, [tgt.ptr]);
                                        if (!boxed.isNull()) {
                                            const bb = boxed.add(0x10);
                                            const hp = bb.readS32();
                                            entry.dmgMin = bb.add(0x60).readS32();
                                            entry.dmgMax = bb.add(0x64).readS32();
                                            // kill = possible (max>=hp) ; killSure
                                            // = garanti (min>=hp, indépendant du roll).
                                            entry.kill = (entry.dmgMax ?? 0) >= hp;
                                            entry.killSure = (entry.dmgMin ?? 0) >= hp;
                                            entry.mightCrit = bb.add(0xb1).readU8() !== 0;
                                        }
                                    }
                                }
                            } catch { /* prédiction best-effort */ }
                        }
                        ranked.push(entry);
                        if (!removeMi) { err = "Remove not resolved (rang tronqué à 1)"; break; }
                        const removed = invokeMethod(removeMi.info, set, [best]);
                        const ok = !removed.isNull() && removed.add(0x10).readU8() !== 0;
                        if (ok) { removeWorks = true; }
                        else { err = "Remove a renvoyé false (stop)"; break; }
                    }
                } catch (e) { err = (e as Error).message; }
                finally { try { gcRoot.remove(set); } catch { /* */ } }
                evals.push({ targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                    targetPos: posById.get(tgt.id) ?? null, abilityId: ab.id,
                    ability: ab.name, kind: ab.kind, movableCount,
                    rankCount: ranked.length, ranked, err });
            }
        }
        units.push({ unitId: u.id, visualId: visById.get(u.id) ?? null,
            pos: posById.get(u.id) ?? null, currentTile, abilities, evals });
    }
    return { units, enemyCount: enemies.length, removeWorks };
}

interface FullUnit {
    id: number; visualId: string | null;
    pos: { col: number; row: number } | null;
    hp: number | null; owner: number | null; team: number | null;
    alive: boolean; ctrl: boolean; hasAction: boolean; ranged: boolean;
    abilities: Array<{ id: number; name: string; kind: string }>;
}

/** Projection de TOUTES les units (2 camps) : flags vivants + abilities concrètes. */
function projectUnitsFull(statePtr: NativePointer, allAbilities: boolean): FullUnit[] {
    const proj = projectMatchState(statePtr);
    const base = new Map<number, (typeof proj.units)[number]>();
    for (const u of proj.units) base.set(u.squadId, u);
    const out: FullUnit[] = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        const b = base.get(id);
        out.push({
            id, visualId: b?.visualId ?? null, pos: b?.pos ?? null,
            hp: b?.hp ?? null, owner: b?.ownerId ?? null, team: b?.teamId ?? null,
            alive: invokeBool(isAliveMi, [e, statePtr]),
            ctrl: invokeBool(isCtrlByCurMi, [e, statePtr]),
            hasAction: invokeBool(hasActionLeftMi, [e]),
            ranged: invokeBool(isRangedMi, [e]),
            abilities: unitAbilityTypes(e, allAbilities),
        });
    });
    return out;
}

interface FullMow {
    /** Platform entityId (ancre sur la grille). */
    id: number;
    /** Machine entityId — porte HP/owner/abilities ; = casterId pour applyAction. */
    machineId: number;
    casterId: number;
    visualId: string | null;
    pos: { col: number; row: number } | null;
    hp: number | null; maxHp: number | null;
    owner: number | null; team: number | null;
    alive: boolean; ctrl: boolean; hasAction: boolean;
    /** Slot de déploiement (MachineOfWarPosition : 1=Top, 2=Bottom) — les MoW
     *  n'ont pas de (col,row) propre, juste un slot mappé aux tiles du board. */
    slot: number | null;
    abilities: Array<{ id: number; name: string; kind: string }>;
}

/** Projection des MoW (MachinePlatform/Machine) prête pour l'oracle. Les MoW ne
 *  bougent pas (ability-only) → pas de plan de move. La projection `proj.mows`
 *  porte déjà pos/hp/owner/team ; on enrichit ici les flags vivants + abilities
 *  concrètes lues sur l'entité Machine (Type 6, porteuse des abilities). Le
 *  casterId pour `applyAction {kind:"ability"}` = machineId. */
function projectMowsFull(
    statePtr: NativePointer, proj: ReturnType<typeof projectMatchState>,
): FullMow[] {
    const mows = proj.mows ?? [];
    if (mows.length === 0) return [];
    const machinePtr = new Map<number, NativePointer>();
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty === EntityType.Machine) machinePtr.set(id, e);
    });
    const out: FullMow[] = [];
    for (const m of mows) {
        const e = machinePtr.get(m.machineId);
        out.push({
            id: m.id, machineId: m.machineId, casterId: m.machineId,
            visualId: m.visualId, pos: m.pos,
            hp: m.hp, maxHp: m.maxHp, owner: m.ownerId, team: m.teamId,
            alive: e ? invokeBool(isAliveMi, [e, statePtr]) : !m.isDead,
            ctrl: e ? invokeBool(isCtrlByCurMi, [e, statePtr]) : false,
            hasAction: e ? invokeBool(hasActionLeftMi, [e]) : false,
            slot: m.initialSlot,
            abilities: e ? mowAbilityTypes(e) : [],
        });
    }
    return out;
}

/** Danger zone = tiles que les ENNEMIS du joueur courant peuvent frapper au
 *  prochain tour (move ∪ portée d'attaque), agrégées. Read-only. */
function computeDangerZone(
    statePtr: NativePointer, movementQuery: NativePointer, attackQuery: NativePointer,
): {
    tileCount: number; tiles: Array<{ col: number; row: number }>;
    byEnemy: Array<{ enemyId: number; threatCount: number }>;
} {
    const getAllTilesMi = findMethodByParamCount(
        attackQuery.readPointer(), "GetAllTilesInAbilityRange", 3);
    const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
    const incTrue = Memory.alloc(1); incTrue.writeU8(1);
    const optsBuf = Memory.alloc(0x30);
    for (let k = 0; k < 0x30; k += 4) optsBuf.add(k).writeU32(0);
    const union = new Set<string>();
    const byEnemy: Array<{ enemyId: number; threatCount: number }> = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        if (invokeBool(isCtrlByCurMi, [e, statePtr])) return; // ennemis seulement
        let threat: Array<{ col: number; row: number }> = [];
        try {
            const os = invokeMethod(getMovableTilesMi!.info, movementQuery,
                [e, boolFalse, optsBuf]);
            if (!os.isNull() && getAllTilesMi) {
                const tos = invokeMethod(getAllTilesMi.info, attackQuery, [e, os, incTrue]);
                threat = extractTiles(tos);
            }
        } catch { /* */ }
        for (const t of threat) union.add(t.col + "," + t.row);
        byEnemy.push({ enemyId: id, threatCount: threat.length });
    });
    return {
        tileCount: union.size,
        tiles: [...union].map((k) => {
            const [c, r] = k.split(",").map(Number); return { col: c, row: r };
        }),
        byEnemy,
    };
}

/** Dump RE : champs (nom/offset/type) d'une classe + parents (cap 4 niveaux).
 *  Sert à localiser HP/abilities/position sur des entités atypiques (MoW). */
function classFieldsDump(
    klass: NativePointer,
): Array<{ name: string; offset: number; type: string }> {
    const out: Array<{ name: string; offset: number; type: string }> = [];
    let k = klass; let depth = 0;
    while (!k.isNull() && depth < 4) {
        try {
            const iter = Memory.alloc(Process.pointerSize);
            iter.writePointer(ptr(0));
            for (;;) {
                const f = class_get_fields(k, iter) as NativePointer;
                if (f.isNull()) break;
                let type = "?";
                try {
                    const tc = type_get_class_or_element_class(
                        field_get_type(f) as NativePointer) as NativePointer;
                    if (!tc.isNull()) type = s(class_get_name(tc) as NativePointer);
                } catch { /* */ }
                out.push({
                    name: s(field_get_name(f) as NativePointer),
                    offset: field_get_offset(f) as number, type,
                });
            }
        } catch { /* */ }
        k = class_get_parent(k) as NativePointer;
        depth++;
    }
    return out;
}

export function register(ctx: Ctx): void {
    /** Étape 1 : pilote 1 MoveNext de CalculateNextActionForPlayer et décode
     *  l'action de la prochaine unité que l'IA jouerait — SANS commit. Sûr
     *  (ne mute pas le runner). Valide le pilotage manuel sur runner isolé.
     *  body: { runnerId?: number } — défaut = live runner. */
    ctx.rpc.aiStepDryRun = (
        body?: { runnerId?: number; maxPump?: number },
    ): Promise<DryRunResult> => queueOnMainThread((): DryRunResult => {
        const MAX_PUMP = (typeof body?.maxPump === "number" && body.maxPump > 0)
            ? body.maxPump : 2000;
        // 1. Runner cible.
        let runner: NativePointer;
        let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner;
            label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId or start a live battle" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };

        // 2. État + garde stage Running + joueur courant.
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) {
            return { ok: false, error: label + " _state null (not initialized)" };
        }
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: label + " stage " + (status.stageName ?? status.stage)
                    + " (need Running)" };
        }
        const playerId = status.currentTurnPlayer;
        if (playerId === null) {
            return { ok: false, runner: label, error: "no currentTurnPlayer" };
        }

        // 3. AiControl + stratégie.
        const aiControl = runner.add(runnerOff.aiControl).readPointer();
        if (aiControl.isNull()) {
            return { ok: false, runner: label, error: "aiControl null" };
        }
        const { strategy, src: strategySrc, err: strategyErr } =
            resolveStrategy(aiControl, playerId);
        if (strategy.isNull()) {
            return { ok: false, runner: label, playerId, strategyErr,
                error: "strategy unresolved" };
        }

        // 4. Player IEntity = entité dont l'id == currentTurnPlayer.
        const playerEntity = resolvePlayerEntity(statePtr, playerId);
        if (playerEntity.isNull()) {
            return { ok: false, runner: label, playerId,
                error: "player entity (id=" + playerId + ") not found in state" };
        }

        // 5. Snapshot AVANT.
        const before = summarize(statePtr);

        // 6. CalculateNextActionForPlayer(player) → enumerator.
        const strategyClass = strategy.readPointer();
        const cnafpMi = findMethod(strategyClass, "CalculateNextActionForPlayer");
        if (!cnafpMi) {
            return { ok: false, runner: label, playerId, strategySrc,
                error: "CalculateNextActionForPlayer not found on "
                    + s(class_get_name(strategyClass) as NativePointer) };
        }
        let enumerator: NativePointer;
        try {
            enumerator = invokeMethod(cnafpMi.info, strategy, [playerEntity]);
        } catch (e) {
            return { ok: false, runner: label, playerId, strategySrc,
                error: "CalculateNextActionForPlayer threw: " + (e as Error).message };
        }
        if (enumerator.isNull()) {
            return { ok: false, runner: label, playerId, strategySrc,
                error: "enumerator null" };
        }

        // 7. UN MoveNext, lire <>2__current @0x18, décoder. Pin l'enumerator
        //    le temps de la séquence (les invoke peuvent déclencher un GC).
        gcRoot.add(enumerator);
        try {
            const enumClass = enumerator.readPointer();
            const moveNextMi = findMethod(enumClass, "MoveNext");
            if (!moveNextMi) {
                return { ok: false, runner: label, playerId, strategySrc,
                    error: "MoveNext not found on enumerator" };
            }
            // Pompe MoveNext jusqu'à une liste NON-VIDE (l'action d'une unité)
            // ou épuisement. La coroutine yield des listes vides pendant le
            // calcul multi-frame (decisionStopWatch / runAiCalculationsInMultipleFrames).
            let hasNext = false;
            let moveNextCalls = 0;
            let emptyYields = 0;
            let action: { count: number; messages: DecodedMsg[] } | null = null;
            let activatedUnitId: number | null = null;
            try {
                while (moveNextCalls < MAX_PUMP) {
                    const boxed = invokeMethod(moveNextMi.info, enumerator, null);
                    moveNextCalls++;
                    hasNext = !boxed.isNull() && boxed.add(0x10).readU8() !== 0;
                    if (!hasNext) break;  // tour épuisé, aucune action
                    // d__6 : <>2__current @0x18 = la List<IInputMessage> yieldée.
                    const list = enumerator.add(0x18).readPointer();
                    const decoded = decodeMsgList(list);
                    if (decoded.count > 0) {  // action d'une unité prête
                        action = decoded;
                        for (const m of decoded.messages) {
                            if (m.cls === "MoveUnitMessage" && m.unitId !== undefined) {
                                activatedUnitId = m.unitId; break;
                            }
                            if (m.cls === "FinishUnitTurnMessage"
                                && m.unitId !== undefined
                                && activatedUnitId === null) {
                                activatedUnitId = m.unitId;
                            }
                        }
                        break;
                    }
                    emptyYields++;  // yield vide = calcul en cours, on re-pompe
                }
            } catch (e) {
                return { ok: false, runner: label, playerId, strategySrc,
                    error: "MoveNext threw after " + moveNextCalls
                        + " calls: " + (e as Error).message,
                    moveNextCalls, emptyYields, before };
            }

            // Re-projection APRÈS pour confirmer que le dry-run n'a rien mué.
            const after = summarize(statePtr);
            return {
                ok: true, runner: label, playerId, strategySrc, strategyErr,
                hasNext, moveNextCalls, emptyYields, action, activatedUnitId,
                mutated: before.sig !== after.sig,
                before,
            };
        } finally {
            try { gcRoot.remove(enumerator); } catch { /* best effort */ }
        }
    });

    /** Driver per-unité COMPLET (sans CheatRunAIMessage) : pour chaque tour
     *  d'équipe, pilote CalculateNextActionForPlayer — pompe MoveNext jusqu'à
     *  un chunk non-vide, snapshot l'état AVANT chaque MoveUnitMessage, applique
     *  le chunk (runner.Apply), re-pompe ; à l'épuisement, EndTurn → équipe
     *  suivante. Capture 1 démo (état, unité, déplacement) par activation avec
     *  déplacement. L'IA choisit unité + position ; on ne contrôle que le grain.
     *  body: { runnerId, maxTurns?, maxActivations?, maxPump? } */
    ctx.rpc.aiPlayByUnit = (
        body?: {
            runnerId?: number; maxTurns?: number;
            maxActivations?: number; maxPump?: number;
            probeEachTurn?: boolean; captureEvents?: boolean;
            captureOverwatch?: boolean;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        // Runner cible.
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!runnerApplyMi) return { ok: false, error: "runner.Apply not resolved" };

        const maxTurns = body?.maxTurns ?? 60;
        const maxActivations = body?.maxActivations ?? 400;
        const maxPump = (typeof body?.maxPump === "number" && body.maxPump > 0)
            ? body.maxPump : 30000;
        const probeEachTurn = body?.probeEachTurn === true;
        // Capture de TOUTE la cascade du tour, uniformément : chaque event
        // StreamDispatcher de chaque activation, annoté par l'activation qui l'a
        // produit (turn/player/unit/message). PAS de cas spécial overwatch —
        // l'overwatch est un event comme un autre (UnitDamaged Effect_Type=1009),
        // décodé côté Python (stream_events) au même titre que counter, aura, DoT,
        // kills. Alias rétro-compat : captureOverwatch.
        const captureEvents = body?.captureEvents === true
            || body?.captureOverwatch === true;
        const cascade: Array<StreamEvent & {
            turnIndex: number; player: number;
            activationUnitId: number | null; msgCls: string;
        }> = [];
        const t0 = Date.now();
        const demos: UnitDemo[] = [];
        const turnProbes: Array<{
            turnIndex: number; player: number; proposals: UnitProposal[];
        }> = [];
        let turnsPlayed = 0;
        let totalActivations = 0;
        let totalPumps = 0;
        let stopReason = "maxTurns";

        while (turnsPlayed < maxTurns) {
            const statePtr = runner.add(runnerOff.state).readPointer();
            if (statePtr.isNull()) { stopReason = "state null"; break; }
            const status = readBattleStatus(statePtr);
            if (status.stage !== 1) {
                stopReason = "stage " + (status.stageName ?? status.stage); break;
            }
            const playerId = status.currentTurnPlayer;
            if (playerId === null) { stopReason = "no currentTurnPlayer"; break; }
            const aiControl = runner.add(runnerOff.aiControl).readPointer();
            if (aiControl.isNull()) { stopReason = "aiControl null"; break; }
            const { strategy } = resolveStrategy(aiControl, playerId);
            if (strategy.isNull()) { stopReason = "strategy null"; break; }
            const playerEntity = resolvePlayerEntity(statePtr, playerId);
            if (playerEntity.isNull()) {
                stopReason = "player entity " + playerId + " not found"; break;
            }
            const cnafpMi = findMethod(
                strategy.readPointer(), "CalculateNextActionForPlayer");
            if (!cnafpMi) { stopReason = "CalculateNextActionForPlayer not found"; break; }

            // Probe READ-ONLY en début de tour : ce que chaque unité ferait,
            // contre l'état de DÉBUT de tour (avant que l'équipe ne joue).
            if (probeEachTurn) {
                const calcUnitMi = findMethod(
                    strategy.readPointer(), "CalculateNextActionForUnit");
                if (calcUnitMi) {
                    const sweep = sweepAllUnitProposals(
                        statePtr, strategy, calcUnitMi, maxPump, { mi: null });
                    totalPumps += sweep.pumps;
                    turnProbes.push({
                        turnIndex: turnsPlayed, player: playerId,
                        proposals: sweep.units,
                    });
                }
            }

            // Boucle de PAS du tour : CalculateNextActionForPlayer yield UN seul
            // pas (1 liste) puis se termine — comme le d__16, on RE-CRÉE
            // l'énumérateur à chaque pas, jusqu'à ce que le tour passe (la main
            // change) ou qu'aucune action ne soit produite (tour épuisé).
            let moveNextMi: { info: NativePointer; ptr: NativePointer } | null = null;
            let turnErr: string | null = null;
            let step = 0;
            const MAX_STEPS = 250;
            try {
                while (step < MAX_STEPS && totalActivations < maxActivations) {
                    step++;
                    // Énumérateur FRAIS pour ce pas.
                    const e = invokeMethod(cnafpMi.info, strategy, [playerEntity]);
                    if (e.isNull()) break;
                    gcRoot.add(e);
                    if (!moveNextMi) moveNextMi = findMethod(e.readPointer(), "MoveNext");
                    let chunk: Array<{ ptr: NativePointer; decoded: DecodedMsg }>
                        | null = null;
                    try {
                        let pumps = 0;
                        while (moveNextMi && pumps < maxPump) {
                            const boxed = invokeMethod(moveNextMi.info, e, null);
                            pumps++; totalPumps++;
                            if (boxed.isNull() || boxed.add(0x10).readU8() === 0) break;
                            const items = processMsgList(e.add(0x18).readPointer());
                            if (items.length > 0) { chunk = items; break; }
                        }
                    } finally {
                        try { gcRoot.remove(e); } catch { /* best effort */ }
                    }
                    if (!chunk) break;  // aucune action → tour épuisé

                    // Snapshot AVANT si le pas contient un déplacement.
                    const hasMove = chunk.some(
                        (it) => it.decoded.cls === "MoveUnitMessage");
                    const snap = hasMove ? captureStateForDemo(statePtr) : null;
                    for (const it of chunk) {
                        if (it.decoded.cls === "MoveUnitMessage" && snap
                            && it.decoded.unitId !== undefined) {
                            demos.push({
                                turnIndex: turnsPlayed,
                                player: playerId,
                                activatedUnitId: it.decoded.unitId,
                                move: {
                                    to: it.decoded.to ?? null,
                                    pathLen: it.decoded.pathLen ?? 0,
                                },
                                toActivate: snap.toActivate,
                                units: snap.units,
                            });
                            totalActivations++;
                        }
                        // Applique via ApplyAiMessage (→ _inputProcessor), PAS
                        // runner.Apply direct : sinon l'action n'est pas
                        // consommée côté AI/turn et l'unité reste « à jouer ».
                        if (captureEvents && applyAiMsgMi) {
                            // Wrap l'apply dans une frame → capture TOUTE la
                            // cascade de cette activation (applyAiMsgMi hooké
                            // NON-top → sans frame, events dans le vide). Aucun
                            // filtre : tout remonte, annoté ; décodage Python.
                            ensureStreamHooks();
                            const evs: StreamEvent[] = [];
                            pushApply("built", evs);
                            try { invokeMethod(applyAiMsgMi.info, aiControl, [it.ptr]); }
                            finally { try { popApply(); } catch { /* */ } }
                            for (const ev of evs) {
                                cascade.push({
                                    ...ev, turnIndex: turnsPlayed, player: playerId,
                                    activationUnitId: it.decoded.unitId ?? null,
                                    msgCls: it.decoded.cls,
                                });
                            }
                        } else if (applyAiMsgMi) {
                            invokeMethod(applyAiMsgMi.info, aiControl, [it.ptr]);
                        } else {
                            invokeMethod(runnerApplyMi.info, runner, [it.ptr]);
                        }
                    }

                    // La main a-t-elle changé (tour passé) ?
                    const sp = runner.add(runnerOff.state).readPointer();
                    if (!sp.isNull()
                        && readBattleStatus(sp).currentTurnPlayer !== playerId) {
                        break;
                    }
                }
            } catch (e) {
                turnErr = (e as Error).message;
            }
            if (turnErr) { stopReason = "turn err: " + turnErr; break; }
            turnsPlayed++;

            // Force le passage de tour si toujours le même joueur (et battle pas finie).
            const sp2 = runner.add(runnerOff.state).readPointer();
            if (!sp2.isNull()) {
                const st2 = readBattleStatus(sp2);
                if (st2.stage === 1 && st2.currentTurnPlayer === playerId) {
                    try {
                        // Capture aussi les effets de FRONTIÈRE de tour (ticks
                        // d'AoE/DoT résolus à l'EndTurn) dans la cascade.
                        if (captureEvents) {
                            const evs: StreamEvent[] = [];
                            applyEndTurn(runner, evs);
                            for (const ev of evs) {
                                cascade.push({
                                    ...ev, turnIndex: turnsPlayed, player: playerId,
                                    activationUnitId: null, msgCls: "EndTurnMessage",
                                });
                            }
                        } else {
                            applyEndTurn(runner);
                        }
                    } catch (e) {
                        stopReason = "endturn threw: " + (e as Error).message; break;
                    }
                }
            }
            if (totalActivations >= maxActivations) {
                stopReason = "maxActivations"; break;
            }
        }

        const spEnd = runner.add(runnerOff.state).readPointer();
        const endStatus = spEnd.isNull() ? null : readBattleStatus(spEnd);
        return {
            ok: true, runner: label,
            turnsPlayed, totalActivations, totalPumps,
            ms: Date.now() - t0, stopReason,
            finalStage: endStatus?.stage ?? null,
            finalStageName: endStatus?.stageName ?? null,
            finalPlayer: endStatus?.currentTurnPlayer ?? null,
            demoCount: demos.length, demos,
            probeCount: turnProbes.length, turnProbes,
            cascadeCount: cascade.length, cascade,
        };
    });

    /** INTERVENTION étape 1 : FORCER l'ordre d'activation. Au lieu de laisser
     *  PickNextUnit choisir, on désigne nous-mêmes l'unité et on pilote
     *  `CalculateNextActionForUnit(unit)` (l'IA décide quoi fait l'unité, nous
     *  décidons QUI joue et dans quel ordre).
     *  body: { runnerId, order?: "asc"|"desc"|number[], maxTurns?,
     *          maxActivations?, maxPump? } — order défaut "desc". */
    ctx.rpc.aiPlayOrdered = (
        body?: {
            runnerId?: number; order?: "asc" | "desc" | number[];
            maxTurns?: number; maxActivations?: number; maxPump?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!applyAiMsgMi && !runnerApplyMi) {
            return { ok: false, error: "no apply method resolved" };
        }

        const order = body?.order ?? "desc";
        const maxTurns = body?.maxTurns ?? 60;
        const maxActivations = body?.maxActivations ?? 400;
        const maxPump = (typeof body?.maxPump === "number" && body.maxPump > 0)
            ? body.maxPump : 30000;
        const MAX_STEPS_PER_UNIT = 40;
        const t0 = Date.now();
        const demos: UnitDemo[] = [];
        const turnOrders: Array<{ turnIndex: number; player: number; order: number[] }> = [];
        let turnsPlayed = 0;
        let totalActivations = 0;
        let totalPumps = 0;
        let stopReason = "maxTurns";
        let moveNextMi: { info: NativePointer; ptr: NativePointer } | null = null;

        while (turnsPlayed < maxTurns) {
            const statePtr = runner.add(runnerOff.state).readPointer();
            if (statePtr.isNull()) { stopReason = "state null"; break; }
            const status = readBattleStatus(statePtr);
            if (status.stage !== 1) {
                stopReason = "stage " + (status.stageName ?? status.stage); break;
            }
            const playerId = status.currentTurnPlayer;
            if (playerId === null) { stopReason = "no currentTurnPlayer"; break; }
            const aiControl = runner.add(runnerOff.aiControl).readPointer();
            if (aiControl.isNull()) { stopReason = "aiControl null"; break; }
            const { strategy } = resolveStrategy(aiControl, playerId);
            if (strategy.isNull()) { stopReason = "strategy null"; break; }
            const calcUnitMi = findMethod(
                strategy.readPointer(), "CalculateNextActionForUnit");
            if (!calcUnitMi) { stopReason = "CalculateNextActionForUnit not found"; break; }

            // NOTRE ordre d'activation imposé.
            const myUnits = validSquadsOrdered(statePtr, order);
            const playedThisTurn: number[] = [];
            let turnErr: string | null = null;

            try {
                for (const u of myUnits) {
                    if (totalActivations >= maxActivations) break;
                    // Re-vérifie : l'unité peut avoir été tuée / avoir agi via
                    // une réaction pendant l'activation d'une autre.
                    if (!invokeBool(isAliveMi, [u.ptr, statePtr])) continue;
                    if (!invokeBool(hasActionLeftMi, [u.ptr])) continue;
                    playedThisTurn.push(u.id);

                    // Force-joue cette unité jusqu'à épuisement de ses actions.
                    let g = 0;
                    while (g < MAX_STEPS_PER_UNIT
                        && invokeBool(hasActionLeftMi, [u.ptr])
                        && invokeBool(isAliveMi, [u.ptr, statePtr])) {
                        g++;
                        const e = invokeMethod(calcUnitMi.info, strategy, [u.ptr]);
                        if (e.isNull()) break;
                        gcRoot.add(e);
                        if (!moveNextMi) {
                            moveNextMi = findMethod(e.readPointer(), "MoveNext");
                        }
                        let chunk: Array<{ ptr: NativePointer; decoded: DecodedMsg }>
                            | null = null;
                        try {
                            let pumps = 0;
                            while (moveNextMi && pumps < maxPump) {
                                const boxed = invokeMethod(moveNextMi.info, e, null);
                                pumps++; totalPumps++;
                                if (boxed.isNull() || boxed.add(0x10).readU8() === 0) break;
                                const items = processMsgList(e.add(0x18).readPointer());
                                if (items.length > 0) { chunk = items; break; }
                            }
                        } finally {
                            try { gcRoot.remove(e); } catch { /* best effort */ }
                        }
                        if (!chunk) break;  // plus d'action pour cette unité

                        const hasMove = chunk.some(
                            (it) => it.decoded.cls === "MoveUnitMessage");
                        const snap = hasMove ? captureStateForDemo(statePtr) : null;
                        for (const it of chunk) {
                            if (it.decoded.cls === "MoveUnitMessage" && snap
                                && it.decoded.unitId !== undefined) {
                                demos.push({
                                    turnIndex: turnsPlayed, player: playerId,
                                    activatedUnitId: it.decoded.unitId,
                                    move: {
                                        to: it.decoded.to ?? null,
                                        pathLen: it.decoded.pathLen ?? 0,
                                    },
                                    toActivate: snap.toActivate, units: snap.units,
                                });
                                totalActivations++;
                            }
                            if (applyAiMsgMi) {
                                invokeMethod(applyAiMsgMi.info, aiControl, [it.ptr]);
                            } else {
                                invokeMethod(runnerApplyMi!.info, runner, [it.ptr]);
                            }
                        }
                        const sp = runner.add(runnerOff.state).readPointer();
                        if (!sp.isNull()
                            && readBattleStatus(sp).currentTurnPlayer !== playerId) {
                            break;
                        }
                    }
                }
            } catch (e) {
                turnErr = (e as Error).message;
            }
            turnOrders.push({ turnIndex: turnsPlayed, player: playerId, order: playedThisTurn });
            if (turnErr) { stopReason = "turn err: " + turnErr; break; }
            turnsPlayed++;

            const sp2 = runner.add(runnerOff.state).readPointer();
            if (!sp2.isNull()) {
                const st2 = readBattleStatus(sp2);
                if (st2.stage === 1 && st2.currentTurnPlayer === playerId) {
                    try { applyEndTurn(runner); }
                    catch (e) {
                        stopReason = "endturn threw: " + (e as Error).message; break;
                    }
                }
            }
            if (totalActivations >= maxActivations) { stopReason = "maxActivations"; break; }
        }

        return {
            ok: true, runner: label, orderMode: order,
            turnsPlayed, totalActivations, totalPumps,
            ms: Date.now() - t0, stopReason,
            turnOrders, demoCount: demos.length, demos,
        };
    });

    /** DRY-RUN sur TOUTES les units du joueur courant : pour chaque squad
     *  contrôlé + vivant, pompe `CalculateNextActionForUnit(unit)` pour lire
     *  l'action proposée par l'IA — SANS appliquer. Read-only (vérifie
     *  mutated=false). Donne, contre le MÊME état courant, ce que ferait
     *  chaque unité « si elle jouait en premier ». body: { runnerId, maxPump? } */
    ctx.rpc.aiDryRunAllUnits = (
        body?: { runnerId?: number; maxPump?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const maxPump = (typeof body?.maxPump === "number" && body.maxPump > 0)
            ? body.maxPump : 30000;

        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status.stageName ?? status.stage) };
        }
        const playerId = status.currentTurnPlayer;
        if (playerId === null) return { ok: false, error: "no currentTurnPlayer" };
        const aiControl = runner.add(runnerOff.aiControl).readPointer();
        if (aiControl.isNull()) return { ok: false, error: "aiControl null" };
        const { strategy } = resolveStrategy(aiControl, playerId);
        if (strategy.isNull()) return { ok: false, error: "strategy null" };
        const calcUnitMi = findMethod(
            strategy.readPointer(), "CalculateNextActionForUnit");
        if (!calcUnitMi) {
            return { ok: false, error: "CalculateNextActionForUnit not found" };
        }

        // Map squadId → (visualId, pos) pour identifier les unités (ex.
        // Terminators) et mesurer la distance du déplacement proposé.
        const proj = projectMatchState(statePtr);
        const visById = new Map<number, string | null>();
        const posById = new Map<number, { col: number; row: number } | null>();
        for (const u of proj.units) {
            visById.set(u.squadId, u.visualId);
            posById.set(u.squadId, u.pos);
        }

        const before = summarize(statePtr);
        const t0 = Date.now();
        const { units, pumps } = sweepAllUnitProposals(
            statePtr, strategy, calcUnitMi, maxPump, { mi: null });
        const after = summarize(statePtr);
        const unitsWithVis = units.map((u) => ({
            ...u,
            visualId: visById.get(u.unitId) ?? null,
            pos: posById.get(u.unitId) ?? null,
        }));
        return {
            ok: true, runner: label, playerId,
            mutated: before.sig !== after.sig,
            totalPumps: pumps, ms: Date.now() - t0,
            unitCount: unitsWithVis.length, units: unitsWithVis,
        };
    });

    /** DRY-RUN des tiles atteignables : pour chaque squad contrôlé+vivant du
     *  joueur courant, appelle `MovementQuery.GetMovableTilesFor(unit, false, {})`
     *  et extrait l'ensemble des tiles légales — SANS muter. Une deep-strike
     *  unit (TeleportStrike) aura un ensemble plus large (téléport). body:
     *  { runnerId } */
    ctx.rpc.aiMovableTiles = (
        body?: {
            runnerId?: number;
            side?: "friendly" | "enemy" | "all";
            dangerZone?: boolean;
            threat?: boolean;
            extraRange?: number;     // OverrideRangeBonus.ExtraRange (+N, buff)
            overrideRange?: number;  // OverrideRange (absolu, sûr)
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        const side = body?.side ?? "friendly";
        const dangerZone = body?.dangerZone === true;
        const threat = body?.threat === true;
        const extraRange = (typeof body?.extraRange === "number")
            ? (body.extraRange | 0) : 0;
        const overrideRange = (typeof body?.overrideRange === "number")
            ? (body.overrideRange | 0) : null;
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getMovableTilesMi) {
            return { ok: false, error: "GetMovableTilesFor(3) not resolved" };
        }
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status.stageName ?? status.stage) };
        }
        const playerId = status.currentTurnPlayer;
        const movementQuery = runner.add(movementQueryOff).readPointer();
        if (movementQuery.isNull()) {
            return { ok: false, error: "MovementQuery null on runner" };
        }
        const attackQuery = runner.add(attackQueryOff).readPointer();
        let getAllTilesMi: { info: NativePointer; ptr: NativePointer } | null = null;

        const proj = projectMatchState(statePtr);
        const visById = new Map<number, string | null>();
        const posById = new Map<number, { col: number; row: number } | null>();
        for (const u of proj.units) {
            visById.set(u.squadId, u.visualId);
            posById.set(u.squadId, u.pos);
        }

        const before = summarize(statePtr);
        const results: Array<{
            unitId: number; visualId: string | null;
            pos: { col: number; row: number } | null;
            tileCount: number; tiles: Array<{ col: number; row: number }>;
            threatCount: number; threatTiles: Array<{ col: number; row: number }>;
            err: string | null;
        }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit) return;
            if (!invokeBool(isAliveMi, [e, statePtr])) return;
            const ctrl = invokeBool(isCtrlByCurMi, [e, statePtr]);
            if (side === "friendly" && !ctrl) return;
            if (side === "enemy" && ctrl) return;
            const boolBuf = Memory.alloc(1); boolBuf.writeU8(0);
            // MovementOptions = 0x30 octets (Nullable<RangeBonus> @0x10).
            const optsBuf = Memory.alloc(0x30);
            for (let k = 0; k < 0x30; k += 4) optsBuf.add(k).writeU32(0);
            // MovementOptions.IsDangerZone @0x2 — ce que l'UI passe pour la
            // surbrillance rouge (menace : déplacement + portée d'attaque).
            if (dangerZone) optsBuf.add(0x2).writeU8(1);
            // OverrideRange (Nullable<int> @0x4 : hasValue@0x4, value@0x8) — absolu.
            if (overrideRange !== null) {
                optsBuf.add(0x4).writeU8(1);
                optsBuf.add(0x8).writeS32(overrideRange);
            }
            // OverrideRangeBonus (Nullable<RangeBonus> @0x10) — le VRAI champ
            // d'un buff de move (Warboss actif, Sibyll/Makothep) :
            //   hasValue@0x10 · RangeBonus.ExtraRange@0x18 ·
            //   ExtraRangeCondition(Func)@0x20=null (→ inconditionnel) ·
            //   ReduceRange(Nullable<int>)@0x28=0.
            if (extraRange !== 0) {
                optsBuf.add(0x10).writeU8(1);
                optsBuf.add(0x18).writeS32(extraRange);
            }
            let tiles: Array<{ col: number; row: number }> = [];
            let threatTiles: Array<{ col: number; row: number }> = [];
            let err: string | null = null;
            try {
                const os = invokeMethod(
                    getMovableTilesMi.info, movementQuery, [e, boolBuf, optsBuf]);
                tiles = extractTiles(os);
                // Menace = move ∪ portée d'attaque depuis ces tiles :
                // AttackQuery.GetAllTilesInAbilityRange(unit, moveTiles, true).
                if (threat && !attackQuery.isNull() && !os.isNull()) {
                    if (!getAllTilesMi) {
                        getAllTilesMi = findMethodByParamCount(
                            attackQuery.readPointer(),
                            "GetAllTilesInAbilityRange", 3);
                    }
                    if (getAllTilesMi) {
                        const incBuf = Memory.alloc(1); incBuf.writeU8(1);
                        const tos = invokeMethod(
                            getAllTilesMi.info, attackQuery, [e, os, incBuf]);
                        threatTiles = extractTiles(tos);
                    }
                }
            } catch (ex) { err = (ex as Error).message; }
            results.push({
                unitId: id, visualId: visById.get(id) ?? null,
                pos: posById.get(id) ?? null,
                tileCount: tiles.length, tiles,
                threatCount: threatTiles.length, threatTiles,
                err,
            });
        });
        const after = summarize(statePtr);
        // Union (danger zone agrégée) — sur la menace si threat, sinon le move.
        const unionKeys = new Set<string>();
        for (const r of results) {
            const src = threat ? r.threatTiles : r.tiles;
            for (const t of src) unionKeys.add(t.col + "," + t.row);
        }
        return {
            ok: true, runner: label, playerId, side, dangerZone,
            mutated: before.sig !== after.sig,
            unionTileCount: unionKeys.size,
            unionTiles: [...unionKeys].map((k) => {
                const [c, r] = k.split(",").map(Number);
                return { col: c, row: r };
            }),
            unitCount: results.length, units: results,
        };
    });

    /** RANKING des tiles d'attaque par (unit, target) — shrink-and-recall sur
     *  `AttackQuery.GetBestTileToAttackFrom(unit, movableSet, target, ability)`.
     *  GetBestTileToAttackFrom rend l'argmax de l'utilité IA (1 tile) parmi les
     *  positions LÉGALES d'où `unit` peut attaquer `target` avec `ability`. On
     *  retire cette tile du set et on rappelle → 2e meilleure, etc. Donne, par
     *  ennemi ciblable, la LISTE RANKÉE des positions d'attaque (fallback quand
     *  2 units se disputent une tile : l'unité battue prend sa tile suivante).
     *  Read-only sur l'état (on ne mute qu'un IOrderedSet transient créé par
     *  GetMovableTilesFor, pas le MatchState). Signature C# (dump kqkbjqfb6c) :
     *    IEntity GetBestTileToAttackFrom(IEntity unit, IOrderedSet<IEntity> tiles,
     *                                    IEntity target, ActiveAbilityType ability)
     *  AUTONOME : si `abilityType` n'est pas fourni, on lit les abilities
     *  CONCRÈTES de chaque unité (NormalAttackType + GetActives si allAbilities) —
     *  l'attaque normale a un id typé par unité (ex. Loki_NormalAttack=69), pas
     *  l'abstrait 17. La tile COURANTE de l'unité (GetMainTile) est ajoutée au set
     *  candidat (GetMovableTilesFor l'exclut → sinon « rester sur place et
     *  attaquer » manquerait au ranking).
     *  body: { runnerId, unitId?, targetId?, abilityType?, allAbilities?=false,
     *          maxRank?=8, overrideRange? } — unitId/targetId absents = toutes les
     *  units/ennemis ; abilityType absent = abilities réelles de chaque unité. */
    ctx.rpc.aiAttackRank = (
        body?: {
            runnerId?: number; unitId?: number; targetId?: number;
            abilityType?: number; allAbilities?: boolean;
            maxRank?: number; overrideRange?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        const manualAbility = (typeof body?.abilityType === "number")
            ? (body.abilityType | 0) : null;
        const allAbilities = body?.allAbilities === true;
        const maxRank = (typeof body?.maxRank === "number" && body.maxRank > 0)
            ? (body.maxRank | 0) : 8;
        // Diag : portée de move forcée (Nullable<int> @0x4) — géante = toute la
        // map atteignable, isole « hors portée » de « ability non résolue ».
        const overrideRange = (typeof body?.overrideRange === "number")
            ? (body.overrideRange | 0) : null;
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getMovableTilesMi) {
            return { ok: false, error: "GetMovableTilesFor(3) not resolved" };
        }
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status.stageName ?? status.stage) + " (need Running)" };
        }
        const playerId = status.currentTurnPlayer;
        const movementQuery = runner.add(movementQueryOff).readPointer();
        if (movementQuery.isNull()) return { ok: false, error: "MovementQuery null" };
        const attackQuery = runner.add(attackQueryOff).readPointer();
        if (attackQuery.isNull()) return { ok: false, error: "AttackQuery null" };

        // GetBestTileToAttackFrom(unit, tiles, target, ability) — 4 params logiques.
        const getBestMi = findMethodByParamCount(
            attackQuery.readPointer(), "GetBestTileToAttackFrom", 4);
        if (!getBestMi) {
            return { ok: false, error: "GetBestTileToAttackFrom(4) not resolved on "
                + s(class_get_name(attackQuery.readPointer()) as NativePointer) };
        }

        // Identité (visualId/pos) pour lisibilité.
        const proj = projectMatchState(statePtr);
        const visById = new Map<number, string | null>();
        const posById = new Map<number, { col: number; row: number } | null>();
        for (const u of proj.units) {
            visById.set(u.squadId, u.visualId);
            posById.set(u.squadId, u.pos);
        }

        // Units à ranker (contrôlées+vivantes) et cibles ennemies (vivantes).
        const myUnits: Array<{ id: number; ptr: NativePointer }> = [];
        const enemies: Array<{ id: number; ptr: NativePointer }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit) return;
            if (!invokeBool(isAliveMi, [e, statePtr])) return;
            const ctrl = invokeBool(isCtrlByCurMi, [e, statePtr]);
            if (ctrl) {
                if (body?.unitId === undefined || body.unitId === id) {
                    myUnits.push({ id, ptr: e });
                }
            } else if (body?.targetId === undefined || body.targetId === id) {
                enemies.push({ id, ptr: e });
            }
        });

        // Args value-type : ability (int) réécrit par eval ; bool false.
        const abilBuf = Memory.alloc(4);
        const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
        // MovementOptions = 0x30 octets, tout à zéro (pas de buff/override).
        const optsZero = Memory.alloc(0x30);
        for (let k = 0; k < 0x30; k += 4) optsZero.add(k).writeU32(0);
        if (overrideRange !== null) {
            optsZero.add(0x4).writeU8(1);
            optsZero.add(0x8).writeS32(overrideRange);
        }

        // Remove/Add(IEntity) sur l'IOrderedSet (résolus lazy depuis sa classe runtime).
        let removeMi: { info: NativePointer; ptr: NativePointer } | null = null;
        let addMi: { info: NativePointer; ptr: NativePointer } | null = null;
        let setResolved = false;
        let removeWorks: boolean | null = null;

        const before = summarize(statePtr);
        const t0 = Date.now();
        interface AttackEval {
            targetId: number; targetVis: string | null;
            targetPos: { col: number; row: number } | null;
            abilityId: number; ability: string; kind: string;
            movableCount: number; rankCount: number;
            ranked: Array<{ col: number; row: number }>; err: string | null;
        }
        const results: Array<{
            unitId: number; visualId: string | null;
            pos: { col: number; row: number } | null;
            currentTile: { col: number; row: number } | null;
            abilities: Array<{ id: number; name: string; kind: string }>;
            evals: AttackEval[];
        }> = [];

        for (const u of myUnits) {
            // Abilities concrètes à ranker : override manuel sinon auto-découverte.
            const abilities = (manualAbility !== null)
                ? [{ id: manualAbility,
                     name: abilityName(manualAbility) ?? "id:" + manualAbility,
                     kind: "manual" }]
                : unitAbilityTypes(u.ptr, allAbilities);
            // Tile courante (ajoutée au set candidat = option « rester sur place »).
            const mainTile = getUnitMainTile(u.ptr, statePtr);
            const currentTile = mainTile.isNull() ? null : readTileCoord(mainTile);
            const evals: AttackEval[] = [];

            for (const ab of abilities) {
                abilBuf.writeS32(ab.id);
                for (const tgt of enemies) {
                    // Set FRAIS (mutable) pour CE triplet (unit, ability, target).
                    let set: NativePointer;
                    try {
                        set = invokeMethod(
                            getMovableTilesMi.info, movementQuery,
                            [u.ptr, boolFalse, optsZero]);
                    } catch (e) {
                        evals.push({
                            targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                            targetPos: posById.get(tgt.id) ?? null,
                            abilityId: ab.id, ability: ab.name, kind: ab.kind,
                            movableCount: 0, rankCount: 0, ranked: [],
                            err: "movable: " + (e as Error).message });
                        continue;
                    }
                    if (set.isNull()) {
                        evals.push({
                            targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                            targetPos: posById.get(tgt.id) ?? null,
                            abilityId: ab.id, ability: ab.name, kind: ab.kind,
                            movableCount: 0, rankCount: 0, ranked: [], err: "movable null" });
                        continue;
                    }
                    if (!setResolved) {
                        removeMi = findMethodByParamCount(set.readPointer(), "Remove", 1);
                        addMi = findMethodByParamCount(set.readPointer(), "Add", 1);
                        setResolved = true;
                    }
                    gcRoot.add(set);
                    let err: string | null = null;
                    // Ajoute la tile courante au set candidat (Add idempotent).
                    if (!mainTile.isNull() && addMi) {
                        try { invokeMethod(addMi.info, set, [mainTile]); }
                        catch { /* */ }
                    }
                    const movableCount = extractTilePtrs(set).length;
                    const ranked: Array<{ col: number; row: number }> = [];
                    try {
                        for (let r = 0; r < maxRank; r++) {
                            const best = invokeMethod(
                                getBestMi.info, attackQuery,
                                [u.ptr, set, tgt.ptr, abilBuf]);
                            if (best.isNull()) break;  // plus de position d'attaque
                            ranked.push(readTileCoord(best));
                            if (!removeMi) {
                                err = "Remove not resolved (rang tronqué à 1)"; break;
                            }
                            const removed = invokeMethod(removeMi.info, set, [best]);
                            const ok = !removed.isNull() && removed.add(0x10).readU8() !== 0;
                            if (ok) { removeWorks = true; }
                            else { err = "Remove a renvoyé false (stop)"; break; }
                        }
                    } catch (e) { err = (e as Error).message; }
                    finally { try { gcRoot.remove(set); } catch { /* */ } }
                    evals.push({
                        targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                        targetPos: posById.get(tgt.id) ?? null,
                        abilityId: ab.id, ability: ab.name, kind: ab.kind,
                        movableCount, rankCount: ranked.length, ranked, err,
                    });
                }
            }
            results.push({
                unitId: u.id, visualId: visById.get(u.id) ?? null,
                pos: posById.get(u.id) ?? null, currentTile, abilities, evals,
            });
        }
        const after = summarize(statePtr);
        return {
            ok: true, runner: label, playerId,
            abilityMode: manualAbility !== null
                ? "manual:" + manualAbility
                : (allAbilities ? "auto+actives" : "auto-normal"),
            maxRank, overrideRange,
            mutated: before.sig !== after.sig, removeWorks,
            ms: Date.now() - t0,
            unitCount: results.length, enemyCount: enemies.length, units: results,
        };
    });

    /** decisionView — LA vue décision-ready en UN appel (couche DYNAMIQUE de
     *  l'oracle). Agrège : méta (stage/tour/joueur courant) ; TOUTES les units
     *  (pos hex/HP/team/owner/alive/ctrl/hasAction/ranged/abilities concrètes) ;
     *  les units à activer ; les plans d'attaque rankés du joueur courant
     *  (computeAttackPlans, normal attack par défaut) ; la DANGER ZONE ennemie.
     *  Read-only (mutated=false attendu). Python merge ensuite avec board.py
     *  (terrain/hex) + gameconfig.py (kits) + wiki (tactique).
     *  body: { runnerId, maxRank?=6, allAbilities?=false } */
    ctx.rpc.decisionView = (
        body?: { runnerId?: number; maxRank?: number; allAbilities?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        const allAbilities = body?.allAbilities === true;
        const maxRank = (typeof body?.maxRank === "number" && body.maxRank > 0)
            ? (body.maxRank | 0) : 6;
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getMovableTilesMi) {
            return { ok: false, error: "GetMovableTilesFor(3) not resolved" };
        }
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status.stageName ?? status.stage) + " (need Running)" };
        }
        const playerId = status.currentTurnPlayer;
        const movementQuery = runner.add(movementQueryOff).readPointer();
        if (movementQuery.isNull()) return { ok: false, error: "MovementQuery null" };
        const attackQuery = runner.add(attackQueryOff).readPointer();
        if (attackQuery.isNull()) return { ok: false, error: "AttackQuery null" };
        const getBestMi = findMethodByParamCount(
            attackQuery.readPointer(), "GetBestTileToAttackFrom", 4);
        if (!getBestMi) {
            return { ok: false, error: "GetBestTileToAttackFrom(4) not resolved" };
        }

        const before = summarize(statePtr);
        const t0 = Date.now();
        const proj = projectMatchState(statePtr);
        const units = projectUnitsFull(statePtr, allAbilities);
        const mows = projectMowsFull(statePtr, proj);
        // toActivate inclut les MoW jouables (ability-only) du joueur courant.
        const toActivate = [
            ...units.filter((u) => u.ctrl && u.alive && u.hasAction).map((u) => u.id),
            ...mows.filter((m) => m.ctrl && m.alive && m.hasAction).map((m) => m.casterId),
        ];
        const plans = computeAttackPlans(
            statePtr, movementQuery, attackQuery, getBestMi, resolveDpq(runner),
            { allAbilities, maxRank });
        const danger = computeDangerZone(statePtr, movementQuery, attackQuery);
        const after = summarize(statePtr);
        return {
            ok: true, runner: label,
            stage: status.stage, stageName: status.stageName,
            turn: proj.turn, currentPlayer: playerId,
            mutated: before.sig !== after.sig, ms: Date.now() - t0,
            unitCount: units.length, units,
            mowCount: mows.length, mows,
            toActivateCount: toActivate.length, toActivate,
            attackPlans: plans.units, removeWorks: plans.removeWorks,
            dangerZone: danger,
        };
    });

    /** DEBUG RE — dumpe les composants (classe + ns + champs nom/offset/type)
     *  d'une entité par id. Sert à localiser HP/abilities/position sur les MoW
     *  (Machine Type 6 / MachinePlatform Type 7) dont la structure diffère des
     *  squads. body: { runnerId?, entityId, withFields?=true } */
    ctx.rpc.dumpEntityComponents = (
        body?: { runnerId?: number; entityId?: number; withFields?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
        } else if (state.liveRunner) { runner = state.liveRunner; }
        else return { ok: false, error: "no runner — pass runnerId" };
        if (runner.isNull()) return { ok: false, error: "runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const target = body?.entityId;
        if (typeof target !== "number") return { ok: false, error: "pass entityId" };
        const withFields = body?.withFields !== false;
        let result: unknown = { ok: false, error: "entity " + target + " not found" };
        forEachEntity(statePtr, (e, id, ty) => {
            if (id !== target) return;
            const components: Array<unknown> = [];
            forEachComponent(e, (comp, klass) => {
                components.push({
                    cls: s(class_get_name(klass) as NativePointer),
                    ns: s(class_get_namespace(klass) as NativePointer),
                    comp: comp.toString(),
                    fields: withFields ? classFieldsDump(klass) : undefined,
                });
            });
            result = { ok: true, id, type: ty, entityPtr: e.toString(), components };
        });
        return result;
    });

    /** APPLIQUER MON COUP (Phase 5) — construit + applique une (ou des) action(s)
     *  via AiControl.ApplyAiMessage sur le runner, avec snapshot AVANT/APRÈS pour
     *  observer le résultat réel. Décomposable : 1 action par appel (move PUIS
     *  observe PUIS ability) → jouer une unité « en 2 temps ». MoW = ability seule
     *  (ne bougent pas). Faithful : SkipFlags=false → le moteur valide portée /
     *  action restante / overwatch.
     *  body: { runnerId?, action?, actions?[] }
     *    action: { kind:"move", unitId, to:{col,row} | feet:[{col,row}...] }
     *          | { kind:"ability", casterId, targetId, abilityType }
     *          | { kind:"finish", unitId } */
    ctx.rpc.applyAction = (
        body?: {
            runnerId?: number;
            action?: ActionSpec; actions?: ActionSpec[];
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (!applyAiMsgMi) return { ok: false, error: "ApplyAiMessage not resolved" };
        if (!moveUnitMsgClass || !activeAbilityMsgClass || !finishUnitTurnMsgClass) {
            return { ok: false, error: "message classes not resolved" };
        }
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status0 = readBattleStatus(statePtr);
        if (status0.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status0.stageName ?? status0.stage)
                    + " (need Running)" };
        }
        const aiControl = runner.add(runnerOff.aiControl).readPointer();
        if (aiControl.isNull()) return { ok: false, error: "aiControl null" };

        const actions = body?.actions ?? (body?.action ? [body.action] : []);
        if (!actions.length) {
            return { ok: false, error: "no action(s) — pass action/actions" };
        }

        const t0 = Date.now();
        const results: ActionResult[] = [];
        for (const a of actions) results.push(applyOneAction(runner, aiControl, a));

        const stateF = runner.add(runnerOff.state).readPointer();
        const finalStatus = readBattleStatus(stateF);
        const units = projectMatchState(stateF).units.map((u) => ({
            squadId: u.squadId, pos: u.pos, hp: u.hp, ownerId: u.ownerId,
        }));
        return {
            ok: results.every((r) => r.ok), runner: label, ms: Date.now() - t0,
            actions: results,
            stage: finalStatus.stage, stageName: finalStatus.stageName,
            currentPlayer: finalStatus.currentTurnPlayer,
            units,
        };
    });

    /** PROBE prédiction de dégâts : pour (unit, target) depuis une tile choisie
     *  (col,row ; défaut = tile courante), appelle
     *  `DamagePredictionQuery.GetAllPredictions(unit, selectedTile, ability)` →
     *  IDictionary<IEntity, DamagePredictionResult>, puis `dict.get_Item(target)`
     *  → struct boxée lue à +0x10. Read-only. Valide la chaîne d'invoke avant
     *  d'intégrer la prédiction aux attackPlans.
     *  body: { runnerId, unitId, targetId, abilityType?, col?, row? } */
    ctx.rpc.aiPredict = (
        body?: {
            runnerId?: number; unitId?: number; targetId?: number;
            abilityType?: number; col?: number; row?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getMovableTilesMi) return { ok: false, error: "GetMovableTilesFor(3) not resolved" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, error: "stage " + (status.stageName ?? status.stage) };
        }
        const movementQuery = runner.add(movementQueryOff).readPointer();
        // Instance portant GetAllPredictions : <DamagePredictionQuery> du runner
        // si présent, sinon l'attackQuery (BattleQuery god-object implémente tout).
        const dpqCands: Array<{ inst: NativePointer; src: string }> = [];
        if (servicesOff >= 0 && dpqInServicesOff >= 0) {
            const services = runner.add(servicesOff).readPointer();
            if (!services.isNull()) {
                const d = services.add(dpqInServicesOff).readPointer();
                if (!d.isNull()) {
                    dpqCands.push({ inst: d, src: "EntityServices.<DamagePredictionQuery>" });
                }
            }
        }
        const aq0 = runner.add(attackQueryOff).readPointer();
        if (!aq0.isNull()) dpqCands.push({ inst: aq0, src: "attackQuery" });
        let dpq = ptr(0);
        let getAllPredMi: { info: NativePointer; ptr: NativePointer } | null = null;
        let dpqSrc = "none";
        for (const c of dpqCands) {
            const mi = findMethodByParamCount(c.inst.readPointer(), "GetAllPredictions", 3);
            if (mi) { dpq = c.inst; getAllPredMi = mi; dpqSrc = c.src; break; }
        }
        if (!getAllPredMi) {
            return { ok: false, error: "GetAllPredictions(3) introuvable (servicesOff="
                + servicesOff + ", dpqInServices=" + dpqInServicesOff
                + ", cands=" + dpqCands.map((c) => c.src).join(",") + ")" };
        }

        let unit = ptr(0); let target = ptr(0);
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit) return;
            if (id === body?.unitId) unit = e;
            if (id === body?.targetId) target = e;
        });
        if (unit.isNull()) return { ok: false, error: "unit " + body?.unitId + " not found" };
        if (target.isNull()) return { ok: false, error: "target " + body?.targetId + " not found" };

        let ability = body?.abilityType;
        if (typeof ability !== "number") {
            const abs = unitAbilityTypes(unit, false);
            ability = abs.length ? abs[0].id : 0;
        }
        const abilBuf = Memory.alloc(4); abilBuf.writeS32(ability);

        // Tile attaquante : (col,row) dans le movable set, sinon tile courante.
        let tile = ptr(0);
        const wantCol = body?.col; const wantRow = body?.row;
        if (typeof wantCol === "number" && typeof wantRow === "number") {
            const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
            const optsZero = Memory.alloc(0x30);
            for (let k = 0; k < 0x30; k += 4) optsZero.add(k).writeU32(0);
            try {
                const os = invokeMethod(getMovableTilesMi.info, movementQuery,
                    [unit, boolFalse, optsZero]);
                for (const t of extractTilePtrs(os)) {
                    if (t.col === wantCol && t.row === wantRow) { tile = t.ptr; break; }
                }
            } catch { /* */ }
            if (tile.isNull()) {
                const mt = getUnitMainTile(unit, statePtr);
                if (!mt.isNull()) {
                    const c = readTileCoord(mt);
                    if (c.col === wantCol && c.row === wantRow) tile = mt;
                }
            }
            if (tile.isNull()) {
                return { ok: false, error: "tile (" + wantCol + "," + wantRow + ") pas dans le movable set" };
            }
        } else {
            tile = getUnitMainTile(unit, statePtr);
            if (tile.isNull()) return { ok: false, error: "current tile null" };
        }

        const before = summarize(statePtr);
        let dict: NativePointer;
        try { dict = invokeMethod(getAllPredMi.info, dpq, [unit, tile, abilBuf]); }
        catch (e) { return { ok: false, error: "GetAllPredictions threw: " + (e as Error).message }; }
        let dictCount = -1; let pred: Record<string, number> | null = null;
        let err: string | null = null;
        if (!dict.isNull()) {
            const dictClass = dict.readPointer();
            const getCountMi = findMethod(dictClass, "get_Count");
            if (getCountMi) {
                try { dictCount = invokeMethod(getCountMi.info, dict, null).add(0x10).readS32(); }
                catch { /* */ }
            }
            const getItemMi = findMethodByParamCount(dictClass, "get_Item", 1);
            if (getItemMi) {
                try {
                    const boxed = invokeMethod(getItemMi.info, dict, [target]);
                    if (!boxed.isNull()) {
                        // struct DamagePredictionResult @ boxed+0x10 (dump kqkbjqfb6c) :
                        // CurrentHealth@0 Armor@4 Shield@8 ;
                        // AccurateHealthDamage(MinMaxDamage)@0x58 (Min@0x60,Max@0x64) ;
                        // TotalDamage@0x88 (Min@0x90,Max@0x94) ;
                        // MightCrit@0xB1 ForceOverkill@0xB2 AppliedHits@0xBC.
                        const b = boxed.add(0x10);
                        pred = {
                            hpBefore: b.readS32(), armorBefore: b.add(0x4).readS32(),
                            shieldBefore: b.add(0x8).readS32(),
                            healthDmgMin: b.add(0x60).readS32(),
                            healthDmgMax: b.add(0x64).readS32(),
                            totalDmgMin: b.add(0x90).readS32(),
                            totalDmgMax: b.add(0x94).readS32(),
                            mightCrit: b.add(0xb1).readU8(),
                            appliedHits: b.add(0xbc).readS32(),
                        };
                    }
                } catch (e) { err = "get_Item: " + (e as Error).message; }
            } else { err = "get_Item not resolved"; }
        }
        const after = summarize(statePtr);
        return {
            ok: true, runner: label, dpqSrc,
            unitId: body?.unitId, targetId: body?.targetId,
            ability, abilityName: abilityName(ability), tile: readTileCoord(tile),
            dictNull: dict.isNull(), dictCount, pred,
            kill: pred ? (pred.healthDmgMax >= pred.hpBefore) : null,
            killSure: pred ? (pred.healthDmgMin >= pred.hpBefore) : null,
            mutated: before.sig !== after.sig, err,
        };
    });
}
