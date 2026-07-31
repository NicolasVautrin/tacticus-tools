/** ORACLE de la face NONCOMPARABLE (#350-r3 mur (a)) — `ncPlaybookPredict`.
 *
 *  POURQUOI CE RPC EXISTE. `aiPlaybookPredict` ne peut STRUCTURELLEMENT rien rendre pour un
 *  playbook NonComparable, et ce n'est pas un trou de harnais : `ComparablePlaybook`1` et
 *  `NonComparablePlaybook`1` sont deux enfants FRÈRES de `Playbook`1` (lu dans la table versionnée
 *  `data/symbols/<build>/frida/classes.tsv`), et les quatre `Make*Predictions` ne sont déclarées
 *  que sur la branche Comparable (`ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$Make
 *  DamagePredictions` et ses trois sœurs). Sur un NonComparable, le `findMethodByParamCount` de
 *  `playbook-predict.ts::makeDamagePredictions` ne résout donc RIEN : `makeArity: 0`,
 *  `listNull: true`, `count: -1`. C'est la VALEUR DE RETOUR qui dit « ce chemin n'existe pas ici »,
 *  pas un silence à interpréter.
 *
 *  MAIS LA PRÉDICTION EXISTE. `<X>Playbook$$EvaluateNonComparable` évalue le nœud de dégât de son
 *  ability, lit `AActiveAbility$$GetDamageProfile` / `$$GetHits`, et passe le triplet à
 *  `Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent`. Or les DEUX
 *  surcharges « triplet » de ce corps — `(AbilityEntities, damage, profile, hits)` et
 *  `(caster, target, UnitPosition, damage, profile, hits)` — appellent `IBattleQuery` slot `0x28`
 *  (`GetAttackPrediction`) puis `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor` AVANT de scorer.
 *  Un playbook NonComparable construit donc EXACTEMENT le même `ProbableDamageEvent` qu'un
 *  Comparable — il ne le met simplement dans aucune liste, il le consomme sur place. La différence
 *  entre les deux faces n'est pas « prédiction vs heuristique » mais « prédiction RENDUE vs
 *  prédiction CONSOMMÉE ». Détail et preuves : `docs/rl/case-350r3-oracle-noncomparable.md`.
 *
 *  D'OÙ L'ANCRAGE : `ProbableDamageEvent$$.ctor` (corps UNIQUE, signature `(IEntity target,
 *  DamagePredictionResult damagePrediction, Nullable<Fix64> probability, Nullable<Fix64> weight)`),
 *  résolu par `findClassAnywhere` + `findMethodByParamCount(4)` — aucune RVA. La struct est celle que
 *  `playbook-predict.ts::readDamageEvent` décode déjà (offsets dans `game/damage-prediction.ts`,
 *  #276), puisque c'est littéralement le même ctor : ZÉRO layout neuf.
 *
 *  ⚠ HOOK FENÊTRÉ, JAMAIS PERMANENT. Ce ctor est CHAUD (tout `MakeDamagePredictions` comparable le
 *  traverse, et le sweep de décision natif en fait des milliers). Le trampoline est donc attaché
 *  juste avant l'invocation, détaché juste après, dans le `finally`. Il n'existe aucun RPC d'arm
 *  persistant : hors de la fenêtre d'un appel, le jeu tourne sans trampoline.
 *
 *  DEUX VOIES (`via`), et la seconde est le VERROU D'AUTO-VALIDATION :
 *   - `via: "evaluate"` (défaut) — invoque le wrapper `Evaluate(unit, UnitPosition[, tiles])` du
 *     playbook, comme `ncEvaluate` (appeler la leaf `EvaluateNonComparable` nue crashe : l'AbilityState
 *     et le contexte montés par le wrapper manquent). Rend les events CAPTURÉS + l'utilité `best` du
 *     Bucket. C'est l'oracle de la face NC.
 *   - `via: "makeDamagePredictions"` — invoque le chemin COMPARABLE sous le même capteur, et rend
 *     `captured` ET `returned` (la liste décodée). Sur une ability Comparable les deux doivent
 *     COÏNCIDER : c'est ce qui prouve que le capteur lit la bonne struct, sur une face déjà connue,
 *     au lieu de le supposer. Un capteur non validé rendrait des nombres invérifiables.
 *
 *  Read-only (queries de prédiction) — même classe de gestes que `ncEvaluate`/`aiPlaybookPredict`.
 */
import { findClassAnywhere, findMethodByParamCount } from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { runnerOff } from "../../game/runner.js";
import { getRunner } from "../../game/runner-registry.js";
import { setTraceOrigin } from "../../game/trace-origin.js";
import { EntityType, forEachEntity, readBattleStatus } from "../../game/match-state.js";
import { state } from "../../game/state.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { abilityName } from "../../data/ability-names.js";
import { Ctx } from "../../controller.js";
import {
    extractTilePtrs, getMovableTilesMi, getUnitMainTile, movementQueryOff, readTileCoord,
    unitAbilityTypes,
} from "./internals.js";
import {
    classNameAt, DamageEvent, decodeDamageEvents, loadPlaybook, makeDamagePredictions,
    readDamageEvent, resolvePlaybookDatabase, unitPositionAtTile, unitPositionCurrent,
} from "./playbook-predict.js";

/** Borne dure du buffer de capture : au-delà on marque `truncated` plutôt que d'allouer sans fin
 *  (une évaluation NC produit un event par cible éligible — quelques unités, pas des centaines). */
const CAPTURE_CAP = 256;

/** `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor`, résolu UNE fois par session. L'échec est
 *  MÉMORISÉ et NOMMÉ (jamais un zéro silencieux : un renommage inter-build doit rendre une erreur
 *  lisible, pas une capture vide qui se lirait « le natif n'a rien construit »). */
let pdeCtor: NativePointer | null = null;
let pdeCtorError: string | null = null;

function resolveProbableDamageEventCtor(): NativePointer | null {
    if (pdeCtor !== null) return pdeCtor;
    if (pdeCtorError !== null) return null;
    const klass = findClassAnywhere("IdunBattle.AI.Playbook", "ProbableDamageEvent");
    if (!klass) {
        pdeCtorError = "classe IdunBattle.AI.Playbook.ProbableDamageEvent introuvable";
        return null;
    }
    const mi = findMethodByParamCount(klass, ".ctor", 4);
    if (!mi || mi.ptr.isNull()) {
        pdeCtorError = "ProbableDamageEvent..ctor(target, damagePrediction, probability, weight)"
            + " non résolu (4 params)";
        return null;
    }
    pdeCtor = mi.ptr;
    return pdeCtor;
}

interface CaptureResult {
    events: DamageEvent[];
    truncated: boolean;
    ret: NativePointer;
    error?: string;
}

/** Attache le trampoline sur le ctor, exécute `run()`, détache — dans cet ordre et TOUJOURS
 *  (le détachement est dans le `finally`). La struct `ProbableDamageEvent` vit sur la PILE de
 *  l'appelant : elle n'est remplie qu'au RETOUR du ctor, d'où la capture de `args[0]` en `onEnter`
 *  et la lecture en `onLeave` (même discipline que les captures de ctor déjà en place). */
function captureAround(
    ctorPtr: NativePointer, idByPtr: Map<string, number>, run: () => NativePointer,
): CaptureResult {
    const events: DamageEvent[] = [];
    let truncated = false;
    const listener = Interceptor.attach(ctorPtr, {
        onEnter(args) {
            (this as unknown as { pde: NativePointer }).pde = args[0];
        },
        onLeave() {
            const p = (this as unknown as { pde: NativePointer }).pde;
            if (!p || p.isNull()) return;
            if (events.length >= CAPTURE_CAP) { truncated = true; return; }
            try { events.push(readDamageEvent(p, idByPtr)); } catch { /* transient */ }
        },
    });
    Interceptor.flush();
    let ret = ptr(0); let error: string | undefined;
    try { ret = run(); }
    catch (e) { error = (e as Error).message; }
    finally {
        try { listener.detach(); } catch { /* */ }
        Interceptor.flush();
    }
    return { events, truncated, ret, error };
}

export function registerViewNcPredict(ctx: Ctx): void {
    /** ORACLE NONCOMPARABLE (#350-r3). body: { runnerId?, unitId, abilityType,
     *  via? ("evaluate" | "makeDamagePredictions", défaut "evaluate"), targetId? (requis pour
     *  "makeDamagePredictions"), col?, row? (tuile candidate du movable set ; défaut = tuile
     *  courante), level?, multiplier? } */
    ctx.rpc.ncPlaybookPredict = (
        body?: {
            runnerId?: number; unitId?: number; abilityType?: number; targetId?: number;
            via?: string; col?: number; row?: number; level?: number; multiplier?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.unitId !== "number" || typeof body?.abilityType !== "number") {
            return { ok: false, error: "need unitId + abilityType" };
        }
        const via = body?.via === "makeDamagePredictions" ? "makeDamagePredictions" : "evaluate";
        if (via === "makeDamagePredictions" && typeof body?.targetId !== "number") {
            return { ok: false, error: "via=makeDamagePredictions exige targetId" };
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

        const ctorPtr = resolveProbableDamageEventCtor();
        if (!ctorPtr) return { ok: false, error: pdeCtorError };

        const dbHit = resolvePlaybookDatabase(runner);
        if (!dbHit) return { ok: false, error: "PlaybookDatabase introuvable" };
        const playbook = loadPlaybook(dbHit.db, body.abilityType);
        if (playbook.isNull()) {
            return { ok: false, error: "pas de playbook pour ability " + body.abilityType };
        }
        const playbookClass = classNameAt(playbook);

        // Entités : caster (unité OU machine, cf. aiPlaybookPredict), cible, et la map ptr→id qui
        // résout le `IEntity Target` de chaque event capturé.
        let unit = ptr(0); let target = ptr(0);
        const idByPtr = new Map<string, number>();
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty === EntityType.Unit || ty === EntityType.Machine) {
                idByPtr.set(e.toString(), id);
                if (id === body.unitId) unit = e;
            }
            if (ty === EntityType.Unit && id === body.targetId) target = e;
        });
        if (unit.isNull()) return { ok: false, error: "unit " + body.unitId + " not found" };
        if (via === "makeDamagePredictions" && target.isNull()) {
            return { ok: false, error: "target " + body.targetId + " not found" };
        }

        // UnitPosition : tuile courante, ou tuile CANDIDATE (col,row) du movable set — mêmes
        // conventions qu'`aiPlaybookPredict`/`ncEvaluate`. `tilesObj` = 3e argument d'`Evaluate/3`.
        let tilesObj = ptr(0);
        const movementQuery = runner.add(movementQueryOff).readPointer();
        if (getMovableTilesMi && !movementQuery.isNull()) {
            const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
            const optsZero = Memory.alloc(0x30);
            for (let k = 0; k < 0x30; k += 4) optsZero.add(k).writeU32(0);
            try { tilesObj = invokeMethod(getMovableTilesMi.info, movementQuery,
                [unit, boolFalse, optsZero]); } catch { /* best-effort */ }
        }
        let posPtr = unitPositionCurrent(unit, statePtr);
        let posSrc = "current";
        const wantCol = body?.col; const wantRow = body?.row;
        if (typeof wantCol === "number" && typeof wantRow === "number") {
            let tile = ptr(0);
            if (!tilesObj.isNull()) {
                for (const t of extractTilePtrs(tilesObj)) {
                    if (t.col === wantCol && t.row === wantRow) { tile = t.ptr; break; }
                }
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
        if (!posPtr) return { ok: false, error: "GetUnitPosition null" };
        const pos = posPtr;

        // AbilityState per-ability : override body > capteur #100 > défaut flaggé (mirror exact
        // d'`aiPlaybookPredict` — sans quoi les deux oracles ne parleraient pas du même niveau).
        let lvl = body?.level; let mult = body?.multiplier; let stSrc = "body";
        if (typeof lvl !== "number" || typeof mult !== "number") {
            const info = unitAbilityTypes(unit, true).find((a) => a.id === body.abilityType);
            if (info && typeof info.level === "number") {
                lvl = info.level; mult = info.multiplier ?? 100; stSrc = "capteur";
            } else if (typeof lvl !== "number") {
                lvl = 0; mult = mult ?? 100; stSrc = "default(0,100) — entrée ActiveAbility absente";
            }
        }

        let evalName: string | null = null;
        let cap: CaptureResult;
        if (via === "evaluate") {
            // Voie du GÉNÉRATEUR : le wrapper `Evaluate` monte l'AbilityState + DisallowRandom puis
            // appelle `EvaluateInternal` → `EvaluateNonComparable` (slot de vtable +0x318). Appeler
            // la leaf nue crashe (AV 0x0) — mêmes résolutions ordonnées que `ncEvaluate`.
            let evalMi = null;
            for (const [nm, n] of [["Evaluate", 3], ["Evaluate", 2]] as Array<[string, number]>) {
                evalMi = findMethodByParamCount(playbook.readPointer(), nm, n);
                if (evalMi) { evalName = nm + "/" + n; break; }
            }
            if (!evalMi) {
                return { ok: false, playbookClass,
                    error: "Evaluate(2|3) introuvable sur " + playbookClass };
            }
            const args = evalName === "Evaluate/3" ? [unit, pos, tilesObj] : [unit, pos];
            const mi = evalMi;
            cap = captureAround(ctorPtr, idByPtr, () => invokeMethod(mi.info, playbook, args));
        } else {
            cap = captureAround(ctorPtr, idByPtr, () => makeDamagePredictions(
                playbook, unit, pos, target, lvl as number, (mult ?? 100) as number).list);
        }

        const out: Record<string, unknown> = {
            ok: cap.error === undefined, runner: label, via, playbookClass, evalName, posSrc,
            unitId: body.unitId, targetId: body?.targetId ?? null,
            ability: body.abilityType, abilityName: abilityName(body.abilityType),
            abilityState: { level: lvl, multiplier: mult, source: stSrc },
            capturedCount: cap.events.length, captured: cap.events, truncated: cap.truncated,
        };
        if (cap.error !== undefined) out.error = cap.error;

        if (via === "makeDamagePredictions") {
            // VERROU : la liste RENDUE, décodée par le chemin déjà éprouvé. Sur un Comparable elle
            // doit égaler la capture — c'est la preuve que le capteur lit la bonne struct.
            const dec = decodeDamageEvents(cap.ret, idByPtr);
            out.returned = dec.events;
            out.returnedCount = dec.count;
            out.retClass = dec.retClass;
            out.listNull = cap.ret.isNull();
            if (dec.error) out.returnedError = dec.error;
        } else if (!cap.ret.isNull()) {
            // Bucket de la voie NC : `best@+0x20`, `BucketAction{action@+0x10, util Fix64@+0x18}`
            // (mêmes layouts que `ncEvaluate`) — l'utilité que le natif a réellement attribuée.
            try {
                const best = cap.ret.add(0x20).readPointer();
                if (best.isNull()) { out.bucket = "empty"; }
                else {
                    out.bucketUtil = best.add(0x18).readS64().toNumber() / 4294967296;
                    const action = best.add(0x10).readPointer();
                    if (!action.isNull()) {
                        out.bucketAction = {
                            targetLow: action.add(0x18).readU32(),
                            ability: action.add(0x20).readS32(),
                        };
                    }
                }
            } catch (e) { out.bucketError = (e as Error).message; }
        }
        return out;
    });
}
