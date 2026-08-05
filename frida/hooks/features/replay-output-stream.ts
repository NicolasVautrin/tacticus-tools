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
// CE QU'IL FAUT ARMER — la version precedente de cette docstring etait FAUSSE
// ---------------------------------------------------------------------------
// Elle affirmait : « `IdunBattle.Runner.IdunRunner$$Initialize` appelle
// INCONDITIONNELLEMENT `IdunBattle.Runner.IdunRunner$$SetupReplayRecorder`, donc
// c'est disponible sur nos runners sans rien armer ». MESURE FAUSSE (#477-r1) :
// l'appel est sous garde.
//
//   `IdunRunner$$Initialize` :
//       if (options != null) {
//           if (options+0x10 != 0) SetupReplayRecorder(logger, timeSource,
//                                                      rng.GetSeed(), configuration);
//           if (options+0x11 != 0) AddReplayBugFinder(...);
//           ...
//       }
//
// `IdunBattle.Runner.IdunRunnerOptions$$.ctor` pose `+0x10 = 1` : le defaut du
// JEU est « on enregistre ». Mais `game/runner.ts` (`buildRunner`) ecrivait
// `0` a cet offset pour tous nos runners — d'ou un `Replay` vide, en silence.
// C'est desormais un choix explicite : `buildRunner(cfg, { recordReplay: true })`,
// expose par `initAndStart({ recordReplay: true })` et par
// `rl_duel build --record-replay`.
//
// CE QUI ARRIVE QUAND C'EST DESARME (mesure du 2026-08-04, avant correctif) :
// `_replayRecorder` est NON NUL quand meme — c'est le ctor du runner qui le cree,
// et `IdunBattleLogic.Replay.ReplayRecorder$$.ctor` alloue deja son `Replay`, sa
// liste `Messages` et son `StringBuilder`. `GetReplay` rend donc un objet valide
// dont `Messages` est VIDE => flux "" et 0 evenement PRNG, avec `ok:true`.
// Le champ `recorderArmed` du resultat existe pour que ce cas se DISE au lieu de
// se lire comme « la bataille n'a rien produit ».
//
// CE QUE `SetupReplayRecorder` FAIT, une fois arme :
//   1. filtre `BattleConfiguration.Player` (type
//      `IdunBattle.Configuration.PlayersConfiguration`) `.Players`, un
//      `SortedDictionary` : il ne garde que les CLES dont la valeur
//      (`IdunBattle.Configuration.PlayerConfiguration`) a un `PlayerType` qui
//      n'est ni 1 (AI) ni 2 (Environment). Sur notre seed BC, les trois joueurs
//      sont 11/12/13 de PlayerType 0/1/2 => la liste vaut [11], et RIEN dans le
//      harnais n'ecrit `PlayerType` (verifie sur tout le depot) ;
//   2. `ReplayRecorder.Init(logger, playerIndicesToRecord, timeSource)` ;
//   3. `ReplayRecorder.SetupBattle(seed, configuration)` ;
//   4. inscrit le recorder dans `IdunRunner._messageListeners` — la liste que
//      `IdunBattle.Runner.IdunRunner$$Apply` parcourt AVANT le processeur, en
//      appelant `ReplayRecorder$$Listen(message, state, playerIndex)` ;
//   5. l'abonne au `StreamCache` (=> `OnStreamCacheRootGroupFinished`) et au
//      PRNG (=> `HandleOnRngEventCreated`).
//
// FILTRAGE de `ReplayRecorder$$Listen`, a connaitre pour lire le flux :
//   - `playerIndex` vient de `StateExtensions.GetCurrentPlayerId(state)` (calcule
//     par `Apply`) ; si `HasValue` et hors `playerIndicesToRecord`, le message
//     n'est PAS transforme en `ReplayStep` ;
//   - deux types de message sont exclus d'office : celui construit par
//     `IdunBattle.Operations.SetupGameOperation$$ExecuteStartingMessages` et le
//     WRAPPER d'action IA construit par
//     `IdunBattle.Core.Services.AiControl$$ApplyAiMessage` (celui que
//     `IdunBattleLogic.Validation.InputInterceptor$$Intercept` deballe par `+0x10`).
//   => les sous-messages de l'IA ne creent PAS de pas ; leur sortie de stream,
//      elle, s'accumule et atterrit sur le pas SUIVANT.
//
// COUT : nul tant que le RPC n'est pas appele — aucun Interceptor n'est pose.
// Le cout d'ARMER, lui, est cote runner (retention du texte + un objet par tirage
// PRNG pour toute la bataille), d'ou le defaut a `false`.

import { findClass, findMethod, getFieldOffset } from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { getRunner, listRunners } from "../game/runner-registry.js";
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

// `ReplayRecorder._playerIndicesToRecord` : le SEUL des six champs du recorder
// qu'ecrit `IdunBattleLogic.Replay.ReplayRecorder$$Init` — et `Init` n'a qu'un
// appelant, `IdunBattle.Runner.IdunRunner$$SetupReplayRecorder`. Son nullite est
// donc la mesure NATIVE, sur l'objet lui-meme, de « l'enregistreur a-t-il ete
// arme sur ce runner ? » (le ctor du recorder, lui, n'y touche pas). Elle vaut
// aussi pour un runner que nous n'avons pas construit.
const recorderClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattleLogic.Replay", "ReplayRecorder");
const recorderPlayersOff = recorderClass
    ? getFieldOffset(recorderClass, "_playerIndicesToRecord") : -1;

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
    /** Ce runner a-t-il ete construit avec l'enregistreur ARME ? `false` =>
     *  `SetupReplayRecorder` n'a jamais tourne, le flux est vide PAR
     *  CONSTRUCTION (et non parce que la bataille n'aurait rien produit).
     *  `null` = pas mesure (runner inconnu du registre). */
    recorderArmed: boolean | null;
    err: string | null;
}

function emptyResult(runnerId: number, err: string): ReplayOutputStreamResult {
    return {
        ok: false, runnerId, outputStream: null, outputStreamLength: 0,
        truncated: false, rngEventCount: null, stepCount: null,
        recorderArmed: null, err,
    };
}

/** Panne NOMMEE : un flux vide sur un runner desarme n'est pas une mesure de
 *  bataille, c'est l'absence de capteur. Sans ce libelle, les deux se lisent
 *  pareil (`ok:true`, `""`, 0 pas, 0 evenement PRNG) — c'est exactement ce qui
 *  a coute la premiere confrontation de ce module. */
const DISARMED_ERR =
    "replay recorder DESARME sur ce runner : construit sans `recordReplay` "
    + "=> `IdunBattle.Runner.IdunRunner$$Initialize` a saute "
    + "`IdunBattle.Runner.IdunRunner$$SetupReplayRecorder`. Reconstruire avec "
    + "`initAndStart({ recordReplay: true })` / `rl_duel build --record-replay`.";

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
        // Le ctor du runner cree le recorder AVANT toute option : un null
        // signale un runner non construit par `buildRunner`, pas un
        // enregistrement desarme (celui-la se lit dans `recorderArmed`).
        return emptyResult(runnerId, "runner has no ReplayRecorder (not initialized?)");
    }

    // MESURE native d'abord (l'objet, pas notre registre) ; repli sur le drapeau
    // de construction si le champ n'est pas resolu — jamais un `false` invente.
    const armed: boolean = recorderPlayersOff >= 0
        ? !recorder.add(recorderPlayersOff).readPointer().isNull()
        : entry.recordReplay === true;

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

    // Un flux VIDE sur un runner DESARME accuse le montage, pas la bataille :
    // on le dit, et on ne rend pas `ok:true` — sinon l'appelant conclut « le
    // natif n'a rien produit », ce qui est faux.
    const emptyAndDisarmed = !armed && length === 0;
    return {
        ok: text !== null && !emptyAndDisarmed,
        runnerId,
        outputStream: text,
        outputStreamLength: length,
        truncated,
        rngEventCount,
        stepCount,
        recorderArmed: armed,
        err: text === null ? "output stream unreadable"
            : (emptyAndDisarmed ? DISARMED_ERR : null),
    };
}

/** Etat de resolution des symboles — permet de constater la disponibilite du
 *  capteur sans monter de bataille.
 *
 *  ⚠ QUATRE `true` NE PROUVENT RIEN sur le contenu du flux : ces champs disent
 *  que les accesseurs sont resolus, pas que l'enregistreur est ARME. Le
 *  2026-08-04 ils etaient tous `true` alors que TOUS les runners vivants
 *  etaient desarmes. C'est pour ca que `runners[]` est rendu ici : c'est LUI
 *  qui repond a « pourquoi le flux est-il vide ». */
export function replayOutputStreamStatus(): Record<string, unknown> {
    const runners = listRunners().map((r) => ({
        runnerId: r.runnerId, recordReplay: r.recordReplay, owner: r.owner,
    }));
    return {
        replayClassResolved: !!replayClass,
        getWholeBattleOutputStreamResolved:
            !!getWholeOutputStreamMi && !getWholeOutputStreamMi.ptr.isNull(),
        getWholeBattleRngEventsResolved:
            !!getWholeRngEventsMi && !getWholeRngEventsMi.ptr.isNull(),
        getReplayResolved: !!getReplayMi && !getReplayMi.ptr.isNull(),
        replayMessagesOffset: replayMessagesOff,
        replayRecorderOffset: runnerOff.replayRecorder,
        /** Offset de `ReplayRecorder._playerIndicesToRecord` — -1 = la mesure
         *  NATIVE de l'armement n'est pas disponible (repli sur le registre). */
        recorderPlayerIndicesOffset: recorderPlayersOff,
        /** Un par runner VIVANT : `recordReplay:false` => son flux sera vide,
         *  quoi qu'il se passe en bataille. */
        runners,
        armedRunnerCount: runners.filter((r) => r.recordReplay).length,
    };
}

export function register(ctx: Ctx): void {
    // Aucun Interceptor pose : ce module est purement a la demande.
    ctx.rpc.replayOutputStream = (a?: { runnerId?: number; maxChars?: number }) =>
        replayOutputStream(a);
    ctx.rpc.replayOutputStreamStatus = () => replayOutputStreamStatus();
}
