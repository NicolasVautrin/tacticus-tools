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
    class_get_fields, class_get_name, class_instance_size, field_get_name, field_get_offset,
    findClassAnywhere, findMethod, s,
} from "../../il2cpp/helpers.js";
import { classNameAt } from "./playbook-predict.js";
import { readTileCoord } from "./internals.js";

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
    /** Taille de la `List<ITile>` rendue. `-1` = retour non décodable (ni `List`1` ni tableau). */
    returnedCount: number;
    returnedClass: string | null;
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

/** Décode une `List<T>` de références (items@+0x10, count@+0x18, éléments dès +0x20, stride 8) ou
 *  un tableau managé (count@+0x18, éléments dès +0x20) — le MÊME harnais que
 *  `playbook-predict.decodeEventsGeneric`, réduit aux références.
 *  `count = -1` ⇒ forme non décodable : c'est une ERREUR, pas un zéro. */
function readRefList(
    list: NativePointer,
): { count: number; cls: string | null; tiles: Array<{ col: number; row: number }> } {
    const tiles: Array<{ col: number; row: number }> = [];
    if (list.isNull()) return { count: -1, cls: null, tiles };
    const cls = classNameAt(list);
    try {
        let items = list;                          // tableau : éléments dès +0x20 sur `list`
        if (cls === "List`1") items = list.add(0x10).readPointer();
        else if (cls === null || !cls.endsWith("[]")) return { count: -1, cls, tiles };
        const count = list.add(0x18).readS32();
        if (items.isNull() || count <= 0) return { count: Math.max(count, 0), cls, tiles };
        for (let i = 0; i < Math.min(count, MAX_TILES); i++) {
            const e = items.add(0x20 + i * 8).readPointer();
            if (e.isNull()) continue;
            const c = readTileCoord(e);
            if (c.col >= 0 && c.row >= 0) tiles.push({ col: c.col, row: c.row });
        }
        return { count, cls, tiles };
    } catch { return { count: -1, cls, tiles }; }
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
                calls.push({
                    seq: pendingSeq, thisPtr: self.toString(), ctx: readCtx(ctx),
                    returnedCount: ret.count, returnedClass: ret.cls,
                });
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
                        returnedTiles: ret.tiles,
                    };
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
