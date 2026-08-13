// #993 — L'ENTREE ET LA SORTIE DE BATAILLE SANS UN SEUL CLIC, cablees dans le warmup.
//
// CE QUE CE MODULE REMPLACE. Le cycle de `warmup-singletons.ts` pilote l'UI sur cinq etapes
// (`to-campaign`, `click-node`, `click-play`, puis `pause -> retraite -> confirmation`) dont
// l'unique effet utile est TROIS appels natifs. Toute la fragilite du cycle vit dans ces clics :
// clic AVALE indiscernable d'un clic reussi (#332), repos de 800 ms, chemin de noeud qui change
// a chaque run, et un cran 8 qui rattrape le wedge que tout cela produit.
//
// LES TROIS APPELS, MESURES (build `rnca9r7q6c`, sessions 77-80, cf. `case-992`) :
//
//     ViewCommandExecutor$$StartCampaignMatch(campaignId, locationIndex, type, nullable)
//     IdunMainView$$OnBattleSurrender()      -> popup de confirmation (PauseSurrender DIFFERE)
//     IdunMainView$$ContinueSurrender()      -> fin de bataille, retour au meta
//
// ~2 s contre 19-26 s pour le meme aller-retour pilote a l'UI, et ZERO stamina (on se retire
// AVANT le deploiement -- ce que le natif nomme lui-meme `hasSurrenderedBeforeDeployment`).
//
// ⚠ ENTRER PAR LA BONNE PORTE -- C'EST L'INVARIANT CENTRAL DE CE MODULE, ET IL A ETE APPRIS EN
// CASSANT. Un premier essai appelait `ContinueSurrender` SEULE : la bataille se terminait bien
// (`get_IsBattleActive -> False`) et le jeu restait SANS AUCUN ECRAN RENDU -- il a fallu
// `ToTacticiansMenu()` pour le recuperer. Entrer par le milieu donne la FIN sans ce qui la
// PREPARE. `ContinueSurrender` n'est donc JAMAIS appelee ici sans que l'EFFET d'`OnBattleSurrender`
// ait ete OBSERVE. C'est la lecon de #332 transposee du clic a l'invoke : on ne conclut pas du
// retour d'un appel qu'il a porte.
//
// ⚠ ET L'EFFET D'`OnBattleSurrender` N'EST PAS UN : `AGameModeSource$$PauseSurrender(Action)`
// rend un BOOLEEN -- c'est une QUESTION, pas une etape. `true` = il DIFFERE (il garde le callback
// pour apres le popup de confirmation), `false` = il laisse passer et la bataille se termine
// seule. Mesure du warmup UI : `true`. Mais rien ne garantit que ce soit toujours la branche
// prise, et supposer le popup ferait echouer a tort la branche « passe tout droit ». D'ou
// `attendreEffetDeSurrender`, a TROIS issues nommees.
//
// POURQUOI CE MODULE EST PUR. Le cycle complet n'est pas rejouable a volonte (il lance une VRAIE
// bataille et exige une session Frida vivante), et les gestes qu'il enchaine sont IRREVERSIBLES.
// La LOGIQUE -- ordre des appels, gardes, bornes, distinction des etats -- est donc isolee ici,
// sans un seul acces a Frida : ses effets sont injectes. `frida/tools/probe-993-warmup-programmatique.ts`
// l'exerce hors Frida avec des doublures qui COMPTENT leurs appels. Meme decoupe que
// `warmup-wedge-remedy.ts` en son temps, et pour la meme raison : une
// logique juste mais non cablee se lit exactement comme un chemin qui marche.
//
// CE QUE CE MODULE NE FAIT PAS. Il ne DIT PAS au jeu ou se retrouver. La sortie de bataille rend
// la main sur ce que le jeu affiche ensuite -- mesure du 2026-08-13 : `Idun_UI_Navigation`, pas
// la campagne -- et le seul cran exigible est qu'un ecran soit remonte (`attendreMetaChargee`).
//
// ⚠ ET IL N'A PAS DE REPLI. Le pilotage d'UI a ete RETIRE du warmup avec cette tranche : quand
// l'un des motifs ci-dessous sort, le warmup est ROUGE. Un repli sur les clics aurait rendu
// cette voie INVERIFIABLE -- elle pourrait cesser de porter sans que rien ne le signale, le
// cycle repayant simplement les 19-26 s d'avant. C'est pour cela que chaque panne porte un
// `reason` NOMME plutot qu'un `ok: false` : le motif est tout ce qui reste pour diagnostiquer.

/** Les deux seules entrees de sortie de bataille qu'on s'autorise a invoquer. La liste blanche
 *  vit dans `retreat-capture.ts` (`INVOCABLES`) ; ce type en est la moitie utilisee ici. */
export type SortieMethode = "OnBattleSurrender" | "ContinueSurrender";

/** Ce que rend l'attente qui suit `OnBattleSurrender`. TROIS issues, jamais un booleen : le natif
 *  a deux branches legitimes et une panne, et les confondre ferait soit appeler `ContinueSurrender`
 *  sur une bataille deja finie, soit declarer en panne une retraite qui a marche. */
export type EffetDeSurrender = "popup-de-confirmation" | "bataille-terminee" | "rien";

export interface EtapeProg {
    step: string;
    ok: boolean;
    info: string;
}

/** Les effets dont ce cycle a besoin, injectes par l'appelant. Aucun n'est implemente ici :
 *  c'est ce qui rend le module executable hors du process de jeu. */
export interface EntreeProgDeps {
    /** `IdunMainView$$get_IsBattleActive()`, STATIQUE. `null` = NON MESUREE -- jamais rabattu
     *  sur `false` : lancer une bataille en croyant qu'aucune ne tourne ferait refuser
     *  `StartMatch(checkIfAlreadyRunning: true)` EN SILENCE, et on attendrait une capture qui ne
     *  viendrait jamais. */
    enBataille: () => Promise<boolean | null>;
    /** LE GARDE « UNE BATAILLE TOURNE DEJA » EST-IL ARME ? -- `IdunMainView$$get_IsActive()`.
     *
     *  ⚠ CE N'EST PAS `get_IsBattleActive`, ET LES CONFONDRE COUTE UN CYCLE ENTIER. Mesure du
     *  2026-08-13, apres un lancement dont la scene n'avait pas monte :
     *
     *      get_IsActive       = True     <- le garde que `StartMatch(checkIfAlreadyRunning)` teste
     *      get_IsBattleActive = False    <- aucune scene de bataille
     *      FindObjectsByType(IdunMainView) -> 0 instance
     *
     *  Dans cet etat, `StartMatch` journalise et RETOURNE : la source `CampaignGameModeSource`
     *  est bien creee (elle l'est AVANT l'appel au chargeur), donc la capture reussit et le cycle
     *  se croit en bataille -- pour echouer 20 s plus loin sur un symptome qui ne nomme pas la
     *  cause. Le garde survit a un lancement rate, et rien ne le nettoie tout seul. */
    gardeDejaEnCours: () => Promise<boolean | null>;
    /** `IdunMainView$$SetBattleNotRunning()` -- le desarmement du garde ci-dessus.
     *
     *  ⚠ IL ECRIT, et il n'est appele que dans UN etat sans ambiguite : garde arme ALORS
     *  QU'AUCUNE bataille n'existe. Cet etat ne peut venir que d'un lancement avorte -- le jeu,
     *  lui, nettoie le garde en fin de bataille. Ne jamais l'appeler quand une bataille tourne
     *  vraiment : ce serait mentir au jeu au lieu de reparer un residu. */
    desarmerGarde: () => Promise<{ ok: boolean; err?: string }>;
    /** LE CHARGEMENT DE SCENE EST-IL TERMINE ? -- `thor.Loader.__loadingStep == 0`.
     *
     *  ⚠ C'EST LE DISCRIMINANT, ET IL EST CAUSAL. `thor.Loader$$LoadScene` REFUSE EN SILENCE de
     *  charger quand un chargement est deja en cours (`_scenesToLoad.Count >= 1` ou
     *  `IsLoadingInternal`, c.-a-d. `_loadingStep > 0`) : il journalise et retourne. Se retirer
     *  dans cette fenetre fait donc annuler le RETOUR AU META sans un mot -- la bataille se
     *  termine (`get_IsBattleActive -> false`), le popup de confirmation reste a l'ecran, et le
     *  jeu n'affiche plus rien tout en repondant aux RPC.
     *
     *  MESURE DU 2026-08-13, statique lue toutes les ~900 ms apres `StartCampaignMatch` :
     *
     *      t=1,1 s   __loadingStep = 1
     *      t=3,1 s   __loadingStep = 6
     *      t=9,8 s   __loadingStep = 10
     *      t=10,8 s  __loadingStep = 0     <- chargement TERMINE
     *
     *  Les trois cycles qui ont bloque le jeu se retiraient entre 8 et 10 s : dans la fenetre.
     *  Le meme geste joue a ~30 s rend la main sur un ecran complet en 7,8 s.
     *
     *  ⚠ ET AUCUN AUTRE SIGNAL NE MARCHE, tous mesures et tous ECARTES : `get_IsBattleActive`
     *  bascule des 6,8 s ; l'instance d'`IdunMainView` est vivante avant ; le FSM rend
     *  `UnitDeploymentState` des 1,2 s ; les boutons de deploiement sont la a 8,8 s ; et le
     *  popup de confirmation s'affiche par-dessus une bataille encore en chargement, donc son
     *  `montre-fin` ne dit rien de l'etat du chargement.
     *
     *  `null` = NON MESURE (statique illisible, classe non initialisee) -- jamais rabattu sur
     *  « termine » : se retirer sans savoir est precisement ce qui casse le jeu. */
    attendreChargementTermine: (timeoutMs: number) => Promise<boolean>;
    /** `ViewCommandExecutor$$StartCampaignMatch(...)`. Rend seulement si l'INVOKE a eu lieu --
     *  jamais si la bataille a demarre : ca, c'est `attendreCapture` qui le dit. */
    lancerBataille: () => Promise<{ ok: boolean; err?: string }>;
    /** Le pointeur de `CampaignGameModeSource` des qu'il est capture, sinon `null`. C'est LE but
     *  fonctionnel du warmup : tout le reste n'est que ce qu'il faut traverser pour l'obtenir. */
    attendreCapture: (timeoutMs: number) => Promise<string | null>;
    /** L'instance d'`IdunMainView` est-elle capturee ET VIVANTE ? Elle nait avec la scene de
     *  bataille, donc APRES la capture. Sans elle, la sortie n'a pas de `this`. */
    attendrePorteDeSortie: (timeoutMs: number) => Promise<boolean>;
    invoquerSortie: (m: SortieMethode) => Promise<{ ok: boolean; err?: string }>;
    /** L'EFFET d'`OnBattleSurrender`, a trois issues (cf. `EffetDeSurrender`).
     *
     *  ⚠ « LE POPUP EXISTE » N'EST PAS « LE POPUP EST AFFICHE », ET LA DIFFERENCE A CASSE LE JEU
     *  DEUX FOIS. Mesure du 2026-08-13, journal de `idun.ui.ScreenVisibilityManager` :
     *
     *      montre-debut  BlurredBackgroundScreen
     *      montre-debut  GenericMessagePopup       <- le bouton existe DEJA ici
     *      montre-fin    BlurredBackgroundScreen
     *      montre-fin    GenericMessagePopup       <- il n'est REELLEMENT affiche qu'ici
     *
     *  Appeler `ContinueSurrender` dans cet intervalle termine bien la bataille
     *  (`get_IsBattleActive -> false`) mais laisse le popup EN PLACE et la scene meta jamais
     *  rechargee : jeu vivant, RPC repondants, AUCUN ecran. C'est la lecon de #332 transposee du
     *  clic a l'invoke -- « trouvable » precede « pret », et agir entre les deux se perd.
     *
     *  L'attente doit donc porter sur le signal `montre-fin`, jamais sur la presence d'un
     *  bouton. */
    attendreEffetDeSurrender: (timeoutMs: number) => Promise<EffetDeSurrender>;
    /** L'EFFET de `ContinueSurrender` : le popup COMMENCE A SE CACHER (`cache-debut`).
     *
     *  Un invoke qui rend la main ne prouve rien -- c'est ce signal qui distingue « la
     *  confirmation a porte » de « le jeu est reste sur le popup », qui est exactement l'etat
     *  wedge observe. */
    attendreDisparitionDuPopup: (timeoutMs: number) => Promise<boolean>;
    /** `get_IsBattleActive()` retombe-t-il a `false` ? */
    attendreFinDeBataille: (timeoutMs: number) => Promise<boolean>;
    /** LA SCENE META EST-ELLE (RE)CHARGEE ? -- une `idun.UI.IdunNavigation` vivante.
     *
     *  ⚠ C'EST LE SEUL CRITERE QUI DISTINGUE « SORTI » DE « ECRAN NOIR », et il a fallu deux
     *  erreurs pour y arriver. `get_IsBattleActive() == false` ne suffit PAS : mesure du
     *  2026-08-12, il rend `false` aussi bien apres une retraite reussie qu'apres celle qui
     *  laisse le jeu sans rien afficher. Et « le noeud de campagne est-il la ? » -- le critere
     *  du cycle d'UI -- est FAUX ici : mesure du 2026-08-13, la retraite rend la main sur
     *  `Idun_UI_Navigation` (131 boutons), PAS sur l'ecran campagne. Exiger la campagne, c'est
     *  dire au jeu ou on veut se retrouver ; on charge une bataille et on en sort, le reste ne
     *  nous regarde pas.
     *
     *  `IdunNavigation` vivante est ce que le jeu produit dans les deux bons cas et ce qui
     *  MANQUE dans le mauvais (mesure du run wedge : « aucune instance IdunNavigation
     *  vivante »). */
    attendreMetaChargee: (timeoutMs: number) => Promise<boolean>;
    log: (m: string) => void;
}

/** Le motif NOMME de la sortie du cycle. Un par cause reelle -- jamais un `ok: false` a
 *  interpreter. Il n'y a PLUS de repli sur les clics : ce motif est donc l'erreur meme du
 *  warmup, et la seule chose qui dira ou la chaine s'est arretee. */
export type EntreeProgReason =
    | "capture-et-retraite"
    | "capture-sans-retraite"
    | "etat-de-bataille-non-mesure"
    | "bataille-heritee-non-quittee"
    | "lancement-refuse"
    | "capture-absente"
    | "garde-deja-en-cours-arme"
    | "chargement-en-cours"
    | "porte-de-sortie-absente"
    | "surrender-refuse"
    | "effet-de-surrender-absent"
    | "continue-refuse"
    | "popup-toujours-affiche"
    | "bataille-toujours-active"
    | "meta-non-chargee";

export interface EntreeProgResult {
    ok: boolean;
    reason: EntreeProgReason;
    /** Le pointeur capture, ou `null`. Non nul DES QUE la capture a eu lieu, y compris si la
     *  retraite echoue ensuite : l'appelant doit pouvoir dire « capture obtenue, sortie ratee »,
     *  qui n'est pas « rien obtenu ». */
    capturedAt: string | null;
    /** Le jeu etait-il DEJA en bataille a l'entree (ecran herite du cycle precedent) ? */
    batailleHeritee: boolean;
    steps: EtapeProg[];
}

/** CE QUE L'ON BORNE, ET POURQUOI CES VALEURS-LA.
 *
 * Aucune n'est tiree au jugement : chacune reprend un budget deja mesure ailleurs dans le cycle.
 *
 *   CHARGE  (60 s)  = `thor.Loader.__loadingStep` retombe a 0. Mesure : 10,8 s sur un process
 *                     chaud ; large, parce que c'est le SEUL cran dont le depassement casse le
 *                     jeu, et qu'un chargement a froid est plus lent.
 *   CAPTURE (20 s)  = le chargement de bataille a froid. Mesure : la capture tombe a 2,1 s.
 *   PORTE   (20 s)  = `IdunMainView` nait avec la scene, donc apres la capture.
 *   EFFET    (8 s)  = l'animation d'apparition du popup. Mesure : `montre-fin` en moins de 2 s.
 *   POPUP    (8 s)  = son animation de disparition (`cache-debut`), meme ordre de grandeur.
 *   FIN     (20 s)  = la fin de bataille. Mesure : `get_IsBattleActive` retombe a 2,9 s.
 *   META    (30 s)  = le RE-chargement de la scene meta. Mesure : ecran complet a 6,7 s.
 *
 * Le chemin nominal ne paie aucune de ces bornes : ce sont des plafonds, pas des attentes -- et
 * il n'y a AUCUN repos fixe nulle part. Chaque cran attend un SIGNAL. */
export const PROG_CHARGEMENT_WAIT_MS = 60000;
export const PROG_CAPTURE_WAIT_MS = 20000;
export const PROG_PORTE_WAIT_MS = 20000;
export const PROG_EFFET_WAIT_MS = 8000;
export const PROG_POPUP_WAIT_MS = 8000;
export const PROG_FIN_WAIT_MS = 20000;
export const PROG_META_WAIT_MS = 30000;

/** LA SORTIE DE BATAILLE, en deux appels dont le second est CONDITIONNE PAR L'EFFET DU PREMIER.
 *
 * Rend `null` si le jeu n'est plus en bataille a la fin, sinon le motif NOMME du premier echec.
 * `etiquette` prefixe les steps : le meme geste sert a quitter une bataille HERITEE et a quitter
 * celle qu'on vient de lancer, et confondre les deux dans la trace rendrait le journal illisible. */
async function sortirDeBataille(
    deps: EntreeProgDeps, steps: EtapeProg[], etiquette: string,
): Promise<EntreeProgReason | null> {
    // ⚠ ET DANS CET ORDRE : LA PORTE D'ABORD, LE CHARGEUR ENSUITE. Mesure du 2026-08-13 --
    // interroger le chargeur juste apres l'invoke rend `0`, non parce qu'il a fini mais parce
    // qu'il n'a PAS ENCORE COMMENCE (l'etape ne monte a 1 que vers t=1,1 s). Une garde qui se
    // laisse satisfaire par l'etat d'AVANT le geste ne garde rien. L'instance d'`IdunMainView`,
    // elle, nait avec la scene : quand elle est la, le chargement a bel et bien demarre.
    const porte = await deps.attendrePorteDeSortie(PROG_PORTE_WAIT_MS);
    if (!porte) {
        steps.push({
            step: `${etiquette}-porte-de-sortie`, ok: false,
            info: `aucune instance IdunMainView capturee et vivante apres `
                + `${PROG_PORTE_WAIT_MS} ms -- la scene de bataille n'est pas montee, ou son `
                + "instance a ete detruite (un pointeur epingle survit a l'objet Unity)",
        });
        return "porte-de-sortie-absente";
    }
    steps.push({
        step: `${etiquette}-porte-de-sortie`, ok: true,
        info: "instance IdunMainView capturee et confrontee vivante -- la scene est montee, "
            + "donc le chargeur a DEMARRE : l'interroger maintenant a un sens",
    });

    if (!await deps.attendreChargementTermine(PROG_CHARGEMENT_WAIT_MS)) {
        steps.push({
            step: `${etiquette}-chargement-termine`, ok: false,
            info: `thor.Loader.__loadingStep n'est pas retombe a 0 en ${PROG_CHARGEMENT_WAIT_MS} `
                + "ms (ou n'est pas MESURABLE) -- se retirer maintenant ferait refuser le retour "
                + "au meta en silence, et laisserait le jeu sur le popup sans aucun ecran",
        });
        return "chargement-en-cours";
    }
    steps.push({
        step: `${etiquette}-chargement-termine`, ok: true,
        info: "thor.Loader.__loadingStep = 0 -- le retour au meta ne sera pas refuse",
    });

    const surrender = await deps.invoquerSortie("OnBattleSurrender");
    if (!surrender.ok) {
        steps.push({
            step: `${etiquette}-on-battle-surrender`, ok: false,
            info: `invoke refuse ou en echec : ${surrender.err ?? "?"}`,
        });
        return "surrender-refuse";
    }
    steps.push({
        step: `${etiquette}-on-battle-surrender`, ok: true,
        info: "IdunMainView$$OnBattleSurrender() invoquee -- l'effet reste a MESURER",
    });

    // ⚠ ICI SE JOUE L'INVARIANT DU MODULE. `ContinueSurrender` n'est appelee QUE si l'effet
    // d'`OnBattleSurrender` a ete OBSERVE. Sur `rien`, on ARRETE : appeler la suite sur un etat
    // qu'on ne comprend pas est exactement le geste qui a laisse le jeu sans ecran rendu.
    const effet = await deps.attendreEffetDeSurrender(PROG_EFFET_WAIT_MS);
    if (effet === "bataille-terminee") {
        // `PauseSurrender` a rendu FALSE : il n'a pas differe, la retraite est passee tout droit.
        // Il n'y a plus rien a confirmer -- appeler `ContinueSurrender` ici serait entrer par le
        // milieu sur une bataille deja finie.
        steps.push({
            step: `${etiquette}-effet-de-surrender`, ok: true,
            info: "bataille TERMINEE sans popup -- `PauseSurrender` n'a pas differe, "
                + "`ContinueSurrender` est SANS OBJET et n'est pas appelee",
        });
        deps.log(`[warmup-prog] ${etiquette} : sortie sans popup de confirmation`);
        return await attendreLeMeta(deps, steps, etiquette);
    }
    if (effet === "rien") {
        steps.push({
            step: `${etiquette}-effet-de-surrender`, ok: false,
            info: `ni popup de confirmation ni fin de bataille apres ${PROG_EFFET_WAIT_MS} ms -- `
                + "l'appel a rendu la main sans effet observable. `ContinueSurrender` n'est PAS "
                + "appelee : appelee sans son entree, elle termine la bataille en laissant le jeu "
                + "SANS ECRAN RENDU (mesure #992)",
        });
        return "effet-de-surrender-absent";
    }
    steps.push({
        step: `${etiquette}-effet-de-surrender`, ok: true,
        info: "popup de confirmation PLEINEMENT AFFICHE (`montre-fin`) -- `PauseSurrender` a "
            + "DIFFERE. C'est ce signal, et pas la simple existence du bouton, qui autorise "
            + "la suite",
    });

    const cont = await deps.invoquerSortie("ContinueSurrender");
    if (!cont.ok) {
        steps.push({
            step: `${etiquette}-continue-surrender`, ok: false,
            info: `invoke refuse ou en echec : ${cont.err ?? "?"}`,
        });
        return "continue-refuse";
    }
    steps.push({
        step: `${etiquette}-continue-surrender`, ok: true,
        info: "IdunMainView$$ContinueSurrender() invoquee -- l'effet reste a MESURER",
    });

    // L'EFFET, pas le retour de l'appel. Un `ContinueSurrender` qui rend `ok` en laissant le
    // popup a l'ecran est exactement l'etat wedge mesure : bataille finie, aucun ecran.
    if (!await deps.attendreDisparitionDuPopup(PROG_POPUP_WAIT_MS)) {
        steps.push({
            step: `${etiquette}-popup-se-cache`, ok: false,
            info: `le popup de confirmation ne commence pas a se cacher en ${PROG_POPUP_WAIT_MS} `
                + "ms -- la confirmation n'a pas porte, le jeu reste dessus",
        });
        return "popup-toujours-affiche";
    }
    steps.push({
        step: `${etiquette}-popup-se-cache`, ok: true,
        info: "`cache-debut` sur le popup de confirmation -- la confirmation a porte",
    });

    if (!await deps.attendreFinDeBataille(PROG_FIN_WAIT_MS)) {
        steps.push({
            step: `${etiquette}-fin-de-bataille`, ok: false,
            info: `get_IsBattleActive() ne retombe pas a false en ${PROG_FIN_WAIT_MS} ms`,
        });
        return "bataille-toujours-active";
    }
    steps.push({
        step: `${etiquette}-fin-de-bataille`, ok: true,
        info: "get_IsBattleActive() = false -- NECESSAIRE, mais PAS SUFFISANT",
    });
    return await attendreLeMeta(deps, steps, etiquette);
}

/** LE DERNIER CRAN, et le seul qui separe « sorti » de « ecran noir ».
 *
 * `get_IsBattleActive() == false` est vrai dans les DEUX cas -- mesure du 2026-08-12. Ce qui les
 * separe, c'est que la scene META soit rechargee. On ne demande PAS au jeu ou se retrouver :
 * mesure du 2026-08-13, il rend la main sur `Idun_UI_Navigation` et non sur la campagne, et
 * c'est tres bien. On verifie seulement qu'il rend la main quelque part. */
async function attendreLeMeta(
    deps: EntreeProgDeps, steps: EtapeProg[], etiquette: string,
): Promise<EntreeProgReason | null> {
    if (!await deps.attendreMetaChargee(PROG_META_WAIT_MS)) {
        steps.push({
            step: `${etiquette}-meta-chargee`, ok: false,
            info: `aucune IdunNavigation vivante ${PROG_META_WAIT_MS} ms apres la fin de `
                + "bataille -- la scene meta n'est pas remontee. Le jeu est VIVANT et repond "
                + "aux RPC, mais il n'affiche RIEN : c'est le regime que `thor.Loader$$LoadScene` "
                + "produit quand il refuse un chargement en silence. Relancer le jeu est le seul "
                + "recours",
        });
        return "meta-non-chargee";
    }
    steps.push({
        step: `${etiquette}-meta-chargee`, ok: true,
        info: "IdunNavigation vivante -- la scene meta est remontee, le jeu affiche un ecran",
    });
    return null;
}

/** L'ENTREE + LA CAPTURE + LA RETRAITE, sans toucher a l'ecran.
 *
 * Ne leve jamais : toute panne ressort comme un `reason` nomme, parce que l'appelant doit pouvoir
 * REPLIER sur le pilotage d'UI en DISANT pourquoi -- un repli muet ferait disparaitre la
 * regression le jour ou cette voie cesserait de marcher. */
export async function runEntreeProgrammatique(
    deps: EntreeProgDeps, opts?: { stopAfterCapture?: boolean },
): Promise<EntreeProgResult> {
    const steps: EtapeProg[] = [];
    const rendre = (
        ok: boolean, reason: EntreeProgReason,
        capturedAt: string | null, batailleHeritee: boolean,
    ): EntreeProgResult => ({ ok, reason, capturedAt, batailleHeritee, steps });

    // -- 1. Y A-T-IL DEJA UNE BATAILLE ? On le DEMANDE a la comptabilite du jeu, on ne le deduit
    //    pas de l'etat des ECRANS comme le faisait le harnais jusqu'ici.
    const avant = await deps.enBataille();
    if (avant === null) {
        steps.push({
            step: "prog-etat-initial", ok: false,
            info: "IdunMainView$$get_IsBattleActive() INTROUVABLE -- etat NON MESURE. On ne lance "
                + "pas une bataille sans savoir si une autre tourne : `StartMatch` verifie "
                + "`checkIfAlreadyRunning` et retourne EN SILENCE, donc on attendrait une capture "
                + "qui ne viendrait jamais",
        });
        return rendre(false, "etat-de-bataille-non-mesure", null, false);
    }
    const batailleHeritee = avant;
    steps.push({
        step: "prog-etat-initial", ok: true,
        info: avant ? "une bataille est DEJA active (ecran herite) -- il faut en sortir d'abord"
                    : "aucune bataille active",
    });

    // -- 1bis. L'ECRAN DE BATAILLE HERITE. Meme geste que le cran 1bis du cycle UI, par la voie
    //    native : sans lui la voie programmatique ne serait autonome qu'une fois sur deux, ce qui
    //    est exactement le defaut que le cycle UI a mis deux tranches a reparer.
    if (batailleHeritee) {
        deps.log("[warmup-prog] bataille heritee -- sortie prealable");
        const echec = await sortirDeBataille(deps, steps, "prog-heritee");
        if (echec !== null) return rendre(false, "bataille-heritee-non-quittee", null, true);
    }

    // -- 1ter. LE GARDE RESIDUEL. Arme alors qu'aucune bataille n'existe = residu d'un lancement
    //    avorte, et il fait refuser TOUS les lancements suivants en silence. On le desarme, et on
    //    le DIT -- un nettoyage muet ferait disparaitre la trace d'un cycle precedent casse.
    const garde = await deps.gardeDejaEnCours();
    if (garde === null) {
        steps.push({
            step: "prog-garde-deja-en-cours", ok: false,
            info: "IdunMainView$$get_IsActive() INTROUVABLE -- on ne lance pas sans savoir si le "
                + "garde `checkIfAlreadyRunning` est arme : `StartMatch` retournerait EN SILENCE",
        });
        return rendre(false, "garde-deja-en-cours-arme", null, batailleHeritee);
    }
    if (garde) {
        const d = await deps.desarmerGarde();
        const apres = d.ok ? await deps.gardeDejaEnCours() : null;
        if (apres !== false) {
            steps.push({
                step: "prog-garde-deja-en-cours", ok: false,
                info: "garde `IsActive` ARME sans bataille, et le desarmement n'a pas porte : "
                    + (d.err ?? `get_IsActive rend toujours ${String(apres)}`),
            });
            return rendre(false, "garde-deja-en-cours-arme", null, batailleHeritee);
        }
        steps.push({
            step: "prog-garde-deja-en-cours", ok: true,
            info: "garde `IsActive` etait ARME sans qu'aucune bataille existe -- RESIDU d'un "
                + "lancement avorte, desarme par SetBattleNotRunning(). Sans cela, tous les "
                + "lancements suivants auraient ete refuses EN SILENCE",
        });
    } else {
        steps.push({
            step: "prog-garde-deja-en-cours", ok: true,
            info: "garde `IsActive` non arme -- rien a nettoyer",
        });
    }

    // -- 2. LANCER -- mais PAS PENDANT UN CHARGEMENT DE SCENE, et c'est le SYMETRIQUE exact de
    //    la garde de sortie. Mesure du 2026-08-13 : lancer alors que la scene META finit de se
    //    charger fait refuser `thor.Loader$$LoadBattle` EN SILENCE. Le piege est que la CAPTURE
    //    reussit quand meme -- `StartCampaignMatch` cree la source AVANT d'appeler le chargeur --
    //    donc le cycle se croit en bataille alors qu'aucune scene ne monte, et echoue 20 s plus
    //    loin sur un symptome (`porte-de-sortie-absente`) qui ne nomme pas la cause.
    if (!await deps.attendreChargementTermine(PROG_CHARGEMENT_WAIT_MS)) {
        steps.push({
            step: "prog-chargement-termine", ok: false,
            info: `thor.Loader.__loadingStep n'est pas retombe a 0 en ${PROG_CHARGEMENT_WAIT_MS} `
                + "ms (ou n'est pas MESURABLE) -- lancer maintenant ferait refuser LoadBattle en "
                + "silence : la source serait creee, mais aucune scene de bataille ne monterait",
        });
        return rendre(false, "chargement-en-cours", null, batailleHeritee);
    }
    steps.push({
        step: "prog-chargement-termine", ok: true,
        info: "thor.Loader.__loadingStep = 0 -- LoadBattle ne sera pas refuse",
    });

    // Un invoke qui rend la main ne prouve RIEN : `StartMatch` journalise et RETOURNE quand une
    // bataille tourne deja. C'est `attendreCapture` qui tranche.
    const lance = await deps.lancerBataille();
    if (!lance.ok) {
        steps.push({
            step: "prog-start-campaign-match", ok: false,
            info: `invoke refuse ou en echec : ${lance.err ?? "?"}`,
        });
        return rendre(false, "lancement-refuse", null, batailleHeritee);
    }
    steps.push({
        step: "prog-start-campaign-match", ok: true,
        info: "ViewCommandExecutor$$StartCampaignMatch invoquee -- l'effet reste a MESURER",
    });

    // -- 3. LA CAPTURE, qui est le BUT du warmup.
    const capturedAt = await deps.attendreCapture(PROG_CAPTURE_WAIT_MS);
    if (capturedAt === null) {
        steps.push({
            step: "prog-capture", ok: false,
            info: `CampaignGameModeSource non capturee en ${PROG_CAPTURE_WAIT_MS} ms apres `
                + "l'invoke -- la bataille n'a pas demarre (garde `checkIfAlreadyRunning`, "
                + "arguments refuses, ou chargement plus long que la borne)",
        });
        return rendre(false, "capture-absente", null, batailleHeritee);
    }
    steps.push({
        step: "prog-capture", ok: true,
        info: `CampaignGameModeSource @ ${capturedAt}`,
    });
    deps.log(`[warmup-prog] CGMS capturee @ ${capturedAt} sans un seul clic`);

    // -- 4. `stopAfterCapture` : le but fonctionnel est ATTEINT ici. Le jeu reste en bataille,
    //    et c'est dit -- le cycle suivant devra l'en sortir (cran 1bis, ou notre propre 1bis).
    if (opts?.stopAfterCapture === true) {
        steps.push({
            step: "prog-stop-after-capture", ok: true,
            info: "retraite sautee SUR DEMANDE EXPLICITE -- le jeu reste en bataille",
        });
        return rendre(true, "capture-sans-retraite", capturedAt, batailleHeritee);
    }

    // -- 5. SORTIR. Avant le deploiement, donc SANS STAMINA (`hasSurrenderedBeforeDeployment`).
    const echec = await sortirDeBataille(deps, steps, "prog-retraite");
    if (echec !== null) return rendre(false, echec, capturedAt, batailleHeritee);

    return rendre(true, "capture-et-retraite", capturedAt, batailleHeritee);
}
