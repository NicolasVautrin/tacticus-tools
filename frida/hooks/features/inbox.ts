// ---------------------------------------------------------------------------------------
// BOITE DE RECEPTION -- lire les envois et en reclamer le contenu, sans aucun ecran.
//
// POURQUOI CE MODULE EXISTE : les recompenses des codes promotionnels n'entrent PAS dans
// l'inventaire, elles atterrissent ici (`InboxScreen$$ShowPromoCodeRewards`). Un `Success`
// de `promoRedeem` ne vaut donc rien tant que l'envoi n'a pas ete reclame.
//
// LA CHAINE NATIVE :
//   thor.UserProgress.InboxProgression$$GetInboxItems()  -> List<IInboxItem>
//   thor.UserProgress.InboxProgression$$ClaimInboxItem(id:InboxItemGUID) -> List<LootReward>
// Le porteur est `ViewCommandExecutor._inboxProgression`, resolu PAR NOM comme les autres.
//
// CE QUI REND LE FILTRE POSSIBLE, ET C'EST LE POINT : un item porte ses recompenses AVANT
// d'etre reclame (`<rewards>k__BackingField`). `ClaimInboxItem` rend bien les `LootReward`,
// mais APRES coup -- trop tard pour decider. C'est la lecture du champ qui permet de dire
// << celui-la contient de la stamina, on n'y touche pas >>.
//
// ⚠ POURQUOI EPARGNER LA STAMINA. Elle se REMPLIT toute seule et PLAFONNE : la reclamer quand
// la jauge est pleine en jette la difference, definitivement. Les autres recompenses, elles,
// s'empilent sans perte. Ce module ne decide donc RIEN : il EXPOSE le type de chaque
// recompense (`IdunMetaLogic.Loot.RewardType`) et laisse l'appelant filtrer. Une politique
// codee ici serait invisible depuis le pilote -- meme faute que le seuil d'echecs de
// `promo-code.ts`, qui a coute 90 codes.
//
// ⚠ LES ITEMS SONT HETEROGENES. `GetInboxItems` rend des `IInboxItem` dont la classe CONCRETE
// varie (`PromoCodeUserInboxItem`, `DelayedRewardsInboxItem`, `GuildJoinRequestInboxItem`...).
// On ne resout donc PAS les offsets une fois pour toutes : on lit le `Il2CppClass*` de CHAQUE
// objet et on redemande ses offsets par NOM. Un champ absent d'une classe donnee rend `null`
// -- au sens NON MESURE, jamais rabattu sur une valeur par defaut.
//
// ⚠ DEUX TYPES VALEUR SUR LE CHEMIN, ET ILS ONT COUTE UNE PASSE. `InboxItemGUID` est une
// STRUCT (un seul champ `_value:String`) et `<rewards>` est un `List<RewardDto>` ou
// `RewardDto` est une STRUCT AUSSI. La premiere version dereferencait l'un et lisait l'autre
// a foulee 8 : elle rendait un COMPTE d'elements JUSTE avec des champs NULS, et des envois
// << sans identite >>. Rien n'avait l'air casse. Les primitives de `il2cpp/read.ts` ferment
// les deux trous -- foulee DERIVEE, offsets DEBOXES.
//
// ⚠ ON NE FABRIQUE PAS D'`InboxItemGUID`. La reclamation reutilise l'identite PORTEE PAR
// L'ITEM, relue sur une liste FRAICHE a l'instant ou l'on reclame. Construire un GUID
// reviendrait a deviner sa forme pour un gain nul, et la moindre erreur ferait reclamer un
// envoi qu'on n'a pas designe.
// ---------------------------------------------------------------------------------------

import { findClassAnywhere, findMethodByParamCount, getFieldOffset }
    from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
// Les primitives de LECTURE vivent dans `il2cpp/read.ts`, pas ici : parcourir un `List<T>`
// sans supposer sa foulee et deboxer l'offset d'un champ ne sont pas des besoins de boite de
// reception. Elles sont nees dans ce fichier et en sont sorties le jour meme -- meme
// trajectoire que la fabrique de delegues, sortie de `features/expedition-dispatch.ts`.
import {
    listElements, field, fieldIn, fieldAny, stringField, stringAt, boolField, className,
} from "../il2cpp/read.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";
import { executeurVivant, Refus as RefusVue } from "./view-command.js";

function isViewRefusal(x: NativePointer | RefusVue): x is RefusVue {
    return typeof x === "object" && x !== null && (x as RefusVue).ok === false;
}

/** Borne de surete sur une reclamation groupee : au-dela, c'est probablement une erreur
 *  d'appelant, pas une intention. */
const MAX_ENTRIES = 40;

/** L'`InboxProgression` vivante. Champ resolu PAR NOM a chaque appel -- un offset en dur se
 *  perime au build suivant, en silence. Lecture PURE : rien ne bouge a l'ecran du joueur. */
function inboxProgression(): NativePointer | null {
    try {
        const exec = executeurVivant();
        if (isViewRefusal(exec)) return null;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return null;
        const off = getFieldOffset(kExec, "_inboxProgression");
        if (off < 0) return null;              // ⚠ -1 est *truthy* : tester `< 0`
        const p = (exec as NativePointer).add(off).readPointer();
        return p.isNull() ? null : p;
    } catch { return null; }
}

interface RewardInfo { type: number | null; id: string | null; amount: number | null; }

interface InboxEntry {
    /** L'identite, en clair. `null` = illisible (donc NON reclamable par cette voie). */
    guid: string | null;
    cls: string | null;
    type: string | null;
    title: string | null;
    isRead: boolean | null;
    isClaimed: boolean | null;
    /** `null` = la classe ne porte pas de `<rewards>` -- a distinguer d'une liste VIDE, qui
     *  est une mesure. */
    rewards: RewardInfo[] | null;
    /** Renseigne quand la lecture a ete REFUSEE (foulee inconnue, accesseur absent...). Un
     *  `rewards: null` AVEC motif n'est pas << pas de recompense >> : c'est un aveu. */
    rewardsErr?: string;
}

/** `thor.UserProgress.Data.InboxItemGUID` -- une STRUCT a un seul champ `_value:String`.
 *  Resolue une fois, gardee : elle ne change pas au sein d'une session. */
let guidKlass: NativePointer | null | undefined;
function guidClass(): NativePointer | null {
    if (guidKlass === undefined) {
        guidKlass = findClassAnywhere("thor.UserProgress.Data", "InboxItemGUID");
    }
    return guidKlass;
}

/** L'identite d'un envoi, en clair.
 *
 *  ⚠ `InboxItemGUID` etant une STRUCT, le champ `<id>k__BackingField` ne porte PAS un pointeur
 *  vers un objet GUID : il porte la structure INLINE. La dereferencer comme un objet rendait
 *  `null` -- silencieusement, puisqu'un envoi sans identite se lit juste << non reclamable >>. */
function readGuid(item: NativePointer): string | null {
    const a = field(item, "<id>k__BackingField");
    const k = guidClass();
    if (!a || !k) return null;
    return stringAt(fieldIn(a, k, "_value"));
}

function readRewards(item: NativePointer): { rewards: RewardInfo[] | null; err?: string } {
    const a = field(item, "<rewards>k__BackingField");
    if (!a) return { rewards: null };                 // la classe n'en porte pas : NON MESURE
    let list: NativePointer;
    try { list = a.readPointer(); } catch { return { rewards: null, err: "liste illisible" }; }
    const el = listElements(list);
    if (el.err) return { rewards: null, err: el.err };
    if (!el.klass) return { rewards: [] };            // liste vide : c'est une MESURE
    const out: RewardInfo[] = [];
    for (const addr of el.addrs) {
        try {
            if (!el.inline && addr.isNull()) continue;
            // Deux formes NOMMEES coexistent : `RewardDto` (struct, minuscules) et `Reward`
            // (classe). Le conteneur decide laquelle on tient -- ce n'est pas une devinette.
            const aType = fieldAny(addr, el.klass, ["type", "Type"]);
            const aAmount = fieldAny(addr, el.klass, ["amount", "<Amount>k__BackingField"]);
            const aId = fieldAny(addr, el.klass, ["id", "Id"]);
            out.push({
                type: aType ? aType.readS32() : null,
                id: stringAt(aId),
                amount: aAmount ? aAmount.readS32() : null,
            });
        } catch { /* element suivant -- on rend ce qu'on a pu lire */ }
    }
    return { rewards: out };
}

function readEntry(item: NativePointer): InboxEntry {
    const r = readRewards(item);
    return {
        guid: readGuid(item), cls: className(item),
        type: stringField(item, "<type>k__BackingField"),
        title: stringField(item, "<title>k__BackingField"),
        isRead: boolField(item, "<read>k__BackingField"),
        isClaimed: boolField(item, "<claimed>k__BackingField"),
        rewards: r.rewards, rewardsErr: r.err,
    };
}

/** Les envois vivants, decodes. Rend aussi les POINTEURS bruts, dont `inboxClaim` a besoin
 *  pour retrouver l'identite sans refaire le tour. */
function listEntries(prog: NativePointer):
    { entries?: InboxEntry[]; items?: NativePointer[]; error?: string } {
    const kProg = findClassAnywhere("thor.UserProgress", "InboxProgression");
    if (!kProg) return { error: "classe `InboxProgression` absente de ce build" };
    const mi = findMethodByParamCount(kProg, "GetInboxItems", 0);
    if (!mi) return { error: "`GetInboxItems` sans parametre INTROUVABLE -- il existe une "
        + "surcharge a 1 parametre (`types`), on ne s'y replie PAS : elle filtrerait" };
    const list = invokeMethod(mi.info, prog, null);
    if (list.isNull()) return { error: "`GetInboxItems` a rendu null" };
    const el = listElements(list);
    if (el.err) return { error: "liste d'envois : " + el.err };
    // `List<IInboxItem>` est une liste de REFERENCES -- si elle se lisait comme des valeurs,
    // c'est que la forme a change, et on le DIT plutot que de decoder au hasard.
    if (el.inline) return { error: "les envois se lisent comme des types VALEUR -- forme "
        + "inattendue pour `List<IInboxItem>`, on refuse de decoder" };
    const items = el.addrs.filter((x) => !x.isNull());
    return { entries: items.map(readEntry), items };
}

export function register(ctx: Ctx): void {

    /** LISTER la boite de reception, recompenses comprises. Lecture PURE.
     *
     *  ⚠ Rend les types de recompense en ORDINAL (`IdunMetaLogic.Loot.RewardType`). Le nom se
     *  redemande au jeu par `dumpEnum` : une table recopiee ici se perimerait en silence. Le
     *  seul qui compte pour l'usage courant est `Stamina` -- et c'est a l'APPELANT de
     *  l'ecarter, pas a ce module. */
    ctx.rpc.inboxList = (): Promise<unknown> => queueOnMainThread(() => {
        const prog = inboxProgression();
        if (prog === null) {
            return { ok: false, error: "`InboxProgression` introuvable sur "
                + "`ViewCommandExecutor._inboxProgression`" };
        }
        const r = listEntries(prog);
        if (r.error) return { ok: false, error: r.error };
        return {
            ok: true, n: (r.entries ?? []).length, entries: r.entries,
            note: "`rewards[].type` est un ordinal de `IdunMetaLogic.Loot.RewardType` -- le "
                + "nommer par `dumpEnum`. `rewards: null` = la classe ne porte pas de "
                + "`<rewards>` (NON MESURE), a distinguer d'une liste vide.",
        };
    });

    /** RECLAMER des envois, designes par leur GUID.
     *
     *  ⚠ CE RPC ECRIT. `confirmer: true` exige, comme les portes d'Operations.
     *
     *  ⚠ IL NE FILTRE RIEN, ET C'EST DELIBERE. Il reclame EXACTEMENT les GUID qu'on lui donne.
     *  Le tri (epargner la stamina, par exemple) se fait chez l'appelant, sur ce que
     *  `inboxList` a rendu -- une politique enfouie ici serait invisible depuis le pilote.
     *
     *  ⚠ Les GUID sont re-resolus DANS CET APPEL, sur la liste fraiche : aucun pointeur n'est
     *  garde entre deux RPC. Un objet retenu d'un appel precedent aurait pu etre deplace par
     *  le GC ou invalide par une synchronisation serveur. */
    ctx.rpc.inboxClaim = (body?: { guids?: string[]; confirmer?: boolean; }):
        Promise<unknown> | unknown => {
        const guids = Array.isArray(body?.guids) ? (body as { guids: string[] }).guids : [];
        if (guids.length === 0) {
            return { ok: false, error: "`guids` manquant ou vide -- ce RPC n'ENUMERE PAS : "
                + "lire `inboxList`, filtrer, puis lui passer les identites retenues" };
        }
        if (guids.some((x) => typeof x !== "string" || !x)) {
            return { ok: false, error: "`guids` doit etre une liste de chaines non vides" };
        }
        if (guids.length > MAX_ENTRIES) {
            return { ok: false,
                     error: `${guids.length} > ${MAX_ENTRIES} envois -- borne de surete` };
        }
        if (body?.confirmer !== true) {
            return { ok: false, error: "REFUS : `confirmer: true` exige. Ce RPC ECRIT sur le "
                + "compte -- il est a un caractere de `inboxList`, qui ne fait que lire." };
        }
        return queueOnMainThread(() => {
            const prog = inboxProgression();
            if (prog === null) {
                return { ok: false, error: "`InboxProgression` introuvable sur "
                    + "`ViewCommandExecutor._inboxProgression`" };
            }
            const kProg = findClassAnywhere("thor.UserProgress", "InboxProgression");
            if (!kProg) return { ok: false, error: "classe `InboxProgression` absente" };
            const mi = findMethodByParamCount(kProg, "ClaimInboxItem", 1);
            if (!mi) {
                return { ok: false, error: "`ClaimInboxItem` a 1 parametre INTROUVABLE -- ne pas "
                    + "se replier sur `ClaimInboxItems`, qui prend des TYPES et reclamerait "
                    + "bien plus que ce qu'on a designe" };
            }

            // La liste FRAICHE : c'est elle qui fournit les identites a passer.
            const r = listEntries(prog);
            if (r.error || !r.items) return { ok: false, error: r.error ?? "liste indisponible" };
            // ⚠ L'ADRESSE de la structure `InboxItemGUID`, pas un pointeur d'objet : le
            //   parametre de `ClaimInboxItem` est un type VALEUR, donc `runtime_invoke` veut
            //   l'adresse des donnees.
            const byGuid = new Map<string, NativePointer>();
            for (const item of r.items) {
                const a = field(item, "<id>k__BackingField");
                if (!a) continue;
                const s = readGuid(item);
                if (s) byGuid.set(s, a);
            }

            const results: Array<{ guid: string; ok: boolean; reason?: string }> = [];
            for (const g of guids) {
                const idAddr = byGuid.get(g);
                if (!idAddr) {
                    // INTROUVABLE n'est pas un echec de reclamation : l'envoi a pu etre
                    // reclame entre le `inboxList` de l'appelant et maintenant.
                    results.push({ guid: g, ok: false, reason: "INTROUVABLE dans la liste "
                        + "fraiche -- deja reclame, ou identite perimee" });
                    continue;
                }
                log("[inbox] reclamation " + g
                    + " -- si le jeu gele, cette ligne est la derniere sortie");
                try {
                    invokeMethod(mi.info, prog, [idAddr]);
                    results.push({ guid: g, ok: true });
                } catch (ex) {
                    results.push({ guid: g, ok: false,
                        reason: String((ex as Error).message || ex).slice(0, 180) });
                }
            }
            const claimed = results.filter((x) => x.ok).length;
            return {
                ok: claimed > 0, requested: guids.length, claimed, results,
                note: "L'appel est passe -- ca ne prouve PAS que les recompenses sont creditees. "
                    + "Relire `inboxList` : c'est lui qui atteste (l'envoi disparait ou passe "
                    + "`isClaimed: true`). Et une reclamation part meme si le jeu gele ensuite.",
            };
        });
    };
}
