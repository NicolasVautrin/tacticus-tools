import {
    class_get_fields, class_get_name, class_get_parent,
    field_get_name, field_get_offset, field_get_type,
    fieldOffsetOr, findClassAnywhere, findMethodByParamCount, s,
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
    extractTilePtrs, extractTiles, getMovableTilesMi, getTilesMi, getUnitMainTile, invokeBool,
    isAliveMi, isCtrlByCurMi, hasActionLeftMi, isRangedMi,
    mowAbilityTypes, readTileCoord, unitAbilityTypes,
} from "./internals.js";
import type { AbilityInfo } from "./internals.js";
import { readEffectsByUnit } from "../../game/effects.js";
import { DamagePredictionFields, readDamagePredictionResult } from "../../game/damage-prediction.js";
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
    /** #350-r3a-r4 — `ranked` est-il l'ensemble COMPLET des positions valides ?
     *  `true` seulement si la boucle est sortie sur `best.isNull()` (épuisement).
     *  `false` = plafond `maxRank` atteint, ou `Remove` en échec : il PEUT rester des positions.
     *  Le champ ABSENT (bundle antérieur) se lit « pas mesuré », jamais « complet ». */
    rankComplete: boolean;
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
    // Remplit une RankedTile depuis un `DamagePredictionResult` DÉCODÉ (source playbook OU
    // preview) : dmg affiché + K!/K? via les seuils de mort EFFECTIFS (post floor-Resilient +
    // overkill), PAS dmgMin/Max brut. predOptimistic dégrade K!→K? si la cible porte un
    // dmg-reducer trigger-based non simulé (TF04).
    //
    // #372 — cette fonction RECEVAIT les deux BORNES (`willKill`, `mightKill`) et rejouait
    // `hp <= willKill` chez elle. C'était un TROISIÈME lieu où la règle de `get_WillBeKill`
    // était ré-assemblée à la main, donc un troisième endroit où il manquait le gate
    // `CannotBeGuaranteedKilled@0x89` et la préférence pour `BlockScenarios[0]+0x0c`. Elle
    // prend désormais le résultat décodé et lit le VERDICT que le décodeur a calculé — foyer
    // unique. `willBeKill` est TRI-ÉTAT : `null` = non mesuré, et on laisse alors `killSure`
    // non posé (sous-claim assumé : le HUD n'affiche pas K!) plutôt que d'inventer un `false`
    // indiscernable d'un « pas de kill garanti ».
    const applyDmg = (
        entry: RankedTile, p: DamagePredictionFields, hasReducer: boolean,
    ): void => {
        entry.dmgMin = p.healthDmgMin; entry.dmgMax = p.healthDmgMax;
        if (p.willBeKill !== null) entry.killSure = p.willBeKill;
        entry.kill = p.mightBeKill;
        entry.mightCrit = p.mightCrit !== 0;
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
                        // rien n'a été énuméré : on ne sait RIEN des positions valides (#350-r3a-r4)
                        rankComplete: false,
                        ranked: [], err: "movable: " + (e as Error).message });
                    continue;
                }
                if (set.isNull()) {
                    evals.push({ targetId: tgt.id, targetVis: visById.get(tgt.id) ?? null,
                        targetPos: posById.get(tgt.id) ?? null, abilityId: ab.id,
                        ability: ab.name, kind: ab.kind, movableCount: 0, rankCount: 0,
                        rankComplete: false,                        // idem (#350-r3a-r4)
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
                // #350-r3a-r4 — `rankComplete` DIT si la boucle a été plafonnée.
                // Le plafond `maxRank` n'existe nulle part côté natif :
                // `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` interroge
                // `IdunBattle.Core.Services.AttackQuery$$GetValidTargets` UNE FOIS PAR POSITION,
                // sans borne. À `maxRank = 6` (défaut du RPC `decisionView`) 21 positions sur 33
                // disparaissent du plan — assez pour déplacer un argmax (mesuré, `case-350r3` §9).
                // Le drapeau ne détronque pas (le coût du shrink-and-recall reste borné) : il rend
                // la troncature LISIBLE, ce qui permet au port de ne payer un `castFromTiles` que
                // là où il en a besoin, au lieu de le payer partout ou de se dégrader en silence.
                // Faux par DÉFAUT, vrai UNIQUEMENT sur la sortie par épuisement des tuiles valides
                // (`best.isNull()`). Les autres sorties — plafond `maxRank` atteint, `Remove` non
                // résolu, `Remove` rendant false, exception — laissent `false` : dans tous ces cas
                // il PEUT rester des positions valides, et le supposer serait la dégradation
                // permissive elle-même. Un défaut à `true` aurait fait taire le cas nominal.
                let rankComplete = false;
                try {
                    for (let r = 0; r < maxRank; r++) {
                        const best = invokeMethod(getBestMi.info, attackQuery,
                            [u.ptr, set, tgt.ptr, abilBuf]);
                        if (best.isNull()) { rankComplete = true; break; }
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
                                        applyDmg(entry, ev, tgtHasReducer);
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
                                            // Struct BOXÉ : champs à `boxed+0x10`. Offsets
                                            // centralisés dans `game/damage-prediction.ts` (#276).
                                            // dmgMin/Max = `HealthDamage` MITIGÉ ; kill/killSure via
                                            // les seuils de mort EFFECTIFS que lisent
                                            // `get_WillBeKill` / `get_MightBeKill` (PAS dmgMin/Max
                                            // brut — sur-claime K! sur un Resilient, cf. TF04).
                                            const p = readDamagePredictionResult(boxed.add(0x10));
                                            applyDmg(entry, p, tgtHasReducer);
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
                    rankCount: ranked.length, ranked, rankComplete, err });
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
    /** TRI-ÉTAT du champ ci-dessus (#378) : `false` = capteur MUET (classe
     *  `ChildComponent` irrésolue ou lecture en erreur) — `parentId: null` n'y
     *  veut PAS dire « pas de parent ». `true` = mesure faite ; `parentId: null`
     *  y signifie « cette unité n'est l'enfant de personne ». cf. `readParentLink`. */
    parentMeasured: boolean;
    /** #419-r1-tr10-r2 — l'EMPREINTE : toutes les tuiles de l'entité, dans l'ordre des pieds
     *  (`feet[0]` est la MainTile). Mirror d'`IdunBattle.Entities.EntityExtensions$$GetTiles`.
     *  TRI-ÉTAT : `null` = capteur MUET, `[]` = mesuré et vide (entité sans tuile). */
    feet: Array<{ col: number; row: number }> | null;
    abilities: AbilityInfo[];
}

/** Lien enfant -> invocateur, TRI-ÉTAT. Source UNIQUE des deux canaux qui le publient
 *  (`decisionView.units[]` via `projectUnitsFull`, `combatSnapshot.units[]` via
 *  `rpc-snapshot.ts`) — un seul point de RE, donc pas de divergence possible entre eux.
 *
 *  MIRROR : `IdunBattle.Entities.Components.ChildComponent`, champ `ParentId` (`BEntityId`
 *  = int32). C'est CE champ que lit `IdunBattle.Entities.UnitExtensions$$GetParent` —
 *  `TryGetComponent<ChildComponent>(child)` puis `state.GetEntity(comp.ParentId)`, et la
 *  RÉCURSION vers la racine n'a lieu que si son 3e argument `root` est vrai (le nœud DSL
 *  `IdunBattleLogic.Entities.DSLSelectors$$Parent` le passe explicitement). On publie le lien
 *  DIRECT ; remonter la chaîne est l'affaire du consommateur.
 *
 *  ⚠ Ne PAS confondre avec `IdunBattle.Entities.Components.ParentComponent`, dont le champ
 *  `+0x10` est `ChildrenIds` (une `List`, le sens PARENT -> enfants) : son `$$.ctor` y construit
 *  une liste et son `$$ToString` la formate. C'est l'ancrage que le résidu de #372 nommait, et
 *  il désigne l'autre bout du lien. Le lien enfant -> parent, celui dont on a besoin, est bien
 *  `ChildComponent.ParentId`. Vérifié sur `rnca9r7q6c` par DEUX sources indépendantes : le RPC
 *  `classFields` (`ParentId`, offset 16, type `BEntityId`) et le décompilé de
 *  `IdunBattle.Entities.Components.ChildComponent$$ToString` (`il2cpp_value_box(Int32,
 *  *(int *)(this + 0x10))`).
 *
 *  POURQUOI LE TRI-ÉTAT. « Pas de parent » = un FAIT ; « classe irrésolue » = on n'a rien lu. Les
 *  rabattre tous deux sur `null` ferait passer un capteur MORT pour un board sans aucun summon, et
 *  le consommateur écraserait en silence un `parent_id` que la simulation offline avait, lui,
 *  correctement posé. Même discipline que `unitFlags` / `traits` (`null` = non mesuré, `[]` =
 *  mesuré et vide).
 *
 *  ⚠ `ParentId == 0` VAUT « PAS DE PARENT », et on le normalise en `null` ici. Ce n'est pas une
 *  convention qu'on invente, c'est celle du natif, établie par DEUX voies :
 *   * STRUCTURE — `IdunBattle.Entities.Components.MatchComponent$$NextId` est un PRÉ-incrément
 *     (`*(int *)(this + 0x10) += 1 ; return`) sur un champ zéroé à la construction, et c'est la
 *     source UNIQUE des ids (ses xrefs sont exactement les `Add*Operation$$Execute` : unité,
 *     machine, plateforme, tuile, effet, joueur, ability d'environnement). Le premier id émis est
 *     donc `1` : **`0` n'est jamais un id d'entité**, c'est le zéro d'un champ jamais écrit —
 *     `IdunBattle.Entities.Components.ChildComponent$$.ctor` n'écrit PAS `ParentId`.
 *   * COMPORTEMENT — `UnitExtensions$$GetParent` ne gate PAS sur zéro : il appelle
 *     `state.GetEntity(ParentId)` tel quel, qui rend `null` pour un id inexistant. Rendre `null`
 *     ici est donc le mirror EXACT de ce que le natif conclut, pas un raccourci.
 *   * MESURÉ le 2026-07-31 (`probe_378_parent_link.py`, runner 264, MC1_67/777) : le warboss et
 *     les trois autres unités du roster portent `ParentId = 0`, les deux `orksOrkBoys` invoqués
 *     portent `83` = l'id du warboss ; et `dumpEntityComponents(entityId: 0)` rend
 *     `entity 0 not found`.
 *
 *  ⚠ La branche « composant absent » ne se déclenche PAS en pratique — le même probe montre que
 *  CHAQUE unité porte `ChildComponent` ET `ParentComponent`, l'ECS les crée systématiquement. On
 *  la garde parce qu'elle mirrore la sortie `TryGetComponent == false` de `GetParent`, et parce
 *  qu'un capteur qui SUPPOSE la présence d'un composant rend du garbage le jour où elle change. */
export interface ParentLink { parentId: number | null; parentMeasured: boolean }

// ─── #419-r1-tr10-r2 — l'EMPREINTE d'une entité, côté DÉCISION ────────────────────────────────
// MIRROR : `IdunBattle.Entities.EntityExtensions$$GetTiles(entity, state)`, dont le corps est
// LITTÉRALEMENT `new List<IEntity>(IdunBattle.Entities.EntityExtensions$$IterateTiles(entity,
// state))` — la MATÉRIALISATION de l'itérateur que consomme
// `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` (`inner = origin.Select(entities)`,
// puis le ring-1 de CHAQUE tuile de `inner`). C'est donc l'artefact EXACT, pas un substitut.
//
// ⚠ POURQUOI PAS `IdunBattle.Entities.UnitExtensions$$GetUnitFeet`, que le résidu nommait.
// Son corps, relu : `GetComponent<UnitComponent>(GetUnit(unit,state))` ->
// `UnitComponent$$GetFeetEnumerator()` -> pour chaque pied, `state.GetEntity(<footId>)`. Il rend
// donc les entités **UnitFoot**, PAS les TUILES — le port a besoin des coordonnées de tuile, et
// `IterateTiles` fait justement la résolution `UnitFoot -> Tile` (`foot.<+0x20>.<+0x14>`) que
// `GetUnitFeet` ne fait pas. Le point d'ancrage du backlog est corrigé ici.
//
// ⚠ POURQUOI PAS `combatSnapshot`, que le FOYER du backlog désignait. Ce capteur est COLD
// (« one-shot, à appeler une fois au chargement de la BattleConfig ») alors qu'une empreinte est
// DYNAMIQUE : elle suit chaque déplacement. Publiée là, elle serait PÉRIMÉE dès le premier move —
// une valeur fausse plutôt qu'une valeur absente. Elle vit donc sur `decisionView`, refrappé à
// chaque pas.
//
// TRI-ÉTAT, comme `unitFlags` / `traits` / `parentId` : `null` = capteur MUET (méthode non
// résolue, ou invocation en erreur) — surtout PAS `[]`, qui se lirait « cette entité n'occupe
// aucune tuile », ce qui est une valeur LÉGITIME du domaine (une MoW hors plateau). Le
// consommateur (`engine/playbook/adjacency.py::iterate_tiles`) retombe alors sur la MainTile,
// c'est-à-dire le comportement d'avant ce capteur, EXACTEMENT.
export function readEntityFeet(
    entityPtr: NativePointer, statePtr: NativePointer,
): Array<{ col: number; row: number }> | null {
    if (!getTilesMi) return null;
    try {
        const list = invokeMethod(getTilesMi.info, null, [entityPtr, statePtr]);
        if (list.isNull()) return null;
        return extractTiles(list);
    } catch { return null; }
}

// `ParentId` (BEntityId) résolu par NOM au runtime ; repli sur +0x10 (offset mesuré, cf. le
// commentaire ci-dessus) si la table de champs n'est pas énumérable.
const childComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "ChildComponent");
// `fieldOffsetOr` et NON `getFieldOffset(...) || …` : le « nom absent » vaut **-1**, truthy en JS,
// donc le repli ne se déclenchait pas (lecture à `comp - 1`). Mesuré sur `actorStats` (#340-r1).
const childParentIdOff = childComponentClass
    ? fieldOffsetOr(childComponentClass, "ParentId", 0x10) : 0x10;

export function readParentLink(entityPtr: NativePointer): ParentLink {
    // Classe irrésolue -> AUCUNE mesure possible. Le distinguer de « composant absent » est
    // tout l'objet du champ `parentMeasured` : sans lui les deux rendaient `null`.
    if (!childComponentClass) return { parentId: null, parentMeasured: false };
    let comp: NativePointer | null = null;
    forEachComponent(entityPtr, (c, klass) => {
        if (comp === null && klass.equals(childComponentClass)) comp = c;
    });
    // Composant absent = mesure FAITE, et son résultat est « cette unité n'a pas de parent » —
    // c'est exactement la sortie `TryGetComponent == false` de `UnitExtensions$$GetParent`.
    if (comp === null) return { parentId: null, parentMeasured: true };
    try {
        const raw = (comp as NativePointer).add(childParentIdOff).readS32();
        // `0` = champ jamais écrit = aucun parent (cf. `MatchComponent$$NextId`, pré-incrément).
        return { parentId: raw === 0 ? null : raw, parentMeasured: true };
    } catch { return { parentId: null, parentMeasured: false }; }
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
            ...readParentLink(e),
            alive: invokeBool(isAliveMi, [e, statePtr]),
            ctrl: invokeBool(isCtrlByCurMi, [e, statePtr]),
            hasAction: invokeBool(hasActionLeftMi, [e]),
            ranged: invokeBool(isRangedMi, [e]),
            defeatedByMelee: death.defeatedByMelee, killerId: death.killerId,
            feet: readEntityFeet(e, statePtr),
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
    /** #419-r1-tr10-r2 — `GetTiles(<entité Machine>, state)`, tri-état (cf. `readEntityFeet`).
     *  ⚠ Il peut valoir `[]` : `EntityExtensions.<IterateTiles>d__17$$MoveNext` teste TROIS types
     *  d'entité (pied -> sa tuile ; tuile -> elle-même ; unité -> ses pieds) et sort FAUX pour
     *  tout le reste. Une `EntityType.Machine` n'est aucune des trois — c'est un FAIT natif, pas
     *  une panne, d'où `platformTiles` juste en dessous. */
    feet: Array<{ col: number; row: number }> | null;
    /** Les positions des `MachinePlatform` du même `machineId`, agrégées.
     *
     *  ⚠ **MESURÉ (`#419-r7`) : ce champ ne peut PAS dépasser UNE tuile, et la prémisse qui le
     *  justifiait est fausse.** Elle disait « l'empreinte était déjà publiée, éclatée en une ligne
     *  `mows[]` par plateforme ». `projectMatchState` n'en émet plus qu'**une par MACHINE**
     *  (`for (const [machineId, m] of machines)`, avec `platformByMachine` qui garde la PREMIÈRE
     *  plateforme comme ancre) — un correctif antérieur, dont le commentaire dit lui-même
     *  « emit ONE row PER MACHINE ». Agréger `proj.mows` par `machineId` regroupe donc des lignes
     *  DÉJÀ uniques. Mesure live : `adeptExorcist` et `ultraDreadnought` rendent chacun
     *  **1 ligne** `mows`, `feet = []` et `platformTiles = []`, avec `pos = null`.
     *
     *  Ce n'est pas mordant, et c'est pourquoi le champ reste : une MoW est **hors plateau**
     *  (`decisionView.mows[].pos is null`, déjà mesuré par `#287-r4-r1`), donc elle n'a pas
     *  d'empreinte à publier. Le porteur multi-tuiles RÉEL de la face DÉCISION est un **summon**
     *  (`ultraSmnDreadnought`, 3 hexes) — une `EntityType.Unit`, donc couverte par
     *  `units[].feet`, qui, lui, est confronté et rend bien ses 3 tuiles.
     *
     *  Le remplir vraiment demanderait de balayer les `EntityType.MachinePlatform` ici même
     *  (`forEachEntity` + `readMachinePlatformLink` + `readTilePosition`) plutôt que de dériver de
     *  `proj.mows`. À ne faire que si une MoW acquiert une empreinte sur la grille : aujourd'hui
     *  ce serait du code sans observable. */
    platformTiles: Array<{ col: number; row: number }>;
    /** #287-r14-r2 — les entityId des `MachinePlatform` (Type=7) liées à cette machine.
     *
     *  ⚠ À NE PAS confondre avec `platformTiles` juste au-dessus : celui-là publie des
     *  POSITIONS (et il est vide, mesuré, parce qu'une plateforme n'a pas de
     *  `PositionComponent`) ; celui-ci publie des IDENTITÉS D'ENTITÉ, et elles EXISTENT —
     *  mesuré le 2026-08-14 sur `orksRukkatrukk` : **deux** (75, 76), quand `id` n'en publiait
     *  qu'une. C'est le substrat de la branche `EntityType == 7` d'`IdunBattle.Entities.
     *  UnitExtensions$$GetMachine` (via `TileExtensions$$GetMachinePlatformContent`), que le
     *  port ne peut pas résoudre sans la liste ENTIÈRE.
     *
     *  `null` = pas mesuré (projection plus ancienne) ; `[]` = mesuré, aucune plateforme liée. */
    platformIds: number[] | null;
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
    // #419-r1-tr10-r2 — regroupement des plateformes par machine : c'est l'empreinte.
    const platformsByMachine = new Map<number, Array<{ col: number; row: number }>>();
    for (const m of mows) {
        if (!m.pos) continue;
        const l = platformsByMachine.get(m.machineId) ?? [];
        l.push(m.pos);
        platformsByMachine.set(m.machineId, l);
    }
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
            feet: e ? readEntityFeet(e, statePtr) : null,
            platformTiles: platformsByMachine.get(m.machineId) ?? [],
            // #287-r14-r2 — transporté TEL QUEL depuis `projectMatchState`, qui est le seul
            // étage à balayer les entités `MachinePlatform`. `?? null` préserve le tri-état.
            platformIds: m.platformIds ?? null,
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
                                        // Struct BOXÉ : champs à `boxed+0x10` (#276).
                                        const p = readDamagePredictionResult(boxed.add(0x10));
                                        dmgMin = p.healthDmgMin;
                                        dmgMax = p.healthDmgMax;
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
