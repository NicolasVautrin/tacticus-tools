// ---------------------------------------------------------------------------------------
// BOITE DE RECEPTION -- lire les envois et en reclamer le contenu, sans aucun ecran.
//
// POURQUOI CE MODULE EXISTE : les recompenses des codes promotionnels n'entrent PAS dans
// l'inventaire, elles atterrissent ici (`InboxScreen$$ShowPromoCodeRewards`). Un `Success`
// de `promoRedeem` ne vaut donc rien tant que l'envoi n'a pas ete reclame.
//
// LA CHAINE NATIVE :
//   thor.UserProgress.InboxProgression$$GetInboxItems()        -> List<IInboxItem>
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
// objet et on redemande ses offsets par NOM. Un champ absent d'une classe donnee est rendu
// `null` -- au sens NON MESURE, jamais rabattu sur une valeur par defaut.
//
// ⚠ ON NE FABRIQUE PAS D'`InboxItemGUID`. La reclamation reutilise l'objet identite PORTE PAR
// L'ITEM (`<id>k__BackingField`), lu a l'instant ou l'on reclame. Construire un GUID
// reviendrait a deviner sa forme (classe ? structure ?) pour un gain nul, et la moindre erreur
// de forme ferait reclamer un envoi qu'on n'a pas designe.
// ---------------------------------------------------------------------------------------

import { findClassAnywhere, findMethodByParamCount, getFieldOffset, readIl2cppString }
    from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";
import { executeurVivant, Refus as RefusVue } from "./view-command.js";

function estRefusVue(x: NativePointer | RefusVue): x is RefusVue {
    return typeof x === "object" && x !== null && (x as RefusVue).ok === false;
}

/** Borne de surete sur une reclamation groupee : au-dela, c'est probablement une erreur
 *  d'appelant, pas une intention. */
const MAX_ENVOIS = 40;

/** Disposition d'un `List<T>` IL2CPP : le tableau a +0x10, la taille a +0x18, et les elements
 *  du tableau commencent a +0x20. Convention deja employee par `il2cpp/project.ts`. */
function lireListe(liste: NativePointer, max = 256): NativePointer[] {
    const out: NativePointer[] = [];
    if (liste.isNull()) return out;
    const taille = liste.add(0x18).readS32();
    const tableau = liste.add(0x10).readPointer();
    if (tableau.isNull() || taille <= 0) return out;
    for (let i = 0; i < Math.min(taille, max); i++) {
        out.push(tableau.add(0x20 + i * Process.pointerSize).readPointer());
    }
    return out;
}

/** L'`InboxProgression` vivante. Champ resolu PAR NOM a chaque appel -- un offset en dur se
 *  perime au build suivant, en silence. Lecture PURE : rien ne bouge a l'ecran du joueur. */
function progressionInbox(): NativePointer | null {
    try {
        const exec = executeurVivant();
        if (estRefusVue(exec)) return null;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return null;
        const off = getFieldOffset(kExec, "_inboxProgression");
        if (off < 0) return null;              // ⚠ -1 est *truthy* : tester `< 0`
        const p = (exec as NativePointer).add(off).readPointer();
        return p.isNull() ? null : p;
    } catch { return null; }
}

/** Lit un champ sur la classe CONCRETE de l'objet. Rend `null` si le champ n'existe pas sur
 *  cette classe -- c'est un NON MESURE, pas un zero. */
function champ(obj: NativePointer, nom: string): NativePointer | null {
    try {
        const klass = obj.readPointer();          // `Il2CppClass*`, premier mot de tout objet
        if (klass.isNull()) return null;
        const off = getFieldOffset(klass, nom);
        if (off < 0) return null;
        return obj.add(off);
    } catch { return null; }
}

function chaine(obj: NativePointer, nom: string): string | null {
    const a = champ(obj, nom);
    if (!a) return null;
    try {
        const p = a.readPointer();
        return p.isNull() ? null : readIl2cppString(p);
    } catch { return null; }
}

function booleen(obj: NativePointer, nom: string): boolean | null {
    const a = champ(obj, nom);
    if (!a) return null;
    try { return a.readU8() !== 0; } catch { return null; }
}

interface Recompense { type: number | null; id: string | null; montant: number | null; }
interface Envoi {
    /** L'identite, en clair. `null` = illisible sur cette classe (donc NON reclamable ici). */
    guid: string | null;
    classe: string | null;
    type: string | null;
    titre: string | null;
    lu: boolean | null;
    reclame: boolean | null;
    /** `null` = la classe ne porte pas de `<rewards>` (envoi sans recompense, ou forme
     *  differente) -- a distinguer d'une liste VIDE, qui est une mesure. */
    recompenses: Recompense[] | null;
}

/** Le `Il2CppClass*` -> nom, pour dire de quelle forme est chaque envoi. */
function nomClasse(obj: NativePointer): string | null {
    try {
        const klass = obj.readPointer();
        if (klass.isNull()) return null;
        // `Il2CppClass` porte son nom a +0x10 (pointeur vers un `char*` C).
        const p = klass.add(0x10).readPointer();
        return p.isNull() ? null : p.readUtf8String();
    } catch { return null; }
}

function lireEnvoi(item: NativePointer): Envoi {
    const idObj = champ(item, "<id>k__BackingField");
    let guid: string | null = null;
    try {
        if (idObj) {
            const g = idObj.readPointer();
            if (!g.isNull()) guid = chaine(g, "_value");
        }
    } catch { /* guid reste null */ }

    let recompenses: Recompense[] | null = null;
    const aRec = champ(item, "<rewards>k__BackingField");
    if (aRec) {
        recompenses = [];
        try {
            for (const r of lireListe(aRec.readPointer())) {
                if (r.isNull()) continue;
                // Un element peut etre un `Reward` ou un `LootReward` qui l'enveloppe : on
                // deballe si le champ `Reward` existe, sinon on lit l'objet tel quel.
                let cible = r;
                const enveloppe = champ(r, "Reward");
                if (enveloppe) {
                    try {
                        const d = enveloppe.readPointer();
                        if (!d.isNull()) cible = d;
                    } catch { /* on garde `r` */ }
                }
                const aType = champ(cible, "Type");
                const aMontant = champ(cible, "<Amount>k__BackingField");
                recompenses.push({
                    type: aType ? aType.readS32() : null,
                    id: chaine(cible, "Id"),
                    montant: aMontant ? aMontant.readS32() : null,
                });
            }
        } catch { /* on rend ce qu'on a pu lire */ }
    }

    return {
        guid, classe: nomClasse(item),
        type: chaine(item, "<type>k__BackingField"),
        titre: chaine(item, "<title>k__BackingField"),
        lu: booleen(item, "<read>k__BackingField"),
        reclame: booleen(item, "<claimed>k__BackingField"),
        recompenses,
    };
}

function envois(prog: NativePointer): { envois?: Envoi[]; error?: string } {
    const kProg = findClassAnywhere("thor.UserProgress", "InboxProgression");
    if (!kProg) return { error: "classe `InboxProgression` absente de ce build" };
    const mi = findMethodByParamCount(kProg, "GetInboxItems", 0);
    if (!mi) return { error: "`GetInboxItems` sans parametre INTROUVABLE -- il existe une "
        + "surcharge a 1 parametre (`types`), on ne s'y replie PAS : elle filtrerait" };
    const liste = invokeMethod(mi.info, prog, null);
    if (liste.isNull()) return { error: "`GetInboxItems` a rendu null" };
    return { envois: lireListe(liste).filter((x) => !x.isNull()).map(lireEnvoi) };
}

export function register(ctx: Ctx): void {

    /** LISTER la boite de reception, recompenses comprises. Lecture PURE.
     *
     *  ⚠ Rend les types de recompense en ORDINAL (`IdunMetaLogic.Loot.RewardType`). Le nom se
     *  redemande au jeu par `dumpEnum` : une table recopiee ici se perimerait en silence.
     *  Le seul qui compte pour l'usage courant est `Stamina` -- et c'est a l'APPELANT de
     *  l'ecarter, pas a ce module. */
    ctx.rpc.inboxList = (): Promise<unknown> => queueOnMainThread(() => {
        const prog = progressionInbox();
        if (prog === null) {
            return { ok: false, error: "`InboxProgression` introuvable sur "
                + "`ViewCommandExecutor._inboxProgression`" };
        }
        const r = envois(prog);
        if (r.error) return { ok: false, error: r.error };
        return {
            ok: true, n: (r.envois ?? []).length, envois: r.envois,
            note: "`recompenses[].type` est un ordinal de `IdunMetaLogic.Loot.RewardType` -- "
                + "le nommer par `dumpEnum`. `recompenses: null` = la classe ne porte pas de "
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
     *  ⚠ Les GUID sont re-resolus DANS CET APPEL, sur la liste fraiche : on ne garde aucun
     *  pointeur entre deux RPC. Un objet retenu d'un appel precedent aurait pu etre deplace
     *  par le GC ou invalide par une synchronisation serveur. */
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
        if (guids.length > MAX_ENVOIS) {
            return { ok: false, error: `${guids.length} > ${MAX_ENVOIS} envois -- borne de surete` };
        }
        if (body?.confirmer !== true) {
            return { ok: false, error: "REFUS : `confirmer: true` exige. Ce RPC ECRIT sur le "
                + "compte -- il est a un caractere de `inboxList`, qui ne fait que lire." };
        }
        return queueOnMainThread(() => {
            const prog = progressionInbox();
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
            const mGet = findMethodByParamCount(kProg, "GetInboxItems", 0);
            if (!mGet) return { ok: false, error: "`GetInboxItems` INTROUVABLE" };

            // La liste FRAICHE : c'est elle qui fournit les objets identite a passer.
            const liste = invokeMethod(mGet.info, prog, null);
            if (liste.isNull()) return { ok: false, error: "`GetInboxItems` a rendu null" };
            const parGuid = new Map<string, NativePointer>();
            for (const item of lireListe(liste)) {
                if (item.isNull()) continue;
                const a = champ(item, "<id>k__BackingField");
                if (!a) continue;
                try {
                    const g = a.readPointer();
                    if (g.isNull()) continue;
                    const s = chaine(g, "_value");
                    if (s) parGuid.set(s, g);
                } catch { /* envoi suivant */ }
            }

            const resultats: Array<{ guid: string; ok: boolean; motif?: string }> = [];
            for (const g of guids) {
                const idObj = parGuid.get(g);
                if (!idObj) {
                    // INTROUVABLE n'est pas un echec de reclamation : l'envoi a pu etre
                    // reclame entre le `inboxList` de l'appelant et maintenant.
                    resultats.push({ guid: g, ok: false, motif: "INTROUVABLE dans la liste "
                        + "fraiche -- deja reclame, ou identite perimee" });
                    continue;
                }
                log("[inbox] reclamation " + g
                    + " -- si le jeu gele, cette ligne est la derniere sortie");
                try {
                    invokeMethod(mi.info, prog, [idObj]);
                    resultats.push({ guid: g, ok: true });
                } catch (ex) {
                    resultats.push({ guid: g, ok: false,
                        motif: String((ex as Error).message || ex).slice(0, 180) });
                }
            }
            const reussis = resultats.filter((x) => x.ok).length;
            return {
                ok: reussis > 0, demandes: guids.length, reussis, resultats,
                note: "L'appel est passe -- ca ne prouve PAS que les recompenses sont creditees. "
                    + "Relire `inboxList` : c'est lui qui atteste (l'envoi disparait ou passe "
                    + "`reclame: true`). Et une reclamation part meme si le jeu gele ensuite.",
            };
        });
    };
}
