/** RPCs PREDICTION : aiPredict (preview decisionView, piege documente) +
 *  aiPlaybookPredict (oracle DIRECT du playbook per-ability, #102).
 *  Scinde de rpc-view.ts (2026-07-11, >2300 l. — seuil ~1000 l.) ; l'API RPC est
 *  INCHANGEE (memes noms ctx.rpc.*), agregee par registerView (rpc-view.ts). */
import {
    class_get_name, class_get_namespace, findClass, findClassAnywhere, findMethod,
    findMethodByParamClasses, findMethodByParamCount, getFieldOffset, readIl2cppString, s,
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
    entityExtClass, finishUnitTurnMsgClass, getMovableTilesMi, getTilesMi, getUnitMainTile,
    invokeBool, isAliveMi, isCtrlByCurMi, LIST_SIZE, moveUnitMsgClass, movementQueryOff,
    mowAbilityTypes, readTileCoord, resolveDpq, servicesOff, summarize, unitAbilityTypes,
    unitExtClass,
} from "./internals.js";
import { applyAiMsgMi } from "../../game/ai-control.js";
import {
    classFieldsDump, computeAttackPlans, computeDangerZone, computeExposure,
    projectMowsFull, projectUnitsFull,
} from "./projection.js";

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
     *  idempotent). body: { runnerId, unitId, targetId, abilityType, level?, multiplier? }
     *  (level/multiplier OVERRIDENT le capteur — pour tester une hypothèse de niveau). */
    ctx.rpc.aiPlaybookPredict = (
        body?: {
            runnerId?: number; unitId?: number; targetId?: number;
            abilityType?: number; level?: number; multiplier?: number;
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

        // 1. PlaybookDatabase : scan des champs pointeurs des racines candidates (match par nom).
        const classNameAt = (p: NativePointer): string | null => {
            try {
                const k = p.readPointer();
                if (k.isNull()) return null;
                return s(class_get_name(k) as NativePointer);
            } catch { return null; }
        };
        const scanForClass = (
            obj: NativePointer, want: string, maxOff: number,
        ): { p: NativePointer; off: number } | null => {
            if (obj.isNull()) return null;
            for (let off = 0x10; off < maxOff; off += 8) {
                try {
                    const p = obj.add(off).readPointer();
                    if (p.isNull()) continue;
                    if (classNameAt(p) === want) return { p, off };
                } catch { break; }
            }
            return null;
        };
        const aiControl = runner.add(runnerOff.aiControl).readPointer();
        const services = servicesOff >= 0 ? runner.add(servicesOff).readPointer() : ptr(0);
        const roots: Array<[string, NativePointer, number]> = [
            ["runner", runner, 0x300], ["aiControl", aiControl, 0x200],
            ["services", services, 0x200],
        ];
        let db: NativePointer = ptr(0); let dbSrc = "none";
        for (const [name, obj, max] of roots) {
            const hit = scanForClass(obj, "PlaybookDatabase", max);
            if (hit) { db = hit.p; dbSrc = name + "+0x" + hit.off.toString(16); break; }
        }
        // Fallback 2-niveaux : PlaybookDatabase peut vivre dans un objet intermédiaire (tactic/AI ctx).
        if (db.isNull() && !aiControl.isNull()) {
            for (let off = 0x10; off < 0x150 && db.isNull(); off += 8) {
                try {
                    const mid = aiControl.add(off).readPointer();
                    if (mid.isNull() || classNameAt(mid) === null) continue;
                    const hit = scanForClass(mid, "PlaybookDatabase", 0x150);
                    if (hit) {
                        db = hit.p;
                        dbSrc = "aiControl+0x" + off.toString(16) + "->+0x" + hit.off.toString(16);
                    }
                } catch { /* */ }
            }
        }
        if (db.isNull()) {
            return { ok: false, error: "PlaybookDatabase introuvable (scan runner/aiControl/"
                + "services 1-2 niveaux) — élargir le scan" };
        }

        // 2. LoadPlaybook — 3 registres PARALLÈLES par TYPE de clé (dump PlaybookDatabase 12101) :
        //    ActiveAbilityType  → LoadPlaybook(ability, bool fallbackToDefault) @1810e0090
        //                         (dicts _playbookBuilders@0x68/_loadedPlaybooks@0x70 ; fallback
        //                         _defaultPlaybookBuilder@0x80 = Func<ActiveAbilityType,IPlaybook>
        //                         → couvre l'attaque NORMALE et toute ability sans playbook bespoke)
        //    TriggeredAbilityType → @1810dfd10 (+0x88/+0x90) ; UnitSpecificBehaviourType → @1810dfed0
        //    (+0xa8/+0xb0 — PIÈGE mesuré : un findMethodByParamCount(1) aveugle matche CELUI-LÀ,
        //    1150 y résout UnbridledCarnagePlaybook). Désambiguïsation par TYPE du 1er param.
        const dbClass = db.readPointer();
        const loadMi = findMethodByParamClasses(dbClass, "LoadPlaybook", ["ActiveAbilityType", null]);
        if (!loadMi) {
            return { ok: false, error: "LoadPlaybook(ActiveAbilityType, bool) non résolu sur "
                + classNameAt(db) };
        }
        const abilBuf = Memory.alloc(4); abilBuf.writeS32(body.abilityType | 0);
        const fallbackBuf = Memory.alloc(1); fallbackBuf.writeU8(1);   // fallbackToDefault = true
        let playbook: NativePointer;
        try { playbook = invokeMethod(loadMi.info, db, [abilBuf, fallbackBuf]); }
        catch (e) { return { ok: false, error: "LoadPlaybook threw: " + (e as Error).message }; }
        if (playbook.isNull()) {
            return { ok: false, dbSrc, error: "pas de playbook pour ability " + body.abilityType };
        }
        const playbookClass = classNameAt(playbook);

        // Entités + tuile courante (+ map ptr→id pour résoudre le target des events).
        let unit = ptr(0); let target = ptr(0);
        const idByPtr = new Map<string, number>();
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit) return;
            idByPtr.set(e.toString(), id);
            if (id === body.unitId) unit = e;
            if (id === body.targetId) target = e;
        });
        if (unit.isNull()) return { ok: false, error: "unit " + body.unitId + " not found" };
        if (target.isNull()) return { ok: false, error: "target " + body.targetId + " not found" };
        const getUnitPosMi = entityExtClass
            ? findMethodByParamCount(entityExtClass, "GetUnitPosition", 2) : null;
        if (!getUnitPosMi) return { ok: false, error: "GetUnitPosition(2) non résolu" };
        let posPtr: NativePointer;
        try {
            const pos = invokeMethod(getUnitPosMi.info, null, [unit, statePtr]);
            if (pos.isNull()) return { ok: false, error: "GetUnitPosition null" };
            posPtr = pos.add(0x10);                       // struct UnitPosition (8o) déboxé
        } catch (e) { return { ok: false, error: "GetUnitPosition: " + (e as Error).message }; }

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
        const stateBuf = Memory.alloc(12);
        stateBuf.writeS32(lvl as number);
        stateBuf.add(4).writeS32((mult ?? 100) as number);
        stateBuf.add(8).writeS32(0);

        // 3. MakeDamagePredictions — override résolu sur la classe CONCRÈTE (walk parents),
        //    arité 4 (…, AbilityState*) d'abord (signature du slot +0x358), 3 en secours.
        const pbCls = playbook.readPointer();
        let makeMi = findMethodByParamCount(pbCls, "MakeDamagePredictions", 4);
        let makeArgs: NativePointer[] = [unit, posPtr, target, stateBuf];
        if (!makeMi) {
            makeMi = findMethodByParamCount(pbCls, "MakeDamagePredictions", 3);
            makeArgs = [unit, posPtr, target];
        }
        if (!makeMi) {
            return { ok: false, dbSrc, playbookClass,
                error: "MakeDamagePredictions(3|4) non résolu sur " + playbookClass };
        }
        const before = summarize(statePtr);
        let list: NativePointer;
        try { list = invokeMethod(makeMi.info, playbook, makeArgs); }
        catch (e) {
            return { ok: false, dbSrc, playbookClass,
                error: "MakeDamagePredictions threw: " + (e as Error).message };
        }
        // Lecture d'UN ProbableDamageEvent (struct 0xd8, ctor @181135500) à l'adresse `ev` :
        // +0x00 = référence IEntity cible (pointeur 8 o — un readS32 y lit du garbage) → résolue
        // en unitId via la map ; l'AttackHitPrediction copiée commence à +0x08.
        const readEvent = (ev: NativePointer): Record<string, unknown> => {
            const fx = (off: number): number =>
                ev.add(off).readS64().toNumber() / 4294967296;   // Fix64 Q32.32
            return {
                targetId: idByPtr.get(ev.readPointer().toString()) ?? null,
                hpBefore: ev.add(0x08).readS32(),
                armorBefore: ev.add(0x0c).readS32(),
                shieldBefore: ev.add(0x10).readS32(),
                healthDmgMin: ev.add(0x68).readS32(),
                healthDmgMax: ev.add(0x6c).readS32(),
                totalDmgMin: ev.add(0x98).readS32(),
                totalDmgMax: ev.add(0x9c).readS32(),
                mightCrit: ev.add(0xb9).readU8(),
                appliedHits: ev.add(0xc4).readS32(),
                probability: fx(0xc8), probMult: fx(0xd0),
            };
        };
        const events: Array<Record<string, unknown>> = [];
        let count = -1;
        let retClass: string | null = null;
        if (!list.isNull()) {
            retClass = classNameAt(list);
            try {
                const STRIDE = 0xd8;                       // sizeof(ProbableDamageEvent)
                if (retClass === "List`1") {
                    // Retour CONCRET List<ProbableDamageEvent> (ex. PlasmaCannonPlaybook @181150b10).
                    const items = list.add(0x10).readPointer();
                    count = list.add(0x18).readS32();
                    if (!items.isNull() && count > 0 && count < 64) {
                        for (let i = 0; i < count; i++) {
                            events.push(readEvent(items.add(0x20 + i * STRIDE)));
                        }
                    }
                } else if (retClass !== null && retClass.endsWith("[]")) {
                    // Retour ARRAY managé ProbableDamageEvent[] (ex. Loki_NormalAttackPlaybook) :
                    // max_length @+0x18, éléments value-type INLINE dès +0x20.
                    count = list.add(0x18).readS32();
                    if (count > 0 && count < 64) {
                        for (let i = 0; i < count; i++) {
                            events.push(readEvent(list.add(0x20 + i * STRIDE)));
                        }
                    }
                } else {
                    // Retour YIELD (machine d'état `<MakeDamagePredictions>d__N`, ex.
                    // NormalAttackPlaybook<T> @18149eeb0) : IEnumerable ET IEnumerator. On mirror
                    // GetEnumerator (state -2 → 0, retourne this) en posant `<>1__state` = 0, puis
                    // MoveNext() + lecture du struct INLINE `<>2__current` (offsets par NOM).
                    const iterCls = list.readPointer();
                    const stateOff = getFieldOffset(iterCls, "<>1__state");
                    const curOff = getFieldOffset(iterCls, "<>2__current");
                    const moveMi = findMethodByParamCount(iterCls, "MoveNext", 0);
                    if (stateOff < 0 || curOff < 0 || !moveMi) {
                        return { ok: false, dbSrc, playbookClass, retClass,
                            error: "retour ni List`1 ni yield-machine décodable (" + retClass + ")" };
                    }
                    list.add(stateOff).writeS32(0);        // GetEnumerator: -2 (as-enumerable) → 0
                    count = 0;
                    for (let i = 0; i < 64; i++) {
                        const more = invokeMethod(moveMi.info, list, null);
                        if (more.isNull() || more.add(0x10).readU8() === 0) break;
                        events.push(readEvent(list.add(curOff)));
                        count++;
                    }
                }
            } catch (e) {
                return { ok: false, dbSrc, playbookClass, retClass, count,
                    error: "lecture events: " + (e as Error).message };
            }
        }
        const after = summarize(statePtr);
        return {
            ok: true, runner: label, dbSrc, playbookClass, retClass,
            makeArity: makeArgs.length,
            unitId: body.unitId, targetId: body.targetId,
            ability: body.abilityType, abilityName: abilityName(body.abilityType),
            abilityState: { level: lvl, multiplier: mult, source: stSrc },
            listNull: list.isNull(), count, events,
            mutated: before.sig !== after.sig,
        };
    });
}
