// #285-r1 -- EPREUVE HORS FRIDA de la porte de warmup.
//
// Ce que ce probe mesure, et ce qu'il NE mesure PAS. Il exerce la LOGIQUE de
// `warm-gate.ts` avec un `runWarmup` factice : marquage, coup unique, file
// unique, echappatoire, et le chemin d'echec. Il ne touche ni Frida, ni le jeu,
// ni le host -- donc il ne prouve RIEN du CABLAGE dans `rpcCall`. Cette moitie-la
// se mesure en live par `scripts/python/probe_285r1_warm_gate.py`, qui exige un
// host portant ce code. Les deux sont necessaires : une porte juste et non
// cablee se lit exactement comme une porte qui marche.
//
// USAGE  (depuis frida/)
//   node node_modules/tsx/dist/cli.mjs host/warm-gate.probe.ts

import {
    ensureWarmForCreation, forgetSession, getWarmState, isWarmed,
    markWarmed, noteRpcResult, isColdSessionRefusal, WARM_GATE_MARKER,
} from "./warm-gate.js";

let checks = 0;
const failures: string[] = [];

function check(label: string, ok: boolean, detail = ""): void {
    checks += 1;
    console.log(`  [${ok ? "OK  " : "FAIL"}] ${label}${detail ? ` -- ${detail}` : ""}`);
    if (!ok) failures.push(`${label} -- ${detail}`);
}

/** Un `runWarmup` factice qui COMPTE ses appels : c'est l'instrument qui
 *  distingue « la porte a warme » de « la porte a warme QUATRE FOIS ». */
function fakeWarmup(opts: { ok: boolean; delayMs?: number }) {
    const calls = { n: 0 };
    const fn = async (_sid: number): Promise<unknown> => {
        calls.n += 1;
        if (opts.delayMs) await new Promise((r) => setTimeout(r, opts.delayMs));
        return opts.ok ? { ok: true, capturedAt: "0xdead" } : { ok: false, err: "boom" };
    };
    return { fn, calls };
}

async function main(): Promise<number> {
    console.log("[285-r1] epreuve hors Frida de la porte de warmup\n");

    // -- 1. Une session neuve est FROIDE. Le defaut doit etre le refus de
    //       supposer, pas la confiance.
    console.log("[1] etat initial");
    forgetSession(1);
    check("une session inconnue n'est PAS chaude", !isWarmed(1));

    // -- 2. La porte WARME et laisse passer. C'est le comportement nominal :
    //       l'appelant ne voit rien, il obtient juste une session chaude.
    console.log("\n[2] session froide -> la porte warme, puis laisse passer");
    const w2 = fakeWarmup({ ok: true });
    await ensureWarmForCreation(1, "initAndStart", w2.fn);
    check("le warmup a ete declenche", w2.calls.n === 1, `appels=${w2.calls.n}`);
    check("la session est declaree chaude", isWarmed(1));
    check("l'origine est tracee comme `auto`",
        getWarmState().warmed.find((x) => x.sessionId === 1)?.how === "auto");

    // -- 3. COUP UNIQUE. Le warmup pilote l'UI du jeu (~12 s) : le rejouer
    //       devant chaque creation perturberait les runners deja en place.
    console.log("\n[3] coup unique : une session chaude ne se re-warme pas");
    const w3 = fakeWarmup({ ok: true });
    await ensureWarmForCreation(1, "buildPatchedRunner", w3.fn);
    check("aucun second warmup", w3.calls.n === 0, `appels=${w3.calls.n}`);

    // -- 4. FILE UNIQUE. Quatre agents qui buildent en parallele sur une session
    //       froide ne doivent declencher QU'UN warmup -- quatre navigations UI
    //       concurrentes dans le meme process casseraient le jeu.
    console.log("\n[4] file unique : 4 creations concurrentes -> 1 seul warmup");
    forgetSession(2);
    const w4 = fakeWarmup({ ok: true, delayMs: 40 });
    await Promise.all([1, 2, 3, 4].map(() =>
        ensureWarmForCreation(2, "initAndStart", w4.fn)));
    check("un seul warmup pour 4 appelants", w4.calls.n === 1, `appels=${w4.calls.n}`);
    check("la session est chaude", isWarmed(2));

    // -- 5. LE CHEMIN D'ECHEC. Quand le warmup echoue, il n'y a plus de bon
    //       resultat possible : on refuse, et le refus NOMME sa cause.
    console.log("\n[5] warmup en echec -> refus, et le refus se nomme");
    forgetSession(3);
    const w5 = fakeWarmup({ ok: false });
    let refused: unknown = null;
    try {
        await ensureWarmForCreation(3, "initAndStart", w5.fn);
    } catch (e) { refused = e; }
    check("la creation est refusee", refused !== null);
    check("le refus est un ColdSessionError", isColdSessionRefusal(refused));
    const msg = (refused as Error)?.message ?? "";
    check("le message porte le marqueur", msg.includes(WARM_GATE_MARKER),
        msg.slice(0, 90));
    check("le message est ASCII (cp1252-safe)",
        // eslint-disable-next-line no-control-regex
        /^[\x00-\x7F]*$/.test(msg),
        "un non-ASCII ferait crasher le print du lecteur Python");
    check("le message nomme le remede", msg.includes("/api/admin/warmup"));
    check("la session reste FROIDE apres un echec", !isWarmed(3));
    check("l'echec est compte", getWarmState().autoWarmupFailures >= 1,
        `failures=${getWarmState().autoWarmupFailures}`);

    // -- 5bis. Un echec ne doit pas CONDAMNER la session : le warmup suivant
    //          doit pouvoir reussir. Sinon un incident transitoire figerait la
    //          session jusqu'au prochain reinject.
    console.log("\n[5bis] un echec ne condamne pas la session");
    const w5b = fakeWarmup({ ok: true });
    await ensureWarmForCreation(3, "initAndStart", w5b.fn);
    check("un warmup ulterieur reussit", isWarmed(3) && w5b.calls.n === 1);

    // -- 6. LECTURE DU RESULTAT. Les trois voies de warmup (inject enchaine,
    //       /api/admin/warmup, appel direct au RPC) marquent la session sans
    //       une ligne de code chez elles.
    console.log("\n[6] un warmup reussi par une AUTRE voie marque la session");
    forgetSession(4);
    noteRpcResult(4, "warmupGameSingletons", { ok: true });
    check("marquee par lecture du resultat", isWarmed(4));
    check("l'origine est tracee comme `observed`",
        getWarmState().warmed.find((x) => x.sessionId === 4)?.how === "observed");
    forgetSession(5);
    noteRpcResult(5, "warmupGameSingletons", { ok: false });
    check("un warmup ok=false ne marque PAS", !isWarmed(5));
    forgetSession(6);
    noteRpcResult(6, "battleStatus", { ok: true });
    check("une autre RPC ne marque PAS", !isWarmed(6));

    // -- 7. `already-ready` COMPTE. C'est la reponse du RPC quand les singletons
    //       sont deja captures -- un succes, pas un echec. La confondre ferait
    //       re-warmer en boucle une session parfaitement chaude.
    console.log("\n[7] `already-ready` est un succes");
    forgetSession(7);
    noteRpcResult(7, "warmupGameSingletons", { ok: true, skipped: "already-ready" });
    check("already-ready marque la session", isWarmed(7));

    // -- 8. L'ECHAPPATOIRE existe, et elle est CONSCIENTE. Sans elle, un
    //       diagnostic legitime sur session froide deviendrait impossible.
    console.log("\n[8] echappatoire TACTICUS_ALLOW_COLD_RUNNER=1");
    forgetSession(8);
    process.env.TACTICUS_ALLOW_COLD_RUNNER = "1";
    const w8 = fakeWarmup({ ok: false });
    let threw = false;
    try { await ensureWarmForCreation(8, "initAndStart", w8.fn); } catch { threw = true; }
    check("la creation passe malgre une session froide", !threw);
    check("et AUCUN warmup n'est declenche", w8.calls.n === 0, `appels=${w8.calls.n}`);
    check("l'echappatoire est PUBLIEE dans l'etat", getWarmState().escapeHatch === true,
        "une echappatoire invisible se lit comme un gate qui ne mord pas");
    delete process.env.TACTICUS_ALLOW_COLD_RUNNER;

    // -- 9. OUBLI. Une session morte n'est plus chaude : son script est parti,
    //       donc les caches Frida-side qu'un warmup avait remplis aussi.
    console.log("\n[9] une session morte redevient froide");
    check("forgetSession efface l'etat", (() => {
        forgetSession(1); return !isWarmed(1);
    })());

    console.log(`\n[285-r1] ${checks - failures.length}/${checks} verifications OK`);
    if (failures.length) {
        console.log("[285-r1] VERDICT : ECHEC");
        for (const f of failures) console.log(`  - ${f}`);
        return 1;
    }
    console.log("[285-r1] VERDICT : la porte warme, une seule fois, une seule file, "
        + "et nomme sa cause quand elle refuse.");
    return 0;
}

main().then((rc) => process.exit(rc)).catch((e) => {
    console.log(`[285-r1] ERREUR : ${(e as Error).stack}`);
    process.exit(1);
});
