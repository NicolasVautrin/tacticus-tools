/* Garde de #10008 -- les DEUX canaux qui restaient a ecrire dans le foyer
 * `frida/hooks/features/ai-step/rpc-snapshot.ts` : `receiveDamageTypeThisTurn` (#487-r2) et
 * `weapons` PAR ENTITE (#419-r1-tr14-r5-r2-r1-r2-r1-r2).
 *
 * Lancement (depuis `frida/`) :
 *     node node_modules/tsx/dist/cli.mjs tools/probe-10008-canaux-du-foyer.ts
 *
 * POURQUOI CE HARNAIS EXISTE. Un hook ne s'execute que dans le process du jeu : le VALIDER
 * exigerait une reinjection, geste interdit tant qu'une session est partagee. La logique des
 * deux canaux est donc PARAMETREE (`DictProbe`, `WeaponsProbe`) et rejouee ici sur une
 * disposition capturee en LECTURE PURE, plus des MUTATIONS adversariales. Ce qui tourne ici
 * est le code de PRODUCTION, pas une copie. Meme dispositif que
 * `tools/probe-1039-rarity-canal.ts` et `tools/probe-1072-capteurs-fenetre.ts`.
 *
 * ⚠ ET IL VA PLUS LOIN QUE SES DEUX AINES : il rejoue aussi les fonctions de LECTURE
 * (`RDT.readReceiveDamageTypes`, `WPN.readWeapons`) sur une MEMOIRE SIMULEE. C'est ce qui rend
 * verifiables, sans fenetre, les trois seuils qui ne sont visibles nulle part ailleurs :
 * le `Range < 2` de `get_IsMelee` (une arme de portee 1 est MELEE), le filtrage des slots
 * LIBERES d'un `Dictionary`, et la separation `{}` (mesure) / `null` (panne).
 *
 * CE QU'IL NE MESURE PAS : que le bundle INJECTE emette ces valeurs, ni ce que les capteurs
 * rendent sur une entite reelle. Cela exige un reinject -- ils restent NON CONFRONTES EN LIVE.
 * Le volet live est `scripts/python/probe_10008_canaux_du_foyer.py`.
 */

// --- Stub des globaux Frida ---------------------------------------------------------
// `hooks/il2cpp/helpers.ts` touche `Process` / `NativeFunction` des son chargement. Le stub
// sert UNIQUEMENT a rendre l'import possible ; les `LIVE_PROBE` de production n'y trouveront
// rien et s'auto-declareront en echec, ce qui est le comportement attendu hors process. Le
// harnais, lui, appelle les fonctions avec SES propres probes.

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

// ⚠ IMPORTS DYNAMIQUES, ET C'EST STRUCTUREL. Un `import` statique est HISSÉ : il s'exécute
// AVANT le stub ci-dessus, et `hooks/il2cpp/helpers.ts` touche `Process` dès son chargement
// (`ReferenceError: Process is not defined`). Les modules de production ne peuvent donc être
// chargés qu'APRÈS. Seuls les TYPES sont importés statiquement — `import type` est effacé à la
// compilation, il n'a aucun effet à l'exécution. Même contrainte que `probe-1072`.
import type {
    DictProbe, ReceiveDamageChannel,
} from "../hooks/game/receive-damage-types.js";
import type { WeaponsChannel, WeaponsProbe } from "../hooks/game/weapons.js";

type RdtMod = typeof import("../hooks/game/receive-damage-types.js");
type WeaponsMod = typeof import("../hooks/game/weapons.js");

let RDT: RdtMod;
let WPN: WeaponsMod;

// --- Disposition, telle que la rend le RPC `classFields` ----------------------------

interface FakeField { name: string; offset: number; typeKey: string | null; }
interface FakeClass {
    key: string; ns: string; cls: string; instanceSize: number;
    fields: FakeField[];
    /** `{nom: ordinal}` si c'est un enum. */
    enumMembers?: Record<string, number>;
}
type Dispo = Record<string, FakeClass>;

const ASC_KEY = "IdunBattle.Entities.Components.ActorStatisticsComponent";
/** L'instance INFLATEE du dictionnaire. C'est ELLE qui porte un layout exploitable. */
const DICT_KEY = "System.Collections.Generic.Dictionary<DamageProfileType,Int32>";
/** La definition OUVERTE, MESUREE sur le build en vol : `boxedSize: 0`, DIX champs a 0.
 *  L'etape 2 s'en sert pour verifier que le canal REFUSE au lieu de lire a l'offset 0. */
const DICT_OPEN_KEY = "System.Collections.Generic.Dictionary`2";
const ENTRY_KEY = "System.Collections.Generic.Dictionary<DamageProfileType,Int32>.Entry";
const DPT_KEY = "IdunBattle.Entities.Enum.DamageProfileType";
const WC_KEY = "IdunBattle.Entities.Components.WeaponsComponent";
const WP_KEY = "IdunShared.Battle.WeaponProfile";
const NULLABLE_INT_KEY = "System.Nullable<System.Int32>";
const NULLABLE_OPEN_KEY = "System.Nullable`1";
/** Le look-alike d'ordinaux : le confondre serait SILENCIEUX EN ORDINAL (meme forme que les
 *  cinq `Rarity` de #1039). */
const DPT_LOOKALIKE_KEY = "IdunBattle.Entities.Enum.AttackType";

/** Ordinaux LUS dans `data/symbols/t6dpr4k06g/frida/enums.tsv` -- NON contigus, et `None`
 *  vaut **-1**. Un capteur qui supposerait « 0..N » se tromperait des la premiere cle. */
const DPT_MEMBERS: Record<string, number> = {
    None: -1, Physical: 0, Projectile: 1, Flame: 3, Bolter: 4, Particle: 5, Acid: 6,
    Plasma: 7, Melta: 8, Gauss: 10, Enmitic: 11, Psychic: 13, Power: 14, DirectDamage: 15,
    Energy: 16, Chain: 17, Blast: 18, HeavyRound: 19, Piercing: 20, Las: 21, Bio: 22,
    Pulse: 23, Toxic: 24, Eviscerate: 25,
};

/** Disposition capturee le 2026-08-15 sur le build `t6dpr4k06g`, session 93, par
 *  `POST /api/scripts/93/rpc {"method":"classFields", ...}` -- LECTURE PURE, aucun reinject.
 *  Offsets BRUTS (types REFERENCE : header objet compris ; ValueTypes : offset BOXE).
 *
 *  ⚠ RESTREINTE aux champs que les deux resolveurs TOUCHENT, plus les champs-pieges.
 *  `ActorStatisticsComponent` en porte 52 : les recopier tous ferait rougir ce harnais au
 *  premier champ deplace AILLEURS, sans rapport avec ces canaux.
 *
 *  ⚠ `Entry` n'est PAS mesurable par `classFields` (nom generique -> definition OUVERTE, tous
 *  offsets a 0). Sa disposition est celle du `Dictionary<K,V>.Entry` de .NET
 *  (`{uint hashCode; int next; TKey key; TValue value}`) avec K=V=Int32, donc stride 16 ; le
 *  code de PRODUCTION, lui, la DERIVE et ne l'ecrit nulle part -- c'est justement ce que
 *  l'etape 2d verifie en la faussant. */
function dispositionReelle(): Dispo {
    return {
        [ASC_KEY]: {
            key: ASC_KEY, ns: RDT.RDT_COMPONENT_NS, cls: RDT.RDT_COMPONENT_CLS, instanceSize: 256,
            fields: [
                // Les voisins immediats, pour qu'un decalage d'un cran se VOIE.
                { name: "TotalDamageDealtThisTurn", offset: 0x78, typeKey: null },
                { name: "MaxDamageDealtInOneTurn", offset: 0x7c, typeKey: null },
                { name: RDT.RDT_FIELD, offset: 0x80, typeKey: DICT_KEY },
                { name: "TotalBlocksMade", offset: 0x88, typeKey: null },
            ],
        },
        [DICT_KEY]: {
            key: DICT_KEY, ns: "System.Collections.Generic", cls: "Dictionary`2",
            instanceSize: 0x50,
            fields: [
                { name: "_buckets", offset: 0x10, typeKey: null },
                { name: "_entries", offset: 0x18, typeKey: ENTRY_KEY },
                { name: "_count", offset: 0x20, typeKey: null },
                { name: "_freeList", offset: 0x24, typeKey: null },
                { name: "_freeCount", offset: 0x28, typeKey: null },
            ],
        },
        [ENTRY_KEY]: {
            key: ENTRY_KEY, ns: "System.Collections.Generic", cls: "Entry",
            instanceSize: 0x10 + 16,
            fields: [
                { name: "hashCode", offset: 0x10 + 0, typeKey: null },
                { name: "next", offset: 0x10 + 4, typeKey: null },
                { name: "key", offset: 0x10 + 8, typeKey: DPT_KEY },
                { name: "value", offset: 0x10 + 12, typeKey: null },
            ],
        },
        [DPT_KEY]: {
            key: DPT_KEY, ns: "IdunBattle.Entities.Enum", cls: "DamageProfileType",
            instanceSize: 20, fields: [], enumMembers: DPT_MEMBERS,
        },
        [WC_KEY]: {
            key: WC_KEY, ns: WPN.WEAPONS_COMPONENT_NS, cls: WPN.WEAPONS_COMPONENT_CLS,
            instanceSize: 24,
            fields: [
                { name: "ComponentId", offset: 0x0, typeKey: null },
                { name: WPN.WEAPONS_FIELD, offset: 0x10, typeKey: null },
            ],
        },
        [WP_KEY]: {
            key: WP_KEY, ns: WPN.WEAPON_PROFILE_NS, cls: WPN.WEAPON_PROFILE_CLS, instanceSize: 48,
            fields: [
                { name: "DamageProfileType", offset: 0x10, typeKey: DPT_KEY },
                { name: "DamageProfile", offset: 0x18, typeKey: null },
                { name: "Hits", offset: 0x20, typeKey: null },
                { name: "Range", offset: 0x24, typeKey: NULLABLE_INT_KEY },
            ],
        },
        [NULLABLE_INT_KEY]: {
            key: NULLABLE_INT_KEY, ns: "System", cls: "Nullable`1", instanceSize: 0x10 + 8,
            fields: [
                { name: "hasValue", offset: 0x10 + 0, typeKey: null },
                { name: "value", offset: 0x10 + 4, typeKey: null },
            ],
        },
        // --- Les deux definitions OUVERTES, MESUREES (session 93) : boxedSize 0, tout a 0 ---
        [DICT_OPEN_KEY]: {
            key: DICT_OPEN_KEY, ns: "System.Collections.Generic", cls: "Dictionary`2",
            instanceSize: 0,
            fields: [
                { name: "_buckets", offset: 0, typeKey: null },
                { name: "_entries", offset: 0, typeKey: ENTRY_KEY },
                { name: "_count", offset: 0, typeKey: null },
                { name: "_freeCount", offset: 0, typeKey: null },
            ],
        },
        [NULLABLE_OPEN_KEY]: {
            key: NULLABLE_OPEN_KEY, ns: "System", cls: "Nullable`1", instanceSize: 0,
            fields: [
                { name: "hasValue", offset: 0, typeKey: null },
                { name: "value", offset: 0, typeKey: null },
            ],
        },
        [DPT_LOOKALIKE_KEY]: {
            key: DPT_LOOKALIKE_KEY, ns: "IdunBattle.Entities.Enum", cls: "AttackType",
            instanceSize: 20, fields: [], enumMembers: { None: -1, Physical: 0 },
        },
    };
}

/** Une classe, representee par sa CLE (une chaine). Le probe ne manipule jamais de vrai
 *  pointeur : `NativePointer` est ici un porteur de cle, ce qui suffit aux resolveurs. */
function fakeClassPtr(key: string): NativePointer {
    return { __key: key, isNull: () => false, toString: () => key,
        equals: (o: { __key?: string }) => o?.__key === key } as unknown as NativePointer;
}
function keyOf(p: NativePointer): string {
    return (p as unknown as { __key: string }).__key;
}

function makeProbe(d: Dispo): DictProbe & WeaponsProbe {
    const byNsCls = (ns: string, cls: string): FakeClass | null => {
        for (const k of Object.keys(d)) {
            if (d[k].ns === ns && d[k].cls === cls) return d[k];
        }
        return null;
    };
    return {
        findClass: (ns, cls) => {
            const c = byNsCls(ns, cls);
            return c === null ? null : fakeClassPtr(c.key);
        },
        className: (k) => d[keyOf(k)].cls,
        classNamespace: (k) => d[keyOf(k)].ns,
        instanceSize: (k) => d[keyOf(k)].instanceSize,
        rawFieldOffset: (k, name) => {
            const f = d[keyOf(k)].fields.find((x) => x.name === name);
            return f === undefined ? -1 : f.offset;
        },
        fieldTypeClass: (k, name) => {
            const f = d[keyOf(k)].fields.find((x) => x.name === name);
            if (f === undefined || f.typeKey === null) return null;
            return fakeClassPtr(f.typeKey);
        },
        enumMembers: (k) => d[keyOf(k)].enumMembers ?? null,
    };
}

// --- Memoire SIMULEE, pour rejouer les LECTURES ---------------------------------------
//
// Un `NativePointer` adosse a un `Map<adresse, octet>`. Les lectures multi-octets sont
// reconstituees a la main : c'est volontairement bete, pour qu'aucune erreur de decodage
// du harnais ne puisse etre prise pour une erreur du capteur.

class FakeMem {
    private bytes = new Map<number, number>();
    writeS32(addr: number, v: number): void {
        const u = v >>> 0;
        for (let i = 0; i < 4; i++) this.bytes.set(addr + i, (u >>> (8 * i)) & 0xff);
    }
    writeU8(addr: number, v: number): void { this.bytes.set(addr, v & 0xff); }
    /** Un "pointeur" tient sur 8 octets ; on n'y met que des adresses de cette memoire. */
    writePtr(addr: number, target: number): void {
        this.writeS32(addr, target);
        this.writeS32(addr + 4, 0);
    }
    readS32(addr: number): number {
        let u = 0;
        for (let i = 0; i < 4; i++) u |= (this.bytes.get(addr + i) ?? 0) << (8 * i);
        return u | 0;
    }
    readU8(addr: number): number { return this.bytes.get(addr) ?? 0; }
    ptr(addr: number): NativePointer {
        const self = this;
        const mk = (a: number): NativePointer => ({
            isNull: () => a === 0,
            add: (n: number) => mk(a + n),
            readS32: () => self.readS32(a),
            readU8: () => self.readU8(a),
            readPointer: () => mk(self.readS32(a)),
            toString: () => "0x" + a.toString(16),
            equals: (o: { __addr?: number }) => o?.__addr === a,
            __addr: a,
        } as unknown as NativePointer);
        return mk(addr);
    }
}

// --- Harnais --------------------------------------------------------------------------

let failures = 0;
let checks = 0;

function check(label: string, ok: boolean, detail = ""): void {
    checks++;
    if (ok) { console.log("  OK   " + label); return; }
    failures++;
    console.log("  FAIL " + label + (detail ? " -- " + detail : ""));
}

function mutate(d: Dispo, f: (d: Dispo) => void): Dispo {
    const copy: Dispo = JSON.parse(JSON.stringify(d)) as Dispo;
    f(copy);
    return copy;
}

// Les imports dynamiques doivent SUIVRE l'installation du stub : `helpers.ts` touche `Process`
// des son chargement. Tout ce qui exerce le code de PRODUCTION vit donc dans `main()`.
async function main(): Promise<void> {
    RDT = await import("../hooks/game/receive-damage-types.js");
    WPN = await import("../hooks/game/weapons.js");
    // ===== ETAPE 1 : la disposition REELLE resout les deux canaux ==========================
    console.log("");
    console.log("[1] disposition REELLE (t6dpr4k06g, session 93, lecture pure)");
    {
        const d = dispositionReelle();
        const r = RDT.resolveReceiveDamageChannel(makeProbe(d));
        check("#487-r2 : canal resolu", r.channel !== null, JSON.stringify(r.errors));
        check("#487-r2 : aucun drift", r.drift.length === 0, JSON.stringify(r.drift));
        if (r.channel) {
            check("#487-r2 : champ @0x80", r.channel.fieldOffset === 0x80);
            check("#487-r2 : Entry stride DERIVE = 16", r.channel.entryStride === 16,
                String(r.channel.entryStride));
            check("#487-r2 : key@8 value@12 (deboxes)",
                r.channel.keyOff === 8 && r.channel.valueOff === 12,
                r.channel.keyOff + "/" + r.channel.valueOff);
            check("#487-r2 : enum de cle NOMME",
                r.channel.keyEnumFullName === RDT.RDT_KEY_ENUM_FULL_NAME);
            check("#487-r2 : None vaut -1 (ordinaux NON contigus)",
                r.channel.keyEnumMembers.None === -1);
        }
        const w = WPN.resolveWeaponsChannel(makeProbe(d));
        check("#419 : canal resolu", w.channel !== null, JSON.stringify(w.errors));
        check("#419 : aucun drift", w.drift.length === 0, JSON.stringify(w.drift));
        if (w.channel) {
            check("#419 : liste @0x10", w.channel.listOffset === 0x10);
            check("#419 : Range @0x24", w.channel.rangeOffset === 0x24);
            check("#419 : Nullable DERIVE hasValue@0 value@4",
                w.channel.rangeHasValueOff === 0 && w.channel.rangeValueOff === 4,
                w.channel.rangeHasValueOff + "/" + w.channel.rangeValueOff);
            check("#419 : enum de profil NOMME",
                w.channel.profileEnumFullName === WPN.WEAPON_PROFILE_ENUM_FULL_NAME);
        }
    }

    // ===== ETAPE 2 : mutations ADVERSARIALES -- chacune doit REFUSER ou DEGRADER ===========
    console.log("");
    console.log("[2] mutations adversariales");
    {
        const base = dispositionReelle();

        // (a) LE CAS QUI A MOTIVE CE MODULE. La fiche #487-r2 nomme le champ
        //     `receivedDamageThisTurn` ; le build le nomme `ReceiveDamageTypeThisTurn`. Un
        //     `fieldOffsetOr(asClass, "ReceivedDamageThisTurn", 0x80)` se serait REPLIE en silence
        //     sur le litteral decompile -- il aurait « marche » sur ce build par coincidence, et
        //     serait devenu faux au premier deplacement de champ, sans rien dire.
        const renomme = mutate(base, (d) => {
            const f = d[ASC_KEY].fields.find((x) => x.name === RDT.RDT_FIELD)!;
            f.name = "ReceivedDamageThisTurn";
        });
        const rRen = RDT.resolveReceiveDamageChannel(makeProbe(renomme));
        check("(a) nom de la FICHE -> canal REFUSE (aucun repli sur 0x80)",
            rRen.channel === null && rRen.errors.some((e) => e.indexOf("CHAMP INTROUVABLE") >= 0),
            JSON.stringify(rRen.errors));

        // (b) La disposition OUVERTE du Dictionary. MESUREE : tous les champs a 0. C'est le cas
        //     que la garde `< 0` LAISSE PASSER -- il faut une garde de PLAGE.
        const ouvert = mutate(base, (d) => {
            const f = d[ASC_KEY].fields.find((x) => x.name === RDT.RDT_FIELD)!;
            f.typeKey = DICT_OPEN_KEY;
        });
        const rOuv = RDT.resolveReceiveDamageChannel(makeProbe(ouvert));
        check("(b) Dictionary NON INFLATE -> canal REFUSE",
            rOuv.channel === null
            && rOuv.errors.some((e) => e.indexOf("DISPOSITION OUVERTE") >= 0),
            JSON.stringify(rOuv.errors));

        // (c) Enum de cle mal apparie : SILENCIEUX EN ORDINAL, seul le nom PLEIN le montre.
        const mauvaisEnum = mutate(base, (d) => {
            const f = d[ENTRY_KEY].fields.find((x) => x.name === "key")!;
            f.typeKey = DPT_LOOKALIKE_KEY;
        });
        const rEnum = RDT.resolveReceiveDamageChannel(makeProbe(mauvaisEnum));
        check("(c) enum de cle mal apparie -> canal REFUSE",
            rEnum.channel === null
            && rEnum.errors.some((e) => e.indexOf("ENUM MAL APPARIE") >= 0),
            JSON.stringify(rEnum.errors));

        // (d) Le stride d'`Entry` retreci sous ses propres champs : c'est la faute #276-r1
        //     (`ENTRY_SIZE = 32` sur une entree de 24), qui faisait lire a cote des la 2e cle.
        const strideFaux = mutate(base, (d) => { d[ENTRY_KEY].instanceSize = 0x10 + 8; });
        const rStride = RDT.resolveReceiveDamageChannel(makeProbe(strideFaux));
        check("(d) Entry trop courte pour ses champs -> canal REFUSE",
            rStride.channel === null
            && rStride.errors.some((e) => e.indexOf("HORS BORNES") >= 0),
            JSON.stringify(rStride.errors));

        // (e) DEGRADATION BORNEE : `_freeCount` disparait -> le canal RESTE, le controle tombe.
        //     Un capteur qui refuserait tout ici perdrait la mesure pour un temoin.
        const sansFree = mutate(base, (d) => {
            d[DICT_KEY].fields = d[DICT_KEY].fields.filter((x) => x.name !== "_freeCount");
        });
        const rFree = RDT.resolveReceiveDamageChannel(makeProbe(sansFree));
        check("(e) _freeCount absent -> canal RESOLU, drift NOMME",
            rFree.channel !== null && rFree.channel.freeCountOff === -1
            && rFree.drift.some((x) => x.indexOf("_freeCount") >= 0),
            JSON.stringify(rFree.errors) + JSON.stringify(rFree.drift));

        // (f) DEGRADATION BORNEE : `Entry.next` disparait -> plus de filtrage des slots liberes,
        //     et le capteur le DIT (`freeSlotsSkipped: null`) au lieu de les compter comme des cles.
        const sansNext = mutate(base, (d) => {
            d[ENTRY_KEY].fields = d[ENTRY_KEY].fields.filter((x) => x.name !== "next");
        });
        const rNext = RDT.resolveReceiveDamageChannel(makeProbe(sansNext));
        check("(f) Entry.next absent -> canal RESOLU, drift NOMME",
            rNext.channel !== null && rNext.channel.nextOff === -1
            && rNext.drift.some((x) => x.indexOf("next") >= 0),
            JSON.stringify(rNext.errors) + JSON.stringify(rNext.drift));

        // (g) Champ DEPLACE : la lecture SUIT (c'est la doc qui devient fausse), et le drift le dit.
        const deplace = mutate(base, (d) => {
            const f = d[ASC_KEY].fields.find((x) => x.name === RDT.RDT_FIELD)!;
            f.offset = 0x90;
        });
        const rDep = RDT.resolveReceiveDamageChannel(makeProbe(deplace));
        check("(g) champ deplace -> canal RESOLU a l'offset LU, drift NOMME",
            rDep.channel !== null && rDep.channel.fieldOffset === 0x90
            && rDep.drift.length > 0,
            JSON.stringify(rDep.drift));

        // (h) #419 -- LE PIEGE DU NOM. Le champ est un backing field d'auto-property ; chercher
        //     `Weapons` sans les chevrons ne resout rien.
        const sansChevrons = mutate(base, (d) => {
            const f = d[WC_KEY].fields.find((x) => x.name === WPN.WEAPONS_FIELD)!;
            f.name = "Weapons";
        });
        const wSans = WPN.resolveWeaponsChannel(makeProbe(sansChevrons));
        check("(h) champ sans chevrons -> canal REFUSE",
            wSans.channel === null
            && wSans.errors.some((e) => e.indexOf("BACKING FIELD") >= 0),
            JSON.stringify(wSans.errors));

        // (i) #419 -- `Nullable` NON INFLATE : hasValue et value tous deux a 0. Lire dans cet etat
        //     rendrait le BIT a la place de la portee : c'est exactement la faute #579-r1.
        const nullableOuvert = mutate(base, (d) => {
            const f = d[WP_KEY].fields.find((x) => x.name === "Range")!;
            f.typeKey = NULLABLE_OPEN_KEY;
        });
        const wNull = WPN.resolveWeaponsChannel(makeProbe(nullableOuvert));
        check("(i) Nullable NON INFLATE -> canal REFUSE",
            wNull.channel === null
            && wNull.errors.some((e) => e.indexOf("NULLABLE NON INFLATE") >= 0),
            JSON.stringify(wNull.errors));

        // (j) #419 -- enum de profil mal apparie.
        const wpEnumFaux = mutate(base, (d) => {
            const f = d[WP_KEY].fields.find((x) => x.name === "DamageProfileType")!;
            f.typeKey = DPT_LOOKALIKE_KEY;
        });
        const wEnum = WPN.resolveWeaponsChannel(makeProbe(wpEnumFaux));
        check("(j) enum de profil mal apparie -> canal REFUSE",
            wEnum.channel === null
            && wEnum.errors.some((e) => e.indexOf("ENUM MAL APPARIE") >= 0),
            JSON.stringify(wEnum.errors));

        // (k) #419 -- un champ de `WeaponProfile` HORS instance (48 octets) : le confondre avec un
        //     champ statique ferait lire n'importe ou.
        const horsInstance = mutate(base, (d) => {
            const f = d[WP_KEY].fields.find((x) => x.name === "Hits")!;
            f.offset = 0x100;
        });
        const wHors = WPN.resolveWeaponsChannel(makeProbe(horsInstance));
        check("(k) champ hors instance -> canal REFUSE",
            wHors.channel === null
            && wHors.errors.some((e) => e.indexOf("HORS INSTANCE") >= 0),
            JSON.stringify(wHors.errors));
    }

    // ===== ETAPE 3 : les LECTURES, sur memoire simulee =====================================
    //
    // C'est ici que se verifient les seuils qu'aucune resolution ne montre.
    console.log("");
    console.log("[3] lectures sur memoire simulee");
    {
        const d = dispositionReelle();
        const ch = RDT.resolveReceiveDamageChannel(makeProbe(d)).channel as ReceiveDamageChannel;
        const wch = WPN.resolveWeaponsChannel(makeProbe(d)).channel as WeaponsChannel;

        // --- #487-r2 : un dictionnaire a DEUX profils, plus UN slot libere -----------------
        const mem = new FakeMem();
        const COMP = 0x1000, DICT = 0x2000, ENTRIES = 0x3000;
        mem.writePtr(COMP + ch.fieldOffset, DICT);
        mem.writeS32(DICT + ch.countOff, 3);            // 3 slots occupes OU liberes
        mem.writeS32(DICT + ch.freeCountOff, 1);
        mem.writePtr(DICT + ch.entriesOff, ENTRIES);
        mem.writeS32(ENTRIES + 0x18, 8);                // longueur du tableau
        const ent = (i: number): number => ENTRIES + 0x20 + i * ch.entryStride;
        // slot 0 : Psychic (13) recu 2 fois
        mem.writeS32(ent(0) + ch.nextOff, -1);
        mem.writeS32(ent(0) + ch.keyOff, DPT_MEMBERS.Psychic);
        mem.writeS32(ent(0) + ch.valueOff, 2);
        // slot 1 : LIBERE (`next = StartOfFreeList - freeList` <= -3) -- doit etre SAUTE
        mem.writeS32(ent(1) + ch.nextOff, -3);
        mem.writeS32(ent(1) + ch.keyOff, DPT_MEMBERS.Bolter);
        mem.writeS32(ent(1) + ch.valueOff, 99);
        // slot 2 : None (-1) recu 1 fois -- une cle NEGATIVE, que « 0..N » raterait
        mem.writeS32(ent(2) + ch.nextOff, -1);
        mem.writeS32(ent(2) + ch.keyOff, DPT_MEMBERS.None);
        mem.writeS32(ent(2) + ch.valueOff, 1);

        const got = RDT.readReceiveDamageTypes(mem.ptr(COMP), ch);
        check("#487-r2 : deux profils lus, le slot LIBERE saute",
            JSON.stringify(got.profiles) === JSON.stringify({ 13: 2, "-1": 1 }),
            JSON.stringify(got));
        check("#487-r2 : freeSlotsSkipped compte le trou", got.freeSlotsSkipped === 1,
            String(got.freeSlotsSkipped));
        check("#487-r2 : freeCount publie", got.freeCount === 1, String(got.freeCount));

        // Dictionnaire VIDE : `{}` est une MESURE, pas une panne. C'est l'etat MAJORITAIRE.
        const memVide = new FakeMem();
        memVide.writePtr(COMP + ch.fieldOffset, DICT);
        memVide.writeS32(DICT + ch.countOff, 0);
        const vide = RDT.readReceiveDamageTypes(memVide.ptr(COMP), ch);
        check("#487-r2 : dict vide -> {} (MESURE), pas null",
            vide.profiles !== null && Object.keys(vide.profiles).length === 0,
            JSON.stringify(vide));

        // Dictionnaire NUL : le natif LEVE dans ce cas -> on NOMME, on ne rend pas `{}`.
        const memNul = new FakeMem();
        memNul.writePtr(COMP + ch.fieldOffset, 0);
        const nul = RDT.readReceiveDamageTypes(memNul.ptr(COMP), ch);
        check("#487-r2 : dict nul -> null + cause NOMMEE",
            nul.profiles === null && nul.error === "dictionnaire nul", JSON.stringify(nul));

        // Canal non resolu : jamais `{}`.
        const sansCanal = RDT.readReceiveDamageTypes(mem.ptr(COMP), null);
        check("#487-r2 : canal null -> profiles null, jamais {}",
            sansCanal.profiles === null && sansCanal.error === "canal non resolu");

        // --- #419 : trois armes, dont le cas-limite `Range == 1` --------------------------
        const wmem = new FakeMem();
        const WCOMP = 0x5000, LIST = 0x6000, ITEMS = 0x7000;
        const W0 = 0x8000, W1 = 0x8100, W2 = 0x8200;
        const LL = { itemsOff: 0x10, sizeOff: 0x18 };
        wmem.writePtr(WCOMP + wch.listOffset, LIST);
        wmem.writePtr(LIST + LL.itemsOff, ITEMS);
        wmem.writeS32(LIST + LL.sizeOff, 3);
        wmem.writePtr(ITEMS + 0x20 + 0 * 8, W0);
        wmem.writePtr(ITEMS + 0x20 + 1 * 8, W1);
        wmem.writePtr(ITEMS + 0x20 + 2 * 8, W2);
        // W0 : melee « evident » -- pas de Range du tout.
        wmem.writeS32(W0 + wch.typeOffset, DPT_MEMBERS.Power);
        wmem.writeS32(W0 + wch.hitsOffset, 4);
        wmem.writeU8(W0 + wch.rangeOffset + wch.rangeHasValueOff, 0);
        wmem.writeS32(W0 + wch.rangeOffset + wch.rangeValueOff, 12345);  // doit etre IGNORE
        // W1 : LE PIEGE -- Range = 1. `get_IsMelee` rend VRAI (`Range.Value < 2`). Un capteur
        //      qui lirait « Range present => ranged » se tromperait ICI, et nulle part ailleurs
        //      sur ce gameconfig (aucune arme a Range == 1 : la faute serait INVISIBLE en live).
        wmem.writeS32(W1 + wch.typeOffset, DPT_MEMBERS.Bolter);
        wmem.writeS32(W1 + wch.hitsOffset, 2);
        wmem.writeU8(W1 + wch.rangeOffset + wch.rangeHasValueOff, 1);
        wmem.writeS32(W1 + wch.rangeOffset + wch.rangeValueOff, 1);
        // W2 : ranged franc.
        wmem.writeS32(W2 + wch.typeOffset, DPT_MEMBERS.Psychic);
        wmem.writeS32(W2 + wch.hitsOffset, 3);
        wmem.writeU8(W2 + wch.rangeOffset + wch.rangeHasValueOff, 1);
        wmem.writeS32(W2 + wch.rangeOffset + wch.rangeValueOff, 4);

        const wgot = WPN.readWeapons(wmem.ptr(WCOMP), wch, LL);
        check("#419 : trois armes lues", wgot.weapons !== null && wgot.weapons.length === 3,
            JSON.stringify(wgot));
        if (wgot.weapons) {
            check("#419 : Range absent -> melee, valeur IGNOREE",
                wgot.weapons[0].isMelee && wgot.weapons[0].range === null,
                JSON.stringify(wgot.weapons[0]));
            check("#419 : Range == 1 -> MELEE (seuil `< 2`, pas `present`)",
                wgot.weapons[1].isMelee && wgot.weapons[1].range === 1,
                JSON.stringify(wgot.weapons[1]));
            check("#419 : Range == 4 -> ranged", !wgot.weapons[2].isMelee);
            check("#419 : hits lus", wgot.weapons.map((w) => w.hits).join(",") === "4,2,3");
            check("#419 : profils lus",
                wgot.weapons.map((w) => w.damageProfileType).join(",")
                === [DPT_MEMBERS.Power, DPT_MEMBERS.Bolter, DPT_MEMBERS.Psychic].join(","));
        }
        check("#419 : HasRangedWeapon(null) = true des qu'UNE arme n'est pas melee",
            wgot.hasRangedWeapon === true);

        // Une unite qui n'a QUE des armes melee : `false` est une MESURE.
        const wmem2 = new FakeMem();
        wmem2.writePtr(WCOMP + wch.listOffset, LIST);
        wmem2.writePtr(LIST + LL.itemsOff, ITEMS);
        wmem2.writeS32(LIST + LL.sizeOff, 1);
        wmem2.writePtr(ITEMS + 0x20, W0);
        wmem2.writeS32(W0 + wch.typeOffset, DPT_MEMBERS.Power);
        wmem2.writeS32(W0 + wch.hitsOffset, 4);
        wmem2.writeU8(W0 + wch.rangeOffset + wch.rangeHasValueOff, 0);
        const wonly = WPN.readWeapons(wmem2.ptr(WCOMP), wch, LL);
        check("#419 : que du melee -> hasRangedWeapon === false (MESURE)",
            wonly.hasRangedWeapon === false, JSON.stringify(wonly));

        // Layout de `List<T>` non resolu : jamais une liste plausible.
        const wnoll = WPN.readWeapons(wmem.ptr(WCOMP), wch, null);
        check("#419 : layout de List<T> non resolu -> null + cause NOMMEE",
            wnoll.weapons === null && wnoll.hasRangedWeapon === null
            && wnoll.error === "layout de List<T> non resolu", JSON.stringify(wnoll));

        // Composant absent : `null` NOMME, jamais `[]` (qui dirait « porte le composant, vide »).
        const wabs = WPN.readWeapons(null, wch, LL);
        check("#419 : composant absent -> null NOMME, jamais []",
            wabs.weapons === null && wabs.error === "WeaponsComponent absent");
    }

    console.log("");
    console.log("[10008] " + (checks - failures) + "/" + checks + " controles OK, "
        + failures + " echec(s)");
}

void main().then(() => {
    process.exit(failures === 0 ? 0 : 1);
});
