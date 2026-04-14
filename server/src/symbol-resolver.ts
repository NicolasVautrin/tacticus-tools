/**
 * Resolve IL2CPP method offsets, enum values, and I2 descriptions.
 *
 * Loads:
 *   - symbols.json  (methods + enums)
 *   - i2_en.json    (localization terms)
 *   - gameconfig-abilities.json (ability variables/constants)
 */

import fs from "fs";
import path from "path";

const STYLE_RE = /<\/?style[^>]*>/g;
const PLACEHOLDER_RE = /\{\[((?:[^\[\]]*|\[[^\]]*\])*)\]\}/g;
const ENUM_PREFIX = "IdunBattle.Entities.Enum.";

const ABILITY_I2 = ["Abilities/{name}_CurrentLevelDescription"];
const EFFECT_I2 = [
  "UnitEffects/{name}_Description",
  "UnitEffects/{name}_UnitEffect_Description",
  "Abilities/{name}_CurrentLevelDescription",
  "Traits/{name}_Description",
];

// ---------- Types ----------

interface SymbolsJson {
  methods: Record<string, string>;
  enums: Record<string, Record<string, string>>;
}

interface AbilityConfig {
  variables?: Record<string, string[]>;
  constants?: Record<string, string>;
  [k: string]: unknown;
}

// ---------- Class ----------

export class SymbolResolver {
  private methods: [number, string][] = []; // sorted by offset
  private enums: Map<string, Map<number, string>> = new Map();

  private activeNames: Map<number, string> = new Map();
  private triggeredNames: Map<number, string> = new Map();
  private effectNames: Map<number, string> = new Map();
  private traitNames: Map<number, string> = new Map();

  private i2Terms: Map<string, string> = new Map();
  private gcAbilities: Map<string, AbilityConfig> = new Map();

  private _loaded = false;

  get isLoaded() {
    return this._loaded;
  }
  get methodCount() {
    return this.methods.length;
  }
  get enumCount() {
    return this.enums.size;
  }
  get abilityConfigCount() {
    return this.gcAbilities.size;
  }

  // ==================== Load ====================

  load(symbolsPath: string): boolean {
    if (!fs.existsSync(symbolsPath)) return false;

    let data: SymbolsJson;
    try {
      data = JSON.parse(fs.readFileSync(symbolsPath, "utf-8"));
    } catch {
      return false;
    }

    // Methods — sorted array for binary search
    const entries: [number, string][] = [];
    for (const [hex, name] of Object.entries(data.methods ?? {})) {
      const off = parseInt(hex, 16);
      if (!isNaN(off)) entries.push([off, name]);
    }
    entries.sort((a, b) => a[0] - b[0]);
    this.methods = entries;

    // Enums
    this.enums.clear();
    for (const [typeName, values] of Object.entries(data.enums ?? {})) {
      const m = new Map<number, string>();
      for (const [k, v] of Object.entries(values)) {
        const n = parseInt(k, 10);
        if (!isNaN(n)) m.set(n, v);
      }
      this.enums.set(typeName, m);
    }
    this.activeNames = this.enums.get(`${ENUM_PREFIX}ActiveAbilityType`) ?? new Map();
    this.triggeredNames = this.enums.get(`${ENUM_PREFIX}TriggeredAbilityType`) ?? new Map();
    this.effectNames = this.enums.get(`${ENUM_PREFIX}EffectType`) ?? new Map();
    this.traitNames = this.enums.get(`${ENUM_PREFIX}UnitTrait`) ?? new Map();

    // I2 terms
    const dir = path.dirname(symbolsPath);
    const i2Path = path.join(dir, "i2_en.json");
    if (fs.existsSync(i2Path)) {
      try {
        const raw: Record<string, string> = JSON.parse(fs.readFileSync(i2Path, "utf-8"));
        this.i2Terms = new Map(Object.entries(raw));
        console.log(`[symbols] Loaded ${this.i2Terms.size} I2 terms`);
      } catch { /* ignore */ }
    }

    // Gameconfig abilities
    const gcPath = path.join(dir, "gameconfig-abilities.json");
    if (fs.existsSync(gcPath)) {
      try {
        const raw: Record<string, AbilityConfig> = JSON.parse(fs.readFileSync(gcPath, "utf-8"));
        this.gcAbilities = new Map(Object.entries(raw));
        console.log(`[symbols] Loaded ${this.gcAbilities.size} ability configs`);
      } catch { /* ignore */ }
    }

    this._loaded = true;
    return true;
  }

  // ==================== Method resolution ====================

  resolveMethod(offset: number): string {
    if (!this.methods.length) return `il2cpp+0x${offset.toString(16)}`;
    // bisect_right equivalent
    let lo = 0, hi = this.methods.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this.methods[mid][0] <= offset) lo = mid + 1;
      else hi = mid;
    }
    const idx = lo - 1;
    if (idx < 0) return `il2cpp+0x${offset.toString(16)}`;
    const [mOff, mName] = this.methods[idx];
    const delta = offset - mOff;
    if (delta > 0x10000) return `il2cpp+0x${offset.toString(16)}`;
    if (delta === 0) return mName;
    return `${mName}+0x${delta.toString(16)}`;
  }

  resolveStack(offsets: number[]): string[] {
    return offsets.map((o) => this.resolveMethod(o));
  }

  resolveEnum(enumType: string, value: number): string | undefined {
    return this.enums.get(enumType)?.get(value);
  }

  // ==================== Name variants ====================

  private static nameVariants(name: string): string[] {
    const parts = name.split("_");
    const variants = [name];
    for (let i = parts.length - 1; i > 0; i--) {
      variants.push(parts.slice(0, i).join("_"));
    }
    for (let i = 1; i < parts.length; i++) {
      variants.push(parts.slice(i).join("_"));
    }
    return variants;
  }

  private findI2Template(name: string, patterns: string[]): [string | null, string | null] {
    for (const variant of SymbolResolver.nameVariants(name)) {
      for (const pattern of patterns) {
        const key = pattern.replace("{name}", variant);
        const raw = this.i2Terms.get(key);
        if (raw) return [variant, raw.replace(STYLE_RE, "")];
      }
    }
    return [null, null];
  }

  private getConfig(resolvedName: string): AbilityConfig | null {
    for (const variant of SymbolResolver.nameVariants(resolvedName)) {
      const cfg = this.gcAbilities.get(variant);
      if (cfg) return cfg;
    }
    return null;
  }

  // ==================== Description resolution ====================

  private resolveDescription(
    enumName: string,
    stateIndex: number | null,
    i2Patterns: string[],
  ): string | null {
    const [resolvedName, template] = this.findI2Template(enumName, i2Patterns);
    if (!template) return null;

    const config = this.getConfig(resolvedName ?? enumName);
    const params: Record<string, string> = {};

    // Constants
    const constants = config?.constants;
    if (constants) {
      for (const [k, v] of Object.entries(constants)) {
        if (typeof v === "string") params[k] = v;
      }
    }

    // Variables (indexed by state/level)
    const variables = config?.variables;
    if (variables && stateIndex != null && stateIndex >= 0) {
      for (const [k, values] of Object.entries(variables)) {
        if (!Array.isArray(values)) continue;
        const raw =
          stateIndex < values.length ? values[stateIndex] : values[values.length - 1];
        if (raw == null) continue;
        params[k] = raw;
        if (typeof raw === "string" && raw.includes(",")) {
          raw.split(",").forEach((pv, pi) => {
            params[`${k}[${pi}]`] = pv.trim();
          });
        }
      }
    }

    return template.replace(PLACEHOLDER_RE, (match, name: string) => {
      if (name in params) return params[name];
      if (name.endsWith("Current")) {
        const base = name.slice(0, -7);
        if (base in params) return params[base];
      }
      if (name.includes("/")) {
        const term = this.i2Terms.get(name);
        if (term != null) return term.replace(STYLE_RE, "");
      }
      return match;
    });
  }

  // ==================== Enrichment pipeline ====================

  enrichPayload(payload: unknown): unknown {
    if (!this._loaded) return payload;
    const result = this.enrich(payload);
    // Post-pass: effect descriptions using source unit ability params
    if (this.i2Terms.size && isObj(result)) {
      const entities = (result as any)._entities;
      if (Array.isArray(entities)) this.enrichEffects(entities);
    }
    return result;
  }

  private enrich(obj: unknown): unknown {
    if (Array.isArray(obj)) return obj.map((item) => this.enrich(item));
    if (!isObj(obj)) return obj;

    const result: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      let resolvedKey = k;
      if (k.startsWith('{"_enum":')) {
        try {
          const keyObj = JSON.parse(k);
          const name = this.resolveEnum(keyObj._enum, Number(keyObj._value));
          if (name != null) resolvedKey = name;
        } catch { /* ignore */ }
      }
      result[resolvedKey] = this.enrich(v);
    }

    // Resolve stacks
    if (Array.isArray(result.stack) && result.stack.length && typeof result.stack[0] === "number") {
      result.stack = this.resolveStack(result.stack as number[]);
    }

    // Resolve enum markers
    if (typeof result._enum === "string" && result._value != null) {
      const name = this.resolveEnum(result._enum as string, Number(result._value));
      if (name != null) result._name = name;
    }

    // I2 descriptions on abilities
    if (this.i2Terms.size) this.enrichI2(result);

    return result;
  }

  private enrichI2(obj: Record<string, unknown>): void {
    const cls = obj._class;
    if (cls === "ActiveAbility") {
      const typeId = obj.AbilityName as number | undefined;
      const state = obj._abilityState as number | undefined;
      const enumName = typeId != null ? this.activeNames.get(typeId) : undefined;
      if (enumName) {
        const desc = this.resolveDescription(enumName, state ?? null, ABILITY_I2);
        if (desc) obj._description = desc;
      }
    } else if (cls === "TriggeredAbility") {
      const typeId = obj.ConfigId as number | undefined;
      const state = obj.AbilityState as number | undefined;
      const enumName = typeId != null ? this.triggeredNames.get(typeId) : undefined;
      if (enumName) {
        const desc = this.resolveDescription(enumName, state ?? null, ABILITY_I2);
        if (desc) obj._description = desc;
      }
    }
  }

  // ==================== Effect enrichment (post-pass) ====================

  private poolAbilityParams(
    abilities: unknown[],
    namesMap: Map<number, string>,
    idField: string,
    stateField: string,
  ): Record<string, string> {
    const params: Record<string, string> = {};
    for (const a of abilities) {
      if (!isObj(a)) continue;
      const rec = a as Record<string, unknown>;
      const cid = rec[idField] as number | undefined;
      const state = rec[stateField] as number | undefined;
      const enumName = cid != null ? namesMap.get(cid) : undefined;
      if (!enumName) continue;
      const config = this.getConfig(enumName);
      if (!config) continue;

      const variables = config.variables;
      if (variables) {
        for (const [k, values] of Object.entries(variables)) {
          if (!Array.isArray(values)) continue;
          const raw =
            state != null && state >= 0 && state < values.length
              ? values[state]
              : values[values.length - 1];
          if (raw != null) params[k] = raw;
        }
      }

      const constants = config.constants;
      if (constants) {
        for (const [k, v] of Object.entries(constants)) {
          if (typeof v === "string") params[k] = v;
        }
      }
    }
    return params;
  }

  private buildUnitParams(entities: unknown[]): Map<number, Record<string, string>> {
    const unitParams = new Map<number, Record<string, string>>();
    for (const e of entities) {
      if (!isObj(e)) continue;
      const rec = e as Record<string, unknown>;
      if (rec.Type !== 1) continue;
      const uid = (rec.Id as number) ?? 0;
      const params: Record<string, string> = {};

      const ta = ((rec.TriggeredAbility as any)?.Abilities ?? []) as unknown[];
      if (Array.isArray(ta)) {
        Object.assign(params, this.poolAbilityParams(ta, this.triggeredNames, "ConfigId", "AbilityState"));
      }

      const aa = ((rec.ActiveAbility as any)?.Abilities ?? []) as unknown[];
      if (Array.isArray(aa)) {
        Object.assign(params, this.poolAbilityParams(aa, this.activeNames, "AbilityName", "_abilityState"));
      }

      if (Object.keys(params).length) unitParams.set(uid, params);
    }
    return unitParams;
  }

  private enrichEffects(entities: unknown[]): void {
    const unitParams = this.buildUnitParams(entities);

    for (const e of entities) {
      if (!isObj(e)) continue;
      const rec = e as Record<string, unknown>;
      if (rec.Type !== 3) continue;
      const ec = rec.Component as Record<string, unknown> | undefined;
      if (!isObj(ec)) continue;

      const etype = ec!.EffectType as number | undefined;
      if (etype == null) continue;
      const enumName = this.effectNames.get(etype);
      if (!enumName) continue;

      const [, template] = this.findI2Template(enumName, EFFECT_I2);
      if (!template) continue;

      const sourceUid = (ec!.SourceUnitId as number) ?? 0;
      const level = ec!.Level as number | undefined;
      const [resolvedName] = this.findI2Template(enumName, EFFECT_I2);
      const config = this.getConfig(resolvedName ?? enumName);

      const params: Record<string, string> = {};
      // Source unit params as base
      const up = unitParams.get(sourceUid);
      if (up) Object.assign(params, up);

      // Effect's own config on top
      if (config?.constants) {
        for (const [k, v] of Object.entries(config.constants)) {
          if (typeof v === "string") params[k] = v;
        }
      }
      if (config?.variables) {
        const si = typeof level === "number" && level > 0 ? level : 0;
        for (const [k, values] of Object.entries(config.variables)) {
          if (!Array.isArray(values)) continue;
          params[k] = si < values.length ? values[si] : values[values.length - 1];
        }
      }

      ec!._description = template.replace(PLACEHOLDER_RE, (match, name: string) => {
        if (name in params) return params[name];
        if (name.endsWith("Current")) {
          const base = name.slice(0, -7);
          if (base in params) return params[base];
        }
        if (name.includes("/")) {
          const term = this.i2Terms.get(name);
          if (term != null) return term.replace(STYLE_RE, "");
        }
        return match;
      });
    }
  }
}

// ---------- Helpers ----------

function isObj(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v);
}

// ---------- Singleton ----------

let instance: SymbolResolver | null = null;

export function getResolver(): SymbolResolver {
  if (!instance) instance = new SymbolResolver();
  return instance;
}
