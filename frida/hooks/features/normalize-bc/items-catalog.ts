// Item catalog reader + Best-In-Slot picker.
//
// Walks `gameConfig.items` (`Dictionary<ItemConfigId, ItemConfigDto>`) and
// `gameConfig.units.lineup` (`Dictionary<string, LineupUnitConfigDto>`) once,
// caches everything as JS records, then computes BiS items per unit/slot
// at a given rarity cap.
//
// IL2CPP Dictionary<K,V> layout (Unity 6, x64):
//   +0x10  _buckets : int[]
//   +0x18  _entries : Entry[]
//   +0x20  _count   : int             (entry array logical size)
//   +0x24  _freeList : int
//   +0x28  _freeCount : int
// We discover offsets at runtime via class_get_fields to survive layout
// drift across Unity builds.
//
// Entry<K,V> layout (Mono/.NET):
//   +0x00  hashCode : int
//   +0x04  next     : int
//   +0x08  key      : K
//   +pad   value    : V   (with K's alignment requirements)
// For Dictionary<ItemConfigId, ItemConfigDto>:
//   ItemConfigId is `struct { string _value }` = 8 bytes (pointer)
//   ItemConfigDto is a ref type = 8-byte pointer
//   Entry size = 4 + 4 + 8 + 8 = 24 bytes (aligned to 8)

import {
    class_get_fields, class_get_parent, field_get_name, field_get_offset,
    findMethodByParamCount, readIl2cppString, s as cstr,
} from "../../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../../il2cpp/invoke.js";
import { getLastGameConfig } from "../campaign-builder.js";
import { log } from "../../runtime/diag.js";
import { ARRAY_OFF_DATA, LIST_OFF_ITEMS, LIST_OFF_SIZE } from "./live-bc.js";

interface DictFieldOffsets {
    entries: number;
    count: number;
}

const _dictOffsetsCache = new Map<string, DictFieldOffsets>();

function resolveDictOffsets(dictClass: NativePointer): DictFieldOffsets | null {
    const key = dictClass.toString();
    const cached = _dictOffsetsCache.get(key);
    if (cached) return cached;
    let entriesOff = -1, countOff = -1;
    try {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        let klass: NativePointer | null = dictClass;
        while (klass && !klass.isNull() && (entriesOff < 0 || countOff < 0)) {
            it.writePointer(ptr(0));
            while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
                const name = cstr(field_get_name(f) as NativePointer);
                const off = field_get_offset(f) as number;
                if (name === "_entries") entriesOff = off;
                else if (name === "_count") countOff = off;
            }
            klass = class_get_parent(klass) as NativePointer;
        }
    } catch { /* leave -1 */ }
    if (entriesOff < 0 || countOff < 0) return null;
    const res: DictFieldOffsets = { entries: entriesOff, count: countOff };
    _dictOffsetsCache.set(key, res);
    return res;
}

export interface ItemCatalogEntry {
    configId: string;
    itemType: number;
    rarity: number;
    starLvl: number;
    levelCount: number;
    isRelic: boolean;
    allowedFactions: string[];
    allowedUnits: string[];
}

let _itemCatalog: ItemCatalogEntry[] | null = null;

export const ITEM_TYPE_NAMES = [
    "I_Crit", "I_Block", "I_Defensive", "I_Booster_Crit", "I_Booster_Block",
    "Weapon_Warrior", "Weapon_Mage", "Weapon_Rogue",
    "Armor_Mage", "Armor_Rogue", "Armor_Warrior",
    "Shield_All", "Trinket_All", "Ring_All",
];
export const ITEM_RARITY_NAMES = [
    "Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic",
];

// ItemConfigDto field offsets (see dump.cs TypeDefIndex 17426).
const ICD_OFF_ITEM_TYPE = 0x10;        // ItemType (int)
const ICD_OFF_RARITY = 0x14;           // ItemRarity (int)
const ICD_OFF_STAR_LVL = 0x18;         // int
const ICD_OFF_LEVELS = 0x20;           // List<ItemLevelConfigDto>
const ICD_OFF_ALLOWED_FACTIONS = 0x28; // List<string>
const ICD_OFF_ALLOWED_UNITS = 0x30;    // List<string>
const ICD_OFF_IS_RELIC = 0x38;         // bool

function readManagedStringList(listPtr: NativePointer): string[] {
    if (listPtr.isNull()) return [];
    try {
        const arr = listPtr.add(LIST_OFF_ITEMS).readPointer();
        const size = listPtr.add(LIST_OFF_SIZE).readS32();
        if (arr.isNull() || size <= 0 || size > 10000) return [];
        const out: string[] = [];
        for (let i = 0; i < size; i++) {
            const sp = arr.add(ARRAY_OFF_DATA + i * Process.pointerSize)
                .readPointer();
            if (sp.isNull()) continue;
            const s = readIl2cppString(sp);
            if (s) out.push(s);
        }
        return out;
    } catch { return []; }
}

function readListSize(listPtr: NativePointer): number {
    if (listPtr.isNull()) return 0;
    try { return listPtr.add(LIST_OFF_SIZE).readS32(); }
    catch { return 0; }
}

/** Build the items catalog from `gameConfig.items` by walking the dict
 *  _entries array directly. Cached after first call. */
export function buildItemCatalog(): {
    ok: boolean; err?: string; count?: number;
} {
    if (_itemCatalog) return { ok: true, count: _itemCatalog.length };
    const gameConfig = getLastGameConfig();
    if (!gameConfig) return { ok: false, err: "no lastGameConfig captured" };

    const itemsDict = gameConfig.add(0x18).readPointer();
    if (itemsDict.isNull()) return { ok: false, err: "gameConfig.items null" };
    const dictClass = itemsDict.readPointer();
    const off = resolveDictOffsets(dictClass);
    if (!off) return { ok: false, err: "couldn't resolve Dictionary offsets" };

    const entriesArr = itemsDict.add(off.entries).readPointer();
    if (entriesArr.isNull()) return { ok: false, err: "_entries array null" };
    const count = itemsDict.add(off.count).readS32();
    if (count <= 0 || count > 100000) {
        return { ok: false, err: `implausible items count: ${count}` };
    }

    const ENTRY_SIZE = 24;
    const ENTRY_KEY_OFF = 8;   // ItemConfigId = struct{string} → string ptr at +8
    const ENTRY_VAL_OFF = 16;  // ref ptr
    const catalog: ItemCatalogEntry[] = [];

    for (let i = 0; i < count; i++) {
        try {
            const entry = entriesArr.add(ARRAY_OFF_DATA + i * ENTRY_SIZE);
            const hashCode = entry.readS32();
            if (hashCode === 0) continue; // free slot in entries[]
            const keyPtr = entry.add(ENTRY_KEY_OFF).readPointer();
            if (keyPtr.isNull()) continue;
            const configId = readIl2cppString(keyPtr);
            if (!configId) continue;
            const value = entry.add(ENTRY_VAL_OFF).readPointer();
            if (value.isNull()) continue;
            catalog.push({
                configId,
                itemType: value.add(ICD_OFF_ITEM_TYPE).readS32(),
                rarity: value.add(ICD_OFF_RARITY).readS32(),
                starLvl: value.add(ICD_OFF_STAR_LVL).readS32(),
                levelCount: readListSize(
                    value.add(ICD_OFF_LEVELS).readPointer()),
                isRelic: value.add(ICD_OFF_IS_RELIC).readU8() !== 0,
                allowedFactions: readManagedStringList(
                    value.add(ICD_OFF_ALLOWED_FACTIONS).readPointer()),
                allowedUnits: readManagedStringList(
                    value.add(ICD_OFF_ALLOWED_UNITS).readPointer()),
            });
        } catch { /* skip malformed entry */ }
    }

    _itemCatalog = catalog;
    log(`[normalize-bc] built item catalog: ${catalog.length} items` +
        ` (dict count=${count})`);
    return { ok: true, count: catalog.length };
}

export function getCachedCatalog(): ItemCatalogEntry[] | null {
    return _itemCatalog;
}

interface UnitSlotsCache {
    slots: number[];  // ItemType enum values, one per slot (typically 3)
    faction: string | null;
}

const _unitSlotsCache = new Map<string, UnitSlotsCache | null>();
let _lineupTryGetMi: { info: NativePointer; ptr: NativePointer } | null = null;
let _lineupResolved = false;

function getUnitItemSlots(unitId: string): UnitSlotsCache | null {
    if (_unitSlotsCache.has(unitId)) {
        return _unitSlotsCache.get(unitId) ?? null;
    }
    const gameConfig = getLastGameConfig();
    if (!gameConfig) return null;
    try {
        const unitsConfig = gameConfig.add(0x40).readPointer();
        if (unitsConfig.isNull()) return null;
        const lineupDict = unitsConfig.add(0x10).readPointer(); // .lineup
        if (lineupDict.isNull()) return null;

        if (!_lineupResolved) {
            _lineupResolved = true;
            const dictClass = lineupDict.readPointer();
            _lineupTryGetMi = findMethodByParamCount(dictClass, "TryGetValue", 2);
        }
        if (!_lineupTryGetMi) return null;

        const keyStr = createManagedString(unitId);
        const outBuf = Memory.alloc(Process.pointerSize);
        outBuf.writePointer(ptr(0));
        const okRet = invokeMethod(_lineupTryGetMi.info, lineupDict,
            [keyStr, outBuf]) as NativePointer;
        // ret is boxed bool — heap-allocated. Quick deref to its byte.
        const found = !okRet.isNull() && okRet.add(0x10).readU8() !== 0;
        if (!found) {
            _unitSlotsCache.set(unitId, null);
            return null;
        }
        const lineup = outBuf.readPointer();
        if (lineup.isNull()) {
            _unitSlotsCache.set(unitId, null);
            return null;
        }
        // LineupUnitConfigDto.itemSlots at 0xB0 (List<ItemType> = List<int>)
        const slotsList = lineup.add(0xB0).readPointer();
        const slots: number[] = [];
        if (!slotsList.isNull()) {
            const arr = slotsList.add(LIST_OFF_ITEMS).readPointer();
            const size = slotsList.add(LIST_OFF_SIZE).readS32();
            if (!arr.isNull() && size > 0 && size < 100) {
                // List<int> stores int[] inline at +0x20, each 4 bytes
                for (let i = 0; i < size; i++) {
                    slots.push(arr.add(ARRAY_OFF_DATA + i * 4).readS32());
                }
            }
        }
        const cached: UnitSlotsCache = { slots, faction: null };
        _unitSlotsCache.set(unitId, cached);
        return cached;
    } catch (e) {
        log(`[normalize-bc] getUnitItemSlots(${unitId}) error: ${(e as Error).message}`);
        _unitSlotsCache.set(unitId, null);
        return null;
    }
}

interface BisOpts {
    rarityCap: number;     // 0-5
    faction: string;       // unit's faction
    excludeRelics?: boolean; // default true
}

function pickBisForSlot(
    slotType: number, unitId: string, opts: BisOpts,
): ItemCatalogEntry | null {
    if (!_itemCatalog) return null;
    let best: ItemCatalogEntry | null = null;
    for (const item of _itemCatalog) {
        if (item.itemType !== slotType) continue;
        if (item.rarity > opts.rarityCap) continue;
        if (opts.excludeRelics !== false && item.isRelic) continue;
        if (item.allowedFactions.length > 0
            && !item.allowedFactions.includes(opts.faction)) continue;
        if (item.allowedUnits.length > 0
            && !item.allowedUnits.includes(unitId)) continue;
        // Prefer higher rarity, then higher starLvl, then higher levelCount.
        if (!best
            || item.rarity > best.rarity
            || (item.rarity === best.rarity && item.starLvl > best.starLvl)
            || (item.rarity === best.rarity && item.starLvl === best.starLvl
                && item.levelCount > best.levelCount)) {
            best = item;
        }
    }
    return best;
}

/** Build itemSpecs for a list of (unitId, faction) pairs at a given rarity
 *  cap. Each unit gets up to N items (one per slot) picked at max rarity. */
export function buildBisItemSpecs(args: {
    units: Array<{ unitId: string; faction: string }>;
    rarityCap?: number;
    excludeRelics?: boolean;
}): {
    ok: boolean;
    err?: string;
    catalogCount?: number;
    itemSpecs: Record<string, Array<{ configId: string; level: number }>>;
    perUnit: Array<{
        unitId: string;
        slotTypes: number[];
        items: Array<{ slot: number; configId: string | null; rarity: number;
                       starLvl: number; reason?: string }>;
    }>;
} {
    const cat = buildItemCatalog();
    if (!cat.ok) return { ok: false, err: cat.err, itemSpecs: {}, perUnit: [] };
    const rarityCap = args.rarityCap ?? 5;
    const itemSpecs: Record<string, Array<{ configId: string; level: number }>> = {};
    const perUnit: ReturnType<typeof buildBisItemSpecs>["perUnit"] = [];

    for (const u of args.units) {
        const slotInfo = getUnitItemSlots(u.unitId);
        if (!slotInfo) {
            perUnit.push({
                unitId: u.unitId, slotTypes: [],
                items: [{ slot: -1, configId: null, rarity: -1, starLvl: -1,
                         reason: "no lineup config" }],
            });
            continue;
        }
        const items: Array<{ slot: number; configId: string | null;
                             rarity: number; starLvl: number; reason?: string }> = [];
        const specs: Array<{ configId: string; level: number }> = [];
        for (let i = 0; i < slotInfo.slots.length; i++) {
            const slotType = slotInfo.slots[i];
            const pick = pickBisForSlot(slotType, u.unitId, {
                rarityCap, faction: u.faction,
                excludeRelics: args.excludeRelics,
            });
            if (!pick) {
                items.push({ slot: slotType, configId: null,
                            rarity: -1, starLvl: -1,
                            reason: `no item matches ItemType=${slotType}` });
                continue;
            }
            items.push({
                slot: slotType, configId: pick.configId,
                rarity: pick.rarity, starLvl: pick.starLvl,
            });
            // Use max level for the item (levels.length); level is 1-based.
            specs.push({ configId: pick.configId, level: pick.levelCount });
        }
        itemSpecs[u.unitId] = specs;
        perUnit.push({
            unitId: u.unitId, slotTypes: slotInfo.slots, items,
        });
    }
    return { ok: true, catalogCount: cat.count, itemSpecs, perUnit };
}
