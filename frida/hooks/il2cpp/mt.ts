// MersenneTwister snapshot/restore — lets us freeze PRNG state around each
// message apply to keep the replay deterministic.
//
// Layout of the game's MersenneTwister instance:
//   seed  @ 16 (int32)
//   count @ 20 (int32) — number of values drawn
//   mt[]  @ 32 (pointer to Il2CppArray of 624 uint32s)
//   mti   @ 40 (int32) — index into mt[]
//
// The RNG pointer may be wrapped in a pass-through (Disallowable, etc.) that
// holds the real MT at offset 16. `resolveMt` hops up to 4 times to reach it.

import { class_get_name, s } from "./helpers.js";

export interface MtSnapshot {
    seed: number;
    count: number;
    mti: number;
    mtBytes: ArrayBuffer;
    mtLen: number;
}

/** Walk up to 4 wrapper hops to resolve the underlying MersenneTwister. */
export function resolveMt(startPtr: NativePointer): NativePointer | null {
    let mt = startPtr;
    for (let hop = 0; hop < 4; hop++) {
        if (s(class_get_name(mt.readPointer()) as NativePointer)
            .indexOf("MersenneTwister") >= 0) return mt;
        const next = mt.add(16).readPointer();
        if (next.isNull() || next.equals(mt)) return null;
        mt = next;
    }
    return null;
}

export function snapshotMt(mt: NativePointer): MtSnapshot | null {
    const seed = mt.add(16).readS32();
    const count = mt.add(20).readS32();
    const mti = mt.add(40).readS32();
    const arr = mt.add(32).readPointer();
    if (arr.isNull()) return null;
    const len = arr.add(0x18).readS32();
    const bytes = arr.add(0x20).readByteArray(len * 4);
    if (bytes === null) return null;
    return { seed, count, mti, mtBytes: bytes, mtLen: len };
}

/** Restore only mti + mt[]. seed/count are metadata, skipped. */
export function restoreMt(mt: NativePointer, snap: MtSnapshot): boolean {
    mt.add(40).writeS32(snap.mti);
    const arr = mt.add(32).readPointer();
    if (arr.isNull()) return false;
    arr.add(0x20).writeByteArray(snap.mtBytes);
    return true;
}
