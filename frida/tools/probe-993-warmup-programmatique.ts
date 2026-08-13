/* Garde de #993 -- le warmup entre et sort de bataille SANS UN SEUL CLIC, et l'ordre des trois
 * appels natifs est un INVARIANT, pas une habitude.
 *
 * Lancement (depuis `frida/`) :
 *     node node_modules/tsx/dist/cli.mjs tools/probe-993-warmup-programmatique.ts
 *
 * POURQUOI CE HARNAIS EXISTE. Le cycle n'est pas rejouable a volonte : il lance une VRAIE
 * bataille, exige une session Frida vivante, et ses gestes sont IRREVERSIBLES. La question
 * « l'ordre des appels est-il tenu ? » ne peut donc pas etre posee au jeu a chaque edition. Elle
 * se decoupe en deux, et les DEUX etages sont necessaires : une logique juste mais non cablee se
 * lit exactement comme un cycle qui marche, et un cablage vers une logique fausse aussi.
 *
 *   ETAGE 1 -- COMPORTEMENT. Exerce `runEntreeProgrammatique` (le code de PRODUCTION, pas une
 *   copie) avec des doublures qui COMPTENT et ORDONNENT leurs appels. C'est le seul instrument
 *   qui distingue « ContinueSurrender a ete appelee » de « ContinueSurrender a ete appelee SANS
 *   que l'effet d'OnBattleSurrender ait ete observe » -- la faute exacte qui a laisse le jeu
 *   SANS ECRAN RENDU le 2026-08-12.
 *
 *   ETAGE 2 -- CABLAGE. Confronte le SOURCE de `hooks/features/warmup-singletons.ts` au
 *   contrat : les trois appels passent par leurs FOYERS, le capteur qui ancre
 *   `StartCampaignMatch` est DEPOSE avant l'invoke, les arguments sont les constantes MESUREES,
 *   et il ne reste AUCUN pilotage d'UI ni aucun repli vers lui.
 *
 * CE QU'IL NE MESURE PAS : que le bundle injecte capture reellement la source. Cela exige une
 * session vivante -- c'est la confrontation live, et elle est distincte de ce garde-ci.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
    runEntreeProgrammatique, EntreeProgDeps, EntreeProgReason, EntreeProgResult,
    EffetDeSurrender, SortieMethode,
    PROG_CAPTURE_WAIT_MS, PROG_CHARGEMENT_WAIT_MS, PROG_PORTE_WAIT_MS, PROG_POPUP_WAIT_MS,
    PROG_EFFET_WAIT_MS, PROG_FIN_WAIT_MS, PROG_META_WAIT_MS,
} from "../hooks/features/warmup-programmatique.js";

let checks = 0;
const failures: string[] = [];

function check(label: string, ok: boolean, detail = ""): void {
    checks += 1;
    console.log(`  [${ok ? "OK  " : "FAIL"}] ${label}${detail ? ` -- ${detail}` : ""}`);
    if (!ok) failures.push(`${label} -- ${detail}`);
}

// --- Doublures instrumentees -------------------------------------------------------

interface FakeSpec {
    /** Ce que rend `enBataille`, indexe par appel (dernier repete). */
    enBataille?: Array<boolean | null>;
    lancer?: { ok: boolean; err?: string };
    /** Ce que rend `attendreCapture`, indexe par appel (dernier repete). */
    capture?: Array<string | null>;
    popup?: boolean[];
    charge?: boolean[];
    garde?: Array<boolean | null>;
    desarme?: { ok: boolean; err?: string };
    meta?: boolean[];
    porte?: boolean[];
    /** Ce que rend `invoquerSortie`, indexe par appel (dernier repete). */
    sortie?: Array<{ ok: boolean; err?: string }>;
    effet?: EffetDeSurrender[];
    fin?: boolean[];
}

interface FakeCalls {
    /** LA trace qui compte : chaque effet significatif, DANS L'ORDRE. C'est elle qui repond a
     *  « ContinueSurrender a-t-elle ete appelee apres l'observation ? », qu'aucun compteur seul
     *  ne peut trancher. */
    ordre: string[];
    sorties: SortieMethode[];
    lancers: number;
    /** Les timeouts demandes, par effet -- pour verifier que le budget paye est celui declare. */
    attentes: Record<string, number[]>;
    logs: string[];
}

function makeFakes(spec: FakeSpec): { deps: EntreeProgDeps; calls: FakeCalls } {
    const calls: FakeCalls = {
        ordre: [], sorties: [], lancers: 0,
        attentes: { capture: [], charge: [], porte: [], effet: [], popup: [], fin: [], meta: [] },
        logs: [],
    };
    const pick = <T>(arr: T[] | undefined, i: number, dflt: T): T => {
        if (!arr || arr.length === 0) return dflt;
        return arr[Math.min(i, arr.length - 1)] as T;
    };
    let nEnBataille = 0;
    let nCapture = 0;
    let nPorte = 0;
    let nEffet = 0;
    let nFin = 0;
    let nSortie = 0;
    let nPopup = 0;
    let nCharge = 0;
    let nGarde = 0;
    let nMeta = 0;

    return {
        calls,
        deps: {
            enBataille: async () => {
                const v = pick<boolean | null>(spec.enBataille, nEnBataille, false);
                nEnBataille += 1;
                calls.ordre.push(`enBataille=${String(v)}`);
                return v;
            },
            lancerBataille: async () => {
                calls.lancers += 1;
                calls.ordre.push("StartCampaignMatch");
                return spec.lancer ?? { ok: true };
            },
            attendreCapture: async (ms) => {
                const v = pick<string | null>(spec.capture, nCapture, "0xCAFE");
                nCapture += 1;
                calls.attentes.capture.push(ms);
                calls.ordre.push(`capture=${v ?? "null"}`);
                return v;
            },
            gardeDejaEnCours: async () => {
                const v = pick<boolean | null>(spec.garde, nGarde, false);
                nGarde += 1;
                calls.ordre.push(`garde=${String(v)}`);
                return v;
            },
            desarmerGarde: async () => {
                calls.ordre.push("SetBattleNotRunning");
                return spec.desarme ?? { ok: true };
            },
            attendreChargementTermine: async (ms) => {
                const v = pick(spec.charge, nCharge, true);
                nCharge += 1;
                calls.attentes.charge.push(ms);
                calls.ordre.push(`chargeFini=${String(v)}`);
                return v;
            },
            attendreDisparitionDuPopup: async (ms) => {
                const v = pick(spec.popup, nPopup, true);
                nPopup += 1;
                calls.attentes.popup.push(ms);
                calls.ordre.push(`popupCache=${String(v)}`);
                return v;
            },
            attendreMetaChargee: async (ms) => {
                const v = pick(spec.meta, nMeta, true);
                nMeta += 1;
                calls.attentes.meta.push(ms);
                calls.ordre.push(`meta=${String(v)}`);
                return v;
            },
            attendrePorteDeSortie: async (ms) => {
                const v = pick(spec.porte, nPorte, true);
                nPorte += 1;
                calls.attentes.porte.push(ms);
                calls.ordre.push(`porte=${String(v)}`);
                return v;
            },
            invoquerSortie: async (m) => {
                const v = pick(spec.sortie, nSortie, { ok: true });
                nSortie += 1;
                calls.sorties.push(m);
                calls.ordre.push(m);
                return v;
            },
            attendreEffetDeSurrender: async (ms) => {
                const v = pick<EffetDeSurrender>(
                    spec.effet, nEffet, "popup-de-confirmation");
                nEffet += 1;
                calls.attentes.effet.push(ms);
                calls.ordre.push(`effet=${v}`);
                return v;
            },
            attendreFinDeBataille: async (ms) => {
                const v = pick(spec.fin, nFin, true);
                nFin += 1;
                calls.attentes.fin.push(ms);
                calls.ordre.push(`fin=${String(v)}`);
                return v;
            },
            log: (m: string) => { calls.logs.push(m); },
        },
    };
}

const isAscii = (s: string): boolean =>
    // eslint-disable-next-line no-control-regex
    /^[\x00-\x7F]*$/.test(s);

/** L'index du premier element egal a `x`, ou -1. */
function idx(a: string[], x: string): number { return a.indexOf(x); }

// --- ETAGE 1 : le comportement -----------------------------------------------------

async function etage1(): Promise<void> {
    console.log("[993] ETAGE 1 -- comportement du cycle (doublures instrumentees)\n");

    // -- 1. LE CHEMIN NOMINAL, et son ORDRE. Les trois appels natifs, dans cet ordre-la, et
    //    chacun separe du suivant par l'OBSERVATION de son effet.
    console.log("[1] chemin nominal : trois appels, chacun valide par son EFFET");
    {
        const f = makeFakes({});
        const res = await runEntreeProgrammatique(f.deps);
        check("ok", res.ok);
        check("motif = capture-et-retraite",
            res.reason === "capture-et-retraite", res.reason);
        check("la capture est rendue", res.capturedAt === "0xCAFE", `${res.capturedAt}`);
        check("les DEUX sorties invoquees, dans l'ordre",
            f.calls.sorties.join(",") === "OnBattleSurrender,ContinueSurrender",
            f.calls.sorties.join(","));
        check("le lancement precede la capture",
            idx(f.calls.ordre, "StartCampaignMatch") < idx(f.calls.ordre, "capture=0xCAFE"));
        check("la capture precede la retraite",
            idx(f.calls.ordre, "capture=0xCAFE") < idx(f.calls.ordre, "OnBattleSurrender"));
        check("aucune bataille heritee", res.batailleHeritee === false);
    }

    // -- 2. L'INVARIANT CENTRAL. `ContinueSurrender` n'est JAMAIS appelee sans que l'effet
    //    d'`OnBattleSurrender` ait ete OBSERVE. Mesure du 2026-08-12 : appelee seule, elle
    //    termine bien la bataille (`get_IsBattleActive -> False`) et laisse le jeu SANS AUCUN
    //    ECRAN RENDU -- il a fallu `ToTacticiansMenu()` pour le recuperer.
    console.log("\n[2] INVARIANT : `ContinueSurrender` exige l'effet OBSERVE d'OnBattleSurrender");
    {
        const f = makeFakes({ effet: ["rien"] });
        const res = await runEntreeProgrammatique(f.deps);
        check("pas ok", !res.ok);
        check("motif = effet-de-surrender-absent",
            res.reason === "effet-de-surrender-absent", res.reason);
        check("`ContinueSurrender` N'A PAS ete appelee",
            !f.calls.sorties.includes("ContinueSurrender"), f.calls.sorties.join(","));
        check("`OnBattleSurrender` l'a bien ete (l'entree, elle, est jouee)",
            f.calls.sorties.join(",") === "OnBattleSurrender", f.calls.sorties.join(","));
        check("l'effet est OBSERVE apres l'appel, jamais avant",
            idx(f.calls.ordre, "OnBattleSurrender") < idx(f.calls.ordre, "effet=rien"));
        check("le step nomme le regime evite",
            res.steps.some((s) => (s.info ?? "").includes("SANS ECRAN RENDU")));
    }

    // -- 1ter. LE GARDE RESIDUEL. `get_IsActive` reste ARME apres un lancement avorte, et il fait
    //    refuser TOUS les lancements suivants en silence -- pendant que la capture, elle, reussit.
    //    Il n'est desarme QUE dans l'etat sans ambiguite : arme sans aucune bataille.
    console.log("\n[1ter] le garde residuel `IsActive` est detecte et desarme, jamais suppose");
    {
        const f = makeFakes({});
        await runEntreeProgrammatique(f.deps);
        check("le garde est lu AVANT le lancement",
            idx(f.calls.ordre, "garde=false") < idx(f.calls.ordre, "StartCampaignMatch"),
            f.calls.ordre.join(" -> "));
        check("et rien n'est desarme quand il n'est pas arme",
            !f.calls.ordre.includes("SetBattleNotRunning"));
    }
    {
        const f = makeFakes({ garde: [true, false] });
        const res = await runEntreeProgrammatique(f.deps);
        check("garde arme -> desarme, puis on lance", res.ok, res.reason);
        check("`SetBattleNotRunning` a ete appele UNE fois",
            f.calls.ordre.filter((x) => x === "SetBattleNotRunning").length === 1,
            f.calls.ordre.join(" -> "));
        check("le desarmement est RELU (on ne suppose pas qu'il a porte)",
            f.calls.ordre.filter((x) => x.startsWith("garde=")).length === 2,
            f.calls.ordre.join(" -> "));
        check("le step DIT que c'etait un residu", res.steps.some(
            (s) => s.step === "prog-garde-deja-en-cours" && (s.info ?? "").includes("RESIDU")));
    }
    {
        const f = makeFakes({ garde: [true, true] });
        const res = await runEntreeProgrammatique(f.deps);
        check("desarmement sans effet -> motif = garde-deja-en-cours-arme",
            res.reason === "garde-deja-en-cours-arme", res.reason);
        check("RIEN n'a ete lance", f.calls.lancers === 0, `lancers=${f.calls.lancers}`);
    }
    {
        const f = makeFakes({ garde: [null] });
        const res = await runEntreeProgrammatique(f.deps);
        check("garde NON MESURE -> refus, et aucun desarmement a l'aveugle",
            res.reason === "garde-deja-en-cours-arme"
            && !f.calls.ordre.includes("SetBattleNotRunning"), res.reason);
    }

    // -- 2-0. LE SIGNAL DECISIF, ET IL PASSE AVANT TOUT LE RESTE. `thor.Loader$$LoadScene` refuse
    //    EN SILENCE tant qu'un chargement est en cours : se retirer dans cette fenetre annule le
    //    retour au meta sans un mot. Mesure du 2026-08-13 : `__loadingStep` vaut 1 -> 6 -> 10
    //    puis retombe a 0 a t=10,8 s, et les TROIS cycles qui ont bloque le jeu se retiraient
    //    entre 8 et 10 s.
    console.log("\n[2-0] le chargement de scene est attendu AVANT toute tentative de retraite");
    {
        const f = makeFakes({});
        await runEntreeProgrammatique(f.deps);
        check("`chargeFini` est lu avant `OnBattleSurrender`",
            idx(f.calls.ordre, "chargeFini=true") < idx(f.calls.ordre, "OnBattleSurrender"),
            f.calls.ordre.join(" -> "));
        // ⚠ ET LE CHARGEUR EST INTERROGE AVANT LE LANCEMENT AUSSI : c'est le symetrique exact.
        // Lancer pendant que la scene META charge fait refuser `LoadBattle` en silence, et la
        // CAPTURE reussit quand meme -- donc rien ne le signale avant 20 s plus loin.
        check("le chargeur est aussi interroge AVANT `StartCampaignMatch`",
            idx(f.calls.ordre, "chargeFini=true") < idx(f.calls.ordre, "StartCampaignMatch"),
            f.calls.ordre.join(" -> "));
        // ⚠ ET APRES LA PORTE, PAS AVANT : juste apres l'invoke, le chargeur rend `0` parce
        // qu'il n'a PAS ENCORE DEMARRE. Une garde satisfaite par l'etat d'avant le geste ne
        // garde rien -- c'est exactement ce qui a fait passer un cycle qui ne montait aucune
        // scene de bataille.
        const iPorte = idx(f.calls.ordre, "porte=true");
        const iChargeApres = f.calls.ordre.indexOf("chargeFini=true", iPorte);
        check("la garde de SORTIE vient APRES la porte (le chargeur a alors demarre)",
            iPorte > 0 && iChargeApres > iPorte, f.calls.ordre.join(" -> "));
    }
    {
        const f = makeFakes({ charge: [false] });
        const res = await runEntreeProgrammatique(f.deps);
        check("chargement en cours -> motif = chargement-en-cours",
            res.reason === "chargement-en-cours", res.reason);
        check("AUCUNE sortie invoquee", f.calls.sorties.length === 0,
            f.calls.sorties.join(","));
        // Le refus tombe AVANT le lancement : rien n'est lance, donc il n'y a pas de capture.
        check("et RIEN n'a ete lance", f.calls.lancers === 0, `lancers=${f.calls.lancers}`);
        check("aucune capture rendue", res.capturedAt === null, `${res.capturedAt}`);
        check("le step nomme le refus SILENCIEUX du retour au meta",
            res.steps.some((s) => (s.info ?? "").includes("en silence")));
    }

    // -- 2bis. L'EFFET DE `ContinueSurrender` SE MESURE AUSSI. Mesure du 2026-08-13 : l'invoke
    //    rend `ok`, la bataille se termine, et le jeu RESTE sur le popup de confirmation --
    //    `GenericMessagePopup(Clone)` toujours a l'ecran, 6 boutons, aucune scene meta. Le
    //    retour de l'appel ne prouve rien ; le signal `cache-debut`, si.
    console.log("\n[2bis] l'effet de `ContinueSurrender` est MESURE, pas suppose");
    {
        const f = makeFakes({ popup: [false] });
        const res = await runEntreeProgrammatique(f.deps);
        check("popup toujours affiche -> motif = popup-toujours-affiche",
            res.reason === "popup-toujours-affiche", res.reason);
        check("`ContinueSurrender` avait pourtant rendu ok",
            f.calls.sorties.includes("ContinueSurrender"));
        check("la capture reste rendue", res.capturedAt === "0xCAFE");
        check("aucune attente de fin de bataille jetee apres ce constat",
            f.calls.attentes.fin.length === 0, `${f.calls.attentes.fin.length}`);
    }
    {
        const f = makeFakes({});
        await runEntreeProgrammatique(f.deps);
        check("le signal `cache-debut` est lu APRES l'invoke de ContinueSurrender",
            idx(f.calls.ordre, "ContinueSurrender") < idx(f.calls.ordre, "popupCache=true"),
            f.calls.ordre.join(" -> "));
        check("et AVANT le constat de fin de bataille",
            idx(f.calls.ordre, "popupCache=true") < idx(f.calls.ordre, "fin=true"));
    }

    // -- 2ter. `get_IsBattleActive == false` NE SUFFIT PAS. Mesure du 2026-08-12 : il rend
    //    `false` aussi bien apres une retraite reussie qu'apres celle qui laisse le jeu sans
    //    rien afficher. Le discriminant est le RE-chargement de la scene meta.
    console.log("\n[2ter] la fin de bataille ne suffit pas : la scene meta doit etre REMONTEE");
    {
        const f = makeFakes({ meta: [false] });
        const res = await runEntreeProgrammatique(f.deps);
        check("pas ok", !res.ok);
        check("motif = meta-non-chargee", res.reason === "meta-non-chargee", res.reason);
        check("la fin de bataille avait pourtant ete VUE",
            f.calls.ordre.includes("fin=true"), f.calls.ordre.join(" -> "));
        check("le step de fin dit lui-meme qu'il ne suffit pas",
            res.steps.some((s) => s.step.endsWith("-fin-de-bataille")
                && (s.info ?? "").includes("PAS SUFFISANT")));
        check("le meta est le DERNIER cran",
            f.calls.ordre[f.calls.ordre.length - 1] === "meta=false",
            f.calls.ordre.join(" -> "));
    }

    // -- 3. L'AUTRE BRANCHE DU NATIF. `PauseSurrender` rend un BOOLEEN : il DIFFERE (popup) ou
    //    il laisse passer. Supposer le popup ferait echouer a tort la seconde branche, et
    //    appeler `ContinueSurrender` sur une bataille DEJA finie serait entrer par le milieu.
    console.log("\n[3] `PauseSurrender` n'a pas differe -> pas de popup, et pas de Continue");
    {
        const f = makeFakes({ effet: ["bataille-terminee"] });
        const res = await runEntreeProgrammatique(f.deps);
        check("ok malgre l'absence de popup", res.ok, res.reason);
        check("motif = capture-et-retraite",
            res.reason === "capture-et-retraite", res.reason);
        check("`ContinueSurrender` est SANS OBJET et n'est pas appelee",
            !f.calls.sorties.includes("ContinueSurrender"), f.calls.sorties.join(","));
        check("aucune attente de fin jetee (la bataille est deja finie)",
            f.calls.attentes.fin.length === 0, `${f.calls.attentes.fin.length}`);
        check("le step DIT pourquoi Continue est sautee",
            res.steps.some((s) => (s.info ?? "").includes("SANS OBJET")));
        // Le cran meta vaut sur les DEUX branches : un raccourci qui le sauterait ici rendrait
        // `ok: true` sur un ecran noir, exactement le regime qu'on cherche a exclure.
        check("le cran meta est joue AUSSI sur cette branche",
            f.calls.attentes.meta.length === 1, `${f.calls.attentes.meta.length}`);
    }

    // -- 4. L'ETAT NON MESURE N'EST PAS UN `false`. Lancer une bataille en croyant qu'aucune ne
    //    tourne ferait refuser `StartMatch(checkIfAlreadyRunning: true)` EN SILENCE, et on
    //    attendrait 20 s une capture qui ne viendrait jamais.
    console.log("\n[4] etat de bataille NON MESURE -> aucun lancement");
    {
        const f = makeFakes({ enBataille: [null] });
        const res = await runEntreeProgrammatique(f.deps);
        check("pas ok", !res.ok);
        check("motif = etat-de-bataille-non-mesure",
            res.reason === "etat-de-bataille-non-mesure", res.reason);
        check("RIEN n'a ete lance", f.calls.lancers === 0, `lancers=${f.calls.lancers}`);
        check("RIEN n'a ete invoque en sortie", f.calls.sorties.length === 0);
        check("le step nomme `checkIfAlreadyRunning`",
            res.steps.some((s) => (s.info ?? "").includes("checkIfAlreadyRunning")));
    }

    // -- 5. L'ECRAN DE BATAILLE HERITE. Le cycle s'en sort AVANT de lancer -- sans quoi il ne
    //    serait autonome qu'une fois sur deux, exactement le defaut que le cycle d'UI a mis deux
    //    tranches a reparer.
    console.log("\n[5] bataille heritee -> on en SORT d'abord, puis on lance");
    {
        const f = makeFakes({ enBataille: [true, false] });
        const res = await runEntreeProgrammatique(f.deps);
        check("ok", res.ok, res.reason);
        check("la bataille heritee est SIGNALEE", res.batailleHeritee === true);
        check("QUATRE invocations de sortie (deux retraites)",
            f.calls.sorties.length === 4, f.calls.sorties.join(","));
        check("la premiere retraite precede le lancement",
            idx(f.calls.ordre, "OnBattleSurrender") < idx(f.calls.ordre, "StartCampaignMatch"),
            f.calls.ordre.join(" -> "));
        check("les deux retraites sont tracees SEPAREMENT",
            res.steps.some((s) => s.step.startsWith("prog-heritee-"))
            && res.steps.some((s) => s.step.startsWith("prog-retraite-")));
    }
    console.log("\n[5bis] bataille heritee dont on ne sort pas -> motif PROPRE, aucun lancement");
    {
        const f = makeFakes({ enBataille: [true], porte: [false] });
        const res = await runEntreeProgrammatique(f.deps);
        check("motif = bataille-heritee-non-quittee",
            res.reason === "bataille-heritee-non-quittee", res.reason);
        check("RIEN n'a ete lance", f.calls.lancers === 0, `lancers=${f.calls.lancers}`);
        check("le step precis (`porte-de-sortie`) est quand meme la",
            res.steps.some((s) => s.step === "prog-heritee-porte-de-sortie" && !s.ok));
    }

    // -- 6. UN INVOKE QUI REND LA MAIN NE PROUVE RIEN. `StartMatch` journalise et RETOURNE quand
    //    une bataille tourne deja : c'est la CAPTURE qui tranche, pas le retour de l'appel.
    console.log("\n[6] lancement invoque mais capture absente -> echec, et aucune retraite");
    {
        const f = makeFakes({ capture: [null] });
        const res = await runEntreeProgrammatique(f.deps);
        check("pas ok", !res.ok);
        check("motif = capture-absente", res.reason === "capture-absente", res.reason);
        check("la capture rendue est nulle", res.capturedAt === null, `${res.capturedAt}`);
        check("aucune retraite tentee sur une bataille qui n'a pas demarre",
            f.calls.sorties.length === 0, f.calls.sorties.join(","));
    }
    console.log("\n[6bis] invoke refuse -> on n'attend meme pas la capture");
    {
        const f = makeFakes({ lancer: { ok: false, err: "REFUS : confirmer" } });
        const res = await runEntreeProgrammatique(f.deps);
        check("motif = lancement-refuse", res.reason === "lancement-refuse", res.reason);
        check("aucune attente de capture jetee",
            f.calls.attentes.capture.length === 0, `${f.calls.attentes.capture.length}`);
        check("le message du refus est REPORTE tel quel",
            res.steps.some((s) => (s.info ?? "").includes("REFUS : confirmer")));
    }

    // -- 7. « CAPTURE OBTENUE, SORTIE RATEE » N'EST PAS « RIEN OBTENU ». Le pointeur reste rendu
    //    meme quand la retraite echoue : c'est ce qui permet a l'appelant de dire lequel des
    //    deux s'est produit.
    console.log("\n[7] capture obtenue puis sortie ratee -> le pointeur est QUAND MEME rendu");
    {
        const f = makeFakes({ porte: [false] });
        const res = await runEntreeProgrammatique(f.deps);
        check("pas ok", !res.ok);
        check("motif = porte-de-sortie-absente",
            res.reason === "porte-de-sortie-absente", res.reason);
        check("la capture est rendue malgre l'echec",
            res.capturedAt === "0xCAFE", `${res.capturedAt}`);
    }

    // -- 8. `stopAfterCapture` : le but fonctionnel est atteint a la capture. Le jeu reste en
    //    bataille, et c'est DIT.
    console.log("\n[8] stopAfterCapture -> aucune retraite, et le motif le dit");
    {
        const f = makeFakes({});
        const res = await runEntreeProgrammatique(f.deps, { stopAfterCapture: true });
        check("ok", res.ok);
        check("motif = capture-sans-retraite",
            res.reason === "capture-sans-retraite", res.reason);
        check("aucune sortie invoquee", f.calls.sorties.length === 0);
        check("le step dit que le jeu reste en bataille",
            res.steps.some((s) => (s.info ?? "").includes("reste en bataille")));
    }

    // -- 9. LES BORNES SONT CELLES QUI SONT DECLAREES. Un budget paye qui ne serait pas le
    //    budget publie rendrait les constantes decoratives.
    console.log("\n[9] les budgets payes sont les constantes EXPORTEES");
    {
        const f = makeFakes({});
        await runEntreeProgrammatique(f.deps);
        check("capture", f.calls.attentes.capture[0] === PROG_CAPTURE_WAIT_MS,
            `${f.calls.attentes.capture[0]}`);
        check("chargement termine", f.calls.attentes.charge[0] === PROG_CHARGEMENT_WAIT_MS,
            `${f.calls.attentes.charge[0]}`);
        check("popup se cache", f.calls.attentes.popup[0] === PROG_POPUP_WAIT_MS,
            `${f.calls.attentes.popup[0]}`);
        check("porte de sortie", f.calls.attentes.porte[0] === PROG_PORTE_WAIT_MS,
            `${f.calls.attentes.porte[0]}`);
        check("effet de surrender", f.calls.attentes.effet[0] === PROG_EFFET_WAIT_MS,
            `${f.calls.attentes.effet[0]}`);
        check("fin de bataille", f.calls.attentes.fin[0] === PROG_FIN_WAIT_MS,
            `${f.calls.attentes.fin[0]}`);
        check("meta chargee", f.calls.attentes.meta[0] === PROG_META_WAIT_MS,
            `${f.calls.attentes.meta[0]}`);
        check("l'observation du popup est la PLUS COURTE (animation, pas chargement)",
            PROG_EFFET_WAIT_MS < PROG_CAPTURE_WAIT_MS
            && PROG_EFFET_WAIT_MS < PROG_FIN_WAIT_MS,
            `${PROG_EFFET_WAIT_MS} vs ${PROG_CAPTURE_WAIT_MS}/${PROG_FIN_WAIT_MS}`);
        check("les deux animations de popup ont le MEME budget (meme nature d'evenement)",
            PROG_EFFET_WAIT_MS === PROG_POPUP_WAIT_MS,
            `${PROG_EFFET_WAIT_MS} / ${PROG_POPUP_WAIT_MS}`);
        check("le chargement a le budget le PLUS LARGE (son depassement casse le jeu)",
            PROG_CHARGEMENT_WAIT_MS > PROG_CAPTURE_WAIT_MS
            && PROG_CHARGEMENT_WAIT_MS > PROG_META_WAIT_MS,
            `${PROG_CHARGEMENT_WAIT_MS}`);
    }

    // -- 10. LE CYCLE NE PEUT PAS EXPLOSER, et chaque motif est DISTINCT. Un `ok: false` unique
    //     les confondrait -- et il n'y a plus de repli sur les clics pour rattraper : ce motif
    //     EST le diagnostic.
    console.log("\n[10] motifs deux a deux distincts, ASCII, et chaque step porte une info");
    {
        const scenarios: FakeSpec[] = [
            {},                                                   // capture-et-retraite
            { enBataille: [null] },                               // etat-non-mesure
            { enBataille: [true], porte: [false] },               // heritee-non-quittee
            { lancer: { ok: false } },                            // lancement-refuse
            { capture: [null] },                                  // capture-absente
            { garde: [null] },                                    // garde-arme (non mesure)
            { charge: [false] },                                  // chargement-en-cours
            { porte: [false] },                                   // porte-absente
            { sortie: [{ ok: false, err: "x" }] },                // surrender-refuse
            { effet: ["rien"] },                                  // effet-absent
            { sortie: [{ ok: true }, { ok: false, err: "y" }] },  // continue-refuse
            { popup: [false] },                                   // popup-toujours-affiche
            { fin: [false] },                                     // bataille-toujours-active
            { meta: [false] },                                    // meta-non-chargee
        ];
        const vus: EntreeProgReason[] = [];
        let asciiOk = true;
        let infoOk = true;
        let leve = false;
        for (const spec of scenarios) {
            let res: EntreeProgResult | null = null;
            try { res = await runEntreeProgrammatique(makeFakes(spec).deps); }
            catch { leve = true; continue; }
            vus.push(res.reason);
            if (!isAscii(res.reason)) asciiOk = false;
            for (const s of res.steps) {
                if (!isAscii(s.step) || !isAscii(s.info)) asciiOk = false;
                if (s.info.length === 0) infoOk = false;
            }
        }
        check("aucun scenario ne fait lever le cycle", !leve);
        check("14 motifs, tous distincts", new Set(vus).size === 14, vus.join(" / "));
        const attendu: EntreeProgReason[] = [
            "capture-et-retraite", "etat-de-bataille-non-mesure",
            "bataille-heritee-non-quittee", "lancement-refuse", "capture-absente",
            "garde-deja-en-cours-arme", "chargement-en-cours", "porte-de-sortie-absente",
            "surrender-refuse",
            "effet-de-surrender-absent",
            "continue-refuse", "popup-toujours-affiche", "bataille-toujours-active",
            "meta-non-chargee",
        ];
        check("et ce sont bien ceux-la", vus.join(",") === attendu.join(","), vus.join(","));
        check("tous les libelles sont ASCII (cp1252-safe)", asciiOk);
        check("chaque step porte une info non vide", infoOk);
        // `capture-sans-retraite` est le 14e, atteint uniquement via `stopAfterCapture`.
        const stop = await runEntreeProgrammatique(
            makeFakes({}).deps, { stopAfterCapture: true });
        check("le 15e motif (`capture-sans-retraite`) est distinct des 14 autres",
            !vus.includes(stop.reason), stop.reason);
    }
}

// --- ETAGE 2 : le cablage ----------------------------------------------------------

function lireSource(...parts: string[]): string {
    const ici = dirname(fileURLToPath(import.meta.url));
    return readFileSync(join(ici, "..", ...parts), "utf8");
}

/** Les lignes EXECUTABLES : un commentaire qui CITE l'ancien monde ne doit pas faire rougir un
 *  garde -- il punirait la doc, pas le defaut. (Lecon apprise par `probe-390` a son premier
 *  passage : il rougissait sur sa propre citation historique.) */
function executable(src: string): string {
    return src.split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");
}

function etage2(): void {
    console.log("\n[993] ETAGE 2 -- cablage dans le cycle (source verbatim)\n");
    const src = lireSource("hooks", "features", "warmup-singletons.ts");
    const exe = executable(src);

    // -- 1. Le module pur est IMPORTE et APPELE. Sans cela il vit en orbite : sa logique est
    //    juste et personne ne s'en sert.
    console.log("[1] le module pur est importe et appele");
    check("import de `runEntreeProgrammatique`",
        /import\s*\{[^}]*runEntreeProgrammatique[^}]*\}\s*from\s*"\.\/warmup-programmatique\.js"/s
            .test(src));
    check("appel de `runEntreeProgrammatique(`", exe.includes("runEntreeProgrammatique("));

    // -- 2. LES TROIS APPELS PASSENT PAR LEURS FOYERS. Les recopier ici ferait exister deux
    //    chaines dont une seule serait corrigee -- c'est litteralement ce qui est arrive a la
    //    chaine de CLICS (#332).
    console.log("\n[2] les trois appels passent par leurs FOYERS, jamais par une copie");
    check("l'entree passe par `invoquerCommande` (view-command)",
        /import\s*\{[^}]*invoquerCommande[^}]*\}\s*from\s*"\.\/view-command\.js"/s.test(src)
        && /invoquerCommande\(\{/.test(exe));
    check("la sortie passe par `provoquerRetraite` (retreat-capture)",
        /import\s*\{[^}]*provoquerRetraite[^}]*\}\s*from\s*"\.\/retreat-capture\.js"/s.test(src)
        && /provoquerRetraite\(\{/.test(exe));
    check("l'etat de bataille vient de `enBataille`, pas d'un proxy d'ecran",
        /import\s*\{[^}]*enBataille[^}]*\}\s*from\s*"\.\/retreat-capture\.js"/s.test(src)
        && /enBataille\(\)/.test(exe));
    check("aucun `Interceptor` ni `invokeMethod` sur la chaine de sortie ici",
        !/invokeMethod\([^)]*OnBattleSurrender/.test(exe));

    // -- 3. NE JAMAIS ANCRER LA METHODE QU'ON INVOQUE -- 3 gels sur 3, et un gel se lit comme un
    //    RPC qui ne revient pas. Le capteur #991 ancre precisement `StartCampaignMatch`.
    console.log("\n[3] le capteur qui ancre `StartCampaignMatch` est DEPOSE avant l'invoke");
    check("`deposerCapteur` est importe", /deposerCapteur/.test(src));
    const iDepot = exe.indexOf("deposerCapteur()");
    const iInvoke = exe.indexOf("methode: \"StartCampaignMatch\"");
    const iRepose = exe.indexOf("reposerCapteur()");
    check("le depot precede l'invoke", iDepot > 0 && iInvoke > iDepot, `${iDepot} < ${iInvoke}`);
    check("et la repose le suit", iRepose > iInvoke, `${iRepose}`);
    check("la repose est CONDITIONNEE (on ne repose pas ce qu'on n'a pas depose)",
        /if \(aReposer\)/.test(exe));
    check("elle est dans un `finally` (un invoke qui leve ne doit pas laisser l'ancrage bas)",
        /finally\s*\{[\s\S]{0,120}reposerCapteur/.test(exe));

    // -- 4. LES ARGUMENTS SONT LES VALEURS MESUREES. Composer une valeur plausible est
    //    exactement le geste que le capteur #991 existe pour eviter.
    console.log("\n[4] les arguments rejouent des valeurs OBSERVEES");
    check("`locationIndex` est une constante NOMMEE, pas un litteral au site d'appel",
        /const PROG_LOCATION_INDEX = \d+;/.test(src)
        && /args: \[CAMPAIGN_ID_INDOMITUS, PROG_LOCATION_INDEX,/.test(exe));
    check("sa provenance est ECRITE (capteur, tranche, build)",
        /VALEUR OBSERVEE, PAS CHOISIE/.test(src)
        && /startCampaignMatchCaptures/.test(src));
    check("le `Nullable<Boolean>` transporte les octets BRUTS observes",
        /const PROG_ENEMY_AI_BRUT = \{ brut: "0101", octets: 2 \}/.test(src));
    check("et le fait que sa disposition reste NON TRANCHEE est dit",
        /NON TRANCHEE/.test(src));

    // -- 5. IL NE RESTE AUCUN PILOTAGE D'UI, ET AUCUN REPLI VERS LUI. C'est la demande de la
    //    tranche, et c'est aussi ce qui rend la voie native VERIFIABLE : un repli silencieux la
    //    laisserait ceder sans que rien ne le signale.
    console.log("\n[5] AUCUN clic, AUCUN balayage de boutons, aucun repli vers l'UI");
    for (const interdit of [
        "PLAY_BUTTON_KEY", "PAUSE_BUTTON_KEY", "RETREAT_BUTTON_KEY", "RETREAT_CONFIRM_KEY",
        "clickUntilEffect", "waitForAndClick", "clicsDeRetraite", "retreatToCampaign",
        "runRetreatToCampaign", "runWedgeRemedy", "dismissOpenPopups", "clickByPath",
        "navToCampaignOnMainThread", "invokeToCampaign", "NODE_SUFFIX",
        // ⚠ CE SONT CEUX-LA QUI COMPTENT LE PLUS. Chercher un bouton, meme sans cliquer, c'est
        // interroger l'existence d'un objet -- or « le bouton existe » arrive des `montre-debut`,
        // et agir la est exactement ce qui a bloque le jeu sur le popup. Le signal correct est
        // `montre-fin`, et il ne s'obtient pas en enumerant.
        "enumerateButtons", "findButtonBySuffix", "findButtonByContains", "ensureRefs",
        "ui-nav.js", "UiRefs",
    ]) {
        check(`aucune trace de \`${interdit}\``, !src.includes(interdit));
    }
    check("aucun repli : le mot `repli` n'apparait dans aucune ligne executable",
        !/repli/i.test(exe));

    // -- 6. DES SIGNAUX, PAS DES DELAIS. Un repos fixe est un pari sur une duree ; le depot en a
    //    deja paye un (`SETTLE_BEFORE_CLICK_MS`, 800 ms) pour un clic qui restait avale. Le seul
    //    `sleep` tolere est l'intervalle de SONDAGE de `waitFor`.
    console.log("\n[6] que des signaux : aucun repos fixe hors intervalle de sondage");
    const nSleep = (exe.match(/\bsleep\(/g) ?? []).length;
    check("`sleep(` n'apparait que 2 fois : sa definition et le sondage de `waitFor`",
        nSleep === 2, `occurrences=${nSleep}`);
    check("et l'unique usage est bien dans `waitFor`",
        /async function waitFor[\s\S]{0,700}await sleep\(intervalMs\)/.test(src));
    check("les budgets sont declares comme des PLAFONDS",
        /PLAFONDS, jamais des attentes/.test(src));

    // -- 7. LES SIGNAUX VIENNENT DES ANCRAGES DE `ScreenVisibilityManager`, POUSSES.
    //    C'est la difference entre « le bouton existe » (`montre-debut`) et « le popup est
    //    affiche » (`montre-fin`) -- la fenetre entre les deux est celle ou le jeu se bloque.
    console.log("\n[7] les signaux sont des transitions POUSSEES, pas des sondages d'objets");
    check("le cycle s'abonne a `ecouterTransitions`",
        /import\s*\{[^}]*ecouterTransitions[^}]*\}\s*from\s*"\.\/ui-windows\.js"/s.test(src)
        && /const ecoute = ecouterTransitions\(\);/.test(exe));
    check("l'abonnement est OUVERT avant les appels et FERME dans un `finally`",
        exe.indexOf("ecouterTransitions()") < exe.indexOf("entreeCaptureRetraite(ecoute")
        && /finally\s*\{\s*ecoute\.fermer\(\);/.test(exe));
    check("l'effet d'`OnBattleSurrender` attend `montre-fin`, PAS `montre-debut`",
        /quoi === "montre-fin" && estLePopupDeConfirmation/.test(exe)
        && !/montre-debut/.test(exe));
    check("l'effet de `ContinueSurrender` attend `cache-debut`",
        /quoi === "cache-debut" && estLePopupDeConfirmation/.test(exe));
    check("le popup est identifie par sa CLASSE et son GuiId, pas par un chemin de bouton",
        /t\.classe === "GenericMessagePopup" \|\| t\.gui\.nom === "MessagePopup"/.test(exe));
    check("l'autre issue de l'attente est NATIVE (`enBataille`)",
        /attendreEffetDeSurrender:[\s\S]{0,700}enBataille\(\) === false/.test(exe));
    check("et la mesure qui justifie `montre-fin` est ECRITE",
        /montre-debut/.test(src) && /montre-fin/.test(src));

    // -- 8. LE CRAN FINAL NE DIT PAS AU JEU OU SE RETROUVER. Il exigeait le noeud de campagne ;
    //    mesure du 2026-08-13 : la retraite rend la main sur `Idun_UI_Navigation`, pas sur la
    //    campagne. Le critere est desormais « un ecran est remonte », et rien de plus.
    console.log("\n[8] le cycle ne dit pas au jeu ou se retrouver");
    check("le critere de sortie est `IdunNavigation` vivante",
        /function metaChargee\(\)/.test(src)
        && /attendreMetaChargee:[\s\S]{0,160}metaChargee\(\)/.test(exe));
    // -- 8bis. L'ETAT DU CHARGEUR EST UNE LIB, pas un helper enterre dans le warmup : la question
    //    « un changement de scene est-il en cours ? » conditionne TOUT geste qui en declenche un.
    check("le cycle lit l'etat du chargeur depuis `game/loader.js`",
        /import\s*\{[^}]*chargementEnCours[^}]*\}\s*from\s*"\.\.\/game\/loader\.js"/s.test(src)
        && /attendreChargementTermine:[\s\S]{0,200}chargementEnCours\(\) === false/.test(exe));
    check("et la lib ne redefinit pas le lecteur de statiques",
        !/staticFieldProbe/.test(src), "elle l'importe, elle ne le recopie pas");
    check("le cycle DIT que get_IsBattleActive ne distingue pas les deux etats",
        /rend `false` dans les deux cas/i.test(src));
    check("et il DIT que l'ecran d'arrivee n'est pas la campagne",
        /Idun_UI_Navigation/.test(src));

    // -- 8. LA SORTIE DU MODULE PUR EST REPORTEE TELLE QUELLE. Un `ok: false` generique
    //    effacerait le seul diagnostic disponible, maintenant qu'il n'y a plus de repli.
    console.log("\n[8] le motif du module pur devient l'erreur du warmup");
    check("les steps du module pur sont recopies dans ceux du cycle",
        /for \(const s of res\.steps\) steps\.push\(s\);/.test(exe));
    check("le motif est rendu comme `err`", /return \{ err: res\.reason \};/.test(exe));
    check("et l'appelant le remonte tel quel",
        /return \{ ok: false, err: entree\.err, steps \};/.test(exe));

    // -- 9. LE MODULE PUR RESTE PUR : aucun import, donc exercable hors Frida. Le jour ou il
    //    importerait `helpers.js`, ce probe cesserait de tourner -- en silence.
    console.log("\n[9] le module pur n'importe RIEN");
    const pur = lireSource("hooks", "features", "warmup-programmatique.ts");
    check("aucun `import` dans `warmup-programmatique.ts`",
        !/^\s*import\s/m.test(pur), "sinon il n'est plus exercable hors Frida");
}

async function main(): Promise<number> {
    console.log("[993] le warmup entre et sort de bataille sans un seul clic\n");
    await etage1();
    etage2();

    console.log(`\n[993] ${checks - failures.length}/${checks} verifications OK`);
    if (failures.length) {
        console.log("[993] VERDICT : ECHEC");
        for (const f of failures) console.log(`  - ${f}`);
        return 1;
    }
    console.log("[993] VERDICT : trois appels natifs, chacun valide par son EFFET ; "
        + "`ContinueSurrender` ne peut pas etre appelee sans l'entree qui la prepare ; "
        + "aucun pilotage d'UI ne subsiste et aucun repli ne masque une panne.");
    return 0;
}

main().then((rc) => process.exit(rc)).catch((e) => {
    console.log(`[993] ERREUR : ${(e as Error).stack}`);
    process.exit(1);
});
