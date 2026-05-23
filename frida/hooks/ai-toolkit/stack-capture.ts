// Backtrace capture utility for diagnostic hooks.
//
// `Thread.backtrace(ctx, ACCURATE)` returns absolute pointers; for IL2CPP
// methods we want RVAs (offsets relative to GameAssembly.dll base) so they
// can be cross-referenced offline against `data/dumps/<HASH>/` once we know
// the running build's hash. Non-IL2CPP frames (Unity native, system DLLs)
// stay as absolute pointers, prefixed `abs:` so callers can tell them apart.
//
// Includes a helper for the most common diag pattern: dedup by (category,
// topRva) — the same hot loop fires thousands of times but we only want one
// specimen per unique entry point per category.
//
// Generic — used by overwatch-fix, ai-utility-trace, bucket-audit (and any
// future AI fix that wants to capture stacks).

import { il2cppBase, il2cppSize } from "../il2cpp/helpers.js";

export interface CapturedStack {
    /** First IL2CPP-resident frame's RVA (decimal, for fast Set/Map keys).
     * -1 if no IL2CPP frame at top of stack. */
    topRva: number;
    /** Up to 16 frames, formatted as `rva:0x...` for IL2CPP-resident
     * addresses or `abs:0x...` for outside frames. */
    frames: string[];
}

/** Capture and format a stack from the given CpuContext. Cap at 16 frames
 * — empirically more than enough to identify the call path without
 * blowing up the diag JSON. */
export function captureStack(ctx: CpuContext): CapturedStack {
    let topRva = -1;
    const frames: string[] = [];
    try {
        const bt = Thread.backtrace(ctx, Backtracer.ACCURATE);
        for (let i = 0; i < Math.min(bt.length, 16); i++) {
            const off = bt[i].sub(il2cppBase);
            const inIl2cpp = il2cppSize > 0
                && off.compare(0) >= 0 && off.compare(il2cppSize) < 0;
            if (i === 0 && inIl2cpp) topRva = off.toInt32();
            frames.push(inIl2cpp
                ? "rva:0x" + off.toString(16)
                : "abs:" + bt[i].toString());
        }
    } catch (e) {
        frames.push("<failed: " + (e as Error).message + ">");
    }
    return { topRva, frames };
}

/** A diag bucket of captured stacks, deduped by (category, topRva). Cap
 * controls how many distinct stacks we keep total — past the cap, all
 * `record(...)` calls become no-ops. The `categoryCounts` map is always
 * incremented though, so callers see how many fires landed in each
 * category even after the dedup cap is hit.
 *
 * Typical use: an `onEnter`/`onLeave` callback classifies the call into
 * one of N categories (`patched`, `out_of_range`, `no_dest`, etc.) and
 * pushes the stack via `record(...)`. Inspecting the resulting buckets
 * tells you "we have 1 specimen per call site per outcome category". */
export class StackBucket<TCategory extends string> {
    public readonly stacks: Array<{
        category: TCategory; topRva: number; frames: string[];
        annotation: string | null; ts: number;
    }> = [];
    public readonly categoryCounts: Record<string, number> = {};
    private readonly cap: number;

    constructor(cap = 30) { this.cap = cap; }

    /** Increment the category counter (always), then push a deduped stack
     * if (a) the cap isn't reached and (b) no prior entry shares the same
     * (category, topRva) pair. The `annotation` is appended to the frames
     * array so callers can attach context (a tile coord, an entity id...)
     * without inventing a new field. */
    record(
        ctx: CpuContext, category: TCategory, annotation: string | null = null,
    ): void {
        this.categoryCounts[category] =
            (this.categoryCounts[category] ?? 0) + 1;
        if (this.stacks.length >= this.cap) return;
        const { topRva, frames } = captureStack(ctx);
        for (const s of this.stacks) {
            if (s.category === category && s.topRva === topRva) return;
        }
        const annotated = annotation !== null
            ? [...frames, annotation] : frames;
        this.stacks.push({
            category, topRva, frames: annotated, annotation, ts: Date.now(),
        });
    }

    reset(): void {
        this.stacks.length = 0;
        for (const k of Object.keys(this.categoryCounts)) {
            this.categoryCounts[k] = 0;
        }
    }
}
