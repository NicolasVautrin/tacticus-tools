// Comprehensive observation RPC over a runner's MatchState.
//
// Thin wrapper around `projectMatchState` (game/match-state.ts) which is
// the canonical projector: it uses IL2CPP component class reflection
// (`forEachComponent`) instead of hardcoded offsets, walks UnitFoot →
// Tile to resolve visible piece positions correctly, and resolves
// Player → TeamId so the `teamId` is the logical team (1/2/3).
//
// Output shape preserves the historic observeBattle contract used by
// diag scripts: { stage, stageName, units: [{entityId, visualId,
// playerId, col, row, hp, hpMax, ...}], counts, byType }.
// Per-foot entries (= one row per visible tile occupied by a unit).
//
// `units[].inPlay` (2026-08-16) porte le verdict natif `UnitExtensions$$IsAlive` — le
// SEUL canal qui distingue une unité RETIRÉE d'une unité vivante ici, `isDead` restant
// `false` dans les deux cas. Voir sa docstring : sans lui, les pieds d'un avatar de MoW
// rappelé restent publiés à pleine vie et se lisent comme une divergence de moteur.

import { state } from "../game/state.js";
import { runnerOff } from "../game/runner.js";
import {
    forEachEntity, forEachComponent, projectMatchState, EntityType,
} from "../game/match-state.js";
import { getRunner as getRegistryRunner } from "../game/runner-registry.js";
import {
    class_get_name, class_get_namespace, cstr, findMethodByParamCount,
} from "../il2cpp/helpers.js";
import { unitExtClass, invokeBoolOrNull } from "./ai-step/internals.js";

/** `IdunBattle.Entities.UnitExtensions$$IsAlive(entity, state)` — résolution RUNTIME
 *  (aucune RVA), `null` si irrésolue, ce que `inPlay` publie alors tel quel. */
const isAliveMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "IsAlive", 2) : null;
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

/** DIAG (scratch): dump component class names for entities of given types,
 * to discover where a Machine's HP/position actually live. One entity per
 * type by default. Reads a few candidate int fields raw for inspection. */
function dumpEntityComponents(opts: {
    runnerId?: number; types?: number[]; perType?: number;
}): unknown {
    let runner: NativePointer | null = null;
    if (opts?.runnerId !== undefined) {
        try { runner = getRegistryRunner(opts.runnerId).runner; }
        catch (e) { return { err: (e as Error).message }; }
    } else { runner = state.liveRunner ?? null; }
    if (!runner) return { err: "no runner" };
    const statePtr = runner.add(runnerOff.state).readPointer();
    if (statePtr.isNull()) return { err: "matchState null" };

    const types = opts.types ?? [1, 6, 7];
    const perType = opts.perType ?? 1;
    const seen: Record<number, number> = {};
    const out: Array<Record<string, unknown>> = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (!types.includes(ty)) return;
        seen[ty] = (seen[ty] ?? 0) + 1;
        if (seen[ty] > perType) return;
        const comps: Array<Record<string, unknown>> = [];
        forEachComponent(e, (comp, klass) => {
            let name = "?", ns = "?";
            try { name = cstr(class_get_name(klass) as NativePointer); }
            catch { /* keep */ }
            try { ns = cstr(class_get_namespace(klass) as NativePointer); }
            catch { /* keep */ }
            // Raw ints at the offsets the projector cares about, so we can
            // eyeball where HP (Max@0x14/Rem@0x18) and pos (@0x10/0x14) sit.
            const peek: Record<string, number> = {};
            for (const off of [0x10, 0x14, 0x18, 0x20, 0x78]) {
                try { peek[`0x${off.toString(16)}`] = comp.add(off).readS32(); }
                catch { /* skip */ }
            }
            comps.push({ name, ns, comp: comp.toString(), peek });
        });
        out.push({ entityId: id, entityType: ty, components: comps });
    });
    return { ok: true, counts: seen, entities: out };
}

interface UnitObservation {
    /** ⚠ L'ENTITE `UnitFoot`, PAS L'UNITE — et surtout PAS un id adressable.
     *
     *  `projectMatchState` emet UNE LIGNE PAR PIED : ce champ porte le pied, `squadId`
     *  porte l'escouade. Une unite multi-hex a PLUSIEURS pieds pour un seul `squadId`
     *  (mesure live, Galatian : 108/109/110 -> squadId 107), et l'ordre croissant de ce
     *  champ EST l'ordre de `_feet` (cf. `engine/runner/snapshot.py::_load_feet`), qui
     *  en depend. Il a donc une raison d'exister : ne pas le supprimer.
     *
     *  ⚠ NE JAMAIS LE PASSER a `applyAction`, `fsmInput`/`fsmTap`, ni le comparer a
     *  `decisionView.unitId`/`targetId` : ces trois canaux adressent l'ESCOUADE. Sur une
     *  unite mono-pied l'ecart est de +1 exactement, donc l'id fautif DESIGNE UNE AUTRE
     *  ENTITE VALIDE et le natif echoue en silence -- mesure du 2026-08-09, six gestes
     *  d'attaque sans effet avant que `_unit.ToString()` du FSM ne rende
     *  `[Unit 101, unitId: spaceBlackmane]` la ou ce champ disait 102.
     *
     *  Le nom est trompeur et devrait etre `footId` ; le renommage touche 133 fichiers
     *  (dont ~30 tests live) et n'est pas fait ici. */
    entityId: number;
    /** L'ESCOUADE — c'est CELUI-CI qu'on passe partout ailleurs (`applyAction`,
     *  `fsmInput`, `decisionView.unitId`/`targetId`, `_unit` du FSM). */
    squadId: number;
    /** Verdict d'`IdunBattle.Entities.UnitExtensions$$IsAlive(entity, state)` sur
     *  l'ESCOUADE. Tri-état : `null` = PAS MESURÉ (méthode irrésolue), jamais rabattu
     *  sur `false` — un capteur en panne qui rendrait `false` effacerait TOUTES les
     *  unités, c'est-à-dire serait indiscernable d'une bataille vide.
     *
     *  ⚠ CE N'EST PAS `isDead`, ET C'EST TOUT L'INTÉRÊT. `isDead` lit le composant ;
     *  `IsAlive` teste EN PLUS l'appartenance à la collection du MatchState. Une unité
     *  RETIRÉE SANS MOURIR a donc `isDead: false` mais `inPlay: false` — cas mesuré le
     *  2026-08-16 sur l'avatar de Machine of War : `AetherStride` fait descendre la MoW
     *  en unité invoquée (`RemoveMachine` + `AddUnit`, `Unit_Parent_Id`), puis le
     *  `StartTurn` suivant la rappelle (`StartTurnOperation$$ResetMachine`) avec
     *  `Unit_IsDying:0`. Le moteur la retire ; ses PIEDS, eux, restaient publiés ici à
     *  pleine vie, sur des tuiles qu'elle n'occupe plus.
     *
     *  Le coût de l'absence de ce canal a été mesuré : un rejeu pas-à-pas du combat
     *  d'un autre joueur a été déclaré DIVERGENT (3 unités « survivantes » à 7634 PV)
     *  alors qu'il était BIT-EXACT — 47 messages, 0 écart — dès qu'on croisait avec
     *  `combatSnapshot`, qui filtre par ce même prédicat (`isAliveMi`, cf.
     *  `rpc-snapshot.ts`). L'écart n'était pas dans le moteur mais dans cette vue.
     *
     *  Les lignes ne sont PAS supprimées : ~250 montages Python consomment cette forme,
     *  et une unité retirée reste utile à observer. On PUBLIE le verdict, on ne filtre
     *  pas à la place de l'appelant. */
    inPlay: boolean | null;
    visualId: string | null;
    /** Logical team id (1=player, 2=AI, 3=env). Use this for friend/foe. */
    teamId: number | null;
    /** Owner's PlayerEntityId (BEntityId in MatchState — not the logical
     * 11/12 PlayerId of the BC config). Kept for traceability. */
    playerId: number | null;
    col: number | null;
    row: number | null;
    hp: number | null;
    hpMax: number | null;
    /** Depletable armor pool (ArmorComponent, StatType.Armor=4). null if the
     * unit has no ArmorComponent (unarmored). Feeds the repair ARMOR term (#83). */
    armor: number | null;
    armorMax: number | null;
    rank: number | null;
    isDead: boolean;
}

interface BattleObservation {
    ok: boolean;
    runner: string | null;
    matchState: string | null;
    stage: number | null;
    stageName: string | null;
    currentPlayer: number | null;
    counts: { total: number; tiles: number; units: number; match: number;
              effects: number; player: number; other: number };
    byType: Record<number, number>;
    units: UnitObservation[];
    /** MoW projection (1 row per MachinePlatform → linked Machine). Empty
     * unless the battle has deployed Machines of War. Exposes pos/hp/owner so
     * we can verify a MoW is actually on the board and being played. */
    mows: unknown[];
    err?: string;
}

function observeBattle(opts?: { runnerId?: number }): BattleObservation {
    const obs: BattleObservation = {
        ok: false, runner: null, matchState: null,
        stage: null, stageName: null, currentPlayer: null,
        counts: { total: 0, tiles: 0, units: 0, match: 0,
                  effects: 0, player: 0, other: 0 },
        byType: {}, units: [], mows: [],
    };

    let runner: NativePointer | null = null;
    if (opts?.runnerId !== undefined) {
        try {
            runner = getRegistryRunner(opts.runnerId).runner;
        } catch (e) {
            obs.err = (e as Error).message; return obs;
        }
    } else {
        runner = state.liveRunner ?? null;
    }
    if (!runner) { obs.err = "no runner (live or by id)"; return obs; }
    obs.runner = runner.toString();

    const statePtr = runner.add(runnerOff.state).readPointer();
    if (statePtr.isNull()) { obs.err = "matchState is null"; return obs; }
    obs.matchState = statePtr.toString();

    // Counts per EntityType: fast scan (no component decoding).
    forEachEntity(statePtr, (_e, _id, type) => {
        obs.counts.total++;
        obs.byType[type] = (obs.byType[type] ?? 0) + 1;
        switch (type) {
            case EntityType.Tile: obs.counts.tiles++; break;
            case EntityType.Unit: obs.counts.units++; break;
            case EntityType.Match: obs.counts.match++; break;
            case EntityType.Effect: obs.counts.effects++; break;
            case EntityType.Player: obs.counts.player++; break;
            default: obs.counts.other++; break;
        }
    });

    // Reuse the canonical projector — robust to layout changes (uses
    // component class reflection), and resolves UnitFoot → Tile positions
    // + Player → TeamId mapping correctly.
    const proj = projectMatchState(statePtr);
    obs.stage = proj.stage;
    obs.stageName = proj.stageName;
    obs.currentPlayer = proj.playerOnTurn;

    // `IsAlive` se juge sur l'ENTITÉ ESCOUADE (Type Unit/Machine), pas sur le pied :
    // le prédicat natif prend `(entity, state)`. On indexe donc par id d'escouade,
    // puis on annote chaque pied. Une escouade ABSENTE de la collection n'a plus
    // d'entité du tout — c'est `false` (retirée), pas `null` (pas mesuré).
    const enJeuParEscouade = new Map<number, boolean | null>();
    if (isAliveMi) {
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit && ty !== EntityType.Machine) return;
            enJeuParEscouade.set(id, invokeBoolOrNull(isAliveMi, [e, statePtr]));
        });
    }

    for (const u of proj.units) {
        obs.units.push({
            entityId: u.id,
            squadId: u.squadId,
            inPlay: isAliveMi === null
                ? null
                : (enJeuParEscouade.has(u.squadId)
                    ? enJeuParEscouade.get(u.squadId) ?? null
                    : false),
            visualId: u.visualId,
            teamId: u.teamId,
            playerId: u.ownerId,
            col: u.pos?.col ?? null,
            row: u.pos?.row ?? null,
            hp: u.hp,
            hpMax: u.maxHp,
            armor: u.armor,
            armorMax: u.armorMax,
            rank: u.rank,
            isDead: u.isDead,
        });
    }

    // Expose the MoW projection the projector already computed (units-only
    // copy above drops it). Lets callers verify a Machine of War is deployed
    // on the board (pos set) and being played (pos/hp change across turns).
    obs.mows = (proj.mows ?? []) as unknown[];

    // #480 — TRI-ETAT : « aucune entite » n'est PAS « bataille vide », c'est « PAS MESURE ».
    // Mesure du 2026-08-05 (session 7) : appele SANS `runnerId` alors qu'aucune bataille n'est
    // chargee, ce RPC rendait `ok:true`, `counts` tout a zero, `units: []` et AUCUNE `err` --
    // `obs.ok = true` etait pose inconditionnellement des que `statePtr` est non nul. Un
    // consommateur qui verifie pourtant `ok` lisait donc « la bataille existe et elle est vide ».
    // Discriminant mesure, meme session : runner porteur d'une bataille = 158 entites / 63 tuiles ;
    // live sans bataille = 0 / 0. Une `MatchState` reelle porte toujours ses tuiles, donc
    // `total === 0` ne peut designer qu'un etat non mesurable -- le seul cas ou ce durcissement
    // mord, et il ne change rien pour un appel portant un `runnerId` de runner monte.
    if (obs.counts.total === 0) {
        obs.err = "matchState carries no entity — no battle loaded (not an empty battle)";
        return obs;
    }

    obs.ok = true;
    return obs;
}

export function register(ctx: Ctx): void {
    ctx.rpc.observeBattle = (opts?: { runnerId?: number }) =>
        queueOnMainThread(() => observeBattle(opts));
    ctx.rpc.dumpEntityComponents = (opts?: {
        runnerId?: number; types?: number[]; perType?: number;
    }) => queueOnMainThread(() => dumpEntityComponents(opts ?? {}));
}
