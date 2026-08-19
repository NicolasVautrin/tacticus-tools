// guild-war-leaderboard — LE CLASSEMENT DE SAISON, CAPTE AU VOL, SANS UN OCTET RESEAU.
//
// A QUOI CA SERT, CONCRETEMENT
// -----------------------------
// Le classement de saison EST la liste des guildes qui jouent reellement la guerre de guilde,
// ordonnee. C'est donc l'outil de recherche d'une guilde active -- une question a laquelle le
// gameconfig NE REPOND PAS : les criteres d'eligibilite d'une guilde au GW viennent du serveur
// (`GuildWarProgression$$GetGuildWarEligibilityConfig` -> `GuildWarEligibilityDto`), pas de la
// config embarquee.
//
// POURQUOI ON OBSERVE, ET POURQUOI ON NE DECLENCHE PAS
// -----------------------------------------------------
// Deux methodes PRODUISENT ce classement, et les DEUX passent par le reseau :
//     GuildWarProgression$$FetchSeasonLeaderboard(season, onFinish)
//     GuildWarProgression$$FetchLeagueLeaderboard(onFinish)
//         -> thor.Client.Services.PlayerEventService$$GetGuildWarLeagueLeaderboard
// Les invoquer emettrait une requete. Ce module ne les appelle JAMAIS : il ancre le point ou le
// resultat ARRIVE, donc il ne capture que ce que le jeu allait chercher de toute facon, quand
// l'utilisateur ouvre l'ecran. Zero requete ajoutee, zero ecriture.
//
// OU EXACTEMENT, ET POURQUOI CE POINT-LA
// ----------------------------------------
// `GuildWarProgression$$CacheGuildDetails` est le convergent : le decompile (surcharge a deux
// parametres) montre qu'il recoit `myGuildId` et la `List<GuildWarLeaderboardEntryDto>`
// COMPLETE, l'enumere, et n'en retient qu'un `thor.UserProgress.Data.DisplayableGuild` par
// entree, ajoute a la collection `this+0x58`.
//
// ⚠ C'EST POURQUOI ON N'ANCRE PAS LE CACHE, ET C'EST LA LE POINT : le cache ne garde que les
// guildes. La POSITION, le score et la section sont dans les entrees SOURCE, que
// `CacheGuildDetails` lit puis laisse tomber. Lire `this+0x58` apres coup rendrait une liste de
// guildes SANS classement -- c'est-a-dire precisement pas un classement. Il faut donc prendre
// l'argument AU PASSAGE.
//
// LECTURE PURE : `onEnter` seulement, aucune ecriture, aucun `retval.replace`, aucune invocation
// de methode du jeu. La serialisation passe par le serialiseur Newtonsoft deja embarque.

import { findClassAnywhere, findMethodByParamClasses } from "../il2cpp/helpers.js";
import { isSerializerReady, serializeToJson } from "../il2cpp/serializer.js";
import { estRefus, refus } from "./lecture-champs.js";
import { Ctx } from "../controller.js";

const NS = "Idun.Source.IdunMeta.Logic.UserProgress.GuildWars";
const CLS = "GuildWarProgression";

interface Capture {
    /** `season` quand la capture vient de la surcharge saison, sinon `null` — NON DEVINE. */
    origine: string;
    /** L'identifiant de MA guilde tel que le jeu l'a passe. `null` = sans guilde. */
    monGuildId: string | null;
    /** Le classement, tel que serialise. `null` si la serialisation a echoue (`erreur` dit
     *  pourquoi) — jamais une liste vide qui se lirait comme « classement vide ». */
    entrees: unknown;
    nbEntrees: number | null;
    erreur: string | null;
    frameVue: number;
}

const captures: Capture[] = [];
const CAPTURES_MAX = 4;
let listeners: InvocationListener[] = [];
let arme = false;
let refusAncrage: string | null = null;
let firesVus = 0;

/** Serialise un objet gere en JSON. Rend l'ERREUR plutot qu'un vide : un classement absent et un
 *  classement illisible ne doivent pas se lire pareil. */
function enJson(p: NativePointer): { valeur: unknown; erreur: string | null } {
    if (p.isNull()) return { valeur: null, erreur: "l'argument est NUL" };
    if (!isSerializerReady()) {
        return { valeur: null, erreur: "serialiseur Newtonsoft PAS PRET (amorce incomplet ?)" };
    }
    try {
        const j = serializeToJson(p);
        if (j === null) return { valeur: null, erreur: "serialisation NULLE" };
        return { valeur: JSON.parse(j), erreur: null };
    } catch (e) {
        return { valeur: null, erreur: (e as Error).message };
    }
}

function compter(v: unknown): number | null {
    return Array.isArray(v) ? v.length : null;
}

function armer(veut: boolean): Record<string, unknown> {
    if (!veut) {
        for (const l of listeners) { try { l.detach(); } catch { /* best effort */ } }
        listeners = [];
        arme = false;
        return { ok: true, arme: false, captures: captures.length };
    }
    if (arme) return { ok: true, arme: true, captures: captures.length, note: "deja arme" };

    const k = findClassAnywhere(NS, CLS);
    if (!k || k.isNull()) {
        refusAncrage = "classe `" + NS + "." + CLS + "` introuvable sur ce build";
        return { ok: false, arme: false, error: refusAncrage };
    }

    // ⚠ DEUX SURCHARGES, et elles ne portent PAS la meme chose. On les prend par la CLASSE de
    // leurs parametres, jamais par l'arite : `findMethodByParamCount` rendrait l'une OU l'autre
    // sans le dire, et la surcharge `GuildWarLeaderboardDto` ne donne pas `myGuildId`.
    const cibles: Array<{ nom: string; params: Array<string | null>; iId: number; iListe: number }> = [
        // (myGuildId, List<GuildWarLeaderboardEntryDto>) — celle que le decompile etablit.
        { nom: "CacheGuildDetails(String, List)", params: ["String", "List`1"], iId: 1, iListe: 2 },
        // (GuildWarLeaderboardDto) — le DTO entier ; pas de `myGuildId` separe.
        { nom: "CacheGuildDetails(GuildWarLeaderboardDto)",
          params: ["GuildWarLeaderboardDto"], iId: -1, iListe: 1 },
    ];

    const poses: string[] = [];
    for (const c of cibles) {
        const mr = findMethodByParamClasses(k, "CacheGuildDetails", c.params);
        if (!mr || mr.ptr.isNull()) continue;
        listeners.push(Interceptor.attach(mr.ptr, {
            onEnter(args) {
                firesVus++;
                try {
                    let monId: string | null = null;
                    if (c.iId >= 0) {
                        const r = enJson(args[c.iId]);
                        monId = typeof r.valeur === "string" ? r.valeur : null;
                    }
                    const j = enJson(args[c.iListe]);
                    captures.push({
                        origine: c.nom,
                        monGuildId: monId,
                        entrees: j.valeur,
                        nbEntrees: compter(j.valeur),
                        erreur: j.erreur,
                        frameVue: firesVus,
                    });
                    if (captures.length > CAPTURES_MAX) captures.shift();
                } catch (e) {
                    captures.push({
                        origine: c.nom, monGuildId: null, entrees: null, nbEntrees: null,
                        erreur: (e as Error).message, frameVue: firesVus,
                    });
                }
            },
        }));
        poses.push(c.nom);
    }

    if (poses.length === 0) {
        refusAncrage = "aucune surcharge de `CacheGuildDetails` resolue -- chemin PERIME sur ce "
            + "build ; ne PAS se replier sur l'arite, les deux surcharges ne portent pas la "
            + "meme chose";
        return { ok: false, arme: false, error: refusAncrage };
    }
    refusAncrage = null;
    arme = true;
    return { ok: true, arme: true, ancrees: poses };
}

export function register(ctx: Ctx): void {
    /** ARMER l'observation. N'EMET AUCUNE REQUETE : il faut ensuite OUVRIR l'ecran de classement
     *  dans le jeu, c'est ce geste-la qui declenche le fetch, comme d'habitude. */
    ctx.rpc.guildWarLeaderboardArmer = (body?: { armer?: boolean }): unknown =>
        armer(body?.armer !== false);

    /** LE CLASSEMENT CAPTE. `total: 0` avec `arme: true` veut dire « rien n'est encore passe » —
     *  ouvrir l'ecran de classement dans le jeu. Ce n'est PAS « le classement est vide ». */
    ctx.rpc.guildWarLeaderboard = (body?: { brut?: boolean }): unknown => {
        const derniere = captures.length ? captures[captures.length - 1] : null;
        if (derniere === null) {
            return {
                ok: true, arme, refusAncrage, total: 0, firesVus, capture: null,
                note: arme
                    ? "ARME mais RIEN CAPTE : ouvrir l'ecran de classement de guerre de guilde "
                        + "dans le jeu. Ce module n'emet aucune requete lui-meme."
                    : "NON ARME : appeler `guildWarLeaderboardArmer` d'abord.",
            };
        }
        return {
            ok: true, arme, refusAncrage, total: captures.length, firesVus,
            capture: {
                origine: derniere.origine,
                monGuildId: derniere.monGuildId,
                nbEntrees: derniere.nbEntrees,
                erreur: derniere.erreur,
                entrees: body?.brut === false ? null : derniere.entrees,
            },
        };
    };
}
