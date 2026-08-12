/** `#969-r1` — CAPTEUR : la PORTE ALEATOIRE des playbooks (`BasePlaybook$$ShouldEvaluate`).
 *
 *  ⚠ **INERTE tant que le bundle n'est pas rebuilde + reinjecte** (geste orchestrateur). Le
 *  `register` n'arme AUCUN hook : il n'expose qu'un RPC.
 *
 *  ## Ce que le residu ne peut pas mesurer sans lui
 *
 *  `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` est une porte a trois regimes, LUE :
 *
 *      p = <virtuelle +0x1f8 GetUseProbability>(this, unit, this-><+0x200>);
 *      if (Fix64.op_GreaterThanOrEqual(p, Fix64(1))) return true;    // deterministe VRAI
 *      if (Fix64.op_LessThanOrEqual   (p, Fix64(0))) return false;   // deterministe FAUX
 *      return <IPseudoRNG @this+0x30>.<slot 4 NextBool>(p);          // TIRAGE
 *
 *  Les deux zeros deterministes SONT portes (#969). C'est le regime INTERMEDIAIRE qui manque, et il
 *  DOMINE en partie : `1049 CrusadeOfWrath` vaut `0.1 x maxBuffed` (donc `]0,1[` des que
 *  `1 <= maxBuffed <= 9`) et `1106 WarHowl` vaut `0.50`/`0.75` des que `n < 3`. Le port reste
 *  PERMISSIF a dessein (refuser rendrait l'ability INVISIBLE, defaut le plus cher, #967), mais
 *  l'ecart est alors ASSUME et non mesure : `6/7 -> 4/7` de match d'ability.
 *
 *  **Ce capteur rend l'ecart MESURABLE** : il publie, par appel, la probabilite `p` EXACTE et le
 *  resultat du tirage. Il vaut pour tous les porteurs du meme regime (`BlackRage` 0.4, `ItItches`).
 *
 *  ## Le point d'ancrage, et pourquoi il n'est PAS chaud
 *
 *  La sequence de `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`,
 *  lue en entier, place les surcharges :
 *
 *      BOUCLE PAR ABILITY :
 *         ... LoadPlaybook(abilityId) ...
 *         IPlaybook.<slot 4> ShouldEvaluate(unit)          -> false ? continue    <-- ANCRE
 *         IPlaybook.<slot 5> ShouldEvaluate(unit, tiles)   -> false ? continue    <-- ANCRE
 *         BOUCLE PAR POSITION :
 *            IPlaybook.<slot 6> ShouldEvaluate(unit, pos, tiles)                  <-- **PAS** ancre
 *
 *  Les slots 4 et 5 tirent **une fois par couple (unite, ability)**, AVANT toute enumeration de
 *  tuile : c'est le point le plus etroit du gate. Le slot 6, lui, tire PAR POSITION CANDIDATE —
 *  c'est un chemin CHAUD, et il n'est pas ancre. (Il n'a d'ailleurs pas de tirage : son corps est
 *  un gate `IdunBattle.Entities.TileExtensions$$IsTemporary`.)
 *
 *  ## Comment `p` est capte, alors que `ShouldEvaluate` ne le rend pas
 *
 *  `ShouldEvaluate` rend un `bool` ; `p` ne sort jamais. On ancre donc AUSSI
 *  `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextBool` (l'overload `Fix64`, slot 4 d'
 *  `IdunBattle.Utils.PRNG.IPseudoRNG`), dont `args[1]` **EST** `p`.
 *
 *  ⚠ Ce symbole est PARTAGE par tout autre consommateur de `NextBool(Fix64)`. On ne publie donc un
 *  tirage comme « celui de ce `ShouldEvaluate` » que s'il est IMBRIQUE dedans, sur le MEME thread :
 *  un compteur de profondeur pose a l'`onEnter` de `ShouldEvaluate` et retire a l'`onLeave`. Les
 *  tirages HORS imbrication sont comptes a part (`rngHorsPortee`) et **jamais** attribues — un
 *  capteur qui melangerait les deux rendrait des probabilites appartenant a une autre mecanique.
 *
 *  ⚠ **Deux overloads de `NextBool`**, et confondre les deux fausserait tout : le slot 4 prend une
 *  `Fix64` dans [0,1], le slot **5** un `int` POURCENTAGE (1..99). On resout par le TYPE du
 *  parametre (`findMethodByParamClasses`), jamais par l'arite, qui est la meme.
 *
 *  ## Discipline
 *
 *  Arme a la demande (`shouldEvaluateTrace {action:"arm"}`), anneau borne, `disarm` detache.
 *  Read-only : aucune valeur reecrite, aucun `Interceptor.replace`. La resolution est rendue au
 *  moment de l'armement — un capteur qui ne peut pas s'attacher doit le dire LA, pas se taire
 *  jusqu'a rendre zero fire.
 */
import {
    class_get_name, cstr, findClassAnywhere, findMethodByParamClasses, findMethodByParamCount,
} from "../il2cpp/helpers.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

interface GateCall {
    /** Arite de la surcharge ancree : 1 = `ShouldEvaluate(unit)` (slot 4), 2 = `(unit, tiles)`
     *  (slot 5). Publiee parce que les deux ont le MEME corps mais des virtuelles distinctes. */
    arity: number;
    /** `Entity+0x10` — l'unite qui evalue. `null` = non lisible (jamais fabrique). */
    unitId: number | null;
    /** Le verdict RENDU par `ShouldEvaluate`. */
    returned: boolean;
    /** La probabilite brute (`Fix64` base 10) passee a `NextBool`, si un tirage a eu lieu DANS cet
     *  appel. `null` = AUCUN tirage -> l'appel est tombe dans un des deux regimes DETERMINISTES,
     *  et c'est une information, pas une absence de mesure. */
    probRaw: string | null;
    /** `probRaw / 2^32` — la probabilite en clair. */
    prob: number | null;
    /** Le resultat du tirage lui-meme (identique a `returned` quand il y a eu tirage). */
    drew: boolean | null;
    seq: number;
}

const RING_MAX = 500;

const trace = {
    armed: false,
    listeners: [] as InvocationListener[],
    calls: [] as GateCall[],
    seq: 0,
    diag: {
        gateFires: 0, rngFires: 0,
        /** Tirages vus HORS d'un `ShouldEvaluate` : jamais attribues, mais COMPTES — c'est la
         *  mesure du bruit que le symbole partage apporte. */
        rngHorsPortee: 0,
        unitReadFailed: 0, dropped: 0,
        /** Appels tombes dans un regime DETERMINISTE (aucun tirage imbrique). */
        deterministes: 0,
    },
};

/** Profondeur d'imbrication PAR THREAD. Un `NextBool` n'est attribue que si elle est > 0. */
const depth: Record<number, number> = {};
/** L'appel en cours par thread, pour y ecrire la probabilite quand le tirage survient. */
const pending: Record<number, GateCall | undefined> = {};

/** Fix64 (Q32.32) brut -> nombre. Meme conversion que `sort-utility-trace`. */
function fix64ToNumber(raw: Int64): number {
    try { return Number(BigInt(raw.toString())) / 4294967296; } catch { return NaN; }
}

/** Un `NativePointer` de registre -> `Int64` SIGNE.
 *
 *  ⚠ `new Int64(p.toString())` SATURE — `NativePointer.toString()` rend l'hexa NON SIGNE, que
 *  `Int64` parse au-dela de `Int64.MaxValue` et rabat dessus. Mesure `#419-r7` : 100 % des cles
 *  d'un capteur voisin rendaient `9223372036854775807`, et deux regimes differents se lisaient
 *  IDENTIQUES. Le detour par la memoire reinterprete les 64 bits en complement a deux. */
const rawBuf = Memory.alloc(8);
function toInt64(p: NativePointer): Int64 {
    rawBuf.writePointer(p);
    return rawBuf.readS64();
}

export function registerShouldEvaluateTrace(ctx: Ctx): void {
    ctx.rpc.shouldEvaluateTrace = (
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
            const pbClass = findClassAnywhere("IdunBattle.AI.Playbook", "BasePlaybook");
            const gate1 = pbClass ? findMethodByParamCount(pbClass, "ShouldEvaluate", 1) : null;
            const gate2 = pbClass ? findMethodByParamCount(pbClass, "ShouldEvaluate", 2) : null;
            // `IntBasedMersenneTwister` est l'implementation TERMINALE (`DisallowablePseudoRNG`
            // n'est qu'un decorateur qui delegue). On resout l'overload par le TYPE du parametre :
            // `Fix64` = la probabilite ; l'autre overload prend un `int` POURCENTAGE.
            const rngClass = findClassAnywhere(
                "IdunBattle.Utils.PRNG", "IntBasedMersenneTwister");
            const nextBool = rngClass
                ? findMethodByParamClasses(rngClass, "NextBool", ["Fix64"]) : null;
            const resolution = {
                basePlaybook: !!pbClass,
                shouldEvaluate1: !!gate1, shouldEvaluate2: !!gate2,
                mersenneTwister: !!rngClass, nextBoolFix64: !!nextBool,
            };
            if (!gate1 && !gate2) {
                return { ok: false, armed: false, resolution,
                    error: "aucune surcharge de `BasePlaybook$$ShouldEvaluate` resolue — AUCUN "
                        + "hook pose (un capteur a demi arme rendrait des tirages sans porte)" };
            }
            if (!nextBool) {
                return { ok: false, armed: false, resolution,
                    error: "`IntBasedMersenneTwister$$NextBool(Fix64)` non resolu. On REFUSE de "
                        + "s'armer sur la seule porte : `ShouldEvaluate` ne rend que le booleen, "
                        + "donc `p` — la valeur qui tranche le residu — serait TOUJOURS `null`, "
                        + "ce qui se lirait a tort comme « regime deterministe »." };
            }

            const attachGate = (mi: { ptr: NativePointer }, arity: number) => {
                trace.listeners.push(Interceptor.attach(mi.ptr, {
                    onEnter(this: InvocationContext, args) {
                        trace.diag.gateFires++;
                        const t = this.threadId;
                        depth[t] = (depth[t] ?? 0) + 1;
                        let unitId: number | null = null;
                        try {
                            const u = args[1];
                            if (u && !u.isNull()) unitId = u.add(0x10).readS32();
                            else trace.diag.unitReadFailed++;
                        } catch { trace.diag.unitReadFailed++; }
                        trace.seq++;
                        const row: GateCall = {
                            arity, unitId, returned: false,
                            probRaw: null, prob: null, drew: null, seq: trace.seq,
                        };
                        // Une porte peut en appeler une autre (surcharge 2 -> surcharge 1) : on
                        // n'ecrase le `pending` que si le thread n'en a pas deja un, sinon le
                        // tirage de l'appel INTERNE serait attribue a l'externe.
                        if (depth[t] === 1) pending[t] = row;
                        (this as { _row?: GateCall })._row = row;
                    },
                    onLeave(this: InvocationContext, retval) {
                        const t = this.threadId;
                        depth[t] = Math.max(0, (depth[t] ?? 1) - 1);
                        const row = (this as { _row?: GateCall })._row;
                        if (depth[t] === 0) pending[t] = undefined;
                        if (!row) return;
                        row.returned = (retval.toInt32() & 1) === 1;
                        if (row.probRaw === null) trace.diag.deterministes++;
                        trace.calls.push(row);
                        while (trace.calls.length > RING_MAX) {
                            trace.calls.shift(); trace.diag.dropped++;
                        }
                    },
                }));
            };
            if (gate1) attachGate(gate1, 1);
            if (gate2) attachGate(gate2, 2);

            trace.listeners.push(Interceptor.attach(nextBool.ptr, {
                onEnter(this: InvocationContext, args) {
                    trace.diag.rngFires++;
                    const t = this.threadId;
                    if (!(depth[t] > 0)) { trace.diag.rngHorsPortee++; return; }
                    const row = pending[t];
                    if (!row) { trace.diag.rngHorsPortee++; return; }
                    const raw = toInt64(args[1] as NativePointer);
                    row.probRaw = raw.toString();
                    row.prob = fix64ToNumber(raw);
                    (this as { _row?: GateCall })._row = row;
                },
                onLeave(this: InvocationContext, retval) {
                    const row = (this as { _row?: GateCall })._row;
                    if (row) row.drew = (retval.toInt32() & 1) === 1;
                },
            }));

            trace.armed = true;
            return { ok: true, armed: true, resolution };
        }

        const out = {
            ok: true, armed: trace.armed,
            diag: { ...trace.diag },
            callCount: trace.calls.length,
            calls: action === "status" ? [] : trace.calls,
        };
        if (body?.clear) {
            trace.calls = [];
            trace.diag = { gateFires: 0, rngFires: 0, rngHorsPortee: 0,
                unitReadFailed: 0, dropped: 0, deterministes: 0 };
        }
        return out;
    });
}

/** Le nom de classe d'un `Il2CppClass*` — utilitaire de diagnostic, jamais un chemin de decision. */
export function klassName(k: NativePointer): string {
    try { return cstr(class_get_name(k) as NativePointer); } catch { return "?"; }
}
