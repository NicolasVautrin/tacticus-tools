/** `#419-r6-r1-r1` — CAPTEUR : l'utilite PAR CIBLE du selecteur de tri par degat.
 *
 *  ## La question binaire, et la valeur qui la tranche
 *
 *  `#419-r6-r1` a MESURE que `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select`
 *  ne fait PAS entrer `MightCrit` dans son classement (port sans le flag = BIT-EXACT avec le live ;
 *  contrefactuel avec le flag = DIVERGE). Ce qui n'est pas isole, c'est l'ETAGE qui le neutralise :
 *  les trois maillons lus au decompile transportent tous le flag
 *  (`IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` memset une
 *  `AttackPredictionRequest` puis appelle le slot 4 ; `IdunBattle.AI.Utilities.UtilityAttackCase$$ForDamagePrediction`
 *  recopie `+0x00..+0x9c` flags compris ; `IdunBattle.AI.Utilities.OverkillUnitUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext`
 *  appelle bien `MightBeOverkill`).
 *
 *  **La valeur non publiee qui tranche : l'utilite RENDUE PAR CIBLE dans la boucle du selecteur.**
 *  Si elle est IDENTIQUE quand le flag change, l'etage neutralisant est EN AVAL de la
 *  prediction (le decideur, ou l'utilite elle-meme) ; si elle DIFFERE alors que l'ORDRE ne
 *  bouge pas, la neutralisation est dans le TRI (egalites, arrondi de la cle). Aucun autre canal
 *  ne peut separer ces deux mondes : `pairUtility` est l'utilite de PAIRE d'un playbook, pas
 *  celle de ce selecteur.
 *
 *  ## Le point d'ancrage, et pourquoi CELUI-LA
 *
 *  Le corps de `$$Select`, relu en entier, termine par
 *
 *      OrderBy( <la liste source>, new Func(<DisplayClass9_0>, <Select>b__0) ) -> ToList()
 *
 *  et la lambda est LITTERALEMENT
 *
 *      // SortUnitsByDamageUtilitySelector.u003Cu003Ec__DisplayClass9_0$$u003CSelectu003Eb__0(this, unit)
 *      return -this.<+0x28 = Dictionary<IEntity, Fix64>>[unit];
 *
 *  C'est donc EXACTEMENT la cle de tri, unite par unite, et le dictionnaire qu'elle lit est celui
 *  que la boucle a rempli avec le retour d'
 *  `IdunBattleLogic.AI.Utilities.UtilityDecider$$CalculateUtility`.
 *
 *  ⚠ **On ancre la LAMBDA, pas `UtilityDecider$$CalculateUtility`** — et c'est un choix mesure,
 *  pas une commodite. Deux raisons :
 *   1. `$$CalculateUtility` est une DEFINITION GENERIQUE
 *      (`...$$CalculateUtilityu003C__Il2CppFullySharedGenericTypeu003E`) : `findMethod` y rend le
 *      thunk d'invocation, pas le corps partage (#259-b) — le piege du hook qui se declare
 *      `enabled` avec 0 fire.
 *   2. Son corps gshared est partage par TOUT le decideur d'utilite de l'IA : l'ancrer poserait un
 *      trampoline sur un chemin chaud, pour n'en garder qu'une fraction infime. La lambda, elle,
 *      n'a que DEUX xrefs dans tout le binaire, toutes deux dans ce selecteur.
 *
 *  On ancre AUSSI `$$Select` lui-meme, pour DELIMITER les sessions : sans lui, les paires de deux
 *  casts successifs se melangeraient dans un seul flot, et « l'utilite par cible » perdrait le
 *  seul contexte qui la rend interpretable.
 *
 *  ## Discipline
 *
 *  ARME A LA DEMANDE, jamais installe au chargement (`sortUtilityTrace {action:"arm"}`), anneau
 *  borne, `disarm` detache. Read-only : aucune valeur n'est reecrite, aucun `Interceptor.replace`.
 */
import {
    class_get_name, class_get_nested_types, findClassAnywhere, findMethod, s,
} from "../../il2cpp/helpers.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { Ctx } from "../../controller.js";

/** Une paire (cible, cle de tri) telle que l'`OrderBy` natif l'a lue. */
interface SortPair {
    /** `Entity+0x10` — l'entityId de l'unite triee (meme lecture que `forEachEntity`). */
    unitId: number | null;
    /** `Entity+0x14` — l'EntityType, pour que le lecteur voie si le selecteur a trie autre
     *  chose que des `Unit` (une `Machine`, une `Tile`) sans avoir a le supposer. */
    entityType: number | null;
    /** La CLE DE TRI rendue par la lambda, brute (raw Fix64, base 10). C'est `-utilite`. */
    keyRaw: string;
    /** La cle convertie (`raw / 2^32`) — Q32.32. */
    key: number;
    /** `-key` : l'utilite telle que `UtilityDecider$$CalculateUtility` l'a rendue. */
    utility: number;
    /** Index de session (`selectSeq`) : les paires d'un meme `$$Select` partagent la valeur. */
    seq: number;
}

interface SelectSession {
    seq: number;
    /** Nombre d'unites que l'`OrderBy` a demandees (== cardinal de la liste source). */
    pairs: number;
    /** L'ORDRE rendu par `$$Select` — les entityId de la liste TRIEE, dans l'ordre.
     *  `null` = la liste de retour n'a pas pu etre decodee (jamais `[]`, qui voudrait dire
     *  « le selecteur n'a rien rendu »). */
    ordered: number[] | null;
    ts: number;
}

const RING_MAX = 400;
const SESSION_MAX = 40;

const trace = {
    armed: false,
    listeners: [] as InvocationListener[],
    pairs: [] as SortPair[],
    sessions: [] as SelectSession[],
    seq: 0,
    /** Compteurs de DIAGNOSTIC : un capteur muet doit le DIRE, pas rendre une liste vide qui se
     *  lit « le natif n'a rien trie ». */
    diag: {
        selectFires: 0, lambdaFires: 0,
        unitReadFailed: 0, orderedReadFailed: 0, dropped: 0,
    },
};

/** `List<IEntity>` (le retour de `$$Select`) -> entityIds. Bornee ET tri-etat : `null` si la
 *  forme n'est pas celle attendue, jamais un tableau tronque silencieusement. */
function readEntityIdList(listPtr: NativePointer): number[] | null {
    if (listPtr.isNull()) return null;
    try {
        const items = listPtr.add(0x10).readPointer();
        const size = listPtr.add(0x18).readS32();
        if (items.isNull() || size < 0 || size > 512) return null;
        const out: number[] = [];
        for (let i = 0; i < size; i++) {
            const e = items.add(0x20 + i * Process.pointerSize).readPointer();
            out.push(e.isNull() ? -1 : e.add(0x10).readS32());
        }
        return out;
    } catch { return null; }
}

/** Fix64 (Q32.32) brut -> nombre. Meme conversion que `bucket-audit` / `scorer-damage-trace`. */
function fix64ToNumber(raw: Int64): number {
    try { return Number(BigInt(raw.toString())) / 4294967296; } catch { return NaN; }
}

/** La lambda `<Select>b__0` de `<>c__DisplayClass9_0`, resolue PAR SON DECLARANT.
 *
 *  ⚠ Jamais par `findClassAnywhere("<>c__DisplayClass9_0")` : ce nom court COLLISIONNE
 *  massivement (le compilateur en genere un par methode a closure), et la recherche rendrait la
 *  PREMIERE classe trouvee — potentiellement la mauvaise, sans la moindre erreur. Le declarant
 *  leve l'ambiguite, exactement comme `class_get_declaring_type` le prescrit pour les state
 *  machines d'iterateur. */
function resolveSortLambda(): { info: NativePointer; ptr: NativePointer } | null {
    const owner = findClassAnywhere(
        "IdunBattle.Entities.Selectors", "SortUnitsByDamageUtilitySelector");
    if (!owner) return null;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let nested: NativePointer;
    while (!(nested = class_get_nested_types(owner, it) as NativePointer).isNull()) {
        const name = s(class_get_name(nested) as NativePointer);
        if (name.indexOf("DisplayClass9_0") < 0) continue;
        const m = findMethod(nested, "<Select>b__0");
        if (m) return m;
    }
    return null;
}

export function registerSortUtilityTrace(ctx: Ctx): void {
    /** `sortUtilityTrace` — arme/lit/desarme la trace du selecteur de tri par degat.
     *
     *  body: { action: "arm" | "read" | "disarm" | "status", clear?: boolean }
     *
     *  `arm` rend le detail de la RESOLUTION (quel symbole a ete trouve, lequel non) : un capteur
     *  qui ne peut pas s'attacher doit le dire au moment ou on l'arme, pas se taire jusqu'a rendre
     *  zero fire. */
    ctx.rpc.sortUtilityTrace = (
        body?: { action?: string; clear?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        const action = body?.action ?? "read";

        if (action === "disarm") {
            for (const l of trace.listeners) { try { l.detach(); } catch { /* */ } }
            trace.listeners = [];
            trace.armed = false;
            return { ok: true, armed: false };
        }

        if (action === "arm") {
            if (trace.armed) {
                return { ok: true, armed: true, note: "deja arme (aucun hook re-attache)" };
            }
            const selectorClass = findClassAnywhere(
                "IdunBattle.Entities.Selectors", "SortUnitsByDamageUtilitySelector");
            const selectMi = selectorClass ? findMethod(selectorClass, "Select") : null;
            const lambdaMi = resolveSortLambda();
            const resolution = {
                selectorClass: !!selectorClass,
                select: !!selectMi,
                lambda: !!lambdaMi,
            };
            if (!selectMi || !lambdaMi) {
                return { ok: false, armed: false, resolution,
                    error: "resolution incomplete — AUCUN hook pose (un capteur a demi arme "
                        + "rendrait des paires sans session, ou des sessions sans paires)" };
            }
            // `$$Select` : borne la session ET publie l'ORDRE natif rendu.
            trace.listeners.push(Interceptor.attach(selectMi.ptr, {
                onEnter() {
                    trace.diag.selectFires++;
                    trace.seq++;
                    (this as { _seq?: number })._seq = trace.seq;
                },
                onLeave(retval) {
                    const seq = (this as { _seq?: number })._seq ?? 0;
                    const ordered = readEntityIdList(retval as NativePointer);
                    if (ordered === null) trace.diag.orderedReadFailed++;
                    trace.sessions.push({
                        seq,
                        pairs: trace.pairs.filter((p) => p.seq === seq).length,
                        ordered,
                        ts: Date.now(),
                    });
                    while (trace.sessions.length > SESSION_MAX) trace.sessions.shift();
                },
            }));
            // La lambda : (unite, cle de tri). `args[0]` = le DisplayClass, `args[1]` = l'unite.
            trace.listeners.push(Interceptor.attach(lambdaMi.ptr, {
                onEnter(args) {
                    trace.diag.lambdaFires++;
                    (this as { _unit?: NativePointer })._unit = args[1];
                },
                onLeave(retval) {
                    const u = (this as { _unit?: NativePointer })._unit;
                    let unitId: number | null = null;
                    let entityType: number | null = null;
                    if (u && !u.isNull()) {
                        try {
                            unitId = u.add(0x10).readS32();
                            entityType = u.add(0x14).readS32();
                        } catch { trace.diag.unitReadFailed++; }
                    } else { trace.diag.unitReadFailed++; }
                    // Fix64 = struct de 8 octets => rendu dans RAX, donc `retval` EST la valeur
                    // brute. On la garde AUSSI en base 10 : la conversion Q32.32 perd des bits de
                    // poids faible sur un `double`, et une comparaison « identique / different »
                    // doit pouvoir se faire sur l'entier exact.
                    const raw = new Int64(retval.toString());
                    const key = fix64ToNumber(raw);
                    trace.pairs.push({
                        unitId, entityType,
                        keyRaw: raw.toString(), key, utility: -key,
                        seq: trace.seq,
                    });
                    while (trace.pairs.length > RING_MAX) {
                        trace.pairs.shift(); trace.diag.dropped++;
                    }
                },
            }));
            trace.armed = true;
            return { ok: true, armed: true, resolution };
        }

        // `read` / `status`
        const out = {
            ok: true,
            armed: trace.armed,
            diag: { ...trace.diag },
            sessionCount: trace.sessions.length,
            pairCount: trace.pairs.length,
            sessions: action === "status" ? [] : trace.sessions,
            pairs: action === "status" ? [] : trace.pairs,
        };
        if (body?.clear) {
            trace.pairs = []; trace.sessions = [];
            trace.diag = { selectFires: 0, lambdaFires: 0, unitReadFailed: 0,
                orderedReadFailed: 0, dropped: 0 };
        }
        return out;
    });
}
