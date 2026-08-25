/**
 * garde-jeton — REFUSER le START d'une bataille LIVE quand aucune lineup n'est retenue (#10047).
 *
 * LE PROBLEME. Entrer dans une bataille est GRATUIT ; c'est le START qui engage le jeton
 * (`HandleStartMatch` -> `GenerateNewBattleId` -> `StartCampaignLocation`). Or la composition
 * que le deploiement posera vient du REGISTRE de `lineup-poser` : si rien n'y est retenu pour ce
 * mode, on part avec ce que le jeu a garde de la derniere fois -- et le jeton est deja parti
 * quand on s'en apercoit.
 *
 * OU L'ARRETER, ET POURQUOI PAS AILLEURS
 * ---------------------------------------
 * Lu au decompile, `IdunBattle.View.FSM.UnitDeployment.UnitDeploymentState$$StartBattle(units)`
 * consulte DEUX predicats avant de laisser partir la bataille :
 *
 *     1. `VisualBattleQuery$$IsMinUnitAmountToBringToStartBattleReached(units.Count)`
 *        -> FAUX : `StartBattle` alloue LUI-MEME sa raison (champ `+0x30 = 1`), l'affiche,
 *           et rend FAUX. Aucune depense.
 *     2. `VisualBattleQuery$$HasGameModeReasonNotToStartMatch(units, out reason)`
 *        -> VRAI : meme sortie, mais la raison doit etre FOURNIE par l'appele.
 *
 * On detourne le PREMIER. C'est le plus tot, et surtout le seul dont le refus n'exige rien de
 * nous : `reasonNotToStartMatch` n'est PAS un enum -- c'est une reference vers un OBJET que
 * l'implementation alloue et peuple (mesure : `CampaignGameModeSource` y met la liste des unites
 * requises manquantes, `GuildBossGameModeSource` un drapeau). Le detourner nous obligerait a
 * fabriquer cet objet, ou a passer un NUL a un consommateur qui ne l'attend pas. Le premier
 * predicat, lui, est PUR : `MinUnitsNeededToStartBattle(this) <= amountUnits`, rien d'autre.
 *
 * ⇒ Le jeu affichera SON message (<< pas assez d'unites >>), qui n'est pas la vraie raison. C'est
 * pourquoi on ouvre EN PLUS notre propre boite de dialogue, qui dit ce qui se passe vraiment.
 *
 * ⛔ ON NE BLOQUE JAMAIS LA SANDBOX. C'est par elle qu'on MONTE la lineup : la bloquer
 * fermerait la seule porte de sortie. La source est lue sur la requete par son champ NOMME
 * `_gameModeSource` (`+0x80` sur ce build, resolu par `getFieldOffset`, jamais code en dur).
 *
 * ⛔ ET IL NE BLOQUE QUE CE QU'IL SAIT DEBLOQUER. Une source absente de `lineup-poser.CLASSES`
 * n'admet AUCUNE composition retenue : la refuser enfermerait le mode pour de bon, sans geste
 * pour en sortir. La couverture est DEMANDEE a `lineup-poser` (`estSourceCouverte`), jamais
 * recopiee ici.
 *
 * ⚠ LE REGISTRE VIT EN MEMOIRE, DONC IL MEURT AU REINJECT. Consequence directe et assumee :
 * apres un reinject, chaque mode redemande son montage sandbox avant de pouvoir partir. C'est le
 * comportement demande ; `gardeJetonArmer {bloquer: false}` le leve sans toucher a l'ancrage.
 *
 * ⛔ ET IL ECHOUE OUVERT. Toute incertitude -- source illisible, classe inconnue, champ absent
 * du build -- LAISSE PASSER, en le disant. Un garde qui bloque sur ce qu'il n'a pas su mesurer
 * enfermerait le joueur hors de son propre jeu ; c'est la faute la plus chere qu'il puisse
 * commettre, bien plus qu'un jeton perdu.
 *
 * ⚠ LE CORPS DU PREDICAT EST COURT, DONC SUSPECT DE DEDUPLICATION. IL2CPP partage les corps
 * triviaux, et la table est indexee par adresse : un corps partage n'a qu'UN proprietaire
 * affiche, donc rien ne prouve par la table que l'ancrage ne tire que pour lui. On ne suppose
 * pas -- chaque tir VERIFIE que `this` est bien une `VisualBattleQuery` avant de decider, et les
 * tirs ecartes sont COMPTES (`etrangers`). Un compte non nul serait la mesure de la
 * deduplication, pas une surprise.
 *
 * ⚠ LA POPUP EST DIFFEREE, PAS INLINE. On la poste par `queueOnMainThread` (donc au prochain
 * `Update`) au lieu de l'ouvrir dans le callback : au moment ou le predicat repond, la FSM de
 * deploiement est au milieu de sa transition. Elle est aussi ETRANGLEE -- le predicat peut etre
 * consulte plusieurs fois par geste, et une popup par appel serait ininterrompable.
 */
import {
    class_get_name, findClassAnywhere, findMethodByParamCount, getFieldOffset, s,
} from "../il2cpp/helpers.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { compositionRetenue, estSourceCouverte } from "./lineup-poser.js";
import { afficherMessage } from "./message-box.js";
import { Ctx } from "../controller.js";

const NS_QUERY = "IdunBattle.View.FSM";
const CLS_QUERY = "VisualBattleQuery";
const METH = "IsMinUnitAmountToBringToStartBattleReached";
const CHAMP_SOURCE = "_gameModeSource";
/** La sandbox est la voie de MONTAGE de la lineup : la bloquer fermerait la porte de sortie. */
const CLS_SANDBOX = "SandboxGameModeSource";
/** Deux appels du meme geste ne doivent pas ouvrir deux popups. */
const ETRANGLEMENT_MS = 5000;

interface Decision {
    ordre: number;
    verdict: "laisse" | "bloque";
    raison: string;
    classeSource: string | null;
    retenue: number | null;
    quand: string;
}

let listener: InvocationListener | null = null;
let bloquer = true;
/** ⚠ POURQUOI CE DRAPEAU EXISTE, ALORS QU'IL DESACTIVE LA SEULE EXEMPTION DU GARDE.
 *
 *  Le chemin BLOQUANT ne s'exerce, en usage normal, que sur une bataille REELLE -- donc le
 *  valider coute un jeton SI le garde rate. C'est exactement l'ordre inverse de celui que le
 *  depot pratique : on prouve le mecanisme en sandbox, ou rien n'est engage, AVANT de le laisser
 *  courir sur le compte. Ce drapeau fait traiter la sandbox comme une bataille live, le temps
 *  d'une verification. Il est DESARME par defaut et n'est jamais pose par le register : arme par
 *  megarde, il rendrait le montage de lineup impossible -- la porte de sortie que tout le reste
 *  du module s'attache a garder ouverte. */
let traiterLaSandboxCommeLive = false;
/** La popup est un CONFORT, jamais une condition du refus -- et pendant une verification
 *  automatisee elle ne fait qu'interrompre l'operateur. Le refus, lui, ne se tait jamais :
 *  il reste lisible dans `gardeJetonEtat.decisions`. */
let popup = true;
let fires = 0;
let etrangers = 0;
let bloques = 0;
let refusArmement: string | null = null;
let derniereDecision: Decision | null = null;
const decisions: Decision[] = [];
let dernierePopup = 0;

function noter(
    verdict: "laisse" | "bloque", raison: string,
    classeSource: string | null, retenue: number | null,
): void {
    const d: Decision = {
        ordre: fires, verdict, raison, classeSource, retenue,
        quand: new Date().toISOString(),
    };
    derniereDecision = d;
    decisions.push(d);
    if (decisions.length > 40) decisions.shift();
}

/** La classe CONCRETE de la source du mode, lue sur la requete par champ NOMME.
 *  Rend `null` quand on ne sait pas -- et ce `null` fait LAISSER PASSER, jamais bloquer. */
function classeDeLaSource(query: NativePointer): string | null {
    try {
        const kq = query.readPointer();
        const off = getFieldOffset(kq, CHAMP_SOURCE);
        if (off < 0) return null;
        const src = query.add(off).readPointer();
        if (src.isNull()) return null;
        return s(class_get_name(src.readPointer()) as NativePointer);
    } catch { return null; }
}

/** Est-ce bien une `VisualBattleQuery` ? Le garde contre un corps DEDUPLIQUE (cf. l'en-tete). */
function estLaRequete(obj: NativePointer): boolean {
    try { return s(class_get_name(obj.readPointer()) as NativePointer) === CLS_QUERY; }
    catch { return false; }
}

function prevenirLeJoueur(classeSource: string): void {
    if (!popup) return;
    const maintenant = Date.now();
    if (maintenant - dernierePopup < ETRANGLEMENT_MS) return;
    dernierePopup = maintenant;
    queueOnMainThread(() => afficherMessage({
        titre: "DEPART BLOQUE",
        texte: "Aucune composition n'est retenue pour ce mode ("
            + classeSource + ").\n\n"
            + "Le depart a ete refuse AVANT que le jeton ne soit depense. Monte la composition "
            + "en sandbox, puis reviens : elle sera reposee toute seule au deploiement.\n\n"
            + "Le message du jeu juste derriere parle d'un nombre d'unites -- c'est le refus par "
            + "lequel nous passons, pas la vraie raison.",
        okTexte: "Compris",
    })).catch(() => { /* la popup est un confort, jamais une condition du refus */ });
}

function armer(): Record<string, unknown> {
    if (listener !== null) return { ok: true, deja: true, bloquer };
    const k = findClassAnywhere(NS_QUERY, CLS_QUERY);
    if (!k) {
        refusArmement = `classe ${NS_QUERY}.${CLS_QUERY} introuvable -- chemin PERIME`;
        return { ok: false, error: refusArmement };
    }
    const mi = findMethodByParamCount(k, METH, 1);
    if (!mi) {
        refusArmement = `\`${METH}\` a 1 parametre introuvable -- chemin PERIME`;
        return { ok: false, error: refusArmement };
    }
    listener = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            (this as unknown as { q: NativePointer }).q = args[0];
        },
        onLeave(retval) {
            fires += 1;
            const q = (this as unknown as { q?: NativePointer }).q;
            if (q === undefined || !estLaRequete(q)) { etrangers += 1; return; }
            // Le jeu refuse deja : rien a faire, et surtout rien a raconter au joueur.
            if (retval.toInt32() === 0) {
                noter("laisse", "le jeu refuse deja (pas assez d'unites)", null, null);
                return;
            }
            const classeSource = classeDeLaSource(q);
            if (classeSource === null) {
                noter("laisse", "source NON MESUREE (champ `" + CHAMP_SOURCE + "` absent, nul, "
                    + "ou illisible) -- on echoue OUVERT", null, null);
                return;
            }
            if (classeSource === CLS_SANDBOX && !traiterLaSandboxCommeLive) {
                noter("laisse", "sandbox -- c'est la voie de MONTAGE, jamais bloquee",
                      classeSource, null);
                return;
            }
            // ⛔ LE CRAN QUI EMPECHE UN VERROUILLAGE DEFINITIF. Bloquer une source pour laquelle
            // `lineup-poser` ne sait RIEN retenir rendrait le mode injouable : le joueur n'aurait
            // aucun geste pour lever le refus. La couverture est DEMANDEE au module qui la porte,
            // jamais recopiee ici -- deux listes divergeraient, et c'est le joueur qui paierait.
            if (!estSourceCouverte(classeSource)) {
                noter("laisse", "source NON COUVERTE par `lineup-poser` -- aucune composition ne "
                    + "peut y etre retenue, donc un refus serait DEFINITIF", classeSource, null);
                return;
            }
            const retenue = compositionRetenue(classeSource);
            if (retenue !== null) {
                noter("laisse", `lineup retenue (${retenue.origine})`,
                      classeSource, retenue.ids.length);
                return;
            }
            if (!bloquer) {
                noter("laisse", "AUCUNE lineup retenue -- mais le blocage est DESARME",
                      classeSource, null);
                return;
            }
            retval.replace(ptr(0));
            bloques += 1;
            noter("bloque", "AUCUNE lineup retenue pour ce mode -- depart refuse AVANT la "
                + "depense du jeton", classeSource, null);
            prevenirLeJoueur(classeSource);
        },
    });
    refusArmement = null;
    return { ok: true, bloquer, methode: `${CLS_QUERY}$$${METH}` };
}

export function register(ctx: Ctx): void {
    // ARME AU REGISTER, et blocage ACTIF. C'est un garde : desarme, il ne protege rien. Le cout
    // est un ancrage sur un predicat consulte au geste de depart, pas sur un chemin chaud -- et
    // toute incertitude LAISSE PASSER (cf. l'en-tete).
    armer();

    /** L'etat du garde, et les 40 dernieres decisions AVEC LEUR RAISON.
     *
     *  ⚠ `etrangers` n'est pas decoratif : il compte les tirs dont le `this` n'est PAS une
     *  `VisualBattleQuery`. Non nul, il mesure une deduplication de corps par IL2CPP -- ce que
     *  la table de symboles, indexee par adresse, ne peut pas dire. */
    ctx.rpc.gardeJetonEtat = (): unknown => ({
        ok: true,
        arme: listener !== null,
        bloquer,
        traiterLaSandboxCommeLive,
        popup,
        refusArmement,
        fires,
        etrangers,
        bloques,
        derniereDecision,
        decisions: decisions.slice(-15),
    });

    /** Desarmer/rearmer le BLOCAGE (l'ancrage, lui, reste en place et continue d'observer).
     *
     *  `bloquer: false` laisse tout passer en CONTINUANT de noter ce qui aurait ete bloque --
     *  c'est le mode qui permet de verifier le garde sans en subir le refus. */
    ctx.rpc.gardeJetonArmer = (body?: {
        bloquer?: boolean;
        popup?: boolean;
        traiterLaSandboxCommeLive?: boolean;
        confirmerSandboxCommeLive?: boolean;
    }): unknown => {
        if (typeof body?.bloquer === "boolean") bloquer = body.bloquer;
        if (typeof body?.popup === "boolean") popup = body.popup;
        // ⚠ EXIGE `confirmer` : arme par megarde, ce drapeau ferme la voie de MONTAGE de la
        // lineup -- la seule sortie que le garde laisse au joueur. On ne l'ouvre pas par defaut
        // de frappe. Il ne sert qu'a EPROUVER le blocage la ou rien n'est engage.
        if (typeof body?.traiterLaSandboxCommeLive === "boolean") {
            if (body.traiterLaSandboxCommeLive && body.confirmerSandboxCommeLive !== true) {
                return { ok: false, arme: listener !== null, bloquer,
                         traiterLaSandboxCommeLive,
                         error: "REFUS : `traiterLaSandboxCommeLive: true` FERME la voie de "
                             + "montage de la lineup. Repasser avec "
                             + "`confirmerSandboxCommeLive: true` si c'est bien une "
                             + "verification du blocage." };
            }
            traiterLaSandboxCommeLive = body.traiterLaSandboxCommeLive;
        }
        const r = armer();
        return { ...r, arme: listener !== null, bloquer, popup, traiterLaSandboxCommeLive };
    };
}
