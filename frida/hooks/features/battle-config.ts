// Live BattleConfiguration inspection + (eventually) mutation.
//
// BattleConfiguration is the per-battle config stitched by
// CampaignGameModeSource.LoadBattle() and stored at _currentBattle (+0x80).
// We read from the amorce-captured campaignGameModeSourcePtr — so any inspection RPC requires
// a successful amorce first.
//
// Layout reference (from decompilation):
//   BattleConfiguration                     class
//     +0x10  Id                             string
//     +0x28  SpawnPointSetIndex             int
//     +0x30  Player                         PlayersConfiguration
//     +0x40  PredefinedUnits                List<PredefinedUnits>
//     +0x68  Board                          BattleConfigBoardConfiguration
//     +0x80  Units                          List<UnitConfiguration>  (templates)
//     +0x88  Tiles                          List<BattleConfigTileConfiguration> (palette)
//
//   ⚠ LES NEUF BOOLEENS SONT CONSECUTIFS A PARTIR DE +0xE0, ET SE RESSEMBLENT TOUS.
//   Cette ligne a porte `+0xE7 RandomizeAiInput` — c'est FAUX d'un octet, `+0xE7` est
//   `DisableRandomness` (#10022-r1). L'erreur etait INVISIBLE parce que les deux valent
//   `false` au seed : un accord en regime degenere. Chaque ligne cite ci-dessous l'ancre
//   NOMMEE qui la fixe ; les positions sans ancre sont deduites de l'ordre de
//   serialisation Newtonsoft de `data/seed-bc.json`, encadre par deux ancres.
//     +0xE0  UseGroupForAddUnit         bool   IdunBattle.Core.Services.BattleQuery$$get_UseGroupForAddUnit
//     +0xE1  NoAutomaticUnitTurns       bool   IdunBattle.Core.Services.BattleQuery$$get_NoAutomaticUnitTurns
//     +0xE2  EnableIdunAbilities        bool   (position)
//     +0xE3  IsTestBattle               bool   (position)
//     +0xE4  DisableTimeouts            bool   (position)
//     +0xE5  DisableAnimatorRecovery    bool   (position)
//     +0xE6  DisableActiveAbilitiesOnAI bool   IdunBattle.Runner.IdunRunner$$Initialize -> param `disableActiveAbilities`
//     +0xE7  DisableRandomness          bool   idun.IdunMainView$$ShowBattle (gate du seed horloge)
//     +0xE8  RandomizeAiInput           bool   IdunBattle.Runner.IdunRunner$$Initialize -> param `configurationRandomizeAiInput`
//
//   PredefinedUnits (per-player squad)      class
//     +0x10  Id                             PlayerId (enum int)
//     +0x18  Units                          List<PredefinedUnit>
//
//   PredefinedUnit                          class
//     +0x10  UnitId                         string
//     +0x18  RemainingHealth                Nullable<int>
//     +0x20  MaxHealth                      Nullable<int>
//
//   UnitConfiguration (template)            class
//     +0x10  Id                             string
//     +0x18  VisualId                       string
//     +0x28  Faction                        string
//     +0x38  Health                         int
//
//   BattleConfigBoardConfiguration          class
//     +0x10  Id                             string
//     +0x18  Width                          int
//     +0x1C  Height                         int
//
//   System.Collections.Generic.List<T>      class (IL2CPP)
//     +0x10  _items                         T[]  (Il2CppArray: len at +0x18, data at +0x20)
//     +0x18  _size                          int

import {
    readIl2cppString, findClassAnywhere, findMethod, class_get_methods, class_get_name,
    method_get_name, method_get_param_count, methodEntry, s as cstr, MethodRef,
} from "../il2cpp/helpers.js";
import { createManagedString } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import {
    getCampaignGameModeSourcePtr, getMowEventGameModeSourcePtr,
    getPvpGameModeSourcePtr, tryActiveDiscoveryOfSources,
    findPvpGameModeSourceViaHeap,
} from "./campaign-builder.js";
import { buildRunner, runnerApplyMi } from "../game/runner.js";
import { registerRunner, getRunner as getRegistryRunner,
    listRunners as listRegistryRunners, MAX_RUNNERS }
    from "../game/runner-registry.js";
import {
    findClass, findCtorByParamCount, findMethodByParamCount, methodParamClass,
    getFieldInfo, field_get_type, type_get_class_or_element_class, class_instance_size,
} from "../il2cpp/helpers.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { bcDeLaSourceMontee, sourceMontee } from "./source-vivante.js";
// (!)FORME B. Le FOYER du réceptacle `EnvironmentAbilities` -- même objet que celui que posent
// `guild-war-config` (buffs de zone) et `sandbox-mode` (pression de fin d'Arène). Son ctor natif
// ne crée AUCUN de ses trois membres : une troisième copie du geste aurait divergé, et ce sont
// des ÉCRITURES en mémoire managée, où une divergence ne donne pas un résultat différent mais un
// CRASH. Pas de cycle : `environment-abilities` n'importe pas ce module.
import * as envAbilities from "./environment-abilities.js";
import { champPointeur, estRefus } from "./lecture-champs.js";
import { triggeredAbilityName } from "../data/triggered-ability-names.js";
import { deserializeFromJson, isDeserializerReady } from "../il2cpp/serializer.js";
import { getFieldOffset } from "../il2cpp/helpers.js";
import { serializeToJson as _serializeBcToJson } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

// --- Diag : hook AddPredefinedMachines pour savoir si elle fire pendant
//     Initialize. Si oui → la condition mode-skip n'est pas la cause, c'est
//     ailleurs (IsMachineOfWar(unitId)=false, slot manquant, etc.).
//     Si non → SetupGameOperation.Execute() la skip → faut hooker plus haut. ---
let _addPredefMachinesFires = 0;
const setupGameOpClass = findClassAnywhere(
    "IdunBattle.Operations", "SetupGameOperation");
const addPredefMachinesMi = setupGameOpClass
    ? findMethod(setupGameOpClass, "AddPredefinedMachines") : null;
if (addPredefMachinesMi) {
    try {
        Interceptor.attach(addPredefMachinesMi.ptr, {
            onEnter() { _addPredefMachinesFires++; },
        });
        log("[battle-config] AddPredefinedMachines hooked for diag");
    } catch (e) {
        log("[battle-config] AddPredefinedMachines hook failed: " + (e as Error).message);
    }
} else {
    log("[battle-config] AddPredefinedMachines method not resolved");
}

// --- PredefinedMachine class resolution (for BC.PredefinedMachines patch) ---

const predefinedMachinesOfWarClass = findClassAnywhere(
    "IdunBattle.Configuration", "PredefinedMachinesOfWar");
const predefinedMachineOfWarClass = findClassAnywhere(
    "IdunBattle.Configuration", "PredefinedMachineOfWar");
const predefinedMachinesOfWarCtor = predefinedMachinesOfWarClass
    ? findCtorByParamCount(predefinedMachinesOfWarClass, 0) : null;
// PredefinedMachineOfWar a un ctor(string unitId) + un ctor() — on prend
// celui à 1 arg pour init avec UnitId.
const predefinedMachineOfWarCtor1 = predefinedMachineOfWarClass
    ? findCtorByParamCount(predefinedMachineOfWarClass, 1) : null;
const predefinedMachineOfWarCtor0 = predefinedMachineOfWarClass
    ? findCtorByParamCount(predefinedMachineOfWarClass, 0) : null;

// --- Offsets ---

const CGMS_OFF_CURRENT_BATTLE = 0x80;
// MachinesOfWarEventGameModeSource a son _currentBattle a un offset different
// (+0xF0 vs +0x80 pour Campaign). On essaie d'abord Campaign puis MoW Event.
const MOWE_OFF_CURRENT_BATTLE = 0xF0;
// PvpGameModeSource._currentBattle @+0xD8
const PVP_OFF_CURRENT_BATTLE = 0xD8;

const BC_OFF_ID = 0x10;
// BC.GameMode est `Nullable<GameMode>` @0x18. Mono Nullable<int> layout :
// hasValue @+0 (1B + 3B padding), value @+4 (4B). Donc hasValue @0x18,
// value @0x1C. GameMode enum : Campaign=0, PvP=1, MachinesOfWarEvent=15.
const BC_OFF_GAMEMODE_HASVALUE = 0x18;
const BC_OFF_GAMEMODE_VALUE = 0x1C;
// BC.RuleSet est `Nullable<SyncPvpRuleSet>` @0x20. SyncPvpRuleSet enum :
// Deathmatch=0, Heist=1, KingOfTheHill=2, Territories=3, Boosts=4,
// EscortTheSummons=5, Draft=6, Boosts_Infested=7.
const BC_OFF_RULESET_HASVALUE = 0x20;
const BC_OFF_RULESET_VALUE = 0x24;
const BC_OFF_SPAWN_POINT_SET_INDEX = 0x28;
const BC_OFF_PREDEFINED_UNITS = 0x40;
const BC_OFF_PREDEFINED_MACHINES = 0x48;  // List<PredefinedMachinesOfWar>
// PredefinedMachinesOfWar : Id (PlayerId enum int) @+0x10, MachineOfWar
// (PredefinedMachineOfWar wrapper) @+0x18.
const PMOW_OFF_PLAYER_ID = 0x10;
const PMOW_OFF_MACHINE = 0x18;
// PredefinedMachineOfWar : UnitId (string) @+0x10.
const PMOW_OFF_UNIT_ID = 0x10;
const BC_OFF_BOARD = 0x68;
const BC_OFF_UNITS = 0x80;       // List<UnitConfiguration>
const BC_OFF_TILES = 0x88;       // List<BattleConfigTileConfiguration>
// #10022-r1 : etait 0xE7 — c'est `DisableRandomness`, pas `RandomizeAiInput`. Voir la table
// des neuf booleens en tete de fichier. En ECRITURE, l'octet fautif figeait le seed de la
// bataille au lieu de randomiser l'ordre d'activation IA.
const BC_OFF_RANDOMIZE_AI = 0xE8;

const LIST_OFF_ITEMS = 0x10;
const LIST_OFF_SIZE = 0x18;

const ARRAY_OFF_LEN = 0x18;
const ARRAY_OFF_DATA = 0x20;

const PU_OFF_ID = 0x10;
const PU_OFF_UNITS = 0x18;

const PUNIT_OFF_UNIT_ID = 0x10;
const PUNIT_OFF_REMAINING_HP = 0x18; // Nullable<int>: {hasValue@0x10?, value@0x14?} — confirm at runtime
const PUNIT_OFF_MAX_HP = 0x20;

const UC_OFF_ID = 0x10;
const UC_OFF_VISUAL_ID = 0x18;
const UC_OFF_FACTION = 0x28;
const UC_OFF_HEALTH = 0x38;
const UC_OFF_DAMAGE = 0x50;

const BCBC_OFF_ID = 0x10;        // Board.Id (also at +0x10 on master BoardConfiguration but with different base)
const BCBC_OFF_WIDTH = 0x18;
const BCBC_OFF_HEIGHT = 0x1C;

// --- Helpers ---

/** Resolve the live BattleConfiguration from the amorce-captured campaignGameModeSourcePtr.
 * Si Campaign source absent ou BC null, fallback sur MoW Event source
 * (offset _currentBattle different : 0xF0 vs 0x80). User doit avoir navigué
 * manuellement vers le MoW Event in-game pour que ce dernier soit capturé. */
// Un `_currentBattle` valide DOIT être une `IdunBattle.Configuration.BattleConfiguration`
// (class_get_name -> "BattleConfiguration"). Une source de mode PÉRIMÉE (typiquement une
// source PvP résiduelle après une nav PvP) peut garder à cet offset un objet à moitié
// démonté / pré-désérialisé — `JPropertyKeyedCollection` (JSON Newtonsoft), PAS une BC.
// Sans ce garde, la priorité PvP masquait une BC campagne VALIDE avec ce JObject stale ->
// `buildRunner` passait un non-BC à `Initialize` -> lecture de champs BC à des offsets
// faux -> access violation « system error » (crash opaque, diag: runner_init_threw
// step=initialize configKlass=JPropertyKeyedCollection). On type-check par NOM de classe
// (robuste, sur l'objet runtime, sans dépendre d'une résolution de classe au load).
function isBattleConfig(bc: NativePointer): boolean {
    try {
        const klass = bc.readPointer();
        if (klass.isNull()) return false;
        return cstr(class_get_name(klass) as NativePointer) === "BattleConfiguration";
    } catch { return false; }
}

/** Lit `src._currentBattle` (offset `off`) et ne le rend QUE si c'est une BattleConfiguration
 *  valide. Un candidat non-BC (source stale) est signalé et rejeté (jamais rendu) -> on tombe
 *  sur la source suivante. */
function readCurrentBattleIfValid(
    src: NativePointer, off: number, tag: string,
): NativePointer | null {
    try {
        const bc = src.add(off).readPointer();
        if (bc.isNull()) return null;
        if (isBattleConfig(bc)) return bc;
        let kn = "?";
        try { kn = cstr(class_get_name(bc.readPointer()) as NativePointer); } catch { /* */ }
        log(`[battle-config] getLiveBattleConfig: ${tag} _currentBattle n'est pas une `
            + `BattleConfiguration (classe=${kn}) -> source stale ignorée`);
        return null;
    } catch { return null; }
}

export function getLiveBattleConfig(): NativePointer | null {
    // ⚠ LA SOURCE RÉELLEMENT MONTÉE PASSE AVANT TOUTES LES SOURCES CAPTURÉES, ET C'EST UN
    // CORRECTIF, PAS UN CONFORT. Les trois candidats ci-dessous sont des sources CAPTURÉES au
    // vol (amorce, hooks de ctor) : aucune ne connaît `SandboxGameModeSource`. Mesuré le
    // 2026-08-22 -- un onslaught `Waves_Imperial_22` MONTÉ et tournant, et `getLiveBattleConfig`
    // rendait la BC `Campaign1_06` / board `C1_01` d'une source qui ne jouait plus.
    //
    // ⚠ CE QUI REND LA PANNE INVISIBLE : la BC périmée est PARFAITEMENT LISIBLE. Elle porte un
    // `Id`, un board, ses templates -- `inspectBattleConfig` la décrit sans broncher, et une
    // mutation appliquée dessus rend `relu: true` sans avoir le moindre effet. Le type-guard
    // ci-dessous ne peut rien contre ça : l'objet EST une `BattleConfiguration` valide, elle
    // n'est simplement plus celle qu'on joue. Seule la source montée le sait.
    const bcMontee = bcDeLaSourceMontee();
    if (bcMontee !== null && isBattleConfig(bcMontee)) return bcMontee;

    // Priorité : Pvp > MoW Event > Campaign. Quand l'user navigue vers un mode plus avancé
    // (PvP, MoW), on veut sa BC en priorité (plus riche : RuleSet, MoW ammo, templates :pvp).
    // CHAQUE candidat est TYPE-GUARDÉ (BattleConfiguration) : une source stale d'un mode
    // supérieur ne peut plus masquer une BC valide d'un mode inférieur.
    const pSrc = getPvpGameModeSourcePtr();
    if (pSrc !== null) {
        const bc = readCurrentBattleIfValid(pSrc, PVP_OFF_CURRENT_BATTLE, "PvP");
        if (bc !== null) return bc;
    }
    const mSrc = getMowEventGameModeSourcePtr();
    if (mSrc !== null) {
        const bc = readCurrentBattleIfValid(mSrc, MOWE_OFF_CURRENT_BATTLE, "MoW");
        if (bc !== null) return bc;
    }
    const cSrc = getCampaignGameModeSourcePtr();
    if (cSrc !== null) {
        const bc = readCurrentBattleIfValid(cSrc, CGMS_OFF_CURRENT_BATTLE, "Campaign");
        if (bc !== null) return bc;
    }
    return null;
}

/** Read a managed `List<T>` of reference-type elements. Returns the raw
 * Il2CppArray pointer + element count. Element i lives at `arrayPtr + 0x20 + i*8`
 * (already-typed reference). Returns null if the list itself is null. */
function readManagedList(
    listPtr: NativePointer,
): { array: NativePointer; size: number } | null {
    if (listPtr.isNull()) return null;
    try {
        const items = listPtr.add(LIST_OFF_ITEMS).readPointer();
        const size = listPtr.add(LIST_OFF_SIZE).readS32();
        if (items.isNull() || size < 0 || size > 10000) return null;
        return { array: items, size };
    } catch { return null; }
}

function readListItem(
    listInfo: { array: NativePointer; size: number }, i: number,
): NativePointer {
    return listInfo.array.add(ARRAY_OFF_DATA + i * Process.pointerSize)
        .readPointer();
}

// --- Inspection RPC ---

interface BattleConfigSnapshot {
    ok: boolean;
    bcPtr?: string;
    id?: string | null;
    /** GameMode enum value (Campaign=0, PvP=1, ..., MoWEvent=15). null si Nullable.hasValue=false. */
    gameMode?: number | null;
    /** SyncPvpRuleSet enum value (Deathmatch=0, Heist=1, ...). null si Nullable.hasValue=false. */
    ruleSet?: number | null;
    spawnPointSetIndex?: number;
    randomizeAiInput?: boolean;
    board?: {
        ptr: string;
        id: string | null;
        width: number;
        height: number;
    };
    palette?: { tileTypeCount: number };
    templates?: {
        unitTemplateCount: number;
        sample: Array<{ id: string | null; visualId: string | null;
                        faction: string | null; health: number }>;
    };
    predefinedUnits?: Array<{
        playerId: number;
        unitCount: number;
        units: Array<{ unitId: string | null }>;
    }>;
    /** List<PredefinedMachinesOfWar> — MoW à deployer auto par
     * runner.Initialize(). Souvent vide en mode Campaign (qui hardcode
     * SupportsMachinesOfWar=false → le GameModeSource ne peuple pas). */
    predefinedMachines?: Array<{
        playerId: number;
        unitId: string | null;
    }>;
    err?: string;
}

function inspectBattleConfig(): BattleConfigSnapshot {
    const bc = getLiveBattleConfig();
    if (bc === null) {
        return {
            ok: false,
            err: "no live BattleConfiguration — amorce not run OR " +
                 "LoadBattle hasn't fired yet (amorce retreats too early?)",
        };
    }

    const snap: BattleConfigSnapshot = { ok: true, bcPtr: bc.toString() };

    try {
        snap.id = readIl2cppString(bc.add(BC_OFF_ID).readPointer());
        // Nullable<GameMode>/Nullable<SyncPvpRuleSet> : hasValue @+0, value @+4
        snap.gameMode = bc.add(BC_OFF_GAMEMODE_HASVALUE).readU8() !== 0
            ? bc.add(BC_OFF_GAMEMODE_VALUE).readS32() : null;
        snap.ruleSet = bc.add(BC_OFF_RULESET_HASVALUE).readU8() !== 0
            ? bc.add(BC_OFF_RULESET_VALUE).readS32() : null;
        snap.spawnPointSetIndex = bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).readS32();
        snap.randomizeAiInput = bc.add(BC_OFF_RANDOMIZE_AI).readU8() !== 0;
    } catch (e) {
        snap.err = `header read: ${(e as Error).message}`;
    }

    // Board
    try {
        const board = bc.add(BC_OFF_BOARD).readPointer();
        if (!board.isNull()) {
            snap.board = {
                ptr: board.toString(),
                id: readIl2cppString(board.add(BCBC_OFF_ID).readPointer()),
                width: board.add(BCBC_OFF_WIDTH).readS32(),
                height: board.add(BCBC_OFF_HEIGHT).readS32(),
            };
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | board: ${(e as Error).message}`;
    }

    // Tiles palette
    try {
        const tiles = readManagedList(bc.add(BC_OFF_TILES).readPointer());
        if (tiles) snap.palette = { tileTypeCount: tiles.size };
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | tiles: ${(e as Error).message}`;
    }

    // Unit templates (with a small sample to verify offsets)
    try {
        const units = readManagedList(bc.add(BC_OFF_UNITS).readPointer());
        if (units) {
            const sample = [];
            // Bumped to 30 to find MoW/PvP-suffixed templates.
            const N = Math.min(units.size, 200);
            for (let i = 0; i < N; i++) {
                const uc = readListItem(units, i);
                if (uc.isNull()) continue;
                sample.push({
                    id: readIl2cppString(uc.add(UC_OFF_ID).readPointer()),
                    visualId: readIl2cppString(
                        uc.add(UC_OFF_VISUAL_ID).readPointer()),
                    faction: readIl2cppString(
                        uc.add(UC_OFF_FACTION).readPointer()),
                    health: uc.add(UC_OFF_HEALTH).readS32(),
                });
            }
            snap.templates = {
                unitTemplateCount: units.size,
                sample,
            };
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | templates: ${(e as Error).message}`;
    }

    // PredefinedMachines (MoW deployment list)
    try {
        const pm = readManagedList(
            bc.add(BC_OFF_PREDEFINED_MACHINES).readPointer());
        if (pm) {
            const mows: Array<{ playerId: number; unitId: string | null }> = [];
            for (let i = 0; i < pm.size; i++) {
                const entry = readListItem(pm, i);
                if (entry.isNull()) continue;
                const playerId = entry.add(PMOW_OFF_PLAYER_ID).readS32();
                let unitId: string | null = null;
                try {
                    const machinePtr = entry.add(PMOW_OFF_MACHINE).readPointer();
                    if (!machinePtr.isNull()) {
                        unitId = readIl2cppString(
                            machinePtr.add(PMOW_OFF_UNIT_ID).readPointer());
                    }
                } catch { /* leave null */ }
                mows.push({ playerId, unitId });
            }
            snap.predefinedMachines = mows;
        } else {
            snap.predefinedMachines = [];
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | predefMachines: ${(e as Error).message}`;
    }

    // PredefinedUnits (composition per player)
    try {
        const pu = readManagedList(bc.add(BC_OFF_PREDEFINED_UNITS).readPointer());
        if (pu) {
            const players: BattleConfigSnapshot["predefinedUnits"] = [];
            for (let i = 0; i < pu.size; i++) {
                const grp = readListItem(pu, i);
                if (grp.isNull()) continue;
                const playerId = grp.add(PU_OFF_ID).readS32();
                const unitsList = readManagedList(
                    grp.add(PU_OFF_UNITS).readPointer());
                const units: Array<{ unitId: string | null }> = [];
                if (unitsList) {
                    for (let j = 0; j < unitsList.size; j++) {
                        const pUnit = readListItem(unitsList, j);
                        if (pUnit.isNull()) continue;
                        units.push({
                            unitId: readIl2cppString(
                                pUnit.add(PUNIT_OFF_UNIT_ID).readPointer()),
                        });
                    }
                }
                players.push({
                    playerId,
                    unitCount: unitsList?.size ?? 0,
                    units,
                });
            }
            snap.predefinedUnits = players;
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | predef: ${(e as Error).message}`;
    }

    return snap;
}

// --- Patch / mutation API ---
//
// A `BattleConfigPatch` describes a set of in-place mutations to apply to
// the next BattleConfiguration assembled by LoadBattle. Stored in module
// state via `setBattleConfigPatch`; applied automatically by the
// LoadBattle.onLeave hook on CampaignGameModeSource. `consumeOnce` (default
// true) auto-clears the patch after a single application so a subsequent
// human-driven battle isn't accidentally affected.

interface UnitStatsOverride {
    health?: number;
    damage?: number;
    armor?: number;        // legacy Armor field (Idun)
    fixedArmor?: number;
    shield?: number;
    movement?: number;
    range?: number;
    critChance?: number;
    critDamage?: number;
    blockChance?: number;
    blockDamage?: number;
}

interface BattleConfigPatch {
    /** Replace all AI units (PredefinedUnits[0].Units). Must match current
     * count — list resizing not implemented yet. Format: "unitId:level"
     * e.g., "necroNpc1Warrior:6". */
    aiUnits?: string[];
    /** Or: replace specific AI unit slots by index. Same format as aiUnits. */
    aiUnitsAt?: Record<number, string>;
    /** Override stats on unit templates by their Id. Affects ALL spawned
     * instances of that unit. Useful for normalizing power level (RL D3 baseline). */
    templateOverrides?: Record<string, UnitStatsOverride>;
    /** Toggle the BattleConfiguration.RandomizeAiInput flag. */
    randomizeAi?: boolean;
    /** Set the spawn-point preset index (each board has 1-N presets). */
    spawnPointSetIndex?: number;
    /** Le calendrier de vagues -- `BC.UnitSpawningOverTime.Tiers`, forme
     *  `{ "<tour>": { "<playerId>": <Wave> } }`.
     *
     *  ⚠ APPLIQUÉ AU `LoadBattle.onLeave`, DONC SUR LA BC QUE LA SOURCE VIENT DE PRODUIRE, en
     *  mémoire -- aucune sérialisation, aucune substitution. C'est le seul moment où le
     *  calendrier est encore modifiable : `OperationProcessor$$AddPlayer(..., spawnsPerTurn,
     *  ...)` le transcrit dans le `PlayerComponent` au SETUP, et ne le relit jamais.
     *
     *  ⚠ LES VALEURS QUI MARCHENT SE LISENT SUR UNE BC PRODUITE PAR LE JEU (un onslaught en
     *  porte six). Mesuré le 2026-08-22 : `SpawnPointTag` vaut `"defaultGroup"` -- et il ne
     *  s'apparie à AUCUN `Tag` du board, dont les 17 points portent la chaîne vide. C'est une
     *  clé de CONVENTION du moteur, pas une référence au plateau : la « dériver du board » est
     *  un raisonnement faux qui se donne l'air rigoureux. `Index` est incrémenté d'une vague à
     *  l'autre (0,1,2,…), pas remis à zéro. */
    unitSpawningOverTime?: unknown;
    /** Compagnons de `Tiers` dans le nœud, conservés à leur valeur par défaut sauf demande. */
    useAtomicGroup?: boolean;
    useSpawnPointFromUnitIndex?: boolean;
    /** Les abilities d'ENVIRONNEMENT à INSTALLER -- `BC.EnvironmentAbilities`, le RÉCEPTACLE,
     *  et surtout PAS le catalogue `BC.Abilities.EnvironmentAbilities` (166 définitions).
     *
     *  `abilityType` est un ordinal de `IdunBattle.Entities.Enum.TriggeredAbilityType`, `niveau`
     *  choisit dans les tableaux de variables de la config (0 = le natif n'arme rien).
     *
     *  ⚠ CE QUI DÉCIDE DE LA CIBLE EST LE `CreateTrigger` DE L'ABILITY, PAS UN ARGUMENT D'ICI --
     *  il n'existe aucun champ « équipe » à passer. Mesuré au décompilé sur `t6dpr4k06g` :
     *    `EnvReinforcementShield` (1270) = `On(UnitAdded) | On(InitialMatchUnitAdded)`
     *        `AND IsHero(Actor) AND IsInTeam(Actor, 1)` -> l'équipe du JOUEUR (`TeamId=1`,
     *        `playerId=11`, `PlayerType=0` dans `BC.Player.Players`) ;
     *    `EnvStartProtection` (1280) = `On(TurnStart_EffectActivation)` gardé par
     *        `TotalTurnsFinished == <const>`, cible `_allAliveUnits - _currentTurnUnits`,
     *        donc le camp qui NE joue PAS -- team-agnostique, et pas forcément le tien. */
    environmentAbilities?: Array<{ abilityType: number; niveau: number }>;
    /** Les DÉFINITIONS à poser dans le CATALOGUE -- `BC.Abilities.EnvironmentAbilities`, le
     *  dictionnaire à clé CHAÎNE, et surtout PAS `env.AbilitiesConfigurations` (clé de type
     *  valeur, dont l'insertion à la main a tué le process le 2026-08-21).
     *
     *  Deux usages, tous deux mesurés :
     *    * DOTER une ability qui n'a aucune config ici -- sans quoi son premier
     *      `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` LÈVE, et ça remonte
     *      en « system error » au cast ou au déploiement (#254) ;
     *    * CHANGER une constante existante -- ex. `EnhancementDamageBoost.extraDmgPct` de `20`
     *      à `-100`, qui met les dégâts de la cible à ZÉRO (multiplicateur `1 + pct/100`, borné
     *      à zéro en dessous de -100).
     *
     *  ⚠ Les valeurs sont des CHAÎNES, comme dans la BC (`{"extraDmgPct": "-100"}`).
     *
     *  ⚠ LA CLÉ EST UN ORDINAL, PAS UN NOM, et ce n'est pas un choix de confort : le
     *  dictionnaire du catalogue est keyé par un `TriggeredAbilityConfigId` (un TYPE VALEUR --
     *  le JSON le fait passer pour une chaîne), donc on ne l'écrit pas soi-même. On passe par
     *  `AbilitiesConfiguration$$AddEnvironmentAbility(TriggeredAbilityType, …)`, qui prend un
     *  ENUM PLAT et fabrique la clé lui-même.
     *
     *  ⚠ CONSÉQUENCE : les VARIANTES sont hors d'atteinte. `EnhancementAddTrait:Stationary` est
     *  un `TriggeredAbilityType` PLUS un `VariantId`, et l'ordinal seul ne l'exprime pas. Les 106
     *  variantes restent joignables par la voie SEED BC (Newtonsoft y construit les clés), pas
     *  par ce patch. `nom` est purement DÉCORATIF -- il n'entre dans aucune clé. */
    environmentAbilityConfigs?: Array<{ abilityType: number; nom?: string;
                                        constants?: Record<string, string>;
                                        variables?: Record<string, string[]> }>;
    /** Les ENHANCEMENTS -- la SECONDE liste du réceptacle, et la SEULE qui cible par unité NOMMÉE.
     *
     *  `environmentAbilities` (ci-dessus) installe des abilities dont la cible est écrite dans
     *  leur `CreateTrigger` : rien à passer. Une entrée d'enhancement porte, elle, une liste
     *  `Targets` d'`unitId` que `IdunBattleLogic.Entities.DSLTriggers$$IsEnhancementTarget`
     *  confronte -- c'est l'équivalent du `unitAmount` de l'UI d'incursion, et `stack` celui de
     *  son `stacks`. Le catalogue de la BC porte **106** variantes `EnhancementAddTrait:<Trait>`
     *  déjà configurées, dont le gameconfig n'en expose que quatre.
     *
     *  ⚠ Une ability gardée par `IsEnhancementTarget` sans `cibles` ne tire JAMAIS -- le retour
     *  le DIT (`note`) plutôt que de le laisser deviner. */
    environmentEnhancements?: Array<envAbilities.SpecEnhancement>;
    // ⛔ `playerTeamIds` ET `spawnGroupPlayerIndexes` ONT ÉTÉ RETIRÉS (2026-08-23), 327 lignes.
    //
    // Ils réécrivaient `BC.Player.Players[].TeamId` (par parcours du dictionnaire ET de l'arbre
    // rouge-noir d'un `SortedDictionary`) et `Board.SpawnPointSets[].SpawnPointGroups[]
    // .TeamWithPlayerIndex`, pour contourner « le camp adverse disparaît quand on inverse les
    // équipes ».
    //
    // ⚠ CE SYMPTÔME N'ÉTAIT PAS LE LEUR. Mesuré et clos par #10046 : inverser les `TeamId`
    // FONCTIONNE côté natif -- les cinq abandons muets de la pose sont négatifs et les 10 unités
    // montent. La disparition venait d'une COLLISION DE TUILES causée par un `TWPI 0` codé en dur
    // dans `rl_duel.py`, donc du HARNAIS. Deux mécanismes de contournement sont donc restés
    // armés sans cible, avec leur propre piège d'idempotence (« appliqué deux fois, ça se
    // défait ») et un parcours d'arbre rouge-noir à borne dure sur le thread principal du jeu.
    //
    // Ce qu'ils visaient reste atteignable, et plus simplement : `turnOrder` ci-dessous pour le
    // camp que protège `EnvStartProtection`, et `environmentEnhancements` ci-dessus pour viser
    // des unités NOMMÉES sans toucher à aucune équipe.
    // Détail : `docs/rl/case-10046-pose-des-unites-predefinies.md` §5ter.
    /** L'ORDRE DES TOURS -- `BC.Player.TurnOrder`, une `List<PlayerId>` RÉORDONNÉE EN PLACE.
     *  `[12, 11, 13]` = « l'ennemi ouvre, puis le joueur, puis l'environnement ».
     *
     *  ⚠ **C'EST LE LEVIER DU BOUCLIER D'ENVIRONNEMENT**, et le seul. `EnvStartProtection` (1280)
     *  cible `_allAliveUnits - _currentTurnUnits` au tout premier `TurnStart_EffectActivation`
     *  (gardé par `TotalTurnsFinished == 0`) : elle protège **le camp qui N'OUVRE PAS**. Le défaut
     *  `[11, 12, 13]` fait donc ouvrir le joueur, dont les unités sont exactement celles
     *  qu'exclut la soustraction — mesuré le 2026-08-22 en bataille réelle, où les 7 boucliers de
     *  500 sont allés à l'adversaire. Mettre `12` en tête retourne la soustraction.
     *
     *  ⚠ **Ne PAS chercher à corriger ça par les ÉQUIPES** : le ciblage de cette ability est
     *  team-agnostique (aucun `IsInTeam`), donc `playerTeamIds` n'y change RIEN. La seule ability
     *  qui vise nommément l'équipe du joueur, `EnvReinforcementShield` (1270), a **0 occurrence
     *  dans le gameconfig** (re-mesuré le 2026-08-23) : elle est hors d'atteinte sur ce client.
     *
     *  ⚠ **PERMUTATION SEULEMENT.** L'écriture refuse si la longueur diffère ou si les valeurs
     *  demandées ne sont pas un réarrangement de celles déjà présentes — on ne crée pas un
     *  `playerId` qui n'existe pas, et on ne redimensionne pas la liste. Ce contrôle sert AUSSI
     *  d'auto-validation de la disposition : si le pas de lecture était faux, on lirait du bruit
     *  au lieu d'une permutation, et l'écriture serait refusée au lieu de corrompre la liste. */
    turnOrder?: number[];
    /** If true (default), the patch is cleared after a single application. */
    consumeOnce?: boolean;
}

interface PatchApplyResult {
    ok: boolean;
    appliedAt: string;            // ISO timestamp
    bcPtr: string;
    operations: string[];         // human-readable log of what was changed
    warnings: string[];
}

let pendingPatch: BattleConfigPatch | null = null;
let lastApply: PatchApplyResult | null = null;

// Extra UnitConfiguration offsets used only by patch (read-only ones are
// already declared above for inspectBattleConfig).
const UC_OFF_ARMOR = 0x44;       // legacy Armor (Idun-only, Obsolete)
const UC_OFF_FIXED_ARMOR = 0x48;
const UC_OFF_SHIELD = 0x4C;
const UC_OFF_MOVEMENT = 0x54;
const UC_OFF_RANGE = 0x5C;
const UC_OFF_CRIT_CHANCE = 0x60;
const UC_OFF_CRIT_DAMAGE = 0x64;
const UC_OFF_BLOCK_CHANCE = 0x68;
const UC_OFF_BLOCK_DAMAGE = 0x6C;

// --- LE CALENDRIER DE VAGUES, ÉCRIT DANS LA BC ---------------------------------------------
//
// ⚠ FOYER UNIQUE. `bcWaveSet` (wave-inject.ts) et le patch `LoadBattle.onLeave` écrivent tous
// deux `BC.UnitSpawningOverTime` ; deux implémentations dériveraient, et celle qui ne sert pas
// pourrirait en silence. Le champ se résout PAR NOM sur la classe de l'objet — les offsets en
// dur de ce fichier valent chacun pour UNE classe, en appliquer un à une autre lirait un champ
// voisin et rendrait un pointeur plausible.
//
// ⚠ ON DÉSÉRIALISE L'OBJET ENTIER PLUTÔT QUE DE LE CONSTRUIRE. `Tiers` est un
// `Dictionary<Int32, Dictionary<PlayerId, Wave>>` : le bâtir à la main exigerait de boxer des
// clés de type valeur, ce qui a déjà tué le process le 2026-08-21 sur
// `EnvironmentAbilities.AbilitiesConfigurations`. Newtonsoft convertit les clés JSON (chaînes)
// vers `Int32` — c'est la forme que le jeu SÉRIALISE lui-même, on la lui rend telle quelle.
export interface EcritureCalendrier {
    ok: boolean;
    offset?: string;
    noeudAvant?: string;
    noeudApres?: string;
    relu?: boolean;
    octetsJson?: number;
    error?: string;
}

export function ecrireCalendrierDeVagues(
    bc: NativePointer, tiers: unknown,
    opts?: { useAtomicGroup?: boolean; useSpawnPointFromUnitIndex?: boolean },
): EcritureCalendrier {
    let klass: NativePointer;
    try { klass = bc.readPointer(); } catch (e) {
        return { ok: false, error: "classe de la BC illisible : " + (e as Error).message };
    }
    if (klass.isNull()) return { ok: false, error: "la BC porte une classe NULLE" };
    let nomClasse: string;
    try { nomClasse = cstr(class_get_name(klass) as NativePointer); }
    catch (e) { return { ok: false, error: "nom de classe illisible : " + (e as Error).message }; }
    if (nomClasse !== "BattleConfiguration") {
        return {
            ok: false,
            error: "l'objet est un `" + nomClasse + "`, pas une `BattleConfiguration` -- écrire "
                + "dedans corromprait un objet d'un autre type",
        };
    }
    let off = -1;
    for (const nom of ["UnitSpawningOverTime", "<UnitSpawningOverTime>k__BackingField"]) {
        off = getFieldOffset(klass, nom);
        if (off >= 0) break;
    }
    if (off < 0) {
        return {
            ok: false,
            error: "`BattleConfiguration.UnitSpawningOverTime` ABSENT sous ses deux écritures "
                + "connues -- chemin PÉRIMÉ sur ce build",
        };
    }
    let avant: string;
    try { avant = bc.add(off).readPointer().toString(); }
    catch (e) { return { ok: false, error: "lecture du champ : " + (e as Error).message }; }

    if (!isDeserializerReady()) {
        return {
            ok: false,
            error: "`JsonConvert.DeserializeObject` non résolu -- le nœud ne peut pas être "
                + "construit sans lui, et je ne le fabrique pas à la main",
        };
    }
    const kUso = findClassAnywhere("IdunBattle.Configuration",
                                   "UnitSpawningOverTimeConfiguration");
    if (!kUso) {
        return {
            ok: false,
            error: "classe `IdunBattle.Configuration.UnitSpawningOverTimeConfiguration` "
                + "introuvable -- chemin PÉRIMÉ sur ce build",
        };
    }
    const json = JSON.stringify({
        Tiers: tiers,
        UseAtomicGroup: opts?.useAtomicGroup ?? false,
        UseSpawnPointFromUnitIndex: opts?.useSpawnPointFromUnitIndex ?? false,
    });
    let noeud: NativePointer;
    try { noeud = deserializeFromJson(json, kUso); }
    catch (e) {
        return {
            ok: false,
            error: "désérialisation d'`UnitSpawningOverTimeConfiguration` : "
                + (e as Error).message,
        };
    }
    if (noeud.isNull()) {
        return { ok: false, error: "nœud désérialisé en NUL -- rien n'a été écrit" };
    }
    // ⚠ ENRACINER AVANT D'ÉCRIRE : le GC d'IL2CPP ne voit pas notre référence JS, et un objet
    // frais peut être collecté entre sa création et l'écriture du champ.
    gcRoot.add(noeud);
    try { bc.add(off).writePointer(noeud); }
    catch (e) { return { ok: false, error: "écriture du champ : " + (e as Error).message }; }
    let apres: string;
    try { apres = bc.add(off).readPointer().toString(); } catch { apres = "?"; }
    return {
        ok: true, offset: "+0x" + off.toString(16), noeudAvant: avant, noeudApres: apres,
        relu: apres === noeud.toString(), octetsJson: json.length,
    };
}

// ---------------------------------------------------------------------------------------
// LES ABILITIES D'ENVIRONNEMENT -- INSTALLER, ET SAVOIR SI ELLES SONT INSTALLABLES.
//
// DEUX CHAMPS PORTENT CE NOM, ET LES CONFONDRE EST LE PIEGE :
//
//   `BattleConfiguration.EnvironmentAbilities`        <- le RECEPTACLE : ce qui est INSTALLE
//   `BattleConfiguration.Abilities.EnvironmentAbilities` <- le CATALOGUE : 166 DEFINITIONS
//
// Le premier dit « cette bataille joue ces abilities-la » ; le second dit « voici a quoi
// ressemble chacune ». Un grep de la BC trouve un nom dans le SECOND et fait croire au PREMIER
// -- c'est la mesure du 2026-08-22 sur `EnvEndBombardment`, trouve TROIS fois dans une BC dont
// la liste des installees etait VIDE.
//
// ⚠ ET LE CATALOGUE EST UNE CONDITION QUI N'EMET AUCUN SIGNAL, exactement comme le `UnitId`
// d'une vague (cf. `unitSpawningOverTime` ci-dessus) : `EnvReinforcementShield` est ABSENT du
// catalogue de `data/seed-bc.json` (166 entrees), alors que `EnvStartProtection` y est avec son
// `shieldHp: 500`. On PUBLIE donc, pour chaque ability demandee, si son nom est au catalogue --
// pour qu'un echec ait un NOM AVANT d'etre observe, au lieu de trois causes accusees a tort.
export interface EcritureEnvironnement {
    ok: boolean;
    offset?: string;
    noeudAvant?: string;
    noeudApres?: string;
    relu?: boolean;
    /** Ce qui est REELLEMENT dans le receptacle -- compte des membres, pas un « configure ». */
    installees?: Record<string, unknown>;
    /** FUSION dans le receptacle de la progression, ou receptacle NEUF. Les deux n'ont pas les
     *  memes consequences : la seconde jetterait ce que le mode avait pose. */
    voie?: string;
    /** Le nombre de definitions du catalogue. `null` = pas lu. Un catalogue a 0 et un catalogue
     *  a 166 ne racontent pas la meme histoire quand rien n'apparait en bataille. */
    tailleCatalogue?: number | null;
    detail?: Array<Record<string, unknown>>;
    /** La SECONDE liste, quand on lui a demandé quelque chose. Séparée de `detail` : les deux
     *  listes ne ciblent pas pareil, les confondre dans un même tableau les ferait lire pareil. */
    detailEnhancements?: Array<Record<string, unknown>>;
    error?: string;
}

/** Le nom d'une ability est-il au CATALOGUE de cette BC ?
 *
 *  Tri-etat : `null` = PAS MESURE, jamais rendu comme un `false` -- « absent » et « pas
 *  regarde » n'autorisent pas la meme conclusion.
 *
 *  ⚠ CETTE SONDE A MENTI, ET LA FORME DU MENSONGE EST INSTRUCTIVE. Premiere version : elle
 *  appelait `ContainsKey` avec une chaine managee, SANS verifier le type de cle du
 *  dictionnaire. Mesure du 2026-08-22 : elle a rendu ABSENT pour `EnvStartProtection` alors
 *  que le catalogue vivant le PORTE (166 definitions, verifie en serialisant la BC). Une
 *  reponse UNIFORME sur toutes les entrees est la signature d'une sonde cassee, pas d'un
 *  catalogue vide -- et elle a failli faire accuser le catalogue a la place du vrai defaut.
 *
 *  Le correctif n'est pas un ajustement : c'est un REFUS DE REPONDRE quand la question ne se
 *  pose pas. On lit le type du parametre de `ContainsKey` ; si ce n'est pas `System.String`,
 *  la cle est un type valeur (un `TriggeredAbilityConfigId`, serialise en nom mais pas stocke
 *  comme tel) et l'appel n'a aucun sens -- on rend `null`. */
function catalogueContient(bc: NativePointer, nom: string): boolean | null {
    try {
        const abilities = champPointeur(bc, "Abilities");
        if (estRefus(abilities)) return null;
        const dict = champPointeur(abilities as NativePointer, "EnvironmentAbilities");
        if (estRefus(dict)) return null;
        const d = dict as NativePointer;
        const mHas = findMethodByParamCount(d.readPointer(), "ContainsKey", 1);
        if (!mHas) return null;
        // LE CRAN QUI MANQUAIT : la cle est-elle vraiment une chaine ?
        const kParam = methodParamClass(mHas.info, 0);
        if (!kParam) return null;
        let nomParam: string;
        try { nomParam = cstr(class_get_name(kParam) as NativePointer); } catch { return null; }
        if (nomParam !== "String") return null;
        const r = invokeMethod(mHas.info, d, [createManagedString(nom)]);
        if (r.isNull()) return null;
        // ⚠ `il2cpp_runtime_invoke` BOXE les types valeur : le `bool` est a +0x10, pas au
        // pointeur lui-meme. Le lire au mauvais endroit rendrait un vrai/faux plausible.
        return r.add(0x10).readU8() !== 0;
    } catch { return null; }
}

/** Le nombre de definitions du catalogue -- un FAIT, la ou `catalogueContient` peut se taire.
 *  `null` = pas lu. Publie systematiquement : un catalogue a 0 et un catalogue a 166 ne
 *  racontent pas la meme histoire quand rien n'apparait en bataille. */
function catalogueTaille(bc: NativePointer): number | null {
    try {
        const abilities = champPointeur(bc, "Abilities");
        if (estRefus(abilities)) return null;
        const dict = champPointeur(abilities as NativePointer, "EnvironmentAbilities");
        if (estRefus(dict)) return null;
        const d = dict as NativePointer;
        const off = getFieldOffset(d.readPointer(), "_count");
        return off < 0 ? null : d.add(off).readS32();
    } catch { return null; }
}

// ---------------------------------------------------------------------------------------
// LE CATALOGUE -- `BC.Abilities.EnvironmentAbilities`, ET POURQUOI ON N'Y ECRIT PAS SOI-MEME.
//
// ⚠ LA CLE N'EST PAS UNE CHAINE, ET LE JSON LE FAIT CROIRE. Une BC serialisee montre
// `{"EnvStartProtection": {...}}` -- on lit un nom, on conclut `Dictionary<String, ...>`. FAUX :
// mesure du 2026-08-23 sur une BC `SandboxGameModeSource` vivante, le parametre de `ContainsKey`
// est un `TriggeredAbilityConfigId`. Un `TriggeredAbilityConfigId` SE SERIALISE en nom sans etre
// STOCKE comme tel -- c'est exactement le piege que `catalogueContient` documente depuis le
// 2026-08-22, et il se referme une seconde fois des qu'on veut ECRIRE au lieu de lire.
//
// ⇒ Insertion a la main = boxage d'une cle de type valeur = le geste qui a tue le process le
//   2026-08-21 (`Tacticus.exe.30620.dmp`). ON NE L'ECRIT PAS.
//
// ⚠ LA SORTIE EST QUE LE NATIF A SA PROPRE METHODE, et elle est keyee par un ENUM PLAT :
//
//     IdunBattle.Configuration.AbilitiesConfiguration$$AddEnvironmentAbility(
//         id: IdunBattle.Entities.Enum.TriggeredAbilityType, configuration: AbilityConfiguration)
//     IdunBattle.Configuration.AbilitiesConfiguration$$GetEnvironmentAbility(
//         abilityType: IdunBattle.Entities.Enum.TriggeredAbilityType) -> AbilityConfiguration
//
// Un `int`. C'est le natif qui fabrique le `TriggeredAbilityConfigId`, donc plus rien a boxer.
// Le getter donne en prime une RELECTURE qui ne depend d'aucune convention de cle.
//
// ⚠ IL EXISTE DEUX SURCHARGES A DEUX PARAMETRES (l'autre prend un `TriggeredAbilityConfigId`), et
// `findMethodByParamCount` en choisirait une AU HASARD. On selectionne par le TYPE du premier
// parametre -- se tromper ici ne rend pas un mauvais resultat, ca crashe.
//
// ⚠ CE QUE CETTE VOIE NE SAIT PAS FAIRE : une VARIANTE. `EnhancementAddTrait:Stationary` est un
// `TriggeredAbilityType` PLUS un `VariantId`, et l'enum seul ne peut pas l'exprimer. Les 106
// variantes `EnhancementAddTrait:<Trait>` restent donc joignables par la voie SEED BC (ou
// Newtonsoft construit les cles) et PAS par ce patch. On le DIT au lieu de le laisser decouvrir.
interface EcritureCatalogue {
    ok: boolean;
    /** Le compte du dictionnaire AVANT / APRES -- un fait, pas un « configuré ». */
    tailleAvant?: number | null;
    tailleApres?: number | null;
    detail?: Array<Record<string, unknown>>;
    error?: string;
}

/** La surcharge dont le PREMIER PARAMÈTRE est du type demandé — jamais « la première trouvée ». */
function methodeParTypeDuPremierParam(
    klass: NativePointer, nom: string, nbParams: number, nomTypeAttendu: string,
): { info: NativePointer } | null {
    let k = klass;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
            try {
                if (cstr(method_get_name(m) as NativePointer) !== nom) continue;
                if ((method_get_param_count(m) as number) !== nbParams) continue;
                const kp = methodParamClass(m, 0);
                if (!kp) continue;
                if (cstr(class_get_name(kp) as NativePointer) === nomTypeAttendu) {
                    return { info: m };
                }
            } catch { /* méthode illisible : on passe, on ne devine pas */ }
        }
        break; // pas d'héritage à remonter : la méthode est déclarée sur la classe elle-même
    }
    return null;
}

/** ÉCRIRE des définitions dans le CATALOGUE de la BC — la moitié qui manquait au patch.
 *
 *  Sans elle, `environmentAbilities` pouvait installer une ability dont aucune config n'existe :
 *  le natif lève au premier `GetNumberConstant`, et le patch n'avait qu'un `avertissement` à
 *  offrir. Mesuré sur `EnvAttemptDebuff`, absent des 166 définitions du seed BC.
 *
 *  ⚠ ON ÉCRASE UNE ENTRÉE EXISTANTE SANS RIEN DEMANDER, ET C'EST VOULU : c'est le seul moyen de
 *  changer une constante déjà définie (`EnhancementDamageBoost.extraDmgPct` de `20` à `-100`).
 *  Le retour DIT, par entrée, si elle existait avant — pour qu'un écrasement soit lu, pas subi. */
export function ecrireCatalogueEnvironnement(
    bc: NativePointer,
    entrees: Array<{ abilityType: number; nom?: string; constants?: Record<string, string>;
                     variables?: Record<string, string[]> }>,
): EcritureCatalogue {
    if (!isDeserializerReady()) {
        return { ok: false, error: "`JsonConvert.DeserializeObject` non résolu -- une "
            + "`AbilityConfiguration` ne peut pas être construite" };
    }
    const abilities = champPointeur(bc, "Abilities");
    if (estRefus(abilities)) {
        return { ok: false, error: "`BC.Abilities` : " + (abilities as { error: string }).error };
    }
    const cfgAbilities = abilities as NativePointer;

    const kCfg = findClassAnywhere("IdunBattle.Configuration", "AbilityConfiguration");
    if (!kCfg) {
        return { ok: false, error: "classe `IdunBattle.Configuration.AbilityConfiguration` "
            + "introuvable -- chemin PÉRIMÉ sur ce build" };
    }
    const kAbilities = cfgAbilities.readPointer();
    const mAdd = methodeParTypeDuPremierParam(
        kAbilities, "AddEnvironmentAbility", 2, "TriggeredAbilityType");
    const mGet = methodeParTypeDuPremierParam(
        kAbilities, "GetEnvironmentAbility", 1, "TriggeredAbilityType");
    if (!mAdd) {
        return { ok: false, error: "`AbilitiesConfiguration$$AddEnvironmentAbility(TriggeredAbility"
            + "Type, AbilityConfiguration)` INTROUVABLE -- on ne se replie PAS sur la surcharge à "
            + "`TriggeredAbilityConfigId` : sa clé est un type valeur, et la boxer est le geste "
            + "qui a tué le process le 2026-08-21" };
    }

    // ⚠ `GetEnvironmentAbility` NE SAIT PAS DIRE « ABSENT », ET S'EN SERVIR REND UN VERT VACANT.
    // Mesure du 2026-08-23 : sur `EnvAttemptDebuff`, il rendait NON-NUL *avant* l'écriture alors
    // que le compte du dictionnaire passait de 166 à 167 -- l'entrée n'y était donc pas. Il
    // fabrique un défaut au lieu de rendre `null`. Une vérification bâtie dessus aurait rendu
    // `relu=true` quoi qu'il arrive, y compris si l'insertion avait échoué : c'est le capteur
    // qui confirme l'hypothèse l'ayant fait naître, encore lui.
    //
    // Le seul signal HONNÊTE est le COMPTE du dictionnaire, pris avant et après CHAQUE entrée :
    //   apres > avant  -> entrée NEUVE, réellement insérée
    //   apres == avant -> une entrée existait déjà et vient d'être ÉCRASÉE (le geste voulu quand
    //                     on change une constante) -- ou l'insertion n'a rien fait, et les deux
    //                     sont indistinguables par le compte seul. On le DIT.
    const getterNonNul = (t: number): boolean | null => {
        if (!mGet) return null;
        try {
            const buf = Memory.alloc(4); buf.writeS32(t | 0);
            return !invokeMethod(mGet.info, cfgAbilities, [buf]).isNull();
        } catch { return null; }
    };

    const tailleAvant = catalogueTaille(bc);
    const detail: Array<Record<string, unknown>> = [];
    for (const e of entrees) {
        const nom = e.nom ?? triggeredAbilityName(e.abilityType);
        const compteAvant = catalogueTaille(bc);
        // La forme que le jeu SÉRIALISE lui-même — on la lui rend telle quelle.
        const charge = {
            Variables: e.variables ?? {},
            Constants: e.constants ?? {},
            AttackRangeType: 0,
            VariablesAffectedByUnitRarityMultiplier: [] as number[],
            TutorialAbilityBehaviours: {},
        };
        let cfg: NativePointer;
        try { cfg = deserializeFromJson(JSON.stringify(charge), kCfg); }
        catch (err) {
            return { ok: false, tailleAvant, detail,
                error: "`" + nom + "` : désérialisation de l'`AbilityConfiguration` : "
                    + (err as Error).message };
        }
        if (cfg.isNull()) {
            return { ok: false, tailleAvant, detail,
                error: "`" + nom + "` : l'`AbilityConfiguration` s'est désérialisée en NUL" };
        }
        gcRoot.add(cfg);
        try {
            const buf = Memory.alloc(4); buf.writeS32(e.abilityType | 0);
            invokeMethod(mAdd.info, cfgAbilities, [buf, cfg]);
        } catch (err) {
            return { ok: false, tailleAvant, detail,
                error: "`" + nom + "` : `AddEnvironmentAbility` a LEVÉ : " + (err as Error).message };
        }
        const compteApres = catalogueTaille(bc);
        const neuve = (compteAvant !== null && compteApres !== null)
            ? compteApres > compteAvant : null;
        detail.push({
            abilityType: e.abilityType, nom,
            constants: e.constants ?? {},
            compteAvant, compteApres,
            /** `true` = entrée NEUVE (le compte a monté) · `false` = une entrée existait et a été
             *  ÉCRASÉE, OU rien n'a bougé — le compte seul ne les sépare pas · `null` = pas mesuré. */
            neuve,
            /** ⚠ NE PROUVE RIEN SUR L'ABSENCE : ce getter fabrique un défaut au lieu de rendre
             *  `null` (mesuré le 2026-08-23). Publié pour la lecture, jamais comme verdict. */
            getterNonNul: getterNonNul(e.abilityType),
            note: neuve === false
                ? "compte INCHANGÉ : soit la définition existante a été ÉCRASÉE (le geste voulu "
                  + "pour changer une constante), soit l'insertion n'a rien fait -- le compte ne "
                  + "sépare pas les deux"
                : undefined,
        });
    }
    return { ok: true, tailleAvant, tailleApres: catalogueTaille(bc), detail };
}

/** INSTALLER des abilities d'environnement sur la BC que la source vient de produire.
 *
 *  ⚠ MEME FENETRE QUE LE CALENDRIER DE VAGUES : on ecrit au `LoadBattle.onLeave`, sur l'objet
 *  en memoire, sans aucune serialisation ni substitution.
 *
 *  ⚠ LE RECEPTACLE NE SE CONSTRUIT PAS AU CTOR. `EnvironmentAbilities..ctor` laisse ses trois
 *  membres NULS ; `creerReceptacle` passe par Newtonsoft parce que ces membres sont des
 *  generiques INFLATES, introuvables par leur nom.
 *
 *  ⚠ `AbilitiesConfigurations` reste VIDE, et c'est le choix deja pris par `guild-war-config` :
 *  sa cle est un TYPE VALEUR, et se tromper de convention ne leve pas -- ca CRASHE le jeu
 *  (2026-08-21, `Tacticus.exe.30620.dmp`). L'hypothese est que le CATALOGUE de la BC suffit ;
 *  `catalogueContient` la rend verifiable au lieu de la laisser tacite. */
export function ecrireAbilitesEnvironnement(
    bc: NativePointer, demandes: Array<{ abilityType: number; niveau: number }>,
    enhancements: envAbilities.SpecEnhancement[] = [],
): EcritureEnvironnement {
    let klass: NativePointer;
    try { klass = bc.readPointer(); } catch (e) {
        return { ok: false, error: "classe de la BC illisible : " + (e as Error).message };
    }
    if (klass.isNull()) return { ok: false, error: "la BC porte une classe NULLE" };
    let nomClasse: string;
    try { nomClasse = cstr(class_get_name(klass) as NativePointer); }
    catch (e) { return { ok: false, error: "nom de classe illisible : " + (e as Error).message }; }
    if (nomClasse !== "BattleConfiguration") {
        return {
            ok: false,
            error: "l'objet est un `" + nomClasse + "`, pas une `BattleConfiguration` -- écrire "
                + "dedans corromprait un objet d'un autre type",
        };
    }
    let off = -1;
    for (const nom of ["EnvironmentAbilities", "<EnvironmentAbilities>k__BackingField"]) {
        off = getFieldOffset(klass, nom);
        if (off >= 0) break;
    }
    if (off < 0) {
        return {
            ok: false,
            error: "`BattleConfiguration.EnvironmentAbilities` ABSENT sous ses deux écritures "
                + "connues -- chemin PÉRIMÉ sur ce build",
        };
    }
    let avant: string;
    try { avant = bc.add(off).readPointer().toString(); }
    catch (e) { return { ok: false, error: "lecture du champ : " + (e as Error).message }; }

    // ⚠ ON FUSIONNE, ON NE REMPLACE PAS -- ET C'EST UNE EXIGENCE DU CHEMIN REEL.
    // `CampaignGameModeSource$$LoadBattle` appelle `ApplyEnvironmentAbilitiesFromProgression`
    // AVANT que ce hook ne rende la main (xrefs mesurees : la campagne, l'evenement de
    // campagne, l'amicale, le boss de guilde et la guerre de guilde passent TOUS par la).
    // Ecrire un receptacle neuf jetterait donc en silence les abilities que la progression du
    // joueur vient d'y poser. On REUTILISE celui qui est deja la quand il est utilisable, et on
    // DIT laquelle des deux voies a servi.
    let env: NativePointer;
    let voie: string;
    const existant = (() => {
        try {
            const p = bc.add(off).readPointer();
            if (p.isNull()) return null;
            // Type-garde : on n'ajoute pas dans un objet dont on ne sait pas ce qu'il est.
            const n = cstr(class_get_name(p.readPointer()) as NativePointer);
            return n === "EnvironmentAbilities" ? p : null;
        } catch { return null; }
    })();
    if (existant !== null) {
        env = existant;
        voie = "FUSION dans le réceptacle posé par la progression";
    } else {
        const envR = envAbilities.creerReceptacle();
        if (estRefus(envR)) return { ok: false, error: (envR as { error: string }).error };
        env = envR as NativePointer;
        voie = "réceptacle NEUF (le champ était nul ou d'un autre type)";
    }

    const tailleCatalogue = catalogueTaille(bc);
    const detail: Array<Record<string, unknown>> = [];
    for (const d of demandes) {
        const nom = triggeredAbilityName(d.abilityType);
        const auCatalogue = catalogueContient(bc, nom);
        const pose = envAbilities.ajouterAbility(env, d.abilityType, d.niveau);
        if (estRefus(pose)) {
            return { ok: false, error: "`" + nom + "` : " + (pose as { error: string }).error };
        }
        detail.push({
            abilityType: d.abilityType, nom, niveau: d.niveau,
            arme: pose === true,
            // `false` = le natif n'arme pas non plus a niveau 0 ; ce n'est pas un echec.
            raison: pose === false ? "niveau 0 -- le natif n'arme pas non plus" : undefined,
            auCatalogue,
            avertissement: auCatalogue === false
                ? "ABSENTE du catalogue `Abilities.EnvironmentAbilities` de cette BC ("
                  + tailleCatalogue + " définitions) -- si rien n'apparaît en bataille, c'est "
                  + "la première cause à regarder, et elle n'émettra AUCUNE trace"
                : (auCatalogue === null
                    ? "catalogue NON MESURÉ (clé non-`String` ou dictionnaire illisible) -- "
                      + "cette sonde se TAIT plutôt que de rendre un `absent` qu'elle ne peut "
                      + "pas établir"
                    : undefined),
        });
    }

    // Les ENHANCEMENTS -- la SECONDE liste du réceptacle, celle qui cible par unité NOMMÉE.
    const detailEnh: Array<Record<string, unknown>> = [];
    for (const e of enhancements) {
        const auCatalogue = catalogueContient(bc, e.ability);
        const pose = envAbilities.ajouterEnhancement(env, e);
        if (estRefus(pose)) {
            return { ok: false, error: "`" + e.ability + "` : " + (pose as { error: string }).error };
        }
        detailEnh.push({
            ability: e.ability, niveau: e.niveau ?? 1, playerId: e.playerId ?? null,
            cibles: e.cibles ?? [], stack: e.stack ?? 1,
            // CE QUI EST REELLEMENT ECRIT dans `Targets`, apres scission du suffixe par le mirror
            // de `UnitConfigId$$CreateFromString`. Sans cet écho, un `:6` mal apparié ne se verrait
            // NULLE PART : l'installation resterait `ok` et la liste compterait 1.
            ciblesResolues: (pose as { ciblesResolues?: unknown[] }).ciblesResolues,
            auCatalogue,
            note: (pose as { note?: string }).note,
            avertissement: auCatalogue === false
                ? "ABSENTE du catalogue de cette BC -- son premier `GetNumberConstant` LÈVERA "
                  + "(« system error »). Poser sa config par `environmentAbilityConfigs` AVANT."
                : undefined,
        });
    }

    // La ré-écriture du champ est INUTILE en fusion (l'objet est déjà en place) mais elle est
    // faite quand même : elle est idempotente, et elle donne le `relu` qui atteste.
    try { bc.add(off).writePointer(env); }
    catch (e) { return { ok: false, error: "écriture du champ : " + (e as Error).message }; }
    let apres: string;
    try { apres = bc.add(off).readPointer().toString(); } catch { apres = "?"; }
    return {
        ok: true, offset: "+0x" + off.toString(16), noeudAvant: avant, noeudApres: apres,
        relu: apres === env.toString(), voie, tailleCatalogue,
        // « CONFIGURE » N'EST PAS « INSTALLE » : seul le compte des membres tranche.
        installees: envAbilities.resume(env),
        detail,
        detailEnhancements: detailEnh.length > 0 ? detailEnh : undefined,
    };
}

/** Réordonne `BC.Player.TurnOrder` EN PLACE — c'est le levier du bouclier d'environnement.
 *
 *  ⚠ **PERMUTATION SEULEMENT, et ce refus est aussi l'AUTO-VALIDATION de la disposition.**
 *  `TurnOrder` est une `List<PlayerId>` de structs à 4 octets, donc on lit au pas de 4 — pas au
 *  pas d'un pointeur, comme le fait `readListItem`. Si ce pas était faux, les valeurs lues
 *  seraient du bruit, donc PAS un réarrangement de celles demandées, et l'écriture serait
 *  refusée. Le contrôle métier (« on n'invente pas un `playerId` ») et le contrôle de disposition
 *  (« je lis bien la liste ») sont donc le MÊME test — un capteur qui ne se recoupe avec rien
 *  peut confirmer l'hypothèse qui l'a fait naître (cf. `case-10046` §6bis). */
function ecrireOrdreDesTours(
    bc: NativePointer, ordre: number[],
): { ok: boolean; error?: string; avant?: number[]; apres?: number[]; relu?: boolean } {
    const cfgJoueurs = champPointeur(bc, "Player");
    if (estRefus(cfgJoueurs)) {
        return { ok: false, error: "`BC.Player` : " + (cfgJoueurs as { error: string }).error };
    }
    const listeP = champPointeur(cfgJoueurs as NativePointer, "TurnOrder");
    if (estRefus(listeP)) {
        return { ok: false,
            error: "`BC.Player.TurnOrder` : " + (listeP as { error: string }).error };
    }
    const info = readManagedList(listeP as NativePointer);
    if (info === null) return { ok: false, error: "`TurnOrder` illisible comme `List`" };
    if (info.size !== ordre.length) {
        return { ok: false, error: `\`TurnOrder\` compte ${info.size} entrée(s), l'ordre demandé `
            + `en a ${ordre.length} — on NE REDIMENSIONNE PAS, on permute` };
    }

    const avant: number[] = [];
    try {
        for (let i = 0; i < info.size; i++) {
            avant.push(info.array.add(ARRAY_OFF_DATA + i * 4).readS32());
        }
    } catch (e) {
        return { ok: false, error: `lecture de \`TurnOrder\` impossible : ${e}` };
    }
    const trie = (a: number[]) => a.slice().sort((x, y) => x - y).join(",");
    if (trie(avant) !== trie(ordre)) {
        return { ok: false, error: `REFUS : l'ordre demandé [${ordre.join(",")}] n'est pas une `
            + `permutation de celui lu [${avant.join(",")}]. Soit un \`playerId\` est inventé, `
            + `soit la disposition de la liste a changé sur ce build — dans les deux cas on `
            + `n'écrit RIEN.` };
    }

    for (let i = 0; i < info.size; i++) {
        info.array.add(ARRAY_OFF_DATA + i * 4).writeS32(ordre[i] | 0);
    }
    const apres: number[] = [];
    for (let i = 0; i < info.size; i++) {           // ON RELIT, toujours
        apres.push(info.array.add(ARRAY_OFF_DATA + i * 4).readS32());
    }
    return { ok: true, avant, apres, relu: apres.join(",") === ordre.join(",") };
}

function applyPatchToConfig(
    bc: NativePointer, patch: BattleConfigPatch,
): PatchApplyResult {
    const ops: string[] = [];
    const warnings: string[] = [];

    // Toggle randomize AI
    if (patch.randomizeAi !== undefined) {
        try {
            bc.add(BC_OFF_RANDOMIZE_AI).writeU8(patch.randomizeAi ? 1 : 0);
            ops.push(`randomizeAi=${patch.randomizeAi}`);
        } catch (e) {
            warnings.push(`randomizeAi: ${(e as Error).message}`);
        }
    }

    // Le calendrier de vagues -- MUTATION de la BC produite, jamais une substitution.
    if (patch.unitSpawningOverTime !== undefined && patch.unitSpawningOverTime !== null) {
        const w = ecrireCalendrierDeVagues(bc, patch.unitSpawningOverTime, {
            useAtomicGroup: patch.useAtomicGroup,
            useSpawnPointFromUnitIndex: patch.useSpawnPointFromUnitIndex,
        });
        if (w.ok) {
            const n = typeof patch.unitSpawningOverTime === "object"
                ? Object.keys(patch.unitSpawningOverTime as object).length : 0;
            ops.push(`unitSpawningOverTime=${n} tour(s) @${w.offset} `
                + `(${w.noeudAvant} -> ${w.noeudApres}, relu=${w.relu})`);
        } else {
            warnings.push(`unitSpawningOverTime: ${w.error}`);
        }
    }

    // ⚠ LE CATALOGUE D'ABORD, ET L'ORDRE N'EST PAS COSMÉTIQUE. Une ability installée sans sa
    // définition fait LEVER son premier `GetNumberConstant` ; poser la config APRÈS l'installation
    // laisserait donc une fenêtre où la BC est armée et incohérente. On dote, PUIS on installe.
    if (patch.environmentAbilityConfigs !== undefined && patch.environmentAbilityConfigs !== null
        && patch.environmentAbilityConfigs.length > 0) {
        const w = ecrireCatalogueEnvironnement(bc, patch.environmentAbilityConfigs);
        if (w.ok) {
            const lu = (w.detail ?? []).map((d) =>
                `${d.nom}:${d.neuve === true ? "NEUVE" : (d.neuve === false ? "écrase-ou-inerte"
                    : "non mesurée")}`);
            ops.push(`environmentAbilityConfigs ${lu.join(" ")} `
                + `(catalogue ${w.tailleAvant} -> ${w.tailleApres})`);
            for (const d of w.detail ?? []) {
                // On n'alerte QUE sur ce qu'on ne sait pas mesurer. Un compte inchangé est le
                // régime NORMAL d'un écrasement de constante -- en faire un warning banaliserait
                // le canal, et c'est le canal qui porte les vraies causes muettes.
                if (d.neuve === null) {
                    warnings.push(`environmentAbilityConfigs[${d.nom}]: compte du catalogue NON `
                        + `MESURÉ -- l'insertion n'est ni confirmée ni infirmée`);
                }
            }
        } else {
            warnings.push(`environmentAbilityConfigs: ${w.error}`);
        }
    }

    // Les abilities d'environnement -- MUTATION du même objet, à la même fenêtre.
    // Les DEUX listes du réceptacle passent par le MÊME appel : il n'y a qu'une acquisition du
    // réceptacle (fusion ou neuf), donc pas deux chances d'en créer un second et de jeter le
    // premier.
    const demandesEnv = patch.environmentAbilities ?? [];
    const demandesEnh = patch.environmentEnhancements ?? [];
    if (demandesEnv.length > 0 || demandesEnh.length > 0) {
        const w = ecrireAbilitesEnvironnement(bc, demandesEnv, demandesEnh);
        if (w.ok) {
            const inst = JSON.stringify(w.installees);
            ops.push(`environmentAbilities=${demandesEnv.length} + enhancements=`
                + `${demandesEnh.length} demandée(s) `
                + `@${w.offset} (${w.noeudAvant} -> ${w.noeudApres}, relu=${w.relu}) `
                + `installées=${inst}`);
            // L'absence au catalogue ne fait PAS échouer l'écriture -- elle est ANNONCÉE, parce
            // que c'est une cause qui, sinon, n'émet aucune trace.
            for (const d of w.detail ?? []) {
                if (d.avertissement) warnings.push(`environmentAbilities[${d.nom}]: ${d.avertissement}`);
            }
            for (const d of w.detailEnhancements ?? []) {
                if (d.avertissement) {
                    warnings.push(`environmentEnhancements[${d.ability}]: ${d.avertissement}`);
                }
                if (d.note) warnings.push(`environmentEnhancements[${d.ability}]: ${d.note}`);
            }
        } else {
            warnings.push(`environmentAbilities: ${w.error}`);
        }
    }

    // L'ordre des tours -- le levier du bouclier d'environnement (cf. `turnOrder` en tête).
    if (patch.turnOrder !== undefined && patch.turnOrder !== null) {
        const w = ecrireOrdreDesTours(bc, patch.turnOrder);
        if (w.ok) {
            ops.push(`turnOrder [${(w.avant ?? []).join(",")}] -> [${(w.apres ?? []).join(",")}]`);
            if (w.relu !== true) {
                warnings.push("turnOrder: RELECTURE DIVERGENTE "
                    + `(écrit [${patch.turnOrder.join(",")}], relu [${(w.apres ?? []).join(",")}])`);
            }
        } else {
            warnings.push(`turnOrder: ${w.error}`);
        }
    }

    // SpawnPointSetIndex
    if (patch.spawnPointSetIndex !== undefined) {
        try {
            bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).writeS32(
                patch.spawnPointSetIndex);
            ops.push(`spawnPointSetIndex=${patch.spawnPointSetIndex}`);
        } catch (e) {
            warnings.push(
                `spawnPointSetIndex: ${(e as Error).message}`);
        }
    }

    // Index template by Id, for both AI unit validation and stat overrides.
    const templates = readManagedList(bc.add(BC_OFF_UNITS).readPointer());
    const templatesById = new Map<string, NativePointer>();
    if (templates) {
        for (let i = 0; i < templates.size; i++) {
            const uc = readListItem(templates, i);
            if (uc.isNull()) continue;
            const id = readIl2cppString(uc.add(UC_OFF_ID).readPointer());
            if (id) templatesById.set(id, uc);
        }
    }

    // AI unit swap
    const wantedAiUnits = mergeAiUnitsSpec(patch);
    if (wantedAiUnits !== null) {
        const pu = readManagedList(
            bc.add(BC_OFF_PREDEFINED_UNITS).readPointer());
        if (!pu || pu.size < 1) {
            warnings.push("aiUnits: PredefinedUnits list empty");
        } else {
            // First entry assumed to be the AI player (validated by
            // inspectBattleConfig observation: single group, playerId=12).
            const aiGroup = readListItem(pu, 0);
            const aiUnits = readManagedList(
                aiGroup.add(PU_OFF_UNITS).readPointer());
            if (!aiUnits) {
                warnings.push("aiUnits: AI group's Units list null");
            } else if (wantedAiUnits.length !== aiUnits.size) {
                warnings.push(
                    `aiUnits: count mismatch — spec wants ` +
                    `${wantedAiUnits.length}, current has ${aiUnits.size}. ` +
                    `List resize not implemented; keeping original.`);
            } else {
                // No template validation here — BattleConfiguration.Units
                // holds the PLAYER roster, not AI enemies. AI unit IDs are
                // resolved at spawn time against a global registry (likely
                // GameConfigData). We just write the strings and let the
                // game complain if an ID is genuinely invalid.
                for (let i = 0; i < wantedAiUnits.length; i++) {
                    const pUnit = readListItem(aiUnits, i);
                    if (pUnit.isNull()) continue;
                    const newStr = createManagedString(wantedAiUnits[i]);
                    pUnit.add(PUNIT_OFF_UNIT_ID).writePointer(newStr);
                }
                ops.push(`aiUnits=${wantedAiUnits.length} slots replaced`);
            }
        }
    }

    // Template stat overrides
    if (patch.templateOverrides) {
        for (const [unitId, stats] of Object.entries(patch.templateOverrides)) {
            const uc = templatesById.get(unitId);
            if (!uc) {
                warnings.push(`templateOverrides: unknown unit ${unitId}`);
                continue;
            }
            const changed: string[] = [];
            try {
                if (stats.health !== undefined) {
                    uc.add(UC_OFF_HEALTH).writeS32(stats.health);
                    changed.push(`hp=${stats.health}`);
                }
                if (stats.damage !== undefined) {
                    uc.add(UC_OFF_DAMAGE).writeS32(stats.damage);
                    changed.push(`dmg=${stats.damage}`);
                }
                if (stats.armor !== undefined) {
                    uc.add(UC_OFF_ARMOR).writeS32(stats.armor);
                    changed.push(`armor=${stats.armor}`);
                }
                if (stats.fixedArmor !== undefined) {
                    uc.add(UC_OFF_FIXED_ARMOR).writeS32(stats.fixedArmor);
                    changed.push(`fixedArmor=${stats.fixedArmor}`);
                }
                if (stats.shield !== undefined) {
                    uc.add(UC_OFF_SHIELD).writeS32(stats.shield);
                    changed.push(`shield=${stats.shield}`);
                }
                if (stats.movement !== undefined) {
                    uc.add(UC_OFF_MOVEMENT).writeS32(stats.movement);
                    changed.push(`mv=${stats.movement}`);
                }
                if (stats.range !== undefined) {
                    uc.add(UC_OFF_RANGE).writeS32(stats.range);
                    changed.push(`range=${stats.range}`);
                }
                if (stats.critChance !== undefined) {
                    uc.add(UC_OFF_CRIT_CHANCE).writeS32(stats.critChance);
                    changed.push(`crit%=${stats.critChance}`);
                }
                if (stats.critDamage !== undefined) {
                    uc.add(UC_OFF_CRIT_DAMAGE).writeS32(stats.critDamage);
                    changed.push(`critDmg=${stats.critDamage}`);
                }
                if (stats.blockChance !== undefined) {
                    uc.add(UC_OFF_BLOCK_CHANCE).writeS32(stats.blockChance);
                    changed.push(`block%=${stats.blockChance}`);
                }
                if (stats.blockDamage !== undefined) {
                    uc.add(UC_OFF_BLOCK_DAMAGE).writeS32(stats.blockDamage);
                    changed.push(`blockDmg=${stats.blockDamage}`);
                }
            } catch (e) {
                warnings.push(
                    `templateOverrides ${unitId}: ${(e as Error).message}`);
                continue;
            }
            ops.push(`${unitId}{${changed.join(",")}}`);
        }
    }

    return {
        ok: warnings.length === 0,
        appliedAt: new Date().toISOString(),
        bcPtr: bc.toString(),
        operations: ops,
        warnings,
    };
}

function mergeAiUnitsSpec(patch: BattleConfigPatch): string[] | null {
    if (patch.aiUnits) return patch.aiUnits.slice();
    if (patch.aiUnitsAt) {
        // Need to know current count; we'll merge against existing inside the
        // application logic. Return null here; caller handles the partial case
        // via a separate path. Simpler approach: caller resolves aiUnitsAt
        // into a full-length array using inspectBattleConfig data — but for
        // now treat partial as not supported in v1 of the patch API.
        // TODO: handle partial slot replacement
        return null;
    }
    return null;
}

// --- Spawn helper: materialize PredefinedUnits into runner via AddUnitMessage ---
//
// buildRunner gives us a SKELETON (tiles + match + players) but no Unit
// entities. We need to apply AddUnitMessage(unitId, playerId, col, row) for
// each PredefinedUnit, using the SpawnPointGroup matching the player's team.
//
// Layout reminders:
//   BattleConfiguration.Board.SpawnPointSets : List<SpawnPointSetConfiguration>
//   SpawnPointSetConfiguration.SpawnPointGroups : List<SpawnPointGroupConfiguration>
//   SpawnPointGroupConfiguration:
//     +0x10  TeamWithPlayerIndex (int)
//     +0x14  MachineOfWarPosition
//     +0x18  SpawnPoints : List<SpawnPointConfiguration>
//   SpawnPointConfiguration : BattleConfigPosition
//     +0x10  Column
//     +0x14  Row
//   AddUnitMessage (4-arg ctor): (string unitId, PlayerId, int col, int row)
//     +0x28  SpawnSource (set to Deployment=5 per launch.ts)

const BCBC_OFF_SPAWN_POINT_SETS = 0x28; // BattleConfigBoardConfiguration
const SPS_OFF_SPAWN_GROUPS = 0x10;      // SpawnPointSetConfiguration
const SPG_OFF_TEAM_PLAYER_INDEX = 0x10; // SpawnPointGroupConfiguration
const SPG_OFF_SPAWN_POINTS = 0x18;
const SP_OFF_COL = 0x10;
const SP_OFF_ROW = 0x14;

const addUnitMsgClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Messages", "AddUnitMessage");
const addUnitMsgCtor4 = addUnitMsgClass
    ? findCtorByParamCount(addUnitMsgClass, 4) : null;

function buildAddUnitMessage(
    unitId: string, playerId: number, col: number, row: number,
): NativePointer {
    if (!addUnitMsgClass) throw new Error("AddUnitMessage class not found");
    if (!addUnitMsgCtor4) throw new Error("AddUnitMessage 4-arg ctor not found");
    const msg = il2cpp_object_new(addUnitMsgClass) as NativePointer;
    if (msg.isNull()) throw new Error("il2cpp_object_new(AddUnitMessage) returned null");
    gcRoot.add(msg);
    const unitIdStr = createManagedString(unitId);
    const pidBuf = Memory.alloc(4); pidBuf.writeS32(playerId);
    const colBuf = Memory.alloc(4); colBuf.writeS32(col);
    const rowBuf = Memory.alloc(4); rowBuf.writeS32(row);
    invokeMethod(addUnitMsgCtor4.info, msg, [unitIdStr, pidBuf, colBuf, rowBuf]);
    // SpawnSource = Deployment (5) — matches what the live game writes
    // for pre-battle player placements.
    msg.add(0x28).writeS32(5);
    return msg;
}

/** Read all SpawnPointGroups in the BC's active SpawnPointSet, each with
 * its team-player-index and spawn point coordinates. */
function readAllSpawnGroups(bc: NativePointer): Array<{
    teamWithPlayerIndex: number;
    points: Array<{ col: number; row: number }>;
}> {
    const board = bc.add(BC_OFF_BOARD).readPointer();
    if (board.isNull()) return [];
    const setIdx = bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).readS32();
    const sets = readManagedList(
        board.add(BCBC_OFF_SPAWN_POINT_SETS).readPointer());
    if (!sets || setIdx < 0 || setIdx >= sets.size) return [];
    const set = readListItem(sets, setIdx);
    const groups = readManagedList(set.add(SPS_OFF_SPAWN_GROUPS).readPointer());
    if (!groups) return [];
    const out = [];
    for (let g = 0; g < groups.size; g++) {
        const grp = readListItem(groups, g);
        if (grp.isNull()) continue;
        const tpi = grp.add(SPG_OFF_TEAM_PLAYER_INDEX).readS32();
        const spawnPts = readManagedList(
            grp.add(SPG_OFF_SPAWN_POINTS).readPointer());
        const points: Array<{ col: number; row: number }> = [];
        if (spawnPts) {
            for (let i = 0; i < spawnPts.size; i++) {
                const sp = readListItem(spawnPts, i);
                if (sp.isNull()) continue;
                points.push({
                    col: sp.add(SP_OFF_COL).readS32(),
                    row: sp.add(SP_OFF_ROW).readS32(),
                });
            }
        }
        out.push({ teamWithPlayerIndex: tpi, points });
    }
    return out;
}

/** Auto-spawn every unit listed in BC.PredefinedUnits into the given runner.
 * Maps PredefinedUnits[i] to SpawnPointGroup[i].SpawnPoints[j] positionally
 * — relies on the convention that PredefinedUnits and SpawnPointGroups are
 * declared in the same order (typically [human, ai]). Returns per-player
 * spawn count + any errors. */
function spawnPredefinedUnitsInto(
    runner: NativePointer, bc: NativePointer,
): {
    ok: boolean;
    spawned: Array<{
        playerId: number; pickedGroupIndex: number;
        teamWithPlayerIndex: number; count: number; errors: string[];
    }>;
} {
    if (!runnerApplyMi) throw new Error("runner.Apply not resolved");
    const pu = readManagedList(bc.add(BC_OFF_PREDEFINED_UNITS).readPointer());
    if (!pu) return { ok: false, spawned: [] };

    const allGroups = readAllSpawnGroups(bc);
    // Heuristic to find which SpawnPointGroup serves a given PredefinedUnits
    // group: pick the spawn group with enough points AND the largest count,
    // preferring exact size match if it exists. Skip groups already consumed
    // by a previous PredefinedUnits group in the same call.
    const consumed = new Set<number>();
    const pickGroup = (needed: number) => {
        let bestIdx = -1;
        let bestScore = -Infinity;
        for (let i = 0; i < allGroups.length; i++) {
            if (consumed.has(i)) continue;
            const avail = allGroups[i].points.length;
            if (avail < needed) continue;
            // Score: prefer exact match (high), penalize over-allocation,
            // but reward more available slots over less.
            const score = avail === needed ? 1000 : avail - needed * 2;
            if (score > bestScore) { bestScore = score; bestIdx = i; }
        }
        return bestIdx;
    };

    const result: Array<{
        playerId: number; pickedGroupIndex: number;
        teamWithPlayerIndex: number; count: number; errors: string[];
    }> = [];
    for (let g = 0; g < pu.size; g++) {
        const grp = readListItem(pu, g);
        if (grp.isNull()) continue;
        const playerId = grp.add(PU_OFF_ID).readS32();
        const unitsList = readManagedList(
            grp.add(PU_OFF_UNITS).readPointer());
        if (!unitsList) {
            result.push({
                playerId, pickedGroupIndex: -1, teamWithPlayerIndex: -1,
                count: 0, errors: ["units list null"],
            });
            continue;
        }
        const pickedIdx = pickGroup(unitsList.size);
        if (pickedIdx < 0) {
            result.push({
                playerId, pickedGroupIndex: -1, teamWithPlayerIndex: -1,
                count: 0,
                errors: [`no SpawnPointGroup with at least ${unitsList.size} ` +
                         `points available (groups: ${allGroups.map(
                            (g, i) => `${i}=${g.points.length}`).join(",")})`],
            });
            continue;
        }
        consumed.add(pickedIdx);
        const picked = allGroups[pickedIdx];
        const errors: string[] = [];
        let count = 0;
        for (let i = 0; i < unitsList.size; i++) {
            const pUnit = readListItem(unitsList, i);
            if (pUnit.isNull()) continue;
            const unitId = readIl2cppString(
                pUnit.add(PUNIT_OFF_UNIT_ID).readPointer());
            if (!unitId) { errors.push(`slot ${i}: null unitId`); continue; }
            const sp = picked.points[i];
            try {
                const msg = buildAddUnitMessage(
                    unitId, playerId, sp.col, sp.row);
                invokeMethod(runnerApplyMi.info, runner, [msg]);
                count++;
            } catch (e) {
                errors.push(`slot ${i} (${unitId} @ ${sp.col},${sp.row}): ` +
                            `${(e as Error).message}`);
            }
        }
        result.push({
            playerId, pickedGroupIndex: pickedIdx,
            teamWithPlayerIndex: picked.teamWithPlayerIndex,
            count, errors,
        });
    }
    return { ok: result.every((r) => r.errors.length === 0), spawned: result };
}

// --- LoadBattle.onLeave hook ---
//
// Applique le patch en attente à la BC que `LoadBattle` vient de rendre. Plusieurs
// `Interceptor.attach` sur la même méthode sont sûrs — `mode-source-capture.ts` y est déjà pour
// la CAPTURE ; on ajoute un canal latéral de MUTATION.
//
// ⚠ DEUX SOURCES, ET LA SECONDE EST CE QUI REND LE BANC D'ESSAI POSSIBLE. Le hook ne visait que
// `CampaignGameModeSource` : chaque hypothèse à tester coûtait donc une VRAIE bataille à
// l'utilisateur — montée, observée, abandonnée. `SandboxGameModeSource` porte SON PROPRE
// `LoadBattle` (vérifié dans `frida/methods.tsv` du build, ce n'est pas un héritage supposé), et
// la sandbox sait RETRAITER (`HandleBattleSurrender`). L'ancrer rend le banc FIDÈLE au sens fort :
// même patch, même geste, même fenêtre `onLeave` que le live — pas un régime approchant.
//
// ⚠ On n'ancre PAS `AGameModeSource.LoadBattle` (la base) : ça couvrirait d'un coup les ~12
// sources, dont la PvP et la guerre de guilde, qui courent sur le compte RÉEL. La liste est
// EXPLICITE pour que l'ajout d'un mode soit une décision, jamais un effet de bord.
const SOURCES_PATCHABLES = ["CampaignGameModeSource", "SandboxGameModeSource"] as const;

function installLoadBattleHook(): void {
    const poses: string[] = [];
    const manquantes: string[] = [];
    for (const nom of SOURCES_PATCHABLES) {
        const klass = findClassAnywhere("IdunBattle.ViewLogic.BattleSource", nom);
        const m = klass ? findMethod(klass, "LoadBattle") : null;
        if (!m) { manquantes.push(nom); continue; }
        if (attacherPatchSurLoadBattle(m.ptr, nom)) poses.push(nom);
    }
    if (poses.length === 0) {
        log("[battle-config] AUCUNE source patchable résolue (" + manquantes.join(", ")
            + ") — patch hook désactivé");
        return;
    }
    log("[battle-config] LoadBattle.onLeave patch hook installé sur : " + poses.join(", ")
        + (manquantes.length > 0 ? " | NON RÉSOLUES : " + manquantes.join(", ") : ""));
}

/** Pose le canal de mutation sur UN `LoadBattle`. Rend `false` si l'attache échoue — une source
 *  manquante n'est pas une panne du patch, seulement un mode qu'on ne peut pas piloter. */
function attacherPatchSurLoadBattle(ptr: NativePointer, source: string): boolean {
    try {
        Interceptor.attach(ptr, {
            onLeave(retval) {
                if (pendingPatch === null) return;
                if (retval.isNull()) return;
                const patch = pendingPatch;
                if (patch.consumeOnce !== false) {
                    pendingPatch = null; // consume now to avoid re-apply
                }
                try {
                    const result = applyPatchToConfig(retval, patch);
                    // La SOURCE est publiée : sans elle, un `lastApply` ne dit pas si le patch a
                    // mordu sur la campagne ou sur le banc, et les deux se lisent pareil.
                    result.operations.unshift(`source=${source}`);
                    lastApply = result;
                    log(`[battle-config] patch applied (${source}): ` +
                        `${result.operations.join("; ")}` +
                        (result.warnings.length > 0
                            ? ` | warnings: ${result.warnings.join("; ")}`
                            : ""));
                } catch (e) {
                    log(`[battle-config] patch threw: ${(e as Error).message}`);
                    lastApply = {
                        ok: false,
                        appliedAt: new Date().toISOString(),
                        bcPtr: retval.toString(),
                        operations: [],
                        warnings: [`exception: ${(e as Error).message}`],
                    };
                }
            },
        });
        return true;
    } catch (e) {
        log(`[battle-config] attache sur ${source}.LoadBattle refusée : ${(e as Error).message}`);
        return false;
    }
}

export function register(ctx: Ctx): void {
    installLoadBattleHook();

    ctx.rpc.inspectBattleConfig = () => queueOnMainThread(
        () => inspectBattleConfig());

    /** Dump SpawnPointSets structure for the live BC — useful to figure
     * out which group serves which player. */
    ctx.rpc.inspectSpawnPoints = () => queueOnMainThread(() => {
        const bc = getLiveBattleConfig();
        if (bc === null) return { ok: false, err: "no live BC" };
        const board = bc.add(BC_OFF_BOARD).readPointer();
        if (board.isNull()) return { ok: false, err: "board null" };
        const setIdx = bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).readS32();
        const sets = readManagedList(
            board.add(BCBC_OFF_SPAWN_POINT_SETS).readPointer());
        if (!sets) return { ok: false, err: "spawn point sets null" };
        const allSets = [];
        for (let s = 0; s < sets.size; s++) {
            const set = readListItem(sets, s);
            const groups = readManagedList(
                set.add(SPS_OFF_SPAWN_GROUPS).readPointer());
            const grpInfo = [];
            if (groups) {
                for (let g = 0; g < groups.size; g++) {
                    const grp = readListItem(groups, g);
                    const team = grp.add(SPG_OFF_TEAM_PLAYER_INDEX).readS32();
                    const pts = readManagedList(
                        grp.add(SPG_OFF_SPAWN_POINTS).readPointer());
                    const ptList = [];
                    if (pts) {
                        for (let p = 0; p < pts.size; p++) {
                            const sp = readListItem(pts, p);
                            ptList.push({
                                col: sp.add(SP_OFF_COL).readS32(),
                                row: sp.add(SP_OFF_ROW).readS32(),
                            });
                        }
                    }
                    grpInfo.push({
                        groupIndex: g,
                        teamWithPlayerIndex: team,
                        count: ptList.length,
                        points: ptList,
                    });
                }
            }
            allSets.push({
                setIndex: s,
                active: s === setIdx,
                groupCount: groups?.size ?? 0,
                groups: grpInfo,
            });
        }
        return { ok: true, activeSetIndex: setIdx, sets: allSets };
    });

    /** Set the patch applied at the next LoadBattle. Pass null/undefined
     * fields to leave them unchanged. Default consumeOnce=true means the
     * patch is cleared after one application — set consumeOnce=false to
     * make it sticky across multiple battles. */
    ctx.rpc.setBattleConfigPatch = (patch: BattleConfigPatch) => {
        if (!patch || typeof patch !== "object") {
            return { ok: false, err: "patch must be an object" };
        }
        pendingPatch = { ...patch };
        return {
            ok: true,
            stored: pendingPatch,
            note: "applied at next CampaignGameModeSource.LoadBattle",
        };
    };

    ctx.rpc.clearBattleConfigPatch = () => {
        pendingPatch = null;
        return { ok: true };
    };

    ctx.rpc.getBattleConfigPatchStatus = () => ({
        ok: true,
        pending: pendingPatch,
        lastApply,
    });

    /** Apply a patch DIRECTLY to the live BattleConfiguration (no LoadBattle
     * required). Useful when the battle is already loaded and you want to
     * tweak stats mid-deployment, or when inspectBattleConfig already shows
     * a live config. */
    ctx.rpc.applyBattleConfigPatchNow = (patch: BattleConfigPatch) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) {
                return {
                    ok: false,
                    err: "no live BattleConfiguration to mutate",
                };
            }
            const result = applyPatchToConfig(bc, patch);
            lastApply = result;
            return result;
        });
    };

    /** Build a fresh ISOLATED IdunRunner from the live captured
     * BattleConfiguration, optionally applying a patch first.
     *
     * This is the clean RL workflow: no UI involvement, no in-game battle
     * lifecycle. The new runner is constructed with the patched config —
     * since StartingActions (spawn messages) are built INSIDE Initialize()
     * from PredefinedUnits, our patch IS reflected in what spawns.
     *
     * The runner is registered in the runner-registry; the returned
     * `runnerId` can then be used with `observeBattle({runnerId})`,
     * `applyAddUnit`, `startBattle`, etc.
     *
     * The original captured BC is mutated in-place. Callers wanting to
     * preserve the original should clone it first (not yet implemented). */
    ctx.rpc.diagPredefMachinesFires = () => ({ fires: _addPredefMachinesFires });

    /** Sérialise la BC live (Pvp prioritaire, fallback Campaign) en JSON
     * Newtonsoft. Le JSON peut ensuite être passé à `initRunner` pour
     * construire un runner isolé reproductible. */
    ctx.rpc.dumpBattleConfig = () => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return { ok: false, err: "no live BC" };
            try {
                // serializeToJson est dans il2cpp/serializer.ts. Faut l'importer.
                const json = _serializeBcToJson(bc);
                if (json === null) return { ok: false, err: "serializeToJson returned null" };
                return { ok: true, bcPtr: bc.toString(), jsonLength: json.length, configJson: json };
            } catch (e) {
                return { ok: false, err: (e as Error).message };
            }
        });
    };

    /** Force discovery heap-scan : trouve les GameModeSource instances déjà
     * vivantes en mémoire (après reinject ou inject mid-game). Utile pour
     * retrouver une battle PvP/MoW Event déjà lancée. */
    ctx.rpc.discoverSources = async (opts?: {
        chunkMb?: number; pauseMs?: number;
    }) => {
        // tryActiveDiscoveryOfSources is sync — Campaign scan is short.
        const ok = await queueOnMainThread(() => tryActiveDiscoveryOfSources());
        // Pvp via heap scan chunked + async (yield au main thread Tacticus
        // entre chunks, pour ne pas trigger UnityFreezeDetector).
        if (getPvpGameModeSourcePtr() === null) {
            try {
                await findPvpGameModeSourceViaHeap({
                    chunkMb: opts?.chunkMb ?? 4,
                    pauseMs: opts?.pauseMs ?? 30,
                });
            } catch { /* leave null */ }
        }
        return {
            ok,
            campaign: getCampaignGameModeSourcePtr()?.toString() || null,
            pvp: getPvpGameModeSourcePtr()?.toString() || null,
            mowEvent: getMowEventGameModeSourcePtr()?.toString() || null,
        };
    };

    /** Override BC.RuleSet (Nullable<SyncPvpRuleSet>). Test hypothesis :
     * SetupGameOperation peut gate AddPredefinedMachines sur RuleSet != null. */
    ctx.rpc.setBattleConfigRuleSet = (opts: { rule: number | null }) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return { ok: false, err: "no live BC" };
            const prevHas = bc.add(BC_OFF_RULESET_HASVALUE).readU8();
            const prevVal = bc.add(BC_OFF_RULESET_VALUE).readS32();
            if (opts.rule === null) {
                bc.add(BC_OFF_RULESET_HASVALUE).writeU8(0);
                bc.add(BC_OFF_RULESET_VALUE).writeS32(0);
            } else {
                bc.add(BC_OFF_RULESET_HASVALUE).writeU8(1);
                bc.add(BC_OFF_RULESET_VALUE).writeS32(opts.rule | 0);
            }
            return {
                ok: true,
                prev: { hasValue: prevHas !== 0, value: prevVal },
                cur: { hasValue: opts.rule !== null, value: opts.rule ?? 0 },
            };
        });
    };

    /** Override BC.GameMode (Nullable<GameMode>). Set to 1 (PvP) to unlock
     * MoW handling — Campaign (0) skips MoW deployment in
     * SetupGameOperation. Pass null to clear (hasValue=false). */
    ctx.rpc.setBattleConfigGameMode = (opts: { mode: number | null }) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return { ok: false, err: "no live BC" };
            const prevHas = bc.add(BC_OFF_GAMEMODE_HASVALUE).readU8();
            const prevVal = bc.add(BC_OFF_GAMEMODE_VALUE).readS32();
            if (opts.mode === null) {
                bc.add(BC_OFF_GAMEMODE_HASVALUE).writeU8(0);
                bc.add(BC_OFF_GAMEMODE_VALUE).writeS32(0);
            } else {
                bc.add(BC_OFF_GAMEMODE_HASVALUE).writeU8(1);
                bc.add(BC_OFF_GAMEMODE_VALUE).writeS32(opts.mode | 0);
            }
            return {
                ok: true,
                prev: { hasValue: prevHas !== 0, value: prevVal },
                cur: { hasValue: opts.mode !== null, value: opts.mode ?? 0 },
            };
        });
    };

    /** Add a MoW to the live BC.PredefinedMachines list. The MoW will be
     * auto-deployed by runner.Initialize() when the next runner is built
     * from this BC. Campaign mode normally leaves this list empty
     * (SupportsMachinesOfWar=false) — calling this is how we inject MoW
     * into our RL battles. To deploy a *player* MoW use `applyAddMachine`
     * (runtime AddMachineMessage) instead — players add their MoW after
     * Initialize(), like for units (applyAddUnit). */
    ctx.rpc.addPredefinedMachine = (opts: {
        playerId: number; unitId: string;
    }) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return {
                ok: false, err: "no live BC — amorce first" };
            if (!predefinedMachinesOfWarClass
                || !predefinedMachinesOfWarCtor
                || !predefinedMachineOfWarClass
                || !(predefinedMachineOfWarCtor1 || predefinedMachineOfWarCtor0)) {
                return { ok: false, err: "PredefinedMachine class/ctor not resolved" };
            }
            try {
                // 1. PredefinedMachineOfWar { UnitId }
                const inner = il2cpp_object_new(
                    predefinedMachineOfWarClass) as NativePointer;
                if (inner.isNull()) throw new Error("alloc PredefinedMachineOfWar");
                gcRoot.add(inner);
                const unitIdStr = createManagedString(opts.unitId);
                if (predefinedMachineOfWarCtor1) {
                    invokeMethod(predefinedMachineOfWarCtor1.info, inner,
                        [unitIdStr]);
                } else {
                    invokeMethod(predefinedMachineOfWarCtor0!.info, inner, null);
                    inner.add(PMOW_OFF_UNIT_ID).writePointer(unitIdStr);
                }
                // 2. PredefinedMachinesOfWar wrapper { Id=playerId, MachineOfWar=inner }
                const wrapper = il2cpp_object_new(
                    predefinedMachinesOfWarClass) as NativePointer;
                if (wrapper.isNull()) throw new Error("alloc PredefinedMachinesOfWar");
                gcRoot.add(wrapper);
                invokeMethod(predefinedMachinesOfWarCtor.info, wrapper, null);
                wrapper.add(PMOW_OFF_PLAYER_ID).writeS32(opts.playerId);
                wrapper.add(PMOW_OFF_MACHINE).writePointer(inner);
                // 3. List<PredefinedMachinesOfWar>.Add(wrapper)
                const listPtr = bc.add(BC_OFF_PREDEFINED_MACHINES).readPointer();
                if (listPtr.isNull()) {
                    return { ok: false, err: "BC.PredefinedMachines list is null" };
                }
                const listKlass = listPtr.readPointer();
                const addMi = findMethodByParamCount(listKlass, "Add", 1);
                if (!addMi) return { ok: false, err: "List.Add(1) not found" };
                invokeMethod(addMi.info, listPtr, [wrapper]);
                return { ok: true, playerId: opts.playerId,
                         unitId: opts.unitId,
                         listSize: listPtr.add(LIST_OFF_SIZE).readS32() };
            } catch (e) {
                return { ok: false, err: (e as Error).message };
            }
        });
    };

    /** Auto-spawn all PredefinedUnits into the given runner. Maps each
     * PredefinedUnits group to the SpawnPointGroup at the same index, and
     * each unit to its corresponding SpawnPoint. */
    ctx.rpc.spawnPredefinedUnits = (opts: { runnerId: number }) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return { ok: false, err: "no live BC" };
            try {
                const entry = getRegistryRunner(opts.runnerId);
                return spawnPredefinedUnitsInto(entry.runner, bc);
            } catch (e) {
                return { ok: false, err: (e as Error).message };
            }
        });
    };

    // `owner` (2e argument, facultatif) : étiquette du propriétaire enregistrée
    // dans le registre — cf. runner-registry.ts.
    ctx.rpc.buildPatchedRunner = (patch?: BattleConfigPatch, owner?: string) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) {
                return {
                    ok: false,
                    err: "no live BattleConfiguration captured — " +
                         "autoBootExtraire first",
                };
            }
            // Same hard cap as initAndStart — this path never disposed
            // siblings (already coexist), only the gcRoot budget guard
            // was missing.
            const active = listRegistryRunners();
            if (active.length >= MAX_RUNNERS) {
                return {
                    ok: false,
                    err: "runner cap reached (" + MAX_RUNNERS + ") — dispose "
                         + "one first (disposeRunner). Active runnerIds: "
                         + active.map((r) => r.runnerId).join(", "),
                };
            }
            let patchResult: PatchApplyResult | null = null;
            if (patch) {
                patchResult = applyPatchToConfig(bc, patch);
                lastApply = patchResult;
            }
            try {
                const handle = buildRunner(bc);
                const entry = registerRunner(handle,
                    { autoDispose: false, owner });
                log(`[battle-config] buildPatchedRunner: runnerId=` +
                    `${entry.runnerId} runner=${handle.runner} seed=${handle.seed}`);
                return {
                    ok: true,
                    runnerId: entry.runnerId,
                    runner: handle.runner.toString(),
                    seed: handle.seed,
                    bcPtr: bc.toString(),
                    patch: patchResult,
                };
            } catch (e) {
                return {
                    ok: false,
                    err: `buildRunner failed: ${(e as Error).message}`,
                    patch: patchResult,
                };
            }
        });
    };
}
