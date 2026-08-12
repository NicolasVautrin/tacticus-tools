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
// #988 — le décodeur d'arbre de bucket : `best` seul ne voit pas la voie à stratégies multiples.
import { chooseAction, countActions, decodeBucket } from "../../ai-toolkit/bucket-decode.js";
import {
    extractTilePtrs, getMovableTilesMi, getUnitMainTile, movementQueryOff, readTileCoord,
    unitAbilityTypes,
} from "./internals.js";
import {
    classNameAt, DamageEvent, decodeDamageEvents, makeDamagePredictions,
    nullUnitPosition, readDamageEvent, resolvePlaybookDatabase, unitPositionAtTile,
    unitPositionCurrent,
} from "./playbook-predict.js";
import {
    AbilityKeySpace, buildUtilityAttackCase, invokeTriggeredAttackUtility, isAbilityKeySpace,
    isTriggeredVia, loadPlaybookByKeySpace, readTriggeredGates, TriggeredVia,
} from "./triggered-predict.js";

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
    /** ORACLE NONCOMPARABLE (#350-r3) + face TRIGGERED (#369).
     *
     *  body: { runnerId?, unitId, abilityType,
     *    abilityKind? ("active" | "triggered" | "triggeredNonOwner", défaut "active"),
     *    via? — face ACTIVE : "evaluate" (défaut) | "makeDamagePredictions" ;
     *           face TRIGGERED : "attackUtilityInSteps" (défaut) | "attackUtilityForMainTarget"
     *           | "attackUtilityForSecondaryTarget",
     *    targetId? (requis pour "makeDamagePredictions" ET pour toute voie TRIGGERED),
     *    hits? (voies triggered, défaut 1), allowDefault? (face ACTIVE, défaut FALSE),
     *    attackAbility? (voies triggered — `ActiveAbilityType` de l'ATTAQUE CONSIDÉRÉE, ou
     *      "normalAttack" pour l'attaque normale du caster ; défaut = case SANS ability nommée),
     *    col?, row? (tuile candidate du movable set ; défaut = tuile courante),
     *    level?, multiplier? }
     *
     *  ⚠ `attackAbility` EST CE QUI DÉ-MUSELLE `via: "attackUtilityInSteps"` (#375). Sans lui le
     *  `UtilityAttackCase` porte un `Nullable<AbilityOrEffect>` sans valeur, et les deux machines à
     *  états qui construisent un `ProbableDamageEvent` refusent en tête sur
     *  `TriggeredAbilityPlaybook<T>$$IsRegularAttack` — elles yieldent UN `Fix64(0)` et sortent.
     *  `capturedCount: 0` était donc la réponse EXACTE du natif, pas un capteur défaillant : mesuré
     *  le 2026-07-31 sur `1103`/`1054` (et sur `1247`, pour une raison DIFFÉRENTE —
     *  `FuryOfTheAncientsPlaybook` ne surcharge pas la voie attaque). La réponse porte désormais
     *  `gates` (`isRegularAttack` / `isMeleeAttack`) : un zéro y est NOMMÉ, plus jamais muet.
     *
     *  ⚠ `abilityKind` N'EST PAS COSMÉTIQUE : à id égal, `ActiveAbilityType` et
     *  `TriggeredAbilityType` désignent des abilities DIFFÉRENTES, et jusqu'à #369 ce RPC
     *  répondait toujours par le key-space ACTIVE — donc une valeur plausible pour la MAUVAISE
     *  ability, sans jamais d'erreur (`1103` -> `SuperchargePlaybook` au lieu de
     *  `LightImUpPlaybook`). Le champ `abilityKind` est ÉCHOÉ dans la réponse : un appelant peut
     *  ainsi détecter un hook antérieur au correctif (champ absent) au lieu de croire un chiffre.
     *
     *  ⚠ `allowDefault` vaut FALSE par défaut, et c'est le durcissement : sans lui,
     *  `LoadPlaybook(ActiveAbilityType, fallbackToDefault: true)` rend un
     *  `DefaultActiveAbilityPlaybook` pour tout id inconnu — un oracle qui répond « quelque chose »
     *  à une question sans réponse. Les faces triggered n'ont AUCUN fallback natif : là, un id
     *  inconnu rend toujours une erreur. */
    ctx.rpc.ncPlaybookPredict = (
        body?: {
            runnerId?: number; unitId?: number; abilityType?: number; targetId?: number;
            abilityKind?: string; via?: string; hits?: number; allowDefault?: boolean;
            attackAbility?: number | string;
            col?: number; row?: number; level?: number; multiplier?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.unitId !== "number" || typeof body?.abilityType !== "number") {
            return { ok: false, error: "need unitId + abilityType" };
        }
        let keySpace: AbilityKeySpace = "active";
        if (body?.abilityKind !== undefined) {
            if (!isAbilityKeySpace(body.abilityKind)) {
                return { ok: false, error: "abilityKind inconnu: " + String(body.abilityKind)
                    + " (attendu active | triggered | triggeredNonOwner)" };
            }
            keySpace = body.abilityKind;
        }
        const isTriggered = keySpace !== "active";
        // Les deux familles de `via` ne sont PAS interchangeables : la face triggered n'a ni
        // `Evaluate` ni `Make*Predictions` (hiérarchie séparée), la face active n'a pas de
        // `CalculateAttackUtility*`. Un `via` de l'autre famille est une ERREUR, pas un défaut
        // silencieux — sinon on retomberait exactement sur le mode de panne que #369 ferme.
        let via: string;
        let triggeredVia: TriggeredVia = "attackUtilityInSteps";
        if (isTriggered) {
            if (body?.via !== undefined) {
                if (!isTriggeredVia(body.via)) {
                    return { ok: false, error: "via=" + String(body.via) + " n'existe pas sur la face "
                        + keySpace + " (attendu attackUtilityInSteps | attackUtilityForMainTarget"
                        + " | attackUtilityForSecondaryTarget)" };
                }
                triggeredVia = body.via;
            }
            via = triggeredVia;
            if (typeof body?.targetId !== "number") {
                return { ok: false, error: "abilityKind=" + keySpace
                    + " exige targetId (UtilityAttackCase.Base prend une cible)" };
            }
        } else {
            if (isTriggeredVia(body?.via)) {
                return { ok: false, error: "via=" + String(body?.via)
                    + " est une voie TRIGGERED — passe abilityKind:\"triggered\"" };
            }
            via = body?.via === "makeDamagePredictions" ? "makeDamagePredictions" : "evaluate";
            if (via === "makeDamagePredictions" && typeof body?.targetId !== "number") {
                return { ok: false, error: "via=makeDamagePredictions exige targetId" };
            }
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
        const load = loadPlaybookByKeySpace(
            dbHit.db, body.abilityType, keySpace, body?.allowDefault === true);
        if (load.playbook.isNull()) {
            return { ok: false, abilityKind: keySpace, via,
                ability: body.abilityType, error: load.error };
        }
        const playbook = load.playbook;
        const playbookClass = classNameAt(playbook);

        // Entités : caster (unité OU machine, cf. aiPlaybookPredict), cible, et la map ptr→id qui
        // résout le `IEntity Target` de chaque event capturé.
        let unit = ptr(0); let target = ptr(0); let casterIsMachine = false;
        const idByPtr = new Map<string, number>();
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty === EntityType.Unit || ty === EntityType.Machine) {
                idByPtr.set(e.toString(), id);
                if (id === body.unitId) { unit = e; casterIsMachine = ty === EntityType.Machine; }
            }
            if (ty === EntityType.Unit && id === body.targetId) target = e;
        });
        if (unit.isNull()) return { ok: false, error: "unit " + body.unitId + " not found" };
        if ((via === "makeDamagePredictions" || isTriggered) && target.isNull()) {
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
        // Caster MACHINE OF WAR → `UnitPosition$$NullPosition()`, ce que passe littéralement
        // `DefaultMachineTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext` (#360). Ce RPC
        // marchait DÉJÀ sur une MoW — parce que `GetUnitPosition(machine)` rend la même liste VIDE
        // — mais par coïncidence de valeur, pas par mirror : on nomme donc la source. C'est en le
        // comparant à `aiPlaybookPredict` (qui, lui, substituait la position de la CIBLE) que le
        // verrou de l'oracle MoW a été localisé.
        let posSrc = casterIsMachine ? "machine:NullPosition" : "current";
        let posPtr = casterIsMachine ? nullUnitPosition() : unitPositionCurrent(unit, statePtr);
        if (!posPtr && casterIsMachine) {
            posPtr = unitPositionCurrent(unit, statePtr);
            posSrc = "machine:GetUnitPosition(empty)";
        }
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

        // #375 — l'ability que le case NOMME. `"normalAttack"` la résout sur le caster :
        // `ActiveAbilityComponent.NormalAttackType` porte un id CONCRET par unité (ex.
        // `69 Loki_NormalAttack`), jamais l'abstrait `17 NormalAttack` — c'est exactement ce que
        // `unitAbilityTypes` rend sous `kind: "normal"`.
        let attackAbility: number | null = null;
        let attackAbilitySrc: string | null = null;
        if (isTriggered && body?.attackAbility !== undefined) {
            if (typeof body.attackAbility === "number") {
                attackAbility = body.attackAbility | 0;
                attackAbilitySrc = "body";
            } else if (body.attackAbility === "normalAttack") {
                const na = unitAbilityTypes(unit, false).find((a) => a.kind === "normal");
                if (!na) {
                    return { ok: false, abilityKind: keySpace, via,
                        error: "attackAbility:\"normalAttack\" — NormalAttackType absent du caster"
                            + " (une MoW n'en porte pas : passer un id explicite)" };
                }
                attackAbility = na.id; attackAbilitySrc = "NormalAttackType";
            } else {
                return { ok: false, abilityKind: keySpace, via,
                    error: "attackAbility inconnu: " + String(body.attackAbility)
                        + " (attendu un ActiveAbilityType numerique ou \"normalAttack\")" };
            }
        }

        let evalName: string | null = null;
        let cap: CaptureResult;
        let gates: { isRegularAttack: boolean | null; isMeleeAttack: boolean | null } | null = null;
        let triggeredUtil: { utilities: number[]; total: number | null; arity: number;
            error?: string } | null = null;
        if (isTriggered) {
            // Face TRIGGERED — mirror de la boucle native
            // `TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext` :
            // un `UtilityAttackCase` monté par sa factory, puis l'entrée du playbook. Le capteur
            // reste le MÊME `ProbableDamageEvent$$.ctor` — re-confronté sur les quatre call-sites
            // demi-vers-le-pair (#369 §5) : trois l'appellent directement, le quatrième via ses
            // délégations à `…ForMainTarget`/`…ForSecondaryTarget`.
            const built = buildUtilityAttackCase(unit, pos, target, attackAbility);
            if (built.kase.isNull()) {
                return { ok: false, abilityKind: keySpace, via, playbookClass,
                    ability: body.abilityType, error: built.error };
            }
            evalName = "CalculateAttackUtility/" + triggeredVia;
            const kase = built.kase;
            const hits = typeof body?.hits === "number" ? body.hits : 1;
            // Lues AVANT l'invocation, sur le case réellement soumis : c'est ce qui nomme un
            // éventuel `capturedCount: 0` au lieu de le laisser muet.
            gates = readTriggeredGates(playbook, kase);
            cap = captureAround(ctorPtr, idByPtr, () => {
                triggeredUtil = invokeTriggeredAttackUtility(playbook, kase, triggeredVia, hits);
                return ptr(0);   // la voie triggered rend une UTILITÉ, pas une liste d'events
            });
            if (cap.error === undefined && triggeredUtil !== null) {
                const tu = triggeredUtil as { error?: string };
                if (tu.error !== undefined) cap = { ...cap, error: tu.error };
            }
        } else if (via === "evaluate") {
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
            // `abilityKind` + `playbookSource` sont ÉCHOÉS pour que l'appelant puisse vérifier ce
            // qu'il a réellement interrogé — leur ABSENCE de la réponse identifie un hook antérieur
            // à #369, qui répondait toujours par le key-space ACTIVE.
            abilityKind: keySpace, playbookSource: load.source,
            unitId: body.unitId, targetId: body?.targetId ?? null,
            ability: body.abilityType, abilityName: abilityName(body.abilityType),
            abilityState: { level: lvl, multiplier: mult, source: stSrc },
            capturedCount: cap.events.length, captured: cap.events, truncated: cap.truncated,
        };
        if (cap.error !== undefined) out.error = cap.error;

        if (isTriggered) {
            // L'utilité rendue par la face triggered. ⚠ MINORÉE : `getUtilityVal` n'est pas fourni,
            // et `TriggeredAbilityPlaybook<T>$$GetUtilityValue` rend alors 0 pour chaque poids (il
            // le tolère explicitement, cf. `triggered-predict.ts`). C'est `captured` qui porte la
            // prédiction fidèle, pas ce scalaire — d'où le flag qui le dit dans la réponse.
            const tu = triggeredUtil as {
                utilities: number[]; total: number | null; arity: number } | null;
            out.triggeredUtilities = tu ? tu.utilities : [];
            out.triggeredUtilityTotal = tu ? tu.total : null;
            out.utilityWeightsProvided = false;
            // #375 — l'ability NOMMÉE par le case, et les deux gates lues sur ce case. Leur
            // PRÉSENCE identifie un hook porteur du correctif : un appelant peut ainsi distinguer
            // « le natif a refusé la gate » de « le hook ne sait pas nommer d'ability ».
            out.attackAbility = attackAbility === null ? null : {
                requested: body?.attackAbility ?? null, resolved: attackAbility,
                name: abilityName(attackAbility), source: attackAbilitySrc,
            };
            out.gates = gates;
        } else if (via === "makeDamagePredictions") {
            // VERROU : la liste RENDUE, décodée par le chemin déjà éprouvé. Sur un Comparable elle
            // doit égaler la capture — c'est la preuve que le capteur lit la bonne struct.
            const dec = decodeDamageEvents(cap.ret, idByPtr);
            out.returned = dec.events;
            out.returnedCount = dec.count;
            out.retClass = dec.retClass;
            out.listNull = cap.ret.isNull();
            if (dec.error) out.returnedError = dec.error;
        } else if (!cap.ret.isNull()) {
            // Bucket de la voie NC — l'utilité que le natif a réellement attribuée.
            //
            // ⚠ #988 : lire le SEUL champ `best` rendait « empty » sur un bucket PLEIN.
            // `IdunBattle.AI.Playbook.NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies`
            // n'appelle que `Bucket<T>$$AddActionToBucket`, qui écrit `sub.best` dans un
            // sous-bucket de la `SortedList` — jamais le `best` de la racine, qui reste nul PAR
            // CONSTRUCTION. On décode donc l'arbre entier et on mirrore `Bucket<T>$$ChooseAction`
            // (lecture pure : les trois corps natifs ne lisent que des champs).
            try {
                const decoded = decodeBucket(cap.ret);
                const chosen = decoded ? chooseAction(decoded) : null;
                if (!chosen) {
                    // Vraie vacuité : AUCUNE action dans tout l'arbre, sous-buckets compris.
                    out.bucket = "empty";
                    out.bucketActionCount = decoded ? countActions(decoded) : null;
                } else {
                    out.bucketUtil = chosen.utility;
                    out.bucketUtilRaw = chosen.utilityRaw;
                    const action = ptr(chosen.content);
                    if (!action.isNull()) {
                        out.bucketAction = {
                            targetLow: action.add(0x18).readU32(),
                            ability: action.add(0x20).readS32(),
                        };
                    }
                    // D'OÙ vient la valeur : un lecteur doit pouvoir distinguer le régime
                    // Comparable (`best` de la racine) du régime à stratégies multiples.
                    out.bucketVia = decoded && decoded.best
                        && decoded.best.ptr === chosen.ptr ? "best" : "subBuckets";
                    out.bucketActionCount = decoded ? countActions(decoded) : null;
                    out.bucketSubCount = decoded ? decoded.subBuckets.length : null;
                }
            } catch (e) { out.bucketError = (e as Error).message; }
        }
        return out;
    });
}
