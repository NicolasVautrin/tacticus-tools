/**
 * gw-oubli-fin-bataille — OUBLIER la composition retenue quand une bataille de GUERRE DE GUILDE
 * se termine (#10047).
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Le garde-jeton refuse un depart quand `lineup-poser` ne retient AUCUNE composition pour le
 * mode. Une composition retenue reste donc valable... indefiniment. En guerre de guilde c'est
 * precisement ce qu'on ne veut pas : les unites qui viennent de se battre sont consommees pour
 * la guerre en cours, donc reproposer la meme equipe au combat suivant est une faute qui ne
 * s'annonce pas. On OUBLIE a la fin de la bataille, ce qui force un choix DELIBERE au suivant --
 * le garde s'occupant de rendre ce choix obligatoire.
 *
 * ⛔ CE MODULE N'ECRIT RIEN DANS LE JEU. Il ne touche ni le magasin de compositions du joueur, ni
 * ce que l'ecran de deploiement pre-pose : `oublierComposition` ne vide que NOTRE registre. Un
 * module qui ecrirait dans le jeu depuis un `HandleFinishBattle` toucherait une fin de bataille
 * REELLE, et ce n'est pas ce qui a ete demande.
 *
 * ⚠ DEUX ANCRAGES, ET C'EST VOLONTAIRE. `HandleFinishBattle` est la fin SEMANTIQUE,
 * `ShowBattleEndScreen` la fin VISIBLE ; selon le chemin (victoire, defaite, abandon, erreur)
 * l'un peut tirer sans l'autre. L'oubli est IDEMPOTENT -- le second passage ne trouve plus rien
 * et le dit (`dejaOublie`) -- donc doubler l'ancrage ne coute qu'un tir, et ne pas le doubler
 * couterait un oubli manque. On ne choisit pas entre deux points quand l'operation ne craint pas
 * d'etre rejouee.
 *
 * ⚠ LE `this` DECIDE, PAS L'ANCRAGE. IL2CPP deduplique les corps triviaux et la table est
 * indexee par adresse : un ancrage pose pour `GuildWarsGameModeSource` peut tirer avec un `this`
 * d'une tout autre classe. Les tirs ecartes sont COMPTES (`etrangers`), jamais ignores en
 * silence -- un compte non nul EST la mesure de la deduplication.
 *
 * ⚠ ET IL ECHOUE OUVERT, comme le garde qu'il sert : une classe introuvable ou une methode
 * absente n'est pas une panne du jeu, c'est un chemin PERIME, et ca se lit dans `refusArmement`.
 */
import { class_get_name, findClassAnywhere, findMethod, s } from "../il2cpp/helpers.js";
import { oublierComposition } from "./lineup-poser.js";
import { Ctx } from "../controller.js";

const NS_SOURCE = "IdunBattle.ViewLogic.BattleSource";
const CLS_SOURCE = "GuildWarsGameModeSource";
/** La fin SEMANTIQUE, puis la fin VISIBLE -- cf. l'en-tete : on ancre les deux. */
const METHODES = ["HandleFinishBattle", "ShowBattleEndScreen"] as const;

interface Oubli {
    quand: string;
    methode: string;
    /** Ce qu'on a JETE. `null` = il n'y avait rien a oublier -- et ce n'est pas la meme chose. */
    ids: string[] | null;
    origine: string | null;
}

const listeners: InvocationListener[] = [];
const posees: string[] = [];
let refusArmement: string | null = null;
let fires = 0;
let etrangers = 0;
let oubliesEffectifs = 0;
let dejaOublie = 0;
let dernier: Oubli | null = null;
const historique: Oubli[] = [];

function noter(methode: string, jete: { ids: string[]; origine: string } | null): void {
    const o: Oubli = {
        quand: new Date().toISOString(), methode,
        ids: jete === null ? null : jete.ids.slice(),
        origine: jete === null ? null : jete.origine,
    };
    dernier = o;
    historique.push(o);
    if (historique.length > 20) historique.shift();
}

function armer(): Record<string, unknown> {
    if (listeners.length > 0) return { ok: true, deja: true, posees: posees.slice() };
    const k = findClassAnywhere(NS_SOURCE, CLS_SOURCE);
    if (!k) {
        refusArmement = `classe ${NS_SOURCE}.${CLS_SOURCE} introuvable -- chemin PERIME`;
        return { ok: false, error: refusArmement };
    }
    const refus: string[] = [];
    for (const nom of METHODES) {
        const mi = findMethod(k, nom);
        if (!mi || mi.ptr.isNull()) { refus.push(`${nom} introuvable`); continue; }
        try {
            listeners.push(Interceptor.attach(mi.ptr, {
                onEnter(args) {
                    fires += 1;
                    let classeThis: string | null = null;
                    try { classeThis = s(class_get_name(args[0].readPointer()) as NativePointer); }
                    catch { classeThis = null; }
                    if (classeThis !== CLS_SOURCE) { etrangers += 1; return; }
                    const jete = oublierComposition(CLS_SOURCE);
                    if (jete === null) { dejaOublie += 1; noter(nom, null); return; }
                    oubliesEffectifs += 1;
                    noter(nom, { ids: jete.ids, origine: jete.origine });
                },
            }));
            posees.push(`${CLS_SOURCE}$$${nom}`);
        } catch (e) {
            refus.push(`${nom} : ${(e as Error).message}`);
        }
    }
    refusArmement = refus.length > 0 ? refus.join(" | ") : null;
    return { ok: listeners.length > 0, posees: posees.slice(), refus };
}

export function register(ctx: Ctx): void {
    // ARME AU REGISTER. Le cout est un ancrage sur deux methodes de FIN DE BATAILLE -- appelees
    // une fois par bataille, jamais sur un chemin chaud.
    armer();

    /** L'etat de l'oubli, et les 20 derniers.
     *
     *  ⚠ `oubliesEffectifs` et `dejaOublie` sont SEPARES : « j'ai jete 5 unites » et « il n'y
     *  avait rien a jeter » ne se corrigent pas pareil, et un compteur unique les confondrait.
     *  `fires: 0` dit que la fin de bataille n'a jamais ete traversee -- pas que rien n'a ete
     *  retenu. */
    ctx.rpc.gwOubliEtat = (): unknown => ({
        ok: true,
        arme: listeners.length > 0,
        posees: posees.slice(),
        refusArmement,
        fires,
        etrangers,
        oubliesEffectifs,
        dejaOublie,
        dernier,
        historique: historique.slice(-10),
    });
}
