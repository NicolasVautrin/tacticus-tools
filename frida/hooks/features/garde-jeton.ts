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
 * CE QUI EST MESURE (session 148, sandbox guerre de guilde, zone Trenches1)
 * ------------------------------------------------------------------------
 * L'ancrage tire UNE FOIS par appui sur START -- jamais par frame -- et `etrangers` est reste
 * a 0, donc le corps n'est pas partage avec une autre methode.
 *
 *   plateau SANS unite du joueur   -> `laisse`, << le jeu refuse deja >>, stage `Setup`
 *   5 unites posees, registre vide -> `bloque`, stage `Setup`      <- la branche qui compte
 *   5 unites posees, sandbox exemptee -> `laisse`, stage `Running` <- LE CONTRE-ESSAI
 *
 * ⚠ C'EST LE CONTRE-ESSAI QUI FAIT LA MESURE, pas le refus. << Reste a `Setup` >> a d'autres
 * causes possibles (pas assez d'unites, HUD non pret, montage incomplet) : seul le fait que le
 * MEME plateau parte quand on retire le seul drapeau qui change etablit que le refus vient de
 * nous. Les deux tirs se lisent dans `decisions`, a 22 s d'intervalle.
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
 * ⛔ CE QUI A CHANGE LE 2026-08-26, ET POURQUOI CE PARAGRAPHE DISAIT L'INVERSE
 * ---------------------------------------------------------------------------
 * Il annoncait : << le registre meurt au reinject, donc chaque mode redemande son montage sandbox
 * avant de pouvoir partir -- c'est le comportement demande >>. Ce n'etait pas un comportement,
 * c'etait un DEFAUT presente comme une intention, et il a coute CINQ departs de campagne refuses
 * d'affilee sur une bataille dont le plateau etait PLEIN. `lineupSource`, interroge sur la source
 * VIVANTE au meme moment, rendait les cinq unites exactement affichees a l'ecran.
 *
 * Deux fautes, distinctes, corrigees toutes les deux :
 *
 *   1. LE PREDICAT CONFONDAIT << JE N'AI RIEN NOTE >> ET << IL N'Y EN A PAS >>. Il ne consultait
 *      que NOTRE registre. Il consulte desormais AUSSI `lineupObservee` -- ce que le NATIF a
 *      rendu, capte passivement a l'ancrage de `lineup-poser`. Et quand cet ancrage n'est pas
 *      arme (le cas par defaut : `lineup-poser` ne s'arme PAS au register), l'absence n'est pas
 *      ETABLIE, donc on LAISSE PASSER en le disant. C'est l'invariant que l'avant-dernier
 *      paragraphe promet deja -- le module ne le tenait pas.
 *
 *   2. L'ANCRAGE DE DEPLOIEMENT NE BLOQUE PLUS DU TOUT, il OBSERVE (`auraitBloque`). Il est
 *      structurellement trop tard : plusieurs modes ont deja depense le jeton quand la phase de
 *      deploiement existe (cf. `docs/rl/case-10047-le-garde-est-trop-tard-en-pvp.md`). Y refuser
 *      n'evite aucune depense -- ca prive d'une partie deja payee. Le refus vit desormais sur les
 *      popups de PREVISUALISATION seules, qui precedent la depense PAR CONSTRUCTION.
 *
 * `gardeJetonArmer {bloquer: false}` leve ce qui reste, sans toucher aux ancrages.
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
import {
    compositionRetenue, estSourceCouverte, lineupObservee, estSourceObservable,
} from "./lineup-poser.js";
import { afficherMessage } from "./message-box.js";
import { Ctx } from "../controller.js";

const NS_QUERY = "IdunBattle.View.FSM";
const CLS_QUERY = "VisualBattleQuery";
const METH = "IsMinUnitAmountToBringToStartBattleReached";
const CHAMP_SOURCE = "_gameModeSource";
/** ⛔ LE SECOND ANCRAGE, ET IL EXISTE PARCE QUE LE PREMIER EST TROP TARD EN PvP (#10047).
 *
 *  Rapporte par l'utilisateur le 2026-08-26 : la popup s'affichait ALORS QUE le jeton etait
 *  deja parti. La premisse du module -- << entrer est GRATUIT, c'est le START qui engage >> --
 *  vient de la chaine CAMPAGNE, et toutes ses mesures avaient ete prises en sandbox guerre de
 *  guilde. `PvpGameModeSource` n'override meme pas `HandleStartMatch` : l'ecran qui precede
 *  (`PvpBattlePreviewPopup`) porte deja le cout (`ShowTokenCost`, `Pvp_BattleButton_OutOfBattleToken`)
 *  et son bouton mene a `PvpProgression$$LoadPvpBattle`, qui parle au serveur AVANT que l'ecran
 *  de deploiement n'existe. Notre predicat de deploiement est en aval de tout ca.
 *
 *  ⚠ ON NE SAIT TOUJOURS PAS OU LE JETON EST PRELEVE EXACTEMENT (corps en dispatch par slot ; le
 *  mesurer couterait un jeton). On n'en a pas besoin : le TAP PRECEDE PAR CONSTRUCTION tout ce
 *  qui est en aval de lui. Bloquer ici est donc plus tot que le prelevement, quel qu'il soit --
 *  c'est une propriete de l'ordre d'appel, pas une hypothese sur la mecanique.
 *
 *  ⛔ ET ON NE `replace` RIEN. Le natif porte deja sa porte de sortie -- `if (success == 0)
 *  return;` en TETE de corps. On force ce parametre a 0, donc on emprunte un chemin que le jeu
 *  prevoit, au lieu d'en inventer un. */
const METH_POPUP = "HandleOnStartBattleTapped";
/**
 * Les popups de previsualisation qu'on ancre, et la source que chacun fait demarrer.
 *
 * ⚠ LA SOURCE EST ECRITE, PAS DERIVEE. Le popup ne la porte pas -- il PRECEDE la bataille, donc
 * il n'existe aucune `VisualBattleQuery` a interroger. Et la deriver du NOM ne marche pas : la
 * famille compte 12 membres dont `WavesBattlePreviewPopup` (source `Onslaught...`),
 * `BattlePreviewPopup` tout court (source `Campaign...`) et `SurvivalBattlePreviewPopup`
 * (source `SurvivalEvent...`). Un prefixe devine faux au moins trois fois.
 *
 * ⛔ ET LA TABLE NE PEUT PAS MENTIR DANS LE SENS DANGEREUX : chaque entree est reconfrontee a
 * `estSourceCouverte` AU MOMENT DU TIR. Une source que `lineup-poser` ne sait pas servir n'est
 * jamais bloquee, quelle que soit cette table -- le refus serait definitif.
 *
 * ⚠ LES 6 AUTRES MEMBRES DE LA FAMILLE RESTENT NON GARDES, ET C'EST DIT (`famillePopups` dans
 * l'etat) : `Survival`, `TreasureBeach`, `LegendaryEvent`, `CampaignEvent`, `Waves`,
 * `LinearHeroEvent` n'ont aucune composition retenable, donc les bloquer enfermerait le mode.
 * Le trou est REPORTE plutot que tu.
 *
 * ⚠ LA CAMPAGNE N'Y EST PAS, DELIBEREMENT : son ancrage de deploiement refuse DEJA avant la
 * depense (c'est la chaine ou la premisse a ete mesuree). L'ajouter ici avancerait le refus sans
 * rien protéger de plus, et toucherait la voie que la chaine de farm emprunte.
 */
const POPUPS: ReadonlyArray<{ ns: string; cls: string; source: string }> = [
    // #10047 : le PvP, ou l'ancrage de deploiement arrive APRES la depense.
    { ns: "idun.Meta.View.Hud", cls: "PvpBattlePreviewPopup", source: "PvpGameModeSource" },
    // La guerre de guilde : meme forme EXACTE au decompile (`if (success == 0) return this;`),
    // et meme raison -- ses tentatives sont limitees, et son popup precede le deploiement.
    { ns: "idun.Meta.View.Hud", cls: "GuildWarsBattlePreviewPopup",
      source: "GuildWarsGameModeSource" },
    { ns: "idun.Meta.View.Hud", cls: "MachinesOfWarEventBattlePreviewPopup",
      source: "MachinesOfWarEventGameModeSource" },
    { ns: "idun.ui.guildBoss.Popups", cls: "GuildBossBattlePreviewPopup",
      source: "GuildBossGameModeSource" },
    { ns: "idun.ui.guildBoss.Popups", cls: "GuildBossSupportingBattlePreviewPopup",
      source: "GuildBossGameModeSource" },
];
/** Les membres de la famille qu'on N'ANCRE PAS, pour que le trou soit lisible. */
const POPUPS_NON_GARDES: readonly string[] = [
    "SurvivalBattlePreviewPopup", "TreasureBeachBattlePreviewPopup",
    "LegendaryEventBattlePreviewPopup", "CampaignEventBattlePreviewPopup",
    "WavesBattlePreviewPopup", "LinearHeroEventBattlePreviewPopup",
    "BattlePreviewPopup (campagne -- garde au deploiement, cf. ci-dessus)",
];
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
const listenersPopup: InvocationListener[] = [];
const popupsPoses: string[] = [];
let firesPopup = 0;
let etrangersPopup = 0;
let bloquesPopup = 0;
let refusArmementPopup: string | null = null;
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
/** Ce que l'ancrage de DEPLOIEMENT aurait refuse s'il bloquait encore. Il n'interdit plus rien
 *  (trop tard pour le jeton, et son predicat confond « pas mesure » et « vide ») -- mais on
 *  compte, sinon on remplacerait un faux refus par un silence. */
let auraitBloque = 0;
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

function prevenirLeJoueur(classeSource: string, suite?: string): void {
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
            + (suite ?? "Le message du jeu juste derriere parle d'un nombre d'unites -- c'est le "
                + "refus par lequel nous passons, pas la vraie raison."),
        okTexte: "Compris",
    })).catch(() => { /* la popup est un confort, jamais une condition du refus */ });
}

/**
 * Le garde POSE SUR LE BOUTON << Battle >> du popup de previsualisation PvP (#10047).
 *
 * Meme discipline que l'ancrage de deploiement, point par point :
 *  - ECHEC OUVERT : toute incertitude laisse passer, et le DIT.
 *  - ON NE BLOQUE QUE CE QU'ON SAIT DEBLOQUER : si `lineup-poser` ne couvre pas
 *    `PvpGameModeSource`, refuser enfermerait le mode sans geste de sortie.
 *  - LE `this` EST VERIFIE : IL2CPP deduplique les corps, et l'ancrage ne doit decider que pour
 *    le sien. Les tirs ecartes sont COMPTES (`etrangersPopup`), pas ignores en silence.
 */
function armerPopup(): Record<string, unknown> {
    if (listenersPopup.length > 0) return { ok: true, deja: true, poses: popupsPoses.slice() };
    const refus: string[] = [];
    for (const p of POPUPS) {
        const k = findClassAnywhere(p.ns, p.cls);
        if (!k) { refus.push(`${p.cls} : classe introuvable -- chemin PERIME`); continue; }
        // Un seul parametre manage : le `bool success` que le corps teste en tete.
        const mi = findMethodByParamCount(k, METH_POPUP, 1);
        if (!mi) { refus.push(`${p.cls}$$${METH_POPUP} a 1 parametre introuvable`); continue; }
        try {
            listenersPopup.push(Interceptor.attach(mi.ptr, {
                onEnter(args) {
                    firesPopup += 1;
                    let classeThis: string | null = null;
                    try { classeThis = s(class_get_name(args[0].readPointer()) as NativePointer); }
                    catch { classeThis = null; }
                    // ⛔ LE `this` DECIDE, PAS L'ANCRAGE. IL2CPP deduplique les corps : un
                    // ancrage pose pour X peut tirer avec un `this` de Y. On refuse alors de
                    // decider, et on COMPTE le tir ecarte.
                    if (classeThis !== p.cls) { etrangersPopup += 1; return; }
                    // Le jeu refuse deja (reponse NON a la confirmation) : rien a faire.
                    if (args[1].toInt32() === 0) {
                        noter("laisse", "le tap arrive deja a `success = 0` -- rien a refuser",
                              p.source, null);
                        return;
                    }
                    if (!estSourceCouverte(p.source)) {
                        noter("laisse", "source NON COUVERTE par `lineup-poser` -- un refus "
                            + "serait DEFINITIF", p.source, null);
                        return;
                    }
                    const retenue = compositionRetenue(p.source);
                    if (retenue !== null) {
                        noter("laisse", `lineup retenue (${retenue.origine})`,
                              p.source, retenue.ids.length);
                        return;
                    }
                    // ⛔ LA SECONDE REPONSE, ET ELLE MANQUAIT. `compositionRetenue` dit ce que
                    // NOUS avons note ; `lineupObservee` dit ce que LE JEU a rendu. Un registre
                    // vide n'est pas un plateau vide -- mesure du 2026-08-26, cinq departs de
                    // campagne refuses alors que la source vivante rendait ses cinq unites.
                    const vue = lineupObservee(p.source);
                    if (vue !== null && vue.length > 0) {
                        noter("laisse", "lineup OBSERVEE sur la source (`GetBattleLineup`) -- rien "
                            + "dans notre registre, mais le jeu en a rendu une", p.source, vue.length);
                        return;
                    }
                    if (!bloquer) {
                        noter("laisse", "AUCUNE lineup retenue -- mais le blocage est DESARME",
                              p.source, null);
                        return;
                    }
                    // ⛔ NON MESURE N'EST PAS ABSENT -- ET C'EST CE CRAN QUI MANQUAIT. L'ancrage de
                    // `lineup-poser` n'est PAS arme au register : dans une session fraiche, ni le
                    // registre ni l'observation n'ont quoi que ce soit a dire. Refuser la-dessus,
                    // c'est refuser sur une IGNORANCE -- exactement ce que l'en-tete de ce module
                    // promet de ne jamais faire (<< toute incertitude LAISSE PASSER >>). Il ne le
                    // tenait pas : c'est la cause des cinq refus du 2026-08-26.
                    if (vue === null && !estSourceObservable(p.source)) {
                        noter("laisse", "NON MESURE : l'ancrage `GetBattleLineup` de "
                            + "`lineup-poser` n'est pas arme pour ce mode, donc l'absence de "
                            + "lineup n'est pas ETABLIE -- on echoue OUVERT", p.source, null);
                        return;
                    }
                    // ⛔ LA PORTE DE SORTIE EST CELLE DU NATIF. `if ((char)success == '\0')
                    // return;` est la premiere instruction du corps : on force le parametre, on
                    // ne detourne rien.
                    args[1] = ptr(0);
                    bloquesPopup += 1;
                    noter("bloque", `AUCUNE lineup retenue -- tap sur << Battle >> de ${p.cls} `
                        + "neutralise AVANT que la bataille ne soit demandee", p.source, null);
                    // ⚠ ICI LA POPUP N'EST PAS UN CONFORT : le jeu n'affichera RIEN (le tap est
                    // simplement avale). Sans elle, le bouton parait casse.
                    prevenirLeJoueur(p.source,
                        "Le bouton ne repond pas parce que NOUS l'avons neutralise, avant que la "
                        + "bataille ne soit demandee au serveur. Le jeu n'affichera aucun "
                        + "message : celui-ci est le seul.");
                },
            }));
            popupsPoses.push(`${p.cls}$$${METH_POPUP} -> ${p.source}`);
        } catch (e) {
            refus.push(`${p.cls} : ${(e as Error).message}`);
        }
    }
    refusArmementPopup = refus.length > 0 ? refus.join(" | ") : null;
    return { ok: listenersPopup.length > 0, poses: popupsPoses.slice(), refus };
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
            // ⛔ CET ANCRAGE N'INTERDIT PLUS RIEN -- IL MESURE. Et ce n'est pas un affaiblissement,
            // c'est la consequence de ce qu'on a etabli deux fois.
            //
            // (1) IL EST STRUCTURELLEMENT TROP TARD (#10047, `case-10047-le-garde-est-trop-tard-en-pvp.md`) :
            // il decide au DEPLOIEMENT, or plusieurs modes ont deja depense le jeton quand cette
            // phase existe. Bloquer la n'evite aucune depense -- ca prive seulement d'une partie
            // deja payee. Le blocage vit desormais sur les popups de PREVISUALISATION, qui
            // precedent la depense PAR CONSTRUCTION.
            //
            // (2) SON PREDICAT CONFOND << JE NE SAIS PAS >> ET << IL N'Y EN A PAS >>. Il interroge
            // NOTRE registre `lineup-poser` ; un reinject le vide, et il conclut alors << AUCUNE
            // lineup >> sur une bataille dont le plateau est PLEIN. Mesure du 2026-08-26 : 5
            // departs de campagne refuses d'affilee alors que `lineupSource` rendait, sur la
            // source VIVANTE, les 5 unites exactement affichees a l'ecran. C'est le tri-etat
            // rabattu sur zero que tout le reste du depot interdit.
            //
            // ⚠ ON GARDE LA MESURE, ET C'EST TOUT L'INTERET. `auraitBloque` compte ce que
            // l'ancien regime aurait refuse : sans lui, on remplacerait un faux refus par un
            // silence, et on ne saurait plus jamais combien de fois le predicat se trompe.
            auraitBloque += 1;
            noter("laisse", "OBSERVATION PURE : aucune lineup dans NOTRE registre -- mais cet "
                + "ancrage est trop tard pour proteger un jeton, et un registre vide ne prouve "
                + "pas un plateau vide. Le refus vit sur les popups de previsualisation.",
                  classeSource, null);
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
    // ⛔ ET LE SECOND, SUR LE BOUTON DU POPUP PvP. Le premier ne protege PAS ce mode : il decide
    // au deploiement, donc apres que la bataille a ete demandee au serveur (#10047).
    armerPopup();

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
        // ⚠ `bloques` est desormais structurellement 0 : l'ancrage de DEPLOIEMENT n'interdit plus
        // rien (trop tard pour le jeton, et son predicat confondait « pas mesure » et « vide »).
        // `auraitBloque` compte ce que l'ancien regime aurait refuse -- sans lui on aurait
        // remplace un faux refus par un silence.
        auraitBloque,
        // Le second ancrage a ses PROPRES compteurs : les fondre dans les premiers rendrait
        // indistinguable << le popup n'a jamais tire >> de << le deploiement n'a jamais tire >>,
        // et c'est exactement la question qu'on se pose apres #10047.
        popupsDePrevisualisation: {
            poses: popupsPoses.slice(),
            refusArmement: refusArmementPopup,
            fires: firesPopup,
            etrangers: etrangersPopup,
            bloques: bloquesPopup,
            // ⚠ LE TROU EST PUBLIE. Ces modes-la ne sont PAS gardes -- `lineup-poser` ne sait
            // rien y retenir, donc un refus y serait definitif. Les taire ferait lire une
            // couverture qui n'existe pas.
            famillePopupsNonGardee: POPUPS_NON_GARDES,
        },
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
        const rp = armerPopup();
        return { ...r, arme: listener !== null, bloquer, popup, traiterLaSandboxCommeLive,
                 popupsDePrevisualisation: rp };
    };
}
