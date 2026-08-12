/** `#988` — DECODEUR de `IdunBattle.AI.BucketSystem.Bucket<T>`, sous-buckets COMPRIS.
 *
 *  ## Le trou que ce module ferme, et il est MESURE
 *
 *  Tous les lecteurs de bucket du depot lisent le SEUL champ `best` (l'action retenue), et
 *  concluent « bucket vide » quand il est nul. Or il existe une voie entiere ou ce champ N'EST
 *  JAMAIS ECRIT, et c'est celle de la face NonComparable a strategies multiples.
 *
 *  Lu en entier dans le decompile :
 *
 *      // IdunBattle.AI.BucketSystem.Bucket<T>$$AddAction(this, action, mi)
 *      if (action == null) return;
 *      if (!IsValidAction(this, action)) return;
 *      if (this-><best> == null) { this-><best> = action; return; }
 *      if (Fix64.op_GreaterThan(action-><utility>, this-><best>-><utility>))
 *          this-><best> = action;                                  // <-- ECRIT `best`
 *
 *      // IdunBattle.AI.BucketSystem.Bucket<T>$$AddActionToBucket(this, key, action, mi)
 *      if (action == null) return;
 *      sub = null;
 *      this-><subBuckets>.TryGetValue(key, out sub);               // SortedList<int, Bucket<T>>
 *      if (sub == null) { sub = new Bucket<T>(); this-><subBuckets>.Add(key, sub); }
 *      sub.AddAction(action);                    // <-- ECRIT `sub.best`, JAMAIS `this.best`
 *
 *  `IdunBattle.AI.Playbook.NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies` n'appelle
 *  QUE `AddActionToBucket`. Le bucket qu'elle rend a donc `best == null` par CONSTRUCTION, et toute
 *  son information vit dans `subBuckets`. Un lecteur qui s'arrete a `best` rend « vide » sur un
 *  bucket PLEIN — c'est le faux negatif qui a fait ecrire « buckets toutes vides » sur
 *  `1043 ThunderousAssault` alors que l'action existait.
 *
 *  A l'inverse `IdunBattle.AI.Playbook.ComparablePlaybook<T>$$EvaluateInternal` ecrit `best`
 *  directement (et `GenerateBucketWithActionForEveryEligibleTarget` passe par `AddAction`) : les
 *  deux regimes coexistent, donc on ne peut pas remplacer une lecture par l'autre — il faut LES DEUX.
 *
 *  ## Ce que le natif choisit, et pourquoi on peut le mirrorer EXACTEMENT
 *
 *      // IdunBattle.AI.BucketSystem.Bucket<T>$$IsValidAction(this, action, mi)
 *      if (action == null) return false;
 *      if (!this-><minUtility>.HasValue) return true;          // Nullable<Fix64>
 *      return Fix64.op_GreaterThanOrEqual(action-><utility>, this-><minUtility>.Value);
 *
 *      // IdunBattle.AI.BucketSystem.Bucket<T>$$ChooseAction(this, mi)
 *      if (IsValidAction(this, this-><best>)) return this-><best>;
 *      a = ChooseActionFromBuckets(this);
 *      return IsValidAction(this, a) ? a : null;
 *
 *      // IdunBattle.AI.BucketSystem.Bucket<T>$$ChooseActionFromBuckets(this, mi)
 *      foreach (kv in this-><subBuckets>)            // SortedList => ordre CROISSANT des cles
 *          sub = kv.Value;
 *          r = IsValidAction(sub, sub-><best>) ? sub-><best> : ChooseActionFromBuckets(sub);
 *          if (!IsValidAction(sub, r)) continue;     // NB: valide contre SUB, pas contre `this`
 *          if (r != null) return r;
 *      return null;
 *
 *  Ces trois corps ne lisent que des champs — aucun appel de service, aucun etat de match. Le
 *  mirror ci-dessous est donc EXACT, et il est en LECTURE PURE : on n'invoque aucun natif, ce qui
 *  evite a la fois le gel (`reference_never_hook_the_method_you_invoke`) et le risque d'un natif
 *  qui ecrirait. La cle de tri etant un `int` croissant, l'ordre d'enumeration de la `SortedList`
 *  se relit directement dans son tableau `keys`, deja trie.
 *
 *  ## Resolution
 *
 *  Aucun offset de champ n'est ecrit en dur : ils sont resolus AU RUNTIME **par le TYPE du champ**
 *  (le champ de type `SortedList\`2` est le conteneur de sous-buckets, celui de type
 *  `BucketAction\`1` est l'action retenue). Ce choix est deliberement plus robuste qu'une
 *  resolution par nom : il survit a un renommage de champ comme a un decalage d'offset, et le
 *  diagnostic publie le nom REELLEMENT trouve pour que la peremption soit visible.
 */
import {
    class_get_fields, class_get_name, cstr, field_get_name, field_get_offset, field_get_type,
    findClassAnywhere, type_get_class_or_element_class,
} from "../il2cpp/helpers.js";

/** Fix64 (Q32.32) brut -> nombre. Meme conversion que `sort-utility-trace`. */
export function fix64ToNumber(raw: Int64): number {
    try { return Number(BigInt(raw.toString())) / 4294967296; } catch { return NaN; }
}

/** Une action telle qu'elle vit dans un bucket. */
export interface DecodedAction {
    /** `BucketAction<T>` lui-meme (diagnostic / correlation). */
    ptr: string;
    /** `BucketAction<T>.<content>` — le `UnitAction*`. */
    content: string;
    /** L'utilite brute (Fix64 base 10) — exacte, sans perte de bits de poids faible. */
    utilityRaw: string;
    /** L'utilite convertie (`raw / 2^32`). */
    utility: number;
}

/** Un bucket decode, recursivement. */
export interface DecodedBucket {
    ptr: string;
    /** Le champ `best`. `null` = REELLEMENT nul (et ce n'est PAS « le bucket est vide »). */
    best: DecodedAction | null;
    /** Le seuil `Nullable<Fix64>` : `null` = `HasValue == false` (aucun seuil, tout est valide). */
    minUtility: number | null;
    minUtilityRaw: string | null;
    /** Les sous-buckets, dans l'ordre CROISSANT des cles — l'ordre d'enumeration du natif. */
    subBuckets: Array<{ key: number; bucket: DecodedBucket }>;
    /** Profondeur atteinte ; `true` si la recursion a ete coupee (jamais silencieusement). */
    truncated?: boolean;
}

interface BucketLayout {
    bestOff: number; bestField: string;
    subOff: number; subField: string;
    minOff: number; minField: string;
    slKeysOff: number; slValuesOff: number; slSizeOff: number;
}

/** `BucketAction<T>` : `content` puis `utility` (Fix64). Resolus par TYPE comme le reste. */
interface ActionLayout { contentOff: number; utilityOff: number }

let layout: BucketLayout | null = null;
let actionLayout: ActionLayout | null = null;
let resolveError: string | null = null;

/** `FIELD_ATTRIBUTE_STATIC` — le bit qui distingue un champ statique d'un champ d'instance. */
const FIELD_ATTRIBUTE_STATIC = 0x0010;

const _fieldGetFlags = (() => {
    try {
        const mod = Process.findModuleByName("GameAssembly.dll");
        const p = mod ? mod.findExportByName("il2cpp_field_get_flags") : null;
        return p ? new NativeFunction(p, "uint32", ["pointer"]) : null;
    } catch { return null; }
})();

/** Enumere (nom, offset, nom-de-classe-du-type) des champs d'INSTANCE d'une classe.
 *
 *  ⚠ Les champs STATIQUES sont ECARTES. Leur offset ne se compte pas depuis le debut de l'objet :
 *  le lire comme un champ d'instance produirait une adresse arbitraire, donc un decodage faux SANS
 *  erreur. Si le drapeau n'est pas lisible sur ce build, on les garde plutot que de tout jeter --
 *  la resolution PAR TYPE qui suit reste le vrai discriminant. */
function fieldsOf(klass: NativePointer): Array<{
    name: string; off: number; typeName: string;
}> {
    const out: Array<{ name: string; off: number; typeName: string }> = [];
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        if (_fieldGetFlags) {
            try {
                if (((_fieldGetFlags(f) as number) & FIELD_ATTRIBUTE_STATIC) !== 0) continue;
            } catch { /* drapeau illisible : on garde le champ */ }
        }
        let typeName = "?";
        try {
            const t = field_get_type(f) as NativePointer;
            const k = type_get_class_or_element_class(t) as NativePointer;
            if (!k.isNull()) typeName = cstr(class_get_name(k) as NativePointer);
        } catch { /* typeName reste "?" */ }
        out.push({
            name: cstr(field_get_name(f) as NativePointer),
            off: field_get_offset(f) as number,
            typeName,
        });
    }
    return out;
}

/** Resout le layout une fois. Rend `null` en POSANT `resolveError` : un decodeur qui ne sait pas
 *  lire doit le DIRE, jamais rendre un bucket vide qui se lirait comme une mesure. */
function ensureLayout(): BucketLayout | null {
    if (layout) return layout;
    if (resolveError) return null;
    const bucketCls = findClassAnywhere("IdunBattle.AI.BucketSystem", "Bucket`1");
    if (!bucketCls) { resolveError = "classe `Bucket`1` introuvable"; return null; }
    const bf = fieldsOf(bucketCls);
    const best = bf.find((x) => x.typeName.indexOf("BucketAction") === 0);
    const sub = bf.find((x) => x.typeName.indexOf("SortedList") === 0);
    const min = bf.find((x) => x.typeName.indexOf("Nullable") === 0);
    if (!best || !sub) {
        resolveError = "champs de `Bucket`1` non identifies par TYPE — vus: "
            + bf.map((x) => x.name + ":" + x.typeName + "@0x" + x.off.toString(16)).join(", ");
        return null;
    }
    const slCls = findClassAnywhere("System.Collections.Generic", "SortedList`2");
    if (!slCls) { resolveError = "classe `SortedList`2` introuvable"; return null; }
    const sf = fieldsOf(slCls);
    const keys = sf.find((x) => x.name === "keys");
    const values = sf.find((x) => x.name === "values");
    const size = sf.find((x) => x.name === "_size");
    if (!keys || !values || !size) {
        resolveError = "champs de `SortedList`2` non resolus — vus: "
            + sf.map((x) => x.name + "@0x" + x.off.toString(16)).join(", ");
        return null;
    }
    layout = {
        bestOff: best.off, bestField: best.name,
        subOff: sub.off, subField: sub.name,
        minOff: min ? min.off : -1, minField: min ? min.name : "<absent>",
        slKeysOff: keys.off, slValuesOff: values.off, slSizeOff: size.off,
    };
    return layout;
}

function ensureActionLayout(): ActionLayout | null {
    if (actionLayout) return actionLayout;
    const cls = findClassAnywhere("IdunBattle.AI.BucketSystem", "BucketAction`1");
    if (!cls) return null;
    const f = fieldsOf(cls);
    // Le champ Fix64 est l'utilite ; l'autre champ d'instance est le contenu.
    const util = f.find((x) => x.typeName === "Fix64");
    const content = f.find((x) => x !== util);
    if (!util || !content) return null;
    actionLayout = { contentOff: content.off, utilityOff: util.off };
    return actionLayout;
}

/** Le layout resolu, pour le diagnostic d'un appelant. Jamais un chemin de decision. */
export function bucketLayoutReport(): unknown {
    const l = ensureLayout();
    const a = ensureActionLayout();
    return {
        resolved: !!l,
        error: resolveError,
        bucket: l ? {
            best: l.bestField + "@0x" + l.bestOff.toString(16),
            subBuckets: l.subField + "@0x" + l.subOff.toString(16),
            minUtility: l.minField + (l.minOff >= 0 ? "@0x" + l.minOff.toString(16) : ""),
        } : null,
        sortedList: l ? {
            keys: "0x" + l.slKeysOff.toString(16),
            values: "0x" + l.slValuesOff.toString(16),
            _size: "0x" + l.slSizeOff.toString(16),
        } : null,
        bucketAction: a ? {
            content: "0x" + a.contentOff.toString(16),
            utility: "0x" + a.utilityOff.toString(16),
        } : null,
    };
}

function decodeAction(p: NativePointer): DecodedAction | null {
    if (p.isNull()) return null;
    const a = ensureActionLayout();
    if (!a) return null;
    const raw = p.add(a.utilityOff).readS64();
    return {
        ptr: p.toString(),
        content: p.add(a.contentOff).readPointer().toString(),
        utilityRaw: raw.toString(),
        utility: fix64ToNumber(raw),
    };
}

const MAX_DEPTH = 8;
const MAX_SUBS = 64;

/** Decode un `Bucket<T>` et TOUS ses sous-buckets. Lecture pure. */
export function decodeBucket(
    bucketPtr: NativePointer, depth = 0,
): DecodedBucket | null {
    const l = ensureLayout();
    if (!l || bucketPtr.isNull()) return null;
    const out: DecodedBucket = {
        ptr: bucketPtr.toString(),
        best: null, minUtility: null, minUtilityRaw: null, subBuckets: [],
    };
    try {
        out.best = decodeAction(bucketPtr.add(l.bestOff).readPointer());
    } catch { /* best reste null */ }
    // `Nullable<Fix64>` : la valeur occupe les 8 premiers octets, `HasValue` le 9e.
    if (l.minOff >= 0) {
        try {
            if (bucketPtr.add(l.minOff + 8).readU8() !== 0) {
                const raw = bucketPtr.add(l.minOff).readS64();
                out.minUtilityRaw = raw.toString();
                out.minUtility = fix64ToNumber(raw);
            }
        } catch { /* pas de seuil lisible */ }
    }
    if (depth >= MAX_DEPTH) { out.truncated = true; return out; }
    try {
        const sl = bucketPtr.add(l.subOff).readPointer();
        if (sl.isNull()) return out;
        const size = sl.add(l.slSizeOff).readS32();
        if (size <= 0) return out;
        const keys = sl.add(l.slKeysOff).readPointer();
        const values = sl.add(l.slValuesOff).readPointer();
        if (keys.isNull() || values.isNull()) return out;
        const n = Math.min(size, MAX_SUBS);
        if (n < size) out.truncated = true;
        for (let i = 0; i < n; i++) {
            // Tableaux manages : en-tete d'objet puis les elements a +0x20.
            const key = keys.add(0x20 + i * 4).readS32();
            const sub = values.add(0x20 + i * Process.pointerSize).readPointer();
            const decoded = decodeBucket(sub, depth + 1);
            if (decoded) out.subBuckets.push({ key, bucket: decoded });
        }
    } catch { /* sous-buckets illisibles : on rend ce qu'on a, jamais un faux vide */ }
    return out;
}

/** Mirror EXACT de `Bucket<T>$$IsValidAction`. */
function isValidAction(b: DecodedBucket, a: DecodedAction | null): boolean {
    if (!a) return false;
    if (b.minUtilityRaw === null) return true;
    return BigInt(a.utilityRaw) >= BigInt(b.minUtilityRaw);
}

/** Mirror EXACT de `Bucket<T>$$ChooseActionFromBuckets`. */
function chooseFromSubBuckets(b: DecodedBucket): DecodedAction | null {
    for (const { bucket: sub } of b.subBuckets) {
        const r = isValidAction(sub, sub.best) ? sub.best : chooseFromSubBuckets(sub);
        if (!isValidAction(sub, r)) continue;
        if (r) return r;
    }
    return null;
}

/** Mirror EXACT de `Bucket<T>$$ChooseAction` — l'action que le natif RETIENDRAIT.
 *
 *  ⚠ C'est un mirror en LECTURE, pas une invocation : il ne peut donc pas diverger du natif par
 *  effet de bord, mais il vaut ce que vaut la lecture des trois corps cites en tete. */
export function chooseAction(b: DecodedBucket): DecodedAction | null {
    if (isValidAction(b, b.best)) return b.best;
    const a = chooseFromSubBuckets(b);
    return isValidAction(b, a) ? a : null;
}

/** Compte total d'actions retenues dans l'arbre (racine + sous-buckets). Un `0` ici est une vraie
 *  mesure de vacuite — contrairement a « `best` est nul ». */
export function countActions(b: DecodedBucket): number {
    let n = b.best ? 1 : 0;
    for (const s of b.subBuckets) n += countActions(s.bucket);
    return n;
}
