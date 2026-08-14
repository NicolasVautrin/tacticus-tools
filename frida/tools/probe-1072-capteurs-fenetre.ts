/* Garde de #1072 -- les TROIS logiques pures des quatre capteurs de la fenetre.
 *
 * Lancement (depuis `frida/`) :
 *     node node_modules/tsx/dist/cli.mjs tools/probe-1072-capteurs-fenetre.ts
 *     node node_modules/tsx/dist/cli.mjs tools/probe-1072-capteurs-fenetre.ts --offline
 *
 * POURQUOI CE HARNAIS EXISTE. Les quatre capteurs de #1064 ne s'executent que dans le process
 * du jeu : les VALIDER exigerait une reinjection, geste interdit tant qu'une session est
 * partagee. Trois d'entre eux ont donc leur logique EXTRAITE et PARAMETREE -- c'est ce qui rend
 * une faute de cablage detectable AVANT la fenetre, au lieu de lui couter une passe. Ce qui
 * tourne ici est le code de PRODUCTION, pas une copie. Meme dispositif que
 * `tools/probe-1039-rarity-canal.ts` et `tools/probe-279-layout-by-name.ts`.
 *
 * CE QU'IL MESURE :
 *   1. LIVE (facultatif) -- la disposition rendue par les metadonnees du build courant,
 *      confrontee aux offsets LUS au decompile. Point central : `System.Nullable`1` OUVERT
 *      rend `boxedSize: 0` et ses deux champs a l'offset 0. C'est la mesure qui a fait du
 *      `Nullable` un TEMOIN et du NIVEAU le seul etage bloquant.
 *   2. #1036-r8 -- mutations adversariales de `resolveTertiaryChannel`. Le cas qui compte :
 *      l'enum type sur `ActiveAbilityType` (233 ordinaux communs avec `TriggeredAbilityType`)
 *      -- confusion SILENCIEUSE EN ORDINAL. Plus la DEGRADATION BORNEE : le niveau survit a la
 *      perte du Nullable.
 *   3. #982-r6 -- `classInitState`. Le cran garde est l'ORDRE : `initializedBefore` doit etre
 *      lu AVANT le forcage, sinon la seule information qui distingue « le jeu etait chaud » de
 *      « c'est moi qui l'ai chauffe » disparait.
 *   4. #1009-r3 -- `classTagOf`. Un tag doit rendre `null` sur un ENTIER passe en registre et
 *      sur du garbage imprimable, et le nom PLEIN sur un vrai objet.
 *
 * CE QU'IL NE MESURE PAS : que le bundle INJECTE emette ces valeurs, ni ce que les capteurs
 * rendent sur une entite reelle. Cela exige un reinject -- ils restent NON CONFRONTES EN LIVE.
 * Le volet live est `scripts/python/probe_1072_capteurs_de_la_fenetre.py`.
 */

// --- Stub des globaux Frida --------------------------------------------------------
// `hooks/il2cpp/helpers.ts` touche `Process` / `NativeFunction` des son chargement. Le stub sert
// UNIQUEMENT a rendre l'import possible ; les probes de PRODUCTION (`LIVE_PROBE`,
// `LIVE_CLASS_INIT_PROBE`) n'y trouveront rien et s'auto-declareront en echec, ce qui est le
// comportement attendu hors process. Le harnais, lui, appelle les fonctions avec SES probes.

interface StubPtr {
    isNull(): boolean;
    add(n: number): StubPtr;
    readPointer(): StubPtr;
    writePointer(p: unknown): void;
    equals(o: unknown): boolean;
    toString(): string;
}

function makeNullPtr(): StubPtr {
    const p: StubPtr = {
        isNull: () => true,
        add: () => p,
        readPointer: () => p,
        writePointer: () => { /* no-op */ },
        equals: () => true,
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

// --- Disposition, telle que la rend le RPC `classFields` ----------------------------

interface RpcField { name: string; offset: number; type: string; typeKey?: string; }
interface RpcClass { ns: string; cls: string; boxedSize: number; fields: RpcField[]; }
type Dispo = Record<string, RpcClass>;

const CFG_KEY = "IdunBattle.Configuration.UnitConfiguration";
const COMP_KEY = "IdunBattle.Entities.Components.BaseUnitComponent";
const BC_KEY = "IdunBattle.Configuration.BattleConfiguration";
const LEVEL_KEY = "Idun.Shared.Level";
/** L'instance INFLATEE. C'est elle qui porte un layout exploitable. */
const NULLABLE_KEY = "System.Nullable<IdunBattle.Entities.Enum.TriggeredAbilityType>";
/** La DEFINITION OUVERTE, mesuree sur le build en vol : `boxedSize: 0`, deux champs a 0.
 *  L'etage 2 s'en sert pour verifier que le canal DEGRADE au lieu de lire n'importe quoi. */
const NULLABLE_OPEN_KEY = "System.Nullable`1";
const ENUM_KEY = "IdunBattle.Entities.Enum.TriggeredAbilityType";
/** Le look-alike d'ordinaux : 233 ordinaux communs avec `TriggeredAbilityType` (CLAUDE.md,
 *  #270-c). Une confusion serait SILENCIEUSE, et la MEME classe porte `ActiveAbilities`. */
const ENUM_LOOKALIKE_KEY = "IdunBattle.Entities.Enum.ActiveAbilityType";

/** Offsets LUS au decompile
 *  (`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` lit `config + 0xb0` par
 *  `Nullable<T>.get_HasValue` ; `…$$InitBaseComponent` ecrit `component+0x10 = config+0x10`)
 *  et RE-MESURES au RPC `classFields` sur `rnca9r7q6c`, session 89, en lecture pure. */
const DEC_TERTIARY_OFF = 0xb0;
const DEC_TERTIARY_LEVEL_OFF = 0xc0;
const DEC_TERTIARY_MULT_OFF = 0x78;
const DEC_CONFIG_ID_OFF = 0x10;
const DEC_COMPONENT_ID_OFF = 0x10;
const DEC_UNITS_OFF = 0x80;
/** Le champ que `rpc-snapshot.ts` lit DEJA a `UnitConfiguration+0x74` sous `UCFG.mult`.
 *  Voisin immediat du multiplicateur TERTIAIRE (+0x78) : c'est LUI qu'une recopie d'offset
 *  a un chiffre pres irait lire. */
const CONFIG_TRAP_FIELD = "AbilityVariablesMultiplierPercentage";

/** Disposition capturee le 2026-08-14 sur le build `rnca9r7q6c`, session 89, par
 *  `POST /api/scripts/89/rpc {"method":"classFields", …}` -- LECTURE PURE, aucun reinject.
 *  Offsets BRUTS (types REFERENCE : header objet compris ; ValueTypes : offset BOXE).
 *
 *  ⚠ RESTREINTE AUX CHAMPS QUE LE RESOLVEUR TOUCHE, plus le champ-piege. `UnitConfiguration`
 *  en porte 37, `BaseUnitComponent` 17 et `BattleConfiguration` 35 : les recopier tous ferait
 *  rougir ce harnais au premier champ deplace AILLEURS, sans rapport avec ce canal.
 *
 *  ⚠ `Nullable<TriggeredAbilityType>` est le SEUL element NON capture : `classFields(ns, cls)`
 *  ne sait designer qu'une classe par son nom, donc il rend la DEFINITION OUVERTE
 *  (`boxedSize: 0`, champs a 0 -- capturee elle, sous `NULLABLE_OPEN_KEY`). Les offsets 0x10 /
 *  0x14 ci-dessous sont la CONVENTION .NET (`{ bool hasValue; T value; }` aligne), et c'est
 *  precisement pour cela que le capteur ne les ecrit nulle part : il les DERIVE. Ce que
 *  l'etage 2 garde ici, c'est que la derivation REFUSE quand elle echoue. */
const SNAPSHOT: Dispo = {
    [CFG_KEY]: {
        ns: "IdunBattle.Configuration", cls: "UnitConfiguration", boxedSize: 216,
        fields: [
            { name: "Id", offset: DEC_CONFIG_ID_OFF, type: "String" },
            { name: CONFIG_TRAP_FIELD, offset: 0x74, type: "Int32" },
            { name: "TertiaryAbilityVariablesMultiplierPercentage",
                offset: DEC_TERTIARY_MULT_OFF, type: "Int32" },
            { name: "TertiaryAbility", offset: DEC_TERTIARY_OFF, type: "Nullable`1",
                typeKey: NULLABLE_KEY },
            { name: "TertiaryAbilityLevel", offset: DEC_TERTIARY_LEVEL_OFF, type: "Level",
                typeKey: LEVEL_KEY },
        ],
    },
    [COMP_KEY]: {
        ns: "IdunBattle.Entities.Components", cls: "BaseUnitComponent", boxedSize: 120,
        fields: [
            { name: "Id", offset: DEC_COMPONENT_ID_OFF, type: "String" },
            { name: "VisualId", offset: 0x20, type: "String" },
        ],
    },
    [BC_KEY]: {
        ns: "IdunBattle.Configuration", cls: "BattleConfiguration", boxedSize: 240,
        fields: [{ name: "Units", offset: DEC_UNITS_OFF, type: "List`1" }],
    },
    [LEVEL_KEY]: {
        ns: "Idun.Shared", cls: "Level", boxedSize: 20,
        fields: [{ name: "val", offset: 0x10, type: "Int32" }],
    },
    [NULLABLE_KEY]: {
        ns: "System", cls: "Nullable`1", boxedSize: 24,
        fields: [
            { name: "hasValue", offset: 0x10, type: "Boolean" },
            { name: "value", offset: 0x14, type: "TriggeredAbilityType", typeKey: ENUM_KEY },
        ],
    },
    [NULLABLE_OPEN_KEY]: {
        ns: "System", cls: "Nullable`1", boxedSize: 0,
        fields: [
            { name: "hasValue", offset: 0, type: "Boolean" },
            { name: "value", offset: 0, type: "T" },
        ],
    },
    [ENUM_KEY]: {
        ns: "IdunBattle.Entities.Enum", cls: "TriggeredAbilityType", boxedSize: 4, fields: [],
    },
    [ENUM_LOOKALIKE_KEY]: {
        ns: "IdunBattle.Entities.Enum", cls: "ActiveAbilityType", boxedSize: 4, fields: [],
    },
};

/** Les classes qui sont des VALUE TYPES dans la disposition -- ce que `class_is_valuetype`
 *  repond. Sans elle, le deboxage des offsets internes serait un pari. */
const VALUE_TYPES = new Set([LEVEL_KEY, NULLABLE_KEY, NULLABLE_OPEN_KEY, ENUM_KEY,
    ENUM_LOOKALIKE_KEY]);

interface FakeClass { key: string; }

function buildTertiaryProbe(dispo: Dispo, valueTypes: Set<string>): unknown {
    const cl = (k: unknown): RpcClass | undefined => dispo[(k as FakeClass).key];
    return {
        findClass: (ns: string, cls: string) => {
            const key = ns + "." + cls;
            return dispo[key] ? ({ key } as FakeClass) : null;
        },
        className: (k: unknown) => (cl(k) as RpcClass).cls,
        classNamespace: (k: unknown) => (cl(k) as RpcClass).ns,
        instanceSize: (k: unknown) => (cl(k) as RpcClass).boxedSize,
        isValueType: (k: unknown) => valueTypes.has((k as FakeClass).key),
        rawFieldOffset: (k: unknown, name: string) => {
            const f = (cl(k) as RpcClass).fields.find((x) => x.name === name);
            return f ? f.offset : -1;
        },
        fieldTypeClass: (k: unknown, name: string) => {
            const f = (cl(k) as RpcClass).fields.find((x) => x.name === name);
            if (!f) return null;
            const key = f.typeKey ?? Object.keys(dispo).find((x) => dispo[x].cls === f.type);
            return key && dispo[key] ? ({ key } as FakeClass) : null;
        },
    };
}

function deepCopy(d: Dispo): Dispo {
    return JSON.parse(JSON.stringify(d)) as Dispo;
}

const RPC_URL_BASE = "http://127.0.0.1:8765";

interface AdminStatus { session?: { id?: number } }

async function sessionId(): Promise<number | null> {
    try {
        const res = await fetch(RPC_URL_BASE + "/api/admin/status");
        const json = await res.json() as AdminStatus;
        const id = json.session ? json.session.id : undefined;
        return typeof id === "number" ? id : null;
    } catch { return null; }
}

async function rpc(sid: number, method: string, args: unknown[]): Promise<unknown> {
    const res = await fetch(RPC_URL_BASE + "/api/scripts/" + sid + "/rpc", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ method, args }),
    });
    const json = await res.json() as { result?: unknown };
    return json.result;
}

function hx(n: number): string {
    return (n < 0 ? "-0x" : "0x") + Math.abs(n).toString(16);
}

let failures = 0;

function out(x: string): void { process.stdout.write(x); }

async function etapeLive(): Promise<void> {
    out("=== ETAPE 1 : disposition LIVE vs offsets LUS au decompile ===\n");
    const sid = await sessionId();
    if (sid === null) {
        out("HOST INJOIGNABLE ou sans session -- etape 1 NON JOUEE. Relancer avec le host up,"
            + " ou --offline pour les etages deterministes seuls.\n\n");
        failures++;
        return;
    }
    type CF = { ok?: boolean; boxedSize?: number; fields?: RpcField[] };
    const attendus: Array<[string, string, string, number]> = [
        ["IdunBattle.Configuration", "UnitConfiguration", "TertiaryAbility", DEC_TERTIARY_OFF],
        ["IdunBattle.Configuration", "UnitConfiguration", "TertiaryAbilityLevel",
            DEC_TERTIARY_LEVEL_OFF],
        ["IdunBattle.Configuration", "UnitConfiguration",
            "TertiaryAbilityVariablesMultiplierPercentage", DEC_TERTIARY_MULT_OFF],
        ["IdunBattle.Configuration", "UnitConfiguration", "Id", DEC_CONFIG_ID_OFF],
        ["IdunBattle.Entities.Components", "BaseUnitComponent", "Id", DEC_COMPONENT_ID_OFF],
        ["IdunBattle.Configuration", "BattleConfiguration", "Units", DEC_UNITS_OFF],
        ["Idun.Shared", "Level", "val", 0x10],
    ];
    const cache: Record<string, CF> = {};
    out("champ".padEnd(60) + "decompile".padEnd(12) + "live".padEnd(10) + "verdict\n");
    for (const [ns, cls, field, want] of attendus) {
        const key = ns + "." + cls;
        if (!cache[key]) cache[key] = await rpc(sid, "classFields", [ns, cls]) as CF;
        const f = (cache[key].fields ?? []).find((x) => x.name === field);
        const got = f ? f.offset : -1;
        const ok = got === want;
        if (!ok) failures++;
        out((key + "." + field).padEnd(60) + hx(want).padEnd(12) + hx(got).padEnd(10)
            + (ok ? "OK" : "ECART") + "\n");
    }
    // LE PIEGE MESURE, celui qui a decide de la conception : la DEFINITION OUVERTE ne porte
    // pas de layout exploitable. Si ce n'etait plus vrai, la prose du capteur serait a relire.
    const nl = await rpc(sid, "classFields", ["System", "Nullable`1"]) as CF;
    const nf = nl.fields ?? [];
    const h = nf.find((x) => x.name === "hasValue");
    const v = nf.find((x) => x.name === "value");
    if (h && v && h.offset === v.offset && (nl.boxedSize ?? -1) === 0) {
        out("PIEGE CONFIRME : `System.Nullable`1` OUVERT rend boxedSize=0 et hasValue/value"
            + " au MEME offset (" + hx(h.offset) + ") -- deriver dessus donnerait deux offsets"
            + " identiques et faux. C'est pourquoi le Nullable est un TEMOIN et le NIVEAU le"
            + " seul etage bloquant.\n");
    } else {
        out("ATTENTION : la definition ouverte de `Nullable`1` porte desormais un layout"
            + " (boxedSize=" + (nl.boxedSize ?? -1) + ", hasValue=" + (h ? hx(h.offset) : "?")
            + ", value=" + (v ? hx(v.offset) : "?") + ") -- la prose de"
            + " `game/tertiary-ability.ts` est a relire\n");
        failures++;
    }
    // Le TYPE declare, cote metadonnees : c'est le seul canal ou la confusion d'enum se voit.
    const cfg = cache["IdunBattle.Configuration.UnitConfiguration"];
    const ta = (cfg.fields ?? []).find((x) => x.name === "TertiaryAbility");
    const aa = (cfg.fields ?? []).find((x) => x.name === "ActiveAbilities");
    out("types declares : TertiaryAbility=" + (ta ? ta.type : "ABSENT")
        + "  ActiveAbilities=" + (aa ? aa.type : "ABSENT")
        + "  (le second est le voisin qu'une confusion irait lire)\n\n");
}

function etageTertiaire(): void {
    out("=== ETAGE 2 (#1036-r8) : mutations adversariales du canal tertiaire ===\n");
    /* eslint-disable @typescript-eslint/no-var-requires */
    const mod = tertiaryMod;
    const { resolveTertiaryChannel, TERTIARY_ENUM_FULL_NAME } = mod;
    type Probe = Parameters<typeof resolveTertiaryChannel>[0];
    const P = (d: Dispo, vt?: Set<string>): Probe =>
        buildTertiaryProbe(d, vt ?? VALUE_TYPES) as Probe;

    const expectRefus = (name: string, needle: string, d: Dispo, vt?: Set<string>): void => {
        const r = resolveTertiaryChannel(P(d, vt));
        if (r.channel !== null) {
            out("ROUGE " + name + " : canal RENDU (levelOffset="
                + hx(r.channel.levelOffset) + ") -- il aurait du etre refuse\n");
            failures++;
            return;
        }
        if (!r.errors.some((e) => e.indexOf(needle) >= 0)) {
            out("ROUGE " + name + " : refus sans le motif attendu (" + needle + ") -> ["
                + r.errors.join(" | ") + "]\n");
            failures++;
            return;
        }
        out("OK    " + name + "\n        -> " + r.errors[0] + "\n");
    };

    /** Degradation BORNEE : le canal RESTE, le NIVEAU est lisible, l'ability ne l'est pas,
     *  et la perte est DITE. C'est l'inverse d'un refus, et c'est ce qui ferme #1036-r8 meme
     *  quand le Nullable resiste. */
    const expectDegrade = (name: string, needle: string, d: Dispo, vt?: Set<string>): void => {
        const r = resolveTertiaryChannel(P(d, vt));
        if (r.channel === null) {
            out("ROUGE " + name + " : canal REFUSE alors que le NIVEAU restait lisible -> "
                + r.errors.join(" | ") + "\n");
            failures++;
            return;
        }
        const c = r.channel;
        const ok = c.levelOffset === DEC_TERTIARY_LEVEL_OFF && c.levelValOffset === 0
            && !c.abilityReadable && c.abilityEnumFullName === null
            && r.drift.some((x) => x.indexOf(needle) >= 0);
        if (!ok) {
            out("ROUGE " + name + " : level=" + hx(c.levelOffset) + " val="
                + hx(c.levelValOffset) + " abilityReadable=" + c.abilityReadable
                + " enum=" + c.abilityEnumFullName + " drift=[" + r.drift.join(" | ") + "]\n");
            failures++;
            return;
        }
        out("OK    " + name + " : NIVEAU conserve, ability ECARTEE, derive signalee\n"
            + "        -> " + r.drift.filter((x) => x.indexOf(needle) >= 0)[0] + "\n");
    };

    // (a) LE CAS CENTRAL. Le `Nullable` se resout sur sa DEFINITION OUVERTE : deux offsets
    //     EGAUX. Lire dessus donnerait un `hasValue` et un `value` au meme endroit -- un id
    //     d'ability parfaitement plausible et faux. Doit DEGRADER, jamais lire.
    {
        const d = deepCopy(SNAPSHOT);
        const f = d[CFG_KEY].fields.find((x) => x.name === "TertiaryAbility") as RpcField;
        f.typeKey = NULLABLE_OPEN_KEY;
        expectDegrade("Nullable resolu sur sa DEFINITION OUVERTE", "DEFINITION OUVERTE", d);
    }

    // (a') Le VOISIN de (a) : les deux champs du Nullable ABSENTS (renommes). Meme degradation,
    //      MOTIF DIFFERENT -- sans quoi on ferait chercher une inflation la ou il n'y a qu'un
    //      renommage. C'est la distinction que le premier jet ratait.
    {
        const d = deepCopy(SNAPSHOT);
        d[NULLABLE_KEY].fields = d[NULLABLE_KEY].fields.map(
            (x) => ({ ...x, name: x.name + "XX" }));
        expectDegrade("champs du Nullable renommes", "layout du Nullable non derivable", d);
    }

    // (b) L'AUTRE cas central : l'enum type sur `ActiveAbilityType`. 233 ordinaux communs --
    //     aucune erreur au runtime, seul le nom PLEIN separe les deux.
    {
        const d = deepCopy(SNAPSHOT);
        const f = d[NULLABLE_KEY].fields.find((x) => x.name === "value") as RpcField;
        f.typeKey = ENUM_LOOKALIKE_KEY;
        expectDegrade("enum type sur ActiveAbilityType (233 ordinaux communs)",
            "ENUM MAL APPARIE", d);
    }

    // (c) NIVEAU absent = REFUS. C'est le seul etage bloquant : sans lui le residu reste
    //     ouvert, donc rendre un canal serait mentir sur ce qu'on mesure.
    {
        const d = deepCopy(SNAPSHOT);
        d[CFG_KEY].fields = d[CFG_KEY].fields.filter(
            (x) => x.name !== "TertiaryAbilityLevel");
        expectRefus("TertiaryAbilityLevel absent", "CHAMP INTROUVABLE", d);
    }

    // (d) NIVEAU type sur autre chose qu'`Idun.Shared.Level` : c'est ce type qui donne son
    //     sens au ZERO (= verrouille). Le lire comme un entier nu ferait passer un verrou
    //     pour un niveau.
    {
        const d = deepCopy(SNAPSHOT);
        const f = d[CFG_KEY].fields.find((x) => x.name === "TertiaryAbilityLevel") as RpcField;
        f.typeKey = ENUM_KEY;
        expectRefus("niveau type sur autre chose que Idun.Shared.Level",
            "TYPE DE NIVEAU MAL APPARIE", d);
    }

    // (e) Cle de jointure perdue cote ENTITE : sans elle, aucune configuration n'est
    //     atteignable -- et c'est precisement le maillon qui rend la voie MoW-compatible.
    {
        const d = deepCopy(SNAPSHOT);
        d[COMP_KEY].fields = d[COMP_KEY].fields.filter((x) => x.name !== "Id");
        expectRefus("BaseUnitComponent.Id absent", "CHAMP INTROUVABLE", d);
    }

    // (f) `BattleConfiguration` absente : rien a parcourir.
    {
        const d = deepCopy(SNAPSHOT);
        delete d[BC_KEY];
        expectRefus("BattleConfiguration absente", "CLASSE INTROUVABLE", d);
    }

    // (g) OFFSET HORS INSTANCE = champ statique, jamais un champ d'instance.
    {
        const d = deepCopy(SNAPSHOT);
        const f = d[CFG_KEY].fields.find((x) => x.name === "TertiaryAbilityLevel") as RpcField;
        f.offset = 4096;
        expectRefus("niveau hors instance (statique)", "OFFSET HORS INSTANCE", d);
    }

    // (h) VALUETYPE INDETERMINABLE sur le NIVEAU : deboxer ou non change le resultat de
    //     16 octets. Ne pas savoir doit REFUSER, pas choisir.
    {
        const d = deepCopy(SNAPSHOT);
        const vt = new Set(VALUE_TYPES);
        const probe = buildTertiaryProbe(d, vt) as Record<string, unknown>;
        probe.isValueType = () => null;
        const r = resolveTertiaryChannel(probe as unknown as Probe);
        const ok = r.channel === null
            && r.errors.some((e) => e.indexOf("CHAMP INTERNE DU NIVEAU NON DERIVABLE") >= 0);
        if (!ok) {
            out("ROUGE valuetype indeterminable : canal="
                + (r.channel === null ? "REFUSE" : "RENDU") + " errors=["
                + r.errors.join(" | ") + "]\n");
            failures++;
        } else {
            out("OK    valuetype indeterminable sur le NIVEAU : refuse\n        -> "
                + r.errors[0] + "\n");
        }
    }

    // (i) LE PIEGE D'OFFSET VOISIN. Si le deboxage etait OUBLIE sur `Level`, `levelValOffset`
    //     vaudrait 0x10 et la lecture viserait `TertiaryAbilityLevel + 0x10` = un AUTRE champ.
    //     On le mesure sur la disposition INTACTE : la somme doit rester l'offset du niveau.
    {
        const r = resolveTertiaryChannel(P(deepCopy(SNAPSHOT)));
        const somme = r.channel ? r.channel.levelOffset + r.channel.levelValOffset : -1;
        if (somme !== DEC_TERTIARY_LEVEL_OFF) {
            out("ROUGE deboxage du niveau : lecture a " + hx(somme) + ", attendu "
                + hx(DEC_TERTIARY_LEVEL_OFF) + " (un oubli de deboxage viserait +0x10)\n");
            failures++;
        } else {
            out("OK    deboxage du niveau : lecture a " + hx(somme)
                + " (offset du champ + 0 interne)\n");
        }
    }

    // (j) TEMOIN de multiplicateur perdu : degradation bornee, le canal RESTE et l'ability
    //     aussi. La perte porte sur -1, pas sur un repli vers le VOISIN 0x74.
    {
        const d = deepCopy(SNAPSHOT);
        d[CFG_KEY].fields = d[CFG_KEY].fields.filter(
            (x) => x.name !== "TertiaryAbilityVariablesMultiplierPercentage");
        const r = resolveTertiaryChannel(P(d));
        const ok = r.channel !== null && r.channel.multiplierOffset === -1
            && r.channel.abilityReadable
            && r.drift.some((x) => x.indexOf("temoin perdu") >= 0);
        if (!ok) {
            out("ROUGE temoin multiplicateur : " + JSON.stringify(r.channel) + " drift=["
                + r.drift.join(" | ") + "]\n");
            failures++;
        } else {
            out("OK    temoin de multiplicateur perdu : -1, canal et ability conserves\n");
        }
    }

    // (k) CONTRE-EPREUVE VERTE. Sans elle, les rouges ci-dessus ne prouveraient rien.
    {
        const r = resolveTertiaryChannel(P(deepCopy(SNAPSHOT)));
        if (r.channel === null) {
            out("ROUGE disposition intacte : canal REFUSE -> " + r.errors.join(" | ") + "\n");
            failures++;
        } else if (r.errors.length > 0 || r.drift.length > 0) {
            out("ROUGE disposition intacte : erreurs=[" + r.errors.join(" | ") + "] drift=["
                + r.drift.join(" | ") + "]\n");
            failures++;
        } else {
            const c = r.channel;
            const attendu = c.levelOffset === DEC_TERTIARY_LEVEL_OFF
                && c.levelValOffset === 0
                && c.tertiaryOffset === DEC_TERTIARY_OFF
                && c.nullableHasValueOffset === 0 && c.nullableValueOffset === 4
                && c.multiplierOffset === DEC_TERTIARY_MULT_OFF
                && c.unitsOffset === DEC_UNITS_OFF
                && c.configIdOffset === DEC_CONFIG_ID_OFF
                && c.componentIdOffset === DEC_COMPONENT_ID_OFF
                && c.abilityReadable
                && c.abilityEnumFullName === TERTIARY_ENUM_FULL_NAME;
            if (!attendu) {
                out("ROUGE disposition intacte : canal " + JSON.stringify(c) + "\n");
                failures++;
            } else {
                out("OK    disposition intacte : niveau=" + hx(c.levelOffset)
                    + " ability=" + hx(c.tertiaryOffset) + " nullable{has="
                    + hx(c.nullableHasValueOffset) + ",val=" + hx(c.nullableValueOffset)
                    + "} enum=" + c.abilityEnumFullName + " ; 0 erreur, 0 derive\n");
            }
        }
    }
    out("\n");
}

function etageClassInit(): void {
    out("=== ETAGE 3 (#982-r6) : forcage d'initialisation, et l'ORDRE ===\n");
    const { classInitState } = classInitMod;
    const K = NULL_PTR as unknown as NativePointer;

    /** Un probe qui SIMULE une classe froide qui se rechauffe au forcage, et COMPTE ses
     *  lectures : c'est l'instrument qui distingue « lu avant » de « lu apres ». */
    const froide = (opts: { exporte: boolean; leve?: boolean }) => {
        const etat = { chaud: false, lectures: [] as boolean[] };
        return {
            etat,
            probe: {
                readInitialized: (): boolean | null => {
                    etat.lectures.push(etat.chaud);
                    return etat.chaud;
                },
                forceInit: opts.exporte
                    ? (): void => {
                        if (opts.leve) throw new Error("boom");
                        etat.chaud = true;
                    }
                    : null,
            },
        };
    };

    // (a) L'ORDRE. Une classe FROIDE qu'on force doit rendre `before=false, after=true`.
    //     Si `initializedBefore` etait lu APRES le forcage, il vaudrait `true` -- et le
    //     lecteur croirait mesurer l'etat du JEU alors qu'il mesure le sien.
    {
        const { etat, probe } = froide({ exporte: true });
        const r = classInitState(probe, K, true);
        const ok = r.initializedBefore === false && r.initialized === true
            && r.forcedInit === true && r.forceInitError === null
            && etat.lectures.length === 2 && etat.lectures[0] === false;
        if (!ok) {
            out("ROUGE ordre : " + JSON.stringify(r) + " lectures="
                + JSON.stringify(etat.lectures) + "\n");
            failures++;
        } else {
            out("OK    ordre : before=false lu AVANT le forcage, after=true apres\n");
        }
    }

    // (b) SANS forcage, on n'appelle rien. Le drapeau est explicite, et une lecture de
    //     vtable ne doit jamais chauffer une classe a l'insu de l'appelant.
    {
        const { etat, probe } = froide({ exporte: true });
        const r = classInitState(probe, K, false);
        const ok = r.initializedBefore === false && r.initialized === false
            && r.forcedInit === false && r.forceInitError === null && etat.chaud === false;
        if (!ok) { out("ROUGE sans forcage : " + JSON.stringify(r) + "\n"); failures++; }
        else out("OK    sans forcage : rien n'est appele, la classe reste froide\n");
    }

    // (c) EXPORT ABSENT + forcage demande : `forcedInit` reste FAUX et l'echec est NOMME.
    //     Un capteur qui rendrait `forcedInit: true` ferait lire les zeros comme une mesure.
    {
        const { probe } = froide({ exporte: false });
        const r = classInitState(probe, K, true);
        const ok = r.forcedInit === false && r.runtimeClassInitAvailable === false
            && r.forceInitError !== null
            && r.forceInitError.indexOf("il2cpp_runtime_class_init") >= 0;
        if (!ok) { out("ROUGE export absent : " + JSON.stringify(r) + "\n"); failures++; }
        else {
            out("OK    export absent : forcedInit=false, echec NOMME\n        -> "
                + r.forceInitError + "\n");
        }
    }

    // (d) Le forcage LEVE : meme exigence -- pas de `forcedInit: true` menteur.
    {
        const { probe } = froide({ exporte: true, leve: true });
        const r = classInitState(probe, K, true);
        const ok = r.forcedInit === false && r.forceInitError !== null
            && r.forceInitError.indexOf("boom") >= 0 && r.initialized === false;
        if (!ok) { out("ROUGE forcage qui leve : " + JSON.stringify(r) + "\n"); failures++; }
        else out("OK    forcage qui leve : forcedInit=false, cause remontee\n");
    }

    // (e) OFFSET ILLISIBLE : `null`, jamais `false`. `false` = « classe froide », une
    //     assertion sur le jeu ; `null` = « je n'ai pas lu ».
    {
        const probe = {
            readInitialized: (): boolean | null => null,
            forceInit: (): void => { /* */ },
        };
        const r = classInitState(probe, K, false);
        const ok = r.initializedBefore === null && r.initialized === null;
        if (!ok) { out("ROUGE offset illisible : " + JSON.stringify(r) + "\n"); failures++; }
        else out("OK    offset illisible : null (PAS MESURE), jamais false\n");
    }

    // (f) CONTRE-EPREUVE : une classe DEJA chaude, sans forcage, rend une vraie mesure.
    {
        const probe = {
            readInitialized: (): boolean | null => true,
            forceInit: (): void => { /* */ },
        };
        const r = classInitState(probe, K, false);
        const ok = r.initializedBefore === true && r.initialized === true
            && r.forcedInit === false;
        if (!ok) { out("ROUGE classe chaude : " + JSON.stringify(r) + "\n"); failures++; }
        else out("OK    classe deja chaude : mesure du JEU, aucun forcage\n");
    }
    out("\n");
}

function etageClassTag(): void {
    out("=== ETAGE 4 (#1009-r3) : le tag de classe des noeuds DSL ===\n");
    const { classTagOf } = dslMod;
    /** Un faux pointeur : `classTagOf` n'a besoin que de `isNull()` et `toString()`. */
    const P = (hex: string): NativePointer => ({
        isNull: () => hex === "0x0",
        toString: () => hex,
    } as unknown as NativePointer);
    const lecteur = (table: Record<string, { ns: string; cls: string }>) =>
        (p: NativePointer) => {
            const v = table[p.toString()];
            if (!v) throw new Error("adresse non mappee");
            return v;
        };

    const cas: Array<[string, string, Record<string, { ns: string; cls: string }>,
        string | null]> = [
        ["objet nomme -> nom PLEIN", "0x7ff123456780",
            { "0x7ff123456780": { ns: "IdunBattle.Entities.Triggers",
                cls: "IsActiveAbilityTrigger" } },
            "IdunBattle.Entities.Triggers.IsActiveAbilityTrigger"],
        ["classe sans namespace -> nom court", "0x7ff123456790",
            { "0x7ff123456790": { ns: "", cls: "GlobalType" } }, "GlobalType"],
        ["ENTIER passe en registre (un enum) -> null", "0x5", {}, null],
        ["pointeur nul -> null", "0x0", {}, null],
        ["adresse non lisible (leve) -> null", "0x7ff1234567a0", {}, null],
        ["garbage imprimable -> null", "0x7ff1234567b0",
            { "0x7ff1234567b0": { ns: "", cls: "!!\x01 pas un identifiant" } }, null],
        ["nom demesure -> null", "0x7ff1234567c0",
            { "0x7ff1234567c0": { ns: "", cls: "A".repeat(400) } }, null],
        ["nom vide -> null", "0x7ff1234567d0", { "0x7ff1234567d0": { ns: "", cls: "" } },
            null],
    ];
    for (const [label, hexa, table, attendu] of cas) {
        const got = classTagOf(lecteur(table), P(hexa));
        const ok = got === attendu;
        if (!ok) failures++;
        out((ok ? "OK    " : "ROUGE ") + label + " -> " + JSON.stringify(got)
            + (ok ? "" : "  (attendu " + JSON.stringify(attendu) + ")") + "\n");
    }
    // Le cas qui MOTIVE le capteur : deux instances DISTINCTES de la meme classe portent le
    // MEME nom. Le tag ne peut donc pas remplacer le pointeur -- il l'ACCOMPAGNE.
    {
        const t = { "0x7ff100000010": { ns: "IdunBattle.DSL", cls: "TargetsSelector" },
            "0x7ff100000020": { ns: "IdunBattle.DSL", cls: "TargetsSelector" } };
        const a = classTagOf(lecteur(t), P("0x7ff100000010"));
        const b = classTagOf(lecteur(t), P("0x7ff100000020"));
        if (a !== b || a === null) {
            out("ROUGE homonymie : a=" + a + " b=" + b + "\n"); failures++;
        } else {
            out("OK    deux instances DISTINCTES rendent le MEME nom (" + a + ") : c'est"
                + " pourquoi `ret`/`args` restent des pointeurs\n");
        }
    }
    out("\n");
}

// Les imports dynamiques doivent suivre l'installation du stub : `helpers.ts` touche `Process`
// des son chargement.
/* eslint-disable @typescript-eslint/no-explicit-any */
let tertiaryMod: any;
let classInitMod: any;
let dslMod: any;

async function main(): Promise<void> {
    tertiaryMod = await import("../hooks/game/tertiary-ability.js");
    classInitMod = await import("../hooks/il2cpp/class-init.js");
    dslMod = await import("../hooks/features/dsl-ctor-trace.js");

    const offline = process.argv.indexOf("--offline") >= 0;
    if (!offline) await etapeLive();
    etageTertiaire();
    etageClassInit();
    etageClassTag();

    out("PORTEE : ce harnais garde les LOGIQUES PURES des capteurs, hors Frida.\n");
    out("NON COUVERT : que le bundle injecte emette ces valeurs, et ce que les capteurs\n");
    out("  rendent sur une entite reelle -- il faut une fenetre de reinject. Le volet live\n");
    out("  est `scripts/python/probe_1072_capteurs_de_la_fenetre.py`.\n");
    out("NON COUVERT NON PLUS : #969-r4, dont la logique est une INVOCATION native\n");
    out("  (`invokeBoolOrNull`) sans partie pure a exercer -- son contrat est garde par le\n");
    out("  probe Python (etage source), et sa mesure exige la fenetre.\n");
    out("\nBILAN : " + (failures === 0 ? "OK" : failures + " ECHEC(S)") + "\n");
    process.exitCode = failures === 0 ? 0 : 1;
}

void main();
