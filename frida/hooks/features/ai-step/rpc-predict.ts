/** RPCs PREDICTION : aiPredict (preview decisionView, piege documente) +
 *  aiPlaybookPredict (oracle DIRECT du playbook per-ability, #102).
 *  Scinde de rpc-view.ts (2026-07-11, >2300 l. — seuil ~1000 l.) ; l'API RPC est
 *  INCHANGEE (memes noms ctx.rpc.*), agregee par registerView (rpc-view.ts). */
import {
    class_get_name, class_get_namespace, findClass, findClassAnywhere, findMethod,
    findMethodByParamCount, method_get_name, method_get_param_count,
    readIl2cppString, s,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
// #988 — le décodeur d'arbre de bucket : `best` seul ne voit pas la voie à stratégies multiples.
import { chooseAction, countActions, decodeBucket } from "../../ai-toolkit/bucket-decode.js";
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
import {
    DamagePredictionFields, predictionLayoutError, readDamagePredictionResult,
} from "../../game/damage-prediction.js";
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
    classNameAt, decodeDamageEvents, decodeEffectEvents, decodeHealEvents,
    decodeRepairDict, loadPlaybook, makeDamagePredictions, nullUnitPosition,
    resolvePlaybookDatabase, unitPositionAtTile, unitPositionCurrent,
} from "./playbook-predict.js";
import { withWillBeKillProbe } from "./playbook-gate-probe.js";
import { withMovableTilesProbe, type MovableTilesProbe } from "./movable-tiles-probe.js";

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
        let dictCount = -1; let pred: DamagePredictionFields | null = null;
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
                        // `IdunBattle.Core.Services.DamagePredictionResult` BOXÉ :
                        // les champs commencent à `boxed+0x10` (header IL2CPP). Tous
                        // les offsets vivent dans `game/damage-prediction.ts` — un
                        // seul décodeur, une seule garde de layout (#276/#268).
                        pred = readDamagePredictionResult(boxed.add(0x10));
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
            // Deux formules HISTORIQUES, conservées telles quelles : elles portent sur
            // `AccurateHealthDamage@0x40` (le dégât santé CAPÉ), PAS sur les bornes que
            // lisent les getters natifs. Ce ne sont donc PAS `get_MightBeKill` /
            // `get_WillBeKill` — ne pas les confondre avec les deux champs ci-dessous.
            kill: pred ? (pred.healthDmgMax >= pred.hpBefore) : null,
            killSure: pred ? (pred.healthDmgMin >= pred.hpBefore) : null,
            // Mirror EXACT des deux getters natifs. #372 : ces deux champs REJOUAIENT la
            // comparaison ici (`hpBefore <= willKillDmg`), donc SANS le gate
            // `CannotBeGuaranteedKilled@0x89` ni la préférence pour `BlockScenarios[0]+0x0c`
            // — un mirror qui se disait « EXACT » et ne l'était pas. Ils lisent maintenant le
            // verdict calculé par le décodeur, foyer unique. `willBeKill` est TRI-ÉTAT :
            // `null` = une entrée n'a pas pu être mesurée (cf. `blockScenarioCount`).
            mightBeKill: pred ? pred.mightBeKill : null,
            willBeKill: pred ? pred.willBeKill : null,
            // #276 — non nul dès que la garde de layout échoue : le décodeur ne
            // décode plus ce build, `pred` n'est PAS une mesure.
            layoutError: predictionLayoutError(),
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
     *   3. Retour `List<ProbableDamageEvent>` (structs de 0xb8, `IdunBattle.AI.Playbook
     *      .ProbableDamageEvent$$.ctor`) : `IEntity Target`@+0x00 (un POINTEUR, pas un id),
     *      copie intégrale du `DamagePredictionResult`@+0x08, `Fix64 Probability`@+0xa8,
     *      `Fix64 Weight`@+0xb0. Le décodage des champs vit dans
     *      `game/damage-prediction.ts` (#276) — plus aucun offset ici.
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
            /** #361 — arme le capteur de gate `WillBeKill` LE TEMPS de cette invocation
             *  (`playbook-gate-probe.ts`). Absent/false = aucun hook posé. */
            gateProbe?: boolean;
            /** #370 — arme le capteur du MAILLON INTERNE de `GetTileToMoveTo`
             *  (`movable-tiles-probe.ts` : `MovableTilesInRangeSelector$$Select` +
             *  `CasterSelector$$Select` + `CasterTileSelector$$Select`), LE TEMPS de cette
             *  invocation. Absent/false = aucun hook posé. Composable avec `gateProbe`. */
            tileProbe?: boolean;
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
        // UnitPosition (point de calcul). Pour une UNITÉ = sa tuile courante. Pour une MACHINE OF
        // WAR = `UnitPosition$$NullPosition()` — ce que passe littéralement
        // `DefaultMachineTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext` (cf.
        // `nullUnitPosition`), c.-à-d. une position dont la liste de tuiles est VIDE.
        //
        // ⚠ #360 — CE CHEMIN SUBSTITUAIT LA `UnitPosition` DE LA **CIBLE**, et c'est ce qui fermait
        // l'oracle MoW. Aucun antécédent natif : le tactic Machine ne vise pas la cible, il passe
        // NullPosition. Mesuré sur `blackForgefiend` / `1147 HadesAutocannons`, un summon en jeu :
        // avec la position de la cible `MakeDamagePredictions` LÈVE (`count = -1`, `listNull = true`,
        // l'exception étant avalée par `makeDamagePredictions`) ; avec NullPosition la MÊME invocation
        // rend `(324, 492, 6)`. La cause est lisible dans
        // `Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetEntitiesFromSelector`, qui pose
        // `ctx.<+0xc0> = UnitPosition$$get_MainTile(casterPosition)` : donner la tuile de la cible
        // fait évaluer le sélecteur depuis un point de vue qui n'existe pas.
        let posSrc = casterIsMachine ? "machine:NullPosition" : "current";
        let posPtr = casterIsMachine ? nullUnitPosition() : unitPositionCurrent(unit, statePtr);
        if (!posPtr && casterIsMachine) {
            // Repli : `GetUnitPosition(machine)` = `GetTiles(machine)` rend elle aussi une liste
            // VIDE (une Machine n'a pas de tuile) — même valeur, résolution différente.
            posPtr = unitPositionCurrent(unit, statePtr);
            posSrc = "machine:GetUnitPosition(empty)";
        }
        // Tuile CANDIDATE (col,row) : UnitPosition à cette tuile (GetUnitPositionAtTile),
        // résolution mirror d'aiPredict (movable set via GetMovableTilesFor(3), sinon la
        // tuile courante). Unités seulement (une MoW n'a pas de tuile candidate — son tactic
        // passe `new OrderedSet()`, l'ensemble VIDE).
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
        //    #34 : invoque AUSSI les siblings MakeHealPredictions / MakeEffectPredictions
        //    (mêmes args ; base = enumerable VIDE si le playbook n'override pas) →
        //    healEvents/effectEvents — l'oracle couvre les abilities heal/buff
        //    (ex. 1113 Stormcaller, 1121 ItItches, 1151 TheQuickening, 1163 BlackRage).
        //    Erreur d'une famille = champ *Error (ne fail pas le RPC ; le gate reste damage).
        const before = summarize(statePtr);
        // #361 — `gateProbe: true` arme le capteur de GATE le TEMPS de cette invocation
        // (cf. `playbook-gate-probe.ts` : pourquoi ce point d'ancrage, et les trois issues).
        // Hors flag, aucun hook n'est posé : `get_WillBeKill` est appelé par l'UI à chaque
        // frame, on ne le taxe jamais par défaut.
        //
        // #370 — `tileProbe: true` arme, DANS LA MÊME invocation, le capteur du maillon interne
        // de `GetTileToMoveTo` (cf. `movable-tiles-probe.ts`). Les deux capteurs sont
        // COMPOSABLES : le gate encadre le tile, qui encadre l'invocation native.
        const runMake = () => makeDamagePredictions(
            playbook, unit, posPtr, target, lvl as number, (mult ?? 100) as number);
        let tileProbe: MovableTilesProbe | null = null;
        const inner = () => {
            if (body.tileProbe !== true) return runMake();
            const t = withMovableTilesProbe(runMake);
            tileProbe = t.probe;
            return t.result;
        };
        const gate = body.gateProbe === true ? withWillBeKillProbe(inner) : null;
        const mk = gate !== null ? gate.result : inner();
        const dec = decodeDamageEvents(mk.list, idByPtr);
        const mkHeal = makeDamagePredictions(
            playbook, unit, posPtr, target, lvl as number, (mult ?? 100) as number,
            "MakeHealPredictions");
        const decHeal = decodeHealEvents(mkHeal.list, idByPtr);
        const mkEff = makeDamagePredictions(
            playbook, unit, posPtr, target, lvl as number, (mult ?? 100) as number,
            "MakeEffectPredictions");
        const decEff = decodeEffectEvents(mkEff.list, idByPtr);
        // #45 : 4e famille du scorer (`CalculateUtilityFromPredictions @181407890`,
        // virtuel +0x388) — Dictionary, pas d'event (décodage v2 decodeRepairDict).
        const mkRep = makeDamagePredictions(
            playbook, unit, posPtr, target, lvl as number, (mult ?? 100) as number,
            "MakeRepairPredictions");
        const decRep = decodeRepairDict(mkRep.list, idByPtr);
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
            healCount: decHeal.count, healEvents: decHeal.events,
            healRetClass: mkHeal.retClass, healError: decHeal.error ?? null,
            effectCount: decEff.count, effectEvents: decEff.events,
            effectRetClass: mkEff.retClass, effectError: decEff.error ?? null,
            repairCount: decRep.count, repairs: decRep.events,
            repairRetClass: decRep.retClass, repairError: decRep.error ?? null,
            // #361 — TRI-ÉTAT : `null` = capteur non demandé (`gateProbe` absent) ; un objet dont
            // `calls` vaut `null` = demandé mais NON ARMÉ (maillon non résolu, `error` le dit) ;
            // `calls: []` = armé et AUCUN appel — ce qui est en soi un verdict.
            gateProbe: gate !== null ? gate.probe : null,
            // #370 — MÊME tri-état : `null` = capteur non demandé (`tileProbe` absent) ; un objet
            // dont `nodes` vaut `null` = demandé mais NON ARMÉ (`nodesError` nomme le maillon) ;
            // `nodes: []` = armé et AUCUN appel — l'arbre `GetTileToMoveTo` n'est pas évalué.
            tileProbe,
            mutated: before.sig !== after.sig,
        };
    });

    /** #45 — UTILITÉ DE PAIRE NATIVE : invoque le scoreur COMPARABLE
     *  `ComparablePlaybook.CalculateUtilityFromPredictions @181407890` (4 params :
     *  unit, UnitPosition, target, Nullable<AbilityState>) sur le playbook
     *  `LoadPlaybook(ability)` → la valeur EXACTE que le bucket natif attribue à la
     *  paire (ability, cible) depuis une position : Σ des 4 familles damage/heal/
     *  effect/repair (probabilités et modificateurs inclus), en Fix64. Voie DIRECTE :
     *  le wrapper `Evaluate` (ncEvaluate) AV @0x46 sur les playbooks comparables
     *  invoqués hors du tour de décision natif — le scoreur, lui, ne dépend que du
     *  playbook chargé (UtilitiesDatabase à playbook+0x40) et des mêmes args que
     *  Make*Predictions (déjà validés par aiPlaybookPredict). Résolution par NOM,
     *  aucun RVA. Retour Fix64 boxé → valeur à +0x10 (Q32.32).
     *  body: { runnerId?, unitId, targetId, abilityType, level?, multiplier?,
     *  col?, row? } (mêmes conventions qu'aiPlaybookPredict, tuile candidate incl.) */
    ctx.rpc.pairUtility = (
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
        const dbHit = resolvePlaybookDatabase(runner);
        if (!dbHit) return { ok: false, error: "PlaybookDatabase introuvable" };
        const playbook = loadPlaybook(dbHit.db, body.abilityType);
        if (playbook.isNull()) {
            return { ok: false, error: "pas de playbook pour ability " + body.abilityType };
        }
        const playbookClass = classNameAt(playbook);
        const scoreMi = findMethodByParamCount(
            playbook.readPointer(), "CalculateUtilityFromPredictions", 4);
        if (!scoreMi) {
            return { ok: false, playbookClass,
                error: "CalculateUtilityFromPredictions(4) introuvable" };
        }
        // #302-t5 — LA CIBLE N'EST PAS TYPÉE côté natif. `CalculateUtilityFromPredictions(unit,
        // UnitPosition, target, Nullable<AbilityState>)` prend un `IEntity`, exactement comme
        // `IdunBattle.AI.ActionGenerators.UnitAction$$.ctor(position, target, abilityType)`.
        // Ce RPC, lui, n'acceptait que `EntityType.Unit` -> toute ability à cibles TUILE
        // (bit `TargetIsTile`, cf. `IdunBattle.Core.Services.TargetingOptions$$get_IsTileTargeting`)
        // renvoyait « target N not found », et l'oracle par étage était INVALIDABLE sur ces
        // 19 abilities du registre — dont `1169 PlagueburstMortar` et `1148 DaemonicOrdnance`,
        // portées par #302. Le filtre était donc une limite du HARNAIS, pas du jeu.
        //
        // On résout donc la cible par ID sur TOUS les types d'entité, et on PUBLIE le type
        // retenu (`targetEntityType`) : un consommateur qui croyait viser une unité et reçoit
        // une tuile doit pouvoir le voir, plutôt que de le découvrir dans un chiffre faux.
        // Départage déterministe si deux entités portaient le même id : `Unit` gagne.
        let unit = ptr(0); let target = ptr(0);
        let casterIsMachine = false;
        let targetType: number | null = null;
        const idTypesSeen: number[] = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty === EntityType.Unit || ty === EntityType.Machine) {
                if (id === body.unitId) { unit = e; casterIsMachine = ty === EntityType.Machine; }
            }
            if (id === body.targetId) {
                idTypesSeen.push(ty);
                if (target.isNull() || ty === EntityType.Unit) { target = e; targetType = ty; }
            }
        });
        if (unit.isNull()) return { ok: false, error: "unit " + body.unitId + " not found" };
        if (target.isNull()) return { ok: false, error: "target " + body.targetId + " not found" };
        // UnitPosition : tuile courante, ou tuile CANDIDATE (col,row) du movable set
        // (mirror aiPlaybookPredict). Caster MACHINE → `NullPosition()`, ce que passe le tactic
        // natif (#360) : les TROIS oracles (aiPlaybookPredict / pairUtility / ncPlaybookPredict)
        // doivent partir de la MÊME position, sans quoi ils scorent des scènes différentes.
        let posSrc = casterIsMachine ? "machine:NullPosition" : "current";
        let posPtr = casterIsMachine ? nullUnitPosition() : unitPositionCurrent(unit, statePtr);
        if (!posPtr && casterIsMachine) {
            posPtr = unitPositionCurrent(unit, statePtr);
            posSrc = "machine:GetUnitPosition(empty)";
        }
        if (typeof body?.col === "number" && typeof body?.row === "number") {
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
                        if (t.col === body.col && t.row === body.row) { tile = t.ptr; break; }
                    }
                } catch { /* fallback courante */ }
            }
            if (tile.isNull()) {
                const mt = getUnitMainTile(unit, statePtr);
                if (!mt.isNull()) {
                    const c = readTileCoord(mt);
                    if (c.col === body.col && c.row === body.row) tile = mt;
                }
            }
            if (tile.isNull()) {
                return { ok: false, error: "tile (" + body.col + "," + body.row
                    + ") ni courante ni dans le movable set" };
            }
            const atTile = unitPositionAtTile(unit, tile, statePtr);
            if (!atTile) return { ok: false, error: "GetUnitPositionAtTile null" };
            posPtr = atTile; posSrc = "tile(" + body.col + "," + body.row + ")";
        }
        if (!posPtr) return { ok: false, error: "GetUnitPosition null" };
        // AbilityState : override body > capteur #100 > défaut flaggé (mirror aiPlaybookPredict).
        let lvl = body.level; let mult = body.multiplier; let stSrc = "body";
        if (typeof lvl !== "number" || typeof mult !== "number") {
            const info = unitAbilityTypes(unit, true).find((a) => a.id === body.abilityType);
            if (info && typeof info.level === "number") {
                lvl = info.level; mult = info.multiplier ?? 100; stSrc = "capteur";
            } else if (typeof lvl !== "number") {
                lvl = 0; mult = mult ?? 100; stSrc = "default(0,100)";
            }
        }
        const stateBuf = Memory.alloc(12);
        stateBuf.writeS32((lvl as number) | 0);
        stateBuf.add(4).writeS32(((mult ?? 100) as number) | 0);
        stateBuf.add(8).writeS32(0);
        const before = summarize(statePtr);
        let boxed: NativePointer;
        try {
            boxed = invokeMethod(scoreMi.info, playbook, [unit, posPtr, target, stateBuf]);
        } catch (e) {
            // #302-t5 — DIAGNOSTIC, mesuré le 2026-07-30 : passer une entité TUILE au playbook
            // d'une ability qui cible des UNITÉS fait jeter le natif (« system error ») au lieu
            // de refuser proprement. Avant le correctif de résolution, le RPC répondait
            // « target N not found » — opaque, mais au moins ça nommait le problème. On publie
            // donc le TYPE résolu dans le chemin d'erreur AUSSI : sans lui, l'appelant voit un
            // « system error » nu et n'a aucun moyen de savoir qu'il a confondu les domaines.
            return { ok: false, playbookClass, posSrc,
                targetEntityType: targetType,
                hint: targetType === EntityType.Tile
                    ? "cible de type Tile passée à `" + playbookClass + "` : ce playbook "
                        + "attend-il vraiment un domaine TUILE (bit `TargetIsTile`) ?"
                    : undefined,
                error: "CalculateUtilityFromPredictions threw: " + (e as Error).message };
        }
        const after = summarize(statePtr);
        const raw = boxed.isNull() ? null : boxed.add(0x10).readS64();
        return {
            ok: true, runner: label, playbookClass, posSrc,
            unitId: body.unitId, targetId: body.targetId,
            // #302-t5 : valeur de `EntityType` de la cible retenue (0 = Tile, 1 = Unit, …).
            // `targetIdTypesSeen` n'apparaît QUE s'il y a collision d'id entre deux types —
            // anormal, donc signalé plutôt que tu.
            targetEntityType: targetType,
            targetIdTypesSeen: idTypesSeen.length > 1 ? idTypesSeen : undefined,
            ability: body.abilityType, abilityName: abilityName(body.abilityType),
            abilityState: { level: lvl, multiplier: mult, source: stSrc },
            utility: raw === null ? null : raw.toNumber() / 4294967296,
            utilRaw: raw === null ? null : raw.toString(),
            mutated: before.sig !== after.sig,
        };
    });

    /** ORACLE NC (#46) : invoque la LEAF NATIVE `EvaluateNonComparable(unit, UnitPosition)`
     *  du playbook d'une ability, par POSITION (courante + sweep du movable set), et décode
     *  le Bucket rendu (best BucketAction : utilité Fix64 + UnitAction{position,target,ability}).
     *  Bisecte un désaccord de DÉCISION NC : bucket vide à une position ⇒ le déclin natif se
     *  joue DANS la leaf (éligibilité/gates internes) ; bucket plein partout ⇒ le drop est en
     *  AMONT (générateur : gates d'état, slot-6 per-position, HasValidTargets 0x3f, ChooseAction).
     *  On lit AUSSI `HasValidTargets(unit, pos, ability)` (BattleQuery, gate per-position du
     *  générateur `<GenerateActions>d__7 @18119a3f0`) pour croiser. Layouts décodés du
     *  décompilé (générateur finish-block) : Bucket.best@+0x20 ; BucketAction{action@+0x10,
     *  util Fix64@+0x18} ; UnitAction{position@+0x10, target BEntityId@+0x18, ability@+0x20}.
     *  Read-only (queries de prédiction). body: { runnerId?, unitId, abilityType,
     *  sweep? (défaut true = courante + toutes les tuiles de move), col?, row? } */
    ctx.rpc.ncEvaluate = (
        body?: {
            runnerId?: number; unitId?: number; abilityType?: number;
            sweep?: boolean; col?: number; row?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.unitId !== "number" || typeof body?.abilityType !== "number") {
            return { ok: false, error: "need unitId + abilityType" };
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
        const dbHit = resolvePlaybookDatabase(runner);
        if (!dbHit) return { ok: false, error: "PlaybookDatabase introuvable" };
        const playbook = loadPlaybook(dbHit.db, body.abilityType);
        if (playbook.isNull()) {
            return { ok: false, error: "pas de playbook pour ability " + body.abilityType };
        }
        const playbookClass = classNameAt(playbook);
        // Voie du GÉNÉRATEUR (`<GenerateActions>d__7 @18119a3f0`) : slot 7 = `Evaluate(unit,
        // UnitPosition, tiles)` (wrapper @18111df40 : AbilityState + DisallowRandom +
        // EvaluateInternal → EvaluateNonComparable). On invoque CE wrapper — appeler la leaf
        // nue crashe (AV 0x0 : l'AbilityState/contexte monté par le wrapper manque).
        let evalMi = null; let evalName = "";
        for (const [nm, n] of [["Evaluate", 3], ["Evaluate", 2],
            ["EvaluateNonComparable", 2]] as Array<[string, number]>) {
            evalMi = findMethodByParamCount(playbook.readPointer(), nm, n);
            if (evalMi) { evalName = nm + "/" + n; break; }
        }
        if (!evalMi) {
            return { ok: false, playbookClass,
                error: "Evaluate/EvaluateNonComparable introuvable sur " + playbookClass };
        }
        let unit = ptr(0);
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty === EntityType.Unit && id === body.unitId) unit = e;
        });
        if (unit.isNull()) return { ok: false, error: "unit " + body.unitId + " not found" };
        // Gate per-position du générateur : HasValidTargets(unit, UnitPosition, AbilityType)
        // (BattleQuery slot 0x3f) — best-effort (null si non résolu).
        const aq = runner.add(attackQueryOff).readPointer();
        const hvtMi = aq.isNull()
            ? null : findMethodByParamCount(aq.readPointer(), "HasValidTargets", 3);
        const abilBuf = Memory.alloc(4); abilBuf.writeS32(body.abilityType | 0);
        // Positions candidates : tuile courante (+ movable set si sweep, défaut true).
        const posList: Array<{ col: number | null; row: number | null;
            tile: NativePointer; cur: boolean }> = [];
        const mt = getUnitMainTile(unit, statePtr);
        if (!mt.isNull()) {
            const c = readTileCoord(mt);
            posList.push({ col: c.col, row: c.row, tile: mt, cur: true });
        }
        const sweep = body?.sweep !== false;
        const oneCol = body?.col; const oneRow = body?.row;
        let tilesObj = ptr(0);   // collection movable native = 3e arg d'Evaluate (action tiles)
        if (getMovableTilesMi) {
            const movementQuery = runner.add(movementQueryOff).readPointer();
            const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
            const optsZero = Memory.alloc(0x30);
            for (let k = 0; k < 0x30; k += 4) optsZero.add(k).writeU32(0);
            try {
                const os = invokeMethod(getMovableTilesMi.info, movementQuery,
                    [unit, boolFalse, optsZero]);
                tilesObj = os;
                if (sweep || typeof oneCol === "number") {
                    for (const t of extractTilePtrs(os)) {
                        if (typeof oneCol === "number"
                            && (t.col !== oneCol || t.row !== oneRow)) continue;
                        posList.push({ col: t.col, row: t.row, tile: t.ptr, cur: false });
                    }
                }
            } catch { /* sweep best-effort */ }
        }
        const out: unknown[] = [];
        for (const p of posList) {
            const posPtr = unitPositionAtTile(unit, p.tile, statePtr);
            if (!posPtr) {
                out.push({ pos: [p.col, p.row], cur: p.cur, error: "UnitPosition null" });
                continue;
            }
            let hvt: boolean | null = null;
            if (hvtMi) {
                try { hvt = !invokeMethod(hvtMi.info, aq, [unit, posPtr, abilBuf]).isNull(); }
                catch { hvt = null; }
            }
            try {
                const evalArgs = evalName === "Evaluate/3"
                    ? [unit, posPtr, tilesObj] : [unit, posPtr];
                const bucket = invokeMethod(evalMi.info, playbook, evalArgs);
                if (bucket.isNull()) {
                    out.push({ pos: [p.col, p.row], cur: p.cur, hvt, bucket: null });
                    continue;
                }
                // ⚠ #988 — lire le SEUL champ `best` rendait « empty » sur un bucket PLEIN.
                // `IdunBattle.AI.Playbook.NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies`
                // ne passe QUE par `IdunBattle.AI.BucketSystem.Bucket<T>$$AddActionToBucket`, qui
                // écrit `sub.best` dans un sous-bucket de la `SortedList` — le `best` de la racine
                // reste nul PAR CONSTRUCTION. On décode l'arbre et on mirrore
                // `Bucket<T>$$ChooseAction` (lecture pure). Mesuré sur `1043 ThunderousAssault` :
                // 23 positions rendues « empty » alors que l'action existait.
                const decoded = decodeBucket(bucket);
                const chosen = decoded ? chooseAction(decoded) : null;
                if (!chosen) {
                    // Vraie vacuité : aucune action dans tout l'arbre, sous-buckets compris.
                    out.push({ pos: [p.col, p.row], cur: p.cur, hvt, bucket: "empty",
                        actionCount: decoded ? countActions(decoded) : null,
                        subCount: decoded ? decoded.subBuckets.length : null });
                    continue;
                }
                // BucketAction{action@+0x10, util Fix64@+0x18} ; UnitAction{position@+0x10,
                // target BEntityId@+0x18, ability@+0x20} (layouts du finish-block).
                const utilRaw = new Int64(chosen.utilityRaw);
                const action = ptr(chosen.content);
                // D'OÙ vient la valeur : distingue le régime Comparable (`best` de la racine)
                // du régime à stratégies multiples (un sous-bucket).
                const via = decoded && decoded.best && decoded.best.ptr === chosen.ptr
                    ? "best" : "subBuckets";
                let act: unknown = null;
                if (!action.isNull()) {
                    act = {
                        posQ: action.add(0x10).readU64().toString(16),
                        targetQ: action.add(0x18).readU64().toString(16),
                        targetLow: action.add(0x18).readU32(),
                        ability: action.add(0x20).readS32(),
                    };
                }
                out.push({ pos: [p.col, p.row], cur: p.cur, hvt,
                    util: utilRaw.toNumber() / 4294967296, action: act, via,
                    actionCount: decoded ? countActions(decoded) : null,
                    subCount: decoded ? decoded.subBuckets.length : null });
            } catch (e) {
                out.push({ pos: [p.col, p.row], cur: p.cur, hvt,
                    error: (e as Error).message });
            }
        }
        return { ok: true, runner: label, playbookClass, evalName,
            unitId: body.unitId,
            ability: body.abilityType, abilityName: abilityName(body.abilityType),
            positions: out };
    });

    /** MAPPING itf→méthode d'un playbook (#46) : dumpe, pour CHAQUE interface implémentée
     *  par la classe du playbook d'une ability, les slots de vtable qu'elle projette
     *  (layout IL2CPP du décompilé : interfaceOffsets @klass+0xb0 = paires 16 o
     *  {Il2CppClass* itf, int32 offset}, count u16 @+0x12e ; vtable @+0x138, entrées 16 o
     *  {codePtr, MethodInfo*}). Résout ce que sont RÉELLEMENT les slots 4/5/6 (gates du
     *  générateur `<GenerateActions>d__7 @18119a3f0`) qu'aucune table de symboles offline
     *  n'expose. body: { runnerId?, abilityType, maxSlots? } */
    ctx.rpc.pbSlots = (
        body?: { runnerId?: number; abilityType?: number; maxSlots?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.abilityType !== "number") {
            return { ok: false, error: "need abilityType" };
        }
        let runner: NativePointer;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
        } else if (state.liveRunner) { runner = state.liveRunner; }
        else { return { ok: false, error: "no runner — pass runnerId" }; }
        const dbHit = resolvePlaybookDatabase(runner);
        if (!dbHit) return { ok: false, error: "PlaybookDatabase introuvable" };
        const playbook = loadPlaybook(dbHit.db, body.abilityType);
        if (playbook.isNull()) {
            return { ok: false, error: "pas de playbook pour ability " + body.abilityType };
        }
        const klass = playbook.readPointer();
        const playbookClass = classNameAt(playbook);
        const nItf = klass.add(0x12e).readU16();
        const pairs = klass.add(0xb0).readPointer();
        const maxSlots = body?.maxSlots ?? 12;
        const interfaces: unknown[] = [];
        for (let i = 0; i < nItf; i++) {
            const itf = pairs.add(i * 0x10).readPointer();
            const off = pairs.add(i * 0x10 + 8).readS32();
            let itfName = "?";
            try {
                itfName = s(class_get_namespace(itf) as NativePointer) + "."
                    + s(class_get_name(itf) as NativePointer);
            } catch { /* */ }
            const slots: unknown[] = [];
            // On ne détaille que les interfaces « playbook » (les System.* n'intéressent pas).
            if (itfName.indexOf("Playbook") >= 0 || itfName.indexOf("playbook") >= 0) {
                for (let sIdx = 0; sIdx < maxSlots; sIdx++) {
                    try {
                        const mi = klass.add(0x138 + (off + sIdx) * 0x10 + 8).readPointer();
                        if (mi.isNull()) { slots.push({ slot: sIdx, name: null }); continue; }
                        const mName = s(method_get_name(mi) as NativePointer);
                        let nParams = -1;
                        try { nParams = method_get_param_count(mi) as number; } catch { /* */ }
                        slots.push({ slot: sIdx, name: mName, params: nParams });
                    } catch (e) {
                        slots.push({ slot: sIdx, error: (e as Error).message });
                    }
                }
            }
            interfaces.push({ itf: itfName, offset: off,
                slots: slots.length ? slots : undefined });
        }
        return { ok: true, playbookClass, interfaceCount: nItf, interfaces };
    });

    /** GATE-PROBE générique (#46) : invoque UN slot d'interface du playbook d'une ability,
     *  avec une spec d'arguments fournie par l'appelant — permet de tester chaque gate du
     *  générateur (slots 4/5/6…) sans re-livrer de hooks. La convention d'appel est celle
     *  du jeu : `codePtr(this, args..., MethodInfo)` (entrées vtable 16 o {code, mi}).
     *  args: liste de specs parmi "unit" (entité unitId), "pos" (UnitPosition à col/row,
     *  défaut tuile courante), "tiles" (collection movable native), "null".
     *  body: { runnerId?, unitId, abilityType, itf? (sous-chaîne du nom d'interface,
     *  défaut "Playbook"), slot, args, col?, row? } → { retRaw, retLow } */
    ctx.rpc.pbGate = (
        body?: {
            runnerId?: number; unitId?: number; abilityType?: number;
            itf?: string; slot?: number; args?: string[]; col?: number; row?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.unitId !== "number" || typeof body?.abilityType !== "number"
            || typeof body?.slot !== "number") {
            return { ok: false, error: "need unitId + abilityType + slot" };
        }
        let runner: NativePointer;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
        } else if (state.liveRunner) { runner = state.liveRunner; }
        else { return { ok: false, error: "no runner — pass runnerId" }; }
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const dbHit = resolvePlaybookDatabase(runner);
        if (!dbHit) return { ok: false, error: "PlaybookDatabase introuvable" };
        const playbook = loadPlaybook(dbHit.db, body.abilityType);
        if (playbook.isNull()) {
            return { ok: false, error: "pas de playbook pour ability " + body.abilityType };
        }
        const klass = playbook.readPointer();
        let unit = ptr(0);
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty === EntityType.Unit && id === body.unitId) unit = e;
        });
        if (unit.isNull()) return { ok: false, error: "unit " + body.unitId + " not found" };
        // Interface ciblée par sous-chaîne de nom.
        const wantItf = body?.itf ?? "Playbook";
        const nItf = klass.add(0x12e).readU16();
        const pairs = klass.add(0xb0).readPointer();
        let itfOff = -1; let itfName = "";
        for (let i = 0; i < nItf; i++) {
            const itf = pairs.add(i * 0x10).readPointer();
            let nm = "";
            try {
                nm = s(class_get_namespace(itf) as NativePointer) + "."
                    + s(class_get_name(itf) as NativePointer);
            } catch { continue; }
            if (nm.indexOf(wantItf) >= 0) { itfOff = pairs.add(i * 0x10 + 8).readS32();
                itfName = nm; break; }
        }
        if (itfOff < 0) return { ok: false, error: "interface '" + wantItf + "' absente" };
        const entry = klass.add(0x138 + (itfOff + body.slot) * 0x10);
        const code = entry.readPointer();
        const mi = entry.add(8).readPointer();
        if (code.isNull() || mi.isNull()) {
            return { ok: false, error: "slot " + body.slot + " vide" };
        }
        let miName = "?";
        try { miName = s(method_get_name(mi) as NativePointer); } catch { /* */ }
        // Résolution des args.
        let tilesObj = ptr(0); let posPtr: NativePointer | null = null;
        const needTiles = (body.args ?? []).indexOf("tiles") >= 0;
        const needPos = (body.args ?? []).indexOf("pos") >= 0;
        if ((needTiles || needPos) && getMovableTilesMi) {
            const movementQuery = runner.add(movementQueryOff).readPointer();
            const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
            const optsZero = Memory.alloc(0x30);
            for (let k = 0; k < 0x30; k += 4) optsZero.add(k).writeU32(0);
            try {
                tilesObj = invokeMethod(getMovableTilesMi.info, movementQuery,
                    [unit, boolFalse, optsZero]);
            } catch { /* */ }
        }
        if (needPos) {
            let tile = ptr(0);
            if (typeof body?.col === "number" && !tilesObj.isNull()) {
                for (const t of extractTilePtrs(tilesObj)) {
                    if (t.col === body.col && t.row === body.row) { tile = t.ptr; break; }
                }
            }
            if (tile.isNull()) tile = getUnitMainTile(unit, statePtr);
            posPtr = tile.isNull() ? null : unitPositionAtTile(unit, tile, statePtr);
            if (!posPtr) return { ok: false, error: "UnitPosition irresoluble" };
        }
        const natArgs: NativePointer[] = [playbook];
        for (const a of (body.args ?? [])) {
            if (a === "unit") natArgs.push(unit);
            else if (a === "pos") natArgs.push(posPtr as NativePointer);
            else if (a === "tiles") natArgs.push(tilesObj);
            else if (a === "null") natArgs.push(ptr(0));
            else return { ok: false, error: "arg spec inconnue: " + a };
        }
        natArgs.push(mi);
        try {
            // `propagate` : appel MANAGE, cf. `il2cpp/invoke.ts`.
            const fn = new NativeFunction(code, "pointer",
                natArgs.map(() => "pointer") as unknown as NativeFunctionArgumentType[],
                { exceptions: "propagate" });
            const ret = fn.apply(null, natArgs as never) as NativePointer;
            return { ok: true, itf: itfName, slot: body.slot, method: miName,
                retRaw: ret.toString(16), retLow: ret.and(0xff).toUInt32() };
        } catch (e) {
            return { ok: false, itf: itfName, slot: body.slot, method: miName,
                error: (e as Error).message };
        }
    });
}
