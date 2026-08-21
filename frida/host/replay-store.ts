// ECRIRE SUR DISQUE, TOUT DE SUITE, LE REPLAY CAPTE A LA FIN D'UNE BATAILLE.
//
// (!)POURQUOI CE MODULE EXISTE. `replay-fin-auto.ts` capte le replay a la derniere frame ou il
// est atteignable, et le gardait EN MEMOIRE du script injecte. `replay_recuperer.py` porte le
// constat en tete de fichier : << Rien ne l'en sortait : ca se faisait a la main >>. Mesure du
// 2026-08-21 : une bataille de guerre de guilde jouee A LA MAIN a bien ete captee
// (`dejaCapture: true`, 42 pas, `Finished`, 119 Ko) et n'existait NULLE PART sur disque, parce
// qu'aucune chaine Python ne tournait pour vider le tampon. Le replay etait recuperable ce
// jour-la ; il ne l'aurait plus ete apres un reinject.
//
// Le host tourne toujours, lui. Il ecrit donc a la seconde ou l'artefact existe.
//
// ⚠ OU IL ECRIT, ET POURQUOI LA. `data/` est VERSIONNE et ne porte que des ENTREES -- la regle du
// depot est << `data/` = ce qu'on LIT, `logs/` = ce qu'on ECRIT >>. Un replay n'est pas une
// sortie de run : c'est une ENTREE NEUVE, exactement du meme genre que celles deja rangees sous
// `data/replays/`. Il atterrit donc sous `data/replays/_captures/`, et le fait qu'il APPARAISSE
// dans `git status` est le garde-fou, pas un accident : il dit << un replay est arrive, decide
// si tu le gardes >>. Le classer sous son nom canonique (`<joueur>-f..z..p..s..-<seed>.json`)
// reste un geste delibere -- le replay seul ne porte ni le joueur ni la zone.
//
// ⚠ IL N'ECRASE JAMAIS. Deux batailles peuvent partager un seed (un rejeu impose le seed du
// replay d'origine !) : le nom porte donc aussi la frame, et un fichier deja present fait
// RENONCER en le disant, jamais un remplacement silencieux.

import { promises as fs } from "fs";
import path from "path";
import zlib from "zlib";
import { registerHandler } from "./router-messages.js";

const CAPTURES_DIR = path.resolve(process.cwd(), "..", "data", "replays", "_captures");

/** Le jeu rend le replay en `base64(gzip(JSON))`. On le rend LISIBLE sur disque : le decompile
 *  de `ReplaySerializer$$DeserializeReplay` teste `StartsWith("{")` AVANT tout, donc le JSON nu
 *  est relisible tel quel par le jeu -- la forme compressee n'apporte rien qu'on doive garder. */
function enJsonLisible(officiel: string): { json: string; seed: unknown; mode: unknown } {
    const clair = zlib.gunzipSync(Buffer.from(officiel, "base64")).toString("utf8");
    const obj = JSON.parse(clair) as Record<string, unknown>;
    const bc = obj.BattleConfiguration as Record<string, unknown> | undefined;
    return {
        json: JSON.stringify(obj, null, 1),
        seed: obj.RngSeed,
        mode: bc ? bc.GameMode : undefined,
    };
}

function morceauSur(v: unknown, defaut: string): string {
    const s = String(v ?? defaut);
    return s.replace(/[^A-Za-z0-9_.-]/g, "_") || defaut;
}

export function initReplayStore(): void {
    registerHandler("replay_fin", ({ sessionId, payload, envelope }) => {
        const officiel = payload.officiel;
        if (typeof officiel !== "string" || officiel.length === 0) return;

        // ⚠ LA CHARGE NE PART PAS AU NAVIGATEUR NI AU JOURNAL. 119 Ko de base64 par bataille
        // dans l'anneau WS n'apprennent rien a personne et noient le reste.
        envelope.payload = {
            t: "replay_fin", ecrit: true,
            raison: payload.raison, stageName: payload.stageName, winner: payload.winner,
            frameNo: payload.frameNo, stepCount: payload.stepCount, longueur: payload.longueur,
        };

        void (async () => {
            let lisible: { json: string; seed: unknown; mode: unknown };
            try {
                lisible = enJsonLisible(officiel);
            } catch (e) {
                // Un artefact illisible se DIT. Le jeter en silence rendrait la capture
                // indistinguable d'une absence de bataille.
                console.log("[replay-store] replay capte mais ILLISIBLE (base64/gzip/JSON) : "
                    + (e as Error).message);
                return;
            }
            const nom = [
                morceauSur(lisible.mode, "mode"),
                morceauSur(lisible.seed, "seed"),
                "f" + morceauSur(payload.frameNo, "0"),
            ].join("-") + ".json";
            const dst = path.join(CAPTURES_DIR, nom);
            try {
                await fs.mkdir(CAPTURES_DIR, { recursive: true });
                // `wx` : ECHOUE si le fichier existe. C'est ce qui garantit qu'on n'ecrase pas.
                await fs.writeFile(dst, lisible.json, { encoding: "utf8", flag: "wx" });
                console.log(`[replay-store] session ${sessionId} -- replay ECRIT : ${dst} `
                    + `(${lisible.json.length} car., ${payload.stepCount} pas, `
                    + `winner=${payload.winner})`);
            } catch (e) {
                const err = e as NodeJS.ErrnoException;
                if (err.code === "EEXIST") {
                    console.log(`[replay-store] replay DEJA PRESENT, rien ecrase : ${dst}`);
                    return;
                }
                console.log("[replay-store] ecriture IMPOSSIBLE : " + err.message);
            }
        })();
    });
    console.log(`[replay-store] captures de fin de bataille -> ${CAPTURES_DIR}`);
}
