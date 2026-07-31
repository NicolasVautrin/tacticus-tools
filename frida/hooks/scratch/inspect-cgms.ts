import { findClass, class_get_fields, field_get_name, field_get_offset, class_get_methods, method_get_name, method_get_param_count, s } from "../il2cpp/helpers.js";
import { Ctx } from "../controller.js";

const ASM_BATTLE = "IdunBattle.ViewLogic.dll";
const NS_BATTLE_SOURCE = "IdunBattle.ViewLogic.BattleSource";

export function inspectCgms() {
    const klass = findClass(ASM_BATTLE, NS_BATTLE_SOURCE, "CampaignGameModeSource");
    if (!klass) {
        console.log("[inspect-cgms] CampaignGameModeSource class NOT found");
        return;
    }
    console.log("[inspect-cgms] Fields for CampaignGameModeSource:");
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        const fname = s(field_get_name(f) as NativePointer);
        const off = field_get_offset(f) as number;
        console.log(`  - Field: ${fname} @ +0x${off.toString(16)}`);
    }

    console.log("[inspect-cgms] Methods for CampaignGameModeSource:");
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        const mname = s(method_get_name(m) as NativePointer);
        const pcount = method_get_param_count(m) as number;
        console.log(`  - Method: ${mname} (params: ${pcount})`);
    }
}

export function register(ctx: Ctx) {
    ctx.rpc.inspectCgms = () => {
        inspectCgms();
        return { ok: true };
    };
}
