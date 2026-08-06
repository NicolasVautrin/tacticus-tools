// #390 — LE REMEDE DU WEDGE POST-RETRAITE, applique par le cycle lui-meme.
//
// CE QUE CE MODULE REPARE. Le cran 8 du warmup (`wait-back-to-campaign`) attendait
// 45 s le retour de l'ecran campagne, et s'il ne venait pas rendait un echec dont le
// message disait litteralement « try rpc navToCampaign, else relaunch the game ».
// Le cycle NOMMAIT son remede dans son propre message d'erreur et attendait qu'un
// humain le tape. Le suivi de tache porte `navToCampaign 2/2` : les deux fois ou il a
// ete essaye a la main, il a debloque.
//
// POURQUOI CE MODULE EST SEPARE ET PUR. Le cycle complet n'est pas rejouable a volonte
// (il pilote l'UI du jeu, et une reinjection est interdite tant qu'une session est
// partagee). La LOGIQUE du remede — ordre des volets, bornes, libelles, distinction des
// etats — est donc isolee ici, sans un seul acces a Frida : ses effets sont injectes.
// `frida/tools/probe-390-wedge-remedy.ts` l'exerce hors Frida avec des doublures qui
// COMPTENT leurs appels. Meme decoupe que `host/warm-gate.ts` + `warm-gate.probe.ts`.
//
// CE QUE LA RE ETABLIT, ET QUI AUTORISE CE REMEDE (build rnca9r7q6c) :
//
//   - Le retour post-retraite est un CHARGEMENT DE SCENE, pas une navigation d'ecran :
//     `thor.Idun.Source.Thor.Menu.PauseMenu$$OnBackToMapPressed` ->
//     `IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$PauseSurrender` ->
//     `idun.IdunMainView$$ProcessFinishSurrender` -> `idun.IdunMainView$$CleanupBattle`
//     -> `idun.IdunMainView$$EndBattleAndGoToMeta` -> `thor.Loader$$LoadBackToMeta` ->
//     `thor.Loader$$LoadMeta` -> `thor.Loader$$LoadMetaScene` -> `thor.Loader$$LoadScene`.
//     `idun.UI.IdunNavigation$$ToCampaign` n'est sur AUCUN maillon de cette chaine —
//     ses quatre appelants sont `idun.Tutorials.TutorialManager$$StartTutorial` et les
//     trois `idun.shared.commands.ViewCommandExecutor$$ToCampaign` /
//     `$$ToCampaignBattle` / `$$ToDeepLink`. Le remede n'est donc PAS « rejouer ce que
//     le jeu fait » : c'est une voie DISTINCTE, qui agit sur la scene meta une fois
//     chargee.
//
//   - `thor.Loader$$LoadScene` REFUSE EN SILENCE de charger quand un chargement est
//     deja en cours (`_scenesToLoad.Count >= 1` ou `thor.Loader$$IsLoadingInternal`,
//     c.-a-d. `_loadingStep > 0`) : il journalise par
//     `idun.Idun.Source.Util.Logging.IdunViewLogger$$Log` et retourne. Dans ce regime
//     la scene meta n'existe pas, donc `IdunNavigation` non plus : le remede est
//     INAPPLICABLE, et c'est un etat a NOMMER, pas a reessayer.
//
//   - `idun.UI.IdunNavigation$$ToCampaign` = `UnityEngine.PlayerPrefs$$SetString` (dernier
//     onglet) + `idun.UI.Screens.CampaignScreen.IdunCampaignScreen$$SetCampaignToShow` +
//     `idun.UI.IdunNavigation$$ShowScreenAndHideOthers(screen, null, createScreenInstance:
//     true)`. AUCUN court-circuit « deja sur cet ecran » dans le decompile : elle
//     reexecute inconditionnellement, et masque les autres ecrans. C'est ce qui la rend
//     capable de sortir d'un ecran meta qui n'est pas la campagne.
//
// LES TROIS REGIMES, ET POURQUOI LE REMEDE A DEUX VOLETS ORDONNES :
//
//   (1) scene meta absente        -> ToCampaign inapplicable  -> `scene-meta-absente`
//   (2) scene meta chargee, mais pas sur l'ecran campagne     -> volet B (ToCampaign)
//   (3) campagne remontee mais MASQUEE PAR UN POPUP           -> volet A (fermeture)
//
// Le regime (3) n'est pas un etat du jeu mais un angle mort de NOTRE detecteur :
// `enumerateButtons(r, false)` ne retient que les boutons `active && interactable`, et
// un popup modal desactive tout ce qui est derriere lui — c'est exactement ce que
// l'etape 1 du warmup (`dismiss-popups`) repare a l'ENTREE du cycle, et que le cran 8
// ne faisait pas a la SORTIE. `idun.UI.IdunNavigation` porte precisement une famille de
// popups de retour-au-meta (`$$ShowDelayedRewards`,
// `$$ShowLiveEventInterstitialPopupIfNecessary`, `$$ShowOfferInterstitialPopupIfNecessary`,
// `$$ShowCampaignUnlockedIfNecessary`, `$$ShowPowerLevelUpSequenceScreenIfNecessary`),
// tous invoques par delegate — donc invisibles a une xref statique. Le regime (3) reste
// une HYPOTHESE non mesuree : ce qui est etabli, c'est le filtre du detecteur et
// l'existence de ces popups, pas qu'ils soient la cause du wedge observe.
//
// C'EST AUSSI L'INSTRUMENT QUI TRANCHERA. Aujourd'hui personne ne sait lequel des trois
// regimes se produit. Le remede le DIT : `reason` nomme celui qui a porte. Au prochain
// wedge, `steps` repond a la question au lieu de la reposer.

/** Ce que rend une tentative d'invoquer `idun.UI.IdunNavigation$$ToCampaign`.
 *
 * TROIS cas, jamais un booleen : `no-nav-instance` (la scene meta n'est pas chargee) et
 * `error` (l'invoke a leve) sont des causes DIFFERENTES qui appellent des conduites
 * differentes — la premiere est definitive pour ce cycle, la seconde peut etre
 * transitoire. Un `ok: false` unique les confondrait, et c'est ce genre de sentinelle
 * qui fait diagnostiquer la mauvaise cause. */
export type NavOutcome =
    | { kind: "ok"; navInstance: string }
    | { kind: "no-nav-instance" }
    | { kind: "error"; err: string };

/** Les effets que le remede a besoin de produire, injectes par l'appelant.
 * Aucun d'eux n'est implemente ici : c'est ce qui rend ce module executable hors
 * du process de jeu. */
export interface WedgeRemedyDeps {
    /** Ferme les popups modaux ouverts. Rend les noms fermes (vide si aucun). */
    dismissPopups: () => Promise<string[]>;
    /** Invoque la nav interne du jeu vers la campagne Indomitus. */
    navToCampaign: () => Promise<NavOutcome>;
    /** `true` des qu'un noeud de campagne redevient actif+interactable, au plus tard
     * apres `timeoutMs`. */
    campaignVisible: (timeoutMs: number) => Promise<boolean>;
    /** Journal de diagnostic. */
    log: (msg: string) => void;
}

export interface WedgeRemedyStep {
    step: string;
    ok: boolean;
    info?: string;
}

/** Le motif NOMME de la sortie du remede. Un par cause reelle — jamais un code de
 * retour a interpreter. */
export type WedgeRemedyReason =
    | "campagne-remontee-apres-fermeture-de-popup"
    | "campagne-remontee-apres-nav-to-campaign"
    | "scene-meta-absente"
    | "nav-to-campaign-a-leve"
    | "remede-epuise";

export interface WedgeRemedyResult {
    recovered: boolean;
    reason: WedgeRemedyReason;
    /** Trace lisible : c'est elle qui distingue « remede tente et sans effet » de
     * « remede non tente » — l'absence totale de step `wedge-remedy-*` signifie que le
     * remede n'a pas tourne. */
    steps: WedgeRemedyStep[];
    /** Combien de tours ont ete joues (<= WEDGE_REMEDY_ATTEMPTS). */
    attempts: number;
}

/** CE QUE L'ON BORNE, ET POURQUOI ON LE BORNE.
 *
 * Un retry non borne transformerait un wedge VISIBLE (echec en 45 s, message explicite)
 * en attente muette — strictement pire que le defaut qu'on repare. Les trois constantes
 * ci-dessous sont donc le budget MAXIMAL que le remede peut ajouter au cycle, et il
 * s'ecrit en clair : 2 tours x (8 s apres fermeture de popup + 12 s apres nav) = 40 s au
 * pire, en plus des 45 s d'attente initiale. Le chemin nominal, lui, ne les paie pas :
 * le remede n'est atteint qu'apres l'echec du cran 8.
 *
 * DEUX tours et pas trois : le remede n'a que deux leviers, et un troisieme tour ne
 * ferait que les rejouer a l'identique. Il vaut pour le cas ou fermer un popup en revele
 * un second (meme raison que la boucle de 3 de l'etape 1 du warmup).
 *
 * 12 s pour la nav : c'est `CLICK_EFFECT_TIMEOUT_MS` du warmup, mesure pour couvrir le
 * dechargement/rechargement de scene. 8 s apres une fermeture de popup : il n'y a la
 * qu'une animation de teardown a laisser passer, pas un chargement. */
export const WEDGE_REMEDY_ATTEMPTS = 2;
export const WEDGE_REMEDY_POPUP_WAIT_MS = 8000;
export const WEDGE_REMEDY_NAV_WAIT_MS = 12000;

/** Applique le remede au wedge post-retraite. Ne leve jamais : toute panne ressort
 * comme un `reason` nomme, parce qu'un remede qui explose en silence serait exactement
 * le defaut qu'il repare. */
export async function runWedgeRemedy(
    deps: WedgeRemedyDeps,
): Promise<WedgeRemedyResult> {
    const steps: WedgeRemedyStep[] = [];
    let navThrew: string | null = null;
    let attempts = 0;

    for (let attempt = 1; attempt <= WEDGE_REMEDY_ATTEMPTS; attempt++) {
        attempts = attempt;
        const tag = `${attempt}/${WEDGE_REMEDY_ATTEMPTS}`;

        // --- Volet A : fermer les popups modaux (regime 3).
        // Le meme geste que l'etape 1 du cycle, applique a la SORTIE. On ne paie la
        // re-attente que si quelque chose a REELLEMENT ete ferme : sans popup ferme,
        // rien n'a change et attendre 8 s serait du temps jete.
        let dismissed: string[] = [];
        try {
            dismissed = await deps.dismissPopups();
        } catch (e) {
            steps.push({
                step: "wedge-remedy-dismiss-popups", ok: false,
                info: `tentative ${tag} : ERREUR ${(e as Error).message}`,
            });
        }
        if (dismissed.length > 0) {
            steps.push({
                step: "wedge-remedy-dismiss-popups", ok: true,
                info: `tentative ${tag} : ferme ${dismissed.join(",")}`,
            });
            deps.log(`[warmup-wedge] ${tag} popup(s) ferme(s) : ${dismissed.join(",")}`);
            if (await deps.campaignVisible(WEDGE_REMEDY_POPUP_WAIT_MS)) {
                steps.push({
                    step: "wedge-remedy-outcome", ok: true,
                    info: "campagne remontee apres fermeture de popup -- le cran 8 "
                        + "etait aveugle, pas le jeu bloque",
                });
                return {
                    recovered: true,
                    reason: "campagne-remontee-apres-fermeture-de-popup",
                    steps, attempts,
                };
            }
        } else {
            steps.push({
                step: "wedge-remedy-dismiss-popups", ok: true,
                info: `tentative ${tag} : aucun popup a fermer`,
            });
        }

        // --- Volet B : la nav interne du jeu (regime 2).
        const nav = await deps.navToCampaign();
        if (nav.kind === "no-nav-instance") {
            // ARRET IMMEDIAT, et ce n'est pas un abandon : sans scene meta chargee il
            // n'existe aucune instance a piloter, donc aucun tour supplementaire ne peut
            // changer quoi que ce soit. Reessayer ici ne ferait que retarder le
            // diagnostic vrai.
            steps.push({
                step: "wedge-remedy-nav-to-campaign", ok: false,
                info: `tentative ${tag} : INAPPLICABLE -- aucune instance `
                    + "IdunNavigation vivante, donc la scene meta n'est pas chargee "
                    + "(thor.Loader$$LoadScene refuse en silence quand un chargement "
                    + "est deja en cours)",
            });
            steps.push({
                step: "wedge-remedy-outcome", ok: false,
                info: "remede INAPPLICABLE : relancer le jeu est le seul recours",
            });
            deps.log("[warmup-wedge] scene meta absente -- remede inapplicable");
            return { recovered: false, reason: "scene-meta-absente", steps, attempts };
        }
        if (nav.kind === "error") {
            // Une levee peut etre transitoire (ecran en cours de construction) : on
            // retente, mais on RETIENT le motif pour ne pas le rendre comme un simple
            // epuisement de tentatives.
            navThrew = nav.err;
            steps.push({
                step: "wedge-remedy-nav-to-campaign", ok: false,
                info: `tentative ${tag} : ERREUR ${nav.err}`,
            });
            deps.log(`[warmup-wedge] ${tag} ToCampaign a leve : ${nav.err}`);
            continue;
        }

        steps.push({
            step: "wedge-remedy-nav-to-campaign", ok: true,
            info: `tentative ${tag} : ToCampaign invoquee @${nav.navInstance}`,
        });
        if (await deps.campaignVisible(WEDGE_REMEDY_NAV_WAIT_MS)) {
            steps.push({
                step: "wedge-remedy-outcome", ok: true,
                info: "campagne remontee apres nav-to-campaign",
            });
            return {
                recovered: true,
                reason: "campagne-remontee-apres-nav-to-campaign",
                steps, attempts,
            };
        }
        deps.log(`[warmup-wedge] ${tag} campagne toujours absente apres ToCampaign`);
    }

    const reason: WedgeRemedyReason =
        navThrew !== null ? "nav-to-campaign-a-leve" : "remede-epuise";
    steps.push({
        step: "wedge-remedy-outcome", ok: false,
        info: reason === "nav-to-campaign-a-leve"
            ? `ToCampaign a leve a chaque tentative : ${navThrew}`
            : `${WEDGE_REMEDY_ATTEMPTS} tentative(s) appliquees, campagne toujours `
                + "absente -- ni popup ni nav n'expliquent cet etat",
    });
    return { recovered: false, reason, steps, attempts };
}
