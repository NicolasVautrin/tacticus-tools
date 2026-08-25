// LA MEMOIRE DE DEPLOIEMENT — pour que le RETRY reparte avec l'equipe deja composee, et pour que
// la RETRAITE enregistre la composition que le joueur avait sur le plateau.
//
// Extrait de `deployment-draft.ts` le 2026-08-26, avec SES RPC : dix de ses etats etaient mutes
// depuis l'exterieur, presque tous par eux. Un module possede son etat ET ce qui l'ecrit.
//
// ⚠ IL PORTE DEUX MEMOIRES QUI NE SE CONFONDENT PAS :
//   * `memoirePoses` — ce qu'on REPOSE au retry, prise en UNE FOIS au START sur le plateau reel ;
//   * `photoPlaceholders` — ce que la RETRAITE enregistre, prise a CHAQUE GESTE parce que les
//     vues sont detruites avant `HandleBattleSurrender`.
//
// ⚠ CETTE COUPE A ECHOUE UNE PREMIERE FOIS, ET C'EST L'ORDRE QUI ETAIT FAUX. Tentee avant
// `deployment-plateau`, elle reclamait neuf symboles de cet etage : un pont a neuf entrees aurait
// ete pire que le monolithe. Une fois le plateau sorti, la meme coupe passe et les neuf
// dependances sont un import ordinaire. L'ordre des coupes se derive, il ne se choisit pas.
//
// ⚠ `armerBouton` N'EST PAS ICI : forcer le bouton START est un geste de HUD ; la memoire ne fait
// que s'en servir. L'y emporter tirait six symboles de plus. `armerStart`, en revanche, EST ici :
// c'est `deploymentMemoire` qui l'arme, et l'etat FSM du deploiement est ce que la memoire rejoue.

import { Ctx } from "../controller.js";
import {
    findClassAnywhere, findMethodByParamCount, getFieldOffset, readIl2cppString,
    class_get_name, s,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString, il2cpp_object_new } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { elementsDeListe, estRefus as estRefusLecture } from "./lecture-champs.js";
import {
    Refus, refus, lireTete, teteTriviale, NS_SRC, CLS_SANDBOX, NS_VIEWS, CLS_VIEWS,
} from "./deployment-socle.js";
import { PlaceholderPose } from "./lineup-poser.js";
import {
    definirDicoDeGet, definirVuesDePose, dicoDeGet, vuesDePose, NS_PREFAB,
} from "./deployment-prefab.js";
import { oublierPreEmprunt, classeDerriere } from "./deployment-pool.js";
import {
    Pose, UniteDuPlateau, vuesJeu, vueDeLaMoW, ordreDeConversion, unitesDuPlateau, compteJoueur,
    etatDuDeploiement, refusSiEmpilement, marquerLesUnitesDuPlateau, assurerHud, hudInstance,
    definirVuesJeu, definirHudInstance, tailleListe, NS_HUD, CLS_HUD,
} from "./deployment-plateau.js";

/**
 * LA PHOTO DU PLATEAU, PRISE PENDANT QU'IL EXISTE.
 *
 * ⚠ MESURÉ le 2026-08-26, retraite déclenchée par un CLIC du joueur : quand
 * `SandboxGameModeSource$$HandleBattleSurrender` s'exécute, `GetPlaceholderUnitViews` rend une
 * liste VIDE -- les vues sont détruites AVANT. Une lecture prise à la retraite ne peut donc rien
 * retenir, et son refus (« le plateau est vide ») accusait le joueur qui venait de déployer.
 *
 * On photographie donc au moment des GESTES : chaque pose (`UnitDeployment_PlaceUnitOnBoard`) et
 * chaque reprise en main (`PutUnitIntoHand`, qui porte aussi le retrait). Le dernier cliché est
 * l'état du plateau tel que le joueur l'a laissé.
 */
export let photoPlaceholders: PlaceholderPose[] | null = null;

export function placeholdersDepuis(o: unknown): PlaceholderPose[] | null {
    if (!Array.isArray(o)) return null;   // `{erreur}` -> PAS MESURÉ, surtout pas `[]`
    return (o as Array<Record<string, unknown>>)
        .filter((x) => typeof x.unitId === "string")
        .map((x) => x as unknown as PlaceholderPose);
}

export function photographierPlaceholders(): void {
    // Une photo ratée ne doit JAMAIS casser la pose qu'on observe : on garde la précédente.
    try {
        const v = placeholdersDepuis(ordreDeConversion());
        if (v !== null) photoPlaceholders = v;
    } catch { /* best effort */ }
}

// ============================================================================
// MÉMOIRE DE DÉPLOIEMENT — pour que le RETRY reparte avec l'équipe déjà composée.
//
// Le retry ramène la phase de déploiement, mais le plateau revient VIDE : la bataille est
// reconstruite depuis la BC, qui ne porte aucun `PredefinedUnits` côté joueur. Recomposer cinq
// unités à chaque essai rend le mode inutilisable pour ce à quoi il sert -- réessayer une
// composition contre un boss.
//
// On mémorise donc les poses APPLIQUÉES, et on les rejoue quand la phase revient.
//
// ⚠ LE REJEU EST GARDÉ PAR L'ÉTAT DU PLATEAU, pas par un drapeau : on ne rejoue QUE si le camp
// du joueur est vide. Sans ce cran, un `Show` qui tire alors que les unités sont déjà là
// doublerait la mise -- et une pose sur une case occupée échoue en silence (mesuré le
// 2026-08-17 : `ultraApothecary` sur la case de `ultraTigurius`).
export const memoirePoses: Pose[] = [];

export let memoireAuto = false;

export let memoireRejeux = 0;

export let memoireDernier: string | null = null;

/**
 * ⚠ LA MACHINE OF WAR A SON PROPRE CHEMIN, ET IL NE CROISE JAMAIS CELUI DES UNITÉS.
 *
 * Mesuré le 2026-08-17 : `tyranBiovore` sort de `TryMarkUnitAsPlaced` avec `mow=true` et
 * `accepte=true`, mais n'apparaît NI dans la mémoire NI dans `deploymentPlateau`. Deux causes
 * distinctes, toutes deux structurelles :
 *
 *   * la pose passe par `AddPlaceholderMachine(unitId, isManual, playerId, position)` -- une
 *     MoW n'a ni colonne ni ligne, elle a une `MachineOfWarPosition` et sa plateforme. Notre
 *     ancrage ne visait que `AddPlaceholderUnit` ;
 *   * `deploymentPlateau` énumère des `AUnitView` ; une MoW est une `MachineView`. Son absence
 *     de l'inventaire ne prouvait donc PAS son absence de l'écran.
 *
 * ⛔ ON ANCRE l'étage FSM (`UnitDeployment_PlaceMachineOfWarUnitOnBoard`, qui porte la
 * `position`) ET ON INVOQUE l'étage vues (`AddPlaceholderMachine`). Deux classes, deux
 * méthodes : la règle « ne jamais ancrer ce qu'on invoque » est tenue.
 */
export interface PoseMoW { unitId: string; playerId: number; position: number }

export let memoireMoW: PoseMoW | null = null;      // une seule MoW par bataille

/** OÙ la MoW s'intercale dans la séquence de pose. `null` = en DERNIER, le comportement
 *  historique -- c'est le défaut, donc rien ne change pour un appelant qui l'ignore.
 *
 *  (!)POURQUOI CET INDEX EXISTE. La MoW était posée APRÈS les unités, toujours, parce qu'elle
 *  passe par un autre chemin (`rejouerLaMoW` vs `poserUnHerosParFsm`). Conséquence MESURÉE le
 *  2026-08-21 : l'ordre de conversion obtenu ne peut mettre la machine qu'aux EXTRÉMITÉS --
 *  dernière sur plateau vierge (`U + [M]`), première sur plateau plein, où la liste libre se
 *  comporte en pile (`reverse(U + [M])` = `[M] + reverse(U)`). Aucune permutation des unités ne
 *  l'en déloge : elle n'est pas dans la partie permutée.
 *
 *  Or un replay où le joueur a posé la MoW AU MILIEU enregistre exactement ça -- et il devient
 *  alors irreproductible. Ce n'était pas visible tant que tous nos replays venaient de notre
 *  propre chaîne, qui la posait en dernier ; la capture automatique de fin de bataille en
 *  produit désormais d'autres. Le gisement est né de cette ouverture, pas d'un défaut du jeu. */
export let memoireMoWIndex: number | null = null;

/* ⛔ LA MÉMOIRE APPARTIENT À UNE BATAILLE, ET SON REJEU EST UN JETON À USAGE UNIQUE.
 *
 * Ces deux variables existent parce que `memoireAuto` seul est un booléen GLOBAL : une fois armé,
 * le `Show` du HUD de déploiement appelle `rejouerMemoire()` à CHAQUE écran, sans savoir de quelle
 * bataille la mémoire vient ni qui a monté celle qui s'ouvre. Deux dégâts mesurés le 2026-08-22,
 * rapportés par l'écran :
 *
 *   1. SANDBOX SUIVANTE — montage de `campaign1` nœud 22 juste après avoir joué le nœud 19 :
 *      l'écran s'ouvre avec les cinq poses du nœud 19 rejouées sur `C1_05`, qui n'a pas la même
 *      géométrie. Et le rejeu VIDE LE PLATEAU d'abord, donc il écrase aussi le dernier
 *      déploiement que le jeu propose lui-même par `GetBattleLineup` -- la seule lineup
 *      pré-posée légitime.
 *   2. BATAILLE RÉELLE — le même artefact sur un combat officiel contre le boss. Là c'est notre
 *      hook qui écrit dans la partie du joueur, et c'est la faute grave : un relais laissé armé
 *      qui pose tout seul est exactement ce qui fait perdre un jeton.
 *
 * `memoireBataille` retient le `BC.Id` de la bataille à qui la mémoire appartient ;
 * `memoireRejeuArme` est un JETON posé par le montage sandbox et CONSOMMÉ au premier rejeu. Une
 * bataille qu'on n'a pas montée ne pose aucun jeton, donc elle ne peut pas déclencher de rejeu --
 * quel que soit l'état de `memoireAuto`.
 *
 * (!)LE JETON EST LE CRAN QUI TIENT, PAS L'IDENTIFIANT. Comparer le `BC.Id` ne suffirait pas :
 * après un montage sandbox, `memoireBataille` reste renseigné, et une bataille RÉELLE lancée
 * ensuite retomberait dans le même piège. C'est l'usage unique qui ferme le cas 2. */
export let memoireBataille: string | null = null;

export let memoireRejeuArme = false;

export let listenerMoW: InvocationListener | null = null;

/** Le montage sandbox DÉCLARE la bataille qu'il monte. Vide la mémoire si c'en est une autre,
 *  et pose le jeton de rejeu. Appelé par `sandboxModeBcOverride` -- le seul point du code qui
 *  sache qu'une bataille est LA NÔTRE. */
export function memoireBatailleMontee(bcId: string | null): Record<string, unknown> {
    const change = bcId !== memoireBataille;
    const avant = memoirePoses.length;
    if (change) {
        memoirePoses.length = 0;
        memoireMoW = null;
        memoireMoWIndex = null;
        memoireDernier = `mémoire VIDÉE : montage de ${bcId ?? "?"}, `
            + `la mémoire appartenait à ${memoireBataille ?? "aucune bataille"} `
            + `(${avant} pose(s) jetée(s))`;
    }
    memoireBataille = bcId;
    memoireRejeuArme = true;
    return { bataille: bcId, changeDeBataille: change, posesJetees: change ? avant : 0,
             rejeuArme: true };
}

/** REPOSER le jeton -- appelé depuis l'ancrage de `SandboxGameModeSource$$LoadBattle`.
 *
 *  (!)C'EST LE RETRY QUI EXIGE ÇA, ET LE PREMIER CORRECTIF LE CASSAIT. Un jeton posé une seule
 *  fois au montage est consommé par l'écran de déploiement initial ; au RETRY, le jeu rouvre la
 *  phase de déploiement de la MÊME bataille sans repasser par le RPC de montage, donc plus aucun
 *  jeton -- et la composition était perdue, ce qui est précisément ce que la mémoire existe pour
 *  éviter. Rapporté par l'écran le 2026-08-22.
 *
 *  `SandboxGameModeSource$$LoadBattle` est le bon point parce qu'il tire à CHAQUE chargement de
 *  la bataille sandbox, retry compris, et qu'une bataille RÉELLE n'y passe jamais : elle a sa
 *  propre `GameModeSource`. Le jeton reste donc refusé là où il doit l'être. */
export function memoireRejeuAutoriser(): void {
    memoireRejeuArme = true;
}

/**
 * OUBLIER TOUS LES POINTEURS CAPTÉS SUR LA BATAILLE PRÉCÉDENTE.
 *
 * ⛔ CE MODULE MET EN CACHE CINQ POINTEURS D'OBJETS VIVANTS, ET RIEN NE LES INVALIDAIT. Ils sont
 * captés au vol dans les appels du jeu — c'est justement ce qui fait leur valeur (cf. l'en-tête
 * de `dicoVivant` : « aller CHERCHER la vue rend *une* vue, pas *celle que le déploiement
 * utilise* »). Mais l'objet meurt avec sa bataille, et le pointeur, lui, restait.
 *
 * ⚠ MESURÉ, ET LE MOTIF EST NET : le PREMIER montage d'une session passe, le SECOND tue le jeu
 * pendant la pose. Trois crashs le 2026-08-21 (`.50856` 16:42, `.29408` 16:5x, plus celui de
 * 16:27). Signature au journal : sur un plateau qu'on vient de monter, `deploymentEtat` rend un
 * `ordreConversion` NON VIDE — il décrit la bataille morte, lue à travers un pointeur périmé.
 *
 * ⚠ ET NE PAS LES TRAITER UN PAR UN. J'ai d'abord nullifié le seul `vuesJeu`, en inversant au
 * passage la préférence de `vueDeLaMoW` vers `dicoVivant()` — dont la tête est `vuesDePose`,
 * périmée de la MÊME façon. Le crash est revenu à l'identique : le défaut avait été DÉPLACÉ, pas
 * réparé. Une liste de suspects ne peut pas montrer celui qu'elle a oublié ; on remet donc à nul
 * TOUT pointeur d'objet du module, et on l'appelle depuis le seul verbe que l'appelant joue avant
 * chaque montage.
 *
 * Aucune perte : chacun est re-rempli par son propre ancrage dès que la nouvelle bataille appelle
 * la méthode correspondante. Ce qui disparaît, c'est uniquement ce qui ne devait plus servir.
 */
export function oublierLesPointeursDeLaBatailleMorte(): string[] {
    const vides: string[] = [];
    if (oublierPreEmprunt()) vides.push("preEmprunt");
    if (hudInstance !== null) { definirHudInstance(null); vides.push("hudInstance"); }
    if (dicoDeGet !== null) { definirDicoDeGet(null); vides.push("dicoDeGet"); }
    if (vuesDePose !== null) { definirVuesDePose(null); vides.push("vuesDePose"); }
    if (vuesJeu !== null) { definirVuesJeu(null); vides.push("vuesJeu"); }
    return vides;
}

export let listenerVidangeRetraite: InvocationListener | null = null;

export let vidangeRetraiteFires = 0;

export let vidangeRetraiteDernier: string | null = null;

/**
 * VIDER LA MÉMOIRE À LA RETRAITE — elle n'a aucune raison de survivre d'une sandbox à l'autre.
 *
 * ⚠ `memoireBatailleMontee` NE SUFFIT PAS, ET C'EST MESURÉ. Elle ne vide que si le `BC.Id`
 * CHANGE ; deux montages de la MÊME zone de guerre de guilde portent le même id, donc la mémoire
 * traversait. Et comme elle passe AVANT la substitution de lineup (elle est réputée plus
 * fraîche), elle a fait lire « le jeu a redéployé ta composition » là où c'était ELLE qui
 * rejouait — un vert sur une mesure polluée, trouvé le 2026-08-26. Un remontage à l'identique
 * est précisément le cas où l'on ne veut AUCUN héritage.
 *
 * ⚠ À LA RETRAITE, PAS AU MONTAGE. Vider au montage casserait le RETRY, qui repose justement sur
 * la survie de la mémoire. Une retraite est un ABANDON : rien de ce qui la précède ne doit peser
 * sur la bataille suivante.
 *
 * ⚠ HOOK LÉGER, ARMÉ AU `register` : il ne fait qu'écrire dans nos propres variables, n'invoque
 * rien et ne touche à aucun retour. C'est ce qui autorise l'armement d'office.
 */
export function armerVidangeALaRetraite(): true | Refus {
    if (listenerVidangeRetraite) return true;
    const k = findClassAnywhere(NS_SRC, CLS_SANDBOX);
    if (!k) return refus(`${NS_SRC}.${CLS_SANDBOX} INTROUVABLE`);
    const mi = findMethodByParamCount(k, "HandleBattleSurrender", 9);
    if (!mi) return refus(`\`${CLS_SANDBOX}$$HandleBattleSurrender(9 params)\` INTROUVABLE`);
    listenerVidangeRetraite = Interceptor.attach(mi.ptr, {
        onEnter() {
            vidangeRetraiteFires++;
            const avant = memoirePoses.length;
            const avaitMoW = memoireMoW !== null;
            memoirePoses.length = 0;
            memoireMoW = null;
            memoireMoWIndex = null;
            // ⚠ ON OUBLIE AUSSI LA BATAILLE. La garder ferait croire à `memoireBatailleMontee`
            // que le prochain montage du même id « ne change pas », donc qu'il n'y a rien à
            // vider -- on rouvrirait la porte qu'on vient de fermer.
            memoireBataille = null;
            vidangeRetraiteDernier = `retraite : mémoire VIDÉE (${avant} pose(s)`
                + `${avaitMoW ? " + MoW" : ""} jetée(s))`;
        },
    });
    return true;
}

/** Retient une pose, dédupliquée par unité (la dernière position gagne). */
export function memoriser(p: Pose): void {
    const i = memoirePoses.findIndex((x) => x.unitId === p.unitId);
    if (i >= 0) memoirePoses[i] = p; else memoirePoses.push(p);
}

/**
 * L'INSTANTANÉ DE LA MÉMOIRE, PRIS UNE SEULE FOIS : À L'APPUI SUR START.
 *
 * ⚠ POURQUOI PAS UNE SYNCHRONISATION À CHAQUE GESTE. Tenir la mémoire à jour pose par pose et
 * retrait par retrait, c'est maintenir un DOUBLE du plateau : deux états qui doivent rester
 * égaux, donc qui finissent par diverger — et la divergence est SILENCIEUSE, elle ne se voit
 * qu'au retry suivant, sous la forme d'une unité qu'on croyait retirée et qui revient. Le
 * plateau est la vérité, et il est LISIBLE. On le recopie donc une fois, au moment où la
 * composition est arrêtée.
 *
 * ⛔ ENFILÉ. `unitesDuPlateau` invoque des natifs, et un natif invoqué depuis un callback
 * d'interception a déjà FIGÉ le jeu (cf. le callback de `armerBouton`).
 *
 * ⚠ LA MoW N'EST PAS DANS CET INSTANTANÉ, ET C'EST STRUCTUREL : `unitesDuPlateau` énumère des
 * `AUnitView`, une MoW est une `MachineView`. `memoireMoW` reste donc alimentée par SON capteur
 * (`UnitDeployment_PlaceMachineOfWarUnitOnBoard`), qui la voit au clic. Écraser `memoireMoW`
 * ici la perdrait à chaque START.
 */
export function instantanerAuStart(): void {
    queueOnMainThread(() => unitesDuPlateau()).then((u) => {
        if (!Array.isArray(u)) {
            memoireDernier = "instantané au START ANNULÉ -- plateau non lisible : " + String(u);
            return;
        }
        const miennes = (u as UniteDuPlateau[]).filter(
            (x) => x.duJoueur && x.unitId !== null && x.col !== null && x.row !== null);
        if (miennes.length === 0) {
            // ⚠ ON NE VIDE JAMAIS SUR UN ZÉRO. Un plateau lu vide au moment du START est bien
            // plus probablement une lecture prématurée qu'une équipe vide — et écraser la
            // mémoire par ce zéro perdrait exactement la composition que le retry doit rendre.
            // Un zéro qui EFFACE est le pire des deux résultats possibles.
            memoireDernier = "instantané au START IGNORÉ -- 0 unité du joueur lue ; la mémoire "
                + `précédente est CONSERVÉE (${memoirePoses.length} pose(s))`;
            return;
        }
        memoirePoses.length = 0;
        for (const x of miennes) {
            memoirePoses.push({ unitId: x.unitId as string, playerId: x.playerId ?? 11,
                                col: x.col as number, row: x.row as number });
        }
        memoireDernier = `instantané au START : ${memoirePoses.length} pose(s) prises sur le `
            + "plateau RÉEL"
            + (memoireMoW ? ` + MoW ${memoireMoW.unitId} (capteur propre)` : " (aucune MoW)");
    }, (e) => { memoireDernier = "instantané au START LEVÉ : " + String(e); });
}

/**
 * Rejoue la mémoire si le camp du joueur est VIDE.
 *
 * ⛔ Appelé depuis la FILE du thread principal, jamais depuis un callback d'interception.
 */
export function rejouerMemoire(): void {
    if (memoirePoses.length === 0 && memoireMoW === null) return;
    queueOnMainThread(() => compteJoueur()).then((n) => {
        const nb = n as number | null;
        if (nb === null) { memoireDernier = "plateau non lisible -- rejeu ANNULÉ"; return; }
        if (nb > 0) {
            memoireDernier = `plateau déjà peuplé (${nb}) -- rejeu ANNULÉ (pas de doublon)`;
            return;
        }
        memoireRejeux++;
        memoireDernier = `rejeu de ${memoirePoses.length} pose(s)`
            + (memoireMoW ? ` + MoW ${memoireMoW.unitId}` : " (aucune MoW mémorisée)");
        // ⚠ UN REJEU PASSE PAR UN CLEAR, TOUJOURS -- cf. `viderLePlateauParFsm`. L'écran arrive
        // pré-rempli par le lineup sauvegardé du jeu, et reposer par-dessus fait refuser chaque
        // unité : le rejeu ne corrigerait RIEN et les cases resteraient celles du jeu.
        //
        // (!)CE « TOUJOURS » N'EN ÉTAIT PAS UN, ET ÇA S'EST VU SUR UNE BATAILLE RÉELLE. Le clear
        // était conditionné à `poseParFsm`, un drapeau que l'appelant devait penser à armer. Sur
        // la campagne réelle du 2026-08-21 il ne l'était pas : le clear a été sauté, les cinq
        // reposes sont tombées sur un plateau déjà plein, et `deploymentEtat` a continué de
        // publier l'arrangement du JEU -- 4 rejeux, 0 changement, aucun message d'erreur. Le
        // journal disait même « plateau VIDÉ avant rejeu », parce que cette ligne s'écrit sans
        // condition. Depuis la suppression de la voie commit, il n'y a plus de drapeau : la pose
        // est TOUJOURS un placeholder, donc le clear est TOUJOURS joué.
        viderLePlateauParFsm().then((r) => {
            const rr = r as { ok?: boolean; error?: string };
            if (rr.ok !== true) {
                // Poser sans avoir vidé produirait un déploiement MÉLANGÉ, donc faux en silence.
                memoireDernier = `rejeu ANNULÉ -- clear ÉCHOUÉ : ${rr.error}`;
                return;
            }
            memoireDernier = (memoireDernier ?? "") + " | plateau VIDÉ avant rejeu";
            // ⚠ LA MoW S'INTERCALE, ELLE N'EST PLUS FORCÉMENT DERNIÈRE. `memoireMoWIndex` dit
            // combien d'unités la précèdent ; `null` (le défaut) la remet en fin de séquence,
            // donc un appelant qui l'ignore obtient exactement le comportement d'avant.
            const idxMoW = memoireMoW === null ? -1
                : (memoireMoWIndex === null ? memoirePoses.length
                    : Math.max(0, Math.min(memoirePoses.length, memoireMoWIndex)));
            for (let i = 0; i < memoirePoses.length; i++) {
                if (i === idxMoW) rejouerLaMoW(memoireMoW as PoseMoW);
                poserUnHerosParFsm(memoirePoses[i]);
            }
            if (idxMoW >= memoirePoses.length) rejouerLaMoW(memoireMoW as PoseMoW);
        }, (e) => { memoireDernier = "rejeu ANNULÉ -- clear levé : " + String(e); });
    }, (e) => { memoireDernier = "rejeu ÉCHOUÉ : " + String(e); });
}

/**
 * Re-pose la MoW par `IdunGameViews$$AddPlaceholderMachine`.
 *
 * ⛔ ENFILÉ, jamais appelé depuis un callback d'interception.
 * ⚠ On ne rend pas la MoW RÉELLE ici : on la remet à sa plateforme, comme le ferait le clic.
 * Le passage au réel est le travail du START, comme pour les unités pré-positionnées.
 */
export function rejouerLaMoW(m: PoseMoW): void {
    queueOnMainThread((): Record<string, unknown> => {
        const v = vueDeLaMoW();
        if ("ok" in v) {
            return { ok: false, error: "aucune `IdunGameViews` joignable -- " + v.error };
        }
        // ⚠ ON PASSE PAR L'ÉTAGE FSM, PAS PAR LA VUE — et c'est mesuré.
        //
        // `IdunGameViews$$AddPlaceholderMachine` ne pose qu'un PLACEHOLDER DE VUE. Le commit du
        // déploiement (`UnitDeploymentHud$$HandleOnStartBattleTapped`) ne le trouve alors PAS
        // là où il le cherche et CRASHE en « system error » — mesuré le 2026-08-19 : START
        // lève avec la MoW reposée par la vue, et PASSE sans elle, toutes gardes identiques
        // (`+0x22c`=0, source et callbacks non nuls, 5 unités posées).
        //
        // Le clic humain, lui, passe par `StateMachineActions$$UnitDeployment_PlaceMachineOfWarUnitOnBoard`
        // — le pendant MoW de `UnitDeployment_PlaceUnitOnBoard`, et c'est exactement ce que
        // notre propre capteur ancre pour REMPLIR `memoireMoW`. On invoque donc la même chose
        // qu'on observe : le porteur est `IdunGameViews._stateMachineActions`.
        const kam = findClassAnywhere("IdunBattle.View.FSM", "StateMachineActions");
        const mi = kam
            ? findMethodByParamCount(kam, "UnitDeployment_PlaceMachineOfWarUnitOnBoard", 4)
            : null;
        if (!mi) {
            return { ok: false,
                     error: "`UnitDeployment_PlaceMachineOfWarUnitOnBoard` INTROUVABLE "
                         + "(4 paramètres)" };
        }
        let actions: NativePointer;
        try {
            const off = getFieldOffset(v.vues.readPointer(), "_stateMachineActions");
            if (off < 0) return { ok: false, error: "`_stateMachineActions` ABSENT de ce build" };
            actions = v.vues.add(off).readPointer();
        } catch (e) { return { ok: false, error: "`_stateMachineActions` ILLISIBLE : " + (e as Error).message }; }
        if (actions.isNull()) {
            return { ok: false, error: "`_stateMachineActions` NUL -- la phase de déploiement "
                + "n'est pas montée. Ce n'est PAS « pas de MoW »." };
        }
        try {
            // `isManual`, `playerId` et `position` sont des types VALEUR : on transmet
            // l'ADRESSE de la valeur, jamais la valeur elle-même.
            const manuel = Memory.alloc(1); manuel.writeU8(1);
            const pid = Memory.alloc(4); pid.writeS32(m.playerId);
            const pos = Memory.alloc(4); pos.writeS32(m.position);
            invokeMethod(mi.info, actions, [createManagedString(m.unitId), manuel, pid, pos]);
            return { ok: true, unitId: m.unitId, actions: actions.toString(),
                     vue: v.vues.toString(), source: v.source, voie: "étage FSM" };
        } catch (e) { return { ok: false, error: "LEVÉ : " + (e as Error).message }; }
    }).then((r) => {
        const rr = r as { ok?: boolean; error?: string; source?: string };
        // ⚠ ON PUBLIE AUSSI LE SUCCÈS. La version d'avant ne consignait que l'échec : une MoW
        // reposée et une MoW jamais tentée rendaient exactement la même trace.
        memoireDernier = (memoireDernier ?? "")
            + (rr.ok === true ? ` | MoW REPOSÉE (${rr.source})` : ` | MoW: ${rr.error}`);
    }, (e) => { memoireDernier = (memoireDernier ?? "") + ` | MoW levée: ${String(e)}`; });
}

/** Poser les HÉROS par l'étage FSM, comme la MoW. C'est désormais LA voie, il n'y en a plus
 *  d'autre -- le drapeau qui les départageait est parti avec la voie commit. */
export const poseFsmTrace: Array<Record<string, unknown>> = [];

export function tracerPose(r: unknown): void {
    if (poseFsmTrace.length < 32) poseFsmTrace.push(r as Record<string, unknown>);
}

/**
 * POSER UN HÉROS PAR L'ÉTAGE FSM — le pendant exact de `rejouerLaMoW`.
 *
 * ⚠ CE QUE FAISAIT LA VOIE SUPPRIMÉE, ET POURQUOI ÇA NE SUFFISAIT PAS. Elle fabriquait un
 * `AddUnitMessage` et l'appliquait DIRECTEMENT au runner : l'unité apparaissait sur le plateau,
 * mais elle passait À CÔTÉ DU HUD. Mesuré le 2026-08-20 : le bouton START affiche **0/5** alors
 * que cinq unités sont en jeu, et `IdunGameViews$$GetPlaceholderUnitViews` ne rend qu'UN élément
 * -- la MoW, seule posée par l'étage FSM. Les héros n'ont jamais été des placeholders.
 *
 * ⚠ ET LE 5/1 QU'ON AVAIT MESURÉ ÉTAIT LE NÔTRE. `UnitDeploymentHudButtons$$UpdateState` rendait
 * `standardUnitsCount = 5`, ce qui a fait conclure « le HUD compte bien notre déploiement ». Mais
 * `deploymentBoutonArmer` RÉÉCRIT ce compte (son propre commentaire le dit) : on lisait notre
 * écriture. L'écran, lui, disait 0/5 depuis le début.
 *
 * Conséquence en chaîne : `AddUnitsFromPlaceholdersAndRunnerStartMatch` ne convertit qu'un seul
 * placeholder au lieu de six, et le groupe de flux de la MoW part seul. Le replay de référence,
 * lui, vient d'une sandbox où TOUT avait été posé au HUD -- six placeholders convertis d'un coup.
 *
 * On invoque donc pour les héros la méthode que le clic humain invoque :
 * `StateMachineActions$$UnitDeployment_PlaceUnitOnBoard(unitId, column, row, isManual, playerId)`.
 */
export function poserUnHerosParFsm(p: Pose): void {
    memoriser(p);
    queueOnMainThread((): Record<string, unknown> => {
        const bloque = refusSiEmpilement(p, "UnitDeployment_PlaceUnitOnBoard");
        if (bloque) return { ok: false, unitId: p.unitId, error: bloque.error };
        const v = vueDeLaMoW();
        if ("ok" in v) {
            return { ok: false, unitId: p.unitId,
                     error: "aucune `IdunGameViews` joignable -- " + v.error };
        }
        const kam = findClassAnywhere("IdunBattle.View.FSM", "StateMachineActions");
        const mi = kam ? findMethodByParamCount(kam, "UnitDeployment_PlaceUnitOnBoard", 5) : null;
        if (!mi) {
            return { ok: false, unitId: p.unitId,
                     error: "`UnitDeployment_PlaceUnitOnBoard` INTROUVABLE (5 paramètres)" };
        }
        let actions: NativePointer;
        try {
            const off = getFieldOffset(v.vues.readPointer(), "_stateMachineActions");
            if (off < 0) return { ok: false, unitId: p.unitId,
                                  error: "`_stateMachineActions` ABSENT de ce build" };
            actions = v.vues.add(off).readPointer();
        } catch (e) {
            return { ok: false, unitId: p.unitId,
                     error: "`_stateMachineActions` ILLISIBLE : " + (e as Error).message };
        }
        if (actions.isNull()) {
            return { ok: false, unitId: p.unitId,
                     error: "`_stateMachineActions` NUL -- la phase de déploiement n'est pas "
                         + "montée. Ce n'est PAS « pas de héros »." };
        }
        try {
            // `column`, `row`, `isManual` et `playerId` sont des types VALEUR : on transmet
            // l'ADRESSE de la valeur, jamais la valeur elle-même. Même règle que pour la MoW.
            const col = Memory.alloc(4); col.writeS32(p.col);
            const row = Memory.alloc(4); row.writeS32(p.row);
            const manuel = Memory.alloc(1); manuel.writeU8(1);
            const pid = Memory.alloc(4); pid.writeS32(p.playerId);
            invokeMethod(mi.info, actions,
                         [createManagedString(p.unitId), col, row, manuel, pid]);
        } catch (e) {
            return { ok: false, unitId: p.unitId, error: "LEVÉ : " + (e as Error).message };
        }
        return { ok: true, unitId: p.unitId, voie: "FSM" };
    }).then((r) => {
        if (poseFsmTrace.length < 32) poseFsmTrace.push(r as Record<string, unknown>);
    }, (e) => {
        if (poseFsmTrace.length < 32) {
            poseFsmTrace.push({ ok: false, unitId: p.unitId, error: String(e) });
        }
    });
}

/**
 * VIDER LE PLATEAU PAR L'ÉTAGE FSM — le préalable OBLIGÉ de tout rejeu de déploiement.
 *
 * ⚠ UN REJEU QUI NE VIDE PAS EMPILE. Mesuré le 2026-08-20 : l'écran arrive DÉJÀ pré-rempli --
 * `GetBattleLineup` rend le lineup que le jeu a sauvegardé, et le HUD pose les cinq unités à
 * SES cases. Reposer par-dessus fait refuser chaque unité (« déjà un placeholder »), donc le
 * rejeu ne corrige RIEN et les cases restent celles du jeu, pas celles du replay. Pour un test
 * de déterminisme, une case fausse suffit à tout invalider.
 *
 * ⛔ CE N'EST **PAS** `UnitDeployment_RemoveAllUnitsFromBoard`, ET C'EST MESURÉ.
 * Son corps énumère le service `this+0x18` par le slot d'interface `0x22` et retire par le slot
 * `0x1f` -- ce sont les unités RÉELLEMENT DÉPLOYÉES. En phase de déploiement il y en a ZÉRO :
 * la boucle tourne à vide, l'appel rend `ok`, et le HUD garde ses cinq placeholders. Mesuré le
 * 2026-08-20 -- les cinq poses suivantes ont été refusées (« déjà un placeholder ») et le roster
 * continuait d'afficher tout comme placé. Un `ok` de cet appel-là ne prouve RIEN.
 *
 * LE RACCOURCI EST LE BOUTON LUI-MÊME : `UnitDeploymentHud$$HandleOnRemoveAllHeroesPressed()`
 * (0 paramètre), que `armerClear` ANCRE DÉJÀ -- on invoque donc exactement ce qu'on observe,
 * plutôt que de reconstituer un retrait unité par unité.
 *
 * ⚠ SI `deploymentClearArmer` EST ARMÉ, cet appel déclenche AUSSI notre relais, donc un
 * `retirerDuRunner(null)`. En régime placeholders il est éteint, et c'est ce qui rend l'appel
 * inoffensif -- pas une propriété du bouton.
 *
 * ⚠ ET ON RELIT. Le retrait transite par le flux de bataille : il ne se voit pas dans la frame de
 * l'appel (même décalage que la pose, mesuré « instantané à 5, réel à 4 une seconde plus tard »).
 * Rendre `ok` sans avoir vu le compte tomber, c'est exactement le mensonge qu'on vient de payer.
 *
 * ⛔ ENFILÉ, comme la pose : invoquer un natif depuis un callback d'interception fige le jeu.
 */
export function viderLePlateauParFsm(): Promise<Record<string, unknown>> {
    return queueOnMainThread((): Record<string, unknown> => {
        const e = etatDuDeploiement();
        if ("ok" in e) {
            return { ok: false, error: "état du déploiement NON LISIBLE (" + e.error
                + ") -- ce n'est PAS « plateau déjà vide »" };
        }
        if (e.placeholders === 0) return { ok: true, otes: 0, voie: "rien à vider" };
        const hud = assurerHud();
        if (hud === null) {
            return { ok: false, error: "aucun `UnitDeploymentHud` -- ni capté à son `Show`, ni "
                + "rendu par la scène. Le clear est INJOUABLE, ce n'est pas « déjà vide »." };
        }
        const k = findClassAnywhere(NS_HUD, CLS_HUD);
        const mi = k ? findMethodByParamCount(k, "HandleOnRemoveAllHeroesPressed", 0) : null;
        if (!mi) {
            return { ok: false, error: "`UnitDeploymentHud$$HandleOnRemoveAllHeroesPressed` "
                + "INTROUVABLE (0 paramètre)" };
        }
        try {
            invokeMethod(mi.info, hud, []);
        } catch (err) { return { ok: false, error: "LEVÉ : " + (err as Error).message }; }
        return { ok: true, avant: e.placeholders, voie: "bouton CLEAR du HUD" };
    }).then((r) => {
        const rr = r as { ok?: boolean };
        if (rr.ok !== true) return r as Record<string, unknown>;
        // LA RELECTURE, et c'est elle qui fait foi -- pas l'appel.
        return queueOnMainThread(() => {
            const e2 = etatDuDeploiement();
            if ("ok" in e2) {
                return { ok: false, error: "après retrait, état NON LISIBLE : " + e2.error };
            }
            if (e2.placeholders !== 0) {
                return { ok: false, error: `${e2.placeholders} placeholder(s) SUBSISTENT après `
                    + "retrait -- le clear n'a pas mordu" };
            }
            return { ...(r as Record<string, unknown>), verifie: true };
        }) as Promise<Record<string, unknown>>;
    });
}

/**
 * Enfile une pose APRÈS `reste` images de pump.
 *
 * ⛔ On repasse par la FILE à chaque image, on ne dort pas : une attente bloquante dans la file
 * du thread principal FIGE le jeu. Même idiome que `verifierPuisNettoyer`.
 *
 * ⚠ POURQUOI ATTENDRE. Le retrait ne prend effet qu'au passage du flux de bataille
 * (`IdunBattle.View.BattleStream.StepHandlers.RemoveUnitStepHandler`) : une pose émise dans la
 * même image tombe sur une case ENCORE OCCUPÉE, et une pose sur case occupée échoue EN SILENCE
 * (mesuré le 2026-08-17 : `ultraApothecary` sur la case de `ultraTigurius`).
 */
export function poserApresDelai(p: Pose, reste: number): void {
    if (reste <= 0) { poserUnHerosParFsm(p); return; }
    queueOnMainThread(() => ({ attendre: true })).then(
        () => poserApresDelai(p, reste - 1),
        (e) => tracerPose({ ok: false, unitId: p.unitId, error: String(e) }));
}

// ============================================================================
// LE DÉMARRAGE — le capteur qui tranche entre « composer par l'écran » et « inventer ».
//
// `UnitDeploymentHud$$HandleOnStartBattleTapped` relaie les unités posées à
// `_callbacksDelegate` (`UnitDeploymentState`, mesuré) dont le slot 3 est :
//
//     UnitDeploymentState$$StartBattle(units) :
//         ok = source.<slot 0x31>(units.<champ +0x18>)
//         si ok  : source.<slot 0x59>(units, &resultat)
//                  si echec : <slot 0x1d>(1)        <- CHEMIN D'ECHEC
//         sinon  : fabrique un objet de repli
//         this.<slot 0x69>(resultat)                <- demarrage reel
//
// ⚠ DEUX SLOTS PORTÉS PAR LA SOURCE DE MODE DE JEU — exactement l'endroit où la sandbox nous a
// déjà stubbés deux fois (`GetUnitsForDeploymentHUD` rendait un conteneur vide,
// `AmountOfUnlockedUnits` un `return 0` dédupliqué). Savoir si elle les implémente décide du
// design : si oui, on compose entièrement par l'écran (clear et start natifs, cohérents) ; si
// non, il faut écrire la conversion placeholder -> unité réelle, et ce chemin-là n'a AUCUN
// précédent dans le binaire.
//
// ⛔ Le callback ne fait que des LECTURES DE MÉMOIRE : pas une invocation. C'est la leçon des
// deux gels de ce soir. La résolution des noms se fait après coup, par RPC.

export const NS_ETAT = "IdunBattle.View.FSM.UnitDeployment";

export const CLS_ETAT = "UnitDeploymentState";

export let listenerStart: InvocationListener | null = null;

export const startTrace: Array<Record<string, unknown>> = [];

export function armerStart(): true | Refus {
    if (listenerStart) return true;
    const k = findClassAnywhere(NS_ETAT, CLS_ETAT);
    if (!k) return refus(`\`${NS_ETAT}.${CLS_ETAT}\` INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(k, "StartBattle", 1);
    if (!mi) return refus(`\`${CLS_ETAT}$$StartBattle\` INTROUVABLE (1 paramètre)`);
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête de \`StartBattle\` ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus(`REFUS : \`${CLS_ETAT}$$StartBattle\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${t.retA}) -- adresse PARTAGÉE. Cf. §8.`);
    }
    // Les offsets viennent du décompilé et sont des positions de CHAMP, pas des adresses :
    // `this+0x28` = la source interrogée, `this+0x18` = le relais de démarrage.
    listenerStart = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            const self = this as unknown as { e: Record<string, unknown> };
            self.e = {};
            try {
                const ceci = args[0];
                const units = args[1];
                self.e.units = units.toString();
                self.e.unitsNul = units.isNull();
                if (!units.isNull()) {
                    self.e.classeUnits = classeDerriere(units).classe;
                    self.e.tailleUnits = tailleListe(units);
                }
                const src = ceci.add(0x28).readPointer();
                self.e.source = src.toString();
                self.e.classeSource = src.isNull() ? null : classeDerriere(src).classe;
                const relais = ceci.add(0x18).readPointer();
                self.e.classeRelais = relais.isNull() ? null : classeDerriere(relais).classe;
            } catch (e) { self.e.erreur = (e as Error).message; }
        },
        onLeave(retval) {
            const self = this as unknown as { e: Record<string, unknown> };
            self.e.retour = retval.toInt32() & 0xff;
            // ⚠ `1` est le retour du CHEMIN D'ECHEC (`<slot 0x1d>(1)` puis `return true`) :
            // un « true » ici ne veut donc PAS dire que la bataille a démarré.
            self.e.lecture = (self.e.retour === 1)
                ? "retour 1 -- c'est la valeur du CHEMIN D'ECHEC du décompilé, pas un succès"
                : "retour 0 -- passé par le démarrage réel (slot 0x69)";
            if (startTrace.length < 16) startTrace.push(self.e);
            // ⛔ ON ENFILE, ON N'INVOQUE RIEN ICI. C'est LE point de prise de la mémoire : la
            // composition ne bougera plus, et le plateau la porte en entier.
            if (memoireAuto) instantanerAuStart();
        },
    });
    Interceptor.flush();
    return true;
}

export function registerMemoire(ctx: Ctx): void {
    /**
     * LA MÉMOIRE DE DÉPLOIEMENT — pour que le RETRY reparte avec l'équipe déjà composée.
     *
     * Armée, elle retient chaque pose appliquée et la rejoue quand la phase de déploiement
     * revient (le `Show` du HUD). `{ oublier: true }` la vide ; sans corps, elle se lit.
     *
     * ⚠ Le rejeu ne part QUE si le camp du joueur est vide -- c'est l'état du plateau qui
     * garde, pas un drapeau. Un `Show` sur un plateau déjà peuplé ne doit rien doubler.
     */
    ctx.rpc.deploymentMemoire = (body?: {
        armer?: boolean; oublier?: boolean; rejouer?: boolean; confirmer?: boolean;
        poser?: { poses?: Array<{ unitId: string; playerId: number; col: number; row: number }>;
                  mow?: { unitId: string; playerId: number; position: number } | null };
    }): unknown => {
        const etat = () => ({
            arme: memoireAuto, poses: memoirePoses.map((p) => ({
                unitId: p.unitId, playerId: p.playerId, col: p.col, row: p.row,
            })),
            // LA VIDANGE À LA RETRAITE, publiée : sans compteur, « la mémoire est vide » ne
            // distingue pas « elle a été vidée » de « le capteur n'a jamais tiré ».
            vidangeRetraite: { fires: vidangeRetraiteFires, arme: listenerVidangeRetraite !== null,
                               dernier: vidangeRetraiteDernier },
            // La MoW est SÉPARÉE, parce que son chemin natif l'est : elle n'a ni colonne ni
            // ligne. La publier à part évite de la croire absente quand on lit `poses`.
            mow: memoireMoW,
            // `null` = en dernier. Publié parce que c'est ce qui décide la POSITION de la machine
            // dans l'ordre de conversion, et qu'un appelant qui le croit sans le lire se trompe.
            mowIndex: memoireMoWIndex,
            vuesJeu: vuesJeu === null ? null : vuesJeu.toString(),
            // ⚠ SANS CE CAPTEUR, L'INSTANTANÉ NE SE PREND JAMAIS. Le publier évite de lire
            // `arme: true` comme « la mémoire se remplira » alors qu'elle restera vide.
            capteurStartArme: listenerStart !== null,
            rejeux: memoireRejeux, dernier: memoireDernier,
            // À QUI la mémoire appartient, et si un rejeu est ENCORE autorisé. Sans ces deux-là,
            // « armé » se lit comme « va rejouer » alors que le jeton peut être consommé.
            bataille: memoireBataille, rejeuArme: memoireRejeuArme,
        });
        if (body?.oublier === true) {
            memoirePoses.length = 0; memoireMoW = null; memoireMoWIndex = null;
            memoireBataille = null; memoireRejeuArme = false;
            // ⚠ LES POINTEURS DE LA BATAILLE PRÉCÉDENTE PARTENT AVEC LA MÉMOIRE, et c'est ici que
            // ça doit se faire : ce verbe est ce que l'appelant joue AVANT chaque montage
            // (`sandbox_gw.py` : « memoire de pose VIDEE avant montage »). Cf.
            // `oublierLesPointeursDeLaBatailleMorte` pour ce que ça a coûté.
            const vides = oublierLesPointeursDeLaBatailleMorte();
            memoireDernier = vides.length === 0
                ? "mémoire vidée (aucun pointeur en cache)"
                : `mémoire vidée | pointeurs oubliés : ${vides.join(", ")}`;
            return { ok: true, action: "oubliee", pointeursOublies: vides, ...etat() };
        }
        // POSER une mémoire venue du DEHORS.
        //
        // ⚠ CE QUI SURVIT À QUOI, MESURÉ le 2026-08-17 -- et je l'avais écrit à l'envers.
        // La mémoire vit dans des variables de CE script : elle survit donc parfaitement à un
        // REMONTAGE (retraite + forge + BC + `sandboxModeStart`), et c'est vérifié
        // (`rejeux` 2 -> 3, les cinq unités reposées aux mêmes cases, MoW comprise).
        // Ce qu'elle NE survit PAS, c'est un REINJECT : recharger le bundle repart de zéro.
        // D'où cette entrée -- l'appelant relit avant, repose après, et rien n'est perdu.
        if (body?.poser !== undefined) {
            memoirePoses.length = 0;
            for (const p of body.poser.poses ?? []) {
                if (typeof p?.unitId === "string" && p.unitId !== "") memoriser(p as Pose);
            }
            memoireMoW = body.poser.mow ?? null;
            // `mowIndex` ABSENT != `mowIndex: 0`. Un appelant qui ne connaît pas ce champ doit
            // retrouver le comportement d'avant (MoW en dernier), pas la poser en tête.
            const mi = (body.poser as { mowIndex?: unknown }).mowIndex;
            memoireMoWIndex = typeof mi === "number" && isFinite(mi) ? Math.trunc(mi) : null;
            memoireDernier = `mémoire POSÉE depuis l'extérieur : ${memoirePoses.length} pose(s)`
                + (memoireMoW ? ` + MoW ${memoireMoW.unitId}` : " (aucune MoW)")
                + (memoireMoWIndex === null ? "" : ` (MoW intercalée en ${memoireMoWIndex})`);
            return { ok: true, action: "posee", ...etat() };
        }
        if (body?.rejouer === true) {
            if (body.confirmer !== true) {
                // (!)CE MESSAGE ANNONÇAIT DES `AddUnitMessage` -- FAUX depuis la suppression de
                // la voie commit. `rejouerMemoire` VIDE le plateau puis repose par l'étage FSM,
                // donc en placeholders. Un avertissement périmé invente un risque disparu et
                // décrédibilise ceux qui restent : ce rejeu MUTE bien l'écran, et c'est pour ÇA
                // qu'il exige `confirmer`.
                return refus("`confirmer: true` exigé : le rejeu VIDE le plateau puis repose "
                    + "les unités mémorisées par l'étage FSM -- il modifie l'écran de "
                    + "déploiement en cours");
            }
            rejouerMemoire();
            return { ok: true, action: "rejeu ENFILÉ", ...etat() };
        }
        if (body?.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`armer: true` : la composition est PRISE EN UNE FOIS à l'appui sur "
                         + "START (instantané du plateau réel), puis REJOUÉE au retour de la "
                         + "phase de déploiement (retry). Le rejeu ne part que si le camp du "
                         + "joueur est VIDE." };
        }
        memoireAuto = body.armer === true;
        // ⚠ L'INSTANTANÉ SE PREND AU START : sans le capteur de START, la mémoire ne se remplit
        // JAMAIS et le retry reviendrait à vide -- en silence. On l'arme donc ici, et on DIT si
        // l'armement a échoué plutôt que de rendre un `arme: true` qui ne tiendrait rien.
        let start: true | Refus | "non demandé" = "non demandé";
        if (memoireAuto) start = armerStart();
        return { ok: true, action: memoireAuto ? "arme" : "retire", ...etat(),
                 capteurStart: start === true ? "ARMÉ"
                     : (start === "non demandé" ? start : "REFUSÉ : " + start.error) };
    };

    /**
     * POSER LA MoW SEULE, À L'INSTANT CHOISI — sans passer par le rejeu de mémoire.
     *
     * ⚠ POURQUOI CE RPC EXISTE. `deploymentMemoire {rejouer}` pose les héros PUIS la MoW dans la
     * MÊME vague : les six appels sont enfilés d'affilée sur le thread principal. Le joueur, lui,
     * clique la machine plusieurs secondes après ses héros. Mesuré le 2026-08-20 : la pose
     * humaine DÉMARRE la bataille (`stageName = Running`) avec des arguments IDENTIQUES aux
     * nôtres (`blackForgefiend`, `playerId 11`, `position 2`, relevés par notre propre capteur
     * sur le clic). Ce n'est donc pas QUOI on passe -- reste QUAND.
     *
     * Et le rejeu de mémoire ne peut pas servir à l'éprouver : il REFUSE quand le plateau est
     * déjà peuplé (garde anti-doublon), ce qui est justement le cas après les héros.
     */
    ctx.rpc.deploymentMoWPoser = (body?: {
        unitId?: string; playerId?: number; position?: number; confirmer?: boolean;
    }): unknown => {
        if (body?.confirmer !== true) {
            return refus("ECRITURE -- exige `confirmer: true`. Ce RPC invoque l'étage FSM de "
                + "pose de Machine of War (`UnitDeployment_PlaceMachineOfWarUnitOnBoard`).");
        }
        if (typeof body.unitId !== "string" || body.unitId === "") {
            return refus("`unitId` exigé -- ce RPC ne devine aucune machine.");
        }
        if (typeof body.playerId !== "number" || typeof body.position !== "number") {
            return refus("`playerId` et `position` exigés (entiers) -- ils ne se devinent pas, "
                + "et un `position` faux pose la machine sur une AUTRE plateforme.");
        }
        rejouerLaMoW({ unitId: body.unitId, playerId: body.playerId, position: body.position },
                     );
        return { ok: true, enfile: true, unitId: body.unitId, playerId: body.playerId,
                 position: body.position,
                 note: "ENFILÉ sur le thread principal -- vérifier l'EFFET par "
                     + "`deploymentBoutonArmer` (placees) ou `observeBattle`, jamais ce retour." };
    };

    /** LA TRACE DES POSES — lecture pure. Il n'y a plus de voie à choisir, donc plus rien à
     *  armer : `deploymentPoseFsmArmer` et `deploymentPoseCommitArmer` sont SUPPRIMÉS avec la
     *  voie commit. Ce RPC ne garde que ce qu'ils publiaient d'utile, les derniers résultats. */
    ctx.rpc.deploymentPoseTrace = (): unknown =>
        ({ ok: true, lecture: true, faits: poseFsmTrace.slice(-8),
           note: "les poses passent TOUJOURS par l'étage FSM (placeholder) -- la voie "
               + "`AddUnitMessage` au runner est supprimée depuis le 2026-08-21." });

    /** Rend START vivant SANS geste manuel sur une BC pré-remplie : à chaque `Show`, les unités
     *  déjà présentes sont déclarées au HUD et le bouton est rafraîchi. */
    ctx.rpc.deploymentSyncArmer = (body?: {
        armer?: boolean; confirmer?: boolean; maintenant?: boolean;
    }): Promise<unknown> | unknown => {
        if (body?.maintenant === true) {
            return queueOnMainThread(() => marquerLesUnitesDuPlateau());
        }
        const etat = () => ({ actif: syncAuto, dernier: syncDernier });
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`armer: true` + `confirmer: true` : chaque `Show` déclarera au HUD "
                         + "les unités déjà sur le plateau (invoque `TryMarkUnitAsPlaced`)" };
        }
        if (body.armer === false) { syncAuto = false; return { ok: true, ...etat() }; }
        if (body.confirmer !== true) return refus("`confirmer: true` exigé");
        // Le relais vit dans `Show`, qui est ancré par `armerHud` : sans lui, rien ne tirera.
        const r = armerHud();
        if (r !== true) return r;
        syncAuto = true;
        return { ok: true, ...etat() };
    };
}


// --- CE QUE `deployment-draft` ECRIT CHEZ NOUS ------------------------------------------------
// ESM interdit d'assigner un import, et c'est tant mieux : chaque ecriture est NOMMEE, donc
// greppable, au lieu d'une affectation invisible a travers deux modules.
export function definirMemoireMoW(m: PoseMoW | null): void { memoireMoW = m; }
export function definirMemoireMoWIndex(i: number | null): void { memoireMoWIndex = i; }
export function definirListenerMoW(l: InvocationListener | null): void { listenerMoW = l; }
export function definirMemoireRejeuArme(v: boolean): void { memoireRejeuArme = v; }
export function definirMemoireDernier(v: string | null): void { memoireDernier = v; }
export function definirVidangeRetraiteDernier(v: string | null): void {
    vidangeRetraiteDernier = v;
}

/** Le CLEAR invalide la photo (cf. `armerClear` dans `deployment-draft`). On POSE `[]` -- << mesure,
 *  et vide >> -- plutot que de relire un plateau qui n'a pas encore ete vide : le retrait ne se
 *  voit pas dans la frame de l'appel. */
export function viderLaPhotoDesPlaceholders(): void { photoPlaceholders = []; }

/** La photo, PRISE : `deployment-draft` la rafraichit a chaque pose et a chaque reprise en main. */
export function poserLaPhotoDesPlaceholders(v: PlaceholderPose[] | null): void {
    if (v !== null) photoPlaceholders = v;
}

export let syncAuto = false;
export let syncDernier: unknown = null;

/** `armerHud` vit dans l'etage HUD, qui nous importe : on ne l'importe pas en retour, il nous
 *  est INJECTE. Non injecte, on REFUSE l'armement en le disant -- plutot que de rendre `ok` sur
 *  un relais qui ne tirera jamais. */
let armerHudInjecte: (() => true | Refus) | null = null;
export function enregistrerArmerHud(fn: () => true | Refus): void { armerHudInjecte = fn; }
function armerHud(): true | Refus {
    return armerHudInjecte
        ? armerHudInjecte()
        : refus("`armerHud` NON INJECTE -- le relais de `Show` ne serait jamais pose");
}

/** Le relais de `Show` (etage HUD) publie ici son dernier verdict de synchronisation. */
export function definirSyncDernier(v: unknown): void { syncDernier = v; }

export function definirListenerStart(l: InvocationListener | null): void { listenerStart = l; }

/** CONSOMMER la photo : `null`, pas `[]`. La distinction porte du sens -- `[]` dit << mesure, et
 *  vide >> (le joueur a vide le plateau), `null` dit << plus de cliche >>. Les confondre ferait
 *  refuser une retraite en accusant un plateau vide au lieu d'une photo deja servie. */
export function consommerLaPhotoDesPlaceholders(): void { photoPlaceholders = null; }
