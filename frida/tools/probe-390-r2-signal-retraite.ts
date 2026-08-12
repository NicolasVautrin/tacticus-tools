/* Garde de #390-r2 -- la chaine de retraite DETECTE PAR SIGNAL et NOMME ce qu'elle traverse.
 *
 * Lancement (depuis `frida/`) :
 *     npx tsx tools/probe-390-r2-signal-retraite.ts
 *     node node_modules/tsx/dist/cli.mjs tools/probe-390-r2-signal-retraite.ts
 *
 * POURQUOI CE HARNAIS EXISTE -- meme raison que `probe-390-wedge-remedy.ts`, dont il reprend
 * le patron. Le cycle pilote l'UI du jeu ; l'activer exige une reinjection, geste interdit
 * tant qu'une session est partagee. La question « la detection est-elle passee au signal ? »
 * ne peut donc pas etre posee au jeu, et elle se decoupe en TROIS etages, tous necessaires --
 * une logique juste mais non cablee se lit exactement comme une logique qui marche.
 *
 *   ETAGE 1 -- COMPORTEMENT. Exerce `runRetreatToCampaign` (le code de PRODUCTION) avec des
 *   doublures qui COMPTENT leurs appels. C'est le seul instrument qui distingue « detecte par
 *   signal » de « detecte par le filet », et « signal absent » de « signal indisponible ».
 *
 *   ETAGE 2 -- CABLAGE. Confronte les SOURCES de `hooks/features/warmup-singletons.ts` et
 *   `hooks/features/ui-windows.ts` au contrat : l'ecoute est ouverte AVANT le premier clic et
 *   fermee dans un `finally`, plus aucun sondage ne subsiste hors du filet, les deux appelants
 *   publient l'`info`, et les crans de `ui-windows.ts` sont intacts.
 *
 *   ETAGE 3 -- LE MEMBRE D'ENUM EXISTE. `GUI_ECRAN_DE_PAUSE` est confronte a la table
 *   VERSIONNEE `data/symbols/<build>/frida/enums.tsv`. Un membre disparu au prochain build
 *   rendrait le signal muet EN SILENCE : la chaine tomberait sur son filet et personne ne
 *   saurait pourquoi.
 *
 * CE QU'IL NE MESURE PAS : que le bundle injecte recoive reellement `retire/PauseMenu`. Cela
 * a ete mesure A LA MAIN sur la session 73 (deux cycles de warmup complets, 28 transitions
 * chacun, sequences identiques) mais avec le bundle PRECEDENT, via le RPC `uiWindowEvents` --
 * pas avec ce code-ci. La confrontation reste due, et c'est precisement pourquoi le step
 * publie sa branche : le premier warmup joue apres deploiement dira laquelle a servi.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
    runRetreatToCampaign, estSortieDeBataille, nommerFrame,
    RetreatDeps, RetreatReason, RetreatResult, TransitionVue, NavOutcome,
    GUI_ECRAN_DE_PAUSE, RETREAT_SIGNAL_WAIT_MS,
    TRANSITION_RETRAIT, TRANSITION_MONTRE_DEBUT,
} from "../hooks/features/warmup-retreat-signal.js";

let checks = 0;
const failures: string[] = [];

function check(label: string, ok: boolean, detail = ""): void {
    checks += 1;
    console.log(`  [${ok ? "OK  " : "FAIL"}] ${label}${detail ? ` -- ${detail}` : ""}`);
    if (!ok) failures.push(`${label} -- ${detail}`);
}

const isAscii = (s: string): boolean =>
    // eslint-disable-next-line no-control-regex
    /^[\x00-\x7F]*$/.test(s);

// --- Doublures instrumentees -------------------------------------------------------

/** Fabrique une transition telle que `ui-windows.ts` la diffuse. */
function T(quoi: string, nom: string | null, classe: string | null = "ScreenVisibility",
           v: number | null = 1): TransitionVue {
    return { quoi, gui: { v, nom }, classe };
}

interface FakeSpec {
    /** Motif d'echec des trois clics (`null` = ils portent). */
    clics?: string | null;
    /** `null` = AUCUN ancrage, donc aucun signal possible. */
    ancrages?: number | null;
    /** Ce que l'ecoute rendra, dans l'ordre, APRES les clics. */
    transitions?: TransitionVue[];
    /** Le signal arrive-t-il ? (sinon `attendre` rend `null` = plafond atteint) */
    signal?: boolean;
    /** Reponses successives de `noeudCampagnePresent` (derniere repetee). */
    noeud?: boolean[];
    navVivante?: boolean;
    nav?: NavOutcome;
    noeudApresNav?: boolean;
}

interface FakeCalls {
    clics: number;
    attendre: number;
    /** Les plafonds demandes, dans l'ordre -- c'est ce qui distingue filet et signal. */
    plafonds: number[];
    /** L'index `depuis` demande a `attendre` : il doit valoir le REPERE. */
    depuis: number[];
    noeud: number;
    navVivante: number;
    nav: number;
    noeudApresNav: number;
    logs: string[];
}

function makeFakes(spec: FakeSpec): { deps: RetreatDeps; calls: FakeCalls } {
    const calls: FakeCalls = {
        clics: 0, attendre: 0, plafonds: [], depuis: [], noeud: 0,
        navVivante: 0, nav: 0, noeudApresNav: 0, logs: [],
    };
    const vues: TransitionVue[] = [];
    const pick = <U>(arr: U[] | undefined, i: number, dflt: U): U => {
        if (!arr || arr.length === 0) return dflt;
        return arr[Math.min(i, arr.length - 1)] as U;
    };
    return {
        calls,
        deps: {
            clicsDeRetraite: async () => {
                calls.clics += 1;
                // Les clics eux-memes produisent des transitions (menu pause, popup de
                // confirmation) : elles sont ANTERIEURES au repere et ne doivent JAMAIS
                // etre comptees comme des frames traversees.
                vues.push(T(TRANSITION_MONTRE_DEBUT, "PauseMenu"));
                vues.push(T(TRANSITION_MONTRE_DEBUT, "MessagePopup"));
                return spec.clics ?? null;
            },
            ecoute: {
                ancrages: spec.ancrages === undefined ? 6 : spec.ancrages,
                vues: () => vues,
                attendre: async (pred, plafondMs, depuis = 0) => {
                    calls.attendre += 1;
                    calls.plafonds.push(plafondMs);
                    calls.depuis.push(depuis);
                    for (const t of spec.transitions ?? []) vues.push(t);
                    if (spec.signal === false) return null;
                    const sortie = T(TRANSITION_RETRAIT, GUI_ECRAN_DE_PAUSE);
                    vues.push(sortie);
                    return pred(sortie) ? sortie : null;
                },
            },
            noeudCampagnePresent: async () => {
                const i = calls.noeud;
                calls.noeud += 1;
                return pick(spec.noeud, i, false);
            },
            attendreNavVivante: async (ms) => {
                calls.navVivante += 1;
                calls.plafonds.push(ms);
                return spec.navVivante ?? true;
            },
            navToCampaign: async () => {
                calls.nav += 1;
                return spec.nav ?? { kind: "ok", navInstance: "0xabc" };
            },
            attendreNoeudCampagne: async (ms) => {
                calls.noeudApresNav += 1;
                calls.plafonds.push(ms);
                return spec.noeudApresNav ?? true;
            },
            log: (m) => { calls.logs.push(m); },
        },
    };
}

// --- ETAGE 1 : le comportement -----------------------------------------------------

async function etage1(): Promise<void> {
    console.log("[390-r2] ETAGE 1 -- comportement (doublures instrumentees)\n");

    // -- 1. LE CHEMIN NOMINAL EST CELUI DU SIGNAL, ET IL NE SONDE RIEN.
    //    C'est le critere de la tranche : aucune interrogation de l'UI, aucun invoke de nav.
    console.log("[1] signal recu -> aucun sondage, aucun invoke");
    {
        const f = makeFakes({});
        const res = await runRetreatToCampaign(f.deps);
        check("err null", res.err === null, String(res.err));
        check("motif = sortie-signalee", res.reason === "sortie-signalee", res.reason);
        check("la nav n'est PAS invoquee", f.calls.nav === 0, `nav=${f.calls.nav}`);
        check("l'attente de la nav n'est PAS payee",
            f.calls.navVivante === 0, `navVivante=${f.calls.navVivante}`);
        check("le noeud de campagne n'est PAS interroge",
            f.calls.noeud === 0, `noeud=${f.calls.noeud}`);
        check("aucune attente du noeud n'est payee",
            f.calls.noeudApresNav === 0, `attentes=${f.calls.noeudApresNav}`);
        check("UNE seule attente, celle du signal", f.calls.attendre === 1,
            `attendre=${f.calls.attendre}`);
        check("l'info NOMME le signal qui a tranche",
            res.info.includes(TRANSITION_RETRAIT) && res.info.includes(GUI_ECRAN_DE_PAUSE),
            res.info);
    }

    // -- 2. LE REPERE. Les frames de la CHAINE elle-meme (menu pause, popup de confirmation)
    //    ne sont pas des frames « traversees » : les compter repondrait a cote de la question.
    console.log("\n[2] les frames de la chaine ne sont PAS comptees comme traversees");
    {
        const f = makeFakes({});
        const res = await runRetreatToCampaign(f.deps);
        check("aucune frame traversee sur le chemin nominal",
            res.framesTraversees.length === 0, res.framesTraversees.join(","));
        check("`attendre` recoit le repere, pas 0",
            f.calls.depuis[0] === 2, `depuis=${f.calls.depuis[0]}`);
        check("et l'info le DIT explicitement",
            res.info.includes("aucune frame montree"), res.info);
    }

    // -- 3. LA FRAME EST NOMMEE. C'est la deuxieme exigence de la tranche : sur un warmup
    //    vert, on doit savoir si une frame s'est intercalee ET laquelle.
    console.log("\n[3] une frame intersticielle traversee est NOMMEE");
    {
        const f = makeFakes({
            transitions: [
                T(TRANSITION_MONTRE_DEBUT, "InterstitialPopup"),
                T("cache-debut", "ChestScreen"),
                T(TRANSITION_MONTRE_DEBUT, "LoadingPopup"),
            ],
        });
        const res = await runRetreatToCampaign(f.deps);
        check("motif = sortie-signalee", res.reason === "sortie-signalee", res.reason);
        check("les DEUX frames montrees sont nommees",
            res.framesTraversees.length === 2, res.framesTraversees.join(","));
        check("par leur MEMBRE d'enum, pas leur ordinal",
            res.info.includes("InterstitialPopup") && res.info.includes("LoadingPopup"),
            res.info);
        check("une transition qui n'est pas un `montre-debut` n'est pas une frame",
            !res.framesTraversees.some((x) => x.includes("ChestScreen")),
            res.framesTraversees.join(","));
        check("et la classe REELLE accompagne le nom",
            res.framesTraversees.every((x) => x.includes("(ScreenVisibility)")),
            res.framesTraversees.join(","));
    }

    // -- 4. UN GUI ILLISIBLE NE SE MAQUILLE PAS. `Register`/`Unregister` prennent des
    //    INTERFACES : l'objet recu peut ne pas etre un `ScreenVisibility`, et l'entier lu est
    //    alors arbitraire (mesure : -1988785488). On publie l'ordinal ET la classe.
    console.log("\n[4] un GuiId illisible est publie tel quel, avec sa classe");
    {
        const f = makeFakes({
            transitions: [T(TRANSITION_MONTRE_DEBUT, null,
                            "BlurredBackgroundScreen", -1988785488)],
        });
        const res = await runRetreatToCampaign(f.deps);
        check("l'ordinal aberrant est publie, pas efface",
            res.framesTraversees[0]?.includes("-1988785488") === true,
            res.framesTraversees.join(","));
        check("et la classe qui l'EXPLIQUE l'accompagne",
            res.framesTraversees[0]?.includes("BlurredBackgroundScreen") === true,
            res.framesTraversees.join(","));
        check("aucun nom n'est invente",
            !res.framesTraversees[0]?.includes("null"),
            res.framesTraversees.join(","));
    }

    // -- 5. SIGNAL ABSENT != SIGNAL INDISPONIBLE. Le premier est une mesure (le jeu n'a pas
    //    emis), le second une panne de capteur (aucun ancrage). Les confondre ferait chercher
    //    la mauvaise cause -- exactement le vice que `WedgeRemedyReason` a deja corrige.
    console.log("\n[5] absent != indisponible, et les deux tombent sur le FILET");
    {
        const absent = await runRetreatToCampaign(
            makeFakes({ signal: false, noeud: [true] }).deps);
        const indispo = await runRetreatToCampaign(
            makeFakes({ ancrages: null, noeud: [true] }).deps);
        check("signal absent -> motif `signal-absent-*`",
            absent.reason.startsWith("signal-absent-"), absent.reason);
        check("aucun ancrage -> motif `signal-indisponible-*`",
            indispo.reason.startsWith("signal-indisponible-"), indispo.reason);
        check("les deux motifs sont DISTINCTS", absent.reason !== indispo.reason,
            `${absent.reason} / ${indispo.reason}`);
        check("les deux ont abouti (le filet a repris)",
            absent.err === null && indispo.err === null,
            `${absent.err} / ${indispo.err}`);
    }
    console.log("\n[5bis] sans ancrage, on n'ATTEND rien -- attendre un signal inexistant "
        + "serait le plafond paye pour rien");
    {
        const f = makeFakes({ ancrages: null, noeud: [true] });
        await runRetreatToCampaign(f.deps);
        check("`attendre` n'est PAS appele", f.calls.attendre === 0,
            `attendre=${f.calls.attendre}`);
    }

    // -- 6. LE FILET EST BIEN L'ANCIEN MECANISME, DANS SON ORDRE. Attendre la nav AVANT
    //    d'invoquer `ToCampaign` est une MESURE de #390 : juste apres le remplacement du
    //    popup, l'invoke rend `no live IdunNavigation instance`.
    console.log("\n[6] le filet garde l'ordre mesure : nav vivante PUIS ToCampaign");
    {
        const f = makeFakes({ signal: false, noeud: [false, false] });
        const res = await runRetreatToCampaign(f.deps);
        check("l'attente de la nav a eu lieu", f.calls.navVivante === 1,
            `navVivante=${f.calls.navVivante}`);
        check("ToCampaign a ete invoquee APRES", f.calls.nav === 1, `nav=${f.calls.nav}`);
        check("puis le noeud a ete attendu", f.calls.noeudApresNav === 1,
            `attentes=${f.calls.noeudApresNav}`);
        check("motif = signal-absent-nav-a-repris",
            res.reason === "signal-absent-nav-a-repris", res.reason);
    }
    console.log("\n[6bis] campagne deja la -> le filet n'invoque RIEN");
    {
        const f = makeFakes({ signal: false, noeud: [true] });
        const res = await runRetreatToCampaign(f.deps);
        check("motif = signal-absent-campagne-deja-la",
            res.reason === "signal-absent-campagne-deja-la", res.reason);
        check("aucune attente de nav", f.calls.navVivante === 0);
        check("aucun invoke", f.calls.nav === 0);
    }

    // -- 7. CHAQUE PANNE DU FILET PORTE UN MOTIF PROPRE.
    console.log("\n[7] les pannes du filet sont deux a deux distinctes");
    {
        const scenarios: Array<[string, FakeSpec]> = [
            ["scene meta absente", { signal: false, navVivante: false }],
            ["nav disparue a l'invoke",
                { signal: false, nav: { kind: "no-nav-instance" } }],
            ["nav a leve", { signal: false, nav: { kind: "error", err: "boum" } }],
            ["campagne jamais remontee", { signal: false, noeudApresNav: false }],
        ];
        const vus: RetreatReason[] = [];
        let tousEnEchec = true;
        let tousNommes = true;
        for (const [, spec] of scenarios) {
            const r = await runRetreatToCampaign(makeFakes(spec).deps);
            vus.push(r.reason);
            if (r.err === null) tousEnEchec = false;
            if (!(r.err ?? "").includes("signal")) tousNommes = false;
        }
        check("4 scenarios, 3 motifs (les deux absences de scene meta convergent)",
            new Set(vus).size === 3, vus.join(" / "));
        check("tous rendent une erreur", tousEnEchec, vus.join(" / "));
        check("et chaque erreur RAPPELLE que le signal n'a pas joue", tousNommes);
        check("une levee de la nav porte sa cause",
            (await runRetreatToCampaign(makeFakes(
                { signal: false, nav: { kind: "error", err: "boum" } }).deps)
            ).err?.includes("boum") === true);
    }

    // -- 8. LES CLICS D'ABORD. Un echec de clic ne doit pas etre maquille en probleme de
    //    signal, et surtout ne doit RIEN attendre derriere lui.
    console.log("\n[8] un echec de clic sort immediatement, sans rien attendre");
    {
        const f = makeFakes({ clics: "bouton pause introuvable" });
        const res = await runRetreatToCampaign(f.deps);
        check("motif = clics-de-retraite-en-echec",
            res.reason === "clics-de-retraite-en-echec", res.reason);
        check("l'erreur porte le motif du clic",
            res.err?.includes("bouton pause introuvable") === true, String(res.err));
        check("aucune attente de signal", f.calls.attendre === 0);
        check("aucun invoke de nav", f.calls.nav === 0);
    }

    // -- 9. LE PLAFOND EST UN FILET, ET IL EST DIMENSIONNE SUR UN CHARGEMENT DE SCENE.
    //    Une frame de chargement s'intercale entre la confirmation et le retrait ; un budget
    //    court transformerait le chemin nominal en repli systematique.
    console.log("\n[9] le plafond couvre un chargement de scene");
    {
        const f = makeFakes({});
        await runRetreatToCampaign(f.deps);
        check("l'attente du signal utilise la constante DECLAREE",
            f.calls.plafonds[0] === RETREAT_SIGNAL_WAIT_MS,
            `plafond=${f.calls.plafonds[0]}`);
        check("elle couvre un unload+reload (>= 30 s, cf. le cran 8 du cycle)",
            RETREAT_SIGNAL_WAIT_MS >= 30000, `${RETREAT_SIGNAL_WAIT_MS} ms`);
        check("et reste bornee (un filet n'est pas une boucle d'attente)",
            RETREAT_SIGNAL_WAIT_MS <= 60000, `${RETREAT_SIGNAL_WAIT_MS} ms`);
    }

    // -- 10. LE PREDICAT EST CELUI QU'ON CROIT, ET IL SE TROMPE DANS LE BON SENS.
    console.log("\n[10] `estSortieDeBataille` discrimine");
    {
        check("retire/PauseMenu -> vrai",
            estSortieDeBataille(T(TRANSITION_RETRAIT, GUI_ECRAN_DE_PAUSE)));
        check("montre-debut/PauseMenu -> faux (c'est l'OUVERTURE du menu)",
            !estSortieDeBataille(T(TRANSITION_MONTRE_DEBUT, GUI_ECRAN_DE_PAUSE)));
        check("retire/autre ecran -> faux",
            !estSortieDeBataille(T(TRANSITION_RETRAIT, "MessagePopup")));
        check("retire/gui illisible -> faux (jamais sur un ordinal aberrant)",
            !estSortieDeBataille(T(TRANSITION_RETRAIT, null, "X", -1988785488)));
        check("`nommerFrame` ne rend jamais une chaine vide",
            nommerFrame(T("x", null, null, null)).length > 0);
    }

    // -- 11. ASCII. Ces libelles partent vers des `print` Python (cp1252).
    console.log("\n[11] motifs, infos et erreurs sont ASCII");
    {
        const tous: RetreatResult[] = [
            await runRetreatToCampaign(makeFakes({}).deps),
            await runRetreatToCampaign(makeFakes({ signal: false }).deps),
            await runRetreatToCampaign(makeFakes({ ancrages: null }).deps),
            await runRetreatToCampaign(makeFakes({ clics: "x" }).deps),
            await runRetreatToCampaign(
                makeFakes({ signal: false, navVivante: false }).deps),
        ];
        let ok = true;
        let infoNonVide = true;
        for (const r of tous) {
            if (!isAscii(r.reason) || !isAscii(r.info) || !isAscii(r.err ?? "")) ok = false;
            if (r.info.length === 0) infoNonVide = false;
        }
        check("tout est ASCII (cp1252-safe)", ok);
        check("aucun resultat n'a une `info` vide", infoNonVide,
            "un step muet ne repond a aucune question");
    }
}

// --- ETAGE 2 : le cablage ----------------------------------------------------------

function lireSource(nom: string): string {
    const ici = dirname(fileURLToPath(import.meta.url));
    return readFileSync(join(ici, "..", "hooks", "features", nom), "utf8");
}

function etage2(): void {
    console.log("\n[390-r2] ETAGE 2 -- cablage (sources verbatim)\n");
    const warm = lireSource("warmup-singletons.ts");
    const win = lireSource("ui-windows.ts");
    const pur = lireSource("warmup-retreat-signal.ts");

    // -- 1. La chaine est IMPORTEE et APPELEE. Sans cela le module vit en orbite.
    console.log("[1] `runRetreatToCampaign` est importe et appele");
    check("import depuis `./warmup-retreat-signal.js`",
        /import\s*\{[^}]*runRetreatToCampaign[^}]*\}\s*from\s*"\.\/warmup-retreat-signal\.js"/s
            .test(warm));
    check("appel", warm.includes("runRetreatToCampaign({"));
    check("l'ecoute vient de `./ui-windows.js`",
        /import\s*\{\s*ecouterTransitions\s*\}\s*from\s*"\.\/ui-windows\.js"/.test(warm));

    // -- 2. L'ECOUTE EST OUVERTE AVANT LES CLICS. Une transition emise entre le clic et
    //    l'abonnement serait perdue -- et c'est celle qui compte.
    console.log("\n[2] l'ecoute est ouverte avant les clics et fermee dans un `finally`");
    const iFn = warm.indexOf("async function retreatToCampaign(");
    const iEcoute = warm.indexOf("ecouterTransitions()", iFn);
    const iRun = warm.indexOf("runRetreatToCampaign({", iFn);
    check("`retreatToCampaign` existe encore", iFn > 0);
    check("l'abonnement precede l'appel de la chaine",
        iEcoute > iFn && iEcoute < iRun, `ecoute=${iEcoute} run=${iRun}`);
    check("et il est ferme dans un `finally`",
        /finally\s*\{\s*ecoute\.fermer\(\);?\s*\}/.test(warm));

    // -- 3. PLUS AUCUN SONDAGE HORS DU FILET. C'est LE critere de la tranche : le corps de
    //    `retreatToCampaign` ne doit contenir de `waitFor` que dans les deps NOMMEES filet.
    console.log("\n[3] aucun `waitFor` hors des deux deps de filet");
    const corps = warm.slice(iFn, warm.indexOf("\n}", iRun) + 2);
    const waits = (corps.match(/waitFor\(/g) ?? []).length;
    check("exactement 2 `waitFor`, tous deux dans le filet", waits === 2,
        `occurrences=${waits}`);
    check("le premier est `attendreNavVivante`",
        /attendreNavVivante:[\s\S]{0,240}waitFor\(/.test(corps));
    check("le second est `attendreNoeudCampagne`",
        /attendreNoeudCampagne:[\s\S]{0,160}waitFor\(/.test(corps));
    check("`noeudCampagnePresent` est UNE lecture, pas un `waitFor`",
        /noeudCampagnePresent:[\s\S]{0,200}queueOnMainThread\(/.test(corps)
        && !/noeudCampagnePresent:[\s\S]{0,200}waitFor\(/.test(corps));
    check("l'ancienne constante de sondage a disparu",
        !/const RETREAT_NAV_WAIT_MS\s*=/.test(warm),
        "elle bornait les deux sondages remplaces");

    // -- 4. LES DEUX APPELANTS PUBLIENT L'INFO. Un step muet ne repond a aucune question --
    //    c'est l'etat de depart de la tranche (`retreat-to-campaign` etait pousse sans info).
    console.log("\n[4] les deux appelants publient la branche ET l'info");
    for (const [nom, motif] of [
        ["retreat-to-campaign", /step:\s*"retreat-to-campaign",\s*ok:\s*true,\s*\n?\s*info:/],
        ["recover-from-battle", /step:\s*"recover-from-battle",\s*ok:\s*true,\s*\n?\s*info:/],
    ] as Array<[string, RegExp]>) {
        check(`le step \`${nom}\` porte un \`info\``, motif.test(warm));
    }
    check("l'info du step cite `reason` ET `info`",
        /info:\s*`\$\{retreat\.reason\}\s*:\s*\$\{retreat\.info\}`/.test(warm));
    check("celle de l'etape 1bis aussi",
        /out\.reason[\s\S]{0,40}out\.info/.test(warm));

    // -- 5. LE MEMBRE, JAMAIS L'ORDINAL. Regle du depot, et elle est ce qui rend une
    //    confusion d'enum visible : un ordinal juste aujourd'hui est faux en silence demain.
    console.log("\n[5] le GuiId est ecrit par son MEMBRE");
    check("`GUI_ECRAN_DE_PAUSE` est une chaine, pas un nombre",
        /export const GUI_ECRAN_DE_PAUSE = "PauseMenu";/.test(pur));
    check("l'ordinal 34 n'apparait dans aucune ligne EXECUTABLE du module pur",
        !pur.split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))
            .some((l) => /\b34\b/.test(l)));

    // -- 6. LES LIBELLES DE TRANSITION SONT APPARIES. Le module pur ne peut pas importer
    //    `ui-windows.ts` (il doit rester executable hors Frida) : il redeclare donc les
    //    siens, et une divergence rendrait le signal muet sans rien casser d'autre.
    console.log("\n[6] les libelles du module pur == ceux poses par `ui-windows.ts`");
    check("`ui-windows.ts` publie le foyer `TRANSITION`",
        /export const TRANSITION = \{/.test(win));
    for (const [cle, valeur] of [
        ["retire", TRANSITION_RETRAIT], ["montreDebut", TRANSITION_MONTRE_DEBUT],
    ] as Array<[string, string]>) {
        check(`\`TRANSITION.${cle}\` vaut "${valeur}"`,
            new RegExp(`${cle}:\\s*"${valeur}"`).test(win));
    }
    check("`Unregister` est bien ancree sous `TRANSITION.retire`",
        /ancrer\(klass,\s*"Unregister",\s*TRANSITION\.retire\)/.test(win));
    check("`HandleOnScreenStartedShowing` sous `TRANSITION.montreDebut`",
        /ancrer\(klass,\s*"HandleOnScreenStartedShowing",\s*TRANSITION\.montreDebut\)/
            .test(win));

    // -- 7. LES CRANS DE `ui-windows.ts` SONT INTACTS. On a AJOUTE un acces, pas reecrit un
    //    module dont les avertissements sont chers.
    //    ⚠ ON VERIFIE LE MECANISME, PAS LA PROSE. Premier jet de ce probe : il cherchait la
    //    phrase du commentaire (« Attache TOUTES les methodes... ») et rougissait sur son
    //    accent. Une garde qui lit un commentaire ne garde rien -- reecrire le commentaire
    //    la ferait passer au vert avec le cran cassé.
    console.log("\n[7] les crans de `ui-windows.ts` sont intacts");
    const iAncrer = win.indexOf("function ancrer(");
    const corpsAncrer = win.slice(iAncrer, win.indexOf("\n}", iAncrer));
    check("`ancrer` ENUMERE les methodes de la classe",
        /while \(!\(mi = class_get_methods\(klass, it\)/.test(corpsAncrer),
        "`findMethod` rendrait UNE surcharge au hasard");
    check("et ne s'arrete pas au premier match (il COMPTE)",
        /poses\+\+;/.test(corpsAncrer) && !/\breturn\b[\s\S]{0,40}poses[\s\S]{0,10}\n[\s\S]*?\}/
            .test(corpsAncrer.slice(0, corpsAncrer.indexOf("poses++"))),
        "le compte ne monterait pas au-dela de 1");
    check("`ancrer` n'utilise PAS `findMethod`", !/findMethod\(/.test(corpsAncrer));
    check("`ancrages` reste tri-etat", /let ancrages: number \| null = null;/.test(win));
    check("`installerAncrages` est toujours le seul poseur",
        (win.match(/function installerAncrages\(/g) ?? []).length === 1);
    check("le RPC `uiWindowEvents` existe toujours",
        /ctx\.rpc\.uiWindowEvents\s*=/.test(win));
    check("`uiWindows` aussi", /ctx\.rpc\.uiWindows\s*=/.test(win));

    // -- 8. L'ABONNEMENT EST ADDITIF. Il ne doit ni lire ni ecrire l'etat de l'OPERATEUR :
    //    un `start`/`stop` du warmup eteindrait un journal arme a la main, et un `clear`
    //    effacerait ses transitions.
    console.log("\n[8] `ecouterTransitions` ne touche pas l'etat de l'operateur");
    const iEc = win.indexOf("export function ecouterTransitions()");
    const corpsEc = win.slice(iEc, win.indexOf("\nfunction installerAncrages(", iEc));
    check("`ecouterTransitions` existe", iEc > 0);
    check("il n'ecrit jamais `actif`", !/\bactif\s*=/.test(corpsEc));
    check("il ne lit jamais le tampon `journal`", !/\bjournal\b/.test(corpsEc));
    check("il ne touche pas `recus` ni `ecartes`",
        !/\brecus\b/.test(corpsEc) && !/\becartes\b/.test(corpsEc));
    check("il pose les ancrages si besoin",
        /if \(ancrages === null\) ancrages = installerAncrages\(\);/.test(corpsEc));
    check("et publie `ancrages` a l'appelant", /\bancrages,/.test(corpsEc));

    // -- 9. LA DIFFUSION PRECEDE LE GATE. Sinon le warmup devrait armer le journal de
    //    l'operateur pour recevoir quoi que ce soit -- ce que le point 8 interdit.
    console.log("\n[9] `noter` diffuse AVANT le gate `actif`");
    const iNoter = win.indexOf("function noter(");
    const corpsNoter = win.slice(iNoter, win.indexOf("\n}", win.indexOf("recus++", iNoter)));
    const iDiffusion = corpsNoter.indexOf("cb(vue)");
    const iGate = corpsNoter.indexOf("if (!actif) return;");
    check("la diffusion existe", iDiffusion > 0);
    check("elle precede le gate", iGate > iDiffusion, `cb=${iDiffusion} gate=${iGate}`);
    check("sortie immediate quand personne n'ecoute",
        /if \(!actif && abonnes\.size === 0\) return;/.test(corpsNoter),
        "sinon on paierait la lecture du GuiId pour rien");
    check("un abonne qui jette n'emporte pas les autres",
        /try \{ cb\(vue\); \} catch/.test(corpsNoter));

    // -- 10. LA CLASSE REELLE EST PUBLIEE. C'est ce qui rend l'ordinal aberrant LISIBLE.
    console.log("\n[10] la classe reelle de l'objet est publiee");
    check("`classeDe` lit le premier slot de l'objet",
        /function classeDe\([\s\S]{0,300}obj\.readPointer\(\)/.test(win));
    check("elle rend `null` plutot que d'inventer",
        /function classeDe\([\s\S]{0,400}catch \{ return null; \}/.test(win));
    check("`TransitionVue` porte `classe`",
        /export interface TransitionVue \{[\s\S]{0,300}classe: string \| null;/.test(win));
    check("le journal la porte aussi (`Transition extends TransitionVue`)",
        /interface Transition extends TransitionVue \{ n: number \}/.test(win));

    // -- 11. LE MODULE PUR RESTE PUR : c'est ce qui rend l'etage 1 possible.
    console.log("\n[11] `warmup-retreat-signal.ts` n'importe RIEN");
    check("aucun `import` dans le module pur",
        !/^\s*import\s/m.test(pur), "un seul import Frida le rendrait inexecutable ici");
}

// --- ETAGE 3 : le membre d'enum existe dans le build --------------------------------

function etage3(): void {
    console.log("\n[390-r2] ETAGE 3 -- le membre d'enum existe dans le build\n");
    const ici = dirname(fileURLToPath(import.meta.url));
    const racine = join(ici, "..", "..");
    const build = readFileSync(join(racine, "data", "symbols", "CURRENT"), "utf8").trim();
    console.log(`  build courant : ${build}`);
    const enums = readFileSync(
        join(racine, "data", "symbols", build, "frida", "enums.tsv"), "utf8");
    const ligne = enums.split("\n").find((l) => l.startsWith("idun.tracking.GuiId\t"));
    check("`idun.tracking.GuiId` est dans la table versionnee", ligne !== undefined);
    const membres = (ligne ?? "").split("\t")[1] ?? "";
    const noms = new Set(membres.split(",").map((x) => x.split("=")[1]));
    check(`le membre \`${GUI_ECRAN_DE_PAUSE}\` existe`, noms.has(GUI_ECRAN_DE_PAUSE),
        "sans lui le signal serait muet EN SILENCE (repli systematique sur le filet)");
    // Les frames mesurees pendant la sequence de retraite. Elles ne conditionnent pas la
    // detection -- elles sont ce que le step NOMME -- mais leur disparition dirait que la
    // table a bouge sous nos pieds.
    for (const m of ["Campaign", "MessagePopup", "InterstitialPopup"]) {
        check(`le membre \`${m}\` existe`, noms.has(m));
    }
}

async function main(): Promise<number> {
    console.log("[390-r2] la chaine de retraite detecte par SIGNAL et NOMME ce qu'elle "
        + "traverse\n");
    await etage1();
    etage2();
    etage3();

    console.log(`\n[390-r2] ${checks - failures.length}/${checks} verifications OK`);
    if (failures.length) {
        console.log("[390-r2] VERDICT : ECHEC");
        for (const f of failures) console.log(`  - ${f}`);
        return 1;
    }
    console.log("[390-r2] VERDICT : la sortie de bataille est detectee par le RETRAIT de "
        + "l'ecran de pause (signal push), le chemin nominal ne sonde plus rien, et le step "
        + "dit sa branche en nommant les frames traversees.");
    return 0;
}

main().then((rc) => process.exit(rc)).catch((e) => {
    console.log(`[390-r2] ERREUR : ${(e as Error).stack}`);
    process.exit(1);
});
