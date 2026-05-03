// RPC: dump the game's unitId → assetNaming mapping from
// `IdunVisuals._unitConfigMap` (static Dictionary<string, IdunUnitType>).
//
// IdunUnitType has:  unitId @ 0x20,  assetNaming @ 0x30
// (ScriptableObject layout — stable across builds).
//
// This replaces the fragile camelCase→snake_case heuristic in the front-end
// with the game's own authoritative mapping.

import {
    findClassAnywhere, il2cppBase, IL2CPP_MODULE_NAME, readIl2cppString,
} from "../il2cpp/helpers.js";
import { Ctx } from "../controller.js";

const libBase = il2cppBase;
// il2cppBase is re-exported; we use its module for export lookups.
const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
function exp(name: string): NativePointer {
    if (!lib) throw new Error(`${IL2CPP_MODULE_NAME} not loaded`);
    const p = lib.findExportByName(name);
    if (!p) throw new Error(`missing export: ${name}`);
    return p;
}

const _getFieldFromName = (() => {
    try {
        return new NativeFunction(
            exp("il2cpp_class_get_field_from_name"), "pointer", ["pointer", "pointer"]);
    } catch { return null; }
})();
const _fieldStaticGetValue = (() => {
    try {
        return new NativeFunction(
            exp("il2cpp_field_static_get_value"), "void", ["pointer", "pointer"]);
    } catch { return null; }
})();

export function register(ctx: Ctx): void {
    ctx.rpc.getUnitAssetMap = () => {
        if (!_getFieldFromName || !_fieldStaticGetValue) {
            throw new Error("IL2CPP reflection exports missing");
        }
        const cls = findClassAnywhere("idun.ui", "IdunVisuals");
        if (!cls) throw new Error("IdunVisuals class not found");
        const nameBuf = Memory.allocUtf8String("_unitConfigMap");
        const field = _getFieldFromName(cls, nameBuf) as NativePointer;
        if (field.isNull()) throw new Error("_unitConfigMap field not found");

        const storage = Memory.alloc(Process.pointerSize);
        _fieldStaticGetValue(field, storage);
        const dict = storage.readPointer();
        if (dict.isNull()) throw new Error("_unitConfigMap not initialized yet");

        // Dictionary<string, IdunUnitType> (.NET Core):
        //   _entries @ 0x18,  _count @ 0x20
        // Entry<string, ref>: hashCode(4) + next(4) + key-ref(8) + value-ref(8) = 24B
        // Il2CppArray header = 0x20.
        const count = dict.add(0x20).readS32();
        const entries = dict.add(0x18).readPointer();
        if (entries.isNull()) throw new Error("entries array is null");

        const map: Record<string, { unitId: string | null; assetNaming: string | null }> = {};
        for (let i = 0; i < count; i++) {
            const base = entries.add(0x20 + i * 24);
            const next = base.add(4).readS32();
            if (next < -1) continue;  // free slot
            const keyPtr = base.add(8).readPointer();
            const valPtr = base.add(16).readPointer();
            if (keyPtr.isNull() || valPtr.isNull()) continue;
            const key = readIl2cppString(keyPtr);
            if (!key) continue;
            // IdunUnitType.unitId @ 0x20,  assetNaming @ 0x30
            const unitIdPtr = valPtr.add(0x20).readPointer();
            const assetPtr = valPtr.add(0x30).readPointer();
            map[key] = {
                unitId: readIl2cppString(unitIdPtr),
                assetNaming: readIl2cppString(assetPtr),
            };
        }
        return { count: Object.keys(map).length, map };
    };
    // Prevent unused-warning on re-exported helpers.
    void libBase;
}
