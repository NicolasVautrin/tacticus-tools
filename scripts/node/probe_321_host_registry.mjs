// probe_321_host_registry.mjs -- garde OFFLINE des deux regles du cache host de
// runners qui, si elles cassaient, DETRUIRAIENT du travail en vol.
//
// Ce probe n'ouvre AUCUNE session Frida et ne parle a AUCUN host : il importe
// directement `frida/host/battle-store.ts` et `frida/host/runner-reconcile.ts`,
// les pilote, et verifie leur comportement. Il est donc rejouable a tout moment,
// y compris pendant qu'une session partagee est vivante.
//
// LES DEUX REGLES SOUS GARDE (#321) :
//
//   1. FERMETURE DE COURSE. `pruneRunners(keep, createdBefore)` ne purge QUE les
//      entrees enregistrees AVANT la photo du registre hooks. `keep` est une
//      photo prise a un instant T ; un runner cree par un autre agent a T+e en
//      est absent SANS ETRE MORT. Sans la borne, ce runner tout neuf serait
//      purge et ses dumps `logs/runs/<id>` effaces sous les pieds de son
//      proprietaire.
//
//   2. TRI-ETAT. `reconcileOnce()` sans session vivante rend `hooksCount = null`
//      et ne purge RIEN. « Je n'ai pas pu compter » n'est jamais « il n'y a
//      rien » : un timer qui purgerait sur mesure absente viderait le cache
//      pendant une fenetre de re-attache. Meme discipline que `host_inputs.py`
//      (#273) et que la jauge de drain (#285).
//
// Usage (depuis `frida/`, ou node_modules est installe) :
//   node node_modules/tsx/dist/cli.mjs ../scripts/node/probe_321_host_registry.mjs
//
// Sortie ASCII stricte (console Windows cp1252).

import { routeMessage } from "../../frida/host/router-messages.js";
import {
    initBattleStore, listRunners, countRunners, hasRunner,
    removeRunner, pruneRunners, registerRunner,
} from "../../frida/host/battle-store.js";
import { reconcileOnce } from "../../frida/host/runner-reconcile.js";

let failures = 0;

function check(label, cond, detail = "") {
    const tag = cond ? "OK  " : "FAIL";
    if (!cond) failures += 1;
    console.log(`  [${tag}] ${label}${detail ? "  -- " + detail : ""}`);
}

/** Simule l'arrivee d'un `battle_event` du hook : c'est la voie par laquelle le
 *  cache host apprend l'existence de la quasi-totalite des runners (auto-
 *  inference), et donc celle qu'il faut exercer pour un test realiste. */
function feedBattleEvent(runnerId, sessionId = 1, msg = "StartMatch") {
    const envelope = { type: "send", ts: new Date().toISOString(), payload: {} };
    routeMessage({
        sessionId,
        payload: { t: "battle_event", runnerId, msg, events: [], matchState: "{}" },
        envelope,
    });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

await initBattleStore();

// Le cache est un module singleton : on part d'une table propre pour que les
// verdicts ne dependent pas de ce qu'un import aurait laisse.
await pruneRunners(new Set());
check("table de depart vide", countRunners() === 0, `count=${countRunners()}`);

console.log("[1] auto-inference depuis battle_event");
feedBattleEvent(101);
feedBattleEvent(102);
check("2 entrees creees", countRunners() === 2, `count=${countRunners()}`);
check("hasRunner(101)", hasRunner(101) === true);
check("hasRunner(999) faux", hasRunner(999) === false);
check("configId absent (auto-inference, pas /api/launch)",
    listRunners().every((r) => r.configId === undefined));

console.log("[2] registerRunner (voie /api/launch) pose bien le configId");
registerRunner(103, 1, "cfg-abc");
check("configId pose", listRunners().find((r) => r.runnerId === 103)?.configId === "cfg-abc");

console.log("[3] removeRunner idempotent");
check("1er retrait -> true", (await removeRunner(103)) === true);
check("2e retrait -> false", (await removeRunner(103)) === false);
check("count redescendu", countRunners() === 2, `count=${countRunners()}`);

console.log("[4] REGLE 1 -- fermeture de course sur pruneRunners");
// Photo prise MAINTENANT : elle ne connait que 101.
await sleep(5);
const snapshotAt = Date.now();
await sleep(5);
// 104 nait APRES la photo -- il est absent de `keep` sans etre mort.
feedBattleEvent(104);
const removed = await pruneRunners(new Set([101]), snapshotAt);
check("102 purge (anterieur a la photo, absent de keep)", removed.includes(102),
    `removed=[${removed}]`);
check("104 EPARGNE (posterieur a la photo)", !removed.includes(104),
    `removed=[${removed}]`);
check("104 toujours au cache", hasRunner(104) === true);
check("101 toujours au cache (dans keep)", hasRunner(101) === true);

// Contre-epreuve : SANS la borne, 104 tombe. Si cette ligne ne purgeait pas 104,
// le test ci-dessus passerait au vert pour la mauvaise raison (borne inoperante
// parce que rien n'etait purgeable).
const removedNoBound = await pruneRunners(new Set([101]));
check("contre-epreuve : sans borne, 104 EST purge", removedNoBound.includes(104),
    `removed=[${removedNoBound}]`);

console.log("[5] REGLE 2 -- tri-etat du reconciliateur (aucune session vivante)");
feedBattleEvent(201);
feedBattleEvent(202);
const before = countRunners();
const r = await reconcileOnce();
check("hooksCount = null (PAS MESURE, jamais 0)", r.hooksCount === null,
    `hooksCount=${r.hooksCount}`);
check("erreur nommee", typeof r.error === "string" && r.error.length > 0, r.error ?? "");
check("AUCUNE purge sur mesure absente", r.removed.length === 0,
    `removed=[${r.removed}]`);
check("cache intact", countRunners() === before,
    `${before} -> ${countRunners()}`);

console.log(failures === 0
    ? "\nRESULTAT: OK -- les deux regles tiennent"
    : `\nRESULTAT: ${failures} ECHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
