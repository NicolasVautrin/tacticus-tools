// net-capture — TOUT CE QUE LE CLIENT ENVOIE AU SERVEUR, capté au point de fil.
//
// POURQUOI CE POINT-LÀ, ET PAS LES DTO. La première version de ce module ancrait les
// constructeurs de trois DTO de campagne (`Start`/`Complete`/`Fail`) plus
// `ReplaySerializer$$SerializeReplay`. Ça prouvait qu'un DTO était CONSTRUIT avec son champ
// `replay` rempli — pas qu'il PARTAIT : la sérialisation peut omettre un champ, la charge être
// tronquée, et `GameEventQueueProcesser$$AddToQueue` montre qu'il y a une FILE, donc que
// l'envoi est différé. Écrire « envoyé » sur cette base était la même faute qu'un `ok:true` lu
// comme un effet.
//
// Le point de fil est à la fois PLUS SÛR (c'est ce qui part réellement) et PLUS LARGE (il ne
// connaît pas les types : il attrape toutes les requêtes, pas seulement les trois DTO qu'on
// avait pensé à nommer). Les hooks de DTO sont donc RETIRÉS, pas complétés.
//
// Mesuré le 2026-08-10 (session 29, victoire sur `Campaign1_06`) — ce que la voie
// `PostString` a rendu :
//     POST api-live.loki.snowprintstudios.com/game-event/game3/   85 702 car, marque gzip @2982
//     POST ct-live.loki.snowprintstudios.com/ct/userId/...            658 car, pas de marque
// Le rejeu sérialisé faisait 82 324 caractères : le corps posté vaut donc le rejeu + 3 378 de
// d'enveloppe, et la marque tombe DANS le JSON, là où commence la valeur de `replay`.
//
// ⚠ TROIS PORTES, PAS UNE. `WwwWebHelper` expose `PostString(url, String, …)`,
// `PostBytes(url, Byte[], …)` et `PostData(url, Byte[], …)`. On les ancre TOUTES et le journal
// publie `via` : sans ça, « on capte tout ce qui part » resterait une hypothèse, et une
// requête passée par une porte non ancrée se lirait comme « rien n'est parti ». Si les trois
// voient la même charge, le journal le MONTRERA (doublons) — c'est un fait à mesurer, pas à
// deviner. Elles sont froides (une poignée d'appels par action), pas un hot path.
//
// ARMÉ À LA DEMANDE, jamais auto-armé.

import { findClassAnywhere, findMethod } from "../il2cpp/helpers.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

/** Plafond d'entrées : au-delà on cesse d'empiler plutôt que de grossir sans borne. */
const CAP = 200;
/** Ce qu'on garde d'un corps quand on ne le garde pas en entier. */
const PREFIXE = 400;
/** Budget TOTAL de caractères de corps conservés. Un corps de bataille pèse ~85 Ko ; ce budget
 *  en laisse passer une vingtaine, après quoi on ne garde que taille + préfixe et on COMPTE
 *  les omis. Un journal qui tronque en silence se lirait comme un journal complet. */
const BUDGET_CORPS = 2_000_000;

/** `System.String` IL2CPP : longueur @+0x10, caractères UTF-16 @+0x14. On lit la longueur SANS
 *  matérialiser la chaîne — connaître la taille d'un corps de 85 Ko ne doit pas coûter 85 Ko. */
function chaine(p: NativePointer): { len: number; lire: (n: number) => string | null } | null {
    if (p.isNull()) return null;
    try {
        const len = p.add(0x10).readS32();
        if (len < 0 || len > 0x4000000) return null;
        return {
            len,
            lire: (n: number) => {
                try { return p.add(0x14).readUtf16String(Math.min(len, n)); }
                catch { return null; }
            },
        };
    } catch { return null; }
}

/** `System.Byte[]` IL2CPP : longueur @+0x18, octets @+0x20. */
function octets(p: NativePointer): { len: number; lire: (n: number) => string | null } | null {
    if (p.isNull()) return null;
    try {
        const len = p.add(0x18).readS32();
        if (len < 0 || len > 0x4000000) return null;
        return {
            len,
            lire: (n: number) => {
                try {
                    const buf = p.add(0x20).readByteArray(Math.min(len, n));
                    if (buf === null) return null;
                    // Latin-1 suffit : on cherche un marqueur ASCII, pas à décoder de l'UTF-8.
                    return Array.from(new Uint8Array(buf))
                        .map((b) => String.fromCharCode(b)).join("");
                } catch { return null; }
            },
        };
    } catch { return null; }
}

interface Envoi {
    n: number; via: string; url: string | null; len: number | null;
    prefixe: string | null; corps: string | null; corpsOmis?: true;
}

const tampon: Envoi[] = [];
let compteur = 0;
let budgetRestant = BUDGET_CORPS;
let corpsOmis = 0;
const listeners: InvocationListener[] = [];
const layout: Record<string, unknown> = {};

function noter(
    via: string, urlPtr: NativePointer,
    charge: { len: number; lire: (n: number) => string | null } | null,
): void {
    if (tampon.length >= CAP) return;
    let url: string | null = null;
    try { const u = chaine(urlPtr); url = u ? u.lire(400) : null; } catch { /* url null */ }
    if (charge === null) {
        tampon.push({ n: ++compteur, via, url, len: null, prefixe: null, corps: null });
        return;
    }
    // On garde le corps ENTIER tant que le budget le permet — c'est lui la donnée. Au-delà,
    // taille + préfixe, et `corpsOmis` dit combien de fois on a renoncé.
    let corps: string | null = null;
    let omis: true | undefined;
    if (charge.len <= budgetRestant) {
        corps = charge.lire(charge.len);
        if (corps !== null) budgetRestant -= charge.len;
    } else { omis = true; corpsOmis++; }
    tampon.push({
        n: ++compteur, via, url, len: charge.len,
        prefixe: charge.lire(PREFIXE), corps,
        ...(omis ? { corpsOmis: omis } : {}),
    });
}

export function register(ctx: Ctx): void {
    /** Arme les trois portes. Idempotent.
     *  body: {} -> { ok, armes, layout } */
    ctx.rpc.netCaptureArm = (): Promise<unknown> => queueOnMainThread(() => {
        if (listeners.length > 0) return { ok: true, deja: true, armes: listeners.length, layout };
        const wh = findClassAnywhere("Snowprint.ClientSdk.Web", "WwwWebHelper");
        if (!wh) return { ok: false, error: "Snowprint.ClientSdk.Web.WwwWebHelper introuvable" };

        // `PostString` porte une String ; `PostBytes`/`PostData` un Byte[]. Le lecteur DIFFÈRE,
        // donc on ne peut pas les ancrer par une boucle unique sans se tromper de layout.
        const portes: Array<{ nom: string; parOctets: boolean }> = [
            { nom: "PostString", parOctets: false },
            { nom: "PostBytes", parOctets: true },
            { nom: "PostData", parOctets: true },
        ];
        for (const porte of portes) {
            const mi = findMethod(wh, porte.nom);
            if (!mi || mi.ptr.isNull()) { layout[porte.nom] = "NON RESOLUE"; continue; }
            layout[porte.nom] = true;
            try {
                listeners.push(Interceptor.attach(mi.ptr, {
                    onEnter(args) {
                        try {
                            noter(porte.nom, args[0],
                                  porte.parOctets ? octets(args[1]) : chaine(args[1]));
                        } catch { /* un capteur ne jette jamais */ }
                    },
                }));
            } catch { layout[porte.nom] = "ANCRAGE EN ECHEC"; }
        }
        Interceptor.flush();
        log("[net-capture] arme : " + listeners.length + " porte(s)");
        return { ok: true, armes: listeners.length, layout };
    });

    /** body: { reset?, depuis?: number, sansCorps?: true, contient?: string }
     *
     *  `sansCorps` rend le journal SANS les charges (utile pour lister ce qui est parti sans
     *  rapatrier des mégaoctets). `contient` filtre sur l'URL. */
    ctx.rpc.netCaptureDump = (body?: {
        reset?: boolean; depuis?: number; sansCorps?: boolean; contient?: string;
    }): Promise<unknown> => queueOnMainThread(() => {
        const depuis = typeof body?.depuis === "number" ? body.depuis : 0;
        const filtre = typeof body?.contient === "string" && body.contient
            ? body.contient.toLowerCase() : null;
        let entries = tampon.filter((e) => e.n > depuis);
        if (filtre) entries = entries.filter((e) => (e.url ?? "").toLowerCase().includes(filtre));
        if (body?.sansCorps) {
            entries = entries.map((e) => ({ ...e, corps: null }));
        }
        const out = {
            ok: true, arme: listeners.length > 0, count: tampon.length, plafond: CAP,
            corpsOmis, budgetRestant, entries, layout,
        };
        if (body?.reset) {
            tampon.length = 0; corpsOmis = 0; budgetRestant = BUDGET_CORPS;
        }
        return out;
    });

    ctx.rpc.netCaptureDisarm = (): Promise<unknown> => queueOnMainThread(() => {
        for (const l of listeners) { try { l.detach(); } catch { /* deja parti */ } }
        listeners.length = 0;
        return { ok: true, restant: tampon.length };
    });

    ctx.rpc.netCaptureStatus = (): Promise<unknown> => queueOnMainThread(() => ({
        ok: true, arme: listeners.length > 0, portes: listeners.length,
        count: tampon.length, corpsOmis, budgetRestant, layout,
    }));
}
