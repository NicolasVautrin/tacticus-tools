/* Garde de #279 — la resolution PAR NOM du decodeur de prediction.
 *
 * Lancement (depuis `frida/`) :
 *     npx tsx tools/probe-279-layout-by-name.ts            # etapes 1 + 2 (host requis)
 *     npx tsx tools/probe-279-layout-by-name.ts --offline  # etape 2 seule (deterministe)
 *
 * POURQUOI CE HARNAIS EXISTE. `frida/hooks/game/damage-prediction.ts` ne peut pas
 * s'executer hors du process de jeu, et le valider EXIGERAIT une reinjection — geste
 * interdit tant qu'une session est partagee. La resolution y est donc parametree par un
 * `LayoutProbe` : ce harnais en fournit un construit sur la disposition REELLE du build
 * courant, capturee par le RPC `classFields`. Ce qui tourne ici est le code de
 * PRODUCTION (`resolveFieldPath`, `resolveFieldsSize`, `resolvePredictionLayout`), pas
 * une copie.
 *
 * CE QU'IL MESURE, en deux etapes distinctes :
 *   1. LIVE — la disposition rendue par les metadonnees IL2CPP du build courant,
 *      confrontee aux offsets RE figes que le decodeur portait avant la conversion.
 *      Un ecart = le fichier mentait DEJA. Table nom -> attendu / live.
 *   2. ADVERSARIAL — on FAUSSE la disposition (nom de champ inexistant, conteneur
 *      declare non-ValueType, offset de champ statique) et on exige que la resolution
 *      LEVE avec un message nomme, au lieu de retomber sur 0 / -1 et de lire a cote.
 *      C'est le point central : `getFieldOffset` rend -1 sur un nom absent, et lire a
 *      -1 serait PIRE qu'un offset perime — perime mais stable.
 *   3. #372 — les deux entrees de `get_WillBeKill` que le canal n'exposait pas
 *      (`CannotBeGuaranteedKilled@0x89` et `BlockScenarios[0]+0x0c`) : resolution de la
 *      chaine du scenario, table de verite du mirror `computeWillBeKill` (dont les DEUX
 *      lignes qui opposent la borne de block a la borne par defaut), et sentinelles de
 *      forme sur les champs neufs.
 *
 * CE QU'IL NE MESURE PAS : que le bundle injecte emette les memes valeurs. Cela exige
 * un reinject. Le code reste NON CONFRONTE tant que ce n'est pas fait.
 */

// --- Stub des globaux Frida --------------------------------------------------------
// `hooks/il2cpp/helpers.ts` touche `Process` / `NativeFunction` des son chargement.
// Le stub sert UNIQUEMENT a rendre l'import possible : la resolution de production
// (`LIVE_PROBE`) n'y trouvera aucune classe et s'auto-declarera en echec, ce qui est le
// comportement attendu hors process. Le harnais, lui, appelle les fonctions exportees
// avec SON probe.

interface StubPtr {
    isNull(): boolean;
    add(n: number): StubPtr;
    readPointer(): StubPtr;
    writePointer(p: unknown): void;
    toString(): string;
}

function makeNullPtr(): StubPtr {
    const p: StubPtr = {
        isNull: () => true,
        add: () => p,
        readPointer: () => p,
        writePointer: () => { /* no-op */ },
        toString: () => "0x0",
    };
    return p;
}

const NULL_PTR = makeNullPtr();

const g = globalThis as unknown as Record<string, unknown>;
g.ptr = (): StubPtr => NULL_PTR;
g.NativeFunction = function NativeFunctionStub() {
    return (): StubPtr => NULL_PTR;
} as unknown as unknown;
g.Memory = { alloc: (): StubPtr => NULL_PTR };
g.Process = {
    pointerSize: 8,
    findModuleByName: () => ({
        base: NULL_PTR, size: 0,
        findExportByName: (): StubPtr => NULL_PTR,
    }),
};
g.send = (): void => { /* diag.ts */ };

// --- Disposition d'une classe, telle que la rend le RPC `classFields` ---------------

interface RpcField { name: string; offset: number; type: string; declaredBy: string; }
interface RpcClass {
    ns: string; cls: string; boxedSize: number; fieldsSize: number;
    fields: RpcField[];
}

/** Fermeture transitive des types touches par le decodeur. `isValueType` est une
 *  ENTREE du test, pas une donnee du RPC : `classFields` ne la rend pas. Elle est
 *  mesurable autrement (boxedSize - fieldsSize = 0x10 sur chacun, et le decompile les
 *  passe par valeur) ; la poser ici permet justement d'en faire un cas adversarial. */
const TARGETS: Array<{ ns: string; cls: string; valueType: boolean }> = [
    { ns: "IdunBattle.Core.Services", cls: "DamagePredictionResult", valueType: true },
    { ns: "IdunBattle.Core.Services", cls: "DamagePredictionScenario", valueType: true },
    { ns: "IdunBattle.Core.Services", cls: "DamagePredictionDamage", valueType: true },
    { ns: "IdunBattle.Core.Services", cls: "MinMaxDamage", valueType: true },
    { ns: "IdunBattle.Core.Services", cls: "HealPredictionResult", valueType: true },
    { ns: "IdunBattle.AI.Playbook", cls: "ProbableDamageEvent", valueType: true },
    { ns: "IdunBattle.AI.Playbook", cls: "ProbableHealEvent", valueType: true },
    { ns: "IdunBattle.AI.Playbook", cls: "ProbableEffectEvent", valueType: true },
];

/** Disposition capturee le 2026-07-30 sur le build `rnca9r7q6c`, session 2, par
 *  `POST /api/scripts/2/rpc {"method":"classFields",...}`. Offsets BOXES, tels quels.
 *  Sert de reference deterministe a l'etape 2 quand le host n'est pas joignable ; l'
 *  etape 1 la re-mesure et signale toute divergence. */
const SNAPSHOT: Record<string, RpcClass> = {
    "IdunBattle.Core.Services.DamagePredictionResult": {
        ns: "IdunBattle.Core.Services", cls: "DamagePredictionResult",
        boxedSize: 176, fieldsSize: 160,
        fields: [
            { name: "CurrentHealth", offset: 16, type: "Int32", declaredBy: "DamagePredictionResult" },
            { name: "CurrentShield", offset: 20, type: "Int32", declaredBy: "DamagePredictionResult" },
            { name: "DamageProfile", offset: 24, type: "DamageProfile", declaredBy: "DamagePredictionResult" },
            { name: "DefaultScenario", offset: 32, type: "DamagePredictionScenario", declaredBy: "DamagePredictionResult" },
            { name: "BlockScenarios", offset: 72, type: "List`1", declaredBy: "DamagePredictionResult" },
            { name: "AccurateHealthDamage", offset: 80, type: "MinMaxDamage", declaredBy: "DamagePredictionResult" },
            { name: "AccurateShieldDamage", offset: 96, type: "MinMaxDamage", declaredBy: "DamagePredictionResult" },
            { name: "TotalDamage", offset: 112, type: "MinMaxDamage", declaredBy: "DamagePredictionResult" },
            { name: "Modifiers", offset: 128, type: "List`1", declaredBy: "DamagePredictionResult" },
            { name: "DeniedDamage", offset: 136, type: "Int32", declaredBy: "DamagePredictionResult" },
            { name: "IndividualHitDamage", offset: 144, type: "List`1", declaredBy: "DamagePredictionResult" },
            { name: "LimitedByMinHp", offset: 152, type: "Boolean", declaredBy: "DamagePredictionResult" },
            { name: "CannotBeGuaranteedKilled", offset: 153, type: "Boolean", declaredBy: "DamagePredictionResult" },
            { name: "MightCrit", offset: 154, type: "Boolean", declaredBy: "DamagePredictionResult" },
            { name: "ForceOverkill", offset: 155, type: "Boolean", declaredBy: "DamagePredictionResult" },
            { name: "PreventOverkill", offset: 156, type: "Boolean", declaredBy: "DamagePredictionResult" },
            { name: "OverkillDmgPctOfHealth", offset: 160, type: "Nullable`1", declaredBy: "DamagePredictionResult" },
            { name: "AppliedHits", offset: 168, type: "Int32", declaredBy: "DamagePredictionResult" },
        ],
    },
    "IdunBattle.Core.Services.DamagePredictionScenario": {
        ns: "IdunBattle.Core.Services", cls: "DamagePredictionScenario",
        boxedSize: 52, fieldsSize: 36,
        fields: [
            { name: "Probability", offset: 16, type: "Int32", declaredBy: "DamagePredictionScenario" },
            { name: "Damage", offset: 20, type: "DamagePredictionDamage", declaredBy: "DamagePredictionScenario" },
        ],
    },
    "IdunBattle.Core.Services.DamagePredictionDamage": {
        ns: "IdunBattle.Core.Services", cls: "DamagePredictionDamage",
        boxedSize: 48, fieldsSize: 32,
        fields: [
            { name: "HealthDamage", offset: 16, type: "MinMaxDamage", declaredBy: "DamagePredictionDamage" },
            { name: "ShieldDamage", offset: 32, type: "MinMaxDamage", declaredBy: "DamagePredictionDamage" },
        ],
    },
    "IdunBattle.Core.Services.MinMaxDamage": {
        ns: "IdunBattle.Core.Services", cls: "MinMaxDamage",
        boxedSize: 32, fieldsSize: 16,
        fields: [
            { name: "_cap", offset: 16, type: "Nullable`1", declaredBy: "MinMaxDamage" },
            { name: "Min", offset: 24, type: "Int32", declaredBy: "MinMaxDamage" },
            { name: "Max", offset: 28, type: "Int32", declaredBy: "MinMaxDamage" },
        ],
    },
    "IdunBattle.Core.Services.HealPredictionResult": {
        ns: "IdunBattle.Core.Services", cls: "HealPredictionResult",
        boxedSize: 24, fieldsSize: 8,
        fields: [
            { name: "CurrentHealth", offset: 16, type: "Int32", declaredBy: "HealPredictionResult" },
            { name: "TotalHeal", offset: 20, type: "Int32", declaredBy: "HealPredictionResult" },
        ],
    },
    "IdunBattle.AI.Playbook.ProbableDamageEvent": {
        ns: "IdunBattle.AI.Playbook", cls: "ProbableDamageEvent",
        boxedSize: 200, fieldsSize: 184,
        fields: [
            { name: "Target", offset: 16, type: "IEntity", declaredBy: "ProbableDamageEvent" },
            { name: "DamagePrediction", offset: 24, type: "DamagePredictionResult", declaredBy: "ProbableDamageEvent" },
            { name: "Probability", offset: 184, type: "Fix64", declaredBy: "ProbableDamageEvent" },
            { name: "Weight", offset: 192, type: "Fix64", declaredBy: "ProbableDamageEvent" },
        ],
    },
    "IdunBattle.AI.Playbook.ProbableHealEvent": {
        ns: "IdunBattle.AI.Playbook", cls: "ProbableHealEvent",
        boxedSize: 40, fieldsSize: 24,
        fields: [
            { name: "Target", offset: 16, type: "IEntity", declaredBy: "ProbableHealEvent" },
            { name: "HealPrediction", offset: 24, type: "HealPredictionResult", declaredBy: "ProbableHealEvent" },
            { name: "Probability", offset: 32, type: "Fix64", declaredBy: "ProbableHealEvent" },
        ],
    },
    "IdunBattle.AI.Playbook.ProbableEffectEvent": {
        ns: "IdunBattle.AI.Playbook", cls: "ProbableEffectEvent",
        boxedSize: 40, fieldsSize: 24,
        fields: [
            { name: "Target", offset: 16, type: "IEntity", declaredBy: "ProbableEffectEvent" },
            { name: "EffectType", offset: 24, type: "EffectType", declaredBy: "ProbableEffectEvent" },
            { name: "Probability", offset: 32, type: "Fix64", declaredBy: "ProbableEffectEvent" },
        ],
    },
};

// --- Probe construit sur une disposition capturee ----------------------------------

type Dispo = Record<string, RpcClass>;

interface FakeClass { key: string; }

function buildProbe(
    dispo: Dispo, valueTypes: Record<string, boolean>,
): {
        findClass(ns: string, cls: string): unknown;
        className(k: unknown): string;
        isValueType(k: unknown): boolean | null;
        instanceSize(k: unknown): number;
        rawFieldOffset(k: unknown, name: string): number;
        fieldTypeClass(k: unknown, name: string): unknown;
    } {
    const byName: Record<string, string> = {};
    for (const key of Object.keys(dispo)) byName[dispo[key].cls] = key;
    const cl = (k: unknown): RpcClass => dispo[(k as FakeClass).key];
    return {
        findClass: (ns, cls) => {
            const key = ns + "." + cls;
            return dispo[key] ? ({ key } as FakeClass) : null;
        },
        className: (k) => cl(k).cls,
        isValueType: (k) => {
            const v = valueTypes[cl(k).cls];
            return v === undefined ? null : v;
        },
        instanceSize: (k) => cl(k).boxedSize,
        rawFieldOffset: (k, name) => {
            const f = cl(k).fields.find((x) => x.name === name);
            return f ? f.offset : -1;
        },
        fieldTypeClass: (k, name) => {
            const f = cl(k).fields.find((x) => x.name === name);
            if (!f) return null;
            const key = byName[f.type];
            return key ? ({ key } as FakeClass) : null;
        },
    };
}

function deepCopy(d: Dispo): Dispo {
    return JSON.parse(JSON.stringify(d)) as Dispo;
}

function defaultValueTypes(): Record<string, boolean> {
    const out: Record<string, boolean> = {};
    for (const t of TARGETS) out[t.cls] = t.valueType;
    return out;
}

// --- Etape 1 : disposition LIVE vs offsets RE figes ---------------------------------

const RPC_URL = "http://127.0.0.1:8765/api/scripts/2/rpc";

async function fetchDispo(): Promise<Dispo | null> {
    const out: Dispo = {};
    for (const t of TARGETS) {
        let json: { result?: { ok?: boolean; err?: string } & RpcClass };
        try {
            const res = await fetch(RPC_URL, {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ method: "classFields", args: [t.ns, t.cls] }),
            });
            json = await res.json() as typeof json;
        } catch (e) {
            process.stdout.write("HOST INJOIGNABLE (" + (e as Error).message
                + ") -- etape 1 impossible\n");
            return null;
        }
        const r = json.result;
        if (!r || r.ok !== true) {
            process.stdout.write("classFields KO pour " + t.ns + "." + t.cls
                + " : " + (r ? r.err : "reponse vide") + "\n");
            return null;
        }
        out[t.ns + "." + t.cls] = {
            ns: t.ns, cls: t.cls, boxedSize: r.boxedSize,
            fieldsSize: r.fieldsSize, fields: r.fields,
        };
    }
    return out;
}

/** Offsets que le decodeur figeait AVANT #279 (etat de `damage-prediction.ts` a
 *  `origin/master`). Chaque ligne est donc la question : « ce littéral etait-il encore
 *  vrai sur le build courant ? ». */
const FROZEN_BEFORE_279: Array<[string, string[], number]> = [
    ["DamagePredictionResult", ["CurrentHealth"], 0x00],
    ["DamagePredictionResult", ["CurrentShield"], 0x04],
    ["DamagePredictionResult", ["DefaultScenario", "Probability"], 0x10],
    ["DamagePredictionResult", ["DefaultScenario", "Damage", "HealthDamage"], 0x14],
    ["DamagePredictionResult", ["DefaultScenario", "Damage", "ShieldDamage"], 0x24],
    ["DamagePredictionResult", ["BlockScenarios"], 0x38],
    ["DamagePredictionResult", ["AccurateHealthDamage"], 0x40],
    ["DamagePredictionResult", ["AccurateShieldDamage"], 0x50],
    ["DamagePredictionResult", ["TotalDamage"], 0x60],
    ["DamagePredictionResult", ["IndividualHitDamage"], 0x80],
    ["DamagePredictionResult", ["LimitedByMinHp"], 0x88],
    ["DamagePredictionResult", ["MightCrit"], 0x8a],
    ["DamagePredictionResult", ["ForceOverkill"], 0x8b],
    ["DamagePredictionResult", ["PreventOverkill"], 0x8c],
    ["DamagePredictionResult", ["AppliedHits"], 0x98],
    ["MinMaxDamage", ["Min"], 0x08],
    ["MinMaxDamage", ["Max"], 0x0c],
    ["ProbableDamageEvent", ["DamagePrediction"], 0x08],
    ["ProbableDamageEvent", ["Probability"], 0xa8],
    ["ProbableDamageEvent", ["Weight"], 0xb0],
];

const FROZEN_SIZES: Array<[string, string, number]> = [
    ["IdunBattle.Core.Services", "DamagePredictionResult", 0xa0],
    ["IdunBattle.AI.Playbook", "ProbableDamageEvent", 0xb8],
    ["IdunBattle.AI.Playbook", "ProbableHealEvent", 0x18],
    ["IdunBattle.AI.Playbook", "ProbableEffectEvent", 0x18],
];

function hx(n: number): string {
    return "0x" + n.toString(16);
}

// --- Corps ------------------------------------------------------------------------

async function main(): Promise<void> {
    const mod = await import("../hooks/game/damage-prediction.js");
    const { resolveFieldPath, resolveFieldsSize, resolvePredictionLayout } = mod;
    type Probe = Parameters<typeof resolveFieldPath>[0];
    const nsOf: Record<string, string> = {};
    for (const t of TARGETS) nsOf[t.cls] = t.ns;

    let failures = 0;
    const offline = process.argv.indexOf("--offline") >= 0;

    // ---- Etape 1 : LIVE vs fige ----
    let live: Dispo | null = null;
    if (!offline) {
        process.stdout.write("=== ETAPE 1 : disposition LIVE vs offsets figes"
            + " (avant #279) ===\n");
        live = await fetchDispo();
        if (live === null) {
            process.stdout.write("ETAPE 1 NON JOUEE (host indisponible)."
                + " Relancer avec le host up, ou --offline pour l'etape 2 seule.\n");
            failures++;
        } else {
            const probe = buildProbe(live, defaultValueTypes()) as unknown as Probe;
            let drift = 0;
            process.stdout.write(
                "chemin".padEnd(58) + "fige".padEnd(8) + "live".padEnd(8) + "verdict\n");
            for (const [cls, path, frozen] of FROZEN_BEFORE_279) {
                const k = probe.findClass(nsOf[cls], cls);
                if (k === null) { process.stdout.write("classe absente: " + cls + "\n"); failures++; continue; }
                let got = -1; let err = "";
                try { got = resolveFieldPath(probe, k, cls, path); }
                catch (e) { err = (e as Error).message; }
                const label = cls + "." + path.join(".");
                if (err) {
                    process.stdout.write(label.padEnd(58) + hx(frozen).padEnd(8)
                        + "LEVE".padEnd(8) + err + "\n");
                    failures++;
                } else {
                    const ok = got === frozen;
                    if (!ok) drift++;
                    process.stdout.write(label.padEnd(58) + hx(frozen).padEnd(8)
                        + hx(got).padEnd(8) + (ok ? "OK" : "ECART") + "\n");
                }
            }
            for (const [ns, cls, frozen] of FROZEN_SIZES) {
                const k = probe.findClass(ns, cls);
                if (k === null) { failures++; continue; }
                let got = -1; let err = "";
                try { got = resolveFieldsSize(probe, k, cls); }
                catch (e) { err = (e as Error).message; }
                const label = cls + ".<fieldsSize>";
                if (err) {
                    process.stdout.write(label.padEnd(58) + hx(frozen).padEnd(8)
                        + "LEVE".padEnd(8) + err + "\n");
                    failures++;
                } else {
                    const ok = got === frozen;
                    if (!ok) drift++;
                    process.stdout.write(label.padEnd(58) + hx(frozen).padEnd(8)
                        + hx(got).padEnd(8) + (ok ? "OK" : "ECART") + "\n");
                }
            }
            process.stdout.write("ECARTS fige/live : " + drift + " sur "
                + (FROZEN_BEFORE_279.length + FROZEN_SIZES.length) + "\n");

            // Le snapshot embarque doit rester fidele a la mesure live, sinon l'etape 2
            // teste une disposition morte.
            let snapDelta = 0;
            for (const key of Object.keys(SNAPSHOT)) {
                const a = JSON.stringify(SNAPSHOT[key]);
                const b = JSON.stringify(live[key]);
                if (a !== b) { snapDelta++; process.stdout.write("SNAPSHOT PERIME: " + key + "\n"); }
            }
            process.stdout.write("snapshot embarque vs live : "
                + (snapDelta === 0 ? "IDENTIQUE" : snapDelta + " classe(s) divergente(s)")
                + "\n");
            if (snapDelta > 0) failures++;
        }
        process.stdout.write("\n");
    }

    // ---- Etape 2 : mutations adversariales ----
    process.stdout.write("=== ETAPE 2 : mutations adversariales (deterministe) ===\n");
    const base = live ?? SNAPSHOT;

    const expectThrow = (
        name: string, needle: string, fn: () => unknown,
    ): void => {
        let msg: string | null = null;
        try { fn(); } catch (e) { msg = (e as Error).message; }
        if (msg === null) {
            process.stdout.write("ROUGE " + name
                + " : AUCUNE exception -- la resolution a rendu une valeur\n");
            failures++;
            return;
        }
        if (msg.indexOf(needle) < 0) {
            process.stdout.write("ROUGE " + name + " : message inattendu -> " + msg + "\n");
            failures++;
            return;
        }
        process.stdout.write("OK    " + name + "\n        -> " + msg + "\n");
    };

    // (a) nom de champ FAUSSE -- le cas nomme par la tache.
    {
        const d = deepCopy(base);
        const c = d["IdunBattle.Core.Services.DamagePredictionResult"];
        const f = c.fields.find((x) => x.name === "AccurateHealthDamage");
        if (f) f.name = "AccurateHealthDamageXX";
        const probe = buildProbe(d, defaultValueTypes()) as unknown as Probe;
        const k = probe.findClass("IdunBattle.Core.Services", "DamagePredictionResult");
        expectThrow("champ renomme -> resolution directe", "CHAMP INTROUVABLE",
            () => resolveFieldPath(probe, k as NonNullable<typeof k>,
                "DamagePredictionResult", ["AccurateHealthDamage"]));
        const r = resolvePredictionLayout(probe);
        if (r.layout !== null) {
            process.stdout.write("ROUGE resolvePredictionLayout : layout rendu malgre"
                + " un champ absent\n");
            failures++;
        } else {
            process.stdout.write("OK    resolvePredictionLayout -> layout=null, "
                + r.errors.length + " erreur(s)\n        -> " + r.errors[0] + "\n");
        }
    }

    // (b) maillon INTERMEDIAIRE renomme -- la chaine imbriquee doit lever aussi.
    {
        const d = deepCopy(base);
        const c = d["IdunBattle.Core.Services.DamagePredictionScenario"];
        const f = c.fields.find((x) => x.name === "Damage");
        if (f) f.name = "DamageZZ";
        const probe = buildProbe(d, defaultValueTypes()) as unknown as Probe;
        const k = probe.findClass("IdunBattle.Core.Services", "DamagePredictionResult");
        expectThrow("maillon imbrique renomme", "CHAMP INTROUVABLE",
            () => resolveFieldPath(probe, k as NonNullable<typeof k>,
                "DamagePredictionResult",
                ["DefaultScenario", "Damage", "HealthDamage"]));
    }

    // (c) conteneur declare NON-ValueType : ses champs ne sont plus INLINE, le -0x10
    //     serait faux et il faudrait dereferencer. Refus attendu.
    {
        const vt = defaultValueTypes();
        vt["DamagePredictionDamage"] = false;
        const probe = buildProbe(deepCopy(base), vt) as unknown as Probe;
        const k = probe.findClass("IdunBattle.Core.Services", "DamagePredictionResult");
        expectThrow("sous-struct non-ValueType", "n'est PAS un ValueType",
            () => resolveFieldPath(probe, k as NonNullable<typeof k>,
                "DamagePredictionResult",
                ["DefaultScenario", "Damage", "HealthDamage"]));
    }

    // (d) primitive de metadonnees absente : « je ne sais pas » n'autorise pas a lire.
    {
        const vt = defaultValueTypes();
        delete vt["DamagePredictionResult"];
        const probe = buildProbe(deepCopy(base), vt) as unknown as Probe;
        const k = probe.findClass("IdunBattle.Core.Services", "DamagePredictionResult");
        expectThrow("is_valuetype indisponible", "non exporte",
            () => resolveFieldPath(probe, k as NonNullable<typeof k>,
                "DamagePredictionResult", ["CurrentHealth"]));
    }

    // (e) champ STATIQUE (offset hors plage d'instance) : ne doit jamais etre compose.
    {
        const d = deepCopy(base);
        const c = d["IdunBattle.Core.Services.DamagePredictionResult"];
        const f = c.fields.find((x) => x.name === "MightCrit");
        if (f) f.offset = 4096;
        const probe = buildProbe(d, defaultValueTypes()) as unknown as Probe;
        const k = probe.findClass("IdunBattle.Core.Services", "DamagePredictionResult");
        expectThrow("offset hors instance (statique)", "OFFSET HORS INSTANCE",
            () => resolveFieldPath(probe, k as NonNullable<typeof k>,
                "DamagePredictionResult", ["MightCrit"]));
    }

    // (f) strides des deux petits events desaccordes : SMALL_EVENT_STRIDE ne peut plus
    //     etre unique. L'ancien code le SUPPOSAIT ; ici on le verifie.
    {
        const d = deepCopy(base);
        d["IdunBattle.AI.Playbook.ProbableEffectEvent"].boxedSize = 48;
        const probe = buildProbe(d, defaultValueTypes()) as unknown as Probe;
        const r = resolvePredictionLayout(probe);
        const hit = r.errors.some((e) => e.indexOf("STRIDE PARTAGE INVALIDE") >= 0);
        if (r.layout !== null || !hit) {
            process.stdout.write("ROUGE stride partage : desaccord non detecte\n");
            failures++;
        } else {
            process.stdout.write("OK    stride partage desaccorde\n        -> "
                + r.errors.filter((e) => e.indexOf("STRIDE") >= 0)[0] + "\n");
        }
    }

    // (g) contre-epreuve VERTE : sur la disposition intacte, tout se resout et la
    //     detection de derive est SILENCIEUSE. Sans ce cas, les rouges ci-dessus
    //     pourraient venir d'un harnais qui echoue toujours.
    {
        const probe = buildProbe(deepCopy(base), defaultValueTypes()) as unknown as Probe;
        const r = resolvePredictionLayout(probe);
        if (r.layout === null) {
            process.stdout.write("ROUGE disposition intacte : layout=null -> "
                + r.errors.join(" | ") + "\n");
            failures++;
        } else if (r.drift.length > 0) {
            process.stdout.write("ROUGE disposition intacte : derive signalee -> "
                + r.drift.join(" | ") + "\n");
            failures++;
        } else {
            const l = r.layout;
            process.stdout.write("OK    disposition intacte : layout resolu, 0 derive\n");
            process.stdout.write("        dpr.healthDamage=" + hx(l.dpr.healthDamage)
                + " dpr.scenarioHealthDamage=" + hx(l.dpr.scenarioHealthDamage)
                + " minMax=" + hx(l.minMaxMin) + "/" + hx(l.minMaxMax)
                + " dprSize=" + hx(l.dprFieldsSize)
                + " pdeStride=" + hx(l.pdeStride)
                + " pdePred=" + hx(l.pdePrediction) + "\n");
        }
    }

    // (h) derive SIGNALEE mais non bloquante : un champ deplace doit etre suivi, et
    //     rapporte en `drift`, PAS en erreur. C'est l'inversion apportee par #279.
    {
        const d = deepCopy(base);
        const c = d["IdunBattle.Core.Services.DamagePredictionResult"];
        const f = c.fields.find((x) => x.name === "AppliedHits");
        if (f) f.offset = 164;
        const probe = buildProbe(d, defaultValueTypes()) as unknown as Probe;
        const r = resolvePredictionLayout(probe);
        const moved = r.layout !== null && r.layout.dpr.appliedHits === 164 - 16;
        const flagged = r.drift.some((x) => x.indexOf("appliedHits") >= 0);
        if (!moved || !flagged) {
            process.stdout.write("ROUGE champ deplace : suivi=" + moved
                + " signale=" + flagged + "\n");
            failures++;
        } else {
            process.stdout.write("OK    champ deplace : suivi ET signale\n        -> "
                + r.drift.join(" ; ") + "\n");
        }
    }

    // ================================================================================
    // #372 — les DEUX entrees de `get_WillBeKill` que le canal n'exposait pas.
    // ================================================================================
    process.stdout.write("\n=== ETAPE 3 (#372) : CannotBeGuaranteedKilled +"
        + " BlockScenarios[0] ===\n");
    const { computeWillBeKill, damagePredictionShapeErrors } = mod;

    // (i) le gate est un champ REQUIS : le renommer doit rendre layout=null, pas un
    //     decodeur qui lit le flag a cote (le voisin @0x88 est `LimitedByMinHp`, un bool
    //     lui aussi -- une lecture decalee serait PLAUSIBLE, donc indetectable).
    {
        const d = deepCopy(base);
        const c = d["IdunBattle.Core.Services.DamagePredictionResult"];
        const f = c.fields.find((x) => x.name === "CannotBeGuaranteedKilled");
        if (f) f.name = "CannotBeGuaranteedKilledXX";
        const probe = buildProbe(d, defaultValueTypes()) as unknown as Probe;
        const r = resolvePredictionLayout(probe);
        const hit = r.errors.some((e) => e.indexOf("CannotBeGuaranteedKilled") >= 0);
        if (r.layout !== null || !hit) {
            process.stdout.write("ROUGE gate renomme : layout="
                + (r.layout === null ? "null" : "RENDU") + " signale=" + hit + "\n");
            failures++;
        } else {
            process.stdout.write("OK    gate renomme -> layout=null et nom cite\n");
        }
    }

    // (j) la chaine du SCENARIO (`BlockScenarios[0]`) est resolue sur la classe du champ
    //     `DefaultScenario` -- meme type, etabli par `GetBlockScenarioOrDefault`. Casser
    //     `Probability` doit donc casser la resolution ENTIERE, pas la degrader.
    {
        const d = deepCopy(base);
        const c = d["IdunBattle.Core.Services.DamagePredictionScenario"];
        const f = c.fields.find((x) => x.name === "Probability");
        if (f) f.name = "ProbabilityZZ";
        const probe = buildProbe(d, defaultValueTypes()) as unknown as Probe;
        const r = resolvePredictionLayout(probe);
        const hit = r.errors.some((e) => e.indexOf("DamagePredictionScenario.Probability") >= 0);
        if (r.layout !== null || !hit) {
            process.stdout.write("ROUGE scenario.Probability renomme : layout="
                + (r.layout === null ? "null" : "RENDU") + " signale=" + hit + "\n");
            failures++;
        } else {
            process.stdout.write("OK    scenario.Probability renomme -> layout=null\n");
        }
    }

    // (k) contre-epreuve VERTE du sous-layout scenario : sur la disposition intacte, les
    //     trois offsets ET le stride se resolvent, aux valeurs LUES au decompile
    //     (`get_WillBeKill` lit `BlockScenarios[0] + 0x0c`).
    {
        const probe = buildProbe(deepCopy(base), defaultValueTypes()) as unknown as Probe;
        const r = resolvePredictionLayout(probe);
        const sc = r.layout ? r.layout.scenario : null;
        const want = { probability: 0x00, healthDamageMin: 0x0c, healthDamageMax: 0x10,
            stride: 0x24 };
        if (sc === null) {
            process.stdout.write("ROUGE sous-layout scenario : non resolu\n");
            failures++;
        } else if (sc.probability !== want.probability
            || sc.healthDamageMin !== want.healthDamageMin
            || sc.healthDamageMax !== want.healthDamageMax || sc.stride !== want.stride) {
            process.stdout.write("ROUGE sous-layout scenario : "
                + JSON.stringify(sc) + " != " + JSON.stringify(want) + "\n");
            failures++;
        } else {
            process.stdout.write("OK    sous-layout scenario : prob=" + hx(sc.probability)
                + " hpMin=" + hx(sc.healthDamageMin) + " hpMax=" + hx(sc.healthDamageMax)
                + " stride=" + hx(sc.stride) + " (le +0x0c de get_WillBeKill)\n");
        }
    }

    // (l) `computeWillBeKill` = le mirror ENTIER. Table de verite ; chaque ligne separe
    //     une facon differente de se tromper. Les lignes 4 et 5 sont les seules qui
    //     DISCRIMINENT le choix de borne : elles opposent `blockKillDmg` a `willKillDmg`.
    {
        type Row = [string, Parameters<typeof computeWillBeKill>[0], boolean | null];
        const rows: Row[] = [
            ["gate arme : les bornes tuent, le natif rend false",
                { hpBefore: 10, willKillDmg: 999, cannotBeGuaranteedKilled: 1,
                    blockScenarioCount: 0, blockKillDmg: null }, false],
            ["pas de scenario de block, borne letale -> true",
                { hpBefore: 10, willKillDmg: 10, cannotBeGuaranteedKilled: 0,
                    blockScenarioCount: 0, blockKillDmg: null }, true],
            ["pas de scenario de block, borne insuffisante -> false",
                { hpBefore: 10, willKillDmg: 9, cannotBeGuaranteedKilled: 0,
                    blockScenarioCount: 0, blockKillDmg: null }, false],
            ["BlockScenarios[0] PRIME et refuse le kill (bloc < hp < defaut)",
                { hpBefore: 10, willKillDmg: 999, cannotBeGuaranteedKilled: 0,
                    blockScenarioCount: 1, blockKillDmg: 9 }, false],
            ["BlockScenarios[0] PRIME et accorde le kill (defaut < hp <= bloc)",
                { hpBefore: 10, willKillDmg: 1, cannotBeGuaranteedKilled: 0,
                    blockScenarioCount: 1, blockKillDmg: 10 }, true],
            ["liste NON MESUREE -> null, jamais false",
                { hpBefore: 10, willKillDmg: 999, cannotBeGuaranteedKilled: 0,
                    blockScenarioCount: null, blockKillDmg: null }, null],
            ["count>=1 mais borne NON MESUREE -> null",
                { hpBefore: 10, willKillDmg: 999, cannotBeGuaranteedKilled: 0,
                    blockScenarioCount: 1, blockKillDmg: null }, null],
        ];
        for (const [label, input, want] of rows) {
            const got = computeWillBeKill(input).willBeKill;
            if (got !== want) {
                process.stdout.write("ROUGE computeWillBeKill : " + label
                    + " -> attendu " + want + ", obtenu " + got + "\n");
                failures++;
            } else {
                process.stdout.write("OK    computeWillBeKill : " + label + "\n");
            }
        }
    }

    // (m) sentinelles de FORME sur les champs neufs : un bool hors {0,1} et un Count
    //     aberrant accusent le DECODEUR (base fausse), pas la bataille.
    {
        const okFields = {
            hpBefore: 100, armorBefore: null, shieldBefore: 0,
            willKillDmg: 10, mightKillDmg: 20,
            cannotBeGuaranteedKilled: 0, blockScenarioCount: 0, blockProbability: null,
            blockKillDmg: null, blockMightDmg: null, willKillDmgEffective: 10,
            willBeKill: false, mightBeKill: false,
            healthDmgMin: 1, healthDmgMax: 2, shieldDmgMin: 0, shieldDmgMax: 0,
            totalDmgMin: 1, totalDmgMax: 2, limitedByMinHp: 0, mightCrit: 0,
            forceOverkill: 0, preventOverkill: 0, appliedHits: 1,
        };
        const cases: Array<[string, Record<string, unknown>, string]> = [
            ["bool de gate hors {0,1}", { cannotBeGuaranteedKilled: 25 },
                "cannotBeGuaranteedKilled=25 hors {0,1}"],
            ["Count negatif", { blockScenarioCount: -1 },
                "blockScenarioCount=-1 hors [0,1024]"],
            ["Count delirant", { blockScenarioCount: 70000 },
                "blockScenarioCount=70000 hors [0,1024]"],
            ["paire de block inversee",
                { blockScenarioCount: 1, blockKillDmg: 9, blockMightDmg: 3 },
                "blockKillDmg=9 > blockMightDmg=3"],
        ];
        for (const [label, mut, needle] of cases) {
            const v = { ...okFields, ...mut } as Parameters<typeof damagePredictionShapeErrors>[0];
            const errs = damagePredictionShapeErrors(v);
            if (!errs.some((e) => e.indexOf(needle) >= 0)) {
                process.stdout.write("ROUGE sentinelle : " + label
                    + " non detectee -> [" + errs.join(" ; ") + "]\n");
                failures++;
            } else {
                process.stdout.write("OK    sentinelle : " + label + "\n");
            }
        }
        // Contre-epreuve : la forme INTACTE ne doit lever aucune sentinelle, sinon les
        // rouges ci-dessus ne prouveraient rien.
        const clean = damagePredictionShapeErrors(
            okFields as Parameters<typeof damagePredictionShapeErrors>[0]);
        if (clean.length > 0) {
            process.stdout.write("ROUGE sentinelle : forme intacte signalee -> "
                + clean.join(" ; ") + "\n");
            failures++;
        } else {
            process.stdout.write("OK    sentinelle : forme intacte silencieuse\n");
        }
    }

    process.stdout.write("\nBILAN : " + (failures === 0 ? "OK" : failures + " ECHEC(S)")
        + "\n");
    process.exitCode = failures === 0 ? 0 : 1;
}

void main();
