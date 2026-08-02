// #443-r1a — LE TERME MOVE D'UNE TRIGGERED ABILITY, ATTRIBUÉ À SON UNITÉ ET À SA TUILE.
//
// ═══ CE QUE CE CAPTEUR EST SEUL À VOIR, ET POURQUOI IL EXISTE ═════════════════════════════════
// `scorerTileTermTrace` (scorer-damage-trace.ts) capte le composite `Tile(7)` COMPLET par
// candidat, mais son event **ne porte aucun `unitId`** — il n'a que la tuile du caster courant.
// Mesuré par #443-r1 sur `MC1_67`/777 : les 4 events captés portaient TOUS sur des tuiles
// occupées par un TIERS, et une version antérieure du probe, qui ne filtrait pas, a rendu un
// **accord parfait sur le `Tile(7)` d'une AUTRE unité**. Un canal sans attribution ne produit pas
// « moins de mesure » : il produit du FAUX POSITIF, à l'échelle.
//
// Ce capteur publie donc, PAR ÉVALUATION : à QUI (l'unité du `case`, plus le parent quand elle
// SPAWNE), à QUELLE TUILE (la `MovementPosition` du `case`), COMBIEN (le total yieldé), et
// **QUELLE ABILITY a contribué combien** (la décomposition par playbook). Cette dernière est ce
// qui manquait aussi à `ai-trace` L3 : lui émet le score TOTAL de la state machine, sans dire
// laquelle des triggered abilities du mover l'a produit — insuffisant pour confronter le terme
// d'UNE ability quand le mover en porte plusieurs.
//
// ═══ POURQUOI PAS `ai-trace` L3 ══════════════════════════════════════════════════════════════
// `installL3` (features/ai-trace/utilities.ts) hooke la MÊME surface — et 51 autres — mais :
//   * `--l3` est INTERDIT par le CLAUDE.md : hooks session-GLOBAUX, 52 trampolines posés d'un
//     bloc sur le hot path du sweep IA, et crash si un autre agent walke l'IA en parallèle ;
//   * ses events partent dans le flux ai-trace global, **sans attribution par runner** — donc
//     inexploitables quand plusieurs runners coexistent (la règle de coexistence du dépôt) ;
//   * il n'a pas la décomposition par ability (cf. ci-dessus).
// Ici : **2 hooks**, armés à la demande, buffers `OriginBuffers` (un bucket par runner d'origine,
// purgés au dispose), et rien n'est attaché au `register`.
//
// ═══ L'ARTEFACT NATIF, LU AU DÉCOMPILÉ ═══════════════════════════════════════════════════════
// `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
// (et sa JUMELLE `…TriggeredAbilitiesNonOwnerUtility.u003CEvaluateMovementInStepsu003Ed__0$$MoveNext`,
// MÊME layout de state machine à 72 octets, dont le décompilé — plus lisible — a servi de SECONDE
// SOURCE pour lever l'ambiguïté de flux du premier). Remis en C# :
//
//     Fix64 x = 0;
//     if (case.Unit == null) { yield return x; yield break; }
//     foreach (var ta in case.Unit.GetComponent<TriggeredAbilitiesComponent>().<Abilities@+0x18>) {
//         var pb = this.<>4__this.<playbookDatabase@+0x48>.LoadPlaybook(ta.<AbilityType>);
//         if (pb == null) continue;
//         var it = pb.<slot 2 = CalculateMovementUtilityInSteps>(case, this.<>4__this.<weights@+0x58>);
//         while (it.MoveNext()) yield return (Fix64)0;      // les « steps » : budget de calcul
//         x += it.Current;                                   // la contribution de CETTE ability
//     }
//     yield return x;                                        // le TOTAL
//
// Layout de la state machine (offsets LUS, mais résolus PAR NOM au runtime — cf. `resolveSm`) :
//   +0x10 `<>1__state` · +0x18 `<>2__current` (Fix64) · +0x20 `case` · +0x28 `<>4__this`
//   +0x30 accumulateur `x` (Fix64) · +0x38 énumérateur EXTERNE · +0x40 énumérateur INTERNE
//
// `IdunBattle.AI.Utilities.UtilityMovementCase` (64 o), lu sur ses propres accesseurs :
//   +0x10 `Unit`             — `$$get_UnitOrParent` (`this+0x10` sinon `this+0x30`),
//                              `$$StaysOnTile` (`GetMainTile(this+0x10, state)`), `$$get_IsSpawning`
//   +0x18 `MovementPosition` — `UnitPosition` **INLINE** ; `$$get_MovementTile` =
//                              `IdunBattle.Core.UnitPosition$$get_MainTile(this + 0x18)`, qui rend
//                              `list[0]` de la liste au champ `+0x00` de la struct
//   +0x30 `Parent`           — le SPAWNER, consulté quand `Unit` est nul (`$$get_IsSpawning` rend
//                              vrai exactement dans ce cas)
//
// ⚠ `Unit` et `Parent` sont publiés SÉPARÉMENT, jamais fondus. `get_UnitOrParent` les confond
// parce que ses appelants n'ont besoin que d'« un sujet » ; un canal d'ATTRIBUTION qui ferait
// pareil rendrait indiscernables « le drone a été évalué » et « le drone SPAWNE depuis X » —
// c'est-à-dire qu'il rejouerait, sur un autre axe, le faux positif que ce capteur existe pour tuer.
//
// ═══ RÉSOLUTION 100 % RUNTIME — aucune adresse en dur ════════════════════════════════════════
// La classe utility se résout par `findClassAnywhere`, sa state machine par
// `il2cpp_class_get_nested_types` (préfixe `<EvaluateMovementInSteps>d__`, l'API qui donne le
// DÉCLARANT et lève donc la collision des noms courts), son `MoveNext` par `findMethod`, et
// chaque offset par `getFieldOffset` sur la classe résolue. Les offsets ci-dessus ne servent que
// de REPLI nommé, et `triggeredMoveTraceStatus` publie, champ par champ, ce qui a été résolu par
// nom et ce qui est retombé sur le repli.
//
// RPC : `triggeredMoveTrace{On,Off,Clear,Dump,Status}`.

import { Ctx } from "../controller.js";
import {
    class_get_declaring_type, class_get_name, class_get_nested_types,
    findClassAnywhere, findMethod, getFieldOffset, s,
} from "../il2cpp/helpers.js";
import { log } from "../runtime/diag.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { getTraceOrigin, OriginBuffers } from "../game/trace-origin.js";
import { readTileCoord } from "./ai-step/internals.js";

// Cap PAR BUCKET (par origine). Un sweep de mouvement balaie quelques dizaines de tuiles par
// unité ; 4000 couvre plusieurs tours sans qu'un acteur bavard affame les autres (les buckets
// sont séparés par origine, cf. `OriginBuffers`).
const CAP = 4000;

// --- Offsets de REPLI, tous LUS au décompilé (cf. l'en-tête) ------------------------------------
// Ils ne sont utilisés que si `getFieldOffset` échoue sur le nom. Ce ne sont PAS des adresses :
// des offsets de STRUCT, que le CLAUDE.md autorise explicitement (« Les offsets RELATIFS restent »).
const SM_FALLBACK = {
    state: 0x10,        // <>1__state
    current: 0x18,      // <>2__current (Fix64)
    caseArg: 0x20,      // le paramètre `case` capturé
    outerThis: 0x28,    // <>4__this
    acc: 0x30,          // l'accumulateur Fix64
    outerEnum: 0x38,    // <>7__wrap1 — les triggered abilities du mover
    innerEnum: 0x40,    // <>7__wrap2 — l'itérateur rendu par le playbook
} as const;

const CASE_FALLBACK = {
    unit: 0x10,             // Unit
    movementPosition: 0x18, // MovementPosition (UnitPosition, struct INLINE)
    parent: 0x30,           // Parent (le spawner)
} as const;

// `IdunBattle.Core.Entity` : Id @+0x10 (BEntityId, int32), Type @+0x14 (EntityType).
// Mêmes constantes que `game/match-state.ts` — offsets de struct, pas des RVA.
const ENTITY_ID_OFF = 0x10;

/** Noms de champ candidats, dans l'ordre d'essai. Le compilateur C# nomme ses locals capturés
 *  `<nom>5__N` et ses énumérateurs imbriqués `<>7__wrapN`, mais l'indice N dépend de la version
 *  du compilateur : on essaie, et on DIT ce qu'on a trouvé (`triggeredMoveTraceStatus`) plutôt
 *  que de supposer. Le repli reste l'offset LU. */
const FIELD_CANDIDATES: Record<keyof typeof SM_FALLBACK, string[]> = {
    state: ["<>1__state"],
    current: ["<>2__current"],
    caseArg: ["case", "<>3__case", "movementCase", "<case>5__1"],
    outerThis: ["<>4__this"],
    // L'accumulateur : un local `Fix64` capturé. Son nom source est inconnu hors métadonnées ;
    // les indices 1..3 couvrent les formes vues sur cette famille de state machines.
    acc: ["<utility>5__1", "<x>5__1", "<result>5__1", "<sum>5__1",
          "<utility>5__2", "<x>5__2", "<result>5__2"],
    outerEnum: ["<>7__wrap1"],
    innerEnum: ["<>7__wrap2", "<>7__wrap3"],
};

const CASE_CANDIDATES: Record<keyof typeof CASE_FALLBACK, string[]> = {
    unit: ["Unit"],
    movementPosition: ["MovementPosition"],
    parent: ["Parent"],
};

interface Resolved {
    /** Nom de la classe utility hookée (`TriggeredAbilitiesUtility`, …). */
    utility: string;
    off: Record<string, number>;
    /** Champs retombés sur leur offset de REPLI (donc NON résolus par nom). */
    fallbacks: string[];
}

/** Une évaluation TERMINÉE : le total yieldé pour (unité, tuile), avec sa décomposition. */
interface MoveEvalEvent {
    seq: number;
    originRunnerId: number | null;
    /** Classe utility d'où vient l'évaluation (owner vs non-owner). */
    utility: string;
    /** `case.Unit` — l'unité ÉVALUÉE. `null` = champ illisible OU unité nulle (spawn) ;
     *  `unitMeasured` tranche. */
    unitId: number | null;
    /** TRI-ÉTAT : `false` = on n'a rien pu lire du `case` (offset non résolu, pointeur nul,
     *  lecture en erreur). `unitId: null` n'y veut PAS dire « pas d'unité ». */
    unitMeasured: boolean;
    /** `case.Parent` — le SPAWNER, non nul quand l'évaluation porte sur une unité qui APPARAÎT.
     *  Publié À PART de `unitId` : `UtilityMovementCase$$get_UnitOrParent` les confond, un canal
     *  d'attribution ne le doit pas. */
    parentId: number | null;
    /** Mirror de `UtilityMovementCase$$get_IsSpawning` : `Unit == null && Parent != null`. */
    isSpawning: boolean;
    /** Tuile CANDIDATE (`MainTile` de `case.MovementPosition`). `null` = non lue — jamais
     *  rabattu sur `(-1,-1)`, qui se lirait comme une coordonnée. */
    tile: { col: number; row: number } | null;
    /** Le total yieldé par la state machine = la somme des contributions ci-dessous. */
    total: number;
    /** Décomposition PAR ABILITY : le delta d'accumulateur observé à la fin de chaque
     *  sous-itération, étiqueté du nom de classe de l'itérateur du playbook (ex.
     *  `SaviorProtocolsPlaybook.<CalculateMovementUtilityInStepsInternal>d__4`).
     *  TRI-ÉTAT : `null` = l'accumulateur ou l'énumérateur interne n'a pas été résolu, donc la
     *  décomposition n'a PAS été mesurée — `[]` veut dire « mesurée, et aucune ability n'a
     *  contribué ». Les confondre ferait lire « ce mover ne porte aucune triggered ability »
     *  là où le capteur est simplement aveugle. */
    contribs: Array<{ playbook: string; value: number }> | null;
    /** Nombre d'appels `MoveNext` qu'a coûté cette évaluation (diagnostic de volume). */
    steps: number;
}

const trace: { on: boolean; seq: number; buf: OriginBuffers<MoveEvalEvent> } = {
    on: false, seq: 0, buf: new OriginBuffers<MoveEvalEvent>(CAP, "dropNew"),
};

// État PAR INSTANCE de state machine, accumulé entre les `MoveNext`. Clé = pointeur de la SM.
// Purgé quand l'évaluation se termine (et borné, cf. `MAX_LIVE_SM`) : une SM abandonnée en cours
// d'itération (l'IA jette l'énumérateur sans le drainer) ne doit pas fuir.
interface Live {
    contribs: Array<{ playbook: string; value: number }>;
    /** Dernière valeur d'accumulateur observée (Fix64 -> nombre). */
    lastAcc: number;
    steps: number;
    /** `false` dès qu'un maillon de la décomposition manque -> `contribs` sera publié `null`. */
    decomposable: boolean;
}
const live = new Map<string, Live>();
// Borne dure : au-delà, on jette les entrées les plus anciennes. Le sweep IA crée une SM par
// (utility, tuile candidate) ; quelques centaines suffisent largement, et la borne garantit que
// des SM jamais drainées ne font pas croître la Map indéfiniment.
const MAX_LIVE_SM = 2048;

/** Cache NOM DE CLASSE par pointeur `Il2CppClass*`. `class_get_name` est un appel natif sur un
 *  chemin CHAUD (une fois par sous-itération) ; le pointeur de classe est stable, donc le cache
 *  est efficace et le coût s'amortit à zéro. */
const classNameCache = new Map<string, string>();

/** Nom QUALIFIÉ par son déclarant d'une classe nested — sans quoi le label est ambigu :
 *  39 classes portent un `<EvaluateMovementInSteps>d__N` sur ce build, et plusieurs le même
 *  `d__2`. Sans `il2cpp_class_get_declaring_type`, on rend le nom court PRÉFIXÉ de `?.` : un
 *  label dégradé qui se VOIT, plutôt qu'un nom qualifié inventé. */
function qualifiedClassName(klass: NativePointer): string {
    if (klass.isNull()) return "?";
    const key = klass.toString();
    const hit = classNameCache.get(key);
    if (hit !== undefined) return hit;
    let name = "?";
    try {
        name = s(class_get_name(klass) as NativePointer) || "?";
        if (class_get_declaring_type) {
            const decl = class_get_declaring_type(klass) as NativePointer;
            if (!decl.isNull()) {
                const outer = s(class_get_name(decl) as NativePointer);
                if (outer) name = outer + "." + name;
            }
        } else {
            name = "?." + name;      // déclarant non résoluble -> dégradation VISIBLE
        }
    } catch { /* name reste "?" */ }
    classNameCache.set(key, name);
    return name;
}

/** Fix64 (int64 signé, 32 bits de fraction) -> nombre. Même conversion que `scorer-damage-trace`. */
function fix64(p: NativePointer): number {
    let raw = BigInt(p.readS64().toString());
    if (raw >= (1n << 63n)) raw -= (1n << 64n);
    return Number(raw) / 4294967296;
}

/** `il2cpp_class_get_nested_types` -> la state machine `<methodName>d__N` de `klass`.
 *  Elle n'est PAS cherchable par `findClassAnywhere` : son nom court collisionne (mesuré :
 *  39 porteurs d'un `<EvaluateMovementInSteps>d__N`), et la recherche rendrait la première
 *  trouvée. Passer par le DÉCLARANT est la seule voie non ambiguë. */
function findStateMachineClass(
    klass: NativePointer, methodName: string,
): NativePointer | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    const expected = "<" + methodName + ">d__";
    let cls: NativePointer;
    while (!(cls = class_get_nested_types(klass, it) as NativePointer).isNull()) {
        const name = s(class_get_name(cls) as NativePointer);
        if (name && name.startsWith(expected)) return cls;
    }
    return null;
}

/** Offset d'un champ, essayé par NOM sur chaque candidat, sinon l'offset de REPLI (LU au
 *  décompilé). Renseigne `fallbacks` pour que le status DISE ce qui n'a pas été résolu.
 *  ⚠ `getFieldOffset` rend **-1** quand le nom est absent, pas `0` — un test truthy laisserait
 *  passer le -1 et lirait à `base - 1` (le vice mesuré sur `actorStats`, #340-r1). */
function offsetOf(
    klass: NativePointer, key: string, names: string[], fallback: number, fallbacks: string[],
): number {
    for (const n of names) {
        const off = getFieldOffset(klass, n);
        if (off >= 0) return off;
    }
    fallbacks.push(key);
    return fallback;
}

const CASE_CLASS = (): NativePointer | null =>
    findClassAnywhere("IdunBattle.AI.Utilities", "UtilityMovementCase");

/** Les DEUX porteurs du terme `TriggeredAbilities` d'un case de MOUVEMENT. `Owner` est celui qui
 *  charge le playbook des abilities DU MOVER (le cas de `SaviorProtocols` 1120, dont le playbook
 *  est le point de vue du PROTECTEUR) ; `NonOwner` celui des abilities des AUTRES unités. On
 *  hooke les deux : même layout de SM, donc même décodeur, et couvrir un seul des deux laisserait
 *  un « zéro event » qu'on lirait à tort comme « le terme ne fire pas ». */
const UTILITY_CLASSES: readonly string[] = [
    "TriggeredAbilitiesUtility",
    "TriggeredAbilitiesNonOwnerUtility",
];

const installed: Record<string, string> = {};
const resolvedInfo: Record<string, unknown> = {};
let installDone = false;

function install(): boolean {
    if (installDone) return true;
    const caseKlass = CASE_CLASS();
    const caseFallbacks: string[] = [];
    const caseOff = {
        unit: caseKlass
            ? offsetOf(caseKlass, "case.unit", CASE_CANDIDATES.unit,
                       CASE_FALLBACK.unit, caseFallbacks)
            : CASE_FALLBACK.unit,
        movementPosition: caseKlass
            ? offsetOf(caseKlass, "case.movementPosition", CASE_CANDIDATES.movementPosition,
                       CASE_FALLBACK.movementPosition, caseFallbacks)
            : CASE_FALLBACK.movementPosition,
        parent: caseKlass
            ? offsetOf(caseKlass, "case.parent", CASE_CANDIDATES.parent,
                       CASE_FALLBACK.parent, caseFallbacks)
            : CASE_FALLBACK.parent,
    };
    if (!caseKlass) caseFallbacks.push("UtilityMovementCase:class_not_found");
    resolvedInfo.utilityMovementCase = { off: caseOff, fallbacks: caseFallbacks };

    let ok = 0;
    for (const cls of UTILITY_CLASSES) {
        const k = findClassAnywhere("IdunBattle.AI.Utilities", cls);
        if (!k) { installed[cls] = "class_not_found"; continue; }
        const sm = findStateMachineClass(k, "EvaluateMovementInSteps");
        if (!sm) { installed[cls] = "state_machine_not_found"; continue; }
        const mn = findMethod(sm, "MoveNext");
        if (!mn || mn.ptr.isNull()) { installed[cls] = "movenext_not_found"; continue; }
        const fallbacks: string[] = [];
        const off: Record<string, number> = {};
        for (const key of Object.keys(SM_FALLBACK) as Array<keyof typeof SM_FALLBACK>) {
            off[key] = offsetOf(sm, key, FIELD_CANDIDATES[key], SM_FALLBACK[key], fallbacks);
        }
        const r: Resolved = { utility: cls, off, fallbacks };
        resolvedInfo[cls] = { off, fallbacks, movenext: mn.ptr.toString() };
        try {
            attach(mn.ptr, r, caseOff);
            installed[cls] = "ok";
            ok++;
        } catch (e) {
            installed[cls] = "attach_failed: " + (e as Error).message;
        }
    }
    installDone = ok > 0;
    log("[triggered-move-trace] install: " + JSON.stringify(installed));
    return installDone;
}

interface Attribution {
    unitId: number | null;
    unitMeasured: boolean;
    parentId: number | null;
    isSpawning: boolean;
    tile: { col: number; row: number } | null;
}

/** Lit l'ATTRIBUTION depuis le `UtilityMovementCase` : à QUI et à QUELLE TUILE.
 *  C'est le critère d'acceptation de ce capteur — sans elle il fabriquerait, à l'échelle, le faux
 *  positif que #443-r1 a mesuré (accord parfait sur la tuile d'une AUTRE unité). */
function readAttribution(
    casePtr: NativePointer, caseOff: { unit: number; movementPosition: number; parent: number },
): Attribution {
    const none: Attribution = {
        unitId: null, unitMeasured: false, parentId: null, isSpawning: false, tile: null,
    };
    if (casePtr.isNull()) return none;
    let unitId: number | null = null;
    let parentId: number | null = null;
    let measured = false;
    try {
        const u = casePtr.add(caseOff.unit).readPointer();
        if (!u.isNull()) unitId = u.add(ENTITY_ID_OFF).readS32();
        measured = true;      // le `case` est lisible : `unitId: null` = « pas d'unité », un FAIT
    } catch { return none; }
    try {
        const p = casePtr.add(caseOff.parent).readPointer();
        if (!p.isNull()) parentId = p.add(ENTITY_ID_OFF).readS32();
    } catch { /* parent optionnel — l'attribution principale reste valide */ }
    // MIRROR de `IdunBattle.Core.UnitPosition$$get_MainTile(this + 0x18)` : la struct est INLINE
    // dans le case, son champ `+0x00` est la liste des tuiles occupées, et `MainTile` en est
    // l'élément 0 (`get_Count(list) == 0 -> null`). Layout `List<T>` : `_items @0x10`,
    // `_size @0x18`, éléments (références) à partir de `_items + 0x20`.
    let tile: { col: number; row: number } | null = null;
    try {
        const list = casePtr.add(caseOff.movementPosition).readPointer();
        if (!list.isNull()) {
            const size = list.add(0x18).readS32();
            if (size > 0 && size <= 32) {
                const items = list.add(0x10).readPointer();
                if (!items.isNull()) {
                    const t = items.add(0x20).readPointer();
                    if (!t.isNull()) {
                        const c = readTileCoord(t);
                        // `readTileCoord` rend (-1,-1) quand le `PositionComponent` est
                        // introuvable. On ne publie PAS ça : une coordonnée négative se lirait
                        // comme une tuile. `null` = non lue, et ça se voit.
                        if (c.col >= 0 && c.row >= 0) tile = c;
                    }
                }
            }
        }
    } catch { /* tuile optionnelle — `null` dit qu'elle n'a pas été lue */ }
    return {
        unitId, unitMeasured: measured, parentId,
        // MIRROR de `UtilityMovementCase$$get_IsSpawning` : vrai ssi `Unit == null` ET
        // `Parent != null` (le décompilé rend faux dès que `this+0x10` est non nul).
        isSpawning: unitId === null && parentId !== null,
        tile,
    };
}

function attach(
    fn: NativePointer, r: Resolved,
    caseOff: { unit: number; movementPosition: number; parent: number },
): void {
    const O = r.off;
    // La décomposition par ability exige les DEUX maillons. S'il en manque un, on publiera
    // `contribs: null` — « non mesurée » — plutôt qu'une liste vide qui se lirait « aucune
    // ability n'a contribué ».
    const decomposable = !r.fallbacks.includes("acc") && !r.fallbacks.includes("innerEnum");
    Interceptor.attach(fn, {
        onEnter(args): void {
            if (!trace.on) return;
            const self = this as {
                _sm?: NativePointer; _inner?: string; _acc?: number;
            };
            const sm = args[0];
            if (sm.isNull()) return;
            self._sm = sm;
            if (!decomposable) return;
            // On lit l'énumérateur INTERNE **avant** l'appel : `MoveNext` le remet à `null` juste
            // après avoir accumulé sa `Current`. C'est le seul instant où l'on sait QUELLE ability
            // vient de contribuer — le nom de classe de son itérateur porte celui du playbook.
            try {
                self._acc = fix64(sm.add(O.acc));
                const inner = sm.add(O.innerEnum).readPointer();
                if (!inner.isNull()) self._inner = qualifiedClassName(inner.readPointer());
            } catch { /* transient */ }
        },
        onLeave(retval): void {
            if (!trace.on) return;
            const self = this as {
                _sm?: NativePointer; _inner?: string; _acc?: number;
            };
            const sm = self._sm;
            if (!sm || sm.isNull()) return;
            const key = sm.toString();
            let st = live.get(key);
            if (!st) {
                if (live.size >= MAX_LIVE_SM) {
                    // SM jamais drainées (l'IA jette l'énumérateur) : on borne, en jetant la plus
                    // ancienne. Sans cette borne la Map croîtrait sur toute la session.
                    const oldest = live.keys().next();
                    if (!oldest.done) live.delete(oldest.value);
                }
                st = { contribs: [], lastAcc: 0, steps: 0, decomposable };
                live.set(key, st);
            }
            st.steps++;
            try {
                if (st.decomposable) {
                    const acc = fix64(sm.add(O.acc));
                    // L'accumulateur n'a bougé QUE si une sous-itération vient de se terminer :
                    // `x += it.Current`. Le delta EST la contribution de cette ability, et le nom
                    // capturé à l'entrée est celui de son playbook.
                    if (self._acc !== undefined && acc !== self._acc) {
                        st.contribs.push({
                            playbook: self._inner ?? "?",
                            value: acc - self._acc,
                        });
                    }
                    st.lastAcc = acc;
                }
                const state = sm.add(O.state).readS32();
                // Les DEUX états terminaux qui posent `<>2__current = x` (le TOTAL) :
                //   1 = sortie immédiate `case.Unit == null` ;
                //   3 = fin de la boucle externe.
                // L'état 2, lui, est un « step » : `<>2__current` y vaut `Fix64(0)`, pas le total.
                const isTotal = retval.toInt32() !== 0 && (state === 1 || state === 3);
                if (!isTotal) return;
                const casePtr = sm.add(O.caseArg).readPointer();
                const attr = readAttribution(casePtr, caseOff);
                trace.buf.push({
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    utility: r.utility,
                    unitId: attr.unitId,
                    unitMeasured: attr.unitMeasured,
                    parentId: attr.parentId,
                    isSpawning: attr.isSpawning,
                    tile: attr.tile,
                    total: fix64(sm.add(O.current)),
                    contribs: st.decomposable ? st.contribs : null,
                    steps: st.steps,
                });
            } catch { /* transient — l'event est simplement perdu, jamais faux */ }
            finally {
                const state2 = (() => {
                    try { return sm.add(O.state).readS32(); } catch { return -99; }
                })();
                // L'itération est finie (états terminaux, ou `MoveNext` a rendu faux) -> on purge
                // l'état vivant. Le même pointeur de SM peut être RÉUTILISÉ par l'allocateur pour
                // une autre évaluation ; garder l'entrée mélangerait deux décompositions.
                if (state2 === 1 || state2 === 3 || state2 < 0) live.delete(key);
            }
        },
    });
}

export function register(ctx: Ctx): void {
    // Le register n'attache RIEN : ce `MoveNext` est sur le hot path du sweep de mouvement de
    // l'IA (un appel par tuile candidate ET par step). L'armement est explicite.

    ctx.rpc.triggeredMoveTraceOn = (): Promise<unknown> =>
        queueOnMainThread(() => {
            const ok = install();
            trace.on = ok;
            return { ok, on: trace.on, installed, resolved: resolvedInfo };
        });

    ctx.rpc.triggeredMoveTraceOff = (): unknown => {
        trace.on = false;
        return { ok: true, bufferSize: trace.buf.size() };
    };

    ctx.rpc.triggeredMoveTraceClear = (body?: { runnerId?: number }): unknown => {
        const rid = body?.runnerId;
        trace.buf.clear(rid);
        if (typeof rid !== "number") { trace.seq = 0; live.clear(); }
        return { ok: true, bufferSize: trace.buf.size() };
    };

    /** Les évaluations TERMINÉES, avec leur attribution (unité + tuile) et leur décomposition.
     *  `runnerId` -> bucket direct de CE runner ; sans -> toutes origines, ordre `seq`. */
    ctx.rpc.triggeredMoveTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            on: trace.on, installed,
            bufferSize: trace.buf.size(),
            entries: trace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Ce que la résolution runtime a trouvé, champ par champ — et surtout ce qu'elle N'A PAS
     *  trouvé (`fallbacks`). Un capteur dont un offset est retombé sur son repli n'est pas faux,
     *  mais il n'est plus auto-vérifiant : il faut le SAVOIR avant d'exploiter une mesure. */
    ctx.rpc.triggeredMoveTraceStatus = (): unknown => ({
        on: trace.on, installDone, installed, resolved: resolvedInfo,
        liveStateMachines: live.size, bufferSize: trace.buf.size(),
    });
}
