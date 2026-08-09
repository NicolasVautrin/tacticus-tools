// net-capture — CE QUE LE CLIENT ENVOIE AU SERVEUR pour une bataille de campagne.
//
// POURQUOI. La forme des DTO se lit dans le binaire ; ce qu'ils PORTENT en vrai, non. On
// savait que `AEndLocationRequestDto` déclare `seed : Int32` et `replay : String` — on ne
// savait pas si `replay` part rempli, ni de quelle taille. Un champ déclaré et toujours nul
// et un champ déclaré et gros n'ont pas du tout les mêmes conséquences, et le décompilé ne
// les distingue pas.
//
// LES TROIS POINTS DE CAPTURE, tous FROIDS (une fois par bataille, jamais un hot path) :
//
//   `thor.Client.DTO.Events.GameEvents.Request.StartCampaignLocationRequestDto$$.ctor`
//       le lancement : `units` (le roster déclaré), `battleId`, l'identité du noeud.
//   `thor.Client.DTO.Events.GameEvents.Request.CompleteCampaignLocationRequestDto$$.ctor`
//   `thor.Client.DTO.Events.GameEvents.Request.FailCampaignLocationRequestDto$$.ctor`
//       la fin, victoire ou défaite : `seed`, `replay`, `rewards`, `heroDetails`...
//   `thor.Scripts.Idun.Source.IdunBattle.ReplaySerialization.ReplaySerializer$$SerializeReplay`
//       la taille du rejeu, mesurée à la source et indépendamment du DTO.
//
// ARMÉ À LA DEMANDE, JAMAIS AUTO-ARMÉ. Le module s'enregistre sans rien installer ; seul
// `netCaptureArm` pose les `Interceptor.attach`. C'est la leçon de `modifier-observe` : un
// capteur auto-armé finit par tourner pendant une session de jeu normale, et on ne s'en
// aperçoit qu'au crash.
//
// ON NE REND JAMAIS LE REJEU ENTIER. Il peut peser des mégaoctets et il n'a pas à traverser
// le pont RPC : on publie sa LONGUEUR et un préfixe court. La longueur est le chiffre qui
// répond à la question ; le contenu ne s'y ajouterait qu'en coût.

import { findClassAnywhere, findMethod } from "../il2cpp/helpers.js";
import { classFieldsDump } from "./ai-step/projection.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

/** Plafond du tampon : au-delà on cesse d'empiler plutôt que de grossir sans borne. Une
 *  bataille produit 2 entrées (lancement + fin), donc 200 couvre largement une session. */
const CAP = 200;
/** Ce qu'on garde d'une chaîne longue. Assez pour reconnaître un format (JSON ? base64 ?),
 *  trop peu pour peser. */
const PREFIXE = 240;

/** `System.String` IL2CPP : longueur @+0x10, caractères UTF-16 @+0x14. On lit la longueur
 *  SANS matérialiser la chaîne — un rejeu de plusieurs Mo deviendrait sinon une chaîne JS
 *  de plusieurs Mo pour en connaître la taille. */
function chaineInfo(p: NativePointer): { len: number; prefixe: string | null } | null {
    if (p.isNull()) return null;
    try {
        const len = p.add(0x10).readS32();
        if (len < 0 || len > 0x4000000) return { len: -1, prefixe: null };
        let prefixe: string | null = null;
        try { prefixe = p.add(0x14).readUtf16String(Math.min(len, PREFIXE)); }
        catch { /* prefixe reste null */ }
        return { len, prefixe };
    } catch { return null; }
}

/** Décode UN champ selon son type. Tri-état assumé : ce qu'on ne sait pas décoder est rendu
 *  comme `{ ref: <classe>, present: bool }`, jamais comme une valeur inventée.
 *
 *  ⚠ `List<T>` : `_size` est à +0x18 (layout .NET standard `_items@0x10, _size@0x18`). C'est
 *  le SEUL type composite qu'on décode, parce que c'est le seul dont le layout soit une
 *  certitude. `Dictionary<K,V>` n'est PAS décodé : son `_count` dépend de la version du
 *  runtime, et publier un compte deviné vaudrait moins que d'avouer qu'on ne l'a pas lu. */
function lireChamp(
    obj: NativePointer, champ: { name: string; offset: number; type: string },
): unknown {
    const a = obj.add(champ.offset);
    try {
        switch (champ.type) {
            case "Int32": return a.readS32();
            case "UInt32": return a.readU32();
            case "Int64": return a.readS64().toString();
            case "Boolean": return a.readU8() !== 0;
            case "Single": return a.readFloat();
            case "String": {
                const info = chaineInfo(a.readPointer());
                if (info === null) return null;
                // Une chaîne courte est rendue telle quelle ; une longue (le rejeu) ne l'est
                // jamais — on publie sa taille, ce qui est l'information utile.
                return info.len <= PREFIXE
                    ? info.prefixe
                    : { len: info.len, prefixe: info.prefixe, tronque: true };
            }
            default: {
                const p = a.readPointer();
                if (p.isNull()) return null;
                if (champ.type === "List`1") {
                    try { return { list: champ.type, size: p.add(0x18).readS32() }; }
                    catch { return { list: champ.type, size: null }; }
                }
                return { ref: champ.type, present: true };
            }
        }
    } catch { return undefined; }   // undefined = ILLISIBLE, distinct de `null` = champ nul
}

interface Entree { quoi: string; n: number; champs: Record<string, unknown> }

const tampon: Entree[] = [];
let compteur = 0;
const listeners: InvocationListener[] = [];
const layout: Record<string, unknown> = {};

/** Attache le ctor d'un DTO et publie ses champs, LUS PAR NOM après construction.
 *
 *  ⚠ On lit dans `onLeave`, pas dans `onEnter` : à l'entrée le ctor n'a encore rien écrit, et
 *  les arguments seuls perdraient ce que la classe de base a rempli. On mémorise donc `this`
 *  (= `args[0]`) à l'entrée pour le relire à la sortie. */
function attacherCtor(ns: string, cls: string): void {
    const klass = findClassAnywhere(ns, cls);
    if (!klass) { layout[cls] = "classe INTROUVABLE"; return; }
    const mi = findMethod(klass, ".ctor");
    if (!mi || mi.ptr.isNull()) { layout[cls] = "ctor NON RESOLU"; return; }
    const champs = classFieldsDump(klass);
    layout[cls] = { champs: champs.length };
    listeners.push(Interceptor.attach(mi.ptr, {
        onEnter(args) {
            (this as InvocationContext & { self?: NativePointer }).self = args[0];
        },
        onLeave() {
            const self = (this as InvocationContext & { self?: NativePointer }).self;
            if (!self || self.isNull() || tampon.length >= CAP) return;
            const out: Record<string, unknown> = {};
            for (const c of champs) {
                const v = lireChamp(self, c);
                if (v !== undefined) out[c.name] = v;
                else out[c.name] = "ILLISIBLE";
            }
            tampon.push({ quoi: cls, n: ++compteur, champs: out });
        },
    }));
}

export function register(ctx: Ctx): void {
    /** Arme les quatre captures. Idempotent : un second appel ne double pas les hooks.
     *  body: {} -> { ok, armes, layout } */
    ctx.rpc.netCaptureArm = (): Promise<unknown> => queueOnMainThread(() => {
        if (listeners.length > 0) return { ok: true, deja: true, armes: listeners.length, layout };
        const NS = "thor.Client.DTO.Events.GameEvents.Request";
        attacherCtor(NS, "StartCampaignLocationRequestDto");
        attacherCtor(NS, "CompleteCampaignLocationRequestDto");
        attacherCtor(NS, "FailCampaignLocationRequestDto");

        // La taille du rejeu, prise à la SOURCE — indépendante du DTO, donc capable de
        // contredire ce qu'il publie. Deux mesures valent mieux qu'une quand l'enjeu est
        // « le champ part-il rempli ? ».
        const rs = findClassAnywhere(
            "thor.Scripts.Idun.Source.IdunBattle.ReplaySerialization", "ReplaySerializer");
        const smi = rs ? findMethod(rs, "SerializeReplay") : null;
        if (!smi || smi.ptr.isNull()) {
            layout.SerializeReplay = rs ? "methode NON RESOLUE" : "classe INTROUVABLE";
        } else {
            layout.SerializeReplay = true;
            listeners.push(Interceptor.attach(smi.ptr, {
                onLeave(retval) {
                    if (tampon.length >= CAP) return;
                    const info = chaineInfo(retval as NativePointer);
                    tampon.push({
                        quoi: "SerializeReplay", n: ++compteur,
                        champs: info === null
                            ? { retour: "NON LISIBLE" }
                            : { len: info.len, prefixe: info.prefixe },
                    });
                },
            }));
        }
        // --- LE POINT DE FIL, et pourquoi il est INDISPENSABLE (#599-r2) ---
        //
        // Hooker le ctor du DTO prouve qu'il est CONSTRUIT avec un `replay` rempli. Il ne
        // prouve PAS qu'il part : la serialisation peut omettre le champ, la charge peut etre
        // tronquee, l'evenement peut ne jamais quitter la file. Ecrire << envoye >> sur cette
        // base serait la meme faute que lire un `ok:true` comme un effet.
        //
        // `Snowprint.ClientSdk.Web.WwwWebHelper$$PostString(url, postData, ...)` est l'endroit
        // ou la charge devient une requete HTTP. On y lit la TAILLE, et pour les gros corps on
        // CHERCHE la marque du rejeu (`H4sI` = base64 de l'entete gzip) : une taille seule
        // laisserait la question ouverte, la marque tranche.
        const wh = findClassAnywhere("Snowprint.ClientSdk.Web", "WwwWebHelper");
        const post = wh ? findMethod(wh, "PostString") : null;
        if (!post || post.ptr.isNull()) {
            layout.PostString = wh ? "methode NON RESOLUE" : "classe INTROUVABLE";
        } else {
            layout.PostString = true;
            listeners.push(Interceptor.attach(post.ptr, {
                onEnter(args) {
                    if (tampon.length >= CAP) return;
                    const champs: Record<string, unknown> = {};
                    try {
                        const u = chaineInfo(args[0]);
                        champs.url = u && u.len <= 400 ? u.prefixe : (u ? u.prefixe : null);
                    } catch { champs.url = null; }
                    const corps = chaineInfo(args[1]);
                    if (corps === null) { champs.corps = "NON LISIBLE"; }
                    else {
                        champs.len = corps.len;
                        champs.prefixe = corps.prefixe;
                        // On ne materialise le corps QUE s'il est gros — donc au plus une
                        // poignee de fois, sur les seules requetes qui pourraient le porter.
                        if (corps.len > 20000) {
                            try {
                                const plein = args[1].add(0x14).readUtf16String(corps.len) ?? "";
                                champs.contientMarqueGzip = plein.indexOf("H4sI") >= 0;
                                champs.posMarque = plein.indexOf("H4sI");
                            } catch { champs.contientMarqueGzip = null; }
                        } else {
                            champs.contientMarqueGzip = false;
                        }
                    }
                    tampon.push({ quoi: "PostString", n: ++compteur, champs });
                },
            }));
        }

        log("[net-capture] arme : " + listeners.length + " hook(s)");
        return { ok: true, armes: listeners.length, layout };
    });

    /** body: { reset?: true } -> { ok, count, entries } */
    ctx.rpc.netCaptureDump = (
        body?: { reset?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        const entries = tampon.slice();
        const out = { ok: true, arme: listeners.length > 0, count: tampon.length, plafond: CAP,
                      entries, layout };
        if (body?.reset) { tampon.length = 0; }
        return out;
    });

    ctx.rpc.netCaptureDisarm = (): Promise<unknown> => queueOnMainThread(() => {
        for (const l of listeners) { try { l.detach(); } catch { /* deja parti */ } }
        listeners.length = 0;
        return { ok: true, restant: tampon.length };
    });

    ctx.rpc.netCaptureStatus = (): Promise<unknown> => queueOnMainThread(() => ({
        ok: true, arme: listeners.length > 0, hooks: listeners.length,
        count: tampon.length, layout,
    }));
}
