export function dumpMethodInfo(m: NativePointer) {
    console.log(`[dump] MethodInfo @ ${m}:`);
    console.log(hexdump(m, { length: 64 }));
}
