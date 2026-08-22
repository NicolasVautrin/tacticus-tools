/**
 * L'INVENTAIRE DE MATERIAUX, VIVANT -- lecture et OBSERVATION, jamais d'ecriture.
 *
 * POURQUOI CE MODULE EXISTE. Pour decrementer les besoins d'un plan de farming, il faut savoir ce
 * qu'une bataille a REELLEMENT rapporte. Mesure du 2026-08-22 : `user_progression.json` (le
 * miroir sur disque, sous `AppData/LocalLow`) NE SE RAFRAICHIT PAS a chaque bataille -- il portait
 * 37 minutes de retard alors qu'une dizaine de raids venaient d'etre joues. Le seul etat fidele
 * est celui que le jeu tient EN MEMOIRE.
 *
 * DEUX VOIES, ET ELLES NE DISENT PAS LA MEME CHOSE :
 *
 *   - `inventaireUpgrades` LIT les quantites (`UpgradeProgression$$GetAmount`). C'est l'ETAT.
 *     Un avant/apres en donne le DELTA, mais un delta ne dit pas d'ou vient le gain : un achat en
 *     boutique, un coffre ouvert ou un craft s'y melangent au butin de bataille.
 *   - `inventaireObserver` ANCRE `UpgradeProgression$$AddUpgradeLocally`, l'ecriture elle-meme.
 *     C'est l'EVENEMENT : chaque gain, avec son id et son montant, dans l'ordre.
 *
 * On garde les deux parce que chacune rattrape l'angle mort de l'autre : l'observateur rate ce
 * qui est arme trop tard, l'etat rate la CAUSE.
 *
 * ⛔ CE MODULE N'APPELLE JAMAIS `CheatAddUpgrade` NI `CheatClearUpgrades`. Elles sont dans la
 * meme classe, a un nom pres. Ecrire dans l'inventaire d'un compte reel n'est pas une mesure.
 *
 * ⛔ ET L'ANCRAGE N'INVOQUE RIEN. `AddUpgradeLocally` est ancree, donc on ne l'appelle pas --
 * ancrer ce qu'on invoque gele le jeu. Le callback ne fait que LIRE ses arguments et empiler.
 */
import {
    class_get_fields, class_get_name, field_get_name, field_get_offset,
    findClassAnywhere, findMethodByParamCount, readIl2cppString, s as cstr,
} from "../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { executeurVivant } from "./view-command.js";
import { estRefus, refus } from "./lecture-champs.js";
import { Ctx } from "../controller.js";

const NS_PROG = "IdunMetaLogic.UserProgress";

type Gain = { id: string | null; montant: number; ordre: number };

let observateur: InvocationListener | null = null;
let gains: Gain[] = [];
let compteur = 0;
let derniereErreur: string | null = null;

/**
 * L'instance de `UpgradeProgression`, trouvee sur l'executeur -- NOM D'ABORD, CLASSE ENSUITE.
 *
 * (!)ON NE DEVINE PAS LE NOM DU CHAMP, ET ON NE SE FIE PAS NON PLUS AU NOM SEUL.
 * `_unitProgression`, `_itemProgression`, `_resourceProgression` existent sur l'executeur, donc
 * `_upgradeProgression` est PLAUSIBLE -- et une supposition plausible qui rate rend un nul qu'on
 * lirait comme << pas d'inventaire >>. On filtre donc par le nom (metadonnee IL2CPP, aucune
 * lecture memoire, donc aucun risque), puis on VERIFIE la classe de l'objet pointe. C'est la
 * verification qui fait la mesure ; le nom ne fait que borner le balayage.
 *
 * ⛔ POURQUOI NE PAS BALAYER *TOUS* LES CHAMPS. Il faudrait lire chaque offset comme un pointeur
 * puis le dereferencer pour en tirer la classe. Sur un champ de type VALEUR, ce pointeur est un
 * entier quelconque, et le dereferencer fait tomber le jeu. Le filtre par nom evite ca.
 *
 * Le champ retenu est PUBLIE : un changement de build se verra dans la reponse.
 */
function progressionDesUpgrades(): { ptr: NativePointer; champ: string; classe: string }
    | ReturnType<typeof refus> {
    const exec = executeurVivant();
    if (estRefus(exec)) return exec as ReturnType<typeof refus>;
    const e = exec as NativePointer;
    let klass: NativePointer;
    try { klass = e.readPointer(); }
    catch (err) { return refus("executeur illisible : " + (err as Error).message); }

    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(NULL);
    const candidats: Array<{ nom: string; off: number }> = [];
    const tous: string[] = [];
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        let nom: string;
        try { nom = cstr(field_get_name(f) as NativePointer); } catch { continue; }
        tous.push(nom);
        if (/upgrade/i.test(nom) || /progression/i.test(nom)) {
            candidats.push({ nom, off: field_get_offset(f) as number });
        }
    }
    const echecs: string[] = [];
    for (const c of candidats) {
        let ptr: NativePointer;
        try { ptr = e.add(c.off).readPointer(); } catch { continue; }
        if (ptr.isNull()) { echecs.push(c.nom + ":NUL"); continue; }
        let classe: string;
        try { classe = cstr(class_get_name(ptr.readPointer()) as NativePointer); }
        catch { echecs.push(c.nom + ":classe illisible"); continue; }
        if (classe === "UpgradeProgression") return { ptr, champ: c.nom, classe };
        echecs.push(c.nom + ":" + classe);
    }
    return refus("aucun champ de l'executeur ne porte une `UpgradeProgression` -- "
        + `${candidats.length} candidat(s) sur ${tous.length} champ(s) : `
        + (echecs.join(", ") || "aucun") + ". Chemin PERIME ?");
}

export function register(ctx: Ctx): void {
    /** LES QUANTITES, PAR ID. Read-only : `GetAmount` est un accesseur pur.
     *
     *  `ids` est EXIGE -- rendre les 461 materiaux du jeu couterait 461 invocations pour un
     *  besoin qui n'en concerne qu'une vingtaine, et noierait le resultat utile. */
    ctx.rpc.inventaireUpgrades = (body?: {
        ids?: string[];
    }): Promise<unknown> | unknown => {
        const ids = body?.ids;
        if (!Array.isArray(ids) || ids.length === 0) {
            return refus("`ids` manquant -- la liste des materiaux a lire (ex. les `upgArmC003` "
                + "du plan de raids)");
        }
        return queueOnMainThread(() => {
            const p = progressionDesUpgrades();
            if (estRefus(p)) return p;
            const prog = (p as { ptr: NativePointer; champ: string; classe: string });
            const k = findClassAnywhere(NS_PROG, "UpgradeProgression");
            if (!k) return refus("classe `UpgradeProgression` INTROUVABLE");
            const m = findMethodByParamCount(k, "GetAmount", 1);
            if (!m) return refus("`UpgradeProgression$$GetAmount(1)` INTROUVABLE -- signature "
                + "changee, chemin PERIME");
            const quantites: Record<string, number | null> = {};
            const refus_: Record<string, string> = {};
            for (const id of ids) {
                try {
                    const r = invokeMethod(m.info, prog.ptr, [createManagedString(id)]);
                    // ⚠ `runtime_invoke` BOXE les types valeur : un `int` se lit a +0x10 de la
                    // boite, jamais sur le pointeur lui-meme.
                    quantites[id] = (r && !r.isNull()) ? r.add(0x10).readS32() : null;
                } catch (e) {
                    // `null` = NON MESURE, jamais rabattu sur 0 -- un zero invente ferait croire
                    // que le materiau manque et relancerait du farming pour rien.
                    quantites[id] = null;
                    refus_[id] = (e as Error).message;
                }
            }
            return { ok: true, champ: prog.champ, instance: prog.ptr.toString(),
                     quantites, refus: refus_,
                     note: "LECTURE SEULE -- `GetAmount` est un accesseur." };
        });
    };

    /** L'OBSERVATEUR DE GAINS -- ancre `AddUpgradeLocally` et empile ce qui passe.
     *
     *  ⛔ Aucune invocation dans le callback : on lit les arguments et on empile. */
    ctx.rpc.inventaireObserver = (body?: {
        armer?: boolean; lire?: boolean; vider?: boolean;
    }): Promise<unknown> | unknown => {
        const etat = () => ({
            arme: observateur !== null, gains: gains.length, total: compteur,
            derniereErreur, detail: gains,
        });
        if (body?.vider === true) { gains = []; return { ok: true, action: "vide", ...etat() }; }
        if (body?.lire === true || body?.armer === undefined) {
            return { ok: true, lecture: true, ...etat() };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (observateur) { observateur.detach(); observateur = null; }
                return { ok: true, action: "desarme", ...etat() };
            }
            if (observateur) return { ok: true, action: "deja arme", ...etat() };
            const k = findClassAnywhere(NS_PROG, "UpgradeProgression");
            if (!k) return refus("classe `UpgradeProgression` INTROUVABLE");
            const m = findMethodByParamCount(k, "AddUpgradeLocally", 2);
            if (!m) {
                return refus("`UpgradeProgression$$AddUpgradeLocally(2)` INTROUVABLE -- la "
                    + "signature a change (id, montant attendus), chemin PERIME");
            }
            observateur = Interceptor.attach(m.ptr, {
                onEnter(args) {
                    compteur += 1;
                    let id: string | null = null;
                    let montant = 0;
                    // args[0] = `this`, args[1] = l'id, args[2] = le montant.
                    try { id = readIl2cppString(args[1]); } catch { id = null; }
                    try { montant = args[2].toInt32(); } catch { montant = 0; }
                    gains.push({ id, montant, ordre: compteur });
                    // Une pile qui grossit sans fin finirait par peser ; on borne, et on le DIT.
                    if (gains.length > 4096) {
                        gains.splice(0, gains.length - 4096);
                        derniereErreur = "pile bornee a 4096 -- les plus anciens gains sont perdus";
                    }
                },
            });
            return { ok: true, action: "arme",
                     ancrage: "IdunMetaLogic.UserProgress.UpgradeProgression$$AddUpgradeLocally",
                     ...etat() };
        });
    };
}
