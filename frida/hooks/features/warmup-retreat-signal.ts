// #390-r2 — LA CHAINE DE RETRAITE SUR LE SIGNAL, plus sur le sondage.
//
// CE QUE CE MODULE REMPLACE. Apres le clic de confirmation, `retreatToCampaign` demandait
// toutes les 250 ms a l'UI « le noeud de campagne est-il la ? », puis « une instance
// IdunNavigation est-elle vivante ? ». Deux budgets de 12 s tires au jugement, et un warmup
// VERT ne disait RIEN de ce qui s'etait passe entre les deux : campagne remontee seule, ou
// frame intersticielle traversee ? Personne ne pouvait le dire.
//
// LE SIGNAL EXISTAIT DEJA DANS LE DEPOT : `features/ui-windows.ts` ancre les cinq points de
// `idun.ui.ScreenVisibilityManager` et note chaque transition avec son `GuiId` NOMME.
//
// CE QUE LA MESURE ETABLIT (build rnca9r7q6c, session 73, DEUX cycles de warmup complets
// consecutifs -- 28 transitions chacun, sequences IDENTIQUES) :
//
//     #11  inscrit      PauseMenu       <- l'ecran de pause s'inscrit : on ENTRE en bataille
//     ...
//     #23  cache-debut  MessagePopup    <- la confirmation de retraite cede la place
//     #24  retire       <wrapper>
//     #25  cache-debut  ChestScreen
//     #26  retire       <wrapper>
//     #27  retire       PauseMenu       <- l'ecran de pause est retire : on est SORTI
//     #28  cache-debut  ChestScreen
//     (plus rien)
//
// D'ou le signal retenu : `ScreenVisibilityManager$$Unregister` portant `GuiId.PauseMenu`.
// Il est SYMETRIQUE de l'inscription d'entree (#11), il est NOMME, et il est reproductible.
//
// ⚠ CE QUE LA MESURE REFUTE, ET QU'IL NE FAUT PAS REINTRODUIRE :
//
//   - « attendre que l'ecran de CAMPAGNE se montre ». Il n'y a AUCUN `montre-debut`/`montre-fin`
//     de `GuiId.Campaign` au retour -- l'ecran campagne est `retire` a l'entree en bataille
//     (#7) et ne se reinscrit pas dans les deux cycles mesures. Fonder la detection dessus
//     aurait rendu le plafond systematique, donc un faux « frame intersticielle » a chaque
//     warmup.
//   - « la nav est vivante » comme preuve de sortie. Mesure anterieure (#390) : juste apres le
//     remplacement du popup, l'invoke rend `no live IdunNavigation instance`.
//
// ⚠ ET CE QUE LE JOURNAL VOIT, LE SONDAGE `uiWindows` NE LE VOIT PAS. Au meme instant,
// `FindObjectsByType(ScreenVisibility, Include)` rend 8 ecrans sans AUCUN `Campaign`, alors que
// `#7 retire Campaign` prouve qu'il en existait un : `Register` prend une INTERFACE
// (`idun.ui.IScreenVisibility`), donc des implementations qui ne sont pas des `ScreenVisibility`
// MonoBehaviour passent par le manager sans etre enumerables. Le journal est strictement plus
// complet -- c'est une raison de plus de detecter par lui.
//
// POURQUOI CE MODULE EST SEPARE ET PUR. Meme decoupe que `warmup-wedge-remedy.ts` : le cycle
// pilote l'UI du jeu et n'est pas rejouable a volonte (une reinjection est interdite tant
// qu'une session est partagee). La LOGIQUE -- ordre des etapes, motifs, plafonds, ce qui est
// NOMME -- vit donc ici sans un seul acces a Frida, et `frida/tools/probe-390-r2-signal-retraite.ts`
// l'exerce avec des doublures qui COMPTENT leurs appels.

/** La forme d'une transition, telle que `ui-windows.ts` la diffuse. Redeclaree ici (et non
 *  importee) pour garder ce module executable hors Frida : TypeScript est structurel, donc
 *  l'objet reel est accepte tel quel. */
export interface TransitionVue {
    quoi: string;
    gui: { v: number | null; nom: string | null };
    classe: string | null;
}

/** Le libelle que `ui-windows.ts` pose sur `ScreenVisibilityManager$$Unregister`.
 *  ⚠ DUPLIQUE de `TRANSITION.retire` par necessite (ce module ne peut pas importer un module
 *  Frida) : l'etage 2 du probe garde les deux appariés. */
export const TRANSITION_RETRAIT = "retire";
/** Idem pour `$$HandleOnScreenStartedShowing` -- c'est lui qui NOMME les frames traversees. */
export const TRANSITION_MONTRE_DEBUT = "montre-debut";

/** L'ecran dont le RETRAIT signale la sortie de bataille, par son MEMBRE d'enum
 *  (`idun.tracking.GuiId.PauseMenu`) -- jamais son ordinal, qui serait juste aujourd'hui et
 *  faux en silence au prochain build. */
export const GUI_ECRAN_DE_PAUSE = "PauseMenu";

/** LE PLAFOND EST UN FILET, PAS UN INSTRUMENT. Il ne mesure rien : la detection est un push.
 *  Il est dimensionne sur le phenomene physique qu'il doit couvrir -- une frame de CHARGEMENT
 *  s'intercale entre la confirmation et le retrait (`cache-debut` encadre les `retire` dans la
 *  sequence mesuree), et un chargement de scene « can exceed 30s on a busy frame budget ».
 *  C'est exactement le budget que le cran 8 du cycle (`wait-back-to-campaign`) s'accorde deja
 *  pour LE MEME phenomene : deux budgets differents pour un meme chargement ne se justifieraient
 *  par rien. Sur le chemin nominal il n'est jamais paye -- le signal arrive avant. */
export const RETREAT_SIGNAL_WAIT_MS = 45000;

/** Le motif NOMME de la sortie de la chaine. Un par cause reelle, jamais un code a interpreter
 *  -- meme discipline que `WedgeRemedyReason`. Les motifs `signal-absent-*` disent TOUS que le
 *  signal n'est pas venu ET ce que le filet a trouve : les confondre ferait chercher la
 *  mauvaise cause. */
export type RetreatReason =
    | "clics-de-retraite-en-echec"
    | "sortie-signalee"
    | "signal-indisponible-campagne-deja-la"
    | "signal-indisponible-nav-a-repris"
    | "signal-absent-campagne-deja-la"
    | "signal-absent-nav-a-repris"
    | "signal-absent-scene-meta-absente"
    | "signal-absent-nav-a-leve"
    | "signal-absent-campagne-jamais-remontee";

/** Ce que rend une tentative d'invoquer `idun.UI.IdunNavigation$$ToCampaign`. Meme forme que
 *  dans `warmup-wedge-remedy.ts` -- TROIS cas, jamais un booleen. */
export type NavOutcome =
    | { kind: "ok"; navInstance: string }
    | { kind: "no-nav-instance" }
    | { kind: "error"; err: string };

/** L'ECOUTE des transitions d'ecran, injectee. `ancrages === null` = le signal N'EXISTE PAS
 *  (classe introuvable) : la chaine le DIT et passe au filet, elle ne fabrique pas un vert. */
export interface EcouteTransitions {
    ancrages: number | null;
    vues: () => readonly TransitionVue[];
    attendre: (
        pred: (t: TransitionVue) => boolean, plafondMs: number, depuis?: number,
    ) => Promise<TransitionVue | null>;
}

export interface RetreatDeps {
    /** Joue `pause -> retraite -> confirmation`, chaque clic valide par son EFFET.
     *  Rend `null` si les trois ont porte, sinon le motif du premier echec. */
    clicsDeRetraite: () => Promise<string | null>;
    ecoute: EcouteTransitions;
    /** UNE lecture, pas un sondage : le noeud de campagne est-il actif+interactable ? */
    noeudCampagnePresent: () => Promise<boolean>;
    /** FILET seulement : attend une instance `IdunNavigation` vivante, au plus `ms`. */
    attendreNavVivante: (ms: number) => Promise<boolean>;
    navToCampaign: () => Promise<NavOutcome>;
    /** FILET seulement : attend le noeud de campagne, au plus `ms`. */
    attendreNoeudCampagne: (ms: number) => Promise<boolean>;
    log: (msg: string) => void;
}

export interface RetreatResult {
    /** `null` = la retraite a abouti. Sinon le motif, deja redige pour l'operateur. */
    err: string | null;
    reason: RetreatReason;
    /** CE QUE LE STEP DOIT DIRE : la branche prise ET les frames traversees, NOMMEES.
     *  C'est la reponse a « sur un warmup vert, la campagne est-elle remontee seule ? ». */
    info: string;
    /** Les frames MONTREES entre le clic de confirmation et la sortie, `GuiId (classe)`. */
    framesTraversees: string[];
}

/** `GuiId (classe)` -- les DEUX, parce qu'aucun des deux ne suffit. Le `GuiId` est lu a
 *  l'offset de `idun.ui.ScreenVisibility` sur un objet recu par une INTERFACE : quand l'objet
 *  n'est pas de cette classe, l'entier est arbitraire (mesure : `-1988785488`, deux fois par
 *  cycle). La classe est ce qui permet de le voir. */
export function nommerFrame(t: TransitionVue): string {
    const gui = t.gui.nom ?? (t.gui.v === null ? "gui-illisible" : `ordinal ${t.gui.v}`);
    return t.classe === null ? gui : `${gui} (${t.classe})`;
}

/** Vrai quand la transition est le RETRAIT de l'ecran de pause -- la sortie de bataille. */
export function estSortieDeBataille(t: TransitionVue): boolean {
    return t.quoi === TRANSITION_RETRAIT && t.gui.nom === GUI_ECRAN_DE_PAUSE;
}

function framesMontrees(
    vues: readonly TransitionVue[], depuis: number,
): string[] {
    const out: string[] = [];
    for (let i = depuis; i < vues.length; i++) {
        const t = vues[i] as TransitionVue;
        if (t.quoi === TRANSITION_MONTRE_DEBUT) out.push(nommerFrame(t));
    }
    return out;
}

function direFrames(frames: string[]): string {
    return frames.length === 0
        ? "aucune frame montree entre la confirmation et la sortie"
        : `frame(s) traversee(s) : ${frames.join(" -> ")}`;
}

/** Le FILET, et rien d'autre : l'ancien mecanisme, atteint UNIQUEMENT quand le signal n'a pas
 *  pu jouer. Il garde ses propres motifs pour qu'on sache POURQUOI on y est tombe. */
async function filet(
    deps: RetreatDeps, prefixe: string, suffixe: "-indisponible" | "-absent",
    frames: string[],
): Promise<RetreatResult> {
    const dit = direFrames(frames);
    const base = (r: string): RetreatReason => `signal${suffixe}-${r}` as RetreatReason;

    if (await deps.noeudCampagnePresent()) {
        return {
            err: null, reason: base("campagne-deja-la"), framesTraversees: frames,
            info: `${prefixe} ; le noeud de campagne etait deja monte -- ${dit}`,
        };
    }
    deps.log(`[warmup-retraite] ${prefixe} -- filet : attente de la nav `
        + `(${RETREAT_SIGNAL_WAIT_MS} ms) puis ToCampaign`);
    if (!await deps.attendreNavVivante(RETREAT_SIGNAL_WAIT_MS)) {
        return {
            err: `${prefixe} ; NI le retrait de l'ecran de pause, NI le noeud de campagne, `
                + `NI une instance IdunNavigation vivante en ${RETREAT_SIGNAL_WAIT_MS} ms `
                + `-- scene meta non rechargee (${dit})`,
            reason: base("scene-meta-absente"), info: dit, framesTraversees: frames,
        };
    }
    // La campagne a pu remonter pendant cette attente : `ToCampaign` est idempotente, mais
    // ne l'appelons pas pour rien.
    if (await deps.noeudCampagnePresent()) {
        return {
            err: null, reason: base("campagne-deja-la"), framesTraversees: frames,
            info: `${prefixe} ; campagne remontee pendant l'attente de la nav -- ${dit}`,
        };
    }
    const nav = await deps.navToCampaign();
    if (nav.kind === "no-nav-instance") {
        return {
            err: `${prefixe} ; nav declaree vivante puis introuvable a l'invoke -- scene meta `
                + `en cours de dechargement (${dit})`,
            reason: base("scene-meta-absente"), info: dit, framesTraversees: frames,
        };
    }
    if (nav.kind === "error") {
        return {
            err: `${prefixe} ; nav vivante mais ToCampaign a leve : ${nav.err} (${dit})`,
            reason: base("nav-a-leve"), info: dit, framesTraversees: frames,
        };
    }
    if (!await deps.attendreNoeudCampagne(RETREAT_SIGNAL_WAIT_MS)) {
        return {
            err: `${prefixe} ; ToCampaign invoquee @${nav.navInstance} mais le noeud de `
                + `campagne n'est pas monte en ${RETREAT_SIGNAL_WAIT_MS} ms (${dit})`,
            reason: base("campagne-jamais-remontee"), info: dit, framesTraversees: frames,
        };
    }
    return {
        err: null, reason: base("nav-a-repris"), framesTraversees: frames,
        info: `${prefixe} ; campagne ramenee par ToCampaign @${nav.navInstance} -- ${dit}`,
    };
}

/** `pause -> retraite -> confirmation`, puis LE SIGNAL. Ne leve jamais : toute panne ressort
 *  comme un `reason` nomme. */
export async function runRetreatToCampaign(
    deps: RetreatDeps,
): Promise<RetreatResult> {
    const clics = await deps.clicsDeRetraite();
    if (clics !== null) {
        return {
            err: clics, reason: "clics-de-retraite-en-echec",
            info: `chaine de clics interrompue : ${clics}`, framesTraversees: [],
        };
    }

    // REPERE : tout ce qui suit est POSTERIEUR au clic de confirmation. Sans lui, les frames
    // de la chaine elle-meme (menu pause, popup de confirmation) seraient comptees comme des
    // frames « traversees », ce qui est exactement l'inverse de ce qu'on cherche a nommer.
    const repere = deps.ecoute.vues().length;

    if (deps.ecoute.ancrages === null) {
        // TRI-ETAT : pas d'ancrage = pas de signal. On le DIT et on passe au filet -- rendre
        // un vert ici ferait passer une panne de capteur pour une mesure.
        deps.log("[warmup-retraite] AUCUN ancrage sur ScreenVisibilityManager -- le signal de "
            + "sortie de bataille est indisponible, repli sur le filet");
        return filet(deps, "signal INDISPONIBLE (aucun ancrage sur "
            + "idun.ui.ScreenVisibilityManager)", "-indisponible", []);
    }

    const sortie = await deps.ecoute.attendre(
        estSortieDeBataille, RETREAT_SIGNAL_WAIT_MS, repere);
    const frames = framesMontrees(deps.ecoute.vues(), repere);

    if (sortie !== null) {
        // C'EST FINI. Le retrait de l'ecran de pause EST la sortie de bataille ; on ne
        // reverifie pas derriere lui avec un sondage, ce qui reintroduirait exactement le
        // mecanisme que cette tranche remplace. Le noeud de campagne, lui, reste garde en
        // aval par le cran 8 du cycle.
        const info = `sortie de bataille SIGNALEE par ${TRANSITION_RETRAIT}/`
            + `${nommerFrame(sortie)} apres ${deps.ecoute.vues().length - repere} `
            + `transition(s) ; ${direFrames(frames)}`;
        deps.log(`[warmup-retraite] ${info}`);
        return { err: null, reason: "sortie-signalee", info, framesTraversees: frames };
    }

    deps.log(`[warmup-retraite] signal ${TRANSITION_RETRAIT}/${GUI_ECRAN_DE_PAUSE} ABSENT `
        + `apres ${RETREAT_SIGNAL_WAIT_MS} ms -- ${direFrames(frames)}`);
    return filet(deps, `signal ${TRANSITION_RETRAIT}/${GUI_ECRAN_DE_PAUSE} absent en `
        + `${RETREAT_SIGNAL_WAIT_MS} ms`, "-absent", frames);
}
