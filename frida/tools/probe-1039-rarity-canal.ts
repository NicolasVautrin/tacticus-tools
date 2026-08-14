/* Garde de #1039 -- le canal `rarity` de `combatSnapshot`, resolu PAR NOM.
 *
 * Lancement (depuis `frida/`) :
 *     npx tsx tools/probe-1039-rarity-canal.ts            # etapes 1 + 2 (host requis)
 *     npx tsx tools/probe-1039-rarity-canal.ts --offline  # etape 2 seule (deterministe)
 *
 * POURQUOI CE HARNAIS EXISTE. `frida/hooks/game/rarity.ts` ne peut pas s'executer hors du
 * process de jeu, et le valider EXIGERAIT une reinjection -- geste interdit tant qu'une
 * session est partagee. La resolution y est donc parametree par un `RarityProbe` : ce
 * harnais en fournit un construit sur la disposition REELLE du build courant, capturee par
 * le RPC `classFields`, puis sur des MUTATIONS de cette disposition. Ce qui tourne ici est
 * le code de PRODUCTION (`resolveRarityChannel`), pas une copie. Meme dispositif que
 * `tools/probe-279-layout-by-name.ts`.
 *
 * CE QU'IL MESURE :
 *   1. LIVE -- la disposition rendue par les metadonnees IL2CPP du build courant,
 *      confrontee aux offsets LUS AU DECOMPILE. Le point central de l'etape : le meme
 *      `0x74` designe la RARETE dans `BaseUnitComponent` et le MULTIPLICATEUR dans
 *      `UnitConfiguration` -- deux structs, un offset, et `rpc-snapshot.ts` lit deja le
 *      second. On le VERIFIE au lieu de le croire.
 *   2. ADVERSARIAL -- on FAUSSE la disposition et on exige que le canal soit REFUSE
 *      (`channel === null`) avec un message nomme, au lieu de retomber sur -1 / 0. Le cas
 *      qui compte : le champ type sur l'un des QUATRE enums homonymes d'ordinaux --
 *      confusion SILENCIEUSE EN ORDINAL, que seul le nom PLEIN rend visible.
 *   3. Contre-epreuve VERTE : sur la disposition intacte, tout se resout, 0 erreur,
 *      0 derive. Sans elle, les rouges ci-dessus pourraient venir d'un harnais qui echoue
 *      toujours.
 *
 * CE QU'IL NE MESURE PAS : que le bundle INJECTE emette ces valeurs, ni ce que
 * `readRarity` rend sur une entite reelle. Cela exige un reinject. Le capteur reste NON
 * CONFRONTE EN LIVE tant que ce n'est pas fait.
 */

// --- Stub des globaux Frida --------------------------------------------------------
// `hooks/il2cpp/helpers.ts` touche `Process` / `NativeFunction` des son chargement. Le
// stub sert UNIQUEMENT a rendre l'import possible : `LIVE_PROBE` n'y trouvera aucune
// classe et s'auto-declarera en echec, ce qui est le comportement attendu hors process.
// Le harnais, lui, appelle `resolveRarityChannel` avec SON probe.

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

interface RpcField { name: string; offset: number; type: string; declaredBy: string; }
interface RpcClass {
    ns: string; cls: string; boxedSize: number;
    fields: RpcField[];
    /** Membres, quand la classe est un ENUM. `null` sinon. */
    members: Record<string, number> | null;
}

type Dispo = Record<string, RpcClass>;

const COMP_KEY = "IdunBattle.Entities.Components.BaseUnitComponent";
const CFG_KEY = "IdunBattle.Configuration.UnitConfiguration";
const ENUM_KEY = "idun.meta.Rarity";
/** Le look-alike qu'on injecte a l'etape 2. Il EXISTE dans le build, avec exactement les
 *  six memes membres aux memes ordinaux (cf. `data/symbols/<build>/frida/enums.tsv`), et
 *  c'est celui que `case-1024` §4 et `#999-r1`/`#999-r3` nommaient par erreur. */
const LOOKALIKE_KEY = "IdunMetaLogic.UserProgress.Model.UnitRarity";

const RARITY_MEMBERS: Record<string, number> = {
    Common: 0, Uncommon: 1, Rare: 2, Epic: 3, Legendary: 4, Mythic: 5,
};

/** Offsets LUS au decompile de
 *  `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent`
 *  (`component+0x74 = config+0x80`) et des trois gates. L'etape 1 les re-mesure. */
const DECOMPILED_COMPONENT_OFF = 0x74;
const DECOMPILED_CONFIG_OFF = 0x80;
/** Le champ que `rpc-snapshot.ts` lit DEJA a `UnitConfiguration+0x74`, sous `UCFG.mult`.
 *  C'est LUI que lirait une recopie d'offset d'un struct vers l'autre. */
const CONFIG_TRAP_FIELD = "AbilityVariablesMultiplierPercentage";

/** Disposition capturee le 2026-08-14 sur le build `rnca9r7q6c`, session 88, par
 *  `POST /api/scripts/88/rpc {"method":"classFields",...}` et
 *  `{"method":"dumpEnum","args":[{"asm":"IdunSharedAssembly.dll","ns":"idun.meta",
 *  "cls":"Rarity"}]}`. Offsets BRUTS (types REFERENCE : header objet compris).
 *
 *  ⚠ RESTREINTE AUX CHAMPS QUE LE RESOLVEUR TOUCHE, plus le champ-piege. `UnitConfiguration`
 *  en porte 37 et `BaseUnitComponent` 17 : les recopier tous ferait rougir ce harnais au
 *  premier champ deplace AILLEURS, sans rapport avec la rarete. L'etape 1 le dit
 *  explicitement quand elle compare. */
const SNAPSHOT: Dispo = {
    [COMP_KEY]: {
        ns: "IdunBattle.Entities.Components", cls: "BaseUnitComponent",
        boxedSize: 120, members: null,
        fields: [
            { name: "Id", offset: 16, type: "String", declaredBy: "BaseUnitComponent" },
            { name: "Rarity", offset: 116, type: "Rarity", declaredBy: "BaseUnitComponent" },
        ],
    },
    [CFG_KEY]: {
        ns: "IdunBattle.Configuration", cls: "UnitConfiguration",
        boxedSize: 216, members: null,
        fields: [
            { name: CONFIG_TRAP_FIELD, offset: 116, type: "Int32", declaredBy: "UnitConfiguration" },
            { name: "Rarity", offset: 128, type: "Rarity", declaredBy: "UnitConfiguration" },
        ],
    },
    [ENUM_KEY]: {
        ns: "idun.meta", cls: "Rarity", boxedSize: 4,
        members: { ...RARITY_MEMBERS }, fields: [],
    },
    [LOOKALIKE_KEY]: {
        ns: "IdunMetaLogic.UserProgress.Model", cls: "UnitRarity", boxedSize: 4,
        members: { ...RARITY_MEMBERS }, fields: [],
    },
};

// --- Probe construit sur une disposition capturee ----------------------------------

interface FakeClass { key: string; }

function buildProbe(dispo: Dispo): unknown {
    const cl = (k: unknown): RpcClass | undefined => dispo[(k as FakeClass).key];
    return {
        findClass: (ns: string, cls: string) => {
            const key = ns + "." + cls;
            return dispo[key] ? ({ key } as FakeClass) : null;
        },
        className: (k: unknown) => (cl(k) as RpcClass).cls,
        classNamespace: (k: unknown) => (cl(k) as RpcClass).ns,
        instanceSize: (k: unknown) => (cl(k) as RpcClass).boxedSize,
        rawFieldOffset: (k: unknown, name: string) => {
            const f = (cl(k) as RpcClass).fields.find((x) => x.name === name);
            return f ? f.offset : -1;
        },
        fieldTypeClass: (k: unknown, name: string) => {
            const f = (cl(k) as RpcClass).fields.find((x) => x.name === name);
            if (!f) return null;
            // Le TYPE d'un champ est resolu par sa CLE PLEINE quand elle est portee par la
            // disposition (`typeKey`), sinon par le nom court -- ce qui permet d'injecter un
            // homonyme a l'etape 2 sans toucher au reste.
            const key = (f as RpcField & { typeKey?: string }).typeKey
                ?? Object.keys(dispo).find((x) => dispo[x].cls === f.type);
            return key && dispo[key] ? ({ key } as FakeClass) : null;
        },
        enumMembers: (k: unknown) => (cl(k) as RpcClass).members,
        sameClass: (a: unknown, b: unknown) => (a as FakeClass).key === (b as FakeClass).key,
    };
}

function deepCopy(d: Dispo): Dispo {
    return JSON.parse(JSON.stringify(d)) as Dispo;
}

// --- Etape 1 : disposition LIVE ----------------------------------------------------

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
    return "0x" + n.toString(16);
}

async function main(): Promise<void> {
    const mod = await import("../hooks/game/rarity.js");
    const {
        resolveRarityChannel, RARITY_ENUM_FULL_NAME, RARITY_COMPONENT_CLS, RARITY_FIELD,
    } = mod;
    type Probe = Parameters<typeof resolveRarityChannel>[0];

    let failures = 0;
    const offline = process.argv.indexOf("--offline") >= 0;

    // ---- Etape 1 : LIVE ----
    if (!offline) {
        process.stdout.write("=== ETAPE 1 : disposition LIVE vs offsets LUS au decompile"
            + " ===\n");
        const sid = await sessionId();
        if (sid === null) {
            process.stdout.write("HOST INJOIGNABLE ou sans session -- etape 1 NON JOUEE."
                + " Relancer avec le host up, ou --offline pour l'etape 2 seule.\n");
            failures++;
        } else {
            type CF = { ok?: boolean; boxedSize?: number; fields?: RpcField[] };
            const comp = await rpc(sid, "classFields",
                ["IdunBattle.Entities.Components", "BaseUnitComponent"]) as CF;
            const cfg = await rpc(sid, "classFields",
                ["IdunBattle.Configuration", "UnitConfiguration"]) as CF;
            const en = await rpc(sid, "dumpEnum",
                [{ asm: "IdunSharedAssembly.dll", ns: "idun.meta", cls: "Rarity" }]) as
                { values?: Record<string, string> };
            const fieldOf = (c: CF, n: string): RpcField | undefined =>
                (c.fields ?? []).find((f) => f.name === n);

            const rows: Array<[string, number, number]> = [];
            const cr = fieldOf(comp, "Rarity");
            const gr = fieldOf(cfg, "Rarity");
            const tr = fieldOf(cfg, CONFIG_TRAP_FIELD);
            if (!cr || !gr || !tr) {
                process.stdout.write("classFields incomplet : Rarity(comp)="
                    + (cr ? "ok" : "ABSENT") + " Rarity(cfg)=" + (gr ? "ok" : "ABSENT")
                    + " " + CONFIG_TRAP_FIELD + "=" + (tr ? "ok" : "ABSENT") + "\n");
                failures++;
            } else {
                rows.push(["BaseUnitComponent.Rarity", DECOMPILED_COMPONENT_OFF, cr.offset]);
                rows.push(["UnitConfiguration.Rarity", DECOMPILED_CONFIG_OFF, gr.offset]);
                rows.push(["UnitConfiguration." + CONFIG_TRAP_FIELD,
                    DECOMPILED_COMPONENT_OFF, tr.offset]);
                process.stdout.write("champ".padEnd(56) + "decompile".padEnd(12)
                    + "live".padEnd(10) + "verdict\n");
                for (const [label, want, got] of rows) {
                    const ok = want === got;
                    if (!ok) failures++;
                    process.stdout.write(label.padEnd(56) + hx(want).padEnd(12)
                        + hx(got).padEnd(10) + (ok ? "OK" : "ECART") + "\n");
                }
                // LE PIEGE, mesure et non suppose : le meme offset, deux structs, deux sens.
                if (cr.offset === tr.offset) {
                    process.stdout.write("PIEGE CONFIRME : " + hx(cr.offset)
                        + " = RARETE dans BaseUnitComponent ET " + CONFIG_TRAP_FIELD
                        + " dans UnitConfiguration -- une recopie d'offset lirait "
                        + "le multiplicateur (100/180) au lieu de 0..5\n");
                } else {
                    process.stdout.write("ATTENTION : le piege d'offset partage n'existe"
                        + " plus sur ce build (" + hx(cr.offset) + " vs " + hx(tr.offset)
                        + ") -- la prose de `game/rarity.ts` est a relire\n");
                    failures++;
                }
                // Le TYPE du champ doit etre un enum nomme `Rarity` des DEUX cotes.
                if (cr.type !== "Rarity" || gr.type !== "Rarity") {
                    process.stdout.write("TYPE INATTENDU : comp=" + cr.type
                        + " cfg=" + gr.type + "\n");
                    failures++;
                }
            }
            const live = en && en.values ? en.values : null;
            if (live === null) {
                process.stdout.write("dumpEnum(idun.meta.Rarity) KO -- l'enum du type"
                    + " declare des gates ne se resout pas\n");
                failures++;
            } else {
                const got: Record<string, number> = {};
                for (const k of Object.keys(live)) got[k] = parseInt(live[k], 10);
                const same = JSON.stringify(got) === JSON.stringify(RARITY_MEMBERS);
                process.stdout.write("idun.meta.Rarity live = " + JSON.stringify(got)
                    + (same ? "  OK" : "  ECART vs snapshot") + "\n");
                if (!same) failures++;
            }
            process.stdout.write("\n");
        }
    }

    // ---- Etape 2 : mutations adversariales ----
    process.stdout.write("=== ETAPE 2 : mutations adversariales (deterministe) ===\n");

    const expectRefus = (name: string, needle: string, d: Dispo): void => {
        const r = resolveRarityChannel(buildProbe(d) as Probe);
        if (r.channel !== null) {
            process.stdout.write("ROUGE " + name
                + " : canal RENDU (componentOffset=" + hx(r.channel.componentOffset)
                + ") -- il aurait du etre refuse\n");
            failures++;
            return;
        }
        if (!r.errors.some((e) => e.indexOf(needle) >= 0)) {
            process.stdout.write("ROUGE " + name + " : refus sans le motif attendu ("
                + needle + ") -> [" + r.errors.join(" | ") + "]\n");
            failures++;
            return;
        }
        process.stdout.write("OK    " + name + "\n        -> " + r.errors[0] + "\n");
    };

    // (a) champ renomme : `rawFieldOffset` rend -1, et -1 est *truthy* en JS.
    {
        const d = deepCopy(SNAPSHOT);
        const f = d[COMP_KEY].fields.find((x) => x.name === "Rarity");
        if (f) f.name = "RarityXX";
        expectRefus("champ Rarity renomme", "CHAMP INTROUVABLE", d);
    }

    // (b) LE CAS CENTRAL : le champ type sur un des QUATRE enums homonymes d'ordinaux.
    //     Aucune erreur ne serait levee au runtime -- seul le nom PLEIN separe les cinq.
    {
        const d = deepCopy(SNAPSHOT);
        const f = d[COMP_KEY].fields.find((x) => x.name === "Rarity") as
            RpcField & { typeKey?: string };
        f.typeKey = LOOKALIKE_KEY;
        expectRefus("enum homonyme d'ordinaux (" + LOOKALIKE_KEY + ")",
            "ENUM MAL APPARIE", d);
    }

    // (c) offset hors plage d'instance = champ STATIQUE, jamais un champ d'instance.
    {
        const d = deepCopy(SNAPSHOT);
        const f = d[COMP_KEY].fields.find((x) => x.name === "Rarity");
        if (f) f.offset = 4096;
        expectRefus("offset hors instance (statique)", "OFFSET HORS INSTANCE", d);
    }

    // (d) type du champ non resolu : l'ordinal ne serait nommable par personne.
    {
        const d = deepCopy(SNAPSHOT);
        const f = d[COMP_KEY].fields.find((x) => x.name === "Rarity");
        if (f) f.type = "TypeQuiNExistePas";
        expectRefus("type du champ non resolu", "TYPE DE CHAMP NON RESOLU", d);
    }

    // (e) classe du composant absente.
    {
        const d = deepCopy(SNAPSHOT);
        delete d[COMP_KEY];
        expectRefus("BaseUnitComponent absent", "CLASSE INTROUVABLE", d);
    }

    // (f) enum sans membre lisible.
    {
        const d = deepCopy(SNAPSHOT);
        d[ENUM_KEY].members = {};
        expectRefus("enum sans membre", "ENUM VIDE", d);
    }

    // (g) champ DEPLACE : la lecture doit SUIVRE (preuve que rien n'est fige) et le
    //     deplacement doit etre SIGNALE. C'est l'inversion apportee par #279, transposee.
    //     0x70 et pas 0x78 : `boxedSize` vaut 0x78, donc 0x78 tomberait HORS instance et
    //     serait refuse par le cas (c) -- on mesurerait alors le mauvais cran.
    {
        const d = deepCopy(SNAPSHOT);
        const f = d[COMP_KEY].fields.find((x) => x.name === "Rarity");
        if (f) f.offset = 0x70;
        const r = resolveRarityChannel(buildProbe(d) as Probe);
        const suivi = r.channel !== null && r.channel.componentOffset === 0x70;
        const signale = r.drift.some((x) => x.indexOf("BaseUnitComponent.Rarity") >= 0);
        if (!suivi || !signale) {
            process.stdout.write("ROUGE champ deplace : suivi=" + suivi
                + " signale=" + signale + "\n");
            failures++;
        } else {
            process.stdout.write("OK    champ deplace : suivi ET signale\n        -> "
                + r.drift.join(" ; ") + "\n");
        }
    }

    // (h) TEMOIN de config perdu : le canal doit RESTER (le composant fait foi), avec
    //     `configOffset = -1` et une derive. Une degradation BORNEE, pas un refus.
    {
        const d = deepCopy(SNAPSHOT);
        d[CFG_KEY].fields = d[CFG_KEY].fields.filter((x) => x.name !== "Rarity");
        const r = resolveRarityChannel(buildProbe(d) as Probe);
        const ok = r.channel !== null && r.channel.componentOffset === DECOMPILED_COMPONENT_OFF
            && r.channel.configOffset === -1
            && r.drift.some((x) => x.indexOf("temoin perdu") >= 0);
        if (!ok) {
            process.stdout.write("ROUGE temoin perdu : canal="
                + (r.channel === null ? "REFUSE" : "rendu, configOffset="
                    + r.channel.configOffset) + " drift=[" + r.drift.join(" | ") + "]\n");
            failures++;
        } else {
            process.stdout.write("OK    temoin de config perdu : canal conserve,"
                + " configOffset=-1, derive signalee\n");
        }
    }

    // (i) TEMOIN type sur un AUTRE enum : identite de POINTEUR de classe, pas egalite de
    //     nom court -- les cinq enums s'appellent tous `*Rarity`.
    {
        const d = deepCopy(SNAPSHOT);
        const f = d[CFG_KEY].fields.find((x) => x.name === "Rarity") as
            RpcField & { typeKey?: string };
        f.typeKey = LOOKALIKE_KEY;
        const r = resolveRarityChannel(buildProbe(d) as Probe);
        const ok = r.channel !== null && r.channel.configOffset === -1
            && r.drift.some((x) => x.indexOf("meme type d'enum") >= 0);
        if (!ok) {
            process.stdout.write("ROUGE temoin mal type : configOffset="
                + (r.channel ? r.channel.configOffset : "canal REFUSE")
                + " drift=[" + r.drift.join(" | ") + "]\n");
            failures++;
        } else {
            process.stdout.write("OK    temoin de config mal type : ecarte, derive"
                + " signalee\n");
        }
    }

    // (j) CONTRE-EPREUVE VERTE. Sans elle, les rouges ci-dessus ne prouveraient rien.
    {
        const r = resolveRarityChannel(buildProbe(deepCopy(SNAPSHOT)) as Probe);
        if (r.channel === null) {
            process.stdout.write("ROUGE disposition intacte : canal REFUSE -> "
                + r.errors.join(" | ") + "\n");
            failures++;
        } else if (r.errors.length > 0 || r.drift.length > 0) {
            process.stdout.write("ROUGE disposition intacte : erreurs=["
                + r.errors.join(" | ") + "] drift=[" + r.drift.join(" | ") + "]\n");
            failures++;
        } else {
            const c = r.channel;
            const attendu = c.componentOffset === DECOMPILED_COMPONENT_OFF
                && c.configOffset === DECOMPILED_CONFIG_OFF
                && c.enumFullName === RARITY_ENUM_FULL_NAME
                && JSON.stringify(c.members) === JSON.stringify(RARITY_MEMBERS);
            if (!attendu) {
                process.stdout.write("ROUGE disposition intacte : canal "
                    + JSON.stringify(c) + "\n");
                failures++;
            } else {
                process.stdout.write("OK    disposition intacte : "
                    + RARITY_COMPONENT_CLS + "." + RARITY_FIELD + "="
                    + hx(c.componentOffset) + " config=" + hx(c.configOffset)
                    + " enum=" + c.enumFullName + " membres="
                    + Object.keys(c.members).length + " ; 0 erreur, 0 derive\n");
            }
        }
    }

    process.stdout.write("\nBILAN : " + (failures === 0 ? "OK" : failures + " ECHEC(S)")
        + "\n");
    process.exitCode = failures === 0 ? 0 : 1;
}

void main();
