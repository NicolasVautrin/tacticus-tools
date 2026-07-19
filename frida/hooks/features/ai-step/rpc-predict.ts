/** RPCs PREDICTION : aiPredict (preview decisionView, piege documente) +
 *  aiPlaybookPredict (oracle DIRECT du playbook per-ability, #102).
 *  Scinde de rpc-view.ts (2026-07-11, >2300 l. — seuil ~1000 l.) ; l'API RPC est
 *  INCHANGEE (memes noms ctx.rpc.*), agregee par registerView (rpc-view.ts). */
import {
    class_get_name, class_get_namespace, findClass, findClassAnywhere, findMethod,
    findMethodByParamCount, readIl2cppString, s,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import { runnerClass, runnerOff } from "../../game/runner.js";
import { getRunner } from "../../game/runner-registry.js";
import { setTraceOrigin } from "../../game/trace-origin.js";
import {
    EntityType, forEachComponent, forEachEntity, projectMatchState,
    readBattleStatus, unitFootComponentClass,
} from "../../game/match-state.js";
import {
    readEffectsByUnit, readEffectsByTile, readRoundCapClock, readEffectAbilityStateRaw,
} from "../../game/effects.js";
import { state } from "../../game/state.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { abilityName } from "../../data/ability-names.js";
import { TARGETING_RULE_BITS } from "../../data/targeting-rule-names.js";
import { Ctx } from "../../controller.js";
import {
    ActionResult, ActionSpec, activeAbilityMsgClass, applyOneAction,
    attackQueryOff, battleInServicesOff, dpqInServicesOff, entityServicesClass,
    extractTiles, extractTilePtrs,
    finishUnitTurnMsgClass, getMovableTilesMi, getTilesMi, getUnitMainTile,
    invokeBool, isAliveMi, isCtrlByCurMi, LIST_SIZE, moveUnitMsgClass, movementQueryOff,
    mowAbilityTypes, readTileCoord, resolveDpq, servicesOff, summarize, unitAbilityTypes,
    unitExtClass,
} from "./internals.js";
import { applyAiMsgMi } from "../../game/ai-control.js";
import {
    classFieldsDump, computeAttackPlans, computeDangerZone, computeExposure,
    projectMowsFull, projectUnitsFull,
} from "./projection.js";
import {
    classNameAt, decodeDamageEvents, loadPlaybook, makeDamagePredictions,
    resolvePlaybookDatabase, unitPositionAtTile, unitPositionCurrent,
} from "./playbook-predict.js";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function registerViewPredict(ctx: Ctx): void {
    /** PROBE prédiction de dégâts : pour (unit, target) depuis une tile choisie
     *  (col,row ; défaut = tile courante), appelle
     *  `DamagePredictionQuery.GetAllPredictions(unit, selectedTile, ability)` →
     *  IDictionary<IEntity, DamagePredictionResult>, puis `dict.get_Item(target)`
     *  → struct boxée lue à +0x10. Read-only. Valide la chaîne d'invoke avant
     *  d'intégrer la prédiction aux attackPlans.
     *
     *  ⚠⚠ PIÈGES DE MESURE (#96/#98, 2026-07-11) — À LIRE avant d'utiliser ce RPC comme ORACLE :
     *  1. `GetAllPredictions` = le PREVIEW decisionView (dégât Attack-based/normal), PAS le dégât
     *     per-ability du PLAYBOOK de décision (`<Ability>Playbook.MakeDamagePredictions`, ex.
     *     PlasmaCannon config-based maxDmg±20%). aiPredict(special) == aiPredict(normale) ne prouve
     *     RIEN sur le playbook (faux verdict #96). Oracle playbook = dumps per-bout modifier-observe
     *     (GetBaseDamageWithFixedPiercedArmor) captés PENDANT le tour de décision IA.
     *  2. L'instance résolue par défaut = `CachedDamagePredictionQuery @180e2d990` (clé
     *     {unitId, tileId, abilityType} — l'ability EST dans la clé) : une valeur peut être STALE
     *     (état antérieur du tour). `fresh: true` court-circuite le cache (query interne @+0x10).
     *  3. Tuile d'attaque INVALIDE (ex. mêlée non adjacente) → le natif sert le fallback
     *     `GetPredictionForTargetsUnreachableFromSelectionTile @1810935c0` (prédiction depuis une
     *     autre tuile) — ne PAS interpréter comme la prédiction de cette tuile.
     *  body: { runnerId, unitId, targetId, abilityType?, col?, row?, fresh? } */
    ctx.rpc.aiPredict = (
        body?: {
            runnerId?: number; unitId?: number; targetId?: number;
            abilityType?: number; col?: number; row?: number; fresh?: boolean;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
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
        let queryClass: string | null = null;
        try { queryClass = s(class_get_name(dpq.readPointer()) as NativePointer); } catch { /* */ }
        // `fresh: true` : bypass du cache — l'instance par défaut est `CachedDamagePredictionQuery`
        // (clé {unit,tile,ability}, valeurs potentiellement STALE) ; sa query INTERNE (le vrai
        // `DamagePredictionQuery`) est le champ @+0x10 (décompilé @180e2d990 : `plVar1 = *(this+0x10)`,
        // dispatché sur cache-miss). On invoque directement l'interne → recompute garanti.
        if (body?.fresh && queryClass && queryClass.indexOf("Cached") >= 0) {
            try {
                const inner = dpq.add(0x10).readPointer();
                if (!inner.isNull()) {
                    const mi = findMethodByParamCount(inner.readPointer(), "GetAllPredictions", 3);
                    if (mi) {
                        dpq = inner; getAllPredMi = mi; dpqSrc += "->inner(fresh)";
                        try { queryClass = s(class_get_name(inner.readPointer()) as NativePointer); }
                        catch { /* */ }
                    }
                }
            } catch { /* fallback : instance cachée */ }
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
            ok: true, runner: label, dpqSrc, queryClass,
            unitId: body?.unitId, targetId: body?.targetId,
            ability, abilityName: abilityName(ability), tile: readTileCoord(tile),
            dictNull: dict.isNull(), dictCount, pred,
            kill: pred ? (pred.healthDmgMax >= pred.hpBefore) : null,
            killSure: pred ? (pred.healthDmgMin >= pred.hpBefore) : null,
            mutated: before.sig !== after.sig, err,
        };
    });

    /** aiPlaybookPredict — ORACLE DIRECT du dégât per-ability du PLAYBOOK (#102). Invoque le
     *  `<Ability>Playbook.MakeDamagePredictions` NATIF — ce que `aiPredict` N'est PAS
     *  (GetAllPredictions = preview decisionView Attack-based, cf. pièges docs sur aiPredict).
     *  Chaîne native mirrorée (RE #102) :
     *   1. `PlaybookDatabase.LoadPlaybook(ActiveAbilityType, bool fallbackToDefault)` @1810e0090 —
     *      registry _playbookBuilders@+0x68 / _loadedPlaybooks@+0x70, fallback
     *      _defaultPlaybookBuilder@+0x80 (couvre l'attaque normale ; ctor @1810e0380). ⚠ 2 autres
     *      overloads homonymes à AUTRE key-space (Triggered@1810dfd10, UnitSpecificBehaviour
     *      @1810dfed0) → désambiguïser par TYPE de param. L'INSTANCE PlaybookDatabase est posée par
     *      `IdunRunner.Initialize @180e35400` (offset non porté) → résolue par SCAN des champs
     *      pointeurs (runner, puis aiControl, puis EntityServices), match par nom de classe.
     *      Résolution par NOM (aucun RVA).
     *   2. `playbook.MakeDamagePredictions(caster, UnitPosition, target[, AbilityState*])` —
     *      slot vtable +0x358 chez le scorer (`CalculateUtilityFromPredictions @181407890`,
     *      overrides ex. PlasmaCannonPlaybook @181150b10, ALoki_NormalAttackPlaybook @181372730).
     *      Le playbook monte son AbilityEntities en INTERNE (ability à playbook+0x68) — on ne
     *      fabrique PAS le struct 34-params. `UnitPosition` = struct 8o {IList Tiles} via
     *      `UnitExtensions.GetUnitPosition(unit, state)` (tuile COURANTE — la prédiction depuis
     *      une tuile candidate n'est pas portée en v1 : bouger l'unité pour tester une position).
     *      `AbilityState` {level@0, mult@4, 0@8} = l'entrée ActiveAbility de l'unité (capteur
     *      #100, _abilityState@0x4c) — le 5e arg que CalculateUtilityFromPredictions forwarde.
     *   3. Retour `List<ProbableDamageEvent>` (array de structs 0xd8, ctor @181135500) :
     *      target(BEntityId)@+0x00 ; copie AttackHitPrediction@+0x08 (hp@+0x08, armor@+0x0c,
     *      shield@+0x10, healthDmgMin@+0x68, healthDmgMax@+0x6c, totalDmg@+0x98/+0x9c,
     *      mightCrit@+0xb9, appliedHits@+0xc4) ; probability(Fix64)@+0xc8 ; probMult(Fix64)@+0xd0.
     *  ⚠ Certains playbooks (heal/repair) rendent des Probable{Heal,Effect}Event (@181135820/
     *  @1811359a0) — stride/champs DIFFÉRENTS : ce RPC ne décode que les DamageEvent (gate par
     *  taille de struct non porté ; l'appelant passe une ability d'ATTAQUE). Read-only visé
     *  (summarize avant/après → mutated ; PredictAttack peut lazy-init des caches widget,
     *  idempotent). body: { runnerId, unitId, targetId, abilityType, level?, multiplier?,
     *  col?, row? } (level/multiplier OVERRIDENT le capteur — pour tester une hypothèse de
     *  niveau ; col/row = TUILE CANDIDATE de cast → UnitPosition via `GetUnitPositionAtTile
     *  @180eb6dc0`, exactement ce que le sweep de DÉCISION natif évalue — la tuile doit être
     *  la courante ou dans le movable set, résolution mirror d'aiPredict ; absent = tuile
     *  courante. Confrontation par-étage Étape 1 : prédire depuis la tuile d'attaque CHOISIE
     *  élimine le faux 0 « hors de portée depuis la tuile courante » des chunks composés). */
    ctx.rpc.aiPlaybookPredict = (
        body?: {
            runnerId?: number; unitId?: number; targetId?: number;
            abilityType?: number; level?: number; multiplier?: number;
            col?: number; row?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.unitId !== "number" || typeof body?.targetId !== "number"
            || typeof body?.abilityType !== "number") {
            return { ok: false, error: "need unitId + targetId + abilityType" };
        }
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) { runner = state.liveRunner; label = "live"; }
        else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, error: "stage " + (status.stageName ?? status.stage) };
        }

        // 1. PlaybookDatabase (scan par nom, aucun RVA — cf. playbook-predict.ts).
        const dbHit = resolvePlaybookDatabase(runner);
        if (!dbHit) {
            return { ok: false, error: "PlaybookDatabase introuvable (scan runner/aiControl/"
                + "services 1-2 niveaux) — élargir le scan" };
        }
        const { db, dbSrc } = dbHit;

        // 2. LoadPlaybook(ActiveAbilityType, fallbackToDefault=true) — désambiguïse les 3
        //    overloads homonymes par TYPE de param (cf. playbook-predict.ts).
        const playbook = loadPlaybook(db, body.abilityType);
        if (playbook.isNull()) {
            return { ok: false, dbSrc,
                error: "pas de playbook pour ability " + body.abilityType
                    + " (LoadPlaybook non résolu / null)" };
        }
        const playbookClass = classNameAt(playbook);

        // Entités + tuile courante (+ map ptr→id pour résoudre le target des events).
        // Le CASTER peut être une UNITÉ ou une MACHINE OF WAR (MoW off-board, #172) : les 2 playbooks
        // MoW (DaemonicOrdnance 1148 / HadesAutocannons 1147) sont dans la MÊME PlaybookDatabase que
        // les units (RE #172, InitializePlaybookBuilders b__31_150/149) et le scorer slot +0x358 est
        // GÉNÉRIQUE (aucun test EntityType) → LoadPlaybook + MakeDamagePredictions marchent tels quels ;
        // il suffit d'accepter EntityType.Machine pour résoudre le caster. Les CIBLES restent des unités.
        let unit = ptr(0); let target = ptr(0); let casterIsMachine = false;
        const idByPtr = new Map<string, number>();
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty === EntityType.Unit || ty === EntityType.Machine) {
                idByPtr.set(e.toString(), id);
                if (id === body.unitId) { unit = e; casterIsMachine = ty === EntityType.Machine; }
            }
            if (ty === EntityType.Unit && id === body.targetId) target = e;
        });
        if (unit.isNull()) {
            return { ok: false, error: "unit " + body.unitId + " not found (unit/machine)" };
        }
        if (target.isNull()) return { ok: false, error: "target " + body.targetId + " not found" };
        // UnitPosition (point de calcul). Pour une UNITÉ = sa tuile courante. Pour un MoW (off-board),
        // GetUnitPosition rend une UnitPosition VIDE (Tiles=[]) → le bombard `GetTargetAreaTiles` part
        // de rien → 0 cible. Le bombard MoW s'AIME sur une tuile : pour la confrontation on passe la
        // UnitPosition de la CIBLE comme point de visée (le selector monte la zone autour). (RE #172)
        let posPtr = casterIsMachine
            ? unitPositionCurrent(target, statePtr)
            : unitPositionCurrent(unit, statePtr);
        if (!posPtr) posPtr = unitPositionCurrent(unit, statePtr);
        // Tuile CANDIDATE (col,row) : UnitPosition à cette tuile (GetUnitPositionAtTile),
        // résolution mirror d'aiPredict (movable set via GetMovableTilesFor(3), sinon la
        // tuile courante). Unités seulement (le MoW off-board garde la visée sur la cible).
        let posSrc = "current";
        const wantCol = body?.col; const wantRow = body?.row;
        if (!casterIsMachine && typeof wantCol === "number" && typeof wantRow === "number") {
            let tile = ptr(0);
            if (getMovableTilesMi) {
                const movementQuery = runner.add(movementQueryOff).readPointer();
                const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
                const optsZero = Memory.alloc(0x30);
                for (let k = 0; k < 0x30; k += 4) optsZero.add(k).writeU32(0);
                try {
                    const os = invokeMethod(getMovableTilesMi.info, movementQuery,
                        [unit, boolFalse, optsZero]);
                    for (const t of extractTilePtrs(os)) {
                        if (t.col === wantCol && t.row === wantRow) { tile = t.ptr; break; }
                    }
                } catch { /* fallback tuile courante ci-dessous */ }
            }
            if (tile.isNull()) {
                const mt = getUnitMainTile(unit, statePtr);
                if (!mt.isNull()) {
                    const c = readTileCoord(mt);
                    if (c.col === wantCol && c.row === wantRow) tile = mt;
                }
            }
            if (tile.isNull()) {
                return { ok: false, error: "tile (" + wantCol + "," + wantRow
                    + ") ni courante ni dans le movable set" };
            }
            const atTile = unitPositionAtTile(unit, tile, statePtr);
            if (!atTile) return { ok: false, error: "GetUnitPositionAtTile null" };
            posPtr = atTile; posSrc = "tile(" + wantCol + "," + wantRow + ")";
        }
        if (!posPtr) return { ok: false, error: "GetUnitPosition null (caster/cible)" };

        // AbilityState per-ability : override body > capteur #100 > défaut flaggé.
        let lvl = body.level; let mult = body.multiplier; let stSrc = "body";
        if (typeof lvl !== "number" || typeof mult !== "number") {
            const info = unitAbilityTypes(unit, true).find((a) => a.id === body.abilityType);
            if (info && typeof info.level === "number") {
                lvl = info.level; mult = info.multiplier ?? 100; stSrc = "capteur";
            } else if (typeof lvl !== "number") {
                lvl = 0; mult = mult ?? 100; stSrc = "default(0,100) — entrée ActiveAbility absente";
            }
        }
        // 3. MakeDamagePredictions (tuile courante) + décodage List/array/yield — cf.
        //    playbook-predict.ts (helper partagé avec l'affichage decisionView).
        const before = summarize(statePtr);
        const mk = makeDamagePredictions(
            playbook, unit, posPtr, target, lvl as number, (mult ?? 100) as number);
        const dec = decodeDamageEvents(mk.list, idByPtr);
        const after = summarize(statePtr);
        if (dec.error) {
            return { ok: false, dbSrc, playbookClass, retClass: mk.retClass,
                count: dec.count, error: dec.error };
        }
        return {
            ok: true, runner: label, dbSrc, playbookClass, retClass: mk.retClass,
            makeArity: mk.makeArity, posSrc,
            unitId: body.unitId, targetId: body.targetId,
            ability: body.abilityType, abilityName: abilityName(body.abilityType),
            abilityState: { level: lvl, multiplier: mult, source: stSrc },
            listNull: mk.list.isNull(), count: dec.count, events: dec.events,
            mutated: before.sig !== after.sig,
        };
    });
}
