// IStatsFormula plumbing — direct call to
// `IStatsFormula.StatsUsingProgressionIndexFor(...)` bypasses the
// `UnitProgression.GetStats(...)` cascade (which is player-state dependent
// via item rarity-cap filtering).
//
// Also exposes:
//   - safe construction of empty `List<int>` / `List<IItemModel>` via
//     `il2cpp_object_new` + `(int capacity)` ctor — NEVER reuse Lists
//     materialized by game helpers (`GetCappedItemModelsOfUnit` etc.):
//     they can have an internal layout that crashes the formula iterator.
//   - synthetic `ItemModel` ctor (with optional level override) so any
//     `ItemConfigId` can be passed to the formula without touching the
//     player's actual inventory.
//
// UnitDynamicStats layout (12 ints, 48 bytes):
//   0x00 Health        0x10 CritChance       0x20 CritChanceBonus
//   0x04 Damage        0x14 CritDamage       0x24 CritDamageBonus
//   0x08 Armor         0x18 BlockChance      0x28 BlockChanceBonus
//   0x0C FixedArmor    0x1C BlockDamage      0x2C BlockDamageBonus
// Boxed return adds +0x10 header.

import {
    findClassAnywhere, findMethodByParamCount, findCtorByParamCount,
} from "../../il2cpp/helpers.js";
import {
    createManagedString, invokeMethod, il2cpp_object_new,
} from "../../il2cpp/invoke.js";

export interface FormulaState {
    statsForMi: { info: NativePointer; ptr: NativePointer };
    getIndicesMi: { info: NativePointer; ptr: NativePointer };
    getItemsMi: { info: NativePointer; ptr: NativePointer };
    isMowMi: { info: NativePointer; ptr: NativePointer };
    statsFormula: NativePointer;
    unitsConfig: NativePointer;
    emptyListInt: NativePointer | null;
    emptyListItems: NativePointer | null;
}

let _formulaState: FormulaState | null = null;

export function resolveFormulaState(
    unitProg: NativePointer,
): FormulaState | string {
    if (_formulaState) return _formulaState;
    const unitProgClass = unitProg.readPointer();
    if (unitProgClass.isNull()) return "unitProgression class ptr null";

    const getIndicesMi = findMethodByParamCount(
        unitProgClass, "GetIndicesOfAppliedUpgrades", 2);
    if (!getIndicesMi) return "GetIndicesOfAppliedUpgrades(2) not found";
    const getItemsMi = findMethodByParamCount(
        unitProgClass, "GetCappedItemModelsOfUnit", 2);
    if (!getItemsMi) return "GetCappedItemModelsOfUnit(2) not found";

    // IsMachineOfWar lives on UnitConfigUtil (static-like helper, takes
    // UnitsConfigDto + string).
    const utilClass = findClassAnywhere(
        "IdunMetaLogic.UserProgress", "UnitConfigUtil");
    if (!utilClass) return "UnitConfigUtil class not found";
    const isMowMi = findMethodByParamCount(utilClass, "IsMachineOfWar", 2);
    if (!isMowMi) return "IsMachineOfWar(2) not found";

    // IStatsFormula instance @ unitProg+0x80, then its concrete class
    const statsFormula = unitProg.add(0x80).readPointer();
    if (statsFormula.isNull()) return "_statsFormula is null";
    const formulaClass = statsFormula.readPointer();
    if (formulaClass.isNull()) return "_statsFormula class ptr null";

    const statsForMi = findMethodByParamCount(
        formulaClass, "StatsUsingProgressionIndexFor", 6);
    if (!statsForMi) return "StatsUsingProgressionIndexFor(6) not found";

    const unitsConfig = unitProg.add(0x38).readPointer();
    if (unitsConfig.isNull()) return "_unitsConfig is null";

    _formulaState = {
        statsForMi, getIndicesMi, getItemsMi, isMowMi,
        statsFormula, unitsConfig,
        emptyListInt: null, emptyListItems: null,
    };
    return _formulaState;
}

// Construct a properly-initialized empty `List<T>` by allocating via
// il2cpp_object_new and invoking the (int capacity) ctor with capacity=0.
//
// We can't trust List<T> instances returned by game helpers when those
// helpers exit on an out-of-band path — earlier we materialized them via
// `GetCappedItemModelsOfUnit(id, invalidRarity=-1)`, but the resulting
// object had unsafe internal state (apparent _size=0 but _items array
// uninitialized), causing a silent crash when StatsFormula iterated it.
//
// classInit ensures the type's static ctor has run before allocation.
export function createEmptyList(listClass: NativePointer): NativePointer {
    if (_classInitFn) {
        try { _classInitFn(listClass); } catch { /* best effort */ }
    }
    const obj = il2cpp_object_new(listClass) as NativePointer;
    if (obj.isNull()) throw new Error("il2cpp_object_new returned null");
    const ctor = findCtorByParamCount(listClass, 1);
    if (!ctor) throw new Error("List<T> ctor(int) not found");
    const capBuf = Memory.alloc(4); capBuf.writeS32(0);
    invokeMethod(ctor.info, obj, [capBuf]);
    return obj;
}

let _classInitFn: NativeFunction<void, [NativePointer]> | null = null;
{
    const lib = Process.findModuleByName("GameAssembly.dll");
    if (lib) {
        const p = lib.findExportByName("il2cpp_runtime_class_init");
        if (p) _classInitFn = new NativeFunction(p, "void", ["pointer"]);
    }
}

// Resolve List<int> and List<IItemModel> exact classes from the target
// method's param types, then construct empty instances via proper ctor.
export function ensureEmptyLists(
    state: FormulaState, _unitProg: NativePointer, _probeUnitId: string,
): string | null {
    if (state.emptyListInt && state.emptyListItems) return null;

    const lib = Process.findModuleByName("GameAssembly.dll");
    if (!lib) return "GameAssembly.dll not found";
    const mgpPtr = lib.findExportByName("il2cpp_method_get_param");
    const cftPtr = lib.findExportByName("il2cpp_class_from_type");
    if (!mgpPtr || !cftPtr) return "missing IL2CPP introspection exports";
    const mgp = new NativeFunction(mgpPtr, "pointer", ["pointer", "uint32"]);
    const cft = new NativeFunction(cftPtr, "pointer", ["pointer"]);

    if (!state.emptyListInt) {
        try {
            const t = mgp(state.statsForMi.info, 4) as NativePointer;
            const klass = cft(t) as NativePointer;
            if (klass.isNull()) return "List<int> class resolution null";
            state.emptyListInt = createEmptyList(klass);
        } catch (e) {
            return "List<int> construct failed: " + (e as Error).message;
        }
    }
    if (!state.emptyListItems) {
        try {
            const t = mgp(state.statsForMi.info, 5) as NativePointer;
            const klass = cft(t) as NativePointer;
            if (klass.isNull()) return "List<IItemModel> class resolution null";
            state.emptyListItems = createEmptyList(klass);
        } catch (e) {
            return "List<IItemModel> construct failed: " + (e as Error).message;
        }
    }
    return null;
}

export interface FormulaStatsResult {
    Health: number; Damage: number; Armor: number; FixedArmor: number;
    CritChance: number; CritDamage: number;
    BlockChance: number; BlockDamage: number;
    CritChanceBonus: number; CritDamageBonus: number;
    BlockChanceBonus: number; BlockDamageBonus: number;
}

export function readUnitDynamicStats(boxed: NativePointer): FormulaStatsResult {
    const b = boxed.add(0x10);
    return {
        Health: b.add(0x00).readS32(),
        Damage: b.add(0x04).readS32(),
        Armor: b.add(0x08).readS32(),
        FixedArmor: b.add(0x0c).readS32(),
        CritChance: b.add(0x10).readS32(),
        CritDamage: b.add(0x14).readS32(),
        BlockChance: b.add(0x18).readS32(),
        BlockDamage: b.add(0x1c).readS32(),
        CritChanceBonus: b.add(0x20).readS32(),
        CritDamageBonus: b.add(0x24).readS32(),
        BlockChanceBonus: b.add(0x28).readS32(),
        BlockDamageBonus: b.add(0x2c).readS32(),
    };
}

// -----------------------------------------------------------------------------
// Synthetic ItemModel construction
//
// `ItemModel.ctor(ItemConfigId, IItemProgression, Nullable<Level>)`:
//   ItemConfigId = struct { string _value; }  // 8 bytes: managed string ptr
//   IItemProgression = service interface (we read it from unitProg+0xD8)
//   Nullable<Level> = struct { bool hasValue; Level val; }  // 8 bytes
//     where Level = struct { int val; }  // 4 bytes
//
// Nullable<T> .NET layout (verified for Mono/IL2CPP): hasValue at 0x0
// (1 byte + 3 padding), value at 0x4. Pass hasValue=0 to use the item's
// default level (read from configId), or hasValue=1 + level to override.

export interface ItemModelState {
    itemModelClass: NativePointer;
    ctor3Mi: { info: NativePointer; ptr: NativePointer };
    listAddMi: { info: NativePointer; ptr: NativePointer };
    itemProgressionService: NativePointer;
}
let _itemModelState: ItemModelState | null = null;

export function resolveItemModelState(
    state: FormulaState, unitProg: NativePointer,
): string | null {
    if (_itemModelState) return null;

    const klass = findClassAnywhere("IdunMetaLogic.UserProgress.Model", "ItemModel");
    if (!klass) return "ItemModel class not found (ns=IdunMetaLogic.UserProgress.Model)";

    const ctor3 = findCtorByParamCount(klass, 3);
    if (!ctor3) return "ItemModel ctor(3) not found";

    const itemProg = unitProg.add(0xD8).readPointer();
    if (itemProg.isNull()) return "_itemProgression service is null";

    if (!state.emptyListItems) return "emptyListItems not initialized";
    const listClass = state.emptyListItems.readPointer();
    const addMi = findMethodByParamCount(listClass, "Add", 1);
    if (!addMi) return "List.Add(1) not found";

    _itemModelState = {
        itemModelClass: klass, ctor3Mi: ctor3, listAddMi: addMi,
        itemProgressionService: itemProg,
    };
    return null;
}

export function createItemModel(
    configIdValue: string, level: number | null,
): NativePointer {
    const s = _itemModelState!;
    const obj = il2cpp_object_new(s.itemModelClass) as NativePointer;
    if (obj.isNull()) throw new Error("il2cpp_object_new ItemModel failed");

    // ItemConfigId = { string _value; } (8 bytes = string pointer)
    const configIdBuf = Memory.alloc(8);
    configIdBuf.writePointer(createManagedString(configIdValue));

    // Nullable<Level> = { bool hasValue@0; Level val@4 }  (8 bytes)
    const nullableBuf = Memory.alloc(8);
    nullableBuf.writeU8(level !== null ? 1 : 0);
    nullableBuf.add(1).writeU8(0);
    nullableBuf.add(2).writeU8(0);
    nullableBuf.add(3).writeU8(0);
    nullableBuf.add(4).writeS32(level ?? 0);

    invokeMethod(s.ctor3Mi.info, obj,
        [configIdBuf, s.itemProgressionService, nullableBuf]);
    return obj;
}

export function addItemToList(list: NativePointer, item: NativePointer): void {
    invokeMethod(_itemModelState!.listAddMi.info, list, [item]);
}
