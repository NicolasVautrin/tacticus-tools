// On-demand BattleConfiguration builder for campaign nodes.
//
// Strategy: piggy-back on a live `CampaignGameModeSource` instance. The
// game's own LoadBattle(isRestart=true) walks `_currentMatch` (a resolved
// `CampaignConfigDto`) + the linked GameConfig and assembles a full
// BattleConfiguration. We just need to mute the source's "where am I"
// fields, invoke LoadBattle, capture the return, then restore.
//
// Two RPCs:
//   dumpCampaignCatalog()
//     → JsonConvert.SerializeObject(gameConfig.battles.campaigns)
//     Returns the catalog of every campaign per CampaignType. Used by the
//     host to populate /api/campaigns/catalog and meta/<v>/.
//
//   buildCampaignConfig({ campaignType, campaignId, locationIndex })
//     → mutes _currentCampaignId/_currentLocationIndex/_currentMatch on the
//       captured CampaignGameModeSource, calls LoadBattle(true), restores.
//     Returns the full BattleConfiguration as JSON.
//
// Live instance discovery: hook CampaignGameModeSource..ctor (cheap, fires
// once per campaign navigation) and stash the latest `this`. If no instance
// has been created yet (user hasn't opened a campaign in-game), the RPCs
// throw — the host returns 503 with a clear message.
//
// Caveats / risks:
//   - LoadBattle(true) may emit funnel/analytics events. Phase 1 accepts
//     this; Phase 2 will switch to BattleConfigBuilder.GetCampaignLevelConfig
//     (pure functional) if pollution is observed.
//   - Some fields are reads/writes through interface types (IGameConfigData);
//     we resolve offsets via il2cpp field name lookup to stay version-safe.

import {
    class_get_methods, class_get_name,
    findClass, findClassAnywhere, findMethod, findMethodByParamCount,
    getFieldOffset, il2cppBase, IL2CPP_MODULE_NAME, MethodRef,
    methodEntry, method_get_name, method_get_param_count, s,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log, traceEnter } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

const ASM_BATTLE = "Assembly-CSharp.dll";
const NS_BATTLE_SOURCE = "IdunBattle.ViewLogic.BattleSource";

const _libIl2cpp = Process.findModuleByName(IL2CPP_MODULE_NAME);

/** Cross-feature accessor: other features (e.g. mow-builder) need the
 * captured GameConfigDto without re-implementing heap-scans (which freeze
 * the game's main thread). Returns the most-recently captured pointer or
 * null if natural capture hasn't fired yet. */
export function getUnitProgressionPtr(): NativePointer | null {
    return unitProgressionPtr;
}

export function getLastGameConfig(): NativePointer | null {
    return lastGameConfig;
}

export function getCampaignGameModeSourcePtr(): NativePointer | null {
    return campaignGameModeSourcePtr;
}

export function getMowEventGameModeSourcePtr(): NativePointer | null {
    return mowEventGameModeSourcePtr;
}

export function getPvpGameModeSourcePtr(): NativePointer | null {
    return pvpGameModeSourcePtr;
}

export function getGuildBossGameModeSourcePtr(): NativePointer | null {
    return guildBossGameModeSourcePtr;
}

/**
 * ⚠ `lastGameConfig` NE CONTIENT QUE DU `GameConfigDto`, ou RIEN.
 *
 * La version précédente, quand l'unwrap échouait, stockait le pointeur BRUT :
 *
 *     } else { lastGameConfig = p; }        // <- repli qui FABRIQUE un succès
 *
 * `campaignBuilderStatus` répondait alors `hasGameConfig: true` sur un objet qui n'est pas un
 * DTO, et TOUS les consommateurs (`buildCampaignConfig`, `dumpCampaignCatalog`,
 * `dump-pvp-boards`, `mow-builder`) échouaient en aval sur « chain resolution failed » —
 * un message qui accuse la chaîne alors que la faute est ICI, à la capture. Mesuré le
 * 2026-08-17 : les deux RPC de catalogue refusaient, en bataille comme hors bataille, avec
 * les trois pointeurs annoncés présents.
 *
 * Ne rien stocker est STRICTEMENT MEILLEUR que stocker un pointeur inexploitable : le repli
 * de `buildCampaignConfig` (unwrap depuis `CampaignGameModeSource._gameConfig`) ne s'arme
 * QUE si `lastGameConfig` est nul. Le faux vert désarmait donc la seule voie de secours.
 *
 * Le brut est conservé à part, pour le diagnostic — jamais pour l'usage.
 */
export function setLastGameConfig(p: NativePointer): void {
    if (p.isNull()) return;
    lastGameConfigBrut = p;
    const dto = unwrapGameConfig(p);
    if (dto && !dto.isNull()) {
        lastGameConfig = dto;
        raisonUnwrap = null;
        log(`[campaign-builder] setLastGameConfig: unwrapped GameConfigDto captured @ ${dto}`);
    } else {
        log(`[campaign-builder] setLastGameConfig: REFUS -- @ ${p} n'est pas exploitable `
            + `(${raisonUnwrap ?? "raison non renseignée"}). \`lastGameConfig\` reste NUL pour `
            + "que le repli par `CampaignGameModeSource._gameConfig` puisse s'armer.");
    }
    // Le signal de boot part une seule fois, et il DIT s'il porte une config exploitable —
    // l'ancien `via: "auto-boot-raw"` se lisait comme un succès.
    if (!_readyEnvoye) {
        _readyEnvoye = true;
        try {
            send({ t: "builder_ready",
                   via: dto ? "auto-boot-unwrapped" : "auto-boot-brut",
                   exploitable: dto !== null && !dto.isNull() });
        } catch { /* */ }
    }
}

export function setUnitProgressionPtr(p: NativePointer): void {
    if (p.isNull()) return;
    unitProgressionPtr = p;
    log(`[campaign-builder] setUnitProgressionPtr: captured UnitProgression @ ${p}`);
}

export async function tryActiveDiscoveryOfSources(): Promise<boolean> {
    // Tous les heap scans sont chunked async (chunks 4MB + yield 30ms entre).
    // Total typique : 30-60s mais main thread Tacticus respire → pas de
    // UnityFreezeDetector kill, socket PvP préservée, GPU TDR évité.
    if (lastGameConfig === null) {
        try {
            const scannedGc = await findGameConfigDtoViaHeap();
            if (scannedGc !== null) {
                lastGameConfig = scannedGc;
                log("[campaign-builder] tryActiveDiscoveryOfSources: GameConfigDto captured via active Heap Scan.");
            }
        } catch (e) {
            log("[campaign-builder] tryActiveDiscoveryOfSources: error scanning for GameConfigDto: " + (e as Error).message);
        }
    }
    if (campaignGameModeSourcePtr === null) {
        try {
            const scannedSource = await findCampaignGameModeSourceViaHeap();
            if (scannedSource !== null) {
                campaignGameModeSourcePtr = scannedSource;
                log("[campaign-builder] tryActiveDiscoveryOfSources: CampaignGameModeSource captured via active Heap Scan.");
            }
        } catch (e) {
            log("[campaign-builder] tryActiveDiscoveryOfSources: error scanning for CampaignGameModeSource: " + (e as Error).message);
        }
    }
    // Pvp/MoW Event : capture passive via Interceptor hooks (get_BattleGameMode,
    // HandleTurnStarted, etc. — cf. register section). Scan manuel possible
    // via le RPC `discoverSources` qui invoque findPvpGameModeSourceViaHeap.
    if (unitProgressionPtr === null) {
        try {
            const scannedUp = await findUnitProgressionViaHeap();
            if (scannedUp !== null) {
                unitProgressionPtr = scannedUp;
                log("[campaign-builder] tryActiveDiscoveryOfSources: UnitProgression captured via active Heap Scan.");
            }
        } catch (e) {
            log("[campaign-builder] tryActiveDiscoveryOfSources: error scanning for UnitProgression: " + (e as Error).message);
        }
    }
    return campaignGameModeSourcePtr !== null && lastGameConfig !== null
        && unitProgressionPtr !== null;
}

// Most-recent CampaignGameModeSource instance — captured by the .ctor hook.
// Pinned via raw pointer; valid as long as the game's DI container holds it.
// If the user destroys the campaign view, the pointer may go stale — every
// usage re-validates the type via `klass at offset 0` before touching fields.
let campaignGameModeSourcePtr: NativePointer | null = null;
// Same idea pour MachinesOfWarEventGameModeSource — capturé via ctor/LoadBattle
// quand l'user navigue vers MoW Event in-game. Permet de récupérer une BC
// live qui contient des MoW dans PredefinedMachines (vs Campaign mode qui
// laisse cette liste vide).
let mowEventGameModeSourcePtr: NativePointer | null = null;
// PvpGameModeSource — capture quand user navigue vers Arena PvP in-game.
// _currentBattle @+0xD8 (vs Campaign 0x80, MoW Event 0xF0). Cette BC live
// PvP devrait avoir RuleSet set, MachineOfWarAmmo>0, et templates :pvp
// init correctement.
let pvpGameModeSourcePtr: NativePointer | null = null;
let guildBossGameModeSourcePtr: NativePointer | null = null;

// GameConfigDto* — captured independently from any DI consumer that takes it
// as a ctor parameter. Available very early (game boot, before any battle),
// which lets the catalog endpoint work without forcing the user to enter a
// campaign first. Build still needs `campaignGameModeSourcePtr`.
let lastGameConfig: NativePointer | null = null;
// Le pointeur BRUT tel que la capture l'a lu, et POURQUOI il n'a pas pu être déballé.
// Conservés pour le diagnostic UNIQUEMENT : aucun consommateur ne doit les lire comme une
// config. `null` = pas de tentative, jamais « tout va bien ».
let lastGameConfigBrut: NativePointer | null = null;
let raisonUnwrap: string | null = null;
let _readyEnvoye = false;

// UnitProgression instance — captured at the first natural
// UnitProgression.GetUnit(string) call. Used by the per-faction amorce
// step to pre-resolve metadata for enemy units of a faction the user
// hasn't touched.
let unitProgressionPtr: NativePointer | null = null;
let getUnitMi: MethodRef | null = null;

// Resolved lazily on first use (depends on CampaignGameModeSource being
// loaded by the IL2CPP runtime — guaranteed once any battle code path runs).
let cgmsClass: NativePointer | null = null;
let loadBattleMi: MethodRef | null = null;
let offCurrentCampaignId = -1;
let offCurrentLocationIndex = -1;
let offCurrentMatch = -1;
let offCurrentBattle = -1;
let offGameConfig = -1;

// GameConfigDto.battles -> BattlesConfigDto.campaigns chain
let gameConfigClass: NativePointer | null = null;
let battlesDtoClass: NativePointer | null = null;
let campaignsDtoClass: NativePointer | null = null;
let offBattles = -1;
let offCampaigns = -1;

// CampaignsConfigDto.GetCampaign(CampaignType, string) → CampaignBattlesConfig
let getCampaignMi: MethodRef | null = null;

// CampaignBattlesConfig.battles : List<CampaignConfigDto>
let campaignBattlesConfigClass: NativePointer | null = null;
let offCampaignBattles = -1;

// List<T>._items / _size
let listItemsOff = -1;
let listSizeOff = -1;

function ensureCgmsResolved(): boolean {
    if (cgmsClass && loadBattleMi) return true;
    cgmsClass = findClass(ASM_BATTLE, NS_BATTLE_SOURCE, "CampaignGameModeSource");
    if (!cgmsClass) { log("[campaign-builder] CampaignGameModeSource class not found"); return false; }
    loadBattleMi = findMethod(cgmsClass, "LoadBattle");
    if (!loadBattleMi) { log("[campaign-builder] LoadBattle method not found"); return false; }

    offCurrentCampaignId   = getFieldOffset(cgmsClass, "_currentCampaignId");
    offCurrentLocationIndex = getFieldOffset(cgmsClass, "_currentLocationIndex");
    offCurrentMatch        = getFieldOffset(cgmsClass, "_currentMatch");
    offCurrentBattle       = getFieldOffset(cgmsClass, "_currentBattle");
    offGameConfig          = getFieldOffset(cgmsClass, "_gameConfig");

    if ([offCurrentCampaignId, offCurrentLocationIndex, offCurrentMatch,
         offCurrentBattle, offGameConfig].some((o) => o < 0)) {
        log("[campaign-builder] missing CampaignGameModeSource field offsets");
        return false;
    }
    return true;
}

let _gameConfigKlassLogged = false;
/** Read the klass name of a managed object pointer. */
function klassName(p: NativePointer): string | null {
    try {
        if (p.isNull()) return null;
        const klass = p.readPointer();
        if (klass.isNull()) return null;
        const np = class_get_name(klass) as NativePointer;
        if (np.isNull()) return null;
        return s(np);
    } catch { return null; }
}

/** `_gameConfig` on CampaignGameModeSource is typed as IGameConfigData
 * (interface). On Tacticus PC the runtime concrete class is `GameConfigData`
 * — a wrapper/service that exposes the actual `GameConfigDto` via a
 * `get_gameConfigDto` getter. Resolves the getter once and unwraps. */
let _gameConfigDataGetterMi: MethodRef | null = null;
function unwrapGameConfig(p: NativePointer): NativePointer | null {
    // ⚠ CHAQUE SORTIE NULLE RENSEIGNE `raisonUnwrap`. Sans ça, l'échec ne se lisait que dans
    // la console Frida, et l'appelant ne pouvait rendre qu'un « chain resolution failed » qui
    // accuse le mauvais étage.
    raisonUnwrap = null;
    if (p.isNull()) { raisonUnwrap = "pointeur NUL"; return null; }
    const name = klassName(p);
    if (name === "GameConfigDto") return p;
    if (name !== "GameConfigData") {
        raisonUnwrap = `classe INATTENDUE derrière le pointeur : '${name ?? "illisible"}' `
            + "-- attendu `GameConfigDto` ou `GameConfigData`";
        if (!_gameConfigKlassLogged) {
            _gameConfigKlassLogged = true;
            log("[campaign-builder] _gameConfig field holds unexpected class '"
                + (name ?? "?") + "' @ " + p);
        }
        return null;
    }
    // Wrapper case — invoke the getter to extract the wrapped DTO.
    if (_gameConfigDataGetterMi === null) {
        const klass = findClassAnywhere(
            "IdunMetaLogic.Client.DTO.Config", "GameConfigData");
        const m = klass ? findMethod(klass, "get_gameConfigDto") : null;
        if (!m || m.ptr.isNull()) {
            raisonUnwrap = klass === null
                ? "`IdunMetaLogic.Client.DTO.Config.GameConfigData` INTROUVABLE sur ce build"
                : "`GameConfigData$$get_gameConfigDto` INTROUVABLE sur ce build";
            log("[campaign-builder] GameConfigData.get_gameConfigDto not found");
            return null;
        }
        _gameConfigDataGetterMi = m;
    }
    try {
        const dto = invokeMethod(_gameConfigDataGetterMi.info, p, null);
        if (dto.isNull()) {
            raisonUnwrap = "`get_gameConfigDto` a rendu NUL";
            return null;
        }
        const nomDto = klassName(dto);
        if (nomDto === "GameConfigDto") return dto;
        raisonUnwrap = `\`get_gameConfigDto\` a rendu un '${nomDto ?? "illisible"}', `
            + "pas un `GameConfigDto`";
        return null;
    } catch (e) {
        raisonUnwrap = "`get_gameConfigDto` a LEVÉ : " + (e as Error).message;
        log("[campaign-builder] unwrapGameConfig invoke threw: "
            + (e as Error).message);
        return null;
    }
}

function ensureGameConfigChainResolved(gameConfigInstance: NativePointer): boolean {
    if (battlesDtoClass && campaignsDtoClass && getCampaignMi) return true;

    // Read klass directly from the live instance — survives even if the
    // declared type is the IGameConfigData interface.
    gameConfigClass = gameConfigInstance.readPointer();
    if (gameConfigClass.isNull()) return false;

    offBattles = getFieldOffset(gameConfigClass, "battles");
    if (offBattles < 0) {
        log("[campaign-builder] gameConfig.battles offset not found");
        return false;
    }
    const battlesPtr = gameConfigInstance.add(offBattles).readPointer();
    if (battlesPtr.isNull()) {
        log("[campaign-builder] gameConfig.battles is null");
        return false;
    }
    battlesDtoClass = battlesPtr.readPointer();
    offCampaigns = getFieldOffset(battlesDtoClass, "campaigns");
    if (offCampaigns < 0) {
        log("[campaign-builder] battles.campaigns offset not found");
        return false;
    }
    const campaignsPtr = battlesPtr.add(offCampaigns).readPointer();
    if (campaignsPtr.isNull()) {
        log("[campaign-builder] battles.campaigns is null");
        return false;
    }
    campaignsDtoClass = campaignsPtr.readPointer();
    getCampaignMi = findMethod(campaignsDtoClass, "GetCampaign");
    if (!getCampaignMi) {
        log("[campaign-builder] GetCampaign method not found on CampaignsConfigDto");
        return false;
    }
    return true;
}

function ensureCampaignBattlesConfigResolved(cbcInstance: NativePointer): boolean {
    if (campaignBattlesConfigClass && offCampaignBattles >= 0
        && listItemsOff >= 0 && listSizeOff >= 0) return true;

    campaignBattlesConfigClass = cbcInstance.readPointer();
    offCampaignBattles = getFieldOffset(campaignBattlesConfigClass, "battles");
    if (offCampaignBattles < 0) {
        log("[campaign-builder] CampaignBattlesConfig.battles offset not found");
        return false;
    }
    const listPtr = cbcInstance.add(offCampaignBattles).readPointer();
    if (listPtr.isNull()) return false;
    const listKlass = listPtr.readPointer();
    listItemsOff = getFieldOffset(listKlass, "_items");
    listSizeOff = getFieldOffset(listKlass, "_size");
    return listItemsOff >= 0 && listSizeOff >= 0;
}

// IL2CPP runtime helpers used by the heap-scan validators.
const _objectGetClass = (() => {
    if (!_libIl2cpp) return null;
    const p = _libIl2cpp.findExportByName("il2cpp_object_get_class");
    return p ? new NativeFunction(p, "pointer", ["pointer"]) : null;
})();
const _classIsAssignableFrom = (() => {
    if (!_libIl2cpp) return null;
    const p = _libIl2cpp.findExportByName("il2cpp_class_is_assignable_from");
    return p ? new NativeFunction(p, "uint8", ["pointer", "pointer"]) : null;
})();

/** Walk all writable memory ranges scanning for managed objects whose
 * klass pointer matches the target class. Returns the first match passing
 * `validate` (or simply the first kclass match if no validator).
 *
 * IL2CPP-managed objects start with a Il2CppClass* at offset 0. We scan
 * for the raw klass pointer and check each hit. Multiple instances may
 * exist (a singleton + transient/stale copies); a validator distinguishes
 * the LIVE instance by checking a critical field is non-null. */
function findInstanceByHeapScan(
    klass: NativePointer,
    validate?: (candidate: NativePointer) => boolean,
): NativePointer | null {
    // Pattern: little-endian klass pointer as 8 hex bytes.
    const patternHex = (() => {
        const v = klass.toString(16).padStart(16, "0");
        const bytes: string[] = [];
        for (let i = 7; i >= 0; i--) bytes.push(v.substr(i * 2, 2));
        return bytes.join(" ");
    })();
    let match: NativePointer | null = null;
    const ranges = Process.enumerateRanges("rw-");
    for (const r of ranges) {
        if (match) break;
        if (r.size < 1024 * 1024) continue;
        if (r.size > 2 * 1024 * 1024 * 1024) continue;
        try {
            Memory.scanSync(r.base, r.size, patternHex).forEach((m) => {
                if (match) return;
                const candidate = m.address;
                try {
                    if (!candidate.readPointer().equals(klass)) return;
                    if (validate && !validate(candidate)) return;
                    match = candidate;
                } catch { /* unmapped — skip */ }
            });
        } catch { /* range went away — skip */ }
    }
    return match;
}

/** Version chunked + async — scan en morceaux de chunkSize avec une pause
 * de pauseMs entre chunks. Laisse le main thread Tacticus respirer →
 * UnityFreezeDetector ne kick pas. Plus lent (~2-5x) que scanSync mais
 * SAFE pour scan mid-battle avec PvP socket active.
 *
 * Returns Promise<NativePointer | null>. À appeler depuis un context async
 * (RPC handler avec await). */
export async function findInstanceByHeapScanChunked(
    klass: NativePointer,
    validate?: (candidate: NativePointer) => boolean,
    opts: { chunkMb?: number; pauseMs?: number } = {},
): Promise<NativePointer | null> {
    const chunkSize = (opts.chunkMb ?? 4) * 1024 * 1024;
    const pauseMs = opts.pauseMs ?? 30;
    const patternHex = (() => {
        const v = klass.toString(16).padStart(16, "0");
        const bytes: string[] = [];
        for (let i = 7; i >= 0; i--) bytes.push(v.substr(i * 2, 2));
        return bytes.join(" ");
    })();
    const sleep = (ms: number) => new Promise<void>(
        (r) => { setTimeout(r, ms); });
    let match: NativePointer | null = null;
    const ranges = Process.enumerateRanges("rw-");
    let chunksScanned = 0;
    for (const r of ranges) {
        if (match) break;
        if (r.size < 1024 * 1024) continue;
        if (r.size > 2 * 1024 * 1024 * 1024) continue;
        let offset = 0;
        while (offset < r.size && !match) {
            const size = Math.min(chunkSize, r.size - offset);
            const base = r.base.add(offset);
            try {
                await new Promise<void>((resolve) => {
                    const out: NativePointer[] = [];
                    Memory.scan(base, size, patternHex, {
                        onMatch(addr) {
                            try {
                                if (addr.readPointer().equals(klass)) {
                                    out.push(addr);
                                }
                            } catch { /* unmapped */ }
                        },
                        onError() { /* skip chunk */ },
                        onComplete() {
                            for (const c of out) {
                                if (match) return;
                                if (!validate || validate(c)) { match = c; return; }
                            }
                            resolve();
                        },
                    });
                });
            } catch { /* range gone */ break; }
            offset += size;
            chunksScanned++;
            // Yield to give Tacticus main thread a frame (UnityFreezeDetector).
            await sleep(pauseMs);
        }
    }
    return match;
}

/** Find a live UnitProgression instance via heap scan. Required for
 * synthesizing the Func<string,IUnitModel> delegate when the natural
 * broad-hook hasn't fired yet (post-reinject, idle game state).
 *
 * Validator: candidate must be assignable to UnitProgression klass AND
 * have its core injected DI fields populated (_unitsConfig, _logger).
 * UnitProgression has 30+ injected services — checking 2-3 is plenty
 * to filter Zenject placeholders. */
async function findUnitProgressionViaHeap(): Promise<NativePointer | null> {
    const upCls = findClassAnywhere(
        "IdunMetaLogic.UserProgress", "UnitProgression");
    if (!upCls) return null;
    const start = Date.now();
    const found = await findInstanceByHeapScanChunked(upCls, (cand) => {
        try {
            if (!_objectGetClass || !_classIsAssignableFrom) return false;
            const candKlass = _objectGetClass(cand) as NativePointer;
            if (candKlass.isNull()) return false;
            const ok = _classIsAssignableFrom(upCls, candKlass) as number;
            if (!ok) return false;
            // Check several injected fields are heap pointers, not 0/1/garbage.
            // Layout (from dump.cs):
            //   0x28 _gameEventService, 0x30 _unitProgressionData,
            //   0x38 _unitsConfig (the units dictionary — critical),
            //   0xA0 _logger
            const min = ptr(0x10000);
            for (const off of [0x28, 0x30, 0x38, 0xA0]) {
                const v = cand.add(off).readPointer();
                if (v.compare(min) < 0) return false;
            }
            return true;
        } catch { return false; }
    });
    const elapsed = Date.now() - start;
    if (found) {
        log("[campaign-builder] found UnitProgression @ " + found
            + " via heap scan (" + elapsed + " ms, validated)");
    } else {
        log("[campaign-builder] heap scan for UnitProgression yielded nothing ("
            + elapsed + " ms)");
    }
    return found;
}

/** Find a live CampaignGameModeSource instance via heap scan with type
 * validation. The instance is what `path 2 (mute mode)` mutates + calls
 * LoadBattle on.
 *
 * #989 — CE SCAN NE TROUVE RIEN AVANT LA PREMIERE BATAILLE, et la phrase
 * remplacee ici pretendait le contraire (« created naturally early during
 * Tacticus boot — Zenject DI eagerly resolves it »). Les deux moities etaient
 * fausses : il n'y a pas de conteneur DI dans le binaire, et l'instance n'existe
 * pas au boot. Son SEUL site de creation est
 * `idun.shared.commands.ViewCommandExecutor$$StartCampaignMatch`, qui alloue puis
 * appelle le ctor inline avant d'enchainer sur le chargement de la bataille.
 * Un scan qui aboutit prouve donc qu'une bataille de campagne a DEJA ete lancee
 * dans cette session. Voir
 * `docs/rl/case-989-campaign-game-mode-source-transient.md`.
 *
 * Validator: heap-scanned instance must have a non-null klass and that
 * klass must be assignable to CampaignGameModeSource (filters wrong-type or
 * partially-initialised heap candidates). */
async function findCampaignGameModeSourceViaHeap(): Promise<NativePointer | null> {
    const cgmsCls = findClass(ASM_BATTLE, NS_BATTLE_SOURCE,
        "CampaignGameModeSource");
    if (!cgmsCls) return null;
    if (!ensureCgmsResolved()) return null;
    const start = Date.now();
    // Strict validator. The first heap-scan result was a corrupt
    // partially-initialized instance (locIdx field = stack garbage). To
    // reliably distinguish the CURRENT source from earlier/partial ones,
    // require:
    //   1. Type assignability to CGMS klass (filters stale/wrong-type heap)
    //   2. gameConfig pointer matches our captured lastGameConfig — le
    //      `IGameConfigData` de longue duree que le `ViewCommandExecutor`
    //      detient et passe au ctor ; seule une source construite depuis le
    //      MEME executor pointe dessus.
    // #989 — « singleton » serait faux : il y a UNE instance PAR BATAILLE
    // lancee (le ctor n'a qu'un site d'appel, `StartCampaignMatch`), et le
    // hook ne garde que la plus recente. Un heap scan peut donc voir plusieurs
    // instances mortes des sessions precedentes — c'est ce que ce validateur
    // filtre. Voir `docs/rl/case-989-campaign-game-mode-source-transient.md`.
    //   3. currentLocationIndex within sane bounds (0-100; campaigns rarely
    //      have more)
    const found = await findInstanceByHeapScanChunked(cgmsCls, (cand) => {
        try {
            if (!_objectGetClass || !_classIsAssignableFrom) return false;
            const candKlass = _objectGetClass(cand) as NativePointer;
            if (candKlass.isNull()) return false;
            const ok = _classIsAssignableFrom(cgmsCls, candKlass) as number;
            if (!ok) return false;
            const min = ptr(0x10000);
            const gc = cand.add(offGameConfig).readPointer();
            if (gc.compare(min) < 0) return false;
            // Match our singleton — the killer check.
            if (lastGameConfig !== null) {
                const gcDto = unwrapGameConfig(gc);
                if (gcDto === null || !gcDto.equals(lastGameConfig)) {
                    return false;
                }
            }
            // Sanity on locIdx (placeholder had 848628048).
            const loc = cand.add(offCurrentLocationIndex).readS32();
            if (loc < -1 || loc > 100) return false;
            return true;
        } catch { return false; }
    });
    const elapsed = Date.now() - start;
    if (found) {
        log("[campaign-builder] found CampaignGameModeSource @ " + found
            + " via heap scan (" + elapsed + " ms, validated)");
    } else {
        log("[campaign-builder] heap scan for CampaignGameModeSource yielded nothing ("
            + elapsed + " ms) — open any campaign once to instantiate");
    }
    return found;
}


/** Heap-scan fallback pour PvpGameModeSource — utile au reinject si l'user
 * est déjà dans une battle PvP. Validator : type assignable + _gameConfig
 * matches lastGameConfig + _currentBattle non-null (=battle chargée). */
export async function findPvpGameModeSourceViaHeap(
    opts: { chunkMb?: number; pauseMs?: number } = {},
): Promise<NativePointer | null> {
    const cls = findClass(ASM_BATTLE, NS_BATTLE_SOURCE, "PvpGameModeSource");
    if (!cls) return null;
    const start = Date.now();
    // PvpGameModeSource layout : _gameConfig @+0xA8, _currentBattle @+0xD8
    const PVP_OFF_GAMECONFIG = 0xA8;
    const PVP_OFF_CURRENT_BATTLE = 0xD8;
    const found = await findInstanceByHeapScanChunked(cls, (cand) => {
        try {
            if (!_objectGetClass || !_classIsAssignableFrom) return false;
            const candKlass = _objectGetClass(cand) as NativePointer;
            if (candKlass.isNull()) return false;
            if (!_classIsAssignableFrom(cls, candKlass)) return false;
            const min = ptr(0x10000);
            const gc = cand.add(PVP_OFF_GAMECONFIG).readPointer();
            if (gc.compare(min) < 0) return false;
            // _currentBattle non-null = battle chargée → la BC qu'on veut
            const bc = cand.add(PVP_OFF_CURRENT_BATTLE).readPointer();
            if (bc.isNull() || bc.compare(min) < 0) return false;
            return true;
        } catch { return false; }
    }, opts);
    const elapsed = Date.now() - start;
    if (found) {
        log("[campaign-builder] found PvpGameModeSource @ " + found
            + " via chunked heap scan (" + elapsed + " ms, validated)");
        pvpGameModeSourcePtr = found;
        try { send({ t: "pvp_builder_ready", via: "heap-scan" }); }
        catch { /* */ }
    } else {
        log("[campaign-builder] chunked heap scan for PvpGameModeSource yielded nothing ("
            + elapsed + " ms) — navigate to PvP/Arena to instantiate");
    }
    return found;
}


/** Heap-scan fallback for the live GameConfigDto when get_gameConfigDto
 * hasn't fired naturally (re-injection mid-game, idle home screen, etc.).
 *
 * Multiple GameConfigDto instances may exist in memory (live singleton +
 * transient copies from deserialization buffers). We validate each scan
 * hit by checking that the `battles` field is non-null AND that the
 * pointed-to BattlesConfigDto in turn has a non-null `campaigns` field.
 * Only the fully-populated singleton survives this check. */
async function findGameConfigDtoViaHeap(): Promise<NativePointer | null> {
    const klass = findClassAnywhere(
        "IdunMetaLogic.Client.DTO.Config", "GameConfigDto");
    if (!klass) return null;
    const battlesOff = getFieldOffset(klass, "battles");
    if (battlesOff < 0) {
        log("[campaign-builder] GameConfigDto.battles offset not found");
        return null;
    }
    const start = Date.now();
    const found = await findInstanceByHeapScanChunked(klass, (cand) => {
        try {
            const battlesPtr = cand.add(battlesOff).readPointer();
            if (battlesPtr.isNull()) return false;
            // Check battles -> campaigns to weed out half-populated copies.
            const battlesKlass = battlesPtr.readPointer();
            if (battlesKlass.isNull()) return false;
            const campaignsOffLocal = getFieldOffset(battlesKlass, "campaigns");
            if (campaignsOffLocal < 0) return false;
            const campaignsPtr = battlesPtr.add(campaignsOffLocal).readPointer();
            return !campaignsPtr.isNull();
        } catch {
            return false;
        }
    });
    const elapsed = Date.now() - start;
    if (found) {
        log("[campaign-builder] found GameConfigDto @ " + found
            + " via heap scan (" + elapsed + " ms, validated)");
    } else {
        log("[campaign-builder] heap scan for GameConfigDto yielded nothing ("
            + elapsed + " ms)");
    }
    return found;
}

/** Read element i of a List<T>. _items is T[] (Il2CppArray header = 0x20). */
function listGet(listPtr: NativePointer, i: number): NativePointer {
    const items = listPtr.add(listItemsOff).readPointer();
    if (items.isNull()) return ptr(0);
    const size = listPtr.add(listSizeOff).readS32();
    if (i < 0 || i >= size) {
        throw new Error(`list index out of range: ${i} (size=${size})`);
    }
    return items.add(0x20 + i * Process.pointerSize).readPointer();
}

function listSize(listPtr: NativePointer): number {
    if (listPtr.isNull()) return 0;
    return listPtr.add(listSizeOff).readS32();
}

/** Read a managed System.String into a JS string. Il2CppString layout:
 *   0x00: klass*  0x08: monitor*  0x10: length(int32)  0x14: chars(utf16) */
function readString(strPtr: NativePointer): string | null {
    try {
        if (strPtr.isNull()) return null;
        const len = strPtr.add(0x10).readS32();
        if (len < 0 || len > 4096) return null;
        return strPtr.add(0x14).readUtf16String(len);
    } catch { return null; }
}

/** Per-faction amorce — call UnitProgression.GetUnit(id) for each unit id
 * in the targetMatch's first variation. Each call forces IL2CPP to resolve
 * the unit's class metadata + parent chain (faction-specific cctors).
 *
 * Without this, building a campaign whose enemy faction the user hasn't
 * touched in-game crashes inside LoadBattle (the cold-start cascade we
 * fixed for paths 0/1 — same root cause now showing up at the unit-class
 * level instead of the controller level).
 *
 * Cheap idempotent: GetUnit on already-warm classes is a fast hashmap
 * lookup. */
function prechargerUnitesCibles(targetMatch: NativePointer): number {
    if (unitProgressionPtr === null || getUnitMi === null) return 0;
    let precharges = 0;
    try {
        // targetMatch.units (List<List<string>>) at offset 0x70
        const unitsListList = targetMatch.add(0x70).readPointer();
        if (unitsListList.isNull()) return 0;
        const variationCount = listSize(unitsListList);
        if (variationCount <= 0) return 0;
        // Use only the first variation — sufficient for metadata amorce.
        const variation0 = listGet(unitsListList, 0);
        if (variation0.isNull()) return 0;
        const unitCount = listSize(variation0);
        const seen = new Set<string>();
        for (let i = 0; i < unitCount; i++) {
            const idStr = listGet(variation0, i);
            if (idStr.isNull()) continue;
            // unit ids are formatted "<key>:<level>" — strip the level so
            // GetUnit resolves the class chain only (level is per-instance).
            const raw = readString(idStr);
            if (!raw) continue;
            const idOnly = raw.split(":")[0];
            if (seen.has(idOnly)) continue;
            seen.add(idOnly);
            try {
                const idManaged = createManagedString(idOnly);
                invokeMethod(getUnitMi.info, unitProgressionPtr!, [idManaged]);
                precharges += 1;
            } catch { /* unknown id — skip */ }
        }
    } catch (e) {
        log("[campaign-builder] prechargerUnitesCibles failed: " + (e as Error).message);
    }
    return precharges;
}

export function register(ctx: Ctx): void {
    // Two capture points to maximise coverage:
    //   1. .ctor — fires for any new CampaignGameModeSource instance created
    //      AFTER our inject (typical: user clicks a node in-game).
    //   2. LoadBattle.onEnter — fires every time the instance prepares a
    //      battle. Crucially this catches instances that already existed
    //      BEFORE inject (e.g. user was mid-campaign when we attached).
    // Both write to the same `campaignGameModeSourcePtr` slot — most-recent wins.
    const ctorClass = findClass(ASM_BATTLE, NS_BATTLE_SOURCE, "CampaignGameModeSource");
    if (ctorClass) {
        const ctor = findMethod(ctorClass, ".ctor");
        if (ctor && !ctor.ptr.isNull()) {
            try {
                Interceptor.attach(ctor.ptr, {
                    onEnter(args) {
                        traceEnter("CampaignGameModeSource..ctor");
                        // Stash the `this` pointer for onLeave. We can't use
                        // it now (ctor body hasn't run, fields uninitialised)
                        // but the pointer itself is stable — il2cpp_object_new
                        // already happened.
                        this.selfPtr = ptr(args[0].toString());
                    },
                    onLeave() {
                        // ctor body finished → all fields (including
                        // _gameConfig at +0x90) are now valid. Safe to publish.
                        //
                        // #989 — CE N'EST PAS DE L'INJECTION PAR CONTENEUR, et le
                        // commentaire qui l'affirmait ici a nourri l'idee qu'un
                        // `Resolve` pourrait remplacer ce hook. Il n'y a AUCUN
                        // conteneur DI dans le binaire (`Zenject` = 0 symbole).
                        // `_gameConfig` est ecrit par le ctor lui-meme, depuis un
                        // champ du `ViewCommandExecutor` appelant. Voir
                        // `docs/rl/case-989-campaign-game-mode-source-transient.md`.
                        const self = this.selfPtr as NativePointer;
                        if (!self || self.isNull()) return;
                        const wasNull = campaignGameModeSourcePtr === null;
                        campaignGameModeSourcePtr = self;
                        log("[campaign-builder] captured (ctor) @ " + self);
                        if (wasNull) {
                            try { send({ t: "builder_ready", via: "ctor" }); }
                            catch { /* */ }
                        }
                    },
                });
                log("[+] CampaignGameModeSource..ctor (instance capture)");
            } catch (e) {
                log("[campaign-builder] ctor hook failed: " + (e as Error).message);
            }
        }
        // Same instance-capture pattern pour MachinesOfWarEventGameModeSource
        // — pour récupérer une BC contenant des MoW. User doit naviguer
        // manuellement vers le MoW Event in-game.
        const mowClass = findClass(ASM_BATTLE, NS_BATTLE_SOURCE,
            "MachinesOfWarEventGameModeSource");
        if (mowClass) {
            const mowCtor = findMethod(mowClass, ".ctor");
            if (mowCtor && !mowCtor.ptr.isNull()) {
                try {
                    Interceptor.attach(mowCtor.ptr, {
                        onEnter(args) {
                            this.selfPtr = ptr(args[0].toString());
                        },
                        onLeave() {
                            const self = this.selfPtr as NativePointer;
                            if (!self || self.isNull()) return;
                            const wasNull = mowEventGameModeSourcePtr === null;
                            mowEventGameModeSourcePtr = self;
                            log("[campaign-builder] MoWEvent captured (ctor) @ " + self);
                            if (wasNull) {
                                try { send({ t: "mow_builder_ready", via: "ctor" }); }
                                catch { /* */ }
                            }
                        },
                    });
                    log("[+] MachinesOfWarEventGameModeSource..ctor (instance capture)");
                } catch (e) {
                    log("[campaign-builder] MoW ctor hook failed: " + (e as Error).message);
                }
            }
            const mowLoadBattle = findMethod(mowClass, "LoadBattle");
            if (mowLoadBattle && !mowLoadBattle.ptr.isNull()) {
                try {
                    Interceptor.attach(mowLoadBattle.ptr, {
                        onEnter(args) {
                            const self = ptr(args[0].toString());
                            if (self.isNull()) return;
                            if (!mowEventGameModeSourcePtr
                                || !mowEventGameModeSourcePtr.equals(self)) {
                                const wasNull = mowEventGameModeSourcePtr === null;
                                mowEventGameModeSourcePtr = self;
                                log("[campaign-builder] MoWEvent captured (LoadBattle) @ " + self);
                                if (wasNull) {
                                    try { send({ t: "mow_builder_ready", via: "LoadBattle" }); }
                                    catch { /* */ }
                                }
                            }
                        },
                    });
                    log("[+] MachinesOfWarEventGameModeSource.LoadBattle (instance capture)");
                } catch (e) {
                    log("[campaign-builder] MoW LoadBattle hook failed: " + (e as Error).message);
                }
            }
        } else {
            log("[campaign-builder] MachinesOfWarEventGameModeSource class not found");
        }

        // Same pour PvpGameModeSource — pour Arena PvP. PvpGameModeSource n'a
        // pas de LoadBattle visible — on s'appuie sur ctor + StartBattle.
        const pvpClass = findClass(ASM_BATTLE, NS_BATTLE_SOURCE,
            "PvpGameModeSource");
        if (pvpClass) {
            const pvpCtor = findMethod(pvpClass, ".ctor");
            if (pvpCtor && !pvpCtor.ptr.isNull()) {
                try {
                    Interceptor.attach(pvpCtor.ptr, {
                        onEnter(args) {
                            this.selfPtr = ptr(args[0].toString());
                        },
                        onLeave() {
                            const self = this.selfPtr as NativePointer;
                            if (!self || self.isNull()) return;
                            const wasNull = pvpGameModeSourcePtr === null;
                            pvpGameModeSourcePtr = self;
                            log("[campaign-builder] Pvp captured (ctor) @ " + self);
                            if (wasNull) {
                                try { send({ t: "pvp_builder_ready", via: "ctor" }); }
                                catch { /* */ }
                            }
                        },
                    });
                    log("[+] PvpGameModeSource..ctor (instance capture)");
                } catch (e) {
                    log("[campaign-builder] Pvp ctor hook failed: " + (e as Error).message);
                }
            }
            // Hooks passifs sur plusieurs methods appelees pendant la battle.
            // Capture `this` au passage → zero cost, pas de heap scan.
            // Au moins un parmi ces hooks doit fire pendant une PvP battle :
            //   - get_BattleGameMode/get_Name : property getters, appeles
            //     par UI, runtime, save system
            //   - HandleTurnStarted : chaque turn
            //   - PreventAIControl/PreventHumanControl : chaque turn par player
            const pvpPassiveMethods = [
                "get_BattleGameMode", "get_Name", "HandleTurnStarted",
                "PreventAIControl", "PreventHumanControl", "StartBattle",
                "get_ControlsRunner",
            ];
            for (const methodName of pvpPassiveMethods) {
                const mi = findMethod(pvpClass, methodName);
                if (!mi || mi.ptr.isNull()) continue;
                try {
                    Interceptor.attach(mi.ptr, {
                        onEnter(args) {
                            const self = ptr(args[0].toString());
                            if (self.isNull()) return;
                            if (pvpGameModeSourcePtr !== null
                                && pvpGameModeSourcePtr.equals(self)) return;
                            const wasNull = pvpGameModeSourcePtr === null;
                            pvpGameModeSourcePtr = self;
                            if (wasNull) {
                                log(`[campaign-builder] Pvp captured (${methodName}) @ ` + self);
                                try { send({ t: "pvp_builder_ready", via: methodName }); }
                                catch { /* */ }
                            }
                        },
                    });
                    log(`[+] PvpGameModeSource.${methodName} (passive capture)`);
                } catch (e) {
                    log(`[campaign-builder] Pvp ${methodName} hook failed: ` + (e as Error).message);
                }
            }
        } else {
            log("[campaign-builder] PvpGameModeSource class not found");
        }

        // GuildBossGameModeSource — MEME PATRON que Pvp, et pour la meme raison : c'est la
        // SOURCE DU MODE qui sait produire sa propre `BattleConfiguration`.
        //
        // ⚠ POURQUOI CAPTER PLUTOT QUE FABRIQUER. `LoadBattleInternal` ne lit que 6 champs, et
        // on saurait tous les cabler -- mais il appelle `ApplyEnvironmentAbilitiesFromProgression`,
        // qui en exige 2 de plus (`ModifierProgression` +0x10, `Logger` +0x18) ET fait un appel
        // VIRTUEL sur `this` (vtable a +0x178). Une instance FABRIQUEE ferait dependre ce
        // dernier d'une vtable qu'on n'a pas verifiee ; une instance du JEU l'a par
        // construction. On capte.
        //
        // ⚠ On n'ancre AUCUNE des methodes qu'on invoquera (`LoadBattleInternal`) : ce serait
        // le gel garanti. Les portes ci-dessous sont des getters et des relais d'UI.
        const guildBossClass = findClass(ASM_BATTLE, NS_BATTLE_SOURCE, "GuildBossGameModeSource");
        if (guildBossClass) {
            const gbCtor = findMethod(guildBossClass, ".ctor");
            if (gbCtor && !gbCtor.ptr.isNull()) {
                try {
                    Interceptor.attach(gbCtor.ptr, {
                        onEnter(args) { this.selfPtr = ptr(args[0].toString()); },
                        onLeave() {
                            const self = this.selfPtr as NativePointer;
                            if (!self || self.isNull()) return;
                            // Meme controle qu'aux portes passives : un `.ctor` resolu sur la
                            // classe peut etre celui d'un PARENT si elle n'en declare pas.
                            try {
                                const k = self.readPointer();
                                if (k.isNull()) return;
                                if (s(class_get_name(k) as NativePointer)
                                    !== "GuildBossGameModeSource") return;
                            } catch { return; }
                            const wasNull = guildBossGameModeSourcePtr === null;
                            guildBossGameModeSourcePtr = self;
                            log("[campaign-builder] GuildBoss captured (ctor) @ " + self);
                            if (wasNull) {
                                try { send({ t: "guildboss_builder_ready", via: "ctor" }); }
                                catch { /* */ }
                            }
                        },
                    });
                    log("[+] GuildBossGameModeSource..ctor (instance capture)");
                } catch (e) {
                    log("[campaign-builder] GuildBoss ctor hook failed: " + (e as Error).message);
                }
            }
            // Captures passives : `this` au passage, cout nul, aucun heap scan.
            //
            // ⛔ LA CLASSE EST CONFRONTEE AVANT DE RETENIR, ET CE N'EST PAS UNE PRECAUTION DE
            // STYLE. Mesure le 2026-08-17 : sans ce controle, la capture retenait un pointeur
            // dont AUCUN des huit champs attendus n'etait lisible -- parce que ces getters sont
            // HERITES et qu'IL2CPP partage UN SEUL corps entre toutes les sources. Le hook
            // attrapait donc le `this` d'une autre `*GameModeSource`, et le probe repondait
            // `pret: true` dessus. Invoquer `LoadBattleInternal` sur cet objet aurait execute
            // du natif sur une disposition memoire etrangere.
            const nomAttendu = "GuildBossGameModeSource";
            for (const methodName of ["get_BattleGameMode", "get_Name", "HandleTurnStarted",
                                      "GetBattleLineup", "IsUnitDeployable",
                                      "get_ControlsRunner"]) {
                const mi = findMethod(guildBossClass, methodName);
                if (!mi || mi.ptr.isNull()) continue;
                try {
                    Interceptor.attach(mi.ptr, {
                        onEnter(args) {
                            const self = ptr(args[0].toString());
                            if (self.isNull()) return;
                            if (guildBossGameModeSourcePtr !== null
                                && guildBossGameModeSourcePtr.equals(self)) return;
                            // Corps PARTAGE : confronter la classe reelle, sinon on retient
                            // la source d'un autre mode.
                            let nom: string | null = null;
                            try {
                                const k = self.readPointer();
                                if (!k.isNull()) nom = s(class_get_name(k) as NativePointer);
                            } catch { return; }
                            if (nom !== nomAttendu) return;
                            const wasNull = guildBossGameModeSourcePtr === null;
                            guildBossGameModeSourcePtr = self;
                            if (wasNull) {
                                log(`[campaign-builder] GuildBoss captured (${methodName}) @ `
                                    + self);
                                try { send({ t: "guildboss_builder_ready", via: methodName }); }
                                catch { /* */ }
                            }
                        },
                    });
                    log(`[+] GuildBossGameModeSource.${methodName} (passive capture)`);
                } catch (e) {
                    log(`[campaign-builder] GuildBoss ${methodName} hook failed: `
                        + (e as Error).message);
                }
            }
        } else {
            log("[campaign-builder] GuildBossGameModeSource class not found");
        }

        const loadBattle = findMethod(ctorClass, "LoadBattle");
        if (loadBattle && !loadBattle.ptr.isNull()) {
            try {
                Interceptor.attach(loadBattle.ptr, {
                    onEnter(args) {
                        traceEnter("CampaignGameModeSource.LoadBattle");
                        const self = ptr(args[0].toString());
                        if (self.isNull()) return;
                        if (!campaignGameModeSourcePtr || !campaignGameModeSourcePtr.equals(self)) {
                            const wasNull = campaignGameModeSourcePtr === null;
                            campaignGameModeSourcePtr = self;
                            log("[campaign-builder] captured (LoadBattle) @ " + self);
                            if (wasNull) {
                                try { send({ t: "builder_ready", via: "LoadBattle" }); }
                                catch { /* */ }
                            }
                        }
                    },
                });
                log("[+] CampaignGameModeSource.LoadBattle (instance capture)");
            } catch (e) {
                log("[campaign-builder] LoadBattle hook failed: " + (e as Error).message);
            }
        }
    } else {
        log("[campaign-builder] CampaignGameModeSource class not found");
    }

    // BattleConfigBuilder hook removed: it captured the builder + delegate
    // for path 1 (direct GetCampaignLevelConfig invoke). Path 2 (mute mode
    // + progression-swap) doesn't need either — it works directly off the
    // live CampaignGameModeSource and its real Zenject-injected dependencies.

    // RandomGenerator broad-hook DISABLED — was used to populate the
    // `_random` field of a DIY-constructed BattleConfigBuilder for path 1.
    // Path 2 (progression-swap mute) doesn't need a DIY builder — the live
    // CampaignGameModeSource already has a fully-injected one. Removing the
    // broad-hook on Get/Initialize/Next/Set/Roll/Range methods that were
    // firing constantly during natural gameplay (every random roll, every
    // UI animation, etc.) — they're called many thousands of times per
    // battle build.

    // Capture UnitProgression via UnitProgression.GetUnit(string) — that
    // method fires on every UI render that needs a unit (home screen, hero
    // panels, ...), so it's caught within seconds after inject. Used to
    // synthesize the Func<string,IUnitModel> delegate without needing the
    // game to call GetCampaignLevelConfig naturally.
    const upClass = findClassAnywhere(
        "IdunMetaLogic.UserProgress", "UnitProgression");
    if (upClass) {
        // Pick the right method to bind for `getEnemyUnit` delegate:
        //   - GetNpcUnit(string) → resolves NPC units from static config,
        //     independent of user progression. CRITICAL for events the
        //     user never unlocked (returns valid IUnitModel anyway).
        //   - GetUnit(string) → resolves from user's progression; returns
        //     null for any unit not unlocked. Causes downstream null derefs.
        // The param is named `getEnemyUnit` in GetCampaignLevelConfig — for
        // NPCs (campaign enemies), GetNpcUnit is the correct resolver.
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let candidate: NativePointer | null = null;
        let allCandidates = "";
        let m: NativePointer;
        while (!(m = class_get_methods(upClass, it) as NativePointer).isNull()) {
            const name = s(method_get_name(m) as NativePointer);
            if (name === "GetNpcUnit") {
                const pc = method_get_param_count(m) as number;
                allCandidates += name + "/" + pc + " ";
                // The 1-arg overload (string unitId) matches Func<string,IUnitModel>.
                if (pc === 1) { candidate = m; }
            }
        }
        // Note: previously we hooked ~20 Get*/Has*/Is*/Compute*/Try/Find/Update
        // methods to broadly capture a UnitProgression instance. This was
        // unstable: those methods are called by every UI screen (popups, hero
        // panels, …) and the cumulative trampoline overhead destabilised the
        // game during cctor cascades (live event popup close → crash).
        // The specific hook on GetUnit below is sufficient — it fires within
        // milliseconds of any unit-rendering UI activity.
        if (candidate !== null) {
            const entry = methodEntry(candidate);
            getUnitMi = { info: candidate, ptr: entry };
            if (!entry.isNull()) {
                try {
                    Interceptor.attach(entry, {
                        onEnter(args) {
                            traceEnter("UnitProgression.GetUnit", 100);
                            if (unitProgressionPtr === null) {
                                const self = ptr(args[0].toString());
                                if (!self.isNull()) {
                                    // No gcRoot pin needed: UnitProgression
                                    // is a player-side singleton, rooted by
                                    // the game's own references. Boehm GC
                                    // (IL2CPP) is non-moving, so the ptr is
                                    // stable for the process lifetime.
                                    unitProgressionPtr = self;
                                    log("[campaign-builder] captured UnitProgression @ "
                                        + self + " (via GetUnit)");
                                }
                            }
                        },
                    });
                    log("[+] UnitProgression.GetUnit (instance capture)");
                } catch (e) {
                    log("[campaign-builder] GetUnit hook failed: "
                        + (e as Error).message);
                }
            }
        } else {
            log("[campaign-builder] UnitProgression.GetNpcUnit(1-arg) not found · candidates: "
                + (allCandidates || "(none)"));
        }
    } else {
        log("[campaign-builder] UnitProgression class not found");
    }

    // GameConfigDto capture: previously hooked GameConfigData.get_gameConfigDto
    // to capture the singleton on first call. Removed — that getter is invoked
    // hundreds of times per Newtonsoft serialization the game does internally
    // (~1700 calls in 62 ms observed via traceEnter), and our hook overhead
    // amplified Tacticus's natural cctor cascade into a hard crash. Heap scan
    // (findGameConfigDtoViaHeap) finds the singleton in ~11 s post-inject,
    // which is fast enough — and zero hot-path overhead.

    /** Dump the entire campaign catalog as Newtonsoft JSON. Doesn't require
     * a CampaignGameModeSource — uses the GameConfigDto captured from
     * UserProgression..ctor (available from game boot). */
    ctx.rpc.dumpCampaignCatalog = async (opts?: { allowHeapScan?: boolean }) => {
        // Prefer the directly-captured GameConfigDto. Fall back to the one
        // referenced by a live CampaignGameModeSource — unwrap the
        // GameConfigData service if needed. Heap scan only when caller opts
        // in (↻ button); chunked async donc safe (~30s avec yield).
        let gameConfig: NativePointer | null = lastGameConfig;
        if (gameConfig === null && campaignGameModeSourcePtr !== null && ensureCgmsResolved()) {
            const p = campaignGameModeSourcePtr.add(offGameConfig).readPointer();
            const dto = unwrapGameConfig(p);
            if (dto !== null) {
                gameConfig = dto;
                lastGameConfig = dto;
            }
        }
        if (gameConfig === null && opts?.allowHeapScan) {
            const scanned = await findGameConfigDtoViaHeap();
            if (scanned !== null) {
                lastGameConfig = scanned;
                gameConfig = scanned;
            }
        }
        return queueOnMainThread(() => {
        if (gameConfig === null) {
            throw new Error("GameConfigDto not captured. Click any campaign battle in-game to trigger natural capture. If the issue persists, click the ↻ button which forces a heap scan (10 s game freeze).");
        }
        if (!ensureGameConfigChainResolved(gameConfig)) {
            throw new Error("gameConfig → battles → campaigns chain resolution failed");
        }
        const battlesPtr = gameConfig.add(offBattles).readPointer();
        const campaignsPtr = battlesPtr.add(offCampaigns).readPointer();
        const json = serializeToJson(campaignsPtr);
        if (!json) throw new Error("JsonConvert.SerializeObject(campaigns) returned null");
        return { bytes: json.length, json };
        });
    };

    /** Build a BattleConfiguration for an arbitrary campaign node.
     *
     * Two paths, in order of preference:
     *   1. Delegate path — if we've captured a BattleConfigBuilder and a
     *      Func<string,IUnitModel> from a natural game call, invoke
     *      GetCampaignLevelConfig directly. No CampaignGameModeSource
     *      mutation, no LoadBattle side-effects, no funnel events.
     *   2. Mute path — fallback: mutate campaignGameModeSourcePtr (CampaignGameModeSource)
     *      and call LoadBattle(true). Required when we haven't yet captured
     *      a delegate (game is on home screen, never opened a campaign).
     */
    ctx.rpc.buildCampaignConfig = (args: {
        campaignType: number;
        campaignId: string;
        locationIndex: number;
    }) => queueOnMainThread(() => {
        // Resolve target CampaignConfigDto via gameConfig.battles.campaigns.
        let gameConfig: NativePointer | null = lastGameConfig;
        if (gameConfig === null && campaignGameModeSourcePtr !== null && ensureCgmsResolved()) {
            const p = campaignGameModeSourcePtr.add(offGameConfig).readPointer();
            const dto = unwrapGameConfig(p);
            if (dto !== null) {
                gameConfig = dto;
                lastGameConfig = dto;
            }
        }
        if (gameConfig === null) {
            // Heap scan async sera disponible via le RPC discoverSources
            // (chunked, safe pour Tacticus). Pas de fallback inline ici car
            // queueOnMainThread est sync et bloquerait le main thread.
            throw new Error("no GameConfigDto captured yet — call `discoverSources` RPC first to trigger smooth heap scan, then retry");
        }
        if (!ensureGameConfigChainResolved(gameConfig)) {
            throw new Error("gameConfig chain resolution failed");
        }
        const battlesPtr = gameConfig.add(offBattles).readPointer();
        const campaignsPtr = battlesPtr.add(offCampaigns).readPointer();

        // GetCampaign(type, id) → CampaignBattlesConfig
        const boxedType = Memory.alloc(8);
        boxedType.writeU64(uint64(args.campaignType));
        const idStr = createManagedString(args.campaignId);
        const cbc = invokeMethod(getCampaignMi!.info, campaignsPtr, [boxedType, idStr]);
        if (cbc.isNull()) {
            throw new Error(`GetCampaign(${args.campaignType}, "${args.campaignId}") returned null`);
        }
        if (!ensureCampaignBattlesConfigResolved(cbc)) {
            throw new Error("CampaignBattlesConfig resolution failed");
        }
        const battlesList = cbc.add(offCampaignBattles).readPointer();
        const targetMatch = listGet(battlesList, args.locationIndex);
        if (targetMatch.isNull()) {
            throw new Error(`battles[${args.locationIndex}] is null`);
        }

        let json: string | null = null;
        const pathUsed = "mute";

        // Resolve the live CampaignGameModeSource. Captured at amorce via the
        // ctor.onLeave hook. Heap-scan fallback covers re-injection after the
        // user already navigated into a campaign (rare).
        let sourcePtr = campaignGameModeSourcePtr;
        // Pas de fallback heap scan ici (sync queueOnMainThread bloquerait
        // le main thread). Si null, l'user doit call `discoverSources` RPC.
        // Path 2 (mute + progression-swap). The source has
        // source._campaignProgression (offset 0x20) pointing to a
        // CampaignProgression for the user's current chapter. LoadBattle
        // reads its _battlesConfigCampaigns[locIdx] field. To build any
        // config (inactive events included) we temporarily swap that list
        // + _campaignType + _campaignId on the live progression instance,
        // call LoadBattle, then restore. The swap window is a single
        // synchronous queueOnMainThread invocation — no other code observes
        // the swapped state.
        if (sourcePtr !== null && ensureCgmsResolved()) {
            log("[campaign-builder] entering mute path on source @ " + sourcePtr);
            // Per-faction amorce — pre-resolve the metadata for each enemy
            // unit class referenced by this match. Without this, building
            // a campaign of a faction the user hasn't touched (e.g. tyranid
            // event after warming up via Indomitus/necron) crashes the same
            // way as cold-start for path 1.
            const precharges = prechargerUnitesCibles(targetMatch);
            if (precharges > 0) {
                log("[campaign-builder] warmed up " + precharges
                    + " unit classes via UnitProgression.GetUnit");
            }
            const origCampaignId = sourcePtr.add(offCurrentCampaignId).readPointer();
            const origLocationIndex = sourcePtr.add(offCurrentLocationIndex).readS32();
            const origMatch = sourcePtr.add(offCurrentMatch).readPointer();
            const origBattle = sourcePtr.add(offCurrentBattle).readPointer();
            // Dump all source fields to verify it's a real instance (not a
            // Zenject placeholder with garbage). Show first 0x100 bytes of
            // the object header.
            log(`[campaign-builder] mute source fields: `
                + `gameConfig@${offGameConfig.toString(16)}=${sourcePtr.add(offGameConfig).readPointer()} `
                + `campaignId@${offCurrentCampaignId.toString(16)}=${origCampaignId} `
                + `locIdx@${offCurrentLocationIndex.toString(16)}=${origLocationIndex} `
                + `match@${offCurrentMatch.toString(16)}=${origMatch} `
                + `battle@${offCurrentBattle.toString(16)}=${origBattle}`);
            log("[campaign-builder] mute: orig state captured, mutating + invoking LoadBattle");

            // PROGRESSION CONTROLLER SWAP. The progression instance at
            // source[+0x20] is shared and live; we restore it in the finally
            // block. Swapped fields (CampaignProgression layout, dump.cs
            // line 546873):
            //   +0x18 = _campaignType (CampaignType enum, 4 bytes)
            //   +0x28 = _campaignId (string ptr)
            //   +0x88 = _battlesConfigCampaigns (List<CampaignConfigDto> ptr)
            const PROGRESSION_OFF_TYPE = 0x18;
            const PROGRESSION_OFF_ID = 0x28;
            const PROGRESSION_OFF_BATTLES = 0x88;
            const progPtr = sourcePtr.add(0x20).readPointer();
            const origProgType = !progPtr.isNull()
                ? progPtr.add(PROGRESSION_OFF_TYPE).readS32() : -1;
            const origProgId = !progPtr.isNull()
                ? progPtr.add(PROGRESSION_OFF_ID).readPointer() : ptr(0);
            const origProgBattles = !progPtr.isNull()
                ? progPtr.add(PROGRESSION_OFF_BATTLES).readPointer() : ptr(0);
            const swapApplied = !progPtr.isNull();
            if (swapApplied) {
                log(`[campaign-builder] swapping progression @ ${progPtr}: `
                    + `type ${origProgType} → ${args.campaignType}, `
                    + `id ${origProgId} → "${args.campaignId}", `
                    + `battlesList ${origProgBattles} → ${battlesList}`);
                progPtr.add(PROGRESSION_OFF_TYPE).writeS32(args.campaignType);
                progPtr.add(PROGRESSION_OFF_ID).writePointer(
                    createManagedString(args.campaignId));
                progPtr.add(PROGRESSION_OFF_BATTLES).writePointer(battlesList);
            }
            try {
                const newCampaignIdStr = createManagedString(args.campaignId);
                sourcePtr.add(offCurrentCampaignId).writePointer(newCampaignIdStr);
                sourcePtr.add(offCurrentLocationIndex).writeS32(args.locationIndex);
                sourcePtr.add(offCurrentMatch).writePointer(targetMatch);
                sourcePtr.add(offCurrentBattle).writePointer(ptr(0));
                const isRestartArg = Memory.alloc(8);
                isRestartArg.writeU64(uint64(1));
                const t0 = Date.now();
                const battleConfig = invokeMethod(loadBattleMi!.info, sourcePtr, [isRestartArg]);
                log("[campaign-builder] mute: LoadBattle returned " + battleConfig
                    + " (took " + (Date.now() - t0) + " ms)");
                if (battleConfig.isNull()) throw new Error("LoadBattle returned null");
                json = serializeToJson(battleConfig);
                if (!json) throw new Error("SerializeObject(BattleConfiguration) returned null");
                log("[campaign-builder] mute: serialized to " + json.length + " bytes");
            } finally {
                // Restore source.
                sourcePtr.add(offCurrentCampaignId).writePointer(origCampaignId);
                sourcePtr.add(offCurrentLocationIndex).writeS32(origLocationIndex);
                sourcePtr.add(offCurrentMatch).writePointer(origMatch);
                sourcePtr.add(offCurrentBattle).writePointer(origBattle);
                // Restore progression — critical to avoid leaving the live
                // progression in a corrupted state for the rest of the game.
                if (swapApplied && !progPtr.isNull()) {
                    progPtr.add(PROGRESSION_OFF_TYPE).writeS32(origProgType);
                    progPtr.add(PROGRESSION_OFF_ID).writePointer(origProgId);
                    progPtr.add(PROGRESSION_OFF_BATTLES).writePointer(origProgBattles);
                    log("[campaign-builder] progression restored");
                }
            }
            return { campaignType: args.campaignType, campaignId: args.campaignId,
                     locationIndex: args.locationIndex, path: pathUsed,
                     bytes: json!.length, json: json! };
        }

        throw new Error("no live CampaignGameModeSource captured — open any campaign world map in-game and click a battle to warm up. Then retry.");
    });

    /** Diagnostic — what's available to the builder right now.
     *   hasGameConfig       → catalog dump works (lastGameConfig captured)
     *   hasUnitProgression  → per-faction amorce is possible
     *   hasInstance         → path 2 mute progression-swap is ready
     * Build needs `hasInstance` (campaignGameModeSourcePtr captured = user clicked a battle
     * once in-game). The frontend polls this every 5 s. Cheap by design —
     * never triggers heap scans. */
    /** ⚠ `hasGameConfig` signifie « un vrai `GameConfigDto` est capté », rien d'autre. Il a
     *  déjà rendu `true` sur un pointeur inexploitable, et ce vert-là a fait chercher la panne
     *  dans la chaîne alors qu'elle était à la capture. Le brut et la RAISON sont publiés à
     *  part, pour que l'échec se lise sans ouvrir la console Frida. */
    ctx.rpc.campaignBuilderStatus = () => ({
        hasGameConfig: lastGameConfig !== null,
        hasUnitProgression: unitProgressionPtr !== null,
        hasInstance: campaignGameModeSourcePtr !== null,
        instance: campaignGameModeSourcePtr ? campaignGameModeSourcePtr.toString() : null,
        gameConfig: lastGameConfig ? lastGameConfig.toString() : null,
        gameConfigBrut: lastGameConfigBrut ? lastGameConfigBrut.toString() : null,
        classeBrute: lastGameConfigBrut ? klassName(lastGameConfigBrut) : null,
        raisonUnwrap,
    });

    /** POURQUOI un nœud de campagne est INJOUABLE — la CAUSE, pas le symptôme (#599-r1).
     *
     *  Le jeu GRISE le bouton d'un nœud injouable. Notre outillage ne peut pas le voir :
     *  `uiList` n'énumère que des `UnityEngine.UI.Button`, jamais l'`Image` d'habillage ni
     *  l'icône de verrou qui vivent DANS le bouton — et le grisé n'est pas l'état désactivé du
     *  `Selectable` (le nœud 2, injouable, rapporte `interactable: true`). Mesuré à la dure :
     *  cinq clics sur ce nœud, cinq `ok:true`, rien ne s'ouvre.
     *
     *  On lit donc les prédicats que le jeu lui-même consulte, sur
     *  `IdunMetaLogic.UserProgress.CampaignProgression` — l'instance vit à `_campaignProgression`
     *  sur le `CampaignGameModeSource` capturé a l'amorce. Tri-état : `null` = PAS MESURÉ
     *  (méthode irrésolue ou invoke en faute), jamais rabattu sur `false` — un `false` muet se
     *  lirait « ce nœud est verrouillé » et ferait renoncer à une bataille jouable.
     *
     *  body: { locationIndex } — 0-BASÉ, comme `buildCampaignConfig` (nœud 14 => 13). */
    ctx.rpc.campaignNodeState = (
        body?: { locationIndex?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        const loc = body?.locationIndex;
        if (typeof loc !== "number") return { ok: false, error: "passer locationIndex (0-base)" };
        const src = campaignGameModeSourcePtr;
        if (src === null) {
            return { ok: false, error: "aucun CampaignGameModeSource capture — amorce requis" };
        }
        // Offset résolu PAR NOM sur la classe réelle : une constante en dur survivrait au
        // changement de build et lirait un champ voisin comme si c'était la progression.
        const srcKlass = src.readPointer();
        const offProg = getFieldOffset(srcKlass, "_campaignProgression");
        if (offProg < 0) {
            return { ok: false, error: "_campaignProgression absent de la classe source" };
        }
        const prog = src.add(offProg).readPointer();
        if (prog.isNull()) return { ok: false, error: "_campaignProgression nul" };
        const klass = prog.readPointer();

        const arg = Memory.alloc(4); arg.writeS32(loc);
        const layout: Record<string, unknown> = { offCampaignProgression: offProg };
        /** Invoque `nom(locationIndex)` ou `nom()`, et décode le retour BOXÉ (valeur @+0x10). */
        const appel = (nom: string, avecArg: boolean): number | boolean | null => {
            const mi = findMethodByParamCount(klass, nom, avecArg ? 1 : 0);
            layout[nom] = !!mi;
            if (!mi) return null;
            try {
                const r = invokeMethod(mi.info, prog, avecArg ? [arg] : []);
                if (r.isNull()) return null;
                return r.add(0x10).readS32();
            } catch { return null; }
        };
        const bool = (v: number | boolean | null): boolean | null =>
            v === null ? null : !!v;

        const isLocationReached = bool(appel("IsLocationReached", true));
        const hasTokens = bool(appel("HasTokensToPlayCampaignBattle", true));
        const hasStamina = bool(appel("HasStaminaToPlayCampaignBattle", true));
        const isLocked = bool(appel("IsLocked", false));
        const isInCampaignTutorial = bool(appel("IsInCampaignTutorial", false));
        const hasWon = bool(appel("HasWonLocation", true));
        const timesWon = appel("GetTimesWon", true);
        const timesLost = appel("GetTimesLost", true);
        const stars = appel("GetStarsOfLocation", true);

        // Le PREMIER motif qui bloque, dans l'ordre où le jeu les oppose. `null` (pas mesuré)
        // n'est jamais compté comme un blocage : on ne refuse pas sur ce qu'on n'a pas lu.
        let bloqueur: string | null = null;
        if (isLocked === true) bloqueur = "IsLocked";
        else if (isLocationReached === false) bloqueur = "!IsLocationReached";
        else if (hasTokens === false) bloqueur = "!HasTokensToPlayCampaignBattle";
        else if (hasStamina === false) bloqueur = "!HasStaminaToPlayCampaignBattle";

        return {
            ok: true, locationIndex: loc, noeud: loc + 1,
            isLocked, isLocationReached, hasTokens, hasStamina, isInCampaignTutorial,
            hasWon, timesWon, timesLost, stars,
            bloqueur,
            // `bloqueur === null` ne dit PAS « jouable » : il dit « aucun des quatre motifs
            // LUS ne bloque ». Le nœud de tutoriel, lui, n'est refusé par aucun d'eux.
            verdict: bloqueur === null ? "aucun des motifs lus ne bloque" : "BLOQUE : " + bloqueur,
            layout,
        };
    });
}
