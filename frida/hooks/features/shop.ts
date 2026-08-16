// ---------------------------------------------------------------------------------------
// BOUTIQUES -- lire les produits d'un marchand, et prendre CEUX QUI SONT GRATUITS.
//
// POURQUOI CE MODULE N'EST PAS UN `shopBuy` GENERIQUE. Chaque boutique porte une offre a
// cout nul (le coffre quotidien du marchand `default`, les composants de Machine of War du
// war shop) qui expire en quelques heures et ne coute RIEN a prendre. Le reste depense de
// l'or, des gemmes ou une devise de faction -- c'est-a-dire une ressource du compte du
// joueur. Le RPC s'appelle donc `shopBuyFree` et REFUSE, de maniere executable, tout produit
// dont le cout n'est pas nul. Un `shopBuy` generique aurait le meme corps a une garde pres,
// et cette garde-la est precisement ce qui separe un inventaire d'une depense.
//
// LA CHAINE NATIVE, couche LOGIQUE -- pas la couche commande :
//   IdunMetaLogic.UserProgress.ProductProgression$$GetMerchantProducts(merchantId:String)
//       -> List<ShopProduct>
//   IdunMetaLogic.UserProgress.ProductProgression$$PurchaseMerchantProduct(
//          productId:MerchantProductId, merchantId:String, purchaseAmount:Int32,
//          result:PurchaseMerchantProductResult&) -> List<Reward>
// Le porteur est `ViewCommandExecutor._productProgression`, resolu PAR NOM.
//
// ⚠ ON NE PASSE PAS PAR `BuyShopProductIfPossibleCommand`. Son `Execute` traine les popups de
// confirmation, les flyouts et les sequences de recompense (`ShowRewardSequence`,
// `ShowPurchaseConfirmationPopup`, `GetProductOrigin` qui veut un `Transform`) -- de l'UI, sur
// un jeu dont on ne pilote pas l'ecran. La couche logique fait le meme travail sans rien
// afficher, exactement comme `InboxProgression` pour la boite de reception.
//
// ⚠ `Success` VAUT 3, PAS 0. `PurchaseMerchantProductResult` = UnknownProductId 0,
// CannotAfford 1, AlreadySold 2, Success 3 (demande au jeu par `dumpEnum`, pas recopie d'un
// dump). Un `resultat === 0` lu comme un succes serait exactement l'inverse de la verite --
// il designe le produit INTROUVABLE. On compare au NOM, jamais a un ordinal suppose.
//
// ⚠ `MerchantProductId` EST UNE STRUCT (un seul champ `_value:String`, `fieldsSize` 8). Le
// champ `productId` d'un produit porte donc la structure INLINE, pas un pointeur : on passe
// son ADRESSE a `runtime_invoke`, et on lit son `_value` par offset DEBOXE. C'est le meme
// piege que `InboxItemGUID`, qui avait coute une passe entiere en rendant des identites
// nulles sans la moindre erreur.
//
// ⚠ ON NE FABRIQUE PAS D'IDENTITE. Le `productId` passe a l'achat est celui PORTE PAR L'OBJET
// vivant, relu sur une liste FRAICHE a l'instant de l'achat -- l'appelant ne fournit qu'une
// chaine pour DESIGNER lequel. Meme regle que `inbox.ts` : construire l'identite reviendrait
// a deviner sa forme pour un gain nul, et la moindre erreur ferait acheter autre chose.
//
// ⚠ LE COUT SE LIT SUR L'OBJET DU JEU, jamais sur un fichier. `user_progression.json` exprime
// la gratuite par l'ABSENCE de la cle `cost` ; l'objet vivant, lui, porte un `costAmount:Int64`
// non nullable, donc `0`. Les deux concordent -- mais c'est le jeu qui decide, et c'est lui
// que la garde interroge.
// ---------------------------------------------------------------------------------------

import { findClassAnywhere, findMethodByParamCount, getFieldOffset }
    from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import {
    listElements, field, fieldIn, fieldAny, stringAt, className,
} from "../il2cpp/read.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";
import { executeurVivant, Refus as RefusVue } from "./view-command.js";

function isViewRefusal(x: NativePointer | RefusVue): x is RefusVue {
    return typeof x === "object" && x !== null && (x as RefusVue).ok === false;
}

/** `PurchaseMerchantProductResult`, DEMANDE au jeu le 2026-08-16. Garde ici uniquement pour
 *  nommer le retour : la comparaison porte sur `SUCCESS`, et le RPC rend AUSSI l'ordinal brut
 *  pour qu'un glissement de table se voie. */
const RESULT_NAMES: Record<number, string> = {
    0: "UnknownProductId", 1: "CannotAfford", 2: "AlreadySold", 3: "Success",
};
const SUCCESS = 3;

/** La `ProductProgression` vivante. Champ resolu PAR NOM a chaque appel -- un offset en dur
 *  se perime au build suivant, en silence. */
function productProgression(): NativePointer | null {
    try {
        const exec = executeurVivant();
        if (isViewRefusal(exec)) return null;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return null;
        const off = getFieldOffset(kExec, "_productProgression");
        if (off < 0) return null;                  // ⚠ -1 est *truthy* : tester `< 0`
        const p = (exec as NativePointer).add(off).readPointer();
        return p.isNull() ? null : p;
    } catch { return null; }
}

/** `thor.UserProgress.Data.MerchantProductId` -- STRUCT a un champ `_value:String`. */
let midKlass: NativePointer | null | undefined;
function merchantProductIdClass(): NativePointer | null {
    if (midKlass === undefined) {
        midKlass = findClassAnywhere("thor.UserProgress.Data", "MerchantProductId");
    }
    return midKlass;
}

interface Produit {
    /** L'identite en clair. `null` = illisible, donc NON achetable par cette voie. */
    productId: string | null;
    merchantId: string | null;
    /** `costAmount` de l'objet VIVANT. `null` = NON MESURE -- et un cout non mesure fait
     *  REFUSER l'achat, il n'est jamais rabattu sur zero. */
    costAmount: number | null;
    costType: number | null;
    purchasesLeft: number | null;
    maxPurchases: number | null;
    rewardId: string | null;
    rewardAmount: number | null;
    rewardType: number | null;
    chestId: string | null;
    cls: string | null;
    /** Derive, pour la lisibilite du pilote. Vrai UNIQUEMENT sur un cout MESURE a zero. */
    isFree: boolean;
    isTakeable: boolean;
}

function readProduit(p: NativePointer): Produit {
    const kMid = merchantProductIdClass();
    const aPid = field(p, "productId");
    const productId = (aPid && kMid) ? stringAt(fieldIn(aPid, kMid, "_value")) : null;

    const aCost = field(p, "costAmount");
    const aCostT = field(p, "costType");
    const aLeft = field(p, "purchasesLeft");
    const aMax = field(p, "maxPurchases");

    // `costAmount` est un Int64. On le ramene en Number : les couts de boutique tiennent
    // tres largement dans un entier sur 53 bits, et un `Int64` ne franchit pas le pont RPC.
    let costAmount: number | null = null;
    if (aCost) { try { costAmount = aCost.readS64().toNumber(); } catch { costAmount = null; } }

    let rewardId: string | null = null;
    let rewardAmount: number | null = null;
    let rewardType: number | null = null;
    try {
        const aRew = field(p, "reward");
        const rew = aRew ? aRew.readPointer() : null;
        if (rew && !rew.isNull()) {
            const kRew = rew.readPointer();
            const aT = fieldAny(rew, kRew, ["Type", "type"]);
            const aI = fieldAny(rew, kRew, ["Id", "id"]);
            const aA = fieldAny(rew, kRew, ["<Amount>k__BackingField", "Amount", "amount"]);
            rewardType = aT ? aT.readS32() : null;
            rewardId = stringAt(aI);
            rewardAmount = aA ? aA.readS32() : null;
        }
    } catch { /* recompense illisible -- les champs restent `null`, au sens NON MESURE */ }

    const left = aLeft ? aLeft.readS32() : null;
    const isFree = costAmount === 0;
    return {
        productId,
        merchantId: stringAt(field(p, "merchantId")),
        costAmount, costType: aCostT ? aCostT.readS32() : null,
        purchasesLeft: left, maxPurchases: aMax ? aMax.readS32() : null,
        rewardId, rewardAmount, rewardType,
        chestId: null,
        cls: className(p),
        isFree,
        // GRATUIT != DISPONIBLE : `purchasesLeft` tombe a 0 une fois l'offre prise et
        // l'entree RESTE listee, comme un envoi reclame reste en boite.
        isTakeable: isFree && left !== null && left > 0,
    };
}

function listProduits(prog: NativePointer, merchantId: string):
    { produits?: Produit[]; ptrs?: NativePointer[]; error?: string } {
    const kProg = findClassAnywhere("IdunMetaLogic.UserProgress", "ProductProgression");
    if (!kProg) return { error: "classe `ProductProgression` absente de ce build" };
    const mi = findMethodByParamCount(kProg, "GetMerchantProducts", 1);
    if (!mi) return { error: "`GetMerchantProducts` a 1 parametre INTROUVABLE" };
    const list = invokeMethod(mi.info, prog, [createManagedString(merchantId)]);
    if (list.isNull()) {
        return { error: "`GetMerchantProducts` a rendu null pour `" + merchantId
            + "` -- marchand inconnu, ou boutique non chargee" };
    }
    const el = listElements(list);
    if (el.err) return { error: "liste de produits : " + el.err };
    if (el.inline) {
        return { error: "les produits se lisent comme des types VALEUR -- forme inattendue "
            + "pour `List<ShopProduct>`, on refuse de decoder" };
    }
    const ptrs = el.addrs.filter((x) => !x.isNull());
    return { produits: ptrs.map(readProduit), ptrs };
}

export function register(ctx: Ctx): void {

    /** LISTER les produits d'un marchand, tels que LE JEU les voit. Lecture PURE.
     *
     *  ⚠ Le pendant hors ligne (`scripts/python/shops.py`) lit le meme etat depuis
     *  `user_progression.json`. Les deux doivent concorder ; s'ils divergent, c'est le JEU
     *  qui a raison -- le fichier peut avoir une synchronisation de retard. */
    ctx.rpc.shopProducts = (body?: { merchantId?: string }): Promise<unknown> | unknown => {
        const merchantId = typeof body?.merchantId === "string" ? body.merchantId : "";
        if (!merchantId) {
            return { ok: false, error: "`merchantId` manquant. Ce RPC n'ENUMERE PAS les "
                + "marchands : les noms connus sont `default`, `guild`, `guildWars`, "
                + "`elderShop`, `crusadeShop`, et celui de l'evenement en cours." };
        }
        return queueOnMainThread(() => {
            const prog = productProgression();
            if (prog === null) {
                return { ok: false, error: "`ProductProgression` introuvable sur "
                    + "`ViewCommandExecutor._productProgression`" };
            }
            const r = listProduits(prog, merchantId);
            if (r.error) return { ok: false, error: r.error };
            const produits = r.produits ?? [];
            return {
                ok: true, merchantId, n: produits.length,
                free: produits.filter((x) => x.isFree).length,
                takeable: produits.filter((x) => x.isTakeable).length,
                produits,
                note: "`costAmount: null` = cout NON MESURE, et `shopBuyFree` REFUSE dans ce "
                    + "cas. `isTakeable` exige un cout mesure a ZERO et `purchasesLeft > 0`.",
            };
        });
    };

    /** PRENDRE une offre GRATUITE. Ce RPC ECRIT sur le compte.
     *
     *  ⚠ TROIS REFUS EXECUTABLES, dans cet ordre :
     *    - `confirmer: true` absent               -> on ne fait rien ;
     *    - cout NON MESURE ou NON NUL             -> on ne depense pas une ressource ;
     *    - `purchasesLeft <= 0`                   -> l'offre est deja prise.
     *  Le deuxieme est la raison d'etre du module : la garde interroge l'objet VIVANT, pas la
     *  chaine que l'appelant a bien voulu envoyer. */
    ctx.rpc.shopBuyFree = (body?: {
        merchantId?: string; productId?: string; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const merchantId = typeof body?.merchantId === "string" ? body.merchantId : "";
        const productId = typeof body?.productId === "string" ? body.productId : "";
        if (!merchantId || !productId) {
            return { ok: false, error: "`merchantId` et `productId` exiges -- lire "
                + "`shopProducts` d'abord, puis designer le produit voulu" };
        }
        if (body?.confirmer !== true) {
            return { ok: false, error: "REFUS : `confirmer: true` exige. Ce RPC ECRIT sur le "
                + "compte -- il est a un caractere de `shopProducts`, qui ne fait que lire." };
        }
        return queueOnMainThread(() => {
            const prog = productProgression();
            if (prog === null) {
                return { ok: false, error: "`ProductProgression` introuvable sur "
                    + "`ViewCommandExecutor._productProgression`" };
            }
            const kProg = findClassAnywhere("IdunMetaLogic.UserProgress", "ProductProgression");
            if (!kProg) return { ok: false, error: "classe `ProductProgression` absente" };
            const mi = findMethodByParamCount(kProg, "PurchaseMerchantProduct", 4);
            if (!mi) {
                return { ok: false, error: "`PurchaseMerchantProduct` a 4 parametres "
                    + "INTROUVABLE -- ne PAS se replier sur la voie `BuyShopProductIfPossible`, "
                    + "qui traine l'UI" };
            }

            // La liste FRAICHE : c'est elle qui fournit et l'identite et le COUT.
            const r = listProduits(prog, merchantId);
            if (r.error || !r.ptrs || !r.produits) {
                return { ok: false, error: r.error ?? "liste indisponible" };
            }
            const idx = r.produits.findIndex((x) => x.productId === productId);
            if (idx < 0) {
                return { ok: false, error: "produit `" + productId + "` INTROUVABLE chez `"
                    + merchantId + "` dans la liste fraiche -- deja pris, ou boutique "
                    + "rafraichie depuis la lecture" };
            }
            const p = r.produits[idx];

            // ⚠ LA GARDE. Un cout NON MESURE refuse AUSSI : ne pas savoir ce qu'on depense
            //   n'est pas une raison de depenser.
            if (p.costAmount === null) {
                return { ok: false, produit: p, error: "REFUS : cout NON MESURE sur le produit "
                    + "vivant. On ne prend que ce dont on a LU que le cout est nul." };
            }
            if (p.costAmount !== 0) {
                return { ok: false, produit: p, error: "REFUS : ce produit COUTE "
                    + p.costAmount + " (type de ressource " + p.costType + "). Ce RPC ne prend "
                    + "QUE les offres a cout nul -- il n'existe pas de voie payante ici." };
            }
            if (p.purchasesLeft === null || p.purchasesLeft <= 0) {
                return { ok: false, produit: p, error: "REFUS : `purchasesLeft` = "
                    + p.purchasesLeft + " -- l'offre est deja prise. Une offre prise RESTE "
                    + "listee, ce n'est pas une anomalie." };
            }

            // ⚠ L'ADRESSE de la struct `MerchantProductId`, pas un pointeur d'objet.
            const aPid = field(r.ptrs[idx], "productId");
            if (!aPid) return { ok: false, error: "champ `productId` illisible sur le produit" };

            const aAmount = Memory.alloc(4); aAmount.writeS32(1);
            const aResult = Memory.alloc(4); aResult.writeS32(-1);   // sentinelle hors enum

            log("[shop] achat GRATUIT " + merchantId + "/" + productId
                + " -- si le jeu gele, cette ligne est la derniere sortie");
            let rewards: NativePointer;
            try {
                rewards = invokeMethod(mi.info, prog,
                    [aPid, createManagedString(merchantId), aAmount, aResult]);
            } catch (ex) {
                return { ok: false, produit: p,
                         error: String((ex as Error).message || ex).slice(0, 240) };
            }

            const code = aResult.readS32();
            const nom = RESULT_NAMES[code] ?? ("ORDINAL INCONNU " + code);
            // ⚠ Le decompte des recompenses est INDICATIF : `PurchaseMerchantProduct` peut
            //   rendre une liste vide sur un succes (le lot part par une autre voie). C'est
            //   le CODE qui fait foi, pas la longueur.
            let nRewards: number | null = null;
            try {
                if (!rewards.isNull()) {
                    const el = listElements(rewards);
                    nRewards = el.err ? null : el.addrs.length;
                }
            } catch { nRewards = null; }

            return {
                ok: code === SUCCESS, merchantId, productId,
                resultat: code, resultatNom: nom, nRewards, produit: p,
                note: "Le code fait foi, PAS `nRewards`. `Success` vaut 3 -- un 0 signifie "
                    + "`UnknownProductId`, jamais un succes. Attester en relisant "
                    + "`shopProducts` : `purchasesLeft` doit avoir baisse.",
            };
        });
    };
}
