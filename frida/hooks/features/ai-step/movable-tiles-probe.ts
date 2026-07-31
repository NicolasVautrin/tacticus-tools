/** #370 (résidu `#361-r2`) — capteur du MAILLON INTERNE de `GetTileToMoveTo`.
 *
 *  ⚠ INERTE tant que le bundle n'est pas rebuildé + réinjecté (geste orchestrateur).
 *
 *  # La question, BINAIRE
 *
 *  `#386` a refermé la localisation : les batchs 3/4 de
 *  `IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` sont absents parce que
 *  les deux `ComparablePlaybook<T>$$GenerateAttackPredictions` rendent VIDE, gate OUVERTE
 *  (`get_WillBeKill -> TRUE`, capteur `playbook-gate-probe.ts`), composition `AdjacentUnits` +
 *  `op_Subtraction` + `SelectUniqueUnits(ctx,3)` mesurée VIVANTE 3/3. Reste l'`origin` :
 *  `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo`, qui rend
 *  la bonne tuile dans le contexte de `RammingSpeedAbility$$GetDynamicInvalidTargetReason` (cast
 *  réel, MATCH 2/2) et VIDE dans celui du playbook.
 *
 *  **Lequel des maillons de cet arbre rend vide ?**
 *
 *  # L'arbre, relu au décompilé (`GetTileToMoveTo`, verbatim)
 *
 *  ```
 *  range  = DSLFormulas$$Direct(AbilityConfiguration$$GetNumberConstant(config, 0x16))
 *  pool   = DSLSelectors$$MovableTilesInRange(Caster@0x48, CasterTile@0x50, range, 0, 0)
 *  pool   = TargetsSelector$$op_BitwiseAnd(pool, DSLSelectors$$CanAddUnit(AdjacentTiles(Target@0x60)))
 *  pool   = DSLSelectors$$SortTilesByUtility(pool, Caster@0x48, UtilityBucket{7, 0x36}, null)
 *  return   DSLSelectors$$First(pool, 1, 0)
 *  ```
 *
 *  # Pourquoi CE point d'ancrage — argumenté sur le corps, pas sur le nom
 *
 *  `IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select` est le SEUL nœud de la
 *  chaîne haute dont un retour VIDE est SILENCIEUX, et son corps en porte **trois** issues
 *  distinctes (lues sur le décompilé, dans cet ordre) :
 *
 *   1. `entity = unitSelector.<slot 7>(ctx)` ; `if (entity == null)` → **rend la `List` VIDE**
 *      qui vient d'être allouée. Aucun thrower.
 *   2. `if (unitTileSelector != null)` : `fromTile = unitTileSelector.<slot 0xc>(ctx)` (=
 *      `IdunBattle.DSL.TargetsSelector$$SelectTile`, qui rend `0` quand son énumération ne
 *      produit ni tuile ni unité placée) ; `if (fromTile == null)` → **rend la MÊME `List` VIDE**.
 *   3. sinon `IBattleQuery.GetMovableTilesInRange(entity, fromTile, ignoreFlags, options)` —
 *      dont le retour peut lui aussi être vide.
 *
 *  Partout ailleurs dans cet arbre, un maillon absent tombe dans le thrower (`FUN_1801f51f0`).
 *  Un seul point d'ancrage sépare donc les trois hypothèses restantes — **et un QUATRIÈME état
 *  s'ajoute gratuitement** : `0 appel` signifie que l'arbre n'est PAS ÉVALUÉ du tout, et déplace
 *  la cause en AMONT (`First` / `SortTilesByUtility` / `op_BitwiseAnd` / `AdjacentTiles`).
 *
 *  ⚠ `entity` et `fromTile` sont des LOCALES : `Interceptor.attach` sur `Select` seul voit le
 *  `this`, le contexte et le retour — **pas** les deux valeurs intermédiaires. C'est pourquoi ce
 *  capteur arme AUSSI les deux sous-sélecteurs, qui sont NOMMÉS et dont les corps sont courts :
 *
 *   * `IdunBattle.Entities.Selectors.CasterSelector$$Select` — corps entier :
 *     `if (ctx+0x08 == 0) return new List<T>();  l = new List<T>(1); l.Add(ctx+0x08); return l;`
 *     ⇒ sa taille de retour EST le maillon 1.
 *   * `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` — corps entier :
 *     `tiles = ctx+0x48; if (tiles == null) tiles = ToList(ctx+0x40);
 *      if (tiles == null) tiles = EntityExtensions$$GetTiles(ctx+0x08, state); return new List<T>(tiles);`
 *     ⇒ sa taille de retour EST le maillon 2, et la branche prise se lit sur `+0x48` / `+0x40`.
 *     C'est LE seul nœud de l'arbre qui CHANGE de branche entre les deux contextes (le gate laisse
 *     `+0x48` nul, le playbook le renseigne).
 *
 *  Ces deux classes sont ce que `GetTileToMoveTo` passe (`factory+0x48` / `factory+0x50`), mais le
 *  capteur ne le SUPPOSE pas : il publie le nom de classe EFFECTIF des trois champs du
 *  `MovableTilesInRangeSelector`, et le décodeur refuse de conclure si la structure diffère.
 *
 *  # #374 — le retour se lit en DEUX formes, et une seule était décodée
 *
 *  Premier tir armé (session 3) : **4 appels sur chacun des deux bras**, et `[retour-illisible]`
 *  partout — `classes=['OrderedSet`1' ×4]` — alors que le contrôle positif émettait ses batchs
 *  (bras A : 4 events == 4 attendus ; bras B : 5 == 5). Le capteur ne se trompait pas sur le
 *  fond : il ne savait pas lire ce type. Cause lue au décompilé, pas devinée — les deux
 *  early-returns rendent la `List`1` VIDE que le corps vient d'allouer, tandis que le retour de
 *  `IBattleQuery.GetMovableTilesInRange` est un `idun.shared.collections.OrderedSet`1`, qui
 *  **DÉRIVE de `System.Collections.Generic.List`1`** (`OrderedSet<T>$$.ctor` appelle
 *  `List<T>$$.ctor` sur le même `this` et n'ajoute que son `HashSet` à `+0x28` ;
 *  `OrderedSet<T>$$get_Item` délègue à `List<T>$$get_Item`). Détail dans `readRefList`.
 *
 *  La classe du retour est donc elle-même DISCRIMINANTE : `List`1` ⇒ early-return silencieux,
 *  `OrderedSet`1` ⇒ la requête a répondu. Le capteur la publie, avec la forme de stockage
 *  retenue et le chemin d'héritage qui y mène.
 *
 *  # Discipline
 *
 *  Hooks **armés à la demande, détachés en `finally`**, **filtrés sur le thread appelant**, nombre
 *  d'entrées **borné**. Aucun de ces trois symboles n'est un hot path UI, mais `CasterSelector` /
 *  `CasterTileSelector` sont évalués par TOUT arbre DSL : jamais de hook permanent.
 *
 *  Résolution par NOM (aucune RVA) : `findClassAnywhere` + `findMethod`. Chaque maillon a son
 *  PROPRE tri-état — un maillon non résolu rend une ERREUR NOMMÉE, jamais un zéro qui se lirait
 *  comme « pas d'appel ». */
import {
    class_get_element_class, class_get_fields, class_get_name, class_get_parent,
    class_instance_size, class_is_valuetype, field_get_name, field_get_offset,
    findClassAnywhere, findMethod, s,
} from "../../il2cpp/helpers.js";
import { classNameAt } from "./playbook-predict.js";
import { ARRAY_FIRST, LIST_ITEMS, LIST_SIZE, readTileCoord } from "./internals.js";

/** Offsets, DANS LA STRUCT DE CONTEXTE, des slots que ce capteur publie.
 *
 *  `0x08`, `0x40` et `0x48` sont lus PAR MOI sur les corps de `CasterSelector$$Select` et
 *  `CasterTileSelector$$Select` (cf. l'en-tête) — ce sont eux que le décodeur exploite.
 *  Les quatre autres viennent de la table de `case-361` §7 (`ComparablePlaybook<T>$$Generate
 *  AttackPredictions`) et ne servent qu'au diagnostic : le capteur les publie BRUTS, il n'en
 *  déduit rien. */
const CTX_SLOTS: Array<[string, number]> = [
    ["caster@0x08", 0x08],       // `CasterSelector$$Select` — LU
    ["target@0x10", 0x10],       // `TargetSelector$$Select` — table #365
    ["owner@0x18", 0x18],        // `OwnerSelector$$Select` — table #365
    ["targetTiles@0x38", 0x38],  // `TargetTilesSelector$$Select` — table #365
    ["casterMainTile@0x40", 0x40],  // `CasterTileSelector` repli 2 — LU
    ["casterPosition@0x48", 0x48],  // `CasterTileSelector` voie 1 — LU
    ["slot@0x50", 0x50],         // diagnostic
    ["targetOrigin@0x60", 0x60], // `Target@0x60` de `GetTileToMoveTo` — table #365
];

/** Un pointeur du contexte ou d'un champ, décodé sans supposer son type. */
export interface PtrView {
    ptr: string;
    /** Nom de classe IL2CPP, ou `null` si le pointeur est nul / non déréférençable. */
    cls: string | null;
    /** `(col,row)` si le pointeur porte une `PositionComponent` (donc : c'est une tuile). */
    col?: number;
    row?: number;
}

/** Un champ d'instance lu par son NOM RUNTIME — immunisé à un renommage inter-build. */
export interface FieldView extends PtrView {
    name: string;
    off: number;
    /** Le même emplacement lu en octet : les deux booléens du ctor
     *  (`ignoreFlags`, `ignoreUnitsOnTiles`) ne sont pas des pointeurs. */
    u8: number;
}

/** Un appel de `MovableTilesInRangeSelector$$Select` observé pendant la fenêtre armée. */
export interface MovableTilesCall {
    /** Numéro de séquence GLOBAL à la fenêtre : corrèle cet appel aux appels des
     *  sous-sélecteurs, qui surviennent entre `seqEnter` et `seqLeave`. */
    seqEnter: number;
    seqLeave: number;
    thisPtr: string;
    /** Tous les champs d'instance, par leur nom runtime (`unitSelector`, `unitTileSelector`,
     *  `overrideRange`, `ignoreFlags`, … quels que soient leurs vrais noms). */
    fields: FieldView[] | null;
    fieldsError?: string;
    ctx: Record<string, PtrView>;
    /** Nombre d'éléments rendus. `-1` = retour non décodable — `returnedError` dit POURQUOI. */
    returnedCount: number;
    returnedClass: string | null;
    /** Forme de stockage retenue (`"List`1"` / `"array"`), et le chemin d'héritage qui y mène.
     *  Sur le succès de la requête, on lit `OrderedSet`1 -> List`1` : c'est LA distinction
     *  entre « la requête a répondu » et « early-return sur une `List` vide ». */
    returnedStorage: string | null;
    returnedVia: string;
    /** Classe du premier élément non nul — dit pourquoi un `count > 0` peut rendre 0 tuile. */
    returnedElementClass: string | null;
    returnedError?: string;
    /** Les premières tuiles rendues (bornées) — pour lire le pool quand il n'est PAS vide. */
    returnedTiles: Array<{ col: number; row: number }>;
}

/** Un appel d'un des deux sous-sélecteurs (`CasterSelector` / `CasterTileSelector`). */
export interface SubSelectorCall {
    seq: number;
    thisPtr: string;
    ctx: Record<string, PtrView>;
    returnedCount: number;
    returnedClass: string | null;
    returnedStorage: string | null;
    returnedError?: string;
}

/** Tri-état PAR MAILLON : `null` = capteur NON ARMÉ (le maillon n'a pas résolu, `*Error` le
 *  nomme) ; `[]` = ARMÉ et AUCUN appel — ce qui est un verdict en soi. */
export interface MovableTilesProbe {
    nodes: MovableTilesCall[] | null;
    nodesError?: string;
    casterCalls: SubSelectorCall[] | null;
    casterError?: string;
    casterTileCalls: SubSelectorCall[] | null;
    casterTileError?: string;
    /** Appels vus sur un AUTRE thread et volontairement écartés (tous maillons confondus). */
    otherThreadCalls: number;
    /** Borne atteinte : au-delà on ne perd que la queue, jamais le début. */
    truncated: boolean;
}

const MAX_CALLS = 64;
const MAX_TILES = 16;

function viewPtr(p: NativePointer): PtrView {
    const out: PtrView = { ptr: p.toString(), cls: null };
    if (p.isNull()) return out;
    try { out.cls = classNameAt(p); } catch { /* pointeur non déréférençable */ }
    if (out.cls !== null) {
        try {
            const c = readTileCoord(p);
            if (c.col >= 0 && c.row >= 0) { out.col = c.col; out.row = c.row; }
        } catch { /* pas une tuile */ }
    }
    return out;
}

/** Lit les slots du contexte. `ctx` est le POINTEUR vers la struct passée par valeur (l'ABI
 *  x64 passe par adresse tout struct > 8 octets ; le natif en fait sa propre copie). */
function readCtx(ctx: NativePointer): Record<string, PtrView> {
    const out: Record<string, PtrView> = {};
    if (ctx.isNull()) return out;
    for (const [name, off] of CTX_SLOTS) {
        try { out[name] = viewPtr(ctx.add(off).readPointer()); }
        catch { out[name] = { ptr: "<illisible>", cls: null }; }
    }
    return out;
}

/** Énumère les champs d'instance par leur NOM RUNTIME. Aucun offset de ce capteur n'est écrit
 *  en dur : les trois sélecteurs et les deux booléens du `MovableTilesInRangeSelector` sont
 *  retrouvés par les métadonnées IL2CPP, pas par la lecture du ctor. */
function readFields(obj: NativePointer): { fields: FieldView[] | null; error?: string } {
    if (obj.isNull()) return { fields: null, error: "instance nulle" };
    let klass: NativePointer;
    try { klass = obj.readPointer(); } catch { return { fields: null, error: "klass illisible" }; }
    if (klass.isNull()) return { fields: null, error: "klass nulle" };
    let size = 0x40;
    try { if (class_instance_size) size = class_instance_size(klass) as number; } catch { /* */ }
    const out: FieldView[] = [];
    try {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
            const name = s(field_get_name(f) as NativePointer);
            const off = field_get_offset(f) as number;
            // Un champ STATIQUE porte un offset hors instance : on ne le lit pas.
            if (off <= 0 || off + 1 > size) continue;
            const row: FieldView = { name, off, ptr: "0x0", cls: null, u8: 0 };
            try { row.u8 = obj.add(off).readU8(); } catch { /* */ }
            if (off + 8 <= size) {
                try {
                    const p = obj.add(off).readPointer();
                    const v = viewPtr(p);
                    row.ptr = v.ptr; row.cls = v.cls;
                    if (v.col !== undefined) { row.col = v.col; row.row = v.row; }
                } catch { /* */ }
            }
            out.push(row);
        }
    } catch (e) { return { fields: out.length > 0 ? out : null, error: (e as Error).message }; }
    return { fields: out };
}

/** Décode ce que rend un `Select` de la chaîne — et le natif en rend DEUX formes distinctes.
 *
 *  # Ce que `MovableTilesInRangeSelector$$Select` rend VRAIMENT, lu au décompilé
 *
 *  Le corps alloue d'abord sa liste d'échec, puis la REMPLACE par le retour de la requête :
 *
 *  ```
 *  ret = new System.Collections.Generic.List<T>(…)            // les DEUX early-returns
 *  entity = unitSelector.<slot 7>(ctx);      if (entity == null)   return ret;   // List VIDE
 *  fromTile = unitTileSelector.<slot 0xc>(ctx); if (fromTile == 0) return ret;   // List VIDE
 *  ret = battleQuery.<slot 0xc>(entity, fromTile, ignoreFlags, options);         // OrderedSet
 *  return ret;
 *  ```
 *
 *  ⇒ Les deux issues silencieuses rendent une **`List`1`**, l'issue « la requête a répondu »
 *  rend ce que rend `IBattleQuery.GetMovableTilesInRange` : un
 *  **`idun.shared.collections.OrderedSet`1`**. C'est cette seconde forme que le décodeur de
 *  #370 ne savait pas lire — il rendait `-1` (`[retour-illisible]`) sur les QUATRE appels,
 *  alors que le contrôle positif prouvait les batchs présents.
 *
 *  # Pourquoi le MÊME décodage vaut pour les deux — établi sur le binaire, pas supposé
 *
 *  `idun.shared.collections.OrderedSet<T>` **DÉRIVE** de `System.Collections.Generic.List<T>`
 *  (`data/symbols/<build>/frida/classes.tsv` : parent = `System.Collections.Generic.List`1`),
 *  et son corps le confirme deux fois :
 *
 *   * `OrderedSet<T>$$.ctor` appelle `List<T>$$.ctor` **sur le même `this`**, puis n'ajoute
 *     QUE son `HashSet<T>` propre à `this+0x28` — le stockage ordonné est celui de la base ;
 *   * `OrderedSet<T>$$get_Item` **délègue** à `List<T>$$get_Item(this, index, …)`.
 *
 *  Et `List<T>$$get_Item` donne le layout VERBATIM : borne `_size` = `*(uint*)(this+0x18)`,
 *  tableau `_items` = `*(this+0x10)`, élément à `items + 0x20 + element_size * i`.
 *  (Même lecture que `internals.extractTiles`, qui décode déjà l'`IOrderedSet<IEntity>` de
 *  `MovementQuery$$GetMovableTilesFor` pour le RPC `aiMovableTiles` — confrontée live.)
 *
 *  La reconnaissance se fait donc par la **CHAÎNE D'HÉRITAGE IL2CPP**, jamais par une liste
 *  de noms en dur : toute sous-classe de `List`1` se décode pareil, et ce qui n'en est pas
 *  une reste une ERREUR NOMMÉE.
 *
 *  # Le stride n'est pas supposé
 *
 *  `element_size` vaut `8` pour une référence mais la TAILLE DE LA STRUCT pour un type valeur.
 *  Un `8` écrit en dur rendrait alors des coordonnées plausibles et fausses — exactement le
 *  garbage que ce capteur existe pour ne pas produire. La classe d'élément du tableau est donc
 *  interrogée (`class_get_element_class` + `class_is_valuetype`) et un élément VALEUR fait
 *  répondre `-1` + une raison nommée.
 *
 *  `count = -1` ⇒ forme non décodable : c'est une ERREUR, pas un zéro. */
interface RefListView {
    count: number;
    cls: string | null;
    /** Forme de stockage RETENUE : `"List`1"` (directement ou par héritage), `"array"`, ou
     *  `null` quand rien n'a pu être décodé. Publié pour que le lecteur sache CE QUI a été lu. */
    storage: string | null;
    /** Chaîne des parents jusqu'à la forme reconnue (`"OrderedSet`1 -> List`1"`) — vide si la
     *  classe est elle-même la forme. Rend le verdict auditable sans relire le binaire. */
    via: string;
    tiles: Array<{ col: number; row: number }>;
    /** Classe du premier élément non nul — dit pourquoi `count > 0` peut rendre 0 tuile. */
    elementClass: string | null;
    /** Raison NOMMÉE d'un `count = -1`. Un `-1` muet se relirait comme un bug du capteur. */
    error?: string;
}

/** Remonte la chaîne d'héritage IL2CPP jusqu'à `List`1`. Rend le chemin parcouru, ou `null`
 *  si la classe n'en dérive pas. Bornée : une chaîne circulaire ne doit pas figer le jeu. */
function listAncestry(klass: NativePointer): string[] | null {
    const path: string[] = [];
    let k = klass;
    for (let depth = 0; depth < 16 && !k.isNull(); depth++) {
        let name: string;
        try { name = s(class_get_name(k) as NativePointer); } catch { return null; }
        path.push(name);
        if (name === "List`1") return path;
        try { k = class_get_parent(k) as NativePointer; } catch { return null; }
    }
    return null;
}

function readRefList(list: NativePointer): RefListView {
    const tiles: Array<{ col: number; row: number }> = [];
    const out: RefListView = {
        count: -1, cls: null, storage: null, via: "", tiles, elementClass: null,
    };
    if (list.isNull()) { out.error = "retour NUL"; return out; }
    let klass: NativePointer;
    try { klass = list.readPointer(); } catch { out.error = "klass illisible"; return out; }
    if (klass.isNull()) { out.error = "klass nulle"; return out; }
    out.cls = classNameAt(list);
    try {
        //  `items` = le TABLEAU managé qui porte les éléments ; `count` = le nombre d'éléments
        //  utiles. Pour un tableau nu, les deux sont le même objet (`max_length` @+0x18).
        let items: NativePointer;
        let count: number;
        const anc = listAncestry(klass);
        if (anc !== null) {
            out.storage = "List`1";
            out.via = anc.length > 1 ? anc.join(" -> ") : "";
            items = list.add(LIST_ITEMS).readPointer();
            count = list.add(LIST_SIZE).readS32();
        } else if (out.cls !== null && out.cls.endsWith("[]")) {
            out.storage = "array";
            items = list;
            count = list.add(LIST_SIZE).readS32();
        } else {
            out.error = "classe `" + out.cls + "` : ni tableau, ni derivee de `List`1`";
            return out;
        }
        if (count < 0) {
            out.error = "compte NEGATIF (" + count + ") sur `" + out.storage + "`";
            return out;
        }
        out.count = count;
        if (items.isNull() || count === 0) return out;
        //  Stride : mirror de `List<T>$$get_Item` (`items + 0x20 + element_size * i`). On ne
        //  sait lire que des références — un élément VALEUR fait répondre « je ne sais pas ».
        if (class_get_element_class !== null && class_is_valuetype !== null) {
            let elem: NativePointer | null = null;
            try { elem = class_get_element_class(items.readPointer()) as NativePointer; }
            catch { elem = null; }
            if (elem !== null && !elem.isNull()
                && (class_is_valuetype(elem) as number) !== 0) {
                let en = "?";
                try { en = s(class_get_name(elem) as NativePointer); } catch { /* */ }
                out.count = -1;
                out.error = "elements de type VALEUR (`" + en + "`) : stride inconnu, refus de"
                    + " decoder plutot que rendre des coordonnees plausibles";
                return out;
            }
        }
        for (let i = 0; i < Math.min(count, MAX_TILES); i++) {
            const e = items.add(ARRAY_FIRST + i * Process.pointerSize).readPointer();
            if (e.isNull()) continue;
            if (out.elementClass === null) out.elementClass = classNameAt(e);
            const c = readTileCoord(e);
            if (c.col >= 0 && c.row >= 0) tiles.push({ col: c.col, row: c.row });
        }
        return out;
    } catch (e) {
        out.count = -1;
        out.error = "lecture: " + (e as Error).message;
        return out;
    }
}

/** Exécute `fn` avec les trois maillons armés. Détache TOUJOURS (finally + `Interceptor.flush`),
 *  même si `fn` lève : ces sélecteurs sont évalués par tout arbre DSL. */
export function withMovableTilesProbe<T>(fn: () => T): { result: T; probe: MovableTilesProbe } {
    const probe: MovableTilesProbe = {
        nodes: null, casterCalls: null, casterTileCalls: null,
        otherThreadCalls: 0, truncated: false,
    };
    const tid = Process.getCurrentThreadId();
    const listeners: InvocationListener[] = [];
    let seq = 0;

    /** Arme un sous-sélecteur (`CasterSelector` / `CasterTileSelector`). Rend le tableau
     *  d'appels (armé) ou `null` + l'erreur NOMMÉE. */
    const armSub = (
        cls: string,
    ): { calls: SubSelectorCall[] | null; error?: string } => {
        const klass = findClassAnywhere("IdunBattle.Entities.Selectors", cls);
        if (klass === null) {
            return { calls: null,
                error: "classe `IdunBattle.Entities.Selectors." + cls + "` non résolue" };
        }
        const mi = findMethod(klass, "Select");
        if (mi === null) {
            return { calls: null, error: "`" + cls + "::Select` non résolue sur la classe" };
        }
        const calls: SubSelectorCall[] = [];
        let pendingCtx: NativePointer | null = null;
        let pendingSeq = 0;
        let pendingThis: NativePointer | null = null;
        listeners.push(Interceptor.attach(mi.ptr, {
            onEnter(this: InvocationContext, args) {
                if (this.threadId !== tid) { pendingCtx = null; probe.otherThreadCalls++; return; }
                pendingCtx = args[1]; pendingThis = args[0]; pendingSeq = seq++;
            },
            onLeave(this: InvocationContext, retval) {
                if (this.threadId !== tid || pendingCtx === null) return;
                const ctx = pendingCtx; const self = pendingThis as NativePointer;
                pendingCtx = null;
                if (calls.length >= MAX_CALLS) { probe.truncated = true; return; }
                const ret = readRefList(retval);
                const sub: SubSelectorCall = {
                    seq: pendingSeq, thisPtr: self.toString(), ctx: readCtx(ctx),
                    returnedCount: ret.count, returnedClass: ret.cls,
                    returnedStorage: ret.storage,
                };
                if (ret.error !== undefined) sub.returnedError = ret.error;
                calls.push(sub);
            },
        }));
        return { calls };
    };

    // --- maillon PRINCIPAL ---
    const nodeKlass = findClassAnywhere(
        "IdunBattle.Entities.Selectors", "MovableTilesInRangeSelector");
    if (nodeKlass === null) {
        probe.nodesError = "classe `IdunBattle.Entities.Selectors.MovableTilesInRangeSelector`"
            + " non résolue";
    } else {
        const mi = findMethod(nodeKlass, "Select");
        if (mi === null) {
            probe.nodesError = "`MovableTilesInRangeSelector::Select` non résolue sur la classe";
        } else {
            const nodes: MovableTilesCall[] = [];
            probe.nodes = nodes;
            let pendingCtx: NativePointer | null = null;
            let pendingThis: NativePointer | null = null;
            let pendingSeq = 0;
            listeners.push(Interceptor.attach(mi.ptr, {
                onEnter(this: InvocationContext, args) {
                    if (this.threadId !== tid) {
                        pendingCtx = null; probe.otherThreadCalls++; return;
                    }
                    pendingCtx = args[1]; pendingThis = args[0]; pendingSeq = seq++;
                },
                onLeave(this: InvocationContext, retval) {
                    if (this.threadId !== tid || pendingCtx === null) return;
                    const ctx = pendingCtx; const self = pendingThis as NativePointer;
                    pendingCtx = null;
                    if (nodes.length >= MAX_CALLS) { probe.truncated = true; return; }
                    const ret = readRefList(retval);
                    const f = readFields(self);
                    const row: MovableTilesCall = {
                        seqEnter: pendingSeq, seqLeave: seq++,
                        thisPtr: self.toString(), fields: f.fields, ctx: readCtx(ctx),
                        returnedCount: ret.count, returnedClass: ret.cls,
                        returnedStorage: ret.storage, returnedVia: ret.via,
                        returnedElementClass: ret.elementClass,
                        returnedTiles: ret.tiles,
                    };
                    if (ret.error !== undefined) row.returnedError = ret.error;
                    if (f.error !== undefined) row.fieldsError = f.error;
                    nodes.push(row);
                },
            }));
        }
    }

    // --- sous-maillons : chacun son tri-état ---
    const caster = armSub("CasterSelector");
    probe.casterCalls = caster.calls;
    if (caster.error !== undefined) probe.casterError = caster.error;
    const casterTile = armSub("CasterTileSelector");
    probe.casterTileCalls = casterTile.calls;
    if (casterTile.error !== undefined) probe.casterTileError = casterTile.error;

    try {
        return { result: fn(), probe };
    } finally {
        for (const l of listeners) l.detach();
        Interceptor.flush();
    }
}

/** Nom de classe d'un `Il2CppClass*` — exposé pour le diagnostic d'un champ non pointeur. */
export function klassName(k: NativePointer): string | null {
    try { return k.isNull() ? null : s(class_get_name(k) as NativePointer); }
    catch { return null; }
}
