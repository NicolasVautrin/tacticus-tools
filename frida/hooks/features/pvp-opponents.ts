// pvp-opponents — LES PROPOSITIONS DE L'ARENE, LUES SANS RIEN DEPENSER.
//
// POURQUOI CE MODULE EXISTE. Monter une sandbox « comme un duel d'Arene » demandait jusqu'ici
// d'ENTRER dans le combat pour capturer sa `BattleConfiguration` -- or entrer CONSOMME la
// tentative, et abandonner ne la rend pas. Les propositions, elles, sont deja en memoire des
// que l'ecran d'Arene a charge : il n'y a rien a payer pour les LIRE.
//
// LA CHAINE, ET POURQUOI C'EST CELLE-LA.
//
//     ViewCommandExecutor._pvpProgression        -> PvpProgression
//       PvpProgression._pvpProgressionData       -> PvpProgressionData
//         PvpProgressionData.latestOpponents     -> List<PvpEncounterProgressionData>
//
// ⚠ On passe par le `ViewCommandExecutor`, PAS par `PvpScreen._pvpProgression` (qui existe
// aussi). L'ecran n'est instancie que si l'utilisateur l'a ouvert ; l'executeur, lui, est
// capte au warmup et porte les 44 progressions du compte. Mesure du 2026-08-17, build
// `t6dpr4k06g` : `_pvpProgression` y est declare `IPvpProgression`, aux cotes de 40 autres
// `*Progression` -- c'est le porteur canonique, et `view-command.ts` en est le foyer unique.
//
// ⚠ AUCUN NATIF DU JEU N'EST INVOQUE ICI, et ce n'est pas un scrupule de style : c'est ce que
// le decompile a rendu POSSIBLE. `PvpProgression$$GetLatestOpponents` s'ecrit en entier :
//
//     if (*(param_1 + 0x10) != 0) { return *(*(param_1 + 0x10) + 0x78); }
//     FUN_1801f5460();                              // levee si `_pvpProgressionData` est nul
//
// soit deux dereferencements et une garde. Les deux offsets sont EXACTEMENT ceux que les
// metadonnees nomment (`_pvpProgressionData` a +0x10, `latestOpponents` a +0x78), donc lire
// les champs PAR NOM rend la meme valeur que l'appel, sans passer par `runtime_invoke`.
//
// ⚠ NE PAS CONFONDRE avec `PvpProgression$$RefreshOpponentsAsync`, qui rend une
// `Task<FetchResult<PvpData>>` et part sur le RESEAU. Ce module ne l'appelle pas, et ne doit
// jamais le faire : la difference se lit dans le type de retour, pas dans le nom.
//
// LECTURE SEULE : aucune ecriture, aucun envoi, aucune tentative consommee.

import { findClassAnywhere, getFieldOffset } from "../il2cpp/helpers.js";
// Le FOYER de la resolution du `ViewCommandExecutor` -- importe, jamais re-marche.
import { executeurVivant, Refus as RefusVue } from "./view-command.js";
// Le FOYER de la lecture de champs par NOM. Extrait d'ici quand `guild-boss-config.ts` a eu
// besoin des memes gardes : deux copies auraient diverge, et ce sont des gardes, pas du confort.
import {
    champInt, champPointeur, champTexte, elementsDeListe, estRefus, listeDeTextes, refus,
} from "./lecture-champs.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

/** La `PvpProgression` vivante, via le foyer `executeurVivant`. */
function progressionPvp(): NativePointer | RefusVue {
    const exec = executeurVivant();
    if (estRefus(exec)) return exec;
    const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
    if (!kExec) return refus("classe `idun.shared.commands.ViewCommandExecutor` introuvable");
    const off = getFieldOffset(kExec, "_pvpProgression");
    if (off < 0) {
        return refus("`_pvpProgression` ABSENT de `ViewCommandExecutor` sur ce build "
            + "-- chemin PERIME");
    }
    const p = (exec as NativePointer).add(off).readPointer();
    if (p.isNull()) {
        return refus("`ViewCommandExecutor._pvpProgression` est NUL -- l'executeur vit mais "
            + "n'a pas recu cette dependance");
    }
    return p;
}

/** Le resume d'UNE proposition : ce dont un montage sandbox a besoin, et rien de plus. */
function resumeProposition(enc: NativePointer): Record<string, unknown> {
    const adv = champPointeur(enc, "opponent");
    const advOk = !estRefus(adv) && !adv.isNull();
    return {
        // Le couple que `sandboxModeBuildBc` reclame.
        boardId: champTexte(enc, "boardId"),
        spawnPointsSet: champInt(enc, "spawnPointsSet"),
        ratingGain: champInt(enc, "ratingGain"),
        ratingLoss: champInt(enc, "ratingLoss"),
        adversaire: advOk ? {
            displayName: champTexte(adv as NativePointer, "displayName"),
            rating: champInt(adv as NativePointer, "rating"),
            level: champInt(adv as NativePointer, "level"),
            trophies: champInt(adv as NativePointer, "trophies"),
            machineOfWarLineup: champTexte(adv as NativePointer, "machineOfWarLineup"),
            lineup: (() => {
                const l = champPointeur(adv as NativePointer, "lineup");
                return estRefus(l) || l.isNull() ? null : listeDeTextes(l);
            })(),
        } : null,
        // Pourquoi l'adversaire manque, le cas echeant -- jamais un `null` muet.
        refusAdversaire: estRefus(adv) ? adv.error : (advOk ? null : "`opponent` NUL"),
    };
}

export function register(ctx: Ctx): void {
    /**
     * Les propositions d'Arene actuellement chargees.
     *
     * `{ json: true }` ajoute la serialisation complete (Newtonsoft) -- utile pour rejouer
     * hors ligne, mais lourde et faillible sur les types exotiques ; le RESUME, lui, est lu
     * champ par champ et ne depend d'aucun serialiseur.
     *
     * ⚠ TRI-ETAT sur le compte : `null` = PAS mesure (chaine rompue, et la raison est dite),
     * `0` = mesure et vide (l'Arene n'a rien charge). Les rabattre l'un sur l'autre ferait
     * lire « aucun adversaire » la ou il faut lire « ouvre l'ecran d'Arene ».
     */
    ctx.rpc.pvpOpponents = (body?: { json?: boolean }): Promise<unknown> =>
        queueOnMainThread(() => {
            const prog = progressionPvp();
            if (estRefus(prog)) return { ...prog, nombre: null };

            const data = champPointeur(prog as NativePointer, "_pvpProgressionData");
            if (estRefus(data)) return { ...data, nombre: null };
            if (data.isNull()) {
                return { ok: false, nombre: null,
                         error: "`_pvpProgressionData` est NUL -- c'est la garde meme que le "
                             + "natif teste avant de lever. Les donnees PvP ne sont pas "
                             + "chargees : ouvrir l'ecran d'Arene suffit (ouvrir ne consomme "
                             + "AUCUNE tentative ; seul un combat en consomme)." };
            }

            const liste = champPointeur(data, "latestOpponents");
            if (estRefus(liste)) return { ...liste, nombre: null };
            if (liste.isNull()) {
                return { ok: true, nombre: 0, propositions: [],
                         note: "`latestOpponents` est NUL : la progression PvP est chargee mais "
                             + "aucune proposition ne l'accompagne -- ouvrir l'ecran d'Arene." };
            }

            const els = elementsDeListe(liste);
            if (estRefus(els)) return { ...els, nombre: null };

            const propositions = els
                .filter((p) => !p.isNull())
                .map((p) => resumeProposition(p));

            const sortie: Record<string, unknown> = {
                ok: true,
                nombre: propositions.length,
                progression: (prog as NativePointer).toString(),
                propositions,
            };
            if (body?.json === true) {
                // Best-effort : `serializeToJson` rend `null` si Newtonsoft refuse le graphe.
                // On PUBLIE l'echec plutot que de le taire -- le resume reste valable.
                const j = serializeToJson(liste);
                sortie.json = j;
                sortie.jsonRefus = j === null
                    ? "serialisation Newtonsoft en echec -- le resume ci-dessus reste lu "
                        + "champ par champ, il ne depend pas d'elle"
                    : null;
            }
            return sortie;
        });
}
