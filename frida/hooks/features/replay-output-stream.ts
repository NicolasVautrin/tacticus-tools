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

import {
    class_get_element_class, class_is_valuetype, findClass, findClassAnywhere, findMethod,
    findMethodByParamCount, getFieldOffset, readMsgIdentity,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { getRunner, listRunners } from "../game/runner-registry.js";
import { getReplayMi, runnerOff } from "../game/runner.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { state } from "../game/state.js";
import { Ctx } from "../controller.js";

/** Le runner visé — REGISTRE si un `runnerId` est donné, sinon le runner VIVANT.
 *
 *  POURQUOI ce repli existe. Tout ce module passait par `getRunner(runnerId)`, qui ne connaît
 *  que le registre : sur une bataille jouée à l'écran, `replaySteps` rendait
 *  `runner -1 not found` — donc l'oracle le plus dense qu'on ait (le flux canonique que
 *  `Runner.ReplayValidator` compare caractère par caractère) était inatteignable là où on en
 *  a le plus besoin, c'est-à-dire sur une vraie partie. Mesuré le 2026-08-16 en voulant
 *  comparer deux runs live.
 *
 *  Le `recordReplay` d'un runner vivant n'est pas connu du registre : on rend `null`, et
 *  l'appelant retombe sur la MESURE native (`recorderPlayersOff`) -- jamais sur un `false`
 *  inventé. */
function resoudreRunner(
    runnerId: number,
): { runner: NativePointer; recordReplay: boolean | null } | null {
    if (runnerId >= 0) {
        try {
            const e = getRunner(runnerId);
            return { runner: e.runner, recordReplay: e.recordReplay === true };
        } catch { return null; }
    }
    const live = state.liveRunner;
    if (!live || live.isNull()) return null;
    return { runner: live, recordReplay: null };
}

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

    const entry = resoudreRunner(runnerId);
    if (!entry) {
        return emptyResult(runnerId, runnerId >= 0
            ? "runner " + runnerId + " not found"
            : "aucun runner VIVANT (pas de bataille montee) et aucun `runnerId` donne");
    }
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

// ---------------------------------------------------------------------------------------------
// LE REPLAY OFFICIEL — celui que le JEU produit, pas notre trace.
//
// ⚠ LA DISTINCTION A COUTE UN GEL, ET ELLE N'EST PAS COSMETIQUE. `replayOutputStream` ci-dessus
// rend la serialisation TEXTE des groupes racine du StreamDispatcher (`Group=... Action=...`) :
// c'est un artefact d'OBSERVATION, fait pour valider le port Python. Il n'est PAS rejouable --
// `ReplaySerializer$$DeserializeReplay` teste `StartsWith("{")` et attend le JSON du `ReplayDto`,
// ou du base64+gzip. Croire que la capture de fin de bataille produisait un replay a fait
// chercher un replay ailleurs, et lancer celui d'une AUTRE saison.
//
// L'artefact officiel se produit par la methode que le jeu emploie lui-meme :
//
//     ReplaySerializer$$SerializeReplay(replay : IdunBattleLogic.Replay.Replay,
//                                       optimize : Boolean) -> System.String
//
// STATIQUE (invoquee avec `this` nul), et son entree est le MEME objet `Replay` que
// `ReplayRecorder$$GetReplay` rend deja ici. Sa sortie est exactement ce que contiennent
// `data/replays/**/*.json` et ce que `replayLancer` consomme.
//
// ⚠ `optimize` est un TYPE VALEUR : il se passe par l'ADRESSE d'un octet, jamais par le mot
// lui-meme -- `false` partirait comme pointeur nul.

const NS_SER = "thor.Scripts.Idun.Source.IdunBattle.ReplaySerialization";
/** `undefined` = pas encore cherche ; `null` = cherche et INTROUVABLE (on ne recherche pas
 *  a chaque appel, mais on ne confond pas non plus les deux etats). */
let serializeMi: { info: NativePointer; ptr: NativePointer } | null | undefined;

function miSerializeReplay(): { info: NativePointer; ptr: NativePointer } | null {
    if (serializeMi !== undefined) return serializeMi;
    const k = findClassAnywhere(NS_SER, "ReplaySerializer");
    const mi = k ? findMethodByParamCount(k, "SerializeReplay", 2) : null;
    serializeMi = mi && !mi.ptr.isNull() ? mi : null;
    return serializeMi;
}

// ⚠ ON ANCRE LES CALLEES, JAMAIS `SerializeReplay` ELLE-MEME. Ancrer la methode qu'on invoque
// gele le jeu (regle du depot, payee). Les callees suffisent : la DERNIERE qui tire nomme
// l'etage ou l'`access violation accessing 0x0` se produit, et c'est tout ce qu'on cherche.
// Ordre du corps decompile : ShallowClone -> ReplayDto..ctor -> GzipCompress -> ToBase64String.
const ETAGES: Array<{ nom: string; ns: string; cls: string; methode: string }> = [
    { nom: "1.ShallowClone", ns: "IdunBattleLogic.Replay", cls: "Replay",
      methode: "ShallowClone" },
    { nom: "2.ReplayDto..ctor", ns: NS_SER, cls: "ReplayDto", methode: ".ctor" },
    { nom: "3.GzipCompress", ns: "Snowprint.source.Core.Zip", cls: "ZipUtil",
      methode: "GzipCompress" },
    { nom: "4.ToBase64String", ns: "System", cls: "Convert", methode: "ToBase64String" },
];
const etageListeners: Record<string, InvocationListener> = {};
const etageEtat: Record<string, unknown> = {};

export interface ReplayOfficielResult {
    ok: boolean;
    runnerId: number;
    /** Le replay OFFICIEL. Rejouable tel quel par `replayLancer`. */
    json: string | null;
    /** Longueur REELLE, meme si `json` est tronque. */
    longueur: number;
    tronque: boolean;
    optimise: boolean;
    stepCount: number | null;
    recorderArmed: boolean | null;
    err: string | null;
}

function vide(runnerId: number, err: string): ReplayOfficielResult {
    return { ok: false, runnerId, json: null, longueur: 0, tronque: false,
             optimise: false, stepCount: null, recorderArmed: null, err };
}

/** Le replay OFFICIEL du runner visé, serialise par le jeu lui-meme.
 *
 *  ⚠ A PRENDRE AVANT QUE LE RUNNER DISPARAISSE : a la fin de la bataille il n'est plus
 *  atteignable, et aucun sondage exterieur ne rattrape ca (cf. `replay-fin-auto`). */
export function replayOfficiel(
    args?: { runnerId?: number; maxChars?: number; optimize?: boolean },
): ReplayOfficielResult {
    const runnerId = args?.runnerId ?? -1;
    const maxChars = args?.maxChars ?? DEFAULT_MAX_CHARS;
    const optimize = args?.optimize === true;

    const mi = miSerializeReplay();
    if (!mi) {
        return vide(runnerId, "`ReplaySerializer$$SerializeReplay` INTROUVABLE (2 parametres) "
            + "-- chemin PERIME sur ce build");
    }
    if (!getReplayMi || getReplayMi.ptr.isNull()) {
        return vide(runnerId, "ReplayRecorder.GetReplay not resolved");
    }
    const entry = resoudreRunner(runnerId);
    if (!entry) {
        return vide(runnerId, runnerId >= 0
            ? "runner " + runnerId + " not found"
            : "aucun runner VIVANT (pas de bataille montee) et aucun `runnerId` donne");
    }
    const recorder = entry.runner.add(runnerOff.replayRecorder).readPointer();
    if (recorder.isNull()) {
        return vide(runnerId, "runner has no ReplayRecorder (not initialized?)");
    }
    const armed: boolean = recorderPlayersOff >= 0
        ? !recorder.add(recorderPlayersOff).readPointer().isNull()
        : entry.recordReplay === true;

    let replay: NativePointer;
    try { replay = invokeMethod(getReplayMi.info, recorder, null); }
    catch (e) { return vide(runnerId, "GetReplay a leve : " + (e as Error).message); }
    if (replay.isNull()) return vide(runnerId, "ReplayRecorder.GetReplay returned null");

    let stepCount: number | null = null;
    if (replayMessagesOff >= 0) {
        try {
            const msgs = replay.add(replayMessagesOff).readPointer();
            if (!msgs.isNull()) stepCount = msgs.add(0x18).readS32();
        } catch { /* diagnostic seulement */ }
    }

    // ⚠ ON N'EMPRUNTE PAS `il2cpp_runtime_invoke` ICI, ET C'EST MESURE. Il rend
    // `access violation accessing 0x0` sur cette methode-la, dans les DEUX branches d'`optimize`
    // (donc avant tout branchement du corps), alors que `mi.ptr` est non nul et que le recorder
    // est arme (`stepCount = 3`, flux a 37 Ko au meme instant). On appelle donc le corps compile
    // par l'ABI NATIVE que le jeu emploie lui-meme : pour une methode STATIQUE d'IL2CPP, c'est
    // `(arg0, arg1, MethodInfo*)` -- le `MethodInfo*` est un argument REEL, pas une commodite,
    // et c'est par lui que le prologue resout ses references de type (`FUN_1801f5220` sur les
    // trois DAT du corps decompile). Un `bool` passe alors PAR VALEUR, pas par adresse.
    let strPtr: NativePointer;
    try {
        const fn = new NativeFunction(mi.ptr, "pointer",
                                      ["pointer", "uint8", "pointer"]);
        strPtr = fn(replay, optimize ? 1 : 0, mi.info) as NativePointer;
    } catch (e) {
        // ⚠ ON GARDE `recorderArmed` ET `stepCount` DANS L'ECHEC. La version precedente les
        // jetait (retour `vide`), donc au moment ou ils tranchent -- « rien a serialiser » vs
        // « la serialisation echoue sur des donnees BIEN presentes » -- ils valaient `null`.
        return { ...vide(runnerId, "SerializeReplay a leve : " + (e as Error).message),
                 recorderArmed: armed, stepCount };
    }
    if (strPtr.isNull()) {
        return { ...vide(runnerId, "SerializeReplay a rendu NUL"),
                 recorderArmed: armed, stepCount };
    }

    const { text, length, truncated } = readLargeManagedString(strPtr, maxChars);
    // Un replay VIDE sur un recorder DESARME accuse le montage, pas la bataille -- meme
    // distinction que pour le flux, et pour la meme raison.
    const videEtDesarme = !armed && length === 0;
    return {
        ok: text !== null && !videEtDesarme && length > 0,
        runnerId, json: text, longueur: length, tronque: truncated,
        optimise: optimize, stepCount, recorderArmed: armed,
        err: text === null ? "replay illisible"
            : (videEtDesarme ? DISARMED_ERR
                : (length === 0 ? "replay VIDE alors que le recorder est arme" : null)),
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

// ── #477-r11 : la DECOUPE et le CANAL PRNG, lisibles ────────────────────────
//
// `replayOutputStream` rend le flux CONCATENE et un COMPTE d'evenements PRNG.
// Deux questions restaient donc structurellement hors de portee, et les deux
// comptent pour decider si un comparateur est constructible :
//
//   * QUEL message a produit QUEL pas. Mesure #477-r11 : sur deux boards, les
//     tours du joueur 12 produisent du TEXTE mais AUCUN pas -- conforme au
//     filtre de `IdunBattleLogic.Replay.ReplayRecorder$$Listen`. Cette mesure
//     a du passer par un DELTA de `stepCount` entre deux tours, faute de
//     pouvoir lire les pas. Avec `replaySteps`, elle se lit directement, et
//     `ReplayStep.InputMessage` NOMME le message.
//   * CE QUE CONTIENT un evenement PRNG. `IdunBattle.Utils.PRNG.RngEvent` porte
//     `Event` / `Output` / `StackTrace` / `Index` (dispositions mesurees en
//     live par le RPC `classFields`) -- c'est le second canal du validateur
//     natif (`Runner.RngEventComparer$$DoRngEventsDiffer`), et un compte n'en
//     dit rien.
//
// STRIDE : `RngEvent` est un `System.ValueType` (taille PUBLIEE 48 = BOXEE),
// donc INLINE dans le tableau du `List<T>`. Le stride n'est pas suppose : il
// vient de `il2cpp_class_get_element_class` + `il2cpp_class_get_instance_size`,
// et si l'un des deux manque le lecteur REFUSE au lieu de rendre du garbage
// plausible. `ReplayStep`, lui, est un `System.Object` => tableau de POINTEURS.

const replayStepClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattleLogic.Replay", "ReplayStep");
const stepOff = replayStepClass ? {
    index: getFieldOffset(replayStepClass, "Index"),
    turn: getFieldOffset(replayStepClass, "Turn"),
    inputMessage: getFieldOffset(replayStepClass, "InputMessage"),
    outputStream: getFieldOffset(replayStepClass, "OutputStream"),
    rngEvents: getFieldOffset(replayStepClass, "RngEvents"),
} : null;

const rngEventClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Utils.PRNG", "RngEvent");
/** Offsets rendus par `il2cpp_field_get_offset` pour un ValueType : BOXES
 *  (header 0x10 compris). On les garde tels quels et on lit l'element a
 *  `base - 0x10 + offset`, exactement comme le fait un boxage. */
const rngOff = rngEventClass ? {
    event: getFieldOffset(rngEventClass, "Event"),
    output: getFieldOffset(rngEventClass, "Output"),
    stackTrace: getFieldOffset(rngEventClass, "StackTrace"),
    index: getFieldOffset(rngEventClass, "Index"),
} : null;

const replayRecordedPlayersOff = replayClass
    ? getFieldOffset(replayClass, "RecordedPlayerIds") : -1;

const _class_get_instance_size = (() => {
    const m = Process.findModuleByName("GameAssembly.dll");
    const p = m ? m.findExportByName("il2cpp_class_get_instance_size") : null;
    return p ? new NativeFunction(p, "uint32", ["pointer"]) : null;
})();

/** `List<T>` IL2CPP : `_items` @0x10, `_size` @0x18 ; payload du tableau @0x20. */
function listInfo(list: NativePointer): { items: NativePointer; size: number } {
    return { items: list.add(0x10).readPointer(), size: list.add(0x18).readS32() };
}

function readStr(p: NativePointer, max = 4096): string | null {
    if (p.isNull()) return null;
    const n = p.add(0x10).readS32();
    if (n < 0) return null;
    return p.add(0x14).readUtf16String(Math.min(n, max));
}

export interface ReplayStepRow {
    index: number | null;
    turn: number | null;
    /** Type du message d'entree qui a CREE ce pas -- la reponse a « le
     *  decoupage suit-il un seul joueur ? » se lit ici, sans deltas. */
    messageNs: string | null;
    messageCls: string | null;
    outputStreamLength: number;
    rngEventCount: number | null;
}

export function replaySteps(
    args?: { runnerId?: number; maxSteps?: number },
): Record<string, unknown> {
    const runnerId = args?.runnerId ?? -1;
    const maxSteps = args?.maxSteps ?? 2000;
    if (!replayClass || !stepOff || stepOff.outputStream < 0) {
        return { ok: false, runnerId, steps: null,
                 err: "ReplayStep layout not resolved" };
    }
    if (!getReplayMi || getReplayMi.ptr.isNull()) {
        return { ok: false, runnerId, steps: null,
                 err: "ReplayRecorder.GetReplay not resolved" };
    }
    const entry = resoudreRunner(runnerId);
    if (!entry) {
        return { ok: false, runnerId, steps: null, err: runnerId >= 0
            ? "runner " + runnerId + " not found"
            : "aucun runner VIVANT (pas de bataille montee) et aucun `runnerId` donne" };
    }
    const recorder = entry.runner.add(runnerOff.replayRecorder).readPointer();
    if (recorder.isNull()) {
        return { ok: false, runnerId, steps: null, err: "runner has no ReplayRecorder" };
    }
    const armed: boolean = recorderPlayersOff >= 0
        ? !recorder.add(recorderPlayersOff).readPointer().isNull()
        : entry.recordReplay === true;
    const replay = invokeMethod(getReplayMi.info, recorder, null);
    if (replay.isNull()) {
        return { ok: false, runnerId, steps: null, err: "GetReplay returned null" };
    }

    // `Replay.RecordedPlayerIds` : la liste que `SetupReplayRecorder` a
    // calculee. La RENDRE evite de la deduire du seed BC -- c'est elle qui
    // determine quels messages deviennent des pas.
    let recordedPlayerIds: number[] | null = null;
    if (replayRecordedPlayersOff >= 0) {
        try {
            const l = replay.add(replayRecordedPlayersOff).readPointer();
            if (!l.isNull()) {
                const { items, size } = listInfo(l);
                recordedPlayerIds = [];
                for (let i = 0; i < size && i < 64; i++) {
                    recordedPlayerIds.push(items.add(0x20 + i * 4).readS32());
                }
            }
        } catch { /* diagnostic seulement */ }
    }

    const steps: ReplayStepRow[] = [];
    if (replayMessagesOff >= 0) {
        const msgs = replay.add(replayMessagesOff).readPointer();
        if (!msgs.isNull()) {
            const { items, size } = listInfo(msgs);
            for (let i = 0; i < size && i < maxSteps; i++) {
                // ReplayStep est une CLASSE => tableau de pointeurs.
                const st = items.add(0x20 + i * Process.pointerSize).readPointer();
                if (st.isNull()) continue;
                let msgNs: string | null = null, msgCls: string | null = null;
                try {
                    const im = stepOff.inputMessage >= 0
                        ? st.add(stepOff.inputMessage).readPointer() : NULL;
                    if (!im.isNull()) {
                        const id = readMsgIdentity(im);
                        msgNs = id.ns; msgCls = id.cls;
                    }
                } catch { /* laisse null */ }
                let osLen = 0;
                try {
                    const os = st.add(stepOff.outputStream).readPointer();
                    if (!os.isNull()) osLen = os.add(0x10).readS32();
                } catch { /* laisse 0 */ }
                let rngN: number | null = null;
                try {
                    if (stepOff.rngEvents >= 0) {
                        const l = st.add(stepOff.rngEvents).readPointer();
                        if (!l.isNull()) rngN = l.add(0x18).readS32();
                    }
                } catch { /* laisse null */ }
                steps.push({
                    index: stepOff.index >= 0 ? st.add(stepOff.index).readS32() : null,
                    turn: stepOff.turn >= 0 ? st.add(stepOff.turn).readS32() : null,
                    messageNs: msgNs, messageCls: msgCls,
                    outputStreamLength: osLen, rngEventCount: rngN,
                });
            }
        }
    }
    return {
        ok: true, runnerId, recorderArmed: armed, recordedPlayerIds,
        stepCount: steps.length, steps, err: null,
    };
}

export function replayRngEvents(
    args?: { runnerId?: number; max?: number; includeStackTrace?: boolean },
): Record<string, unknown> {
    const runnerId = args?.runnerId ?? -1;
    const max = args?.max ?? 500;
    const withStack = args?.includeStackTrace === true;
    if (!replayClass || !getWholeRngEventsMi || getWholeRngEventsMi.ptr.isNull()) {
        return { ok: false, runnerId, events: null,
                 err: "Replay.GetWholeBattleRngEvents not resolved" };
    }
    if (!rngEventClass || !rngOff || rngOff.event < 0) {
        return { ok: false, runnerId, events: null,
                 err: "RngEvent layout not resolved" };
    }
    if (!getReplayMi || getReplayMi.ptr.isNull()) {
        return { ok: false, runnerId, events: null,
                 err: "ReplayRecorder.GetReplay not resolved" };
    }
    const entry = resoudreRunner(runnerId);
    if (!entry) {
        return { ok: false, runnerId, events: null, err: runnerId >= 0
            ? "runner " + runnerId + " not found"
            : "aucun runner VIVANT (pas de bataille montee) et aucun `runnerId` donne" };
    }
    const recorder = entry.runner.add(runnerOff.replayRecorder).readPointer();
    if (recorder.isNull()) {
        return { ok: false, runnerId, events: null, err: "runner has no ReplayRecorder" };
    }
    const replay = invokeMethod(getReplayMi.info, recorder, null);
    if (replay.isNull()) {
        return { ok: false, runnerId, events: null, err: "GetReplay returned null" };
    }
    const list = invokeMethod(getWholeRngEventsMi.info, replay, null);
    if (list.isNull()) {
        return { ok: true, runnerId, count: 0, events: [], err: null };
    }
    const { items, size } = listInfo(list);

    // STRIDE mesure, jamais suppose : un `8` en dur rendrait du garbage
    // plausible sur un tableau de ValueType (cf. helpers.class_get_element_class).
    let stride = -1;
    try {
        const arrClass = items.readPointer();
        const elem = class_get_element_class
            ? (class_get_element_class(arrClass) as NativePointer) : NULL;
        if (!elem.isNull() && _class_get_instance_size && class_is_valuetype
            && class_is_valuetype(elem) !== 0) {
            // instance_size est BOXEE : le stride deboxe retranche le header.
            stride = (_class_get_instance_size(elem) as number) - 0x10;
        }
    } catch { /* stride reste -1 */ }
    if (stride <= 0) {
        return {
            ok: false, runnerId, count: size, events: null,
            err: "stride de RngEvent[] non mesurable (element_class ou "
                + "instance_size indisponible) — lecture REFUSEE plutot que devinee",
        };
    }

    const events: Array<Record<string, unknown>> = [];
    for (let i = 0; i < size && i < max; i++) {
        // Element INLINE : sa base deboxee est `items + 0x20 + i*stride`, et les
        // offsets de champ sont BOXES => on retranche 0x10.
        const base = items.add(0x20 + i * stride).sub(0x10);
        try {
            events.push({
                i,
                index: rngOff.index >= 0 ? base.add(rngOff.index).readS32() : null,
                event: readStr(base.add(rngOff.event).readPointer()),
                output: readStr(base.add(rngOff.output).readPointer()),
                ...(withStack && rngOff.stackTrace >= 0
                    ? { stackTrace: readStr(
                        base.add(rngOff.stackTrace).readPointer(), 2048) }
                    : {}),
            });
        } catch (e) {
            events.push({ i, err: String(e) });
        }
    }
    return { ok: true, runnerId, count: size, stride, events, err: null };
}

// --- LE DELTA D'UN SEUL `Apply` (#10040) ------------------------------------------------
//
// (!)LE DECOUPAGE EST FAIT PAR LE NATIF, PAS PAR NOUS.
//
// `ReplayRecorder._lastMessageOutputStream` -- le nom le dit -- est le tampon du DERNIER
// message. `IdunBattleLogic.Replay.ReplayRecorder$$Listen` commence par
// `SaveCurrentOutputStreamBufferToLastMessage(clearBuffer: true)` : il deverse le tampon
// dans le pas PRECEDENT, puis le VIDE, et seulement ensuite cree le pas courant. Or `Listen`
// est un PRE-listener d'`IdunBattle.Runner.IdunRunner$$Apply` (liste parcourue AVANT le
// processeur).
//
// Dans le job d'un `Apply`, la sequence est donc : vidange -> nos groupes -> retour. A la
// sortie, le tampon EST la sortie de ce seul `Apply`. Pas de decoupe a faire, pas d'attente,
// pas d'heuristique sur le texte.
//
// ⚠ SAUF SI LE MESSAGE EST FILTRE. `Listen` sort tot quand le `playerIndex` porte une valeur
// hors `_playerIndicesToRecord`, ou sur l'un de ses deux tests de type : ni vidange, ni pas
// cree, et notre sortie s'AJOUTE a l'ancienne. C'est le regime de TOUS les messages de l'IA,
// et c'est precisement pourquoi sa reponse s'accumule dans NOTRE pas.
//
// Le discriminant n'est donc pas une devinette sur le texte -- c'est `Replay.Messages.Count`.
// S'il a monte pendant l'`Apply`, notre `Listen` a tire, donc la vidange a eu lieu, donc tout
// le tampon est a nous. Sinon on coupe a la longueur relevee avant.
//
// ⚠ ET LE MEME APPEL FIGE LE PAS PRECEDENT. `Messages[n-1].OutputStream` est ecrit a cet
// instant, COMPLET -- reponse de l'IA comprise. C'est ce qui rend le verdict du coup
// precedent lisible SANS RIEN ATTENDRE : c'est notre envoi SUIVANT qui le declenche.

const recorderLastStreamOff = recorderClass
    ? getFieldOffset(recorderClass, "_lastMessageOutputStream") : -1;

// `System.Text.StringBuilder` est CHAINE par chunks : la longueur totale est
// `m_ChunkOffset + m_ChunkLength`, jamais `m_ChunkLength` seul (qui ne donne que le
// dernier maillon). Le texte, lui, passe par `ToString()` -- marcher la chaine a la main
// n'apporterait rien qu'un risque.
const sbClass = findClassAnywhere("System.Text", "StringBuilder");
const sbToStringMi = sbClass ? findMethodByParamCount(sbClass, "ToString", 0) : null;
const sbOff = sbClass ? {
    chunkLength: getFieldOffset(sbClass, "m_ChunkLength"),
    chunkOffset: getFieldOffset(sbClass, "m_ChunkOffset"),
} : null;

/** Le repere pris AVANT l'`Apply`. `null` sur un champ = PAS MESURE, jamais 0. */
export interface RepereRecorder {
    ok: boolean;
    error?: string;
    /** `Replay.Messages.Count` — le discriminant de vidange. */
    pas: number | null;
    /** `_lastMessageOutputStream.Length` — le point de coupe s'il n'y a PAS eu vidange. */
    longueur: number | null;
}

function recorderDe(runnerId: number): NativePointer | string {
    const entry = resoudreRunner(runnerId);
    if (!entry) {
        return runnerId >= 0 ? "runner " + runnerId + " introuvable"
            : "aucun runner VIVANT et aucun `runnerId` donne";
    }
    const rec = entry.runner.add(runnerOff.replayRecorder).readPointer();
    if (rec.isNull()) return "ce runner n'a pas de `ReplayRecorder`";
    return rec;
}

function longueurTampon(recorder: NativePointer): number | null {
    if (recorderLastStreamOff < 0 || !sbOff) return null;
    if (sbOff.chunkLength < 0 || sbOff.chunkOffset < 0) return null;
    try {
        const sb = recorder.add(recorderLastStreamOff).readPointer();
        if (sb.isNull()) return null;
        return sb.add(sbOff.chunkOffset).readS32() + sb.add(sbOff.chunkLength).readS32();
    } catch { return null; }
}

function comptePas(recorder: NativePointer): number | null {
    if (!getReplayMi || getReplayMi.ptr.isNull() || replayMessagesOff < 0) return null;
    try {
        const replay = invokeMethod(getReplayMi.info, recorder, null);
        if (replay.isNull()) return null;
        const msgs = replay.add(replayMessagesOff).readPointer();
        if (msgs.isNull()) return null;
        return msgs.add(0x18).readS32();     // List<T>._size
    } catch { return null; }
}

/** Les deux reperes, a prendre juste AVANT l'`Apply`, dans le MEME job. */
export function repereRecorder(runnerId: number): RepereRecorder {
    const rec = recorderDe(runnerId);
    if (typeof rec === "string") {
        return { ok: false, error: rec, pas: null, longueur: null };
    }
    return { ok: true, pas: comptePas(rec), longueur: longueurTampon(rec) };
}

export interface DeltaRecorder {
    ok: boolean;
    error?: string;
    /** Le texte produit par CET `Apply`, et lui seul. `null` = pas mesure. */
    texte: string | null;
    longueur: number | null;
    tronque: boolean;
    /** Comment la part a ete isolee — jamais a deviner par l'appelant.
     *  `vidange` : notre `Listen` a tire, tout le tampon est a nous.
     *  `suffixe` : message NON enregistre, on a coupe a la longueur d'avant. */
    branche: "vidange" | "suffixe" | null;
    pasAvant: number | null;
    pasApres: number | null;
    /** Le pas que CET `Apply` vient de FIGER — complet, reponse de l'IA comprise. C'est le
     *  verdict definitif du coup PRECEDENT, disponible sans aucune attente. */
    pasFige: { i: number; longueur: number; texte: string | null } | null;
}

function deltaVide(error: string): DeltaRecorder {
    return {
        ok: false, error, texte: null, longueur: null, tronque: false,
        branche: null, pasAvant: null, pasApres: null, pasFige: null,
    };
}

/**
 * Ce que l'`Apply` qui vient de tourner a produit — a appeler juste APRES lui, dans le
 * MEME job, avec le repere pris avant.
 */
export function deltaRecorder(
    runnerId: number, repere: RepereRecorder, maxChars?: number,
): DeltaRecorder {
    const plafond = maxChars ?? DEFAULT_MAX_CHARS;
    const rec = recorderDe(runnerId);
    if (typeof rec === "string") return deltaVide(rec);
    if (recorderLastStreamOff < 0) {
        return deltaVide("`ReplayRecorder._lastMessageOutputStream` non resolu -- champ "
            + "absent de ce build, pas de repli sur un offset mesure");
    }
    if (!sbToStringMi || sbToStringMi.ptr.isNull()) {
        return deltaVide("`System.Text.StringBuilder$$ToString` non resolu");
    }

    const out = deltaVide("");
    out.ok = true;
    delete out.error;
    out.pasAvant = repere.pas;
    out.pasApres = comptePas(rec);

    // LE PAS FIGE PAR NOTRE PROPRE `Listen`. Il n'existe que si la vidange a eu lieu, donc
    // sous exactement la meme condition que la branche `vidange`.
    const aVidange = out.pasAvant !== null && out.pasApres !== null
        && out.pasApres > out.pasAvant;
    if (aVidange && stepOff && stepOff.outputStream >= 0 && replayMessagesOff >= 0
        && getReplayMi && !getReplayMi.ptr.isNull()) {
        try {
            const replay = invokeMethod(getReplayMi.info, rec, null);
            const msgs = replay.isNull() ? NULL : replay.add(replayMessagesOff).readPointer();
            if (!msgs.isNull()) {
                const items = msgs.add(0x10).readPointer();
                const i = (out.pasAvant as number) - 1;
                if (!items.isNull() && i >= 0) {
                    const step = items.add(0x20 + i * Process.pointerSize).readPointer();
                    if (!step.isNull()) {
                        const sPtr = step.add(stepOff.outputStream).readPointer();
                        const lu = readLargeManagedString(sPtr, plafond);
                        out.pasFige = { i, longueur: lu.length, texte: lu.text };
                    }
                }
            }
        } catch { /* diagnostic : n'echoue pas la lecture du delta */ }
    }

    let texte: string | null = null;
    let longueurTotale = 0;
    try {
        const sb = rec.add(recorderLastStreamOff).readPointer();
        if (sb.isNull()) return deltaVide("`_lastMessageOutputStream` NUL");
        const sPtr = invokeMethod(sbToStringMi.info, sb, null);
        const lu = readLargeManagedString(sPtr, plafond);
        texte = lu.text;
        longueurTotale = lu.length;
        out.tronque = lu.truncated;
    } catch (e) {
        return deltaVide("lecture du tampon : " + (e as Error).message);
    }
    if (texte === null) return deltaVide("tampon illisible");

    // ⚠ SANS LES DEUX COMPTES, ON NE TRANCHE PAS. Choisir une branche « par defaut » ferait
    // rendre un texte plausible dont personne ne saurait s'il melange deux coups.
    if (out.pasAvant === null || out.pasApres === null) {
        out.ok = false;
        out.error = "`Replay.Messages.Count` NON MESURE avant ou apres -- la part de cet "
            + "`Apply` n'est pas isolable, et on ne devine pas";
        return out;
    }
    if (aVidange) {
        out.branche = "vidange";
        out.texte = texte;
        out.longueur = longueurTotale;
    } else {
        out.branche = "suffixe";
        const coupe = repere.longueur;
        if (coupe === null) {
            out.ok = false;
            out.error = "message NON enregistre (aucun pas cree) et longueur d'avant NON "
                + "MESUREE -- impossible de couper";
            return out;
        }
        out.texte = texte.slice(Math.min(coupe, texte.length));
        out.longueur = Math.max(0, longueurTotale - coupe);
    }
    return out;
}

export function register(ctx: Ctx): void {
    // Aucun Interceptor pose : ce module est purement a la demande.
    ctx.rpc.replayOutputStream = (a?: { runnerId?: number; maxChars?: number }) =>
        replayOutputStream(a);
    ctx.rpc.replayOutputStreamStatus = () => replayOutputStreamStatus();
    /** Le replay OFFICIEL du runner vivant (ou d'un `runnerId` du registre), serialise par le
     *  jeu. C'est le seul artefact que `replayLancer` sache relire -- `replayOutputStream`,
     *  lui, rend NOTRE TRACE, qui ne l'est pas. LECTURE PURE, aucun hook. */
    /** ⚠ ENFILE SUR LE THREAD PRINCIPAL, ET CE N'EST PAS UNE PRECAUTION DE STYLE. Mesure du
     *  2026-08-19 : appelee depuis le thread RPC, `SerializeReplay` rend
     *  `access violation accessing 0x0` -- capteurs d'etage a l'appui, la faute est
     *  `il2cpp_object_new(<classe ReplayDto>)` avec un pointeur de classe NUL. La MEME methode,
     *  appelee depuis la pompe (`replay-fin-auto`), rend 125 632 caracteres sans une erreur.
     *  L'allocation IL2CPP veut le thread principal ; le diagnostic « pas appelable hors
     *  contexte manage » etait trop large. */
    ctx.rpc.replayOfficiel = (a?: { runnerId?: number; maxChars?: number; optimize?: boolean }) =>
        queueOnMainThread(() => replayOfficiel(a));
    /** LOCALISER l'etage ou `SerializeReplay` tombe. Capteurs PURS sur ses callees -- ils ne
     *  lisent qu'un compteur, n'invoquent RIEN, et laissent la methode invoquee libre de tout
     *  ancrage. `{ armer: true }` puis `replayOfficiel`, puis relire : la derniere qui a tire
     *  borne la faute. `{ armer: false }` retire. */
    ctx.rpc.replayOfficielDiag = (body?: { armer?: boolean }): unknown => {
        if (body?.armer === false) {
            for (const k of Object.keys(etageListeners)) {
                try { etageListeners[k].detach(); } catch { /* best effort */ }
                delete etageListeners[k];
            }
            Interceptor.flush();
            return { ok: true, action: "retire", etages: etageEtat };
        }
        if (body?.armer !== true) {
            return { ok: true, lecture: true, arme: Object.keys(etageListeners).length,
                     etages: etageEtat,
                     note: "`armer: true` pose des capteurs PURS sur les callees de "
                         + "`SerializeReplay` -- jamais sur elle-meme (ancrer ce qu'on invoque "
                         + "gele le jeu)." };
        }
        for (const e of ETAGES) {
            if (etageListeners[e.nom] !== undefined) continue;
            const k = findClassAnywhere(e.ns, e.cls);
            if (!k) { etageEtat[e.nom] = { introuvable: "classe " + e.ns + "." + e.cls }; continue; }
            const mi = findMethod(k, e.methode);
            if (!mi || mi.ptr.isNull()) {
                etageEtat[e.nom] = { introuvable: "methode " + e.methode }; continue;
            }
            etageEtat[e.nom] = { fires: 0, ptr: mi.ptr.toString() };
            etageListeners[e.nom] = Interceptor.attach(mi.ptr, {
                onEnter() { (etageEtat[e.nom] as { fires: number }).fires++; },
            });
        }
        Interceptor.flush();
        return { ok: true, action: "arme", etages: etageEtat };
    };
    ctx.rpc.replaySteps = (a?: { runnerId?: number; maxSteps?: number }) =>
        replaySteps(a);
    ctx.rpc.replayRngEvents = (a?: {
        runnerId?: number; max?: number; includeStackTrace?: boolean;
    }) => replayRngEvents(a);
}
