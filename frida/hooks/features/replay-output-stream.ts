// replay-output-stream (#477) — expose la TRACE TEXTUELLE CANONIQUE que le moteur
// natif produit pour chaque bataille, ainsi que sa sequence PRNG complete.
//
// POURQUOI ce module existe
// -------------------------
// Le jeu embarque son propre oracle de re-simulation, `Runner.ReplayValidator`.
// Sa methode `Runner.ReplayValidator$$RunReplayWithParameters` rejoue un replay
// dans un `IdunBattle.Runner.ReplayRunner` neuf, puis compare le resultat a
// l'original par DEUX canaux, et rien d'autre :
//
//   - `Runner.ReplayValidator$$CompareOutputStream` — compare
//     `IdunBattleLogic.Replay.Replay$$GetWholeBattleOutputStream` des deux cotes,
//     CARACTERE PAR CARACTERE (boucle sur `System.String.get_Chars`) ;
//   - `Runner.ReplayValidator$$CompareRngEvents` — compare
//     `IdunBattleLogic.Replay.Replay$$GetWholeBattleRngEvents` via
//     `Runner.RngEventComparer$$DoRngEventsDiffer`.
//
// Autrement dit : les devs du jeu considerent ces deux flux comme la SIGNATURE
// COMPLETE d'une bataille. C'est exactement l'oracle dense qui nous manque pour
// valider le port Python — et il est non circulaire vis-a-vis de lui, puisqu'il
// est produit par le moteur natif.
//
// CE QUE CONTIENT l'output stream
// -------------------------------
// `IdunBattleLogic.Replay.ReplayRecorder$$OnStreamCacheRootGroupFinished(group)`
// fait `_outputStreamBuffer.Append(group)` : le flux est donc la serialisation
// texte des GROUPES RACINE du StreamDispatcher, dans l'ordre ou ils se terminent.
// `IdunBattleLogic.Replay.ReplayRecorder$$SaveCurrentOutputStreamBufferToLastMessage`
// vide ce buffer dans `ReplayStep.OutputStream` (+0x28) du DERNIER message applique,
// puis `StringBuilder.Clear()`. Le flux est donc decoupe PAR MESSAGE D'ENTREE.
//
// Que ce soit du texte structure en lignes taguees est atteste independamment par
// `Runner.TextComparer` (`DoesLineMatchPattern`, `DoLinesDifferByTagValue`,
// `FindLineDifferences`) et par les detecteurs de triche `Runner.Cheats.*`, qui
// reconnaissent des motifs texte via `get_OutputStreamTextPattern`
// (`BlockDamageCheat`, `CritDamageModificationCheat`, `AbilityVariableAmountCheat`,
// `MoreDamageAndKillCheat`, ...) — donc degats, blocks, crits et valeurs de
// variable d'ability y figurent nommement.
//
// POURQUOI c'est disponible sur NOS runners, sans rien armer
// ----------------------------------------------------------
// `IdunBattle.Runner.IdunRunner$$Initialize` appelle inconditionnellement
// `IdunBattle.Runner.IdunRunner$$SetupReplayRecorder`. Tout runner que
// `buildRunner` initialise possede donc deja un `ReplayRecorder` actif, et
// `game/recorder.ts` tient deja l'objet `Replay` (il n'en lisait que `RngSeed`).
// Ce module ne fait qu'invoquer deux accesseurs de plus sur ce meme objet.
//
// COUT : nul tant que le RPC n'est pas appele — aucun Interceptor n'est pose.

import { findClass, findMethod, getFieldOffset } from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { getRunner } from "../game/runner-registry.js";
import { getReplayMi, runnerOff } from "../game/runner.js";
import { Ctx } from "../controller.js";

// --- Replay accessors ---

const replayClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattleLogic.Replay", "Replay");

const getWholeOutputStreamMi = replayClass
    ? findMethod(replayClass, "GetWholeBattleOutputStream") : null;
const getWholeRngEventsMi = replayClass
    ? findMethod(replayClass, "GetWholeBattleRngEvents") : null;

// `Replay.Messages` : List<ReplayStep>. Sert uniquement a rapporter le nombre
// de pas enregistres (diagnostic) — le flux lui-meme passe par l'accesseur
// manage, pas par une marche d'offsets.
const replayMessagesOff = replayClass
    ? getFieldOffset(replayClass, "Messages") : -1;

/** Taille par defaut du flux rendu, en caracteres UTF-16. */
const DEFAULT_MAX_CHARS = 4000000;

/**
 * Lit une System.String managee SANS le plafond de 500 caracteres de
 * `readIl2cppString` (helpers.ts) — l'output stream d'une bataille le depasse
 * de plusieurs ordres de grandeur, et ce plafond rend `null`, donc un flux
 * silencieusement absent.
 *
 * Layout System.String IL2CPP : length:int32 @ +0x10, chars UTF-16 @ +0x14.
 */
function readLargeManagedString(
    strPtr: NativePointer, maxChars: number,
): { text: string | null; length: number; truncated: boolean } {
    if (strPtr.isNull()) return { text: null, length: 0, truncated: false };
    const length = strPtr.add(0x10).readS32();
    if (length <= 0) {
        return { text: length === 0 ? "" : null, length, truncated: false };
    }
    const take = Math.min(length, maxChars);
    const text = strPtr.add(0x14).readUtf16String(take);
    return { text, length, truncated: take < length };
}

export interface ReplayOutputStreamResult {
    ok: boolean;
    runnerId: number;
    /** Trace textuelle complete de la bataille, ou null si illisible. */
    outputStream: string | null;
    /** Longueur REELLE en caracteres, meme si `outputStream` est tronque. */
    outputStreamLength: number;
    truncated: boolean;
    /** Nombre d'evenements PRNG sur toute la bataille, ou null si non mesure. */
    rngEventCount: number | null;
    /** Nombre de `ReplayStep` enregistres, ou null si non mesure. */
    stepCount: number | null;
    err: string | null;
}

function emptyResult(runnerId: number, err: string): ReplayOutputStreamResult {
    return {
        ok: false, runnerId, outputStream: null, outputStreamLength: 0,
        truncated: false, rngEventCount: null, stepCount: null, err,
    };
}

export function replayOutputStream(
    args?: { runnerId?: number; maxChars?: number },
): ReplayOutputStreamResult {
    const runnerId = args?.runnerId ?? -1;
    const maxChars = args?.maxChars ?? DEFAULT_MAX_CHARS;

    if (!replayClass) return emptyResult(runnerId, "Replay class not resolved");
    if (!getWholeOutputStreamMi || getWholeOutputStreamMi.ptr.isNull()) {
        return emptyResult(runnerId, "Replay.GetWholeBattleOutputStream not resolved");
    }
    if (!getReplayMi || getReplayMi.ptr.isNull()) {
        return emptyResult(runnerId, "ReplayRecorder.GetReplay not resolved");
    }

    const entry = getRunner(runnerId);
    const recorder = entry.runner.add(runnerOff.replayRecorder).readPointer();
    if (recorder.isNull()) {
        // Ne peut normalement pas arriver : IdunRunner.Initialize appelle
        // SetupReplayRecorder. Un null signale un runner NON initialise.
        return emptyResult(runnerId, "runner has no ReplayRecorder (not initialized?)");
    }

    const replay = invokeMethod(getReplayMi.info, recorder, null);
    if (replay.isNull()) {
        return emptyResult(runnerId, "ReplayRecorder.GetReplay returned null");
    }

    const streamPtr = invokeMethod(getWholeOutputStreamMi.info, replay, null);
    const { text, length, truncated } = readLargeManagedString(streamPtr, maxChars);

    let rngEventCount: number | null = null;
    if (getWholeRngEventsMi && !getWholeRngEventsMi.ptr.isNull()) {
        try {
            const list = invokeMethod(getWholeRngEventsMi.info, replay, null);
            // List<T> : _size @ +0x18.
            if (!list.isNull()) rngEventCount = list.add(0x18).readS32();
        } catch { /* diagnostic seulement — n'echoue pas la lecture du flux */ }
    }

    let stepCount: number | null = null;
    if (replayMessagesOff >= 0) {
        try {
            const msgs = replay.add(replayMessagesOff).readPointer();
            if (!msgs.isNull()) stepCount = msgs.add(0x18).readS32();
        } catch { /* diagnostic seulement */ }
    }

    return {
        ok: text !== null,
        runnerId,
        outputStream: text,
        outputStreamLength: length,
        truncated,
        rngEventCount,
        stepCount,
        err: text === null ? "output stream unreadable" : null,
    };
}

/** Etat de resolution des symboles — permet de constater la disponibilite
 *  du capteur sans monter de bataille. */
export function replayOutputStreamStatus(): Record<string, boolean | number> {
    return {
        replayClassResolved: !!replayClass,
        getWholeBattleOutputStreamResolved:
            !!getWholeOutputStreamMi && !getWholeOutputStreamMi.ptr.isNull(),
        getWholeBattleRngEventsResolved:
            !!getWholeRngEventsMi && !getWholeRngEventsMi.ptr.isNull(),
        getReplayResolved: !!getReplayMi && !getReplayMi.ptr.isNull(),
        replayMessagesOffset: replayMessagesOff,
        replayRecorderOffset: runnerOff.replayRecorder,
    };
}

export function register(ctx: Ctx): void {
    // Aucun Interceptor pose : ce module est purement a la demande.
    ctx.rpc.replayOutputStream = (a?: { runnerId?: number; maxChars?: number }) =>
        replayOutputStream(a);
    ctx.rpc.replayOutputStreamStatus = () => replayOutputStreamStatus();
}
