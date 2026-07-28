import {
    class_get_fields, class_get_name, class_get_parent,
    field_get_name, field_get_offset, field_get_type,
    findClassAnywhere, findMethodByParamCount, getFieldOffset, s,
    type_get_class_or_element_class,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import {
    EntityType, forEachComponent, forEachEntity, projectMatchState,
    readUnitDeathMeta,
} from "../../game/match-state.js";
import { abilityName } from "../../data/ability-names.js";
import {
    extractTilePtrs, extractTiles, getMovableTilesMi, getUnitMainTile, invokeBool,
    isAliveMi, isCtrlByCurMi, hasActionLeftMi, isRangedMi,
    mowAbilityTypes, readTileCoord, unitAbilityTypes,
} from "./internals.js";
import type { AbilityInfo } from "./internals.js";
import { readEffectsByUnit } from "../../game/effects.js";
import {
    decodeDamageEvents, loadPlaybook, makeDamagePredictions,
    resolvePlaybookDatabase, unitPositionAtTile,
} from "./playbook-predict.js";

export interface RankedTile {
    col: number; row: number;
    dmgMin?: number; dmgMax?: number;
    kill?: boolean; killSure?: boolean; mightCrit?: boolean;
    /** Target carries an active trigger-based dmg-reduction effect the engine
     *  prediction does NOT simulate → predicted dmg/kill is an OVER-estimate
     *  (K! degraded to K?). cf. TF04. */
    predOptimistic?: boolean;
}
export interface AttackEval {
    targetId: number; targetVis: string | null;
    targetPos: { col: number; row: number } | null;
    abilityId: number; ability: string; kind: string;
    movableCount: number; rankCount: number;
    ranked: RankedTile[]; err: string | null;
}
export interface UnitAttackPlan {
    unitId: number; visualId: string | null;
    pos: { col: number; row: number } | null;
    currentTile: { col: number; row: number } | null;
    abilities: AbilityInfo[];
    evals: AttackEval[];
}

/** Ranking des positions d'attaque par (unit contrôlée, ability, target ennemi)
 *  via shrink-and-recall sur GetBestTileToAttackFrom. Lit les abilities
 *  CONCRÈTES (NormalAttackType + actives) + ajoute la tile courante au set
 *  candidat. NE MUTE PAS le MatchState (seul un IOrderedSet transient est muté). */
export function computeAttackPlans(
    runner: NativePointer,
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
    const idByPtr = new Map<string, number>();
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        idByPtr.set(e.toString(), id);
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        const ctrl = invokeBool(isCtrlByCurMi, [e, statePtr]);
        if (ctrl) {
            if (opts.unitId === undefined || opts.unitId === id) myUnits.push({ id, ptr: e });
        } else if (opts.targetId === undefined || opts.targetId === id) {
            enemies.push({ id, ptr: e });
        }
    });

    // Targets carrying a damage-REDUCTION effect whose simulation by the engine
    // prediction is UNCERTAIN → degrade K!→K? + tag optimistic. Conservative
    // heuristic: it only WEAKENS a claim, so a false positive costs nothing.
    //
    // ⚠ The blanket claim this comment used to make — "CalculateDamagePrediction
    // Scenario models only armor + stat caps, trigger-based defensive effects
    // fire at REAL resolution only" — is NOT established, and its own Aun'Shi
    // example is REFUTED by measurement (#192, 2026-07-28): the native
    // prediction DOES apply SereneUnifierSenseOfStone (1169). Oracle attackPlans
    // (2892, 4338) == offline WITH the effect ported, vs (5784, 8676) without —
    // i.e. the native predictor already halved the damage. What the predictor
    // does and does not simulate is per-effect and must be MEASURED effect by
    // effect; do not generalise from this list. TerminatorArmour specifically is
    // still open (its refusal stage is unidentified — cf. task #151).
    //
    // Matched by EffectType NAME (build-agnostic; enum ids can shift) — note the
    // regex catches neither 1169 nor any effect not spelled *Reduce*/*HitReduction*,
    // so those samples were never degraded in the first place. cf. TF04
    // (seed 80004 Njal/TerminatorArmour, …).
    const DMG_REDUCER_RE = /Reduce(Dmg|Damage|Hits)|HitReduction/i;
    const effectsByUnit = readEffectsByUnit(statePtr);
    const targetHasDmgReducer = (tid: number): boolean => {
        const effs = effectsByUnit.get(tid);
        return effs ? effs.some((e) => DMG_REDUCER_RE.test(e.name ?? "")) : false;
    };

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
    // DamagePrediction : GetAllPredictions(unit, tile, ability) → dict.get_Item(target)
    // → struct (boxed+0x10). = le PREVIEW decisionView (Attack-based quel que soit
    // l'abilityType) → FALLBACK seulement (#103). Le dégât AFFICHÉ passe d'abord par
    // l'ORACLE PLAYBOOK per-ability (MakeDamagePredictions), correct pour les spéciales
    // CONFIG-based (PlasmaCannon…) que GetAllPredictions sous-/zéro-value.
    const predMi = dpq.isNull() ? null
        : findMethodByParamCount(dpq.readPointer(), "GetAllPredictions", 3);
    let predItemMi: { info: NativePointer; ptr: NativePointer } | null = null;
    // Oracle playbook (#102/#103) : PlaybookDatabase résolue UNE fois, playbooks cachés
    // par ability id ; UnitPosition construite sur la tuile candidate `best` (GetUnitPositionAtTile).
    const dbHit = resolvePlaybookDatabase(runner);
    const playbookDb = dbHit ? dbHit.db : ptr(0);
    const playbookCache = new Map<number, NativePointer>();
    const getPlaybook = (abilityId: number): NativePointer => {
        if (playbookDb.isNull()) return ptr(0);
        let pb = playbookCache.get(abilityId);
        if (pb === undefined) { pb = loadPlaybook(playbookDb, abilityId); playbookCache.set(abilityId, pb); }
        return pb;
    };
    // Remplit une RankedTile depuis un tuple {hp, dmgMin/Max, willKill, mightKill, mightCrit}
    // (source playbook OU preview) : dmg affiché + K!/K? via les seuils de mort EFFECTIFS
    // (post floor-Resilient + overkill), PAS dmgMin/Max brut. predOptimistic dégrade K!→K?
    // si la cible porte un dmg-reducer trigger-based non simulé (TF04).
    const applyDmg = (
        entry: RankedTile, hp: number, dmgMin: number, dmgMax: number,
        willKill: number, mightKill: number, mightCrit: boolean, hasReducer: boolean,
    ): void => {
        entry.dmgMin = dmgMin; entry.dmgMax = dmgMax;
        entry.killSure = hp <= willKill;
        entry.kill = hp <= mightKill;
        entry.mightCrit = mightCrit;
        if (hasReducer) { entry.predOptimistic = true; entry.killSure = false; }
    };

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
                const tgtHasReducer = targetHasDmgReducer(tgt.id);
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
                        // Dégât affiché en atterrissant sur `best` contre tgt. Pour les
                        // ACTIVES/granted (candidates config-based) : l'ORACLE PLAYBOOK
                        // per-ability (#103 — MakeDamagePredictions depuis la tuile candidate),
                        // correct pour PlasmaCannon/SpiritLeech… L'attaque NORMALE reste sur
                        // GetAllPredictions : c'est son PREVIEW NATIF authoritatif (== le
                        // playbook, validé NEW==OLD sur id 69) et bien moins cher → on évite
                        // ~half des invokes MakeDamagePredictions. Distinction STRUCTURELLE
                        // normal-vs-active, PAS un gate nom/id (#99).
                        let filled = false;
                        if (ab.kind !== "normal") {
                            const pb = getPlaybook(ab.id);
                            if (!pb.isNull()) {
                                const posPtr = unitPositionAtTile(u.ptr, best, statePtr);
                                if (posPtr) {
                                    const mk = makeDamagePredictions(pb, u.ptr, posPtr, tgt.ptr,
                                        ab.level ?? 0, ab.multiplier ?? 100);
                                    const ev = decodeDamageEvents(mk.list, idByPtr)
                                        .events.find((e) => e.targetId === tgt.id);
                                    if (ev) {
                                        applyDmg(entry, ev.hpBefore, ev.healthDmgMin,
                                            ev.healthDmgMax, ev.willKillDmg, ev.mightKillDmg,
                                            ev.mightCrit !== 0, tgtHasReducer);
                                        filled = true;
                                    }
                                }
                            }
                        }
                        // GetAllPredictions (preview) : chemin normal de l'attaque NORMALE,
                        // + fallback si le playbook d'une active ne résout pas / ne rend pas
                        // d'event pour cette cible.
                        if (!filled && predMi && !dpq.isNull()) {
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
                                            // dmgMin/Max = AccurateHealthDamage MITIGÉ ; kill/killSure
                                            // via les seuils de mort EFFECTIFS get_WillBeKill@0x24 /
                                            // get_MightBeKill@0x28 (PAS dmgMin/Max brut — sur-claime
                                            // K! sur un Resilient, cf. TF04).
                                            applyDmg(entry, bb.readS32(),
                                                bb.add(0x60).readS32(), bb.add(0x64).readS32(),
                                                bb.add(0x24).readS32(), bb.add(0x28).readS32(),
                                                bb.add(0xb1).readU8() !== 0, tgtHasReducer);
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

export interface FullUnit {
    id: number; visualId: string | null;
    pos: { col: number; row: number } | null;
    hp: number | null; owner: number | null; team: number | null;
    alive: boolean; ctrl: boolean; hasAction: boolean; ranged: boolean;
    /** #185 : tué par une attaque de MÊLÉE (`UnitComponent.DefeatedByMeleeAttack`,
     * le byte-gate du sélecteur natif `UnitsDefeatedByMeleeAttackSelector`) +
     * tueur (`DeathReason` → `DamageSource.get_KillerId`). Lu sur le SQUAD →
     * fiable aussi sur les corpses (pas de UnitFoot). false/null sur les vivants. */
    defeatedByMelee: boolean; killerId: number | null;
    /** `ChildComponent.ParentId` — l'entité qui a INVOQUÉ celle-ci (summon),
     *  null si l'unité n'est l'enfant de personne. Publié à la source : tout
     *  gate natif « u est un enfant de X » se lisait jusqu'ici en le
     *  reconstruisant depuis la config (`_kit_spawn_visual_ids`), exact tant
     *  qu'une équipe ne porte pas deux summoners du même summon. */
    parentId: number | null;
    abilities: AbilityInfo[];
}

// ChildComponent : lien enfant -> invocateur. `ParentId` (BEntityId) résolu par
// nom au runtime ; repli sur +0x10 (offset confirmé live, cf. case-perform-ai-action
// §6.2) si la table de champs n'est pas énumérable.
const childComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "ChildComponent");
const childParentIdOff = childComponentClass
    ? (getFieldOffset(childComponentClass, "ParentId") || 0x10) : 0x10;

function readParentId(entityPtr: NativePointer): number | null {
    if (!childComponentClass) return null;
    let comp: NativePointer | null = null;
    forEachComponent(entityPtr, (c, klass) => {
        if (comp === null && klass.equals(childComponentClass)) comp = c;
    });
    if (comp === null) return null;
    try { return (comp as NativePointer).add(childParentIdOff).readS32(); }
    catch { return null; }
}

/** Projection de TOUTES les units (2 camps) : flags vivants + abilities concrètes. */
export function projectUnitsFull(statePtr: NativePointer, allAbilities: boolean): FullUnit[] {
    const proj = projectMatchState(statePtr);
    const base = new Map<number, (typeof proj.units)[number]>();
    for (const u of proj.units) base.set(u.squadId, u);
    const out: FullUnit[] = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        const b = base.get(id);
        const death = readUnitDeathMeta(e);   // #185 (corpses inclus — e = squad)
        out.push({
            id, visualId: b?.visualId ?? null, pos: b?.pos ?? null,
            hp: b?.hp ?? null, owner: b?.ownerId ?? null, team: b?.teamId ?? null,
            parentId: readParentId(e),
            alive: invokeBool(isAliveMi, [e, statePtr]),
            ctrl: invokeBool(isCtrlByCurMi, [e, statePtr]),
            hasAction: invokeBool(hasActionLeftMi, [e]),
            ranged: invokeBool(isRangedMi, [e]),
            defeatedByMelee: death.defeatedByMelee, killerId: death.killerId,
            abilities: unitAbilityTypes(e, allAbilities),
        });
    });
    return out;
}

export interface FullMow {
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
    abilities: AbilityInfo[];
}

/** Projection des MoW (MachinePlatform/Machine) prête pour l'oracle. Les MoW ne
 *  bougent pas (ability-only) → pas de plan de move. La projection `proj.mows`
 *  porte déjà pos/hp/owner/team ; on enrichit ici les flags vivants + abilities
 *  concrètes lues sur l'entité Machine (Type 6, porteuse des abilities). Le
 *  casterId pour `applyAction {kind:"ability"}` = machineId. */
export function projectMowsFull(
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
export function computeDangerZone(
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
export function classFieldsDump(
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

export interface ExposureThreat {
    enemyId: number; enemyVis: string | null;
    abilityId: number; ability: string;
    attackTile: { col: number; row: number } | null;
    dmgMin: number; dmgMax: number;
    overwatch: boolean;
}
export interface UnitExposure {
    unitId: number; visualId: string | null;
    pos: { col: number; row: number } | null;
    hp: number | null;
    threats: ExposureThreat[];
    reachDmgMin: number; reachDmgMax: number;
    lethalSure: boolean; lethalPossible: boolean;
    err: string | null;
}

/** EXPOSITION (move-guard) — l'INVERSE de computeAttackPlans : ennemi=attaquant,
 *  MES units=cibles. C'est la SEULE partie que Python ne peut PAS faire : le dégât
 *  FIDÈLE ennemi→moi. Pour chaque MON unité U (contrôlée+vivante), somme le dégât
 *  que les ENNEMIS peuvent lui infliger au prochain tour : chaque ennemi E à sa
 *  MEILLEURE tuile d'attaque vs U (GetBestTileToAttackFrom) × sa meilleure ability,
 *  dégât fidèle via GetAllPredictions(E, tile, ability)→get_Item(U). reach_dmg =
 *  Σ_E best(E→U). lethalPossible = reach_dmg.max ≥ hp ; lethalSure = min ≥ hp.
 *  Le volet GÉOMÉTRIE (`hasSafeTile` / `exposed = lethal ∧ hasSafeTile`) est calculé
 *  côté PYTHON via oracle.geometric_danger_zone (le RPC dangerZone natif renvoie 0
 *  sur ce build — cf. oracle.py). NE MUTE PAS le MatchState (seuls des IOrderedSet
 *  transients sont touchés). Sur-approx assumée (faux positifs = à déclarer). */
export function computeExposure(
    runner: NativePointer,
    statePtr: NativePointer, movementQuery: NativePointer,
    attackQuery: NativePointer, getBestMi: { info: NativePointer },
    dpq: NativePointer,
    opts: { unitId?: number; allAbilities?: boolean; victimsOffTurn?: boolean },
): { units: UnitExposure[]; enemyCount: number } {
    // défaut TRUE : inclure les actives ennemies (over-approx de la menace).
    const allAbilities = opts.allAbilities !== false;
    // victimsOffTurn : sur un clone POST-endturn, le joueur courant = l'IA →
    // les VICTIMES (mes units) sont HORS-tour, les ATTAQUANTS (IA) sont courants
    // (donc movable sets débloqués = menace next-turn faithful). cf. move-guard
    // Phase 2.5 (hill-climb guidé par la menace).
    const victimsOffTurn = opts.victimsOffTurn === true;
    const proj = projectMatchState(statePtr);
    const visById = new Map<number, string | null>();
    const posById = new Map<number, { col: number; row: number } | null>();
    const hpById = new Map<number, number | null>();
    for (const u of proj.units) {
        visById.set(u.squadId, u.visualId);
        posById.set(u.squadId, u.pos);
        hpById.set(u.squadId, u.hp);
    }
    const effectsByUnit = readEffectsByUnit(statePtr);
    const overwatchArmed = (enemyId: number): boolean => {
        const effs = effectsByUnit.get(enemyId);
        return effs
            ? effs.some((e) => (e.name ?? "").toLowerCase().includes("overwatch"))
            : false;
    };

    const myUnits: Array<{ id: number; ptr: NativePointer }> = [];
    const enemies: Array<{ id: number; ptr: NativePointer }> = [];
    const idByPtr = new Map<string, number>();
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        idByPtr.set(e.toString(), id);
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        const ctrl = invokeBool(isCtrlByCurMi, [e, statePtr]);
        // VICTIMES = courant (live, mon tour) OU hors-tour (clone post-endturn) ;
        // ATTAQUANTS = l'autre camp. Les attaquants doivent être le joueur COURANT
        // pour avoir des movable sets non-vides (turn-gating).
        const isVictim = victimsOffTurn ? !ctrl : ctrl;
        if (isVictim) {
            if (opts.unitId === undefined || opts.unitId === id) myUnits.push({ id, ptr: e });
        } else {
            enemies.push({ id, ptr: e });
        }
    });

    const abilBuf = Memory.alloc(4);
    const boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
    const optsZero = Memory.alloc(0x30);
    for (let k = 0; k < 0x30; k += 4) optsZero.add(k).writeU32(0);

    const predMi = dpq.isNull() ? null
        : findMethodByParamCount(dpq.readPointer(), "GetAllPredictions", 3);
    let predItemMi: { info: NativePointer; ptr: NativePointer } | null = null;
    let addMi: { info: NativePointer; ptr: NativePointer } | null = null;
    let addResolved = false;
    // Oracle playbook (#103) : menace ennemie affichée via MakeDamagePredictions per-ability
    // (correct pour les spéciales config-based), fallback GetAllPredictions. db résolue 1x,
    // playbooks cachés par ability id.
    const dbHit = resolvePlaybookDatabase(runner);
    const playbookDb = dbHit ? dbHit.db : ptr(0);
    const playbookCache = new Map<number, NativePointer>();
    const getPlaybook = (abilityId: number): NativePointer => {
        if (playbookDb.isNull()) return ptr(0);
        let pb = playbookCache.get(abilityId);
        if (pb === undefined) { pb = loadPlaybook(playbookDb, abilityId); playbookCache.set(abilityId, pb); }
        return pb;
    };

    // Movable set de chaque ennemi : calculé UNE fois (GetBestTileToAttackFrom ne
    // mute pas le set → réutilisable pour tous mes U et toutes les abilities). On
    // y ajoute la tuile COURANTE de E (GetMovableTilesFor l'exclut → sinon
    // « attaquer sans bouger » manquerait).
    const enemyData = enemies.map((E) => {
        let set: NativePointer = ptr(0);
        try {
            set = invokeMethod(getMovableTilesMi!.info, movementQuery,
                [E.ptr, boolFalse, optsZero]);
        } catch { set = ptr(0); }
        if (!set.isNull()) {
            gcRoot.add(set);
            if (!addResolved) {
                addMi = findMethodByParamCount(set.readPointer(), "Add", 1);
                addResolved = true;
            }
            const mt = getUnitMainTile(E.ptr, statePtr);
            if (!mt.isNull() && addMi) {
                try { invokeMethod(addMi.info, set, [mt]); } catch { /* */ }
            }
        }
        return { ...E, set, abilities: unitAbilityTypes(E.ptr, allAbilities) };
    });

    const out: UnitExposure[] = [];
    try {
        for (const U of myUnits) {
            const threats: ExposureThreat[] = [];
            let reachMin = 0; let reachMax = 0;
            let err: string | null = null;
            for (const E of enemyData) {
                if (E.set.isNull()) continue;
                // Meilleure menace de E sur U = max dmgMax sur ses abilities.
                let best: ExposureThreat | null = null;
                for (const ab of E.abilities) {
                    abilBuf.writeS32(ab.id);
                    let tile: NativePointer = ptr(0);
                    try {
                        tile = invokeMethod(getBestMi.info, attackQuery,
                            [E.ptr, E.set, U.ptr, abilBuf]);
                    } catch (e) { err = (e as Error).message; continue; }
                    if (tile.isNull()) continue; // E ne peut pas atteindre/frapper U
                    let dmgMin = 0; let dmgMax = 0;
                    // Menace E→U : ACTIVES/granted par l'ORACLE PLAYBOOK per-ability (#103,
                    // depuis `tile`) ; attaque NORMALE par GetAllPredictions (preview natif
                    // authoritatif + moins cher). Distinction structurelle, pas un gate.
                    let filled = false;
                    if (ab.kind !== "normal") {
                        const pb = getPlaybook(ab.id);
                        if (!pb.isNull()) {
                            const posPtr = unitPositionAtTile(E.ptr, tile, statePtr);
                            if (posPtr) {
                                const mk = makeDamagePredictions(pb, E.ptr, posPtr, U.ptr,
                                    ab.level ?? 0, ab.multiplier ?? 100);
                                const ev = decodeDamageEvents(mk.list, idByPtr)
                                    .events.find((e) => e.targetId === U.id);
                                if (ev) { dmgMin = ev.healthDmgMin; dmgMax = ev.healthDmgMax; filled = true; }
                            }
                        }
                    }
                    // GetAllPredictions : attaque NORMALE + fallback active non résolue.
                    if (!filled && predMi && !dpq.isNull()) {
                        try {
                            const dict = invokeMethod(predMi.info, dpq,
                                [E.ptr, tile, abilBuf]);
                            if (!dict.isNull()) {
                                if (!predItemMi) {
                                    predItemMi = findMethodByParamCount(
                                        dict.readPointer(), "get_Item", 1);
                                }
                                if (predItemMi) {
                                    const boxed = invokeMethod(predItemMi.info, dict, [U.ptr]);
                                    if (!boxed.isNull()) {
                                        const bb = boxed.add(0x10);
                                        dmgMin = bb.add(0x60).readS32();
                                        dmgMax = bb.add(0x64).readS32();
                                    }
                                }
                            }
                        } catch { /* prédiction best-effort */ }
                    }
                    if (!best || dmgMax > best.dmgMax) {
                        best = {
                            enemyId: E.id, enemyVis: visById.get(E.id) ?? null,
                            abilityId: ab.id, ability: ab.name,
                            attackTile: readTileCoord(tile),
                            dmgMin, dmgMax, overwatch: overwatchArmed(E.id),
                        };
                    }
                }
                if (best) {
                    threats.push(best);
                    reachMin += best.dmgMin; reachMax += best.dmgMax;
                }
            }
            const hp = hpById.get(U.id) ?? null;
            const lethalSure = hp !== null && reachMin >= hp;
            const lethalPossible = hp !== null && reachMax >= hp;
            out.push({
                unitId: U.id, visualId: visById.get(U.id) ?? null,
                pos: posById.get(U.id) ?? null, hp,
                threats, reachDmgMin: reachMin, reachDmgMax: reachMax,
                lethalSure, lethalPossible, err,
            });
        }
    } finally {
        for (const E of enemyData) {
            if (!E.set.isNull()) { try { gcRoot.remove(E.set); } catch { /* */ } }
        }
    }
    return { units: out, enemyCount: enemies.length };
}
