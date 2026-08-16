// replay-launch — OUVRIR un replay conservé dans le VIEWER du jeu.
//
// POURQUOI CE MODULE EXISTE, et pourquoi `invoquerCommande` ne suffisait pas
// -------------------------------------------------------------------------
// La chaîne exige de passer un OBJET d'un appel natif au suivant :
//
//   res    = ReplaySerializer$$DeserializeReplay(<json|base64>, verifyBattleVersion)
//   replay = res + 0x10
//   ViewCommandExecutor$$StartUserReplayMatch(replay) -> Boolean
//
// `argIl2cpp` (fsm-input.ts) REFUSE volontairement les arguments de type objet : il accepte
// chaîne, booléen, entier, {float}, {long}, {entityId}, {brut,octets}, null — rien d'autre.
// ⚠ `{brut, octets: 8}` ne conviendrait PAS : il alloue 8 octets CONTENANT le pointeur et
// passe l'adresse de l'allocation, donc le natif recevrait un objet bidon. Et `surPointeur`
// fixe l'INSTANCE, pas un argument. Le chaînage doit donc vivre côté natif — c'est tout ce
// que ce module ajoute, et c'est pourquoi il n'a pas sa place dans `view-command.ts`.
//
// CE QUE LE DÉCOMPILÉ DIT DE L'ENTRÉE (et qui la rend bien plus permissive que sa signature)
// ------------------------------------------------------------------------------------------
// `thor.Scripts.Idun.Source.IdunBattle.ReplaySerialization.ReplaySerializer$$DeserializeReplay`
// est déclarée `(base64DataString: String, verifyBattleVersion: String)`, mais son corps :
//
//   * teste `System.String$$StartsWith("{")` AVANT tout — une chaîne JSON est prise TELLE
//     QUELLE. Un `.replay.txt` (base64+gzip) passe par l'autre branche
//     (`System.Convert$$FromBase64String` + `Snowprint.source.Core.Zip.ZipUtil$$GzipDecompress`).
//     ⇒ nos replays ARCHIVÉS DÉCODÉS (`data/replays/**/*.json`) sont directement consommables,
//     sans ré-encodage ;
//   * met TOUT le contrôle de version sous `if (verifyBattleVersion != 0)` ⇒ passer `null`
//     le saute intégralement. C'est le défaut ici, et la version reste un argument EXPLICITE
//     pour qui veut la vérifier ;
//   * rend un `ReplayDeserializationResult` dont on lit deux champs :
//        +0x10 Replay   +0x18 ReplayDto   +0x20 json   +0x28 erreur (null = succès)
//
// LES DEUX PORTES, et pourquoi le choix n'est pas cosmétique
// ----------------------------------------------------------
// `idun.shared.commands.StartUserReplayCommand$$Execute` (derrière `StartUserReplayMatch`)
// dispatche sur le `GameMode` du replay et n'accepte que **0, 3, 4, 6, 11, 12**. Il rend
// `false` EN SILENCE pour 1 (PvP), 2 (Waves) et 5 (TreasureBeach) — aucune stratégie n'existe
// pour eux. `ViewCommandExecutor$$StartReplayMatch` (mode `debug`) n'a AUCUN filtre : il monte
// un `DebugReplayGameModeSource` puis `thor.Loader$$LoadBattle`. C'est la SEULE voie pour un
// replay `Waves` — donc pour nos onslaughts.
//
// N'INSTALLE AUCUN HOOK au register : un seul RPC, et il exige `confirmer: true`.

import {
    findClassAnywhere, findMethodByParamCount, readIl2cppString,
} from "../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
import { decoderRetour } from "./fsm-input.js";
import { executeurVivant } from "./view-command.js";
import { chargementEnCours } from "../game/loader.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

interface Refus { ok: false; error: string }
function refus(error: string): Refus { return { ok: false, error }; }
function estRefus(x: unknown): x is Refus {
    return typeof x === "object" && x !== null && (x as Refus).ok === false;
}

const NS_SER = "thor.Scripts.Idun.Source.IdunBattle.ReplaySerialization";
const OFF_REPLAY = 0x10;   // ReplayDeserializationResult.Replay
const OFF_ERREUR = 0x28;   // ReplayDeserializationResult.<erreur>  (null = succes)

/** Désérialise puis ouvre le replay. Rend un REFUS NOMMÉ à chaque étage — jamais un `ok`
 *  qui masquerait un `false` silencieux du dispatch. */
function lancer(json: string, mode: string, version: string | null): unknown {
    // ⚠ `thor.Loader` REFUSE EN SILENCE de charger pendant un chargement (#993). `null` =
    // NON MESURÉ : on ne conclut pas, donc on n'agit pas non plus.
    const enCours = chargementEnCours();
    if (enCours === true) {
        return refus("chargement de scène EN COURS -- `thor.Loader` refuserait EN SILENCE ; "
            + "l'appel est bloqué ici pour que ça se voie");
    }
    if (enCours === null) {
        return refus("état du chargeur NON MESURÉ (`loaderStatus` le détaille) -- on n'ouvre "
            + "pas une scène sans savoir si une autre charge");
    }

    const kSer = findClassAnywhere(NS_SER, "ReplaySerializer");
    if (!kSer) return refus(`${NS_SER}.ReplaySerializer INTROUVABLE dans ce build`);
    const miDes = findMethodByParamCount(kSer, "DeserializeReplay", 2);
    if (!miDes) return refus("`ReplaySerializer$$DeserializeReplay` à 2 paramètres INTROUVABLE");

    let res: NativePointer;
    try {
        res = invokeMethod(miDes.info, null, [
            createManagedString(json),
            version === null ? ptr(0) : createManagedString(version),
        ]);
    } catch (e) {
        return refus("DeserializeReplay a levé : " + (e as Error).message);
    }
    if (res.isNull()) return refus("DeserializeReplay a rendu null");

    // L'erreur AVANT le replay : un résultat porteur d'erreur peut quand même avoir un Replay
    // non nul, et le lire d'abord ferait passer un échec pour un succès.
    const errPtr = res.add(OFF_ERREUR).readPointer();
    if (!errPtr.isNull()) {
        return refus("le jeu REFUSE ce replay : "
            + (readIl2cppString(errPtr) ?? "<message illisible>"));
    }
    const replay = res.add(OFF_REPLAY).readPointer();
    if (replay.isNull()) {
        return refus("désérialisation sans erreur mais `Replay` NUL -- résultat incohérent, "
            + "on n'ouvre rien");
    }

    const exec = executeurVivant();
    if (estRefus(exec)) return exec;
    const kExec = (exec as NativePointer).readPointer();
    const nomMethode = mode === "debug" ? "StartReplayMatch" : "StartUserReplayMatch";
    const miStart = findMethodByParamCount(kExec, nomMethode, 1);
    if (!miStart) return refus(`\`ViewCommandExecutor$$${nomMethode}\` à 1 paramètre INTROUVABLE`);

    let out: NativePointer;
    try {
        out = invokeMethod(miStart.info, exec as NativePointer, [replay]);
    } catch (e) {
        return refus(nomMethode + " a levé : " + (e as Error).message);
    }
    const retour = decoderRetour(miStart.info, out);
    // ⚠ `StartUserReplayMatch` rend `false` SANS erreur quand le `GameMode` n'a pas de
    // stratégie (1 PvP, 2 Waves, 5 TreasureBeach). On le NOMME au lieu de rendre un `ok: true`
    // qui se lirait « ouvert ».
    if (retour.decode === true && retour.valeur === false) {
        return refus("`StartUserReplayMatch` a rendu FALSE -- le dispatch n'a pas de stratégie "
            + "pour le `GameMode` de ce replay (1 PvP, 2 Waves, 5 TreasureBeach sont refusés). "
            + "Réessayer avec `mode: \"debug\"`, qui n'a aucun filtre.");
    }
    return { ok: true, methode: nomMethode, retour,
             chargementApres: chargementEnCours() };
}

export function register(ctx: Ctx): void {
    /** `replayLancer({ json, mode?, verifyBattleVersion?, confirmer: true })`
     *
     *  `json` = le contenu d'un replay : JSON brut (commence par `{`) OU base64+gzip, les deux
     *  sont acceptés par le natif. `mode` = `"user"` (défaut, filtre par GameMode) ou
     *  `"debug"` (aucun filtre). `verifyBattleVersion` omis = AUCUNE vérification de version. */
    ctx.rpc.replayLancer = (body?: {
        json?: string; mode?: string; verifyBattleVersion?: string; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const json = body?.json;
        if (typeof json !== "string" || json.length === 0) {
            return refus("`json` manquant -- le contenu du replay (JSON ou base64+gzip)");
        }
        if (body?.confirmer !== true) {
            return refus("REFUS : `confirmer: true` exigé. Ce RPC OUVRE une bataille à l'écran "
                + "(il charge une scène) -- ce n'est pas un lecteur.");
        }
        const mode = body?.mode === "debug" ? "debug" : "user";
        const version = typeof body?.verifyBattleVersion === "string"
            ? body.verifyBattleVersion : null;
        return queueOnMainThread(() => lancer(json, mode, version));
    };
}
