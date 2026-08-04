/** RPCs VUES DECISION + action : decisionView, exposureView, dumpEntityComponents,
 *  applyAction.
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
    abilityStateLayout,
    ActionResult, ActionSpec, activeAbilityMsgClass, applyOneAction,
    attackQueryOff, battleInServicesOff, dpqInServicesOff, entityServicesClass,
    extractTiles, extractTilePtrs,
    entityExtClass, finishUnitTurnMsgClass, getMovableTilesMi, getTilesMi, getUnitMainTile,
    invokeBool, isAliveMi, isCtrlByCurMi, LIST_SIZE, moveUnitMsgClass, movementQueryOff,
    mowAbilityTypes, readTileCoord, readTurnsEnded, resolveDpq, servicesOff, summarize,
    turnsEndedLayout, unitAbilityTypes,
    unitExtClass,
} from "./internals.js";
import { applyAiMsgMi } from "../../game/ai-control.js";
import {
    classFieldsDump, computeAttackPlans, computeDangerZone, computeExposure,
    projectMowsFull, projectUnitsFull,
} from "./projection.js";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function registerViewDecision(ctx: Ctx): void {
    /** decisionView — LA vue décision-ready en UN appel (couche DYNAMIQUE de
     *  l'oracle). Agrège : méta (stage/tour/joueur courant) ; TOUTES les units
     *  (pos hex/HP/team/owner/alive/ctrl/hasAction/ranged/abilities concrètes) ;
     *  les units à activer ; les plans d'attaque rankés du joueur courant
     *  (computeAttackPlans, normal attack par défaut) ; la DANGER ZONE ennemie.
     *  Read-only (mutated=false attendu). Python merge ensuite avec board.py
     *  (terrain/hex) + gameconfig.py (kits) + wiki (tactique).
     *  `includeInactive` publie AUSSI les effets posés-mais-inactifs, avec leur
     *  flag `active` (défaut FAUX = comportement historique) : sans lui, l'absence
     *  d'un effet est ambiguë — non-posé ou posé-inactif ? cf. game/effects.ts.
     *  body: { runnerId, maxRank?=6, allAbilities?=false, includeInactive?=false } */
    ctx.rpc.decisionView = (
        body?: {
            runnerId?: number; maxRank?: number; allAbilities?: boolean;
            includeInactive?: boolean;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        const allAbilities = body?.allAbilities === true;
        const includeInactive = body?.includeInactive === true;
        const maxRank = (typeof body?.maxRank === "number" && body.maxRank > 0)
            ? (body.maxRank | 0) : 6;
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
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
            runner, statePtr, movementQuery, attackQuery, getBestMi, resolveDpq(runner),
            { allAbilities, maxRank });
        const danger = computeDangerZone(statePtr, movementQuery, attackQuery);
        // Effets actifs par unité — lus depuis la liste native du jeu
        // (EffectsOwnedComponent.ActiveEffectIds), = ce que l'UI render en
        // icônes de statut. Attaché par unit/mow (railgun-mark, OW armé, Ice,
        // heal-block, Stun… surfacés sans scan ad-hoc — cf. game/effects.ts).
        const effectsByUnit = readEffectsByUnit(statePtr, { includeInactive });
        // Round-cap clock — board-wide bombardment telegraph (EnvEndBombardment_Incoming).
        // NOT in any unit's owned effects, so surfaced separately (cf. hypotheses.md H58).
        const roundCap = readRoundCapClock(statePtr);
        const after = summarize(statePtr);
        return {
            ok: true, runner: label,
            stage: status.stage, stageName: status.stageName,
            turn: proj.turn, currentPlayer: playerId,
            // #433-r4-r2-r1-r1-c-r1 — `TurnComponent.GetAmountOfTurnsEnded(0)`, l'autre moitié
            // de `AttackQuery$$IsAlreadyUsedThisTurn`. À NE PAS confondre avec `turn` ci-dessus,
            // qui est `GetAmountOfTurnsStartedByCurrentPlayer` : ce sont deux compteurs
            // différents, et seul celui-ci est comparé à `ActiveAbility.UnresetedLastTurnUsed`.
            // `null` = PAS MESURÉ (jamais rabattu sur 0, qui est un tour légitime).
            turnsEnded: readTurnsEnded(statePtr),
            // Ce que les capteurs ont RÉSOLU — un lecteur ne doit pas avoir à deviner si un
            // champ nul vaut « vide » ou « pas trouvé ».
            abilityStateLayout: abilityStateLayout(),
            turnsEndedLayout: turnsEndedLayout(),
            mutated: before.sig !== after.sig, ms: Date.now() - t0,
            unitCount: units.length,
            units: units.map((u) => ({
                ...u, effects: effectsByUnit.get(u.id) ?? [],
            })),
            mowCount: mows.length,
            mows: mows.map((m) => ({
                ...m, effects: effectsByUnit.get(m.casterId) ?? [],
            })),
            toActivateCount: toActivate.length, toActivate,
            attackPlans: plans.units, removeWorks: plans.removeWorks,
            dangerZone: danger, roundCap,
        };
    });

    /** exposureView — MOVE-GUARD (l'INVERSE de decisionView.attackPlans). Pour
     *  chaque MON unité contrôlée+vivante U, somme le dégât que les ENNEMIS peuvent
     *  lui infliger AU PROCHAIN TOUR (reach_dmg = Σ_E best(E→U), dégât fidèle via le
     *  prédicteur natif) → flag `exposed` = exposition LÉTALE possible AVEC une tuile
     *  sûre dispo (movable ∖ danger zone). Read-only. À appeler PRÉ-endturn (U déjà
     *  posé à sa tuile de fin de tour) pour le rapport/garde anti-over-extension.
     *  body: { runnerId, unitId?, allAbilities?=true } */
    ctx.rpc.exposureView = (
        body?: {
            runnerId?: number; unitId?: number; allAbilities?: boolean;
            victimsOffTurn?: boolean;
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
        // NATIF = dégât fidèle ennemi→moi seulement. La géométrie (hasSafeTile /
        // exposed) est calculée côté Python via oracle.geometric_danger_zone (le
        // RPC dangerZone natif renvoie 0 sur ce build — cf. oracle.py).
        const exp = computeExposure(
            runner, statePtr, movementQuery, attackQuery, getBestMi, resolveDpq(runner),
            { unitId: body?.unitId, allAbilities: body?.allAbilities,
              victimsOffTurn: body?.victimsOffTurn });
        const after = summarize(statePtr);
        return {
            ok: true, runner: label,
            stage: status.stage, stageName: status.stageName,
            turn: projectMatchState(statePtr).turn, currentPlayer: playerId,
            mutated: before.sig !== after.sig, ms: Date.now() - t0,
            unitCount: exp.units.length, enemyCount: exp.enemyCount,
            lethalCount: exp.units.filter((u) => u.lethalPossible).length,
            units: exp.units,
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
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
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
        // `applyOneAction` LÈVE si l'action n'a pas pu être construite (cf. son
        // commentaire : rien n'a été soumis au moteur, donc rien n'est mesurable).
        // On rhabille la levée du rang de l'action ET du nombre déjà appliqué —
        // l'état de bataille A BOUGÉ, l'appelant doit le savoir pour ne pas
        // réutiliser son snapshot d'avant l'appel.
        // ASCII dans le MESSAGE (pas dans les commentaires) : il traverse le host
        // puis les `print` des sondes Python, dont la console Windows est en cp1252.
        for (let i = 0; i < actions.length; i++) {
            try { results.push(applyOneAction(runner, aiControl, actions[i])); }
            catch (e) {
                throw new Error("action[" + i + "] " + (e as Error).message
                    + (results.length
                        // Ne le dire QUE si c'est vrai : annoncer « l'etat a bouge »
                        // apres 0 action appliquee enverrait rejouer un montage sain.
                        ? " -- ATTENTION: " + results.length + " action(s) DEJA"
                          + " appliquee(s) avant l'echec, l'etat a bouge"
                        : " (aucune action appliquee, l'etat est intact)"));
            }
        }

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

}
