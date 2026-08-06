/* Garde de #390 -- le cycle de warmup APPLIQUE le remede qu'il nomme.
 *
 * Lancement (depuis `frida/`) :
 *     npx tsx tools/probe-390-wedge-remedy.ts
 *     node node_modules/tsx/dist/cli.mjs tools/probe-390-wedge-remedy.ts
 *
 * POURQUOI CE HARNAIS EXISTE. Le cycle complet n'est pas rejouable a volonte : il pilote
 * l'UI du jeu, et l'activer exigerait une reinjection -- geste interdit tant qu'une
 * session est partagee. La question « le remede est-il cable ? » ne peut donc pas etre
 * posee au jeu. Elle se decoupe en deux, et les DEUX etages sont necessaires : une
 * logique juste mais non cablee se lit exactement comme un remede qui marche, et un
 * cablage vers une logique fausse aussi.
 *
 *   ETAGE 1 -- COMPORTEMENT. Exerce `runWedgeRemedy` (le code de PRODUCTION, pas une
 *   copie) avec des doublures qui COMPTENT leurs appels. C'est le seul instrument qui
 *   distingue « le remede a tente » de « le remede a tente QUATRE FOIS », et
 *   « inapplicable » de « epuise ».
 *
 *   ETAGE 2 -- CABLAGE. Confronte le SOURCE de `hooks/features/warmup-singletons.ts` au
 *   contrat : le remede est bien appele depuis la branche d'echec du cran 8, il n'existe
 *   qu'UN foyer d'invoke de la nav, et l'echec dit ce que le remede a fait. Meme patron
 *   que `scripts/python/probe_467r4_contrat_host.py`.
 *
 * CE QU'IL NE MESURE PAS : que le bundle injecte se rattrape reellement d'un wedge. Cela
 * exige un reinject ET qu'un wedge se produise (il est INTERMITTENT). Le remede reste
 * NON CONFRONTE LIVE tant que ce n'est pas fait -- et c'est precisement pour cela qu'il
 * publie `recovered` et ses steps : la premiere occurrence apres deploiement dira lequel
 * des trois regimes se produit.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
    runWedgeRemedy, NavOutcome, WedgeRemedyReason, WedgeRemedyResult,
    WEDGE_REMEDY_ATTEMPTS, WEDGE_REMEDY_NAV_WAIT_MS, WEDGE_REMEDY_POPUP_WAIT_MS,
} from "../hooks/features/warmup-wedge-remedy.js";

let checks = 0;
const failures: string[] = [];

function check(label: string, ok: boolean, detail = ""): void {
    checks += 1;
    console.log(`  [${ok ? "OK  " : "FAIL"}] ${label}${detail ? ` -- ${detail}` : ""}`);
    if (!ok) failures.push(`${label} -- ${detail}`);
}

// --- Doublures instrumentees -------------------------------------------------------

interface FakeSpec {
    /** Popups fermes a chaque tour (indexe par tour, dernier repete). */
    popups?: string[][];
    /** Ce que rend la nav a chaque tour (indexe par tour, dernier repete). */
    nav?: NavOutcome[];
    /** La campagne redevient-elle visible ? indexe par appel, dernier repete. */
    visible?: boolean[];
    /** `dismissPopups` leve-t-il ? */
    dismissThrows?: boolean;
}

interface FakeCalls {
    dismiss: number;
    nav: number;
    /** Les timeouts demandes a `campaignVisible`, dans l'ordre. */
    visibleTimeouts: number[];
    logs: string[];
}

function makeFakes(spec: FakeSpec): {
    deps: Parameters<typeof runWedgeRemedy>[0];
    calls: FakeCalls;
} {
    const calls: FakeCalls = { dismiss: 0, nav: 0, visibleTimeouts: [], logs: [] };
    const pick = <T>(arr: T[] | undefined, i: number, dflt: T): T => {
        if (!arr || arr.length === 0) return dflt;
        return arr[Math.min(i, arr.length - 1)] as T;
    };
    return {
        calls,
        deps: {
            dismissPopups: async () => {
                const i = calls.dismiss;
                calls.dismiss += 1;
                if (spec.dismissThrows) throw new Error("dismiss a explose");
                return pick(spec.popups, i, []);
            },
            navToCampaign: async () => {
                const i = calls.nav;
                calls.nav += 1;
                return pick<NavOutcome>(spec.nav, i, { kind: "ok", navInstance: "0x1" });
            },
            campaignVisible: async (timeoutMs: number) => {
                const i = calls.visibleTimeouts.length;
                calls.visibleTimeouts.push(timeoutMs);
                return pick(spec.visible, i, false);
            },
            log: (m: string) => { calls.logs.push(m); },
        },
    };
}

const isAscii = (s: string): boolean =>
    // eslint-disable-next-line no-control-regex
    /^[\x00-\x7F]*$/.test(s);

function stepNames(res: WedgeRemedyResult): string[] {
    return res.steps.map((s) => s.step);
}

// --- ETAGE 1 : le comportement -----------------------------------------------------

async function etage1(): Promise<void> {
    console.log("[390] ETAGE 1 -- comportement du remede (doublures instrumentees)\n");

    // -- 1. Le volet POPUP porte, et il COURT-CIRCUITE la nav.
    //    Si fermer un popup suffit, invoquer ToCampaign en plus serait un effet de bord
    //    gratuit sur l'UI du jeu.
    console.log("[1] un popup ferme suffit -> la nav n'est PAS invoquee");
    {
        const f = makeFakes({ popups: [["Idun_UI_LiveEventInterstitialPopup"]],
                              visible: [true] });
        const res = await runWedgeRemedy(f.deps);
        check("recovered", res.recovered);
        check("motif = popup",
            res.reason === "campagne-remontee-apres-fermeture-de-popup", res.reason);
        check("la nav n'a PAS ete invoquee", f.calls.nav === 0, `nav=${f.calls.nav}`);
        check("un seul tour", res.attempts === 1, `attempts=${res.attempts}`);
        check("le nom du popup ferme est trace",
            res.steps.some((s) => (s.info ?? "").includes(
                "Idun_UI_LiveEventInterstitialPopup")));
    }

    // -- 2. Aucun popup -> on passe a la nav, et elle porte.
    console.log("\n[2] aucun popup -> la nav prend le relais");
    {
        const f = makeFakes({ popups: [[]], nav: [{ kind: "ok", navInstance: "0xabc" }],
                              visible: [true] });
        const res = await runWedgeRemedy(f.deps);
        check("recovered", res.recovered);
        check("motif = nav",
            res.reason === "campagne-remontee-apres-nav-to-campaign", res.reason);
        check("la nav a ete invoquee une fois", f.calls.nav === 1, `nav=${f.calls.nav}`);
        check("l'instance de nav est tracee",
            res.steps.some((s) => (s.info ?? "").includes("0xabc")));
    }

    // -- 3. ECONOMIE. Sans popup ferme, rien n'a change : attendre le retour de la
    //    campagne serait du temps jete a chaque tour.
    console.log("\n[3] aucun popup ferme -> aucune attente payee pour le volet popup");
    {
        const f = makeFakes({ popups: [[]], nav: [{ kind: "ok", navInstance: "0x1" }],
                              visible: [true] });
        await runWedgeRemedy(f.deps);
        check("une seule attente, celle de la nav",
            f.calls.visibleTimeouts.length === 1
            && f.calls.visibleTimeouts[0] === WEDGE_REMEDY_NAV_WAIT_MS,
            `timeouts=[${f.calls.visibleTimeouts.join(",")}]`);
    }
    console.log("\n[3bis] un popup ferme -> l'attente payee est celle du volet popup");
    {
        const f = makeFakes({ popups: [["P"]], visible: [true] });
        await runWedgeRemedy(f.deps);
        check("le timeout est celui du volet popup",
            f.calls.visibleTimeouts[0] === WEDGE_REMEDY_POPUP_WAIT_MS,
            `timeouts=[${f.calls.visibleTimeouts.join(",")}]`);
    }

    // -- 4. INAPPLICABLE != EPUISE. Sans scene meta chargee il n'existe aucune instance
    //    a piloter : reessayer ne peut RIEN changer, et le confondre avec un epuisement
    //    de tentatives ferait chercher la mauvaise cause.
    console.log("\n[4] pas d'instance de nav -> arret IMMEDIAT, motif propre");
    {
        const f = makeFakes({ popups: [[]], nav: [{ kind: "no-nav-instance" }] });
        const res = await runWedgeRemedy(f.deps);
        check("pas recovered", !res.recovered);
        check("motif = scene-meta-absente",
            res.reason === "scene-meta-absente", res.reason);
        check("UN SEUL tour joue", res.attempts === 1, `attempts=${res.attempts}`);
        check("la nav n'a PAS ete rejouee", f.calls.nav === 1, `nav=${f.calls.nav}`);
        check("aucune attente jetee apres l'arret",
            f.calls.visibleTimeouts.length === 0,
            `timeouts=${f.calls.visibleTimeouts.length}`);
        check("le step nomme l'inapplicabilite",
            res.steps.some((s) => (s.info ?? "").includes("INAPPLICABLE")));
    }

    // -- 5. LA BORNE. Un retry non borne transformerait un wedge visible en attente
    //    muette. La borne est la constante exportee, et le remede s'y tient.
    console.log("\n[5] rien ne marche -> le remede s'arrete a sa borne DECLAREE");
    {
        const f = makeFakes({ popups: [["A"], ["B"]], visible: [false] });
        const res = await runWedgeRemedy(f.deps);
        check("pas recovered", !res.recovered);
        check("motif = remede-epuise", res.reason === "remede-epuise", res.reason);
        check(`exactement ${WEDGE_REMEDY_ATTEMPTS} tours`,
            res.attempts === WEDGE_REMEDY_ATTEMPTS, `attempts=${res.attempts}`);
        check(`exactement ${WEDGE_REMEDY_ATTEMPTS} invocations de nav`,
            f.calls.nav === WEDGE_REMEDY_ATTEMPTS, `nav=${f.calls.nav}`);
        check("la borne est superieure a 1 (fermer un popup peut en reveler un second)",
            WEDGE_REMEDY_ATTEMPTS >= 2, `borne=${WEDGE_REMEDY_ATTEMPTS}`);
        check("la borne reste petite (un remede n'est pas une boucle d'attente)",
            WEDGE_REMEDY_ATTEMPTS <= 3, `borne=${WEDGE_REMEDY_ATTEMPTS}`);
    }

    // -- 6. UNE LEVEE PORTE SON NOM. Un `rc` ou un booleen ne nomme rien : c'est ce qui
    //    a deja fait diagnostiquer la mauvaise cause ailleurs dans ce depot.
    console.log("\n[6] la nav leve -> motif DISTINCT de l'epuisement");
    {
        const f = makeFakes({ popups: [[]], nav: [{ kind: "error", err: "boum" }] });
        const res = await runWedgeRemedy(f.deps);
        check("motif = nav-to-campaign-a-leve",
            res.reason === "nav-to-campaign-a-leve", res.reason);
        check("le message porte la cause",
            res.steps.some((s) => (s.info ?? "").includes("boum")));
        check("une levee est retentee (elle peut etre transitoire)",
            f.calls.nav === WEDGE_REMEDY_ATTEMPTS, `nav=${f.calls.nav}`);
        check("aucune attente jetee sur un invoke qui a leve",
            f.calls.visibleTimeouts.length === 0,
            `timeouts=${f.calls.visibleTimeouts.length}`);
    }

    // -- 7. LE REMEDE NE PEUT PAS EXPLOSER. S'il levait, l'appelant perdrait a la fois
    //    le rattrapage ET le diagnostic -- soit exactement le defaut repare.
    console.log("\n[7] une panne du volet popup ne fait pas exploser le remede");
    {
        const f = makeFakes({ dismissThrows: true,
                              nav: [{ kind: "ok", navInstance: "0x2" }],
                              visible: [true] });
        let threw = false;
        let res: WedgeRemedyResult | null = null;
        try { res = await runWedgeRemedy(f.deps); } catch { threw = true; }
        check("le remede n'a pas leve", !threw);
        check("il a poursuivi vers la nav", f.calls.nav === 1, `nav=${f.calls.nav}`);
        check("la panne du volet popup est TRACEE",
            (res?.steps ?? []).some((s) => s.step === "wedge-remedy-dismiss-popups"
                && !s.ok && (s.info ?? "").includes("dismiss a explose")));
        check("et le rattrapage a quand meme eu lieu", res?.recovered === true);
    }

    // -- 8. AUCUNE SENTINELLE UNIQUE : les cinq motifs sont deux a deux distincts, et
    //    les trois motifs d'ECHEC le sont aussi. Un `ok: false` unique les confondrait.
    console.log("\n[8] les motifs sont distincts, et ASCII (ils partent vers un print)");
    {
        const scenarios: Array<[string, FakeSpec]> = [
            ["popup", { popups: [["P"]], visible: [true] }],
            ["nav", { popups: [[]], visible: [true] }],
            ["absente", { popups: [[]], nav: [{ kind: "no-nav-instance" }] }],
            ["levee", { popups: [[]], nav: [{ kind: "error", err: "e" }] }],
            ["epuise", { popups: [[]], visible: [false] }],
        ];
        const seen: WedgeRemedyReason[] = [];
        let asciiOk = true;
        let infoOk = true;
        for (const [, spec] of scenarios) {
            const res = await runWedgeRemedy(makeFakes(spec).deps);
            seen.push(res.reason);
            if (!isAscii(res.reason)) asciiOk = false;
            for (const s of res.steps) {
                if (!isAscii(s.step) || !isAscii(s.info ?? "")) asciiOk = false;
                if ((s.info ?? "").length === 0) infoOk = false;
            }
        }
        check("5 motifs, tous distincts",
            new Set(seen).size === 5, seen.join(" / "));
        check("tous les libelles sont ASCII (cp1252-safe)", asciiOk,
            "un non-ASCII ferait crasher le print du lecteur Python");
        check("chaque step porte une info non vide", infoOk,
            "un step muet ne nomme aucune panne");
    }

    // -- 9. LA TRACE PERMET DE DISTINGUER LES TROIS ETATS. C'est le critere de la
    //    tranche : « remede non tente » / « tente et sans effet » / « tente et il a
    //    porte » doivent se lire, pas se deviner.
    console.log("\n[9] la trace distingue les trois etats");
    {
        const porte = await runWedgeRemedy(
            makeFakes({ popups: [[]], visible: [true] }).deps);
        const sansEffet = await runWedgeRemedy(
            makeFakes({ popups: [[]], visible: [false] }).deps);
        check("un remede qui a tourne laisse toujours des steps `wedge-remedy-*`",
            porte.steps.length > 0 && sansEffet.steps.length > 0
            && porte.steps.every((s) => s.step.startsWith("wedge-remedy-"))
            && sansEffet.steps.every((s) => s.step.startsWith("wedge-remedy-")),
            stepNames(porte).join(","));
        check("les deux issues portent un step `wedge-remedy-outcome`",
            stepNames(porte).includes("wedge-remedy-outcome")
            && stepNames(sansEffet).includes("wedge-remedy-outcome"));
        check("et son `ok` separe les deux",
            porte.steps[porte.steps.length - 1]?.ok === true
            && sansEffet.steps[sansEffet.steps.length - 1]?.ok === false);
    }
}

// --- ETAGE 2 : le cablage ----------------------------------------------------------

/** Le corps de `warmupGameSingletons`, source verbatim. */
function lireSource(nom: string): string {
    const ici = dirname(fileURLToPath(import.meta.url));
    return readFileSync(join(ici, "..", "hooks", "features", nom), "utf8");
}

function etage2(): void {
    console.log("\n[390] ETAGE 2 -- cablage dans le cycle (source verbatim)\n");
    const src = lireSource("warmup-singletons.ts");

    // -- 1. Le remede est IMPORTE et APPELE. Sans cela le module vit en orbite : sa
    //    logique est juste et personne ne s'en sert -- le defaut d'origine, deplace.
    console.log("[1] le remede est importe et appele");
    check("import de `runWedgeRemedy`",
        /import\s*\{[^}]*runWedgeRemedy[^}]*\}\s*from\s*"\.\/warmup-wedge-remedy\.js"/s
            .test(src));
    check("appel de `runWedgeRemedy(`", src.includes("runWedgeRemedy({"));

    // -- 2. L'appel est DANS la branche d'echec du cran 8. Un remede applique ailleurs
    //    (au debut du cycle, ou sur le chemin nominal) ne repare pas ce wedge-la.
    console.log("\n[2] l'appel vit dans la branche d'echec du cran 8");
    const iBackHome = src.indexOf("const backHome = await waitFor(");
    const iGarde = src.indexOf("if (backHome === null) {", iBackHome);
    const iRemede = src.indexOf("runWedgeRemedy({", iGarde);
    const iFinBranche = src.indexOf(
        "steps.push({ step: \"wait-back-to-campaign\", ok: true });", iGarde);
    check("le cran 8 existe encore", iBackHome > 0 && iGarde > iBackHome);
    check("le remede est appele APRES la garde", iRemede > iGarde, `i=${iRemede}`);
    check("et AVANT la sortie nominale du cran 8",
        iFinBranche > 0 && iRemede < iFinBranche, `fin=${iFinBranche}`);

    // -- 3. L'ECHEC DIT CE QUE LE REMEDE A FAIT. Rendre `ok: false` sans le motif
    //    reproduirait l'etat de depart : un echec qu'il faut interpreter a la main.
    console.log("\n[3] l'echec porte le motif du remede");
    const branche = src.slice(iGarde, iFinBranche > 0 ? iFinBranche : src.length);
    check("l'erreur cite `remedy.reason`", branche.includes("remedy.reason"));
    check("elle cite le compte de tentatives",
        branche.includes("remedy.attempts")
        && branche.includes("WEDGE_REMEDY_ATTEMPTS"));
    check("le succes apres rattrapage publie `recovered`",
        branche.includes("recovered: remedy.reason"));
    check("le champ `recovered` est declare dans le resultat",
        /recovered\?:\s*WedgeRemedyReason/.test(src));

    // -- 4. Le step du cran 8 reste a `ok: false` meme quand le remede porte : un
    //    rattrapage ne doit pas effacer la trace du wedge.
    console.log("\n[4] le wedge reste VISIBLE apres rattrapage");
    check("le step `wait-back-to-campaign` est pousse a ok:false dans la branche",
        /step:\s*"wait-back-to-campaign",\s*ok:\s*false/.test(branche));
    check("les steps du remede sont recopies dans ceux du cycle",
        branche.includes("for (const s of remedy.steps) steps.push(s);"));

    // -- 5. Le message ne prescrit PLUS un geste humain deja automatise.
    //    Mesure sur les lignes EXECUTABLES seulement : le commentaire du bloc CITE
    //    l'ancien message pour dire ce qui a change, et une garde qui rougirait dessus
    //    interdirait d'expliquer la reparation -- elle punirait la doc, pas le defaut.
    //    (Trouve par ce probe a son premier passage : il rougissait sur sa propre
    //    citation historique.)
    console.log("\n[5] le message ne renvoie plus l'humain vers `navToCampaign`");
    const executable = branche.split("\n")
        .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");
    check("aucune ligne executable ne prescrit 'try rpc navToCampaign'",
        !executable.includes("try rpc navToCampaign"),
        "le cycle le fait lui-meme maintenant");
    check("la citation historique reste LISIBLE en commentaire",
        branche.includes("try rpc navToCampaign"),
        "sans elle, un lecteur ne sait pas ce que la tranche a change");

    // -- 6. FOYER UNIQUE de la nav. C'est la lecon de #332 : deux copies, une seule
    //    corrigee. Le triplet resolve+find+invoke ne doit exister qu'une fois.
    console.log("\n[6] un seul foyer d'invoke de la nav");
    const nbInvoke = (src.match(/invokeToCampaign\(/g) ?? []).length;
    check("`invokeToCampaign(` apparait 2 fois : sa definition et SON UNIQUE appel",
        nbInvoke === 2, `occurrences=${nbInvoke}`);
    check("le foyer existe", src.includes("function navToCampaignOnMainThread("));
    check("le RPC de secours passe par le foyer",
        /ctx\.rpc\.navToCampaign\s*=[\s\S]{0,200}navToCampaignOnMainThread\(/.test(src));
    check("le remede passe par le foyer",
        /navToCampaign:\s*\(\)\s*=>[\s\S]{0,120}navToCampaignOnMainThread\(/.test(src));
    check("l'etape 2 du cycle passe par le foyer",
        /const navResult =[\s\S]{0,160}navToCampaignOnMainThread\(true\)/.test(src));

    // -- 7. FOYER UNIQUE de la fermeture des popups : meme geste a l'entree du cycle et
    //    dans le remede.
    console.log("\n[7] un seul foyer de fermeture des popups");
    const nbDismissDef = (src.match(/async function dismissOpenPopups\(/g) ?? []).length;
    check("une seule definition de `dismissOpenPopups`", nbDismissDef === 1,
        `definitions=${nbDismissDef}`);
    check("l'etape 1 l'utilise",
        /const dismissed = await dismissOpenPopups\(r\);/.test(src));
    check("le remede l'utilise",
        /dismissPopups:\s*\(\)\s*=>\s*dismissOpenPopups\(r\)/.test(src));

    // -- 8. Le predicat du remede est CELUI du cran 8. S'ils divergeaient, le remede
    //    pourrait se declarer victorieux sur un critere que le cycle refuse.
    console.log("\n[8] le remede et le cran 8 mesurent la MEME chose");
    check("`campaignVisible` interroge `findButtonBySuffix(r, NODE_SUFFIX)`",
        /campaignVisible:[\s\S]{0,200}findButtonBySuffix\(r, NODE_SUFFIX\)/.test(src));

    // -- 9. Les bornes du remede sont DITES a l'operateur au moment ou il les paie.
    console.log("\n[9] les bornes sont annoncees dans le journal");
    check("le log du wedge cite les trois bornes",
        branche.includes("WEDGE_REMEDY_ATTEMPTS")
        && branche.includes("WEDGE_REMEDY_POPUP_WAIT_MS")
        && branche.includes("WEDGE_REMEDY_NAV_WAIT_MS"));
}

async function main(): Promise<number> {
    console.log("[390] le warmup applique lui-meme le remede qu'il nomme\n");
    await etage1();
    etage2();

    console.log(`\n[390] ${checks - failures.length}/${checks} verifications OK`);
    if (failures.length) {
        console.log("[390] VERDICT : ECHEC");
        for (const f of failures) console.log(`  - ${f}`);
        return 1;
    }
    console.log("[390] VERDICT : sur wedge detecte, le cycle ferme les popups puis "
        + "invoque la nav du jeu, dans une borne declaree, et sa trace distingue "
        + "'non tente' / 'sans effet' / 'il a porte'.");
    return 0;
}

main().then((rc) => process.exit(rc)).catch((e) => {
    console.log(`[390] ERREUR : ${(e as Error).stack}`);
    process.exit(1);
});
